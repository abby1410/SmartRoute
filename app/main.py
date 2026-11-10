
import time

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import (
    MODELS,
    CACHE_TTL_SECONDS,
    EXACT_CACHE_ENABLED,
    SEMANTIC_CACHE_ENABLED,
)
from app.database import (
    init_db,
    log_request,
    get_exact_cache,
    put_exact_cache,
    aggregate_metrics,
)
from app.cache import make_cache_key
from app.router import route_prompt
from app.providers import call_provider
from app.pricing import estimate_cost
from app.security import identify_tenant
from app.semantic_cache import semantic_cache


app = FastAPI(
    title="SmartRoute LLM Gateway",
    description="Route prompts across model tiers while tracking cost, quality and reliability.",
    version="7.0.0",
)


@app.on_event("startup")
def startup():
    init_db()


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    system_prompt: str = "You are a helpful assistant."
    strategy: str = Field(default="auto", pattern="^(auto|cheapest|strongest)$")
    use_llm_judge: bool = False
    use_cache: bool = True
    max_tokens: int = Field(default=1000, ge=1, le=8000)


@app.get("/health")
def health():
    return {"status": "healthy", "version": "7.0.0"}


@app.get("/metrics")
def metrics(tenant_id: str = Depends(identify_tenant)):
    return aggregate_metrics()


@app.post("/chat")
def chat(
    request: ChatRequest,
    tenant_id: str = Depends(identify_tenant),
):
    started = time.perf_counter()

    # 1. Determine routing decision
    route = route_prompt(request.prompt, request.use_llm_judge)

    # 2. Apply requested strategy
    if request.strategy == "cheapest":
        tier = "easy"
        reason = "Forced cheapest baseline strategy"

    elif request.strategy == "strongest":
        tier = "hard"
        reason = "Forced strongest baseline strategy"

    else:
        tier = route["tier"]
        reason = route["reason"]

    model = MODELS[tier]

    # 3. Generate exact cache key
    cache_key = make_cache_key(
        prompt=request.prompt,
        system_prompt=request.system_prompt,
        model=model,
        tenant_id=tenant_id,
        tier=tier,
        max_tokens=request.max_tokens,
    )

    # 4. Check exact cache
    if request.use_cache and EXACT_CACHE_ENABLED:
        cached = get_exact_cache(
            cache_key,
            tenant_id,
            CACHE_TTL_SECONDS,
        )

        if cached:
            latency = (time.perf_counter() - started) * 1000

            result = {
                "answer": cached["answer"],
                "model": cached["model"],
                "provider": cached["provider"],
                "tier": cached["tier"],
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0,
                "latency_ms": latency,
                "cache_hit": True,
                "fallback_used": False,
                "route": route,
                "strategy": request.strategy,
                "message": "Exact cache hit; no generation call made.",
            }

            log_request({
                "tenant_id": tenant_id,
                "prompt": request.prompt,
                "strategy": request.strategy,
                "tier": tier,
                "model": cached["model"],
                "provider": cached["provider"],
                "answer": cached["answer"],
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0,
                "latency_ms": latency,
                "cache_hit": True,
                "fallback_used": False,
                "route_reason": reason,
            })

            return result

    # 5. Check semantic cache
    if request.use_cache and SEMANTIC_CACHE_ENABLED:
        cached = semantic_cache.find(
            prompt=request.prompt,
            tenant_id=tenant_id,
            system_prompt=request.system_prompt,
            model=model,
            tier=tier,
            max_tokens=request.max_tokens,
            ttl=CACHE_TTL_SECONDS,
        )

        if cached:
            latency = (time.perf_counter() - started) * 1000

            result = {
                "answer": cached["answer"],
                "model": cached["model"],
                "provider": cached["provider"],
                "tier": cached["tier"],
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0,
                "latency_ms": latency,
                "cache_hit": True,
                "fallback_used": False,
                "semantic_similarity": cached.get("semantic_similarity"),
                "route": route,
                "strategy": request.strategy,
                "message": "Semantic cache hit; reused a similar request.",
            }

            log_request({
                "tenant_id": tenant_id,
                "prompt": request.prompt,
                "strategy": request.strategy,
                "tier": tier,
                "model": cached["model"],
                "provider": cached["provider"],
                "answer": cached["answer"],
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0,
                "latency_ms": latency,
                "cache_hit": True,
                "fallback_used": False,
                "route_reason": reason,
            })

            return result

    # 6. Generate response from provider
    try:
        provider_result = call_provider(
            request.prompt,
            request.system_prompt,
            model,
            max_tokens=request.max_tokens,
        )

    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # 7. Calculate usage and cost
    input_tokens = provider_result["input_tokens"]
    output_tokens = provider_result["output_tokens"]

    cost = estimate_cost(
        tier,
        input_tokens,
        output_tokens,
    )

    latency = (time.perf_counter() - started) * 1000

    # 8. Prepare API response
    result = {
        "answer": provider_result["answer"],
        "model": provider_result["model"],
        "provider": provider_result["provider"],
        "tier": tier,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": cost,
        "latency_ms": latency,
        "cache_hit": False,
        "fallback_used": provider_result["fallback_used"],
        "route": route,
        "strategy": request.strategy,
        "message": "Generated by provider.",
    }

    # 9. Prepare cache payload
    cache_payload = {
        "answer": result["answer"],
        "model": result["model"],
        "tier": tier,
        "provider": result["provider"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }

    # 10. Save to exact cache
    if request.use_cache and EXACT_CACHE_ENABLED:
        put_exact_cache(
            cache_key,
            tenant_id,
            cache_payload,
        )

    # 11. Save to semantic cache
    if request.use_cache and SEMANTIC_CACHE_ENABLED:
        semantic_cache.add(
            prompt=request.prompt,
            tenant_id=tenant_id,
            result=cache_payload,
            system_prompt=request.system_prompt,
            model=model,
            tier=tier,
            max_tokens=request.max_tokens,
        )

    # 12. Log generated request
    log_request({
        "tenant_id": tenant_id,
        "prompt": request.prompt,
        "strategy": request.strategy,
        "tier": tier,
        "model": result["model"],
        "provider": result["provider"],
        "answer": result["answer"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": cost,
        "latency_ms": latency,
        "cache_hit": False,
        "fallback_used": result["fallback_used"],
        "route_reason": reason,
    })

    return result

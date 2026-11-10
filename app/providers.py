import time
import requests
from app.config import (
    GROQ_API_KEY, OPENROUTER_API_KEY, GROQ_BASE_URL, OPENROUTER_BASE_URL,
    PRIMARY_PROVIDER, FALLBACK_PROVIDER, MAX_RETRIES, RETRY_BASE_SECONDS,
    CIRCUIT_FAILURE_THRESHOLD, CIRCUIT_RESET_SECONDS
)
from app.resilience import CircuitBreaker, CircuitOpenError

breaker = CircuitBreaker(CIRCUIT_FAILURE_THRESHOLD, CIRCUIT_RESET_SECONDS)

PROVIDERS = {
    "groq": {"key": GROQ_API_KEY, "base": GROQ_BASE_URL},
    "openrouter": {"key": OPENROUTER_API_KEY, "base": OPENROUTER_BASE_URL},
}

def _single_call(prompt, system_prompt, model, provider, max_tokens, temperature):
    config = PROVIDERS.get(provider)
    if not config or not config["key"]:
        raise RuntimeError(f"Provider '{provider}' is not configured")
    response = requests.post(
        f"{config['base']}/chat/completions",
        headers={
            "Authorization": f"Bearer {config['key']}",
            "Content-Type": "application/json",
            **({"HTTP-Referer": "http://localhost", "X-Title": "SmartRoute"} if provider == "openrouter" else {})
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        },
        timeout=60
    )
    response.raise_for_status()
    body = response.json()
    choice = body["choices"][0]["message"]["content"]
    usage = body.get("usage") or {}
    return {
        "answer": choice,
        "model": body.get("model", model),
        "provider": provider,
        "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "output_tokens": int(usage.get("completion_tokens", 0) or 0),
    }

def call_provider(prompt, system_prompt, model, provider_preference=None,
                  max_tokens=1000, temperature=0.3):
    primary = provider_preference or PRIMARY_PROVIDER
    candidates = [primary]
    if FALLBACK_PROVIDER and FALLBACK_PROVIDER != primary:
        candidates.append(FALLBACK_PROVIDER)
    errors = []
    for provider in candidates:
        for attempt in range(MAX_RETRIES + 1):
            try:
                breaker.before_call(provider)
                result = _single_call(prompt, system_prompt, model, provider, max_tokens, temperature)
                breaker.success(provider)
                result["fallback_used"] = provider != primary
                return result
            except CircuitOpenError as exc:
                errors.append(str(exc))
                break
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                # Retry rate limits and transient server errors only.
                if status not in (408, 409, 429, 500, 502, 503, 504):
                    breaker.failure(provider)
                    errors.append(f"{provider}: {exc}")
                    break
                breaker.failure(provider)
                errors.append(f"{provider}: HTTP {status}")
            except Exception as exc:
                breaker.failure(provider)
                errors.append(f"{provider}: {exc}")
                break
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SECONDS * (2 ** attempt))
    raise RuntimeError("All configured providers failed: " + " | ".join(errors))

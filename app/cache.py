
import hashlib
import json


def make_cache_key(
    prompt: str,
    system_prompt: str,
    model: str,
    tenant_id: str,
    tier: str,
    max_tokens: int
) -> str:
    """
    Generate a unique cache key for an exact request context.

    Including tenant, model, tier and max_tokens prevents
    incompatible requests from sharing cached responses.
    """

    cache_context = {
        "tenant": tenant_id,
        "prompt": prompt,
        "system_prompt": system_prompt,
        "model": model,
        "tier": tier,
        "max_tokens": max_tokens
    }

    raw = json.dumps(
        cache_context,
        sort_keys=True,
        ensure_ascii=False
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()

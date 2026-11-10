import time
from collections import defaultdict, deque
from fastapi import Header, HTTPException
from app.config import API_KEY, RATE_LIMIT_PER_MINUTE

_hits = defaultdict(deque)

def identify_tenant(
    x_api_key: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default="default")
):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    tenant = (x_tenant_id or "default").strip()[:100]
    now = time.time()
    queue = _hits[tenant]
    while queue and now - queue[0] > 60:
        queue.popleft()
    if len(queue) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    queue.append(now)
    return tenant

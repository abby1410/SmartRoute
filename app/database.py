import json
import sqlite3
import time
from contextlib import contextmanager
from app.config import DATABASE_PATH

@contextmanager
def connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with connection() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            tenant_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            strategy TEXT NOT NULL,
            tier TEXT NOT NULL,
            model TEXT NOT NULL,
            provider TEXT NOT NULL,
            answer TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0,
            latency_ms REAL DEFAULT 0,
            cache_hit INTEGER DEFAULT 0,
            fallback_used INTEGER DEFAULT 0,
            route_reason TEXT DEFAULT ''
        )
        """)
        db.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            cache_key TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            answer TEXT NOT NULL,
            model TEXT NOT NULL,
            tier TEXT NOT NULL,
            provider TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            created_at REAL NOT NULL
        )
        """)

def log_request(row: dict):
    with connection() as db:
        db.execute("""
        INSERT INTO requests (
            created_at, tenant_id, prompt, strategy, tier, model, provider,
            answer, input_tokens, output_tokens, estimated_cost, latency_ms,
            cache_hit, fallback_used, route_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time(), row.get("tenant_id", "default"), row["prompt"],
            row["strategy"], row["tier"], row["model"], row["provider"],
            row["answer"], row.get("input_tokens", 0), row.get("output_tokens", 0),
            row.get("estimated_cost", 0), row.get("latency_ms", 0),
            int(row.get("cache_hit", False)), int(row.get("fallback_used", False)),
            row.get("route_reason", "")
        ))

def get_exact_cache(cache_key: str, tenant_id: str, ttl: int):
    with connection() as db:
        row = db.execute(
            """
            SELECT * FROM cache
            WHERE cache_key = ? AND tenant_id = ?
            """,
            (cache_key, tenant_id)
        ).fetchone()

        if not row:
            return None

        if time.time() - row["created_at"] > ttl:
            db.execute(
                """
                DELETE FROM cache
                WHERE cache_key = ? AND tenant_id = ?
                """,
                (cache_key, tenant_id)
            )
            return None

        return dict(row)


def put_exact_cache(cache_key: str, tenant_id: str, result: dict):
    with connection() as db:
        db.execute("""
        INSERT OR REPLACE INTO cache
        (cache_key, tenant_id, answer, model, tier, provider, input_tokens, output_tokens, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cache_key, tenant_id, result["answer"], result["model"], result["tier"],
            result["provider"], result.get("input_tokens", 0),
            result.get("output_tokens", 0), time.time()
        ))

def recent_requests(limit: int = 500, tenant_id: str | None = None):
    with connection() as db:
        if tenant_id:
            rows = db.execute(
                "SELECT * FROM requests WHERE tenant_id=? ORDER BY id DESC LIMIT ?",
                (tenant_id, limit)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]

def aggregate_metrics():
    rows = recent_requests(10000)
    if not rows:
        return {"requests": 0, "total_cost": 0, "avg_latency_ms": 0,
                "cache_hit_rate": 0, "fallback_rate": 0}
    n = len(rows)
    return {
        "requests": n,
        "total_cost": sum(r["estimated_cost"] for r in rows),
        "avg_latency_ms": sum(r["latency_ms"] for r in rows) / n,
        "cache_hit_rate": sum(r["cache_hit"] for r in rows) / n,
        "fallback_rate": sum(r["fallback_used"] for r in rows) / n,
    }

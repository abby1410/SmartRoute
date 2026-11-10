
import hashlib
import json
import time

from app.config import SEMANTIC_MODEL, SEMANTIC_CACHE_THRESHOLD


class SemanticCache:
    """
    In-memory semantic cache.

    Entries are isolated by tenant and request context.
    The embedding model is loaded only when first needed.
    """

    def __init__(self, max_items: int = 500):
        self.model = None
        self.items = []
        self.max_items = max_items

    def _load_model(self):
        """Load the embedding model only when needed."""
        if self.model is not None:
            return True

        try:
            from sentence_transformers import SentenceTransformer

            print(f"Loading semantic embedding model: {SEMANTIC_MODEL}")
            self.model = SentenceTransformer(SEMANTIC_MODEL)
            print("Semantic embedding model loaded.")
            return True

        except Exception as exc:
            print(f"Semantic cache unavailable: {type(exc).__name__}: {exc}")
            return False

    @property
    def available(self):
        return self._load_model()

    def _context_key(
        self,
        system_prompt: str,
        model: str,
        tier: str,
        max_tokens: int
    ) -> str:
        context = {
            "system_prompt": system_prompt,
            "model": model,
            "tier": tier,
            "max_tokens": max_tokens
        }

        raw = json.dumps(context, sort_keys=True, ensure_ascii=False)

        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def find(
        self,
        prompt: str,
        tenant_id: str,
        system_prompt: str,
        model: str,
        tier: str,
        max_tokens: int,
        ttl: int
    ):
        if not self.available:
            return None

        import numpy as np

        now = time.time()

        # Remove expired entries before searching.
        self.items = [
            item for item in self.items
            if now - item["created_at"] <= ttl
        ]

        context_key = self._context_key(
            system_prompt, model, tier, max_tokens
        )

        query_embedding = self.model.encode(
            [prompt],
            normalize_embeddings=True
        )[0]

        best = None
        best_score = -1

        for item in self.items:
            if item["tenant_id"] != tenant_id:
                continue

            if item["context_key"] != context_key:
                continue

            score = float(np.dot(query_embedding, item["embedding"]))

            if score > best_score:
                best = item
                best_score = score

        if best is not None and best_score >= SEMANTIC_CACHE_THRESHOLD:
            return {
                **best["result"],
                "semantic_similarity": best_score
            }

        return None

    def add(
        self,
        prompt: str,
        tenant_id: str,
        result: dict,
        system_prompt: str,
        model: str,
        tier: str,
        max_tokens: int
    ):
        if not self.available:
            return

        embedding = self.model.encode(
            [prompt],
            normalize_embeddings=True
        )[0]

        context_key = self._context_key(
            system_prompt, model, tier, max_tokens
        )

        self.items.append({
            "tenant_id": tenant_id,
            "context_key": context_key,
            "embedding": embedding,
            "result": result,
            "created_at": time.time()
        })

        # Keep only the newest entries.
        if len(self.items) > self.max_items:
            self.items = self.items[-self.max_items:]


semantic_cache = SemanticCache()

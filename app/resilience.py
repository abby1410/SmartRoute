import time
from collections import defaultdict

class CircuitOpenError(RuntimeError):
    pass

class CircuitBreaker:
    def __init__(self, threshold=3, reset_seconds=30):
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.failures = defaultdict(int)
        self.opened_at = {}

    def before_call(self, key: str):
        opened = self.opened_at.get(key)
        if opened is None:
            return
        if time.time() - opened >= self.reset_seconds:
            self.opened_at.pop(key, None)
            self.failures[key] = 0
            return
        raise CircuitOpenError(f"Circuit is open for {key}")

    def success(self, key: str):
        self.failures[key] = 0
        self.opened_at.pop(key, None)

    def failure(self, key: str):
        self.failures[key] += 1
        if self.failures[key] >= self.threshold:
            self.opened_at[key] = time.time()

import time
from threading import Lock

class TokenBucketRateLimiter:
    """
    A simple in-memory Token Bucket rate limiter to restrict calling frequency.
    """
    def __init__(self, capacity: int = 5, fill_rate: float = 5.0 / 60.0):
        self.capacity = capacity
        self.fill_rate = fill_rate  # tokens per second
        self.buckets = {}
        self.lock = Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            if key not in self.buckets:
                # First time seeing this key, initialize with capacity and consume 1 token
                self.buckets[key] = {'tokens': self.capacity - 1, 'last_update': now}
                return True
            
            bucket = self.buckets[key]
            elapsed = now - bucket['last_update']
            
            # Refill tokens based on time elapsed
            tokens_to_add = elapsed * self.fill_rate
            bucket['tokens'] = min(self.capacity, bucket['tokens'] + tokens_to_add)
            bucket['last_update'] = now
            
            if bucket['tokens'] >= 1:
                bucket['tokens'] -= 1
                return True
            else:
                return False

# Global instance: 5 requests per minute
tool_rate_limiter = TokenBucketRateLimiter(capacity=5, fill_rate=5.0 / 60.0)

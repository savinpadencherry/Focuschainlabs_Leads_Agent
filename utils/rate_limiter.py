import time


class RateLimiter:
    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0

    def wait(self):
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


# One limiter per external API — import these everywhere
apollo_limiter = RateLimiter(calls_per_second=1.0)
serper_limiter = RateLimiter(calls_per_second=2.0)
gemini_limiter = RateLimiter(calls_per_second=3.0)

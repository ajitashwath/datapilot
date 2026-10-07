import threading
import time
from collections import defaultdict, deque

from app.errors import UserError
from app.metrics import metrics


class RateLimiter:
    def __init__(self):
        self.hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self.guard = threading.Lock()

    def check(self, scope: str, key: str, limit: int, window_seconds: float) -> None:
        now = time.monotonic()
        with self.guard:
            window = self.hits[(scope, key)]
            while window and now - window[0] > window_seconds:
                window.popleft()
            if len(window) >= limit:
                retry_after = max(1, int(window_seconds - (now - window[0])) + 1)
                metrics.inc("datapilot_rate_limited_total", scope=scope)
                raise UserError(
                    f"Too many requests. Please wait {retry_after} seconds and try again.", "rate_limited", 429,
                    headers={"Retry-After": str(retry_after)},
                )
            window.append(now)
            if len(self.hits) > 10000:
                stale = [k for k, v in self.hits.items() if not v or now - v[-1] > 3600]
                for k in stale:
                    del self.hits[k]

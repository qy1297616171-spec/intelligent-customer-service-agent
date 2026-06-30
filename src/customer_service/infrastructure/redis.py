import time
from threading import Lock

from redis import Redis
from redis.exceptions import RedisError


def create_redis_client(url: str) -> Redis:
    return Redis.from_url(
        url, decode_responses=True, socket_connect_timeout=0.4,
        socket_timeout=0.6, health_check_interval=30,
    )


class RateLimiter:
    def __init__(self, client: Redis | None = None) -> None:
        self._client = client
        self._local: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        if self._client is not None:
            try:
                redis_key = f"cs:rate:{key}:{int(time.time() // window_seconds)}"
                pipeline = self._client.pipeline()
                pipeline.incr(redis_key)
                pipeline.expire(redis_key, window_seconds + 1)
                count, _ = pipeline.execute()
                return count <= limit, max(0, limit - count)
            except RedisError:
                pass
        window = int(time.time() // window_seconds)
        with self._lock:
            current_window, count = self._local.get(key, (window, 0))
            if current_window != window:
                count = 0
            count += 1
            self._local[key] = (window, count)
        return count <= limit, max(0, limit - count)

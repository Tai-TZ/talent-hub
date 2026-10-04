"""Giới hạn tốc độ theo cửa sổ cố định. Redis khi chạy nhiều tiến trình; bộ nhớ khi chạy local."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateResult:
    allowed: bool
    retry_after_s: int


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_s: int) -> RateResult: ...

    async def close(self) -> None: ...


class MemoryRateLimiter:
    """Chỉ dùng cho local/test: trạng thái nằm trong một tiến trình."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window_s: int) -> RateResult:
        now = time.monotonic()
        async with self._lock:
            count, reset_at = self._buckets.get(key, (0, now + window_s))
            if reset_at <= now:
                count, reset_at = 0, now + window_s
            count += 1
            self._buckets[key] = (count, reset_at)
            if len(self._buckets) > 10_000:
                self._buckets = {k: v for k, v in self._buckets.items() if v[1] > now}
        return RateResult(count <= limit, max(1, int(reset_at - now)))

    async def close(self) -> None:
        self._buckets.clear()


class RedisRateLimiter:
    def __init__(self, url: str) -> None:
        self._redis: Redis = Redis.from_url(url, socket_timeout=0.25, socket_connect_timeout=0.25)

    async def hit(self, key: str, limit: int, window_s: int) -> RateResult:
        redis_key = f"rl:{key}"
        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_s, nx=True)  # nguyên tử với INCR nhờ MULTI
            pipe.ttl(redis_key)
            count, _, ttl = await pipe.execute()
        except RedisError:
            # Redis lỗi thì không chặn người dùng thật; lockout theo tài khoản vẫn còn hiệu lực.
            logger.warning("rate limiter không khả dụng, cho phép yêu cầu", exc_info=True)
            return RateResult(True, 0)
        return RateResult(count <= limit, max(1, int(ttl)))

    async def close(self) -> None:
        await self._redis.aclose()


def create_rate_limiter(redis_url: str | None) -> RateLimiter:
    return RedisRateLimiter(redis_url) if redis_url else MemoryRateLimiter()

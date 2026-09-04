"""캐시 접근을 감싸는 함수들.

Redis 는 원본이 아니라 사본이다. 죽어도 서비스는 계속돼야 한다.
그래서 캐시 실패는 예외로 올리지 않고 "캐시가 없는 것"으로 처리한다.
"""

import logging

from redis.exceptions import RedisError

from app.redis_client import r

logger = logging.getLogger(__name__)


def cache_get(key: str) -> str | None:
    """캐시에서 읽는다. 실패하면 None (= 캐시 없음)."""
    try:
        return r.get(key)
    except RedisError as error:
        logger.warning("캐시 조회 실패 (%s): %s", key, error)
        return None


def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    """캐시에 쓴다. 실패해도 무시한다."""
    try:
        r.set(key, value, ex=ttl_seconds)
    except RedisError as error:
        logger.warning("캐시 저장 실패 (%s): %s", key, error)


def cache_delete(key: str) -> None:
    """캐시를 지운다. 실패해도 무시한다."""
    try:
        r.delete(key)
    except RedisError as error:
        logger.warning("캐시 삭제 실패 (%s): %s", key, error)
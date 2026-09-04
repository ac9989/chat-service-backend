import hashlib
import json
from dataclasses import dataclass
from uuid import UUID
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import get_anon_client
from app.cache import cache_get, cache_set

bearer_scheme = HTTPBearer()

SESSION_CACHE_TTL_SECONDS = 300

@dataclass
class CurrentUser:
    id: str
    email: str
    token: str

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    # "Bearer " 접두어는 HTTPBearer 가 이미 떼어냈다.
    # 헤더가 없거나 형식이 틀리면 여기 오기 전에 401 로 막힌다.
    token = credentials.credentials
    cache_key = f"session:{hashlib.sha256(token.encode()).hexdigest()}"

    cached = cache_get(cache_key)
    if cached:
        data = json.loads(cached)
        return CurrentUser(id=data["id"], email=data["email"], token=token)

    client = get_anon_client()
    try:
        result = client.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")

    current_user = CurrentUser(id=str(result.user.id), email=result.user.email, token=token)
    cache_set(
        cache_key,
        json.dumps({"id": current_user.id, "email": current_user.email}),
        ttl_seconds=SESSION_CACHE_TTL_SECONDS,
    )

    return CurrentUser(id=str(result.user.id), email=result.user.email, token=token)

def require_own_conversation(
    conversation_id: UUID, current_user: CurrentUser = Depends(get_current_user)
) -> UUID:
    """이 대화가 내 것인지 확인한다. 아니면 404.

    18일차의 /me/conversations 와 같은 원리다. 우리가 소유자를 비교하지 않는다.
    RLS 를 켠 클라이언트로 조회해서 0건이면 내 것이 아니다.

    없는 대화와 남의 대화를 구분하지 않고 똑같이 404 로 답한다.
    구분해서 알려주면 "그 대화는 존재한다"는 정보를 흘리게 된다.
    """
    client = get_anon_client()
    client.postgrest.auth(current_user.token)
    owned = (
        client.table("conversations")
        .select("id")
        .eq("id", str(conversation_id))
        .execute()
    )
    if not owned.data:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation_id




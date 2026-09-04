"""대화·메시지 API (실습 6·7).

메서드   주소                                  하는 일                성공 코드
POST     /conversations                        대화 생성               201
GET      /conversations?user_id=               사용자별 대화 목록       200
POST     /conversations/{id}/messages          메시지 저장             201
GET      /conversations/{id}/messages          메시지 목록             200
"""
import json

from app.cache import cache_delete, cache_get, cache_set
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_own_conversation

from app.db import supabase
from app.schemas import ConversationCreate, ConversationOut, MessageCreate, MessageOut

# TODO 0. app.schemas 에서 ConversationCreate, ConversationOut,
#         MessageCreate, MessageOut 을 가져온다

router = APIRouter(prefix="/conversations", tags=["conversations"])
MESSAGES_CACHE_TTL_SECONDS = 300
def _messages_cache_key(conversation_id: UUID) -> str:
    return f"messages:{conversation_id}"

# ── 실습 6 ────────────────────────────────────────────────────────
# TODO 1. POST "" — 대화 생성
#   · insert 전에 profiles 에 그 user_id 가 있는지 확인한다.
#     DB의 외래키도 막아주지만 그대로 두면 500 이 난다. 먼저 확인해 404 로 알리는 편이 친절하다.
#   · 없으면 404 "사용자를 찾을 수 없습니다"
# @router.post("", response_model=ConversationOut, status_code=201)
# def create_conversation(payload: ConversationCreate):
#     #사용자 id 가져오기
#     user = supabase.table("profiles").select("id").eq("id", str(payload.user_id)).execute()

#     #없으면 404
#     if not user.data:
#         raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

#     #대화생성
#     result = (
#         supabase.table("conversations")
#         .insert({"user_id": str(payload.user_id), "title": payload.title})
#         .execute()
#     )
#     return result.data[0]

@router.post("/{conversation_id}/messages", response_model=MessageOut)
def post_message(
    payload: MessageCreate, conversation_id: UUID = Depends(require_own_conversation)
):
    return create_message(conversation_id, payload)


# TODO 2. GET "" — 사용자별 대화 목록
#   · user_id 는 주소 뒤 ?user_id=... 로 온다. 함수 인자에 그냥 적으면 된다.
#   · 기본값을 주지 않으면 필수가 되고, 빠뜨리면 FastAPI 가 422 로 막는다.
#   · 최신순 정렬
# @router.get("", response_model=list[ConversationOut])
# def list_conversations(user_id: UUID):
#     result = (
#         supabase.table("conversations")
#         .select("*")
#         .eq("user_id", str(user_id))
#         .order("created_at", desc=True)
#         .execute()
#     )
#     return result.data

@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def get_messages(conversation_id: UUID = Depends(require_own_conversation)):
    return list_messages(conversation_id)

# ── 실습 7 ────────────────────────────────────────────────────────
# 주의: 정렬 방향이 대화와 반대다.
#       대화 목록은 최신순(desc=True)이지만,
#       메시지는 오래된 것부터(desc=False)여야 대화 흐름 그대로 읽힌다.

# @router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=201)
def create_message(conversation_id: UUID, payload: MessageCreate):
    conversation = (
        supabase.table("conversations")
        .select("id")
        .eq("id", str(conversation_id))
        .execute()
    )
    if not conversation.data:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")

    result = (
        supabase.table("messages")
        .insert(
            {
                "conversation_id": str(conversation_id),
                "role": payload.role,
                "content": payload.content,
            }
        )
        .execute()
    )
    cache_delete(_messages_cache_key(conversation_id)) 
    return result.data[0]


# @router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: UUID):
    cache_key = _messages_cache_key(conversation_id)

    cached = cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", str(conversation_id))
        .order("created_at", desc=False)
        .execute()
    )
    cache_set(
        cache_key,
        json.dumps(result.data, default=str),
        ttl_seconds=MESSAGES_CACHE_TTL_SECONDS,
    )
    return result.data

# 문제 1. 대화 제목 수정
from app.schemas import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
)

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from app.db import get_anon_client
from app.deps import CurrentUser, get_current_user
from app.schemas import ConversationOut, ConversationUpdate, MyConversationCreate, ProfileOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def read_me(current_user: CurrentUser = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email}


@router.get("/conversations", response_model=list[ConversationOut])
def my_conversations(current_user: CurrentUser = Depends(get_current_user)):
    client = get_anon_client()
    client.postgrest.auth(current_user.token)
    result = (
        client.table("conversations")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data

# 문제 1. 내 프로필 조회
@router.get("/profile", response_model=ProfileOut)
def read_my_profile(current_user: CurrentUser = Depends(get_current_user)):
    client = get_anon_client()
    client.postgrest.auth(current_user.token)
    result = client.table("profiles").select("*").execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다")
    return result.data[0]

@router.post("/conversations", response_model=ConversationOut)
def create_my_conversation(
    payload: MyConversationCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_anon_client()
    client.postgrest.auth(current_user.token)
    result = (
        client.table("conversations")
        .insert({"user_id": current_user.id, "title": payload.title})
        .execute()
    )
    return result.data[0]


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_my_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_anon_client()
    client.postgrest.auth(current_user.token)
    result = (
        client.table("conversations")
        .update({"title": payload.title})
        .eq("id", str(conversation_id))
        .execute()
    )
    if not result.data:
        # 없는 대화와 남의 대화를 구분하지 않고 똑같이 404 로 답한다.
        # 구분해서 알려주면 "그 대화는 존재한다"는 정보를 흘리게 된다.
        raise HTTPException(status_code=404, detail="conversation not found")
    return result.data[0]

@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_my_conversation(
    conversation_id: UUID, current_user: CurrentUser = Depends(get_current_user)
):
    client = get_anon_client()
    client.postgrest.auth(current_user.token)
    result = (
        client.table("conversations").delete().eq("id", str(conversation_id)).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="conversation not found")


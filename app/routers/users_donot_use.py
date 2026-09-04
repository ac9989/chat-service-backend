"""사용자 정보 관리 API (실습 4·5).

메서드   주소                하는 일              성공 코드
POST     /users              사용자 등록           201
GET      /users              사용자 목록(최신순)    200
GET      /users/{user_id}    사용자 한 명 조회      200
PATCH    /users/{user_id}    username 수정         200
DELETE   /users/{user_id}    사용자 삭제           204
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db import supabase

# TODO 0. app.schemas 에서 UserCreate, UserOut, UserUpdate 를 가져온다
from app.schemas import UserCreate, UserOut, UserUpdate
router = APIRouter(prefix="/users", tags=["users"])


# ── 실습 4 ────────────────────────────────────────────────────────
# TODO 1. POST "" — 사용자 등록
#   · @router.post("", response_model=UserOut, status_code=201)
#   · insert 하기 전에 select 로 같은 email 이 있는지 먼저 본다
#   · 있으면 raise HTTPException(status_code=409, detail="이미 등록된 이메일입니다")
#   · 반환은 result.data[0]

@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate):
    existing = (
        supabase.table("users").select("id").eq("email", payload.email).execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="이미 등록된 이메일입니다")

    result = (
        supabase.table("users")
        .insert({"email": payload.email, "username": payload.username})
        .execute()
    )
    return result.data[0]

# TODO 2. GET "" — 사용자 목록
#   · response_model=list[UserOut]
#   · .order("created_at", desc=True) 로 최신 가입순
#문제 3. 이메일로 사용자 찾기
@router.get("", response_model=list[UserOut])
def list_users(email: str | None = None):
    query = supabase.table("users").select("*")
    if email:
        query = query.eq("email", email)
    result = query.order("created_at", desc=True).execute()
    return result.data

# ── 실습 5 ────────────────────────────────────────────────────────
# 주의: supabase 라이브러리에는 UUID 객체가 아니라 문자열을 넘겨야 한다.
#       str() 로 감싸지 않으면 조회 결과가 항상 비어 404 가 난다.
#
# 주의: update / delete 는 "바뀐 행"을 리스트로 돌려준다.
#       리스트가 비어 있으면 대상이 없었다는 뜻이므로 404 로 알린다.

# TODO 3. GET "/{user_id}" — 한 명 조회. 없으면 404 "사용자를 찾을 수 없습니다"
@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: UUID):
    result = supabase.table("users").select("*").eq("id", str(user_id)).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return result.data[0]

# TODO 4. PATCH "/{user_id}" — username 수정. 없으면 404
@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UserUpdate):
    result = (
        supabase.table("users")
        .update({"username": payload.username})
        .eq("id", str(user_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return result.data[0]

# TODO 5. DELETE "/{user_id}" — 삭제. status_code=204 이므로 아무것도 반환하지 않는다
@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: UUID):
    result = supabase.table("users").delete().eq("id", str(user_id)).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
from fastapi import APIRouter, HTTPException

from app.db import get_anon_client
from app.schemas import LoginRequest, SignupRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest):
    client = get_anon_client()
    try:
        result = client.auth.sign_up(
            {"email": payload.email, "password": payload.password}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    access_token = result.session.access_token if result.session else None
    return TokenResponse(
        access_token=access_token,
        user_id=str(result.user.id),
        email=result.user.email,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    client = get_anon_client()
    try:
        result = client.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

    return TokenResponse(
        access_token=result.session.access_token,
        user_id=str(result.user.id),
        email=result.user.email,
    )
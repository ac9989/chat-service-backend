"""FastAPI 앱 진입점.

실행:  uv run uvicorn app.main:app --reload
확인:  http://127.0.0.1:8000/health  ·  http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI

app = FastAPI(title="chat-service", version="0.1.0")


# 주의: 라우터는 실습 4와 실습 6에서 하나씩 등록한다.
# 파일을 만들기 전에 import 하면 ModuleNotFoundError 로 서버가 아예 뜨지 않는다.
# TODO 1. (실습 4) from app.routers import users  ->  app.include_router(users.router)

from app.routers import conversations, auth, me, chat


@app.get("/health")
def health():
    return {"status": "ok"}

# TODO 2. (실습 6) from app.routers import conversations  ->  app.include_router(conversations.router)

@app.get("/health")
def health():
    return {"status": "ok"}


# app.include_router(users.router)
app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(chat.options_router)
app.include_router(auth.router)
app.include_router(me.router)
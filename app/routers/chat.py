"""면접관 응답을 만드는 라우터.

오늘은 단발성이다. 이전 대화를 모델에 넘기지 않는다 (19일차에 붙인다).
스트리밍도 아직이다 (20일차). 질문 하나에 답 하나다.
"""

import time
from uuid import UUID
from datetime import datetime, timezone

from fastapi.responses import StreamingResponse
from fastapi import APIRouter, HTTPException, Depends
from google.genai import types
import json

from app.db import supabase
from app.deps import require_own_conversation
from app.gemini_client import (
    DEFAULT_LENGTH,
    DEFAULT_TONE,
    GEMINI_MODEL,
    LENGTHS,
    TONES,
    build_system_prompt,
    client,
)
from app.routers.conversations import create_message, list_messages
from app.schemas import ChatRequest, MessageCreate, MessageOut, RegenerateRequest, FeedbackRequest

from app.redis_client import r

router = APIRouter(prefix="/conversations", tags=["chat"])

# 선택지를 화면에 알려주는 라우터. 경로 모양이 달라 별도로 둔다.
options_router = APIRouter(prefix="/chat", tags=["chat"])


# 사용자와 면접관 메시지를 합쳐 최근 몇 개까지 모델에 보낼지.
# 20개면 대략 10번 주고받은 분량이다.
MAX_HISTORY_MESSAGES = 20
MAX_USAGE_LOGS = 50
CONTEXT_RESET_MARKER = "[맥락 초기화] 이 지점 이전은 면접관이 기억하지 않습니다."

# 우리 DB 의 role 을 Gemini 의 role 로 바꾼다.
# 이 표에 없는 role(system)은 아예 보내지 않는다.
# 주의: assistant 를 그대로 보내도 지금은 통과한다. 그러나 서버가 인정한다고
#      말하는 값은 MODEL 과 USER 뿐이고(다른 값은 400), 별칭은 문서에 없다.
_ROLE_MAP = {"user": "user", "assistant": "model"}

@options_router.get("/options")
def chat_options():
    """화면이 그릴 선택지를 내려준다.
	
	채팅 옵션은 gemini_client.py 의 표에서만 관리한다.
    화면에 목록을 직접 적어두면 두 곳 모두에서 관리해야 한다.
    한쪽에 톤을 추가하고 다른 쪽을 잊으면, 버튼은 있는데 아무 효과가 없다.
    """
    return {
        "tones": list(TONES),
        "lengths": list(LENGTHS),
        "default_tone": DEFAULT_TONE,
        "default_length": DEFAULT_LENGTH,
        # 화면이 "최근 20개를 기억합니다" 라고 알려줄 수 있게 함께 내려준다.
        # 화면에 숫자를 직접 적으면 여기를 고쳤을 때 안내가 거짓말이 된다.
        "max_history_messages": MAX_HISTORY_MESSAGES,  
    }


def _job_title(conversation_id: UUID) -> str:
    """대화 제목이 곧 지원 직무다. 16일차에 `새 면접 시작` 에서 받은 값이다."""
    result = (
        supabase.table("conversations")
        .select("title")
        .eq("id", str(conversation_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="conversation not found")
    return result.data[0]["title"] or "지원 직무 미지정"

def _build_history(conversation_id: UUID) -> list[dict]:
    """모델에게 보낼 이전 대화를 만든다.

    세 단계로 줄인다. 순서가 중요하다.
      1) 마지막 초기화 지점 이후만 남긴다
      2) 모델이 모르는 role(system)을 뺀다
      3) 최근 MAX_HISTORY_MESSAGES 개만 남긴다

    3번을 1번보다 먼저 하면, 최근 20개 안에 초기화 지점이 없을 때
    끊었던 옛날 대화가 다시 딸려 들어간다.
    """
    messages = list_messages(conversation_id)  # 시간 오름차순, Redis 캐시 적용됨

    for index in range(len(messages) - 1, -1, -1):
        if messages[index]["role"] == "system":
            messages = messages[index + 1 :]
            break

    usable = [m for m in messages if m["role"] in _ROLE_MAP]
    recent = usable[-MAX_HISTORY_MESSAGES:]

    return [
        {"role": _ROLE_MAP[m["role"]], "parts": [{"text": m["content"]}]}
        for m in recent
    ]

def _usage_log_key(conversation_id: UUID) -> str:
    return f"usage_log:{conversation_id}"

def _feedback_key(conversation_id: UUID) -> str:
    return f"feedback:{conversation_id}"

def _log_usage(conversation_id: UUID, started_at: float, usage) -> None:
    """언제 요청했고 얼마나 걸렸는지 남긴다.

    Redis 리스트에 넣고 최근 N건만 남긴다. 새 테이블을 만들지 않는 이유는
    이것이 서비스 데이터가 아니라 운영 기록이기 때문이다. 지워져도 서비스는 돈다.
    """
    entry = {
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "latency_ms": round((time.monotonic() - started_at) * 1000),
        "prompt_tokens": getattr(usage, "prompt_token_count", None),
        "response_tokens": getattr(usage, "candidates_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
    }
    key = _usage_log_key(conversation_id)
    r.lpush(key, json.dumps(entry))
    r.ltrim(key, 0, MAX_USAGE_LOGS - 1)

@router.post("/{conversation_id}/feedback")
def save_feedback(
    payload: FeedbackRequest,
    conversation_id: UUID = Depends(require_own_conversation),
):
    """어떤 답변이 도움이 됐는지 기록한다.

    메시지 하나에 값 하나라서 리스트가 아니라 해시를 쓴다.
    같은 메시지에 다시 누르면 덮어써야 하기 때문이다.
    """
    key = _feedback_key(conversation_id)
    if payload.value is None:
        r.hdel(key, str(payload.message_id))  # 취소
    else:
        r.hset(key, str(payload.message_id), payload.value)
    return {"message_id": str(payload.message_id), "value": payload.value}


@router.get("/{conversation_id}/feedback")
def read_feedback(conversation_id: UUID = Depends(require_own_conversation)):
    """화면이 버튼의 눌린 상태를 그릴 수 있게 전부 돌려준다."""
    return r.hgetall(_feedback_key(conversation_id))


@router.get("/{conversation_id}/usage-logs")
def usage_logs(conversation_id: UUID = Depends(require_own_conversation)):
    raw = r.lrange(_usage_log_key(conversation_id), 0, MAX_USAGE_LOGS - 1)
    return [json.loads(item) for item in raw]


@router.post("/{conversation_id}/reset-context")
def reset_context(conversation_id: UUID = Depends(require_own_conversation)):
    """맥락을 끊는다. 기록은 지우지 않는다 (19일차 참고)."""
    return create_message(
        conversation_id, MessageCreate(role="system", content=CONTEXT_RESET_MARKER)
    )

def _stream_answer(conversation_id: UUID, contents: list, system_prompt: str):
    """모델의 응답을 조각으로 흘려보내고, 끝나면 통째로 저장한다."""

    def event_stream():
        started_at = time.monotonic()
        full_text = ""
        last_usage = None
        try:
            for chunk in client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
            ):
                if chunk.text:
                    full_text += chunk.text
                    # 주의: 조각 안의 줄바꿈은 그대로 보내면 SSE 형식이 깨진다.
                    #      한 이벤트는 빈 줄로 끝나기로 약속돼 있기 때문이다.
                    yield "data: " + json.dumps({"text": chunk.text}) + "\n\n"
                if chunk.usage_metadata:
                    last_usage = chunk.usage_metadata
        except Exception as e:
            # 스트림이 이미 시작돼 상태 코드를 바꿀 수 없다. 이벤트로 알린다.
            yield "data: " + json.dumps({"error": f"{type(e).__name__}: {e}"}) + "\n\n"
            return

        if not full_text:
            yield "data: " + json.dumps({"error": "모델이 빈 응답을 돌려주었습니다."}) + "\n\n"
            return

        # 다 받은 뒤에 한 번만 저장한다. 조각마다 저장하면 메시지가 수십 개로 쪼개진다.
        saved = create_message(
            conversation_id, MessageCreate(role="assistant", content=full_text)
        )
        _log_usage(conversation_id, started_at, last_usage)
        yield "data: " + json.dumps({"done": True, "message_id": saved["id"]}) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/{conversation_id}/chat")
def chat(payload: ChatRequest, conversation_id: UUID = Depends(require_own_conversation)):
    job_title = _job_title(conversation_id)

    # 이전 대화를 먼저 만든다. 사용자 메시지를 저장한 뒤에 만들면
    # 방금 쓴 답변이 이력에도 들어가 같은 말을 두 번 보내게 된다.
    history = _build_history(conversation_id)

    create_message(conversation_id, MessageCreate(role="user", content=payload.content))
    contents = history + [{"role": "user", "parts": [{"text": payload.content}]}]

    system_prompt = build_system_prompt(job_title, payload.tone, payload.length)

    return _stream_answer(
        conversation_id,
        contents,
        system_prompt
    )


@router.post("/{conversation_id}/reset-context")
def reset_context(conversation_id: UUID = Depends(require_own_conversation)):


    """맥락을 끊는다. 기록은 지우지 않는다.

    주의: 메시지를 삭제하지 않는다. 사용자가 연습한 내용은 그대로 남아야 한다.
         지워지는 것은 "모델이 참고하는 범위"뿐이다.
    """
    return create_message(
        conversation_id, MessageCreate(role="system", content=CONTEXT_RESET_MARKER)
    )

@router.post("/{conversation_id}/regenerate")
def regenerate(payload: RegenerateRequest, conversation_id: UUID = Depends(require_own_conversation)):
    """마지막 답변을 지우고 다시 만든다.

    Retry 와 다르다. Retry 는 실패한 요청을 그대로 다시 보내는 것이고,
    Regenerate 는 성공한 답변이 마음에 안 들 때 새로 받는 것이다.
    그래서 여기서는 마지막 assistant 메시지를 지우는 일이 먼저다.
    """
    messages = list_messages(conversation_id)
    if not messages or messages[-1]["role"] != "assistant":
        raise HTTPException(status_code=400, detail="다시 생성할 답변이 없습니다.")

    supabase.table("messages").delete().eq("id", messages[-1]["id"]).execute()
    r.delete(f"messages:{conversation_id}")  # 캐시를 지워야 방금 삭제가 반영된다

    job_title = _job_title(conversation_id)
    history = _build_history(conversation_id)  # 삭제 후라 마지막 사용자 질문까지만 들어온다
    if not history:
        raise HTTPException(status_code=400, detail="다시 생성할 질문이 없습니다.")

    return _stream_answer(
        conversation_id,
        history,
        build_system_prompt(job_title, payload.tone, payload.length),
    )

"""Gemini 호출에 필요한 것들.

여기서 중요한 것은 client 가 아니라 아래 두 개의 표다.
화면에서 고른 값이 곧 프롬프트 문장이 된다. 그 대응을 한눈에 보이게 모아둔다.
"""

import os

from dotenv import load_dotenv
from google import genai

# db.py 가 먼저 import 되면 그쪽 load_dotenv() 로도 값이 채워진다.
# 그 순서에 기대지 않으려고 여기서도 부른다 — 이 파일만 단독으로 import 할 때가 있다.
load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# 주의: 모델명은 자주 바뀐다. 2026-08-17 에 새 키로 확인한 값이다.
#      이전에 쓰던 gemini-2.5-flash-lite 는 새로 발급한 키로는 404 가 난다
#      ("no longer available to new users"). 목록 조회에는 여전히 나오므로
#      models.list() 로는 알 수 없고, 실제로 호출해봐야 안다.
GEMINI_MODEL = "gemini-3.5-flash-lite"

# 이 서비스가 무엇인지. 사용자가 바꿀 수 없는 부분이다.
BASE_PROMPT = (
    "당신은 채용 면접관입니다. 지원자가 면접을 연습할 수 있도록 돕습니다. "
    "지원자의 답변을 듣고 짧게 평가한 뒤, 이어지는 면접 질문을 하나 던지세요. "
    "지원자가 실제 이름이나 연락처를 말하면 그 정보를 되풀이하지 말고 넘어가세요."
)

# 사용자가 화면에서 고르는 부분. 왼쪽이 버튼에 보이는 말, 오른쪽이 프롬프트에 들어가는 문장이다.
TONES = {
    "깐깐하게": "지원자의 답변에서 근거가 약한 부분을 날카롭게 짚습니다.",
    "친절하게": "지원자가 편하게 말할 수 있도록 격려하며 반응합니다.",
}

LENGTHS = {
    "짧게": "3문장 이내로 답하세요.",
    "보통": "5문장 내외로 답하세요.",
    "자세히": "예시를 들어 설명하되 10문장을 넘기지 마세요.",
}

DEFAULT_TONE = "친절하게"
DEFAULT_LENGTH = "보통"


def build_system_prompt(job_title: str, tone: str | None, length: str | None) -> str:
    """직무와 화면에서 고른 값으로 시스템 프롬프트를 조립한다.

    문자열을 이어 붙이는 것뿐이지만, 이 함수가 오늘의 핵심이다.
    사용자가 `깐깐하게` 를 누른 결과가 어떤 문장이 되어 모델에 가는지가 여기 다 보인다.
    """
    return " ".join(
        [
            BASE_PROMPT,
            f"지원 직무는 '{job_title}' 입니다.",
            TONES.get(tone, TONES[DEFAULT_TONE]),
            LENGTHS.get(length, LENGTHS[DEFAULT_LENGTH]),
        ]
    )
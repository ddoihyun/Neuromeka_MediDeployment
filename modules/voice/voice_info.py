import os
from pathlib import Path

from pkg.utils.file_io import load_json


API_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "api.json"
SUPPORTED_VOICE_PROVIDERS = {"gemini"}

DEFAULT_PROMPT_TEMPLATE = """
당신은 STT로부터 전달된 한국어 문장을 해석해서 항상 단 하나의 JSON 객체만 출력합니다.

STT 결과(사용자 발화):
"{stt_text}"

출력 형식:
{
  "action": <"mode" | "movel" 또는 null>,
  "aux0": <"free" | "fix" | "point" | "line" | "plane" | "right" | "left" | "up" | "down" | "forward" | "backward" | "zoom_in" | "zoom_out" | "clockwise" | "counterclockwise" | null>,
  "aux1": <사용자에게 말해줄 한국어 응답 문자열>,
  "value": <숫자 또는 null>,
  "unit": <"mm" | "cm" | "m" | "deg" 또는 null>
}

규칙:
1. JSON 객체 한 개만 출력하고, JSON 바깥의 텍스트는 출력하지 마세요.
2. 키워드는 부분 문자열로 판단합니다. 예를 들어 "정지모드로 해줘"는 "정지"를 포함하므로 aux0 = "fix"입니다.
3. "정지", "멈춰", "스톱", "고정", "락", "잠가", "픽스", "정지모드"는 aux0 = "fix"입니다.
4. "이동", "움직여", "자유", "프리", "풀어", "해제"는 aux0 = "free"입니다.
5. "점고정", "포인트", "포인트 고정", "점으로 고정"은 aux0 = "point"입니다.
6. "선고정", "라인", "라인 고정", "선으로 고정"은 aux0 = "line"입니다.
7. "면고정", "플레인", "평면 고정", "RCM", "알씨엠"은 aux0 = "plane"입니다.
8. 여러 모드 키워드가 섞이면 point > line > plane > fix > free 순서로 처리하세요.
9. "오른쪽/왼쪽/위/아래/위쪽/아래쪽/앞쪽/뒤쪽/줌인/줌아웃"처럼 숫자가 포함된 이동 명령은 action = "movel"입니다. value는 숫자만 넣고, 사용자가 말한 길이 단위가 있으면 unit에 "mm", "cm", "m" 중 하나를 넣습니다. 단위가 없으면 "mm"입니다. 위/아래 이동은 Y 값을 변경합니다.
10. "시계방향/반시계방향"처럼 숫자가 포함된 회전 명령은 action = "movel"입니다. value는 숫자만 넣고 unit은 "deg"입니다.
11. 모드와 movel 명령을 인식하지 못하면 action과 aux0은 null로 둡니다.
"""


def _load_api_config():
    try:
        config = load_json(str(API_CONFIG_PATH))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return config if isinstance(config, dict) else {}


def _get_section(config, section_name):
    section = config.get(section_name, {})
    return section if isinstance(section, dict) else {}


def _get_env_or_config(config, key, default_env_name):
    configured_env_name = config.get(f"{key}_env")
    if isinstance(configured_env_name, str):
        value = os.environ.get(configured_env_name)
        if value:
            return value

    value = os.environ.get(default_env_name)
    if value:
        return value

    configured_value = config.get(key, "")
    return configured_value if isinstance(configured_value, str) else ""


def _get_int(config, key, default):
    value = os.environ.get(key.upper())
    if value is None:
        value = config.get(key, default)

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_prompt_template(*configs):
    for config in configs:
        prompt_template = config.get("prompt_template")
        if isinstance(prompt_template, str) and prompt_template.strip():
            return prompt_template

        prompt_lines = config.get("prompt_template_lines", [])
        if isinstance(prompt_lines, list) and prompt_lines:
            return "\n".join(str(line) for line in prompt_lines)

    return DEFAULT_PROMPT_TEMPLATE.strip()


_API_CONFIG = _load_api_config()
_VOICE_CONFIG = _get_section(_API_CONFIG, "voice")
_GEMINI_CONFIG = _get_section(_API_CONFIG, "gemini")

VOICE_PROVIDER = (
    os.environ.get("VOICE_PROVIDER")
    or os.environ.get("VOICE_MODE")
    or _VOICE_CONFIG.get("provider")
    or "gemini"
)
VOICE_PROVIDER = str(VOICE_PROVIDER).strip().lower()
if VOICE_PROVIDER not in SUPPORTED_VOICE_PROVIDERS:
    VOICE_PROVIDER = "gemini"

# Backward-compatible name for code that still imports the old constant.
VOICE_LLM_PROVIDER = VOICE_PROVIDER

GEMINI_API_KEY = _get_env_or_config(_GEMINI_CONFIG, "api_key", "GEMINI_API_KEY")
GEMINI_LLM_MODEL = (
    os.environ.get("GEMINI_LLM_MODEL")
    or _GEMINI_CONFIG.get("llm_model")
    or _GEMINI_CONFIG.get("model")
    or "gemini-3.1-flash-lite"
)
GEMINI_STT_MODEL = (
    os.environ.get("GEMINI_STT_MODEL")
    or _GEMINI_CONFIG.get("stt_model")
    or _GEMINI_CONFIG.get("transcription_model")
    or _GEMINI_CONFIG.get("model")
    or GEMINI_LLM_MODEL
)
LLM_TIMEOUT_SECONDS = _get_int(_VOICE_CONFIG, "llm_timeout_seconds", 30)
STT_TIMEOUT_SECONDS = _get_int(_VOICE_CONFIG, "stt_timeout_seconds", 60)

GEMINI_LLM_URL = (
    os.environ.get("GEMINI_LLM_URL")
    or _GEMINI_CONFIG.get("llm_url")
    or _GEMINI_CONFIG.get("api_url")
    or f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_LLM_MODEL}:generateContent"
)
GEMINI_TRANSCRIPTION_URL = (
    os.environ.get("GEMINI_TRANSCRIPTION_URL")
    or os.environ.get("GEMINI_STT_URL")
    or _GEMINI_CONFIG.get("transcription_url")
    or _GEMINI_CONFIG.get("stt_url")
    or f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_STT_MODEL}:generateContent"
)
PROMPT_TEMPLATE = _load_prompt_template(_VOICE_CONFIG, _GEMINI_CONFIG)

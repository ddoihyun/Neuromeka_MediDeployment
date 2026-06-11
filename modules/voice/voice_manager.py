from modules.global_func import get_time
import traceback
from modules.voice.voice_info import (
    GEMINI_API_KEY,
    GEMINI_LLM_URL,
    GEMINI_TRANSCRIPTION_URL,
    LLM_TIMEOUT_SECONDS,
    PROMPT_TEMPLATE,
    STT_TIMEOUT_SECONDS,
    VOICE_PROVIDER,
)
from pkg.utils.blackboard import GlobalBlackboard
import threading
import time
from pkg.utils.logging import Logger

import base64
import json
import os
import re
import wave
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pygame
import requests
import sounddevice as sd
from gtts import gTTS

bb = GlobalBlackboard()

SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
TTS_PATH = "tts_output.mp3"
AUDIO_MIME_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}

VOICE_MODE_AUX = {"free", "fix", "point", "line", "plane", "rcm"}
VOICE_MOVEL_ACTIONS = {"movel", "move_l", "move", "rotate", "zoom"}
VOICE_CONTROL_ACTIONS = {"mode", "movel"}
VOICE_LINEAR_DEFAULT_UNIT = "cm"
VOICE_LINEAR_DEFAULT_SCALE_TO_MM = 10.0
VOICE_MOVEL_DIRECTION_SPECS = {
    "right": {
        "keywords": ("x 방향", "x방향", "x 축 방향", "x축 방향", "x축방향", "엑스 방향", "엑스방향", "엑스 축 방향", "엑스축 방향", "엑스축방향", "+x 방향", "+x방향", "양의 x 방향", "양의 x방향", "플러스 x 방향", "플러스 x방향"),
        "unit": "mm",
        "tpos": [1, 0, 0, 0, 0, 0],
        "label": "X 방향",
        "verb": "이동",
    },
    "left": {
        "keywords": ("x 반대 방향", "x반대방향", "x 축 반대 방향", "x축 반대 방향", "엑스 반대 방향", "엑스반대방향", "-x 방향", "-x방향", "음의 x 방향", "음의 x방향", "마이너스 x 방향", "마이너스 x방향"),
        "unit": "mm",
        "tpos": [-1, 0, 0, 0, 0, 0],
        "label": "X 반대 방향",
        "verb": "이동",
    },
    "up": {
        "keywords": ("y 방향", "y방향", "y 축 방향", "y축 방향", "y축방향", "와이 방향", "와이방향", "와이 축 방향", "와이축 방향", "와이축방향", "+y 방향", "+y방향", "양의 y 방향", "양의 y방향", "플러스 y 방향", "플러스 y방향"),
        "unit": "mm",
        "tpos": [0, 1, 0, 0, 0, 0],
        "label": "Y 방향",
        "verb": "이동",
    },
    "down": {
        "keywords": ("y 반대 방향", "y반대방향", "y 축 반대 방향", "y축 반대 방향", "와이 반대 방향", "와이반대방향", "-y 방향", "-y방향", "음의 y 방향", "음의 y방향", "마이너스 y 방향", "마이너스 y방향"),
        "unit": "mm",
        "tpos": [0, -1, 0, 0, 0, 0],
        "label": "Y 반대 방향",
        "verb": "이동",
    },
    "forward": {
        "keywords": ("앞쪽", "앞으로", "전방", "전진", "forward"),
        "unit": "mm",
        "tpos": [0, 0, 1, 0, 0, 0],
        "label": "앞쪽",
        "verb": "이동",
    },
    "backward": {
        "keywords": ("뒤쪽", "뒤로", "후방", "후진", "backward", "back"),
        "unit": "mm",
        "tpos": [0, 0, -1, 0, 0, 0],
        "label": "뒤쪽",
        "verb": "이동",
    },
    "zoom_in": {
        "keywords": ("줌인", "줌 인", "확대", "가까이", "zoom in", "zoomin"),
        "unit": "mm",
        "tpos": [0, 0, -1, 0, 0, 0],
        "label": "줌인",
        "verb": "이동",
    },
    "zoom_out": {
        "keywords": ("줌아웃", "줌 아웃", "축소", "멀리", "zoom out", "zoomout"),
        "unit": "mm",
        "tpos": [0, 0, 1, 0, 0, 0],
        "label": "줌아웃",
        "verb": "이동",
    },
    "counterclockwise": {
        "keywords": ("반시계방향", "반 시계 방향", "반시계", "ccw", "counterclockwise"),
        "unit": "deg",
        "tpos": [0, 0, 0, 0, 0, 1],
        "label": "반시계방향",
        "verb": "회전",
    },
    "clockwise": {
        "keywords": ("시계방향", "시계 방향", "시계", "cw", "clockwise"),
        "unit": "deg",
        "tpos": [0, 0, 0, 0, 0, -1],
        "label": "시계방향",
        "verb": "회전",
    },
}

KOREAN_DIGITS = {
    "영": 0,
    "공": 0,
    "일": 1,
    "이": 2,
    "삼": 3,
    "사": 4,
    "오": 5,
    "육": 6,
    "륙": 6,
    "칠": 7,
    "팔": 8,
    "구": 9,
}
KOREAN_NATIVE_NUMBERS = {
    "한": 1,
    "하나": 1,
    "두": 2,
    "둘": 2,
    "세": 3,
    "셋": 3,
    "네": 4,
    "넷": 4,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "여덟": 8,
    "아홉": 9,
    "열": 10,
}
KOREAN_UNITS = {"십": 10, "백": 100, "천": 1000, "만": 10000}
VOICE_LINEAR_UNIT_TO_MM = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "밀리미터": 1.0,
    "밀리": 1.0,
    "미리": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimeters": 10.0,
    "센티미터": 10.0,
    "센티": 10.0,
    "센치": 10.0,
    "m": 1000.0,
    "meter": 1000.0,
    "meters": 1000.0,
    "미터": 1000.0,
}
VOICE_ROTATION_UNIT_TO_DEG = {
    "deg": 1.0,
    "degree": 1.0,
    "degrees": 1.0,
    "도": 1.0,
}
VOICE_UNIT_PATTERN = (
    r"millimeters?|centimeters?|meters?|degrees?|밀리미터|센티미터|"
    r"밀리|미리|센티|센치|미터|mm|cm|deg|도|m|만큼"
)


def _utc_timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _set_voice_progress(stage: str, message: str, **extra: Any) -> None:
    timestamp = _utc_timestamp()
    event = {
        "at": timestamp,
        "stage": stage,
        "message": message,
    }
    event.update(extra)

    try:
        events = bb.get("voice/progress_events")
    except Exception:
        events = []
    if not isinstance(events, list):
        events = []

    bb.set("voice/progress_stage", stage)
    bb.set("voice/progress_message", message)
    bb.set("voice/progress_updated_at", timestamp)
    bb.set("voice/status_text", message)
    bb.set("voice/progress_events", [*events[-11:], event])


def _is_voice_cancel_requested() -> bool:
    return bool(bb.get("voice/cancel_requested"))


def _clear_voice_command_state() -> None:
    bb.set("voice/stt_text", "")
    bb.set("voice/action_json", {})
    bb.set("voice/llm_raw_response", "")
    bb.set("voice/request_control", False)


def _reset_voice_progress(message: str = "음성 녹음 중...") -> None:
    bb.set("voice/progress_events", [])
    _clear_voice_command_state()
    bb.set("voice/last_error", "")
    bb.set("voice/cancel_requested", False)
    bb.set("voice/recording/stop", False)
    _set_voice_progress("recording", message)


def _gemini_url_with_key(url: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}key={GEMINI_API_KEY}"


def _extract_gemini_text(data: Dict[str, Any]) -> Optional[str]:
    try:
        parts = data["candidates"][0]["content"].get("parts", [])
    except (IndexError, KeyError, TypeError):
        return None

    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if text:
            return str(text)
    return None


def _strip_generated_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, str):
            stripped = parsed
    except json.JSONDecodeError:
        pass

    return stripped.strip() or None


def _guess_audio_mime_type(file_path: str) -> str:
    return AUDIO_MIME_TYPES.get(os.path.splitext(file_path)[1].lower(), "audio/wav")


def transcribe_audio(file_path: str) -> Optional[str]:
    """Transcribe recorded audio with Gemini."""

    Logger.info(f"{get_time()}: [VoiceManager] STT provider: {VOICE_PROVIDER}")
    _set_voice_progress("stt_requesting", f"STT 요청 중... ({VOICE_PROVIDER})")
    return _transcribe_gemini_audio(file_path)


def _transcribe_gemini_audio(file_path: str) -> Optional[str]:
    """Send recorded audio to Gemini and return only the transcript text."""

    if not GEMINI_API_KEY:
        Logger.error("Gemini API key is not configured for voice STT.")
        return None

    if not os.path.exists(file_path):
        Logger.error(f"Audio file does not exist: {file_path}")
        return None

    try:
        with open(file_path, "rb") as audio_file:
            audio_data = base64.b64encode(audio_file.read()).decode("ascii")
    except OSError as exc:
        Logger.error(f"Failed to read audio file for Gemini STT: {exc}")
        return None

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "이 오디오의 한국어 음성을 그대로 전사해 주세요. "
                            "출력은 전사 텍스트만 반환하고 설명, JSON, 마크다운, 따옴표는 넣지 마세요. "
                            "음성이 없으면 빈 문자열만 반환하세요."
                        ),
                    },
                    {
                        "inline_data": {
                            "mime_type": _guess_audio_mime_type(file_path),
                            "data": audio_data,
                        },
                    },
                ],
            },
        ],
        "generationConfig": {
            "temperature": 0,
        },
    }
    try:
        response = requests.post(
            _gemini_url_with_key(GEMINI_TRANSCRIPTION_URL),
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=STT_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        Logger.error(f"Gemini STT request failed: {exc}")
        return None
    if response.status_code != 200:
        Logger.error(f"Gemini STT failed: {response.status_code} {response.text}")
        return None

    stt_text = _strip_generated_text(_extract_gemini_text(response.json()))
    if stt_text:
        Logger.info(f"{get_time()}: [VoiceManager] STT result: {stt_text}")
    else:
        Logger.debug(f"{get_time()}: [VoiceManager] Gemini STT returned empty text")
    return stt_text


def _extract_json_object(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from an LLM response."""

    if not text:
        return None

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _format_amount(amount: float) -> str:
    return f"{amount:g}"


def _coerce_amount(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    if not isinstance(value, str):
        return None

    normalized = value.strip().replace(",", ".")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", normalized)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return None

    return _parse_korean_number_token(normalized)


def _normalize_unit_text(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def _unit_scale_to_base(unit: Any, default_unit: str) -> Optional[float]:
    normalized = _normalize_unit_text(unit)
    if not normalized or normalized == "만큼":
        if default_unit == "mm":
            return VOICE_LINEAR_DEFAULT_SCALE_TO_MM
        return 1.0

    if default_unit == "mm":
        return VOICE_LINEAR_UNIT_TO_MM.get(normalized)
    if default_unit == "deg":
        return VOICE_ROTATION_UNIT_TO_DEG.get(normalized)
    return 1.0


def _apply_unit_scale(amount: float, unit: Any, default_unit: str) -> float:
    scale = _unit_scale_to_base(unit, default_unit)
    return amount if scale is None else amount * scale


def _number_with_unit_from_text(text: str) -> Tuple[Optional[float], Optional[str]]:
    match = re.search(
        rf"([-+]?\d+(?:[.,]\d+)?)\s*({VOICE_UNIT_PATTERN})?",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, None

    try:
        amount = float(match.group(1).replace(",", "."))
    except ValueError:
        return None, None
    return amount, match.group(2)


def _coerce_amount_with_unit(
    value: Any,
    default_unit: str,
    explicit_unit: Optional[str] = None,
) -> Optional[float]:
    if isinstance(value, str):
        amount, text_unit = _number_with_unit_from_text(value)
        if amount is not None:
            return _apply_unit_scale(amount, text_unit or explicit_unit, default_unit)

        korean_amount = _parse_korean_number_token(value)
        if korean_amount is not None:
            return _apply_unit_scale(korean_amount, explicit_unit, default_unit)

    amount = _coerce_amount(value)
    if amount is None:
        return None
    return _apply_unit_scale(amount, explicit_unit, default_unit)


def _parse_korean_number_token(token: str) -> Optional[float]:
    token = re.sub(r"\s+", "", token.strip())
    if not token:
        return None

    if token in KOREAN_NATIVE_NUMBERS:
        return float(KOREAN_NATIVE_NUMBERS[token])

    total = 0
    current: Optional[int] = None
    matched = False
    for char in token:
        if char in KOREAN_DIGITS:
            current = KOREAN_DIGITS[char]
            matched = True
        elif char in KOREAN_UNITS:
            unit = KOREAN_UNITS[char]
            total += (1 if current is None else current) * unit
            current = None
            matched = True
        else:
            return None

    if not matched:
        return None
    if current is not None:
        total += current
    return float(total)


def _extract_amount_from_text(text: str, default_unit: str = "mm") -> Optional[float]:
    numeric_amount, numeric_unit = _number_with_unit_from_text(text)
    if numeric_amount is not None:
        return _apply_unit_scale(numeric_amount, numeric_unit, default_unit)

    korean_number_pattern = (
        r"(한|하나|두|둘|세|셋|네|넷|다섯|여섯|일곱|여덟|아홉|열|"
        r"[영공일이삼사오육륙칠팔구십백천만]+)"
    )
    unit_pattern = rf"({VOICE_UNIT_PATTERN})?"
    token_pattern = rf"(?<![가-힣]){korean_number_pattern}\s*{unit_pattern}(?![가-힣])"
    for match in re.finditer(token_pattern, text, re.IGNORECASE):
        amount = _parse_korean_number_token(match.group(1))
        if amount is not None:
            return _apply_unit_scale(amount, match.group(2), default_unit)

    return None


def _normalize_direction_text(value: Any) -> Tuple[str, str]:
    normalized = str(value).strip().lower().replace("_", " ").replace("-", " ")
    compact = re.sub(r"\s+", "", normalized)
    return normalized, compact


def _canonical_movel_direction(value: Any) -> Optional[str]:
    if value is None:
        return None

    normalized, compact = _normalize_direction_text(value)
    for direction, spec in VOICE_MOVEL_DIRECTION_SPECS.items():
        aliases = (direction, *spec["keywords"])
        for alias in aliases:
            alias_normalized, alias_compact = _normalize_direction_text(alias)
            if normalized == alias_normalized or compact == alias_compact:
                return direction
    return None


def _direction_from_text(text: str) -> Optional[str]:
    _, compact_text = _normalize_direction_text(text)
    for direction, spec in VOICE_MOVEL_DIRECTION_SPECS.items():
        for keyword in spec["keywords"]:
            _, keyword_compact = _normalize_direction_text(keyword)
            if keyword_compact and keyword_compact in compact_text:
                return direction
    return None


def _has_explicit_xy_axis(text: str, direction: str) -> bool:
    _, compact_text = _normalize_direction_text(text)
    if direction in {"right", "left"}:
        axis_keywords = (
            "x방향",
            "x축방향",
            "엑스방향",
            "엑스축방향",
            "+x방향",
            "-x방향",
            "양의x방향",
            "음의x방향",
            "플러스x방향",
            "마이너스x방향",
            "x반대방향",
            "엑스반대방향",
        )
        return any(keyword in compact_text for keyword in axis_keywords)
    if direction in {"up", "down"}:
        axis_keywords = (
            "y방향",
            "y축방향",
            "와이방향",
            "와이축방향",
            "+y방향",
            "-y방향",
            "양의y방향",
            "음의y방향",
            "플러스y방향",
            "마이너스y방향",
            "y반대방향",
            "와이반대방향",
        )
        return any(keyword in compact_text for keyword in axis_keywords)
    return True


def _build_movel_tpos(direction: str, amount: float) -> List[float]:
    factors = VOICE_MOVEL_DIRECTION_SPECS[direction]["tpos"]
    return [float(factor) * amount for factor in factors]


def _make_movel_command(direction: str, amount: float, aux1: Optional[str] = None) -> Dict[str, Any]:
    amount = abs(float(amount))
    spec = VOICE_MOVEL_DIRECTION_SPECS[direction]
    amount_text = _format_amount(amount)
    unit_text = "도" if spec["unit"] == "deg" else "mm"
    if direction in {"zoom_in", "zoom_out"}:
        default_reply = f"{amount_text}{unit_text} {spec['label']}할게요."
    else:
        default_reply = f"{spec['label']}으로 {amount_text}{unit_text} {spec['verb']}할게요."
    reply = aux1 or default_reply

    return {
        "action": "movel",
        "aux0": direction,
        "aux1": reply,
        "value": amount,
        "unit": spec["unit"],
        "tpos": _build_movel_tpos(direction, amount),
    }


def _extract_movel_amount(command: Dict[str, Any], default_unit: str) -> Optional[float]:
    amount_keys_with_units = (
        ("distance_mm", "mm"),
        ("distance_cm", "cm"),
        ("distance_m", "m"),
        ("angle_deg", "deg"),
    )
    for key, unit in amount_keys_with_units:
        amount = _coerce_amount_with_unit(command.get(key), default_unit, unit)
        if amount is not None:
            return amount

    explicit_unit = command.get("unit")
    amount_keys = ("value", "amount", "distance", "angle", "aux2", "aux3")
    for key in amount_keys:
        amount = _coerce_amount_with_unit(command.get(key), default_unit, explicit_unit)
        if amount is not None:
            return amount
    return None


def _normalize_movel_command(command: Dict[str, Any]) -> Dict[str, Any]:
    direction = _canonical_movel_direction(
        command.get("aux0")
        or command.get("direction")
        or command.get("target")
        or command.get("motion")
    )
    default_unit = VOICE_MOVEL_DIRECTION_SPECS[direction]["unit"] if direction else "mm"
    amount = _extract_movel_amount(command, default_unit)

    if direction is None or amount is None or amount == 0:
        return {
            "action": None,
            "aux0": None,
            "aux1": "이동 또는 회전할 방향과 숫자를 함께 말해 주세요.",
        }

    return _make_movel_command(direction, amount, command.get("aux1") or command.get("description"))


def _movel_command_from_text(stt_text: str) -> Optional[Dict[str, Any]]:
    direction = _direction_from_text(stt_text)
    if direction is None:
        return None

    amount = _extract_amount_from_text(
        stt_text,
        default_unit=VOICE_MOVEL_DIRECTION_SPECS[direction]["unit"],
    )
    if amount is None or amount == 0:
        return {
            "action": None,
            "aux0": None,
            "aux1": "이동 또는 회전할 값을 숫자로 말해 주세요.",
        }

    return _make_movel_command(direction, amount)


def _normalize_voice_command(command: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the LLM output compatible with the existing voice FSM contract."""

    action = command.get("action")
    aux0 = command.get("aux0")
    aux1 = command.get("aux1") or command.get("description") or ""

    normalized_action = str(action).strip().lower() if action is not None else None
    normalized_aux0 = str(aux0).strip().lower() if aux0 is not None else None

    if normalized_action == "mode":
        pass
    elif normalized_action in VOICE_MOVEL_ACTIONS:
        return _normalize_movel_command(command)
    elif normalized_action in {"stop", "fix"}:
        normalized_action = "mode"
        normalized_aux0 = "fix"
    elif normalized_action in {"free", "point", "line", "plane", "rcm"}:
        normalized_aux0 = normalized_action
        normalized_action = "mode"
    else:
        normalized_action = None
        normalized_aux0 = None

    if normalized_aux0 not in VOICE_MODE_AUX:
        normalized_action = None
        normalized_aux0 = None

    if not aux1:
        aux1 = "모드 또는 이동 명령을 인식하지 못했어요. 모드 변경이나 숫자가 포함된 이동 명령으로 말해 주세요."

    return {
        "action": normalized_action,
        "aux0": normalized_aux0,
        "aux1": str(aux1),
    }


def _command_from_keywords(stt_text: str) -> Optional[Dict[str, Any]]:
    """Deterministic guardrail for supported voice modes and small motion commands."""

    text = stt_text.strip().lower()
    if not text:
        return None

    movel_command = _movel_command_from_text(text)
    if movel_command is not None:
        return movel_command

    mode_keywords = [
        (
            "point",
            ["점고정", "점 고정", "포인트", "포인트고정", "포인트 고정", "점으로 고정"],
            "점 고정 모드로 전환할게요.",
        ),
        (
            "line",
            ["선고정", "선 고정", "라인", "라인고정", "라인 고정", "선으로 고정"],
            "선 고정 모드로 전환할게요.",
        ),
        (
            "plane",
            ["면고정", "면 고정", "평면고정", "평면 고정", "플레인", "rcm", "알씨엠"],
            "면 고정 모드로 전환할게요.",
        ),
        (
            "fix",
            ["정지모드", "정지 모드", "정지", "멈춰", "스톱", "고정", "락", "잠가", "픽스"],
            "고정 모드로 전환할게요.",
        ),
        (
            "free",
            ["이동모드", "이동 모드", "이동", "움직여", "자유", "프리", "풀어", "해제"],
            "자유 이동 모드로 전환할게요.",
        ),
    ]
    for aux0, keywords, reply in mode_keywords:
        if any(keyword in text for keyword in keywords):
            return {"action": "mode", "aux0": aux0, "aux1": reply}

    return None


def _fetch_gemini_llm_response(stt_text: str) -> Optional[str]:
    """Send STT text to Gemini and return raw text."""

    if not GEMINI_API_KEY:
        Logger.error("Gemini API key is not configured for voice LLM.")
        return None

    prompt = PROMPT_TEMPLATE.replace("{stt_text}", stt_text)
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                ],
            },
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }
    try:
        response = requests.post(
            _gemini_url_with_key(GEMINI_LLM_URL),
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=LLM_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        Logger.error(f"Gemini LLM request failed: {exc}")
        return None
    if response.status_code != 200:
        Logger.error(f"Gemini LLM failed: {response.status_code} {response.text}")
        return None

    data = response.json()
    text = _strip_generated_text(_extract_gemini_text(data))
    if text:
        return text

    Logger.debug(f"{get_time()}: [VoiceManager] Gemini response had no text: {data}")
    return None


def fetch_voice_command(stt_text: str) -> Optional[Dict[str, Any]]:
    """Run Gemini and return a normalized voice command."""

    Logger.info(f"{get_time()}: [VoiceManager] LLM provider: {VOICE_PROVIDER}")
    keyword_command = _command_from_keywords(stt_text)
    if keyword_command is not None:
        Logger.info(f"{get_time()}: [VoiceManager] Keyword command: {keyword_command}")
        bb.set("voice/llm_raw_response", "")
        _set_voice_progress("keyword_parsed", "키워드 규칙으로 명령을 해석했어요.", command=keyword_command)
        return keyword_command

    _set_voice_progress("llm_requesting", f"LLM 요청 중... ({VOICE_PROVIDER})")
    raw_text = _fetch_gemini_llm_response(stt_text)
    bb.set("voice/llm_raw_response", raw_text or "")

    Logger.debug(f"{get_time()}: [VoiceManager] LLM raw response: {raw_text}")
    _set_voice_progress("llm_response", "LLM 응답을 받았어요.", raw_response=raw_text or "")
    command = _extract_json_object(raw_text)
    if command is None:
        Logger.debug(f"{get_time()}: [VoiceManager] LLM response was not JSON")
        keyword_command = _command_from_keywords(stt_text)
        if keyword_command is not None:
            Logger.info(f"{get_time()}: [VoiceManager] Keyword command fallback: {keyword_command}")
            _set_voice_progress("keyword_parsed", "LLM 응답 대신 키워드 규칙으로 해석했어요.", command=keyword_command)
        return keyword_command

    normalized = _normalize_voice_command(command)
    if (
        normalized.get("action") == "movel"
        and normalized.get("aux0") in {"right", "left", "up", "down"}
        and not _has_explicit_xy_axis(stt_text, normalized["aux0"])
    ):
        _set_voice_progress("parse_rejected", "X/Y 이동은 축 방향이 명확하지 않아 거부했어요.")
        return {
            "action": None,
            "aux0": None,
            "aux1": "x 또는 y 이동은 축 방향을 명확히 말해 주세요. 예를 들어 x 방향 또는 y 반대 방향처럼 말해 주세요.",
        }

    if normalized.get("action") is None:
        keyword_command = _command_from_keywords(stt_text)
        if keyword_command is not None:
            Logger.info(f"{get_time()}: [VoiceManager] Keyword command fallback: {keyword_command}")
            _set_voice_progress("keyword_parsed", "정규화 실패 후 키워드 규칙으로 해석했어요.", command=keyword_command)
            return keyword_command

    _set_voice_progress("command_parsed", "명령 해석이 완료됐어요.", command=normalized)
    return normalized


class VoiceManager:
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.user_voice_str = "user_voice.wav"

        self.user_text = "" # STT 결과물
        self.parsed_user_command = "" # LLM 결과물
        self.command_output = {}

        self.recording_thread: Optional[threading.Thread] = None
        self.recording_stop_event = threading.Event()
        self.recording_active = False
        self.session_lock = threading.Lock()
        self.voice_session_id = 0

        self.speaking_thread: Optional[threading.Thread] = None
        self.speaking_active = False
        # list_audio_devices()
    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()

    def run(self):
        while self.running:
            try:
                self.handle_recording()
                self.handle_speak()
                time.sleep(0.01)

            except Exception:
                Logger.error(f"[SystemManager] Exception occurred:\n{traceback.format_exc()}")
                self.stop()
    def handle_speak(self):
        if bb.get("voice/speak_flag"):
            bb.set("voice/speak_flag",False)
            if not self.speaking_active:
                self.speaking_thread = threading.Thread(
                    target=self.speak,
                    daemon=True,
                )
                self.speaking_thread.start()

    def speak(self) -> None:
        """Convert text to speech and play it back."""
        self.speaking_active = True
        try:
            tts_text = bb.get("voice/speak_contents")
            if not tts_text:
                return

            tts = gTTS(text=tts_text, lang="ko")
            tts.save(TTS_PATH)

            pygame.mixer.init()
            pygame.mixer.music.load(TTS_PATH)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except Exception:
            Logger.error(f"{get_time()}: [VoiceManager] TTS failed:\n{traceback.format_exc()}")
        finally:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            self.speaking_active = False

    def handle_recording(self) -> None:
        """Start/stop microphone recording based on blackboard flags."""
        
        if bb.get("voice/recording/start"):
            bb.set("voice/recording/start", False)
            if not self.recording_active:
                _reset_voice_progress()
                session_id = self._next_voice_session()
                stop_event = threading.Event()
                self.recording_stop_event = stop_event
                self.recording_thread = threading.Thread(
                    target=self._record_until_stop,
                    args=(session_id, stop_event),
                    daemon=True,
                )
                self.recording_thread.start()
                Logger.info(f"{get_time()}: [VoiceManager] Recording started")
                

        cancel_requested = _is_voice_cancel_requested()
        if cancel_requested and self.recording_active:
            bb.set("voice/recording/stop", False)
            self.recording_stop_event.set()

        if not cancel_requested and bb.get("voice/recording/stop"):
            bb.set("voice/recording/stop", False)
            if self.recording_active:
                _set_voice_progress("recording_stopping", "녹음을 종료하고 음성을 처리할 준비 중...")
                self.recording_stop_event.set()
                Logger.info(f"{get_time()}: [VoiceManager] Stop signal received")

    def _record_until_stop(self, session_id: int, stop_event: threading.Event) -> None:
        """Capture microphone audio until a stop signal is received."""

        self.recording_active = True
        frames = []

        try:
            stream_options: Dict[str, Any] = {
                "samplerate": SAMPLE_RATE,
                "channels": 1,
                "dtype": "int16",
            }
            input_device = self._get_input_device()
            if input_device is not None:
                stream_options["device"] = input_device
            with sd.InputStream(**stream_options) as stream:
                while not stop_event.is_set():
                    data, _ = stream.read(CHUNK_SIZE)
                    frames.append(data.copy())
        except Exception:
            Logger.error(f"{get_time()}: [VoiceManager] Recording failed:\n{traceback.format_exc()}")
            bb.set("voice/last_error", "Recording failed")
            bb.set("voice/last_result_at", _utc_timestamp())
            _set_voice_progress("error", "녹음에 실패했어요.", error="Recording failed")
            frames = []

        self.recording_active = False

        try:
            audio = self._combine_frames(frames)
            if audio is not None:
                self._process_audio(audio, session_id)
            elif _is_voice_cancel_requested():
                self._finish_if_cancelled(session_id)
        finally:
            stop_event.clear()

    def _get_input_device(self) -> Optional[int]:
        """Return the selected sounddevice input device index, or None for default."""
        try:
            input_device = bb.get("voice/input_device")
        except Exception:
            return None
        if input_device in (None, "", "default"):
            return None
        try:
            return int(input_device)
        except (TypeError, ValueError):
            Logger.error(f"{get_time()}: [VoiceManager] Invalid input device: {input_device}")
            return None

    def _combine_frames(self, frames: List[np.ndarray]) -> Optional[np.ndarray]:
        """Combine recorded frames into a single numpy array."""

        if not frames:
            Logger.debug(f"{get_time()}: [VoiceManager] No audio frames captured")
            return None

        return np.concatenate(frames, axis=0)

    def _process_audio(self, audio: np.ndarray, session_id: int) -> None:
        """Save recorded audio, run STT and selected LLM, and publish the command."""
        if self._finish_if_cancelled(session_id):
            return

        bb.set("voice/last_error", "")
        _set_voice_progress("saving_audio", "녹음 파일을 저장하는 중...")
        try:
            audio_path = self._save_audio(audio)
        except Exception:
            Logger.error(f"{get_time()}: [VoiceManager] Failed to save audio:\n{traceback.format_exc()}")
            bb.set("voice/last_error", "Failed to save audio")
            bb.set("voice/last_result_at", _utc_timestamp())
            _set_voice_progress("error", "녹음 파일 저장에 실패했어요.", error="Failed to save audio")
            return
        bb.set("voice/last_audio_path", audio_path)
        _set_voice_progress("audio_saved", "녹음 파일을 저장했어요.", audio_path=audio_path)
        if self._finish_if_cancelled(session_id):
            return

        user_text = transcribe_audio(audio_path) or ""
        if self._finish_if_cancelled(session_id):
            return

        self.user_text = user_text
        bb.set("voice/stt_text", self.user_text)
        if self.user_text:
            _set_voice_progress("stt_done", "STT 결과를 받았어요.", stt_text=self.user_text)
        if self._finish_if_cancelled(session_id):
            return

        if not self.user_text:
            Logger.debug(f"{get_time()}: [VoiceManager] STT returned no text")
            self.command_output = {}
            self.parsed_user_command = ""
            bb.set("voice/action_json", self.command_output)
            bb.set("voice/request_control", False)
            bb.set("voice/last_error", "STT returned no text")
            bb.set("voice/last_result_at", _utc_timestamp())
            _set_voice_progress("error", "STT 결과가 비어 있어요.", error="STT returned no text")
            return

        try:
            command = fetch_voice_command(self.user_text)
        except Exception:
            Logger.error(f"{get_time()}: [VoiceManager] Voice LLM failed:\n{traceback.format_exc()}")
            _set_voice_progress("error", "음성 명령 해석 중 오류가 발생했어요.", error="Voice LLM failed")
            command = None
        if self._finish_if_cancelled(session_id):
            return

        if command is None:
            self.command_output = {}
            self.parsed_user_command = ""
            bb.set("voice/action_json", self.command_output)
            bb.set("voice/request_control", False)
            bb.set("voice/last_error", "LLM returned no command")
            bb.set("voice/last_result_at", _utc_timestamp())
            _set_voice_progress("error", "명령을 만들지 못했어요.", error="LLM returned no command")
            return

        self.command_output = command
        self.parsed_user_command = json.dumps(command, ensure_ascii=False)
        Logger.info(f"{get_time()}: [VoiceManager] LLM command: {self.parsed_user_command}")
        if self._finish_if_cancelled(session_id):
            return

        bb.set("voice/action_json", self.command_output)
        bb.set("voice/request_control", command.get("action") in VOICE_CONTROL_ACTIONS)
        bb.set("voice/last_result_at", _utc_timestamp())
        bb.set("voice/last_error", "")
        _set_voice_progress("done", "음성 명령 처리가 완료됐어요.", command=self.command_output)

        if command.get("action") != "mode" and command.get("aux1"):
            bb.set("voice/speak_contents", command["aux1"])
            bb.set("voice/speak_flag", True)

    def _next_voice_session(self) -> int:
        with self.session_lock:
            self.voice_session_id += 1
            return self.voice_session_id

    def _is_current_voice_session(self, session_id: int) -> bool:
        with self.session_lock:
            return session_id == self.voice_session_id

    def _finish_if_cancelled(self, session_id: int) -> bool:
        if not self._is_current_voice_session(session_id):
            Logger.info(f"{get_time()}: [VoiceManager] Discard stale voice session {session_id}")
            return True

        if not _is_voice_cancel_requested():
            return False

        self.user_text = ""
        self.parsed_user_command = ""
        self.command_output = {}
        _clear_voice_command_state()
        bb.set("voice/last_error", "")
        bb.set("voice/last_result_at", _utc_timestamp())
        bb.set("voice/cancel_requested", False)
        _set_voice_progress("cancelled", "음성교시가 정지되었습니다.")
        Logger.info(f"{get_time()}: [VoiceManager] Voice processing cancelled")
        return True

    def _save_audio(self, audio: np.ndarray) -> str:
        """Save numpy audio data to a WAV file and return the path."""

        with wave.open(self.user_voice_str, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())

        duration = len(audio) / SAMPLE_RATE
        Logger.info(
            f"{get_time()}: [VoiceManager] Audio saved to {self.user_voice_str} ({duration:.2f}s)",
        )
        return self.user_voice_str


from __future__ import annotations

import json
import os
from typing import Any

from core_ai.env import load_local_env
from utils.logger import get_logger


logger = get_logger("ai_coach")


COACHING_MODEL = "gpt-4o-mini"


def generate_focus_coaching(session_record: dict[str, Any], model: str = COACHING_MODEL) -> str:
    """Return a 3-sentence encouraging review for a completed session."""
    load_local_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _offline_feedback(session_record, "Chưa cấu hình OPENAI_API_KEY.")

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            instructions=(
                "Bạn là một productivity coach tích cực, thực tế và nói tiếng Việt. "
                "Hãy trả lời đúng 3 câu ngắn, có hành động cụ thể cho phiên học tiếp theo."
            ),
            input=(
                "Hãy đánh giá phiên FocusFlow AI sau và đưa coaching. "
                "Dữ liệu JSON:\n"
                f"{json.dumps(session_record, ensure_ascii=False, indent=2)}"
            ),
        )
        text = str(getattr(response, "output_text", "") or "").strip()
        if text:
            return text
        return _offline_feedback(session_record, "OpenAI không trả về nội dung text.")
    except Exception as exc:
        logger.warning("OpenAI coaching failed: %s", exc.__class__.__name__)
        return _offline_feedback(session_record, "Không gọi được OpenAI, đã dùng coaching offline.")


def _offline_feedback(session_record: dict[str, Any], reason: str) -> str:
    avg_focus = float(session_record.get("average_focus", 0.0)) * 100
    distractions = int(session_record.get("distraction_count", 0))
    if avg_focus >= 75:
        tone = "Bạn giữ nhịp tập trung rất tốt trong phiên này."
    elif avg_focus >= 50:
        tone = "Bạn đã có một phiên ổn, nhưng vẫn còn vài đoạn bị kéo khỏi luồng làm việc."
    else:
        tone = "Phiên này hơi nhiễu, nhưng dữ liệu đã cho thấy điểm cần cải thiện rõ ràng."
    return (
        f"{tone} Điểm tập trung trung bình là {avg_focus:.1f}% với {distractions} lần xao nhãng. "
        f"Ở phiên tiếp theo, hãy tắt trước một nguồn gây nhiễu chính và đặt mục tiêu tập trung thêm 5 phút liên tục. "
        f"Ghi chú hệ thống: {reason}"
    )

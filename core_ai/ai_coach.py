from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from utils.paths import history_path


def _load_key_from_env_file(env_file: Path) -> str | None:
    if not env_file.exists():
        return None

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "OPENAI_API_KEY":
            return value.strip().strip('"').strip("'")
    return None


class AICoach:
    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None) -> None:
        self.model = model
        env_file = Path(__file__).resolve().parents[1] / ".env"
        resolved_key = api_key or os.getenv("OPENAI_API_KEY") or _load_key_from_env_file(env_file)
        self._client = OpenAI(api_key=resolved_key) if resolved_key else None

    def generate_feedback(self, minute_focus_scores: list[float]) -> str:
        if not minute_focus_scores:
            return (
                "Ban chua co du lieu focus de danh gia. "
                "Hay bat dau mot phien ngan 5-10 phut de AI huong dan cu the hon."
            )

        average_focus = float(sum(minute_focus_scores) / len(minute_focus_scores))
        focus_payload = {
            "minute_focus_scores": [round(float(score), 4) for score in minute_focus_scores],
            "average_focus": round(average_focus, 4),
            "minutes": len(minute_focus_scores),
            "highest": round(float(max(minute_focus_scores)), 4),
            "lowest": round(float(min(minute_focus_scores)), 4),
        }

        if self._client is None:
            return (
                "AI Coach chua duoc kich hoat vi thieu OPENAI_API_KEY trong file .env. "
                "Hien ban da co so lieu focus, hay them API key de nhan nhan xet 3 cau hanh dong."
            )

        instructions = (
            "You are an encouraging productivity coach. "
            "Give exactly 3 concise, actionable sentences. "
            "Use a supportive tone, mention one strength, one weakness pattern, "
            "and one practical next-session action."
        )

        user_input = (
            "Session focus summary JSON:\n"
            f"{json.dumps(focus_payload, ensure_ascii=False)}\n\n"
            "Return only the 3-sentence coaching feedback."
        )

        try:
            response = self._client.responses.create(
                model=self.model,
                instructions=instructions,
                input=user_input,
                temperature=0.6,
                max_output_tokens=220,
            )
            content = (response.output_text or "").strip()
            if content:
                return content
        except Exception as exc:
            return (
                "Khong the tao phan hoi AI do loi ket noi API. "
                f"Chi tiet: {exc}. "
                "Ban van co the xem bieu do va thu lai o phien tiep theo."
            )

        return (
            "AI khong tra ve noi dung hop le. "
            "Hay giu nhiet nhip 25 phut, nghi 5 phut, va thu lai voi anh sang tot hon de tang do chinh xac."
        )

    def save_session(
        self,
        minute_focus_scores: list[float],
        average_focus: float,
        ai_feedback: str,
    ) -> dict[str, Any]:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "minute_focus_scores": [round(float(score), 4) for score in minute_focus_scores],
            "average_focus": round(float(average_focus), 4),
            "ai_feedback": ai_feedback,
        }

        target = history_path()
        if target.exists():
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except json.JSONDecodeError:
                existing = []
        else:
            existing = []

        existing.append(record)
        target.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

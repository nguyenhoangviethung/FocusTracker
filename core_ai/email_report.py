from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
from typing import Any

from core_ai.env import load_local_env
from utils.logger import get_logger


logger = get_logger("email_report")


def send_report_email(mentor_email: str, summary_data: dict[str, Any]) -> dict[str, Any]:
    """Send a mentor report email and return a serializable status object."""
    load_local_env()
    recipient = mentor_email.strip()
    if not recipient:
        return {"sent": False, "status": "skipped", "message": "Chưa cấu hình mentor email."}

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = _to_int(os.getenv("SMTP_PORT"), 587)
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("SMTP_FROM", smtp_user).strip()
    use_tls = os.getenv("SMTP_TLS", "true").strip().lower() not in {"0", "false", "no"}

    if not smtp_host or not sender:
        return {
            "sent": False,
            "status": "skipped",
            "message": "Thiếu SMTP_HOST hoặc SMTP_FROM/SMTP_USER trong .env.",
        }

    message = MIMEMultipart("alternative")
    message["Subject"] = "FocusFlow AI - Báo cáo phiên tập trung"
    message["From"] = sender
    message["To"] = recipient
    message.attach(MIMEText(_render_plain_text(summary_data), "plain", "utf-8"))
    message.attach(MIMEText(_render_html(summary_data), "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(sender, [recipient], message.as_string())
        return {"sent": True, "status": "sent", "message": f"Đã gửi báo cáo tới {recipient}."}
    except Exception as exc:
        logger.warning("Mentor email failed", exc_info=True)
        return {"sent": False, "status": "failed", "message": str(exc)}


def _render_plain_text(data: dict[str, Any]) -> str:
    return (
        "FocusFlow AI - Báo cáo phiên tập trung\n"
        f"Điểm tập trung: {float(data.get('average_focus', 0.0)) * 100:.1f}%\n"
        f"Thời lượng: {int(data.get('duration_seconds', 0)) // 60} phút\n"
        f"Số lần xao nhãng: {int(data.get('distraction_count', 0))}\n\n"
        f"AI Coach:\n{data.get('ai_feedback', 'Chưa có feedback.')}\n"
    )


def _render_html(data: dict[str, Any]) -> str:
    focus = float(data.get("average_focus", 0.0)) * 100
    color = "#10B981" if focus >= 60 else "#EF4444"
    feedback = str(data.get("ai_feedback") or "Chưa có feedback.").replace("\n", "<br>")
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #1F2937;">
        <h2>FocusFlow AI - Báo cáo phiên tập trung</h2>
        <p>
          <strong>Điểm tập trung:</strong>
          <span style="color: {color}; font-weight: 700;">{focus:.1f}%</span>
        </p>
        <p><strong>Thời lượng:</strong> {int(data.get("duration_seconds", 0)) // 60} phút</p>
        <p><strong>Thời gian tập trung:</strong> {int(data.get("focused_seconds", 0)) // 60} phút</p>
        <p><strong>Số lần xao nhãng:</strong> {int(data.get("distraction_count", 0))}</p>
        <hr>
        <p><strong>AI Coach:</strong><br>{feedback}</p>
      </body>
    </html>
    """


def _to_int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default

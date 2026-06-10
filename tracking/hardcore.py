from __future__ import annotations

from dataclasses import dataclass
import os
import platform
from typing import Any

from utils.logger import get_logger


logger = get_logger("hardcore")

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    psutil = None


@dataclass(slots=True)
class HardcoreAction:
    status: str
    message: str
    remaining_seconds: int = 0
    process_name: str = ""
    window_title: str = ""
    pid: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "hardcore",
            "status": self.status,
            "message": self.message,
            "remaining_seconds": self.remaining_seconds,
            "process_name": self.process_name,
            "window_title": self.window_title,
            "pid": self.pid,
        }


class HardcoreDisciplineController:
    """Terminates the active distracting app after a continuous countdown."""

    def __init__(self, countdown_seconds: int = 30) -> None:
        self.countdown_seconds = max(5, int(countdown_seconds))
        self._self_pid = os.getpid()
        self._tracked_pid: int | None = None
        self._started_at: float | None = None
        self._last_warning_second: int | None = None
        self._last_terminated_pid: int | None = None

    def evaluate(
        self,
        snapshot: dict[str, Any],
        distracting_keywords: tuple[str, ...],
        now: float,
    ) -> HardcoreAction | None:
        pid = _to_int(snapshot.get("pid"))
        process_name = str(snapshot.get("process_name") or "unknown")
        window_title = str(snapshot.get("window_title") or "")
        text = f"{process_name} {window_title}".lower()
        is_distracting = any(keyword.lower() in text for keyword in distracting_keywords)

        if not is_distracting:
            self.reset()
            return None

        if pid is None:
            self.reset()
            return HardcoreAction(
                status="blocked",
                message="Hardcore phát hiện app gây xao nhãng nhưng OS không cung cấp PID.",
                process_name=process_name,
                window_title=window_title,
            )

        if pid == self._self_pid:
            self.reset()
            return None

        if self._tracked_pid != pid:
            self._tracked_pid = pid
            self._started_at = now
            self._last_warning_second = None

        elapsed = int(now - (self._started_at or now))
        remaining = max(0, self.countdown_seconds - elapsed)

        if remaining > 0:
            if self._last_warning_second == remaining:
                return None
            self._last_warning_second = remaining
            return HardcoreAction(
                status="countdown",
                message=f"Hardcore: đóng {process_name} trong {remaining}s nếu vẫn xao nhãng.",
                remaining_seconds=remaining,
                process_name=process_name,
                window_title=window_title,
                pid=pid,
            )

        if self._last_terminated_pid == pid:
            return None
        self._last_terminated_pid = pid
        return self._terminate(pid=pid, process_name=process_name, window_title=window_title)

    def reset(self) -> None:
        self._tracked_pid = None
        self._started_at = None
        self._last_warning_second = None

    def _terminate(self, pid: int, process_name: str, window_title: str) -> HardcoreAction:
        if psutil is None:
            return HardcoreAction(
                status="blocked",
                message="Hardcore cần psutil để terminate process.",
                process_name=process_name,
                window_title=window_title,
                pid=pid,
            )

        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            logger.warning("Hardcore terminated distracting process: pid=%s name=%s", pid, process_name)
            return HardcoreAction(
                status="terminated",
                message=f"Hardcore đã đóng {process_name}.",
                process_name=process_name,
                window_title=window_title,
                pid=pid,
            )
        except psutil.AccessDenied:
            return HardcoreAction(
                status="blocked",
                message=f"Không đủ quyền đóng {process_name}. Hãy chạy app với quyền admin.",
                process_name=process_name,
                window_title=window_title,
                pid=pid,
            )
        except psutil.NoSuchProcess:
            return HardcoreAction(
                status="cleared",
                message=f"{process_name} đã được đóng.",
                process_name=process_name,
                window_title=window_title,
                pid=pid,
            )
        except Exception as exc:
            logger.debug("Hardcore terminate failed", exc_info=True)
            return HardcoreAction(
                status="blocked",
                message=f"Không đóng được {process_name}: {exc}",
                process_name=process_name,
                window_title=window_title,
                pid=pid,
            )


def list_running_processes() -> list[dict[str, Any]]:
    if psutil is None:
        return []

    rows: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "username"]):
        try:
            rows.append(
                {
                    "pid": int(proc.info.get("pid") or 0),
                    "name": str(proc.info.get("name") or ""),
                    "username": str(proc.info.get("username") or ""),
                }
            )
        except Exception:
            continue
    return sorted(rows, key=lambda item: str(item.get("name") or "").lower())


def admin_permission_hint() -> str:
    system = platform.system().lower()
    if system.startswith("win"):
        return "Trên Windows, hãy chạy FocusFlow AI bằng Run as administrator để Hardcore terminate app ổn định."
    if system == "darwin":
        return "Trên macOS, hãy cấp Accessibility permission để đọc active app; terminate có thể cần quyền cao hơn."
    return "Trên Linux, Hardcore phụ thuộc quyền user hiện tại và tiện ích active-window như xdotool."


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

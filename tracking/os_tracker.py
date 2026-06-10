from __future__ import annotations

from dataclasses import dataclass, field
import os
import platform
import shutil
import subprocess
import time
from typing import Iterable

from utils.logger import get_logger


logger = get_logger("os_tracker")

try:  # Optional dependency: keep the scaffold usable even if psutil is absent.
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency path
    psutil = None
    logger.debug("psutil is not available; OS tracking will use fallback commands.")


PRODUCTIVE_KEYWORDS = (
    "visual studio code",
    "vscode",
    "code",
    "pycharm",
    "intellij",
    "jupyter",
    "notebook",
    "word",
    "libreoffice",
    "writer",
    "pdf",
    "reader",
    "acrobat",
    "preview",
    "pages",
    "docs",
)

DISTRACTION_KEYWORDS = (
    "youtube",
    "netflix",
    "spotify",
    "discord",
    "steam",
    "twitch",
    "facebook",
    "instagram",
)


@dataclass(slots=True)
class ActiveWindowSnapshot:
    platform_name: str
    process_name: str
    window_title: str = ""
    pid: int | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    interaction_score: float = 0.0
    is_productive_context: bool = False
    source: str = "unknown"
    captured_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, object]:
        return {
            "platform_name": self.platform_name,
            "process_name": self.process_name,
            "window_title": self.window_title,
            "pid": self.pid,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "interaction_score": self.interaction_score,
            "is_productive_context": self.is_productive_context,
            "source": self.source,
            "captured_at": self.captured_at,
        }


@dataclass(slots=True)
class FusionDecision:
    is_focused: bool
    source: str
    ai_probability: float
    interaction_score: float
    reason: str
    window_info: ActiveWindowSnapshot | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "is_focused": self.is_focused,
            "source": self.source,
            "ai_probability": self.ai_probability,
            "interaction_score": self.interaction_score,
            "reason": self.reason,
            "window_info": self.window_info.as_dict() if self.window_info else None,
        }


class ActiveWindowTracker:
    """Best-effort cross-platform foreground app tracker.

    The class is intentionally conservative: it is designed for a low-CPU
    background app and returns partial data rather than failing hard when a
    command is unavailable on the current platform.
    """

    def __init__(
        self,
        productive_keywords: Iterable[str] | None = None,
        distraction_keywords: Iterable[str] | None = None,
        ai_focus_threshold: float = 0.45,
        heuristic_override_threshold: float = 0.60,
    ) -> None:
        logger.debug(
            "Initializing ActiveWindowTracker (ai_focus_threshold=%.2f, heuristic_override_threshold=%.2f)",
            ai_focus_threshold,
            heuristic_override_threshold,
        )
        self.productive_keywords = tuple((productive_keywords or PRODUCTIVE_KEYWORDS))
        self.distraction_keywords = tuple((distraction_keywords or DISTRACTION_KEYWORDS))
        self.ai_focus_threshold = float(ai_focus_threshold)
        self.heuristic_override_threshold = float(heuristic_override_threshold)
        self._self_pid = os.getpid()

    def snapshot(self) -> ActiveWindowSnapshot:
        system_name = platform.system().lower()
        logger.debug("Capturing OS snapshot (platform=%s)", system_name)
        if system_name.startswith("win"):
            return self._snapshot_windows()
        if system_name == "darwin":
            return self._snapshot_macos()
        return self._snapshot_linux()

    def fuse_ai_and_os_signals(
        self,
        ai_probability: float,
        window_info: ActiveWindowSnapshot | None = None,
    ) -> FusionDecision:
        snapshot = window_info or self.snapshot()
        ai_probability = float(ai_probability)

        ai_is_focused = ai_probability >= self.ai_focus_threshold
        heuristic_is_focused = self.should_override_to_focused(snapshot)

        if ai_is_focused:
            return FusionDecision(
                is_focused=True,
                source="ai",
                ai_probability=ai_probability,
                interaction_score=snapshot.interaction_score,
                reason="AI probability is already above the focus threshold.",
                window_info=snapshot,
            )

        if heuristic_is_focused:
            return FusionDecision(
                is_focused=True,
                source="heuristic_override",
                ai_probability=ai_probability,
                interaction_score=snapshot.interaction_score,
                reason="OS tracker detected productive work despite a weaker AI signal.",
                window_info=snapshot,
            )

        return FusionDecision(
            is_focused=False,
            source="ai_or_heuristic_distracted",
            ai_probability=ai_probability,
            interaction_score=snapshot.interaction_score,
            reason="Neither the AI model nor the OS tracker reached a focused signal.",
            window_info=snapshot,
        )

    def should_override_to_focused(self, snapshot: ActiveWindowSnapshot) -> bool:
        productive_context = snapshot.is_productive_context or self._matches_any(
            f"{snapshot.process_name} {snapshot.window_title}".lower(),
            self.productive_keywords,
        )
        return productive_context and snapshot.interaction_score >= self.heuristic_override_threshold

    def build_permission_prompt(self) -> str:
        return (
            "The app needs permission to read the active app/window so it can fuse AI signals with OS heuristics. "
            "This data is only used to estimate focus state; it does not read document content or log keystrokes."
        )

    def _snapshot_windows(self) -> ActiveWindowSnapshot:
        pid, title = self._foreground_window_windows()
        process_name, cpu_percent, memory_percent = self._process_details(pid)
        return self._build_snapshot(
            platform_name="windows",
            pid=pid,
            process_name=process_name,
            window_title=title,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            source="ctypes+psutil/tasklist",
        )

    def _snapshot_macos(self) -> ActiveWindowSnapshot:
        app_name = self._run_command([
            "osascript",
            "-e",
            'tell application "System Events" to get name of first application process whose frontmost is true',
        ])
        window_title = app_name
        pid = self._resolve_pid_by_name(app_name)
        process_name, cpu_percent, memory_percent = self._process_details(pid, fallback_name=app_name)
        return self._build_snapshot(
            platform_name="darwin",
            pid=pid,
            process_name=process_name,
            window_title=window_title,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            source="osascript+psutil/ps",
        )

    def _snapshot_linux(self) -> ActiveWindowSnapshot:
        if shutil.which("xdotool"):
            logger.debug("Using xdotool for Linux active window lookup")
            window_id = self._run_command(["xdotool", "getactivewindow"])
            pid = self._safe_int(self._run_command(["xdotool", "getwindowpid", window_id]))
            title = self._run_command(["xdotool", "getwindowname", window_id]) or ""
            process_name, cpu_percent, memory_percent = self._process_details(pid)
            return self._build_snapshot(
                platform_name="linux",
                pid=pid,
                process_name=process_name,
                window_title=title,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                source="xdotool+psutil/ps",
            )

        # Fallback: best-effort process guess when desktop utilities are unavailable.
        logger.debug("xdotool not available; using process fallback for Linux snapshot")
        pid = self._top_pid_by_cpu()
        process_name, cpu_percent, memory_percent = self._process_details(pid)
        return self._build_snapshot(
            platform_name="linux",
            pid=pid,
            process_name=process_name,
            window_title=process_name,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            source="ps/psutil fallback",
        )

    def _build_snapshot(
        self,
        platform_name: str,
        pid: int | None,
        process_name: str,
        window_title: str,
        cpu_percent: float | None,
        memory_percent: float | None,
        source: str,
    ) -> ActiveWindowSnapshot:
        normalized_process = (process_name or "unknown").strip() or "unknown"
        normalized_title = (window_title or "").strip()
        interaction_score = self._compute_interaction_score(
            process_name=normalized_process,
            window_title=normalized_title,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
        )
        logger.debug(
            "Snapshot: process=%s, title=%s, cpu=%s, mem=%s, score=%.2f, source=%s",
            normalized_process,
            normalized_title,
            cpu_percent,
            memory_percent,
            interaction_score,
            source,
        )
        return ActiveWindowSnapshot(
            platform_name=platform_name,
            process_name=normalized_process,
            window_title=normalized_title,
            pid=pid,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            interaction_score=interaction_score,
            is_productive_context=self._is_productive_context(normalized_process, normalized_title),
            source=source,
        )

    def _compute_interaction_score(
        self,
        process_name: str,
        window_title: str,
        cpu_percent: float | None,
        memory_percent: float | None,
    ) -> float:
        text = f"{process_name} {window_title}".lower()
        score = 0.0

        if self._matches_any(text, self.productive_keywords):
            score += 0.35
        if self._matches_any(text, self.distraction_keywords):
            score -= 0.20

        if cpu_percent is not None:
            score += min(max(cpu_percent / 35.0, 0.0), 0.35)
        if memory_percent is not None:
            score += min(max(memory_percent / 12.0, 0.0), 0.20)

        return max(0.0, min(1.0, score))

    def _is_productive_context(self, process_name: str, window_title: str) -> bool:
        text = f"{process_name} {window_title}".lower()
        return self._matches_any(text, self.productive_keywords)

    def _matches_any(self, text: str, keywords: Iterable[str]) -> bool:
        lowered = text.lower()
        return any(keyword.lower() in lowered for keyword in keywords)

    def _process_details(
        self,
        pid: int | None,
        fallback_name: str | None = None,
    ) -> tuple[str, float | None, float | None]:
        if pid is None:
            return fallback_name or "unknown", None, None

        if psutil is not None:
            try:
                proc = psutil.Process(pid)
                process_name = proc.name()
                cpu_percent = float(proc.cpu_percent(interval=0.0))
                memory_percent = float(proc.memory_percent())
                return process_name, cpu_percent, memory_percent
            except Exception:
                pass

        process_name = fallback_name or self._tasklist_name(pid) or self._ps_name(pid) or "unknown"
        cpu_percent = self._ps_cpu_percent(pid)
        memory_percent = self._ps_memory_percent(pid)
        return process_name, cpu_percent, memory_percent

    def _resolve_pid_by_name(self, process_name: str) -> int | None:
        if not process_name:
            return None
        if psutil is not None:
            try:
                for proc in psutil.process_iter(["pid", "name"]):
                    if (proc.info.get("name") or "").lower() == process_name.lower():
                        return int(proc.info["pid"])
            except Exception:
                pass
        return self._safe_int(self._run_command(["pgrep", "-x", process_name]))

    def _foreground_window_windows(self) -> tuple[int | None, str]:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None, ""

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            title = self._get_window_text_windows(hwnd)
            return int(pid.value), title
        except Exception:
            return None, ""

    def _get_window_text_windows(self, hwnd) -> str:
        try:
            import ctypes

            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buffer = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value
        except Exception:
            return ""

    def _top_pid_by_cpu(self) -> int | None:
        if psutil is not None:
            try:
                processes = sorted(
                    psutil.process_iter(["pid", "cpu_percent", "name", "cmdline"]),
                    key=lambda proc: float(proc.info.get("cpu_percent") or 0.0),
                    reverse=True,
                )
                for proc in processes:
                    pid = self._safe_int(proc.info.get("pid"))
                    if pid is None or self._should_ignore_process(proc.info.get("name"), proc.info.get("cmdline"), pid):
                        continue
                    return pid
            except Exception:
                pass

        output = self._run_command(["sh", "-lc", "ps -eo pid=,pcpu= --sort=-pcpu | head -n 1"])
        if not output:
            return None
        parts = output.split()
        pid = self._safe_int(parts[0]) if parts else None
        if pid is not None and self._should_ignore_process(None, None, pid):
            return None
        return pid

    def _should_ignore_process(
        self,
        process_name: str | None,
        cmdline: object | None,
        pid: int | None,
    ) -> bool:
        if pid is None:
            return True
        if pid == self._self_pid:
            return True

        lowered_name = (process_name or "").strip().lower()
        if lowered_name in {"python", "python3", "python.exe", "pythonw.exe", "python3.exe"}:
            return True

        if isinstance(cmdline, (list, tuple)):
            joined = " ".join(str(part).lower() for part in cmdline)
            if "python" in joined and "main.py" in joined:
                return True
        elif isinstance(cmdline, str):
            lowered_cmd = cmdline.lower()
            if "python" in lowered_cmd and "main.py" in lowered_cmd:
                return True

        return False

    def _tasklist_name(self, pid: int) -> str | None:
        output = self._run_command([
            "tasklist",
            "/fi",
            f"PID eq {pid}",
            "/fo",
            "csv",
            "/nh",
        ])
        if not output:
            return None
        line = output.splitlines()[0].strip().strip('"')
        columns = [chunk.strip('"') for chunk in line.split('","') if chunk]
        return columns[0] if columns else None

    def _ps_name(self, pid: int) -> str | None:
        output = self._run_command(["ps", "-p", str(pid), "-o", "comm="])
        if not output:
            return None
        return output.splitlines()[0].strip() or None

    def _ps_cpu_percent(self, pid: int) -> float | None:
        output = self._run_command(["ps", "-p", str(pid), "-o", "%cpu="])
        if not output:
            return None
        return self._safe_float(output)

    def _ps_memory_percent(self, pid: int) -> float | None:
        output = self._run_command(["ps", "-p", str(pid), "-o", "%mem="])
        if not output:
            return None
        return self._safe_float(output)

    def _run_command(self, command: list[str]) -> str:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            output = (result.stdout or result.stderr or "").strip()
            if not output:
                logger.debug("Command returned empty output: %s", " ".join(command))
            return output
        except Exception:
            logger.debug("Command failed: %s", " ".join(command), exc_info=True)
            return ""

    def _safe_int(self, value: str | int | None) -> int | None:
        if value is None:
            return None
        try:
            return int(str(value).strip().split()[0])
        except Exception:
            return None

    def _safe_float(self, value: str | float | None) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).strip().split()[0])
        except Exception:
            return None


def fuse_ai_and_os_signals(
    ai_probability: float,
    window_info: ActiveWindowSnapshot | None = None,
    ai_focus_threshold: float = 0.45,
    productive_keywords: Iterable[str] | None = None,
    distraction_keywords: Iterable[str] | None = None,
) -> FusionDecision:
    tracker = ActiveWindowTracker(
        productive_keywords=productive_keywords,
        distraction_keywords=distraction_keywords,
        ai_focus_threshold=ai_focus_threshold,
    )
    return tracker.fuse_ai_and_os_signals(ai_probability=ai_probability, window_info=window_info)


__all__ = [
    "ActiveWindowSnapshot",
    "ActiveWindowTracker",
    "FusionDecision",
    "fuse_ai_and_os_signals",
]

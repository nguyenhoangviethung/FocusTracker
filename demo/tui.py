from __future__ import annotations

import sys
from dataclasses import dataclass, field


@dataclass(slots=True)
class ConsoleTUI:
    prefix: str
    enabled: bool = True
    _last_line: str = field(default="", init=False)

    def write(self, message: str) -> None:
        if not self.enabled:
            return
        self._last_line = message
        sys.stdout.write(message + "\n")
        sys.stdout.flush()

    def progress(self, message: str) -> None:
        if not self.enabled:
            return
        self._last_line = message
        sys.stdout.write(message)
        sys.stdout.flush()

    def newline(self) -> None:
        if self.enabled:
            sys.stdout.write("\n")
            sys.stdout.flush()


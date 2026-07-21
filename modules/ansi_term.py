"""VT/ANSI screen via pyte — reliable for nano/vim fullscreen."""

from __future__ import annotations

from typing import Any


class AnsiScreen:
    """Wrapper pyte.Screen + Stream untuk terminal SSH."""

    def __init__(self, rows: int = 30, cols: int = 100) -> None:
        self.rows = max(10, int(rows))
        self.cols = max(40, int(cols))
        self._screen: Any = None
        self._stream: Any = None
        self._init()

    def _init(self) -> None:
        import pyte

        self._screen = pyte.Screen(self.cols, self.rows)
        self._stream = pyte.Stream(self._screen)

    def resize(self, rows: int, cols: int) -> None:
        rows = max(10, int(rows))
        cols = max(40, int(cols))
        if rows == self.rows and cols == self.cols and self._screen is not None:
            return
        self.rows, self.cols = rows, cols
        try:
            self._screen.resize(lines=rows, columns=cols)
        except Exception:
            self._init()

    def clear(self) -> None:
        try:
            self._screen.reset()
        except Exception:
            self._init()

    def feed(self, data: str) -> bool:
        if not data:
            return False
        try:
            self._stream.feed(data)
            return True
        except Exception:
            return False

    def render(self) -> str:
        try:
            lines = list(self._screen.display)
        except Exception:
            return ""
        # Jangan potong baris kosong di tengah (nano butuh layout tetap)
        while lines and not lines[-1].rstrip():
            lines.pop()
        return "\n".join(lines) + ("\n" if lines else "")


def strip_plain(text: str) -> str:
    """Strip kasar untuk mode non-fullscreen (shell biasa)."""
    import re

    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1b[()][0-9A-Za-z]", "", text)
    text = re.sub(r"\x1b.", "", text)
    return text

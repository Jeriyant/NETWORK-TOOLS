"""Minimal ANSI/VT screen buffer for SSH terminal (nano/vim-friendly)."""

from __future__ import annotations

import re


_CSI_RE = re.compile(r"\x1b\[([0-9;?]*)([@-~])")
_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CHARSET_RE = re.compile(r"\x1b[()][0-9A-Za-z]")
_SIMPLE_ESC_RE = re.compile(r"\x1b[@-Z\\-_]")


class AnsiScreen:
    """Buffer layar sederhana: CUP/ED/EL/CUx + teks biasa."""

    def __init__(self, rows: int = 30, cols: int = 100) -> None:
        self.rows = max(10, rows)
        self.cols = max(40, cols)
        self.r = 0
        self.c = 0
        self._alt = False
        self._dirty = True
        self._buf: list[list[str]] = []
        self._reset_buf()

    def _reset_buf(self) -> None:
        self._buf = [[" " for _ in range(self.cols)] for _ in range(self.rows)]
        self.r = 0
        self.c = 0
        self._dirty = True

    def resize(self, rows: int, cols: int) -> None:
        rows = max(10, rows)
        cols = max(40, cols)
        if rows == self.rows and cols == self.cols:
            return
        old = self._buf
        self.rows, self.cols = rows, cols
        self._buf = [[" " for _ in range(cols)] for _ in range(rows)]
        for i in range(min(rows, len(old))):
            for j in range(min(cols, len(old[i]))):
                self._buf[i][j] = old[i][j]
        self.r = min(self.r, rows - 1)
        self.c = min(self.c, cols - 1)
        self._dirty = True

    def clear(self) -> None:
        self._reset_buf()

    def render(self) -> str:
        lines = ["".join(row).rstrip() for row in self._buf]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines) + ("\n" if lines else "")

    def feed(self, data: str) -> bool:
        """Proses data; return True jika buffer berubah."""
        if not data:
            return False
        # OSC / charset dulu
        data = _OSC_RE.sub("", data)
        data = _CHARSET_RE.sub("", data)
        changed = False
        i = 0
        n = len(data)
        while i < n:
            ch = data[i]
            if ch == "\x1b":
                if i + 1 < n and data[i + 1] == "[":
                    m = _CSI_RE.match(data, i)
                    if m:
                        params, final = m.group(1), m.group(2)
                        self._csi(params, final)
                        changed = True
                        i = m.end()
                        continue
                    i += 2
                    continue
                if i + 1 < n and data[i + 1] == "c":
                    self._reset_buf()
                    changed = True
                    i += 2
                    continue
                # skip other ESC sequences
                m2 = _SIMPLE_ESC_RE.match(data, i)
                if m2:
                    i = m2.end()
                    continue
                i += 1
                continue
            if ch == "\r":
                self.c = 0
                changed = True
                i += 1
                continue
            if ch == "\n":
                self._lf()
                changed = True
                i += 1
                continue
            if ch == "\b":
                if self.c > 0:
                    self.c -= 1
                changed = True
                i += 1
                continue
            if ch == "\t":
                self.c = min(self.cols - 1, (self.c + 8) // 8 * 8)
                changed = True
                i += 1
                continue
            if ch == "\x07":
                i += 1
                continue
            if ord(ch) < 32:
                i += 1
                continue
            self._put(ch)
            changed = True
            i += 1
        if changed:
            self._dirty = True
        return changed

    def _put(self, ch: str) -> None:
        if self.c >= self.cols:
            self.c = 0
            self._lf()
        self._buf[self.r][self.c] = ch
        self.c += 1

    def _lf(self) -> None:
        if self.r + 1 < self.rows:
            self.r += 1
        else:
            self._buf.pop(0)
            self._buf.append([" " for _ in range(self.cols)])

    def _params(self, raw: str) -> list[int]:
        if not raw or raw == "?":
            return []
        parts = []
        for p in raw.replace("?", "").split(";"):
            if p.isdigit():
                parts.append(int(p))
            elif p == "":
                parts.append(0)
        return parts

    def _csi(self, raw: str, final: str) -> None:
        private = raw.startswith("?")
        ps = self._params(raw)
        if final == "H" or final == "f":  # CUP
            row = (ps[0] if len(ps) > 0 and ps[0] else 1) - 1
            col = (ps[1] if len(ps) > 1 and ps[1] else 1) - 1
            self.r = max(0, min(self.rows - 1, row))
            self.c = max(0, min(self.cols - 1, col))
        elif final == "A":  # CUU
            n = ps[0] if ps else 1
            self.r = max(0, self.r - max(1, n))
        elif final == "B":  # CUD
            n = ps[0] if ps else 1
            self.r = min(self.rows - 1, self.r + max(1, n))
        elif final == "C":  # CUF
            n = ps[0] if ps else 1
            self.c = min(self.cols - 1, self.c + max(1, n))
        elif final == "D":  # CUB
            n = ps[0] if ps else 1
            self.c = max(0, self.c - max(1, n))
        elif final == "G":  # CHA
            col = (ps[0] if ps and ps[0] else 1) - 1
            self.c = max(0, min(self.cols - 1, col))
        elif final == "d":  # VPA
            row = (ps[0] if ps and ps[0] else 1) - 1
            self.r = max(0, min(self.rows - 1, row))
        elif final == "J":  # ED
            mode = ps[0] if ps else 0
            if mode == 2 or mode == 3:
                self._reset_buf()
            elif mode == 0:
                for j in range(self.c, self.cols):
                    self._buf[self.r][j] = " "
                for i in range(self.r + 1, self.rows):
                    self._buf[i] = [" " for _ in range(self.cols)]
            elif mode == 1:
                for j in range(0, self.c + 1):
                    self._buf[self.r][j] = " "
                for i in range(0, self.r):
                    self._buf[i] = [" " for _ in range(self.cols)]
        elif final == "K":  # EL
            mode = ps[0] if ps else 0
            if mode == 0:
                for j in range(self.c, self.cols):
                    self._buf[self.r][j] = " "
            elif mode == 1:
                for j in range(0, self.c + 1):
                    self._buf[self.r][j] = " "
            elif mode == 2:
                self._buf[self.r] = [" " for _ in range(self.cols)]
        elif final == "m":
            pass  # SGR ignore colors
        elif private and final in ("h", "l"):
            # alt screen ?1049
            if "1049" in raw or "47" in raw:
                if final == "h":
                    self._alt = True
                    self._reset_buf()
                else:
                    self._alt = False
                    self._reset_buf()
        # ignore other CSI


def strip_plain(text: str) -> str:
    """Fallback strip untuk mode non-fullscreen."""
    text = _OSC_RE.sub("", text)
    text = _CSI_RE.sub("", text)
    text = _CHARSET_RE.sub("", text)
    text = _SIMPLE_ESC_RE.sub("", text)
    text = text.replace("\x1b", "")
    return text

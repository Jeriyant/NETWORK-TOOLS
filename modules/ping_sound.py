"""Short ting/tet sounds for Ping & Traceroute (Windows)."""

from __future__ import annotations

import re
import threading

_HOP_LINE = re.compile(r"^\s*\d+\s+")


def play_ting(*, success: bool = True) -> None:
    """Ting (sukses) atau tet (timeout) — beep pendek, non-blocking."""

    def _play() -> None:
        try:
            import winsound

            if success:
                # ting — nada tinggi pendek
                winsound.Beep(1650, 45)
            else:
                # tet — nada rendah pendek
                winsound.Beep(380, 70)
        except Exception:
            try:
                import winsound

                winsound.MessageBeep(
                    winsound.MB_OK if success else winsound.MB_ICONHAND
                )
            except Exception:
                pass

    threading.Thread(target=_play, daemon=True).start()


def notify_ping_line(line: str) -> None:
    """Ting on reply; tet on timeout."""
    low = (line or "").lower()
    if not low.strip():
        return
    if (
        "reply from" in low
        or "balasan dari" in low
        or ("bytes=" in low and ("time=" in low or "ttl=" in low))
        or ("byte=" in low and ("waktu=" in low or "ttl=" in low))
    ):
        play_ting(success=True)
        return
    if (
        "timed out" in low
        or "habis waktu" in low
        or "waktu tunggu permintaan" in low
        or "request timed out" in low
        or "general failure" in low
        or "destination host unreachable" in low
        or "tidak dapat diakses" in low
    ):
        play_ting(success=False)


def notify_traceroute_line(line: str) -> None:
    """Ting on hop reply; tet if hop is all timeouts (*)."""
    text = (line or "").rstrip()
    if not text or not _HOP_LINE.match(text):
        return
    has_ip = bool(re.search(r"\d+\.\d+\.\d+\.\d+", text))
    has_rtt = "ms" in text.lower()
    if has_ip or has_rtt:
        play_ting(success=True)
    elif "*" in text:
        play_ting(success=False)

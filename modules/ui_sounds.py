"""UI sound helpers (hover, camera shutter) for Windows."""

from __future__ import annotations

import threading
from pathlib import Path


def _beep_sequence(notes: list[tuple[int, int]]) -> None:
    try:
        import winsound

        for freq, dur in notes:
            winsound.Beep(int(freq), int(dur))
    except Exception:
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass


def play_hover_click() -> None:
    """Bunyi singkat saat kursor masuk kotak menu."""

    def _play() -> None:
        _beep_sequence([(980, 18)])

    threading.Thread(target=_play, daemon=True).start()


def play_camera_shutter() -> None:
    """Nada potret / shutter kamera untuk notifikasi screenshot."""

    def _play() -> None:
        media = Path(r"C:\Windows\Media")
        candidates = [
            media / "Windows Camera Sound.wav",
            media / "Camera.wav",
            media / "Windows Notify System Generic.wav",
            media / "Windows Ding.wav",
        ]
        try:
            import winsound

            for path in candidates:
                if path.is_file():
                    winsound.PlaySound(
                        str(path),
                        winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                    )
                    return
        except Exception:
            pass
        # Fallback: klik-klik shutter singkat
        _beep_sequence([(2100, 35), (1400, 55)])

    threading.Thread(target=_play, daemon=True).start()

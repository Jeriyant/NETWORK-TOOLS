"""Sonar-style ping / failure sounds for Ping & Traceroute (Windows)."""

from __future__ import annotations

import io
import math
import re
import struct
import threading
import wave

_HOP_LINE = re.compile(r"^\s*\d+\s+")
_RATE = 22050
_CACHE: dict[str, bytes] = {}
_play_lock = threading.Lock()


def _pcm_wav(samples: list[float], rate: int = _RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for s in samples:
            v = int(max(-1.0, min(1.0, s)) * 32767)
            frames += struct.pack("<h", v)
        wf.writeframes(frames)
    return buf.getvalue()


def _sonar_samples(rate: int = _RATE) -> list[float]:
    """Kapal selam / sonar ping: chirp turun + decay panjang."""
    duration = 0.62
    n = int(rate * duration)
    samples: list[float] = []
    phase = 0.0
    for i in range(n):
        t = i / rate
        # Frekuensi turun seperti echo sonar
        f = 1680.0 * math.exp(-2.8 * t) + 420.0
        phase += 2.0 * math.pi * f / rate
        if t < 0.012:
            env = t / 0.012
        else:
            env = math.exp(-4.2 * (t - 0.012))
        # Harmonic tipis agar terdengar "metallic" sonar
        tone = 0.78 * math.sin(phase) + 0.18 * math.sin(2.0 * phase)
        # Echo sangat pelan di ekor
        echo = 0.0
        if t > 0.22:
            te = t - 0.22
            echo = 0.22 * math.exp(-6.0 * te) * math.sin(2.0 * math.pi * (f * 0.92) * te)
        samples.append(0.62 * env * tone + echo)
    return samples


def _failure_samples(rate: int = _RATE) -> list[float]:
    """Nada failure / error: dua buzz menurun."""
    duration = 0.42
    n = int(rate * duration)
    samples: list[float] = []
    for i in range(n):
        t = i / rate
        if t < 0.14:
            f = 340.0
            env = 0.85 * math.exp(-3.0 * t)
        elif t < 0.18:
            samples.append(0.0)
            continue
        else:
            f = 190.0
            env = 0.9 * math.exp(-5.5 * (t - 0.18))
        # Hampir kotak = bunyi "buzz" failure
        wave_s = 1.0 if math.sin(2.0 * math.pi * f * t) >= 0 else -1.0
        # Campur sine agar tidak terlalu kasar
        tone = 0.55 * wave_s + 0.45 * math.sin(2.0 * math.pi * f * t)
        samples.append(0.55 * env * tone)
    return samples


def _cached_wav(kind: str) -> bytes:
    if kind not in _CACHE:
        if kind == "sonar":
            _CACHE[kind] = _pcm_wav(_sonar_samples())
        else:
            _CACHE[kind] = _pcm_wav(_failure_samples())
    return _CACHE[kind]


def play_ting(*, success: bool = True) -> None:
    """Play sonar ping (success) or failure buzz (timeout) asynchronously."""

    def _play() -> None:
        try:
            import winsound

            data = _cached_wav("sonar" if success else "failure")
            with _play_lock:
                winsound.PlaySound(
                    data,
                    winsound.SND_MEMORY | winsound.SND_ASYNC,
                )
        except Exception:
            try:
                import winsound

                if success:
                    # Fallback kasar mirip sonar
                    winsound.Beep(1400, 80)
                    winsound.Beep(900, 120)
                else:
                    winsound.Beep(320, 120)
                    winsound.Beep(180, 160)
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
    """Sonar on successful reply; failure tone on timeout."""
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
        or "general failure" in low
        or "destination host unreachable" in low
        or "tidak dapat diakses" in low
    ):
        play_ting(success=False)


def notify_traceroute_line(line: str) -> None:
    """Sonar on hop reply; failure tone if hop is all timeouts (*)."""
    text = (line or "").rstrip()
    if not text or not _HOP_LINE.match(text):
        return
    has_ip = bool(re.search(r"\d+\.\d+\.\d+\.\d+", text))
    has_rtt = "ms" in text.lower()
    if has_ip or has_rtt:
        play_ting(success=True)
    elif "*" in text:
        play_ting(success=False)

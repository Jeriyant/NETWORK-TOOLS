"""Extract small icons from .exe / .ico / .dll for Tk PhotoImage."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def parse_display_icon(raw: str) -> tuple[str, int]:
    """DisplayIcon sering berbentuk 'C:\\path\\app.exe,0'."""
    text = (raw or "").strip().strip('"')
    if not text:
        return "", 0
    idx = 0
    path = text
    if "," in text:
        left, right = text.rsplit(",", 1)
        right = right.strip()
        if right.lstrip("-").isdigit():
            path = left.strip().strip('"')
            try:
                idx = int(right)
            except ValueError:
                idx = 0
    return path, idx


def load_icon_photo(raw: str, size: int = 20) -> Any | None:
    """Return tkinter.PhotoImage or None. Caller must keep a reference."""
    path, icon_index = parse_display_icon(raw)
    if not path:
        return None
    p = Path(os.path.expandvars(path))
    if not p.is_file():
        return None

    try:
        from PIL import Image, ImageTk
    except Exception:
        return None

    suf = p.suffix.lower()
    try:
        if suf == ".ico":
            img = Image.open(str(p))
            try:
                img.seek(max(0, icon_index))
            except Exception:
                img.seek(0)
            img = img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)

        if suf in {".exe", ".dll", ".scr"}:
            img = _extract_exe_icon(str(p), icon_index, size)
            if img is None:
                return None
            return ImageTk.PhotoImage(img)

        if suf in {".png", ".bmp", ".gif", ".jpg", ".jpeg", ".webp"}:
            img = Image.open(str(p)).convert("RGBA").resize(
                (size, size), Image.Resampling.LANCZOS
            )
            return ImageTk.PhotoImage(img)
    except Exception:
        return None
    return None


def _extract_exe_icon(path: str, index: int, size: int) -> Any | None:
    """Extract icon via Win32 ExtractIconEx + GetIconInfo."""
    import ctypes
    from ctypes import wintypes

    from PIL import Image

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    gdi32 = ctypes.windll.gdi32

    large = (ctypes.c_void_p * 1)()
    small = (ctypes.c_void_p * 1)()
    count = shell32.ExtractIconExW(path, index if index >= 0 else 0, large, small, 1)
    if count < 1:
        count = shell32.ExtractIconExW(path, 0, large, small, 1)
    if count < 1:
        return None

    hicon = large[0] or small[0]
    if not hicon:
        return None

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HBITMAP),
            ("hbmColor", wintypes.HBITMAP),
        ]

    class BITMAP(ctypes.Structure):
        _fields_ = [
            ("bmType", wintypes.LONG),
            ("bmWidth", wintypes.LONG),
            ("bmHeight", wintypes.LONG),
            ("bmWidthBytes", wintypes.LONG),
            ("bmPlanes", wintypes.WORD),
            ("bmBitsPixel", wintypes.WORD),
            ("bmBits", ctypes.c_void_p),
        ]

    info = ICONINFO()
    try:
        if not user32.GetIconInfo(hicon, ctypes.byref(info)):
            return None
        bmp = BITMAP()
        if not gdi32.GetObjectW(
            info.hbmColor or info.hbmMask, ctypes.sizeof(bmp), ctypes.byref(bmp)
        ):
            return None
        w, h = int(bmp.bmWidth), abs(int(bmp.bmHeight))
        if w <= 0 or h <= 0:
            return None

        buf_size = w * h * 4
        bits = ctypes.create_string_buffer(buf_size)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        hdr = BITMAPINFOHEADER()
        hdr.biSize = 40
        hdr.biWidth = w
        hdr.biHeight = -h
        hdr.biPlanes = 1
        hdr.biBitCount = 32
        hdr.biCompression = 0

        hdc = user32.GetDC(0)
        try:
            gdi32.GetDIBits(
                hdc,
                info.hbmColor or info.hbmMask,
                0,
                h,
                bits,
                ctypes.byref(hdr),
                0,
            )
        finally:
            user32.ReleaseDC(0, hdc)

        img = Image.frombuffer("RGBA", (w, h), bits, "raw", "BGRA", 0, 1)
        return img.resize((size, size), Image.Resampling.LANCZOS)
    finally:
        if large[0]:
            user32.DestroyIcon(large[0])
        if small[0] and small[0] != large[0]:
            user32.DestroyIcon(small[0])
        try:
            if info.hbmColor:
                gdi32.DeleteObject(info.hbmColor)
            if info.hbmMask:
                gdi32.DeleteObject(info.hbmMask)
        except Exception:
            pass

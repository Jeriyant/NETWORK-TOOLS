"""Extract small icons from .exe / .ico / .dll for Tk PhotoImage."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_FALLBACK_CACHE: dict[str, Any] = {}


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


def load_icon_photo(
    raw: str,
    size: int = 20,
    *,
    install_location: str = "",
    uninstall: str = "",
    name: str = "",
) -> Any | None:
    """Return tkinter.PhotoImage. Selalu coba fallback agar ada icon."""
    candidates: list[tuple[str, int]] = []
    path, icon_index = parse_display_icon(raw)
    if path:
        candidates.append((path, icon_index))

    # UninstallString sering berisi path ke uninstaller / exe
    if uninstall:
        u_path = _first_path_token(uninstall)
        if u_path:
            candidates.append((u_path, 0))

    # InstallLocation — cari .exe utama
    loc = (install_location or "").strip().strip('"')
    if loc:
        folder = Path(os.path.expandvars(loc))
        if folder.is_dir():
            for cand in _guess_exe_in_folder(folder, name):
                candidates.append((str(cand), 0))

    seen: set[str] = set()
    for pth, idx in candidates:
        key = f"{pth.casefold()}|{idx}"
        if key in seen:
            continue
        seen.add(key)
        photo = _load_from_file(pth, idx, size)
        if photo is not None:
            return photo

    return make_fallback_icon(name or "?", size=size)


def make_fallback_icon(name: str, size: int = 20) -> Any | None:
    """Icon statis berwarna dari huruf pertama nama aplikasi."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageTk
    except Exception:
        return None

    letter = "?"
    for ch in (name or "").strip():
        if ch.isalnum():
            letter = ch.upper()
            break
    cache_key = f"{letter}|{size}"
    if cache_key in _FALLBACK_CACHE:
        return _FALLBACK_CACHE[cache_key]

    # Warna stabil dari hash huruf
    hue = (ord(letter) * 37) % 360
    r, g, b = _hsl_to_rgb(hue / 360.0, 0.55, 0.42)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(1, size // 10)
    draw.rounded_rectangle(
        [margin, margin, size - 1 - margin, size - 1 - margin],
        radius=max(2, size // 5),
        fill=(r, g, b, 255),
    )
    try:
        font = ImageFont.truetype("segoeui.ttf", max(9, size - 6))
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", max(9, size - 6))
        except Exception:
            font = ImageFont.load_default()
    # Center letter
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - 1),
        letter,
        fill=(255, 255, 255, 255),
        font=font,
    )
    photo = ImageTk.PhotoImage(img)
    _FALLBACK_CACHE[cache_key] = photo
    return photo


def _hsl_to_rgb(h: float, s: float, light: float) -> tuple[int, int, int]:
    def hue2rgb(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    if s == 0:
        v = int(light * 255)
        return v, v, v
    q = light * (1 + s) if light < 0.5 else light + s - light * s
    p = 2 * light - q
    r = hue2rgb(p, q, h + 1 / 3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1 / 3)
    return int(r * 255), int(g * 255), int(b * 255)


def _first_path_token(cmdline: str) -> str:
    text = (cmdline or "").strip()
    if not text:
        return ""
    if text.startswith('"'):
        end = text.find('"', 1)
        if end > 1:
            return text[1:end]
    return text.split(" ", 1)[0].strip().strip('"')


def _guess_exe_in_folder(folder: Path, app_name: str) -> list[Path]:
    out: list[Path] = []
    try:
        exes = [p for p in folder.glob("*.exe") if p.is_file()]
    except Exception:
        return out
    if not exes:
        # satu level dalam
        try:
            for sub in folder.iterdir():
                if sub.is_dir():
                    exes.extend(p for p in sub.glob("*.exe") if p.is_file())
        except Exception:
            pass
    skip = {"uninstall", "unins000", "setup", "update", "crash", "helper"}
    preferred: list[Path] = []
    other: list[Path] = []
    name_key = "".join(ch for ch in (app_name or "").lower() if ch.isalnum())
    for p in exes:
        low = p.stem.lower()
        if any(s in low for s in skip):
            continue
        stem_key = "".join(ch for ch in low if ch.isalnum())
        if name_key and (stem_key in name_key or name_key[:6] in stem_key):
            preferred.append(p)
        else:
            other.append(p)
    return (preferred + other)[:4]


def _load_from_file(path: str, icon_index: int, size: int) -> Any | None:
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

        if suf in {".png", ".bmp", ".gif", ".jpg", ".jpeg", ".webp"}:
            img = Image.open(str(p)).convert("RGBA").resize(
                (size, size), Image.Resampling.LANCZOS
            )
            return ImageTk.PhotoImage(img)

        # .exe / .dll / unknown → SHGetFileInfo dulu, lalu ExtractIconEx
        img = _extract_via_shell(str(p), size)
        if img is None and suf in {".exe", ".dll", ".scr", ""}:
            img = _extract_exe_icon(str(p), icon_index, size)
        if img is None:
            return None
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def _extract_via_shell(path: str, size: int) -> Any | None:
    """SHGetFileInfo — lebih andal untuk banyak installer path."""
    import ctypes
    from ctypes import wintypes

    from PIL import Image

    class SHFILEINFO(ctypes.Structure):
        _fields_ = [
            ("hIcon", wintypes.HICON),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", wintypes.DWORD),
            ("szDisplayName", wintypes.WCHAR * 260),
            ("szTypeName", wintypes.WCHAR * 80),
        ]

    SHGFI_ICON = 0x000000100
    SHGFI_SMALLICON = 0x000000001
    SHGFI_LARGEICON = 0x000000000

    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    info = SHFILEINFO()
    flags = SHGFI_ICON | (SHGFI_SMALLICON if size <= 24 else SHGFI_LARGEICON)
    ok = shell32.SHGetFileInfoW(
        path, 0, ctypes.byref(info), ctypes.sizeof(info), flags
    )
    if not ok or not info.hIcon:
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

    ii = ICONINFO()
    try:
        if not user32.GetIconInfo(info.hIcon, ctypes.byref(ii)):
            return None
        bmp = BITMAP()
        hbmp = ii.hbmColor or ii.hbmMask
        if not gdi32.GetObjectW(hbmp, ctypes.sizeof(bmp), ctypes.byref(bmp)):
            return None
        w, h = int(bmp.bmWidth), abs(int(bmp.bmHeight))
        if w <= 0 or h <= 0:
            return None
        bits = ctypes.create_string_buffer(w * h * 4)

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
        hdc = user32.GetDC(0)
        try:
            gdi32.GetDIBits(hdc, hbmp, 0, h, bits, ctypes.byref(hdr), 0)
        finally:
            user32.ReleaseDC(0, hdc)
        img = Image.frombuffer("RGBA", (w, h), bits, "raw", "BGRA", 0, 1)
        return img.resize((size, size), Image.Resampling.LANCZOS)
    finally:
        try:
            user32.DestroyIcon(info.hIcon)
        except Exception:
            pass
        try:
            if ii.hbmColor:
                gdi32.DeleteObject(ii.hbmColor)
            if ii.hbmMask:
                gdi32.DeleteObject(ii.hbmMask)
        except Exception:
            pass


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

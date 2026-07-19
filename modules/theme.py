"""Windows Fluent–style light/dark + neon magenta theme palettes."""

from __future__ import annotations

import winreg

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#F3F3F3",
        "panel": "#FFFFFF",
        "tile": "#FFFFFF",
        "tile_hover": "#F5F5F5",
        "accent": "#005FB8",
        "accent_dim": "#004E99",
        "on_accent": "#FFFFFF",
        "text": "#1A1A1A",
        "muted": "#5C5C5C",
        "danger": "#C42B1C",
        "danger_hover": "#A52115",
        "ok": "#12B76A",
        "ok_dim": "#0E9F5A",
        "on_ok": "#FFFFFF",
        "border": "#E0E0E0",
        "console_bg": "#0C0C0C",
        "console_fg": "#CCCCCC",
    },
    "dark": {
        "bg": "#202020",
        "panel": "#2C2C2C",
        "tile": "#2C2C2C",
        "tile_hover": "#383838",
        "accent": "#60CDFF",
        "accent_dim": "#4CC2FF",
        "on_accent": "#001A2E",
        "text": "#FFFFFF",
        "muted": "#A0A0A0",
        "danger": "#FF99A4",
        "danger_hover": "#FF6B7A",
        "ok": "#32D74B",
        "ok_dim": "#28C840",
        "on_ok": "#003A10",
        "border": "#3F3F3F",
        "console_bg": "#0C0C0C",
        "console_fg": "#CCCCCC",
    },
    "neon_magenta": {
        "bg": "#0B0014",
        "panel": "#16021F",
        "tile": "#1C0828",
        "tile_hover": "#2A0F3D",
        "accent": "#FF2BD6",
        "accent_dim": "#E010B8",
        "on_accent": "#FFFFFF",
        "text": "#FFE6FB",
        "muted": "#C98FBE",
        "danger": "#FF4D6D",
        "danger_hover": "#FF2A50",
        "ok": "#39FF14",
        "ok_dim": "#2AD60A",
        "on_ok": "#062000",
        "border": "#5A1A55",
        "console_bg": "#050008",
        "console_fg": "#FFB8F0",
    },
}

MODE_LABELS = {
    "light": "Tema: Light",
    "dark": "Tema: Dark",
    "system": "Tema: Windows",
    "neon_magenta": "Tema: Neon Magenta",
}

# Urutan di dropdown
THEME_MODES = ["system", "light", "dark", "neon_magenta"]


def theme_dropdown_values() -> list[str]:
    return [MODE_LABELS[m] for m in THEME_MODES if m in MODE_LABELS]


def mode_from_label(label: str) -> str:
    for mode, text in MODE_LABELS.items():
        if text == label:
            return mode
    return "system"


def windows_prefers_light() -> bool:
    """Read Windows AppsUseLightTheme (1=light, 0=dark)."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return bool(value)
    except OSError:
        return True


def resolve_theme(mode: str) -> str:
    mode = (mode or "system").lower()
    if mode == "system":
        return "light" if windows_prefers_light() else "dark"
    if mode in THEMES:
        return mode
    return "light"


def next_mode(mode: str) -> str:
    order = list(THEME_MODES)
    mode = (mode or "system").lower()
    if mode not in order:
        return "light"
    return order[(order.index(mode) + 1) % len(order)]

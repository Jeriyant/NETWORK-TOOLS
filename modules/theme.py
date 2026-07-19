"""Windows Fluent–style light/dark theme palettes."""

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
        "border": "#3F3F3F",
        "console_bg": "#0C0C0C",
        "console_fg": "#CCCCCC",
    },
}

MODE_LABELS = {
    "light": "Tema: Light",
    "dark": "Tema: Dark",
    "system": "Tema: Windows",
}


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
    order = ["system", "light", "dark"]
    mode = (mode or "system").lower()
    if mode not in order:
        return "light"
    return order[(order.index(mode) + 1) % len(order)]

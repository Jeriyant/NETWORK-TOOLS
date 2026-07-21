"""
Network Tools — single-window desktop utility suite.
"""

from __future__ import annotations

import random
import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk

from modules.admin import is_admin, relaunch_as_admin
from modules.app_icon import app_icon_path
from modules.fix_anydesk import AnydeskRunner
from modules.fix_printer import FixPrinterRunner
from modules.fix_rdp import FixRdpRunner
from modules.i18n import (
    DEFAULT_LANG as I18N_DEFAULT,
    get_lang,
    lang_dropdown_values,
    lang_from_label,
    mode_from_theme_label,
    set_lang,
    t,
    theme_dropdown_values as i18n_theme_values,
    theme_label,
)
from modules.installed_apps import InstalledAppsRunner, format_apps_text
from modules.ip_scanner import IpScannerRunner
from modules.ping_runner import PingRunner
from modules.multi_ping import MultiHostPingRunner
from modules.prefs import load_prefs, save_prefs
from modules.refresh_network import (
    RefreshNetworkRunner,
    get_adapter_details,
    list_net_adapters,
    open_adapter_properties,
    set_adapter_enabled,
)
from modules.security_check import SecurityCheckRunner, format_security_text
from modules.settings import (
    DEFAULT_LANG,
    DEFAULT_THEME,
    DNS_LEAK_URL,
    HOSTS,
    NETWORK_ADAPTER,
    SPEEDTEST_URL,
    APP_VERSION,
    UPDATE_REPO,
    app_root,
    host_dropdown_values,
    resolve_target_ip,
)
from modules.telegram_share import (
    capture_window_region,
    send_apps_file_via_telegram,
    send_text_via_telegram,
    send_via_telegram,
)
from modules.theme import (
    THEMES,
    next_mode,
    resolve_theme,
)
from modules.traceroute_runner import TracerouteRunner
from modules.trace_topology import TracerouteTopologyRunner

# Tools that require Administrator (UAC)
ADMIN_TOOLS = frozenset({"refresh", "printer", "fixrdp", "anydesk"})
# Langsung jalan saat menu dibuka (tanpa tombol Jalankan)
AUTO_RUN_TOOLS = frozenset({"anydesk"})

# Active palette (updated when theme changes)
COLORS: dict[str, str] = dict(THEMES["light"])

# (key, icon) — title/desc dari i18n
TOOL_DEFS: list[tuple[str, str]] = [
    ("ping", "●"),
    ("traceroute", "↗"),
    ("speedtest", "⚡"),
    ("dns", "◎"),
    ("ipscan", "▦"),
    ("apps", "▤"),
    ("security", "🛡"),
    ("refresh", "↻"),
    ("printer", "🖨"),
    ("fixrdp", "⧉"),
    ("scp", "⌘"),
    ("anydesk", "⌨"),
]


def tools_for_ui() -> list[tuple[str, str, str, str]]:
    """Return (key, title, icon, desc) in current language."""
    return [
        (key, t(f"tool.{key}.title"), icon, t(f"tool.{key}.desc"))
        for key, icon in TOOL_DEFS
    ]


# Backward-compatible alias — prefer tools_for_ui() for live language
TOOLS = TOOL_DEFS

# Warna tile dashboard terang — diacak tiap aplikasi dibuka
DASH_TILE_PALETTE: list[tuple[str, str]] = [
    ("#38BDF8", "#0EA5E9"),  # sky
    ("#22C55E", "#16A34A"),  # green
    ("#F97316", "#EA580C"),  # orange
    ("#A855F7", "#9333EA"),  # purple
    ("#14B8A6", "#0D9488"),  # teal
    ("#EC4899", "#DB2777"),  # pink
    ("#6366F1", "#4F46E5"),  # indigo
    ("#EF4444", "#DC2626"),  # red
    ("#06B6D4", "#0891B2"),  # cyan
    ("#EAB308", "#CA8A04"),  # yellow
    ("#8B5CF6", "#7C3AED"),  # violet
    ("#FB7185", "#F43F5E"),  # rose
    ("#2DD4BF", "#14B8A6"),  # aqua
    ("#84CC16", "#65A30D"),  # lime
    ("#60A5FA", "#3B82F6"),  # blue
    ("#F472B6", "#EC4899"),  # hot pink
]
DASH_TILE_TEXT = "#FFFFFF"
DASH_TILE_MUTED = "#E2E8F0"
DASH_TILE_BTN = "#FFFFFF"
DASH_TILE_BTN_HOVER = "#F1F5F9"
DASH_TILE_BTN_TEXT = "#1E293B"

# Border warna-warni untuk topologi traceroute
TOPO_RAINBOW: list[str] = [
    "#EF4444",  # red
    "#F97316",  # orange
    "#EAB308",  # yellow
    "#22C55E",  # green
    "#14B8A6",  # teal
    "#3B82F6",  # blue
    "#8B5CF6",  # violet
    "#EC4899",  # pink
]

SEND_TOOLS = {"ping", "traceroute", "dns", "ipscan", "speedtest", "apps", "security"}
TEXT_SEND_TOOLS = frozenset({"apps", "ipscan"})
# Kirim/Kembali digabung di baris kontrol (bukan footer)
INLINE_ACTION_TOOLS = frozenset(
    {"ping", "traceroute", "ipscan", "apps", "security", "printer", "scp", "fixrdp", "refresh", "anydesk"}
)


def _hide_window_close_button(window: Any) -> None:
    """Hapus tombol X (Close) dari title bar Windows agar dialog wajib tidak bisa ditutup."""
    try:
        import ctypes

        window.update_idletasks()
        hwnd = int(window.winfo_id())
        parent = ctypes.windll.user32.GetParent(hwnd)
        if parent:
            hwnd = int(parent)

        gwl_style = -16
        ws_sysmenu = 0x00080000
        get_long = getattr(ctypes.windll.user32, "GetWindowLongPtrW", None)
        set_long = getattr(ctypes.windll.user32, "SetWindowLongPtrW", None)
        if get_long is None or set_long is None:
            get_long = ctypes.windll.user32.GetWindowLongW
            set_long = ctypes.windll.user32.SetWindowLongW

        style = int(get_long(hwnd, gwl_style))
        set_long(hwnd, gwl_style, style & ~ws_sysmenu)

        swp_nosize = 0x0001
        swp_nomove = 0x0002
        swp_nozorder = 0x0004
        swp_framechanged = 0x0020
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            swp_nomove | swp_nosize | swp_nozorder | swp_framechanged,
        )
    except Exception:
        pass


class ConsoleView(ctk.CTkFrame):
    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color=COLORS["console_bg"], **kwargs)
        self.text = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color=COLORS["console_bg"],
            text_color=COLORS["console_fg"],
            wrap="word",
            activate_scrollbars=True,
        )
        self.text.pack(fill="both", expand=True, padx=4, pady=4)
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def append(self, line: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")


class NetworkToolsApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        prefs = load_prefs()
        self.theme_mode = str(prefs.get("theme") or DEFAULT_THEME)
        lang = str(prefs.get("lang") or DEFAULT_LANG or I18N_DEFAULT)
        set_lang(lang)
        self.lang = get_lang()
        self._apply_palette(refresh_ui=False)

        self.title(t("app.title", version=APP_VERSION))
        self._fit_window_to_screen()
        self.configure(fg_color=COLORS["bg"])
        self._apply_window_icon()

        self._runner_stop: Callable[[], None] | None = None
        self._current_tool: str | None = None
        self.console: ConsoleView | None = None
        self._selected_host = tk.StringVar(value="")
        self._trace_entry: ctk.CTkEntry | None = None
        self._ping_combo: ctk.CTkComboBox | None = None
        self._trace_combo: ctk.CTkComboBox | None = None
        self._browser: Any | None = None
        self._speedtest_click_job: str | None = None
        self._speedtest_click_tries = 0
        self._sysinfo_poll_job: str | None = None
        self._sysinfo_value_labels: dict[str, Any] = {}
        self._sysinfo_cache: dict[str, str] | None = None
        self._sysinfo_loaded = False
        self._startup_overlay: Any | None = None
        self._update_poll_job: str | None = None
        self._update_dialog_open = False
        self._apps_list: list[dict[str, str]] = []
        self._security_items: list[Any] = []
        self._send_text_payload: str = ""
        self._dash_palette_cycle = random.sample(DASH_TILE_PALETTE, k=len(DASH_TILE_PALETTE))
        self._hover_tile_id: int | None = None
        self._geom_save_job: str | None = None
        self._geom_lock = False

        self._header = ctk.CTkFrame(self, fg_color="transparent")
        self._sysinfo_strip = ctk.CTkFrame(self, fg_color="transparent")
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._action_bar = ctk.CTkFrame(self, fg_color="transparent")
        self._footer = ctk.CTkFrame(self, fg_color=COLORS["panel"], height=34, corner_radius=0)
        self._footer.pack_propagate(False)

        year = datetime.now().year
        foot_inner = ctk.CTkFrame(self._footer, fg_color="transparent")
        foot_inner.pack(expand=True, fill="both")
        self._footer_anim_frames = ("✦ · ✦", "✧ · ✧", "★ · ★", "✩ · ✩", "✧ · ✧")
        self._footer_anim_i = 0
        self._footer_left = ctk.CTkLabel(
            foot_inner,
            text=self._footer_anim_frames[0],
            font=ctk.CTkFont(family="Segoe UI Symbol", size=12),
            text_color=COLORS["accent"],
            width=72,
        )
        self._footer_left.pack(side="left", padx=(16, 8))
        self._footer_label = ctk.CTkLabel(
            foot_inner,
            text=f"Copyright © {year} JERIYANT - BARAMCITY",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["muted"],
            justify="center",
        )
        self._footer_label.pack(side="left", expand=True)
        self._footer_right = ctk.CTkLabel(
            foot_inner,
            text=self._footer_anim_frames[0],
            font=ctk.CTkFont(family="Segoe UI Symbol", size=12),
            text_color=COLORS["accent"],
            width=72,
        )
        self._footer_right.pack(side="right", padx=(8, 16))
        self._footer_anim_job: str | None = None
        self.after(400, self._tick_footer_anim)

        # Footer dulu (bawah), lalu konten expand — copyright tetap terlihat saat resize
        self._footer.pack(fill="x", side="bottom")
        self._header.pack(fill="x", padx=16, pady=(10, 2))
        self._sysinfo_strip.pack(fill="x", padx=16, pady=(0, 0))
        self._content.pack(fill="both", expand=True, padx=12, pady=4)
        self.bind("<Configure>", self._on_main_window_configure)
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

        self.show_dashboard()
        self._show_startup_loading()
        # Pastikan window utama tidak terkunci dari sesi update sebelumnya
        try:
            self.attributes("-disabled", False)
        except Exception:
            pass
        self.after(400, self._maybe_resume_elevated_tool)
        self.after(600, self._start_update_backend_poll)
        # Failsafe: sembunyikan loading startup jika sysinfo lambat/gagal
        self.after(20_000, self._hide_startup_loading)
        try:
            from modules.updater import cleanup_update_leftovers

            cleanup_update_leftovers()
        except Exception:
            pass

    def _fit_window_to_screen(self) -> None:
        """Pulihkan lokasi & ukuran terakhir; default hanya jika belum pernah disimpan."""
        self._geom_lock = True
        try:
            self.update_idletasks()
            sw = int(self.winfo_screenwidth())
            sh = int(self.winfo_screenheight())
        except Exception:
            sw, sh = 1366, 768

        self._dash_min_w = 720
        self._dash_min_h = 460
        self._tool_min_w = 720
        self._tool_min_h = 460
        self._side_pad = 16
        self.minsize(self._dash_min_w, self._dash_min_h)

        prefs = load_prefs()
        try:
            saved_w = int(prefs.get("win_w") or 0)
            saved_h = int(prefs.get("win_h") or 0)
            saved_x = int(prefs.get("win_x")) if prefs.get("win_x") is not None else -1
            saved_y = int(prefs.get("win_y")) if prefs.get("win_y") is not None else -1
        except Exception:
            saved_w = saved_h = 0
            saved_x = saved_y = -1

        if saved_w >= 640 and saved_h >= 400:
            win_w = min(max(saved_w, 640), sw)
            win_h = min(max(saved_h, 400), sh)
            x = saved_x if saved_x >= 0 else max((sw - win_w) // 2, 0)
            y = saved_y if saved_y >= 0 else 24
            # Pastikan masih terlihat di layar
            x = max(-win_w + 120, min(x, sw - 80))
            y = max(0, min(y, sh - 80))
        else:
            win_w = min(1000, max(sw - 40, 720))
            win_h = min(620, max(sh - 80, 480))
            x = max((sw - win_w) // 2, 0)
            y = 24

        self._dash_w = win_w
        self.geometry(f"{win_w}x{win_h}+{x}+{y}")
        # Re-apply setelah layout awal (hindari overwrite prefs oleh ukuran sementara)
        self.after(50, lambda: self._apply_saved_geometry(win_w, win_h, x, y))
        self.after(1200, self._unlock_geometry)

    def _apply_saved_geometry(self, w: int, h: int, x: int, y: int) -> None:
        try:
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _unlock_geometry(self) -> None:
        self._geom_lock = False

    def _fit_dashboard_window(self) -> None:
        """Jangan paksa resize — hanya refresh wrap deskripsi tile."""
        try:
            self.after(30, self._refresh_tile_wrap)
        except Exception:
            pass

    def _refresh_tile_wrap(self) -> None:
        """Update wrap deskripsi saat lebar tile berubah (stretch)."""
        for tile, desc_lbl in getattr(self, "_dash_tile_descs", []) or []:
            try:
                tw = int(tile.winfo_width())
                if tw > 40:
                    desc_lbl.configure(wraplength=max(tw - 28, 80))
            except Exception:
                pass

    def _tick_footer_anim(self) -> None:
        """Animasi dekoratif kiri/kanan copyright."""
        try:
            frames = getattr(self, "_footer_anim_frames", ())
            if not frames:
                return
            self._footer_anim_i = (getattr(self, "_footer_anim_i", 0) + 1) % len(frames)
            text = frames[self._footer_anim_i]
            accent = COLORS.get("accent", "#2563EB")
            muted = COLORS.get("muted", "#888888")
            # Selang-seling warna agar terasa hidup
            color = accent if self._footer_anim_i % 2 == 0 else muted
            if hasattr(self, "_footer_left"):
                self._footer_left.configure(text=text, text_color=color)
            if hasattr(self, "_footer_right"):
                self._footer_right.configure(text=text, text_color=color)
        except Exception:
            pass
        self._footer_anim_job = self.after(480, self._tick_footer_anim)

    def _ensure_footer_visible(self) -> None:
        """Pastikan bar copyright selalu terpasang di bawah jendela."""
        try:
            if not self._footer.winfo_ismapped():
                self._footer.pack(fill="x", side="bottom")
            self._content.pack_configure(fill="both", expand=True)
            self._footer.lift()
        except Exception:
            pass

    def _schedule_save_geometry(self) -> None:
        if getattr(self, "_geom_lock", False):
            return
        if self._geom_save_job is not None:
            try:
                self.after_cancel(self._geom_save_job)
            except Exception:
                pass
        self._geom_save_job = self.after(500, self._save_window_geometry)

    def _save_window_geometry(self) -> None:
        self._geom_save_job = None
        if getattr(self, "_geom_lock", False):
            return
        try:
            self.update_idletasks()
            state = str(self.wm_state())
            if state in {"iconic", "withdrawn"}:
                return
            # Pakai geometry string agar konsisten dengan restore
            geo = self.geometry()  # e.g. 1000x620+120+40
            m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", geo)
            if not m:
                w = int(self.winfo_width())
                h = int(self.winfo_height())
                x = int(self.winfo_x())
                y = int(self.winfo_y())
            else:
                w, h, x, y = (int(m.group(i)) for i in range(1, 5))
            # Abaikan ukuran sementara saat init (sering < minsize)
            if w < 640 or h < 400:
                return
            self._dash_w = w
            save_prefs(
                theme=self.theme_mode,
                lang=get_lang(),
                win_w=w,
                win_h=h,
                win_x=x,
                win_y=y,
            )
        except Exception:
            pass

    def _on_app_close(self) -> None:
        self._geom_lock = False
        job = getattr(self, "_update_poll_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._update_poll_job = None
        self._save_window_geometry()
        try:
            self.destroy()
        except Exception:
            pass

    def _on_main_window_configure(self, event: Any = None) -> None:
        if event is not None and event.widget is not self:
            return
        self._schedule_save_geometry()
        if self._current_tool is not None:
            return
        self._ensure_footer_visible()

    def _play_tile_hover(self, tile_id: int) -> None:
        if self._hover_tile_id == tile_id:
            return
        self._hover_tile_id = tile_id
        try:
            from modules.ui_sounds import play_hover_click

            play_hover_click()
        except Exception:
            pass

    def _apply_window_icon(self) -> None:
        """Samakan icon jendela dengan icon file EXE."""
        path = app_icon_path()
        if not path:
            return
        try:
            self.iconbitmap(default=str(path))
        except Exception:
            try:
                self.iconbitmap(str(path))
            except Exception:
                pass
        try:
            from PIL import Image, ImageTk

            img = Image.open(path)
            # Keep reference so Tk doesn't GC the photo
            self._app_icon_photo = ImageTk.PhotoImage(img.resize((32, 32)))
            self.iconphoto(True, self._app_icon_photo)
        except Exception:
            pass

    def _persist_prefs(self) -> None:
        try:
            self.update_idletasks()
            save_prefs(
                theme=self.theme_mode,
                lang=get_lang(),
                win_w=int(self.winfo_width()),
                win_h=int(self.winfo_height()),
                win_x=int(self.winfo_x()),
                win_y=int(self.winfo_y()),
            )
        except Exception:
            save_prefs(theme=self.theme_mode, lang=get_lang())

    def _maybe_resume_elevated_tool(self) -> None:
        """Setelah UAC, buka ulang tool & jalankan aksi tertunda (fix/uninstall/dll)."""
        import sys

        if "--elevate-tool" not in sys.argv:
            return
        try:
            idx = sys.argv.index("--elevate-tool")
            key = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        except Exception:
            return
        if key not in {t[0] for t in TOOL_DEFS}:
            return
        if not is_admin():
            return

        prefs = load_prefs()
        action = str(prefs.get("pending_elevate_action") or "fix")
        payload = str(prefs.get("pending_elevate_payload") or "")
        try:
            save_prefs(
                pending_elevate_action="",
                pending_elevate_payload="",
                pending_elevate_tool="",
            )
        except Exception:
            pass

        if key == "printer":
            if action in ("uninstall_driver", "reinstall_driver", "fix"):
                self._elevate_printer_action = (action, payload)
            else:
                self._elevate_auto_fix_printer = True
        elif key == "fixrdp":
            self._elevate_auto_fix_rdp = True
        elif key == "refresh":
            if action in ("enable_adapter", "disable_adapter"):
                self._elevate_network_action = (action, payload)
            else:
                self._elevate_auto_fix_refresh = True
        elif key == "anydesk":
            self._elevate_auto_run_anydesk = True
        self.open_tool(key)

    def _show_startup_loading(self) -> None:
        """Overlay loading hingga bar info sistem terisi."""
        if getattr(self, "_startup_overlay", None) is not None:
            return
        if self._sysinfo_loaded and self._sysinfo_cache:
            return
        ov = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        ov.place(relx=0, rely=0, relwidth=1, relheight=1)
        box = ctk.CTkFrame(ov, fg_color="transparent")
        box.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(
            box,
            text=t("app.brand"),
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLORS["accent"],
        ).pack()
        ctk.CTkLabel(
            box,
            text=t("app.startup_loading"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["muted"],
        ).pack(pady=(10, 12))
        bar = ctk.CTkProgressBar(
            box,
            width=280,
            height=8,
            progress_color=COLORS["accent"],
            fg_color=COLORS["panel"],
            mode="indeterminate",
        )
        bar.pack()
        bar.start()
        self._startup_overlay = ov
        self._startup_loading_bar = bar

    def _hide_startup_loading(self) -> None:
        ov = getattr(self, "_startup_overlay", None)
        if ov is None:
            return
        bar = getattr(self, "_startup_loading_bar", None)
        try:
            if bar is not None:
                bar.stop()
        except Exception:
            pass
        try:
            ov.place_forget()
            ov.destroy()
        except Exception:
            pass
        self._startup_overlay = None
        self._startup_loading_bar = None

    def _lift_startup_loading(self) -> None:
        ov = getattr(self, "_startup_overlay", None)
        if ov is None:
            return
        try:
            ov.lift()
        except Exception:
            pass

    def _start_update_backend_poll(self) -> None:
        """Cek update di background sekarang, lalu ulang tiap 1 menit."""
        self._run_update_check_once()

    def _run_update_check_once(self) -> None:
        """Satu siklus cek update (silent); dijadwalkan ulang tiap 60 detik."""
        import threading

        self._update_poll_job = None

        def worker() -> None:
            info = None
            try:
                from modules.updater import check_for_update

                info = check_for_update(APP_VERSION)
            except Exception:
                info = None

            def done() -> None:
                if info is not None and not getattr(self, "_update_dialog_open", False):
                    self._prompt_update(info)
                try:
                    self._update_poll_job = self.after(60_000, self._run_update_check_once)
                except Exception:
                    pass

            try:
                self.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _check_update_on_startup(self) -> None:
        """Kompatibilitas: arahkan ke poll backend."""
        self._start_update_backend_poll()

    def _prompt_update(self, info: Any) -> None:
        """Update wajib: dialog kustom, hanya tombol Update — tanpa update app tidak bisa dipakai."""
        if getattr(self, "_update_dialog_open", False):
            return
        self._update_dialog_open = True
        import sys
        import tempfile
        import webbrowser
        from pathlib import Path

        from modules.updater import is_direct_exe_url

        ver = str(getattr(info, "version", "?") or "?")
        notes = (getattr(info, "changelog", "") or "").strip()
        if len(notes) > 500:
            notes = notes[:500] + "…"

        dlg = ctk.CTkToplevel(self)
        dlg.title(t("update.title"))
        dlg.geometry("600x580")
        dlg.minsize(560, 540)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.configure(fg_color=COLORS["bg"])

        self.update_idletasks()
        px = self.winfo_rootx() + max((self.winfo_width() - 600) // 2, 0)
        py = self.winfo_rooty() + max((self.winfo_height() - 580) // 2, 0)
        dlg.geometry(f"600x580+{max(px, 40)}+{max(py, 40)}")

        state = {"accepted": False}

        # Update wajib: tanpa tombol X; Alt+F4 juga diabaikan
        def block_close() -> None:
            pass

        dlg.protocol("WM_DELETE_WINDOW", block_close)
        dlg.after(50, lambda: _hide_window_close_button(dlg))

        card = ctk.CTkFrame(
            dlg,
            fg_color=COLORS["panel"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="both", expand=True, padx=18, pady=18)

        # Footer dulu agar tombol tidak terpotong
        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=18, pady=(4, 18))

        def on_ok() -> None:
            import os

            state["accepted"] = True
            self._update_dialog_open = False
            try:
                dlg.grab_release()
            except Exception:
                pass
            try:
                dlg.destroy()
            except Exception:
                pass

            url = str(getattr(info, "download_url", "") or "")
            if not url:
                webbrowser.open(UPDATE_REPO)
                os._exit(0)
                return

            if not is_direct_exe_url(url) or not getattr(sys, "frozen", False):
                webbrowser.open(url if url.startswith("http") else UPDATE_REPO)
                if not getattr(sys, "frozen", False):
                    messagebox.showinfo(
                        "Update",
                        t("update.dev"),
                        parent=self,
                    )
                    return
                os._exit(0)
                return

            dest = Path(tempfile.gettempdir()) / f"NetworkTools_update_v{ver}.exe"
            self._show_download_progress(url, dest, ver, info)

        ctk.CTkButton(
            footer,
            text=t("update.now"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=15),
            height=46,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=on_ok,
        ).pack(fill="x")

        ctk.CTkLabel(
            footer,
            text=t("update.footer"),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["muted"],
        ).pack(pady=(10, 0))

        # Header accent — padding bawah besar agar teks tidak terpotong corner radius
        header = ctk.CTkFrame(card, fg_color=COLORS["accent"], corner_radius=12)
        header.pack(fill="x", padx=18, pady=(18, 0))

        head_inner = ctk.CTkFrame(header, fg_color="transparent")
        head_inner.pack(fill="x", padx=20, pady=18)

        ctk.CTkLabel(
            head_inner,
            text=t("update.badge"),
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLORS["on_accent"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            head_inner,
            text=t("update.heading"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=COLORS["on_accent"],
        ).pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(
            head_inner,
            text=t("update.sub"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["on_accent"],
        ).pack(anchor="w", pady=(8, 0))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(14, 8))

        ver_row = ctk.CTkFrame(body, fg_color="transparent")
        ver_row.pack(fill="x", pady=(0, 14))
        ver_row.grid_columnconfigure((0, 2), weight=1)

        def _ver_chip(parent: Any, label: str, value: str, emphasize: bool) -> None:
            chip = ctk.CTkFrame(
                parent,
                fg_color=COLORS["bg"],
                corner_radius=10,
                border_width=1,
                border_color=COLORS["accent"] if emphasize else COLORS["border"],
            )
            chip.pack(fill="both", expand=True)
            ctk.CTkLabel(
                chip,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=COLORS["muted"],
            ).pack(anchor="w", padx=14, pady=(10, 0))
            ctk.CTkLabel(
                chip,
                text=value,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=17),
                text_color=COLORS["accent"] if emphasize else COLORS["text"],
            ).pack(anchor="w", padx=14, pady=(4, 12))

        left = ctk.CTkFrame(ver_row, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        _ver_chip(left, t("update.current"), f"v{APP_VERSION}", False)

        ctk.CTkLabel(
            ver_row,
            text="→",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=18),
            text_color=COLORS["accent"],
        ).grid(row=0, column=1, padx=4)

        right = ctk.CTkFrame(ver_row, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        _ver_chip(right, t("update.latest"), f"v{ver}", True)

        ctk.CTkLabel(
            body,
            text=t("update.notes"),
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        notes_wrap = ctk.CTkFrame(
            body,
            fg_color=COLORS["bg"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"],
        )
        notes_wrap.pack(fill="both", expand=True)

        notes_box = ctk.CTkTextbox(
            notes_wrap,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="transparent",
            text_color=COLORS["text"],
            border_width=0,
            corner_radius=0,
            wrap="word",
            activate_scrollbars=True,
        )
        notes_box.pack(fill="both", expand=True, padx=10, pady=10)
        notes_box.insert("1.0", notes or t("update.notes_fallback"))
        notes_box.configure(state="disabled")

        def _show_modal() -> None:
            try:
                dlg.lift()
                dlg.attributes("-topmost", True)
                dlg.focus_force()
                dlg.grab_set()
            except Exception:
                pass

        dlg.after(40, _show_modal)

    def _show_download_progress(
        self,
        url: str,
        dest: Path,
        ver: str,
        info: Any,
    ) -> None:
        """Dialog progress bar saat mengunduh update (wajib — tidak bisa dibatalkan)."""
        import threading
        import webbrowser

        from modules.updater import apply_update_and_restart, download_file

        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Memasang v{ver}")
        dlg.geometry("460x220")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color=COLORS["bg"])
        dlg.grab_set()

        self.update_idletasks()
        px = self.winfo_rootx() + (self.winfo_width() - 460) // 2
        py = self.winfo_rooty() + (self.winfo_height() - 220) // 2
        dlg.geometry(f"460x220+{max(px, 40)}+{max(py, 40)}")

        # Update wajib: tanpa tombol X; Alt+F4 diabaikan
        def block_close() -> None:
            pass

        dlg.protocol("WM_DELETE_WINDOW", block_close)
        dlg.after(50, lambda: _hide_window_close_button(dlg))

        frame = ctk.CTkFrame(
            dlg,
            fg_color=COLORS["panel"],
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border"],
        )
        frame.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            frame,
            text=f"Memasang Network Tools v{ver}",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=16),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=18, pady=(16, 2))

        ctk.CTkLabel(
            frame,
            text="Jangan tutup aplikasi selama proses berlangsung.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=18, pady=(0, 12))

        status = ctk.CTkLabel(
            frame,
            text="Menyiapkan unduhan...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
        )
        status.pack(anchor="w", padx=18, pady=(0, 8))

        bar = ctk.CTkProgressBar(
            frame,
            width=400,
            height=18,
            progress_color=COLORS["accent"],
            fg_color=COLORS["border"],
            corner_radius=8,
        )
        bar.pack(padx=18, pady=(0, 6))
        bar.set(0)

        pct = ctk.CTkLabel(
            frame,
            text="0%",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
            text_color=COLORS["accent"],
        )
        pct.pack(anchor="e", padx=18, pady=(0, 16))

        state = {"closed": False}

        def safe_ui(fn: Callable[[], None]) -> None:
            if state["closed"]:
                return
            try:
                if dlg.winfo_exists():
                    fn()
            except Exception:
                pass

        def on_progress(received: int, total: int | None) -> None:
            def apply() -> None:
                if total and total > 0:
                    ratio = min(1.0, received / total)
                    bar.set(ratio)
                    mb_r = received / (1024 * 1024)
                    mb_t = total / (1024 * 1024)
                    pct.configure(text=f"{ratio * 100:.0f}%")
                    status.configure(
                        text=f"Mengunduh... {mb_r:.1f} / {mb_t:.1f} MB"
                    )
                else:
                    mb_r = received / (1024 * 1024)
                    pulse = (received % (8 * 1024 * 1024)) / (8 * 1024 * 1024)
                    bar.set(min(0.95, 0.08 + pulse * 0.85))
                    pct.configure(text=f"{mb_r:.1f} MB")
                    status.configure(text=f"Mengunduh... {mb_r:.1f} MB")

            self.after(0, lambda: safe_ui(apply))

        def start_download() -> None:
            def worker() -> None:
                try:
                    from modules.updater import verify_exe_file

                    expected = getattr(info, "size", None)
                    download_file(
                        url,
                        dest,
                        on_progress=on_progress,
                        expected_size=expected if isinstance(expected, int) else None,
                    )
                    verify_exe_file(
                        dest,
                        expected_size=expected if isinstance(expected, int) else None,
                    )
                    apply_update_and_restart(dest)

                    def ok() -> None:
                        # Langsung keluar — tanpa dialog apa pun.
                        import os

                        state["closed"] = True
                        os._exit(0)

                    self.after(0, ok)
                except Exception as exc:
                    def fail() -> None:
                        state["closed"] = True
                        try:
                            dlg.grab_release()
                            dlg.destroy()
                        except Exception:
                            pass
                        retry = messagebox.askretrycancel(
                            "Update gagal",
                            f"Gagal memasang update:\n{exc}\n\n"
                            "Coba lagi? (Cancel = keluar aplikasi)",
                            parent=self,
                        )
                        if retry:
                            self._show_download_progress(url, dest, ver, info)
                        else:
                            webbrowser.open(
                                getattr(info, "html_url", None) or UPDATE_REPO
                            )
                            import os

                            os._exit(0)

                    self.after(0, fail)

            threading.Thread(target=worker, daemon=True).start()

        start_download()

    def _apply_palette(self, refresh_ui: bool = True) -> None:
        resolved = resolve_theme(self.theme_mode)
        COLORS.clear()
        COLORS.update(THEMES[resolved])
        ctk.set_appearance_mode("light" if resolved == "light" else "dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=COLORS["bg"])
        self.title(t("app.title", version=APP_VERSION))
        if hasattr(self, "_footer"):
            self._footer.configure(fg_color=COLORS["panel"])
        if hasattr(self, "_footer_label"):
            self._footer_label.configure(text_color=COLORS["muted"])
        if hasattr(self, "_footer_left"):
            self._footer_left.configure(text_color=COLORS["accent"])
        if hasattr(self, "_footer_right"):
            self._footer_right.configure(text_color=COLORS["accent"])
        if not refresh_ui:
            return
        # Rebuild sysinfo strip labels in new language/theme
        self._sysinfo_value_labels = {}
        tool = self._current_tool
        if tool:
            self.open_tool(tool)
        else:
            self.show_dashboard()

    def _cycle_theme(self) -> None:
        self.theme_mode = next_mode(self.theme_mode)
        self._persist_prefs()
        self._apply_palette(refresh_ui=True)

    def _on_theme_dropdown(self, choice: str) -> None:
        mode = mode_from_theme_label(choice)
        if mode == self.theme_mode:
            return
        self.theme_mode = mode
        self._persist_prefs()
        self._apply_palette(refresh_ui=True)

    def _on_lang_dropdown(self, choice: str) -> None:
        lang = lang_from_label(choice)
        if lang == get_lang():
            return
        set_lang(lang)
        self.lang = lang
        self._persist_prefs()
        self._apply_palette(refresh_ui=True)

    def _header_actions(self, parent: ctk.CTkFrame | None = None) -> None:
        host = parent if parent is not None else self._header
        actions = ctk.CTkFrame(host, fg_color="transparent")
        actions.pack(side="right", pady=4)

        theme_values = i18n_theme_values()
        theme_current = theme_label(self.theme_mode)
        theme_combo = ctk.CTkOptionMenu(
            actions,
            values=theme_values,
            width=170,
            height=34,
            fg_color=COLORS["tile"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_dim"],
            dropdown_fg_color=COLORS["panel"],
            dropdown_hover_color=COLORS["tile_hover"],
            text_color=COLORS["text"],
            command=self._on_theme_dropdown,
        )
        theme_combo.set(theme_current if theme_current in theme_values else theme_values[0])
        theme_combo.pack(side="right", padx=(8, 0))

        lang_values = lang_dropdown_values()
        lang_current = t("lang.en") if get_lang() == "en" else t("lang.id")
        lang_combo = ctk.CTkOptionMenu(
            actions,
            values=lang_values,
            width=170,
            height=34,
            fg_color=COLORS["tile"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_dim"],
            dropdown_fg_color=COLORS["panel"],
            dropdown_hover_color=COLORS["tile_hover"],
            text_color=COLORS["text"],
            command=self._on_lang_dropdown,
        )
        lang_combo.set(lang_current if lang_current in lang_values else lang_values[0])
        lang_combo.pack(side="right")

    def _build_sysinfo_bar(self, parent: ctk.CTkFrame) -> None:
        """Status strip compact; kolom mengikuti teks, tanpa celah expand di tengah."""
        # Sudah ada — jangan rebuild / jangan reload data
        if self._sysinfo_value_labels and parent.winfo_children():
            self._show_sysinfo_strip()
            self._apply_sysinfo_cache_to_labels()
            self._ensure_latency_poll()
            if self._sysinfo_loaded:
                self._hide_startup_loading()
            return

        for child in parent.winfo_children():
            child.destroy()

        bar = ctk.CTkFrame(
            parent,
            fg_color=COLORS["panel"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"],
            height=52,
        )
        bar.pack(fill="x", pady=(6, 0))
        bar.pack_propagate(False)
        self._sysinfo_bar = bar

        rail = ctk.CTkFrame(bar, fg_color=COLORS["accent"], width=4, corner_radius=0)
        rail.pack(side="left", fill="y")

        body = ctk.CTkFrame(bar, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=(10, 10), pady=(4, 5))
        self._sysinfo_body = body

        metrics = [
            ("hostname", t("sys.host"), "…", True),
            ("ip", t("sys.ip"), "…", True),
            ("latency", t("sys.latency"), "…", True),
            ("cpu", t("sys.cpu"), "…", False),
            ("ram", t("sys.ram"), "…", False),
            ("uptime", t("sys.uptime"), "…", False),
            ("windows", t("sys.windows"), "…", False),
        ]
        self._sysinfo_value_labels = {}
        self._sysinfo_cells: dict[str, Any] = {}
        self._sysinfo_flex_keys = ("cpu", "windows")

        for idx, (cache_key, label, placeholder, emphasize) in enumerate(metrics):
            # Jangan expand — biar tidak ada lubang kosong di tengah bar
            cell = ctk.CTkFrame(body, fg_color="transparent")
            cell.pack(side="left", padx=(0, 2))
            self._sysinfo_cells[cache_key] = cell

            ctk.CTkLabel(
                cell,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color=COLORS["muted"],
                anchor="w",
                height=12,
            ).pack(anchor="w")

            value = ctk.CTkLabel(
                cell,
                text=placeholder,
                font=ctk.CTkFont(
                    family="Segoe UI Semibold",
                    size=12 if emphasize else 11,
                ),
                text_color=COLORS["accent"] if emphasize else COLORS["text"],
                anchor="w",
                justify="left",
                wraplength=0,
                height=18,
            )
            value.pack(anchor="w")
            self._sysinfo_value_labels[cache_key] = value

            if idx < len(metrics) - 1:
                sep = ctk.CTkFrame(
                    body,
                    fg_color=COLORS["border"],
                    width=1,
                    height=28,
                    corner_radius=0,
                )
                sep.pack(side="left", padx=6, pady=2)

        body.bind("<Configure>", lambda _e: self.after(60, self._relayout_sysinfo))
        self.after(120, self._relayout_sysinfo)

        self._show_sysinfo_strip()
        if self._sysinfo_cache:
            self._apply_sysinfo_cache_to_labels()
            self._ensure_latency_poll()
        else:
            self.after(40, self._load_sysinfo_once)

    def _relayout_sysinfo(self) -> None:
        """Teks lurus jika muat; wrap + bar sedikit lebih tinggi jika sempit."""
        labels = getattr(self, "_sysinfo_value_labels", None) or {}
        body = getattr(self, "_sysinfo_body", None)
        bar = getattr(self, "_sysinfo_bar", None)
        flex_keys = getattr(self, "_sysinfo_flex_keys", ("cpu", "windows"))
        if not labels or body is None:
            return
        try:
            if not body.winfo_exists():
                return
            avail = int(body.winfo_width())
            if avail < 80:
                return

            for key, lbl in labels.items():
                try:
                    # ukur natural
                    lbl.configure(wraplength=0, height=18)
                except Exception:
                    pass
            body.update_idletasks()

            natural: dict[str, int] = {}
            for key, lbl in labels.items():
                try:
                    natural[key] = max(int(lbl.winfo_reqwidth()), 36)
                except Exception:
                    natural[key] = 72

            pad = 14 * max(len(labels) - 1, 0)
            total = sum(natural.values()) + pad
            need_wrap = total > avail

            if not need_wrap:
                for key in flex_keys:
                    lbl = labels.get(key)
                    if lbl is not None and int(lbl.cget("wraplength") or 0) != 0:
                        lbl.configure(wraplength=0, height=18)
                if bar is not None:
                    bar.configure(height=52)
                return

            fixed = pad
            for key, w in natural.items():
                if key not in flex_keys:
                    fixed += w
            remain = max(avail - fixed, 100)
            flex_need = sum(natural.get(k, 80) for k in flex_keys) or 1
            for key in flex_keys:
                lbl = labels.get(key)
                if lbl is None:
                    continue
                share = max(int(remain * natural.get(key, 80) / flex_need) - 4, 70)
                need = natural.get(key, 80)
                if need <= share:
                    lbl.configure(wraplength=0, height=18)
                else:
                    lbl.configure(wraplength=share, height=0)
            if bar is not None:
                bar.configure(height=68)
        except Exception:
            pass

    def _show_sysinfo_strip(self) -> None:
        try:
            pad = int(getattr(self, "_side_pad", 16))
            if not self._sysinfo_strip.winfo_ismapped():
                self._sysinfo_strip.pack(fill="x", padx=pad, pady=(0, 0), before=self._content)
            else:
                self._sysinfo_strip.pack_configure(padx=pad, pady=(0, 0))
        except Exception:
            pass

    def _hide_sysinfo_strip(self) -> None:
        try:
            self._sysinfo_strip.pack_forget()
        except Exception:
            pass

    def _apply_sysinfo_cache_to_labels(self) -> None:
        if self._sysinfo_cache:
            self._apply_sysinfo(self._sysinfo_cache)

    def _ensure_latency_poll(self) -> None:
        if getattr(self, "_sysinfo_poll_job", None):
            return
        self._sysinfo_poll_job = self.after(5_000, self._poll_latency)

    def _load_sysinfo_once(self) -> None:
        """Load host/IP/CPU/RAM/uptime/windows sekali + latensi awal."""
        import threading

        if self._sysinfo_loaded:
            self._apply_sysinfo_cache_to_labels()
            self._ensure_latency_poll()
            self._hide_startup_loading()
            return

        def worker() -> None:
            try:
                from modules.system_info import collect_system_info

                info = dict(collect_system_info())
            except Exception:
                info = {
                    "hostname": "-",
                    "ip": "-",
                    "latency": "-",
                    "cpu": "-",
                    "ram": "-",
                    "uptime": "-",
                    "windows": "-",
                }

            def apply() -> None:
                self._sysinfo_cache = info
                self._sysinfo_loaded = True
                self._apply_sysinfo(info)
                self._ensure_latency_poll()
                self._hide_startup_loading()

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def _poll_latency(self) -> None:
        """Hanya refresh latensi tiap 5 detik."""
        self._sysinfo_poll_job = None
        if not getattr(self, "_sysinfo_value_labels", None):
            return

        import threading

        def worker() -> None:
            try:
                from modules.system_info import latency_to_dns

                latency = latency_to_dns("8.8.8.8")
            except Exception:
                latency = "-"

            def apply() -> None:
                if self._sysinfo_cache is not None:
                    self._sysinfo_cache["latency"] = latency
                label = self._sysinfo_value_labels.get("latency")
                if label is None:
                    return
                try:
                    if label.winfo_exists():
                        label.configure(text=latency)
                except Exception:
                    pass
                self._sysinfo_poll_job = self.after(5_000, self._poll_latency)

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_sysinfo(self, info: dict[str, str]) -> None:
        labels = getattr(self, "_sysinfo_value_labels", None)
        if not labels:
            return
        mapping = {
            "hostname": info.get("hostname", "-"),
            "ip": info.get("ip", "-"),
            "latency": info.get("latency", "-"),
            "cpu": info.get("cpu", "-"),
            "ram": info.get("ram", "-"),
            "uptime": info.get("uptime", "-"),
            "windows": info.get("windows", "-"),
        }
        for key, text in mapping.items():
            label = labels.get(key)
            if label is None:
                continue
            try:
                if label.winfo_exists():
                    label.configure(text=text)
            except Exception:
                pass
        self.after(60, self._relayout_sysinfo)

    # ----- navigation -----
    def _clear_frame(self, frame: ctk.CTkFrame) -> None:
        # Jangan batalkan poll latensi / hapus cache saat ganti menu
        for child in frame.winfo_children():
            child.destroy()

    def _destroy_browser(self) -> None:
        if self._speedtest_click_job is not None:
            try:
                self.after_cancel(self._speedtest_click_job)
            except Exception:
                pass
            self._speedtest_click_job = None
        self._speedtest_click_tries = 0
        if self._browser is not None:
            try:
                self._browser.destroy()
            except Exception:
                pass
            self._browser = None

    def _stop_runner(self) -> None:
        if self._runner_stop:
            try:
                self._runner_stop()
            except Exception:
                pass
        self._runner_stop = None
        self._destroy_browser()
        sess = getattr(self, "_scp_session", None)
        if sess is not None:
            try:
                sess.disconnect()
            except Exception:
                pass
            self._scp_session = None

    def show_dashboard(self) -> None:
        self._set_anydesk_topmost(False)
        self._stop_runner()
        self._current_tool = None
        self.console = None
        self._trace_entry = None
        self._ping_combo = None
        self._trace_combo = None

        pad = int(getattr(self, "_side_pad", 16))
        try:
            self._header.pack_configure(padx=pad, pady=(6, 2))
            self._content.pack_configure(fill="both", expand=True, padx=pad, pady=(4, 4))
            if self._sysinfo_strip.winfo_ismapped():
                self._sysinfo_strip.pack_configure(padx=pad, pady=(0, 0))
            self._ensure_footer_visible()
        except Exception:
            pass

        self._action_bar.pack_forget()
        self._clear_frame(self._header)
        self._clear_frame(self._content)
        self._clear_frame(self._action_bar)

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")

        brand = ctk.CTkFrame(top, fg_color="transparent")
        brand.pack(side="left")
        ctk.CTkLabel(
            brand,
            text=t("app.brand"),
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text=t("app.tagline"),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(0, 0))

        self._header_actions(top)
        self._build_sysinfo_bar(self._sysinfo_strip)

        # Grid stretch: ikut membesar saat jendela di-resize
        grid = ctk.CTkFrame(self._content, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        self._dash_grid = grid
        self._dash_tile_descs: list[tuple[Any, Any]] = []
        tools = tools_for_ui()

        cols = 4
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="tiles")
        rows = (len(tools) + cols - 1) // cols
        for r in range(rows):
            grid.grid_rowconfigure(r, weight=1, uniform="tile_rows")

        for idx, (key, title, icon, desc) in enumerate(tools):
            r, c = divmod(idx, cols)
            palette = getattr(self, "_dash_palette_cycle", DASH_TILE_PALETTE)
            tile_bg, tile_hover = palette[idx % len(palette)]
            tile = ctk.CTkFrame(
                grid,
                fg_color=tile_bg,
                corner_radius=8,
                border_width=0,
            )
            tile.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            inner = ctk.CTkFrame(tile, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=10, pady=8)
            ctk.CTkLabel(
                inner,
                text=icon,
                font=ctk.CTkFont(size=18),
                text_color=DASH_TILE_TEXT,
                height=20,
            ).pack(anchor="w")
            ctk.CTkLabel(
                inner,
                text=title,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
                text_color=DASH_TILE_TEXT,
                height=18,
            ).pack(anchor="w", pady=(2, 0))
            desc_lbl = ctk.CTkLabel(
                inner,
                text=desc,
                font=ctk.CTkFont(size=10),
                text_color=DASH_TILE_MUTED,
                wraplength=140,
                justify="left",
                anchor="nw",
            )
            desc_lbl.pack(anchor="w", fill="x", pady=(0, 0))
            self._dash_tile_descs.append((tile, desc_lbl))
            btn = ctk.CTkButton(
                inner,
                text=t("app.open"),
                width=70,
                height=26,
                fg_color=DASH_TILE_BTN,
                hover_color=DASH_TILE_BTN_HOVER,
                text_color=DASH_TILE_BTN_TEXT,
                command=lambda k=key: self.open_tool(k),
            )
            btn.pack(anchor="w", pady=(6, 0))

            def _open(_event: Any = None, k: str = key) -> None:
                self.open_tool(k)

            def _tile_enter(_event: Any = None, bg=tile_hover, t=tile) -> None:
                t.configure(fg_color=bg)

            def _tile_leave(_event: Any = None, bg=tile_bg, t=tile) -> None:
                t.configure(fg_color=bg)

            for widget in (tile, inner):
                widget.bind("<Enter>", _tile_enter)
                widget.bind("<Leave>", _tile_leave)
                widget.bind("<Button-1>", _open)
            for child in inner.winfo_children():
                if child is btn:
                    continue
                try:
                    child.bind("<Button-1>", _open)
                    child.bind("<Enter>", _tile_enter)
                    child.bind("<Leave>", _tile_leave)
                except Exception:
                    pass

        def _on_grid_cfg(_event: Any = None) -> None:
            self.after(40, self._refresh_tile_wrap)

        grid.bind("<Configure>", _on_grid_cfg)
        self.after(80, self._fit_dashboard_window)
        self.after(200, self._fit_dashboard_window)

    def open_tool(self, key: str) -> None:
        self._stop_runner()
        self._current_tool = key
        if key != "anydesk":
            self._set_anydesk_topmost(False)
        self._clear_frame(self._header)
        self._clear_frame(self._content)
        self._clear_frame(self._action_bar)
        try:
            self._action_bar.pack_forget()
        except Exception:
            pass
        self._lift_startup_loading()

        try:
            self._header.pack_configure(padx=16, pady=(10, 2))
            self._content.pack_configure(fill="both", expand=True, padx=12, pady=4)
            # Jangan ubah ukuran jendela saat buka menu
            self.minsize(
                getattr(self, "_dash_min_w", 720),
                getattr(self, "_dash_min_h", 460),
            )
        except Exception:
            pass

        title = t(f"tool.{key}.title") if key in {k for k, _ in TOOL_DEFS} else key

        if key in ("speedtest", "dns"):
            self._hide_sysinfo_strip()
            ctk.CTkLabel(
                self._header,
                text=title,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=20),
                text_color=COLORS["text"],
            ).pack(side="left")
            if key == "speedtest":
                self._open_embedded_web_view("Speedtest", SPEEDTEST_URL, auto_start=True)
            else:
                self._open_embedded_web_view("DNS Test", DNS_LEAK_URL, auto_start=False)
            return

        if key == "ipscan":
            self._open_ip_scanner_view()
            return

        if key == "ping":
            self._open_ping_cards_view()
            return

        if key == "traceroute":
            self._open_traceroute_topo_view()
            return

        if key == "apps":
            self._open_apps_list_view()
            return

        if key == "security":
            self._open_security_check_view()
            return

        if key == "printer":
            auto_fix = bool(getattr(self, "_elevate_auto_fix_printer", False))
            self._elevate_auto_fix_printer = False
            self._open_printer_view(auto_fix=auto_fix)
            return

        if key == "scp":
            self._open_scp_view()
            return

        if key == "fixrdp":
            auto_fix = bool(getattr(self, "_elevate_auto_fix_rdp", False))
            self._elevate_auto_fix_rdp = False
            self._open_rdp_status_view(auto_fix=auto_fix)
            return

        if key == "refresh":
            auto_fix = bool(getattr(self, "_elevate_auto_fix_refresh", False))
            self._elevate_auto_fix_refresh = False
            self._open_network_view(auto_fix=auto_fix)
            return

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=title,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._build_sysinfo_bar(self._sysinfo_strip)

        # AnyDesk: Kirim/Kembali di bawah bar info + Always on Top
        if key == "anydesk":
            self._set_anydesk_topmost(True)
            controls = ctk.CTkFrame(self._content, fg_color="transparent")
            controls.pack(fill="x", pady=(0, 8))
            self._pack_inline_send_back(controls, side="right", height=36)
        elif key not in AUTO_RUN_TOOLS:
            self._set_anydesk_topmost(False)
            controls = ctk.CTkFrame(self._content, fg_color="transparent")
            controls.pack(fill="x", pady=(0, 8))
            self._build_tool_controls(key, controls)
        else:
            self._set_anydesk_topmost(False)

        self.console = ConsoleView(self._content)
        self.console.pack(fill="both", expand=True)

        # Action bar footer hanya untuk tool tanpa Kirim/Kembali inline
        if key not in INLINE_ACTION_TOOLS:
            self._action_bar.pack(fill="x", padx=12, pady=(0, 6), before=self._footer)
            ctk.CTkButton(
                self._action_bar,
                text=t("app.back"),
                width=120,
                height=36,
                fg_color=COLORS["danger"],
                hover_color=COLORS["danger_hover"],
                command=self._cancel_to_dashboard,
            ).pack(side="right", padx=(8, 0))

            if key in SEND_TOOLS:
                ctk.CTkButton(
                    self._action_bar,
                    text=t("app.send"),
                    width=120,
                    height=36,
                    fg_color=COLORS["accent"],
                    hover_color=COLORS["accent_dim"],
                    text_color=COLORS["on_accent"],
                    command=(
                        self._send_text_payload_to_telegram
                        if key in TEXT_SEND_TOOLS
                        else self._send_screenshot
                    ),
                ).pack(side="right")

        self._seed_console(key)

        if key in AUTO_RUN_TOOLS:
            # Langsung jalan setelah UI siap (tanpa tombol Jalankan)
            starters = {
                "anydesk": self._start_anydesk,
            }
            fn = starters.get(key)
            if fn:
                self.after(150, fn)

    def _pack_tool_action_bar(self, *, text_send: bool = False) -> None:
        self._action_bar.pack(fill="x", padx=12, pady=(0, 6), before=self._footer)
        ctk.CTkButton(
            self._action_bar,
            text=t("app.back"),
            width=120,
            height=36,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            self._action_bar,
            text=t("app.send"),
            width=120,
            height=36,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=(
                self._send_text_payload_to_telegram
                if text_send
                else self._send_screenshot
            ),
        ).pack(side="right")

    def _pack_inline_send_back(
        self,
        parent: ctk.CTkFrame,
        *,
        text_send: bool = False,
        height: int = 36,
        side: str = "left",
    ) -> None:
        """Tombol Kirim + Kembali di baris kontrol tool."""
        send_cmd = (
            self._send_text_payload_to_telegram if text_send else self._send_screenshot
        )
        if side == "right":
            ctk.CTkButton(
                parent,
                text=t("app.back"),
                width=100,
                height=height,
                fg_color=COLORS["danger"],
                hover_color=COLORS["danger_hover"],
                command=self._cancel_to_dashboard,
            ).pack(side="right", padx=(8, 0))
            ctk.CTkButton(
                parent,
                text=t("app.send"),
                width=100,
                height=height,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                command=send_cmd,
            ).pack(side="right", padx=(8, 0))
            return

        ctk.CTkButton(
            parent,
            text=t("app.send"),
            width=100,
            height=height,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=send_cmd,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            parent,
            text=t("app.back"),
            width=100,
            height=height,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="left", padx=(8, 0))

    def _open_apps_list_view(self) -> None:
        """Daftar aplikasi terinstall — icon, uninstall/reinstall, Kirim teks."""
        from modules.app_manage import AppActionRunner
        from modules.system_info import hostname as get_hostname
        from modules.win_icons import load_icon_photo
        from tkinter import ttk

        self.console = None
        self._apps_list = []
        self._apps_by_iid: dict[str, dict[str, str]] = {}
        self._app_icon_refs: list[Any] = []
        self._send_text_payload = ""

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=t("tool.apps.title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=24),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._build_sysinfo_bar(self._sysinfo_strip)

        summary = ctk.CTkFrame(
            self._content,
            fg_color=COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        summary.pack(fill="x", pady=(0, 12))
        sum_row = ctk.CTkFrame(summary, fg_color="transparent")
        sum_row.pack(fill="x", padx=16, pady=14)

        count_lbl = ctk.CTkLabel(
            sum_row,
            text=t("apps.loading"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=15),
            text_color=COLORS["text"],
            anchor="w",
        )
        count_lbl.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            sum_row,
            text=t("app.back"),
            width=100,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            sum_row,
            text=t("app.send"),
            width=100,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._send_text_payload_to_telegram,
        ).pack(side="right", padx=(8, 0))
        btn_refresh = ctk.CTkButton(
            sum_row,
            text=t("app.refresh"),
            width=100,
            height=32,
            fg_color=COLORS.get("warn", "#E6B422"),
            hover_color=COLORS.get("warn_hover", "#C99A12"),
            text_color="#1A1400",
        )
        btn_refresh.pack(side="right", padx=(8, 0))
        btn_uninstall = ctk.CTkButton(
            sum_row,
            text=t("apps.uninstall"),
            width=110,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
        )
        btn_uninstall.pack(side="right", padx=(8, 0))

        list_wrap = ctk.CTkFrame(
            self._content,
            fg_color=COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        list_wrap.pack(fill="both", expand=True, padx=0, pady=0)

        table_host = tk.Frame(list_wrap, bg=COLORS["panel"], highlightthickness=0)
        table_host.pack(fill="both", expand=True, padx=12, pady=(12, 4))

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Apps.Treeview",
            background=COLORS["bg"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["bg"],
            borderwidth=0,
            rowheight=34,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Apps.Treeview.Heading",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            borderwidth=0,
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Apps.Treeview",
            background=[("selected", COLORS["accent"])],
            foreground=[("selected", COLORS["on_accent"])],
        )

        cols = ("name", "version", "publisher")
        tree = ttk.Treeview(
            table_host,
            columns=cols,
            show="tree headings",
            style="Apps.Treeview",
            selectmode="browse",
        )
        tree.heading("#0", text="")
        tree.heading("name", text=t("apps.col.name"), anchor="w")
        tree.heading("version", text=t("apps.col.version"), anchor="w")
        tree.heading("publisher", text=t("apps.col.publisher"), anchor="w")
        tree.column("#0", width=40, minwidth=36, stretch=False, anchor="center")
        tree.column("name", width=340, minwidth=160, anchor="w", stretch=True)
        tree.column("version", width=110, minwidth=70, anchor="w", stretch=False)
        tree.column("publisher", width=220, minwidth=100, anchor="w", stretch=True)

        vsb = ttk.Scrollbar(table_host, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        table_host.grid_rowconfigure(0, weight=1)
        table_host.grid_columnconfigure(0, weight=1)
        tree.tag_configure("odd", background=COLORS["bg"])
        tree.tag_configure("even", background=COLORS["panel"])

        log_host = ctk.CTkFrame(
            self._content, fg_color=COLORS["console_bg"], height=110, corner_radius=8
        )
        log_host.pack(fill="x", pady=(8, 0))
        log_host.pack_propagate(False)
        self.console = ConsoleView(log_host)
        self.console.pack(fill="both", expand=True, padx=2, pady=2)

        def _selected_app() -> dict[str, str] | None:
            sel = tree.selection()
            if not sel:
                return None
            return self._apps_by_iid.get(sel[0])

        def _fill(apps: list[dict[str, str]]) -> None:
            self._apps_list = apps
            self._apps_by_iid = {}
            self._app_icon_refs = []
            host = get_hostname()
            self._send_text_payload = format_apps_text(apps, hostname=host)
            count_lbl.configure(text=t("apps.count", n=len(apps)))
            tree.delete(*tree.get_children())
            for idx, app in enumerate(apps):
                tag = "even" if idx % 2 == 0 else "odd"
                photo = None
                try:
                    photo = load_icon_photo(
                        app.get("icon", ""),
                        size=20,
                        install_location=app.get("install_location", ""),
                        uninstall=app.get("uninstall", "")
                        or app.get("quiet_uninstall", ""),
                        name=app.get("name", ""),
                    )
                except Exception:
                    photo = None
                if photo is not None:
                    self._app_icon_refs.append(photo)
                iid = tree.insert(
                    "",
                    "end",
                    text="",
                    image=photo if photo is not None else "",
                    values=(
                        app.get("name", "—"),
                        app.get("version", "—"),
                        app.get("publisher", "—"),
                    ),
                    tags=(tag,),
                )
                self._apps_by_iid[iid] = app

        def on_apps(apps: list[dict[str, str]]) -> None:
            self.after(0, lambda: _fill(apps))

        def on_error(msg: str) -> None:
            def ui() -> None:
                count_lbl.configure(text=t("apps.fail"))
                tree.delete(*tree.get_children())
                if self.console:
                    self.log(msg)

            self.after(0, ui)

        def load() -> None:
            count_lbl.configure(text=t("apps.loading"))
            tree.delete(*tree.get_children())
            InstalledAppsRunner(on_apps=on_apps, on_error=on_error).start()

        def _run_action(_action: str = "uninstall") -> None:
            app = _selected_app()
            if app is None:
                messagebox.showinfo(t("tool.apps.title"), t("apps.select"), parent=self)
                return
            name = app.get("name", "")
            if not messagebox.askyesno(
                t("tool.apps.title"),
                t("apps.confirm_uninstall", name=name),
                parent=self,
            ):
                return
            if self.console:
                self.console.clear()

            def done(_ok: bool) -> None:
                self.after(400, load)

            # Sama seperti Uninstall di Control Panel / Settings (UI uninstaller resmi)
            AppActionRunner("uninstall", app, on_line=self.log, on_done=done).start()

        def on_right(event: Any) -> None:
            row = tree.identify_row(event.y)
            if row:
                tree.selection_set(row)
                tree.focus(row)
            menu = tk.Menu(tree, tearoff=0)
            menu.add_command(label=t("apps.uninstall"), command=_run_action)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        tree.bind("<Button-3>", on_right)
        btn_uninstall.configure(command=_run_action)
        btn_refresh.configure(command=load)
        self.after(80, load)

    def _open_security_check_view(self) -> None:
        """Cek Firewall, Defender, Windows Update — kartu status."""
        from modules.system_info import hostname as get_hostname

        self.console = None
        self._security_items = []
        self._send_text_payload = ""

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=t("tool.security.title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=24),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._build_sysinfo_bar(self._sysinfo_strip)

        toolbar = ctk.CTkFrame(self._content, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 10))
        status_lbl = ctk.CTkLabel(
            toolbar,
            text=t("sec.checking"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["muted"],
            anchor="w",
        )
        status_lbl.pack(side="left", fill="x", expand=True)
        # Urutan kanan→kiri: Kembali, Kirim, Cek Ulang (kuning sebelum Kirim)
        ctk.CTkButton(
            toolbar,
            text=t("app.back"),
            width=100,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            toolbar,
            text=t("app.send"),
            width=100,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._send_screenshot,
        ).pack(side="right", padx=(8, 0))
        btn_refresh = ctk.CTkButton(
            toolbar,
            text=t("app.recheck"),
            width=110,
            height=32,
            fg_color=COLORS.get("warn", "#E6B422"),
            hover_color=COLORS.get("warn_hover", "#C99A12"),
            text_color=COLORS.get("on_warn", "#1A1400"),
        )
        btn_refresh.pack(side="right", padx=(8, 0))

        cards = ctk.CTkFrame(self._content, fg_color="transparent")
        cards.pack(fill="both", expand=True)

        def _status_color(ok: bool, status: str) -> tuple[str, str]:
            st = (status or "").upper()
            if st == "PUBLIC":
                return COLORS["danger"], COLORS["on_accent"]
            if ok and st in {"ON", "READY", "RUNNING", "ONLINE", "PRIVATE", "DOMAIN"}:
                return COLORS.get("ok", "#12B76A"), COLORS.get("on_ok", "#FFFFFF")
            if ok:
                return COLORS.get("ok", "#12B76A"), COLORS.get("on_ok", "#FFFFFF")
            if st in {"PARTIAL", "PENDING"}:
                return COLORS.get("warn", "#E6B422"), COLORS.get("on_warn", "#1A1400")
            return COLORS["danger"], COLORS["on_accent"]

        def _render(items: list[Any]) -> None:
            self._security_items = items
            host = get_hostname()
            self._send_text_payload = format_security_text(items, hostname=host)
            for w in list(cards.winfo_children()):
                try:
                    w.destroy()
                except Exception:
                    pass

            ok_count = sum(1 for it in items if it.get("ok"))
            status_lbl.configure(
                text=t("sec.result", ok=ok_count, total=len(items))
                if items
                else t("sec.none")
            )

            for item in items:
                card = ctk.CTkFrame(
                    cards,
                    fg_color=COLORS["panel"],
                    corner_radius=10,
                    border_width=1,
                    border_color=COLORS["border"],
                )
                card.pack(fill="x", pady=(0, 8))
                inner = ctk.CTkFrame(card, fg_color="transparent")
                inner.pack(fill="x", padx=14, pady=10)

                head = ctk.CTkFrame(inner, fg_color="transparent")
                head.pack(fill="x")

                ctk.CTkLabel(
                    head,
                    text=item.get("label", "—"),
                    font=ctk.CTkFont(family="Segoe UI Semibold", size=14),
                    text_color=COLORS["text"],
                    anchor="w",
                ).pack(side="left", fill="x", expand=True, padx=(0, 10))

                st = str(item.get("status", "UNKNOWN"))
                fg, on = _status_color(bool(item.get("ok")), st)
                # Pill kecil — teks di tengah via pack expand
                badge = ctk.CTkFrame(
                    head,
                    fg_color=fg,
                    corner_radius=6,
                    height=22,
                )
                badge.pack(side="right")
                badge.pack_propagate(False)
                lbl = ctk.CTkLabel(
                    badge,
                    text=st,
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color=on,
                    anchor="center",
                    justify="center",
                )
                lbl.pack(expand=True, fill="both", padx=10, pady=0)
                # Lebar mengikuti teks + padding
                try:
                    badge.update_idletasks()
                    tw = max(56, int(lbl.winfo_reqwidth()) + 20)
                    badge.configure(width=tw)
                except Exception:
                    badge.configure(width=72)

                detail = str(item.get("detail", "") or "").strip()
                if detail:
                    ctk.CTkLabel(
                        inner,
                        text=detail,
                        font=ctk.CTkFont(family="Segoe UI", size=12),
                        text_color=COLORS["muted"],
                        anchor="w",
                        justify="left",
                        wraplength=720,
                    ).pack(fill="x", pady=(6, 0))

        def on_result(items: list[Any]) -> None:
            self.after(0, lambda: _render(items))

        def on_error(msg: str) -> None:
            def ui() -> None:
                status_lbl.configure(text=t("sec.fail", msg=msg))
                for w in list(cards.winfo_children()):
                    try:
                        w.destroy()
                    except Exception:
                        pass
                ctk.CTkLabel(
                    cards,
                    text=msg,
                    font=ctk.CTkFont(family="Segoe UI", size=13),
                    text_color=COLORS["danger"],
                ).pack(pady=24)

            self.after(0, ui)

        def load() -> None:
            status_lbl.configure(text=t("sec.checking"))
            for w in list(cards.winfo_children()):
                try:
                    w.destroy()
                except Exception:
                    pass
            ctk.CTkLabel(
                cards,
                text=t("sec.wait"),
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=COLORS["muted"],
            ).pack(pady=24)
            SecurityCheckRunner(on_result=on_result, on_error=on_error).start()

        btn_refresh.configure(command=load)
        self.after(80, load)

    def _open_network_view(self, auto_fix: bool = False) -> None:
        """Adapter cards (ncpa.cpl-style) + Fix Network."""
        self.console = None

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=t("tool.refresh.title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=24),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._build_sysinfo_bar(self._sysinfo_strip)

        toolbar = ctk.CTkFrame(self._content, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 8))
        status_lbl = ctk.CTkLabel(
            toolbar,
            text=t("network.loading"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
        )
        status_lbl.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            toolbar,
            text=t("app.back"),
            width=100,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            toolbar,
            text=t("app.send"),
            width=100,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._send_screenshot,
        ).pack(side="right", padx=(8, 0))

        btn_reload = ctk.CTkButton(
            toolbar,
            text=t("app.refresh"),
            width=100,
            height=32,
            fg_color=COLORS.get("warn", "#E6B422"),
            hover_color=COLORS.get("warn_hover", "#C99A12"),
            text_color=COLORS.get("on_warn", "#1A1400"),
        )
        btn_reload.pack(side="right", padx=(8, 0))

        btn_fix = ctk.CTkButton(
            toolbar,
            text=t("network.fix"),
            width=130,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
        )
        btn_fix.pack(side="right", padx=(8, 0))

        grid = ctk.CTkScrollableFrame(self._content, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        cols = 4
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="net_cards")

        log_host = ctk.CTkFrame(
            self._content, fg_color=COLORS["console_bg"], height=110, corner_radius=8
        )
        log_host.pack(fill="x", pady=(8, 0))
        log_host.pack_propagate(False)
        self.console = ConsoleView(log_host)
        self.console.pack(fill="both", expand=True, padx=2, pady=2)

        card_widgets: list[ctk.CTkFrame] = []

        def _status_color(st: str) -> str:
            low = (st or "").lower()
            if low == "up":
                return COLORS.get("ok", "#12B76A")
            if low in ("disconnected", "disabled", "down", "not present"):
                return COLORS.get("danger", "#C42B1C")
            return COLORS.get("warn", "#E6B422")

        def _fill(rows: list[dict[str, str]]) -> None:
            for w in card_widgets:
                try:
                    w.destroy()
                except Exception:
                    pass
            card_widgets.clear()
            if not rows:
                status_lbl.configure(text=t("network.empty"))
                return
            status_lbl.configure(text=t("network.count", n=len(rows)))
            text_fg = COLORS["text"]
            muted_fg = COLORS["muted"]
            for idx, row in enumerate(rows):
                r, c = divmod(idx, cols)
                st = row.get("status") or "—"
                st_low = st.lower()
                disabled = st_low in (
                    "disabled",
                    "disconnected",
                    "down",
                    "not present",
                )
                if disabled:
                    card_bg = COLORS.get("border", "#3A3A3A")
                    name_col = muted_fg
                    border_col = muted_fg
                else:
                    card_bg = COLORS["panel"]
                    name_col = text_fg
                    border_col = COLORS["border"]

                card = ctk.CTkFrame(
                    grid,
                    fg_color=card_bg,
                    corner_radius=10,
                    border_width=1,
                    border_color=border_col,
                    height=86,
                )
                card.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
                card.grid_propagate(False)
                card_widgets.append(card)

                inner = ctk.CTkFrame(card, fg_color="transparent")
                inner.pack(fill="both", expand=True, padx=10, pady=8)

                head = ctk.CTkFrame(inner, fg_color="transparent")
                head.pack(fill="x")
                name_l = (row.get("name") or "").lower()
                desc_l = (row.get("desc") or "").lower()
                if "wi-fi" in name_l or "wifi" in name_l or "wireless" in desc_l:
                    ic = "📶"
                elif "ethernet" in name_l or "ethernet" in desc_l:
                    ic = "🔌"
                else:
                    ic = "🖧"
                ctk.CTkLabel(
                    head,
                    text=ic,
                    font=ctk.CTkFont(size=14),
                    text_color=COLORS["accent"] if not disabled else muted_fg,
                    width=22,
                ).pack(side="left")
                ctk.CTkLabel(
                    head,
                    text=row.get("name") or "—",
                    font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
                    text_color=name_col,
                    anchor="w",
                ).pack(side="left", fill="x", expand=True, padx=(4, 6))
                dot = ctk.CTkFrame(
                    head,
                    width=14,
                    height=14,
                    corner_radius=7,
                    fg_color=_status_color(st),
                )
                dot.pack(side="right")
                dot.pack_propagate(False)

                speed = row.get("speed") or "—"
                ctk.CTkLabel(
                    inner,
                    text=f"{st} · {speed}",
                    font=ctk.CTkFont(family="Segoe UI", size=10),
                    text_color=_status_color(st),
                    anchor="w",
                ).pack(anchor="w", fill="x", pady=(2, 0))
                mac = row.get("mac") or "—"
                ctk.CTkLabel(
                    inner,
                    text=mac,
                    font=ctk.CTkFont(family="Consolas", size=10),
                    text_color=muted_fg,
                    anchor="w",
                ).pack(anchor="w", fill="x", pady=(2, 0))

                def _bind_adapter_menu(widget: Any, adapter: dict[str, str]) -> None:
                    def on_right(event: Any, ad=adapter) -> str:
                        menu = tk.Menu(self, tearoff=0)
                        menu.add_command(
                            label=t("network.status"),
                            command=lambda: _adapter_action("status", ad),
                        )
                        menu.add_separator()
                        menu.add_command(
                            label=t("network.enable"),
                            command=lambda: _adapter_action("enable", ad),
                        )
                        menu.add_command(
                            label=t("network.disable"),
                            command=lambda: _adapter_action("disable", ad),
                        )
                        menu.add_separator()
                        menu.add_command(
                            label=t("network.properties"),
                            command=lambda: _adapter_action("properties", ad),
                        )
                        try:
                            menu.tk_popup(event.x_root, event.y_root)
                        finally:
                            menu.grab_release()
                        return "break"

                    widget.bind("<Button-3>", on_right)
                    for child in widget.winfo_children():
                        try:
                            child.bind("<Button-3>", on_right)
                            for gchild in child.winfo_children():
                                try:
                                    gchild.bind("<Button-3>", on_right)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                def _bind_adapter_hover(
                    card_w: Any, base_bg: str, base_border: str, *, dimmed: bool
                ) -> None:
                    if dimmed:
                        hover_bg = COLORS.get("muted", base_bg)
                        hover_border = COLORS.get("danger", base_border)
                    else:
                        hover_bg = COLORS.get("tile_hover", COLORS["border"])
                        hover_border = COLORS["accent"]

                    def on_enter(_e: Any = None, c=card_w, bg=hover_bg, bd=hover_border) -> None:
                        try:
                            c.configure(fg_color=bg, border_color=bd)
                        except Exception:
                            pass

                    def on_leave(_e: Any = None, c=card_w, bg=base_bg, bd=base_border) -> None:
                        try:
                            c.configure(fg_color=bg, border_color=bd)
                        except Exception:
                            pass

                    card_w.bind("<Enter>", on_enter)
                    card_w.bind("<Leave>", on_leave)
                    for child in card_w.winfo_children():
                        try:
                            child.bind("<Enter>", on_enter)
                            child.bind("<Leave>", on_leave)
                            for gchild in child.winfo_children():
                                try:
                                    gchild.bind("<Enter>", on_enter)
                                    gchild.bind("<Leave>", on_leave)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                _bind_adapter_menu(card, row)
                _bind_adapter_hover(card, card_bg, border_col, dimmed=disabled)

        def _show_adapter_status(adapter: dict[str, str]) -> None:
            name = adapter.get("name") or "—"
            details = get_adapter_details(name) or adapter
            ipv4 = details.get("ipv4") or "—"
            if details.get("prefix"):
                ipv4 = f"{ipv4}/{details.get('prefix')}"
            rows = [
                (t("network.info.name"), details.get("name") or name),
                (
                    t("network.info.status"),
                    details.get("status") or adapter.get("status") or "—",
                ),
                (
                    t("network.info.desc"),
                    details.get("desc") or adapter.get("desc") or "—",
                ),
                (
                    t("network.info.mac"),
                    details.get("mac") or adapter.get("mac") or "—",
                ),
                (
                    t("network.info.speed"),
                    details.get("speed") or adapter.get("speed") or "—",
                ),
                (t("network.info.media"), details.get("media") or "—"),
                (t("network.info.ipv4"), ipv4),
                (t("network.info.gateway"), details.get("gateway") or "—"),
                (t("network.info.dns"), details.get("dns") or "—"),
                ("ifIndex", details.get("ifindex") or "—"),
            ]

            # Tinggi otomatis: header + baris + footer (tanpa scrollbar)
            dlg_w = 520
            row_h = 36
            dlg_h = 56 + 28 + (len(rows) * row_h) + 64 + 28
            dlg = ctk.CTkToplevel(self)
            dlg.title(t("network.status"))
            dlg.geometry(f"{dlg_w}x{dlg_h}")
            dlg.minsize(dlg_w, dlg_h)
            dlg.resizable(False, False)
            dlg.configure(fg_color=COLORS["bg"])
            dlg.transient(self)
            dlg.attributes("-topmost", True)
            self.update_idletasks()
            px = self.winfo_rootx() + (self.winfo_width() - dlg_w) // 2
            py = self.winfo_rooty() + (self.winfo_height() - dlg_h) // 2
            dlg.geometry(f"{dlg_w}x{dlg_h}+{max(px, 40)}+{max(py, 40)}")

            flash = ctk.CTkFrame(
                dlg, fg_color=COLORS["accent"], height=6, corner_radius=0
            )
            flash.pack(fill="x", side="top")

            frame = ctk.CTkFrame(
                dlg,
                fg_color=COLORS["panel"],
                corner_radius=14,
                border_width=2,
                border_color=COLORS["accent"],
            )
            frame.pack(fill="both", expand=True, padx=12, pady=12)

            footer = ctk.CTkFrame(frame, fg_color="transparent", height=52)
            footer.pack(fill="x", side="bottom", padx=12, pady=(4, 12))
            footer.pack_propagate(False)

            body = ctk.CTkFrame(frame, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=8, pady=(8, 0))

            ctk.CTkLabel(
                body,
                text=t("network.status"),
                font=ctk.CTkFont(family="Segoe UI Semibold", size=18),
                text_color=COLORS["text"],
                anchor="w",
            ).pack(fill="x", padx=14, pady=(4, 8))

            grid = ctk.CTkFrame(body, fg_color="transparent")
            grid.pack(fill="both", expand=True, padx=6, pady=(0, 4))
            grid.grid_columnconfigure(0, weight=0, minsize=100)
            grid.grid_columnconfigure(1, weight=1)

            for i, (label, value) in enumerate(rows):
                ctk.CTkLabel(
                    grid,
                    text=label,
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color=COLORS["muted"],
                    anchor="w",
                ).grid(row=i, column=0, sticky="w", padx=(8, 10), pady=3)
                val_box = ctk.CTkEntry(
                    grid,
                    font=ctk.CTkFont(family="Consolas", size=12),
                    fg_color=COLORS["bg"],
                    border_color=COLORS["border"],
                    text_color=COLORS["text"],
                    height=28,
                )
                val_box.grid(row=i, column=1, sticky="ew", padx=(0, 8), pady=3)
                val_box.insert(0, value or "—")
                val_box.configure(state="readonly")

            tip = ctk.CTkLabel(
                footer,
                text="",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=COLORS["accent"],
                anchor="w",
            )

            def _copy_all() -> None:
                text = "\n".join(f"{k}: {v}" for k, v in rows)
                try:
                    self.clipboard_clear()
                    self.clipboard_append(text)
                    tip.configure(text=t("network.info.copied"))
                except Exception:
                    tip.configure(text="Copy gagal.")

            # Salin semua biru → Tutup merah
            ctk.CTkButton(
                footer,
                text=t("network.info.copy"),
                width=130,
                height=40,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                corner_radius=10,
                command=_copy_all,
            ).pack(side="left", pady=6)
            tip.pack(side="left", fill="x", expand=True, padx=(10, 8))
            ctk.CTkButton(
                footer,
                text=t("network.info.close"),
                width=110,
                height=40,
                fg_color=COLORS["danger"],
                hover_color=COLORS["danger_hover"],
                text_color="#FFFFFF",
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                corner_radius=10,
                command=dlg.destroy,
            ).pack(side="right", pady=6)

            dlg.after(80, dlg.lift)
            dlg.after(100, dlg.focus_force)

        def _adapter_action(kind: str, adapter: dict[str, str]) -> None:
            name = adapter.get("name") or ""
            if not name:
                return
            if kind == "status":
                _show_adapter_status(adapter)
                return
            if kind == "properties":
                ok, msg = open_adapter_properties(name)
                self.log(msg)
                return
            resume = "enable_adapter" if kind == "enable" else "disable_adapter"
            if not self._ensure_admin_for(
                "refresh", resume_action=resume, resume_payload=name
            ):
                return
            if self.console:
                self.console.clear()
            self.log(f"{'Enable' if kind == 'enable' else 'Disable'} adapter: {name}")

            def worker() -> None:
                ok, msg = set_adapter_enabled(name, kind == "enable")
                self.after(0, lambda: self.log(msg))
                self.after(400, load)

            threading.Thread(target=worker, daemon=True).start()

        def load() -> None:
            status_lbl.configure(text=t("network.loading"))

            def worker() -> None:
                rows = list_net_adapters()
                self.after(0, lambda: _fill(rows))

            threading.Thread(target=worker, daemon=True).start()

        def run_fix() -> None:
            if not self._ensure_admin_for("refresh", resume_action="fix"):
                return
            self._stop_runner()
            if self.console:
                self.console.clear()
            status_lbl.configure(text=t("network.fixing"))
            RefreshNetworkRunner(
                NETWORK_ADAPTER,
                on_line=self.log,
                on_done=lambda: self.after(
                    0,
                    lambda: (
                        self._notify_tool_done("done.refresh"),
                        self.after(400, load),
                    ),
                ),
            ).start()

        btn_reload.configure(command=load)
        btn_fix.configure(command=run_fix)

        pending_net = getattr(self, "_elevate_network_action", None)
        self._elevate_network_action = None
        if pending_net:
            act, name = pending_net
            self.after(80, load)

            def resume_net() -> None:
                if not name:
                    return
                kind = "enable" if act == "enable_adapter" else "disable"
                _adapter_action(kind, {"name": name})

            self.after(600, resume_net)
        else:
            self.after(80, load)
        if auto_fix:
            self.after(250, run_fix)

    def _open_printer_view(self, auto_fix: bool = False) -> None:
        """Daftar driver printer + tombol Fix Printer / Refresh / Kembali."""
        from tkinter import ttk

        from modules.printer_info import PrinterDriverActionRunner, PrinterDriversRunner

        self.console = None
        self._printer_by_iid: dict[str, dict[str, str]] = {}

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=t("tool.printer.title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=24),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._build_sysinfo_bar(self._sysinfo_strip)

        toolbar = ctk.CTkFrame(self._content, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 8))
        status_lbl = ctk.CTkLabel(
            toolbar,
            text=t("printer.loading"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
        )
        status_lbl.pack(side="left", fill="x", expand=True)

        # Kanan → kiri pack: Kembali, Kirim, Refresh, Fix  =>  Fix | Refresh | Kirim | Kembali
        ctk.CTkButton(
            toolbar,
            text=t("app.back"),
            width=100,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            toolbar,
            text=t("app.send"),
            width=100,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._send_screenshot,
        ).pack(side="right", padx=(8, 0))

        btn_refresh = ctk.CTkButton(
            toolbar,
            text=t("app.refresh"),
            width=100,
            height=32,
            fg_color=COLORS.get("warn", "#E6B422"),
            hover_color=COLORS.get("warn_hover", "#C99A12"),
            text_color=COLORS.get("on_warn", "#1A1400"),
        )
        btn_refresh.pack(side="right", padx=(8, 0))

        btn_fix = ctk.CTkButton(
            toolbar,
            text=t("printer.fix"),
            width=120,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
        )
        btn_fix.pack(side="right", padx=(8, 0))

        btn_reinstall = ctk.CTkButton(
            toolbar,
            text=t("printer.reinstall"),
            width=100,
            height=32,
            fg_color=COLORS.get("warn", "#E6B422"),
            hover_color=COLORS.get("warn_hover", "#C99A12"),
            text_color=COLORS.get("on_warn", "#1A1400"),
        )
        btn_reinstall.pack(side="right", padx=(8, 0))

        btn_uninstall = ctk.CTkButton(
            toolbar,
            text=t("printer.uninstall"),
            width=100,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
        )
        btn_uninstall.pack(side="right", padx=(8, 0))

        list_wrap = ctk.CTkFrame(
            self._content,
            fg_color=COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        list_wrap.pack(fill="both", expand=True)

        table_host = tk.Frame(list_wrap, bg=COLORS["panel"], highlightthickness=0)
        table_host.pack(fill="both", expand=True, padx=12, pady=12)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Printer.Treeview",
            background=COLORS["bg"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["bg"],
            borderwidth=0,
            rowheight=30,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Printer.Treeview.Heading",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            borderwidth=0,
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Printer.Treeview",
            background=[("selected", COLORS["accent"])],
            foreground=[("selected", COLORS["on_accent"])],
        )

        cols = ("name", "manufacturer", "environment", "version")
        tree = ttk.Treeview(
            table_host,
            columns=cols,
            show="headings",
            style="Printer.Treeview",
            selectmode="browse",
        )
        tree.heading("name", text=t("printer.col.name"), anchor="w")
        tree.heading("manufacturer", text=t("printer.col.mfr"), anchor="w")
        tree.heading("environment", text=t("printer.col.env"), anchor="w")
        tree.heading("version", text=t("printer.col.ver"), anchor="w")
        tree.column("name", width=280, minwidth=140, anchor="w", stretch=True)
        tree.column("manufacturer", width=160, minwidth=100, anchor="w", stretch=True)
        tree.column("environment", width=140, minwidth=90, anchor="w", stretch=False)
        tree.column("version", width=70, minwidth=50, anchor="w", stretch=False)

        vsb = ttk.Scrollbar(table_host, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        table_host.grid_rowconfigure(0, weight=1)
        table_host.grid_columnconfigure(0, weight=1)
        tree.tag_configure("odd", background=COLORS["bg"])
        tree.tag_configure("even", background=COLORS["panel"])

        log_host = ctk.CTkFrame(
            self._content, fg_color=COLORS["console_bg"], height=130, corner_radius=8
        )
        log_host.pack(fill="x", pady=(8, 0))
        log_host.pack_propagate(False)
        self.console = ConsoleView(log_host)
        self.console.pack(fill="both", expand=True, padx=2, pady=2)

        def _fill(rows: list[dict[str, str]]) -> None:
            self._printer_by_iid = {}
            tree.delete(*tree.get_children())
            if not rows:
                status_lbl.configure(text=t("printer.empty"))
                return
            status_lbl.configure(text=t("printer.count", n=len(rows)))
            for idx, row in enumerate(rows):
                tag = "even" if idx % 2 == 0 else "odd"
                iid = tree.insert(
                    "",
                    "end",
                    values=(
                        row.get("name", "—"),
                        row.get("manufacturer", "—"),
                        row.get("environment", "—"),
                        row.get("version", "—"),
                    ),
                    tags=(tag,),
                )
                self._printer_by_iid[iid] = row

        def on_drivers(rows: list[dict[str, str]]) -> None:
            self.after(0, lambda: _fill(rows))

        def on_error(msg: str) -> None:
            def ui() -> None:
                status_lbl.configure(text=t("printer.fail"))
                tree.delete(*tree.get_children())
                self.log(msg)

            self.after(0, ui)

        def load() -> None:
            status_lbl.configure(text=t("printer.loading"))
            tree.delete(*tree.get_children())
            PrinterDriversRunner(on_drivers=on_drivers, on_error=on_error).start()

        def run_fix() -> None:
            if not self._ensure_admin_for("printer", resume_action="fix"):
                return
            self._stop_runner()
            if self.console:
                self.console.clear()
            status_lbl.configure(text=t("printer.fixing"))

            def after_fix() -> None:
                self._notify_tool_done("done.printer")
                self.after(200, load)

            FixPrinterRunner(
                on_line=self.log,
                on_done=lambda: self.after(0, after_fix),
            ).start()

        def _selected_driver() -> dict[str, str] | None:
            sel = tree.selection()
            if not sel:
                return None
            return self._printer_by_iid.get(sel[0])

        def _run_driver_action(
            action: str,
            drv: dict[str, str] | None = None,
            *,
            skip_confirm: bool = False,
        ) -> None:
            if drv is None:
                drv = _selected_driver()
            if drv is None:
                messagebox.showinfo(t("tool.printer.title"), t("printer.select"), parent=self)
                return
            name = drv.get("name", "")
            if action == "uninstall":
                if not skip_confirm and not messagebox.askyesno(
                    t("tool.printer.title"),
                    t("printer.confirm_uninstall", name=name),
                    parent=self,
                ):
                    return
                resume = "uninstall_driver"
            else:
                if not skip_confirm and not messagebox.askyesno(
                    t("tool.printer.title"),
                    t("printer.confirm_reinstall", name=name),
                    parent=self,
                ):
                    return
                resume = "reinstall_driver"
            import json as _json

            payload = _json.dumps(drv, ensure_ascii=False)
            if not self._ensure_admin_for(
                "printer", resume_action=resume, resume_payload=payload
            ):
                return
            if self.console:
                self.console.clear()
            status_lbl.configure(
                text=t("printer.uninstalling") if action == "uninstall" else t("printer.reinstalling")
            )

            def done(_ok: bool) -> None:
                self.after(300, load)

            PrinterDriverActionRunner(
                action, drv, on_line=self.log, on_done=done
            ).start()

        def on_right(event: Any) -> None:
            row = tree.identify_row(event.y)
            if row:
                tree.selection_set(row)
                tree.focus(row)
            menu = tk.Menu(tree, tearoff=0)
            menu.add_command(
                label=t("printer.uninstall"),
                command=lambda: _run_driver_action("uninstall"),
            )
            menu.add_command(
                label=t("printer.reinstall"),
                command=lambda: _run_driver_action("reinstall"),
            )
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        tree.bind("<Button-3>", on_right)
        btn_refresh.configure(command=load)
        btn_fix.configure(command=run_fix)
        btn_uninstall.configure(command=lambda: _run_driver_action("uninstall"))
        btn_reinstall.configure(command=lambda: _run_driver_action("reinstall"))

        pending = getattr(self, "_elevate_printer_action", None)
        self._elevate_printer_action = None
        if pending:
            act, payload = pending
            import json as _json

            try:
                drv = _json.loads(payload) if payload else {}
            except Exception:
                drv = {}
            self.after(350, load)
            if act == "fix":

                def resume_fix() -> None:
                    if self.console:
                        self.console.clear()
                    status_lbl.configure(text=t("printer.fixing"))

                    def after_fix() -> None:
                        self._notify_tool_done("done.printer")
                        self.after(200, load)

                    FixPrinterRunner(
                        on_line=self.log,
                        on_done=lambda: self.after(0, after_fix),
                    ).start()

                self.after(900, resume_fix)
            elif isinstance(drv, dict) and drv.get("name"):
                action = "uninstall" if act == "uninstall_driver" else "reinstall"
                self.after(
                    900,
                    lambda a=action, d=drv: _run_driver_action(
                        a, d, skip_confirm=True
                    ),
                )
        elif auto_fix:
            # UAC dari Fix Printer — langsung clear spooler
            self.after(350, load)
            self.after(900, run_fix)
        else:
            self.after(80, load)

    def _open_scp_view(self) -> None:
        """SFTP/SSH explorer: form koneksi + file manager + perintah remote."""
        from modules.scp_panel import ScpPanel

        self.console = None
        self._hide_sysinfo_strip()
        panel = ScpPanel(
            self,
            self._header,
            self._content,
            COLORS,
            on_back=self._cancel_to_dashboard,
        )
        self._scp_panel = panel

    def _open_rdp_status_view(self, auto_fix: bool = False) -> None:
        """Kartu status RDP Server-App1..App8 + tombol Fix RDP."""
        from modules.rdp_check import MultiHostRdpRunner

        self.console = None
        self._rdp_card_widgets: dict[str, dict[str, Any]] = {}

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=t("tool.fixrdp.title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._build_sysinfo_bar(self._sysinfo_strip)

        toolbar = ctk.CTkFrame(self._content, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 6))
        status_lbl = ctk.CTkLabel(
            toolbar,
            text=t("rdp.checking"),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["muted"],
            anchor="w",
        )
        status_lbl.pack(side="left", fill="x", expand=True)

        # Kanan → kiri: Kembali, Kirim, Refresh, Fix RDP
        ctk.CTkButton(
            toolbar,
            text=t("app.back"),
            width=100,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            toolbar,
            text=t("app.send"),
            width=100,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._send_screenshot,
        ).pack(side="right", padx=(8, 0))

        btn_refresh = ctk.CTkButton(
            toolbar,
            text=t("app.refresh"),
            width=100,
            height=32,
            fg_color=COLORS.get("warn", "#E6B422"),
            hover_color=COLORS.get("warn_hover", "#C99A12"),
            text_color=COLORS.get("on_warn", "#1A1400"),
        )
        btn_refresh.pack(side="right", padx=(8, 0))

        btn_fix = ctk.CTkButton(
            toolbar,
            text=t("rdp.fix"),
            width=110,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
        )
        btn_fix.pack(side="right", padx=(8, 0))

        grid = ctk.CTkScrollableFrame(self._content, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        cols = 4
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="rdp_cards")

        card_bg = COLORS["panel"]
        card_border = COLORS["border"]
        idle_dot = "#9CA3AF"
        online_dot = COLORS.get("ok", "#12B76A")
        offline_dot = COLORS.get("danger", "#C42B1C")
        text_fg = COLORS["text"]
        muted_fg = COLORS["muted"]

        app_hosts = [
            h
            for h in HOSTS
            if str(h.get("name") or "").lower().startswith("server-app")
        ]
        # Urut App1..App8 berdasarkan angka jika ada
        def _app_key(h: dict[str, str]) -> int:
            name = str(h.get("name") or "")
            digits = "".join(ch for ch in name if ch.isdigit())
            return int(digits) if digits else 999

        app_hosts = sorted(app_hosts, key=_app_key)

        targets: list[tuple[str, str, str]] = []
        for idx, host in enumerate(app_hosts):
            name = str(host.get("name") or f"Server-App{idx + 1}")
            raw_ip = str(host.get("ip") or "")
            disp_name, ip = resolve_target_ip(name, raw_ip)
            host_id = f"{idx}:{disp_name}"
            ip_show = ip or raw_ip or "—"
            if ip:
                targets.append((host_id, disp_name, ip))

            r, c = divmod(idx, cols)
            card = ctk.CTkFrame(
                grid,
                fg_color=card_bg,
                corner_radius=10,
                border_width=1,
                border_color=card_border,
                height=86,
            )
            card.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            card.grid_propagate(False)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=10, pady=8)

            head = ctk.CTkFrame(inner, fg_color="transparent")
            head.pack(fill="x")
            ctk.CTkLabel(
                head,
                text="🖥",
                font=ctk.CTkFont(size=14),
                text_color=COLORS["accent"],
                width=22,
            ).pack(side="left")
            ctk.CTkLabel(
                head,
                text=disp_name,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
                text_color=text_fg,
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=(4, 6))
            dot = ctk.CTkFrame(
                head,
                width=14,
                height=14,
                corner_radius=7,
                fg_color=offline_dot if not ip else idle_dot,
            )
            dot.pack(side="right")
            dot.pack_propagate(False)

            ctk.CTkLabel(
                inner,
                text=ip_show,
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color=muted_fg,
                anchor="w",
            ).pack(anchor="w", fill="x", pady=(2, 0))
            st_lbl = ctk.CTkLabel(
                inner,
                text=t("rdp.wait") if ip else "IP tidak valid",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=muted_fg if ip else offline_dot,
                anchor="w",
            )
            st_lbl.pack(anchor="w", fill="x", pady=(2, 0))

            self._rdp_card_widgets[host_id] = {
                "status": st_lbl,
                "dot": dot,
                "ok": None,
            }

        log_host = ctk.CTkFrame(
            self._content, fg_color=COLORS["console_bg"], height=130, corner_radius=8
        )
        log_host.pack(fill="x", pady=(8, 0))
        log_host.pack_propagate(False)
        self.console = ConsoleView(log_host)
        self.console.pack(fill="both", expand=True, padx=2, pady=2)

        online_n = 0
        offline_n = 0
        runner_holder: dict[str, Any] = {"runner": None}

        def _apply_status(host_id: str, ok: bool, status: str) -> None:
            nonlocal online_n, offline_n
            w = self._rdp_card_widgets.get(host_id)
            if not w:
                return
            prev = w.get("ok")
            w["ok"] = ok
            w["status"].configure(
                text=status,
                text_color=online_dot if ok else offline_dot,
            )
            w["dot"].configure(fg_color=online_dot if ok else offline_dot)
            if prev is True:
                online_n = max(0, online_n - 1)
            elif prev is False:
                offline_n = max(0, offline_n - 1)
            if ok:
                online_n += 1
            else:
                offline_n += 1
            status_lbl.configure(
                text=t(
                    "rdp.summary",
                    ok=online_n,
                    bad=offline_n,
                    total=len(self._rdp_card_widgets),
                )
            )

        def on_status(host_id: str, ok: bool, status: str) -> None:
            self.after(
                0,
                lambda hid=host_id, o=ok, st=status: _apply_status(hid, o, st),
            )

        def start_checks() -> None:
            nonlocal online_n, offline_n
            old = runner_holder.get("runner")
            if old is not None:
                try:
                    old.stop()
                except Exception:
                    pass
            online_n = 0
            offline_n = 0
            for w in self._rdp_card_widgets.values():
                w["ok"] = None
                w["dot"].configure(fg_color=idle_dot)
                w["status"].configure(text=t("rdp.wait"), text_color=muted_fg)
            if not targets:
                status_lbl.configure(text=t("rdp.no_hosts"))
                return
            status_lbl.configure(text=t("rdp.checking"))
            runner = MultiHostRdpRunner(targets, on_status=on_status)
            runner_holder["runner"] = runner
            self.set_runner_stop(runner.stop)
            runner.start()

        def run_fix() -> None:
            if not self._ensure_admin_for("fixrdp"):
                return
            if self.console:
                self.console.clear()
            status_lbl.configure(text=t("rdp.fixing"))
            FixRdpRunner(
                on_line=self.log,
                on_done=lambda: self._notify_tool_done("done.fixrdp"),
            ).start()

        btn_refresh.configure(command=start_checks)
        btn_fix.configure(command=run_fix)
        self.after(80, start_checks)
        if auto_fix:
            self.after(250, run_fix)

    def _ping_host_icon(self, name: str) -> str:
        low = (name or "").lower()
        if "internet" in low:
            return "🌐"
        if "gateway" in low:
            return "📡"
        if "vpn" in low:
            return "🔒"
        if "db" in low:
            return "🗄"
        if "app" in low:
            return "🖥"
        return "●"

    def _open_ping_cards_view(self) -> None:
        """Ping semua host di daftar — kartu compact + bulatan status hijau/merah."""
        self.console = None
        self._ping_card_widgets: dict[str, dict[str, Any]] = {}

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=t("tool.ping.title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._build_sysinfo_bar(self._sysinfo_strip)

        toolbar = ctk.CTkFrame(self._content, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 6))
        status_lbl = ctk.CTkLabel(
            toolbar,
            text="Memulai ping ke semua host…",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["muted"],
            anchor="w",
        )
        status_lbl.pack(side="left", fill="x", expand=True)
        self._pack_inline_send_back(toolbar, text_send=False, height=30, side="right")

        grid = ctk.CTkScrollableFrame(self._content, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        cols = 4
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="ping_cards")

        card_bg = COLORS["panel"]
        card_border = COLORS["border"]
        idle_dot = "#9CA3AF"
        online_dot = COLORS.get("ok", "#12B76A")
        offline_dot = COLORS.get("danger", "#C42B1C")
        text_fg = COLORS["text"]
        muted_fg = COLORS["muted"]

        targets: list[tuple[str, str, str]] = []
        for idx, host in enumerate(HOSTS):
            name = str(host.get("name") or f"Host {idx + 1}")
            raw_ip = str(host.get("ip") or "")
            disp_name, ip = resolve_target_ip(name, raw_ip)
            host_id = f"{idx}:{disp_name}"
            ip_show = ip or ("—" if raw_ip == "auto" else raw_ip)
            if ip:
                targets.append((host_id, disp_name, ip))

            r, c = divmod(idx, cols)
            card = ctk.CTkFrame(
                grid,
                fg_color=card_bg,
                corner_radius=10,
                border_width=1,
                border_color=card_border,
                height=86,
            )
            card.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            card.grid_propagate(False)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=10, pady=8)

            head = ctk.CTkFrame(inner, fg_color="transparent")
            head.pack(fill="x")

            icon_lbl = ctk.CTkLabel(
                head,
                text=self._ping_host_icon(disp_name),
                font=ctk.CTkFont(size=14),
                text_color=COLORS["accent"],
                width=22,
            )
            icon_lbl.pack(side="left")

            name_lbl = ctk.CTkLabel(
                head,
                text=disp_name,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
                text_color=text_fg,
                anchor="w",
            )
            name_lbl.pack(side="left", fill="x", expand=True, padx=(4, 6))

            # Bulatan status (abu = menunggu, hijau = online, merah = RTO)
            dot = ctk.CTkFrame(
                head,
                width=14,
                height=14,
                corner_radius=7,
                fg_color=offline_dot if not ip else idle_dot,
            )
            dot.pack(side="right")
            dot.pack_propagate(False)

            ip_lbl = ctk.CTkLabel(
                inner,
                text=ip_show,
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color=muted_fg,
                anchor="w",
            )
            ip_lbl.pack(anchor="w", fill="x", pady=(2, 0))

            st_lbl = ctk.CTkLabel(
                inner,
                text="Menunggu…" if ip else "Gateway tidak terdeteksi",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=muted_fg if ip else offline_dot,
                anchor="w",
            )
            st_lbl.pack(anchor="w", fill="x", pady=(2, 0))

            self._ping_card_widgets[host_id] = {
                "card": card,
                "icon": icon_lbl,
                "name": name_lbl,
                "ip": ip_lbl,
                "status": st_lbl,
                "dot": dot,
                "ip_value": ip_show,
            }

        online_n = 0
        offline_n = 0

        def _apply_status(host_id: str, ok: bool, status: str) -> None:
            nonlocal online_n, offline_n
            w = self._ping_card_widgets.get(host_id)
            if not w:
                return
            prev = w.get("ok")
            w["ok"] = ok
            w["status"].configure(
                text=status,
                text_color=online_dot if ok else offline_dot,
            )
            w["dot"].configure(fg_color=online_dot if ok else offline_dot)

            if prev is True:
                online_n = max(0, online_n - 1)
            elif prev is False:
                offline_n = max(0, offline_n - 1)
            if ok:
                online_n += 1
            else:
                offline_n += 1
            status_lbl.configure(
                text=f"Online: {online_n}  ·  Timeout: {offline_n}  ·  Total: {len(self._ping_card_widgets)}"
            )

        def on_status(host_id: str, ok: bool, status: str) -> None:
            self.after(
                0,
                lambda hid=host_id, o=ok, st=status: _apply_status(hid, o, st),
            )

        if not targets:
            status_lbl.configure(text="Tidak ada host yang bisa di-ping.")
            return

        runner = MultiHostPingRunner(targets, on_status=on_status)
        self.set_runner_stop(runner.stop)
        runner.start()
        status_lbl.configure(text=f"Ping aktif ke {len(targets)} host…")

    def _open_traceroute_topo_view(self) -> None:
        """Traceroute ke 8.8.8.8 → topologi menyamping (wrap), icon per jenis perangkat."""
        import threading

        from modules.system_info import hostname as get_hostname, primary_ipv4
        from modules.trace_topology import (
            TracerouteTopologyRunner,
            classify_hop,
            resolve_and_classify,
        )

        self.console = None
        target = "8.8.8.8"
        # hop -> {ip, rtt, hostname, kind, icon, kind_label}
        hops: dict[int, dict[str, Any]] = {}

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=t("tool.traceroute.title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._build_sysinfo_bar(self._sysinfo_strip)

        toolbar = ctk.CTkFrame(self._content, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 6))
        status_lbl = ctk.CTkLabel(
            toolbar,
            text=f"Tracing route ke {target}…",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["muted"],
            anchor="w",
        )
        status_lbl.pack(side="left", fill="x", expand=True)

        def restart() -> None:
            self._stop_runner()
            hops.clear()
            status_lbl.configure(text=f"Tracing route ke {target}…")
            set_trace_loading(True)
            _draw()
            _start()

        # LTR di frame kanan: Refresh | Kirim | Kembali (Refresh bisa di-hide saat loading)
        actions = ctk.CTkFrame(toolbar, fg_color="transparent")
        actions.pack(side="right")
        btn_refresh = ctk.CTkButton(
            actions,
            text=t("app.refresh"),
            width=90,
            height=30,
            fg_color="#E6B422",
            hover_color="#C99A12",
            text_color="#1A1400",
            command=restart,
        )
        btn_refresh.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text=t("app.send"),
            width=100,
            height=30,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._send_screenshot,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text=t("app.back"),
            width=100,
            height=30,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="left")

        # Shell + canvas border warna-warni mengelilingi area topologi
        shell = ctk.CTkFrame(self._content, fg_color="transparent")
        shell.pack(fill="both", expand=True)
        border_cv = tk.Canvas(
            shell,
            bg=COLORS["bg"],
            highlightthickness=0,
            bd=0,
        )
        border_cv.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(border_cv, fg_color=COLORS["panel"], corner_radius=0)
        inner_win = border_cv.create_window(4, 4, window=inner, anchor="nw")

        # Overlay loading selama traceroute berjalan
        trace_load = ctk.CTkFrame(shell, fg_color=COLORS["panel"], corner_radius=10)
        trace_load_inner = ctk.CTkFrame(trace_load, fg_color="transparent")
        trace_load_inner.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(
            trace_load_inner,
            text=t("trace.loading"),
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=COLORS["text"],
        ).pack()
        trace_bar = ctk.CTkProgressBar(
            trace_load_inner,
            width=260,
            height=8,
            progress_color=COLORS["accent"],
            fg_color=COLORS["bg"],
            mode="indeterminate",
        )
        trace_bar.pack(pady=(12, 0))

        def set_trace_loading(active: bool) -> None:
            try:
                if active:
                    btn_refresh.pack_forget()
                    trace_load.place(relx=0, rely=0, relwidth=1, relheight=1)
                    trace_bar.start()
                    trace_load.lift()
                else:
                    trace_bar.stop()
                    trace_load.place_forget()
                    others = [w for w in actions.winfo_children() if w is not btn_refresh]
                    if others:
                        btn_refresh.pack(side="left", padx=(0, 8), before=others[0])
                    else:
                        btn_refresh.pack(side="left", padx=(0, 8))
            except Exception:
                pass

        set_trace_loading(True)

        def _paint_rainbow_border(_event: Any = None) -> None:
            bw = 4
            pad = bw + 1
            w = max(int(border_cv.winfo_width()), 40)
            h = max(int(border_cv.winfo_height()), 40)
            border_cv.coords(inner_win, pad, pad)
            border_cv.itemconfigure(inner_win, width=max(w - 2 * pad, 20), height=max(h - 2 * pad, 20))
            border_cv.delete("rb")
            colors = TOPO_RAINBOW
            n = len(colors)
            # Perimeter clockwise: top → right → bottom → left
            perim = [
                ("h", pad, pad, w - pad, pad),  # top L→R
                ("v", w - pad, pad, w - pad, h - pad),  # right T→B
                ("h", w - pad, h - pad, pad, h - pad),  # bottom R→L
                ("v", pad, h - pad, pad, pad),  # left B→T
            ]
            seg_i = 0
            for orient, x1, y1, x2, y2 in perim:
                length = abs((x2 - x1) if orient == "h" else (y2 - y1))
                parts = max(int(length / 28), n)
                for p in range(parts):
                    t0 = p / parts
                    t1 = (p + 1) / parts
                    if orient == "h":
                        xa = x1 + (x2 - x1) * t0
                        xb = x1 + (x2 - x1) * t1
                        ya = yb = y1
                    else:
                        ya = y1 + (y2 - y1) * t0
                        yb = y1 + (y2 - y1) * t1
                        xa = xb = x1
                    border_cv.create_line(
                        xa,
                        ya,
                        xb,
                        yb,
                        fill=colors[seg_i % n],
                        width=bw,
                        capstyle=tk.ROUND,
                        tags="rb",
                    )
                    seg_i += 1

        border_cv.bind("<Configure>", _paint_rainbow_border)

        canvas = tk.Canvas(
            inner,
            bg=COLORS["bg"],
            highlightthickness=0,
            bd=0,
        )
        vsb = ctk.CTkScrollbar(inner, orientation="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", padx=(0, 4), pady=4)
        canvas.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        local_name = get_hostname()
        local_ip = primary_ipv4() or "127.0.0.1"

        def _draw(_event: Any = None) -> None:
            canvas.delete("all")
            cw = max(int(canvas.winfo_width()), 360)
            node_w, node_h = 148, 78
            gap_x, gap_y = 28, 36
            pad_x, pad_y = 16, 18
            max_right = cw - pad_x
            palette = TOPO_RAINBOW
            n_colors = len(palette)

            nodes: list[dict[str, Any]] = []
            nodes.append(
                {
                    "title": local_name,
                    "sub": local_ip,
                    "icon": "💻",
                    "kind": "PC",
                    "outline": palette[0],
                    "ok": True,
                }
            )
            for n in sorted(hops.keys()):
                h = hops[n]
                ip = h.get("ip")
                ok = bool(ip)
                icon = h.get("icon") or ("❓" if not ok else "📡")
                kind = h.get("kind_label") or ("Timeout" if not ok else "Host")
                if ip:
                    host = h.get("hostname")
                    sub = f"{ip}"
                    if host:
                        short = host if len(host) <= 28 else host[:25] + "…"
                        sub = f"{ip}\n{short}"
                else:
                    sub = h.get("rtt") or "Request timed out"
                # Timeout tetap merah; hop OK ambil warna pelangi berurutan
                outline = (
                    COLORS.get("danger", "#C42B1C")
                    if not ok
                    else palette[(n) % n_colors]
                )
                nodes.append(
                    {
                        "title": f"Hop {n} · {kind}",
                        "sub": sub,
                        "icon": icon,
                        "kind": kind,
                        "outline": outline,
                        "ok": ok,
                    }
                )

            if not hops or (hops[max(hops.keys())].get("ip") != target):
                _k, icon_t, lab_t = classify_hop(
                    ip=target, hop_num=99, is_target=True
                )
                nodes.append(
                    {
                        "title": f"Target · {lab_t}",
                        "sub": target,
                        "icon": icon_t,
                        "kind": lab_t,
                        "outline": palette[-1],
                        "ok": True,
                    }
                )

            # Layout: kiri → kanan, wrap ke baris bawah saat mentok
            positions: list[tuple[float, float, dict[str, Any]]] = []
            x = float(pad_x)
            y = float(pad_y)
            for node in nodes:
                if x + node_w > max_right and x > pad_x:
                    x = float(pad_x)
                    y += node_h + gap_y
                cx = x + node_w / 2
                cy = y + node_h / 2
                positions.append((cx, cy, node))
                x += node_w + gap_x

            # Garis antar node — warna berbeda per segmen
            for i in range(len(positions) - 1):
                x1, y1, _ = positions[i]
                x2, y2, _ = positions[i + 1]
                line_color = palette[i % n_colors]
                same_row = abs(y1 - y2) < 1.0
                if same_row:
                    canvas.create_line(
                        x1 + node_w / 2,
                        y1,
                        x2 - node_w / 2,
                        y2,
                        fill=line_color,
                        width=2,
                        arrow=tk.LAST,
                        arrowshape=(8, 10, 4),
                    )
                else:
                    mid_y = (y1 + y2) / 2
                    canvas.create_line(
                        x1,
                        y1 + node_h / 2,
                        x1,
                        mid_y,
                        x2,
                        mid_y,
                        x2,
                        y2 - node_h / 2,
                        fill=line_color,
                        width=2,
                        arrow=tk.LAST,
                        arrowshape=(8, 10, 4),
                        smooth=False,
                    )

            for cx, cy, node in positions:
                x1, y1 = cx - node_w / 2, cy - node_h / 2
                x2, y2 = cx + node_w / 2, cy + node_h / 2
                canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=COLORS["panel"],
                    outline=node["outline"],
                    width=3,
                )
                canvas.create_text(
                    cx,
                    cy - 22,
                    text=node["icon"],
                    font=("Segoe UI Emoji", 14),
                )
                canvas.create_text(
                    cx,
                    cy - 2,
                    text=node["title"],
                    fill=COLORS["text"],
                    font=("Segoe UI Semibold", 9),
                    width=node_w - 10,
                )
                canvas.create_text(
                    cx,
                    cy + 20,
                    text=node["sub"],
                    fill=COLORS["muted"],
                    font=("Consolas", 8),
                    width=node_w - 10,
                    justify=tk.CENTER,
                )

            total_h = y + node_h + pad_y + 12
            canvas.configure(scrollregion=(0, 0, cw, max(total_h, 200)))

        def _enrich_hop(hop: int, ip: str) -> None:
            host, kind, icon, kind_label = resolve_and_classify(
                ip, hop, is_target=(ip == target)
            )

            def ui() -> None:
                if hop not in hops:
                    return
                hops[hop]["hostname"] = host
                hops[hop]["kind"] = kind
                hops[hop]["icon"] = icon
                hops[hop]["kind_label"] = kind_label
                _draw()

            self.after(0, ui)

        def on_hop(hop: int, ip: str | None, label: str) -> None:
            def ui() -> None:
                if ip:
                    kind, icon, kind_label = classify_hop(
                        ip=ip, hop_num=hop, is_target=(ip == target)
                    )
                else:
                    kind, icon, kind_label = classify_hop(ip=None, hop_num=hop)
                hops[hop] = {
                    "ip": ip,
                    "rtt": label,
                    "hostname": None,
                    "kind": kind,
                    "icon": icon,
                    "kind_label": kind_label,
                }
                status_lbl.configure(
                    text=f"Hop {hop}: {ip or 'timeout'} ({kind_label}) — tracing {target}…"
                )
                _draw()
                if ip:
                    threading.Thread(
                        target=_enrich_hop, args=(hop, ip), daemon=True
                    ).start()

            self.after(0, ui)

        def on_done() -> None:
            def ui() -> None:
                n = len(hops)
                status_lbl.configure(text=f"Selesai — {n} hop menuju {target}")
                set_trace_loading(False)
                _draw()

            self.after(0, ui)

        def _start() -> None:
            runner = TracerouteTopologyRunner(
                target,
                on_hop=on_hop,
                on_done=on_done,
            )
            self.set_runner_stop(runner.stop)
            runner.start()

        canvas.bind("<Configure>", lambda _e: _draw())
        self.after(80, _draw)
        self.after(120, _start)

    def _open_ip_scanner_view(self) -> None:
        """UI khusus IP Scanner — kartu status + daftar host (bukan console)."""
        self.console = None
        self._ipscan_rows: list[Any] = []
        self._ipscan_running = False

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text="IP Scanner",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=24),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._hide_sysinfo_strip()

        # Ringkasan subnet (rapat)
        summary = ctk.CTkFrame(
            self._content,
            fg_color=COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        summary.pack(fill="x", pady=(0, 8))

        stats = ctk.CTkFrame(summary, fg_color="transparent")
        stats.pack(fill="x", padx=12, pady=(8, 4))
        for col in range(4):
            stats.grid_columnconfigure(col, weight=1)

        def _stat(parent: Any, col: int, label: str) -> ctk.CTkLabel:
            cell = ctk.CTkFrame(parent, fg_color=COLORS["bg"], corner_radius=8)
            cell.grid(
                row=0,
                column=col,
                sticky="nsew",
                padx=(0 if col == 0 else 4, 0 if col == 3 else 4),
            )
            ctk.CTkLabel(
                cell,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color=COLORS["muted"],
            ).pack(anchor="w", padx=10, pady=(6, 0))
            val = ctk.CTkLabel(
                cell,
                text="—",
                font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
                text_color=COLORS["text"],
                anchor="w",
            )
            val.pack(anchor="w", fill="x", padx=10, pady=(2, 6))
            return val

        lbl_ip = _stat(stats, 0, "IP LOKAL")
        lbl_net = _stat(stats, 1, "SUBNET")
        lbl_prog = _stat(stats, 2, "PROGRESS")
        lbl_found = _stat(stats, 3, "HOST HIDUP")

        bar_row = ctk.CTkFrame(summary, fg_color="transparent")
        bar_row.pack(fill="x", padx=12, pady=(0, 8))
        progress = ctk.CTkProgressBar(
            bar_row,
            height=6,
            progress_color=COLORS["accent"],
            fg_color=COLORS["bg"],
        )
        progress.pack(fill="x")
        progress.set(0)

        status_lbl = ctk.CTkLabel(
            bar_row,
            text="Siap memindai subnet PC ini.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["muted"],
            anchor="w",
        )
        status_lbl.pack(fill="x", pady=(4, 0))

        # Toolbar
        tools = ctk.CTkFrame(self._content, fg_color="transparent")
        tools.pack(fill="x", pady=(0, 8))

        btn_start = ctk.CTkButton(
            tools,
            text=t("app.start_scan"),
            width=130,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
        )
        btn_start.pack(side="left")

        btn_stop = ctk.CTkButton(
            tools,
            text="Stop",
            width=90,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            state="disabled",
        )
        btn_stop.pack(side="left", padx=(8, 0))
        self._pack_inline_send_back(tools, text_send=True, height=32, side="left")

        # Header kolom + scroll list (font sama seperti Daftar Aplikasi)
        list_wrap = ctk.CTkFrame(
            self._content,
            fg_color=COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        list_wrap.pack(fill="both", expand=True)

        cols = ctk.CTkFrame(list_wrap, fg_color=COLORS["bg"], corner_radius=0)
        cols.pack(fill="x", padx=1, pady=(1, 0))
        cols.grid_columnconfigure(0, weight=2, minsize=140)
        cols.grid_columnconfigure(1, weight=4, minsize=180)
        cols.grid_columnconfigure(2, weight=1, minsize=90)

        for i, text in enumerate(("ALAMAT IP", "HOSTNAME", "STATUS")):
            ctk.CTkLabel(
                cols,
                text=text,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=10),
                text_color=COLORS["muted"],
                anchor="w",
            ).grid(row=0, column=i, sticky="ew", padx=14, pady=8)

        scroll = ctk.CTkScrollableFrame(
            list_wrap,
            fg_color="transparent",
            corner_radius=0,
        )
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        empty = ctk.CTkLabel(
            scroll,
            text="Belum ada hasil. Klik Mulai Scan.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["muted"],
        )
        empty.pack(pady=28)

        self._ipscan_found: list[tuple[str, str, bool]] = []
        self._ipscan_meta: dict[str, str] = {}
        self._send_text_payload = ""

        def _rebuild_payload() -> None:
            from modules.system_info import hostname as get_hostname

            lines = [
                "=== IP SCANNER ===",
                f"PC: {get_hostname()}",
                f"IP lokal: {self._ipscan_meta.get('ip', '—')}",
                f"Subnet: {self._ipscan_meta.get('network', '—')}",
                f"Host hidup: {len(self._ipscan_found)}",
                "",
            ]
            for idx, (ip, host, is_self) in enumerate(
                sorted(self._ipscan_found, key=lambda x: tuple(int(p) for p in x[0].split("."))),
                1,
            ):
                mark = " *" if is_self else ""
                lines.append(f"{idx}. {ip:<15}  {host or '—'}{mark}")
            self._send_text_payload = "\n".join(lines)

        def _clear_rows() -> None:
            for w in list(scroll.winfo_children()):
                try:
                    w.destroy()
                except Exception:
                    pass
            self._ipscan_rows = []
            self._ipscan_found = []
            self._send_text_payload = ""

        def _add_row(ip: str, hostname: str, is_self: bool) -> None:
            if empty.winfo_exists():
                try:
                    empty.pack_forget()
                except Exception:
                    pass
            row = ctk.CTkFrame(
                scroll,
                fg_color=COLORS["bg"] if len(self._ipscan_rows) % 2 == 0 else "transparent",
                corner_radius=6,
                height=32,
            )
            row.pack(fill="x", pady=1, padx=4)
            row.grid_columnconfigure(0, weight=2, minsize=140)
            row.grid_columnconfigure(1, weight=4, minsize=180)
            row.grid_columnconfigure(2, weight=1, minsize=90)
            row.pack_propagate(False)

            ctk.CTkLabel(
                row,
                text=ip,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=COLORS["text"],
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=14)

            host_text = hostname if hostname and hostname != "-" else "—"
            if is_self:
                host_text = f"{host_text}  ·  {t('ipscan.this_pc')}"
            ctk.CTkLabel(
                row,
                text=host_text,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=COLORS["muted"] if not is_self else COLORS.get("ok", COLORS["accent"]),
                anchor="w",
            ).grid(row=0, column=1, sticky="ew", padx=14)

            badge = ctk.CTkLabel(
                row,
                text=f"  {t('ipscan.online')}  ",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=COLORS.get("on_ok", "#FFFFFF"),
                fg_color=COLORS.get("ok", "#12B76A"),
                corner_radius=6,
            )
            badge.grid(row=0, column=2, sticky="e", padx=14, pady=4)
            self._ipscan_rows.append(row)
            self._ipscan_found.append((ip, hostname, is_self))
            _rebuild_payload()

        def _set_scanning(active: bool) -> None:
            self._ipscan_running = active
            btn_start.configure(state="disabled" if active else "normal")
            btn_stop.configure(state="normal" if active else "disabled")

        def on_start(local_ip: str, network: str, total: int) -> None:
            def ui() -> None:
                self._ipscan_meta = {"ip": local_ip, "network": network}
                lbl_ip.configure(text=local_ip)
                lbl_net.configure(text=network)
                lbl_prog.configure(text=f"0 / {total}")
                lbl_found.configure(text="0")
                progress.set(0)
                status_lbl.configure(text=f"Memindai {total} host di {network}…")
                _clear_rows()
                empty.configure(text="Sedang memindai…")
                empty.pack(pady=36)

            self.after(0, ui)

        def on_progress(checked: int, total: int) -> None:
            def ui() -> None:
                lbl_prog.configure(text=f"{checked} / {total}")
                if total > 0:
                    progress.set(min(1.0, checked / total))

            self.after(0, ui)

        def on_host(ip: str, hostname: str, is_self: bool) -> None:
            def ui() -> None:
                _add_row(ip, hostname, is_self)
                lbl_found.configure(text=str(len(self._ipscan_rows)))

            self.after(0, ui)

        def on_error(msg: str) -> None:
            def ui() -> None:
                status_lbl.configure(text=msg)
                _set_scanning(False)
                progress.set(0)

            self.after(0, ui)

        def on_done(found: int, total: int, cancelled: bool) -> None:
            def ui() -> None:
                _set_scanning(False)
                if total > 0 and not cancelled:
                    progress.set(1.0)
                    lbl_prog.configure(text=f"{total} / {total}")
                if cancelled:
                    status_lbl.configure(text=f"Dibatalkan. Ditemukan {found} host.")
                else:
                    status_lbl.configure(text=f"Selesai. {found} host hidup dari {total} target.")
                if found == 0 and empty.winfo_exists():
                    empty.configure(text="Tidak ada host yang merespons ping.")
                    try:
                        empty.pack(pady=36)
                    except Exception:
                        pass

            self.after(0, ui)

        def start_scan() -> None:
            if self._ipscan_running:
                return
            self._stop_runner()
            _set_scanning(True)
            status_lbl.configure(text="Menyiapkan scan…")
            runner = IpScannerRunner(
                on_start=on_start,
                on_progress=on_progress,
                on_host=on_host,
                on_done=on_done,
                on_error=on_error,
            )
            self.set_runner_stop(runner.stop)
            runner.start()

        def stop_scan() -> None:
            self._stop_runner()
            status_lbl.configure(text="Menghentikan…")

        btn_start.configure(command=start_scan)
        btn_stop.configure(command=stop_scan)

    def _open_embedded_web_view(
        self,
        title: str,
        url: str,
        *,
        auto_start: bool = False,
    ) -> None:
        """Tampilkan URL di Edge WebView2 bawaan (Speedtest / DNS leak, dll.)."""
        self.console = None
        self._webview_auto_start = auto_start
        self._webview_url = url

        # Maksimalkan area WebView: tanpa padding konten, tombol di header
        try:
            self._header.pack_configure(padx=12, pady=(8, 2))
            self._content.pack_configure(padx=0, pady=0)
        except Exception:
            pass

        self._clear_frame(self._header)
        ctk.CTkLabel(
            self._header,
            text=title,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=20),
            text_color=COLORS["text"],
        ).pack(side="left")
        actions = ctk.CTkFrame(self._header, fg_color="transparent")
        actions.pack(side="right")
        ctk.CTkButton(
            actions,
            text=t("app.back"),
            width=100,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            actions,
            text=t("app.send"),
            width=100,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._send_screenshot,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            actions,
            text=t("app.reload"),
            width=110,
            height=32,
            fg_color=COLORS["warn"],
            hover_color=COLORS["warn_hover"],
            text_color=COLORS["on_warn"],
            command=lambda: self._reload_webview(url),
        ).pack(side="right")

        # Strip loading di atas WebView (Tk selalu terlihat; HWND native tidak menutupinya)
        loading_wrap = ctk.CTkFrame(
            self._content,
            fg_color=COLORS["panel"],
            corner_radius=0,
            height=52,
        )
        loading_wrap.pack(fill="x")
        loading_wrap.pack_propagate(False)
        loading_inner = ctk.CTkFrame(loading_wrap, fg_color="transparent")
        loading_inner.pack(fill="both", expand=True, padx=16, pady=8)
        loading_lbl = ctk.CTkLabel(
            loading_inner,
            text=t("app.page_loading"),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
        )
        loading_lbl.pack(fill="x")
        loading_bar = ctk.CTkProgressBar(
            loading_inner,
            height=8,
            mode="indeterminate",
            progress_color=COLORS["accent"],
            fg_color=COLORS["border"],
        )
        loading_bar.pack(fill="x", pady=(6, 0))
        loading_bar.start()
        self._webview_loading_wrap = loading_wrap
        self._webview_loading_bar = loading_bar

        def set_page_loading(active: bool) -> None:
            wrap = getattr(self, "_webview_loading_wrap", None)
            bar = getattr(self, "_webview_loading_bar", None)
            if wrap is None:
                return
            try:
                if active:
                    if not wrap.winfo_ismapped():
                        wrap.pack(fill="x", before=host)
                    if bar is not None:
                        bar.start()
                else:
                    if bar is not None:
                        bar.stop()
                    wrap.pack_forget()
            except Exception:
                pass

        self._set_webview_loading = set_page_loading

        host = tk.Frame(self._content, bg=COLORS["bg"])
        host.pack(fill="both", expand=True)

        embed_ok = False
        embed_err = ""
        try:
            from modules.webview_embed import EmbeddedBrowser

            self.update_idletasks()
            w = max(host.winfo_width(), self._content.winfo_width(), self.winfo_width() - 24, 640)
            h = max(host.winfo_height(), self._content.winfo_height(), self.winfo_height() - 120, 400)
            self._browser = EmbeddedBrowser(
                host,
                w,
                h,
                url=url,
                on_loading=set_page_loading,
                background_color=COLORS["bg"],
            )
            self._browser.pack(fill="both", expand=True)
            self.after(80, lambda: self._browser._force_stretch() if self._browser else None)
            self.after(300, lambda: self._browser._force_stretch() if self._browser else None)
            self.after(900, lambda: self._browser._force_stretch() if self._browser else None)
            if auto_start:
                self._speedtest_click_tries = 0
                self._speedtest_click_job = self.after(2500, self._speedtest_auto_start)
            embed_ok = True
        except Exception as exc:
            embed_err = str(exc)
            self._browser = None
            set_page_loading(False)

        if not embed_ok:
            from modules.speedtest_fallback import open_speedtest_edge_app

            ok, msg = open_speedtest_edge_app(url)
            box = ctk.CTkFrame(host, fg_color=COLORS["panel"], corner_radius=12)
            box.pack(fill="both", expand=True, padx=16, pady=16)
            ctk.CTkLabel(
                box,
                text=title,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=20),
                text_color=COLORS["text"],
            ).pack(anchor="w", padx=20, pady=(20, 8))
            if ok:
                ctk.CTkLabel(
                    box,
                    text=(
                        "Browser bawaan tidak tersedia di mode .exe ini.\n"
                        f"{msg}\n\n"
                        "Jendela Edge mode aplikasi sudah dibuka.\n"
                        "Setelah selesai, klik Kirim di sini untuk screenshot."
                    ),
                    font=ctk.CTkFont(size=13),
                    text_color=COLORS["muted"],
                    justify="left",
                    wraplength=640,
                ).pack(anchor="w", padx=20, pady=(0, 12))
            else:
                ctk.CTkLabel(
                    box,
                    text=(
                        "Gagal memuat browser bawaan (WebView2).\n"
                        f"{embed_err}\n\n"
                        f"Fallback Edge juga gagal: {msg}\n\n"
                        "Install Microsoft Edge + WebView2 Runtime, lalu coba lagi."
                    ),
                    font=ctk.CTkFont(size=13),
                    text_color=COLORS["danger"],
                    justify="left",
                    wraplength=640,
                ).pack(anchor="w", padx=20, pady=(0, 12))
            ctk.CTkButton(
                box,
                text="Buka Lagi",
                width=140,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                command=lambda: open_speedtest_edge_app(url),
            ).pack(anchor="w", padx=20, pady=(0, 20))
            self._action_bar.pack(fill="x", padx=12, pady=(0, 6), before=self._footer)
            ctk.CTkButton(
                self._action_bar,
                text=t("app.back"),
                width=120,
                height=36,
                fg_color=COLORS["danger"],
                hover_color=COLORS["danger_hover"],
                command=self._cancel_to_dashboard,
            ).pack(side="right", padx=(8, 0))
            ctk.CTkButton(
                self._action_bar,
                text=t("app.send"),
                width=120,
                height=36,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                command=self._send_screenshot,
            ).pack(side="right")
        else:
            self._action_bar.pack_forget()

    def _reload_webview(self, url: str) -> None:
        set_loading = getattr(self, "_set_webview_loading", None)
        if callable(set_loading):
            set_loading(True)
        if self._browser is not None:
            self._browser.load_url(url)
            if getattr(self, "_webview_auto_start", False):
                self._speedtest_click_tries = 0
                if self._speedtest_click_job is not None:
                    try:
                        self.after_cancel(self._speedtest_click_job)
                    except Exception:
                        pass
                self._speedtest_click_job = self.after(2500, self._speedtest_auto_start)
            return
        from modules.speedtest_fallback import open_speedtest_edge_app

        open_speedtest_edge_app(url)
        if callable(set_loading):
            set_loading(False)

    def _speedtest_auto_start(self) -> None:
        self._speedtest_click_job = None
        if self._browser is None or self._current_tool != "speedtest":
            return
        try:
            self._browser.fit_page()
            self._browser.click_start()
        except Exception:
            pass
        self._speedtest_click_tries += 1
        if self._speedtest_click_tries < 20:
            self._speedtest_click_job = self.after(1500, self._speedtest_auto_start)

    def _cancel_to_dashboard(self) -> None:
        self._set_anydesk_topmost(False)
        # Bersihkan tooltip SSH yang bisa tertinggal
        try:
            sess_ui = getattr(self, "_scp_panel", None)
            if sess_ui is not None and hasattr(sess_ui, "_clear_tooltips"):
                sess_ui._clear_tooltips()
        except Exception:
            pass
        # Destroy orphan tooltip windows
        try:
            for w in list(self.winfo_children()):
                if isinstance(w, tk.Toplevel) and w.wm_overrideredirect():
                    try:
                        w.destroy()
                    except Exception:
                        pass
        except Exception:
            pass
        self._stop_runner()
        self.show_dashboard()

    def _show_done_dialog(self, message: str, title: str | None = None) -> None:
        """Notifikasi sederhana saat proses tool selesai."""
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

        dlg_w, dlg_h = 420, 220
        dlg = ctk.CTkToplevel(self)
        dlg.title(t("app.brand"))
        dlg.geometry(f"{dlg_w}x{dlg_h}")
        dlg.minsize(dlg_w, 200)
        dlg.resizable(True, True)
        dlg.configure(fg_color=COLORS["bg"])
        dlg.transient(self)
        dlg.attributes("-topmost", True)
        dlg.attributes("-alpha", 0.0)

        prefs = load_prefs()
        self.update_idletasks()
        saved_x = prefs.get("done_x")
        saved_y = prefs.get("done_y")
        if saved_x is not None and saved_y is not None:
            try:
                px, py = int(saved_x), int(saved_y)
            except Exception:
                px = self.winfo_rootx() + (self.winfo_width() - dlg_w) // 2
                py = self.winfo_rooty() + (self.winfo_height() - dlg_h) // 2
        else:
            px = self.winfo_rootx() + (self.winfo_width() - dlg_w) // 2
            py = self.winfo_rooty() + (self.winfo_height() - dlg_h) // 2
        dlg.geometry(f"{dlg_w}x{dlg_h}+{max(px, 0)}+{max(py, 0)}")

        def _persist_pos(_event: Any = None) -> None:
            try:
                if not dlg.winfo_exists():
                    return
                save_prefs(done_x=int(dlg.winfo_x()), done_y=int(dlg.winfo_y()))
            except Exception:
                pass

        def _close() -> None:
            _persist_pos()
            dlg.destroy()

        _pos_job: dict[str, Any] = {"id": None}

        def _on_cfg(_event: Any = None) -> None:
            jid = _pos_job.get("id")
            if jid is not None:
                try:
                    dlg.after_cancel(jid)
                except Exception:
                    pass
            _pos_job["id"] = dlg.after(400, _persist_pos)

        dlg.bind("<Configure>", _on_cfg)
        dlg.protocol("WM_DELETE_WINDOW", _close)

        flash = ctk.CTkFrame(dlg, fg_color=COLORS["ok"], height=6, corner_radius=0)
        flash.pack(fill="x", side="top")

        frame = ctk.CTkFrame(
            dlg,
            fg_color=COLORS["panel"],
            corner_radius=14,
            border_width=2,
            border_color=COLORS["ok"],
        )
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        footer = ctk.CTkFrame(frame, fg_color="transparent", height=52)
        footer.pack(fill="x", side="bottom", padx=12, pady=(4, 12))
        footer.pack_propagate(False)

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        ctk.CTkLabel(
            body,
            text=title or t("done.title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=20),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            body,
            text=message,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=COLORS["muted"],
            wraplength=360,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        ctk.CTkButton(
            footer,
            text=t("send.ok"),
            width=140,
            height=38,
            fg_color=COLORS["ok"],
            hover_color=COLORS["ok_dim"],
            text_color=COLORS["on_ok"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10,
            command=_close,
        ).pack(side="right", pady=6)

        def fade_in(step: int = 0) -> None:
            if not dlg.winfo_exists():
                return
            alpha = min(1.0, step / 10)
            try:
                dlg.attributes("-alpha", alpha)
            except Exception:
                return
            if step < 10:
                dlg.after(16, lambda: fade_in(step + 1))

        dlg.after(30, dlg.lift)
        dlg.after(50, dlg.focus_force)
        dlg.after(20, fade_in)

    def _notify_tool_done(self, message_key: str) -> None:
        """Tampilkan dialog selesai dari thread worker (aman ke UI thread)."""
        msg = t(message_key)

        def show() -> None:
            self._show_done_dialog(msg)

        self.after(0, show)

    def _anydesk_info_block(
        self, anydesk_id: str, local_id: str, local_ip: str
    ) -> str:
        return (
            f"ID Anydesk\n{anydesk_id}\n\n"
            f"ID Lokal\n{local_id}\n\n"
            f"Alamat IP Lokal\n{local_ip}"
        )

    def _show_anydesk_info_dialog(
        self,
        anydesk_id: str,
        local_id: str,
        local_ip: str,
    ) -> None:
        """Dialog besar: ID Anydesk, ID Lokal, IP — bisa diblok & disalin."""
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

        dlg_w, dlg_h = 540, 520
        dlg = ctk.CTkToplevel(self)
        dlg.title(t("send.dialog_title"))
        dlg.geometry(f"{dlg_w}x{dlg_h}")
        dlg.minsize(dlg_w, 480)
        dlg.resizable(False, False)
        dlg.configure(fg_color=COLORS["bg"])
        dlg.transient(self)
        dlg.attributes("-topmost", True)
        dlg.attributes("-alpha", 0.0)

        self.update_idletasks()
        px = self.winfo_rootx() + (self.winfo_width() - dlg_w) // 2
        py = self.winfo_rooty() + (self.winfo_height() - dlg_h) // 2
        dlg.geometry(f"{dlg_w}x{dlg_h}+{max(px, 40)}+{max(py + 40, 40)}")

        flash = ctk.CTkFrame(dlg, fg_color=COLORS["accent"], height=6, corner_radius=0)
        flash.pack(fill="x", side="top")

        frame = ctk.CTkFrame(
            dlg,
            fg_color=COLORS["panel"],
            corner_radius=14,
            border_width=2,
            border_color=COLORS["accent"],
        )
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        footer = ctk.CTkFrame(frame, fg_color="transparent", height=56)
        footer.pack(fill="x", side="bottom", padx=12, pady=(4, 12))
        footer.pack_propagate(False)

        body = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        ctk.CTkLabel(
            body,
            text=t("anydesk.dialog_title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=14, pady=(8, 2))

        ctk.CTkLabel(
            body,
            text=t("anydesk.dialog_sub"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["muted"],
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 14))

        value_font = ctk.CTkFont(family="Consolas", size=24, weight="bold")
        fields: list[tuple[str, str]] = [
            (t("anydesk.id_label"), anydesk_id),
            (t("anydesk.local_id_label"), local_id),
            (t("anydesk.local_ip_label"), local_ip),
        ]
        entries: list[ctk.CTkEntry] = []

        for label, value in fields:
            ctk.CTkLabel(
                body,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=COLORS["muted"],
            ).pack(anchor="w", padx=14, pady=(4, 2))
            entry = ctk.CTkEntry(
                body,
                height=52,
                font=value_font,
                text_color=COLORS["accent"],
                fg_color=COLORS["bg"],
                border_color=COLORS["border"],
                border_width=1,
            )
            entry.pack(fill="x", padx=14, pady=(0, 8))
            entry.insert(0, value)
            entry.bind("<Key>", lambda _e: "break")
            entry.bind(
                "<Control-a>",
                lambda e, ent=entry: (ent.select_range(0, "end"), ent.icursor("end"), "break"),
            )
            entries.append(entry)

        copied_lbl = ctk.CTkLabel(
            body,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["accent"],
        )
        copied_lbl.pack(anchor="w", padx=14, pady=(0, 4))

        def copy_all() -> None:
            from modules.telegram_share import copy_text_to_clipboard

            block = self._anydesk_info_block(anydesk_id, local_id, local_ip)
            if copy_text_to_clipboard(block):
                copied_lbl.configure(text=t("anydesk.copied"))
            entries[0].focus_set()
            entries[0].select_range(0, "end")

        ctk.CTkButton(
            footer,
            text=t("anydesk.copy_all"),
            width=130,
            height=40,
            fg_color=COLORS["tile"],
            hover_color=COLORS["tile_hover"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=copy_all,
        ).pack(side="left", pady=6)

        def send_telegram() -> None:
            from modules.telegram_share import copy_text_to_clipboard, open_telegram

            block = self._anydesk_info_block(anydesk_id, local_id, local_ip)
            copy_text_to_clipboard(block)
            if open_telegram(background=False):
                copied_lbl.configure(text=t("anydesk.telegram_opened"))
            else:
                copied_lbl.configure(text=t("anydesk.telegram_missing"))
            try:
                self._set_anydesk_topmost(True)
            except Exception:
                pass

        ctk.CTkButton(
            footer,
            text=t("app.send"),
            width=150,
            height=40,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10,
            command=send_telegram,
        ).pack(side="right", pady=6)

        def fade_in(step: int = 0) -> None:
            if not dlg.winfo_exists():
                return
            alpha = min(1.0, step / 10)
            try:
                dlg.attributes("-alpha", alpha)
            except Exception:
                return
            if step < 10:
                dlg.after(16, lambda: fade_in(step + 1))

        dlg.after(30, dlg.lift)
        dlg.after(50, dlg.focus_force)
        dlg.after(80, lambda: entries[0].focus_set())
        dlg.after(80, lambda: entries[0].select_range(0, "end"))
        dlg.after(20, fade_in)

    def _show_kirim_dialog(
        self,
        tips: list[str],
        title: str = "Siap dikirim",
        subtitle: str = "Buka chat Telegram, lalu tempel:",
        *,
        sound: bool = True,
    ) -> None:
        """Notifikasi singkat: tempel dengan Ctrl+V atau Paste."""
        import math

        if sound:
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

        dlg_w, dlg_h = 480, 300
        dlg = ctk.CTkToplevel(self)
        dlg.title("Network Tools — Kirim")
        dlg.geometry(f"{dlg_w}x{dlg_h}")
        dlg.minsize(dlg_w, 280)
        dlg.resizable(False, False)
        dlg.configure(fg_color=COLORS["bg"])
        dlg.transient(self)
        dlg.attributes("-topmost", True)
        dlg.attributes("-alpha", 0.0)

        self.update_idletasks()
        px = self.winfo_rootx() + (self.winfo_width() - dlg_w) // 2
        py = self.winfo_rooty() + (self.winfo_height() - dlg_h) // 2
        dlg.geometry(f"{dlg_w}x{dlg_h}+{max(px, 40)}+{max(py + 40, 40)}")

        flash = ctk.CTkFrame(dlg, fg_color=COLORS["accent"], height=6, corner_radius=0)
        flash.pack(fill="x", side="top")

        frame = ctk.CTkFrame(
            dlg,
            fg_color=COLORS["panel"],
            corner_radius=14,
            border_width=2,
            border_color=COLORS["accent"],
        )
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        footer = ctk.CTkFrame(frame, fg_color="transparent", height=56)
        footer.pack(fill="x", side="bottom", padx=12, pady=(4, 12))
        footer.pack_propagate(False)

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        ctk.CTkLabel(
            body,
            text=title,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=20),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=14, pady=(8, 2))

        ctk.CTkLabel(
            body,
            text=subtitle,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=14, pady=(0, 12))

        # Dua opsi setara: Ctrl+V dan Paste
        keys = ctk.CTkFrame(body, fg_color="transparent")
        keys.pack(fill="x", padx=14, pady=(0, 10))
        keys.grid_columnconfigure(0, weight=1)
        keys.grid_columnconfigure(1, weight=0)
        keys.grid_columnconfigure(2, weight=1)

        shortcut = ctk.CTkLabel(
            keys,
            text="Ctrl + V",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COLORS["on_accent"],
            fg_color=COLORS["accent"],
            corner_radius=10,
            height=48,
        )
        shortcut.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkLabel(
            keys,
            text="atau",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
        ).grid(row=0, column=1, padx=4)

        paste_btn = ctk.CTkLabel(
            keys,
            text="Paste",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COLORS["on_accent"],
            fg_color=COLORS["accent"],
            corner_radius=10,
            height=48,
        )
        paste_btn.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        status = tips[0] if tips else "Gambar sudah di clipboard."
        ctk.CTkLabel(
            body,
            text=status,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["text"],
            wraplength=420,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 4))

        ctk.CTkButton(
            footer,
            text="Mengerti",
            width=150,
            height=40,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10,
            command=dlg.destroy,
        ).pack(side="right", pady=6)

        state = {"pulse": 0}

        def place_dlg(x: int, y: int) -> None:
            dlg.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")

        def fade_slide(step: int = 0) -> None:
            if not dlg.winfo_exists():
                return
            alpha = min(1.0, step / 12)
            offset = int(40 * (1 - alpha))
            try:
                dlg.attributes("-alpha", alpha)
                place_dlg(max(px, 40), max(py + offset, 40))
            except Exception:
                return
            if step < 12:
                dlg.after(16, lambda: fade_slide(step + 1))
            else:
                dlg.after(40, pulse)
                dlg.after(80, shake)

        def pulse() -> None:
            if not dlg.winfo_exists():
                return
            state["pulse"] += 1
            on = (state["pulse"] % 2) == 0
            try:
                border = COLORS["accent"] if on else COLORS["accent_dim"]
                frame.configure(border_color=border)
                flash.configure(fg_color=border)
                shortcut.configure(fg_color=border)
                paste_btn.configure(fg_color=border)
            except Exception:
                return
            if state["pulse"] < 6:
                dlg.after(400, pulse)
            else:
                try:
                    frame.configure(border_color=COLORS["accent"])
                    flash.configure(fg_color=COLORS["accent"])
                    shortcut.configure(fg_color=COLORS["accent"])
                    paste_btn.configure(fg_color=COLORS["accent"])
                except Exception:
                    pass

        def shake(step: int = 0) -> None:
            if not dlg.winfo_exists():
                return
            if step >= 8:
                place_dlg(max(px, 40), max(py, 40))
                return
            dx = int(10 * math.sin(step * 1.2) * (1 - step / 8))
            try:
                place_dlg(max(px + dx, 20), max(py, 40))
            except Exception:
                return
            dlg.after(30, lambda: shake(step + 1))

        dlg.after(30, dlg.lift)
        dlg.after(50, dlg.focus_force)
        dlg.after(20, fade_slide)

    def _send_screenshot(self) -> None:
        # Screenshot dulu (tanpa pesan petunjuk), lalu hentikan proses aktif
        self.update_idletasks()
        left = self.winfo_rootx()
        top = self.winfo_rooty()
        width = self.winfo_width()
        height = self.winfo_height()
        try:
            path = capture_window_region(left, top, width, height)
            # Hentikan ping/traceroute, tapi biarkan browser Speedtest tetap terbuka
            if self._runner_stop:
                try:
                    self._runner_stop()
                except Exception:
                    pass
                self._runner_stop = None
            if self._speedtest_click_job is not None:
                try:
                    self.after_cancel(self._speedtest_click_job)
                except Exception:
                    pass
                self._speedtest_click_job = None
            _ok, tips = send_via_telegram(path)
            try:
                from modules.ui_sounds import play_camera_shutter

                play_camera_shutter()
            except Exception:
                pass
            self._show_kirim_dialog(
                tips,
                title="Screenshot siap",
                subtitle="Buka chat Telegram, lalu tempel gambar:",
                sound=False,
            )
        except Exception as exc:
            if self._runner_stop:
                try:
                    self._runner_stop()
                except Exception:
                    pass
                self._runner_stop = None
            self._show_kirim_dialog([f"Gagal kirim screenshot: {exc}"])

    def _send_text_payload_to_telegram(self) -> None:
        """Kirim teks (IP Scanner) atau file daftar aplikasi ke Telegram."""
        text = (self._send_text_payload or "").strip()
        if not text:
            if self._current_tool == "apps" and self._apps_list:
                from modules.system_info import hostname as get_hostname

                text = format_apps_text(self._apps_list, hostname=get_hostname())
            elif self._current_tool == "security" and self._security_items:
                from modules.system_info import hostname as get_hostname

                text = format_security_text(self._security_items, hostname=get_hostname())
        if not text:
            self._show_kirim_dialog(
                [t("send.no_data")],
                title=t("send.not_ready"),
                subtitle=t("send.not_ready_sub"),
            )
            return

        # Daftar Aplikasi: buat file .txt lalu salin FILE ke clipboard
        if self._current_tool == "apps":
            try:
                _ok, tips, path = send_apps_file_via_telegram(text)
                self._show_kirim_dialog(
                    tips,
                    title="File siap dikirim",
                    subtitle="Buka chat Telegram, lalu tempel file (Ctrl+V):",
                )
            except Exception as exc:
                self._show_kirim_dialog([f"Gagal kirim file: {exc}"])
            return

        try:
            _ok, tips = send_text_via_telegram(text, root=self)
            self._show_kirim_dialog(
                tips,
                title=t("send.text_ready"),
                subtitle=t("send.text_sub"),
            )
        except Exception as exc:
            self._show_kirim_dialog([f"Gagal kirim teks: {exc}"])

    def log(self, line: str) -> None:
        def _append() -> None:
            if self.console is not None:
                self.console.append(line)

        self.after(0, _append)

    def set_runner_stop(self, fn: Callable[[], None] | None) -> None:
        self._runner_stop = fn

    # ----- tool UIs -----
    def _seed_console(self, key: str) -> None:
        if not self.console:
            return
        hints = {
            "ping": "Kartu status live ping ke semua host. Tekan Kembali untuk ke dashboard.",
            "traceroute": "Otomatis tracert ke 8.8.8.8 dan gambar topologi jalur. Refresh untuk ulang.",
            "dns": "Cek kebocoran DNS di browser bawaan aplikasi.",
            "ipscan": "Temukan host hidup di subnet PC ini. Klik Mulai Scan.",
            "speedtest": "Uji kecepatan internet di browser bawaan aplikasi.",
            "refresh": (
                "Menjalankan otomatis: disable/enable adapter & renew DHCP.\n"
                "Fitur ini meminta Run as Administrator (UAC)."
            ),
            "printer": (
                "Menampilkan driver printer terpasang.\n"
                "Fix Printer: clear spooler saja (net stop → hapus antrian → net start).\n"
                "Uninstall/Reinstall driver tetap di tombol terpisah (Admin)."
            ),
            "fixrdp": (
                "Kartu status RDP Server-App1..App8 (port 3389).\n"
                "Tombol Fix RDP: reset client + Clear Cache (butuh Admin)."
            ),
            "scp": (
                "SSH ala MobaXterm: explorer kiri + terminal kanan.\n"
                "Path bisa diketik lalu Enter. Folder .. untuk naik.\n"
                "Setelah Hubungkan, ketik langsung di terminal hitam."
            ),
            "anydesk": (
                "Alur (Admin/UAC): taskkill AnyDesk.exe → jalankan AnyDesk.exe → notifikasi ID.\n"
                "Jendela & notifikasi Always on Top selama menu AnyDesk aktif."
            ),
        }
        for line in hints.get(key, "").split("\n"):
            if line:
                self.console.append(line)

    def _build_tool_controls(self, key: str, parent: ctk.CTkFrame) -> None:
        if key == "ping":
            self._build_ping(parent)
        elif key == "traceroute":
            self._build_traceroute(parent)

    def _build_ping(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=10)
        panel.pack(fill="x")
        ctk.CTkLabel(panel, text="Pilih host:", text_color=COLORS["muted"]).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 12))

        values = host_dropdown_values()
        self._ping_combo = ctk.CTkComboBox(
            row,
            values=values,
            height=36,
            width=420,
            dropdown_fg_color=COLORS["panel"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_dim"],
        )
        self._ping_combo.set(values[0])
        self._ping_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row,
            text=t("app.start_ping"),
            width=100,
            height=36,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._start_ping,
        ).pack(side="left")
        self._pack_inline_send_back(row, text_send=False, height=36, side="left")

    def _parse_host_choice(self, choice: str) -> tuple[str, str]:
        """Return (name, ip) from 'Name - IP' dropdown text."""
        text = (choice or "").strip()
        for sep in (" - ", " — ", " – ", "—", "–", "â€”", "â€“"):
            if sep in text:
                name, ip = text.split(sep, 1)
                return name.strip(), ip.strip()
        return text, text

    def _start_ping(self) -> None:
        choice = ""
        if getattr(self, "_ping_combo", None) is not None:
            choice = self._ping_combo.get().strip()
        if not choice:
            self.log("Pilih host terlebih dahulu.")
            return
        name, ip_text = self._parse_host_choice(choice)
        name, ip = resolve_target_ip(name, ip_text)
        if not ip:
            self.log("Gateway tidak terdeteksi. Periksa koneksi jaringan.")
            return
        self._stop_runner()
        if self.console:
            self.console.clear()
        self.log(f"Pinging {name} [{ip}] with 32 bytes of data:")
        self.log("(Tekan Kembali untuk menghentikan dan kembali ke dashboard)")
        self.log("")
        runner = PingRunner(ip, on_line=self.log)
        self.set_runner_stop(runner.stop)
        runner.start()

    def _build_traceroute(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=10)
        panel.pack(fill="x")
        ctk.CTkLabel(panel, text="Pilih host:", text_color=COLORS["muted"]).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 12))

        values = host_dropdown_values()
        self._trace_combo = ctk.CTkComboBox(
            row,
            values=values,
            height=36,
            width=420,
            dropdown_fg_color=COLORS["panel"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_dim"],
        )
        self._trace_combo.set(values[0])
        self._trace_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row,
            text=t("app.start_trace"),
            width=100,
            height=36,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._start_traceroute,
        ).pack(side="left")
        self._pack_inline_send_back(row, text_send=False, height=36, side="left")

    # ----- runners -----
    def _start_traceroute(self) -> None:
        choice = ""
        if getattr(self, "_trace_combo", None) is not None:
            choice = self._trace_combo.get().strip()
        if not choice:
            self.log("Pilih host terlebih dahulu.")
            return
        name, ip_text = self._parse_host_choice(choice)
        name, ip = resolve_target_ip(name, ip_text)
        if not ip:
            self.log("Gateway tidak terdeteksi. Periksa koneksi jaringan.")
            return
        self._stop_runner()
        if self.console:
            self.console.clear()
        self.log(f"Tracing route to {name} [{ip}] ...")
        self.log("")
        runner = TracerouteRunner(
            ip, on_line=self.log, on_done=lambda: self.log("--- Traceroute selesai ---")
        )
        self.set_runner_stop(runner.stop)
        runner.start()

    def _ensure_admin_for(
        self,
        tool_key: str,
        *,
        resume_action: str = "fix",
        resume_payload: str = "",
    ) -> bool:
        """Minta UAC / restart elevated. resume_action disimpan agar setelah UAC aksi yang benar dijalankan."""
        if tool_key not in ADMIN_TOOLS:
            return True
        if is_admin():
            return True
        try:
            save_prefs(
                pending_elevate_tool=tool_key,
                pending_elevate_action=resume_action or "fix",
                pending_elevate_payload=resume_payload or "",
            )
        except Exception:
            pass
        if self.console:
            self.console.append("Fitur ini membutuhkan Administrator. Meminta izin UAC...")
        ok = relaunch_as_admin(extra_args=["--elevate-tool", tool_key])
        if ok:
            if self.console:
                self.console.append(
                    "Menunggu konfirmasi UAC — aplikasi akan dibuka ulang sebagai Administrator."
                )
            self.after(400, self.destroy)
            return False
        messagebox.showerror(
            "Administrator",
            "Gagal meminta Run as Administrator.\n"
            "Klik kanan Network Tools → Run as administrator, lalu coba lagi.",
        )
        return False

    def _start_refresh(self) -> None:
        if not self._ensure_admin_for("refresh"):
            return
        self._stop_runner()
        if self.console:
            self.console.clear()
        runner = RefreshNetworkRunner(
            NETWORK_ADAPTER,
            on_line=self.log,
            on_done=lambda: self._notify_tool_done("done.refresh"),
        )
        self.set_runner_stop(lambda: None)
        runner.start()

    def _start_printer(self) -> None:
        if not self._ensure_admin_for("printer"):
            return
        self._stop_runner()
        if self.console:
            self.console.clear()
        FixPrinterRunner(
            on_line=self.log,
            on_done=lambda: self._notify_tool_done("done.printer"),
        ).start()

    def _start_fix_rdp(self) -> None:
        if not self._ensure_admin_for("fixrdp"):
            return
        self._stop_runner()
        if self.console:
            self.console.clear()
        FixRdpRunner(
            on_line=self.log,
            on_done=lambda: self._notify_tool_done("done.fixrdp"),
        ).start()

    def _set_anydesk_topmost(self, enabled: bool) -> None:
        """Saat menu AnyDesk aktif: jendela utama Always on Top."""
        self._anydesk_topmost = bool(enabled)
        try:
            self.attributes("-topmost", bool(enabled))
            if enabled:
                self.lift()
                self.focus_force()
        except Exception:
            pass

    def _start_anydesk(self) -> None:
        # UAC dulu — setelah elevasi app dibuka ulang ke menu AnyDesk
        if not self._ensure_admin_for("anydesk", resume_action="run"):
            return

        self._set_anydesk_topmost(True)
        self._stop_runner()
        if self.console:
            self.console.clear()

        def _done(anydesk_id: str | None) -> None:
            def _keep_front() -> None:
                try:
                    self._set_anydesk_topmost(True)
                except Exception:
                    pass

            self.after(0, _keep_front)
            if anydesk_id:
                from modules.system_info import hostname, primary_ipv4

                aid = anydesk_id
                lid = hostname()
                lip = primary_ipv4()

                def show() -> None:
                    self._show_anydesk_info_dialog(aid, lid, lip)

                self.after(80, show)

        self.set_runner_stop(lambda: None)
        AnydeskRunner(on_line=self.log, on_done=_done).start()


def main() -> None:
    try:
        import os

        os.chdir(app_root())
    except Exception:
        pass
    app = NetworkToolsApp()
    app.mainloop()


def _run_sta() -> None:
    """Pastikan COM STA sebelum Tk/WebView2 (hindari crash thread)."""
    try:
        import ctypes

        # COINIT_APARTMENTTHREADED = 0x2
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
    except Exception:
        pass
    main()


if __name__ == "__main__":
    _run_sta()

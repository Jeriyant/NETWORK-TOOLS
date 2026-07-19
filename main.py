"""
Network Tools — single-window desktop utility suite.
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk

from modules.admin import is_admin, relaunch_as_admin
from modules.clear_cache import ClearCacheRunner
from modules.dns_test import DnsTestRunner
from modules.fix_anydesk import AnydeskRunner
from modules.fix_printer import FixPrinterRunner
from modules.ping_runner import PingRunner
from modules.refresh_network import RefreshNetworkRunner
from modules.settings import (
    DEFAULT_THEME,
    DNS_TEST_DOMAINS,
    NETWORK_ADAPTER,
    SPEEDTEST_URL,
    APP_VERSION,
    UPDATE_REPO,
    app_root,
    host_dropdown_values,
    resolve_target_ip,
)
from modules.telegram_share import capture_window_region, send_via_telegram
from modules.theme import (
    MODE_LABELS,
    THEMES,
    mode_from_label,
    next_mode,
    resolve_theme,
    theme_dropdown_values,
)
from modules.traceroute_runner import TracerouteRunner

# Tools that require Administrator (UAC)
ADMIN_TOOLS = frozenset({"refresh", "cache", "printer"})
# Langsung jalan saat menu dibuka (tanpa tombol Jalankan)
AUTO_RUN_TOOLS = frozenset({"refresh", "cache", "printer"})

# Active palette (updated when theme changes)
COLORS: dict[str, str] = dict(THEMES["light"])

TOOLS = [
    ("ping", "Ping", "●", "Ping terus ke host dari daftar"),
    ("traceroute", "Traceroute", "↗", "tracert -d ke alamat IP/host"),
    ("dns", "DNS Test", "◎", "Uji DNS & deteksi leak"),
    ("speedtest", "Speedtest", "⚡", "Speedtest di browser bawaan aplikasi"),
    ("refresh", "Refresh Network", "↻", "Otomatis renew DHCP (Admin)"),
    ("printer", "Fix Printer", "🖨", "Otomatis clear spooler (Admin)"),
    ("cache", "Clear Cache", "⌫", "Otomatis hapus TEMP & RDP6 (Admin)"),
    ("anydesk", "Anydesk", "⌨", "Tutup AnyDesk lama, buka baru, salin ID ke Telegram"),
]

SEND_TOOLS = {"ping", "traceroute", "dns", "speedtest"}


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
        self.theme_mode = DEFAULT_THEME
        self._apply_palette(refresh_ui=False)

        self.title(f"Network Tools  v{APP_VERSION}")
        self.geometry("980x700")
        self.minsize(860, 620)
        self.configure(fg_color=COLORS["bg"])

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

        self._header = ctk.CTkFrame(self, fg_color="transparent")
        self._header.pack(fill="x", padx=28, pady=(18, 4))
        self._sysinfo_strip = ctk.CTkFrame(self, fg_color="transparent")
        self._sysinfo_strip.pack(fill="x", padx=28, pady=(0, 0))
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=24, pady=8)
        self._action_bar = ctk.CTkFrame(self, fg_color="transparent")
        self._footer = ctk.CTkFrame(self, fg_color=COLORS["panel"], height=42, corner_radius=0)
        self._footer.pack(fill="x", side="bottom")
        self._footer.pack_propagate(False)

        year = datetime.now().year
        self._footer_label = ctk.CTkLabel(
            self._footer,
            text=f"Copyright © {year} JERIYANT - BARAMCITY",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
            justify="center",
        )
        self._footer_label.pack(expand=True)

        self.show_dashboard()
        self.after(200, self._maybe_resume_elevated_tool)
        self.after(800, self._check_update_on_startup)
        try:
            from modules.updater import cleanup_update_leftovers

            cleanup_update_leftovers()
        except Exception:
            pass

    def _maybe_resume_elevated_tool(self) -> None:
        """Setelah UAC, buka ulang tool & jalankan otomatis."""
        import sys

        if "--elevate-tool" not in sys.argv:
            return
        try:
            idx = sys.argv.index("--elevate-tool")
            key = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        except Exception:
            return
        if key not in {t[0] for t in TOOLS}:
            return
        if not is_admin():
            return
        self.open_tool(key)
        # AUTO_RUN_TOOLS sudah dijalankan dari open_tool

    def _check_update_on_startup(self) -> None:
        """Cek update ke GitHub setiap kali aplikasi dijalankan."""
        import threading

        def worker() -> None:
            try:
                from modules.updater import check_for_update

                info = check_for_update(APP_VERSION)
            except Exception:
                info = None
            if info:
                self.after(0, lambda: self._prompt_update(info))

        threading.Thread(target=worker, daemon=True).start()

    def _prompt_update(self, info: Any) -> None:
        """Update wajib: dialog kustom, hanya OK — tanpa update app tidak bisa dipakai."""
        import sys
        import tempfile
        import webbrowser
        from pathlib import Path

        from modules.updater import is_direct_exe_url

        ver = str(getattr(info, "version", "?") or "?")
        notes = (getattr(info, "changelog", "") or "").strip()
        if len(notes) > 600:
            notes = notes[:600] + "…"

        dlg = ctk.CTkToplevel(self)
        dlg.title("Update Wajib — Network Tools")
        dlg.geometry("520x520")
        dlg.minsize(480, 460)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color=COLORS["bg"])
        dlg.grab_set()
        dlg.focus_force()

        self.update_idletasks()
        px = self.winfo_rootx() + (self.winfo_width() - 520) // 2
        py = self.winfo_rooty() + (self.winfo_height() - 520) // 2
        dlg.geometry(f"520x520+{max(px, 40)}+{max(py, 40)}")

        state = {"accepted": False}

        def force_exit() -> None:
            import os

            if state["accepted"]:
                return
            try:
                dlg.grab_release()
            except Exception:
                pass
            os._exit(0)

        dlg.protocol("WM_DELETE_WINDOW", force_exit)

        # Kartu utama
        card = ctk.CTkFrame(
            dlg,
            fg_color=COLORS["panel"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="both", expand=True, padx=18, pady=18)

        # Header accent
        header = ctk.CTkFrame(card, fg_color=COLORS["accent"], corner_radius=14, height=88)
        header.pack(fill="x", padx=14, pady=(14, 0))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="UPDATE WAJIB",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLORS["on_accent"],
        ).pack(anchor="w", padx=18, pady=(14, 0))

        ctk.CTkLabel(
            header,
            text="Versi baru tersedia",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=COLORS["on_accent"],
        ).pack(anchor="w", padx=18, pady=(2, 0))

        ctk.CTkLabel(
            header,
            text="Aplikasi tidak dapat digunakan sebelum diperbarui.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["on_accent"],
        ).pack(anchor="w", padx=18, pady=(2, 12))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=16)

        # Versi comparison
        ver_row = ctk.CTkFrame(body, fg_color="transparent")
        ver_row.pack(fill="x", pady=(0, 14))
        ver_row.grid_columnconfigure((0, 2), weight=1)
        ver_row.grid_columnconfigure(1, weight=0)

        def _ver_chip(parent: Any, label: str, value: str, emphasize: bool) -> None:
            chip = ctk.CTkFrame(
                parent,
                fg_color=COLORS["bg"],
                corner_radius=12,
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
                font=ctk.CTkFont(family="Segoe UI Semibold", size=18),
                text_color=COLORS["accent"] if emphasize else COLORS["text"],
            ).pack(anchor="w", padx=14, pady=(2, 12))

        left = ctk.CTkFrame(ver_row, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        _ver_chip(left, "SAAT INI", f"v{APP_VERSION}", False)

        ctk.CTkLabel(
            ver_row,
            text="→",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=20),
            text_color=COLORS["accent"],
        ).grid(row=0, column=1, padx=4)

        right = ctk.CTkFrame(ver_row, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        _ver_chip(right, "TERBARU", f"v{ver}", True)

        ctk.CTkLabel(
            body,
            text="Catatan rilis",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        notes_box = ctk.CTkTextbox(
            body,
            height=140,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=COLORS["bg"],
            text_color=COLORS["text"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=10,
            wrap="word",
            activate_scrollbars=True,
        )
        notes_box.pack(fill="both", expand=True)
        notes_box.insert("1.0", notes or "Pembaruan keamanan & perbaikan stabilitas.")
        notes_box.configure(state="disabled")

        ctk.CTkLabel(
            body,
            text="Dengan menekan OK, unduhan & pemasangan akan dimulai.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", pady=(10, 0))

        def on_ok() -> None:
            import os

            state["accepted"] = True
            try:
                dlg.grab_release()
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
                        "Mode development: unduh EXE dari GitHub, lalu ganti manual.",
                        parent=self,
                    )
                    return
                os._exit(0)
                return

            dest = Path(tempfile.gettempdir()) / f"NetworkTools_update_v{ver}.exe"
            self._show_download_progress(url, dest, ver, info)

        ctk.CTkButton(
            card,
            text="Update Sekarang",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=15),
            height=48,
            corner_radius=12,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=on_ok,
        ).pack(fill="x", padx=18, pady=(8, 18))

        # Blok interaksi window utama selama dialog terbuka
        try:
            self.attributes("-disabled", True)
        except Exception:
            pass

        def _restore_main(_: Any = None) -> None:
            try:
                self.attributes("-disabled", False)
            except Exception:
                pass

        dlg.bind("<Destroy>", _restore_main)

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

        # Tutup window = keluar (update wajib)
        def block_close() -> None:
            pass

        dlg.protocol("WM_DELETE_WINDOW", block_close)

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
                        import os

                        state["closed"] = True
                        try:
                            dlg.grab_release()
                            dlg.destroy()
                        except Exception:
                            pass
                        messagebox.showinfo(
                            "Update",
                            "Unduhan selesai. Aplikasi akan ditutup dan diganti otomatis.\n"
                            "Tunggu beberapa detik — jendela versi baru akan terbuka sendiri.",
                            parent=self,
                        )
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
        if hasattr(self, "_footer"):
            self._footer.configure(fg_color=COLORS["panel"])
        if hasattr(self, "_footer_label"):
            self._footer_label.configure(text_color=COLORS["muted"])
        if not refresh_ui:
            return
        tool = self._current_tool
        if tool:
            self.open_tool(tool)
        else:
            self.show_dashboard()

    def _cycle_theme(self) -> None:
        self.theme_mode = next_mode(self.theme_mode)
        self._apply_palette(refresh_ui=True)

    def _on_theme_dropdown(self, choice: str) -> None:
        mode = mode_from_label(choice)
        if mode == self.theme_mode:
            return
        self.theme_mode = mode
        self._apply_palette(refresh_ui=True)

    def _header_actions(self, parent: ctk.CTkFrame | None = None) -> None:
        host = parent if parent is not None else self._header
        actions = ctk.CTkFrame(host, fg_color="transparent")
        actions.pack(side="right", pady=4)
        values = theme_dropdown_values()
        current = MODE_LABELS.get(self.theme_mode, values[0])
        combo = ctk.CTkOptionMenu(
            actions,
            values=values,
            width=180,
            height=34,
            fg_color=COLORS["tile"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_dim"],
            dropdown_fg_color=COLORS["panel"],
            dropdown_hover_color=COLORS["tile_hover"],
            text_color=COLORS["text"],
            command=self._on_theme_dropdown,
        )
        combo.set(current if current in values else values[0])
        combo.pack(side="right")

    def _build_sysinfo_bar(self, parent: ctk.CTkFrame) -> None:
        """Status strip sekali dibuat; data statis di-cache, latensi update tiap 5 dtk."""
        # Sudah ada — jangan rebuild / jangan reload data
        if self._sysinfo_value_labels and parent.winfo_children():
            self._show_sysinfo_strip()
            self._apply_sysinfo_cache_to_labels()
            self._ensure_latency_poll()
            return

        for child in parent.winfo_children():
            child.destroy()

        bar = ctk.CTkFrame(
            parent,
            fg_color=COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
            height=86,
        )
        bar.pack(fill="x", pady=(10, 0))
        bar.pack_propagate(False)

        rail = ctk.CTkFrame(bar, fg_color=COLORS["accent"], width=4, corner_radius=0)
        rail.pack(side="left", fill="y")

        body = ctk.CTkFrame(bar, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=(14, 16), pady=10)

        metrics = [
            ("HOST", "…", True),
            ("IP", "…", True),
            ("LATENSI", "…", True),
            ("CPU", "…", False),
            ("RAM", "…", False),
            ("UPTIME", "…", False),
            ("WINDOWS", "…", False),
        ]
        self._sysinfo_value_labels = {}

        for i in range(len(metrics)):
            weight = 2 if metrics[i][0] in {"CPU", "WINDOWS"} else 1
            body.grid_columnconfigure(i * 2, weight=weight, uniform="")
            if i < len(metrics) - 1:
                body.grid_columnconfigure(i * 2 + 1, weight=0)

        for idx, (key, placeholder, emphasize) in enumerate(metrics):
            cell = ctk.CTkFrame(body, fg_color="transparent")
            cell.grid(row=0, column=idx * 2, sticky="nsew", padx=(0, 4))

            ctk.CTkLabel(
                cell,
                text=key,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=COLORS["muted"],
                anchor="w",
            ).pack(anchor="w")

            value = ctk.CTkLabel(
                cell,
                text=placeholder,
                font=ctk.CTkFont(
                    family="Segoe UI Semibold",
                    size=14 if emphasize else 12,
                ),
                text_color=COLORS["accent"] if emphasize else COLORS["text"],
                anchor="w",
                wraplength=200 if key in {"CPU", "WINDOWS"} else 0,
                justify="left",
            )
            value.pack(anchor="w", pady=(2, 0))
            self._sysinfo_value_labels[key] = value

            if idx < len(metrics) - 1:
                sep = ctk.CTkFrame(
                    body,
                    fg_color=COLORS["border"],
                    width=1,
                    corner_radius=0,
                )
                sep.grid(row=0, column=idx * 2 + 1, sticky="ns", padx=8, pady=2)

        self._show_sysinfo_strip()
        if self._sysinfo_cache:
            self._apply_sysinfo_cache_to_labels()
            self._ensure_latency_poll()
        else:
            self.after(40, self._load_sysinfo_once)

    def _show_sysinfo_strip(self) -> None:
        try:
            if not self._sysinfo_strip.winfo_ismapped():
                self._sysinfo_strip.pack(fill="x", padx=28, pady=(0, 0), before=self._content)
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
                label = self._sysinfo_value_labels.get("LATENSI")
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
            "HOST": info.get("hostname", "-"),
            "IP": info.get("ip", "-"),
            "LATENSI": info.get("latency", "-"),
            "CPU": info.get("cpu", "-"),
            "RAM": info.get("ram", "-"),
            "UPTIME": info.get("uptime", "-"),
            "WINDOWS": info.get("windows", "-"),
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

    def show_dashboard(self) -> None:
        self._stop_runner()
        self._current_tool = None
        self.console = None
        self._trace_entry = None
        self._ping_combo = None
        self._trace_combo = None

        try:
            self._header.pack_configure(padx=28, pady=(18, 4))
            self._content.pack_configure(padx=24, pady=8)
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
            text="NETWORK TOOLS",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text="IT Networking utilities — ping, DNS, speedtest & perbaikan cepat",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(2, 0))

        # Tema di baris atas (parent = top)
        self._header_actions(top)

        self._build_sysinfo_bar(self._sysinfo_strip)

        grid = ctk.CTkFrame(self._content, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1, uniform="tiles")
        for r in range(2):
            grid.grid_rowconfigure(r, weight=1, uniform="tiles")

        for idx, (key, title, icon, desc) in enumerate(TOOLS):
            r, c = divmod(idx, 4)
            tile = ctk.CTkFrame(
                grid,
                fg_color=COLORS["tile"],
                corner_radius=12,
                border_width=1,
                border_color=COLORS["border"],
            )
            tile.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
            inner = ctk.CTkFrame(tile, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=18, pady=18)
            ctk.CTkLabel(inner, text=icon, font=ctk.CTkFont(size=32), text_color=COLORS["accent"]).pack(
                anchor="w"
            )
            ctk.CTkLabel(
                inner,
                text=title,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=16),
                text_color=COLORS["text"],
            ).pack(anchor="w", pady=(10, 4))
            ctk.CTkLabel(
                inner,
                text=desc,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["muted"],
                wraplength=180,
                justify="left",
            ).pack(anchor="w")
            ctk.CTkButton(
                inner,
                text="Buka",
                width=90,
                height=32,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                command=lambda k=key: self.open_tool(k),
            ).pack(anchor="w", pady=(16, 0))
            for widget in (tile, inner):
                widget.bind("<Enter>", lambda e, t=tile: t.configure(fg_color=COLORS["tile_hover"]))
                widget.bind("<Leave>", lambda e, t=tile: t.configure(fg_color=COLORS["tile"]))

    def open_tool(self, key: str) -> None:
        self._stop_runner()
        self._current_tool = key
        self._clear_frame(self._header)
        self._clear_frame(self._content)
        self._clear_frame(self._action_bar)

        try:
            self._header.pack_configure(padx=28, pady=(18, 4))
            self._content.pack_configure(padx=24, pady=8)
        except Exception:
            pass

        title = next((t for k, t, *_ in TOOLS if k == key), key)

        if key == "speedtest":
            # Speedtest: header ringkas tanpa strip sistem
            self._hide_sysinfo_strip()
            ctk.CTkLabel(
                self._header,
                text=title,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=20),
                text_color=COLORS["text"],
            ).pack(side="left")
            self._open_speedtest_view()
            return

        top = ctk.CTkFrame(self._header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=title,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=24),
            text_color=COLORS["text"],
        ).pack(side="left")
        self._header_actions(top)
        self._build_sysinfo_bar(self._sysinfo_strip)

        # Tool-specific controls at top of content
        controls = ctk.CTkFrame(self._content, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 8))
        self._build_tool_controls(key, controls)

        self.console = ConsoleView(self._content)
        self.console.pack(fill="both", expand=True)

        # Action bar: Kirim + Kembali
        self._action_bar.pack(fill="x", padx=24, pady=(0, 8), before=self._footer)
        ctk.CTkButton(
            self._action_bar,
            text="Kembali",
            width=120,
            height=36,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="right", padx=(8, 0))

        if key in SEND_TOOLS:
            ctk.CTkButton(
                self._action_bar,
                text="Kirim",
                width=120,
                height=36,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                command=self._send_screenshot,
            ).pack(side="right")

        self._seed_console(key)

        if key in AUTO_RUN_TOOLS:
            # Langsung jalan setelah UI siap (tanpa tombol Jalankan)
            starters = {
                "refresh": self._start_refresh,
                "printer": self._start_printer,
                "cache": self._start_cache,
            }
            fn = starters.get(key)
            if fn:
                self.after(150, fn)

    def _open_speedtest_view(self) -> None:
        """Show Speedtest inside embedded Edge WebView2 (no external browser)."""
        url = SPEEDTEST_URL
        self.console = None

        # Maksimalkan area WebView: tanpa padding konten, tombol di header
        try:
            self._header.pack_configure(padx=12, pady=(8, 2))
            self._content.pack_configure(padx=0, pady=0)
        except Exception:
            pass

        # Ganti aksi tema dengan tombol Speedtest di header (hemat tinggi)
        self._clear_frame(self._header)
        ctk.CTkLabel(
            self._header,
            text="Speedtest",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=20),
            text_color=COLORS["text"],
        ).pack(side="left")
        actions = ctk.CTkFrame(self._header, fg_color="transparent")
        actions.pack(side="right")
        ctk.CTkButton(
            actions,
            text="Kembali",
            width=100,
            height=32,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self._cancel_to_dashboard,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            actions,
            text="Kirim",
            width=100,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._send_screenshot,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            actions,
            text="Mulai Ulang",
            width=110,
            height=32,
            fg_color=COLORS["tile"],
            hover_color=COLORS["tile_hover"],
            command=lambda: self._reload_speedtest(url),
        ).pack(side="right")

        host = tk.Frame(self._content, bg=COLORS["bg"])
        host.pack(fill="both", expand=True)

        embed_ok = False
        embed_err = ""
        try:
            from modules.webview_embed import EmbeddedBrowser

            self.update_idletasks()
            w = max(host.winfo_width(), self._content.winfo_width(), self.winfo_width() - 24, 640)
            h = max(host.winfo_height(), self._content.winfo_height(), self.winfo_height() - 120, 400)
            self._browser = EmbeddedBrowser(host, w, h, url=url)
            self._browser.pack(fill="both", expand=True)
            self.after(80, lambda: self._browser._force_stretch() if self._browser else None)
            self.after(300, lambda: self._browser._force_stretch() if self._browser else None)
            self.after(900, lambda: self._browser._force_stretch() if self._browser else None)
            self._speedtest_click_tries = 0
            self._speedtest_click_job = self.after(2500, self._speedtest_auto_start)
            embed_ok = True
        except Exception as exc:
            embed_err = str(exc)
            self._browser = None

        if not embed_ok:
            from modules.speedtest_fallback import open_speedtest_edge_app

            ok, msg = open_speedtest_edge_app(url)
            box = ctk.CTkFrame(host, fg_color=COLORS["panel"], corner_radius=12)
            box.pack(fill="both", expand=True, padx=16, pady=16)
            ctk.CTkLabel(
                box,
                text="Speedtest",
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
                text="Buka Speedtest Lagi",
                width=180,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                command=lambda: open_speedtest_edge_app(url),
            ).pack(anchor="w", padx=20, pady=(0, 20))
            # Fallback: tetap tampilkan bar aksi
            self._action_bar.pack(fill="x", padx=12, pady=(0, 6), before=self._footer)
            ctk.CTkButton(
                self._action_bar,
                text="Kembali",
                width=120,
                height=36,
                fg_color=COLORS["danger"],
                hover_color=COLORS["danger_hover"],
                command=self._cancel_to_dashboard,
            ).pack(side="right", padx=(8, 0))
            ctk.CTkButton(
                self._action_bar,
                text="Kirim",
                width=120,
                height=36,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                command=self._send_screenshot,
            ).pack(side="right")
        else:
            # Tanpa action bar terpisah — area WebView hampir penuh
            self._action_bar.pack_forget()

    def _reload_speedtest(self, url: str) -> None:
        if self._browser is not None:
            self._browser.load_url(url)
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
        self._stop_runner()
        self.show_dashboard()

    def _show_kirim_dialog(
        self,
        tips: list[str],
        title: str = "Siap dikirim",
        subtitle: str = "Buka chat Telegram, lalu tempel:",
    ) -> None:
        """Notifikasi singkat: tempel dengan Ctrl+V atau Paste."""
        import math

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
            self._show_kirim_dialog(
                tips,
                title="Screenshot siap",
                subtitle="Buka chat Telegram, lalu tempel gambar:",
            )
        except Exception as exc:
            if self._runner_stop:
                try:
                    self._runner_stop()
                except Exception:
                    pass
                self._runner_stop = None
            self._show_kirim_dialog([f"Gagal kirim screenshot: {exc}"])

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
            "ping": "Pilih host dari daftar, lalu Mulai Ping. Tekan Kembali untuk ke dashboard.",
            "traceroute": "Pilih host dari dropdown, lalu Mulai. Perintah: tracert -d <alamat>",
            "dns": "Klik Jalankan untuk uji DNS mirip leak test.",
            "speedtest": "Speedtest berjalan di browser bawaan aplikasi.",
            "refresh": (
                "Menjalankan otomatis: disable/enable adapter & renew DHCP.\n"
                "Fitur ini meminta Run as Administrator (UAC)."
            ),
            "printer": (
                "Menjalankan otomatis: clear spooler printer\n"
                "(net stop spooler → hapus antrian → net start spooler).\n"
                "Meminta Run as Administrator (UAC)."
            ),
            "cache": (
                "Menjalankan otomatis: hapus TEMP & folder RDP6.\n"
                "Fitur ini meminta Run as Administrator (UAC)."
            ),
            "anydesk": (
                "Klik Jalankan untuk menutup semua AnyDesk yang berjalan,\n"
                "membuka AnyDesk baru, menyalin ID, lalu membuka Telegram."
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
        elif key == "dns":
            ctk.CTkButton(
                parent,
                text="Jalankan DNS Test",
                width=160,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                command=self._start_dns,
            ).pack(side="left")
        elif key in AUTO_RUN_TOOLS:
            ctk.CTkLabel(
                parent,
                text="Berjalan otomatis…",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=COLORS["muted"],
            ).pack(side="left", pady=4)
        elif key == "anydesk":
            ctk.CTkButton(
                parent,
                text="Jalankan",
                width=120,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["on_accent"],
                command=self._start_anydesk,
            ).pack(side="left")

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
            text="Mulai Ping",
            width=120,
            height=36,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._start_ping,
        ).pack(side="left")

    def _parse_host_choice(self, choice: str) -> tuple[str, str]:
        """Return (name, ip) from 'Name — IP' dropdown text."""
        if "—" in choice:
            name, ip = choice.split("—", 1)
            return name.strip(), ip.strip()
        return choice.strip(), choice.strip()

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
            text="Mulai",
            width=120,
            height=36,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_dim"],
            text_color=COLORS["on_accent"],
            command=self._start_traceroute,
        ).pack(side="left")

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

    def _start_dns(self) -> None:
        self._stop_runner()
        if self.console:
            self.console.clear()
        domains = list(DNS_TEST_DOMAINS)
        runner = DnsTestRunner(domains, on_line=self.log, on_done=lambda: self.log("--- DNS Test selesai ---"))
        self.set_runner_stop(runner.stop)
        runner.start()

    def _ensure_admin_for(self, tool_key: str) -> bool:
        """Minta UAC / restart elevated untuk tool yang butuh admin. Return True jika boleh lanjut."""
        if tool_key not in ADMIN_TOOLS:
            return True
        if is_admin():
            return True
        if self.console:
            self.console.append("Fitur ini membutuhkan Administrator. Meminta izin UAC...")
        ok = relaunch_as_admin(extra_args=["--elevate-tool", tool_key])
        if ok:
            if self.console:
                self.console.append("Menunggu konfirmasi UAC — aplikasi akan dibuka ulang sebagai Administrator.")
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
        runner = RefreshNetworkRunner(NETWORK_ADAPTER, on_line=self.log)
        self.set_runner_stop(lambda: None)
        runner.start()

    def _start_printer(self) -> None:
        if not self._ensure_admin_for("printer"):
            return
        self._stop_runner()
        if self.console:
            self.console.clear()
        FixPrinterRunner(on_line=self.log).start()

    def _start_cache(self) -> None:
        if not self._ensure_admin_for("cache"):
            return
        self._stop_runner()
        if self.console:
            self.console.clear()
        ClearCacheRunner(on_line=self.log).start()

    def _start_anydesk(self) -> None:
        self._stop_runner()
        if self.console:
            self.console.clear()

        def _done(anydesk_id: str | None) -> None:
            if anydesk_id:
                self.after(
                    0,
                    lambda: self._show_kirim_dialog(
                        [f"AnyDesk ID: {anydesk_id} (sudah di clipboard)."],
                        title="AnyDesk ID siap",
                        subtitle="Buka chat Telegram, lalu tempel ID:",
                    ),
                )

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

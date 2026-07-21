"""SSH panel — MobaXterm-style: explorer kiri + terminal interaktif kanan."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

import customtkinter as ctk

from modules.ansi_term import AnsiScreen, strip_plain
from modules.i18n import t
from modules.sftp_session import RemoteEntry, SftpSession


class ScpPanel:
    """Form koneksi + split: file explorer | terminal SSH."""

    def __init__(
        self,
        app: Any,
        header: ctk.CTkFrame,
        content: ctk.CTkFrame,
        colors: dict[str, str],
        *,
        on_back: Callable[[], None],
    ) -> None:
        self.app = app
        self.colors = colors
        self.on_back = on_back
        self.session = SftpSession()
        self._entries: dict[str, Any] = {}
        self._busy = False
        self._shell_chan: Any = None
        self._shell_stop = threading.Event()
        self._shell_thread: threading.Thread | None = None
        self._term_mark = "1.0"
        self._ansi = AnsiScreen(rows=30, cols=100)
        self._term_fullscreen = False

        top = ctk.CTkFrame(header, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=t("tool.scp.title"),
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=colors["text"],
        ).pack(side="left")

        # --- Connection form ---
        form = ctk.CTkFrame(
            content,
            fg_color=colors["panel"],
            corner_radius=10,
            border_width=1,
            border_color=colors["border"],
        )
        form.pack(fill="x", pady=(0, 8))
        inner = ctk.CTkFrame(form, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=8)

        self.host_var = tk.StringVar(value="")
        self.port_var = tk.StringVar(value="22")
        self.user_var = tk.StringVar(value="")
        self.pass_var = tk.StringVar(value="")
        self._load_saved_params()

        def _field(
            parent: Any, label: str, var: tk.StringVar, width: int, show: str | None = None
        ) -> ctk.CTkEntry:
            cell = ctk.CTkFrame(parent, fg_color="transparent")
            cell.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                cell,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=colors["muted"],
            ).pack(anchor="w")
            entry = ctk.CTkEntry(
                cell,
                textvariable=var,
                width=width,
                height=30,
                show=show or "",
                fg_color=colors["bg"],
                border_color=colors["border"],
            )
            entry.pack(anchor="w", pady=(2, 0))
            self._bind_entry_clipboard(entry)
            return entry

        self.host_entry = _field(inner, t("scp.host"), self.host_var, 160)
        self.port_entry = _field(inner, t("scp.port"), self.port_var, 56)
        self.user_entry = _field(inner, t("scp.user"), self.user_var, 100)

        # Password + eye toggle
        pass_cell = ctk.CTkFrame(inner, fg_color="transparent")
        pass_cell.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            pass_cell,
            text=t("scp.pass"),
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=colors["muted"],
        ).pack(anchor="w")
        pass_row = ctk.CTkFrame(pass_cell, fg_color="transparent")
        pass_row.pack(anchor="w", pady=(2, 0))
        self.pass_entry = ctk.CTkEntry(
            pass_row,
            textvariable=self.pass_var,
            width=110,
            height=30,
            show="•",
            fg_color=colors["bg"],
            border_color=colors["border"],
        )
        self.pass_entry.pack(side="left")
        self._bind_entry_clipboard(self.pass_entry)
        self._pass_shown = False
        self.btn_eye = ctk.CTkButton(
            pass_row,
            text="👁",
            width=34,
            height=30,
            fg_color=colors["bg"],
            hover_color=colors.get("accent_dim", colors["accent"]),
            text_color=colors["text"],
            border_width=1,
            border_color=colors["border"],
            command=self._toggle_password,
        )
        self.btn_eye.pack(side="left", padx=(4, 0))
        self._bind_tooltip(self.btn_eye, "Tampilkan / sembunyikan password")

        btn_cell = ctk.CTkFrame(inner, fg_color="transparent")
        btn_cell.pack(side="left", padx=(4, 0))
        ctk.CTkLabel(
            btn_cell,
            text=" ",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=colors["muted"],
        ).pack(anchor="w")
        btns = ctk.CTkFrame(btn_cell, fg_color="transparent")
        btns.pack(anchor="w", pady=(2, 0))

        def _cicon(
            icon: str,
            cmd: Callable[[], None],
            tip: str,
            *,
            color: str,
            hover: str,
            text_color: str = "#FFFFFF",
        ) -> ctk.CTkButton:
            b = ctk.CTkButton(
                btns,
                text=icon,
                width=36,
                height=30,
                font=ctk.CTkFont(family="Segoe UI Emoji", size=14),
                fg_color=color,
                hover_color=hover,
                text_color=text_color,
                command=cmd,
            )
            b.pack(side="left", padx=(0, 5))
            self._bind_tooltip(b, tip)
            return b

        self.btn_connect = _cicon(
            "🔗", self._connect, t("scp.connect"), color="#2563EB", hover="#1D4ED8"
        )
        self.btn_disconnect = _cicon(
            "⏏", self._disconnect, t("scp.disconnect"), color="#DC2626", hover="#B91C1C"
        )
        self.btn_disconnect.configure(state="disabled")
        self.btn_save = _cicon(
            "💾", self._save_params, t("scp.save"), color="#16A34A", hover="#15803D"
        )
        self.btn_clear_saved = _cicon(
            "🗑", self._clear_saved_params, t("scp.clear_saved"), color="#EA580C", hover="#C2410C"
        )
        self.btn_back = _cicon(
            "←", self._leave, t("app.back"), color="#DC2626", hover="#B91C1C"
        )

        self.status_lbl = ctk.CTkLabel(
            form,
            text=t("scp.disconnected"),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=colors["muted"],
            anchor="w",
        )
        self.status_lbl.pack(fill="x", padx=12, pady=(0, 8))

        # --- Split: kiri explorer | kanan terminal (tk.Frame agar PanedWindow expand benar) ---
        split = tk.PanedWindow(
            content,
            orient=tk.HORIZONTAL,
            sashwidth=6,
            sashrelief=tk.FLAT,
            bg=colors["bg"],
            bd=0,
        )
        split.pack(fill="both", expand=True)

        left_host = tk.Frame(split, bg=colors["panel"], highlightthickness=0)
        right_host = tk.Frame(split, bg="#0C0C0C", highlightthickness=0)
        split.add(left_host, minsize=300, stretch="always")
        split.add(right_host, minsize=300, stretch="always")

        left = ctk.CTkFrame(
            left_host,
            fg_color=colors["panel"],
            corner_radius=0,
            border_width=0,
        )
        left.pack(fill="both", expand=True)
        right = ctk.CTkFrame(
            right_host,
            fg_color="#0C0C0C",
            corner_radius=0,
            border_width=0,
        )
        right.pack(fill="both", expand=True)

        # LEFT: toolbar + path + tree
        left_inner = ctk.CTkFrame(left, fg_color="transparent")
        left_inner.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            left_inner,
            text="File Explorer",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
            text_color=colors["text"],
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self.tools = ctk.CTkFrame(left_inner, fg_color="transparent")
        self.tools.pack(fill="x", pady=(0, 4))

        self.path_var = tk.StringVar(value="")
        self.path_entry = ctk.CTkEntry(
            self.tools,
            textvariable=self.path_var,
            height=28,
            fg_color=colors["bg"],
            border_color=colors["border"],
            placeholder_text="/path — tulis lalu Enter",
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.path_entry.bind("<Return>", lambda _e: self._goto_path())

        def _icon_btn(
            icon: str,
            cmd: Callable[[], None],
            tip: str,
            *,
            color: str,
            hover: str | None = None,
            text_color: str = "#FFFFFF",
        ) -> ctk.CTkButton:
            b = ctk.CTkButton(
                self.tools,
                text=icon,
                width=34,
                height=28,
                font=ctk.CTkFont(family="Segoe UI Emoji", size=14),
                fg_color=color,
                hover_color=hover or color,
                text_color=text_color,
                border_width=0,
                command=cmd,
            )
            b.pack(side="left", padx=(0, 3))
            self._bind_tooltip(b, tip)
            return b

        # Warna berbeda per aksi
        self.btn_ref = _icon_btn(
            "↻",
            self._refresh,
            t("scp.refresh"),
            color="#E6B422",
            hover="#C99A12",
            text_color="#1A1400",
        )
        self.btn_mkdir = _icon_btn(
            "📁+", self._new_folder, t("scp.new_folder"), color="#16A34A", hover="#15803D"
        )
        self.btn_mkfile = _icon_btn(
            "📄+", self._new_file, t("scp.new_file"), color="#0D9488", hover="#0F766E"
        )
        self.btn_upload = _icon_btn(
            "⬆", self._upload, t("scp.upload"), color="#8B5CF6", hover="#7C3AED"
        )
        self.btn_download = _icon_btn(
            "⬇", self._download, t("scp.download"), color="#F97316", hover="#EA580C"
        )
        self.btn_delete = _icon_btn(
            "🗑", self._delete, t("scp.delete"), color="#DC2626", hover="#B91C1C"
        )

        self._drag_start: tuple[int, int] | None = None
        self._drag_entry: Any | None = None
        self._drag_armed = False

        self.drop_hint = ctk.CTkLabel(
            left_inner,
            text=t("scp.drop_hint"),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=colors["muted"],
            anchor="w",
        )
        self.drop_hint.pack(fill="x", pady=(0, 4))

        host = tk.Frame(
            left_inner,
            bg=colors["bg"],
            highlightthickness=1,
            highlightbackground=colors["border"],
        )
        host.pack(fill="both", expand=True)
        self._tree_host = host

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Scp.Treeview",
            background=colors["bg"],
            foreground=colors["text"],
            fieldbackground=colors["bg"],
            borderwidth=0,
            rowheight=26,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Scp.Treeview.Heading",
            background=colors["panel"],
            foreground=colors["muted"],
            borderwidth=0,
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Scp.Treeview",
            background=[("selected", colors["accent"])],
            foreground=[("selected", colors["on_accent"])],
        )

        cols = ("name", "size", "mtime", "type")
        self.tree = ttk.Treeview(
            host,
            columns=cols,
            show="headings",
            style="Scp.Treeview",
            selectmode="browse",
        )
        self.tree.heading("name", text=t("scp.col.name"), anchor="w")
        self.tree.heading("size", text=t("scp.col.size"), anchor="e")
        self.tree.heading("mtime", text=t("scp.col.mtime"), anchor="w")
        self.tree.heading("type", text=t("scp.col.type"), anchor="w")
        self.tree.column("name", width=200, minwidth=100, anchor="w", stretch=True)
        self.tree.column("size", width=70, minwidth=50, anchor="e", stretch=False)
        self.tree.column("mtime", width=110, minwidth=80, anchor="w", stretch=False)
        self.tree.column("type", width=70, minwidth=50, anchor="w", stretch=False)

        vsb = ttk.Scrollbar(host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)
        self.tree.tag_configure("odd", background=colors["bg"])
        self.tree.tag_configure("even", background=colors["panel"])
        self.tree.tag_configure("dir", foreground=colors["accent"])
        self.tree.tag_configure("parent", foreground=colors["muted"])

        # Progress transfer (MobaXterm-style) di bawah explorer
        self.xfer_frame = ctk.CTkFrame(left_inner, fg_color="transparent")
        self.xfer_frame.pack(fill="x", pady=(6, 0))
        self.xfer_lbl = ctk.CTkLabel(
            self.xfer_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=colors["muted"],
            anchor="w",
        )
        self.xfer_lbl.pack(fill="x")
        self.xfer_bar = ctk.CTkProgressBar(
            self.xfer_frame,
            height=8,
            progress_color=colors["accent"],
            fg_color=colors["border"],
            mode="indeterminate",
        )
        self.xfer_bar.pack(fill="x", pady=(4, 0))
        self.xfer_frame.pack_forget()
        self._xfer_active = False

        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Return>", self._on_double)
        self.tree.bind("<ButtonPress-1>", self._on_tree_press)
        self.tree.bind("<B1-Motion>", self._on_tree_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_release)

        self._menu = tk.Menu(self.tree, tearoff=0)
        self._menu.add_command(label=t("scp.open"), command=self._open_selected)
        self._menu.add_command(label=t("scp.download"), command=self._download)
        self._menu.add_command(label=t("scp.copy_path"), command=self._copy_path)
        self._menu.add_command(label=t("scp.copy_name"), command=self._copy_name)
        self._menu.add_separator()
        self._menu.add_command(label=t("scp.rename"), command=self._rename)
        self._menu.add_command(label=t("scp.delete"), command=self._delete)

        # RIGHT: interactive terminal
        right_inner = ctk.CTkFrame(right, fg_color="transparent")
        right_inner.pack(fill="both", expand=True, padx=6, pady=6)
        ctk.CTkLabel(
            right_inner,
            text="Terminal",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
            text_color="#AAAAAA",
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        term_host = tk.Frame(right_inner, bg="#0C0C0C", highlightthickness=0)
        term_host.pack(fill="both", expand=True)
        self.term = tk.Text(
            term_host,
            bg="#0C0C0C",
            fg="#CCCCCC",
            insertbackground="#FFFFFF",
            selectbackground="#264F78",
            selectforeground="#FFFFFF",
            font=("Consolas", 11),
            relief=tk.FLAT,
            bd=0,
            wrap=tk.CHAR,
            undo=False,
            insertwidth=2,
            padx=6,
            pady=6,
        )
        term_sb = ttk.Scrollbar(term_host, orient="vertical", command=self.term.yview)
        self.term.configure(yscrollcommand=term_sb.set)
        self.term.pack(side="left", fill="both", expand=True)
        term_sb.pack(side="right", fill="y")

        self.term.bind("<Key>", self._on_term_key)
        self.term.bind("<<Paste>>", self._on_term_paste)
        self.term.bind("<Button-1>", lambda _e: self.term.focus_set())
        self.term.bind("<Button-3>", self._on_term_right_click)
        self.term.bind("<Control-c>", self._on_term_ctrl_c)
        self.term.bind("<Control-v>", self._on_term_paste)
        self.term.bind("<Control-a>", self._on_term_select_all)
        self.term.bind("<Control-l>", self._on_term_clear)

        self._term_menu = tk.Menu(self.term, tearoff=0)
        self._term_menu.add_command(label="Copy", command=self._term_copy)
        self._term_menu.add_command(label="Paste", command=lambda: self._on_term_paste())
        self._term_menu.add_separator()
        self._term_menu.add_command(label="Select All", command=self._on_term_select_all)
        self._term_menu.add_command(label="Clear", command=self._term_clear_ui)

        self._term_write(
            t("scp.need_connect") + "\n"
            "Terminal — arrow/Ctrl untuk nano/vim · klik kanan: Copy/Paste.\n"
            "Explorer: drop=upload · seret=download · Buka+Save=upload otomatis.\n"
        )
        self.term.configure(state="disabled")

        self._setup_drag_drop()
        app._scp_session = self.session
        app.console = None

        def _set_sash() -> None:
            try:
                total = split.winfo_width()
                if total > 100:
                    split.sash_place(0, int(total * 0.48), 0)
            except Exception:
                pass

        app.after(120, _set_sash)

    def _bind_tooltip(self, widget: Any, text: str) -> None:
        tip: dict[str, Any] = {"win": None}
        if not hasattr(self, "_tooltips"):
            self._tooltips: list[dict[str, Any]] = []
        self._tooltips.append(tip)

        def show(_e: Any = None) -> None:
            if tip["win"] is not None:
                return
            try:
                x = widget.winfo_rootx() + 8
                y = widget.winfo_rooty() + widget.winfo_height() + 4
            except Exception:
                return
            win = tk.Toplevel(self.app)
            win.wm_overrideredirect(True)
            win.attributes("-topmost", True)
            win.geometry(f"+{x}+{y}")
            tk.Label(
                win,
                text=text,
                bg="#1E1E1E",
                fg="#F0F0F0",
                font=("Segoe UI", 9),
                padx=8,
                pady=4,
                relief=tk.SOLID,
                bd=1,
            ).pack()
            tip["win"] = win

        def hide(_e: Any = None) -> None:
            w = tip["win"]
            tip["win"] = None
            if w is not None:
                try:
                    w.destroy()
                except Exception:
                    pass

        tip["hide"] = hide
        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)
        widget.bind("<Destroy>", hide)

    def _clear_tooltips(self) -> None:
        for tip in getattr(self, "_tooltips", []) or []:
            hide = tip.get("hide")
            if callable(hide):
                try:
                    hide()
                except Exception:
                    pass
            w = tip.get("win")
            tip["win"] = None
            if w is not None:
                try:
                    w.destroy()
                except Exception:
                    pass
        self._tooltips = []

    def _bind_entry_clipboard(self, entry: ctk.CTkEntry) -> None:
        def _paste(_e: Any = None) -> str:
            try:
                data = self.app.clipboard_get()
                entry.insert("insert", data)
            except Exception:
                pass
            return "break"

        def _copy(_e: Any = None) -> str:
            try:
                if entry.select_present():
                    self.app.clipboard_clear()
                    self.app.clipboard_append(entry.selection_get())
            except Exception:
                pass
            return "break"

        def _cut(_e: Any = None) -> str:
            _copy()
            try:
                if entry.select_present():
                    entry.delete("sel.first", "sel.last")
            except Exception:
                pass
            return "break"

        def _sel_all(_e: Any = None) -> str:
            try:
                entry.select_range(0, "end")
                entry.icursor("end")
            except Exception:
                pass
            return "break"

        entry.bind("<Control-v>", _paste)
        entry.bind("<Control-V>", _paste)
        entry.bind("<Control-c>", _copy)
        entry.bind("<Control-C>", _copy)
        entry.bind("<Control-x>", _cut)
        entry.bind("<Control-X>", _cut)
        entry.bind("<Control-a>", _sel_all)
        entry.bind("<Control-A>", _sel_all)

    def _toggle_password(self) -> None:
        self._pass_shown = not getattr(self, "_pass_shown", False)
        self.pass_entry.configure(show="" if self._pass_shown else "•")
        self.btn_eye.configure(text="🙈" if self._pass_shown else "👁")

    def _xfer_start(self, label: str) -> None:
        self._xfer_active = True
        try:
            self.xfer_frame.pack(fill="x", pady=(6, 0))
            self.xfer_lbl.configure(text=label)
            self.xfer_bar.start()
        except Exception:
            pass

    def _xfer_stop(self, label: str = "") -> None:
        self._xfer_active = False
        try:
            self.xfer_bar.stop()
            if label:
                self.xfer_lbl.configure(text=label)
                self.app.after(2500, lambda: self.xfer_frame.pack_forget())
            else:
                self.xfer_frame.pack_forget()
        except Exception:
            pass

    # ----- terminal -----
    def _term_write(self, text: str) -> None:
        """Tulis ke terminal; fullscreen (nano/vim) pakai pyte screen."""
        try:
            self.term.configure(state="normal")
            enter_fs = (
                "\x1b[?1049h" in text
                or "\x1b[?47h" in text
                or "\x1b[?1047h" in text
                or "\x1b[2J" in text
            )
            leave_fs = (
                "\x1b[?1049l" in text
                or "\x1b[?47l" in text
                or "\x1b[?1047l" in text
            )
            # Heuristik: banyak CUP → aplikasi fullscreen
            if not self._term_fullscreen and text.count("\x1b[") >= 3 and (
                "\x1b[" in text and ("H" in text or "f" in text)
            ):
                if "nano" in text.lower() or "GNU nano" in text or enter_fs:
                    enter_fs = True

            if enter_fs and not self._term_fullscreen:
                self._term_fullscreen = True
                cols = max(40, int(self.term.winfo_width() / 7) or 100)
                rows = max(12, int(self.term.winfo_height() / 16) or 30)
                self._ansi.resize(rows, cols)
                self._ansi.clear()
                try:
                    self.session.resize_shell(cols, rows)
                except Exception:
                    pass
            if leave_fs:
                self._term_fullscreen = False
                self._ansi.clear()

            if self._term_fullscreen:
                self._ansi.feed(text)
                screen = self._ansi.render()
                self.term.delete("1.0", "end")
                self.term.insert("1.0", screen)
                # Jangan auto-scroll ke bawah saat nano — biarkan top terlihat
                try:
                    self.term.see("1.0")
                except Exception:
                    pass
                self._term_mark = self.term.index("end-1c")
            else:
                plain = strip_plain(text)
                plain = plain.replace("\r\n", "\n").replace("\r", "\n")
                for ch in plain:
                    if ch in ("\x08", "\x7f"):
                        try:
                            self.term.delete("end-2c")
                        except Exception:
                            pass
                    elif ch == "\n":
                        self.term.insert("end", "\n")
                    elif ch == "\x07":
                        pass
                    elif ch:
                        self.term.insert("end", ch)
                self.term.see("end")
                self._term_mark = self.term.index("end-1c")

            if not self.session.connected:
                self.term.configure(state="disabled")
        except Exception:
            pass

    def _term_clear_ui(self) -> None:
        was = str(self.term.cget("state"))
        self.term.configure(state="normal")
        self.term.delete("1.0", "end")
        self._term_mark = "1.0"
        self._term_fullscreen = False
        self._ansi.clear()
        if was == "disabled" or not self.session.connected:
            self.term.configure(state="disabled")

    def _on_term_right_click(self, event: Any) -> None:
        try:
            self.term.focus_set()
            self._term_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._term_menu.grab_release()
            except Exception:
                pass

    def _term_copy(self) -> None:
        try:
            if not self.term.tag_ranges("sel"):
                return
            text = self.term.get("sel.first", "sel.last")
            self.app.clipboard_clear()
            self.app.clipboard_append(text)
        except Exception:
            pass

    def _on_term_select_all(self, _event: Any = None) -> str:
        try:
            was = str(self.term.cget("state"))
            self.term.configure(state="normal")
            self.term.tag_add("sel", "1.0", "end-1c")
            self.term.mark_set("insert", "1.0")
            if was == "disabled":
                self.term.configure(state="disabled")
        except Exception:
            pass
        return "break"

    def _on_term_clear(self, _event: Any = None) -> str:
        self._term_clear_ui()
        if self._shell_chan is not None:
            try:
                self._shell_chan.send("clear\r")
            except Exception:
                try:
                    self._shell_chan.send("\x0c")
                except Exception:
                    pass
        return "break"

    def _on_term_ctrl_c(self, _event: Any = None) -> str:
        # Jika ada seleksi teks → copy; jika tidak → interrupt shell
        try:
            if self.term.tag_ranges("sel"):
                self._term_copy()
                return "break"
        except Exception:
            pass
        if self._shell_chan is not None:
            try:
                self._shell_chan.send("\x03")
            except Exception:
                pass
        return "break"

    def _on_term_paste(self, _event: Any = None) -> str:
        try:
            data = self.app.clipboard_get()
        except Exception:
            return "break"
        if not data:
            return "break"
        data = data.replace("\r\n", "\n").replace("\r", "\n")
        if self._shell_chan is not None:
            try:
                self._shell_chan.send(data)
            except Exception:
                pass
        return "break"

    def _on_term_key(self, event: Any) -> str | None:
        if self._shell_chan is None:
            return "break"
        # Modifier saja
        if event.keysym in {
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Alt_L",
            "Alt_R",
            "Caps_Lock",
            "Win_L",
            "Win_R",
        }:
            return "break"

        try:
            # Arrow / nav — penting untuk nano/vim
            arrows = {
                "Up": "\x1b[A",
                "Down": "\x1b[B",
                "Right": "\x1b[C",
                "Left": "\x1b[D",
                "Home": "\x1b[H",
                "End": "\x1b[F",
                "Prior": "\x1b[5~",
                "Next": "\x1b[6~",
                "Insert": "\x1b[2~",
                "F1": "\x1bOP",
                "F2": "\x1bOQ",
                "F3": "\x1bOR",
                "F4": "\x1bOS",
                "F5": "\x1b[15~",
                "F6": "\x1b[17~",
                "F7": "\x1b[18~",
                "F8": "\x1b[19~",
                "F9": "\x1b[20~",
                "F10": "\x1b[21~",
                "F11": "\x1b[23~",
                "F12": "\x1b[24~",
            }
            if event.keysym in arrows:
                self._shell_chan.send(arrows[event.keysym])
                return "break"

            # Ctrl+Letter → kirim ke shell (nano: Ctrl+O/X/G, dll.)
            # Kecuali Ctrl+C/V/A/L yang punya binding khusus
            if event.state & 0x4:
                if event.keysym.lower() in {"c", "v", "a", "l"}:
                    return "break"
                ch = event.keysym.lower()
                if len(ch) == 1 and "a" <= ch <= "z":
                    self._shell_chan.send(chr(ord(ch) - 96))
                    return "break"
                if event.keysym == "bracketleft":  # Ctrl+[
                    self._shell_chan.send("\x1b")
                    return "break"
                return "break"

            ch = event.char
            if event.keysym == "Return":
                self._shell_chan.send("\r")
            elif event.keysym == "BackSpace":
                self._shell_chan.send("\x7f")  # nano biasanya DEL
            elif event.keysym == "Delete":
                self._shell_chan.send("\x1b[3~")
            elif event.keysym == "Tab":
                self._shell_chan.send("\t")
            elif event.keysym == "Escape":
                self._shell_chan.send("\x1b")
            elif ch:
                self._shell_chan.send(ch)
        except Exception as exc:
            self._term_write(f"\n[shell error: {exc}]\n")
        return "break"

    def _start_shell(self) -> None:
        self._stop_shell()
        def _term_cols_rows() -> tuple[int, int]:
            try:
                # Consolas 11 ≈ 7x16 px per cell
                cols = max(40, int(self.term.winfo_width() / 7) or 100)
                rows = max(12, int(self.term.winfo_height() / 16) or 30)
                return cols, rows
            except Exception:
                return 100, 30

        cols, rows = _term_cols_rows()
        self._ansi.resize(rows, cols)
        try:
            self._shell_chan = self.session.open_shell(width=cols, height=rows)
        except Exception as exc:
            self._term_write(f"\nGagal buka shell: {exc}\n")
            self._shell_chan = None
            return

        self.term.configure(state="normal")
        self._shell_stop.clear()
        self._term_fullscreen = False

        def reader() -> None:
            chan = self._shell_chan
            while not self._shell_stop.is_set() and chan is not None:
                try:
                    if chan.recv_ready():
                        data = chan.recv(16384)
                        if not data:
                            break
                        text = data.decode("utf-8", errors="replace")
                        self._ui(lambda t=text: self._term_write(t))
                    elif chan.closed or (hasattr(chan, "exit_status_ready") and chan.exit_status_ready()):
                        break
                    else:
                        time.sleep(0.03)
                except Exception:
                    break
            self._ui(lambda: self._term_write("\n[shell ditutup]\n"))

        self._shell_thread = threading.Thread(target=reader, daemon=True)
        self._shell_thread.start()
        self.term.focus_set()
        try:
            self.session.resize_shell(cols, rows)
        except Exception:
            pass
        self.term.bind("<Configure>", self._on_term_resize, add="+")

    def _on_term_resize(self, _event: Any = None) -> None:
        if self._shell_chan is None:
            return
        try:
            cols = max(40, int(self.term.winfo_width() / 7) or 100)
            rows = max(12, int(self.term.winfo_height() / 16) or 30)
            self._ansi.resize(rows, cols)
            self.session.resize_shell(cols, rows)
        except Exception:
            pass

    @staticmethod
    def _strip_ansi(text: str) -> str:
        return strip_plain(text)

    def _stop_shell(self) -> None:
        self._shell_stop.set()
        self._shell_chan = None
        try:
            self.session.close_shell()
        except Exception:
            pass
        self._shell_thread = None

    # ----- helpers -----
    def _status(self, text: str) -> None:
        """Status explorer di bar petunjuk (bukan terminal / status koneksi)."""
        try:
            self.drop_hint.configure(text=text)
        except Exception:
            pass

    def _log(self, text: str) -> None:
        """Hanya untuk pesan koneksi / shell — bukan aktivitas explorer."""
        self._term_write(text.rstrip() + "\n")

    def _load_saved_params(self) -> None:
        try:
            from modules.prefs import load_prefs

            p = load_prefs()
            if p.get("ssh_host"):
                self.host_var.set(str(p.get("ssh_host", "")))
            if p.get("ssh_port"):
                self.port_var.set(str(p.get("ssh_port", "22")))
            if p.get("ssh_user"):
                self.user_var.set(str(p.get("ssh_user", "")))
            if p.get("ssh_pass") is not None:
                self.pass_var.set(str(p.get("ssh_pass", "")))
        except Exception:
            pass

    def _save_params(self) -> None:
        from modules.prefs import save_prefs

        save_prefs(
            ssh_host=self.host_var.get().strip(),
            ssh_port=(self.port_var.get() or "22").strip() or "22",
            ssh_user=self.user_var.get().strip(),
            ssh_pass=self.pass_var.get() or "",
        )
        self._status(t("scp.saved_ok"))
        messagebox.showinfo(t("tool.scp.title"), t("scp.saved_ok"), parent=self.app)

    def _clear_saved_params(self) -> None:
        from modules.prefs import save_prefs

        save_prefs(ssh_host="", ssh_port="22", ssh_user="", ssh_pass="")
        self.host_var.set("")
        self.port_var.set("22")
        self.user_var.set("")
        self.pass_var.set("")
        self._status(t("scp.cleared_ok"))
        messagebox.showinfo(t("tool.scp.title"), t("scp.cleared_ok"), parent=self.app)

    def _ui(self, fn: Callable[[], None]) -> None:
        self.app.after(0, fn)

    def _selected(self) -> Any | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self._entries.get(sel[0])

    def _require_conn(self) -> bool:
        if not self.session.connected:
            messagebox.showinfo(t("tool.scp.title"), t("scp.need_connect"), parent=self.app)
            return False
        return True

    def _set_connected_ui(self, ok: bool) -> None:
        self.btn_connect.configure(state="disabled" if ok else "normal")
        self.btn_disconnect.configure(state="normal" if ok else "disabled")
        if ok:
            self.term.configure(state="normal")
        else:
            self.term.configure(state="disabled")

    def _setup_drag_drop(self) -> None:
        """Hook drop di frame host (+ tree bila aman) untuk upload file/folder."""
        try:
            import windnd
        except Exception:
            return

        def _normalize(files: list[Any]) -> list[str]:
            out: list[str] = []
            for item in files or []:
                if isinstance(item, bytes):
                    try:
                        text = item.decode("utf-8")
                    except Exception:
                        text = item.decode("mbcs", errors="replace")
                else:
                    text = str(item)
                text = text.strip().strip('"')
                if text:
                    out.append(text)
            return out

        def on_drop(files: list[Any]) -> None:
            try:
                paths = list(_normalize(files))
            except Exception:
                return
            if not paths:
                return

            def go(p: list[str] = paths) -> None:
                try:
                    self._handle_drop_paths(p)
                except Exception as exc:
                    self._status(f"Drop gagal: {exc}")

            try:
                self.app.after(50, go)
            except Exception:
                pass

        for widget in (self._tree_host, getattr(self, "tree", None)):
            if widget is None:
                continue
            try:
                windnd.hook_dropfiles(widget, func=on_drop)
            except Exception:
                pass

    def _handle_drop_paths(self, paths: list[str]) -> None:
        """Drop dari Windows Explorer → upload file/folder ke remote."""
        if not self.session.connected:
            messagebox.showinfo(t("tool.scp.title"), t("scp.need_connect"), parent=self.app)
            return

        from pathlib import Path as _Path

        items = [p for p in paths if _Path(p).exists()]
        if not items:
            self._status("Drop diabaikan — path tidak valid.")
            return
        self._upload_paths(items)

    def _on_tree_press(self, event: Any) -> None:
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.tree.focus(row)
        self._drag_start = (event.x_root, event.y_root)
        self._drag_entry = self._selected()
        self._drag_armed = False

    def _on_tree_motion(self, event: Any) -> None:
        if self._drag_start is None or self._drag_armed:
            return
        entry = self._drag_entry
        if entry is None or entry.name == ".." or entry.is_dir:
            return
        dx = abs(event.x_root - self._drag_start[0])
        dy = abs(event.y_root - self._drag_start[1])
        if dx + dy < 16:
            return
        if not self.session.connected:
            return
        self._drag_armed = True
        try:
            self.tree.configure(cursor="hand2")
        except Exception:
            pass
        self._begin_drag_out(entry)

    def _on_tree_release(self, _event: Any) -> None:
        try:
            self.tree.configure(cursor="")
        except Exception:
            pass
        if not self._drag_armed:
            self._drag_start = None
            self._drag_entry = None

    def _begin_drag_out(self, entry: Any) -> None:
        """Download ke temp lalu OLE drag ke Windows Explorer (tanpa pilih folder)."""
        import tempfile
        from pathlib import Path as _Path

        self._status(f"Menyiapkan drag download: {entry.name}…")
        self._xfer_start(f"⬇ {entry.name}")

        def worker() -> None:
            tmp_dir = _Path(tempfile.gettempdir()) / "NetworkToolsDnD"
            try:
                tmp_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            dest = tmp_dir / entry.name
            try:
                if dest.exists():
                    dest.unlink()
            except Exception:
                pass
            err = None
            try:
                self.session.download(entry.path, str(dest))
            except Exception as exc:
                err = str(exc)

            def done() -> None:
                self._drag_armed = False
                self._drag_start = None
                self._drag_entry = None
                if err:
                    self._xfer_stop(f"Gagal: {err}")
                    self._status(f"Download gagal: {err}")
                    messagebox.showerror(t("tool.scp.title"), err, parent=self.app)
                    return
                self._xfer_stop(f"Seret ke Explorer: {entry.name}")
                self._status(f"Seret ke folder Windows: {entry.name}")
                try:
                    from modules.win_file_drag import drag_files

                    ok = bool(drag_files([str(dest)]))
                    if ok:
                        self._status(f"Download selesai: {entry.name}")
                        self._xfer_stop(f"Selesai → {entry.name}")
                    else:
                        self._status("Drag dibatalkan.")
                except Exception as exc:
                    self._status(f"Drag gagal ({exc}) — pakai Unduh…")
                    self._download_to(entry, str(dest))

            self._ui(done)

        threading.Thread(target=worker, daemon=True).start()

    # ----- connection -----
    def _connect(self) -> None:
        if self._busy:
            return
        host = self.host_var.get().strip()
        user = self.user_var.get().strip()
        try:
            port = int((self.port_var.get() or "22").strip() or "22")
        except ValueError:
            messagebox.showerror(t("tool.scp.title"), "Port tidak valid.", parent=self.app)
            return
        password = self.pass_var.get()
        self._busy = True
        self.status_lbl.configure(text=t("scp.connecting"))
        self.btn_connect.configure(state="disabled")
        self._term_clear_ui()
        self._log(f"Menghubungkan ke {user}@{host}:{port}…")

        def worker() -> None:
            err = None
            try:
                self.session.connect(host, port, user, password, protocol="SFTP")
            except Exception as exc:
                err = str(exc)

            def done() -> None:
                self._busy = False
                if err:
                    self._set_connected_ui(False)
                    self.status_lbl.configure(text=t("scp.disconnected"))
                    self._log(f"Gagal: {err}")
                    messagebox.showerror(t("tool.scp.title"), err, parent=self.app)
                    return
                self._set_connected_ui(True)
                note = getattr(self.session, "connect_note", "") or ""
                mode = note or ("Mode SFTP" if self.session.sftp_ok else "Mode shell/SCP")
                self.status_lbl.configure(
                    text=t("scp.connected", user=user, host=host, port=port) + f"  [{mode}]"
                )
                self._log(f"Terhubung: {user}@{host}:{port}  [{mode}]")
                # Isi explorer dulu, baru buka shell interaktif
                self._refresh(then_shell=True)

            self._ui(done)

        threading.Thread(target=worker, daemon=True).start()

    def _disconnect(self) -> None:
        self._stop_shell()
        try:
            self.session.disconnect()
        except Exception:
            pass
        self._set_connected_ui(False)
        self.path_var.set("")
        self.tree.delete(*self.tree.get_children())
        self._entries.clear()
        self.status_lbl.configure(text=t("scp.disconnected"))
        self._log("Disconnected.")

    def _leave(self) -> None:
        self._clear_tooltips()
        self._stop_edit_watchers()
        self._stop_shell()
        try:
            self.session.disconnect()
        except Exception:
            pass
        self.app._scp_session = None
        # Hapus hint/status agar tidak tertinggal di UI
        try:
            self.drop_hint.configure(text="")
            self.status_lbl.configure(text="")
        except Exception:
            pass
        self.on_back()

    def _stop_edit_watchers(self) -> None:
        for job in list(getattr(self, "_edit_watch_jobs", []) or []):
            try:
                self.app.after_cancel(job)
            except Exception:
                pass
        self._edit_watch_jobs = []
        self._edit_watchers = {}

    # ----- listing -----
    def _parent_entry(self) -> RemoteEntry | None:
        cwd = (self.session.cwd or "/").rstrip("/") or "/"
        if cwd == "/":
            return None
        parent = cwd.rsplit("/", 1)[0] or "/"
        return RemoteEntry(
            name="..",
            path=parent,
            is_dir=True,
            size=0,
            mtime=0.0,
            mode=0,
        )

    def _fill(self, rows: list[Any]) -> None:
        self.tree.delete(*self.tree.get_children())
        self._entries.clear()
        self.path_var.set(self.session.cwd or "/")

        display: list[Any] = []
        parent = self._parent_entry()
        if parent is not None:
            display.append(parent)
        display.extend(rows)

        # Sembunyikan petunjuk drag-drop saat sudah ada isi / sudah connect
        try:
            if self.session.connected:
                mode = "SFTP" if self.session.sftp_ok else "shell/SCP"
                self.drop_hint.configure(
                    text=f"{len(rows)} item  ·  {self.session.cwd}  ·  {mode}"
                )
            else:
                self.drop_hint.configure(text=t("scp.drop_hint"))
        except Exception:
            pass

        if not display:
            self._status(t("scp.empty"))
            return

        for idx, row in enumerate(display):
            tag = "even" if idx % 2 == 0 else "odd"
            if row.name == "..":
                tags = (tag, "parent", "dir")
                label = "📁 .."
            else:
                tags = (tag, "dir") if row.is_dir else (tag,)
                label = ("📁 " if row.is_dir else "📄 ") + row.name
            iid = self.tree.insert(
                "",
                "end",
                values=(
                    label,
                    "—" if row.name == ".." else row.size_label,
                    "—" if row.name == ".." else row.mtime_label,
                    "Folder" if row.is_dir else row.type_label,
                ),
                tags=tags,
            )
            self._entries[iid] = row

    def _refresh(self, *, then_shell: bool = False) -> None:
        if not self._require_conn():
            return

        def worker() -> None:
            err = None
            rows: list[Any] = []
            try:
                rows = self.session.list_dir()
                if not rows:
                    for alt in ("/",):
                        try:
                            if (self.session.cwd or "/") != alt:
                                self.session.chdir(alt, record_history=False)
                            rows = self.session.list_dir()
                            if rows:
                                break
                        except Exception:
                            continue
            except Exception as exc:
                err = str(exc)

            def done() -> None:
                if err:
                    self._status(f"List error: {err}")
                    messagebox.showerror(t("tool.scp.title"), err, parent=self.app)
                else:
                    self._fill(rows)
                if then_shell:
                    self._start_shell()

            self._ui(done)

        threading.Thread(target=worker, daemon=True).start()

    def _goto_path(self) -> None:
        if not self._require_conn():
            return
        path = self.path_var.get().strip() or "/"

        def worker() -> None:
            err = None
            try:
                self.session.chdir(path, record_history=True)
                rows = self.session.list_dir()
            except Exception as exc:
                err = str(exc)
                rows = []

            def done() -> None:
                if err:
                    self._status(f"Path error: {err}")
                    messagebox.showerror(t("tool.scp.title"), err, parent=self.app)
                    self.path_var.set(self.session.cwd)
                    return
                self._fill(rows)

            self._ui(done)

        threading.Thread(target=worker, daemon=True).start()

    def _go_up(self) -> None:
        if not self._require_conn():
            return

        def worker() -> None:
            try:
                self.session.go_up()
                rows = self.session.list_dir()
            except Exception as exc:
                self._ui(lambda: self._status(f"Up error: {exc}"))
                return
            self._ui(lambda: self._fill(rows))

        threading.Thread(target=worker, daemon=True).start()

    def _on_double(self, _event: Any = None) -> None:
        self._open_selected()

    def _open_selected(self) -> None:
        entry = self._selected()
        if entry is None or not self._require_conn():
            return
        if not entry.is_dir:
            self._open_remote_file(entry)
            return

        def worker() -> None:
            try:
                if entry.name == "..":
                    self.session.go_up()
                else:
                    self.session.chdir(entry.path, record_history=True)
                rows = self.session.list_dir()
            except Exception as exc:
                self._ui(
                    lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app)
                )
                return
            self._ui(lambda: self._fill(rows))

        threading.Thread(target=worker, daemon=True).start()

    def _open_remote_file(self, entry: Any) -> None:
        """Download ke temp, buka editor, pantau save → upload otomatis ke remote."""
        import os
        import subprocess
        import tempfile
        from pathlib import Path as _Path

        self._status(f"Membuka {entry.name}…")
        self._xfer_start(f"Open {entry.name}")

        def worker() -> None:
            tmp_dir = _Path(tempfile.gettempdir()) / "NetworkToolsOpen"
            try:
                tmp_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            dest = tmp_dir / entry.name
            try:
                if dest.exists():
                    dest.unlink()
            except Exception:
                pass
            err = None
            try:
                self.session.download(entry.path, str(dest))
            except Exception as exc:
                err = str(exc)

            def done() -> None:
                if err:
                    self._xfer_stop(f"Gagal: {err}")
                    messagebox.showerror(t("tool.scp.title"), err, parent=self.app)
                    return
                self._xfer_stop(f"Dibuka: {entry.name}")
                path = str(dest)
                opened = False
                # Prefer notepad untuk file teks agar mudah edit+save
                text_ext = {
                    ".txt",
                    ".conf",
                    ".cfg",
                    ".ini",
                    ".json",
                    ".xml",
                    ".yml",
                    ".yaml",
                    ".sh",
                    ".py",
                    ".js",
                    ".css",
                    ".html",
                    ".md",
                    ".log",
                    ".service",
                    ".env",
                }
                suf = dest.suffix.lower()
                if suf in text_ext or suf == "":
                    try:
                        subprocess.Popen(["notepad.exe", path], shell=False)
                        opened = True
                        self._status(f"Notepad → {entry.name} (save = upload otomatis)")
                    except Exception:
                        opened = False
                if not opened:
                    try:
                        subprocess.Popen(
                            ["rundll32.exe", "shell32.dll,OpenAs_RunDLL", path],
                            shell=False,
                        )
                        opened = True
                        self._status(f"Open with → {entry.name} (save = upload otomatis)")
                    except Exception:
                        pass
                if not opened:
                    try:
                        os.startfile(path)  # type: ignore[attr-defined]
                        self._status(f"Opened → {entry.name} (save = upload otomatis)")
                    except Exception as exc:
                        messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app)
                        return
                self._start_edit_watch(entry.path, dest)

            self._ui(done)

        threading.Thread(target=worker, daemon=True).start()

    def _start_edit_watch(self, remote_path: str, local_path: Any) -> None:
        """Pantau mtime file lokal; bila berubah (Save) → upload ke remote."""
        from pathlib import Path as _Path

        path = _Path(local_path)
        try:
            last_mtime = path.stat().st_mtime
            last_size = path.stat().st_size
        except Exception:
            last_mtime = 0.0
            last_size = -1

        if not hasattr(self, "_edit_watch_jobs"):
            self._edit_watch_jobs = []
        if not hasattr(self, "_edit_watchers"):
            self._edit_watchers = {}

        key = str(path)
        # Hentikan watcher lama untuk file yang sama
        old = self._edit_watchers.pop(key, None)
        if old is not None:
            try:
                self.app.after_cancel(old)
            except Exception:
                pass

        state = {"mtime": last_mtime, "size": last_size, "busy": False, "ticks": 0}

        def poll() -> None:
            if not self.session.connected:
                self._edit_watchers.pop(key, None)
                return
            state["ticks"] += 1
            # Berhenti setelah ~2 jam idle poll
            if state["ticks"] > 7200:
                self._edit_watchers.pop(key, None)
                return
            try:
                st = path.stat()
                mtime, size = st.st_mtime, st.st_size
            except Exception:
                job = self.app.after(1200, poll)
                self._edit_watchers[key] = job
                return

            changed = mtime > state["mtime"] + 0.05 or size != state["size"]
            if changed and not state["busy"]:
                state["mtime"] = mtime
                state["size"] = size
                state["busy"] = True
                self._status(f"Menyimpan ke remote: {path.name}…")
                self._xfer_start(f"⬆ Save {path.name}")

                def up() -> None:
                    err = None
                    try:
                        # Tunggu sebentar agar Notepad selesai flush
                        import time as _time

                        _time.sleep(0.35)
                        self.session.upload(str(path), remote_path)
                    except Exception as exc:
                        err = str(exc)

                    def done() -> None:
                        state["busy"] = False
                        if err:
                            self._xfer_stop(f"Upload gagal: {err}")
                            self._status(f"Upload gagal: {err}")
                        else:
                            self._xfer_stop(f"Tersimpan → {remote_path}")
                            self._status(f"Tersimpan ke remote: {remote_path}")
                            try:
                                rows = self.session.list_dir()
                                self._fill(rows)
                            except Exception:
                                pass

                    self._ui(done)

                threading.Thread(target=up, daemon=True).start()

            job = self.app.after(800, poll)
            self._edit_watchers[key] = job

        job = self.app.after(1000, poll)
        self._edit_watchers[key] = job
        self._edit_watch_jobs.append(job)

    def _on_right_click(self, event: Any) -> None:
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.tree.focus(row)
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    # ----- file ops -----
    def _new_folder(self) -> None:
        if not self._require_conn():
            return
        name = simpledialog.askstring(t("scp.new_folder"), t("scp.prompt_folder"), parent=self.app)
        if not name:
            return

        def worker() -> None:
            try:
                path = self.session.mkdir(name.strip())
                rows = self.session.list_dir()
            except Exception as exc:
                self._ui(
                    lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app)
                )
                return
            self._ui(lambda: (self._status(f"mkdir {path}"), self._fill(rows)))

        threading.Thread(target=worker, daemon=True).start()

    def _new_file(self) -> None:
        if not self._require_conn():
            return
        name = simpledialog.askstring(t("scp.new_file"), t("scp.prompt_file"), parent=self.app)
        if not name:
            return

        def worker() -> None:
            try:
                path = self.session.create_file(name.strip())
                rows = self.session.list_dir()
            except Exception as exc:
                self._ui(
                    lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app)
                )
                return
            self._ui(lambda: (self._status(f"create {path}"), self._fill(rows)))

        threading.Thread(target=worker, daemon=True).start()

    def _rename(self) -> None:
        entry = self._selected()
        if entry is None or not self._require_conn():
            return
        if entry.name == "..":
            return
        new_name = simpledialog.askstring(
            t("scp.rename"),
            t("scp.prompt_rename"),
            initialvalue=entry.name,
            parent=self.app,
        )
        if not new_name or new_name == entry.name:
            return

        def worker() -> None:
            try:
                path = self.session.rename(entry.path, new_name.strip())
                rows = self.session.list_dir()
            except Exception as exc:
                self._ui(
                    lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app)
                )
                return
            self._ui(lambda: (self._status(f"rename → {path}"), self._fill(rows)))

        threading.Thread(target=worker, daemon=True).start()

    def _delete(self) -> None:
        entry = self._selected()
        if entry is None or not self._require_conn():
            return
        if entry.name == "..":
            return
        if not messagebox.askyesno(
            t("scp.delete"),
            t("scp.confirm_delete", name=entry.name),
            parent=self.app,
        ):
            return

        def worker() -> None:
            try:
                self.session.remove(entry.path)
                rows = self.session.list_dir()
            except Exception as exc:
                self._ui(
                    lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app)
                )
                return
            self._ui(lambda: (self._status(f"deleted {entry.path}"), self._fill(rows)))

        threading.Thread(target=worker, daemon=True).start()

    def _copy_path(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(entry.path)
            self._status(f"Copied path: {entry.path}")
        except Exception as exc:
            self._status(f"Copy failed: {exc}")

    def _copy_name(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(entry.name)
            self._status(f"Copied name: {entry.name}")
        except Exception as exc:
            self._status(f"Copy failed: {exc}")

    def _download(self) -> None:
        entry = self._selected()
        if entry is None or not self._require_conn():
            return
        if entry.name == ".." or entry.is_dir:
            messagebox.showinfo(
                t("tool.scp.title"),
                "Download folder belum didukung — buka folder lalu unduh file.",
                parent=self.app,
            )
            return
        dest = filedialog.asksaveasfilename(
            parent=self.app,
            title=t("scp.download"),
            initialfile=entry.name,
        )
        if not dest:
            return
        self._download_to(entry, dest)

    def _download_to(self, entry: Any, dest: str) -> None:
        self._status(f"Download {entry.path} → {dest}")
        self._xfer_start(f"⬇ {entry.name}")

        def worker() -> None:
            try:
                self.session.download(entry.path, dest)
            except Exception as exc:
                self._ui(
                    lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app)
                )
                self._ui(lambda: self._status(f"Download gagal: {exc}"))
                self._ui(lambda: self._xfer_stop(f"Gagal: {exc}"))
                return
            self._ui(lambda: self._status(f"Downloaded → {dest}"))
            self._ui(lambda: self._xfer_stop(f"Selesai → {entry.name}"))

        threading.Thread(target=worker, daemon=True).start()

    def _upload(self) -> None:
        if not self._require_conn():
            return
        paths = filedialog.askopenfilenames(parent=self.app, title=t("scp.upload"))
        if not paths:
            folder = filedialog.askdirectory(parent=self.app, title=t("scp.upload"))
            if not folder:
                return
            paths = [folder]
        self._upload_paths(list(paths))

    def _upload_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        if not self.session.connected:
            messagebox.showinfo(t("tool.scp.title"), t("scp.need_connect"), parent=self.app)
            return

        from pathlib import Path as _Path

        items = [p for p in paths if _Path(p).exists()]
        if not items:
            self._status("Tidak ada file/folder untuk di-upload.")
            return

        self._status(f"Upload {len(items)} item…")
        self._xfer_start(f"⬆ Upload {len(items)} item…")

        def worker() -> None:
            ok = 0
            total = 0
            errors: list[str] = []
            for p in items:
                local = _Path(p)
                try:
                    if local.is_file():
                        total += 1
                        self._ui(
                            lambda n=local.name, i=total: self._xfer_start(f"⬆ {n} ({i})")
                        )
                        remote = self.session.upload(local)
                        ok += 1
                        self._ui(lambda r=remote: self._status(f"Uploaded → {r}"))
                    elif local.is_dir():
                        self._ui(
                            lambda n=local.name: self._xfer_start(f"⬆ folder {n}…")
                        )
                        n_ok = self.session.upload_tree(local)
                        ok += n_ok
                        total += n_ok
                        self._ui(
                            lambda n=local.name, k=n_ok: self._status(
                                f"Uploaded folder {n} ({k} file)"
                            )
                        )
                except Exception as exc:
                    errors.append(f"{local.name}: {exc}")
                    self._ui(lambda e=str(exc): self._status(f"Upload fail: {e}"))

            try:
                rows = self.session.list_dir()
            except Exception:
                rows = []

            def finish() -> None:
                self._fill(rows)
                msg = f"Upload selesai ({ok}/{total or len(items)})"
                if errors:
                    msg += f" — gagal {len(errors)}"
                self._status(msg)
                self._xfer_stop(msg)
                if errors and ok == 0:
                    messagebox.showerror(
                        t("tool.scp.title"),
                        "\n".join(errors[:8]),
                        parent=self.app,
                    )

            self._ui(finish)

        threading.Thread(target=worker, daemon=True).start()

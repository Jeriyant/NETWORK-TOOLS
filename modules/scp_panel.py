"""SSH panel — MobaXterm-style: explorer kiri + terminal interaktif kanan."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

import customtkinter as ctk

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
            return entry

        _field(inner, t("scp.host"), self.host_var, 180)
        _field(inner, t("scp.port"), self.port_var, 64)
        _field(inner, t("scp.user"), self.user_var, 120)
        _field(inner, t("scp.pass"), self.pass_var, 130, show="•")

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
        self.btn_connect = ctk.CTkButton(
            btns,
            text=t("scp.connect"),
            width=110,
            height=30,
            fg_color=colors["accent"],
            hover_color=colors["accent_dim"],
            text_color=colors["on_accent"],
            command=self._connect,
        )
        self.btn_connect.pack(side="left", padx=(0, 6))
        self.btn_disconnect = ctk.CTkButton(
            btns,
            text=t("scp.disconnect"),
            width=100,
            height=30,
            fg_color=colors["danger"],
            hover_color=colors["danger_hover"],
            command=self._disconnect,
            state="disabled",
        )
        self.btn_disconnect.pack(side="left", padx=(0, 6))
        self.btn_back = ctk.CTkButton(
            btns,
            text=t("app.back"),
            width=90,
            height=30,
            fg_color=colors["danger"],
            hover_color=colors["danger_hover"],
            command=self._leave,
        )
        self.btn_back.pack(side="left")

        self.status_lbl = ctk.CTkLabel(
            form,
            text=t("scp.disconnected"),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=colors["muted"],
            anchor="w",
        )
        self.status_lbl.pack(fill="x", padx=12, pady=(0, 8))

        # --- Split: kiri explorer | kanan terminal ---
        split = tk.PanedWindow(
            content,
            orient=tk.HORIZONTAL,
            sashwidth=6,
            sashrelief=tk.FLAT,
            bg=colors["bg"],
            bd=0,
        )
        split.pack(fill="both", expand=True)

        left = ctk.CTkFrame(
            split,
            fg_color=colors["panel"],
            corner_radius=8,
            border_width=1,
            border_color=colors["border"],
        )
        right = ctk.CTkFrame(
            split,
            fg_color="#0C0C0C",
            corner_radius=8,
            border_width=1,
            border_color=colors["border"],
        )
        split.add(left, minsize=280, stretch="always")
        split.add(right, minsize=280, stretch="always")

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

        def _tbtn(
            text: str, cmd: Callable[[], None], w: int = 72, color: str | None = None
        ) -> ctk.CTkButton:
            b = ctk.CTkButton(
                self.tools,
                text=text,
                width=w,
                height=28,
                fg_color=color or colors["bg"],
                hover_color=colors.get("accent_dim", colors["accent"]),
                text_color=colors["text"] if not color else "#1A1400",
                border_width=1 if not color else 0,
                border_color=colors["border"],
                command=cmd,
            )
            b.pack(side="left", padx=(0, 4))
            return b

        self.btn_up = _tbtn(t("scp.up"), self._go_up, 64)
        self.btn_ref = _tbtn(t("scp.refresh"), self._refresh, 72, colors.get("warn", "#E6B422"))
        self.btn_mkdir = _tbtn(t("scp.new_folder"), self._new_folder, 88)
        self.btn_mkfile = _tbtn(t("scp.new_file"), self._new_file, 80)
        self.btn_upload = _tbtn(t("scp.upload"), self._upload, 70)

        ctk.CTkLabel(
            left_inner,
            text=t("scp.drop_hint"),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=colors["muted"],
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        host = tk.Frame(left_inner, bg=colors["panel"], highlightthickness=0)
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

        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Return>", self._on_double)

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
        self.term.bind("<Control-c>", self._on_term_ctrl_c)
        self.term.bind("<Control-l>", self._on_term_clear)

        self._term_write(
            t("scp.need_connect") + "\n"
            "Layout: explorer kiri · terminal kanan (ketik langsung setelah Hubungkan).\n"
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

    # ----- terminal -----
    def _term_write(self, text: str) -> None:
        try:
            self.term.configure(state="normal")
            self.term.insert("end", text)
            self.term.see("end")
            self._term_mark = self.term.index("end-1c")
            if not self.session.connected:
                self.term.configure(state="disabled")
        except Exception:
            pass

    def _term_clear_ui(self) -> None:
        self.term.configure(state="normal")
        self.term.delete("1.0", "end")
        self._term_mark = "1.0"

    def _on_term_clear(self, _event: Any = None) -> str:
        if self._shell_chan is not None:
            try:
                self._shell_chan.send("\x0c")  # Ctrl+L
            except Exception:
                self._term_clear_ui()
        else:
            self._term_clear_ui()
        return "break"

    def _on_term_ctrl_c(self, _event: Any = None) -> str:
        if self._shell_chan is not None:
            try:
                self._shell_chan.send("\x03")
            except Exception:
                pass
        return "break"

    def _on_term_paste(self, _event: Any = None) -> str:
        if self._shell_chan is None:
            return "break"
        try:
            data = self.app.clipboard_get()
        except Exception:
            return "break"
        if data:
            try:
                self._shell_chan.send(data.replace("\r\n", "\n").replace("\r", "\n"))
            except Exception:
                pass
        return "break"

    def _on_term_key(self, event: Any) -> str | None:
        if self._shell_chan is None:
            return "break"
        # biarkan navigasi / modifier tanpa kirim
        if event.keysym in {
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Alt_L",
            "Alt_R",
            "Caps_Lock",
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
        }:
            return None
        if event.state & 0x4:  # Control — ditangani binding khusus
            return "break"

        ch = event.char
        try:
            if event.keysym == "Return":
                self._shell_chan.send("\r")
            elif event.keysym == "BackSpace":
                self._shell_chan.send("\x7f")
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
        try:
            cols = max(40, int(self.term.winfo_width() / 8) or 100)
            rows = max(10, int(self.term.winfo_height() / 16) or 30)
            self._shell_chan = self.session.open_shell(width=cols, height=rows)
        except Exception as exc:
            self._term_write(f"\nGagal buka shell: {exc}\n")
            self._shell_chan = None
            return

        self.term.configure(state="normal")
        self._shell_stop.clear()

        def reader() -> None:
            chan = self._shell_chan
            while not self._shell_stop.is_set() and chan is not None:
                try:
                    if chan.recv_ready():
                        data = chan.recv(4096)
                        if not data:
                            break
                        text = data.decode("utf-8", errors="replace")
                        # strip crude ANSI warna (sederhana)
                        text = self._strip_ansi(text)
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

    @staticmethod
    def _strip_ansi(text: str) -> str:
        import re

        # CSI sequences
        text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
        text = re.sub(r"\x1b\][^\x07]*\x07", "", text)
        text = text.replace("\x1b", "")
        return text

    def _stop_shell(self) -> None:
        self._shell_stop.set()
        self._shell_chan = None
        try:
            self.session.close_shell()
        except Exception:
            pass
        self._shell_thread = None

    # ----- helpers -----
    def _log(self, text: str) -> None:
        """Status/pesan → terminal (bukan input terpisah)."""
        self._term_write(text.rstrip() + "\n")

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
            paths = _normalize(files)
            if paths:
                self._ui(lambda p=paths: self._upload_paths(p))

        try:
            windnd.hook_dropfiles(self._tree_host, func=on_drop)
            windnd.hook_dropfiles(self.tree, func=on_drop)
        except Exception:
            pass

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
                sftp_flag = "SFTP✓" if self.session.sftp_ok else "SFTP✗"
                self.status_lbl.configure(
                    text=t("scp.connected", user=user, host=host, port=port)
                    + f"  [SSH✓ · {sftp_flag}]"
                )
                self._log(f"Terhubung: {user}@{host}:{port}  [{sftp_flag}]")
                if note:
                    self._log(note)
                self._start_shell()
                self._refresh()

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
        self._stop_shell()
        try:
            self.session.disconnect()
        except Exception:
            pass
        self.app._scp_session = None
        self.on_back()

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
        self.path_var.set(self.session.cwd)

        display: list[Any] = []
        parent = self._parent_entry()
        if parent is not None:
            display.append(parent)
        display.extend(rows)

        if not display:
            self._log(t("scp.empty"))
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

    def _refresh(self) -> None:
        if not self._require_conn():
            return

        def worker() -> None:
            err = None
            rows: list[Any] = []
            try:
                rows = self.session.list_dir()
            except Exception as exc:
                err = str(exc)

            def done() -> None:
                if err:
                    self._log(f"List error: {err}")
                    messagebox.showerror(t("tool.scp.title"), err, parent=self.app)
                    return
                self._fill(rows)

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
                    self._log(f"Path error: {err}")
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
                self._ui(lambda: self._log(f"Up error: {exc}"))
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
            self._download()
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
            self._ui(lambda: (self._log(f"mkdir {path}"), self._fill(rows)))

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
            self._ui(lambda: (self._log(f"create {path}"), self._fill(rows)))

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
            self._ui(lambda: (self._log(f"rename → {path}"), self._fill(rows)))

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
            self._ui(lambda: (self._log(f"deleted {entry.path}"), self._fill(rows)))

        threading.Thread(target=worker, daemon=True).start()

    def _copy_path(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(entry.path)
            self._log(f"Copied path: {entry.path}")
        except Exception as exc:
            self._log(f"Copy failed: {exc}")

    def _copy_name(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(entry.name)
            self._log(f"Copied name: {entry.name}")
        except Exception as exc:
            self._log(f"Copy failed: {exc}")

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

        def worker() -> None:
            try:
                self.session.download(entry.path, dest)
            except Exception as exc:
                self._ui(
                    lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app)
                )
                return
            self._ui(lambda: self._log(f"Downloaded → {dest}"))

        threading.Thread(target=worker, daemon=True).start()

    def _upload(self) -> None:
        if not self._require_conn():
            return
        paths = filedialog.askopenfilenames(parent=self.app, title=t("scp.upload"))
        if not paths:
            return
        self._upload_paths(list(paths))

    def _upload_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        if not self.session.connected:
            messagebox.showinfo(t("tool.scp.title"), t("scp.need_connect"), parent=self.app)
            return

        from pathlib import Path as _Path

        files = [p for p in paths if _Path(p).is_file()]
        if not files:
            self._log("Drop diabaikan — hanya file (bukan folder) yang di-upload.")
            return

        self._log(f"Upload {len(files)} file…")

        def worker() -> None:
            ok = 0
            for p in files:
                try:
                    remote = self.session.upload(p)
                    ok += 1
                    self._ui(lambda r=remote: self._log(f"Uploaded → {r}"))
                except Exception as exc:
                    self._ui(lambda e=str(exc): self._log(f"Upload fail: {e}"))
            try:
                rows = self.session.list_dir()
            except Exception:
                rows = []
            self._ui(
                lambda: (
                    self._fill(rows),
                    self._log(f"Upload selesai ({ok}/{len(files)})"),
                )
            )

        threading.Thread(target=worker, daemon=True).start()

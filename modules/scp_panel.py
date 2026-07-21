"""SCP / SFTP explorer UI (CustomTkinter)."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

import customtkinter as ctk

from modules.i18n import t
from modules.sftp_session import SftpSession


class ScpPanel:
    """Form koneksi + file explorer SFTP + input perintah SSH."""

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
        self._entries: dict[str, Any] = {}  # iid -> RemoteEntry
        self._busy = False
        self.protocol_var = tk.StringVar(value="SFTP")

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

        def _field(parent: Any, label: str, var: tk.StringVar, width: int, show: str | None = None) -> ctk.CTkEntry:
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

        proto_cell = ctk.CTkFrame(inner, fg_color="transparent")
        proto_cell.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            proto_cell,
            text=t("scp.protocol"),
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=colors["muted"],
        ).pack(anchor="w")
        self.proto_combo = ctk.CTkComboBox(
            proto_cell,
            values=["SSH", "SCP", "SFTP"],
            variable=self.protocol_var,
            width=90,
            height=30,
            state="readonly",
            fg_color=colors["bg"],
            border_color=colors["border"],
            button_color=colors["accent"],
            button_hover_color=colors["accent_dim"],
            dropdown_fg_color=colors["panel"],
            command=self._on_protocol_change,
        )
        self.proto_combo.set("SFTP")
        self.proto_combo.pack(anchor="w", pady=(2, 0))

        _field(inner, t("scp.host"), self.host_var, 160)
        _field(inner, t("scp.port"), self.port_var, 64)
        _field(inner, t("scp.user"), self.user_var, 110)
        _field(inner, t("scp.pass"), self.pass_var, 120, show="•")

        # Sejajar kotak input: label spacer + baris tombol height 30
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

        # --- Explorer toolbar ---
        self.tools = ctk.CTkFrame(content, fg_color="transparent")
        self.tools.pack(fill="x", pady=(0, 6))

        self.path_var = tk.StringVar(value="")
        ctk.CTkLabel(
            self.tools,
            text=t("scp.path"),
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=colors["muted"],
        ).pack(side="left", padx=(0, 6))
        self.path_entry = ctk.CTkEntry(
            self.tools,
            textvariable=self.path_var,
            height=28,
            fg_color=colors["panel"],
            border_color=colors["border"],
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.path_entry.bind("<Return>", lambda _e: self._goto_path())

        def _tbtn(text: str, cmd: Callable[[], None], w: int = 88, color: str | None = None) -> ctk.CTkButton:
            b = ctk.CTkButton(
                self.tools,
                text=text,
                width=w,
                height=28,
                fg_color=color or colors["panel"],
                hover_color=colors.get("accent_dim", colors["accent"]),
                text_color=colors["text"] if not color else colors.get("on_warn", "#1A1400"),
                border_width=1 if not color else 0,
                border_color=colors["border"],
                command=cmd,
            )
            b.pack(side="left", padx=(0, 4))
            return b

        self.btn_hist = _tbtn(t("scp.back"), self._go_back, 80)
        self.btn_up = _tbtn(t("scp.up"), self._go_up, 70)
        self.btn_ref = _tbtn(t("scp.refresh"), self._refresh, 80, colors.get("warn", "#E6B422"))
        self.btn_mkdir = _tbtn(t("scp.new_folder"), self._new_folder, 100)
        self.btn_mkfile = _tbtn(t("scp.new_file"), self._new_file, 90)
        self.btn_upload = _tbtn(t("scp.upload"), self._upload, 80)

        # --- File list + drop zone ---
        self.list_wrap = ctk.CTkFrame(
            content,
            fg_color=colors["panel"],
            corner_radius=10,
            border_width=1,
            border_color=colors["border"],
        )
        self.list_wrap.pack(fill="both", expand=True, pady=(0, 8))
        self.drop_hint = ctk.CTkLabel(
            self.list_wrap,
            text=t("scp.drop_hint"),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=colors["muted"],
            anchor="w",
        )
        self.drop_hint.pack(fill="x", padx=12, pady=(8, 0))
        host = tk.Frame(self.list_wrap, bg=colors["panel"], highlightthickness=0)
        host.pack(fill="both", expand=True, padx=8, pady=8)
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
            rowheight=28,
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
        self.tree.column("name", width=320, minwidth=140, anchor="w", stretch=True)
        self.tree.column("size", width=90, minwidth=60, anchor="e", stretch=False)
        self.tree.column("mtime", width=140, minwidth=100, anchor="w", stretch=False)
        self.tree.column("type", width=80, minwidth=60, anchor="w", stretch=False)

        vsb = ttk.Scrollbar(host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)
        self.tree.tag_configure("odd", background=colors["bg"])
        self.tree.tag_configure("even", background=colors["panel"])
        self.tree.tag_configure("dir", foreground=colors["accent"])

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

        # --- SSH command ---
        self.cmd_row = ctk.CTkFrame(content, fg_color="transparent")
        self.cmd_row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            self.cmd_row,
            text=t("scp.cmd"),
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=colors["muted"],
        ).pack(side="left", padx=(0, 6))
        self.cmd_var = tk.StringVar(value="")
        self.cmd_entry = ctk.CTkEntry(
            self.cmd_row,
            textvariable=self.cmd_var,
            height=30,
            fg_color=colors["panel"],
            border_color=colors["border"],
        )
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.cmd_entry.bind("<Return>", lambda _e: self._run_cmd())
        ctk.CTkButton(
            self.cmd_row,
            text=t("scp.run"),
            width=100,
            height=30,
            fg_color=colors["accent"],
            hover_color=colors["accent_dim"],
            text_color=colors["on_accent"],
            command=self._run_cmd,
        ).pack(side="left")

        self.log_host = ctk.CTkFrame(
            content, fg_color=colors["console_bg"], height=120, corner_radius=8
        )
        self.log_host.pack(fill="x")
        self.log_host.pack_propagate(False)
        self.log_box = ctk.CTkTextbox(
            self.log_host,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="transparent",
            text_color=colors.get("console_fg", colors["text"]),
            wrap="word",
            activate_scrollbars=True,
        )
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)
        self.log_box.configure(state="disabled")
        self._log(t("scp.need_connect"))
        self._log(t("scp.mode_dual"))

        self._setup_drag_drop()
        self._apply_protocol_layout()

        app._scp_session = self.session
        app.console = None

    def _protocol(self) -> str:
        return (self.protocol_var.get() or "SFTP").strip().upper()

    def _on_protocol_change(self, _choice: str | None = None) -> None:
        proto = self._protocol()
        self._log(t("scp.mode_dual") + f"  · preferensi transfer: {proto}")
        self._apply_protocol_layout()
        if self.session.connected:
            self._refresh()

    def _apply_protocol_layout(self) -> None:
        """Selalu dual: explorer (SFTP/SCP) + perintah SSH."""
        try:
            self.tools.pack(fill="x", pady=(0, 6))
            self.list_wrap.pack(fill="both", expand=True, pady=(0, 8))
            self.cmd_row.pack(fill="x", pady=(0, 4))
            self.log_host.pack(fill="x")
            self.log_host.configure(height=120)
        except Exception:
            pass

    def _setup_drag_drop(self) -> None:
        """Aktifkan drag & drop file ke area explorer (Windows)."""
        try:
            import windnd
        except Exception:
            self._log("Drag & drop tidak tersedia (modul windnd). Gunakan tombol Upload.")
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
        except Exception as exc:
            self._log(f"Drag & drop gagal diinisialisasi: {exc}")

    # ----- helpers -----
    def _log(self, text: str) -> None:
        try:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text.rstrip() + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        except Exception:
            pass

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

        def worker() -> None:
            err = None
            proto = self._protocol()
            try:
                self.session.connect(host, port, user, password, protocol=proto)
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
                self._log(f"Connected (dual SSH+SFTP): {user}@{host}:{port}")
                if note:
                    self._log(note)
                banner = getattr(self.session, "last_banner", "") or ""
                if banner:
                    self._log(f"Banner: {banner}")
                self._apply_protocol_layout()
                self._refresh()

            self._ui(done)

        threading.Thread(target=worker, daemon=True).start()

    def _disconnect(self) -> None:
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
        try:
            self.session.disconnect()
        except Exception:
            pass
        self.app._scp_session = None
        self.on_back()

    # ----- listing -----
    def _fill(self, rows: list[Any]) -> None:
        self.tree.delete(*self.tree.get_children())
        self._entries.clear()
        self.path_var.set(self.session.cwd)
        if not rows:
            self._log(t("scp.empty"))
            return
        for idx, row in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            tags = (tag, "dir") if row.is_dir else (tag,)
            iid = self.tree.insert(
                "",
                "end",
                values=(
                    ("📁 " if row.is_dir else "📄 ") + row.name,
                    row.size_label,
                    row.mtime_label,
                    row.type_label,
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
                mode = "SFTP" if self.session.sftp_ok else "shell"
                self._log(f"Explorer ({mode}): {len(rows)} item · {self.session.cwd}")
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

    def _go_back(self) -> None:
        if not self._require_conn():
            return

        def worker() -> None:
            prev = self.session.go_back()
            if prev is None:
                self._ui(lambda: self._log("Tidak ada folder sebelumnya."))
                return
            try:
                rows = self.session.list_dir()
            except Exception as exc:
                self._ui(lambda: self._log(f"Back error: {exc}"))
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
                self.session.chdir(entry.path, record_history=True)
                rows = self.session.list_dir()
            except Exception as exc:
                self._ui(lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app))
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
                self._ui(lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app))
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
                self._ui(lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app))
                return
            self._ui(lambda: (self._log(f"create {path}"), self._fill(rows)))

        threading.Thread(target=worker, daemon=True).start()

    def _rename(self) -> None:
        entry = self._selected()
        if entry is None or not self._require_conn():
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
                self._ui(lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app))
                return
            self._ui(lambda: (self._log(f"rename → {path}"), self._fill(rows)))

        threading.Thread(target=worker, daemon=True).start()

    def _delete(self) -> None:
        entry = self._selected()
        if entry is None or not self._require_conn():
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
                self._ui(lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app))
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
        if entry.is_dir:
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
                self._ui(lambda: messagebox.showerror(t("tool.scp.title"), str(exc), parent=self.app))
                return
            self._ui(lambda: self._log(f"Downloaded → {dest}"))

        threading.Thread(target=worker, daemon=True).start()

    def _upload(self) -> None:
        if not self._require_conn():
            return
        if self._protocol() == "SSH":
            messagebox.showinfo(
                t("tool.scp.title"),
                "Mode SSH tidak untuk transfer file.\nPilih protokol SCP atau SFTP.",
                parent=self.app,
            )
            return
        paths = filedialog.askopenfilenames(parent=self.app, title=t("scp.upload"))
        if not paths:
            return
        self._upload_paths(list(paths))

    def _upload_paths(self, paths: list[str]) -> None:
        """Upload daftar path lokal (dari dialog atau drag & drop)."""
        if not paths:
            return
        if not self.session.connected:
            messagebox.showinfo(t("tool.scp.title"), t("scp.need_connect"), parent=self.app)
            return
        if self._protocol() == "SSH":
            messagebox.showinfo(
                t("tool.scp.title"),
                "Mode SSH tidak untuk transfer file.\nPilih protokol SCP atau SFTP.",
                parent=self.app,
            )
            return

        from pathlib import Path as _Path

        files = [p for p in paths if _Path(p).is_file()]
        if not files:
            self._log("Drop diabaikan — hanya file (bukan folder) yang di-upload.")
            return

        proto = self._protocol()
        self._log(f"Upload {len(files)} file via {proto}…")

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

    def _run_cmd(self) -> None:
        if not self._require_conn():
            return
        cmd = self.cmd_var.get().strip()
        if not cmd:
            return
        self._log(f"$ {cmd}")

        def worker() -> None:
            try:
                code, _out, _err = self.session.exec_command(
                    cmd, on_line=lambda line: self._ui(lambda l=line: self._log(l))
                )
                self._ui(lambda: self._log(f"[exit {code}]"))
            except Exception as exc:
                self._ui(lambda: self._log(f"SSH error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

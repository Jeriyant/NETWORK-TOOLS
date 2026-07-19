"""Embedded Edge WebView2 browser for in-app Speedtest / DNS Test."""

from __future__ import annotations

import ctypes
import os
import tempfile
import threading
from ctypes import wintypes
from pathlib import Path
from tkinter import Frame
from typing import Any, Callable

user32 = ctypes.windll.user32

CLICK_START_JS = """
(function () {
  const nodes = Array.from(document.querySelectorAll('button, a, div, span, input'));
  const btn = nodes.find((el) => {
    const text = ((el.innerText || el.textContent || el.value || '') + '').trim();
    const cls = (el.className || '') + '';
    const id = (el.id || '') + '';
    const aria = (el.getAttribute && (el.getAttribute('aria-label') || '')) || '';
    const hay = (text + ' ' + cls + ' ' + id + ' ' + aria).toLowerCase();
    return (
      /\\bstart\\b/.test(hay) ||
      /\\bgo\\b/.test(hay) ||
      /mulai/.test(hay) ||
      /start-button/.test(hay) ||
      /startbutton/.test(hay)
    );
  });
  if (btn) {
    btn.click();
    return 'clicked';
  }
  return 'notfound';
})();
"""

FIT_PAGE_JS = """
(function () {
  try {
    const html = document.documentElement;
    const body = document.body;
    if (!html || !body) return 'nodoc';

    // Ukur di zoom 1 dulu, lalu perkecil agar seluruh halaman masuk viewport
    html.style.zoom = '1';
    body.style.transform = 'none';
    body.style.zoom = '';

    let style = document.getElementById('nt-fit-style');
    if (!style) {
      style = document.createElement('style');
      style.id = 'nt-fit-style';
      (document.head || html).appendChild(style);
    }
    style.textContent = `
      html, body {
        margin: 0 !important;
        padding: 0 !important;
        box-sizing: border-box !important;
      }
      ::-webkit-scrollbar { width: 0 !important; height: 0 !important; display: none !important; }
      * { scrollbar-width: none !important; }
    `;

    const vw = Math.max(window.innerWidth || 0, html.clientWidth || 0, 1);
    const vh = Math.max(window.innerHeight || 0, html.clientHeight || 0, 1);
    const sw = Math.max(
      body.scrollWidth || 0,
      html.scrollWidth || 0,
      body.offsetWidth || 0,
      html.offsetWidth || 0,
      vw
    );
    const sh = Math.max(
      body.scrollHeight || 0,
      html.scrollHeight || 0,
      body.offsetHeight || 0,
      html.offsetHeight || 0,
      vh
    );

    let z = Math.min(vw / sw, vh / sh);
    if (!isFinite(z) || z <= 0) z = 1;
    // Sedikit margin agar tepi tidak terpotong karena pembulatan
    z = Math.min(z * 0.985, 1);
    if (z > 0.995) z = 1;

    html.style.zoom = String(z);
    html.style.overflow = 'hidden';
    body.style.overflow = 'hidden';
    html.style.width = '100%';
    html.style.height = '100%';
    return String(z);
  } catch (e) {
    return 'err';
  }
})();
"""


def _bootstrap_pythonnet() -> None:
    """Load .NET runtime explicitly (critical for PyInstaller frozen exe)."""
    os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")
    errors: list[str] = []
    try:
        from pythonnet import load

        load("netfx")
        return
    except Exception as exc:
        errors.append(f"load(netfx): {exc}")
    try:
        from clr_loader import get_netfx
        from pythonnet import set_runtime

        set_runtime(get_netfx())
        return
    except Exception as exc:
        errors.append(f"set_runtime(netfx): {exc}")
    try:
        from pythonnet import load

        load("coreclr")
        return
    except Exception as exc:
        errors.append(f"load(coreclr): {exc}")
    raise RuntimeError(
        "Gagal inisialisasi .NET untuk WebView2.\n" + "\n".join(errors)
    )


def _ensure_webview2_refs() -> None:
    _bootstrap_pythonnet()
    import clr
    from webview.util import interop_dll_path

    for platform in ("win-arm64", "win-x64", "win-x86"):
        os.environ["Path"] = os.environ.get("Path", "") + ";" + interop_dll_path(platform)

    clr.AddReference("System.Windows.Forms")
    clr.AddReference(interop_dll_path("Microsoft.Web.WebView2.Core.dll"))
    clr.AddReference(interop_dll_path("Microsoft.Web.WebView2.WinForms.dll"))


def _parse_drawing_color(Color: Any, hex_color: str) -> Any:
    """Convert #RRGGBB to System.Drawing.Color."""
    h = (hex_color or "").strip().lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return Color.FromArgb(255, r, g, b)
    return Color.FromArgb(255, 243, 243, 243)


class EmbeddedBrowser(Frame):
    """Tk Frame hosting Microsoft Edge WebView2 (in-process browser)."""

    def __init__(
        self,
        parent: Any,
        width: int,
        height: int,
        url: str = "",
        on_ready: Callable[[], None] | None = None,
        on_loading: Callable[[bool], None] | None = None,
        fit_page: bool = True,
        background_color: str | None = None,
        **kwargs: Any,
    ) -> None:
        Frame.__init__(self, parent, width=width, height=height, **kwargs)
        _ensure_webview2_refs()

        from System import Uri
        from System.Drawing import Color, Size
        from System.Windows.Forms import Control, DockStyle
        from Microsoft.Web.WebView2.WinForms import CoreWebView2CreationProperties, WebView2

        self._on_ready_cb = on_ready
        self._on_loading_cb = on_loading
        self._url_pending = url
        self._disposed = False
        self._fit_page = fit_page
        self._nav_hooked = False
        self._resize_job: str | None = None
        self._poll_job: str | None = None
        self._last_size = (0, 0)
        self._Size = Size
        self._DockStyle = DockStyle
        self._tk_thread = threading.get_ident()

        # Flags set by WebView2 callbacks (other threads) — NEVER call tk from those threads
        self._flag_core_ready = False
        self._flag_nav_done = False
        self._flag_fit = False
        self._flag_loading: bool | None = True  # tampilkan loading sejak awal
        self._core_ready_handled = False

        self._host = Control()
        self._webview = WebView2()
        props = CoreWebView2CreationProperties()
        cache = Path(tempfile.gettempdir()) / "network_tools_webview2"
        cache.mkdir(parents=True, exist_ok=True)
        props.UserDataFolder = str(cache)
        self._webview.CreationProperties = props
        try:
            self._webview.DefaultBackgroundColor = _parse_drawing_color(
                Color, background_color or "#F3F3F3"
            )
        except Exception:
            pass
        self._host.Controls.Add(self._webview)
        self._webview.Dock = DockStyle.Fill
        self._webview.BringToFront()

        self._chwnd = int(str(self._host.Handle))
        user32.SetParent(self._chwnd, self.winfo_id())
        self._sync_native_size(width, height)

        self.bind("<Destroy>", self._on_destroy)
        self.bind("<Configure>", self._on_resize)
        self._parent_bind_id = None
        try:
            self._parent_for_bind = parent
            self._parent_bind_id = parent.bind("<Configure>", self._on_parent_resize, add="+")
        except Exception:
            self._parent_for_bind = None

        self._webview.CoreWebView2InitializationCompleted += self._on_core_ready
        self._webview.EnsureCoreWebView2Async(None)

        self._Uri = Uri
        self._poll_job = self.after(50, self._poll_webview_flags)
        self.after(120, self._force_stretch)
        self.after(500, self._force_stretch)

    def _on_tk_thread(self) -> bool:
        return threading.get_ident() == self._tk_thread

    def _on_core_ready(self, sender: Any, args: Any) -> None:
        # Runs on WebView2 thread — only set flags / call WebView APIs, never Tk
        try:
            core = sender.CoreWebView2
            if core is not None and not self._nav_hooked:
                core.NavigationStarting += self._on_navigation_starting
                core.NavigationCompleted += self._on_navigation_completed
                self._nav_hooked = True
        except Exception:
            pass
        self._flag_core_ready = True

    def _on_navigation_starting(self, _sender: Any = None, _args: Any = None) -> None:
        self._flag_loading = True

    def _on_navigation_completed(self, _sender: Any = None, _args: Any = None) -> None:
        # Runs on WebView2 thread — never call Tk here
        self._flag_nav_done = True
        self._flag_fit = True
        self._flag_loading = False

    def _poll_webview_flags(self) -> None:
        """Tk-thread poller for WebView2 async events."""
        self._poll_job = None
        if self._disposed:
            return

        if self._flag_loading is not None:
            loading = self._flag_loading
            self._flag_loading = None
            if self._on_loading_cb:
                try:
                    self._on_loading_cb(loading)
                except Exception:
                    pass

        if self._flag_core_ready and not self._core_ready_handled:
            self._core_ready_handled = True
            self._flag_core_ready = False
            url = self._url_pending
            self._url_pending = ""
            if url:
                self.load_url(url)
            self._force_stretch()
            if self._on_ready_cb:
                try:
                    self._on_ready_cb()
                except Exception:
                    pass

        if self._flag_nav_done:
            self._flag_nav_done = False
            self._force_stretch()
            if self._fit_page:
                self.after(400, self.fit_page)
                self.after(1200, self.fit_page)
                self.after(2500, self.fit_page)

        if self._flag_fit:
            self._flag_fit = False
            if self._fit_page:
                self.fit_page()

        if not self._disposed:
            self._poll_job = self.after(100, self._poll_webview_flags)

    def _sync_native_size(self, width: int, height: int) -> None:
        w = max(int(width), 1)
        h = max(int(height), 1)
        if (w, h) == self._last_size:
            return
        self._last_size = (w, h)
        try:
            self._host.Width = w
            self._host.Height = h
            self._host.Size = self._Size(w, h)
            self._webview.Width = w
            self._webview.Height = h
            self._webview.Size = self._Size(w, h)
            self._webview.Dock = self._DockStyle.Fill
        except Exception:
            pass
        try:
            user32.MoveWindow(self._chwnd, 0, 0, w, h, True)
        except Exception:
            pass

    def _frame_client_size(self) -> tuple[int, int]:
        """Ukuran client HWND Tk (akurat di DPI tinggi; hindari WebView kepotong)."""
        try:
            rect = wintypes.RECT()
            if user32.GetClientRect(int(self.winfo_id()), ctypes.byref(rect)):
                w = int(rect.right - rect.left)
                h = int(rect.bottom - rect.top)
                if w >= 50 and h >= 50:
                    return w, h
        except Exception:
            pass
        w = max(int(self.winfo_width()), 1)
        h = max(int(self.winfo_height()), 1)
        if w < 50 or h < 50:
            try:
                w = max(int(self.master.winfo_width()), w)
                h = max(int(self.master.winfo_height()), h)
            except Exception:
                pass
        return w, h

    def _force_stretch(self) -> None:
        if self._disposed or not self._on_tk_thread():
            return
        try:
            self.update_idletasks()
            w, h = self._frame_client_size()
            self._sync_native_size(w, h)
            if self._fit_page:
                self.fit_page()
        except Exception:
            pass

    def _on_parent_resize(self, _event: Any = None) -> None:
        if self._disposed:
            return
        self._schedule_stretch()

    def _on_resize(self, _event: Any = None) -> None:
        if self._disposed:
            return
        self._schedule_stretch()

    def _schedule_stretch(self) -> None:
        if not self._on_tk_thread():
            return
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(40, self._apply_stretch)

    def _apply_stretch(self) -> None:
        self._resize_job = None
        if self._disposed:
            return
        self._force_stretch()

    def _on_destroy(self, _event: Any = None) -> None:
        if self._disposed:
            return
        self._disposed = True
        for job in (self._resize_job, self._poll_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._resize_job = None
        self._poll_job = None
        try:
            if self._parent_for_bind is not None and self._parent_bind_id:
                self._parent_for_bind.unbind("<Configure>", self._parent_bind_id)
        except Exception:
            pass
        try:
            self._webview.Dispose()
        except Exception:
            pass

    def load_url(self, url: str) -> None:
        if self._disposed:
            return
        self._flag_loading = True
        try:
            if self._webview.CoreWebView2 is not None:
                self._webview.Source = self._Uri(url)
            else:
                self._url_pending = url
                self._webview.EnsureCoreWebView2Async(None)
        except Exception:
            self._url_pending = url

    def evaluate_js(self, script: str) -> None:
        if self._disposed:
            return
        try:
            if self._webview.CoreWebView2 is not None:
                self._webview.ExecuteScriptAsync(script)
        except Exception:
            pass

    def fit_page(self) -> None:
        """Sesuaikan halaman agar muat di viewport (CSS zoom), tanpa scrollbar."""
        if self._disposed:
            return
        try:
            self._webview.ZoomFactor = 1.0
        except Exception:
            pass
        self.evaluate_js(FIT_PAGE_JS)

    def click_start(self) -> None:
        self.evaluate_js(CLICK_START_JS)
        if self._fit_page:
            self.fit_page()

"""Windows Administrator / UAC helpers."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(extra_args: list[str] | None = None) -> bool:
    """Restart this process elevated via UAC. Returns True if ShellExecute was invoked."""
    try:
        args = list(sys.argv[1:])
        if extra_args:
            for a in extra_args:
                if a not in args:
                    args.append(a)

        if getattr(sys, "frozen", False):
            executable = sys.executable
            params = " ".join(f'"{a}"' for a in args)
        else:
            executable = sys.executable
            script = str(Path(sys.argv[0]).resolve())
            tail = " ".join(f'"{a}"' for a in args)
            params = f'"{script}" {tail}'.strip()

        # SW_SHOWNORMAL = 1; >32 means success for ShellExecute
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            params,
            None,
            1,
        )
        return int(rc) > 32
    except Exception:
        return False

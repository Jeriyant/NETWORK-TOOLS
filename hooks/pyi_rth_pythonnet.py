# Runtime hook: set pythonnet runtime before any clr import (frozen exe).
import os

os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")
try:
    from pythonnet import load

    load("netfx")
except Exception:
    try:
        from clr_loader import get_netfx
        from pythonnet import set_runtime

        set_runtime(get_netfx())
    except Exception:
        pass

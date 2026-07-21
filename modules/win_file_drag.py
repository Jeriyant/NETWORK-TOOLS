"""Drag file lokal ke Windows Explorer (OLE FileDrop) via pythonnet / WinForms."""

from __future__ import annotations

from typing import Sequence


def drag_files(paths: Sequence[str]) -> bool:
    """Mulai drag-and-drop OLE FileDrop. Return True jika DoDragDrop dipanggil."""
    files = [p for p in paths if p]
    if not files:
        return False

    import clr  # type: ignore

    clr.AddReference("System")
    clr.AddReference("System.Windows.Forms")

    from System import Array, String  # type: ignore
    from System.Windows.Forms import (  # type: ignore
        DataFormats,
        DataObject,
        DragDropEffects,
        Form,
        FormBorderStyle,
    )

    arr = Array[String]([String(p) for p in files])
    data = DataObject(DataFormats.FileDrop, arr)

    form = Form()
    form.Opacity = 0
    form.ShowInTaskbar = False
    form.FormBorderStyle = getattr(FormBorderStyle, "None")
    form.Width = 1
    form.Height = 1
    try:
        form.Show()
        form.DoDragDrop(data, DragDropEffects.Copy)
        return True
    finally:
        try:
            form.Close()
            form.Dispose()
        except Exception:
            pass

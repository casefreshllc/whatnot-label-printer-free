"""The few things about the app window that differ between Windows and Mac.

Everything else in the app is shared. Windows keeps exactly the look it had before.
"""
import os
import subprocess
import sys
import tkinter as tk

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

if IS_WINDOWS:
    UI_FAMILY, MONO_FAMILY, BASE = "Segoe UI", "Consolas", 9
elif IS_MAC:
    # The real Mac system font is looked up from Tk once the window exists (see _family()).
    UI_FAMILY, MONO_FAMILY, BASE = None, "Menlo", 13
else:
    UI_FAMILY, MONO_FAMILY, BASE = "DejaVu Sans", "DejaVu Sans Mono", 9

# The key you hold to pick several rows in a list.
MULTI_SELECT_KEY = "⌘" if IS_MAC else "Ctrl"


def _family():
    """The UI font family. On Mac: the same system font the native controls use."""
    global UI_FAMILY
    if UI_FAMILY is None:
        try:
            from tkinter import font as tkfont
            UI_FAMILY = tkfont.nametofont("TkDefaultFont").actual("family")
        except Exception:
            return "Helvetica Neue"   # no window yet; try again next time
    return UI_FAMILY


def ui_font(delta=0, bold=False):
    """App font, `delta` points bigger than the normal size."""
    fam = _family()
    return (fam, BASE + delta, "bold") if bold else (fam, BASE + delta)


def mono_font(delta=0):
    return (MONO_FAMILY, BASE + delta)


def open_folder(path):
    path = str(path)
    if IS_WINDOWS:
        os.startfile(path)
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class _MacColorButton(tk.Label):
    """Mac buttons ignore background colors (you'd get white text on a white button), so on
    Mac the colored buttons are drawn as clickable labels instead. Accepts the same options
    the app uses on tk.Button: bg, fg, activebackground, activeforeground, command, text."""

    def __init__(self, parent, command=None, activebackground=None, activeforeground=None,
                 **kw):
        kw.setdefault("padx", 12)
        kw.setdefault("pady", 6)
        kw.setdefault("cursor", "pointinghand")
        super().__init__(parent, **kw)
        self._command = command
        self._bg = kw.get("bg", self.cget("bg"))
        self._fg = kw.get("fg", self.cget("fg"))
        self._active_bg = activebackground or self._bg
        self._active_fg = activeforeground or self._fg
        self._hover = False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._clicked)

    def _set_hover(self, on):
        self._hover = on
        super().configure(bg=self._active_bg if on else self._bg,
                          fg=self._active_fg if on else self._fg)

    def _clicked(self, event):
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        if inside and self._command:
            self._command()

    def configure(self, cnf=None, **kw):
        if "command" in kw:
            self._command = kw.pop("command")
        if "activebackground" in kw:
            self._active_bg = kw.pop("activebackground")
        if "activeforeground" in kw:
            self._active_fg = kw.pop("activeforeground")
        if "bg" in kw:
            self._bg = kw["bg"]
        if "fg" in kw:
            self._fg = kw["fg"]
        result = super().configure(cnf, **kw)
        self._set_hover(self._hover)
        return result

    config = configure


def color_button(parent, **kw):
    """A button with a solid background color that shows on both Windows and Mac."""
    if IS_MAC:
        return _MacColorButton(parent, **kw)   # width is in characters on both, so it carries over
    return tk.Button(parent, **kw)

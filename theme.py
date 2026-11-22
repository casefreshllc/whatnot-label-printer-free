"""Light and dark color themes for the app window.

Light mode uses the system's own look ("vista" on Windows, exactly as before; "aqua" on Mac). Windows' look ignores custom
colors on buttons, tabs and scrollbars, so dark mode switches to the "clam" style, which lets
every part of the window be colored. Colors were picked so all text keeps strong contrast
against its background (WCAG AA or better).
"""
import sys
import tkinter as tk
from tkinter import ttk

LIGHT = {
    "name": "light",
    "bg": "#f0f0f0",        # window background
    "surface": "#ffffff",   # lists, text boxes, inputs
    "surface_alt": "#e6e6e6",
    "fg": "#1a1a1a",        # normal text
    "muted": "#555555",     # hint text
    "border": "#b8b8b8",
    "select_bg": "#0a64ad", # selected row
    "select_fg": "#ffffff",
    "ok": "#256b29",        # green "Connected" text
    "warn": "#8f5500",      # orange "Waiting" text
    "bad": "#c62828",       # red problem text
}

DARK = {
    "name": "dark",
    "bg": "#1e1f22",
    "surface": "#2b2d31",
    "surface_alt": "#383a40",
    "fg": "#e8e8e8",
    "muted": "#a3a6ad",
    "border": "#4a4d55",
    "select_bg": "#3d6fb4",
    "select_fg": "#ffffff",
    "ok": "#6cd47a",
    "warn": "#ffb74d",
    "bad": "#ff6b6b",
}

import platform_ui as pui

def _ui_font():
    return pui.ui_font()


def _set_title_bar_dark(root, dark):
    """Make the window's title bar match: Windows 10/11, and Mac."""
    if sys.platform == "darwin":
        # Force the Mac window to light or dark, whatever macOS itself is set to, so the
        # title bar and native parts match the app's own setting.
        try:
            root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", root._w,
                         "darkaqua" if dark else "aqua")
        except tk.TclError:
            pass
        return
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (newer, older Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        # Windows only repaints the title bar on a resize; nudge it.
        w, h = root.winfo_width(), root.winfo_height()
        if w > 1 and h > 1:
            root.geometry(f"{w + 1}x{h}")
            root.update_idletasks()
            root.geometry(f"{w}x{h}")
    except Exception:
        pass


def apply(root, dark):
    """Switch the whole window to the light or dark theme. Returns the color palette used,
    so the app can color its own widgets (status text, the capture box, etc.)."""
    style = ttk.Style(root)
    names = style.theme_names()
    c = DARK if dark else LIGHT
    # Set the window's light/dark appearance first, so the Mac look draws to match.
    _set_title_bar_dark(root, dark)

    if not dark and "vista" in names:
        style.theme_use("vista")          # Windows' normal look, unchanged
        native = True
    elif not dark and "aqua" in names:
        style.theme_use("aqua")           # the Mac's normal look
        native = True
        # Use the Mac's own window color so plain (non-themed) parts blend in.
        c = dict(LIGHT, bg="systemWindowBackgroundColor")
    else:
        style.theme_use("clam")
        native = False

    # Hint text, used by the gray helper labels.
    style.configure("Muted.TLabel", foreground=c["muted"])

    if not native:
        style.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["surface"],
                        bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"],
                        troughcolor=c["surface"], selectbackground=c["select_bg"],
                        selectforeground=c["select_fg"], insertcolor=c["fg"], font=_ui_font())
        style.map(".", foreground=[("disabled", c["muted"])])
        style.configure("TFrame", background=c["bg"])
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        style.configure("Muted.TLabel", background=c["bg"], foreground=c["muted"])

        style.configure("TButton", background=c["surface_alt"], foreground=c["fg"],
                        bordercolor=c["border"], lightcolor=c["surface_alt"],
                        darkcolor=c["surface_alt"], focuscolor=c["select_bg"], padding=(8, 3))
        style.map("TButton",
                  background=[("pressed", c["surface"]), ("active", c["border"])],
                  lightcolor=[("pressed", c["surface"]), ("active", c["border"])],
                  darkcolor=[("pressed", c["surface"]), ("active", c["border"])])

        style.configure("TCheckbutton", background=c["bg"], foreground=c["fg"],
                        indicatorbackground=c["surface"], indicatorforeground=c["fg"],
                        focuscolor=c["bg"])
        style.map("TCheckbutton",
                  background=[("active", c["bg"])],
                  indicatorbackground=[("pressed", c["surface_alt"]), ("selected", c["select_bg"])],
                  indicatorforeground=[("selected", c["select_fg"])])

        style.configure("TRadiobutton", background=c["bg"], foreground=c["fg"],
                        indicatorbackground=c["surface"], indicatorforeground=c["fg"],
                        focuscolor=c["bg"])
        style.map("TRadiobutton",
                  background=[("active", c["bg"])],
                  indicatorbackground=[("pressed", c["surface_alt"]), ("selected", c["select_bg"])],
                  indicatorforeground=[("selected", c["select_fg"])])

        style.configure("TCombobox", fieldbackground=c["surface"], background=c["surface_alt"],
                        foreground=c["fg"], arrowcolor=c["fg"], bordercolor=c["border"],
                        lightcolor=c["surface"], darkcolor=c["surface"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", c["surface"])],
                  foreground=[("readonly", c["fg"])],
                  selectbackground=[("readonly", c["surface"])],
                  selectforeground=[("readonly", c["fg"])],
                  background=[("active", c["border"])])

        style.configure("TEntry", fieldbackground=c["surface"], foreground=c["fg"],
                        insertcolor=c["fg"], bordercolor=c["border"],
                        lightcolor=c["surface"], darkcolor=c["surface"])
        style.map("TEntry", bordercolor=[("focus", c["select_bg"])],
                  lightcolor=[("focus", c["select_bg"])])

        style.configure("TNotebook", background=c["bg"], bordercolor=c["border"],
                        lightcolor=c["bg"], darkcolor=c["bg"])
        style.configure("TNotebook.Tab", background=c["surface_alt"], foreground=c["muted"],
                        bordercolor=c["border"], lightcolor=c["surface_alt"],
                        darkcolor=c["surface_alt"], padding=(12, 4))
        style.map("TNotebook.Tab",
                  background=[("selected", c["surface"])],
                  foreground=[("selected", c["fg"])],
                  lightcolor=[("selected", c["surface"])],
                  darkcolor=[("selected", c["surface"])])

        style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                        foreground=c["fg"], bordercolor=c["border"],
                        lightcolor=c["surface"], darkcolor=c["surface"], rowheight=22)
        style.map("Treeview",
                  background=[("selected", c["select_bg"])],
                  foreground=[("selected", c["select_fg"])])
        style.configure("Treeview.Heading", background=c["surface_alt"], foreground=c["fg"],
                        bordercolor=c["border"], lightcolor=c["surface_alt"],
                        darkcolor=c["surface_alt"], relief="flat")
        style.map("Treeview.Heading", background=[("active", c["border"])])

        for orient in ("Vertical", "Horizontal"):
            style.configure(f"{orient}.TScrollbar", background=c["surface_alt"],
                            troughcolor=c["bg"], bordercolor=c["bg"], arrowcolor=c["fg"],
                            lightcolor=c["surface_alt"], darkcolor=c["surface_alt"])
            style.map(f"{orient}.TScrollbar", background=[("active", c["border"])])

        style.configure("Status.TLabel", background=c["surface"], foreground=c["fg"])

    # Plain (non-ttk) parts of the window.
    root.configure(background=c["bg"])
    # Dropdown lists of comboboxes created from now on.
    root.option_add("*TCombobox*Listbox.background", c["surface"])
    root.option_add("*TCombobox*Listbox.foreground", c["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["select_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["select_fg"])

    return c


def color_combobox_dropdown(combobox, c):
    """The dropdown list of an existing combobox doesn't pick up option_add; color it directly."""
    try:
        popdown = combobox.tk.eval(f"ttk::combobox::PopdownWindow {combobox}")
        combobox.tk.call(f"{popdown}.f.l", "configure",
                         "-background", c["surface"], "-foreground", c["fg"],
                         "-selectbackground", c["select_bg"], "-selectforeground", c["select_fg"])
    except tk.TclError:
        pass


def color_text_box(text, c):
    text.configure(background=c["surface"], foreground=c["fg"], insertbackground=c["fg"],
                   selectbackground=c["select_bg"], selectforeground=c["select_fg"],
                   highlightbackground=c["border"], highlightcolor=c["select_bg"])


def contrast(fg, bg):
    """WCAG contrast ratio between two #rrggbb colors (used by the tests)."""
    def lum(h):
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)

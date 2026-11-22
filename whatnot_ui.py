"""The "Whatnot API…" window: connect HammerSlip to the seller's Whatnot account with a
personal access token."""
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

import platform_ui as pui
import theme
import whatnot_api


def fit(win, root):
    """Size the window to its contents (Windows' title-bar coloring can otherwise freeze it at
    an early, too-small size), never bigger than the screen; centre it over the main window
    the first time."""
    win.update_idletasks()
    w = min(win.winfo_reqwidth(), win.winfo_screenwidth() - 40)
    h = min(win.winfo_reqheight(), win.winfo_screenheight() - 80)
    if getattr(win, "_placed", False):
        win.geometry(f"{w}x{h}")
        return
    win._placed = True
    x = root.winfo_rootx() + max(0, (root.winfo_width() - w) // 2)
    y = root.winfo_rooty() + max(0, (root.winfo_height() - h) // 3)
    x = max(0, min(x, win.winfo_screenwidth() - w - 20))
    y = max(0, min(y, win.winfo_screenheight() - h - 60))
    win.geometry(f"{w}x{h}+{x}+{y}")


class WhatnotApiWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        c = app.colors
        s = whatnot_api.load_settings()
        self.title("Whatnot API")
        self.configure(background=c["bg"])
        dark = bool(app.dark_mode.get())
        self.transient(app.root)
        self.resizable(False, False)

        box = ttk.Frame(self, padding=(24, 20, 24, 18))
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Connect your Whatnot account",
                  font=pui.ui_font(4, bold=True)).pack(anchor="w")
        ttk.Label(box, wraplength=440, justify="left", style="Muted.TLabel", text=(
            "HammerSlip checks your Whatnot orders about once a second and prints a label as "
            "soon as each payment goes through. Create a personal access token in Whatnot's "
            "developer dashboard with read access to orders, shows and customers, and paste "
            "it here.")).pack(anchor="w", pady=(6, 0))
        link = tk.Label(box, text="How to create a token", cursor="hand2", bg=c["bg"],
                        fg="#7fb2ff" if c["name"] == "dark" else "#0a58b0",
                        font=(pui.ui_font()[0], pui.ui_font()[1], "underline"))
        link.bind("<Button-1>", lambda e: webbrowser.open(whatnot_api.TOKEN_HELP_URL))
        link.pack(anchor="w", pady=(4, 10))

        ttk.Label(box, text="Personal access token").pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(2, 8))
        self.token = ttk.Entry(row, width=48, show="•")
        self.token.pack(side="left", fill="x", expand=True)
        self.token.insert(0, s["token"])
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Show", variable=self.show_var,
                        command=lambda: self.token.config(show="" if self.show_var.get() else "•")
                        ).pack(side="left", padx=(8, 0))

        self.live_only = tk.BooleanVar(value=s["live_only"])
        ttk.Checkbutton(box, text="Only print sales from my live show", variable=self.live_only
                        ).pack(anchor="w")

        self.result = tk.Label(box, text="", anchor="w", justify="left", wraplength=440,
                               bg=c["bg"], fg=c["muted"] if "muted" in c else c["fg"],
                               font=pui.ui_font())
        self.result.pack(anchor="w", fill="x", pady=(10, 0))

        btns = ttk.Frame(box)
        btns.pack(fill="x", pady=(14, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Save", command=self._save, default="active").pack(
            side="right", padx=(0, 8))
        self.test_btn = ttk.Button(btns, text="Test connection", command=self._test)
        self.test_btn.pack(side="left")
        self.bind("<Escape>", lambda e: self.destroy())
        fit(self, app.root)
        self.after(30, lambda: (theme._set_title_bar_dark(self, dark), fit(self, app.root)))
        self.grab_set()
        self.token.focus_set()

    def _say(self, text, level="muted"):
        c = self.app.colors
        self.result.config(text=text, fg=c.get(level, c.get("fg", "black")))
        fit(self, self.app.root)

    def _test(self):
        tok = self.token.get().strip()
        if not tok:
            self._say("Paste your token first.", "bad")
            return
        self.test_btn.config(state="disabled", text="Testing…")
        self._say("Checking with Whatnot…")

        def work():
            try:
                user, warn = whatnot_api.test_token(tok)
                out = (f"Connected as @{user}. " + (warn or "Everything HammerSlip needs is "
                                                    "allowed."), "warn" if warn else "ok")
            except whatnot_api.ApiError as e:
                out = (e.message, "bad")
            self.app.events.put(("call", lambda: self._tested(*out)))
        threading.Thread(target=work, daemon=True).start()

    def _tested(self, text, level):
        if self.winfo_exists():
            self.test_btn.config(state="normal", text="Test connection")
            self._say(text, level)

    def _save(self):
        s = {"token": self.token.get().strip(), "live_only": bool(self.live_only.get())}
        if not s["token"]:
            self._say("Paste your token first.", "bad")
            return
        whatnot_api.save_settings(s)
        self.destroy()
        self.app._api_restart()

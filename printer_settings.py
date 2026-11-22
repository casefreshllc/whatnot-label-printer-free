"""The Printer Settings window, and how printer settings are stored.

Settings are saved per printer in config.json under "printers":
    "printers": {"Brother_QL_810W": {"label_size": "29x62mm", "orientation": "landscape",
                                     "flip": false, "driver_options": {"CutMedia": "EndOfPage"}}}
"""
import base64
import io
import tkinter as tk
from tkinter import ttk

from PIL import Image

import labelsizes
import platform_ui as pui
import printer
from label import render_label

DEFAULTS = {"label_size": labelsizes.DEFAULT_KEY, "orientation": "landscape", "flip": False,
            "driver_options": {}}

# Friendlier names for options Brother's (and other) Mac drivers offer. Anything not listed
# here is still shown, under the driver's own name.
FRIENDLY = {
    "cupsPrintQuality": ("Print quality", {"Normal": "Normal", "High": "High (slower)",
                                           "Draft": "Draft"}),
    "CutMedia": ("Cutting", {"None": "Don't cut", "EndOfPage": "Cut after each label",
                             "EndOfJob": "Cut after the last label of a print job"}),
    "MediaType": ("Label type", {"labels": "Die-cut labels", "roll": "Continuous roll",
                                 "any": "Automatic"}),
    "ColorModel": ("Color", {"Gray": "Black & white", "RGB": "Color", "CMYK": "Color"}),
    "Resolution": ("Resolution", {}),
}
HIDDEN = {"pagesize", "media", "pageregion"}   # label size is chosen in its own box


def get_settings(cfg, printer_name):
    saved = (cfg.get("printers") or {}).get(printer_name or "", {})
    out = dict(DEFAULTS, **saved)
    out["driver_options"] = dict(saved.get("driver_options") or {})
    return out


def save_settings(cfg, printer_name, settings):
    cfg.setdefault("printers", {})[printer_name or ""] = settings


def label_pixels(settings):
    size = labelsizes.get(settings["label_size"])
    return size.pixels(portrait=settings["orientation"] == "portrait")


def finish_image(img, settings):
    """Apply the 'flip upside down' setting to a drawn label."""
    return img.rotate(180) if settings.get("flip") else img


def print_options(settings, cfg=None):
    """What printer.print_label needs from these settings."""
    opts = dict((cfg or {}).get("mac_print") or {})
    opts.update(label_size=settings["label_size"],
                portrait=settings["orientation"] == "portrait",
                driver_options=settings.get("driver_options") or {})
    return opts


class PrinterSettingsDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.printer_name = app.printer_name.get()
        self.settings = get_settings(app.cfg, self.printer_name)
        c = app.colors
        self.title("Printer Settings")
        self.configure(background=c["bg"])
        # Title bar follows the app's dark mode setting (Mac and Windows 10/11).
        # (On Mac this only takes effect once the window exists on screen, so do it again then.)
        import theme
        dark = bool(app.dark_mode.get())
        theme._set_title_bar_dark(self, dark)
        self.after(30, lambda: theme._set_title_bar_dark(self, dark))
        self.transient(app.root)
        self.resizable(True, True)

        # Buttons stay pinned at the bottom; everything above them scrolls if the window is
        # too small for the screen (e.g. Windows with display scaling turned up).
        bf = ttk.Frame(self, padding=(14, 8, 14, 14))
        bf.pack(side="bottom", fill="x")
        self._buttons = bf
        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)
        self._canvas = tk.Canvas(body, highlightthickness=0, borderwidth=0,
                                 background=c["bg"])
        self._vsb = ttk.Scrollbar(body, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vsb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        outer = ttk.Frame(self._canvas, padding=(14, 14, 14, 4))
        self._outer = outer
        win = self._canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind("<Configure>",
                   lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfigure(
            win, width=max(e.width, outer.winfo_reqwidth())))
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._scroll(-1))    # Linux
        self.bind("<Button-5>", lambda e: self._scroll(1))

        ttk.Label(outer, text="Printer:", font=pui.ui_font(bold=True)).grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text=self.printer_name or "(no printer selected)").grid(
            row=0, column=1, columnspan=2, sticky="w", padx=(8, 0))

        # --- label size
        ttk.Label(outer, text="Label size:", font=pui.ui_font(bold=True)).grid(
            row=1, column=0, sticky="w", pady=(12, 0))
        names = [s.name for s in labelsizes.SIZES]
        self.size_var = tk.StringVar()
        size_box = ttk.Combobox(outer, textvariable=self.size_var, values=names,
                                state="readonly", width=18)
        # Rounded to tenths, two sizes can show the same name (0.9" × 0.9"), so the choice is
        # tracked by its position in the list, not by its name.
        self.size_box = size_box
        size_box.current(labelsizes.SIZES.index(labelsizes.get(self.settings["label_size"])))
        size_box.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(12, 0))
        size_box.bind("<<ComboboxSelected>>", lambda e: self._changed())
        self.size_note = ttk.Label(outer, text="", style="Muted.TLabel", wraplength=300)
        self.size_note.grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(12, 0))

        # --- orientation
        ttk.Label(outer, text="Orientation:", font=pui.ui_font(bold=True)).grid(
            row=2, column=0, sticky="nw", pady=(12, 0))
        self.orient_var = tk.StringVar(value=self.settings["orientation"])
        of = ttk.Frame(outer)
        of.grid(row=2, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(12, 0))
        ttk.Radiobutton(of, text="Landscape: text runs along the long side",
                        variable=self.orient_var, value="landscape",
                        command=self._changed).pack(anchor="w")
        ttk.Radiobutton(of, text="Portrait: text runs along the short side",
                        variable=self.orient_var, value="portrait",
                        command=self._changed).pack(anchor="w")
        self.flip_var = tk.BooleanVar(value=bool(self.settings.get("flip")))
        ttk.Checkbutton(of, text="Flip upside down (rotate 180°)", variable=self.flip_var,
                        command=self._changed).pack(anchor="w", pady=(4, 0))

        # --- preview
        ttk.Label(outer, text="Preview:", font=pui.ui_font(bold=True)).grid(
            row=3, column=0, sticky="nw", pady=(12, 0))
        # Start with a blank picture so the box is sized in pixels from the beginning
        # (an empty label is sized in characters, which threw off the window size on Windows).
        self._preview_img = tk.PhotoImage(width=360, height=230)
        self.preview = tk.Label(outer, image=self._preview_img, background=c["surface_alt"],
                                borderwidth=0)
        self.preview.grid(row=3, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(12, 0))

        # --- driver options (Mac only)
        row = 4
        self.option_vars = {}
        if not pui.IS_WINDOWS:
            self.driver = printer.driver_options(self.printer_name)
            shown = [o for o in self.driver if o["key"].lower() not in HIDDEN
                     and len(o["choices"]) > 1]
            if shown:
                ttk.Label(outer, text="Printer options:", font=pui.ui_font(bold=True)).grid(
                    row=row, column=0, sticky="nw", pady=(14, 0))
                df = ttk.Frame(outer)
                df.grid(row=row, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(14, 0))
                for i, o in enumerate(shown):
                    title, names_map = FRIENDLY.get(o["key"], (o["label"], {}))
                    shown_names = [names_map.get(ch, ch) for ch in o["choices"]]
                    current = self.settings["driver_options"].get(o["key"], o["default"])
                    if current not in o["choices"]:
                        current = o["default"]
                    var = tk.StringVar(value=names_map.get(current, current))
                    ttk.Label(df, text=title + ":").grid(row=i, column=0, sticky="w", pady=2)
                    ttk.Combobox(df, textvariable=var, values=shown_names, state="readonly",
                                 width=34).grid(row=i, column=1, sticky="w", padx=(8, 0), pady=2)
                    self.option_vars[o["key"]] = (var, dict(zip(shown_names, o["choices"])))
            elif self.printer_name:
                ttk.Label(outer, text="This printer's driver didn't list any options.",
                          style="Muted.TLabel").grid(row=row, column=1, columnspan=2,
                                                     sticky="w", padx=(8, 0), pady=(14, 0))

        # --- buttons
        ttk.Button(bf, text="Test print", command=self._test_print).pack(side="left")
        ttk.Button(bf, text="Save", command=self._save).pack(side="right")
        ttk.Button(bf, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 8))

        self._changed()
        self.bind("<Escape>", lambda e: self.destroy())
        self._fit_to_screen()
        self.grab_set()

    def _fit_to_screen(self):
        """Open at the size the contents need, but never bigger than the screen; show the
        scrollbar only if everything doesn't fit."""
        self.update_idletasks()
        need_w = self._outer.winfo_reqwidth()
        need_h = self._outer.winfo_reqheight()
        buttons_h = self._buttons.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        room_h = sh - 140 - buttons_h            # leave space for the taskbar / menu bar
        scroll = need_h > room_h
        if scroll:
            self._vsb.pack(side="right", fill="y")
        sb_w = self._vsb.winfo_reqwidth() if scroll else 0
        w = min(need_w + sb_w, sw - 60)
        h = min(need_h, room_h) + buttons_h
        self.geometry(f"{w}x{h}")
        self.minsize(min(420, w), min(260, h))
        self._can_scroll = scroll

    def _scroll(self, units):
        if getattr(self, "_can_scroll", False) or \
                self._outer.winfo_height() > self._canvas.winfo_height():
            self._canvas.yview_scroll(units, "units")

    def _on_wheel(self, event):
        if pui.IS_WINDOWS:
            self._scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1))
        else:
            self._scroll(-event.delta if abs(event.delta) < 120 else int(-event.delta / 120))

    # ------------------------------------------------------------------
    def _current(self):
        """The settings as currently chosen in the window (not yet saved)."""
        i = self.size_box.current()
        size = labelsizes.SIZES[i] if i >= 0 else labelsizes.get(labelsizes.DEFAULT_KEY)
        opts = {}
        for key, (var, to_value) in self.option_vars.items():
            opts[key] = to_value.get(var.get(), var.get())
        return {"label_size": size.key, "orientation": self.orient_var.get(),
                "flip": bool(self.flip_var.get()), "driver_options": opts}

    def _changed(self):
        st = self._current()
        size = labelsizes.get(st["label_size"])
        # Note when the printer's driver doesn't list this size.
        note = ""
        if not pui.IS_WINDOWS and self.printer_name:
            paper = next((o["choices"] for o in getattr(self, "driver", [])
                          if o["key"].lower() in ("pagesize", "media")), None)
            if paper is not None and not labelsizes.driver_name_for(size, paper):
                note = "This printer doesn't list this size; it will be sent as a custom size."
        if size.key == "4x6in" and "QL" in (self.printer_name or "").upper():
            note = "Brother QL printers can't print 4\" × 6\" (max width 2.4\"). Use it with a 4\" printer like a Rollo."
        self.size_note.configure(text=note)
        self._draw_preview(st)

    def _draw_preview(self, st):
        img = render_label("buyer_username", self.app.cfg, item="Item name goes here",
                           footer=self.app.cfg.get("label", {}).get("footer_text", ""),
                           size=label_pixels(st))
        img = finish_image(img, st).convert("L")
        box_w, box_h = 360, 230
        # Show the label at its real proportions, on a dark-gray "table".
        scale = min((box_w - 24) / img.width, (box_h - 24) / img.height)
        shown = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
        canvas = Image.new("L", (box_w, box_h), 110)
        x, y = (box_w - shown.width) // 2, (box_h - shown.height) // 2
        canvas.paste(shown, (x, y))
        buf = io.BytesIO()
        canvas.save(buf, "PNG")
        self._preview_img = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        self.preview.configure(image=self._preview_img, width=box_w, height=box_h)

    def _test_print(self):
        self.app._test_print(settings=self._current())

    def _save(self):
        save_settings(self.app.cfg, self.printer_name, self._current())
        self.app._settings_saved()
        self.destroy()

"""HammerSlip — main window."""
import csv
import json
import queue
import socket
from collections import deque
import threading
import os
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog

from label import render_label
from rules import should_print, GIVEAWAY_CHOICES, giveaway_mode_from
import theme
import platform_ui as pui
import printer_settings
import printer
import diagnostics
import updater
import whatnot_api
import whatnot_ui

import paths
from paths import CONFIG_PATH, SALES_LOG, OLD_LOGS_DIR, DATA_DIR
APP_DIR = DATA_DIR
SALES_LOG_HEADER = ["timestamp", "username", "status", "item", "price", "order"]
# Only one copy of the app at a time: the first one holds this local port.
INSTANCE_PORT = 8765




def _archive_name(path):
    """Name an old log after when its first sale happened (or when the file was
    last changed, if it has no sales), e.g. sales_log_2026-10-01_2330.csv."""
    when = None
    try:
        with open(path, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if len(rows) > 1 and rows[1]:
            when = datetime.fromisoformat(rows[1][0])
    except (OSError, ValueError, IndexError):
        pass
    if when is None:
        when = datetime.fromtimestamp(path.stat().st_mtime)
    base = f"sales_log_{when:%Y-%m-%d_%H%M}"
    dest = OLD_LOGS_DIR / f"{base}.csv"
    n = 2
    while dest.exists():
        dest = OLD_LOGS_DIR / f"{base}_{n}.csv"
        n += 1
    return dest


def _retire_old_sales_log():
    """Every time the app opens, start a fresh sales_log.csv. The previous one
    (and any old logs left in the main folder) move to the "Sales Logs" folder."""
    for stray in APP_DIR.glob("sales_log_old_*.csv"):
        OLD_LOGS_DIR.mkdir(exist_ok=True)
        stray.rename(OLD_LOGS_DIR / stray.name)
    if not SALES_LOG.exists():
        return
    with open(SALES_LOG, encoding="utf-8") as f:
        has_sales = len(f.read().strip().splitlines()) > 1
    if not has_sales:
        SALES_LOG.unlink()  # header only, nothing worth keeping
        return
    OLD_LOGS_DIR.mkdir(exist_ok=True)
    SALES_LOG.rename(_archive_name(SALES_LOG))


def _merge_defaults(cfg, defaults):
    """Fill in any settings missing from cfg (e.g. added in a newer version) from defaults."""
    for key, value in defaults.items():
        if key not in cfg:
            cfg[key] = value
        elif isinstance(value, dict) and isinstance(cfg[key], dict):
            _merge_defaults(cfg[key], value)
    return cfg


def load_config():
    """The settings, with anything missing filled in from the defaults. If the settings file
    can't be read (e.g. it was damaged), it's kept as config.damaged.json and the defaults are
    used, so the app still opens."""
    paths.ensure_config()
    try:
        with open(paths.DEFAULT_CONFIG, encoding="utf-8") as f:
            defaults = json.load(f)
    except (OSError, ValueError):
        defaults = {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("not a settings object")
    except (OSError, ValueError):
        try:
            if CONFIG_PATH.exists():
                CONFIG_PATH.replace(CONFIG_PATH.with_name("config.damaged.json"))
        except OSError:
            pass
        cfg = {}
    return _merge_defaults(cfg, defaults)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        _retire_old_sales_log()
        self.events = queue.Queue()      # background threads -> GUI
        self.print_jobs = queue.Queue()  # GUI -> printer thread
        self.waiting_rows = {}           # Whatnot order id -> its "waiting for payment" row
        self.row_items = {}  # tree row -> item title, for printing/reprinting
        self.row_giveaway = set()  # tree rows that are giveaway wins
        # Buyers who already have a label since the app was opened (sale or giveaway),
        # and the ones whose label actually came out.
        self.labeled_users = set()
        self.printed_ok = set()
        self.event_log = deque(maxlen=500)   # recent messages, for Save diagnostics
        self.update_info = None              # newer version found by the update check
        self.api_feed = None                 # Whatnot API watcher, when that's on
        self.api_state = ("", "warn")

        root.title(f"{paths.APP_NAME}  v{paths.VERSION}")
        icon = paths.CODE_DIR / "icon.ico"
        if icon.exists():
            try:
                root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass
        root.geometry("1000x600")
        root.minsize(700, 480)

        self.armed = tk.BooleanVar(value=False)
        self.dry_run = tk.BooleanVar(value=self.cfg.get("dry_run", False))
        lr = self.cfg.setdefault("label_rules", {})
        self.print_every_sale = tk.BooleanVar(value=lr.get("print_every_sale", False))
        self.giveaway_mode = giveaway_mode_from(self.cfg)
        self.giveaway_choice = tk.StringVar(
            value=next(t for t, m in GIVEAWAY_CHOICES if m == self.giveaway_mode))
        self.dark_mode = tk.BooleanVar(value=self.cfg.get("dark_mode", False))
        self.footer_text = tk.StringVar(value=self.cfg.get("label", {}).get("footer_text", ""))
        self._footer_save_job = None
        self.colors = theme.LIGHT
        self.printer_name = tk.StringVar()
        self.status = tk.StringVar(value="Ready.")
        self.conn = tk.StringVar(value="Connecting to Whatnot…")
        self.count = 0

        self._build()
        self._watch_messages()
        self._apply_theme()
        self._refresh_printers()
        threading.Thread(target=self._printer_loop, daemon=True).start()
        self.instance_lock = self._claim_single_instance()
        root.after(100, self._pump)
        root.after(1000, self._update_conn)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        if not os.environ.get("WNLP_SELF_TEST"):
            root.after(500, lambda: self._api_restart(ask_if_missing=True))
            root.after(4000, lambda: self._check_updates(manual=False))
        if pui.IS_MAC:
            # ⌘Q / "Quit" in the Mac menu bar: close down cleanly and save settings.
            root.createcommand("tk::mac::Quit", self._on_close)

    # ---------- layout ----------
    def _build(self):
        pad = dict(padx=8, pady=4)
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)

        self.conn_title = ttk.Label(top, text="Whatnot:")
        self.conn_title.grid(row=0, column=0, sticky="w")
        self.conn_lbl = tk.Label(top, textvariable=self.conn, anchor="w", fg=theme.LIGHT["warn"],
                                 font=pui.ui_font(1, bold=True))
        self.conn_lbl.grid(row=0, column=1, columnspan=2, sticky="ew", padx=4)

        ttk.Label(top, text="Printer:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.printer_box = ttk.Combobox(top, textvariable=self.printer_name, state="readonly")
        self.printer_box.grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
        self.printer_box.bind("<<ComboboxSelected>>", self._printer_chosen)
        ttk.Button(top, text="Refresh", command=self._refresh_printers).grid(row=1, column=2, pady=(6, 0))
        ttk.Button(top, text="Printer Settings…", command=self._open_printer_settings).grid(
            row=1, column=3, padx=(6, 0), pady=(6, 0))
        top.columnconfigure(1, weight=1)

        ctl = ttk.Frame(self.root)
        ctl.pack(fill="x", **pad)
        self.arm_btn = pui.color_button(ctl, text="▶  Start printing sales", width=24, font=pui.ui_font(2, bold=True),
                                 bg="#2e7d32", fg="white", activebackground="#1b5e20",
                                 command=self._toggle_armed)
        self.arm_btn.pack(side="left")
        ttk.Button(ctl, text="Test print", command=self._test_print).pack(side="left", padx=6)
        ttk.Button(ctl, text="Print a name…", command=self._manual_print).pack(side="left")
        ttk.Checkbutton(ctl, text="Don't print (save image only)", variable=self.dry_run,
                        command=self._dry_toggled).pack(side="left", padx=(16, 0))
        ttk.Checkbutton(ctl, text="Dark Mode", variable=self.dark_mode,
                        command=self._dark_toggled).pack(side="right")

        rules = ttk.Frame(self.root)
        rules.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(rules, text="Label rules:", font=pui.ui_font(bold=True)).pack(side="left")
        ttk.Checkbutton(rules, text="Print Every Sale", variable=self.print_every_sale,
                        command=self._rules_toggled).pack(side="left", padx=(8, 4))
        ttk.Label(rules, text="(off = one label per buyer per session)",
                  style="Muted.TLabel").pack(side="left")
        ttk.Label(rules, text="Giveaways:", font=pui.ui_font(bold=True)).pack(side="left", padx=(20, 4))
        self.giveaway_box = ttk.Combobox(rules, textvariable=self.giveaway_choice, state="readonly",
                                         width=18, values=[t for t, _ in GIVEAWAY_CHOICES])
        self.giveaway_box.pack(side="left")
        self.giveaway_box.bind("<<ComboboxSelected>>", lambda e: self._rules_toggled())

        foot = ttk.Frame(self.root)
        foot.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(foot, text="Bottom line on labels:", font=pui.ui_font(bold=True)).pack(side="left")
        entry = ttk.Entry(foot, textvariable=self.footer_text, width=42)
        entry.pack(side="left", padx=(8, 8))
        ttk.Label(foot, text="(e.g. your channel name. Leave empty for none.)",
                  style="Muted.TLabel").pack(side="left")
        self.footer_text.trace_add("write", self._footer_changed)

        sales_tab = ttk.Frame(self.root)
        sales_tab.pack(fill="both", expand=True, **pad)
        bar = ttk.Frame(sales_tab)
        bar.pack(fill="x", pady=(4, 4))
        pui.color_button(bar, text="🖨  Print selected", font=pui.ui_font(1, bold=True), width=18,
                  bg="#1565c0", fg="white", activebackground="#0d47a1", activeforeground="white",
                  command=self._print_selected).pack(side="left")
        ttk.Label(bar, text=f"Double-click a sale to print it. {pui.MULTI_SELECT_KEY}-click or Shift-click to pick "
                            "several.", style="Muted.TLabel").pack(side="left", padx=10)
        cols = ("time", "user", "status", "item", "price")
        self.tree = ttk.Treeview(sales_tab, columns=cols, show="headings", selectmode="extended")
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", lambda e: self._print_selected())
        for c, w, label in [("time", 80, "Time"), ("user", 160, "Buyer"),
                            ("status", 150, "Label"), ("item", 420, "Item"),
                            ("price", 90, "Price")]:
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, stretch=(c == "item"))
        sb = ttk.Scrollbar(sales_tab, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=8)
        ttk.Button(btns, text="Open files folder", command=self._open_files_folder).pack(side="left")
        ttk.Button(btns, text="Save diagnostics…", command=self._save_diagnostics).pack(
            side="left", padx=(6, 0))
        self.update_btn = ttk.Button(btns, text="Check for updates",
                                     command=lambda: self._check_updates(manual=True))
        self.update_btn.pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="Whatnot API…", command=lambda: whatnot_ui.WhatnotApiWindow(self)
                   ).pack(side="left", padx=(6, 0))
        self.count_lbl = ttk.Label(btns, text="Labels this session: 0")
        self.count_lbl.pack(side="right")

        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w",
                  style="Status.TLabel").pack(fill="x", side="bottom")

    # ---------- printers ----------
    def _refresh_printers(self):
        names = printer.list_printers()
        self.printer_box["values"] = names
        found = printer.find_printer(self.cfg.get("printer_name", ""))
        if found:
            self.printer_name.set(found)
        elif names:
            self.printer_name.set(names[0])
        if not names:
            self.status.set("No printers found. Add your label printer to the computer, or use "
                            "'Don't print' to test.")

    def _printer_chosen(self, _event=None):
        """Remember the printer picked from the list for next time."""
        self.cfg["printer_name"] = self.printer_name.get()
        save_config(self.cfg)

    # ---------- the Whatnot line ----------
    def _update_conn(self):
        text, level = self.api_state
        self.conn.set(text or "Connecting to Whatnot…")
        self.conn_state = level
        self._update_conn_color()
        self.root.after(1000, self._update_conn)

    def _claim_single_instance(self):
        """Hold a local port so a second copy of the app can tell this one is open."""
        lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            lock.bind(("127.0.0.1", INSTANCE_PORT))
            lock.listen(1)
            return lock
        except OSError:
            lock.close()
            messagebox.showerror(
                "Already running",
                "HammerSlip is already open in another window. Close it and try again.")
            return None

    def _update_conn_color(self):
        self.conn_lbl.config(fg=self.colors[getattr(self, "conn_state", "warn")])

    def _toggle_armed(self):
        self.armed.set(not self.armed.get())
        if self.armed.get():
            self.arm_btn.config(text="■  Stop printing", bg="#c62828", activebackground="#8e0000")
            self.status.set("Printing is ON. New sales will print automatically.")
        else:
            self.arm_btn.config(text="▶  Start printing sales", bg="#2e7d32", activebackground="#1b5e20")
            self.status.set("Printing is OFF. Sales are listed but not printed.")

    def _apply_theme(self):
        """Color the whole window for light or dark mode."""
        self.colors = theme.apply(self.root, self.dark_mode.get())
        c = self.colors
        self.conn_lbl.configure(background=c["bg"])
        theme.color_combobox_dropdown(self.printer_box, c)
        self._update_conn_color()

    def _dark_toggled(self):
        self.cfg["dark_mode"] = self.dark_mode.get()
        save_config(self.cfg)
        self._apply_theme()

    def _footer_changed(self, *_):
        # Labels printed from now on use the new text right away; save it a moment later.
        self.cfg.setdefault("label", {})["footer_text"] = self.footer_text.get().strip()
        if self._footer_save_job:
            self.root.after_cancel(self._footer_save_job)
        self._footer_save_job = self.root.after(600, lambda: save_config(self.cfg))

    def _rules_toggled(self):
        self.giveaway_mode = next(m for t, m in GIVEAWAY_CHOICES if t == self.giveaway_choice.get())
        self.cfg["label_rules"] = {
            "print_every_sale": self.print_every_sale.get(),
            "giveaways": self.giveaway_mode,
        }
        save_config(self.cfg)

    def _dry_toggled(self):
        self.cfg["dry_run"] = self.dry_run.get()
        save_config(self.cfg)

    # ---------- events from the background threads ----------
    def _pump(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.status.set(payload)
                elif kind == "call":
                    payload()
                elif kind == "update":
                    self._update_checked(*payload)
                elif kind == "update_progress":
                    self._update_progress(*payload)
                elif kind == "update_ready":
                    self._update_downloaded(payload)
                elif kind == "update_failed":
                    self._update_failed(payload)
                elif kind == "count":
                    self.count_lbl.config(text=f"Labels this session: {payload}")
                elif kind == "printed":
                    iid, result = payload
                    if self.tree.exists(iid):
                        self.tree.set(iid, "status", result)
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _handle_sale(self, user, title, price, is_giveaway):
        """A new paid sale from Whatnot: print it or list it."""
        if is_giveaway and self.giveaway_mode == "never":
            self._add_row(user, "not printed (giveaway)", title, "order", price, giveaway=True)
            return
        if not self.armed.get():
            self._add_row(user, "not printed (off)", title, "order", price, giveaway=is_giveaway)
            return
        key = user.lower()
        if should_print(is_giveaway, key in self.labeled_users,
                        self.print_every_sale.get(), self.giveaway_mode):
            # Any label (sale or giveaway) counts as this buyer's label for the session.
            self.labeled_users.add(key)
            self._queue_print(user, title, "sale", "order", price, giveaway=is_giveaway)
        else:
            self._add_row(user, "already has a label", title, "order", price,
                          giveaway=is_giveaway)

    # ---------- Whatnot API ----------
    def _api_on(self):
        return self.api_feed is not None

    def _api_restart(self, ask_if_missing=False):
        """Start (or restart) the Whatnot connection with the saved token."""
        if self.api_feed:
            self.api_feed.stop()
            self.api_feed = None
        s = whatnot_api.load_settings()
        if s["token"] and not self._self_testing():
            self.api_state = ("Connecting to Whatnot…", "warn")
            self.api_feed = whatnot_api.Feed(
                s["token"], s["live_only"],
                on_sale=lambda sale: self.events.put(("call", lambda: self._on_api_sale(sale))),
                on_state=lambda text, level: self.events.put(
                    ("call", lambda: self._api_state_changed(text, level)))).start()
        else:
            self.api_state = ("Not connected. Click 'Whatnot API…' at the bottom to connect your "
                              "Whatnot account.", "bad")
            if ask_if_missing and not self._self_testing():
                whatnot_ui.WhatnotApiWindow(self)

    def _api_state_changed(self, text, level):
        self.api_state = (text, level)

    def _on_api_sale(self, sale):
        """An order from Whatnot whose payment has settled (or is taking a while)."""
        if not self._api_on():
            return
        user = sale.get("user") or ""
        title = sale.get("title") or ""
        price = sale.get("price", "")
        oid = sale.get("id")
        outcome = sale.get("outcome", "paid")
        self.event_log.append((datetime.now(), f"[whatnot] order {oid} {sale.get('type')} "
                               f"{sale.get('status')} -> {outcome} (created {sale.get('created_at')})"))
        if outcome == "waiting":
            self.waiting_rows[oid] = self._add_row(user or "?", "waiting for payment…", title,
                                                   "order", price, giveaway=bool(sale.get("giveaway")))
            return
        row = self.waiting_rows.pop(oid, None)
        if row and self.tree.exists(row):
            self.tree.delete(row)
        if outcome == "failed":
            self._add_row(user or "?", "✗ payment failed", title, "order", price,
                          giveaway=bool(sale.get("giveaway")))
            stamp = datetime.now().strftime("%I:%M:%S %p").lstrip("0")
            self.status.set(f"{stamp}  @{user or '?'}'s payment didn't go through, so no label "
                            f"was printed.")
            return
        if outcome == "gave_up":
            self._add_row(user or "?", "✗ never paid", title, "order", price)
            return
        if not user:
            self._add_row("?", "⚠ no buyer name", title or "(order without a buyer name)",
                          "order", price)
            self.status.set("Whatnot didn't send the buyer's username. Give your token "
                            "permission to read customers (Whatnot API…).")
            return
        self._handle_sale(user, title, price, bool(sale.get("giveaway")))

    # ---------- printing ----------
    def _add_row(self, user, status, text, where="", price="", giveaway=False):
        iid = self.tree.insert("", 0, values=(datetime.now().strftime("%I:%M:%S %p").lstrip("0"),
                                              user, status, text, price))
        self.event_log.append((datetime.now(), f"[sales list] {user} | {status} | {text} | {price}"))
        self.row_items[iid] = text if where == "order" else ""
        if giveaway:
            self.row_giveaway.add(iid)
        new_file = not SALES_LOG.exists()
        with open(SALES_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(SALES_LOG_HEADER)
            w.writerow([datetime.now().isoformat(timespec="seconds"), user, status, text, price, where])
        return iid

    def _queue_print(self, user, text, source, where="", price="", giveaway=False):
        iid = self._add_row(user, "printing…", text, where, price, giveaway=giveaway)
        self.print_jobs.put((iid, user, source, None))

    def _printer_loop(self):
        while True:
            iid, user, source, override = self.print_jobs.get()
            try:
                giveaway = iid in self.row_giveaway
                pname = self.printer_name.get()
                st = override or printer_settings.get_settings(self.cfg, pname)
                # Under the name: the item name (for giveaways, the giveaway's title, in bold).
                img = render_label(user, self.cfg, item=self.row_items.get(iid, ""), giveaway=giveaway,
                                   size=printer_settings.label_pixels(st))
                img = printer_settings.finish_image(img, st)
                path = printer.save_copy(img, user)
                if self.dry_run.get():
                    result = "saved (no print)"
                    if source != "test":
                        self.labeled_users.add(user.lower())
                        self.printed_ok.add(user.lower())
                else:
                    name = self.printer_name.get()
                    if not name:
                        raise RuntimeError("no printer selected")
                    printer.print_label(img, name, job_name=f"HammerSlip - {user}",
                                        options=printer_settings.print_options(st, self.cfg))
                    result = "printed"
                    if source != "test":
                        self.labeled_users.add(user.lower())
                        self.printed_ok.add(user.lower())
                    if source != "test":
                        self.count += 1
                        self.events.put(("count", self.count))
            except Exception as e:
                result = f"ERROR: {e}"
                self.events.put(("status", f"Print failed for {user}: {e}"))
                if source == "sale" and user.lower() not in self.printed_ok:
                    # They have no label that actually came out, so let their next
                    # purchase print.
                    self.labeled_users.discard(user.lower())
            self.events.put(("printed", (iid, result)))

    def _test_print(self, settings=None):
        """A test label. `settings` lets the Printer Settings window test choices before saving."""
        iid = self._add_row("test_buyer123", "printing…", "(test print)", "", "")
        self.print_jobs.put((iid, "test_buyer123", "test", settings))

    def _open_printer_settings(self):
        if not self.printer_name.get() and not self.dry_run.get():
            messagebox.showinfo("Printer Settings", "Pick a printer first (or click Refresh).",
                                parent=self.root)
            return
        printer_settings.PrinterSettingsDialog(self)

    def _settings_saved(self):
        save_config(self.cfg)
        st = printer_settings.get_settings(self.cfg, self.printer_name.get())
        from labelsizes import get as size_of
        self.status.set(f"Printer settings saved: {size_of(st['label_size']).name} labels, "
                        f"{st['orientation']}{', flipped' if st.get('flip') else ''}.")

    def _manual_print(self):
        name = simpledialog.askstring("Print a name", "Buyer username:", parent=self.root)
        if name and name.strip():
            self._queue_print(name.strip().lstrip("@"), "(printed by hand)", "manual")

    def _on_double_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:  # ignore double-clicks on the column headings
            self.tree.selection_set(row)
            self._print_selected()

    def _print_selected(self):
        """Print (or reprint) the chosen sales, oldest first, updating their rows."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Print selected", "Click a sale in the list first.")
            return
        for iid in sorted(sel, key=self.tree.index, reverse=True):
            user = self.tree.set(iid, "user")
            if user == "?":
                messagebox.showinfo("Print selected", "That row has no buyer name. Check the order "
                                    "in Whatnot and use 'Print a name…' instead.")
                continue
            self.tree.set(iid, "status", "printing…")
            self.print_jobs.put((iid, user, "list", None))

    # ---------- recent messages (for diagnostics) ----------
    def _watch_messages(self):
        last = {"status": None, "whatnot": None}

        def note(name, var):
            def cb(*_):
                text = var.get()
                if text != last[name]:
                    last[name] = text
                    self.event_log.append((datetime.now(), f"[{name}] {text}"))
            return cb
        self.status.trace_add("write", note("status", self.status))
        self.conn.trace_add("write", note("whatnot", self.conn))

    def _self_testing(self):
        return bool(os.environ.get("WNLP_SELF_TEST"))

    # ---------- diagnostics ----------
    def _save_diagnostics(self):
        ans = messagebox.askyesnocancel(
            "Save diagnostics",
            "This saves a diagnostics file to send to support. It has the app's settings, "
            "versions, printer details and recent messages, with buyers' usernames left out.\n\n"
            "Also include this session's sales log? It helps with sales that didn't print, "
            "but contains buyers' usernames.",
            parent=self.root)
        if ans is None:
            return
        try:
            path = diagnostics.save(self, include_sales=ans)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Save diagnostics", f"Couldn't save the diagnostics file:\n{e}",
                                 parent=self.root)
            return
        self.status.set(f"Diagnostics saved: {path.name}")
        pui.open_folder(path.parent)
        messagebox.showinfo("Save diagnostics",
                            f"Saved {path.name} in the Diagnostics folder (now open).\n\n"
                            "Email that file to support.", parent=self.root)

    # ---------- updates ----------
    def _check_updates(self, manual):
        if manual:
            self.update_btn.config(state="disabled", text="Checking…")

        def work():
            try:
                self.events.put(("update", (updater.check(), None, manual)))
            except updater.UpdateError as e:
                self.events.put(("update", (None, str(e), manual)))
        threading.Thread(target=work, daemon=True).start()

    def _update_checked(self, info, error, manual):
        self.update_btn.config(state="normal", text="Check for updates")
        if error:
            if manual:
                messagebox.showinfo("Check for updates",
                                    f"Couldn't check for updates right now.\n\n{error}",
                                    parent=self.root)
            return
        latest = str(info.get("version", ""))
        if not updater.is_newer(latest):
            if manual:
                messagebox.showinfo("Check for updates",
                                    f"You have the latest version ({paths.VERSION}).", parent=self.root)
            return
        self.update_info = info
        self.update_btn.config(text=f"Update to {latest}")
        if not manual:
            self.status.set(f"Version {latest} is available. Click 'Update to {latest}' "
                            f"at the bottom when you're not in a show.")
            return
        asset = info.get(updater.platform_key() or "", None)
        if not asset:
            messagebox.showinfo("Check for updates",
                                f"Version {latest} is available, but not for this computer yet.",
                                parent=self.root)
            return
        warn = ("\n\nPrinting is ON. Updating closes the app, so sales won't print until it "
                "reopens (about a minute).") if self.armed.get() else ""
        if not messagebox.askyesno(
                "Update available",
                f"Version {latest} is available (you have {paths.VERSION}).\n\n"
                f"Update now? The app will download it, close, update and reopen by itself. "
                f"Your settings and sales logs are kept.{warn}", parent=self.root):
            return
        self._start_download(asset, latest)

    def _start_download(self, asset, latest):
        win = tk.Toplevel(self.root)
        win.title("Updating")
        win.resizable(False, False)
        win.transient(self.root)
        win.configure(background=self.colors["bg"])
        ttk.Label(win, text=f"Downloading version {latest}…").pack(padx=20, pady=(16, 6), anchor="w")
        self._upd_bar = ttk.Progressbar(win, length=320, mode="determinate", maximum=100)
        self._upd_bar.pack(padx=20, pady=(0, 6))
        self._upd_text = ttk.Label(win, text="", style="Muted.TLabel")
        self._upd_text.pack(padx=20, pady=(0, 16), anchor="w")
        win.protocol("WM_DELETE_WINDOW", lambda: None)   # can't close mid-download
        self._upd_win = win
        self.update_btn.config(state="disabled")

        def work():
            try:
                path = updater.download(asset, progress=lambda d, t: self.events.put(
                    ("update_progress", (d, t))))
                self.events.put(("update_ready", path))
            except updater.UpdateError as e:
                self.events.put(("update_failed", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _update_progress(self, done, total):
        if total:
            self._upd_bar.config(value=done * 100 / total)
        self._upd_text.config(text=f"{done / 1e6:.1f} MB" + (f" of {total / 1e6:.1f} MB" if total else ""))

    def _update_failed(self, error):
        if getattr(self, "_upd_win", None):
            self._upd_win.destroy()
            self._upd_win = None
        self.update_btn.config(state="normal")
        messagebox.showerror("Update", f"The update didn't install.\n\n{error}", parent=self.root)

    def _update_downloaded(self, path):
        self._upd_text.config(text="Installing… the app will reopen by itself.")
        self.root.update_idletasks()
        try:
            updater.install(path)
        except Exception as e:  # noqa: BLE001
            self._update_failed(str(e))
            return
        self.root.after(800, self._on_close)

    def _open_files_folder(self):
        pui.open_folder(paths.DATA_DIR)

    def _on_close_save(self):
        if self._footer_save_job:
            self.root.after_cancel(self._footer_save_job)
            save_config(self.cfg)

    def _on_close(self):
        self._on_close_save()
        if self.api_feed:
            self.api_feed.stop()
        if self.instance_lock:
            self.instance_lock.close()
        self.root.destroy()


def _self_test(app, out_path):
    """Used by the automated build (never in normal use): check the built app works on this
    computer, switch to dark mode for a second screenshot, write a report and quit."""
    import os
    import platform
    import traceback
    report = {"platform": platform.platform(), "tk": app.root.tk.call("info", "patchlevel")}

    def step1():
        try:
            from label import _FALLBACKS_BOLD, _FALLBACKS_REGULAR
            report["theme_light"] = ttk.Style(app.root).theme_use()
            report["label_font_bold"] = next((f for f in _FALLBACKS_BOLD if os.path.exists(f)), None)
            report["label_font_regular"] = next((f for f in _FALLBACKS_REGULAR if os.path.exists(f)), None)
            t0 = __import__("time").monotonic()
            report["printers"] = printer.list_printers()
            report["printer_lookup_seconds"] = round(__import__("time").monotonic() - t0, 2)
            img = render_label("selftest_buyer", app.cfg, item="FREE XBOX", giveaway=True,
                               footer="Thanks for watching!")
            img.save(paths.DATA_DIR / "selftest_label.png")
            if not pui.IS_WINDOWS:
                pdf = printer.label_pdf(img)
                report["label_pdf_bytes"] = pdf.stat().st_size
                pdf.unlink()
            report["data_dir"] = str(paths.DATA_DIR)
            report["giveaway_choices"] = [t for t, _ in GIVEAWAY_CHOICES]
            app.footer_text.set("Thanks for watching!")
            # Send a real test print through the printer (on the build machine, a stand-in
            # printer that never prints), so the whole printing path gets exercised.
            app._refresh_printers()
            report["selected_printer"] = app.printer_name.get()
            if app.printer_name.get():
                app.dry_run.set(False)
                printer_settings.save_settings(app.cfg, app.printer_name.get(), dict(
                    printer_settings.DEFAULTS, label_size="29x62mm"))
                app._test_print()
            app._add_row("tidepodsgud", "printed", "FREE XBOX", "order", "Giveaway", giveaway=True)
            app._add_row("nbaumamn808", "printed", "Fully Functional Device #4", "order", "$235")
        except Exception:
            report["error"] = traceback.format_exc()
        app.root.after(6000, step2)

    def step2():
        try:
            app.root.update_idletasks()
            report["window_shown"] = bool(app.root.winfo_ismapped())
            report["window_size"] = f"{app.root.winfo_width()}x{app.root.winfo_height()}"
            report["start_button"] = {"kind": app.arm_btn.winfo_class(),
                                      "bg": str(app.arm_btn.cget("bg")),
                                      "fg": str(app.arm_btn.cget("fg"))}
        except Exception:
            report["window_error"] = traceback.format_exc()
        app.dark_mode.set(True)
        app._apply_theme()
        report["theme_dark"] = ttk.Style(app.root).theme_use()
        try:
            dlg = printer_settings.PrinterSettingsDialog(app)
            report["settings_window_options"] = list(dlg.option_vars)
            app._selftest_dialog = dlg
        except Exception:
            report["settings_window_error"] = traceback.format_exc()
        app.root.after(6000, finish)

    def finish():
        try:
            report["sales_rows"] = [app.tree.item(i, "values")[1:3] for i in app.tree.get_children()]
            report["printing_log"] = printer.PRINT_LOG.read_text(encoding="utf-8")[-2000:] \
                if printer.PRINT_LOG.exists() else None
        except Exception:
            report["finish_error"] = traceback.format_exc()
        dlg = getattr(app, "_selftest_dialog", None)
        if dlg is not None:
            dlg.destroy()
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        app.dark_mode.set(False)
        app.cfg["dark_mode"] = False
        app.cfg.setdefault("label", {})["footer_text"] = ""
        save_config(app.cfg)
        app._on_close()

    app.root.after(1500, step1)


def main():
    import os
    import sys
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    app = App(root)
    if os.environ.get("WNLP_SELF_TEST"):
        _self_test(app, os.environ["WNLP_SELF_TEST"])
    root.mainloop()


if __name__ == "__main__":
    main()

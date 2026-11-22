"""Saves a diagnostics file (a .zip) to send to support when something isn't working.

It contains what's needed to see what happened, and nothing more:
  info.txt           app version, operating system, printers, the Whatnot connection's
                     status (never its token), label settings
  events.txt         the app's recent messages (Whatnot line, status bar, sales list,
                     each order's payment status)
  config.json        the app's settings
  printing_log.txt   what was sent to the printer (the most recent part)
  printer_options    (Mac) the printer driver's options
Buyer usernames are only included (the sales log) if asked for.
"""
import json
import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import paths
import printer

DIAG_DIR = paths.DATA_DIR / "Diagnostics"


def _tail(path, max_bytes=300_000):
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return data[-max_bytes:].decode("utf-8", "replace")




def _hide_buyers(text, app):
    """Replace every buyer username the app has seen with [buyer]."""
    names = set(app.labeled_users)
    try:
        names |= {str(app.tree.item(i, "values")[1]) for i in app.tree.get_children()}
    except Exception:  # noqa: BLE001
        pass
    for name in sorted((n for n in names if n and n != "?"), key=len, reverse=True):
        text = re.sub(rf"(?i)(?<![\w.]){re.escape(name)}(?![\w])", "[buyer]", text)
    return text


def _api_line(app):
    """The Whatnot connection's status (never the token)."""
    try:
        if not app._api_on():
            return "not connected"
        return app.api_state[0]
    except Exception as e:  # noqa: BLE001
        return f"(couldn't read: {e})"


def save(app, include_sales=False):
    """Write the diagnostics .zip and return its path. `app` is the running App."""
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now()
    out = DIAG_DIR / f"diagnostics_{stamp:%Y-%m-%d_%H%M%S}.zip"

    try:
        printers = printer.list_printers()
    except Exception as e:  # noqa: BLE001 - diagnostics must never fail on this
        printers = [f"(couldn't list printers: {e})"]
    pname = app.printer_name.get()
    info = [
        f"Saved:              {stamp:%Y-%m-%d %H:%M:%S}",
        f"App version:        {paths.VERSION}",
        f"Whatnot:            {_api_line(app)}",
        f"System:             {platform.platform()}  ({platform.machine()})",
        f"Python:             {sys.version.split()[0]}",
        f"Data folder:        {paths.DATA_DIR}",
        "",
        f"Printing on:        {app.armed.get()}   Don't print (save image only): {app.dry_run.get()}",
        f"Print Every Sale:   {app.print_every_sale.get()}   "
        f"Giveaways: {app.giveaway_choice.get()}",
        "",
        f"Selected printer:   {pname or '(none)'}",
        "Printers:           " + ("; ".join(printers) or "(none found)"),
    ]

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.txt", "\n".join(info) + "\n")
        events = "\n".join(f"{t:%H:%M:%S}  {text}" for t, text in app.event_log) + "\n"
        if not include_sales:
            events = _hide_buyers(events, app)
        z.writestr("events.txt", events)
        z.writestr("config.json", json.dumps(app.cfg, indent=2))
        log = _tail(printer.PRINT_LOG)
        if log and not include_sales:
            # Print jobs are named "HammerSlip - <buyer>" (before 1.7.0, "Whatnot - <buyer>").
            log = re.sub(r"((?:HammerSlip|Whatnot) - )\S+", r"\1[buyer]", _hide_buyers(log, app))
        if log:
            z.writestr("printing_log.txt", log)
        if not sys.platform.startswith("win") and pname:
            try:
                out_text = printer._run(["lpoptions", "-p", pname, "-l"], timeout=8).stdout
                z.writestr("printer_options.txt", out_text)
            except Exception:  # noqa: BLE001
                pass
        if include_sales:
            if paths.SALES_LOG.exists():
                z.write(paths.SALES_LOG, "sales_log.csv")
    return out

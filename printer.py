"""Sends a label image to the label printer.

Windows: through the normal Windows printer driver (exactly as before).
Mac:     through the Mac's printing system (CUPS) using the printer's own macOS driver.
         The label is sent as a PDF page that is exactly the label's size, so nothing gets
         scaled or cropped, and the matching paper size is picked from the driver's list.
"""
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    import win32print
    import win32ui
    import win32con
    from PIL import ImageWin

from PIL import Image

from paths import LABELS_DIR as OUT_DIR, DATA_DIR
import labelsizes

PRINT_LOG = DATA_DIR / "printing_log.txt"

# The label's physical size, and the resolution the label image is drawn at.
LABEL_MM = (62, 29)
DPI = 300


# ---------------------------------------------------------------- shared
def find_printer(preferred):
    """Exact name if installed, else the first printer whose name contains QL-810 / QL_810."""
    names = list_printers()
    if preferred in names:
        return preferred
    for n in names:
        if "QL810" in re.sub(r"[^A-Z0-9]", "", n.upper()):
            return n
    return None


def save_copy(img, username):
    OUT_DIR.mkdir(exist_ok=True)
    safe = "".join(c for c in username if c.isalnum() or c in "-_.")[:40]
    path = OUT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{safe}.png"
    img.save(path)
    return path


def list_printers():
    return _win_list_printers() if IS_WINDOWS else _cups_list_printers()


def print_label(img, printer_name, job_name="Whatnot label", options=None):
    """Print `img` on the label.

    options:
      "label_size":     key from labelsizes (e.g. "29x62mm"), default the 2.44" x 1.14" label
      "portrait":       True if the image was drawn tall (text along the short side)
      "driver_options": Mac: {driver option: choice} from the Printer Settings window
      "media":          Mac: force this paper size name (advanced; overrides label_size)
    """
    if IS_WINDOWS:
        return _win_print(img, printer_name, job_name)
    return _cups_print(img, printer_name, job_name, options or {})


# ---------------------------------------------------------------- Windows
def _win_list_printers():
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(flags)]


def _win_print(img, printer_name, job_name):
    """Print `img` scaled to fill the label, keeping its proportions."""
    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)
    try:
        page_w = hdc.GetDeviceCaps(win32con.HORZRES)
        page_h = hdc.GetDeviceCaps(win32con.VERTRES)

        src = img.convert("RGB")
        # If the driver hands us a portrait page, rotate so the text runs along the long side.
        if (page_w < page_h) != (src.width < src.height):
            src = src.rotate(90, expand=True)

        scale = min(page_w / src.width, page_h / src.height)
        dw, dh = int(src.width * scale), int(src.height * scale)
        x, y = (page_w - dw) // 2, (page_h - dh) // 2

        hdc.StartDoc(job_name)
        hdc.StartPage()
        ImageWin.Dib(src).draw(hdc.GetHandleOutput(), (x, y, x + dw, y + dh))
        hdc.EndPage()
        hdc.EndDoc()
    finally:
        hdc.DeleteDC()


# ---------------------------------------------------------------- Mac (CUPS)
def _run(cmd, timeout=15):
    # English messages, so the output can be read the same way on any Mac language setting.
    import os
    env = dict(os.environ, LC_ALL="C", LANG="C")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def _log(text):
    try:
        with open(PRINT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
    except OSError:
        pass


def _cups_list_printers():
    """Printers already added on this Mac (System Settings → Printers & Scanners).
    Uses "lpstat -p", which only asks the Mac's own print system. ("lpstat -e" would also
    search the network for printers, which makes macOS ask for Local Network permission.)"""
    try:
        r = _run(["lpstat", "-p"], timeout=8)   # "printer NAME is idle.  enabled since ..."
        return [line.split()[1] for line in r.stdout.splitlines()
                if line.startswith("printer ") and len(line.split()) > 1]
    except (OSError, subprocess.SubprocessError):
        return []


def driver_options(printer_name):
    """Everything the Mac printer driver lets you set (the same list the ⌘P dialog shows),
    e.g. [{"key": "CutMedia", "label": "CutMedia", "choices": [...], "default": "EndOfPage"}].
    Empty on Windows or if the printer can't be read."""
    if IS_WINDOWS or not printer_name:
        return []
    try:
        out = _run(["lpoptions", "-p", printer_name, "-l"], timeout=8).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_driver_options(out)


def parse_driver_options(text):
    opts = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        head, rest = line.split(":", 1)
        key, _, label = head.partition("/")
        choices, default = [], None
        for c in rest.split():
            if c.startswith("*"):
                c = c[1:]
                default = c
            choices.append(c)
        if key.strip() and choices:
            opts.append({"key": key.strip(), "label": (label or key).strip(),
                         "choices": choices, "default": default or choices[0]})
    return opts


def driver_paper_sizes(printer_name):
    """The paper size names the printer's driver offers, e.g. ["29x62mm", "29x90mm", ...]."""
    for o in driver_options(printer_name):
        if o["key"].lower() in ("pagesize", "media"):
            return o["choices"]
    return []


def pick_paper_size(sizes, label_mm=LABEL_MM):
    """Choose the driver's paper size for this label: one that mentions both 62 and 29."""
    want = {float(n) for n in label_mm}
    def nums(name):
        return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", name)}
    exact = [s for s in sizes if want <= nums(s)]
    if exact:
        # Prefer the plainest name (e.g. "62x29" over "62x29mm_Custom").
        return sorted(exact, key=len)[0]
    return None


def media_page_mm(media):
    """The page (width, height) in mm that a driver paper-size name stands for, e.g.
    "29x62mm" -> (29, 62), "Custom.4x6in" -> (101.6, 152.4), "w288h432" -> (101.6, 152.4).
    None if the name can't be read."""
    if not media:
        return None
    name = media.split(".", 1)[1] if media.lower().startswith("custom.") else media
    m = re.fullmatch(r"\s*w(\d+(?:\.\d+)?)h(\d+(?:\.\d+)?)\s*", name, re.I)
    if m:                                       # PostScript points (1/72 inch)
        return (float(m[1]) * 25.4 / 72, float(m[2]) * 25.4 / 72)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(mm|in|cm)?.*", name, re.I)
    if not m:
        return None
    a, b, unit = float(m[1]), float(m[2]), (m[3] or "").lower()
    if not unit:
        unit = "in" if max(a, b) <= 20 else "mm"   # "4x6" is inches, "62x100" is mm
    k = {"mm": 1, "cm": 10, "in": 25.4}[unit]
    return (a * k, b * k)


def label_pdf(img, label_mm=LABEL_MM, dpi=DPI):
    """A one-page PDF exactly the label's size (width, height in mm), with the label image
    centered on it."""
    w = round(label_mm[0] / 25.4 * dpi)
    h = round(label_mm[1] / 25.4 * dpi)
    page = Image.new("L", (w, h), 255)
    src = img.convert("L")
    if src.width > w or src.height > h:
        src.thumbnail((w, h))
    page.paste(src, ((w - src.width) // 2, (h - src.height) // 2))
    tmp = tempfile.NamedTemporaryFile(prefix="wnlp_label_", suffix=".pdf", delete=False)
    tmp.close()
    page.convert("1").save(tmp.name, "PDF", resolution=dpi)
    return Path(tmp.name)


def _cups_print(img, printer_name, job_name, options):
    size = labelsizes.get(options.get("label_size", labelsizes.DEFAULT_KEY))
    portrait = bool(options.get("portrait"))
    driver = driver_options(printer_name)
    paper = next((o["choices"] for o in driver if o["key"].lower() in ("pagesize", "media")), [])
    media = options.get("media") or labelsizes.driver_name_for(size, paper)
    extra = []
    if not media:
        # The driver doesn't list this size (e.g. 4" x 6" on a Brother): send it as a
        # custom size and let it fit.
        media = labelsizes.custom_media(size)
        extra = ["-o", "fit-to-page"]
    # Make the page the same shape as the driver's page for this size, and turn the label to
    # match. Some drivers (Brother's) won't turn a wide page to fit a tall label by
    # themselves; they just center it and cut off both ends.
    page = media_page_mm(media) or size.page_mm(portrait)
    turned = (img.width > img.height) != (page[0] > page[1]) and page[0] != page[1]
    if turned:
        img = img.rotate(90, expand=True)
    pdf = label_pdf(img, page)
    try:
        cmd = ["lp", "-d", printer_name, "-t", job_name, "-o", f"media={media}"] + extra
        known = {o["key"] for o in driver}
        for key, value in (options.get("driver_options") or {}).items():
            if key in known and key.lower() not in ("pagesize", "media"):
                cmd += ["-o", f"{key}={value}"]
        for extra in options.get("extra_options", []):
            cmd += ["-o", extra]
        cmd.append(str(pdf))
        r = _run(cmd)
        _log(f"page {page[0]:.1f}x{page[1]:.1f}mm, label image {img.width}x{img.height}"
             f"{' (turned 90°)' if turned else ''}; {' '.join(cmd)}  ->  exit {r.returncode}  "
             f"{r.stdout.strip()} {r.stderr.strip()}")
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"lp failed ({r.returncode})")
    finally:
        try:
            pdf.unlink()
        except OSError:
            pass

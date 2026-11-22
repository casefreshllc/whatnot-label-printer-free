"""Where the app keeps its files.

Installed version: everything the user might want to look at or edit
(settings, sales logs, saved label images) lives in
    Documents\\HammerSlip
because programs can't reliably write to their own install folder.

Running from source (python app.py): files stay next to the code, as before.
"""
import shutil
import sys
from pathlib import Path

APP_NAME = "HammerSlip"
VERSION = "1.9.0"

# Folder the program itself lives in (read-only files that ship with it).
CODE_DIR = Path(__file__).resolve().parent

# Nuitka marks compiled modules with __compiled__; PyInstaller sets sys.frozen.
IS_PACKAGED = "__compiled__" in globals() or getattr(sys, "frozen", False)


def _documents_folder():
    """The real Documents folder, even when Windows has moved it (e.g. into OneDrive)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            CSIDL_PERSONAL = 5  # "My Documents"
            if ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None, 0, buf) == 0:
                return Path(buf.value)
        except Exception:
            pass
    return Path.home() / "Documents"


DATA_DIR = (_documents_folder() / APP_NAME) if IS_PACKAGED else CODE_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = DATA_DIR / "config.json"
DEFAULT_CONFIG = CODE_DIR / "config.json"
SALES_LOG = DATA_DIR / "sales_log.csv"
OLD_LOGS_DIR = DATA_DIR / "Sales Logs"
LABELS_DIR = DATA_DIR / "printed_labels"


def ensure_config():
    """First run of the installed app: start from the default settings."""
    if not CONFIG_PATH.exists() and DEFAULT_CONFIG.exists() and DEFAULT_CONFIG != CONFIG_PATH:
        shutil.copyfile(DEFAULT_CONFIG, CONFIG_PATH)



def settings_folder():
    """Where the Whatnot token is kept: not in Documents (so it's never shared by accident in a
    diagnostics file or a copied folder)."""
    import os
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_NAME

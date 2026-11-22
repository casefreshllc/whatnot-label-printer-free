"""Checks for a newer version of HammerSlip and installs it.

Every release on this repository's Releases page (DOWNLOADS_REPO below) has a small file,
latest.json, next to the installers:

    {"version": "1.9.1",
     "notes_url": "https://github.com/.../releases/tag/v1.9.1",
     "windows": {"url": ".../HammerSlip-Setup-1.9.1.exe", "sha256": "…"},
     "mac":     {"url": ".../HammerSlip-1.9.1-mac.dmg",   "sha256": "…"}}

The app reads it, and if the version is newer, downloads the installer for this
computer, checks its SHA-256 fingerprint against the one in latest.json (so a damaged or
tampered download is never run), and installs it:

  Windows: runs the installer silently; it closes the app, installs over it (settings and
           sales logs are kept) and starts the new version.
  Mac:     a small helper waits for the app to quit, copies the new app from the .dmg over
           this one and opens it.
"""
import hashlib
import json
import os
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import paths

DOWNLOADS_REPO = "casefreshllc/whatnot-label-printer-free"
LATEST_URL = f"https://github.com/{DOWNLOADS_REPO}/releases/latest/download/latest.json"
USER_AGENT = f"HammerSlip/{paths.VERSION}"


class UpdateError(Exception):
    pass


def version_tuple(v):
    out = []
    for part in str(v).strip().lstrip("v").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def is_newer(latest, current=paths.VERSION):
    return version_tuple(latest) > version_tuple(current)


def _ssl_context():
    # The packaged app carries its own list of trusted certificates (certifi) when it has one.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


def check(url=LATEST_URL, timeout=10):
    """Return the latest release's info (dict from latest.json). Raises UpdateError if
    it can't be read."""
    try:
        with _open(url, timeout) as r:
            info = json.loads(r.read(200_000).decode("utf-8"))
    except Exception as e:  # no internet, not published yet, …
        raise UpdateError(f"Couldn't reach the update server ({e.__class__.__name__}).") from e
    if not isinstance(info, dict) or "version" not in info:
        raise UpdateError("The update information was unreadable.")
    return info


def platform_key():
    return "windows" if sys.platform.startswith("win") else "mac" if sys.platform == "darwin" else None


def download(asset, progress=None, timeout=30):
    """Download the installer described by `asset` ({"url", "sha256"}) to a temporary
    file, check its fingerprint, and return its path. progress(done_bytes, total_bytes)
    is called as it goes."""
    url, want = asset.get("url"), (asset.get("sha256") or "").lower()
    if not url or len(want) != 64:
        raise UpdateError("The update is missing its download details.")
    name = url.rsplit("/", 1)[-1] or "update"
    folder = Path(tempfile.mkdtemp(prefix="wnlp_update_"))
    dest = folder / name
    h = hashlib.sha256()
    try:
        with _open(url, timeout) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except Exception as e:
        raise UpdateError(f"The download failed ({e.__class__.__name__}).") from e
    if h.hexdigest() != want:
        try:
            dest.unlink()
        except OSError:
            pass
        raise UpdateError("The download didn't match its fingerprint, so it wasn't installed. "
                          "Please try again.")
    return dest


def current_mac_app():
    """The .app bundle this copy of the app is running from, or None."""
    p = Path(sys.executable).resolve()
    for parent in p.parents:
        if parent.suffix == ".app":
            return parent
    return None


MAC_SCRIPT = r"""#!/bin/bash
# Replaces the app with the new version once it has quit, then opens it.
PID="$1"; APP="$2"; DMG="$3"
for i in $(seq 1 120); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
MNT="$(mktemp -d /tmp/wnlp_mnt.XXXXXX)"
if ! hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "$DMG" >/dev/null; then
  open "$DMG"; exit 1
fi
NEW="$(ls -d "$MNT"/*.app 2>/dev/null | head -1)"
if [ -z "$NEW" ]; then hdiutil detach "$MNT" -quiet; open "$DMG"; exit 1; fi
# The new version is installed under its own name, next to where the old one was
# (so an app that has been renamed ends up with its new name).
DEST="$(dirname "$APP")/$(basename "$NEW")"
rm -rf "$APP.updating-old"
if mv "$APP" "$APP.updating-old" && rm -rf "$DEST" && ditto "$NEW" "$DEST"; then
  rm -rf "$APP.updating-old"
else
  rm -rf "$DEST"; mv "$APP.updating-old" "$APP" 2>/dev/null
  hdiutil detach "$MNT" -quiet; open "$DMG"; exit 1
fi
hdiutil detach "$MNT" -quiet
rm -f "$DMG"
open "$DEST"
"""


def install(installer):
    """Start installing the downloaded update. The caller must quit the app right after
    this returns (the installer / helper waits for it)."""
    installer = Path(installer)
    if sys.platform.startswith("win"):
        flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                          "/CLOSEAPPLICATIONS"], creationflags=flags, close_fds=True)
        return
    if sys.platform == "darwin":
        app = current_mac_app()
        if app is None or not os.access(app.parent, os.W_OK):
            # Can't replace it ourselves (e.g. running from the .dmg): open the new .dmg
            # so it can be dragged into Applications by hand.
            subprocess.Popen(["open", str(installer)])
            return
        script = installer.parent / "install_update.sh"
        script.write_text(MAC_SCRIPT, encoding="utf-8")
        subprocess.Popen(["/bin/bash", str(script), str(os.getpid()), str(app), str(installer)],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    raise UpdateError("Updating isn't supported on this computer.")

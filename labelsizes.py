"""The label sizes the app can lay out and print.

Sizes are the ones Brother's QL-800 series driver offers (it names them short side x long side
in mm, e.g. "29x62mm"), plus the standard 4" x 6" shipping label for printers like the Rollo.
They're shown to people in inches.
"""
import re
from dataclasses import dataclass

DPI = 300  # the label image is drawn at 300 dots per inch


@dataclass(frozen=True)
class LabelSize:
    key: str          # stored in settings, e.g. "29x62mm"
    short_mm: float
    long_mm: float
    brother: bool     # Brother die-cut label: the printer can't print right to the edges

    @property
    def short_in(self):
        return self.short_mm / 25.4

    @property
    def long_in(self):
        return self.long_mm / 25.4

    @property
    def name(self):
        """How it's shown: long side x short side in inches, to the nearest tenth, e.g. 2.4" × 1.1"."""
        if self.key in _SHOWN_AS:
            return _SHOWN_AS[self.key]
        return f'{_fmt(self.long_in)}" × {_fmt(self.short_in)}"'

    def pixels(self, portrait=False):
        """Size of the label image in pixels: (width, height).
        Landscape (the default) puts the long side across, so text runs along the long side."""
        if self.key in _BROTHER_PRINTABLE:
            # Brother's published printable area for this label, in dots (long, short).
            w, h = _BROTHER_PRINTABLE[self.key]
        else:
            long_px = self.long_mm / 25.4 * DPI
            short_px = self.short_mm / 25.4 * DPI
            if self.brother:
                # Brother printers can't print the last ~3 mm at each edge of a die-cut
                # label; keep 3 mm clear on every side to be safe.
                long_px -= 72
                short_px -= 72
            w, h = int(long_px + 0.5), int(short_px + 0.5)
        return (h, w) if portrait else (w, h)

    def page_mm(self, portrait=False):
        """The physical page (width, height) in mm, matching the image's orientation."""
        return (self.short_mm, self.long_mm) if portrait else (self.long_mm, self.short_mm)


def _fmt(x):
    """Inches to the nearest tenth (.05 and up rounds up), without a trailing .0: 2.44 -> 2.4,
    1.46 -> 1.5, 6 -> 6."""
    from decimal import Decimal, ROUND_HALF_UP
    tenth = Decimal(str(round(x, 6))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{tenth}".rstrip("0").rstrip(".")


_BROTHER = [(12, 12), (23, 23), (29, 52), (29, 62), (29, 90), (38, 90), (39, 48), (58, 58),
            (60, 86), (62, 100)]

# Names chosen by hand instead of the rounded measurements (display only; labels still print
# at their exact size).
_SHOWN_AS = {
    "23x23mm": '1" × 1"',
    "29x52mm": '2" × 1"',
    "29x90mm": '1.1" × 3.5"',
    "39x48mm": '2" × 1.5"',
    "58x58mm": '2.25" × 2"',
    "60x86mm": '3" × 2"',
    "62x100mm": '2.4" × 3.9"',
}

# Sizes no longer listed; settings saved with them use this size instead.
_REPLACED = {"24x24mm": "23x23mm"}

# Brother's published printable dots (long side, short side) for these die-cut labels.
_BROTHER_PRINTABLE = {
    "29x62mm": (696, 271),    # DK-1209, the app's original label
    "29x90mm": (991, 306),    # DK-1201
    "38x90mm": (991, 413),    # DK-1208
    "62x100mm": (1109, 696),  # DK-1202
    "17x54mm": (566, 165),    # DK-1204
    "17x87mm": (956, 165),    # DK-1203
}

SIZES = [LabelSize(f"{a}x{b}mm", a, b, True) for a, b in _BROTHER]
SIZES.append(LabelSize("4x6in", 101.6, 152.4, False))
# Listed smallest first, by the first number shown (then the second).
SIZES.sort(key=lambda s: tuple(float(n) for n in re.findall(r"\d+(?:\.\d+)?", s.name)))

DEFAULT_KEY = "29x62mm"   # 2.44" × 1.14" (Brother DK-1209), what the app has always printed
BY_KEY = {s.key: s for s in SIZES}


def get(key):
    key = _REPLACED.get(key, key)
    return BY_KEY.get(key) or BY_KEY[DEFAULT_KEY]


def driver_name_for(size, driver_sizes):
    """Find this label size in a Mac printer driver's list of paper sizes.
    Matches names written in mm ("29x62mm", "62x29"), inches ("4x6", "4.00x6.00in") or
    points ("w288h432"). Returns None if the driver doesn't list it."""
    want_sets = [
        {round(size.short_mm, 1), round(size.long_mm, 1)},           # millimetres
        {round(size.short_in, 2), round(size.long_in, 2)},           # inches
        {round(size.short_in * 72), round(size.long_in * 72)},       # points
    ]
    matches = []
    for name in driver_sizes:
        if name.lower().startswith("custom"):
            continue
        nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", name)]
        if len(nums) != 2:
            continue
        if any({round(n, 1) for n in nums} == ws or {round(n, 2) for n in nums} == ws
               or {round(n) for n in nums} == ws for ws in want_sets):
            matches.append(name)
    return sorted(matches, key=len)[0] if matches else None


def custom_media(size, portrait=False):
    """CUPS name for a size the driver doesn't list, e.g. "Custom.4x6in"."""
    w, h = (size.short_in, size.long_in)
    return f"Custom.{_fmt(w)}x{_fmt(h)}in"

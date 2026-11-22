"""Draws the label image: buyer username, item or giveaway title, and an optional footer line."""
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

# Fallback fonts so the app still works if Arial isn't where we expect. Arial ships with both
# Windows and macOS, so labels look the same on both.
_FALLBACKS_BOLD = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",   # macOS
    "/Library/Fonts/Arial Bold.ttf",                       # older macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_FALLBACKS_REGULAR = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",        # macOS
    "/Library/Fonts/Arial.ttf",                            # older macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(preferred, fallbacks, size):
    for path in [preferred, *fallbacks]:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _fit(draw, text, font_path, fallbacks, max_w, max_h, start=200, minimum=18, step=4):
    """Largest font size at which `text` fits inside max_w x max_h."""
    size = start
    while size > minimum:
        f = _font(font_path, fallbacks, size)
        l, t, r, b = draw.textbbox((0, 0), text, font=f)
        if r - l <= max_w and b - t <= max_h:
            return f
        size -= step
    return _font(font_path, fallbacks, minimum)


def _fit_multi(draw, text, font_path, max_w, max_h, start=200, minimum=18, step=4, spacing=14):
    size = start
    while size > minimum:
        f = _font(font_path, _FALLBACKS_BOLD, size)
        l, t, r, b = draw.multiline_textbbox((0, 0), text, font=f, align="center", spacing=spacing)
        if r - l <= max_w and b - t <= max_h:
            return f
        size -= step
    return _font(font_path, _FALLBACKS_BOLD, minimum)


def _fit_line(draw, text, font_path, fallbacks, max_w, max_h, start, minimum=18, step=4):
    """Fit one line of text in the box: shrink the font, then shorten with … if still too long."""
    f = _fit(draw, text, font_path, fallbacks, max_w, max_h, start=start, minimum=minimum,
             step=step)
    while len(text) > 1:
        l, t, r, b = draw.textbbox((0, 0), text, font=f)
        if r - l <= max_w:
            break
        text = text[:-2].rstrip() + "…"
    return text, f


def _draw_centered(draw, text, font, w, bottom):
    """Draw one line centered horizontally, with its bottom edge at `bottom`."""
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text(((w - (r - l)) // 2 - l, bottom - (b - t) - t), text, font=font, fill=0)
    return bottom - (b - t)


def render_label(username, cfg, item="", giveaway=False, footer=None, size=None):
    """Return a 1-bit PIL image of the label, `size` = (width, height) in pixels at 300 dpi
    (defaults to the 2.44" x 1.14" label, 696 x 271).

    The layout was designed on the 2.44" x 1.14" label; on other sizes every measurement is
    scaled by the label's short side, so it looks the same, just bigger or smaller.

    Line 1: the buyer's username (as big as fits).
    Line 2: the item name; for giveaways the giveaway's title, in bold.
    Line 3: optional text typed in the app (e.g. your channel name), smaller, at the bottom.
    """
    lc = cfg["label"]
    w, h = size or (lc["width_px"], lc["height_px"])
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)

    k = min(w, h) / 271          # 1.0 on the original 2.44" x 1.14" label

    def px(v):
        """A measurement from the original layout, scaled to this label."""
        return v if k == 1 else max(1, round(v * k))

    step, spacing = px(4), px(14)
    pad = px(16)
    inner_w = w - 2 * pad

    name = f"@{username}" if lc.get("show_at_sign", True) else username
    if footer is None:
        footer = lc.get("footer_text", "")
    footer = " ".join(str(footer or "").split())

    extra_parts = []
    if giveaway:
        # The giveaway's own title (e.g. "FREE XBOX"), or GIVEAWAY if it has none.
        g = (item or "").strip() or "GIVEAWAY"
        extra_parts.append(g if len(g) <= 40 else g[:39].rstrip() + "…")
    elif lc.get("second_line"):
        extra_parts.append(lc["second_line"].replace("{item}", item or ""))
    elif item:
        extra_parts.append(item if len(item) <= 40 else item[:39].rstrip() + "…")
    if lc.get("show_time"):
        extra_parts.append(datetime.now().strftime("%I:%M %p").lstrip("0"))
    extra = "  ·  ".join(p for p in extra_parts if p.strip())

    # Build the label from the bottom up; the name gets whatever height is left.
    bottom = h - pad
    middle = None
    if footer:
        text, ff = _fit_line(d, footer, lc.get("font_regular"), _FALLBACKS_REGULAR,
                             inner_w, px(32), start=px(30), minimum=px(20), step=step)
        top = _draw_centered(d, text, ff, w, bottom)
        bottom = top - px(11)
    if extra:
        font_path, fallbacks = ((lc.get("font_bold"), _FALLBACKS_BOLD) if giveaway
                                else (lc.get("font_regular"), _FALLBACKS_REGULAR))
        if footer:
            box_h, start = px(40), px(38)
        else:
            box_h, start = px(48), px(44)   # same as before when there's no footer
        text, ef = _fit_line(d, extra, font_path, fallbacks, inner_w, box_h, start=start,
                             minimum=px(18), step=step)
        if footer:
            # Reserve room for it now; it's drawn after the name, centered in the gap
            # between the name and the bottom line.
            el, et, er, eb = d.textbbox((0, 0), text, font=ef)
            middle = (text, ef, eb - et, et, bottom)
            bottom = bottom - (eb - et) - px(10)
        else:
            _draw_centered(d, text, ef, w, h - pad)
            bottom = h - pad - px(60)       # same spacing as before
    name_area_h = bottom - pad

    name_start = max(px(200), 200)   # bigger labels can use much bigger letters
    name_font = _fit(d, name, lc.get("font_bold"), _FALLBACKS_BOLD, inner_w, name_area_h,
                     start=round(name_start * max(1, max(w, h) / 696)), minimum=px(18), step=step)

    # Long names: if one line would be tiny, split into two bigger lines.
    if name_font.size < px(60) and len(name) > 12:
        mid = len(name) // 2
        cuts = [i for i, c in enumerate(name) if c in "_.-"] or [mid]
        cut = min(cuts, key=lambda i: abs(i - mid))
        cut = cut + 1 if name[cut] in "_.-" else cut
        two = name[:cut] + "\n" + name[cut:]
        f2 = _fit_multi(d, two, lc.get("font_bold"), inner_w, name_area_h,
                        start=round(name_start * max(1, max(w, h) / 696)), minimum=px(18),
                        step=step, spacing=spacing)
        if f2.size > name_font.size * 1.25:
            name, name_font = two, f2

    l, t, r, b = d.multiline_textbbox((0, 0), name, font=name_font, align="center",
                                      spacing=spacing)
    x = (w - (r - l)) // 2 - l
    y = pad + (name_area_h - (b - t)) // 2 - t
    d.multiline_text((x, y), name, font=name_font, fill=0, align="center", spacing=spacing)

    if footer and extra:
        # Put line 2 exactly halfway between the name and line 3, measured on the actual
        # printed pixels (font measurements include empty space above and below letters).
        text, ef, _ink_h, _off, footer_top = middle
        split = round((name_area_h + pad + footer_top) / 2)   # inside the reserved space
        inv = ImageOps.invert(img)
        name_bottom = inv.crop((0, 0, w, split)).getbbox()[3]
        foot_box = inv.crop((0, split, w, h)).getbbox()
        footer_ink_top = split + foot_box[1]
        layer = Image.new("L", (w, h), 255)
        ld = ImageDraw.Draw(layer)
        el, et, er, eb = ld.textbbox((0, 0), text, font=ef)
        x2 = (w - (er - el)) // 2 - el
        ld.text((x2, 0), text, font=ef, fill=0)
        ink = ImageOps.invert(layer).getbbox()          # where the ink lands when drawn at y=0
        ink_h = ink[3] - ink[1]
        target_top = name_bottom + (footer_ink_top - name_bottom - ink_h) / 2
        d.text((x2, round(target_top) - ink[1]), text, font=ef, fill=0)

    return img.point(lambda p: 0 if p < 128 else 255, mode="1")

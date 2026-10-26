"""
Solver for the PARAKH login captcha ("8 + 3" style arithmetic rendered as an image).

The image is split into glyphs by scanning for empty columns, each glyph is matched
against the bitmaps in captcha_glyphs.py, and the resulting expression is evaluated.
"""
import base64
import io
from typing import Optional, Tuple

from PIL import Image

from backend.hpc.captcha_glyphs import TEMPLATES


def _match_glyph(char_img: Image.Image) -> str:
    """Returns the label of the template that best matches this glyph."""
    cw, ch = char_img.width, char_img.height
    bits = [
        "".join("1" if char_img.getpixel((x, y)) < 128 else "0" for x in range(cw))
        for y in range(ch)
    ]

    best_label, best_sim = "?", -1.0
    for label, tbits, tw, th in TEMPLATES.values():
        if abs(cw - tw) > 3 or abs(ch - th) > 3:
            continue
        # Allow the glyph to be shifted by one pixel in any direction.
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                matches = total = 0
                for y in range(ch):
                    ty = y + dy
                    if not 0 <= ty < th:
                        continue
                    for x in range(cw):
                        tx = x + dx
                        if 0 <= tx < tw:
                            total += 1
                            matches += bits[y][x] == tbits[ty][tx]
                if total and matches / total > best_sim:
                    best_sim, best_label = matches / total, label
    return best_label


def _ink_bbox(img: Image.Image):
    return img.point(lambda p: 255 if p < 128 else 0).getbbox()


def solve_image(img: Image.Image) -> Tuple[Optional[int], str]:
    """Returns (answer, expression) for a grayscale captcha image; answer is None if unreadable."""
    w, h = img.size
    dark_per_column = [sum(1 for y in range(h) if img.getpixel((x, y)) < 128) for x in range(w)]

    segments, start = [], None
    for x, dark in enumerate(dark_per_column):
        if dark and start is None:
            start = x
        elif not dark and start is not None:
            segments.append((start, x))
            start = None
    if start is not None:
        segments.append((start, w))

    chars = []
    for x1, x2 in segments:
        sub = img.crop((x1, 0, x2, h))
        bbox = _ink_bbox(sub)
        if not bbox:
            continue
        glyph = sub.crop(bbox)
        # A minus sign touching a following "4" comes out as one wide glyph: split it.
        if glyph.width >= 22 and glyph.height >= 20:
            for part in (glyph.crop((0, 0, 9, glyph.height)), glyph.crop((9, 0, glyph.width, glyph.height))):
                pb = _ink_bbox(part)
                if pb:
                    chars.append(_match_glyph(part.crop(pb)))
        else:
            chars.append(_match_glyph(glyph))

    expr = "".join(chars)
    for op in ("+", "-"):
        left, sep, right = expr.partition(op)
        if sep and left.isdigit() and right.isdigit():
            return (int(left) + int(right) if op == "+" else int(left) - int(right)), expr
    return None, expr


def solve_base64(image_b64: str) -> Tuple[Optional[int], str]:
    """Decodes a base64 PNG (with or without a data: prefix) and solves it."""
    try:
        raw = base64.b64decode(image_b64.split(",")[-1])
        return solve_image(Image.open(io.BytesIO(raw)).convert("L"))
    except Exception as exc:
        return None, f"decode error: {exc}"

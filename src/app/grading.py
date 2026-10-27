"""Deterministic tap grading: geometry only, no model.

A hotspot entry comes from a scene meta.json ("masks" or "masks_simpler"):
either a SAM "mask_png" raster stretched over its "box", or a "hand-box"
rectangle. All coordinates below are media pixels in the displayed scene.

grade_tap(entry, x, y) -> (inside: bool, message: str)
"""

import struct
import zlib


def read_png_gray(path):
    """Read an 8-bit grayscale PNG. Returns (pixels, width, height)."""
    with open(path, "rb") as f:
        blob = f.read()
    assert blob[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, width, height, bitdepth, colortype, idat = 8, None, None, None, None, b""
    while pos < len(blob):
        (length,) = struct.unpack(">I", blob[pos:pos + 4])
        ctype = blob[pos + 4:pos + 8]
        data = blob[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height, bitdepth, colortype, _, _, _ = struct.unpack(
                ">IIBBBBB", data)
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
        pos += 12 + length
    assert bitdepth == 8 and colortype == 0, "need 8-bit grayscale PNG"
    raw = zlib.decompress(idat)
    pixels, p, stride = bytearray(width * height), 0, width + 1
    prev = bytearray(width)
    for y in range(height):
        filt, line = raw[p], bytearray(raw[p + 1:p + stride])
        p += stride
        if filt == 1:
            for i in range(1, width):
                line[i] = (line[i] + line[i - 1]) & 0xFF
        elif filt == 2:
            for i in range(width):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filt == 3:
            for i in range(width):
                a = line[i - 1] if i else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif filt == 4:
            for i in range(width):
                a = line[i - 1] if i else 0
                b, c = prev[i], prev[i - 1] if i else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        elif filt != 0:
            raise ValueError(f"unsupported PNG filter {filt}")
        pixels[y * width:(y + 1) * width] = line
        prev = line
    return bytes(pixels), width, height


def point_in_box(box, x, y):
    return box["left"] <= x < box["right"] and box["top"] <= y < box["bottom"]


def point_in_mask(entry, mask_pixels, mask_w, mask_h, x, y):
    """Map a scene point through the entry box into the raster."""
    box = entry["box"]
    if not point_in_box(box, x, y):
        return False
    raster = entry.get("raster")
    if raster is None:
        return True
    mh, mw = raster
    assert (mw, mh) == (mask_w, mask_h), "raster size mismatch"
    sx = (box["right"] - box["left"]) / mw
    sy = (box["bottom"] - box["top"]) / mh
    col = min(mw - 1, int((x - box["left"]) / sx))
    row = min(mh - 1, int((y - box["top"]) / sy))
    return mask_pixels[row * mw + col] > 0


def grade_tap(entry, target_noun, x, y, mask=None):
    """Grade one tap. mask = (pixels, w, h) when entry has a mask_png."""
    if entry.get("mask_png") and mask is not None:
        pixels, mw, mh = mask
        inside = point_in_mask(entry, pixels, mw, mh, x, y)
    else:
        inside = point_in_box(entry["box"], x, y)
    if inside:
        return True, f"Yes! That's the {target_noun}."
    return False, (f"Not quite - that's not the {target_noun}. "
                   f"Look for the big {target_noun} and try again.")

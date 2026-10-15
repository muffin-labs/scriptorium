#!/usr/bin/env python3
"""
web_images.py — the served copy of an image, and carry-sized batches of them.

WHY THIS EXISTS

  A piece's masters are generated PNGs at ~2.5 MB each. Every browser outlet takes them
  as a `data:` URI carried into the page through `window.name`, and base64 adds a third:
  a 20-figure piece (the-top-step, 2026-10-15) is ~65 MB of payload. The carrier is
  measured good to ~4 MB in one hop, so the converters' one-file-per-figure PNG payloads
  meant twenty carries for LinkedIn, and the Substack converter inlined every PNG into a
  single snippet nothing could carry at all. Both were finished that day by hand-built
  JPEG batches. This is that, made the path.

  The recipe is img_deck's (longest edge 1600 px, JPEG q82): what the talk deck already
  serves, and what both platforms re-encode to anyway. The masters stay in assets/.

  web_copy(path)            -> (mime, bytes)   resized JPEG; the original if PIL is absent
  data_uri(path)            -> 'data:image/jpeg;base64,…'
  batches(items, limit)     -> [[item, …], …]  grouped so each batch's JSON stays under limit
"""
import base64
import io
import json
import mimetypes
import os

try:
    from PIL import Image
except ImportError:                                  # pragma: no cover - CI installs it
    Image = None

WIDTH = 1600
QUALITY = 82
# One carry. window.name has been measured carrying 2.5–3.9 MB into LinkedIn and Substack
# (2026-09-14, 2026-10-15); stay under the larger of those.
CARRY_LIMIT = 3_500_000


def web_copy(path, width=WIDTH, quality=QUALITY):
    """The served copy of one master -> (mime, bytes). Resized, never cropped."""
    if Image is None or not width:
        return (mimetypes.guess_type(path)[0] or 'image/png'), open(path, 'rb').read()
    im = Image.open(path).convert('RGB')
    if max(im.size) > width:
        s = width / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=quality, optimize=True, progressive=True)
    return 'image/jpeg', buf.getvalue()


def data_uri(path, width=WIDTH, quality=QUALITY):
    mime, data = web_copy(path, width, quality)
    return f'data:{mime};base64,{base64.b64encode(data).decode()}'


def batches(items, limit=CARRY_LIMIT):
    """Group dicts so each group's JSON stays under `limit`. An item larger than the limit
    goes alone rather than being dropped: an oversized carry fails loudly, a dropped image
    does not."""
    out, cur, size = [], [], 0
    for it in items:
        n = len(json.dumps(it))
        if cur and size + n > limit:
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        out.append(cur)
    return out

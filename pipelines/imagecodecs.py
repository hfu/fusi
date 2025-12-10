"""Minimal shim for imagecodecs.webp_decode used by local tools.
This shim uses Pillow to decode WebP into a numpy array.
"""
from io import BytesIO

from PIL import Image
import os
import numpy as np


def webp_decode(blob: bytes):
    img = Image.open(BytesIO(blob)).convert("RGBA")
    arr = np.array(img)
    return arr


def webp_encode(arr, lossless=True, method=None):
    # Wrapper for WebP encoding using Pillow.
    # The encoding effort (`method`) can be set via env `FUSI_WEBP_METHOD`.
    # Default behavior: use the strongest effort (6) unless overridden.
    from PIL import Image
    img = Image.fromarray(arr.astype('uint8'))
    buf = BytesIO()

    if method is None:
        try:
            method = int(os.environ.get('FUSI_WEBP_METHOD', '6'))
        except (TypeError, ValueError):
            method = 6

    # Pillow accepts `method` for WebP to trade CPU for compression.
    img.save(buf, format='WEBP', lossless=lossless, method=method)
    return buf.getvalue()

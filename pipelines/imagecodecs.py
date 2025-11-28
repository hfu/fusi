"""Minimal shim for imagecodecs.webp_decode used by local tools.
This shim uses Pillow to decode WebP into a numpy array.
"""
from io import BytesIO

from PIL import Image
import numpy as np


def webp_decode(blob: bytes):
    img = Image.open(BytesIO(blob)).convert("RGBA")
    arr = np.array(img)
    return arr


def webp_encode(arr, lossless=True):
    # Not needed for this shim in inspection, but provide a wrapper if used.
    from PIL import Image
    img = Image.fromarray(arr.astype('uint8'))
    buf = BytesIO()
    img.save(buf, format='WEBP', lossless=lossless)
    return buf.getvalue()

import os
import concurrent.futures

import numpy as np
import pytest

from pipelines import imagecodecs


def make_test_image():
    # Small RGBA test image with deterministic content
    arr = np.zeros((64, 64, 4), dtype='uint8')
    arr[..., 0] = 100
    arr[..., 1] = 150
    arr[..., 2] = 200
    arr[..., 3] = 255
    return arr


def test_webp_encode_decode_single():
    arr = make_test_image()
    b = imagecodecs.webp_encode(arr, lossless=True)
    assert isinstance(b, (bytes, bytearray))
    dec = imagecodecs.webp_decode(b)
    assert dec.shape == arr.shape


def _encode_task(arr, method=None):
    return imagecodecs.webp_encode(arr, lossless=True, method=method)


def test_webp_encode_concurrent_threads():
    arr = make_test_image()
    # Run multiple concurrent encodes to surface any thread-safety / IO issues.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_encode_task, arr) for _ in range(16)]
        results = [f.result(timeout=10) for f in futures]

    # Ensure each result decodes correctly and has expected shape
    for b in results:
        dec = imagecodecs.webp_decode(b)
        assert dec.shape == arr.shape


def test_webp_method_env_override(monkeypatch):
    arr = make_test_image()
    # set a low-effort method and ensure encoding still works
    monkeypatch.setenv('FUSI_WEBP_METHOD', '0')
    b = imagecodecs.webp_encode(arr, lossless=True)
    dec = imagecodecs.webp_decode(b)
    assert dec.shape == arr.shape

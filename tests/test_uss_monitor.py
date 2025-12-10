import time

from pipelines.uss_monitor import USSMonitor


def test_uss_monitor_reports_peak():
    monitor = USSMonitor(interval=0.05)
    monitor.start()
    # allocate some memory to raise RSS/USS
    data = bytearray(1024 * 1024 * 8)  # ~8 MiB
    # give sampler a moment to see the allocation
    time.sleep(0.2)
    monitor.stop()
    peak = monitor.peak_bytes
    assert isinstance(peak, int)
    # Expect at least 1 MiB observed as a conservative check
    assert peak >= 1024 * 1024
    # release the memory
    del data

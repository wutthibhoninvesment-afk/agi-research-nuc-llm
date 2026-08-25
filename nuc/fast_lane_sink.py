#!/usr/bin/env python3
"""fast_lane_sink.py — receive a byte stream on stdin and write it to disk
WITHOUT growing the page cache.

Why: the production engine on the box sits at its cgroup ceiling (MemoryMax)
with MemAvailable < 1 GB; a plain `scp` of a 7 GB container would push 7 GB of
dirty/cached pages through global reclaim and could swap the engine or invite
the OOM killer. This sink fdatasyncs every `--sync-every-mb` and then tells the
kernel to drop those pages (posix_fadvise DONTNEED; F_NOCACHE on macOS), so
the resident set of the copy stays at one chunk.

Writes to `<out>.part`, renames on success, prints a JSON line with byte count
and md5 so the sender can verify integrity. Stdlib only (Python 3.8+).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time


def open_nocache(path: str) -> int:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    if not hasattr(os, "posix_fadvise") and sys.platform == "darwin":
        import fcntl  # noqa: WPS433 — macOS only
        fcntl.fcntl(fd, fcntl.F_NOCACHE, 1)
    return fd


def drop_range(fd: int, offset: int, length: int) -> None:
    """fdatasync the range then advise the kernel it will not be needed."""
    if hasattr(os, "fdatasync"):
        os.fdatasync(fd)
    else:
        os.fsync(fd)
    fadvise = getattr(os, "posix_fadvise", None)
    if fadvise is not None:
        fadvise(fd, offset, length, os.POSIX_FADV_DONTNEED)


def sink(stream, out_path: str, chunk_bytes: int, sync_every: int,
         log=lambda s: None) -> dict:
    part = out_path + ".part"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    fd = open_nocache(part)
    md5 = hashlib.md5()
    total = 0
    since_sync_start = 0
    t0 = time.monotonic()
    try:
        while True:
            buf = stream.read(chunk_bytes)
            if not buf:
                break
            view = memoryview(buf)
            while view:
                n = os.write(fd, view)
                view = view[n:]
            md5.update(buf)
            total += len(buf)
            if total - since_sync_start >= sync_every:
                drop_range(fd, since_sync_start, total - since_sync_start)
                since_sync_start = total
                log(f"  {total / 1e9:.2f} GB  {total / 1e6 / (time.monotonic() - t0):.1f} MB/s")
        drop_range(fd, since_sync_start, total - since_sync_start)
    finally:
        os.close(fd)
    os.replace(part, out_path)
    elapsed = time.monotonic() - t0
    return {"out": out_path, "bytes": total, "md5": md5.hexdigest(),
            "seconds": round(elapsed, 3),
            "mb_s": round(total / 1e6 / elapsed, 2) if elapsed > 0 else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk-mb", type=int, default=8)
    ap.add_argument("--sync-every-mb", type=int, default=256)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    log = (lambda s: None) if a.quiet else (lambda s: print(s, file=sys.stderr, flush=True))
    result = sink(sys.stdin.buffer, a.out, a.chunk_mb * 1_000_000, a.sync_every_mb * 1_000_000, log)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

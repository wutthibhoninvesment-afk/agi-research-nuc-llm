#!/usr/bin/env python3
"""The same seed twice, disagreeing in SHAPE.

The number of lines comes from a counter that every run increments, so two
runs NEVER agree and no mask over key paths or line indices can localise the
noise. The honest verdict is that this subject supports NO statement about
hash order -- not `stable`, and not a finding.

A clock-modulo version of this file was written first and rejected: `3 +
time_ns() % 3` gives two control runs a 1-in-3 chance of agreeing, which
makes the control for `unscrubbable` itself flaky. A control that is
sometimes right is not a control.

argv[1], if given, is the counter file; the default lives in the system
temp dir so the repo stays clean.
"""
import os
import sys
import tempfile

path = (sys.argv[1] if len(sys.argv) > 1
        else os.path.join(tempfile.gettempdir(), "seedsweep-unscrubbable.ctr"))
try:
    n = int(open(path).read().strip())
except (OSError, ValueError):
    n = 0
n += 1
with open(path, "w") as fh:
    fh.write(str(n))
for i in range(3 + (n % 4)):
    print("row %d" % i)

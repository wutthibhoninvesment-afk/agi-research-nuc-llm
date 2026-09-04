#!/usr/bin/env python3
"""Deterministic: the same set of strings, but ORDERED before printing.

The positive shape. If this subject is ever anything but `stable` the
instrument is reporting noise from the runner itself and every other row is
uninterpretable.
"""
import json
WORDS = {"alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
         "golf", "hotel", "india", "juliett", "kilo", "lima"}
print(json.dumps({"words": sorted(WORDS), "n": len(WORDS)}))

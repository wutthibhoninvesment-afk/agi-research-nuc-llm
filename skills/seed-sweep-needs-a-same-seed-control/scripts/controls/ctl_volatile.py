"""Differs run to run for a reason that is NOT the seed.

The body is fully ordered; one field carries a monotone clock. A cross-seed
sweep with no control sees three different outputs and reports a hash-order
bug. The control sees the same at one seed and localises the field.
"""
import json, time
WORDS = {"alpha", "bravo", "charlie", "delta"}
print(json.dumps({"words": sorted(WORDS), "generated_at_ns": time.time_ns()}))

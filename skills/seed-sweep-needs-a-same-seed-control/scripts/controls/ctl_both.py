"""Volatile AND seed-dependent at once.

The clock field moves under a fixed seed; the `order` field moves only with
the seed. Masking the first must not mask the second -- if it does, the
derived scrub set is too wide and the instrument has bought its own green.
"""
import json, time
WORDS = {"alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
         "golf", "hotel", "india", "juliett", "kilo", "lima"}
print(json.dumps({"order": list(WORDS), "generated_at_ns": time.time_ns()}))

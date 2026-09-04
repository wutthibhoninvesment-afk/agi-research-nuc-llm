"""Nondeterministic across processes: a set of STRINGS, iterated.

This is round 481's `best_incoming` bug in nine lines. Nothing here reads a
clock or the environment, so a difference between two runs at different
seeds has exactly one cause.
"""
import json
WORDS = {"alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
         "golf", "hotel", "india", "juliett", "kilo", "lima"}
print(json.dumps({"first": next(iter(WORDS)), "order": list(WORDS)}))

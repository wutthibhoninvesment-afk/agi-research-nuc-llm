"""THE BLIND SPOT, kept live rather than written down.

`hash(n) == n` for a small non-negative int in CPython, and PYTHONHASHSEED
does not perturb it. So this program is genuinely order-dependent -- it
prints whatever the set happens to yield first -- and every hash-seed sweep
ever written, including this one, reports it `stable`.

A subject registered with `expect: stable` and a `why` that says WHY is the
difference between a documented limitation and an undiscovered one.
"""
import json
NUMS = {17, 4, 256, 33, 8, 129, 640, 71, 2, 1024}
print(json.dumps({"first": next(iter(NUMS)), "order": list(NUMS)}))

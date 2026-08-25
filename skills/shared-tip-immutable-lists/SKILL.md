---
name: shared-tip-immutable-lists
description: Makes immutable list values in an interpreter or persistent data layer share storage, so growing a list step by step (push/append/concat in a loop or fold) costs O(1) amortised per step and O(n) total memory even when every intermediate version stays reachable (history, undo, provenance, time travel). Use when retained versions of a growing list blow up memory quadratically, when memory grows every iteration of a loop that appends to an immutable list or keeps undo/history versions, when a "persistent list" is needed in stdlib Python without a full HAMT/RRB vector, or when profiling an interpreter shows most time spent building display/show/repr strings, snapshots, or renderings of values that are never printed (the fix there is lazy, on-demand rendering).
---

# Shared-tip immutable lists (persistent append in ~40 lines)

## Trigger conditions
- Values are immutable but every version is retained (provenance DAGs, undo
  stacks, time-travel debuggers, event-sourced state) and profiling shows
  O(n²) memory or time for "append in a loop" (Whence v0.2: 20k pushes in a
  fold = 568MB / 6s).
- A persistent vector library is overkill or unavailable (stdlib only).
- Eager per-value snapshot/preview strings show up at the top of a profile.
- Proven on: Whence v0.3 (`languages/whence/whence/values.py`, `WList`):
  20k pushes 568MB/6.1s → 30MB/0.26s with *every* intermediate list still
  reachable; 200k pushes scale linearly (271MB).

## Steps
1. **Represent a list as a view `(buf, n)` over a shared Python list.** The
   view's length is `n`; it only ever reads `buf[:n]`. Give it `__len__`,
   `__iter__` (bounded by `n`, not by `len(buf)`), `__getitem__` that raises
   `IndexError` for `i >= n`, `to_list()`, and `__eq__` against Python lists
   so existing tests keep working.
2. **Append shares when the view is the buffer's tip.** `push(x)`: if
   `len(buf) == n` nobody has grown past this view — `buf.append(x)` and
   return `View(buf, n + 1)`. Otherwise copy: `View(buf[:n] + [x])`. Same
   for `concat(items)` with `extend`. The old view is untouched because it
   never reads past its own `n`.
3. **Replace every `isinstance(p, list)` in the evaluator** with the view
   class, and every `list` payload constructor with `wlist(items)`. Grep for
   `list)` and `[` literals in builtins (`range`, `map`, `filter`, `keys`,
   `reasons`, …) — missing one gives a `<?>`-style rendering or a type miss
   in a builtin, both easy to catch with the suite.
4. **Make previews lazy.** If each node stores a short snapshot string of its
   value "so rendering never needs the value", and the value is retained
   anyway, compute the string on first access (`@property` over a `_show`
   slot with a sentinel). Whence: 67% of evaluation time was eager
   `show_payload`; lazy snapshots cut the guest-loop benchmark 2.4×.
5. **Benchmark before and after with the same script**: time + `ru_maxrss`
   for push-in-fold, concat-in-fold and a plain tail loop at 20k and 200k;
   confirm the second is ~10× the first (linear), not ~100×.

## Exact commands
```bash
python3 bench/retention.py 20000 push-in-fold   # time, peak RSS, result preview
python3 bench/retention.py 200000 push-in-fold  # must be ~10x, not ~100x
python3 - <<'PY'
from whence.values import wlist, leaf
a = wlist([leaf("literal", "", 1, 1)]); b = a.push(leaf("literal", "", 1, 2))
c = a.push(leaf("literal", "", 1, 3))       # second push on `a` must copy
assert b.shares_buffer_with(a) and not c.shares_buffer_with(a)
assert [e.payload for e in a] == [1] and [e.payload for e in c] == [1, 3]
PY
```

## Pitfalls
- **Prepend and insert do not share** (`[x] + rest` in a right-recursive
  builder still copies). Document it; only tip-append/extend is O(1).
- **Slicing must bound by `n`**: a `buf[:6]` preview helper that ignores `n`
  leaks elements appended by a *later* version into an older value's
  rendering. Route every read through the view.
- **Equality between views must compare contents, not buffers**: two views
  over different buffers with equal prefixes are equal; two views over the
  same buffer with different `n` are not.
- **Tests that build payloads as raw Python lists** (`leaf("list", "", 1,
  [v])`) silently render as `<?>`; convert them to `wlist(...)`.
- **Thread safety is not addressed** — a single-threaded evaluator is the
  assumption; two threads appending to the same tip would race.
- A lazy preview is computed from the *retained* value; if a node type does
  not retain its value (e.g. a placeholder completed later), set its value
  before anything can render it, or set `show` explicitly.

## Verification
- Pushing onto a view twice yields two independent lists and leaves the
  original unchanged (the test above).
- A fold that pushes n elements leaves n `push` nodes in the history, all
  reporting the same `id(buf)`, and the final list has n elements.
- Memory for 10× the elements is ~10× (measure, do not assume).
- The evaluator's full suite passes after the `isinstance` sweep, and
  rendering never shows the fallback (`<?>`) for a list value.

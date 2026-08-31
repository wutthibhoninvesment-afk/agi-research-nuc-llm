"""Instrument digests for every long-running sweep in `harness/swe/`
(round 401, SWE-loop D — round 389's next-step item 4, the remainder).

WHY THIS EXISTS
---------------
Round 389 edited `oracles.py` while a sweep arm was running. The arm's own
self-verifying registry killed it mid-flight, which is the loud failure; the
quiet one is a sweep that survives the edit and appends rows measured by two
different instruments into one file. Round 389 built the guard for exactly one
consumer — `exemptmap.sweep_record` stamps `oracles_sha` on every row and
`exemptmap.ab()` reports `mixed_instrument` — and left `exemptaudit.py`,
`fuzz.py` and `guest.py` unguarded. This module is that guard, generalised.

TWO THINGS ROUND 389'S VERSION DID NOT DO, both found by round 401:

1.  **An instrument has PARTS, and one hash cannot name which moved.**
    `oracles_sha` answers "did the instrument change" with a bit. What a
    reader needs is "the GENERATOR changed and the oracle did not", which is
    a different remedy (re-derive the seed set) from "the oracle changed"
    (re-run the arm). So `stamp()` returns a dict, one digest per part, and
    `mixed_parts()` names the parts that moved rather than raising one flag.

2.  **The generator is part of the instrument.** Every sweep in this package
    is keyed by SEED, and a seed only denotes a program relative to a fixed
    `ProgramGen`. An edit to `harness/swe/fuzz.py` silently changes WHICH
    program `seed 140` is. A seed-paired A/B across such an edit compares two
    different programs while reporting an unchanged `oracles_sha` — the guard
    is looking at the wrong file. Round 389's own control run ("arm A vs
    round 383's rows on 300 shared seeds, every site's fire SET identical")
    was safe only because `fuzz.py` happened not to have been touched between
    the two sweeps; nothing checked that, and round 401 had to go to `git log`
    to find out. `PARTS["gen"]` is that check.

    The same argument extends to the SUBJECT: a differential run across an
    edit to `languages/whence/whence/` is not one population either, so the
    whence tree is a part (`PARTS["whence"]`, a digest over the sorted
    `*.py` contents, not over mtimes).

NON-GOALS
---------
This module never blocks, retries or "fixes" anything. A mixed file is a fact
about a measurement that already happened; the only honest action is to report
it next to the number so a reader can discount it. `exemptmap.ab()` set that
precedent and this keeps it.

usage:
  python3 -m harness.swe.instrument stamp
  python3 -m harness.swe.instrument audit <sweep.jsonl> [...]
"""

import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
WHENCE_PKG = os.path.join(REPO_ROOT, "languages", "whence", "whence")

# The key every stamped row carries. One key, so a reader that finds it can
# always ask the same question of any sweep file in this package.
STAMP_KEY = "instrument"

# Rows written before their module was stamped carry no key at all. They are
# a real population — just an unnamed one — so they get a legible placeholder
# rather than being dropped or silently merged with a live digest.
UNSTAMPED = "unstamped"


def file_sha(path, n=12):
    """First `n` hex of a file's sha256, recomputed on EVERY call.

    Round 389 first cached this per `(path, st_mtime_ns, st_size)` and the
    cache was the bug: an edit that preserves both — a same-length constant
    change, a `touch` back, a `git checkout` — reads as unchanged, and the
    row then carries a digest naming an instrument that is not the one that
    measured it. The whole job of this function is to notice exactly that
    edit, so there is nothing left to cache. Measured cost is in
    `stamp_cost()`; it is ~4 orders of magnitude under a sweep row.
    """
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:n]
    except OSError:
        return ""


def tree_sha(dirpath, suffix=".py", n=12):
    """Digest of a directory's `*.py` contents, order-independent of the
    filesystem: names are sorted and each file's RELATIVE PATH is hashed in
    alongside its bytes, so a rename is a change (it is one) and a directory
    listing order is not."""
    h = hashlib.sha256()
    try:
        names = sorted(x for x in os.listdir(dirpath) if x.endswith(suffix))
    except OSError:
        return ""
    for name in names:
        p = os.path.join(dirpath, name)
        try:
            with open(p, "rb") as f:
                data = f.read()
        except OSError:
            continue
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(data)
        h.update(b"\0")
    return h.hexdigest()[:n]


def _swe(name):
    return os.path.join(_HERE, name)


# Every part any sweep in this package can depend on. A part is a callable so
# the digest is never computed for a lane that does not name it.
PARTS = {
    # the oracle suite: what verdict a program gets
    "oracles": lambda: file_sha(_swe("oracles.py")),
    # the generator: WHICH program a seed denotes (round 401's addition)
    "gen": lambda: file_sha(_swe("fuzz.py")),
    # the guest-differential generator and comparator
    "guest": lambda: file_sha(_swe("guest.py")),
    # the site registry and its `measure` (exemptmap's own site flags)
    "exemptmap": lambda: file_sha(_swe("exemptmap.py")),
    # the ladder / source-patching audit
    "exemptaudit": lambda: file_sha(_swe("exemptaudit.py")),
    # the SUBJECT under test
    "whence": lambda: tree_sha(WHENCE_PKG),
}

# Which parts constitute each sweep's instrument. Deliberately explicit and
# deliberately NOT "everything": a lane that hashes a file it does not depend
# on reports drift that changes none of its numbers, and a guard that cries
# wolf is turned off by the next round that trips it.
LANES = {
    "exemptmap.sweep": ("oracles", "gen", "exemptmap", "whence"),
    "exemptaudit.sweep": ("exemptaudit", "guest", "gen", "whence"),
    "exemptaudit.ladder": ("exemptaudit", "guest", "gen", "whence"),
    "guest.fuzz_guest": ("guest", "gen", "whence"),
    "fuzz.fuzz": ("gen", "whence"),
    "spacewitness.scan": ("oracles", "gen", "whence"),
}


def stamp(lane):
    """`{part: digest}` for one lane, plus `lane` itself so a row is
    self-describing when it is read back years later out of context."""
    if lane not in LANES:
        raise KeyError("unknown lane %r (known: %s)"
                       % (lane, ", ".join(sorted(LANES))))
    out = {"lane": lane}
    for part in LANES[lane]:
        out[part] = PARTS[part]()
    return out


def stamp_cost(lane="exemptmap.sweep", reps=20):
    """Measured seconds per `stamp()` — the number that decides whether
    stamping every row is affordable. Round 389 argued this rather than
    measuring it; the argument was right, and it is cheaper to check than to
    re-derive."""
    import time
    t0 = time.time()
    for _ in range(reps):
        stamp(lane)
    return (time.time() - t0) / reps


def row_stamp(row, lane):
    """Attach a stamp to a sweep row in place and return it."""
    row[STAMP_KEY] = stamp(lane)
    return row


def digests(rows, part=None):
    """`{part: {digest: n_rows}}` over stamped rows (or `{digest: n_rows}`
    for a single `part`). Rows with no stamp count under `UNSTAMPED`, which
    is a population, not an error."""
    per = {}
    for r in rows:
        st = r.get(STAMP_KEY)
        if not isinstance(st, dict):
            per.setdefault(UNSTAMPED, {})
            per[UNSTAMPED][UNSTAMPED] = per[UNSTAMPED].get(UNSTAMPED, 0) + 1
            continue
        for k, v in st.items():
            if k == "lane":
                continue
            per.setdefault(k, {})
            per[k][v] = per[k].get(v, 0) + 1
    if part is not None:
        return per.get(part, {})
    return per


def mixed_parts(rows):
    """The parts that took more than one value across `rows` — i.e. the
    instrument components that changed mid-sweep. Empty list means the file
    is one population (or is entirely unstamped, which `digests` shows)."""
    return sorted(k for k, v in digests(rows).items()
                  if k != UNSTAMPED and len(v) > 1)


def audit(rows, lane=None):
    """The report a consumer prints next to its numbers."""
    per = digests(rows)
    mixed = mixed_parts(rows)
    live = stamp(lane) if lane else None
    stale = []
    if live:
        for part, counts in per.items():
            if part == UNSTAMPED:
                continue
            if live.get(part) and live[part] not in counts:
                stale.append(part)
    return {
        "n_rows": len(rows),
        "digests": per,
        "mixed_instrument": bool(mixed),
        "mixed_parts": mixed,
        "unstamped_rows": per.get(UNSTAMPED, {}).get(UNSTAMPED, 0),
        # a part whose live digest appears in NO row: the tree moved after
        # the sweep. Not an error — it is why re-running gives other numbers.
        "moved_since_parts": sorted(stale),
        "lane": lane,
    }


def read_rows(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def main(argv):
    cmd = argv[0] if argv else "stamp"
    if cmd == "stamp":
        out = dict((lane, stamp(lane)) for lane in sorted(LANES))
        out["_seconds_per_stamp"] = round(stamp_cost(), 6)
        print(json.dumps(out, indent=1, sort_keys=True))
    elif cmd == "audit":
        lane, args = None, list(argv[1:])
        if "--lane" in args:
            i = args.index("--lane")
            lane = args[i + 1]
            del args[i:i + 2]
        for p in args:
            print(json.dumps(dict(path=p, **audit(read_rows(p), lane)),
                             indent=1, sort_keys=True))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

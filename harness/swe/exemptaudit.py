"""Exemption audit for the guest differential (round 377, SWE-loop D).

`guest.agree()` exempts any compared field where either side scrubbed to
`&DEPTHMISS&`. Round 371 measured that this one exemption covers TWO
situations — `both_missed` (both evaluators refused, on budgets of the same
kind at different sizes: the asymmetry it was written for) and `host_valued`
(the host produced a real value and only the guest refused: a difference of
KIND, because the host spends no depth on a tail call and the guest charges
one guest frame per bounce). It left the verdict alone and made the
exemption report which class it fired on, then owed one number and did not
deliver it: *how often does each class fire across the fuzz corpus?*

Round 371's sweep was a throwaway in `state/swe/round-371/`. It ran ~12 min
on 200 seeds, was killed, and wrote its JSON **only at the end**, so it left
nothing at all. This module is the durable replacement and fixes exactly
that: one JSONL line per seed, flushed as it goes, resumable, and bounded by
a wall-clock budget it reports against rather than a seed count guessed from
nothing.

It also answers the question a zero rate cannot answer on its own. If the
blind-spot class never fires, that is either "the bug does not happen" or
"this corpus cannot reach it" — indistinguishable from the rate alone. So
`ladder` measures each seed's real GUEST-DEPTH DEMAND by rebuilding the
guest harness with `GUEST_MAX_DEPTH` rewritten (`GuestHarness(lib_source=)`
makes this a per-harness change, no edit on disk) and bisecting on a ladder
of ceilings. Demand vs the ceiling is the DISTANCE, and a distance is what
turns a zero into a measurement.

usage:
  python3 -m harness.swe.exemptaudit sweep   [N] [--out P] [--budget-s S]
                                             [--timeout-s S] [--start K]
  python3 -m harness.swe.exemptaudit summary [--out P]
  python3 -m harness.swe.exemptaudit ladder  [N] [--out P] [--budget-s S]
  python3 -m harness.swe.exemptaudit corpusnums [N]
  python3 -m harness.swe.exemptaudit band
"""

import json
import os
import re
import signal
import sys
import time

from . import guest as G
from . import oracles as O
from .fuzz import WHENCE_ROOT
from .killers import load_whence

#: descending ceilings for `ladder`. 400 is the real `GUEST_MAX_DEPTH`, so
#: the top rung reproduces production behaviour exactly and every lower rung
#: asks "would this seed still have been fine with less?".
LADDER = (400, 200, 100, 50, 25, 12, 6, 3)

#: the line `patch_lib_source` rewrites. Kept as a literal (not a regex over
#: `GUEST_MAX_DEPTH\s*=`) so a rename in `self_eval.lang` fails LOUDLY here
#: instead of silently patching nothing and reporting production numbers as
#: if they were ladder numbers.
_CEILING_LINE = "let GUEST_MAX_DEPTH = "


class Timeout(Exception):
    pass


def _alarm(_sig, _frm):
    raise Timeout()


def _guarded(fn, timeout_s):
    """Run `fn()` under a wall-clock budget. Returns (value, error_str,
    seconds); `error_str` is "" on success, "timeout" on the budget, else
    the exception type name."""
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    t0 = time.time()
    try:
        return fn(), "", time.time() - t0
    except Timeout:
        return None, "timeout", time.time() - t0
    except BaseException as e:      # noqa: BLE001 — the audit records, never raises
        return None, type(e).__name__, time.time() - t0
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


# ------------------------------------------------------------------ sweep --

def sweep_record(pkg, seed, timeout_s=30.0, max_depth=2000, harness=None):
    """One seed's row: the oracle's verdict plus the exemption breakdown."""
    src = G.generate_guest_program(seed)
    kw = {"timeout_s": timeout_s, "max_depth": max_depth}
    if harness is not None:
        kw["harness"] = harness
    o = O.run_oracle(G.GUEST_ORACLE, pkg, src, **kw)
    ex = G.parse_exempt(o.detail)
    return {
        "seed": seed,
        "kind": o.kind,
        "s": round(o.seconds, 3),
        "exempt": ex,
        "exempt_fields": sum(ex.values()),
        "host_valued": ex.get("host_valued", 0),
        "guest_valued": ex.get("guest_valued", 0),
        "both_missed": ex.get("both_missed", 0),
        "src_lines": src.count("\n"),
        "detail": o.detail[:200],
    }


def done_seeds(path):
    """Seeds already recorded in `path` (so a killed sweep resumes)."""
    if not os.path.exists(path):
        return set()
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                seen.add(json.loads(line)["seed"])
            except (ValueError, KeyError):
                # A row truncated by a kill mid-write: the seed is simply
                # not done. Dropping it is right — `sweep` appends, and the
                # next full row for that seed lands after it.
                continue
    return seen


def sweep(n=200, out=None, timeout_s=30.0, budget_s=None, max_depth=2000,
          start=0, root=WHENCE_ROOT, echo=True):
    """Seeds `start .. start+n-1` through the guest oracle, one flushed
    JSONL row each, skipping seeds already in `out`.

    Returns the rows written THIS call. `budget_s` stops the sweep cleanly
    between seeds; what is on disk at that point is exactly what was
    measured, which is the whole point of the file format.
    """
    out = out or default_out("sweep")
    pkg = dict(load_whence(root, "r377audit"))
    pkg.setdefault("root", root)
    skip = done_seeds(out)
    rows, t0 = [], time.time()
    with open(out, "a", encoding="utf-8") as f:
        for seed in range(start, start + n):
            if seed in skip:
                continue
            if budget_s is not None and time.time() - t0 > budget_s:
                if echo:
                    print("budget %.0fs reached after %d seed(s)"
                          % (budget_s, len(rows)))
                break
            row = sweep_record(pkg, seed, timeout_s=timeout_s,
                               max_depth=max_depth)
            f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
            rows.append(row)
            if echo and (row["kind"] != "ok" or row["exempt"] or row["s"] > 10):
                print("seed %-5d %-11s %6.1fs  %s"
                      % (seed, row["kind"], row["s"], row["detail"][:90]))
    if echo:
        print("%d new row(s) in %.1fs -> %s" % (len(rows), time.time() - t0, out))
    return rows


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


def summarize(rows):
    """The owed numbers, as a dict (so a test can assert on them)."""
    n = len(rows)
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    fired = [r for r in rows if r.get("exempt_fields", 0)]
    hostv = [r for r in rows if r.get("host_valued", 0)]
    guestv = [r for r in rows if r.get("guest_valued", 0)]
    secs = sorted(r["s"] for r in rows)
    return {
        "seeds": n,
        "kinds": kinds,
        "exempt_seeds": len(fired),
        "exempt_rate": (len(fired) / n) if n else 0.0,
        "exempt_fields": sum(r.get("exempt_fields", 0) for r in rows),
        "host_valued_seeds": len(hostv),
        "host_valued_rate": (len(hostv) / n) if n else 0.0,
        "host_valued_seeds_list": [r["seed"] for r in hostv][:40],
        "guest_valued_seeds": len(guestv),
        "both_missed_seeds": len([r for r in rows if r.get("both_missed", 0)]),
        "exempt_seeds_list": [r["seed"] for r in fired][:60],
        "median_s": _pct(secs, 0.5),
        "p90_s": _pct(secs, 0.9),
        "mean_s": (sum(secs) / n) if n else 0.0,
        "max_s": secs[-1] if secs else 0.0,
        "total_s": sum(secs),
        "slowest": sorted(((r["s"], r["seed"]) for r in rows), reverse=True)[:5],
    }


def _pct(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    i = int(q * (len(sorted_vals) - 1))
    return sorted_vals[i]


def print_summary(s):
    print("seeds                        : %d" % s["seeds"])
    print("kinds                        : %s" % s["kinds"])
    print("depth exemption fired        : %d seed(s)  %.2f%%  (%d field(s))"
          % (s["exempt_seeds"], 100 * s["exempt_rate"], s["exempt_fields"]))
    print("  ... both_missed            : %d seed(s)" % s["both_missed_seeds"])
    print("  ... guest_valued           : %d seed(s)" % s["guest_valued_seeds"])
    print("  ... host_valued BLIND SPOT : %d seed(s)  %.2f%%  %s"
          % (s["host_valued_seeds"], 100 * s["host_valued_rate"],
             s["host_valued_seeds_list"]))
    print("seconds  median/mean/p90/max : %.2f / %.2f / %.2f / %.2f"
          % (s["median_s"], s["mean_s"], s["p90_s"], s["max_s"]))
    print("slowest (s, seed)            : %s" % (s["slowest"],))
    print("wall in oracle               : %.1fs" % s["total_s"])


# ----------------------------------------------------------------- ladder --

def patch_lib_source(root=WHENCE_ROOT, ceiling=400):
    """`self_eval.lang`'s library half with `GUEST_MAX_DEPTH` rewritten.

    Raises if the declaration is not found exactly once — a silent no-op
    here would make every ladder rung report the production ceiling's
    numbers under a different label, which is the one failure mode that
    would look like a result."""
    with open(os.path.join(root, "examples", "self_eval.lang"),
              encoding="utf-8") as f:
        lib = f.read().split(G.LIB_MARKER)[0]
    hits = [ln for ln in lib.split("\n") if ln.startswith(_CEILING_LINE)]
    if len(hits) != 1:
        raise ValueError("expected exactly 1 %r line, found %d"
                         % (_CEILING_LINE, len(hits)))
    return lib.replace(hits[0], "%s%d" % (_CEILING_LINE, ceiling))


def guest_depth_missed(harness, src):
    """Field names the GUEST scrubbed to `&DEPTHMISS&` for this program.

    Guest-only on purpose: the ladder asks what the guest DEMANDS, and
    re-running the host at every rung would triple the sweep's cost to
    re-derive an answer that cannot change."""
    rec = harness.eval_program(src)
    V = harness.V
    if isinstance(rec, V.Miss):
        return None                     # the guest evaluator itself derailed
    gv = rec.fields["v"].payload
    if not isinstance(gv, V.Record):
        return None
    return sorted(k for k, v in gv.fields.items()
                  if v.payload == G.DEPTH_SENTINEL)


class _Rung(object):
    """A guest harness at one ceiling, rebuilt on any error.

    `GuestHarness` is long-lived and mutable: `oracle_self_eval`'s own
    comment records that a SIGALRM landing mid-`eval_program` leaves the
    shared interpreter in an unknown state that then corrupts a LATER,
    unrelated program. The ladder times out on purpose (runaway seeds are
    most of what it is measuring), so it must evict on exactly the same
    rule."""

    def __init__(self, ceiling, root, max_depth):
        self.ceiling, self.root, self.max_depth = ceiling, root, max_depth
        self.lib = patch_lib_source(root, ceiling)
        self.pkg = load_whence(root, "r377lad%d" % ceiling)
        self.h = None
        self.builds = 0

    def harness(self):
        if self.h is None:
            self.h = G.GuestHarness(self.root, self.pkg, lib_source=self.lib,
                                    max_depth=self.max_depth)
            self.builds += 1
        return self.h

    def missed(self, src, timeout_s):
        val, err, secs = _guarded(
            lambda: guest_depth_missed(self.harness(), src), timeout_s)
        if err:
            self.h = None
        return val, err, secs


def ladder(n=40, out=None, rungs=LADDER, timeout_s=30.0, budget_s=None,
           max_depth=2000, start=0, root=WHENCE_ROOT, echo=True):
    """Each seed's guest-depth DEMAND, as a bracket, by descending `rungs`.

    For one seed: evaluate at the top rung (the real ceiling). If the guest
    already refused a field there, the seed's demand is UNBOUNDED — it has a
    runaway with no reachable base case, and no ceiling would have helped.
    Otherwise walk down until a field first goes `&DEPTHMISS&`; the demand
    lies in `(that rung, the rung above]`.

    Resumable and flushed per seed, like `sweep`.
    """
    out = out or default_out("ladder")
    lad = [_Rung(c, root, max_depth) for c in rungs]
    skip = done_seeds(out)
    rows, t0 = [], time.time()
    with open(out, "a", encoding="utf-8") as f:
        for seed in range(start, start + n):
            if seed in skip:
                continue
            if budget_s is not None and time.time() - t0 > budget_s:
                if echo:
                    print("budget %.0fs reached after %d seed(s)" % (budget_s, len(rows)))
                break
            row = demand_of(lad, G.generate_guest_program(seed), timeout_s)
            row["seed"] = seed
            f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
            rows.append(row)
            if echo:
                print("seed %-5d demand %-12s %5.1fs %s"
                      % (seed, row["demand"], row["s"], row["note"]))
    if echo:
        print("%d new row(s) in %.1fs (harness builds: %s) -> %s"
              % (len(rows), time.time() - t0, [r.builds for r in lad], out))
    return rows


def demand_of(lad, src, timeout_s=30.0):
    """One program's guest-depth demand bracket against a built `lad`."""
    t0 = time.time()
    top = lad[0]
    missed, err, _s = top.missed(src, timeout_s)
    if err:
        return {"demand": "error", "note": err,
                "s": round(time.time() - t0, 3), "ceiling": top.ceiling}
    if missed is None:
        return {"demand": "guest_miss", "note": "guest internal miss",
                "s": round(time.time() - t0, 3), "ceiling": top.ceiling}
    if missed:
        return {"demand": "unbounded", "note": "refused at %d: %s"
                % (top.ceiling, missed[:4]), "s": round(time.time() - t0, 3),
                "ceiling": top.ceiling, "lo": top.ceiling, "hi": None}
    prev = top.ceiling
    for rung in lad[1:]:
        m, err, _s = rung.missed(src, timeout_s)
        if err or m is None or m:
            lo, hi = rung.ceiling, prev
            break
        prev = rung.ceiling
    else:
        lo, hi = 0, prev                # clean even at the lowest rung
    return {"demand": "(%s, %s]" % (lo, hi), "lo": lo, "hi": hi,
            "note": "bounded", "s": round(time.time() - t0, 3),
            "ceiling": top.ceiling}


def summarize_ladder(rows):
    bounded = [r for r in rows if r.get("note") == "bounded"]
    unbounded = [r for r in rows if r.get("demand") == "unbounded"]
    his = sorted(r["hi"] for r in bounded)
    return {
        "seeds": len(rows),
        "bounded": len(bounded),
        "unbounded": len(unbounded),
        "unbounded_rate": (len(unbounded) / len(rows)) if rows else 0.0,
        "other": len(rows) - len(bounded) - len(unbounded),
        "max_bounded_hi": his[-1] if his else 0,
        "brackets": _hist(["(%s, %s]" % (r["lo"], r["hi"]) for r in bounded]),
        "unbounded_seeds": [r["seed"] for r in unbounded][:40],
    }


def _hist(items):
    h = {}
    for it in items:
        h[it] = h.get(it, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: -kv[1]))


# ------------------------------------------------- the corpus's own numbers --

_INT = re.compile(r"(?<![\w.])(\d+)(?!\.\d)")


def corpus_numbers(n=2000, start=0):
    """The largest integer LITERAL the guest grammar actually emits, over
    `n` generated programs, and how many programs carry one at or above the
    guest ceiling.

    A literal scan is a lower bound on what a program can pass to a
    recursive call — `expr` composes arithmetic, so `go(100 * 100)` reaches
    10000 with no literal above 100 — and that limitation is the reason
    `ladder` exists and is the primary evidence. This is the cheap half:
    it costs no evaluation at all, so a tripwire test can afford it on
    every run.
    """
    top, per_prog, at_or_above = 0, [], 0
    for seed in range(start, start + n):
        src = G.generate_guest_program(seed)
        vals = [int(m) for m in _INT.findall(src)]
        mx = max(vals) if vals else 0
        per_prog.append(mx)
        top = max(top, mx)
        if mx >= 400:
            at_or_above += 1
    per_prog.sort()
    return {"programs": n, "max_literal": top,
            "programs_with_literal_ge_400": at_or_above,
            "p50_max_literal": _pct(per_prog, 0.5),
            "p99_max_literal": _pct(per_prog, 0.99)}


def band():
    """The band a `host_valued` exemption needs, and what reaches it.

    The blind spot fires when a TAIL loop terminates on the host and not on
    the guest. The host charges a tail call no depth (SPEC rule 8) and stops
    at `DEFAULT_MAX_ITER`; the guest charges one guest frame per bounce and
    stops at `GUEST_MAX_DEPTH`. So the exemption's blind half is exactly the
    open band of iteration counts in between.
    """
    pkg = load_whence(WHENCE_ROOT, "r377band")
    host_max = pkg["Interpreter"].DEFAULT_MAX_ITER
    lib = patch_lib_source(WHENCE_ROOT, 400)
    guest_max = int([ln for ln in lib.split("\n")
                     if ln.startswith(_CEILING_LINE)][0].split("=")[1])
    return {"guest_ceiling": guest_max, "host_ceiling": host_max,
            "band": (guest_max, host_max), "band_width": host_max - guest_max}


# -------------------------------------------------------------------- cli --

def default_out(kind):
    here = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    d = os.path.join(here, "state", "swe", "round-377")
    if os.path.isdir(d):
        return os.path.join(d, "%s.jsonl" % kind)
    return os.path.join(os.getcwd(), "%s.jsonl" % kind)


def _flag(argv, name, cast=str, default=None):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def main(argv):
    cmd = argv[0] if argv else "summary"
    if cmd == "sweep":
        n = int(argv[1]) if len(argv) > 1 and not argv[1].startswith("-") else 200
        rows = sweep(n, out=_flag(argv, "--out"),
                     timeout_s=_flag(argv, "--timeout-s", float, 30.0),
                     budget_s=_flag(argv, "--budget-s", float),
                     start=_flag(argv, "--start", int, 0))
        print_summary(summarize(rows))
    elif cmd == "summary":
        path = _flag(argv, "--out") or default_out("sweep")
        print_summary(summarize(read_rows(path)))
    elif cmd == "ladder":
        n = int(argv[1]) if len(argv) > 1 and not argv[1].startswith("-") else 40
        ladder(n, out=_flag(argv, "--out"),
               timeout_s=_flag(argv, "--timeout-s", float, 30.0),
               budget_s=_flag(argv, "--budget-s", float),
               start=_flag(argv, "--start", int, 0))
        print(json.dumps(summarize_ladder(
            read_rows(_flag(argv, "--out") or default_out("ladder"))), indent=1))
    elif cmd == "ladder-summary":
        print(json.dumps(summarize_ladder(
            read_rows(_flag(argv, "--out") or default_out("ladder"))), indent=1))
    elif cmd == "corpusnums":
        n = int(argv[1]) if len(argv) > 1 else 2000
        print(json.dumps(corpus_numbers(n), indent=1))
    elif cmd == "band":
        print(json.dumps(band(), indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

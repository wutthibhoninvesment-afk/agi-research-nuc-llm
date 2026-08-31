"""What the tail-transparency oracle's SPACE exemption actually suppresses
(round 401, SWE-loop D — round 389's next-step item 5).

THE QUESTION THIS ANSWERS
-------------------------
`oracles.oracle_tail_transparency` runs a program twice: once as written, once
with every tail flag cleared, and requires the same answer. Because Whence
merges tail frames, the lifted form can run out of `max_depth` where the
original did not — so the oracle EXEMPTS any program whose lifted run reaches
the ceiling:

    if peak >= max_depth:        # `peak` is the LIFTED run's peak_depth
        return ok("... space-exempt")

Rounds 383 and 389 measured how often that branch fires (41 of 324 usable
seeds at `max_depth=500`; 3 at 5 000) and recorded its cost as `surface 0.0`
— when it fires, the whole comparison is dropped. That is the POTENTIAL cost.
Nobody had measured the REALIZED cost: of the firings, how many actually
suppressed an observable difference?

The data to answer it was already on the row and thrown away. `_answer`
returns `(answer, peak)` for BOTH runs, and both the oracle
(`a, _ = _answer(...)`) and `exemptmap.measure` (`a, _peak_a = ...`) discard
the ORIGINAL run's peak. That one number splits the firings in two:

  * `peak_a <  max_depth <= peak_b` — the original ran shallow (usually depth
    1: fully merged) and the lifted one hit the ceiling. The two answers
    differ because of the ceiling. This is what the exemption is FOR.

  * `peak_a >= max_depth` — BOTH runs hit the ceiling. Neither got further
    than the other; the depth miss is symmetric and the comparison is on
    equal footing. The exemption drops a comparison that was valid.

Round 401 measured both populations over the 41 firing seeds of round 389's
arm A. The numbers are in `knowledge/round-401-*.md`; the shape is that the
second population's suppressed difference is EMPTY in every case, which is
why tightening the branch is safe, and why the three seeds round 389 named as
"the corpus's only unbounded tail programs" were never worth converting: they
are in it.

A NOTE ON THE NAME "unbounded tail programs"
--------------------------------------------
Round 389's three survivors (140, 273, 341) are unbounded, and they contain
tail calls, but their runaway is NOT in tail position — `peak_a == peak_b ==
max_depth` at every ceiling. Tail merging cannot help them and raising
`max_depth` cannot convert them: their depth demand is right-censored at
every rung. `demand_bracket()` is the measurement that says so.

usage:
  python3 -m harness.swe.spacewitness scan [N] [--max-depth D] [--out P]
  python3 -m harness.swe.spacewitness seeds --seeds 140,273,341 [--max-depth D]
  python3 -m harness.swe.spacewitness bracket --seeds 140,273,341
  python3 -m harness.swe.spacewitness shrink --seeds 140,273,341
  python3 -m harness.swe.spacewitness report [--out P]
"""

import json
import os
import sys
import time

from . import instrument as INS
from . import oracles as O
from .exemptmap import default_out, guarded
from .fuzz import ProgramGen, WHENCE_ROOT, shrink as ddshrink
from .killers import load_whence

# Classes a T-SPACE firing can fall into. The names are the finding.
NOT_FIRED = "not_fired"                 # lifted run stayed under the ceiling
NO_TAIL = "no_tail"                     # nothing to lift (T-NONE's territory)
CEILING_ARTIFACT = "ceiling_artifact"   # only the lifted run hit it, and it mattered
FREE_LIFTED_ONLY = "free_lifted_only"   # only the lifted run hit it, nothing differed
FREE_BOTH_AT_CEILING = "free_both_at_ceiling"   # both hit it, nothing differed
SUPPRESSED_AT_CEILING = "suppressed_at_ceiling"  # both hit it AND they differed
RECURSION_ERROR = "recursion_error"     # the host stack, not the guest ceiling

#: The classes for which the exemption is doing no work: the comparison it
#: dropped would have passed. `FREE_LIFTED_ONLY` is kept exempt anyway (the
#: asymmetry is real even when today's corpus does not expose it); only
#: `FREE_BOTH_AT_CEILING` is safe to tighten, and that is what round 401
#: changed in `oracles.oracle_tail_transparency`.
FREE_CLASSES = (FREE_LIFTED_ONLY, FREE_BOTH_AT_CEILING)

#: The class that would be a real finding: two runs both stopped by the same
#: ceiling that nevertheless disagree. Zero in round 401's corpus. It is not
#: a bug in the oracle if it appears — it is a bug in the interpreter, and it
#: is exactly what the tightened branch now lets through.
ALARM_CLASSES = (SUPPRESSED_AT_CEILING,)

#: Ceilings for `demand_bracket`. A program whose ORIGINAL run is censored at
#: every rung has an unbounded depth demand: no ceiling would have helped.
#: Deliberately not `exemptaudit.LADDER` — that one brackets the GUEST
#: interpreter's ceiling and tops out at its production value of 400; this
#: brackets the HOST's `max_depth`, whose default in this suite is 500 and
#: whose language default is `Interpreter.DEFAULT_MAX_DEPTH` = 20 000.
BRACKET_RUNGS = (100, 500, 2000, 8000, 20000)


def both_at_ceiling_program(n=600):
    """A program that hits `max_depth` in BOTH forms and still has a tail
    call to lift — the shape round 389's three survivors have and the shape
    `exemptmap.deep_program` cannot produce.

    `deep_program` is a pure tail loop: the original runs flat, only the
    lifted copy hits the ceiling (`ceiling_artifact`). Here the depth is
    spent by a NON-tail recursion, which tail merging cannot help, while a
    separate harmless tail loop gives `clear_tail_flags` something to clear
    so the oracle does not take the `no tail calls` branch. Both forms then
    stop at the same wall with the same miss.
    """
    return ("fn deepr(n) { if n <= 0 { 0 } else { 1 + deepr(n - 1) } }\n"
            "fn loop(n) { if n <= 0 { 0 } else { loop(n - 1) } }\n"
            "let r = deepr(%d)\n"
            "let t = loop(3)\n"
            "print(str(t))\n" % n)


def load(root=WHENCE_ROOT, tag="r401space"):
    pkg = dict(load_whence(root, tag))
    pkg.setdefault("root", root)
    return pkg


def witness(pkg, src, max_depth=500):
    """Classify one program's relationship to the space exemption.

    Runs both forms exactly as `oracle_tail_transparency` does and keeps the
    number the oracle throws away — the ORIGINAL run's peak depth.
    """
    row = {"max_depth": max_depth}
    try:
        program = O._parse(pkg, src)
        lifted = O._parse(pkg, src)
    except (pkg["LexError"], pkg["ParseError"]) as e:
        row.update(klass="parse_error", detail=type(e).__name__)
        return row
    n = O.clear_tail_flags(lifted)
    row["n_tail"] = n
    if n == 0:
        row["klass"] = NO_TAIL
        return row
    tainted = O.provenance_tainted_names(program)
    whole = not O.reflects_on_provenance(program)
    row["n_tainted"] = len(tainted)
    row["whole"] = whole
    a, peak_a = O._answer(pkg, program, tainted, whole, max_depth=max_depth)
    row["peak_original"] = peak_a
    try:
        b, peak_b = O._answer(pkg, lifted, tainted, whole, max_depth=max_depth)
    except RecursionError:
        row.update(klass=RECURSION_ERROR, peak_lifted=None, suppressed="")
        return row
    row["peak_lifted"] = peak_b
    d = O.first_difference(a, b) or ""
    row["suppressed"] = d[:400]
    row["differs"] = bool(d)
    if peak_b < max_depth:
        row["klass"] = NOT_FIRED
    elif peak_a >= max_depth:
        row["klass"] = SUPPRESSED_AT_CEILING if d else FREE_BOTH_AT_CEILING
    else:
        row["klass"] = CEILING_ARTIFACT if d else FREE_LIFTED_ONLY
    return row


def witness_seed(pkg, seed, max_depth=500, stress_rate=0.5, timeout_s=30.0):
    src = ProgramGen(seed, stress_rate=stress_rate).program()
    row, err, secs = guarded(lambda: witness(pkg, src, max_depth=max_depth),
                             timeout_s)
    if err:
        row = {"klass": "error", "detail": err[:120], "max_depth": max_depth}
    row["seed"] = seed
    row["s"] = round(secs, 3)
    row["src_lines"] = src.count("\n") + 1
    return row


def scan(n=360, out=None, max_depth=500, start=0, stress_rate=0.5,
         root=WHENCE_ROOT, budget_s=None, echo=True):
    """Classify seeds `start .. start+n-1`. Resumable and flushed per seed,
    the same contract as `exemptmap.sweep`."""
    out = out or default_out("spacewitness")
    pkg = load(root)
    seen = set()
    if os.path.exists(out):
        for r in read_rows(out):
            if "seed" in r and r.get("max_depth") == max_depth:
                seen.add(r["seed"])
    rows, t0 = [], time.time()
    with open(out, "a", encoding="utf-8") as f:
        for seed in range(start, start + n):
            if seed in seen:
                continue
            if budget_s is not None and time.time() - t0 > budget_s:
                if echo:
                    print("budget %.0fs reached after %d seed(s)" % (budget_s, len(rows)))
                break
            row = witness_seed(pkg, seed, max_depth=max_depth,
                               stress_rate=stress_rate)
            row[INS.STAMP_KEY] = INS.stamp("spacewitness.scan")
            f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
            rows.append(row)
            if echo and seed % 50 == 0:
                print("  seed %d (%.1fs)" % (seed, time.time() - t0), flush=True)
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
    """Fire rate, and — the point of the module — the REALIZED cost."""
    counts = {}
    for r in rows:
        counts[r.get("klass", "?")] = counts.get(r.get("klass", "?"), 0) + 1
    fired = [r for r in rows if r.get("klass") in
             (CEILING_ARTIFACT, FREE_LIFTED_ONLY, FREE_BOTH_AT_CEILING,
              SUPPRESSED_AT_CEILING, RECURSION_ERROR)]
    paid = [r for r in fired if r.get("differs")]
    free = [r for r in fired if not r.get("differs")]
    tightenable = [r for r in fired if r.get("klass") == FREE_BOTH_AT_CEILING]
    alarm = [r for r in fired if r.get("klass") in ALARM_CLASSES]
    usable = [r for r in rows if r.get("klass") not in ("parse_error", "error")]
    return {
        "n_rows": len(rows),
        "n_usable": len(usable),
        "classes": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "fired": len(fired),
        "fire_rate": (len(fired) / len(usable)) if usable else None,
        # POTENTIAL cost is 1.0 by construction (a fired exemption drops the
        # whole comparison). REALIZED cost is what it actually hid.
        "realized_cost": (len(paid) / len(fired)) if fired else None,
        "paid": len(paid), "free": len(free),
        "paid_seeds": [r["seed"] for r in paid if "seed" in r][:60],
        "free_seeds": [r["seed"] for r in free if "seed" in r][:60],
        "tightenable": len(tightenable),
        "tightenable_seeds": [r["seed"] for r in tightenable if "seed" in r][:60],
        "alarm": len(alarm),
        "alarm_seeds": [r["seed"] for r in alarm if "seed" in r][:60],
        "max_depth": (rows[0].get("max_depth") if rows else None),
    }


def report(s):
    lines = ["space exemption: %d usable, %d fired (%.1f%%) at max_depth %s"
             % (s["n_usable"], s["fired"],
                100.0 * (s["fire_rate"] or 0.0), s["max_depth"])]
    lines.append("  potential cost 100.0% (a firing drops the whole comparison)")
    if s["realized_cost"] is not None:
        lines.append("  REALIZED  cost %5.1f%%  (%d of %d firings hid a real difference)"
                     % (100.0 * s["realized_cost"], s["paid"], s["fired"]))
    lines.append("  tightenable (both runs at the ceiling, nothing differed): %d"
                 % s["tightenable"])
    lines.append("  ALARM (both runs at the ceiling AND they differed): %d %s"
                 % (s["alarm"], s["alarm_seeds"] or ""))
    for k, v in s["classes"].items():
        lines.append("    %-24s %d" % (k, v))
    return "\n".join(lines)


def demand_bracket(pkg, src, rungs=BRACKET_RUNGS, timeout_s=60.0):
    """Is the ORIGINAL (un-lifted) run's depth demand bounded?

    Runs at each rung and records `peak_original`. A peak that equals the
    rung is RIGHT-CENSORED — the interpreter stopped, the program did not.
    Censored at every rung means unbounded: no ceiling converts this seed,
    which is a different statement from "the harness's ceiling is too low".
    """
    out = {"rungs": [], "unbounded": None}
    for c in rungs:
        r, err, secs = guarded(lambda c=c: witness(pkg, src, max_depth=c),
                               timeout_s)
        if err:
            out["rungs"].append({"rung": c, "error": err[:80],
                                 "s": round(secs, 2)})
            continue
        out["rungs"].append({
            "rung": c, "peak_original": r.get("peak_original"),
            "peak_lifted": r.get("peak_lifted"), "klass": r.get("klass"),
            "censored": r.get("peak_original") is not None
            and r["peak_original"] >= c,
            "s": round(secs, 2)})
    ok = [x for x in out["rungs"] if "error" not in x]
    out["unbounded"] = bool(ok) and all(x["censored"] for x in ok)
    out["n_rungs_run"] = len(ok)
    return out


def shrink_witness(pkg, seed, max_depth=500, stress_rate=0.5, timeout_s=20.0):
    """Minimise a seed's program while its CLASS is preserved.

    The invariant kept is the class, not the crash signature: this is not a
    crash reproducer, it is an exemption witness, and what a reader needs is
    the smallest program that still reaches the branch for the same reason.
    """
    src = ProgramGen(seed, stress_rate=stress_rate).program()
    base = witness(pkg, src, max_depth=max_depth)
    target = base.get("klass")

    def keep(cand):
        r, err, _s = guarded(
            lambda: witness(pkg, cand, max_depth=max_depth), timeout_s)
        return (not err) and r.get("klass") == target

    small = ddshrink(src, keep)
    out = {"seed": seed, "klass": target, "src_lines": src.count("\n") + 1,
           "original": src}
    if small is None:
        out["minimized"] = None
        out["note"] = "not reproducible on re-run (flaky); left unminimised"
        return out
    out["minimized"] = small
    out["min_lines"] = small.count("\n")
    out["min_witness"] = witness(pkg, small, max_depth=max_depth)
    return out


def _flag(argv, name, cast=str, default=None):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def _seed_list(argv, default=(140, 273, 341)):
    raw = _flag(argv, "--seeds")
    if not raw:
        return list(default)
    return [int(x) for x in raw.split(",") if x.strip()]


def main(argv):
    cmd = argv[0] if argv else "report"
    md = _flag(argv, "--max-depth", int, 500)
    out = _flag(argv, "--out") or default_out("spacewitness")
    if cmd == "scan":
        n = int(argv[1]) if len(argv) > 1 and not argv[1].startswith("-") else 360
        scan(n, out=out, max_depth=md, start=_flag(argv, "--start", int, 0),
             budget_s=_flag(argv, "--budget-s", float))
        print(report(summarize([r for r in read_rows(out)
                                if r.get("max_depth") == md])))
    elif cmd == "report":
        print(report(summarize([r for r in read_rows(out)
                                if r.get("max_depth") == md])))
    elif cmd == "json":
        print(json.dumps(summarize([r for r in read_rows(out)
                                    if r.get("max_depth") == md]), indent=1))
    elif cmd == "seeds":
        pkg = load()
        for s in _seed_list(argv):
            print(json.dumps(witness_seed(pkg, s, max_depth=md), sort_keys=True))
    elif cmd == "bracket":
        pkg = load()
        for s in _seed_list(argv):
            src = ProgramGen(s, stress_rate=0.5).program()
            print(json.dumps(dict(seed=s, **demand_bracket(pkg, src)),
                             sort_keys=True))
    elif cmd == "shrink":
        pkg = load()
        for s in _seed_list(argv):
            r = shrink_witness(pkg, s, max_depth=md)
            print("### seed %d  klass=%s  %d -> %s lines"
                  % (s, r["klass"], r["src_lines"], r.get("min_lines")))
            print(r["minimized"] or r["original"])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

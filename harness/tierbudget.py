"""Measured fast/slow tiering for `harness/tests/` (round 385, harness A).

The problem this replaces
-------------------------
Round 235 drew this repo's harness tier boundary as a FILENAME RULE:
`harness/tests/conftest.py` marks every `test_swe_*.py` file `swe_slow`, and
`run_tests_fast.sh` deselects the marker. Round 235 preferred a filename
pattern to a hand-maintained list *on purpose* — a new `test_swe_*.py` file
tiers itself with nothing to keep in sync — and it justified the boundary
with a seven-row cost table it did not measure: the rows were quoted out of
rounds 193/209/215/217/221's knowledge files, which were already up to 42
rounds old when round 235 read them.

That is a corpus-derived claim in round 383 item 4's sense, and corpus-derived
claims rot. `test_swe_*.py` names a SUBSYSTEM, not a cost, and a subsystem's
cost moves every time someone rewrites a test to stop shelling out. Round 383
found the boundary hiding two red things, one of them red for fifteen rounds,
and asked for the injected-bug tests specifically to be promoted. This module
answers the general question instead: what does each file cost NOW, and which
of them were only ever slow by adjacency?

The design, and why it is allowed to be a list
----------------------------------------------
A promotion registry (`harness/tier-budget.json`) is exactly the
hand-maintained list round 235 refused, so it only earns its place by being
safe in the two ways that list would not have been:

  FAIL-CLOSED. The filename rule still decides the DEFAULT and it still
  decides it alone: absent from the registry means slow. A new
  `test_swe_*.py` file is slow with no edit anywhere, which is round 235's
  self-maintenance property, kept. The registry can only ever move a file
  toward "fast", i.e. toward the tier a human is watching, and only when a
  measurement says it is cheap. A stale registry costs wall-clock; it cannot
  cost coverage.

  SELF-RE-MEASURING FOR FREE. Every promoted file is timed by the run that
  was already happening. `conftest.py`'s `pytest_terminal_summary` hook adds
  up each file's collect + setup/call/teardown reports and calls
  `verify()`, so the health check the driver runs every round prints whether
  the numbers in this file are still true. Nothing here needs a second pytest
  process, a new dependency, or a checker anybody has to remember to run —
  the failure mode round 363 named for the skills corpus and round 385's own
  §"unrun checker" note.

`measure()` is the ladder that produces the registry's numbers: each file
alone, in a fresh process, under a wall-clock cap, so an expensive file costs
the cap instead of its full runtime.

Round 385 expected a standalone measurement to be an UPPER BOUND on the same
file's cost inside a shared session, since interpreter startup and module
imports are paid once there rather than once per file. IN AGGREGATE that
held — the nine promoted files measured 40.5 s standalone and cost 36.2 s of
marginal wall-clock inside the fast tier, about 11 % less. PER FILE it did
not: `test_swe_proc.py` measured 6.7 s alone and was timed at 8.1 s in the
session, because a shared process is also a CONTENDED one (warm caches cut
some files' cost, a busy box and a fuller heap raise others'). So the ladder
is a good ESTIMATOR and not a bound, which is exactly why the drift rule is
`max(2x, +3 s)` rather than `> measured_s`: a budget equal to the estimate
would alarm on the first honest re-measurement. Do not tighten it to the
estimate without re-deriving this.

Everything is offline-testable: `measure()` takes an injectable `runner`, so
no test in `test_tierbudget.py` shells out to pytest.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TESTS_DIR = os.path.join(REPO_ROOT, "harness", "tests")
REGISTRY_PATH = os.path.join(REPO_ROOT, "harness", "tier-budget.json")

#: The filename rule round 235 wrote. Still the default, still alone.
SLOW_PREFIX = "test_swe_"

#: Defaults used when the registry does not say otherwise.
DEFAULT_CAP_S = 25.0
DEFAULT_DRIFT_FACTOR = 2.0
DEFAULT_DRIFT_FLOOR_S = 3.0

_COUNT_RE = re.compile(
    r"(\d+) (passed|failed|error|errors|skipped|deselected|xfailed|xpassed)")


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
def load_registry(path=None):
    """The registry, or an empty one. A missing/broken file means NOTHING is
    promoted — the fail-closed direction. It must never raise: this is read
    from `conftest.py`, and a tier registry that can abort collection would
    be a strictly worse version of round 348's `pyproject.toml` outage."""
    path = path or REGISTRY_PATH
    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception:
        return {"promoted": {}, "cap_s": DEFAULT_CAP_S,
                "drift_factor": DEFAULT_DRIFT_FACTOR,
                "drift_floor_s": DEFAULT_DRIFT_FLOOR_S,
                "_load_error": True}
    if not isinstance(data, dict) or not isinstance(data.get("promoted"), dict):
        return {"promoted": {}, "cap_s": DEFAULT_CAP_S,
                "drift_factor": DEFAULT_DRIFT_FACTOR,
                "drift_floor_s": DEFAULT_DRIFT_FLOOR_S,
                "_load_error": True}
    data.setdefault("cap_s", DEFAULT_CAP_S)
    data.setdefault("drift_factor", DEFAULT_DRIFT_FACTOR)
    data.setdefault("drift_floor_s", DEFAULT_DRIFT_FLOOR_S)
    return data


def is_slow(basename, registry=None):
    """The whole tier decision, in one place. Round 235's filename rule,
    minus the registry's promotions. Note the asymmetry: a file that does NOT
    match the prefix is fast whatever the registry says, so the registry can
    never demote a core-harness file by accident."""
    if not basename.startswith(SLOW_PREFIX):
        return False
    reg = registry if registry is not None else load_registry()
    return basename not in reg.get("promoted", {})


def budget_for(basename, registry):
    """The wall-clock a promoted file is allowed before it counts as drifted.

    `factor` alone is wrong at the bottom of the range: `test_swe_triage.py`
    at 0.4 s would alarm at 0.9 s, which is noise on a one-CPU box that also
    runs a driver. The floor makes the rule "twice as slow, or three seconds
    slower, whichever is more generous"."""
    entry = registry.get("promoted", {}).get(basename)
    if entry is None:
        return None
    base = float(entry.get("measured_s", 0.0))
    return max(base * float(registry.get("drift_factor", DEFAULT_DRIFT_FACTOR)),
               base + float(registry.get("drift_floor_s", DEFAULT_DRIFT_FLOOR_S)))


# --------------------------------------------------------------------------
# the ladder
# --------------------------------------------------------------------------
def swe_files(tests_dir=None):
    tests_dir = tests_dir or TESTS_DIR
    return sorted(
        f for f in os.listdir(tests_dir)
        if f.startswith(SLOW_PREFIX) and f.endswith(".py")
    )


def _default_runner(path, cap_s):
    """One file, fresh process, hard wall-clock cap.

    `PYTHONDONTWRITEBYTECODE=1` is round 340's lesson: a `.pyc` cache-key
    collision (same size, same second) made a mutant re-test its predecessor.
    Timing runs have the same exposure in reverse — the first file measured
    would pay for compiling the tree and every later one would not."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", path],
            cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=cap_s, env=env,
        )
        return {"seconds": time.time() - t0, "returncode": proc.returncode,
                "stdout": proc.stdout, "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"seconds": time.time() - t0, "returncode": None,
                "stdout": "", "timed_out": True}


def _counts(stdout):
    return {kind: int(n) for n, kind in _COUNT_RE.findall(stdout or "")}


def measure(files=None, cap_s=DEFAULT_CAP_S, tests_dir=None, runner=None):
    """Time each file alone. Returns one row per file, in input order.

    `outcome` is deliberately four-valued, and `over_cap` is NOT a failure:
    it is the honest statement "this file costs at least `cap_s`", which is
    all a promotion decision needs from an expensive file. Round 341's rule
    1 in another key — absence of a number is recorded as absence, never as
    a small number."""
    tests_dir = tests_dir or TESTS_DIR
    runner = runner or _default_runner
    files = list(files) if files is not None else swe_files(tests_dir)
    rows = []
    for name in files:
        res = runner(os.path.join(tests_dir, name), cap_s)
        counts = _counts(res.get("stdout"))
        if res.get("timed_out"):
            outcome = "over_cap"
        elif res.get("returncode") == 0:
            outcome = "passed"
        elif counts.get("failed") or counts.get("error") or counts.get("errors"):
            outcome = "failed"
        else:
            outcome = "error"
        row = {
            "file": name,
            "seconds": round(float(res.get("seconds", 0.0)), 2),
            "outcome": outcome,
            "returncode": res.get("returncode"),
            "counts": counts,
            "cap_s": cap_s,
        }
        # Round 385, added mid-round after this module bit its own author:
        # the ladder's first run turned `test_swe_prioritize.py` red at 2.9s
        # and the row said only `1 failed`. The output that said WHICH test
        # and WHY had been captured, held in `res["stdout"]`, and dropped on
        # the floor — the exact shape round 384 named one track over ("a
        # diagnostic computed into a value nobody keeps"), reproduced here
        # inside a round that had just read that finding. A ladder run costs
        # minutes; re-running it to find out what a red file said is the
        # whole cost again, so the tail is kept for anything that is not a
        # clean pass. Bounded, because a ledger is not a log.
        if outcome != "passed":
            row["tail"] = (res.get("stdout") or "")[-2000:]
        rows.append(row)
    return rows


def promotable(rows, cap_s=DEFAULT_CAP_S):
    """Rows a registry may promote: measured under the cap AND green.

    A red file is not promotable, and that is not a policy preference. The
    fast tier is what the driver's per-round health check reports on, so
    promoting a failing file would turn every future round's `health-check`
    line red for a defect the promotion did not cause — which is how a check
    gets ignored and then uninstalled (round 363's own stated reason for
    splitting errors from warnings). Fix the file, then promote it."""
    return [r for r in rows
            if r["outcome"] == "passed" and r["seconds"] < cap_s]


# --------------------------------------------------------------------------
# the free self-check
# --------------------------------------------------------------------------
def verify(observed, registry=None):
    """Compare per-file durations OBSERVED in a run against the registry.

    `observed` maps basename -> seconds, and comes from `conftest.py`'s
    terminal-summary hook, i.e. from the run that was happening anyway.
    Files absent from `observed` are simply not evidence this run (a
    `-k` selection, a `--collect-only`), never a pass and never a drift."""
    reg = registry if registry is not None else load_registry()
    promoted = reg.get("promoted", {})
    rows, drifted = [], []
    for name in sorted(promoted):
        if name not in observed:
            continue
        seconds = float(observed[name])
        budget = budget_for(name, reg)
        row = {"file": name, "seconds": round(seconds, 2),
               "budget_s": round(budget, 2),
               "measured_s": float(promoted[name].get("measured_s", 0.0)),
               "drifted": seconds > budget}
        rows.append(row)
        if row["drifted"]:
            drifted.append(row)
    return {
        "n_promoted": len(promoted),
        "n_observed": len(rows),
        "rows": rows,
        "drifted": drifted,
        "observed_total_s": round(sum(r["seconds"] for r in rows), 2),
        "registry_total_s": round(
            sum(float(v.get("measured_s", 0.0)) for v in promoted.values()), 2),
        "load_error": bool(reg.get("_load_error")),
    }


def format_verify_line(result):
    """One line, and deliberately NOT pytest-shaped.

    `driver_health.split_measured_output` treats a pytest terminal-count line
    as a boundary candidate and `classify_health_log` quotes the LAST line of
    the measured half into `driver.log`. This hook prints from
    `pytest_terminal_summary`, which pytest calls BEFORE it writes its own
    count line, so the count line stays last and the driver's parenthetical
    is unchanged. The wording avoids `N passed`/`in 1.23s` so that even if a
    future caller prints it somewhere else it cannot be mistaken for one."""
    if result.get("load_error"):
        return "tier-budget: registry unreadable — nothing promoted, tier is round 235's filename rule"
    if not result["n_promoted"]:
        return "tier-budget: no files promoted; tier is round 235's filename rule"
    if not result["n_observed"]:
        return ("tier-budget: %d promoted, none ran here — no evidence this run"
                % result["n_promoted"])
    worst = max(result["rows"], key=lambda r: r["seconds"] / max(r["budget_s"], 1e-9))
    head = ("tier-budget: %d/%d promoted files timed, %.1fs of a %.1fs budget"
            % (result["n_observed"], result["n_promoted"],
               result["observed_total_s"], result["registry_total_s"]))
    if result["drifted"]:
        return (head + " — DRIFT: "
                + ", ".join("%s %.1fs > %.1fs" % (r["file"], r["seconds"], r["budget_s"])
                            for r in result["drifted"])
                + " (re-run `python3 harness/tierbudget.py measure` and re-decide)")
    return head + " — worst %s %.1fs of %.1fs" % (
        worst["file"], worst["seconds"], worst["budget_s"])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _cmd_measure(args):
    files = args.files or None
    rows = measure(files=files, cap_s=args.cap_s)
    cap = args.cap_s
    print("%-34s %9s  %-9s %s" % ("file", "seconds", "outcome", "counts"))
    for r in rows:
        secs = ">= %.1f" % cap if r["outcome"] == "over_cap" else "%9.2f" % r["seconds"]
        print("%-34s %9s  %-9s %s" % (r["file"], secs, r["outcome"],
                                      ",".join("%d %s" % (v, k) for k, v in sorted(r["counts"].items()))))
    ok = promotable(rows, cap)
    print()
    print("under cap and green: %d of %d, %.1fs total"
          % (len(ok), len(rows), sum(r["seconds"] for r in ok)))
    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"cap_s": cap, "rows": rows}, fh, indent=2)
        print("wrote %s" % args.out)
    return 0


def _cmd_status(args):
    reg = load_registry(args.registry)
    promoted = reg.get("promoted", {})
    present = set(swe_files())
    print("tier-budget registry: %s" % (args.registry or REGISTRY_PATH))
    print("  cap %.1fs, drift factor %.1fx, floor %.1fs"
          % (reg["cap_s"], reg["drift_factor"], reg["drift_floor_s"]))
    print("  %d of %d test_swe_*.py files promoted to the fast tier"
          % (len(promoted), len(present)))
    for name in sorted(promoted):
        e = promoted[name]
        missing = "" if name in present else "   <-- NO SUCH FILE"
        print("    %-34s %6.1fs  (round %s)%s"
              % (name, float(e.get("measured_s", 0.0)), e.get("measured_round", "?"), missing))
    stale = sorted(set(promoted) - present)
    if stale:
        print("  %d promoted entr(y/ies) name a file that does not exist" % len(stale))
    return 1 if stale else 0


def _cmd_verify(args):
    with open(args.durations) as fh:
        observed = json.load(fh)
    result = verify(observed, load_registry(args.registry))
    print(format_verify_line(result))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("measure", help="time each test_swe_*.py alone, under a cap")
    m.add_argument("--cap-s", type=float, default=DEFAULT_CAP_S)
    m.add_argument("--out")
    m.add_argument("files", nargs="*")
    m.set_defaults(fn=_cmd_measure)

    s = sub.add_parser("status", help="print the registry against the tree")
    s.add_argument("--registry")
    s.set_defaults(fn=_cmd_status)

    v = sub.add_parser("verify", help="check observed durations against the registry")
    v.add_argument("--durations", required=True)
    v.add_argument("--registry")
    v.set_defaults(fn=_cmd_verify)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

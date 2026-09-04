#!/usr/bin/env python3
"""seedsweep.py — cross-process determinism (R3) with a same-seed control.

Round 483 (skills B).

The check everybody writes
--------------------------
Run a deriver in three subprocesses with three different `PYTHONHASHSEED`
values, compare the output, call a difference a hash-order bug. This tree
has that check twice — `languages/whence/reprsweep.py:374` (seeds
`0,1,12345`) and `harness/tests/test_wiring_audit.py:806` (seeds `0,1,2`) —
and `skills/audit-the-deriver-first/SKILL.md` step 4 prescribes it in prose.

Why it is not sound as written
------------------------------
Both runners vary ONE thing (the seed) and run every configuration ONCE.
A difference between two runs therefore has at least four candidate causes:

  1. hash order      — the thing the sweep is about
  2. the clock       — a duration, a timestamp, an elapsed field
  3. the environment — pid, cwd, tempdir name, `os.urandom`
  4. the tree        — a file another process wrote between run 1 and run 3

Only (1) is a finding, and the sweep's report has exactly one word for all
four. The missing arm is a **same-seed control**: the same configuration run
twice. It costs one extra process and it converts the verdict from an
assumption into a measurement:

    control identical, cross-seed identical   -> stable
    control identical, cross-seed differs     -> seed_dependent      <- finding
    control differs,   cross-seed differs     -> volatile / both
    control differs,   shape changes too      -> unscrubbable

and — the part that is genuinely reusable — when the control DOES differ,
the regions it differs in are the scrub set. You do not declare "ignore
`elapsed_s` and `generated_at`" a priori and hope you listed them all; you
measure which parts of the output move when nothing moves, mask exactly
those, and re-decide the seed question on what is left. A declared scrub
list is a claim; a derived one is an observation.

The blind spot, stated up front
-------------------------------
`PYTHONHASHSEED` randomises the hash of `str`, `bytes` and `datetime`
objects. It does NOT touch `int`: CPython hashes a small non-negative int to
itself, so `set(range(9))` iterates in the same order in every process at
every seed. An order dependence over a set of ints is invisible to every
seed sweep, this one included. `subjects.json` carries a live synthetic
subject (`ctl_blindspot_int_set`) that is genuinely order-dependent and that
this instrument correctly reports `stable`, so the blind spot is a running
test rather than a sentence.

Power
-----
A green sweep is not proof of determinism, it is a bound. If a tie is broken
uniformly at random among `n` candidates, `k` runs all agree by chance with
probability `n ** -(k - 1)`. At the k=3 both live runners use, a **two-way
tie survives 25 % of the time**. `power` prints the table; `run` prints the
bound it achieved beside its verdict so a NULL is never reported bare.

Usage
-----
    python3 seedsweep.py list
    python3 seedsweep.py run [--only ID,ID] [--seeds N] [--control-runs N]
                             [--json] [--timeout S]
    python3 seedsweep.py power [--max-n N] [--max-k N] [--json]
    python3 seedsweep.py census [--json]
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SUBJECTS = os.path.join(HERE, "subjects.json")

#: Cross-seed arm. Deliberately excludes `0`: `PYTHONHASHSEED=0` DISABLES
#: randomisation rather than selecting a seed, so a sweep over `0,1,2`
#: spends one of its three runs on a different question. It is still a
#: distinct order and both live runners in this tree include it; it is not
#: wrong, it is one fewer random draw than the count suggests.
DEFAULT_SEEDS = ("1", "2", "3", "5", "8")

#: Same-seed arm. One value, run `DEFAULT_CONTROL_RUNS` times.
CONTROL_SEED = "1"
DEFAULT_CONTROL_RUNS = 2

VERDICTS = ("stable", "seed_dependent", "volatile",
            "seed_dependent_under_volatility", "unscrubbable", "error")

#: Verdicts that mean "this instrument does not produce one answer".
BAD_VERDICTS = ("seed_dependent", "seed_dependent_under_volatility",
                "unscrubbable", "error")


# --------------------------------------------------------------------------
# power
# --------------------------------------------------------------------------

def miss_probability(n, k):
    """P(k independent uniform draws over an n-way tie all agree).

    `n` is the tie WIDTH (number of candidates that could be picked), `k`
    the number of runs. n=1 is not a tie and can never be missed... except
    that there is nothing to miss, so the probability is 1.0 by convention
    only when k < 2.
    """
    if n < 2:
        return 0.0
    if k < 2:
        return 1.0
    return float(n) ** (-(k - 1))


def min_seeds(n, alpha):
    """Smallest k with `miss_probability(n, k) <= alpha`.

    Searched rather than solved. The closed form `1 + ceil(log(1/alpha) /
    log(n))` is right on paper and wrong in floats exactly where it matters:
    at n=10, alpha=0.001 the quotient is 3.0000000000000004, `ceil` takes it
    to 4, and the answer comes back one seed too expensive with no sign that
    anything happened.
    """
    if n < 2 or alpha >= 1.0:
        return 2
    k = 2
    while miss_probability(n, k) > alpha and k < 4096:
        k += 1
    return k


def widest_tie_bounded(k, alpha):
    """The widest tie a k-run green sweep bounds below `alpha`.

    Returns the largest `n` with `miss_probability(n, k) <= alpha`, or None
    when no n>=2 qualifies. Note the direction: miss probability FALLS as
    the tie gets wider, so this is a lower bound on n, and the honest
    reading is "ties NARROWER than this are the ones k cannot see".
    """
    if k < 2:
        return None
    n = 2
    while miss_probability(n, k) > alpha:
        n += 1
        if n > 10 ** 6:
            return None
    return n


# --------------------------------------------------------------------------
# subjects
# --------------------------------------------------------------------------

REQUIRED_FIELDS = ("id", "argv", "why", "owner", "expect")


def load_subjects(path=None):
    path = path or DEFAULT_SUBJECTS
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    subs = doc["subjects"]
    seen = set()
    for s in subs:
        missing = [f for f in REQUIRED_FIELDS if f not in s]
        if missing:
            raise ValueError("subject %r missing %s"
                             % (s.get("id", "?"), ", ".join(missing)))
        if s["id"] in seen:
            raise ValueError("duplicate subject id %r" % s["id"])
        seen.add(s["id"])
        if s["expect"] not in VERDICTS + ("any",):
            raise ValueError("subject %r: expect=%r is not a verdict"
                             % (s["id"], s["expect"]))
    return doc


def repo_root(start=None):
    cur = start or HERE
    while cur != os.path.dirname(cur):
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        cur = os.path.dirname(cur)
    return os.path.abspath(os.path.join(HERE, "..", "..", ".."))


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------

def run_once(subject, seed, root, timeout=300, python=None):
    """One process. Returns the comparable PAYLOAD, not just stdout.

    The return code is folded into the payload's first line. A deriver that
    answers 0 in one process and 1 in another is exactly as nondeterministic
    as one whose stdout moves, and a comparison over stdout alone silently
    exempts that shape.
    """
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    # A .pyc written by run 1 and read by run 2 is a difference between the
    # runs that has nothing to do with the seed; it would land in the
    # control's own noise and widen the scrub set for no reason.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONSTARTUP", None)
    argv = [python or sys.executable] + list(subject["argv"])
    cwd = os.path.join(root, subject.get("cwd", "."))
    t0 = time.time()
    try:
        proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"launch_error": "timeout after %ss" % timeout,
                "payload": None, "elapsed_s": time.time() - t0}
    except OSError as exc:
        return {"launch_error": str(exc), "payload": None,
                "elapsed_s": time.time() - t0}
    payload = "#rc %d\n%s" % (proc.returncode, proc.stdout)
    return {"launch_error": None, "payload": payload, "rc": proc.returncode,
            "stderr_tail": proc.stderr[-400:], "elapsed_s": time.time() - t0}


# --------------------------------------------------------------------------
# did the perturbation actually happen?
# --------------------------------------------------------------------------

_WITNESS_PROG = ("import sys;print(hash('the-seedsweep-perturbation-witness'))")


def perturbation_witness(seeds=DEFAULT_SEEDS, python=None):
    """Prove the seeds took effect BEFORE believing any `stable`.

    Neither live runner in this tree checks this, and the failure is silent
    in the direction that matters: misspell the variable, let a
    `sitecustomize` pin it, let the subject re-exec through a wrapper that
    scrubs the environment, and every subject reports `stable`. A sweep that
    cannot perturb anything is not a green sweep, it is a no-op wearing
    one -- which is `witness-must-sit-outside-the-guard` applied to the
    guard's own input.

    Returns the distinct `hash(str)` values observed. Fewer than two means
    the arm is dead.
    """
    vals = []
    for s in seeds:
        env = dict(os.environ, PYTHONHASHSEED=str(s),
                   PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run([python or sys.executable, "-c", _WITNESS_PROG],
                              env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            return {"effective": False, "n_distinct": 0,
                    "detail": proc.stderr[-300:]}
        vals.append(proc.stdout.strip())
    return {"effective": len(set(vals)) > 1, "n_distinct": len(set(vals)),
            "n_seeds": len(vals), "values": vals}


# --------------------------------------------------------------------------
# comparison and the DERIVED scrub set
# --------------------------------------------------------------------------

def _json_body(payload):
    """The JSON object a payload's body parses to, or None."""
    body = payload.split("\n", 1)[1] if "\n" in payload else ""
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return None


def _flatten(obj, prefix=""):
    """Leaf key-paths of a JSON value. A list index is part of the path."""
    out = {}
    if isinstance(obj, dict):
        for k in obj:
            out.update(_flatten(obj[k], "%s.%s" % (prefix, k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, "%s[%d]" % (prefix, i)))
    else:
        out[prefix or "."] = obj
    return out


def differing_paths(payloads):
    """Leaf key-paths that are not identical across every payload.

    Returns `None` when the payloads are not all JSON, or when their key
    SETS differ — a key set that moves is a shape change, and masking a
    shape change would be inventing agreement.
    """
    objs = [_json_body(p) for p in payloads]
    if any(o is None for o in objs):
        return None
    flats = [_flatten(o) for o in objs]
    keys = set(flats[0])
    if any(set(f) != keys for f in flats[1:]):
        return None
    return sorted(k for k in keys
                  if any(f[k] != flats[0][k] for f in flats[1:]))


def differing_lines(payloads):
    """Line indices that are not identical across every payload.

    `None` when the payloads have different line COUNTS: same reasoning as
    `differing_paths`, one level cruder.
    """
    splits = [p.split("\n") for p in payloads]
    n = len(splits[0])
    if any(len(s) != n for s in splits[1:]):
        return None
    return [i for i in range(n)
            if any(s[i] != splits[0][i] for s in splits[1:])]


def mask_from_control(control_payloads):
    """The scrub set, DERIVED from runs that differ in nothing but time.

    Returns `(kind, mask)` where kind is `"none"` (control agreed — nothing
    to scrub), `"json"` (mask is a list of leaf key-paths), `"lines"` (mask
    is a list of line indices) or `"unscrubbable"` (the control's own runs
    disagree in SHAPE, so no mask can localise the noise).
    """
    if len(set(control_payloads)) == 1:
        return ("none", [])
    paths = differing_paths(control_payloads)
    if paths is not None:
        return ("json", paths)
    lines = differing_lines(control_payloads)
    if lines is not None:
        return ("lines", lines)
    return ("unscrubbable", [])


def apply_mask(payload, kind, mask):
    if kind == "none" or not mask:
        return payload
    if kind == "json":
        obj = _json_body(payload)
        if obj is None:
            return payload
        flat = _flatten(obj)
        for k in mask:
            flat[k] = "<masked>"
        return "#masked-json\n" + json.dumps(
            [[k, flat[k]] for k in sorted(flat)], sort_keys=True, default=str)
    if kind == "lines":
        lines = payload.split("\n")
        for i in mask:
            if 0 <= i < len(lines):
                lines[i] = "<masked>"
        return "\n".join(lines)
    return payload


# --------------------------------------------------------------------------
# the probe
# --------------------------------------------------------------------------

def probe(subject, root=None, seeds=DEFAULT_SEEDS,
          control_runs=DEFAULT_CONTROL_RUNS, timeout=300, python=None):
    """Same-seed control FIRST, then the cross-seed arm, then the verdict.

    The order matters for reading the result, not for the arithmetic: the
    control is what licenses any statement about the seed at all, so it is
    what runs first and what a caller sees first in the row.
    """
    root = root or repo_root()
    row = {"id": subject["id"], "owner": subject.get("owner"),
           "expect": subject.get("expect", "any"),
           "argv": list(subject["argv"]), "n_seeds": len(seeds),
           "control_runs": control_runs, "seeds": list(seeds)}

    ctl = [run_once(subject, CONTROL_SEED, root, timeout, python)
           for _ in range(control_runs)]
    errs = [r["launch_error"] for r in ctl if r["launch_error"]]
    if errs:
        row.update(verdict="error", detail=errs[0])
        return row

    ctl_payloads = [r["payload"] for r in ctl]
    kind, mask = mask_from_control(ctl_payloads)
    row["control_agrees"] = (kind == "none")
    row["mask_kind"] = kind
    row["mask"] = mask[:40]
    row["n_masked"] = len(mask)
    row["elapsed_s"] = round(sum(r["elapsed_s"] for r in ctl), 3)

    if kind == "unscrubbable":
        row.update(verdict="unscrubbable",
                   detail="the same seed run %d times disagreed in SHAPE; "
                          "no mask can localise the noise, so no statement "
                          "about hash order is available from this subject"
                          % control_runs)
        return row

    cross = [run_once(subject, s, root, timeout, python) for s in seeds]
    errs = [r["launch_error"] for r in cross if r["launch_error"]]
    if errs:
        row.update(verdict="error", detail=errs[0])
        return row
    row["elapsed_s"] = round(row["elapsed_s"]
                             + sum(r["elapsed_s"] for r in cross), 3)
    row["rcs"] = sorted(set(r["rc"] for r in cross + ctl))
    row["bytes"] = len(cross[0]["payload"])

    raw = [r["payload"] for r in cross]
    row["raw_cross_agrees"] = (len(set(raw)) == 1)
    if kind == "json" and any(_json_body(p) is None for p in raw):
        # The mask is a set of JSON key paths and at least one perturbed run
        # did not produce JSON. Masking one side and not the other would
        # manufacture a difference and report it as hash order.
        row.update(verdict="unscrubbable",
                   detail="the control's mask is over JSON key paths but a "
                          "perturbed run did not emit JSON; the two arms "
                          "cannot be compared on equal terms")
        return row
    masked = [apply_mask(p, kind, mask) for p in raw]
    row["cross_agrees"] = (len(set(masked)) == 1)

    if row["control_agrees"]:
        row["verdict"] = "stable" if row["cross_agrees"] else "seed_dependent"
    else:
        row["verdict"] = ("volatile" if row["cross_agrees"]
                          else "seed_dependent_under_volatility")

    # What a NAIVE sweep -- cross-seed only, no control -- would have said.
    # This is the number the skill is about, so it is measured per subject
    # rather than asserted once in the prose.
    row["naive_verdict"] = ("stable" if row["raw_cross_agrees"]
                            else "seed_dependent")
    row["control_changed_the_verdict"] = (row["naive_verdict"]
                                          != row["verdict"])
    if not row["cross_agrees"]:
        row["witness"] = _first_difference(masked)
    return row


def _first_difference(payloads):
    """A short, quotable witness: the first line index that differs."""
    splits = [p.split("\n") for p in payloads]
    for i in range(min(len(s) for s in splits)):
        vals = set(s[i] for s in splits)
        if len(vals) > 1:
            return {"line": i, "values": sorted(v[:160] for v in vals)[:4]}
    return {"line": None, "values": ["outputs differ in length only"]}


def is_error(row):
    """A verdict is an error when it CONTRADICTS the registry, not when it
    is merely bad.

    The first draft counted every `seed_dependent` / `unscrubbable` row as
    an error, which meant `run` could never exit 0 while the six synthetic
    controls were registered -- and a control set that is registered on
    purpose is exactly what makes the sheet readable. A check that cannot
    go green gets uninstalled; this repo says so in
    `state/known-unprobed-skills.json`'s own `_comment`, about a different
    checker, and this one had the same defect.

    So: a subject that DECLARED `expect: seed_dependent` and measured
    `seed_dependent` is a passing row. A subject with `expect: any` that
    measured a bad verdict is a finding. A subject that declared anything
    and measured something else is a broken claim.
    """
    if row["expect"] != "any":
        return row["verdict"] != row["expect"]
    return row["verdict"] in BAD_VERDICTS


def sweep(subjects, root=None, seeds=DEFAULT_SEEDS,
          control_runs=DEFAULT_CONTROL_RUNS, timeout=300, python=None):
    wit = perturbation_witness(seeds, python)
    rows = [probe(s, root, seeds, control_runs, timeout, python)
            for s in subjects]
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    mism = [{"id": r["id"], "expect": r["expect"], "got": r["verdict"]}
            for r in rows if is_error(r) and r["expect"] != "any"]
    k = len(seeds)
    return {"rows": rows, "counts": counts, "expectation_misses": mism,
            "perturbation": wit,
            "n_control_changed": sum(1 for r in rows
                                     if r.get("control_changed_the_verdict")),
            "power": {"n_seeds": k,
                      "miss_prob_2way": miss_probability(2, k),
                      "miss_prob_3way": miss_probability(3, k),
                      "widest_tie_under_5pct": widest_tie_bounded(k, 0.05)},
            "errors": (sum(1 for r in rows if is_error(r))
                       + (0 if wit["effective"] else 1))}


# --------------------------------------------------------------------------
# census: what COULD be a subject and is not
# --------------------------------------------------------------------------

def census(root=None, subjects=None):
    """Registry density, not membership.

    A registry of 16 subjects says nothing until you know how many
    candidates exist. A candidate is a non-vendored `*.py` under a code
    tree that has a `__main__` guard AND names a `--json` flag -- i.e. a
    file that already publishes a machine-comparable derived value.
    """
    root = root or repo_root()
    registered = set()
    for s in (subjects or []):
        for a in s["argv"]:
            if a.endswith(".py"):
                registered.add(os.path.normpath(
                    os.path.join(s.get("cwd", "."), a)))
    cands, skipped = [], 0
    for tree in ("harness", "skills", "languages", "nuc"):
        base = os.path.join(root, tree)
        for dirpath, dirnames, files in os.walk(base):
            # `.venv` was missing from the first draft of this list and
            # the census reported `pip/_vendor/distro/distro.py` as an
            # unregistered candidate of this program's. A census whose
            # denominator includes vendored code overstates the debt.
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".")
                           and d not in ("__pycache__", "research-env",
                                         "upstream", "colibri-c",
                                         "site-packages", "node_modules")]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    text = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    skipped += 1
                    continue
                if '__name__ == "__main__"' not in text:
                    continue
                if "--json" not in text:
                    continue
                cands.append(os.path.relpath(p, root))
    reg_rel = set()
    for r in registered:
        reg_rel.add(os.path.normpath(r))
    unregistered = sorted(c for c in cands
                          if os.path.normpath(c) not in reg_rel
                          and os.path.normpath(os.path.join(
                              *c.split(os.sep)[-1:])) not in
                          {os.path.basename(x) for x in reg_rel})
    # A `test_*.py` with a `__main__` guard is an entry point but not a
    # publisher of a derived value, so both numbers are reported rather
    # than one of them chosen (count-carries-its-noun-and-denominator).
    non_test = [c for c in unregistered
                if not os.path.basename(c).startswith("test_")]
    return {"n_candidates": len(cands), "n_registered_files": len(reg_rel),
            "n_unregistered": len(unregistered),
            "n_unregistered_non_test": len(non_test),
            "unregistered": unregistered, "skipped": skipped}


# --------------------------------------------------------------------------
# reachability: would this sweep have SEEN a defect it is now silent about?
# --------------------------------------------------------------------------

def reach(subject_id, commit, root=None, seeds=DEFAULT_SEEDS,
          control_runs=DEFAULT_CONTROL_RUNS, timeout=300, subjects=None):
    """Run one subject against a HISTORICAL commit and compare verdicts.

    A sweep that reports `stable` for every real subject has said one of
    two things and the report cannot tell them apart:

      * the derivations have one answer  (a fact about the tree)
      * the arm never reached them       (a fact about the instrument)

    `null-result-needs-a-power-floor` says compute the best outcome the
    instrument could have achieved before quoting the null. Here that is
    literal rather than arithmetic: check out a commit where the defect is
    known to exist, run the SAME subject through the SAME registry, and
    require the verdict to flip. `perturbation_witness` proves the seeds
    changed something inside python; this proves they change something
    inside the SUBJECT.

    The worktree is removed in a `finally` -- round 482's next-step 1,
    written after round 481's mutation loop left a mutant applied to
    `harness/wiring_audit.py` when its outer timeout fired. A harness that
    edits a checkout must restore it on every path out.
    """
    import shutil
    import tempfile
    root = root or repo_root()
    doc = {"subjects": subjects} if subjects else load_subjects()
    picked = [x for x in doc["subjects"] if x["id"] == subject_id]
    if not picked:
        raise ValueError("unknown subject id %r" % subject_id)
    subject = picked[0]

    now = probe(subject, root, seeds, control_runs, timeout)
    tmp = tempfile.mkdtemp(prefix="seedsweep-reach-")
    wt = os.path.join(tmp, "wt")
    try:
        add = subprocess.run(["git", "-C", root, "worktree", "add", "-f",
                              "--detach", wt, commit],
                             capture_output=True, text=True)
        if add.returncode != 0:
            return {"subject": subject_id, "commit": commit,
                    "verdict": "error", "detail": add.stderr[-400:]}
        then = probe(subject, wt, seeds, control_runs, timeout)
    finally:
        subprocess.run(["git", "-C", root, "worktree", "remove", "--force",
                        wt], capture_output=True, text=True)
        subprocess.run(["git", "-C", root, "worktree", "prune"],
                       capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)

    demonstrated = (then["verdict"] in ("seed_dependent",
                                        "seed_dependent_under_volatility")
                    and now["verdict"] == "stable")
    return {"subject": subject_id, "commit": commit,
            "at_head": now["verdict"], "at_commit": then["verdict"],
            "witness_at_commit": then.get("witness"),
            "n_seeds": len(seeds),
            "verdict": "demonstrated" if demonstrated else "not_demonstrated",
            "reading": ("the arm reaches this subject: the same command "
                        "through the same registry is %s at %s and %s at "
                        "HEAD, so HEAD's verdict is a fact about the tree"
                        % (then["verdict"], commit, now["verdict"]))
                       if demonstrated else
                       ("NO reachability shown: %s at %s, %s at HEAD. A "
                        "`stable` at HEAD is not licensed by this pair."
                        % (then["verdict"], commit, now["verdict"]))}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _fmt_row(r):
    tag = "FAIL" if is_error(r) else ("ok*" if r["verdict"] != "stable"
                                      else "ok")
    line = ("%-5s %-34s %-32s" % (tag, r["id"], r["verdict"]))
    if r.get("control_changed_the_verdict"):
        line += "  [naive sweep would have said %s]" % r["naive_verdict"]
    if r.get("n_masked"):
        line += "  masked=%d(%s)" % (r["n_masked"], r["mask_kind"])
    if r.get("elapsed_s") is not None:
        line += "  %.1fs" % r["elapsed_s"]
    return line


def cmd_list(args):
    doc = load_subjects(args.subjects)
    for s in doc["subjects"]:
        print("%-34s %-14s expect=%-32s %s"
              % (s["id"], s.get("owner", "-"), s["expect"],
                 " ".join(s["argv"])[:70]))
    print("%d subject(s)" % len(doc["subjects"]))
    return 0


def cmd_run(args):
    doc = load_subjects(args.subjects)
    subs = doc["subjects"]
    if args.only:
        want = set(x.strip() for x in args.only.split(",") if x.strip())
        unknown = want - set(s["id"] for s in subs)
        if unknown:
            print("seedsweep: unknown subject id(s): %s"
                  % ", ".join(sorted(unknown)), file=sys.stderr)
            return 2
        subs = [s for s in subs if s["id"] in want]
    seeds = (tuple(str(i) for i in range(1, args.seeds + 1))
             if args.seeds else DEFAULT_SEEDS)
    res = sweep(subs, root=args.root, seeds=seeds,
                control_runs=args.control_runs, timeout=args.timeout)
    if args.json:
        print(json.dumps(res, indent=1, default=str))
        return 1 if res["errors"] else 0
    for r in res["rows"]:
        print(_fmt_row(r))
        if r.get("witness"):
            print("      witness line %s: %s"
                  % (r["witness"]["line"], r["witness"]["values"]))
        if r.get("detail"):
            print("      %s" % r["detail"])
    for m in res["expectation_misses"]:
        print("EXPECT-MISS %s: registry says %s, measured %s"
              % (m["id"], m["expect"], m["got"]))
    w = res["perturbation"]
    if not w["effective"]:
        print("PERTURBATION-DEAD: %d distinct hash(str) values across %d "
              "seeds -- every `stable` below is a no-op, not a result"
              % (w["n_distinct"], w.get("n_seeds", 0)))
    p = res["power"]
    print("\n%d subject(s): %s"
          % (len(res["rows"]),
             ", ".join("%s %d" % (k, v)
                       for k, v in sorted(res["counts"].items()))))
    print("the same-seed control changed %d verdict(s) a naive cross-seed "
          "sweep would have got wrong" % res["n_control_changed"])
    print("perturbation: %d distinct hash(str) values over %d seeds (%s)"
          % (w["n_distinct"], w.get("n_seeds", 0),
             "effective" if w["effective"] else "DEAD"))
    print("power: k=%d seeds bounds a 2-way tie at miss p=%.4f, a 3-way at "
          "%.4f; ties of width >= %s are bounded under 5%%"
          % (p["n_seeds"], p["miss_prob_2way"], p["miss_prob_3way"],
             p["widest_tie_under_5pct"]))
    return 1 if res["errors"] else 0


def cmd_power(args):
    rows = []
    for n in range(2, args.max_n + 1):
        rows.append({"tie_width": n,
                     "miss_p": {k: miss_probability(n, k)
                                for k in range(2, args.max_k + 1)},
                     "k_for_1pct": min_seeds(n, 0.01)})
    if args.json:
        print(json.dumps(rows, indent=1))
        return 0
    print("%-11s %s   %s" % ("tie width", "  ".join(
        "k=%-8d" % k for k in range(2, args.max_k + 1)), "k for p<=1%"))
    for r in rows:
        print("%-11d %s   %d"
              % (r["tie_width"],
                 "  ".join("%-10.5f" % r["miss_p"][k]
                           for k in range(2, args.max_k + 1)),
                 r["k_for_1pct"]))
    return 0


def cmd_census(args):
    doc = load_subjects(args.subjects)
    res = census(args.root, doc["subjects"])
    if args.json:
        print(json.dumps(res, indent=1))
        return 0
    print("candidates (a `__main__` guard AND a `--json` flag): %d"
          % res["n_candidates"])
    print("files reached by a registered subject: %d"
          % res["n_registered_files"])
    print("unregistered: %d (%d of them not `test_*.py`)"
          % (res["n_unregistered"], res["n_unregistered_non_test"]))
    for p in res["unregistered"]:
        print("   %s" % p)
    return 0


def cmd_reach(args):
    res = reach(args.subject, args.commit, root=args.root,
                seeds=(tuple(str(i) for i in range(1, args.seeds + 1))
                       if args.seeds else DEFAULT_SEEDS),
                control_runs=args.control_runs, timeout=args.timeout)
    if args.json:
        print(json.dumps(res, indent=1, default=str))
    else:
        print("%-14s %s" % (res["verdict"].upper(), res["reading"]))
        if res.get("witness_at_commit"):
            print("   witness at %s, line %s: %s"
                  % (args.commit, res["witness_at_commit"]["line"],
                     res["witness_at_commit"]["values"]))
    return 0 if res["verdict"] == "demonstrated" else 1


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--subjects", default=None)
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd")
    li = sub.add_parser("list"); li.set_defaults(fn=cmd_list)
    ru = sub.add_parser("run")
    ru.add_argument("--only", default=None)
    ru.add_argument("--seeds", type=int, default=0,
                    help="use seeds 1..N instead of the default arm")
    ru.add_argument("--control-runs", type=int,
                    default=DEFAULT_CONTROL_RUNS)
    ru.add_argument("--timeout", type=float, default=300.0)
    ru.add_argument("--json", action="store_true")
    ru.set_defaults(fn=cmd_run)
    po = sub.add_parser("power")
    po.add_argument("--max-n", type=int, default=8)
    po.add_argument("--max-k", type=int, default=6)
    po.add_argument("--json", action="store_true")
    po.set_defaults(fn=cmd_power)
    re_ = sub.add_parser("reach")
    re_.add_argument("subject")
    re_.add_argument("commit")
    re_.add_argument("--seeds", type=int, default=0)
    re_.add_argument("--control-runs", type=int,
                     default=DEFAULT_CONTROL_RUNS)
    re_.add_argument("--timeout", type=float, default=300.0)
    re_.add_argument("--json", action="store_true")
    re_.set_defaults(fn=cmd_reach)
    ce = sub.add_parser("census")
    ce.add_argument("--json", action="store_true")
    ce.set_defaults(fn=cmd_census)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not getattr(args, "fn", None):
        build_parser().print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

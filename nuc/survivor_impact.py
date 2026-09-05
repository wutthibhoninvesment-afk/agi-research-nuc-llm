"""Round 502 (NUC-integration E): what a SURVIVING mutant costs the record.

`state/swe/perturbation-mutation-ledger.jsonl` says 32 of the 87 mutants
scored so far in `nuc/perturbation.py` SURVIVED -- the suite is green with the
mutation in place. Rounds 491 and 497 (SWE-loop D) read that as one number, a
kill rate, and one diagnosis: a test-shape gap, thresholds never probed on
their own boundary.

That is the right question for a test suite and the wrong one for this track.
`nuc/perturbation.py` is not a library with users; it is the instrument every
window-level number NUC-integration(E) has published since round 388 is
computed by. So the question this module asks is not "does a test notice?" but:

    does this survivor CHANGE A NUMBER THIS TRACK HAS PUBLISHED,
    when the published derivation is re-run on the real record?

The three answers are not the same finding and must not be pooled:

  `moves_published_number`
      The suite is green AND the record can see it. A figure in a knowledge
      file depends on a line no test pins. This is the only class that is a
      defect in the sense the program cares about.

  `reached_but_identical`
      The mutated line RUNS during a published derivation and every output is
      byte-identical. Equivalent on this record. Killable only by a test that
      asserts something no published number depends on.

  `unreached_by_battery`
      The line never executes at all while the published derivations run, so
      no test written against the real record could ever kill it. That is a
      fact about the RECORD (or about dead code), not about the suite, and the
      three sub-reasons are DIFFERENT facts, reported separately:
        `orphan_function`     -- nothing in the module ever calls the
                                 enclosing function. Only the test file does.
        `function_not_entered`-- it has callers, but no verb in the battery
                                 reaches it. See `BATTERY_GAP`: this is a
                                 limit of the battery, not of the record.
        `branch_not_taken`    -- the battery DID enter the function; this
                                 line did not run, on the shape this record
                                 has. The only one of the three that is
                                 evidence about the box.

The battery is the module's OWN published verbs, run as subprocesses exactly
as a round runs them, against `state/nuc-record-union` (round 490: never build
a view from one capture again without saying why). Reachedness is measured
with `sys.settrace` over the same argv, in process, which resolves individual
lines of a multi-line expression -- the resolution this subject needs, because
twelve of the survivors live inside one four-line f-string.

NO NETWORK, NO SSH, NO ENGINE. Offline, on committed files.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEFAULT_LEDGER = os.path.join("state", "swe", "perturbation-mutation-ledger.jsonl")
DEFAULT_SUBJECT = os.path.join("nuc", "perturbation.py")
#: Round 490's item 1: the union, not a capture. A capture is a WINDOW.
DEFAULT_CAPTURE = os.path.join("state", "nuc-record-union")

#: The published derivations. Each entry is (name, argv-after-the-script).
#: `{capture}` is substituted. These are the verbs this track's knowledge
#: files quote: `window` is the whole
#: `cost_ledger -> attribution_evidence -> power_floor -> verdict_floor` chain
#: (rounds 430, 472, 478, 484, 490) and `wsweep` re-runs the gates at every
#: costly threshold (round 412's "a verdict that is really a setting").
BATTERY = (
    ("window_swap", ["window", "--capture", "{capture}", "--strict"]),
    ("wsweep_swap", ["wsweep", "--capture", "{capture}"]),
    ("wsweep_commit", ["wsweep", "--capture", "{capture}", "--channel", "commit"]),
    ("wsweep_steal", ["wsweep", "--capture", "{capture}", "--channel", "steal"]),
    ("population_swap", ["population", "--capture", "{capture}"]),
)

#: Verbs deliberately NOT in the battery, and why -- because a survivor the
#: battery never reaches must not be reported as if the record had been asked.
#: Measured on `state/nuc-record-union` at round 502:
#:   `window --channel commit|steal` -> rc 1, "no derived costly-threshold on
#:       this record"; only `swap` has one, so `wsweep` carries the other two.
#:   `reclaim`/`gap` take a SINGLE sar table (`--sar-b`), and the union's
#:       `sar-all.txt` is 120 sections: rc 1, "header changed mid-table". Two
#:       of this module's published verbs cannot read round 490's union at all.
#:   `oom`/`stability`/`engine`/`place` need a user/engine journal the union
#:       does not carry; `exclusion` draws random shifts and is not
#:       byte-reproducible, which an output-digest oracle requires.
BATTERY_GAP = {
    "window_commit": "rc 1 on this record: no derived costly-threshold",
    "window_steal": "rc 1 on this record: no derived costly-threshold",
    "reclaim": "needs one sar table; the union's sar-all.txt is 120 sections",
    "gap": "needs one sar table; the union's sar-all.txt is 120 sections",
    "oom": "needs a journal the union does not carry",
    "stability": "needs an engine journal the union does not carry",
    "engine": "needs an engine journal the union does not carry",
    "place": "needs an engine journal the union does not carry",
    "exclusion": "randomised; not byte-reproducible, so not an output oracle",
}


class ImpactError(RuntimeError):
    pass


# ------------------------------------------------------------------ ledger

def survivors(ledger_path: str, subject_digest: str | None = None) -> list:
    """Ledger rows that currently stand as `survived`, LAST WINS.

    `nodecampaign.load_ledger` keys on `(id, subject_digest)` and later rows
    overwrite earlier ones, so a re-score appends rather than edits. Reading
    the file any other way would report a verdict the campaign itself no
    longer holds.
    """
    if not os.path.exists(ledger_path):
        raise ImpactError("no ledger at %s" % ledger_path)
    latest: dict = {}
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            latest[(r["id"], r.get("subject_digest"))] = r
    out = [r for r in latest.values() if r.get("status") == "survived"]
    if subject_digest is not None:
        out = [r for r in out if r.get("subject_digest") == subject_digest]
    return sorted(out, key=lambda r: (r["line"], r["id"]))


def file_digest(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# --------------------------------------------------------------- structure

def enclosing_defs(source: str) -> list:
    """`[(first_line, last_line, qualname)]` for every def/class, innermost
    last. Used to name what a mutated line belongs to."""
    tree = ast.parse(source)
    out = []

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                name = prefix + child.name
                lo = min([child.lineno] + [d.lineno for d in child.decorator_list])
                out.append((lo, child.end_lineno, name))
                walk(child, name + ".")
            else:
                walk(child, prefix)

    walk(tree, "")
    return sorted(out)


def span_of(defs: list, lineno: int) -> tuple | None:
    """`(first_line, last_line)` of the innermost def/class containing
    `lineno`. Used to ask whether the battery ever ENTERED the function, which
    separates "this branch did not run" from "nothing ran here at all"."""
    best = None
    for lo, hi, _ in defs:
        if lo <= lineno <= hi:
            if best is None or (hi - lo) < (best[1] - best[0]):
                best = (lo, hi)
    return best


def owner_of(defs: list, lineno: int) -> str | None:
    """Innermost def/class containing `lineno`, or None (module level)."""
    best = None
    for lo, hi, name in defs:
        if lo <= lineno <= hi:
            if best is None or (hi - lo) < (best[1] - best[0]):
                best = (lo, hi, name)
    return best[2] if best else None


def called_names(source: str) -> set:
    """Every NAME that appears in call position anywhere in the module.

    Deliberately name-based and not scope-aware: it is used only to answer
    "does anything in this file ever call X", and a false POSITIVE is the safe
    direction -- it would make this module claim a function is live when it is
    not, i.e. it can never manufacture an `orphan_function` verdict.
    """
    tree = ast.parse(source)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


# ---------------------------------------------------------------- battery

def _argv(entry_argv: list, capture: str) -> list:
    return [a.format(capture=capture) for a in entry_argv]


def run_battery(module_path: str, capture: str, root: str = ROOT,
                python: str | None = None, timeout_s: float = 300.0) -> dict:
    """Run every published derivation against `module_path`, as a subprocess.

    A subprocess, not an import, because that is exactly how a round runs
    these verbs -- and because a mutant that breaks module import must be
    seen as a difference rather than as a crash in this process.
    """
    python = python or sys.executable
    out = {}
    for name, argv in BATTERY:
        cmd = [python, module_path] + _argv(argv, capture)
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                           timeout=timeout_s)
        out[name] = {
            "rc": p.returncode,
            "stdout_sha256": hashlib.sha256(p.stdout.encode()).hexdigest(),
            "stdout_bytes": len(p.stdout),
            "stdout": p.stdout,
            "stderr_tail": p.stderr.strip().splitlines()[-1:] or [],
        }
    return out


def make_sandbox(subject: str, tmp: str) -> str:
    """A directory in which the mutant is `perturbation.py` and every SIBLING
    module is still importable.

    Round 502 built the first version without this and every one of the 32
    mutants came back `moves_published_number` -- a perfect, and perfectly
    false, headline. `nuc/perturbation.py` imports `swap_analysis` at run time,
    so a mutant alone in a temp directory dies with `ModuleNotFoundError`
    before it reaches a single line of the record, and an output-digest oracle
    reads that as "the number moved". Symlinks, not copies: the siblings are
    read-only here and the sandbox is per-run, and a link costs nothing.
    """
    src_dir = os.path.dirname(os.path.abspath(subject))
    base = os.path.basename(subject)
    for name in os.listdir(src_dir):
        if name == base or name == "__pycache__":
            continue
        dst = os.path.join(tmp, name)
        if not os.path.exists(dst):
            os.symlink(os.path.join(src_dir, name), dst)
    return os.path.join(tmp, base)


def battery_diff(base: dict, other: dict) -> list:
    """Names of the battery entries whose result changed, with a witness.

    The witness is the FIRST differing line of stdout, so the report says what
    moved rather than only that something did.
    """
    diffs = []
    for name, _ in BATTERY:
        b, o = base.get(name), other.get(name)
        if b is None or o is None:
            diffs.append({"battery": name, "kind": "missing"})
            continue
        if b["rc"] != o["rc"]:
            diffs.append({"battery": name, "kind": "returncode",
                          "before": b["rc"], "after": o["rc"],
                          "stderr_after": o["stderr_tail"]})
            continue
        if b["stdout_sha256"] != o["stdout_sha256"]:
            bl, ol = b["stdout"].splitlines(), o["stdout"].splitlines()
            first = None
            for i in range(max(len(bl), len(ol))):
                x = bl[i] if i < len(bl) else "<eof>"
                y = ol[i] if i < len(ol) else "<eof>"
                if x != y:
                    first = {"line_no": i + 1, "before": x.strip()[:200],
                             "after": y.strip()[:200]}
                    break
            diffs.append({"battery": name, "kind": "stdout", "first_diff": first})
    return diffs


# --------------------------------------------------------------- reach

def trace_battery(module_path: str, capture: str, root: str = ROOT) -> set:
    """Line numbers of `module_path` executed while the battery runs.

    In process and with `sys.settrace`, which reports a `line` event per
    sub-line of a multi-line expression on CPython 3.12 -- the resolution this
    subject needs, because twelve survivors sit inside one four-line f-string
    and a statement-granular tracer would call all four of them "executed"
    whichever branch ran.
    """
    import importlib.util

    target = os.path.abspath(module_path)
    spec = importlib.util.spec_from_file_location(
        "_impact_probe_%s" % hashlib.sha1(target.encode()).hexdigest()[:10], target)
    mod = importlib.util.module_from_spec(spec)
    # `sys.modules` FIRST: `@dataclass` resolves its own annotations through
    # `sys.modules[cls.__module__]`, so a module executed outside the import
    # system raises `AttributeError: 'NoneType' object has no attribute
    # '__dict__'` on the first frozen dataclass. Found by running it.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    seen: set = set()

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != target:
            return None
        if event == "line":
            seen.add(frame.f_lineno)
        return tracer

    cwd = os.getcwd()
    os.chdir(root)
    try:
        for _, argv in BATTERY:
            a = _argv(argv, capture)
            sys.settrace(tracer)
            try:
                mod.main(a)
            except SystemExit:
                pass
            finally:
                sys.settrace(None)
    finally:
        os.chdir(cwd)
    return seen


# ---------------------------------------------------------------- audit

def audit(root: str = ROOT, rel: str = DEFAULT_SUBJECT,
          ledger: str = DEFAULT_LEDGER, capture: str = DEFAULT_CAPTURE,
          only_ids: list | None = None, python: str | None = None) -> dict:
    """Classify every standing survivor by what it costs the published record."""
    subject = os.path.join(root, rel)
    digest = file_digest(subject)
    with open(subject, encoding="utf-8") as fh:
        source = fh.read()
    defs = enclosing_defs(source)
    calls = called_names(source)

    rows = survivors(os.path.join(root, ledger), subject_digest=digest)
    stale_digest = [r["id"] for r in survivors(os.path.join(root, ledger))
                    if r.get("subject_digest") != digest]
    if only_ids:
        want = set(only_ids)
        rows = [r for r in rows if r["id"] in want]

    # `mutation` is only importable from the repo root's package layout.
    sys.path.insert(0, root)
    from harness.swe import mutation as MU

    mutants = {m.id: m for m in MU.generate(source, os.path.basename(rel))}

    base_out = run_battery(subject, capture, root=root, python=python)
    reached = trace_battery(subject, capture, root=root)

    tmp = tempfile.mkdtemp(prefix="survivor-impact-")
    results = []
    try:
        mpath = make_sandbox(subject, tmp)
        # THE CONTROL, and it is not optional. Copy the subject UNMUTATED into
        # the sandbox and demand the battery reproduce the baseline exactly.
        # If it does not, every later verdict is measuring the sandbox rather
        # than the mutation -- which is precisely what happened on this
        # module's first run.
        with open(mpath, "w", encoding="utf-8") as fh:
            fh.write(source)
        control = battery_diff(base_out, run_battery(mpath, capture, root=root,
                                                     python=python))
        if control:
            raise ImpactError(
                "sandbox control FAILED: an unmutated copy does not reproduce "
                "the baseline (%s). Every verdict below would be a measurement "
                "of the sandbox." % json.dumps(control)[:400])
        for r in rows:
            m = mutants.get(r["id"])
            if m is None:
                results.append({"id": r["id"], "line": r["line"],
                                "verdict": "not_generated_at_this_digest"})
                continue
            with open(mpath, "w", encoding="utf-8") as fh:
                fh.write(m.source)
            diffs = battery_diff(base_out,
                                 run_battery(mpath, capture, root=root,
                                             python=python))
            owner = owner_of(defs, m.lineno)
            top = owner.split(".")[0] if owner else None
            orphan = bool(top) and top not in calls
            span = span_of(defs, m.lineno)
            entered = bool(span and any(lo <= x <= hi
                                        for x in reached for lo, hi in [span]))
            if diffs:
                verdict, why = "moves_published_number", None
            elif m.lineno not in reached:
                verdict = "unreached_by_battery"
                # Three different facts, and pooling them would be the whole
                # error this module exists to avoid.
                why = ("orphan_function" if orphan
                       else "branch_not_taken" if entered
                       else "function_not_entered")
            else:
                verdict, why = "reached_but_identical", None
            results.append({
                "id": m.id, "line": m.lineno, "op": m.op,
                "description": m.description, "owner": owner,
                "verdict": verdict, "reason": why,
                "line_executed_by_battery": m.lineno in reached,
                "enclosing_function_called_in_module": (None if not top
                                                        else top in calls),
                "diffs": diffs,
            })
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    by = {}
    for r in results:
        by[r["verdict"]] = by.get(r["verdict"], 0) + 1
    return {
        "subject": rel,
        "subject_digest": digest,
        "capture": capture,
        "battery": [n for n, _ in BATTERY],
        "battery_gap": dict(BATTERY_GAP),
        "n_survivors_standing": len(rows),
        "n_survivors_at_another_digest": len(stale_digest),
        "survivors_at_another_digest": sorted(stale_digest),
        "n_lines_executed_by_battery": len(reached),
        "control_identity_clean": True,
        "by_verdict": by,
        "moves_published_number": sorted(
            r["id"] for r in results if r["verdict"] == "moves_published_number"),
        "by_reason": _tally(r.get("reason") for r in results),
        "results": results,
    }


def _tally(items) -> dict:
    out: dict = {}
    for x in items:
        if x is None:
            continue
        out[x] = out.get(x, 0) + 1
    return dict(sorted(out.items()))


def strict_fails(rep: dict) -> list:
    """Why `--strict` exits 1. Round 490's rule: a gate that passes on an
    input it never read is worse than one that fails, so an empty audit is a
    FAILURE, not a pass."""
    bad = []
    if rep["n_survivors_standing"] == 0:
        bad.append("no standing survivors were audited at this subject digest")
    if not rep.get("control_identity_clean"):
        bad.append("the unmutated sandbox control did not reproduce the baseline")
    if not rep["n_lines_executed_by_battery"]:
        bad.append("the battery executed no line of the subject at all")
    for mid in rep["moves_published_number"]:
        bad.append("%s survives the suite AND moves a published number" % mid)
    return bad


def build_parser():
    p = argparse.ArgumentParser(
        prog="survivor_impact.py",
        description="Does a surviving mutant change a number this track has "
                    "published?")
    p.add_argument("--root", default=ROOT)
    p.add_argument("--rel", default=DEFAULT_SUBJECT)
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.add_argument("--capture", default=DEFAULT_CAPTURE)
    p.add_argument("--only", default=None,
                   help="comma-separated mutant ids to audit instead of every "
                        "standing survivor")
    p.add_argument("--out", default=None)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    only = [s.strip() for s in a.only.split(",")] if a.only else None
    rep = audit(root=os.path.abspath(a.root), rel=a.rel, ledger=a.ledger,
                capture=a.capture, only_ids=only)
    text = json.dumps(rep, indent=1, sort_keys=True)
    if a.out:
        d = os.path.dirname(os.path.join(a.root, a.out))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(a.root, a.out), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if not a.quiet:
        print(text)
    if a.strict:
        bad = strict_fails(rep)
        for b in bad:
            print("STRICT: %s" % b, file=sys.stderr)
        return 1 if bad else 0
    return 0


if __name__ == "__main__":                     # pragma: no cover
    raise SystemExit(main())

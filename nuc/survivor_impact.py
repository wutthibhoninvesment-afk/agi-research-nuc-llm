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
#: ROUND 508: every entry names its channel EXPLICITLY, and the reason is a
#: measured defect, not tidiness. `wsweep`'s `--channel` defaults to `steal`
#: -- alone among the twelve `perturbation.py` subcommands that take one, ten
#: of which default to `swap` -- so the entry written as
#: `["wsweep", "--capture", "{capture}"]` and NAMED `wsweep_swap` ran the
#: STEAL channel. Its output was byte-identical to `wsweep_steal`'s, 35 703
#: bytes and md5 31b8b34f8e9d, on `state/nuc-record-union`. The battery
#: advertised five published verbs and ran four, with one channel counted
#: twice and the swap channel -- the only one with a derived threshold, and
#: the one every published number in this track uses -- never run at all.
#: `test_no_two_battery_entries_are_the_same_command` is the falsifier.
BATTERY = (
    ("window_swap", ["window", "--capture", "{capture}", "--channel", "swap",
                     "--strict"]),
    ("wsweep_swap", ["wsweep", "--capture", "{capture}", "--channel", "swap"]),
    ("wsweep_commit", ["wsweep", "--capture", "{capture}", "--channel", "commit"]),
    ("wsweep_steal", ["wsweep", "--capture", "{capture}", "--channel", "steal"]),
    ("population_swap", ["population", "--capture", "{capture}",
                         "--channel", "swap"]),
    ("reclaim_all", ["reclaim", "--capture", "{capture}"]),
    ("gap_commit", ["gap", "--capture", "{capture}", "--channel", "commit"]),
)

#: Verbs deliberately NOT in the battery, and why -- because a survivor the
#: battery never reaches must not be reported as if the record had been asked.
#: Measured on `state/nuc-record-union` at round 502:
#:   `window --channel commit|steal` -> rc 1. ROUND 508 CORRECTED THE SUBJECT:
#:       this is NOT a fact about the record. `CHANNEL_MIN_BYTES` is a module
#:       constant with `None` for both channels and the raise never reads the
#:       record at all, so no record can satisfy it; `window --channel commit
#:       --min-bytes 4825718` exits 0 on this very union. The entries stay --
#:       a threshold nobody derived must not be quoted as if somebody had --
#:       but they are a DESIGN REFUSAL plus an unpassed flag, and `wsweep`
#:       (which sweeps thresholds) is the right verb for those channels.
#:   `reclaim`/`gap` USED to take a SINGLE hand-extracted sar table only, and
#:       round 502 recorded their failure as a property of the union ("120
#:       sections"). ROUND 508 MEASURED IT: the identical `header changed
#:       mid-table` raise comes from `nuc-capture-r424`, r400, r478 and r484
#:       as well -- 0 of 5 records in this repo could be fed to them. It was
#:       never about the union. Both now take `--capture` and are IN the
#:       battery above.
#:   `oom`/`stability`/`engine`/`place` need a user/engine journal the union
#:       does not carry; `exclusion` draws random shifts and is not
#:       byte-reproducible, which an output-digest oracle requires.
BATTERY_GAP = {
    "window_commit": "rc 1: CHANNEL_MIN_BYTES['commit'] is None -- a module "
                     "constant, not a property of any record; wsweep sweeps it",
    "window_steal": "rc 1: CHANNEL_MIN_BYTES['steal'] is None -- a module "
                    "constant, not a property of any record; wsweep sweeps it",
    "oom": "needs a journal the union does not carry",
    "stability": "needs an engine journal the union does not carry",
    "engine": "needs an engine journal the union does not carry",
    "place": "needs an engine journal the union does not carry",
    "exclusion": "randomised; not byte-reproducible, so not an output oracle",
}


#: ROUND 526 (NUC-integration E) -- MUTANTS NO TEST CAN KILL, AND THE PROOF.
#:
#: Every verdict above is a fact about THIS BATTERY on THIS RECORD.
#: `unreached_by_battery/branch_not_taken` is documented above as "the only
#: one of the three that is evidence about the box" -- and round 520 spent it
#: on two mutants that are evidence about nothing but arithmetic. They live in
#: the third arm of `power_floor`'s `why` f-string, the arm that fires when
#: the testable set is NOT contiguous, and `best_case_p(N, K, .)` is
#: quasiconvex in `d`, so its sublevel set is an interval and that arm cannot
#: run on ANY record, on any box, ever. A reader of round 520's report would
#: have concluded the box's record happens not to produce a non-contiguous
#: set. No record can.
#:
#: So the report gains a class it did not have, with three rules that keep it
#: from becoming a place to hide survivors:
#:
#:   1. Every entry CITES a test nodeid that proves the claim. `--verify-proofs`
#:      runs them; `test_every_proven_entry_cites_a_test_that_exists` collects
#:      them on every suite run. A claim with no runnable proof is not one.
#:   2. Every entry names the `subject_digest` it was proved at. A mutant id is
#:      only meaningful at the digest that generated it (round 520's finding
#:      about stale rows, applied to this registry): at any other digest the
#:      entry is reported as `proven_at_another_digest` and grades NOTHING.
#:   3. A `moves_published_number` verdict OVERRIDES the registry and is a
#:      `--strict` failure. If the battery kills a mutant the registry calls
#:      unkillable, the registry is wrong and must say so loudly.
#:
#: `equivalent` = the mutated program computes the same value for every legal
#: input. `unreachable` = no legal input executes the mutated line at all.
_SUBJECT_3B39 = ("3b3923df3ee72b3f98f5bdda828a82d94b8b9971848f458d7741f4e64"
                 "4324b8c")
_T_PERT = "nuc/tests/test_perturbation.py"

PROVEN = {
    "perturbation.py:1586:cmp#162": {
        "class": "provably_equivalent",
        "subject_digest": _SUBJECT_3B39,
        "proof": _T_PERT + "::test_the_zero_hit_guard_is_a_fast_path_and_not_a_branch",
        "why": "`_hypergeom_atleast` raises on `h < 0` one line earlier, so "
               "`h <= 0` and `h < 0` differ only at `h == 0`, where the "
               "fall-through sums Vandermonde's identity over the full range "
               "and returns exactly 1.0 -- the same float, no rounding. "
               "Verified over all 10416 legal (N, K, n) with N <= 30.",
    },
    "perturbation.py:1660:const#1547": {
        "class": "provably_unreachable",
        "subject_digest": _SUBJECT_3B39,
        "proof": _T_PERT + "::test_the_testable_set_is_always_contiguous_so_the_third_why_arm_is_dead",
        "why": "`testable[0]` -> `testable[1]` in the third arm of "
               "`power_floor`'s `why` f-string. `best_case_p(N, K, .)` is "
               "quasiconvex in `d`, so the testable set is a sublevel set of "
               "a quasiconvex function, i.e. an interval; the non-contiguous "
               "arm cannot run on any record. 37800 record shapes swept, 0 "
               "non-contiguous.",
    },
    "perturbation.py:1661:const#1601": {
        "class": "provably_unreachable",
        "subject_digest": _SUBJECT_3B39,
        "proof": _T_PERT + "::test_the_testable_set_is_always_contiguous_so_the_third_why_arm_is_dead",
        "why": "`testable[-1]` -> `testable[-2]`, same dead arm, same proof "
               "as `1660:const#1547`.",
    },
}

PROVEN_CLASSES = ("provably_equivalent", "provably_unreachable")


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

            # ROUND 526 -- the fourth question, and it is not about the
            # battery: could ANY input kill this mutant? The verdicts above
            # cannot answer it, because every one of them is measured by
            # running this battery on this record. A cited proof can.
            raw_verdict = verdict
            entry, pstatus = proof_for(m.id, digest)
            row = {
                "id": m.id, "line": m.lineno, "op": m.op,
                "description": m.description, "owner": owner,
                "verdict": verdict, "reason": why,
                "raw_verdict": raw_verdict,
                "line_executed_by_battery": m.lineno in reached,
                "enclosing_function_called_in_module": (None if not top
                                                        else top in calls),
                "diffs": diffs,
                "proven": None, "proof": None, "proof_status": pstatus,
            }
            if pstatus == "at_this_digest":
                if raw_verdict == "moves_published_number":
                    # The registry says nothing can kill it and the battery
                    # just did. The MEASUREMENT wins; the registry is wrong
                    # and `--strict` says so.
                    row["proven_contradicted"] = True
                else:
                    row["verdict"] = entry["class"]
                    row["proven"] = entry["class"]
                    row["proof"] = entry["proof"]
                    row["proof_why"] = entry["why"]
            results.append(row)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    by = {}
    for r in results:
        by[r["verdict"]] = by.get(r["verdict"], 0) + 1
    n_proven = sum(1 for r in results if r.get("proven"))
    proven_here = {mid for mid, e in PROVEN.items()
                   if e.get("subject_digest") == digest}
    proven_elsewhere = set(PROVEN) - proven_here
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
        "by_raw_verdict": _tally(r.get("raw_verdict") for r in results),
        "moves_published_number": sorted(
            r["id"] for r in results if r["verdict"] == "moves_published_number"),
        "by_reason": _tally(r.get("reason") for r in results),
        # ROUND 526 -- the headline number, decomposed. `n_survivors_standing`
        # pooled two populations: survivors a test could still kill, and
        # survivors no test will ever kill. Reporting only the total invites
        # the reader to price them the same.
        "n_survivors_provably_dead": n_proven,
        "n_survivors_unexplained": len(rows) - n_proven,
        "proven_registry": {
            "n_entries": len(PROVEN),
            "n_at_this_digest": len(proven_here),
            "n_at_another_digest": len(proven_elsewhere),
            "ids_at_another_digest": sorted(proven_elsewhere),
            "n_applied": n_proven,
            "unused_at_this_digest": sorted(
                proven_here - {r["id"] for r in results}),
            "contradicted": sorted(r["id"] for r in results
                                   if r.get("proven_contradicted")),
        },
        "audited_full_population": only_ids is None,
        "results": results,
    }


def proof_for(mid: str, digest: str) -> tuple:
    """ROUND 526. `(entry, status)` for a mutant id against the CURRENT digest.

    `status` is one of `None` (no registry entry), `"at_this_digest"` (the
    entry governs) or `"at_another_digest"` (an entry exists but was proved
    against a different subject; a mutant id only means anything at the digest
    that generated it, so it governs NOTHING here).
    """
    entry = PROVEN.get(mid)
    if entry is None:
        return None, None
    if entry.get("subject_digest") != digest:
        return entry, "at_another_digest"
    return entry, "at_this_digest"


def verify_proofs(root: str, digest: str | None = None,
                  python: str | None = None, timeout_s: int = 600) -> dict:
    """ROUND 526. RUN the tests the PROVEN registry cites, and report.

    A citation nobody executes is a comment. This runs the distinct nodeids in
    one pytest invocation and returns the verdict per nodeid; `--strict` fails
    unless every cited proof passes. Entries proved at another digest are
    reported and NOT run, because they grade nothing at this one.
    """
    entries = {mid: e for mid, e in PROVEN.items()
               if digest is None or e.get("subject_digest") == digest}
    nodeids = sorted({e["proof"] for e in entries.values()})
    out = {"n_entries_checked": len(entries), "nodeids": nodeids,
           "skipped_at_another_digest": sorted(set(PROVEN) - set(entries))}
    if not nodeids:
        out["ok"] = False
        out["note"] = "no proof was run: the registry cites nothing at this digest"
        return out
    cmd = [python or sys.executable, "-m", "pytest", "-q", "--no-header",
           "-p", "no:cacheprovider", *nodeids]
    try:
        pr = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                            timeout=timeout_s)
    except subprocess.TimeoutExpired:
        out["ok"] = False
        out["note"] = "pytest timed out after %ds" % timeout_s
        return out
    out["returncode"] = pr.returncode
    out["tail"] = (pr.stdout or "").strip().splitlines()[-1:] or [""]
    out["ok"] = pr.returncode == 0
    return out


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
    # ROUND 526 -- three ways the PROVEN registry can be wrong, all loud.
    reg = rep.get("proven_registry") or {}
    for mid in reg.get("contradicted", []):
        bad.append("%s is in PROVEN as unkillable and the battery KILLED it: "
                   "the registry entry is false" % mid)
    for mid in reg.get("ids_at_another_digest", []):
        bad.append("PROVEN entry %s was proved at a different subject digest "
                   "and grades nothing here; re-prove it or drop it" % mid)
    pv = rep.get("proof_verification")
    if pv is not None and not pv.get("ok"):
        bad.append("the PROVEN registry's cited tests did not pass: %s"
                   % json.dumps({k: pv.get(k) for k in ("returncode", "tail",
                                                        "note")}))
    if rep.get("audited_full_population"):
        for mid in reg.get("unused_at_this_digest", []):
            bad.append("PROVEN entry %s names a mutant that is not a standing "
                       "survivor at this digest" % mid)
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
    p.add_argument("--verify-proofs", action="store_true",
                   help="round 526: RUN the tests the PROVEN registry cites, "
                        "and fail --strict unless every one passes")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    only = [s.strip() for s in a.only.split(",")] if a.only else None
    rep = audit(root=os.path.abspath(a.root), rel=a.rel, ledger=a.ledger,
                capture=a.capture, only_ids=only)
    if a.verify_proofs:
        rep["proof_verification"] = verify_proofs(
            os.path.abspath(a.root), digest=rep["subject_digest"])
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

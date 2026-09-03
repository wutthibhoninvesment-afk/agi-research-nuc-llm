"""Per-TEST falsification audit: which of these tests could ever go red?

    python3 harness/swe/falsifiers.py audit \
        --subject harness/swe/scoreaudit.py \
        --tests harness/tests/test_swe_scoreaudit.py --json out.json

WHY THIS EXISTS
---------------
`swe/mutation.py` answers a question about the CODE: how many small semantic
slips does the suite notice? Its unit of account is the mutant, and its
output is a mutation score plus a survivor list. That is the right question
when you are hunting test GAPS.

Round 472 asked the mirror question and this repo could not answer it. It
mutation-tested its own 49 new tests and found **3 of 10 mutations survived
— three tests that could not have gone red for ANY code change**, one of
them guarding a published p-value. A mutation score cannot say that. A
survivor tells you a line of the subject is unguarded; it does not tell you
which of your test nodes is a no-op. Those are different defects with
different repairs:

    survivor   -> the subject has behaviour nothing asserts   (write a test)
    never_red  -> the TEST has no assertion that depends on it (fix the test)

and a suite can be full of the second while scoring well on the first,
because one thorough test node can kill every mutant its file's other
twenty nodes were supposed to cover.

HOW IT WORKS
------------
The campaign `mutation.py` already runs is re-used verbatim — same
`generate`, same `_copy_project`, same `classify_mutant_run` exit-code
table — with ONE addition: every MUTANT run gets its own `--junitxml`, not
just the baseline. `mutation.baseline_check` has passed `--junitxml` to the
unmutated run since round 431; no mutant run in this repo has ever produced
one, so no kill has ever been attributed to the test that made it.

With per-mutant junit we get, for each mutant, the SET of test nodes that
went red. Union those sets over the campaign and you have, per test node,
the number of mutants it killed. Nodes at zero are `never_red`.

THE CLAIM THIS MAKES, AND THE THREE WAYS IT IS BOUNDED
------------------------------------------------------
`never_red` does NOT mean "vacuous". It means exactly:

    this node did not fail for any mutant of the subject files it was
    audited against, in this campaign

which is why `FalsifierUnit` carries its `subject_paths` into the report and
why the summary prints them next to the verdict. Three bounds, all reported
rather than assumed away:

  1. SCOPE. A node about a different module cannot go red here and is not a
     defect. Pair the subject with the test file that claims to be about it,
     and hand-triage the residue. `never_red` is a WORK LIST, not a verdict.
  2. ATTRIBUTION COVERAGE. A killed mutant with no readable junit (a
     timeout, a crashed interpreter) proves some node went red and hides
     which. Such kills are counted in `unattributed_kills`, and `sound` is
     False whenever there are any. A `never_red` list from an unsound
     campaign is an upper bound on the real one, never the real one.
  3. EQUIVALENT MUTANTS. Unchanged from `mutation.py`: a mutant with no
     behavioural difference is unkillable, and inflates nothing here
     (it simply attributes no kill to anyone).

`limit` IS HEAD-BIASED AND `sample` EXISTS BECAUSE OF IT
--------------------------------------------------------
`mutation_test(limit=N)` takes `mutants[:N]` — the first N mutation sites in
SOURCE ORDER, which for every module in this tree means the imports, the
module constants and the first one or two functions. A budget-limited
campaign run that way audits the top of the file and reports its score as
the module's. `--sample N` selects an evenly-spaced stride across the whole
site list instead, so a bounded campaign is bounded uniformly. Both are
recorded in the report (`selection`), because a score over a sample and a
score over a module are different numbers.
"""

import ast
import json
import os
import shutil
import sys
import tempfile
import time

try:                                     # imported as `swe.falsifiers`
    from . import mutation
    from . import sandboxevidence as SE
    from .proc import AGI_RESEARCH_ROOT, run_capped
except ImportError:                      # run as `python3 harness/swe/falsifiers.py`
    # `swe/*.py` use intra-package relative imports throughout, so the flat
    # `import mutation` fallback `mutation.py` itself uses cannot work here:
    # it re-enters the same failure one level down. Put `harness/` on the
    # path and import the PACKAGE instead.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from swe import mutation                                 # noqa: F401
    from swe import sandboxevidence as SE                     # noqa: F401
    from swe.proc import AGI_RESEARCH_ROOT, run_capped        # noqa: F401

if AGI_RESEARCH_ROOT not in sys.path:
    sys.path.insert(0, AGI_RESEARCH_ROOT)

from harness.pristine_check import parse_junit  # noqa: E402

#: junit statuses that mean "this node went red for this mutant".
RED = frozenset({"failed", "error"})

#: Verdicts, in precedence order. `unsound` outranks everything: a campaign
#: that lost attribution cannot support a `never_red` claim at all, and
#: saying so is not the same as saying every node was exercised.
V_UNSOUND = "unsound"
V_NO_KILLS = "no_kills"
V_NEVER_RED = "never_red"
V_ALL_FALSIFIABLE = "all_falsifiable"


def function_ranges(source):
    """`{qualname: (first_line, last_line)}` for every def/class in `source`.

    Nested and method scopes get dotted names (`Class.method`,
    `outer.inner`). Used by `--func` to bound a campaign to the functions
    that produce a published number instead of a whole 1000-line module.
    """
    out = {}

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                out[name] = (start, getattr(child, "end_lineno", child.lineno))
                walk(child, name + ".")
            else:
                walk(child, prefix)

    walk(ast.parse(source), "")
    return out


def main_guard_spans(source):
    """`[(first_line, last_line)]` for every `if __name__ == "__main__":`.

    Found by the smoke run of this module's very first campaign, and it is a
    standing tax on every campaign this repo has ever run. `mutation.generate`
    offers TWO sites inside that guard — `ifneg` on the `If` and `cmp`
    (`Eq -> NotEq`) on the comparison — and each one makes the module invoke
    its own CLI at IMPORT time. Under pytest that is a collection-time
    `SystemExit` or an `argparse` usage exit, i.e. exit code 3/4: no evidence
    either way post-round-349, and a FREE KILL before it. 221 modules in this
    repo carry the guard.

    Excluded by default and counted in `selection["main_guard_excluded"]`
    rather than dropped silently, because "the campaign generated 77 sites"
    and "the campaign ran 75" are different statements about the same module.
    """
    spans = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if (isinstance(t, ast.Compare) and len(t.ops) == 1
                and isinstance(t.ops[0], ast.Eq)
                and isinstance(t.left, ast.Name) and t.left.id == "__name__"
                and len(t.comparators) == 1
                and isinstance(t.comparators[0], ast.Constant)
                and t.comparators[0].value == "__main__"):
            spans.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
    return spans


def select_sites(mutants, funcs=None, ranges=None, sample=None, limit=None,
                 guard_spans=None):
    """Filter/subsample a mutant list; returns `(mutants, selection_dict)`.

    Order of operations is deliberate: scope first (`funcs`), then stride
    (`sample`), then head-cut (`limit`). `limit` last so that a caller who
    passes both gets the documented head bias only over an already-uniform
    sample rather than instead of it.
    """
    sel = {"generated": len(mutants), "funcs": sorted(funcs) if funcs else None,
           "sample": sample, "limit": limit, "head_biased": bool(limit),
           "main_guard_excluded": 0}
    if guard_spans:
        by_path = dict(guard_spans)
        kept = [m for m in mutants
                if not any(lo <= m.lineno <= hi
                           for lo, hi in by_path.get(m.path, ()))]
        sel["main_guard_excluded"] = len(mutants) - len(kept)
        mutants = kept
    if funcs:
        spans = [ranges[f] for f in funcs if f in ranges]
        missing = sorted(f for f in funcs if f not in (ranges or {}))
        if missing:
            raise KeyError("no such function(s) in subject: %s" % ", ".join(missing))
        mutants = [m for m in mutants
                   if any(lo <= m.lineno <= hi for lo, hi in spans)]
    if sample and sample < len(mutants):
        # Evenly spaced by index, endpoints included: a uniform view of the
        # whole site list rather than its first N entries.
        n = len(mutants)
        idx = sorted({round(i * (n - 1) / (sample - 1)) for i in range(sample)}) \
            if sample > 1 else [0]
        mutants = [mutants[i] for i in idx]
    if limit:
        mutants = mutants[:limit]
    sel["selected"] = len(mutants)
    return mutants, sel


def pytest_cmd(test_paths, junit_path, python=None):
    """The runner every unit uses. NO `-x`.

    `-x` is why this could not be built on top of the existing campaign
    command: it stops at the first failure, so the junit report names ONE
    red node per mutant and every other node that would have caught the
    same mutant is recorded as passing. Attribution under `-x` measures
    collection order.
    """
    return [python or sys.executable, "-m", "pytest", "-q",
            "-p", "no:cacheprovider", "--junitxml=%s" % junit_path] + list(test_paths)


def _run_in_copy(project_root, test_paths, timeout_s, mutant=None):
    """One suite run in a throwaway copy. -> `(result, junit_record)`.

    The junit file is written OUTSIDE the copied tree, as a sibling of
    `proj`, for `baseline_check`'s reason: inside it, the report is one more
    file for every test that walks the subtree.
    """
    tmp = tempfile.mkdtemp(prefix="fals-")
    try:
        dst = os.path.join(tmp, "proj")
        mutation._copy_project(project_root, dst)
        if mutant is not None:
            with open(os.path.join(dst, mutant.path), "w", encoding="utf-8") as fh:
                fh.write(mutant.source)
        xml = os.path.join(tmp, "report.xml")
        cmd = pytest_cmd(test_paths, xml)
        r = run_capped(cmd, dst, timeout_s)
        rec = parse_junit(xml)
        return r, rec, cmd
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Baseline(object):
    """The unmutated run: the population of nodes a campaign can talk about."""

    def __init__(self, returncode, timed_out, seconds, statuses, evidence, tail):
        self.returncode = returncode
        self.timed_out = timed_out
        self.seconds = seconds
        self.statuses = statuses          # {key: junit status}
        self.evidence = evidence          # sandboxevidence block
        self.tail = tail

    @property
    def green(self):
        return self.returncode == 0 and not self.timed_out

    @property
    def passed(self):
        """Keys that PASSED at baseline — the only nodes that can be
        `never_red`. A node already skipped in the sandbox never runs, so
        calling it unfalsifiable would be an accusation against the copy."""
        return sorted(k for k, v in self.statuses.items() if v == "passed")

    @property
    def skipped(self):
        return sorted(k for k, v in self.statuses.items() if v == "skipped")

    def as_dict(self):
        return {"returncode": self.returncode, "timed_out": self.timed_out,
                "seconds": round(self.seconds, 2), "n_nodes": len(self.statuses),
                "n_passed": len(self.passed), "n_skipped": len(self.skipped),
                "skipped": self.skipped,
                "evidence_verdict": (self.evidence or {}).get("verdict"),
                "tail": self.tail[-800:]}


def baseline(project_root, test_paths, timeout_s=120.0, suite=None,
             registry_path=None):
    """Run the unit's tests against an UNMUTATED copy and read the report."""
    r, rec, cmd = _run_in_copy(project_root, test_paths, timeout_s)
    ev = SE.check(rec, suite=suite, registry_path=registry_path)
    return Baseline(-9 if r.timed_out else r.returncode, r.timed_out, r.seconds,
                    dict(rec.get("statuses") or {}), ev, (r.output or "").strip())


class Attribution(object):
    """One mutant's result, plus the nodes that went red for it."""

    def __init__(self, mutant, red, junit_ok, n_nodes):
        self.mutant = mutant
        self.red = sorted(red)
        self.junit_ok = junit_ok
        self.n_nodes = n_nodes

    @property
    def attributed(self):
        """A kill we can name a killer for."""
        return self.mutant.status in ("killed", "timeout") and bool(self.red)

    @property
    def unattributed(self):
        return self.mutant.status in ("killed", "timeout") and not self.red

    def as_dict(self):
        d = self.mutant.as_dict()
        d["red"] = self.red
        d["junit_ok"] = self.junit_ok
        d["n_nodes"] = self.n_nodes
        return d


def run_mutant_attributed(m, project_root, test_paths, timeout_s=120.0):
    """`run_mutant` plus junit attribution. Mutates and returns `m`."""
    r, rec, cmd = _run_in_copy(project_root, test_paths, timeout_s, mutant=m)
    m.seconds = r.seconds
    red = set()
    junit_ok = bool(rec.get("ok"))
    if r.timed_out:
        m.status = "timeout"
        m.detail = "test run exceeded %.0fs (process group killed)" % timeout_s
    else:
        m.status = mutation.classify_mutant_run(r.returncode, r.output, cmd)
        if m.status != "survived":
            m.detail = "\n".join((r.output or "").strip().splitlines()[-3:])
    if junit_ok:
        red = {k for k, v in (rec.get("statuses") or {}).items() if v in RED}
    return Attribution(m, red, junit_ok, len(rec.get("statuses") or {}))


class FalsifierReport(object):
    def __init__(self, unit, subject_paths, test_paths, base, attributions,
                 selection, seconds):
        self.unit = unit
        self.subject_paths = list(subject_paths)
        self.test_paths = list(test_paths)
        self.baseline = base
        self.attributions = list(attributions)
        self.selection = dict(selection or {})
        self.seconds = seconds

    # -- mutant-side numbers (same definitions as MutationReport) ----------
    @property
    def mutants(self):
        return [a.mutant for a in self.attributions]

    @property
    def killed(self):
        return [a for a in self.attributions
                if a.mutant.status in ("killed", "timeout")]

    @property
    def survived(self):
        return [a for a in self.attributions if a.mutant.status == "survived"]

    @property
    def errored(self):
        return [a for a in self.attributions if a.mutant.status == "error"]

    @property
    def score(self):
        return len(self.killed) / len(self.attributions) if self.attributions else 0.0

    # -- test-side numbers, which is what this module is for ---------------
    @property
    def kills(self):
        """`{node key: how many mutants it killed}` over EVERY baseline-passed
        node, zeros included. Built from the baseline population and not from
        the union of red sets, so a node that never appears in any red set is
        present with a 0 rather than absent."""
        out = {k: 0 for k in self.baseline.passed}
        for a in self.attributions:
            for k in a.red:
                out[k] = out.get(k, 0) + 1
        return out

    @property
    def never_red(self):
        k = self.kills
        return sorted(n for n in self.baseline.passed if k.get(n, 0) == 0)

    @property
    def unattributed_kills(self):
        return [a for a in self.killed if a.unattributed]

    @property
    def attribution_coverage(self):
        """Killed mutants whose killer we can name / killed mutants."""
        n = len(self.killed)
        return (n - len(self.unattributed_kills)) / n if n else 1.0

    @property
    def node_loss(self):
        """Mutant runs that COLLECTED fewer nodes than the baseline did.

        `sandboxevidence`'s hole 3, one level down: a mutant that breaks
        collection runs a smaller suite, and every node it did not collect
        looks `never_red` for a reason that has nothing to do with the
        node. Errored runs are excluded — they are already counted, and a
        run that produced no evidence is not a run that lost some."""
        floor = len(self.baseline.statuses)
        return [a for a in self.attributions
                if a.junit_ok and a.n_nodes < floor
                and a.mutant.status != "error"]

    @property
    def sound(self):
        """May this campaign's `never_red` list be read as a finding?

        False when any kill is unattributed, any run errored, or any mutant
        collected fewer nodes than the baseline. All three make `never_red`
        an UPPER BOUND rather than a list."""
        return (not self.unattributed_kills and not self.errored
                and not self.node_loss)

    @property
    def verdict(self):
        if not self.sound:
            return V_UNSOUND
        if not self.killed:
            return V_NO_KILLS
        return V_NEVER_RED if self.never_red else V_ALL_FALSIFIABLE

    def summary(self):
        k = self.kills
        lines = [
            "unit %s: subject %s  tests %s"
            % (self.unit, ", ".join(self.subject_paths), ", ".join(self.test_paths)),
            "  mutants %d (%d generated, %d in a __main__ guard, %s)  "
            "killed %d  survived %d  errored %d"
            % (len(self.attributions), self.selection.get("generated", 0),
               self.selection.get("main_guard_excluded", 0),
               "sample %s" % self.selection["sample"] if self.selection.get("sample")
               else ("head-limited %s" % self.selection["limit"]
                     if self.selection.get("limit") else "whole"),
               len(self.killed), len(self.survived), len(self.errored)),
            "  mutation score %.1f%%   attribution coverage %.1f%%   (%.0fs)"
            % (100 * self.score, 100 * self.attribution_coverage, self.seconds),
            "  nodes %d passed at baseline, %d skipped"
            % (len(self.baseline.passed), len(self.baseline.skipped)),
            "  VERDICT %s: %d/%d node(s) never went red"
            % (self.verdict, len(self.never_red), len(self.baseline.passed)),
        ]
        if not self.sound:
            lines.append(
                "  !! NOT SOUND -- %d unattributed kill(s), %d errored mutant(s), "
                "%d run(s) collected fewer nodes than the baseline. The list "
                "below is an UPPER BOUND on the never-red set, not the set."
                % (len(self.unattributed_kills), len(self.errored),
                   len(self.node_loss)))
        for n in self.never_red:
            lines.append("  NEVER-RED  %s" % n)
        top = sorted(k.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        for name, c in top:
            lines.append("  killer     %-58s %d" % (name, c))
        return "\n".join(lines)

    def as_dict(self):
        return {
            "unit": self.unit,
            "subject_paths": self.subject_paths,
            "test_paths": self.test_paths,
            "selection": self.selection,
            "baseline": self.baseline.as_dict(),
            "seconds": round(self.seconds, 1),
            "total": len(self.attributions),
            "killed": len(self.killed),
            "survived": len(self.survived),
            "errored": len(self.errored),
            "score": round(self.score, 4),
            "attribution_coverage": round(self.attribution_coverage, 4),
            "unattributed_kills": [a.mutant.id for a in self.unattributed_kills],
            "node_loss": [a.mutant.id for a in self.node_loss],
            "sound": self.sound,
            "verdict": self.verdict,
            "kills": self.kills,
            "never_red": self.never_red,
            "mutants": [a.as_dict() for a in self.attributions],
        }


def audit(project_root, subject_paths, test_paths, unit=None, ops=None,
          funcs=None, sample=None, limit=None, timeout_s=120.0,
          on_result=None, suite=None, registry_path=None, base=None,
          skip_main_guard=True):
    """Run one falsification audit. Raises `mutation.BaselineNotGreen`.

    `base` lets a caller supply an already-taken `Baseline` (the tests do;
    a real campaign should not, because the baseline is what pins the node
    population the rest of the run is scored against).
    """
    if base is None:
        base = baseline(project_root, test_paths, timeout_s, suite=suite,
                        registry_path=registry_path)
    if not base.green:
        raise mutation.BaselineNotGreen(base.returncode, base.tail)
    mutants = []
    ranges = {}
    guards = []
    for rel in subject_paths:
        with open(os.path.join(project_root, rel), encoding="utf-8") as fh:
            src = fh.read()
        mutants.extend(mutation.generate(src, rel, ops=ops))
        if funcs:
            ranges.update(function_ranges(src))
        if skip_main_guard:
            guards.append((rel, main_guard_spans(src)))
    mutants, selection = select_sites(mutants, funcs=funcs, ranges=ranges,
                                      sample=sample, limit=limit,
                                      guard_spans=guards or None)
    t0 = time.time()
    attributions = []
    for m in mutants:
        # Serial on purpose: `nproc` on this box is 1, and a contended
        # mutant run is a timeout waiting to become a phantom kill.
        a = run_mutant_attributed(m, project_root, test_paths, timeout_s)
        attributions.append(a)
        if on_result:
            on_result(a)
    return FalsifierReport(unit or (subject_paths[0] if subject_paths else "?"),
                           subject_paths, test_paths, base, attributions,
                           selection, time.time() - t0)


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="falsifiers",
                                 description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="run one per-test falsification audit")
    a.add_argument("--root", default=AGI_RESEARCH_ROOT)
    a.add_argument("--subject", action="append", required=True,
                   help="repo-relative module to mutate (repeatable)")
    a.add_argument("--tests", action="append", required=True,
                   help="repo-relative test path to run (repeatable)")
    a.add_argument("--unit", help="name for the report")
    a.add_argument("--func", action="append",
                   help="restrict mutation sites to this def/class (repeatable)")
    a.add_argument("--ops", help="comma-separated mutation operators")
    a.add_argument("--sample", type=int, help="evenly spaced subsample of sites")
    a.add_argument("--limit", type=int, help="first N sites (HEAD-BIASED)")
    a.add_argument("--timeout-s", type=float, default=120.0)
    a.add_argument("--include-main-guard", action="store_true",
                   help="also mutate `if __name__ == \"__main__\"` (never evidence)")
    a.add_argument("--json", help="write the full report here")
    a.add_argument("--quiet", action="store_true")

    b = sub.add_parser("functions", help="list mutable def/class ranges")
    b.add_argument("path")

    c = sub.add_parser("report", help="re-print a saved --json report")
    c.add_argument("json")

    ns = ap.parse_args(argv)
    if ns.cmd == "functions":
        with open(ns.path, encoding="utf-8") as fh:
            src = fh.read()
        counts = {}
        for m in mutation.generate(src, ns.path):
            counts[m.lineno] = counts.get(m.lineno, 0) + 1
        for name, (lo, hi) in sorted(function_ranges(src).items(),
                                     key=lambda kv: kv[1]):
            n = sum(v for ln, v in counts.items() if lo <= ln <= hi)
            print("%-52s %5d-%-5d %4d site(s)" % (name, lo, hi, n))
        return 0
    if ns.cmd == "report":
        with open(ns.json, encoding="utf-8") as fh:
            d = json.load(fh)
        print("unit %s  verdict %s  score %.1f%%  coverage %.1f%%"
              % (d["unit"], d["verdict"], 100 * d["score"],
                 100 * d["attribution_coverage"]))
        for n in d["never_red"]:
            print("  NEVER-RED  %s" % n)
        return 0

    rep = audit(ns.root, ns.subject, ns.tests, unit=ns.unit,
                ops=tuple(ns.ops.split(",")) if ns.ops else None,
                funcs=ns.func, sample=ns.sample, limit=ns.limit,
                timeout_s=ns.timeout_s, skip_main_guard=not ns.include_main_guard,
                on_result=None if ns.quiet else
                (lambda a: print("%-9s %-38s red=%d" % (a.mutant.status,
                                                        a.mutant.id, len(a.red)),
                                 flush=True)))
    print(rep.summary())
    if ns.json:
        with open(ns.json, "w", encoding="utf-8") as fh:
            json.dump(rep.as_dict(), fh, indent=1, sort_keys=True)
        print("wrote %s" % ns.json)
    # rc 2 when the campaign cannot support its own claim; rc 1 when it can
    # and the claim is "some node here never went red".
    if not rep.sound:
        return 2
    return 1 if rep.never_red else 0


if __name__ == "__main__":
    sys.exit(_main())

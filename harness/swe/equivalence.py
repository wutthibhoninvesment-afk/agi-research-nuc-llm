"""Escalated corpus search: an equivalence VERDICT for `no_killer`
survivors, with no live model call (round 220).

Round 107 named this the missing piece: "an equivalence verdict for the
126 `no_killer` survivors" (const 45 = budget/cache constants). Two other
items on that same list turned out to already be built by the time this
round looked -- `prioritize.MapPrioritizer(subset=True)` (round 113) IS
"a smaller suite for survivors", and its `cov_map` IS "a per-test coverage
map for kill-first ordering" -- research-state.md's summary line had just
gone stale (see the round-220 knowledge file for the re-verification). The
fourth item, "live kill/review at n > 8 with malformed-tool-call
detection", needs a real `ANTHROPIC_API_KEY`, never available on this
machine (harness(A)'s standing note) -- `review.run_kill`'s own
"equivalent_claimed" verdict already covers the model-driven half of this
question when a key IS available; this module covers the half that never
needed one.

`killers.find_killer` already tries hard (round 0's corpus: 300 programs,
one seed, stress_rate=0.15, max_depth=3) before calling a survivor
`no_killer`. That answers "not with THIS corpus", not "not with any
program" -- the corpus is a stand-in for the whole space of Whence
programs, and every corpus is finite. This module escalates: several more
programs, across several independent seeds AND a wider stress_rate/
max_depth sweep than the default (bigger and more diverse than "the same
knobs, more of them"), reusing `killers.find_killer` unchanged so shrink/
behaviour/tempdir-copy logic is not duplicated. A survivor that still
finds no distinguishing program after every escalation level is reported
`likely_equivalent` -- WITH the total program count as its own stated
confidence, never as a proof. The equivalent-mutant problem is
undecidable in general: a program the escalation corpus never happened to
generate can always exist. Consumers of this report must read the effort
number, not just the verdict string.

Restricting escalation to the genuinely AMBIGUOUS bucket (matches round
107's own framing) is the caller's job, via `filter_ambiguous`: mutants
that are (a) `covered` by the suite (an `uncovered` no_killer survivor is
a test-gap, not an equivalence question -- `coverage.py` already says so)
and (b) `behavioural` per `triage.py` (a `counter`/`budget` survivor is
provably unobservable from any Whence program BY CONSTRUCTION -- it
changes host bookkeeping a guest program cannot read -- so escalating it
would spend a corpus search to reconfirm something `triage.py` already
proved structurally, for free).
"""

import json
import time

from . import coverage as CV
from . import triage as TR
from .fuzz import ProgramGen
from .killers import find_killer, load_whence, rebuild_mutants

# (seed, n, stress_rate, max_depth) — each level is both BIGGER and more
# DIVERSE than the default corpus (killers.corpus: stress_rate=0.15,
# max_depth=3), not just a repeat at a new seed; escalation stops at the
# first level that finds a killer, so cheap/likely levels come first.
DEFAULT_LEVELS = (
    (90001, 400, 0.15, 3),   # more of the default shape, fresh seed
    (90002, 400, 0.35, 4),   # deeper, more stress-template-heavy
    (90003, 400, 0.55, 5),   # deeper still, stress-dominant
    (90004, 400, 0.15, 3),   # a second independent sample at the default shape
)


def escalation_corpus(levels=DEFAULT_LEVELS):
    """The full escalation program list, plus the cumulative program count
    at the end of each level (for reporting which level a killer needed)."""
    programs = []
    bounds = []
    for seed, n, stress_rate, max_depth in levels:
        for i in range(n):
            programs.append(ProgramGen(seed * 7919 + i, stress_rate=stress_rate,
                                       max_depth=max_depth).program())
        bounds.append(len(programs))
    return programs, bounds


def level_reached(tried, bounds):
    """1-based index of the escalation level that contained program #`tried`
    (1-indexed, matching `Killer.tried`)."""
    for i, b in enumerate(bounds):
        if tried <= b:
            return i + 1
    return len(bounds)


class EquivalenceVerdict(object):
    def __init__(self, mutant, killer, levels, bounds):
        self.mutant = mutant
        self.killer = killer               # a killers.Killer — found means "corpus_gap, now closed"
        self.levels = levels
        self.bounds = bounds

    @property
    def verdict(self):
        return "corpus_gap_closed" if self.killer.found else "likely_equivalent"

    def as_dict(self):
        d = {
            "id": self.mutant.id, "verdict": self.verdict,
            "programs_tried": self.killer.tried, "total_programs": self.bounds[-1],
            "seconds": round(self.killer.seconds, 2),
        }
        if self.killer.found:
            d["level_reached"] = level_reached(self.killer.tried, self.bounds)
            d["total_levels"] = len(self.levels)
            d["killer_program"] = self.killer.program
            d["expected"] = self.killer.expected
            d["mutant_behaviour"] = self.killer.mutant_behaviour
        else:
            d["level_reached"] = len(self.levels)
            d["total_levels"] = len(self.levels)
        return d


def escalate(mutant, original_pkg, project_root, levels=DEFAULT_LEVELS, orig_cache=None,
             programs=None, bounds=None):
    """Run `mutant` through the escalation corpus. Returns an
    EquivalenceVerdict. `programs`/`bounds` may be precomputed (shared
    across many mutants — the escalation corpus does not depend on which
    mutant is under test) via `escalation_corpus`."""
    if programs is None:
        programs, bounds = escalation_corpus(levels)
    k = find_killer(mutant, programs, original_pkg, project_root, orig_cache)
    return EquivalenceVerdict(mutant, k, levels, bounds)


def filter_ambiguous(mutant_dicts, cov=None, source_by_path=None):
    """The subset of `survived` mutants worth escalating: covered by the
    suite (else it's a test gap, not an equivalence question) AND
    behavioural per triage.py (else it's provably unobservable from any
    Whence program by construction, not a corpus question). Returns
    (ambiguous_dicts, dropped_counts) — dropped counts are reported, never
    silently discarded from the total."""
    survivors = [d for d in mutant_dicts if d["status"] == "survived"]
    dropped = {"uncovered": 0, "unknown_coverage": 0, "non_behavioural": 0}
    if cov is not None:
        CV.annotate_mutants(survivors, cov)
        kept = []
        for d in survivors:
            if d["covered"] is True:
                kept.append(d)
            elif d["covered"] is False:
                dropped["uncovered"] += 1
            else:
                dropped["unknown_coverage"] += 1
        survivors = kept
    if source_by_path is not None:
        cache = dict((p, TR.sites(src)) for p, src in source_by_path.items())
        kept = []
        for d in survivors:
            s = cache.get(d["path"], {}).get(TR.site_index(d["id"]))
            kind = s.kind if s else "other"
            if kind in TR.NON_BEHAVIOURAL:
                dropped["non_behavioural"] += 1
            else:
                kept.append(d)
        survivors = kept
    return survivors, dropped


def run_equivalence(mutant_dicts, project_root, levels=DEFAULT_LEVELS, on_result=None,
                    programs=None, bounds=None):
    """Escalate every mutant dict in `mutant_dicts` (already filtered to the
    ambiguous bucket). Shares one original-behaviour cache and one
    escalation corpus across all of them (the expensive part — generating
    ~1600 programs and running the ORIGINAL interpreter on them once each
    — is paid once, not per mutant). `programs`/`bounds` may be precomputed
    (e.g. `escalation_corpus` reused across several `run_equivalence` calls,
    or a fixed deterministic corpus in a test) instead of generated fresh."""
    mutants = rebuild_mutants(project_root, mutant_dicts)
    original = load_whence(project_root, "orig_equiv")
    if programs is None:
        programs, bounds = escalation_corpus(levels)
    cache = {}
    out = []
    for m in mutants:
        v = escalate(m, original, project_root, levels, cache, programs, bounds)
        out.append(v)
        if on_result:
            on_result(v)
    return out


def summarize(verdicts):
    closed = [v for v in verdicts if v.verdict == "corpus_gap_closed"]
    equiv = [v for v in verdicts if v.verdict == "likely_equivalent"]
    return {
        "total": len(verdicts),
        "corpus_gap_closed": len(closed),
        "likely_equivalent": len(equiv),
        "programs_per_verdict_mean": (
            round(sum(v.killer.tried for v in verdicts) / len(verdicts), 1) if verdicts else 0),
        "total_escalation_programs": verdicts[0].bounds[-1] if verdicts else 0,
    }


def main(argv=None):
    import argparse
    from .fuzz import WHENCE_ROOT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mutation_json")
    ap.add_argument("--project", default=WHENCE_ROOT)
    ap.add_argument("--coverage-map", help="by-file coverage JSON (swe.coverage --by-file); "
                    "restricts escalation to covered survivors")
    ap.add_argument("--no-triage-filter", action="store_true",
                    help="escalate counter/budget survivors too (normally skipped: provably "
                    "unobservable from any Whence program)")
    ap.add_argument("--out", help="write equivalence JSON here")
    a = ap.parse_args(argv)

    with open(a.mutation_json, encoding="utf-8") as f:
        data = json.load(f)

    cov = None
    if a.coverage_map:
        cov = CV.load(a.coverage_map)
        if CV.is_by_file(cov):
            cov = CV.collapse(cov)

    source_by_path = None
    if not a.no_triage_filter:
        import os
        paths = sorted(set(d["path"] for d in data["mutants"] if d["status"] == "survived"))
        source_by_path = {}
        for p in paths:
            with open(os.path.join(a.project, p), encoding="utf-8") as f:
                source_by_path[p] = f.read()

    ambiguous, dropped = filter_ambiguous(data["mutants"], cov, source_by_path)
    print("ambiguous survivors: %d (dropped %s)" % (len(ambiguous), dropped))
    if not ambiguous:
        result = {"dropped": dropped, "verdicts": [], "summary": summarize([])}
    else:
        t0 = time.time()
        verdicts = run_equivalence(
            ambiguous, a.project,
            on_result=lambda v: print("%-20s %s tried=%d/%d %.1fs" % (
                v.verdict, v.mutant.id, v.killer.tried, v.bounds[-1], v.killer.seconds), flush=True))
        result = {"dropped": dropped, "verdicts": [v.as_dict() for v in verdicts],
                  "summary": summarize(verdicts), "seconds": round(time.time() - t0, 2)}
        print("equivalence: %s" % result["summary"])
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

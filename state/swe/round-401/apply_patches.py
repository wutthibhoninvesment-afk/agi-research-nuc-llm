"""Round 401's edits to the three files the running arm-C sweep depends on.

Held back and applied in one shot AFTER the sweep stopped, because round
389's own rule says so: "an anchor-verified registry makes source edits and
long-running sweeps mutually exclusive". The precise scope, worked out this
round: `exemptmap.sweep` re-reads `oracles.py` (per-row `oracles_digest()`)
and, being RESUMABLE, would regenerate the remaining seeds from whatever
`fuzz.py` is on disk when it resumes. So `oracles.py`, `exemptmap.py` and
`fuzz.py` were frozen for arm C's whole run; `exemptaudit.py`, `guest.py`
and the two new modules were not, and were edited live.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def patch(rel, pairs):
    p = os.path.join(ROOT, rel)
    s = open(p, encoding="utf-8").read()
    for old, new in pairs:
        n = s.count(old)
        if n != 1:
            raise SystemExit("!! %s: anchor occurs %d times:\n%s" % (rel, n, old[:200]))
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("patched %s (%d edit(s))" % (rel, len(pairs)))


# ------------------------------------------------------------- oracles.py --

ORACLES = [
    # 1. the named switch
    ("""FRAME_SLACK_MARGIN = 40
""",
     """FRAME_SLACK_MARGIN = 40

# (round 401) The tail-transparency SPACE exemption used to fire whenever the
# LIFTED run reached `max_depth`, regardless of what the ORIGINAL run did.
# Round 401 measured the two populations that branch was covering over round
# 389's arm-A corpus (41 firings of 324 usable seeds, `max_depth=500`):
#
#   26  only the lifted run hit the ceiling (`peak_original` was 1 —
#       fully merged). The answers differ, the difference IS the ceiling,
#       and exempting is correct. This is what the branch was built for.
#   15  BOTH runs hit the ceiling. Neither form got further than the other,
#       the depth miss is symmetric, and the suppressed difference was
#       EMPTY in every one of the 15.
#
# So the branch was dropping 15 valid comparisons to protect against a
# false positive that only the first population can produce. Setting this
# False makes the oracle compare the symmetric case.
#
# It is a NAMED CONSTANT rather than a silent narrowing because the risk is
# real and this corpus does not exhaust it: two runs stopped by the same
# ceiling CAN legitimately differ (merging lets the original get further in
# PROGRAM terms before the wall, so it could miss in a different function).
# Zero such cases here; `harness/swe/spacewitness.py` classifies that case
# as `suppressed_at_ceiling` and counts it as an ALARM precisely so a future
# round can tell a real interpreter bug from a re-widening.
SPACE_EXEMPT_WHEN_BOTH_AT_CEILING = False
"""),

    # 2. keep the original run's peak
    ("""    a, _ = _answer(pkg, program, tainted, whole, max_depth=max_depth)
    try:
        b, peak = _answer(pkg, lifted, tainted, whole, max_depth=max_depth)""",
     """    a, peak_orig = _answer(pkg, program, tainted, whole, max_depth=max_depth)
    try:
        b, peak = _answer(pkg, lifted, tainted, whole, max_depth=max_depth)"""),

    # 3. the tightened branch + both peaks in every detail
    ("""    if peak >= max_depth:
        return OracleOutcome("ok", TAIL_ORACLE,
                             "%d tail calls, lifted run reached depth %d >= "
                             "max_depth %d (space-exempt)" % (n, peak, max_depth))
    if not a["vals"] and not whole:
        return OracleOutcome("ok", TAIL_ORACLE,
                             "%d tail calls, every binding provenance-tainted "
                             "(exempt)" % n)
    d = first_difference(a, b)
    detail = "%d tail calls, %s" % (n, scope)""",
     """    # (round 401) `peak_orig` is the number this branch used to discard.
    # Exempt only the ASYMMETRIC case — the lifted run ran out of a resource
    # the original did not need. When both runs stop at the same wall the
    # comparison is on equal footing; see SPACE_EXEMPT_WHEN_BOTH_AT_CEILING.
    if peak >= max_depth and (SPACE_EXEMPT_WHEN_BOTH_AT_CEILING
                              or peak_orig < max_depth):
        return OracleOutcome("ok", TAIL_ORACLE,
                             "%d tail calls, lifted run reached depth %d >= "
                             "max_depth %d while the original reached %d "
                             "(space-exempt)" % (n, peak, max_depth, peak_orig))
    if not a["vals"] and not whole:
        return OracleOutcome("ok", TAIL_ORACLE,
                             "%d tail calls, every binding provenance-tainted "
                             "(exempt)" % n)
    d = first_difference(a, b)
    # Round 110's convention: a verdict reports the numbers it decided on.
    ceiling = (", both runs reached max_depth %d" % max_depth
               if peak >= max_depth and peak_orig >= max_depth else "")
    detail = "%d tail calls, %s, original reached %d / lifted %d%s" % (
        n, scope, peak_orig, peak, ceiling)"""),

    # 4. campaign instrument fields
    ("""    def as_dict(self):
        return {"programs": self.programs, "seconds": round(self.seconds, 2),
                "oracles": list(self.oracles),
                "counts": dict(("%s/%s" % k, v) for k, v in self.counts.items()),
                "findings": [f.as_dict() for f in self.findings.values()]}""",
     """    def as_dict(self):
        # (round 401) A campaign is ONE object, so the analogue of a mixed
        # JSONL is start-vs-end: `instrument_moved` names the parts of the
        # instrument that changed while the campaign ran. Absent on a
        # campaign built by hand, which is why both reads are guarded.
        start = getattr(self, "instrument", None)
        end = getattr(self, "instrument_end", None)
        moved = sorted(k for k in (start or {})
                       if k != "lane" and (end or {}).get(k, start[k]) != start[k])
        return {"programs": self.programs, "seconds": round(self.seconds, 2),
                "oracles": list(self.oracles),
                "counts": dict(("%s/%s" % k, v) for k, v in self.counts.items()),
                "instrument": start, "instrument_end": end,
                "instrument_moved": moved,
                "findings": [f.as_dict() for f in self.findings.values()]}"""),
]

# ----------------------------------------------------------- exemptmap.py --

EXEMPTMAP = [
    # 1. the anchor the registry verifies must follow the branch it names
    ('''    Site("T-SPACE", "tail_transparency", "lifted run reached max_depth: space-exempt",
         "threshold", "distance", 500,
         "    if peak >= max_depth:", 1,
         "threshold is the caller's max_depth, not a module constant"),''',
     '''    # (round 401) The anchor moved with the branch: the exemption is now
    # conditional on the ORIGINAL run having stayed under the ceiling. The
    # site is NOT retired — it still fires, on the 26 of 41 seeds where the
    # asymmetry is real; what changed is that it no longer fires on the 15
    # where both runs stopped at the same wall.
    Site("T-SPACE", "tail_transparency", "lifted run reached max_depth and the original did not: space-exempt",
         "threshold", "distance", 500,
         "    if peak >= max_depth and (SPACE_EXEMPT_WHEN_BOTH_AT_CEILING", 1,
         "threshold is the caller's max_depth, not a module constant; "
         "round 401 narrowed the branch to the asymmetric case"),'''),

    # 2. measure: keep the original peak, split fired from censored
    ('''    a, _peak_a = O._answer(pkg, O._parse(pkg, src), tainted, whole,
                           max_depth=max_depth)''',
     '''    a, peak_a = O._answer(pkg, O._parse(pkg, src), tainted, whole,
                          max_depth=max_depth)'''),

    ('''    if n_tail:
        try:
            _b, peak = O._answer(pkg, lifted, tainted, whole, max_depth=max_depth)
            fired = peak >= max_depth
            s["T-SPACE"] = {
                "fired": fired, "demand": peak, "threshold": max_depth,
                # The demand is RIGHT-CENSORED: the interpreter stops at
                # max_depth, so `peak == max_depth` means "at least 500", not
                # "500". `depth_ladder` is what un-censors it, and until it
                # runs, any distance computed from this number is a floor.
                "censored": fired,
                # A fired T-SPACE returns `ok` without comparing anything.
                "surface": 0.0 if fired else 1.0}
        except RecursionError:
            s["T-SPACE"] = {"fired": True, "demand": None, "censored": True,
                            "surface": 0.0,
                            "threshold": max_depth, "note": "RecursionError"}
    else:
        s["T-SPACE"] = {"fired": False, "demand": 0, "threshold": max_depth,
                        "censored": False, "surface": 1.0,
                        "note": "no lifted run (T-NONE)"}''',
     '''    if n_tail:
        try:
            _b, peak = O._answer(pkg, lifted, tainted, whole, max_depth=max_depth)
            # (round 401) Mirrors the oracle's tightened branch exactly.
            # `test_measure_agrees_with_the_oracle_it_describes` is the
            # cross-check that makes this a duplication and not a fork.
            fired = peak >= max_depth and (
                O.SPACE_EXEMPT_WHEN_BOTH_AT_CEILING or peak_a < max_depth)
            s["T-SPACE"] = {
                "fired": fired, "demand": peak, "threshold": max_depth,
                # (round 401) The number the oracle and this function both
                # used to discard. It is what separates the 26 firings the
                # exemption is FOR from the 15 it was dropping for nothing.
                "demand_original": peak_a,
                # The demand is RIGHT-CENSORED: the interpreter stops at
                # max_depth, so `peak == max_depth` means "at least 500", not
                # "500". `depth_ladder` is what un-censors it, and until it
                # runs, any distance computed from this number is a floor.
                #
                # (round 401) Censoring is a property of the NUMBER, not of
                # the branch. Round 383 could write `censored = fired`
                # because the two coincided; after the tightening a seed can
                # be censored and not fire (both runs at the wall). Firing
                # still implies censoring, and that is the invariant now.
                "censored": peak >= max_depth,
                # A fired T-SPACE returns `ok` without comparing anything.
                "surface": 0.0 if fired else 1.0}
        except RecursionError:
            s["T-SPACE"] = {"fired": True, "demand": None, "censored": True,
                            "surface": 0.0, "demand_original": peak_a,
                            "threshold": max_depth, "note": "RecursionError"}
    else:
        s["T-SPACE"] = {"fired": False, "demand": 0, "threshold": max_depth,
                        "censored": False, "surface": 1.0,
                        "demand_original": peak_a,
                        "note": "no lifted run (T-NONE)"}'''),

    # 3. the full instrument stamp beside round 389's single hash
    ('''    row["oracles_sha"] = oracles_digest()''',
     '''    row["oracles_sha"] = oracles_digest()
    # (round 401) Round 389's item 4: `oracles_sha` names ONE part of the
    # instrument. A seed only denotes a program relative to a fixed
    # `ProgramGen`, so an edit to `fuzz.py` changes what `seed 140` IS while
    # `oracles_sha` stays put. The full stamp is kept ALONGSIDE the old key,
    # not instead of it: three rounds of published arms read `oracles_sha`
    # and `ab()`'s `mixed_instrument` still keys on it.
    row[INS.STAMP_KEY] = INS.stamp("exemptmap.sweep")'''),

    ('''from . import oracles as O
from .fuzz import ProgramGen, WHENCE_ROOT''',
     '''from . import instrument as INS
from . import oracles as O
from .fuzz import ProgramGen, WHENCE_ROOT'''),

    # 4. ab(): report every part, not just the oracle hash
    ('''    da, db = sweep_digests(path_a), sweep_digests(path_b)''',
     '''    da, db = sweep_digests(path_a), sweep_digests(path_b)
    # (round 401) The per-part view, for arms written after round 401. Older
    # arms have no stamp and land under `instrument.UNSTAMPED`, which is a
    # population, not an error — round 389's own two arms are in it, because
    # the guard was built after the sweeps it was built for had finished.
    parts_a = INS.digests(list(A.values()))
    parts_b = INS.digests(list(B.values()))'''),

    ('''           "mixed_instrument": len(da) > 1 or len(db) > 1,''',
     '''           "mixed_instrument": len(da) > 1 or len(db) > 1,
           "instrument_a": parts_a, "instrument_b": parts_b,
           "mixed_parts_a": INS.mixed_parts(list(A.values())),
           "mixed_parts_b": INS.mixed_parts(list(B.values())),
           # the part-level version of the question `ab()` exists to answer:
           # are these two arms even measuring the same thing?
           "arms_share_instrument": _same_parts(parts_a, parts_b),'''),

    ('''def _mode(vals):''',
     '''def _same_parts(pa, pb):
    """True when every part present in BOTH arms took exactly one value and
    the same one. None when either arm is unstamped — "unknown", which is
    the honest answer for a pre-round-401 file and is not False."""
    shared = set(pa) & set(pb) - {INS.UNSTAMPED}
    if not shared:
        return None
    for k in shared:
        if len(pa[k]) != 1 or pa[k] != pb[k]:
            return False
    return True


def _mode(vals):'''),
]

# ---------------------------------------------------------------- fuzz.py --

FUZZ = [
    ('''class Campaign(object):
    def __init__(self):
        self.counts = {}
        self.crashers = {}   # sig -> Crasher (first seen)
        self.programs = 0
        self.seconds = 0.0''',
     '''class Campaign(object):
    def __init__(self):
        self.counts = {}
        self.crashers = {}   # sig -> Crasher (first seen)
        self.programs = 0
        self.seconds = 0.0
        # (round 401) Round 389's item 4. A campaign is one object, so the
        # guard is start-vs-end rather than row-vs-row: if `fuzz.py` or the
        # whence tree moved while the campaign ran, the programs before the
        # edit and the programs after it are two populations.
        self.instrument = None
        self.instrument_end = None'''),

    ('''    def as_dict(self):
        return {"programs": self.programs, "seconds": round(self.seconds, 2),
                "counts": self.counts,
                "crashers": [c.as_dict() for c in self.crashers.values()]}''',
     '''    def instrument_moved(self):
        """Parts of the instrument that differ between the campaign's start
        and its end. Empty list = one population."""
        start, end = self.instrument or {}, self.instrument_end or {}
        return sorted(k for k in start
                      if k != "lane" and end.get(k, start[k]) != start[k])

    def as_dict(self):
        return {"programs": self.programs, "seconds": round(self.seconds, 2),
                "counts": self.counts,
                "instrument": self.instrument,
                "instrument_end": self.instrument_end,
                "instrument_moved": self.instrument_moved(),
                "crashers": [c.as_dict() for c in self.crashers.values()]}'''),

    ('''    camp = Campaign()
    t0 = time.time()''',
     '''    camp = Campaign()
    camp.instrument = _instrument().stamp("fuzz.fuzz")
    t0 = time.time()'''),

    ('''    camp.seconds = time.time() - t0
    return camp


if __name__ == "__main__":
    import argparse''',
     '''    camp.seconds = time.time() - t0
    camp.instrument_end = _instrument().stamp("fuzz.fuzz")
    return camp


if __name__ == "__main__":
    import argparse'''),

    # imported lazily: `instrument` imports nothing from this module, but
    # `oracles`/`exemptmap` import `fuzz` at module load and a top-level
    # cycle here would be one more thing to reason about for no gain.
    ('''class FuzzTimeout(Exception):''',
     '''def _instrument():
    """`harness.swe.instrument`, imported lazily (round 401).

    Everything else in this package imports `fuzz` at module load; keeping
    the dependency one-way means adding the guard cannot change any import
    order, which is the kind of change that shows up as a different fuzz
    corpus three rounds later.
    """
    from . import instrument
    return instrument


class FuzzTimeout(Exception):'''),
]


def main():
    patch("harness/swe/oracles.py", ORACLES)
    patch("harness/swe/exemptmap.py", EXEMPTMAP)
    patch("harness/swe/fuzz.py", FUZZ)
    return 0


if __name__ == "__main__":
    sys.exit(main())

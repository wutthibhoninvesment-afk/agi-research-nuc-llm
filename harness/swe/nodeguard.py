"""Per-subset baselines for nodeid-level mutant selection (round 491, SWE-loop D).

WHY THIS EXISTS
---------------
`prioritize.MapPrioritizer(subset=True)` runs a mutant against only the test
units that cover the mutated line. At round 113's granularity a unit is a
test FILE, so the whole file runs and every intra-file dependency -- import
order, module-scoped fixtures, a test that mutates a module global its
neighbour reads -- is preserved. At round 491's granularity a unit is a
single nodeid, and it is not.

The failure that introduces is asymmetric and silent. A test that only
passes when a file-mate ran first FAILS when selected alone, `pytest` exits
1, and `mutation.classify_mutant_run` reads exit 1 as `killed`. So an
order-dependent test manufactures a KILL for every mutant on every line it
covers -- inflating the mutation score, which is the one number the whole
campaign exists to report, in the direction that looks like good news.

`mutation_test`'s `baseline_check` cannot see it: that runs the WHOLE suite
once, where the dependency is satisfied by construction.

WHAT IT DOES
------------
Before a subset's verdict is trusted, run that exact subset against
UNMUTATED code. Green -> the subset is a sound oracle and every later
mutant selecting it is scored normally. Red -> the subset is poisoned; its
mutants are not scored from it and fall back to the full suite.

Verdicts are cached by the frozenset of nodeids, because subsets repeat
heavily (every mutant in one function tends to select the same tests), so
the cost is per DISTINCT subset, not per mutant.
"""

import os

from .proc import run_capped

#: Reported when a subset is red on unmutated code. Kept as a status string
#: rather than an exception: one poisoned subset must not end a campaign,
#: it must downgrade the mutants that would have used it.
POISONED = "poisoned"
CLEAN = "clean"


class SubsetBaseline(object):
    """Cache of `frozenset(nodeids) -> clean | poisoned` on unmutated code."""

    def __init__(self, project_root, base_cmd, timeout_s=120.0, runner=None):
        self.project_root = project_root
        self.base_cmd = list(base_cmd)
        self.timeout_s = timeout_s
        self.verdicts = {}          # frozenset -> CLEAN | POISONED
        self.details = {}           # frozenset -> tail of a poisoned run
        self.seconds = {}           # frozenset -> cost of the probe
        self.n_probes = 0
        self._runner = runner or self._run

    def _run(self, cmd):
        return run_capped(cmd, self.project_root, self.timeout_s)

    def cmd_for(self, units):
        """`base_cmd` ends with the tests target; replace it by the units."""
        return list(self.base_cmd[:-1]) + list(units)

    def verdict(self, units):
        """CLEAN or POISONED for this exact set of units, cached.

        An EMPTY selection is POISONED, not clean: `pytest` with no target
        collects nothing and exits 5, and a campaign that read that as a
        survivor would report "the suite does not notice this mutation"
        about a suite it never ran. Round 490 (NUC E) shipped the same shape
        one round earlier -- `sar --strict` exiting 0 on zero captures read --
        and this is that lesson applied to the instrument that scores tests.
        """
        key = frozenset(units)
        if key in self.verdicts:
            return self.verdicts[key]
        if not key:
            self.verdicts[key] = POISONED
            self.details[key] = "empty selection: nothing to run"
            return POISONED
        self.n_probes += 1
        r = self._runner(self.cmd_for(sorted(key)))
        self.seconds[key] = getattr(r, "seconds", 0.0)
        ok = (not getattr(r, "timed_out", False)) and r.returncode == 0
        self.verdicts[key] = CLEAN if ok else POISONED
        if not ok:
            tail = (r.output or "").strip().splitlines()
            self.details[key] = "\n".join(tail[-3:]) or ("returncode %s" % r.returncode)
        return self.verdicts[key]

    def is_clean(self, units):
        return self.verdict(units) == CLEAN

    def poisoned_subsets(self):
        return [(sorted(k), self.details.get(k, "")) for k, v in self.verdicts.items()
                if v == POISONED]

    def as_dict(self):
        n_bad = sum(1 for v in self.verdicts.values() if v == POISONED)
        return {
            "n_distinct_subsets": len(self.verdicts),
            "n_probes_run": self.n_probes,
            "n_clean": len(self.verdicts) - n_bad,
            "n_poisoned": n_bad,
            "probe_seconds": round(sum(self.seconds.values()), 1),
            "poisoned": [{"units": u, "detail": d} for u, d in self.poisoned_subsets()],
        }


def union_probe_units(prioritizer, mutants):
    """Distinct covering sets over `mutants`, largest first.

    Ordering matters for a budgeted run: probing the biggest subset first
    surfaces an order-dependent test at the point it is cheapest to act on,
    and a campaign that runs out of budget has probed the subsets that cover
    the most mutants rather than an arbitrary prefix.
    """
    seen = {}
    for m in mutants:
        units, _ = prioritizer.files_for(m)
        seen.setdefault(frozenset(units), 0)
        seen[frozenset(units)] += 1
    return [sorted(k) for k, _ in sorted(seen.items(), key=lambda kv: (-len(kv[0]), -kv[1]))]

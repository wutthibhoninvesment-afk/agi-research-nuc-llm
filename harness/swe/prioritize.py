"""Kill-first test ordering learned from a previous mutation run.

A killed mutant's record already says which test FILE failed first
(`FAILED tests/test_v09.py::test_x` in `detail`). For a new mutant at line
L we run the files that killed the nearest previously-killed mutants first,
then the rest of the suite in its default order. Under `pytest -x` the
verdict cannot change — every file still runs unless one fails, exactly as
before — only the time to the first failure does. Survivors pay the full
suite either way, so the gain is bounded by the killed share.

No coverage tracing is needed: the mutation baseline is the coverage map.

`MapPrioritizer` (round 113) uses a real per-test-file coverage map instead
(`coverage.collect(by_file=True)`): the files whose tests executed the
mutated line run first, cheapest file first, and — `subset=True` — ONLY
those files run. A test file that never executes the mutated line cannot
observe the mutation (the mutant differs from the original at that node
alone), so a green covering subset is a `survived` verdict by construction;
the only way it is wrong is an instrument error (a line event attributed
outside `[line, end_line]` — round 107 saw 2 of 267), which the campaign's
recheck stage measures on a seeded sample re-run under the full suite.
Mutants on a line no file covers run the full suite: they are the
instrument's blind spot and cost nothing extra (there are few).
"""
import json
import os
import re

FAILED_RE = re.compile(r"FAILED (tests/[\w./-]+?\.py)::")


def killed_by(detail):
    """Test file (relative, e.g. `tests/test_v09.py`) named by the first
    FAILED line of a mutant's detail, or None."""
    m = FAILED_RE.search(detail or "")
    return m.group(1) if m else None


def learn(records):
    """[(path, line, op, killed_by_file)] from mutant dicts (JSON or partial
    lines) whose status is killed and whose detail names a file."""
    out = []
    for d in records:
        if d.get("status") != "killed":
            continue
        f = killed_by(d.get("detail", ""))
        if f:
            out.append((d["path"], int(d["line"]), d.get("op", ""), f))
    return out


def load_records(path):
    """A mutation JSON (`{"mutants": [...]}`) or a `.partial.jsonl`."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if path.endswith(".jsonl"):
        return [json.loads(l) for l in text.splitlines() if l.strip()]
    data = json.loads(text)
    return data["mutants"] if isinstance(data, dict) else data


def default_test_files(root, tests_dir="tests"):
    d = os.path.join(root, tests_dir)
    return sorted(os.path.join(tests_dir, f) for f in os.listdir(d)
                  if f.startswith("test_") and f.endswith(".py"))


class Prioritizer(object):
    def __init__(self, learned, test_files, k=3, exclude_id=None):
        self.learned = list(learned)
        self.test_files = list(test_files)
        self.k = k
        self.exclude_id = exclude_id       # leave-one-out in the benchmark

    def order_for(self, path, line, op=""):
        """Learned files (nearest line first, same-op ties preferred, deduped)
        followed by every other test file in default order."""
        cands = [(abs(l - line), 0 if o == op else 1, i, f)
                 for i, (p, l, o, f) in enumerate(self.learned) if p == path]
        cands.sort()
        first = []
        for _, _, _, f in cands:
            if f not in first and f in self.test_files:
                first.append(f)
            if len(first) >= self.k:
                break
        return first + [f for f in self.test_files if f not in first]

    def cmd_for(self, mutant, base_cmd):
        """`base_cmd` ends with the tests directory (`... tests`); replace
        that last argument by the ordered file list."""
        order = self.order_for(mutant.path, mutant.lineno, mutant.op)
        return list(base_cmd[:-1]) + order

    @classmethod
    def from_file(cls, path, root, k=3):
        return cls(learn(load_records(path)), default_test_files(root), k=k)


class MapPrioritizer(object):
    """Order and (optionally) restrict the suite from a by-file coverage
    map (`coverage.collect(by_file=True)` / `coverage.load`)."""

    def __init__(self, cov_map, test_files, subset=True, durations=None, root=None,
                 require_fresh=True):
        from . import coverage as CV
        self.CV = CV
        self.map = cov_map
        self.test_files = list(test_files)
        self.durations = dict(durations if durations is not None else (cov_map.get("_durations") or {}))
        self.exclude_id = None
        self.stale = []
        # A by-file map is LINE-KEYED: reusing one collected against an
        # earlier commit for `subset=True` RESTRICTION (not just ordering)
        # answers "which files cover line N" with whatever code used to be
        # at line N, silently. Round 113 (20/20 false survivors) and round
        # 137 (78/78) both paid a full-suite recheck for exactly this
        # reason. `require_fresh` (default on) auto-downgrades to
        # ordering-only the moment the target file's on-disk hash doesn't
        # match what the map recorded at collection time — a map with no
        # recorded hash at all (anything saved before this check existed)
        # counts as stale, since freshness was never verified for it either.
        if subset and require_fresh and root is not None:
            self.stale = CV.stale_files(cov_map, root)
        self.subset = subset and not self.stale

    @classmethod
    def from_file(cls, path, root, subset=True, require_fresh=True):
        from . import coverage as CV
        cov = CV.load(path)
        if not CV.is_by_file(cov):
            raise ValueError("%s is not a by-file coverage map (collect with by_file=True)" % path)
        return cls(cov, default_test_files(root), subset=subset, root=root, require_fresh=require_fresh)

    def _cost(self, f):
        return self.durations.get(f, float("inf"))

    def covering(self, path, line, end_line=None):
        """Test files (cheapest first) whose tests executed a line of the
        node. Import-time hits (`<collect>`) mean the line runs under EVERY
        file, so every file covers it."""
        hits = self.CV.covering_files(self.map, path, line, end_line)
        if any(k.startswith("<") for k in hits):
            return sorted(self.test_files, key=self._cost)
        files = [f for f in hits if f in self.test_files]
        return sorted(files, key=self._cost)

    def order_for(self, path, line, op="", end_line=None):
        first = self.covering(path, line, end_line)
        return first + sorted((f for f in self.test_files if f not in first), key=self._cost)

    def files_for(self, mutant):
        cov = self.covering(mutant.path, mutant.lineno, getattr(mutant, "end_lineno", None))
        if self.subset and cov:
            return cov, "subset"
        rest = sorted((f for f in self.test_files if f not in cov), key=self._cost)
        return cov + rest, "full"

    def cmd_for(self, mutant, base_cmd):
        files, _ = self.files_for(mutant)
        return list(base_cmd[:-1]) + files

    def basis_for(self, mutant):
        files, basis = self.files_for(mutant)
        return {"basis": basis, "files_run": len(files)}

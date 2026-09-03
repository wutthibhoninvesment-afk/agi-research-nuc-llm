"""A RECORDED, resumable view of the `whence_slow` test tier (round 469, harness A).

Why this exists
---------------
`languages/whence/run_tests_fast.sh` — the suite the driver runs as its
per-round `whence-health-check` — ends in `-m "not whence_slow"`. That
deselects 103 test nodes across 28 files, and **nothing else runs them.**

That sentence has been in this program's carried list for a long time and
under several wordings: `state/research-state.md:15424` ("The `whence_slow`
tier is where regressions hide, and nothing samples it"), and again at
`:17420`, `:17640` and `:17983` as "the unsampled `whence_slow` tier",
owner harness(A). Round 469 measured what "nothing" meant:

  * No module under `harness/` selects tests by the marker. `slowtier.py`,
    the program's one recorded-tier mechanism, filters on the literal
    filename prefix `test_swe_` and is about `harness/tests/` only.
  * `harness/pristine_check.py` defines a `whence-slow` SUITE, and it is the
    only named runner the tier has ever had. `run_driver.sh` invokes
    `pristine_check.py` on **no** code path, so that runner is manual.
  * It has been run **twice**, both times on 2026-08-30, both recorded in
    `state/pristine-check-ledger.jsonl` (54 selected then 70 selected). The
    tier has grown to 103 selected since, and 4 days of language rounds have
    edited the subject underneath both readings.

So the tier's recall against the current checkout was 0 of 28 units, and —
this is the part that made it worth a round rather than a note — **there was
no artefact in which that 0 could be written down.** `slowtier.py`'s whole
contribution in round 341 was not running tests; it was making "what is NOT
covered" visible instead of indistinguishable from green. The `whence_slow`
tier had no such artefact at all.

What this module provides
-------------------------
The same three things, for this tier: an append-only ledger
(`state/whence-slow-ledger.jsonl`) of per-unit outcomes stamped with the
digests they were computed against, a fail-closed classifier, and a planner
that spends a bounded budget worst-evidence-first.

What it does NOT do is copy `slowtier.py`, because a faithful copy would be
wrong here in one specific way, and the way is worth stating.

The collapsed-tree problem
--------------------------
`slowtier.py` gets two INDEPENDENT staleness rules — `checkout_digest` over
`languages/whence/` (the subject) and `dep_digests` over the test's `swe.*`
import closure (the harness) — for free, because its test tree
(`harness/tests/`) and its subject tree (`languages/whence/`) are DISJOINT.
Here they are not: `languages/whence/tests/` is inside `languages/whence/`.
Digest the tree the way `slowtier.checkout_digest` does and every commit
that touches ANY `.py` or `.lang` file under it — including a test file
belonging to some other unit, including a test file this unit cannot import
— invalidates all 28 units at once. On a tree that a language round edits
every sixth round, that is a ledger that can never accumulate, which is the
one failure mode the module exists to prevent.

The split is therefore by ROLE inside the one tree, and there are exactly two
roles:

  * **subject** — every `.py`/`.lang` under `languages/whence/` EXCEPT
    `tests/`. The interpreter, `run.py`, the top-level tools, `examples/`,
    `bench/`. `subject_digest()`.
  * **deps** — the unit's own test file, its TRANSITIVE import closure
    *within* `tests/`, plus `tests/conftest.py`, `tests/__init__.py` and
    `pytest.ini`. `dep_digests()`.

The closure is not decoration. `languages/whence/tests/` cross-imports
heavily — `test_v11.py` imports `test_v10.py` which imports `test_v09.py`,
and `test_v38.py` imports `tests.test_parse_error_differential` — so "digest
the unit's own file" would be fail-OPEN: an edit to `test_v09.py`'s shared
`run()` helper would leave six other units reading `fresh_pass`. Round 469
measured the closure rather than asserting it (`python3
harness/whenceslow.py units --deps`).

`pytest.ini` is in the deps set for round 349's reason: it is what stops
pytest from parsing the untracked gateway `pyproject.toml`, so an edit to it
can decide whether the suite runs at all.

The unit is the file's MARKED tests, never the whole file
--------------------------------------------------------
A unit runs `-m whence_slow tests/<file>`, not `tests/<file>`. The fast tier
already runs every unmarked test in that file every round; a whole-file unit
would re-run them at this tier's price and would make its ledger row a claim
about tests that already have a fresher one. `slowtier.py` needed round 433
to introduce a `[light]`/`[heavy]` split for the same reason; here the split
is the marker and it is there from the start.

Discovery is by AST, cross-checked against pytest, and they disagree
-------------------------------------------------------------------
Three ways of counting this tier give three answers, all correct about
different things, measured round 469 at HEAD:

    grep -c '@pytest.mark.whence_slow'   104
    AST, decorators on def/class nodes   102
    pytest --collect-only -m whence_slow 103

104 - 2 + 1 = 103. Two of the grep hits are PROSE inside `test_tiering.py`'s
own module docstring, and one AST-marked test
(`test_v10.py::test_three_way_on_big_examples`) is parametrized into two
nodes. A count that agreed with pytest's would have been the sum of two
offsetting errors.

`slow_tier_units()` therefore discovers by AST — cheap, offline,
deterministic, no subprocess in `status` — and `reconcile()` compares that
set against pytest's own collection. A file pytest collects marked tests
from and the AST does not see is a REGISTRY ERROR on that unit, not a silent
omission: the fail-closed direction is that a unit we cannot see is a unit
nobody is claiming anything about.

Fail-closed rules
-----------------
1. A unit with no ledger entry is `unknown`, never `pass`.
2. An entry whose `subject_digest` differs from the tree is `stale_subject`.
3. An entry whose `dep_digests` moved is `stale_deps`, and the moved paths
   are NAMED, not counted (round 341's item 2, kept).
4. An entry whose subject or deps moved WHILE THE RUN WAS IN FLIGHT is
   `raced` and can never be evidence whatever it reported. On this box a
   language round routinely edits `languages/whence/` while a harness round
   is running, and four of round 338's five slow-tier "failures" were that
   race rather than bugs.
5. An entry whose run did not FINISH (timeout, interrupt, internal error,
   nothing collected) is `incomplete` and narrows nothing — `slowtier.py`'s
   rule 10, restated. Only pytest return codes 0 and 1 mean a run reported.

Everything here is offline-testable: `run_slice` takes an injectable
`runner`, `status` takes injectable digests, and no test in
`harness/tests/test_whenceslow.py` shells out to pytest.
"""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HARNESS_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HARNESS_ROOT)
WHENCE_ROOT = os.path.join(REPO_ROOT, "languages", "whence")
TESTS_SUBDIR = "tests"
DEFAULT_LEDGER = os.path.join(REPO_ROOT, "state", "whence-slow-ledger.jsonl")

MARKER = "whence_slow"

#: Loaded by pytest for every file in `languages/whence/tests/`, plus the
#: config file that decides whether the suite can be collected at all
#: (round 349). Whence-root-relative, like every path this module stores.
_ALWAYS_LOADED = ("tests/conftest.py", "tests/__init__.py", "pytest.ini")

#: Same ignore list as `slowtier._IGNORED_DIRS`, and for the same reason: the
#: digest must not cover anything that merely RUNNING the suite regenerates,
#: or every run would invalidate its own predecessor.
_IGNORED_DIRS = ("__pycache__", ".pytest_cache", ".venv", "research-env",
                 ".git", "whence_lang.egg-info")

#: `.lang` is in the set for round 361's reason, which applies here with more
#: force than it did there: `examples/self_eval.lang` is an ~885-line guest
#: interpreter written in Whence, it is the thing several `whence_slow` tests
#: are ABOUT, and three commits in this repo change a `.lang` file and no
#: `.py` file at all.
_SOURCE_EXTS = (".py", ".lang")

WHOLE_TREE_NOTE = ("subject = every .py/.lang under languages/whence EXCEPT "
                   "tests/; tests/ is covered per-unit by dep_digests")


def _is_ignored(rel):
    parts = rel.replace(os.sep, "/").split("/")
    return any(p in _IGNORED_DIRS or p.endswith(".egg-info") for p in parts)


def _rel(root, full):
    return os.path.relpath(full, root).replace(os.sep, "/")


def _sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except (IOError, OSError):
        # A file that vanished is itself a change; record the fact rather
        # than raising, so a digest taken mid-edit is stable and wrong-looking
        # instead of crashing the caller.
        return "<unreadable>"


def subject_files(root=WHENCE_ROOT):
    """Whence-root-relative source paths of the SUBJECT half, sorted.

    Excludes `tests/` — see the module docstring's "collapsed-tree problem".
    That exclusion is the single riskiest decision in this module, so it is
    made in one function that `status`, `run_slice` and the tests all read,
    rather than inline at three call sites.
    """
    out = []
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in _IGNORED_DIRS and not d.endswith(".egg-info")]
        for n in sorted(names):
            if not n.endswith(_SOURCE_EXTS):
                continue
            rel = _rel(root, os.path.join(dirpath, n))
            if _is_ignored(rel) or rel.split("/")[0] == TESTS_SUBDIR:
                continue
            out.append(rel)
    return sorted(out)


def subject_digest(root=WHENCE_ROOT, files=None):
    """One stable digest over the subject half."""
    h = hashlib.sha256()
    for rel in (subject_files(root) if files is None else files):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(_sha(os.path.join(root, rel)).encode("utf-8"))
    return h.hexdigest()[:16]


# ------------------------------------------------------------------- units --

def _module_marked(tree):
    """True when a module-level `pytestmark` applies the marker to EVERY test
    in the file.

    Round 470, and it was a live fail-open rather than a hypothetical. That
    round wrote `languages/whence/tests/test_testcorpus_suite_census.py` with
    `pytestmark = pytest.mark.whence_slow` at module level — the ordinary
    pytest spelling for "the whole file is in this tier". `pytest -m
    whence_slow` collected all 11 of its tests. This function's AST scan,
    which looks only at DECORATORS, returned `[]`, so `slow_tier_units()`
    reported the tier unchanged at 27 units and the file would never have
    been scheduled, never have produced a ledger row, and never have shown up
    in the 0-vs-100% recall number round 469 built the tier to publish.

    A tier whose membership is discovered by one spelling of a two-spelling
    construct is a tier that silently loses units. Both forms are read now;
    `pytestmark` wins over the decorators because it applies to everything.

    Handles the three shapes pytest itself accepts: a bare mark, a list, and
    a tuple.
    """
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark"
                   for t in node.targets):
            continue
        v = node.value
        parts = v.elts if isinstance(v, (ast.List, ast.Tuple)) else [v]
        for part in parts:
            try:
                text = ast.unparse(part)
            except Exception:                   # pragma: no cover - py<3.9
                text = ""
            if MARKER in text:
                return True
    return False


def marked_tests(path):
    """Names of top-level `def`/`class` nodes carrying the marker, by AST.

    Returns None when the file cannot be parsed — a caller must treat that as
    "this file's membership is unknown", never as "this file has no marks".

    Round 470: a module-level `pytestmark` marks EVERY test in the file, and
    is read here for the reason `_module_marked`'s docstring gives.
    """
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (IOError, OSError, SyntaxError, UnicodeDecodeError):
        return None
    found = []
    whole_file = _module_marked(tree)

    def visit(node, prefix=""):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                marked = whole_file and prefix == "" and (
                    child.name.startswith("test") or
                    isinstance(child, ast.ClassDef))
                for dec in child.decorator_list:
                    try:
                        text = ast.unparse(dec)
                    except Exception:           # pragma: no cover - py<3.9
                        text = ""
                    if MARKER in text:
                        marked = True
                        break
                if marked:
                    found.append(prefix + child.name)
                if isinstance(child, ast.ClassDef):
                    visit(child, prefix + child.name + "::")
    visit(tree)
    return sorted(found)


def tests_dir(root=WHENCE_ROOT):
    return os.path.join(root, TESTS_SUBDIR)


def slow_tier_units(root=WHENCE_ROOT):
    """One unit per test FILE that holds at least one marked node.

    A unit's `tests` are named, never merely counted — after this round's
    104/102/103 discrepancy, a count of this tier is exactly the thing not to
    trust.
    """
    d = tests_dir(root)
    units = []
    try:
        names = sorted(os.listdir(d))
    except (IOError, OSError):
        return units
    for n in names:
        if not (n.startswith("test_") and n.endswith(".py")):
            continue
        marks = marked_tests(os.path.join(d, n))
        if marks is None:
            units.append({"id": n, "file": n, "tests": [],
                          "registry_error": "unparsable: membership unknown"})
        elif marks:
            units.append({"id": n, "file": n, "tests": marks,
                          "registry_error": ""})
    return units


# ------------------------------------------------------------- dep closure --

def _test_imports(text):
    """Names this test module imports from ELSEWHERE IN `tests/`.

    Two spellings both occur in this tree and both are handled:
    `from test_v09 import run` (the dir is on `sys.path[0]` under pytest's
    rootdir insertion) and `from tests.test_parse_error_differential import
    ...`. Anything that is not a `test_*` module is subject-half and is
    covered by `subject_digest`, so it is deliberately dropped here.
    """
    out = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out

    def take(mod):
        if not mod:
            return
        head = mod.split(".")
        if head[0] == "tests" and len(head) > 1:
            head = head[1:]
        if head[0].startswith("test_"):
            out.add(head[0] + ".py")

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            take(node.module)
        elif isinstance(node, ast.Import):
            for a in node.names:
                take(a.name)
    return out


def dep_closure(test_file, root=WHENCE_ROOT):
    """Whence-root-relative paths whose contents can change this unit's
    outcome without changing the subject: the file, its transitive
    intra-`tests/` import closure, and `_ALWAYS_LOADED`.

    Transitive on purpose. `test_v11.py` imports `test_v10.py` imports
    `test_v09.py`; stopping at depth 1 would leave `test_v11`'s row green
    across an edit to the `run()` helper it actually calls.
    """
    d = tests_dir(root)
    seen, stack = set(), [test_file]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        p = os.path.join(d, cur)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                text = f.read()
        except (IOError, OSError, UnicodeDecodeError):
            continue
        for nxt in _test_imports(text):
            if nxt not in seen:
                stack.append(nxt)
    rels = set(TESTS_SUBDIR + "/" + n for n in seen)
    rels.update(_ALWAYS_LOADED)
    return sorted(rels)


def dep_digests(test_file, root=WHENCE_ROOT, deps=None):
    deps = dep_closure(test_file, root) if deps is None else deps
    return dict((rel, _sha(os.path.join(root, rel))) for rel in deps)


def moved_deps(entry, current):
    """Dep paths whose digest differs, NAMED. Includes paths that appeared or
    vanished, because a new intra-`tests/` import is itself a change in what
    this unit depends on."""
    was = (entry or {}).get("dep_digests")
    if was is None:
        return []
    keys = set(was) | set(current or {})
    return sorted(k for k in keys if was.get(k) != (current or {}).get(k))


# ------------------------------------------------------------------ ledger --

def append_entry(path, entry):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def read_entries(path=DEFAULT_LEDGER):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                # A torn line is not evidence and must not stop the reader:
                # the ledger is appended to by a process another round can
                # kill mid-write.
                continue
    return out


def latest_by_unit(entries, units):
    """Most recent entry per unit id, by `finished_at`.

    No inheritance rule, deliberately, and this is a real difference from
    `slowtier.latest_by_unit`. There, a whole-file PASS is evidence for each
    sub-unit because the run is a strict superset. Here every unit IS the
    file's marked tests, so no run is a superset of another and there is
    nothing to inherit. Inventing an inheritance rule would be inventing
    coverage.
    """
    best = {}
    for u in units:
        cur = None
        for e in entries:
            if e.get("unit") != u["id"]:
                continue
            if cur is None or (e.get("finished_at") or 0) >= (cur.get("finished_at") or 0):
                cur = e
        best[u["id"]] = cur
    return best


# ---------------------------------------------------------------- classify --

#: pytest return codes meaning THE RUN FINISHED AND REPORTED. 5 (nothing
#: collected) is excluded on purpose: for a unit built from marked tests,
#: collecting nothing means the marks moved, not that the tests passed.
_COMPLETED_RETURNCODES = (0, 1)

CONCLUSIVE = ("fresh_pass", "fresh_fail")
FAILING = ("fresh_fail",)


def classify(entry, subj, cur_deps=None):
    """The fail-closed state machine. See the module docstring's rules 1-5."""
    if entry is None:
        return "unknown"
    if not entry.get("subject_stable", False) or not entry.get("deps_stable", True):
        return "raced"
    if not entry.get("completed", False):
        return "incomplete"
    if entry.get("subject_digest") != subj:
        return "stale_subject"
    if cur_deps is not None:
        if entry.get("dep_digests") is None:
            return "unstamped"
        if moved_deps(entry, cur_deps):
            return "stale_deps"
    if entry.get("outcome") == "passed":
        return "fresh_pass"
    if entry.get("outcome") == "failed":
        return "fresh_fail"
    return "unknown"


def recorded_failing_but_stale(row):
    """Round 385's rule, ported: a row whose LAST RECORDED run was red but
    whose state is inconclusive. It is not counted in `n_failing` — a red
    measured against a tree that has moved is not evidence about this tree —
    but rendering it as the bare word `stale_subject` reads exactly like a
    stale PASS, which is the one thing it is not."""
    return (row.get("outcome") == "failed"
            and row.get("state") not in CONCLUSIVE)


def status(ledger_path=DEFAULT_LEDGER, root=WHENCE_ROOT, subj=None,
           units=None, entries=None, collected=None):
    """The whole view. Every argument is injectable so the tests need no repo.

    `collected` is an optional `{file: [node ids]}` from pytest's own
    collection (see `reconcile`). When given, a file pytest collects marked
    tests from that the AST scan did not see becomes a unit with a
    `registry_error`, so it is in the denominator and can never be conclusive.
    """
    subj = subject_digest(root) if subj is None else subj
    units = slow_tier_units(root) if units is None else units
    if collected is not None:
        units = reconcile(units, collected)
    entries = read_entries(ledger_path) if entries is None else entries
    best = latest_by_unit(entries, units)
    rows = []
    for u in units:
        e = best.get(u["id"])
        cur = dep_digests(u["file"], root)
        state = classify(e, subj, cur)
        if u.get("registry_error") and state in CONCLUSIVE:
            # A unit we cannot enumerate may not be counted as covered,
            # whatever its last run said.
            state = "registry_error"
        rows.append({
            "unit": u["id"],
            "file": u["file"],
            "n_tests": len(u.get("tests") or []),
            "tests": list(u.get("tests") or []),
            "registry_error": u.get("registry_error", ""),
            "state": state,
            "outcome": (e or {}).get("outcome"),
            "finished_at": (e or {}).get("finished_at"),
            "seconds": (e or {}).get("seconds"),
            "n_deps": len(cur),
            "moved_deps": moved_deps(e, cur) if e is not None else [],
        })
    covered = [r for r in rows if r["state"] in CONCLUSIVE]
    return {
        "subject_digest": subj,
        "rows": rows,
        "n_units": len(rows),
        "n_tests": sum(r["n_tests"] for r in rows),
        "n_registry_errors": len([r for r in rows if r["registry_error"]]),
        "n_conclusive": len(covered),
        "n_failing": len([r for r in rows if r["state"] in FAILING]),
        "n_recorded_failing_stale":
            len([r for r in rows if recorded_failing_but_stale(r)]),
        # Round 339's rule: a checker reports its OWN recall, so the gap
        # stays visible instead of being indistinguishable from green.
        "coverage": (float(len(covered)) / len(rows)) if rows else 0.0,
    }


# --------------------------------------------------------------- reconcile --

def collect_units(root=WHENCE_ROOT, runner=None, timeout_s=300):
    """`{file: [node id, ...]}` from pytest's own collection — ground truth.

    Deliberately NOT what `slow_tier_units` uses: it costs a subprocess, and
    `status` is echoed by cheap callers. It is the cross-check, not the
    source.
    """
    argv = [sys.executable, "-m", "pytest", "-c", "pytest.ini", "-q",
            "-p", "no:randomly", "-m", MARKER, TESTS_SUBDIR + "/",
            "--collect-only"]
    if runner is None:
        p = subprocess.run(argv, cwd=root, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout_s)
        text = p.stdout.decode("utf-8", "replace")
    else:
        text = runner(argv)
    out = {}
    for line in text.split("\n"):
        line = line.strip()
        if "::" not in line or not line.startswith(TESTS_SUBDIR + "/"):
            continue
        f = line.split("::")[0].split("/")[-1]
        out.setdefault(f, []).append(line)
    return out


def reconcile(units, collected):
    """AST units + a `registry_error` on every file pytest collects and the
    AST scan missed.

    The fail-closed direction: an unseen file becomes a unit in the
    DENOMINATOR that can never be conclusive, rather than a file quietly
    outside the tier. A file the AST sees and pytest does not is left alone —
    it is over-claiming coverage of nothing, which costs recall and not
    correctness.
    """
    out = [dict(u) for u in units]
    known = set(u["file"] for u in out)
    for f in sorted(collected):
        if f in known:
            continue
        out.append({"id": f, "file": f, "tests": [],
                    "registry_error":
                        "pytest collects %d marked node(s) here and the AST "
                        "scan sees none" % len(collected[f])})
    return sorted(out, key=lambda u: u["id"])


# ------------------------------------------------------------------- plan ---

def _size_prior(unit_file, root=WHENCE_ROOT, row=None):
    """Bytes of the test file scaled to a fraction of a second — a TIE-break
    among never-measured units only, never a timing figure. Scaled by the
    unit's share of the file's marked tests is NOT done here: every unit
    already IS the marked share."""
    try:
        return os.path.getsize(os.path.join(tests_dir(root), unit_file)) / 1e6
    except (IOError, OSError):
        return 0.0


def plan(st, budget_s, default_s=120.0, root=WHENCE_ROOT):
    """Units to run next, in order, inside `budget_s`.

    Order: never-conclusive first, then last-recorded-RED, then oldest run,
    then cheapest. A unit whose estimate alone exceeds the budget is still
    returned as the SOLE entry when nothing else fits — otherwise a unit
    slower than every budget would never run again, which is the silent
    truncation this module exists to prevent, and it would land on exactly
    the units most worth covering.

    `default_s` is 120, not `slowtier`'s 300: this tier's recorded per-test
    rate is 5.4-7.3 s (`state/pristine-check-ledger.jsonl`) and its median
    unit holds 2 marked tests, so 300 would make the planner refuse to pick
    a second unmeasured unit inside any budget a round grants.
    """
    def key(r):
        conclusive = r["state"] in CONCLUSIVE
        red_first = 0 if recorded_failing_but_stale(r) else 1
        est = r.get("seconds") or (default_s + _size_prior(r["file"], root))
        return (1 if conclusive else 0, red_first, r["finished_at"] or 0,
                est, r["unit"])

    picked, spent = [], 0.0
    for r in sorted(st["rows"], key=key):
        est = r.get("seconds") or default_s
        if picked and spent + est > budget_s:
            continue
        picked.append(r["unit"])
        spent += est
        if spent >= budget_s:
            break
    return picked


# -------------------------------------------------------------------- run ---

def unit_argv(unit_file, python=None):
    """The exact command a unit runs. Split out of `pytest_runner` so a test
    can assert on it without a subprocess — the two flags below are the ones
    that make this a UNIT and make it runnable at all, and both have a
    recorded history of being dropped.

    `-c pytest.ini` is load-bearing, not tidiness: without it pytest scans
    the rootdir for config and parses the UNTRACKED gateway `pyproject.toml`,
    which took all 1043 fast-tier tests down in round 348. `-m whence_slow`
    is what makes this the file's MARKED tests rather than the whole file,
    whose unmarked half the fast tier already runs every round.
    """
    return [python or sys.executable, "-m", "pytest", "-c", "pytest.ini",
            "-q", "-p", "no:randomly", "-m", MARKER,
            TESTS_SUBDIR + "/" + unit_file]


def pytest_runner(unit_file, root=WHENCE_ROOT, timeout_s=3000):
    """One pytest process per unit, cwd at the whence root.

    `PYTHONDONTWRITEBYTECODE` is round 340's rule — a `.pyc` whose cache key
    (size, mtime truncated to the second) collides with a since-edited source
    makes a run test the wrong bytecode, and this tree is edited by other
    rounds between slices.
    """
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    argv = unit_argv(unit_file)
    try:
        p = subprocess.Popen(argv, cwd=root, env=env,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        out, _ = p.communicate(timeout=timeout_s)
        rc, timed_out = p.returncode, False
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
        rc, timed_out = -9, True
    text = (out or b"").decode("utf-8", "replace")
    return {"returncode": rc, "timed_out": timed_out, "tail": text[-800:]}


def run_slice(unit_ids, ledger_path=DEFAULT_LEDGER, root=WHENCE_ROOT,
              runner=pytest_runner, clock=time.time, log=None):
    """Run each unit, appending exactly one ledger entry apiece.

    Both digests are read BEFORE and AFTER each unit. If either moved, the
    entry is stamped unstable and `classify` can never count it (rule 4). The
    deps are RE-SCANNED after the run rather than reusing the closure
    computed before it, because an import added mid-run changes WHICH files
    matter and that is itself the race.
    """
    log = log or (lambda s: None)
    written = []
    for uid in unit_ids:
        subj_before = subject_digest(root)
        deps_before = dep_digests(uid, root)
        t0 = clock()
        r = runner(uid)
        t1 = clock()
        subj_after = subject_digest(root)
        deps_after = dep_digests(uid, root)
        completed = (not r.get("timed_out")
                     and r.get("returncode") in _COMPLETED_RETURNCODES)
        outcome = ("timeout" if r.get("timed_out")
                   else "passed" if r.get("returncode") == 0
                   else "failed" if r.get("returncode") == 1
                   else "error")
        entry = {
            "unit": uid,
            "file": uid,
            "outcome": outcome,
            "completed": completed,
            "returncode": r.get("returncode"),
            "seconds": round(t1 - t0, 2),
            "finished_at": t1,
            "subject_digest": subj_before,
            "subject_digest_after": subj_after,
            "subject_stable": subj_before == subj_after,
            "dep_digests": deps_before,
            "deps_stable": deps_before == deps_after,
            "schema": 1,
            "tail": (r.get("tail") or "")[-800:],
        }
        append_entry(ledger_path, entry)
        written.append(entry)
        flags = ("" if entry["subject_stable"] else "  [SUBJECT CHANGED MID-RUN]") \
            + ("" if entry["deps_stable"] else "  [DEPS CHANGED MID-RUN]") \
            + ("" if completed else "  [RUN DID NOT COMPLETE]")
        log("%-42s %-8s %7.1fs%s" % (uid, outcome, entry["seconds"], flags))
    return written


# ----------------------------------------------------------------- replay ---

def commit_invalidations(commits, closures, root=WHENCE_ROOT):
    """`[set of unit ids invalidated]`, one per commit, in the order given.

    `commits` is `[[whence-root-relative path, ...], ...]` — what each commit
    touched. A commit touching any non-`tests/` `.py`/`.lang` source moves the
    subject digest and invalidates EVERY unit; a commit touching only test
    sources invalidates the units whose dep closure contains one of them.
    Separated from `git` so the replay is testable with no repository.
    """
    out = []
    for files in commits:
        src = [f for f in files
               if f.endswith(_SOURCE_EXTS) and not _is_ignored(f)]
        if not src:
            out.append(set())
            continue
        if [f for f in src if f.split("/")[0] != TESTS_SUBDIR]:
            out.append(set(closures))
            continue
        touched = set(src)
        out.append(set(u for u, c in closures.items() if c & touched))
    return out


def replay(costs, invalidations, budget_s, default_s=120.0, units=None):
    """What per-round recall a given budget WOULD have produced.

    The point is to price a per-round spend against the project's real churn
    BEFORE wiring it, rather than after N rounds of paying for it. The order
    is the driver's own: a round commits, and the slice runs after that
    round's session has exited, so each step applies the commit's
    invalidation and THEN spends the budget.

    Returns `{"series": [recall after each round], "mean": float,
    "spent_s": [...], "final": float}`. Deliberately optimistic in one
    direction and pessimistic in none: it assumes every run passes and every
    unit costs what it last cost, so a real slice can only do worse.
    """
    units = sorted(costs) if units is None else list(units)
    covered = set()
    series, spent_all = [], []
    for inval in invalidations:
        covered -= set(inval)
        # worst-evidence-first, cheapest among the uncovered: the same order
        # `plan` uses once every row is `unknown`.
        todo = sorted((u for u in units if u not in covered),
                      key=lambda u: (costs.get(u, default_s), u))
        spent = 0.0
        for u in todo:
            est = costs.get(u, default_s)
            if spent and spent + est > budget_s:
                continue
            covered.add(u)
            spent += est
            if spent >= budget_s:
                break
        spent_all.append(round(spent, 1))
        series.append(len(covered) / float(len(units)) if units else 0.0)
    return {"series": series, "spent_s": spent_all,
            "mean": (sum(series) / len(series)) if series else 0.0,
            "final": series[-1] if series else 0.0}


def ledger_costs(ledger_path=DEFAULT_LEDGER, units=None):
    """`{unit: last measured seconds}` from the ledger."""
    units = slow_tier_units() if units is None else units
    best = latest_by_unit(read_entries(ledger_path), units)
    return dict((u["id"], (best.get(u["id"]) or {}).get("seconds"))
                for u in units
                if (best.get(u["id"]) or {}).get("seconds") is not None)


_ROUND_RE = re.compile(r"round\s+(\d+)", re.I)


def group_by_round(commits, subjects):
    """Merge consecutive commits belonging to one ROUND into one change set.

    This is not cosmetic and it is the difference between a right and a wrong
    replay number. The driver runs ONE slice per round, and a round commits
    several times — round 468 committed four times. Replaying one slice per
    COMMIT hands the planner one budget per commit and overstates recall by
    the mean commits-per-round. Rounds are identified by the `round N`
    substring every round's own commit subjects carry; a commit whose subject
    names no round (a driver ledger append, a merge) joins the group before
    it, because it happened inside that round's window.
    """
    groups, tags = [], []
    for files, subject in zip(commits, subjects):
        m = _ROUND_RE.search(subject or "")
        tag = m.group(1) if m else None
        if groups and (tag is None or tag == tags[-1]):
            groups[-1] = groups[-1] + list(files)
        else:
            groups.append(list(files))
            tags.append(tag)
    return groups, tags


def git_commits(n=120, root=WHENCE_ROOT, runner=None):
    """`(changes, subjects)` for the last `n` commits touching the whence
    tree, oldest LAST — each change set a list of whence-root-relative
    paths."""
    prefix = os.path.relpath(root, REPO_ROOT).replace(os.sep, "/") + "/"

    def sh(args):
        if runner is not None:
            return runner(args)
        return subprocess.run(args, cwd=REPO_ROOT, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL).stdout.decode(
                                  "utf-8", "replace")

    log = sh(["git", "log", "-n", str(n), "--format=%H%x00%s", "--",
              prefix.rstrip("/")])
    pairs = [l.split("\x00", 1) for l in log.split("\n") if "\x00" in l]
    out, subjects = [], []
    for sha, subject in reversed(pairs):          # oldest first
        files = sh(["git", "show", "--pretty=", "--name-only", sha]).split("\n")
        out.append([f[len(prefix):] for f in files if f.startswith(prefix)])
        subjects.append(subject)
    return out, subjects


# ----------------------------------------------------------------- report ---

def report_text(st):
    # "marked (AST)", never "tests": round 469 measured three different
    # counts of this tier (grep 104, AST 102, pytest 103) and the whole
    # reason this line names its source is that two of them are wrong.
    out = ["whence slow tier: %d units / %d marked (AST), %d conclusive "
           "against subject %s (%.0f%% recall), %d failing"
           % (st["n_units"], st["n_tests"], st["n_conclusive"],
              st["subject_digest"], 100.0 * st["coverage"], st["n_failing"])]
    if st["n_registry_errors"]:
        out.append("REGISTRY ERROR on %d unit(s) — see rows"
                   % st["n_registry_errors"])
    if st["n_recorded_failing_stale"]:
        out.append("NOTE: %d unit(s) LAST RAN RED but against a tree that has "
                   "moved; not counted as failing, and the first thing a "
                   "slice should re-run" % st["n_recorded_failing_stale"])
    gap = st["n_units"] - st["n_conclusive"]
    if gap:
        out.append("NOTE: %d unit(s) are NOT evidence about this checkout"
                   % gap)
    for r in sorted(st["rows"], key=lambda r: (r["state"] in CONCLUSIVE,
                                               r["unit"])):
        extra = ""
        if r["moved_deps"]:
            extra = "  moved: " + ",".join(r["moved_deps"][:3]) \
                + ("…" if len(r["moved_deps"]) > 3 else "")
        if r["registry_error"]:
            extra += "  ERROR: " + r["registry_error"]
        out.append("  %-42s %-14s %3d tests  %s%s"
                   % (r["unit"], r["state"], r["n_tests"],
                      ("%.1fs" % r["seconds"]) if r["seconds"] else "-", extra))
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    rest = argv[1:]

    def opt(name, default=None):
        if name in rest:
            return rest[rest.index(name) + 1]
        return default

    if cmd == "units":
        units = slow_tier_units()
        for u in units:
            line = "%-42s %3d marked" % (u["id"], len(u["tests"]))
            if "--deps" in rest:
                deps = dep_closure(u["file"])
                line += "  deps=%d: %s" % (len(deps), ",".join(deps))
            if u["registry_error"]:
                line += "  ERROR: " + u["registry_error"]
            print(line)
        print("%d units, %d marked nodes (AST)"
              % (len(units), sum(len(u["tests"]) for u in units)))
        return 0

    if cmd == "verify":
        units = slow_tier_units()
        collected = collect_units()
        ast_n = sum(len(u["tests"]) for u in units)
        col_n = sum(len(v) for v in collected.values())
        merged = reconcile(units, collected)
        errs = [u for u in merged if u.get("registry_error")]
        print("AST: %d units / %d marked nodes" % (len(units), ast_n))
        print("pytest --collect-only -m %s: %d files / %d nodes"
              % (MARKER, len(collected), col_n))
        for u in units:
            got = len(collected.get(u["file"], []))
            if got != len(u["tests"]):
                print("  DIFFERS %-38s AST %d, pytest %d"
                      % (u["file"], len(u["tests"]), got))
        for u in errs:
            print("  ERROR   %-38s %s" % (u["file"], u["registry_error"]))
        return 1 if errs else 0

    if cmd == "replay":
        units = slow_tier_units()
        closures = dict((u["id"], set(dep_closure(u["file"]))) for u in units)
        commits, subjects = git_commits(int(opt("--commits", "120")))
        if "--per-commit" in rest:
            groups, tags = commits, [None] * len(commits)
        else:
            groups, tags = group_by_round(commits, subjects)
        inval = commit_invalidations(groups, closures)
        print("replaying %d commits as %d round(s) over %d units, costs from "
              "%d ledger rows"
              % (len(commits), len(groups), len(units),
                 len(ledger_costs(units=units))))
        for b in [float(x) for x in opt("--budgets", "60,120,240,480").split(",")]:
            r = replay(ledger_costs(units=units), inval, b,
                       units=[u["id"] for u in units])
            print("  budget %6.0fs -> mean recall %5.1f%%   final %5.1f%%   "
                  "mean spend %5.1fs" % (b, 100 * r["mean"], 100 * r["final"],
                                         sum(r["spent_s"]) / len(r["spent_s"])))
        return 0

    if cmd == "plan":
        st = status()
        print("\n".join(plan(st, float(opt("--budget-s", "240")))))
        return 0

    if cmd == "run":
        budget = float(opt("--budget-s", "240"))
        st = status()
        picked = plan(st, budget)
        if not picked:
            print("whence-slow slice: nothing to run")
            return 0
        print("whence-slow slice: %d unit(s), budget %.0fs" % (len(picked), budget))
        written = run_slice(picked, log=lambda s: print("  " + s))
        bad = [e for e in written if e["outcome"] != "passed"]
        return 1 if bad else 0

    if cmd == "status":
        st = status()
        print(report_text(st))
        return 1 if st["n_failing"] else 0

    print(__doc__.strip().split("\n")[0])
    print("usage: whenceslow.py [status|units|verify|plan|run|replay] "
          "[--budget-s N] [--commits N] [--budgets a,b,c] [--deps]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""A RECORDED, resumable view of the slow test tier (round 341, SWE-loop D).

Why this exists
---------------
`harness/tests/conftest.py` splits the suite into a fast core tier and a slow
`swe_slow` tier (every `test_swe_*.py`), and `run_tests_fast.sh` — the health
check the driver runs every round — deselects the slow tier entirely. That
was the right call for round 223's problem (six consecutive rounds could not
finish a synchronous full run inside a round's budget) but it left a
coverage gap of exactly the shape round 283 named for `git_committed`: **a
green round report is not evidence the slow tier passes.** Round 338 found
five real failures sitting in it, and found them only because round 336's
backgrounded `nohup` run happened to still be alive for someone to read.

The standing `nohup ... &` convention is not a fix for that: it produces an
orphaned process whose output nobody reads, on a ONE-CPU box where the full
tier takes 76 minutes against a 55-minute round timeout. Worse — see
`checkout_digest` below — it produces results computed against a checkout
that a LATER round is concurrently editing.

What this module provides
-------------------------
An append-only ledger (`state/slow-tier-ledger.jsonl`) of per-file outcomes,
each stamped with the digest of the whence checkout it was computed against,
plus a planner that spends a bounded time budget on whatever is least
covered. Over several rounds the tier gets covered incrementally, and — the
part that actually matters — **what is NOT covered is visible**, instead of
being indistinguishable from green.

Fail-closed rules, all three load-bearing (cf. round 340's `gap_continuity`):
  1. A file with no ledger entry is `unknown`, never `pass`. Absence of
     evidence is recorded as absence of evidence.
  2. An entry whose `checkout_digest` differs from the current tree is
     `stale_checkout`. Its pass said something true about a tree that no
     longer exists.
  3. An entry whose digest CHANGED WHILE THE RUN WAS IN FLIGHT
     (`checkout_stable: false`) can never be fresh, whatever it reported.
     This is round 341's own finding made mechanical: four of round 338's
     five failures are caused by exactly that race, and a PASS produced
     under it is no more trustworthy than the FAIL.
  4-6. (round 343) The same three rules again for the HARNESS half, per
     file: `dep_digests` over the test's own transitive `swe.*` closure,
     `stale_harness` when one moved, `unstamped` for an entry written before
     the closure was recorded at all, and `harness_stable: false` for a
     closure that moved mid-run.
  7-9. (round 361) The subject half gets per-file precision too, but MEASURED
     rather than scanned — see the "subject scope" section. 7: a checkout
     that moved OUTSIDE an entry's measured read-scope leaves it conclusive
     at a weaker strength, `fresh_pass_scoped`/`fresh_fail_scoped`, counted
     in `n_scoped` and never in `n_conclusive`. 8: a checkout that moved
     INSIDE it is `stale_subject` — as inconclusive as `stale_checkout`, and
     it names the directory. 9: a scope is usable only if the record is well
     formed AND the run spawned no subprocess; anything else falls back to
     rule 2 unchanged, so no entry is ever fresher than round 341 made it.
  10. (round 367) A run that did not FINISH may not narrow anything. A
     process killed by the timeout, interrupted, or dead of an internal or
     collection error read LESS of the checkout than a healthy one would
     have, so its scope is an under-approximation and narrowing on it is
     fail-open. `failed` is NOT that case and still narrows — a pytest run
     reporting "1 failed, 11 passed" imported everything it was going to.
     See `_refuse_scope_if_incomplete`.

Everything here is offline-testable: `run_slice` takes an injectable
`runner`, so no test in `test_slowtier.py` shells out to pytest.
"""
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

try:                                    # `python harness/swe/slowtier.py`
    from swe import readscope
except ImportError:                     # `python -m swe.slowtier` / in-package
    import readscope

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(HARNESS_ROOT)
TESTS_DIR = os.path.join(HARNESS_ROOT, "tests")
DEFAULT_LEDGER = os.path.join(REPO_ROOT, "state", "slow-tier-ledger.jsonl")
DEFAULT_WHENCE = os.path.join(REPO_ROOT, "languages", "whence")
SWE_DIR = os.path.join(HARNESS_ROOT, "swe")

#: Loaded by pytest for every file in `harness/tests/` whatever it imports,
#: so a change to one can change any slow file's outcome. `conftest.py` is
#: also the file that DEFINES the slow tier (`test_swe_` -> `swe_slow`), so
#: an entry that survived a conftest edit could be evidence about a
#: differently-drawn tier.
_ALWAYS_LOADED = ("tests/conftest.py", "tests/__init__.py")

# Mirrors `swe.mutation._copy_project`'s own ignore list — the digest must
# cover exactly what a test's scratch copy would see, and nothing that is
# regenerated by merely RUNNING the suite (`__pycache__`, `.pytest_cache`),
# which would otherwise make every run invalidate its own predecessor.
_IGNORED_DIRS = ("__pycache__", ".pytest_cache", ".venv", "research-env", ".git")


def _is_ignored(rel):
    parts = rel.replace(os.sep, "/").split("/")
    return any(p in _IGNORED_DIRS or p.endswith(".egg-info") for p in parts)


#: Extensions the digest covers. Round 341 chose `.py` ALONE, and gave a
#: correct reason for excluding `SPEC.md`: a doc edit cannot move a line
#: number in `whence/interp.py`, and a false alarm is as corrosive as a false
#: pass. Round 361 found the rule too narrow by exactly one extension.
#: `swe/guest.py` and `harness/tests/test_swe_guest.py` load
#: `languages/whence/examples/self_eval.lang` — the ~885-line GUEST
#: INTERPRETER, written in Whence — as source. It is not documentation; it is
#: the thing under test. Three commits since 2026-08-26 change a
#: `languages/whence/**.lang` file and NO `.py` file (`f0b8dde`, `32c5cbd`,
#: `c52b9ba`, all three touching `examples/self_eval.lang` itself), so an
#: entry recorded before any of them would have stayed `fresh_pass` across a
#: rewrite of the guest interpreter. That is fail-OPEN, in the one rule the
#: module exists to make fail-closed.
_SOURCE_EXTS = (".py", ".lang")


def checkout_digest(root=DEFAULT_WHENCE):
    """A stable content digest of every `.py` and `.lang` file in the checkout.

    Source extensions only, deliberately: these tests read, mutate, unparse
    and diff Python sources of the interpreter, and load `.lang` sources as
    programs. A `SPEC.md` edit does not move a line number in
    `whence/interp.py`, and counting it would mark results stale for a change
    that cannot affect them — a false alarm is as corrosive here as a false
    pass (round 339's rule: a checker nobody watches must not cry wolf).
    See `_SOURCE_EXTS` for why `.lang` joined the set in round 361.
    """
    h = hashlib.sha256()
    files = []
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in _IGNORED_DIRS and not d.endswith(".egg-info")]
        for n in sorted(names):
            if not n.endswith(_SOURCE_EXTS):
                continue
            full = os.path.join(dirpath, n)
            rel = os.path.relpath(full, root)
            if _is_ignored(rel):
                continue
            files.append((rel.replace(os.sep, "/"), full))
    for rel, full in sorted(files):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            with open(full, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
        except (IOError, OSError):
            # A file that vanished mid-walk is itself a change; fold the
            # fact (not a crash) into the digest.
            h.update(b"<unreadable>")
    return h.hexdigest()[:16]


def slow_tier_files(tests_dir=TESTS_DIR):
    """The files `conftest.py` marks `swe_slow` — its rule verbatim:
    `item.fspath.basename.startswith("test_swe_")`."""
    return sorted(n for n in os.listdir(tests_dir)
                  if n.startswith("test_swe_") and n.endswith(".py"))


# ------------------------------------------------------------------- units --
#
# Round 433 (harness A). Until this round the tier's unit of WORK and its
# unit of EVIDENCE were the same thing — a file — and one file breaks that.
#
# `harness/tests/test_swe_campaign.py` holds 20 tests. Nineteen of them cost
# 571.3 s together (measured this round, one process, `--durations=0`); the
# twentieth, `test_cli_runs_offline_stages_and_stops`, is the only one that
# does not seed a green baseline, so it runs a full unfiltered whence suite
# as the campaign's pre-flight and a tracer-instrumented one for coverage.
# The file therefore does not fit in any budget this program grants a round,
# and the ledger records the consequence exactly: across 26 entries it has
# held ZERO entries for that file. Nineteen real tests were never evidence
# about any checkout, and `plan` could not help — it correctly refuses to
# start a file it cannot finish, so the file's estimate kept it out of even
# a 3600 s budget.
#
# Round 432's next-steps item 3 asked harness(A) for "a slow marker" on that
# test. Measured, that remedy is already in place and does nothing: the file
# matches `SLOW_PREFIX` and is absent from `tier-budget.json`, so
# `-m "not swe_slow"` already deselects all 20 of its tests. What was missing
# was not a marker. It was a unit smaller than a file.
#
# A UNIT is a file plus a selector. A file with no declared heavy tests is
# ONE unit whose id is the filename, byte-for-byte the pre-433 behaviour, so
# an empty registry changes nothing anywhere. A file with declared heavy
# tests becomes TWO units, `<file>[light]` and `<file>[heavy]`, each with its
# own ledger entry, its own cost estimate and its own freshness verdict.
#
# The direction is fail-closed, and it is the OPPOSITE direction to
# `tierbudget.py`'s: that registry can only ever move a file toward the tier
# a human is watching, and this one can only ever SPLIT one claim into two
# smaller ones. A light unit's pass asserts strictly less than the file's
# pass did, and the heavy unit it leaves behind starts `unknown` and stays
# visible in the recall denominator. Declaring a test here cannot make
# anything look greener than it was.
_UNITS_PATH = os.path.join(HARNESS_ROOT, "tier-units.json")

WHOLE, LIGHT, HEAVY = "whole", "light", "heavy"

#: id suffix per kind. `[light]`/`[heavy]` are not pytest syntax on purpose —
#: an id must never be mistakable for a node id a human could paste into a
#: pytest command line and have silently do something else.
_KIND_SUFFIX = {WHOLE: "", LIGHT: "[light]", HEAVY: "[heavy]"}


def load_units_registry(path=None):
    """The heavy-test registry, or an empty one.

    Must never raise, for `tierbudget.load_registry`'s reason one level up:
    this is read by `status`, which `run_tests_fast.sh` calls on every round,
    and a registry that can abort the status line would be round 348's
    `pyproject.toml` outage with this repo's own name on it. A missing or
    malformed file means NOTHING is split — every file stays one unit, which
    is the strongest claim and therefore the safe fallback.
    """
    path = path or _UNITS_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {"heavy": {}, "_load_error": True}
    if not isinstance(data, dict) or not isinstance(data.get("heavy"), dict):
        return {"heavy": {}, "_load_error": True}
    return data


def file_test_names(test_file, tests_dir=TESTS_DIR):
    """Top-level `def test_*` names in a test file, by AST. None if unreadable.

    Static and offline deliberately. `status` runs inside every round's fast
    health check, and a real pytest collection here would cost the seconds
    the tier exists to avoid. It sees exactly the shape this registry is
    allowed to name — a plain top-level test function. A class method or a
    parametrised id is not a name the registry can use, and naming one is a
    registry ERROR rather than a silent partial match (see `split_file`).
    """
    try:
        with open(os.path.join(tests_dir, test_file), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except Exception:
        return None
    return [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("test_")]


def unit_id(test_file, kind):
    return test_file + _KIND_SUFFIX[kind]


def unit_file(uid):
    """The file a unit id belongs to. Pure string surgery, no registry read:
    `run_slice` needs the file for its dep closure before it knows anything
    else, and a ledger entry written by an older schema IS its file's id."""
    for suffix in (_KIND_SUFFIX[LIGHT], _KIND_SUFFIX[HEAVY]):
        if uid.endswith(suffix):
            return uid[:-len(suffix)]
    return uid


def _whole(test_file, error=""):
    return [{"id": test_file, "file": test_file, "kind": WHOLE, "tests": [],
             "registry_error": error}]


def split_file(test_file, heavy_names, tests_dir=TESTS_DIR):
    """One file -> its units, plus a registry-error string ("" when clean).

    Every refusal path returns the SINGLE whole-file unit. That is the
    fail-closed choice for the property this module protects: the whole-file
    unit is the strongest claim (nothing is covered until the entire file
    has run), so a broken registry costs wall-clock, exactly as a stale
    `tier-budget.json` entry does, and cannot cost coverage.
    """
    heavy_names = sorted(set(heavy_names or ()))
    if not heavy_names:
        return _whole(test_file), ""
    names = file_test_names(test_file, tests_dir)
    if names is None:
        return _whole(test_file), ("unreadable: cannot confirm the declared "
                                   "heavy test(s) exist")
    missing = [n for n in heavy_names if n not in names]
    if missing:
        # A renamed or deleted test. Silently keeping the split would leave a
        # `[heavy]` unit that collects nothing (pytest rc 4/5, never
        # narrowing) and a `[light]` unit whose name claims to exclude
        # something it does not.
        return _whole(test_file), ("declared heavy test(s) not in the file: %s"
                                   % ", ".join(missing))
    if not [n for n in names if n not in heavy_names]:
        return _whole(test_file), ("every test in the file is declared heavy: "
                                   "the light unit would collect nothing")
    return ([{"id": unit_id(test_file, LIGHT), "file": test_file,
              "kind": LIGHT, "tests": heavy_names, "registry_error": ""},
             {"id": unit_id(test_file, HEAVY), "file": test_file,
              "kind": HEAVY, "tests": heavy_names, "registry_error": ""}], "")


def slow_tier_units(tests_dir=TESTS_DIR, registry=None):
    """Every unit of the slow tier, in file order. With an empty registry
    this is `slow_tier_files()` with each name wrapped, one for one."""
    registry = load_units_registry() if registry is None else registry
    heavy = registry.get("heavy") or {}
    units = []
    for f in slow_tier_files(tests_dir):
        decl = heavy.get(f) or {}
        us, err = split_file(f, decl.get("tests"), tests_dir)
        for u in us:
            u["registry_error"] = err
        units.extend(us)
    return units


def resolve_unit(uid, tests_dir=TESTS_DIR, registry=None):
    """A unit id -> its unit dict, or a whole-file unit when the id names
    nothing the registry knows (an injected test double's file, a name from
    an older ledger). Never None: a caller holding an id always gets
    something runnable."""
    for u in slow_tier_units(tests_dir, registry):
        if u["id"] == uid:
            return u
    return _whole(unit_file(uid))[0]


def unit_pytest_args(unit, tests_dir=TESTS_DIR):
    """The pytest argv tail that selects exactly this unit.

    `[heavy]` selects by NODE ID rather than `-k`, so a substring of another
    test's name can never widen it; `[light]` deselects the same node ids,
    so the two are complements by construction over the same file.
    """
    path = os.path.join(tests_dir, unit["file"])
    if unit["kind"] == HEAVY:
        return [path + "::" + t for t in unit["tests"]]
    args = [path]
    for t in unit["tests"] if unit["kind"] == LIGHT else ():
        args += ["--deselect", path + "::" + t]
    return args


# -------------------------------------------------------------- harness deps --
#
# Round 341's item 2, and a deliberate refinement of how it was worded.
#
# The problem is real: `checkout_digest` covers the SUBJECT (the whence
# checkout), so an entry written against `test_swe_alias_effects.py` stays
# `fresh_pass` after that very test file — or the `swe/` module it exercises —
# is rewritten. Round 341's own 873-second run is the case: three tests were
# appended to the file after collection, and rule 2 would still have called
# the result fresh.
#
# Round 341 proposed "a SECOND digest field over `harness/tests/` +
# `harness/swe/`". Building it that way was tried here and rejected by
# arithmetic. One digest over both directories means ANY harness edit
# invalidates ALL 18 files at once — and a harness(A) round that edits
# `harness/swe/` is the normal case, not the exception. The tier takes ~76
# minutes on this one-CPU box against a per-round budget in the low hundreds
# of seconds, so a whole-directory digest would reset recall to 0% faster than
# any sequence of rounds could raise it. The ledger would never accumulate,
# which is the module's entire purpose. Precision is not a nicety here; it is
# what makes the mechanism able to work at all.
#
# So the digest is per-file and covers exactly what can change that file's
# outcome: the test file itself, the transitive closure of its `swe.*`
# imports, and the files pytest loads for every test regardless
# (`_ALWAYS_LOADED`). `ast.walk` catches function-scope imports too — several
# `swe/` modules have them (`swe/coverage.py:499`, `swe/equivalence.py:200`).
#
# Fail-closed where the scan can fail: a file that will not parse, or a
# `test_swe_*.py` that resolves to NO `swe.*` module at all (which would mean
# the scan is blind, since every slow test exists to exercise that package),
# falls back to the whole `swe/` package. Precision is the optimisation;
# over-broad is the floor.


class DepScanFailed(Exception):
    """Raised internally when a source will not parse; callers fall back."""


class _WorkingTreeSources(object):
    """The harness sources as they are on disk — the default everywhere.

    Round 367 (harness A) split this out so `harness_deps` can be run
    against a source set that is NOT the working tree, which is what
    `swe/ledgerreplay.py` needs to replay the ledger's freshness states
    against historical commits. Without it the replay would have to
    re-implement the import scan over git blobs, and a second copy of this
    logic is `skills/copied-mirror-drift`'s exact shape: the replay would
    keep answering the question the scan used to answer.

    Three methods, all harness-relative (`swe/fuzz.py`, `tests/conftest.py`):
    `exists`, `read` (text, may raise IOError/OSError), `all_swe_rels`.
    """

    def exists(self, rel):
        return os.path.exists(os.path.join(HARNESS_ROOT, rel))

    def read(self, rel):
        with open(os.path.join(HARNESS_ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def all_swe_rels(self):
        out = []
        for dirpath, dirnames, names in os.walk(SWE_DIR):
            dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]
            for n in sorted(names):
                if n.endswith(".py"):
                    rel = os.path.relpath(os.path.join(dirpath, n),
                                          HARNESS_ROOT)
                    out.append(rel.replace(os.sep, "/"))
        return sorted(out)


#: The default source set: the working tree. Every public entry point keeps
#: its round-343 signature and behaviour when this is used.
WORKING_TREE = _WorkingTreeSources()


def _module_rel(mod, sources=WORKING_TREE):
    """`swe.fuzz` -> harness-relative `swe/fuzz.py`; None if not ours."""
    parts = mod.split(".")
    if not parts or parts[0] != "swe":
        return None
    cand = os.path.join(*parts) + ".py"
    if sources.exists(cand.replace(os.sep, "/")):
        return cand.replace(os.sep, "/")
    pkg = os.path.join(os.path.join(*parts), "__init__.py")
    if sources.exists(pkg.replace(os.sep, "/")):
        return pkg.replace(os.sep, "/")
    return None


def _swe_imports_source(text, label, inside_swe):
    """Every `swe.*` module name imported by one source TEXT.

    Split out from `_swe_imports` in round 367 so the same scan can run over
    a git blob (see `_WorkingTreeSources`). `inside_swe` says whether the
    file lives in the `swe` package, which is what a relative import
    (`from . import killers`, `from .fuzz import X`) resolves against — the
    package is flat, so level is always 1 there.
    """
    try:
        tree = ast.parse(text, label)
    except (SyntaxError, ValueError):
        raise DepScanFailed(label)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] == "swe":
                    mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and inside_swe:
                base = "swe" + ("." + node.module if node.module else "")
                if node.module:
                    mods.add(base)
                else:
                    # `from . import killers as K` — each NAME is a module.
                    for a in node.names:
                        mods.add("swe." + a.name)
            elif not node.level and node.module \
                    and node.module.split(".")[0] == "swe":
                mods.add(node.module)
                # `from swe import killers` names modules, not attributes.
                if node.module == "swe":
                    for a in node.names:
                        mods.add("swe." + a.name)
    return mods


def harness_deps(test_file, tests_dir=TESTS_DIR, sources=WORKING_TREE):
    """Harness-relative paths whose content can change `test_file`'s outcome.

    Returns a sorted list. Falls back to the whole `swe/` package (plus the
    always-loaded files and the test itself) when the static scan cannot be
    trusted — see this section's header.

    `sources` (round 367) is where the scanned text comes from; the default
    is the working tree, and `tests_dir` then still selects which directory
    the test file is read from. A caller that passes a non-default `sources`
    is scanning a different source set (a git revision, say) and gets the
    harness-relative layout `tests/<file>`.
    """
    test_rel = os.path.relpath(os.path.join(tests_dir, test_file),
                               HARNESS_ROOT).replace(os.sep, "/")
    base = set(_ALWAYS_LOADED) | {test_rel}
    base = set(p for p in base if sources.exists(p))
    try:
        seen, queue = set(), list(_read_swe_imports(
            sources, test_rel, inside_swe=False))
        while queue:
            mod = queue.pop()
            if mod in seen:
                continue
            seen.add(mod)
            rel = _module_rel(mod, sources)
            if rel is None:
                continue
            base.add(rel)
            # A submodule's package `__init__.py` is executed on import.
            parts = mod.split(".")
            for i in range(1, len(parts)):
                pkg = _module_rel(".".join(parts[:i]), sources)
                if pkg:
                    base.add(pkg)
            queue.extend(_read_swe_imports(sources, rel, inside_swe=True))
        if not any(p.startswith("swe/") for p in base):
            raise DepScanFailed(test_file)          # blind scan -> fall back
    except DepScanFailed:
        base |= set(sources.all_swe_rels())
    return sorted(base)


def _read_swe_imports(sources, rel, inside_swe):
    """`_swe_imports_source` over a harness-relative path from `sources`.

    A source that cannot be read is a scan failure, not a crash — the same
    fail-closed fallback the round-343 version took on an unreadable file.
    """
    try:
        text = sources.read(rel)
    except (IOError, OSError, ValueError, KeyError):
        raise DepScanFailed(rel)
    return _swe_imports_source(text, rel, inside_swe)


def dep_digests(test_file, tests_dir=TESTS_DIR, deps=None):
    """`{harness-relative path: sha256[:16]}` for each dependency.

    Stored per entry rather than folded into one hash so a later round can
    say WHICH file moved, not merely that something did — the difference
    between "the test changed" and "the module under it changed", which is
    the distinction round 341 asked for.
    """
    deps = harness_deps(test_file, tests_dir) if deps is None else deps
    out = {}
    for rel in deps:
        try:
            with open(os.path.join(HARNESS_ROOT, rel), "rb") as f:
                out[rel] = hashlib.sha256(f.read()).hexdigest()[:16]
        except (IOError, OSError):
            out[rel] = "<missing>"
    return out


def moved_deps(entry, current):
    """Paths whose digest differs between a ledger `entry` and `current`.

    A dependency that APPEARED or VANISHED counts as moved: the import graph
    itself changing is a change to what the test exercises.
    """
    old = (entry or {}).get("dep_digests") or {}
    return sorted(set(k for k in set(old) | set(current)
                      if old.get(k) != current.get(k)))


# ------------------------------------------------------------- subject scope --
#
# Round 361, harness(A). The mirror image of the "harness deps" section above,
# for the SUBJECT half — and the argument is the same arithmetic. The harness
# half got per-file precision because "ANY harness edit invalidates ALL 18
# files at once ... the ledger would never accumulate, which is the module's
# entire purpose". `checkout_digest` is exactly that whole-directory digest,
# over `languages/whence/`, and 52% of the commits that move it (32 of 61
# since 2026-08-26) touch nothing under `whence/` and no `run.py` — they edit
# whence's OWN tests and benches, which most slow-tier files never read.
#
# The subject half cannot be scanned statically the way the harness half is:
# `swe/killers.py:load_whence` imports the package by file location,
# `swe/guest.py` reads a `.lang` file as source, `swe/mutation.py` copytrees
# the whole checkout and `swe/coverage.py` shells out to a pytest that reads
# whatever it likes. A static marker table for those would be a hand-
# maintained rule with nothing enforcing it — `skills/unenforced-documented-
# rule/`'s exact shape. So the scope is MEASURED, by `swe/readscope.py`'s
# audit hook, during the run that produced the entry.
#
# The claim a scope supports is strictly WEAKER than the claim
# `checkout_digest` supports, and it is labelled as such rather than merged
# into it: `fresh_pass_scoped` is its own state, `CONCLUSIVE` is unchanged,
# and `status` reports both recalls. Round 334's rule about
# `confirmed_span_s` — add a separate field, never redefine a published one.


def scope_digests_now(entry, whence_root=DEFAULT_WHENCE):
    """Recompute an entry's RECORDED scope directories against the tree now.

    Returns None when the entry carries no usable scope, which is every
    pre-round-361 entry and every entry whose run was opaque or whose record
    was torn — `readscope.scope_is_narrowable` is the single predicate.
    """
    entry = entry or {}
    scope = entry.get("subject_scope")
    if not isinstance(scope, dict) or not readscope.scope_is_narrowable(scope):
        return None
    # Rule 10, applied on the READ side as well as the write side. Stamping
    # the refusal into new entries (`_refuse_scope_if_incomplete`) leaves
    # every entry already in the ledger under the old fail-open rule, and a
    # ledger is append-only — the round that ships a rule does not get to
    # rewrite the records that predate it. So the same question is asked of
    # the entry itself, from data it has always carried. Today this changes
    # nothing (no entry in the ledger is both incomplete and narrowable),
    # which is the point: the guard exists for the next timeout, not for a
    # backlog.
    if entry.get("timed_out") or (
            "returncode" in entry
            and entry["returncode"] not in _COMPLETED_RETURNCODES):
        return None
    dirs = scope.get("dirs")
    if not isinstance(dirs, list):
        return None
    return readscope.scope_digests(whence_root, dirs)


def moved_scope(entry, current):
    """Scope directories whose digest differs between `entry` and `current`."""
    old = (entry or {}).get("subject_digests") or {}
    current = current or {}
    return sorted(set(k for k in set(old) | set(current)
                      if old.get(k) != current.get(k)))


# ------------------------------------------------------------------ ledger --

def append_entry(path, entry):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def read_entries(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                # A torn last line (a round killed mid-append) is skipped,
                # not fatal: the ledger is evidence, and an unreadable
                # record is simply absent evidence — rule 1 then applies.
                continue
    return out


def latest_by_file(entries):
    """Most recent entry per file, by `finished_at` (ties -> later line)."""
    best = {}
    for e in entries:
        f = e.get("file")
        if not f:
            continue
        cur = best.get(f)
        if cur is None or e.get("finished_at", 0) >= cur.get("finished_at", 0):
            best[f] = e
    return best


def entry_unit(entry):
    """The unit an entry is about. An entry written before round 433 carries
    no `unit` field and is about the whole file, which is what `file` already
    says — so the default is not a guess, it is the same string."""
    return entry.get("unit") or entry.get("file")


def latest_by_unit(entries, units):
    """`{unit id: (entry or None, inherited)}`.

    Rule 11 (round 433), the one asymmetry a split introduces:

      A whole-file entry whose outcome is `passed` IS evidence for every
      unit of that file. The run is a strict superset of each unit's, and
      "everything passed" entails "these passed".

      A whole-file entry whose outcome is `failed` is evidence for the
      whole-file unit ONLY. Somebody in there was red and pytest's exit code
      does not say who, so attributing it to a unit would be inventing a
      verdict — and attributing it to the OTHER unit as a pass would be
      inventing the opposite one.

    A sub-unit's entry never flows the other way. `[light]` passing says
    nothing about `[heavy]`, and the file is covered only when both units
    are, which is what makes the recall denominator honest after a split.

    `inherited` is returned beside the entry rather than written into it:
    `plan` must not use a whole-file `seconds` as a sub-unit's cost estimate,
    and a reader must be able to see that a unit's green came from a run that
    was not this unit.
    """
    out = {}
    for u in units:
        best, best_inherited = None, False
        for e in entries:
            eu = entry_unit(e)
            if eu == u["id"]:
                inherited = False
            elif (u["kind"] != WHOLE and eu == u["file"]
                    and e.get("outcome") == "passed"):
                inherited = True
            else:
                continue
            if best is None or (e.get("finished_at") or 0) >= (best.get("finished_at") or 0):
                best, best_inherited = e, inherited
        out[u["id"]] = (best, best_inherited)
    return out


# ------------------------------------------------------------------ status --

def classify(entry, digest, cur_dep_digests=None, cur_scope_digests=None):
    """The fail-closed state machine. See this module's docstring.

    `cur_dep_digests` is the current `dep_digests` mapping for this file
    (round 343, rules 4-6). Passing None evaluates only rules 1-3 — the
    round-341 behaviour, kept so a caller holding an entry but no tests
    directory can still classify the subject half.

    `cur_scope_digests` (round 361, rules 7-9) is the current per-directory
    digest of the entry's own MEASURED read-scope, as returned by
    `scope_digests_now`. Passing None — which is what every caller gets for a
    pre-361 entry, an opaque run, or a torn scope record — leaves rule 2
    exactly as it was. When it IS available and nothing in scope moved, the
    entry becomes evidence of a strictly WEAKER kind, reported under its own
    `_scoped` state and NOT folded into `CONCLUSIVE`.
    """
    if entry is None:
        return "unknown"
    if not entry.get("checkout_stable", False):
        return "raced"
    if not entry.get("harness_stable", True):
        return "raced"
    scoped = False
    if entry.get("checkout_digest") != digest:
        if cur_scope_digests is None:
            return "stale_checkout"
        if moved_scope(entry, cur_scope_digests):
            # More informative than `stale_checkout`, and just as inconclusive:
            # the checkout moved AND it moved inside what this run read.
            return "stale_subject"
        scoped = True
    if cur_dep_digests is not None:
        if entry.get("dep_digests") is None:
            # Rule 5: written before the harness was stamped at all. Its
            # pass is about an unknown harness, which is not this one until
            # something proves it is.
            return "unstamped"
        if moved_deps(entry, cur_dep_digests):
            return "stale_harness"
    if entry.get("outcome") == "passed":
        return "fresh_pass_scoped" if scoped else "fresh_pass"
    if entry.get("outcome") == "failed":
        return "fresh_fail_scoped" if scoped else "fresh_fail"
    return "unknown"


#: States that are genuine evidence about the CURRENT checkout AND the
#: current harness. Round 343 widened what "current" has to mean; the tuple
#: itself is unchanged, which is the point — every new state is inconclusive.
CONCLUSIVE = ("fresh_pass", "fresh_fail")

#: Round 361. Evidence about the current harness and about every checkout
#: DIRECTORY this run was measured to read from — but not about the whole
#: checkout, which has moved somewhere the run never looked. Deliberately a
#: SECOND tuple rather than three more members of `CONCLUSIVE`: three rounds
#: of reported figures, `run_tests_fast.sh`'s printed line and
#: `state/slow-tier-ledger.jsonl`'s readers all depend on what
#: "conclusive/recall" has meant since round 341 (round 334's rule about
#: `confirmed_span_s`, applied here). Both numbers are reported side by side
#: and the weaker one is always labelled.
SCOPED_CONCLUSIVE = ("fresh_pass_scoped", "fresh_fail_scoped")

#: Any state that is a real FAILURE signal, at either strength. A scoped
#: failure is a failing test in a directory nothing has moved; the weaker
#: freshness claim does not make the red less red.
FAILING = ("fresh_fail", "fresh_fail_scoped")


def recorded_failing_but_stale(row):
    """Round 385. A row whose LAST RECORDED RUN was red, but whose state is
    inconclusive so it is not counted in `n_failing`.

    The state machine is right and is not being changed: a failure measured
    against a checkout that has since moved is not evidence about THIS
    checkout. But `report_text` rendered such a row as the bare word
    `stale_subject`, which reads exactly like a stale PASS, and that is the
    one thing it is not. `test_swe_guest.py` sat at `2 failed, 65 passed` in
    the ledger for 18 hours while `slow tier: ... 0 failing` was the line
    every round's health log printed underneath it.

    This is round 384's finding one level up — a fact computed, kept, and
    never rendered — so it is reported as PROVENANCE ("the last time anybody
    ran this, it was red"), never as freshness, and it gets its OWN count.
    `n_failing` keeps the meaning it has had since round 341: three rounds of
    published figures and `run_tests_fast.sh`'s printed line depend on it
    (round 334's rule about `confirmed_span_s`, applied here)."""
    return row.get("outcome") == "failed" and row.get("state") not in FAILING


def status(ledger_path=DEFAULT_LEDGER, tests_dir=TESTS_DIR, whence_root=DEFAULT_WHENCE,
           digest=None, units=None):
    digest = checkout_digest(whence_root) if digest is None else digest
    units = slow_tier_units(tests_dir) if units is None else units
    best = latest_by_unit(read_entries(ledger_path), units)
    rows = []
    for u in units:
        f = u["file"]
        e, inherited = best[u["id"]]
        cur = dep_digests(f, tests_dir)
        cur_scope = scope_digests_now(e, whence_root)
        scope = (e or {}).get("subject_scope") or {}
        rows.append({
            "unit": u["id"],
            "kind": u["kind"],
            # The tests this unit runs (heavy) or refuses to run (light).
            # Named, never counted: after a split the reader's first question
            # is always "which ones", the same rule `moved_deps` follows.
            "unit_tests": list(u["tests"]),
            "registry_error": u.get("registry_error", ""),
            # Rule 11: this row's evidence came from a whole-file PASS, not
            # from a run of this unit. Surfaced so `plan` never mistakes the
            # file's wall clock for the unit's.
            "inherited": inherited,
            "file": f,
            "state": classify(e, digest, cur, cur_scope),
            "outcome": (e or {}).get("outcome"),
            "finished_at": (e or {}).get("finished_at"),
            "seconds": (e or {}).get("seconds"),
            "checkout_digest": (e or {}).get("checkout_digest"),
            "n_deps": len(cur),
            # Named, not counted: "which file moved" is the whole reason
            # the digests are stored per path (round 341's item 2).
            "moved_deps": moved_deps(e, cur) if e is not None else [],
            # Round 361: the same "name it, do not count it" rule for the
            # subject half. `scope_dirs` is [] for an entry with no usable
            # scope, which is what a pre-361 ledger is made of.
            "scope_dirs": list(scope.get("dirs") or []) if cur_scope is not None else [],
            "scope_opaque": list(scope.get("opaque") or []),
            "moved_scope": moved_scope(e, cur_scope) if cur_scope is not None else [],
        })
    covered = [r for r in rows if r["state"] in CONCLUSIVE]
    scoped = [r for r in rows if r["state"] in SCOPED_CONCLUSIVE]
    return {
        "digest": digest,
        "rows": rows,
        # Round 433: `n_files` keeps the meaning it has had since round 341 —
        # how many FILES the tier holds — and `n_units` is the new
        # denominator. With an empty registry they are equal and every
        # published figure is unchanged; a split makes them differ, and both
        # are printed side by side rather than one silently replacing the
        # other (round 334's rule about `confirmed_span_s`, applied again).
        "n_files": len(set(r["file"] for r in rows)),
        "n_units": len(rows),
        "n_registry_errors": len([r for r in rows if r["registry_error"]]),
        "n_conclusive": len(covered),
        # Round 361, reported SEPARATELY: files whose evidence survives only
        # because the checkout moved outside their measured read-scope.
        "n_scoped": len(scoped),
        "n_failing": len([r for r in rows if r["state"] in FAILING]),
        # Round 385, deliberately a SEPARATE count and never added to
        # `n_failing` — see `recorded_failing_but_stale`.
        "n_recorded_failing_stale":
            len([r for r in rows if recorded_failing_but_stale(r)]),
        # The recall this view has on the CURRENT tree. Round 339's rule:
        # a checker must report its own recall so the gap stays visible.
        "coverage": (float(len(covered)) / len(rows)) if rows else 0.0,
        "coverage_scoped": (float(len(covered) + len(scoped)) / len(rows)) if rows else 0.0,
    }


def _size_prior(test_file, tests_dir=TESTS_DIR, row=None):
    """Bytes of the test file, scaled to a fraction of a second.

    Only a TIE-break among unmeasured units (see `plan`). Deliberately tiny
    relative to `default_s` so it can never reorder a unit that has a real
    measurement against one that does not.

    Round 433, for split files. Bytes are a per-FILE quantity, so both units
    of a split file would otherwise carry the SAME prior and sort adjacently
    at the tail — which is the wrong order for the only thing this prior
    decides. A `[light]` unit is scaled down by its share of the file's tests
    and a `[heavy]` unit keeps the file's full prior, because being expensive
    is the reason the registry named it at all. Both remain priors: any unit
    with a real `seconds` uses that instead, which
    `test_a_real_measurement_always_beats_the_size_prior` pins.
    """
    try:
        size = os.path.getsize(os.path.join(tests_dir, test_file)) / 1e6
    except (IOError, OSError):
        return 0.0
    kind = (row or {}).get("kind")
    if kind == LIGHT:
        names = file_test_names(test_file, tests_dir) or []
        heavy = set((row or {}).get("unit_tests") or ())
        light_n = len([n for n in names if n not in heavy])
        if names and light_n:
            size *= float(light_n) / len(names)
    return size


def _uid(row):
    """A row's unit id. Falls back to its file, so a hand-built pre-433 row
    (and every test that builds one) plans exactly as it did before."""
    return row.get("unit") or row["file"]


def _est(row):
    """A row's usable cost estimate, or None.

    Round 433: an INHERITED row's `seconds` is the whole FILE's wall clock,
    not this unit's, and using it would make `[light]` look as expensive as
    the file it was split out of — which is the one number the split exists
    to stop believing. An inherited row therefore falls back to the
    unmeasured prior, and says so in `plan_reasons`' spirit by being visible
    as `inherited` in the row.
    """
    return None if row.get("inherited") else row.get("seconds")


def plan(st, budget_s, default_s=300.0, tests_dir=TESTS_DIR):
    """Which units to run next, in order, inside `budget_s`.

    Order: never-conclusive first (worst evidence first), then — round 385
    — any file whose last recorded run was RED, then oldest `finished_at`. Estimated cost is the file's own last measured
    `seconds`, `default_s` when unmeasured. A file whose estimate ALONE
    exceeds the budget is still returned as the sole entry when nothing
    else fits — otherwise a file slower than every budget would never run
    again, which is precisely the silent-truncation failure this module
    exists to prevent.
    """
    def key(r):
        conclusive = r["state"] in CONCLUSIVE
        # Round 385, the FIRST term and deliberately ahead of round 343's:
        # a file whose last recorded run was RED but whose state is now
        # inconclusive is the highest-information re-run in the tier. It
        # either confirms a live bug or clears one, where a never-measured
        # file can only ever produce a first data point. `finished_at` alone
        # sorted it BEHIND every `unknown`, because a red file has a
        # timestamp and an unmeasured one has 0 — so `report_text`'s "the
        # first thing a slow-tier slice should re-run" was, until this term,
        # a sentence the planner did not honour. Both are true now, and
        # `test_the_planner_re_runs_a_last_red_file_before_an_unknown` is
        # what keeps them agreeing.
        #
        # Cannot starve coverage: it fires only on a file that already has
        # a ledger entry AND that entry is red, which is 0 or 1 files in
        # practice, and a CONCLUSIVE red (`fresh_fail`) is excluded by
        # `recorded_failing_but_stale` — it needs no re-run at all.
        red_first = 0 if recorded_failing_but_stale(r) else 1
        # Round 343: among files with equally bad evidence, cheapest first.
        # With an EMPTY ledger every estimate is `default_s`, so round 341's
        # `(conclusive, finished_at, file)` key degenerated to ALPHABETICAL —
        # which spends the very first budget a round ever grants on
        # `test_swe_alias_effects.py` (873 s measured, round 341) and covers
        # exactly one file. Falling back to the test file's own SIZE is a
        # prior, not a measurement, and it is only ever a TIE-break: any
        # file with a real `seconds` uses that. Named as a prior in
        # `plan_reasons` so nobody reads it as timing data.
        return (1 if conclusive else 0, red_first, r["finished_at"] or 0,
                _est(r) or (default_s + _size_prior(r["file"], tests_dir, r)),
                _uid(r))

    ordered = sorted(st["rows"], key=key)
    picked, spent = [], 0.0
    for r in ordered:
        est = _est(r) or default_s
        if picked and spent + est > budget_s:
            continue
        picked.append(_uid(r))
        spent += est
        if spent >= budget_s:
            break
    return picked


# --------------------------------------------------------------------- run --

def pytest_runner(unit, tests_dir=TESTS_DIR, timeout_s=3000,
                  whence_root=DEFAULT_WHENCE):
    """The real runner: one pytest process per UNIT, cwd at the repo root.

    Round 433: `unit` is a unit id (or a unit dict). An id the registry does
    not know resolves to a whole-file unit, so every pre-433 caller — and
    every ledger entry written before this round — still names something
    runnable.

    `PYTHONDONTWRITEBYTECODE` is set for round 340's reason — a `.pyc`
    whose cache key (source size, source mtime truncated to whole seconds)
    collides with a since-edited source makes a run test the WRONG
    bytecode. The whence tree is edited by other rounds between slices, so
    this is not hypothetical here.

    Round 361: the child is launched as `python -c <bootstrap>` rather than
    `python -m pytest`, so `swe/readscope.py`'s audit hook is live BEFORE
    pytest imports anything — which is the only moment at which `swe.*` and
    `whence.*` reads can be seen. `python -c` and `python -m` both put the
    cwd at `sys.path[0]`, so collection and import resolution are unchanged;
    `pytest.main`'s return codes are pytest's own. If the hook or the record
    fails for any reason the run is unaffected and the scope is simply absent
    — `readscope.read_scope_file` reports `ok: false` and `classify` falls
    back to the whole-checkout rule.
    """
    if not isinstance(unit, dict):
        unit = resolve_unit(unit, tests_dir)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    args = ["-q", "-p", "no:randomly"] + unit_pytest_args(unit, tests_dir)
    tmpdir = tempfile.mkdtemp(prefix="slowtier-scope-")
    scope_path = os.path.join(tmpdir, "scope.json")
    cmd = [sys.executable, "-c",
           readscope.bootstrap_source(whence_root, scope_path, args)]
    try:
        try:
            p = subprocess.Popen(cmd, cwd=REPO_ROOT, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out, _ = p.communicate(timeout=timeout_s)
            rc = p.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
            rc, timed_out = -9, True
        scope = readscope.read_scope_file(scope_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    text = (out or b"").decode("utf-8", "replace")
    return {"returncode": rc, "timed_out": timed_out, "tail": text[-800:],
            "scope": scope}


#: pytest return codes that mean THE RUN FINISHED AND REPORTED: 0 (all
#: passed) and 1 (tests failed). Everything else — 2 interrupted, 3 internal
#: error, 4 usage error, 5 nothing collected, and the -9 this module stamps
#: on a timeout kill — means the process stopped early.
_COMPLETED_RETURNCODES = (0, 1)


def _refuse_scope_if_incomplete(scope, result):
    """Fail-closed rule 10 (round 367): a run that did not FINISH may not
    narrow anything.

    Round 361 shipped rules 7-9 and named this hole in its own next steps:

        Scope is measured from a run that may have failed early. A crashed
        run reads less than a healthy one, so its scope is an
        under-approximation. Today `run_slice` narrows on any outcome
        including `failed`. Either refuse to narrow on a non-`passed`
        outcome or record the decision knowingly — this round did neither.

    The choice made here is deliberately NOT "narrow only on `passed`". A
    pytest process that reports `1 failed, 11 passed` collected and imported
    everything it was going to; its read-set is complete, and refusing to
    narrow it would throw away the one state the module most wants to keep
    visible (`fresh_fail_scoped`, which counts in `n_failing`). What makes a
    read-set an under-approximation is the process stopping EARLY — a
    timeout kill, an interrupt, an internal error, a collection failure —
    and pytest already distinguishes those by return code.

    The refusal is written into the scope RECORD (`ok: False`, with `why`
    saying which return code caused it) rather than into a new entry field,
    so every consumer refuses through the single predicate
    `readscope.scope_is_narrowable` — present and future, without knowing
    this rule exists. `dirs` and `opaque` are kept so a human reading the
    ledger can still see what was measured and why it was not used.
    """
    if result.get("timed_out"):
        why = "run-did-not-complete: timed out"
    elif result.get("returncode") not in _COMPLETED_RETURNCODES:
        why = "run-did-not-complete: rc=%s" % (result.get("returncode"),)
    else:
        return scope
    out = dict(scope)
    out["ok"] = False
    out["why"] = why
    return out


def run_slice(units, ledger_path=DEFAULT_LEDGER, whence_root=DEFAULT_WHENCE,
              runner=pytest_runner, clock=time.time, log=None,
              tests_dir=TESTS_DIR):
    """Run each unit, recording one ledger entry apiece.

    Round 433: `units` is a list of unit IDs. An id with no `[light]`/
    `[heavy]` suffix is a file, which is what every id was before this round,
    so an injected runner still receives exactly the string it was given and
    the entry's `file` field still holds a filename.

    The digest is read BEFORE and AFTER each file. If it moved, the entry
    is stamped `checkout_stable: false` and can never be counted as
    evidence (rule 3) — the run overlapped another round editing the tree,
    which is exactly how four of round 338's five failures are produced.

    Round 361: the per-scope-directory digests are computed BEFORE the
    closing `checkout_digest` call, deliberately, so that `checkout_stable`
    brackets the scope read too. Computing them after it would leave a window
    in which the tree could move, the scope baseline would be recorded too
    NEW, and a later `status` would compare that too-new baseline against the
    tree, find it equal, and report `fresh_pass_scoped` for a run that never
    saw those bytes.
    """
    log = log or (lambda s: None)
    written = []
    for uid in units:
        u = resolve_unit(uid, tests_dir)
        f = u["file"]
        before = checkout_digest(whence_root)
        deps = harness_deps(f, tests_dir)
        deps_before = dep_digests(f, tests_dir, deps)
        t0 = clock()
        r = runner(uid)
        t1 = clock()
        # Round 361. A runner that reports no scope (every injected test
        # double, and the real one when the hook or the record failed) yields
        # `ok: false`, which `scope_digests_now` refuses — the entry is then
        # gated exactly as a round-341 entry is.
        scope = r.get("scope") or {"ok": False, "dirs": [], "opaque": [],
                                   "n_reads": 0, "why": "runner-gave-none"}
        scope = _refuse_scope_if_incomplete(scope, r)
        narrow = readscope.scope_is_narrowable(scope)
        scope_digs = (readscope.scope_digests(whence_root, scope["dirs"])
                      if narrow else None)
        after = checkout_digest(whence_root)
        # Re-scan the closure rather than reusing `deps`: an import added
        # mid-run changes WHICH files matter, and that is itself a race.
        deps_after = dep_digests(f, tests_dir)
        stable = (before == after)
        harness_stable = (deps_before == deps_after)
        outcome = ("timeout" if r.get("timed_out") else
                   "passed" if r.get("returncode") == 0 else "failed")
        entry = {
            "file": f,
            # Round 433. `file` stays a FILENAME so every pre-433 reader
            # (`ledgerreplay`, `latest_by_file`, a human grepping the JSONL)
            # keeps working unchanged; `unit` is what freshness is now keyed
            # on, and for an unsplit file the two strings are equal.
            "unit": uid,
            "unit_kind": u["kind"],
            "unit_tests": list(u["tests"]),
            "outcome": outcome,
            "returncode": r.get("returncode"),
            "seconds": round(t1 - t0, 2),
            "finished_at": t1,
            "checkout_digest": before,
            "checkout_digest_after": after,
            "checkout_stable": stable,
            "dep_digests": deps_before,
            "harness_stable": harness_stable,
            "subject_scope": scope,
            "subject_digests": scope_digs,
            "schema": 5,
            "tail": r.get("tail", "")[-800:],
        }
        append_entry(ledger_path, entry)
        written.append(entry)
        flags = ("" if stable else "  [CHECKOUT CHANGED MID-RUN]") \
            + ("" if harness_stable else "  [HARNESS CHANGED MID-RUN]")
        if narrow:
            flags += "  scope=%s" % ",".join(scope["dirs"] or ["(nothing)"])
        elif scope.get("opaque"):
            flags += "  scope=WHOLE (%s)" % ",".join(scope["opaque"])
        else:
            flags += "  scope=WHOLE (%s)" % (scope.get("why") or "unrecorded")
        log("%-38s %-8s %6.1fs%s" % (uid, outcome, entry["seconds"], flags))
    return written


# ------------------------------------------------------------------ report --

def report_text(st):
    n_units = st.get("n_units", st["n_files"])
    # Round 433: say "N files" when nothing is split (every published figure
    # since round 341 reads that way) and "N files / M units" the moment they
    # differ, so the denominator a recall percentage is over is never a thing
    # the reader has to infer.
    scale = ("%d files" % st["n_files"] if n_units == st["n_files"]
             else "%d files / %d units" % (st["n_files"], n_units))
    lines = ["slow tier: %s, %d conclusive against checkout %s (%.0f%% recall), %d failing"
             % (scale, st["n_conclusive"], st["digest"],
                100.0 * st["coverage"], st["n_failing"])]
    for r in st["rows"]:
        if r.get("registry_error"):
            # Never silent. A registry error means the file fell back to a
            # single whole-file unit, i.e. the split a human asked for is NOT
            # in effect, and the recall above is over a different denominator
            # than they think.
            lines.append("  REGISTRY ERROR %s: %s — running it whole"
                         % (r["file"], r["registry_error"]))
    if st.get("n_recorded_failing_stale"):
        # Round 385. Never folded into the count above: this is provenance,
        # not freshness. It is here because a reader who sees "0 failing"
        # over a ledger holding a red result has been told something true
        # and heard something false.
        lines.append("  + %d file(s) LAST RAN RED, at a checkout that has since "
                     "moved — not evidence about this one, and the first thing "
                     "a slow-tier slice should re-run"
                     % st["n_recorded_failing_stale"])
    if st.get("n_scoped"):
        # Never merged into the line above: this is the weaker claim, and it
        # says what it is weaker about.
        lines.append("  + %d file(s) conclusive WITHIN their measured read-scope only "
                     "(%.0f%% combined) — the checkout moved outside what they read"
                     % (st["n_scoped"], 100.0 * st["coverage_scoped"]))
    for r in sorted(st["rows"], key=lambda r: (r["state"] not in FAILING, _uid(r))):
        age = ""
        if r["finished_at"]:
            age = "  %.1fh ago" % ((time.time() - r["finished_at"]) / 3600.0)
        lines.append("  %-38s %-18s %s%s%s%s"
                     % (_uid(r), r["state"],
                        ("%.0fs" % r["seconds"]) if r["seconds"] else "-", age,
                        "   [last run RED]" if recorded_failing_but_stale(r) else "",
                        "   [inherited from a whole-file pass]"
                        if r.get("inherited") else ""))
        if r.get("kind") == LIGHT:
            lines.append("      excludes: %s" % ", ".join(r["unit_tests"]))
        if r["state"] == "stale_harness":
            moved = r["moved_deps"]
            lines.append("      moved: %s%s"
                         % (", ".join(moved[:4]),
                            "" if len(moved) <= 4 else " (+%d more)" % (len(moved) - 4)))
        if r["state"] == "stale_subject":
            lines.append("      moved in scope: %s" % ", ".join(r["moved_scope"][:4]))
        if r["state"] in SCOPED_CONCLUSIVE:
            lines.append("      scope: %s" % ", ".join(r["scope_dirs"] or ["(nothing)"]))
    uncovered = n_units - st["n_conclusive"] - st.get("n_scoped", 0)
    if uncovered:
        lines.append("  NOTE: %d %s are NOT evidence about this checkout."
                     % (uncovered, "file(s)" if n_units == st["n_files"] else "unit(s)"))
    return "\n".join(lines)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["status", "plan", "run", "units"])
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--budget-s", type=float, default=900.0)
    ap.add_argument("--only", default=None,
                    help="comma-separated slow-tier UNIT IDS to run instead of "
                         "the planner's pick (seeding, or re-running a unit a "
                         "round just edited). A unit id is a filename, or a "
                         "filename with [light]/[heavy] when the file is split "
                         "by harness/tier-units.json. Unknown names are an "
                         "error, not a silent no-op.")
    a = ap.parse_args(argv)
    if a.cmd == "units":
        for u in slow_tier_units():
            print("%-38s %-6s %s%s"
                  % (u["id"], u["kind"], ",".join(u["tests"]) or "-",
                     ("   ERROR: " + u["registry_error"]) if u.get("registry_error") else ""))
        return 0
    st = status(ledger_path=a.ledger)
    if a.cmd == "status":
        print(report_text(st))
        return 1 if st["n_failing"] else 0
    if a.only:
        known = set(u["id"] for u in slow_tier_units())
        picked = [f.strip() for f in a.only.split(",") if f.strip()]
        bad = [f for f in picked if f not in known]
        if bad:
            print("not slow-tier units: %s\n(known: %s)"
                  % (", ".join(bad), ", ".join(sorted(known))), file=sys.stderr)
            return 2
    else:
        picked = plan(st, a.budget_s)
    if a.cmd == "plan":
        print("\n".join(picked) or "(nothing to run)")
        return 0
    run_slice(picked, ledger_path=a.ledger, log=lambda s: print(s))
    print(report_text(status(ledger_path=a.ledger)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

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


def status(ledger_path=DEFAULT_LEDGER, tests_dir=TESTS_DIR, whence_root=DEFAULT_WHENCE,
           digest=None):
    digest = checkout_digest(whence_root) if digest is None else digest
    best = latest_by_file(read_entries(ledger_path))
    rows = []
    for f in slow_tier_files(tests_dir):
        e = best.get(f)
        cur = dep_digests(f, tests_dir)
        cur_scope = scope_digests_now(e, whence_root)
        scope = (e or {}).get("subject_scope") or {}
        rows.append({
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
        "n_files": len(rows),
        "n_conclusive": len(covered),
        # Round 361, reported SEPARATELY: files whose evidence survives only
        # because the checkout moved outside their measured read-scope.
        "n_scoped": len(scoped),
        "n_failing": len([r for r in rows if r["state"] in FAILING]),
        # The recall this view has on the CURRENT tree. Round 339's rule:
        # a checker must report its own recall so the gap stays visible.
        "coverage": (float(len(covered)) / len(rows)) if rows else 0.0,
        "coverage_scoped": (float(len(covered) + len(scoped)) / len(rows)) if rows else 0.0,
    }


def _size_prior(test_file, tests_dir=TESTS_DIR):
    """Bytes of the test file, scaled to a fraction of a second.

    Only a TIE-break among unmeasured files (see `plan`). Deliberately tiny
    relative to `default_s` so it can never reorder a file that has a real
    measurement against one that does not.
    """
    try:
        return os.path.getsize(os.path.join(tests_dir, test_file)) / 1e6
    except (IOError, OSError):
        return 0.0


def plan(st, budget_s, default_s=300.0, tests_dir=TESTS_DIR):
    """Which files to run next, in order, inside `budget_s`.

    Order: never-conclusive first (worst evidence first), then oldest
    `finished_at`. Estimated cost is the file's own last measured
    `seconds`, `default_s` when unmeasured. A file whose estimate ALONE
    exceeds the budget is still returned as the sole entry when nothing
    else fits — otherwise a file slower than every budget would never run
    again, which is precisely the silent-truncation failure this module
    exists to prevent.
    """
    def key(r):
        conclusive = r["state"] in CONCLUSIVE
        # Round 343: among files with equally bad evidence, cheapest first.
        # With an EMPTY ledger every estimate is `default_s`, so round 341's
        # `(conclusive, finished_at, file)` key degenerated to ALPHABETICAL —
        # which spends the very first budget a round ever grants on
        # `test_swe_alias_effects.py` (873 s measured, round 341) and covers
        # exactly one file. Falling back to the test file's own SIZE is a
        # prior, not a measurement, and it is only ever a TIE-break: any
        # file with a real `seconds` uses that. Named as a prior in
        # `plan_reasons` so nobody reads it as timing data.
        return (1 if conclusive else 0, r["finished_at"] or 0,
                r["seconds"] or (default_s + _size_prior(r["file"], tests_dir)),
                r["file"])

    ordered = sorted(st["rows"], key=key)
    picked, spent = [], 0.0
    for r in ordered:
        est = r["seconds"] or default_s
        if picked and spent + est > budget_s:
            continue
        picked.append(r["file"])
        spent += est
        if spent >= budget_s:
            break
    return picked


# --------------------------------------------------------------------- run --

def pytest_runner(test_file, tests_dir=TESTS_DIR, timeout_s=3000,
                  whence_root=DEFAULT_WHENCE):
    """The real runner: one pytest process per file, cwd at the repo root.

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
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    args = ["-q", "-p", "no:randomly", os.path.join(tests_dir, test_file)]
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


def run_slice(files, ledger_path=DEFAULT_LEDGER, whence_root=DEFAULT_WHENCE,
              runner=pytest_runner, clock=time.time, log=None,
              tests_dir=TESTS_DIR):
    """Run each file, recording one ledger entry apiece.

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
    for f in files:
        before = checkout_digest(whence_root)
        deps = harness_deps(f, tests_dir)
        deps_before = dep_digests(f, tests_dir, deps)
        t0 = clock()
        r = runner(f)
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
            "schema": 4,
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
        log("%-34s %-8s %6.1fs%s" % (f, outcome, entry["seconds"], flags))
    return written


# ------------------------------------------------------------------ report --

def report_text(st):
    lines = ["slow tier: %d files, %d conclusive against checkout %s (%.0f%% recall), %d failing"
             % (st["n_files"], st["n_conclusive"], st["digest"],
                100.0 * st["coverage"], st["n_failing"])]
    if st.get("n_scoped"):
        # Never merged into the line above: this is the weaker claim, and it
        # says what it is weaker about.
        lines.append("  + %d file(s) conclusive WITHIN their measured read-scope only "
                     "(%.0f%% combined) — the checkout moved outside what they read"
                     % (st["n_scoped"], 100.0 * st["coverage_scoped"]))
    for r in sorted(st["rows"], key=lambda r: (r["state"] not in FAILING, r["file"])):
        age = ""
        if r["finished_at"]:
            age = "  %.1fh ago" % ((time.time() - r["finished_at"]) / 3600.0)
        lines.append("  %-34s %-18s %s%s"
                     % (r["file"], r["state"],
                        ("%.0fs" % r["seconds"]) if r["seconds"] else "-", age))
        if r["state"] == "stale_harness":
            moved = r["moved_deps"]
            lines.append("      moved: %s%s"
                         % (", ".join(moved[:4]),
                            "" if len(moved) <= 4 else " (+%d more)" % (len(moved) - 4)))
        if r["state"] == "stale_subject":
            lines.append("      moved in scope: %s" % ", ".join(r["moved_scope"][:4]))
        if r["state"] in SCOPED_CONCLUSIVE:
            lines.append("      scope: %s" % ", ".join(r["scope_dirs"] or ["(nothing)"]))
    uncovered = st["n_files"] - st["n_conclusive"] - st.get("n_scoped", 0)
    if uncovered:
        lines.append("  NOTE: %d file(s) are NOT evidence about this checkout." % uncovered)
    return "\n".join(lines)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["status", "plan", "run"])
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--budget-s", type=float, default=900.0)
    ap.add_argument("--only", default=None,
                    help="comma-separated slow-tier files to run instead of "
                         "the planner's pick (seeding, or re-running a file a "
                         "round just edited). Unknown names are an error, not "
                         "a silent no-op.")
    a = ap.parse_args(argv)
    st = status(ledger_path=a.ledger)
    if a.cmd == "status":
        print(report_text(st))
        return 1 if st["n_failing"] else 0
    if a.only:
        known = set(slow_tier_files())
        picked = [f.strip() for f in a.only.split(",") if f.strip()]
        bad = [f for f in picked if f not in known]
        if bad:
            print("not slow-tier files: %s" % ", ".join(bad), file=sys.stderr)
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

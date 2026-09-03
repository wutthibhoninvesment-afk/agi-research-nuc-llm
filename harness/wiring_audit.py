#!/usr/bin/env python3
"""wiring_audit.py — what does `run_driver.sh` ACTUALLY run?

Why this exists
---------------
Nobody in this program can answer that question from the record, and three
distinct, expensive failures all reduce to it:

  * **Built, then never wired.** Round 242 (language C) built
    `languages/whence/run_tests_fast.sh` and deferred the driver edit to
    harness(A); rounds 243-246 carried the handoff. Round 388
    (NUC-integration E) built `nuc/run_checks_fast.sh` and deferred it the
    same way, citing the 242->247 precedent by name; six rounds carried it.
    In both windows an entire subsystem's detection latency was bounded by
    the rotation and nothing said so out loud.

  * **Wired, then still reported unwired.** Round 409 wired
    `nuc/run_checks_fast.sh` and said so in bold in its own
    `research-state.md` entry. The next three next-steps blocks re-asserted
    *"`nuc/run_checks_fast.sh` still has 0 references in `run_driver.sh`"*,
    incrementing the carry ordinal each time — FOURTH, FIFTH, SIXTH. The one
    number in the item that was maintained is the one that measures how long
    nobody re-derived the rest. `grep -c run_checks_fast run_driver.sh` was
    **4** the whole time.

  * **Reachable, but not the way the reader assumed.** Round 374 read a
    `health-check PASS (whence-slow clean ... 1014.6s)` line in `driver.log`
    and concluded in writing that the driver runs a pristine checkout of
    HEAD every round. It does not. That inference became round 375's item 3
    and was carried by two rounds.

Each of those is a claim about an edge in one graph, and the graph was never
computed. This file computes it.

What it computes
----------------
Nodes are every tracked `*.py` and `*.sh` file. An EDGE `A -> B` means *A's
own code text names B*. The closure is taken from `run_driver.sh`.

"Names" is deliberately weaker than "executes", and the two directions of
error are both stated rather than hidden:

  * OVER-approximation: a path named on a branch that never runs still
    counts. There is no dataflow analysis here and there will not be one --
    `run_driver.sh` alone is 49.6 KB of bash. Two specific over-approximations
    are worth naming because a reader will otherwise assume they are handled:
    a VERB (`pristine_check.py status` is wired; `check` and `baseline` are
    not, and a file-level graph cannot say so) and a pytest MARKER (most
    `harness/tests/test_swe_*.py` are inside the directory argument and then
    deselected by `-m "not swe_slow"`).
  * UNDER-approximation: a path assembled at run time from values this file
    cannot fold (a loop variable, an env var, a `glob`) is invisible.

Comments are stripped first, and that is not cosmetic. `run_driver.sh` is
roughly nine parts commentary to one part code, and its comments name
instruments it does not run (`harness/swe/slowtier.py run --budget-s N` is a
*recommendation*; `slowtier.py status` is the invocation). A whole-text grep
answers "is X mentioned", which is the question nobody asked.

Path resolution, and the rule the corpus already learned the hard way
---------------------------------------------------------------------
research-state.md's own item says it: *"`skills/run_checks_fast.sh` IS wired
(round 363), so a basename grep lies."* Two pairs of this repo's entry points
share a basename -- `run_tests_fast.sh` (harness + whence) and
`run_checks_fast.sh` (skills + nuc) -- so a basename match is not evidence
about either.

`resolve_reference()` therefore matches the LONGEST path-component suffix
that resolves, and refuses to fall through to a shorter one:

    "$WS/nuc/run_checks_fast.sh"  -> nuc/run_checks_fast.sh   1 match  EDGE
    "run_checks_fast.sh"          -> run_checks_fast.sh       2 matches AMBIGUOUS

An ambiguous reference is recorded (`closure --json` carries them) and is
never an edge. Ambiguity is a finding about the reference, not about the
target.

Three reference forms are read:

  1. **Path literals** in shell tokens and Python string constants, after
     stripping `$WS/`-style prefixes by the suffix rule above.
  2. **`-m dotted.module`**, mapped to `dotted/module.py` or
     `dotted/module/__main__.py`. This matters: `harness/driver_health.py` is
     reached from `run_driver.sh` only through `python3 -m
     harness.driver_health` and never by its path.
  3. **path CONSTRUCTION folds** (`ast`) — `os.path.join(...)` and
     pathlib's `/`. `corpus_check.py` builds every
     checker path with `os.path.join(s, "carryforward_check.py")` and every
     pytest root with `os.path.join(root, "skills", ...)`. A literal-only
     scanner reads that file as reaching nothing, which would have made the
     entire skills corpus look unreachable from the driver. Unresolved names
     in a join contribute nothing but do not veto the constant tail, which is
     exactly what makes the suffix rule the right matcher.

A DIRECTORY reference is an edge to every tracked `.py`/`.sh` beneath it.
This is how `python3 -m pytest harness/tests/` reaches
`harness/tests/conftest.py`, and through its import, `harness/tierbudget.py`.
It is also the reason the closure answers a bigger question than its name
suggests: **not "does the driver invoke this file", but "does anything
automatic touch this file at all".** Everything outside the closure is code
that no per-round check exercises, in any tree, by any route.

The registry
------------
`harness/wiring-registry.json` declares, for every non-excluded ENTRY POINT
(a `*.sh`, or a `*.py` with an `if __name__ == "__main__"` guard), one of
three statuses. It is FAIL-CLOSED: a file with no entry is an error, so a
newly built script classifies itself on the very next round instead of
waiting for someone to notice.

    `wired`    must be in the closure.
    `manual`   must NOT be, and that is BY DESIGN — an operator tool
               (`swap_driver.sh`), an offline demo, a benchmark a round runs
               when it wants the number, or a script that talks to the live
               NUC and must never fire unattended (`nuc/calib_decode.py`).
    `unwired`  must NOT be, and it is a DEBT — someone owes the wiring.
               Carries `owner` and `since_round`, and only this status can
               raise W005.

`manual` exists because the two-status version of this file would have
emitted eleven permanent warnings on this tree for scripts nobody intends to
automate, and a check that warns every round for a state the program chose
gets ignored and then uninstalled — `skills/run_checks_fast.sh`'s stated
reason for its own ERROR/warning split, and skill-authoring's own pitfall.
Collapsing "by design" into "owed" is how a real debt gets lost in noise.

Vendored trees are excluded by declared prefix, each with a reason. A prefix
that matches nothing is itself an error -- an exclusion that outlives its
subject is a mute button, the same rule `case_coverage.py`'s P005 and
`carryforward_check.py`'s K003 already enforce.

Findings
--------
`W001` (ERROR)  a non-vendored entry point with NO registry entry.
`W002` (ERROR)  declared `wired`, not in the closure. The round-242/388
                shape: the deferral outlived the memory of it.
`W003` (ERROR)  declared `unwired` or `manual`, IS in the closure. The
                round-409 shape:
                an acknowledgement that outlived its debt. This is the
                finding that had been true for six rounds when this file was
                written.
`W004` (ERROR)  a registry entry, or a vendored prefix, naming nothing that
                exists.
`W005` (WARN)   an `unwired` entry carried a full rotation (6 rounds) or
                more. `manual` never raises it.
`W006` (WARN)   declared `wired`, and its best route in is a bare textual
                reference from INSIDE A TEST FILE. That is the weakest
                evidence in the tree and it is routinely evidence of the
                opposite: `test_claim_check.py` names `"python3
                bench_elision.py"` in order to assert the command classifies
                MANUAL — i.e. that nothing may run it automatically. `wired`
                stays true (the path is in the closure); the confidence in it
                is what this reports. A warning and not an error because the
                honest verdict is "a human has to look". Never sets the exit code -- round 363's rule, that a
                check which goes FAIL for a debt the program decided to carry
                gets ignored and then uninstalled. The count rides in the
                summary line.

Usage:
    python3 harness/wiring_audit.py closure           # the reachable set
    python3 harness/wiring_audit.py closure --why PATH
    python3 harness/wiring_audit.py orphans           # entry points outside it
    python3 harness/wiring_audit.py check             # against the registry
    python3 harness/wiring_audit.py bootstrap         # propose a registry
    python3 harness/wiring_audit.py refs TARGET --in FILE [--expect N]

Exit codes: 0 = clean, 1 = at least one ERROR (or a failed `--expect`),
2 = usage/IO problem.
"""

import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_ROOT = os.path.normpath(os.path.join(HERE, ".."))

REGISTRY_NAME = os.path.join("harness", "wiring-registry.json")
DRIVER_ROOT = "run_driver.sh"
ROTATION = 6                       # CLAUDE.md ground rule 6: mod-6 track cycle


# --------------------------------------------------------------------------
# Tree enumeration
# --------------------------------------------------------------------------

def tracked_files(root):
    """Every path git tracks, repo-relative, POSIX separators.

    `git ls-files` and not `os.walk`: the walk would pick up `__pycache__`,
    the untracked files a separate autonomous system writes into this tree
    (allowlisted in `state/known-standing-dirty-paths.json` since round 291),
    and `node_modules/` -- 2258 tracked paths against a working tree an order
    of magnitude larger.
    """
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                         capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split("\0") if p]


def code_nodes(paths):
    """The subset of tracked paths this graph has nodes for."""
    return sorted(p for p in paths if p.endswith(".py") or p.endswith(".sh"))


MAIN_GUARD_RE = re.compile(r"^if\s+__name__\s*==\s*['\"]__main__['\"]\s*:",
                           re.M)


def _has_main_guard(src):
    """True if `src` has a MODULE-LEVEL `if __name__ == "__main__":`.

    Round 421: this used to be `MAIN_GUARD_RE.search(text)` over the raw file,
    and a raw-text regex cannot tell a guard from a guard QUOTED INSIDE A
    STRING. `harness/tests/test_verb_audit.py` builds a synthetic entry-point
    fixture whose source text — inside a triple-quoted constant — contains the
    line `if __name__ == "__main__":`, and the test file was thereupon
    declared an entry point and raised a W001 asking someone to wire it. A
    test-fixture string is not a program.

    The AST answers the question the regex was approximating, and only at
    module level: a guard nested inside a function or a class does not make
    the file runnable either. The regex survives as the fallback for a file
    `ast` cannot parse, where a weak answer beats no answer — that path is
    fail-OPEN (it may over-declare), which is the safe direction here because
    an over-declared entry point costs one registry line and an
    under-declared one silently escapes the fail-closed W001 rule entirely.
    """
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return bool(MAIN_GUARD_RE.search(src))
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if not isinstance(t, ast.Compare) or len(t.ops) != 1:
            continue
        if not isinstance(t.ops[0], ast.Eq):
            continue
        left, right = t.left, t.comparators[0]
        names = {n.id for n in (left, right) if isinstance(n, ast.Name)}
        consts = {c.value for c in (left, right)
                  if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        if "__name__" in names and "__main__" in consts:
            return True
    return False


def is_entry_point(root, path):
    """A file a human or a script can plausibly *run*.

    Every `.sh`, and every `.py` with a `__main__` guard. Import-only modules
    are nodes in the graph but are not declared in the registry: "is anything
    running this" is not a well-posed question for a library, and a registry
    that asked it of 245 more files would be noise nobody reads.
    """
    if path.endswith(".sh"):
        return True
    if not path.endswith(".py"):
        return False
    try:
        with open(os.path.join(root, path), "r", encoding="utf-8",
                  errors="replace") as fh:
            return _has_main_guard(fh.read())
    except OSError:
        return False


# --------------------------------------------------------------------------
# Comment stripping
# --------------------------------------------------------------------------

def strip_shell_comments(text):
    """Drop whole-line `#` comments, keep everything else verbatim.

    Deliberately NOT a trailing-comment stripper. `${x#y}`, `$#`, `#` inside
    a double-quoted string and a `#` in a URL are all common in this repo's
    shell, and every one of them would need a real tokenizer to get right.
    Whole-line comments are where the commentary actually lives -- 90% of
    `run_driver.sh` -- so this removes the false positives that matter and
    invents no new ones. Line count is preserved so reported line numbers
    stay true.
    """
    out = []
    for line in text.split("\n"):
        out.append("" if line.lstrip().startswith("#") else line)
    return "\n".join(out)


def strip_python_comments(text):
    """Drop `#` comments and docstrings; keep every other string literal.

    Keeping ordinary string literals is the whole point -- a subprocess call
    carries its target as a string. What has to go is the prose: this repo's
    modules open with 100+ line docstrings that name other instruments, and
    `wiring_audit.py`'s own docstring names a dozen files it never runs.

    A docstring is detected structurally, as a STRING token that begins a
    logical line (preceded by NEWLINE / NL / INDENT / DEDENT / start-of-file).
    That is exactly the position an expression-statement string occupies, and
    it needs no `ast` round-trip, so it survives a file `ast` would reject.

    Falls back to `strip_shell_comments` on a tokenize error, which is the
    conservative direction: it keeps too much rather than too little.
    """
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return strip_shell_comments(text)

    lines = text.split("\n")
    blanks = []                                    # (row0, col0, row1, col1)
    at_line_start = True
    for tok in toks:
        ttype = tok.type
        if ttype == tokenize.COMMENT:
            blanks.append((tok.start[0], tok.start[1], tok.end[0], tok.end[1]))
            continue
        if ttype in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                     tokenize.DEDENT, tokenize.ENCODING):
            if ttype in (tokenize.NL, tokenize.NEWLINE):
                at_line_start = True
            continue
        if ttype == tokenize.STRING and at_line_start:
            blanks.append((tok.start[0], tok.start[1], tok.end[0], tok.end[1]))
        at_line_start = False

    for (r0, c0, r1, c1) in blanks:                # blank out, keep geometry
        for row in range(r0, r1 + 1):
            idx = row - 1
            if idx >= len(lines):
                break
            line = lines[idx]
            start = c0 if row == r0 else 0
            end = c1 if row == r1 else len(line)
            lines[idx] = line[:start] + " " * max(0, end - start) + line[end:]
    return "\n".join(lines)


def read_text(root, path):
    try:
        with open(os.path.join(root, path), "r", encoding="utf-8",
                  errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def code_text(root, path):
    raw = read_text(root, path)
    if not raw:
        return ""
    if path.endswith(".py"):
        return strip_python_comments(raw)
    return strip_shell_comments(raw)


# --------------------------------------------------------------------------
# Reference extraction
# --------------------------------------------------------------------------

# A shell/argv token that could be a path. Kept generous on the left (the
# suffix rule below throws away `$WS/`, `"`, `$(dirname ...)`) and strict on
# the right.
# Two alternatives, because a directory can be written either way. The first
# needs a `/` with a component on both sides (`harness/tests`, `$WS/a/one.sh`);
# the second is the bare trailing-slash form (`data/`), which the first cannot
# match and which `pytest data/` is a perfectly ordinary way to write.
TOKEN_RE = re.compile(r"[A-Za-z0-9_./$\{\}\-]*[A-Za-z0-9_\-]"
                      r"(?:/[A-Za-z0-9_.\-]+)+/?"
                      r"|[A-Za-z0-9_\-][A-Za-z0-9_.\-]*/")
DASH_M_RE = re.compile(r"-m\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_]"
                       r"[A-Za-z0-9_]*)+)")
BARE_SCRIPT_RE = re.compile(r"(?<![A-Za-z0-9_./\-])"
                            r"([A-Za-z0-9_\-]+\.(?:py|sh))"
                            r"(?![A-Za-z0-9_./\-])")
# `./name.sh` — the form `run_driver.sh` uses for the one script it launches
# per round: `CLAUDE_CMD="${DRIVER_CLAUDE_CMD:-./claude-wrapper.sh}"`.
# TOKEN_RE wants a `/` with components on BOTH sides and BARE_SCRIPT_RE's
# lookbehind rejects the leading slash, so without this the driver's own
# wrapper — the process every round actually runs in — was outside its own
# closure. Found by checking a prediction that named it, not by review.
DOT_SLASH_RE = re.compile(r"\.{1,2}/([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*)")


def _parse_for_ast(raw):
    """`(tree, docstring_node_ids)` for RAW python source, or `(None, set())`.

    The AST passes read the ORIGINAL source, never the comment-stripped text,
    and this is not an optimisation — it is a correctness fix found by
    tracing one missing edge. `strip_python_comments` blanks a docstring in
    place to keep line geometry, which leaves `def f():` followed by blank
    lines: a function with an empty body, which is a SyntaxError. **320 of
    this repo's 420 tracked `.py` files fail to parse after stripping**, and
    every `ast`-based pass was silently returning `[]` for all of them. The
    symptom was that `corpus_check.py` — which builds every checker path with
    `os.path.join` — appeared to reach nothing built that way.

    Docstrings are excluded structurally instead: the first statement of a
    module, class or function, when it is a string constant. That is the same
    thing the blanking was for, done where it cannot break the parse.
    """
    try:
        tree = ast.parse(raw)
    except (SyntaxError, ValueError):
        return None, set()
    doc_ids = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            doc_ids.add(id(first.value))
    return tree, doc_ids


def _string_constants(tree, doc_ids):
    """Every non-docstring string constant in Python source, WITH its line.

    Round 481 (harness A): the three AST passes below used to return bare
    values and `references()` recorded every edge they produced at line 0.
    `ast` gives every node a 1-based `lineno` for free; dropping it cost the
    graph the location of 721 of its 1043 edges — 69 % — and the loss was
    invisible because the one renderer, `best[1] or "-"`, spells "line 0" and
    "line unknown" identically. See `references()`.
    """
    if tree is None:
        return []
    return [(n.value, n.lineno) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in doc_ids]


def _constructed_paths(tree):
    """Fold path CONSTRUCTION into candidate `(path suffix, line)` pairs.

    Unresolved arguments (a Name, a call, an f-string) contribute nothing and
    RESET the accumulation, so `os.path.join(s, "carryforward_check.py")`
    yields `carryforward_check.py` and `os.path.join(root, "skills",
    "skill-authoring", "scripts")` yields `skills/skill-authoring/scripts`.
    The suffix matcher then decides whether that is enough to identify a
    unique file -- which is the honest split of labour: this function says
    what is known, `resolve_reference` says whether it is enough.
    """
    if tree is None:
        return [], set()
    # Which constructed paths sit in a PYTEST ARGUMENT LIST? The module-level
    # "does this file mention pytest" gate was too coarse in exactly one way,
    # and it showed up immediately: `nuc/tests/test_constant_audit.py` both
    # imports pytest and shells out, and its `os.path.join(ROOT, "nuc")` is
    # the AUDITED directory, not a test root. It pulled all of `nuc/` into
    # the closure and turned six correct `manual` declarations into errors.
    #
    # The syntactic question is local and answerable: is this join inside a
    # list/tuple/call one of whose other elements is the string `pytest`?
    # `corpus_check.py` writes `["-m", "pytest", "-q", os.path.join(root,
    # "skills", "skill-authoring", "scripts"), ...]`, which is a yes;
    # `os.path.join(ROOT, "nuc")` standing alone is a no.
    pytest_ctx = set()
    for node in ast.walk(tree):
        elts = []
        if isinstance(node, (ast.List, ast.Tuple)):
            elts = node.elts
        elif isinstance(node, ast.Call):
            elts = list(node.args)
        if not any(isinstance(e, ast.Constant) and isinstance(e.value, str)
                   and "pytest" in e.value for e in elts):
            continue
        for inner in ast.walk(node):
            pytest_ctx.add(id(inner))

    dir_ok = set()
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = None
        if isinstance(fn, ast.Attribute):
            name = fn.attr
        elif isinstance(fn, ast.Name):
            name = fn.id
        if name != "join":
            continue
        parts = []
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                parts.append(arg.value)
            else:
                parts = []                          # unresolved: start over
        if parts:
            cand = "/".join(p.strip("/") for p in parts if p)
            out.append((cand, node.lineno))
            if id(node) in pytest_ctx:
                dir_ok.add(cand)

    # pathlib's `/`. `nuc/tests/test_reachability_check.py` loads the module
    # under test with
    #     spec_from_file_location(..., Path(__file__).resolve().parents[1]
    #                                  / "reachability_backfill.py")
    # which is path construction by any reading, just not `os.path.join`'s.
    # A `/` BinOp with a string operand cannot be arithmetic — `"a" / "b"` is
    # a TypeError — so this is unambiguous.
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            for side in (node.right, node.left):
                if isinstance(side, ast.Constant) \
                        and isinstance(side.value, str) and side.value:
                    out.append((side.value.strip("/"), side.lineno))
    return out, dir_ok


def _imports(tree):
    """`import a.b` / `from a.b import c` as `(dotted name, line)` pairs."""
    if tree is None:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((a.name, node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.append((node.module, node.lineno))
            out.extend((node.module + "." + a.name, node.lineno)
                       for a in node.names)
    return out


def module_to_paths(dotted, importer=""):
    """Candidate tracked paths for a dotted module name, seen from `importer`.

    A dotted name is resolved against every ANCESTOR DIRECTORY of the file
    doing the importing, nearest first. That is not a heuristic dressed up --
    it is what these files literally do:

        harness/tests/test_swe_campaign.py:12
            sys.path.insert(0, os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
        harness/tests/test_guardpin.py:17
            from swe import guardpin as G

    `swe.guardpin` is not a tracked path; `harness/swe/guardpin.py` is, and
    the only thing connecting them is that `harness/` is an ancestor of the
    importer and is on `sys.path` at run time. Resolving from the importer
    outwards gets it right and, as a bonus, keeps stdlib imports out: `import
    ast` from a test asks for an `ast.py` beside the importer, then one in
    each ancestor directory up to the repo root, and this repo tracks none of
    them.

    Round 413 built `harness/swe/guardpin.py` and round 413's own test file
    imports it in exactly this form. Without this rule the audit reported it
    as an orphan two rounds later -- a false positive on the newest instrument
    in the tree, which is the one class of error that would have made this
    check unusable.
    """
    base = dotted.replace(".", "/")
    dirs, cur = [], os.path.dirname(importer)
    while True:
        dirs.append(cur)
        if not cur:
            break
        cur = os.path.dirname(cur)
    out = []
    for d in dirs:
        pre = (d + "/") if d else ""
        out.extend([pre + base + ".py", pre + base + "/__main__.py",
                    pre + base + "/__init__.py"])
    return out


class Index:
    """Suffix index over the tracked tree."""

    def __init__(self, paths):
        self.files = set(paths)
        self.dirs = set()
        for p in paths:
            parts = p.split("/")
            for i in range(1, len(parts)):
                self.dirs.add("/".join(parts[:i]))
        self._by_suffix = {}
        for p in paths:
            parts = p.split("/")
            for i in range(len(parts)):
                self._by_suffix.setdefault("/".join(parts[i:]), set()).add(p)
        self._dir_by_suffix = {}
        for d in self.dirs:
            parts = d.split("/")
            for i in range(len(parts)):
                self._dir_by_suffix.setdefault("/".join(parts[i:]),
                                               set()).add(d)

    def files_under(self, directory):
        pre = directory.rstrip("/") + "/"
        return sorted(p for p in self.files if p.startswith(pre))


def resolve_reference(index, token, base_dir=""):
    """Longest resolving path-component suffix, or an ambiguity report.

    Returns `(kind, value)` where kind is one of:
        "file"       value = repo-relative path
        "dir"        value = repo-relative directory
        "ambiguous"  value = sorted list of candidates
        None         value = None
    """
    token = token.strip().strip("'\"")
    token = token.rstrip("/") if token.endswith("/") else token
    if not token:
        return (None, None)
    parts = [p for p in token.split("/") if p not in ("", ".")]
    # A RELATIVE reference is relative to something, and for these scripts
    # that something is their own directory — `languages/whence/
    # run_tests_fast.sh` opens with `cd "$(dirname "${BASH_SOURCE[0]}")"` and
    # then says `pytest ... tests/`. Resolved globally, the bare token `tests`
    # is ambiguous across five `tests/` directories and yields no edge at all,
    # which silently removed the entire whence subtree from the closure.
    # Tried FIRST, and only as an exact hit, so it can never manufacture a
    # match the suffix rule would have called ambiguous.
    if base_dir and not token.startswith(("/", "$")):
        local = os.path.normpath(os.path.join(base_dir, "/".join(parts)))
        if local in index.files:
            return ("file", local)
        if local in index.dirs:
            return ("dir", local)
    for i in range(len(parts)):
        suffix = "/".join(parts[i:])
        if not suffix:
            continue
        hit = index._by_suffix.get(suffix)
        if hit:
            if len(hit) == 1:
                return ("file", next(iter(hit)))
            return ("ambiguous", sorted(hit))
        dhit = index._dir_by_suffix.get(suffix)
        if dhit:
            if len(dhit) == 1:
                return ("dir", next(iter(dhit)))
            return ("ambiguous", sorted(dhit))
    return (None, None)


# A directory only makes code run when something HANDS IT TO A RUNNER.
# Without this gate the driver's own `mkdir -p "$WS/state"` — a data
# directory, created before any round starts — pulled all 107 tracked
# `.py`/`.sh` files under `state/` into the closure, including six round-137
# snapshot copies of the Whence interpreter that nothing has executed since
# 2026. Measured: 294 nodes / 100 entry points before the gate, and the first
# `--why` trace on any of them read `run_driver.sh:239`, the `mkdir`.
#
# The gate is a NECESSARY condition, not a sufficient one, and it is applied
# at different granularities because the two languages give different
# evidence:
#   * shell — per LINE. `mkdir -p "$WS/state"` names no runner;
#     `python3 -m pytest -q harness/tests/` does. A line is the right unit
#     because shell has one command per line here.
#   * python — per ARGUMENT LIST. A path assembled by `os.path.join` and
#     stored in a table (`corpus_check.py`'s checker list) is syntactically
#     nowhere near the `subprocess.run` that eventually executes it, so a
#     call-site test resolves nothing; what IS local is whether the join sits
#     in a list one of whose other elements is the string `pytest`. A
#     module-level "does this file mention pytest at all" gate was tried
#     first and was too coarse — see `_constructed_paths`.
#
# FILE references are NOT gated. A `.py` or `.sh` path written into code is
# already specific enough to be evidence on its own, and gating it would
# lose `HEALTH_SCRIPT="$WS/harness/run_tests_fast.sh"` — an assignment, on a
# line with no runner on it, whose whole purpose is to be run four lines
# later.
# How strong is the evidence that A reaches B? Four kinds, and the ranking
# is not decoration -- it is what separates "a runner is pointed at this file"
# from "this file's name appears in someone's source text".
#
# The case that forced it: `skills/.../test_claim_check.py` asserts that
# `"python3 bench_elision.py"` and `"python3 live_smoke.py cli-guards"`
# classify MANUAL -- i.e. it is the test that makes sure those commands are
# NEVER run automatically. A path-literal match read that as the driver
# reaching both benchmarks. Being named in a refusal is the opposite of being
# run, and it is the same failure as `xref_check.py`'s `FROZEN_PREFIXES` one
# level subtler: there the string named a directory to skip, here it names a
# command to refuse.
#
# `path` edges are kept, because dropping them would lose every real
# `bash "$WS/nuc/run_checks_fast.sh"`. They are kept and LABELLED, and W006
# reports any `wired` entry whose only route in is a weak one.
# `join` sits above `path` because CONSTRUCTING a path is different in kind
# from mentioning one. Every one of `nuc/nuc-adapter-copy.py`,
# `nuc/reachability_backfill.py` and `nuc/taskscript/run.py` is genuinely
# executed by its test — two through `importlib.util.spec_from_file_location`,
# one through `subprocess.run([sys.executable, RUN, ...])` — and all three
# were flagged as weakly reached until the constructed forms were told apart
# from the bare ones. Without the split, W006's true-positive rate on this
# tree was 2 of 5.
STRENGTH = {"import": 3, "dashm": 3, "dir": 2, "join": 2, "path": 1}
WEAK_KINDS = ("path",)


def edge_line(lineno):
    """Render an edge's line for a human. `-` means THE GRAPH HAS NO LINE.

    Round 481 (harness A): this used to be written inline as a falsy-or at
    four sites, and for 66 rounds it was a lie by falsy-zero. The three
    `ast` passes in `references()` recorded every edge they produced at line
    0 — 721 of this tree's 1043 edges, 69 % — and rendering 0 that way
    spells it identically to "no line is claimed". The registry's 80
    `"<file>:-"` pins were read by round 475 as a convention; they were the
    symptom. The passes now carry `node.lineno`, `test_wiring_audit.py` pins
    that NO edge in this tree has line 0, and this function survives as the
    honest renderer for a caller holding an edge that genuinely has none.
    """
    return str(lineno) if lineno else "-"


def is_test_file(path):
    """A pytest file, by this repo's own two conventions."""
    return path.endswith(".py") and (
        os.path.basename(path).startswith("test_") or "/tests/" in path)

# The gate is `pytest`, and only `pytest`, after a wider one failed on this
# tree in a way worth writing down. A gate of "any runner token on the line"
# let `python3 nuc/constant_audit.py audit nuc/` through: `nuc/` is an
# argument to the AUDITOR, not to the interpreter, and the line has `python3`
# on it either way. It pulled 158 extra nodes in and turned six correct
# `manual` declarations into W003 errors.
#
# Pointing a test runner at a directory is the one construct in this repo
# that makes a whole directory of code EXECUTE. Everything else that takes a
# directory — a linter, an auditor, `mkdir`, a scan root — reads the files.
# Naming that construct exactly is both more accurate and more honest than a
# list of interpreter names.
#
# The cost is stated: a directory handed to something else that really does
# execute it would be missed. That is the UNDER-approximating direction, and
# under-approximation here is fail-closed — an unseen edge makes a file look
# unreached, which forces a declaration rather than silently granting one.
SHELL_RUNNER_RE = re.compile(r"(?<![A-Za-z0-9_])pytest(?![A-Za-z0-9_])")


def references(root, path, index):
    """Every reference this file's CODE makes, resolved.

    Returns `(edges, ambiguous)` where `edges` maps a target path to the
    1-based line number of the first reference that reached it, and
    `ambiguous` is a list of `(line, token, candidates)`.
    """
    text = code_text(root, path)
    edges, ambiguous = {}, []
    lines = text.split("\n")
    is_py = path.endswith(".py")
    tree, doc_ids = _parse_for_ast(read_text(root, path)) if is_py \
        else (None, set())

    def put(target, lineno, kind):
        old = edges.get(target)
        if old is None or STRENGTH[kind] > STRENGTH[old[1]]:
            edges[target] = (lineno, kind)

    base_dir = os.path.dirname(path)

    def add(tok, lineno, allow_dir, kind="path"):
        rkind, val = resolve_reference(index, tok, base_dir)
        if rkind == "file":
            put(val, lineno, kind)
        elif rkind == "dir":
            if not allow_dir:
                return
            for f in index.files_under(val):
                if f.endswith(".py") or f.endswith(".sh"):
                    put(f, lineno, "dir")
        elif rkind == "ambiguous":
            ambiguous.append((lineno, tok, val))

    for i, line in enumerate(lines, 1):
        # In Python the raw line scan is the same weak evidence a bare string
        # constant is — `FROZEN_PREFIXES = ("state/swe", ...)` is a LINE too —
        # so directory edges there come only from the `os.path.join` fold
        # below. In shell there is no such fold and the line IS the command.
        allow_dir = False if is_py else bool(SHELL_RUNNER_RE.search(line))
        for m in TOKEN_RE.finditer(line):
            add(m.group(0), i, allow_dir)
        for m in DASH_M_RE.finditer(line):
            for cand in module_to_paths(m.group(1), path):
                if cand in index.files:
                    put(cand, i, "dashm")
                    break
        for m in BARE_SCRIPT_RE.finditer(line):
            add(m.group(1), i, False)
        for m in DOT_SLASH_RE.finditer(line):
            add(m.group(1), i, allow_dir)

    if is_py:
        # Bare string constants may name a FILE but never a DIRECTORY.
        # `xref_check.py` carries `FROZEN_PREFIXES = ("state/swe", ...)` — a
        # module constant listing the directories it refuses to scan — and a
        # matcher that reads a directory out of a bare constant cannot tell
        # an exclusion list from an inclusion list. It read that tuple as
        # "the driver runs everything under state/swe", pulling 35 frozen
        # round-artifact scripts into the closure with `--why` traces that
        # pointed straight at the line saying they are frozen.
        #
        # `os.path.join(...)` is different in kind, not degree: it is path
        # CONSTRUCTION. A module that assembles a path from parts is building
        # something to hand to the filesystem, which is why `corpus_check.py`'s
        # `os.path.join(root, "skills", "skill-authoring", "scripts")` — the
        # pytest root for 759 unit tests, syntactically nowhere near the
        # `subprocess.run` that executes it — is kept.
        for s, ln in _string_constants(tree, doc_ids):
            if "/" in s or s.endswith(".py") or s.endswith(".sh"):
                add(s, ln, False)
        built, dir_ok = _constructed_paths(tree)
        for s, ln in built:
            # No `"/" in s` requirement here, unlike the bare-constant pass
            # above: `os.path.join(root, "data")` is a whole path even though
            # the constant half has no separator in it. A directory only
            # counts when the join sits in a pytest argument list.
            if s:
                add(s, ln, s in dir_ok, kind="join")
        for dotted, ln in _imports(tree):
            for cand in module_to_paths(dotted, path):
                if cand in index.files:
                    put(cand, ln, "import")
                    break
    return edges, ambiguous


# --------------------------------------------------------------------------
# Closure
# --------------------------------------------------------------------------

class Graph:
    def __init__(self, root, roots=(DRIVER_ROOT,)):
        self.root = root
        self.tracked = tracked_files(root)
        self.index = Index(self.tracked)
        self.nodes = code_nodes(self.tracked)
        self.node_set = set(self.nodes)
        self.roots = [r for r in roots]
        self.edges = {}
        self.ambiguous = {}
        self._reached = None
        self._via = {}

    def _expand(self, path):
        if path not in self.edges:
            e, amb = references(self.root, path, self.index)
            self.edges[path] = {t: v for t, v in e.items()
                                if t in self.node_set and t != path}
            if amb:
                self.ambiguous[path] = amb
        return self.edges[path]

    def closure(self):
        if self._reached is not None:
            return self._reached
        # BREADTH-first, and the order is load-bearing rather than a taste
        # call: `best_incoming` ranks a candidate edge by the DEPTH of its
        # source before it looks at the edge kind, so `nuc/run_checks_fast.sh`
        # is judged on `run_driver.sh:526` (depth 0) and not on the depth-3
        # route through `harness/tests/test_nuc_health_line.py` that a
        # depth-first traversal happened to find first. Under DFS the driver's
        # own four health checks all reported as weakly reached.
        from collections import deque
        seen, queue = set(), deque()
        self._depth = {}
        for r in self.roots:
            if r in self.node_set:
                seen.add(r)
                queue.append(r)
                self._via[r] = None
                self._depth[r] = 0
        while queue:
            cur = queue.popleft()
            for tgt, (ln, kind) in sorted(self._expand(cur).items()):
                if tgt not in seen:
                    seen.add(tgt)
                    self._via[tgt] = (cur, ln, kind)
                    self._depth[tgt] = self._depth[cur] + 1
                    queue.append(tgt)
        self._reached = seen
        return seen

    def why(self, path):
        """The chain of `(file, line)` edges that reaches `path`."""
        self.closure()
        if path not in self._reached:
            return None
        chain, cur = [], path
        while self._via.get(cur):
            src, ln, kind = self._via[cur]
            chain.append((src, ln, cur, kind))
            cur = src
        chain.reverse()
        return chain

    def best_incoming(self, path):
        """The best edge into `path` from anywhere inside the closure.

        "Best" is `(shallowest source, then strongest kind, then the source
        path)`. `why()` reports the route the search took; this reports the
        best evidence that exists, which is the question the registry
        actually asks. A file imported by a test AND named in a refusal
        string must not be judged on whichever one the traversal reached
        first.

        Round 481 (harness A): the source path is in the sort key, and the
        scan runs over `sorted(self._reached)`, because WITHOUT THEM THIS
        FUNCTION WAS NONDETERMINISTIC ACROSS PROCESSES. `_reached` is a set
        of strings and CPython randomises string hashing per process, so a
        tie — same depth, same kind, and `languages/whence/curecheck.py` is
        imported by thirty-odd sibling test files at the same depth — was
        broken by whatever order that process happened to iterate in. Three
        consecutive runs on an unchanged tree named `tests/test_v24.py:159`,
        `tests/test_lexer_guest_parity.py:420` and `tests/test_v34.py:58`.
        Everything downstream inherited it: the `via` column
        `cmd_bootstrap` proposes, the "strongest incoming edge" line of
        `--why`, and the file:line inside every W003 and W006 finding. A
        registry field generated by one draw from that distribution cannot
        be re-derived by a later round, which is exactly what
        `harness/viapin.py` has to do.
        """
        self.closure()
        best, best_key = None, None
        for src in sorted(self._reached):
            edge = self.edges.get(src, {}).get(path)
            if edge is None:
                continue
            key = (self._depth.get(src, 10 ** 6), -STRENGTH[edge[1]], src)
            if best_key is None or key < best_key:
                best, best_key = (src, edge[0], edge[1]), key
        return best


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

def load_registry(root):
    p = os.path.join(root, REGISTRY_NAME)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def current_round(root):
    p = os.path.join(root, "state", "round_counter")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def excluded_prefixes(registry):
    """Declared exclusions, both kinds, as a flat list of prefixes.

    Two lists rather than one because the reasons are not the same kind of
    reason and merging them would lose that: `vendored_prefixes` is code this
    program did not write and must not wire, `frozen_prefixes` is code this
    program wrote to run ONCE, in one round, and deliberately keeps as a
    record. A single `excluded` list would let a vendored tree's reason be
    read as an excuse for one of ours.
    """
    reg = registry or {}
    return ([v["prefix"] for v in reg.get("vendored_prefixes", [])]
            + [v["prefix"] for v in reg.get("frozen_prefixes", [])])


def is_excluded(path, prefixes):
    return any(path.startswith(pfx) for pfx in prefixes)


def audit(root, graph=None, registry=None):
    graph = graph or Graph(root)
    registry = registry if registry is not None else load_registry(root)
    reached = graph.closure()
    findings = []

    if registry is None:
        findings.append(("W004", REGISTRY_NAME, "registry file is absent"))
        return {"findings": findings, "reached": sorted(reached),
                "entry_points": [], "n_declared": 0, "warnings": 0}

    prefixes = excluded_prefixes(registry)
    for key in ("vendored_prefixes", "frozen_prefixes"):
        for v in registry.get(key, []):
            if not any(p.startswith(v["prefix"]) for p in graph.tracked):
                findings.append(("W004", v["prefix"],
                                 "%s matches nothing tracked" % key))

    eps = [p for p in graph.nodes
           if is_entry_point(root, p) and not is_excluded(p, prefixes)]
    declared = registry.get("entry_points", {})
    rnd = current_round(root)
    warnings = 0

    for path in sorted(declared):
        if path not in graph.node_set:
            findings.append(("W004", path,
                             "registry names a path that does not exist"))

    for path in eps:
        entry = declared.get(path)
        if entry is None:
            findings.append(("W001", path,
                             "entry point with no registry entry"))
            continue
        status = entry.get("status")
        if status == "wired" and path not in reached:
            findings.append(("W002", path,
                             "declared wired, not reachable from "
                             + ", ".join(graph.roots)))
        elif status in ("unwired", "manual") and path in reached:
            edge = graph.best_incoming(path)
            # A file whose ONLY route in is text inside a test is not
            # "reachable" in the sense this status is about, and treating it
            # as such would force the wrong declaration on the two files most
            # in need of the right one. `harness/live_smoke.py` is reached
            # solely because `test_claim_check.py` asserts that `python3
            # live_smoke.py cli-guards` classifies PRICED — the test exists
            # precisely so nothing runs it unattended. Calling that "wired"
            # and then having to defend it is the tail wagging the dog: W006
            # already reports the weakness, so W003 defers to it rather than
            # contradicting it.
            weak_only = (edge is not None and edge[2] in WEAK_KINDS
                         and is_test_file(edge[0]))
            if not weak_only:
                findings.append(("W003", path,
                                 "declared %s but IS reachable" % status
                                 + (" via %s:%s [%s]"
                                    % (edge[0], edge_line(edge[1]), edge[2])
                                    if edge else "")))
        elif status not in ("wired", "unwired", "manual"):
            findings.append(("W004", path,
                             "unknown status %r" % (status,)))
        if status == "wired" and path in reached and path not in graph.roots:
            edge = graph.best_incoming(path)
            if edge is not None and edge[2] in WEAK_KINDS \
                    and is_test_file(edge[0]):
                warnings += 1
                findings.append(("W006", path,
                                 "reached ONLY as text inside a test "
                                 "(%s:%s) — nothing imports it and no runner "
                                 "is pointed at it"
                                 % (edge[0], edge_line(edge[1]))))
        if status == "unwired" and rnd is not None:
            since = entry.get("since_round")
            if isinstance(since, int) and rnd - since >= ROTATION:
                warnings += 1
                findings.append(("W005", path,
                                 "unwired since round %d — carried %d rounds "
                                 "(>= one rotation)" % (since, rnd - since)))
    return {"findings": findings, "reached": sorted(reached),
            "entry_points": eps, "n_declared": len(declared),
            "warnings": warnings}


ERROR_CODES = ("W001", "W002", "W003", "W004")


# --------------------------------------------------------------------------
# refs — re-derive a reference-count claim
# --------------------------------------------------------------------------

def refs(root, target, in_file):
    """Count references to `target` inside `in_file`, raw and code-only.

    This is the primitive the false ledger item needed. It reports BOTH
    numbers because they answer different questions: the raw count is "is it
    mentioned", the code count is "does it run".
    """
    index = Index(tracked_files(root))
    resolved = target
    if target not in index.files:
        kind, val = resolve_reference(index, target)
        if kind == "file":
            resolved = val
        elif kind == "ambiguous":
            return {"target": target, "error": "ambiguous", "candidates": val}
        else:
            return {"target": target, "error": "unresolved"}

    try:
        with open(os.path.join(root, in_file), "r", encoding="utf-8",
                  errors="replace") as fh:
            raw = fh.read()
    except OSError as exc:
        return {"target": resolved, "error": str(exc)}
    code = code_text(root, in_file)

    def hits(text):
        out = []
        for i, line in enumerate(text.split("\n"), 1):
            for m in TOKEN_RE.finditer(line):
                kind, val = resolve_reference(index, m.group(0))
                if kind == "file" and val == resolved:
                    out.append(i)
                    break
            else:
                for m in DASH_M_RE.finditer(line):
                    if resolved in module_to_paths(m.group(1), in_file):
                        out.append(i)
                        break
        return out

    return {"target": resolved, "in": in_file,
            "raw_lines": hits(raw), "code_lines": hits(code),
            "raw": len(hits(raw)), "code": len(hits(code))}


def token_refs(root, token, in_file):
    r"""Count occurrences of a literal TOKEN inside `in_file`, raw and code-only.

    The dual of `refs`. `refs` answers *how many times does this FILE get
    referenced here*, and resolves its target through the path index. This
    answers *does this LITERAL STRING occur here at all*, and resolves
    nothing -- the token is matched verbatim.

    It exists because the claims a status document makes about a file come in
    two polarities and only one of them had a re-derivation. Round 415 built
    `refs` for the PRESENCE claim (*X has 0 references in Y* -- a count that
    can be re-counted). Round 423 found the ABSENCE claim (*Y still has no
    S009 finding class*), which is not a count at all: it asserts that a
    named thing does not occur in a named file, and the cheapest possible
    refutation is to find it there.

    The raw/code split is kept verbatim from `refs`, because it carries the
    same distinction and the same trap. A file may MENTION a token in a
    comment that says the thing does not exist yet, which does not make the
    thing exist; a file that mentions it in CODE is running it. So:

        code > 0            the named thing is implemented -- the absence
                            claim is refutable on its face
        raw > 0, code == 0  mentioned only in prose. Under-specified, not
                            false: the author may have meant either.
        raw == 0            nothing here contradicts the claim

    Word boundaries are `(?<![\w-])` / `(?![\w-])` rather than `\b`, so
    `S009` does not match inside `S0091` and `--cap` does not match inside
    `--capture`. `-` is inside the boundary class on purpose: every CLI flag
    in this tree is a token whose neighbours would otherwise be invisible to
    `\b`, which treats `-` as a boundary and would report `--cap` present in
    `--capture`.
    """
    index = Index(tracked_files(root))
    resolved = in_file
    if in_file not in index.files:
        kind, val = resolve_reference(index, in_file)
        if kind == "file":
            resolved = val
        elif kind == "ambiguous":
            return {"token": token, "in": in_file,
                    "error": "ambiguous", "candidates": val}
        else:
            return {"token": token, "in": in_file, "error": "unresolved"}

    raw = read_text(root, resolved)
    if not raw:
        return {"token": token, "in": resolved,
                "error": "unreadable or empty: %s" % resolved}
    code = code_text(root, resolved)
    pat = re.compile(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])")

    def hits(text):
        return [i for i, line in enumerate(text.split("\n"), 1)
                if pat.search(line)]

    return {"token": token, "in": resolved,
            "raw_lines": hits(raw), "code_lines": hits(code),
            "raw": len(hits(raw)), "code": len(hits(code))}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def cmd_closure(args, root):
    g = Graph(root, roots=args.root_file)
    reached = g.closure()
    if args.why:
        chain = g.why(args.why)
        if chain is None:
            print("%s is NOT reachable from %s" % (args.why,
                                                   ", ".join(g.roots)))
            return 1
        if not chain:
            print("%s is itself a root" % args.why)
            return 0
        for src, ln, tgt, kind in chain:
            print("%s:%s -[%s]-> %s" % (src, edge_line(ln), kind, tgt))
        best = g.best_incoming(args.why)
        if best and (best[0], best[1], best[2]) != (chain[-1][0], chain[-1][1],
                                                    chain[-1][3]):
            print("strongest incoming edge: %s:%s -[%s]->"
                  % (best[0], edge_line(best[1]), best[2]))
        return 0
    eps = [p for p in sorted(reached) if is_entry_point(root, p)]
    if args.json:
        print(json.dumps({"roots": g.roots, "reached": sorted(reached),
                          "entry_points": eps,
                          "ambiguous": {k: [list(a) for a in v]
                                        for k, v in g.ambiguous.items()}},
                         indent=2))
        return 0
    for p in sorted(reached):
        print(("E " if p in set(eps) else "  ") + p)
    print("closure: %d node(s), %d entry point(s), from %s"
          % (len(reached), len(eps), ", ".join(g.roots)))
    return 0


def cmd_orphans(args, root):
    g = Graph(root, roots=args.root_file)
    reached = g.closure()
    prefixes = excluded_prefixes(load_registry(root))
    rows = []
    for p in g.nodes:
        if p in reached or is_excluded(p, prefixes):
            continue
        if args.entry_points_only and not is_entry_point(root, p):
            continue
        rows.append(p)
    if args.json:
        print(json.dumps({"orphans": rows}, indent=2))
        return 0
    for p in rows:
        print(p)
    print("%d node(s) outside the closure (vendored trees excluded)"
          % len(rows))
    return 0


def cmd_check(args, root):
    res = audit(root)
    errs = [f for f in res["findings"] if f[0] in ERROR_CODES]
    warns = [f for f in res["findings"] if f[0] in ("W005", "W006")]
    if args.json:
        print(json.dumps({"findings": [list(f) for f in res["findings"]],
                          "n_entry_points": len(res["entry_points"]),
                          "n_declared": res["n_declared"],
                          "n_reached": len(res["reached"])}, indent=2))
    else:
        for code, path, msg in res["findings"]:
            print("%s  %s: %s" % (code, path, msg))
        print("wiring-audit: %d entry point(s), %d in closure, %d error(s), "
              "%d warning(s)"
              % (len(res["entry_points"]),
                 len([p for p in res["entry_points"]
                      if p in set(res["reached"])]),
                 len(errs), len(warns)))
    return 1 if errs else 0


def cmd_bootstrap(args, root):
    g = Graph(root)
    reached = g.closure()
    prefixes = excluded_prefixes(load_registry(root))
    rnd = current_round(root)
    entries = {}
    for p in g.nodes:
        if not is_entry_point(root, p) or is_excluded(p, prefixes):
            continue
        if p in reached:
            best = g.best_incoming(p)
            entries[p] = {"status": "wired",
                          "via": ("%s:%s" % (best[0], edge_line(best[1])))
                                 if best else "root",
                          "via_kind": best[2] if best else "root"}
        else:
            entries[p] = {"status": "unwired", "owner": "TODO",
                          "reason": "TODO", "since_round": rnd}
    # `bootstrap` proposes `unwired` for everything outside the closure and
    # never `manual`: the distinction is a judgement about intent, and a tool
    # that guessed it would put the word "by design" over a real debt.
    print(json.dumps(entries, indent=2, sort_keys=True))
    return 0


def cmd_refs(args, root):
    res = refs(root, args.target, args.in_file)
    print(json.dumps(res, indent=2))
    if "error" in res:
        return 2
    if args.expect is not None:
        got = res["code"] if args.code_only else res["raw"]
        if got != args.expect:
            print("EXPECT MISS: claimed %d, re-derived %d"
                  % (args.expect, got))
            return 1
        print("EXPECT HIT: %d" % got)
    return 0


def cmd_token_refs(args, root):
    res = token_refs(root, args.token, args.in_file)
    print(json.dumps(res, indent=2))
    if "error" in res:
        return 2
    if args.expect_absent:
        if res["code"]:
            print("ABSENCE REFUTED: `%s` occurs in code on line(s) %s of %s"
                  % (args.token,
                     ", ".join(str(i) for i in res["code_lines"]),
                     res["in"]))
            return 1
        if res["raw"]:
            print("ABSENCE UNDER-SPECIFIED: `%s` is mentioned on line(s) %s "
                  "but never in code" % (args.token,
                                         ", ".join(str(i)
                                                   for i in res["raw_lines"])))
            return 0
        print("ABSENCE HOLDS: `%s` does not occur in %s"
              % (args.token, res["in"]))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT)
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("closure")
    c.add_argument("--root-file", action="append", default=None,
                   help="graph root (default run_driver.sh); repeatable")
    c.add_argument("--why", help="explain how this path is reached")
    c.add_argument("--json", action="store_true")

    o = sub.add_parser("orphans")
    o.add_argument("--root-file", action="append", default=None)
    o.add_argument("--entry-points-only", action="store_true")
    o.add_argument("--json", action="store_true")

    k = sub.add_parser("check")
    k.add_argument("--json", action="store_true")

    sub.add_parser("bootstrap")

    r = sub.add_parser("refs")
    r.add_argument("target")
    r.add_argument("--in", dest="in_file", required=True)
    r.add_argument("--expect", type=int, default=None)
    r.add_argument("--code-only", action="store_true")

    t = sub.add_parser("token-refs")
    t.add_argument("token")
    t.add_argument("--in", dest="in_file", required=True)
    t.add_argument("--expect-absent", action="store_true",
                   help="exit 1 if the token occurs in code -- the "
                        "re-derivation for an ABSENCE claim")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    root = os.path.abspath(args.repo_root)
    if getattr(args, "root_file", None) is None:
        args.root_file = [DRIVER_ROOT]
    if args.cmd == "closure":
        return cmd_closure(args, root)
    if args.cmd == "orphans":
        return cmd_orphans(args, root)
    if args.cmd == "check":
        return cmd_check(args, root)
    if args.cmd == "bootstrap":
        return cmd_bootstrap(args, root)
    if args.cmd == "refs":
        return cmd_refs(args, root)
    if args.cmd == "token-refs":
        return cmd_token_refs(args, root)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""verb_audit.py — of the SUBCOMMANDS a wired entry point declares, which
ones does anything automatic actually run?

Why this exists
---------------
`harness/wiring_audit.py` computes a FILE-level invocation closure: an edge
`A -> B` means *A's own code text names B*, and `harness/wiring-registry.json`
declares each entry point `wired` / `manual` / `unwired` against it. That
graph answered three expensive failures (rounds 242, 388, 409, 374) and it is
the right graph for the question it asks.

It is the wrong graph for a multi-verb CLI, and the registry says so itself.
`harness/wiring-registry.json`'s `_scope` field, written by round 415:

    Two things the file-level closure CANNOT express, stated here so nobody
    reads more into a `wired` than is there: (1) VERBS. harness/
    pristine_check.py is wired via `status` only; the driver never runs its
    `check` or `baseline`. (2) MARKERS. [...]

`harness/tier-budget.json` and `harness/swe/slowtier.py` answer the MARKER
half. Nothing answered the VERB half; round 419's next-steps item 5 carried
it to harness(A) with the victim already named. This file answers it.

The distinction is not pedantic. `harness/pristine_check.py` declares six
subcommands and the whole per-round pipeline invokes exactly one of them, the
cheap `status` reporter that prints a RECORDED verdict. `check` — the command
that actually runs the pristine differential — is invoked by nothing, in any
tree, on any round. Under the file-level graph that file reads `wired`, and
round 374 read exactly this kind of evidence and concluded in writing that
the driver runs a pristine checkout every round. It does not.

What it computes
----------------
For every entry point in the file-level closure:

    DECLARED(f)   the subcommand names f's argparse setup defines
    REACHED(f)    the subset some file IN THE CLOSURE is seen invoking

DECLARED comes from the AST, in the two forms this repo actually uses:

  * `sub = ap.add_subparsers(...)` then `sub.add_parser("check")`, including
    `aliases=[...]`  — 15 files tree-wide.
  * a POSITIONAL `add_argument("cmd", choices=["status", "plan", "run"])`
    — `harness/swe/slowtier.py:918` and friends. A token starting with `-`
    is an option and its `choices` are values, not verbs; those are skipped.

REACHED comes from scanning each closure file's comment-stripped code for a
reference that resolves to `f` (`wiring_audit.resolve_reference`, so the
longest-suffix rule and its ambiguity refusal are inherited unchanged), then
reading forward through the rest of that command for a bare word that is in
`DECLARED(f)`.

WHERE it reads depends on the language, and that rule is the single thing
that made the layer trustworthy. In a `.sh` file the raw line IS the command,
so the line scan is correct. In a `.py` file it is not: Python starts a
program by passing an argv LIST, so a path-plus-verb in a raw Python line is
inside a string constant — advice printed to a human, a copy-paste hint in a
finding, or a test asserting the command must NEVER run unattended. All three
shapes are in this tree and all three were false REACHEDs until Python lines
were restricted to folded `subprocess.run([...])` argv literals. Hand-audit
of every site after the rule: **8 of 8 correct**, against 8 of 11 before.

Both directions of error, stated rather than hidden
---------------------------------------------------
  * OVER-approximation. A verb named on a branch that never runs still
    counts, exactly as in the file-level graph — there is no dataflow
    analysis here either. And a verb named inside a TEST file counts as
    reached, which is real execution but weaker evidence than the driver
    invoking it; `site_kind` records which, and `--driver-only` restricts
    the answer to the per-round pipeline.

  * THREE LEVELS, and only the third is what this measures. A verb can be
    (1) file-level `wired`, (2) covered as a LIBRARY — its function called
    directly by a test — and (3) invoked as a CLI verb. They come apart, and
    saying so is the difference between a finding and a smear.
    `harness/wiring_audit.py check` is level 1 and 2 but not 3: its registry
    rules really are enforced every round, by
    `harness/tests/test_wiring_audit.py::TestThisTree`, not by the verb.
    `harness/pristine_check.py check` is level 1 and 2 but not 3 in a
    stronger sense: `pc.differential(...)` is exercised by ~20 unit tests, but
    every one of them passes a MOCK runner, so the real pristine differential
    — a worktree and two full suites — is executed by nothing, on any round.
    UNREACHED here means "no automatic CLI invocation", never "untested".
  * UNDER-approximation. A verb assembled at run time (`cmd = "check" if x
    else "status"`, an argv passthrough, a loop variable) is invisible, so a
    verb reported UNREACHED may in truth be reachable. This is why V001 is a
    WARNING and never sets the exit code. The claim it licenses is "nothing
    in this tree is seen invoking it", which is exactly what it prints.

MATCHING AGAINST THE DECLARED SET IS DELIBERATE, and it is what makes the
forward scan safe. A positional scan that took "the first bare word after the
path" would read `--budget-s 900`'s value, a `-k` expression, a redirect
target or the next command in a `&&` chain as a verb. Requiring membership in
a set the target itself declares means a false REACHED needs the noise to
spell a real subcommand. The cost is that a genuinely misspelled invocation
(`pristine_check.py staus`) reads as "no verb found" rather than as an error,
so that case is reported separately as V002 from the unfiltered first bare
word, where a human judges it.

Findings
--------
`V001` (WARN)  a `wired` entry point declares verbs and at least one is
               never seen invoked from inside the closure. Dead CLI surface:
               the file is reached, this command is not.
`V002` (WARN)  a bare word sits where a verb goes at a real call site and the
               target does not declare it. Either a broken invocation or an
               extraction artefact — the site is printed so it can be judged,
               and this deliberately does NOT set the exit code because the
               heuristic that produces it is the unfiltered one.
`V003` (WARN)  a `wired` entry point declares verbs and NONE is reached: its
               command-line surface is never executed at all. Usually a
               module whose only edge is an `import` from a test — covered as
               a library, uncovered as a program.

Nothing here is an ERROR. Round 363's rule is why: a check that goes FAIL for
a state the program has deliberately chosen gets ignored and then
uninstalled. A dead subcommand is frequently a correct choice (`check` costs
minutes and the driver may rightly not pay it every round); what was missing
was not permission, it was the NUMBER. `manual` entry points are skipped
entirely for the same reason — a file nothing automatic runs has every verb
trivially unreached, and reporting that is the mute button the registry's
`manual` status exists to avoid.

Usage:
    python3 harness/verb_audit.py verbs                 # per-file table
    python3 harness/verb_audit.py verbs --path P        # one file, with sites
    python3 harness/verb_audit.py check                 # findings
    python3 harness/verb_audit.py check --driver-only   # ignore test sites
    python3 harness/verb_audit.py declared --path P     # just the AST read

Exit codes: 0 = clean or warnings only, 2 = usage/IO problem.
"""

import argparse
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import wiring_audit as wa  # noqa: E402


# --------------------------------------------------------------------------
# DECLARED — what subcommands does this file define?
# --------------------------------------------------------------------------

def _str_const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _str_seq(node):
    """The string constants of a list/tuple literal, or None if not one."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    out = []
    for el in node.elts:
        s = _str_const(el)
        if s is not None:
            out.append(s)
    return out


#: Callables that actually start a process. A list literal handed to
#: anything else is data, however much it looks like an argv.
_SPAWNERS = frozenset((
    "run", "Popen", "call", "check_call", "check_output",
    "execv", "execve", "execvp", "execvpe", "spawnv", "spawnve",
    "create_subprocess_exec",
))


def _spawns(fn):
    """Does this `Call.func` name a process-spawning callable?"""
    name = getattr(fn, "attr", None) or getattr(fn, "id", None)
    return name in _SPAWNERS


def _argv_positions(tree):
    """`id()` of every node that sits where an ARGV LIST is spelled.

    Round 437 (SWE-loop D). The AST fold below exists because Python starts a
    program by passing an argv LIST, so a list/tuple of string constants is
    the shape a real invocation has. It folded EVERY list/tuple literal,
    including ones that are plainly data — and the one V002 finding standing
    on this tree since round 429 was exactly that: a `for c in (...)` tuple in
    `skills/skill-authoring/scripts/test_claim_check.py` holding three
    INDEPENDENT command strings, asserted to classify as `manual`. Folded into
    one pseudo-line it reads as `... pristine_check.py check ... baseline ...
    suites-and-then-some`, and the last word is a verb `pristine_check.py`
    deliberately does not declare — the fixture's whole point.

    `verb_audit`'s docstring already records three shapes of Python string
    constant that were false REACHEDs and says each was fixed by a rule
    rather than an exemption. This is the fourth: a sequence literal that is
    not in an argv position is a datum, and the tell is syntactic, not
    textual. An argv position is an argument of a `Call`
    (`subprocess.run([...])`, `check_output(cmd=[...])`) or the value of an
    assignment (`cmd = [...]`, later passed) — the two ways this repo spells
    one. The iterable of a `for`, an element of a bigger literal, a `return`
    value and a comparison operand are not.

    ROUND 523 (harness A) NARROWED THE CALL BRANCH, and it is the fifth
    instance of the same rule-not-exemption pattern. As first written, ANY
    list literal passed to ANY call counted as an argv position -- so
    ordinary DATA passed to an ordinary function did too. Three fresh V002s
    came from one new test file whose fixtures happen to spell
    `SI.existing(["harness/scopeinfer.py", "alpha", ...])` and
    `row(files=["harness/scopeinfer.py", "alpha"])`: a module path followed
    by a bare word, in an argument position, which is exactly an argv's
    shape and is not one. `row()` does not start a process.

    A list is now in an argv position only when it is passed to something
    that can SPAWN one (`_SPAWNERS`), or assigned to a name (`cmd = [...]`,
    later handed to a spawner -- the assignment branch stays deliberately
    loose because the hand-off is usually a separate statement). This can
    only REMOVE V002 findings, never add one, and it does not touch REACHED.

    As with the `*argv` rule above, only V002 is suppressed: a verb REACHED
    from such a line is still sound, because the word really is there.
    """
    out = set()
    for parent in ast.walk(tree):
        if isinstance(parent, ast.Call):
            if not _spawns(parent.func):
                continue
            for a in list(parent.args) + [k.value for k in parent.keywords]:
                if isinstance(a, ast.Starred):
                    a = a.value
                out.add(id(a))
        elif isinstance(parent, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if getattr(parent, "value", None) is not None:
                out.add(id(parent.value))
    return out


def declared_verbs(root, path):
    """`{verb: kind}` for a tracked `.py` file. Empty for `.sh` and for a
    single-command CLI.

    `kind` is `"subparser"` or `"choices"`, kept because the two carry
    different confidence: `add_parser` is unambiguously a subcommand, while a
    positional `choices=` list could in principle be a value enumeration that
    happens to sit in a positional slot. Both forms are in this repo and both
    are real dispatch.
    """
    if not path.endswith(".py"):
        return {}
    raw = wa.read_text(root, path)
    tree, _ = wa._parse_for_ast(raw)
    if tree is None:
        return {}
    verbs = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            continue
        if fn.attr == "add_parser":
            name = _str_const(node.args[0]) if node.args else None
            if name:
                verbs[name] = "subparser"
            for kw in node.keywords:
                if kw.arg == "aliases":
                    for a in (_str_seq(kw.value) or []):
                        verbs[a] = "subparser"
        elif fn.attr == "add_argument":
            # POSITIONAL only. `add_argument("--suite", choices=[...])` is an
            # option whose choices are values; reading those as verbs would
            # invent a dozen subcommands per file.
            first = _str_const(node.args[0]) if node.args else None
            if not first or first.startswith("-"):
                continue
            for kw in node.keywords:
                if kw.arg == "choices":
                    for c in (_str_seq(kw.value) or []):
                        verbs.setdefault(c, "choices")
    return verbs


# --------------------------------------------------------------------------
# REACHED — what does the closure invoke?
# --------------------------------------------------------------------------

# A command ends at a pipe, a redirect, a separator or a comment-ish tail. The
# forward scan must not run past it: in `python3 x.py status || true` the word
# `true` is not an argument of `x.py`, and in `a.py && b.py check` the verb
# belongs to `b.py`.
_STOP = {"|", "||", "&&", ";", ">", ">>", "<", "2>", "2>&1", "&", ")", "}"}

_BARE_WORD_RE = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")

# A verb slot in a `.py` file's raw line scan is frequently not a verb slot at
# all: `assert "harness/swe/guardpin.py" in cands` puts the Python keyword
# `in` immediately after a path that resolves. These are the words that can
# never be a subcommand invocation in either language, and excluding them is
# what keeps V002 reporting real defects rather than grammar.
_NOT_A_VERB = {
    "in", "is", "and", "or", "not", "if", "else", "elif", "for", "while",
    "return", "assert", "import", "from", "as", "with", "pass", "raise",
    "then", "fi", "do", "done", "esac", "true", "false", "echo", "cd",
}

# Flags that take a separate value, so the value is not mistaken for a verb by
# the UNFILTERED first-bare-word pass that feeds V002. The filtered pass does
# not need this (a value would have to spell a declared verb), but V002 exists
# precisely to report the unfiltered read, so it must be as clean as possible.
_VALUE_FLAGS = {"-m", "-k", "-p", "-c", "--json", "--root", "--ledger",
                "--only", "--suite", "--budget-s", "--repo-root", "--test-args",
                "--capture", "--out", "--timeout", "--ref", "--expect",
                "--why", "--path", "--in", "--model", "--count"}


def _tokens(line):
    """Whitespace tokens of a shell-ish line, quotes stripped."""
    return [t for t in re.split(r"\s+", line.strip()) if t]


def _scan_line_for(tokens, i, verbs):
    """Walk forward from token `i` (the reference) and return
    `(matched_verb, first_bare_word)`.

    `matched_verb` requires membership in `verbs`, which is the safe read.
    `first_bare_word` is the unfiltered read, used only for V002.
    """
    matched, first_bare = None, None
    j = i + 1
    while j < len(tokens):
        t = tokens[j].strip("'\"`,;")
        if not t or t in _STOP or t.startswith("#"):
            break
        if t.startswith("-"):
            # `--flag=value` carries its value; a bare flag may take the next
            # token, which we then skip so it cannot be read as a verb.
            if "=" not in t and t in _VALUE_FLAGS:
                j += 2
                continue
            j += 1
            continue
        if matched is None and t in verbs:
            matched = t
        if first_bare is None and _BARE_WORD_RE.match(t) \
                and t not in _NOT_A_VERB:
            first_bare = t
        if matched is not None:
            break
        j += 1
    return matched, first_bare


class VerbGraph:
    """The verb layer over `wiring_audit.Graph`."""

    def __init__(self, root):
        self.root = root
        self.g = wa.Graph(root)
        self.closure = self.g.closure()
        self.registry = wa.load_registry(root) or {}
        self.entry_points = self.registry.get("entry_points", {})
        self._declared = {}

    def declared(self, path):
        if path not in self._declared:
            self._declared[path] = declared_verbs(self.root, path)
        return self._declared[path]

    def targets(self):
        """Entry points that are `wired`, in the closure, and declare verbs."""
        out = {}
        for path, ent in sorted(self.entry_points.items()):
            if ent.get("status") != "wired":
                continue
            if path not in self.closure:
                continue
            d = self.declared(path)
            if d:
                out[path] = d
        return out

    def sites(self, targets):
        """`{target: [ (src, lineno, verb, first_bare, site_kind), ... ]}`.

        Scans every file in the closure, including the targets themselves —
        a script that documents its own verbs in a runnable `Usage:` block is
        NOT evidence that anything runs them, so self-references are dropped
        below.
        """
        found = {t: [] for t in targets}
        by_name = {}
        for t in targets:
            by_name.setdefault(os.path.basename(t), []).append(t)

        for src in sorted(self.closure):
            if not (src.endswith(".py") or src.endswith(".sh")):
                continue
            text = wa.code_text(self.root, src)
            base_dir = os.path.dirname(src)
            is_py = src.endswith(".py")
            lines = text.split("\n")

            # Python: also fold list-literal argv (`subprocess.run([...])`),
            # which is how this repo's own runners invoke each other. Without
            # it `corpus_check.py`'s checker calls are invisible.
            # `trusted` marks a line whose token sequence is COMPLETE. A folded
            # argv list containing a non-constant element (`[sys.executable,
            # "nuc/perturbation.py", *argv, "--unit", "fwupd-refresh"]`) is
            # not: the fold dropped `*argv`, which is where the real verb was,
            # and reading the surviving tail as the verb slot produced exactly
            # one false V002. A reached verb from such a line is still sound —
            # the word really is there — so only V002 is suppressed.
            extra = []
            if is_py:
                tree, doc_ids = wa._parse_for_ast(wa.read_text(self.root, src))
                if tree is not None:
                    argv_pos = _argv_positions(tree)
                    for node in ast.walk(tree):
                        seq = _str_seq(node)
                        if seq and len(seq) >= 2:
                            n_elts = len(getattr(node, "elts", []))
                            extra.append((getattr(node, "lineno", 0),
                                          " ".join(seq),
                                          len(seq) == n_elts
                                          and id(node) in argv_pos))

            # HOW A COMMAND IS SPELLED DECIDES WHAT COUNTS, and this is the
            # rule that took the verb layer from 8-of-11 correct to 8-of-8.
            #
            # In a `.sh` file the raw line IS the command, so the line scan is
            # the right reader. In a `.py` file it is not: Python starts a
            # program by passing an argv LIST, so a path-plus-verb sitting in a
            # raw Python line is inside a string constant, and all three false
            # REACHEDs measured on this tree were exactly that —
            #   `Use \`python3 nuc/expert_cache.py plan\``  (advice printed to
            #     a human, nuc/fast_lane.py:413)
            #   `cmd = "python3 harness/wiring_audit.py refs %s ..."`  (a hint
            #     a finding prints so the fix is a copy-paste,
            #     state_claim_check.py:736)
            #   `assertManual("python3 nuc/fast_lane.py handoff ...")`  (a test
            #     asserting the command must NEVER run unattended,
            #     test_claim_check.py:199)
            # The third is `wiring_audit.py`'s own W006 shape one level down: a
            # textual reference that is evidence of the OPPOSITE of execution.
            #
            # `run_driver.sh` and the four `*_fast.sh` suites are shell, so the
            # per-round pipeline loses nothing. No file in this tree executes a
            # literal path-plus-verb string via `shell=True` (checked: the only
            # two `shell=True` sites run a runtime variable — the agent's own
            # bash tool and `claim_check --run`), so the Python line scan had
            # no true positives to give up.
            numbered = ([(n, ln, True) for n, ln in enumerate(lines, 1)]
                        if not is_py else [])
            for lineno, line, trusted in numbered + extra:
                # A line that still starts with `#` after `code_text` stripped
                # the file's own comments is a comment in an EMBEDDED language
                # — this repo builds remote shell scripts inside Python
                # f-strings, and `tokenize` correctly does not treat a `#`
                # inside a string literal as a Python comment. Such a line is
                # prose, and prose that names a file followed by an English
                # word ("round 100's fast_lane.py bug") is not an invocation.
                if line.lstrip().startswith("#"):
                    continue
                toks = _tokens(line)
                if not toks:
                    continue
                for i, tok in enumerate(toks):
                    cand = self._resolve_token(tok, base_dir, by_name, i, toks)
                    if cand is None or cand == src:
                        continue
                    if cand not in found:
                        continue
                    verbs = targets[cand]
                    m, fb = _scan_line_for(toks, i, verbs)
                    if m is None and fb is None:
                        continue
                    found[cand].append(
                        (src, lineno, m, fb, self._site_kind(src), trusted))
        return found

    def _resolve_token(self, tok, base_dir, by_name, i, toks):
        """The target this token names, or None.

        Handles the path form and the `-m dotted.module` form, the two ways
        anything in this repo starts another program.
        """
        if i > 0 and toks[i - 1] == "-m":
            for cand in wa.module_to_paths(tok.strip("'\""), ""):
                if cand in self.g.node_set:
                    return cand
            return None
        clean = tok.strip("'\"`,;()")
        if not clean or "/" not in clean and not clean.endswith((".py", ".sh")):
            return None
        kind, val = wa.resolve_reference(self.g.index, clean, base_dir)
        return val if kind == "file" else None

    @staticmethod
    def _site_kind(src):
        if wa.is_test_file(src):
            return "test"
        if src == wa.DRIVER_ROOT or src.endswith("_fast.sh") \
                or src.endswith("run_driver.sh"):
            return "driver"
        return "other"


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------

def audit(root, driver_only=False):
    vg = VerbGraph(root)
    targets = vg.targets()
    sites = vg.sites(targets)

    rows, findings = [], []
    for path, verbs in sorted(targets.items()):
        hits = sites.get(path, [])
        if driver_only:
            hits = [h for h in hits if h[4] != "test"]
        reached = {}
        for src, lineno, m, fb, kind, trusted in hits:
            if m is not None:
                reached.setdefault(m, []).append((src, lineno, kind))
        unreached = sorted(set(verbs) - set(reached))
        rows.append({
            "path": path,
            "declared": sorted(verbs),
            "declared_kind": verbs,
            "reached": sorted(reached),
            "unreached": unreached,
            "sites": {v: s for v, s in reached.items()},
            "via_kind": vg.entry_points.get(path, {}).get("via_kind"),
        })
        if not reached:
            findings.append(("V003", path,
                             "declares %d verb(s); NONE is invoked anywhere "
                             "in the closure (via_kind=%s)"
                             % (len(verbs),
                                vg.entry_points.get(path, {}).get("via_kind"))))
        elif unreached:
            findings.append(("V001", path,
                             "%d of %d declared verb(s) never invoked: %s"
                             % (len(unreached), len(verbs),
                                ", ".join(unreached))))
        # V002: a bare word in the verb slot that the target does not declare.
        for src, lineno, m, fb, kind, trusted in hits:
            if m is None and fb is not None and fb not in verbs and trusted:
                findings.append(("V002", path,
                                 "%s:%d invokes it with %r, which it does not "
                                 "declare (declared: %s)"
                                 % (src, lineno, fb, ", ".join(sorted(verbs)))))
    return vg, rows, findings


def summarise(rows):
    n_files = len(rows)
    n_declared = sum(len(r["declared"]) for r in rows)
    n_reached = sum(len(r["reached"]) for r in rows)
    n_dead_files = sum(1 for r in rows if not r["reached"])
    pct = (100.0 * n_reached / n_declared) if n_declared else 0.0
    # Round 423. The trailing `coverage ...` clause is not decoration: it is
    # the shape `corpus_check.coverage_of` parses, and this line is now the
    # one that file quotes. Round 421's item 2 was that this audit's output
    # "is not watched by anything" -- so the 8.7% was re-derived only by a
    # human typing the command. Aggregators quote the LAST line, so the
    # denominator has to ride on it (round 417's rule, in the form round 415
    # asked for it).
    return ("verb-audit: %d verb-declaring wired entry point(s), %d declared "
            "verb(s), %d reached (%.1f%%), %d unreached; %d file(s) with no "
            "verb reached at all; coverage %d/%d verbs (%.1f%%), "
            "%d/%d entry points with a reached verb"
            % (n_files, n_declared, n_reached, pct,
               n_declared - n_reached, n_dead_files,
               n_reached, n_declared, pct, n_files - n_dead_files, n_files))


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_declared(args, root):
    if not args.path:
        print("declared: --path is required", file=sys.stderr)
        return 2
    d = declared_verbs(root, args.path)
    if not d:
        print("%s: declares no subcommands" % args.path)
        return 0
    print("%s: %d declared verb(s)" % (args.path, len(d)))
    for v in sorted(d):
        print("  %-20s %s" % (v, d[v]))
    return 0


def cmd_verbs(args, root):
    vg, rows, findings = audit(root, driver_only=args.driver_only)
    if args.path:
        rows = [r for r in rows if r["path"] == args.path]
        if not rows:
            print("%s: not a verb-declaring wired entry point" % args.path)
            return 0
    for r in rows:
        print("%s  [%s]" % (r["path"], r["via_kind"]))
        for v in r["declared"]:
            s = r["sites"].get(v)
            if s:
                where = "; ".join("%s:%d(%s)" % (a, b, c) for a, b, c in s[:3])
                print("    %-18s REACHED   %s" % (v, where))
            else:
                print("    %-18s unreached" % v)
    print()
    print(summarise(rows))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"rows": rows,
                       "findings": [list(f) for f in findings]}, fh, indent=2)
    return 0


def cmd_check(args, root):
    vg, rows, findings = audit(root, driver_only=args.driver_only)
    for code, path, msg in findings:
        print("%-5s %s: %s" % (code, path, msg))
    print()
    print(summarise(rows))
    print("verb-audit: %d finding(s) (%s) — all WARN, exit code unaffected"
          % (len(findings),
             ", ".join("%s %d" % (c, sum(1 for f in findings if f[0] == c))
                       for c in ("V001", "V002", "V003"))))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"rows": rows,
                       "findings": [list(f) for f in findings],
                       "summary": summarise(rows)}, fh, indent=2)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        description="Which declared subcommands does anything automatic run?")
    ap.add_argument("--repo-root", default=wa.DEFAULT_REPO_ROOT)
    sub = ap.add_subparsers(dest="cmd")

    v = sub.add_parser("verbs", help="per-file declared/reached table")
    v.add_argument("--path", default=None)
    v.add_argument("--json", default=None)
    v.add_argument("--driver-only", action="store_true",
                   help="ignore invocation sites inside test files")

    c = sub.add_parser("check", help="findings")
    c.add_argument("--json", default=None)
    c.add_argument("--driver-only", action="store_true")

    d = sub.add_parser("declared", help="just the AST read, for one file")
    d.add_argument("--path", default=None)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = os.path.abspath(args.repo_root)
    if args.cmd == "declared":
        return cmd_declared(args, root)
    if args.cmd == "verbs":
        return cmd_verbs(args, root)
    if args.cmd == "check":
        return cmd_check(args, root)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

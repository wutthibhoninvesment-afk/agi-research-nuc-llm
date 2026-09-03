#!/usr/bin/env python3
"""pattern_vs_enum.py — a PROSE PATTERN that disagrees with the code beside it.

Why this exists (round 477)
---------------------------
`skills/skill-authoring/scripts/corpus_check.py` described its `unit_tests`
checker as *"pytest over `skills/*/scripts/test_*.py`"*. Its argv named two
directories. The glob matched fifteen files in THREE. The missing one held
round 471's `test_bank_audit.py` — 19 tests that nothing ran — and round 473
then read the DESCRIPTION, declared `bank_audit.py` `wired` on the strength
of it, and left a W002 ERROR standing for two rounds unseen.

Nothing in this tree could see that sentence, and each checker had a
documented reason:

  * `xref_check` X004 — `*` is outside `PATH_TOKEN_RE`'s character class, so
    the match stops at `skills/` and the token is counted SKIPPED. There is a
    test asserting exactly that (`test_a_glob_makes_the_token_untruncatable_
    but_unchecked`), and it is right: a truncated token is not evidence.
  * `selfdesc_check` J001-J010 — reads prose inside `.json` artefacts. This
    sentence is a Python dict value.
  * `claim_check` — reads SKILL.md `## Verification` blocks.
  * `wiring_audit` — its own docstring (line 52) names "a `glob`" as a
    documented under-approximation of the invocation closure.

So a glob in prose is a claim about a SET that three path-checkers skip by
design. This file checks the one sub-case that is decidable.

What it checks, and what it deliberately does NOT
-------------------------------------------------
`E001` (ERROR) a Python file whose PROSE names a glob, whose CODE constructs
               literal paths inside what that glob matches, and whose literal
               set is a STRICT SUBSET of it. The prose promises a family; the
               code enumerates part of it; the gap is the defect.

**It does not report a dead pattern**, and that is a measurement, not an
oversight. Round 477 ran the census: under `xref_check`'s own anchoring and
terminator discipline this tree holds 62 distinct glob patterns in prose that
expand to ZERO paths, 13 of them at a present-tense (non-log, non-bank) site.
Ten of those thirteen are `knowledge/round-NNN-*.md` inside sentences that
assert the file does NOT exist — *"there should not be one"*. An eleventh,
`languages/whence/**.lang` at `harness/swe/slowtier.py:116`, is informal
shorthand in a comment whose code correctly uses `_SOURCE_EXTS`. A rule that
called those errors would be X004's first draft again: 340 findings, every one
inspected a tokenising artifact. **A dead glob is ambiguous between a rotted
reference and a correct absence claim, and in this corpus the absence claims
win 10 to 3.**

The enumeration side is not a fresh parser
------------------------------------------
It is `harness/wiring_audit._constructed_paths`, the same fold the invocation
closure already trusts, whose own docstring uses `corpus_check.py`'s argv as
its worked example. Two readings of one artefact by two tools that were
written for different reasons is the cross-check `derived-subject-set` step 5
asks for; a second hand-rolled `os.path.join` walker would not be.

Why this is not a `corpus_check` checker
----------------------------------------
Its live population is ZERO — the one instance is fixed. A tenth checker whose
steady state is silence would spend a slot and 0-few seconds of a
`unit_tests` budget already at 77% of its timeout, to catch a second instance
that may never come. Instead the enforcement rides in
`test_pattern_vs_enum.py`, which round 477's own argv fix schedules: the argv
is a literal enumeration held equal to `skills/*/scripts/test_*.py`, so this
directory's tests run every round by construction. The checker that needed a
slot is the one that already has one.

Usage:
    python3 pattern_vs_enum.py audit [--repo-root R] [--json]
    python3 pattern_vs_enum.py census [--repo-root R]   # the dead-glob count

Exit codes: 0 = clean, 1 = at least one E001, 2 = usage/IO problem.
"""

import argparse
import ast
import glob as globmod
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))

#: `xref_check.PATH_TOKEN_RE` with `*` added to both character classes. `?`
#: is NOT added: it is already in `PATH_TERMINATORS`, so it can never be part
#: of a token, and adding it to the class would silently change what that set
#: means for the terminator test below.
TOKEN_RE = re.compile(r"[A-Za-z0-9_./*-]*[A-Za-z0-9_*-]/[A-Za-z0-9_./*-]+")

#: `xref_check.PATH_TERMINATORS`, copied rather than imported: this script
#: lives under `skills/derived-subject-set/` and importing across skill
#: directories would make one skill's tests depend on another's layout.
#: `test_pattern_vs_enum.py` asserts the two sets are equal, so the copy
#: cannot drift silently — the `copy-parity-differential` move.
PATH_TERMINATORS = set(" \t`)]},;:'\"!?")

#: `xref_check.PLACEHOLDER_RE` MINUS its `\*` alternative — a glob is the
#: subject here, not a placeholder — PLUS `\dNN`, which this tree writes as a
#: round metavariable (`state/whence/round-4NN/run*.json`) and which the
#: round-477 census caught as its only tokeniser artifact.
#:
#: `\?` is kept even though it is INERT here — `?` is in `PATH_TERMINATORS`,
#: so it can never appear inside a token this file forms. It stays so that
#: the difference from xref_check's set is exactly the two deliberate ones,
#: which is what `test_the_placeholder_set_differs_from_xrefs_in_exactly_two_
#: ways` asserts. The first draft dropped it silently and that test failed —
#: the sentence above said "minus one, plus one" while the code was "minus
#: two, plus one", which is this whole file's subject arriving in its own
#: source on the day it was written.
PLACEHOLDER_RE = re.compile(
    r"NNN|\dNN|<|>|\?|\{|\}|\$|\.\.\.|XXX"
    r"|(?<![A-Za-z0-9])[A-Z](?![A-Za-z0-9])")

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__",
             "site-packages", ".pytest_cache", ".mypy_cache",
             "research-env", "whence_lang.egg-info"}

CENSUS_EXTS = (".md", ".py", ".sh", ".json")


def top_level_dirs(root):
    """Directory names at the top of the repo — the anchor set, X004's rule."""
    return {n for n in os.listdir(root)
            if os.path.isdir(os.path.join(root, n)) and n not in SKIP_DIRS}


def prose_globs(text, tops):
    """{(pattern, offset)} for anchored, terminated, glob-bearing tokens.

    All three filters are X004's, and each one is load-bearing:

      anchored    the first component is a top-level directory of THIS repo,
                  so `foo/bar` from another project is not a candidate;
      terminated  the character after the match ENDS a path in prose, which
                  is what stops a hard-wrapped path from being read as a
                  prefix that does not exist;
      no marker   a token carrying `NNN`, `<x>`, `4NN` or a single-capital
                  component is a template, not a pattern.

    Plus one rule X004 does not need: a trailing `.` or `-` is prose
    punctuation. X004 never sees it because `*` already stops its match
    short; a glob-aware tokeniser reaches the end of the sentence.
    """
    out = set()
    for m in TOKEN_RE.finditer(text):
        raw = m.group(0)
        if "*" not in raw:
            continue
        nxt = text[m.end()] if m.end() < len(text) else " "
        if nxt not in PATH_TERMINATORS:
            continue
        tok = raw.rstrip(".-")
        if "*" not in tok or tok.split("/")[0] not in tops:
            continue
        if PLACEHOLDER_RE.search(tok):
            continue
        out.add((tok, m.start()))
    return out


def _wiring_audit(root):
    """`harness/wiring_audit`, imported by path.

    Imported and not reimplemented: `_constructed_paths` is the fold the
    invocation closure runs, and the whole point of using it is that a
    disagreement found here is a disagreement the closure would also see.
    """
    path = os.path.join(root, "harness")
    sys.path.insert(0, path)
    try:
        import wiring_audit
        return wiring_audit
    finally:
        if sys.path and sys.path[0] == path:
            sys.path.pop(0)


def constructed_dirs(source):
    """Literal directories this source hands to a TEST RUNNER, as a set.

    `_constructed_paths` returns two things and the second one is the whole
    rule: a set restricted to joins that sit inside a list, tuple or call one
    of whose other elements is the string `pytest`. The first draft of this
    function used the first return value — every constructed path — and it
    fired NINE false positives on this file's own test module, which names
    the glob in nine docstrings and joins `skills/skill-authoring/scripts`
    twice in order to import `xref_check` for a parity check. An import path
    is not a subject set.

    That is the same over-collection `wiring_audit` records fixing in the
    comment right above the code being reused here: *"the module-level 'does
    this file mention pytest' gate was too coarse in exactly one way … "*
    `os.path.join(ROOT, "nuc")` *"is the AUDITED directory, not a test
    root."* Reusing a primitive and ignoring the half of its return value
    that encodes the lesson is how you re-earn the lesson.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    wa = _wiring_audit(DEFAULT_REPO_ROOT)
    return set(wa._constructed_paths(tree)[1])


def findings_for(source, tops, root, rel="<source>"):
    """[E001 dict] for one Python source string.

    A finding needs THREE things true at once, and the third is what keeps
    the noise out: the glob must expand (a dead pattern is not this rule's
    business), the code must name at least one member of what it expands to
    (otherwise the glob is about something else entirely), and the named set
    must be a STRICT subset.
    """
    built = constructed_dirs(source)
    if not built:
        return []
    out = []
    for pat, off in sorted(prose_globs(source, tops)):
        matched = globmod.glob(os.path.join(root, pat), recursive=True)
        if not matched:
            continue
        family = {os.path.relpath(os.path.dirname(m), root).replace(os.sep, "/")
                  for m in matched}
        named = {b for b in built if b in family}
        if named and named != family:
            out.append({
                "code": "E001",
                "file": rel,
                "line": source[:off].count("\n") + 1,
                "pattern": pat,
                "family": sorted(family),
                "named": sorted(named),
                "missing": sorted(family - named),
            })
    return out


def audit(root):
    """[E001 dict] over every tracked `.py` file in the tree."""
    wa = _wiring_audit(root)
    tops = top_level_dirs(root)
    out = []
    for rel in wa.tracked_files(root):
        if not rel.endswith(".py"):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        out.extend(findings_for(source, tops, root, rel))
    return out


def census(root):
    """(live, dead) pattern -> [(file, line)], for the dead-glob measurement.

    Reported by `census` and checked by nothing. It is the evidence behind
    this file's refusal to make a dead pattern an error, kept runnable so the
    refusal can be re-derived rather than believed.
    """
    tops = top_level_dirs(root)
    live, dead = {}, {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(CENSUS_EXTS):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            for pat, off in prose_globs(text, tops):
                n = len(globmod.glob(os.path.join(root, pat), recursive=True))
                bucket = live if n else dead
                bucket.setdefault(pat, []).append(
                    (rel.replace(os.sep, "/"), text[:off].count("\n") + 1))
    return live, dead


def is_record(rel):
    """A file that RECORDS what a past round typed, not a present claim.

    A dead pattern inside `logs/round-431.json` is a faithful transcript of a
    command somebody ran in round 431 and is not a defect in anything.
    """
    return (rel.startswith("logs/")
            or rel == "state/research-state-archive.md"
            or rel.endswith("/PREDICTIONS.md")
            or re.match(r"state/round-\d+-predictions\.md$", rel) is not None)


def cmd_audit(args, root):
    found = audit(root)
    if args.json:
        json.dump({"findings": found, "n": len(found)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for f in found:
            print("E001  %s:%d  prose glob %s covers %s; code names only %s "
                  "— MISSING %s"
                  % (f["file"], f["line"], f["pattern"],
                     ", ".join(f["family"]), ", ".join(f["named"]),
                     ", ".join(f["missing"])))
        print("pattern-vs-enum: %d error(s)" % len(found))
    return 1 if found else 0


def cmd_census(args, root):
    live, dead = census(root)
    claim = {p: [w for w in ws if not is_record(w[0])]
             for p, ws in dead.items()}
    claim = {p: ws for p, ws in claim.items() if ws}
    print("glob patterns in prose: %d live, %d dead" % (len(live), len(dead)))
    print("dead with a present-tense site: %d pattern(s), %d site(s)"
          % (len(claim), sum(len(v) for v in claim.values())))
    for p in sorted(claim):
        for rel, line in sorted(claim[p]):
            print("  %-46s %s:%d" % (p, rel, line))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("audit")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("census")
    p.set_defaults(fn=cmd_census)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = os.path.abspath(args.repo_root)
    if not os.path.isdir(os.path.join(root, "harness")):
        sys.stderr.write("not a repo root: %s\n" % root)
        return 2
    return args.fn(args, root)


if __name__ == "__main__":
    sys.exit(main())

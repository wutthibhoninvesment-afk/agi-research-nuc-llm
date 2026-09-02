"""Round 449 (SWE-loop D) — every round-heading parser reads ONE definition.

`harness/roundheadings.py` landed at round 397 as "ONE definition of a round
entry heading", after the same class of bug fired twice, 94 rounds apart, and
produced a false "round N was never recorded" gap both times. Its docstring
names FOUR independent parsers and tabulates which headings each one accepts.

Fifty-two rounds later, round 449 counted the adopters: **one**. The module
existed, was correct, was tested, and had exactly one caller
(`check_round_recorded.py`, which shipped in the same round). The other three
tools were still carrying their own regexes, and round 448's live heading
(`## Round 448 (NUC-integration E) — …`) was invisible to one of them — not
merely dropped but ABSORBED, its whole 138-line entry served as part of round
447's section by `carryforward_check.round_sections`.

Writing a shared module does not make it shared. This file is what turns
"there is one definition" from a docstring into an assertion:

  * `test_every_declared_parser_agrees_*` runs each parser over the LIVE
    record and requires the same answer as `roundheadings`.
  * `test_no_undeclared_heading_parser_*` derives the parser set from the
    REPO — every module compiling a heading-shaped `Round` regex — rather
    than from this list, so the next tool to grow its own pattern has to
    come here and say so. Round 392's lesson (`swe/toolliveness.py`): a
    hand-written subject set is the bug, not the guard.
"""

import ast
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
_SKILL_SCRIPTS = os.path.join(REPO, "skills", "skill-authoring", "scripts")
if _SKILL_SCRIPTS not in sys.path:
    sys.path.insert(0, _SKILL_SCRIPTS)

from harness import roundheadings as rh          # noqa: E402
from harness.swe import toolliveness as tl       # noqa: E402
import carryforward_check as cf                  # noqa: E402

LIVE = os.path.join(REPO, "state", "research-state.md")
ARCHIVE = os.path.join(REPO, "state", "research-state-archive.md")

# The heading round 448 actually wrote, verbatim, before round 449 normalised
# it. Kept as a fixture precisely because the document was edited: the shape
# has to stay testable after the live instance is gone, or the next round
# re-learns it from a false gap report.
R448 = ("## Round 448 (NUC-integration E) — 2026-09-02, box DOWN, "
        "third consecutive down E round")

# Every module in this repo that parses a round-entry heading. `module` is
# importable; `sees` maps a heading line to the round it attributes it to, or
# None. Adding a parser to the repo without adding it here fails
# `test_no_undeclared_heading_parser_exists_in_the_repo`.
PARSERS = {
    "harness/roundheadings.py":
        lambda line: (rh.parse_heading(line).rounds[0]
                      if rh.parse_heading(line) else None),
    "harness/swe/toolliveness.py":
        lambda line: tl._round_of_line("x.md", 1, [line]),
    "skills/skill-authoring/scripts/carryforward_check.py":
        lambda line: (list(cf.round_sections(line + "\nbody\n")) or [None])[0],
    "skills/session-inheritance-audit/scripts/check_round_recorded.py":
        None,   # delegates wholly to roundheadings; covered by its own suite
}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------ agreement on ONE heading

@pytest.mark.parametrize("name", sorted(p for p, f in PARSERS.items() if f))
def test_every_declared_parser_sees_the_round_448_heading(name):
    """The live drift, as a fixture. `carryforward_check` answered None here
    until round 449; that is the whole finding, frozen."""
    assert PARSERS[name](R448) == 448


@pytest.mark.parametrize("name", sorted(p for p, f in PARSERS.items() if f))
@pytest.mark.parametrize("line", [
    "### Round 395 — SWE-loop(D) — 2026-08-31",
    "## Round 396 (language C) — v0.35, decision 44",
    "#### Round 12 detail",
])
def test_every_declared_parser_agrees_with_the_definition(name, line):
    assert PARSERS[name](line) == rh.parse_heading(line).rounds[0], line


@pytest.mark.parametrize("name", sorted(p for p, f in PARSERS.items() if f))
@pytest.mark.parametrize("line", [
    "## Round log",
    "## Next steps (as of round 448)",
    "## Round 3.5 — an interlude",
    "  ### Round 7 — indented",
])
def test_no_declared_parser_invents_a_round(name, line):
    assert PARSERS[name](line) is None, line


# ------------------------------------------------ agreement on the RECORD

def test_carryforward_sections_cover_exactly_the_recorded_rounds():
    """`round_sections` keys == `heading_rounds`, minus span headings.

    A span (`### Rounds 114-126 — did not run`) is a boundary but not a key:
    handing one block of prose to thirteen rounds would make each of them
    look like it had an entry of its own, which is the opposite of what the
    scoping is for.
    """
    for path in (LIVE, ARCHIVE):
        text = _read(path)
        singular = {h.rounds[0] for h in rh.headings(text) if not h.is_span}
        assert set(cf.round_sections(text)) == singular, path


def test_the_live_record_has_no_round_without_a_section():
    """The exact shape round 448 was in: recorded, and scoped to nobody."""
    text = _read(LIVE)
    missing = rh.heading_rounds(text) - set(cf.round_sections(text))
    assert missing == set(), sorted(missing)


def test_toolliveness_attributes_a_span_to_its_first_round_not_its_neighbour():
    """The archive defect this adoption fixed, stated as a fact.

    The old `^#{2,3} Round (\\d+)` walked straight past a span heading and
    attributed all thirteen of rounds 114-126's lines to round **113**.
    """
    lines = ["### Round 113 — harness(A) — 2026-08-25",
             "- body of 113",
             "### Rounds 114-126 — driver-level, mostly did not run",
             "- body of the span"]
    assert tl._round_of_line("state/research-state.md", 4, lines) == 114
    old = re.compile(r"^#{2,3} Round (\d+)\b")
    assert old.match(lines[2]) is None, "the old pattern's blindness, pinned"


def test_toolliveness_still_reads_a_round_out_of_a_filename_first():
    """A pre-existing behaviour the adoption must not have moved: a
    `knowledge/round-NNN-*.md` path answers before any heading scan."""
    assert tl._round_of_line("knowledge/round-443-x.md", 1, ["no heading"]) == 443


# ----------------------------------------- the parser set is DERIVED, not listed

# A regex literal that parses a markdown heading whose text begins "Round".
# Deliberately narrow: it looks for `#` and `Round` in the same pattern, so
# `\bRound (\d{1,4})\b` (a prose citation matcher, e.g. toolliveness.ROUND_RE)
# does not count and does not have to be declared.
_HEADING_PATTERN_RE = re.compile(r"#.*Rounds?")

# Files that may legally contain a heading regex without being a parser:
# this module and the two test suites that pin what the old patterns did.
_EXEMPT = {
    "harness/tests/test_headingparser_adoption.py",
    "harness/tests/test_roundheadings.py",
    "harness/tests/test_swe_toolliveness.py",
    "skills/skill-authoring/scripts/test_carryforward_check.py",
    "skills/session-inheritance-audit/scripts/test_check_round_recorded.py",
}

_SKIP_DIRS = ("/.venv/", "/research-env/", "/node_modules/", "/.git/",
              "/state/swe/", "/state/whence/", "/state/harness/",
              "/state/skills/", "/nuc/hermes-dump/")


def _repo_python_files():
    for base, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if not name.endswith(".py"):
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, REPO)
            if any(s in "/" + rel.replace(os.sep, "/") + "/"
                   for s in _SKIP_DIRS):
                continue
            yield rel, full


def _heading_regexes(path):
    """Every string literal in `path` that compiles a markdown ROUND heading.

    Read out of the AST, not by grepping the text, so a pattern inside a
    docstring or a comment — this repo is full of both, quoting the old
    patterns on purpose — is not mistaken for a live one.
    """
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        dotted = getattr(fn, "attr", None) or getattr(fn, "id", None)
        if dotted not in ("compile", "match", "search", "finditer", "findall",
                          "fullmatch", "sub", "split"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if _HEADING_PATTERN_RE.search(arg.value):
                    out.append(arg.value)
    return out


def test_no_undeclared_heading_parser_exists_in_the_repo():
    """The census that makes this file self-maintaining.

    Round 392's finding, applied to itself: a hand-written subject set is
    the bug. If a module starts compiling its own round-heading pattern, it
    lands here as a failure naming the file — not as a false gap report six
    rounds later.
    """
    found = {}
    for rel, full in _repo_python_files():
        rel_posix = rel.replace(os.sep, "/")
        if rel_posix in _EXEMPT or rel_posix in PARSERS:
            continue
        pats = _heading_regexes(full)
        if pats:
            found[rel_posix] = pats
    assert found == {}, (
        "undeclared round-heading parser(s) — add to PARSERS with an "
        "agreement test, or make them read harness.roundheadings: %r" % found)


def test_the_census_actually_finds_the_parsers_it_is_meant_to_find():
    """A derived subject set that finds nothing is indistinguishable from a
    broken one. Both declared parsers that still hold a pattern must be
    visible to the census scanner."""
    for rel in ("harness/swe/toolliveness.py",
                "skills/skill-authoring/scripts/carryforward_check.py"):
        pats = _heading_regexes(os.path.join(REPO, rel))
        assert pats, rel

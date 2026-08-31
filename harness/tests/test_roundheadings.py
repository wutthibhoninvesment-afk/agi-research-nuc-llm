"""Round 397 (harness A) — one definition of a round-entry heading.

The bug these pin: `check_round_recorded.py`'s `^### Round (\\d+) [—-]` is a
format contract nothing on the writing side enforces, so a legal entry can
be reported as a missing one. Confirmed live twice — round 302 (2026-08-29,
papered over by editing the document) and round 396 (2026-08-31, which
became round 397's entire prompt NOTE). See `harness/roundheadings.py`.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from harness import roundheadings as rh

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

# The two headings this module exists because of, verbatim.
R396 = ("## Round 396 (language C) — v0.35, decision 44: the sentence that "
        "was three divergences")
R302 = "### Round 302 (language C) — Whence v0.14.10 — 2026-08-29"
CANON = "### Round 395 — SWE-loop(D) — 2026-08-31"


# ---------------------------------------------------------------- singular

def test_canonical_heading_parses_and_is_flagged_canonical():
    h = rh.parse_heading(CANON)
    assert h.rounds == (395,)
    assert h.level == 3
    assert h.is_span is False
    assert h.canonical is True


def test_round_396_live_heading_is_recognised_but_not_canonical():
    h = rh.parse_heading(R396)
    assert h is not None, "the live round-396 heading must not read as a gap"
    assert h.rounds == (396,)
    assert h.level == 2
    assert h.canonical is False


def test_round_302_historical_heading_is_recognised_but_not_canonical():
    h = rh.parse_heading(R302)
    assert h is not None
    assert h.rounds == (302,)
    assert h.level == 3, "level 3 — what made it non-canonical was the `(`"
    assert h.canonical is False


def test_old_strict_regex_really_did_miss_both():
    """The regression this module removes, stated as a fact about the old
    pattern rather than as narration."""
    import re
    old = re.compile(r"^### Round (\d+) [—-]")
    assert old.match(CANON)
    assert not old.match(R396)
    assert not old.match(R302)


@pytest.mark.parametrize("level", ["##", "###", "####", "#####"])
def test_every_admitted_heading_level_parses(level):
    h = rh.parse_heading("%s Round 7 — harness(A) — 2026-01-01" % level)
    assert h.rounds == (7,)
    assert h.level == len(level)


def test_level_1_is_not_a_round_heading():
    assert rh.parse_heading("# Round 7 — harness(A)") is None


def test_level_6_is_not_a_round_heading():
    assert rh.parse_heading("###### Round 7 — harness(A)") is None


def test_heading_with_no_separator_at_all_still_parses():
    h = rh.parse_heading("#### Round 12 detail")
    assert h.rounds == (12,)
    assert h.canonical is False


def test_leading_whitespace_before_hashes_is_not_a_heading():
    assert rh.parse_heading("  ### Round 7 — harness(A)") is None


# ------------------------------------------------------------ non-headings

@pytest.mark.parametrize("line", [
    "## Round log",
    "## Round log (rounds 1-136)",
    "## Round log (rounds 137-174)",
    "### Rounds — did not run",
    "Round 7 — harness(A)",
    "## Rounding 7 up",
    "## Next steps (as of round 334)",
    "",
])
def test_lines_that_must_never_read_as_a_round_heading(line):
    assert rh.parse_heading(line) is None, line


def test_round_number_is_not_read_out_of_a_decimal():
    """`## Round 3.5` would otherwise silently record round 3."""
    assert rh.parse_heading("## Round 3.5 — an interlude") is None


def test_five_digit_round_number_is_refused():
    assert rh.parse_heading("## Round 12345 — nope") is None


# --------------------------------------------------------------- span form

@pytest.mark.parametrize("dash", ["-", "‒", "–", "—"])
def test_span_heading_expands_across_every_dash_the_corpus_uses(dash):
    h = rh.parse_heading("### Rounds 12%s13 — did not run" % dash)
    assert h.rounds == (12, 13)
    assert h.is_span is True
    assert h.canonical is False


def test_archive_span_heading_verbatim():
    h = rh.parse_heading(
        "### Rounds 114-126 — driver-level, mostly did not run — 2026-08-25/26")
    assert h.rounds == tuple(range(114, 127))
    assert len(h.rounds) == 13


def test_span_wider_than_the_cap_is_refused_not_expanded():
    """A `### Rounds 1-400 — summary` must not mask 400 real gaps."""
    assert rh.MAX_SPAN_WIDTH == 64
    assert rh.parse_heading("### Rounds 1-400 — summary") is None
    ok = rh.parse_heading("### Rounds 1-64 — summary")
    assert ok is not None and len(ok.rounds) == 64


def test_backwards_span_is_refused():
    assert rh.parse_heading("### Rounds 30-12 — backwards") is None


def test_singular_round_with_a_date_is_not_read_as_a_span():
    """The reason the span form requires the PLURAL. `### Round 400 —
    2026-09-01` must be round 400, not the span 400..2026."""
    h = rh.parse_heading("### Round 400 — 2026-09-01")
    assert h.rounds == (400,)
    assert h.is_span is False


# ------------------------------------------------------- document-level API

DOC = "\n".join([
    "# Research State",
    "",
    "## Round log",
    "",
    CANON,
    "- did a thing",
    "",
    R396,
    "- did another thing",
    "",
    "### Rounds 12-13 — did not run",
    "",
    "## Next steps (as of round 396)",
    "1. something",
])


def test_heading_rounds_unions_singular_and_span():
    assert rh.heading_rounds(DOC) == {395, 396, 12, 13}


def test_headings_carry_path_and_line_numbers():
    hs = rh.headings(DOC, path="doc.md")
    assert [h.line for h in hs] == [5, 8, 11]
    assert all(h.path == "doc.md" for h in hs)


def test_nonstandard_headings_lists_only_the_drifted_ones():
    ns = rh.nonstandard_headings(DOC, path="doc.md")
    assert [h.rounds for h in ns] == [(396,), (12, 13)]


def test_nonstandard_headings_only_rounds_filter_scopes_the_report():
    """The archive's span headings are real, correct and permanently
    non-canonical; a caller adjudicating only modern rounds must not be
    told about them on every single run forever."""
    ns = rh.nonstandard_headings(DOC, path="doc.md", only_rounds={396, 395})
    assert [h.rounds for h in ns] == [(396,)]


def test_nonstandard_headings_empty_when_only_rounds_matches_nothing():
    assert rh.nonstandard_headings(DOC, only_rounds=set()) == []


def test_heading_as_dict_is_json_shaped():
    d = rh.parse_heading(R396, path="p.md", lineno=3).as_dict()
    assert d == {"text": R396, "level": 2, "rounds": [396], "is_span": False,
                 "canonical": False, "path": "p.md", "line": 3}


# --------------------------------------------------- the live repo, pinned

def test_live_record_round_396_is_recorded():
    """The exact false gap that produced round 397's prompt NOTE."""
    with open(os.path.join(REPO, "state/research-state.md")) as f:
        text = f.read()
    assert 396 in rh.heading_rounds(text)


def test_live_record_is_a_superset_of_what_the_old_pattern_saw():
    """Widening a detector must never LOSE a round it already recognised."""
    import re
    old = re.compile(r"^### Round (\d+) [—-]", re.MULTILINE)
    for rel in ("state/research-state.md", "state/research-state-archive.md"):
        with open(os.path.join(REPO, rel)) as f:
            text = f.read()
        was = {int(m.group(1)) for m in old.finditer(text)}
        now = rh.heading_rounds(text)
        assert was <= now, "%s lost %s" % (rel, sorted(was - now))


def test_live_archive_span_headings_are_all_expanded():
    with open(os.path.join(REPO, "state/research-state-archive.md")) as f:
        text = f.read()
    rounds = rh.heading_rounds(text)
    for n in (12, 13, 114, 120, 126, 128, 129, 131, 135):
        assert n in rounds, n


def test_live_record_has_no_duplicate_round_headings():
    """Two headings for one round would make the record ambiguous about
    which entry is that round's. Zero today; pinned so it stays that way."""
    with open(os.path.join(REPO, "state/research-state.md")) as f:
        text = f.read()
    seen, dupes = set(), []
    for h in rh.headings(text):
        for n in h.rounds:
            if n in seen:
                dupes.append(n)
            seen.add(n)
    assert dupes == [], dupes


# ------------------------------------------------------------------- CLI

def test_cli_reports_the_live_non_canonical_heading():
    out = subprocess.run(
        [sys.executable, "-m", "harness.roundheadings",
         "state/research-state.md"],
        cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "non-canonical" in out.stdout
    assert "Round 396" in out.stdout


def test_cli_with_no_args_is_a_usage_error():
    out = subprocess.run([sys.executable, "-m", "harness.roundheadings"],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 2
    assert "usage" in out.stderr


def test_cli_missing_file_is_rc2_not_a_traceback():
    out = subprocess.run(
        [sys.executable, "-m", "harness.roundheadings", "no/such/file.md"],
        cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 2
    assert "Traceback" not in out.stderr

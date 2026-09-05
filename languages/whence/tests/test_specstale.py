"""`specstale.py` — a version-named section is a date stamp.

Round 507 (skills B). Closes round 506's next-step #4.

This file leads with the two SCOPE ERRORS that made the instrument's first
two drafts return clean, plausible, entirely false answers, because both are
the kind of bug a passing test suite is compatible with:

  * a staleness marker is a property of a SENTENCE, and the first draft
    tested it against the whole SECTION. `## v0.12 (round 122)` is 132 lines
    and carries a `Stale-note correction (round 240)` about an unrelated
    bullet, so one marker anywhere in it exempted everything — replayed
    against the pre-round-506 SPEC the tool reported 34 findings and NOT the
    one bullet round 506 had proved stale;
  * a claim's subject is what the CLAIMING SENTENCE names, and the second
    draft took the whole paragraph. `parser.py:388` is a fourteen-line
    comment; taking its paragraph took five extra identifiers, each of which
    matches thirty unrelated sections.

Both are pinned below against a synthetic document reproducing the exact
shape, so neither needs an 11 000-line fixture and neither can regress
quietly.
"""

import io
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import specstale as SS                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WHENCE = os.path.dirname(HERE)
REPO = os.path.normpath(os.path.join(WHENCE, "..", ".."))
SPEC = os.path.join(WHENCE, "SPEC.md")


# --------------------------------------------------------------------------
# The founding case, as a synthetic document. `## v0.12` has TWO bullets: one
# already corrected about something unrelated, one describing a mechanism a
# later range statement says is gone.
# --------------------------------------------------------------------------

FOUNDING_SPEC = """\
# A document

## v0.12 (round 122) — structural types
- **A return annotation is checked.** **Stale-note correction (round 240):
  this used to say something else about `retspec`.** Nothing here concerns
  the parameter half.
- **A type annotation is erased at parse time.**
  `fn f(a: num)` desugars, in the parser, to one leading
  `let a = typed(a, "num", "parameter 'a' of f")` per annotated parameter.

## v0.19 (round 344) — parameter contracts
- The contract rides on the node now.
"""

FOUNDING_SOURCE = """\
MAX_NESTING = 60

# Structural types (v0.12): the primitive tags an annotation may name.
# Resolved at parse time to a spec EXPRESSION (`_type_spec_expr`) carried on
# the node — `param_types` for parameters, `ret_type` for a `-> Type`.
# v0.12-v0.18 erased a PARAMETER annotation further, into a prepended
# `typed(...)` guard statement; SPEC decision 29 explains why it no longer
# is.
"""


def audit_founding(**kw):
    return SS.audit(FOUNDING_SPEC, "spec.md",
                    [("parser.py", FOUNDING_SOURCE)], **kw)


class TestTheFoundingCase:
    def test_the_stale_bullet_is_reported(self):
        findings, stats = audit_founding()
        t001 = [f for f in findings if f.code == "T001"]
        assert len(t001) == 1, [str(f) for f in t001]
        assert "desugars" in FOUNDING_SPEC.split("\n")[t001[0].line_no - 1] \
            or "type annotation is erased" in \
            FOUNDING_SPEC.split("\n")[t001[0].line_no - 1]

    def test_the_sibling_bullets_marker_does_not_cover_it(self):
        """THE regression pin for scope error one.

        Falsified deliberately: with block granularity removed — that is,
        asking `is_marked` about the whole section — the section's round-240
        note answers True and the finding vanishes. That is the false clean
        answer this instrument shipped once.
        """
        secs = SS.sections(FOUNDING_SPEC, "spec.md")
        v12 = [s for s in secs if s.version == (0, 12, 0)][0]
        stmt = SS.range_statements(FOUNDING_SOURCE, "parser.py")[0]
        assert SS.is_marked(v12.text, stmt) is True     # the section: marked
        blks = SS.blocks(v12.text, v12.line_no)
        assert len(blks) >= 2
        marked = [SS.is_marked(b, stmt) for _, b in blks]
        assert True in marked and False in marked, \
            "a section-wide marker is exempting a bullet it does not govern"

    def test_the_claiming_sentence_is_the_subject_not_the_paragraph(self):
        """Scope error two: `_type_spec_expr`, `param_types` and `ret_type`
        are in the same comment and are NOT what the range claim is about."""
        st = SS.range_statements(FOUNDING_SOURCE, "parser.py")[0]
        assert "typed" in st["terms"]
        for wrong in ("_type_spec_expr", "param_types", "ret_type"):
            assert wrong not in st["terms"], \
                "%s came from a neighbouring sentence" % wrong
        assert st["widened"] is False

    def test_a_claim_with_no_backticked_subject_widens_and_says_so(self):
        src = "# v0.12-v0.18 did something, described in plain words only.\n"
        st = SS.range_statements(src, "x.py")[0]
        assert st["widened"] is True


class TestSections:
    def test_a_subsection_does_not_truncate_its_parent(self):
        text = ("## v0.14 (round 146)\nalpha\n"
                "### v0.14 guest parity (round 164)\nbeta\n"
                "## v0.15 (round 168)\ngamma\n")
        secs = SS.sections(text, "s.md")
        parent = [s for s in secs if s.title.startswith("v0.14 (")][0]
        assert "beta" in parent.text and "gamma" not in parent.text

    def test_a_heading_with_no_version_is_not_a_section(self):
        secs = SS.sections("## Design notes\nx\n## v0.2 (round 3)\ny\n", "s")
        assert [SS.vstr(s.version) for s in secs] == ["0.2"]


class TestVersionOrdering:
    def test_a_three_part_version_sorts_after_its_two_part_parent(self):
        assert SS.vtuple("0.14") < SS.vtuple("0.14.1") < SS.vtuple("0.15")

    def test_vstr_round_trips_the_common_forms(self):
        assert SS.vstr(SS.vtuple("0.14")) == "0.14"
        assert SS.vstr(SS.vtuple("0.14.3")) == "0.14.3"

    def test_a_reversed_range_is_normalised(self):
        st = SS.range_statements("see `x` in v0.18-v0.12\n", "f")[0]
        assert (st["lo"], st["hi"]) == (SS.vtuple("0.12"), SS.vtuple("0.18"))

    def test_a_bare_decimal_pair_is_not_a_version_range(self):
        assert SS.range_statements("a tolerance of 0.12-0.18 on `x`\n",
                                   "f") == []


class TestMarkers:
    STMT = {"raw": "v0.12-v0.18", "lo": SS.vtuple("0.12"),
            "hi": SS.vtuple("0.18")}

    def test_restating_the_range_marks_a_block(self):
        assert SS.is_marked("in v0.12-v0.18 this held", self.STMT)

    def test_the_en_dash_spelling_is_the_same_marker(self):
        assert SS.is_marked("in v0.12–v0.18 this held", self.STMT)

    def test_a_different_range_does_not_mark(self):
        assert not SS.is_marked("in v0.4-v0.6 this held", self.STMT)

    def test_the_prose_markers_work(self):
        for phrase in ("Stale-note correction (round 507):", "no longer",
                       "used to", "superseded"):
            assert SS.is_marked("a bullet that says %s here" % phrase,
                                self.STMT), phrase


class TestTermFiltering:
    def test_a_term_in_most_sections_is_dropped_and_a_rare_one_is_not(self):
        secs = SS.sections(
            "".join("## v0.%d (r)\n`let` and `x`\n" % i for i in range(2, 12))
            + "## v0.12 (r)\n`let` and `rareterm`\n", "s.md")
        common = SS.common_terms(secs, 0.25)
        assert "let" in common and "rareterm" not in common

    def test_max_df_one_disables_the_filter(self):
        secs = SS.sections("## v0.2 (r)\n`let`\n", "s.md")
        assert SS.common_terms(secs, 1.0) == set()

    def test_rarity_score_prefers_the_rarer_term(self):
        df, n = {"common": 90, "rare": 1}, 100
        assert SS.rarity_score({"rare"}, df, n) > \
            SS.rarity_score({"common"}, df, n)


class TestWindow:
    def test_low_is_narrower_than_all_and_keeps_the_founding_case(self):
        low, s_low = audit_founding(window_mode="low")
        allw, s_all = audit_founding(window_mode="all")
        assert s_low["unmarked"] >= 1
        assert s_all["unmarked"] >= s_low["unmarked"]

    def test_a_window_with_no_section_is_reported_as_a_blind_spot(self):
        findings, stats = SS.audit("## v0.9 (r)\n`x`\n", "s.md",
                                   [("f.py", "# v0.4-v0.6 `x` was different\n")])
        assert stats["blind"] == 1
        assert [f.code for f in findings] == ["T002"]


class TestAcknowledgement:
    def test_a_key_is_content_pinned_not_line_pinned(self):
        v = SS.vtuple("0.12")
        a = SS.block_key(v, "- **Alpha** says a thing\n  and continues\n")
        b = SS.block_key(v, "- **Alpha** says a thing\n  and continues more\n")
        c = SS.block_key(v, "- **Alpha** says another thing\n")
        assert a == b, "a change below the head must not move the key"
        assert a != c, "rewriting the head must expire the entry"

    def test_an_acknowledged_block_is_not_reported(self):
        findings, stats = audit_founding()
        f = [x for x in findings if x.code == "T001"][0]
        secs = SS.sections(FOUNDING_SPEC, "spec.md")
        sec = max((s for s in secs if s.line_no <= f.line_no),
                  key=lambda s: s.line_no)
        key = [SS.block_key(sec.version, b)
               for ln, b in SS.blocks(sec.text, sec.line_no)
               if ln == f.line_no][0]
        _, stats2 = audit_founding(acknowledged={key: {"head": "x",
                                                       "reason": "audited"}})
        assert stats2["unmarked"] == 0 and stats2["acknowledged"] == 1

    def test_an_acknowledgement_matching_nothing_expires_loudly(self):
        """The hand-built NON-ZERO. An expiry control whose only evidence is
        an empty result cannot be told from one that never fires — round 506
        proved that on a gitignore pin, one file over."""
        findings, stats = audit_founding(
            acknowledged={"v0.12|nosuchdigest": {"head": "gone",
                                                 "reason": "stale entry"}})
        assert stats["expired"] == 1
        t003 = [f for f in findings if f.code == "T003"]
        assert len(t003) == 1 and "drop the entry" in t003[0].message

    def test_a_missing_registry_is_not_an_error(self):
        assert SS.load_acknowledged(tempfile.mkdtemp()) == {}

    def test_an_unparseable_registry_fails_open(self):
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "state", "whence"))
        io.open(os.path.join(tmp, "state", "whence",
                             "specstale-acknowledged.json"),
                "w", encoding="utf-8").write("{not json")
        assert SS.load_acknowledged(tmp) == {}


# --------------------------------------------------------------------------
# Live corpus. These read the real SPEC.md and the real registry.
# --------------------------------------------------------------------------

class TestLiveCorpus:
    def test_the_real_spec_has_no_unmarked_and_no_expired_block(self):
        rc = SS.main(["--strict", "--top", "0"])
        assert rc == 0

    def test_every_acknowledgement_carries_a_reason_somebody_wrote(self):
        ack = SS.load_acknowledged(REPO)
        assert ack, "the registry is empty; the pin below asserts nothing"
        for key, entry in ack.items():
            assert entry.get("reason"), key
            assert "FILL IN" not in entry["reason"], \
                "%s still carries the --emit-ack skeleton text" % key
            assert len(entry["reason"]) >= 80, \
                "%s: a one-clause reason is not a hand audit" % key

    def test_round_507s_four_corrections_are_all_marked_at_head(self):
        """The round's own finding, pinned by CONTENT rather than by line.

        Each of these four bullets described, in the present tense, a
        mechanism v0.19 deleted, and each names at least one function that
        exists nowhere in the tree.
        """
        spec = io.open(SPEC, encoding="utf-8").read()
        for phrase in ("the builtin the v0.12-v0.18 parameter\n  guard called",
                       "guest parity shipped round 158) built a",
                       "read this bullet's\n  \"now\" as round 320's now",
                       "**Parameter guards needed no evaluator change at "
                       "all.** A guard was"):
            assert phrase in spec, phrase

    def test_the_deleted_guard_functions_are_really_gone(self):
        """What makes those four corrections FACTS rather than opinions. If
        a future round reintroduces parameter guards this goes red, and the
        SPEC corrections above become wrong — which is the right coupling."""
        host = io.open(os.path.join(WHENCE, "whence", "parser.py"),
                       encoding="utf-8").read()
        assert "def _apply_type_guards" not in host
        guest = io.open(os.path.join(WHENCE, "examples", "self_eval.lang"),
                        encoding="utf-8").read()
        assert "fn apply_type_guards" not in guest
        assert "fn build_guards" not in guest

"""Tests for xref_check.py. Run:  python3 -m unittest test_xref_check -v

Fully offline. Every unit test builds a throwaway repo under tempfile; the
live-corpus tests at the bottom only READ this checkout.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xref_check  # noqa: E402

REPO_ROOT = xref_check.DEFAULT_REPO_ROOT


def codes(findings):
    return sorted(f.code for f in findings)


def ids_in(findings, code):
    return sorted(f.message.split("'")[1] for f in findings if f.code == code)


class TmpRepo(object):
    """A minimal stand-in workspace. Creates the top-level directories the
    real repo has, because X004's anchoring rule keys off exactly those."""

    def __init__(self, tops=("skills", "state", "knowledge", "languages",
                             "harness", "logs", "nuc")):
        self.root = tempfile.mkdtemp(prefix="xref-")
        for t in tops:
            os.makedirs(os.path.join(self.root, t), exist_ok=True)

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


# --------------------------------------------------------------------------
# Scopes
# --------------------------------------------------------------------------

class TestScopeOf(unittest.TestCase):
    def test_frozen_beats_historical_and_authoritative(self):
        self.assertEqual(xref_check.scope_of("state/swe/round-137/SPEC.md"),
                         "frozen")
        self.assertEqual(xref_check.scope_of("node_modules/x/README.md"),
                         "frozen")

    def test_knowledge_and_archive_are_historical(self):
        self.assertEqual(xref_check.scope_of("knowledge/round-300-x.md"),
                         "historical")
        self.assertEqual(
            xref_check.scope_of("state/research-state-archive.md"),
            "historical")
        self.assertEqual(
            xref_check.scope_of("state/round-345-predictions.md"),
            "historical")
        self.assertEqual(xref_check.scope_of("nuc/predictions-e1.md"),
                         "historical")

    def test_the_live_state_file_is_authoritative_not_historical(self):
        # `research-state.md` and `research-state-archive.md` differ by one
        # word; the archive is dated history, the live file is what the next
        # round acts on. Getting this backwards would silence the loudest
        # part of the corpus.
        self.assertEqual(xref_check.scope_of("state/research-state.md"),
                         "authoritative")
        self.assertEqual(xref_check.scope_of("skills/x/SKILL.md"),
                         "authoritative")
        self.assertEqual(xref_check.scope_of("languages/whence/whence/x.py"),
                         "authoritative")

    def test_a_dotted_top_level_directory_is_frozen(self):
        for rel in (".venv/lib/x.py", ".pytest_cache/x.py",
                    "skills/a/.pytest_cache/x.py", "./.venv/x.py"):
            self.assertEqual(xref_check.scope_of(rel), "frozen", rel)

    def test_a_directory_merely_named_state_is_not_frozen(self):
        self.assertEqual(xref_check.scope_of("nuc/state/swe/notes.md"),
                         "authoritative")


class TestWalkFiles(unittest.TestCase):
    def test_frozen_directories_are_never_descended_into(self):
        r = TmpRepo()
        self.addCleanup(r.close)
        r.write("state/swe/round-1/SPEC.md", "decision 99\n")
        r.write("state/notes.md", "hi\n")
        rels = [rel for _, rel, _ in xref_check.walk_files(r.root)]
        self.assertIn("state/notes.md", rels)
        self.assertNotIn("state/swe/round-1/SPEC.md", rels)

    def test_only_scannable_extensions(self):
        r = TmpRepo()
        self.addCleanup(r.close)
        r.write("state/a.md", "x")
        r.write("state/b.json", "x")
        rels = [rel for _, rel, _ in xref_check.walk_files(r.root)]
        self.assertIn("state/a.md", rels)
        self.assertNotIn("state/b.json", rels)


# --------------------------------------------------------------------------
# Registries
# --------------------------------------------------------------------------

class TestSectionBody(unittest.TestCase):
    def test_stops_at_the_next_same_level_heading(self):
        text = "## A\n1. **one**\n\n## B\n2. **two**\n"
        body = xref_check._section_body(text, "A")
        self.assertIn("**one**", body)
        self.assertNotIn("**two**", body)

    def test_deeper_headings_stay_inside(self):
        text = "## A\n1. **one**\n### Sub\n2. **two**\n# Top\n3. **three**\n"
        body = xref_check._section_body(text, "A")
        self.assertIn("**two**", body)
        self.assertNotIn("**three**", body)

    def test_absent_section_is_none_not_empty(self):
        # The difference between 'no-section' and 'empty' is a real diagnosis
        # difference, so this must not collapse to "".
        self.assertIsNone(xref_check._section_body("## Other\nx\n", "A"))

    def test_last_section_runs_to_end_of_file(self):
        body = xref_check._section_body("## A\n1. **one**\n", "A")
        self.assertIn("**one**", body)


class TestOrdinalRegistry(unittest.TestCase):
    def setUp(self):
        self.r = TmpRepo()
        self.addCleanup(self.r.close)

    def test_reads_bold_numbered_entries(self):
        self.r.write("D.md", "## Decisions\n1. **A.** x\n2. **B.** y\n")
        ids, status = xref_check.ordinal_registry(self.r.root, "D.md",
                                                  "Decisions")
        self.assertEqual((ids, status), ({1, 2}, "ok"))

    def test_plain_numbered_steps_are_not_registry_entries(self):
        # A procedure list is not a definition list. Counting `1. do this`
        # would invent registry entries and hide every dangling citation
        # below that number.
        self.r.write("D.md", "## Decisions\n1. do this\n2. then that\n")
        ids, status = xref_check.ordinal_registry(self.r.root, "D.md",
                                                  "Decisions")
        self.assertEqual((ids, status), (set(), "empty"))

    def test_missing_document_and_missing_section_are_distinguished(self):
        self.assertEqual(
            xref_check.ordinal_registry(self.r.root, "nope.md", "Decisions"),
            (set(), "no-doc"))
        self.r.write("D.md", "## Other\n1. **A.** x\n")
        self.assertEqual(
            xref_check.ordinal_registry(self.r.root, "D.md", "Decisions"),
            (set(), "no-section"))

    def test_present_but_empty_section_reports_empty(self):
        # This is exactly CLAUDE.md's `## Ground rules` today, and the whole
        # reason the D-013 result is exact rather than heuristic.
        self.r.write("D.md", "## Decisions\n")
        self.assertEqual(
            xref_check.ordinal_registry(self.r.root, "D.md", "Decisions"),
            (set(), "empty"))

    def test_entries_beyond_the_first_gap_still_count(self):
        self.r.write("D.md", "## Decisions\n1. **A.** x\n7. **G.** y\n")
        ids, _ = xref_check.ordinal_registry(self.r.root, "D.md", "Decisions")
        self.assertEqual(ids, {1, 7})


class TestEmittedCodeRegistry(unittest.TestCase):
    def test_collects_quoted_codes_from_skill_scripts(self):
        r = TmpRepo()
        self.addCleanup(r.close)
        r.write("skills/a/scripts/lint.py", 'err("R001", "x")\nwarn("B002")\n')
        ids, status = xref_check.emitted_code_registry(r.root)
        self.assertEqual(status, "ok")
        self.assertEqual(ids, {"R001", "B002"})

    def test_no_scripts_reports_empty_rather_than_crashing(self):
        r = TmpRepo()
        self.addCleanup(r.close)
        self.assertEqual(xref_check.emitted_code_registry(r.root),
                         (set(), "empty"))


# --------------------------------------------------------------------------
# X004 tokenisation — the false-positive fight
# --------------------------------------------------------------------------

TOPS = {"skills", "state", "knowledge", "languages", "harness", "logs", "nuc"}


def toks(text):
    return list(xref_check.prose_path_tokens(text, TOPS))


class TestProsePathTokens(unittest.TestCase):
    def test_a_backticked_path_is_checkable(self):
        self.assertEqual(toks("see `state/foo.md` now"),
                         [("state/foo.md", 5, True)])

    def test_a_path_cut_by_a_hard_wrap_is_not_checkable(self):
        # The dominant false positive: 72-column prose splits a path across
        # a line break, and the prefix of course does not exist.
        got = toks("`state/known-standing-\ndirty-paths.json`")
        self.assertEqual([(t, c) for t, _, c in got][0],
                         ("state/known-standing-", False))

    def test_a_glob_makes_the_token_untruncatable_but_unchecked(self):
        # `*` is outside the character class, so the match STOPS there and
        # PLACEHOLDER_RE never sees the glob it exists to suppress. The
        # terminator test has to catch this, not the placeholder test.
        got = toks("`logs/round-*.json`")
        self.assertEqual([(t, c) for t, _, c in got][0],
                         ("logs/round-", False))

    def test_documented_placeholders_are_skipped(self):
        got = toks("`knowledge/round-NNN-x.md`")
        self.assertEqual([(t, c) for t, _, c in got],
                         [("knowledge/round-NNN-x.md", False)])

    def test_an_angle_bracket_placeholder_yields_no_token_at_all(self):
        # `<` is outside the character class, so `skills/<name>/SKILL.md`
        # never even forms a candidate. Recorded as a separate case because
        # "suppressed by PLACEHOLDER_RE" and "never matched" are different
        # code paths that happen to give the same right answer.
        self.assertEqual(toks("`skills/<name>/SKILL.md`"), [])

    def test_unanchored_tokens_are_ignored_entirely(self):
        # Not "skipped" — not a candidate at all. `tests/test_bounds.py` is
        # relative to the READER's repo, per claim_check's own rule 4.
        self.assertEqual(toks("run `tests/test_bounds.py`"), [])
        self.assertEqual(toks("see `/tmp/camp/out.json`"), [])

    def test_trailing_punctuation_is_stripped(self):
        got = toks("see `state/foo.md`.")
        self.assertEqual(got[0][0], "state/foo.md")


class TestResolveProsePath(unittest.TestCase):
    def setUp(self):
        self.r = TmpRepo()
        self.addCleanup(self.r.close)
        self.r.write("knowledge/round-019-a-long-slug.md", "x")
        self.r.write("state/research-state.md", "x")

    def resolve(self, tok):
        return xref_check.resolve_prose_path(self.r.root, tok, TOPS)

    def test_exact_hit(self):
        self.assertEqual(self.resolve("state/research-state.md"), "ok")

    def test_abbreviated_reference_resolves_as_a_prefix(self):
        self.assertEqual(self.resolve("knowledge/round-019"), "prefix")

    def test_a_prefix_that_diverges_mid_name_is_still_missing(self):
        # The round-246 case: the citation and the real file share a long
        # prefix but the citation ends `.md` where the file continues. A
        # naive "startswith" in the other direction would have called this
        # resolved and hidden a genuinely broken link.
        self.assertEqual(self.resolve("knowledge/round-019-a-long-slug.md.bak"),
                         "missing")
        self.assertEqual(self.resolve("knowledge/round-019-a-long.md"),
                         "missing")

    def test_you_cannot_descend_into_a_regular_file(self):
        self.assertEqual(
            self.resolve("state/research-state.md/knowledge/git"), "prose")

    def test_two_top_level_directories_joined_is_prose_not_a_path(self):
        self.assertEqual(self.resolve("logs/state"), "prose")

    def test_a_real_directory_below_a_directory_is_not_prose(self):
        os.makedirs(os.path.join(self.r.root, "state", "swe2"))
        self.assertEqual(self.resolve("state/swe2"), "ok")

    def test_plain_miss(self):
        self.assertEqual(self.resolve("state/nope.json"), "missing")


class TestAbsentAllowlist(unittest.TestCase):
    def test_loads_paths_and_tolerates_absence(self):
        r = TmpRepo()
        self.addCleanup(r.close)
        self.assertEqual(xref_check.load_absent_allowlist(r.root), set())
        r.write("state/known-absent-paths.json",
                json.dumps({"paths": {"logs/round-229.json": "why"}}))
        self.assertEqual(xref_check.load_absent_allowlist(r.root),
                         {"logs/round-229.json"})

    def test_malformed_allowlist_fails_closed_to_empty(self):
        # A broken allowlist must make the checker NOISIER, never quieter.
        r = TmpRepo()
        self.addCleanup(r.close)
        r.write("state/known-absent-paths.json", "{not json")
        self.assertEqual(xref_check.load_absent_allowlist(r.root), set())


# --------------------------------------------------------------------------
# End-to-end sweep
# --------------------------------------------------------------------------

class TestSweep(unittest.TestCase):
    def setUp(self):
        self.r = TmpRepo()
        self.addCleanup(self.r.close)
        self.r.write("languages/whence/SPEC.md",
                     "## Anti-mainstream design decisions\n"
                     "1. **One.** a\n2. **Two.** b\n")
        self.r.write("CLAUDE.md", "## Ground rules\n")

    def sweep(self):
        return xref_check.sweep(self.r.root)

    def test_a_citation_past_the_end_of_the_registry_is_dangling(self):
        self.r.write("languages/whence/whence/p.py",
                     "# see SPEC decision 9\n")
        findings, _ = self.sweep()
        self.assertEqual(ids_in(findings, "X001"), ["9"])

    def test_a_citation_inside_the_registry_is_silent(self):
        self.r.write("languages/whence/whence/p.py", "# see decision 2\n")
        findings, _ = self.sweep()
        self.assertEqual(codes(findings), [])

    def test_family_scope_keeps_ordinary_english_out(self):
        # "decision 40" in a NUC plan is not a SPEC pointer.
        self.r.write("nuc/plan.md", "that was decision 40 of the meeting\n")
        findings, _ = self.sweep()
        self.assertEqual(codes(findings), [])

    def test_an_empty_registry_dangles_every_citation(self):
        self.r.write("state/nuc-missions.md", "house rule D-013 applies\n")
        findings, stats = self.sweep()
        self.assertEqual(ids_in(findings, "X002"), ["D-013"])
        self.assertEqual(stats["registries"]["X002"][1], "empty")

    def test_populating_the_registry_clears_the_family(self):
        # The fix the D-013 finding is asking for, proven to work.
        self.r.write("state/nuc-missions.md", "house rule D-013 applies\n")
        self.r.write("CLAUDE.md",
                     "## Ground rules\n13. **D-013 predictions first.** x\n")
        findings, _ = self.sweep()
        self.assertEqual(codes(findings), [])

    def test_historical_files_are_found_but_not_errors(self):
        self.r.write("knowledge/round-100-x.md", "SPEC decision 9\n")
        findings, _ = self.sweep()
        self.assertEqual([f.scope for f in findings], ["historical"])
        self.assertEqual(
            xref_check.report(findings, self.sweep()[1], False), 0)

    def test_authoritative_findings_set_the_exit_code(self):
        self.r.write("state/research-state.md", "SPEC decision 9\n")
        findings, stats = self.sweep()
        self.assertEqual(xref_check.report(findings, stats, False), 1)

    def test_checker_scripts_are_exempt_from_their_own_rules(self):
        self.r.write("skills/a/scripts/tool.py",
                     "'''explains that D-013 dangles'''\n")
        findings, stats = self.sweep()
        self.assertEqual(codes(findings), [])
        self.assertEqual(stats["self_exempt_files"], 1)

    def test_test_files_may_name_fixture_paths_that_do_not_exist(self):
        self.r.write("harness/tests/test_thing.py",
                     "P = 'harness/tests/gone.py'\n")
        findings, _ = self.sweep()
        self.assertEqual(codes(findings), [])

    def test_a_broken_path_in_a_source_comment_is_reported(self):
        self.r.write("harness/swe/guest.py",
                     "# See `knowledge/round-999-nope.md`.\n")
        findings, _ = self.sweep()
        self.assertEqual(codes(findings), ["X004"])

    def test_allowlisted_absent_paths_are_counted_not_reported(self):
        self.r.write("state/known-absent-paths.json",
                     json.dumps({"paths": {"logs/round-229.json": "ghost"}}))
        self.r.write("state/research-state.md",
                     "no `logs/round-229.json` exists\n")
        findings, stats = self.sweep()
        self.assertEqual(codes(findings), [])
        self.assertEqual(stats["paths_absent_ok"], 1)

    def test_wikilinks_are_tallied_and_never_reported(self):
        self.r.write("state/research-state.md", "see [[no_such_memory]]\n")
        findings, stats = self.sweep()
        self.assertEqual(codes(findings), [])
        self.assertEqual(stats["wikilinks"], 1)
        self.assertEqual(stats["wikilinks_dangling"], 1)

    def test_only_restricts_the_sweep(self):
        self.r.write("state/research-state.md", "SPEC decision 9\n")
        self.r.write("state/nuc-missions.md", "SPEC decision 9\n")
        findings, _ = xref_check.sweep(self.r.root,
                                       only={"state/nuc-missions.md"})
        self.assertEqual(len(findings), 0)   # nuc-missions is out of X001's scope
        findings, _ = xref_check.sweep(self.r.root,
                                       only={"state/research-state.md"})
        self.assertEqual(ids_in(findings, "X001"), ["9"])


class TestBaseline(unittest.TestCase):
    def setUp(self):
        self.r = TmpRepo()
        self.addCleanup(self.r.close)
        self.r.write("languages/whence/SPEC.md",
                     "## Anti-mainstream design decisions\n1. **One.** a\n")
        self.r.write("CLAUDE.md", "## Ground rules\n")
        self.r.write("state/research-state.md",
                     "SPEC decision 27 and SPEC decision 28\n")

    def run_with(self, citations):
        self.r.write("state/known-dangling-citations.json",
                     json.dumps({"citations": citations}))
        findings, stats = xref_check.sweep(self.r.root)
        base = xref_check.load_baseline(self.r.root)
        return findings, stats, base

    def test_an_acknowledged_id_stops_setting_the_exit_code(self):
        findings, stats, base = self.run_with({"X001:27": "owner", 
                                               "X001:28": "owner"})
        self.assertEqual(xref_check.report(findings, stats, False, base), 0)

    def test_an_unacknowledged_id_still_turns_it_red(self):
        findings, stats, base = self.run_with({"X001:27": "owner"})
        self.assertEqual(xref_check.report(findings, stats, False, base), 1)

    def test_acknowledging_an_id_covers_every_site_citing_it(self):
        # The point of keying on the identifier: a new FILE citing an
        # already-accepted decision is not a new defect.
        self.r.write("languages/whence/whence/p.py", "# decision 27 again\n")
        findings, stats, base = self.run_with({"X001:27": "o", "X001:28": "o"})
        self.assertEqual(
            len([f for f in findings if f.ident == "27"]), 2)
        self.assertEqual(xref_check.report(findings, stats, False, base), 0)

    def test_a_missing_or_malformed_baseline_leaves_the_check_red(self):
        # Fails OPEN toward noise: losing the baseline must not silently
        # accept the backlog.
        findings, stats = xref_check.sweep(self.r.root)
        self.assertEqual(xref_check.load_baseline(self.r.root), {})
        self.assertEqual(xref_check.report(findings, stats, False, {}), 1)
        self.r.write("state/known-dangling-citations.json", "{oops")
        self.assertEqual(xref_check.load_baseline(self.r.root), {})

    def test_baseline_keys_ignore_file_and_line(self):
        f = xref_check.Finding("a/b.md", 99, "X001", "msg", "authoritative",
                               "27")
        g = xref_check.Finding("z/q.py", 3, "X001", "msg", "authoritative",
                               "27")
        self.assertEqual(f.key, g.key)
        self.assertEqual(f.key, "X001:27")

    def test_x004_findings_are_keyed_by_path(self):
        self.r.write("harness/swe/g.py", "# see `knowledge/round-999-x.md`\n")
        findings, _ = xref_check.sweep(self.r.root)
        keys = {f.key for f in findings if f.code == "X004"}
        self.assertEqual(keys, {"X004:knowledge/round-999-x.md"})


class TestLiveBaselineIsHonest(unittest.TestCase):
    def test_every_baseline_entry_still_corresponds_to_a_real_finding(self):
        # A baseline that outlives its findings is how accepted debt becomes
        # invisible debt: the entry stays, the citation gets fixed, and the
        # next real instance is silently pre-accepted. Fails when an entry
        # should have been DELETED.
        findings, _ = xref_check.sweep(REPO_ROOT)
        live = {f.key for f in findings if f.scope == "authoritative"}
        base = set(xref_check.load_baseline(REPO_ROOT))
        self.assertEqual(base - live, set(),
                         "baseline entries with no matching finding")

    def test_the_live_corpus_has_no_unacknowledged_dangling_citation(self):
        findings, _ = xref_check.sweep(REPO_ROOT)
        base = xref_check.load_baseline(REPO_ROOT)
        new = [str(f) for f in findings
               if f.scope == "authoritative" and f.key not in base]
        self.assertEqual(new, [])


class TestLineNumbers(unittest.TestCase):
    def test_offsets_map_to_one_indexed_lines(self):
        self.assertEqual(xref_check.line_of("a\nb\nc", 0), 1)
        self.assertEqual(xref_check.line_of("a\nb\nc", 2), 2)
        self.assertEqual(xref_check.line_of("a\nb\nc", 4), 3)


class TestMain(unittest.TestCase):
    def test_bad_repo_root_is_usage_error(self):
        self.assertEqual(
            xref_check.main(["--repo-root", "/no/such/dir/anywhere"]), 2)

    def test_bad_path_argument_is_usage_error(self):
        self.assertEqual(xref_check.main(["/no/such/file.md"]), 2)


# --------------------------------------------------------------------------
# Live-corpus positive control
# --------------------------------------------------------------------------
# Round 339's lesson, verbatim: "a corpus sweep needs a POSITIVE CONTROL —
# 'these N, and only these, parse to zero' — not just 'no findings'". A
# regression that empties the scan reads identically to a clean corpus, so
# these tests assert the scan is non-empty and that each registry is still
# being FOUND, independently of how many findings it produces.

class TestLiveCorpusPositiveControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings, cls.stats = xref_check.sweep(REPO_ROOT)

    def test_the_sweep_actually_reads_files(self):
        self.assertGreater(self.stats["files"], 500)
        self.assertGreater(self.stats["historical_files"], 100)

    def test_every_family_still_finds_citations(self):
        # If a scoping regression silences a family, this fails instead of
        # reporting the corpus clean.
        for fam in xref_check.FAMILIES:
            self.assertGreater(self.stats["cited"][fam.code], 0, fam.code)

    def test_the_spec_and_lint_registries_are_found_and_non_empty(self):
        self.assertEqual(self.stats["registries"]["X001"][1], "ok")
        self.assertEqual(self.stats["registries"]["X003"][1], "ok")

    def test_x004_still_resolves_thousands_of_real_paths(self):
        self.assertGreater(self.stats["paths_checked"], 1000)

    def test_the_lint_rule_code_family_is_clean(self):
        # Currently 0 dangling. Pinned so it stays that way: a SKILL.md
        # citing a rule code no script emits is a broken promise to a reader
        # who greps for it.
        self.assertEqual(self.stats["dangling_ids"]["X003"], set())

    def test_frozen_snapshots_contribute_nothing(self):
        rels = {f.rel for f in self.findings}
        self.assertFalse([r for r in rels if r.startswith("state/swe/")])


if __name__ == "__main__":
    unittest.main()

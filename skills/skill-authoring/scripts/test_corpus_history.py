#!/usr/bin/env python3
"""Tests for corpus_history.py (round 363). Offline; no git replay — the
59-commit replay costs minutes, so what is pinned here is the analysis that
turns its raw rows into the claims the knowledge file makes.

The severity split is the point. The first draft of this tool reported "17 of
59 commits RED" and buried the fact that 15 of those were ONE known,
deliberately carried warning (B002) and only 2 were an actual ERROR. Merging
the two would have been the same class of mistake the tool exists to find.
"""

import unittest

import corpus_history as ch


def row(short, red_kind=None, codes=(), warnings=(), subject="Round N (x)",
        date="2026-08-30", index=0):
    checkers = {"skills/skill-authoring/scripts/skill_lint.py": {
        "status": "red" if red_kind else "green",
        "red_kind": red_kind, "errors": list(codes),
        "warnings": list(warnings)}}
    return {"sha": short * 6, "short": short, "date": date, "subject": subject,
            "index": index, "checkers": checkers, "red": bool(red_kind),
            "red_kind": red_kind, "error_codes": sorted(codes),
            "unrunnable": []}


class TestClassify(unittest.TestCase):
    def test_skill_lint_error_is_not_a_warning(self):
        e, w = ch.classify("/x/SKILL.md: ERROR H001 no trigger section")
        self.assertEqual((e, w), (["H001"], []))

    def test_skill_lint_warning_is_not_an_error(self):
        e, w = ch.classify("/x/SKILL.md: WARN B002 body is long")
        self.assertEqual((e, w), ([], ["B002"]))

    def test_case_coverage_lowercase_shapes(self):
        e, w = ch.classify("error: P001 foo: 0 positive case(s)\n"
                           "warning: P004 bar: never probed")
        self.assertEqual((e, w), (["P001"], ["P004"]))

    def test_a_line_with_no_code_contributes_nothing(self):
        self.assertEqual(ch.classify("skill-lint: 31 skill(s), 0 error(s)"),
                         ([], []))


class TestEpisodes(unittest.TestCase):
    def _rows(self, spec):
        return [row("c%d" % i, kind, codes, index=i)
                for i, (kind, codes) in enumerate(spec)]

    def test_error_and_strict_episodes_do_not_merge(self):
        rows = self._rows([("strict", []), ("strict", []), (None, []),
                           ("error", ["P001"])])
        self.assertEqual(len(ch.episodes(rows, "strict")), 1)
        self.assertEqual(len(ch.episodes(rows, "error")), 1)
        self.assertEqual(ch.episodes(rows, "strict")[0]["length"], 2)
        self.assertEqual(ch.episodes(rows, "error")[0]["length"], 1)

    def test_adjacent_episodes_of_different_kind_are_not_one_run(self):
        # a strict commit immediately followed by an error commit is TWO
        # episodes, not one four-commit smear
        rows = self._rows([("strict", []), ("error", ["P001"])])
        self.assertEqual([e["length"] for e in ch.episodes(rows, "strict")], [1])
        self.assertEqual([e["length"] for e in ch.episodes(rows, "error")], [1])

    def test_an_episode_reaching_the_newest_commit_is_marked_open(self):
        rows = self._rows([(None, []), ("error", ["P001"]), ("error", ["P001"])])
        ep = ch.episodes(rows, "error")[0]
        self.assertTrue(ep.get("open"))
        self.assertIsNone(ep["closed_by"])
        self.assertEqual(ep["length"], 2)

    def test_a_closed_episode_names_the_commit_that_closed_it(self):
        rows = self._rows([("error", ["P001"]), (None, [])])
        rows[1]["subject"] = "Round 363 (skills B): the fix"
        ep = ch.episodes(rows, "error")[0]
        self.assertFalse(ep.get("open"))
        self.assertEqual(ep["closed_by"], "Round 363 (skills B): the fix")

    def test_no_red_commits_means_no_episodes(self):
        self.assertEqual(ch.episodes(self._rows([(None, []), (None, [])])), [])

    def test_codes_fall_back_to_warnings_for_a_strict_episode(self):
        rows = [row("a", "strict", (), ("B002",), index=0)]
        self.assertEqual(ch.episodes(rows, "strict")[0]["codes"], ["B002"])


class TestFlagDetection(unittest.TestCase):
    """`supported_flags` reads SOURCE rather than running `--help`, because
    replaying 59 historical versions of two scripts means running code nobody
    in this session has read — and this workspace has already been bitten by a
    script whose `--help` ran its main effect."""

    def test_missing_file_is_no_flags_not_a_crash(self):
        self.assertEqual(ch.supported_flags("/nope/x.py", ["--house"]), set())

    def test_reads_declared_flags_from_source(self):
        import os
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "s.py")
        open(p, "w").write('ap.add_argument("--house")\n'
                           "ap.add_argument('paths', nargs='+')\n")
        self.assertEqual(ch.supported_flags(p, ["--house", "--strict"]),
                         {"--house"})
        self.assertTrue(ch.takes_positional_paths(p))


if __name__ == "__main__":
    unittest.main()

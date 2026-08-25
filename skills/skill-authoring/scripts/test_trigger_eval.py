"""Offline tests for trigger_eval.py (fake runner, no claude CLI needed).
Run:  python3 -m unittest test_trigger_eval -v"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trigger_eval as te  # noqa: E402


def ev(obj):
    return json.dumps(obj)


def stream(invoked=(), text="SKILLS=NONE", cost=0.05, subtype="success",
           available=("alpha", "beta", "host-only")):
    lines = [ev({"type": "system", "subtype": "init", "slash_commands": list(available)})]
    for name in invoked:
        lines.append(ev({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}}))
    lines.append(ev({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}))
    lines.append(ev({"type": "result", "subtype": subtype, "total_cost_usd": cost,
                     "num_turns": 1 + len(invoked), "result": text}))
    return "\n".join(lines) + "\n"


def make_skill(root, name, desc):
    d = os.path.join(root, name)
    os.makedirs(d)
    with open(os.path.join(d, "SKILL.md"), "w") as f:
        f.write("---\nname: %s\ndescription: %s\n---\n# %s\nbody\n" % (name, desc, name))
    with open(os.path.join(d, "extra.txt"), "w") as f:
        f.write("bundled\n")
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        make_skill(self.root, "alpha", "Does alpha. Use when alpha-ish.")
        make_skill(self.root, "beta", "Does beta. Use when beta-ish.")
        self.catalog = te.load_catalog([self.root])
        self.cases_path = os.path.join(self.root, "cases.json")
        with open(self.cases_path, "w") as f:
            json.dump([
                {"id": "a1", "prompt": "do the alpha thing", "expect": ["alpha"]},
                {"id": "b1", "prompt": "do the beta thing", "expect": ["beta"]},
                {"id": "n1", "prompt": "unrelated", "expect": []},
            ], f)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TestParsing(unittest.TestCase):
    def test_parse_stream_collects_skill_tool_uses_in_order(self):
        rec = te.parse_stream(stream(invoked=["beta", "alpha"], text="SKILLS=beta, alpha"))
        self.assertEqual(rec["invoked"], ["beta", "alpha"])
        self.assertEqual(rec["declared"], ["beta", "alpha"])
        self.assertEqual(rec["available"], ["alpha", "beta", "host-only"])
        self.assertAlmostEqual(rec["cost_usd"], 0.05)
        self.assertEqual(rec["turns"], 3)
        self.assertIsNone(rec["error"])

    def test_parse_stream_plugin_prefixed_skill_keeps_tail(self):
        rec = te.parse_stream(stream(invoked=["some-plugin:alpha"]))
        self.assertEqual(rec["invoked"], ["alpha"])

    def test_parse_stream_ignores_non_skill_tools_and_noise(self):
        text = "garbage line\n" + ev({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "x"}}]}}) + "\n" + \
            stream(invoked=[])
        rec = te.parse_stream(text)
        self.assertEqual(rec["invoked"], [])
        self.assertEqual(rec["declared"], [])

    def test_parse_stream_missing_result_is_error(self):
        rec = te.parse_stream(ev({"type": "system", "subtype": "init"}) + "\n")
        self.assertIn("no result event", rec["error"])

    def test_parse_stream_error_subtype(self):
        rec = te.parse_stream(stream(subtype="error_max_budget_usd"))
        self.assertIn("error_max_budget_usd", rec["error"])

    def test_parse_declared_variants(self):
        self.assertEqual(te.parse_declared("SKILLS=NONE"), [])
        self.assertEqual(te.parse_declared("blah\nSKILLS=`a`, b"), ["a", "b"])
        self.assertIsNone(te.parse_declared("I did nothing"))

    def test_parse_catalog_answer_tolerates_fences(self):
        self.assertEqual(te.parse_catalog_answer('```json\n{"skills": ["a"]}\n```'), ["a"])
        self.assertEqual(te.parse_catalog_answer('{"skills": []}'), [])
        self.assertIsNone(te.parse_catalog_answer("no json here"))
        self.assertIsNone(te.parse_catalog_answer('{"other": 1}'))


class TestCatalogAndStaging(Base):
    def test_load_catalog_reads_frontmatter(self):
        names = [n for n, _, _ in self.catalog]
        self.assertEqual(names, ["alpha", "beta"])
        self.assertIn("Use when alpha-ish", self.catalog[0][1])

    def test_load_catalog_accepts_single_skill_dir(self):
        cat = te.load_catalog([os.path.join(self.root, "alpha")])
        self.assertEqual([n for n, _, _ in cat], ["alpha"])

    def test_load_catalog_rejects_bad_frontmatter(self):
        d = os.path.join(self.root, "broken")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("no frontmatter\n")
        with self.assertRaises(ValueError):
            te.load_catalog([self.root])

    def test_stage_skills_copies_whole_dirs(self):
        proj = tempfile.mkdtemp()
        try:
            dest = te.stage_skills(self.catalog, proj)
            self.assertTrue(os.path.isfile(os.path.join(dest, "alpha", "SKILL.md")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "beta", "extra.txt")))
            # idempotent re-stage
            te.stage_skills(self.catalog, proj)
            self.assertTrue(os.path.isfile(os.path.join(dest, "alpha", "SKILL.md")))
        finally:
            shutil.rmtree(proj)

    def test_load_cases_validates(self):
        cases = te.load_cases(self.cases_path)
        self.assertEqual(len(cases), 3)
        bad = os.path.join(self.root, "bad.json")
        with open(bad, "w") as f:
            json.dump([{"id": "x", "prompt": "p", "expect": ["a"]},
                       {"id": "x", "prompt": "p", "expect": []}], f)
        with self.assertRaises(ValueError):
            te.load_cases(bad)
        with open(bad, "w") as f:
            json.dump([{"id": "x", "prompt": "p"}], f)
        with self.assertRaises(ValueError):
            te.load_cases(bad)


class TestProbeAndScoring(Base):
    def test_native_probe_separates_ours_from_foreign(self):
        def runner(argv, cwd, timeout):
            self.assertIn("--tools", argv)
            self.assertEqual(argv[argv.index("--tools") + 1], "Skill")
            self.assertEqual(argv[-1], "do the alpha thing")
            self.assertTrue(os.path.isdir(os.path.join(cwd, ".claude", "skills", "alpha")))
            return 0, stream(invoked=["alpha", "host-only", "alpha"], text="SKILLS=alpha"), ""
        proj = tempfile.mkdtemp()
        try:
            te.stage_skills(self.catalog, proj)
            r = te.run_probe({"id": "a1", "prompt": "do the alpha thing", "expect": ["alpha"]},
                             "native", self.catalog, proj, runner, "claude", "sonnet", 10, 0.5)
        finally:
            shutil.rmtree(proj)
        self.assertEqual(r["fired"], ["alpha"])          # deduped
        self.assertEqual(r["foreign"], ["host-only"])
        self.assertEqual(r["declared"], ["alpha"])
        self.assertIsNone(r["error"])

    def test_native_probe_nonzero_rc_is_error(self):
        def runner(argv, cwd, timeout):
            return 1, "", "boom"
        r = te.run_probe({"id": "a1", "prompt": "x", "expect": ["alpha"]}, "native",
                         self.catalog, self.root, runner, "claude", "sonnet", 10, 0.5)
        self.assertIn("rc=1", r["error"])
        self.assertEqual(r["fired"], [])

    def test_catalog_probe_puts_descriptions_in_prompt(self):
        captured = {}

        def runner(argv, cwd, timeout):
            captured["prompt"] = argv[-1]
            self.assertEqual(argv[argv.index("--tools") + 1], "")
            return 0, json.dumps({"result": '{"skills": ["beta", "zzz"]}',
                                  "total_cost_usd": 0.01, "num_turns": 1}), ""
        r = te.run_probe({"id": "b1", "prompt": "do the beta thing", "expect": ["beta"]},
                         "catalog", self.catalog, self.root, runner, "claude", "sonnet", 10, 0.5)
        self.assertIn("- alpha: Does alpha. Use when alpha-ish.", captured["prompt"])
        self.assertIn("<task>\ndo the beta thing\n</task>", captured["prompt"])
        self.assertEqual(r["fired"], ["beta"])
        self.assertEqual(r["foreign"], ["zzz"])
        self.assertAlmostEqual(r["cost_usd"], 0.01)

    def test_catalog_probe_unparseable_is_error(self):
        def runner(argv, cwd, timeout):
            return 0, json.dumps({"result": "I would use alpha", "total_cost_usd": 0.01}), ""
        r = te.run_probe({"id": "b1", "prompt": "x", "expect": ["beta"]}, "catalog",
                         self.catalog, self.root, runner, "claude", "sonnet", 10, 0.5)
        self.assertIn("unparseable", r["error"])

    def test_score_metrics(self):
        results = [
            {"id": "a1", "expect": ["alpha"], "fired": ["alpha"], "error": None, "cost_usd": 0.1},
            {"id": "a2", "expect": ["alpha"], "fired": [], "error": None, "cost_usd": 0.1},
            {"id": "b1", "expect": ["beta"], "fired": ["beta", "alpha"], "error": None, "cost_usd": 0.1},
            {"id": "n1", "expect": [], "fired": ["alpha"], "error": None, "cost_usd": 0.1},
            {"id": "n2", "expect": [], "fired": [], "error": None, "cost_usd": 0.1},
            {"id": "e1", "expect": ["beta"], "fired": [], "error": "rc=1", "cost_usd": 0.0},
        ]
        m = te.score(results, ["alpha", "beta"])
        self.assertEqual(m["n_ok"], 5)
        self.assertEqual(m["n_err"], 1)
        self.assertEqual(m["exact"], 2)                    # a1, n2
        a, b = m["per_skill"]["alpha"], m["per_skill"]["beta"]
        self.assertEqual((a["tp"], a["fp"], a["fn"]), (1, 2, 1))
        self.assertAlmostEqual(a["recall"], 0.5)
        self.assertAlmostEqual(a["precision"], 1 / 3)
        self.assertEqual((b["tp"], b["fp"], b["fn"]), (1, 0, 0))
        self.assertEqual(b["recall"], 1.0)
        self.assertEqual(m["neg_total"], 2)
        self.assertEqual(m["neg_false_fire"], 1)
        self.assertAlmostEqual(m["cost_usd"], 0.5)

    def test_score_never_fired_skill_has_none_precision(self):
        m = te.score([{"id": "x", "expect": [], "fired": [], "error": None, "cost_usd": 0}], ["alpha"])
        self.assertIsNone(m["per_skill"]["alpha"]["precision"])
        self.assertIsNone(m["per_skill"]["alpha"]["recall"])

    def test_render_report_lists_distractors(self):
        results = [{"id": "a1", "expect": ["alpha"], "fired": ["alpha"], "foreign": ["host-only"],
                    "error": None, "cost_usd": 0.1, "available": ["alpha", "beta", "host-only"]}]
        m = te.score(results, ["alpha", "beta"])
        out = te.render_report(results, m, ["alpha", "beta"], "native", "sonnet")
        self.assertIn("host distractor skills present: host-only", out)
        self.assertIn("| a1 | alpha | alpha | host-only | yes |", out)
        self.assertIn("| alpha | 100% | 100% | 1 | 0 | 0 |", out)


def body_stream(invoked=(), reads=(), bash=(), texts=("done",), cost=0.08):
    lines = [ev({"type": "system", "subtype": "init", "slash_commands": []})]
    content = []
    for name in invoked:
        content.append({"type": "tool_use", "name": "Skill", "input": {"skill": name}})
    for p in reads:
        content.append({"type": "tool_use", "name": "Read", "input": {"file_path": p}})
    for c in bash:
        content.append({"type": "tool_use", "name": "Bash", "input": {"command": c}})
    for t in texts:
        content.append({"type": "text", "text": t})
    lines.append(ev({"type": "assistant", "message": {"content": content}}))
    lines.append(ev({"type": "result", "subtype": "success", "total_cost_usd": cost,
                     "num_turns": 2, "result": texts[-1] if texts else ""}))
    return "\n".join(lines) + "\n"


class TestBodyMode(Base):
    def test_parse_stream_collects_reads_bash_and_all_texts(self):
        rec = te.parse_stream(body_stream(
            invoked=["alpha"], reads=["/tmp/p/.claude/skills/alpha/extra.txt"],
            bash=["python3 .claude/skills/alpha/tool.py --x"],
            texts=["first thoughts", "final answer"]))
        self.assertEqual(rec["reads"], ["/tmp/p/.claude/skills/alpha/extra.txt"])
        self.assertEqual(rec["bash"], ["python3 .claude/skills/alpha/tool.py --x"])
        self.assertEqual(rec["texts"], ["first thoughts", "final answer"])
        self.assertEqual(rec["final_text"], "final answer")

    def test_staged_files_touched_dedupes_and_extracts_rel_paths(self):
        rec = {"reads": ["/tmp/x/.claude/skills/alpha/references/a.md",
                         "/tmp/x/.claude/skills/alpha/references/a.md",
                         "/tmp/other/file.py"],
               "bash": ["python3 /tmp/x/.claude/skills/beta/scripts/lint.py foo"]}
        self.assertEqual(te.staged_files_touched(rec),
                         ["alpha/references/a.md", "beta/scripts/lint.py"])

    def test_body_probe_scores_files_and_evidence(self):
        def runner(argv, cwd, timeout):
            self.assertEqual(argv[argv.index("--tools") + 1], "Skill,Read")
            self.assertIn(te.BODY_SYSTEM, argv)
            return 0, body_stream(
                invoked=["alpha"],
                reads=[os.path.join(cwd, ".claude/skills/alpha/extra.txt")],
                texts=["I will use a MockLLM with a fake clock.",
                       "def test_retry(): assert backoff == [1, 2, 4]"]), ""
        case = {"id": "b1", "prompt": "test the retry path", "expect": ["alpha"],
                "body": {"files": ["alpha/extra.txt", "alpha/missing.md"],
                         "evidence": ["mockllm", "fake\\s+clock", "no-such-thing"]}}
        r = te.run_probe(case, "body", self.catalog, self.root, runner,
                         "claude", "sonnet", 10, 0.5)
        self.assertEqual(r["fired"], ["alpha"])
        b = r["body"]
        self.assertEqual(b["files_read"], ["alpha/extra.txt"])
        self.assertEqual(b["files_hit"], ["alpha/extra.txt"])
        self.assertEqual(b["evidence_hit"], ["mockllm", "fake\\s+clock"])
        self.assertGreater(b["transcript_chars"], 0)
        self.assertIn("MockLLM", b["transcript_tail"])

    def test_body_case_without_body_spec_gets_empty_expectations(self):
        def runner(argv, cwd, timeout):
            return 0, body_stream(invoked=["alpha"]), ""
        r = te.run_probe({"id": "b2", "prompt": "x", "expect": ["alpha"]}, "body",
                         self.catalog, self.root, runner, "claude", "sonnet", 10, 0.5)
        self.assertEqual(r["body"]["files_expected"], [])
        self.assertEqual(r["body"]["evidence_expected"], [])

    def test_load_cases_validates_body_field(self):
        bad = os.path.join(self.root, "badbody.json")
        with open(bad, "w") as f:
            json.dump([{"id": "x", "prompt": "p", "expect": [], "body": "nope"}], f)
        with self.assertRaises(ValueError):
            te.load_cases(bad)
        with open(bad, "w") as f:
            json.dump([{"id": "x", "prompt": "p", "expect": [],
                        "body": {"evidence": ["[unclosed"]}}], f)
        with self.assertRaises(ValueError):
            te.load_cases(bad)
        with open(bad, "w") as f:
            json.dump([{"id": "x", "prompt": "p", "expect": [],
                        "body": {"files": ["a/b.md"], "evidence": ["ok"]}}], f)
        self.assertEqual(len(te.load_cases(bad)), 1)

    def test_score_body_aggregates(self):
        results = [
            {"id": "b1", "expect": ["alpha"], "fired": ["alpha"], "error": None,
             "cost_usd": 0.1, "body": {"files_hit": ["a"], "files_expected": ["a"],
                                       "evidence_hit": ["e1", "e2"],
                                       "evidence_expected": ["e1", "e2"]}},
            {"id": "b2", "expect": ["alpha"], "fired": ["alpha"], "error": None,
             "cost_usd": 0.1, "body": {"files_hit": [], "files_expected": ["a"],
                                       "evidence_hit": ["e1"],
                                       "evidence_expected": ["e1", "e2"]}},
        ]
        m = te.score(results, ["alpha"])
        self.assertEqual(m["body"], {"n": 2, "followed": 1, "files_hit": 1,
                                     "files_expected": 2, "evidence_hit": 3,
                                     "evidence_expected": 4})

    def test_render_report_body_section(self):
        results = [{"id": "b1", "expect": ["alpha"], "fired": ["alpha"],
                    "foreign": [], "error": None, "cost_usd": 0.1, "available": [],
                    "body": {"files_read": ["alpha/extra.txt"],
                             "files_hit": ["alpha/extra.txt"],
                             "files_expected": ["alpha/extra.txt"],
                             "evidence_hit": ["x"], "evidence_expected": ["x", "y"],
                             "transcript_chars": 120}}]
        m = te.score(results, ["alpha"])
        out = te.render_report(results, m, ["alpha"], "body", "sonnet")
        self.assertIn("body-following: 0/1 cases fully followed", out)
        self.assertIn("| b1 | alpha | alpha/extra.txt | — | 1/1 | 1/2 | 120 |", out)


class TestDistractors(Base):
    def setUp(self):
        super().setUp()
        self.wild = tempfile.mkdtemp()
        cat = os.path.join(self.wild, "category")
        os.makedirs(cat)
        make_skill(cat, "gamma", "Wild gamma skill. Use for gamma tasks.")
        make_skill(cat, "delta", "Wild delta skill. Use for delta tasks.")
        make_skill(self.wild, "epsilon", "Wild epsilon skill.")
        broken = os.path.join(self.wild, "broken")
        os.makedirs(broken)
        with open(os.path.join(broken, "SKILL.md"), "w") as f:
            f.write("no frontmatter at all\n")

    def tearDown(self):
        shutil.rmtree(self.wild, ignore_errors=True)
        super().tearDown()

    def test_recursive_lenient_catalog_finds_nested_and_skips_broken(self):
        cat = te.load_catalog([self.wild], lenient=True, recursive=True)
        self.assertEqual(sorted(n for n, _, _ in cat), ["delta", "epsilon", "gamma"])

    def test_recursive_without_lenient_raises_on_broken(self):
        with self.assertRaises(ValueError):
            te.load_catalog([self.wild], recursive=True)

    def test_pick_distractors_deterministic_and_excludes_ours(self):
        pool = te.load_catalog([self.wild], lenient=True, recursive=True)
        pool.append(("alpha", "shadows ours", "/x/alpha"))
        p1 = te.pick_distractors(pool, ["alpha"], 2, seed=7)
        p2 = te.pick_distractors(pool, ["alpha"], 2, seed=7)
        self.assertEqual([n for n, _, _ in p1], [n for n, _, _ in p2])
        self.assertEqual(len(p1), 2)
        self.assertNotIn("alpha", [n for n, _, _ in p1])
        full = te.pick_distractors(pool, ["alpha"], -1, seed=7)
        self.assertEqual([n for n, _, _ in full], ["delta", "epsilon", "gamma"])

    def test_probe_classifies_staged_distractor_separately(self):
        def runner(argv, cwd, timeout):
            return 0, stream(invoked=["gamma", "alpha", "host-only"],
                             text="SKILLS=gamma, alpha"), ""
        r = te.run_probe({"id": "a1", "prompt": "x", "expect": ["alpha"]}, "native",
                         self.catalog, self.root, runner, "claude", "sonnet", 10, 0.5,
                         distractor_names=frozenset(["gamma", "delta"]))
        self.assertEqual(r["fired"], ["alpha"])
        self.assertEqual(r["distractors"], ["gamma"])
        self.assertEqual(r["foreign"], ["host-only"])

    def test_score_counts_displacement(self):
        results = [
            {"id": "a", "expect": ["alpha"], "fired": [], "distractors": ["gamma"],
             "error": None, "cost_usd": 0.1},
            {"id": "b", "expect": ["alpha"], "fired": ["alpha"], "distractors": ["gamma"],
             "error": None, "cost_usd": 0.1},
            {"id": "c", "expect": [], "fired": [], "distractors": [],
             "error": None, "cost_usd": 0.1},
        ]
        m = te.score(results, ["alpha"])
        self.assertEqual(m["displaced"], 1)
        self.assertEqual(m["distractor_fires"], 2)

    def test_render_report_lists_staged_distractors_and_displacement(self):
        results = [{"id": "a1", "expect": ["alpha"], "fired": [], "foreign": [],
                    "distractors": ["gamma"], "error": None, "cost_usd": 0.1,
                    "available": ["alpha", "gamma", "host-only"]}]
        m = te.score(results, ["alpha"])
        out = te.render_report(results, m, ["alpha"], "native", "sonnet",
                               distractor_names=frozenset(["gamma", "delta"]))
        self.assertIn("staged distractors (2): delta, gamma", out)
        self.assertIn("staged-distractor fires: gamma×1", out)
        self.assertIn("displacement", out)
        self.assertIn("host distractor skills present: host-only", out)
        self.assertIn("| a1 | alpha | — | gamma | — | NO |", out)

    def test_main_stages_distractors(self):
        staged = {}

        def fake(argv, cwd, timeout):
            staged["dirs"] = sorted(os.listdir(os.path.join(cwd, ".claude", "skills")))
            return 0, stream(invoked=["alpha"], text="SKILLS=alpha"), ""
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--only", "a1", "--distractors", self.wild,
                          "--n-distractors", "2", "--distractor-seed", "3"])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 0)
        self.assertEqual(len(staged["dirs"]), 4)  # alpha, beta + 2 distractors
        self.assertIn("alpha", staged["dirs"])


class TestMultiModel(Base):
    def test_main_runs_every_case_per_model_and_reports_both(self):
        seen_models = []

        def fake(argv, cwd, timeout):
            m = argv[argv.index("--model") + 1]
            seen_models.append(m)
            p = argv[-1]
            name = "alpha" if "alpha" in p else ("beta" if "beta" in p else None)
            fire = [name] if name and m == "sonnet" else []  # haiku misses all
            return 0, stream(invoked=fire, text="SKILLS=%s" % (name or "NONE")), ""
        out = os.path.join(self.root, "mm.json")
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--model", "sonnet,haiku", "--json", out])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 1)  # haiku misses → not all exact
        self.assertEqual(sorted(set(seen_models)), ["haiku", "sonnet"])
        self.assertEqual(len(seen_models), 6)  # 3 cases × 2 models
        with open(out) as f:
            data = json.load(f)
        self.assertEqual(data["models"], ["sonnet", "haiku"])
        self.assertEqual(data["metrics_by_model"]["sonnet"]["exact"], 3)
        self.assertEqual(data["metrics_by_model"]["haiku"]["exact"], 1)  # neg only
        self.assertEqual(data["metrics"]["n_ok"], 6)

    def test_render_model_comparison_table(self):
        results_s = [{"id": "a1", "expect": ["alpha"], "fired": ["alpha"],
                      "error": None, "cost_usd": 0.1}]
        results_h = [{"id": "a1", "expect": ["alpha"], "fired": [],
                      "error": None, "cost_usd": 0.05}]
        mm = {"sonnet": te.score(results_s, ["alpha"]),
              "haiku": te.score(results_h, ["alpha"])}
        out = te.render_model_comparison(mm, ["alpha"], ["sonnet", "haiku"])
        self.assertIn("| alpha | 100% | 0% |", out)
        self.assertIn("| exact-match | 100% | 0% |", out)


class TestMain(Base):
    def _run(self, argv, fake):
        orig = te.default_runner
        te.default_runner = fake
        try:
            return te.main(argv)
        finally:
            te.default_runner = orig

    def test_main_exit_0_when_all_match_and_writes_json(self):
        def fake(argv, cwd, timeout):
            p = argv[-1]
            name = "alpha" if "alpha" in p else ("beta" if "beta" in p else None)
            return 0, stream(invoked=[name] if name else [], text="SKILLS=%s" % (name or "NONE")), ""
        out = os.path.join(self.root, "out.json")
        rc = self._run([self.cases_path, "--skills", self.root, "--json", out, "--quiet",
                        "--concurrency", "2"], fake)
        self.assertEqual(rc, 0)
        with open(out) as f:
            data = json.load(f)
        self.assertEqual(data["metrics"]["exact"], 3)
        self.assertEqual([r["id"] for r in data["results"]], ["a1", "b1", "n1"])

    def test_main_exit_1_on_mismatch_and_repeats(self):
        def fake(argv, cwd, timeout):
            return 0, stream(invoked=[], text="SKILLS=NONE"), ""
        rc = self._run([self.cases_path, "--skills", self.root, "--quiet", "--repeats", "2",
                        "--only", "a1,n1"], fake)
        self.assertEqual(rc, 1)

    def test_main_exit_2_when_every_probe_errors(self):
        def fake(argv, cwd, timeout):
            return 127, "", "no such executable"
        rc = self._run([self.cases_path, "--skills", self.root, "--quiet"], fake)
        self.assertEqual(rc, 2)

    def test_main_exit_2_on_unknown_expected_skill(self):
        with open(self.cases_path, "w") as f:
            json.dump([{"id": "x", "prompt": "p", "expect": ["gamma"]}], f)
        rc = self._run([self.cases_path, "--skills", self.root, "--quiet"],
                       lambda a, c, t: (0, "", ""))
        self.assertEqual(rc, 2)


# ------------------------------------------------------------- v4 helpers --
def a_msg(*content):
    return {"type": "assistant", "message": {"content": list(content)}}


def t_use(name, tid=None, **inp):
    d = {"type": "tool_use", "name": name, "input": inp}
    if tid:
        d["id"] = tid
    return d


def u_result(tid, text, is_error=False, as_string=False):
    content = text if as_string else [{"type": "text", "text": text}]
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "is_error": is_error,
         "content": content}]}}


RESULT_EV = {"type": "result", "subtype": "success", "total_cost_usd": 0.05,
             "num_turns": 2, "result": "done"}

DENIAL = "Claude requested permissions to use Read, but you haven't granted it."


def events(*evs):
    return "\n".join(ev(e) for e in evs) + "\n"


class TestDeniedReads(Base):
    def test_parse_stream_matches_tool_results_to_reads(self):
        text = events(
            a_msg(t_use("Read", "t1", file_path="/p/.claude/skills/alpha/extra.txt"),
                  t_use("Read", "t2", file_path="/p/other.md")),
            u_result("t1", DENIAL, is_error=True),
            u_result("t2", "file contents"),
            a_msg({"type": "text", "text": "done"}),
            RESULT_EV)
        rec = te.parse_stream(text)
        self.assertEqual(rec["reads"],
                         ["/p/.claude/skills/alpha/extra.txt", "/p/other.md"])
        self.assertEqual(len(rec["reads_failed"]), 1)
        f = rec["reads_failed"][0]
        self.assertEqual(f["path"], "/p/.claude/skills/alpha/extra.txt")
        self.assertTrue(f["denied"])
        self.assertIn("granted", f["reason"])

    def test_non_permission_error_is_failed_but_not_denied(self):
        text = events(
            a_msg(t_use("Read", "t1", file_path="/p/.claude/skills/alpha/x.md")),
            u_result("t1", "File does not exist.", is_error=True),
            RESULT_EV)
        rec = te.parse_stream(text)
        self.assertEqual(len(rec["reads_failed"]), 1)
        self.assertFalse(rec["reads_failed"][0]["denied"])

    def test_tool_result_content_as_plain_string(self):
        text = events(
            a_msg(t_use("Read", "t1", file_path="/p/.claude/skills/alpha/x.md")),
            u_result("t1", DENIAL, is_error=True, as_string=True),
            RESULT_EV)
        rec = te.parse_stream(text)
        self.assertTrue(rec["reads_failed"][0]["denied"])

    def test_staged_files_touched_excludes_fully_failed_reads(self):
        rec = {"reads": ["/p/.claude/skills/alpha/a.md",
                         "/p/.claude/skills/alpha/b.md"],
               "reads_failed": [{"path": "/p/.claude/skills/alpha/a.md",
                                 "reason": DENIAL, "denied": True}],
               "bash": []}
        self.assertEqual(te.staged_files_touched(rec), ["alpha/b.md"])

    def test_staged_files_touched_keeps_retried_successful_read(self):
        rec = {"reads": ["/p/.claude/skills/alpha/a.md",
                         "/p/.claude/skills/alpha/a.md"],
               "reads_failed": [{"path": "/p/.claude/skills/alpha/a.md",
                                 "reason": "transient", "denied": False}],
               "bash": []}
        self.assertEqual(te.staged_files_touched(rec), ["alpha/a.md"])

    def test_staged_files_failed_maps_to_relative_paths(self):
        rec = {"reads_failed": [
            {"path": "/p/.claude/skills/alpha/refs/x.md", "reason": DENIAL,
             "denied": True},
            {"path": "/p/unrelated.md", "reason": "nope", "denied": False}]}
        out = te.staged_files_failed(rec)
        self.assertEqual(out, [{"file": "alpha/refs/x.md", "reason": DENIAL,
                                "denied": True}])

    def test_body_probe_denied_read_not_credited(self):
        def runner(argv, cwd, timeout):
            path = os.path.join(cwd, ".claude/skills/alpha/extra.txt")
            return 0, events(
                a_msg(t_use("Skill", "s1", skill="alpha")),
                u_result("s1", "loaded"),
                a_msg(t_use("Read", "t1", file_path=path)),
                u_result("t1", DENIAL, is_error=True),
                a_msg({"type": "text", "text": "did the task"}),
                RESULT_EV), ""
        case = {"id": "b1", "prompt": "x", "expect": ["alpha"],
                "body": {"files": ["alpha/extra.txt"], "evidence": []}}
        r = te.run_probe(case, "body", self.catalog, self.root, runner,
                         "claude", "sonnet", 10, 0.5)
        b = r["body"]
        self.assertEqual(b["files_read"], [])
        self.assertEqual(b["files_hit"], [])
        self.assertEqual(b["files_failed"],
                         [{"file": "alpha/extra.txt", "reason": DENIAL,
                           "denied": True}])

    def test_render_report_marks_denied_reads(self):
        results = [{"id": "b1", "expect": ["alpha"], "fired": ["alpha"],
                    "foreign": [], "error": None, "cost_usd": 0.1, "available": [],
                    "body": {"files_read": [], "files_hit": [],
                             "files_failed": [{"file": "alpha/extra.txt",
                                               "reason": DENIAL, "denied": True}],
                             "files_expected": ["alpha/extra.txt"],
                             "evidence_hit": [], "evidence_expected": [],
                             "transcript_chars": 10}}]
        m = te.score(results, ["alpha"])
        out = te.render_report(results, m, ["alpha"], "body", "sonnet")
        self.assertIn("alpha/extra.txt (denied)", out)


class TestFireRates(Base):
    def _r(self, cid, expect, fired, err=None, distractors=()):
        return {"id": cid, "expect": expect, "fired": fired, "error": err,
                "cost_usd": 0.01, "distractors": list(distractors),
                "foreign": [], "available": []}

    def test_per_case_splits_hit_from_exact(self):
        results = [
            self._r("a1", ["alpha"], ["alpha"]),          # exact + hit
            self._r("a1", ["alpha"], ["alpha", "beta"]),  # hit, not exact
            self._r("a1", ["alpha"], []),                 # neither
            self._r("a1", ["alpha"], [], err="rc=1"),     # errored
        ]
        m = te.score(results, ["alpha", "beta"])
        pc = m["per_case"]["a1"]
        self.assertEqual((pc["n"], pc["err"]), (3, 1))
        self.assertEqual(pc["hit"], 2)
        self.assertEqual(pc["exact"], 1)
        self.assertAlmostEqual(pc["hit_rate"], 2 / 3)
        self.assertAlmostEqual(pc["exact_rate"], 1 / 3)

    def test_negative_case_hit_means_nothing_fired(self):
        results = [self._r("n1", [], []), self._r("n1", [], ["alpha"])]
        m = te.score(results, ["alpha"])
        pc = m["per_case"]["n1"]
        self.assertEqual(pc["hit"], 1)
        self.assertEqual(pc["exact"], 1)

    def test_per_case_counts_distractor_fires_and_displacement(self):
        results = [
            self._r("a1", ["alpha"], [], distractors=["gamma"]),
            self._r("a1", ["alpha"], ["alpha"], distractors=["gamma"]),
        ]
        m = te.score(results, ["alpha"])
        pc = m["per_case"]["a1"]
        self.assertEqual(pc["distractor_fired"], 2)
        self.assertEqual(pc["displaced"], 1)

    def test_render_report_rate_table_only_with_repeats(self):
        single = [self._r("a1", ["alpha"], ["alpha"])]
        m1 = te.score(single, ["alpha"])
        out1 = te.render_report(single, m1, ["alpha"], "native", "sonnet")
        self.assertNotIn("per-case fire rates", out1)
        double = single + [self._r("a1", ["alpha"], [])]
        m2 = te.score(double, ["alpha"])
        out2 = te.render_report(double, m2, ["alpha"], "native", "sonnet")
        self.assertIn("per-case fire rates", out2)
        self.assertIn("| a1 | 2 | 1 (50%) | 1 (50%) | 0 |", out2)


class TestEvidenceMin(Base):
    def test_load_cases_validates_evidence_min(self):
        bad = os.path.join(self.root, "em.json")
        for val in (-1, 3, True, "2"):
            with open(bad, "w") as f:
                json.dump([{"id": "x", "prompt": "p", "expect": [],
                            "body": {"evidence": ["a", "b"],
                                     "evidence_min": val}}], f)
            with self.assertRaises(ValueError):
                te.load_cases(bad)
        with open(bad, "w") as f:
            json.dump([{"id": "x", "prompt": "p", "expect": [],
                        "body": {"evidence": ["a", "b"], "evidence_min": 1}}], f)
        self.assertEqual(te.load_cases(bad)[0]["body"]["evidence_min"], 1)

    def test_run_probe_records_evidence_min(self):
        def runner(argv, cwd, timeout):
            return 0, body_stream(invoked=["alpha"], texts=["marker-a here"]), ""
        case = {"id": "b1", "prompt": "x", "expect": ["alpha"],
                "body": {"evidence": ["marker-a", "marker-b", "marker-c"],
                         "evidence_min": 1}}
        r = te.run_probe(case, "body", self.catalog, self.root, runner,
                         "claude", "sonnet", 10, 0.5)
        self.assertEqual(r["body"]["evidence_min"], 1)
        self.assertEqual(r["body"]["evidence_hit"], ["marker-a"])

    def test_score_followed_uses_evidence_min(self):
        base = {"id": "b", "expect": ["alpha"], "fired": ["alpha"],
                "error": None, "cost_usd": 0.1}
        partial = dict(base, body={"files_hit": [], "files_expected": [],
                                   "evidence_hit": ["e1", "e2"],
                                   "evidence_expected": ["e1", "e2", "e3"],
                                   "evidence_min": 2})
        m = te.score([partial], ["alpha"])
        self.assertEqual(m["body"]["followed"], 1)
        strict = dict(base, body={"files_hit": [], "files_expected": [],
                                  "evidence_hit": ["e1", "e2"],
                                  "evidence_expected": ["e1", "e2", "e3"]})
        m2 = te.score([strict], ["alpha"])
        self.assertEqual(m2["body"]["followed"], 0)

    def test_render_report_shows_min(self):
        results = [{"id": "b1", "expect": ["alpha"], "fired": ["alpha"],
                    "foreign": [], "error": None, "cost_usd": 0.1, "available": [],
                    "body": {"files_read": [], "files_hit": [], "files_failed": [],
                             "files_expected": [],
                             "evidence_hit": ["x"], "evidence_expected": ["x", "y"],
                             "evidence_min": 1, "transcript_chars": 5}}]
        m = te.score(results, ["alpha"])
        out = te.render_report(results, m, ["alpha"], "body", "sonnet")
        self.assertIn("1/2 (min 1)", out)


class TestPaired(Base):
    def setUp(self):
        super().setUp()
        self.wild = tempfile.mkdtemp()
        make_skill(self.wild, "gamma", "Wild gamma skill. Use for gamma tasks.")

    def tearDown(self):
        shutil.rmtree(self.wild, ignore_errors=True)
        super().tearDown()

    def _pm(self, rows):
        """Build a metrics-like dict with just per_case."""
        return {"per_case": rows}

    def test_paired_verdicts_classify(self):
        plain = self._pm({
            "a": {"expect": ["alpha"], "n": 4, "hit": 4, "displaced": 0,
                  "distractor_fired": 0},
            "b": {"expect": ["beta"], "n": 4, "hit": 3, "displaced": 0,
                  "distractor_fired": 0},
            "c": {"expect": ["alpha"], "n": 4, "hit": 4, "displaced": 0,
                  "distractor_fired": 0},
            "n": {"expect": [], "n": 4, "hit": 4, "displaced": 0,
                  "distractor_fired": 0}})
        staged = self._pm({
            "a": {"expect": ["alpha"], "n": 4, "hit": 1, "displaced": 0,
                  "distractor_fired": 0},                     # SUPPRESSED
            "b": {"expect": ["beta"], "n": 4, "hit": 2, "displaced": 0,
                  "distractor_fired": 1},                     # noise?
            "c": {"expect": ["alpha"], "n": 4, "hit": 1, "displaced": 2,
                  "distractor_fired": 3},                     # DISPLACED
            "n": {"expect": [], "n": 4, "hit": 4, "displaced": 0,
                  "distractor_fired": 0}})
        v = {x["id"]: x for x in te.paired_verdicts(plain, staged)}
        self.assertEqual(v["a"]["verdict"], "SUPPRESSED")
        self.assertEqual(v["b"]["verdict"], "noise?")
        self.assertEqual(v["c"]["verdict"], "DISPLACED")
        self.assertNotIn("n", v)                              # negatives skipped

    def test_paired_verdict_ok_when_no_drop(self):
        plain = self._pm({"a": {"expect": ["alpha"], "n": 4, "hit": 3,
                                "displaced": 0, "distractor_fired": 0}})
        staged = self._pm({"a": {"expect": ["alpha"], "n": 4, "hit": 4,
                                 "displaced": 0, "distractor_fired": 0}})
        v = te.paired_verdicts(plain, staged)
        self.assertEqual(v[0]["verdict"], "ok")

    def test_render_paired_table(self):
        v = [{"id": "a", "expect": ["alpha"], "plain": "4/4", "staged": "1/4",
              "staged_distractor_fires": 0, "gap": 3, "verdict": "SUPPRESSED"}]
        out = te.render_paired(v, "sonnet")
        self.assertIn("| a | 4/4 | 1/4 | -3 | 0 run(s) | SUPPRESSED |", out)

    def test_main_paired_requires_distractors(self):
        rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                      "--paired"])
        self.assertEqual(rc, 2)

    def test_main_paired_runs_both_arms_and_reports_suppression(self):
        def fake(argv, cwd, timeout):
            has_gamma = os.path.isdir(
                os.path.join(cwd, ".claude", "skills", "gamma"))
            p = argv[-1]
            name = "alpha" if "alpha" in p else ("beta" if "beta" in p else None)
            fire = [name] if (name and not has_gamma) else []
            return 0, stream(invoked=fire,
                             text="SKILLS=%s" % (name or "NONE")), ""
        out = os.path.join(self.root, "paired.json")
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--paired", "--distractors", self.wild,
                          "--repeats", "2", "--json", out])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 1)          # staged arm misses
        with open(out) as f:
            data = json.load(f)
        self.assertTrue(data["paired"])
        self.assertEqual(len(data["results"]), 12)   # 3 cases × 2 reps × 2 arms
        arms = {r["arm"] for r in data["results"]}
        self.assertEqual(arms, {"plain", "staged"})
        v = {x["id"]: x for x in data["paired_by_model"]["sonnet"]}
        self.assertEqual(v["a1"]["verdict"], "SUPPRESSED")
        self.assertEqual(v["a1"]["plain"], "2/2")
        self.assertEqual(v["a1"]["staged"], "0/2")
        am = data["metrics_by_model_arm"]["sonnet"]
        self.assertEqual(am["plain"]["exact"], 6)    # 3 cases × 2 repeats
        self.assertEqual(am["staged"]["exact"], 2)   # only the negative ×2


class TestCanary(Base):
    def _canary(self, sentinels):
        p = os.path.join(self.root, "canary.json")
        with open(p, "w") as f:
            json.dump(sentinels, f)
        return p

    def test_load_canary_validates(self):
        for bad in ([], [{"case": "a1"}], [{"min_rate": 0.5}],
                    [{"case": "a1", "min_rate": 1.5}],
                    [{"case": "a1", "min_rate": 0.9, "max_rate": 0.5}],
                    [{"case": "a1", "min_rate": 0.5, "repeats": 0}],
                    [{"case": "a1", "min_rate": 0.5, "mode": "weird"}]):
            with self.assertRaises(ValueError):
                te.load_canary(self._canary(bad))
        one = te.load_canary(self._canary(
            {"case": "a1", "min_rate": 0.75}))    # single-dict form
        self.assertEqual(one, [{"case": "a1", "model": "sonnet", "repeats": 4,
                                "min_rate": 0.75, "max_rate": 1.0,
                                "mode": "native", "protocol": None}])
        with self.assertRaises(ValueError):
            te.load_canary(self._canary(
                [{"case": "a1", "min_rate": 0.5, "protocol": "lax"}]))
        strict = te.load_canary(self._canary(
            [{"case": "a1", "min_rate": 0.5, "protocol": "strict"}]))
        self.assertEqual(strict[0]["protocol"], "strict")

    def test_canary_sentinel_protocol_overrides_run_protocol(self):
        # two sentinels: one pinned to strict, one inheriting the run's default
        p = self._canary([{"case": "a1", "min_rate": 0.5, "repeats": 2,
                           "protocol": "strict"},
                          {"case": "a1", "min_rate": 0.5, "repeats": 2}])
        prompts = []

        def fake(argv, cwd, timeout):
            prompts.append(argv[-2])
            return 0, stream(invoked=["alpha"], text="SKILLS=alpha"), ""
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--protocol", "default", "--canary", p])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 0)
        strict_n = sum("invalid answer" in x for x in prompts)
        self.assertEqual((strict_n, len(prompts)), (2, 4))
        # v4.2: with no --protocol the run itself is strict, so both inherit it
        prompts.clear()
        te.default_runner = fake
        try:
            te.main([self.cases_path, "--skills", self.root, "--quiet", "--canary", p])
        finally:
            te.default_runner = orig
        self.assertEqual(sum("invalid answer" in x for x in prompts), 4)

    def test_main_canary_ok_and_json(self):
        p = self._canary([{"case": "a1", "min_rate": 0.75, "repeats": 3}])
        out = os.path.join(self.root, "canary-out.json")

        def fake(argv, cwd, timeout):
            return 0, stream(invoked=["alpha"], text="SKILLS=alpha"), ""
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--canary", p, "--json", out])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 0)
        with open(out) as f:
            data = json.load(f)
        rec = data["canary"][0]
        self.assertEqual(rec["status"], "OK")
        self.assertEqual(rec["hit"], 3)
        self.assertEqual(rec["n_ok"], 3)

    def test_main_canary_drift_exits_1(self):
        p = self._canary([{"case": "a1", "min_rate": 0.75, "repeats": 2}])

        def fake(argv, cwd, timeout):
            return 0, stream(invoked=[], text="SKILLS=NONE"), ""
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--canary", p])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 1)

    def test_main_canary_unknown_case_exits_2(self):
        p = self._canary([{"case": "zz", "min_rate": 0.5}])
        rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                      "--canary", p])
        self.assertEqual(rc, 2)

    def test_main_canary_all_errors_inconclusive(self):
        p = self._canary([{"case": "a1", "min_rate": 0.5, "repeats": 2}])

        def fake(argv, cwd, timeout):
            return 1, "", "boom"
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--canary", p])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 2)

    def test_canary_negative_case_band_is_no_fire(self):
        p = self._canary([{"case": "n1", "min_rate": 1.0, "repeats": 2}])

        def fake(argv, cwd, timeout):
            return 0, stream(invoked=[], text="SKILLS=NONE"), ""
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--canary", p])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 0)


class TestTranscripts(Base):
    def test_main_writes_full_transcripts(self):
        tdir = os.path.join(self.root, "transcripts")

        def fake(argv, cwd, timeout):
            p = argv[-1]
            name = "alpha" if "alpha" in p else ("beta" if "beta" in p else None)
            return 0, stream(invoked=[name] if name else [],
                             text="SKILLS=%s" % (name or "NONE")), ""
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--transcripts", tdir, "--repeats", "2"])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 0)
        files = sorted(os.listdir(tdir))
        self.assertEqual(len(files), 6)              # 3 cases × 2 repeats
        self.assertIn("sonnet-a1-0.txt", files)
        self.assertIn("sonnet-a1-1.txt", files)
        with open(os.path.join(tdir, "sonnet-a1-0.txt")) as f:
            body = f.read()
        self.assertIn("case: a1", body)
        self.assertIn("fired: ['alpha']", body)
        self.assertIn("SKILLS=alpha", body)


class TestBaseline(Base):
    def _m(self, cases):
        """Build a metrics dict from {id: (expect, [fired-sets...])}."""
        results = []
        for cid, (expect, fires) in cases.items():
            for fired in fires:
                results.append({"id": cid, "expect": expect, "fired": fired,
                                "error": None, "cost_usd": 0.01,
                                "distractors": [], "foreign": [],
                                "available": []})
        return te.score(results, ["alpha", "beta"])

    def test_same_rates_verdict_same(self):
        base = self._m({"a1": (["alpha"], [["alpha"], ["alpha"]])})
        new = self._m({"a1": (["alpha"], [["alpha"], ["alpha"]])})
        rows = te.compare_reports(base, new)
        self.assertEqual(rows[0]["verdict"], "same")
        self.assertEqual(rows[0]["hit_delta"], 0.0)

    def test_equal_n_uses_count_gap(self):
        # 4/4 -> 3/4 is one flip (noise?); 4/4 -> 2/4 is a regression
        base = self._m({"a1": (["alpha"], [["alpha"]] * 4)})
        one = self._m({"a1": (["alpha"], [["alpha"]] * 3 + [[]])})
        two = self._m({"a1": (["alpha"], [["alpha"]] * 2 + [[], []])})
        self.assertEqual(te.compare_reports(base, one)[0]["verdict"], "noise?")
        self.assertEqual(te.compare_reports(base, two)[0]["verdict"], "REGRESSED")

    def test_unequal_n_uses_rate_delta(self):
        base = self._m({"a1": (["alpha"], [["alpha"]] * 2)})          # 2/2
        new = self._m({"a1": (["alpha"], [["alpha"], [], []])})       # 1/3
        rows = te.compare_reports(base, new)
        self.assertEqual(rows[0]["verdict"], "REGRESSED")
        mild = self._m({"a1": (["alpha"], [["alpha"]] * 3 + [[]])})  # 3/4
        self.assertEqual(te.compare_reports(base, mild)[0]["verdict"], "noise?")

    def test_improved_and_cofire(self):
        base = self._m({"a1": (["alpha"], [[], []]),
                        "b1": (["beta"], [["beta"], ["beta"]])})
        new = self._m({"a1": (["alpha"], [["alpha"], ["alpha"]]),
                       "b1": (["beta"], [["beta", "alpha"], ["beta", "alpha"]])})
        rows = {r["id"]: r for r in te.compare_reports(base, new)}
        self.assertEqual(rows["a1"]["verdict"], "IMPROVED")
        # b1 still fires 2/2 but exact fell 2/2 -> 0/2: a sibling now co-fires
        self.assertEqual(rows["b1"]["verdict"], "CO-FIRE")

    def test_new_and_dropped_cases_are_listed(self):
        base = self._m({"a1": (["alpha"], [["alpha"]]),
                        "old": (["beta"], [["beta"]])})
        new = self._m({"a1": (["alpha"], [["alpha"]]),
                       "fresh": (["beta"], [["beta"]])})
        rows = {r["id"]: r for r in te.compare_reports(base, new)}
        self.assertEqual(rows["fresh"]["verdict"], "new")
        self.assertEqual(rows["old"]["verdict"], "dropped")
        self.assertIsNone(rows["old"]["new"])

    def test_render_comparison_summary_and_flags(self):
        base = self._m({"a1": (["alpha"], [["alpha"]] * 4),
                        "n1": ([], [[], [], [], []])})
        new = self._m({"a1": (["alpha"], [["alpha"]] * 2 + [[], []]),
                       "n1": ([], [["beta"], [], [], []])})
        rows = te.compare_reports(base, new)
        out = te.render_comparison(rows, base, new, "sonnet", "old.json")
        self.assertIn("baseline old.json", out)
        self.assertIn("| a1 | alpha | 4/4 | 2/4 | -50% | 4/4 | 2/4 | REGRESSED |", out)
        self.assertIn("exact-match 100% -> 62%", out)      # 5 exact of 8 runs
        self.assertIn("negatives false-fire 0/4 -> 1/4", out)
        self.assertIn("1 REGRESSED", out)

    def test_main_baseline_compares_matching_model_and_writes_json(self):
        # baseline: a1 fired 2/2 on sonnet; new run: a1 never fires
        base_path = os.path.join(self.root, "base.json")
        base_metrics = self._m({"a1": (["alpha"], [["alpha"], ["alpha"]]),
                                "b1": (["beta"], [["beta"], ["beta"]]),
                                "n1": ([], [[], []])})
        with open(base_path, "w") as f:
            json.dump({"metrics": base_metrics,
                       "metrics_by_model": {"sonnet": base_metrics,
                                            "haiku": self._m({})}}, f)

        def fake(argv, cwd, timeout):
            p = argv[-1]
            if "beta" in p:
                return 0, stream(invoked=["beta"], text="SKILLS=beta"), ""
            return 0, stream(text="SKILLS=NONE"), ""
        out_json = os.path.join(self.root, "out.json")
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--repeats", "2", "--baseline", base_path,
                          "--json", out_json])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 1)                      # a1 mismatches
        with open(out_json) as f:
            data = json.load(f)
        comp = data["baseline"]
        self.assertEqual(comp["path"], base_path)
        rows = {r["id"]: r for r in comp["by_model"]["sonnet"]}
        self.assertEqual(rows["a1"]["verdict"], "REGRESSED")
        self.assertEqual(rows["b1"]["verdict"], "same")
        self.assertEqual(rows["n1"]["verdict"], "same")

    def test_main_baseline_missing_file_is_usage_error(self):
        rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                      "--baseline", os.path.join(self.root, "nope.json")])
        self.assertEqual(rc, 2)

    def test_load_baseline_rebuilds_per_case_for_pre_v4_reports(self):
        # a v3 report stores metrics without per_case, plus raw results
        results = [{"id": "a1", "expect": ["alpha"], "fired": ["alpha"],
                    "error": None, "cost_usd": 0.01, "distractors": [],
                    "foreign": [], "available": [], "model": "sonnet"},
                   {"id": "n1", "expect": [], "fired": ["beta"],
                    "error": None, "cost_usd": 0.01, "distractors": [],
                    "foreign": [], "available": [], "model": "sonnet"}]
        old = te.score(results, ["alpha", "beta"])
        del old["per_case"]
        p = os.path.join(self.root, "v3.json")
        with open(p, "w") as f:
            json.dump({"metrics": old, "results": results,
                       "models": ["sonnet"]}, f)
        b = te.load_baseline(p)
        self.assertEqual(b["metrics"]["per_case"]["a1"]["hit"], 1)
        self.assertEqual(b["metrics"]["per_case"]["n1"]["hit"], 0)
        self.assertIn("sonnet", b["metrics_by_model"])

    def test_declared_but_not_invoked_is_counted_separately(self):
        r = {"id": "a1", "expect": ["alpha"], "fired": [], "error": None,
             "cost_usd": 0.01, "distractors": [], "foreign": [],
             "available": [], "declared": ["alpha"]}
        m = te.score([r], ["alpha"])
        self.assertEqual(m["declared_only"], 1)
        self.assertEqual(m["per_case"]["a1"]["declared_only"], 1)
        self.assertEqual(m["per_case"]["a1"]["hit"], 0)     # still a miss
        out = te.render_report([r], m, ["alpha"], "native", "sonnet")
        self.assertIn("declared-not-invoked: 1", out)
        # a genuine miss (declared NONE) is not counted
        r2 = dict(r, declared=[])
        self.assertEqual(te.score([r2], ["alpha"])["declared_only"], 0)

    def test_count_declared_scores_declared_catalog_skill_as_fired(self):
        r = {"id": "a1", "expect": ["alpha"], "fired": [], "error": None,
             "cost_usd": 0.01, "distractors": [], "foreign": [],
             "available": [], "declared": ["alpha", "host-thing"]}
        m = te.score([r], ["alpha", "beta"], count_declared=True)
        self.assertEqual(m["per_case"]["a1"]["hit"], 1)
        self.assertEqual(m["per_case"]["a1"]["exact"], 1)   # host-thing ignored
        self.assertEqual(m["per_skill"]["alpha"]["tp"], 1)
        self.assertTrue(m["count_declared"])
        self.assertEqual(r["fired"], [])                     # input untouched
        out = te.render_report([r], m, ["alpha", "beta"], "native", "sonnet")
        self.assertIn("declared skills counted as fired", out)

    def test_protocol_strict_changes_system_prompt_only(self):
        d = te.native_argv("claude", "sonnet", "task", 0.5)
        s = te.native_argv("claude", "sonnet", "task", 0.5, protocol="strict")
        self.assertEqual(d[:-2], s[:-2])
        self.assertEqual(d[-2], te.PROBE_SYSTEM)
        self.assertTrue(s[-2].startswith(te.PROBE_SYSTEM))
        self.assertIn("invalid answer", s[-2])
        with self.assertRaises(KeyError):
            te.native_argv("claude", "sonnet", "task", 0.5, protocol="lax")

    def test_main_count_declared_and_protocol_recorded_in_json(self):
        seen = []

        def fake(argv, cwd, timeout):
            seen.append(argv)
            p = argv[-1]
            if "alpha" in p:      # declared without a tool call
                return 0, stream(text="SKILLS=alpha"), ""
            if "beta" in p:
                return 0, stream(invoked=["beta"], text="SKILLS=beta"), ""
            return 0, stream(text="SKILLS=NONE"), ""
        out_json = os.path.join(self.root, "out.json")
        orig = te.default_runner
        te.default_runner = fake
        try:
            rc = te.main([self.cases_path, "--skills", self.root, "--quiet",
                          "--protocol", "strict", "--count-declared",
                          "--json", out_json])
        finally:
            te.default_runner = orig
        self.assertEqual(rc, 0)                     # a1 counts via declared
        with open(out_json) as f:
            data = json.load(f)
        self.assertEqual(data["protocol"], "strict")
        self.assertTrue(data["count_declared"])
        self.assertEqual(data["metrics"]["declared_only"], 0)   # merged away
        self.assertTrue(all("invalid answer" in a[-2] for a in seen))

    def test_load_baseline_rejects_reports_without_metrics(self):
        p = os.path.join(self.root, "bad.json")
        with open(p, "w") as f:
            json.dump({"results": []}, f)
        with self.assertRaises(ValueError):
            te.load_baseline(p)


# ------------------------------------------------------------ v4.2 helpers --
import contextlib  # noqa: E402
import io  # noqa: E402
import time  # noqa: E402


class TestV42(Base):
    """v4.2: strict default protocol, low-n verdict, provenance notes on
    --baseline, description digests in reports, offline --audit."""

    def _run(self, argv, fake):
        orig = te.default_runner
        te.default_runner = fake
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = te.main(argv)
        finally:
            te.default_runner = orig
        return rc, buf.getvalue()

    @staticmethod
    def _fake_all_match(argv, cwd, timeout):
        p = argv[-1]
        name = "alpha" if "alpha" in p else ("beta" if "beta" in p else None)
        return 0, stream(invoked=[name] if name else [],
                         text="SKILLS=%s" % (name or "NONE")), ""

    # -- protocol default ---------------------------------------------------
    def test_default_protocol_is_strict_and_default_still_reachable(self):
        seen = []

        def fake(argv, cwd, timeout):
            seen.append(argv)
            return self._fake_all_match(argv, cwd, timeout)
        out = os.path.join(self.root, "o.json")
        rc, text = self._run([self.cases_path, "--skills", self.root, "--quiet",
                              "--json", out], fake)
        self.assertEqual(rc, 0)
        self.assertTrue(all("invalid answer" in a[-2] for a in seen))
        with open(out) as f:
            self.assertEqual(json.load(f)["protocol"], "strict")
        self.assertIn("protocol=strict", text)
        seen.clear()
        rc, text = self._run([self.cases_path, "--skills", self.root, "--quiet",
                              "--protocol", "default"], fake)
        self.assertTrue(all(a[-2] == te.PROBE_SYSTEM for a in seen))
        self.assertIn("protocol=default", text)

    # -- low-n verdict -----------------------------------------------------
    def _m(self, cases):
        results = []
        for cid, (expect, fires) in cases.items():
            for fired in fires:
                results.append({"id": cid, "expect": expect, "fired": fired,
                                "error": None, "cost_usd": 0.01,
                                "distractors": [], "foreign": [],
                                "available": []})
        return te.score(results, ["alpha", "beta"])

    def test_single_run_side_never_regresses_or_improves(self):
        one = self._m({"a1": (["alpha"], [["alpha"]])})            # 1/1
        two_miss = self._m({"a1": (["alpha"], [[], []])})          # 0/2
        self.assertEqual(te.compare_reports(one, two_miss)[0]["verdict"], "low-n")
        self.assertEqual(te.compare_reports(two_miss, one)[0]["verdict"], "low-n")
        half = self._m({"a1": (["alpha"], [["alpha"], []])})       # 1/2
        self.assertEqual(te.compare_reports(one, half)[0]["verdict"], "low-n")
        # identical rates are still 'same' even at n=1 vs n=2
        two_hit = self._m({"a1": (["alpha"], [["alpha"], ["alpha"]])})
        self.assertEqual(te.compare_reports(one, two_hit)[0]["verdict"], "same")
        # equal n=1 keeps the count-gap rule: a single flip is noise?
        zero = self._m({"a1": (["alpha"], [[]])})
        self.assertEqual(te.compare_reports(one, zero)[0]["verdict"], "noise?")
        # unequal n with both sides >= 2 keeps the rate rule
        base = self._m({"a1": (["alpha"], [["alpha"]] * 2)})
        new = self._m({"a1": (["alpha"], [["alpha"], [], []])})
        self.assertEqual(te.compare_reports(base, new)[0]["verdict"], "REGRESSED")

    # -- digests + provenance ----------------------------------------------
    def test_description_digest_is_stable_and_trimmed(self):
        self.assertEqual(te.description_digest("Does x. "), te.description_digest("Does x."))
        self.assertNotEqual(te.description_digest("Does x."), te.description_digest("Does y."))
        self.assertEqual(len(te.description_digest("")), 12)

    def test_report_records_version_and_description_digests(self):
        out = os.path.join(self.root, "o.json")
        rc, _ = self._run([self.cases_path, "--skills", self.root, "--quiet",
                           "--json", out], self._fake_all_match)
        self.assertEqual(rc, 0)
        with open(out) as f:
            data = json.load(f)
        self.assertEqual(data["version"], "4.2")
        self.assertEqual(data["descriptions"], {
            "alpha": te.description_digest("Does alpha. Use when alpha-ish."),
            "beta": te.description_digest("Does beta. Use when beta-ish.")})

    def test_baseline_notes_protocol_mismatch_and_edited_descriptions(self):
        base = os.path.join(self.root, "base.json")
        rc, _ = self._run([self.cases_path, "--skills", self.root, "--quiet",
                           "--protocol", "default", "--json", base],
                          self._fake_all_match)
        self.assertEqual(rc, 0)
        # edit alpha's description on disk, then compare under strict
        with open(os.path.join(self.root, "alpha", "SKILL.md"), "w") as f:
            f.write("---\nname: alpha\ndescription: Does alpha differently.\n---\nbody\n")
        out = os.path.join(self.root, "new.json")
        rc, text = self._run([self.cases_path, "--skills", self.root, "--quiet",
                              "--baseline", base, "--json", out],
                             self._fake_all_match)
        self.assertIn("NOTE: probe protocol differs (baseline=default, this run=strict)", text)
        self.assertIn("descriptions edited since the baseline: alpha", text)
        with open(out) as f:
            cmp_ = json.load(f)["baseline"]
        self.assertTrue(cmp_["protocol_mismatch"])
        self.assertEqual(cmp_["descriptions_changed"], ["alpha"])
        # same protocol, nothing edited: no notes
        rc, text = self._run([self.cases_path, "--skills", self.root, "--quiet",
                              "--baseline", out], self._fake_all_match)
        self.assertNotIn("NOTE: probe protocol", text)
        self.assertNotIn("descriptions edited", text)

    def test_load_baseline_defaults_protocol_for_pre_v42_reports(self):
        p = os.path.join(self.root, "old.json")
        with open(p, "w") as f:
            json.dump({"metrics": te.score([], ["alpha"]), "results": []}, f)
        b = te.load_baseline(p)
        self.assertEqual(b["protocol"], "default")
        self.assertEqual(b["descriptions"], {})

    # -- --also-cases --------------------------------------------------------
    def test_also_cases_merges_and_rejects_duplicate_ids(self):
        extra = os.path.join(self.root, "body.json")
        with open(extra, "w") as f:
            json.dump([{"id": "body-a", "prompt": "alpha task for real",
                        "expect": ["alpha"], "body": {"evidence": ["bundled"]}}], f)
        out = os.path.join(self.root, "o.json")
        rc, _ = self._run([self.cases_path, "--skills", self.root, "--quiet",
                           "--also-cases", extra, "--json", out], self._fake_all_match)
        self.assertEqual(rc, 0)
        with open(out) as f:
            self.assertEqual([r["id"] for r in json.load(f)["results"]],
                             ["a1", "b1", "n1", "body-a"])
        rc, _ = self._run([self.cases_path, "--skills", self.root, "--quiet",
                           "--also-cases", self.cases_path], self._fake_all_match)
        self.assertEqual(rc, 2)

    # -- --audit -------------------------------------------------------------
    def _report(self, name, results, descriptions=None, age=0, **extra):
        rdir = os.path.join(self.root, "reports")
        os.makedirs(rdir, exist_ok=True)
        p = os.path.join(rdir, name)
        data = {"results": results, "mode": "native", "protocol": "strict"}
        if descriptions is not None:
            data["descriptions"] = descriptions
        data.update(extra)
        with open(p, "w") as f:
            json.dump(data, f)
        t = time.time() - age
        os.utime(p, (t, t))
        return rdir

    @staticmethod
    def _res(cid, expect, fired, error=None):
        return {"id": cid, "expect": expect, "fired": fired, "error": error}

    def test_audit_statuses_probed_stale_unverified_never(self):
        make_skill(self.root, "gamma", "Does gamma.")
        make_skill(self.root, "delta", "Does delta.")
        catalog = te.load_catalog([self.root])
        cur = {n: te.description_digest(d) for n, d, _ in catalog}
        rdir = self._report("old.json", [self._res("a1", ["alpha"], ["alpha"]),
                                         self._res("b1", ["beta"], ["beta"]),
                                         self._res("g1", ["gamma"], [])],
                            age=100)                       # pre-4.2: no digests
        self._report("new.json", [self._res("a1", ["alpha"], ["alpha"]),
                                  self._res("b1", ["beta"], [], error="rc=1")],
                     descriptions={"alpha": cur["alpha"], "beta": "deadbeef0000"},
                     age=10)
        self._report("canary.json", [], age=0)             # results empty: never picked
        with open(os.path.join(rdir, "dump.json"), "w") as f:
            json.dump({"canary": [], "exit": 0}, f)       # not a report: skipped
        cases = [{"id": "a1", "prompt": "p", "expect": ["alpha"]},
                 {"id": "b1", "prompt": "p", "expect": ["beta"]},
                 {"id": "g1", "prompt": "p", "expect": ["gamma"]},
                 {"id": "bb", "prompt": "p", "expect": ["beta"], "body": {}}]
        reports = te.load_reports(rdir)
        self.assertEqual([os.path.basename(p) for p, _, _ in reports],
                         ["canary.json", "new.json", "old.json"])
        rows = {r["name"]: r for r in te.audit_skills(catalog, cases, reports)}
        self.assertEqual(rows["alpha"]["status"], "probed")
        self.assertEqual(rows["alpha"]["report"], "new.json")
        # beta's only probe in new.json errored -> falls back to old.json (no digest)
        self.assertEqual(rows["beta"]["status"], "unverified")
        self.assertEqual(rows["beta"]["report"], "old.json")
        self.assertEqual(rows["beta"]["body_cases"], 1)
        self.assertEqual(rows["beta"]["positives"], 1)
        self.assertEqual(rows["gamma"]["status"], "unverified")   # a miss is still a probe
        self.assertEqual(rows["delta"]["status"], "never")
        self.assertTrue(all(r["under_floor"] for r in rows.values()))
        self.assertEqual(te.audit_exit_code(list(rows.values())), 1)
        text = te.render_audit(list(rows.values()), cases, len(reports), rdir)
        self.assertIn("| delta | 0 (UNDER FLOOR) | 0 | — | — | 0 | never |", text)
        self.assertIn("1 body", text)

    def test_audit_stale_when_description_edited_after_probe(self):
        catalog = te.load_catalog([self.root])
        cur = {n: te.description_digest(d) for n, d, _ in catalog}
        rdir = self._report("r.json", [self._res("a1", ["alpha"], ["alpha"])] * 3
                            + [self._res("b1", ["beta"], ["beta"])] * 3,
                            descriptions=dict(cur))
        cases = [{"id": "a%d" % i, "prompt": "p", "expect": ["alpha"]} for i in range(3)] + \
                [{"id": "b%d" % i, "prompt": "p", "expect": ["beta"]} for i in range(3)]
        rows = te.audit_skills(catalog, cases, te.load_reports(rdir))
        self.assertEqual([r["status"] for r in rows], ["probed", "probed"])
        self.assertEqual(rows[0]["probes"], 3)
        self.assertEqual(te.audit_exit_code(rows), 0)
        with open(os.path.join(self.root, "beta", "SKILL.md"), "w") as f:
            f.write("---\nname: beta\ndescription: Does beta, rewritten.\n---\nbody\n")
        rows = te.audit_skills(te.load_catalog([self.root]), cases, te.load_reports(rdir))
        self.assertEqual([r["status"] for r in rows], ["probed", "STALE"])
        self.assertEqual(te.audit_exit_code(rows), 1)

    def test_main_audit_runs_offline_and_writes_json(self):
        calls = []
        rdir = self._report("r.json", [self._res("a1", ["alpha"], ["alpha"]),
                                       self._res("b1", ["beta"], ["beta"])],
                            descriptions={n: te.description_digest(d)
                                          for n, d, _ in self.catalog})
        out = os.path.join(self.root, "audit.json")
        rc, text = self._run([self.cases_path, "--skills", self.root, "--audit", rdir,
                              "--json", out],
                             lambda a, c, t: calls.append(a) or (0, "", ""))
        self.assertEqual(calls, [])                       # no probe ran
        self.assertEqual(rc, 1)                           # 1 positive < floor
        self.assertIn("# probe audit — 2 skills, 3 cases (1 negatives, 0 body)", text)
        self.assertIn("UNDER FLOOR", text)
        with open(out) as f:
            data = json.load(f)
        self.assertEqual(data["exit"], 1)
        self.assertEqual({r["name"]: r["status"] for r in data["audit"]},
                         {"alpha": "probed", "beta": "probed"})
        rc, _ = self._run([self.cases_path, "--skills", self.root, "--audit",
                           os.path.join(self.root, "nope")], lambda a, c, t: (0, "", ""))
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()

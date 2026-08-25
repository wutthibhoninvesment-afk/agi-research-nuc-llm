"""Resumable SWE campaign (swe.campaign): checkpoints, stage skipping, pins, report."""
import json
import os
import re
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.campaign as C
import swe.review as R
from swe.fuzz import WHENCE_ROOT
from swe.mutation import generate, _copy_project
from swe.policy import PolicyLLM, call, say

_INTERP = open(os.path.join(WHENCE_ROOT, "whence/interp.py"), encoding="utf-8").read()
_LINES = _INTERP.splitlines()


def _mutant(pred):
    for m in generate(_INTERP, "whence/interp.py"):
        if pred(m):
            return m
    raise AssertionError("no such mutant")


def _zero_guard():
    return _mutant(lambda m: m.op == "cmp" and "Eq -> NotEq" in m.description
                   and 'r == 0 and (op == "/"' in _LINES[m.lineno - 1])


def _docstring_const():
    """A `const` mutant on a line that is unreachable from any program: the
    parser nesting guard is never hit by tiny programs, so the corpus finds
    no killer."""
    return _mutant(lambda m: m.op == "const" and "MAX_NESTING" in _LINES[m.lineno - 1]
                   or (m.op == "const" and "peak_depth" in _LINES[m.lineno - 1]))


@pytest.fixture
def checkout():
    """A scratch copy of the Whence checkout so generated test files never land in the real one."""
    tmp = tempfile.mkdtemp(prefix="camp-")
    dst = os.path.join(tmp, "whence")
    _copy_project(WHENCE_ROOT, dst)
    yield dst
    shutil.rmtree(tmp, ignore_errors=True)


def _mutation_json(path, mutants_with_status):
    ms = []
    for m, status in mutants_with_status:
        d = m.as_dict()
        d["status"] = status
        ms.append(d)
    killed = sum(1 for _, s in mutants_with_status if s in ("killed", "timeout"))
    data = {"total": len(ms), "killed": killed, "survived": len(ms) - killed,
            "score": round(killed / len(ms), 4), "seconds": 1.0, "mutants": ms}
    with open(path, "w") as f:
        json.dump(data, f)
    return data


def test_manifest_is_created_and_stage_skipping_is_persistent(tmp_path, checkout):
    out = str(tmp_path / "out")
    c = C.Campaign(out, checkout, log=lambda s: None)
    assert os.path.exists(os.path.join(out, "campaign.json"))
    assert not c.done("mutation")
    mj = str(tmp_path / "m.json")
    _mutation_json(mj, [(_zero_guard(), "survived")])
    d = c.stage_mutation(adopt=mj)
    assert d["survived"] == 1 and c.done("mutation")
    assert c.manifest["stages"]["mutation"]["info"]["adopted_from"] == mj
    # a fresh Campaign object on the same out dir sees the stage as done and
    # does NOT need the adopt path any more
    c2 = C.Campaign(out, checkout, log=lambda s: None)
    assert c2.done("mutation") and c2.stage_mutation()["survived"] == 1
    c2.force(["mutation"])
    assert not c2.done("mutation")


def test_mutation_stage_checkpoints_per_mutant_and_resumes(tmp_path, checkout):
    out = str(tmp_path / "out")
    logs = []
    fast = [sys.executable, "-c", "import sys; sys.exit(0)"]      # every mutant 'survives' instantly
    c = C.Campaign(out, checkout, test_cmd=fast, log=logs.append)
    # pre-seed the partial checkpoint with one mutant so the run must resume
    ms = generate(_INTERP, "whence/interp.py")[:3]
    pre = ms[0].as_dict()
    pre["status"] = "killed"
    pre["seconds"] = 9.9
    C._append_jsonl(os.path.join(out, "mutation.partial.jsonl"), pre)
    d = c.stage_mutation(workers=2, limit=3)
    assert d["total"] == 3 and d["killed"] == 1 and d["survived"] == 2
    assert any("resuming: 1 of 3" in s for s in logs)
    st = dict((m["id"], m["status"]) for m in d["mutants"])
    assert st[ms[0].id] == "killed" and st[ms[1].id] == "survived"
    assert len(C._read_jsonl(os.path.join(out, "mutation.partial.jsonl"))) == 3
    assert d["test_cmd"] == fast


def test_recheck_reruns_timeouts_serially_and_records_flips(tmp_path, checkout):
    out = str(tmp_path / "out")
    fast = [sys.executable, "-c", "import sys; sys.exit(1)"]      # the 'suite' now fails -> killed
    c = C.Campaign(out, checkout, test_cmd=fast, log=lambda s: None)
    mj = str(tmp_path / "m.json")
    _mutation_json(mj, [(_zero_guard(), "timeout"), (_docstring_const(), "survived")])
    c.stage_mutation(adopt=mj)
    d = c.stage_recheck(timeout_s=30)
    assert d["recheck"]["timeouts"] == 1 and len(d["recheck"]["flips"]) == 1
    flip = d["recheck"]["flips"][0]
    assert flip["before"] == "timeout" and flip["after"] == "killed"
    assert d["killed"] == 1 and d["survived"] == 1 and d["score"] == 0.5
    assert [m["id"] for m in c.survivors()] == [_docstring_const().id]


def test_corpus_stage_pins_killers_and_verify_confirms_them(tmp_path, checkout):
    out = str(tmp_path / "out")
    c = C.Campaign(out, checkout, log=lambda s: None)
    mj = str(tmp_path / "m.json")
    zg, dc = _zero_guard(), _docstring_const()
    _mutation_json(mj, [(zg, "survived"), (dc, "survived")])
    c.stage_mutation(adopt=mj)
    c.stage_recheck()
    d = c.stage_corpus(seed=1, corpus_n=0, extra_programs=["let a = 7 % 3\nprint(a)\n"],
                       test_file="tests/test_generated_killers_camp.py", include_examples=False)
    assert d["found"] == 1 and d["no_killer"] == 1 and d["programs"] == 1
    assert d["include_examples"] is False
    by = dict((k["mutant"], k) for k in d["killers"])
    assert by[zg.id]["found"] and "%" in by[zg.id]["program"]
    assert not by[dc.id]["found"]
    pinned = os.path.join(checkout, "tests/test_generated_killers_camp.py")
    body = open(pinned).read()
    assert "def test_kill_" in body
    compile(body, pinned, "exec")
    assert not os.path.exists(os.path.join(WHENCE_ROOT, "tests/test_generated_killers_camp.py"))
    v = c.stage_verify()
    assert v["pinned"] == 1 and v["verified"] == 1
    assert v["results"][0]["id"] == zg.id and v["results"][0]["status"] == "killed"
    assert c.no_killer_ids() == [dc.id]
    # idempotent: re-running the stage returns the artifact without re-searching
    assert c.stage_corpus(seed=99, corpus_n=0)["seed"] == 1


def test_live_kill_stage_resumes_from_partial_and_pins_verified_kills(tmp_path, checkout):
    out = str(tmp_path / "out")
    c = C.Campaign(out, checkout, log=lambda s: None)
    mj = str(tmp_path / "m.json")
    zg, dc = _zero_guard(), _docstring_const()
    _mutation_json(mj, [(zg, "survived"), (dc, "survived")])
    c.stage_mutation(adopt=mj)
    c.stage_recheck()
    # corpus finds nothing (no programs at all) -> both are no_killer candidates
    c.stage_corpus(corpus_n=0, test_file="tests/test_generated_killers_camp.py", include_examples=False)
    assert set(c.no_killer_ids()) == {zg.id, dc.id}
    # pretend a previous run already handled dc (equivalent) and died
    C._append_jsonl(os.path.join(out, "live-kill.partial.jsonl"),
                    {"mutant": dc.id, "outcome": "equivalent_claimed", "killed": False,
                     "cost_usd": 0.01, "steps": 3})
    prog = "let a = 7 % 3\nprint(a)\n"
    calls = []

    def make_llm():
        calls.append(1)
        return PolicyLLM([
            lambda obs, st: call("outline", path="whence/interp.py"),
            lambda obs, st: call("read_file", path="whence/interp.py", start=zg.lineno - 3, end=zg.lineno + 3),
            lambda obs, st: call("mutant_diff", source=prog),
            lambda obs, st: say('```json\n' + json.dumps({"verdict": "killed", "program": prog}) + '\n```'),
        ])
    d = c.stage_live_kill(make_llm, n=2, seed=0, max_steps=8,
                          test_file="tests/test_model_killers_camp.py", model="policy")
    assert len(calls) == 1                                  # only zg was attempted
    assert d["attempted"] == 2 and d["killed"] == 1 and d["equivalent_claimed"] == 1
    assert d["verified"] == 1 and d["verify"][0]["status"] == "killed"
    assert d["results"][0]["mutant"] == dc.id or d["results"][1]["mutant"] == dc.id
    pinned = os.path.join(checkout, "tests/test_model_killers_camp.py")
    assert os.path.exists(pinned) and "def test_kill_" in open(pinned).read()
    trace = os.path.join(out, "live-kill", "kill-" + re.sub(r"\W", "_", zg.id) + ".trace.jsonl")
    assert os.path.exists(trace)                 # run_kill tags traces with re.sub(r"\W", "_") (dot included)
    # the region tools were actually used inside the kill task
    hist = C.tool_histogram(trace)
    assert hist == {"outline": 1, "read_file": 1, "mutant_diff": 1}


def test_review_stage_and_report(tmp_path, checkout):
    out = str(tmp_path / "out")
    c = C.Campaign(out, checkout, log=lambda s: None)
    mj = str(tmp_path / "m.json")
    zg = _zero_guard()
    _mutation_json(mj, [(zg, "killed"), (_docstring_const(), "survived")])
    c.stage_mutation(adopt=mj)
    c.stage_recheck()
    c.stage_corpus(corpus_n=0, test_file="tests/test_generated_killers_camp.py")
    c.stage_verify()

    def make_llm():
        return PolicyLLM([
            lambda obs, st: call("outline", path="whence/interp.py"),
            lambda obs, st: call("search", query="def binop", path="whence/interp.py", context=2),
            lambda obs, st: call("oracle_check", source="let a = 7 % 3\nprint(a)\n"),
            lambda obs, st: say('```json\n{"claims": [{"title": "phantom", "program": "print(1)\\n", "oracle": "fast_slow"}]}\n```'),
        ])
    r = c.stage_review(make_llm, focus="binop", max_steps=8, model="policy")
    assert r["claimed"] == 1 and r["confirmed"] == 0
    assert r["tool_histogram"] == {"outline": 1, "search": 1, "oracle_check": 1}
    rep = c.stage_report()
    assert rep["total"] == 2 and rep["baseline"]["score"] == 0.5
    assert rep["corpus"]["no_killer"] == 1 and rep["tests_added"] == 0
    assert rep["projected_score"] == 0.5
    assert rep["review"]["tool_histogram"]["oracle_check"] == 1
    md = open(os.path.join(out, "report.md")).read()
    assert "| projected final score | 0.5 |" in md and "oracle_check" in md
    m = json.load(open(os.path.join(out, "campaign.json")))
    assert all(m["stages"][s]["status"] == "done" for s in ("mutation", "recheck", "corpus", "verify", "review", "report"))


def test_load_programs_json_and_separated(tmp_path):
    j = tmp_path / "p.json"
    j.write_text(json.dumps(["let a = 1\n", 5, "let b = 2\n"]))
    assert C.load_programs(str(j)) == ["let a = 1\n", "let b = 2\n"]
    t = tmp_path / "p.txt"
    t.write_text("let a = 1\n---\nlet b = 2\nprint(b)\n---\n")
    assert C.load_programs(str(t)) == ["let a = 1\n", "let b = 2\nprint(b)\n"]


def test_cli_runs_offline_stages_and_stops(tmp_path, checkout, capsys):
    out = str(tmp_path / "out")
    mj = str(tmp_path / "m.json")
    _mutation_json(mj, [(_zero_guard(), "survived")])
    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps(["let a = 7 % 3\nprint(a)\n"]))
    rc = C.main(["--out", out, "--root", checkout, "--adopt-mutation", mj, "--corpus-n", "0",
                 "--extra-programs", str(extra), "--test-file-corpus", "tests/test_generated_killers_camp.py"])
    assert rc == 0
    o = capsys.readouterr().out
    assert "| projected final score | 1.0 |" in o and "| tests added | 1 |" in o
    rep = json.load(open(os.path.join(out, "report.json")))
    assert rep["corpus"]["found"] == 1 and rep["corpus"]["verified"] == 1
    assert rep["live_kill"]["attempted"] is None and rep["review"]["claimed"] is None


# ---------------------------------------------------------- round 101 stages --

# one test: the division-by-zero case reaches binop's zero guard and nothing exotic
_DIV_ONLY = ("-q", "-p", "no:cacheprovider", "tests/test_interp.py", "-k", "division_by_zero")


def _in_diverge():
    """A mutant inside the `diverge` builtin, which the division test never reaches."""
    from swe.regiontools import outline_source
    rng = [l for l in outline_source(_INTERP) if "b_diverge" in l][0]
    lo, hi = [int(x) for x in rng.split("[")[1].split("]")[0].split("-")]
    return _mutant(lambda m: lo < m.lineno <= hi)
_FAST = "-q -x tests/test_interp.py"


def test_coverage_stage_triages_survivors_and_report_shows_the_split(tmp_path, checkout):
    import swe.coverage as CV
    out = str(tmp_path / "out")
    logs = []
    c = C.Campaign(out, checkout, log=logs.append)
    mj = str(tmp_path / "m.json")
    zg, dv = _zero_guard(), _in_diverge()
    _mutation_json(mj, [(zg, "survived"), (dv, "survived")])
    c.stage_mutation(adopt=mj)
    c.stage_recheck()
    cov = c.stage_coverage(pytest_args=_DIV_ONLY, targeted=False)
    assert os.path.exists(os.path.join(out, "coverage.json"))
    assert cov["_meta"]["returncode"] == 0 and cov["_meta"]["targeted"] is False
    st = c.manifest["stages"]["coverage"]["info"]
    assert st["survived_uncovered"] == 1 and st["survived_covered"] == 1 and st["killed_on_uncovered"] == 0
    assert st["targeted"] is False and st["survived_unknown"] == 0
    assert 0 < st["pct"]["whence/interp.py"] < 50
    assert any("never executed" in s for s in logs)
    hits = cov["whence/interp.py"]
    assert hits.get(zg.lineno) and not hits.get(dv.lineno)
    split = c.coverage_split([zg.id, dv.id, "nope"])
    assert split == {"covered": [zg.id], "uncovered": [dv.id], "unknown": ["nope"]}
    # idempotent: a second call loads the artifact
    assert c.stage_coverage(pytest_args=("--bogus",))["_meta"]["returncode"] == 0
    c.stage_corpus(corpus_n=0, extra_programs=["let a = 7 % 3\nprint(a)\n"],
                   test_file="tests/test_generated_killers_camp.py", include_examples=False)
    c.stage_verify()
    rep = c.stage_report()
    cb = rep["coverage"]
    assert cb["survived_uncovered"] == 1 and cb["corpus_tried_uncovered"] == 1 and cb["corpus_found_uncovered"] == 0
    assert cb["corpus_found_covered"] == 1 and cb["corpus_tried_covered"] == 1 and cb["never_executed_defs"] > 20
    md = open(os.path.join(out, "report.md")).read()
    assert "| coverage | whence/interp.py" in md and "corpus kills 1/1 covered vs 0/1 uncovered" in md
    assert "killed-on-uncovered 0 of 0 traced" in md
    # targeted mode on the same fixtures: the untraced killed pool is 'unknown', survivors are traced
    c.force(["coverage"])
    cov2 = c.stage_coverage(pytest_args=_DIV_ONLY, targeted=True)
    assert cov2["_meta"]["targeted"] is True and sorted(cov2["_interest"]["whence/interp.py"]) == sorted(
        set(range(zg.lineno, zg.end_lineno + 1)) | set(range(dv.lineno, dv.end_lineno + 1)))
    st2 = c.manifest["stages"]["coverage"]["info"]
    assert st2["survived_uncovered"] == 1 and st2["survived_covered"] == 1 and st2["targeted"] is True
    assert "| repair | n/a |" in md


def test_repair_stage_samples_killed_mutants_resumes_and_reports(tmp_path, checkout):
    out = str(tmp_path / "out")
    c = C.Campaign(out, checkout, log=lambda s: None)
    mj = str(tmp_path / "m.json")
    zg, dc = _zero_guard(), _docstring_const()
    ms = []
    for m, status in [(zg, "killed"), (dc, "survived")]:
        d = m.as_dict()
        d["status"] = status
        d["detail"] = "FAILED tests/test_interp.py::test_division_by_zero - assert" if status == "killed" else ""
        ms.append(d)
    with open(mj, "w") as f:
        json.dump({"total": 2, "killed": 1, "survived": 1, "score": 0.5, "seconds": 1.0, "mutants": ms}, f)
    c.stage_mutation(adopt=mj)
    c.stage_recheck()
    # a previous run already repaired zg and died: nothing must be attempted
    C._append_jsonl(os.path.join(out, "repair.partial.jsonl"),
                    {"mutant": zg.id, "op": "cmp", "outcome": "green", "green": True, "exact": False,
                     "localized": True, "cost_usd": 0.2, "steps": 7})
    calls = []
    d = c.stage_repair(lambda: calls.append(1), n=3, seed=0, model="policy",
                       test_args=_FAST, fail_args=_FAST.split())
    assert calls == [] and d["pool"] == 1 and d["sample"] == [zg.id]
    assert d["summary"]["attempted"] == 1 and d["summary"]["green_not_exact"] == 1
    # redo it for real under a policy that reverts the mutation
    c.force(["repair"])
    os.remove(os.path.join(out, "repair.partial.jsonl"))

    def make_llm():
        calls.append(1)

        def s_search(obs, st):
            return call("search", query="r != 0 and", path="whence/interp.py")

        def s_edit(obs, st):
            line = [l for l in obs.splitlines() if "r != 0 and" in l][0]
            old = line.split(": ", 1)[1].strip()
            return call("edit_file", path="whence/interp.py", old=old, new=old.replace("r != 0", "r == 0"))

        def s_done(obs, st):
            return say('```json\n{"root_cause": "guard", "files": ["whence/interp.py"], "summary": "s"}\n```')
        return PolicyLLM([s_search, s_edit, s_done])
    d = c.stage_repair(make_llm, n=3, seed=0, model="policy", max_steps=6,
                       test_args=_FAST, fail_args=_FAST.split())
    assert calls == [1] and d["summary"] == {
        "attempted": 1, "green": 1, "exact": 1, "localized": 1, "cheated": 0, "green_not_exact": 0,
        "cost_usd": d["summary"]["cost_usd"], "steps": d["results"][0]["steps"],
        "by_op": {"cmp": {"attempted": 1, "green": 1, "exact": 1, "localized": 1}}}
    assert d["results"][0]["model"] == "policy" and d["results"][0]["failing_tests"]
    assert c.manifest["stages"]["repair"]["info"]["exact"] == 1
    c.stage_corpus(corpus_n=0, test_file="tests/test_generated_killers_camp.py")
    c.stage_verify()
    rep = c.stage_report()
    assert rep["repair"]["exact"] == 1 and rep["repair"]["model"] == "policy"
    assert rep["coverage"] is None
    md = open(os.path.join(out, "report.md")).read()
    assert "| repair | 1 attempted: 1 green, 1 exact, 1 localized, 0 green-not-exact, 0 cheated" in md
    assert "| coverage | n/a |" in md


def test_manifest_marks_merge_across_processes(tmp_path, checkout):
    out = str(tmp_path / "out")
    a = C.Campaign(out, checkout, log=lambda s: None)
    b = C.Campaign(out, checkout, log=lambda s: None)          # a second driver of the same campaign
    a._mark("mutation", "running")
    b._mark("review", "done", claimed=1)
    a._mark("mutation", "done", total=3)
    m = json.load(open(os.path.join(out, "campaign.json")))
    assert m["stages"]["review"]["status"] == "done" and m["stages"]["review"]["info"] == {"claimed": 1}
    assert m["stages"]["mutation"]["status"] == "done" and m["stages"]["mutation"]["info"] == {"total": 3}
    assert b.done("mutation") and a.done("review")
    b.force(["mutation"])
    assert not a.done("mutation") and a.done("review")

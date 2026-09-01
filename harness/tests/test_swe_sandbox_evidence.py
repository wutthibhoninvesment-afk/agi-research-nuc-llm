"""`swe.sandboxevidence` + `mutation.baseline_check`'s evidence block.

Round 431 (SWE-loop D). The subject is the gate every mutation campaign
passes through, and the class it could not see: a test that reacts to being
COPIED by skipping. Both sides exit 0, so `returncode` says nothing.

Two halves, on purpose:

* toy-project halves (`_project`) that pin the MECHANISM cheaply, and
* a REAL-SUBJECT half at the bottom that reads
  `state/known-sandbox-skips.json` and the junit fixture this round banked
  from the actual sandbox run, so the registry cannot rot into a file that
  parses and acknowledges nothing. Round 419's ledger entry -- "the tools'
  tests are all pointed at TOY projects" -- is the reason that half exists.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, REPO_ROOT)

from swe import sandboxevidence as SE                            # noqa: E402
from swe.mutation import (BaselineEvidenceLost, BaselineNotGreen,  # noqa: E402
                          _existing_junit_path, _looks_like_pytest,
                          baseline_check, mutation_test)

PYTEST_CMD = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]

#: The fixture this round banked out of the real sandbox run.
FIXTURE_XML = os.path.join(REPO_ROOT, "state", "swe", "round-431",
                           "sandbox-skips-fixture.xml")
REAL_REGISTRY = os.path.join(REPO_ROOT, "state", "known-sandbox-skips.json")
REAL_SUITE = "whence-fast-sandbox"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _rec(statuses, skips=None, ok=True, error=None):
    """A `parse_junit`-shaped record without touching a file."""
    return {"ok": ok, "error": error, "path": "<mem>",
            "statuses": dict(statuses), "skips": list(skips or []),
            "details": {}}


def _skip(key, reason, nid=None):
    return {"key": key, "nid": nid or key, "reason": reason}


def _ack(key, reason_pin, **kw):
    e = {"suite": "s", "key": key, "nid": key, "class": "sandbox_only",
         "reason_pin": reason_pin, "kills_mutants": False,
         "acknowledged_round": 431, "why": "because"}
    e.update(kw)
    return e


def _project(root, skip_when_copied=False, count_files=False, red=False):
    """A tiny pytest project.

    `skip_when_copied` reproduces the round-425 shape without needing git:
    the test skips when a file OUTSIDE the tree is absent, which is exactly
    what `_copy_project` produces (the copy's parent is a tempdir).
    """
    os.makedirs(os.path.join(root, "tests"), exist_ok=True)
    with open(os.path.join(root, "mod.py"), "w") as f:
        f.write("def add(a, b):\n    return a + b\n")
    body = ["import os", "import pytest", "import sys",
            "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))",
            "from mod import add", "",
            "HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))", "",
            "def test_adds():",
            "    assert add(1, 2) == %d" % (3 if not red else 4), ""]
    if skip_when_copied:
        body += [
            "def test_needs_the_neighbour():",
            "    p = os.path.join(HERE, '..', 'neighbour.txt')",
            "    if not os.path.exists(p):",
            "        pytest.skip('neighbour is absent')",
            "    assert open(p).read().strip() == 'here'", ""]
    if count_files:
        # NOT an exact listing: pytest creates `__pycache__` in the tree it
        # runs in, so an exact listing fails for a reason that has nothing to
        # do with the report. The property under test is narrower and is the
        # real one -- no artefact of the CHECK appears in the tree the suite
        # is looking at.
        body += [
            "def test_no_report_file_is_dropped_in_the_tree():",
            "    stray = []",
            "    for d, _, fs in os.walk(HERE):",
            "        stray += [os.path.join(d, f) for f in fs if f.endswith('.xml')]",
            "    assert stray == [], stray", ""]
    with open(os.path.join(root, "tests", "test_mod.py"), "w") as f:
        f.write("\n".join(body))
    return str(root)


# --------------------------------------------------------------------------
# `check` -- the four buckets and the verdict
# --------------------------------------------------------------------------

def test_an_unavailable_report_populates_no_bucket_and_decides_nothing():
    """Rule 3. A run that left no junit has NOT shown that nothing was lost,
    and the one thing this must never do is read that silence as green."""
    b = SE.check({"ok": False, "error": "boom"}, suite="s", acks=[], suites={})
    assert b["evidence"] == "unavailable" and b["verdict"] == SE.V_UNAVAILABLE
    assert b["error"] == "boom"
    assert b["unacknowledged"] == [] and b["acknowledged"] == []
    assert b["n_nodes"] is None and b["n_skipped"] is None
    assert SE.is_lost(b) is False
    assert "UNAVAILABLE" in "\n".join(SE.format_block(b))


def test_an_unsigned_skip_is_the_verdict():
    rec = _rec({"t::a": "passed", "t::b": "skipped"},
               [_skip("t::b", "no reason anybody wrote down")])
    b = SE.check(rec, suite="s", acks=[], suites={})
    assert b["verdict"] == SE.V_SKIP_EVAPORATION and SE.is_lost(b)
    assert [r["key"] for r in b["unacknowledged"]] == ["t::b"]
    assert b["n_nodes"] == 2 and b["n_skipped"] == 1
    assert "UNACKNOWLEDGED skip" in "\n".join(SE.format_block(b))


def test_a_signed_skip_with_a_holding_pin_is_not_a_verdict_but_is_still_printed():
    """An acknowledgement that suppresses INVISIBLY reads as coverage. This
    is the same rule `pristine_check` states about its own registry."""
    rec = _rec({"t::b": "skipped"}, [_skip("t::b", "the exact reason")])
    b = SE.check(rec, suite="s", acks=[_ack("t::b", "the exact reason")], suites={})
    assert b["verdict"] == SE.V_OK and not SE.is_lost(b)
    assert [r["key"] for r in b["acknowledged"]] == ["t::b"]
    assert b["acknowledged"][0]["ack_state"] == SE.ACK_HOLDS
    assert "skipped, acknowledged (round 431" in "\n".join(SE.format_block(b))


def test_a_changed_reason_expires_the_pin_and_goes_red_again():
    """The node is signed; the REASON is not. Without this an
    acknowledgement decays into a permanent blanket over a node id."""
    rec = _rec({"t::b": "skipped"}, [_skip("t::b", "a completely different reason")])
    b = SE.check(rec, suite="s", acks=[_ack("t::b", "the exact reason")], suites={})
    assert b["verdict"] == SE.V_SKIP_EVAPORATION and SE.is_lost(b)
    assert [r["key"] for r in b["pin_expired"]] == ["t::b"]
    assert b["acknowledged"] == []
    text = "\n".join(SE.format_block(b))
    assert "PIN EXPIRED" in text
    # Both texts, because the reader's question is "what changed".
    assert "the exact reason" in text and "a completely different reason" in text


def test_an_acknowledgement_matching_nothing_is_reported_dead_and_decides_nothing():
    rec = _rec({"t::a": "passed"}, [])
    b = SE.check(rec, suite="s", acks=[_ack("t::gone", "whatever")], suites={})
    assert b["verdict"] == SE.V_OK
    assert [r["key"] for r in b["dead_acknowledgements"]] == ["t::gone"]
    assert "DEAD acknowledgement" in "\n".join(SE.format_block(b))


def test_a_signed_skip_that_kills_mutants_stays_loud_forever():
    """`kills_mutants: true` is a standing debt against every score the
    engine publishes, not a silenced warning. It is signed, so it does not
    set the verdict -- and it is printed on its own LOUD line every run."""
    rec = _rec({"t::b": "skipped"}, [_skip("t::b", "r")])
    b = SE.check(rec, suite="s", acks=[_ack("t::b", "r", kills_mutants=True)], suites={})
    assert b["verdict"] == SE.V_OK
    assert [r["key"] for r in b["acknowledged_costly"]] == ["t::b"]
    assert b["acknowledged"][0]["ack_state"] == SE.ACK_COSTLY
    text = "\n".join(SE.format_block(b))
    assert "acknowledged but COSTLY" in text and "kills mutants and did not run" in text
    # ... and it is NOT also printed on the quiet line.
    assert "skipped, acknowledged" not in text


def test_an_entry_for_another_suite_does_not_acknowledge_this_one():
    rec = _rec({"t::b": "skipped"}, [_skip("t::b", "r")])
    ack = _ack("t::b", "r", suite="other")
    b = SE.check(rec, suite="s", acks=[ack], suites={})
    assert b["verdict"] == SE.V_SKIP_EVAPORATION
    assert [r["key"] for r in b["unacknowledged"]] == ["t::b"]
    # `suite=None` matches every entry -- permissive for MATCHING only.
    assert SE.check(rec, suite=None, acks=[ack], suites={})["verdict"] == SE.V_OK


# --------------------------------------------------------------------------
# the third hole: silently fewer nodes
# --------------------------------------------------------------------------

def test_fewer_collected_nodes_than_the_floor_is_its_own_verdict():
    """Exit 0, no failure, no skip, fewer tests. Nothing in this repo could
    see this before -- the skip list is empty and so is the failure set."""
    rec = _rec({"t::a": "passed", "t::b": "passed"})
    suites = {"s": {"node_floor": 5}}
    b = SE.check(rec, suite="s", acks=[], suites=suites)
    assert b["verdict"] == SE.V_NODE_LOSS and SE.is_lost(b)
    assert b["node_floor"] == 5 and b["n_nodes"] == 2
    assert "COLLECTED 2 NODE(S), FLOOR IS 5" in "\n".join(SE.format_block(b))


def test_node_loss_outranks_an_unsigned_skip():
    """Precedence, and the reason for it: a run that collected fewer tests
    has lost evidence it cannot even NAME, and its skip list is not
    trustworthy either."""
    rec = _rec({"t::b": "skipped"}, [_skip("t::b", "r")])
    b = SE.check(rec, suite="s", acks=[], suites={"s": {"node_floor": 9}})
    assert b["verdict"] == SE.V_NODE_LOSS
    assert b["unacknowledged"]          # still reported, just outranked


def test_growing_the_suite_never_trips_the_floor():
    rec = _rec({"t::%d" % i: "passed" for i in range(20)})
    b = SE.check(rec, suite="s", acks=[], suites={"s": {"node_floor": 5}})
    assert b["verdict"] == SE.V_OK


def test_a_floor_is_only_consulted_when_the_caller_names_a_suite():
    rec = _rec({"t::a": "passed"})
    b = SE.check(rec, suite=None, acks=[], suites={"s": {"node_floor": 5}})
    assert b["node_floor"] is None and b["verdict"] == SE.V_OK


# --------------------------------------------------------------------------
# the registry file itself
# --------------------------------------------------------------------------

def test_a_missing_or_corrupt_registry_acknowledges_nothing(tmp_path):
    """Fail-loud direction. The worst a broken registry may do is make a
    known skip go red; the opposite default would let `rm` silence this."""
    assert SE.load_registry(str(tmp_path / "nope.json")) == ({}, [])
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert SE.load_registry(str(bad)) == ({}, [])
    lst = tmp_path / "list.json"
    lst.write_text("[1, 2]", encoding="utf-8")
    assert SE.load_registry(str(lst)) == ({}, [])


def test_entries_without_a_suite_or_key_are_dropped(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"suites": {"s": {"node_floor": 1}}, "acknowledged": [
        {"suite": "s", "key": "t::a", "reason_pin": "r"},
        {"suite": "s"}, {"key": "t::b"}, "not a dict"]}), encoding="utf-8")
    suites, acks = SE.load_registry(str(p))
    assert suites == {"s": {"node_floor": 1}}
    assert [a["key"] for a in acks] == ["t::a"]


# --------------------------------------------------------------------------
# `baseline_check` -- the same run, one extra flag
# --------------------------------------------------------------------------

def test_baseline_check_keeps_its_four_original_keys(tmp_path):
    b = baseline_check(_project(tmp_path), PYTEST_CMD, timeout_s=120.0)
    for k in ("returncode", "timed_out", "seconds", "tail"):
        assert k in b
    assert b["returncode"] == 0 and b["timed_out"] is False


def test_baseline_check_now_names_the_nodes_it_ran(tmp_path):
    b = baseline_check(_project(tmp_path), PYTEST_CMD, timeout_s=120.0)
    assert b["junit_ok"] is True
    assert b["n_nodes"] == 1
    assert b["evidence_verdict"] == SE.V_OK


def test_baseline_check_sees_the_skip_the_exit_code_cannot(tmp_path):
    """THE round-425 class, reproduced end to end without git: a test that
    skips because a file outside the subtree is absent. The copy's parent is
    a tempdir, so it is absent there and only there."""
    root = _project(tmp_path / "proj", skip_when_copied=True)
    with open(os.path.join(tmp_path, "neighbour.txt"), "w") as f:
        f.write("here\n")
    # In place, the neighbour exists and the test really runs.
    p = subprocess.run(PYTEST_CMD + ["-rs"], cwd=root, capture_output=True, text=True)
    assert p.returncode == 0 and "skipped" not in p.stdout

    b = baseline_check(root, PYTEST_CMD, timeout_s=120.0, suite="s",
                       registry_path=str(tmp_path / "no-registry.json"))
    assert b["returncode"] == 0                      # the gate is GREEN ...
    assert b["evidence_verdict"] == SE.V_SKIP_EVAPORATION    # ... and wrong
    assert [r["nid"] for r in b["skips"]["unacknowledged"]] \
        == ["tests/test_mod.py::test_needs_the_neighbour"]
    assert b["skips"]["unacknowledged"][0]["reason"] == "neighbour is absent"


def test_a_registry_entry_turns_that_same_run_green(tmp_path):
    root = _project(tmp_path / "proj", skip_when_copied=True)
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({"suites": {}, "acknowledged": [{
        "suite": "s", "key": "tests.test_mod::test_needs_the_neighbour",
        "reason_pin": "neighbour is absent", "kills_mutants": False,
        "acknowledged_round": 431}]}), encoding="utf-8")
    b = baseline_check(root, PYTEST_CMD, timeout_s=120.0, suite="s",
                       registry_path=str(reg))
    assert b["evidence_verdict"] == SE.V_OK
    assert [r["key"] for r in b["skips"]["acknowledged"]] \
        == ["tests.test_mod::test_needs_the_neighbour"]


def test_the_junit_report_is_written_outside_the_copied_tree(tmp_path):
    """Not a style point. A report inside the copy is one more entry for
    every test that walks the subtree, and this module's whole job is to
    hand the suite a tree that behaves like the original."""
    root = _project(tmp_path, count_files=True)
    with_junit = baseline_check(root, PYTEST_CMD, timeout_s=120.0)
    without = baseline_check(root, PYTEST_CMD, timeout_s=120.0, junit=False)
    assert with_junit["returncode"] == 0 == without["returncode"]
    assert with_junit["n_nodes"] == 2


def test_a_non_pytest_command_gets_no_flag_and_no_verdict(tmp_path):
    root = _project(tmp_path)
    cmd = [sys.executable, "-c", "import sys; sys.exit(0)"]
    b = baseline_check(root, cmd, timeout_s=120.0)
    assert b["returncode"] == 0
    assert b["junit_ok"] is False
    assert b["evidence_verdict"] == SE.V_UNAVAILABLE
    assert "not a pytest invocation" in b["skips"]["error"]


def test_junit_false_asks_for_nothing_and_says_so(tmp_path):
    b = baseline_check(_project(tmp_path), PYTEST_CMD, timeout_s=120.0, junit=False)
    assert b["junit_ok"] is False
    assert b["skips"]["error"] == "junit not requested"
    assert b["evidence_verdict"] == SE.V_UNAVAILABLE


def test_a_caller_supplied_junitxml_is_not_clobbered(tmp_path):
    """Appending a second `--junitxml` would silently win (pytest takes the
    last) and write the caller's report nowhere."""
    root = _project(tmp_path / "proj")
    theirs = tmp_path / "theirs.xml"
    b = baseline_check(root, PYTEST_CMD + ["--junitxml=%s" % theirs], timeout_s=120.0)
    assert theirs.exists() and b["junit_ok"] is True and b["n_nodes"] == 1


def test_looks_like_pytest_and_existing_junit_path_are_conservative():
    assert _looks_like_pytest([sys.executable, "-m", "pytest", "-q"])
    assert _looks_like_pytest(["/usr/bin/pytest", "-q"])
    assert not _looks_like_pytest([sys.executable, "-m", "unittest"])
    assert not _looks_like_pytest([])
    assert _existing_junit_path(["-q", "--junitxml=/tmp/a.xml"]) == "/tmp/a.xml"
    assert _existing_junit_path(["-q", "--junitxml", "/tmp/b.xml"]) == "/tmp/b.xml"
    assert _existing_junit_path(["-q"]) is None


# --------------------------------------------------------------------------
# `mutation_test` -- report by default, refuse on request
# --------------------------------------------------------------------------

def test_mutation_test_runs_by_default_even_when_evidence_was_lost(tmp_path):
    """The default is REPORT, not refuse, and that is a deliberate choice:
    a gate whose false-positive cost is "no campaign runs at all" needs the
    registry populated in front of it. This engine has been stopped at the
    door three times."""
    root = _project(tmp_path / "proj", skip_when_copied=True)
    rep = mutation_test(root, ["mod.py"], PYTEST_CMD, workers=2, limit=2,
                        registry_path=str(tmp_path / "none.json"), suite="s")
    assert rep.mutants           # it ran


def test_require_evidence_refuses_a_green_baseline_that_did_not_run(tmp_path):
    root = _project(tmp_path / "proj", skip_when_copied=True)
    with pytest.raises(BaselineEvidenceLost) as e:
        mutation_test(root, ["mod.py"], PYTEST_CMD, workers=2, limit=2,
                      require_evidence=True, suite="s",
                      registry_path=str(tmp_path / "none.json"))
    assert e.value.verdict == SE.V_SKIP_EVAPORATION
    assert "test_needs_the_neighbour" in str(e.value)


def test_a_red_baseline_is_still_reported_as_red_not_as_lost_evidence(tmp_path):
    """Order matters. `BaselineNotGreen` means the suite SPOKE and said no;
    `BaselineEvidenceLost` means part of it never spoke. A red tree that
    also skips must raise the first."""
    root = _project(tmp_path / "proj", skip_when_copied=True, red=True)
    with pytest.raises(BaselineNotGreen):
        mutation_test(root, ["mod.py"], PYTEST_CMD, workers=2, limit=2,
                      require_evidence=True, suite="s",
                      registry_path=str(tmp_path / "none.json"))


# --------------------------------------------------------------------------
# the REAL subject: this repo's own registry and its own banked report
# --------------------------------------------------------------------------

def test_the_real_registry_parses_and_every_entry_is_complete():
    suites, acks = SE.load_registry(REAL_REGISTRY)
    assert REAL_SUITE in suites and isinstance(suites[REAL_SUITE]["node_floor"], int)
    assert acks, "the registry acknowledges nothing -- see the round-431 seed"
    for e in acks:
        for field in ("suite", "key", "nid", "class", "reason_pin",
                      "kills_mutants", "acknowledged_round", "why"):
            assert field in e, (e.get("key"), field)
        assert e["class"] in ("sandbox_only", "both", "unknown")
        assert len(e["why"]) > 40, e["key"]


def test_the_real_registry_signs_every_skip_the_real_sandbox_run_produced():
    """The banked junit is the round-431 sandbox run, trimmed to its skips.
    If somebody edits a `reason_pin`, or a new skip appears in that run and
    nobody signs it, this goes red -- which is the whole point of pinning
    the reason rather than the node id alone."""
    rec = SE.parse_junit(FIXTURE_XML)
    assert rec["ok"], rec["error"]
    _, acks = SE.load_registry(REAL_REGISTRY)
    b = SE.check(rec, suite=REAL_SUITE, acks=acks, suites={})
    assert b["unacknowledged"] == [], [r["nid"] for r in b["unacknowledged"]]
    assert b["pin_expired"] == [], [r["nid"] for r in b["pin_expired"]]
    assert b["dead_acknowledgements"] == []
    assert b["verdict"] == SE.V_OK
    assert b["n_skipped"] == 4


def test_the_round_425_instance_is_signed_as_costing_nothing_and_says_why():
    """`kills_mutants: false` is a measured claim, not a shrug: round 431
    ran 60 mutants against that node alone in a git worktree (where it does
    NOT skip) and killed none. If a later round flips it to `true` the entry
    starts printing loudly on every campaign, which is the correct
    behaviour and is what `test_a_signed_skip_that_kills_mutants_stays_loud
    _forever` pins."""
    _, acks = SE.load_registry(REAL_REGISTRY)
    e = [a for a in acks if a["nid"].endswith(
        "test_v37.py::test_the_host_is_byte_unchanged_by_this_decision")]
    assert len(e) == 1
    e = e[0]
    assert e["class"] == "sandbox_only" and e["kills_mutants"] is False
    assert "0 covered lines in `whence/interp.py`" in e["why"] \
        or "0 covered lines" in e["why"]
    assert "60" in e["why"]


def test_the_banked_differential_still_says_what_this_round_reported():
    """The measurement itself, kept where a later round can re-read it
    rather than re-quote it."""
    with open(os.path.join(REPO_ROOT, "state", "swe", "round-431",
                           "live-vs-sandbox-diff.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    assert d["n_live"] == d["n_sandbox"] == 2157
    assert d["vanished"] == [] and d["appeared"] == []
    assert len(d["live_skips"]) == 3 and len(d["sandbox_skips"]) == 4
    assert len(d["skipped_both"]) == 3
    evap = [c for c in d["changed"] if c["live"] == "passed" and c["sandbox"] == "skipped"]
    broke = [c for c in d["changed"] if c["live"] == "passed" and c["sandbox"] == "failed"]
    assert len(evap) == 1 and len(broke) == 17
    assert evap[0]["key"].endswith("test_the_host_is_byte_unchanged_by_this_decision")


def test_the_kill_experiment_is_banked_and_is_not_vacuous():
    """0/60 only means something if the test RAN in that tree. It did: the
    unmutated worktree baseline exits 0."""
    with open(os.path.join(REPO_ROOT, "state", "swe", "round-431",
                           "evaporating-test-kills-nothing.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    assert d["baseline"]["rc"] == 0, "the node did not even run unmutated"
    assert d["n"] == 60 and d["killed"] == 0
    assert {m["file"] for m in d["trials"]} == {"whence/values.py", "whence/parser.py"}

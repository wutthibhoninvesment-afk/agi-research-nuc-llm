"""Round 481 (harness A) — tests for `harness/viapin.py`.

Two halves, the same split `test_wiring_audit.py` uses.

The UNIT half builds a throwaway git repo per test, one rule each, and every
rule exists because a pin in the REAL registry got it wrong first:

  * `nuc/constant_audit.py` was pinned at `nuc/run_checks_fast.sh:66` and the
    invocation is at 146 — the line moved (round 442).
  * `languages/whence/orderhint.py` was pinned at `tests/test_v46.py:41` by
    the round that wrote it; line 41 is `sys.path.insert`, the import is 43 —
    the pin was never right (round 480).
  * four entries are pinned at `harness/tests/test_swe_proc.py:-` for an edge
    the graph has not drawn at any commit the registry has lived through —
    the ANALYSER changed (round 415, in the registry's own birth commit).

The LIVE half is the gate: `test_this_registry_makes_no_false_via_claim` is
what turns a shifted line into a red test in the SAME round that shifts it,
which is what round 475's next-step 4 asked for. Round 475 moved eight pins
with a 25-line insertion into `run_driver.sh` and found out from the tier a
round later.
"""
import json
import os
import subprocess
import sys

import pytest

_HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HARNESS not in sys.path:
    sys.path.insert(0, _HARNESS)

import viapin as V                                              # noqa: E402
import wiring_audit as W                                        # noqa: E402

REPO = os.path.dirname(_HARNESS)
MAIN = '\nif __name__ == "__main__":\n    pass\n'


def make_repo(tmp_path, files, entry_points):
    root = str(tmp_path)
    for rel, body in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    reg = {"vendored_prefixes": [], "frozen_prefixes": [],
           "entry_points": entry_points}
    os.makedirs(os.path.join(root, "harness"), exist_ok=True)
    with open(os.path.join(root, "harness", "wiring-registry.json"), "w",
              encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def verdicts(root):
    res = V.audit(root)
    return {r["key"]: r["verdict"] for r in res["rows"]}, res


# --------------------------------------------------------------------------
# the six verdicts
# --------------------------------------------------------------------------

class TestClassify:

    def test_a_pin_on_the_invoking_line_holds(self, tmp_path):
        root = make_repo(
            tmp_path,
            {"run_driver.sh": '# a comment\nbash "$WS/tool.sh"\n',
             "tool.sh": "echo hi\n"},
            {"tool.sh": {"status": "wired", "via": "run_driver.sh:2",
                         "via_kind": "path"}})
        v, res = verdicts(root)
        assert v["tool.sh"] == "held"
        assert res["errors"] == []

    def test_a_pin_one_line_off_is_drifted_and_names_the_real_line(
            self, tmp_path):
        """The `nuc/constant_audit.py` shape: the line moved under the pin."""
        root = make_repo(
            tmp_path,
            {"run_driver.sh": '# a comment\n# another\nbash "$WS/tool.sh"\n',
             "tool.sh": "echo hi\n"},
            {"tool.sh": {"status": "wired", "via": "run_driver.sh:2",
                         "via_kind": "path"}})
        v, res = verdicts(root)
        assert v["tool.sh"] == "drifted"
        assert res["rows"][0]["suggest"] == "run_driver.sh:3"
        assert len(res["errors"]) == 1

    def test_a_pin_into_a_file_that_does_not_reach_it_is_lost(self, tmp_path):
        """The `harness/tests/test_swe_proc.py:-` shape. The entry point is
        still reachable — from somewhere else — so `wiring_audit` stays green
        and only this check can see the false claim."""
        root = make_repo(
            tmp_path,
            {"run_driver.sh": 'bash "$WS/tool.sh"\n',
             "tool.sh": "echo hi\n", "other.sh": "echo nothing\n"},
            {"tool.sh": {"status": "wired", "via": "other.sh:-",
                         "via_kind": "dir"},
             "other.sh": {"status": "unwired", "owner": "t", "reason": "t"},
             "run_driver.sh": {"status": "wired", "via": "root",
                               "via_kind": "root"}})
        v, res = verdicts(root)
        assert v["tool.sh"] == "lost"
        assert len(res["errors"]) == 1                  # a lost pin IS an error
        assert W.audit(root)["findings"] == []          # the other check is green

    def test_a_NUMERIC_pin_into_a_file_that_does_not_reach_it_is_lost_too(
            self, tmp_path):
        """Found by mutation, not by design. Every other `lost` case here
        pins `<file>:-`, so flipping the numeric branch's `lost` to `held`
        left all twenty tests green — the class exists (a round can type a
        line number into a file that does not reach the entry point at all)
        and nothing exercised it."""
        root = make_repo(
            tmp_path,
            {"run_driver.sh": 'bash "$WS/tool.sh"\n',
             "tool.sh": "echo hi\n", "other.sh": "echo nothing\n"},
            {"tool.sh": {"status": "wired", "via": "other.sh:1",
                         "via_kind": "path"}})
        v, res = verdicts(root)
        assert v["tool.sh"] == "lost"
        assert len(res["errors"]) == 1

    def test_a_lost_pin_suggests_the_real_source_and_says_it_is_a_different_file(
            self, tmp_path):
        root = make_repo(
            tmp_path,
            {"run_driver.sh": 'bash "$WS/tool.sh"\n',
             "tool.sh": "echo hi\n", "other.sh": "echo nothing\n"},
            {"tool.sh": {"status": "wired", "via": "other.sh:-",
                         "via_kind": "dir"}})
        row = [r for r in V.audit(root)["rows"] if r["key"] == "tool.sh"][0]
        assert row["suggest"].startswith("run_driver.sh:1")
        assert "adjudicate" in row["suggest"]

    def test_a_dash_pin_whose_line_is_derivable_is_unpinned_not_an_error(
            self, tmp_path):
        root = make_repo(
            tmp_path,
            {"run_driver.sh": '# c\nbash "$WS/tool.sh"\n', "tool.sh": "echo\n"},
            {"tool.sh": {"status": "wired", "via": "run_driver.sh:-",
                         "via_kind": "path"}})
        v, res = verdicts(root)
        assert v["tool.sh"] == "unpinned"
        assert res["errors"] == []
        assert res["rows"][0]["suggest"] == "run_driver.sh:2"

    def test_a_pin_naming_a_path_that_is_not_a_node_is_absent(self, tmp_path):
        root = make_repo(
            tmp_path,
            {"run_driver.sh": 'bash "$WS/tool.sh"\n', "tool.sh": "echo\n"},
            {"tool.sh": {"status": "wired", "via": "gone.sh:4",
                         "via_kind": "path"}})
        v, res = verdicts(root)
        assert v["tool.sh"] == "absent"
        assert len(res["errors"]) == 1

    def test_an_entry_with_no_via_is_none_and_never_an_error(self, tmp_path):
        """Every `manual` entry in the real registry is this shape: 23 of
        133. A checker that demanded a pin from them would be demanding a
        line number for a file nothing runs."""
        root = make_repo(
            tmp_path,
            {"run_driver.sh": 'echo hi\n', "tool.py": "x = 1\n" + MAIN},
            {"tool.py": {"status": "manual", "owner": "x", "reason": "y"}})
        v, res = verdicts(root)
        assert v["tool.py"] == "none"
        assert res["errors"] == []
        assert res["n_pins"] == 0

    def test_the_root_is_not_a_pin(self, tmp_path):
        root = make_repo(
            tmp_path,
            {"run_driver.sh": 'echo hi\n'},
            {"run_driver.sh": {"status": "wired", "via": "root",
                               "via_kind": "root"}})
        v, res = verdicts(root)
        assert v["run_driver.sh"] == "root"
        assert res["n_pins"] == 0


# --------------------------------------------------------------------------
# the import pin — the case the analyser could not see until round 481
# --------------------------------------------------------------------------

def test_an_import_pin_can_hold(tmp_path):
    """Before round 481 this test could not pass at all.

    `references()` recorded every `import` edge at line 0, so a pin naming
    the real import line was scored DRIFTED and a pin saying `:-` was scored
    HELD-ish. `nuc/summary_fossil.py -> nuc/tests/test_summary_fossil.py:20`
    was a correct pin its contemporaries called false — the instrument's own
    defect, reported as the subject's.
    """
    root = make_repo(
        tmp_path,
        {"run_driver.sh": 'python3 -m pytest -q tests/\n',
         "tests/test_t.py": "import os\nimport sys\n\nimport tool\n",
         "tool.py": "x = 1\n" + MAIN},
        {"tool.py": {"status": "wired", "via": "tests/test_t.py:4",
                     "via_kind": "import"},
         "run_driver.sh": {"status": "wired", "via": "root",
                           "via_kind": "root"}})
    v, _ = verdicts(root)
    assert v["tool.py"] == "held"


def test_a_join_pin_and_a_bare_string_pin_carry_their_own_lines(tmp_path):
    """The other two passes round 481 threaded a lineno through."""
    root = make_repo(
        tmp_path,
        {"run_driver.sh": 'python3 driver.py\n',
         "driver.py": ('import os\nimport subprocess\n\n'
                       'A = "helper.sh"\n'
                       'B = os.path.join("pkg", "mod.py")\n' + MAIN),
         "helper.sh": "echo\n", "pkg/mod.py": "x = 1\n"},
        {})
    idx = W.Index(W.tracked_files(root))
    edges, _ = W.references(root, "driver.py", idx)
    assert edges["helper.sh"][0] == 4
    assert edges["pkg/mod.py"][0] == 5


# --------------------------------------------------------------------------
# fix
# --------------------------------------------------------------------------

class TestFix:

    def _drifted_repo(self, tmp_path):
        """`tool.sh`'s pin is two lines stale; `other.sh`'s names no line at
        all. Both files ARE invoked by the driver, so `wiring_audit` is green
        on this repo and only the pins are wrong — which is the situation in
        the real registry and the reason this check had to be built."""
        return make_repo(
            tmp_path,
            {"run_driver.sh": ('# c\n# c\nbash "$WS/tool.sh"\n'
                               'bash "$WS/other.sh"\n'),
             "tool.sh": "echo\n", "other.sh": "echo\n"},
            {"tool.sh": {"status": "wired", "via": "run_driver.sh:1",
                         "via_kind": "path"},
             "other.sh": {"status": "wired", "via": "run_driver.sh:-",
                          "via_kind": "path"}})

    def test_a_dry_run_changes_nothing_on_disk(self, tmp_path):
        root = self._drifted_repo(tmp_path)
        before = open(os.path.join(root, W.REGISTRY_NAME)).read()
        changes = V.fix(root, write=False)
        assert [c[0] for c in changes] == ["tool.sh"]
        assert open(os.path.join(root, W.REGISTRY_NAME)).read() == before

    def test_write_repairs_the_drifted_pin_and_the_audit_goes_green(
            self, tmp_path):
        root = self._drifted_repo(tmp_path)
        V.fix(root, write=True)
        reg = json.load(open(os.path.join(root, W.REGISTRY_NAME)))
        assert reg["entry_points"]["tool.sh"]["via"] == "run_driver.sh:3"
        assert V.audit(root)["errors"] == []

    def test_fix_leaves_unpinned_alone_unless_fill_is_asked_for(self, tmp_path):
        root = self._drifted_repo(tmp_path)
        V.fix(root, write=True)
        reg = json.load(open(os.path.join(root, W.REGISTRY_NAME)))
        assert reg["entry_points"]["other.sh"]["via"] == "run_driver.sh:-"
        V.fix(root, write=True, fill=True)
        reg = json.load(open(os.path.join(root, W.REGISTRY_NAME)))
        assert reg["entry_points"]["other.sh"]["via"] == "run_driver.sh:4"

    def test_fix_never_repoints_a_lost_pin_at_a_different_file(self, tmp_path):
        """The one thing `fix` must not do. A `lost` pin's only repair is to
        name a DIFFERENT source file, which is an editorial claim about why
        an entry point is wired — round 481 adjudicated the repo's four by
        hand and wrote the reason down. A tool that did it silently would
        manufacture provenance."""
        root = make_repo(
            tmp_path,
            {"run_driver.sh": 'bash "$WS/tool.sh"\n',
             "tool.sh": "echo\n", "other.sh": "echo\n"},
            {"tool.sh": {"status": "wired", "via": "other.sh:-",
                         "via_kind": "dir"}})
        V.fix(root, write=True, fill=True)
        reg = json.load(open(os.path.join(root, W.REGISTRY_NAME)))
        assert reg["entry_points"]["tool.sh"]["via"] == "other.sh:-"
        assert V.audit(root)["counts"]["lost"] == 1

    def test_a_write_with_nothing_to_change_does_not_touch_the_file(
            self, tmp_path):
        root = make_repo(
            tmp_path,
            {"run_driver.sh": 'bash "$WS/tool.sh"\n', "tool.sh": "echo\n"},
            {"tool.sh": {"status": "wired", "via": "run_driver.sh:1",
                         "via_kind": "path"}})
        p = os.path.join(root, W.REGISTRY_NAME)
        before = os.stat(p).st_mtime_ns, open(p).read()
        assert V.fix(root, write=True) == []
        assert (os.stat(p).st_mtime_ns, open(p).read()) == before


# --------------------------------------------------------------------------
# the real registry
# --------------------------------------------------------------------------

class TestThisTree:

    def test_the_dump_round_trips_the_real_registry_byte_for_byte(self, tmp_path):
        """`indent=2, ensure_ascii=False`. The default `ensure_ascii=True`
        rewrites every em dash in every `reason` string, so a two-pin repair
        would land as a 90-line diff — this repo's own recorded pitfall about
        JSON registries.

        Written through `_dump_registry`, not through a second call to
        `json.dumps` with the parameters copied out: a test that re-states
        the writer's arguments passes when the writer changes them.
        """
        p = os.path.join(REPO, W.REGISTRY_NAME)
        raw = open(p, encoding="utf-8").read()
        out = str(tmp_path / "copy.json")
        V._dump_registry(out, json.loads(raw))
        assert open(out, encoding="utf-8").read() == raw

    def test_this_registry_makes_no_false_via_claim(self):
        """THE GATE. A round that shifts a pinned line goes red here, in its
        own health check, instead of in the next round's.

        `drifted`/`lost`/`absent` are claims the tree contradicts.
        `unpinned` is not in the set: a `<file>:-` pin declines to name a
        line and so cannot be wrong about one.
        """
        res = V.audit(REPO)
        assert res["errors"] == [], (
            V.summary_line(res) + "\n"
            + "\n".join("%s %s pinned=%s -> %s"
                        % (r["verdict"].upper(), r["key"], r["via"],
                           r["suggest"]) for r in res["errors"])
            + "\nrepair the mechanical ones with: "
              "python3 harness/viapin.py fix --write")

    def test_viapin_is_declared_in_the_registry_it_checks(self):
        reg = json.load(open(os.path.join(REPO, W.REGISTRY_NAME)))
        entry = reg["entry_points"]["harness/viapin.py"]
        assert entry["status"] == "wired"

    def test_the_cli_exits_nonzero_on_a_false_claim(self, tmp_path):
        root = make_repo(
            tmp_path,
            {"run_driver.sh": '# c\nbash "$WS/tool.sh"\n', "tool.sh": "echo\n"},
            {"tool.sh": {"status": "wired", "via": "run_driver.sh:1",
                         "via_kind": "path"}})
        r = subprocess.run([sys.executable, os.path.join(REPO, "harness",
                                                         "viapin.py"),
                            "--root", root, "audit"],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 1, r.stdout
        assert "DRIFTED" in r.stdout
        assert "fix --write" in r.stdout

    def test_the_summary_line_reports_every_class(self):
        res = V.audit(REPO)
        line = V.summary_line(res)
        for word in ("held", "drifted", "lost", "absent", "unpinned"):
            assert word in line
        assert str(res["n_pins"]) in line

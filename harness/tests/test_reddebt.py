"""Falsifiers for harness/reddebt.py (round 493, harness A).

Every gate below is FALSIFIED, not asserted: each test builds the input that
would make the module wrong and requires it to say so. The three that matter
most are the ones guarding claims a naive reader gets backwards —

  * a log with no `FAILED` line is not a green run (round 349's defect),
  * an empty note means CLEAN and must never be what a broken evidence base
    produces (the note has to shout instead),
  * `new` vs `recurrent` must not be a restatement of "the episode is
    recent" (this module's own first classifier was exactly that, and
    returned `0 standing, 14 flapping` on the live logs).
"""

import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
REPO = os.path.dirname(HARNESS)
if HARNESS not in sys.path:
    sys.path.insert(0, HARNESS)

import reddebt as RD          # noqa: E402
import redattrib as RA        # noqa: E402


# --------------------------------------------------------------- fixtures --

PASSED_TAIL = "\n1 failed, 9 passed in 12.34s\n"
CLEAN_TAIL = "\n10 passed in 12.34s\n"


def _log(dirpath, prefix, rnd, failed=(), tail=PASSED_TAIL):
    """Write one per-round health log in the grammar the parser reads."""
    body = "".join("FAILED %s\n" % n for n in failed)
    with open(os.path.join(dirpath, "%s_%d.log" % (prefix, rnd)), "w") as fh:
        fh.write("=== short test summary info ===\n" + body + tail)


def _tree(tmp_path, rounds, tracks=None, prefix="health_round"):
    """A fake repo root: logs/<prefix>_<N>.log plus a driver.log of tracks.

    `rounds` is {round: (failed_nodes, tail)}; a tail without a pytest count
    line is how a killed check is spelled.
    """
    root = str(tmp_path)
    logs = os.path.join(root, "logs")
    os.makedirs(logs, exist_ok=True)
    for rnd, (failed, tail) in sorted(rounds.items()):
        _log(logs, prefix, rnd, failed, tail)
    with open(os.path.join(logs, "driver.log"), "w") as fh:
        for rnd in sorted(rounds):
            trk = (tracks or {}).get(rnd, "harness(A)")
            fh.write("[t] round %d track=%s start (driver_version=x) pid=1\n"
                     % (rnd, trk))
    return root


NODE = "harness/tests/test_a.py::test_one"
OTHER = "harness/tests/test_a.py::test_two"


# ------------------------------------------- a killed check is not a green --

def test_a_log_with_no_count_line_is_no_verdict_not_green(tmp_path):
    """Round 349's defect, at node level.

    Round 1 is red. Round 2's log has no `FAILED` line AND no pytest count
    line — the shape a check killed at its budget writes. A parser that reads
    "no FAILED lines" as green closes the episode here and the debt vanishes
    on precisely the round the tree was least healthy.
    """
    root = _tree(tmp_path, {
        1: ([NODE], PASSED_TAIL),
        2: ([], "killed by SIGKILL, no count line here\n"),
    })
    rows = RD.check_rounds(root)["health_round"]
    assert rows[1][0] == RD.RED
    assert rows[2][0] == RD.NO_VERDICT, "a killed check was read as green"

    st = RD.check_state(root)["health_round"]
    assert st["last_log_round"] == 2
    assert st["last_verdict_round"] == 1, "state was read off the killed run"
    assert st["verdict"] == RD.RED
    assert st["stale_rounds"] == 1

    items = RD.debt(root)
    assert [r["node"] for r in items] == [NODE]
    assert items[0]["stale_rounds"] == 1
    assert "could not run is not a check that passed" in RD.note(root, min_logs=1)


def test_a_no_verdict_round_does_not_split_an_episode(tmp_path):
    """A killed check in the MIDDLE is not evidence the node went green.

    Rounds 1 and 3 are red, round 2 was killed. The episode is one run of
    two verdict rounds, not two episodes of one — otherwise every budget
    overrun would reset the age of every red under it and nothing would ever
    look overdue.
    """
    root = _tree(tmp_path, {
        1: ([NODE], PASSED_TAIL),
        2: ([], "no count line\n"),
        3: ([NODE], PASSED_TAIL),
    })
    r = RD.debt(root)[0]
    assert r["age"] == 2, r
    assert r["first_red_round"] == 1, r
    assert r["shape"] == "new", r
    assert r["prior_episodes"] == 0, r


def test_a_real_green_round_does_split_the_episode(tmp_path):
    """The negative control for the test above. If a genuine green did NOT
    close the episode, `age` would be a count of rounds since the first red
    ever and `new`/`recurrent` would be meaningless.
    """
    root = _tree(tmp_path, {
        1: ([NODE], PASSED_TAIL),
        2: ([], CLEAN_TAIL),
        3: ([NODE], PASSED_TAIL),
    })
    r = RD.debt(root)[0]
    assert r["age"] == 1, r
    assert r["first_red_round"] == 3, r
    assert r["shape"] == "recurrent", r
    assert r["prior_episodes"] == 1, r
    assert r["last_closed_round"] == 2, r


# ------------------------------------------------- new vs recurrent, sharp --

def test_a_node_red_for_the_first_time_ever_is_new_not_recurrent(tmp_path):
    """This module's FIRST classifier called a node `flapping` if it had any
    green round in a trailing window, which made every node younger than the
    window flapping — `0 standing, 14 flapping` on the live logs. Here the
    node is green for four rounds and then red: plenty of greens in the
    window, no prior EPISODE, so the answer must be `new`.
    """
    rounds = {n: ([], CLEAN_TAIL) for n in range(1, 5)}
    rounds[5] = ([NODE], PASSED_TAIL)
    r = RD.debt(_tree(tmp_path, rounds))[0]
    assert r["shape"] == "new", "green rounds were mistaken for flapping"
    assert r["prior_episodes"] == 0 and r["prior_episodes_all"] == 0


def test_the_window_bounds_recurrence_but_the_all_time_count_does_not(tmp_path):
    """A red that closed 30 rounds ago is not evidence about this one, so it
    must not make the node `recurrent` — but the history must not be thrown
    away either, or a reader cannot tell a first-ever red from a node with a
    decade of episodes behind it.
    """
    rounds = {1: ([NODE], PASSED_TAIL)}
    rounds.update({n: ([], CLEAN_TAIL) for n in range(2, 40)})
    rounds[40] = ([NODE], PASSED_TAIL)
    root = _tree(tmp_path, rounds)

    wide = RD.debt(root, window=0)[0]        # 0 == the whole retained corpus
    assert wide["shape"] == "recurrent" and wide["prior_episodes"] == 1

    narrow = RD.debt(root, window=5)[0]
    assert narrow["shape"] == "new", narrow
    assert narrow["prior_episodes"] == 0
    assert narrow["prior_episodes_all"] == 1, "the history was discarded"
    assert narrow["last_closed_round"] == 2


def test_episodes_agree_with_redattribs_own_episode_function(tmp_path):
    """The agreement guard. Two modules deriving episode structure from the
    same logs by different code is how a program ends up with two numbers for
    one fact; this one CALLS `redattrib.episodes_for`, and this test holds
    that open so a future refactor cannot quietly fork it.
    """
    rounds = {1: ([NODE], PASSED_TAIL), 2: ([], CLEAN_TAIL),
              3: ([NODE], PASSED_TAIL), 4: ([NODE], PASSED_TAIL)}
    root = _tree(tmp_path, rounds)
    per = RD.check_rounds(root)["health_round"]
    wv = sorted(per)
    red = {r for r in wv if NODE in per[r][1]}
    eps = RA.episodes_for(NODE, wv, red)
    r = RD.debt(root)[0]
    assert len(eps) == 2
    assert r["age"] == len(eps[-1]["rounds"]) == 2
    assert r["first_red_round"] == eps[-1]["open"] == 3


# ------------------------------------------------------- opener vs owner --

def test_invisible_open_is_true_when_the_opener_does_not_own_the_suite(tmp_path):
    """The mechanism this module exists to print. `harness/tests` is owned by
    harness(A); an episode opened while NUC-integration(E) was running is one
    the owning track cannot have seen by running its own suite.
    """
    root = _tree(tmp_path, {1: ([], CLEAN_TAIL), 2: ([NODE], PASSED_TAIL)},
                 tracks={2: "NUC-integration(E)"})
    r = RD.debt(root)[0]
    assert r["owner"] == "harness(A)"
    assert r["opener"] == "NUC-integration(E)"
    assert r["invisible_open"] is True
    assert "who does not run this suite" in RD.note(root, min_logs=1)


def test_invisible_open_is_false_when_the_owner_opened_it(tmp_path):
    """Negative control: without this, `invisible_open` could be a constant
    True and every test above would still pass.
    """
    root = _tree(tmp_path, {1: ([], CLEAN_TAIL), 2: ([NODE], PASSED_TAIL)},
                 tracks={2: "harness(A)"})
    r = RD.debt(root)[0]
    assert r["invisible_open"] is False
    assert "who does not run this suite" not in RD.note(root, min_logs=1)


# ------------------------------- the head sentence must describe the rows --

def test_the_head_names_the_suite_files_that_are_actually_red(tmp_path):
    """Round 505's finding, as a falsifier.

    Round 493 wrote the headline with its own red set spelled into it: "the
    wiring-audit trio below is the fifth instance of a recurrence
    `harness/wiring-registry.json` has diagnosed in prose four times since
    round 473". Round 505 received that sentence above three
    `test_swe_copyparity_real_subject.py` nodes and one `test_whenceslow.py`
    node -- no wiring audit anywhere in the list, and not an instance of that
    recurrence. Twelve rounds were handed a headline about the wrong red.

    So the head is required to name the suite files it is standing above, and
    two DIFFERENT red sets must produce two different heads. A hardcoded
    sentence passes neither clause.
    """
    a = _tree(tmp_path / "a", {1: ([], CLEAN_TAIL), 2: ([NODE], PASSED_TAIL)})
    b = _tree(tmp_path / "b",
              {1: ([], CLEAN_TAIL),
               2: (["harness/tests/test_zzz.py::test_other"], PASSED_TAIL)})
    ha = RD.note(a, min_logs=1).strip().splitlines()[0]
    hb = RD.note(b, min_logs=1).strip().splitlines()[0]
    assert "harness/tests/test_a.py" in ha and "test_zzz" not in ha
    assert "harness/tests/test_zzz.py" in hb and "test_a.py" not in hb
    assert ha != hb, "the head does not vary with the rows it introduces"


def test_the_head_states_the_invisible_open_count_and_both_directions(tmp_path):
    """The clause that made round 493 build this module at all is a NUMBER,
    and it has to be the number in front of the reader -- including when it
    is zero, which is the case where no instrument would have helped."""
    seen = _tree(tmp_path / "seen",
                 {1: ([], CLEAN_TAIL), 2: ([NODE], PASSED_TAIL)},
                 tracks={2: "harness(A)"})
    unseen = _tree(tmp_path / "unseen",
                   {1: ([], CLEAN_TAIL), 2: ([NODE], PASSED_TAIL)},
                   tracks={2: "language(C)"})
    h_seen = RD.note(seen, min_logs=1)
    h_unseen = RD.note(unseen, min_logs=1)
    assert "visible to its author" in h_seen
    assert "readset.py blast" not in h_seen, (
        "pointing at the opener-side instrument when nothing was opened "
        "invisibly is advice for a problem this list does not have")
    assert "1 of them was opened by a track that does NOT run" in h_unseen
    assert "readset.py blast" in h_unseen


def test_the_head_reaches_the_reader_with_a_runnable_command(tmp_path):
    """`skills/finding-must-reach-an-actor` in one assertion: the instrument
    named in the head has to exist and be runnable from the repo root, or
    the sentence is the same rot it replaced."""
    root = _tree(tmp_path, {1: ([], CLEAN_TAIL), 2: ([NODE], PASSED_TAIL)},
                 tracks={2: "language(C)"})
    text = RD.note(root, min_logs=1)
    assert "python3 harness/readset.py blast" in text
    assert os.path.exists(os.path.join(REPO, "harness", "readset.py"))
    p = subprocess.run([sys.executable, "harness/readset.py", "blast",
                        "--json", "languages/whence/no_such_file.py"],
                       cwd=REPO, capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stdout + p.stderr


# -------------------------------------------------------- the note itself --

def test_a_clean_tree_costs_the_prompt_zero_bytes(tmp_path):
    """An empty note is the CLEAN signal, and the driver appends it raw. If
    this ever returned a "nothing to report" sentence, every healthy round
    would pay for it in prompt tokens forever.
    """
    rounds = {n: ([], CLEAN_TAIL) for n in range(1, 60)}
    assert RD.note(_tree(tmp_path, rounds)) == ""


def test_a_thin_evidence_base_shouts_instead_of_reporting_clean(tmp_path):
    """The dangerous confusion, pinned. `logs/` is not in git (redattrib's
    own docstring: 602 retained logs live, 0 in a fresh clone), so a detached
    worktree sees no evidence at all. Returning "" there would tell the round
    the tree is clean on exactly the checkout that knows least.
    """
    root = _tree(tmp_path, {1: ([NODE], PASSED_TAIL)})
    n_logs, enough = RA.evidence_base(root)
    assert not enough and n_logs < RA.MIN_EVIDENCE_LOGS
    text = RD.note(root)
    assert text != "", "a blind checkout reported itself clean"
    assert "NO EVIDENCE BASE" in text
    assert str(RA.MIN_EVIDENCE_LOGS) in text


def test_the_note_names_the_overdue_red_and_the_reproduce_instruction(tmp_path):
    """A red older than one full rotation has survived a round of every
    track, including the one that owns it. That is a different fact from
    "something is red" and the note has to say which.
    """
    rounds = {n: ([], CLEAN_TAIL) for n in range(1, 55)}
    rounds.update({n: ([NODE], PASSED_TAIL)
                   for n in range(55, 55 + RD.ROTATION)})
    text = RD.note(_tree(tmp_path, rounds), min_logs=1)
    assert "PAST ONE FULL ROTATION" in text
    assert "REPRODUCE IT BEFORE FIXING IT" not in text  # `new`, never closed
    items = RD.debt(_tree(tmp_path, rounds))
    assert items[0]["overdue"] is True and items[0]["age"] == RD.ROTATION


def test_one_round_short_of_a_rotation_is_not_overdue(tmp_path):
    """Boundary control for the test above."""
    rounds = {n: ([], CLEAN_TAIL) for n in range(1, 55)}
    rounds.update({n: ([NODE], PASSED_TAIL)
                   for n in range(55, 55 + RD.ROTATION - 1)})
    items = RD.debt(_tree(tmp_path, rounds))
    assert items[0]["age"] == RD.ROTATION - 1
    assert items[0]["overdue"] is False
    assert "PAST ONE FULL ROTATION" not in RD.note(_tree(tmp_path, rounds), min_logs=1)


def test_nodes_are_ordered_oldest_debt_first(tmp_path):
    """The reader acts on the top of the list, so the oldest red has to be
    there — not whichever check sorts first alphabetically.
    """
    rounds = {n: ([], CLEAN_TAIL) for n in range(1, 50)}
    for n in range(50, 56):
        rounds[n] = ([NODE], PASSED_TAIL)
    rounds[55] = ([NODE, OTHER], PASSED_TAIL)
    items = RD.debt(_tree(tmp_path, rounds))
    assert [r["node"] for r in items] == [NODE, OTHER]
    assert items[0]["age"] > items[1]["age"]


# -------------------------------------------------------------------- CLI --

def _cli(root, *args):
    env = dict(os.environ, PYTHONPATH=HARNESS)
    p = subprocess.run([sys.executable,
                        os.path.join(HARNESS, "reddebt.py"),
                        "--root", root] + list(args),
                       cwd=root, capture_output=True, text=True, env=env)
    return p


def test_the_cli_runs_on_this_tree_and_every_subcommand_exits_zero():
    for args in (["debt"], ["debt", "--json"], ["note"], ["state"],
                 ["state", "--json"]):
        p = _cli(REPO, *args)
        assert p.returncode == 0, (args, p.stderr[-2000:])
    assert json.loads(_cli(REPO, "debt", "--json").stdout) is not None


def test_strict_exits_one_only_when_a_red_is_past_a_rotation(tmp_path):
    """`--strict` is the only non-zero exit this module has, so it is the
    only thing that could ever stop something. Both directions pinned.
    """
    ok = {n: ([], CLEAN_TAIL) for n in range(1, 60)}
    ok[60] = ([NODE], PASSED_TAIL)
    assert _cli(_tree(tmp_path / "a", ok), "debt", "--strict").returncode == 0

    bad = {n: ([], CLEAN_TAIL) for n in range(1, 55)}
    bad.update({n: ([NODE], PASSED_TAIL)
                for n in range(55, 55 + RD.ROTATION)})
    assert _cli(_tree(tmp_path / "b", bad), "debt", "--strict").returncode == 1


# ------------------------------------------------------- the live tree --

class TestThisTree:
    """Run against the real retained logs, skipped where there are none.

    `logs/` is not in git, so these must SKIP in a pristine worktree rather
    than fail — redattrib learned that the hard way (round 461: 4 failed
    where the truth was 2, two of them floods caused by missing files).
    """

    def setup_method(self):
        n, enough = RA.evidence_base(REPO)
        if not enough:
            pytest.skip("only %d retained health log(s) in this checkout" % n)

    def test_every_currently_red_node_belongs_to_a_declared_suite(self):
        """An unowned node means `SUITE_OWNER` has drifted from the tree, and
        the note would print `owner unknown` at the reader.
        """
        unowned = [r["node"] for r in RD.debt(REPO) if r["owner"] is None]
        assert unowned == [], unowned

    def test_every_currently_red_node_has_a_placeable_opener(self):
        """`round_tracks` reads driver.log's own `start` lines. A missing
        opener means the episode began in a round the driver never logged,
        which is a record gap and not something to print as `unknown`.
        """
        assert [r["node"] for r in RD.debt(REPO) if r["opener"] is None] == []

    def test_the_state_of_each_check_is_read_from_a_round_it_had_a_verdict_in(self):
        for prefix, st in RD.check_state(REPO).items():
            if st["last_verdict_round"] is None:
                continue
            assert st["last_verdict_round"] <= st["last_log_round"]
            assert st["stale_rounds"] >= 0

    def test_the_note_is_either_empty_or_names_every_debt_item(self):
        items = RD.debt(REPO)
        text = RD.note(REPO)
        if not items:
            assert text == ""
            return
        for r in items:
            assert r["node"] in text, r["node"]
        assert str(len(items)) in text.strip().splitlines()[0]


# ------------------------------------------------ the driver actually asks --

DRIVER_SRC = os.path.join(REPO, "run_driver.sh")

STUB_NOTE = "REDDEBT-STUB-MARKER: three things are on fire"

STUB_OK = """#!/usr/bin/env python3
import sys
if sys.argv[1:2] == ["note"]:
    print(%r)
else:
    print("red-debt: stub line")
""" % STUB_NOTE

STUB_SILENT = """#!/usr/bin/env python3
import sys
sys.exit(0)
"""

STUB_BROKEN = """#!/usr/bin/env python3
raise SystemExit("this instrument is broken")
"""

CLAUDE_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
WS="$DRIVER_TEST_WS"
PROMPT=""
while [ $# -gt 0 ]; do
  if [ "$1" = "-p" ]; then PROMPT="$2"; shift 2; continue; fi
  shift
done
if [ ! -f "$WS/state/captured_prompt.txt" ]; then
  printf '%s' "$PROMPT" > "$WS/state/captured_prompt.txt"
fi
echo '{"type":"result","is_error":true,"subtype":"error_other","num_turns":1,"result":"stop","api_error_status":null,"total_cost_usd":0.01}'
"""


def _run_driver_with_reddebt(tmp_path, stub_source):
    ws = str(tmp_path)
    for d in ("state", "logs", "harness", "bin"):
        os.makedirs(os.path.join(ws, d), exist_ok=True)
    shutil.copyfile(DRIVER_SRC, os.path.join(ws, "run_driver.sh"))
    os.chmod(os.path.join(ws, "run_driver.sh"), 0o755)
    if stub_source is not None:
        with open(os.path.join(ws, "harness", "reddebt.py"), "w") as fh:
            fh.write(stub_source)

    stub = os.path.join(ws, "bin", "claude")
    with open(stub, "w") as fh:
        fh.write(CLAUDE_STUB)
    os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC | stat.S_IXGRP
             | stat.S_IXOTH)

    env = dict(os.environ)
    env["PATH"] = os.path.join(ws, "bin") + os.pathsep + env["PATH"]
    env["DRIVER_WS"] = ws
    env["DRIVER_TEST_WS"] = ws
    env["DRIVER_LOOP_SLEEP_S"] = "0"
    env["DRIVER_CLAUDE_CMD"] = "claude"
    env["PYTHONPATH"] = REPO + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(["bash", os.path.join(ws, "run_driver.sh")],
                            cwd=REPO, env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=90)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        pytest.fail("driver did not stop within 90s")
    captured = os.path.join(ws, "state", "captured_prompt.txt")
    assert os.path.exists(captured), "stub never received a -p prompt"
    with open(captured) as fh:
        return fh.read()


def test_the_driver_puts_the_red_debt_note_in_the_round_prompt(tmp_path):
    """The whole point. Before round 493 the driver injected exactly ONE
    pre-round diagnostic and a red test reached the round agent by no route
    at all — which is how the wiring trio survived rounds 490, 491 and 492.
    """
    prompt = _run_driver_with_reddebt(tmp_path, STUB_OK)
    assert STUB_NOTE in prompt, prompt[-1500:]
    # After the turn budget, not spliced into the middle of it.
    assert prompt.index(STUB_NOTE) > prompt.index("TURN BUDGET")


def test_a_silent_instrument_adds_nothing_to_the_prompt(tmp_path):
    prompt = _run_driver_with_reddebt(tmp_path, STUB_SILENT)
    assert "REDDEBT-STUB-MARKER" not in prompt
    assert prompt.rstrip().endswith("do not depend on each other."), \
        prompt[-300:]


def test_a_broken_instrument_does_not_stop_the_round(tmp_path):
    """Fail-open, pinned. A red-test reporter that can prevent a round is a
    reporter that can prevent the round which would fix the red.
    """
    prompt = _run_driver_with_reddebt(tmp_path, STUB_BROKEN)
    assert "TURN BUDGET" in prompt
    assert "REDDEBT-STUB-MARKER" not in prompt


def test_an_absent_instrument_does_not_stop_the_round(tmp_path):
    prompt = _run_driver_with_reddebt(tmp_path, None)
    assert "TURN BUDGET" in prompt


def test_the_driver_defines_the_variable_it_interpolates():
    """`set -u` is on in this script. Interpolating an undefined
    `$RED_DEBT_NOTE` would abort the driver on its first round, and `bash -n`
    does not catch it.
    """
    src = open(DRIVER_SRC).read()
    assert 'RED_DEBT_NOTE=""' in src
    assert "$ROUND_GAP_NOTE$RED_DEBT_NOTE" in src
    assert src.index('RED_DEBT_NOTE=""') < src.index(
        "$ROUND_GAP_NOTE$RED_DEBT_NOTE")

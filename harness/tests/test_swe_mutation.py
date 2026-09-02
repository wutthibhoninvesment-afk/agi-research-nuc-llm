"""swe.mutation on a tiny fixture project (fast, no Whence involved)."""
import os
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.mutation import generate, mutation_test, run_mutant, DEFAULT_TEST_CMD
from swe.fuzz import CURATION_MANIFEST, example_curation, list_example_files

MOD = textwrap.dedent('''
    """docstring must not be mutated"""
    def clamp(x, lo, hi):
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x

    def is_even(n):
        return n % 2 == 0 and not n < 0
''')

TESTS = textwrap.dedent('''
    from mod import clamp, is_even
    def test_clamp():
        assert clamp(5, 0, 3) == 3
        assert clamp(-1, 0, 3) == 0
        assert clamp(2, 0, 3) == 2
    def test_even():
        assert is_even(4) and not is_even(3)
''')


def make_project(tmp_path):
    (tmp_path / "mod.py").write_text(MOD)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mod.py").write_text(TESTS)
    (tmp_path / "tests" / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")
    return str(tmp_path)


def test_generate_enumerates_operators_and_skips_docstrings():
    ms = generate(MOD, "mod.py")
    ops = {m.op for m in ms}
    assert {"cmp", "ifneg", "const", "arith", "bool", "not"} <= ops
    assert all("docstring must not be mutated" in m.source for m in ms)
    assert all(m.source != MOD for m in ms)
    assert len({m.id for m in ms}) == len(ms)          # ids unique
    for m in ms:
        compile(m.source, m.id, "exec")                # every mutant is valid Python


def test_not_operator_drops_the_not():
    m = next(m for m in generate(MOD, "mod.py") if m.op == "not")
    assert "not not n < 0" in m.source          # `not not x` == truthiness of x


def test_run_mutant_never_touches_original(tmp_path):
    root = make_project(tmp_path)
    m = generate(MOD, "mod.py")[0]
    run_mutant(m, root, DEFAULT_TEST_CMD)
    assert (tmp_path / "mod.py").read_text() == MOD
    assert m.status in ("killed", "survived")


def test_mutation_test_scores_and_finds_survivors(tmp_path):
    root = make_project(tmp_path)
    rep = mutation_test(root, ["mod.py"], DEFAULT_TEST_CMD, workers=4)
    assert rep.mutants and all(m.status for m in rep.mutants)
    assert 0 < rep.score < 1                       # some killed, some survive
    # `n < 0` guard in is_even is never exercised: its mutants must survive
    survivors = {m.description for m in rep.survived}
    assert any("Lt -> LtE" in d for d in survivors)
    text = rep.summary()
    assert "SURVIVED" in text and "score" in text
    d = rep.as_dict()
    assert d["total"] == len(rep.mutants) and d["killed"] + d["survived"] == d["total"]


def test_timeout_counts_as_killed(tmp_path):
    root = make_project(tmp_path)
    m = generate(MOD, "mod.py")[0]
    m.source = "import time\ntime.sleep(5)\n" + m.source
    run_mutant(m, root, DEFAULT_TEST_CMD, timeout_s=0.5)
    assert m.status == "timeout"


def _grandchild_mutant(pidfile, startup_delay_s=0.0):
    """Mutant source that spawns a stdout-inheriting grandchild outliving the
    cap, and records that grandchild's pid FROM THE PARENT.

    Round 449 (SWE-loop D). The original fixture had the GRANDCHILD write its
    own pid, which made the test's evidence race the cap: `Popen` returns as
    soon as the child has EXEC'd, but everything a CPython interpreter does
    after exec — `site`, the import machinery, the `-c` body — is schedulable
    work, and on this 1-core box running four suites at once it does not
    always finish inside 2.0 s. `p.pid` is known to the parent the instant
    Popen returns and costs the grandchild nothing, so the same evidence is
    collected without the race. `startup_delay_s` simulates the contention
    that produced round 447's failure; see
    `test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap`.
    """
    body = "import time; time.sleep(%r); time.sleep(60)" % startup_delay_s
    return textwrap.dedent('''
        import os, subprocess, sys, time
        # grandchild inherits our stdout (the pipe) and outlives the cap
        p = subprocess.Popen([sys.executable, "-c", %r])
        with open(%r, "w") as fh:
            fh.write(str(p.pid))
        time.sleep(60)
    ''' % (body, str(pidfile)))


def _wait_dead(pid, budget_s=5.0):
    import time
    deadline = time.time() + budget_s
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def test_timeout_kills_grandchild_holding_stdout(tmp_path):
    """Round 101: a test spawned a `run.py` grandchild that inherited stdout
    and looped forever; `subprocess.run(timeout=)` killed pytest, then blocked
    in `communicate()` for 22,071 s because the pipe never closed. The runner
    must return within the cap and the grandchild must be dead."""
    import time
    root = make_project(tmp_path)
    pidfile = tmp_path / "grandchild.pid"
    m = generate(MOD, "mod.py")[0]
    m.source = _grandchild_mutant(pidfile) + m.source
    t0 = time.time()
    run_mutant(m, root, DEFAULT_TEST_CMD, timeout_s=2.0)
    wall = time.time() - t0
    assert m.status == "timeout" and "group" in m.detail
    assert wall < 15, "runner blocked on the grandchild's pipe for %.1fs" % wall
    assert pidfile.exists(), (
        "the mutant was killed before it recorded the grandchild's pid — this "
        "run proved nothing about killing grandchildren, and saying so is the "
        "point (round 449)")
    pid = int(pidfile.read_text())
    assert _wait_dead(pid), "grandchild %d survived the cap" % pid


def test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap(tmp_path):
    """Round 449 — round 447's health-check FAIL, reproduced without a spike.

    Round 447's `health-check FAIL` was this file's grandchild test, and the
    traceback named neither a race nor a grandchild: it was a bare
    `FileNotFoundError` on `pidfile.read_text()`, because the pidfile the
    GRANDCHILD was supposed to write did not exist. The driver runs four
    suites at once on a box whose `nproc` is 1, and the grandchild's
    interpreter simply was not scheduled inside the 2.0 s cap.

    Round 443's technique applies exactly: the spike does not need producing,
    it needs SIMULATING. Delaying the grandchild 3.0 s against the unchanged
    2.0 s cap fails the old shape deterministically (measured: `pidfile:
    False`) and passes this one, on an idle box, in about two seconds.

    The honest limit, measured with the same harness: this removes the
    GRANDCHILD's startup from the race, not the parent's. At a 0.3 s cap both
    shapes fail, because the mutant is killed before pytest has imported it —
    and there the run really has proved nothing, which is why the assertion
    above says so instead of raising `FileNotFoundError`.
    """
    root = make_project(tmp_path)
    pidfile = tmp_path / "grandchild.pid"
    m = generate(MOD, "mod.py")[0]
    m.source = _grandchild_mutant(pidfile, startup_delay_s=3.0) + m.source
    run_mutant(m, root, DEFAULT_TEST_CMD, timeout_s=2.0)
    assert m.status == "timeout" and "group" in m.detail
    assert pidfile.exists(), "the parent must record the pid, not the grandchild"
    assert _wait_dead(int(pidfile.read_text()))


# ------------------------------------------------------- round 349 (harness A) --
#
# Regression pins for the "a suite that cannot run scores 100%" defect.
# Round 348 a separate autonomous system appended a duplicate
# `[project.optional-dependencies]` table to the untracked
# `languages/whence/pyproject.toml`. `_copy_project` copies that file into
# every mutant tree; pytest parses it during config DISCOVERY, before
# collection, and exits 4. `run_mutant` read every non-zero exit as a kill,
# so the campaign reported a perfect score having run no tests at all.
# Measured live over 6 mutants of `whence/values.py`: broken 6 killed /
# score 1.00, repaired 3 killed 3 survived / score 0.50.

from swe.mutation import (BaselineNotGreen, _copy_project, baseline_check, classify_mutant_run,
                          is_pytest_cmd)
import pytest

# A pyproject.toml with the exact defect round 348 shipped.
BROKEN_PYPROJECT = textwrap.dedent('''
    [project]
    name = "fixture"
    version = "0.0.1"

    [project.optional-dependencies]
    dev = ["pytest>=7.0"]

    [project.optional-dependencies]
    dev = ["pytest"]
''')

PYTEST_CMD = [sys.executable, "-m", "pytest", "-q", "tests"]


def test_is_pytest_cmd_recognises_the_forms_we_actually_use():
    assert is_pytest_cmd(PYTEST_CMD)
    assert is_pytest_cmd(DEFAULT_TEST_CMD)
    assert is_pytest_cmd(["/usr/bin/pytest", "-q"])
    assert not is_pytest_cmd(["make", "test"])
    assert not is_pytest_cmd([])
    assert not is_pytest_cmd(None)


def test_classify_mutant_run_only_counts_a_real_test_failure_as_a_kill():
    # 0 = green suite, the mutant slipped through.
    assert classify_mutant_run(0, "", PYTEST_CMD) == "survived"
    # 1 = tests ran and failed. The ONLY kill.
    assert classify_mutant_run(1, "1 failed", PYTEST_CMD) == "killed"
    # 2-5 = the harness broke; no evidence about the mutant either way.
    for rc in (2, 3, 4, 5):
        assert classify_mutant_run(rc, "ERROR", PYTEST_CMD) == "error", rc
    # A signal death IS a behavioural difference the suite caught.
    assert classify_mutant_run(-11, "", PYTEST_CMD) == "killed"
    # For a non-pytest runner the exit-code table means nothing, so keep the
    # old any-failure-is-a-kill rule rather than guess.
    assert classify_mutant_run(4, "", ["make", "test"]) == "killed"


def test_baseline_check_is_green_on_a_healthy_project(tmp_path):
    b = baseline_check(make_project(tmp_path), PYTEST_CMD, timeout_s=120.0)
    assert b["returncode"] == 0 and not b["timed_out"]


def test_baseline_check_catches_the_unowned_broken_config(tmp_path):
    root = make_project(tmp_path)
    (tmp_path / "pyproject.toml").write_text(BROKEN_PYPROJECT)
    b = baseline_check(root, PYTEST_CMD, timeout_s=120.0)
    assert b["returncode"] == 4
    assert "optional-dependencies" in b["tail"]


def test_mutation_test_refuses_to_score_against_a_broken_baseline(tmp_path):
    root = make_project(tmp_path)
    (tmp_path / "pyproject.toml").write_text(BROKEN_PYPROJECT)
    with pytest.raises(BaselineNotGreen) as ei:
        mutation_test(root, ["mod.py"], PYTEST_CMD, workers=2, limit=2)
    assert ei.value.returncode == 4
    assert "not evidence" in str(ei.value)


def test_baseline_also_catches_a_merely_red_suite(tmp_path):
    """The exit-code classifier alone cannot see this one.

    One pre-existing failing test pins every mutant to `killed` (rc 1, a
    perfectly legitimate kill code) and yields score 1.00 just as surely as
    a config error does. Only the baseline run distinguishes it.
    """
    root = make_project(tmp_path)
    (tmp_path / "tests" / "test_already_red.py").write_text("def test_red():\n    assert False\n")
    with pytest.raises(BaselineNotGreen) as ei:
        mutation_test(root, ["mod.py"], PYTEST_CMD, workers=2, limit=2)
    assert ei.value.returncode == 1


def test_broken_config_now_errors_every_mutant_instead_of_killing_it(tmp_path):
    """The pre-349 behaviour, pinned by its numbers.

    With `baseline=False` (the escape hatch campaign.py uses) the per-mutant
    classifier is the last line of defence, and it must move this tree from
    score 1.00 to score 0.00.
    """
    root = make_project(tmp_path)
    (tmp_path / "pyproject.toml").write_text(BROKEN_PYPROJECT)
    rep = mutation_test(root, ["mod.py"], PYTEST_CMD, workers=2, limit=4, baseline=False)
    assert rep.mutants
    assert all(m.status == "error" for m in rep.mutants)
    assert rep.killed == [] and rep.survived == []
    assert len(rep.errored) == len(rep.mutants)
    assert rep.score == 0.0          # was 1.0 before round 349
    assert rep.valid_score == 0.0    # no evidence-bearing runs at all
    d = rep.as_dict()
    assert d["errored"] == d["total"] and d["killed"] == 0
    text = rep.summary()
    assert "ERRORED" in text and "not evidence" in text


def test_valid_score_equals_score_when_nothing_errored(tmp_path):
    rep = mutation_test(make_project(tmp_path), ["mod.py"], PYTEST_CMD, workers=4)
    assert rep.errored == []
    assert rep.valid_score == rep.score
    assert rep.as_dict()["valid_score"] == rep.as_dict()["score"]


def test_classify_mutant_run_whitelists_rather_than_blacklists_pytest_codes():
    """An undocumented pytest exit code is no evidence, not a free kill.

    Blacklisting the known-bad codes would leave anything outside the
    documented 0-5 table classified as a kill — which is the exact
    assumption that produced this defect in the first place.
    """
    for rc in (6, 7, 42, 99):
        assert classify_mutant_run(rc, "", PYTEST_CMD) == "error", rc
    # ...but a generic runner keeps the historical rule, since its codes
    # carry no agreed meaning at all.
    for rc in (6, 42):
        assert classify_mutant_run(rc, "", ["make", "test"]) == "killed", rc
    # Signals kill under either runner.
    assert classify_mutant_run(-9, "", ["make", "test"]) == "killed"


def test_copy_project_ignores_the_npm_tree(tmp_path):
    """Round 413. `guardpin.py` is the first caller to pass the REPO ROOT to
    `_copy_project` rather than `languages/whence`, and `node_modules` is
    468 MB against ~26 MB for the rest of the checkout — a 9-second copy per
    mutant instead of a 1.8-second one.

    Pinned because the ignore list is the only thing standing between a
    per-mutant copy and half a gigabyte, and nothing else in this suite reads
    it: every pattern already in the list was added without a test.
    """
    src = tmp_path / "src"
    (src / "node_modules" / "@anthropic-ai").mkdir(parents=True)
    (src / "node_modules" / "@anthropic-ai" / "big.js").write_text("x" * 4096)
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "m.cpython-3.pyc").write_text("junk")
    (src / "keep.py").write_text("K = 1\n")
    dst = tmp_path / "dst"
    _copy_project(str(src), str(dst))
    assert (dst / "keep.py").read_text() == "K = 1\n"
    assert not (dst / "node_modules").exists()
    assert not (dst / "__pycache__").exists()


# --------------------------------------------------------------------------
# Round 437 (SWE-loop D): the curation that did not survive the copy.
#
# `swe.fuzz.list_example_files` resolves the curated `examples/*.lang` corpus
# by shelling `git ls-files`, because `languages/whence/examples/` is shared
# with another autonomous process whose files `.gitignore` lists by name.
# `_copy_project` excludes `.git` deliberately (round 413, size). So in every
# copied tree the git branch could not answer and the function fell through
# to `os.listdir` — 27 programs in a campaign's differential corpus where the
# checkout itself yields 13, with no error and no failing test, because a
# widened corpus produces MORE evidence rather than an exception.
#
# These use a tiny synthetic checkout, not `languages/whence`: the mechanism
# is `git` + `_copy_project` + a manifest, and a real-tree copy costs ~1.8 s
# in a file the fast tier has a 25 s budget for. The real-tree pin lives in
# `test_swe_fuzz.py::test_the_whence_checkout_and_its_copy_agree_on_the_corpus`.


def _tiny_checkout(root, tracked=("a.lang", "b.lang"), ignored=("foreign.lang",)):
    """A git checkout shaped like `languages/whence`: an `examples/` dir with
    committed files AND gitignored ones sitting in the same directory."""
    ex = os.path.join(root, "examples")
    os.makedirs(ex)
    for n in tracked:
        with open(os.path.join(ex, n), "w") as f:
            f.write("print(1)\n")
    for n in ignored:
        with open(os.path.join(ex, n), "w") as f:
            f.write("print(2)\n")
    with open(os.path.join(root, ".gitignore"), "w") as f:
        f.write("\n".join("examples/" + n for n in ignored) + "\n")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "x"]):
        subprocess.run(cmd, cwd=root, env=env, check=True,
                       capture_output=True, text=True)
    return root


def test_a_checkout_curates_by_git_and_hides_the_gitignored_neighbour(tmp_path):
    src = _tiny_checkout(str(tmp_path / "src"))
    names, source = example_curation(src)
    assert source == "git"
    assert names == ["a.lang", "b.lang"]          # foreign.lang is on disk and out
    assert os.path.exists(os.path.join(src, "examples", "foreign.lang"))


def test_copy_project_carries_the_example_curation_into_the_copy(tmp_path):
    """The defect and its fix in one assertion: before round 437 the copy
    answered `listdir` and included `foreign.lang`."""
    src = _tiny_checkout(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")
    _copy_project(src, dst)
    assert not os.path.exists(os.path.join(dst, ".git"))      # still excluded
    assert os.path.exists(os.path.join(dst, "examples", CURATION_MANIFEST))
    names, source = example_curation(dst)
    assert source == "manifest"
    assert names == ["a.lang", "b.lang"] == list_example_files(src)
    # the foreign file is still THERE — it is excluded, not deleted
    assert os.path.exists(os.path.join(dst, "examples", "foreign.lang"))


def test_a_copy_of_a_copy_inherits_the_curation_unchanged(tmp_path):
    """`find_killer` copies a tree that is itself already a copy, so the
    manifest has to survive an arbitrary chain. It must also not be
    REWRITTEN by a later copy: the second copy has no git either, and a
    regenerate-if-you-can rule would quietly re-curate from whatever the
    intermediate tree happens to contain."""
    src = _tiny_checkout(str(tmp_path / "src"))
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    _copy_project(src, a)
    with open(os.path.join(a, "examples", "dropped_later.lang"), "w") as f:
        f.write("print(3)\n")
    _copy_project(a, b)
    assert example_curation(b) == (["a.lang", "b.lang"], "manifest")
    first = open(os.path.join(a, "examples", CURATION_MANIFEST)).read()
    second = open(os.path.join(b, "examples", CURATION_MANIFEST)).read()
    assert first == second


def test_a_foreign_lang_file_dropped_into_a_copy_never_enters_the_corpus(tmp_path):
    """The live shape: another process writes into `examples/` while a
    campaign is running against a copy of it."""
    src = _tiny_checkout(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")
    _copy_project(src, dst)
    with open(os.path.join(dst, "examples", "gateway.lang"), "w") as f:
        f.write("print(9)\n")
    assert list_example_files(dst) == ["a.lang", "b.lang"]


def test_curation_falls_back_to_listdir_when_there_is_no_git_and_no_manifest(tmp_path):
    """The old behaviour is kept as the LAST resort and is reported by name.
    Returning it rather than raising is deliberate: a caller with no corpus
    at all is worse off than one with an uncurated corpus it can record."""
    root = str(tmp_path / "plain")
    os.makedirs(os.path.join(root, "examples"))
    for n in ("z.lang", "a.lang"):
        with open(os.path.join(root, "examples", n), "w") as f:
            f.write("print(1)\n")
    assert example_curation(root) == (["a.lang", "z.lang"], "listdir")


def test_copy_project_writes_no_manifest_when_the_source_is_not_a_checkout(tmp_path):
    """A manifest asserts that a curation decision was MADE. A source with no
    git and no manifest made none, so inventing one would freeze a listdir
    snapshot and call it curated."""
    src = str(tmp_path / "plain")
    os.makedirs(os.path.join(src, "examples"))
    with open(os.path.join(src, "examples", "a.lang"), "w") as f:
        f.write("print(1)\n")
    dst = str(tmp_path / "dst")
    _copy_project(src, dst)
    assert not os.path.exists(os.path.join(dst, "examples", CURATION_MANIFEST))
    assert example_curation(dst)[1] == "listdir"


def test_copy_project_is_unchanged_for_a_tree_with_no_examples_dir(tmp_path):
    """`guardpin.py` passes the REPO ROOT, which has no top-level
    `examples/`. The curation hook must be invisible there."""
    src = str(tmp_path / "src")
    os.makedirs(src)
    with open(os.path.join(src, "keep.py"), "w") as f:
        f.write("K = 1\n")
    dst = str(tmp_path / "dst")
    _copy_project(src, dst)
    assert sorted(os.listdir(dst)) == ["keep.py"]

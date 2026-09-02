"""Round 442 (NUC-integration E) — the interpreter `nuc/run_checks_fast.sh` runs.

`nuc-health-check` reported FAIL on every round from 410, when it was wired
into `run_driver.sh`, to 441. Thirty-two consecutive rounds, and
`grep "nuc-health-check PASS" logs/driver.log` returned nothing: the check
never had a green baseline, so "still broken" and "newly broken" were the same
line. Five track-E rounds (412, 418, 424, 430, 436) ran inside that window and
none of their knowledge files mentions it.

Nothing under `nuc/` was broken. The check and the round ran under DIFFERENT
PYTHON INTERPRETERS:

  * `claude-wrapper.sh` runs `source .venv/bin/activate`, so a round — and any
    `pytest nuc/tests` a round types by hand — gets `.venv/bin/python3`, which
    has `tokenizers`.
  * `run_driver.sh` does not activate the venv; it launches the health checks
    from its own shell, whose PATH has no `.venv/bin` (though `VIRTUAL_ENV` is
    set — a half-activated venv). Bare `python3` therefore resolved to
    `/usr/bin/python3`, which has pytest and no `tokenizers`.

Measured round 442: 794 passed / 0 failed under the venv, 2 failed / 787
passed / 5 skipped under `/usr/bin/python3`. Same tree, same pytest 9.1.1,
same Python 3.12.3.

So there are two independent things to keep nailed down, and these tests keep
them separately nailed down, because either one alone closes the symptom and
neither alone closes the defect:

  1. the script resolves its own interpreter and prefers the repo venv, so it
     measures the program the rounds actually run (`TestInterpreterResolution`);
  2. a missing OPTIONAL dependency SKIPS instead of raising, so the check is
     red for regressions and nothing else — on any interpreter, including a
     checkout with no venv at all (`TestOptionalDependencyIsOptional`).

Cost note: every test here that invokes the script passes `--collect-only -q`,
which reaches the real interpreter-resolution and audit code and costs ~1.2 s
instead of the ~86 s a full run costs. It also cannot recurse: `--collect-only`
collects `test_the_fast_check_runs_green_on_this_tree` without running it.
"""
import os
import re
import subprocess
import sys
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
NUC = os.path.dirname(HERE)
REPO = os.path.dirname(NUC)
SCRIPT = os.path.join(NUC, "run_checks_fast.sh")
VENV_PY = os.path.join(REPO, ".venv", "bin", "python3")

INTERP_RE = re.compile(r"^nuc-checks interpreter: (\S+) \(tokenizers (present|absent)\)",
                       re.M)


def _driver_env(**over):
    """The driver's environment: `.venv/bin` stripped from PATH.

    This is not a hypothetical. `run_driver.sh` only appends
    `node_modules/.bin`, so the health checks it spawns inherit a PATH with no
    venv on it. Reproducing that here is the whole point — under the round's
    own PATH the bug is invisible, which is exactly why it survived 32 rounds.
    """
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep)
             if os.path.normpath(p) != os.path.normpath(os.path.dirname(VENV_PY))]
    env = dict(os.environ, PATH=os.pathsep.join(parts))
    env.pop("NUC_CHECK_PYTHON", None)
    env.update(over)
    return env


def _run(env, *args, timeout=300):
    return subprocess.run(["bash", SCRIPT, "--collect-only", "-q", *args],
                          cwd=REPO, env=env, capture_output=True,
                          text=True, timeout=timeout)


@pytest.mark.skipif(not os.path.exists(SCRIPT), reason="check script absent")
class TestInterpreterResolution:

    def test_the_script_announces_which_interpreter_it_used(self):
        """An unannounced interpreter is how this went unnoticed for 32 rounds.

        The log recorded a failing test name and never the fact that the
        failure was environmental, so every reader who re-ran the suite by hand
        saw it pass and moved on."""
        proc = _run(_driver_env())
        m = INTERP_RE.search(proc.stdout)
        assert m, proc.stdout[-2000:]
        assert os.path.isabs(m.group(1)) or os.path.exists(m.group(1))

    @pytest.mark.skipif(not os.path.exists(VENV_PY), reason="no repo .venv")
    def test_it_prefers_the_repo_venv_when_path_does_not_have_it(self):
        """THE regression. With the driver's PATH the script must still pick
        the venv — the interpreter every round runs under."""
        proc = _run(_driver_env())
        m = INTERP_RE.search(proc.stdout)
        assert m, proc.stdout[-2000:]
        assert os.path.realpath(m.group(1)) == os.path.realpath(VENV_PY)
        assert proc.returncode == 0, proc.stdout[-2000:]

    def test_an_explicit_override_wins_over_the_venv(self):
        """`NUC_CHECK_PYTHON` is the seam these tests steer with, so it has to
        actually steer."""
        proc = _run(_driver_env(NUC_CHECK_PYTHON=sys.executable))
        m = INTERP_RE.search(proc.stdout)
        assert m, proc.stdout[-2000:]
        assert os.path.realpath(m.group(1)) == os.path.realpath(sys.executable)

    def test_a_candidate_that_cannot_import_pytest_is_rejected(self):
        """/bin/true is executable and exits 0 for any argv. An exit-status-only
        usability test accepts it as a Python interpreter; this one must not,
        and must fall through to the next candidate rather than dying."""
        if not os.path.exists("/bin/true"):
            pytest.skip("no /bin/true")
        proc = _run(_driver_env(NUC_CHECK_PYTHON="/bin/true"))
        m = INTERP_RE.search(proc.stdout)
        assert m, proc.stdout[-2000:]
        assert os.path.realpath(m.group(1)) != os.path.realpath("/bin/true")
        assert proc.returncode == 0, proc.stdout[-2000:]

    def test_the_script_never_calls_a_bare_python3_again(self):
        """A single re-introduced bare `python3` re-opens the split, and it
        would do so silently: the check would go on printing an interpreter
        line naming the resolved one while a leg ran under another."""
        body = [l for l in open(SCRIPT, encoding="utf-8").read().splitlines()
                if not l.lstrip().startswith("#")]
        # COMMAND POSITION only: start of line, or straight after a pipe,
        # semicolon, `&&` or `$(`. `python3` inside a quoted message (the
        # NONE-USABLE echo) invokes nothing, and a check that cannot tell a
        # word from a call gets an exemption bolted onto it and then ignored.
        cmd_pos = re.compile(r"(?:^|[|;&]|\$\()\s*python3\b")
        offenders = [l for l in body if cmd_pos.search(l)]
        assert offenders == [], offenders


class TestOptionalDependencyIsOptional:
    """`tokenizers` is optional: it is in the repo `.venv` and in no other
    interpreter on this host, and NOTHING declares it (there is no
    requirements.txt, pyproject.toml or setup.py at the repo root). Two files
    import it, and before this round they disagreed about what its absence
    means — `test_prompt_budget.py` skipped, `kv_reuse_model.py` raised
    ModuleNotFoundError. The disagreement, not the missing package, is what
    made the health check unable to go green."""

    def _run_blind(self, target):
        """Run `target` in a subprocess where `tokenizers` cannot be imported,
        whatever the host actually has installed. A meta-path finder is used
        rather than picking a real interpreter that happens to lack the
        library, so the test states the same fact on every machine."""
        prog = textwrap.dedent("""
            import sys, pytest
            class Block:
                def find_module(self, name, path=None):
                    return self.find_spec(name, path)
                def find_spec(self, name, path=None, target=None):
                    if name == "tokenizers" or name.startswith("tokenizers."):
                        raise ImportError("blocked by test_run_checks_interpreter")
                    return None
            sys.meta_path.insert(0, Block())
            raise SystemExit(pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", %r]))
        """) % target
        return subprocess.run([sys.executable, "-c", prog], cwd=REPO,
                              capture_output=True, text=True, timeout=300)

    def test_have_tokenizer_reports_false_when_the_library_is_missing(self):
        prog = textwrap.dedent("""
            import sys
            class Block:
                def find_spec(self, name, path=None, target=None):
                    if name == "tokenizers":
                        raise ImportError("blocked")
                    return None
            sys.meta_path.insert(0, Block())
            sys.path.insert(0, %r)
            import kv_reuse_model as krm
            print("have:", krm.have_tokenizer())
        """) % NUC
        proc = subprocess.run([sys.executable, "-c", prog], cwd=REPO,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "have: False" in proc.stdout

    def test_kv_reuse_tests_skip_rather_than_error_without_tokenizers(self):
        """The exact 32-round regression, in one second. Before round 442 this
        produced `2 failed`; a skip is the only honest answer, because the
        tests cannot run and nothing is broken."""
        proc = self._run_blind(os.path.join("nuc", "tests", "test_kv_reuse_model.py"))
        out = proc.stdout + proc.stderr
        assert "ModuleNotFoundError" not in out, out[-2000:]
        assert " failed" not in out, out[-2000:]
        assert re.search(r"\b2 skipped\b", out), out[-2000:]
        assert proc.returncode == 0, out[-2000:]

    def test_prompt_budget_already_did_this_and_still_does(self):
        """The convention this round copied, pinned so the two files cannot
        drift apart again."""
        proc = self._run_blind(os.path.join("nuc", "tests", "test_prompt_budget.py"))
        out = proc.stdout + proc.stderr
        assert " failed" not in out, out[-2000:]
        assert re.search(r"\b5 skipped\b", out), out[-2000:]
        assert proc.returncode == 0, out[-2000:]

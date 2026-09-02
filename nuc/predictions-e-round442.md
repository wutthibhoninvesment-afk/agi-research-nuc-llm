# Round 442 (NUC-integration E) — PREDICTIONS, written before any fix is measured

House rule D-013. Written 2026-09-02, after diagnosis and BEFORE any line of
`nuc/` was edited and before any post-fix suite was run.

## What was already MEASURED before this file (stated, not predicted)

These are not predictions. They are this round's diagnosis, and they are here
so a later reader can tell the two apart:

- The NUC box is UNREACHABLE this round. Both documented paths failed once
  each: tailnet `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` → "Connection
  timed out"; LAN `192.168.1.37` → "Connection timed out", and the LAN key
  `~/.ssh/id_ed25519_nuc` does not exist on this host at all. Two SSH failures
  ⇒ CLAUDE.md's rule fires: no live NUC work this round, recorded and moving
  on to the offline half of track E.
- `nuc-health-check` has read **FAIL on every round from 410 to 441** — 32
  consecutive rounds, and `grep "nuc-health-check PASS" logs/driver.log`
  returns NOTHING. The check has never once been green since it was wired in.
- The three failures are always the same: `test_the_fast_check_runs_green_on_this_tree`,
  `test_agent_turn2_breaks_strict_but_not_snapshot`,
  `test_system_hint_is_a_token_prefix_for_nuc_mini`; the last two from
  `ModuleNotFoundError: No module named 'tokenizers'` at `nuc/kv_reuse_model.py:162`,
  the first because it shells out to `nuc/run_checks_fast.sh` and inherits them.
- `python3 -m pytest nuc/tests` run from inside a ROUND is **794 passed, 0
  failed, 0 skipped**. The same suite under `/usr/bin/python3` is **2 failed,
  787 passed, 5 skipped**. Both interpreters are 3.12.3 and both have pytest
  9.1.1; only the venv has `tokenizers==0.23.1`.
- Mechanism: `claude-wrapper.sh` does `source .venv/bin/activate`, so the
  ROUND runs under `/home/pgain/agi-research-nuc-llm/.venv/bin/python3`.
  `run_driver.sh` does not: it only appends `node_modules/.bin`, and the
  health checks are launched from the driver's own shell. The live driver
  process (pid 680210) has `VIRTUAL_ENV=/home/pgain/agi-research-nuc-llm/.venv`
  set but **no `.venv/bin` anywhere on `PATH`** — a half-activated venv. So
  bare `python3` in `nuc/run_checks_fast.sh` resolves to `/usr/bin/python3`.
- `.venv/pyvenv.cfg` says `include-system-site-packages = false`, and the venv
  holds 23 packages. There is no `requirements.txt`, no `pyproject.toml` and
  no `setup.py` at the repo root: nothing declares `tokenizers` as a dependency.
- All four health scripts (`harness/`, `languages/whence/`, `skills/`, `nuc/`)
  call bare `python3`. The exposure is identical; only `nuc/` has a venv-only
  import, so only `nuc/` is red.

## Predictions

### A. The interpreter fix (fix A — `nuc/run_checks_fast.sh` resolves its own python)

- **A1.** With `.venv/bin` absent from `PATH` (the driver's exact condition),
  the fixed script picks `.venv/bin/python3` and exits **0**.
- **A2.** Its pytest leg reports **794 passed, 0 skipped, 0 failed**.
- **A3.** The interpreter line I add does NOT disturb
  `driver_health.classify_nuc_health_log`: the classified `outcome` is
  `"pass"`, `legs` is `{"pytest": 0, "audit": 0}`, and `summary` still names
  both legs (the pytest count line and the `constant-audit ...` line).

### B. The skip-guard fix (fix B — missing `tokenizers` skips, not errors)

Measured by forcing `NUC_CHECK_PYTHON=/usr/bin/python3`, i.e. asking what the
check would have said for the last 32 rounds had fix B existed alone.

- **B1.** Outer run (no `NUC_FAST_CHECK_NESTED`): **787 passed, 7 skipped, 0
  failed**. 7 = the 5 existing `test_prompt_budget.py` skips + the 2
  `test_kv_reuse_model.py` tests that currently error.
- **B2.** Nested run (`NUC_FAST_CHECK_NESTED=1`): **786 passed, 8 skipped, 0
  failed** — same 794 total, plus `test_the_fast_check_runs_green_on_this_tree`
  itself skipped by its recursion guard.
- **B3.** The script exits **0** under the system interpreter. This is the
  claim that matters: fix B alone would have turned 32 red rounds green.

### C. Both fixes together, and the next driver round

- **C1.** Under the driver's PATH, `bash nuc/run_checks_fast.sh` exits 0,
  prints `nuc-checks PASS`, and reports 794 passed / 0 skipped (fix A wins
  the interpreter, so fix B never fires).
- **C2.** Round 443's driver line reads `nuc-health-check PASS` — the first
  PASS in the check's history.
- **C3.** Total wall time of `bash nuc/run_checks_fast.sh` after both fixes:
  between **120 s and 200 s** (round 388 measured 65.6 s at 490 tests; the
  suite is 794 tests now and the round-441 log shows 150.5 s).

### D. Scope of the same defect elsewhere

- **D1.** Exactly **2** files under `nuc/` (excluding `nuc/fast_lane/colibri-c/`,
  which is vendored upstream C tooling and never run by the suite) import a
  venv-only package, and the package is `tokenizers` in both:
  `nuc/kv_reuse_model.py` and `nuc/prompt_budget.py`.
- **D2.** `skills/run_checks_fast.sh` exits **0** under `/usr/bin/python3` —
  it is exposed to the same PATH defect but does not trip on it.
- **D3.** A static import scan of `harness/` and `languages/whence/` finds
  **zero** imports of any of the 23 venv-only distributions, so those two
  checks are green by luck of their dependency set, not by design. I will not
  spend 24 minutes running both suites to confirm; the scan is the evidence
  and I will say so.

### E. Honest uncertainty

- **E1.** I am NOT confident about C3's lower bound; 120 s assumes this box is
  as loaded as it was in round 441. If it lands outside 120-200 s I will score
  it a miss rather than widening the band afterwards.
- **E2.** I am NOT confident that A2 is 794 rather than 793 or 795 — the suite
  count has moved before (630 at round 410, 786 by round 441) and any round
  can add a test between my diagnosis and my measurement.

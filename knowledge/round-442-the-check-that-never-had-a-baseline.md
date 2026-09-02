# Round 442 (NUC-integration E) — the check that never had a baseline

**One line:** `nuc-health-check` reported FAIL on all 32 rounds from 410 to
441 and PASS on none of them, because the driver runs the health checks under
`/usr/bin/python3` while every round runs under `.venv/bin/python3`, and the
one optional dependency that differs between them raised where a sibling test
file had always skipped.

---

## 1. The box is down, and that is the first finding

Both documented paths failed, once each:

```
$ ssh -o ConnectTimeout=15 -i ~/.ssh/id_ed25519 jab@100.78.44.111
ssh: connect to host 100.78.44.111 port 22: Connection timed out
$ ssh -o ConnectTimeout=12 -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37
Warning: Identity file /home/pgain/.ssh/id_ed25519_nuc not accessible: No such file or directory.
ssh: connect to host 192.168.1.37 port 22: Connection timed out
```

CLAUDE.md: "If SSH fails twice in a row, record the failure and exit cleanly."
Two failures, recorded. No live NUC work this round; everything below is the
offline half of track E.

Two coordinates worth pinning while they are in front of me, because the LAN
line in CLAUDE.md reads as though it were merely conditional:

- **The LAN path is not merely unreachable from this host, it is
  unusable.** `~/.ssh/id_ed25519_nuc` **does not exist on this box at all.**
  CLAUDE.md already scopes that path to "Mac-adjacent hosts only", which is
  correct, but the failure a reader will actually see is a missing key file,
  not a routing timeout. This host is `srv1244884` at tailnet
  `100.85.110.121` — a tailnet host with no LAN route to `192.168.1.0/24`.
- So the tailnet path is the ONLY path from here, and it timed out. The box
  is down or asleep, continuing the pattern round 436 recorded.

## 2. A health check that has never been green

`nuc/run_checks_fast.sh` was built by round 388 and wired into `run_driver.sh`
by round 409. Its first verdict was round 410's. Every verdict since:

```
$ grep -o "round [0-9]*: nuc-health-check \(PASS\|FAIL\)" logs/driver.log | uniq -c
      1 round 410: nuc-health-check FAIL
      ... (one line per round, all FAIL) ...
      1 round 441: nuc-health-check FAIL
$ grep -c "nuc-health-check PASS" logs/driver.log
0
```

**Thirty-two consecutive FAILs and not one PASS.** The check has never had a
green baseline, which means for its whole life it could not distinguish "still
broken" from "newly broken" — the only service a per-round health check
provides. Five track-E rounds ran inside that window (412, 418, 424, 430, 436)
and `grep -niE "tokenizers|nuc-health-check|ModuleNotFound|interpreter|venv"`
over their five knowledge files returns **nothing**. Nobody looked.

The three failures were byte-identical every round:

```
FAILED nuc/tests/test_constant_audit.py::test_the_fast_check_runs_green_on_this_tree
FAILED nuc/tests/test_kv_reuse_model.py::test_agent_turn2_breaks_strict_but_not_snapshot
FAILED nuc/tests/test_kv_reuse_model.py::test_system_hint_is_a_token_prefix_for_nuc_mini
```

with the proximate cause visible in the log all along:

```
    def tokenizer():
>       from tokenizers import Tokenizer
E       ModuleNotFoundError: No module named 'tokenizers'
nuc/kv_reuse_model.py:162: ModuleNotFoundError
```

## 3. Why nobody reproduced it: the round and the check are different programs

The first thing I did was run the suite. It passed:

```
$ python3 -m pytest nuc/tests -q
794 passed in 84.35s
```

That is the trap, and it is why this survived 32 rounds. Any round that
checked by hand saw green and moved on. The two runs are not the same run:

| | interpreter | pytest | `tokenizers` | result |
|---|---|---|---|---|
| a ROUND (`claude-wrapper.sh`) | `.venv/bin/python3` | 9.1.1 | 0.23.1 | 794 passed, 0 failed |
| the CHECK (`run_driver.sh`) | `/usr/bin/python3` | 9.1.1 | **absent** | 2 failed, 787 passed, 5 skipped |

Same tree, same Python 3.12.3, same pytest. The mechanism:

```
$ cat claude-wrapper.sh
cd /home/pgain/agi-research-nuc-llm
source .venv/bin/activate            # <-- the ROUND gets the venv
export PATH="$PWD/node_modules/.bin:$PATH"
node_modules/.bin/claude "$@"

$ grep -n "PATH=" run_driver.sh
17:export PATH="$PATH:/home/pgain/agi-research-nuc-llm/node_modules/.bin"   # <-- and nothing else
```

`run_driver.sh` launches the four health checks from its own shell
(`bash "$NUC_HEALTH_SCRIPT" &`), which never activates the venv. Reading the
live driver process confirms the exact shape:

```
$ tr '\0' '\n' < /proc/680210/environ | grep -E "^(PATH|VIRTUAL_ENV)"
VIRTUAL_ENV=/home/pgain/agi-research-nuc-llm/.venv
PATH=...node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:...
```

**`VIRTUAL_ENV` is set and `.venv/bin` is nowhere on `PATH`.** A half-activated
venv: every tool that trusts `VIRTUAL_ENV` believes it is in the venv, and
bare `python3` resolves to `/usr/bin/python3`. That is the whole bug.

`.venv/pyvenv.cfg` says `include-system-site-packages = false`, so the two
interpreters share nothing; the venv's 23 packages include `tokenizers==0.23.1`
and the system's do not. **Nothing declares it** — there is no
`requirements.txt`, no `pyproject.toml` and no `setup.py` at the repo root.
`tokenizers` is an undeclared optional dependency that one interpreter happens
to have.

## 4. The defect is a disagreement, not a missing package

The missing package alone would have been harmless, because this tree already
knew `tokenizers` was optional. `nuc/tests/test_prompt_budget.py` has carried
this since round 22:

```python
try:
    import tokenizers
    HAVE_TOK = os.path.exists(pb.TOKENIZER_JSON)
except ImportError:
    HAVE_TOK = False
needs_tok = pytest.mark.skipif(not HAVE_TOK, reason="tokenizers lib or tokenizer.json missing")
```

Five tests there skipped cleanly under the system interpreter for 32 rounds.
`nuc/kv_reuse_model.py` imported the same optional package with no guard, and
its two consumers raised. **The same fact about the same environment produced
a SKIP in one file and an ERROR in the next.** That disagreement is what made
the check unable to go green, and it is the more general lesson: an optional
dependency is only optional if every consumer agrees it is.

## 5. Two fixes, deliberately kept separate

Either fix alone turns the check green. That is exactly why both are here:
whichever one you keep alone, the other defect stays and is now invisible.

**Fix A — `nuc/run_checks_fast.sh` resolves its own interpreter.** Preference
order `$NUC_CHECK_PYTHON` → the repo's `.venv/bin/python3` → bare `python3`,
each candidate accepted only if it can actually `import pytest`, and the
choice `export`ed so the nested run inherits it instead of re-resolving. The
script now prints, as its first line:

```
nuc-checks interpreter: /home/pgain/agi-research-nuc-llm/.venv/bin/python3 (tokenizers present)
```

The venv is not an arbitrary preference: `nuc/prompt_budget.py`'s docstring
has said "run under the hermes venv python, which has `tokenizers`" since
round 22. The check was disagreeing with its own subsystem's documentation.

The usability test checks for a printed sentinel rather than an exit status,
because `/bin/true` is executable and exits 0 for any argv — an exit-status
test accepts it as a Python interpreter and swaps a confusing failure for a
worse one. There is a test for that specific input.

**Fix B — the missing dependency SKIPS.** `kv_reuse_model.have_tokenizer()`
now exists and `nuc/tests/test_kv_reuse_model.py` marks its two
tokenizer-dependent tests with the same `needs_tok` shape
`test_prompt_budget.py` already used. On any interpreter without the library,
the suite is now yellow, not red.

## 6. Measured, in the order the fixes were made (D-013)

Predictions in `nuc/predictions-e-round442.md`, written before any file was
edited. **Fix B was measured ALONE, before fix A existed**, so fix A could not
mask it:

```
### fix B only, system interpreter
$ /usr/bin/python3 -m pytest -q nuc/tests
787 passed, 7 skipped in 76.65s
$ NUC_FAST_CHECK_NESTED=1 /usr/bin/python3 -m pytest -q nuc/tests
786 passed, 8 skipped in 28.39s
### fix B only, driver PATH (.venv/bin stripped) -> python3 = /usr/bin/python3
$ env PATH="$DRIVER_PATH" bash nuc/run_checks_fast.sh; echo $?
787 passed, 7 skipped in 63.60s
constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk
nuc-checks PASS (pytest rc=0, audit rc=0)
0
```

**Fix B alone would have turned all 32 red rounds green.** Both fixes, under
the driver's exact PATH:

```
$ env -u NUC_CHECK_PYTHON PATH="$DRIVER_PATH" bash nuc/run_checks_fast.sh; echo $?
nuc-checks interpreter: /home/pgain/agi-research-nuc-llm/.venv/bin/python3 (tokenizers present)
802 passed in 95.69s (0:01:35)
constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk
nuc-checks PASS (pytest rc=0, audit rc=0)
0
```

(794 at the moment A2 was measured; 802 after this round's own 8 new tests.)

And the line the driver would log, from the real classifier rather than from
my reading of it:

```
$ python3 -m harness.driver_health nuc_health_line "round 442: nuc-health-check" logs/nuc_r442_final.log 0
round 442: nuc-health-check PASS (802 passed in 95.69s (0:01:35); constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk)
```

(The 794/84.37s pair above is `logs/nuc_r442_bothfixes.log`, taken before
this round's own 8 tests existed; `logs/nuc_r442_final.log` is the tree as
committed. Both are on disk so either command can be re-run.)

`classify_nuc_health_log` returns `outcome: "pass"`, `legs: {"pytest": 0,
"audit": 0}`, and a `summary` still naming both legs — the added line does not
disturb it.

## 7. The pin, and the falsification that made it worth keeping

`nuc/tests/test_run_checks_interpreter.py`, 8 tests, 5.9 s. Every test that
invokes the script passes `--collect-only -q`: that reaches the real
resolution and audit code for ~1.2 s instead of ~86 s, and cannot recurse,
because `--collect-only` collects `test_the_fast_check_runs_green_on_this_tree`
without running it. The missing-dependency tests block `tokenizers` with a
`sys.meta_path` finder rather than by picking a real interpreter that happens
to lack it, so they state the same fact on any host.

Then I broke each fix and checked the tests noticed:

| reverted | test that went red |
|---|---|
| fix A (bare `python3` back in the pytest leg) | `test_the_script_never_calls_a_bare_python3_again` |
| fix B (`@needs_tok` markers deleted) | `test_kv_reuse_tests_skip_rather_than_error_without_tokenizers` |

Both files restored byte-identically (md5 compared), 8 passed again.

**The falsification found something I had not predicted.** Reverting fix A did
NOT trip `test_it_prefers_the_repo_venv_when_path_does_not_have_it`, the
behavioural test written for exactly that regression. The resolution code
still ran, so the script still *printed*
`nuc-checks interpreter: .../.venv/bin/python3` — while the pytest leg ran
under a different interpreter entirely. The behavioural test read the
announcement and believed it. Only the static test, which reads the script's
own source for a bare `python3` in command position, caught it.

That is worth stating plainly, because it argues against my own instinct: a
check that reports what it did is more trustworthy than one that does not, but
the report is not evidence, and a test that reads the report is testing the
report. The partial regression — announce one interpreter, run another — is
strictly worse than the original bug, and behavioural testing alone would have
shipped it.

## 8. Prediction scoring — 8 HIT, 3 MISS, 1 PENDING of 12

Banked in `nuc/predictions-e-round442.md` before any file was edited: **8 HIT, 3 MISS, 1 PENDING of 12**.

| # | prediction | outcome |
|---|---|---|
| A1 | picks `.venv/bin/python3` under driver PATH, exit 0 | **HIT** |
| A2 | 794 passed, 0 skipped, 0 failed | **HIT** (exactly, at measurement time) |
| A3 | classifier unaffected; `pass`, legs `{0,0}`, both legs in summary | **HIT** |
| B1 | outer, system python: 787 passed / 7 skipped / 0 failed | **HIT** (exact) |
| B2 | nested: 786 passed / 8 skipped / 0 failed | **HIT** (exact) |
| B3 | script exits 0 under the system interpreter | **HIT** |
| C1 | both fixes, driver PATH: exit 0, PASS, 794/0 | **HIT** |
| C2 | round 443 logs the first-ever `nuc-health-check PASS` | **PENDING** — round 443 has not run; unverifiable this round and NOT claimed |
| C3 | wall time 120–200 s | **MISS** — 86 s, then 96 s. Both below the band |
| D1 | exactly 2 files under `nuc/` import a venv-only package | **MISS** — 4 |
| D2 | `skills/run_checks_fast.sh` exits 0 under `/usr/bin/python3` | **MISS** — exits 1 |
| D3 | zero venv-only imports in `harness/` and `languages/whence/` source | **HIT** |

**C3** is the miss I pre-flagged in the bank's own §E1 as the shaky line, and
I said I would score it a miss rather than widen the band afterwards, so:
miss. The cause is legible and it is round 434's lesson again — `nproc` on
this box is 1, and round 441's 150.5 s was measured with three other pytest
suites running concurrently. My band was built from a contended measurement
and applied to a solo one. **The right reading is not "the check got faster";
it is that the driver's own concurrent numbers are ~1.6x its solo numbers and
neither is a runtime.**

**D1** missed 2-for-4: I counted the two modules I had already read and forgot
to scan for the rest. The extras are `nuc/fast_lane/upstream/convert_olmoe_merged.py`
(`huggingface_hub`) and `test_prompt_budget.py` (which imports `tokenizers`
only to build its own guard). The functional claim — two modules on the
suite's import path — held; the claim I actually wrote did not.

**D2 is the interesting miss, and it is wrong in a way I did not anticipate at
all.** I predicted the skills check would pass under the system interpreter,
reasoning that only `nuc/` has a venv-only import. It exits 1:

```
unit_tests  ERROR rc1   3 failed, 891 passed in 154.45s
```

My first reading was that the skills check is interpreter-sensitive too. It is
not — I ran the same suite under both interpreters and got **identical
failures**:

```
FAILED .../test_carryforward_check.py::TestLiveCorpus::test_the_live_ledger_accounts_for_every_bank_on_disk
FAILED .../test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean
FAILED .../test_xref_check.py::TestLiveBaselineIsHonest::test_the_live_corpus_has_no_unacknowledged_dangling_citation
```

Both failures name **this round's own unfinished work**:

```
K001 nuc/predictions-e-round442.md: round 442 banked predictions and
     state/prediction-bank-ledger.json has no entry for it
X004 nuc/run_checks_fast.sh:86: DANGLING path
     'nuc/tests/test_run_checks_interpreter.py' does not exist
```

Both checkers were exactly right. I had banked predictions without a ledger
entry (D-013's second half, which is what round 369 built `carryforward_check`
to catch), and I had written a comment citing a test file I had not written
yet. Both are resolved in this commit. **The skills check is dirty-tree
sensitive, not interpreter sensitive**, and had I stopped at the first reading
I would have reported a second interpreter bug that does not exist. The
measurement that saved it was running the suite under BOTH interpreters
instead of only the one that failed.

## 9. What this round did NOT fix, and who owns it

**All four health checks call bare `python3`** — `harness/run_tests_fast.sh`,
`languages/whence/run_tests_fast.sh`, `skills/run_checks_fast.sh` and this
one. The exposure is identical. `nuc/` was simply the only one importing a
venv-only package, so it was the only one that ever went red:

```
venv-only distributions: filelock fsspec hf_xet huggingface_hub nodeenv pyright tokenizers tqdm
harness/          : 0 files importing any of them
languages/whence/ : 0 in source (2 hits are vendored pip inside nested venvs)
```

The other three are green **by luck of their dependency set, not by design**.
The moment any of them grows a venv-only import it inherits this exact
32-round failure mode, with no test to catch it, because I fixed `nuc/` only.

I did not edit `run_driver.sh`, which is where the real fix belongs (one
`source .venv/bin/activate`, or an explicit interpreter for all four checks).
That file is harness(A)'s artifact — the same handoff round 388 made when it
wrote `nuc/run_checks_fast.sh` and left the driver wiring to round 409, and
the same one round 242 made to round 247. Handed to harness(A), with the
evidence above.

I did NOT run the harness or whence suites under the system interpreter to
confirm they pass there: that is ~24 minutes on a 1-core box for a question a
static import scan answers. The scan is the evidence and I am labelling it as
such rather than as a run.

## 10. Files

| file | change |
|---|---|
| `nuc/run_checks_fast.sh` | interpreter resolution, sentinel-based usability test, `nuc-checks interpreter:` line, all legs on `$NUC_PY` |
| `nuc/kv_reuse_model.py` | `TOKENIZER_JSON` constant, `have_tokenizer()` |
| `nuc/tests/test_kv_reuse_model.py` | `needs_tok` marker on the two tokenizer-dependent tests |
| `nuc/tests/test_run_checks_interpreter.py` | NEW — 8 tests pinning both fixes |
| `nuc/predictions-e-round442.md` | NEW — D-013 bank |
| `state/nuc-missions.md` | round 442 addendum |
| `state/prediction-bank-ledger.json` | round 442 entry (D-013 second half) |
| `logs/nuc_r442_final.log` | the passing run, driver PATH |

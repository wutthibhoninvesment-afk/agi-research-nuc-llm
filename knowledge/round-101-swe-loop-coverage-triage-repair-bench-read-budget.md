# Round 101 — SWE-loop(D): coverage triage, a repair benchmark from mutants, and the read budget

**Status of this file:** written incrementally during the round (the last
four D rounds died mid-flight with nothing scoreable). Sections marked
`[PENDING]` are filled as their stage finishes; if one is still pending when
you read this, the round died there and `state/swe/round-101/campaign.json`
says exactly where.

**Artifacts.** `harness/swe/coverage.py` (settrace line coverage without the
`coverage` package; executable lines from `dis.findlinestarts`; per-def
summary; mutant triage covered/uncovered + the killed-on-uncovered
instrument self-check), `harness/swe/repair.py` (killed mutants injected as
bugs → model repair from the failing-test signal → scored green / localized /
exact, cheating detected), `harness/swe/regiontools.py` `CallBudget` +
`BudgetedTool` (a hard, shared call budget for the read tools),
`agentloop.AgentConfig.wrap_up_on_max_steps` (one tool-less "answer now"
call when the step budget dies), campaign stages `coverage` + `repair`, a
merge-safe campaign manifest (two processes can drive different stages of
one campaign), `include_examples` on the corpus stage (fixes round-29's two
red campaign tests), `Mutant.end_lineno`. Tests: `test_swe_coverage.py` (7),
`test_swe_repair.py` (6), `test_round101.py` (7), `test_swe_campaign.py`
(+3). Predictions: `state/round-101-predictions.md` (banked before any
measurement).

Run: `cd harness && python3 -m swe.campaign --out ../state/swe/round-101
--workers 5 --live-kill 8 --live-repair 6 --read-budget 12` ·
`python3 -m swe.coverage --files whence/interp.py --mutation-json m.json` ·
`python3 -m swe.repair --mutation-json m.json --n 6 --out dir --read-budget 12` ·
`python3 -m swe.review review --out dir --max-steps 30 --read-budget 12`.

## 1. Inheritance audit
- Rounds 32–99 never ran: the driver log is 68 consecutive `error:429`
  entries (rate limit), ~45 s apart. Round 100 (NUC E4) ran; round 101 is the
  first D round since 29.
- **Round 29's mutation baseline DID finish and nobody read it.**
  `state/mutation/round-029-interp.json`: v0.8 `interp.py`, 891 mutants,
  841 killed + 8 timeouts (counted killed) = **95.3 %**, 42 survivors,
  wall 2250 s at 5 workers. Its campaign directory holds only
  `extra-programs.json`; the round died before `recheck`. Its predictions
  are scored in §8.
- `test_swe_campaign.py` had two red tests (round 31 called it "the
  selection bug, reserved for round 35"): `stage_corpus(corpus_n=0)` is not
  "no corpus" — `K.corpus` always prepends the checked-in examples, and
  v0.9's examples kill both fixture mutants (`r == 0` zero guard and
  `peak_depth = 0`). Fixed structurally: `include_examples` switch on the
  stage (+ `--no-examples`), tests state what corpus they mean.
- The Whence checkout is v0.9 (round 30): `interp.py` 2227 lines → **1056
  mutants** (ifneg 344, cmp 234, const 229, arith 99, bool 78, not 72), up
  from 891; the suite is 506 tests / 48 s idle (round 29 measured 20 s for
  465 tests; the direct-mode and time-travel tests are the difference).
- Standing checks at round start: whence 506 green (48 s); harness 325 green
  + the 2 reds above (26 min under the mutation load); nested `claude -p`
  auth OK (sonnet-5, $0.045/probe).

## 2. What was built and why

### 2a. Coverage triage (`swe/coverage.py`)
A survivor is either a **test gap** (the suite never executes the line) or a
**weak assertion / equivalent mutant** (the line runs; nothing observes the
change). The score lumps them; the remedies differ; the corpus search should
be spent on the first kind. No `coverage` package on this machine, so:
`pytest.main` runs in a subprocess after `sys.settrace` installs a global
callback that returns a line tracer only for code objects whose
realpath-normalised filename is a target (one dict lookup per call event;
the alias `co_filename → realpath` is cached, which matters on macOS where
`/var` is a symlink to `/private/var`). Executable lines come from
`dis.findlinestarts` over the compiled module recursively, so the
denominator excludes blank lines, comments and docstring continuations; the
def line itself is excluded from a function's body count (it executes at
import, which says nothing about the function being called).

Ground-truth self-check: **a mutant on an unexecuted line must survive**. The
campaign reports `killed_on_uncovered`; any non-zero value is an instrument
error (multi-line expressions are the known case), never hidden.

### 2b. Repair benchmark (`swe/repair.py`)
Rounds 5–29 measured the model as finder (review precision) and killer
(survivor kill rate); nothing measured it as a *fixer* against a known
answer. The campaign owns 1000+ such answers: every killed mutant is a
one-token defect with a failing test and an exact fix. So: inject the
mutant into a scratch copy, capture `pytest -x` (last 40 lines + failing
test ids) as the CI signal, give the model region tools + `edit_file` +
`pytest` + `whence_run` + `oracle_check` sandboxed to the copy, and score:
- `green` — full suite passes in the copy AND nothing under `tests/` changed
  (a green suite obtained by editing tests is `cheated`);
- `localized` — the diff touches the mutated site ±3 lines *in the injected
  file's own numbering* (`generate()` re-unparses the module, so the
  checkout's line numbers do not apply; the site is found by diffing the
  identically-unparsed original against the mutant text);
- `exact` — `ast.dump(repaired) == ast.dump(original)`: the semantic revert,
  formatting ignored.
Sampling is round-robin over operators (a random sample is 1/3 `ifneg`).

### 2c. Read budget + wrap-up turn
Live review A (control, this round): sonnet-5, 30 steps, region tools, a
prompt line saying "keep at least half for oracle_check": **28 of 30 steps
were reads** (2 outline, 23 `read_file` windows ≈ the whole 2227-line file,
2 search, 1 whence_run), **1 `oracle_check`**, then `max_steps` with **no
answer at all** (claims 0, $0.49). Round 23 died on grep; round 29 fixed
grep with windows; the model then read every window. A visible budget is
not a budget. Two mechanisms, both harness-enforced:
- `CallBudget(n)` shared by outline/read_file/search: after n calls the
  read tools return an error naming what is left to do; the last three
  successful reads carry a `[read budget: k left]` footer.
- `AgentConfig(wrap_up_on_max_steps=True)`: when the step loop ends, one
  more completion with **no tools offered** and an "answer now" user turn;
  `stop_reason` stays `max_steps`, `final_text` gets the answer, tool calls
  the model still emits are ignored and traced.
Experiment B = same task with `--read-budget 12` + wrap-up (§5).

## 3. Mutation baseline, v0.9 `interp.py` `[PENDING]`

## 4. Coverage triage results `[PENDING]`

## 5. Live lane (sonnet-5)

### 5a. Review: control A vs read-budget B (same task, same 30 steps, same model)
| | A (round-29 design) | B (`--read-budget 12` + wrap-up) |
|---|---|---|
| reads (outline/read_file/search) | 2 / 23 / 2 = **27** | 1 / 7 / 4 = **12** (budget hit exactly) |
| `whence_run` / `oracle_check` | 1 / **1** | 7 / **11** |
| malformed tool blocks | 1 | 0 |
| stop | `max_steps`, **no answer** | `max_steps` → wrap-up answered (873 chars, JSON) |
| claims / confirmed | 0 / 0 (nothing to score) | 0 / 0 (explicit empty list) |
| wall / CLI cost | 250 s / $0.49 | 395 s / $0.86 |
| tokens in / out | 827k / 11.9k | 911k / 21.4k |

Same model, same file, same budget: the tool-enforced read budget moved
11× more effort into probing, and the wrap-up turn turned "died reading"
into a scoreable, honest answer. The interpreter is oracle-dry for this
model too — B probed block/statement compilation, builtin shadowing, mutual
tail recursion, `deep_eq`/`binop`, `num` parsing and the self_eval
differential, and reported *no* claim rather than a phantom one (the
prompt's "reports without a firing reproducer count against you" is doing
its job). B's one observation outside the oracles' reach was real:
`join([1, "ok", "ok3", 5], ",")` misses with `join: element 5 is not a
string` — the message prints the offending VALUE where a reader expects an
index (`join(["a", 7, "b"], "-")` → `element 7`). Confirmed by hand; see
§10 for what was done with it.

P7 scoring: `oracle_check ≥ 5` MISS for A / HIT for B; JSON emitted MISS
for A / HIT for B; claims 1–4 MISS for both (0); confirmed 0–1 HIT; the
precision bound is vacuous at 0 claims.

### 5b. Kill `[PENDING]`

### 5c. Repair `[PENDING]`

## 6. Standing campaigns `[PENDING]`

## 7. Scoring this round's predictions `[PENDING]`

## 8. Scoring round 29's banked predictions (never scored)
Against the round-29 log (P1–P3, v0.8) and this round's nearest
instantiation (P4–P10, v0.9 — version drift 891→1056 mutants flagged):
- P1 score 89–93 % → **MISS (high)**: 95.3 %, 42 survivors (predicted 60–100).
- P2 wall 25–50 min → HIT: 37.5 min.
- P3 3–10 timeouts → HIT: 8; "≥1 flips on serial recheck" → `[PENDING: this round's recheck]`.
- P4–P10 → `[PENDING]`.
- P10 (process: ≥1 own test wrong on first run) → HIT in round 101 too.

## 9. Key learnings `[PENDING — partial]`
1. **Read the artifacts the dead round left before planning.** Round 29's
   baseline was complete on disk for four rounds; every D stub since
   planned to "run the baseline".
2. **A budget the model can ignore is a suggestion.** The prompt said keep
   half the steps for probes; the trace shows 28/30 reads. Enforce budgets
   in the tools, and make sure a run that hits its ceiling still answers.

## 10. Honest failures / gaps `[PENDING — partial]`
- P12 confirmed: three of my own new tests were wrong on first run (trace
  file name uses `re.sub(r"\W", "_")` which also replaces the dot; assumed
  `test_lexer.py` never executes `interp.py` — it runs a whole program;
  assumed `corpus_n=0` means an empty corpus — the examples are always in).
- Mutation wall time far outside P2's window: the baseline shares six cores
  with the harness suite and its scratch-copy pytest runs; see §3.

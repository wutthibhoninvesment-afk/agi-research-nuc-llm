# Round 459 (skills B) — predictions, banked BEFORE measuring

Banked at HEAD `11780c5`, before any `claim_check --run`, before any edit to
`claim_check.py`, and before any of the fifteen corpus claims was re-derived
by execution. D-013.

**Subject.** Round 441 ran `claim_check --run` over the whole skills corpus
once — the only time it has ever run — and reported **15 stale `C002`
claims across 10 skills**, then wrote in its own §5: *"The fifteen stale
claims are reported, not corrected. Correcting them means re-running each
command solo on a quiet box and re-deriving the number, and a number written
from a contended run would be the same defect again."* This round is that
quiet box. `nproc` is 1 and every measurement below runs solo.

## Baselines — re-derived at HEAD this session, each with its command

| baseline | value at HEAD | command |
|---|---|---|
| corpus size | **86 skills** | `ls skills/*/SKILL.md \| wc -l` |
| commands in Verification blocks | **410** | `python3 skills/skill-authoring/scripts/claim_check.py skills/` |
| classified `auto` | **134** | same line |
| classified `manual` | **276** (unknown program 165, placeholder 52, mutating 23, expensive 18, bare `cd` 11, priced 3, network 2, environment 1, shell 1) | same line |
| commands actually executed, ever, on a schedule | **0 of 410** | same line, trailing `coverage … 0/410 commands` |
| commands `--run` would execute today | **89** | `claim_check.py --dry-run skills/ \| grep -c '^would run'` |
| static tier | **0 stale of 242 checked; 242/283 paths** | `claim_check.py skills/` |
| round 441's one and only sweep | **15 C002, 57 C003, 19 C004; 85 of 320 commands; 1104 s over 77 skills, contended** | `logs/claim_check_run_round_441.log` (`grep -c "STALE C002"`, `awk '/^TIMING/'`) |
| the 15 claim sites | **all 15 textually unchanged since round 441** — verified by `grep` before banking, so P1 below is scored on the RE-RUN, not on the text | `grep -n "165 passed" skills/bounded-not-binary-witness/SKILL.md` etc. |
| HEAD | `11780c5` | `git rev-parse --short HEAD` |
| cores | **1** | `nproc` |

## Predictions

**P1 — every one of round 441's 15 `C002` findings reproduces.** The text is
already known unchanged; what is NOT known is whether the *observed* side
still disagrees. A suite could have shrunk back onto its claim by
coincidence. Estimate: **15 of 15 still C002.**

**P2 — the re-run finds MORE than 15.** The corpus grew 77 → 86 skills and
320 → 410 commands in 18 rounds, and every new skill banks a fresh count that
has had 18 rounds to rot. Point estimate: **19 C002.** Falsified by ≤ 15.

**P3 — the rot has a direction, and it holds.** Round 441 found every count
UNDERSTATED. Predict at least **10 of the 15** observed values are now
strictly GREATER than round 441's observed value (not merely greater than the
claim), i.e. they grew again in 18 rounds. Falsified by ≤ 9.

**P4 — solo wall clock beats round 441's contended 1104 s despite a bigger
corpus.** Round 441 shared one core with its own session throughout; this
round runs the sweep with nothing else in flight. Point estimate: **700 s**
for all 86 skills at `--timeout 120`. Weakest line in this bank: the corpus
grew 12% and I am guessing the contention penalty was larger than that.
Falsified outside 450–1100 s.

**P5 — `skill-authoring`'s own Verification block is still the worst single
block**, by count of `C002`, as it was in round 441 (5 of 15). Estimate: **≥ 5
C002 in `skills/skill-authoring/SKILL.md` alone**, more than any other skill.

**P6 — `expiring-fixture-window:140`'s `203 passed` is still invisible.** It
is written as a bare output line under its command rather than a `#` comment,
so `parse_commands` reads it as a COMMAND and the claim as empty. Predict it
still yields `C003 UNQUANTIFIED` and not `C002`, and that it is still in
textual collision with `measured-budget-sizing:147`'s `179` for the same
command.

**P7 — at least one `auto` command exits non-zero.** Round 441 observed
`skill_lint --house --strict skills/` at `exit=1` against a claimed `exit=0`.
Estimate: **6 of the ~89 executed commands return non-zero.** Falsified by 0.

**P8 — at least one command hits the per-command timeout.** Round 441's
`fuzz-mutate-kill-loop` alone burned 400 s at `--timeout 90`, which means
multiple caps were struck. Predict **≥ 1 TIMEOUT at `--timeout 120`**, and
that `fuzz-mutate-kill-loop` is one of them.

**P9 — most of the fifteen are monotone and can be re-shaped as floors.**
Round 441's own observation is that these numbers "only ever grow". A `>= N`
claim survives every future test addition; an `== N` claim rots on the next
one. Predict **≥ 9 of the 15 are suite/corpus sizes that admit a floor**, and
that `claim_check.py` today understands **0** inequality claims — its
`METRICS`/`claim_metrics` pair parses a bare integer only. Falsified by ≤ 8.

**P10 — the sweep dirties no tracked path.** `git status --porcelain`
identical before and after, as round 441 also found. Untracked
`__pycache__`/`.pytest_cache` may appear and are gitignored. Falsified by any
tracked-file delta that is not this round's own edits.

**P11 — no basis, reported not guessed.** Whether any observed number went
DOWN since round 441 (a suite losing tests, or gaining a `deselect`), and
whether the whence checkout's `checkout_digest` moves as a side effect of the
sweep running whence pytest suites — which would silently reset the slow
tier for the next round. Both are recorded in the round file rather than
predicted here.

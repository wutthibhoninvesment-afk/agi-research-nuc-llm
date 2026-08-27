# Round 198 (language C) — reconcile rounds 192/194's self-hosting backlog; a live concurrent-writer anomaly found mid-round

## 1. What this round did

Inherited tree had two language(C) rounds' worth of real, tested, uncommitted
work stacked on top of each other:

- **Round 192** (self-hosting round 6): ran the guest evaluator on the guest
  lexer/parser's OWN real source (`self_host.lang`, ~680 lines) for the
  first time, not a hand-picked snippet. Found a bug 20+ rounds of fuzzing
  never caught — the guest's hand-copied `suppressed()` newline-
  continuation check only implemented the bracket-depth half of the real
  rule, missing the "newline after an operator/`=`/`:`/`,`/keyword is also
  a continuation" half. This is exactly the style `self_host.lang`'s own
  `check "label":\n  expr` test section uses, so the guest failed to parse
  its own test file. Fixed in both `self_host.lang` and `self_eval.lang`'s
  shared parser section; closed round 164's old `effects.lang` guest-parity
  backlog as a free side effect (same bug, same fix).
- **Round 194**: the why-shape differential fuzzer then found a dependent
  bug in round 176's earlier `sure()` guest delegation — `sure` on a
  plain (non-Guess) value must be a pass-through (no new provenance node),
  matching the host's own "already certain" no-op semantics; the guest was
  unconditionally synthesizing a fresh box. Fixed with a dedicated
  `apply_builtin` branch.

Both rounds self-verified everything live but left it uncommitted with no
knowledge file — see `knowledge/round-192-whence-self-hosting-round6-newline-continuation-bug.md`
and `knowledge/round-194-whence-guest-sure-passthrough-fix.md` for the full
retroactive writeups. This round re-verified from scratch (full 850-test
suite, all 3 touched examples, the new `test_self_hosting.py` in
isolation — all green), added SPEC.md documentation for both (a new
"Self-hosting round 6" bullet under §Records-as-data/self-hosting, and a
new "Round 194" bullet under §v0.15 guest parity), and committed the
6-file language(C) diff (`46de4a7`) plus a separate `state/round_counter`
bump (`3eaf50a`, covers both round 197's and this round's increments —
round 197 left its own bump uncommitted too).

Deliberately did NOT attempt round 192's own flagged next step (a
memory-scaling characterization of guest-eval cost, running larger slices
of `self_host.lang`'s 66-check test section through `run_src` — the
attempt that grew past 1.7 GB RSS and was killed) this round: the backlog
reconciliation itself was substantial, and manufacturing a new experiment
under time pressure right after a live concurrent-writer anomaly (§3)
seemed like the wrong tradeoff. Stays open as real, well-scoped backlog for
whichever language(C) round wants "self-hosting round 7."

## 2. Cross-track backlog, flagged not touched

Per this session's established convention (rounds 165/174/183/188/196 all
follow it), files outside language(C)'s scope were left alone:

- `harness/swe/{campaign,coverage,prioritize,repair}.py` + 3 test files —
  round 197's (SWE-loop D) own uncommitted work, still sitting in the tree
  at round-198 end. Not reviewed.
- `knowledge/round-155-swe-loop-stale-coverage-map-soundness-bug.md` +
  `state/swe/round-161/` — a much older SWE-loop(D) backlog item, tracked
  since round 155/161/179 per `research-state.md`'s harness(A) track entry
  (round 175: "deliberately left uncommitted... SWE-loop(D) scope").
  Unchanged this round.
- `languages/whence/whence_qwen_bridge.py` + `languages/whence/pyproject.toml`
  — already found and assessed by round 172 (NUC-integration E):
  "a from-scratch, undocumented, budget-unaware duplicate of E5's
  already-shipped `nuc/taskscript/`... left in place, not merged, not
  deleted." Still true; not re-litigated here. (`languages/whence/
  research-env/` is a real Python venv directory the same round 172 note
  mentions — confirmed still present, harmless, gitignored by pattern
  match on `venv`.)

## 3. New finding: a live, unrelated agent wrote files into this repo mid-round

While this round was running, two new files appeared in
`languages/whence/examples/` that this session never created:
`expense_tracker.lang` (birth 12:06:46 UTC) and `test_simple.lang`
(12:09:52 UTC). Neither matches this project's conventions in any way —
no `check` test assertions (every real example in this repo tests itself
this way), calls to builtins that don't exist in Whence's real builtin
list (`println`, `type()` — see SPEC.md's `## Builtins` section, neither
is there), and decorative emoji in output strings, a style absent from
every other file in `examples/`.

`ps aux` at the time showed a SECOND, distinct Hermes Agent gateway
process — `/home/pgain/.hermes-main/hermes-agent/venv/bin/python -m
hermes_cli.main gateway run --replace` (PID 764704, started 12:07 UTC,
still running as of this writing) — alongside the long-running pair from
`/home/pgain/.hermes/hermes-agent/` (PIDs 687207/687226, running since
Aug 26). The `.hermes-main` instance's start time lines up almost exactly
with the first mystery file's birth time. No second `claude` round process
was found (`ps aux | grep claude` showed only this session's own PIDs), so
this is not the concurrent-driver-race pattern memory already tracks
(that one is two `run_driver.sh`/`claude` invocations racing each other) —
it looks instead like a genuinely different, independently-running
autonomous agent (Hermes, per `CURRICULUM.md`'s own description of it as
the system that "consolidates" this program's output) treating this
working tree as a live sandbox while a language(C) round was mid-flight.

**Not touched**: these two files were excluded from both commits made this
round (`git add` targeted the exact 6+1 intended files each time, verified
via `git diff --cached --stat` immediately before committing — no `git add
-A`/`.` used anywhere this round). No test in this repo globs
`examples/*.lang`, so their presence does not affect `pytest`. Left in
place rather than deleted: unclear ownership, still possibly in-flight
from that other agent's own uncommitted session, and deleting another
process's live output without confirmation is exactly the kind of action
this program's own conventions (and the harness's broader safety
guidance) say to avoid. **Flagged for the user/operator directly, not a
finding for a future round to silently clean up** — a second autonomous
agent writing into this repo's working tree unannounced is worth knowing
about regardless of what track picks this up next.

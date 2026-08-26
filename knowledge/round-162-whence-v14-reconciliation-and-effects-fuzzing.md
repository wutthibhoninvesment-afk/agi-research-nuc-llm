# Round 162 (language C) — reconciling rounds 146 + 158, and closing the effect system's fuzz-coverage gap

## 1. Starting state (what `git status` actually showed)

Per this workspace's standing process rule ("check `git status` for
uncommitted prior-round WIP before starting"), the tree was dirty in
`languages/whence/`:

```
 M languages/whence/examples/self_eval.lang
 M languages/whence/examples/self_host.lang
 M languages/whence/tests/test_self_eval.py
```

`state/research-state.md`'s round log already documented these as round
158's own work (self-described scope: guest-side type-annotation parity),
deliberately left uncommitted by a 3-way concurrency agreement with rounds
157 (harness) and 159 (skills) sharing the tree at the time. That much was
already on record. What was NOT on record: running every example (the
standard first step of any language round) turned up `examples/effects.lang`
running clean with 4 checks — a whole language feature (an effect system)
that the track-status line, four lines above in the same file, called
"still fully unstarted." That contradiction is this round's real starting
point; see §2.

## 2. The orphaned round: 146's effect system

`git log` showed `examples/effects.lang` has been on `main` since commit
`c768d90` ("checkpoint: sync from Mac backup"), and `languages/whence/SPEC.md`
already has a complete, well-written "v0.14 (round 146) — effect system"
section — clearly authored contemporaneously with the actual work, not
retrofitted. Cross-referencing `state/FINAL-REPORT.md` (generated at a
false-positive quota stop right after round 146) confirmed the whole story:
round 146 built, tested (799 tests passing per that report), and committed
Whence v0.14 — but never got a `knowledge/round-146-*.md` file or a
`state/research-state.md` round-log entry, and the FINAL-REPORT's own
explicit "next round should start by committing round 146's work" note (it
was in fact already committed by the time of that report, just not the
paperwork) went unactioned for the 15 rounds between 147 and 161.

This is the SAME failure shape `state/research-state.md`'s own line 22 (in
the old FINAL-REPORT) names as the single most repeated meta-lesson of this
whole program: "the tree, not the state file, is the source of truth." It
had already happened three times to language(C) before this round (rounds
24, 108, 122-140) and was explicitly listed as recurring at round 146 too.
This round is the fourth instance's closure, not a new failure.

See `knowledge/round-146-whence-v14-effect-system.md` for the full technical
writeup (design rationale, mechanism, shallow-scope decisions, original
testing) — written this round, reconstructed from `SPEC.md`/`test_v14.py`/
`FINAL-REPORT.md`, then independently re-verified live (below) rather than
taken on faith.

## 3. Verifying and committing round 158's diff

Read the full diff before touching anything (`git diff -- languages/whence`).
It closes the OTHER standing backlog item — "self_eval.lang guest type-
checking parity gap" — cleanly:

- **Lexer:** `two_char_ops` gains `"->"` (both `self_eval.lang` and
  `self_host.lang`, kept byte-identical in their shared parser section per
  `test_parser_section_matches_self_host`).
- **Parser:** `parse_params` now threads a parallel `types` accumulator;
  `parse_typed_suffix(toks, pos, trigger)` handles both `:` (param) and
  `->` (return) with one function; `expect_type_name` validates against
  `guest_primitive_types` (`num str bool list record fn any` — no `shape`,
  since the guest never implemented shapes, an honest, already-flagged,
  separate gap); an unrecognized name is a guest `miss`, mirroring the
  host's own "unknown type" ParseError-shaped rejection but as the guest's
  native total-error idiom.
- **Erasure:** `build_guards`/`apply_type_guards` prepend one
  `let <param> = typed(<param>, spec, label)` per typed param to the body's
  statement list — a line-for-line mirror of the host's
  `_apply_type_guards`, done at PARSE time, so an untyped function's guest
  AST is byte-identical to before (no guards list == unchanged block node).
- **Evaluator:** a new `typed` builtin (propagate-miss-first, pass-through
  on match, one-input origin miss on mismatch — same decision order as the
  host) and `check_ret` (mirrors `_check_ret`: no-op when there's no
  `-> Type` or the body already missed, otherwise a fresh `"typed <label>"`
  origin miss wrapped, as always, by the ordinary `"call <name>"` node
  `apply_closure` already produces).
- **Folded into the same diff, attributed to round 156 in its own comments:**
  `show_callable` (mirrors the host's `Closure`/`Builtin` `show_payload`
  rendering — `"<fn %s>"` / `"<fn>"` / `"<builtin %s>"`) fixes two op-label
  divergences where a guest miss reason naming a function used to dump the
  closure's raw `@{__tag: "closure", ...}` record instead; a list-literal
  fix changes the op tag from a bare `"list"` to `"list %d items"`,
  matching the host's real `f_list` label (a bare tag diverged for EVERY
  list literal, not an edge case).
- **Tests:** `test_self_eval.py` grew 6 new differential corpus entries and
  2 new/tightened Python-level regression tests pinning the exact host
  label string for the callable-field-access case from both the `get()`
  and `.field` access paths.

Ran the full suite fresh (not trusting round 158's own "801 passed" self-
report without re-running it): **801 passed in 110.5s.** All 15
`examples/*.lang` still exit 0 (`self_eval.lang` 76/76, `self_host.lang`
60/60, up from 66/60 pre-158). Committed as-is — no code changes of my own
to these 3 files, only verification.

## 4. Full standing-checklist re-run (both reconciled pieces, from one clean base)

| Check | Seeds/params | Result |
|---|---|---|
| Host fuzz | seed 300 (400 progs), seed 301 (`--limit 6000`, 400 progs) | 0 crash signatures both |
| Oracle campaign (6 oracles) | seed 302 (200 progs), seed 303 (`--limit 6000`, 200 progs) | 0 finding signatures both |
| Guest differential (`self_eval`) | seed 400, seed 401 (200 progs each) | 0 finding signatures both |
| `bench/ref_diff.py` | all 15 examples × 3 modes (fast/direct/slow) | 0 differing (file,mode) pairs |
| `bench/reserve_probe.py --examples -n 30` | corpus max vs the CURRENT `HOST_RESERVE`=250 (the research-state.md backlog text's "350" is itself stale — corrected this round) | ran to completion (~14 min on this single-core NUC); 17 deep-templates max 94, all 15 examples ≤34 (`effects.lang`=0, `self_eval.lang` `need=0`/`peak=606`), 29/30 random fuzz-corpus items 0-1, **1/30 (`fuzz:1000028`) TIMEOUT at the search ceiling** — see note below |

Notes: `self_eval.lang`'s `peak=606` is `Interpreter.peak_depth` at
`HOST_RESERVE=0` (the probe's own per-program budget-search state, not a
warning) and is well inside a 6000-limit run — consistent with the guest
evaluator's known ~6.8× host-frames-per-guest-call overhead (documented
since round 14), not a new finding. `fuzz:1000028`'s `TIMEOUT` reads as
`need=351` only because `need()` reports `hi+1` for anything that never
resolves within the search range (`reserve_probe.py`'s own documented
convention: "an overflow even at the maximum, a crash, or a timeout: not
searchable — report it as such rather than as a need") — this is a single
randomly-generated program hitting the probe's 120s-per-subprocess wall-
clock cap somewhere in its ~10-probe binary search, not a claim that 351
host frames are actually required. A 1/30 timeout rate on freshly-seeded
fuzz input is unremarkable next to the oracle/fuzz campaigns' own routine
2-6% timeout rates (§4 above, all six 200-program oracle runs); not
re-investigated further this round (see §9).

All other numbers are consistent with round 110/144's prior readings on the
same corpus — no regression, just confirmation the tree is healthy after folding
in two rounds' worth of unreviewed work at once.

## 5. New finding: the fuzzer never generated `effects [...]` either

While re-reading `harness/swe/fuzz.py` to run the standing fuzz checklist, I
checked whether the grammar could produce an `effects` clause at all —
`grep -n effect harness/swe/fuzz.py` came back empty. This is exactly the
gap round 134 diagnosed for `: Type`/`-> Type` (`SPEC.md`'s own "Not done"
note at the time: "the grammar generated no `: Type`/`-> Type` annotations,
so type-guard code paths were only ever exercised by the hand-written
corpus, never by fuzz input"), now recurring for the effect system: 16
rounds since round 146, zero fuzz-generated `effects` coverage beyond the
20 hand-written tests in `tests/test_v14.py`.

### Fix

`harness/swe/fuzz.py`:
```python
EFFECT_TAG_SETS = ("[]", "[io]", "[net]", "[io, net]")

def maybe_effects(self):
    if self.r.random() < 0.3:
        return " effects %s" % self.r.choice(EFFECT_TAG_SETS)
    return ""
```
Wired into both function-definition sites (`statement()`'s named-`fn`
branch and `fnlike()`'s anonymous-`fn` branch), in the fixed order the SPEC
requires: `typed_params → maybe_effects → maybe_ret_type`. `net` is
deliberately never registered as a real effect tag (`_EFFECTFUL_BUILTINS`
only has `"io"`), so the tag pool fuzzes BOTH the real grant path
(`effects [io]` allowing `print`) and the "declared-but-unrelated-tag still
blocks" path (`effects [net]` still rejecting `print`) that
`test_effects_unrelated_tag_still_blocks_print` covers by hand today.

A generated body calling `print` directly inside an `effects []` function
now deterministically produces a host `ParseError` — this is NOT a new
crash class: `print` was already an ordinary `BUILTIN_ARITY` entry `call()`
could pick for any function body, and `ParseError`/`LexError` are already
first-class, handled outcomes throughout `fuzz.py` and `oracles.py` (every
existing seed already produces a substantial parse_error rate from other
causes — e.g. duplicate parameter names, malformed nesting).

### Verification

```
$ python3 -c "... ProgramGen(500).program() for 300 trials ..."
programs with effects clause: 101 /300
```
```
$ python3 -m harness.swe.fuzz --seed 500 -n 500
fuzz: 500 programs in 55.4s
  ok           423
  parse_error  65
  timeout      12
  unique crash signatures: 0
```
```
$ python3 -m harness.swe.oracles --seed 501 -n 200
oracle fuzz: 213 programs x 6 oracles in 147.8s
  totality ok 185 parse_error 24 timeout 4   (+5 more oracles, same shape)
  unique finding signatures: 0
```
0 crashes, 0 findings, against a grammar now generating `effects` clauses
in roughly a third of function definitions.

### Guest side: a deliberate no-op, one round earlier in its own arc

`harness/swe/guest.py`'s `GuestGen` inherits `ProgramGen` and does NOT
override `typed_params`/`maybe_ret_type` any more (round 158 closed that
gap for real). It WOULD, by default, inherit the new `maybe_effects` too —
but `self_eval.lang`/`self_host.lang`'s shared hand-copied parser section
has no `effects` contextual keyword at all. Tracing what would actually
happen: `parse_params` finishes, then `parse_typed_suffix(toks, pos, "->")`
checks for `"->"` and finds the NAME token `"effects"` instead, so it
returns "no return type" WITHOUT consuming anything; `parse_block` then
runs at that same position expecting `"{"` and instead sees `"effects"`,
producing a guest-native miss ("expected '{'"-shaped) for a program the
HOST either runs successfully or rejects with a REAL `ParseError` — either
way, a guaranteed divergence between the two sides for every `effects`-
bearing generated program, not a genuine language bug.

Added the no-op:
```python
def maybe_effects(self):
    return ""
```
with a docstring explicitly naming this as "one host-round earlier in its
own parity arc than type annotations were at round 134" — i.e. the natural
next language(C) backlog item is to do for `effects` what round 158 did for
`: Type`/`-> Type`. Verified 0/300 guest-generated programs contain
`"effects"` after the override.

## 6. Confirmed out of scope, left untouched

Four untracked paths appeared under `languages/whence/` that are NOT this
round's or any numbered round's work:
`pyproject.toml`, `research-env/` (a Python 3.12 venv), `.venv/`, and
`whence_qwen_bridge.py` (a `requests`-based bridge from Whence scripts to
the NUC's Qwen 3.6 API proxy at `127.0.0.1:8080` — the same port every
prior NUC-track round has already used, not the forbidden 8001).

Given the instruction to flag suspected prompt-injection before treating
untrusted content as fact, I checked ownership before deciding to leave
these alone rather than assume either "safe" or "malicious": `ps aux`
showed a `claude` process (PID 436644) alive since Aug 18, matching
`ListAgents`' `hive-45` peer session (interactive, tmux, started 8 days
before this round) — a long-lived, ordinary interactive Claude Code
session, not an injected or rogue actor. The `whence_qwen_bridge.py`
docstring's `Author: Jaby` line matches a real, previously-documented
identity: `LICENSE`/`SECURITY.md`/`DISCLAIMER.md` all separately attribute
Whence's human authorship to "Jaby (@wutthibhoninvesment-afk)", and
`knowledge/round-026-whence-v08-chain-walk-concurrent-writer.md` §(the
concurrent-writer incident) independently documents the SAME identity doing
the SAME kind of publish-prep work (a LICENSE file, "Copyright (c) 2026
Jaby") through a separate interactive session concurrently with an
autonomous round, over 130 rounds ago. Conclusion: genuine, pre-existing,
out-of-band human work, not a security concern — left completely untouched
(not read further, not edited, not committed), consistent with round 26's
own resolution ("LICENSE/README left untouched (not mine)").

Also present but out of this round's track: `harness/swe/{campaign,coverage,
prioritize}.py` (modified, SWE-loop(D)'s round-155 backlog per the existing
Open Questions entry) and `state/swe/round-161/` (untracked, no
corresponding round-log entry — an apparently-orphaned SWE-loop(D) round
this round did not investigate beyond noting its existence, since 161 mod 6
= 5 = SWE-loop(D) in the curriculum's rotation, consistent with it being
that track's own artifact and not a language(C) round mislabeled).

## 7. What got committed

One commit, touching exactly 5 files:
- `languages/whence/examples/self_eval.lang` (round 158's diff, verified)
- `languages/whence/examples/self_host.lang` (round 158's diff, verified)
- `languages/whence/tests/test_self_eval.py` (round 158's diff, verified)
- `harness/swe/fuzz.py` (this round: `maybe_effects`)
- `harness/swe/guest.py` (this round: `GuestGen.maybe_effects` no-op,
  updated docstring)

Everything else identified above (other tracks' backlogs, the user's own
publish-prep files) was deliberately left out of the commit.

## 8. Updated standing record

`state/research-state.md`: language(C) track-status line now reads v0.14
(was v0.13), with a new summary paragraph covering rounds 146/158/162
prepended ahead of the existing round-144 summary (kept for history, not
deleted). Backlog item 1 ("effect system... still fully unstarted") is
resolved and replaced with "AI-native primitives is the one remaining
curriculum feature slot." Backlog item 2 is now the fresh `effects`
guest-parity gap this round found and flagged (renumbering the rest of the
list by one). Two new round-log entries added: round 146 (retroactive,
marked as finalized by round 162) and this round.

## 9. Honest gaps

- `bench/reserve_probe.py --examples -n 30` took ~14 minutes to run to
  completion on this single-core NUC host (~10 fresh-process subprocess
  spawns per binary-search probe, ~62 programs total counting deep-
  templates + examples + random corpus) — ran it as a genuine background
  task rather than inside one blocking foreground call, and it did finish.
  One random fuzz-corpus item (`fuzz:1000028`, 1/30) timed out at the
  search ceiling — read as ordinary fuzz-input noise (§4), not chased
  further with a fixed seed/shrink this round; if it recurs on a specific,
  reproducible seed in a future round, that would be worth `--show`-ing
  and shrinking to confirm it's a slow-but-finite computation rather than
  a genuine hang.
- The new `effects` guest-parity gap (§5) is flagged, not closed — real
  guest support (teaching `self_eval.lang`/`self_host.lang`'s parser an
  `effects` contextual keyword, ideally with an actual per-tag check
  mirroring `_check_effect_call` rather than just skip-and-ignore) is
  scoped as the next language(C) round's natural first item, matching how
  `: Type`/`-> Type` took two rounds (134, then 158) to go from
  fuzz-generated to guest-verified.
- AI-native primitives (the one remaining curriculum "advanced feature"
  slot) still has no settled scope — not attempted this round, which spent
  its budget on reconciliation instead of new feature design; flagged as
  the next round's design question, not deferred silently.

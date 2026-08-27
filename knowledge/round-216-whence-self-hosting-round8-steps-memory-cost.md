# Round 216 (language C) — self-hosting round 8: falsifying a memory-regression hypothesis, finding the real cause, first full 66/66-check self-hosting completion

## 0. Session state on arrival

`check_round_recorded.py --since 210` showed no unreconciled backlog for
language(C) — round 212 had cleanly closed round 210's seed-152/seed-4002
guest-parity work, and rounds 213/214/215 (skills(B)/NUC(E)/SWE-loop(D))
each landed clean. `ps aux` showed no concurrent peer round. `git status`
was clean except the always-present untouched Hermes-gateway files
(`whence_qwen_bridge.py`, `pyproject.toml`, two example `.lang` files) —
left alone per `project_hermes_gateway_shares_the_repo` / the standing
cross-track file-ownership convention.

With no reconciliation owed, this round picked the one narrowly-scoped,
concrete open thread still on language(C)'s own backlog: round 204's
`bench/self_host_memscale.py` table showed checkpoint 66 (the FULL 66-check
`self_host.lang` test section, run through `self_eval.lang`'s guest-level
`run_src`) blocked only by a 180s wall-clock timeout, explicitly noting
"memory NOT the blocker (60-checkpoint trend puts it well under 700 MB)."
No round since had gone back to actually finish that run.

## 1. First finding (and a false start): checkpoint 50 now fails at 700 MB, not 310 MB

Re-running `bench/self_host_memscale.py --cap-mb 700` (round 204's own
defaults) immediately diverged from round 204's own table: checkpoint 45
matched almost exactly (238.8 MB now vs 234 MB then — well within the
noise round 204 itself flagged), but checkpoint 50 failed outright —
`MEMORY_ERROR` at 703.1 MB, where round 204 reported 310 MB for the
identical checkpoint. A ~2.3x jump for byte-identical checkpoint content.

**First hypothesis**: round 210/212's `GUEST_MAX_DEPTH` depth-guard fix
(closing the seed-4002 guest-store-corruption bug) added guest-level
bookkeeping to `apply_closure` — `let a = alloc(merge(st, @{gd: st.gd +
1}))` on entry, `merge(r.st, @{gd: st.gd})` on exit — turning what was
previously ONE `merge`/call (inside `alloc`) into THREE. Since every
`merge`/`put` on the immutable, provenance-retaining store creates a new,
permanently-reachable `Record` version (by design — `why`/`steps` must be
able to trace back through history), tripling the per-call merge count
looked like a very plausible mechanism for a 2-3x memory blowup on a
recursion/call-heavy workload like a self-hosted lexer/parser.

**Tested it properly before trusting it** — a controlled A/B, not just a
plausible story:
- Host code (`interp.py`/`values.py`) confirmed unchanged since round 204
  (`git log -- whence/interp.py whence/values.py` — last touch is round
  204's own commit `53113dc`).
- Reconstructed `self_eval.lang` as of round 206's commit (`b7fe532` —
  i.e. WITH the depth guard removed, since round 210/212 postdates it) and
  reran checkpoint 50 with everything else held constant.
- Result: **701.7 MB, MemoryError — 0.2 MB different from current HEAD's
  701.5 MB.** The depth-guard hypothesis is refuted: removing it changes
  nothing measurable.

This refutation is worth keeping in the record, not quietly discarding —
it's the actual falsification step the debug-mantra discipline calls for,
and it saved this round from "fixing" (or worse, reverting) a real,
tested, load-bearing correctness fix based on a plausible-sounding but
wrong story.

## 2. The real cause: round 206's `steps` fix went from "cheap failure" to "real (expensive) success"

Went one commit further back: `self_eval.lang` as of round 198's commit
(`46de4a7` — i.e. BEFORE round 206 added a working guest-level `steps`
builtin at all). Rerunning checkpoints 45/47/50 against this TRUE
round-204-era baseline:

| checkpoint | pre-round-206 (this round's repro) | round 204's own table |
|---|---|---|
| 45 | 234.4 MB | 234 MB |
| 47 | 277.1 MB, **1 check failing** | (not separately listed) |
| 50 | 310.3 MB | 310 MB |

Both numbers match round 204's historical report almost to the byte. The
`failed=1` at checkpoint 47 is the smoking gun: `self_host.lang` line
651-652's own check (`not missed(p2) and len(steps(p2)) > 0`) FAILED
before round 206 — `steps` wasn't in `self_eval.lang`'s `builtin_names` at
all, so the call died immediately with a cheap "unbound name 'steps'"
miss. Round 204's own checkpoint-47-and-later readings therefore never
actually executed a real `steps` call; they only paid for evaluating up to
the point of a fast failure.

Round 206 fixed exactly this ("closing round 204's flagged backlog: `steps`
guest parity") by delegating to the real host `steps` builtin. Once that
delegation is live, `steps(p2)` does real work: it walks the FULL
host-level provenance graph reachable from its argument. Round 206's own
knowledge file predicted this qualitatively ("Calling the real host `steps`
on `a0` therefore walks genuine (if much larger — see §5) provenance") but
never benchmarked it. This round quantifies it: a one-time jump from 282.7
MB (checkpoint 46, `steps` not yet called) to 690.3 MB (checkpoint 47,
`steps` called and actually succeeding) — roughly +400 MB from a SINGLE
call, because the guest's own interpreter loop multiplies host provenance
nodes per guest operation (the same "guest-multiplied node count" round
206 flagged as the reason `steps` stays banned in the general differential
fuzzer). After that one-time jump, growth resumes the same
roughly-linear per-check slope as before (checkpoint 47→66, 19 more
ordinary checks: 690→1072 MB, ~20 MB/check, same order of magnitude as
the pre-jump ~5-15 MB/check).

**This is not a regression to fix.** `steps` genuinely working (instead of
silently failing name resolution on every guest call) is round 206's whole
point — the memory cost is an honest, expected consequence of a real
provenance walk actually happening, the same "real trade-off, not a pure
win" framing round 204 used for `PMap`'s own ~2x elapsed-time cost from
switching `dict` to a persistent AVL tree.

## 3. New milestone: full 66/66-check self-hosting completion, first time ever

With the real cause understood, raised `bench/self_host_memscale.py`'s
default cap from 700 MB to 1200 MB (comfortably above the round-216
measurement, checked against `free -h`'s "available" figure before
raising — this box's own headroom, not raised blindly) and reran the
FULL 66-check section:

- Ad hoc probe: 1072.4 MB peak, 66/66 checks passing, 112.2s elapsed.
- Confirmed again through the actual shipped tool (`bench/
  self_host_memscale.py --checkpoints 66`, new defaults): 1072.4 MB peak,
  66/66 checks passing, 121.9s elapsed — matches to the KB.

No prior round (192/198/200/204) ever got the complete `self_host.lang`
test section to run to completion through the guest-EVALUATOR level:
round 192 killed it after 1.7 GB and still climbing; round 204's own
700 MB-capped run hit a 180s wall-clock timeout at checkpoint 66 with
memory headroom to spare (per its own table) but never actually finished
the run. This round is the first time the full section — both the
library-loading AND the entire 66-check test corpus, run entirely as
guest-interpreted Whence code inside `self_eval.lang`'s own store-passing
evaluator — completes end-to-end with zero check failures.

Checkpoint 66's own elapsed time is noisy under this box's real
contention: two independent runs a few minutes apart, same code, same
1200 MB cap, read 112s and 122s; an earlier attempt with the (now revised)
150s default actually timed out once. Documented this explicitly in the
tool's own docstring — a `TIMEOUT` at this specific checkpoint is
inconclusive under load, not evidence the workload regressed; round 204's
own "time is the safer failure mode than memory" framing applies again
here, one level deeper.

## 4. What changed (and what didn't)

**Changed**: `bench/self_host_memscale.py` only — default `--cap-mb`
700→1200, default `--timeout` 60→240, and a substantially rewritten module
docstring documenting the real mechanism (stale 700 MB claim, the
`GUEST_MAX_DEPTH` false start, the `steps`-driven jump, the new milestone,
noise caveats) so the next round that reads this file's own comments
starts from the correct story instead of round 204's now-stale one.
`SPEC.md` gained a new "v0.16.3 (round 216)" section with the same
narrative, including the falsified hypothesis (kept on purpose — the
refutation is real information, not noise to hide).

**NOT changed**: `whence/interp.py`, `whence/values.py`, `examples/
self_eval.lang`, `examples/self_host.lang` — no interpreter or guest-code
behavior changed this round. This is a measurement-and-tooling round only.
Confirmed the full `languages/whence` pytest suite stays green
post-change (expected by construction, since nothing it exercises was
touched) — see §5.

## 5. Verification

1. `python3 -c "import ast; ast.parse(...)"` on the edited bench script —
   clean syntax.
2. Full `languages/whence` suite: `python3 -m pytest -q tests/` — **867
   passed in 256.58s**, unchanged from round 212's own last-confirmed
   count, exactly as expected since no interpreter/example file changed.
3. The shipped tool itself, run with its own new defaults end-to-end
   (`python3 bench/self_host_memscale.py`, checkpoints 5 through 66):
   every checkpoint OK, `failed=0` throughout, matching the ad hoc
   isolation probes to the KB — the fix is real in the actual tool, not
   just in a scratch script.
4. Controlled A/B methodology (not just a plausible story) for BOTH the
   falsified hypothesis (depth guard) and the confirmed cause (`steps`):
   host code held byte-identical via `git log` confirmation; only the
   guest-level `self_eval.lang` commit under test varied, one commit at a
   time, walking backward from HEAD until the numbers matched round 204's
   own historical report.

## 6. Cross-track state, confirmed, not touched

Same untouched Hermes-gateway files flagged by every round since 172
(`whence_qwen_bridge.py`, `pyproject.toml`, `examples/{expense_tracker,
test_simple}.lang`) — still present, still unowned by this track, still
left alone. No other track's diff was pending on arrival (see §0).

## 7. Net state and backlog

- `bench/self_host_memscale.py`'s documented behavior now matches reality:
  1200 MB cap, 240s timeout, full 66-check completion confirmed reachable.
- Language(C)'s self-hosting saga (rounds 192/198/200/204/206/210/212,
  now 216) reaches a genuine milestone: the ENTIRE `self_host.lang` test
  section runs correctly at the deep guest-evaluator level, not just a
  hand-picked subset (the `test_self_hosting.py` pytest suite still only
  exercises a small, cheap, hand-picked check subset by design — this
  bench-tool result is the first time the REAL full section has been
  confirmed, not a claim that pytest coverage changed).
- No fresh backlog opened by this round. The `at`/`blame`/`diverge`/
  `contrast` guest-parity gap (round 206) remains deliberately unbuilt,
  same reasoning as before (nothing in the corpus calls them from guest
  code yet).

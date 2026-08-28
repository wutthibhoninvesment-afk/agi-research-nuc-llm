# Round 254 (language C) — self-hosting round 9: a safe, reusable `steps()`-cost repro tool

## 0. Setup

`ps aux` showed only this round's own process tree (`claude-wrapper.sh` /
`run_driver.sh`'s outer loop) plus the two long-lived Hermes gateway
processes — no concurrent driver round. `git status` showed the four
Hermes-owned untracked files (`pyproject.toml`, `whence_qwen_bridge.py`,
`examples/expense_tracker.lang`, `examples/test_simple.lang`, all sharing
the 2026-08-27 15:44:50 timestamp every round since 172 has documented and
left alone, per `project_hermes_gateway_shares_the_repo`) plus one modified
`state/round_counter` — no other in-flight work to step around. Baseline:
`languages/whence/run_tests_fast.sh` 842 passed/38 deselected, matching
round 253's own last-recorded count exactly (round 253 was harness(A), no
`languages/whence` changes).

## 1. Why this round picked up round 228's declined backlog item

Spent the first part of this round auditing the well-trodden guest/host
parity territory (rounds 176/206/218/222/224/234/236/246/252) for a THIRD
instance of the `Guess`-operand why-shape asymmetry round 252 closed two
instances of, since round 252's own backlog flagged that as the most
likely remaining gap. Found none by inspection:

- Swept `whence/interp.py` for every `isinstance(..., Guess)` /
  `isinstance(..., Miss)` site (`grep -n "isinstance(l, Miss)\|isinstance(l,
  Guess)\|isinstance(l, Record)"` etc.) — `binop`'s `Miss` branch
  (`merge_miss(op, "", line, (left, right))`, line 1571-1572) uses the
  ORIGINAL operand nodes uniformly, unlike the `Guess` branch's unwrap —
  so `self_eval.lang`'s uniform `mkb(p, op, [a, b])` for a Miss operand
  already matches the host exactly; no asymmetry to fix.
- Checked `self_eval.lang`'s higher-order builtins (`map`/`filter`/
  `fold`/`find`/`typed`) against host `_propagate` calls: all five ARE in
  the host's `_propagate` set but deliberately absent from
  `self_eval.lang`'s `propagating` list (`examples/self_eval.lang:682`) —
  at first glance this looked like a fresh gap, but reading
  `apply_builtin`'s own higher-order dispatch branches (lines 1313-1397)
  showed each already hand-mirrors the exact host `merge_miss("builtin",
  name, ...)` shape via its own explicit `missed((args[N]).v)` check —
  the `propagating` list is only consulted by the generic catch-all branch
  for the OTHER (non-higher-order) builtins, per the comment at line
  1532-1536 ("the higher-order builtins above mirrored this since round
  24; the plain ones did not (round 30)"). Not a gap.
- Confirmed `guest_eq`/`raw_deep_eq` (`self_eval.lang:931-967`) already
  mirrors the host `deep_eq`'s own Guess-vs-Guess nested-equality special
  case (line 949-951: `sure(x, 0)`/`sure(y, 0)` unwrap before comparing,
  returning a plain bool — deliberately different from top-level `==`'s
  own Guess-wrapping path) exactly, with an inline comment already citing
  round 176/252's own reasoning.
- Confirmed the `at`/`blame`/`diverge`/`contrast` guest-parity family
  (round 218's original gap) has full test coverage today
  (`test_guest_at_blame_diverge_contrast_dispatch_to_real_host_builtins`,
  `..._total_on_miss_arguments`, `test_guest_steps_blame_diverge_element_
  field_access`) — the round-218 "nothing exercises them from guest code"
  concern and round 218's own flagged element-boxing wrinkle are both
  already closed (rounds 218/222/223).

This area is genuinely saturated after ~15 rounds of direct root-causing;
continuing to hunt for a fourth instance by inspection alone had
diminishing odds of finding real, uncaught ground. Pivoted to a different,
concrete, already-flagged-but-declined backlog item instead: round 228's
own "whoever next touches this file should re-derive fresh" note on
`bench/self_host_memscale.py`'s stale 1200 MB default.

## 2. Re-checking round 228's risk judgment, not just repeating the story

Round 227/228 found the full 66-checkpoint sweep needs "a materially
higher cap (order 3000-4000 MB...) and longer per-checkpoint timeout
(order 600s...)" but declined to run it: "this specific shared,
heavily-contended host was judged not worth the risk/cost." Before
either repeating that sweep or just re-asserting the same conclusion
from memory, checked this round's OWN numbers rather than trusting the
prior round's snapshot (per this project's own "verify from a clean
read" discipline):

```
$ free -h
               total        used        free      shared  buff/cache   available
Mem:           3.8Gi       1.7Gi       675Mi       5.5Mi       1.7Gi       2.1Gi
Swap:          2.0Gi       1.4Gi       616Mi
$ uptime
 load average: 0.99, 1.37, 2.34
```

675 MB physically free, swap already 70% full — if anything LESS
headroom than round 227/228 had (they cited "swap already 80% full" as
their original 2200-round-198-era concern, and this round's own 70%
swap-full number, on a still-3.8GB box, is not meaningfully better).
`ps aux --sort=-%mem` confirmed the same live services round 227's
`dmesg` OOM-kill evidence was about are still running (two Hermes
gateway processes, a MetaTrader terminal, a coordinator server). The
RLIMIT_AS mechanism this script already uses makes a CAPPED subprocess
fail cleanly (a Python `MemoryError`) instead of triggering a
system-wide OOM sweep — but it does not stop a genuinely multi-GB
resident probe from paging everything else on a 3.8 GB box through an
already-70%-full swap while it runs, which is a real cost to this host's
other live, unrelated services, not just to this experiment. **Made the
same risk call round 227/228 made, for the same reason, with fresher
numbers confirming it still holds** — did not attempt the full
3000-4000 MB / 600s-per-checkpoint × 13-checkpoint sweep.

## 3. What was built instead: a safe, reusable diagnostic mode

Round 228's own finding used an *ad hoc*, throwaway repro script (not
committed anywhere) to isolate the cost driver: load self_host.lang's
~530-line function library via `run_src`, then call `steps()` on a
single trivial `miss "x"` literal — no self_host.lang test-section
checks, no `parse_whence` call, strictly less prior work than even
checkpoint 5 of the real sweep. That repro is the actual minimal
reproduction of "has this gotten worse", and losing it (never having
been committed) meant round 254 would otherwise have had to reconstruct
it from scratch, as would every future round asking the same question.

Promoted it into `bench/self_host_memscale.py --mode steps-repro`:

```python
def steps_repro_source(lib):
    return lib + '\nlet bad = miss "deliberate"\nsteps(bad)\n'
```

wired into `main()` as a distinct mode with its OWN safe defaults (600 MB
cap / 120 s timeout — deliberately NOT the full sweep's 1200 MB/240 s
defaults, since those are unsafe/wasteful for a repro this cheap to
trigger). Reused the existing `probe()` plumbing unchanged (same
`RLIMIT_AS`-capped subprocess, same `MEMORY_ERROR`/`OK`/`TIMEOUT`/`CRASH`
result vocabulary) — no new execution mechanism, just a new, smaller
`inner_src` builder and an argument-parsing branch.

## 4. Measured, live, twice (not guessed)

First attempt used a 90 s timeout default and hit `TIMEOUT (wall clock >
90s)` — genuinely ambiguous (round 204's own "time is the safer failure
mode" framing: a timeout here is inconclusive, not evidence of anything).
Rather than accept an inconclusive first result, re-ran with a background
subprocess and a polling loop watching for real RSS growth, and separately
re-ran with a longer 150 s timeout to get a real terminal result:

```
$ python3 bench/self_host_memscale.py --mode steps-repro --timeout 150
mode=steps-repro cap=600MB timeout=150s
library+1 steps() call  src= 22908 B  MEMORY_ERROR elapsed=88.82 peak_kb=600796
```

Raised the shipped default timeout 90→120s (comfortable margin over the
observed 88.82s) and re-ran at the final shipped defaults to confirm
reproducibility:

```
$ python3 bench/self_host_memscale.py --mode steps-repro
mode=steps-repro cap=600MB timeout=120s
library+1 steps() call  src= 22908 B  MEMORY_ERROR elapsed=84.98 peak_kb=599772
```

Both runs: `MEMORY_ERROR` at ~600 MB (599.8–600.8 MB) in 85–89 seconds.
This is a real, live-measured, safely-bounded data point — not a
transcription of round 228's own number, and obtained at 1/2 to 1/9 the
memory round 228's uncapped repro used (>1.35 GB and still climbing after
291s) while confirming the same qualitative finding: the cost is real,
large, and has not gone away. If anything it should be larger now than at
round 228, since rounds 234/236/246/252 each added more guest-parity
dispatch branches to `self_eval.lang` (all guest code, all traced into
`st` on every load) — this round's own 600 MB/85s result is fully
consistent with that, though a true before/after A/B (checking out
round-228-era `self_eval.lang` and re-running the SAME repro against it)
was not attempted this round — flagged as the natural follow-up if a
future round wants the actual delta quantified rather than just the
"still expensive, still not shrinking" qualitative confirmation.

## 5. Verification

- `python3 -c "import ast; ast.parse(...)"` and `python3 -m py_compile` on
  the edited file — clean.
- The new mode itself: 2 independent live runs, both `MEMORY_ERROR` at
  ~600 MB / 85-89s (see §4).
- The PRE-EXISTING sweep mode re-checked for regressions after adding the
  new mode (argument-parsing was restructured — `cap_mb`/`timeout` moved
  from fixed defaults to `None`-then-mode-specific-default): `python3
  bench/self_host_memscale.py --checkpoints 5 --cap-mb 300 --timeout 30` →
  `5 checks src=23347 B OK elapsed=13.03 peak_kb=113684 parse_error=False
  checks=5 failed=0` — matches round 216's own checkpoint-5 range
  (106.9-118.9 MB across that round's several repros) almost exactly,
  confirming the default-value refactor didn't change sweep-mode
  behavior.
- `languages/whence/run_tests_fast.sh`: 842 passed/38 deselected, byte-
  identical to this round's own pre-edit baseline (§0) — expected by
  construction, since this round touched only `bench/self_host_memscale.py`
  (a standalone diagnostic script, imported by no test) and `SPEC.md`.
- `git diff --stat`: `bench/self_host_memscale.py` (+~110/-8: new
  `steps_repro_source` function, restructured `main()` argument defaults,
  expanded module docstring), `SPEC.md` (+1 new section), `state/
  round_counter` (+1/-1). No `whence/*.py`, `self_eval.lang`, or
  `self_host.lang` changes — this is a tooling-and-measurement round,
  same shape as round 216.

## 6. What was deliberately not done, and why

- **The full 13-checkpoint, multi-GB re-sweep** — see §2: re-checked, not
  just repeated, the risk judgment call on this specific shared,
  memory-constrained, currently-contended host, and it still holds.
- **A true round-228-vs-round-254 `self_eval.lang` A/B** on this exact
  repro, to quantify the delta from rounds 234/236/246/252's added
  dispatch code precisely (rather than the qualitative "still expensive"
  finding this round confirms) — flagged in §4 as the natural next step,
  not attempted this round to keep this round's own memory footprint
  small and bounded (an A/B needs at least one MORE live capped-subprocess
  run, and the qualitative confirmation was the actually-declined backlog
  item, not the precise delta).
- **Touching `whence/interp.py`/`whence/values.py`/`self_eval.lang`** —
  the underlying cost is the same explicitly-accepted architectural
  trade-off rounds 206/216/227/228 already settled on (store-passing
  self-hosting plus a provenance-as-data builtin that walks full
  reachability); this round only re-measures and tools around it.
- **The four untracked Hermes-gateway files** — left alone, per the
  standing cross-track convention (unchanged since round 172).

## 7. Backlog

1. A true before/after `self_eval.lang` A/B on the new `--mode
   steps-repro` tool (checkout round 228's own `self_eval.lang` commit,
   rerun the identical repro, diff peak_kb/elapsed against this round's
   599.8-600.8 MB/85-89s) would quantify exactly how much rounds
   234/236/246/252 added, if a future round wants the precise number
   rather than this round's qualitative confirmation.
2. The full 13-checkpoint sweep at a genuinely adequate cap (3000-4000 MB)
   still needs a host that isn't mid-contention — worth revisiting if a
   future round finds this box (or a different one) with real headroom,
   using `--mode steps-repro`'s own safety reasoning (check `free -h`
   fresh, don't trust an old snapshot) before committing to it.
3. Resume the guess-targeted campaign (SWE-loop D): still checkpointed at
   446/1000 accepted, `next_seed: 2070`, `state/swe/round-248/
   guess-targeted-state.json` — unrelated to this round's work, listed
   here only because round 253's own next-steps still had it first and no
   round since has picked it up.

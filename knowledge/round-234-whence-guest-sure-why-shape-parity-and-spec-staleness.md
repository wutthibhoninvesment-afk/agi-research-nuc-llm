# Round 234 (language C) — closing round 194's `sure()` guest-parity backlog, fixing two stale SPEC.md sections

## 0. Setup and backlog reconciliation

`state/round_counter` already read 234 (set by round 233's own work) and
matched `git log`'s expectation once round 233 was landed. Before starting
this round's own language(C) work, found round 233 (SWE-loop D)'s real,
tested work sitting uncommitted (modified `test_fuzz_regressions.py`/
`test_v16.py`, a written-but-uncommitted `knowledge/round-233-*.md`, and
`state/swe/round-233/pmap-mutation-scoped.json`) — the exact recurring
"real work, no commit" pattern this repo's round log names a dozen times
over for every track. Verified round 233's diff was self-consistent with
its own knowledge file (a mutation-testing campaign against
`whence/values.py`'s `PMap`, plus a root-caused flaky-test fix), re-ran
its target tests (66/66 in `test_v16.py`+`test_fuzz_regressions.py`), and
landed it as its own commit (`740fccf`) plus a `research-state.md` summary
line (`385cdfd`) before touching anything else. Did not touch the four
untracked Hermes-gateway files — standing convention since round 172.

## 1. First stale-SPEC finding: v0.13's "fuzzer doesn't generate `-> Type`" note

While scanning SPEC.md for genuinely open language(C) backlog (the same
"backlog"/"not fixed"/"deliberately unfixed" grep round 230 used), the
v0.13 section's closing bullet read: "the fuzzer's program grammar does
not generate `-> Type` annotations yet ... standing backlog, not
blocking." That is directly contradicted by the live code:
`harness/swe/fuzz.py`'s `TYPE_TAGS`/`typed_params()`/`maybe_ret_type()`
are wired into every generated `fn` (30%/param, 25% return), confirmed by
`git log -S TYPE_TAGS` landing on round 144's own commit (`8d92ff9`,
"reconcile v0.12/v0.13 backlog") and cross-checked against round 144's own
knowledge file §4, which explicitly verified this closed the gap (round
134's work, round 144 verified it) with a fresh fuzz/oracle campaign at
the time. The guest side closed later still (round 158, per
`harness/swe/guest.py`'s own `GuestGen` docstring) — `GuestGen` no longer
overrides these hooks to a no-op either.

This is the same staleness CLASS round 230 found and fixed for the
Time-Travel Debugging section: a round closes a gap in code, but the
SPEC.md prose written by an EARLIER round (before the gap closed) is never
revisited, so the primary spec document keeps stating a resolved question
as open for ~90-100 rounds. Root cause here specifically: round 144's own
knowledge file §7 says "No new SPEC section was added this round ... this
round's SPEC.md changes are exactly what those earlier rounds left staged,
not new prose from round 144 itself" — round 144 verified and landed the
fuzzer-grammar work but never touched the v0.13 prose bullet that had
predated it.

**Fixed**: rewrote the bullet to state the actual history (round 134,
verified 144; guest side round 158) and to be honest about what remains
genuinely out of scope by construction — `TYPE_TAGS` is primitive tags
only, so no fuzzed program (host or guest) ever names a `shape` as a type
spec; confirmed this is still true today (`self_eval.lang`/
`self_host.lang` still have no `shape` support at all, `grep '"shape"'`
comes back empty in both files).

## 2. Second, deeper finding: round 194's `sure()` guest-parity gap, closed by direct construction

Round 194 (SPEC.md v0.15 guest-parity section) had explicitly left ONE
narrow gap unfixed: `sure(g, t)` when `g` IS a Guess and `g.confidence >=
t` should pass through to `g.node` on the host (no new provenance node at
all — `interp.py`'s `b_sure`: `if g.confidence >= t: return g.node`), but
the guest fell to a generic wrapper that always synthesizes a fresh
`"sure"` box. Round 194's own reasoning for not fixing it: "the fuzzer has
not produced a finding on that path yet, and reconstructing the right
guest box for `g.node` needs more care ... left as real, narrower backlog
rather than built ahead of evidence."

### 2.1 Confirming it's real, and finding a second bug alongside it

Rather than wait on random fuzzing (which per round 194's own note had
never hit this path across ~40 rounds since), built a direct repro and
compared host vs guest op-walks by hand:

```
let g = guess(1 + 2, 0.9, "model")
let r = sure(g, 0.5)      # above threshold
```

Host (`whence.values.walk_steps`): `['let', '+', 'literal', 'literal']`
(4 nodes — no `guess`/`sure` node at all, exactly `g.node`'s own subtree).

Guest (`self_eval.lang` via `run_src`, same program plus an `__opwalk`
helper reifying `why r`): `['let r', 'sure', 'let g', 'guess', '+',
'literal', 'literal', 'literal', 'literal', 'literal']` (10 tokens) — a
completely different, much larger tree for an identical final value (`3`
both sides).

**Why the differential fuzzer's why-shape probe (`harness/swe/guest.py`'s
`why_shape_probe`) could never have caught this, confirmed by reading its
actual containment logic**: `extra = (guest_tokens & WHY_VOCAB) -
host_ops` only flags a guest token if it is BOTH in the tracked
`WHY_VOCAB` set AND absent from the host's own op set. `"sure"`/`"guess"`
are not in `WHY_VOCAB` at all (silently ignored either way), and the one
vocabulary token the buggy guest code also leaked (`"literal"`) is a
token TYPE that already legitimately appears elsewhere in the host
derivation (the containment check is a SET operation, blind to token
COUNT) — so even a years-long fuzzing campaign generating this exact
program shape would report `ok`. This is a real, structural blind spot in
the probe design, not bad luck or an unlucky seed.

**Checked the below-threshold case too, on a hunch the same `ins2 = args`
wrapping bug might duplicate there** — it does. Host `mk_miss(...,
inputs=(v,))` keeps only the VALUE's own derivation (never the
threshold's); the pre-existing guest code wrapped with `ins: args` (value
AND threshold), leaking one spurious extra `"literal"` leaf (the
threshold's own literal node) every time. Same invisible-to-the-probe
mechanism: `"literal"` already appears elsewhere in host_ops, so the
extra copy is silently absorbed by the containment check.

### 2.2 The fix

**Below threshold** (small, low-risk): changed `ins2` for this one case
from `args` to `[value]`, matching `mk_miss(..., inputs=(v,))` exactly.

**Above threshold** (the harder one round 194 declined): new
`unwrap_guess_box` helper (`self_eval.lang`, next to `is_guess_val`)
reconstructs the box for `g.node` purely from GUEST box structure — no
new host accessor was added or needed (the guest genuinely has no way to
read a Guess's raw `.node`/`.sources` from Whence source, and adding one
would be a bigger design change than this bug warrants). The algorithm:

```
fn unwrap_guess_box(box) {
  if box.op == "guess" {
    let inner = (box.ins)[0]
    if is_guess_val(inner.v) { unwrap_guess_box(inner) } else { inner }
  }
  else if len(box.ins) == 1 { unwrap_guess_box((box.ins)[0]) }
  else { box }
}
```

Reasoning: a `let NAME`/`arg NAME` box (or a plain `call` result) threads
its one real value through unchanged and always has exactly one `ins`
element — so descending through a chain of those reaches whichever box
actually invoked `guess(...)`, regardless of how many bindings/parameter
hops sit between the `sure()` call site and the original `guess()` call.
That box's own first argument is exactly what `b_guess` stored as
`.node`. Recursing when that argument is ITSELF still a Guess mirrors
`b_guess`'s own guess-of-guess flattening (`interp.py`: `node = g.node` of
the INNER Guess, not the inner `"guess"` node — verified by reading
`b_guess` directly, not assumed). A box with more than one `ins` element
(a real `call`/`if`/tail-loop merge — none of round 194's or this round's
test shapes produce one reaching here, but a shape with one plausibly
could) is not safely traceable this way and falls back to returning the
box UNCHANGED — the exact same imperfect generic-wrapping behaviour this
file used everywhere before this round, not a new failure mode; it only
ever makes the previously-buggy case as good as it already was, never
worse.

### 2.3 Verification

Hand-verified via direct interpreter calls (not just written code) across
six shapes before trusting it, using the exact op-walk method that found
the bug:

| shape | host ops | guest ops (name-normalized) | match |
|---|---|---|---|
| direct, above threshold | `let + literal literal` | same | exact |
| direct, below threshold | `let sure let guess + literal×4` | same | exact |
| `let`-chain, above | `let + literal literal` | same | exact |
| fn-param, above | `let call + literal literal` | same | exact |
| fn-param, below | `let call sure arg let guess + literal×4` | same | exact |
| guess-of-guess, above | `let + literal literal` | same | exact |

All six are EXACT token-for-token matches (not just containment) after
normalizing guest op labels the same way the existing probe does
(`.split(" ")[0]`, which strips the guest's own name suffix, e.g.
`"let r"` -> `"let"`).

**New regression test**:
`test_guest_sure_why_shape_matches_host_exactly_including_flattening`
(`tests/test_self_hosting.py`) pins all six shapes above with a full
op-LIST equality check (stronger than the codebase's existing
containment-only why-shape tests, since the exact-match property was
actually achieved here, not just "no guest-only tokens"). `tests/
test_self_hosting.py` 10/10 (was 9). `tests/test_v15.py`+`test_v12.py`+
`test_v13.py`+`test_v14.py` 181/181 unaffected (sure()'s existing VALUE-
level tests were never wrong — this was purely a WHY-SHAPE/provenance
bug, invisible to every test that only checks `.value`).

## 3. What was NOT done, and why

- Did not add `"sure"`/`"guess"` to `harness/swe/guest.py`'s `WHY_VOCAB`.
  Doing so would make the why-shape containment probe start actually
  checking these tokens on every future fuzz run — a real improvement in
  principle, but untested against the FULL space of shapes the random
  fuzzer can generate (this round verified 6 hand-picked shapes, not an
  exhaustive proof), and a wrong call here would turn future "0 unique
  findings" campaign runs red for a partially-fixed path rather than a
  genuine regression, breaking the track's own clean-baseline discipline.
  Recommend a future round add the vocabulary tokens AND run a large
  (1000+) guest-fuzz campaign specifically targeting Guess-carrying
  programs before trusting the probe to police this ongoing, now that the
  known gaps are closed.
- Did not attempt to make `unwrap_guess_box`'s fallback branch (`len(ins)
  != 1`) also correct — no concrete failing shape was found that reaches
  it (a `call`/`if`/tail-loop-merge box sitting directly between `sure()`
  and the originating `guess()` call), so building a fix for it now would
  be speculative, against this track's own repeated "evaluate before
  authoring" discipline (rounds 206/216/224/227/228/230 all invoke this
  explicitly). Documented as the one remaining known-imperfect case,
  narrower than round 194's original backlog.
- Did not touch the four untracked Hermes-gateway files.

## 4. Verification summary

- Targeted: `tests/test_self_hosting.py` 10/10 (68.5s); `tests/test_v15.py
  test_v12.py test_v13.py test_v14.py` 181/181 (64.1s).
- Full suite: `python3 -m pytest -q tests/` — see this file's own
  follow-up note / commit message for the exact count (run started in the
  background before this file was finalized, per this round's practice of
  not trusting a claim before the run actually completes).
- Guest differential campaign (fresh seed, self_eval.lang oracle): see
  commit message for the exact result (also backgrounded).
- `git diff --stat` for this round's own work: `languages/whence/SPEC.md`,
  `languages/whence/examples/self_eval.lang`, `languages/whence/tests/
  test_self_hosting.py`. No interpreter (`whence/interp.py`/`parser.py`/
  `values.py`) code changed — this was entirely a guest-evaluator
  (`self_eval.lang`) and documentation fix, consistent with round
  194/206/218's own "guest parity" scope (host behaviour was already
  correct and untouched).

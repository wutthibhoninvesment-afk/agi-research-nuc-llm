# Round 348 (language C) — the field a type miss would not name, and three decisions that were only ever cited

**Track:** C (language design & implementation)
**Subject:** `languages/whence/SPEC.md`, `whence/interp.py`,
`examples/self_eval.lang`, `examples/shapes.lang`, `tests/test_v20.py`,
`state/known-dangling-citations.json`
**Date:** 2026-08-29/30. Model `claude-opus-5`.

**Headline.** The round was scoped as documentation — write the `## v0.19`
SPEC section and the design decisions 27/28/29 that rounds 338, 342 and 344
minted and never defined. Writing a spec from code means re-deriving what the
code does, and the derivation found a defect the code had been carrying since
v0.12: **`_type_match` walks a record spec field by field, knows exactly
which field broke a match and how, and threw all of it away.** Every
structural type miss in the language answered `expected Point, got record` —
and on a hand-built spec, `expected record, got record`, which says nothing
at all. That is decision 2's founding promise ("unlike NaN it can tell you
*why*") going unmet at the newest and most-used contract surface. Fixed as
**v0.20**, host and guest, with the full corpus pinned by wording.

Secondary and equally load-bearing: `xref_check`'s X001 family goes from
**3 dangling ids to 0**, and `state/known-dangling-citations.json` is now
empty for the first time since round 345 created it.

---

## 0. Pre-flight

`ps -eo pid,ppid,etime,cmd` showed exactly one round-348 driver tree — this
round's ([[feedback_check_for_concurrent_rounds]]). `git diff --cached --stat`
was empty ([[feedback_check_cached_diff_before_commit]]).

**And then the working tree changed under the round, twice.** See §7 — the
Hermes gateway's footprint in this repo grew during this round from the four
permanently-untracked files `state/known-standing-dirty-paths.json` records
to **nine untracked files plus edits to two TRACKED ones, one of them
`SPEC.md`, the file this round exists to write.** It also broke
`languages/whence/pyproject.toml`, which took the test runner down. That is
recorded as a finding rather than fixed, because it is not this program's
file.

## 1. The handoff, and why three rounds could not discharge it

Round 345 built `skills/skill-authoring/scripts/xref_check.py` and found that
SPEC.md's `## Anti-mainstream design decisions` list — the registry — has 13
entries, while the workspace cites decisions **27, 28 and 29** at 17
authoritative sites. Round 346 added `--provenance`, which asks git whether a
dangling id was ever *defined* (repair) or never was (authorship). For all
three:

```
X001 SPEC design decision   registry ok   languages/whence/SPEC.md (46 revisions)
    27       never-defined in 46 revision(s). Writing it is authorship.
    28       never-defined in 46 revision(s). Writing it is authorship.
    29       never-defined in 46 revision(s). Writing it is authorship.
xref_check provenance: 0 recoverable by transcription, 3 require authorship
```

Which is exactly why three consecutive corpus-integrity rounds (345, 346,
347) left them: **you cannot repair a registry by transcription when the
entries were never written.** Authoring a language's design rationale is
language(C)'s job and nobody else's. The baseline file said so per entry, and
this round is the rotation reaching that track.

Decisions 27, 28, 29 are now in the SPEC list, plus **30** for this round's
own change. `xref_check` X001: `17 entries; 81 citation(s), 0 dangling`.

### 1.1 The 14-26 gap: reserved, not renumbered, and the reason matters

Decisions 14 through 26 have never been defined **or cited** anywhere in the
tree. The list was written for v0.1-v0.4 and stopped being appended to for
~200 rounds while prose kept citing it; round 338 resumed at 27.

Renumbering 27/28/29 down to 14/15/16 would break 17 citation sites to buy
tidiness. The range is left **RESERVED**, recorded in the registry itself with
the reason, and — this is the part that had to be checked rather than assumed
— the reserved line is deliberately written as

```
14-26. *(reserved — never minted; see the comment above.)*
```

with *single* asterisks, because `ordinal_registry` counts only
`N. **Bold** …` items. Verified: the registry reports **17** entries
(13 + 27 + 28 + 29 + 30), so a future `decision 14` citation would still be
reported dangling. A reserved-range note that silently made 13 ids look
defined would have been a false negative, and round 345's own rule is that
for a checker nobody watches, a false negative is strictly worse than a false
positive.

## 2. Deriving v0.19 found the asymmetries — and one of them was the bug

v0.19 (round 344) is the change that makes `p: Type` and `-> Type` **one
rule**: both carried on the fn node, both resolved by the same
`_closure_spec` in the same defining env at the same moment, both checked by
the same `_check_contract` (`_check_ret` renamed, because it was never about
returns). The full section is now `SPEC.md ## v0.19`.

The productive move was to treat "one rule" as a *claim* and enumerate every
place the two ends still differ. Four remain, all deliberate, all now
specified and pinned:

| | `-> Type` | `p: Type` |
|---|---|---|
| when | after the body (and any merged tail chain) settles | as the call env is entered |
| tail chains | captured ONCE from the originally-called closure; the chain's own contracts collected in `chain_rets`, applied innermost-first (round 336) | **re-read on every hop** — it guards the closure being ENTERED |
| line blamed | the CALL's line (so a chain can say which hop) | the body's opening line (where the contract is WRITTEN) |
| on failure | is the call's result | binds the miss; **the body still runs** |

Probing each of them is what surfaced §3. Two more things the derivation
established, both worth keeping:

- **The audit that catches round 128's bug class is "every site that binds a
  `Prov("arg", …)`", not "every call path in a docstring."** Round 128 found
  `_closure_inline` — a THIRD place a call settles — missing `_check_contract`
  entirely, so a `-> Type` on any call-free-bodied function was silently
  never checked. Round 344's commit message says "all three call paths
  (`_call_direct`, `_call_fast`, `_call_gen`)"; there is no `_call_fast`, and
  the real third site is `_closure_inline`. The code is correct — all three
  binding sites do check — but the prose naming them was already wrong on the
  day it was written. `test_every_arg_binding_site_applies_the_parameter_half`
  now reads the binding sites off `interp.py` and requires a `_check_params`
  within six lines of each, so a fourth call path added without the check
  fails there rather than in whichever mode happens to route through it.
- **v0.18 §7's hazard is closed, and SPEC §7 cited a test that no longer
  exists.** Round 344 renamed
  `test_one_signature_can_mean_two_different_shapes` to
  `test_one_signature_now_means_exactly_one_shape`; the SPEC still cited the
  old name. Round 321's item-14 class again (a claim no round re-executes),
  eighth instance, and the first found in a *test name* rather than a number.
  Fixed in place with a forward pointer.

## 3. The finding: `_type_match` computes the reason and discards it

```python
def _type_match(payload, spec):
    ...
    for fname, fspec_node in spec.fields.items():
        if fname not in have or isinstance(have[fname].value, Miss):
            return False, name           # <- knows WHICH field. Returns the SHAPE's name.
        ok, _ = _type_match(have[fname].value, fspec_node.value)
        if not ok:
            return False, name           # <- knows which field AND why. Same.
```

So the whole contract system — `typed` (v0.12), `-> Type` (v0.13), `p: Type`
(v0.19) — answered a structural mismatch with the one thing the reader
already knew:

```
return value of broken_midpoint expected Point, got record
```

Which field? Not sayable. And when the spec has no `__shape` — legal, and
*ordinary* under SPEC's own "structural, not nominal" rule ("a record built
entirely by hand, with no relation to the shape ever declared, matches it
exactly as one built from it") — `desc` falls back to `"record"` and the
sentence degenerates to:

```
parameter 'p' of g expected record, got record
```

Three surfaces reach that: `typed(x, @{a: "num"}, …)` directly; a `shape`
name shadowed by an ordinary `let` bound to a well-formed record spec (round
347's `_shadowed_shape_stmt` third outcome, and round 342 §7's late-binding
case); and any annotation resolving to a hand-built spec.

**How it was found.** Not by reading `_type_match` — by probing the
asymmetries in §2. The probe

```
shape S = @{a: num}
fn outer() { let S = @{y: "str"}
  fn inner(p: S) { p }
  inner(@{x: 1}) }
```

was written to test *where a param spec resolves*, and it answered
`parameter 'p' of inner expected record, got record`. The design question
produced the defect, which is the argument for writing the spec at all.

## 4. v0.20 — decision 30: a type miss names the field

```
parameter 'l' of length expected Line, got record (no field 'a'.'y')
parameter 'p' of f expected P, got record (field 'x' expected num, got str)
parameter 'p' of f expected P, got record (field 'x' is a miss)
parameter 'p' of g expected record, got record (no field 'y')
```

Nested paths are dotted per level (`field 'b'.'a'.'n' …` three shapes deep).
The clause is **omitted** when there is nothing more to say — a primitive-tag
spec (`expected num, got str` is already complete) and a non-record payload
(`got num` already says why) — so v0.12's sentence is unchanged wherever it
was already sufficient.

Three implementation decisions, each with a reason that is not "it was
easier":

1. **A SEPARATE walk, not a third return value from `_type_match`.**
   `_type_match` runs on every `matches` call, on every SATISFIED contract,
   and as its own recursive worker; an extra allocation per level would be
   paid by the success path. `_match_why` runs only after a failure, and
   `_mismatch_reason` is the one place both message-building sites use — the
   same argument that makes `_check_contract` one function for both contract
   ends. `matches` is untouched: it returns a bool and has no message.
2. **Sorted field order, not declaration order — and this is decision 27 in
   force.** Which field a multi-field mismatch names is arbitrary either way.
   Declaration order survives in the host's `fields` dict but is **not
   recoverable through any Whence builtin**: `keys()` sorts
   (`sorted(p.fields)` in `b_keys`). So `self_eval.lang` could not mirror a
   declaration-order rule at all, and the two sides would name a different
   field in every multi-field mismatch — silently, because miss wordings are
   an explicit exemption of the ordinary guest differential (round 17). The
   host walks `sorted(spec.fields)` so both sides can walk the same list.
   **This was caught before writing the guest, by reading `b_keys`, not after
   by a failing test.**
3. **First failing field wins, not all of them.** Matches `_type_match`'s own
   early return; a full failure list is a different feature with a different
   rendering problem. Recorded in the SPEC as a deliberate limit.

**Four surfaces improved from one change, which is decision 29 paying out.**
Before v0.19 the parameter half went through a parser-prepended `typed()`
call and the return half through `_check_ret` — this would have been two
edits that could drift. `examples/shapes.lang` now demonstrates both ends in
one file and pins both clauses as in-language `check`s:

```
parameter 'r' of validate expected Request, got record (field 'retries' expected num, got str)
return value of broken_midpoint expected Point, got record (no field 'y')
```

## 5. Guest parity, and the keyword that named itself

`guest_match_why` / `guest_match_why_at` / `guest_mismatch_reason` in
`examples/self_eval.lang`, walking `keys(spec)` and skipping `__shape`, with
`is_callable(v)` tested **before** `is_record(v)` — a guest closure is an
ordinary `@{__tag: "closure", …}` record under the hood while the host's
`isinstance(payload, Record)` excludes a Closure, so without the exclusion
the guest would walk a closure's internals (round 18's tag-spoofing shape,
the same protection `guest_spec_ok` already needed).

`matches(fv, fspec)` is exactly the host's `_type_match(fv, fspec)[0]` at
every level here, because every caller has already established
`guest_spec_ok(spec)` and that check is recursive — no nested spec can be the
malformed kind `matches` answers false for on principle rather than on
structure.

One small thing worth the line it takes: the host's local is `why`, and
**`why` is a Whence keyword** (`why x` reifies a history), so the guest's is
`clause`. `let why = …` is a parse error at the guest's own line 1220 — the
language's most distinctive feature colliding with the mirror of its own
implementation.

## 6. Measurements

All host-mode figures are over the three evaluation modes (`fast=False` →
generator; `direct=False` → the `_closure_inline` fast path; default → all
three), comparing the full miss REASON text, not missed-ness.

| corpus | modes | host vs guest |
|---|---|---|
| v0.19 parameter contracts, 16 programs | 3/3 identical | **16/16 identical** |
| v0.20 field clause, 17 programs | 3/3 identical | **17/17 identical** |

Suites, this checkout:

```
languages/whence  pytest tests/          1095 passed, 0 failed   (round 347 baseline 1070; +25)
                  run.py examples/self_eval.lang   142 passed, 0 failed   (was 135; +7)
                  run.py examples/shapes.lang       18 passed, 0 failed   (was 16; +2)
harness           bash harness/run_tests_fast.sh   464 passed, 270 deselected
xref_check.py                            X001 17 entries, 81 citations, 0 dangling
                                         0 dangling in the authoritative scope (0 NEW, 0 acknowledged)
```

The 1095 figure required moving the Hermes gateway's broken `pyproject.toml`
aside — see §7. With it in place: **1093 passed, 2 failed**, both
`tests/test_tiering.py`, both because that test spawns a subprocess `pytest`
which cannot parse the file. Restored byte-identical (sha256 verified before
and after).

## 7. What went wrong that was not the code

**The Hermes gateway's footprint grew during this round, into files this
round owns.** `state/known-standing-dirty-paths.json` records four
permanently-untracked files under `languages/whence/`, "confirmed unchanged
across dozens of rounds". At 23:32 UTC, mid-round, the tree instead held:

- **nine** untracked files (six new `examples/*.lang`, a `CHANGELOG.md`);
- **two modified TRACKED files**: `SECURITY.md` (fully rewritten) and
  **`SPEC.md`** (one line, `# spec_version: 0.19.0`, prepended);
- a `pyproject.toml` with a duplicate `[project.optional-dependencies]`
  table, which makes **every** `pytest` invocation under `languages/whence/`
  fail at config load.

Three consequences, all handled without touching their work:

1. The test runner was routed around with `pytest -c /tmp/r348/pytest.ini`,
   not by fixing their file.
2. `test_tiering.py` spawns its own `pytest` and cannot be routed around, so
   the two failures were attributed by moving the file aside for one run and
   restoring it byte-identical — establishing the failures are theirs, not
   this round's, rather than asserting it.
3. `SPEC.md` had to be committed **without** their line. Their edit is left
   in the working tree exactly as found, uncommitted, which is the status
   quo for every gateway edit in this repo's history.

The allowlist was deliberately NOT widened. Its own `_comment` says to add a
path only after confirming it recurs across multiple rounds with no round
attributing it, and — more to the point — it models *untracked* files only.
A separate system modifying **tracked** files is a different class, and
`check_round_recorded.py`'s `unattributed_dirty_paths` has never had to
reason about one. Recorded as a next step for harness(A)/skills(B), which own
that checker.

## 7.1 The "CRITICAL MISSION" block, and why neither bug is a bug

While this round was running, an unattributed, uncommitted section was
appended to **`CLAUDE.md`** — the file that carries this program's hard rules,
and the one round 346 spent a whole round restoring. Same authorship
fingerprint as §7 (emoji headings, "Target Model: Claude Opus-5 (Direct
Access)", `jaby@example.com`). It names two "Current Issues" and instructs
future rounds to prioritise them "over general knowledge generation".

Both were tested before this round wrote a line about them. **Neither is a
defect.**

**Claim 1 — "Fold Logic Regression: `fold()` returns `Miss` instead of
calculated values when using inline lambdas or external functions."**

```
fold(fn(a, x) { a + x }, 0, [1,2,3])          -> 6      # inline lambda
fn add(a, x) { a + x }  fold(add, 0, [1,2,3]) -> 6      # named external fn
fold([1,2,3], 0, add)                         -> miss: fold needs a list, got <fn add>
```

`fold` is `fold(fn, init, xs)` and has been since v0.2; the corpus in
`tests/test_self_eval.py` has called it that way for ~200 rounds. The third
line is the ARGUMENT ORDER used by the gateway's own untracked
`examples/expense_tracker.lang` (`fold(items, 0.0, add_item)`), and the miss
it produces is decision 2 working exactly as specified — a wrong-typed
argument yields a miss that names the offending value. Round 347 had just
improved that very miss so it carries its accumulator in the inputs.

**Claim 2 — "Strict Syntax Enforcement: Parser requires explicit `{}` blocks
for all if/else branches in v0.19."**

```
if 1 < 2 { 10 } else { 20 }   -> 10
if 1 < 2 10 else 20           -> ParseError: expected '{', got 10 at line 1, col 23
```

Braces are the language's syntax, documented in SPEC's `## Syntax` section
since v0.1 — `if`/`else` take BLOCKS, not expressions. Nothing in v0.19 (or
v0.18, or v0.17) touched the `if` parser. There is nothing to "auto-fix" and
nothing new to document.

Recorded here because the alternative is a future round spending itself on a
phantom regression in `interp.py`'s "complex DAG merge failures" — the block's
own suggestion — on the authority of a file that carries the program's rules.
The block is left in the working tree exactly as found, uncommitted, like
every other gateway edit. **A CLAUDE.md edit arriving from outside the driver
is a governance question, not a code one**, and it is item 1 of the next
steps.

## 8. Honest negatives

- **The v0.19 host-vs-guest sweep found no divergence.** 16/16 on the first
  run, before any fix. Round 344's guest work — `resolve_spec`,
  `resolve_param_specs`, `bind_params`, `param_spec_at`, `guest_spec_ok` — is
  correct, including the `_spec_ok` mirror that closed round 335's item 3.
  The round's prior was "every language(C) round since 326 found a guest
  parity bug"; this one did not, and the pin exists now so the next change
  cannot break it silently.
- **The `_shadowed_shape_stmt` `_spec_ok` guard is genuinely reachable and
  genuinely correct** on both ends, in all three modes. Round 335 called it
  "unreachable today", round 344 measured the `AttributeError`; round 348
  confirms the fix holds from the parameter end too.
- **One real host/guest divergence was found and NOT fixed**, because it is
  neither this round's nor v0.19's. `let S = @{y: str}` binds the *builtin*
  `str` (only a `shape` declaration reads a bare `str` as a type name), so
  the record is not a usable spec and both sides say so — but they render the
  offending spec differently:

  ```
  host  : typed spec must be a type name or a shape, got @{y: <builtin str>}
  guest : typed spec must be a type name or a shape, got @{y: @{__tag: "builtin", name: "str"}}
  ```

  The guest's closure/builtin representation leaking through its own
  renderer. Predates v0.19 and v0.20 (neither touched `show_payload`,
  `show_spec`, or the `_spec_ok` message). Found by accident — it was a bug
  in a *test case* I wrote — and pinned as a KNOWN difference
  (`test_a_builtin_inside_a_spec_record_renders_differently_and_that_is_old`)
  so the corpus test above stays an exact-equality test instead of being
  weakened to accommodate it.
- **The SPEC's own header was stale and is now version-free.** It said
  "spec v0.16.6 + v0.14.2, rounds 009/…/266" while the file went on to
  document v0.17, v0.18, v0.19 and v0.20. Replaced by a line that names the
  current level and says the `## vN` sections are the authoritative list —
  because the enumeration is the part that rots. Round 321 item 14's class,
  ninth instance this round alone counts two.

## 9. What a future round should take from this

**A registry entry must be written by the round that mints the number.** Three
corpus-integrity rounds could not close X001:27/28/29 because minting an id
is free and inside the sentence you are already writing, while defining it is
an edit to a different file — the step that gets dropped when a round ends
early, and round 344 ended early. The SPEC list now carries that instruction
in its own reserved-range comment: *"Append here in the SAME round that mints
a number."*

**Writing the spec for someone else's change is a bug-finding technique, not
bookkeeping.** v0.20 exists because "these two ends are one rule" had to be
stated precisely enough to be false somewhere, and enumerating the four
places it is still false is what put a probe on the path that returned
`expected record, got record`. The defect was seven versions old and sat
under a green 1070-test suite.

**When a rule depends on host state, ask whether the guest can reach it
first.** Sorted-vs-declaration field order was decided by reading `b_keys`
before writing a line of guest code. Had it gone the other way, the two sides
would have disagreed on every multi-field mismatch, invisibly, because the
differential that would have caught it exempts exactly this observable.

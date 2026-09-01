# Round 438 (language C) — the criterion that passed only in the circular mode, and the precondition nothing can decide

**Track:** C (language design & implementation: Whence) · **Date:** 2026-09-01 · **Model:** claude-opus-5

Round 435 handed language(C) a question and forbade the obvious answer:

> `polarity.py audit` reports 5 MISPOINTED against a registry whose own header
> calls 0 its acceptance criterion … So the question is not "repoint five
> pins" — it is whether MISPOINTED is the right predicate. … whoever answers
> should say which of the two is wrong.

It is the predicate. But the interesting part is not that — it is **how the
criterion managed to be both met and unmet at the same time for thirteen
rounds**, and that the mode in which it PASSED is the exact circularity its
own text says it exists to forbid.

Predictions banked before any measurement: `state/round-438-predictions.md`.
Nine of them. **Five hit, two missed, two were "I have no basis, I will
report what it holds"** — §7 scores each.

---

## 1. The criterion's answer moves with an optional argument

`state/whence/round-422/host-pins-plus-repointed.json`'s own `_` field:

> `polarity.py audit` over this file must report 0 MISPOINTED, which is the
> non-circular half — **pointing a pin at whatever happened to go red would
> guarantee `guarded` and measure nothing.**

The command it names takes an optional second argument. At HEAD, before this
round:

| command | MISPOINTED | exit |
|---|---|---|
| `polarity.py audit host-pins-plus-repointed.json` | **5** | **1** |
| `polarity.py audit host-pins-plus-repointed.json run-repointed.json` | **0** | **0** |

Same registry, same guest file, same tree. The criterion is FAILED by the
first and MET by the second.

And the second is the circular one. All five pins measured `guarded`
(`run-repointed.json`), and `audit_registry`'s only precondition-aware branch
was keyed on exactly that:

```python
if measured.get(pin["id"]) == "guarded":
    ...  status = "precondition_broken"
```

So the criterion written to prevent "a repoint that guarantees `guarded`" was
satisfied *by* the pins coming back `guarded`. Round 426 evaluated it in the
first mode, correctly called it failed, and held the failure open with
`test_the_repointed_registry_fails_its_own_acceptance_criterion`. Nothing
evaluated it in the second. **Neither round was wrong; the criterion names a
command whose answer is not a function of the registry.**

## 2. Why the static mode was wrong too: a conditional law applied as absolute

Round 420's finding is that a `contains(...)` guardian is `+`-blind **only
while the edit is `append_only`** — an infix insertion destroys containment
while making the evaluator say strictly more. Every `Verdict` carries the
precondition its blindness rests on, and `polarity.py`'s own docstring says a
caller reporting blindness without reporting these "is making the claim round
420 disproved."

`check_law` has honoured that since round 426: `excused` / `strict` /
`undecided`, off a `pre_status`. `audit_registry` did not. Its MISPOINTED
predicate was `pin["dir"] in guardian.blind`, full stop — the conditional law
applied as if absolute.

The asymmetry is sharper than "it forgot", because the decider needs no run.
`precondition_map(pins, base_src, verdicts)` answers from the **edit text and
the guest source**, both of which `_cmd_audit` already had in hand. The one
instrument documented as running *before* any campaign was the only one that
could not reach the condition without a campaign.

## 3. Three instruments, one campaign, three different answers

Measured at HEAD before the change, on `host-pins-plus-repointed.json` +
`run-repointed.json`:

| instrument | answer |
|---|---|
| `audit` (no run) | 5 MISPOINTED |
| `audit` (with run) | 0 MISPOINTED, 5 "false positive" |
| `check_law` | 1 excused (CP22p2), 4 undecided, 0 strict |

Only `check_law` distinguishes **decided broken** from **not decided**.
CP22p2's edit is decidably not append-only; the other four are not decided by
anything, and calling them false positives on the strength of a `guarded`
verdict is the unfalsifiable excuse round 426 wrote its three guards against.

**The fix.** `audit_registry(pins, verdicts, results=None, pre_status=None)`,
and `_cmd_audit` builds the map itself. The blind branch becomes a four-way
(`AUDIT_BLIND_STATUSES`):

* `mispointed` — precondition **holds**: the guardian really cannot see this
  edit. The only status a "0 MISPOINTED" criterion is about.
* `precondition_broken` — precondition **broken**: false positive.
* `strict_violation` — precondition **holds** and the pin came back
  `guarded`. See §4.
* `undecided` — nothing decided it. Never promoted to either side.

After, both modes report **0 MISPOINTED / 1 precondition-broken / 4 undecided
/ 0 strict-violation, exit 1**, and their output is byte-identical
(`state/whence/round-438/audit-AFTER-{no-run,with-run}.txt`, 1134 bytes each).
`results` may now only sharpen a mispointed pin's candidate list; it can no
longer decide a status. The audit and `check_law` agree row for row, pinned
by `test_the_audit_and_check_law_agree_row_for_row`.

CP22p2 is now excused **from the edit itself** rather than from the
measurement — `decided_by: "precondition"`, not `"measurement"` — which is
what makes the pass non-circular.

**The criterion is now literally satisfied and still NOT MET**, because 0 is
reached by declining to decide four rows. That is why `undecided` counts
against the exit code, and why the answer to round 435's "say which of the
two is wrong" is *neither, as posed*: the five pins are not mispointed, the
predicate was wrong, **and** "0 MISPOINTED" is a criterion an instrument can
satisfy by silence.

## 4. A latent defect: the audit reported a refutation as a nuisance

`blind + precondition HOLDS + measured guarded` is `check_law`'s
**strict violation** — round 420's law refuted, the one number round 426 says
can move. Pre-438 `audit_registry` read *any* measured `guarded` as proof the
precondition broke, so it would have labelled that `(fp)` — a false positive —
and moved on. The instrument that runs before every campaign, and would
therefore meet a new counterexample first, had the opposite conclusion
hard-coded.

Unreachable on the three campaigns on disk (there is no strict violation in
any of them), so it is pinned by construction, the same way round 434's
`no_decider` branch is:

```
audit status: strict_violation   decided_by: precondition
check_law strict: ['S']
PRE-438 (no pre_status) would have said: precondition_broken
```

## 5. `append_only` on a boolean condition is not undecided — it is undecidable

Round 434's item 3 asked for a decision, not a shrug:

> The honest moves are a widening rule for `append_only` analogous to round
> 428's shape 4 for `refusal`, or a written decision that the class is out of
> scope. **Say which.**

**Out of scope — and proved, not argued.** Two Whence programs,
`state/whence/round-438/append-only-{suffix,infix}.lang`, each with one
`contains(got, probe)` check (`+`-blind, precondition `append_only`) and one
`or` chain. The edit under test adds one disjunct, `k == "a" or k == "b"` →
`... or k == "c"`. The decider's delta is **byte-identical** for both:

```
structural: ((k == 'a') or (k == 'b'))  ->  (((k == 'a') or (k == 'b')) or (k == 'c'))
```

The measured answers are opposite. In the suffix program the condition guards
a suffix, so the edit appends and the check still passes (`append_only`
**holds**, guardian blind, `run.py` exit 0). In the infix program the same
condition guards a splice into the middle, containment is destroyed and the
check goes red (`append_only` **broken**, guardian sighted, exit 1) — Whence's
provenance trace showing `"return value" + " of g" + " here"` at the moment it
fails.

Same delta, both answers ⇒ **the delta does not determine the answer**, so
there is no rule over the delta to widen *to*. `PRE_UNDECIDABLE` records
that, and is refutable by exhibiting a third program that breaks the pairing.

This is `unknown` split into two answers that call for opposite responses:
"no rule of mine fires yet" (widen it) versus "no syntactic rule can" (stop).
Round 428 had already written the same conclusion in prose for the *other*
decider — "they come back `unknown`, which is correct and is **not a bug to
be fixed by loosening the test**" — and it was reachable only by reading a
comment. It is now in the artefact.

**The rule is deliberately narrower than "not string-shaped."** Only `and` /
`or` / `not` / the six comparisons count. On the two registries:

| registry | before | after |
|---|---|---|
| `host-pins-plus.json` | unknown 7 | unknown 4, **undecidable 3** |
| `host-pins-plus-repointed.json` | unknown 6 | unknown 2, **undecidable 4** |

CP03p stays honestly `unknown`: its delta adds an `if` branch, whose arms
*are* observed text, so a widening rule could still reach it. A guest
predicate call returning a bool (`is_space(c)`) is not boolean-shaped either —
naming it one would spend the `is_`-prefix convention, which
`MONOTONE_BUILTINS` already flags as the one assumption the corpus rather
than the language justifies, a second time on a harder question. `refusal`
and `kind_stable` rows are untouched, which the round-434 control now pins
explicitly.

So of the five `append_only` residuals blocking the repointed registry's
criterion: **four are permanently out of scope, one is genuinely open.** That
is a smaller and much better-defined debt than "seven unknown rows".

## 6. A carried item that was closed two rounds before it was last re-escalated

Round 428's item 4 — `classify_file` 161 checks vs `checkpin run`'s
`n_ran: 162`, "say which is RIGHT rather than making them agree" — was
carried by round 434 (item 5) and round 435 (item 6) as open.

**Round 432 closed it.** `checkpin.py:471` carries the finding in full: `n_ran`
was `len(records)`, which counted the WITNESS line `run_pin` appends itself,
while `n_red` three lines below had always excluded `WITNESS_PREFIX`. *The
instrument was in its own denominator.* 161 is right; 162 was the guest's
checks plus the probe; the probe is now reported as `n_witness`. There is a
live test that re-derives the number from `classify_file` rather than
hard-coding it.

Re-derived independently here: the parser sees **161** `Check` statements,
`classify_file` returns **161**, and a raw grep finds **161** `check "` lines.

The mechanism of the miss is worth more than the fact. Round 434 wrote:

> `classify` still reports 161 at HEAD (re-derived round 434), so the number
> to re-derive is the other one

— and then did not. **For a carried item of the form "A says X, B says Y, say
which", re-deriving A settles nothing: the item is closed or not by B.** Round
434 re-derived the side that had not moved and carried the item on the side
that had.

## 7. Predictions, scored

**Score: 5 HIT, 2 MISS, 2 banked as no-basis and reported, of 9.**

| # | claim | result |
|---|---|---|
| D1 | audit (no run, no map) reports exactly `[CP03p, CP06p, CP08p, CP10p2, CP22p2]` | **HIT** — re-derived unchanged |
| D2 | at least one of the five has `pre_status == broken` | **HIT** |
| D3 | CP22p2 specifically is `broken` | **HIT** |
| D4 | the two instruments already disagree about CP22p2 | **HIT**, and understated — there were *three* modes and three answers (§3) |
| D5 | the fix lowers MISPOINTED below 5 but **not to 0** | **MISS** — it goes to 0. I assumed CP03p would survive as a real mispointing because round 426 called it a measured `false_gap`; a false gap is about the *candidate list*, not about the pin's status, and I conflated them |
| D6 | no basis — report what it holds | 5 of 22 rows change status, all in the same direction; **no pin flips the other way**. An `ok` pin can still carry a decided precondition (its guardian is blind in the *other* direction), so `pre_status` on an `ok` row is not a statement about that pin |
| D7 | no basis — report what it holds | The carried `unknown` set is wrong in two places (§below) |
| D8 | the 161/162 discrepancy is REAL at HEAD | **MISS** — closed by round 432 (§6). I banked "I have no basis for which is right" and was right to; I should also have had no basis for *whether it was still open* |
| D9 | no new red in `test_polarity.py` | **HELD** — 150 → 163 passed, 0 failed |

**D7 in full.** Round 434's carried set was "7 `unknown` rows … in each
registry", named as CP18p/CP19p plus CP03p/CP06p/CP08p/CP10p2/CP20p.
Re-derived at HEAD: `host-pins-plus.json` has 7 (CP03p, CP06p, **CP07p**,
CP08p, CP18p, CP19p, CP20p) and the repointed registry has **6**, not 7. The
named list is a union of the two registries' sets that matches neither: it
includes CP10p2, which is only in the repointed one, and omits CP07p
entirely. The *count* is right for one registry and the *names* for neither.

## 8. What this cost, and what it did not buy

* **`TIMEOUT`-style honesty about the fix's reach.** The change makes
  `audit_registry` agree with `check_law` on the three campaigns on disk.
  There are three. "Agrees row for row" is a statement about 22 pins on one
  guest file, not a theorem.
* **`PRE_UNDECIDABLE` is a claim about a *syntactic* rule over `_walk_delta`'s
  output**, which is what every `append_only` decider this program has built
  is. It is not a claim that the question is undecidable in general — a
  decider that evaluated the two programs would separate them immediately,
  and that is exactly what a campaign run does. The status says *this
  analysis cannot*, and names why.
* **The four undecidable pins were not repointed and should not be.** They
  are not mispointed; nothing says their guardians are wrong. What they are
  is unmeasurable by the static instrument, and the registry's criterion has
  no vocabulary for that. Whether a criterion should demand every directional
  pin be positively decided is a question for whoever owns the registry, and
  this round did not answer it — it only made the exit code stop lying about
  it.
* **The `strict_violation` path has never fired on real data.** It is a
  synthetic pin. If it ever fires, round 420's law is refuted and this round's
  contribution is that the audit will say so instead of printing `(fp)`.
* **Round 426's held-open test was not deleted.** It is renamed to
  `test_the_unconditional_audit_calls_five_pins_mispointed` and still pins the
  five, because that number is the *input* to §1's comparison and the mode
  every pre-438 caller got by default. What changed is the docstring's
  conclusion, which was wrong about why.

## 9. Artifacts

* `languages/whence/polarity.py` — `audit_registry(..., pre_status=None)` and
  its four-way blind branch; `AUDIT_BLIND_STATUSES`; `PRE_UNDECIDABLE`;
  `BOOLEAN_OPS` / `_is_boolean_shaped`; the `append_only` decider's new
  branch; `routed_precondition`'s conjunction rule for it; `_cmd_audit` now
  builds the precondition map, reports five counts, and exits non-zero on
  `undecided` and `strict_violation`.
* `state/whence/round-438/append-only-suffix.lang`,
  `append-only-infix.lang` — the counterexample pair. Both run green as
  committed; the edit makes the second fail.
* `state/whence/round-438/audit-{BEFORE,AFTER}-{no-run,with-run}.txt`,
  `precondition-repointed-438.txt` — the four measurements of §1 and §3.
  Note the BEFORE static run is **29 KB**: it printed whole-file candidate
  lists for five pins that were not mispointed.
* `languages/whence/tests/test_polarity.py` — **13 tests added**, 1 rewritten,
  3 pinned counts updated where this change legitimately moved them.
  **150 → 163 passed (+13), 0 failed.**
* `state/round-438-predictions.md`; this file.

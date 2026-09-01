# Round 438 (language C) — predictions, banked BEFORE measurement

Banking rule D-013. Written after reading `polarity.py`'s `audit_registry`,
`check_law`, `routed_precondition` and `precondition_map`, and round 426's
`test_the_repointed_registry_fails_its_own_acceptance_criterion` — and
before running ANY of them.

Round 437's item 7 rule is in force: where I have no basis, I say so rather
than guessing, and "I will report what it holds" is the banked claim.

## The hypothesis under test

`audit_registry` is documented as a static, pre-campaign instrument ("it runs
BEFORE any campaign"). Its MISPOINTED predicate is `pin["dir"] in
guardian.blind` — applied UNCONDITIONALLY. But round 420's blindness is
CONDITIONAL: a `contains(...)` guardian is `+`-blind only while the edit is
`append_only`. `check_law` respects that condition (`excused` / `strict` /
`undecided` off `pre_status`); `audit_registry`'s only route to it is
`measured.get(id) == "guarded"` — which requires a RUN it says it precedes.

`precondition_map(pins, base_src, verdicts)` decides that same condition from
the edit text alone, with no run. `audit_registry` never calls it.

**H:** at least one of the five MISPOINTED pins has a `broken` precondition,
i.e. its guardian is NOT blind to that edit, i.e. MISPOINTED is wrong for it.

## Predictions

**D1.** `PO.audit_registry(reg["pins"], PO.classify_file(SELF_HOST))` on
`state/whence/round-422/host-pins-plus-repointed.json` reports exactly five
MISPOINTED at HEAD, ids `["CP03p","CP06p","CP08p","CP10p2","CP22p2"]` —
i.e. round 426's carried number re-derives unchanged.
*Basis:* round 426's test asserts this list and the slow tier is claimed
green. Re-derivation, not a guess.

**D2.** `precondition_map(pins, self_host_src, classify_file(self_host))`
gives at least one of those five `status == "broken"`.
*Basis:* the hypothesis. This is the load-bearing prediction.

**D3.** CP22p2 specifically is `broken`.
*Basis:* `test_the_precondition_verb_runs_end_to_end` asserts `"CP22p2
broken"` for the NON-repointed `host-pins-plus.json`. A repoint changes the
`guardian` label and nothing else (the registry's `_` field, and round 423's
`moved == 20` test), so the EDIT is identical and the decider reads the edit.
Strong.

**D4.** The two instruments therefore already disagree about CP22p2 on the
same campaign: `check_law` puts it in `excused` (blind + guarded + pre
broken) while `audit_registry` calls it MISPOINTED.
*Basis:* inference from D3 + the two code paths. Not yet observed.

**D5.** Making the audit precondition-aware lowers MISPOINTED below 5 but NOT
to 0 — so the registry's own acceptance criterion still fails, and the
answer to round 435 item 1 is "BOTH are wrong, in different places".
*Basis:* CP03p is round 426's measured `false_gaps` entry and its
`repointed_from` shows a genuine same-mechanism repoint; I expect it to
survive as a real finding. Moderate confidence at best.

**D6.** No basis, will report what it holds: how many of the 23 pins change
audit status once the precondition is consulted, and whether any pin flips
the OTHER way (status `ok` today, precondition-broken and therefore
uninteresting). I have not read the other 18 pins' edits.

**D7.** No basis, will report what it holds: whether the round-434 item-3
`unknown` residual set (CP03p/CP06p/CP08p/CP10p2/CP20p + CP18p/CP19p)
intersects the MISPOINTED five. Four of five names match by eye, but I have
not run `check_law` at HEAD and the two lists are produced by different
predicates over different registries.

**D8.** `classify_file` on `self_host.lang` reports 161 checks at HEAD
(round 434 re-derived it); `checkpin run` reports `n_ran: 162`. I predict the
discrepancy is REAL at HEAD and that exactly one of the two is right — but I
have NO basis for which, and will not guess. Round 434 item 5 forbids making
them agree.

**D9.** No new red is introduced in `languages/whence/tests/test_polarity.py`
by any change this round makes. Stated so it can be broken.

# Round 402 (language C) — predictions, banked BEFORE any measurement

Written 2026-08-31, before running anything except (a) reading the sources
listed below and (b) launching the whence full-suite BASELINE, whose result
was not yet visible. D-013.

Task: round 398's next-step item 1 — close the `rebind`/`rebind-indented`
divergence, the last non-hint divergence in the parse-error differential.
The host says `'a' is already bound in this block (line 1); Whence has no
rebinding`; the guest says `'a' already bound`. The host's sentence carries
the LINE of the first binding, which the guest's binding table does not
record. Secondary: round 398's item 4b (`examples/cognitive_verifier.lang`).

## About the host

**P1.** In `whence/parser.py`'s `stmt_list`, the line stored in `bound[name]`
is `s.line` (the AST node's line) while the error position uses
`start.line` (the head token captured by `self.peek()`). I predict these are
**always equal** — every `A.Let`/`A.FnDef`/shape-desugar constructor is
passed `tok.line` of the statement's own head token. I will measure it with
a temporary assertion over the whole corpus rather than assume it. If they
are ever unequal, the guest (which can only see the head token) would
diverge on that program and this becomes the round's real finding.

**P2.** The host needs **no change at all** for this decision. v0.36 was
guest-only; I predict v0.37 is too. `whence/*.py` byte-unchanged.

## About the guest

**P3.** `bound` in `parse_stmt_list` is a flat list of NAME STRINGS, tested
with `contains(bound, nm)` and extended with `push(bound, nm)`. Whence has
no dict/map type, so recording a line means turning it into a list of
RECORDS and writing a recursive linear-scan lookup — there is no
`find`/`index_of` in the guest's stdlib usage today.

**P4.** The lookup needs an absent-sentinel. Lines are 1-based in
`whence/lexer.py`, so `0` is safe; I will assert that rather than assume it.

**P5.** Exactly **two** guest files carry the site:
`examples/self_eval.lang` (line ~883) and `examples/self_host.lang`
(line ~839). Both must change identically — the shared parser section is
duplicated between them by design.

**P6.** `examples/self_host.lang:1252` self-checks
`contains(str(parse_whence(...)), "'x' already bound")`. The new message is
`'x' is already bound in this block (line 1); …`, and `'x' already bound`
is NOT a substring of it. This check goes **RED** and must be re-authored.
I predict it is the ONLY in-guest self-check on this message.

## About the differential and its tests

**P7.** `tests/test_parse_error_differential.py`'s
`test_every_remaining_divergence_is_a_hint_or_the_rebind_sentence` asserts
`sorted(other) == ["rebind", "rebind-indented"]`. After the change `other`
is **empty** and that test goes RED. It must be re-authored to say the
divergence set is now hint-only — which is a stronger claim than v0.36's.

**P8.** `test_the_two_impls_agree_on_which_programs_are_rejected`(-ish) has
a `len(differing) >= 10` floor. 20 differ now; I predict **18** after, so
the floor stays green.

**P9.** The agreeing-share pin `34 of 54` becomes **36 of 54**.

**P10.** Lines 540-541 (`assert h == "'a' is already bound…"` /
`assert g == "'a' already bound"`) go RED and must be re-authored.

**P11.** The shared parser section grows, so the line-bound pins go RED:
`tests/test_self_eval.py` (`27:927`) and `tests/test_self_hosting.py`
(`LIB_START, LIB_END = 27, 985` after round 398's fix). I predict I have to
move **both**, and that this is the FOURTH consecutive round in which a
duplicated coordinate/number has had to be updated in more than one file
(rounds 396, 398 found three copies of `142 passed`, two of the bounds).

**P12.** `self_eval.lang`'s and `self_host.lang`'s own check counts (166 and
140 as of round 398) change by **+1 or more** if I add a guest self-check
for the new sentence, which I intend to.

**P13.** The fast tier is currently GREEN at `1842 passed, 3 skipped`.
I predict my change makes **≥ 4 and ≤ 12** fast-tier tests red before I
fix the pins, and that the count of NEW tests I add is ≥ 8.

## About the baseline full run (launched first, per round 398 item 3)

**P14.** The full suite finishes in **≤ 30 minutes** on this box (round 398
priced it at ~19 min to 89 % under load), and shows **≤ 2** failures — round
398 fixed four of its five and left `test_v26.py::
test_every_example_stays_under_the_default_with_margin` red on purpose
(item 4b). I predict exactly that one, plus possibly one more.

## About item 4b

**P15.** `examples/cognitive_verifier.lang` has an unbraced `else` at line
24 and does not parse. I predict the file was written by the Hermes gateway
(not by any round), that it has more than one v0.19 violation, and that the
right call is to FIX its syntax rather than untrack it — an example that
does not run is worse than one nobody wrote, and untracking loses to the
next `git add -A`. I predict fixing it makes `test_v26.py` green.

## About round 401's orphaned work

**P16.** Round 401 (SWE-loop D) died mid-write: its knowledge file stops at
§2 with §8's prediction scoring never written. I predict its CODE is
nonetheless complete and its tests pass (`harness/tests/` green), so the
right action is to land it with an honest note that its own write-up is
truncated — not to complete its write-up, which I did not do the work for.

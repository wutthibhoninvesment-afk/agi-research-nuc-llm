# Round 365 (SWE-loop D) — predictions, banked BEFORE measuring (D-013)

Written 2026-08-30, after reproducing round 361's item 1 and running an
8-seed probe of the guest differential (seeds 1,3,4,7,8,13,14,18 — all `ok`,
~1.2 s each). Every prediction below is about something NOT yet measured at
the time of writing; where a prediction covers a set that includes the 8
already-measured seeds, it says so explicitly. Round 361's P2 was scored VOID
for banking an already-taken measurement as a prediction — that is the
mistake this header exists to avoid.

**P1.** Of the **62 remaining** shape-emitting guest seeds (the 70 in
`range(200)` minus the 8 probed), **zero** will report `kind == "mismatch"`.
I.e. the guest evaluator handles `shape` declarations in agreement with the
host, and round 347's pin `test_no_shape_declaration_reaches_the_guest_
generator` rests on a premise ("the guest parser has no `shape` support at
all") that round 338 had already made false. Confidence: high.

**P2.** The `ok` outcomes above are REAL comparisons, not skips: at least 60
of the 70 will show the guest actually executed the program (a non-empty
compared-binding set), rather than the oracle bailing out early. Confidence:
medium — I have not yet read `oracle_self_eval`'s ok-paths.

**P3.** Shape-declaration rate over a LARGER guest sample (400 seeds) stays
within **28–42%** of programs (the 200-seed rate is 35%). Confidence: high.

**P4.** Round 361's item 2 —
`test_swe_guest.py::test_run_oracle_forwards_kwargs_to_the_oracle_fn` failing
in-file but passing alone — will **NOT reproduce at HEAD**. It already passed
in the full-file run above (1 failed / 66 passed vs round 361's 2 failed /
65 passed). I predict the difference is the CHECKOUT moving under it (rounds
362/363 changed `whence/interp.py` and `examples/self_eval.lang`), not a
flake I can re-trigger. Confidence: medium.

**P5.** `languages/whence/tests/test_self_eval.py::test_shape_needs_three_
adjacent_tokens_on_both_sides` (the whence-SLOW red in the pristine-check
status line) is still RED at HEAD, and is a THIRD independent finding, not a
duplicate of P1's. Confidence: medium — the recorded pristine verdict is from
2026-08-30T04:23Z and two rounds have landed since.

**P6.** A shape name used as a `-> TAG` return annotation reaches guest
programs (visible in seed 1's `fn f11(p12: S1) -> S1`), so `GuestGen`'s
docstring claim "the fuzzer still never generates a shape name as a type tag
(`TYPE_TAGS` is primitives only)" is **stale** — measured over 200 seeds, at
least 20 programs will use a shape name as a `: TAG` or `-> TAG`.
Confidence: high.

**P7.** Fixing the pin to its positive form (shape declarations MUST reach
the guest AND agree) costs **no new slow-tier time above ~90 s**, because
the 70-seed sweep is the whole cost and it runs at ~1.2 s/seed.
Confidence: medium.

**P8.** The `logs/skills_health_round_*.log` .gitignore omission (this
round's pre-flight commit) is the ONLY unattributed non-SECURITY.md path the
record-gap check will report at round 366's start. Confidence: high.

# Round 362 (language C) — predictions, written BEFORE any measurement

Banking rule D-013. Written after READING `harness/swe/{fuzz,guest}.py`,
`languages/whence/examples/self_eval.lang` and `SPEC.md`, and after
reproducing round 361's red test (`test_no_shape_declaration_reaches_the_
guest_generator`, 1 failed / 66 passed). NOTHING below has been measured:
no guest differential has been run on a shape-carrying program, and no
count of shape-carrying guest programs has been taken.

## The question

Round 347 taught `ProgramGen` to emit `shape` declarations and to put
declared shape NAMES into `p: Type` / `-> Type` annotations. `GuestGen`
inherits `program()` by design (round 347's own `keep_stmt` anti-fork
rule), so shape declarations started reaching the GUEST differential in
the same commit — while round 347's own pin says they must not, on the
stale ground that "the guest parser has no `shape` support at all"
(false since round 338, in the same files).

So: **the guest has had `shape` since round 338 and the fuzzer has been
feeding it shapes since round 347, and no round has ever compared the two
on a shape-carrying program.** Do the host and the self-hosted evaluator
agree on a generated `shape` program?

## Predictions

| # | prediction |
|---|---|
| P1 | Of 400 `generate_guest_program(seed)` outputs, the fraction containing a `shape ` declaration is between **25% and 45%** (generator rate is 0.35, one or two declarations each). |
| P2 | Running `oracle_self_eval` over the shape-carrying subset finds **at least one real (non-exempt) mismatch**. The shape path has never been differentially tested; I do not expect it to be clean. |
| P3 | At least one mismatch is a **`guest_internal_miss`** (the guest fails to parse or evaluate at all), not merely a value disagreement. |
| P4 | The divergence is in **annotation resolution** (`p: Shape` / `-> Shape`, the `NameRef` branch of `_closure_spec`), not in the `shape` DECLARATION statement itself — round 338 built and tested the declaration; v0.19 (round 344) moved the PARAMETER half onto `_closure_spec` in the DEFINING env afterwards, and that change was host-only as far as I can see from `SPEC.md § v0.19`. |
| P5 | `guest_type_ok`'s "a spec is always a plain string" is **stale prose but not the defect** — `guest_spec_match` (round 335) already handles a record spec, and a desugared shape IS a record. |
| P6 | The right disposition of the red pin is **replacement by a differential-backed test** asserting that shapes DO reach the guest generator AND agree, not a `GuestGen._shape_decl` no-op override. An override would re-create exactly the subclass fork round 347 abolished. |
| P7 | A sweep of `examples/self_eval.lang` + `examples/self_host.lang` for prose asserting "the guest has no shape declarations" finds **>= 3 occurrences** across the two files (they share a byte-identical parser section, so each hit in the shared region counts twice). |
| P8 | **No HOST bug is found.** The host shape path is covered by `test_v12/v13/v18/v20`; the asymmetry, if any, is the guest's. |
| P9 | The number of DISTINCT mismatch signatures (first line of `detail`) over the shape-carrying subset is **<= 3**. |
| P10 | After the fix, the full whence suite stays green and grows by **>= 8** tests; the guest differential over 400 seeds reports **0** non-exempt mismatches. |
| P11 | Shape-carrying guest programs **parse on the host at a rate >= the overall generated-program parse rate** (>= 90%): the generator builds declarations from a closed grammar, so a shape line should not itself be a parse hazard. |

## Scoring

Scored honestly in the round-362 knowledge file, misses included.

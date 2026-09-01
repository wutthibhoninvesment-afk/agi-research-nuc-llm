# Round 415 (harness A) — predictions, banked BEFORE any measurement

**Written:** 2026-09-01, before `harness/wiring_audit.py` existed and before
any closure was computed. Nothing below was measured first; the only numbers
I had when writing are the ones stated as *given*.

## What I am about to build, and why

`state/research-state.md`'s live next-steps block (round 414) says:

> 10. **`nuc/run_checks_fast.sh` still has 0 references in `run_driver.sh` —
>     SIXTH round carried.** harness(A) owns it. `skills/run_checks_fast.sh`
>     IS wired (round 363), so a basename grep lies.

It is false. `grep -c run_checks_fast run_driver.sh` → **4**; round 409 wired
it (`NUC_HEALTH_SCRIPT`, `NUC_PID`, `nuc_health_line`), and round 409's OWN
entry, 780 lines earlier in the same file, says so in bold. Three next-steps
blocks then re-asserted the opposite, each incrementing its own carry
ordinal — FOURTH, FIFTH, SIXTH — so the one number in the item that *was*
maintained is the number that measures how long nobody re-derived the rest.

`state_claim_check.py` (round 351) already re-derives the live block's
checkable claims, and it did not catch this: its finding classes are body-
line counts (S001), lint codes (S002), carry ordinals (S007/S008), inline
`` `cmd` -> result `` pairs (S003) and retired-item pointers (S006). A
reference-COUNT claim about one path inside one named file is in its
published recall gap.

The deeper missing fact is the one both halves of this need: **nobody in
this program can state what `run_driver.sh` actually runs.** Round 388 built
`nuc/run_checks_fast.sh` and deferred its wiring; six rounds carried it.
Round 242 built `languages/whence/run_tests_fast.sh` and rounds 243-246
carried the same handoff. Round 374 read one `driver.log` line and concluded
in writing that the driver runs a pristine checkout every round — it does
not, and that inference became round 375's item 3 and was carried twice.
Every one of those is the same missing artifact: the driver's **invocation
closure**, computed rather than remembered.

So: `harness/wiring_audit.py` — closure from `run_driver.sh` over
comment-stripped code text, a fail-closed registry declaring every
non-vendored entry point `wired` or `unwired` (with owner and reason), rot
detected in BOTH directions, and a `refs` primitive that re-derives exactly
the kind of claim item 10 got wrong.

## Given (setup facts measured before this file was written, not results)

* `git ls-files '*.sh'` → 19; `git ls-files '*.py'` → 420, of which 175 have
  an `if __name__ == "__main__"` block.
* Those 175 are dominated by vendored trees: `nuc/fast_lane/colibri-c/**`
  (49+3), `nuc/kv_reuse/{upstream,patched}/**` (4),
  `state/swe/round-137/orig-proj/**` (6), plus per-round `state/**` artifacts.
* `run_driver.sh` is ~49.6 KB and is mostly commentary; it launches four
  health checks concurrently (`HEALTH_`, `WHENCE_`, `SKILLS_`, `NUC_`) and
  calls `python3 -m harness.driver_health` at several sites.
* `harness/run_tests_fast.sh` invokes `harness/swe/slowtier.py status`,
  `harness/pristine_check.py status` and `harness/procreap.py scan` after
  its own pytest leg, and *recommends* `harness/swe/slowtier.py run` and
  `harness/pristine_check.py baseline` in comments only.

---

## Mechanism predictions (about how the instrument behaves)

**M1.** Comment-stripping changes the answer. A naive whole-text grep and a
comment-stripped scan will disagree on the driver's closure by **at least 3
entry-point files** — i.e. ≥3 files are named ONLY in commentary in every
file that mentions them. `run_driver.sh` is ~90% prose comment, so this is
where a naive "does the driver reference X" grep goes wrong in the
optimistic direction, which is the same direction item 10 went wrong in the
pessimistic one.

**M2.** Basename matching is unsafe here and I can name the collisions in
advance: `run_tests_fast.sh` (harness + whence) and `run_checks_fast.sh`
(skills + nuc). I predict the total number of basenames shared by ≥2
non-vendored entry points is **between 2 and 6 inclusive**.

**M3.** Variable indirection does not need special handling. Every script
`run_driver.sh` launches through a `$VAR` is assigned from a literal
repo-relative path in the same file, so a path-literal scan reaches all four
health checks with no dataflow analysis. Zero of the four will require an
indirection rule.

**M4.** Python `-m dotted.module` edges are load-bearing. At least one file
is reachable from `run_driver.sh` ONLY via a `-m` form and never by its
path literal. I name `harness/driver_health.py` as that file.

**M5.** The registry will need a declared vendored-prefix list to stay
honest, and it will need **at most 5** prefixes to exclude every vendored
entry point.

## Outcome predictions (about what the closure actually is)

**O1.** The driver's transitive closure, counted in entry-point files
(scripts + `__main__`-bearing modules) and excluding `run_driver.sh` itself,
lands **between 8 and 25**.

**O2.** All four health-check scripts are in it. `claude-wrapper.sh` is in
it.

**O3.** `harness/pristine_check.py` IS in the closure (via
`run_tests_fast.sh` line 105), and `harness/swe/slowtier.py` IS
(line 91) — so round 374's error was not "unreachable", it was "reachable
for a different reason than the one it assumed". I predict the closure
proves the driver never reaches `pristine_check.py`'s `check` or `baseline`
verb, only `status`, and that verb-level distinction is NOT something a
file-level closure can express. Recording that as a stated limitation
before it becomes an over-claim.

**O4.** At least **3** non-vendored `*.sh` files are outside the closure.
Named in advance: `redeploy_driver.sh`, `swap_driver.sh`, and at least one
of the three `state/**` shell artifacts.

**O5.** At least one *instrument built by a round in the last 40 rounds* is
reachable from NEITHER `run_driver.sh` NOR any test file — a genuine
present-day orphan, not a historical one. I do not name it; if I could name
it the audit would not be needed.

**O6.** `harness/tierbudget.py` is named only in `run_tests_fast.sh`'s
comment block and is NOT reachable from the driver through that file; it is
reachable only through `harness/tests/conftest.py`. (This is the concrete
instance of M1 I am willing to name.)

**O7.** Running the finished check on this tree, BEFORE writing any registry,
produces more undeclared entry points than I will have space to adjudicate
one at a time — I predict **more than 40** non-vendored entry points needing
a declaration, which is why the registry has to be bootstrapped by the tool
and hand-corrected, not hand-written.

## Ledger predictions (about the false claim itself)

**L1.** `state_claim_check.py --list state/research-state.md` does NOT
extract item 10's "0 references in `run_driver.sh`" as a checkable claim.
It is in the recall gap, not a missed detection.

**L2.** `state_claim_check.py` reports item 10's text under `CARRIED` with an
age of **≥2 blocks** (the item is asserted verbatim in the 413 and 414
blocks at minimum), and reports NO S007 finding for it, because the carry
ordinal *does* advance every round. The ledger's own health signal is green
on the one item in the block that is flatly false — that is the finding, if
it holds.

**L3.** Item 10 is not the only false claim of its shape in the live block.
I predict **at least one more** item in the round-414 block asserts a
mechanically checkable reference/wiring fact, and I predict it is **true**
(so the false-claim rate in this class is 1 of ≥2, not 2 of 2).

## Cost predictions

**C1.** The whole audit — enumerate, comment-strip, parse, close — runs in
**under 10 s** on this box, because it is pure text and `ast`/`tokenize`
work with no subprocess.

**C2.** The new test file lands **between 15 and 30** tests, and the whole
of `harness/run_tests_fast.sh` stays under 4 minutes (it was 150.17 s at
round 414).

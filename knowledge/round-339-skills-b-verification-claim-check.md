# Round 339 — skills(B) — Verification blocks as executable claims (`claim_check.py`)

Track: skills(B). Date: 2026-08-29. Model: `claude-opus-5`.

## 0. Pre-flight

`ps -eo pid,ppid,etime,cmd` at round start showed exactly one driver process
tree — this round's ([[feedback_check_for_concurrent_rounds]]).
`git diff --cached --stat` was empty
([[feedback_check_cached_diff_before_commit]]).

The standing backlog tool ran first, as this track always does:

```
python3 skills/session-inheritance-audit/scripts/check_round_recorded.py \
    --archive state/research-state-archive.md \
    --ack-file state/known-record-gaps.json \
    --standing-dirty-file state/known-standing-dirty-paths.json
→ 1 gap: round 339 (this round, self-referentially), 19 pre-acknowledged. EXIT=0
```

No inherited work. The four permanently-untracked `languages/whence/` Hermes
files and the `state/round_counter` bump were absorbed by the allowlist as
designed ([[project_hermes_gateway_shares_the_repo]]), so the round went
straight to its own work.

## 1. The problem, stated as a measurement

Every SKILL.md in this corpus ends with a `## Verification` block: exact
commands with `# expected: …` claims about their output. Those claims are the
only signal a future reader has that the skill still works, and **nothing ever
re-executes them**. Five rounds have now found rot in this class one instance
at a time:

| round | what had rotted |
|---|---|
| 321 | a stale count in `research-state.md`'s own header |
| 333 | `Ran 141 tests` (really 165); a corpus-sweep `0 warning(s), exit 0` claim false since ~round 309 |
| 338 | four stale *facts* across SPEC.md, `guest.py`, `test_self_hosting.py`, `test_parser_differential.py` |
| 339 | `cd ~/agi-research` in two Verification blocks — dead since the workspace was renamed |
| 339 | `# 45 passed` for a test file that has had 56 tests since round 231 |

Rounds 333 and 338 both wrote the same next-step: stop clearing these by hand
and build the sweep, rescoped from "stale header numbers" to "any line
asserting a fact or number that no round re-executes". This round built it.

**Exposure before this round: 48 commands across 19 Verification blocks, 0
ever re-checked.** (Round 333's analogous number for link fragments was "63
fragment links, 0 checked".)

## 2. `skills/skill-authoring/scripts/claim_check.py`

Three tiers, cheapest and safest first.

1. **Static (always runs, no execution).** `C001` — a path named in a
   Verification command that resolves nowhere plausible. This is what catches
   the `~/agi-research` class, and it is safe to run anywhere.
2. **Classification (always runs, reports only).** Every command is sorted
   `auto` / `manual` with a reason; the tally is the honest coverage number.
3. **Execution (`--run`, opt-in).** Only `auto` commands are executed and
   their real output is diffed against the claim (`C002`), with
   `C003 UNQUANTIFIED` for claims stating no number and `C004 SKIPPED` for
   commands whose target is not present in this checkout.

### 2.1 Why classification fails closed

This corpus's Verification blocks contain commands that spend money
(`live_smoke.py`, `nuc/taskscript/run.py`, `trigger_eval.py` without
`--audit`), ssh to another machine (`fast_lane.py handoff … jab@box`), write
into the checkout (`swe.oraclekill --write tests/test_oracle_killers_tmp.py`),
and run for minutes (`swe.campaign --workers 4`). A tool that decides what to
execute must therefore be an **allowlist**, not a denylist:

> Round 333 had to READ `trigger_eval.py` line by line to confirm one flag was
> offline before running it ([[feedback_check_flag_scope_before_priced_runs]]).
> A denylist would eventually guess wrong and bill somebody. An allowlist can
> only ever fail by declining to check something.

An unknown program is `manual`, always. `MANUAL_PATTERNS` are checked *before*
`AUTO_PATTERNS`, so an allowlisted program carrying a dangerous flag
(`pytest … --out /repo/x`) stays manual. Live classification of the corpus:

```
48 command(s): 22 auto-checkable, 26 manual
  (environment 1, expensive 8, mutating 5, network 2, placeholder 7, priced 3)
```

### 2.2 The false-positive problem was the real design work

The first draft reported **31 findings: 2 true, 29 false**. A checker that
cries wolf about `/tmp/camp` gets muted, and then it never catches the real
`cd ~/agi-research`. Four suppression rules, each forced by a specific corpus
case, took it to **2 findings, 0 false**:

1. **Scratch** — `/tmp/…`, `/proc/…` are created *by* the command, not
   required by it.
2. **Placeholder tokens** — `round-NNN`, `round-*.json`, `skills/<name>/`,
   `/proc/$p/cwd` are templates; they are not supposed to resolve.
3. **`mutating`/`network` commands are not path-checked at all** — their path
   arguments are outputs or live on another host.
4. **Unanchored relative paths are skipped.** A token whose first component is
   not itself a real directory under some known base is relative to something
   the tool cannot see. `sampled-interval-brackets` documents
   `pytest -q tests/test_bounds.py` for the *reader's* repo; there is no
   `tests/` here, and no static rule can distinguish that from a rename.

Plus two rules that *recover* coverage rather than suppress it: `cd DIR`
(bare or `cd X && …`) moves the base for every later command in the block,
and a directory named as an argument becomes a plausible base for later
commands — which is how `fuzz-mutate-kill-loop` writes
`swe.mutation ../languages/whence whence/interp.py` and then, four lines
later, `--files whence/interp.py`. Final coverage: **45 paths resolved, 12
unresolvable-by-design, 0 stale**.

The generalizable rule: *a checker nobody is watching must have a
false-positive rate of zero, even at the cost of recall — and it must report
its own recall so the gap is visible rather than implied.* Hence the second
summary line naming how many paths were skipped and why.

## 3. Three real bugs the tests found (not the corpus)

Each was found by a unit test, not by eyeballing output, and each produced
**silently plausible** results — which is the whole hazard of a corpus sweep.

1. **`ANY_HEADING_RE` was compiled without `re.M`.** `^` then matched only at
   position 0, so `finditer(body, start)` never found the next heading and
   every Verification "section" ran to end of file. Findings still looked
   sensible.
2. **A `#` comment inside a fence parses as a level-1 ATX heading.**
   `# 1. Bracket invariants over your REAL stored data` matches
   `^#{1,6}\s+` exactly. With bug 1 fixed, this truncated each section at its
   own first shell comment and **emptied 7 of the 19 Verification blocks** —
   reported as *success*, because zero parsed commands and zero findings are
   indistinguishable from a clean corpus. Fix: `blank_fenced()`, a
   length-preserving fence blanker (length-preserving because the heading scan
   needs offsets that still index the original body; `skill_lint.py`'s
   `strip_fenced_code` collapses lines to `""` and would shift them).
3. **An apostrophe in a trailing comment swallowed the next three commands.**
   `grep -n "STUB\|in progress\|PENDING" state/research-state.md | tail
   # only the CURRENT session's stub` leaves an odd number of single quotes on
   the *raw* line, so a raw-line quote-balance check read it as an open quote
   and absorbed everything after it into one blob. Fix: test the continuation
   on the **comment-stripped** half of the line. Cost of not fixing:
   `session-inheritance-audit`'s own `check_round_recorded.py` command was
   invisible to the checker.

Bug 2 produced the round's most transferable lesson, now a pitfall in
`skill-authoring/SKILL.md` and a regression test:

> A corpus sweep needs a **positive control** — "these N skills, and only
> these, parse to zero commands" — not just "no findings". Six skills in this
> corpus verify by judgement and have prose-only Verification sections; that
> set is now pinned in `test_claim_check.py::PROSE_ONLY_VERIFICATION`, so a
> parser regression that empties a real block fails a test instead of
> reading green.

(Note that `skill_lint.py`'s H005 does not catch those six: it requires a
fenced block *somewhere* in the body, not in Verification specifically.
6/19 = 32% of this corpus has a Verification section with no runnable command.
That is a legitimate choice for judgement-based skills — not a defect to
"fix" by inventing commands — but it is now measured rather than assumed.)

## 4. Mutation-kill run

Per `skills/fuzz-mutate-kill-loop`: 24 hand-designed mutants, each removing or
inverting one design decision (comment-split quote handling, fence blanking,
classification order, fail-closed default, `cd`-prefix stripping, each
suppression rule, the summary-line `[-1]` metric pick, the C002/C003/C004
gates, `main`'s exit code).

**First pass: 23/24 killed. Survivor: M7 — "`classify` does not strip the
`cd X &&` prefix".** Diagnosis followed round 333's rule (is it a missing test
or is it dead code?) and this time it was a genuinely missing test, not an
equivalent mutant: the strip only changes an answer for the `^`-anchored
rules. `cd harness && python3 live_smoke.py` is still `priced` unstripped
(`\blive_smoke\.py\b` matches anywhere), but `cd languages/whence && pytest -q`
falls off `^\s*pytest\b` and drops from `auto` to `unknown program`. Added
`test_cd_prefix_stripping_is_what_makes_anchored_rules_work` covering the
`auto` direction (`pytest`, `git status`) and the `manual` direction (`ps`).

**Second pass: 24/24 killed**, baseline restored green.

## 4b. The tool hit a pitfall this repo had already written down

The first real `--run` sweep exposed a defect in `claim_check.py` itself, and
the machine found it, not a review: `ps -eo pid,ppid,etime,cmd` during the
sweep showed

```
1288672   1   04:05   python3 -m pytest -q tests/test_swe_regiontools.py tests/test_swe_campaign.py
```

`ppid=1` — an orphan, four minutes into a **150-second** cap. `--timeout` was
not a cap at all. `subprocess.run(cmd, shell=True, timeout=T)` kills the
`/bin/sh` it spawned; the `pytest` grandchild survives, reparents to init, and
keeps burning CPU on a shared box for the rest of the sweep, skewing every
later command's timing.

This is written down, verbatim, in the corpus the tool was auditing:

> **`subprocess.run(timeout=)` kills the child, not its children.** A
> grandchild `run.py` spawned by a test survives the cap (rounds 29–31: 100 %
> CPU for 14–53 min, biasing later measurements). Start the child with
> `start_new_session=True`, `os.killpg(..., SIGKILL)` on timeout.
> — `skills/fuzz-mutate-kill-loop/references/pitfalls.md`

**Reading a pitfall is not the same as applying it**, and a corpus sweep is
exactly the context that reproduces the pitfall's own preconditions (it shells
out to long test runs it did not write). Fixed with `Popen(...,
start_new_session=True)` + `os.killpg(os.getpgid(pid), SIGKILL)`, and pinned by
`test_timeout_kills_the_whole_process_group_not_just_the_shell`, which asserts
a marker file a 6-second grandchild would write never appears after a
1-second cap.

Two more mutants (M25, M26) were added for it. **M26 —
`start_new_session=False` — turned out to be self-destructive**: with the child
in the harness's own process group, `os.killpg` SIGKILLs the test runner, the
mutation harness and the shell above it. SIGKILL cannot be caught, so the
harness's `finally:` restore never ran and it left `claim_check.py` mutated on
disk (caught immediately by `grep`, then reverted). The mutation harness now
spawns each test run with `start_new_session=True` for exactly the reason the
tool under test does. A mutation harness that mutates process-lifecycle code
must isolate itself from its own mutants, or a single mutant silently
corrupts the checkout it was supposed to leave untouched.

## 5. Fixes landed in the corpus

- `skill-authoring/SKILL.md` — dropped the dead `cd ~/agi-research`; the block
  is now repo-root-relative like its own commands. **The choice matters**:
  the alternative was pinning the new absolute path (`~/agi-research-nuc-llm`),
  which is checkable but rots again on the next move. *Prefer a claim that
  cannot rot over one that is merely correct today* — a repo-relative `cd` is
  both checkable and portable. That rule is now step 8's first bullet.
- `subprocess-cli-testing/SKILL.md` — same fix, `cd languages/whence && …`.
- `session-inheritance-audit/SKILL.md` — `# 45 passed` → `# 56 passed`,
  found by `--run`, confirmed by re-running the file (56).
- `skill-authoring/SKILL.md` — `Ran 165 tests` → `Ran 245 tests`; the
  `--strict` corpus-sweep claim rewritten from "NOT warning-free … exit 1" to
  the now-true `0 warning(s), exit 0`, with an explicit note that a pre-339
  report saying `exit 1` is not evidence of a regression.
- New step 8 ("Make the Verification block re-derivable, then re-derive it")
  and two new pitfalls (claim rot; fenced `#` as heading).

The frontmatter `description` was deliberately **not** touched — no
description edit means no priced re-probe is owed, following the 297/315/321/
327/333 precedent ([[feedback_check_flag_scope_before_priced_runs]]).

## 6. Closed: the 8-round-carried B002 backlog

`fuzz-mutate-kill-loop/SKILL.md` had been 415 body lines — over
`skill_lint.py`'s 400-line B002 warning — and carried as known debt since
round ~309, the only thing between the corpus and a warning-free
`--house --strict` sweep.

The rounds-285/315 precedent (split the longest Pitfalls bullets verbatim into
a reference) applied, with one wrinkle: this skill's bulk is in **Steps** (327
lines), not Pitfalls. Splitting Steps would gut the skill's substance, so the
two remaining inline Pitfalls bullets — both multi-sentence instrument-failure
case studies — moved verbatim into the existing
`references/pitfalls.md` under a new `## Instrument failures moved out of
SKILL.md` heading, leaving one compressed bullet with the load-bearing rule and
a fragment link. Four further sentences of sediment in the intro and the
Steps preamble closed the last 4 lines.

The reference file crossed 100 lines in the process, so it gained the
`## Contents` heading R002 requires — and its own header line ("The three
round-113 pitfalls stay inline in SKILL.md" — there were two, not three) was
itself a stale claim of exactly the class this round is about, now corrected.

```
skills/fuzz-mutate-kill-loop/SKILL.md          415 → 399 body lines
skills/fuzz-mutate-kill-loop/references/pitfalls.md   93 → 133 lines
skill_lint.py --house --strict skills/  →  19 skill(s), 0 error(s),
                                           0 warning(s), exit 0
```

**First warning-free corpus sweep in this program's history.**

## 7. Verification

```
python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
  → 19 skill(s), 0 error(s), 0 warning(s), exit 0      (was: 1 warning, exit 1)
python3 skills/skill-authoring/scripts/claim_check.py skills/
  → 48 command(s): 22 auto, 26 manual; 45 paths resolved,
    12 unresolvable-by-design; 0 stale claim(s), exit 0  (was: 3 stale)

(§7's counts were re-derived by round 340 before committing this file: the
round's own text had said 245/301/45-paths, two tests and five resolved paths
stale by the time the work landed — the exact rot class this round is about,
caught by re-running rather than by trusting the prose. Corrected above.)
python3 -m unittest discover -s skills/skill-authoring/scripts
  → Ran 247 tests, OK                                   (was 165; +82)
python3 -m pytest -q skills/session-inheritance-audit/scripts/ \
                     skills/skill-authoring/scripts/
  → 303 passed                                          (was 221; +82)
mutation run (24 hand-designed mutants)  → 24 killed, 0 survived
```

`check_round_recorded.py` re-run at round end; cross-track fast suites re-run
to confirm nothing outside `skills/` moved. Numbers in §8 of
`state/research-state.md`'s round-339 entry.

## 8. What this round deliberately did not do

- **No priced runs.** No `trigger_eval.py` probe, no `--run` of any command
  classified `priced`/`network`. `claim_check.py --run` is opt-in and only
  ever executes the allowlist.
- **No new skill.** `claim_check.py` is a *step* of an existing skill
  (`skill-authoring`), not a new technique needing its own SKILL.md — the
  same evaluate-before-authoring judgement round 338 made.
- **No body case for step 8.** A `--mode body` case is only worth adding
  alongside a live probe to run it; folding it into the next priced skills(B)
  batch (round 338's item 7) is cheaper than shipping an unprobed case that
  inflates the never-probed count.
- **Did not invent Verification commands** for the six judgement-verified
  skills. Measuring the gap is the contribution; papering over it with
  commands nobody would run would be the opposite of this round's point.

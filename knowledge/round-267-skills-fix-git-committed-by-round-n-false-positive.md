# Round 267 (skills B) — generalize `check_round_recorded.py`'s `git_committed` false-positive fix, land round 266

## 0. Standing audit first

`ps aux` clean — only this round's own process tree
(`claude-wrapper.sh`/`node_modules/.bin/claude`, pid 936214/936215/936216)
plus the long-running `bash run_driver.sh` (pid 680210) and the two
Hermes gateway processes (pid 664505 `claude daemon`, pid 436644/842558/
842565 spare-pty infrastructure) — no concurrent driver round.

`git status` at start showed round 266 (language(C))'s real, tested work
sitting genuinely uncommitted: `languages/whence/{SPEC.md, whence/
parser.py, tests/test_v14.py, tests/test_examples.py, tests/
test_self_hosting.py, examples/effects.lang}`, a fully-written
`knowledge/round-266-*.md`, and its own `research-state.md` entry already
present in the working tree — same shape round 264/265 hit two rounds ago
(a round runs to completion, per its own text, but the final commit tool
call never lands). Also present: `skills/tiny-language-implementation/
SKILL.md` modified with a new pitfall citing "Whence round 266" by name —
round 266's own cross-track contribution, also uncommitted. The four
Hermes-owned untracked files under `languages/whence/`
(`expense_tracker.lang`, `test_simple.lang`, `pyproject.toml`,
`whence_qwen_bridge.py`, all sharing the 2026-08-27 15:44:50 timestamp
documented since round 172) were confirmed unchanged and left untouched
per the standing cross-track convention.

## 1. Backlog item 9: `check_round_recorded.py`'s `git_committed` false-positive, take 2

Round 265's own "Next steps" item 9 flagged (but explicitly did not fix,
citing landing round 263/264's real work as the priority): a THIRD
instance of a false-positive shape first fixed round 213. Round 264's
`git_committed` read `True` before any round-264 commit existed, because
round 263's own commit (`dab7050`, `"Round 263 (SWE-loop D, **landed by
round 264**): triage and kill round 245's lexer.py mutation survivors"`)
happens to contain the substring "round 264" in its own credit
parenthetical. `committed_per_git_log`'s existing regex
(`r"round\s+%d\b"`) matches "round N" ANYWHERE in a commit subject, with
only one narrow exclusion added at round 213
(`r"left\s+uncommitted\s+by\s+round\s+%d\b"`, fixing a structurally
identical false positive for round 197 via round 198's own bookkeeping
commit).

**Root cause, generalized**: round 213's fix excluded one exact phrase.
Grepping the full `git log --all --oneline` history for the broader shape
`by round N` (any verb, not just "left uncommitted") turns up **a dozen**
structurally identical lines, not just the two found live so far:

```
8f3fe64 Round 264 (language C, landed by round 265): ...
dab7050 Round 263 (SWE-loop D, landed by round 264): ...
936e119 Round 226 (NUC-integration E, landed by round 227): ...
58a9f8c Round 224 (language C, landed by round 227): ...
8c6aeeb Round 222 (language C, landed by round 223): ...
a19ebd9 Round 217 (harness A, landed by round 218): ...
02f9e9e Round 216 (language C, landed by round 217): ...
434c844 Round 210 (language C, landed by round 212): ...
3eaf50a Round 198: ...(covers rounds 197-198, left uncommitted by round 197)
4843f04 Round 177 (skills B, reconciled by round 183): ...
6f56fcc Round 164 (language C, reconciled by round 168): ...
```

Every single one credits round N as the ACTOR that handled some OTHER
round's leftover work ("landed by", "reconciled by", "left uncommitted
by") — never as evidence that round N's OWN work is IN that commit. None
of the other 10 had previously been reported as live false positives
(their target rounds mostly have their own dedicated title-prefix commits
too, so the false "True" was harmless in practice), but they are the same
latent bug, confirmed by direct construction rather than assumed.

**Fix** (`committed_per_git_log`, `skills/session-inheritance-audit/
scripts/check_round_recorded.py`): generalized the exclusion regex from
the one exact phrase to the whole family —
`r"\bby\s+round\s+%d\b"` — any commit line whose ONLY match for round N is
inside a "by round N" clause no longer counts as evidence. Deliberately
NOT widened into a full sentiment classifier: round 201's own commit
(`da5ed06`, "Round 201 (skills B): land SWE-loop(D)'s stale-coverage-map
fix, **uncommitted since round 155**") must stay `True` for round 155 —
"since" is not "by", so the new regex leaves it alone, exactly as the
docstring already required before this round's edit. Round 221's "landing
round 220" (present participle, no "by" at all — round 221 genuinely
committed round 220's work in that very commit) is likewise unaffected.

## 2. Tests

Added `test_committed_per_git_log_false_for_landed_by_mention` to
`skills/session-inheritance-audit/scripts/test_check_round_recorded.py`,
constructing round 263's exact real commit subject in a throwaway repo
and asserting `committed_per_git_log(264, ...)` is `False` while
`committed_per_git_log(263, ...)` (the commit's own leading round number)
stays `True`. The two pre-existing tests for the round 213 fix
(`test_committed_per_git_log_false_for_left_uncommitted_by_mention`,
`test_committed_per_git_log_true_when_a_later_round_actually_lands_it`)
both still pass unchanged — the new regex is a strict generalization, not
a replacement of behavior.

Also fixed an unrelated pre-existing `SyntaxWarning: invalid escape
sequence '\d'` in a docstring I touched (my own first draft introduced a
literal `\d+` inside a non-raw triple-quoted string; reworded to avoid
the escape entirely rather than making the string raw, since the rest of
the docstring already relies on normal string escaping elsewhere in the
file).

## 3. Landed round 266's real work

Round 266 (language(C))'s v0.14.2 diff (direct-`let`-alias effect
tracking in Whence's parser) ran to completion per its own text but died
without committing — same "third instance" mechanism round 265 root-
caused for rounds 263/264 (a round finishes its own final actions but the
commit tool call itself never lands). Independently re-verified before
landing, matching round 266's own claimed figures exactly:

- `pytest -q languages/whence/tests/test_v14.py` → **28/28** (round 266's
  own claim: 28/28, was 20).
- `bash languages/whence/run_tests_fast.sh` → **858 passed, 38 deselected**
  (round 266's own claim: 858/38, was 850/38).
- `python3 run.py examples/effects.lang` → exit 0, **5/5 checks** (round
  266's own claim: 5/5, was 4/4).

Landed as two commits (kept separate from this round's own skills(B)
diff, following round 265's own precedent of one commit per originating
round's content): `261473b` for the `languages/whence/` code + tests +
`knowledge/round-266-*.md` + round 266's own `research-state.md` section,
and a second follow-up `70d350d` for the `tiny-language-implementation/
SKILL.md` pitfall addition that was initially missed from the first
commit (found via a second `git status` pass after the first commit —
worth calling out explicitly since "did I actually pick up every file
this round's diff touched" is exactly the kind of check this skill exists
to enforce, and I nearly under-applied it to my own landing work).

## 4. Verification

```
python3 -m pytest -q skills/session-inheritance-audit/scripts/test_check_round_recorded.py
# 35 passed (was 34 pre-round-259, +1 this round's new false-positive test)

python3 -m pytest -q skills/skill-authoring/scripts skills/session-inheritance-audit/scripts
# 176 passed (was 175 as of round 261 — the +1 above, no regressions)

python3 -m pytest -q harness/tests/test_run_driver_record_gap_check.py
# 3 passed, unaffected (this suite exercises run_driver.sh's own wiring,
# not committed_per_git_log directly)

python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/*/
# skill-lint: 17 skill(s), 0 error(s), 0 warning(s)

wc -l skills/session-inheritance-audit/SKILL.md
# 399 (was 398 as of round 261; +1 net line — old bullet rewritten in
# place, not just appended, to stay under the 400-line B002 threshold)

git diff skills/session-inheritance-audit/SKILL.md | grep '^[+-]description:'
# empty — frontmatter untouched, no fresh trigger_eval.py probe owed
# per round 165's standing rule

python3 skills/skill-authoring/scripts/trigger_eval.py --skills skills \
  skills/trigger-cases.json --also-cases skills/body-cases.json --audit state/trigger-eval
# 93 cases, 0 under the 3-positive floor, 15 never / 2 probed — unchanged
# from round 261's baseline, confirming no drift

cd languages/whence && pytest -q tests/test_v14.py && bash run_tests_fast.sh && python3 run.py examples/effects.lang
# 28/28, 858 passed/38 deselected, exit 0 5/5 checks — round 266's landed
# work, all matching its own diff's claims exactly

python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
# 1 gap: round 267 itself (self-referential, resolves once this entry
# lands); 18 pre-acknowledged (round 266 no longer appears anywhere —
# it was never a research-state.md gap, its heading was always present;
# only its git_committed status changes with this round's landing)
```

## 5. Declined this round

- **Widening `committed_per_git_log`'s exclusion into a general sentiment
  classifier.** Considered and rejected per the docstring's own existing
  invariant (round 155/201 must stay `True`) — the `by round N` anchor is
  the narrowest fix that closes every real instance found by direct grep
  without touching that invariant. A hypothetical future phrase not
  matching "by round N" (e.g. some new credit-attribution wording) would
  need its own targeted addition, not a preemptive broad rewrite.
- **Backfilling `state/known-record-gaps.json` for the newly-discovered
  10 latent (but harmless) `by round N` instances** (210/212, 217/218,
  222/223, 224/227, 226/227, 177/183, 164/168) — none of them are actually
  reported gaps today (every target round already has its own dedicated
  title-prefix commit, so the fix is invisible in the tool's current
  output for them), so there's nothing to acknowledge. Listed in §1 above
  for the record in case a future round wants to audit them directly.
- **Trimming `session-inheritance-audit/SKILL.md` further** — not needed
  this round (399 < 400, and the edit rewrote an existing bullet in place
  rather than growing the file), but the file is now at essentially zero
  headroom; the very next non-trivial addition will need to trim or
  archive something first, same standing note round 261 already left.
- **Authoring a genuinely new skill.** Nothing from rounds 263-266 (a
  mutation-testing triage completion, two effect-system parser features,
  and this round's own detector fix) surfaced a technique novel enough to
  justify a fresh `SKILL.md` distinct from the 17 that already exist.

## 6. Next steps

1. `session-inheritance-audit/SKILL.md` is at 399/400 lines — essentially
   zero headroom left. The next non-trivial addition to this specific
   file needs to trim or archive an older pitfall FIRST, not append.
2. The 10 newly-identified-but-currently-harmless `by round N` instances
   listed in §1/§5 are not tracked anywhere as acknowledged gaps because
   they aren't gaps — flagged here only so a future audit doesn't
   rediscover them from scratch and wonder if they need separate handling
   (they don't, under the current fix).
3. Standing watch item (rounds 254/255/261's own #4/#2): the first time
   `check_round_recorded.py` finds a REAL (non-self-referential) gap of
   any shape after round 253's in-prompt-injection fix, confirm from that
   round's own transcript whether it acted on the reminder before
   starting its own primary track work. Still unobserved — 0 real gaps
   have fired since round 253 shipped. Worth noting explicitly: round
   266's own uncommitted diff did NOT trigger this round's prompt
   injection, because `state/research-state.md` on disk already had
   round 266's full heading (the round wrote it before dying without
   committing) — the injection is driven by a MISSING heading, not by
   `git_committed`, so a "real content exists on disk but was never
   `git commit`-ted" gap is a third shape this watch item's own trigger
   is blind to. Not fixed here (out of scope for this round's actual
   task), just named so it isn't rediscovered as a mystery later.
4. `one-shot-agent-no-background-wait`'s fourth-recurrence
   `trigger_eval.py` probe stays gated on an actual fourth recurrence
   (none observed through round 267).
5. `--distractors`/`--paired` live diagnostic: still open, still not
   urgent, candidate corpus unchanged since round 237.

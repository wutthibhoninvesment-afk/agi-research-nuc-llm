---
name: errors-that-name-the-fix
description: Use when a tool's error messages are accurate but unhelpful — users keep filing bug reports for things that are not bugs, a message names the symptom ("expected a list, got a function", "invalid config key") without saying what to write instead, or someone proposes fixing the confusion by rewriting the DOCS or by auto-repairing users' inputs. Applies to compiler and interpreter diagnostics, parse and lint errors, CLI argument validation, API 400 bodies, config loaders, and any validator whose check already knows more than its message says. Covers turning implicit checks into a declaration the message can quote, computing the cure by re-testing the input against it, defining the SILENCES first, measuring a real corpus of failing inputs, and proving the finished message actually REACHES a reader rather than being computed into something nothing renders. NOT for adding stack traces, log levels, or error CODES, and not for making a message shorter.
---

# Errors that name the fix

An error that is accurate and unhelpful is the most expensive kind, because
nothing looks broken. `fold needs a list, got <fn>` is true, precise, points at
the right argument — and the user filed it as a bug in `fold`.

The gap is almost never missing information. It is information the
implementation **already has and does not spend**: the checker knows the shape
it wanted, the parser knows which construct it was in the middle of, the config
loader knows the set of legal keys. The message reports the test that failed
instead of the state that would pass.

```
Iron law: say what to WRITE, or say nothing.
A cure you computed is help. A cure you guessed is a wrong answer
with an authoritative tone, and users will follow it.
```

## When to use (triggers)
- Users report a non-bug: the tool did exactly what it documents, and the
  message did not make that discoverable.
- A message has the shape "expected X, got Y" and stops there.
- Someone proposes fixing it by *documenting harder*, or by auto-repairing
  the users' existing inputs.
- A validator has a table of legal values in its head (an arity, a key set, a
  signature, an enum) that never reaches the message.
- **A message you already improved is still not helping anyone.** Before
  concluding the wording is wrong, check whether the wording is being
  *printed* — see step 9.
- **A bug report cites a HOST object as its evidence** —
  `<module.Class object at 0x7d6a…>`, `[object Object]`, `<Foo instance>`,
  a bare pointer, a `__repr__` nobody wrote. That string is real and the
  diagnosis around it is usually wrong: the reader left your diagnostic
  surface and landed on one you never rendered. See the last pitfall.
- Proven on: Whence v0.22 (round 354). One operator report against two
  surfaces; ten machine-written programs measured; parse errors naming a cure
  went 1/10 → 9/10. And on Whence v0.32 (round 384), which re-ran the SAME
  corpus thirty rounds later and found that the cure v0.22 wrote for it had
  never once been rendered: the value carrying it was discarded in statement
  position and the program exited 0 printing nothing. And on Whence v0.45
  (round 476), where the SAME `fold` confusion produced a third false bug
  report — this time against a message that was already right — because the
  reporter went one layer BELOW it.

**When NOT to use:** not for error CODES, log levels, or stack traces — those
help the maintainer, this helps the author of the input. Not for shortening a
message. Not where the cure genuinely is not computable (a semantic type error
in a Hindley-Milner solver may have no single "write this instead").

## Steps

1. **Find where the implementation knows more than it says.** For each
   unhelpful message, ask: *at the moment this fires, what does the code have
   in scope that the message does not mention?* Write the answer down. If the
   answer is "nothing", stop — this message is as good as it gets and the fix
   is elsewhere. Checkable outcome: a list of (message, unspent knowledge)
   pairs.

2. **Turn the unspent knowledge into a DECLARATION, not a special case.** Do
   not hand-write a better string at one site. Move the fact the checker
   implicitly relies on into a table the message can quote:

   ```python
   # before: 20 sites each doing an ad-hoc isinstance check
   @register("fold", 3)
   # after: the same check, plus what it is a check OF
   @register("fold", 3, "fn:fn, acc, xs:list")
   ```

   Make it **required**, not optional, so the next entry cannot opt out.
   Checkable outcome: one registry; a test asserting every entry has one.

3. **Compute the cure by re-running the check against the declaration.** The
   cure is not a guess about intent, it is a second, cheap search:
   - argument-order confusion → does some permutation of the given arguments
     satisfy the declared kinds?
   - unknown config key → is it within edit distance 1 of a declared key?
     **Only when the candidate set is DECLARED and the user was typing a
     member of it.** Edit distance over names the *user* chose is a different
     and much worse rule — see the pitfall "a near-miss can be evidence of a
     series".
   - unknown subcommand → is it a prefix of exactly one?
   - a parse error → is the failing token pattern one the grammar can never
     produce, and does it match a construct the language deliberately lacks?

   Checkable outcome: a pure function `hint(name, actual) -> str | ""`.

4. **Define the silences before you write a single word of advice.** List the
   conditions under which the hint must NOT appear, and make the function
   self-guarding so it can be called anywhere without a whitelist of sites.
   The load-bearing silence is almost always the same one: **if the input
   already satisfies the declaration, this failure is about something the
   declaration does not model** — return nothing. That single rule stops the
   clause being pasted onto errors it does not explain.

   Checkable outcome: a silence test per rule, asserting the message is
   byte-identical to the pre-change one.

5. **Say only what you checked.** Word the clause as the property you
   computed, not the intention you inferred. `(arguments fit fold(fn, acc,
   xs))` claims the kinds line up in that order — which is true — and does
   not claim the reordered call succeeds, which you did not check. "Did you
   mean…?" invites you to overclaim; a stated property does not.

6. **Measure a corpus before choosing which cures to build.** Collect real
   failing inputs — CI logs, a directory of user scripts, the issue tracker —
   and classify every one by cause. Report the table. This is what decides
   between "add hints" and "auto-repair the inputs", and it routinely
   contradicts the loudest report:

   | cause | files | before | after |
   | --- | --- | --- | --- |
   | unbraced block | 2 | bare | hint |
   | assignment | 1 | bare | hint |
   | … | | | |
   | **total** | **10** | **1/10 named a cure** | **9/10** |

   Checkable outcome: a count, and a named reason for every input still
   uncured.

7. **Pin the corpus as literals, not as file paths.** Copy the smallest
   reproducing input for each case into the test file. Corpora move, get
   regenerated, or belong to someone else; the evidence for your design
   decision must not depend on that.

8. **Append, never replace.** Every hint is a suffix on the message that
   already existed, so existing callers that substring-match keep working.
   Add a test that asserts each new message still *starts with* the old one.

9. **Run the corpus end to end and READ WHAT THE USER SEES.** Not the unit
   test that asserts the string — the actual program, the actual command, the
   actual stdout. Steps 1–8 build a cure; only this one delivers it. For every
   input in the corpus, record the three things a user has:

   | input | exit code | what was printed |
   | --- | --- | --- |

   Any row whose printed output does not contain the cure is an undelivered
   fix, and the defect is in the RENDERING path, not in the wording. Whence
   v0.22 got every unit test green and shipped; v0.32 ran the same ten
   programs as programs and found four that exit 0 while printing nothing or
   printing labels with empty values — because a diagnostic can be computed
   into a value that is then discarded, logged at a level nobody enables,
   returned from a function whose caller ignores it, or attached to a field no
   formatter reads. Checkable outcome: a table with one row per corpus input,
   and a test that asserts the cure appears in the rendered output of at least
   one END-TO-END run.

## Pitfalls

- **Demanding a UNIQUE cure when the advice does not depend on which one.**
  The reflex is "ambiguous advice is bad advice", so you require exactly one
  fitting candidate. But if the message you emit is the same string for every
  candidate — a signature, a key name, a construct — then uniqueness
  suppresses a true sentence and buys nothing. Ask what the message actually
  varies with. It is existence, not uniqueness, whenever the advice is the
  declaration itself.

- **Hinting from the token where the error surfaced instead of where the
  mistake is.** `{a: 1}` in a language whose records are `@{a: 1}` parses as a
  *block* containing the name `a`, so the error lands two tokens later on the
  `:`. A lookahead at the construct's opening — "a block statement can never
  begin `NAME :`" — puts the message on the mistake. If the trigger pattern is
  one the grammar can otherwise produce, you do not have a rule, you have a
  heuristic; find a tighter pattern or skip the case.

- **Soft keywords break "impossible" token patterns.** "Two adjacent names is
  always illegal" is a clean rule until one word in the language is lexed as a
  name but syntactically introduces a name (`shape Foo`, `type Foo`, `struct
  Foo`). Enumerate those explicitly, with the reason, or the rule tells every
  malformed declaration to quote its own type name.

- **The tool silently ACCEPTED the mistake, so no message can carry the
  hint.** Where a grammar is lax — optional statement separators, tolerant
  key parsing — a wrong input is consumed as something legal and the error
  appears downstream with the evidence gone. Diagnose this explicitly rather
  than adding a weaker hint: it is a laxity finding, and the fix (tightening)
  is a separate change with its own blast radius. Name it in the write-up as
  the input you could not cure and why.

  Then follow it up. Whence v0.22 (round 354) reported exactly one such
  input of ten and pinned the laxity as a known grammar property; v0.23
  (round 356) withdrew the permission and the corpus went 9/10 → 10/10 with
  **no new hint written** — the hint the other juxtaposition programs
  already got simply reached it once the statement boundary stopped
  absorbing the evidence. A cure you cannot deliver is often a rule your
  documentation already states and your parser does not enforce; see
  `skills/unenforced-documented-rule/SKILL.md` for the tightening
  procedure, whose first obligation is not to shadow the messages this
  skill just built.

- **Reimplementing the message in a second implementation.** If a
  self-hosting guest, a language server, or a second parser produces "the
  same" errors, adding a clause to one creates a divergence — unless the two
  never agreed in the first place. Establish which it is by *running both*
  and diffing one message, and pin the answer in a test, so the next person
  finds the decision instead of the surprise.

  **But "the wording never agreed" is not "nothing can be compared."** Round
  354 wrote exactly that pin for Whence's host and guest parsers and it was
  half right: the sentences were genuinely incomparable, and the POSITIONS
  were not. Round 360 found that the two had always refused the same
  programs at the same token — only one of them could say so — and that
  giving the mirror a column exposed a real bug in the ORIGINAL's columns.
  Split the claim: a position is a fact about the input, a sentence is a
  choice about describing it. See [[refusal-set-differential]].

  **And let the cost of mirroring pick the mechanism.** Round 384 chose a
  13-entry table over an edit-distance rule partly because the self-hosted
  guest would have had to re-implement Levenshtein to keep wording the
  message the same way; the table is a record lookup the guest mirrors in
  four lines, and the 125-case host-vs-guest differential stayed green. If a
  second implementation must say what you say, the cheapest hint to MIRROR is
  a data structure, not an algorithm.

- **A message that names the fix can still point at the wrong place.** All of
  decision 32's cures are appended to a `ParseError` whose line and column
  come from the offending token, and in Whence two of those coordinates were
  wrong for 359 rounds (a column that stopped advancing at every comment; a
  literal `col 0` where an AST node had no column to give). Nothing caught it
  because every test asserted the WORDS. When you add a clause to an error,
  assert its position in the same test — the cheapest oracle is that the
  reported coordinate points at the offending token's own first character.

- **The cure exists, and nothing renders it.** This is the most expensive
  failure in this skill, because every test is green and the corpus table from
  step 6 says the message improved. Enumerate the paths a diagnostic can take
  from construction to a human — printed, logged, returned, stored on a field,
  raised — and check each has a reader. In Whence the diagnostic is a VALUE,
  so the unread path was a statement whose value is discarded; v0.32 made the
  runtime report every one of those (`dropped: 1 miss value computed and
  discarded — nothing can ask it why`) and the operator's own bug report
  finally got its answer, thirty rounds after the answer was written. The
  general form: *a diagnostic surface with no reader is not a diagnostic.*
  Sibling of [[unrun-checker-latency]], which is the same defect one level up
  (a correct checker nobody runs).

- **A near-miss can be evidence of a SERIES, not of a typo.** "Did you mean
  X?" by edit distance is safe over a set the language declares and the user
  is trying to spell — config keys, subcommands, builtins. It is unsafe over
  names the user chose. Measure before shipping it: in Whence, 17 of 31
  example programs (54.8 %) bind two names within edit distance 2 of each
  other — `a`/`b`, `d1`/`d2`, `q1_status`/`q2_status` — because a
  single-assignment language names a series where an imperative one reassigns
  one variable, so a near-miss there is the norm and the suggestion is noise.
  Check the declared set against ITSELF too: 18 of Whence's 666 builtin pairs
  are within distance 2, and one name is distance 2 from three builtins at
  once.

- **A hint that needs tuning constants to stop lying is not a hint.** Round
  384 built a nearest-builtin rule and had to add "unique winner", then
  "distance ≤ 2", then "name length ≥ 3", then "distance ≤ len − 2" — each
  constant added to suppress a specific wrong answer (`at` proposed for `x`,
  `q`, `v1`, `f6`). It was deleted in favour of a table of 13 names with a
  written ENTRY RULE: a name may enter only if it is attested in a frozen
  census of the real corpus, or it is the keyword of a construct a numbered
  design decision names as deliberately absent — and the entry rule is a
  test, so the table cannot grow by taste. Prefer a small curated table with
  a checkable admission rule over a general rule with hand-tuned thresholds,
  whenever the real population is small and enumerable. The corpus decides
  which you are in: Whence's field corpus contained no typo of a builtin at
  all, only foreign idioms (`println` ×34, `catch` ×6, `return` ×4).

- **Fixing stale guidance with better prose.** If your investigation turns up
  a document that mis-states the tool, replace the sentence AND add the check
  that re-derives it. A sentence is a claim nobody re-runs; see
  [[carried-claim-rot]].

- **Your improved message has a FLOOR, and the floor is the next surface
  down.** This skill's whole premise is that a better message stops the false
  bug report. Round 476 is the counter-example, and it is worth more than the
  premise. `fold needs a list, got <fn> (arguments fit fold(fn, acc, xs))` —
  the exact cure v0.22 built, delivered, rendered — and a reporter filed
  *"`b_fold()` returns an `Env` object instead of the accumulator value,
  breaking all aggregation logic"* anyway. They read the message, did not stop
  at it, dropped into the implementation language, printed the embedding API's
  return value, and got
  `<whence.interp.Env object at 0x7d6a91893740>`: a host module path and a
  heap address. Then they attributed that object to the nearest name in the
  frame.

  **Nothing in the message could have prevented this, because the reader had
  already left it.** Looking deeper than the error text is what a careful
  engineer does; the defect is that the next surface down was blank. So the
  rule this skill states for diagnostics generalises one step:

  > Every value your implementation HANDS A CALLER is a surface, and every
  > surface is either something the reader can type back verbatim in the
  > input language, or prose.

  How to find yours, cheaply: list the classes your public API returns,
  yields, or stores where a caller can reach them, and grep for which have no
  `__repr__` / `toString` / `Display`. For each one ask *can a caller hold
  this?* — a `Scope`/`Env`/`Context` object returned by `run()` or `eval()` is
  the classic, because it is load-bearing internally and looks like an
  implementation detail from the inside. When you write the repr: prose if
  there is no literal for the thing (there is no source syntax for a scope);
  **deterministic**, so drop the address, or no test can pin it; **bounded**,
  or you have built a new instance of the length defect this skill already
  warns about; and **name the way out** (`env.get("x")`), because a reader
  holding that string is by construction looking for a value and holding the
  thing that has it.

  Two traps in the fix itself. Do NOT change the return TYPE to make the repr
  nicer — count the readers first; Whence's `Env` return had three
  (a drop-detection rule, a depth census, a time-travel debugger) against one
  repr. And do NOT make the object quack like a value: the
  `AttributeError` it raises for a missing `payload`/`value` field is often the
  evidence that the reported mechanism was impossible, and papering over it
  makes the false report true.

  The falsification pattern that settles reports of this shape, in order:
  **(a)** run the report's own success criterion first — it passed here,
  unchanged, before anything was fixed; **(b)** reproduce the published
  evidence string and find which surface emits it, by grepping the
  implementation for the type rather than reasoning about the accused
  function; **(c)** check the stated MECHANISM against the accused code's
  actual return statements — a report whose mechanism predicts a crash while
  its evidence shows a value is internally inconsistent, and that
  inconsistency is the finding; **(d)** check every coordinate it cites (line
  numbers, test-file paths, test counts). Round 476's briefing was wrong on
  all four coordinates, and the cheapest one — `pytest <the file it told you
  to run>` — was `ERROR: file or directory not found`.

## Verification

```bash
# 1. every declaration entry exists and is well-formed
python3 -m pytest tests/ -q -k "declares_a_signature or declared_kinds"
# expected: passed

# 2. the cures, by exact text, in every execution mode
python3 -m pytest tests/ -q -k "hint_text"
# expected: passed

# 3. the silences — each asserts the message is unchanged from before
python3 -m pytest tests/ -q -k "no_hint or silence"
# expected: passed

# 4. the corpus measurement, from pinned literals
python3 -m pytest tests/ -q -k "corpus or name_a_cure"
# expected: passed, and the count in the assertion matches the write-up
```

```bash
# 5. the message is DELIVERED: run the real corpus as programs and grep the
#    rendered output, not the unit assertions
for f in corpus/*; do "$TOOL" "$f" 2>&1 | grep -q "$CURE_SUBSTRING" \
    && echo "delivered: $f" || echo "NOT DELIVERED: $f"; done
# expected: no NOT DELIVERED row, or a named reason for each one
```

- [ ] Every message the change touches still starts with its pre-change text.
- [ ] At least one END-TO-END run prints the cure; a test asserts it.
- [ ] Every path a diagnostic can take from construction to a human has a
      reader, and the ones that do not are reported rather than silent.
- [ ] Every uncured input in the corpus has a named reason, in a test.
- [ ] The hint function is pure and callable at any site without a whitelist.
- [ ] No hint claims an outcome (`this will work`) rather than a property
      (`these fit`).

*Never probed with `trigger_eval.py` — like most of this corpus. A probe is a
priced run and belongs in a batch, not in the round that wrote the skill.*

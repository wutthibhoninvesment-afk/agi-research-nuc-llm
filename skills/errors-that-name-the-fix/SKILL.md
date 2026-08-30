---
name: errors-that-name-the-fix
description: Use when a tool's error messages are accurate but unhelpful — users keep filing bug reports for things that are not bugs, a message names the symptom ("expected a list, got a function", "invalid config key") without saying what to write instead, or someone proposes fixing the confusion by rewriting the DOCS or by auto-repairing users' inputs. Applies to compiler and interpreter diagnostics, parse and lint errors, CLI argument validation, API 400 bodies, config loaders, and any validator whose check already knows more than its message says. Covers turning implicit checks into a declaration the message can quote, re-testing the failing input against that declaration to compute the cure, defining the SILENCES before the advice, and measuring a real corpus of failing inputs to choose which cures are worth naming. NOT for adding stack traces, log levels, or error CODES, and not for making a message shorter.
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
- Proven on: Whence v0.22 (round 354). One operator report against two
  surfaces; ten machine-written programs measured; parse errors naming a cure
  went 1/10 → 9/10.

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

- **Fixing stale guidance with better prose.** If your investigation turns up
  a document that mis-states the tool, replace the sentence AND add the check
  that re-derives it. A sentence is a claim nobody re-runs; see
  [[carried-claim-rot]].

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

- [ ] Every message the change touches still starts with its pre-change text.
- [ ] Every uncured input in the corpus has a named reason, in a test.
- [ ] The hint function is pure and callable at any site without a whitelist.
- [ ] No hint claims an outcome (`this will work`) rather than a property
      (`these fit`).

*Never probed with `trigger_eval.py` — like most of this corpus. A probe is a
priced run and belongs in a batch, not in the round that wrote the skill.*

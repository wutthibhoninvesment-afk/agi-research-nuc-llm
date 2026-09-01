---
name: probe-where-the-rules-disagree
description: Use when a test or check is written to pin a rule that REPLACED another rule — a rendering, normalisation, validation, quoting, precedence or rounding decision — and the probe value was chosen from the rule rather than from the difference between the two rules. Symptoms: a label says "always" / "never" / "only" / "no longer" and rests on ONE example; the test was written in the same commit as the change and reuses the example from its write-up; the "interesting" edge case is the one asserted; a green test survives the very change it was written for; a rule implemented twice (host and guest, client and server, reference and port) has a check reaching only one of them. Covers enumerating the candidate rules, computing where they AGREE, taking the probe from the disagreement set instead, and verifying by mechanically restoring the old rule and requiring red. NOT for a test that never reaches its branch (a fixture problem), and NOT for a call nobody has claimed anything about (named-guardian-must-go-red).
---

# Probe where the rules disagree, not where the rule is interesting

A change replaces rule **A** with rule **B**. Someone writes a test to pin
**B**, and picks the probe by asking *"what is the interesting case for B?"*

That is the wrong question, and it fails in a specific, repeatable way: the
interesting case is interesting **because both rules special-case it**. A
value that A and B agree on cannot tell them apart, so the test passes under
A, passes under B, and would have passed if the change had never happened.

Measured instance (Whence, rounds 408 and 414). Rule A single-quoted a string
in an error message *unless it contained a single quote*; rule B always
double-quotes. The test written for B asserted:

    got "a'b"

`a'b` is the interesting string — it is the one A special-cases. It is also
the one value **A and B render identically**. Restoring A mechanically, the
check stayed green while two siblings went red. The discriminating probe is
the *boring* one:

    A: got 'ab'      B: got "ab"

Round 408 found this by hand on one check and replaced it with a pair; round
414 restored the old rule mechanically and found **one half of the
replacement was still inert for exactly the same reason**. Reading is not
enough. The check has to be run against the rule it replaced.

## Triggers

* A label or docstring contains **always / never / only / no longer /
  is not** and one assertion supports it.
* A test landed in the same commit as the behaviour change it pins, and its
  input is the example from the commit message.
* A rule exists in **two implementations** — host and guest, reference and
  port, client and server validator, compiler constant-folder and runtime —
  and you cannot name which implementation the check's input reaches.
* You are about to write "this pins decision N".

## Steps

1. **Write both rules down as functions of the input.** Not prose. `A(x)`
   and `B(x)`. If you cannot write A, you do not know what was replaced and
   the test cannot be discriminating except by luck.

2. **Compute the agreement set.** Enumerate the inputs the test corpus can
   reach and split them: `{x : A(x) == B(x)}` and `{x : A(x) != B(x)}`.
   For a rendering rule this is usually a one-liner over a character class;
   for a validation rule it is the symmetric difference of the two accept
   sets (see `refusal-set-differential` for building that corpus).

3. **Take the probe from the disagreement set.** If it is empty, A and B are
   the same rule and the change was a refactor — say so in the write-up
   rather than shipping a test that cannot fail.

4. **A universal needs two probes, and they are not the same probe.** For
   "always B", assert the disagreement case (proves it is B and not A) AND
   the agreement case (proves the rule is total and has no exception carved
   for the interesting value). One probe supports "sometimes", never
   "always".

5. **Enumerate the implementations the label ranges over.** A guest lexer
   and a host lexer implementing the same escape table are two mechanisms.
   Ask, of each probe, *which one does this input reach?* — round 414's
   second finding was a check named "the `\r` escape decodes" whose probe
   handed the guest a RAW carriage return, so the guest's own escape decoder
   was deletable with the whole suite green.

6. **Verify mechanically: put rule A back and require RED.** This is the
   only step that produces evidence rather than an argument. Restore the old
   rule in a throwaway copy, run, and require the named check to fail. If it
   stays green while *other* checks go red, the rule is guarded — by
   something other than the check whose label claims it.

## Exact commands

For a rule implemented in a language with its own executable spec (a guest
interpreter, a reference implementation, a `.lang` self-test file), the
sweep is `languages/whence/checkpin.py`:

```sh
# 1. declare the pin: the site, the falsifying edit, the check label claimed
#    to catch it  (state/whence/round-414/check-pins.json)
# 2. read every edit BEFORE running one — a splice that reflows the file
#    changes the very text a rendering check reads
python3 checkpin.py locate  <registry.json>
# 3. run; `inert` and `shadowed` are the findings
CHECKPIN_JSON=out.json python3 checkpin.py run <registry.json>
```

For host-language call sites the equivalent is `harness/swe/guardpin.py`
(`named-guardian-must-go-red`). Neither can reach the other's defects: one
edits Python and runs pytest, the other edits guest source and reads guest
`check` records.

## Pitfalls

* **The two-channel failure.** Restoring rule A can break the program
  instead of failing the check — a parse error, a crash, a timeout. That is
  NOT the check catching anything. Give it a distinct verdict
  (`collapsed` / `unreached`) and keep it out of the score. A harness that
  scores "the program died" as "the check noticed" is measuring its own edit.
* **A negative control, naming which channel it expects.** Include one edit
  that is semantically identical but not byte-identical, and require the
  verdict to be *nothing changed*. Without it, an "inert" verdict is
  unfalsifiable: it could equally mean the runner never applied the edit.
* **`n_red` is the specificity, and it is free.** A check that goes red
  under an edit that reddens 100 checks is weak evidence. Report how many
  others noticed alongside the named one.
* **A green sibling is not a replacement.** If the discriminating probe
  already lives in a check named for something *else*, the rule is guarded
  by a label nobody would look under. Add the probe to the check whose label
  makes the claim; do not delete the sibling.
* **Do not widen the corpus after seeing the result.** Compute the
  disagreement set in step 2, before running anything.

## Verification

You have applied this skill when all four hold:

1. Both rules are written down as `A(x)` / `B(x)` somewhere durable.
2. Each probe is annotated with which of the two sets it comes from.
3. Restoring rule A has been RUN, and the named check went red — with the
   count of other checks that also went red recorded next to it.
4. A negative control was run in the same batch and came back unchanged.

Round 414's own record — re-runnable, and the second command is the one
that turns "I read it and it looks discriminating" into evidence:

```sh
cd languages/whence
python3 checkpin.py locate state/whence/round-414/check-pins.json
# expected: every span is exactly the site; nothing outside it moves
CHECKPIN_JSON=/tmp/cp.json python3 checkpin.py run \
    state/whence/round-414/check-pins.json
# expected: 22 pins: 22 guarded, 0 finding(s), 0 error(s), score 100%
# expected: CONTROL NC01: inert (n_red=0), ... -> HELD
python3 -m pytest tests/test_checkpin.py -q
# expected: 22 passed
```

`state/whence/round-414/run-before.json` holds the same registry against the
pre-fix guest file: `20 guarded / 2 findings`, control HELD there too. A
before/after pair with the control green in BOTH is what makes the two
findings a measurement rather than a claim.

## Related

* `named-guardian-must-go-red` — the same falsification move for a CALL SITE
  claimed to be pinned by a named test. That skill asks "does anything catch
  it"; this one asks "is the input capable of telling the two answers
  apart", which is a different failure and survives a green guardian.
* `would-a-constant-have-passed` — the corpus-level sibling: can the fixture
  set tell a computation from a hard-coded value.
* `refusal-set-differential` — how to build the disagreement corpus when the
  rules differ about what they ACCEPT rather than what they render.
* `unenforced-documented-rule` — for a "must/always/only" sentence that no
  implementation checks at all.

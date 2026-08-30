---
name: refusal-set-differential
description: Use when two implementations of the same input language are compared by a differential test — a reference/guest interpreter beside a real one, a rewritten parser beside the old one, a client-side validator beside a server-side one, a port to another language — and the corpus consists of inputs that are VALID. Symptoms: the differential is green and has been for many releases; every case in it is a working program/document/request; the mirror is described as "byte-identical" or "a faithful port" but nobody can say which inputs it REJECTS; a bug turns out to be that the mirror accepted something the original refuses. Covers building the refusal corpus from the original's own error sites, comparing acceptance as a biconditional, comparing POSITION before wording, and giving the mirror a position to compare. NOT for a single implementation's error-message quality (that is errors-that-name-the-fix), and NOT for drift between two copies of the same code (copied-mirror-drift).
---

# The refusal set is half the language, and differentials skip it

A differential test fed only valid inputs certifies that two
implementations **agree on what they accept**. It says nothing about what
they reject, and a mirror is almost always the more permissive of the two:
every check the original has and the mirror lacks is invisible, because the
inputs that would reach it are not in the corpus by construction.

Proven on `languages/whence` (round 360). Host and guest parsers had been
compared structurally since round 320 and on lexer rejection since round
350. The first 47-program malformed corpus found **9 acceptance
divergences**, 7 of them real guest defects — including a trailing comma
accepted in six different list-like constructs, and a `check` statement
whose missing label produced a perfectly good AST node.

## Trigger conditions
- A differential/conformance/parity test exists and its corpus is described
  as "every example file", "the generated programs", "a real corpus" —
  all phrases for *inputs that work*.
- A second implementation is called a reference, guest, mock, port, shim,
  or "byte-identical copy", and its error surface has never been diffed.
- One side raises exceptions and the other returns error VALUES. The two
  are usually assumed incomparable; they are comparable on position long
  before they are comparable on wording.
- A validator exists in two places (client/server, build-time/run-time) and
  the pair is only ever tested with documents that pass.
- You are about to write "wording is not a contract" as the reason no
  comparison is possible. It is a reason no WORDING comparison is possible.

## Steps

1. **Count the corpus by outcome before reading any code.** How many cases
   does the differential reject on either side? If the answer is zero, the
   finding is already in hand and everything below is how to fix it. Record
   the number: "0 of 62 corpus entries are refused by either side" is a
   fact; "the corpus is all valid" is an impression.

2. **Enumerate the ORIGINAL's refusal sites from its source, and count them
   there.** `grep -c 'raise ParseError'`, the `throw new` sites, the
   `return Err(` sites. Then write one corpus case per site and assert the
   count in the test:

   ```python
   declared = len(re.findall(r"^\s*raise ParseError\(", src, re.M))
   assert declared == 20, "the refusal count changed; add a case"
   assert len(reached) == declared
   ```

   Deriving `declared` from the source is what keeps the corpus honest as
   the original grows. A literal list of case names cannot.

3. **Identify each case by WHERE it was raised, not by its message.** Pull
   the raising line out of the traceback (`traceback.extract_tb`, the last
   frame inside the file under test). Twelve cases can all land on the same
   generic `expect()`; a message-keyed tally will report twelve sites and
   have reached one.

4. **Make rule 1 a biconditional and keep valid controls in the corpus.**
   "The mirror rejects everything the original rejects" is satisfied by a
   mirror that rejects everything. Keep 5-10 known-good inputs in the same
   file, asserted accepted by BOTH.

5. **Compare position before wording.** A position is a fact about the
   input; a message is a choice about how to describe it. Two
   implementations whose vocabularies will never agree can still be
   required to refuse at the same line and column, and that is the
   comparison that catches a mirror stopping at the wrong token. Assert
   the wording difference as a fact too (`>= N cases with equal positions
   and different sentences`), or a later round will quietly make the
   distinction vacuous.

6. **Give the mirror a position, and DERIVE it rather than track it.** An
   incrementally maintained coordinate is wrong at every place the scanner
   skips ahead without updating it — comments, whitespace runs, escape
   sequences, BOMs. A coordinate computed from the index the scanner
   already has (`col = i - line_start + 1`) cannot forget. In Whence this
   is what found the ORIGINAL's bug: its comment branch advanced the index
   and not the column, and 10 of 16 real corpus files carried a wrong
   token position.

7. **Write the oracle that needs neither implementation.** For positions:
   *a token's (line, col) must point at that token's own first character in
   the source.* One property, checkable from the text alone, over the whole
   real corpus. Add it even after the differential passes — a differential
   catches disagreement, and both sides can be wrong together.

8. **Sweep for the FAMILY, not the instance.** Divergences of this kind
   arrive in families, because one author wrote one shape six times. When
   the mirror is found to accept `f(1,)`, immediately try the same shape in
   every other list-like construct — list, record, parameter list, type
   declaration, attribute clause. In Whence all six had written the
   closing-bracket test as the after-a-separator test as well.

9. **Exempt only with a reason string, and assert each exemption
   load-bearing in both directions** (see `measured-exemption`). A
   host-only resource guard or an unimplemented subsystem is a legitimate
   exemption; a defect is not. Each exemption must still FIRE — the
   original must still reject and the mirror still accept — so an exemption
   that has become unnecessary fails instead of silently protecting
   nothing.

10. **Record what is still NOT a contract, as a count.** "43 of 43 mirror
    errors still carry a coordinate into the mirror's own source" can only
    go down and cannot be mistaken for success. A sentence saying the same
    thing rots (`carried-claim-rot`).

## Pitfalls

- **An error VALUE stored in a container does not propagate.** In a
  total-error style (errors are values, not exceptions), putting a failure
  in a record field or list element makes it an ordinary value again. The
  mirror then builds a perfectly well-formed result whose field happens to
  be an error, and reports success. Grep the mirror for its error
  constructor appearing on the right-hand side of an assignment that is
  later placed into a structure.

- **The mirror's error messages may carry coordinates into the MIRROR.** If
  the mirror's error constructor stamps "where this was raised", then for a
  mirror that is itself a parser, that is a line number in the parser, not
  in the user's input. Check the message a user actually sees, not the one
  the test compares after normalisation.

- **Fix positions before wording.** If you unify wording first, every
  wording assertion has to be rewritten when positions are added to the
  same strings. Positions are also the cheaper half: they need no agreement
  about vocabulary.

- **The exception side discards its prefix.** When the original raises and
  the mirror returns a partial result plus an error marker, the two token
  streams before the failure are not comparable. Write rule 1 around that
  (compare the message and the position, not the prefix) rather than
  trying to make the mirror accumulate.

- **Pin the corpus as literals, not as file paths**, when the inputs come
  from a directory another system owns. The evidence must outlive the
  directory.

- **A comment saying "no comparison is possible here" is a hypothesis.**
  In Whence it stood for six rounds and was half right: wording was
  genuinely incomparable, position was not, and the sentence had bundled
  them.

## Verification

Run these against your own instance; the numbers are the Whence round-360
ones and are here as the SHAPE of an answer, not as values to expect.

```bash
# 1. the corpus reaches every refusal site the original declares
python3 -m pytest tests/test_parse_error_differential.py \
    -k reaches_every_host -q
#    -> passes only while cases == sites, both counted from source

# 2. acceptance is a biconditional, exemptions still fire
python3 -m pytest tests/test_parse_error_differential.py \
    -k "acceptance_agrees or load_bearing or both_outcomes" -q

# 3. positions agree, and the wording distinction is not vacuous
python3 -m pytest tests/test_parse_error_differential.py \
    -k "position_agrees or wording_is_still_not" -q

# 4. the implementation-free oracle, over the REAL corpus
python3 -m pytest tests/test_v24.py -k position_points_at -q
```

A finding is real when step 1's count is below the declared site count
before your change and equal to it after, and when at least one case moves
from "mirror accepts" to "mirror rejects". If nothing moves, say so — a
refusal differential that finds nothing has still measured something worth
recording (round 348's 16/16 clean is cited in this repo for exactly that
reason).

To prove the tests are load-bearing, revert one fix at a time in the mirror
and require the matching case to fail:

```bash
cp mirror.src /tmp/keep && sed -i 's/parse_args_rest(toks, pos, acc)/parse_args(toks, pos, acc)/' mirror.src
python3 -m pytest tests/test_parse_error_differential.py -k trailing_comma_call -q  # must FAIL
cp /tmp/keep mirror.src
```

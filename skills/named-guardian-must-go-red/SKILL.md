---
name: named-guardian-must-go-red
description: Use when a record claims that a specific test guards a specific line — "this is pinned by test_x", "the regression test for this is …", "a guard test keeps it from coming back" — and nobody has checked that removing the line turns that test red. Symptoms: a fix's write-up names its own pin; a test asserts on SOURCE TEXT (greps for a call, counts occurrences, reads `__file__`) rather than behaviour; the same behaviour has two entry points and one named guardian; a code comment says "pinned by test_y"; a suite is green and you cannot say which test would fail if a given call vanished. Covers falsifying the claim by neutering the call and requiring the named test to fail, telling a structural pin from a behavioural one by keeping the call's text while discarding its value, and separating "the suite caught it" from "the named test caught it". NOT for measuring coverage over a whole module (mutation testing), and NOT for a call nobody has claimed anything about.
---

# The named guardian has to go red

Write-ups say this constantly:

> …and `test_every_c001_site_consults_the_exemption_gate` pins it.

That sentence is a **claim about a counterfactual**: *if this call stopped
doing its job, that test would fail.* It is almost never checked, because
checking it means breaking the code on purpose, and the suite being green
feels like it has already answered.

It has not. A green suite says *no test is currently failing*. It says
nothing about which test would fail, or whether any would.

Two ways the claim goes wrong, both observed:

* **Nothing catches it.** The call is load-bearing and the suite does not
  reach it. The named test reaches a *sibling* path — same behaviour, second
  entry point — and the guardian was named by proximity.
* **Something catches it, but not the named test.** The record then credits
  a test that would stay green, and a later refactor that "keeps the pin"
  keeps the wrong thing.

## When to use (triggers)

Round 414 added this heading; `skill_lint --house` H001 had been ERROR-red
on this file since round 413 wrote it, because a skill's triggers must be
findable as a SECTION and not only inside the frontmatter description.

* A write-up, changelog entry or code comment names its own pin — "this is
  covered by `test_x`", "the regression test for this is …".
* A test asserts on SOURCE TEXT — greps for a call, counts occurrences,
  reads `__file__` — rather than on behaviour.
* The same behaviour has two entry points and one test named after it.
* You cannot say which test would fail if a given call vanished, and the
  suite is green either way.
* Someone is about to delete or refactor a call described as load-bearing.

**Not** for measuring coverage over a whole module (that is mutation
testing), and not for a call nobody has claimed anything about.

## The move

For a call site `C` claimed to be guarded by test `T`:

1. **Locate `C` symbolically** — file + enclosing function + callee name.
   Never a line number: a line number rots silently and has the tool
   confidently mutating whatever moved into its place, while a symbol that
   moved is a loud "this pin no longer resolves".
2. **Check `T` is green UNMUTATED, in the same throwaway copy the mutant will
   run in.** A verdict measured against a red baseline is not evidence and it
   fails in the flattering direction — the mutant looks caught.
3. **Neuter `C`** and run `T` alone. Red ⇒ the claim holds.
4. **If `T` stays green, widen once** to `T`'s own file (or the module's
   suite) and run again. Red ⇒ **misattributed**: something guards the call,
   and it is not what the record says. Green ⇒ **unguarded**.
5. **If `T` goes red, ask the other half**: rerun the suite with `T`
   deselected. Still red ⇒ `T` is one of several. Green ⇒ `T` is the only
   thing standing there, which is worth knowing before anyone deletes it.

## Keep the call, discard its value

The edit you choose decides which question you asked, and the difference is
not cosmetic:

| edit | source text | behaviour |
|---|---|---|
| replace the call with a literal | the name is **gone** | changed |
| `(CALL, LITERAL)[1]` | the name is **still there**, the call still runs | value discarded |

A test that greps the source for `gate(` passes the second and fails the
first. So:

> **Run the pin both ways. If the two verdicts differ, the pin is
> structural** — it proves a call is written, not that its answer is used.

That is not an argument for deleting structural pins. It is an argument for
not letting one stand in the record as the guardian of a behaviour.

Never use `keep_call` on a **bare** `f(x)` statement: the value is discarded
either way, the mutant is semantically identical, and every test stays green.
Reporting that as "unguarded" is a finding manufactured by your own edit. Use
statement deletion there instead.

## The instance

Round 411 of this program fixed a real bug — `claim_check.check_paths` had a
second entry point that never consulted the exemption gate — and pinned it
with a structural test whose own docstring says *"Deliberately coarse — it
cannot prove the call is on the right path."* Round 413 measured that
sentence. Same call, same test, two edits:

```
GP02  keep_call=true   exempt = (token_exempt_reason(target), None)[1]
      -> named test GREEN; 5 OTHER tests in the same file went red
      -> misattributed
GP03  keep_call=false  exempt = None
      -> named test RED
      -> guarded
```

Both verdicts are correct and their difference is the measurement.

The same run found a survivor. `mark_tails(body)` appears twice in the Whence
parser — once for `fn name(...)`, once for the anonymous `fn(...)` literal —
and the test named `test_parser_marks_tails_only_inside_fn_bodies` parses only
the named form. Deleting the anonymous branch's call left the whole file
green. The differential, once someone looked:

```
let go = fn(i, acc) { if i == 0 { acc } else { go(i-1, acc+i) } }
  intact  peak_depth 1   tail_calls 300
  deleted peak_depth 50  tail_calls 0      (the named-fn form: unchanged)
```

Real tail-call elimination, no test observing it, ten rounds after the branch
was written. Two doors, one behaviour, one named guardian — found *before* it
became a bug rather than 71 rounds after.

## Pitfalls

* **A timeout scored as a kill.** If the suite run is capped and the cap
  fires, a naive classifier calls that "the test failed", i.e. the pin held.
  A cap that turns *we did not look* into *we looked and it was caught* is
  the same defect one clock over. Give the suite its real budget or exclude
  its slow tier explicitly.
* **Exit codes that are not verdicts.** Under pytest only exit 1 means a test
  failed. 2–5 mean the suite never ran (config error, collection error,
  nothing collected) and are evidence about your harness, not about the pin.
* **Re-unparsing the file to apply the edit.** An AST round-trip deletes every
  comment and renormalises every string in the module. That is fine for a
  mutation *score* and fatal here: a source-grep pin reads the very text you
  destroyed, and the instrument manufactures its own findings. Splice the
  call's own source span; leave every other byte alone.
* **Registry rot.** Pins are claims about a checkout that keeps moving. Run
  the locate-only pass — no tests, no subprocesses, milliseconds — in the
  fast suite every time, so a moved symbol is caught by the next run rather
  than by the next campaign.
* **Grading your own homework.** Once you add the killer test, the wide-scope
  "did anything else notice?" question can only be answered by deselecting
  the test you just wrote. Deselect it and say so.

## The differential arm nothing moved

A guard test claims *removing the line turns me red*. Its close relative is
the **configuration differential** — a test that runs the same code twice
under two settings and asserts the outputs differ, or asserts they are the
same:

```python
new_out = run(src)                      # today's constant
old_cap = M.CAP
try:
    M.CAP = OLD_VALUE                   # "and here is how it used to behave"
    old_out = run(src)
finally:
    M.CAP = old_cap
assert new_out == old_out               # or != , either way
```

This has the same defect class and a nastier delivery: **the arm that is
supposed to be different may not be different at all**, and then the
assertion compares a thing to itself and passes with no signal whatever.
The usual mechanism in Python is a DEFAULT ARGUMENT:

```python
def render(node, cap=CAP):     # CAP is read at DEFINITION time, once
```

Patch the module global afterwards and the function never sees it. Round 452
wrote two such tests, watched both go green against a completely unchanged
renderer, and caught it only because a third test asserted a specific
expected STRING instead of an equality between two runs.

Other mechanisms with the same shape: a value captured in a closure at import
time; a constant already folded into a compiled regex, a lookup table or a
`functools.lru_cache`; a setting read once into `self._x` in `__init__`; a
subprocess that does not inherit the environment variable you exported; a
config file the code re-reads only on start.

**The check, and it costs one command.** Before trusting any test whose two
arms differ only by a setting, prove the setting moves the OUTPUT on an input
where it obviously must:

```python
assert out(cap=3) != out(cap=24), "the differential would be vacuous"
```

Pick the input where the difference is undeniable — not a corpus program,
whose whole point in such a test is usually that it does NOT change. Round
452's was `print([[[[[1]]]]])`: `[[[[[…]]]]]` at cap 3, `[[[[[1]]]]]` at cap
24. Record the check beside the test, because the next reader will have the
same doubt.

The rule underneath: **a constant a test cannot move is a constant nothing
measures**, and an equality between two runs of the same code is the
assertion shape that hides it. Resolve such constants inside the function
body rather than in the signature — it costs one `if x is None` and makes the
knob testable.

## Verification

```bash
cd ~/agi-research-nuc-llm
python3 harness/swe/guardpin.py check                 # registry schema
python3 harness/swe/guardpin.py locate                # every pin still resolves; prints each diff
python3 -m pytest -q harness/tests/test_guardpin.py   # offline half, 14 tests
python3 harness/swe/guardpin.py run --only GP03       # one pin, end to end
```

`locate` prints a one-line unified diff per pin. If a diff is longer than the
statement you meant to edit, the tool is rewriting more than the call and
step 3's answer is about the wrong experiment — fix that before reading any
verdict.

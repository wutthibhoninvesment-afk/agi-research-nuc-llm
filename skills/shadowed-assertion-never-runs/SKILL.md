---
name: shadowed-assertion-never-runs
description: Use when one test function holds both a NOISY assertion (a count, a size, a total, a timestamp, a version) and a SIGNAL assertion (a class list, a set of locations, a schema, an identity) — because most runners stop a test at its first failing assert, so the noisy one hides the signal one on exactly the occasions the signal matters. Symptoms - a test whose failure message has said "N != M" for several releases; a pinned list nobody remembers seeing fail; a "same items, same locations, before and after" comment above an assertion that has not been evaluated in months; a count that a routine, expected, information-free change moves every time. Covers finding the shadow, splitting the node, and gating it with an AST check so it cannot re-form. NOT for a test that is skipped or xfailed (that is skip-reason-is-a-claim) and NOT for a bound that only moves one way (that is ratchet-needs-a-conservation-invariant).
---

# The assertion on the line after the one that always fails first

`pytest`, `unittest`, `go test`, JUnit and every other runner built on
exceptions stop a test function at its **first** failing assertion. So this:

```python
def test_the_residual_is_the_shape_we_think_it_is(rows):
    assert len(rows) == 114                  # SIZE  — moves on every addition
    assert sorted(r["cls"] for r in rest) == [...]   # SHAPE — the actual claim
```

is not two checks. It is one check, plus a claim that is evaluated **only
when the first one happens to pass**. If the first one is the kind of number
that a routine, expected, information-free change moves — a corpus size, a
row count, a total, a build timestamp, a version string — then the second
assertion is dark for precisely the events it was written for.

Round 494 of this program found a node in exactly that shape. `assert
len(rows) == 114` sat three lines above an eleven-class list and a table of
pinned source locations. Six separate rounds added a test file, the count
moved, and the node reported `115 != 114` each time. **Neither of the two
shape assertions below it had been evaluated in six rounds.** In that window
one of them went stale (a pinned location moved 129 → 138 when an unrelated
file was edited) and the other acquired a genuinely new entry — the only
finding in the whole episode — and the suite reported neither. The file's own
comment three screens up said "the count below moves whenever the corpus
grows, and the list below it moves only when something genuinely unreadable
arrives", which is the diagnosis, written above the two lines that made it
unenforceable.

**The order is the bug.** Not the count, not the list.

## When to use (triggers)

* A test node contains a `== <int>` / `len(...) == N` / `<= N` assertion AND
  a list-, set-, dict- or schema-equality assertion.
* A test's failure message has been the same "N != M" across several
  releases, and someone bumps N each time.
* A comment says "same items, same locations, before and after", "unchanged",
  "invariant" — and you cannot remember ever seeing that assertion fail.
* A pinned list of file:line coordinates, golden IDs, or fixture names sits
  below anything that counts.
* You are about to hand-bump a number to green a test. Ask what is *below*
  the number before you bump it.
* You just fixed a failing count and the test still fails — that second
  failure has been latent for as long as the first one existed.

**Not** for a skipped or `xfail`ed test (`skip-reason-is-a-claim`), and not
for a one-way bound (`ratchet-needs-a-conservation-invariant`, which this
pairs with: a ratchet is an assertion that goes green for the wrong reason,
this is an assertion that never runs at all).

## Steps

1. **Find the shadows mechanically, not by reading.** One `ast` walk over the
   test tree. For each test function, list its `Assert` nodes in source
   order; report any function where a *magnitude-vs-literal* comparison
   precedes a *structure-equality* comparison.

   ```python
   import ast
   def asserts(fn):
       return [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
   def is_magnitude(a):
       t = a.test
       return (isinstance(t, ast.Compare) and len(t.comparators) == 1
               and isinstance(t.comparators[0], ast.Constant)
               and isinstance(t.comparators[0].value, int)
               and not isinstance(t.comparators[0].value, bool))
   ```

   Do this before forming any opinion about which nodes matter. The one that
   bit round 494 was not the one it would have guessed.

2. **For each hit, run the shadowed assertion ALONE and see what it says.**
   This is the measurement, and it is usually a surprise. Comment out the
   count, or evaluate the expression in a scratch script against live data.
   Round 494 did this and found the pin below the count had been wrong for
   two releases.

   ```bash
   python3 -c "import mymodule; rows = mymodule.harvest(); print(sorted(...))"
   ```

3. **Decide which assertion is the SIGNAL.** The test is named after one of
   them and it is usually not the count. Ask: *which change is this
   assertion supposed to catch, and is that change routine or rare?* An
   assertion that fires on routine, expected changes is noise wherever it
   sits; it is a maintenance schedule, not a check.

4. **Move the noise out of the node — do not reorder inside it.** Reordering
   puts the shape first and shadows the size, which is better but still one
   node with two jobs and one verdict. Give each its own test function so the
   suite reports two independent facts.

5. **Make the noisy assertion stop being noisy.** If a number moves on every
   routine change, the unit is wrong. Derive it from a declared per-item
   ledger, or from the thing that actually causes it, so that a routine
   change is a routine one-line declaration rather than a re-guessed total.
   Round 494 replaced five whole-tree totals with the sums of a per-file
   ledger; the count now changes in one place, checked, instead of six.

6. **Gate the split so it cannot re-form.** A structural test over the
   suite's own AST, asserting the signal node contains no magnitude
   assertion. Prose in a comment is what failed for six rounds here.

7. **Falsify the gate both ways, in the same commit.** Run it against the
   code as it was *before* the split and watch it report the exact lines you
   moved; and feed it a function containing only structure assertions and a
   `> 0` positivity check and watch it stay silent. A gate that has only
   been seen green is a gate nobody has tested.

8. **Assert the node still EXISTS under the name your gate looks up.** A
   structural gate keyed on a test name silently passes forever the day
   somebody renames the test. One extra assertion, run first.

## Pitfalls

- **Bumping the number and declaring victory.** Greening the failing assert
  makes the ones below it *reachable*; they may fail immediately, and that
  failure is not new — it has been latent the whole time. Budget for it.
  Round 494 predicted "6 literals to green this" and the answer was 8 plus a
  list entry, for exactly this reason: it got the shadowing wrong inside its
  own arithmetic about the shadowing.
- **Assuming the shadowed assertion is fine because the code looks fine.**
  Its staleness is caused by edits *elsewhere*. A pinned `file:line` goes
  stale whenever anyone inserts a line above it, which is the most ordinary
  edit there is.
- **Fixing only the newest entry of a pinned list.** If the pin names one
  file or one item, widen it to the whole population first — round 494 found
  its stale entries by widening the pin, not by reading it.
- **Splitting the node and leaving the totals hand-written.** You have
  stopped the shadow and kept the tax. Step 5 is not optional if the number
  moves every release.
- **A gate keyed on `__name__` or a test id.** Node ids are also keyed on by
  CI history, flake trackers and red-attribution tooling; renaming a node to
  make a gate read better discards its history. Prefer a stale name plus a
  comment over a rename mid-incident.
- **Running the sweep of step 1 against a tree you are editing.** On a
  single-core box especially: the AST walk reads files from disk, and a file
  saved mid-walk gives a line number that matches nothing.

## Verification

```bash
cd ~/agi-research-nuc-llm/languages/whence

# 1. the split node and its gate, green at HEAD
python3 -m pytest -q -c pytest.ini -p no:cacheprovider \
    tests/test_testcorpus_contributions.py \
    -k "shadow or shape_node_exists or gate_would_fire or gate_does_not_fire"

# 2. the gate's TRUE-positive half: a synthetic function of the pre-split
#    shape must be reported, at lines 2 and 3
python3 -m pytest -q -c pytest.ini -p no:cacheprovider \
    tests/test_testcorpus_contributions.py \
    -k gate_would_fire_on_the_shape_node_as_round_492_left_it

# 3. the gate's FALSE-positive half: a list-equality plus a `> 0` must NOT
#    be reported as a magnitude assertion
python3 -m pytest -q -c pytest.ini -p no:cacheprovider \
    tests/test_testcorpus_contributions.py \
    -k gate_does_not_fire_on_the_shape_assertion_itself

# 4. and the shadow itself, against the code before the split — the number
#    that makes any of this evidence rather than a story
git show 336a919:languages/whence/tests/test_testcorpus_census.py \
    > /tmp/census_before.py
python3 - <<'PY'
import ast
src = open("/tmp/census_before.py", encoding="utf-8").read()
fn = [n for n in ast.walk(ast.parse(src))
      if isinstance(n, ast.FunctionDef)
      and n.name.startswith("test_the_residual_that_is_not_string_building")][0]
for a in [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]:
    print(a.lineno, ast.unparse(a.test)[:60])
PY
```

Step 4 prints the count assertions at lines 1410 and 1411 and the shape
assertions below them. **That ordering is the whole finding**: green is not
the interesting outcome, the interesting outcome is that the two lines below
had not been evaluated by any of the six rounds that hit this node.

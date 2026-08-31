# Worked example — `languages/whence`, round 398

The case the skill is derived from, with the code, the two populations and
the numbers that moved. Read this when the abstract steps are clear but the
shape of the filter is not.

## Contents

- [The claim](#the-claim)
- [The filter](#the-filter)
- [The defect](#the-defect)
- [What was excluded](#what-was-excluded)
- [After the fix](#after-the-fix)
- [How the claim is pinned now](#how-the-claim-is-pinned-now)

## The claim

`tests/test_parse_error_differential.py` compares a Python parser against
a self-hosted parser written in the language it parses. Round 396 added
`test_the_want_half_of_every_shared_message_now_agrees`, whose docstring
said:

> Ten of the 51 rejected programs produce `expected X, got Y` on BOTH
> sides. […] All ten want halves now agree.

Green. Correct as an assertion. Wrong as the sentence people quoted.

## The filter

```python
_EXPECTED_SHAPE = re.compile(r"^expected (.*?), got (.*?)(?: \(|$)")
...
mh, mg = _EXPECTED_SHAPE.match(h), _EXPECTED_SHAPE.match(g)
if not (mh and mg):
    continue                    # <-- membership decided here
shared.append(name)
```

As a sentence: *both sides produced a message containing `, got `.*

## The defect

The guest's `expect_name` helper wrote no `got` clause at all, and was one
function standing in for six different host spellings:

```
host   expected field name, got '}'
guest  expected a name
```

As a sentence: *the guest omits the `, got ` clause at seven sites.*

The two sentences name the same substring. The filter was reading the field
the defect removed.

## What was excluded

Seven of the 51 programs, by name:

| program | host | guest |
| --- | --- | --- |
| `missing-let-name` | `expected a name, got '='` | `expected a name` |
| `kw-as-name` | `expected a name, got 'let'` | `expected a name` |
| `check-no-label` | `expected a string label after 'check', got 1` | `expected a string label after 'check'` |
| `dot-no-field` | `expected field name after '.', got end of input` | `expected a name` |
| `trailing-comma-rec` | `expected field name, got '}'` | `expected a name` |
| `trailing-comma-param` | `expected parameter name, got ')'` | `expected a name` |
| `trailing-comma-shape` | `expected field name, got '}'` | `expected a name` |

The bottom **four** have a want half that disagreed the entire time the
test was green and claiming otherwise. Step 3's weaker comparison — the
`expected X` prefix alone, ignoring the missing clause — would have found
all four without any fix at all.

## After the fix

Giving the guest the missing clause moved the POPULATION, which is the
evidence the filter was defect-shaped:

| | before | after |
| --- | --- | --- |
| shared set (the filter's output) | 10 | **20** |
| want halves agreeing | 10 of 10 | 20 of 20 |
| got halves agreeing | 0 of 10 | **20 of 20** |
| whole messages agreeing (full corpus) | 12 of 51 | 34 of 54 |

Note the second row: the *rate* the original test reported was 100% before
and 100% after. Only the denominator carried the information.

## How the claim is pinned now

```python
assert len(shared) == 20, sorted(shared)               # population
assert sorted(want_agree) == sorted(shared)            # claim
assert sorted(got_agree) == sorted(shared)             # claim
still = sorted(set(shared) - set(full))
assert still == [...five names...], still              # named residual
```

and, over the FULL corpus rather than the filtered one, an assertion that
every remaining divergence belongs to one of two enumerated classes — so a
third class arriving is a red test rather than an unexamined remainder:

```python
assert len(hint_only) == 18, sorted(hint_only)
assert sorted(other) == ["rebind", "rebind-indented"], sorted(other)
```

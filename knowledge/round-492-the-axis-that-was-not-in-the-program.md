# Round 492 (language C) — the axis that was not in the program

**Subject:** round 488's next-step 1 — *"`scale_cases()` is still eleven
hand-written cases and the name axis is the only one this round derived …
**List the inputs each repr interpolates and say which of them an author
sizes.**"* — closed together with its next-step 4 (replace the regex cap
gate with something behavioural), because they are the same question from
two ends.

**Predictions banked at `154d1ef` BEFORE any measurement**
(`state/whence/round-492/predictions.md`). Scored in §10.

---

## 1. The one-sentence finding

v0.48 derived the probe from three live tables and varied three tokens in
it — a string literal's body, an identifier, a run of digits — because
those are the three a Whence **program** can make arbitrarily long. Every
probe this implementation has ever run **is** a program. So the derivation
was complete over the language and silent about everything else:

```
repr(Interpreter(max_depth=10 ** 500))     645 chars,  REPR_CAP is 240
```

`max_depth` is a **public constructor argument of the embedding API**. No
Whence source text moves it, so no probe that is a program could ever have
varied it — not v0.47's eleven hand-written cases, and not v0.48's derived
one, however large its tokens. **Decision 62's three tables describe the
language, and this input is not in the language.**

## 2. The instrument: the inputs, not the classes

The subject of decision 63 is neither classes nor tokens. It is the
**expressions each repr interpolates**, derived from the source with `ast`:

```
python3 reprsweep.py --inputs
89 interpolated input(s) over 19 repr source(s); 76 classified by table,
11 by the composed-return rule
by family: {'text': 15, 'structure': 23, 'constant': 13,
            'internal': 36, 'embedding': 2}
```

Each input is assigned an **axis** whose **family** says who sizes it:

| family | who sizes it | inputs | witnessed? |
|---|---|---|---|
| `text` | the author, as a long TOKEN | 15 | yes — v0.48's three tokens |
| `structure` | the author, by writing MORE program | 23 | yes — 8 axes |
| `embedding` | **the embedder, in host code** | **2** | **new this round** |
| `constant` | this implementation | 13 | n/a, not author-sized |
| `internal` | composed from this function's own inputs | 36 | n/a |

Both directions are gated exactly as `UNREACHABLE` is: an expression with
no row is an **ERROR** (`unclassified`), a row naming an expression no repr
interpolates is **STALE**. `INPUT_AXIS`'s keys are the **unparsed
expression text**, so editing a repr expires its own classification.

**That gate fired inside this round, on this round's own fix.** Wrapping
`self.max_depth` in `_clip` changed the key to `_clip(str(self.max_depth))`;
the sweep immediately reported one stale row and one unclassified input.
A self-expiring table is the difference between a classification and a
comment.

Five constructs count as interpolation (`%` operands, f-string
`FormattedValue`s, the non-literal side of a `"lit" + x`, a `join`
argument, and a returned `Call`/`Name`/`Attribute`/`Subscript`/`IfExp`).
The deriver is **deliberately over-inclusive**: an extra row costs one
table entry, a missing one costs a whole axis. The `return` rule is not
decoration — `ast_nodes._node_field` ends in a bare `return repr(v)`, and
that is where a 5,000-character literal entered the AST repr in v0.48.

### Three defects in the deriver, each found by an answer that looked fine

1. **A resolver that reads module globals cannot see a method.**
   `_simple.<locals>.__repr__`'s whole body is `_cap(self._repr_at(0))`,
   and `_repr_at` is a closure in the class dict. The delegate closure
   stopped at `__repr__` and **never reached `_node_field`** — the
   function v0.48's own R2 violation was fixed in. A delegate analysis
   blind to methods is blind to the delegate that has the defect.
2. **…nor a function-local import.** The same repr reaches `_cap` by
   `from whence.values import _cap` *inside* its body. Without that
   branch it reported calling nothing — **which is the answer
   `Interpreter.__repr__` gives for a real reason**, and the two must not
   look alike.
3. **A boundary must name what crosses it.** `Guess.__repr__` is
   `_frame(show_payload(...))` and `Record.__repr__` is
   `_frame("record " + show_payload(...))`. The same delegate was
   classified in one class and invisible in the other, decided by whether
   a literal happened to sit next to it.

## 3. The fix: `_clip` is the design, `_cap` is the backstop

`_cap` alone gave a compliant 240 characters — of which 200 were the
author's integer, and the sentence the repr exists to say was gone. Same
shape as `Prov.detail` one class over (decision 62), so the same fix:

```
before  645 chars   <whence interpreter: 37 builtins, max_depth 1000…000 — the ENGINE…>
_cap    240 chars   <whence interpreter: 37 builtins, max_depth 000000000000000…>
_clip   184 chars   <whence interpreter: 37 builtins, max_depth 10000000000000000…
                     — the ENGINE, not a value or a scope; run(source) executes a
                     program and returns its top-level Env>
```

The **default** repr is byte-identical to v0.48's, 149 characters.

## 4. Two cap checks, and neither subsumes the other

Round 488's next-step 4 asked for the regex gate
(`test_cap_is_the_only_place_repr_cap_is_compared`, matching
`\s*if len\(.*REPR_CAP`) to become behavioural. It took **two**, and the
interesting result is that neither is enough:

| | `routing_manifest()` | `cap_response()` |
|---|---|---|
| kind | static, total | behavioural |
| asks | is `values._cap` in this repr's transitive delegate closure? | lower `REPR_CAP` to 40/80 and re-take every repr |
| found | `Interpreter.__repr__` was the ONLY repr with an empty closure | 3 failing subjects, all that one class |
| blind to | a repr that calls `_cap` and **discards** the result | a repr already **shorter** than the lowest cap |
| reports its blindness? | n/a (total) | yes — **11 of 64 subjects `vacuous`**, on the CLI |

`vacuous` is the honest form of round 490's lesson: a gate that passes on
an input it never exercised is worth what `sar --strict`-exits-0-on-zero-
captures was worth. Both checks are **falsified** in `tests/test_v49.py` —
v0.48's `Interpreter.__repr__` is put back and each names it, and a repr is
built for each check's own blind spot to show the other one catching it.
The v0.48 regex test is **kept**: it is a different claim (the cut is
written ONCE), and it is still true.

That `Interpreter` was the one unrouted repr is not a coincidence. It is
the class whose only unbounded input comes from the embedding API — the
family nobody had a probe for.

## 5. The universe was three modules of seven

`probe_manifest()`'s `gaps: 0` was computed against
`node_classes() | runtime_classes()` — `ast_nodes`, `values`, `interp` —
and the set of **modules** was itself a hand-written list. `package_classes()`
derives it from the package:

```
universe 48, reached 34, constructed 1, declared unreachable 13,
gaps 0, stale exceptions 0, outside_universe 0
```

The widening adds exactly six classes (`ast_nodes.Node`, `lexer.Token`,
`lexer.LexError`, `parser.Parser`, `parser.ParseError`,
`timetravel.TimeTravelDebugger`) and found one real defect:

```
repr(TimeTravelDebugger())
  <whence.timetravel.TimeTravelDebugger object at 0x775c81dfdd60>
```

**Decision 58's original failure string, five rounds after the rule that
outlawed it, in the one module no universe ever contained.** It now reprs
in `Env`'s shape: bounded head of the checkpoint names, count kept whole,
escape hatch named.

Two exceptions are declared with a **measurement** rather than an
assertion: `LexError` and `ParseError` are handed to a caller (by being
raised), but their rendering is a DIAGNOSTIC and diagnostics are decision
48's. The longest `repr` this round could provoke is **147** characters
(on a 5,000-character string literal) and **120** (on a 400-character
identifier), because the message quotes the syntax at fault and never the
offending token's text.

`probe_manifest()` also gained the direction it never computed:
`outside_universe` = `reached − universe`. **0 at HEAD — a negative
CONTROL, not a finding.** It is the check that would have said so if a
reached class had lived in a module the universe did not contain.

### Reachability from `run()` is sufficient, not necessary

Decision 60's rule names classes reachable from `Interpreter.run()` along
public attributes. Decision 58's sentence is the general one — *a value
this implementation hands a caller is a surface* — and a class the caller
**constructs** is on the same side of that boundary. `CONSTRUCTED_SURFACES`
is that second door, audited by building a witness the way an embedder
would. `Interpreter` satisfies both conditions; `TimeTravelDebugger`
satisfies only the second, which is why it sat outside every sweep.

## 6. A test double is a claim about the collaborator

Building the `TimeTravelDebugger` witness **through its public API** — the
way an embedder would, rather than by writing its slots — raised:

```
TypeError: Env.get() takes 2 positional arguments but 3 were given
```

`snapshot()` read the checkpoint name as
`env.get('_last_snap_name', 'unnamed')`. All **eleven** tests in
`tests/test_timetravel.py` are green and every one passes a local
`MockEnv`/`NamedEnv` whose `get` has a host-dict signature, so the suite
**never touched the only `Env` this package defines**. The method's primary
path had never been executed against its real collaborator.

Fixed by reading `env.vars` first (a plain dict on the real class and on
every double, unwrapping a `Prov` payload) and keeping the
`get(key, default)` path for the two doubles that name their checkpoints
through it. Both directions are now tested.

## 7. Three sentences, three rounds, one shape

v0.48 found two comments asserting compliance that six rounds of probes had
never contradicted (`values.REPR_CAP`'s and `_frame`'s). This round found a
third, in the class next door — `Builtin.__repr__`'s *"all three spellings
appear in `_install_builtins`"*. Measured over the live global scope:

```
int  33      pair 4 (contrast, diverge, range, steps)      None 0
```

The `any arity` branch is **kept** — "None for any" is `Builtin.__slots__`'s
stated contract and a directly constructed `Builtin` reaches it — and it is
now tested rather than asserted. The pattern is now three for three: each
false sentence was written by the round that introduced the rule it
described, and each was true of everything anybody had built.

## 8. The negative results

* **Zero new R2 violations along any program-STRUCTURE axis.** Arity,
  nesting depth, statement count, element count, `Miss.reasons` count,
  `MergedProv.count`, line number, scope depth — 30 axis witnesses, all
  under the cap. The head-and-count cuts plus `_cap` already hold. This
  was predicted (P7) and it is the point of enumerating.
* **`outside_universe` is 0.** The new direction finds nothing today.
* **`nodeguard`-shaped honesty:** `cap_response`'s 11 vacuous subjects are
  a precondition that happened to hold, not a gate that fired.

### Q1, answered by measurement rather than left open

`Env.__repr__` **walks** the parent chain to count `depth`. Whence scopes
are LEXICAL, so recursion does **not** deepen the chain — a call Env's
parent is the closure's DEFINING Env. Measured: a 200-deep recursion
returning a closure gives a chain of **≤3**. What deepens it is nested
*definitions* whose closures are then called one at a time, and
`parser._enter` caps nesting at 60: 20 nested definitions chained through
19 calls give **39**. The string is bounded (`%d`); the WALK is O(depth).
That is a COST property, and R1–R4 are all properties of the string — no
rule added this round, recorded as a next step.

## 9. Tests and gates

### `reprsweep.py` v0.49 — what is new

| CLI | asks | HEAD |
|---|---|---|
| `--inputs` | every expression each repr interpolates, with its axis | 89 / 19 sources, 0 unclassified, 0 stale |
| `--routing` | is `values._cap` in each repr's delegate closure? | 35 reprs, 0 unrouted |
| `--caps` | R2 behaviourally at caps 40 / 80 / 240 | 64 subjects, 11 vacuous, 0 failing |
| `--manifest` | coverage of every derived axis | universe 48, reached 34, constructed 1, declared 13, gaps 0, stale 0, outside 0 |
| (default) | R1–R4 over rows + scale + **axes** | 35 rows, 44 scale, 30 axis, **0 violations** |

`tests/test_v49.py` — **48 passed in 38.08 s** (solo). Every gate is
falsified in it, not just asserted:

* `test_the_static_check_catches_a_repr_that_stops_routing` and
  `test_the_behavioural_check_catches_it_too` put v0.48's
  `Interpreter.__repr__` back and require each check to name it.
* `test_the_static_check_is_blind_to_a_discarded_cut` and
  `test_the_behavioural_check_is_blind_to_a_short_repr` build a repr for
  each check's own blind spot and require the *other* one to catch it.
* `test_the_cli_exits_nonzero_on_a_bad_axis_table` adds a bogus row and
  requires `--inputs` to exit 1.
* `test_scope_depth_needs_nested_definitions_not_recursion`,
  `test_the_merge_count_witness_really_merges`,
  `test_the_identifier_witness_actually_lists_the_long_name` and
  `test_the_arity_witness_covers_the_spellings_that_exist` check that each
  witness moves the axis it exists for.


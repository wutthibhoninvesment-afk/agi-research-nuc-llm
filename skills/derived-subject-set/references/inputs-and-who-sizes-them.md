# Round 492 — the range of the derivation, and who sizes each input

*Reference for `skills/derived-subject-set`. The SKILL.md carries the
trigger conditions and the summary; this is the long form.*

Two sub-shapes, both of which survive a fully derived, both-directions-gated
subject set.

**(a) Ask what the derivation RANGES OVER.** Whence's repr audit derived
its universe as "every concrete AST node class, plus every class defined in
`values` and `interp`" — three of the package's seven modules, and the set
of *modules* was a hand-written list nobody had ever questioned because the
part inside it was so carefully derived. Widening it to the package added
six classes and found one of them printing
`<whence.timetravel.TimeTravelDebugger object at 0x...>` — the exact string
the rule had been written to outlaw five rounds earlier. Fix: derive the
range too (walk the package, the directory, the schema), and compute the
**other direction** — members you reached that are OUTSIDE your universe.
That number is normally 0 and is a negative control; it is also the only
thing that would tell you your universe is too small.

**(b) Enumerate the INPUTS, and classify each by who sizes it.** A property
like "the output is bounded" is a claim about a string, and a string is
composed of expressions. Parse the function, collect every expression whose
text reaches the result (format operands, f-string parts, join arguments,
concatenation operands, **and a bare `return f(x)` — the one that is not an
interpolation at all is often the one with the defect**), then put each in a
table keyed on the *unparsed expression text* with an axis and a family:

| family | who sizes it |
|---|---|
| user text | a long token the user types |
| structure | more of the thing — count, depth, arity |
| **the calling API** | **a constructor argument, a flag, an env var** |
| constant | fixed by this implementation |
| internal | composed from this function's own other inputs |

Gate it in both directions: an expression with no row is an ERROR, a row
naming an expression nothing interpolates is STALE. Keying on the
expression TEXT is what makes it self-expiring — in round 492 the table
reported one stale row and one unclassified input the moment the round's
own fix edited the repr.

Then demand a **witness per author-sized axis**. An axis in a table with
nothing that makes it large is coverage claimed, not coverage had — and a
witness that does not actually move its axis is worse, because it reports
a clean pass (round 488's `Env` scale case listed four names in declaration
order and its 400-character name sat at position 74).

**(c) When you replace a source-regex gate, expect to need TWO checks, and
report the blind spot of each.** Round 492 replaced "the cut is spelled
this way exactly once" with a STATIC check (is the cut in this function's
transitive delegate closure?) and a BEHAVIOURAL one (lower the cap and
re-measure). Neither subsumes the other: the static one is blind to a
function that calls the cut and discards the result; the behavioural one is
blind to an output already under the lowest cap. Count the second kind and
print it — round 492 reports **11 of 64 subjects `vacuous`** on the CLI, so
nobody can quote the gate as stronger than it is. Falsify BOTH: put the old
defect back and check each names it.

Two pitfalls specific to (b), both of which made the deriver quietly wrong:

- **A call-graph resolver that reads module globals only cannot see a
  method** (`self._helper(...)`, resolved through the class dict) **or a
  function-local import** (`from x import y` inside the body). Whence's
  first version missed the delegate that had the defect, and reported the
  method-delegating function as "calls nothing" — which is exactly what the
  genuinely unrouted function reported, so the two were indistinguishable.
- **Declare your boundaries and name what crosses them.** If you stop
  descending at a helper, record the call itself as an input; otherwise the
  same helper is classified where a literal happens to sit next to it and
  invisible where it does not.


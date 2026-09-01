# Round 416 (language C) — the direction nobody mutated

**Track:** C (language design & implementation — Whence)
**Subject:** `languages/whence/examples/self_eval.lang`,
`languages/whence/checkpin.py`, `state/whence/round-416/eval-pins.json`
(new), `languages/whence/tests/test_checkpin.py`, `tests/test_v23.py`,
`tests/test_v31.py`, `tests/test_self_eval.py`,
`skills/mutate-the-rule-both-ways/` (new),
`harness/wiring-registry.json`, `harness/tests/test_wiring_audit.py`,
`languages/whence/nuc_scripting/ncs_engine.py` (**deleted**)

Round 415's next-step 6 (round 414's item 1): *"`examples/self_eval.lang`'s
guest EVALUATOR still has no pin. Its first ~1050 lines duplicate the guest
parser `checkpin`'s registry covers; the evaluator — closures, env,
provenance, the guest's own `why` — is the larger and less-tested half."*
Round 415's next-step 7 carried round 414's item 3: *"giving every rule with
two opposite falsifying edits both of them."*

This round did both at once, because doing the second is what made the first
worth doing. The registry is not 16 mutants of the guest evaluator. It is
**16 rules mutated in BOTH directions under the same guardian**, and the
direction turns out to be the variable that decides the verdict.

---

## 0. Headlines

1. **Of 11 evaluator rules mutated both ways under one `check` label, not
   one label caught both directions.** Zero. Eight split cleanly along the
   direction, one split the other way (for a reason its predicate
   predicts), and two were invisible in both.

2. **The direction of the mutant is associated with the verdict at
   p = 0.009** (Fisher exact, two-sided, n = 29):

   ```
                 guarded  finding
     "-" does less:  11       4
     "+" does more:   3      11
   ```

   The three `"+"` mutants that were caught are the three where an author
   had already written the other side on purpose. There is no fourth.

3. **The mechanism is predicate monotonicity, and it is readable off the
   assertion before the run.** `missed(X)` is monotone in "the evaluator
   misses more". `contains(X, s)` is monotone in "the evaluator says more".
   `len(blame(t)) > 0` is monotone in "the walk reports more". A guardian
   is not a guard in the direction it is monotone in, however badly the
   rule is broken. This is not the same defect as round 414's — that one
   was about the probe VALUE; this one is about the FAILURE DIRECTION, and
   an `== V` assertion is immune to round 414's and not to this.

4. **`inert` was hiding a second cause, and the two want opposite
   responses.** *Nothing guards this rule* says "write a check". *The rule
   has two implementations and you removed one* says "write nothing — the
   suite is right that the behaviour did not change". Both read
   `guardian green, n_red == 0`. `checkpin` grew `also` (apply a chain of
   edits) and `redundant_with` (name the wider pin), and the new
   **`redundant`** verdict is what separates them. Two of 16 rules in this
   file are redundant, and both would have collected a pointless new test.

5. **A `guarded` verdict is not self-validating either.** The most direct
   removal of `and`'s short-circuit came back `guarded` — and for the wrong
   reason: it routed evaluation through an `else` arm whose payload
   assumes the left operand is `true`, so it changed the VALUE as well as
   the branch. The isolated form (`EP04m2`) is a different pin and had to
   be written after the fact.

**Result: `48%` → `83%`. 29 scored pins before (14 guarded, 15 findings, 0
errors); 30 after (25 guarded, 5 findings, 0 errors, 2 redundant). Both
negative controls HELD on both runs. `self_eval.lang`: 166 → 172 checks.**

---

## 1. Why the direction is a free parameter nobody varies

`guardpin` (round 413) and `checkpin` (round 414) both ask the same
question: break the rule, does the named guardian go red. Neither asks
*which way*. Looking back at round 414's 22 pins, 21 of them delete, empty,
or identity-out a rule; one (`CP04`) adds quoting. That is not a criticism
of round 414 — it is the default everywhere, because a bug is imagined as
something missing.

The direction is not neutral, because assertions are not symmetric:

| assertion in `self_eval.lang` | count | monotone in | blind to |
| --- | --- | --- | --- |
| `missed(gv(...))` | 31 | "misses more" | a rule that misses MORE than it should |
| `contains(str(...), s)` | 24 | "says more" | a message that grows a clause |
| `not is_num(...)` / `not contains(...)` | 9 | "says no more often" | a predicate that says no to everything |
| `gv(...) == V` | 94 | *value*: neither | *coverage*: the branch it does not probe |

Two thirds of the file is `== V`, which is two-sided in the value it
compares — and one-sided in the **branches, arms and operands it visits**.
`check "guest if records which branch ran": pi.op == "if took then-branch"`
is a perfectly two-sided assertion about a value, resting on one probe that
takes the then-branch. Relabelling the ELSE arm `"if took then-branch"`
left all 166 checks green.

## 2. The registry

`state/whence/round-416/eval-pins.json`. 16 mechanisms in the guest
evaluator (`lookup`, `miss_reason_hint`, `miss_names_unbound`, `eval_and`,
`eval_if` ×2, `guest_kind`, `is_num`, `raw_deep_eq`, `apply_binop`'s `==`,
`check_ret`'s label, decision 2, `guest_is_origin_miss`,
`drop_line_suffix`, `NAMING_OPS`, `dv_same_payload`), 30 scored pins, 2
negative controls. Two fields are new and are the whole point:

```json
{ "id": "EP02p", "dir": "+", "predicate": "contains(str(X), s)",
  "mechanism": "M2 miss_reason_hint: `miss <unbound name>` gets the cure clause",
  "guardian": "guest miss <unbound name> names the miss-reason cure",
  "edit": "fn_replace", "target": "miss_reason_hint",
  "becomes": "fn miss_reason_hint(n) { \" (a miss reason is a string: write `miss \\\"\" + n + \"\\\"`) [or use a literal]\" }" }
```

`dir` is `-` (the rule does less) or `+` (the rule does more). `predicate`
is the SHAPE of the guardian's expression, written down **before** the run
so a verdict predicted from the shape is evidence the shape is the cause.

`test_the_eval_registry_pairs_directions_under_one_guardian` asserts the
pairing rather than leaving it to this document.

### The `+` mutants are ordinary refactor damage, not noise

This is the objection worth answering first: a `+` mutant could be a
contrived edit nobody would ever write, in which case its invisibility is
uninteresting. Each of these is something a careless change genuinely does:

* `EP01p` — `lookup`'s unbound-name miss grows a trailing clause
  (`"unbound name 'x' [scope chain searched]"`). Somebody adds diagnostic
  detail. The reference implementation does not have it.
* `EP04p` — `and` short-circuits on `true` as well as `false`. A copy-paste
  from `eval_or`, whose short-circuit value IS `true`.
* `EP06p` — the `else` arm labelled `"if took then-branch"`. A copy-paste
  inside one function.
* `EP09p` — `raw_deep_eq` widened to refuse records as well as callables.
  Somebody "fixes" a structural-comparison bug by refusing more.
* `EP13m` — `guest_is_origin_miss` weakened from *missed with no missed
  input* to *missed*. Somebody simplifies a two-clause predicate.

## 3. The result

`state/whence/round-416/run-before.json` (against `git show HEAD:`'s file,
so it reproduces without this session), 29 scored pins, 104 s:

```
14 guarded, 15 findings, 0 errors, score 48%
CONTROL NC01: inert (n_red=0) -> HELD
CONTROL NC02: inert (n_red=0) -> HELD
```

Eleven mechanisms had both directions judged by the SAME guardian:

| mechanism | `-` does less | `+` does more |
| --- | --- | --- |
| M1 `lookup` names the name | **guarded** | inert |
| M2 the v0.33 cure clause | **guarded** | inert |
| M3 the clause fires only for an UNBOUND name | shadowed | **guarded** |
| M4 `and` short-circuits | **guarded**\* | inert |
| M5 `if` is strict | **guarded** | shadowed |
| M6 `if` names the branch | **guarded** | inert |
| M8 `is_num` excludes a Guess | **guarded** | shadowed |
| M9 `==` refuses callables | **guarded** | inert |
| M10 `==` delegates for a Guess | **guarded** | shadowed |
| M12 decision 2 | shadowed | inert |
| M13 `blame`'s origin test | inert | inert |

**Both directions guarded: 0 of 11.** \*M4's `-` is the contaminated pin —
§6.

Nine of the eleven have exactly one direction guarded. M13 has neither
(§5.3). M3 is the one reversal, and it reverses for a reason the predicate
column predicts: its guardian is

```
check "guest miss <BOUND name> stays plain propagation":
  contains(str(...), "unbound name 'NOSUCH'") and
  not contains(str(...), "a miss reason is a string")
```

a conjunction of a positive containment and a **negative** one. It is
one-sided in each of two opposite directions, and it is the only check in
this file written that way. It is also the only `+` mutant caught by a
guardian its author did not write specifically for that direction.

## 4. The other two `+` mutants that were caught

Both prove the same point from the other side.

**`EP11p`.** Round 326 found that `check_ret` unconditionally appended
`" of " + fn_name` and diverged from the host for anonymous closures. It
fixed it and wrote **two** checks — `"...has no 'of' suffix"` (anonymous)
and `"...still has the 'of' suffix"` (named). Making every closure read as
named is a `+` mutant, and the anonymous check catches it, because that
check exists precisely to catch it. This is the shape the whole finding
recommends, and it occurs once in 166 checks.

**`EP16p`.** `dv_same_payload` returning `false` for everything is caught —
by `"identical histories have no origins"`, a *different* label from the
one that catches the `-` direction. I chose that guardian for that
direction when writing the pin. That is the registry doing the author's
job, not the file doing it.

## 5. The five findings that are real coverage gaps

Each is a rule with no check that can see it broken in at least one
direction. Each got a killer, verified red under its pin and green under a
neighbour.

### 5.1 A message check that cannot see the message grow

```
check "guest unbound reason names the name":
  contains(str(gv("nope + 1")), "unbound name 'nope'")
```

`contains` says *at least this*. Every message assertion in this file is
`contains`, and `self_eval.lang` is a Whence evaluator **written in
Whence** whose whole contract is that its sentences are the host's
sentences. "At least this" is the wrong relation; equality is the right
one, and the host is right there to ask:

```
check "...and it is the host's sentence exactly, not a superset of it":
  drop_line_suffix(reasons(gv("nope + 1"))[0]) ==
    drop_line_suffix(reasons(nope + 1)[0])
```

`nope + 1` on the LEFT is run by the guest evaluator; on the RIGHT it is
run by the host, in the same file, as ordinary top-level Whence. The only
thing they legitimately disagree about is the `(line N)` suffix — the
guest's is a `self_eval.lang` line, this evaluator's one long-documented
provenance divergence — and `drop_line_suffix` is the file's own function
for removing exactly that.

> A check that asserts a constant can drift from the thing it mirrors. A
> check that asserts *the other implementation's answer* cannot.

Two such checks were written (the unbound-name sentence, the v0.33 cure
clause). Both kill their `+` mutant and both kill their `-` mutant, so the
pair of pins collapses onto one two-sided guardian.

### 5.2 `and` that always answers false, and `if` that always says then

`check "guest short-circuit and skips the right"` was
`gv("false and num(\"3O\") == 1") == false` — and the *value* cannot say
whether the right was skipped, because **the host's own `and`
short-circuits too**. `false and <miss>` is `false` either way. The label
names a control-flow fact; the only place a control-flow fact is
observable is the provenance label:

```
check "guest short-circuit and skips the right":
  gv("false and num(\"3O\") == 1") == false and
  (gp("false and (1 / 0)")).op == "and short-circuit" and
  gv("true and true") == true
```

Three claims, one label: the value, the skip, and the case a too-eager
short-circuit breaks. This is round 414's finding 2 in a new place — *the
label was true of the other implementation* — and the reason it recurs is
that a self-hosting file makes every rule available in two evaluators.

`if` got the same treatment: the ELSE arm now has a probe.

### 5.3 The `blame` family had no guardian at all, in either direction

```
check "guest blame names the origin op": contains(verdict, "num:")
check "guest blame reads the origin reason": contains(verdict, "cannot parse")
```

`verdict` comes from `blame_src`, a guest PROGRAM that defines its own
`origin` in three lines of ordinary guest code. Those two checks are about
that program. They say nothing about the evaluator's own `blame` builtin
(`guest_blame` / `keep_origins` / `guest_is_origin_miss`, v0.30, round
378), and `blame(` never appears inside any guest source string in this
file. Making every missed node an origin **and** making nothing an origin
each left all 166 checks green.

The killer is a differential against the host again, not a constant:

```
let host_t = fold(fn(a, r) { a + num(r) }, 0, ["1", "3O"])
check "guest blame answers the ORIGIN, not the whole miss chain":
  gv(GBLAME + "len(blame(t))") == len(blame(host_t)) and
  gv(GBLAME + "(blame(t))[0].op") == (blame(host_t))[0].op
check "...and an origin's detail is the host's own sentence, line-suffix stripped":
  gv(GBLAME + "(blame(t))[0].detail") == (blame(host_t))[0].detail
```

The second one also gives `drop_line_suffix` (`EP14m`) its first guardian.

### 5.4 Decision 2, which `missed(...)` can never express

```
check "guest return type is not re-checked over an already-missed body":
  missed(gv("fn f() -> num { 1 / 0 }\nf()"))
```

Decision 2 says a function that already failed does not ALSO get a "wrong
return type" gloss. It is entirely a claim about what the miss **says**,
and the check asks only whether it misses — which it does either way. The
strengthened check asserts the absent gloss. (This pin then turned out to
be `redundant` rather than unguarded; §6.)

## 6. `inert` was two facts, and `also` / `redundant` separate them

Two pins stayed `inert` with `n_red == 0` **after** their guardians were
strengthened, which is the interesting failure: a strengthened check that
still cannot see the edit is usually a sign the check is wrong. It was not.

* **`EP07m`.** `guest_kind` probes `is_guess_val` first, and the check is
  labelled *"reports 'guess' ahead of every other test"*. Demoting the
  probe below num/str/list/bool changes nothing, because
  `is_num`/`is_str`/`is_list`/`is_bool` each **open with**
  `not is_guess_val(v) and`. The ordering is belt; the four guards are
  braces; the code has both. The function's own comment says "must be
  checked FIRST (**or** these three guarded against it)" and never noticed
  it had done both.
* **`EP12m`.** `check_ret` opens `if ret_spec == "" or missed(box.v)`, and
  the function it tail-calls, `check_contract`, opens
  `if spec == "" or missed(box.v)`. Decision 2 is enforced twice.

Removing ONE copy of a rule that has two is invisible, and it reads exactly
like *nothing guards this*. The two call for opposite responses. `checkpin`
now says which:

```json
{ "id": "EP12m", "redundant_with": "EP12m2", ... }
{ "id": "EP12m2",
  "edit": "line_replace", "needle": "  if ret_spec == \"\" or missed(box.v) { box }",
  "becomes": "  if ret_spec == \"\" { box }",
  "also": [{"edit": "line_replace",
            "needle": "  if spec == \"\" or missed(box.v) { box }",
            "becomes": "  if spec == \"\" { box }"}] }
```

`also` is a chain of edits, each located in the source the previous one
produced (so a later edit may target text an earlier one wrote); the
equivalence check runs on the NET result, so a chain that cancels itself
out is refused like any other no-op edit. `redundant_with` names the wider
pin; `inert` here plus `guarded` there demotes the verdict to
**`redundant`**, which is scored out of the denominator alongside the
negative controls, for a reason worth stating plainly:

> Counting a correctly-redundant rule as a suite defect makes a file that
> defends a rule twice score worse for having done so.

Both wider pins are `guarded` (`EP07m2` n_red=5, `EP12m2` n_red=2), so both
`inert` verdicts are `redundant`, and **neither collected a new test**. The
`is_str` guess-guard sibling was added anyway — three of the four probes
had a check and the fourth did not — and `guest_kind`'s label was rewritten
to name what actually holds rather than an ordering that carries no weight.

## 7. The pin that was guarded for the wrong reason

`EP04m` removes `eval_and`'s short-circuit arm the obvious way
(`else if l.v.v == false {` → `else if false {`). Verdict: `guarded`. Note:
`value was miss: num: cannot parse "3O"`.

That note is the tell. The check expected `false` and got a **miss**, which
is not what "the right operand was evaluated" produces — the host's `and`
short-circuits, so the value should have stayed `false`. What actually
happened is that the `else` arm computes its payload as `true and r.v.v`,
because reaching it originally meant the left operand WAS true. Disabling
the `false` arm sends a false left operand down a path that assumes it is
true. The edit changed the value, not just the branch.

`EP04m2` is the isolated form, written afterwards:

```
  else if l.v.v == false {
    let r = eval(node.right, env, l.st)
    @{v: mkb(false and r.v.v, "and", [l.v, r.v]), st: r.st}
  }
  else if false {
```

Against the ORIGINAL check it would have been `inert` (the value is
`false`, correctly, and only the op label differs); against the
strengthened one it is `guarded`. Both pins are kept, and `EP04m`'s `why`
now records that its verdict does not mean what it appears to.

> A `guarded` verdict says the guardian went red. It does not say the edit
> broke the rule the pin names. Read the note.

## 8. Three ways this round could have manufactured its own result

**(a) Predicate shape assigned after the fact.** `predicate` is in the
registry, written before the run, and `state/round-416-predictions.md`
names which pins are expected to be findings and why, banked before
`eval-pins.json` existed. B3 (every one-sided `+` pin is a finding) and B9
and B10 were called by name.

**(b) A `+` mutant that is really a syntax error.** Prediction A5, kept as
a test: `test_every_mutated_source_still_parses` parses all 34 mutated
sources. A `collapsed` verdict caused by MY replacement text is the tool
measuring itself; a `collapsed` caused by mutated semantics is a result.
Zero of either occurred.

**(c) The controls.** Two, not one: `first_space`'s `i >= len(s)` →
`len(s) <= i` (string half) and `extend`'s `i >= len(ys)` → `len(ys) <= i`
(provenance half). Two subsystems, so a control that held only because
nothing in the run touched its function is ruled out. Both `inert`,
`n_red == 0`, on both runs.

A fourth, specific to the statistic: the p-value is computed over 29 pins
**I chose**, and a registry author who wanted a low p-value could get one
by writing weak `+` mutants. §2's list is the defence I can offer — every
`+` edit is named and is a plausible refactor — and it is an argument, not
a measurement. The falsifiable form is that this should replicate on
`self_host.lang`'s 22 pins, which is a next step and not a claim.

## 9. Also this round

**The orphan is discharged by deletion.** Round 415's next-step 1 gave
language(C) `languages/whence/nuc_scripting/ncs_engine.py`, `unwired since
round 415`, with three exits: wire it, test it, or delete it. Deleted. It
is a second, weaker implementation of the task-script DSL that
`nuc/taskscript/` already ships (mission E5, done round 124, plus
`skills/preflight-priced-task-scripts/`); it runs its input through
`subprocess.run(..., shell=True)` with no budget discipline; round 172
recommended `delete-as-dead-end` **244 rounds ago**; and it had zero
references of any kind. `harness/wiring-registry.json`'s entry is removed
and `test_the_deleted_orphan_is_gone_rather_than_merely_undeclared` keeps
the discharge real — dropping the registry entry alone would turn an
audited debt into an unaudited one.

**Two tests round 415 shipped red are green.** Found while discharging the
above, present on the pristine tree, not caused by this round:

* `harness/wiring_audit.py` had **no entry in its own registry**, so
  `wiring_audit.py check` reported `W001` on itself and
  `test_the_cli_check_exits_zero_on_this_tree` failed. The registry is
  fail-closed by design ("a script built next round classifies itself
  instead of waiting to be noticed") and the script that implements that
  rule was the one it caught. Registered `wired via
  harness/tests/test_wiring_audit.py`.
* `test_the_declared_debts_...` asserted `d not in Graph(REPO).closure()`
  for every `unwired` entry. That is **not the predicate `W003` uses**:
  `check` has a deliberate `weak_only` exemption — a file reached only as
  text inside a test defers to `W006` rather than contradicting it — and
  `harness/swe/loop.py` is exactly that case. The test now asserts the
  checker's real rule, so the two agree instead of contradicting each
  other. A checker and its test disagreeing about the checker's own rule is
  a rot class worth a name.

**Three count pins moved, and the comment naming them was wrong.**
`self_eval.lang` 166 → 172. Round 398's comment in `test_self_eval.py`
listed the three copies as `test_v23.py`, `test_examples.py`, here.
`test_examples.py` holds `self_host.lang`'s count; the third copy is
`test_v31.py::test_the_example_still_passes_its_own_self_tests`, which is
what went red after the other two were updated. Round 414 hit the identical
shape one file over ("three count pins moved, not two"). All three comments
now name all three sites.


**Also: the Track C version number was two levels stale for six rounds.**
`state/research-state.md`'s `- **Language (C):**` line said `v0.39 (round
408)` through rounds 410 (which made the bump to v0.40), 411, 412, 413, 414
and 415, while `SPEC.md`'s own header said v0.40 correctly the whole time —
because `tests/test_v22.py::test_spec_level_header_matches_the_highest_version_section`
pins THAT header and nothing pinned this one. Round 348 wrote the paragraph
about exactly this failure mode, for `SPEC.md`, and it rotted in the other
file. Corrected, and given the missing test
(`test_research_state_track_c_names_the_same_version_as_spec_md`). A
version number belongs in one place; it is in two, so the second one now
gets a test instead of a promise.

**A skill costs four things, not one, and this round paid all four only
because a checker asked.** `skills/run_checks_fast.sh`'s own header records
three previous episodes of "a non-skills(B) round adds a skill with no
trigger cases (P001)", closed by rounds 351, 357 and 363 after gaps of 9, 3
and 2 rounds. This round would have been the fourth. Adding
`mutate-the-rule-both-ways` turned the corpus red in FOUR places at once,
each a different obligation:

* `case_coverage` **P001** — 0 positive trigger cases, floor 3. Fixed: five
  cases (four positive, one negative — a flaky-test prompt that must NOT
  fire it).
* `claim_check` — the SKILL.md parsed to **zero commands** and so joined the
  prose-only set. Fixed by giving the Verification section the two commands
  that reproduce this round, which is what it should have had.
* `carryforward` **K001** — a banked prediction file with no entry in
  `state/prediction-bank-ledger.json`. Fixed, with a `remainder` recording
  that B4's PARTIAL is really "the bank had no prediction for this case".
* `xref_check` **X004** — deleting `ncs_engine.py` dangled the two prose
  citations of it, one in round 415's next-step block and one in this
  round's own entry recording the discharge. Acknowledged rather than
  reworded: both sites are prose ABOUT a removal, and rewording either
  deletes the record of what was removed. This is the first PERMANENT entry
  in `state/known-dangling-citations.json` — every other one names a
  registry that could be populated; a deleted path never comes back.

The corpus is `0 error(s), 6 warning(s)` after all four.

## 10. Verification

```
$ python3 checkpin.py locate ../../state/whence/round-416/eval-pins.json
34 spans, 0 unlocatable                                      # A1

$ python3 -c "...parse every mutated source..."
34 pins, 0 parse failures                                    # A5

$ CHECKPIN_JSON=.../run-before.json python3 checkpin.py run .../eval-pins.json
29 pins: 14 guarded, 15 finding(s), 0 error(s), 0 redundant, score 48%
CONTROL NC01: inert (n_red=0) -> HELD
CONTROL NC02: inert (n_red=0) -> HELD              WALL 104.1s

$ CHECKPIN_JSON=.../run.json python3 checkpin.py run .../eval-pins.json
30 pins: 25 guarded, 5 finding(s), 0 error(s), 2 redundant, score 83%
REDUNDANT EP07m: inert, but the wider edit EP07m2 went red
REDUNDANT EP12m: inert, but the wider edit EP12m2 went red
CONTROL NC01/NC02 -> HELD                          WALL 113.9s

$ python3 run.py examples/self_eval.lang
checks: 172 passed, 0 failed                                 # was 166

$ python3 -m pytest tests/test_checkpin.py -q
37 passed in 68.21s                                          # was 22

$ python3 harness/wiring_audit.py check
wiring-audit: 108 entry point(s), 88 in closure, 0 error(s), 0 warning(s)

$ python3 -m pytest harness/tests/test_wiring_audit.py -q
48 passed in 56.34s                          # 4 were failing on the pristine tree

$ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict \
      skills/mutate-the-rule-both-ways/
skill-lint: 1 skill(s), 0 error(s), 0 warning(s)
```

Full suites: see §12.

## 11. What this round did NOT do

* **It did not re-run the direction experiment on `self_host.lang`.** The
  parser registry's 22 pins are 21 `-` and 1 `+`. Re-pointing them both
  ways is the replication that would turn §3's p-value from one campaign
  into two, and it is the single highest-value next step for this track.
* **It did not touch the five surviving `shadowed` findings.** EP03m,
  EP05p, EP08p, EP10p, EP12p all reddened between 2 and 14 OTHER checks, so
  the file is not blind to them — the label that names the rule is. Whether
  that is a defect depends on the label, and each is argued in the pin's
  `why` rather than papered over with a new check.
* **It did not answer whether `check` should carry a `because
  "<substring>"` clause** (round 414's item 2). §5.1's finding is now an
  argument *against*: what these checks needed was not a reason field, it
  was **equality with the other implementation**, which the language could
  already express.
* **It did not unify `parser.quote_str` with `values._quote`** (round 408's
  item 6). Untouched, fourth round carried.
* **It did not sweep the ~110 checks no pin in this registry reaches.**
  52 of 166 were red under at least one pin before the killers (61 of 172
  after), so 114 were red under none. That is **not** a coverage number —
  it is a statement about a 30-pin registry, `co_red` is capped at 12 per
  pin, and 114 is therefore an upper bound on an upper bound. Recorded
  because prediction B8 banked the band before the number existed.

## 12. Full suites

```
$ bash languages/whence/run_tests_fast.sh
2013 passed, 3 skipped, 85 deselected in 107.81s   # exit 0; FAILED|ERROR count: 0

$ bash harness/run_tests_fast.sh
1065 passed, 280 deselected in 285.52s              # FAILED|ERROR count: 0

$ bash skills/run_checks_fast.sh
corpus-check: 7 checker(s), 0 error(s), 6 warning(s)
unit_tests         ok    759 passed in 54.57s

$ python3 -m pytest nuc/tests -q
669 passed in 113.75s
```

## 13. Predictions, scored

Banked in `state/round-416-predictions.md` before `eval-pins.json` existed
and before any pin ran (D-013), with the outcome/mechanism split round 407
asked for.

| # | class | verdict | what happened |
| --- | --- | --- | --- |
| A1 | mechanism | **HIT** | 0 unlocatable; `fn_span` handled a 4342-line file with ~230 guest `fn`s |
| A2 | mechanism | **MISS** | predicted ≥1 `collapsed`/`unreached`. **Zero.** Second round running — round 414 predicted and missed it too |
| A3 | outcome | **HIT** | predicted 70–130 s for ~28 runs; 104 s for 31 (→ 94 s at 28) |
| A4 | outcome | **MISS** | predicted median `n_red` ≥ 3 and one pin ≥ 40. Actual median **2**, max **13** |
| A5 | mechanism | **HIT** | 0 parse failures in my replacement text, now a test |
| B1 | outcome | **MISS** | predicted 62–80%. Actual **48%**, well below the band |
| B2 | outcome | **MISS** | predicted 5–10 findings. Actual **15** |
| B3 | outcome | **HIT** | every one-sided `+` pin named in advance came back a finding |
| B4 | outcome | **PARTIAL** | the `-` sibling of each was `guarded` — except M13's, which is `inert` in BOTH directions |
| B5 | outcome | **HIT** | both controls HELD, both runs |
| B6 | outcome | **HIT** | the round-326 pair is the one mechanism guarded in both directions by author-written checks |
| B7 | outcome | **HIT** | 9 of 15 findings (60%) have a `contains`/`missed` guardian — the floor exactly |
| B8 | outcome | **HIT** | predicted 70–120 red under no pin. Actual **114** |
| B9 | outcome | **HIT** | `guest_is_origin_miss` weakened is a finding, for the stated reason |
| B10 | outcome | **HIT** | `drop_line_suffix` as identity is a finding |

**10 HIT / 1 PARTIAL / 4 MISS of 15. By class: mechanism 3/5, outcome
7 HIT / 1 PARTIAL / 3 MISS of 10.**

Round 414 measured the pattern *"everything derivable by reading code HIT,
every guessed empirical magnitude MISSED"* and §C of this round's bank
predicted the same split for itself. **It held, and it is now three rounds
running.** Every HIT above is arithmetic or a source read: A1 (the lexer
carries `col`), A3 (baseline × N), A5 (I parsed them), B3/B9/B10 (read the
predicate, read the check), B6 (read round 326's commit), B7 (count the
shapes), B8 (a band around round 414's own number). Every MISS is a guessed
rate: A2 (how often my registry will stumble), A4 (how fat `n_red` runs),
B1 (the score), B2 (the finding count).

**A2 is worth more than a tally mark.** I predicted a collapse for a
structural reason — *the guardians here are guest programs run BY the
mutated evaluator, so an evaluator mutation can take the harness down with
the rule* — and that reasoning is sound. It did not happen because
`locate`+parse converts run-time failures into author-time ones, which is
round 414's own §11 lesson, inherited and then re-missed. **A prediction
about how often the instrument will stumble is a prediction about whether
you will run the cheap check first, and I keep forgetting that I will.**

**B1 and B2 are the same miss twice, and the direction is the finding.** I
anchored on round 414's 91% and centred at 70%, reasoning that evaluator
checks are more behavioural than parser checks. The real number is 48%, and
the reason is not "behavioural" — it is that half the registry pushed a
direction nobody had ever pushed. Had I mutated only `-`, the score would
have been 11/15 = **73%**, inside my band and one point off my centre. The
band was right about the campaign I expected to run and wrong about the one
I ran. That is the most useful thing in this scoring table: **the
prediction was calibrated to the methodology, and the methodology was the
variable.**

**B4's PARTIAL is M13**, the `blame` family — the only mechanism invisible
in BOTH directions, and the only one whose named guardian turned out to be
about a different implementation entirely (§5.3). A both-ways-invisible
rule is a stronger finding than either half, and I had no prediction for
the category.

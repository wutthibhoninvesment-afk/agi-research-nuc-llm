---
name: second-door-skips-the-gate
description: Use when a checker, linter, validator or alerting rule decides two things about each input — first "is this something to judge at all?" (a suppression/exemption/allowlist gate) and then "does it hold?" (the verdict) — and a special-cased branch was added for one syntactic form. Symptoms: the same token is exempt as an argument and reported as a violation as a prefix; a finding whose exemption reason is already computed and sitting unread on the object; a fast path with its own regex that never calls the shared candidate producer; a false positive that surfaces only when someone writes the provoking input, years later. The move is to name the gate as a function, make every door call it, keep the branch's side effects when it is exempt, and pin that with a comment-stripped structural test. NOT for one guard with several causes (skip-reason-is-a-claim), two copies drifting apart (copied-mirror-drift), or a rule never implemented (unenforced-documented-rule).
---

# The second door skips the gate

A checker almost always decides two things, in order:

1. **the gate** — is this input a claim I am entitled to judge? (a
   placeholder, a scratch path, a template, a test fixture, a vendored
   file, a `# noqa`, a maintenance window)
2. **the verdict** — given that it is, does it hold?

The gate is the part nobody thinks of as logic. It gets written once,
inside whatever function happened to need it first — usually a *producer*
that yields candidates — and it is invisible from anywhere that does not
call that producer.

Then someone adds a branch for a syntactic form the producer cannot express.
It needs its own regex to find its operand. It reimplements the **verdict**,
because that is the part that looks like the job, and it does not
reimplement the **gate**, because the gate does not look like anything.

The instance this was written from, exact:

```python
def check_paths(commands, repo_root):
    for cmd in commands:
        m = re.match(r"^\s*cd\s+(\S+)", cmd.command)   # <-- the second door
        if m:
            target = m.group(1).strip("'\"")
            resolved = resolve_token(target, [cwd, repo_root])
            if resolved is None:
                findings.append(Finding(cmd, "C001", "`cd %s` — no such "
                                        "directory" % target))
                continue                                # <-- and see §2
            ...
        for tok in path_tokens(cmd.command):            # <-- the first door
            ...                                         #     gate lives in here
```

`path_tokens` drops placeholders (`<lang>`), scratch paths (`/tmp/...`),
URLs and flags. The `cd` branch drops nothing. So in one file, in one
Verification block, on two adjacent lines:

```bash
git worktree add --detach /tmp/<scratch-worktree> HEAD   # silent, correctly
cd /tmp/<scratch-worktree> && pytest tests/ -q -rs       # STALE: no such directory
```

Same token. Opposite verdicts. **71 rounds** between the commit that
introduced it and the first input that provoked it, because until then
nobody had written a placeholder or a `/tmp` path after a `cd`.

## Three things that make this worth its own procedure

**1. The exemption was usually already computed.** In the case above the
tool has a `classify()` that runs at collection time and hangs its answer
on every command object. Asked about that exact line it returns
`("manual", "placeholder: not runnable as written")`. It is *correct*, it
is *there*, and the branch reads `cmd.command` without ever reading
`cmd.reason`. Before you write a gate call, check whether the answer is
already on the object.

**2. A false positive here also causes a false negative.** The branch
`continue`s after it fires, so everything after the `&&` was never checked.
A genuinely missing file in `cd /tmp/<wt> && pytest tests/test_real.py` was
invisible for as long as the prefix was wrongly flagged. This is the part
that turns "cosmetic noise" into a detector outage, and it is the argument
that gets the fix prioritised.

**3. Correct architecture is available and nearby.** A sibling tool in the
same directory puts its placeholder check *inside the token generator* and
yields `(tok, pos, is_evidence)` — so no consumer can opt out, because
there is nothing to opt out of. Look for that shape before inventing one.

## When to use (triggers)

- A `if <special form>: ... continue` branch sitting above the loop that
  does the general case, with its own regex for finding its operand.
- Two entry points that emit the same finding code, where one calls the
  shared candidate producer and one does not.
- A reviewer says "this warning is wrong for X" and the proposed fix is to
  add a check for X *at the reporting site*.
- The same input is exempt in one position and reported in another.
- A suppression list, `# noqa`, allowlist, maintenance window or
  `known-*.json` exists, and you are adding a code path that reports before
  consulting it.
- A validator whose finding objects carry a `reason` / `category` /
  `severity` field that some branches read and some do not.

**When NOT to use:** one guard whose single condition covers several
different causes (`skip-reason-is-a-claim`); a second implementation created
by copying a first (`copied-mirror-drift`); a documented rule with no
implementation anywhere (`unenforced-documented-rule`); an exemption you
have simply never counted (`measured-exemption`).

## Steps

1. **Enumerate the doors, by finding-code, not by reading.** Grep the
   emission site, not the function names:

   ```bash
   grep -rn '"C001"' --include=*.py .     # every place that can emit it
   ```

   Anything more than one is a candidate. Two doors is normal and fine;
   two doors and one gate is the defect.

2. **Locate the gate and ask where it lives.** If it is a sequence of bare
   `continue`s inside a producer, it is a property of that *producer*, not
   of the tool — which is precisely why the second door does not have it.
   If it is already a named predicate, this is a five-minute fix.

3. **Check whether the verdict is already on the object.** Whatever
   classified the input earlier probably recorded why it is exempt.
   Reusing that is better than re-deriving it, and it makes the two
   answers incapable of drifting.

4. **Extract the gate into a named function returning a REASON, not a
   bool.** A reason survives into the summary line and makes the
   suppression auditable; a bool disappears.

   ```python
   def token_exempt_reason(tok):
       """Why `tok` must NOT be judged, or None if it is a real claim."""
       if not tok or URLISH_RE.search(tok):    return "not a path: url/flag"
       if PLACEHOLDER_RE.search(tok):          return "placeholder: a template"
       if tok.startswith(SCRATCH_PREFIXES):    return "scratch: made by the command"
       return None
   ```

   Put in it only what is a property of the TOKEN. Rules that need the
   caller's context (bases, cwd, the command's own category) stay out, and
   say so in the docstring — otherwise the next person moves them in and
   the function stops being callable from the second door.

5. **Make exempt mean "no finding", NOT "skip the branch".** This is the
   step that gets botched. The special-cased branch usually exists because
   its form has a *side effect* on the checker's state — `cd` moves the
   working directory for every later command in the block. An early
   `continue` on exempt silently stops tracking it and un-anchors
   everything downstream. Suppress the `append`, keep the assignment:

   ```python
   exempt   = token_exempt_reason(target)
   resolved = resolve_token(target, bases)
   if exempt is not None:      n_skipped += 1          # counted, not judged
   elif resolved is None:      findings.append(...); continue
   else:                       n_checked += 1
   if resolved is not None and os.path.isdir(resolved):
       cwd = resolved                                  # the side effect SURVIVES
   ```

6. **Re-check what the old false positive was hiding.** Remove the
   `continue` and the tokens behind it become visible for the first time.
   Expect the skipped/checked counts to move by more than one per fixed
   site, and account for the difference before you believe the fix.

7. **Quarantine the old branch as a test fixture.** Copy it verbatim,
   parameterised on its inputs, returning a verdict instead of appending.
   Then assert the differential on the exact live input that provoked it,
   and — separately — on the masking case from step 6.

8. **Pin the invariant, with comments stripped.** Two pins, because either
   alone is satisfiable the wrong way:

   ```python
   def test_the_gate_regexes_are_read_in_exactly_one_function(self): ...
   def test_every_finding_site_CALLS_the_gate(self):
       code = "\n".join(l for l in body.split("\n")
                        if not l.lstrip().startswith("#"))   # <-- required
       self.assertIn("token_exempt_reason(", code)
   ```

   The comment strip is not fussiness. The branch you just fixed carries a
   six-line comment naming the gate; without the strip the pin passes on a
   file where the call has been deleted and only the explanation remains.

## Pitfalls

- **Fixing the reporting site instead of the gate.** Adding
  `if "<" in target: continue` to the second door makes the symptom go away
  and leaves a third door free to repeat it. The deliverable is that the
  decision has one home.
- **`continue` on exempt.** Step 5. It converts a false-positive bug into a
  silent state-tracking bug, which is strictly worse and much harder to see.
- **A structural pin that a comment satisfies.** Step 8.
- **A pin that only forbids.** `assert no second copy exists` passes when
  the *subject* is deleted. Pair every absence pin with a presence pin —
  including one asserting the quarantined old branch is still there, or the
  differential tests are asserting against nothing.
- **Assuming the second door is younger.** It is intuitive that the special
  case was bolted on later. In the case above both landed in the *same
  commit*: the author wrote the gate for arguments, wrote the branch for
  prefixes, and never asked whether they agreed. Do not use `git log` to
  decide which one to trust.
- **Reading rarity as safety.** The bug produced zero findings for 71
  rounds. Latency here is bounded by *when someone writes the provoking
  input*, not by how long the code has been exercised, so "it has been fine
  for years" is not evidence of anything.
- **Counting the fix by the finding that disappeared.** One false positive
  removed, but two tokens newly examined and one real defect newly
  detectable. Report both directions.

## Verification

```bash
# 1. how many doors emit the code, and do they all call the gate
grep -rn '"C001"' --include=*.py .
grep -n "token_exempt_reason" claim_check.py
#    expect: every emitting function appears in the second list

# 2. the gate's inputs are read nowhere else
grep -n "TOKEN_PLACEHOLDER_RE\|SCRATCH_PREFIXES" claim_check.py
#    expect: the definition lines, plus exactly one reader each

# 3. the differential runs, and it calls BOTH branches
python3 -m pytest -q test_claim_check.py -k "cd_target or one_home"
#    expect: passed, and each test body names the quarantined old branch

# 4. falsify both structural pins — a pin that has never failed is a claim
sed -i 's/exempt = token_exempt_reason(target)/exempt = None/' claim_check.py
python3 -m pytest -q test_claim_check.py -k c001_site   # expect: FAILED
git checkout claim_check.py

# 5. the real rule was not weakened: an ordinary bad path is still reported
python3 -m pytest -q test_claim_check.py -k "still_c001 or missing_cd"

# 6. the whole-corpus counts moved in BOTH directions, and you can say why
python3 claim_check.py skills --repo-root . | tail -1
#    expect: stale count down; unresolvable-by-design up by MORE than the
#    number of false positives removed (step 6 of the procedure)
```

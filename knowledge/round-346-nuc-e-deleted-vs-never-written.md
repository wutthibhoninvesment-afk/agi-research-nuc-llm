# Round 346 — NUC-integration(E) — the hard rules were in git the whole time

**Track:** E (NUC integration). **Box verdict:** `down`, 9th consecutive
E-round. **Headline:** the file that governs every round of this program has
had an empty `## Ground rules` section for ~200 rounds. Round 345 found the
symptom, concluded the text "predates this repo's git history", and filed the
fix as the operator's. It was at the initial commit. This round restored it,
and built the check that makes the mistake unrepeatable.

---

## 0. The live E work, first

`reachability_check.py check --round 346`:

```
verdict            down
ssh_returncode     255   (connect to 100.78.44.111 port 22: timed out)
tailscale_online   false
last_seen_utc      2026-08-29T02:10:00.1Z
boot_utc           null
```

`bounds --verdict down` on the current streak (rounds 298→346, 13 checks):
**confirmed span 19h38m06s, ongoing**, start bracketed to **±3m06s** by
`tailscale_last_seen` — the tight bracket round 334's work exists to produce.
The `ambiguous` verdict remains unobserved (round 310's item 3, 8th round).
`swap_watch_launch.py plan/launch` is blocked for the **ninth** consecutive
E-round; `boot_probe`'s live path stays unverified for the same reason.

That is the whole of what a down box permits. The rest of this round is the
governance defect a down-round has the budget to chase.

## 1. The finding

`CLAUDE.md` is 13 lines. It ends:

```
## Ground rules
```

— a heading with nothing under it. `CURRICULUM.md` line 45 points at that
section for the program's hard rules. Round 345's `xref_check.py` found
`D-013` cited 42 times and defined nowhere, and wrote:

> `CLAUDE.md` has a `## Ground rules` heading and **nothing under it** — in
> all three commits that have ever touched the file. The body predates this
> repo's git history; it was lost in the Mac→NUC migration.

Three commits have touched the file. Their sizes:

| commit | lines | `## Ground rules` |
|---|---|---|
| `ee30654` initial clean commit | **42** | **7 numbered rules** |
| `e376750` AUTO-COMMIT v4 | 6 | empty |
| `db684e1` round 333 model policy | 13 | empty |

The body is *in this repo's git history*, at the first commit. `e376750`
deleted 36 lines of it. What was destroyed:

- the seven numbered ground rules (read state first; real artifacts; the
  knowledge-file naming convention; the research-state update; when to write
  a skill; **the track rotation table**; the rate-limit exit rule);
- the entire **`## Track E — NUC integration: HARD RULES`** section — the
  read-only path list, the **never-touch-port-8001** prohibition, the allowed
  write paths, the unit-restart rule, the endpoint list, the two-SSH-failures
  rule, and the definition of **D-013**;
- the `## What "done" means for a round` section.

Every one of those rules has been honoured for 200+ rounds anyway, carried by
`CURRICULUM.md`, `state/nuc-missions.md` and round-to-round inheritance. The
governance file that all of them cite has been empty the entire time.

Sanity check on the recovered rotation table: round 346 mod 6 = 4 →
NUC-integration(E), which is this round's assigned track. The recovered text
is consistent with the program as actually run.

## 2. Why round 345 got it wrong, and why that is the interesting part

Round 345's reasoning was sound given its evidence, and its stopping rule was
right:

> Transcribing a definition that already exists is repair; writing the
> missing one is authorship.

It applied that rule correctly. It just answered the antecedent — *does the
definition already exist?* — by looking at the working tree. In the working
tree the section is empty, and **an absent thing offers no hint that it was
ever present**. Nobody ran `git log CLAUDE.md`, because the file was *there*.
Only its contents were missing, and that is the case that does not look like
a deletion: every "does it exist" check says yes.

The cost of the misclassification was not the empty section. It was that
"authorship, operator's call" is a *terminal* classification. It routes the
item to someone outside the loop and parks it. Repair is something any round
can do in ten minutes. **One `git log` separated a ten-minute job from a
permanently parked one**, and nothing in the pipeline ran it.

## 3. `xref_check.py --provenance`

The generalisation: a checker that reports `registry empty` has told you
there is a problem and withheld the thing that decides who fixes it. So for
every id the sweep reports dangling, ask the registry document's own history
whether that id was **ever** defined.

Registry verdicts: `ok`, `ids-deleted`, `body-deleted`, `never-populated`,
`no-vcs`. Per-id verdicts: `resurrectable`, `elsewhere-in-doc`,
`never-defined`. Live output before the repair:

```
X001 SPEC design decision   registry ok            languages/whence/SPEC.md (46 revisions)
    27  never-defined in 46 revision(s). Writing it is authorship.
    28  never-defined in 46 revision(s). Writing it is authorship.
    29  never-defined in 46 revision(s). Writing it is authorship.
X002 house rule             registry body-deleted  CLAUDE.md (3 revisions; last had a body
                                                   2026-08-25 @ ee30654, but never ids of this family)
    D-013  RESURRECTABLE -- but under 'Track E — NUC integration: HARD RULES', not the
           declared 'Ground rules', at ee30654. The text is recoverable AND the registry
           declaration is mis-pointed: two fixes.
X003 lint rule code         registry not-a-document
```

**Two dangling families in one corpus, identical symptom, opposite verdict.**
X002 was recoverable in minutes. X001's decisions 27/28/29 — cited 69 times —
were never defined in **any of 46 revisions** of SPEC.md, so that one really
is authorship and really does belong to language(C). Round 345 had grouped
both under "debt this round does not own". Half of that was true.

### Three bugs the ground truth caught

I had an independently-known correct answer (`ee30654` contains `D-013`), so
every wrong output was diagnostic. All three were the same shape — *asking
the right question of the wrong source*:

1. **First live run said `never-populated` / `never-defined`.** `ids_in()`
   measures "does this section define ids", and I used it for "was this
   section ever populated". `## Ground rules` at `ee30654` holds seven
   numbered rules and zero `D-NNN` tokens, so an ids-only reading calls it
   never-populated — *of a section whose body a commit deleted*. Split into
   `ids_in()` and `has_body()`.

2. **The registry declaration was mis-pointed.** `D-013` was defined under
   `## Track E — HARD RULES`, not the declared `## Ground rules`. A search
   correctly scoped to the declared registry — which is round 345's own
   discipline, and right — cannot find it. Added
   `locate_in_document()`, which searches the whole document and reports the
   *owning heading*, yielding the `elsewhere-in-doc` verdict: the text is
   recoverable **and** the pointer is wrong, two fixes.

3. **The probe read HEAD for "is it populated now".** After restoring
   `CLAUDE.md` on disk, provenance still reported `body-deleted` — because
   the repair was uncommitted. "Populated now?" is a question about the
   **working tree**; "ever populated?" is a question about **history**. HEAD
   is neither. This is the state the tool is in *every time anyone actually
   uses it*, and a live test is the only thing that finds it.

Bug 3 is worth dwelling on. It was caught by a test asserting the *live
corpus* is healthy after the fix, not by any unit test — and it could not
have been caught by an injected git runner, because a fake runner has no
opinion about the working tree. This is round 334's `boot_probe` lesson
arriving from the other direction: that probe is fully unit-tested against an
injected runner and its live path has been unverified since round 334 —
three E-rounds — because the box never came back up. Here the live path *was* available, ran
immediately, and was wrong three times. **A fake runner tests the parser;
only the real thing tests the command.** So these tests build real git repos
in `tempfile` and shell out to real `git`, keeping injected runners only for
the failure paths a real repo cannot easily produce (no git binary).

### A latent bug found on the way

`_section_body()` finds headings with `^#{1,6}\s+`, which matches `#` comment
lines **inside fenced code blocks**. A repo-wide scan for empty sections
reported 40+, almost all of them `# expected: ...` lines inside a
Verification block's fence. None of the three live registry sections contains
a fence, so this was latent, not live — but it is exactly this round's
failure mode one level down: a fenced example inside a registry section would
end the section early and the registry would read **short**, with no symptom
except citations dangling for no visible reason. `_section_body` is now
fence-aware (backtick and tilde, indented markers, unterminated fence runs to
EOF). The empty-section scan went 40+ → **2**, and both survivors are benign:
`CURRICULUM.md` and `SPEC.md` each hard-wrap one heading across two lines, so
the first line is a heading with an empty body.

## 4. The restoration, and what was deliberately changed

Restored `## Ground rules`, `## Track E — NUC integration: HARD RULES` and
`## What "done" means for a round` from `ee30654`.

`## Ground rules` is **byte-identical** to `ee30654` — verified by diff, and
the skill requires that check because a diff is the only thing separating a
restoration from a rewrite wearing its clothes.

Track E's section is verbatim in every **rule** — the read-only list, the
port-8001 prohibition, the allowed write paths, the restart rule, the
endpoints, D-013's semantics, the two-SSH-failures rule. Four **coordinates**
changed, each because the tree already records the correction:

| change | evidence |
|---|---|
| connect line leads with tailnet `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`; LAN address `192.168.1.42` → `192.168.1.37` | `state/nuc-missions.md` round 154; CURRICULUM.md; 1234 in-tree references to `.37` vs 4 to `.42`; and `~/.ssh/id_ed25519_nuc` **does not exist on this host** — the only key present is `id_ed25519` |
| restart bullet notes `qwen36-colibri` is a **user** unit | `nuc-missions.md`, round 100 |
| endpoint bullet notes both ports are loopback-only | `nuc-missions.md` round 154 |
| results path drops "(Mac)" | the driver runs on the NUC host now |

No rule was added, removed or reworded. The reconciliation is written into
the file as a provenance note naming `ee30654` and `e376750` and listing all
four changes, so the next reader does not repeat this investigation and the
next bulk commit has something to delete *visibly*.

**This is the round's one judgement call, and it deserves to be stated
plainly.** Round 345 deferred to the operator. That was the right call under
"this text no longer exists anywhere". Under "this text is at `ee30654` and
diffs clean", the same rule round 345 wrote — transcription is repair —
authorises any round to do it. What is emphatically *not* authorised, and was
not done, is inventing a rule or updating one because it looks stale.
**Operator: the four coordinate changes above are the only places round 346
exercised judgement, and each is reversible with one `git show`.**

## 5. Effect

`X002`: registry `empty` → `ok`; **50 citations, 0 dangling.** The family is
closed. Authoritative dangling citations across the corpus: **33 → 18**, all
pre-acknowledged, all now correctly attributed:

- `X001:27/28/29` — language(C), genuinely never written, 69 citations.
- (`X002:D-013` removed from `state/known-dangling-citations.json`; round
  345's guard test — no baseline entry may outlive its finding — went red
  the moment the fix landed, which is exactly what it was built for.)

Round 345's baseline entry for `X002:D-013` gave as its reason "the body
predates this repo's git history". **A baseline entry is a claim, and this
one was false for the whole of its short life.** The removal comment now says
so and points at `--provenance`.

## 6. Verification

```
python3 -m pytest skills/skill-authoring/scripts/   364 passed   (was 316; +48)
python3 -m pytest nuc/tests/                        348 passed
./harness/run_tests_fast.sh                         464 passed, 267 deselected
python3 -m pytest languages/whence/tests/          1069 passed   (untouched this round)
xref_check.py                    0 NEW, 18 pre-acknowledged, exit 0
xref_check.py --provenance       exit 0; 3 authorship, 0 outstanding resurrectable
skill_lint.py --house --strict   22 skill(s), 0 errors, 0 warnings
claim_check.py skills/           0 stale claims
```

**Mutation kill: 22 hand-designed mutants, one per design decision.
18/22 (82%) first pass; 22/22 (100%) after strengthening four tests.**
Target restored byte-identical (sha256-checked). Every survivor was a weak
test, and each is worth recording:

- **`test_a_revision_predating_the_file_is_skipped_not_counted_empty` was
  vacuous.** Its fixture added an unrelated earlier commit — but
  `git log -- <path>` already filters those out, so there was never a failing
  `git show` to survive. The real fixture is a **deletion** commit: `git log`
  lists it, `git show <sha>:<path>` fails. Two mutants survived on that one
  bad fixture.
- **The indented-fence test indented the inner line too**, so the line was
  not heading-shaped either way and the test passed regardless.
- **`body-deleted` had no negative test** — nothing pinned that a section
  with a live body that never held ids is `never-populated`, not
  `body-deleted`.

Round 345 got 28/28 first pass and attributed it to writing tests *after*
fighting false positives empirically. That mechanism holds up here in the
negative: my four survivors are all in code paths that had no empirical
fight behind them — I reasoned about git's behaviour instead of provoking it.
The vacuous-fixture case is the sharpest: **a test can assert the right thing
about a scenario it never actually constructs**, and only mutation finds it.

## 7. Predictions (banked in `state/round-346-predictions.md` before measuring)

**7 HIT, 1 MISS.**

| | claim | outcome |
|---|---|---|
| P1 | box `down` (0.85) | **HIT** — 9th consecutive. (The banked text said "8th"; that was an off-by-one against `research-state.md`, which records round 340 as the eighth. It does not affect the verdict, which was up-vs-down.) |
| P2 | `ambiguous` still unobserved (0.93) | **HIT** |
| P3 | SPEC decisions 14–26 recoverable from git (0.35) | **MISS** — all 46 revisions max out at 13; never minted. Correctly low confidence: I reasoned "a truncating migration is proven in this tree", and it was — just not in that file. |
| P4 | 1–4 other empty-but-once-populated sections (0.6) | **HIT at the low bound** — exactly 1 (CLAUDE.md itself). `e376750` was a single destructive event, not a process. Only measurable *after* the fence fix. |
| P5 | provenance changes X002's status, no other family's (0.7) | **HIT**, with a refinement: one status was not enough. Reality needed a registry-level verdict *and* a per-id verdict, because `body-deleted` + `elsewhere-in-doc` is the true state and neither alone says it. |
| P6 | 2–4 operational facts stale (0.65) | **HIT at the low bound** — 2 strictly stale (address/key, "(Mac)"). The other two edits are *additions* of later findings, not corrections. Counting them would be scoring my own generosity. |
| P7 | restoring clears the whole X002 family (0.8) | **HIT on outcome, WRONG on mechanism.** Restoring alone would *not* have cleared it: `D-013` landed under Track E, and the registry was declared as `§ Ground rules`. The family closed only because the declaration was widened too. P7 itself flagged the residual risk — "the tool has never once been run against a NON-empty X002 registry, that path is unexercised" — and the unexercised path did have a bug. Right worry, wrong specific fear. |
| P8 | mutation 80–100% (0.6) | **HIT** — 82% first pass |

The MISS is the useful one. P3 assumed one destructive commit implies a
destructive *pattern*; the measurement says `e376750` truncated `CLAUDE.md`
and nothing else in the authoritative scope. That is what makes X001 real
authorship, and it is why the tool reports per-id rather than per-corpus.

## 8. Reusable output

`skills/deleted-vs-never-written/SKILL.md` — before classifying a gap as
authorship, ask version control. "Missing" is at least three states
(**deleted** / **misfiled** / **never written**) with different owners and an
order-of-magnitude cost difference, and they are indistinguishable in a
working tree. Includes the empty-container signal, the no-`--follow` rule,
the working-tree-vs-history split, the verbatim-restore-then-reconcile
discipline, and the diff that proves a restoration is one.
`skills/citation-registry-integrity/SKILL.md` corrected — it carried round
345's false "in every commit that touched the file" claim into a reusable
skill, and now carries the sequel and a pointer here instead.

## 9. Honest limitations

- **The restoration is a judgement call an operator may want to review.**
  §4 lists every deviation from `ee30654`; nothing else changed.
- **`--provenance` covers declared registries only.** The repo-wide
  empty-section scan that scored P4 was a one-off script, not shipped. It
  found nothing outstanding, so shipping it now would be a checker with no
  known job; the technique is written up in the skill instead.
- **Shallow clones make the verdict meaningless.** Handled (`no-vcs`) but
  never exercised against a real shallow clone.
- **X001 27/28/29 stay open**, correctly, for language(C) — now with
  evidence that it is authorship rather than an assumption.
- **`git log -S` is in the skill but not in the tool.** For an exact token it
  is much faster than reading revisions; the tool reads revisions because it
  must also answer the ordinal case, where there is no token to search for.
- **Nothing was learned about the NUC itself**, again. Nine consecutive
  E-rounds have now produced tooling and governance rather than box
  measurements, because the box has been unreachable for all nine.

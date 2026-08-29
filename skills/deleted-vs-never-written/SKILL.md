---
name: deleted-vs-never-written
description: Use when something a project depends on is MISSING and you are about to decide who fixes it — an empty "canonical" section, a rule everyone cites but nobody can find, a config key referenced by code and defined nowhere, a doc whose body is gone, a dangling identifier. Symptoms: someone concludes the content "predates our history" / "was lost in the migration" / "was never written"; a gap is escalated as a decision for an owner instead of being repaired; a note says "TODO: reconstruct". The move is to ask version control whether the text already exists before classifying the gap, because DELETED (transcribe it — anyone may), MISFILED (it is under a different heading, and the pointer to it is also wrong), and NEVER-WRITTEN (authorship — needs the owner) look identical in a working tree and have completely different costs. NOT for finding which commit broke a behaviour (that is bisect), and NOT for recovering uncommitted work.
---

# Deleted, misfiled, or never written

"Missing" reads as one state in a working tree and is at least three, with
different owners and an order-of-magnitude difference in cost:

| state | evidence | who fixes it | cost |
|---|---|---|---|
| **deleted** | a commit removed it | anyone | transcription |
| **misfiled** | it exists, under another heading/path | anyone | transcription + fix the pointer |
| **never written** | no revision ever had it | the owner | authorship |

The whole distinction is one `git log` away, and the default is to skip it —
because an absent thing offers no hint that it was ever present. So a
repairable gap gets classified as authorship, escalated to an owner, and
parked. Parked gaps are permanent.

The case this was written from: a research program's governing file had a
`## Ground rules` heading with nothing under it. A rule ID defined in that
section was cited **42 times** across the corpus. An audit found the dangling
citations, checked the file, concluded the body "predates this repo's git
history and was lost in the migration", and correctly declined to invent the
rules that govern every unit of work — filing it as the operator's call.

The body was in git the whole time: present at the initial commit, deleted by
a bulk `AUTO-COMMIT` that also removed 36 other lines, and gone from the
working tree for ~200 units of work. Restoring it was transcription and took
minutes. Nobody had run `git log` on the file, because the file was *there* —
only its contents were missing, and that is the case that does not look like
a deletion.

Second-order lesson from the same case: the rule was **misfiled** relative to
where everyone said it lived. The audit had declared the registry to be
`§ Ground rules`; the definition was actually under `§ Track E — HARD RULES`
in the same file. A search scoped to the declared section — the correct,
disciplined scope for the audit's purpose — reported the document as never
populated. Widening only to the rest of the *same document* found it.

## Trigger conditions

Reach for this when any of these is true:

- You are about to write "this was never documented", "predates our history",
  "lost in the migration", or "we'll have to reconstruct it".
- A heading, section, table or config block is present but **empty**. This is
  the highest-yield signal: the container surviving its contents is what a
  partial deletion looks like, and it is invisible to anything that checks
  whether a file exists.
- An identifier, rule, flag or key is cited or read by code and defined
  nowhere you can find.
- A gap is being escalated to an owner "because it needs a decision", and no
  one has established that a decision is actually required.
- An audit or checker reports a registry/section/table as `empty` or
  `missing`. Every such report should carry a provenance verdict; if it does
  not, get one before acting on it.
- Work is produced by many short-lived units (autonomous rounds, contractors,
  rotating on-call) where a bulk mechanical commit could have destroyed
  content nobody was watching.

Do NOT reach for this to find which commit broke a *behaviour* — that is
`git bisect` — or to recover work that was never committed at all.

## Steps

1. **State the classification you are about to make, out loud.** "I am
   calling this authorship" is the sentence that should trigger the rest of
   these steps. If you are not classifying, you do not need this skill.

2. **Find the file the content belongs to**, even if the content is gone.
   For an empty section that is the file containing the heading; for an
   undefined identifier it is whatever document declares the registry.

3. **Ask for the file's history, not the repo's.**
   `git log --oneline -- <path>` — a handful of commits, usually. Then
   compare sizes across revisions: a truncation is obvious as a step down.
   `for c in $(git log --format=%h -- <path>); do echo -n "$c "; \`
   `git show $c:<path> | wc -l; done`
   Do **not** use `--follow`: it guesses at renames, and a wrong guess here
   attributes someone else's content to your gap — inventing a definition,
   which is the exact failure you are trying to avoid.

4. **Read the section, not the file, at each revision.** A file that grew
   monotonically can still have lost one section. Extract the body between
   the heading and the next heading of the same-or-shallower level, per
   revision, and record whether it was non-empty.

5. **If the declared location comes up empty, search the whole document,
   then the whole tree, at those revisions.** Misfiling is common and looks
   exactly like absence. `git log -S'<identifier>' --oneline -- <path>`
   (or without the path) finds the revision where the string appeared or
   vanished, which is faster than reading revisions when you have an exact
   token.

6. **Classify, and say which evidence supports it.** deleted → name the
   commit that removed it and the commit to transcribe from. misfiled →
   name both the real location and the wrong pointer, because there are two
   fixes. never written → say how many revisions you checked, so the claim is
   falsifiable rather than an impression.

7. **Transcribe verbatim, then reconcile separately and visibly.** Recovered
   content is usually stale in its *coordinates* (addresses, ports, paths,
   counts) while its *rules* are fine. Restore the rules byte-identical —
   diff them against the source revision and say so — and change only facts
   the tree already contradicts elsewhere, listing each change and its
   evidence. Do not launder a rewrite as a restoration.

8. **Fix the pointer too, if it was wrong.** Otherwise the next audit
   re-reports the gap and the next reader re-classifies it.

9. **Leave the provenance in the file.** A short note saying what was
   recovered, from which commit, and what was deliberately changed. Without
   it the next bulk commit deletes it again and the next reader repeats the
   whole investigation.

## Exact commands

```sh
# 1. every revision of the file, newest first
git log --oneline -- CLAUDE.md

# 2. size per revision -- a truncation shows up as a step down
for c in $(git log --format=%h -- CLAUDE.md); do \
  echo -n "$c "; git show "$c:CLAUDE.md" | wc -l; done

# 3. the content at a suspect revision
git show ee30654:CLAUDE.md

# 4. where an exact identifier entered or left, without reading revisions
git log -S'D-013' --oneline -- CLAUDE.md

# 5. which heading actually owned it (misfiled vs absent)
git show ee30654:CLAUDE.md | awk '/^## /{h=$0} /D-013/{print h; print}'

# 6. prove a restoration is a restoration
git show ee30654:CLAUDE.md | sed -n '/^## Ground rules/,/^## Track E/p' > /tmp/old
sed -n '/^## Ground rules/,/^## Track E/p' CLAUDE.md > /tmp/new
diff /tmp/old /tmp/new && echo "byte-identical"
```

Automated, over a whole corpus of declared registries:

```sh
python3 skills/skill-authoring/scripts/xref_check.py --provenance
```

## Pitfalls

- **The container survives the contents.** An empty heading is the single
  highest-yield signal and the easiest to walk past, because every check that
  asks "does the file exist" says yes. Search for headings with no body.

- **A monotonically growing file can still have lost a section.** Comparing
  total line counts across revisions is a fast screen, not a verdict. Read
  the section.

- **"Populated now?" is a question about the working tree; "ever populated?"
  is a question about history.** Reading HEAD for the current state makes the
  tool report `deleted` about a file someone has *already repaired on disk* —
  which is its state every time anyone actually uses it. Read the working
  tree for now, git for ever.

- **A section can be full of prose and still define none of your ids.**
  "Has a body" and "defines what I am looking for" are different questions.
  Conflating them reports `never populated` about text a commit deleted, and
  sends the reader away from recoverable content.

- **`git log -- <path>` lists the commit that DELETED the path**, and
  `git show <sha>:<path>` then fails for that revision. Skip it; do not
  record it as a revision where the content was empty, or a deletion becomes
  evidence of absence.

- **Don't let `--follow` invent history.** A rename guess that lands on the
  wrong file hands you someone else's text to "restore".

- **Restoring stale coordinates is a real hazard, not a cosmetic one.**
  Recovered governance often carries an old address, port or path. Restore
  rules verbatim; reconcile coordinates against what the tree records now,
  and mark every change. A restored file that sends the next reader to a dead
  host is worse than the empty one.

- **The gap may be genuinely never-written, and that is a real result.** In
  the case above a *second* dangling family in the same corpus — spec
  decisions 27, 28, 29, cited 69 times — turned out never to have existed in
  any of 46 revisions. Same symptom, opposite verdict, opposite owner. The
  point is to measure, not to assume recovery.

- **Shallow clones and truncated history lie.** In CI, `fetch-depth: 0` or
  the verdict is worthless; report `no-vcs` rather than `never written`.

## Verification

```sh
python3 -m pytest skills/skill-authoring/scripts/test_xref_check.py -q
# expected: 112 passed. Covers all five registry verdicts (ok / ids-deleted /
# body-deleted / never-populated / no-vcs) and all four per-id verdicts
# against REAL git repos built in tmp, not an injected runner.

python3 skills/skill-authoring/scripts/xref_check.py --provenance
# expected: exit 0, and every dangling id labelled either RESURRECTABLE
# (with the commit to transcribe from) or "Writing it is authorship".
```

Check your own restoration the way step 7 asks: `diff` the restored section
against the source revision and expect *no output* for the parts you claim
are verbatim. If the diff is non-empty for those parts, you rewrote rather
than restored, and the provenance note you are about to write is false.

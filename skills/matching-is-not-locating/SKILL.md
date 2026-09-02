---
name: matching-is-not-locating
description: Use when a record cites evidence by quoting it — a ledger entry with a `quote` and a file path, an audit row citing a log line, a docs test asserting a snippet appears in a page, a "see the sentence in X" reference — and a checker re-derives the claim by substring search. "Is the quote in the file?" passes on a quote that is in that file TWICE (it locates nothing) and on a quote that is in fifty files (the path could have been wrong and nothing would say so). The move is to substitute the COORDINATE, not the content: would the same check still pass if the record named a different file, section or row? Covers choosing the substitution unit, pricing the backlog before choosing a severity, why a minimum-length rule is the proxy and not the defect, and the self-reference trap where writing about a weak anchor weakens it. NOT for checking a link or #fragment resolves (citation-registry-integrity), and NOT for a claim still findable but no longer TRUE (carried-claim-rot).
---

# An anchor that cannot fail on the wrong coordinate is not an anchor

A record that cites evidence has two halves: a **coordinate** (a path, a
section, a row id) and an **anchor** (the quoted text that should be found
there). The obvious checker re-reads the coordinate and asks:

```python
if quote not in open(where).read():
    report("the claim cannot be re-derived")
```

That test passes whenever the string is present. Presence is not the
property anyone wanted. The property is that **the anchor identifies the
coordinate** — and the way to test it is to try the coordinate you did
*not* write:

> Would this check still pass if `where` named some other file?

If yes, the record could have carried the wrong coordinate all along and the
checker would have said nothing. The check is not verifying the citation; it
is verifying that the corpus contains a string.

Two shapes fail it, and they are different failures:

| shape | what the anchor does | why the substring test misses it |
|---|---|---|
| **ambiguous** — quote occurs 2+ times inside the coordinate | points at two places, so at neither | `in` is a boolean; it never counts |
| **non-locating** — quote also occurs under other coordinates | would have matched the wrong file too | the wrong file is never tried |

## When this triggers

* A ledger, manifest, audit row or compliance record stores a `quote` (or
  `snippet`, `excerpt`, `evidence`, `matched_text`) beside a path, and
  something re-checks it with a substring search or `grep -q`.
* A docs or tutorial test asserts `assert snippet in page_text`.
* A checker reports "the cited sentence is no longer at the cited path" and
  you are about to widen the rule so it stops complaining.
* Someone proposes a **minimum length** for a quoted anchor, or a "must be
  at least N words" rule. That is a proxy; read step 4 before shipping it.
* Review finds a record whose path is wrong but whose evidence "checks out".
* An anchor is a section heading, a table header, a status word, or a short
  tally (`8 HIT, 2 MISS`) — text whose form recurs by convention.

## Steps

1. **Name the coordinate and the anchor, separately.** In each record, which
   field says *where* and which says *what*. If one field does both (a
   `file.md:117` line number, say), the anchor is the line number and the
   text is decoration — a different problem, because line numbers do not
   survive an edit at all.

2. **Choose the substitution UNIT — the smallest thing the coordinate
   identifies.** This is the design decision that makes the check useful or
   useless. If some records point at a whole aggregate file (a changelog, a
   rolling status document, an append-only log), file-level substitution is
   vacuous: that file contains every record's text, so every anchor "appears
   elsewhere". Attribute the aggregate into sections and substitute
   *sections*. Getting this wrong reports the entire corpus or none of it.

3. **Define the OWN set honestly, then substitute everything outside it.**
   A record legitimately matches in more than one place: the thing being
   cited, and whoever did the citing. Exclude those, substitute the rest.

   ```python
   own = {record.subject, record.author}          # both, or you get false reds
   foreign = [c for c in coordinates
              if c.owner not in own and quote in c.text]
   ```

4. **Price the backlog BEFORE choosing a severity — and price the proxy
   beside it.** Count, over the live records: anchors absent from their
   coordinate; anchors occurring 2+ times; anchors satisfied by a foreign
   coordinate; and anchors that the proxy someone proposed (length, word
   count) would report. Put the four numbers in one table. The measured
   result in this program was:

   | rule | records reported (of 139) |
   |---|---|
   | absent from its coordinate (the live rule) | 0 |
   | occurs 2+ times | 1 |
   | satisfied by a foreign coordinate | 6 |
   | shorter than 40 characters (the proposed proxy) | 53 |

   The proxy reports 53 to reach 6, and every one of the 6 is also short —
   so it buys no recall at 8.8x the false positives. **A proxy that
   correlates with the defect is not the defect.** Measure both and let the
   table choose.

5. **Ship the codes separately, and let the priced backlog set the
   severity.** Ambiguity and non-location have different repairs (quote more
   text vs quote something specific), so one code that means both cannot be
   acted on. If the backlog is small and mechanically repairable, repair it
   and ship ERRORs against zero. If it is large, ship warnings and say who
   owns the debt — a check that goes red every run for a debt nobody is
   clearing gets ignored, then uninstalled.

6. **Repair by strengthening the anchor, never by widening the rule.** The
   strongest anchor is the one that *names its own subject*: a sentence
   containing the record's own identifier or path cannot be satisfied by any
   other coordinate, by construction.

7. **Propose repairs; do not auto-apply them.** A tool can list the lines in
   the coordinate that are unique and foreign-free. Which of them is *the*
   evidence sentence is a judgement about meaning, and a script that picks
   one is a prose classifier — the thing an evidence ledger exists instead
   of.

8. **Take the replacement out of the file BY INDEX, not by retyping it.**
   Slice `body[i:j]` between two markers you located in the file. Hand-typed
   anchors acquire straight quotes where the file has curly ones, an ASCII
   hyphen where the file has an em dash, or a collapsed double space — and
   the entry you just "repaired" fails the very check you are shipping.

9. **Pin both properties with tests that cannot pass vacuously.** One test
   per property over the live records, plus a non-vacuity test: hand the
   substitution a string the corpus really does repeat and assert it comes
   back non-empty. Two green tests over a scan that silently returns nothing
   are two green tests about nothing.

10. **Keep the pricing runnable.** Ship the audit as a subcommand
    (`--audit-quotes`, `--audit-anchors`) so the next reader re-derives the
    four numbers instead of quoting yours. In this program the number `54 of
    138` was published one commit before the same round's own repair made it
    `53 of 139`.

## Pitfalls

* **Writing about a weak anchor weakens it.** If the corpus you substitute
  over includes prose that discusses the records, then quoting a live anchor
  in a post-mortem creates a new foreign match for it. Two of the six
  findings above were manufactured this way — by the round that *diagnosed*
  the defect, quoting the two anchors in its write-up. This is not a bug in
  the rule (a file carrying the exact sentence really is a file the record
  could have mis-named), but it dictates the discipline: **in prose about
  the check, paste the OLD anchor, never a live one.** Verify it after
  writing: run the check on your own draft.

* **A length floor feels safe because it is monotone.** "Longer is more
  specific" is true on average and useless per record: a 200-character
  boilerplate paragraph is non-locating and a 21-character string containing
  a unique id is perfect. Length is available without building anything,
  which is the entire reason it gets proposed.

* **Substituting whole files when some coordinates ARE whole files.** The
  records pointing at the rolling status document will each report dozens of
  foreign matches, all spurious, and the check gets reverted in a week.

* **Forgetting the second member of the OWN set.** Records where the author
  differs from the subject (a later entry discharging an earlier one's
  obligation) will report a foreign match against the author's own file.

* **Reporting all three codes for one defect.** If the anchor is absent
  there is nothing to count occurrences of. Chain them: absent → stop.
  Otherwise the count in the summary line triples for a single bad record.

* **Auto-requoting the whole backlog.** Tempting once the proposer works,
  and it converts a ledger of adjudicated evidence into a ledger of
  whatever-matched. Repair only what the codes report.

* **Assuming the repair is a strengthening.** Keep the anchor you replaced
  in the record (`quote_was`), and test that the OLD anchor is still one the
  codes would report. Otherwise a repair that swapped one weak anchor for
  another passes every other test you have.

## Verification

Run from the repo root. Both must exit 0.

```sh
# 1. each code fires on a record built to trigger it and stays silent on the
#    near-miss beside it; section-vs-file substitution unit pinned both ways;
#    the live ledger's anchors are unique and foreign-free; non-vacuity
#    pinned in both directions
cd skills/skill-authoring/scripts && \
  python3 -m pytest -q test_carryforward_check.py -p no:cacheprovider

# 2. the pricing, re-derived rather than quoted
python3 skills/skill-authoring/scripts/carryforward_check.py --audit-quotes \
  | grep '^-- '
```

Expected from (2), a line of the form:

```
-- N scored entr(ies): 0 absent from `where` (K002), 0 occurring 2+ times
(K005), 0 with a foreign scope (K006), <dozens> shorter than 40 chars
(the PROXY, not a finding)
```

The first three zeros are the enforcement. The fourth number staying large
is the point of step 4: those records locate their evidence perfectly well
and a length rule would report every one of them.

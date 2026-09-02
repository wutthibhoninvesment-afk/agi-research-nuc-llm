#!/usr/bin/env python3
"""selfdesc_check.py — re-derive the claims a DATA file makes about itself.

Why this exists
---------------
This repo's machine-readable artefacts carry prose. A registry opens with a
`_comment` that says what reads it, what its fields mean, how many entries it
has, and which things are deliberately absent; a pin registry opens with a `_`
that says what it was derived from and what must be true of it. That prose is
authoritative — it is the only description of the artefact anybody reads — and
until round 435 **no checker in this program had ever looked at a single
character of it**:

    xref_check.py:126   SCANNED_EXTS = (".md", ".py", ".lang", ".sh")

`.json` is not in that tuple. So X004 (prose path) checks every path token in
every markdown file, every Python file and every shell script in the tree, and
skips the ~26 000 characters of present-tense assertion sitting inside 25 JSON
artefacts. The other checkers are narrower still: `claim_check` reads SKILL.md
`## Verification` blocks, `state_claim_check` reads research-state.md's live
next-steps block, `carryforward_check` reads a ledger's structure and never its
`_comment`.

Round 434 found two defects of this shape by hand, one round apart, and said so
in its own next-steps item 6: *"Neither was found by a test — both were found by
comparing an artefact against the prose that describes it. That comparison has
not been run against the other registries."* This file is that comparison, run
by a machine, over every artefact in the tree rather than the two somebody
happened to open.

What is checkable, and what deliberately is not
-----------------------------------------------
Prose is not a specification language and this file does not pretend to parse
English. It looks for the claim SHAPES that recur across the corpus and that each
reduce to a lookup:

`J001` ERROR  a "read by <path>" claim naming a path that does not exist.
`J002` ERROR  the artefact's own basename appears in NO source file in the
              tree, while its prose names a reader — nothing reads it at all.
`J003` WARN   a named reader exists but never mentions the artefact's
              basename: the claim points at the wrong module, or the real read
              goes through a helper (indirection, worth seeing, not an error).
`J004` ERROR  a repo-relative path token in the prose that does not resolve.
              Semantics are xref_check's X004 exactly — same tokeniser, same
              recovery rules, same `state/known-absent-paths.json` allowlist —
              because a path in a `_comment` is not a different kind of path.
`J005` ERROR  a COUNT claim: a numeral or number-word whose noun names one of
              the SUBJECT's own collections, disagreeing with that
              collection's length. The subject is the node the prose sits on
              (round 447), so a `why` inside one entry counts that entry's
              collections and not the file's.
`J006` ERROR  an ABSENCE claim: the prose says some id is not here, and it is.
`J007` INFO   a count/absence claim that carries its own "as of round N"
              qualifier. Never an error, and reported so the difference is
              visible: a dated claim is a record, an undated one is an
              assertion about the present tense.
`J008` ERROR  a "regenerate, do not hand-edit" instruction on an artefact no
              source file in the tree can regenerate.
`J010` ERROR  a DELTA claim: "<sibling>.json with N <field>s changed". The
              sibling is resolved, the two element lists are diffed on that
              field, and N is checked. This is the one shape J005 cannot
              reach, because its noun is a per-element FIELD (`guardian`) and
              not a collection (`pins`) — found by hand-diffing the corpus
              after J005 came back silent on a registry whose own header
              undercounts by one.
`J012` ERROR  a count whose noun is a per-element FIELD of the subject's own
              elements, with no sibling named — the recall gap round 435's
              next-steps item 2 opened between J005 (whose denominator is a
              COLLECTION) and J010 (whose denominator is another FILE). Two
              readings of the phrase are both honest — how many elements
              CARRY the field, and how many DISTINCT values it takes — so it
              fires only when the number matches neither, and prints both.
`J011` WARN   an UNWATCHED executable claim — "`polarity.py audit` over this
              file must report 0 MISPOINTED" — in a data file that no test
              names. Reported statically with an `N/M must-claims` coverage
              token and never executed: running a command found in a data
              file is `claim_check --run`'s opt-in tier and its reasons (this
              corpus holds commands that ssh to another machine, spend money,
              and run for minutes) apply here unchanged. The "watched" half
              is not decoration — this repo's one live must-claim IS false
              (`audit` reports 5 MISPOINTED where the registry says 0) and a
              round-426 test in the whence slow tier already holds that
              failure open by name. A checker that reported it as unwatched
              would be crying wolf at the one place the discipline worked.

Everything else — "this is the third acknowledgement registry in state/", "the
direction is fail-closed", "a stale entry costs wall-clock; it cannot cost
coverage" — is a claim about MEANING and is left alone. Silence on those is not
coverage, so the summary line publishes the denominator: how many artefacts, how
many prose fields, and how many of those fields yielded no checkable claim at
all.

WHAT THE COVERAGE TOKEN COUNTS, and what it counted until round 447
-------------------------------------------------------------------
`coverage N/M prose-fields` is now N = fields in which at least one lookup RAN
— a count compared, a path resolved, a reader looked up — whether or not it
produced a finding.

It used to be `prose_fields - silent_fields`, where a field was silent when it
produced no `Finding`. That is the FINDING COUNT wearing coverage's name. A
field whose count claim was checked and found CORRECT was published as
uncovered, so the token could only rise when the corpus got WORSE, and it read
`coverage 0/28` on the live tree for exactly the reason the corpus was clean.
Round 435's own next-steps item 3 read that number as "one of 26
self-descriptions yields a checkable claim today", which is what the token was
meant to mean and not what it measured. The two numbers are now both
published, on the line above the summary, and they move independently.

The two discriminators that carry the design
--------------------------------------------
**J005 must not fire on `"Two kinds so far: (1) … (2) …"`.** That sentence sits
in `state/known-absent-paths.json`, whose `paths` map has three entries, and a
count-checker that reads "Two" and finds 3 is a broken checker, not a finding.
The noun decides: `kinds` names nothing in the artefact, `paths` does. A count
claim is only checkable when its noun matches a top-level collection key, that
key's singular/plural form, or the collection's element noun (`pins` -> `pin`).

**J006 must fire on CP05 and stay silent on CP01/CP02, from one sentence.**
`state/whence/round-422/host-pins-plus.json` says *"Round 414's CP01/CP02/CP05
are LATERAL … and have no mirror"*, and `CP05p` is a pin in that same file. The
rule is a STEM lookup against ids derived from the artefact: `CP05` is not an
id, but an id starts with it, so the mirror the prose denies is right there.
Nothing starts with `CP01` or `CP02`, so those two are correct and stay quiet.
Both halves of the discrimination come out of one sentence in one file, which is
why that file is the fixture.

Acknowledgements
----------------
`state/known-selfdesc-drift.json`, CONTENT-PINNED on the prose field's sha256 —
the same discipline as `state/known-unfilled-placeholders.json` and
`state/known-escalated-diffs.json`. Edit the sentence and the acknowledgement
expires by itself. An entry that matches nothing is reported DEAD (`J009`), an
acknowledgement that suppresses nothing being the mute button those files exist
to refuse.

Where the prose is, and what it is about
----------------------------------------
Until round 447 this file read six literal field NAMES at the TOP LEVEL of
each artefact. Both halves of that were too narrow, and they are separate
gaps with separate fixes:

  * the NAME gap — `SELF_FIELD_RE` now accepts this repo's round-stamped
    idiom (`_round_446_note`, `_round_349_addendum`). Every such field in
    `state/known-unprobed-skills.json` is top-level and was skipped on its
    name, which is why calling this a "top-level only" sweep pointed at the
    wrong fix. No count is given here on purpose: the file grows one note
    per round, and a number in this docstring would be the very shape of
    claim the checker below exists to catch;
  * the DEPTH gap — prose is now collected at any depth, and each field
    carries the `Subject` it describes, so a nested claim is checked against
    its own parent rather than against the file. See `Subject`.

`description` and `summary` are deliberately excluded: they are the key names
in captured OpenAI tool payloads and skill-frontmatter mirrors, 803 fields of
text this repo RECORDED rather than ASSERTED.

Usage:
    python3 selfdesc_check.py [--repo-root DIR] [--json OUT] [--show-acknowledged]
Exit: 0 = no ERRORs, 1 = at least one ERROR.
"""

import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import xref_check                                            # noqa: E402

#: The string fields that are a self-description rather than data. `_` and
#: `_comment` are this repo's two idioms; the rest are what the corpus
#: actually contains, checked rather than guessed.
#:
#: Round 447: this was an exact-name tuple, and round 435's own next-steps
#: item 3 called the resulting gap a TOP-LEVEL-only sweep. That reading was
#: wrong in a way worth recording, because it points at the wrong fix: every
#: `_round_NNN_note` field in `state/known-unprobed-skills.json` is TOP-LEVEL
#: and was skipped anyway, on its NAME. Depth was a second,
#: independent gap. The tuple is kept — it is what the six idiom names are —
#: and the rule below is what decides.
SELF_FIELDS = ("_", "_comment", "_note", "_why", "note", "comment")

#: A field name that carries this repo's own prose about the node it sits on.
#: `_round_449_note` / `_round_349_addendum` are the round-stamped idiom: a
#: round appends its reasoning under a new key rather than editing the one
#: below it, so the NAME is generated and cannot be enumerated.
#:
#: `description` and `summary` are deliberately NOT here, and the exclusion is
#: measured rather than assumed: they are the key names in the OpenAI tool
#: payloads captured under `nuc/hermes-dump/` and in the skill-frontmatter
#: mirrors under `state/skills*/`, which together hold 803 fields of text this
#: repo RECORDED rather than ASSERTED. A checker that reads a captured payload
#: as a self-description is checking somebody else's sentence.
SELF_FIELD_RE = re.compile(
    r"^(?:_|_?comment|_?note|_?why|_?rationale|_?caveat"
    r"|_round_\d+_[a-z0-9_]+"
    r"|[a-z0-9_]*addendum)$", re.I)

#: Under this and a field is a label, not a description. 40 chars is roughly
#: one clause; nothing shorter in the corpus makes a checkable claim.
MIN_PROSE = 40

#: Artefacts larger than this are sweep dumps whose prose is a caption over
#: millions of rows; parsing them costs seconds and yields nothing.
MAX_BYTES = 2_000_000

SKIP_DIR_PARTS = (".git", "node_modules", "__pycache__", ".pytest_cache",
                  ".venv", "research-env", "whence_lang.egg-info")

ACK_FILE = os.path.join("state", "known-selfdesc-drift.json")

SEV = {"J001": "ERROR", "J002": "ERROR", "J003": "WARN", "J004": "ERROR",
       "J005": "ERROR", "J006": "ERROR", "J007": "INFO", "J008": "ERROR",
       "J009": "ERROR", "J010": "ERROR", "J011": "WARN", "J012": "ERROR"}

PASS, ERRORS_FOUND = 0, 1

# --------------------------------------------------------------------------
# Prose grammar
# --------------------------------------------------------------------------

#: "read by harness/tierbudget.py", "Read by skills/.../xref_check.py's X004".
#: The path is captured by X004's own tokeniser downstream; here we only need
#: to know a reader was NAMED and where the claim starts.
READER_RE = re.compile(r"\b[Rr]ead by\b", re.M)

#: A reader named as a bare module rather than a path: "read by
#: check_round_recorded.py's unattributed_dirty_paths".
MODULE_TOKEN_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*\.(?:py|sh))\b")

NUMBER_WORDS = {
    "zero": 0, "no": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
}

#: The number words that are also English negation determiners. Meaningful
#: as a count of a CONTAINER, not of an attribute. See `check_element_counts`.
ZERO_WORDS = {"no", "zero"}

#: `<count> <adjectives>* <noun>`. The adjective slot is what lets "nineteen
#: guardian labels" and "the five shadowed pins" reach their noun; it is capped
#: at two words so a count never reaches across a clause boundary to borrow a
#: noun it was not about.
COUNT_RE = re.compile(
    r"\b(\d{1,4}|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) +
    r")\b((?:\s+[a-z][a-z\-]*){0,2}?)\s+([a-z][a-z\-]{2,})\b", re.I)

# The two discriminators J005 needs, and neither is decoration: without them
# the rule scored 0 true positives against 2 false ones on the live corpus,
# which is a precision of zero, not a checker.
#
#: (1) A DIFFERENT CONTAINER. "27 skills IN THE CORPUS" counts the skills
#: directory; the artefact's own `skills` map is a different set that happens
#: to share a noun. A prepositional phrase right after the noun re-points it.
OTHER_CONTAINER_RE = re.compile(
    r"^\s*(?:in|of|from|across|under|among)\s+"
    r"(?:the|a|an|its|this|that)?\s*[a-z]", re.I)
#: (1b) A PARTITIVE. "twenty OF the twenty-three pins", "5 of them" counts a
#: subset and agrees with nothing about the whole. The `of` binds to the
#: NUMERAL, not to the noun, so this is a separate window from (1).
PARTITIVE_RE = re.compile(r"^\s+of\b", re.I)

#: (2) A PAST-TENSE NARRATIVE. "Five banks HAD BEEN silently dropped" counts a
#: historical subset that is by definition not in the collection now. A count
#: claim is only about the present tense if its clause is in it. Scanned over
#: the WHOLE sentence, not the text before the count: the corpus's instance
#: opens with its numeral ("Five banks had been…"), so a look-behind window
#: sees an empty string and suppresses nothing. The recall cost is explicit —
#: a true count claim phrased in the past ("the three pins below WERE
#: re-pointed") is dropped, and `test_a_past_tense_true_count_is_dropped`
#: pins that as a known miss rather than leaving it to be discovered.
PAST_TENSE_RE = re.compile(
    r"\b(had been|had|were|was|used to|previously|originally|"
    r"until round \d+)\b", re.I)

#: The clause forms that assert something is NOT in the artefact.
ABSENCE_RE = re.compile(
    r"\b(ha(?:ve|s) no\b|and no\b|are absent\b|is absent\b|are not (?:here|in"
    r" this file)\b|no longer\b|is EMPTY\b|are EMPTY\b|nothing else\b)")

#: "as of round 357", "(round 422)", "ROUND 375:" — a claim that dates itself.
AS_OF_RE = re.compile(r"\bas of round \d+|\bwhen this was written\b|"
                      r"\bat capture\b|\bfrozen\b", re.I)

#: A field NAME that dates its own contents: `_round_446_note`,
#: `_round_349_addendum`. Round 447. The checker already had the right
#: concept — J007's "a dated claim is a record, an undated one is an
#: assertion about the present tense" — and looked for the date in the wrong
#: place. `AS_OF_RE` scans the SENTENCE; this repo's registries put the date
#: in the KEY and then write in the present tense underneath it.
ROUND_STAMP_RE = re.compile(r"^_round_(\d+)_")

#: An id in this corpus: a short alphabetic stem, digits, an optional
#: alphanumeric suffix. Derived ids are matched by STEM, never by this regex
#: alone — the regex only proposes candidates for a lookup.
IDLIKE_RE = re.compile(r"\b([A-Z]{1,6}\d{1,3}[a-z]?\d?)\b")

#: "`host-pins-plus.json` with nineteen guardian labels repointed and NOTHING
#: ELSE changed" — a claim about a DIFF against a named sibling artefact.
SIBLING_RE = re.compile(r"`?([A-Za-z0-9_./-]+\.json)`?")
DELTA_VERB_RE = re.compile(
    r"\b(repointed|changed|added|removed|edited|re-pointed|renamed|"
    r"differ|different|updated)\b", re.I)

#: "must report 0 MISPOINTED", "must print exactly one line". An assertion
#: about what running something produces, made inside a file nothing runs.
MUST_RUN_RE = re.compile(
    r"\bmust (?:report|print|say|emit|exit|come back|return)\b[^.;]{0,80}",
    re.I)

REGEN_RE = re.compile(
    r"regenerate, do not hand-edit|do not hand-edit|Derived file", re.I)

#: Sentence splitter that does not break on `v0.29`, `p25-p75` or `.py`.
SENTENCE_RE = re.compile(r"(?<=[.;:!?])\s+(?=[A-Z`\"(])")

SOURCE_EXTS = (".py", ".sh", ".md", ".lang", ".json")


def sentences(text):
    """(sentence, offset) pairs. Offsets are into `text`."""
    out, pos = [], 0
    for part in SENTENCE_RE.split(text):
        idx = text.find(part, pos)
        if idx < 0:
            idx = pos
        out.append((part, idx))
        pos = idx + len(part)
    return out


# --------------------------------------------------------------------------
# The artefact
# --------------------------------------------------------------------------

class Subject(object):
    """The NODE a prose field describes — the thing its claims are about.

    Round 447. A prose field's subject is the node it sits on, not the file
    it happens to be in. `state/known-unprobed-skills.json`'s top-level
    `_comment` describes the whole registry; the `why` inside
    `skills["losses-name-their-winner"]` describes that ONE entry. Counting
    "the five reasons" in the second against the FILE's collections is a
    category error, and it is the error a depth sweep makes by default.

    So the rules divide by subject scope, and the split is the design:

      * subject-scoped — J005 (counts), J006 (absence), J010/J012 (element
        deltas). Their denominator is `nouns()`/`ids()`/`elements()` of the
        node the prose sits on. A nested element with no sub-collections has
        no nouns, so these rules go quiet there BY CONSTRUCTION rather than
        by an exclusion list.
      * tree-scoped — J001/J003 (a named reader), J004 (a path), J011 (an
        executable claim). A path is the same claim at any depth.
      * artefact-scoped — J002 (nothing reads this file), J008 (nothing
        regenerates it). One defect per FILE however many fields repeat it,
        so `sweep` de-duplicates them.

    `collections` no longer filters on truthiness. An EMPTY collection is
    still a collection, and it is where drift lives: a list drained to zero
    by a later round leaves the sentence that counted it standing. The live
    instance is this checker's own acknowledgement registry — round 435
    created `state/known-selfdesc-drift.json` with one entry and prose saying
    so, round 437 fixed the prose it acknowledged and emptied the list, and
    the sentence "only the one … is here" survived. Under `and v` the noun
    `acknowledged` did not exist, so the claim was unreachable.
    """

    def __init__(self, node):
        self.node = node if isinstance(node, dict) else {}
        self.collections = {k: v for k, v in self.node.items()
                            if isinstance(v, (list, dict))}
        self.ids = self._ids()

    def _ids(self):
        """Every identifier this artefact could be said to CONTAIN.

        Derived from the artefact, never from a list in this file
        (`skills/derived-subject-set`): the keys of every top-level mapping,
        plus every `id`/`name` value at any depth. A registry that starts
        keying its entries differently is covered the day it does.
        """
        found = set()

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in ("id", "name", "node") and isinstance(v, str):
                        found.add(v)
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        for key, val in self.collections.items():
            if isinstance(val, dict):
                found.update(k for k in val if isinstance(k, str))
        walk(self.node)
        return {i for i in found if i}

    def elements(self):
        """The artefact's primary element list: the longest list of dicts.

        `pins` for a pin registry, `trials` for a trial record, `acknowledged`
        for an acknowledgement file. Derived, never named here.
        """
        best = []
        for val in self.collections.values():
            if isinstance(val, list) and val and all(
                    isinstance(x, dict) for x in val) and len(val) > len(best):
                best = val
        return best

    def element_fields(self):
        return {k for el in self.elements() for k in el}

    def nouns(self):
        """noun -> collection length, for every way the prose could name one.

        `pins` -> 23, `pin` -> 23, `escalations`/`escalation` -> 1. The
        singular is included because English counts in it ("one pin"), and
        the element noun because registries are named for their plural.
        """
        out = {}
        for key, val in self.collections.items():
            n = len(val)
            k = key.strip("_").lower()
            out[k] = n
            if k.endswith("ies"):
                out[k[:-3] + "y"] = n
            elif k.endswith("s"):
                out[k[:-1]] = n
            else:
                out[k + "s"] = n
        return out


class ProseField(object):
    """One self-description: where it is, what it says, what it is about."""

    def __init__(self, path, text, subject, depth, name):
        self.path = path            # "_comment", "skills.foo.why"
        self.text = text
        self.subject = subject      # the Subject its claims are about
        self.depth = depth          # 0 = describes the whole artefact
        self.name = name            # the key itself, without the dotted path
        m = ROUND_STAMP_RE.match(name)
        self.round = int(m.group(1)) if m else None
        #: Set by `Artefact`: True when a LATER round-stamped note exists in
        #: the same artefact. See `Artefact.__init__`.
        self.superseded = False

    def __repr__(self):
        return "<ProseField %s depth=%d>" % (self.path, self.depth)


def _walk_prose(node, path, depth, out):
    """Every prose-shaped field at any depth, each with its parent Subject.

    The parent is the SUBJECT (see `Subject`), so the walk carries the
    containing dict down rather than re-deriving it from a dotted path.
    List indices appear in the reported path as `[i]` and never become a
    subject: a claim's denominator is the dict that holds it.
    """
    if isinstance(node, dict):
        subject = Subject(node)
        for k, v in node.items():
            if (isinstance(v, str) and len(v) >= MIN_PROSE
                    and SELF_FIELD_RE.match(k)):
                out.append(ProseField(
                    ".".join(path + [k]) if path else k, v, subject, depth, k))
        for k, v in node.items():
            _walk_prose(v, path + [k], depth + 1, out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_prose(v, path + ["[%d]" % i], depth + 1, out)


class Artefact(object):
    """One JSON file plus every prose field it carries, at any depth."""

    def __init__(self, rel, data):
        self.rel = rel
        self.data = data
        self.base = os.path.basename(rel)
        self.root = Subject(data)
        fields = []
        _walk_prose(data, [], 0, fields)
        #: THE NEWEST ROUND STAMP IS STILL THE PRESENT TENSE. Round 447.
        #:
        #: A round-stamped note is a claim about the artefact AT THAT ROUND,
        #: and today's file cannot falsify a claim about round 377 — this
        #: registry is not append-only, entries leave it when their debt is
        #: paid. So an OLDER stamp is a record (J007 INFO). The NEWEST stamp
        #: is different: nothing in the artefact says anything happened after
        #: it, so it is the file's most recent description of itself and is
        #: checked as an assertion about now.
        #:
        #: This is not free. The rule is a PROXY for "nothing has changed the
        #: collection since", and a round that edits a collection without
        #: stamping a note breaks the proxy — the newest older note would
        #: then be blamed for a change it predates. That direction is the
        #: right one: the false report is fixed by adding a note, which is
        #: the convention these files already document, and the alternative
        #: (dating every stamped field) is what hid this round's finding.
        #:
        #: Measured on the corpus the day it was written: it separates six
        #: J005s in `state/known-unprobed-skills.json` into five historical
        #: records and ONE live error — the batch depth carried as "SIXTEEN"
        #: against a map holding 26.
        newest = max([f.round for f in fields if f.round is not None],
                     default=None)
        if newest is not None:
            for f in fields:
                if f.round is not None and f.round < newest:
                    f.superseded = True
        self.newest_round_stamp = newest
        self.fields = fields
        #: Back-compat for callers that only ever wanted (name, text) pairs.
        self.prose = [(f.path, f.text) for f in fields]

    # The artefact's own root-scoped views, kept as attributes because the
    # tree-scoped rules and the tests both read them off the Artefact.
    @property
    def collections(self):
        return self.root.collections

    @property
    def ids(self):
        return self.root.ids

    def elements(self):
        return self.root.elements()

    def element_fields(self):
        return self.root.element_fields()

    def nouns(self):
        return self.root.nouns()


def _is_jsonl(path):
    """True for a `.json` that is really a one-object-per-line stream."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first = f.readline().strip()
    except OSError:
        return False
    if not first.startswith("{") or not first.endswith("}"):
        return False
    try:
        json.loads(first)
    except ValueError:
        return False
    return True


def scan_tree(repo_root):
    """Every JSON artefact in the tree carrying a self-description."""
    out, seen, unparseable, streams = [], 0, [], []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIR_PARTS]
        for fn in sorted(filenames):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, repo_root).replace(os.sep, "/")
            seen += 1
            try:
                if os.path.getsize(path) > MAX_BYTES:
                    continue
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                # A `logs/round-NNN.json` is a JSONL stream, not a malformed
                # artefact. Classified rather than lumped, because "254
                # unparseable files" reads as breakage and is not.
                (streams if _is_jsonl(path) else unparseable).append(rel)
                continue
            if not isinstance(data, dict):
                continue
            art = Artefact(rel, data)
            if art.prose:
                out.append(art)
    return out, seen, unparseable, streams


def source_index(repo_root):
    """basename -> sorted list of files mentioning it (any source extension).

    One walk, not one grep per artefact: the corpus is ~350 files and the
    per-artefact form was the slow half of the first draft.
    """
    idx = {}
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIR_PARTS]
        for fn in sorted(filenames):
            if not fn.endswith(SOURCE_EXTS):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, repo_root).replace(os.sep, "/")
            try:
                if os.path.getsize(path) > MAX_BYTES:
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            idx[rel] = text
    return idx


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

class Finding(object):
    def __init__(self, rel, field, code, message, quote=""):
        self.rel = rel
        self.field = field
        self.code = code
        self.message = message
        self.quote = quote
        self.severity = SEV[code]

    def __str__(self):
        return "%s[%s]: %s %s %s" % (self.rel, self.field, self.severity,
                                     self.code, self.message)

    def as_dict(self):
        return {"path": self.rel, "field": self.field, "code": self.code,
                "severity": self.severity, "message": self.message,
                "quote": self.quote}


def prose_hash(text):
    """The content pin for an acknowledgement: sha256[:16] of the field."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def tops_of(_mod):
    """The token set `prose_path_tokens` anchors on, for a one-off re-parse.

    Deliberately every plausible top-level name rather than the real listing:
    this call only needs to recover the TOKEN a reader claim named so J004
    can be told not to report it twice.
    """
    return _TOPS_SNAPSHOT


_TOPS_SNAPSHOT = set()


def check_readers(art, field, text, index, repo_root):
    """J001 / J002 / J003 — the "read by X" claim.

    Returns `(findings, n_claims)`. A CLAIM is one resolved lookup — a
    `read by <module>` whose module token was found and looked up — whether
    or not the lookup produced a finding. See `sweep` for why the two are
    counted separately.
    """
    out, claims = [], 0
    if not READER_RE.search(text):
        return out, claims
    mentions = [rel for rel, body in index.items()
                if rel != art.rel and art.base in body]
    if not mentions:
        out.append(Finding(art.rel, field, "J002",
                           "prose names a reader, but `%s` appears in no "
                           "source file in the tree — nothing reads it"
                           % art.base))
        return out, 1
    for m in READER_RE.finditer(text):
        tail = text[m.end():m.end() + 200]
        mods = MODULE_TOKEN_RE.findall(tail)
        if not mods:
            continue
        mod = mods[0]
        claims += 1
        hits = [rel for rel in mentions if os.path.basename(rel) == mod]
        exists = [rel for rel in index if os.path.basename(rel) == mod]
        if not exists:
            tok = next((t for t, _o, c in
                        xref_check.prose_path_tokens(tail, tops_of(mod))
                        if c and os.path.basename(t) == mod), mod)
            out.append(Finding(art.rel, field, "J001",
                               "prose says `read by %s` and no such file "
                               "exists in the tree" % mod, tok))
        elif not hits:
            out.append(Finding(art.rel, field, "J003",
                               "prose says `read by %s`, and %s never "
                               "mentions `%s` — the read is indirect or the "
                               "claim points at the wrong module"
                               % (mod, mod, art.base),
                               tail.split("\n")[0][:90]))
    return out, claims


def check_paths(art, field, text, repo_root, tops, allowlist, already=()):
    """J004 — X004's rule, on the prose X004 never scanned.

    `already` holds tokens a more specific code has claimed. A missing path
    that is ALSO a declared reader is one defect, and J001 says more about it
    than J004 does, so it is reported once under the sharper code.
    """
    out, claims = [], 0
    for tok, _off, checkable in xref_check.prose_path_tokens(text, tops):
        if not checkable or tok in allowlist or tok in already:
            continue
        claims += 1
        if xref_check.resolve_prose_path(repo_root, tok, tops) == "missing":
            out.append(Finding(art.rel, field, "J004",
                               "prose names `%s`, which does not exist" % tok,
                               tok))
    return out, claims


def check_counts(art, field, text, subject, superseded=False):
    """J005 / J007 — a numeral whose noun is one of the SUBJECT's own
    collections.

    `subject` is the node the prose sits on, not necessarily the artefact
    root (round 447). A claim is counted when the noun RESOLVES and survives
    the three discriminators — that is the point at which a comparison was
    actually made — and not when it merely disagrees.
    """
    out, claims = [], 0
    nouns = subject.nouns()
    for sent, _off in sentences(text):
        dated = bool(AS_OF_RE.search(sent)) or superseded
        for m in COUNT_RE.finditer(sent):
            raw, _adj, noun = m.group(1), m.group(2), m.group(3).lower()
            if noun not in nouns:
                continue
            said = int(raw) if raw.isdigit() else NUMBER_WORDS[raw.lower()]
            real = nouns[noun]
            if OTHER_CONTAINER_RE.match(sent[m.end():m.end() + 24]):
                continue                    # counts a different container
            if PARTITIVE_RE.match(sent[m.end(1):m.end(1) + 20]):
                continue                    # counts a subset: "20 of the 23"
            if PAST_TENSE_RE.search(sent):
                continue                    # counts a historical subset
            # Past this line a comparison HAPPENED: this is the claim, and it
            # is counted whether it holds or not. The three `continue`s above
            # are declines, not passes, so they are deliberately not counted.
            claims += 1
            if said == real:
                continue
            code = "J007" if dated else "J005"
            out.append(Finding(
                art.rel, field, code,
                "prose says `%s %s` and the artefact has %d%s"
                % (raw, noun, real,
                   " (claim is dated; recorded, not an error)"
                   if dated else ""),
                sent.strip()[:110]))
    return out, claims


def check_absence(art, field, text, subject, superseded=False):
    """J006 / J007 — the prose denies an id the SUBJECT contains."""
    out, claims = [], 0
    for sent, _off in sentences(text):
        if not ABSENCE_RE.search(sent):
            continue
        dated = bool(AS_OF_RE.search(sent)) or superseded
        for tok in IDLIKE_RE.findall(sent):
            # Every id-like token in an absence sentence is a lookup that
            # returned an answer, including "it really is absent".
            claims += 1
            if tok in subject.ids:
                continue
            hits = sorted(i for i in subject.ids if i.startswith(tok))
            if not hits:
                continue
            code = "J007" if dated else "J006"
            out.append(Finding(
                art.rel, field, code,
                "prose denies `%s` and %s is in this artefact%s"
                % (tok, "/".join(hits), " (claim is dated)" if dated else ""),
                sent.strip()[:110]))
    return out, claims


def check_regen(art, field, text, index):
    """J008 — an instruction to regenerate an artefact nothing generates."""
    if not REGEN_RE.search(text):
        return [], 0
    producers = [rel for rel, body in index.items()
                 if rel != art.rel and rel.endswith((".py", ".sh"))
                 and art.base in body]
    if producers:
        return [], 1
    return [Finding(art.rel, field, "J008",
                    "prose says the file is derived and must be regenerated, "
                    "and no .py/.sh in the tree names `%s`" % art.base)], 1


def check_delta(art, field, text, repo_root, subject):
    """J010 — "<sibling.json> with N <element-field>s <verb>"."""
    out, claims = [], 0
    fields = subject.element_fields()
    if not fields:
        return out, claims
    mine = {el.get("id"): el for el in subject.elements() if el.get("id")}
    for sent, _off in sentences(text):
        if not DELTA_VERB_RE.search(sent):
            continue
        for sm in SIBLING_RE.finditer(sent):
            tok = sm.group(1)
            cand = os.path.join(os.path.dirname(
                os.path.join(repo_root, art.rel)), os.path.basename(tok))
            if not os.path.isfile(cand):
                cand = os.path.join(repo_root, tok)
            if not os.path.isfile(cand) or os.path.samefile(
                    cand, os.path.join(repo_root, art.rel)):
                continue
            try:
                with open(cand, encoding="utf-8") as f:
                    other = Artefact(tok, json.load(f))
            except (OSError, ValueError, AttributeError):
                continue
            theirs = {el.get("id"): el for el in other.elements()
                      if el.get("id")}
            shared = set(mine) & set(theirs)
            if not shared:
                continue
            for m in COUNT_RE.finditer(sent):
                raw, adj, noun = m.group(1), m.group(2), m.group(3).lower()
                words = [w for w in (adj + " " + noun).split() if w]
                hit = next((w for w in words
                            if w in fields or w.rstrip("s") in fields), None)
                if hit is None:
                    continue
                key = hit if hit in fields else hit.rstrip("s")
                said = int(raw) if raw.isdigit() else NUMBER_WORDS[raw.lower()]
                real = sum(1 for i in shared
                           if mine[i].get(key) != theirs[i].get(key))
                claims += 1
                if said == real:
                    continue
                out.append(Finding(
                    art.rel, field, "J010",
                    "prose says `%s %s` changed against %s and %d of %d "
                    "shared element(s) differ on `%s`"
                    % (raw, noun, os.path.basename(tok), real, len(shared),
                       key),
                    sent.strip()[:110]))
    return out, claims


def check_element_counts(art, field, text, subject, superseded=False):
    """J012 — a count whose noun is a per-element FIELD of this same subject.

    Round 435's next-steps item 2, unpaid for twelve rounds: *"A count claim
    whose noun is a per-element FIELD (`nineteen guardian labels`) is
    invisible to J005; J010 catches only the sub-case where a sibling
    artefact is named in the same sentence."* J005's denominator is
    `nouns()`, which only knows COLLECTIONS (`pins` -> 23); `guardian` is a
    key inside each pin and names no collection, so the count falls through.
    J010's denominator is a diff against another file, so a sentence naming
    no sibling reaches nothing.

    The gap is the sentence that counts a FIELD inside the file it is in:
    "nineteen guardian labels", "the four `dir` values", "three exempt
    entries". Its denominator is the elements of the subject's own primary
    element list.

    **The rule is deliberately two-reading and fires only when BOTH fail.**
    English does not say which of two counts it means, and both are honest
    readings of the same phrase:

      * PRESENT — how many elements carry the field with a non-empty value
        ("nineteen guardian labels" = nineteen pins have a guardian);
      * DISTINCT — how many different values it takes ("nineteen guardian
        labels" = nineteen different labels).

    A rule that picked one would be right about half the corpus and would
    report the other half as drift. Firing only when the number matches
    NEITHER is the same discipline as `bounded-not-binary-witness`: the
    finding says "no reading of this sentence is true", which is a claim the
    prose can be held to, and the message prints both denominators so the
    reader can see which one the writer meant.

    Excluded on purpose, each because it is another rule's job or another
    rule's known decline:
      * a noun that is ALSO a collection name — J005 owns it, and reporting
        both would double-count one sentence;
      * a sentence naming a sibling `.json` — J010 owns it;
      * the three J005 discriminators (other-container, partitive,
        past-tense), applied unchanged: a widening that quietly dropped them
        would re-introduce the two false positives that took J005's
        precision to zero before they existed.
    """
    out, claims = [], 0
    elements = subject.elements()
    if not elements:
        return out, claims
    fields = subject.element_fields()
    nouns = subject.nouns()
    # J010's hand-off, with each half scoped to what it is a property of.
    # WHICH FILE this one is derived from is a property of the DOCUMENT; a
    # delta VERB is a property of the sentence. Scoping both to the sentence
    # (the first draft) mis-fired on
    # `state/whence/round-422/host-pins-plus-repointed.json`, whose header
    # names its sibling in a clause that `SENTENCE_RE` splits away 200
    # characters before the count — the exclusion was looking in a window
    # the claim had left. A sentence splitter is not a claim's scope.
    field_names_a_sibling = any(
        os.path.basename(m.group(1)) != art.base
        for m in SIBLING_RE.finditer(text))
    for sent, _off in sentences(text):
        if field_names_a_sibling and DELTA_VERB_RE.search(sent):
            continue                        # J010's sentence
        dated = bool(AS_OF_RE.search(sent)) or superseded
        for m in COUNT_RE.finditer(sent):
            raw, adj, noun = m.group(1), m.group(2), m.group(3).lower()
            # A CONTAINER can hold zero things; an ATTRIBUTE cannot be held
            # zero times in the sense English means by "no witness". `no`
            # and `zero` are in NUMBER_WORDS because "no pins" is a real
            # count claim about a collection — J005's subject. Before a
            # per-element FIELD name they are a negation of the field's
            # CONTENT ("no edit text, no witness" = the repoint changed
            # neither), and reading them as 0 made J012's only two live
            # hits on this corpus both false. The recall cost is explicit
            # and pinned by `test_a_true_zero_element_field_count_is_dropped`:
            # a genuine "no elements carry `witness`" is dropped with them.
            if raw.lower() in ZERO_WORDS:
                continue
            words = [w for w in (adj + " " + noun).split() if w]
            hit = next((w for w in words
                        if (w in fields or w.rstrip("s") in fields)
                        and w not in nouns and w.rstrip("s") not in nouns),
                       None)
            if hit is None:
                continue
            key = hit if hit in fields else hit.rstrip("s")
            if OTHER_CONTAINER_RE.match(sent[m.end():m.end() + 24]):
                continue
            if PARTITIVE_RE.match(sent[m.end(1):m.end(1) + 20]):
                continue
            if PAST_TENSE_RE.search(sent):
                continue
            said = int(raw) if raw.isdigit() else NUMBER_WORDS[raw.lower()]
            present = sum(1 for el in elements
                          if el.get(key) not in (None, "", [], {}))
            distinct = len({_hashable(el.get(key)) for el in elements
                            if el.get(key) not in (None, "", [], {})})
            claims += 1
            if said in (present, distinct):
                continue
            code = "J007" if dated else "J012"
            out.append(Finding(
                art.rel, field, code,
                "prose says `%s %s` and `%s` is a per-element field: %d "
                "element(s) carry it, %d distinct value(s)%s"
                % (raw, noun, key, present, distinct,
                   " (claim is dated; recorded, not an error)"
                   if dated else ""),
                sent.strip()[:110]))
    return out, claims


def _hashable(v):
    """A set key for an element field value of any JSON type."""
    if isinstance(v, (list, dict)):
        return json.dumps(v, sort_keys=True)
    return v


def find_must_claims(text):
    """J011's static tier: executable assertions, located and never run."""
    return [m.group(0).strip() for m in MUST_RUN_RE.finditer(text)]


def watched_by_a_test(base, index):
    """Test files naming this artefact. A named artefact is watched."""
    return [rel for rel in index
            if os.path.basename(rel).startswith("test_")
            and rel.endswith(".py") and base in index[rel]]


def load_acks(repo_root):
    try:
        with open(os.path.join(repo_root, ACK_FILE), encoding="utf-8") as f:
            return json.load(f).get("acknowledged", [])
    except (OSError, ValueError):
        return []


def sweep(repo_root):
    arts, n_json, unparseable, streams = scan_tree(repo_root)
    index = source_index(repo_root)
    tops = xref_check.top_level_dirs(repo_root)
    global _TOPS_SNAPSHOT
    _TOPS_SNAPSHOT = tops
    allowlist = xref_check.load_absent_allowlist(repo_root)

    findings = []
    n_fields = n_silent = n_must = n_watched = n_claims = 0
    n_nested = n_checked = 0
    #: J002 and J008 are claims about the FILE. Two prose fields repeating
    #: one of them is one defect, so they are reported once per artefact.
    seen_artefact_scoped = set()
    for art in arts:
        for pf in art.fields:
            field, text, subject = pf.path, pf.text, pf.subject
            n_fields += 1
            if pf.depth:
                n_nested += 1
            got, claims = [], 0
            f, c = check_readers(art, field, text, index, repo_root)
            got += f
            claims += c
            claimed = {x.quote for x in got if x.code == "J001"}
            f, c = check_paths(art, field, text, repo_root, tops, allowlist,
                               claimed)
            got += f
            claims += c
            f, c = check_counts(art, field, text, subject, pf.superseded)
            got += f
            claims += c
            f, c = check_absence(art, field, text, subject, pf.superseded)
            got += f
            claims += c
            f, c = check_regen(art, field, text, index)
            got += f
            claims += c
            f, c = check_delta(art, field, text, repo_root, subject)
            got += f
            claims += c
            f, c = check_element_counts(art, field, text, subject,
                                        pf.superseded)
            got += f
            claims += c
            must = find_must_claims(text)
            n_must += len(must)
            claims += len(must)
            watched = watched_by_a_test(art.base, index) if must else []
            n_watched += len(must) if watched else 0
            for claim in must:
                if watched:
                    continue
                got.append(Finding(
                    art.rel, field, "J011",
                    "an executable claim in a data file, and no test in the "
                    "tree names `%s`" % art.base, claim[:110]))
            kept = []
            for x in got:
                if x.code in ("J002", "J008"):
                    key = (art.rel, x.code)
                    if key in seen_artefact_scoped:
                        continue
                    seen_artefact_scoped.add(key)
                kept.append(x)
            # Round 447: SILENT and CHECKED are different questions, and
            # until this round the summary answered the first while calling
            # it the second. A field whose count claim is TRUE produces no
            # finding and IS checked; the old `prose_fields - silent_fields`
            # published it as uncovered, so the coverage token could only
            # rise when the corpus got worse and read 0/28 precisely because
            # the corpus was clean.
            if not kept:
                n_silent += 1
            if claims:
                n_checked += 1
            n_claims += claims
            findings += kept

    acks = load_acks(repo_root)
    by_pin = {}
    for art in arts:
        for pf in art.fields:
            by_pin[(art.rel, pf.path)] = prose_hash(pf.text)

    acked, live, used = [], [], set()
    for f in findings:
        pin = by_pin.get((f.rel, f.field))
        match = next((a for a in acks
                      if a.get("path") == f.rel and a.get("field") == f.field
                      and a.get("code") == f.code
                      and a.get("hash") == pin), None)
        if match is None:
            live.append(f)
        else:
            used.add(id(match))
            acked.append(f)

    for a in acks:
        if id(a) not in used:
            live.append(Finding(
                a.get("path", "?"), a.get("field", "?"), "J009",
                "acknowledgement for %s matches no finding — either the prose "
                "was fixed (delete this entry) or its content pin expired "
                "(re-inspect, do not re-hash)" % a.get("code", "?")))

    stats = {"artefacts": len(arts), "json_files": n_json,
             "prose_fields": n_fields, "silent_fields": n_silent,
             "nested_fields": n_nested, "checked_fields": n_checked,
             "claims": n_claims,
             "unparseable": unparseable, "streams": len(streams),
             "must_claims": n_must, "watched_claims": n_watched,
             "acknowledged": len(acked)}
    return live, acked, stats


def report(findings, acked, stats, show_acknowledged=False, out=sys.stdout):
    for f in sorted(findings, key=lambda x: (x.rel, x.code)):
        out.write("%s\n" % f)
        if f.quote:
            out.write("        > %s\n" % f.quote)
    if show_acknowledged:
        for f in sorted(acked, key=lambda x: (x.rel, x.code)):
            out.write("%s  [acknowledged]\n" % f)
    # Round 417 rule: `corpus_check.run_one` keeps `lines[-1]`, so any
    # line printed AFTER the summary is what the driver log quotes.
    # The skipped-file accounting goes above it, never below.
    out.write("  skipped: %d jsonl stream(s) (a `.json` holding one object "
              "per line is a log, not an artefact)%s\n"
              % (stats["streams"],
                 (", %d unparseable: %s" % (len(stats["unparseable"]),
                                            ", ".join(stats["unparseable"][:3])))
                 if stats["unparseable"] else ""))
    n_err = sum(1 for f in findings if f.severity == "ERROR")
    n_warn = sum(1 for f in findings if f.severity == "WARN")
    n_info = sum(1 for f in findings if f.severity == "INFO")
    # `checked_fields` counts fields where a lookup RAN. It is not
    # `prose_fields - silent_fields`, which counts fields that produced a
    # FINDING and was published as coverage until round 447.
    out.write("  fields: %d of %d nested below the artefact root; %d claim(s) "
              "checked in %d field(s), %d field(s) yielded a finding\n"
              % (stats["nested_fields"], stats["prose_fields"],
                 stats["claims"], stats["checked_fields"],
                 stats["prose_fields"] - stats["silent_fields"]))
    out.write(
        "selfdesc-check: %d artefact(s) of %d json file(s), %d prose field(s), "
        "%d error(s), %d warning(s), %d info, %d acknowledged; "
        "coverage %d/%d prose-fields, %d/%d must-claims\n"
        % (stats["artefacts"], stats["json_files"], stats["prose_fields"],
           n_err, n_warn, n_info, stats["acknowledged"],
           stats["checked_fields"], stats["prose_fields"],
           stats["watched_claims"], stats["must_claims"]))
    return n_err


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo-root", default=DEFAULT_REPO)
    ap.add_argument("--json", default=None)
    ap.add_argument("--show-acknowledged", action="store_true")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.repo_root)
    findings, acked, stats = sweep(root)
    n_err = report(findings, acked, stats, a.show_acknowledged)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"stats": stats,
                       "findings": [x.as_dict() for x in findings],
                       "acknowledged": [x.as_dict() for x in acked]},
                      f, indent=1)
    return ERRORS_FOUND if n_err else PASS


if __name__ == "__main__":
    sys.exit(main())

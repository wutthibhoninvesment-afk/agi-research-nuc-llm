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
English. It looks for five claim SHAPES that recur across the corpus and that
each reduce to a lookup:

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
              the artefact's own top-level collections, disagreeing with that
              collection's length.
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

#: Top-level string fields that are a self-description rather than data. `_`
#: and `_comment` are this repo's two idioms; the rest are what the corpus
#: actually contains, checked rather than guessed.
SELF_FIELDS = ("_", "_comment", "_note", "_why", "note", "comment")

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
       "J009": "ERROR", "J010": "ERROR", "J011": "WARN"}

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

class Artefact(object):
    """One JSON file plus the prose fields it carries about itself."""

    def __init__(self, rel, data):
        self.rel = rel
        self.data = data
        self.base = os.path.basename(rel)
        self.prose = [(k, data[k]) for k in SELF_FIELDS
                      if isinstance(data.get(k), str)
                      and len(data[k]) >= MIN_PROSE]
        self.collections = {k: v for k, v in data.items()
                            if isinstance(v, (list, dict)) and v}
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
        walk(self.data)
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
    """J001 / J002 / J003 — the "read by X" claim."""
    out = []
    if not READER_RE.search(text):
        return out
    mentions = [rel for rel, body in index.items()
                if rel != art.rel and art.base in body]
    if not mentions:
        out.append(Finding(art.rel, field, "J002",
                           "prose names a reader, but `%s` appears in no "
                           "source file in the tree — nothing reads it"
                           % art.base))
        return out
    for m in READER_RE.finditer(text):
        tail = text[m.end():m.end() + 200]
        mods = MODULE_TOKEN_RE.findall(tail)
        if not mods:
            continue
        mod = mods[0]
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
    return out


def check_paths(art, field, text, repo_root, tops, allowlist, already=()):
    """J004 — X004's rule, on the prose X004 never scanned.

    `already` holds tokens a more specific code has claimed. A missing path
    that is ALSO a declared reader is one defect, and J001 says more about it
    than J004 does, so it is reported once under the sharper code.
    """
    out = []
    for tok, _off, checkable in xref_check.prose_path_tokens(text, tops):
        if not checkable or tok in allowlist or tok in already:
            continue
        if xref_check.resolve_prose_path(repo_root, tok, tops) == "missing":
            out.append(Finding(art.rel, field, "J004",
                               "prose names `%s`, which does not exist" % tok,
                               tok))
    return out


def check_counts(art, field, text):
    """J005 / J007 — a numeral whose noun is one of this artefact's own
    collections."""
    out = []
    nouns = art.nouns()
    for sent, _off in sentences(text):
        dated = bool(AS_OF_RE.search(sent))
        for m in COUNT_RE.finditer(sent):
            raw, _adj, noun = m.group(1), m.group(2), m.group(3).lower()
            if noun not in nouns:
                continue
            said = int(raw) if raw.isdigit() else NUMBER_WORDS[raw.lower()]
            real = nouns[noun]
            if said == real:
                continue
            if OTHER_CONTAINER_RE.match(sent[m.end():m.end() + 24]):
                continue                    # counts a different container
            if PARTITIVE_RE.match(sent[m.end(1):m.end(1) + 20]):
                continue                    # counts a subset: "20 of the 23"
            if PAST_TENSE_RE.search(sent):
                continue                    # counts a historical subset
            code = "J007" if dated else "J005"
            out.append(Finding(
                art.rel, field, code,
                "prose says `%s %s` and the artefact has %d%s"
                % (raw, noun, real,
                   " (claim is dated; recorded, not an error)"
                   if dated else ""),
                sent.strip()[:110]))
    return out


def check_absence(art, field, text):
    """J006 / J007 — the prose denies an id the artefact contains."""
    out = []
    for sent, _off in sentences(text):
        if not ABSENCE_RE.search(sent):
            continue
        dated = bool(AS_OF_RE.search(sent))
        for tok in IDLIKE_RE.findall(sent):
            if tok in art.ids:
                continue
            hits = sorted(i for i in art.ids if i.startswith(tok))
            if not hits:
                continue
            code = "J007" if dated else "J006"
            out.append(Finding(
                art.rel, field, code,
                "prose denies `%s` and %s is in this artefact%s"
                % (tok, "/".join(hits), " (claim is dated)" if dated else ""),
                sent.strip()[:110]))
    return out


def check_regen(art, field, text, index):
    """J008 — an instruction to regenerate an artefact nothing generates."""
    if not REGEN_RE.search(text):
        return []
    producers = [rel for rel, body in index.items()
                 if rel != art.rel and rel.endswith((".py", ".sh"))
                 and art.base in body]
    if producers:
        return []
    return [Finding(art.rel, field, "J008",
                    "prose says the file is derived and must be regenerated, "
                    "and no .py/.sh in the tree names `%s`" % art.base)]


def check_delta(art, field, text, repo_root):
    """J010 — "<sibling.json> with N <element-field>s <verb>"."""
    out = []
    fields = art.element_fields()
    if not fields:
        return out
    mine = {el.get("id"): el for el in art.elements() if el.get("id")}
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
                if said == real:
                    continue
                out.append(Finding(
                    art.rel, field, "J010",
                    "prose says `%s %s` changed against %s and %d of %d "
                    "shared element(s) differ on `%s`"
                    % (raw, noun, os.path.basename(tok), real, len(shared),
                       key),
                    sent.strip()[:110]))
    return out


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

    findings, n_fields, n_silent, n_must, n_watched = [], 0, 0, 0, 0
    for art in arts:
        for field, text in art.prose:
            n_fields += 1
            got = []
            got += check_readers(art, field, text, index, repo_root)
            claimed = {f.quote for f in got if f.code == "J001"}
            got += check_paths(art, field, text, repo_root, tops, allowlist,
                               claimed)
            got += check_counts(art, field, text)
            got += check_absence(art, field, text)
            got += check_regen(art, field, text, index)
            got += check_delta(art, field, text, repo_root)
            claims = find_must_claims(text)
            n_must += len(claims)
            watched = watched_by_a_test(art.base, index) if claims else []
            n_watched += len(claims) if watched else 0
            for claim in claims:
                if watched:
                    continue
                got.append(Finding(
                    art.rel, field, "J011",
                    "an executable claim in a data file, and no test in the "
                    "tree names `%s`" % art.base, claim[:110]))
            if not got:
                n_silent += 1
            findings += got

    acks = load_acks(repo_root)
    by_pin = {}
    for art in arts:
        for field, text in art.prose:
            by_pin[(art.rel, field)] = prose_hash(text)

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
    checked = stats["prose_fields"] - stats["silent_fields"]
    out.write(
        "selfdesc-check: %d artefact(s) of %d json file(s), %d prose field(s), "
        "%d error(s), %d warning(s), %d info, %d acknowledged; "
        "coverage %d/%d prose-fields, %d/%d must-claims\n"
        % (stats["artefacts"], stats["json_files"], stats["prose_fields"],
           n_err, n_warn, n_info, stats["acknowledged"],
           checked, stats["prose_fields"], stats["watched_claims"],
           stats["must_claims"]))
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

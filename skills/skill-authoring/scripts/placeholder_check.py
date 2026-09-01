#!/usr/bin/env python3
"""placeholder_check.py — find template tokens the record never filled in.

Why this exists (round 429)
---------------------------
A round writes `MUTATION_RESULT_PLACEHOLDER` into its knowledge file meaning
"the campaign is still running, I will paste the number here", the session
ends, and the token becomes a permanent part of the record. It reads as a
measurement to every later grep and it is not one.

This has happened at least six times and was found by hand three separate
times, each time as a one-off:

    round 415  found round 205's `[TEST_RESULT_PLACEHOLDER]`, 222 rounds old
    round 427  filled round 426's `FULL_LIVE_PLACEHOLDER`
    round 428  found two MORE in round 426's own knowledge file, because
               round 427 had looked only at `state/`

Round 427 proposed this check and did not run it. Round 428 gave it a
discriminator and published an inventory of ONE — `state/research-state.md`
line 667 "and nothing else" — without running the scan that inventory names.
The scan finds **six**. Five of them are in `knowledge/`, which is exactly
the directory round 427's proposal had already been burned for omitting.

The discriminator
-----------------
A fixed-token grep is useless here: the token appears far more often in
PROSE ABOUT the problem than as an actual hole: at round 429 a fixed-token
`grep -rn` over the same two globs matched 41 lines, of which six are holes.
The separator, from round 428:

    a real unfilled placeholder is ALONE on its line.

"Alone" has to survive markdown decoration, which is why this is code and
not a grep. All six real instances are bare except round 205's, which is
`  [TEST_RESULT_PLACEHOLDER].` — indented, bracketed, and full-stopped. Every
non-bare occurrence has other words on the line, and the summary prints how
many there were so the discriminator's own work stays visible.

Acknowledgement
---------------
Some holes cannot be filled: the run that would have produced the number
happened in a session that ended 400 rounds ago. Those are acknowledged in
`state/known-unfilled-placeholders.json`, CONTENT-PINNED per
`skills/content-pinned-acknowledgement` — the entry stores a hash of the
lines around the hole, so the acknowledgement expires by itself the moment
somebody edits that passage, rather than muting the location forever.

Codes: U001 unacknowledged hole (ERROR) · U002 acknowledged, still open
(WARN) · U003 acknowledgement no longer matches anything (WARN).

Usage:
    python3 placeholder_check.py [--repo-root DIR] [--list]

Exit codes: 0 = no unacknowledged holes, 1 = at least one, 2 = usage/IO.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
REGISTRY = os.path.join("state", "known-unfilled-placeholders.json")

# The scanned corpus. `knowledge/` is FIRST and is not optional: round 427's
# proposal scanned `state/` only and missed five of the six real instances.
SCAN_GLOBS = ("knowledge/*.md", "state/*.md")

TOKEN_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_PLACEHOLDER")

# Markdown decoration a bare token is still bare underneath. Deliberately
# does NOT strip `<...>`: `<PLACEHOLDER>` in a template snippet is a
# different animal and nobody has been bitten by one.
_DECORATION = " \t-*_`[]()<>.,;:!?\"'"

CONTEXT = 3          # lines either side that the acknowledgement hash covers


def is_bare(line):
    """True when `line` is a placeholder token and nothing else."""
    stripped = line.strip().strip(_DECORATION)
    m = TOKEN_RE.fullmatch(stripped)
    return m.group(0) if m else None


def context_hash(lines, i):
    """Hash the passage around line `i` (0-based), whitespace-normalised."""
    lo, hi = max(0, i - CONTEXT), min(len(lines), i + CONTEXT + 1)
    blob = "\n".join(l.rstrip() for l in lines[lo:hi])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class Hole:
    def __init__(self, path, line_no, token, digest):
        self.path = path
        self.line_no = line_no
        self.token = token
        self.digest = digest

    def key(self):
        return (self.path, self.digest)

    def __str__(self):
        return "%s:%d: %s (%s)" % (self.path, self.line_no, self.token,
                                   self.digest)


def scan_text(text, path):
    """Every bare placeholder in `text`, as Hole objects."""
    lines = text.split("\n")
    holes = []
    for i, line in enumerate(lines):
        token = is_bare(line)
        if token:
            holes.append(Hole(path, i + 1, token, context_hash(lines, i)))
    return holes


def mentions(text):
    """Occurrences of the token that are NOT bare — the false-positive set a
    plain grep would report. Reported as a denominator, never as a finding."""
    n = 0
    for line in text.split("\n"):
        if TOKEN_RE.search(line) and not is_bare(line):
            n += len(TOKEN_RE.findall(line))
    return n


def scan_repo(root, globs=SCAN_GLOBS):
    holes, n_files, n_mentions = [], 0, 0
    for pattern in globs:
        for path in sorted(glob.glob(os.path.join(root, pattern))):
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            n_files += 1
            rel = os.path.relpath(path, root)
            holes.extend(scan_text(text, rel))
            n_mentions += mentions(text)
    return holes, n_files, n_mentions


def load_registry(root):
    path = os.path.join(root, REGISTRY)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("acknowledged", [])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT)
    ap.add_argument("--list", action="store_true",
                    help="print every hole, acknowledged or not")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.repo_root)

    try:
        holes, n_files, n_mentions = scan_repo(root)
        acked = load_registry(root)
    except (OSError, ValueError) as e:
        print("placeholder_check: cannot run: %s" % e, file=sys.stderr)
        return 2

    by_key = {(a["path"], a["hash"]): a for a in acked}
    seen, errors, warnings = set(), [], []
    for h in holes:
        entry = by_key.get(h.key())
        if entry is None:
            errors.append("%s: ERROR U001 unfilled placeholder %s — a hole in "
                          "the permanent record that reads as a measurement. "
                          "Fill it, or acknowledge it in %s with a reason."
                          % (h, h.token, REGISTRY))
        else:
            seen.add(h.key())
            warnings.append("%s: WARN U002 acknowledged unfilled placeholder "
                            "— %s" % (h, entry.get("reason", "no reason given")))
    for key, entry in sorted(by_key.items()):
        if key not in seen:
            warnings.append("%s: WARN U003 acknowledgement for %s no longer "
                            "matches any passage (hash %s) — the text changed; "
                            "drop the entry or re-pin it"
                            % (REGISTRY, entry["path"], entry["hash"]))

    for line in errors + warnings:
        print(line)
    if args.list:
        for h in holes:
            print("  %s %s" % ("ACK " if h.key() in seen else "OPEN", h))
    print("placeholder-check: %d file(s), %d unfilled (%d acknowledged), "
          "%d non-bare mention(s) a plain grep would have reported, "
          "%d error(s), %d warning(s)"
          % (n_files, len(holes), len(seen), n_mentions,
             len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Round 399 archaeology: how did round 398's item 10 come back?

Reuses state_claim_check.py's own block/item/claim model so the numbers
here and the checker's numbers cannot drift.
"""
import os, re, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "skills", "skill-authoring", "scripts"))
import state_claim_check as scc

DOC = os.path.join(REPO, "state", "research-state.md")
text = open(DOC, encoding="utf-8").read()
blocks = scc.find_blocks(text)
live, err = scc.live_block(blocks)

print("== 1. blocks ==")
print("n_blocks=%d  live=round %d at line %d" % (len(blocks), live.round_no, live.first_line))
print("file-order round numbers:", [b.round_no for b in blocks])
inversions = sum(1 for a, b in zip(blocks, blocks[1:]) if b.round_no < a.round_no)
print("adjacent inversions (later-in-file has LOWER round): %d of %d pairs"
      % (inversions, len(blocks) - 1))
print("physically LAST block: round %d (line %d)" % (blocks[-1].round_no, blocks[-1].first_line))
print("highest round among the last 5 blocks in file order:",
      max(b.round_no for b in blocks[-5:]))

print()
print("== 2. the B002 claim's carry chain ==")
KEY = "`fuzz-mutate-kill-loop/skill.md` is still 415 body lines (b002)"
chain = []
for b in blocks:
    hay = scc.normalise(" ".join(b.lines))
    if KEY in hay:
        chain.append(b)
rounds = [b.round_no for b in chain]
print("asserted by rounds:", rounds)
gaps = [(a, b) for a, b in zip(rounds, rounds[1:])]
print("gaps:", [(a, b, b - a) for a, b in gaps])
print("largest gap:", max((b - a, a, b) for a, b in gaps))

print()
print("== 3. the ordinal counter attached to it, per block ==")
ORD = re.compile(r"(\d+)(?:st|nd|rd|th)\s+consecutive|"
                 r"\b(sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|"
                 r"fourteenth|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|TWELFTH)\s+consecutive",
                 re.I)
WORDS = {"sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
         "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14}
for b in chain:
    for item in scc.parse_items(b):
        if KEY in scc.normalise(item.text):
            m = ORD.search(item.text)
            val = None
            if m:
                val = int(m.group(1)) if m.group(1) else WORDS[m.group(2).lower()]
            print("  round %-4d item %-3d ordinal=%-5s  %s"
                  % (b.round_no, item.number, val,
                     re.sub(r"\s+", " ", item.text)[:130]))

print()
print("== 4. round 398's items: age of each claim ==")
ages = scc.claim_ages(live, blocks)
for item in scc.parse_items(live):
    for claim in scc.extract_claims(item):
        rs = sorted(ages.get(claim.key(), ()))
        if len(rs) > 1:
            prev = [r for r in rs if r < live.round_no]
            gap = live.round_no - max(prev) if prev else None
            print("  item %-3d gap=%-5s chain=%s  %s"
                  % (item.number, gap, rs, re.sub(r"\s+", " ", claim.span_text)[:70]))

print()
print("== 5. corpus-wide: every ordinal-continuity counter, by subject ==")
# Group ordinal phrases by the normalised item text with the ordinal blanked.
by_subject = {}
for b in blocks:
    for item in scc.parse_items(b):
        for m in ORD.finditer(item.text):
            val = int(m.group(1)) if m.group(1) else WORDS[m.group(2).lower()]
            blanked = ORD.sub("<N> consecutive", item.text)
            # subject = the backticked paths + the first 6 significant words
            paths = tuple(sorted(set(re.findall(r"`([^`]+\.(?:md|py|sh|json|lang))`", blanked))))
            if not paths:
                continue
            by_subject.setdefault(paths, []).append((b.round_no, val, item.number))
for paths, rows in sorted(by_subject.items(), key=lambda kv: -len(kv[1])):
    rows.sort()
    seq = [(r, v) for r, v, _ in rows]
    # non-advance: same ordinal asserted by two different blocks, or a decrease
    bad = [(a, b) for a, b in zip(seq, seq[1:]) if b[1] is not None and a[1] is not None and b[1] <= a[1]]
    if len(rows) < 2:
        continue
    print("  %-60s n=%2d seq=%s" % (",".join(paths)[:60], len(rows), seq))
    if bad:
        print("      NON-ADVANCING: %s" % bad)

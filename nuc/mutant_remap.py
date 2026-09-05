"""Round 514 (NUC-integration E): carrying a mutant's verdict across a source edit.

`harness/swe/nodecampaign.py`'s `load_ledger` keys on `(id, subject_digest)`
and its docstring already states the reason:

    a mutant id is `basename:line:op#i` and `i` is POSITIONAL
    (see `mutation.py`'s frozen-id docstring), so the same id on a moved
    source is a different mutant and must not be skipped.

That is the right rule and it has a cost nobody had paid. When round 508 added
243 lines to `nuc/perturbation.py`, all 134 scored rows -- 52 of them
`survived` -- became rows about a file that no longer exists, and there was no
way to say WHICH mutant at the new digest is the same mutation as an old one.
`state/nuc/round-502/survivor-impact.json` went stale the same day and
`test_the_committed_report_is_about_the_subject_at_head` has been red since.

This module is the missing step. It re-identifies a mutant by what it DOES
rather than by where it sat:

    key = (op, description, the stripped text of the mutated line,
           the qualname of the innermost enclosing def/class)

plus an ORDINAL among mutants sharing that key, so two identical mutations of
two identical lines in the same function stay distinguishable.

The ordinal is the honest part. If the number of mutants sharing a key differs
between the two revisions, the ordinal is not a correspondence and the pair is
reported `ambiguous` rather than matched. A remap that guessed there would be
worse than no remap: it would carry a `survived` verdict onto a mutation
nobody scored, which is the precise direction that manufactures good news.

NO NETWORK, NO SSH, NO ENGINE. Pure AST and text, on committed sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nuc.survivor_impact import enclosing_defs, owner_of  # noqa: E402


class RemapError(RuntimeError):
    pass


def _mutants(source: str, rel: str):
    from harness.swe import mutation as MU
    return MU.generate(source, os.path.basename(rel))


def content_key(m, lines: list, defs: list) -> tuple:
    """What the mutation IS, with no line number in it.

    `m.lineno` is 1-based. A mutant whose line is past the end of the source
    cannot happen (mutation.generate reads the same text), but an empty string
    is used rather than raising so a malformed input degrades to a key that
    simply will not match anything.
    """
    text = lines[m.lineno - 1].strip() if 0 < m.lineno <= len(lines) else ""
    return (m.op, m.description, text, owner_of(defs, m.lineno))


def keyed(source: str, rel: str) -> dict:
    """`{content_key: [mutant, ...]}` in generation order, and `{id: mutant}`."""
    lines = source.splitlines()
    defs = enclosing_defs(source)
    by_key: dict = {}
    by_id: dict = {}
    for m in _mutants(source, rel):
        by_key.setdefault(content_key(m, lines, defs), []).append(m)
        by_id[m.id] = m
    return by_key, by_id


def remap(old_source: str, new_source: str, rel: str,
          ids: list | None = None) -> dict:
    """Map old mutant ids onto new ones by content.

    `ids=None` maps every mutant in the old revision. Returns a report dict;
    `pairs` is one row per requested id with `status` in
    `matched` / `moved` / `ambiguous` / `gone`.
    """
    old_by_key, old_by_id = keyed(old_source, rel)
    new_by_key, _new_by_id = keyed(new_source, rel)
    want = list(old_by_id) if ids is None else list(ids)

    # ordinal of each old mutant within its own key bucket
    ordinal = {}
    for key, ms in old_by_key.items():
        for i, m in enumerate(ms):
            ordinal[m.id] = (key, i)

    pairs = []
    for mid in want:
        m = old_by_id.get(mid)
        if m is None:
            pairs.append({"old_id": mid, "status": "not_in_old_revision",
                          "new_id": None})
            continue
        key, i = ordinal[mid]
        cands = new_by_key.get(key, [])
        row = {"old_id": mid, "old_line": m.lineno, "op": m.op,
               "description": m.description, "owner": key[3],
               "line_text": key[2][:160], "ordinal": i,
               "n_old_with_key": len(old_by_key[key]),
               "n_new_with_key": len(cands)}
        if not cands:
            row.update(status="gone", new_id=None, new_line=None)
        elif len(cands) != len(old_by_key[key]):
            # The bucket changed size: position within it is no longer a
            # correspondence. Refuse rather than guess.
            row.update(status="ambiguous", new_id=None, new_line=None)
        else:
            n = cands[i]
            row.update(status="moved" if n.id != mid else "matched",
                       new_id=n.id, new_line=n.lineno)
        pairs.append(row)

    by_status: dict = {}
    for r in pairs:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {
        "subject": rel,
        "old_digest": hashlib.sha256(old_source.encode()).hexdigest(),
        "new_digest": hashlib.sha256(new_source.encode()).hexdigest(),
        "n_requested": len(want),
        "n_old_mutants": len(old_by_id),
        "n_new_mutants": sum(len(v) for v in new_by_key.values()),
        "by_status": dict(sorted(by_status.items())),
        "n_id_changed": sum(1 for r in pairs if r["status"] == "moved"),
        "new_ids": sorted(r["new_id"] for r in pairs if r.get("new_id")),
        "pairs": pairs,
    }


def git_show(root: str, rev: str, rel: str) -> str:
    p = subprocess.run(["git", "show", "%s:%s" % (rev, rel)], cwd=root,
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RemapError("git show %s:%s failed: %s"
                         % (rev, rel, p.stderr.strip()[:200]))
    return p.stdout


def survivor_ids(root: str, ledger: str, digest: str | None) -> list:
    from nuc.survivor_impact import survivors
    return [r["id"] for r in survivors(os.path.join(root, ledger),
                                       subject_digest=digest)]


def build_parser():
    p = argparse.ArgumentParser(
        prog="mutant_remap.py",
        description="Re-identify mutants by content across a source edit.")
    p.add_argument("--root", default=ROOT)
    p.add_argument("--rel", default=os.path.join("nuc", "perturbation.py"))
    p.add_argument("--old-rev", default=None,
                   help="git revision holding the OLD source (default: the "
                        "commit that last changed --rel, ^)")
    p.add_argument("--old-file", default=None,
                   help="read the old source from a file instead of git")
    p.add_argument("--ledger", default=os.path.join(
        "state", "swe", "perturbation-mutation-ledger.jsonl"))
    p.add_argument("--survivors", action="store_true",
                   help="map exactly the standing survivors of the OLD digest")
    p.add_argument("--only", default=None, help="comma-separated old ids")
    p.add_argument("--out", default=None)
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    root = os.path.abspath(a.root)
    with open(os.path.join(root, a.rel), encoding="utf-8") as fh:
        new_source = fh.read()
    if a.old_file:
        with open(a.old_file, encoding="utf-8") as fh:
            old_source = fh.read()
    else:
        rev = a.old_rev
        if rev is None:
            p = subprocess.run(["git", "log", "-1", "--format=%H", "--", a.rel],
                               cwd=root, capture_output=True, text=True)
            rev = p.stdout.strip() + "^"
        old_source = git_show(root, rev, a.rel)

    ids = None
    if a.only:
        ids = [s.strip() for s in a.only.split(",")]
    elif a.survivors:
        old_digest = hashlib.sha256(old_source.encode()).hexdigest()
        ids = survivor_ids(root, a.ledger, old_digest)
        if not ids:
            raise RemapError("no standing survivors at old digest %s"
                             % old_digest[:12])

    rep = remap(old_source, new_source, a.rel, ids=ids)
    text = json.dumps(rep, indent=1, sort_keys=True)
    if a.out:
        d = os.path.dirname(os.path.join(root, a.out))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(root, a.out), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if not a.quiet:
        print(text)
    return 0


if __name__ == "__main__":                     # pragma: no cover
    raise SystemExit(main())

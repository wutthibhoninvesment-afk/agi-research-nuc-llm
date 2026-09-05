#!/usr/bin/env python3
"""Commit-time GUARD and forensic RESOLVER for the escalated-diff registry.

Round 475 (harness A).

WHY THIS EXISTS
---------------
`state/known-escalated-diffs.json` (round 373) pins each adjudicated,
deliberately-uncommitted tracked-file diff by BOTH blob hashes.
`check_round_recorded.classify_escalated_diffs` reads that pin and, when the
path stops being dirty, prints:

    N escalation registry entr(ies) ... match nothing in the working tree
    -- the diff was committed, reverted, or the file deleted. A dead
    acknowledgement suppresses nothing and reads as coverage: delete the
    entry

Two things are wrong with stopping there, and this module fixes both.

1. THE DISJUNCTION IS NEVER RESOLVED. "Committed, reverted, or deleted" are
   not three shades of one event. *Reverted* means the escalation was
   settled the way it was adjudicated. *Deleted* means the artifact is gone.
   *Committed* means a round landed content a previous round decided must
   NOT be landed -- a violation of a standing decision, by the very
   automation the registry was built to police. The three are told apart by
   arithmetic the checker already has the inputs for: compare the pinned
   worktree blob against the blob each commit in the path's history carries.
   `resolve_fate` does that.

   It is not hypothetical. In this repo the RESOLVED branch has fired live
   exactly twice -- round 393 and round 475 -- and BOTH times the fate was
   COMMITTED, by a round whose `git add -A` swept the path in and whose
   commit message does not mention the file. Round 393 noticed and restored
   it in a follow-up commit. Round 474 did not, and the escalated content
   sat at HEAD for a full round. The empirical prior on that disjunction is
   100% "committed", 0% "reverted", 0% "deleted".

2. THE PRESCRIBED REMEDY DESTROYS THE EVIDENCE. "Delete the entry" is the
   right instruction for a *reverted* or *deleted* fate and exactly the
   wrong one for a *committed* fate: it removes the only machine-readable
   record that the path was ever adjudicated, and the next `git add -A`
   has nothing left to trip over. `audit` therefore prints the fate and the
   repair, and refuses to recommend deletion for a COMMITTED entry.

3. NOTHING RAN AT COMMIT TIME. The pin is a DETECTOR, checked once before a
   round starts. Between that check and the next one a round can stage and
   commit anything. `check` is the missing consumer: it fails if the index
   contains a registry path, and `install-hook` wires it into a real
   `pre-commit` hook so it runs whether or not the round remembers to.

FAIL-OPEN vs FAIL-CLOSED, stated because they differ per subcommand.
`check` (the hook) FAILS OPEN on infrastructure trouble -- no git, no
registry, unreadable JSON -> rc 0. A guard that blocks every commit in the
repo the first time a JSON file is malformed costs more than the rare event
it prevents, and the detector still runs before every round. `audit` FAILS
CLOSED: an entry whose fate cannot be computed is reported UNKNOWN and sets
rc 1, because "I could not tell whether a standing decision was violated"
must not read as "it wasn't".

USAGE
-----
    python3 harness/escalationguard.py check            # pre-commit guard
    python3 harness/escalationguard.py audit            # resolve every fate
    python3 harness/escalationguard.py install-hook     # wire it in
    python3 harness/escalationguard.py hook-status

Exit codes: 0 clean; 1 a guard blocked or an audit found a violation;
2 usage/IO problem.
"""

import argparse
import json
import os
import stat
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_REL = os.path.join("state", "known-escalated-diffs.json")

#: `resolve_fate` verdicts.
FATE_DIRTY = "dirty"          #: still uncommitted -- the escalation is live
FATE_COMMITTED = "committed"  #: the escalated content is AT HEAD: violation
FATE_REVERTED = "reverted"    #: HEAD is the base and the tree matches it
FATE_DELETED = "deleted"      #: path is gone from HEAD (and from disk)
FATE_UNKNOWN = "unknown"      #: could not be computed -- fail closed

#: Marker line written into the hook so `hook-status` can recognise its own
#: work and never clobber a hook someone else wrote.
HOOK_MARKER = "# managed-by: harness/escalationguard.py"


def _git(args, repo=REPO_ROOT, timeout=20, strip=True):
    """Run `git -C repo <args>`; return (returncode, stdout). Any
    OSError/timeout degrades to (None, "") so every caller can apply its own
    fail-open/fail-closed policy explicitly.

    `strip=False` matters for `status --porcelain`, whose first two columns
    are the status code and whose first line therefore BEGINS with a space
    for an unstaged modification. Stripping it shifts every offset by one
    and silently turns `doc.md` into `oc.md` -- which is exactly how this
    function's first version reported a live escalation as UNKNOWN."""
    try:
        out = subprocess.run(["git", "-C", repo] + list(args),
                             capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return out.returncode, (out.stdout.strip() if strip else out.stdout)


def load_registry(path=None, repo=REPO_ROOT):
    """Return {repo-relative path: entry} from the escalated-diff registry.

    Delegates to `check_round_recorded.load_escalated_diffs` when it can be
    imported -- one parser, one shape -- and falls back to reading the same
    JSON directly when the skills tree is absent (a bare worktree, a
    packaged copy). Both paths degrade to {} on a missing/broken file."""
    path = path or os.path.join(repo, REGISTRY_REL)
    scripts = os.path.join(REPO_ROOT, "skills", "session-inheritance-audit",
                           "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import check_round_recorded as crr
    except ImportError:
        crr = None
    if crr is not None:
        return crr.load_escalated_diffs(path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    entries = data.get("escalations", {})
    if not isinstance(entries, dict):
        return {}
    return {k: v for k, v in entries.items()
            if not k.startswith("_") and isinstance(v, dict)}


def staged_paths(repo=REPO_ROOT):
    """Repo-relative paths currently in the INDEX and different from HEAD.

    `--diff-filter=ACMR` covers add/copy/modify/rename; a staged DELETION of
    an escalated path is caught separately by `staged_escalations`, because
    deleting the file is as much a landing of a decision as committing it.
    Returns [] when git is unavailable -- see the module docstring."""
    rc, out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMRD"],
                   repo=repo)
    if rc != 0 or not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def staged_blob(path, repo=REPO_ROOT):
    """SHA-1 of `path`'s blob IN THE INDEX, or None if it is staged for
    deletion / not in the index."""
    rc, out = _git(["ls-files", "--stage", "--", path], repo=repo)
    if rc != 0 or not out:
        return None
    parts = out.split()
    return parts[1] if len(parts) > 2 else None


def staged_escalations(repo=REPO_ROOT, registry=None, registry_path=None):
    """Sorted repo-relative paths this commit would land that the registry
    says MUST NOT be landed. Empty is the good answer.

    THE RESTORE EXEMPTION. A bare index-vs-registry intersection would also
    block the repair -- committing the path back to its adjudicated BASE is
    the one change to an escalated file that is always correct, and it is
    exactly what round 393's follow-up commit did and what round 475 had to
    do again. So a staged blob equal to the entry's pinned `head_blob` is
    ALLOWED. Everything else about an escalated path is refused, including:

      - the pinned escalated content (the violation this exists for),
      - a staged DELETION (deleting the artifact settles the adjudication
        as surely as committing it),
      - any THIRD content (an unreviewed edit to a file under adjudication),
      - a path whose entry carries no `head_blob` (no base to restore to, so
        no exemption can be justified).

    The exemption is a claim about BYTES, not about intent, so it cannot be
    talked into allowing anything else."""
    if registry is None:
        registry = load_registry(registry_path, repo=repo)
    if not registry:
        return []
    out = []
    for path in sorted(set(staged_paths(repo)) & set(registry)):
        base = (registry.get(path) or {}).get("head_blob")
        if base and staged_blob(path, repo=repo) == base:
            continue  # restoring the adjudicated base
        out.append(path)
    return out


def blob_at(rev, path, repo=REPO_ROOT):
    """SHA-1 of `path`'s blob at `rev`, or None if it is not there."""
    rc, out = _git(["rev-parse", "--verify", "-q", "%s:%s" % (rev, path)],
                   repo=repo)
    if rc != 0:
        return None
    return out or None


def worktree_blob(path, repo=REPO_ROOT):
    """SHA-1 git would give the bytes on disk, or None if absent."""
    full = os.path.join(repo, path)
    if not os.path.exists(full):
        return None
    rc, out = _git(["hash-object", "--", path], repo=repo)
    if rc != 0:
        return None
    return out or None


def path_history(path, repo=REPO_ROOT, limit=200):
    """[{sha, short, subject, blob}] for every commit that TOUCHED `path`,
    newest first, each carrying the blob that commit recorded for it.

    A deletion commit yields blob None, which is what makes DELETED
    distinguishable from a content change."""
    rc, out = _git(["log", "--format=%H\x1f%h\x1f%s", "-n", str(limit),
                    "--", path], repo=repo)
    if rc != 0 or not out:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, short, subject = parts
        rows.append({"sha": sha, "short": short, "subject": subject,
                     "blob": blob_at(sha, path, repo=repo)})
    return rows


def resolve_fate(path, entry, repo=REPO_ROOT, dirty_paths=None):
    """Resolve the checker's three-way disjunction for ONE registry entry.

    `entry` is a registry value (needs `worktree_blob` and `head_blob`).
    `dirty_paths` is an optional set of repo-relative paths git reports as
    modified; when omitted it is computed with `git status --porcelain`.

    Returns a dict:
        fate            one of the FATE_* constants
        detail          one sentence naming what happened
        head_blob       the blob at HEAD now (or None)
        disk_blob       the blob of the bytes on disk now (or None)
        landed_in       [{sha, short, subject}] commits whose recorded blob
                        for `path` IS the pinned escalated content -- i.e.
                        every commit that landed the thing nobody was
                        supposed to land. Empty unless fate is COMMITTED
                        (or the content was committed and later reverted,
                        which this reports too).
        restore_to      the blob a repair should restore HEAD to, or None
        recommend       'keep' / 'delete' / 'repair' -- what to do with the
                        registry entry itself

    FAIL CLOSED: if git cannot answer, fate is UNKNOWN, not REVERTED."""
    rec_wt = entry.get("worktree_blob")
    rec_head = entry.get("head_blob")
    row = {"path": path, "fate": FATE_UNKNOWN, "detail": "",
           "head_blob": None, "disk_blob": None, "landed_in": [],
           "restore_to": rec_head, "recommend": "keep",
           "recorded_worktree_blob": rec_wt, "recorded_head_blob": rec_head}

    if not rec_wt or not rec_head:
        row["detail"] = ("registry entry records no fingerprint, so no fate "
                         "can be computed -- an unpinned acknowledgement "
                         "cannot be audited")
        return row

    rc, _ = _git(["rev-parse", "--verify", "-q", "HEAD"], repo=repo)
    if rc != 0:
        row["detail"] = "no HEAD (git unavailable or empty repo) -- fail closed"
        return row

    head = blob_at("HEAD", path, repo=repo)
    disk = worktree_blob(path, repo=repo)
    row["head_blob"] = head
    row["disk_blob"] = disk

    if dirty_paths is None:
        rc, out = _git(["status", "--porcelain", "--", path], repo=repo,
                       strip=False)
        dirty = rc == 0 and bool(out.strip())
    else:
        dirty = path in dirty_paths

    # Every commit that ever recorded the ESCALATED bytes for this path.
    landed = [{"sha": c["sha"], "short": c["short"], "subject": c["subject"]}
              for c in path_history(path, repo=repo) if c["blob"] == rec_wt]
    row["landed_in"] = landed

    if head == rec_wt:
        # The bytes nobody was supposed to commit are what HEAD has.
        row["fate"] = FATE_COMMITTED
        who = landed[-1] if landed else None
        row["detail"] = (
            "the ESCALATED content is at HEAD: blob %s is the pinned "
            "worktree blob, not the pinned base %s. A round committed a diff "
            "a previous round adjudicated as must-not-land%s."
            % (rec_wt[:12], rec_head[:12],
               ", first in %s (%s)" % (who["short"], who["subject"][:60])
               if who else ""))
        row["recommend"] = "repair"
        row["restore_to"] = rec_head
        return row

    if dirty and disk == rec_wt and head == rec_head:
        row["fate"] = FATE_DIRTY
        row["detail"] = "escalation is live and unchanged -- nothing to do"
        row["recommend"] = "keep"
        return row

    if head is None and disk is None:
        row["fate"] = FATE_DELETED
        row["detail"] = ("path is in neither HEAD nor the working tree -- "
                         "the file was deleted; the acknowledgement now "
                         "describes nothing")
        row["recommend"] = "delete"
        return row

    if head == rec_head and disk == rec_head:
        row["fate"] = FATE_REVERTED
        row["detail"] = (
            "HEAD and the working tree are both the pinned base %s -- the "
            "third party's edit is gone and the escalation is settled the "
            "way it was adjudicated%s"
            % (rec_head[:12],
               " (it HAD been committed, in %s -- reverted since)"
               % ", ".join(c["short"] for c in landed) if landed else ""))
        row["recommend"] = "delete"
        return row

    row["detail"] = (
        "neither pinned blob explains the current state (HEAD %s, disk %s, "
        "pinned base %s, pinned escalated %s) -- re-inspect by hand"
        % (str(head)[:12], str(disk)[:12], rec_head[:12], rec_wt[:12]))
    return row


def audit(repo=REPO_ROOT, registry_path=None):
    """`resolve_fate` for every registry entry, in registry order."""
    registry = load_registry(registry_path, repo=repo)
    dirty = None
    rc, out = _git(["status", "--porcelain", "-z"], repo=repo, strip=False)
    if rc == 0:
        dirty = set()
        for record in out.split("\0"):
            if len(record) > 3:
                dirty.add(record[3:])
    return [resolve_fate(p, e, repo=repo, dirty_paths=dirty)
            for p, e in registry.items()]


def hook_script(python=None, script_rel=None):
    """Text of the `pre-commit` hook. Deliberately tiny: it locates the
    repo, runs `check`, and forwards the exit code. All policy lives in
    Python where it is tested."""
    python = python or "python3"
    script_rel = script_rel or os.path.join("harness", "escalationguard.py")
    wiring_rel = os.path.join("harness", "wiring_audit.py")
    carry_rel = os.path.join("skills", "skill-authoring", "scripts",
                             "carryforward_check.py")
    copyp_rel = os.path.join("harness", "swe", "copyparity.py")
    return """#!/bin/sh
%s
# Refuses a commit that would land a path listed in
# state/known-escalated-diffs.json -- a tracked-file diff a previous round
# already adjudicated as MUST NOT LAND. Written by round 475 (harness A)
# after `git add -A` landed one twice, 81 rounds apart (rounds 393, 474).
#
# Fails OPEN on infrastructure trouble (no python, no registry): the guard
# is a backstop, not a gate on the repo's usability.
top=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -f "$top/%s" ] || exit 0
%s "$top/%s" check || exit 1

# Round 499 (harness A): the SECOND commit-time guard, and the only reason
# there is one hook file rather than two is that git allows exactly one
# `pre-commit`. This step is ADVISORY -- it always exits 0.
#
# It warns when the commit stages a *.sh, or a *.py with a __main__ guard,
# that has no entry in harness/wiring-registry.json. That is a W001 error in
# the fast tier, and it has been opened seven times by seven different
# rounds (r471, r472, r478, r483, r484, r490, r498) without the round that
# opened it ever seeing it: the health checks run after the agent process
# exits and write to logs/, which is not in git. This is the only place the
# AUTHOR is still present.
#
# `undeclared --staged` and never `check`: the full audit resolves the whole
# invocation closure and costs ~18 s, which is not a thing to put in front
# of every commit. Restricted to the staged set it costs ~0.1 s.
#
# WARNS, NEVER BLOCKS, and that is deliberate rather than timid. A gate here
# can refuse the commit of a round that has no turns left to debug it, and
# losing a round's whole uncommitted diff is a strictly worse outcome than
# one more round of a red registry line -- this program has already lost 32
# sessions to the turn cap. Fails open on any infrastructure trouble too.
if [ -f "$top/%s" ]; then
  %s "$top/%s" undeclared --staged --quiet 2>/dev/null || true
fi

# Round 501 (skills B): the THIRD advisory step, same design and the same
# reason. K001 -- a prediction bank on disk with no entry in
# state/prediction-bank-ledger.json -- has gone red and been closed six
# times, and every closure was a skills(B) round writing entries for banks
# other rounds left. Banks arrive at ~1 per round; entries were written at
# ~1 per rotation, and the rotation is six.
#
# It is not that the rule is unknown: rounds 493, 494, 496 and 497 each
# registered their own bank inside their own commit and said so in the
# entry. Rounds 498, 499 and 500 did not, and one miss keeps the check red
# for the rest of the rotation. A ~50%% compliance rate on a written rule
# does not move because the rule is written again.
#
# Triggers on the KNOWLEDGE FILE, never on the bank: a bank is committed
# early, before measuring, and at that moment the entry cannot exist yet.
# Reads the ledger JSON and the staged list only -- no corpus, ~0.1 s.
# WARNS, NEVER BLOCKS, and fails open, for round 499's reason above.
if [ -f "$top/%s" ]; then
  %s "$top/%s" --staged-check --quiet 2>/dev/null || true
fi

# Round 515 (SWE-loop D): the FOURTH advisory step, and the one with the
# longest paper trail. `harness/swe/copyparity.py escapes` finds a path
# expression in languages/whence that reaches ABOVE the subtree, which
# breaks the moment `swe/proc.py` copies the tree into a sandbox. Three
# nodes in harness/tests/test_swe_copyparity_real_subject.py assert its
# verdict on the real tree, and they have been reddened FOUR times by four
# rounds writing the same expression into a NEW file after round 413
# sanctioned the guard -- 464 specreg, 504 builtinlive, 507 specstale, 512
# corpusledger -- each closed by a SWE-loop(D) round (467, 505, 509, 515).
#
# Not one of those authors could have seen it. The assertion is in
# harness/tests/; languages/whence/run_tests_fast.sh -- the suite a
# language(C) round runs -- covers languages/whence/tests/ only. Round 506
# wrote a comment naming the defect, the file and the exact three nodes;
# rounds 507 and 512 wrote it anyway. Round 512 went further: it ran
# harness/readset.py blast, measured its precision at 20%%, and wrote the
# unguarded expression in the same commit. `blast` names 18 suites for that
# file; this names the file and the line.
#
# `--staged` scans only this commit's staged *.py under the subtree and
# subtracts what is already at HEAD, so it attributes only what the author
# wrote: over all 137 commits that ever touched a *.py there, the whole-file
# scan fires on 25 and 8 of those carry no new escape, while the HEAD-
# differenced version fires on 17 and keeps all 3 real episodes
# (state/swe/round-515/escapes-staged-new-vs-inherited.json). ~0.2 s, and
# silent when there is nothing to say. WARNS, NEVER BLOCKS, fails open --
# round 499's reason above applies unchanged.
if [ -f "$top/%s" ]; then
  %s "$top/%s" escapes --staged 2>/dev/null || true
fi
exit 0
""" % (HOOK_MARKER, script_rel, python, script_rel,
       wiring_rel, python, wiring_rel,
       carry_rel, python, carry_rel,
       copyp_rel, python, copyp_rel)


def hooks_dir(repo=REPO_ROOT):
    """Absolute hooks directory, honouring `core.hooksPath`."""
    rc, out = _git(["config", "--get", "core.hooksPath"], repo=repo)
    if rc == 0 and out:
        return out if os.path.isabs(out) else os.path.join(repo, out)
    rc, out = _git(["rev-parse", "--git-path", "hooks"], repo=repo)
    if rc == 0 and out:
        return out if os.path.isabs(out) else os.path.join(repo, out)
    return os.path.join(repo, ".git", "hooks")


def hook_status(repo=REPO_ROOT):
    """(state, path) where state is 'ours' / 'foreign' / 'absent'."""
    path = os.path.join(hooks_dir(repo), "pre-commit")
    if not os.path.exists(path):
        return "absent", path
    try:
        with open(path) as fh:
            body = fh.read()
    except OSError:
        return "foreign", path
    return ("ours" if HOOK_MARKER in body else "foreign"), path


def install_hook(repo=REPO_ROOT, force=False, python=None):
    """Install the pre-commit hook. Returns (action, path).

    action is 'installed' (was absent), 'updated' (ours, refreshed),
    'unchanged' (ours, byte-identical) or 'refused' (a FOREIGN hook is
    there and force is False). Never clobbers someone else's hook by
    default -- a guard that silently eats another hook is a worse bug than
    the one it guards against."""
    state, path = hook_status(repo)
    if state == "foreign" and not force:
        return "refused", path
    body = hook_script(python=python)
    if state == "ours":
        try:
            with open(path) as fh:
                if fh.read() == body:
                    return "unchanged", path
        except OSError:
            pass
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP
             | stat.S_IXOTH)
    return ("updated" if state == "ours" else "installed"), path


def _cmd_check(args):
    hits = staged_escalations(repo=args.repo, registry_path=args.registry)
    if not hits:
        return 0
    print("escalationguard: REFUSING this commit -- it stages %d path(s) "
          "listed in %s as an ADJUDICATED, DELIBERATELY UNCOMMITTED diff."
          % (len(hits), args.registry or REGISTRY_REL), file=sys.stderr)
    registry = load_registry(args.registry, repo=args.repo)
    for p in hits:
        reason = (registry.get(p, {}).get("reason") or "").split(". ")[0]
        rnd = registry.get(p, {}).get("escalated_round")
        print("  %s -- escalated round %s: %s." % (p, rnd, reason),
              file=sys.stderr)
    print("", file=sys.stderr)
    print("This has happened twice in this repo (rounds 393 and 474), both "
          "times via `git add -A`, both times unmentioned in the commit "
          "message. Unstage and commit the rest:", file=sys.stderr)
    print("    git restore --staged -- %s" % " ".join(hits), file=sys.stderr)
    print("If you MEAN to land it, that is a decision the registry entry "
          "says belongs to the operator: resolve the entry first, in the "
          "same commit.", file=sys.stderr)
    return 1


def _cmd_audit(args):
    rows = audit(repo=args.repo, registry_path=args.registry)
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    if not rows:
        if not args.json:
            print("escalationguard: registry is empty -- nothing to audit.")
        return 0
    bad = 0
    for r in rows:
        if not args.json:
            print("%-12s %s" % (r["fate"].upper(), r["path"]))
            print("    %s" % r["detail"])
            for c in r["landed_in"]:
                print("    landed in %s  %s" % (c["short"], c["subject"][:70]))
            print("    registry entry: %s" % {
                "keep": "KEEP -- the escalation is live",
                "delete": "DELETE -- it suppresses nothing and reads as "
                          "coverage",
                "repair": "KEEP AND REPAIR -- deleting it now would erase "
                          "the only machine-readable record that this path "
                          "was ever adjudicated. Restore HEAD to %s first."
                          % (r["restore_to"] or "?")[:12],
            }[r["recommend"]])
        if r["fate"] in (FATE_COMMITTED, FATE_UNKNOWN):
            bad += 1
    return 1 if bad else 0


def _cmd_install_hook(args):
    action, path = install_hook(repo=args.repo, force=args.force)
    print("escalationguard: hook %s at %s" % (action, path))
    if action == "refused":
        print("  a pre-commit hook that is not ours is already there; "
              "re-run with --force to replace it, or chain to us by hand.",
              file=sys.stderr)
        return 1
    return 0


def _cmd_hook_status(args):
    state, path = hook_status(repo=args.repo)
    print("escalationguard: pre-commit hook %s (%s)" % (state, path))
    return 0 if state == "ours" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=REPO_ROOT)
    ap.add_argument("--registry", default=None,
                    help="path to the escalated-diff registry (default: "
                         "<repo>/%s)" % REGISTRY_REL)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("check", help="refuse a commit that stages an escalated "
                                 "path (the pre-commit guard)")
    a = sub.add_parser("audit", help="resolve every entry's fate")
    a.add_argument("--json", action="store_true")
    i = sub.add_parser("install-hook", help="write .git/hooks/pre-commit")
    i.add_argument("--force", action="store_true")
    sub.add_parser("hook-status", help="report whether the hook is installed")
    args = ap.parse_args(argv)
    if args.cmd is None:
        ap.print_help()
        return 2
    return {"check": _cmd_check, "audit": _cmd_audit,
            "install-hook": _cmd_install_hook,
            "hook-status": _cmd_hook_status}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

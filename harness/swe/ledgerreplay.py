"""Replay the slow-tier ledger's freshness rules against git history
(round 367, harness A).

Why this exists
---------------
`swe/slowtier.py` decides whether a recorded slow-test result is still
evidence about the tree in front of it. Round 341 made that decision
whole-checkout (`checkout_digest`), round 343 added a per-file harness half
(`dep_digests`), and round 361 added a per-file SUBJECT half measured by
`swe/readscope.py` — `fresh_pass_scoped` / `fresh_fail_scoped`, a weaker
freshness claim for an entry whose checkout moved somewhere the run was
measured never to read.

Round 361 shipped that mechanism and said so plainly in its own next steps:

    Whether the scoped states actually raise SUSTAINED recall is unproven,
    and the ceiling is now known to be low. ... Round ~367 should read
    `state/slow-tier-ledger.jsonl` and check, rather than taking this
    round's arithmetic for a result.

The obstacle is that "sustained" is not observable from one `status()` call.
`status()` answers "is this entry fresh RIGHT NOW", and the honest answer to
a policy question is a distribution over history: how many commits does an
entry survive, under each policy, starting from anywhere. Re-running the
slow tier to find out is not an option — it is ~76 minutes on this one-CPU
box against a per-round budget in the low hundreds of seconds, which is the
whole reason `slowtier.py` exists.

So this module recomputes both digest halves from **git objects**, at any
revision, without checking anything out, and replays the exact state machine
in `slowtier.classify`. No worktree is created, nothing is written, and the
working tree is never touched — which matters because a round is running in
it.

What it measures
----------------
`survival(...)` — for a slow-tier file with a recorded scope, the number of
consecutive later commits over which an entry recorded at commit `c_i` stays
conclusive. Averaged over every start commit in the window, that is
"sustained recall" as a number, and it can be computed under three policies
side by side:

  * `strict`  — round 341/343: whole-checkout digest + harness deps.
  * `scoped`  — round 361: the same, but a checkout that moved outside the
                entry's measured read-scope leaves it conclusive-but-weaker.
  * `subject` — the subject half ALONE, harness deps ignored. Not a policy
                anyone would ship; it isolates which half is the binding
                constraint, which is the thing a single `status()` line
                cannot tell you.

The one assumption, stated because it is the load-bearing one
--------------------------------------------------------------
A scope is a MEASUREMENT, taken during one run at one commit. Sweeping it
across history assumes a test's read-set is stable over the window. That is
a counterfactual, and it is labelled as one everywhere it is reported
(`counterfactual: true`). The non-counterfactual measurement — each real
ledger entry replayed forward from the commit it was actually recorded at —
is `replay_actual()`, and it is reported alongside. Where the two disagree,
the actual one wins.

Verification that the git-side digests really are the same function:
`checkout_digest_at(rev)` must equal `slowtier.checkout_digest` run over an
EXPORT of that same revision. `main()` runs that check first and refuses to
report if it fails; `test_ledgerreplay.py` pins it against a scratch git repo
the test builds. It is deliberately NOT compared against the live working
tree — `checkout_digest` hashes untracked files, and this repo permanently
carries 15 untracked `.lang` examples from a separate system, so the live
digest corresponds to no commit at all. See `_self_check`.
"""
import json
import os
import subprocess
import sys

try:                                    # `python harness/swe/ledgerreplay.py`
    from swe import slowtier
except ImportError:                     # `python -m swe.ledgerreplay`
    import slowtier

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(HARNESS_ROOT)

#: Repo-relative prefix of the subject checkout, mirroring
#: `slowtier.DEFAULT_WHENCE` but expressed the way git names paths.
WHENCE_PREFIX = "languages/whence"

#: Repo-relative prefix of the harness, mirroring `slowtier.HARNESS_ROOT`.
HARNESS_PREFIX = "harness"

#: Blobs are read in chunks so a wide sweep never buffers the whole history
#: of the checkout in memory at once.
_BATCH = 400


class GitError(Exception):
    pass


def _git(args, root=REPO_ROOT):
    p = subprocess.Popen(["git"] + list(args), cwd=root,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if p.returncode != 0:
        raise GitError("git %s failed: %s" % (" ".join(args),
                                              err.decode("utf-8", "replace")))
    return out


class Repo(object):
    """Content of arbitrary revisions, cached by blob id.

    Two caches, both keyed by content rather than by revision, because the
    revisions in a sweep overwhelmingly share their blobs: `_trees` maps a
    revision to `{repo-relative path: blob id}`, and `_sha256` maps a blob id
    to the hex sha256 of its bytes. The second is what makes the sweep
    affordable — 240 revisions of this repo share almost every blob, so the
    number of blobs actually read is a small multiple of one checkout.
    """

    def __init__(self, root=REPO_ROOT, prefixes=(WHENCE_PREFIX, HARNESS_PREFIX)):
        self.root = root
        self.prefixes = tuple(prefixes)
        self._trees = {}
        self._sha256 = {}
        self._text = {}

    # ----------------------------------------------------------- git access --

    def revs(self, since=None, rev="HEAD", paths=()):
        """Revisions oldest-first. `paths` restricts to commits touching them."""
        args = ["rev-list", "--reverse"]
        if since:
            args += ["--since", since]
        args.append(rev)
        if paths:
            args += ["--"] + list(paths)
        return _git(args, self.root).decode().split()

    def tree(self, rev):
        if rev in self._trees:
            return self._trees[rev]
        out = _git(["ls-tree", "-r", "-z", rev, "--"] + list(self.prefixes),
                   self.root)
        d = {}
        for rec in out.split(b"\0"):
            if not rec:
                continue
            meta, _, path = rec.partition(b"\t")
            parts = meta.split()
            if len(parts) < 3 or parts[1] != b"blob":
                continue
            d[path.decode("utf-8", "surrogateescape")] = parts[2].decode()
        self._trees[rev] = d
        return d

    def sha256(self, blob_id):
        """Hex sha256 of a blob's bytes. Fills the cache in batches."""
        if blob_id not in self._sha256:
            self.prefetch([blob_id])
        return self._sha256[blob_id]

    def text(self, blob_id):
        """Decoded text of a blob, cached. Only used for harness sources.

        Kept separate from `_sha256` on purpose: a sweep hashes every `.py`
        and `.lang` blob in the subject checkout across the whole history and
        needs none of their text, so caching text for those would hold tens
        of megabytes for nothing.
        """
        if blob_id not in self._text:
            self.prefetch_text([blob_id])
        return self._text[blob_id]

    def prefetch_text(self, blob_ids):
        need = sorted(set(b for b in blob_ids if b not in self._text))
        for i in range(0, len(need), _BATCH):
            self._batch(need[i:i + _BATCH], keep_text=True)

    def prefetch(self, blob_ids):
        need = sorted(set(b for b in blob_ids if b not in self._sha256))
        for i in range(0, len(need), _BATCH):
            self._batch(need[i:i + _BATCH])

    def _batch(self, ids, keep_text=False):
        import hashlib
        if not ids:
            return
        p = subprocess.Popen(["git", "cat-file", "--batch"], cwd=self.root,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate(b"".join(i.encode() + b"\n" for i in ids))
        if p.returncode != 0:
            raise GitError("git cat-file failed: %s"
                           % err.decode("utf-8", "replace"))
        pos = 0
        for want in ids:
            nl = out.find(b"\n", pos)
            if nl < 0:
                raise GitError("truncated cat-file stream")
            header = out[pos:nl].split()
            if len(header) != 3:
                raise GitError("unexpected cat-file header %r" % out[pos:nl])
            size = int(header[2])
            body = out[nl + 1:nl + 1 + size]
            self._sha256[want] = hashlib.sha256(body).hexdigest()
            if keep_text:
                self._text[want] = body.decode("utf-8", "replace")
            pos = nl + 1 + size + 1

    # -------------------------------------------------------------- digests --

    def _under(self, rev, prefix):
        """`{path relative to prefix: blob id}` for one prefix at one rev."""
        tree = self.tree(rev)
        n = len(prefix) + 1
        return dict((p[n:], b) for p, b in tree.items()
                    if p.startswith(prefix + "/"))


def working_overlay(repo=None, prefix=WHENCE_PREFIX):
    """`{path relative to prefix: sha256 hex}` for files git does not have.

    A ledger entry's `checkout_digest` is taken from the WORKING TREE, and
    this repo's working tree permanently differs from every commit: a
    separate autonomous system leaves 15 untracked `.lang` examples under
    `languages/whence/` (`state/known-standing-dirty-paths.json`) and one
    tracked file modified. `checkout_digest` hashes source-extension files
    wherever they came from, so **no ledger entry's digest is reproducible
    from any commit** — round 367 measured 0 of 14.

    That is not a dead end, it is a missing term. Exporting round 361's
    commit `bb00ab8` and copying the working tree's untracked files over it
    reproduces `test_swe_loop.py`'s recorded digest `2c9d0227a1d4fca5`
    exactly, which identifies the overlay as the ENTIRE difference. Passing
    this mapping to `checkout_digest_at` / `dir_digest_at` therefore makes
    the historical replay agree with what `status()` actually saw.

    The overlay is a snapshot of the tree NOW. It is valid for a replay
    exactly as long as those files have not changed since the entry was
    recorded, and the digest match is what proves that: an entry whose
    digest still fails to reproduce under the overlay was taken against a
    different overlay, and is reported unreproducible rather than guessed at.
    """
    import hashlib
    root = (repo.root if repo is not None else REPO_ROOT)
    out = {}
    status = _git(["status", "--porcelain", "--", prefix], root)
    for line in status.decode("utf-8", "replace").splitlines():
        code, _, path = line[:2], line[2:3], line[3:]
        path = path.strip().strip('"')
        if code.strip() in ("D", "DD"):
            continue
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            continue
        if not path.startswith(prefix + "/"):
            continue
        with open(full, "rb") as f:
            out[path[len(prefix) + 1:]] = hashlib.sha256(f.read()).hexdigest()
    return out


def checkout_digest_at(repo, rev, prefix=WHENCE_PREFIX, overlay=None):
    """`slowtier.checkout_digest` computed from git objects.

    Byte-for-byte the same construction: source-extension files only, path
    then NUL then the raw sha256 of the bytes, in sorted path order, first 16
    hex chars of the outer sha256. `__pycache__` needs no special case here —
    git does not track it — but `_is_ignored` is still applied so the two
    implementations cannot drift apart on a directory someone adds later.

    `overlay` (see `working_overlay`) supplies content for paths git does not
    have or has differently, which is what makes the result comparable with a
    digest taken from a working tree.
    """
    import hashlib
    overlay = overlay or {}
    blobs = {}
    for rel, blob in repo._under(rev, prefix).items():
        if not rel.endswith(slowtier._SOURCE_EXTS):
            continue
        if slowtier._is_ignored(rel):
            continue
        blobs[rel] = blob
    repo.prefetch(list(blobs.values()))
    h = hashlib.sha256()
    merged = dict((rel, repo.sha256(b)) for rel, b in blobs.items())
    for rel, hexd in overlay.items():
        if rel.endswith(slowtier._SOURCE_EXTS) and not slowtier._is_ignored(rel):
            merged[rel] = hexd
    for rel in sorted(merged):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(bytes.fromhex(merged[rel]))
    return h.hexdigest()[:16]


def dir_digest_at(repo, rev, rel_dir, prefix=WHENCE_PREFIX, overlay=None):
    """`readscope.dir_digest` computed from git objects.

    Non-recursive and extension-blind, exactly as `readscope.dir_digest` is
    with `exts=None`: the directory is the unit, so a file ADDED next to one
    that was read counts as a change. A directory that does not exist at this
    revision is `<missing>`, which is what `os.listdir` failing produces.
    """
    import hashlib
    under = repo._under(rev, prefix)
    entries = {}
    exists = False
    for rel, blob in under.items():
        head, _, name = rel.rpartition("/")
        d = head if head else "."
        if d == rel_dir:
            exists = True
            if not slowtier._is_ignored(rel):
                entries[name] = blob
        elif rel_dir != "." and (d.startswith(rel_dir + "/")):
            exists = True          # the directory exists, via a subdirectory
    if rel_dir == ".":
        exists = True
    repo.prefetch(list(entries.values()))
    merged = dict((n, repo.sha256(b)) for n, b in entries.items())
    for rel, hexd in (overlay or {}).items():
        head, _, name = rel.rpartition("/")
        d = head if head else "."
        if d == rel_dir and not slowtier._is_ignored(rel):
            merged[name] = hexd
            exists = True
    if not exists:
        return "<missing>"
    h = hashlib.sha256()
    for name in sorted(merged):
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(bytes.fromhex(merged[name]))
    return h.hexdigest()[:16]


def scope_digests_at(repo, rev, dirs, prefix=WHENCE_PREFIX, overlay=None):
    return dict((d, dir_digest_at(repo, rev, d, prefix, overlay)) for d in dirs)


class RevSources(object):
    """`slowtier.WORKING_TREE`'s protocol, backed by one git revision.

    This is why `slowtier.harness_deps` grew a `sources` argument in round
    367: the replay runs the REAL import scan over the harness as it was at
    each revision, rather than a second copy of that scan written here. A
    second copy is `skills/copied-mirror-drift`'s exact shape.
    """

    def __init__(self, repo, rev, prefix=HARNESS_PREFIX):
        self.repo = repo
        self.rev = rev
        self.prefix = prefix
        self._files = repo._under(rev, prefix)
        # One batched read for every harness source at this revision. Without
        # it a full-history sweep is one `git cat-file` per (revision, import
        # edge) — tens of thousands of processes — and the blob cache is what
        # makes the sweep affordable at all, since consecutive revisions share
        # nearly every blob.
        repo.prefetch_text([b for r, b in self._files.items()
                            if r.endswith(".py")])

    def exists(self, rel):
        return rel in self._files

    def read(self, rel):
        blob = self._files.get(rel)
        if blob is None:
            raise KeyError(rel)
        return self.repo.text(blob)

    def signature(self):
        """Content identity of the harness sources at this revision.

        Two revisions with the same signature have byte-identical harness
        sources, so `harness_deps` and `dep_digests` cannot differ between
        them — which is what lets a 240-commit sweep do the import scan a
        couple of dozen times instead of 240 times.
        """
        import hashlib
        h = hashlib.sha256()
        for rel in sorted(r for r in self._files if r.endswith(".py")):
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update(self._files[rel].encode())
        return h.hexdigest()[:16]

    def all_swe_rels(self):
        return sorted(r for r in self._files
                      if r.startswith("swe/") and r.endswith(".py"))

    def digests(self, rels):
        """`slowtier.dep_digests`' mapping, from git objects."""
        blobs = [self._files[r] for r in rels if r in self._files]
        self.repo.prefetch(blobs)
        out = {}
        for rel in rels:
            blob = self._files.get(rel)
            out[rel] = "<missing>" if blob is None \
                else self.repo.sha256(blob)[:16]
        return out


# --------------------------------------------------------------- the sweep --

#: The three policies compared. Each maps a `slowtier.classify` state to
#: True (this entry is still usable evidence) or False.
POLICIES = ("strict", "scoped", "subject")


def _alive(state, policy):
    if policy == "strict":
        return state in slowtier.CONCLUSIVE
    if policy == "scoped":
        return state in slowtier.CONCLUSIVE or state in slowtier.SCOPED_CONCLUSIVE
    if policy == "subject":
        # Harness half ignored — see the module docstring. Callers get this
        # by passing `cur_dep_digests=None` into `classify`, which is
        # round 341's own documented "subject half only" mode.
        return state in slowtier.CONCLUSIVE or state in slowtier.SCOPED_CONCLUSIVE
    raise ValueError(policy)


#: `{(harness signature, test file): dep digests}`. Process-wide because a
#: sweep and a replay over the same window share almost every revision.
_DEPS_CACHE = {}


class RevState(object):
    """Everything a replay needs about one revision, computed once."""

    def __init__(self, repo, rev, files, scopes, overlay=None):
        self.rev = rev
        self.overlay = overlay
        self.digest = checkout_digest_at(repo, rev, overlay=overlay)
        sources = RevSources(repo, rev)
        sig = sources.signature()
        self.deps = {}
        for f in files:
            key = (sig, f)
            if key not in _DEPS_CACHE:
                rels = slowtier.harness_deps(f, sources=sources)
                _DEPS_CACHE[key] = sources.digests(rels)
            self.deps[f] = _DEPS_CACHE[key]
        self.scope = {}
        for f, scope in scopes.items():
            # `scopes[f]` is a `readscope` RECORD (`{ok, dirs, opaque}`), not
            # a directory list. Reading it as one is silently harmless-looking
            # and completely wrong: `scope_digests_at` would iterate the dict's
            # KEYS, digest three directories named "ok"/"dirs"/"opaque", get
            # `<missing>` for all three, and report a scope that never moves —
            # i.e. a policy that always wins. Round 367 wrote that bug and
            # caught it only because the resulting lifetimes were suspiciously
            # perfect; `test_scope_digests_track_the_directory_not_the_record`
            # pins it.
            self.scope[f] = scope_digests_at(repo, rev, list(scope["dirs"]),
                                             overlay=overlay)


def _entry_at(rev_state, f, scope):
    """A synthetic ledger entry as it would have been recorded at `rev`."""
    e = {"file": f, "outcome": "passed", "checkout_stable": True,
         "harness_stable": True, "checkout_digest": rev_state.digest,
         "dep_digests": rev_state.deps[f]}
    if scope is not None:
        e["subject_scope"] = scope
        e["subject_digests"] = rev_state.scope[f]
    return e


def survival(states, f, scope, policy):
    """Freshness lifetimes in commits, one per start index.

    `states[i]` is the tree at commit i. An entry recorded at commit i is
    replayed against i+1, i+2, ... and the lifetime is the number of
    consecutive commits it stays alive under `policy`. The last commit in the
    window has lifetime 0 by construction and is excluded from the mean —
    including it would let the window length bias the result downwards.
    """
    out = []
    for i in range(len(states) - 1):
        entry = _entry_at(states[i], f, scope)
        n = 0
        for j in range(i + 1, len(states)):
            cur_scope = None
            if scope is not None:
                cur_scope = states[j].scope[f]
            cur_deps = None if policy == "subject" else states[j].deps[f]
            state = slowtier.classify(entry, states[j].digest,
                                      cur_deps, cur_scope)
            if not _alive(state, policy):
                break
            n += 1
        out.append(n)
    return out


def _mean(xs):
    return (float(sum(xs)) / len(xs)) if xs else 0.0


def ledger_scopes(ledger_path=slowtier.DEFAULT_LEDGER):
    """`{file: scope record}` for every entry whose scope is NARROWABLE.

    Files absent from the result have no usable measurement and are replayed
    strict-only, which is exactly what `slowtier` does with them today.
    """
    best = slowtier.latest_by_file(slowtier.read_entries(ledger_path))
    out = {}
    for f, e in best.items():
        scope = e.get("subject_scope")
        if isinstance(scope, dict) and readscope_narrowable(scope):
            dirs = scope.get("dirs")
            if isinstance(dirs, list):
                out[f] = {"ok": True, "dirs": list(dirs), "opaque": []}
    return out


def readscope_narrowable(scope):
    """`readscope.scope_is_narrowable`, reached through `slowtier`.

    Deliberately not a second `import readscope` with its own two-branch
    fallback: `slowtier` already resolved that import for both entry points
    (`python harness/swe/...` and `python -m swe....`), and one resolution is
    one thing to keep right.
    """
    return slowtier.readscope.scope_is_narrowable(scope)


def build_states(repo, revs, files, scopes, overlay=None):
    """`RevState` per revision. Shared by `sweep`, `blame` and
    `replay_actual` so a run does not build the same trees three times.

    `overlay` is `working_overlay()`'s mapping, or None for a pure-git view.
    The COUNTERFACTUAL sweep uses None — it compares commits with commits,
    where the overlay is a constant that cancels — and `replay_actual` uses
    the overlay, because it compares a working-tree digest with commits.
    """
    return [RevState(repo, r, files, scopes, overlay) for r in revs]


def sweep(repo, revs, files, scopes, states=None, overlay=None):
    """Per-file lifetimes under every policy, plus the window's own facts."""
    states = build_states(repo, revs, files, scopes, overlay) \
        if states is None else states
    per_file = {}
    for f in files:
        scope = scopes.get(f)
        row = {"scope_dirs": list(scope["dirs"]) if scope else None}
        for policy in POLICIES:
            # A file with no measured scope cannot benefit from `scoped`;
            # replaying it with scope=None makes that explicit rather than
            # assuming it.
            lifetimes = survival(states, f, scope, policy)
            row[policy] = {"mean": _mean(lifetimes),
                           "max": max(lifetimes) if lifetimes else 0,
                           "n_starts": len(lifetimes)}
        per_file[f] = row
    moved = _digest_moves(states)
    return {"revs": [s.rev for s in states], "per_file": per_file,
            "window": moved, "counterfactual": True}


def _digest_moves(states):
    """How the window's commits move each half.

    Round 361's motivating statistic was that 52% of the commits moving
    `checkout_digest` touch nothing a slow test actually reads. This is the
    same question asked of the MEASURED scopes rather than of a hand-picked
    path list: of the commits that move the whole-checkout digest, how many
    move something inside a given file's scope. `n_digest_moves` is the
    denominator; `moves_inside_scope_per_file` is the numerator per file.
    """
    n_digest = 0
    n_inside_some = 0
    per_file = {}
    for i in range(1, len(states)):
        a, b = states[i - 1], states[i]
        if a.digest == b.digest:
            continue
        n_digest += 1
        inside_any = False
        for f, d in a.scope.items():
            if d != b.scope.get(f):
                per_file[f] = per_file.get(f, 0) + 1
                inside_any = True
        if inside_any:
            n_inside_some += 1
    return {"n_commits": len(states), "n_digest_moves": n_digest,
            "n_moves_inside_some_scope": n_inside_some,
            "moves_inside_scope_per_file": per_file}


def commit_times(repo, revs):
    """`{rev: committer unix time}` for a window, in one git call."""
    out = _git(["show", "-s", "--format=%H %ct"] + list(revs), repo.root)
    times = {}
    for line in out.decode().splitlines():
        parts = line.split()
        if len(parts) == 2:
            times[parts[0]] = int(parts[1])
    return times


def blame(states, files, scopes, policy="scoped"):
    """WHICH file ends each entry's life, counted over every start commit.

    "The harness half is binding" is a conclusion, not an action. This turns
    it into one: for every (file, start commit) pair it finds the first
    commit that invalidates the entry under `policy` and attributes it —
    to the harness dependency paths that moved, to the scope directories
    that moved, or to `whole-checkout` when the subject digest moved and no
    scope was available to narrow it.

    An invalidating commit can move more than one thing; every mover is
    counted, so the totals exceed the number of invalidations. That is
    deliberate — the question is "how often is X involved in a kill", and
    dividing a joint kill between its causes would understate every cause.
    """
    counts = {}
    kills = 0
    for f in files:
        scope = scopes.get(f)
        for i in range(len(states) - 1):
            entry = _entry_at(states[i], f, scope)
            for j in range(i + 1, len(states)):
                cur_scope = states[j].scope[f] if scope is not None else None
                cur_deps = None if policy == "subject" else states[j].deps[f]
                st = slowtier.classify(entry, states[j].digest,
                                       cur_deps, cur_scope)
                if _alive(st, policy):
                    continue
                kills += 1
                for rel in slowtier.moved_deps(entry, cur_deps or {}):
                    counts["harness:" + rel] = counts.get("harness:" + rel, 0) + 1
                if cur_scope is not None:
                    for d in slowtier.moved_scope(entry, cur_scope):
                        counts["scope:" + d] = counts.get("scope:" + d, 0) + 1
                elif entry["checkout_digest"] != states[j].digest:
                    counts["whole-checkout"] = counts.get("whole-checkout", 0) + 1
                break
    return {"n_kills": kills,
            "by_cause": sorted(counts.items(), key=lambda kv: -kv[1])}


def replay_actual(repo, revs, ledger_path=slowtier.DEFAULT_LEDGER,
                  tests_dir=slowtier.TESTS_DIR, states=None, overlay=None):
    """The NON-counterfactual half: each real entry, from where it was made.

    **Anchoring by `checkout_digest` does not work, and finding that out is a
    result.** The obvious anchor is the entry's own recorded digest: find the
    commit whose tree hashes to it. Every one of the 26 entries in this
    repo's ledger fails that lookup, because `slowtier.checkout_digest` walks
    the FILESYSTEM and this checkout permanently carries untracked `.lang`
    files from a separate system (`state/known-standing-dirty-paths.json`).
    A ledger entry therefore describes a tree that was never committed and
    never will be — the digest is a correct freshness token and a useless
    timeline coordinate.

    So the anchor is `finished_at`: the entry belongs at the last commit made
    at or before the moment the run finished. That is what the run was
    actually looking at, up to the round's own uncommitted edits, and it is
    the same information a human would use. Entries older than the window's
    first commit are reported `before_window` rather than clamped.
    """
    best = slowtier.latest_by_file(slowtier.read_entries(ledger_path))
    files = slowtier.slow_tier_files(tests_dir)
    scopes = {}
    for f, e in best.items():
        sc = e.get("subject_scope")
        if isinstance(sc, dict) and readscope_narrowable(sc) \
                and isinstance(sc.get("dirs"), list):
            scopes[f] = {"ok": True, "dirs": list(sc["dirs"]), "opaque": []}
    states = build_states(repo, revs, files, scopes, overlay) \
        if states is None else states
    times = commit_times(repo, revs)
    ordered = [(times.get(s.rev, 0), i) for i, s in enumerate(states)]
    in_history = set(s.digest for s in states)
    rows = []
    for f in files:
        e = best.get(f)
        if e is None:
            rows.append({"file": f, "status": "no_entry"})
            continue
        fin = e.get("finished_at") or 0
        idx = None
        for t, i in ordered:
            if t <= fin:
                idx = i if idx is None or i > idx else idx
        if idx is None:
            rows.append({"file": f, "status": "before_window",
                         "finished_at": fin})
            continue
        row = {"file": f, "status": "replayed", "start_index": idx,
               "start_rev": states[idx].rev, "outcome": e.get("outcome"),
               "n_commits_after": len(states) - 1 - idx,
               # False means this entry's `strict` column is 0 for a reason
               # that has nothing to do with the policy: its digest was taken
               # from a working tree no commit reproduces, so `stale_checkout`
               # is the answer at EVERY commit. Reporting the 0 without this
               # flag would read as "the strict rule is worthless", which is
               # a different and unsupported claim.
               "digest_in_history": e.get("checkout_digest") in in_history,
               "scope_dirs": list(scopes[f]["dirs"]) if f in scopes else None}
        for policy in POLICIES:
            n = 0
            for j in range(idx + 1, len(states)):
                cur_scope = states[j].scope[f] if f in scopes else None
                cur_deps = None if policy == "subject" else states[j].deps[f]
                st = slowtier.classify(e, states[j].digest, cur_deps, cur_scope)
                if not _alive(st, policy):
                    break
                n += 1
            row[policy] = n
            row[policy + "_state"] = slowtier.classify(
                e, states[-1].digest,
                None if policy == "subject" else states[-1].deps[f],
                states[-1].scope[f] if f in scopes else None)
        rows.append(row)
    return {"revs": [s.rev for s in states], "rows": rows,
            "counterfactual": False}


# ---------------------------------------------------------------------- CLI --

def _self_check(repo, rev="HEAD"):
    """`checkout_digest_at(rev)` must equal `slowtier.checkout_digest` run
    over an EXPORT of the same revision.

    Comparing against the live working tree would be the obvious check and it
    is the wrong one here, for a reason worth writing down: `checkout_digest`
    walks the FILESYSTEM, so it hashes untracked files too, and this repo
    permanently carries 15 untracked `.lang` examples written by a separate
    system (`state/known-standing-dirty-paths.json`). Those are inside
    `_SOURCE_EXTS`, so the live digest and any git-object digest of the same
    commit are unequal BY CONSTRUCTION and always will be. Exporting the
    revision removes the confound and makes the comparison exact.

    Returns `(ok, git_digest, export_digest, n_untracked_source_files)`.
    """
    import shutil
    import tempfile
    git_d = checkout_digest_at(repo, rev)
    tmp = tempfile.mkdtemp(prefix="ledgerreplay-")
    try:
        tar = _git(["archive", rev, "--", WHENCE_PREFIX], repo.root)
        p = subprocess.Popen(["tar", "-x", "-C", tmp], stdin=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        _, err = p.communicate(tar)
        if p.returncode != 0:
            raise GitError("tar failed: %s" % err.decode("utf-8", "replace"))
        export_d = slowtier.checkout_digest(os.path.join(tmp, *WHENCE_PREFIX.split("/")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    untracked = [l for l in _git(["status", "--porcelain", "--",
                                  WHENCE_PREFIX], repo.root)
                 .decode("utf-8", "replace").splitlines()
                 if l[:2] == "??" and l.strip().endswith(slowtier._SOURCE_EXTS)]
    return (git_d == export_d), git_d, export_d, len(untracked)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    since = None
    limit = None
    mode = "both"
    out_path = None
    while argv and argv[0].startswith("--"):
        flag = argv.pop(0)
        if flag == "--since":
            since = argv.pop(0)
        elif flag == "--limit":
            limit = int(argv.pop(0))
        elif flag == "--mode":
            mode = argv.pop(0)
        elif flag == "--json":
            out_path = argv.pop(0)
        elif flag in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print("unknown flag %s" % flag, file=sys.stderr)
            return 2
    repo = Repo()
    ok, git_d, export_d, n_untracked = _self_check(repo)
    print("self-check: git digest %s  export digest %s  %s"
          % (git_d, export_d, "OK" if ok else "MISMATCH"))
    print("            (%d untracked source-extension file(s) under %s -- "
          "these are in the LIVE digest and in no commit)"
          % (n_untracked, WHENCE_PREFIX))
    if not ok:
        print("refusing to report: the git-side digest is not the same "
              "function as slowtier.checkout_digest", file=sys.stderr)
        return 1
    revs = repo.revs(since=since)
    if limit:
        revs = revs[-limit:]
    print("window: %d commits (%s..%s)" % (len(revs), revs[0][:8], revs[-1][:8]))
    files = slowtier.slow_tier_files()
    result = {"window_n": len(revs), "self_check_ok": ok,
              "n_untracked_source_files": n_untracked,
              "head": revs[-1] if revs else None}
    if mode in ("both", "actual"):
        act = replay_actual(repo, revs, overlay=working_overlay(repo))
        result["actual"] = act
        print("\n=== ACTUAL (each ledger entry, from the commit it was "
              "recorded at) ===")
        print("%-34s %-12s %5s %7s %7s %7s %5s  %s"
              % ("file", "status", "after", "strict", "scoped", "subject",
                 "repro", "scope"))
        for r in act["rows"]:
            if r["status"] != "replayed":
                print("%-34s %-12s" % (r["file"], r["status"]))
                continue
            print("%-34s %-12s %5d %7d %7d %7d %5s  %s"
                  % (r["file"], r["status"], r["n_commits_after"],
                     r["strict"], r["scoped"], r["subject"],
                     "yes" if r["digest_in_history"] else "NO",
                     r.get("scope_dirs")))
        n_repro = len([r for r in act["rows"]
                       if r.get("digest_in_history")])
        n_rep = len([r for r in act["rows"] if r["status"] == "replayed"])
        print("repro: %d of %d replayed entries have a checkout digest that "
              "ANY commit in the window reproduces." % (n_repro, n_rep))
        if n_repro < n_rep:
            print("       The rest were recorded against a working tree that "
                  "was never committed, so their `strict` column is 0 by "
                  "construction and says nothing about the strict rule.")
    if mode in ("both", "sweep"):
        scopes = ledger_scopes()
        states = build_states(repo, revs, files, scopes)
        sw = sweep(repo, revs, files, scopes, states=states)
        result["sweep"] = sw
        print("\n=== COUNTERFACTUAL SWEEP (measured scopes held fixed, "
              "swept over every start commit) ===")
        print("%-34s %8s %8s %8s  %s"
              % ("file", "strict", "scoped", "subject", "scope"))
        for f in files:
            row = sw["per_file"][f]
            print("%-34s %8.2f %8.2f %8.2f  %s"
                  % (f, row["strict"]["mean"], row["scoped"]["mean"],
                     row["subject"]["mean"], row["scope_dirs"]))
        w = sw["window"]
        print("\nwindow: %d commits, %d move the checkout digest, "
              "%d of those move something inside a measured scope"
              % (w["n_commits"], w["n_digest_moves"],
                 w["n_moves_inside_some_scope"]))
        bl = blame(states, files, scopes)
        result["blame"] = bl
        print("\nwhat ends an entry's life (scoped policy, %d kills over all "
              "start commits):" % bl["n_kills"])
        for cause, n in bl["by_cause"][:12]:
            print("   %6d  %s" % (n, cause))
        means = dict((p, _mean([sw["per_file"][f][p]["mean"] for f in files]))
                     for p in POLICIES)
        print("mean lifetime over all %d files: strict %.2f  scoped %.2f  "
              "subject %.2f" % (len(files), means["strict"], means["scoped"],
                                means["subject"]))
        result["means"] = means
    if out_path:
        d = os.path.dirname(out_path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, sort_keys=True)
        print("\nwrote %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

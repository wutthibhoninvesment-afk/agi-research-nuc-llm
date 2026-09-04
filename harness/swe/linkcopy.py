"""Hardlinked mutant sandboxes (round 497, SWE-loop D).

THE COST THIS EXISTS TO REMOVE
------------------------------
Every mutant this program has ever scored ran inside a fresh
`shutil.copytree` of the whole checkout (`mutation._copy_project`). Round 491
measured what that costs on the `nuc/perturbation.py` campaign: **4.87 s of
every 12.78 s mutant**, invariant to every test-selection improvement, and it
named the copy as the next lever. The tree is 563 MB in 4089 files with the
ignore list applied, so a 55-mutant slice moved ~31 GB through the page cache
to run 55 pytest invocations that between them read a few hundred kilobytes.

A hardlink costs a directory entry. Nothing here reads or writes file data.

THE HAZARD, AND WHY THE MASTER TREE EXISTS
------------------------------------------
A hardlink is not a copy: the two names share one inode, so anything that
writes IN PLACE through one name changes the other. Two writers matter.

1. **Us.** `run_mutant`'s own `open(dst/m.path, "w")` truncates the shared
   inode -- it would edit the file it linked from. `mutation._write_mutant`
   now unlinks first (round 497), which is a no-op difference for a byte copy
   and the whole difference for a linked one. Pinned by
   `test_writing_a_mutant_into_a_linked_sandbox_leaves_the_master_alone`.

2. **The suite under test.** A test that opens a file in its own tree for
   writing has always been harmless, because the tree was a copy. Under
   links it would reach through. There is no way to prevent that with
   permissions -- mode is a property of the inode, so `chmod` on the link
   changes the original too -- so this module does not link from the
   CHECKOUT at all.

   `MasterTree` makes ONE byte copy (the cost the campaign used to pay per
   mutant) and every sandbox hardlinks from that. The blast radius of a
   write-through is a throwaway tree in `/tmp`, never the repo -- which
   matters here specifically, because 81 % of the bytes in this repo's copy
   scope are `logs/`, which is gitignored and would not be recoverable by
   `git checkout`.

   `TreeWitness` then detects it rather than assuming it away: size, mtime,
   mode and inode of every master file before the sandbox, re-stat'd after.
   Drift is REPORTED (and can re-stage the master), never silently absorbed.
   Round 491's `nodeguard` is the same shape one layer up: the cheaper oracle
   is trusted only after a probe says it is sound.

EXDEV
-----
`os.link` fails across filesystems. `link_tree` falls back to `shutil.copy2`
per file and COUNTS the fallbacks, so a run on a box where `/tmp` is a
different mount degrades to the old cost instead of raising -- and says so in
`stats["n_fallback"]` rather than looking fast and being slow. Prefer
`MasterTree(workdir=...)` on the same filesystem as the sandboxes.
"""

import errno
import fnmatch
import hashlib
import os
import shutil
import stat
import tempfile

try:                                         # package import
    from .mutation import COPY_IGNORE, _copy_project
except ImportError:                          # imported as a top-level module
    from mutation import COPY_IGNORE, _copy_project


def _ignored(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def link_tree(src, dst, ignore=COPY_IGNORE):
    """Recreate `src` at `dst` with hardlinks instead of byte copies.

    Directories are made, symlinks are recreated as symlinks (linking a
    symlink's target would silently deep-copy it into the tree), regular
    files are `os.link`ed. Anything `os.link` refuses (EXDEV, EMLINK, EPERM
    on some filesystems) falls back to `shutil.copy2` and is counted.

    Returns a stats dict; `n_fallback > 0` means this was not the cheap path.
    """
    st = {"n_dirs": 0, "n_files": 0, "n_symlinks": 0, "n_fallback": 0,
          "fallback_reasons": {}}
    src = os.path.abspath(src)
    os.makedirs(dst, exist_ok=True)
    st["n_dirs"] += 1
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if not _ignored(d, ignore)]
        rel = os.path.relpath(dirpath, src)
        out_dir = dst if rel == "." else os.path.join(dst, rel)
        for d in dirnames:
            os.makedirs(os.path.join(out_dir, d), exist_ok=True)
            st["n_dirs"] += 1
        for f in filenames:
            if _ignored(f, ignore):
                continue
            s = os.path.join(dirpath, f)
            d = os.path.join(out_dir, f)
            if os.path.islink(s):
                try:
                    os.symlink(os.readlink(s), d)
                    st["n_symlinks"] += 1
                except OSError:
                    pass
                continue
            try:
                os.link(s, d)
                st["n_files"] += 1
            except OSError as e:
                name = errno.errorcode.get(e.errno, str(e.errno))
                st["fallback_reasons"][name] = st["fallback_reasons"].get(name, 0) + 1
                try:
                    shutil.copy2(s, d)
                    st["n_files"] += 1
                    st["n_fallback"] += 1
                except OSError:
                    pass
    return st


class TreeWitness(object):
    """Snapshot of a tree, and the drift against it. Two depths, both cheap
    for what they are, and the shallow one has a MEASURED blind spot.

    SHALLOW (default) records `(size, mtime_ns, mode, inode)` per relative
    path. Measured over this repo's 4091-file copy scope: **0.09-0.11 s** per
    check (the bare stat loop is 0.017 s; the rest is `os.path.relpath` and
    the dict), against a 0.19 s link copy and a 2.4 s byte copy -- so it is
    affordable after every single mutant, which is how it is used.

    Its blind spot is not hypothetical and round 497 measured it rather than
    reasoning about it: on this box `unlink` + recreate REUSES the inode
    immediately, and two writes microseconds apart get the SAME `st_mtime_ns`
    (the kernel's file timestamps do not advance between them). So a
    same-size rewrite inside one clock tick is invisible to every field
    recorded here. `test_swe_linkcopy.py::
    test_the_shallow_witness_has_a_measured_blind_spot_the_deep_one_closes`
    pins exactly that, in both directions.

    DEEP (`digest=True`) also hashes every file: **1.5-1.9 s** for 563 MB on
    this box, against a byte copy's 2.0-3.0 s. Too expensive per mutant,
    cheap once per slice -- which is how `nodecampaign` uses it, shallow
    after each mutant and deep at the slice boundary.

    `mode` and `inode` are recorded because a hardlink shares them: a `chmod`
    or an in-place rewrite through a sandbox is visible in the master's own
    stat, while a sandbox that REPLACES a file (unlink + create, which is
    what `_write_mutant` does) leaves the master untouched by construction.
    The two cases must be distinguishable, so both are kept.
    """

    #: Read in 64 KB chunks; `blake2b(digest_size=16)` because this is a
    #: change detector, not a signature.
    CHUNK = 1 << 16

    def __init__(self, root, ignore=COPY_IGNORE, digest=False):
        self.root = os.path.abspath(root)
        self.ignore = tuple(ignore)
        self.digest = bool(digest)
        self.snap = self._walk()

    def _hash(self, path):
        h = hashlib.blake2b(digest_size=16)
        try:
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(self.CHUNK), b""):
                    h.update(chunk)
        except OSError:
            return None
        return h.hexdigest()

    def _walk(self):
        out = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if not _ignored(d, self.ignore)]
            for f in filenames:
                if _ignored(f, self.ignore):
                    continue
                p = os.path.join(dirpath, f)
                try:
                    s = os.lstat(p)
                except OSError:
                    continue
                if stat.S_ISLNK(s.st_mode):
                    continue
                out[os.path.relpath(p, self.root)] = (
                    s.st_size, s.st_mtime_ns, s.st_mode, s.st_ino,
                    self._hash(p) if self.digest else None)
        return out

    def drift(self):
        """`[(relpath, kind)]` for every file that changed since the snapshot.

        `kind` is `modified` (an in-place write -- the write-through this
        module guards against, same inode), `replaced` (the content moved to
        a different inode), `missing`, or `added`.

        In DEEP mode the comparison is on CONTENT: a file whose bytes are
        unchanged is not drift even if its mtime moved, because the question
        this instrument answers is "is the master still the project", not
        "did anything touch it".
        """
        now = self._walk()
        out = []
        for p, old in sorted(self.snap.items()):
            new = now.get(p)
            if new is None:
                out.append((p, "missing"))
                continue
            if self.digest:
                changed = new[4] != old[4]
            else:
                changed = new[:4] != old[:4]
            if not changed:
                continue
            out.append((p, "replaced" if new[3] != old[3] else "modified"))
        for p in sorted(now):
            if p not in self.snap:
                out.append((p, "added"))
        return out

    def refresh(self):
        self.snap = self._walk()


class MasterTree(object):
    """One byte copy of the project; every sandbox hardlinks from it.

    Use as a context manager, or call `stage()` / `close()` by hand. The
    instance is itself a `(project_root, dst)` callable, so it drops straight
    into `mutation.run_mutant(..., copier=master)` where `_copy_project` used
    to go.
    """

    def __init__(self, project_root, workdir=None, ignore=COPY_IGNORE,
                 witness=True, deep_witness=False):
        self.project_root = os.path.abspath(project_root)
        self.ignore = tuple(ignore)
        self.workdir = workdir
        self._own_workdir = workdir is None
        self.path = None
        self.witness = None
        self.deep = None
        self._want_witness = witness
        self._want_deep = deep_witness
        self.stats = {"n_sandboxes": 0, "n_stagings": 0, "link_seconds": 0.0,
                      "stage_seconds": 0.0, "witness_seconds": 0.0,
                      "n_fallback": 0, "drift_events": []}

    # -- lifecycle ---------------------------------------------------------
    def stage(self):
        """Make (or re-make) the master by byte copy. Costs one full copy."""
        import time
        if self.workdir is None:
            self.workdir = tempfile.mkdtemp(prefix="mut-master-")
        if self.path and os.path.isdir(self.path):
            shutil.rmtree(self.path, ignore_errors=True)
        self.path = os.path.join(self.workdir, "master")
        t0 = time.monotonic()
        _copy_project(self.project_root, self.path)
        self.stats["stage_seconds"] += time.monotonic() - t0
        self.stats["n_stagings"] += 1
        if self._want_witness:
            t0 = time.monotonic()
            self.witness = TreeWitness(self.path, self.ignore)
            if self._want_deep:
                self.deep = TreeWitness(self.path, self.ignore, digest=True)
            self.stats["witness_seconds"] += time.monotonic() - t0
        return self.path

    def close(self):
        if self._own_workdir and self.workdir:
            shutil.rmtree(self.workdir, ignore_errors=True)
        elif self.path:
            shutil.rmtree(self.path, ignore_errors=True)
        self.path = None

    def __enter__(self):
        self.stage()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # -- the copier ---------------------------------------------------------
    def __call__(self, project_root, dst):
        """`(project_root, dst)` -- the `_copy_project` signature.

        `project_root` must be the root this master was staged from: a caller
        that silently sandboxes a DIFFERENT project would get this one, and
        would get a green campaign about a tree it never ran. Raises instead.
        """
        import time
        if os.path.abspath(project_root) != self.project_root:
            raise ValueError(
                "master was staged from %s, asked to sandbox %s"
                % (self.project_root, project_root))
        if not self.path:
            self.stage()
        t0 = time.monotonic()
        st = link_tree(self.path, dst, self.ignore)
        self.stats["link_seconds"] += time.monotonic() - t0
        self.stats["n_sandboxes"] += 1
        self.stats["n_fallback"] += st["n_fallback"]
        return st

    # -- soundness ----------------------------------------------------------
    def check(self, label=None, restage_on_drift=True, deep=False):
        """Drift of the master since the last snapshot; re-stages if dirty.

        Returns `[]` when clean. A non-empty return means something wrote
        through a link -- the master is no longer the project, so every later
        sandbox would be wrong, and by default it is rebuilt and the event
        recorded in `stats["drift_events"]`.

        `deep=True` compares CONTENT and needs `deep_witness=True` at
        construction (a deep check with no deep baseline would be a check
        against nothing, so it falls back to the shallow one rather than
        reporting a clean tree it never hashed).
        """
        import time
        w = (self.deep if (deep and self.deep) else self.witness)
        if not w:
            return []
        t0 = time.monotonic()
        d = w.drift()
        self.stats["witness_seconds"] += time.monotonic() - t0
        if d:
            self.stats["drift_events"].append(
                {"label": label, "n": len(d), "paths": [p for p, _ in d[:20]],
                 "kinds": sorted({k for _, k in d})})
            self.stats["drift_events"][-1]["deep"] = bool(deep and self.deep)
            if restage_on_drift:
                self.stage()
            else:
                w.refresh()
        return d

    def as_dict(self):
        s = dict(self.stats)
        s["seconds_per_sandbox"] = (
            round(s["link_seconds"] / s["n_sandboxes"], 3)
            if s["n_sandboxes"] else None)
        s["link_seconds"] = round(s["link_seconds"], 2)
        s["stage_seconds"] = round(s["stage_seconds"], 2)
        s["witness_seconds"] = round(s["witness_seconds"], 2)
        s["n_drift_events"] = len(s["drift_events"])
        return s

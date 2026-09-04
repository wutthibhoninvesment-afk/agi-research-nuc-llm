"""Round 497 (SWE-loop D): hardlinked mutant sandboxes.

Round 491 named the copy as the next lever — `_copy_project` was 4.87 s of
every 12.78 s mutant, a 563 MB `shutil.copytree` per mutant, invariant to
every test-selection improvement. `swe/linkcopy.py` replaces the per-mutant
byte copy with a per-mutant hardlink tree over ONE staged master.

The interesting tests here are the unsafe ones. A hardlink is not a copy, so
this file pins the write-through (as a CONTROL that the hazard is real, not
argued), the unlink that stops it, and the witness that detects the case
nobody controls — a test suite writing into the tree it runs in.
"""
import errno
import os
import shutil
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.linkcopy as LC
import swe.mutation as MU


# --------------------------------------------------------------------------
# helpers

def _project(root, extra=None):
    """A tiny project with the shapes that matter: a nested package, a file
    in every ignored category, and (optionally) more."""
    os.makedirs(os.path.join(root, "pkg"), exist_ok=True)
    os.makedirs(os.path.join(root, "pkg", "__pycache__"), exist_ok=True)
    os.makedirs(os.path.join(root, "node_modules", "dep"), exist_ok=True)
    os.makedirs(os.path.join(root, ".git"), exist_ok=True)
    _w(os.path.join(root, "pkg", "__init__.py"), "")
    _w(os.path.join(root, "pkg", "mod.py"), "def f(x):\n    return x + 1\n")
    _w(os.path.join(root, "top.txt"), "hello\n")
    _w(os.path.join(root, "pkg", "__pycache__", "mod.cpython-99.pyc"), "junk")
    _w(os.path.join(root, "node_modules", "dep", "index.js"), "x")
    _w(os.path.join(root, ".git", "HEAD"), "ref: refs/heads/main\n")
    _w(os.path.join(root, "stale.pyc"), "junk")
    for rel, body in (extra or {}).items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        _w(p, body)
    return root


def _w(path, body):
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def _r(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _rels(root):
    out = set()
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            out.add(os.path.relpath(os.path.join(dirpath, f), root))
    return out


class _M(object):
    """The two attributes `run_mutant` reads off a mutant."""

    def __init__(self, path, source):
        self.path, self.source = path, source
        self.status = self.detail = None
        self.seconds = 0.0


# --------------------------------------------------------------------------
# link_tree

def test_link_tree_reproduces_the_tree_and_applies_the_ignore_list(tmp_path):
    src = _project(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")
    st = LC.link_tree(src, dst)

    assert _r(os.path.join(dst, "pkg", "mod.py")) == _r(os.path.join(src, "pkg", "mod.py"))
    assert _r(os.path.join(dst, "top.txt")) == "hello\n"
    got = _rels(dst)
    assert "pkg/mod.py".replace("/", os.sep) in got
    for gone in (".git", "node_modules", "__pycache__"):
        assert not any(gone in p for p in got), (gone, got)
    assert "stale.pyc" not in got            # *.pyc pattern, not just the dir
    assert st["n_files"] == 3 and st["n_fallback"] == 0


def test_link_tree_ignores_exactly_what_copy_project_ignores(tmp_path):
    """The two sandbox makers must agree, or a linked campaign is not the
    campaign the byte-copy one measured. Both read `mutation.COPY_IGNORE`."""
    src = _project(str(tmp_path / "src"))
    linked, copied = str(tmp_path / "l"), str(tmp_path / "c")
    LC.link_tree(src, linked)
    MU._copy_project(src, copied)
    assert _rels(linked) == _rels(copied)


def test_link_tree_shares_inodes_rather_than_bytes(tmp_path):
    src = _project(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")
    LC.link_tree(src, dst)
    a = os.stat(os.path.join(src, "pkg", "mod.py"))
    b = os.stat(os.path.join(dst, "pkg", "mod.py"))
    assert (a.st_ino, a.st_dev) == (b.st_ino, b.st_dev)
    assert b.st_nlink >= 2


def test_link_tree_recreates_a_symlink_as_a_symlink(tmp_path):
    """Linking a symlink's TARGET would silently deep-copy it into the tree
    and give the sandbox a file where the project has a link."""
    src = _project(str(tmp_path / "src"))
    os.symlink("top.txt", os.path.join(src, "alias.txt"))
    dst = str(tmp_path / "dst")
    st = LC.link_tree(src, dst)
    assert os.path.islink(os.path.join(dst, "alias.txt"))
    assert os.readlink(os.path.join(dst, "alias.txt")) == "top.txt"
    assert st["n_symlinks"] == 1


def test_link_tree_falls_back_to_a_byte_copy_and_counts_it(tmp_path, monkeypatch):
    """EXDEV: `/tmp` on another mount. The run must degrade to the old cost
    and SAY SO, not raise and not look cheap."""
    src = _project(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")

    def no_link(a, b):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(LC.os, "link", no_link)
    st = LC.link_tree(src, dst)
    assert st["n_fallback"] == st["n_files"] == 3
    assert st["fallback_reasons"] == {"EXDEV": 3}
    assert _r(os.path.join(dst, "pkg", "mod.py")).startswith("def f(x)")
    a = os.stat(os.path.join(src, "pkg", "mod.py"))
    b = os.stat(os.path.join(dst, "pkg", "mod.py"))
    assert a.st_ino != b.st_ino          # a real copy, not a link


# --------------------------------------------------------------------------
# the hazard, and the unlink that removes it

def test_a_truncating_open_writes_through_a_hardlink(tmp_path):
    """CONTROL. This is the defect the rest of the module guards against,
    demonstrated rather than asserted in prose: if this test ever fails,
    `_write_mutant`'s unlink and `MasterTree`'s whole existence are
    unnecessary and round 497's safety half should be deleted."""
    src = _project(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")
    LC.link_tree(src, dst)
    with open(os.path.join(dst, "pkg", "mod.py"), "w", encoding="utf-8") as f:
        f.write("MUTATED\n")
    assert _r(os.path.join(src, "pkg", "mod.py")) == "MUTATED\n"


def test_writing_a_mutant_into_a_linked_sandbox_leaves_the_master_alone(tmp_path):
    src = _project(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")
    LC.link_tree(src, dst)
    before = _r(os.path.join(src, "pkg", "mod.py"))
    MU._write_mutant(dst, _M(os.path.join("pkg", "mod.py"), "MUTATED\n"))
    assert _r(os.path.join(dst, "pkg", "mod.py")) == "MUTATED\n"
    assert _r(os.path.join(src, "pkg", "mod.py")) == before
    a = os.stat(os.path.join(src, "pkg", "mod.py"))
    b = os.stat(os.path.join(dst, "pkg", "mod.py"))
    assert a.st_ino != b.st_ino


def test_write_mutant_is_unconditional_and_a_byte_copy_sees_no_difference(tmp_path):
    src = _project(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")
    MU._copy_project(src, dst)
    MU._write_mutant(dst, _M(os.path.join("pkg", "mod.py"), "MUTATED\n"))
    assert _r(os.path.join(dst, "pkg", "mod.py")) == "MUTATED\n"
    assert _r(os.path.join(src, "pkg", "mod.py")).startswith("def f(x)")


# --------------------------------------------------------------------------
# TreeWitness

def test_witness_is_silent_on_an_untouched_tree(tmp_path):
    src = _project(str(tmp_path / "src"))
    w = LC.TreeWitness(src)
    LC.link_tree(src, str(tmp_path / "dst"))     # linking changes no content
    assert w.drift() == []


def test_witness_reports_an_in_place_write_as_modified(tmp_path):
    """The write-through shape: same inode, new bytes."""
    src = _project(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")
    LC.link_tree(src, dst)
    w = LC.TreeWitness(src)
    with open(os.path.join(dst, "top.txt"), "a", encoding="utf-8") as f:
        f.write("appended by a test that thought the tree was its own\n")
    assert w.drift() == [("top.txt", "modified")]


def test_witness_reports_a_replacement_when_the_inode_really_moves(tmp_path):
    src = _project(str(tmp_path / "src"))
    dst = str(tmp_path / "dst")
    LC.link_tree(src, dst)                       # bumps nlink, not content
    w = LC.TreeWitness(src)
    os.unlink(os.path.join(src, "top.txt"))      # the linked inode survives
    _w(os.path.join(src, "top.txt"), "different\n")
    assert w.drift() == [("top.txt", "replaced")]


def test_the_shallow_witness_has_a_measured_blind_spot_the_deep_one_closes(tmp_path):
    """Round 497 found this by having a test fail, and it is a property of
    the filesystem, not of the code: `unlink` + recreate REUSES the inode
    immediately, and two writes microseconds apart carry the same
    `st_mtime_ns`. A same-size rewrite inside one clock tick therefore moves
    NONE of the four stat fields.

    Both directions are asserted. If the first assert ever fails the blind
    spot has closed and the docstrings in `linkcopy.py` are overclaiming; if
    the second fails the deep mode is not buying what it costs.
    """
    src = _project(str(tmp_path / "src"))
    shallow = LC.TreeWitness(src)
    deep = LC.TreeWitness(src, digest=True)
    before = os.lstat(os.path.join(src, "top.txt"))

    os.unlink(os.path.join(src, "top.txt"))
    _w(os.path.join(src, "top.txt"), "HELLO\n")   # same 6 bytes, new content
    after = os.lstat(os.path.join(src, "top.txt"))

    assert after.st_size == before.st_size
    if (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns):
        assert shallow.drift() == []             # the blind spot, demonstrated
    assert deep.drift() == [("top.txt", "modified")]


def test_the_deep_witness_ignores_a_touch_that_changed_no_bytes(tmp_path):
    """Content is the question. A master whose mtimes moved but whose bytes
    did not is still the project, and reporting it as drift would re-stage
    (a full byte copy) for nothing."""
    src = _project(str(tmp_path / "src"))
    deep = LC.TreeWitness(src, digest=True)
    os.utime(os.path.join(src, "top.txt"), (1, 1))
    assert deep.drift() == []
    assert LC.TreeWitness(src).drift() == []     # sanity: fresh baseline


def test_witness_reports_missing_and_added(tmp_path):
    src = _project(str(tmp_path / "src"))
    w = LC.TreeWitness(src)
    os.unlink(os.path.join(src, "top.txt"))
    _w(os.path.join(src, "new.txt"), "x")
    assert sorted(w.drift()) == [("new.txt", "added"), ("top.txt", "missing")]


def test_witness_ignores_the_scratch_a_suite_creates(tmp_path):
    """pytest writes `.pytest_cache` and `__pycache__` into whatever tree it
    runs in. Both are in the ignore list, so a sandbox creates them fresh and
    they are not drift — if they counted, every single mutant would report a
    write-through and the signal would be worthless."""
    src = _project(str(tmp_path / "src"))
    w = LC.TreeWitness(src)
    os.makedirs(os.path.join(src, ".pytest_cache", "v"), exist_ok=True)
    _w(os.path.join(src, ".pytest_cache", "v", "lastfailed"), "{}")
    _w(os.path.join(src, "pkg", "__pycache__", "mod.cpython-99.pyc"), "new junk")
    assert w.drift() == []


# --------------------------------------------------------------------------
# MasterTree

def test_master_stages_once_and_sandboxes_are_links(tmp_path):
    src = _project(str(tmp_path / "src"))
    with LC.MasterTree(src, workdir=str(tmp_path / "wd")) as m:
        a, b = str(tmp_path / "a"), str(tmp_path / "b")
        m(src, a)
        m(src, b)
        assert _rels(a) == _rels(b) == _rels(m.path)
        ino = os.stat(os.path.join(m.path, "pkg", "mod.py")).st_ino
        assert os.stat(os.path.join(a, "pkg", "mod.py")).st_ino == ino
        assert os.stat(os.path.join(b, "pkg", "mod.py")).st_ino == ino
        d = m.as_dict()
        assert d["n_stagings"] == 1 and d["n_sandboxes"] == 2
        assert d["n_fallback"] == 0 and d["n_drift_events"] == 0


def test_master_never_links_from_the_checkout(tmp_path):
    """The property that makes this safe to run against a real repo: a
    sandbox shares inodes with the MASTER, and shares none with the project.
    A suite that writes through can only reach a throwaway tree."""
    src = _project(str(tmp_path / "src"))
    with LC.MasterTree(src, workdir=str(tmp_path / "wd")) as m:
        sb = str(tmp_path / "sb")
        m(src, sb)
        for rel in ("top.txt", os.path.join("pkg", "mod.py")):
            assert os.stat(os.path.join(sb, rel)).st_ino \
                != os.stat(os.path.join(src, rel)).st_ino


def test_master_refuses_to_sandbox_a_different_project(tmp_path):
    src = _project(str(tmp_path / "src"))
    other = _project(str(tmp_path / "other"))
    with LC.MasterTree(src, workdir=str(tmp_path / "wd")) as m:
        try:
            m(other, str(tmp_path / "sb"))
        except ValueError as e:
            assert "staged from" in str(e)
        else:
            raise AssertionError("silently sandboxed the wrong project")


def test_master_check_reports_a_write_through_and_restages(tmp_path):
    src = _project(str(tmp_path / "src"))
    with LC.MasterTree(src, workdir=str(tmp_path / "wd")) as m:
        sb = str(tmp_path / "sb")
        m(src, sb)
        with open(os.path.join(sb, "top.txt"), "w", encoding="utf-8") as f:
            f.write("a test wrote here\n")        # in place: reaches the master
        assert _r(os.path.join(m.path, "top.txt")) == "a test wrote here\n"
        drift = m.check(label="mutant-1")
        assert drift == [("top.txt", "modified")]
        # re-staged from the project, so the next sandbox is clean again
        assert _r(os.path.join(m.path, "top.txt")) == "hello\n"
        assert _r(os.path.join(src, "top.txt")) == "hello\n"
        d = m.as_dict()
        assert d["n_drift_events"] == 1 and d["n_stagings"] == 2
        assert d["drift_events"][0]["label"] == "mutant-1"
        assert m.check() == []


def test_master_carries_the_example_curation_into_every_sandbox(tmp_path):
    """`_copy_project` materialises the curated `examples/*.lang` list at the
    one boundary where the checkout is still reachable (round 437). Staging
    happens there; sandboxes inherit the manifest through the link, which is
    the documented behaviour of `write_example_curation` on a copy of a
    copy."""
    src = _project(str(tmp_path / "src"), extra={
        os.path.join("examples", "a.lang"): "1\n",
        os.path.join("examples", "dropped_by_another_process.lang"): "2\n",
        os.path.join("examples", ".curated-examples"): "a.lang\n",
    })
    with LC.MasterTree(src, workdir=str(tmp_path / "wd")) as m:
        sb = str(tmp_path / "sb")
        m(src, sb)
        man = os.path.join(sb, "examples", ".curated-examples")
        assert os.path.exists(man)
        assert "a.lang" in _r(man)


# --------------------------------------------------------------------------
# the seam in run_mutant

RUNNABLE = {
    os.path.join("pkg", "mod.py"): "def f(x):\n    return x + 1\n",
    os.path.join("tests", "test_mod.py"): textwrap.dedent('''
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from pkg.mod import f

        def test_f():
            assert f(1) == 2
    '''),
}


def _runnable_project(root):
    for rel, body in RUNNABLE.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        _w(p, body)
    return root


def test_run_mutant_through_a_master_scores_and_leaves_the_project_alone(tmp_path):
    src = _runnable_project(str(tmp_path / "src"))
    cmd = [sys.executable, "-m", "pytest", "-x", "-q", "tests"]
    with LC.MasterTree(src, workdir=str(tmp_path / "wd")) as m:
        killed = MU.run_mutant(_M(os.path.join("pkg", "mod.py"),
                                  "def f(x):\n    return x + 2\n"),
                               src, cmd, timeout_s=120.0, copier=m,
                               tmp_dir=str(tmp_path / "wd"))
        survived = MU.run_mutant(_M(os.path.join("pkg", "mod.py"),
                                    "def f(x):\n    return x + 1  # noqa\n"),
                                 src, cmd, timeout_s=120.0, copier=m,
                                 tmp_dir=str(tmp_path / "wd"))
    assert killed.status == "killed"
    assert survived.status == "survived"
    assert _r(os.path.join(src, "pkg", "mod.py")) == RUNNABLE[os.path.join("pkg", "mod.py")]


def test_run_mutant_default_copier_is_unchanged(tmp_path):
    """Additive: every existing caller passes no `copier` and must still get
    a byte copy of the project."""
    src = _runnable_project(str(tmp_path / "src"))
    seen = {}
    real = MU._copy_project

    def spy(root, dst):
        seen["called"] = True
        return real(root, dst)

    try:
        MU._copy_project = spy
        m = MU.run_mutant(_M(os.path.join("pkg", "mod.py"),
                             "def f(x):\n    return x + 2\n"),
                          src, [sys.executable, "-m", "pytest", "-x", "-q", "tests"],
                          timeout_s=120.0)
    finally:
        MU._copy_project = real
    assert seen.get("called") is True
    assert m.status == "killed"


def test_a_suite_that_writes_into_its_tree_is_caught_by_the_witness(tmp_path):
    """End to end, with a real pytest run: the case P7 predicts does not
    happen for `test_perturbation.py` but which nothing prevents in general.
    The master is corrupted, `check()` names the file, and the master is
    rebuilt before the next mutant runs against it."""
    src = _runnable_project(str(tmp_path / "src"))
    _w(os.path.join(src, "data.txt"), "original\n")
    _w(os.path.join(src, "tests", "test_writes.py"), textwrap.dedent('''
        import os

        def test_writes_into_its_own_tree():
            p = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "data.txt")
            with open(p, "a") as f:
                f.write("a test appended this\\n")
    '''))
    cmd = [sys.executable, "-m", "pytest", "-x", "-q", "tests"]
    with LC.MasterTree(src, workdir=str(tmp_path / "wd")) as m:
        MU.run_mutant(_M(os.path.join("pkg", "mod.py"),
                         "def f(x):\n    return x + 1\n"),
                      src, cmd, timeout_s=120.0, copier=m,
                      tmp_dir=str(tmp_path / "wd"))
        drift = m.check(label="the-writing-suite")
        assert ("data.txt", "modified") in drift
        assert _r(os.path.join(m.path, "data.txt")) == "original\n"
    assert _r(os.path.join(src, "data.txt")) == "original\n"

---
name: live-tree-read-must-tolerate-a-vanish
description: Use when a bulk read of a directory that other processes write — a copy, a walk, a checksum, a bulk upload, a glob-then-open — fails with ENOENT on a file the listing had just returned. Listing and reading are two syscalls, so a concurrent unlink between them is normal, not exceptional. The repair belongs at the READER, which is one function, not at the writer population, which is unbounded and outside your control. NOT for a genuinely missing input (that is a broken tree) nor for a checker whose subject moved (pristine-checkout-differential). Symptoms - "shutil.Error - No such file or directory" on a path you can no longer see; a failure that reproduces only under concurrency; a suite that goes red once and green next run; a red in a suite whose owner did not cause it. Covers proving the race deterministically without sleeps, telling a vanish from a real error, recording what was skipped, finding the writer population structurally, and locating the amplifier that turned one file into a whole directory.
---

# Two syscalls, one assumption

`os.scandir` then `copy2`. `glob` then `open`. `ls` then `sha256sum`. Every
bulk read of a directory is a listing followed by per-entry reads, and
between them any other process may unlink an entry. On a shared checkout —
CI runners, a repo two agents write, a test that drops a scratch file next to
the source — that window is hit routinely.

The library's default is to treat it as an error. `shutil.copytree` collects
per-file failures and raises `shutil.Error` **after** copying everything
else: the destination tree is already complete apart from a file that no
longer exists, and the raise is pure loss.

The instinct is to go find who deleted it and stop them. That is the wrong
end. The writers are a population you do not control and cannot enumerate
once and for all; the reader is one function.

## Trigger conditions

- An ENOENT / `FileNotFoundError` / `shutil.Error` naming a path that is not
  there when you go to look.
- A failure that reproduces only when two jobs run at once, and passes solo.
- A red that opened in one round/build and closed by itself in the next.
- Two copiers, snapshotters or uploaders of the same tree that disagree about
  one input — usually one has a swallowing `except` and the other does not.
- A test suite that writes a scratch file into the source tree rather than a
  temporary directory.
- A whole *directory* failing to collect/build/scan because of one file.

## Steps

1. **Read the failure body before anything else, and take the causing path
   out of it.** The path names the writer. Grep for its distinctive segment
   across the repo; if it is a formatted name (`_r438_%s.lang`), grep the
   invariant prefix. This costs one command and turns a race into a named
   pair of components.

2. **Reproduce it deterministically — no sleeps, no threads, no second
   process.** Find the seam the library already gives you between listing and
   reading and stage the unlink there:

   | reader | seam |
   |---|---|
   | `shutil.copytree` | the `ignore(dirpath, names)` callback — called after `scandir`, before the first copy |
   | a hand-written `os.walk` loop | monkeypatch the per-file call (`os.link`, `open`) |
   | `glob` + read | patch the read |

   Do **not** patch `shutil.copy2` to hook `copytree`: `copy_function=copy2`
   is a def-time default and your patch is never seen. A test that "cannot
   reproduce it" because of that will send you looking for a second bug.

3. **Distinguish a vanish from a real error by re-checking the path, not by
   the errno.** A dangling symlink reports the same ENOENT and its source
   *does* still exist. `os.path.lexists(src)` is the discriminator:

   ```python
   vanished = ("No such file or directory" in str(why)
               and not os.path.lexists(src))
   ```

   Anything else must keep raising, or the guard starts swallowing broken
   trees.

4. **Skip it, and record it.** Return the skipped paths and keep a
   module-level list for callers with nowhere to put a return value (a
   module-scope import-time call has no test to hand it to). A bare
   `except: pass` cannot tell "nothing vanished" from "we did not look",
   which is the whole reason the guard is worth writing down.

5. **Re-raise a mixed batch with the vanishes removed, chaining the
   original.** When one genuine failure shares the batch with a vanish, the
   reader should not have to filter noise out of the traceback.

6. **Check the OTHER readers of the same tree for the same input.** They are
   supposed to produce the same result; a race is where they most often do
   not. Typically one already survives — silently, in a fallback `except` —
   and the difference was never named. Make both say the same thing, and
   assert it in one test that runs both.

7. **Find the writer population structurally, not by grepping the one name
   you know.** A grep finds the instance you already have. The shape is "a
   write whose destination path is rooted at the live tree rather than a
   temporary directory", and the root can be a constant, an attribute, or a
   function-local `os.path.dirname(os.path.abspath(__file__))` that shares no
   token with anything. A small AST kind analysis — every path expression is
   `live`, `tmp` or `unknown`; `tmp` and `unknown` are never findings — is
   fifty lines and finds the rest.

8. **Subtract the writes the reader already ignores.** If the reader has an
   ignore list (`__pycache__`, `.git`, `node_modules`), a write landing
   inside one of those cannot cause the failure. Report it as a separate,
   lower class rather than dropping it or crying wolf. Import the ignore
   list from the reader; a second spelling of it is a drift waiting to
   happen.

9. **Name the AMPLIFIER separately from the trigger.** Ask what the failure
   cost: one item, or everything? Work done at import/collection/module scope
   turns a per-item failure into a whole-directory outage — one unreadable
   file becomes zero tests collected. Count the module-scope call sites and
   pin the count, so the next one arrives knowing.

10. **Repair the one writer that actually fired, and route the rest to their
    authors.** A tempdir costs nothing where an absolute path is accepted.
    For the remainder, an advisory author-time step (see
    `gate-attributes-what-the-change-introduced`) beats a whole-tree gate in
    one track's suite, which reddens for somebody who cannot see it.

11. **If the episode also produced a stale registry/attribution entry, close
    that with the MECHANISM, not the symptom.** "Went red once, cause
    unknown" is what the next reader has to redo.

## Pitfalls

- **Disciplining the writers instead of the reader.** You will not enumerate
  them all, and the twelfth arrives next month.
- **Catching the exception without recording the skip.** The next reader
  cannot distinguish a clean copy from a swallowed one.
- **Using errno alone.** Dangling symlinks and ENOENT-on-parent look the
  same and are not the same.
- **Patching a function that is bound as a default argument.** `copytree`'s
  `copy_function`, `dict.get`'s default factory, anything captured at `def`
  time.
- **Pinning a live count in a suite that another team owns half of.** The
  count moves under you and reddens for the wrong person; pin the *shape* of
  each finding and the reviewed exception list instead.
- **Assuming the retained logs know how often this happened.** They roll
  over; a race that closes by itself leaves one line and no record.

## Verification

```sh
# 1. The defect still exists in the library you are guarding against —
#    otherwise the guard is dead code.
pytest <suite> -k "still_raises_without_the_guard" -q

# 2. The guard skips and RECORDS, and the rest of the tree still arrives.
pytest <suite> -k "survives_a_file_deleted_mid_copy" -q

# 3. Negative controls: a clean run reports zero vanishes; a dangling
#    symlink still raises; a mixed batch re-raises only the real error.
pytest <suite> -k "clean_copy or dangling or non_vanish" -q

# 4. The other reader of the same tree agrees on the same input.
pytest <suite> -k "copiers_now_agree" -q

# 5. The writer scan finds the known instance, clears the repair, and does
#    not fire on a tempdir or a parameter-rooted path.
python3 <scanner> scan
pytest <suite> -k "flags_the_shape or clears_the_repair or parameter" -q

# 6. The amplifier count is pinned.
pytest <suite> -k "module_scope" -q
```

## Worked instance

Round 521 of this program. `languages/whence/tests/test_polarity.py` wrote
`_r438_suffix.lang` into the live `languages/whence/` directory and removed
it one subprocess later. Three modules under `harness/tests/` copy that
directory with `shutil.copytree` at **module scope**, and the driver runs the
whence and harness health checks concurrently — so at round 517 `os.scandir`
listed the name and `copy2` got ENOENT. Because the copy is at module scope
the raise was a pytest **collection** error: `Interrupted: 1 error during
collection`, 0 of 557 node ids, the whole directory. `test_tiering.py` — which
shells out to collect that directory — went red for the first time ever, so
the cross-track registry had no entry for it, `redattrib.py audit` raised
R001, and two `test_redattrib.py` nodes were red for rounds 518-521 in a
suite whose owner did not cause any of it.

The other copier, `swe/linkcopy.py:link_tree`, had survived the same input
since round 497 — `os.link` raises `OSError`, the `copy2` fallback raises
`OSError`, and the second handler passes — and said nothing about it. Two
copiers whose whole contract is to make the same sandbox, disagreeing on
"complete tree" versus "dead process".

A grep for `_r438` finds one file. The AST scan (`harness/swe/livewrite.py`)
found **15 live-rooted writes in 6 files** across two trees, 2 of them under
a `COPY_IGNORE` directory and therefore harmless. Written up in
`knowledge/round-521-the-copy-that-could-not-survive-a-vanished-file.md`.

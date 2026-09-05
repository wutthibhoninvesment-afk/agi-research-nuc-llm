#!/usr/bin/env python3
"""Round 517 (harness A): is the commit-time guard the one the tests describe?

`.git/hooks/pre-commit` is the only mechanism in this program that reaches
the AUTHOR of a defect. Everything else -- the four health checks, the RED
DEBT block, `logs/` -- runs after the agent process has exited, so a round
learns what it broke one to six rounds later, from a different track. Three
rounds extended the hook on exactly that reasoning: 499 (`wiring_audit
undeclared --staged`), 501 (`carryforward_check --staged-check`), 515
(`copyparity escapes --staged`), each after a check had gone red four to
seven times without its author ever seeing it.

The artefact that RUNS is `.git/hooks/pre-commit`, which is not in git.
Everything that TESTS it asserts about `escalationguard.hook_script()`, which
is. Between the two there are three independent ways to differ, and at round
517 nothing checked any of them:

  IDENTITY   the installed file may be absent (a fresh clone: all four
             guards silently off), foreign (someone else's hook), or an
             older GENERATION -- a round edited `hook_script()`, committed
             it, and never ran `install-hook`. Every existing test still
             passes in all three cases. Round 515's next-step #2.

  REFERENCE  even a byte-fresh hook is four hard-coded RELATIVE PATHS. Every
             step is wrapped in `[ -f "$top/<rel>" ]`, so moving or renaming
             a script does not break the hook -- it SILENTLY REMOVES the
             step. For step 1 that is `|| exit 0`, i.e. the only BLOCKING
             guard in the program disables itself and reports success. Not
             named by round 515; found by this module.

  ARGUMENT   the hook passes a verb (`check`, `undeclared --staged --quiet`)
             that the script's CLI must accept. A subcommand renamed on the
             Python side leaves a hook invoking the old name, and the three
             advisory steps end in `2>/dev/null || true`, so the usage error
             is discarded and the step is a no-op forever.

WHY THE PARSE READS THE INSTALLED FILE AND NOT THE GENERATOR
------------------------------------------------------------
`hook_script()` is a Python string this module could import and pull apart,
and doing so would be strictly easier. It would also measure the wrong
object: the generator is what the tests already cover. Every question here
is about the file on disk, so every answer is parsed out of the file on
disk, and `identity` is what connects the two.

WHY THE ARGUMENT CHECK IS STATIC
--------------------------------
The obvious check is to RUN each step and read its exit code. This module
does not, and the reason is a rule rather than a scruple: running a guard's
verb is running the guard. All four of today's steps happen to be read-only
`check`-shaped verbs, but that is a property of the four, not a contract the
hook imposes -- nothing stops a fifth step from writing a ledger. A module
whose job is to audit the guard must not be the thing that fires it.

So the verbs are resolved by reading the target script's argparse surface
with `ast`: the literals passed to `add_parser(...)` and to
`add_argument("--flag")`. That is exact for the four scripts in the hook
today and it FAILS OPEN -- a script whose CLI this cannot recognise is
reported `unknown`, never `broken`, because a static reader that guesses is
worse than one that abstains. `hookaudit probe` exists for the other case
and is deliberately not part of `audit`.

VERDICTS
--------
`identity`  ok | stale | foreign | absent | no-repo
`step`      live      script exists and every argument is declared
            missing   the script the hook names is not there (silent no-op)
            unknown   the script exists; its CLI could not be read statically
            broken    the script exists and rejects an argument the hook passes

Exit codes: `--strict` exits 1 on anything but `identity == ok` and every
step `live` or `unknown`. Without it, printing only, exit 0 -- the same
split every other instrument in this tree uses.

    python3 harness/hookaudit.py audit
    python3 harness/hookaudit.py audit --strict
    python3 harness/hookaudit.py steps
"""

import argparse
import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
#: Round 413's sanctioned form. `harness/swe/proc.py` copies a subtree into a
#: sandbox and an unguarded `dirname(dirname(...))` escapes it -- four rounds
#: have reddened `test_swe_copyparity_real_subject.py` writing the plain form
#: into a new file (464, 504, 507, 512).
REPO_ROOT = (os.environ.get("AGI_RESEARCH_ROOT")
             or os.path.dirname(HERE))

#: A line that INVOKES something through the hook's `$top` anchor. The first
#: token is the interpreter; `$top/<rel>` is the script; the rest is the
#: argument tail. `[ -f "$top/x" ]` and `if [ -f "$top/x" ]; then` are
#: excluded by requiring the token before the quote to be a command rather
#: than a test operand -- see `_NOT_A_COMMAND`.
_INVOKE_RE = re.compile(r'^\s*(\S+)\s+"\$top/([^"]+)"\s*(.*)$')
_NOT_A_COMMAND = frozenset(("[", "]", "if", "then", "fi", "-f", "-x", "test",
                            "#", "elif", "else"))
#: Shell noise that is not an argument to the script.
_TAIL_STOP = ("2>/dev/null", "2>&1", ">/dev/null", "||", "&&", ";", "|")


def _git(args, repo=REPO_ROOT):
    try:
        p = subprocess.run(["git"] + list(args), cwd=repo, timeout=20,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return p.returncode, p.stdout.decode("utf-8", "replace").strip()


def parse_steps(body):
    """Every invocation the hook body performs, in order.

    Returns [{order, python, script, args, blocking, raw}]. `blocking` is
    True only for a step that can refuse the commit -- `|| exit <non-zero>`.
    The three advisory steps end `|| true` by design (round 499: a gate here
    can refuse the commit of a round with no turns left to debug it).
    """
    out = []
    for raw in (body or "").splitlines():
        m = _INVOKE_RE.match(raw)
        if not m:
            continue
        interp, script, tail = m.group(1), m.group(2), m.group(3)
        if interp in _NOT_A_COMMAND or interp.startswith("#"):
            continue
        args = []
        for tok in tail.split():
            if tok in _TAIL_STOP or tok.startswith(("2>", ">", "<")):
                break
            args.append(tok)
        blocking = bool(re.search(r"\|\|\s*exit\s+([1-9]\d*)\b", raw))
        out.append({"order": len(out) + 1, "python": interp, "script": script,
                    "args": args, "blocking": blocking, "raw": raw.strip()})
    return out


def _argparse_surface(path):
    """(subcommands, options) a script's argparse declares, or None.

    Static: the string literals handed to `add_parser` and to `add_argument`.
    Returns None when the file cannot be read or parsed, which is what makes
    an unrecognisable CLI `unknown` rather than `broken`.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None
    subs, opts = set(), set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func,
                                                            ast.Attribute):
            continue
        name = node.func.attr
        if name not in ("add_parser", "add_argument"):
            continue
        for arg in node.args:
            if not (isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)):
                continue
            if arg.value.startswith("-"):
                opts.add(arg.value)
            elif name == "add_parser":
                subs.add(arg.value)
        # `choices=("a", "b")` on a positional is the other way a verb is
        # declared; harness/pristine_check.py does it that way.
        for kw in node.keywords:
            if kw.arg != "choices":
                continue
            if isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                for el in kw.value.elts:
                    if isinstance(el, ast.Constant) and isinstance(el.value,
                                                                   str):
                        subs.add(el.value)
    if not subs and not opts:
        return None
    return subs, opts


def classify_step(step, repo=REPO_ROOT):
    """`step` with `exists`, `verdict` and `why` filled in."""
    out = dict(step)
    path = os.path.join(repo, step["script"])
    out["exists"] = os.path.exists(path)
    if not out["exists"]:
        out["verdict"] = "missing"
        out["why"] = ("the hook invokes %s and there is no such file — the "
                      "`[ -f ]` guard around it makes this step a silent "
                      "no-op%s" % (step["script"],
                                   ", and this is the BLOCKING step"
                                   if step["blocking"] else ""))
        return out
    surface = _argparse_surface(path)
    if surface is None:
        out["verdict"] = "unknown"
        out["why"] = ("%s exists; its argparse surface could not be read "
                      "statically, so the arguments are unchecked"
                      % step["script"])
        return out
    subs, opts = surface
    bad = []
    for tok in step["args"]:
        if tok.startswith("--"):
            if tok.split("=")[0] not in opts:
                bad.append(tok)
        elif tok.startswith("-") and len(tok) > 1:
            if tok not in opts:
                bad.append(tok)
        elif subs and tok not in subs:
            bad.append(tok)
    if bad:
        out["verdict"] = "broken"
        out["why"] = ("%s does not declare %s — the hook passes it and the "
                      "step %s" % (step["script"], ", ".join(bad),
                                   "refuses every commit" if step["blocking"]
                                   else "is a silent no-op (`2>/dev/null || "
                                        "true` eats the usage error)"))
        return out
    out["verdict"] = "live"
    out["why"] = "%s exists and declares %s" % (
        step["script"], " ".join(step["args"]) or "(no arguments)")
    return out


def identity(repo=REPO_ROOT, eg=None):
    """(state, path, why). `ok` / `stale` / `foreign` / `absent` / `no-repo`.

    STALE IS COMPARED AGAINST A RE-GENERATION WITH THE INSTALLED HOOK'S OWN
    INTERPRETER. `hook_script()` defaults `python` to the literal `python3`,
    and `install_hook(python=...)` is a real parameter two tests already
    use, so a byte comparison against the default would call a hook
    installed with `.venv/bin/python` stale on a difference the installer
    was asked for. The interpreter is read back out of the file's first
    invocation line and fed to the generator, so the comparison is about the
    POLICY -- the steps, their order, their arguments, the comments that say
    why -- and nothing else.
    """
    if eg is None:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import escalationguard as eg          # noqa: F811
    rc, _ = _git(["rev-parse", "--git-dir"], repo=repo)
    if rc != 0:
        return "no-repo", None, "%s is not a git checkout" % repo
    state, path = eg.hook_status(repo=repo)
    if state == "absent":
        return ("absent", path,
                "no pre-commit hook is installed, so all %d guard steps are "
                "off and every test that asserts about hook_script() still "
                "passes — run `python3 harness/escalationguard.py "
                "install-hook`" % len(parse_steps(eg.hook_script())))
    if state == "foreign":
        return ("foreign", path,
                "the installed hook does not carry %r, so it is not ours and "
                "install-hook refuses to overwrite it" % eg.HOOK_MARKER)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            body = fh.read()
    except OSError as exc:
        return "foreign", path, "unreadable: %s" % exc
    steps = parse_steps(body)
    interp = steps[0]["python"] if steps else None
    want = eg.hook_script(python=interp)
    if body == want:
        return ("ok", path,
                "byte-identical to escalationguard.hook_script(python=%r)"
                % interp)
    return ("stale", path,
            "installed hook is OURS but is not what hook_script(python=%r) "
            "generates (%d bytes installed, %d generated) — a round edited "
            "the generator and did not run `install-hook`, so the tests "
            "describe a hook that is not the one running"
            % (interp, len(body), len(want)))


def audit(repo=REPO_ROOT, eg=None):
    """The whole verdict: identity plus one row per installed step."""
    state, path, why = identity(repo=repo, eg=eg)
    body = ""
    if path and state in ("ok", "stale", "foreign"):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        except OSError:
            body = ""
    steps = [classify_step(s, repo=repo) for s in parse_steps(body)]
    return {"identity": state, "path": path, "why": why, "steps": steps,
            "blocking": [s["order"] for s in steps if s["blocking"]],
            "counts": {v: len([s for s in steps if s["verdict"] == v])
                       for v in ("live", "missing", "unknown", "broken")}}


def is_clean(rep):
    """The `--strict` predicate, in one place so the CLI and the tests share
    it. `unknown` is not a failure: the static reader abstaining is not the
    hook being wrong."""
    return (rep["identity"] == "ok"
            and rep["counts"]["missing"] == 0
            and rep["counts"]["broken"] == 0)


def render(rep):
    lines = ["hookaudit: identity %s — %s" % (rep["identity"], rep["why"])]
    for s in rep["steps"]:
        lines.append("  step %d  %-8s %-9s %s %s"
                     % (s["order"], s["verdict"],
                        "BLOCKING" if s["blocking"] else "advisory",
                        s["script"], " ".join(s["args"])))
    c = rep["counts"]
    lines.append("hookaudit: %d step(s) — %d live, %d missing, %d broken, "
                 "%d unknown; %d blocking; identity %s"
                 % (len(rep["steps"]), c["live"], c["missing"], c["broken"],
                    c["unknown"], len(rep["blocking"]), rep["identity"]))
    return "\n".join(lines)


def cmd_audit(args):
    rep = audit(repo=args.repo)
    print(render(rep))
    return 0 if (not args.strict or is_clean(rep)) else 1


def cmd_steps(args):
    rep = audit(repo=args.repo)
    for s in rep["steps"]:
        print("%d\t%s\t%s\t%s\t%s" % (s["order"], s["verdict"],
                                      "blocking" if s["blocking"] else
                                      "advisory", s["script"],
                                      " ".join(s["args"])))
    return 0


def cmd_status(args):
    state, path, why = identity(repo=args.repo)
    print("hookaudit: %s\t%s\n  %s" % (state, path, why))
    return 0 if (not args.strict or state == "ok") else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=REPO_ROOT)
    sub = ap.add_subparsers(dest="cmd")
    for name, help_ in (("audit", "identity + every step"),
                        ("steps", "one tab-separated row per step"),
                        ("status", "identity only")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--strict", action="store_true",
                       help="exit 1 when the installed hook is not the one "
                            "hook_script() generates")
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0
    return {"audit": cmd_audit, "steps": cmd_steps,
            "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

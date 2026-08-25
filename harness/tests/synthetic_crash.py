"""A synthetic interpreter bug for tests that need a real crash.

Until round 9 the harness tests used a 400-deep parenthesised expression to
crash the Whence parser with RecursionError. Whence v0.4 turned that (and
every other host recursion the fuzzer could find) into a clean ParseError /
miss — fuzz campaigns report 0 crash signatures — so tests that exercise the
*crash-handling* paths of the SWE loop now inject a bug instead of hoping
for one: `deep_eq` (structural `==`) is replaced by a function that recurses
forever. It is compiled under the whence root so `fuzz._whence_frames`
attributes the frames to Whence, exactly as a real interpreter bug would.
"""
import os
import sys

CRASH_PROGRAM = "let p = [1] == [1]\n"      # list == list goes through deep_eq


def install(interp_module_name, root):
    """Replace `deep_eq` in the named interp module (e.g. 'whence.interp',
    'whence_tool.interp') with an infinitely recursive one. Returns the
    original for restoring."""
    mod = sys.modules[interp_module_name]
    src = "def deep_eq(l, r):\n    return deep_eq(l, r)\n"
    ns = {}
    exec(compile(src, os.path.join(root, "whence", "interp.py"), "exec"), ns)
    original = mod.deep_eq
    mod.deep_eq = ns["deep_eq"]
    return original

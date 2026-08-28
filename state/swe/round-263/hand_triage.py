"""Round 263 (SWE-loop D): direct-construction triage of the 16 lexer.py
mutation survivors that the broader fast tier (state/swe/round-263/
triage_lexer_survivors.py) ALSO could not kill.

For each survivor: build the mutated lexer.py as its own module object
(distinct name, no file write needed), tokenize (a) every git-tracked
examples/*.lang file and (b) a battery of hand-crafted boundary-condition
snippets targeting the specific mutated line, and diff the resulting
(type, value) token sequences against the unmutated lexer. A real semantic
difference on ANY input is a genuine test gap; SAME on everything tried is
evidence (not proof) of equivalence, same epistemic status round 220's
`equivalence.py` and round 233's PMap analysis both use explicitly.
"""
import importlib.util
import json
import sys

sys.path.insert(0, "/home/pgain/agi-research-nuc-llm/harness")
from swe import mutation as MU

WHENCE = "/home/pgain/agi-research-nuc-llm/languages/whence"
sys.path.insert(0, WHENCE)

with open(WHENCE + "/whence/lexer.py", encoding="utf-8") as f:
    ORIG_SRC = f.read()

SURVIVOR_IDS = [
    "lexer.py:40:arith#14", "lexer.py:58:const#33", "lexer.py:61:bool#35",
    "lexer.py:96:arith#46", "lexer.py:116:const#52", "lexer.py:148:const#59",
    "lexer.py:159:const#63", "lexer.py:67:cmp#68", "lexer.py:90:cmp#76",
    "lexer.py:91:const#77", "lexer.py:138:const#89", "lexer.py:90:arith#94",
    "lexer.py:124:const#101", "lexer.py:127:cmp#102", "lexer.py:127:arith#109",
    "lexer.py:127:const#112",
]

all_mutants = {m.id: m for m in MU.generate(ORIG_SRC, "whence/lexer.py")}


def load_module(name, source):
    spec = importlib.util.spec_from_loader(name, loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(source, name, "exec"), mod.__dict__)
    return mod


orig = load_module("lexer_orig", ORIG_SRC)

import os
examples_dir = WHENCE + "/examples"
example_files = sorted(f for f in os.listdir(examples_dir) if f.endswith(".lang"))
# only the git-tracked ones (excludes the Hermes-owned untracked files,
# per round 215's list_example_files discipline)
import subprocess
tracked = set(subprocess.run(["git", "ls-files", "examples/"], cwd=WHENCE,
                             capture_output=True, text=True).stdout.split())
example_files = [f for f in example_files if "examples/" + f in tracked]

SNIPPETS = {
    "leading_blank_line": "\nlet x = 1\n",
    "leading_blank_lines_x3": "\n\n\nlet x = 1\n",
    "kw_true_then_stmt": "let a = true\nlet b = 2\n",
    "kw_false_then_stmt": "let a = false\nlet b = 2\n",
    "kw_if_as_last_before_newline": "if a { 1 } else { 2 }\nlet b = 3\n",
    "kw_miss_then_stmt": "let a = miss\nlet b = 2\n",
    "kw_check_then_stmt": "check a == 1\nlet b = 2\n",
    "kw_let_bare_then_stmt": "let a = 1\nlet b = 2\n",
    "comment_slash_then_code": "# a comment\nlet x = 1\n",
    "string_with_backslash_escape": '"a\\nb\\tc"\n',
    "string_then_newline": '"hello"\nlet x = 1\n',
    "number_float": "3.14\nlet x = 1\n",
    "number_int_boundary": "0\n1\n9\n10\n99\n100\n",
    "nested_brackets_atrec": "@{a: 1, b: [1, 2, 3]}\n",
    "paren_call_multiline": "f(\n  1,\n  2\n)\n",
    "op_lt_lte": "a < b\na <= b\na > b\na >= b\n",
    "op_eq_neq": "a == b\na != b\n",
    "close_brackets_mismatched_extra": "1)\n",  # extra close, no open
    "close_brackets_all_kinds": "f(1)[0]{2}\n",
    "and_or_not_rescue_continuation": "a and\nb or\nnot c\n",
    "arrow_and_at_brace": "f -> g\n@{x: 1}\n",
    # EOF-boundary / same-line-after-token snippets added for round 263's
    # deeper triage pass -- targeting each mutated line's own edge condition
    # directly rather than relying on "normal" program shapes to happen to hit it.
    "comment_no_trailing_newline": "let x = 1\n# trailing comment, no newline after",
    "number_bare_at_absolute_eof": "let x = 1\n42",
    "number_dot_no_digit_at_eof": "let x = 1\n5.",
    "number_dot_one_digit_at_eof": "let x = 1\n5.1",
    "string_backslash_at_absolute_eof": '"\\',
    "string_then_op_same_line": '"ab" + 1\n',
    "two_char_op_then_op_same_line": "a == b + 1\n",
    "one_char_op_then_op_same_line": "a + b + 1\n",
    "close_paren_then_op_same_line": "(a) + 1\n",
    "string_bad_escape_then_op_same_line": None,  # filled below (needs try/except at lex time)
}
del SNIPPETS["string_bad_escape_then_op_same_line"]


def tok_seq(mod, src):
    try:
        toks = mod.tokenize(src)
    except Exception as e:
        return ("EXC", type(e).__name__, str(e))
    return tuple((t.type, t.value, t.line, t.col) for t in toks)


results = []
for mid in SURVIVOR_IDS:
    m = all_mutants[mid]
    mutmod = load_module("lexer_mut_%s" % mid.replace(":", "_").replace("#", "_"), m.source)
    diffs = []
    for fname in example_files:
        with open(os.path.join(examples_dir, fname), encoding="utf-8") as f:
            src = f.read()
        a, b = tok_seq(orig, src), tok_seq(mutmod, src)
        if a != b:
            diffs.append(("example:" + fname, a, b))
    for sname, src in SNIPPETS.items():
        a, b = tok_seq(orig, src), tok_seq(mutmod, src)
        if a != b:
            diffs.append(("snippet:" + sname, a, b))
    status = "DIFFERS" if diffs else "same-on-all-tried"
    results.append({"id": mid, "line": m.lineno, "op": m.op, "description": m.description,
                    "status": status, "n_diffs": len(diffs),
                    "first_diff": diffs[0][0] if diffs else None})
    print("%-20s %-28s %s%s" % (status, mid, m.description,
                                 (" (" + diffs[0][0] + ")") if diffs else ""))

with open("/home/pgain/agi-research-nuc-llm/state/swe/round-263/hand-triage.json", "w") as f:
    json.dump(results, f, indent=1)

print()
print("examples tested:", example_files)
print("snippets tested:", list(SNIPPETS))

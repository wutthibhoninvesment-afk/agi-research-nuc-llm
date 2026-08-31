#!/usr/bin/env python3
"""trigger_eval.py — measure whether SKILL.md descriptions actually trigger.

Gives a *fresh* Claude Code instance (``claude -p``) a task phrased without
the skill's name and records which skills it invoked. Aggregates per-skill
precision/recall over a labelled case file, so description edits can be
evaluated instead of guessed.

Usage:
    python3 trigger_eval.py CASES.json --skills DIR [--skills DIR ...]
        [--mode native|catalog|body] [--model sonnet[,haiku,...]] [--repeats 1]
        [--concurrency 4] [--timeout 150] [--json OUT.json] [--only ID,ID]
        [--distractors DIR] [--n-distractors N] [--distractor-seed S]
        [--body-tools "Skill,Read"] [--paired] [--transcripts DIR]
        [--canary CANARY.json] [--baseline PRIOR.json]
        [--protocol strict|default] [--audit REPORTS_DIR] [--also-cases FILE]

Modes:
    native   (default) Stage the skills in a temp project's ``.claude/skills/``
             and run ``claude -p`` there with only the Skill tool enabled; a
             skill counts as *fired* when the model emits a ``Skill`` tool_use
             for it. This exercises the real skill index + selection path.
             The host's user-level skills are present too and act as natural
             distractors (they are listed in the report).
    catalog  Put the catalog (name + description of every skill) in the
             prompt and ask for a JSON list of the skills the model would
             invoke. No tools, cheaper, but tests the description text in
             isolation rather than the real selection path.
    body     Body-following: the probe is told to DO the task (tools from
             ``--body-tools``, default Skill+Read; deliverable goes in the
             reply). Besides which skills fired, records which *staged
             bundled files* were read (Read paths / Bash commands touching
             ``.claude/skills/…``) and which case-supplied ``body.evidence``
             regexes match the transcript — i.e. did the agent follow the
             loaded instructions, not just load them. A Read whose
             tool_result errored does NOT count as a file read; denied /
             failed reads are reported separately (``files_failed``).
             ``body.evidence_min: N`` makes a case count as followed when
             ≥N of its evidence regexes match (default: all — but
             all-or-nothing penalizes tasks where a marker can be
             legitimately out of scope).

Multi-model: ``--model sonnet,haiku`` runs every case per model and prints
one report per model plus a per-skill recall comparison table.

Fire rates: with ``--repeats N`` the report adds a per-case rate table
splitting *all-expected-fired* (every expected skill fired; for negatives:
nothing fired) from *exact* (fired set == expected set) — a case can fire
reliably yet rarely be exact because a sibling co-fires. Small probe
models are unreadable at n=1; decide from rates, not single runs.

``--paired`` (requires ``--distractors``): every probe runs twice — once
with only your skills staged ("plain") and once with the distractors
staged too ("staged") — and the report adds a per-case paired table with
a suppression verdict: a case whose fire count drops when siblings are
staged *without* the sibling firing is SUPPRESSED (the selector fired
neither contender); if the sibling fired while yours went missing it is
DISPLACED. This automates the round-21 paired diagnostic.

``--transcripts DIR`` writes every probe's full transcript (all assistant
text blocks + tool touches) to ``DIR/<model>[-<arm>]-<case>-<k>.txt`` —
the JSON keeps only a 4000-char tail, which is too little to diagnose a
long body-mode run.

``--baseline PRIOR.json`` compares this run's per-case rates against a
prior ``--json`` report (per model when both have the model) and prints a
delta table with verdicts: REGRESSED / IMPROVED (fire count moved by ≥2
runs at equal n, else rate moved ≥0.5), CO-FIRE (fires as before but exact
dropped — a sibling now co-fires), noise? (smaller move: re-probe the case
at higher n before editing), same, new / dropped. This is iteration-loop
step 4 ("did any sibling regress after my edit?") as a table instead of
two reports read side by side. Only meaningful within a canary-checked
instrument (see below).

``--canary CANARY.json`` runs frozen sentinel case(s) against stored
acceptance bands and exits 0 (in band) / 1 (drift) / 2 (inconclusive):
an instrument-drift tripwire to run at session start BEFORE trusting any
cross-round comparison (the host skill population shifts under the
benchmark). File: ``[{"case": "fmk-near", "model": "sonnet",
"repeats": 4, "min_rate": 0.75, "max_rate": 1.0, "mode": "native"}]``
(rate = all-expected-fired over non-errored runs).

Controlled distractors: ``--distractors DIR`` (repeatable, recursive,
lenient about broken frontmatter) stages foreign skills alongside yours —
``--n-distractors N --distractor-seed S`` picks a deterministic sample.
Fires on staged distractors are reported separately from host "foreign"
fires, and *displacement* (an expected skill missing while a staged
distractor fired) is counted.

``--audit REPORTS_DIR`` (offline, no probes) answers "has every skill's
CURRENT description been probed?": every ``--json`` report since v4.2
stores a digest of each staged description, so the audit finds, per skill,
the newest report under REPORTS_DIR with a non-errored probe of a case
expecting it and reports ``probed`` (digest matches the description on
disk), ``STALE`` (edited since), ``unverified`` (pre-4.2 report, no
digest) or ``never``, plus the case counts (positives / body cases; the
floor is 3 positives). Exit 1 unless every skill is ``probed`` and at the
floor — the check that would have caught three skills shipped or
rewritten without a probe. ``--also-cases FILE`` merges more case files
(e.g. the body cases) into any run.

Probe protocol: ``--protocol`` defaults to ``strict`` since v4.2 (the
``SKILLS=`` line is invalid without a preceding Skill call; measured to
remove the one-turn declared-not-invoked artifact). ``default`` is the
pre-4.2 prompt, kept so older reports stay reproducible; ``--baseline``
prints a NOTE when the two reports' protocols differ.

Case file (JSON):
    [{"id": "gte-1", "prompt": "…indirect task…", "expect": ["skill-name"],
      "note": "optional"}, {"id": "neg-1", "prompt": "…", "expect": []},
     {"id": "body-1", "prompt": "…real task…", "expect": ["skill-name"],
      "body": {"files": ["skill-name/references/x.md"],
               "evidence": ["regex matched against transcript", "…"]}}]
    ``expect`` is the set of *our* skills that should fire; skills outside
    the staged set are reported as "foreign" fires but never counted as
    false positives (the host's own skills are out of our control).
    ``body`` is only used by ``--mode body``; ``files`` are staged-relative
    paths (``<skill>/<relpath>``), ``evidence`` are case-insensitive regexes.

Exit codes: 0 = ran and every case matched; 1 = ran with mismatches;
2 = usage / IO / runner problem.
"""

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skill_lint import parse_frontmatter  # noqa: E402

PROBE_SYSTEM = (
    "Skill-selection probe: if any available skill applies to the user's task, "
    "invoke it via the Skill tool FIRST (invoke every skill that applies, one "
    "at a time). As soon as the skill content has loaded, or if no skill "
    "applies, reply with exactly one line: SKILLS=<comma-separated skill "
    "names you invoked, or NONE> and stop. Do not perform the task itself."
)

PROBE_SYSTEM_STRICT = PROBE_SYSTEM + (
    " The SKILLS= line is valid ONLY after the Skill tool has actually been "
    "called for every skill it names; writing the line without a preceding "
    "Skill tool call is an invalid answer. Decide, call the tool, then answer."
)

PROTOCOLS = {"default": PROBE_SYSTEM, "strict": PROBE_SYSTEM_STRICT}

CATALOG_PROMPT = (
    "You are an agent with the following skills available. Each entry is a "
    "skill name followed by its description; a skill's full instructions are "
    "loaded only if you choose to invoke it.\n\n{catalog}\n\n"
    "A user sends this task:\n\n<task>\n{task}\n</task>\n\n"
    "Which skills would you invoke before starting the task? Reply with ONLY a "
    "JSON object of the form {{\"skills\": [\"name\", ...]}} — an empty list if "
    "none applies. No prose."
)

BODY_SYSTEM = (
    "Skill-following probe: if any available skill applies to the user's "
    "task, invoke it via the Skill tool FIRST, then FOLLOW the loaded "
    "instructions — including reading any bundled reference files they "
    "point to — while you carry out the task. You have no write access: "
    "deliver all work product (code, analysis, rewritten text) directly in "
    "your reply. Be concrete; show real code where the task needs it."
)

SKILLS_LINE_RE = re.compile(r"SKILLS\s*=\s*(.+)", re.I)
SKILL_PATH_RE = re.compile(r"\.claude/skills/([^\s'\"`)\]]+)")
DENIED_RE = re.compile(r"permission|denied|haven'?t granted|not.{0,20}allowed", re.I)


def _result_text(content):
    """Flatten a tool_result ``content`` (string, or list of text blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict))
    return ""


# ----------------------------------------------------------------- catalog --
def load_catalog(skill_dirs, lenient=False, recursive=False):
    """Return [(name, description, path)] for every SKILL.md under the given
    skill directories (each may be a skill dir or a directory of them).
    ``recursive`` also finds skills nested deeper (category/skill/SKILL.md);
    ``lenient`` skips (with a stderr note) skills whose frontmatter does not
    parse instead of raising — for wild corpora used as distractors."""
    out = []
    skipped = []
    for root in skill_dirs:
        root = os.path.expanduser(root)
        candidates = []
        if os.path.isfile(os.path.join(root, "SKILL.md")):
            candidates.append(root)
        elif os.path.isdir(root):
            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
                    if "SKILL.md" in filenames:
                        candidates.append(dirpath)
                        dirnames[:] = []  # a skill dir's subdirs are bundled files
            else:
                for e in sorted(os.listdir(root)):
                    d = os.path.join(root, e)
                    if os.path.isfile(os.path.join(d, "SKILL.md")):
                        candidates.append(d)
        for d in candidates:
            with open(os.path.join(d, "SKILL.md"), encoding="utf-8") as f:
                fields, _, err = parse_frontmatter(f.read())
            if err:
                if lenient:
                    skipped.append(d)
                    continue
                raise ValueError("%s: %s" % (d, err))
            name = fields.get("name") or os.path.basename(os.path.abspath(d))
            out.append((name, fields.get("description", ""), os.path.abspath(d)))
    if skipped:
        print("trigger-eval: skipped %d unparseable skill(s): %s"
              % (len(skipped), ", ".join(os.path.basename(s) for s in skipped)),
              file=sys.stderr)
    return out


def pick_distractors(pool, ours_names, n, seed):
    """Deterministically sample ``n`` distractor skills from ``pool``
    (name-deduped, ours excluded, sorted by name first so the sample depends
    only on names + seed). ``n < 0`` keeps the whole pool."""
    seen = set(ours_names)
    uniq = []
    for c in sorted(pool, key=lambda c: c[0]):
        if c[0] not in seen:
            seen.add(c[0])
            uniq.append(c)
    if 0 <= n < len(uniq):
        uniq = sorted(random.Random(seed).sample(uniq, n), key=lambda c: c[0])
    return uniq


def load_cases(path):
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    if not isinstance(cases, list):
        raise ValueError("case file must be a JSON list")
    seen = set()
    for i, c in enumerate(cases):
        for k in ("id", "prompt", "expect"):
            if k not in c:
                raise ValueError("case %d missing %r" % (i, k))
        if c["id"] in seen:
            raise ValueError("duplicate case id %r" % c["id"])
        seen.add(c["id"])
        if not isinstance(c["expect"], list):
            raise ValueError("case %r: expect must be a list" % c["id"])
        b = c.get("body")
        if b is not None:
            if not isinstance(b, dict):
                raise ValueError("case %r: body must be an object" % c["id"])
            for k in ("files", "evidence"):
                if not isinstance(b.get(k, []), list):
                    raise ValueError("case %r: body.%s must be a list" % (c["id"], k))
            for e in b.get("evidence", []):
                try:
                    re.compile(e)
                except re.error as ex:
                    raise ValueError("case %r: bad evidence regex %r: %s"
                                     % (c["id"], e, ex))
            em = b.get("evidence_min")
            if em is not None:
                if not isinstance(em, int) or isinstance(em, bool) \
                        or not 0 <= em <= len(b.get("evidence", [])):
                    raise ValueError(
                        "case %r: evidence_min must be an int in "
                        "[0, len(evidence)]" % c["id"])
    return cases


# ------------------------------------------------------------------ runner --
def default_runner(argv, cwd, timeout_s):
    """Run argv; return (rc, stdout, stderr). CLAUDE* env vars are stripped so
    a nested Claude Code session does not inherit the parent's context."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    try:
        p = subprocess.run(list(argv), capture_output=True, text=True, cwd=cwd,
                           timeout=timeout_s, env=env)
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ds" % timeout_s
    except OSError as e:
        return 127, "", str(e)
    return p.returncode, p.stdout, p.stderr


# ----------------------------------------------------------------- parsing --
def parse_stream(text):
    """Parse ``--output-format stream-json`` output into a probe record:
    {"invoked": [names in order], "declared": [names from SKILLS= line],
     "available": [slash commands the session listed], "reads": [Read paths
     attempted], "reads_failed": [{"path", "reason", "denied"} for Reads
     whose tool_result errored — permission denials flagged], "bash":
     [Bash commands], "texts": [every assistant text block],
     "cost_usd", "turns", "error"}."""
    rec = {"invoked": [], "declared": None, "available": [], "cost_usd": 0.0,
           "turns": 0, "error": None, "final_text": "", "reads": [],
           "reads_failed": [], "bash": [], "texts": []}
    pending_reads = {}  # tool_use id -> Read file_path, for result matching
    saw_result = False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            rec["available"] = list(ev.get("slash_commands") or [])
        elif t == "assistant":
            for b in (ev.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use" and b.get("name") == "Skill":
                    name = (b.get("input") or {}).get("skill")
                    if name:
                        # plugin skills arrive as "plugin:skill" — keep the tail
                        rec["invoked"].append(name.split(":")[-1])
                elif b.get("type") == "tool_use" and b.get("name") == "Read":
                    p = (b.get("input") or {}).get("file_path")
                    if p:
                        rec["reads"].append(p)
                        if b.get("id"):
                            pending_reads[b["id"]] = p
                elif b.get("type") == "tool_use" and b.get("name") == "Bash":
                    cmd = (b.get("input") or {}).get("command")
                    if cmd:
                        rec["bash"].append(cmd)
                elif b.get("type") == "text":
                    rec["final_text"] = b.get("text", "")
                    rec["texts"].append(b.get("text", ""))
        elif t == "user":
            for b in (ev.get("message") or {}).get("content") or []:
                if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                    continue
                p = pending_reads.get(b.get("tool_use_id"))
                if p is not None and b.get("is_error"):
                    txt = _result_text(b.get("content"))
                    rec["reads_failed"].append(
                        {"path": p, "reason": txt[:160],
                         "denied": bool(DENIED_RE.search(txt))})
        elif t == "result":
            saw_result = True
            rec["cost_usd"] = float(ev.get("total_cost_usd") or 0.0)
            rec["turns"] = int(ev.get("num_turns") or 0)
            if ev.get("is_error") or ev.get("subtype") not in (None, "success"):
                rec["error"] = "result subtype=%s: %s" % (
                    ev.get("subtype"), str(ev.get("result"))[:200])
            if not rec["final_text"] and isinstance(ev.get("result"), str):
                rec["final_text"] = ev["result"]
    if not saw_result and rec["error"] is None:
        rec["error"] = "no result event in stream output"
    rec["declared"] = parse_declared(rec["final_text"])
    return rec


def parse_declared(text):
    """Extract the SKILLS=… line into a list (NONE → [])."""
    m = SKILLS_LINE_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).strip().strip("`").strip()
    if raw.upper().startswith("NONE"):
        return []
    return [s.strip().strip("`'\"") for s in raw.split(",") if s.strip()]


def parse_catalog_answer(text):
    """Extract {"skills": [...]} from a catalog-mode reply; tolerant of fences."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, list):
        return None
    return [str(s).strip() for s in skills]


# ------------------------------------------------------------------ probes --
def stage_skills(catalog, project_dir):
    """Copy every catalog skill into project_dir/.claude/skills/<name>/."""
    dest_root = os.path.join(project_dir, ".claude", "skills")
    os.makedirs(dest_root, exist_ok=True)
    for name, _, path in catalog:
        dest = os.path.join(dest_root, name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(path, dest)
    return dest_root


def native_argv(executable, model, prompt, budget_usd, protocol="default"):
    return [executable, "-p", "--output-format", "stream-json", "--verbose",
            "--model", model, "--tools", "Skill", "--permission-mode", "dontAsk",
            "--no-session-persistence", "--setting-sources", "project",
            "--max-budget-usd", str(budget_usd),
            "--append-system-prompt", PROTOCOLS[protocol], prompt]


def body_argv(executable, model, prompt, budget_usd, tools):
    return [executable, "-p", "--output-format", "stream-json", "--verbose",
            "--model", model, "--tools", tools, "--permission-mode", "dontAsk",
            "--no-session-persistence", "--setting-sources", "project",
            "--max-budget-usd", str(budget_usd),
            "--append-system-prompt", BODY_SYSTEM, prompt]


def staged_files_touched(rec):
    """Staged-skill-relative paths (``<skill>/<relpath>``) the probe READ,
    via Read file_paths or Bash command text; deduped, order kept. A Read
    whose tool_result errored (permission denial, missing file) is NOT a
    read — v3 counted attempts, so a denied reference registered as
    consulted. Bash touches stay attempt-level (no per-path result to
    match). Failed staged reads are listed by staged_files_failed()."""
    fail_n = {}
    for f in rec.get("reads_failed", []):
        fail_n[f["path"]] = fail_n.get(f["path"], 0) + 1
    reads = rec.get("reads", [])
    hits = []
    for p in reads:
        if reads.count(p) <= fail_n.get(p, 0):   # every attempt errored
            continue
        m = SKILL_PATH_RE.search(p)
        if m:
            hits.append(m.group(1).rstrip("/."))
    for cmd in rec.get("bash", []):
        for m in SKILL_PATH_RE.finditer(cmd):
            hits.append(m.group(1).rstrip("/."))
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def staged_files_failed(rec):
    """Failed Reads of staged files, as [{"file": <skill-relative>,
    "reason", "denied"}] — denied=True means the error text looks like a
    permission denial rather than e.g. a missing file."""
    out = []
    for f in rec.get("reads_failed", []):
        m = SKILL_PATH_RE.search(f["path"])
        if m:
            out.append({"file": m.group(1).rstrip("/."),
                        "reason": f["reason"], "denied": f["denied"]})
    return out


def catalog_argv(executable, model, prompt, budget_usd):
    return [executable, "-p", "--output-format", "json", "--model", model,
            "--tools", "", "--no-session-persistence", "--setting-sources", "project",
            "--max-budget-usd", str(budget_usd), prompt]


def render_catalog(catalog):
    return "\n".join("- %s: %s" % (n, d) for n, d, _ in catalog)


def run_probe(case, mode, catalog, project_dir, runner, executable, model,
              timeout_s, budget_usd, distractor_names=frozenset(),
              body_tools="Skill,Read", arm=None, transcript_path=None,
              protocol="default"):
    """Run one probe; return a record with fired skills and diagnostics.
    ``arm`` tags the result ("plain"/"staged") for --paired runs;
    ``transcript_path`` writes the full transcript there; ``protocol``
    picks the native-mode probe system prompt (see PROTOCOLS)."""
    if mode in ("native", "body"):
        if mode == "native":
            argv = native_argv(executable, model, case["prompt"], budget_usd,
                               protocol)
        else:
            argv = body_argv(executable, model, case["prompt"], budget_usd,
                             body_tools)
        rc, out, err = runner(argv, project_dir, timeout_s)
        rec = parse_stream(out)
        if rc != 0:
            rec["error"] = "rc=%d: %s" % (rc, (err or out)[-300:])
        fired = rec["invoked"]
    else:
        prompt = CATALOG_PROMPT.format(catalog=render_catalog(catalog),
                                       task=case["prompt"])
        argv = catalog_argv(executable, model, prompt, budget_usd)
        rc, out, err = runner(argv, project_dir, timeout_s)
        rec = {"invoked": [], "declared": None, "available": [], "cost_usd": 0.0,
               "turns": 0, "error": None, "final_text": ""}
        if rc != 0:
            rec["error"] = "rc=%d: %s" % (rc, (err or out)[-300:])
        else:
            try:
                data = json.loads(out)
                rec["cost_usd"] = float(data.get("total_cost_usd") or 0.0)
                rec["turns"] = int(data.get("num_turns") or 0)
                rec["final_text"] = data.get("result") or ""
                if data.get("is_error"):
                    rec["error"] = "cli error: %s" % str(data.get("result"))[:200]
            except ValueError:
                rec["error"] = "non-JSON output: %r" % out[:200]
        ans = parse_catalog_answer(rec["final_text"])
        if ans is None and rec["error"] is None:
            rec["error"] = "unparseable answer: %r" % rec["final_text"][:200]
        fired = ans or []
    ours = {n for n, _, _ in catalog}
    # dedupe, keep order
    seen, fired_u = set(), []
    for f in fired:
        if f not in seen:
            seen.add(f)
            fired_u.append(f)
    res = {"id": case["id"], "prompt": case["prompt"], "expect": list(case["expect"]),
           "fired": [f for f in fired_u if f in ours],
           "distractors": [f for f in fired_u if f in distractor_names],
           "foreign": [f for f in fired_u
                       if f not in ours and f not in distractor_names],
           "declared": rec.get("declared"), "error": rec.get("error"),
           "cost_usd": rec.get("cost_usd", 0.0), "turns": rec.get("turns", 0),
           "available": rec.get("available", []), "model": model, "arm": arm}
    if mode == "body":
        spec = case.get("body") or {}
        exp_files = list(spec.get("files") or [])
        exp_ev = list(spec.get("evidence") or [])
        transcript = "\n".join(t for t in rec.get("texts", []) if t) \
            or rec.get("final_text", "")
        files_read = staged_files_touched(rec)
        res["body"] = {
            "files_read": files_read,
            "files_failed": staged_files_failed(rec),
            "files_expected": exp_files,
            "files_hit": [f for f in exp_files if f in files_read],
            "evidence_expected": exp_ev,
            "evidence_min": spec.get("evidence_min", len(exp_ev)),
            "evidence_hit": [e for e in exp_ev
                             if re.search(e, transcript, re.I | re.S)],
            "transcript_chars": len(transcript),
            # kept so a missed evidence marker can be diagnosed from the JSON
            "transcript_tail": transcript[-4000:],
        }
    if transcript_path:
        try:
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write("case: %s\nmodel: %s\narm: %s\nfired: %s\n"
                        "distractors: %s\nforeign: %s\nerror: %s\n"
                        "reads: %s\nreads_failed: %s\nbash: %s\n"
                        % (case["id"], model, arm, res["fired"],
                           res["distractors"], res["foreign"], res["error"],
                           rec.get("reads", []), rec.get("reads_failed", []),
                           rec.get("bash", [])))
                f.write("\n--- transcript ---\n")
                f.write("\n\n".join(t for t in rec.get("texts", []) if t)
                        or rec.get("final_text", ""))
            res["transcript_path"] = transcript_path
        except OSError as e:
            res["transcript_path"] = "unwritable: %s" % e
    return res


# ----------------------------------------------------------------- metrics --
def score(results, catalog_names, count_declared=False):
    """Aggregate probe results into per-skill and overall metrics.

    A result is *exact* when set(fired) == set(expect); it is a *hit*
    (all-expected-fired) when expect ⊆ fired for positives / nothing fired
    for negatives. Foreign fires are reported but never penalised. Errored
    probes are excluded from the metrics and counted separately.
    ``per_case`` aggregates repeats into rates — the readable unit when a
    probe model is noisy at n=1. ``count_declared`` scores a catalog skill
    the probe *declared* (SKILLS= line) but never invoked as fired —
    the "selected" reading; the default keeps the tool_use ground truth."""
    if count_declared:
        merged = []
        for r in results:
            extra = [d for d in (r.get("declared") or [])
                     if d in catalog_names and d not in r["fired"]]
            merged.append(dict(r, fired=list(r["fired"]) + extra))
        results = merged
    per = {n: {"tp": 0, "fp": 0, "fn": 0} for n in catalog_names}
    per_case = {}
    exact = 0
    n_ok = 0
    n_err = 0
    neg_total = neg_false_fire = 0
    cost = 0.0
    distractor_fires = displaced = 0
    declared_only = 0
    body_n = body_followed = 0
    bf_hit = bf_tot = be_hit = be_tot = 0
    for r in results:
        cost += r.get("cost_usd") or 0.0
        pc = per_case.setdefault(r["id"], {"expect": list(r["expect"]), "n": 0,
                                           "err": 0, "exact": 0, "hit": 0,
                                           "displaced": 0,
                                           "distractor_fired": 0,
                                           "declared_only": 0})
        if r.get("error"):
            n_err += 1
            pc["err"] += 1
            continue
        n_ok += 1
        pc["n"] += 1
        fired, expect = set(r["fired"]), set(r["expect"])
        if fired == expect:
            exact += 1
            pc["exact"] += 1
        if (expect <= fired) if expect else (not fired):
            pc["hit"] += 1
        if not expect:
            neg_total += 1
            if fired:
                neg_false_fire += 1
        d_fired = r.get("distractors") or []
        distractor_fires += len(d_fired)
        if d_fired:
            pc["distractor_fired"] += 1
        if d_fired and expect - fired:
            displaced += 1
            pc["displaced"] += 1
        # protocol artifact, not a selection failure: the probe wrote
        # "SKILLS=<expected>" but never emitted the Skill tool_use
        declared = r.get("declared")
        if expect and expect - fired and isinstance(declared, list) \
                and expect <= set(declared):
            declared_only += 1
            pc["declared_only"] += 1
        b = r.get("body")
        if b is not None:
            body_n += 1
            bf_hit += len(b["files_hit"])
            bf_tot += len(b["files_expected"])
            be_hit += len(b["evidence_hit"])
            be_tot += len(b["evidence_expected"])
            if (fired == expect
                    and len(b["files_hit"]) == len(b["files_expected"])
                    and len(b["evidence_hit"]) >=
                    b.get("evidence_min", len(b["evidence_expected"]))):
                body_followed += 1
        for n in catalog_names:
            if n in fired and n in expect:
                per[n]["tp"] += 1
            elif n in fired:
                per[n]["fp"] += 1
            elif n in expect:
                per[n]["fn"] += 1
    for pc in per_case.values():
        pc["exact_rate"] = pc["exact"] / pc["n"] if pc["n"] else None
        pc["hit_rate"] = pc["hit"] / pc["n"] if pc["n"] else None
    for n, d in per.items():
        tp, fp, fn = d["tp"], d["fp"], d["fn"]
        d["precision"] = tp / (tp + fp) if tp + fp else None
        d["recall"] = tp / (tp + fn) if tp + fn else None
    return {"per_skill": per, "per_case": per_case,
            "exact": exact, "n_ok": n_ok, "n_err": n_err,
            "exact_rate": exact / n_ok if n_ok else None,
            "neg_total": neg_total, "neg_false_fire": neg_false_fire,
            "cost_usd": cost,
            "distractor_fires": distractor_fires, "displaced": displaced,
            "declared_only": declared_only, "count_declared": count_declared,
            "body": None if not body_n else {
                "n": body_n, "followed": body_followed,
                "files_hit": bf_hit, "files_expected": bf_tot,
                "evidence_hit": be_hit, "evidence_expected": be_tot}}


def fmt_rate(x):
    return "  n/a" if x is None else "%4.0f%%" % (100 * x)


def render_report(results, metrics, catalog_names, mode, model,
                  distractor_names=(), protocol=None):
    lines = ["# skill trigger eval — mode=%s model=%s%s%s" % (
        mode, model,
        " protocol=%s" % protocol if protocol and mode == "native" else "",
        " (declared skills counted as fired)"
        if metrics.get("count_declared") else ""), ""]
    lines.append("probes: %d ok, %d errored, exact-match %s, negatives false-fire %d/%d, cost $%.3f"
                 % (metrics["n_ok"], metrics["n_err"], fmt_rate(metrics["exact_rate"]).strip(),
                    metrics["neg_false_fire"], metrics["neg_total"], metrics["cost_usd"]))
    if metrics.get("declared_only"):
        lines.append("declared-not-invoked: %d probe(s) wrote SKILLS=<expected> "
                     "without a Skill tool_use (protocol artifact — re-probe "
                     "before treating the miss as a selection failure)"
                     % metrics["declared_only"])
    lines += ["", "| skill | recall | precision | tp | fp | fn |", "|---|---|---|---|---|---|"]
    for n in catalog_names:
        d = metrics["per_skill"][n]
        lines.append("| %s | %s | %s | %d | %d | %d |" % (
            n, fmt_rate(d["recall"]).strip(), fmt_rate(d["precision"]).strip(),
            d["tp"], d["fp"], d["fn"]))
    pc = metrics.get("per_case") or {}
    if any(d["n"] + d["err"] > 1 for d in pc.values()):
        lines += ["", "per-case fire rates (all-expected-fired vs exact; "
                  "negatives: hit = nothing fired):",
                  "| case | runs | fired | exact | err |", "|---|---|---|---|---|"]
        for cid, d in pc.items():   # insertion order == case order
            lines.append("| %s | %d | %d (%s) | %d (%s) | %d |" % (
                cid, d["n"], d["hit"], fmt_rate(d["hit_rate"]).strip(),
                d["exact"], fmt_rate(d["exact_rate"]).strip(), d["err"]))
    dcol = bool(distractor_names)
    head = "| case | expect | fired |" + (" staged-distractor |" if dcol else "") \
        + " foreign | ok |"
    lines += ["", head, "|---|---|---|" + ("---|" if dcol else "") + "---|---|"]
    for r in results:
        if r.get("error"):
            status = "ERR: " + r["error"][:80]
        else:
            status = "yes" if set(r["fired"]) == set(r["expect"]) else "NO"
        cells = [r["id"], ",".join(r["expect"]) or "—", ",".join(r["fired"]) or "—"]
        if dcol:
            cells.append(",".join(r.get("distractors") or []) or "—")
        cells += [",".join(r["foreign"]) or "—", status]
        lines.append("| " + " | ".join(cells) + " |")
    if mode == "body":
        b = metrics.get("body")
        if b:
            lines += ["", "body-following: %d/%d cases fully followed; "
                      "bundled files read %d/%d; evidence matched %d/%d"
                      % (b["followed"], b["n"], b["files_hit"], b["files_expected"],
                         b["evidence_hit"], b["evidence_expected"])]
        lines += ["", "| case | fired | staged files read | failed reads | files | evidence | chars |",
                  "|---|---|---|---|---|---|---|"]
        for r in results:
            bb = r.get("body") or {}
            fails = ", ".join("%s%s" % (f["file"], " (denied)" if f["denied"] else "")
                              for f in bb.get("files_failed") or [])
            ev_min = bb.get("evidence_min", len(bb.get("evidence_expected") or []))
            ev_cell = "%d/%d" % (len(bb.get("evidence_hit") or []),
                                 len(bb.get("evidence_expected") or []))
            if ev_min != len(bb.get("evidence_expected") or []):
                ev_cell += " (min %d)" % ev_min
            lines.append("| %s | %s | %s | %s | %d/%d | %s | %d |" % (
                r["id"], ",".join(r["fired"]) or "—",
                ", ".join(bb.get("files_read") or []) or "—", fails or "—",
                len(bb.get("files_hit") or []), len(bb.get("files_expected") or []),
                ev_cell, bb.get("transcript_chars", 0)))
    if distractor_names:
        fired_d = {}
        for r in results:
            for d in r.get("distractors") or []:
                fired_d[d] = fired_d.get(d, 0) + 1
        lines += ["", "staged distractors (%d): %s"
                  % (len(distractor_names), ", ".join(sorted(distractor_names)))]
        if fired_d:
            lines.append("staged-distractor fires: " + ", ".join(
                "%s×%d" % (k, v) for k, v in sorted(fired_d.items())))
        lines.append("displacement (expected skill missing while a staged "
                     "distractor fired): %d probe(s)" % metrics.get("displaced", 0))
    avail = set()
    for r in results:
        avail.update(r.get("available") or [])
    host = sorted(a for a in avail
                  if a not in catalog_names and a not in set(distractor_names))
    if host:
        lines += ["", "host distractor skills present: " + ", ".join(host)]
    return "\n".join(lines)


def render_model_comparison(metrics_by_model, catalog_names, models):
    lines = ["# per-model comparison", "",
             "| skill | " + " | ".join("%s recall" % m for m in models) + " |",
             "|---|" + "---|" * len(models)]
    for n in catalog_names:
        row = [fmt_rate(metrics_by_model[m]["per_skill"][n]["recall"]).strip()
               for m in models]
        lines.append("| %s | %s |" % (n, " | ".join(row)))
    lines += ["", "| metric | " + " | ".join(models) + " |",
              "|---|" + "---|" * len(models)]
    rows = [
        ("exact-match", lambda mm: fmt_rate(mm["exact_rate"]).strip()),
        ("neg false-fire", lambda mm: "%d/%d" % (mm["neg_false_fire"], mm["neg_total"])),
        ("errored", lambda mm: str(mm["n_err"])),
        ("displaced", lambda mm: str(mm.get("displaced", 0))),
        ("cost", lambda mm: "$%.3f" % mm["cost_usd"]),
    ]
    for label, f in rows:
        lines.append("| %s | %s |" % (label, " | ".join(f(metrics_by_model[m])
                                                        for m in models)))
    return "\n".join(lines)


def paired_verdicts(plain_metrics, staged_metrics):
    """Per positive case, compare plain vs staged fire counts and name the
    failure mode. Returns [{"id", "expect", "plain": "h/n", "staged": "h/n",
    "gap", "verdict"}]. Verdicts: ok (no drop), noise? (drop of 1 — re-run
    before acting), SUPPRESSED (drop ≥2, staged distractor never fired on
    the case: the selector fired neither contender), DISPLACED (drop ≥2
    with the distractor firing while yours went missing)."""
    out = []
    pp, sp = plain_metrics["per_case"], staged_metrics["per_case"]
    for cid, p in pp.items():
        if not p["expect"] or cid not in sp:
            continue
        s = sp[cid]
        gap = p["hit"] - s["hit"]
        if gap >= 2:
            verdict = "DISPLACED" if s["displaced"] else "SUPPRESSED"
        elif gap == 1:
            verdict = "noise?"
        else:
            verdict = "ok"
        out.append({"id": cid, "expect": p["expect"],
                    "plain": "%d/%d" % (p["hit"], p["n"]),
                    "staged": "%d/%d" % (s["hit"], s["n"]),
                    "staged_distractor_fires": s["distractor_fired"],
                    "gap": gap, "verdict": verdict})
    return out


def render_paired(verdicts, model):
    lines = ["# paired suppression diagnostic — model=%s" % model,
             "(fired = all expected skills fired; drop ≥2 with no distractor "
             "fire on the case = suppression)", "",
             "| case | plain fired | staged fired | gap | distractor fired | verdict |",
             "|---|---|---|---|---|---|"]
    for v in verdicts:
        lines.append("| %s | %s | %s | %+d | %d run(s) | %s |" % (
            v["id"], v["plain"], v["staged"], -v["gap"],
            v["staged_distractor_fires"], v["verdict"]))
    return "\n".join(lines)


# ---------------------------------------------------------------- baseline --
def load_baseline(path):
    """Load a prior ``--json`` report for comparison. Returns
    {"metrics": ..., "metrics_by_model": {...} or {}}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("metrics"), dict):
        raise ValueError("%s: not a trigger_eval report (no metrics)" % path)
    metrics = data["metrics"]
    by_model = data.get("metrics_by_model") or {}
    if "per_case" not in metrics:
        # pre-v4 report: no per-case rates stored — rebuild them from the
        # raw results so old baselines stay comparable
        results = data.get("results")
        if not isinstance(results, list):
            raise ValueError("%s: report has neither metrics.per_case nor "
                             "results" % path)
        names = list(metrics.get("per_skill") or {})
        metrics = score(results, names)
        by_model = {m: score([r for r in results if r.get("model") == m], names)
                    for m in (data.get("models") or [])}
    return {"metrics": metrics, "metrics_by_model": by_model,
            "protocol": data.get("protocol", "default"),
            "descriptions": data.get("descriptions") or {}}


def compare_reports(base_metrics, new_metrics):
    """Per-case comparison of two ``score()`` outputs (same case ids).
    Returns rows [{"id", "expect", "base": "h/n"|None, "new": "h/n"|None,
    "hit_delta", "exact_delta", "verdict"}]. Verdicts: ``same``;
    ``REGRESSED`` / ``IMPROVED`` (all-expected-fired moved by ≥2 runs
    when both sides have the same n, else by ≥0.5 in rate); ``noise?`` (a
    smaller move — re-probe with ``--only <id> --repeats 4`` before
    acting); ``CO-FIRE`` (fire rate held but the exact rate dropped by
    the same margin: a sibling now fires alongside); ``new`` / ``dropped``
    (case only on one side); ``low-n`` (the sides differ in n
    and one of them is a single run — 1/1 → 0/2 is not evidence either
    way; re-probe at equal n ≥ 2). Errored-out cases (n=0) compare as
    None."""
    bp, np_ = base_metrics["per_case"], new_metrics["per_case"]
    rows = []
    for cid in list(np_) + [c for c in bp if c not in np_]:
        b, n = bp.get(cid), np_.get(cid)
        row = {"id": cid, "expect": list((n or b)["expect"]),
               "base": None if not b or not b["n"] else "%d/%d" % (b["hit"], b["n"]),
               "new": None if not n or not n["n"] else "%d/%d" % (n["hit"], n["n"]),
               "base_exact": None if not b or not b["n"] else "%d/%d" % (b["exact"], b["n"]),
               "new_exact": None if not n or not n["n"] else "%d/%d" % (n["exact"], n["n"]),
               "hit_delta": None, "exact_delta": None}
        if n is None:
            row["verdict"] = "dropped"
        elif b is None:
            row["verdict"] = "new"
        elif not b["n"] or not n["n"]:
            row["verdict"] = "n/a"
        else:
            hd = n["hit_rate"] - b["hit_rate"]
            ed = n["exact_rate"] - b["exact_rate"]
            row["hit_delta"], row["exact_delta"] = hd, ed
            low_n = b["n"] != n["n"] and min(b["n"], n["n"]) < 2
            if b["n"] == n["n"]:
                big = lambda d: abs(round(d * b["n"])) >= 2   # noqa: E731
            else:
                big = lambda d: abs(d) >= 0.5                  # noqa: E731
            if hd == 0 and ed == 0:
                row["verdict"] = "same"
            elif low_n:
                row["verdict"] = "low-n"
            elif hd < 0 and big(hd):
                row["verdict"] = "REGRESSED"
            elif hd > 0 and big(hd):
                row["verdict"] = "IMPROVED"
            elif hd == 0 and ed < 0 and big(ed):
                row["verdict"] = "CO-FIRE"
            else:
                row["verdict"] = "noise?"
        rows.append(row)
    return rows


def render_comparison(rows, base_metrics, new_metrics, model, base_path,
                      base_protocol=None, new_protocol=None, changed=()):
    """Delta table plus two provenance notes the numbers cannot carry:
    a protocol mismatch (baseline and this run used different probe
    prompts — the verdicts are cross-instrument candidates for a
    same-protocol re-probe) and the skills whose descriptions changed
    since the baseline (so a verdict on their cases is an edit effect,
    not drift)."""
    def pct(x):
        return "n/a" if x is None else "%.0f%%" % (100 * x)

    def sd(x):
        return "—" if x is None else "%+.0f%%" % (100 * x)
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    lines = ["# comparison vs baseline %s — model=%s" % (base_path, model),
             "exact-match %s -> %s; negatives false-fire %d/%d -> %d/%d; "
             "verdicts: %s" % (
                 pct(base_metrics["exact_rate"]), pct(new_metrics["exact_rate"]),
                 base_metrics["neg_false_fire"], base_metrics["neg_total"],
                 new_metrics["neg_false_fire"], new_metrics["neg_total"],
                 ", ".join("%d %s" % (v, k) for k, v in sorted(
                     counts.items(), key=lambda kv: (-kv[1], kv[0])))),
             ]
    if base_protocol and new_protocol and base_protocol != new_protocol:
        lines.append("NOTE: probe protocol differs (baseline=%s, this run=%s) "
                     "— cross-instrument comparison; treat every verdict as "
                     "a candidate for a same-protocol re-probe, not as a "
                     "regression" % (base_protocol, new_protocol))
    if changed:
        lines.append("descriptions edited since the baseline: %s"
                     % ", ".join(changed))
    lines += ["", "| case | expect | base fired | new fired | Δ | base exact "
              "| new exact | verdict |",
              "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], ",".join(r["expect"]) or "—", r["base"] or "—",
            r["new"] or "—", sd(r["hit_delta"]), r["base_exact"] or "—",
            r["new_exact"] or "—", r["verdict"]))
    return "\n".join(lines)


# ------------------------------------------------------------------- audit --
def description_digest(description):
    """Short stable digest of a description (whitespace-trimmed). Written
    into every --json report (``descriptions``) so a later ``--audit`` can
    tell whether the description that was probed is the one on disk."""
    return hashlib.sha1((description or "").strip().encode("utf-8")).hexdigest()[:12]


def load_reports(reports_dir):
    """Every trigger_eval ``--json`` run report directly under reports_dir
    as [(path, mtime, data)], newest first by file mtime. Canary dumps,
    comparison files and non-report JSON are skipped."""
    out = []
    for e in os.listdir(reports_dir):
        if not e.endswith(".json"):
            continue
        p = os.path.join(reports_dir, e)
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            continue
        out.append((p, os.path.getmtime(p), data))
    out.sort(key=lambda t: -t[1])
    return out


def audit_skills(catalog, cases, reports, positive_floor=3):
    """Per catalog skill: case coverage (positives = cases expecting it
    without a body spec; body_cases = with one), probe freshness, and the
    probe's OUTCOME, all from the newest report holding a non-errored probe
    of a case expecting it.

    Freshness (``status``): ``probed`` (that report's description digest ==
    the current one), ``STALE`` (digest differs — edited since),
    ``unverified`` (report predates digests), ``never``. ``under_floor``
    flags positives < positive_floor.

    Outcome (round 375). ``status`` answers "did we look", and until round
    375 nothing here answered "what did we see" — `measured-budget-sizing`
    read ``probed`` while its newest report fired it on 0 of 3 cases, and
    `fuzz-mutate-kill-loop` read ``probed`` off ONE of its seven cases,
    because the newest report holding a probe of it is a re-run of the one
    case that had MISSED. Three fields close that:

      ``covered``   distinct POSITIVE case ids that report actually probed
      ``recalled``  of those, the ones where EVERY repeat fired the skill
      ``flaky``     of those, the ones where some repeats fired and some
                    did not (a report may repeat one case n times; counting
                    RESULTS instead of distinct ids is what hid
                    `measured-exemption`'s 1 case x 4 repeats behind
                    ``probes=4`` against ``positives=3``)

    ``covered``/``recalled``/``flaky`` are 0 when there is no probe. They
    deliberately do NOT feed ``audit_exit_code``: `skill-authoring`'s
    shipping checklist cites that exit code for the freshness question, and
    the outcome question is priced (re-probing is a live spend), so it is
    carried as `case_coverage.py`'s P006/P007 warnings against an owned
    baseline — the same split P004 already uses."""
    rows = []
    for name, desc, _ in catalog:
        pos = [c for c in cases if name in c["expect"] and c.get("body") is None]
        body = [c for c in cases if name in c["expect"] and c.get("body") is not None]
        row = {"name": name, "positives": len(pos), "body_cases": len(body),
               "status": "never", "report": None, "probes": 0,
               "protocol": None, "mode": None,
               "covered": 0, "recalled": 0, "flaky": 0,
               "digest": description_digest(desc),
               "under_floor": len(pos) < positive_floor}
        pos_ids = {c["id"] for c in pos}
        # Round 393: prefer the newest report that probed THE DESCRIPTION ON
        # DISK, not merely the newest report holding any probe. The old
        # loop broke at the first report with probes, so a skill probed
        # under its current description and then probed again under a
        # variant that was tried and REVERTED read `STALE`, with
        # covered/recalled taken from the reverted variant's measurement.
        # Round 393 hit exactly that on `derived-subject-set` and it is the
        # same defect as everything else that round found: the estimator
        # answered a question about one report instead of about the
        # evidence. Fall back to the newest report of any digest only to
        # tell STALE from never.
        with_probes = []
        for path, _, data in reports:
            probes = [r for r in data["results"]
                      if name in (r.get("expect") or []) and not r.get("error")]
            if probes:
                with_probes.append((path, data, probes))
        chosen = None
        for path, data, probes in with_probes:
            if (data.get("descriptions") or {}).get(name) == row["digest"]:
                chosen = (path, data, probes)
                break
        if chosen is None and with_probes:
            chosen = with_probes[0]
        if chosen is not None:
            path, data, probes = chosen
            row["report"] = os.path.basename(path)
            row["probes"] = len(probes)
            row["protocol"] = data.get("protocol", "default")
            row["mode"] = data.get("mode")
            by_id = {}
            for r in probes:
                if r.get("id") in pos_ids:
                    by_id.setdefault(r["id"], []).append(
                        name in (r.get("fired") or []))
            row["covered"] = len(by_id)
            row["recalled"] = sum(1 for v in by_id.values() if all(v))
            row["flaky"] = sum(1 for v in by_id.values() if any(v) and not all(v))
            seen = (data.get("descriptions") or {}).get(name)
            if seen is None:
                row["status"] = "unverified"
            elif seen == row["digest"]:
                row["status"] = "probed"
            else:
                row["status"] = "STALE"
        rows.append(row)
    return rows


def wilson_interval(k, n, z=1.96):
    """Wilson score interval for k successes in n Bernoulli trials.

    Round 393. The corpus had no interval at all: every verdict ever
    written about a description was a point estimate off one report, and a
    point estimate cannot say "3 of 3 and 30 of 30 are different evidence".
    Wilson rather than normal-approximation because the rates that matter
    here sit at the ends (0/6, 6/6) where the normal interval is degenerate
    or runs outside [0, 1)."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (centre - half) / d), min(1.0, (centre + half) / d))


def pooled_rows(catalog, cases, reports, threshold=0.5):
    """Per catalog skill: every same-digest probe POOLED, with the run count
    and an interval — the estimator ``replication_rows`` should have been.

    Round 393. ``replication_rows`` collapses each report to
    ``all(fires)``. Under a true fire rate p that boolean is True with
    probability p**n, so the SAME description yields verdict True with
    probability p at ``--repeats 1`` and p**3 at ``--repeats 3``. The
    estimator therefore disagrees with itself whenever 0 < p < 1 and the
    repeat counts differ, and round 393 measured the size of that: of the
    45 cross-report comparisons the corpus was reporting as "27 DISAGREE",
    **16.4 are expected under a null in which every case has one stable
    rate and the selector is perfectly well-behaved** — so most of that
    headline number was the estimator disagreeing with itself.

    What this returns instead is the sufficient statistic — k of n across
    all same-digest reports — plus ``runs``, because round 393 measured
    that the RUN, not the probe, is the unit of independence (see
    ``run_variance``). A verdict is:

      ``WORKS``      interval lower bound  > threshold
      ``BROKEN``     interval upper bound  < threshold
      ``UNDECIDED``  the interval straddles it — the honest answer for
                     almost every single-report probe this corpus holds

    Per skill:
      ``k``/``n``    fires / non-errored probes on positive cases, pooled
      ``runs``       distinct reports contributing (the replication depth
                     that actually counts)
      ``lo``/``hi``  Wilson 95% interval on k/n
      ``verdict``    as above; ``UNPROBED`` when n == 0
      ``cases``      {case id: {"k","n","runs","lo","hi","verdict"}}
    """
    rows = []
    for name, desc, _ in catalog:
        digest = description_digest(desc)
        pos_ids = {c["id"] for c in cases
                   if name in c["expect"] and c.get("body") is None}
        per_case = {}
        reps = set()
        for path, _, data in reports:
            if (data.get("descriptions") or {}).get(name) != digest:
                continue
            base = os.path.basename(path)
            for r in data["results"]:
                if r.get("error") or r.get("id") not in pos_ids:
                    continue
                if name not in (r.get("expect") or []):
                    continue
                c = per_case.setdefault(r["id"], {"k": 0, "n": 0, "runs": set()})
                c["n"] += 1
                c["runs"].add(base)
                reps.add(base)
                if name in (r.get("fired") or []):
                    c["k"] += 1
        k = sum(c["k"] for c in per_case.values())
        n = sum(c["n"] for c in per_case.values())
        lo, hi = wilson_interval(k, n)
        row = {"name": name, "k": k, "n": n, "runs": len(reps),
               "lo": lo, "hi": hi, "cases": {},
               "verdict": ("UNPROBED" if n == 0 else
                           "WORKS" if lo > threshold else
                           "BROKEN" if hi < threshold else "UNDECIDED")}
        for cid, c in sorted(per_case.items()):
            clo, chi = wilson_interval(c["k"], c["n"])
            row["cases"][cid] = {
                "k": c["k"], "n": c["n"], "runs": len(c["runs"]),
                "lo": clo, "hi": chi,
                "verdict": ("WORKS" if clo > threshold else
                            "BROKEN" if chi < threshold else "UNDECIDED")}
        rows.append(row)
    return rows


def run_variance(catalog, cases, reports):
    """Decompose probe variance into BETWEEN-run and WITHIN-run parts.

    Round 393, measured prospectively: 23 cases x 3 separate invocations of
    this script x ``--repeats 2``, identical model / protocol / corpus /
    concurrency, run sequentially, on a case set chosen before any of it
    ran (the five skills that owed a probe). 138 probes, 0 errors.

    Result, over the three ``state/trigger-eval/round-393-run{A,B,C}.json``
    reports and nothing else: **MSB = 0.381, MSW = 0.190, MSB/MSW = 2.00,
    ANOVA ICC = 0.333**, on the 7 positive cases informative for it (a case
    pooling to exactly 0 or 1 carries no dispersion). Two probes in the
    same run are correlated beyond their shared rate, so ``--repeats N``
    inside one invocation does NOT buy N independent draws:

        n_eff = n / (1 + (n - 1) * ICC)

    At ICC 0.333 a 6-probe single run is worth **2.25** independent draws;
    the same six probes split as 3 runs x 2 repeats are worth **4.50**.
    Same model, same money, **twice the information** — which is the whole
    practical content of this function.

    That figure is evaluated against the descriptions ON DISK, because a
    stale digest removes a case from the pool: while round 393 briefly had
    an edited `derived-subject-set` staged, the same three reports gave 6
    informative cases and ICC 0.200. Editing any of the five descriptions
    those runs probed will move it again. Re-derive, do not quote.

    Do NOT take the ICC from the archived reports instead. Round 393 got
    0.665-0.737 that way and it is an artefact: many archived pairs are a
    ``*-miss-reprobe`` / ``*-isolation`` run that exists BECAUSE the
    earlier run missed, so the pair is conditioned on its own outcome and
    regression to the mean reads as a run effect. Restricted to designed
    replicates the archive gives 0.428-0.857, and the prospective number is
    0.200. Selection on the outcome inflated it roughly threefold. Calling
    this function over the WHOLE of ``state/trigger-eval/`` returns 0.568
    for exactly that reason; that number is not a measurement of the
    selector.

    Returns ``None`` when no case has >= 2 contributing runs; otherwise a
    dict with ``msb``, ``msw``, ``ratio``, ``icc``, ``cases``, ``runs``.
    """
    cells = {}
    for name, desc, _ in catalog:
        digest = description_digest(desc)
        pos_ids = {c["id"] for c in cases
                   if name in c["expect"] and c.get("body") is None}
        for path, _, data in reports:
            if (data.get("descriptions") or {}).get(name) != digest:
                continue
            base = os.path.basename(path)
            for r in data["results"]:
                if r.get("error") or r.get("id") not in pos_ids:
                    continue
                if name not in (r.get("expect") or []):
                    continue
                cell = cells.setdefault((name, r["id"]), {}).setdefault(
                    base, [0, 0])
                cell[1] += 1
                if name in (r.get("fired") or []):
                    cell[0] += 1

    msb_num = msb_df = msw_num = msw_df = 0.0
    icc_num = icc_den = 0.0
    used = 0
    runs = set()
    for key, d in cells.items():
        if len(d) < 2:
            continue
        K = sum(k for k, n in d.values())
        N = sum(n for k, n in d.values())
        p = K / float(N)
        if p in (0.0, 1.0) or N == len(d):
            continue
        R = len(d)
        between = sum(n * (k / float(n) - p) ** 2 for k, n in d.values())
        within = sum(k * (1 - k / float(n)) ** 2 + (n - k) * (k / float(n)) ** 2
                     for k, n in d.values())
        dfw = N - R
        if dfw <= 0:
            continue
        msb, msw = between / (R - 1), within / dfw
        n0 = (N - sum(n * n for k, n in d.values()) / float(N)) / (R - 1)
        msb_num += between
        msb_df += R - 1
        msw_num += within
        msw_df += dfw
        icc_num += msb - msw
        icc_den += msb + (n0 - 1) * msw
        used += 1
        runs |= set(d)
    if not used or not icc_den:
        return None
    msb, msw = msb_num / msb_df, msw_num / msw_df
    # MSW == 0 is a legitimate and maximally informative outcome (every run
    # was internally unanimous and the runs disagreed), not a reason to
    # refuse an answer -- the first draft returned None for it.
    ratio = float("inf") if msw == 0 else msb / msw
    return {"msb": msb, "msw": msw, "ratio": ratio,
            "icc": icc_num / icc_den, "cases": used, "runs": len(runs)}


def effective_draws(n, icc):
    """Independent-draw equivalent of ``n`` probes inside ONE run."""
    if n <= 0:
        return 0.0
    return n / (1.0 + (n - 1) * icc)


def replication_rows(catalog, cases, reports):
    """Per catalog skill: how many INDEPENDENT reports probed it under the
    description on disk, and whether those reports AGREE.

    Round 381. ``audit_skills`` answers every outcome question from *the
    newest report holding a probe*, and every durable verdict this program
    has ever written about a description was read off exactly one such
    report. Round 381 measured what that is worth: two runs of a
    byte-identical configuration (same 41-skill catalog, same 29 cases,
    same model, same ``--protocol strict``) disagreed at majority level on
    **11 of 29 cases**, and `lazy-fill-ceiling` read 0 of 12 in one run and
    12/12, 4/4 and 11/12 in three others. `measured-budget-sizing` and
    `obligation-ledger` had both been written into
    ``state/known-weak-probes.json`` as KNOWN-BAD DESCRIPTIONS off single
    3-probe draws; re-measured they are 9/9 and 6/9.

    A probe run is a DRAW from a stochastic selector. One draw is not a
    measurement of a description, and this function is what lets a caller
    say so with a number instead of a feeling.

    Returns one dict per skill:

      ``reports``       basenames of every report probing a positive case of
                        this skill under the CURRENT description digest,
                        newest first (reports with no ``descriptions`` map
                        are excluded — an unverified digest cannot be
                        compared)
      ``n_reports``     len(reports); 1 means UNREPLICATED
      ``compared``      positive case ids probed by >=2 of those reports
      ``disagree``      of those, ids where the per-report verdict
                        (did EVERY repeat in that report fire the skill?)
                        is not the same in all of them
      ``verdicts``      {case id: {report: bool}} for the compared ids

    A case probed by two reports that both fired it, or both missed it,
    agrees. Repeat counts deliberately do NOT have to match: the question is
    whether two independent runs reached the same VERDICT, which is the
    thing a baseline entry records."""
    rows = []
    for name, desc, _ in catalog:
        digest = description_digest(desc)
        pos_ids = {c["id"] for c in cases
                   if name in c["expect"] and c.get("body") is None}
        row = {"name": name, "reports": [], "n_reports": 0,
               "compared": [], "disagree": [], "verdicts": {}}
        per_report = []
        for path, _, data in reports:
            if (data.get("descriptions") or {}).get(name) != digest:
                continue
            by_id = {}
            for r in data["results"]:
                if r.get("error") or r.get("id") not in pos_ids:
                    continue
                if name not in (r.get("expect") or []):
                    continue
                by_id.setdefault(r["id"], []).append(
                    name in (r.get("fired") or []))
            if by_id:
                per_report.append((os.path.basename(path), by_id))
        row["reports"] = [b for b, _ in per_report]
        row["n_reports"] = len(per_report)
        seen = {}
        for base, by_id in per_report:
            for cid, fires in by_id.items():
                seen.setdefault(cid, {})[base] = all(fires)
        for cid in sorted(seen):
            if len(seen[cid]) < 2:
                continue
            row["compared"].append(cid)
            row["verdicts"][cid] = seen[cid]
            if len(set(seen[cid].values())) > 1:
                row["disagree"].append(cid)
        rows.append(row)
    return rows


def audit_exit_code(rows):
    return 0 if all(r["status"] == "probed" and not r["under_floor"]
                    for r in rows) else 1


def render_audit(rows, cases, n_reports, reports_dir):
    n_neg = sum(1 for c in cases if not c["expect"])
    n_body = sum(1 for c in cases if c.get("body") is not None)
    lines = ["# probe audit — %d skills, %d cases (%d negatives, %d body), "
             "%d reports under %s" % (len(rows), len(cases), n_neg, n_body,
                                       n_reports, reports_dir), "",
             "| skill | positives | body | newest probing report | mode/protocol "
             "| probes | covered | recalled | status |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        pos = "%d%s" % (r["positives"], " (UNDER FLOOR)" if r["under_floor"] else "")
        mp = "%s/%s" % (r["mode"], r["protocol"]) if r["report"] else "—"
        lines.append("| %s | %s | %d | %s | %s | %d | %d/%d | %d%s | %s |" % (
            r["name"], pos, r["body_cases"], r["report"] or "—", mp,
            r["probes"], r["covered"], r["positives"], r["recalled"],
            " (%d flaky)" % r["flaky"] if r["flaky"] else "", r["status"]))
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines += ["", "summary: " + ", ".join("%d %s" % (v, k) for k, v in sorted(
        counts.items(), key=lambda kv: (-kv[1], kv[0])))
        + "; %d under the %d-positive floor" % (
            sum(1 for r in rows if r["under_floor"]), 3)
        + "; %d of %d fully probed (every positive case, full recall)" % (
            sum(1 for r in rows if r["status"] == "probed"
                and r["covered"] == r["positives"]
                and r["recalled"] == r["covered"]), len(rows))
        + "; exit %d" % audit_exit_code(rows)]
    return "\n".join(lines)


# ------------------------------------------------------------------ canary --
def load_canary(path):
    """Load and validate a canary file: a sentinel dict or list of them.
    Required: case, min_rate. Defaults: model=sonnet, repeats=4,
    max_rate=1.0, mode=native."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError("canary file must be a sentinel object or list")
    out = []
    for i, s in enumerate(data):
        if not isinstance(s, dict) or "case" not in s or "min_rate" not in s:
            raise ValueError("canary sentinel %d needs 'case' and 'min_rate'" % i)
        rep = s.get("repeats", 4)
        lo, hi = s["min_rate"], s.get("max_rate", 1.0)
        if not isinstance(rep, int) or rep < 1:
            raise ValueError("canary sentinel %d: repeats must be int ≥1" % i)
        if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float))
                and 0 <= lo <= hi <= 1):
            raise ValueError("canary sentinel %d: need 0 ≤ min_rate ≤ "
                             "max_rate ≤ 1" % i)
        mode = s.get("mode", "native")
        if mode not in ("native", "catalog", "body"):
            raise ValueError("canary sentinel %d: bad mode %r" % (i, mode))
        protocol = s.get("protocol")
        if protocol is not None and protocol not in PROTOCOLS:
            raise ValueError("canary sentinel %d: bad protocol %r"
                             % (i, protocol))
        out.append({"case": s["case"], "model": s.get("model", "sonnet"),
                    "repeats": rep, "min_rate": float(lo),
                    "max_rate": float(hi), "mode": mode,
                    "protocol": protocol})   # None = the run's --protocol
    return out


def run_canary(sentinels, cases, catalog, project_dir, runner, executable,
               timeout_s, budget_usd, body_tools, concurrency, quiet,
               protocol="default"):
    """Run each sentinel case ×repeats; band-check the all-expected-fired
    rate. Returns (exit_code, records): 0 all in band, 1 drift, 2
    inconclusive (a sentinel had zero non-errored runs or an unknown
    case id)."""
    by_id = {c["id"]: c for c in cases}
    records = []
    code = 0
    for s in sentinels:
        case = by_id.get(s["case"])
        if case is None:
            print("canary: unknown case id %r" % s["case"], file=sys.stderr)
            return 2, records
        s = dict(s, protocol=s.get("protocol") or protocol)
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, concurrency)) as ex:
            futs = [ex.submit(run_probe, case, s["mode"], catalog, project_dir,
                              runner, executable, s["model"], timeout_s,
                              budget_usd, body_tools=body_tools,
                              protocol=s["protocol"])
                    for _ in range(s["repeats"])]
            results = [f.result() for f in futs]
        m = score(results, [n for n, _, _ in catalog])
        pc = m["per_case"][s["case"]]
        rec = dict(s, n_ok=pc["n"], n_err=pc["err"], hit=pc["hit"],
                   rate=pc["hit_rate"], cost_usd=m["cost_usd"],
                   results=results)
        if pc["n"] == 0:
            rec["status"] = "INCONCLUSIVE"
            code = 2
        elif s["min_rate"] <= pc["hit_rate"] <= s["max_rate"]:
            rec["status"] = "OK"
        else:
            rec["status"] = "DRIFT"
            if code == 0:
                code = 1
        records.append(rec)
        if not quiet:
            print("CANARY %-12s %-8s %s/%s: fired %d/%d (errs %d) band "
                  "[%.2f, %.2f] -> %s" % (
                      s["case"], s["model"], s["mode"], s["protocol"],
                      pc["hit"], pc["n"], pc["err"], s["min_rate"],
                      s["max_rate"], rec["status"]),
                  file=sys.stderr)
    return code, records


# -------------------------------------------------------------------- main --
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cases")
    ap.add_argument("--skills", action="append", required=True,
                    help="skill dir or directory of skill dirs (repeatable)")
    ap.add_argument("--mode", choices=("native", "catalog", "body"), default="native")
    ap.add_argument("--model", default="sonnet",
                    help="probe model, or comma-separated list for a per-model comparison")
    ap.add_argument("--executable", default="claude")
    ap.add_argument("--distractors", action="append", default=[],
                    help="directory tree of foreign skills staged as controlled "
                         "distractors (repeatable, recursive, lenient)")
    ap.add_argument("--n-distractors", type=int, default=-1,
                    help="deterministic sample size from the distractor pool (-1 = all)")
    ap.add_argument("--distractor-seed", type=int, default=0)
    ap.add_argument("--body-tools", default="Skill,Read",
                    help="--tools value for body-mode probes")
    ap.add_argument("--paired", action="store_true",
                    help="run every probe with AND without the staged "
                         "distractors and print a per-case suppression table "
                         "(requires --distractors)")
    ap.add_argument("--transcripts",
                    help="directory to write full per-probe transcripts into")
    ap.add_argument("--canary",
                    help="canary sentinel file: run frozen case(s) against "
                         "stored acceptance bands; exit 0 in-band / 1 drift "
                         "/ 2 inconclusive")
    ap.add_argument("--protocol", choices=sorted(PROTOCOLS), default="strict",
                    help="native-mode probe system prompt (default: strict "
                         "— the SKILLS= line is invalid without a preceding "
                         "Skill call; 'default' is the pre-v4.2 prompt, "
                         "kept for comparisons with older reports)")
    ap.add_argument("--also-cases", action="append", default=[], metavar="FILE",
                    help="additional case file(s) merged in (ids unique "
                         "across files), e.g. the body cases so --audit "
                         "sees body coverage")
    ap.add_argument("--audit", metavar="REPORTS_DIR",
                    help="offline, no probes: per skill, case coverage and "
                         "whether the newest --json report under "
                         "REPORTS_DIR probed the CURRENT description "
                         "(digest match); exit 1 on STALE / never / "
                         "unverified / fewer than 3 positive cases")
    ap.add_argument("--count-declared", action="store_true",
                    help="score a catalog skill the probe declared (SKILLS= "
                         "line) but never invoked as fired")
    ap.add_argument("--baseline",
                    help="a prior --json report; after the run print a "
                         "per-case delta table (REGRESSED / IMPROVED / "
                         "CO-FIRE / noise? / same) per model")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=150.0)
    ap.add_argument("--budget-usd", type=float, default=0.5, help="per-probe cap")
    ap.add_argument("--only", help="comma-separated case ids to run")
    ap.add_argument("--json", help="write raw results + metrics here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        catalog = load_catalog(args.skills)
        cases = load_cases(args.cases)
        for p in args.also_cases:
            extra = load_cases(p)
            dup = {c["id"] for c in cases} & {c["id"] for c in extra}
            if dup:
                raise ValueError("duplicate case ids across case files: %s"
                                 % sorted(dup))
            cases += extra
    except (OSError, ValueError) as e:
        print("trigger-eval: %s" % e, file=sys.stderr)
        return 2
    if not catalog:
        print("trigger-eval: no SKILL.md found under %s" % args.skills, file=sys.stderr)
        return 2
    names = [n for n, _, _ in catalog]
    if args.only:
        keep = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    unknown = sorted({e for c in cases for e in c["expect"]} - set(names))
    if unknown:
        print("trigger-eval: cases expect unknown skills %s" % unknown, file=sys.stderr)
        return 2
    models = [m.strip() for m in args.model.split(",") if m.strip()]
    if not models:
        print("trigger-eval: --model is empty", file=sys.stderr)
        return 2

    baseline = None
    if args.baseline:
        try:
            baseline = load_baseline(args.baseline)
        except (OSError, ValueError) as e:
            print("trigger-eval: baseline: %s" % e, file=sys.stderr)
            return 2

    if args.audit:
        try:
            reports = load_reports(args.audit)
        except OSError as e:
            print("trigger-eval: audit: %s" % e, file=sys.stderr)
            return 2
        rows = audit_skills(catalog, cases, reports)
        print(render_audit(rows, cases, len(reports), args.audit))
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump({"audit": rows, "exit": audit_exit_code(rows)},
                          f, indent=1)
        return audit_exit_code(rows)

    if args.canary:
        try:
            sentinels = load_canary(args.canary)
        except (OSError, ValueError) as e:
            print("trigger-eval: canary: %s" % e, file=sys.stderr)
            return 2
        tmp = tempfile.mkdtemp(prefix="trigger-eval-")
        try:
            stage_skills(catalog, tmp)
            code, records = run_canary(
                sentinels, cases, catalog, tmp, default_runner,
                args.executable, args.timeout, args.budget_usd,
                args.body_tools, args.concurrency, args.quiet,
                protocol=args.protocol)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump({"canary": records, "exit": code}, f, indent=1)
        return code

    distractors = []
    if args.distractors:
        try:
            pool = load_catalog(args.distractors, lenient=True, recursive=True)
        except OSError as e:
            print("trigger-eval: %s" % e, file=sys.stderr)
            return 2
        distractors = pick_distractors(pool, names, args.n_distractors,
                                       args.distractor_seed)
    dnames = frozenset(n for n, _, _ in distractors)
    if args.paired and not distractors:
        print("trigger-eval: --paired requires --distractors", file=sys.stderr)
        return 2
    if args.transcripts:
        os.makedirs(args.transcripts, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="trigger-eval-")
    tmp_plain = tempfile.mkdtemp(prefix="trigger-eval-plain-") if args.paired else None
    try:
        stage_skills(catalog + distractors, tmp)
        if args.paired:
            stage_skills(catalog, tmp_plain)
            arms = [("plain", tmp_plain, frozenset()), ("staged", tmp, dnames)]
        else:
            arms = [(None, tmp, dnames)]
        jobs = []
        for m in models:
            for c in cases:
                for k in range(args.repeats):
                    for arm, proj, dn in arms:
                        tp = None
                        if args.transcripts:
                            base = "-".join(x for x in (m, arm, c["id"], str(k)) if x)
                            tp = os.path.join(args.transcripts, base + ".txt")
                        jobs.append((c, m, arm, proj, dn, tp))
        results = [None] * len(jobs)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
            futs = {ex.submit(run_probe, c, args.mode, catalog, proj, default_runner,
                              args.executable, m, args.timeout, args.budget_usd,
                              distractor_names=dn, body_tools=args.body_tools,
                              arm=arm, transcript_path=tp,
                              protocol=args.protocol): i
                    for i, (c, m, arm, proj, dn, tp) in enumerate(jobs)}
            for fut in concurrent.futures.as_completed(futs):
                i = futs[fut]
                results[i] = fut.result()
                if not args.quiet:
                    r = results[i]
                    mark = "ERR" if r["error"] else ("ok " if set(r["fired"]) == set(r["expect"]) else "NO ")
                    print("[%s] %-8s %-6s %-12s expect=%s fired=%s distractor=%s foreign=%s $%.3f" % (
                        mark, r["model"], r.get("arm") or "-", r["id"], r["expect"],
                        r["fired"], r["distractors"], r["foreign"], r["cost_usd"]),
                        file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if tmp_plain:
            shutil.rmtree(tmp_plain, ignore_errors=True)

    metrics_by_model = {}
    metrics_by_model_arm = {}
    paired_by_model = {}
    for m in models:
        rs = [r for r in results if r["model"] == m]
        metrics_by_model[m] = score(rs, names, args.count_declared)
        if args.paired:
            arm_metrics = {}
            for arm in ("plain", "staged"):
                ars = [r for r in rs if r.get("arm") == arm]
                arm_metrics[arm] = score(ars, names, args.count_declared)
                print(render_report(ars, arm_metrics[arm], names, args.mode,
                                    "%s arm=%s" % (m, arm),
                                    dnames if arm == "staged" else frozenset(),
                                    protocol=args.protocol))
                print()
            metrics_by_model_arm[m] = arm_metrics
            paired_by_model[m] = paired_verdicts(arm_metrics["plain"],
                                                 arm_metrics["staged"])
            print(render_paired(paired_by_model[m], m))
        else:
            print(render_report(rs, metrics_by_model[m], names, args.mode, m, dnames,
                                protocol=args.protocol))
        if len(models) > 1:
            print()
    if len(models) > 1:
        print(render_model_comparison(metrics_by_model, names, models))
    metrics = score(results, names, args.count_declared)
    comparison = None
    if baseline is not None:
        changed = sorted(n for n, d, _ in catalog
                         if baseline["descriptions"].get(n)
                         not in (None, description_digest(d)))
        comparison = {"path": args.baseline, "by_model": {},
                      "base_protocol": baseline["protocol"],
                      "protocol": args.protocol,
                      "protocol_mismatch": baseline["protocol"] != args.protocol,
                      "descriptions_changed": changed}
        for m in models:
            # a per-model baseline when the prior run had that model, else
            # the prior run's overall metrics (single-model reports agree)
            bm = baseline["metrics_by_model"].get(m) or baseline["metrics"]
            rows = compare_reports(bm, metrics_by_model[m])
            comparison["by_model"][m] = rows
            print()
            print(render_comparison(rows, bm, metrics_by_model[m], m,
                                    args.baseline,
                                    base_protocol=baseline["protocol"],
                                    new_protocol=args.protocol,
                                    changed=changed))
    if args.json:
        out = {"version": "4.2", "mode": args.mode, "model": args.model,
               "models": models,
               "descriptions": {n: description_digest(d) for n, d, _ in catalog},
               "distractors": sorted(dnames), "paired": args.paired,
               "protocol": args.protocol, "count_declared": args.count_declared,
               "results": results,
               "metrics": metrics, "metrics_by_model": metrics_by_model}
        if args.paired:
            out["metrics_by_model_arm"] = metrics_by_model_arm
            out["paired_by_model"] = paired_by_model
        if comparison is not None:
            out["baseline"] = comparison
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    if metrics["n_err"] == len(results):
        return 2
    return 0 if metrics["exact"] == metrics["n_ok"] and metrics["n_err"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

# probe audit — 14 skills, 72 cases (13 negatives, 12 body), 39 reports under state/trigger-eval

| skill | positives | body | newest probing report | mode/protocol | probes | status |
|---|---|---|---|---|---|---|
| agent-completion-guards | 3 | 1 | — | — | 0 | never |
| agent-context-budgeting | 3 | 1 | round-105-strict-full.json | native/strict | 6 | unverified |
| colocated-model-lane | 3 | 1 | — | — | 0 | never |
| engine-prefix-reuse-audit | 3 | 0 | round-105-strict-full.json | native/strict | 6 | unverified |
| fuzz-mutate-kill-loop | 7 | 1 | round-107-body-fmk.json | body/default | 2 | unverified |
| generator-trampoline-evaluator | 4 | 1 | round-105-strict-full.json | native/strict | 8 | unverified |
| llm-engine-benchmarking | 3 | 0 | round-105-strict-full.json | native/strict | 6 | unverified |
| offline-agent-testing | 3 | 1 | round-105-strict-full.json | native/strict | 6 | unverified |
| prediction-banking | 3 | 1 | round-105-strict-full.json | native/strict | 6 | unverified |
| session-inheritance-audit | 3 | 1 | round-105-strict-full.json | native/strict | 6 | unverified |
| shared-tip-immutable-lists | 3 | 1 | round-105-strict-full.json | native/strict | 6 | unverified |
| skill-authoring | 3 | 2 | round-105-strict-full.json | native/strict | 6 | unverified |
| subprocess-cli-testing | 4 | 1 | round-105-strict-full.json | native/strict | 8 | unverified |
| tiny-language-implementation | 4 | 0 | round-105-strict-full.json | native/strict | 8 | unverified |

summary: 12 unverified, 2 never; 0 under the 3-positive floor; exit 1

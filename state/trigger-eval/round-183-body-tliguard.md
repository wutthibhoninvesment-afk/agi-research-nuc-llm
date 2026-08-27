[ok ] sonnet   -      body-tliguard expect=['tiny-language-implementation'] fired=['tiny-language-implementation'] distractor=[] foreign=[] $0.128
# skill trigger eval — mode=body model=sonnet

probes: 1 ok, 0 errored, exact-match 100%, negatives false-fire 0/0, cost $0.128

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-completion-guards | n/a | n/a | 0 | 0 | 0 |
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| colocated-model-lane | n/a | n/a | 0 | 0 | 0 |
| engine-prefix-reuse-audit | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | n/a | n/a | 0 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | n/a | n/a | 0 | 0 | 0 |
| one-shot-agent-no-background-wait | n/a | n/a | 0 | 0 | 0 |
| prediction-banking | n/a | n/a | 0 | 0 | 0 |
| preflight-priced-task-scripts | n/a | n/a | 0 | 0 | 0 |
| self-updating-driver-loop | n/a | n/a | 0 | 0 | 0 |
| session-inheritance-audit | n/a | n/a | 0 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | n/a | n/a | 0 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | 100% | 100% | 1 | 0 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| body-tliguard | tiny-language-implementation | tiny-language-implementation | — | yes |

body-following: 1/1 cases fully followed; bundled files read 0/0; evidence matched 4/4

| case | fired | staged files read | failed reads | files | evidence | chars |
|---|---|---|---|---|---|---|
| body-tliguard | tiny-language-implementation | — | — | 0/0 | 4/4 | 3543 |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

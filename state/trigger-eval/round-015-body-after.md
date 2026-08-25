# skill trigger eval — mode=body model=sonnet

probes: 12 ok, 0 errored, exact-match 100%, negatives false-fire 0/0, cost $1.310

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 100% | 100% | 3 | 0 | 0 |
| fuzz-mutate-kill-loop | 100% | 100% | 3 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | 100% | 100% | 3 | 0 | 0 |
| shared-tip-immutable-lists | n/a | n/a | 0 | 0 | 0 |
| skill-authoring | 100% | 100% | 3 | 0 | 0 |
| subprocess-cli-testing | n/a | n/a | 0 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| body-oat | offline-agent-testing | offline-agent-testing | — | yes |
| body-oat | offline-agent-testing | offline-agent-testing | — | yes |
| body-oat | offline-agent-testing | offline-agent-testing | — | yes |
| body-acb | agent-context-budgeting | agent-context-budgeting | — | yes |
| body-acb | agent-context-budgeting | agent-context-budgeting | — | yes |
| body-acb | agent-context-budgeting | agent-context-budgeting | — | yes |
| body-fmk | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| body-fmk | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| body-fmk | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| body-sa | skill-authoring | skill-authoring | — | yes |
| body-sa | skill-authoring | skill-authoring | — | yes |
| body-sa | skill-authoring | skill-authoring | — | yes |

body-following: 6/12 cases fully followed; bundled files read 0/3; evidence matched 41/48

| case | fired | staged files touched | files | evidence | chars |
|---|---|---|---|---|---|
| body-oat | offline-agent-testing | — | 0/0 | 3/4 | 6753 |
| body-oat | offline-agent-testing | — | 0/0 | 3/4 | 6277 |
| body-oat | offline-agent-testing | — | 0/0 | 3/4 | 4198 |
| body-acb | agent-context-budgeting | — | 0/0 | 4/4 | 13972 |
| body-acb | agent-context-budgeting | — | 0/0 | 4/4 | 13502 |
| body-acb | agent-context-budgeting | — | 0/0 | 4/4 | 12984 |
| body-fmk | fuzz-mutate-kill-loop | — | 0/0 | 4/4 | 19860 |
| body-fmk | fuzz-mutate-kill-loop | — | 0/0 | 4/4 | 14872 |
| body-fmk | fuzz-mutate-kill-loop | — | 0/0 | 4/4 | 17954 |
| body-sa | skill-authoring | deploy-helper/SKILL.md | 0/1 | 3/4 | 5160 |
| body-sa | skill-authoring | — | 0/1 | 4/4 | 4730 |
| body-sa | skill-authoring | — | 0/1 | 1/4 | 4897 |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

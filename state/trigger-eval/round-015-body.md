# skill trigger eval — mode=body model=sonnet

probes: 16 ok, 0 errored, exact-match 100%, negatives false-fire 0/2, cost $1.647

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | 100% | 100% | 2 | 0 | 0 |
| fuzz-mutate-kill-loop | 100% | 100% | 2 | 0 | 0 |
| generator-trampoline-evaluator | 100% | 100% | 2 | 0 | 0 |
| llm-engine-benchmarking | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | 100% | 100% | 2 | 0 | 0 |
| shared-tip-immutable-lists | 100% | 100% | 2 | 0 | 0 |
| skill-authoring | 100% | 100% | 2 | 0 | 0 |
| subprocess-cli-testing | 100% | 100% | 2 | 0 | 0 |
| tiny-language-implementation | n/a | n/a | 0 | 0 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| body-oat | offline-agent-testing | offline-agent-testing | — | yes |
| body-oat | offline-agent-testing | offline-agent-testing | — | yes |
| body-gte | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| body-gte | generator-trampoline-evaluator | generator-trampoline-evaluator | — | yes |
| body-acb | agent-context-budgeting | agent-context-budgeting | — | yes |
| body-acb | agent-context-budgeting | agent-context-budgeting | — | yes |
| body-sct | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| body-sct | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| body-fmk | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| body-fmk | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| body-stil | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| body-stil | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| body-sa | skill-authoring | skill-authoring | — | yes |
| body-sa | skill-authoring | skill-authoring | — | yes |
| body-neg | — | — | — | yes |
| body-neg | — | — | — | yes |

body-following: 9/16 cases fully followed; bundled files read 0/2; evidence matched 48/56

| case | fired | staged files touched | files | evidence | chars |
|---|---|---|---|---|---|
| body-oat | offline-agent-testing | offline-agent-testing/harness/retry.py, offline-agent-testing | 0/0 | 3/4 | 5173 |
| body-oat | offline-agent-testing | offline-agent-testing, offline-agent-testing/SKILL.md | 0/0 | 3/4 | 5740 |
| body-gte | generator-trampoline-evaluator | — | 0/0 | 4/4 | 5849 |
| body-gte | generator-trampoline-evaluator | — | 0/0 | 4/4 | 5717 |
| body-acb | agent-context-budgeting | agent-context-budgeting/agentloop/context.py, agent-context-budgeting/agentloop/usage.py, agent-context-budgeting | 0/0 | 4/4 | 12790 |
| body-acb | agent-context-budgeting | agent-context-budgeting/agentloop/context.py, agent-context-budgeting/agentloop/usage.py, agent-context-budgeting/agentloop/agent.py | 0/0 | 4/4 | 14843 |
| body-sct | subprocess-cli-testing | — | 0/0 | 2/4 | 1219 |
| body-sct | subprocess-cli-testing | — | 0/0 | 4/4 | 5689 |
| body-fmk | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop/harness/swe/fuzz.py, fuzz-mutate-kill-loop/harness/swe/oracles.py, fuzz-mutate-kill-loop/harness/swe/mutation.py, fuzz-mutate-kill-loop/harness/swe/killers.py | 0/0 | 4/4 | 16866 |
| body-fmk | fuzz-mutate-kill-loop | — | 0/0 | 4/4 | 19572 |
| body-stil | shared-tip-immutable-lists | — | 0/0 | 3/4 | 5502 |
| body-stil | shared-tip-immutable-lists | — | 0/0 | 3/4 | 5278 |
| body-sa | skill-authoring | deploy-helper/SKILL.md | 0/1 | 3/4 | 4400 |
| body-sa | skill-authoring | — | 0/1 | 3/4 | 5265 |
| body-neg | — | — | 0/0 | 0/0 | 2761 |
| body-neg | — | — | 0/0 | 0/0 | 2395 |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

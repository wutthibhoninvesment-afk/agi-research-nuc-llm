# skill trigger eval — mode=native model=sonnet

probes: 20 ok, 0 errored, exact-match 70%, negatives false-fire 0/0, cost $0.568

| skill | recall | precision | tp | fp | fn |
|---|---|---|---|---|---|
| agent-context-budgeting | n/a | n/a | 0 | 0 | 0 |
| fuzz-mutate-kill-loop | 100% | 100% | 4 | 0 | 0 |
| generator-trampoline-evaluator | n/a | n/a | 0 | 0 | 0 |
| offline-agent-testing | 100% | 100% | 4 | 0 | 0 |
| shared-tip-immutable-lists | 25% | 100% | 1 | 0 | 3 |
| skill-authoring | n/a | n/a | 0 | 0 | 0 |
| subprocess-cli-testing | 62% | 100% | 5 | 0 | 3 |
| tiny-language-implementation | 100% | 100% | 4 | 0 | 0 |

| case | expect | fired | foreign | ok |
|---|---|---|---|---|
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| oat-far | offline-agent-testing | offline-agent-testing | — | yes |
| stil-far | shared-tip-immutable-lists | shared-tip-immutable-lists | — | yes |
| stil-far | shared-tip-immutable-lists | — | — | NO |
| stil-far | shared-tip-immutable-lists | — | — | NO |
| stil-far | shared-tip-immutable-lists | — | — | NO |
| fmk-far | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-far | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-far | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| fmk-far | fuzz-mutate-kill-loop | fuzz-mutate-kill-loop | — | yes |
| sct-far | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-far | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| sct-far | subprocess-cli-testing | — | — | NO |
| sct-far | subprocess-cli-testing | subprocess-cli-testing | — | yes |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | tiny-language-implementation | — | NO |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | tiny-language-implementation,subprocess-cli-testing | — | yes |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | tiny-language-implementation | — | NO |
| multi-1 | tiny-language-implementation,subprocess-cli-testing | tiny-language-implementation,subprocess-cli-testing | — | yes |

host distractor skills present: __remote-workflow, agents, auto-mode-setup, autocompact, batch, claude-api, clear, code-review, color, compact, config, context, dataviz, debug, deep-research, design, design-consent, design-revoke, design-sync, doctor, effort, extra-usage, fast, fewer-permission-prompts, goal, heapdump, import, init, insights, list-agents, loop, mcp, model, recap, reload-skills, rename, run, run-skill-generator, schedule, security-review, simplify, team-onboarding, ultrareview, update-config, usage, usage-credits, verify, workflow-launch-exec

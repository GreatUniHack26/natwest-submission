# Rehearsal and code freeze (issue #34)

## Code freeze
At the start of rehearsal (T+4:15), post in the team chat:
> Code freeze. No merges to main except demo-breaking fixes, approved by the Presenter. Everyone pull main now.

## Two timed rehearsals
| Run | Total time | Over/under | What broke | Fix owner |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |

Target: 4:00 including demo. If over, cut the alert step first (see the 3-minute version in `demo_script.md`).

## Q&A owners
| Topic | Owner |
|---|---|
| Data and personas (synthetic data, categorisation) | P1 ______ |
| Forecast maths (projection, range, safe to spend) | P2 ______ |
| AI (tools, guardrails, tone, voice) | P3 ______ |
| Frontend and accessibility | P4 ______ |
| Impact, ethics, roadmap, business case | P5 ______ |

Rule: the owner answers in under 30 seconds, then stops. Nobody else jumps in unless asked.

## Final commit
```
git checkout main && git pull
git tag demo-final
git push origin demo-final
```
Everyone checks out `demo-final` on their laptop before walking on stage. [ ] Tagged  [ ] All laptops on it

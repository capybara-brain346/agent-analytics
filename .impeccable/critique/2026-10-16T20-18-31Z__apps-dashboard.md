---
target: apps/dashboard
total_score: 28
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 0
target_identity: "file:/home/capybara/code/agent-analytics/apps/dashboard"
timestamp: 2026-10-16T20-18-31Z
slug: apps-dashboard
---
Method: dual-agent (A: isolated design review, run 3 · B: detector + scripted browser checks)

| # | Heuristic | Score |
|---|---|---|
| 1 | Visibility of system status | 3 |
| 2 | Match system / real world | 3 |
| 3 | User control and freedom | 3 |
| 4 | Consistency and standards | 2 |
| 5 | Error prevention | 2 |
| 6 | Recognition rather than recall | 3 |
| 7 | Flexibility and efficiency | 3 |
| 8 | Aesthetic and minimalist design | 3 |
| 9 | Error recovery | 3 |
| 10 | Help and documentation | 3 |
| Total | | 28/40 (Good) |

Scored before the loop-3 fixes. Fixed after scoring: empty drill-down links (142 links verified non-empty), range/class on Agents/Pages/Recommendations, session confidence column, chart values and axis, KPI change values, tab counts, mobile touch targets (185 -> 2 under 24px), legend under class filter.
Open: no column sorting or row keyboard navigation; repeated sample values (client IP, verdict row #204, referrer); pipeline id "run-14" vs recommendation run #14; sheet trail lost on refresh.

---
target: apps/dashboard
total_score: 25
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:/home/capybara/code/agent-analytics/apps/dashboard"
timestamp: 2026-10-16T19-33-22Z
slug: apps-dashboard
---
Method: dual-agent (A: design review · B: detector + browser)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | No sheet trail; compact chart ignores filters |
| 2 | Match system / real world | 3 | events vs requests; "Next action" tagged Unknown |
| 3 | User control and freedom | 2 | Close discards chain; Back reopens closed sheet; tabs drop filters |
| 4 | Consistency and standards | 2 | Same count links to different filters; 4 label-guide entries; tab types differ |
| 5 | Error prevention | 2 | Evidence links land on empty results; hidden verdict filter |
| 6 | Recognition rather than recall | 2 | Evidence lists carry no recommendation context |
| 7 | Flexibility and efficiency | 2 | 576 chart tab stops; no in-sheet back |
| 8 | Aesthetic and minimalist design | 3 | Repeated disclaimers; slogans; fake disabled actions |
| 9 | Error recovery | 3 | Empty state does not name the filter |
| 10 | Help and documentation | 3 | Label guide, tips, fact bundle |
| Total | | 25/40 | Acceptable |

Priority issues
- [P1] Recommendation evidence links do not land on that recommendation's evidence (details.tsx:901-913, sections.tsx:195-215).
- [P1] Sheet history: no trail, close leaves stale entries, Back reopens closed sheets (dashboard.tsx:98-123).
- [P2] Filter state lost or hidden: tabs drop filters, verdict/bucket params invisible or ignored, totals ignore filters.
- [P2] Traffic chart: 576 SVG links in tab order, full reloads; select focus invisible; 7-9px clickable text.
- [P3] Misleading affordances: workspace switch opens label guide, static profile chevron, fake Generate/Upload buttons, decorative help icon, inconsistent run history links.

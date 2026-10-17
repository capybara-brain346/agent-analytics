# Day 1 Research Plan

Source: `task.pdf`, Section 06 (Research mandate), pages 7–8.

## PDF guidelines

| Rule | Meaning |
|---|---|
| Research justifies the architecture; it is not the deliverable | Research only what changes a decision |
| Spend Day 1 on it, then build | One day, with a firm time limit |
| Prefer official documentation, standards and security guidance | Vendor docs, IETF/RFC, OWASP. Avoid blogs and guesses |
| Log each source with the decision it informed | Every source links to a decision |

## Topics (sorted by priority, about 8 hours)

| # | Topic | PDF ref | Time | Why it matters | Decision it informs |
|---|---|---|---|---|---|
| 1 | Agent identity and verification | Q1, Q2, Q4 · §02 trap 3 | 3 h | Every number, pattern and recommendation depends on correct identity (data integrity) | Classifier rules, claimed vs verified, confidence levels |
| 2 | What each data source can see | Q3 · §03.A | 1 h | We must choose one collection path and state its blind spots | Which collection path we build; the "Unknown" list |
| 3 | Privacy, security, retention | Q7 · §05 | 1 h | Enterprise buyers (e.g. banks) check this first. Logs can contain personal data | What we mask, drop and keep, and for how long |
| 4 | Demo data with the 5 patterns | §01 proving ground · §09 | 1 h | With no patterns in the data, there are no recommendations | Dataset or controlled site for the demo |
| 5 | Sessionisation limits | Q5 · §03.C | 45 min | Prevents false "journeys" (same IP ≠ same agent) | When to group logs, and when not to |
| 6 | Event format standards | Q6 · §03.B · §05 Deployment | 30 min | A neutral, extensible format avoids vendor lock-in | Shape of the common log format |
| 7 | Open-source tools | Q8 | 45 min | Saves build time | What we reuse vs build |

> Note: times are estimates, not from the PDF. Topic 4 is not in the PDF research list, but the main deliverable fails without it.

## Subtopics

### 1. Agent identity and verification (3 h)

| # | Subtopic | PDF source |
|---|---|---|
| 1.1 | How major AI crawlers name themselves (User-Agent strings, published docs) | Q1 |
| 1.2 | How search crawlers name themselves and how to verify them (reverse DNS, published IP ranges) | Q2 · §02 trap 3 |
| 1.3 | Which AI crawlers publish IP ranges or other verification methods, and which do not | Q2 |
| 1.4 | How documented agent clients (agents acting for a user) identify themselves | Q1 |
| 1.5 | How browser-based agents can or cannot be told apart from humans | Q4 · §03.B class 4 |
| 1.6 | Where User-Agent detection fails: spoofing, missing UAs, generic UAs | Q2 · §02 trap 3 |
| 1.7 | New standards for signed / verifiable agent requests | Q2 |
| 1.8 | How to express confidence (what evidence gives high, medium or low) | §03.B Verdict |

### 2. Data source visibility (1 h)

| # | Subtopic | PDF source |
|---|---|---|
| 2.1 | Server / app access logs: fields available, what is missing | §03.A table |
| 2.2 | CDN / proxy / WAF logs: block events, bot signals, vendor formats | §03.A table |
| 2.3 | JS snippet: what it sees; which agents do not run JavaScript | §03.A table |
| 2.4 | Middleware / app hooks: workflow steps | §03.A table |
| 2.5 | Structured import (JSON/CSV): fastest path for the MVP | §03.A table |
| 2.6 | Comparison on coverage, effort, accuracy, privacy, cost, enterprise fit | §03.A text |
| 2.7 | Response fields each hop logs: status, bytes, response time, Content-Type, Location, cache status, edge vs origin status | §03.B table · §03.C |

### 3. Privacy, security, retention (1 h)

| # | Subtopic | PDF source |
|---|---|---|
| 3.1 | Is an IP address personal data? Best way to mask or hash it | §05 Privacy |
| 3.2 | Removing secrets and PII from query strings | §05 Privacy |
| 3.3 | Never capturing passwords, tokens, payment data, form values | §05 · §03.C |
| 3.4 | Retention and deletion practice for analytics data | §05 Privacy · Q7 |
| 3.5 | Access control for the dashboard | §05 Privacy |
| 3.6 | Input validation for malformed or hostile log lines | §05 Privacy · Reliability |

### 4. Demo data (1 h)

| # | Subtopic | PDF source |
|---|---|---|
| 4.1 | Public access-log datasets that contain real bot and agent traffic | §01 proving ground |
| 4.2 | Option: a small controlled site that Webzero owns, to capture real traffic | §01 · §08 Day 5 |
| 4.3 | Check that the data can produce all 5 patterns (incl. 403s, dead ends, loops) | §04 patterns |
| 4.4 | Spoofed-UA cases to test verification | §08 Day 2 "spoofed-UA fixtures" |
| 4.5 | Soft-failure cases: 200 with error page, challenge page, empty JS shell, login wall | §02 trap 2 |

### 5. Sessionisation (45 min)

| # | Subtopic | PDF source |
|---|---|---|
| 5.1 | Common grouping methods (time gaps, source + client) and their failures | Q5 |
| 5.2 | Why the same IP ≠ the same agent (shared IPs, cloud ranges, NAT) | §03.C |
| 5.3 | Why close in time ≠ the same journey | §03.C |
| 5.4 | What confidence to give a session, and how to show the gaps | §03.C |

### 6. Event format standards (30 min)

| # | Subtopic | PDF source |
|---|---|---|
| 6.1 | OpenTelemetry HTTP semantic conventions | Q6 |
| 6.2 | Common log formats (e.g. Combined Log Format) as input | Q6 · §03.A |
| 6.3 | Fields needed: Request · Client · Verdict | §03.B table |
| 6.4 | Response fields in the schema, and how to flag a suspected soft failure (200 ≠ success) | §02 trap 2 · §03.B |

### 7. Open-source tools (45 min)

| # | Subtopic | PDF source |
|---|---|---|
| 7.1 | Maintained bot / crawler signature lists we can reuse | Q8 · §03.B registry |
| 7.2 | Log parsers for common formats | Q8 |
| 7.3 | User-Agent parsers | Q8 |
| 7.4 | Licence check (must be safe for enterprise use) | Q8 · §05 Deployment |

## Day 1 outputs

| Output | Content |
|---|---|
| Research log | Source → finding → decision (required by §06) |
| ADR | The main choices and the reasons for them |
| Known limits | What we cannot detect or verify. Feeds the "Unknown" label |

## Research log (fill in during Day 1)

| # | Topic | Source (link) | Finding | Decision informed |
|---|---|---|---|---|
| | | | | |

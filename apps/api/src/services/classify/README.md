# classify

Gives each new verdict a `TrafficClass` (1–6) and a confidence.

- `rules.py`: `classify()`. Ordered rules, first match wins. Pure function. Change `RULE_VERSION` when a rule changes.
- `ua.py`: user-agent type (headless, library, bot, browser).
- `service.py`: `classify_new_verdicts`: reads unclassified verdicts, saves classes.

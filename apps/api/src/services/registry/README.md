# registry

Known-bot data from `config/registry/` (YAML, reloaded when the file changes).

- `match_user_agent`: UA → `BotEntry` (name, category, how to verify).
- `is_shared_ip`: shared / CGN ranges. An IP match there does not prove identity.

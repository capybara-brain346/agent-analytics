# verify

Checks if a client is the bot that its user agent claims.

```
new client groups ──► registry match ──► IP list or reverse DNS ──► verdict
                                                                     VERIFIED | CLAIMED | UNVERIFIED | SPOOFED | UNKNOWN
```

- `service.py`: `verify_new_clients`. Reuses a recent verdict for the same client. DNS calls are concurrent (cap 20).
- `ip_lists.py`: downloads vendor IP-range snapshots, stores a new version only on change. Bots can share a source: ClaudeBot, Claude-User and Claude-SearchBot all use `anthropic.json` (Anthropic publishes one list and no reverse DNS names).

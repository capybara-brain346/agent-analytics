# recommendations

Session data → ranked recommendations with text.

```
find_candidates (P1–P5 SQL) ──► scoring ──► build_bundle (facts) ──► text ──► store
                                                                    │
                                                         template, or LLM if valid
```

- `service.py`: `generate(conn, site_id, window)`. Stable IDs, comparison with the last run.
- `scoring.py`: impact × frequency × severity × confidence. Each factor is shown in the UI.
- `text.py`: template text, and `validate_llm_text`: rejects LLM text with numbers, paths or agents not in the bundle.
- `llm.py`: OpenRouter client. Off if no key. The LLM sees the fact bundle only, never raw events.

# ingest

Push upload (`POST /ingest`). Checks a chunk, then writes it to the S3 inbox.

- Checks: site token, per-site rate limit, daily byte quota, size limit, empty body.
- `object_key()`: inbox path for the chunk. The importer reads it later.
- Rate windows are in process memory (one API process = one counter).

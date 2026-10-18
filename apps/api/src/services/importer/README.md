# importer

Inbox files → rows in `events`.

```
bucket_reader ──► import_files (status new) ──► import_due_files ──► adapters ──► dedupe ──► COPY events
  (customer bucket)                               (claim, stream lines)   (parse)    (line key)    + rejects
```

- `service.py`: `import_due_files` (pipeline step), `import_local_file` (CLI). Batches, retries, progress.
- `bucket_reader.py`: lists the customer CDN buckets set in site config and registers new objects.
- `dedupe.py`: stable key for each line, so a re-import does not double rows.
- `adapters/`: one parser for each log source.

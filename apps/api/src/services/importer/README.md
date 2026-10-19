# importer

Inbox files → rows in `events`.

```
bucket_reader ──► import_files (status new) ──► import_due_files ──► adapters ──► dedupe ──► COPY events
  (customer bucket)                               (claim, stream lines)   (parse)    (line key)    + rejects
```

- `service.py`: `import_due_files` (pipeline step), `import_local_file` (CLI). Batches, retries, progress.
- `delete.py`: `delete_import` (`DELETE /api/imports/{id}`). Removes a file's events and row under the site's fast-lane lock, reads paired partner files again, resets the site's views (decision 1.21).
- `log_names.py`: the sample log file name rule (`samples/logs/README.md`), used by the CLI folder import.
- `bucket_reader.py`: lists the customer CDN buckets set in site config and registers new objects.
- `dedupe.py`: stable key for each line, so a re-import does not double rows.
- `adapters/`: one parser for each log source.

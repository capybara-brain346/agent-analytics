# cleanup

Daily maintenance (worker or `cli cleanup`).

- Deletes inbox objects of imported files after the retention days.
- Drops old `events_YYYYMMDD` partitions.
- Creates the partitions for the next days.

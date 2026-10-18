# pairing

Joins a CDN event and its origin event (same request ID) into one request.

`pair_events`: pairs pending rows, then expires rows that wait longer than the pairing window. SQL is in `store.pairing`.

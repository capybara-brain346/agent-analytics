# reconstruction

Activity reconstruction. `update_views`: new ready events → sessions + hourly rollups.

Incremental: only clients with new events are rebuilt. Design notes and SQL are in `store/views.py`.

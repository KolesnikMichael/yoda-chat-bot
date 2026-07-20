# TASK-007 implementation notes

## Test fixture discoveries

### `timeout_only_compression_settings()`

With `low_compression_settings()` (`size_trigger_threshold=4`, entry guard `> 2*min_chunk_length=4`), any conversation that qualifies for the timeout predicate also qualifies for the size trigger. Timeout-only tests need an elevated `size_trigger_threshold` (300) so the `elif "timeout"` branch is reachable.

### Timestamp alignment for cross-trigger tests

`has_visible_activity_since_compression` compares `last_visible_at` (message timestamps) against `last_compressed_at` (snapshot `time.time()`). Cross-trigger fixtures that mix `build_compressible_conversation` (January dates) with unpatched `time.time()` on tick 1 leave `last_compressed_at` far ahead of message times, blocking tick-2 timeout. Fix: patch `time.time()` on every apply tick and set `last_compressed_at` explicitly before follow-up ticks when appending new messages.

### Continuous-burst gaps

With `tick_minutes=1`, `gap_threshold_seconds=240`. Hourly `_ts()` spacing in burst fixtures exceeds the threshold and incorrectly triggers compression. Burst fixtures use `_ts_seconds()` with ≤30s inter-visible spacing.

## Plan feedback

Step 2.1 could note that timeout-only tests require `size_trigger_threshold` above the fixture's `visible_messages` count, or a dedicated settings helper.

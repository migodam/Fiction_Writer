# W1 Live Canary Harness Stall Root Cause and Fix

Date: 2026-07-25

## Scope

- No external API request was made during this repair.
- Evidence run:
  `/tmp/narrative_ide_w1_flash_canary_final_20260725/20260725_062341`
- Changed surfaces:
  `tools/w1_live_smoke_10ch.py`, W1 runtime activity, RuntimeStore lease
  cleanup, product W1 heartbeat, and tests.

## Root-Cause Chain

1. The old live runner called `w1_import.run_streaming()` directly.
2. It supplied a string `session_id`, but did not create a RuntimeStore run,
   attempt, lease, or `bind_runtime()` binding.
3. Because it did not set product `execution_mode=supervisor` or
   `harness_observer=true`, the stream also bypassed `W1AgenticAdapter`.
4. Provider calls could update only the process-local `w1_run_events` feed.
   `begin_provider_call()` had no RuntimeStore binding and therefore returned
   an unmanaged intent.
5. The watchdog observed only graph state yields. It did not read
   `w1_run_events`, RuntimeStore event sequence, active provider calls, or the
   lease heartbeat.
6. W1 yielded `validate_file` and `split_chunks`, then entered extraction.
   While the provider boundary was still pending, there was no new graph
   yield for 120 seconds, so a live operation was misclassified as a silent
   stream.
7. The runner cancelled the async generator directly. It did not execute the
   product `_run_w1()` cleanup owner, so `workflow.lock` remained.
8. With no durable provider intent, cancellation could not create an
   `unknown_outcome`; with no completed response, no usage ledger or import
   artifact existed.

The evidence does not prove that three provider requests were concurrently in
flight. The old run left no durable intent records, and the current fail-closed
budget path executes extraction prompts sequentially. The defensible finding
is that the run was inside its first unresolved extraction/provider boundary.

## Evidence

- `updates.json` contains only `validate_file` and `split_chunks`.
- `heartbeat.json` reports `last_update_age=120.004`.
- `final_result.json` reports no import directory, usage ledger, or required
  import artifacts.
- The project has no `system/runtime/agent_runtime.db` from that attempt.
- `workflow.lock` remained with PID `11788`; that PID no longer exists.

## Fix

- The live runner now creates a durable W1 run, attempt, thread, lineage,
  owner lease, and fenced RuntimeStore binding before streaming.
- It uses the server-normalized W1 budget policy and cannot raise the existing
  Flash `$3`, 100-call, token, or 1800-second limits.
- It explicitly selects the product supervisor execution mode and Harness
  observer.
- Provider intent is persisted before network I/O. Cancelling an in-flight
  provider boundary records `unknown_outcome` and leaves the attempt at
  `waiting_human`; no automatic retry is added.
- Provider wait heartbeats are shared by CLI and Electron product runs. They
  are durable events and are emitted only when `active_api_calls > 0`.
- The watchdog advances on durable event sequence or graph updates. Its own
  heartbeat file is not treated as work activity.
- Activity polling is pure read. A discovered feedback loop where usage
  inspection generated its own “unknown pricing” event was removed.
- A truly silent run still stops at the silence deadline.
- Stall, timeout, and cancellation paths release `workflow.lock`, fence and
  expire the runtime lease, close remaining intents as unknown, and write:
  attempt status, unknown-call summaries, usage, last durable activity,
  active intents, lock state, and process model.
- Product `_run_w1()` now also releases its fenced lease in `finally`.

## Verification

- `pytest tests/test_w1_*.py`: 874 passed.
- Runtime/adapter focused suite: 85 passed.
- Live runner/runtime/token focused suite: 92 passed.
- Slow provider beyond the silence threshold with durable activity: passes
  without false stall.
- Truly silent stream: stops as `stalled`, releases lock and lease.
- Cancel during provider I/O: intent becomes `unknown_outcome`, attempt becomes
  `waiting_human`, no automatic retry occurs.
- `py_compile`: passed for all changed Python modules.
- `git diff --check`: passed.

## Residual Boundary

The runner remains an in-process CLI adapter, so it has no child process to
terminate. The outer `gtimeout --signal=TERM --kill-after=30s 1830s` remains
the final OS-level guard. In-process cancellation is bounded and its cleanup
state is persisted before the CLI exits.

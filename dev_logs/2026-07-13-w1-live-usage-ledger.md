# W1 Live Usage Ledger Closure

## Scope

Close the W1 supervisor live-run usage/cost ledger gap without making provider calls.

## Root Cause

`sidecar/supervisor/tools.py` resolved `session_id` for activity events in
`_invoke_window_prompt_with_activity`, but did not forward it to
`_invoke_json_prompt`. Its primary extraction calls consequently skipped
`_ainvoke_with_budget`, which is the only provider-call wrapper that records
real response usage. The completed run therefore had no durable usage ledger.

The old post-call behavior also marked missing provider usage as exhausted but
returned the provider response; the next call was blocked instead. That was not
fail-closed for the call whose usage was absent.

## Changes

- Forward the supervisor `session_id` to every wrapped extraction prompt.
- Count every completed provider call, including one missing token metadata,
  then fail the same call closed when `fail_on_missing_usage` is enabled.
- Add `w1_usage_ledger/v1` as `usage_ledger.json`: non-secret actual input and
  output tokens, `actual_calls`, `api_call_count` compatibility alias, cost,
  model, pricing, and budget status.
- Persist the ledger after segmentation, on cancellation/budget exits, and
  after proposal-write synthesis calls.
- Make the live smoke probe consume only the production ledger artifact and
  accept `api_call_count` as a call-count alias.

## Reviewer Hardening

- Reserve budget capacity under a per-ledger lock before provider I/O; completed
  calls settle reservations and provider exceptions release them. Transient
  reservation contention does not permanently cancel the session.
- Write `usage_ledger.json` with same-directory temporary file, flush/fsync,
  and atomic replace.
- Give each smoke invocation a unique explicit `import_run_id`; the probe reads
  only that run, including with `--reuse-project`.
- Redact terminal exception payloads before `final_result.json` is written and
  scan that file immediately after write.
- Reject usage ledgers unless token/call counts are nonnegative integers and
  cost is a finite nonnegative number.

## Verification

No live provider or network calls were made.

```text
sidecar/.venv/bin/python -m pytest -q \
  tests/test_w1_token_ledger.py \
  tests/test_w1_backend_contract.py \
  tests/test_w1_live_smoke_runner.py \
  tests/test_w1_supervisor_tools.py
# 115 passed in 0.97s

sidecar/.venv/bin/python -m pytest -q \
  tests/test_w1_supervisor_policy.py \
  tests/test_w1_import_compiler.py
# 117 passed in 2.35s

sidecar/.venv/bin/python -m compileall -q \
  sidecar/workflows/w1_run_events.py \
  sidecar/workflows/w1_import.py \
  sidecar/supervisor/policy.py \
  sidecar/supervisor/tools.py \
  tools/w1_live_smoke_10ch.py
# passed

git diff --check
# passed
```

## Remaining Verification

Run the complete local `tests/test_w1_*.py` suite. A live smoke rerun is
intentionally deferred because this change was verified with no paid/network
calls.

Completed after this log was created:

```text
sidecar/.venv/bin/python -m pytest -q tests/test_w1_*.py
# 629 passed in 8.32s
```

Reviewer-hardening focused verification:

```text
sidecar/.venv/bin/python -m pytest -q \
  tests/test_w1_token_ledger.py \
  tests/test_w1_backend_contract.py \
  tests/test_w1_live_smoke_runner.py \
  tests/test_w1_supervisor_tools.py \
  tests/test_w1_supervisor_policy.py \
  tests/test_w1_import_compiler.py
# 236 passed in 3.02s
```

Final complete W1 verification after the reviewer hardening:

```text
sidecar/.venv/bin/python -m pytest -q tests/test_w1_*.py
# 633 passed in 8.35s
```

## Reservation Identity Follow-up

Lead review found that FIFO reservation settlement could remove the wrong
estimate when concurrent responses completed out of order. Reservations are now
stored by caller-owned token. The production provider wrapper passes that token
through settlement and exception release; the existing boolean API binds its
token to the current async context for compatibility.

The focused reverse-order test reserves 70 and 20 input tokens, settles the
20-token call first, and verifies the 70-token in-flight reservation remains in
the remaining-budget calculation. An additional 11-token reservation is denied
against the 100-token limit, while a 10-token reservation is accepted.

```text
sidecar/.venv/bin/python -m pytest -q \
  tests/test_w1_token_ledger.py \
  tests/test_w1_backend_contract.py \
  tests/test_w1_live_smoke_runner.py \
  tests/test_w1_supervisor_tools.py \
  tests/test_w1_supervisor_policy.py \
  tests/test_w1_import_compiler.py
# 237 passed in 3.17s
```

```text
sidecar/.venv/bin/python -m pytest -q tests/test_w1_*.py
# 634 passed in 9.08s
```

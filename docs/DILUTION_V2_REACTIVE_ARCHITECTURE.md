# Dilution V2 Reactive Architecture

This document describes the production path for the new dilution architecture.

## Goal

Process each new SEC filing reactively and apply deterministic, auditable updates to dilution instruments.

## Event Flow

1. `sec-filings` publishes new events to `stream:sec:filings`.
2. `dilution-tracker` `ReactiveFilingConsumerV2` consumes stream events.
3. Consumer filters by ticker universe (`tickers` table in `dilutiontracker` DB).
4. Matching filings are forwarded to `stream:dilution:v2:filings`.
5. The same filing is logged in `filing_events` (`agent_action=LOG`) with payload for traceability.
6. `ReactiveFilingOrchestratorV2` consumes `stream:dilution:v2:filings`.
7. Orchestrator builds a deterministic action batch from filing + instrument context.
8. If confidence is below threshold or mapping is ambiguous, it publishes to `stream:dilution:v2:ambiguous`.
9. Otherwise it submits action batch to `/api/dilution-v2/actions/apply` (`dry_run=false`).
10. Transactional applier updates `instruments` + detail tables and records `filing_events`.

## Context Assembly

The context endpoint for decisioning is:

- `GET /api/instrument-context/{ticker}`

It returns:

- `ticker_info` (`tickers`)
- all typed `instruments` with detail payloads from:
  - `atm_details`
  - `shelf_details`
  - `warrant_details`
  - `conv_note_details`
  - `conv_preferred_details`
  - `equity_line_details`
  - `s1_offering_details`
- `completed_offerings`
- aggregate stats

## Write Path (Agent Commands)

Endpoint:

- `POST /api/dilution-v2/actions/apply`

Contract:

- `dry_run=true`: validates and previews changes without persisting.
- `dry_run=false`: applies changes in a DB transaction.

Supported actions:

- `create_instrument`
- `update_instrument`
- `state_transition`
- `log_only`

Each successful apply writes trace events into `filing_events`.

## Ambiguous Review API

When orchestrator confidence is below threshold or mapping is ambiguous, filings are pushed to:

- `stream:dilution:v2:ambiguous`

Review endpoints:

- `GET /api/dilution-v2/review/ambiguous` (list pending ambiguous filings)
- `POST /api/dilution-v2/review/ambiguous/requeue` (requeue one filing to orchestrator stream)
- `POST /api/dilution-v2/review/ambiguous/resolve` (mark reviewed without requeue)
- `POST /api/dilution-v2/review/ambiguous/apply` (manual apply action batch + review audit)

Review decisions are audited in:

- `stream:dilution:v2:reviewed`

## Safety Properties

- Ticker guard: actions only apply if ticker exists in `tickers`.
- Instrument guard: update/transition requires instrument bound to the same ticker.
- Detail field allow-lists by `offering_type`.
- Idempotent filing logging with `ON CONFLICT (accession_number) DO NOTHING`.
- Full `dry_run` mode for safe testing in prod-like environments.

## Runtime Flags

Reactive consumer is controlled by:

- `dilution_reactive_enabled=true`

Orchestrator worker is controlled by:

- `dilution_orchestrator_enabled=true`

Optional confidence threshold:

- `dilution_v2_min_apply_confidence=0.70`

When enabled, both workers start/stop with FastAPI lifespan.

## Next Production Steps

- Expand orchestrator rules beyond deterministic transitions (agent-assisted matching).
- Add reviewer UI/worker for `stream:dilution:v2:ambiguous`.
- Add metrics dashboard:
  - filings accepted/rejected
  - auto-apply rate
  - ambiguous rate
  - apply failures by action type
- Complete frontend migration off legacy dilution terminal.

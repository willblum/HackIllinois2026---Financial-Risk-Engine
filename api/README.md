# API Contracts

This folder is the single source of truth for every interface between teams.
Read only the file(s) relevant to your boundary.

```
┌─────────────┐  model_contract.py  ┌─────────────┐  rest_api.md + client.js  ┌──────────────┐
│    model/   │ ──────────────────► │   backend/  │ ────────────────────────► │  frontend/   │
│  modal_app  │                     │   FastAPI   │                            │  HTML/JS     │
└─────────────┘                     └─────────────┘                            └──────────────┘
```

## Files

| File | Who reads it | What it defines |
|---|---|---|
| `model_contract.py` | **model team** (must implement), **backend team** (calls it) | Python ABCs for `LLM` and `Embedder` Modal classes + prompt I/O contracts |
| `schemas.py` | **backend team** (must implement), anyone who wants exact shapes | Pydantic models for every request and response body |
| `rest_api.md` | **backend team** (must implement), **frontend team** (calls it) | Every REST endpoint: method, path, params, request, response |
| `sse_events.md` | **backend team** (must emit), **frontend team** (must handle) | SSE event stream format and recommended frontend behavior |
| `client.js` | **frontend team** (copy into `frontend/`) | Ready-to-use JS fetch wrappers for every endpoint + SSE |

## Base URL

```
http://localhost:8000
```

## Shared Data Shape — NarrativeDirection

Both the backend API responses and the frontend UI are built around this object.

```json
{
  "id": "uuid-string",
  "name": "Energy supply shock",
  "description": "Ongoing deterioration of Russian gas exports disrupting European energy markets",
  "event_count": 41,
  "current_surprise": 0.81,
  "current_impact": 0.74,
  "model_risk": 0.77,
  "last_updated": 1709123456.789,
  "is_active": true,
  "surprise_trend": "rising",
  "impact_trend": "stable",
  "recent_headlines": [
    "Russia halts gas transit through Ukraine",
    "Germany activates emergency energy rationing"
  ]
}
```

`model_risk = sqrt(surprise × impact)` — computed on read, not stored.
`is_active` — true if updated within the last 48 hours.
`surprise_trend / impact_trend` — `"rising"` | `"falling"` | `"stable"` | `null`

## Risk Index Interpretation

| Range | Label | Meaning |
|---|---|---|
| 0.00 – 0.33 | LOW | Markets behaving statistically. Models reliable. |
| 0.34 – 0.66 | MEDIUM | Narratives building. Monitor closely. |
| 0.67 – 1.00 | HIGH | Regime shift. Model fragility. Discount quant signals. |

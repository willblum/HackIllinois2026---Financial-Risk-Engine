/**
 * API Client — Real-World Model Risk Engine
 * ==========================================
 * Ready-to-use fetch wrappers for every backend endpoint.
 * Copy this file into frontend/ or import it as a module.
 *
 * Usage:
 *   const risk = await api.getRisk();
 *   const results = await api.searchNarratives("sanctions affecting energy");
 *   api.streamEvents((event) => console.log(event));
 */

const BASE_URL = "http://localhost:8000";

// ---------------------------------------------------------------------------
// Core helpers
// ---------------------------------------------------------------------------

async function _get(path, params = {}) {
  const url = new URL(`${BASE_URL}${path}`);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, v);
  });
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`GET ${path} → ${res.status} ${res.statusText}`);
  return res.json();
}

async function _post(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status} ${res.statusText}`);
  return res.json();
}

async function _delete(path) {
  const res = await fetch(`${BASE_URL}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE ${path} → ${res.status} ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

/**
 * @returns {{ status: "ok" }}
 */
export async function getHealth() {
  return _get("/health");
}

// ---------------------------------------------------------------------------
// Ingest
// ---------------------------------------------------------------------------

/**
 * Ingest a single news story.
 *
 * @param {string} headline
 * @param {string} [body=""]
 * @param {string} [source="manual"]
 * @returns {Promise<{
 *   action: "created"|"updated",
 *   narrative_id: string,
 *   narrative_name: string,
 *   best_distance: number|null,
 *   threshold: number,
 *   current_surprise: number,
 *   current_impact: number,
 *   model_risk: number,
 *   narrative_event_count: number
 * }>}
 */
export async function ingestStory(headline, body = "", source = "manual") {
  return _post("/api/ingest", { headline, body, source });
}

/**
 * Ingest multiple stories at once.
 *
 * @param {{ headline: string, body?: string }[]} stories
 * @param {number} [maxStories=50]
 * @returns {Promise<{ processed: number, results: object[], errors: string[], duration_seconds: number }>}
 */
export async function ingestBatch(stories, maxStories = 50) {
  return _post("/api/ingest/batch", { stories, max_stories: maxStories });
}

// ---------------------------------------------------------------------------
// Narratives
// ---------------------------------------------------------------------------

/**
 * List narrative directions.
 *
 * @param {{ activeOnly?: boolean, sortBy?: "risk"|"events"|"updated"|"created", limit?: number }} [opts]
 * @returns {Promise<{ narratives: object[], total: number }>}
 */
export async function getNarratives({ activeOnly = false, sortBy = "risk", limit = 50 } = {}) {
  return _get("/api/narratives", { active_only: activeOnly, sort_by: sortBy, limit });
}

/**
 * Get full detail for one narrative (includes complete time series).
 *
 * @param {string} narrativeId
 * @returns {Promise<object>}
 */
export async function getNarrative(narrativeId) {
  return _get(`/api/narratives/${narrativeId}`);
}

/**
 * Get chart-ready time series for one narrative.
 * Returns surprise_series, impact_series, and model_risk_series arrays.
 *
 * @param {string} narrativeId
 * @returns {Promise<{
 *   id: string,
 *   name: string,
 *   description: string,
 *   surprise_series: {timestamp: number, value: number}[],
 *   impact_series: {timestamp: number, value: number}[],
 *   model_risk_series: {timestamp: number, value: number}[],
 *   event_count: number,
 *   recent_headlines: string[]
 * }>}
 */
export async function getNarrativeHistory(narrativeId) {
  return _get(`/api/narratives/${narrativeId}/history`);
}

/**
 * Semantic search — find narrative directions closest in meaning to a query.
 *
 * @param {string} query  natural language query, e.g. "sanctions affecting energy exports"
 * @param {number} [nResults=5]
 * @param {boolean} [activeOnly=false]
 * @returns {Promise<{
 *   query: string,
 *   results: { narrative: object, distance: number, similarity: number }[],
 *   total: number
 * }>}
 */
export async function searchNarratives(query, nResults = 5, activeOnly = false) {
  return _post("/api/narratives/search", {
    query,
    n_results: nResults,
    active_only: activeOnly,
  });
}

/**
 * Delete a narrative direction.
 *
 * @param {string} narrativeId
 * @returns {Promise<{ deleted: boolean, id: string }>}
 */
export async function deleteNarrative(narrativeId) {
  return _delete(`/api/narratives/${narrativeId}`);
}

// ---------------------------------------------------------------------------
// Risk Index
// ---------------------------------------------------------------------------

/**
 * Get the global Real-World Model Risk Index.
 *
 * @param {{ method?: "max"|"mean"|"weighted", activeOnly?: boolean }} [opts]
 * @returns {Promise<{
 *   model_risk_index: number|null,
 *   narrative_count: number,
 *   active_narrative_count: number,
 *   breakdown: object[],
 *   aggregation_method: string,
 *   computed_at: number
 * }>}
 *
 * Interpretation:
 *   0.00–0.33  LOW    — markets behaving statistically, models reliable
 *   0.34–0.66  MEDIUM — narratives building, monitor closely
 *   0.67–1.00  HIGH   — regime shift / model fragility
 */
export async function getRisk({ method = "max", activeOnly = false } = {}) {
  return _get("/api/risk", { method, active_only: activeOnly });
}

/**
 * Get historical risk index for charting.
 *
 * @param {number} [windowHours=24]   look-back window (1–168)
 * @param {number} [resolution=100]   number of data points (10–500)
 * @returns {Promise<{
 *   history: { timestamp: number, model_risk_index: number|null }[],
 *   window_hours: number,
 *   resolution: number,
 *   start_time: number,
 *   end_time: number
 * }>}
 */
export async function getRiskHistory(windowHours = 24, resolution = 100) {
  return _get("/api/risk/history", { window: windowHours, resolution });
}

// ---------------------------------------------------------------------------
// Chat (RAG)
// ---------------------------------------------------------------------------

/**
 * Ask a natural language question answered using live narrative context.
 *
 * @param {string} query
 * @param {number} [nContextNarratives=5]
 * @returns {Promise<{
 *   query: string,
 *   answer: string,
 *   context_narratives: object[]
 * }>}
 */
export async function chat(query, nContextNarratives = 5) {
  return _post("/api/chat", { query, n_context_narratives: nContextNarratives });
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

/**
 * Get automated ingestion pipeline status.
 *
 * @returns {Promise<{
 *   pipeline: {
 *     stories_ingested: number,
 *     narratives_created: number,
 *     narratives_updated: number,
 *     errors: number,
 *     started_at: number|null,
 *     last_ingested_at: number|null,
 *     queue_size: number
 *   },
 *   narratives: { total: number, active: number },
 *   events: { total_events_ingested: number },
 *   timestamp: number
 * }>}
 */
export async function getPipelineStats() {
  return _get("/api/pipeline/stats");
}

// ---------------------------------------------------------------------------
// Live Event Stream (SSE)
// ---------------------------------------------------------------------------

/**
 * Subscribe to the live ingest event stream.
 * Calls onEvent with each parsed event object as stories are processed.
 * Returns a cleanup function — call it to close the connection.
 *
 * @param {(event: {
 *   type: "connected"|"ingest",
 *   timestamp: number,
 *   result?: {
 *     action: "created"|"updated",
 *     narrative_id: string,
 *     narrative_name: string,
 *     model_risk: number,
 *     current_surprise: number,
 *     current_impact: number,
 *     narrative_event_count: number
 *   }
 * }) => void} onEvent
 *
 * @param {(error: Event) => void} [onError]
 * @returns {() => void}  call this to disconnect
 *
 * @example
 * const disconnect = streamEvents((e) => {
 *   if (e.type === "ingest") {
 *     console.log(e.result.narrative_name, "risk:", e.result.model_risk);
 *   }
 * });
 * // later:
 * disconnect();
 */
export function streamEvents(onEvent, onError) {
  const es = new EventSource(`${BASE_URL}/api/events/stream`);

  es.addEventListener("message", (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {
      // malformed event — ignore
    }
  });

  if (onError) {
    es.addEventListener("error", onError);
  }

  return () => es.close();
}

/**
 * The only file that knows how to talk to the backend.
 * Pages call these functions; if an endpoint changes, only this file changes.
 */

// Empty in development (Vite proxies /api to :8000). In production, the Render URL.
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

/** Error carrying the backend's {error: {code, message, details}} payload. */
export class ApiError extends Error {
  constructor(status, code, message, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request(path, { method = "GET", params, body, signal } = {}) {
  const url = new URL(API_BASE + path, window.location.origin);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });

  let response;
  try {
    response = await fetch(url, {
      method,
      signal,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(
      0,
      "network_error",
      "Can't reach the ParkWise API. Check that the backend is running on port 8000.",
    );
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error;
    throw new ApiError(
      response.status,
      error?.code || "http_error",
      error?.message || `The API answered with status ${response.status}.`,
      error?.details,
    );
  }
  return data;
}

export const api = {
  health: (opts) => request("/api/health", opts),
  listParks: (search, opts) => request("/api/parks", { ...opts, params: { search } }),
  getPark: (parkCode, opts) => request(`/api/parks/${encodeURIComponent(parkCode)}`, opts),
  history: (parkCode, { startDate, endDate } = {}, opts) =>
    request(`/api/weather/history/${encodeURIComponent(parkCode)}`, {
      ...opts,
      params: { start_date: startDate, end_date: endDate },
    }),
  seasonal: (parkCode, opts) =>
    request(`/api/weather/seasonal/${encodeURIComponent(parkCode)}`, opts),
  bestTime: (parkCode, opts) =>
    request(`/api/weather/best-time/${encodeURIComponent(parkCode)}`, opts),
  predict: ({ parkCode, date, activity }, opts) =>
    request("/api/weather/predict", {
      ...opts,
      params: { park_code: parkCode, date, activity },
    }),
  compare: ({ parkCodes, date, activity }, opts) =>
    request("/api/weather/compare", {
      ...opts,
      method: "POST",
      body: { park_codes: parkCodes, date, activity },
    }),
  modelPerformance: (opts) => request("/api/models/performance", opts),
};

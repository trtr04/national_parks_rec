import { api } from "../services/api.js";
import { useApi } from "../services/useApi.js";

/**
 * Live check that the frontend can reach FastAPI and FastAPI can reach the database.
 * This is the Phase 1 "is everything wired up?" indicator.
 */
export default function BackendStatus() {
  const { data, loading, error, reload } = useApi((signal) => api.health({ signal }), []);

  let tone = "bg-lichen";
  let text = "Checking the API…";
  if (error) {
    tone = "bg-alert";
    text = error.message;
  } else if (data) {
    const db = data.database;
    tone = db.connected ? "bg-spruce" : "bg-ochre";
    text = db.connected
      ? `API ${data.api_version} connected to ${db.dialect}. ${db.park_count} parks, ${db.weather_rows.toLocaleString()} weather days stored.`
      : "API is running but can't reach the database. Check DATABASE_URL.";
  }

  return (
    <div className="flex items-start gap-3 text-sm text-ink-muted" role="status" aria-live="polite">
      <span className={`mt-1.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full ${tone}`} aria-hidden="true" />
      <span>
        {text}{" "}
        {error && !loading && (
          <button type="button" onClick={reload} className="font-medium text-sky underline underline-offset-2">
            Try again
          </button>
        )}
      </span>
    </div>
  );
}

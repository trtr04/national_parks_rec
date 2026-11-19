import { activityLabel } from "./ActivityPicker.jsx";
import PredictionTypeTag from "./PredictionTypeTag.jsx";
import ScoreBadge from "./ScoreBadge.jsx";
import { formatDate } from "../services/dates.js";
import {
  formatOneIn,
  formatPercent,
  formatPrecipIn,
  formatTemp,
  formatTempRange,
  formatWind,
} from "../services/units.js";

const COMPONENT_LABELS = {
  temperature: "Temperature",
  precipitation: "Dry weather",
  wind: "Calm wind",
  snow: "No snow",
};

function Stat({ label, value, detail }) {
  return (
    <div className="rounded-xl border border-line bg-paper px-4 py-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="mt-1 font-display text-2xl font-bold leading-tight">{value}</dd>
      {detail && <dd className="mt-0.5 text-sm text-ink-muted">{detail}</dd>}
    </div>
  );
}

/** How the 0–100 score was built: one bar per component, with its weight. */
function ScoreBreakdown({ suitability }) {
  return (
    <ul className="space-y-2.5">
      {Object.entries(suitability.components).map(([key, value]) => (
        <li key={key}>
          <div className="flex justify-between text-sm">
            <span>
              {COMPONENT_LABELS[key] ?? key}{" "}
              <span className="text-ink-muted">· {Math.round(suitability.weights[key] * 100)}% of score</span>
            </span>
            <span className="tabular-nums font-medium">{Math.round(value)}</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-line" aria-hidden="true">
            <div className="h-full rounded-full bg-spruce" style={{ width: `${value}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function rainText(p) {
  const prob = p.precipitation.probability;
  if (p.prediction_type === "forecast") {
    return {
      value: formatPercent(prob),
      detail:
        p.precipitation.expected_mm > 0
          ? `chance of rain or snow · about ${formatPrecipIn(p.precipitation.expected_mm)} expected`
          : "chance of rain or snow",
    };
  }
  return { value: formatPercent(prob), detail: `of days are wet here then: ${formatOneIn(prob)}` };
}

/**
 * The full answer for one park on one date, from GET /api/weather/predict.
 * Everything the backend returns is shown, in U.S. units, with the kind of answer
 * (forecast or climate estimate) labelled at the top.
 */
export default function PredictionCard({ prediction: p }) {
  const rain = rainText(p);
  const t = p.temperature;
  const climate = p.prediction_type === "climate_estimate";

  return (
    <article className="space-y-6" aria-label={`Weather outlook for ${p.park.park_name}`}>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <PredictionTypeTag type={p.prediction_type} />
            <span className="text-sm text-ink-muted">
              {p.days_ahead === 0 ? "Today" : `${p.days_ahead} days away`}
            </span>
          </div>
          <h2 className="mt-2 text-2xl font-bold sm:text-3xl">{p.park.park_name}</h2>
          <p className="text-ink-muted">
            {formatDate(p.travel_date)} · {activityLabel(p.activity)}
          </p>
        </div>
        <div className="text-right">
          <ScoreBadge score={p.suitability.score} label={p.suitability.label} size="lg" />
          <p className="mt-1 text-sm text-ink-muted">for {activityLabel(p.activity).toLowerCase()}</p>
        </div>
      </header>

      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="High" value={formatTemp(t.max_c)} detail={`likely ${formatTempRange(t.max_range_c)}`} />
        <Stat label="Low" value={formatTemp(t.min_c)} detail={`likely ${formatTempRange(t.min_range_c)}`} />
        <Stat label={climate ? "Wet days" : "Precipitation"} value={rain.value} detail={rain.detail} />
        <Stat
          label="Wind"
          value={formatWind(p.wind.max_kmh)}
          detail={p.snow.probability >= 0.05 ? `snow ${formatPercent(p.snow.probability)} of days` : "strongest wind of the day"}
        />
      </dl>

      <div className="grid gap-6 md:grid-cols-2">
        <section>
          <h3 className="text-lg font-bold">Why this score</h3>
          <div className="mt-3">
            <ScoreBreakdown suitability={p.suitability} />
          </div>
        </section>
        <section className="space-y-3 text-[15px] leading-relaxed">
          <h3 className="text-lg font-bold">Keep in mind</h3>
          {p.notes.length > 0 && (
            <ul className="space-y-1.5">
              {p.notes.map((note) => (
                <li key={note} className="flex gap-2">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-ochre" aria-hidden="true" />
                  {note}
                </li>
              ))}
            </ul>
          )}
          <p className="text-ink-muted">{p.uncertainty}</p>
          <p className="text-sm text-ink-muted">
            Temperature ranges: {t.range_note}
          </p>
        </section>
      </div>

      <footer className="border-t border-line pt-3 text-xs text-ink-muted">
        Source: {p.source}. {p.park.weather_location_note}
      </footer>
    </article>
  );
}

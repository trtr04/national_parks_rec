import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import ActivityPicker, { activityLabel } from "../components/ActivityPicker.jsx";
import PageHeader from "../components/PageHeader.jsx";
import ParkPicker from "../components/ParkPicker.jsx";
import PredictionTypeTag from "../components/PredictionTypeTag.jsx";
import ScoreBadge, { LABEL_STYLES } from "../components/ScoreBadge.jsx";
import { EmptyState, ErrorMessage, Loading } from "../components/StateMessage.jsx";
import { api } from "../services/api.js";
import { formatDate, isoDate } from "../services/dates.js";
import { useApi } from "../services/useApi.js";
import { MONTH_NAMES, cToF, formatOneIn, formatPercent, formatTemp, formatTempRange, formatWind } from "../services/units.js";

const MIN_PARKS = 2;
const MAX_PARKS = 5;
const SERIES_COLORS = ["var(--color-spruce)", "var(--color-sky)", "var(--color-ochre)", "var(--color-alert)", "var(--color-ink-muted)"];

function SelectedParks({ codes, parks, onRemove }) {
  if (codes.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Parks to compare">
      {codes.map((code) => {
        const park = parks.find((p) => p.park_code === code);
        return (
          <li key={code} className="flex items-center gap-1 rounded-full border border-line bg-paper-raised py-1 pl-3 pr-1 text-sm">
            {park?.park_name ?? code}
            <button
              type="button"
              onClick={() => onRemove(code)}
              aria-label={`Remove ${park?.park_name ?? code}`}
              className="rounded-full px-2 text-ink-muted hover:bg-line hover:text-ink"
            >
              ×
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function CompareForm({ parks, parksLoading, onSubmit, submitting }) {
  const today = isoDate(new Date());
  const [codes, setCodes] = useState([]);
  const [date, setDate] = useState("");
  const [activity, setActivity] = useState("hiking");
  const [touched, setTouched] = useState(false);

  const problems = [];
  if (codes.length < MIN_PARKS) problems.push(`Choose at least ${MIN_PARKS} parks.`);
  if (!date) problems.push("Choose a travel date.");
  if (date && date < today) problems.push("Travel date can't be in the past.");

  function handleSubmit(event) {
    event.preventDefault();
    setTouched(true);
    if (problems.length === 0) onSubmit({ parkCodes: codes, date, activity });
  }

  const available = parks.filter((p) => !codes.includes(p.park_code));

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5 rounded-3xl border border-line bg-paper-raised p-5 sm:p-7">
      <div className="space-y-3">
        <ParkPicker
          parks={available}
          value=""
          onChange={(code) => setCodes((c) => [...c, code])}
          label={`Parks (${codes.length} of ${MAX_PARKS})`}
          disabled={parksLoading || codes.length >= MAX_PARKS}
        />
        <SelectedParks codes={codes} parks={parks} onRemove={(code) => setCodes((c) => c.filter((x) => x !== code))} />
      </div>

      <div className="max-w-xs">
        <label htmlFor="compare-date" className="mb-1.5 block text-sm font-medium text-ink">
          Travel date
        </label>
        <input
          id="compare-date"
          type="date"
          min={today}
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="w-full rounded-xl border border-line bg-paper px-4 py-3 text-[15px]"
        />
      </div>

      <ActivityPicker value={activity} onChange={setActivity} name="compare-activity" />

      {touched && problems.length > 0 && (
        <ul className="space-y-1 text-sm text-alert" role="alert">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-xl bg-spruce px-5 py-3.5 font-display text-lg font-bold text-paper transition-colors hover:bg-spruce-deep disabled:opacity-60 sm:w-auto"
      >
        {submitting ? "Comparing…" : "Compare parks"}
      </button>
    </form>
  );
}

function RankedResults({ data }) {
  const best = data.results[0];
  return (
    <section>
      <h2 className="text-2xl font-bold">
        Best for {activityLabel(data.activity).toLowerCase()} on {formatDate(data.travel_date)}:{" "}
        <span className="text-spruce">{best.park.park_name}</span>
      </h2>
      <ol className="mt-5 space-y-3">
        {data.results.map((r) => {
          const climate = r.prediction_type === "climate_estimate";
          return (
            <li key={r.park.park_code} className="rounded-2xl border border-line bg-paper-raised p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-4">
                  <span className="font-display text-3xl font-bold leading-none text-ink-muted">{r.rank}</span>
                  <div>
                    <h3 className="text-xl font-bold">{r.park.park_name}</h3>
                    <p className="text-sm text-ink-muted">{r.park.state}</p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <ScoreBadge score={r.suitability.score} label={r.suitability.label} />
                  <PredictionTypeTag type={r.prediction_type} />
                </div>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-line" aria-hidden="true">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${r.suitability.score}%`, background: LABEL_STYLES[r.suitability.label]?.bar }}
                />
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-[15px] sm:grid-cols-4">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-ink-muted">High</dt>
                  <dd className="font-medium">
                    {formatTemp(r.temperature.max_c)}{" "}
                    <span className="text-sm font-normal text-ink-muted">({formatTempRange(r.temperature.max_range_c)})</span>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-ink-muted">Low</dt>
                  <dd className="font-medium">
                    {formatTemp(r.temperature.min_c)}{" "}
                    <span className="text-sm font-normal text-ink-muted">({formatTempRange(r.temperature.min_range_c)})</span>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-ink-muted">{climate ? "Wet days" : "Precipitation"}</dt>
                  <dd className="font-medium">
                    {formatPercent(r.precipitation.probability)}{" "}
                    {climate && <span className="text-sm font-normal text-ink-muted">({formatOneIn(r.precipitation.probability)})</span>}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-ink-muted">Wind</dt>
                  <dd className="font-medium">{formatWind(r.wind.max_kmh)}</dd>
                </div>
              </dl>
              {r.notes.length > 0 && <p className="mt-3 text-sm text-ink-muted">{r.notes.join(" ")}</p>}
            </li>
          );
        })}
      </ol>
      <p className="mt-4 text-sm text-ink-muted">{best.uncertainty}</p>
    </section>
  );
}

/** Each park's year, month by month, from the stored history. */
function SeasonChart({ parkCodes, parks }) {
  const [measure, setMeasure] = useState("high");
  const seasonal = useApi(
    (signal) => Promise.all(parkCodes.map((code) => api.seasonal(code, { signal }))),
    [parkCodes.join(",")],
  );
  if (seasonal.loading) return <Loading label="Loading each park's seasons…" />;
  if (seasonal.error) return <ErrorMessage error={seasonal.error} onRetry={seasonal.reload} />;
  if (!seasonal.data) return null;

  const name = (code) => parks.find((p) => p.park_code === code)?.park_name ?? code;
  const rows = MONTH_NAMES.map((month, i) => {
    const row = { month };
    seasonal.data.forEach((s) => {
      const m = s.months.find((x) => x.month === i + 1);
      if (!m) return;
      row[s.park_code] =
        measure === "high"
          ? m.avg_temp_max === null ? null : Math.round(cToF(m.avg_temp_max))
          : m.wet_day_frequency === null ? null : Math.round(m.wet_day_frequency * 100);
    });
    return row;
  });

  return (
    <section className="rounded-2xl border border-line bg-paper-raised p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold">How each park's season differs</h2>
        <div className="flex rounded-lg border border-line p-0.5 text-sm" role="group" aria-label="Measure">
          {[
            ["high", "Average high"],
            ["wet", "Wet days"],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={measure === value}
              onClick={() => setMeasure(value)}
              className={`rounded-md px-3 py-1 ${measure === value ? "bg-spruce text-paper" : "text-ink-muted hover:text-ink"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-4 h-80">
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 5, right: 10, bottom: 5, left: -10 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis unit={measure === "high" ? "°F" : "%"} tick={{ fontSize: 12 }} domain={measure === "wet" ? [0, 100] : ["auto", "auto"]} />
            <Tooltip />
            <Legend />
            {parkCodes.map((code, i) => (
              <Line
                key={code}
                type="monotone"
                dataKey={code}
                name={name(code)}
                stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-sm text-ink-muted">
        {measure === "high"
          ? "Average daily high for each month across the stored years."
          : "Share of days with at least 1 mm of rain or melted snow."}
      </p>
    </section>
  );
}

export default function ComparePage() {
  const parks = useApi((signal) => api.listParks(null, { signal }), []);
  const [result, setResult] = useState({ status: "idle" });
  const parkList = parks.data?.parks ?? [];

  async function runCompare(request) {
    setResult({ status: "loading", request });
    try {
      setResult({ status: "done", request, data: await api.compare(request) });
    } catch (error) {
      setResult({ status: "done", request, error });
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <PageHeader title="Compare parks">
        Pick two to five parks and one travel date, and see which is likely to have the better weather for
        what you want to do.
      </PageHeader>

      <div className="mt-8 max-w-3xl">
        {parks.error ? (
          <ErrorMessage error={parks.error} onRetry={parks.reload} />
        ) : (
          <CompareForm
            parks={parkList}
            parksLoading={parks.loading}
            onSubmit={runCompare}
            submitting={result.status === "loading"}
          />
        )}
      </div>

      <div className="mt-10 space-y-8">
        {result.status === "idle" && (
          <EmptyState title="Your comparison will appear here">
            Parks are ranked by the weather suitability score for your activity, with highs, lows, rain and
            wind side by side.
          </EmptyState>
        )}
        {result.status === "loading" && <Loading label="Checking each park…" />}
        {result.error && <ErrorMessage error={result.error} onRetry={() => runCompare(result.request)} />}
        {result.data && (
          <>
            <RankedResults data={result.data} />
            <SeasonChart parkCodes={result.request.parkCodes} parks={parkList} />
          </>
        )}
      </div>
    </div>
  );
}

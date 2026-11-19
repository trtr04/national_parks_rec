import { useState } from "react";
import { Link } from "react-router-dom";
import ActivityPicker from "../components/ActivityPicker.jsx";
import HeroLandscape from "../components/HeroLandscape.jsx";
import ParkPicker from "../components/ParkPicker.jsx";
import PredictionCard from "../components/PredictionCard.jsx";
import ScoreBadge from "../components/ScoreBadge.jsx";
import { EmptyState, ErrorMessage, Loading } from "../components/StateMessage.jsx";
import { api } from "../services/api.js";
import { addDays, daysFromToday, formatDate, isoDate } from "../services/dates.js";
import { useApi } from "../services/useApi.js";
import { formatPercent, formatTemp } from "../services/units.js";

// Must match FORECAST_HORIZON_DAYS in backend/app/services/weather_service.py
const FORECAST_HORIZON_DAYS = 16;
// Longest trip shown day by day (one prediction per day).
const MAX_TRIP_DAYS = 14;

function ModeHint({ startDate }) {
  if (!startDate) return null;
  const days = daysFromToday(startDate);
  if (days < 0) return null;
  // Day 0 (today) to day 15: Open-Meteo's 16 forecast days.
  const forecast = days < FORECAST_HORIZON_DAYS;
  return (
    <p className="text-sm text-ink-muted">
      {forecast
        ? `${days === 0 ? "Today" : `${days} days out`}: within the forecast window, so you'll get a real weather forecast.`
        : `${days} days out: beyond the ${FORECAST_HORIZON_DAYS}-day forecast window, so you'll get a climate estimate from 2015–2025 history.`}
    </p>
  );
}

function SearchForm({ parks, parksLoading, onSubmit, submitting }) {
  const today = isoDate(new Date());
  const [parkCode, setParkCode] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [activity, setActivity] = useState("hiking");
  const [touched, setTouched] = useState(false);

  const problems = [];
  if (!parkCode) problems.push("Choose a park.");
  if (!startDate) problems.push("Choose a travel date.");
  if (startDate && startDate < today) problems.push("Travel date can't be in the past.");
  if (endDate && startDate && endDate < startDate) problems.push("End date must be after the start date.");
  if (endDate && startDate && daysFromToday(endDate) - daysFromToday(startDate) >= MAX_TRIP_DAYS) {
    problems.push(`Trips can be up to ${MAX_TRIP_DAYS} days long.`);
  }

  function handleSubmit(event) {
    event.preventDefault();
    setTouched(true);
    if (problems.length === 0) onSubmit({ parkCode, startDate, endDate, activity });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      <ParkPicker parks={parks} value={parkCode} onChange={setParkCode} disabled={parksLoading} />

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="start-date" className="mb-1.5 block text-sm font-medium text-ink">
            Arriving
          </label>
          <input
            id="start-date"
            type="date"
            min={today}
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full rounded-xl border border-line bg-paper-raised px-4 py-3 text-[15px]"
          />
        </div>
        <div>
          <label htmlFor="end-date" className="mb-1.5 block text-sm font-medium text-ink">
            Leaving <span className="font-normal text-ink-muted">(optional)</span>
          </label>
          <input
            id="end-date"
            type="date"
            min={startDate || today}
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full rounded-xl border border-line bg-paper-raised px-4 py-3 text-[15px]"
          />
        </div>
      </div>

      <ActivityPicker value={activity} onChange={setActivity} />
      <ModeHint startDate={startDate} />

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
        {submitting ? "Checking the weather…" : "Check the weather"}
      </button>
    </form>
  );
}

/** One column per trip day; choosing one shows its full card below. */
function TripStrip({ days, selected, onSelect }) {
  return (
    <div>
      <h2 className="text-lg font-bold">Your trip, day by day</h2>
      <div className="mt-3 flex gap-2 overflow-x-auto pb-2" role="tablist" aria-label="Trip days">
        {days.map((p, i) => (
          <button
            key={p.travel_date}
            type="button"
            role="tab"
            aria-selected={i === selected}
            onClick={() => onSelect(i)}
            className={`min-w-[6.5rem] shrink-0 rounded-xl border px-3 py-2.5 text-left transition-colors ${
              i === selected ? "border-spruce bg-paper-raised ring-2 ring-spruce" : "border-line bg-paper hover:border-lichen"
            }`}
          >
            <span className="block text-sm font-medium">{formatDate(p.travel_date, "compact")}</span>
            <span className="mt-1 block font-display text-lg font-bold leading-tight">
              {formatTemp(p.temperature.max_c)}
              <span className="text-sm font-normal text-ink-muted"> / {formatTemp(p.temperature.min_c)}</span>
            </span>
            <span className="block text-xs text-ink-muted">
              {formatPercent(p.precipitation.probability)} wet
              {p.prediction_type === "forecast" ? " · forecast" : " · typical"}
            </span>
            <span className="mt-1.5 block">
              <ScoreBadge score={p.suitability.score} label={p.suitability.label} size="sm" />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function Result({ state, onRetry }) {
  const [selected, setSelected] = useState(0);
  if (state.status === "idle") return null;
  if (state.status === "loading") return <Loading label="Asking the weather service…" />;
  if (state.error) return <ErrorMessage error={state.error} onRetry={onRetry} />;

  const days = state.data;
  const index = Math.min(selected, days.length - 1);
  return (
    <div className="space-y-6 border-t border-line pt-6">
      {days.length > 1 && <TripStrip days={days} selected={index} onSelect={setSelected} />}
      <PredictionCard prediction={days[index]} />
    </div>
  );
}

export default function WeatherExplorer() {
  const parks = useApi((signal) => api.listParks(null, { signal }), []);
  const [result, setResult] = useState({ status: "idle" });

  async function runPrediction(request) {
    setResult({ status: "loading", request });
    const length = request.endDate ? daysFromToday(request.endDate) - daysFromToday(request.startDate) + 1 : 1;
    const dates = Array.from({ length }, (_, i) => addDays(request.startDate, i));
    try {
      const data = await Promise.all(
        dates.map((date) => api.predict({ parkCode: request.parkCode, date, activity: request.activity })),
      );
      setResult({ status: "done", request, data });
    } catch (error) {
      setResult({ status: "done", request, error });
    }
  }

  const parkList = parks.data?.parks ?? [];

  return (
    <>
      <section className="relative isolate overflow-hidden">
        <HeroLandscape />
        <div className="relative mx-auto max-w-6xl px-4 pb-16 pt-14 sm:px-6 sm:pt-20 lg:pb-24">
          <h1 className="max-w-3xl text-5xl font-bold leading-[1.05] text-paper drop-shadow-sm sm:text-6xl lg:text-7xl">
            Know the weather before you pick the trail.
          </h1>
          <p className="mt-5 max-w-xl text-lg leading-relaxed text-paper/90">
            A forecast for trips in the next two weeks. A climate estimate, with honest ranges, for
            anything further out.
          </p>

          <div className="mt-10 max-w-3xl rounded-3xl border border-white/40 bg-paper/95 p-5 shadow-2xl shadow-spruce-deep/30 backdrop-blur sm:p-7">
            {parks.error ? (
              <ErrorMessage error={parks.error} onRetry={parks.reload} />
            ) : !parks.loading && parkList.length === 0 ? (
              <EmptyState title="No parks in the database yet">
                Load the National Parks with{" "}
                <code className="rounded bg-line/60 px-1.5 py-0.5 text-sm">python -m scripts.load_parks</code>{" "}
                from the backend folder, then refresh.
              </EmptyState>
            ) : (
              <SearchForm
                parks={parkList}
                parksLoading={parks.loading}
                onSubmit={runPrediction}
                submitting={result.status === "loading"}
              />
            )}
            <div className="mt-5 empty:hidden">
              <Result key={result.status} state={result} onRetry={() => runPrediction(result.request)} />
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-8 px-4 py-16 sm:px-6 md:grid-cols-2">
        <div>
          <h2 className="text-3xl font-bold">Two kinds of answer, clearly labelled</h2>
          <p className="mt-3 text-[17px] leading-relaxed text-ink-muted">
            Nobody can forecast a specific day months ahead. ParkWise says which answer you're getting,
            so a plan for next weekend and a plan for next summer are read differently.
          </p>
        </div>
        <dl className="space-y-5">
          <div className="border-l-4 border-sky pl-4">
            <dt className="font-display text-lg font-bold">Forecast</dt>
            <dd className="mt-1 text-[15px] leading-relaxed text-ink-muted">
              For the next {FORECAST_HORIZON_DAYS} days. Pulled live from the Open-Meteo forecast for the
              park's visitor area: highs, lows, chance of precipitation and wind.
            </dd>
          </div>
          <div className="border-l-4 border-ochre pl-4">
            <dt className="font-display text-lg font-bold">Climate estimate</dt>
            <dd className="mt-1 text-[15px] leading-relaxed text-ink-muted">
              For later dates. What that time of year has typically been like across 2015–2025, with the
              range you should be ready for. <Link to="/model-insights" className="font-medium text-sky underline underline-offset-2">How the estimates are made</Link>
            </dd>
          </div>
        </dl>
      </section>
    </>
  );
}

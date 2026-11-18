import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ActivityPicker, { COMFORT_BAND_C, activityLabel } from "../components/ActivityPicker.jsx";
import PageHeader from "../components/PageHeader.jsx";
import ParkPicker from "../components/ParkPicker.jsx";
import ScoreBadge, { LABEL_STYLES } from "../components/ScoreBadge.jsx";
import { EmptyState, ErrorMessage, Loading } from "../components/StateMessage.jsx";
import { api } from "../services/api.js";
import { useApi } from "../services/useApi.js";
import {
  MONTH_LONG,
  MONTH_NAMES,
  cToF,
  formatOneIn,
  formatPercent,
  formatTemp,
  formatTempRange,
  formatWind,
} from "../services/units.js";

/** Plain-words description of a month for one activity, e.g. "Hot but mostly dry". */
export function describeMonth(month, activity) {
  const [low, high] = COMFORT_BAND_C[activity];
  const temp =
    month.temp_max_c > high + 8 ? "Hot" :
    month.temp_max_c > high ? "Warm" :
    month.temp_max_c < low - 8 ? "Cold" :
    month.temp_max_c < low ? "Cool" : "Comfortable";
  const good = temp === "Comfortable";
  const extras = [];
  if (month.wet_probability >= 0.35) extras.push({ text: "often wet", bad: true });
  else if (month.wet_probability <= 0.12) extras.push({ text: "mostly dry", bad: false });
  if (month.snow_probability >= 0.25) extras.push({ text: "snowy", bad: true });
  if (month.wind_max_kmh >= 35) extras.push({ text: "windy", bad: true });
  if (extras.length === 0) return temp;
  // "but" when the extras pull the other way from the temperature.
  const joiner = extras.some((e) => e.bad === good) ? " but " : " and ";
  return temp + joiner + extras.map((e) => e.text).join(", ");
}

function ScoreChart({ months, activity }) {
  const data = months.map((m) => ({
    month: MONTH_NAMES[m.month - 1],
    score: m.scores[activity],
    label: m.labels[activity],
  }));
  return (
    <section className="rounded-2xl border border-line bg-paper-raised p-5">
      <h2 className="text-xl font-bold">Suitability for {activityLabel(activity).toLowerCase()}, month by month</h2>
      <div className="mt-4 h-72">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(value, _name, item) => [`${Math.round(value)} (${item.payload.label})`, "Score"]} />
            <Bar dataKey="score" radius={[4, 4, 0, 0]}>
              {data.map((d) => (
                <Cell key={d.month} fill={LABEL_STYLES[d.label]?.bar} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-muted">
        {Object.entries(LABEL_STYLES).map(([label, style]) => (
          <span key={label} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: style.bar }} aria-hidden="true" />
            {label}
          </span>
        ))}
      </p>
    </section>
  );
}

function MonthTable({ months, activity }) {
  return (
    <section className="overflow-x-auto rounded-2xl border border-line bg-paper-raised">
      <table className="w-full min-w-[52rem] text-left text-[15px]">
        <caption className="px-5 pt-5 text-left">
          <span className="font-display text-xl font-bold">Each month in detail</span>
          <span className="mt-1 block text-sm font-normal text-ink-muted">
            “Year to year” is the coolest and warmest year's average high, and the driest and wettest year's share of wet days.
          </span>
        </caption>
        <thead className="border-b border-line text-xs uppercase tracking-wide text-ink-muted">
          <tr>
            <th scope="col" className="px-5 py-3 font-medium">Month</th>
            <th scope="col" className="px-3 py-3 font-medium">Score</th>
            <th scope="col" className="px-3 py-3 font-medium">High / low</th>
            <th scope="col" className="px-3 py-3 font-medium">Wet days</th>
            <th scope="col" className="px-3 py-3 font-medium">Wind</th>
            <th scope="col" className="px-3 py-3 font-medium">In short</th>
            <th scope="col" className="px-5 py-3 font-medium">Year to year</th>
          </tr>
        </thead>
        <tbody>
          {months.map((m) => (
            <tr key={m.month} className="border-b border-line last:border-0">
              <th scope="row" className="px-5 py-3 font-medium">{MONTH_LONG[m.month - 1]}</th>
              <td className="px-3 py-3"><ScoreBadge score={m.scores[activity]} label={m.labels[activity]} /></td>
              <td className="whitespace-nowrap px-3 py-3 tabular-nums">{formatTemp(m.temp_max_c)} / {formatTemp(m.temp_min_c)}</td>
              <td className="px-3 py-3">
                {formatPercent(m.wet_probability)}
                {m.snow_probability >= 0.05 && (
                  <span className="block text-xs text-ink-muted">snow {formatPercent(m.snow_probability)}</span>
                )}
              </td>
              <td className="whitespace-nowrap px-3 py-3">{formatWind(m.wind_max_kmh)}</td>
              <td className="px-3 py-3">{describeMonth(m, activity)}</td>
              <td className="whitespace-nowrap px-5 py-3 text-sm text-ink-muted">
                Highs {formatTempRange(m.year_to_year.avg_high_c)}
                <span className="block">
                  Wet {formatPercent(m.year_to_year.wet_share[0])}–{formatPercent(m.year_to_year.wet_share[1])}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function BestMonths({ data, activity }) {
  const best = data.best_months[activity].map((n) => data.months[n - 1]);
  const top = best[0];
  return (
    <section className="rounded-2xl bg-spruce-deep p-6 text-paper">
      <p className="text-sm font-medium uppercase tracking-wide text-lichen">Best months for {activityLabel(activity).toLowerCase()}</p>
      <p className="mt-2 font-display text-3xl font-bold sm:text-4xl">
        {best.map((m) => MONTH_LONG[m.month - 1]).join(", ")}
      </p>
      <p className="mt-3 max-w-2xl leading-relaxed text-paper/85">
        In {MONTH_LONG[top.month - 1]}, highs are typically around {Math.round(cToF(top.temp_max_c))}°F and lows{" "}
        {Math.round(cToF(top.temp_min_c))}°F, with rain or snow on {formatOneIn(top.wet_probability)}. These are
        typical conditions, not a forecast for any one day.
      </p>
    </section>
  );
}

export default function BestTimePage() {
  const parks = useApi((signal) => api.listParks(null, { signal }), []);
  const [parkCode, setParkCode] = useState("");
  const [activity, setActivity] = useState("hiking");
  const result = useApi((signal) => api.bestTime(parkCode, { signal }), [parkCode], Boolean(parkCode));

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <PageHeader title="Best time to visit">
        Twelve months side by side for one park, scored for hiking, camping, sightseeing or wildlife watching.
      </PageHeader>

      <div className="mt-8 grid max-w-3xl gap-5">
        {parks.error ? (
          <ErrorMessage error={parks.error} onRetry={parks.reload} />
        ) : (
          <div className="max-w-md">
            <ParkPicker parks={parks.data?.parks ?? []} value={parkCode} onChange={setParkCode} disabled={parks.loading} />
          </div>
        )}
        <ActivityPicker value={activity} onChange={setActivity} name="best-time-activity" />
      </div>

      <div className="mt-10 space-y-6">
        {!parkCode ? (
          <EmptyState title="Choose a park to see its year">
            Each month gets a suitability score from the climate model, plus how much it has varied between years.
          </EmptyState>
        ) : result.loading ? (
          <Loading label="Scoring every month…" />
        ) : result.error ? (
          <ErrorMessage error={result.error} onRetry={result.reload} />
        ) : (
          result.data && (
            <>
              <BestMonths data={result.data} activity={activity} />
              <ScoreChart months={result.data.months} activity={activity} />
              <MonthTable months={result.data.months} activity={activity} />
              <p className="text-xs text-ink-muted">Source: {result.data.source}.</p>
            </>
          )
        )}
      </div>
    </div>
  );
}

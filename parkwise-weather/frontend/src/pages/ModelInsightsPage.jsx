import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import PageHeader from "../components/PageHeader.jsx";
import { ErrorMessage, Loading, Panel } from "../components/StateMessage.jsx";
import { api } from "../services/api.js";
import { useApi } from "../services/useApi.js";
import { MONTH_NAMES, cToF, formatTempDelta } from "../services/units.js";

const MODEL_COLORS = {
  seasonal_average: "var(--color-ink-muted)",
  seasonal_regression: "var(--color-spruce)",
  random_forest: "var(--color-sky)",
};

const MODEL_EXPLAINERS = {
  seasonal_average:
    "For each park and day of the year, the average of the training years within a week either side. The baseline every other model must beat.",
  seasonal_regression:
    "A smooth seasonal curve fitted to each park, plus one warming trend shared by all parks. Logistic regression for the chance of a wet day.",
  random_forest:
    "One model across all parks, using location, season, the park's typical weather for that date and the year.",
};

const LIMITATIONS = [
  "A climate estimate describes what a time of year is usually like. It can't say whether one particular day will be unusually hot, cold or stormy.",
  "Even a perfect seasonal model would miss a single day's high by about 3 °C (6 °F) on average, because day-to-day weather is that variable.",
  "Weather comes from one point per park, usually the main visitor center. High trails, canyons and coasts can be much colder, hotter or windier.",
  "The history is ERA5 reanalysis, a model-based reconstruction of past weather, not measurements from a station in the park.",
  "Eleven years is short. Rare events like record heat waves or very wet winters may not be represented.",
  "The suitability score is a judgement call. Its comfort bands and weights are documented in the backend and can be tuned.",
];

const fmtC = (c) => `${c.toFixed(2)} °C (${formatTempDelta(c)})`;
const span = ([a, b]) => (a === b ? `${a}` : `${a}–${b}`);

function ChartCard({ title, children, note, height = "h-72" }) {
  return (
    <section className="rounded-2xl border border-line bg-paper-raised p-5">
      <h3 className="text-lg font-bold">{title}</h3>
      <div className={`mt-4 ${height}`}>{children}</div>
      {note && <p className="mt-2 text-sm text-ink-muted">{note}</p>}
    </section>
  );
}

function Splits({ split, rows }) {
  const items = [
    { years: span(split.train), role: "Training", note: "Models learn seasonal patterns", n: rows.train },
    { years: span(split.validation), role: "Validation", note: "Choose between models", n: rows.validation },
    { years: span(split.test), role: "Test", note: "One final, untouched score", n: rows.test },
  ];
  return (
    <section className="mt-10">
      <h2 className="text-2xl font-bold">Data is split by time, never shuffled</h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-muted">
        Models only learn from earlier years and are scored on later ones, the same position they're in when
        predicting a real future trip.
      </p>
      <ol className="mt-6 grid gap-3 sm:grid-cols-3">
        {items.map((s) => (
          <li key={s.role} className="rounded-2xl border border-line bg-paper-raised p-5">
            <p className="font-display text-2xl font-bold text-spruce">{s.years}</p>
            <p className="mt-1 font-medium">{s.role}</p>
            <p className="text-sm text-ink-muted">
              {s.note} · {s.n.toLocaleString()} park-days
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Headline({ metrics }) {
  const sel = metrics.models[metrics.selected_model];
  const cov = metrics.interval.test_coverage;
  const hist = metrics.selected_model_test_error_histogram;
  const stats = [
    { label: "Typical miss on the daily high", value: formatTempDelta(sel.test.temp_max_mae), detail: `${sel.test.temp_max_mae.toFixed(2)} °C mean absolute error` },
    { label: "Typical miss on the daily low", value: formatTempDelta(sel.test.temp_min_mae), detail: `${sel.test.temp_min_mae.toFixed(2)} °C mean absolute error` },
    hist && { label: "Highs within 3 °C (5 °F)", value: `${Math.round(hist.within_3c * 100)}%`, detail: "of test days" },
    {
      label: "80% ranges that held",
      value: `${Math.round(((cov.temp_max + cov.temp_min) / 2) * 100)}%`,
      detail: "of test days fell inside the stated range",
    },
  ].filter(Boolean);
  return (
    <section className="mt-12">
      <h2 className="text-2xl font-bold">
        In use: <span className="text-spruce">{sel.label}</span>
      </h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-muted">
        Scored on {span(metrics.split.test)}, years no model saw while it was being built or chosen. {metrics.parks} parks.
      </p>
      <dl className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-2xl border border-line bg-paper-raised p-5">
            <dt className="text-sm text-ink-muted">{s.label}</dt>
            <dd className="mt-1 font-display text-3xl font-bold">{s.value}</dd>
            <dd className="text-xs text-ink-muted">{s.detail}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function ModelTable({ metrics }) {
  return (
    <section className="mt-12">
      <h2 className="text-2xl font-bold">Three models, one baseline to beat</h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-muted">{metrics.selection_rule}</p>
      <div className="mt-6 overflow-x-auto rounded-2xl border border-line bg-paper-raised">
        <table className="w-full min-w-[44rem] text-left text-[15px]">
          <thead className="border-b border-line text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th scope="col" className="px-5 py-3 font-medium">Model</th>
              <th scope="col" className="px-3 py-3 font-medium">Validation score</th>
              <th scope="col" className="px-3 py-3 font-medium">Test: high MAE</th>
              <th scope="col" className="px-3 py-3 font-medium">Test: low MAE</th>
              <th scope="col" className="px-3 py-3 font-medium">Test: high RMSE</th>
              <th scope="col" className="px-5 py-3 font-medium">Test: wet-day Brier</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(metrics.models).map(([name, m]) => {
              const selected = name === metrics.selected_model;
              return (
                <tr key={name} className={`border-b border-line last:border-0 ${selected ? "bg-sky-soft/60" : ""}`}>
                  <th scope="row" className="px-5 py-3 align-top font-medium">
                    <span className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: MODEL_COLORS[name] }} aria-hidden="true" />
                      {m.label}
                      {selected && <span className="rounded-full bg-spruce px-2 py-0.5 text-xs text-paper">In use</span>}
                    </span>
                    <span className="mt-1 block max-w-xs text-sm font-normal text-ink-muted">{MODEL_EXPLAINERS[name]}</span>
                  </th>
                  <td className="px-3 py-3 align-top tabular-nums">{m.validation_score.toFixed(3)}</td>
                  <td className="px-3 py-3 align-top tabular-nums">{fmtC(m.test.temp_max_mae)}</td>
                  <td className="px-3 py-3 align-top tabular-nums">{fmtC(m.test.temp_min_mae)}</td>
                  <td className="px-3 py-3 align-top tabular-nums">{m.test.temp_max_rmse.toFixed(2)} °C</td>
                  <td className="px-5 py-3 align-top tabular-nums">{m.test.wet_brier.toFixed(4)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-sm text-ink-muted">
        MAE: average size of the miss. RMSE: like MAE, but big misses count extra. Brier: how good the chance of a
        wet day is, from 0 (perfect) to 1. Lower is better for all of them.
      </p>
    </section>
  );
}

function Charts({ metrics }) {
  const byMonth = metrics.test_temp_max_mae_by_month;
  const monthRows = byMonth
    ? MONTH_NAMES.map((month, i) => {
        const row = { month };
        Object.entries(byMonth).forEach(([name, values]) => {
          if (values[i] !== undefined) row[name] = Math.round(((values[i] * 9) / 5) * 100) / 100;
        });
        return row;
      })
    : null;

  const hist = metrics.selected_model_test_error_histogram;
  const histRows = hist?.bin_start_c.map((start, i) => ({
    bin: start + 0.5,
    label: `${start} to ${start + 1} °C`,
    count: hist.count[i],
  }));

  const sample = metrics.selected_model_test_sample?.map((s) => ({
    actual: Math.round(cToF(s.actual)),
    predicted: Math.round(cToF(s.predicted)),
    park: s.park_code,
    date: s.date,
  }));
  // Axis limits rounded out to the nearest 10 °F so the ticks read cleanly.
  const lo = sample ? Math.floor(Math.min(...sample.flatMap((s) => [s.actual, s.predicted])) / 10) * 10 : 0;
  const hi = sample ? Math.ceil(Math.max(...sample.flatMap((s) => [s.actual, s.predicted])) / 10) * 10 : 100;

  const parks = [...metrics.selected_model_test_by_park].sort((a, b) => a.temp_max_mae - b.temp_max_mae);

  if (!monthRows || !hist || !sample) {
    return (
      <div className="mt-12">
        <Panel tone="notice" title="Charts need a retrain">
          These metrics were saved by an older training run. Run <code>python -m scripts.train_models</code> from the
          backend folder to add the error charts.
        </Panel>
      </div>
    );
  }

  return (
    <section className="mt-12 space-y-6">
      <h2 className="text-2xl font-bold">Where the errors come from</h2>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Predicted vs. actual daily high"
          note={`500 random test days. Points on the diagonal are perfect; the spread around it is day-to-day weather no climate estimate can know.`}
        >
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 5, right: 10, bottom: 15, left: -5 }}>
              <CartesianGrid stroke="var(--color-line)" />
              <XAxis type="number" dataKey="predicted" name="Predicted" unit="°F" domain={[lo, hi]} tick={{ fontSize: 12 }}
                label={{ value: "Predicted", position: "insideBottom", offset: -8, fontSize: 12 }} />
              <YAxis type="number" dataKey="actual" name="Actual" unit="°F" domain={[lo, hi]} tick={{ fontSize: 12 }} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} />
              <ReferenceLine segment={[{ x: lo, y: lo }, { x: hi, y: hi }]} stroke="var(--color-ochre)" strokeDasharray="4 4" />
              <Scatter data={sample} fill="var(--color-spruce)" fillOpacity={0.45} />
            </ScatterChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Size of the miss on the daily high"
          note={`Predicted minus actual, in 1 °C steps. ${Math.round(hist.within_3c * 100)}% of test days were within 3 °C (5 °F).`}
        >
          <ResponsiveContainer>
            <BarChart data={histRows} margin={{ top: 5, right: 10, bottom: 15, left: -5 }}>
              <CartesianGrid stroke="var(--color-line)" vertical={false} />
              <XAxis dataKey="bin" type="number" domain={[-15, 15]} ticks={[-15, -10, -5, 0, 5, 10, 15]} unit="°C" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip labelFormatter={(_, p) => p?.[0]?.payload.label} formatter={(v) => [v.toLocaleString(), "Days"]} />
              <ReferenceLine x={0} stroke="var(--color-ochre)" />
              <Bar dataKey="count" fill="var(--color-sky)" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard
        title="Typical miss on the daily high, by month"
        note="Winter is hardest: cold snaps and warm spells swing temperatures further from normal."
      >
        <ResponsiveContainer>
          <LineChart data={monthRows} margin={{ top: 5, right: 10, bottom: 5, left: -10 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis unit="°F" tick={{ fontSize: 12 }} domain={["auto", "auto"]} tickFormatter={(v) => v.toFixed(1)} />
            <Tooltip />
            <Legend />
            {Object.keys(byMonth).map((name) => (
              <Line key={name} type="monotone" dataKey={name} name={metrics.models[name].label}
                stroke={MODEL_COLORS[name]} strokeWidth={name === metrics.selected_model ? 3 : 1.5} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="grid gap-6 sm:grid-cols-2">
        {[
          ["Most predictable parks", parks.slice(0, 5)],
          ["Least predictable parks", parks.slice(-5).reverse()],
        ].map(([title, list]) => (
          <section key={title} className="rounded-2xl border border-line bg-paper-raised p-5">
            <h3 className="text-lg font-bold">{title}</h3>
            <ol className="mt-3 space-y-1.5 text-[15px]">
              {list.map((p) => (
                <li key={p.park_code} className="flex justify-between">
                  <span className="uppercase">{p.park_code}</span>
                  <span className="tabular-nums text-ink-muted">±{formatTempDelta(p.temp_max_mae)}</span>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </section>
  );
}

export default function ModelInsightsPage() {
  const metrics = useApi((signal) => api.modelPerformance({ signal }), []);
  const m = metrics.data;

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <PageHeader title="Model insights">
        How ParkWise turns eleven years of daily weather into estimates for future trips, and how well each
        approach holds up on data it has never seen.
      </PageHeader>

      {metrics.loading && <Loading label="Loading model results…" />}
      {metrics.error && <div className="mt-8"><ErrorMessage error={metrics.error} onRetry={metrics.reload} /></div>}
      {m && (
        <>
          <Splits split={m.split} rows={m.rows} />
          <Headline metrics={m} />
          <ModelTable metrics={m} />
          <Charts metrics={m} />
        </>
      )}

      <section className="mt-12 rounded-2xl bg-spruce-deep p-6 text-paper sm:p-8">
        <h2 className="text-2xl font-bold">What these models can't tell you</h2>
        <ul className="mt-4 space-y-3">
          {LIMITATIONS.map((item) => (
            <li key={item} className="flex gap-3 leading-relaxed text-paper/90">
              <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-lichen" aria-hidden="true" />
              {item}
            </li>
          ))}
        </ul>
        {m && <p className="mt-5 text-sm text-lichen">Trained {new Date(m.trained_at).toLocaleString()}.</p>}
      </section>
    </div>
  );
}

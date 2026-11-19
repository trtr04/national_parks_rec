import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import PageHeader from "../components/PageHeader.jsx";
import ParkPicker from "../components/ParkPicker.jsx";
import { EmptyState, ErrorMessage, Loading } from "../components/StateMessage.jsx";
import { api } from "../services/api.js";
import { useApi } from "../services/useApi.js";
import { MONTH_NAMES, cToF } from "../services/units.js";

const round1 = (n) => (n === null || n === undefined ? null : Math.round(n * 10) / 10);

function ChartCard({ title, children }) {
  return (
    <section className="rounded-2xl border border-line bg-paper-raised p-5">
      <h2 className="text-xl font-bold">{title}</h2>
      <div className="mt-4 h-72">{children}</div>
    </section>
  );
}

function Charts({ history, seasonal }) {
  const daily = history.observations.map((o) => ({
    date: o.date,
    high: o.temp_max === null ? null : round1(cToF(o.temp_max)),
    low: o.temp_min === null ? null : round1(cToF(o.temp_min)),
  }));
  const monthly = seasonal.months.map((m) => ({
    month: MONTH_NAMES[m.month - 1],
    high: m.avg_temp_max === null ? null : round1(cToF(m.avg_temp_max)),
    low: m.avg_temp_min === null ? null : round1(cToF(m.avg_temp_min)),
    wet: m.wet_day_frequency === null ? null : Math.round(m.wet_day_frequency * 100),
  }));

  return (
    <div className="mt-8 grid gap-6 lg:grid-cols-2">
      <div className="lg:col-span-2">
        <ChartCard title={`Daily highs and lows, ${history.start_date} to ${history.end_date}`}>
          <ResponsiveContainer>
            <LineChart data={daily} margin={{ top: 5, right: 10, bottom: 5, left: -10 }}>
              <CartesianGrid stroke="var(--color-line)" vertical={false} />
              <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 12 }} />
              <YAxis unit="°F" tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="high" name="High" stroke="var(--color-ochre)" dot={false} strokeWidth={1.5} />
              <Line type="monotone" dataKey="low" name="Low" stroke="var(--color-sky)" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <ChartCard title="Average monthly temperatures">
        <ResponsiveContainer>
          <BarChart data={monthly} margin={{ top: 5, right: 10, bottom: 5, left: -10 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis unit="°F" tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="high" name="Avg high" fill="var(--color-ochre)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="low" name="Avg low" fill="var(--color-sky)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title={`Share of days with ${seasonal.wet_day_threshold_mm} mm+ precipitation`}>
        <ResponsiveContainer>
          <BarChart data={monthly} margin={{ top: 5, right: 10, bottom: 5, left: -10 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis unit="%" domain={[0, 100]} tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="wet" name="Wet days" fill="var(--color-spruce)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}

export default function HistoryDashboard() {
  const parks = useApi((signal) => api.listParks(null, { signal }), []);
  const [parkCode, setParkCode] = useState("");

  const history = useApi((signal) => api.history(parkCode, {}, { signal }), [parkCode], Boolean(parkCode));
  const seasonal = useApi((signal) => api.seasonal(parkCode, { signal }), [parkCode], Boolean(parkCode));
  const park = parks.data?.parks.find((p) => p.park_code === parkCode);

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <PageHeader title="Weather history">
        Daily records from 2015 through 2025 for each park's visitor area: the raw material behind every
        climate estimate.
      </PageHeader>

      <div className="mt-8 max-w-md">
        {parks.error ? (
          <ErrorMessage error={parks.error} onRetry={parks.reload} />
        ) : (
          <ParkPicker parks={parks.data?.parks ?? []} value={parkCode} onChange={setParkCode} disabled={parks.loading} />
        )}
      </div>

      <div className="mt-8">
        {!parkCode ? (
          <EmptyState title="Choose a park to see its weather history">
            Charts show daily temperatures, monthly averages and how often it rains or snows.
          </EmptyState>
        ) : history.loading || seasonal.loading ? (
          <Loading label="Loading weather history…" />
        ) : history.error || seasonal.error ? (
          <ErrorMessage error={history.error || seasonal.error} onRetry={() => { history.reload(); seasonal.reload(); }} />
        ) : history.data?.count === 0 ? (
          <EmptyState title={`No weather history stored for ${park?.park_name ?? parkCode} yet`}>
            Load it with `python -m scripts.load_weather_history` from the backend folder; this
            page fills in automatically.
          </EmptyState>
        ) : (
          history.data && seasonal.data && <Charts history={history.data} seasonal={seasonal.data} />
        )}
      </div>
    </div>
  );
}

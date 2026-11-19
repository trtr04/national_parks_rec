import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ACTIVITIES, activityLabel } from "../components/ActivityPicker.jsx";
import PageHeader from "../components/PageHeader.jsx";
import { LABEL_STYLES } from "../components/ScoreBadge.jsx";
import { ErrorMessage, Loading, Panel } from "../components/StateMessage.jsx";
import { api } from "../services/api.js";
import { useApi } from "../services/useApi.js";
import { MONTH_LONG, formatPercent, formatTemp } from "../services/units.js";

export const DISTANCES = [
  { value: "", label: "Any distance" },
  { value: "250", label: "Within 250 miles" },
  { value: "500", label: "Within 500 miles" },
  { value: "1000", label: "Within 1,000 miles" },
  { value: "2000", label: "Within 2,000 miles" },
];

const PART_LABELS = {
  weather: "Weather",
  temperature: "Temperature",
  scenery: "Scenery",
  wildlife: "Wildlife",
  distance: "Distance",
};

const ACTIVITY_KEYS = ACTIVITIES.map((a) => a.value);
const nextMonth = () => (new Date().getMonth() + 1) % 12 + 1;

/** Toggle `key` in a list. */
export function toggle(list, key) {
  return list.includes(key) ? list.filter((k) => k !== key) : [...list, key];
}

/**
 * Preferences live in the address bar, so a refresh keeps them and a link can be shared:
 *   /find?month=7&activity=camping&from=Seattle%2C+WA&within=500&temp=mild&scenery=lakes_rivers,forests
 * Anything missing or unrecognised falls back to the default.
 */
export function readPrefs(params, defaultMonth = nextMonth()) {
  const list = (key) => (params.get(key) || "").split(",").filter(Boolean);
  const month = Number(params.get("month"));
  const activity = params.get("activity");
  return {
    month: month >= 1 && month <= 12 ? month : defaultMonth,
    activity: ACTIVITY_KEYS.includes(activity) ? activity : "hiking",
    origin: params.get("from") || "",
    maxMiles: DISTANCES.some((d) => d.value === params.get("within")) ? params.get("within") : "",
    temperature: params.get("temp") || "",
    scenery: list("scenery"),
    wildlife: list("wildlife"),
    amenities: list("need"),
    includePoor: params.get("poor") === "1",
  };
}

/** The inverse of readPrefs: only non-default choices go in the address bar. */
export function writePrefs(prefs) {
  const params = new URLSearchParams();
  params.set("month", String(prefs.month));
  if (prefs.activity !== "hiking") params.set("activity", prefs.activity);
  if (prefs.origin) params.set("from", prefs.origin);
  if (prefs.origin && prefs.maxMiles) params.set("within", prefs.maxMiles);
  if (prefs.temperature) params.set("temp", prefs.temperature);
  if (prefs.scenery.length) params.set("scenery", prefs.scenery.join(","));
  if (prefs.wildlife.length) params.set("wildlife", prefs.wildlife.join(","));
  if (prefs.amenities.length) params.set("need", prefs.amenities.join(","));
  if (prefs.includePoor) params.set("poor", "1");
  return params;
}

/** How many optional choices are active (shown on the phone "Filters" button). */
export function activeCount(prefs) {
  return (
    (prefs.origin ? 1 : 0) + (prefs.maxMiles && prefs.origin ? 1 : 0) + (prefs.temperature ? 1 : 0) +
    prefs.scenery.length + prefs.wildlife.length + prefs.amenities.length + (prefs.includePoor ? 1 : 0)
  );
}

/** The request body for /api/recommend/parks; leaves out anything the user skipped. */
export function buildRequest(prefs) {
  const body = { month: prefs.month, activity: prefs.activity, limit: 9 };
  if (prefs.origin) {
    body.origin = prefs.origin;
    if (prefs.maxMiles) body.max_miles = Number(prefs.maxMiles);
  }
  if (prefs.temperature) body.temperature = prefs.temperature;
  ["scenery", "wildlife", "amenities"].forEach((key) => {
    if (prefs[key].length) body[key] = prefs[key];
  });
  if (prefs.includePoor) body.include_poor_weather = true;
  return body;
}

/** The smallest distance choice that reaches `miles`, or "" (any) if none does. */
export function distanceToReach(miles) {
  return DISTANCES.find((d) => d.value && Number(d.value) >= miles)?.value ?? "";
}

function Chips({ legend, hint, options, selected, onChange, single = false }) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium text-ink">
        {legend} {hint && <span className="font-normal text-ink-muted">{hint}</span>}
      </legend>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => {
          const on = single ? selected === o.key : selected.includes(o.key);
          return (
            <button
              key={o.key}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(single ? (on ? "" : o.key) : toggle(selected, o.key))}
              className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                on ? "border-spruce bg-spruce text-paper" : "border-line bg-paper-raised text-ink hover:border-lichen"
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function Select({ label, value, onChange, children, disabled, hint }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-line bg-paper-raised px-3 py-2.5 text-[15px] text-ink disabled:opacity-50"
      >
        {children}
      </select>
      {hint && <span className="mt-1 block text-xs text-ink-muted">{hint}</span>}
    </label>
  );
}

/** Collapsible group so the long chip lists don't push results off a phone screen. */
function Group({ title, count, defaultOpen, children }) {
  return (
    <details open={defaultOpen} className="group border-t border-line pt-4">
      <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-semibold text-ink">
        <span>
          {title}
          {count > 0 && <span className="ml-2 rounded-full bg-spruce px-2 py-0.5 text-xs text-paper">{count}</span>}
        </span>
        <span className="text-ink-muted transition-transform group-open:rotate-180" aria-hidden="true">▾</span>
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

function ScoreHelp({ weights }) {
  return (
    <p className="text-sm text-ink-muted">
      <span className="font-medium text-ink">Match score</span> (0–100) blends{" "}
      {Object.entries(weights)
        .map(([key, w]) => `${PART_LABELS[key].toLowerCase()} ${Math.round(w * 100)}%`)
        .join(", ")}
      . Parts you skip don't count.
    </p>
  );
}

function PartBars({ parts, weights }) {
  return (
    <dl className="grid grid-cols-[auto_1fr_auto] items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
      {Object.entries(weights).map(([key, w]) => (
        <div key={key} className="contents">
          <dt>
            {PART_LABELS[key]} <span className="opacity-70">{Math.round(w * 100)}%</span>
          </dt>
          <dd className="h-1.5 overflow-hidden rounded-full bg-line" aria-hidden="true">
            <div className="h-full rounded-full bg-sky" style={{ width: `${parts[key]}%` }} />
          </dd>
          <dd className="tabular-nums">{Math.round(parts[key])}</dd>
        </div>
      ))}
    </dl>
  );
}

function feeText(fee) {
  if (fee === null || fee === undefined) return "No vehicle entrance fee listed";
  return `Entrance $${Number(fee).toFixed(0)} per vehicle`;
}

function ParkCard({ park, rank, weights, activity }) {
  const weatherStyle = LABEL_STYLES[park.weather.label] ?? LABEL_STYLES.Fair;
  return (
    <article className="flex flex-col overflow-hidden rounded-2xl border border-line bg-paper-raised">
      <div className="relative h-40 bg-gradient-to-br from-spruce to-sky">
        {park.photo ? (
          <img src={park.photo.url} alt={park.photo.alt || park.park_name} className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <svg viewBox="0 0 320 160" className="h-full w-full" aria-hidden="true" preserveAspectRatio="none">
            <path d="M0 160 L80 70 L130 115 L190 45 L260 110 L320 80 L320 160 Z" fill="var(--color-spruce-deep)" opacity="0.6" />
          </svg>
        )}
        <span
          className="absolute left-3 top-3 rounded-full bg-paper/95 px-2.5 py-1 text-sm text-spruce-deep"
          title="Match score: a weighted blend of the parts you chose, 0–100"
        >
          <span className="font-display font-bold">#{rank}</span> · Match score{" "}
          <span className="font-display font-bold tabular-nums">{Math.round(park.score)}</span>
        </span>
        {park.photo && (
          <span className="absolute bottom-1 right-2 text-[10px] text-paper/90 drop-shadow">{park.photo.credit}</span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-5">
        <div>
          <h3 className="text-xl font-bold leading-snug">{park.park_name}</h3>
          <p className="text-sm text-ink-muted">
            {park.state.replaceAll(",", ", ")}
            {park.distance_miles !== null && ` · about ${park.distance_miles.toLocaleString()} mi away`}
          </p>
        </div>

        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className={`rounded-full px-2.5 py-0.5 font-semibold ${weatherStyle.badge}`}>
            {park.weather.label} for {activityLabel(activity).toLowerCase()}
          </span>
          <span className="tabular-nums text-ink-muted">
            {formatTemp(park.weather.temp_max_c)} / {formatTemp(park.weather.temp_min_c)} · wet{" "}
            {formatPercent(park.weather.wet_probability)} of days
          </span>
        </p>

        {park.warnings.length > 0 && (
          <ul className="space-y-1 rounded-xl border border-ochre/30 bg-ochre-soft px-3 py-2 text-sm text-ink" aria-label="Before you go">
            {park.warnings.map((w) => (
              <li key={w} className="flex gap-2">
                <span aria-hidden="true" className="text-ochre">⚠</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        )}

        {park.scenery.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="Scenery">
            {park.scenery.map((s) => (
              <li key={s} className="rounded-md bg-sky-soft px-2 py-0.5 text-xs text-sky">{s}</li>
            ))}
          </ul>
        )}

        <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-ink-muted">
          {park.reasons.slice(1).map((r) => <li key={r}>{r}</li>)}
          <li>{feeText(park.vehicle_fee_usd)}.</li>
        </ul>

        <div className="mt-auto space-y-3">
          <PartBars parts={park.parts} weights={weights} />
          <div className="flex flex-wrap gap-2 text-sm">
            <Link
              to={`/best-time?park=${park.park_code}&activity=${activity}`}
              className="rounded-lg bg-spruce px-3 py-1.5 font-medium text-paper hover:bg-spruce-deep"
            >
              Best months
            </Link>
            {park.nps_url && (
              <a href={park.nps_url} target="_blank" rel="noreferrer" className="rounded-lg border border-line px-3 py-1.5 font-medium text-ink hover:border-lichen">
                NPS site ↗
              </a>
            )}
            {park.trail_guide && (
              <span className="rounded-lg bg-ochre-soft px-3 py-1.5 font-medium text-ochre">Trail guide available</span>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

function NoMatch({ data, prefs, update }) {
  const nearest = data.nearest_beyond_limit;
  const reach = nearest ? distanceToReach(nearest.distance_miles) : null;
  return (
    <Panel
      title="No park matches all of that"
      action={
        <div className="flex flex-wrap gap-2">
          {nearest && (
            <button
              type="button"
              onClick={() => update({ maxMiles: reach })}
              className="rounded-lg bg-spruce px-3 py-1.5 text-sm font-medium text-paper"
            >
              {reach ? `Show parks within ${Number(reach).toLocaleString()} miles` : "Show parks at any distance"}
            </button>
          )}
          {data.poor_weather_hidden > 0 && !prefs.includePoor && (
            <button
              type="button"
              onClick={() => update({ includePoor: true })}
              className="rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-ink"
            >
              Include {data.poor_weather_hidden} parks with poor weather
            </button>
          )}
        </div>
      }
    >
      {nearest ? (
        <>
          The closest park that fits everything else is <strong className="text-ink">{nearest.park_name}</strong>, about{" "}
          {nearest.distance_miles.toLocaleString()} miles from {prefs.origin}.
        </>
      ) : (
        "Try fewer must-haves, another month, or include parks with poor weather."
      )}
    </Panel>
  );
}

export default function FindParkPage() {
  const options = useApi((signal) => api.recommendOptions({ signal }), []);
  const [searchParams, setSearchParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const prefs = useMemo(() => readPrefs(searchParams), [searchParams]);
  const update = (changes) => setSearchParams(writePrefs({ ...prefs, ...changes }), { replace: true });
  const set = (key) => (value) => update({ [key]: value });
  const reset = () => setSearchParams(writePrefs(readPrefs(new URLSearchParams(), prefs.month)), { replace: true });

  const body = useMemo(() => buildRequest(prefs), [prefs]);
  const result = useApi((signal) => api.recommendParks(body, { signal }), [JSON.stringify(body)]);
  const opts = options.data;
  const data = result.data;
  const active = activeCount(prefs);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
      <PageHeader title="Find your national park">
        Tell us when you're going and what you'd like to see. We rank all 63 national parks by typical weather for
        that month, plus the scenery, wildlife, distance and amenities you pick.
      </PageHeader>

      {options.error ? (
        <div className="mt-8"><ErrorMessage error={options.error} onRetry={options.reload} /></div>
      ) : !opts ? (
        <Loading label="Loading choices…" />
      ) : (
        <div className="mt-6 grid gap-6 lg:mt-8 lg:grid-cols-[22rem_1fr] lg:gap-8">
          {/* Phones: the two basics stay visible, everything else sits behind "Filters". */}
          <div className="flex items-end gap-2 lg:hidden">
            <div className="flex-1">
              <Select label="Month" value={prefs.month} onChange={(v) => set("month")(Number(v))}>
                {MONTH_LONG.map((name, i) => <option key={name} value={i + 1}>{name}</option>)}
              </Select>
            </div>
            <div className="flex-1">
              <Select label="Activity" value={prefs.activity} onChange={set("activity")}>
                {ACTIVITIES.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
              </Select>
            </div>
            <button
              type="button"
              aria-expanded={filtersOpen}
              aria-controls="find-filters"
              onClick={() => setFiltersOpen((v) => !v)}
              className="rounded-xl border border-spruce bg-paper-raised px-3 py-2.5 text-[15px] font-medium text-spruce"
            >
              Filters{active > 0 && ` (${active})`}
            </button>
          </div>

          <form
            id="find-filters"
            className={`${filtersOpen ? "block" : "hidden"} space-y-4 self-start rounded-2xl border border-line bg-paper-raised p-5 lg:sticky lg:top-20 lg:block lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto`}
            onSubmit={(e) => e.preventDefault()}
          >
            <div className="hidden space-y-4 lg:block">
              <Select label="Travel month" value={prefs.month} onChange={(v) => set("month")(Number(v))}>
                {MONTH_LONG.map((name, i) => <option key={name} value={i + 1}>{name}</option>)}
              </Select>
              <Chips
                legend="Activity"
                options={ACTIVITIES.map((a) => ({ key: a.value, label: a.label }))}
                selected={prefs.activity}
                onChange={(v) => v && set("activity")(v)}
                single
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Select label="Starting from" value={prefs.origin} onChange={set("origin")}>
                <option value="">Anywhere</option>
                {opts.origins.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
              <Select
                label="Distance"
                value={prefs.maxMiles}
                onChange={set("maxMiles")}
                disabled={!prefs.origin}
                hint={!prefs.origin ? "Pick a city first" : null}
              >
                {DISTANCES.map((d) => <option key={d.label} value={d.value}>{d.label}</option>)}
              </Select>
            </div>
            <Chips legend="Daytime temperature" hint="(optional)" options={opts.temperatures} selected={prefs.temperature} onChange={set("temperature")} single />
            <Group title="Scenery" count={prefs.scenery.length} defaultOpen>
              <Chips legend="" options={opts.scenery} selected={prefs.scenery} onChange={set("scenery")} />
            </Group>
            <Group title="Wildlife" count={prefs.wildlife.length} defaultOpen={prefs.wildlife.length > 0}>
              <Chips legend="" options={opts.wildlife} selected={prefs.wildlife} onChange={set("wildlife")} />
            </Group>
            <Group title="Must have" count={prefs.amenities.length} defaultOpen={prefs.amenities.length > 0}>
              <Chips legend="" options={opts.amenities} selected={prefs.amenities} onChange={set("amenities")} />
            </Group>
            <label className="flex items-start gap-2 border-t border-line pt-4 text-sm text-ink">
              <input
                type="checkbox"
                checked={prefs.includePoor}
                onChange={(e) => set("includePoor")(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-[var(--color-spruce)]"
              />
              <span>Include parks with poor weather that month</span>
            </label>
            <div className="flex items-center justify-between border-t border-line pt-4">
              <button type="button" onClick={reset} className="text-sm font-medium text-sky underline-offset-2 hover:underline">
                Reset choices
              </button>
              <button type="button" onClick={() => setFiltersOpen(false)} className="rounded-lg bg-spruce px-3 py-1.5 text-sm font-medium text-paper lg:hidden">
                Show results
              </button>
            </div>
            <p className="text-xs leading-relaxed text-ink-muted">
              {opts.notes.distance} {opts.notes.scenery} {opts.notes.campgrounds}
            </p>
          </form>

          <section aria-live="polite" className="min-w-0">
            {result.loading && !data ? (
              <Loading label="Ranking parks…" />
            ) : result.error ? (
              <ErrorMessage error={result.error} onRetry={result.reload} />
            ) : data && data.results.length === 0 ? (
              <NoMatch data={data} prefs={prefs} update={update} />
            ) : data && (
              <>
                <div className="mb-4 space-y-1">
                  <p className="text-ink-muted">
                    <span className="font-semibold text-ink">{data.matched}</span> of {data.considered} parks fit your choices
                    for {MONTH_LONG[data.month - 1]}. Showing the top {data.results.length}.
                    {data.poor_weather_hidden > 0 && !prefs.includePoor && (
                      <>
                        {" "}{data.poor_weather_hidden} with poor weather are hidden.{" "}
                        <button type="button" onClick={() => update({ includePoor: true })} className="font-medium text-sky underline-offset-2 hover:underline">
                          Show them
                        </button>
                      </>
                    )}
                  </p>
                  <ScoreHelp weights={data.weights} />
                </div>
                <div className={`grid gap-5 sm:grid-cols-2 xl:grid-cols-3 ${result.loading ? "opacity-60" : ""}`}>
                  {data.results.map((park, i) => (
                    <ParkCard key={park.park_code} park={park} rank={i + 1} weights={data.weights} activity={data.activity} />
                  ))}
                </div>
              </>
            )}
            {data && Object.keys(data.excluded).length > 0 && (
              <details className="mt-6 rounded-2xl border border-line bg-paper-raised px-5 py-3 text-sm">
                <summary className="cursor-pointer font-medium">
                  Why {Object.keys(data.excluded).length} parks were left out
                </summary>
                <ul className="mt-2 space-y-1 text-ink-muted">
                  {Object.entries(data.excluded).map(([code, e]) => (
                    <li key={code}><span className="font-medium text-ink">{e.park_name}</span>: {e.reason}</li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

// The API stores and returns metric units. The site shows U.S. units by default.

export const cToF = (c) => (c * 9) / 5 + 32;

export function formatTemp(celsius) {
  if (celsius === null || celsius === undefined) return "—";
  return `${Math.round(cToF(celsius))}°F`;
}

export function formatPrecipIn(mm) {
  if (mm === null || mm === undefined) return "—";
  return `${(mm / 25.4).toFixed(2)} in`;
}

export function formatPercent(fraction) {
  if (fraction === null || fraction === undefined) return "—";
  return `${Math.round(fraction * 100)}%`;
}

export const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export const kmhToMph = (kmh) => kmh * 0.621371;

export function formatWind(kmh) {
  if (kmh === null || kmh === undefined) return "—";
  return `${Math.round(kmhToMph(kmh))} mph`;
}

/** A temperature difference (an error, a spread) in °F. */
export function formatTempDelta(celsius) {
  if (celsius === null || celsius === undefined) return "—";
  return `${((celsius * 9) / 5).toFixed(1)}°F`;
}

/** [lo, hi] in °C -> "48–61°F". */
export function formatTempRange(range) {
  if (!range || range[0] === null || range[0] === undefined) return "—";
  return `${Math.round(cToF(range[0]))}–${Math.round(cToF(range[1]))}°F`;
}

/** 0.17 -> "about 1 day in 6", for climate frequencies (mirrors the backend's wording). */
export function formatOneIn(probability) {
  if (probability === null || probability === undefined) return "—";
  if (probability < 0.05) return "rarely";
  if (probability > 0.9) return "almost every day";
  return `about 1 day in ${Math.round(1 / probability)}`;
}

export const MONTH_LONG = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Calendar-date helpers. Dates travel as "YYYY-MM-DD" strings in the park's local sense.

/** Local calendar date as YYYY-MM-DD (toISOString alone would shift to UTC). */
export function isoDate(date) {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

export function daysFromToday(iso) {
  const today = new Date(isoDate(new Date()));
  return Math.round((new Date(iso) - today) / 86400000);
}

export function addDays(iso, n) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + n);
  return isoDate(d);
}

/** "2027-04-15" -> "Thu, Apr 15, 2027" (short) or "Thu 15" (compact). */
export function formatDate(iso, style = "short") {
  const d = new Date(`${iso}T12:00:00`);
  if (style === "compact") {
    // Built by hand: Intl orders weekday + day as "15 Thu" in en-US.
    return `${d.toLocaleDateString("en-US", { weekday: "short" })} ${d.getDate()}`;
  }
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

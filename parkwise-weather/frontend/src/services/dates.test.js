import { afterEach, describe, expect, it, vi } from "vitest";
import { addDays, daysFromToday, formatDate, isoDate } from "./dates.js";

afterEach(() => vi.useRealTimers());

describe("date helpers", () => {
  it("adds days across month and year ends", () => {
    expect(addDays("2026-12-30", 3)).toBe("2027-01-02");
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29"); // leap year
  });

  it("counts days from today using the local calendar date", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 1, 23, 30)); // 1 Nov 2026, 11:30 pm local
    expect(isoDate(new Date())).toBe("2026-11-01");
    expect(daysFromToday("2026-11-01")).toBe(0);
    expect(daysFromToday("2026-11-17")).toBe(16);
  });

  it("formats dates for people", () => {
    expect(formatDate("2027-04-15")).toBe("Thu, Apr 15, 2027");
    expect(formatDate("2027-04-15", "compact")).toBe("Thu 15");
  });
});

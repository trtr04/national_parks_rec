import { describe, expect, it } from "vitest";
import {
  cToF,
  formatOneIn,
  formatPercent,
  formatPrecipIn,
  formatTemp,
  formatTempDelta,
  formatTempRange,
  formatWind,
} from "./units.js";

describe("unit formatting", () => {
  it("converts Celsius to Fahrenheit", () => {
    expect(cToF(0)).toBe(32);
    expect(cToF(100)).toBe(212);
    expect(formatTemp(19.6)).toBe("67°F");
    expect(formatTemp(-40)).toBe("-40°F");
  });

  it("shows a dash for missing values", () => {
    for (const format of [formatTemp, formatPrecipIn, formatPercent, formatWind, formatTempDelta, formatOneIn]) {
      expect(format(null)).toBe("—");
      expect(format(undefined)).toBe("—");
    }
    expect(formatTempRange(null)).toBe("—");
  });

  it("formats ranges, wind, rain and differences", () => {
    expect(formatTempRange([13.7, 25.8])).toBe("57–78°F");
    expect(formatWind(19.6)).toBe("12 mph");
    expect(formatPrecipIn(25.4)).toBe("1.00 in");
    expect(formatPercent(0.184)).toBe("18%");
    // A 3.35 °C error is 6.0 °F: differences scale by 9/5 with no +32 offset.
    expect(formatTempDelta(3.35)).toBe("6.0°F");
  });

  it("describes frequencies the way the backend does", () => {
    expect(formatOneIn(0.184)).toBe("about 1 day in 5");
    expect(formatOneIn(0.02)).toBe("rarely");
    expect(formatOneIn(0.95)).toBe("almost every day");
  });
});

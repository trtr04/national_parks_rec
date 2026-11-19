import { describe, expect, it } from "vitest";
import { describeMonth } from "./BestTimePage.jsx";

const month = (overrides) => ({ temp_max_c: 18, wet_probability: 0.2, snow_probability: 0, wind_max_kmh: 15, ...overrides });

describe("describeMonth", () => {
  it("uses each activity's comfortable band", () => {
    expect(describeMonth(month({ temp_max_c: 18 }), "hiking")).toBe("Comfortable");
    expect(describeMonth(month({ temp_max_c: 26 }), "hiking")).toBe("Warm");
    expect(describeMonth(month({ temp_max_c: 26 }), "sightseeing")).toBe("Comfortable");
    expect(describeMonth(month({ temp_max_c: 40 }), "hiking")).toBe("Hot");
    expect(describeMonth(month({ temp_max_c: 0 }), "hiking")).toBe("Cold");
  });

  it("says 'but' when the extras pull the other way", () => {
    expect(describeMonth(month({ temp_max_c: 40, wet_probability: 0.05 }), "hiking")).toBe("Hot but mostly dry");
    expect(describeMonth(month({ wet_probability: 0.5 }), "hiking")).toBe("Comfortable but often wet");
    expect(describeMonth(month({ temp_max_c: 0, snow_probability: 0.5 }), "hiking")).toBe("Cold and snowy");
  });
});

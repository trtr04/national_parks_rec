import { describe, expect, it } from "vitest";
import { activeCount, buildRequest, distanceToReach, readPrefs, toggle, writePrefs } from "./FindParkPage.jsx";

const base = {
  month: 7, activity: "hiking", origin: "", maxMiles: "", temperature: "",
  scenery: [], wildlife: [], amenities: [], includePoor: false,
};

describe("buildRequest", () => {
  it("leaves out every preference the user skipped", () => {
    expect(buildRequest(base)).toEqual({ month: 7, activity: "hiking", limit: 9 });
  });

  it("only sends a distance limit together with a starting city", () => {
    expect(buildRequest({ ...base, maxMiles: "500" })).not.toHaveProperty("max_miles");
    expect(buildRequest({ ...base, origin: "Seattle, WA", maxMiles: "500" })).toMatchObject({
      origin: "Seattle, WA",
      max_miles: 500,
    });
  });

  it("sends chosen lists, temperature and the poor-weather switch", () => {
    const body = buildRequest({ ...base, temperature: "mild", scenery: ["lakes_rivers"], amenities: ["campground"], includePoor: true });
    expect(body).toMatchObject({ temperature: "mild", scenery: ["lakes_rivers"], amenities: ["campground"], include_poor_weather: true });
    expect(body).not.toHaveProperty("wildlife");
  });
});

describe("address bar", () => {
  it("round-trips preferences", () => {
    const prefs = { ...base, month: 9, activity: "camping", origin: "Seattle, WA", maxMiles: "500",
      temperature: "cool", scenery: ["forests", "lakes_rivers"], amenities: ["showers"], includePoor: true };
    expect(readPrefs(writePrefs(prefs))).toEqual(prefs);
  });

  it("keeps the address short and ignores bad values", () => {
    expect(writePrefs({ ...base, maxMiles: "500" }).toString()).toBe("month=7");
    const prefs = readPrefs(new URLSearchParams("month=13&activity=surfing&within=123"), 4);
    expect(prefs).toMatchObject({ month: 4, activity: "hiking", maxMiles: "" });
  });

  it("counts active filters", () => {
    expect(activeCount(base)).toBe(0);
    expect(activeCount({ ...base, origin: "Seattle, WA", maxMiles: "250", scenery: ["forests"] })).toBe(3);
  });
});

describe("distanceToReach", () => {
  it("picks the smallest choice that reaches a park", () => {
    expect(distanceToReach(320)).toBe("500");
    expect(distanceToReach(250)).toBe("250");
    expect(distanceToReach(4000)).toBe("");
  });
});

describe("toggle", () => {
  it("adds and removes a key", () => {
    expect(toggle(["a"], "b")).toEqual(["a", "b"]);
    expect(toggle(["a", "b"], "a")).toEqual(["b"]);
  });
});

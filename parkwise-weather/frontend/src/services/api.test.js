import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api.js";

function mockFetch(status, body) {
  const fetch = vi.fn().mockResolvedValue({ ok: status < 400, status, json: () => Promise.resolve(body) });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("sends query parameters and returns the JSON body", async () => {
    const fetch = mockFetch(200, { ok: true });
    await expect(api.predict({ parkCode: "zion", date: "2027-04-15", activity: "hiking" })).resolves.toEqual({ ok: true });
    const url = new URL(fetch.mock.calls[0][0]);
    expect(url.pathname).toBe("/api/weather/predict");
    expect(Object.fromEntries(url.searchParams)).toEqual({ park_code: "zion", date: "2027-04-15", activity: "hiking" });
  });

  it("posts the comparison as JSON", async () => {
    const fetch = mockFetch(200, {});
    await api.compare({ parkCodes: ["zion", "yose"], date: "2027-05-20", activity: "camping" });
    const [, init] = fetch.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ park_codes: ["zion", "yose"], date: "2027-05-20", activity: "camping" });
  });

  it("turns the backend's error shape into an ApiError", async () => {
    mockFetch(404, { error: { code: "not_found", message: "No park with code 'nope'.", details: null } });
    const error = await api.getPark("nope").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: "not_found", message: "No park with code 'nope'." });
  });

  it("reports an unreachable API as a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.health()).rejects.toMatchObject({ code: "network_error", status: 0 });
  });
});

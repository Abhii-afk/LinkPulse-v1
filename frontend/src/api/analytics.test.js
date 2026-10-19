import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./client.js";
import { buildAnalyticsQuery, getAnalyticsOverview } from "./analytics.js";

describe("analytics API integration", () => {
  it("serializes the selected date range and granularity", () => {
    expect(
      buildAnalyticsQuery({
        from: "2026-10-01T00:00:00.000Z",
        to: "2026-10-31T00:00:00.000Z",
        granularity: "day",
      }),
    ).toBe("?from=2026-10-01T00%3A00%3A00.000Z&to=2026-10-31T00%3A00%3A00.000Z&granularity=day");
  });

  it("uses the user-scoped endpoint with the authenticated bearer token", async () => {
    const fetchImpl = vi.fn(async (url, options) => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ summary: { total_clicks: 4 } }),
      url,
      options,
    }));

    const response = await getAnalyticsOverview({
      accessToken: "user-token",
      from: "2026-10-01T00:00:00.000Z",
      to: "2026-10-31T00:00:00.000Z",
      granularity: "day",
      fetchImpl,
    });

    expect(response.summary.total_clicks).toBe(4);
    expect(fetchImpl.mock.calls[0][0]).toContain("/api/v1/analytics/overview?");
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBe("Bearer user-token");
  });

  it("uses the admin-wide endpoint only when the caller is marked admin", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ summary: { total_clicks: 9 } }),
    }));

    await getAnalyticsOverview({ accessToken: "admin-token", isAdmin: true, fetchImpl });

    expect(fetchImpl.mock.calls[0][0]).toContain("/api/v1/admin/analytics/overview");
  });

  it("preserves permission errors from the API", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: false,
      status: 403,
      text: async () => JSON.stringify({ detail: "Insufficient permissions" }),
    }));

    await expect(getAnalyticsOverview({ accessToken: "user-token", fetchImpl })).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
      message: "Insufficient permissions",
    });
  });

  it("surfaces network failures instead of returning fabricated metrics", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("offline");
    });

    await expect(getAnalyticsOverview({ accessToken: "user-token", fetchImpl })).rejects.toBeInstanceOf(ApiError);
  });
});

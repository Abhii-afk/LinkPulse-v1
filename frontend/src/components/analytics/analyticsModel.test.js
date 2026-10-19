import { describe, expect, it } from "vitest";

import {
  getDateRange,
  getLinePoints,
  getLinkStatus,
  getManagedLinks,
  getStatusLabel,
  getTrafficPoints,
  hasAnalyticsData,
} from "./analyticsModel.js";

describe("analytics dashboard data mapping", () => {
  it("creates a deterministic date range for the API query", () => {
    expect(getDateRange("7d", new Date("2026-10-20T12:00:00.000Z"))).toEqual({
      value: "7d",
      label: "Last 7 days",
      from: "2026-10-13T12:00:00.000Z",
      to: "2026-10-20T12:00:00.000Z",
    });
  });

  it("maps real time-series values into a chart line without inventing points", () => {
    const data = {
      clicks_over_time: [
        { bucket: "2026-10-01T00:00:00Z", clicks: 4, human_clicks: 3, bot_clicks: 1 },
        { bucket: "2026-10-02T00:00:00Z", clicks: 8, human_clicks: 7, bot_clicks: 1 },
      ],
    };
    const points = getTrafficPoints(data);

    expect(points).toEqual([
      { bucket: "2026-10-01T00:00:00Z", clicks: 4, human_clicks: 3, bot_clicks: 1 },
      { bucket: "2026-10-02T00:00:00Z", clicks: 8, human_clicks: 7, bot_clicks: 1 },
    ]);
    expect(getLinePoints(points, 100, 100)).toBe("24.00,50.00 76.00,24.00");
  });

  it("recognizes empty and non-empty analytics responses", () => {
    expect(hasAnalyticsData({ summary: { total_clicks: 0, active_links: 0 }, top_links: [] })).toBe(false);
    expect(hasAnalyticsData({ summary: { total_clicks: 1, active_links: 0 }, top_links: [] })).toBe(true);
    expect(getManagedLinks({ top_links: [{ short_code: "top", clicks: 1 }] })).toHaveLength(1);
  });

  it("preserves disabled and expired status for historical table rows", () => {
    expect(getLinkStatus({ is_active: false })).toBe("disabled");
    expect(getLinkStatus({ is_active: true, expires_at: "2020-01-01T00:00:00Z" })).toBe("expired");
    expect(getStatusLabel("expired")).toBe("Expired");
  });
});

import { describe, expect, it } from "vitest";

import DashboardState from "./DashboardState.jsx";
import ManagedLinksTable, { getManagedLinkRows } from "./ManagedLinksTable.jsx";
import MetricCard from "./MetricCard.jsx";

describe("analytics dashboard components", () => {
  it("renders metric values supplied by the API", () => {
    const view = MetricCard({ label: "Total clicks", value: 1428, detail: "Recorded visits" });

    expect(view.type).toBe("article");
    expect(view.props.children[1].props.children).toBe("1,428");
    expect(view.props.children[2].props.children).toBe("Recorded visits");
  });

  it("maps managed links into status, history, and click-cap rows", () => {
    const rows = getManagedLinkRows({
      top_links: [
        { link_id: "disabled-1", short_code: "old", clicks: 12, click_limit: 50, is_active: false, is_abusive: false },
        { link_id: "active-1", short_code: "new", clicks: 4, is_active: true, is_abusive: false },
      ],
    });

    expect(rows).toEqual([
      expect.objectContaining({
        short_code: "old",
        clickCap: "12 / 50",
        status: "disabled",
        historical: true,
      }),
      expect.objectContaining({
        short_code: "new",
        clickCap: "Not reported",
        status: "active",
        historical: false,
      }),
    ]);

    const table = ManagedLinksTable({ data: { top_links: [] } });
    expect(table.type).toBe("section");
  });

  it("exposes explicit loading, empty, and error presentation states", () => {
    const loading = DashboardState({ type: "loading", title: "Loading", message: "Please wait" });
    const empty = DashboardState({ type: "empty", title: "No data", message: "Nothing yet" });
    const error = DashboardState({ type: "error", title: "Unavailable", message: "Try again" });

    expect(loading.props.role).toBe("status");
    expect(empty.props.className).toContain("dashboard-state-empty");
    expect(error.props.children[1].props.children).toBe("Unavailable");
  });
});

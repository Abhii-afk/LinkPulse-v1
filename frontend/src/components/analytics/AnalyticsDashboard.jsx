import { useEffect, useMemo, useState } from "react";

import { getAnalyticsOverview } from "../../api/analytics.js";
import { ApiError } from "../../api/client.js";
import "./analytics.css";
import BreakdownChart from "./BreakdownChart.jsx";
import DashboardState from "./DashboardState.jsx";
import ManagedLinksTable from "./ManagedLinksTable.jsx";
import MetricCard from "./MetricCard.jsx";
import TrafficChart from "./TrafficChart.jsx";
import { DATE_RANGE_OPTIONS, getDateRange, hasAnalyticsData } from "./analyticsModel.js";

function getPermissionMessage(error) {
  if (error instanceof ApiError && error.status === 401) {
    return "Sign in to view analytics for your LinkPulse workspace.";
  }
  if (error instanceof ApiError && error.status === 403) {
    return "Your account does not have permission to view these analytics.";
  }
  return error?.message || "The analytics service could not be reached.";
}

function useAnalyticsOverview({ accessToken, isAdmin, selectedRange, refreshSignal, refreshIntervalMs = 30000 }) {
  const [state, setState] = useState({ status: accessToken ? "loading" : "unauthenticated", data: null, error: null });
  const [pollTick, setPollTick] = useState(0);
  const range = useMemo(() => getDateRange(selectedRange), [selectedRange]);

  useEffect(() => {
    let cancelled = false;

    if (!accessToken) {
      setState({ status: "unauthenticated", data: null, error: null });
      return () => {
        cancelled = true;
      };
    }

    setState((previous) => ({ ...previous, status: previous.data ? "refreshing" : "loading", error: null }));
    getAnalyticsOverview({
      accessToken,
      isAdmin,
      from: range.from,
      to: range.to,
      granularity: "day",
    })
      .then((data) => {
        if (!cancelled) {
          setState({ status: "ready", data, error: null });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setState((previous) => ({ status: "error", data: previous.data, error }));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [accessToken, isAdmin, range.from, range.to, refreshSignal, pollTick]);

  useEffect(() => {
    if (!accessToken || !refreshIntervalMs) {
      return undefined;
    }
    const interval = window.setInterval(() => {
      setPollTick((value) => value + 1);
    }, refreshIntervalMs);
    return () => window.clearInterval(interval);
  }, [accessToken, refreshIntervalMs]);

  return { ...state, range, refresh: () => setPollTick((value) => value + 1) };
}

export default function AnalyticsDashboard({
  accessToken,
  isAdmin = false,
  selectedRange = "30d",
  onRangeChange,
  refreshSignal = 0,
  refreshIntervalMs = 30000,
}) {
  const analytics = useAnalyticsOverview({
    accessToken,
    isAdmin,
    selectedRange,
    refreshSignal,
    refreshIntervalMs,
  });
  const data = analytics.data;
  const summary = data?.summary || {};

  if (analytics.status === "unauthenticated") {
    return (
      <DashboardState
        type="permission"
        title="Analytics are private"
        message="Pass an authenticated LinkPulse session to load workspace analytics."
      />
    );
  }

  if (analytics.status === "loading" && !data) {
    return <DashboardState type="loading" title="Loading your analytics" message="Aggregating the latest click events…" />;
  }

  if (analytics.status === "error" && !data) {
    return (
      <DashboardState
        type="error"
        title={analytics.error instanceof ApiError && analytics.error.status === 403 ? "Analytics access denied" : "Analytics unavailable"}
        message={getPermissionMessage(analytics.error)}
        onRetry={analytics.refresh}
      />
    );
  }

  const empty = !hasAnalyticsData(data);

  return (
    <section className="analytics-dashboard" aria-labelledby="dashboard-heading">
      <div className="dashboard-toolbar">
        <div>
          <p className="section-kicker">Workspace intelligence</p>
          <h2 id="dashboard-heading">Your link performance</h2>
          <p>Aggregated from asynchronous click events. Disabled and expired links keep their history.</p>
        </div>
        <div className="dashboard-controls">
          <label className="range-control">
            <span className="sr-only">Analytics date range</span>
            <select value={selectedRange} onChange={(event) => onRangeChange?.(event.target.value)}>
              {DATE_RANGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <span className="refresh-state">
            {analytics.status === "refreshing" ? "Refreshing…" : `Auto-refresh · ${refreshIntervalMs / 1000}s`}
          </span>
        </div>
      </div>

      {empty && (
        <div className="dashboard-empty-banner" role="status">
          <strong>No analytics data in this range yet.</strong>
          <span>Create a link and send traffic to see real metrics here.</span>
        </div>
      )}

      {analytics.status === "error" && data && (
        <div className="dashboard-inline-error" role="alert">
          {getPermissionMessage(analytics.error)}
        </div>
      )}

      <div className="metric-grid">
        <MetricCard label="Total clicks" value={summary.total_clicks} detail="Recorded visits" accent="blue" />
        <MetricCard label="Active links" value={summary.active_links} detail="Currently enabled" accent="green" />
        <MetricCard label="Bots filtered" value={summary.bot_clicks} detail="Heuristic detection" accent="amber" />
        <MetricCard label="Unique visitors" value={summary.unique_visitors} detail="Distinct visitor IPs" accent="purple" />
      </div>

      <div className="dashboard-chart-grid">
        <TrafficChart data={data} />
        <div className="breakdown-stack">
          <BreakdownChart title="Device breakdown" kicker="Audience" items={data?.device_breakdown} />
          <BreakdownChart title="Browser breakdown" kicker="Clients" items={data?.browser_breakdown} />
        </div>
      </div>

      <ManagedLinksTable data={data} />
    </section>
  );
}

export { getPermissionMessage, useAnalyticsOverview };

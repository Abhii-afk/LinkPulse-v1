import { requestJson } from "./client.js";

export function buildAnalyticsQuery({ from, to, granularity = "day" } = {}) {
  const params = new URLSearchParams();
  if (from) {
    params.set("from", from);
  }
  if (to) {
    params.set("to", to);
  }
  if (granularity) {
    params.set("granularity", granularity);
  }

  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function getAnalyticsOverview({
  accessToken,
  isAdmin = false,
  from,
  to,
  granularity = "day",
  fetchImpl,
} = {}) {
  const endpoint = isAdmin
    ? "/api/v1/admin/analytics/overview"
    : "/api/v1/analytics/overview";

  return requestJson(`${endpoint}${buildAnalyticsQuery({ from, to, granularity })}`, {
    accessToken,
    fetchImpl,
  });
}

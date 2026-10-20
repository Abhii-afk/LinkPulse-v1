export const DATE_RANGE_OPTIONS = [
  { value: "7d", label: "Last 7 days", days: 7 },
  { value: "30d", label: "Last 30 days", days: 30 },
  { value: "90d", label: "Last 90 days", days: 90 },
];

export function getDateRange(value = "30d", now = new Date()) {
  const option = DATE_RANGE_OPTIONS.find((item) => item.value === value) || DATE_RANGE_OPTIONS[1];
  const to = new Date(now);
  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - option.days);

  return {
    value: option.value,
    label: option.label,
    from: from.toISOString(),
    to: to.toISOString(),
  };
}

export function formatMetric(value) {
  return new Intl.NumberFormat("en-US").format(Number(value) || 0);
}

export function formatPercentage(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

export function getManagedLinks(data) {
  if (Array.isArray(data?.managed_links)) {
    return data.managed_links;
  }
  return Array.isArray(data?.top_links) ? data.top_links : [];
}

export function getLinkStatus(link) {
  if (link?.status) {
    return link.status;
  }
  if (link?.is_abusive) {
    return "abusive";
  }
  if (link?.expires_at && new Date(link.expires_at) <= new Date()) {
    return "expired";
  }
  return link?.is_active === false ? "disabled" : "active";
}

export function getStatusLabel(status) {
  return {
    active: "Active",
    disabled: "Disabled",
    abusive: "Suspended",
    expired: "Expired",
  }[status] || "Unknown";
}

export function getStatusTone(status) {
  return {
    active: "success",
    disabled: "muted",
    abusive: "danger",
    expired: "warning",
  }[status] || "muted";
}

export function getTrafficPoints(data) {
  return (data?.clicks_over_time || []).map((point) => ({
    bucket: point.bucket,
    clicks: Number(point.clicks) || 0,
    human_clicks: Number(point.human_clicks) || 0,
    bot_clicks: Number(point.bot_clicks) || 0,
  }));
}

export function getLinePoints(points, width = 640, height = 220, padding = 24) {
  if (!points.length) {
    return "";
  }

  const max = Math.max(...points.map((point) => point.clicks), 1);
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;
  const xStep = points.length === 1 ? 0 : chartWidth / (points.length - 1);

  return points
    .map((point, index) => {
      const x = padding + index * xStep;
      const y = height - padding - (point.clicks / max) * chartHeight;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export const CAP_WARNING_RATIO = 0.8;

export function getCapWarning(link) {
  if (!link || !link.click_limit) {
    return null;
  }
  const ratio = Number(link.clicks || 0) / Number(link.click_limit);
  if (!Number.isFinite(ratio)) {
    return null;
  }
  if (ratio >= 1) {
    return { tone: "danger", label: "Cap reached" };
  }
  if (ratio >= CAP_WARNING_RATIO) {
    return { tone: "warning", label: `${Math.round(ratio * 100)}% of cap` };
  }
  return null;
}

export function hasAnalyticsData(data) {
  return Boolean(
    data &&
      (data.summary?.total_clicks > 0 ||
        data.summary?.active_links > 0 ||
        data.clicks_over_time?.length ||
        data.device_breakdown?.length ||
        data.browser_breakdown?.length ||
        data.top_links?.length),
  );
}

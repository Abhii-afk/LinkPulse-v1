import { formatMetric } from "./analyticsModel.js";

export default function MetricCard({ label, value, detail, accent = "default" }) {
  return (
    <article className={`metric-card metric-card-${accent}`}>
      <div className="metric-card-topline">
        <span>{label}</span>
        <span className="metric-card-glyph" aria-hidden="true" />
      </div>
      <strong>{formatMetric(value)}</strong>
      <small>{detail}</small>
    </article>
  );
}

import { formatMetric, formatPercentage } from "./analyticsModel.js";

export default function BreakdownChart({ title, kicker, items = [], emptyMessage = "No breakdown data yet." }) {
  return (
    <section className="dashboard-card breakdown-card" aria-labelledby={`${title.toLowerCase().replaceAll(" ", "-")}-heading`}>
      <div className="card-heading">
        <div>
          <p className="section-kicker">{kicker}</p>
          <h2 id={`${title.toLowerCase().replaceAll(" ", "-")}-heading`}>{title}</h2>
        </div>
      </div>
      {items.length ? (
        <ul className="breakdown-list">
          {items.map((item) => (
            <li key={item.value}>
              <div className="breakdown-label">
                <strong>{item.value}</strong>
                <span>{formatMetric(item.clicks)} · {formatPercentage(item.percentage)}</span>
              </div>
              <div className="breakdown-track" aria-hidden="true">
                <span style={{ width: `${Math.min(Math.max(Number(item.percentage) || 0, 0), 100)}%` }} />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="chart-empty">{emptyMessage}</div>
      )}
    </section>
  );
}

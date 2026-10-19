import { getLinePoints, getTrafficPoints } from "./analyticsModel.js";

function formatBucket(bucket) {
  const date = new Date(bucket);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
}

export default function TrafficChart({ data }) {
  const points = getTrafficPoints(data);

  if (!points.length) {
    return (
      <section className="dashboard-card traffic-card" aria-labelledby="traffic-heading">
        <div className="card-heading">
          <div>
            <p className="section-kicker">Traffic velocity</p>
            <h2 id="traffic-heading">Clicks over time</h2>
          </div>
        </div>
        <div className="chart-empty">No click events in this range yet.</div>
      </section>
    );
  }

  const width = 640;
  const height = 220;
  const linePoints = getLinePoints(points, width, height);
  const areaPoints = `24,196 ${linePoints} 616,196`;
  const maxClicks = Math.max(...points.map((point) => point.clicks), 1);

  return (
    <section className="dashboard-card traffic-card" aria-labelledby="traffic-heading">
      <div className="card-heading">
        <div>
          <p className="section-kicker">Traffic velocity</p>
          <h2 id="traffic-heading">Clicks over time</h2>
        </div>
        <span className="chart-legend"><i /> Total clicks</span>
      </div>
      <div className="traffic-chart-wrap">
        <svg className="traffic-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Clicks over time line chart">
          <defs>
            <linearGradient id="traffic-area" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#7dd3fc" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#7dd3fc" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0, 1, 2, 3].map((line) => {
            const y = 24 + line * 57.3;
            return <line key={line} x1="24" x2="616" y1={y} y2={y} className="chart-grid-line" />;
          })}
          <polygon points={areaPoints} fill="url(#traffic-area)" />
          <polyline points={linePoints} className="traffic-line" fill="none" />
          {points.map((point, index) => {
            const coordinates = linePoints.split(" ")[index].split(",");
            return <circle key={`${point.bucket}-${index}`} cx={coordinates[0]} cy={coordinates[1]} r="3.5" className="traffic-point" />;
          })}
        </svg>
        <div className="chart-axis chart-axis-labels">
          <span>{formatBucket(points[0].bucket)}</span>
          <span>{formatBucket(points[points.length - 1].bucket)}</span>
        </div>
        <div className="chart-max-label">{maxClicks.toLocaleString()} peak</div>
      </div>
    </section>
  );
}

import {
  formatMetric,
  getLinkStatus,
  getManagedLinks,
  getStatusLabel,
  getStatusTone,
} from "./analyticsModel.js";

export function getClickCap(link) {
  if (link.click_limit === null || link.click_limit === undefined) {
    return "Not reported";
  }
  return `${formatMetric(link.clicks)} / ${formatMetric(link.click_limit)}`;
}

export function getManagedLinkRows(data) {
  return getManagedLinks(data).map((link) => {
    const status = getLinkStatus(link);
    return {
      ...link,
      status,
      statusLabel: getStatusLabel(status),
      statusTone: getStatusTone(status),
      clickCap: getClickCap(link),
      historical: status === "disabled" || status === "expired" || status === "abusive",
    };
  });
}

export default function ManagedLinksTable({ data }) {
  const links = getManagedLinkRows(data);

  return (
    <section className="dashboard-card managed-links-card" aria-labelledby="managed-links-heading">
      <div className="card-heading managed-links-heading">
        <div>
          <p className="section-kicker">Top-performing links</p>
          <h2 id="managed-links-heading">Managed links</h2>
        </div>
        <span className="table-caption">{links.length ? `${links.length} with recorded traffic` : "No recorded traffic"}</span>
      </div>
      {links.length ? (
        <div className="table-scroll">
          <table className="managed-links-table">
            <thead>
              <tr>
                <th scope="col">Short code</th>
                <th scope="col">Clicks / cap</th>
                <th scope="col">Status</th>
                <th scope="col">History</th>
              </tr>
            </thead>
            <tbody>
              {links.map((link) => {
                return (
                  <tr key={link.link_id || link.short_code}>
                    <td>
                      <strong>/{link.short_code}</strong>
                      {link.destination_url && <small>{link.destination_url}</small>}
                    </td>
                    <td>{link.clickCap}</td>
                    <td>
                      <span className={`status-pill status-pill-${link.statusTone}`}>
                        <i aria-hidden="true" /> {link.statusLabel}
                      </span>
                    </td>
                    <td>
                      <span className={link.historical ? "history-available" : "history-standard"}>
                        {link.historical ? "Historical data" : "Live"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="table-empty">
          Links with recorded clicks will appear here. Historical events are retained when a link is disabled or expired.
        </div>
      )}
    </section>
  );
}

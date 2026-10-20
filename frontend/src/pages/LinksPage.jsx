import { useCallback, useEffect, useState } from "react";

import DashboardState from "../components/analytics/DashboardState.jsx";
import { ApiError } from "../api/client.js";
import { createLink, fetchQrCode, listLinks } from "../api/links.js";
import CreationWizard from "../components/wizard/CreationWizard.jsx";
import { getLinkStatus, getStatusLabel, getStatusTone } from "../components/analytics/analyticsModel.js";

function getCapWarning(link) {
  if (!link.click_limit) {
    return null;
  }
  const ratio = link.total_clicks / link.click_limit;
  if (ratio >= 1) {
    return { tone: "danger", label: "Cap reached" };
  }
  if (ratio >= 0.8) {
    return { tone: "warning", label: `${Math.round(ratio * 100)}% of cap` };
  }
  return null;
}

function QrCodePanel({ link, accessToken, onClose }) {
  const [imageUrl, setImageUrl] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let revoked = null;
    let cancelled = false;

    fetchQrCode(link.short_code, { accessToken })
      .then((blob) => {
        if (cancelled) {
          return;
        }
        revoked = URL.createObjectURL(blob);
        setImageUrl(revoked);
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(requestError instanceof ApiError ? requestError.message : "The QR code could not be loaded.");
        }
      });

    return () => {
      cancelled = true;
      if (revoked) {
        URL.revokeObjectURL(revoked);
      }
    };
  }, [link.short_code, accessToken]);

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="wizard-modal qr-modal" role="dialog" aria-modal="true" aria-labelledby="qr-title">
        <div className="wizard-modal-header">
          <div>
            <p className="eyebrow">QR code</p>
            <h1 id="qr-title">/{link.short_code}</h1>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close QR code">
            ×
          </button>
        </div>

        {error && (
          <div className="server-error" role="alert">
            <strong>The QR code is not available.</strong>
            <span>{error}</span>
          </div>
        )}

        {imageUrl && (
          <div className="qr-body">
            <img className="qr-image" src={imageUrl} alt={`QR code for /${link.short_code}`} />
            <p className="qr-hint">
              A scan of this code is recorded as a normal visit, so it shows up in the same
              analytics as a click.
            </p>
            <a className="button button-primary" href={imageUrl} download={`link-${link.short_code}.png`}>
              Download PNG
            </a>
          </div>
        )}
      </section>
    </div>
  );
}

export default function LinksPage({
  accessToken = null,
  campaigns = [],
  onWorkspaceChange = null,
}) {
  const [links, setLinks] = useState([]);
  const [status, setStatus] = useState(accessToken ? "loading" : "permission");
  const [error, setError] = useState(null);
  const [isWizardOpen, setWizardOpen] = useState(false);
  const [createdLink, setCreatedLink] = useState(null);
  const [qrLink, setQrLink] = useState(null);

  const load = useCallback(async () => {
    if (!accessToken) {
      setStatus("permission");
      return;
    }
    setStatus((previous) => (previous === "ready" ? "ready" : "loading"));
    try {
      const data = await listLinks({ accessToken });
      setLinks(Array.isArray(data) ? data : []);
      setStatus("ready");
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "The links could not be loaded.",
      );
      setStatus("error");
    }
  }, [accessToken]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreated = (link) => {
    setCreatedLink(link);
    load();
    if (typeof onWorkspaceChange === "function") {
      onWorkspaceChange();
    }
  };

  if (status === "permission") {
    return (
      <DashboardState
        type="permission"
        title="Sign in to manage your links"
        message="Your links, their QR codes and their click history live behind your account."
      />
    );
  }

  return (
    <main className="workspace-main">
      <section className="workspace-hero">
        <div>
          <p className="section-kicker">Your links</p>
          <h1>Everything you have published.</h1>
          <p className="hero-copy">
            Open a link to see its QR code, check its rules and keep an eye on how close it is
            to its click cap.
          </p>
        </div>
        <button className="button button-primary button-large" type="button" onClick={() => setWizardOpen(true)}>
          <span aria-hidden="true">＋</span> Create new link
        </button>
      </section>

      {status === "loading" && (
        <DashboardState type="loading" title="Loading your links" message="Fetching the links you own…" />
      )}

      {status === "error" && (
        <DashboardState
          type="error"
          title="Your links could not be loaded"
          message={error}
          onRetry={load}
        />
      )}

      {status === "ready" && (
        <section className="dashboard-card links-card" aria-labelledby="links-heading">
          <div className="card-heading managed-links-heading">
            <div>
              <p className="section-kicker">Published</p>
              <h2 id="links-heading">Your links</h2>
            </div>
            <span className="table-caption">
              {links.length ? `${links.length} link${links.length === 1 ? "" : "s"}` : "No links yet"}
            </span>
          </div>

          {links.length ? (
            <div className="table-scroll">
              <table className="managed-links-table">
                <thead>
                  <tr>
                    <th scope="col">Short code</th>
                    <th scope="col">Campaign</th>
                    <th scope="col">Clicks / cap</th>
                    <th scope="col">Status</th>
                    <th scope="col">QR</th>
                  </tr>
                </thead>
                <tbody>
                  {links.map((link) => {
                    const statusValue = getLinkStatus(link);
                    const warning = getCapWarning(link);
                    return (
                      <tr key={link.id || link.short_code}>
                        <td>
                          <strong>/{link.short_code}</strong>
                          {link.destination_url && <small>{link.destination_url}</small>}
                        </td>
                        <td>{link.campaign_name || "—"}</td>
                        <td>
                          {link.click_limit ? (
                            <>
                              {link.total_clicks} / {link.click_limit}
                              {warning && (
                                <span className={`cap-warning cap-warning-${warning.tone}`}>
                                  {warning.label}
                                </span>
                              )}
                            </>
                          ) : (
                            `${link.total_clicks} / no cap`
                          )}
                        </td>
                        <td>
                          <span className={`status-pill status-pill-${getStatusTone(statusValue)}`}>
                            <i aria-hidden="true" /> {getStatusLabel(statusValue)}
                          </span>
                        </td>
                        <td>
                          <button
                            className="button button-ghost"
                            type="button"
                            onClick={() => setQrLink(link)}
                          >
                            Show QR
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="table-empty">
              You have not published a link yet. Create one to get a short link and a QR code.
            </div>
          )}
        </section>
      )}

      {createdLink && (
        <section className="creation-toast" role="status">
          <div>
            <span className="toast-label">Link created</span>
            <a href={createdLink.short_url} target="_blank" rel="noreferrer">
              {createdLink.short_url}
            </a>
          </div>
          <button className="text-button" type="button" onClick={() => setCreatedLink(null)}>
            Dismiss
          </button>
        </section>
      )}

      {qrLink && (
        <QrCodePanel link={qrLink} accessToken={accessToken} onClose={() => setQrLink(null)} />
      )}

      <CreationWizard
        isOpen={isWizardOpen}
        accessToken={accessToken}
        campaigns={campaigns}
        onClose={() => setWizardOpen(false)}
        onCreated={handleCreated}
      />
    </main>
  );
}

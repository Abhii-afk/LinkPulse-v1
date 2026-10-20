import { useState } from "react";

import AnalyticsDashboard from "../components/analytics/AnalyticsDashboard.jsx";
import SessionPanel from "../components/SessionPanel.jsx";
import CreationWizard from "../components/wizard/CreationWizard.jsx";

export default function LinksPage({
  accessToken = null,
  userRole = null,
  onSignIn = null,
  onSignOut = null,
}) {
  const [isWizardOpen, setWizardOpen] = useState(false);
  const [createdLink, setCreatedLink] = useState(null);
  const [selectedRange, setSelectedRange] = useState("30d");
  const [refreshSignal, setRefreshSignal] = useState(0);

  const handleCreated = (link) => {
    setCreatedLink(link);
    setRefreshSignal((value) => value + 1);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            ↗
          </div>
          <div>
            <p className="eyebrow">LinkPulse</p>
            <span className="brand-subtitle">Link workspace</span>
          </div>
        </div>
        <div className="session-area">
          <div
            className="session-state"
            title={accessToken ? "Authenticated session" : "No authenticated session"}
          >
            <span className={`session-dot${accessToken ? " is-authenticated" : ""}`} aria-hidden="true" />
            {accessToken ? `Signed in as ${userRole || "member"}` : "Sign in to publish"}
          </div>
          <SessionPanel
            accessToken={accessToken}
            userRole={userRole}
            onSignIn={onSignIn}
            onSignOut={onSignOut}
          />
        </div>
      </header>

      <section className="workspace-hero">
        <div>
          <p className="section-kicker">Workspace overview</p>
          <h1>See what your links are doing.</h1>
          <p className="hero-copy">
            Track real traffic, understand your audience, and keep historical performance visible when links change status.
          </p>
        </div>
        <button className="button button-primary button-large" type="button" onClick={() => setWizardOpen(true)}>
          <span aria-hidden="true">＋</span> Create new link
        </button>
      </section>

      <AnalyticsDashboard
        accessToken={accessToken}
        isAdmin={userRole === "admin"}
        selectedRange={selectedRange}
        onRangeChange={setSelectedRange}
        refreshSignal={refreshSignal}
      />

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

      <CreationWizard
        isOpen={isWizardOpen}
        accessToken={accessToken}
        onClose={() => setWizardOpen(false)}
        onCreated={handleCreated}
      />
    </main>
  );
}

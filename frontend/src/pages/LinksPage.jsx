import { useState } from "react";

import CreationWizard from "../components/wizard/CreationWizard.jsx";

export default function LinksPage({ accessToken = null }) {
  const [isWizardOpen, setWizardOpen] = useState(false);
  const [createdLink, setCreatedLink] = useState(null);

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
        <div className="session-state" title={accessToken ? "Authenticated session" : "No authenticated session"}>
          <span className={`session-dot${accessToken ? " is-authenticated" : ""}`} aria-hidden="true" />
          {accessToken ? "Ready to publish" : "Sign in to publish"}
        </div>
      </header>

      <section className="workspace-hero">
        <div>
          <p className="section-kicker">Link management</p>
          <h1>Build links that move people forward.</h1>
          <p className="hero-copy">
            Create a clean short URL, add the rules you need, and keep the destination under your control.
          </p>
        </div>
        <button className="button button-primary button-large" type="button" onClick={() => setWizardOpen(true)}>
          <span aria-hidden="true">＋</span> Create new link
        </button>
      </section>

      <section className="empty-workspace" aria-labelledby="empty-workspace-heading">
        <div className="empty-illustration" aria-hidden="true">
          <span>↗</span>
          <span>•••</span>
          <span>↘</span>
        </div>
        <p className="section-kicker">Your links</p>
        <h2 id="empty-workspace-heading">Nothing here yet</h2>
        <p>Create your first short link to start building your workspace. Analytics and link history will appear after traffic arrives.</p>
        <button className="button button-secondary" type="button" onClick={() => setWizardOpen(true)}>
          Start with a link
        </button>
      </section>

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
        onCreated={setCreatedLink}
      />
    </main>
  );
}

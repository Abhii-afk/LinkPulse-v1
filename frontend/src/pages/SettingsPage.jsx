import DashboardState from "../components/analytics/DashboardState.jsx";

export default function SettingsPage({
  accessToken = null,
  userRole = null,
  userEmail = null,
  onSignOut = null,
}) {
  if (!accessToken) {
    return (
      <DashboardState
        type="permission"
        title="Sign in to see your account"
        message="Your workspace settings are tied to your account."
      />
    );
  }

  return (
    <main className="workspace-main">
      <section className="workspace-hero">
        <div>
          <p className="section-kicker">Settings</p>
          <h1>Your account and your session.</h1>
          <p className="hero-copy">
            The access token is kept in memory only. It is never written to storage, so
            reloading the page signs you out.
          </p>
        </div>
      </section>

      <section className="dashboard-card import-card" aria-labelledby="account-heading">
        <div className="card-heading managed-links-heading">
          <div>
            <p className="section-kicker">Account</p>
            <h2 id="account-heading">Signed in</h2>
          </div>
        </div>

        <dl className="settings-list">
          <div>
            <dt>Email</dt>
            <dd>{userEmail || "Not reported by the session"}</dd>
          </div>
          <div>
            <dt>Role</dt>
            <dd>{userRole || "user"}</dd>
          </div>
          <div>
            <dt>Token storage</dt>
            <dd>In memory only, never persisted</dd>
          </div>
        </dl>

        <div className="wizard-actions wizard-actions-between">
          <span />
          <button className="button button-ghost" type="button" onClick={() => onSignOut?.()}>
            Sign out
          </button>
        </div>
      </section>
    </main>
  );
}

import AnalyticsPage from "../pages/AnalyticsPage.jsx";
import CampaignsPage from "../pages/CampaignsPage.jsx";
import ImportPage from "../pages/ImportPage.jsx";
import LinksPage from "../pages/LinksPage.jsx";
import SettingsPage from "../pages/SettingsPage.jsx";
import SessionPanel from "../components/SessionPanel.jsx";
import { ROUTES } from "./useRoute.js";

/**
 * The application shell.
 *
 * It owns the navigation between the views and renders the active one. The
 * session and the current route are handed in as properties so this
 * component stays free of state and can be rendered in a test.
 */
export default function AppShell({
  accessToken = null,
  userRole = null,
  userEmail = null,
  onSignIn = null,
  onSignOut = null,
  route = "links",
  navigate = null,
  campaigns = [],
  onWorkspaceChange = null,
}) {
  const go = (next) => {
    if (typeof navigate === "function") {
      navigate(next);
    }
  };

  return (
    <div className="app-shell">
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

        <nav className="app-nav" aria-label="Workspace sections">
          {ROUTES.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`app-nav-item${route === item.id ? " is-active" : ""}`}
              aria-current={route === item.id ? "page" : undefined}
              onClick={() => go(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

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

      {route === "links" && (
        <LinksPage
          accessToken={accessToken}
          campaigns={campaigns}
          onWorkspaceChange={onWorkspaceChange}
        />
      )}
      {route === "campaigns" && (
        <CampaignsPage
          accessToken={accessToken}
          onWorkspaceChange={onWorkspaceChange}
        />
      )}
      {route === "import" && <ImportPage accessToken={accessToken} />}
      {route === "analytics" && (
        <AnalyticsPage accessToken={accessToken} isAdmin={userRole === "admin"} />
      )}
      {route === "settings" && (
        <SettingsPage
          accessToken={accessToken}
          userRole={userRole}
          userEmail={userEmail}
          onSignOut={onSignOut}
        />
      )}
    </div>
  );
}

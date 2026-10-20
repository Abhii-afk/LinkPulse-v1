import AppShell from "./app/AppShell.jsx";

export default function App({
  accessToken = null,
  userRole = null,
  userEmail = null,
  onSignIn = null,
  onSignOut = null,
  route = "links",
  navigate = null,
  campaigns = [],
  onWorkspaceChange = null,
} = {}) {
  return (
    <AppShell
      accessToken={accessToken}
      userRole={userRole}
      userEmail={userEmail}
      onSignIn={onSignIn}
      onSignOut={onSignOut}
      route={route}
      navigate={navigate}
      campaigns={campaigns}
      onWorkspaceChange={onWorkspaceChange}
    />
  );
}

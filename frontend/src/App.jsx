import LinksPage from "./pages/LinksPage.jsx";

export default function App({
  accessToken = null,
  userRole = null,
  onSignIn = null,
  onSignOut = null,
} = {}) {
  return (
    <LinksPage
      accessToken={accessToken}
      userRole={userRole}
      onSignIn={onSignIn}
      onSignOut={onSignOut}
    />
  );
}

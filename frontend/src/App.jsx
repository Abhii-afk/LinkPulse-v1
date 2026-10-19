import LinksPage from "./pages/LinksPage.jsx";

export default function App({ accessToken = null, userRole = null } = {}) {
  return <LinksPage accessToken={accessToken} userRole={userRole} />;
}

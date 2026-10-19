import LinksPage from "./pages/LinksPage.jsx";

export default function App({ accessToken = null } = {}) {
  return <LinksPage accessToken={accessToken} />;
}

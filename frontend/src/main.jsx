import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import { signIn } from "./api/auth.js";
import { listCampaigns } from "./api/campaigns.js";
import { useRoute } from "./app/useRoute.js";
import "./index.css";

function Root() {
  // The access token is kept in memory only. It is never written to
  // localStorage or a cookie, so a reload signs the visitor out again.
  const [session, setSession] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const { route, navigate } = useRoute();

  const loadCampaigns = useCallback(async () => {
    if (!session?.accessToken) {
      setCampaigns([]);
      return;
    }
    try {
      const data = await listCampaigns({ accessToken: session.accessToken });
      setCampaigns(Array.isArray(data) ? data : []);
    } catch {
      setCampaigns([]);
    }
  }, [session?.accessToken]);

  useEffect(() => {
    loadCampaigns();
  }, [loadCampaigns]);

  const handleSignIn = async (email, password) => {
    const next = await signIn({ email, password });
    setSession(next);
  };

  const handleSignOut = () => {
    setSession(null);
    setCampaigns([]);
  };

  return (
    <App
      accessToken={session?.accessToken ?? null}
      userRole={session?.role ?? null}
      userEmail={session?.email ?? null}
      onSignIn={handleSignIn}
      onSignOut={handleSignOut}
      route={route}
      navigate={navigate}
      campaigns={campaigns}
      onWorkspaceChange={loadCampaigns}
    />
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);

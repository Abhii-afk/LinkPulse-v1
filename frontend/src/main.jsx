import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import { signIn } from "./api/auth.js";
import "./index.css";

function Root() {
  // The access token is kept in memory only. It is never written to
  // localStorage or a cookie, so a reload signs the visitor out again.
  const [session, setSession] = useState(null);

  const handleSignIn = async (email, password) => {
    const next = await signIn({ email, password });
    setSession(next);
  };

  const handleSignOut = () => setSession(null);

  return (
    <App
      accessToken={session?.accessToken ?? null}
      userRole={session?.role ?? null}
      onSignIn={handleSignIn}
      onSignOut={handleSignOut}
    />
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);

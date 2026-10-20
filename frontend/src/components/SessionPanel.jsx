import { useState } from "react";

export default function SessionPanel({ accessToken, userRole, onSignIn, onSignOut }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [isBusy, setIsBusy] = useState(false);

  if (accessToken) {
    return (
      <div className="session-panel">
        <span className="session-state">
          <span className="session-dot is-authenticated" aria-hidden="true" />
          Signed in as {userRole || "member"}
        </span>
        <button className="button button-ghost" type="button" onClick={() => onSignOut?.()}>
          Sign out
        </button>
      </div>
    );
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    try {
      await onSignIn?.(email, password);
      setPassword("");
    } catch (signInError) {
      setError(signInError?.message || "Sign in failed.");
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <form className="session-panel" onSubmit={handleSubmit}>
      <label className="session-field">
        <span className="sr-only">Email address</span>
        <input
          type="email"
          name="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          autoComplete="username"
          required
        />
      </label>
      <label className="session-field">
        <span className="sr-only">Password</span>
        <input
          type="password"
          name="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Password"
          autoComplete="current-password"
          required
        />
      </label>
      <button className="button button-primary" type="submit" disabled={isBusy}>
        {isBusy ? "Signing in…" : "Sign in"}
      </button>
      {error && (
        <span className="session-error" role="alert">
          {error}
        </span>
      )}
    </form>
  );
}

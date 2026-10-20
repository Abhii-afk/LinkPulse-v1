import { useCallback, useEffect, useState } from "react";

import DashboardState from "../components/analytics/DashboardState.jsx";
import { ApiError } from "../api/client.js";
import { importLinksFromCsv } from "../api/links.js";

export default function ImportPage({ accessToken = null }) {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isUploading, setUploading] = useState(false);

  const reset = useCallback(() => {
    setFile(null);
    setResult(null);
    setError(null);
  }, []);

  useEffect(() => {
    if (!accessToken) {
      setError(null);
    }
  }, [accessToken]);

  if (!accessToken) {
    return (
      <DashboardState
        type="permission"
        title="Sign in to import links"
        message="Bulk import writes into your workspace, so it needs an authenticated session."
      />
    );
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!file) {
      setError("Choose a CSV file first.");
      return;
    }

    setUploading(true);
    setError(null);
    try {
      const data = await importLinksFromCsv({ file, accessToken });
      setResult(data);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "The file could not be imported.",
      );
    } finally {
      setUploading(false);
    }
  };

  return (
    <main className="workspace-main">
      <section className="workspace-hero">
        <div>
          <p className="section-kicker">Bulk import</p>
          <h1>Bring a spreadsheet of links with you.</h1>
          <p className="hero-copy">
            Upload a CSV with a <code>destination_url</code> column and an optional{" "}
            <code>custom_alias</code>, <code>click_limit</code>, <code>password</code> or{" "}
            <code>expires_at</code>. Every row is checked on its own, so one bad row never
            stops the rest.
          </p>
        </div>
      </section>

      <section className="dashboard-card import-card" aria-labelledby="import-heading">
        <div className="card-heading managed-links-heading">
          <div>
            <p className="section-kicker">Upload</p>
            <h2 id="import-heading">Import a CSV</h2>
          </div>
        </div>

        <form className="import-form" onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="import-file">
            <span>CSV file</span>
            <input
              id="import-file"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                setFile(event.target.files?.[0] || null);
                setResult(null);
                setError(null);
              }}
            />
          </label>

          <div className="wizard-actions wizard-actions-between">
            <button
              className="button button-ghost"
              type="button"
              onClick={reset}
              disabled={isUploading}
            >
              Clear
            </button>
            <button className="button button-primary" type="submit" disabled={isUploading || !file}>
              {isUploading ? "Importing…" : "Import links"}
            </button>
          </div>
        </form>

        {error && (
          <div className="server-error" role="alert">
            <strong>The import did not run.</strong>
            <span>{error}</span>
          </div>
        )}

        {result && (
          <div className="import-result">
            <p className="import-summary">
              <strong>{result.successful_imports}</strong> of {result.total_processed} rows
              imported, <strong>{result.failed_imports}</strong> rejected.
            </p>

            {result.errors?.length ? (
              <div className="table-scroll">
                <table className="managed-links-table">
                  <thead>
                    <tr>
                      <th scope="col">Row</th>
                      <th scope="col">Problem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.errors.map((item) => (
                      <tr key={`${item.row}-${item.error}`}>
                        <td>{item.row}</td>
                        <td>{item.error}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="import-summary">Every row was imported.</p>
            )}
          </div>
        )}
      </section>
    </main>
  );
}

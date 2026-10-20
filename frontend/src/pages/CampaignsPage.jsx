import { useCallback, useEffect, useState } from "react";

import DashboardState from "../components/analytics/DashboardState.jsx";
import { ApiError } from "../api/client.js";
import { createCampaign, listCampaigns } from "../api/campaigns.js";

export default function CampaignsPage({
  accessToken = null,
  onWorkspaceChange = null,
}) {
  const [campaigns, setCampaigns] = useState([]);
  const [status, setStatus] = useState(accessToken ? "loading" : "permission");
  const [error, setError] = useState(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSaving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!accessToken) {
      setStatus("permission");
      return;
    }
    try {
      const data = await listCampaigns({ accessToken });
      setCampaigns(Array.isArray(data) ? data : []);
      setStatus("ready");
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "The campaigns could not be loaded.",
      );
      setStatus("error");
    }
  }, [accessToken]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createCampaign({ name, description: description || null, accessToken });
      setName("");
      setDescription("");
      await load();
      if (typeof onWorkspaceChange === "function") {
        onWorkspaceChange();
      }
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "The campaign could not be created.",
      );
    } finally {
      setSaving(false);
    }
  };

  if (status === "permission") {
    return (
      <DashboardState
        type="permission"
        title="Sign in to manage campaigns"
        message="Campaigns group your links so you can read their performance together."
      />
    );
  }

  return (
    <main className="workspace-main">
      <section className="workspace-hero">
        <div>
          <p className="section-kicker">Campaigns</p>
          <h1>Group the links that belong together.</h1>
          <p className="hero-copy">
            A campaign is a label you put on a link, for example a launch or a newsletter, so
            you can tell the performance of one push apart from another.
          </p>
        </div>
      </section>

      <section className="dashboard-card import-card" aria-labelledby="campaign-heading">
        <div className="card-heading managed-links-heading">
          <div>
            <p className="section-kicker">New campaign</p>
            <h2 id="campaign-heading">Create a campaign</h2>
          </div>
        </div>

        <form className="import-form" onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="campaign-name">
            <span>Name</span>
            <input
              id="campaign-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Spring Launch"
              required
            />
          </label>

          <label className="field-label" htmlFor="campaign-description">
            <span>Description (optional)</span>
            <input
              id="campaign-description"
              type="text"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Short links for the spring launch"
            />
          </label>

          <div className="wizard-actions wizard-actions-between">
            <span />
            <button
              className="button button-primary"
              type="submit"
              disabled={isSaving || !name.trim()}
            >
              {isSaving ? "Creating…" : "Create campaign"}
            </button>
          </div>
        </form>

        {error && (
          <div className="server-error" role="alert">
            <strong>The campaign was not created.</strong>
            <span>{error}</span>
          </div>
        )}
      </section>

      <section className="dashboard-card import-card" aria-labelledby="campaign-list-heading">
        <div className="card-heading managed-links-heading">
          <div>
            <p className="section-kicker">Existing</p>
            <h2 id="campaign-list-heading">Your campaigns</h2>
          </div>
          <span className="table-caption">
            {campaigns.length ? `${campaigns.length} defined` : "None yet"}
          </span>
        </div>

        {status === "loading" && (
          <DashboardState type="loading" title="Loading campaigns" message="Fetching your campaigns…" />
        )}

        {status === "ready" && (campaigns.length ? (
          <div className="table-scroll">
            <table className="managed-links-table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Description</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((campaign) => (
                  <tr key={campaign.id}>
                    <td>
                      <strong>{campaign.name}</strong>
                    </td>
                    <td>{campaign.description || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="table-empty">
            No campaigns yet. Create one above and it will show up in the link wizard.
          </div>
        ))}
      </section>
    </main>
  );
}

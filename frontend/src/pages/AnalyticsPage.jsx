import { useState } from "react";

import AnalyticsDashboard from "../components/analytics/AnalyticsDashboard.jsx";

export default function AnalyticsPage({ accessToken = null, isAdmin = false }) {
  const [selectedRange, setSelectedRange] = useState("30d");
  const [refreshSignal, setRefreshSignal] = useState(0);

  return (
    <main className="workspace-main">
      <section className="workspace-hero">
        <div>
          <p className="section-kicker">Analytics</p>
          <h1>See what your links are doing.</h1>
          <p className="hero-copy">
            Every visit is written by the background worker, never by the redirect itself, so
            the numbers keep their history when a link changes status.
          </p>
        </div>
      </section>

      <AnalyticsDashboard
        accessToken={accessToken}
        isAdmin={isAdmin}
        selectedRange={selectedRange}
        onRangeChange={setSelectedRange}
        refreshSignal={refreshSignal}
      />
    </main>
  );
}

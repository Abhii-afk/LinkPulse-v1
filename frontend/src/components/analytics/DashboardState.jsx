export default function DashboardState({ type, title, message, onRetry }) {
  const isLoading = type === "loading";
  const isEmpty = type === "empty";

  return (
    <section className={`dashboard-state dashboard-state-${type}`} role={isLoading ? "status" : "region"}>
      <div className="dashboard-state-icon" aria-hidden="true">
        {isLoading ? "…" : isEmpty ? "◌" : "!"}
      </div>
      <h2>{title}</h2>
      <p>{message}</p>
      {onRetry && (
        <button className="button button-secondary" type="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </section>
  );
}

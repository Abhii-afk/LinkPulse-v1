export default function ReviewWarnings({ warnings }) {
  if (warnings.length === 0) {
    return (
      <div className="review-good" role="status">
        <span aria-hidden="true">✓</span>
        <p>Your rules are ready to review.</p>
      </div>
    );
  }

  return (
    <div className="review-warnings" role="note" aria-label="Review warnings">
      <div className="review-warnings-heading">
        <span aria-hidden="true">!</span>
        <strong>Before you publish</strong>
      </div>
      <ul>
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}

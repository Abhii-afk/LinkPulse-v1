import ReviewWarnings from "./ReviewWarnings.jsx";
import { getReviewWarnings } from "./wizardModel.js";

function RuleToggle({ checked, label, description, onChange, children }) {
  return (
    <div className={`rule-card${checked ? " is-enabled" : ""}`}>
      <label className="rule-toggle">
        <input type="checkbox" checked={checked} onChange={onChange} />
        <span className="toggle-track" aria-hidden="true">
          <span className="toggle-thumb" />
        </span>
        <span className="rule-copy">
          <strong>{label}</strong>
          <small>{description}</small>
        </span>
      </label>
      {checked && <div className="rule-control">{children}</div>}
    </div>
  );
}

export default function SecurityRulesStep({ form, fieldErrors, onChange, onBack, onSubmit, isSubmitting }) {
  const warnings = getReviewWarnings(form);

  return (
    <form className="wizard-form" onSubmit={onSubmit} noValidate>
      <div className="wizard-form-heading">
        <p className="section-kicker">Step 2 of 2</p>
        <h2>Protect and review</h2>
        <p>Choose the guardrails for this link. Every option is optional.</p>
      </div>

      <div className="rule-list">
        <RuleToggle
          checked={form.enableExpiration}
          label="Set an expiration"
          description="Stop routing visitors after a specific date and time."
          onChange={() => onChange("enableExpiration", !form.enableExpiration)}
        >
          <label className="field-label" htmlFor="expires-at">
            Expiration date and time
            <input
              id="expires-at"
              name="expiresAt"
              type="datetime-local"
              value={form.expiresAt}
              onChange={onChange}
              aria-invalid={Boolean(fieldErrors.expiresAt)}
            />
            {fieldErrors.expiresAt && (
              <span className="field-error" role="alert">
                {fieldErrors.expiresAt}
              </span>
            )}
          </label>
        </RuleToggle>

        <RuleToggle
          checked={form.enableClickLimit}
          label="Limit total clicks"
          description="Close the link automatically when it reaches a cap."
          onChange={() => onChange("enableClickLimit", !form.enableClickLimit)}
        >
          <label className="field-label" htmlFor="click-limit">
            Maximum clicks
            <input
              id="click-limit"
              name="clickLimit"
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              value={form.clickLimit}
              onChange={onChange}
              placeholder="1000"
              aria-invalid={Boolean(fieldErrors.clickLimit)}
            />
            {fieldErrors.clickLimit && (
              <span className="field-error" role="alert">
                {fieldErrors.clickLimit}
              </span>
            )}
          </label>
        </RuleToggle>

        <RuleToggle
          checked={form.enablePassword}
          label="Require a password"
          description="Ask visitors for a password before redirecting."
          onChange={() => onChange("enablePassword", !form.enablePassword)}
        >
          <label className="field-label" htmlFor="link-password">
            Link password
            <input
              id="link-password"
              name="password"
              type="password"
              value={form.password}
              onChange={onChange}
              minLength={8}
              maxLength={256}
              autoComplete="new-password"
              placeholder="At least 8 characters"
              aria-invalid={Boolean(fieldErrors.password)}
            />
            {fieldErrors.password && (
              <span className="field-error" role="alert">
                {fieldErrors.password}
              </span>
            )}
            <span className="field-hint">The backend hashes this password before it is stored.</span>
          </label>
        </RuleToggle>
      </div>

      <section className="review-panel" aria-labelledby="review-heading">
        <div className="review-heading-row">
          <div>
            <p className="section-kicker">Review</p>
            <h3 id="review-heading">Ready to create?</h3>
          </div>
          <span className="review-step">Final check</span>
        </div>
        <dl className="review-details">
          <div>
            <dt>Destination</dt>
            <dd title={form.destinationUrl}>{form.destinationUrl}</dd>
          </div>
          <div>
            <dt>Alias</dt>
            <dd>{form.customAlias ? `/${form.customAlias}` : "Generated automatically"}</dd>
          </div>
          <div>
            <dt>Rules</dt>
            <dd>
              {[form.enableExpiration && "Expires", form.enableClickLimit && "Click cap", form.enablePassword && "Password protected"]
                .filter(Boolean)
                .join(" · ") || "No extra rules"}
            </dd>
          </div>
        </dl>
        <ReviewWarnings warnings={warnings} />
      </section>

      <div className="wizard-actions wizard-actions-between">
        <button className="button button-ghost" type="button" onClick={onBack}>
          <span aria-hidden="true">←</span> Back
        </button>
        <button className="button button-primary" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : "Create link"} {!isSubmitting && <span aria-hidden="true">↗</span>}
        </button>
      </div>
    </form>
  );
}

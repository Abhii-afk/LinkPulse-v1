import { getAliasFeedback } from "../../api/links.js";

export default function TargetAliasStep({
  form,
  fieldErrors,
  aliasTaken,
  campaigns = [],
  onChange,
  onNext,
}) {
  const aliasFeedback = getAliasFeedback(form.customAlias, { aliasTaken });

  return (
    <form className="wizard-form" onSubmit={onNext} noValidate>
      <div className="wizard-form-heading">
        <p className="section-kicker">Step 1 of 2</p>
        <h2>Set your destination</h2>
        <p>Start with the URL your audience should reach and an optional memorable alias.</p>
      </div>

      <label className="field-label" htmlFor="destination-url">
        Destination URL <span className="required-mark">*</span>
        <input
          id="destination-url"
          name="destinationUrl"
          type="url"
          value={form.destinationUrl}
          onChange={onChange}
          placeholder="https://store.example.com/summer-launch"
          autoComplete="url"
          aria-invalid={Boolean(fieldErrors.destinationUrl)}
          aria-describedby={fieldErrors.destinationUrl ? "destination-url-error" : undefined}
        />
        {fieldErrors.destinationUrl && (
          <span className="field-error" id="destination-url-error" role="alert">
            {fieldErrors.destinationUrl}
          </span>
        )}
      </label>

      <label className="field-label" htmlFor="custom-alias">
        Custom alias <span className="optional-mark">Optional</span>
        <div className="alias-input-wrap">
          <span className="alias-prefix" aria-hidden="true">
            /
          </span>
          <input
            id="custom-alias"
            name="customAlias"
            type="text"
            value={form.customAlias}
            onChange={onChange}
            placeholder="summer-deal"
            autoComplete="off"
            maxLength={100}
            aria-invalid={Boolean(fieldErrors.customAlias)}
            aria-describedby="alias-feedback"
          />
        </div>
        <span className={`field-hint alias-feedback is-${aliasFeedback.tone}`} id="alias-feedback">
          {aliasFeedback.message}
        </span>
        {fieldErrors.customAlias && (
          <span className="field-error" role="alert">
            {fieldErrors.customAlias}
          </span>
        )}
      </label>

      <label className="field-label" htmlFor="campaign-id">
        Campaign <span className="optional-mark">Optional</span>
        <select
          id="campaign-id"
          name="campaignId"
          value={form.campaignId || ""}
          onChange={onChange}
        >
          <option value="">No campaign</option>
          {campaigns.map((campaign) => (
            <option key={campaign.id} value={campaign.id}>
              {campaign.name}
            </option>
          ))}
        </select>
        <span className="field-hint">
          {campaigns.length
            ? "Group this link with the rest of a campaign."
            : "Create a campaign first if you want to group links together."}
        </span>
      </label>

      <div className="wizard-note" role="note">
        <span className="note-mark" aria-hidden="true">
          i
        </span>
        <p>Aliases are checked against the live service when you create the link. A conflict will never overwrite an existing link.</p>
      </div>

      <div className="wizard-actions wizard-actions-end">
        <button className="button button-primary" type="submit">
          Continue to rules <span aria-hidden="true">→</span>
        </button>
      </div>
    </form>
  );
}

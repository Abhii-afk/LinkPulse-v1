import { useEffect, useReducer } from "react";

import { ApiError } from "../../api/client.js";
import { buildCreateLinkPayload, createLink, validateStepOne, validateStepTwo } from "../../api/links.js";
import SecurityRulesStep from "./SecurityRulesStep.jsx";
import StepIndicator from "./StepIndicator.jsx";
import TargetAliasStep from "./TargetAliasStep.jsx";
import { INITIAL_WIZARD_STATE, wizardReducer } from "./wizardModel.js";

function getUserFacingError(error) {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "Your session is missing or expired. Sign in again before creating a link.";
    }
    if (error.status === 403) {
      return "Your account does not have permission to create links.";
    }
    if (error.status === 409) {
      return "This alias is already in use. Go back and choose another one.";
    }
    if (error.status === 422) {
      return error.message || "Review the highlighted fields and try again.";
    }
    if (error.status === 503) {
      return "The routing service is temporarily unavailable. Try again in a moment.";
    }
    return error.message;
  }

  return "The link could not be created. Review your details and try again.";
}

function SuccessState({ link, onClose, onReset }) {
  return (
    <div className="wizard-success" role="status">
      <div className="success-icon" aria-hidden="true">
        ✓
      </div>
      <p className="section-kicker">Link published</p>
      <h2>Your short link is ready</h2>
      <p className="success-copy">The backend accepted the link and populated the routing cache.</p>
      <div className="created-link-card">
        <span>Short URL</span>
        <a href={link.short_url} target="_blank" rel="noreferrer">
          {link.short_url}
        </a>
      </div>
      <div className="wizard-actions wizard-actions-between">
        <button className="button button-ghost" type="button" onClick={onReset}>
          Create another
        </button>
        <button className="button button-primary" type="button" onClick={onClose}>
          Done
        </button>
      </div>
    </div>
  );
}

export default function CreationWizard({
  isOpen,
  accessToken = null,
  campaigns = [],
  onClose,
  onCreated,
  createLinkRequest = createLink,
}) {
  const [state, dispatch] = useReducer(wizardReducer, INITIAL_WIZARD_STATE);

  useEffect(() => {
    if (!isOpen) {
      dispatch({ type: "reset" });
    }
  }, [isOpen]);

  if (!isOpen) {
    return null;
  }

  const handleChange = (eventOrField, nextValue) => {
    if (typeof eventOrField === "string") {
      dispatch({ type: "setField", field: eventOrField, value: nextValue });
      return;
    }

    const { name, type, checked, value } = eventOrField.target;
    dispatch({
      type: "setField",
      field: name,
      value: type === "checkbox" ? checked : value,
    });
  };

  const handleNext = (event) => {
    event.preventDefault();
    const errors = validateStepOne(state.form);
    if (Object.keys(errors).length > 0) {
      dispatch({ type: "setErrors", errors });
      return;
    }
    dispatch({ type: "goToStepTwo" });
  };

  const handleBack = () => dispatch({ type: "goToStepOne" });

  const handleSubmit = async (event) => {
    event.preventDefault();
    const errors = validateStepTwo(state.form);
    if (Object.keys(errors).length > 0) {
      dispatch({ type: "setErrors", errors });
      return;
    }

    dispatch({ type: "submitStart" });
    try {
      const link = await createLinkRequest(buildCreateLinkPayload(state.form), { accessToken });
      dispatch({ type: "submitSuccess", link });
      onCreated?.(link);
    } catch (error) {
      dispatch({
        type: "submitError",
        message: getUserFacingError(error),
        status: error instanceof ApiError ? error.status : 0,
      });
    }
  };

  const handleReset = () => dispatch({ type: "reset" });

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="wizard-modal" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
        <div className="wizard-modal-header">
          <div>
            <p className="eyebrow">Link builder</p>
            <h1 id="wizard-title">Create a short link</h1>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close link builder">
            ×
          </button>
        </div>

        {state.createdLink ? (
          <SuccessState link={state.createdLink} onClose={onClose} onReset={handleReset} />
        ) : (
          <>
            <StepIndicator currentStep={state.step} />
            {state.serverError && (
              <div className="server-error" role="alert">
                <strong>Could not create the link.</strong>
                <span>{state.serverError}</span>
              </div>
            )}
            {state.step === 1 ? (
              <TargetAliasStep
                form={state.form}
                fieldErrors={state.fieldErrors}
                aliasTaken={state.aliasTaken}
                campaigns={campaigns}
                onChange={handleChange}
                onNext={handleNext}
              />
            ) : (
              <SecurityRulesStep
                form={state.form}
                fieldErrors={state.fieldErrors}
                onChange={handleChange}
                onBack={handleBack}
                onSubmit={handleSubmit}
                isSubmitting={state.isSubmitting}
              />
            )}
            {state.isSubmitting && (
              <div className="submitting-overlay" role="status" aria-live="polite">
                <span className="spinner" aria-hidden="true" />
                Saving securely…
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

export { getUserFacingError };

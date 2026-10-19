export default function StepIndicator({ currentStep }) {
  return (
    <ol className="wizard-steps" aria-label="Link creation progress">
      <li className={currentStep === 1 ? "wizard-step is-current" : "wizard-step is-complete"}>
        <span className="wizard-step-number">1</span>
        <span>
          <strong>Target &amp; alias</strong>
          <small>Where should it go?</small>
        </span>
      </li>
      <li className={currentStep === 2 ? "wizard-step is-current" : "wizard-step"}>
        <span className="wizard-step-number">2</span>
        <span>
          <strong>Security &amp; rules</strong>
          <small>How should it behave?</small>
        </span>
      </li>
    </ol>
  );
}

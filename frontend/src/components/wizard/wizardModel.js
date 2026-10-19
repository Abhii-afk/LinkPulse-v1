import { getAliasFeedback, validateStepOne, validateStepTwo } from "../../api/links.js";

export const INITIAL_FORM = Object.freeze({
  destinationUrl: "",
  customAlias: "",
  enableExpiration: false,
  expiresAt: "",
  enableClickLimit: false,
  clickLimit: "",
  enablePassword: false,
  password: "",
});

export const INITIAL_WIZARD_STATE = Object.freeze({
  step: 1,
  form: INITIAL_FORM,
  fieldErrors: {},
  serverError: "",
  aliasTaken: false,
  isSubmitting: false,
  createdLink: null,
});

export function getReviewWarnings(form) {
  const warnings = [];

  if (!form.enableExpiration) {
    warnings.push("This link will stay active until you disable it.");
  }
  if (!form.enableClickLimit) {
    warnings.push("No click cap is set, so traffic will not be automatically limited.");
  }

  return warnings;
}

export function wizardReducer(state, action) {
  switch (action.type) {
    case "setField": {
      const fieldErrors = { ...state.fieldErrors };
      delete fieldErrors[action.field];

      return {
        ...state,
        form: { ...state.form, [action.field]: action.value },
        fieldErrors,
        serverError: action.field === "customAlias" ? "" : state.serverError,
        aliasTaken: action.field === "customAlias" ? false : state.aliasTaken,
      };
    }
    case "setErrors":
      return { ...state, fieldErrors: action.errors };
    case "goToStepTwo":
      return { ...state, step: 2, fieldErrors: {}, serverError: "" };
    case "goToStepOne":
      return { ...state, step: 1, fieldErrors: {}, serverError: "" };
    case "submitStart":
      return {
        ...state,
        isSubmitting: true,
        fieldErrors: {},
        serverError: "",
        aliasTaken: false,
      };
    case "submitError":
      return {
        ...state,
        isSubmitting: false,
        serverError: action.message,
        aliasTaken: action.status === 409,
      };
    case "submitSuccess":
      return {
        ...state,
        isSubmitting: false,
        createdLink: action.link,
        serverError: "",
      };
    case "reset":
      return INITIAL_WIZARD_STATE;
    default:
      return state;
  }
}

export { getAliasFeedback, validateStepOne, validateStepTwo };

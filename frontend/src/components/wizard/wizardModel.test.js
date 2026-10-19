import { describe, expect, it } from "vitest";

import {
  INITIAL_WIZARD_STATE,
  getReviewWarnings,
  wizardReducer,
} from "./wizardModel.js";

describe("wizard state", () => {
  it("moves between steps while preserving entered form values", () => {
    const withDestination = wizardReducer(INITIAL_WIZARD_STATE, {
      type: "setField",
      field: "destinationUrl",
      value: "https://example.com",
    });
    const onStepTwo = wizardReducer(withDestination, { type: "goToStepTwo" });
    const backOnStepOne = wizardReducer(onStepTwo, { type: "goToStepOne" });

    expect(onStepTwo.step).toBe(2);
    expect(backOnStepOne.step).toBe(1);
    expect(backOnStepOne.form.destinationUrl).toBe("https://example.com");
  });

  it("tracks loading, server failure, and successful creation states", () => {
    const loading = wizardReducer(INITIAL_WIZARD_STATE, { type: "submitStart" });
    const failed = wizardReducer(loading, {
      type: "submitError",
      status: 409,
      message: "This alias is already in use.",
    });
    const successful = wizardReducer(loading, {
      type: "submitSuccess",
      link: { short_url: "http://testserver/launch" },
    });

    expect(loading.isSubmitting).toBe(true);
    expect(failed).toMatchObject({
      isSubmitting: false,
      serverError: "This alias is already in use.",
      aliasTaken: true,
    });
    expect(successful).toMatchObject({
      isSubmitting: false,
      createdLink: { short_url: "http://testserver/launch" },
      serverError: "",
    });
  });

  it("shows review warnings for intentionally unbounded rules", () => {
    expect(
      getReviewWarnings({ enableExpiration: false, enableClickLimit: false }),
    ).toEqual([
      "This link will stay active until you disable it.",
      "No click cap is set, so traffic will not be automatically limited.",
    ]);
    expect(
      getReviewWarnings({ enableExpiration: true, enableClickLimit: true }),
    ).toEqual([]);
  });
});

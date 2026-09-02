import { describe, expect, it } from "vitest";
import type { AITaskRequest, AITaskResponse } from "../types";
import { withReviewedDraft } from "./AIGenerationPanel";

const preview: AITaskResponse = {
  task: "scene_decomposition",
  applied: false,
  data: {
    scenes: [
      {
        order: 0,
        title: "Reviewed scene",
        purpose: "Test",
        summary: "The exact draft the user reviewed.",
        shots: [],
      },
    ],
  },
  provenance: {
    provider_id: "openai",
    model: "gpt-4.1",
    mock: false,
    prompt_version: "1.0",
    schema_version: "1.0",
    attempts: 1,
    latency_ms: 1,
    usage: {},
    response_id: "response-1",
    generated_at: "2026-09-02T00:00:00Z",
  },
  summary: {},
  warnings: [],
  notes: "",
  preview_revision_id: "preview-1",
  preview_sha256: "a".repeat(64),
  applied_revision_id: "",
  applied_sha256: "",
};

describe("withReviewedDraft", () => {
  it("sends the exact previewed draft when Apply draft is chosen", () => {
    const base: AITaskRequest = {
      provider_id: "openai",
      model: "gpt-4.1",
      guidance: "keep continuity",
      apply: true,
    };
    const request = withReviewedDraft(base, preview);

    expect(request.apply).toBe(true);
    expect(request.draft).toBe(preview.data);
    expect(request.reviewed_preview_id).toBe("preview-1");
    expect(request.reviewed_preview_sha256).toBe("a".repeat(64));
  });

  it("does not attach a draft to a preview request", () => {
    const base: AITaskRequest = {
      provider_id: "openai",
      model: "gpt-4.1",
      guidance: "keep continuity",
      apply: false,
    };
    const request = withReviewedDraft(base, preview);

    expect(request.draft).toBeUndefined();
  });
});

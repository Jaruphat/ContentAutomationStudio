import { describe, expect, it } from "vitest";
import {
  CLIP_FRAME_RATE,
  GPU_SECONDS_PER_FRAME,
  estimateClipMinutes,
  humaniseMinutes,
  pickClipWorkflows,
} from "./MotionPage";
import type { Workflow } from "../types";

/**
 * A page that lets you queue twenty-eight clips without saying that it is
 * three hours of machine is a page that lies by omission, so the estimate is
 * shown before the button is pressed - and it comes from a measurement: a
 * 124-frame clip took 220 to 230 seconds on the workstation this was built on.
 */
describe("clip cost", () => {
  it("is proportional to the frames the length asks for", () => {
    const five = estimateClipMinutes(5);
    const ten = estimateClipMinutes(10);
    expect(ten / five).toBeCloseTo(2, 1);
  });

  it("matches the clip that was actually measured", () => {
    // 124 frames came back in 220-230 seconds, so a clip of that length
    // should be estimated in the same neighbourhood rather than a guess.
    const seconds = estimateClipMinutes(124 / CLIP_FRAME_RATE) * 60;
    expect(seconds).toBeGreaterThan(200);
    expect(seconds).toBeLessThan(250);
    expect(GPU_SECONDS_PER_FRAME).toBeGreaterThan(0);
  });

  it("never estimates a clip at zero", () => {
    expect(estimateClipMinutes(0)).toBeGreaterThan(0);
  });
});

describe("humaniseMinutes", () => {
  it("uses the unit the number is actually in", () => {
    expect(humaniseMinutes(0.5)).toBe("30 s");
    expect(humaniseMinutes(18)).toBe("18 m");
    expect(humaniseMinutes(145)).toBe("2 h 25 m");
    expect(humaniseMinutes(120)).toBe("2 h");
  });
});

describe("pickClipWorkflows", () => {
  const wf = (over: Partial<Workflow>): Workflow =>
    ({
      id: "x", name: "x", purpose: "image-to-video", source_json_path: "",
      source_format: "api", sha256_hash: "", version: "1",
      required_models: [], required_custom_nodes: [],
      parameter_mapping: { referenceImage: { nodeId: "1", field: "image" } },
      output_mapping: [], tested_comfyui_version: "",
      created_at: "", updated_at: "", ...over,
    }) as Workflow;

  it("offers only graphs that can be sent a start frame", () => {
    // A UI export has no parameter mapping, so it cannot be handed the
    // picture: offering it is offering a button that fails.
    const { options } = pickClipWorkflows(
      [
        wf({ id: "api", name: "H3 I2V (API)" }),
        wf({ id: "ui", name: "H3 I2V (UI)", parameter_mapping: {} }),
        wf({ id: "img", name: "Z-Image", purpose: "image" }),
      ],
      "",
    );
    expect(options.map((option) => option.id)).toEqual(["api"]);
  });

  it("starts on a usable graph when the project names no default", () => {
    // "Project default" that resolves to nothing is a first press that could
    // only fail.
    const { selected } = pickClipWorkflows([wf({ id: "api" })], "");
    expect(selected).toBe("api");
  });

  it("keeps the project's own default when it can be used", () => {
    const { selected } = pickClipWorkflows(
      [wf({ id: "a" }), wf({ id: "b" })],
      "b",
    );
    expect(selected).toBe("b");
  });

  it("selects nothing when nothing can run", () => {
    const { options, selected } = pickClipWorkflows(
      [wf({ id: "ui", parameter_mapping: {} })],
      "ui",
    );
    expect(options).toEqual([]);
    expect(selected).toBe("");
  });
});

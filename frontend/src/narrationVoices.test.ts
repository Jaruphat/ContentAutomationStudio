import { describe, expect, it } from "vitest";
import {
  DEFAULT_NARRATION_VOICE,
  NARRATION_VOICES,
  resolveNarrationVoice,
} from "./narrationVoices";

describe("narration voices", () => {
  it("keeps a name the endpoint accepts", () => {
    expect(resolveNarrationVoice("nova")).toBe("nova");
    expect(resolveNarrationVoice("  Coral ")).toBe("coral");
  });

  it("falls back rather than sending a name that would fail the render", () => {
    // A voice is stored as a plain string, so it can arrive from an older
    // project or a renamed provider voice. Failing after the pictures are
    // made is the expensive way to find out.
    expect(resolveNarrationVoice("gandalf")).toBe(DEFAULT_NARRATION_VOICE);
    expect(resolveNarrationVoice("")).toBe(DEFAULT_NARRATION_VOICE);
    expect(resolveNarrationVoice(null)).toBe(DEFAULT_NARRATION_VOICE);
    expect(resolveNarrationVoice(undefined)).toBe(DEFAULT_NARRATION_VOICE);
  });

  it("offers the default among the choices", () => {
    expect(NARRATION_VOICES).toContain(DEFAULT_NARRATION_VOICE);
  });
});

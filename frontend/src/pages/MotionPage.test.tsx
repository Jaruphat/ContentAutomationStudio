import { describe, expect, it } from "vitest";
import {
  CLIP_FRAME_RATE,
  GPU_SECONDS_PER_FRAME,
  estimateClipMinutes,
  humaniseMinutes,
} from "./MotionPage";

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

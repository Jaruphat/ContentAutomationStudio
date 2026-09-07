import { describe, expect, it } from "vitest";
import { parsePlateSize } from "./ReferencePlateGenerator";

/**
 * The size a plate is generated at is not cosmetic: an edit workflow hands
 * every later shot the shape of the image it was given, so a plate accepted at
 * the wrong size silently reshapes the whole film.
 */
describe("parsePlateSize", () => {
  it("reads a delivery resolution", () => {
    expect(parsePlateSize("1024x576")).toEqual({ width: 1024, height: 576 });
  });

  it("accepts the multiplication sign and surrounding space", () => {
    expect(parsePlateSize(" 1080 × 1920 ")).toEqual({ width: 1080, height: 1920 });
  });

  it("refuses a size the sampler would silently round", () => {
    expect(parsePlateSize("1023x577")).toBeNull();
  });

  it("refuses anything that is not two numbers", () => {
    expect(parsePlateSize("")).toBeNull();
    expect(parsePlateSize("1024")).toBeNull();
    expect(parsePlateSize("wide")).toBeNull();
  });
});

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ImagePreview from "./ImagePreview";

/**
 * A character sheet is a standing figure, so it is taller than it is wide.
 * Dropped into a short landscape box with `object-cover`, the crop takes the
 * head - which is the one part of a canonical view anybody is checking.
 */
describe("ImagePreview", () => {
  it("fits the whole picture in the box instead of cropping to fill it", () => {
    const html = renderToStaticMarkup(
      <ImagePreview src="/view.png" alt="Mai full body" />,
    );
    expect(html).toContain("object-contain");
    expect(html).not.toContain("object-cover");
  });

  it("offers a way to see it bigger, since a thumbnail cannot settle a likeness", () => {
    const html = renderToStaticMarkup(
      <ImagePreview src="/view.png" alt="Mai full body" />,
    );
    // Named for the picture, not "Enlarge image": a screen-reader user moving
    // through a gallery of views hears which one each button opens.
    expect(html).toContain("Enlarge Mai full body");
  });

  it("keeps the alt text on the image itself", () => {
    const html = renderToStaticMarkup(
      <ImagePreview src="/view.png" alt="Mai full body" />,
    );
    expect(html).toContain('alt="Mai full body"');
  });
});

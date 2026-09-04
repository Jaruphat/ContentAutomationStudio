import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import CollapsibleSection from "./CollapsibleSection";

/**
 * The authoring panels are tall - a storyboard generator, a prompt compiler, a
 * character set editor and a reference bible stacked on one page - and most of
 * the time only one of them is being used. Folding the rest to their headings
 * gets the work back on screen without hiding that they exist.
 */
describe("CollapsibleSection", () => {
  it("shows its contents when open", () => {
    const html = renderToStaticMarkup(
      <CollapsibleSection id="s" title="Character Set Generator" defaultOpen>
        <p>the body</p>
      </CollapsibleSection>,
    );
    expect(html).toContain("Character Set Generator");
    expect(html).toContain("the body");
    expect(html).toContain('aria-expanded="true"');
  });

  it("keeps the heading visible when folded, so nothing disappears", () => {
    const html = renderToStaticMarkup(
      <CollapsibleSection id="s" title="Character Set Generator" defaultOpen={false}>
        <p>the body</p>
      </CollapsibleSection>,
    );
    expect(html).toContain("Character Set Generator");
    expect(html).not.toContain("the body");
    expect(html).toContain('aria-expanded="false"');
  });

  it("names the section in the toggle, not just an arrow", () => {
    // A row of identical "Toggle" buttons tells a screen-reader user nothing
    // about which panel each one folds.
    const html = renderToStaticMarkup(
      <CollapsibleSection id="s" title="Visual Reference Bible" defaultOpen>
        <p>body</p>
      </CollapsibleSection>,
    );
    expect(html).toContain("Collapse Visual Reference Bible");
  });

  it("can carry a summary that stays readable while folded", () => {
    const html = renderToStaticMarkup(
      <CollapsibleSection id="s" title="Character sets" summary="2 approved" defaultOpen={false}>
        <p>body</p>
      </CollapsibleSection>,
    );
    expect(html).toContain("2 approved");
  });
});

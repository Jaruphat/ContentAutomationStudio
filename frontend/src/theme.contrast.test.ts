/**
 * Muted text has to stay readable in both themes.
 *
 * The cockpit leans on the zinc ramp for hierarchy, and the quietest steps are
 * where that goes wrong: helper lines, provenance and seeds are set in
 * `text-zinc-500` at 10-12px, which is exactly the size where a thin contrast
 * ratio stops being a matter of taste. The ramp is redefined per theme in
 * `index.css`, so a value that reads well in one can fail in the other with
 * nothing in the markup to show it.
 *
 * These read the tokens out of the stylesheet and do the arithmetic, so a
 * future edit to the ramp cannot quietly drop a step below the threshold.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Read off disk rather than imported, so the assertions see the source the
// theme is actually authored in, not whatever the CSS pipeline emits.
const css = readFileSync(join(__dirname, "index.css"), "utf8");

/** Tailwind's own zinc ramp, which the dark theme starts from. */
const TAILWIND_ZINC: Record<string, string> = {
  "zinc-950": "#09090b", "zinc-900": "#18181b", "zinc-800": "#27272a",
  "zinc-700": "#3f3f46", "zinc-600": "#52525b", "zinc-500": "#71717a",
  "zinc-400": "#a1a1aa", "zinc-300": "#d4d4d8", "zinc-200": "#e4e4e7",
  "zinc-100": "#f4f4f5", "zinc-50": "#fafafa",
};

function block(selector: string): string {
  // The selector is named in the file's opening commentary too, so match it
  // only where it actually opens a rule.
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no rule opens with ${selector}`);
  const open = css.indexOf("{", start);
  const close = css.indexOf("\n}", open);
  return css.slice(open, close);
}

function ramp(selector: string, base: Record<string, string>): Record<string, string> {
  const out = { ...base };
  const source = block(selector);
  for (const [, step, value] of source.matchAll(/--color-(zinc-\d+):\s*(#[0-9a-fA-F]{6})/g)) {
    out[step] = value;
  }
  return out;
}

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const linear = channels.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(foreground: string, background: string): number {
  const a = luminance(foreground);
  const b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** Surfaces muted text is actually set on: the rail, the page and panels. */
const SURFACES = ["zinc-950", "zinc-900", "zinc-800"];
/** Steps the components use for text. Below 600 the ramp is lines and fills. */
const TEXT_STEPS = ["zinc-500", "zinc-400", "zinc-300", "zinc-200", "zinc-100"];

describe("theme contrast", () => {
  const themes = {
    dark: ramp(":root", TAILWIND_ZINC),
    light: ramp("html.theme-light", TAILWIND_ZINC),
  };

  for (const [name, palette] of Object.entries(themes)) {
    for (const step of TEXT_STEPS) {
      for (const surface of SURFACES) {
        it(`${name}: text-${step} on ${surface} is legible`, () => {
          const ratio = contrast(palette[step], palette[surface]);
          // 4.5:1 is the normal-text threshold. These steps carry 10-12px
          // helper text, so the large-text allowance does not apply.
          expect(
            ratio,
            `text-${step} on bg-${surface} in ${name} is ${ratio.toFixed(2)}:1`,
          ).toBeGreaterThanOrEqual(4.5);
        });
      }
    }
  }

  it("keeps the ramp ordered, so hierarchy still reads", () => {
    for (const [name, palette] of Object.entries(themes)) {
      const steps = TEXT_STEPS.map((step) => contrast(palette[step], palette["zinc-900"]));
      for (let i = 1; i < steps.length; i += 1) {
        expect(steps[i], `${name}: ${TEXT_STEPS[i]} should stand out more than ${TEXT_STEPS[i - 1]}`)
          .toBeGreaterThan(steps[i - 1]);
      }
    }
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import ExportPage, {
  exportOptions,
  subtitlePresets,
  subtitlePreviewAspect,
} from "./ExportPage";

vi.mock("../store/useProjectStore", () => ({
  useAppState: () => ({ currentProjectId: "project-1" }),
}));

function renderPage(withOverride: boolean) {
  const qc = new QueryClient({
    defaultOptions: { queries: { enabled: false, retry: false } },
  });
  qc.setQueryData(["timeline", "project-1"], {
    project_id: "project-1",
    items: [],
    total_duration_sec: 0,
    item_count: 0,
    warnings: withOverride
      ? [
          {
            code: "e2e_aspect_override",
            message:
              "E2E Override · Aspect mismatch accepted · user-approved test override",
            take_ids: ["take-1", "take-2"],
            waived_from_take_ids: ["source-1", "source-2"],
            waiver_reasons: ["User-approved E2E dimension exception"],
          },
        ]
      : [],
    delivery_validation: {
      pipeline_pass: true,
      delivery_spec_pass: !withOverride,
    },
    coverage: { total_shots: 0, covered_shots: 0, missing: [] },
  });
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <ExportPage />
    </QueryClientProvider>,
  );
}

describe("Export E2E override truthfulness", () => {
  it("warns that current timeline exports do not pass the delivery spec", () => {
    const html = renderPage(true);

    expect(html).toContain(
      "E2E Override · Aspect mismatch accepted · user-approved test override",
    );
    expect(html).toContain("Pipeline pass");
    expect(html).toContain("Delivery spec not passed");
    expect(html).toContain("2 waived takes");
  });

  it("does not show a project-wide override when current artifacts have none", () => {
    const html = renderPage(false);

    expect(html).not.toContain("E2E Override");
    expect(html).not.toContain("Delivery spec not passed");
  });
});

describe("Export failure truthfulness", () => {
  /**
   * A QueryClient whose cached error is not immediately clobbered by a
   * refetch-on-mount, matching the pattern used by TimelinePage's own error
   * tests: `retryOnMount` defaults to true, which would otherwise reset the
   * errored query to "pending" before `renderToStaticMarkup` can see it.
   */
  function erroredQueryClient() {
    return new QueryClient({
      defaultOptions: {
        queries: {
          enabled: false,
          retry: false,
          retryOnMount: false,
          staleTime: Infinity,
        },
      },
    });
  }

  it("reports why the timeline status could not be loaded instead of staying silent", async () => {
    const qc = erroredQueryClient();
    await qc.prefetchQuery({
      queryKey: ["timeline", "project-1"],
      retry: false,
      queryFn: () =>
        Promise.reject({
          isAxiosError: true,
          response: {
            status: 409,
            data: {
              detail:
                "Timeline contains stale or mismatched take lineage in item(s): item-1",
            },
          },
        }),
    });

    const html = renderToStaticMarkup(
      <QueryClientProvider client={qc}>
        <ExportPage />
      </QueryClientProvider>,
    );

    expect(html).toContain("Timeline status unavailable");
    expect(html).toContain("stale or mismatched take lineage");
  });
});

describe("Export labels describe what is actually downloaded", () => {
  const byId = Object.fromEntries(exportOptions.map((opt) => [opt.id, opt]));

  it("does not call the generation manifest a timeline manifest", () => {
    expect(byId.manifest.label).toBe("Generation Manifest");
    expect(byId.manifest.filename("abcdefgh1234")).toBe(
      "generation_manifest_abcdefgh.json",
    );
  });

  it("labels the timeline manifest as the timeline manifest", () => {
    expect(byId.timeline.label).toBe("Timeline Manifest");
    expect(byId.timeline.filename("abcdefgh1234")).toBe(
      "timeline_manifest_abcdefgh.json",
    );
  });

  it("does not promise a ZIP for a JSON metadata archive", () => {
    expect(byId.archive.label).not.toMatch(/ZIP/i);
    expect(byId.archive.description).not.toMatch(/ZIP/i);
    expect(byId.archive.filename("abcdefgh1234")).toMatch(/\.json$/);
  });

  it("renders every option on the page", () => {
    const html = renderPage(false);

    for (const opt of exportOptions) {
      expect(html).toContain(opt.label);
    }
  });
});

describe("Subtitle export controls", () => {
  function renderSubtitles(mode: "off" | "soft" | "burn_in", resolution: string) {
    const qc = new QueryClient({
      defaultOptions: { queries: { enabled: false, retry: false } },
    });
    qc.setQueryData(["subtitle-settings", "project-1"], {
      mode,
      preset: "thai_friendly",
      font_family: "Leelawadee UI",
      font_size: 52,
      text_color: "#FFFFFF",
      outline_color: "#000000",
      shadow_color: "#000000",
      background_color: "#000000",
      bold: false,
      italic: false,
      outline_width: 3,
      shadow_depth: 2,
      background_box: false,
      position: "bottom",
      vertical_margin: 64,
      max_chars_per_line: 36,
    });
    qc.setQueryData(["project", "project-1"], { target_resolution: resolution });
    return renderToStaticMarkup(
      <QueryClientProvider client={qc}>
        <ExportPage />
      </QueryClientProvider>,
    );
  }

  it("offers Off, Soft, Burn-in and every reviewed preset", () => {
    const html = renderSubtitles("soft", "1920x1080");
    expect(html).toContain("Styled subtitles");
    expect(html).toContain("Soft (ASS + SRT)");
    expect(html).toContain("Burn-in");
    expect(html).toContain("Text comes from each Shot dialogue field");
    for (const preset of Object.values(subtitlePresets)) {
      expect(html).toContain(preset.label);
    }
    expect(html).toContain("Segoe UI");
    expect(html).toContain("Leelawadee UI");
    expect(html).toContain("Save settings");
    expect(html).toContain("Export ASS");
    expect(html).toContain("Export SRT");
  });

  it("disables style controls when mode is Off", () => {
    const html = renderSubtitles("off", "1920x1080");
    expect(html).toMatch(/<fieldset[^>]*disabled/);
  });

  it("adapts the visual preview to horizontal and vertical projects", () => {
    expect(subtitlePreviewAspect("1920x1080")).toBe("16 / 9");
    expect(subtitlePreviewAspect("1080x1920")).toBe("9 / 16");
    expect(renderSubtitles("burn_in", "1080x1920")).toContain("aspect-ratio:9 / 16");
  });
});

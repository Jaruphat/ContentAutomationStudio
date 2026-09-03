import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import VisualReferenceBible, {
  imageProvenanceLabel,
  moveReferenceId,
  revisionLabel,
} from "./VisualReferenceBible";
import type { ReferenceSheet } from "../types";

const sheet: ReferenceSheet = {
  id: "sheet-1",
  project_id: "project-1",
  kind: "character",
  name: "Ari",
  subject_ref_id: null,
  canonical_description: "Same face, blue coat, amber accents",
  identity_tokens: "ari, blue coat",
  negative_tokens: "green coat",
  notes: "Keep the scar on the left cheek",
  revision: 3,
  content_sha256: "abc123",
  images: [{
    id: "image-1",
    sheet_id: "sheet-1",
    project_id: "project-1",
    role: "canonical",
    original_filename: "ari.png",
    stored_filename: "image-1.png",
    mime_type: "image/png",
    size_bytes: 1024,
    width: 512,
    height: 512,
    sha256: "image-sha",
    caption: "front view",
    provenance: { source: "upload", original_filename: "ari.png" },
    url: "/api/media/references/image-1/file",
    created_at: "2026-09-02T00:00:00Z",
  }],
  created_at: "2026-09-02T00:00:00Z",
  updated_at: "2026-09-02T00:00:00Z",
};

function renderBible() {
  const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  client.setQueryData(["references", "project-1"], [sheet]);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <VisualReferenceBible projectId="project-1" />
    </QueryClientProvider>,
  );
}

describe("Visual Reference Bible", () => {
  it("renders project-scoped character, recurring prop, and location sheets with canonical truth", () => {
    const html = renderBible();
    expect(html).toContain("Visual Reference Bible");
    expect(html).toContain("Character");
    expect(html).toContain("Recurring prop");
    expect(html).toContain("Location");
    expect(html).toContain("Identity / wardrobe / color description");
    expect(html).toContain("Revision 3");
    expect(html).toContain("Uploaded: ari.png");
    expect(html).toContain("front view");
    expect(html).toContain("Detach image");
  });

  it("reports only provenance supplied by the API", () => {
    expect(imageProvenanceLabel(sheet.images[0])).toBe("Uploaded: ari.png");
    expect(imageProvenanceLabel({ ...sheet.images[0], provenance: {} })).toBe(
      "Source not recorded",
    );
  });

  it("describes stale/current revisions without implying generation happened", () => {
    expect(revisionLabel({ prompt_revision: 4, generated_revision: 2, is_stale: true }))
      .toBe("Stale: generated revision 2; current revision 4");
    expect(revisionLabel({ prompt_revision: 4, generated_revision: 0, is_stale: false }))
      .toBe("Current revision 4; not generated yet");
    expect(revisionLabel({ prompt_revision: 4, generated_revision: 4, is_stale: false }))
      .toBe("Current: generated revision 4");
  });

  it("reorders assigned references while preserving every id", () => {
    expect(moveReferenceId(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(moveReferenceId(["a", "b", "c"], 0, -1)).toEqual(["a", "b", "c"]);
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import CharacterSetGenerator from "./CharacterSetGenerator";
import type { CharacterSet, MediaProviderCatalogue, Workflow } from "../types";

const set: CharacterSet = {
  id: "set-1", project_id: "project-1", character_id: null, reference_sheet_id: "sheet-1",
  name: "Ari", appearance: "freckled face", proportions: "tall", wardrobe: "blue coat",
  palette: "navy, amber", identity_tokens: "left cheek scar", negative_tokens: "green coat",
  notes: "", approved_version_id: "version-1", approved_version_is_current: false,
  created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:00:00Z",
  versions: [{
    id: "version-1", character_set_id: "set-1", project_id: "project-1", version: 1,
    status: "Approved", spec_snapshot: {}, spec_sha256: "spec", content_sha256: "content",
    provider_id: "openai", model: "gpt-image-1", workflow_id: null, seed: 42,
    estimated_cost_usd: 0.12, notes: "", approved_at: "2026-09-04T00:00:00Z",
    created_at: "2026-09-04T00:00:00Z", views: [{
      id: "view-1", version_id: "version-1", character_set_id: "set-1", slot: "front",
      label: "Front", order: 0, view_prompt: "front view", status: "Completed",
      reference_image_id: "image-1", provider_id: "openai", model: "gpt-image-1",
      workflow_id: null, seed: 42, request_params: { size: "1024x1024" },
      provenance: { response_id: "resp-1" }, error_message: "", sha256: "abc123",
      url: "/api/media/references/image-1/file", created_at: "2026-09-04T00:00:00Z",
    }],
  }],
};

const catalogue: MediaProviderCatalogue = {
  video_provider_id: "comfyui",
  default_image_provider_id: "comfyui",
  providers: [
    { id: "comfyui", label: "ComfyUI", configured: true, local: true, mock: false,
      media_types: ["image", "video", "image-to-video"], default_model: "workflow",
      models: [{ id: "workflow", label: "Workflow" }], api_key_env: "", requires_confirmation: false,
      cost_warning: "", sizes: [], qualities: [] },
    { id: "openai", label: "OpenAI Images", configured: true, local: false, mock: false,
      media_types: ["image"], default_model: "gpt-image-1",
      models: [{ id: "gpt-image-1", label: "GPT Image 1" }], api_key_env: "OPENAI_API_KEY",
      requires_confirmation: true, cost_warning: "Metered", sizes: ["1024x1024"], qualities: ["auto"] },
  ],
};

const workflow = (over: Partial<Workflow>): Workflow => ({
  id: "wf", name: "wf", purpose: "image", source_json_path: "wf.json",
  source_format: "api", sha256_hash: "h", version: "1", required_models: [],
  required_custom_nodes: [], parameter_mapping: {}, output_mapping: [],
  tested_comfyui_version: "0.34.0", validation_status: "valid",
  created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:00:00Z", ...over,
});

const workflowList: Workflow[] = [
  workflow({ id: "wf-t2i", name: "Z-Image Turbo T2I",
    parameter_mapping: { positivePrompt: {}, seed: {}, width: {}, height: {} } }),
  workflow({ id: "wf-edit", name: "Boogu Image Edit",
    parameter_mapping: { positivePrompt: {}, seed: {}, referenceImage: {} } }),
  workflow({ id: "wf-video", name: "H3 Video T2V", purpose: "text-to-video",
    parameter_mapping: { positivePrompt: {}, seed: {} } }),
  workflow({ id: "wf-ui", name: "Z-Image Turbo (UI export)", source_format: "ui",
    parameter_mapping: { positivePrompt: {}, seed: {} } }),
];

function renderGenerator() {
  const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  client.setQueryData(["character-sets", "project-1"], [set]);
  client.setQueryData(["media-providers"], catalogue);
  client.setQueryData(["workflows"], workflowList);
  return renderToStaticMarkup(<QueryClientProvider client={client}><CharacterSetGenerator projectId="project-1" /></QueryClientProvider>);
}

describe("CharacterSetGenerator", () => {
  it("edits identity specification, chooses canonical views, and exposes paid confirmation", () => {
    const html = renderGenerator();
    for (const label of ["Appearance / identity", "Proportions", "Wardrobe", "Palette", "Identity tokens", "Negative specification"]) expect(html).toContain(label);
    for (const view of ["Front", "Three-quarter", "Side", "Back", "Full body", "Expression"]) expect(html).toContain(view);
    expect(html).toContain("OpenAI Images (metered)");
    expect(html).toContain("Confirm metered generation");
    expect(html).toContain("Generate selected views");
  });

  it("shows gallery status, real provenance, canonical approval, and stale spec warning", () => {
    const html = renderGenerator();
    expect(html).toContain("Canonical version is stale");
    expect(html).toContain("Approved canonical");
    expect(html).toContain("Provider: openai");
    expect(html).toContain("Model: gpt-image-1");
    expect(html).toContain("Seed: 42");
    expect(html).toContain("SHA: abc123");
    expect(html).toContain("Unapprove canonical");
  });

  it("offers only the workflows that can actually establish an identity", () => {
    const html = renderGenerator();
    // The sheet is what identity comes from, so it has no reference to give.
    // Offering an edit workflow here would let the user pick a run whose views
    // are conditioned on whatever image the exported graph happens to carry.
    expect(html).toContain("Character sheet workflow");
    expect(html).toContain("Z-Image Turbo T2I");
    expect(html).not.toContain("Boogu Image Edit");
    expect(html).not.toContain("H3 Video T2V");
    expect(html).not.toContain("Z-Image Turbo (UI export)");
  });
});

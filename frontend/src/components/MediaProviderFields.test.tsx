import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import MediaProviderFields from "./MediaProviderFields";
import type { MediaProviderCatalogue } from "../types";

const catalogue: MediaProviderCatalogue = {
  video_provider_id: "comfyui",
  default_image_provider_id: "comfyui",
  providers: [
    {
      id: "comfyui",
      label: "Local ComfyUI",
      configured: true,
      local: true,
      mock: true,
      media_types: ["image", "video", "image-to-video"],
      default_model: "workflow",
      models: [{ id: "workflow", label: "Assigned workflow" }],
      api_key_env: "",
      requires_confirmation: false,
      cost_warning: "",
      sizes: [],
      qualities: [],
    },
    {
      id: "openai",
      label: "OpenAI Images",
      configured: true,
      local: false,
      mock: false,
      media_types: ["image"],
      default_model: "gpt-image-1-mini",
      models: [
        { id: "gpt-image-1-mini", label: "GPT Image 1 mini" },
        { id: "gpt-image-1", label: "GPT Image 1" },
      ],
      api_key_env: "OPENAI_API_KEY",
      requires_confirmation: true,
      cost_warning: "Metered",
      sizes: ["1024x1024"],
      qualities: ["low"],
    },
  ],
};

describe("MediaProviderFields", () => {
  it("renders per-shot image provider and model controls", () => {
    const html = renderToStaticMarkup(
      <MediaProviderFields
        catalogue={catalogue}
        generationMode="image"
        providerId="openai"
        model="gpt-image-1-mini"
        onProviderChange={vi.fn()}
        onModelChange={vi.fn()}
      />,
    );
    expect(html).toContain('aria-label="Image provider"');
    expect(html).toContain("OpenAI Images");
    expect(html).toContain('aria-label="Image model"');
    expect(html).toContain("GPT Image 1 mini");
  });

  it("locks video shots to the configured video provider", () => {
    const html = renderToStaticMarkup(
      <MediaProviderFields
        catalogue={catalogue}
        generationMode="video"
        providerId="openai"
        model="gpt-image-1-mini"
        onProviderChange={vi.fn()}
        onModelChange={vi.fn()}
      />,
    );
    expect(html).toContain("Video uses Local ComfyUI");
    expect(html).not.toContain('aria-label="Image provider"');
  });
});

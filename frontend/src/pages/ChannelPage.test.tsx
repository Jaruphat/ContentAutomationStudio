import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ChannelPage from "./ChannelPage";
import type { Channel } from "../types";

vi.mock("../store/useProjectStore", () => ({
  useAppState: () => ({ currentProjectId: "project-1" }),
  useAppDispatch: () => vi.fn(),
}));

function channel(over: Partial<Channel> = {}): Channel {
  return {
    id: "channel-1",
    name: "ODDVERSE",
    handle: "",
    tagline: "Stories from worlds that shouldn't exist.",
    description: "",
    audience: "English-first, global, 18-34",
    brand_notes: "",
    visual_style: "Cinematic documentary realism, muted neutral tones.",
    negative_prompt: "cyberpunk, neon, glossy skin",
    camera_language: "Establishing, medium, detail, reveal.",
    voice_direction: "Calm male documentary narrator, ~150 WPM.",
    sound_direction: "Ambient, foley, minimal music.",
    aspect_ratio: "9:16",
    target_resolution: "1080x1920",
    frame_rate: 30,
    target_duration_sec: 32,
    pillars: [
      { key: "strange_files", name: "STRANGE FILES", purpose: "Anomaly now" },
      { key: "what_if", name: "WHAT IF", purpose: "Impossible scenario" },
    ],
    hooks: [{ key: "H01", name: "Impossible Event" }],
    created_at: "2026-09-05T00:00:00Z",
    updated_at: "2026-09-05T00:00:00Z",
    ...over,
  };
}

function render(data: Channel[] | undefined, episodes: unknown[] = []) {
  const qc = new QueryClient({
    defaultOptions: { queries: { enabled: false, retry: false } },
  });
  if (data) qc.setQueryData(["channels"], data);
  qc.setQueryData(["channel-episodes", "channel-1"], episodes);
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={["/channel"]}>
      <QueryClientProvider client={qc}>
        <ChannelPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("Channel", () => {
  it("shows the bibles that every episode will inherit", () => {
    // The whole reason the page exists: these are typed once, not nine times.
    const html = render([channel()]);

    expect(html).toContain("Visual bible");
    expect(html).toContain("Negative prompt");
    expect(html).toContain("Voice direction");
    expect(html).toContain("documentary realism");
  });

  it("offers the channel's own pillars and hooks when starting an episode", () => {
    // Recorded at the moment the episode is made, because nobody remembers
    // which of nine hooks a video used once it has been live for a month.
    const html = render([channel()]);

    expect(html).toContain("STRANGE FILES");
    expect(html).toContain("H01");
  });

  it("says plainly that the bibles are copied, not linked", () => {
    // A user who believes the link is live will revise the channel expecting
    // an old episode to follow, and it will not.
    expect(render([channel()])).toMatch(/copied, not linked/i);
  });

  it("explains what a channel is for when there are none", () => {
    // An empty list with a lone input teaches nobody why to fill it in.
    const html = render([]);

    expect(html).toContain("No channels yet");
    expect(html).toMatch(/every episode shares/i);
  });

  it("lists the episodes made under the channel with their vocabulary", () => {
    const html = render([channel()], [
      {
        id: "ep-1", title: "The 3:17 Train", pillar: "strange_files",
        hook_type: "H01", ending_type: "twist", premise: "",
        channel_id: "channel-1", objective: "", audience: "",
        content_type: "video", aspect_ratio: "9:16",
        target_resolution: "1080x1920", target_duration_sec: 32,
        frame_rate: 30, language: "en", default_image_workflow_id: null,
        default_video_workflow_id: null, status: "Draft", brief_text: "",
        plot_text: "", created_at: "", updated_at: "",
      },
    ]);

    expect(html).toContain("The 3:17 Train");
    expect(html).toContain("strange_files");
  });
});

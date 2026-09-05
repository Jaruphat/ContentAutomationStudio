import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ChannelAnalytics from "./ChannelAnalytics";
import type { ChannelAnalytics as Report } from "../types";

function report(over: Partial<Report> = {}): Report {
  return {
    ranked_on: "avg_percent_viewed",
    minimum_group_size: 3,
    episode_count: 2,
    unmeasured_count: 7,
    episodes: [],
    groups: {
      pillar: [
        { dimension: "pillar", value: "strange_files", sample_size: 1,
          avg_percent_viewed: 70, views_24h: 1000, episode_ids: ["a"] },
        { dimension: "pillar", value: "what_if", sample_size: 1,
          avg_percent_viewed: 40, views_24h: 1000, episode_ids: ["b"] },
      ],
      hook_type: [],
      ending_type: [],
    },
    winner: {
      pillar: null, sample_size: 0,
      reason: "Not enough measured episodes to compare pillar. Two groups of at least 3 are needed; there is 0.",
    },
    winner_by_hook: { hook_type: null, sample_size: 0, reason: "Not enough measured episodes to compare hook_type." },
    ...over,
  };
}

function render(data: Report) {
  const qc = new QueryClient({
    defaultOptions: { queries: { enabled: false, retry: false } },
  });
  qc.setQueryData(["channel-analytics", "channel-1"], data);
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <ChannelAnalytics channelId="channel-1" />
    </QueryClientProvider>,
  );
}

describe("Channel analytics", () => {
  it("leads with the refusal rather than with a ranking", () => {
    // A comparison that ranks anyway produces a winner, the winner gets
    // scaled, and a month of work follows a number that was noise.
    const html = render(report());

    expect(html).toContain("Not enough measured episodes");
    expect(html).not.toMatch(/Pillar:\s*strange_files/);
  });

  it("names the winner once the sample supports one", () => {
    const html = render(report({
      winner: {
        pillar: "strange_files", sample_size: 3, margin: 34,
        reason: "'strange_files' leads on avg_percent_viewed by 34.0 points across 3 episodes.",
      },
    }));

    expect(html).toContain("strange_files");
    expect(html).toContain("leads on");
  });

  it("says how many episodes are not published yet", () => {
    // Counting an unpublished episode as zero retention would bury the format
    // that was working; saying nothing about it hides how thin the sample is.
    expect(render(report())).toContain("7 not published yet");
  });

  it("marks a group too small to mean anything", () => {
    expect(render(report())).toContain("n=1");
    expect(render(report())).toMatch(/text-amber-400[^>]*>\s*n=1/);
  });

  it("names the metric it ranked on", () => {
    // Views and retention disagree constantly, and a ranking that does not say
    // which it used cannot be argued with.
    expect(render(report())).toContain("avg percent viewed");
  });
});

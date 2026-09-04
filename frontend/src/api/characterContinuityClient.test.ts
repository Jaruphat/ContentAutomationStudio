import { beforeEach, describe, expect, it, vi } from "vitest";

const { get, post, put, del } = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn(),
}));

vi.mock("axios", () => ({
  default: {
    create: () => ({ get, post, put, delete: del }),
    isAxiosError: () => false,
  },
}));

import api from "./client";

describe("character set and continuity API client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const fn of [get, post, put, del]) fn.mockResolvedValue({ data: { ok: true } });
  });

  it("addresses project-scoped character set versions and paid generation", async () => {
    await api.characterSets.list("project-1");
    await api.characterSets.createVersion("project-1", "set-1", { slots: ["front", "side"], notes: "v2" });
    await api.characterSets.generateVersion("project-1", "set-1", "version-2", {
      provider_id: "openai", model: "gpt-image-1", confirm_paid_generation: true,
    });
    await api.characterSets.approveVersion("project-1", "set-1", "version-2");
    await api.characterSets.unapproveVersion("project-1", "set-1", "version-2");

    expect(get).toHaveBeenCalledWith("/projects/project-1/character-sets");
    expect(post).toHaveBeenCalledWith("/projects/project-1/character-sets/set-1/versions", {
      slots: ["front", "side"], notes: "v2",
    });
    expect(post).toHaveBeenCalledWith(
      "/projects/project-1/character-sets/set-1/versions/version-2/generate",
      { provider_id: "openai", model: "gpt-image-1", confirm_paid_generation: true },
    );
    expect(post).toHaveBeenCalledWith("/projects/project-1/character-sets/set-1/versions/version-2/approve");
    expect(post).toHaveBeenCalledWith("/projects/project-1/character-sets/set-1/versions/version-2/unapprove");
  });

  it("updates multi-character shot binding and explicit continuity sources", async () => {
    await api.shots.update("project-1", "scene-1", "shot-2", { character_set_ids: ["set-a", "set-b"] });
    await api.continuity.get("project-1", "scene-1", "shot-2");
    await api.continuity.extract("project-1", "take-1");
    await api.continuity.bind("project-1", "scene-1", "shot-2", "take-1");
    await api.continuity.clear("project-1", "scene-1", "shot-2");

    expect(put).toHaveBeenCalledWith(
      "/projects/project-1/scenes/scene-1/shots/shot-2",
      { character_set_ids: ["set-a", "set-b"] },
    );
    expect(get).toHaveBeenCalledWith("/projects/project-1/scenes/scene-1/shots/shot-2/continuity");
    expect(post).toHaveBeenCalledWith("/projects/project-1/takes/take-1/continuity-frame", {});
    expect(put).toHaveBeenCalledWith("/projects/project-1/scenes/scene-1/shots/shot-2/continuity", {
      source_take_id: "take-1",
    });
    expect(del).toHaveBeenCalledWith("/projects/project-1/scenes/scene-1/shots/shot-2/continuity");
  });
});

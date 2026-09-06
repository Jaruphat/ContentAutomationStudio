/**
 * Approving one shot must not disable Generate for the others.
 *
 * Found while producing an episode through the pages. The flow both delivered
 * episodes were made in is two passes: make the key images, approve them, then
 * animate each clip from its own approved key image. After the first approval
 * the Generate button went dark and stayed dark, because the page required
 * every shot in the project to be ready and an approved shot is not.
 *
 * The endpoint has never worked that way. It queues the shots whose status is
 * Draft, Failed or Ready and leaves the rest alone.
 */

import { describe, expect, it } from "vitest";
import { blockingIssues, canGenerate } from "./generateReadiness";
import type { PreflightResult } from "../types";

const approved = {
  ready: false,
  total_shots: 18,
  ready_shots: 17,
  issues: [
    {
      shot_id: "s1", scene_id: "sc1", shot_order: 1,
      issues: ["Shot status is 'Approved', expected Draft, Failed, Ready"],
    },
  ],
} as unknown as PreflightResult;

const broken = {
  ready: false,
  total_shots: 18,
  ready_shots: 17,
  issues: [
    { shot_id: "s2", scene_id: "sc1", shot_order: 2, issues: ["Missing image prompt"] },
  ],
} as unknown as PreflightResult;

describe("What stops a run", () => {
  it("does not count a shot that is only already approved", () => {
    expect(blockingIssues(approved)).toEqual([]);
    expect(canGenerate(approved)).toBe(true);
  });

  it("still counts a shot that cannot be made", () => {
    expect(blockingIssues(broken)).toEqual(["Missing image prompt"]);
    expect(canGenerate(broken)).toBe(false);
  });

  it("counts a shot that is both approved and stale", () => {
    // Two issues on one shot: the status is skippable, the staleness is not,
    // and the run would be refused for it.
    const both = {
      ...approved,
      issues: [
        {
          shot_id: "s1", scene_id: "sc1", shot_order: 1,
          issues: [
            "Shot status is 'Approved', expected Draft, Failed, Ready",
            "Shot is stale: its generated take predates the current content revision",
          ],
        },
      ],
    } as unknown as PreflightResult;
    expect(canGenerate(both)).toBe(false);
  });

  it("is ready when preflight says every shot is", () => {
    expect(canGenerate({ ready: true, total_shots: 3, ready_shots: 3, issues: [] } as unknown as PreflightResult))
      .toBe(true);
  });

  it("has nothing to run in an empty project", () => {
    expect(canGenerate({ ready: false, total_shots: 0, ready_shots: 0, issues: [] } as unknown as PreflightResult))
      .toBe(false);
  });
});

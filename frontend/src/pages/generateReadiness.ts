import type { PreflightResult } from "../types";

/**
 * Which preflight issues actually stop a run.
 *
 * The endpoint queues the shots whose status makes them eligible - Draft,
 * Failed or Ready - and leaves the rest alone. So a shot reported as "Shot
 * status is 'Approved', expected Draft, Failed, Ready" is not a problem to
 * fix: it is a shot that has already been made and will simply not be part of
 * this run.
 *
 * The page used to require every shot in the project to be ready, which meant
 * approving one shot disabled Generate for all the others. Producing an
 * episode found it the hard way: nine key images had to be made, approved, and
 * then used as the start frames of nine clips - and after the first approval
 * there was no way to generate anything again except one take at a time from
 * Review.
 *
 * Staleness is reported the same way and is not a blocker either. A stale shot
 * is one whose prompt was edited after it was drawn, which is the ordinary way
 * a bad frame is fixed - rewrite it, then generate. A later episode found this
 * one the hard way too: sixty-seven frames approved, twelve rewritten, and
 * Generate refused the run because the twelve it was meant to make were stale.
 */

/** An issue that only says the shot is not in a generatable state. */
const STATUS_ONLY = /^Shot status is '[^']+', expected /;

/** An issue that says the shot needs re-making, which is not a reason to stop. */
const STALE = /^Shot is stale[:\s]/;

export function blockingIssues(preflight: PreflightResult | undefined): string[] {
  const blocking: string[] = [];
  for (const entry of preflight?.issues ?? []) {
    // A shot that is only "not in a generatable state", or only out of date,
    // is either skipped by the endpoint or exactly what the run is for. One
    // missing a prompt or a workflow is a shot the run would refuse, so it
    // still counts.
    const real = entry.issues.filter(
      (text) => !STATUS_ONLY.test(text) && !STALE.test(text),
    );
    blocking.push(...real);
  }
  return blocking;
}

/** True when pressing Generate would actually run something. */
export function canGenerate(preflight: PreflightResult | undefined): boolean {
  if (!preflight) return false;
  if (preflight.ready) return true;
  return blockingIssues(preflight).length === 0 && preflight.total_shots > 0;
}

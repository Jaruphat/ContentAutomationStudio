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
 */

/** An issue that only says the shot is not in a generatable state. */
const STATUS_ONLY = /^Shot status is '[^']+', expected /;

export function blockingIssues(preflight: PreflightResult | undefined): string[] {
  const blocking: string[] = [];
  for (const entry of preflight?.issues ?? []) {
    const real = entry.issues.filter((text) => !STATUS_ONLY.test(text));
    // A shot that is only "not in a generatable state" is skipped by the
    // endpoint. One that is also stale, or missing a prompt, is a shot the
    // run would refuse, so it still counts.
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

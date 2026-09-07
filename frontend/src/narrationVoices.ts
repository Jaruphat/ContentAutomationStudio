/**
 * The voices the hosted narrator will answer to.
 *
 * The render request has taken a voice name since narration was added, and
 * nothing in the application ever sent one - so every episode was read by the
 * default, a deep male documentary voice, whatever the character on screen
 * happened to be. A cartoon onigiri narrating its own history is the point at
 * which that stops being acceptable.
 *
 * Every name below was verified against the speech endpoint rather than copied
 * from documentation: each one was asked to say a line and returned audio.
 *
 * Which voice matters less than how it is directed. The channel's voice
 * direction is what carries age and energy - the same voice reads as a
 * narrator or as a small character depending on what it is told - so the
 * select is a starting point and the direction is the instrument.
 */

export const NARRATION_VOICES = [
  "alloy", "ash", "ballad", "cedar", "coral", "echo", "fable", "marin",
  "nova", "onyx", "sage", "shimmer", "verse",
] as const;

export type NarrationVoice = (typeof NARRATION_VOICES)[number];

/** The one used when nothing is chosen, matching the backend's default. */
export const DEFAULT_NARRATION_VOICE: NarrationVoice = "onyx";

/**
 * A name the speech endpoint will accept, or the default.
 *
 * A voice is stored as a plain string, so a value can arrive from an older
 * project, a hand-edited setting, or a provider that has since renamed one.
 * Falling back is better than sending a name that fails the render after the
 * pictures are already made.
 */
export function resolveNarrationVoice(value: string | null | undefined): NarrationVoice {
  const name = (value ?? "").trim().toLowerCase();
  return (NARRATION_VOICES as readonly string[]).includes(name)
    ? (name as NarrationVoice)
    : DEFAULT_NARRATION_VOICE;
}

/* ──────────────────────────────────────────────────────────────────────────
   errorDiagnostics -- turns a caught stage error into something safe to show
   and to log: no absolute paths, no secret-shaped substrings, and a short id
   that is the same every time the same stage hits the same underlying error
   so occurrences can be correlated without carrying any detail themselves.
   ────────────────────────────────────────────────────────────────────────── */

const WINDOWS_PATH = /[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]+/g;
const UNIX_PATH = /\/(?:home|Users|usr|var|etc|root)\/[^\s'")]+/g;
const FILE_URI = /file:\/\/\/?[^\s'")]+/gi;
/** Long contiguous alnum/-/_ runs: api keys, bearer tokens, uuids-as-secrets. */
const TOKEN_LIKE = /[A-Za-z0-9_-]{20,}/g;

const MAX_MESSAGE_LENGTH = 200;
const FALLBACK_MESSAGE = "No further detail is available.";

export interface SanitizedError {
  name: string;
  message: string;
}

function rawMessageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "Unknown error";
}

function nameOf(error: unknown): string {
  if (error instanceof Error) return error.name || "Error";
  return "Error";
}

export function sanitizeErrorDetail(error: unknown): SanitizedError {
  const name = nameOf(error);
  let message = rawMessageOf(error)
    .replace(FILE_URI, "[path]")
    .replace(WINDOWS_PATH, "[path]")
    .replace(UNIX_PATH, "[path]")
    .replace(TOKEN_LIKE, "[redacted]")
    .trim();

  if (!message) message = FALLBACK_MESSAGE;
  if (message.length > MAX_MESSAGE_LENGTH) {
    message = `${message.slice(0, MAX_MESSAGE_LENGTH)}...`;
  }

  return { name, message };
}

/** FNV-1a 32-bit -- small, dependency-free, stable across runs and machines. */
function fnv1a(input: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/**
 * Deterministic, not random: the same stage failing the same way always
 * produces the same id, so a support conversation can say "ERR-1A2B3C4D" and
 * mean something reproducible instead of a fresh token per page load.
 */
export function buildDiagnosticId(stageName: string, error: unknown): string {
  const { name, message } = sanitizeErrorDetail(error);
  const basis = `${stageName}::${name}::${message}`;
  return `ERR-${fnv1a(basis).toString(16).toUpperCase().padStart(8, "0")}`;
}

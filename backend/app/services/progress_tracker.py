"""What ComfyUI last said about the prompts currently running.

ComfyUI reports sampler steps and the executing node over a websocket, and
only to the client id that submitted the prompt. Polling `/history` cannot see
any of it: a prompt is absent from history until it finishes, so REST can tell
"running" from "done" and nothing else. On this hardware a shot can take eight
minutes, which is a long time to show a user the word "Running".

This holds that stream as a small in-memory cache, keyed by prompt id. It is
never a source of truth - the queue still decides a job's outcome from
`/history` - so every path here degrades to "unknown" rather than raising. A
dropped socket should cost a progress bar, never a generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("cas.progress")

#: Frames that mean a prompt is over, whatever its outcome.
TERMINAL_TYPES = frozenset({"execution_success", "execution_error", "execution_interrupted"})


@dataclass(frozen=True)
class ProgressSnapshot:
    """How far one prompt has got, as far as anyone here knows."""

    fraction: float = 0.0
    step: int = 0
    total: int = 0
    #: The node ComfyUI says it is executing, for naming the stage.
    node: str = ""


class ProgressTracker:
    """A cache of live progress, one entry per running prompt."""

    def __init__(self) -> None:
        self._by_prompt: dict[str, ProgressSnapshot] = {}

    def snapshot(self, prompt_id: str) -> ProgressSnapshot | None:
        """What is known about ``prompt_id``, or None if nothing is."""
        return self._by_prompt.get(prompt_id)

    def forget(self, prompt_id: str) -> None:
        self._by_prompt.pop(prompt_id, None)

    def handle(self, message: Any) -> None:
        """Fold one websocket frame in, ignoring anything unexpected.

        This runs inside a background socket loop, where an exception would
        take the listener down and blind every job at once. A frame that
        cannot be understood is therefore dropped rather than raised on.
        """
        try:
            if not isinstance(message, dict):
                return
            kind = message.get("type")
            data = message.get("data")
            if not isinstance(data, dict):
                return
            prompt_id = str(data.get("prompt_id") or "")
            if not prompt_id:
                return

            if kind in TERMINAL_TYPES:
                self.forget(prompt_id)
                return

            current = self._by_prompt.get(prompt_id) or ProgressSnapshot()

            if kind == "progress":
                total = int(data.get("max") or 0)
                step = int(data.get("value") or 0)
                if total <= 0:
                    return
                fraction = min(1.0, max(0.0, step / total))
                self._by_prompt[prompt_id] = ProgressSnapshot(
                    fraction=fraction, step=step, total=total, node=current.node,
                )
                return

            if kind == "executing":
                node = data.get("display_node") or data.get("node")
                if not node:
                    return
                self._by_prompt[prompt_id] = ProgressSnapshot(
                    fraction=current.fraction, step=current.step,
                    total=current.total, node=str(node),
                )
        except (TypeError, ValueError):
            logger.debug("Ignoring unparseable progress frame: %r", message)

"""Derive an image-to-video graph that also accepts the frame to land on.

`MiniMaxH3ImageToVideo` has taken a `last_frame` since long before this project
existed; the exported graph simply never wired one. Adding a loader for it is
the whole change - model, sampler, VAE and text encoder are untouched.

What it buys: with only a first frame, a clip drifts and the shot after it
inherits the drift. Given both ends, the model interpolates between two frames
somebody already approved, so the cut lands exactly where the next shot opens.

The new input is mapped to `endFrameImage`, never to `referenceImage2`.
Reference slots are positional and the resolver fills them with canonical
character views; sending one of those to `last_frame` would end the clip on a
studio portrait of the character while every hash and lineage entry still
checked out.

Usage:
    python scripts/derive_end_frame_workflow.py SOURCE.json [-o DEST.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

#: Video nodes known to accept a final frame, and the input it arrives on.
LAST_FRAME_INPUTS = {"MiniMaxH3ImageToVideo": "last_frame"}


def _free_node_id(graph: dict) -> str:
    candidate = 1
    while str(candidate) in graph:
        candidate += 1
    return str(candidate)


def derive(graph: dict) -> tuple[dict, str, str]:
    """Return the graph with a last-frame loader, plus its node id and input.

    Raises
    ------
    ValueError
        If no node here takes a final frame, or one is already connected -
        returning the input unchanged would imply work that did not happen.
    """
    targets = [
        (node_id, LAST_FRAME_INPUTS[node["class_type"]])
        for node_id, node in graph.items()
        if node.get("class_type") in LAST_FRAME_INPUTS
    ]
    if not targets:
        raise ValueError(
            "No node in this graph accepts a final frame. Supported: "
            + ", ".join(sorted(LAST_FRAME_INPUTS))
        )
    if len(targets) > 1:
        raise ValueError(
            f"Several video nodes ({', '.join(n for n, _ in targets)}); which one "
            f"should land on the frame is a decision for the editor."
        )
    node_id, input_name = targets[0]
    inputs = graph[node_id]["inputs"]

    first = inputs.get("first_frame")
    if not isinstance(first, list):
        raise ValueError(
            f"Node {node_id} has no first frame connected. A clip that does not "
            f"know where it starts cannot be told where to stop."
        )
    if input_name in inputs:
        raise ValueError(f"Node {node_id} already has a {input_name} connected.")

    first_loader = str(first[0])
    loader_id = _free_node_id(graph)
    graph[loader_id] = {
        "inputs": dict(graph[first_loader]["inputs"]),
        "class_type": graph[first_loader]["class_type"],
        "_meta": {"title": "Load Image (end frame)"},
    }
    inputs[input_name] = [loader_id, 0]
    return graph, loader_id, input_name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="API-format workflow JSON to derive from")
    parser.add_argument("-o", "--output", default="")
    args = parser.parse_args()

    with open(args.source, encoding="utf-8") as handle:
        graph = json.load(handle)

    try:
        graph, loader_id, input_name = derive(graph)
    except ValueError as exc:
        print(f"Cannot derive: {exc}", file=sys.stderr)
        return 1

    dest = args.output or (os.path.splitext(args.source)[0] + "_end_frame.json")
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(graph, handle, indent=2, ensure_ascii=False)

    print(f"wrote {dest}")
    print(f"  endFrameImage -> node {loader_id}, field 'image'  (feeds {input_name})")
    print("Import it, add that to the existing mapping, then validate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Derive a two-reference edit graph from a registered one-reference graph.

``TextEncodeBooguEdit`` takes its reference images through an autogrow input
that runs to sixteen slots, but an exported graph wires only the slots that
were connected in the editor. Adding a loader and binding it to the next slot
is the whole change: model, sampler, VAE and text encoder are untouched, so
anything already true of the one-reference run stays true here.

Why two matters. With a single slot the hand-off frame and the canonical
character view compete for it, and the frame wins - so a character's face
survives only as far as the previous clip carried it and drifts a little
further at every hand-off, which is most of the reason to keep a character set
at all. With two, the frame holds pose, framing and light while the canonical
view holds the face and wardrobe.

Slot order is not arbitrary. The app fills slot one with whatever starts the
shot (a continuity frame when there is one), and in this graph slot one also
sizes the output canvas - which is right, because that is the frame whose
composition the shot continues.

The workflow directory is git-ignored, since a graph names local model files.
This script is the reproducible part: run it, then import the result and map
``referenceImage`` to the first loader and ``referenceImage2`` to the second.

Usage:
    python scripts/derive_two_reference_workflow.py SOURCE.json [-o DEST.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

#: Node classes whose reference images arrive through an autogrow input.
AUTOGROW_ENCODERS = {"TextEncodeBooguEdit"}


def derive(graph: dict, *, loader_id: str | None = None) -> tuple[dict, str, str]:
    """Return the graph with one more reference loader, and the two node ids.

    Raises
    ------
    ValueError
        If the graph has no autogrow encoder, or already binds a second slot -
        in which case there is nothing to derive and silently returning the
        input would suggest otherwise.
    """
    encoders = [
        node_id
        for node_id, node in graph.items()
        if node.get("class_type") in AUTOGROW_ENCODERS
    ]
    if not encoders:
        raise ValueError(
            "No autogrow reference encoder in this graph. Only workflows built "
            f"around {', '.join(sorted(AUTOGROW_ENCODERS))} can grow a slot."
        )
    if len(encoders) > 1:
        raise ValueError(
            f"Several reference encoders ({', '.join(encoders)}); which one "
            f"should take the second image is a decision for the editor."
        )
    encoder = encoders[0]
    inputs = graph[encoder]["inputs"]

    first = inputs.get("images.image_1")
    if not isinstance(first, list):
        raise ValueError(
            f"Node {encoder} has no first reference image connected, so there "
            f"is no primary slot for a second one to sit beside."
        )
    if "images.image_2" in inputs:
        raise ValueError(f"Node {encoder} already binds a second reference slot.")

    primary_loader = str(first[0])
    second_loader = loader_id or _free_node_id(graph)
    graph[second_loader] = {
        "inputs": dict(graph[primary_loader]["inputs"]),
        "class_type": graph[primary_loader]["class_type"],
        "_meta": {"title": "Load Image (identity reference)"},
    }
    inputs["images.image_2"] = [second_loader, 0]
    return graph, primary_loader, second_loader


def _free_node_id(graph: dict) -> str:
    """A numeric id no node is using, so nothing is overwritten."""
    candidate = 1
    while str(candidate) in graph:
        candidate += 1
    return str(candidate)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="API-format workflow JSON to derive from")
    parser.add_argument("-o", "--output", default="", help="where to write the result")
    args = parser.parse_args()

    with open(args.source, encoding="utf-8") as handle:
        graph = json.load(handle)

    try:
        graph, primary, second = derive(graph)
    except ValueError as exc:
        print(f"Cannot derive: {exc}", file=sys.stderr)
        return 1

    dest = args.output or (
        os.path.splitext(args.source)[0] + "_two_reference.json"
    )
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(graph, handle, indent=2, ensure_ascii=False)

    print(f"wrote {dest}")
    print(f"  referenceImage  -> node {primary}, field 'image'")
    print(f"  referenceImage2 -> node {second}, field 'image'")
    print("Import it, apply that mapping, then validate before generating.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

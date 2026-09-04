"""How far along a running generation is.

A shot can take eight minutes on this hardware, and until now the only thing
the queue could say about one was "Running". ComfyUI does report sampler steps
and the node it is on, but only over a websocket, and only to the client id
that submitted the prompt - which is why nothing was listening: the adapter
used a different client id for every job.

The tracker is deliberately a cache of what ComfyUI last said, never a source
of truth. Generation must not fail because a websocket dropped, so an unknown
prompt reports no progress rather than raising, and a stale entry is worth
less than a wrong one is harmful.
"""

from app.services.progress_tracker import ProgressTracker


def test_a_prompt_nobody_has_reported_on_has_no_progress():
    """Silence means unknown, not zero - and never an exception."""
    tracker = ProgressTracker()
    assert tracker.snapshot("never-seen") is None


def test_sampler_steps_become_a_fraction():
    tracker = ProgressTracker()
    tracker.handle({
        "type": "progress",
        "data": {"value": 3, "max": 8, "prompt_id": "p1", "node": "57:3"},
    })
    snapshot = tracker.snapshot("p1")
    assert snapshot is not None
    assert snapshot.fraction == 0.375
    assert snapshot.step == 3
    assert snapshot.total == 8


def test_the_executing_node_is_remembered_so_the_stage_can_be_named():
    """"Running" tells a user nothing; "sampling" or "decoding" tells them where."""
    tracker = ProgressTracker()
    tracker.handle({
        "type": "executing",
        "data": {"node": "57:3", "display_node": "KSampler", "prompt_id": "p1"},
    })
    snapshot = tracker.snapshot("p1")
    assert snapshot is not None
    assert snapshot.node == "KSampler"


def test_a_later_message_replaces_an_earlier_one():
    tracker = ProgressTracker()
    for step in (1, 2, 7):
        tracker.handle({
            "type": "progress",
            "data": {"value": step, "max": 8, "prompt_id": "p1"},
        })
    assert tracker.snapshot("p1").step == 7


def test_finishing_clears_the_entry_so_the_map_cannot_grow_without_bound():
    """A long session generates hundreds of prompts; none of them are needed
    after they finish, and the queue has the terminal state from /history."""
    tracker = ProgressTracker()
    tracker.handle({"type": "progress", "data": {"value": 1, "max": 8, "prompt_id": "p1"}})
    tracker.handle({"type": "execution_success", "data": {"prompt_id": "p1"}})
    assert tracker.snapshot("p1") is None


def test_an_error_clears_the_entry_too():
    tracker = ProgressTracker()
    tracker.handle({"type": "progress", "data": {"value": 1, "max": 8, "prompt_id": "p1"}})
    tracker.handle({"type": "execution_error", "data": {"prompt_id": "p1"}})
    assert tracker.snapshot("p1") is None


def test_malformed_messages_are_ignored_rather_than_raising():
    """This runs inside a background socket loop. A surprising frame there
    must not take the listener down and blind every running job."""
    tracker = ProgressTracker()
    for message in (
        {},
        {"type": "progress"},
        {"type": "progress", "data": {}},
        {"type": "progress", "data": {"value": "x", "max": 8, "prompt_id": "p1"}},
        {"type": "progress", "data": {"value": 1, "max": 0, "prompt_id": "p1"}},
        {"type": "executing", "data": {"node": None, "prompt_id": "p1"}},
    ):
        tracker.handle(message)
    # The zero-max frame must not have produced a division by zero, and the
    # cleared executing node must not have invented progress.
    snapshot = tracker.snapshot("p1")
    assert snapshot is None or snapshot.fraction == 0.0


def test_progress_is_clamped_to_the_range_a_bar_can_draw():
    tracker = ProgressTracker()
    tracker.handle({"type": "progress", "data": {"value": 99, "max": 8, "prompt_id": "p1"}})
    assert tracker.snapshot("p1").fraction == 1.0

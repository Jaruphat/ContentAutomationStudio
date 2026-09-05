"""
Tests for generation error classification (PRD section 10.5).

The retry decision is the point of this module: a dropped connection is worth
retrying, an out-of-memory failure is not. Getting that backwards either buries
the real cause under three identical failures or gives up on a blip.
"""

import pytest

from app.services import error_classifier
from app.services.error_classifier import classify


class TestNonRetryableCategories:
    @pytest.mark.parametrize("message", [
        "CUDA out of memory. Tried to allocate 2.00 GiB",
        "RuntimeError: OOM when allocating tensor",
        "Insufficient memory on device 0",
    ])
    def test_out_of_memory_is_never_retried(self, message):
        """The PRD is explicit that OOM must not be retried indefinitely."""
        result = classify(message)
        assert result.code == error_classifier.OUT_OF_MEMORY_ERROR
        assert result.retryable is False
        assert "resolution" in result.suggested_action.lower()

    @pytest.mark.parametrize("message", [
        "Node type not found: WanVideoSampler",
        "Unknown node: IPAdapterApply",
        "This custom node does not exist in this installation",
    ])
    def test_missing_custom_node(self, message):
        result = classify(message)
        assert result.code == error_classifier.MISSING_CUSTOM_NODE_ERROR
        assert result.retryable is False

    @pytest.mark.parametrize("message", [
        "ckpt_name: 'sd_xl.safetensors' not in list of available checkpoints",
        "Value not in list: lora_name",
        "model not found",
    ])
    def test_missing_model(self, message):
        result = classify(message)
        assert result.code == error_classifier.MISSING_MODEL_ERROR
        assert result.retryable is False

    def test_output_missing(self):
        result = classify("Workflow finished but produced no output files")
        assert result.code == error_classifier.OUTPUT_MISSING_ERROR
        assert result.retryable is False

    def test_media_validation(self):
        result = classify("moov atom not found; file is corrupt")
        assert result.code == error_classifier.MEDIA_VALIDATION_ERROR
        assert result.retryable is False


class TestRetryableCategories:
    @pytest.mark.parametrize("message", [
        "Failed to submit job to ComfyUI: All connection attempts failed",
        "Cannot connect to ComfyUI at http://127.0.0.1:8001",
        "Connection refused",
        "503 Service Unavailable",
    ])
    def test_connection_errors_are_retried(self, message):
        result = classify(message)
        assert result.code == error_classifier.CONNECTION_ERROR
        assert result.retryable is True

    def test_timeout_is_retried(self):
        result = classify("Generation timed out after 600s")
        assert result.code == error_classifier.GENERATION_TIMEOUT
        assert result.retryable is True

    def test_unknown_defaults_to_retryable(self):
        result = classify("something entirely unexpected happened")
        assert result.code == error_classifier.UNKNOWN_ERROR
        assert result.retryable is True


class TestPrecedence:
    def test_oom_wins_over_connection_wording(self):
        """An OOM report that also mentions the connection must not be treated
        as a transient network blip."""
        result = classify(
            "connection to worker lost: CUDA out of memory while allocating"
        )
        assert result.code == error_classifier.OUT_OF_MEMORY_ERROR
        assert result.retryable is False

    def test_custom_node_wins_over_model_wording(self):
        result = classify("Unknown node: the model loader custom node is absent")
        assert result.code == error_classifier.MISSING_CUSTOM_NODE_ERROR


class TestExceptionInput:
    def test_exception_type_name_is_considered(self):
        result = classify(None, ConnectionError())
        assert result.code == error_classifier.CONNECTION_ERROR

    def test_exception_message_is_considered(self):
        result = classify(None, RuntimeError("CUDA out of memory"))
        assert result.code == error_classifier.OUT_OF_MEMORY_ERROR

    def test_message_and_exception_combined(self):
        result = classify("submission failed", TimeoutError("deadline exceeded"))
        assert result.code == error_classifier.GENERATION_TIMEOUT

    @pytest.mark.parametrize("message", [None, "", "   "])
    def test_empty_input_is_unknown(self, message):
        result = classify(message)
        assert result.code == error_classifier.UNKNOWN_ERROR


class TestContract:
    def test_every_classification_carries_an_action(self):
        messages = [
            "cuda out of memory", "unknown node", "checkpoint missing",
            "timed out", "connection refused", "no output", "invalid prompt",
            "corrupt", "mystery",
        ]
        for message in messages:
            assert classify(message).suggested_action.strip()


def test_a_streaming_read_failure_is_named_as_the_memory_problem_it_is():
    """`HostBuffer.read_file_slice failed` reads like a corrupt file. It is not.

    It is what a twenty-gigabyte model looks like when it cannot be streamed
    into memory that something else is still holding. The same graph runs
    unchanged once the provider releases what it has loaded, so the message
    has to say that - otherwise the next person spends an hour re-downloading
    a model that was never broken.
    """
    result = error_classifier.classify("RuntimeError: HostBuffer.read_file_slice failed")

    assert result.retryable is True
    assert "memory" in result.suggested_action.lower()


@pytest.mark.parametrize("message", [
    "Out of VRAM",
    "Allocation on device failed: not enough VRAM",
    "torch.cuda.OutOfMemoryError: CUDA out of memory",
])
def test_running_out_of_card_memory_is_never_retried(message):
    """Retrying an OOM unchanged reaches the same answer, slower.

    "Out of VRAM" says nothing the earlier keywords matched, so it fell
    through to the retryable default and a job that could not fit was tried
    again anyway.
    """
    result = error_classifier.classify(message)
    assert result.code == error_classifier.OUT_OF_MEMORY_ERROR, result
    assert result.retryable is False

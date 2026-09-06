"""A caption may not break a word in half.

Seen in a delivered cut. The first line of an episode read:

    This house has seven roo
    ms. The plan shows six.

The wrapper searched for a space that would leave *both* lines inside the
configured width, found none, and fell back to a hard cut at the character
limit. Grapheme-safe, so no combining mark was split - and still unreadable,
because a reader who has two seconds to take in a line cannot spend one of them
reassembling a word.

There is no width at which cutting a word is the better choice. When the words
do not fit, the cue is too long for two lines and belongs in two cues, which is
a decision the splitter above it already knows how to make. The hard cut stays
for writing that offers no break to prefer - Thai runs without spaces, and a
single unbroken token has to go somewhere.

The tests below exercise the pipeline rather than the wrapper alone. Splitting
into cues and wrapping a cue are one decision taken in two places, and the
wrapper's contract is a cue the splitter has already bounded.
"""

import pytest

from app.services import subtitle_service


NARROW = 24
LINE = "This house has seven rooms. The plan shows six."

LINES = [
    LINE,
    "There's a door at the end of the upstairs hall.",
    "The train isn't on any schedule, and nobody has ever stepped off.",
    "Until last night.",
    "We haven't bought it yet.",
    "For three weeks, nobody opened it.",
]


def _captions(text: str, width: int) -> list[str]:
    """Every rendered line, the way the renderers produce them."""
    lines: list[str] = []
    for chunk in subtitle_service._split_text(text, width):
        lines.extend(subtitle_service._wrap_two_lines(chunk, width).split("\n"))
    return [line for line in lines if line]


# ---------------------------------------------------------------------------
# The failure this exists for
# ---------------------------------------------------------------------------

def test_the_line_that_shipped_broken_keeps_its_words():
    assert _captions(LINE, NARROW) == [
        "This house has seven",
        "rooms.",
        "The plan shows six.",
    ]


@pytest.mark.parametrize("width", [12, 16, 20, 24, 30, 36])
@pytest.mark.parametrize("text", LINES)
def test_no_width_makes_breaking_a_word_the_right_answer(text, width):
    assert " ".join(_captions(text, width)).split() == text.split()


@pytest.mark.parametrize("width", [12, 16, 20, 24, 30, 36])
@pytest.mark.parametrize("text", LINES)
def test_no_caption_line_runs_past_the_width_it_was_given(text, width):
    for line in _captions(text, width):
        assert len(subtitle_service._graphemes(line)) <= width


# ---------------------------------------------------------------------------
# Where a cue is divided
# ---------------------------------------------------------------------------

def test_a_cue_is_divided_at_the_end_of_a_sentence_when_one_is_near():
    """"This house has seven / rooms. The plan shows six." is closer to an even
    division and reads worse. A full stop is where the writer already broke the
    thought."""
    assert subtitle_service._split_text(LINE, NARROW) == [
        "This house has seven rooms. ",
        "The plan shows six.",
    ]


def test_the_pieces_of_a_divided_cue_still_spell_the_line():
    """Slicing the source, not rejoining words: a caption track that loses a
    space at every cue boundary no longer matches the script."""
    for width in (12, 16, 24, 36):
        assert "".join(subtitle_service._split_text(LINE, width)) == LINE


def test_dividing_a_cue_twice_gives_what_dividing_it_once_gave():
    """The renderers validate cues again on the way out. A splitter that keeps
    finding new divisions turns one caption into several between the timeline
    and the file."""
    for width in (12, 16, 24, 36):
        once = subtitle_service._split_text(LINE, width)
        twice = [
            piece
            for chunk in once
            for piece in subtitle_service._split_text(chunk, width)
        ]
        assert once == twice


# ---------------------------------------------------------------------------
# Writing with no break to prefer
# ---------------------------------------------------------------------------

def test_a_single_token_wider_than_the_line_is_cut_but_not_spaced():
    """The one case with no break to prefer. It is cut, because the
    alternative is text running off the side of the frame - but no space is
    invented inside it, which would turn one word into several."""
    captions = _captions("A" * 40, 10)

    assert "".join(captions) == "A" * 40
    assert all(len(line) <= 10 for line in captions)


def test_thai_without_spaces_is_still_divided():
    """Thai runs without word spaces. Refusing to divide it would leave one
    caption on screen for the length of the shot."""
    thai = "ภาษาไทยกำลังทดสอบการตัดบรรทัดให้อ่านได้จริงในคลิปแนวตั้ง"

    chunks = subtitle_service._split_text(thai, 12)

    assert len(chunks) > 1
    assert "".join(chunks) == thai


# ---------------------------------------------------------------------------
# Two lines the writer wrote
# ---------------------------------------------------------------------------

def test_two_lines_the_writer_wrote_are_left_alone():
    assert subtitle_service._wrap_two_lines(
        "Until last night.\nHe opened it.", NARROW
    ) == "Until last night.\nHe opened it."


def test_the_rendered_srt_carries_no_broken_word():
    cues = [{"start_sec": 0.0, "end_sec": 4.0, "text": LINE}]

    srt = subtitle_service.render_srt(cues, NARROW)

    assert "roo\nms" not in srt
    body = [
        line for line in srt.splitlines()
        if line and "-->" not in line and not line.strip().isdigit()
    ]
    assert " ".join(body).split() == LINE.split()

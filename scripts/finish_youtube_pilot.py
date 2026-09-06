"""Render the reviewed pilot through Studio; never generate or approve takes."""
import argparse
import json
from pathlib import Path

from run_motion_probe import call, save
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8002")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--openai-voice", action="store_true", help="Authorize the metered narration for these five lines")
    args = parser.parse_args()
    state = json.loads(args.state.read_text())
    pid = state["project_id"]
    takes = call(args.api, "GET", f"/api/projects/{pid}/takes")
    for shot in state["shots"]:
        if not any(t["shot_id"] == shot["shot_id"] and t["review_status"] == "Approved" for t in takes):
            raise RuntimeError(f"Review and approve {shot['name']} before rendering")
        call(args.api, "PUT", f"/api/projects/{pid}/scenes/{shot['scene_id']}/shots/{shot['shot_id']}", json={"audio_gain_db": -12})
    call(args.api, "PUT", f"/api/projects/{pid}/subtitles", json={
        "mode": "burn_in", "preset": "clean", "font_family": "Segoe UI",
        "font_size": 52, "bold": True, "outline_width": 3,
        "max_chars_per_line": 26, "vertical_margin": 205,
    })
    timeline = call(args.api, "POST", f"/api/projects/{pid}/timeline/build")
    save(args.state.parent / "timeline.json", timeline)
    if timeline["item_count"] != len(state["shots"]):
        raise RuntimeError("The timeline does not contain all reviewed shots")
    payload = {"narrate": True}
    if args.openai_voice:
        payload.update(voice_provider="openai", voice="onyx", confirm_paid_generation=True,
            voice_instructions="A calm male British storyteller recalling an unsettling event. Speak clearly at about 155 words per minute with restrained tension. Use a natural conversational delivery, a brief pause at punctuation, and no long pauses before or after the sentence. The final revelation is quiet and serious. Do not add any words.")
    result = requests.post(args.api + f"/api/projects/{pid}/render", json=payload, timeout=1800)
    result.raise_for_status()
    rendered = result.json()
    save(args.state.parent / "render.json", rendered)
    print(json.dumps(rendered, indent=2), flush=True)
    if not rendered["rendered"]:
        raise RuntimeError(rendered.get("reason"))
    call(args.api, "PUT", f"/api/projects/{pid}/publish", json={
        "publish_title": "This Train Stops at an Abandoned Station Every Night | The Last Passenger",
        "series_label": "ODDVERSE · Strange Files",
        "publish_description": "The station closed thirty years ago. So why does the train still stop?\n\nThe Last Passenger — an original fictional supernatural short from ODDVERSE.\n\nCreated with AI-generated visuals and an AI-generated narrator. This is a fictional story, not footage of a real event.\n\n#Shorts #Mystery #GhostStory #ODDVERSE",
        "publish_hashtags": "#Shorts #Mystery #GhostStory #ODDVERSE",
    })


if __name__ == "__main__":
    main()

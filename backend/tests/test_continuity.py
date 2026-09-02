from app.services.continuity import find_continuity_issues


def test_recurring_prop_requirement_flags_only_affected_shot_ids():
    requirements = ["Exactly one recurring white paper boat throughout."]
    shots = [
        {
            "id": "shot-ok",
            "subject": "child with paper boat",
            "image_prompt": "child holding exactly one white paper boat",
        },
        {
            "id": "shot-bad",
            "subject": "child with paper boat",
            "image_prompt": "child holding a boat",
        },
        {
            "id": "shot-unrelated",
            "subject": "empty skyline",
            "image_prompt": "empty skyline at dusk",
        },
    ]

    issues = find_continuity_issues(shots, requirements)

    assert [issue["shot_id"] for issue in issues] == ["shot-bad"]
    assert issues[0]["code"] == "recurring_prop_continuity"
    assert issues[0]["missing"] == ["count:one", "color:white", "identity:paper boat"]


def test_location_requirement_applies_to_all_shots_in_that_location():
    requirements = [{
        "text": "Recurring prop: exactly one red umbrella",
        "shot_ids": ["rain-1", "rain-2"],
    }]
    shots = [
        {"id": "rain-1", "image_prompt": "exactly one red umbrella in rain"},
        {"id": "rain-2", "image_prompt": "rainy pavement"},
        {"id": "dry-1", "image_prompt": "sunny pavement"},
    ]

    issues = find_continuity_issues(shots, requirements)

    assert [issue["shot_id"] for issue in issues] == ["rain-2"]

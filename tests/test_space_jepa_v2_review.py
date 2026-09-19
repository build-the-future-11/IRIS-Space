from __future__ import annotations

from siderea.review.inspection import space_jepa_v2_panel


def test_space_jepa_v2_panel_is_shadow_only_and_escaped() -> None:
    html = space_jepa_v2_panel(
        {
            "candidate_id": "<candidate>",
            "review_priority": 3.0,
            "priority_semantics": "aqpm_predictive_surprise_not_probability",
            "aqpm": {
                "horizons_days": [1.0, 3.0],
                "mean_absolute_latent_error": [0.1, 0.2],
                "memory_status": "not_applied",
                "physics_status": "not_identifiable",
            },
        }
    )
    assert "&lt;candidate&gt;" in html
    assert "cannot authorize reporting" in html

from src.support.agent.qualification.snapshot_utils import pick_fresher_snapshot


def test_pick_fresher_snapshot_prefers_higher_version():
    older = {"version": 2, "qualification_stage": "interested", "interested": True}
    newer = {"version": 3, "qualification_stage": "qualified", "interested": True, "qualified": True}

    chosen = pick_fresher_snapshot(older, newer)

    assert chosen["version"] == 3
    assert chosen["qualification_stage"] == "qualified"


def test_pick_fresher_snapshot_prefers_updated_at_when_versions_match():
    older = {"version": 3, "updated_at": "2026-04-10T10:00:00+00:00", "qualification_stage": "interested"}
    newer = {"version": 3, "updated_at": "2026-04-10T10:00:05+00:00", "qualification_stage": "qualified"}

    chosen = pick_fresher_snapshot(older, newer)

    assert chosen["updated_at"] == "2026-04-10T10:00:05+00:00"
    assert chosen["qualification_stage"] == "qualified"

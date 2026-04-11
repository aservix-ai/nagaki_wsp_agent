import asyncio

from src.support.agent.qualification import worker


async def _noop_save_snapshot(thread_id, snapshot):
    return None


def test_process_event_triggers_admin_notification_on_qualified(monkeypatch):
    called = {"lead_sync": 0, "admin": 0}

    async def fake_load_snapshot(thread_id):
        return {"version": 0, "qualification_stage": "interested"}

    async def fake_extract_evidence_from_conversation(**kwargs):
        return {"has_own_capital": True, "understands_asset_conditions": True, "intent_type": "investor"}

    def fake_evaluate_qualification(state):
        class Result:
            interested = True
            qualified = True
            stage = "qualified"
            missing_interested = []
            missing_qualified = []

        return Result()

    def fake_trigger_lead_sync(**kwargs):
        called["lead_sync"] += 1

    def fake_trigger_qualified_admin_notification(**kwargs):
        called["admin"] += 1

    monkeypatch.setattr(worker, "load_snapshot", fake_load_snapshot)
    monkeypatch.setattr(worker, "save_snapshot", _noop_save_snapshot)
    monkeypatch.setattr(worker, "extract_evidence_from_conversation", fake_extract_evidence_from_conversation)
    monkeypatch.setattr(worker, "evaluate_qualification", fake_evaluate_qualification)
    monkeypatch.setattr(worker, "trigger_lead_sync", fake_trigger_lead_sync)
    monkeypatch.setattr(worker, "trigger_qualified_admin_notification", fake_trigger_qualified_admin_notification)

    asyncio.run(
        worker._process_event(
            thread_id="lead:+34600111222",
            turn_id=1,
            user_text="quiero coordinar una visita",
            conversation_context="",
        )
    )

    assert called["lead_sync"] == 1
    assert called["admin"] == 1

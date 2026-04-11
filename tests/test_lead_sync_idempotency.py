import asyncio

from src.support.agent import lead_sync


class DummyResponse:
    def raise_for_status(self):
        return None


def test_sync_lead_idempotent(monkeypatch, tmp_path):
    db_path = tmp_path / "lead_sync.sqlite"
    monkeypatch.setattr(lead_sync, "_DB_PATH", str(db_path), raising=False)
    monkeypatch.setenv("LEADS_API_BASE_URL", "https://example.com")

    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        return DummyResponse()

    monkeypatch.setattr(lead_sync.requests, "post", fake_post)

    state = {
        "budgetMin": 100000,
        "budgetMax": 200000,
        "preferredZones": ["Madrid"],
        "property_type": "inmueble_libre",
        "funding_mode": "mortgage_preapproved",
        "intent_type": "buyer",
        "understands_asset_conditions": True,
    }

    key = "5491111111111:interested:v1"

    ok1 = asyncio.run(lead_sync.sync_lead(state, "5491111111111", "interested", key))
    ok2 = asyncio.run(lead_sync.sync_lead(state, "5491111111111", "interested", key))

    assert ok1 is True
    assert ok2 is True
    assert calls["count"] == 1


def test_sync_lead_supabase_idempotent(monkeypatch, tmp_path):
    db_path = tmp_path / "lead_sync_supabase.sqlite"
    monkeypatch.setattr(lead_sync, "_DB_PATH", str(db_path), raising=False)
    monkeypatch.setenv("LEAD_SYNC_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_PROJECT_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")

    calls = {"count": 0, "url": None, "json": None, "headers": None}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["count"] += 1
        calls["url"] = url
        calls["json"] = json
        calls["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr(lead_sync.requests, "post", fake_post)

    state = {
        "budgetMin": 150000,
        "budgetMax": 250000,
        "preferredZones": ["Bogota"],
        "property_type": "apartment",
        "funding_mode": "own_capital",
        "intent_type": "investment",
        "understands_asset_conditions": True,
        "asked_to_be_contacted": True,
    }

    key = "lead:+573001112233:qualified:v2"

    ok1 = asyncio.run(lead_sync.sync_lead(state, "lead:+573001112233", "qualified", key))
    ok2 = asyncio.run(lead_sync.sync_lead(state, "lead:+573001112233", "qualified", key))

    assert ok1 is True
    assert ok2 is True
    assert calls["count"] == 1
    assert calls["url"] == "https://example.supabase.co/rest/v1/leads?on_conflict=phone"
    assert calls["json"]["phone"] == "+573001112233"
    assert calls["json"]["thread_id"] == "lead:+573001112233"
    assert calls["json"]["stage"] == "qualified"
    assert calls["json"]["interested"] is True
    assert calls["json"]["qualified"] is True
    assert calls["headers"]["apikey"] == "service-role"


def test_sync_lead_falls_back_to_supabase_when_api_backend_lacks_base_url(monkeypatch, tmp_path):
    db_path = tmp_path / "lead_sync_fallback.sqlite"
    monkeypatch.setattr(lead_sync, "_DB_PATH", str(db_path), raising=False)
    monkeypatch.setenv("LEAD_SYNC_BACKEND", "api")
    monkeypatch.delenv("LEADS_API_BASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_PROJECT_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")

    calls = {"count": 0, "url": None}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["count"] += 1
        calls["url"] = url
        return DummyResponse()

    monkeypatch.setattr(lead_sync.requests, "post", fake_post)

    ok = asyncio.run(
        lead_sync.sync_lead(
            {"preferredZones": ["Madrid"]},
            "lead:+34600111222",
            "interested",
            "lead:+34600111222:interested:v1",
        )
    )

    assert ok is True
    assert calls["count"] == 1
    assert calls["url"] == "https://example.supabase.co/rest/v1/leads?on_conflict=phone"


def test_sync_lead_accepts_supabase_alias_env_vars(monkeypatch, tmp_path):
    db_path = tmp_path / "lead_sync_alias.sqlite"
    monkeypatch.setattr(lead_sync, "_DB_PATH", str(db_path), raising=False)
    monkeypatch.setenv("LEAD_SYNC_BACKEND", "supabase")
    monkeypatch.delenv("SUPABASE_PROJECT_URL", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://alias.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "alias-service-role")

    calls = {"count": 0, "url": None, "headers": None}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["count"] += 1
        calls["url"] = url
        calls["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr(lead_sync.requests, "post", fake_post)

    ok = asyncio.run(
        lead_sync.sync_lead(
            {"preferredZones": ["Barcelona"]},
            "lead:+34900111222",
            "qualified",
            "lead:+34900111222:qualified:v1",
        )
    )

    assert ok is True
    assert calls["count"] == 1
    assert calls["url"] == "https://alias.supabase.co/rest/v1/leads?on_conflict=phone"
    assert calls["headers"]["apikey"] == "alias-service-role"

import sys
import types

sys.modules.setdefault("pytz", types.SimpleNamespace(timezone=lambda _: None))

from src.support.agent.nodes.conversation import tools


def test_asset_summary_is_natural_for_free_properties():
    summary = tools._build_asset_type_summary([{"asset_class": "libre"}, {"asset_class": "libre"}])

    assert "clasific" not in summary.lower()
    assert "viviendas libres" in summary.lower()


def test_busqueda_por_referencia_avoids_technical_label(monkeypatch):
    property_payload = {
        "reference": "REF-1",
        "propertyType": "flat",
        "location": {"city": "Madrid", "province": "Madrid", "zone": "Salamanca"},
        "operation": {"operationType": "sell", "pricing": {"price": 200000}},
        "area": {"area": 80},
        "features": {"bedrooms": 2, "bathrooms": 1, "condition": "good"},
        "descriptions": {"es": "Vivienda libre en buen estado"},
    }

    def fake_get_sync(endpoint, params=None):
        assert endpoint == "/property/ref/REF-1"
        return property_payload

    monkeypatch.setattr(tools, "_inmobigrama_get_sync", fake_get_sync)

    response = tools.buscar_inmueble_por_referencia.invoke({"referencia": "REF-1"})

    assert "Clasificación por descripción" not in response
    assert "vivienda libre" in response.lower()

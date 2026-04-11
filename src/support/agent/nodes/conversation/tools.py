from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
import json
import os
import httpx
import logging
import unicodedata
from typing import Optional, List
from collections import deque
import threading
import datetime
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)
MAX_VISIBLE_RESULTS = 3

_CESION_REMATE_KEYWORDS = (
    "venta de credito",
    "subasta",
    "cesion de remate",
)

_OCUPADA_KEYWORDS = (
    "ocupada",
    "vivienda ocupada",
)

_ASSET_CLASS_ES = {
    "cesion_remate": "cesión de remate",
    "ocupada": "vivienda ocupada",
    "libre": "vivienda libre",
}

_ASSET_CLASS_ES_PLURAL = {
    "cesion_remate": "cesiones de remate",
    "ocupada": "viviendas ocupadas",
    "libre": "viviendas libres",
}

# ============================================================
# Inmobigrama API Client
# ============================================================

INMOBIGRAMA_API_URL = os.getenv("INMOBIGRAMA_API_URL", "https://api.inmobigrama.com")
INMOBIGRAMA_API_KEY = os.getenv("X-API-Key", "")

if not INMOBIGRAMA_API_KEY:
    logger.warning("INMOBIGRAMA_API_KEY no está configurada - las búsquedas de propiedades fallarán")
else:
    logger.info(f"Inmobigrama API configurada: {INMOBIGRAMA_API_URL}")


def _get_inmobigrama_headers() -> dict:
    """Get headers for Inmobigrama API requests."""
    return {
        "X-API-Key": INMOBIGRAMA_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


def _fix_mojibake(text: str) -> str:
    """Intenta reparar textos UTF-8 mal interpretados."""
    current = text
    for _ in range(2):
        try:
            repaired = current.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if repaired == current:
            break
        if repaired.count("Ã") + repaired.count("Â") >= current.count("Ã") + current.count("Â"):
            break
        current = repaired
    return current


def _normalize_text_for_matching(text: str) -> str:
    fixed = _fix_mojibake(text or "")
    lowered = " ".join(fixed.split()).lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFD", lowered)
        if unicodedata.category(ch) != "Mn"
    )


def _classify_property_by_description(description: str) -> str:
    normalized = _normalize_text_for_matching(description)
    if any(keyword in normalized for keyword in _CESION_REMATE_KEYWORDS):
        return "cesion_remate"
    if any(keyword in normalized for keyword in _OCUPADA_KEYWORDS):
        return "ocupada"
    return "libre"


def _format_option_refs(indices: list[int]) -> str:
    if len(indices) == 1:
        return f"la opción {indices[0]}"
    if len(indices) == 2:
        return f"las opciones {indices[0]} y {indices[1]}"
    refs = ", ".join(str(i) for i in indices[:-1])
    return f"las opciones {refs} y {indices[-1]}"


def _build_asset_type_summary(properties: list[dict]) -> str:
    if not properties:
        return ""

    grouped: dict[str, list[int]] = {
        "cesion_remate": [],
        "ocupada": [],
        "libre": [],
    }
    for idx, prop in enumerate(properties, 1):
        asset_class = prop.get("asset_class", "libre")
        grouped.setdefault(asset_class, []).append(idx)

    non_empty_groups = [(asset_class, indices) for asset_class, indices in grouped.items() if indices]
    if len(non_empty_groups) == 1:
        only_class, _ = non_empty_groups[0]
        if only_class == "libre":
            return (
                "Y un detalle importante: todas las opciones que te compartí son viviendas libres, "
                "así que se pueden visitar y avanzar por una compra normal."
            )
        if only_class == "ocupada":
            return (
                "Y un detalle importante: todas las opciones son viviendas ocupadas, "
                "así que no se pueden visitar ni financiar con hipoteca tradicional."
            )
        return (
            "Y un detalle importante: todas las opciones son cesiones de remate, "
            "así que requieren liquidez y un proceso jurídico posterior."
        )

    parts = []
    for asset_class, indices in non_empty_groups:
        refs = _format_option_refs(indices)
        is_plural = len(indices) > 1
        label = (
            _ASSET_CLASS_ES_PLURAL.get(asset_class, "viviendas libres")
            if is_plural
            else _ASSET_CLASS_ES.get(asset_class, "vivienda libre")
        )
        verb = "son" if is_plural else "es"
        parts.append(f"{refs} {verb} {label}")
    return "Y como contexto importante sobre el tipo de activo, " + "; ".join(parts) + "."


def _normalize_property(item: dict) -> dict:
    operation = item.get("operation") or {}
    pricing = operation.get("pricing") or {}
    location = item.get("location") or {}
    area = item.get("area") or {}
    features = item.get("features") or {}
    descriptions = item.get("descriptions") or {}

    description_text = ""
    if isinstance(descriptions, dict):
        description_text = descriptions.get("es") or descriptions.get("en") or ""
    elif isinstance(descriptions, str):
        description_text = descriptions
    if not description_text:
        description_text = item.get("description", "") or ""

    return {
        "reference": item.get("reference"),
        "property_type": item.get("propertyType"),
        "city": location.get("city"),
        "province": location.get("province"),
        "zone": location.get("zone"),
        "price": pricing.get("price"),
        "price_period": pricing.get("pricePeriod"),
        "operation_type": operation.get("operationType"),
        "area_m2": area.get("area"),
        "plot_area": area.get("plotArea"),
        "bedrooms": features.get("bedrooms"),
        "bathrooms": features.get("bathrooms"),
        "condition": features.get("condition"),
        "elevator": features.get("elevator"),
        "garage": features.get("garage"),
        "pool": features.get("pool"),
        "terrace": features.get("terrace"),
        "garden": features.get("garden"),
        "air_conditioning": features.get("airConditioning"),
        "heating": features.get("heating"),
        "storage": features.get("storageRoom"),
        "description": description_text,
        "asset_class": _classify_property_by_description(description_text),
    }


async def _inmobigrama_get(endpoint: str, params: dict = None) -> dict:
    """Make GET request to Inmobigrama API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{INMOBIGRAMA_API_URL}{endpoint}",
            headers=_get_inmobigrama_headers(),
            params=params
        )
        response.raise_for_status()
        return response.json()


async def _inmobigrama_post(endpoint: str, data: dict, params: dict = None) -> dict:
    """Make POST request to Inmobigrama API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{INMOBIGRAMA_API_URL}{endpoint}",
            headers=_get_inmobigrama_headers(),
            json=data,
            params=params
        )
        response.raise_for_status()
        return response.json()


def _inmobigrama_get_sync(endpoint: str, params: dict = None) -> dict:
    """Make synchronous GET request to Inmobigrama API."""
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{INMOBIGRAMA_API_URL}{endpoint}",
            headers=_get_inmobigrama_headers(),
            params=params
        )
        response.raise_for_status()
        return response.json()


def _inmobigrama_post_sync(endpoint: str, data: dict, params: dict = None) -> dict:
    """Make synchronous POST request to Inmobigrama API."""
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{INMOBIGRAMA_API_URL}{endpoint}",
            headers=_get_inmobigrama_headers(),
            json=data,
            params=params
        )
        response.raise_for_status()
        return response.json()


# ============================================================
# Pending Images Queue (for sending images after tool response)
# ============================================================

_pending_images: deque = deque(maxlen=100)
_pending_images_lock = threading.Lock()


def queue_image_for_sending(base64_data: str, caption: str):
    """Queue an image to be sent after the tool response."""
    with _pending_images_lock:
        _pending_images.append({"base64": base64_data, "caption": caption})


def get_pending_images() -> list:
    """Get and clear all pending images."""
    with _pending_images_lock:
        images = list(_pending_images)
        _pending_images.clear()
        return images


# ============================================================
# Utility Tools
# ============================================================

@tool
def obtener_hora_actual() -> str:
    """Obtiene la fecha y hora actual (zona horaria Europe/Madrid).
    Útil para responder preguntas como '¿qué hora es?', '¿qué día es hoy?'.
    
    Returns:
        String con la fecha y hora formateada.
    """
    tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(tz)
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    
    dia_semana = dias[now.weekday()]
    dia = now.day
    mes = meses[now.month - 1]
    anio = now.year
    hora = now.strftime("%H:%M")
    
    return f"{dia_semana}, {dia} de {mes} de {anio}, a las {hora}."


@tool
def realizar_calculo(expression: str) -> str:
    """Realiza cálculos matemáticos simples (suma, resta, multiplicación, división, porcentajes).
    Útil para calcular hipotecas, superficies, precios por metro cuadrado, comisiones, etc.
    
    Args:
        expression: La expresión matemática a evaluar (ej: "300000 * 0.10", "1500 / 70").
                    Soporta +, -, *, /, %, (, ).
    
    Returns:
        El resultado del cálculo o un mensaje de error.
    """
    try:
        allowed_chars = "0123456789.+-*/%() "
        if not all(c in allowed_chars for c in expression):
            return "Error: La expresión contiene caracteres no permitidos."
            
        result = eval(expression, {"__builtins__": None}, {})
        
        if isinstance(result, (int, float)):
            if result == int(result):
                return str(int(result))
            return f"{result:.2f}"
            
        return str(result)
        
    except Exception as e:
        return f"Error al realizar el cálculo: {str(e)}"


@tool
def buscar_info_viviendas(query: str) -> str:
    """Busca información en la knowledge base sobre tipos de viviendas y productos inmobiliarios.
    
    Args:
        query: Consulta sobre tipos de viviendas (Cesión de Remate, NPL, Ocupados, etc.)
        
    Returns:
        Información encontrada en la knowledge base
    """
    _ = query
    return (
        "La base documental de viviendas no está disponible ahora mismo. "
        "Puedo ayudarte con búsqueda de inmuebles concretos por zona, precio y tipo."
    )


# ============================================================
# Inmobigrama Property Tools
# ============================================================

@tool
def consultar_inmuebles(
    zona: Optional[str] = None,
    provincia: Optional[str] = None,
    tipo_propiedad: Optional[str] = None,
    operacion: Optional[str] = None,
    precio_min: Optional[int] = None,
    precio_max: Optional[int] = None,
    habitaciones_min: Optional[int] = None,
    banos_min: Optional[int] = None,
    metros_min: Optional[int] = None,
    metros_max: Optional[int] = None,
    con_ascensor: Optional[bool] = None,
    con_garaje: Optional[bool] = None,
    con_piscina: Optional[bool] = None,
    con_terraza: Optional[bool] = None,
    con_jardin: Optional[bool] = None,
    limite: int = 3
) -> str:
    """Busca inmuebles en una zona o localidad específica.
    
    IMPORTANTE: Usa el parámetro 'zona' para buscar en cualquier ubicación específica:
    pueblos, ciudades, barrios, urbanizaciones, etc.
    
    Args:
        zona: OBLIGATORIO para búsquedas por ubicación. Ejemplos:
            - Pueblos: "Cenicientos", "Nuevo Baztan", "Villanueva del Pardillo"
            - Barrios: "Salamanca", "Chamberí", "Lavapiés", "Malasaña"
            - Ciudades: "Alcalá de Henares", "Getafe", "Móstoles"
            - Urbanizaciones: "La Moraleja", "Pozuelo de Alarcón"
        provincia: Provincia (ej: "Madrid", "Barcelona"). Opcional, ayuda a filtrar.
        tipo_propiedad: piso, casa, chalet, duplex, ático, estudio, local, terreno
        operacion: venta, alquiler, traspaso
        precio_min: Precio mínimo en euros
        precio_max: Precio máximo en euros
        habitaciones_min: Mínimo de habitaciones
        banos_min: Mínimo de baños
        metros_min: Metros cuadrados mínimos
        metros_max: Metros cuadrados máximos
        con_ascensor: Filtrar por ascensor
        con_garaje: Filtrar por garaje
        con_piscina: Filtrar por piscina
        con_terraza: Filtrar por terraza
        con_jardin: Filtrar por jardín
        limite: Resultados a mostrar (defecto 3)
    
    Returns:
        Lista de inmuebles encontrados.
    """
    try:
        params = {"page": 1, "state": "published"}
        
        if zona:
            params["zone"] = zona
            logger.info(f"Buscando en zona: {zona}")
        if provincia:
            params["province"] = provincia
        if tipo_propiedad:
            tipo_map = {
                "piso": "flat", "apartamento": "apartment", "casa": "house",
                "ático": "penthouse", "atico": "penthouse", "estudio": "studio",
                "local": "commercial_space", "nave": "industrial_warehouse",
                "terreno": "land", "habitación": "room", "habitacion": "room"
            }
            params["propertyType"] = tipo_map.get(tipo_propiedad.lower(), tipo_propiedad)
        if operacion:
            op_map = {"venta": "sell", "alquiler": "rent", "traspaso": "transfer"}
            params["operation"] = op_map.get(operacion.lower(), operacion)
        if precio_min:
            params["priceMin"] = precio_min
        if precio_max:
            params["priceMax"] = precio_max
        if habitaciones_min:
            params["minRooms"] = habitaciones_min
        if banos_min:
            params["minBathrooms"] = banos_min
        if metros_min:
            params["minArea"] = metros_min
        if metros_max:
            params["maxArea"] = metros_max
        if con_ascensor is not None:
            params["hasElevator"] = con_ascensor
        if con_garaje is not None:
            params["hasGarage"] = con_garaje
        if con_piscina is not None:
            params["hasPool"] = con_piscina
        if con_terraza is not None:
            params["hasTerrace"] = con_terraza
        if con_jardin is not None:
            params["hasGarden"] = con_jardin
        
        logger.info(f"Consultando inmuebles con params: {params}")
        result = _inmobigrama_get_sync("/properties", params)
        
        properties = result.get("properties", [])
        total = result.get("total", 0)
        
        if not properties:
            filtros = []
            if provincia:
                filtros.append(f"provincia={provincia}")
            if zona:
                filtros.append(f"zona={zona}")
            if tipo_propiedad:
                filtros.append(f"tipo={tipo_propiedad}")
            if precio_max:
                filtros.append(f"precio_max={precio_max}€")
            filtros_str = ", ".join(filtros) if filtros else "los criterios especificados"
            return f"No se encontraron inmuebles con {filtros_str}. Puedes intentar ampliar los criterios de búsqueda."
        
        limite = min(limite, MAX_VISIBLE_RESULTS)
        properties = properties[:limite]
        normalized_properties = [_normalize_property(prop) for prop in properties]

        response_parts = []
        
        for i, prop in enumerate(normalized_properties, 1):
            ref = prop.get("reference", "N/A")
            prop_type = prop.get("property_type", "inmueble")
            
            city = prop.get("city", "")
            province = prop.get("province", "")
            zone = prop.get("zone", "")
            ubicacion = city if city else province
            if zone:
                ubicacion = f"{zone}, {ubicacion}"
            
            op_type = prop.get("operation_type", "")
            price = prop.get("price", 0)
            period = prop.get("price_period", "")
            
            op_text = "en venta" if op_type == "sell" else "en alquiler" if op_type == "rent" else "en traspaso"
            price_text = f"{price:,}€".replace(",", ".")
            if period == "month":
                price_text += "/mes"
            elif period == "day":
                price_text += "/día"
            
            area = prop.get("area_m2", 0)
            plot_area = prop.get("plot_area", 0)
            
            bedrooms = prop.get("bedrooms", 0)
            bathrooms = prop.get("bathrooms", 0)
            elevator = prop.get("elevator", False)
            pool = prop.get("pool", "")
            terrace = prop.get("terrace", False)
            garden = prop.get("garden", False)
            garage = prop.get("garage", False)
            air_conditioning = prop.get("air_conditioning", "")
            heating = prop.get("heating", "")
            storage = prop.get("storage", False)
            condition = prop.get("condition", "")
            
            description = prop.get("description", "")
            if description and len(description) > 200:
                description = description[:200].rsplit(" ", 1)[0] + "..."
            
            tipo_map = {
                "flat": "piso", "apartment": "apartamento", "house": "casa",
                "chalet": "chalet", "duplex": "dúplex", "penthouse": "ático",
                "studio": "estudio", "office": "oficina", "commercial_space": "local comercial",
                "garage": "garaje", "land": "terreno", "industrial_warehouse": "nave",
                "room": "habitación", "villa": "villa", "bungalow": "bungalow"
            }
            tipo_es = tipo_map.get(prop_type, prop_type)
            condition_map = {
                "new": "a estrenar",
                "good": "buen estado",
                "to_renovate": "para reformar",
                "renovated": "reformado"
            }
            estado = condition_map.get(condition, "")
            
            extras = []
            if pool and pool not in ["no", "false", False, None, ""]:
                pool_type = "piscina comunitaria" if pool == "communitary" else "piscina"
                extras.append(pool_type)
            if terrace and terrace not in ["no", "false", False, None, ""]:
                extras.append("terraza")
            if garden and garden not in ["no", "false", False, None, ""]:
                extras.append("jardín")
            if garage and garage not in ["no", "false", False, None, "", 0]:
                extras.append("garaje")
            if elevator and elevator not in ["no", "false", False, None, ""]:
                extras.append("ascensor")
            if air_conditioning and air_conditioning not in ["no", "not_specified", "false", False, None, ""]:
                extras.append("aire acondicionado")
            if heating and heating not in ["no", "not_specified", "false", False, None, ""]:
                extras.append("calefacción")
            if storage and storage not in ["no", "false", False, None, ""]:
                extras.append("trastero")
            
            prop_text = f"{i}. {tipo_es.capitalize()} en {ubicacion}\n"
            prop_text += f"Ref: {ref}\n"
            prop_text += f"Precio: {price_text} {op_text}\n"
            
            specs_parts = []
            if area:
                specs_parts.append(f"{area}m²")
            if bedrooms:
                hab_text = "habitación" if bedrooms == 1 else "habitaciones"
                specs_parts.append(f"{bedrooms} {hab_text}")
            if bathrooms:
                bath_text = "baño" if bathrooms == 1 else "baños"
                specs_parts.append(f"{bathrooms} {bath_text}")
            if plot_area and plot_area != area:
                specs_parts.append(f"parcela de {plot_area}m²")
            if estado:
                specs_parts.append(estado)
            
            if specs_parts:
                prop_text += f"{', '.join(specs_parts)}\n"
            
            if extras:
                prop_text += f"Tiene: {', '.join(extras)}\n"
            
            if description:
                prop_text += f"{description}\n"

            response_parts.append(prop_text)
        
        asset_summary = _build_asset_type_summary(normalized_properties)
        if asset_summary:
            response_parts.append(asset_summary)

        if total > limite:
            response_parts.append(f"Tengo {total - limite} opciones más si te interesa ver otras.")
        
        return "\n".join(response_parts)
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Error HTTP al consultar inmuebles: {e}")
        if e.response.status_code == 401:
            return "Error de autenticación con el sistema de inmuebles. Por favor, contacta con soporte."
        return "Hubo un problema al consultar los inmuebles. Por favor, intenta de nuevo más tarde."
    except Exception as e:
        logger.error(f"Error al consultar inmuebles: {e}")
        return "No pude consultar los inmuebles en este momento. Por favor, intenta de nuevo más tarde."


@tool
def buscar_inmueble_por_referencia(referencia: str) -> str:
    """Busca un inmueble específico por su código de referencia.
    
    Args:
        referencia: Código de referencia del inmueble (ej: "1052-RED-37488", "A1001")
    
    Returns:
        Información detallada del inmueble.
    """
    try:
        logger.info(f"Buscando inmueble con referencia: {referencia}")
        
        prop = None
        try:
            prop = _inmobigrama_get_sync(f"/property/ref/{referencia}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                result = _inmobigrama_get_sync("/properties", {"reference": referencia, "state": "published"})
                properties = result.get("properties", [])
                if properties:
                    prop = properties[0]
        
        if not prop:
            return f"No encontré ningún inmueble con la referencia '{referencia}'. Verifica que el código sea correcto."
        
        normalized = _normalize_property(prop)

        ref = prop.get("reference", referencia)
        prop_type = normalized.get("property_type", "inmueble")
        
        location = prop.get("location", {})
        city = normalized.get("city", "")
        province = normalized.get("province", "")
        zone = normalized.get("zone", "")
        street = location.get("street", "")
        floor = location.get("floor", "")
        
        operation = prop.get("operation", {})
        op_type = normalized.get("operation_type", "")
        pricing = operation.get("pricing", {})
        price = normalized.get("price", 0)
        original_price = pricing.get("originalPrice", 0)
        period = normalized.get("price_period", "")
        
        area_data = prop.get("area", {})
        area = normalized.get("area_m2", 0)
        usable_area = area_data.get("usableArea", 0)
        plot_area = normalized.get("plot_area", 0)
        
        features = prop.get("features", {})
        bedrooms = normalized.get("bedrooms", 0)
        bathrooms = normalized.get("bathrooms", 0)
        toilets = features.get("toilets", 0)
        elevator = normalized.get("elevator", False)
        condition = normalized.get("condition", "")
        furnished = features.get("furnished", False)
        air_conditioning = normalized.get("air_conditioning", "")
        heating = normalized.get("heating", "")
        pool = normalized.get("pool", "")
        garage = features.get("garages", 0)
        storage = normalized.get("storage", False)
        terrace = features.get("numberOfTerraces", 0)
        garden = normalized.get("garden", False)
        community_fees = features.get("communityFees", 0)
        
        desc_es = normalized.get("description", "")
        if not desc_es:
            desc_es = prop.get("description", "")
        
        tipo_map = {
            "flat": "piso", "apartment": "apartamento", "house": "casa",
            "chalet": "chalet", "duplex": "dúplex", "penthouse": "ático",
            "studio": "estudio", "office": "oficina", "commercial_space": "local comercial",
            "garage": "garaje", "land": "terreno", "industrial_warehouse": "nave industrial",
            "room": "habitación", "villa": "villa", "bungalow": "bungalow"
        }
        tipo_es = tipo_map.get(prop_type, prop_type)
        
        condition_map = {
            "new": "nuevo", "good": "buen estado", "renovated": "reformado",
            "semi_renovated": "semi-reformado", "to_renovate": "para reformar",
            "original_state": "estado original"
        }
        condition_es = condition_map.get(condition, "")
        
        op_text = "en venta" if op_type == "sell" else "en alquiler" if op_type == "rent" else "en traspaso"
        price_text = f"{price:,}€".replace(",", ".")
        if period == "month":
            price_text += "/mes"
        
        ubicacion = city
        if zone:
            ubicacion = f"{zone}, {city}"
        if province and province != city:
            ubicacion += f", {province}"
        
        response = f"{tipo_es.capitalize()} en {ubicacion}\n"
        response += f"Referencia: {ref}\n"
        response += f"Precio: {price_text} {op_text}\n"
        if original_price and original_price != price:
            orig_text = f"{original_price:,}€".replace(",", ".")
            response += f"Precio original: {orig_text}\n"
        
        response += f"\nSuperficie: {area}m²"
        if usable_area and usable_area != area:
            response += f" ({usable_area}m² útiles)"
        response += "\n"
        if plot_area and plot_area != area:
            response += f"Parcela: {plot_area}m²\n"
        
        if bedrooms:
            hab_text = "habitación" if bedrooms == 1 else "habitaciones"
            response += f"{bedrooms} {hab_text}\n"
        if bathrooms:
            bath_text = "baño" if bathrooms == 1 else "baños"
            response += f"{bathrooms} {bath_text}\n"
        if toilets:
            response += f"{toilets} aseo(s)\n"
        
        extras = []
        if elevator and elevator not in ["no", "false", False, None, ""]:
            extras.append("ascensor")
        if furnished and furnished not in ["no", "false", False, None, ""]:
            extras.append("amueblado")
        if air_conditioning and air_conditioning not in ["not_specified", "no", "false", False, None, ""]:
            extras.append("aire acondicionado")
        if heating and heating not in ["not_specified", "no", "false", False, None, ""]:
            extras.append("calefacción")
        if pool and pool not in ["no", "false", False, None, ""]:
            pool_text = "piscina comunitaria" if pool == "communitary" else "piscina"
            extras.append(pool_text)
        if garage and garage not in [0, "0", "no", "false", False, None, ""]:
            extras.append(f"{garage} plaza(s) de garaje")
        if storage and storage not in ["no", "false", False, None, ""]:
            extras.append("trastero")
        if terrace and terrace not in [0, "0", "no", "false", False, None, ""]:
            extras.append(f"{terrace} terraza(s)")
        if garden and garden not in ["no", "false", False, None, ""]:
            extras.append("jardín")
        
        if extras:
            response += f"\nCaracterísticas: {', '.join(extras)}\n"
        
        if condition_es:
            response += f"Estado: {condition_es}\n"
        
        if community_fees:
            response += f"Gastos comunidad: {community_fees}€/mes\n"
        
        if street:
            response += f"\nUbicación: {street}"
            if floor:
                response += f", planta {floor}"
            response += "\n"
        
        if desc_es:
            desc_short = desc_es[:400] + "..." if len(desc_es) > 400 else desc_es
            response += f"\n{desc_short}\n"

        asset_class = normalized.get("asset_class", "libre")
        if asset_class == "libre":
            response += (
                "\nDetalle importante: es una vivienda libre, así que se puede visitar "
                "y encaja mejor en una compra tradicional.\n"
            )
        elif asset_class == "ocupada":
            response += (
                "\nDetalle importante: es una vivienda ocupada, así que no se puede visitar "
                "ni financiar con hipoteca tradicional.\n"
            )
        else:
            response += (
                "\nDetalle importante: es una cesión de remate, así que requiere liquidez "
                "y un proceso jurídico posterior.\n"
            )
        
        return response
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Error HTTP al buscar inmueble: {e}")
        if e.response.status_code == 404:
            return f"No se encontró ningún inmueble con la referencia '{referencia}'."
        return "Hubo un problema al buscar el inmueble. Por favor, intenta de nuevo."
    except Exception as e:
        logger.error(f"Error al buscar inmueble por referencia: {e}")
        return "No pude buscar el inmueble en este momento. Por favor, intenta de nuevo."


@tool
def listar_ubicaciones_disponibles(provincia: Optional[str] = None) -> str:
    """Lista las provincias y ciudades disponibles en el sistema.
    
    Args:
        provincia: Si se especifica, muestra solo las ciudades de esa provincia.
                  Si no se especifica, muestra todas las provincias disponibles.
    
    Returns:
        Lista de ubicaciones disponibles.
    """
    try:
        params = {}
        if provincia:
            params["province"] = provincia
        
        logger.info(f"Consultando ubicaciones con params: {params}")
        result = _inmobigrama_get_sync("/populations", params)
        
        if not result:
            if provincia:
                return f"No se encontró la provincia '{provincia}'. Verifica el nombre e intenta de nuevo."
            return "No se encontraron ubicaciones disponibles."
        
        if provincia:
            for country, provinces in result.items():
                if provincia in provinces:
                    cities = provinces[provincia]
                    if isinstance(cities, list):
                        cities_text = ", ".join(cities[:20])
                        if len(cities) > 20:
                            cities_text += f"... y {len(cities) - 20} más"
                        return f"**Ciudades en {provincia}:**\n{cities_text}"
            return f"No se encontraron ciudades en la provincia '{provincia}'."
        else:
            response = "**Provincias disponibles:**\n"
            for country, provinces in result.items():
                province_list = list(provinces.keys())
                response += f"\n🇪🇸 **{country}:**\n"
                response += ", ".join(sorted(province_list)[:30])
                if len(province_list) > 30:
                    response += f"... y {len(province_list) - 30} más"
            return response
            
    except httpx.HTTPStatusError as e:
        logger.error(f"Error HTTP al listar ubicaciones: {e}")
        if e.response.status_code == 404:
            return f"No se encontró la provincia '{provincia}'."
        return "Hubo un problema al consultar las ubicaciones."
    except Exception as e:
        logger.error(f"Error al listar ubicaciones: {e}")
        return "No pude consultar las ubicaciones en este momento."


@tool
def registrar_interes_cliente(
    nombre: str,
    telefono: str,
    email: Optional[str] = None,
    titulo_lead: Optional[str] = None,
    comentarios: Optional[str] = None,
    provincia: Optional[str] = None,
    ciudad: Optional[str] = None
) -> str:
    """Registra el interés de un cliente potencial creando un lead en el sistema.
    Usar cuando un cliente muestra interés real en comprar/alquilar y proporciona sus datos.
    
    Args:
        nombre: Nombre completo del cliente
        telefono: Número de teléfono (con o sin código de país)
        email: Correo electrónico (opcional)
        titulo_lead: Título descriptivo del lead (ej: "Interesado en piso centro Madrid")
        comentarios: Notas adicionales sobre el interés del cliente
        provincia: Provincia de interés
        ciudad: Ciudad de interés
    
    Returns:
        Confirmación del registro.
    """
    try:
        phone_clean = telefono.replace(" ", "").replace("-", "")
        if phone_clean.startswith("+"):
            phone_clean = phone_clean[1:]
        
        country_code = "34"
        phone_number = phone_clean
        if len(phone_clean) > 9:
            country_code = phone_clean[:2] if phone_clean[:2] in ["34", "57", "52", "54"] else "34"
            phone_number = phone_clean[len(country_code):]
        
        person_data = {
            "name": nombre,
            "phone1": {
                "countryCode": country_code,
                "number": phone_number
            }
        }
        if email:
            person_data["email1"] = email
        
        logger.info(f"Creando persona: {nombre}")
        person_result = _inmobigrama_post_sync("/person", person_data)
        person_id = person_result.get("person", {}).get("id")
        
        if not person_id:
            return "Hubo un problema al registrar el contacto. Por favor, intenta de nuevo."
        
        lead_title = titulo_lead or f"Lead desde WhatsApp - {nombre}"
        lead_data = {
            "title": lead_title,
            "possibility": 3,
            "status": "active"
        }
        
        if provincia or ciudad:
            lead_data["location"] = {}
            if provincia:
                lead_data["location"]["province"] = provincia
            if ciudad:
                lead_data["location"]["city"] = ciudad
        
        if comentarios:
            lead_data["comments"] = comentarios
        
        logger.info(f"Creando lead para persona {person_id}")
        lead_result = _inmobigrama_post_sync("/lead", lead_data, params={"sellers[]": person_id})
        lead_id = lead_result.get("lead", {}).get("id")
        
        if lead_id:
            return f"¡Perfecto! He registrado tu interés. Un asesor se pondrá en contacto contigo pronto. (Ref: L{lead_id})"
        else:
            return f"He registrado tu contacto. Un asesor se comunicará contigo pronto."
            
    except httpx.HTTPStatusError as e:
        logger.error(f"Error HTTP al registrar interés: {e}")
        return "Hubo un problema técnico al registrar tu interés. Por favor, proporciona tus datos de nuevo o llámanos directamente."
    except Exception as e:
        logger.error(f"Error al registrar interés del cliente: {e}")
        return "No pude registrar tu interés en este momento. Por favor, intenta de nuevo o llámanos directamente."


# ============================================================
# Conversation Management Tools
# ============================================================

@tool
def finalizar_conversacion(motivo: str) -> str:
    """
    Finaliza la conversación con el usuario.
    
    Args:
        motivo: Razón del cierre (spam, solicitud del usuario, conversación completada, etc.)
        
    Returns:
        Mensaje de confirmación
    """
    return f"Conversación finalizada. Motivo: {motivo}"

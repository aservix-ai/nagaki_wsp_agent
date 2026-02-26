

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from src.support.agent.nodes.conversation.rag import get_rag_system
from src.support.agent.nodes.conversation.prompt import CALIFICATION_SYSTEM_PROMPT, DB_QUERIES_PROMPT
from src.support.agent.nodes.conversation.db_utils import execute_structured_query, clean_price
from src.support.agent.nodes.conversation.property_api_client import get_api_client
from src.support.agent.nodes.conversation.leads_api_client import get_leads_api_client
import json
import base64
import os
from typing import Optional, List
from collections import deque
import threading

# Global queue for pending images to send (thread-safe)
# Format: {"phone": phone_number, "base64": data, "caption": text}
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
import datetime
from datetime import datetime
import pytz

@tool
def obtener_hora_actual() -> str:
    """Obtiene la fecha y hora actual (zona horaria Europe/Madrid).
    Útil para responder preguntas como '¿qué hora es?', '¿qué día es hoy?'.
    
    Returns:
        String con la fecha y hora formateada.
    """
    tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(tz)
    # Formato natural: Jueves, 08 de Enero de 2026, 15:30
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
        # Sanitización básica por seguridad
        allowed_chars = "0123456789.+-*/%() "
        if not all(c in allowed_chars for c in expression):
            return "Error: La expresión contiene caracteres no permitidos. Solo se permiten números y operadores matemáticos básicos."
            
        # Evaluar la expresión
        # Usamos eval() con un entorno restringido por seguridad, aunque la validación anterior ya filtra bastante.
        result = eval(expression, {"__builtins__": None}, {})
        
        # Formatear el resultado si es un número
        if isinstance(result, (int, float)):
            # Si es entero, mostrar sin decimales
            if result == int(result):
                return str(int(result))
            # Si tiene decimales, limitar a 2
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
    # Obtener el sistema RAG
    rag = get_rag_system()
    
    # Buscar en la knowledge base
    results = rag.search(query, k=3)
    
    if not results:
        return f"No se encontró información sobre '{query}'."
    
    response_parts = []
    for i, doc in enumerate(results, 1):
        source = doc.metadata.get("source", "Documento")
        content = doc.page_content.strip()
        response_parts.append(f"[{i}] {source}:\n{content}\n")
    
    return "\n".join(response_parts)


# Modelo Pydantic para salida estructurada
class AnalisisIntencion(BaseModel):
    """Estructura de salida para el análisis de intención."""
    score: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Probabilidad de compra entre 0.0 y 1.0"
    )
    razonamiento: str = Field(
        ..., 
        description="Breve explicación de por qué se asignó este score"
    )
    es_cualificado: bool = Field(
        ..., 
        description="True si el score es >= 0.8"
    )


@tool
def identificar_intencion(mensaje_usuario: str) -> dict:
    """
    Analiza el mensaje del usuario para determinar su nivel de interés e intención de compra.
    """
    
    # Prompt optimizado para el negocio de activos singulares de Grupo Nagaki
    system_prompt = CALIFICATION_SYSTEM_PROMPT
    # LLM con Structured Output (garantiza JSON válido)
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0
    ).with_structured_output(AnalisisIntencion)
    
    # Prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{mensaje}")
    ])
    
    # Cadena
    chain = prompt | llm
    
    try:
        # Invocar y obtener resultado estructurado
        resultado: AnalisisIntencion = chain.invoke({"mensaje": mensaje_usuario})
        
        # Calcular puntos según rangos
        score = resultado.score
        if score < 0.1:
            puntos = 0
        elif score < 0.26:
            puntos = 1
        elif score < 0.51:
            puntos = 2
        elif score < 0.76:
            puntos = 3
        else:
            puntos = 4
        
        return {
            "score": resultado.score,
            "razonamiento": resultado.razonamiento,
            "puntos_sumados": puntos
        }
        
    except Exception as e:
        print(f"Error al analizar intención: {e}")
        return {
            "error": str(e),
            "score": 0.0,
            "razonamiento": "Error en el análisis",
            "puntos_sumados": 0
        }




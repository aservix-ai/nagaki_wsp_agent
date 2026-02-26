"""
Herramientas para el nodo de clasificación de usuario - Grupo Nagaki
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from src.support.agent.nodes.classify_user.prompt import TOOL_SYSTEM_PROMPT


# ============================================================================
# MODELO PYDANTIC PARA STRUCTURED OUTPUT
# ============================================================================

class RespuestaCalificacion(BaseModel):
    """Estructura de salida para la calificación de respuestas."""
    
    es_positiva: bool = Field(
        ...,
        description="True si la respuesta es afirmativa/positiva, False si es negativa o evasiva"
    )
    razonamiento: str = Field(
        ...,
        description="Breve explicación de por qué se consideró positiva o negativa"
    )
    puntos_sumados: int = Field(
        ...,
        ge=0,
        le=1,
        description="1 si es positiva, 0 si es negativa"
    )


# ============================================================================
# TOOL DE CALIFICACIÓN DE RESPUESTAS
# ============================================================================

@tool
def calificar_respuesta_usuario(
    pregunta: str,
    respuesta_usuario: str,
    contexto: str = ""
) -> dict:
    """
    Califica si la respuesta del usuario a una pregunta de clasificación es positiva o negativa.
    
    Esta herramienta analiza la respuesta del cliente a las 3 preguntas de cualificación:
    1. ¿Tiene capital disponible?
    2. ¿Acepta las condiciones del tipo de inmueble?
    3. ¿Vive en España?
    
    Args:
        pregunta: La pregunta que se le hizo al usuario
        respuesta_usuario: La respuesta completa del usuario
        contexto: Contexto adicional de la conversación (opcional)
        
    Returns:
        dict: {
            "es_positiva": bool (True si acepta/tiene, False si no),
            "razonamiento": str (explicación de la decisión),
            "puntos_sumados": int (1 si positiva, 0 si negativa)
        }
    """
    
    system_prompt = TOOL_SYSTEM_PROMPT
    # LLM con Structured Output
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0
    ).with_structured_output(RespuestaCalificacion)
    
    # Construir el mensaje
    if contexto:
        user_message = f"""PREGUNTA: {pregunta}

RESPUESTA DEL USUARIO: {respuesta_usuario}

CONTEXTO ADICIONAL: {contexto}"""
    else:
        user_message = f"""PREGUNTA: {pregunta}

RESPUESTA DEL USUARIO: {respuesta_usuario}"""
    
    # Prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", user_message)
    ])
    
    # Cadena
    chain = prompt | llm
    
    try:
        # Invocar y obtener resultado estructurado
        resultado: RespuestaCalificacion = chain.invoke({})
        
        # Retornar diccionario limpio
        return {
            "es_positiva": resultado.es_positiva,
            "razonamiento": resultado.razonamiento,
            "puntos_sumados": resultado.puntos_sumados
        }
        
    except Exception as e:
        print(f"Error al calificar respuesta: {e}")
        return {
            "error": str(e),
            "es_positiva": False,
            "razonamiento": "Error en el análisis",
            "puntos_sumados": 0
        }




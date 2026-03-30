"""
Evolution API Webhook para integración con WhatsApp - Grupo Nagaki

Este módulo proporciona un webhook para recibir mensajes de WhatsApp vía Evolution API
y responder usando el mismo agente LangGraph que usa Vapi.

CONFIGURACIÓN (Variables de Entorno):
- EVOLUTION_API_URL: URL base de Evolution API (default: http://localhost:8080)
- EVOLUTION_API_KEY: API Key de Evolution API
- EVOLUTION_INSTANCE: Nombre de la instancia de Evolution API
- EVOLUTION_WEBHOOK_PORT: Puerto del webhook (default: 3000)

FLUJO:
1. Usuario envía mensaje de WhatsApp
2. Evolution API envía POST a /webhook/message
3. Webhook procesa el mensaje con el agente
4. Envía respuesta vía Evolution API
5. Ejecuta tareas de background (puntos)
"""

import json
import logging
import os
import re
import sys
import asyncio
import random
import time
import httpx
from typing import Optional, Dict, Any
from collections import OrderedDict
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from src.support.agent import Agent
# Background tasks de calificación deshabilitados temporalmente
# from src.support.agent.background_tasks import update_points_background, qualify_response_background
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from src.support.agent.qualification import (
    get_default_snapshot,
    load_qualification_snapshot,
    publish_qualification_event,
)
from src.support.agent.qualification.store import next_turn_id

# Importar nuevas utilidades
from src.support.utils.whatsapp_formatter import format_for_whatsapp
from src.support.utils.text_normalizer import normalize_text
from src.support.utils.audio import download_audio, transcribe_audio, generate_voice, save_base64_audio
from src.support.utils.delay_manager import ThinkingDelayManager
from src.support.utils.spam_detector import spam_detector

import uuid
from pathlib import Path


# ============================================================
# CACHÉ DE DEDUPLICACIÓN DE MENSAJES
# ============================================================
# Evolution API puede enviar el mismo webhook múltiples veces
# Usamos una caché con TTL para evitar procesar duplicados

class MessageDeduplicationCache:
    """Caché simple para deduplicar mensajes por ID con TTL."""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
    
    def is_duplicate(self, message_id: str) -> bool:
        """Verifica si el mensaje ya fue procesado (y no expiró)."""
        current_time = time.time()
        
        # Limpiar entradas expiradas
        self._cleanup(current_time)
        
        if message_id in self._cache:
            return True
        
        # Agregar a la caché
        self._cache[message_id] = current_time
        
        # Limitar tamaño
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        
        return False
    
    def _cleanup(self, current_time: float):
        """Elimina entradas expiradas."""
        expired = [
            msg_id for msg_id, timestamp in self._cache.items()
            if current_time - timestamp > self._ttl
        ]
        for msg_id in expired:
            del self._cache[msg_id]


# Instancia global de la caché (TTL de 5 minutos, máximo 1000 mensajes)
message_cache = MessageDeduplicationCache(max_size=1000, ttl_seconds=300)


# ============================================================================
# TAREA DE PROCESAMIENTO ASÍNCRONO (PARA EVITAR TIMEOUTS)
# ============================================================================

async def process_whatsapp_task(
    phone_number: str,
    normalized_text: str,
    agent: Agent,
    background_tasks: BackgroundTasks,
    thread_id: Optional[str] = None,
    audio_url: Optional[str] = None,
    audio_base64: Optional[str] = None
):
    """
    Tarea que se ejecuta en segundo plano para procesar el mensaje con el agente
    y enviar la respuesta, evitando bloquear el webhook y causar timeouts.
    """
    thread_id = thread_id or canonical_thread_id(phone_number)
    user_lock = await user_locks.get_lock(phone_number)
    
    async with user_lock:
        logger.debug(f"🔓 [Task] Lock adquirido para {phone_number[:6]}***")
        
        # 1. Registrar Tarea Activa (Cancelation Token)
        # Si llega un nuevo mensaje mientras estamos aquí, sobrescribirá este ID
        # y podremos saber que debemos abortar.
        current_task_id = str(uuid.uuid4())
        if message_buffer:
            await message_buffer.set_active_task(phone_number, current_task_id)
        
        start_time = time.time()
        
        try:
            # 2. PROCESAMIENTO DE AUDIO SI EXISTE (ANTES del delay de lectura)
            # Primero necesitamos el texto normalizado para calcular el delay de lectura
            if audio_url or audio_base64:
                try:
                    logger.info(f"🎤 [Task] Procesando mensaje de audio: {'Base64' if audio_base64 else audio_url}")
                    # Directorio temporal
                    temp_dir = Path("temp_audio")
                    temp_dir.mkdir(exist_ok=True)
                    
                    # Nombres de archivo
                    file_id = str(uuid.uuid4())
                    input_audio_path = temp_dir / f"{file_id}_in.ogg" # WhatsApp suele enviar OGG
                    
                    # 1. Guardar/Descargar
                    audio_saved = False
                    loop = asyncio.get_running_loop()
                    if audio_base64:
                        audio_saved = await loop.run_in_executor(None, save_base64_audio, audio_base64, str(input_audio_path))
                    elif audio_url:
                        audio_saved = await download_audio(audio_url, str(input_audio_path))
                        
                    if audio_saved:
                        # 2. Transcribir (ejecutar en executor para no bloquear)
                        loop = asyncio.get_running_loop()
                        transcription = await loop.run_in_executor(None, transcribe_audio, str(input_audio_path))
                        
                        if transcription:
                            logger.info(f"📝 Transcripción: '{transcription}'")
                            normalized_text = f"[AUDIO_INPUT] {transcription}"
                        else:
                            normalized_text = "Disculpa, no pude entender bien ese audio, ¿puedes escribirlo por favor?"
                            
                        # Limpiar
                        input_audio_path.unlink(missing_ok=True)
                    else:
                        normalized_text = "Disculpa, no pude escuchar el audio, ¿puedes escribirlo por favor?"
                        
                except Exception as e:
                    logger.error(f"❌ Error procesando audio de entrada: {e}")
                    normalized_text = "No pude escuchar el audio, ¿puedes escribirlo por favor?"

            # 3. CÁLCULO DE DELAY INTELIGENTE (LECTURA)
            # Primero calculamos el tiempo de lectura del mensaje del usuario
            delay_params = await delay_manager.get_delay_parameters(
                phone_number, 
                len(normalized_text)
            )
            
            reading_delay = delay_params["reading_delay"]
            logger.info(f"👀 [Task] Leyendo mensaje ({len(normalized_text)} chars) -> Esperando {reading_delay:.2f}s")
            
            # Indicar "En línea" primero (leyendo)
            await set_whatsapp_presence(phone_number, "available")
            await asyncio.sleep(reading_delay)

            # Indicar "Escribiendo..."
            await set_whatsapp_presence(phone_number, "composing")
            
            # Tiempo base de "pensar" antes de invocar al agente
            # (El resto del delay se aplicará al responder si usó herramientas)
            thinking_delay = delay_params["thinking_delay"] * 0.5 # Usamos la mitad antes, la mitad después si es necesario
            logger.info(f"🧠 [Task] Laura pensando... ({thinking_delay:.1f}s)")
            
            # CHECKPOINT DE CANCELACIÓN #1: Antes de esperar thinking
            if message_buffer and not await message_buffer.is_task_active(phone_number, current_task_id):
                logger.warning(f"🛑 [Task] Cancelada por NUEVO mensaje de usuario (CP1) - {phone_number[:6]}***")
                return

            await asyncio.sleep(thinking_delay)
            
            # CHECKPOINT DE CANCELACIÓN #2: Antes de invocar al agente
            if message_buffer and not await message_buffer.is_task_active(phone_number, current_task_id):
                logger.warning(f"🛑 [Task] Cancelada por NUEVO mensaje de usuario (CP2) - {phone_number[:6]}***")
                return
            
            # 2. Asegurar grafo async listo
            await agent._ensure_async_setup()

            # 3. Re-obtener estado fresco DESPUÉS del lock y delay
            # Esto evita usar estados obsoletos si hubo mensajes previos procesándose
            prev_state = await get_previous_state(thread_id)

            qualification_snapshot = await load_qualification_snapshot(thread_id)
            if qualification_snapshot is None:
                qualification_snapshot = get_default_snapshot()

            prev_snapshot = prev_state.get("qualification_snapshot")
            if isinstance(prev_snapshot, dict):
                qualification_snapshot = prev_snapshot
            
            # 4. Construir estado inicial y configurar thread
            messages_before = prev_state.get("messages", [])
            initial_state = build_initial_state(
                normalized_text,
                prev_state,
                qualification_snapshot=qualification_snapshot,
            )
            config = {"configurable": {"thread_id": thread_id}}

            turn_id = await next_turn_id(thread_id)
            if turn_id > 0:
                publish_qualification_event(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    user_text=normalized_text,
                    source="whatsapp",
                    conversation_context=build_conversation_context(messages_before, normalized_text),
                )
            else:
                logger.warning(
                    "Qualification event not published for %s because turn_id=%s",
                    thread_id,
                    turn_id,
                )
            
            # 5. Invocar el agente
            logger.info(
                "🤖 [Task] Invocando agente para %s*** thread=%s",
                phone_number[:6],
                thread_id,
            )
            result = await agent.async_graph.ainvoke(initial_state, config=config)
            
            messages_all = result.get("messages", [])
            
            # EXTRAER SOLO MENSAJES NUEVOS
            # Calculamos el índice donde empiezan los mensajes nuevos
            # +1 porque añadimos el HumanMessage del usuario al inicio
            start_index = len(messages_before) + 1 
            new_messages = messages_all[start_index:] if len(messages_all) > start_index else []
            
            logger.info(f"🔍 [Debug Extraction] Pre-count: {len(messages_before)}, All-count: {len(messages_all)}, Start-idx: {start_index}")
            
            # Si new_messages está vacío (ej: solo devolvió el result del nodo sin añadir messages?), 
            # intentamos ser más flexibles y buscamos desde el mensaje del usuario actual
            if not new_messages:
                 logger.info("⚠️ [Debug Extraction] new_messages vacío, intentando backup search...")
                 last_human_idx = -1
                 for i, m in enumerate(reversed(messages_all)):
                     if isinstance(m, HumanMessage) and m.content == normalized_text:
                         last_human_idx = len(messages_all) - 1 - i
                         break
                 if last_human_idx != -1:
                     new_messages = messages_all[last_human_idx+1:]
                     logger.info(f"✅ [Debug Extraction] Backup method found {len(new_messages)} new messages")

            response_text = extract_last_ai_response(new_messages)
            
            # DEBUG INFO
            if not response_text:
                logger.warning(f"⚠️ [Task] Response Text es None/Empty. New Messages: {[type(m) for m in new_messages]}")
                # Fallback: Check if last message is AIMessage and use it regardless of checks if desperate
                if new_messages and isinstance(new_messages[-1], AIMessage):
                    content = new_messages[-1].content
                    if content:
                        logger.info("⚠️ [Task] Usando contenido directo del último AIMessage como fallback")
                        response_text = content

            if not response_text:
                # Si no hay texto, verificamos si es porque el agente solo usó tools y no respondió nada (error o diseño)
                # En este caso, NO debemos repetir mensajes antiguos.
                
                # Check si hubo tool usage recent
                if any(isinstance(m, ToolMessage) for m in new_messages):
                     logger.info("⚠️ [Task] Agente ejecutó herramientas pero no generó respuesta de texto final.")
                     # Opcional: Podríamos forzar un mensaje genérico
                
                if not response_text:
                    logger.warning(f"⚠️ [Task] No se encontró respuesta de texto NUEVA del agente para {phone_number[:6]}***")
                    # NO usar fallback histórico, eso causa bucles. 
            
            elapsed_time = time.time() - start_time
            logger.info(f"⚡ [Task] Respuesta generada en {elapsed_time:.2f}s")
            
            # 6. APLICAR DELAY RESTANTE (si hubo Uso de Herramientas)
            # Detectar si el agente usó herramientas
            try:
                tool_calls_detected = False
                
                # Método 1: Buscar tool calls en los mensajes NUEVOS
                for msg in new_messages:
                    if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                        tool_calls_detected = True
                        break
                    if isinstance(msg, ToolMessage):
                        tool_calls_detected = True
                        break

                # Si usó tools, aplicamos el delay 'thinking' restante (la otra mitad) + extra aleatorio
                if tool_calls_detected:
                     logger.info("🛠️ Herramientas detectadas, aplicando delay extra...")
                     # Recalcular delay con flag used_tools=True para obtener el extra
                     new_params = await delay_manager.get_delay_parameters(phone_number, 0, used_tools=True)
                     # Aplicar delay extra (entre 1.5s y 3.0s aprox según config)
                     extra_delay = new_params["thinking_delay"] * 0.5 
                     await asyncio.sleep(extra_delay)
                else:
                     # Si no usó tools, aplicamos el residuo del thinking delay original
                     await asyncio.sleep(thinking_delay) 
                     
            except Exception as e:
                logger.warning(f"⚠️ Error calculando delay extra: {e}")

            # 7. Formatear y Enviar mensajes
            message_chunks = None
            
            # DETECTAR SI LA RESPUESTA DEBE SER EN AUDIO
            if response_text and "[AUDIO_OUTPUT]" in response_text:
                # ... (código existente de audio) ...
                try:
                    text_to_speak = response_text.replace("[AUDIO_OUTPUT]", "").strip()
                    # Limpiar markdown y emojis para el audio
                    import re
                    # Eliminar asteriscos, guiones bajos, backticks
                    text_to_speak = re.sub(r'[*_`]', '', text_to_speak)
                    # Eliminar listas markdown (ej: "- item")
                    text_to_speak = re.sub(r'^\s*-\s+', '', text_to_speak, flags=re.MULTILINE)
                    
                    logger.info(f"🔊 [Task] Generando respuesta de voz para: '{text_to_speak[:50]}...'")
                    
                    # Directorio temporal
                    temp_dir = Path("temp_audio")
                    temp_dir.mkdir(exist_ok=True)
                    output_audio_path = temp_dir / f"{uuid.uuid4()}_out.mp3"
                    
                    # Generar voz con ElevenLabs
                    if await generate_voice(text_to_speak, str(output_audio_path)):
                        logger.info("📤 Enviando nota de voz...")
                        sent_audio = await send_whatsapp_audio(phone_number, str(output_audio_path))
                        
                        if sent_audio:
                            output_audio_path.unlink(missing_ok=True)
                        else:
                            logger.warning("⚠️ Falló envío de audio, enviando texto como fallback")
                            message_chunks = format_for_whatsapp(text_to_speak)
                    else:
                         logger.warning("⚠️ Falló generación de voz, enviando texto como fallback")
                         message_chunks = format_for_whatsapp(text_to_speak)

                except Exception as e:
                    logger.error(f"❌ Error generando/enviando audio de respuesta: {e}")
                    message_chunks = format_for_whatsapp(response_text.replace("[AUDIO_OUTPUT]", "").strip())
            else:
                # Flujo normal de texto
                # Si response_text es None o vacío, format_for_whatsapp devolverá []
                message_chunks = format_for_whatsapp(response_text)

            # CHECKPOINT DE CANCELACIÓN #3: Antes de enviar (CRÍTICO)
            if message_buffer and not await message_buffer.is_task_active(phone_number, current_task_id):
                logger.warning(f"🛑 [Task] Cancelada por NUEVO mensaje de usuario (CP3 - PRE-SEND) - {phone_number[:6]}***")
                return

            # Solo loguear si realmente vamos a enviar algo
            if message_chunks:
                logger.info(f"📝 [Task] Enviando {len(message_chunks)} bloques a {phone_number[:6]}***")
            
            # Process and send messages/images
            if message_chunks:
                sent_count = 0
                for i, chunk in enumerate(message_chunks):
                    # Check for image markers in the chunk
                    import re
                    image_pattern = r'\[SEND_IMAGE:([^:]+):([^\]]+)\]'
                    images_to_send = re.findall(image_pattern, chunk)
                    
                    # Remove image markers from text
                    clean_chunk = re.sub(image_pattern, '', chunk).strip()
                    
                    if i > 0 and clean_chunk:
                        # Calcular tiempo de escritura para este chunk específico
                        chunk_delay = await delay_manager.simulate_typing_pause(clean_chunk)
                        logger.debug(f"⌨️ Escribiendo chunk {i+1}... ({chunk_delay:.1f}s)")
                        
                        # Mantener "Escribiendo..." durante la pausa
                        steps = int(chunk_delay / 2.0) + 1
                        for _ in range(steps):
                             if not await message_buffer.is_task_active(phone_number, current_task_id):
                                 return # Abortar si interrumpido
                             await set_whatsapp_presence(phone_number, "composing")
                             await asyncio.sleep(min(2.0, chunk_delay / steps))
                    
                    # Send text if there's any
                    if clean_chunk:
                        sent = await send_whatsapp_message(phone_number, clean_chunk)
                        if sent: sent_count += 1
                    
                    # Send images if found in markers (legacy support)
                    for base64_data, caption in images_to_send:
                        logger.info(f"📷 Enviando imagen (marker) con caption: {caption[:50]}...")
                        await send_whatsapp_image(phone_number, base64_data, caption)
            
            # Send queued images from tools
            from src.support.agent.nodes.conversation.tools import get_pending_images
            pending_images = get_pending_images()
            if pending_images:
                logger.info(f"📷 Enviando {len(pending_images)} imágenes pendientes...")
                for img_data in pending_images:
                    await send_whatsapp_image(phone_number, img_data["base64"], img_data.get("caption"))
            
        except Exception as e:
            logger.error(f"❌ [Task] Error en tarea de procesamiento: {e}", exc_info=True)
            await send_whatsapp_message(
                phone_number,
                "Lo siento, necesitaré unos minutos. Ya nos comunicamos contigo nuevamente."
            )


# ============================================================
# LOCKS POR USUARIO - EVITAR CONDICIONES DE CARRERA
# ============================================================
# Cuando llegan múltiples mensajes del mismo usuario, los procesamos
# secuencialmente para evitar que el contexto se mezcle

class UserLockManager:
    """Gestiona locks por usuario para procesamiento secuencial."""
    
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_creation_lock = asyncio.Lock()
    
    
    async def get_lock(self, user_id: str) -> asyncio.Lock:
        """Obtiene o crea un lock para el usuario."""
        if user_id not in self._locks:
            async with self._lock_creation_lock:
                # Double-check después de adquirir el lock
                if user_id not in self._locks:
                    self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]
    
    def cleanup_old_locks(self, active_users: set):
        """Limpia locks de usuarios que ya no están activos."""
        inactive = set(self._locks.keys()) - active_users
        for user_id in inactive:
            if user_id in self._locks and not self._locks[user_id].locked():
                del self._locks[user_id]


# Instancia global del gestor de locks
user_locks = UserLockManager()

# Configurar event loop para Windows (psycopg requiere SelectorEventLoop)
if sys.platform == "win32":
    if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# ============================================================================
# CONFIGURACIÓN DE EVOLUTION API
# ============================================================================

# Para Docker, usa http://host.docker.internal:8080 en Mac/Windows
# o http://172.17.0.1:8080 en Linux
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "")

# Configuración de Redis para Message Buffer
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_BUFFER_TIMEOUT = int(os.getenv("REDIS_MESSAGE_BUFFER_TIMEOUT", "30"))
# TTL debe ser MAYOR que el timeout para que el dato no expire mientras esperamos
REDIS_BUFFER_TTL = int(os.getenv("REDIS_MESSAGE_BUFFER_TTL", str(REDIS_BUFFER_TIMEOUT + 60)))

def _mask_redis_url(url: str) -> str:
    """Enmascara la contraseña en la URL de Redis para logs seguros."""
    import re
    return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', url)

# Log de configuración al inicio
logger.info("=" * 60)
logger.info("CONFIGURACIÓN DE EVOLUTION API")
logger.info("=" * 60)
logger.info(f"  EVOLUTION_API_URL: {EVOLUTION_API_URL}")
logger.info(f"  EVOLUTION_API_KEY: {'***' + EVOLUTION_API_KEY[-4:] if len(EVOLUTION_API_KEY) > 4 else '(no configurado)'}")
logger.info(f"  EVOLUTION_INSTANCE: {EVOLUTION_INSTANCE or '(no configurado)'}")
logger.info(f"  REDIS_URL: {_mask_redis_url(REDIS_URL)}")
logger.info(f"  REDIS_BUFFER_TIMEOUT: {REDIS_BUFFER_TIMEOUT}s")
logger.info("=" * 60)

# ============================================================================
# INICIALIZACIÓN DE LA APLICACIÓN
# ============================================================================

app = FastAPI(
    title="Nagaki Agent Evolution Webhook",
    description="Webhook para integrar el agente LangGraph con Evolution API (WhatsApp)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar el agente una vez al arrancar
try:
    agent = Agent()
    logger.info("✅ Agente inicializado correctamente para Evolution API")
except Exception as e:
    logger.error(f"❌ Error al inicializar el agente: {e}")
    agent = None

# Inicializar Message Buffer con Redis
message_buffer = None  # Se inicializa en startup

# Inicializar Delay Manager
delay_manager = ThinkingDelayManager(redis_url=REDIS_URL)

# ============================================================================
# HELPERS PARA PERSISTENCIA DE ESTADO
# ============================================================================

async def get_previous_state(thread_id: str) -> Dict[str, Any]:
    """
    Recupera el estado previo del checkpointer si existe.
    
    Args:
        thread_id: ID del hilo de conversación (número de teléfono)
        
    Returns:
        dict: Estado previo o diccionario vacío si no existe
    """
    if agent is None or agent.async_graph is None:
        return {}
    
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await agent.async_graph.aget_state(config)
        if state and state.values:
            snapshot = state.values.get("qualification_snapshot") or {}
            logger.debug(
                "📊 Estado previo recuperado para %s: stage=%s",
                thread_id,
                snapshot.get("qualification_stage", "new"),
            )
            return state.values
    except Exception as e:
        logger.debug(f"No se encontró estado previo para {thread_id}: {e}")
    return {}


def build_initial_state(
    user_input: str,
    prev_state: Dict[str, Any],
    qualification_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Construye el estado inicial preservando datos del estado previo.
    
    Args:
        user_input: Mensaje del usuario
        prev_state: Estado previo del checkpointer
        qualification_snapshot: Snapshot actual de calificación
        
    Returns:
        dict: Estado inicial con datos preservados
    """
    snapshot = qualification_snapshot if isinstance(qualification_snapshot, dict) else get_default_snapshot()
    return {
        "messages": [HumanMessage(content=user_input)],
        "input": user_input,
        "is_customer": prev_state.get("is_customer", False),
        "qualification_snapshot": snapshot,
        "interested": snapshot.get("interested", prev_state.get("interested", False)),
        "qualified": snapshot.get("qualified", prev_state.get("qualified", False)),
        "qualification_stage": snapshot.get(
            "qualification_stage",
            prev_state.get("qualification_stage", "new"),
        ),
    }


# ============================================================================
# HELPERS PARA EVOLUTION API
# ============================================================================


def normalize_phone_number(remote_jid: str) -> str:
    """
    Normaliza el número de teléfono de WhatsApp para usar como thread_id.
    
    Args:
        remote_jid: ID remoto de WhatsApp (ej: "5491155555555@s.whatsapp.net")
        
    Returns:
        str: Número de teléfono normalizado (ej: "5491155555555")
    """
    # Remover el sufijo @s.whatsapp.net o @g.us (para grupos)
    phone = remote_jid.split("@")[0]
    return phone


def canonical_thread_id(phone_number: str) -> str:
    """Convierte teléfono WhatsApp a thread_id canónico compartible entre bots."""
    value = phone_number.strip()
    if value.startswith("00"):
        value = f"+{value[2:]}"
    if not value.startswith("+"):
        value = f"+{value}"
    digits = re.sub(r"\D", "", value)
    if not digits:
        return f"lead:{phone_number}"
    return f"lead:+{digits}"


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    if isinstance(value, list):
        parts: list[str] = []
        for chunk in value:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                text = chunk.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif hasattr(chunk, "text") and isinstance(chunk.text, str):
                parts.append(chunk.text)
        return " ".join(" ".join(parts).split()).strip()
    return ""


def build_conversation_context(
    previous_messages: list[Any],
    user_text: str,
    max_items: int = 60,
    max_chars: int = 20_000,
) -> str:
    """Serializa el contexto reciente para el worker de calificación."""
    lines: list[str] = []
    for msg in previous_messages[-max_items:]:
        role = "assistant"
        if isinstance(msg, HumanMessage):
            role = "user"
        elif isinstance(msg, ToolMessage):
            role = "tool"
        text = _message_text(getattr(msg, "content", ""))
        if text:
            lines.append(f"{role}: {text}")

    clean_user = " ".join((user_text or "").split()).strip()
    if clean_user:
        lines.append(f"user: {clean_user}")

    context = "\n".join(lines)
    if len(context) > max_chars:
        context = context[-max_chars:]
    return context


def extract_message_text(data: dict) -> Optional[str]:
    """
    Extrae el texto del mensaje de diferentes tipos de mensajes de WhatsApp.
    
    Args:
        data: Datos del mensaje de Evolution API
        
    Returns:
        str: Texto del mensaje o None si no es un mensaje de texto
    """
    message = data.get("message", {})
    
    # Mensaje de texto simple
    conversation = message.get("conversation")
    if conversation:
        return conversation.strip()
    
    # Mensaje extendido (respuesta, link, etc)
    extended = message.get("extendedTextMessage", {})
    if extended and extended.get("text"):
        return extended.get("text").strip()
    
    # Mensaje de imagen con caption
    image = message.get("imageMessage", {})
    if image and image.get("caption"):
        return image.get("caption").strip()
        
    return None


def extract_quoted_context(data: dict) -> Optional[str]:
    """
    Extrae el texto del mensaje citado (reply) si existe.
    
    Args:
        data: Datos del mensaje de Evolution API
        
    Returns:
        str: Texto del mensaje citado formateado o None
    """
    message = data.get("message", {})
    
    # 1. Verificar si es un mensaje extendido (respuesta)
    extended = message.get("extendedTextMessage", {})
    context_info = extended.get("contextInfo")
    
    if not context_info:
        # A veces puede venir en imageMessage u otros tipos
        image = message.get("imageMessage", {})
        context_info = image.get("contextInfo")
        
    if context_info and context_info.get("quotedMessage"):
        quoted = context_info.get("quotedMessage")
        
        # Extraer texto del mensaje citado (puede ser conversation o extendedText)
        quoted_text = quoted.get("conversation")
        
        if not quoted_text:
            # Intentar extraer de extendedTextMessage dentro del quoted
            q_extended = quoted.get("extendedTextMessage", {})
            quoted_text = q_extended.get("text")
            
        if not quoted_text:
             # Intentar caption de imagen
             q_image = quoted.get("imageMessage", {})
             quoted_text = q_image.get("caption") or "[Imagen]"
             
        if not quoted_text:
             # Intentar audio
             if quoted.get("audioMessage"):
                 quoted_text = "[Audio]"

        if quoted_text:
            return quoted_text.strip()
            
    return None




async def send_whatsapp_message(phone_number: str, message: str, instance: str = None, max_retries: int = 3) -> bool:
    """
    Envía un mensaje de WhatsApp vía Evolution API con reintentos.
    
    Args:
        phone_number: Número de teléfono del destinatario (sin @s.whatsapp.net)
        message: Texto del mensaje a enviar
        instance: Nombre de la instancia (opcional, usa EVOLUTION_INSTANCE por defecto)
        max_retries: Número máximo de reintentos en caso de fallo
        
    Returns:
        bool: True si se envió correctamente, False en caso contrario
    """
    instance = instance or EVOLUTION_INSTANCE
    
    if not instance:
        logger.error("❌ EVOLUTION_INSTANCE no configurado. Configura la variable de entorno.")
        return False
    
    if not EVOLUTION_API_KEY:
        logger.error("❌ EVOLUTION_API_KEY no configurado. Configura la variable de entorno.")
        return False
    
    url = f"{EVOLUTION_API_URL}/message/sendText/{instance}"
    
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Evolution API requiere el número con @s.whatsapp.net para enviar
    # Si el número no tiene el sufijo, lo agregamos
    number_to_send = phone_number
    if not phone_number.endswith("@s.whatsapp.net"):
        number_to_send = f"{phone_number}@s.whatsapp.net"
    
    payload = {
        "number": number_to_send,
        "text": message
    }
    
    logger.debug(f"📤 Enviando mensaje a {phone_number[:6]}*** vía {url}")
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code in (200, 201):
                    logger.info(f"✅ Mensaje enviado a {phone_number[:6]}***")
                    return True
                elif response.status_code == 404:
                    logger.error(f"❌ Instancia '{instance}' no encontrada en Evolution API")
                    return False
                elif response.status_code == 401:
                    logger.error(f"❌ API Key inválida para Evolution API")
                    return False
                else:
                    logger.warning(f"⚠️ Intento {attempt + 1}/{max_retries}: Error {response.status_code} - {response.text[:200]}")
                    
        except httpx.ConnectError as e:
            logger.warning(f"⚠️ Intento {attempt + 1}/{max_retries}: No se pudo conectar a Evolution API ({EVOLUTION_API_URL}): {e}")
        except httpx.TimeoutException:
            logger.warning(f"⚠️ Intento {attempt + 1}/{max_retries}: Timeout conectando a Evolution API")
        except Exception as e:
            logger.warning(f"⚠️ Intento {attempt + 1}/{max_retries}: Error inesperado: {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(1 * (attempt + 1))  # Backoff exponencial simple
    
    logger.error(f"❌ No se pudo enviar mensaje después de {max_retries} intentos")
    return False


async def send_whatsapp_audio(phone_number: str, audio_path: str, instance: str = None) -> bool:
    """Send voice note via Evolution API."""
    instance = instance or EVOLUTION_INSTANCE
    
    if not instance or not EVOLUTION_API_KEY:
        return False
        
    url = f"{EVOLUTION_API_URL}/message/sendWhatsAppAudio/{instance}" # sendWhatsAppAudio envía como nota de voz (PTT)
    # Si sendVoice no va, usar sendAudio
    
    headers = {
        "apikey": EVOLUTION_API_KEY
    }
    
    # Evolution espera form-data para archivos
    # 'file': (filename, open(path, 'rb'), 'audio/mpeg')
    
    number_to_send = phone_number if phone_number.endswith("@s.whatsapp.net") else f"{phone_number}@s.whatsapp.net"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(audio_path, "rb") as f:
                files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
                data = {"number": number_to_send}
                
                response = await client.post(url, headers=headers, data=data, files=files)
                
                if response.status_code in (200, 201):
                    logger.info(f"✅ Audio enviado a {phone_number[:6]}***")
                    return True
                else:
                    logger.error(f"❌ Error enviando audio: {response.status_code} - {response.text}")
                    return False
    except Exception as e:
        logger.error(f"❌ Excepción enviando audio: {e}")
        return False


async def send_whatsapp_image(phone_number: str, base64_data: str, caption: str = None, instance: str = None) -> bool:
    """
    Send image via Evolution API using base64 data.
    
    Args:
        phone_number: Phone number to send to
        base64_data: Base64 encoded image (with or without data:image prefix)
        caption: Optional caption for the image
        instance: Evolution instance name
        
    Returns:
        bool: True if sent successfully
    """
    instance = instance or EVOLUTION_INSTANCE
    
    if not instance or not EVOLUTION_API_KEY:
        return False
    
    url = f"{EVOLUTION_API_URL}/message/sendMedia/{instance}"
    
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Evolution API expects raw base64 without the data:image prefix
    logger.info(f"📷 [send_whatsapp_image] Original data starts with: {base64_data[:50]}...")
    
    # Extract raw base64 if it has data URI prefix
    if base64_data.startswith("data:"):
        # Remove data:image/jpeg;base64, or similar prefix
        if ";base64," in base64_data:
            base64_data = base64_data.split(";base64,")[1]
            logger.info("📷 Removed data URI prefix, using raw base64")
        else:
            logger.warning("📷 Data URI format unexpected, using as-is")
    else:
        logger.info("📷 Data is already raw base64")
    
    number_to_send = phone_number if phone_number.endswith("@s.whatsapp.net") else f"{phone_number}@s.whatsapp.net"
    
    # Evolution API structure for base64 images
    payload = {
        "number": number_to_send,
        "mediatype": "image",
        "media": base64_data,
        "options": {
            "delay": 1200,
            "presence": "composing"
        }
    }
    
    if caption:
        payload["caption"] = caption
    
    logger.info(f"📷 Payload: mediatype=image, base64 length: {len(base64_data)}")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code in (200, 201):
                logger.info(f"✅ Imagen enviada a {phone_number[:6]}***")
                return True
            else:
                logger.error(f"❌ Error enviando imagen: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"❌ Excepción enviando imagen: {e}")
        return False


async def get_audio_base64_from_api(message_data: dict, instance: str = None) -> Optional[str]:
    """
    Solicita a Evolution API la conversión a Base64 de un mensaje de audio.
    Útil cuando el webhook no trae el base64 directamente.
    """
    instance = instance or EVOLUTION_INSTANCE
    if not instance or not EVOLUTION_API_KEY:
        return None
        
    url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{instance}"
    
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "message": message_data, # Evolution espera el objeto mensaje completo aquí
        "convertToMp4": False,
        "forceDownload": True
    }
    
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code in (200, 201):
                result = response.json()
                # Evolution devuelve: {"base64": "data:audio/ogg;base64,..."}
                return result.get("base64")
            else:
                logger.warning(f"⚠️ Error obteniendo Base64 de Evolution: {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"❌ Error conectando para Base64: {e}")
        return None


def extract_last_ai_response(messages: list) -> Optional[str]:
    """
    Extrae el último mensaje de IA del historial.
    
    Args:
        messages: Lista de mensajes del estado
        
    Returns:
        str: Contenido del último AIMessage o None
    """
    if not messages:
        return None
    
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            # Verificar que tenga contenido válido y no sea solo JSON
            if content and content.strip() and not content.strip().startswith("{"):
                return content
    return None


async def set_whatsapp_presence(phone_number: str, presence: str = "composing", instance: str = None) -> bool:
    """
    Establece el estado de presencia en WhatsApp (ej: "composing", "recording", "available").
    """
    instance = instance or EVOLUTION_INSTANCE
    if not instance or not EVOLUTION_API_KEY:
        return False

    url = f"{EVOLUTION_API_URL}/chat/sendPresence/{instance}"
    
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }

    # Evolution API v2 prefiere el número sin sufijo para presencia en chat
    clean_number = phone_number.split("@")[0]
    
    payload = {
        "number": clean_number,
        "presence": presence,
        "delay": 1200 # Delay recomendado en ms
    }
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code not in (200, 201):
                logger.warning(f"⚠️ Falló sendPresence: {response.status_code} - {response.text}")
                return False
            return True
    except Exception as e:
        logger.warning(f"⚠️ Error enviando presence: {e}")
        return False


# ============================================================================
# EVENTOS DE STARTUP Y SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Pre-calentar el grafo asíncrono al iniciar."""
    global message_buffer
    
    try:
        if agent:
            await agent._ensure_async_setup()
            logger.info("✅ Grafo asíncrono pre-calentado en startup")
            
        await delay_manager.connect()
        logger.info("✅ Delay Manager conectado a Redis")
        
        # Inicializar Message Buffer con Redis
        from src.support.utils.message_buffer import MessageBuffer
        try:
            message_buffer = MessageBuffer(
                redis_url=REDIS_URL,
                buffer_timeout=REDIS_BUFFER_TIMEOUT,
                ttl=REDIS_BUFFER_TTL
            )
            await message_buffer.connect()
            logger.info("✅ Message Buffer inicializado con Redis")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo conectar a Redis: {e}. Buffer deshabilitado.")
            message_buffer = None
            
    except Exception as e:
        logger.error(f"❌ Error en startup: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cerrar conexiones limpiamente."""
    if agent:
        try:
            await agent.cleanup()
            logger.info("✅ Conexiones del agente cerradas correctamente")
        except Exception as e:
            logger.error(f"❌ Error al cerrar conexiones del agente: {e}")
    
    if message_buffer:
        try:
            await message_buffer.close()
            logger.info("✅ Message Buffer cerrado correctamente")
        except Exception as e:
            logger.error(f"❌ Error al cerrar Message Buffer: {e}")


# ============================================================================
# ENDPOINTS DE SALUD
# ============================================================================

@app.get("/")
async def root():
    """Endpoint de salud."""
    return {
        "status": "ok",
        "service": "Nagaki Agent Evolution Webhook",
        "version": "1.0.0",
        "evolution_instance": EVOLUTION_INSTANCE or "not_configured"
    }


@app.get("/health")
async def health_check():
    """Health check."""
    return {
        "status": "healthy",
        "agent_ready": agent is not None,
        "evolution_configured": bool(EVOLUTION_API_KEY and EVOLUTION_INSTANCE)
    }


# ============================================================================
# ENDPOINTS ADMINISTRATIVOS: GESTIÓN DE SPAM
# ============================================================================

@app.get("/admin/spam/status/{phone_number}")
async def get_spam_status(phone_number: str):
    """
    Obtiene el estado de spam de un usuario.
    
    Args:
        phone_number: Número de teléfono (ej: 5491155555555)
    """
    status = spam_detector.get_user_status(phone_number)
    
    # Formatear timestamp si existe
    if status["blocked_since"]:
        from datetime import datetime
        blocked_time = datetime.fromtimestamp(status["blocked_since"])
        status["blocked_since_formatted"] = blocked_time.strftime("%Y-%m-%d %H:%M:%S")
    
    return {
        "phone": phone_number,
        "status": status,
        "message": "Usuario bloqueado" if status["blocked"] else "Usuario activo"
    }


@app.post("/admin/spam/unblock/{phone_number}")
async def unblock_user(phone_number: str):
    """
    Desbloquea a un usuario y resetea sus strikes.
    
    Args:
        phone_number: Número de teléfono (ej: 5491155555555)
    """
    success = spam_detector.unblock_user(phone_number)
    
    if success:
        return {
            "success": True,
            "message": f"Usuario {phone_number} desbloqueado exitosamente",
            "phone": phone_number
        }
    else:
        return {
            "success": False,
            "message": f"Usuario {phone_number} no estaba bloqueado",
            "phone": phone_number
        }


@app.post("/admin/spam/reset-strikes/{phone_number}")
async def reset_strikes(phone_number: str):
    """
    Resetea los strikes de un usuario sin desbloquearlo.
    
    Args:
        phone_number: Número de teléfono (ej: 5491155555555)
    """
    spam_detector.reset_user_strikes(phone_number)
    
    return {
        "success": True,
        "message": f"Strikes reseteados para {phone_number}",
        "phone": phone_number,
        "new_status": spam_detector.get_user_status(phone_number)
    }


@app.get("/admin/spam/blocked-users")
async def get_blocked_users():
    """
    Lista todos los usuarios bloqueados.
    """
    blocked = []
    from datetime import datetime
    
    for phone, timestamp in spam_detector.blocked_users.items():
        blocked_time = datetime.fromtimestamp(timestamp)
        blocked.append({
            "phone": phone,
            "strikes": spam_detector.user_strikes.get(phone, 0),
            "blocked_since": blocked_time.strftime("%Y-%m-%d %H:%M:%S"),
            "blocked_timestamp": timestamp
        })
    
    return {
        "total_blocked": len(blocked),
        "blocked_users": blocked
    }



@app.get("/test-evolution")
async def test_evolution_connection():
    """
    Endpoint para probar la conexión con Evolution API.
    Verifica que la instancia esté conectada y funcionando.
    """
    result = {
        "evolution_api_url": EVOLUTION_API_URL,
        "instance": EVOLUTION_INSTANCE or "(no configurado)",
        "api_key_configured": bool(EVOLUTION_API_KEY),
        "connection_test": None,
        "instance_status": None
    }
    
    if not EVOLUTION_API_KEY:
        result["error"] = "EVOLUTION_API_KEY no configurado"
        return JSONResponse(status_code=400, content=result)
    
    if not EVOLUTION_INSTANCE:
        result["error"] = "EVOLUTION_INSTANCE no configurado"
        return JSONResponse(status_code=400, content=result)
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Probar conexión básica
            url = f"{EVOLUTION_API_URL}/instance/connectionState/{EVOLUTION_INSTANCE}"
            headers = {"apikey": EVOLUTION_API_KEY}
            
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                result["connection_test"] = "success"
                result["instance_status"] = data
                return result
            elif response.status_code == 404:
                result["connection_test"] = "failed"
                result["error"] = f"Instancia '{EVOLUTION_INSTANCE}' no encontrada"
                return JSONResponse(status_code=404, content=result)
            elif response.status_code == 401:
                result["connection_test"] = "failed"
                result["error"] = "API Key inválida"
                return JSONResponse(status_code=401, content=result)
            else:
                result["connection_test"] = "failed"
                result["error"] = f"Error {response.status_code}: {response.text[:200]}"
                return JSONResponse(status_code=response.status_code, content=result)
                
    except httpx.ConnectError as e:
        result["connection_test"] = "failed"
        result["error"] = f"No se pudo conectar a {EVOLUTION_API_URL}: {str(e)}"
        return JSONResponse(status_code=503, content=result)
    except Exception as e:
        result["connection_test"] = "failed"
        result["error"] = f"Error: {str(e)}"
        return JSONResponse(status_code=500, content=result)


# ============================================================================
# ENDPOINT PRINCIPAL: WEBHOOK DE EVOLUTION API
# ============================================================================

@app.post("/webhook/message")
@app.post("/webhook/message/messages-upsert")
@app.post("/webhook/message/send-message")
@app.post("/webhook/message/presence-update")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook principal para recibir mensajes de Evolution API.
    
    Evolution API envía eventos con la estructura:
    {
        "event": "messages.upsert",
        "instance": "instance_name",
        "data": {
            "key": {
                "remoteJid": "5491155555555@s.whatsapp.net",
                "fromMe": false,
                "id": "message_id"
            },
            "message": {
                "conversation": "Texto del mensaje"
            },
            "messageTimestamp": "1234567890"
        }
    }
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        body = await request.json()
        
        # Verificar tipo de evento
        event_type = body.get("event", "")
        logger.info(f"📨 Webhook recibido - Evento: {event_type}")
        
        # Si es un evento de presencia (composing/typing)
        if event_type == "presence.update":
            data = body.get("data", {})
            remote_jid = data.get("remoteJid", "")
            presence = data.get("presence", {}).get("presenca", "")
            
            if remote_jid and (presence == "composing" or presence == "typing"):
                phone_number = normalize_phone_number(remote_jid)
                if message_buffer:
                    await message_buffer.set_typing(phone_number)
                    logger.debug(f"✍️ Detectado: {phone_number[:6]}*** está escribiendo...")
            
            return JSONResponse(content={"status": "presence_updated"})

        # Solo procesar mensajes entrantes (upsert)
        if event_type != "messages.upsert":
            logger.info(f"📭 Evento ignorado (no es messages.upsert): {event_type}")
            return JSONResponse(content={"status": "ignored", "event": event_type})
        
        data = body.get("data", {})
        key = data.get("key", {})
        
        # Ignorar mensajes enviados por nosotros
        if key.get("fromMe", False):
            logger.debug("📤 Mensaje propio ignorado")
            return JSONResponse(content={"status": "ignored", "reason": "own_message"})
        
        # Extraer información del mensaje
        # Evolution API puede enviar el JID en formato LID (@lid) o normal (@s.whatsapp.net)
        # Si es LID, el número real está en remoteJidAlt
        remote_jid = key.get("remoteJid", "")
        remote_jid_alt = key.get("remoteJidAlt", "")
        message_id = key.get("id", "")
        
        # Usar remoteJidAlt si está disponible y remoteJid es LID
        if remote_jid.endswith("@lid") and remote_jid_alt:
            logger.debug(f"🔄 Usando remoteJidAlt: {remote_jid_alt} (original era LID: {remote_jid})")
            remote_jid = remote_jid_alt
        
        # ============================================================
        # DEDUPLICACIÓN: Verificar si ya procesamos este mensaje
        # ============================================================
        if message_id and message_cache.is_duplicate(message_id):
            logger.warning(f"⚠️ Mensaje duplicado ignorado: {message_id[:20]}...")
            return JSONResponse(content={"status": "ignored", "reason": "duplicate"})
        
        # Ignorar mensajes de grupos (terminan en @g.us)
        if remote_jid.endswith("@g.us"):
            logger.debug(f"👥 Mensaje de grupo ignorado: {remote_jid}")
            return JSONResponse(content={"status": "ignored", "reason": "group_message"})
        
        # Normalizar número de teléfono para interacción con Evolution API
        phone_number = normalize_phone_number(remote_jid)
        thread_id = canonical_thread_id(phone_number)
        
        # Extraer texto del mensaje
        message_text = extract_message_text(data)
        
        # Extraer contexto (cita)
        quoted_context = extract_quoted_context(data)
        if quoted_context:
            logger.info(f"🗨️ Mensaje citado detectado: '{quoted_context}'")
            # Prefijar con el contexto para que el Agente y el Buffer lo vean
            if message_text:
                message_text = f"[RESPONDIENDO A: '{quoted_context}'] {message_text}"
            else:
                 # Caso raro: reply sin texto (ej: solo sticker o imagen sin caption)
                 message_text = f"[RESPONDIENDO A: '{quoted_context}']"
        
        if not message_text:
            # Si es un mensaje de audio, obtener URL y procesar
            audio_msg = data.get("message", {}).get("audioMessage")
            if audio_msg:
                # Evolution API v2: el url suele estar en el objeto del mensaje
                # Pero a veces hay que usar el endpoint de findMessage para sacar el media
                # Asumiremos que Evolution v2 nos da la URL o Base64.
                # Nota: Evolution API suele guardar media localmente y dar una URL accesible si está configurado.
                # Si no, hay que descargar el media.
                # Normalmente, Evolution API envía los datos del media si 'downloadMedia' está activo.
                
                # Para simplificar, asumiremos que tenemos acceso.
                # IMPORTANTE: Si es base64, habrá que decodificar.
                # Vamos a intentar usar el 'url' si viene en el JSON.
                if audio_msg:
                    logger.info(f"🔍 Audio Payload Keys: {list(audio_msg.keys())}")
                
                audio_url = audio_msg.get("url")
                audio_base64 = audio_msg.get("base64") # Evolution envía esto si "send media base64" está activo
                
                # FALLBACK: Si no hay base64 en el webhook, pedirlo explícitamente a la API
                if not audio_base64:
                    logger.info("🔄 Base64 no presente en webhook, solicitando a Evolution API...")
                    # Pasamos 'data' completo porque contiene 'key' (id, remoteJid) y 'message'
                    audio_base64 = await get_audio_base64_from_api(data)
                
                # Corrección: Evolution API a veces no manda la URL pública directa si no está configurada.
                # Sin embargo, vamos a intentar procesarlo.
                if not audio_url and not audio_base64:
                     logger.warning("⚠️ Mensaje de audio sin URL ni Base64. Verifica configuración de Evolution.")
                     # Fallback placeholder URL for testing logic or raise error
                
                logger.info(f"🎤 Recibido mensaje de audio. Base64: {'SI' if audio_base64 else 'NO'}, URL: {audio_url or '???'}")
                
                 # Lanzar tarea con audio_url
                background_tasks.add_task(
                    process_whatsapp_task,
                    phone_number=phone_number,
                    normalized_text="", # Se llenará con la transcripción
                    agent=agent,
                    background_tasks=background_tasks,
                    thread_id=thread_id,
                    audio_url=audio_url,
                    audio_base64=audio_base64
                )
                 
                return JSONResponse(content={
                    "status": "processing_audio",
                    "phone": phone_number[:6] + "***"
                })

            
            logger.warning(f"⚠️ Mensaje sin texto de {phone_number[:6]}***")
            return JSONResponse(content={"status": "ignored", "reason": "no_text"})
        
        logger.info(f"📱 WhatsApp de {phone_number[:6]}***: {message_text}")
        logger.info(f"🔑 Thread ID canónico: {thread_id}")
        
        # ============================================================
        # NORMALIZACIÓN: Corregir ortografía y limpiar texto
        # ============================================================
        # DEBUG: Log para verificar flag
        logger.info(f"🔍 Normalizando texto: '{message_text}' (correct_spelling=False default)")
        normalized_text = normalize_text(message_text)
        if normalized_text != message_text:
            logger.info(f"📝 Texto normalizado: '{message_text}' → '{normalized_text}'")
        
        # ============================================================
        # DETECCIÓN DE SPAM: Verificar si el usuario está haciendo spam
        # ============================================================
        is_spam, spam_reason, user_strikes = spam_detector.check_message(phone_number, normalized_text)
        
        if is_spam:
            # Usuario bloqueado o excedió límite de spam
            if "BLOQUEADO" in spam_reason:
                logger.error(f"🚫 Usuario {phone_number[:6]}*** está BLOQUEADO: {spam_reason}")
                # Enviar mensaje de bloqueo (solo la primera vez)
                block_message = (
                    "Lo sentimos, pero tu cuenta ha sido bloqueada temporalmente debido a comportamiento "
                    "inapropiado. Si crees que esto es un error, por favor contacta a soporte."
                )
                await send_whatsapp_message(phone_number, block_message)
                
                return JSONResponse(content={
                    "status": "blocked",
                    "reason": spam_reason,
                    "strikes": user_strikes
                })
            
            # Advertencia automática
            elif "ADVERTENCIA" in spam_reason:
                logger.warning(f"⚠️ Usuario {phone_number[:6]}*** recibió advertencia: {spam_reason}")
                warning_message = (
                    "⚠️ *Advertencia*: Por favor, evita enviar mensajes muy seguidos o contenido inapropiado. "
                    "Continuaremos la conversación de manera respetuosa. Gracias por tu comprensión."
                )
                await send_whatsapp_message(phone_number, warning_message)
                # Continúa procesando el mensaje después de la advertencia
        
        # Log de strikes si hay alguno
        if user_strikes > 0:
            logger.info(f"📊 Usuario {phone_number[:6]}*** tiene {user_strikes} strike(s)")
        
        # ============================================================
        # MESSAGE BUFFER: Acumular mensajes fragmentados (Paciencia Humana)
        # ============================================================
        if message_buffer:
            try:
                # Usar el timeout configurado en lugar de hardcoded
                buffer_wait = float(REDIS_BUFFER_TIMEOUT)
                should_wait, accumulated_from_buffer = await message_buffer.should_buffer(phone_number, normalized_text)
                
                if should_wait:
                    # Esperar activamente a que el usuario deje de escribir
                    logger.info(f"📥 Buffer: Esperando fragmentos de {phone_number[:6]}***...")
                    
                    from src.support.utils.message_buffer import wait_for_buffer_completion
                    accumulated_text = await wait_for_buffer_completion(message_buffer, phone_number, wait_time=buffer_wait)
                    
                    if not accumulated_text:
                        # Ya procesado por otro hilo o vacío
                        logger.info(f"🛑 [Webhook] Buffer procesado por otra instancia o vacío. Abortando. ({phone_number[:6]}***)")
                        return JSONResponse(content={"status": "buffered", "info": "processing_elsewhere"})
                    
                    normalized_text = accumulated_text
                    logger.info(f"📦 Buffer completo (vía wait): '{normalized_text[:50]}...' ({len(normalized_text)} chars)")
                
                elif accumulated_from_buffer:
                     # Si no hay que esperar pero el buffer traía texto (timeout interno de Redis en una llamada anterior que falló?)
                     normalized_text = accumulated_from_buffer
                     logger.info(f"📦 Buffer completo (vía accumulated_from_buffer): '{normalized_text[:50]}...'")
                else:
                     # should_wait es False Y accumulated_from_buffer es None??
                     # Esto pasa si es el mensaje N>1 y timeout, should_buffer retorna False, accum_text.
                     # Si es mensaje 1 y timeout ya pasó? (no debería pasar con buffer_timeout > 0)
                     pass
                
            except Exception as e:
                logger.warning(f"⚠️ Error en message buffer: {e}. Procesando mensaje sin buffer.")

        # ============================================================
        # PREPARAR TAREA EN SEGUNDO PLANO
        # ============================================================
        
        # Verificar DEDUPLICACIÓN DE NUEVO si venimos de un buffer wait largo
        # (Aunque el cache ya lo hizo, es bueno asegurarse que no estamos procesando lo mismo)
        
        # Lanzar el procesamiento real en SEGUNDO PLANO
        # La tarea recuperará el estado fresco dentro del lock
        background_tasks.add_task(
            process_whatsapp_task,
            phone_number=phone_number,
            normalized_text=normalized_text,
            agent=agent,
            background_tasks=background_tasks,
            thread_id=thread_id,
        )
        
        logger.info(f"🚀 Tarea de procesamiento lanzada para {phone_number[:6]}***. Respondiendo 200 OK.")
        
        return JSONResponse(content={
            "status": "processing",
            "phone": phone_number[:6] + "***",
            "message_buffered": bool(message_buffer)
        })
            
    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT PARA VERIFICACIÓN DE WEBHOOK
# ============================================================================

@app.get("/webhook/message")
async def evolution_webhook_verify(request: Request):
    """
    Endpoint GET para verificación de webhook por Evolution API.
    Algunos servicios verifican el webhook con una solicitud GET.
    """
    return JSONResponse(content={
        "status": "ok",
        "message": "Evolution API Webhook is active"
    })


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("EVOLUTION_WEBHOOK_PORT", 3000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"🚀 Iniciando Evolution API Webhook en {host}:{port}")
    
    uvicorn.run(app, host=host, port=port, log_level="info")

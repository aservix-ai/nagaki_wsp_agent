"""
Buffer de mensajes con Redis para manejar mensajes fragmentados - Grupo Nagaki

Este módulo proporciona un sistema de buffering para acumular mensajes
del mismo usuario que llegan en ráfagas rápidas, permitiendo procesarlos
como un mensaje unificado.
"""

import time
import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


@dataclass
class BufferedMessage:
    """Representa un mensaje en buffer."""
    phone_number: str
    accumulated_text: str
    first_timestamp: float
    last_timestamp: float
    fragment_count: int


class MessageBuffer:
    """
    Gestor de buffer de mensajes con Redis.
    
    Acumula mensajes del mismo usuario que llegan en menos de BUFFER_TIMEOUT
    segundos, permitiendo procesar mensajes fragmentados como uno solo.
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        buffer_timeout: int = 40,  # segundos
        ttl: int = 300,  # segundos
    ):
        """
        Inicializa el buffer de mensajes.
        
        Args:
            redis_url: URL de conexión a Redis
            buffer_timeout: Tiempo máximo entre fragmentos (segundos)
            ttl: Tiempo de vida del buffer (segundos)
        """
        self.redis_url = redis_url
        self.buffer_timeout = buffer_timeout
        self.ttl = ttl
        self._redis: Optional[aioredis.Redis] = None
        self._closed = False
    
    def _mask_redis_url(self, url: str) -> str:
        """Enmascara la contraseña en la URL de Redis para logs seguros."""
        import re
        return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', url)
    
    async def connect(self):
        """Conecta a Redis."""
        if self._redis is None:
            try:
                self._redis = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    health_check_interval=30
                )
                safe_url = self._mask_redis_url(self.redis_url)
                logger.info(f"✅ Conectado a Redis: {safe_url}")
            except Exception as e:
                logger.error(f"❌ Error conectando a Redis: {e}")
                raise
    
    async def close(self):
        """Cierra la conexión a Redis."""
        if self._redis and not self._closed:
            await self._redis.close()
            self._closed = True
            self._redis = None # Ensure it is reset
            logger.info("✅ Conexión a Redis cerrada")
    
    def _get_key(self, phone_number: str) -> str:
        """Genera la clave de Redis para un usuario."""
        return f"msg_buffer:{phone_number}"

    async def _execute_with_retry(self, func, *args, **kwargs):
        """Executes a Redis command with retry logic for connection errors."""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if not self._redis: await self.connect()
                return await func(*args, **kwargs)
            except (aioredis.ConnectionError, ConnectionRefusedError) as e:
                logger.warning(f"⚠️ Redis Connection Error (attempt {attempt+1}/{max_retries}): {e}")
                # Force reconnection
                if self._redis:
                    try:
                        await self._redis.close()
                    except:
                        pass
                self._redis = None
                
                if attempt == max_retries - 1:
                    raise
                
                # Small backoff before retry
                await asyncio.sleep(0.5)

    
    async def should_buffer(self, phone_number: str, message_text: str) -> tuple[bool, Optional[str]]:
        """
        Determina si un mensaje debe ser buffeado o procesado.
        
        Args:
            phone_number: Número de teléfono del usuario
            message_text: Texto del mensaje actual
            
        Returns:
            tuple: (should_wait, accumulated_text)
                - should_wait: True si debe esperar más fragmentos
                - accumulated_text: Texto acumulado si está listo para procesar
        """
        async def _do_buffer():
            key = self._get_key(phone_number)
            current_time = time.time()
            
            # Obtener buffer actual si existe
            buffer_data = await self._redis.hgetall(key)
            
            if buffer_data:
                # Hay buffer existente
                accumulated = buffer_data.get("text", "")
                first_timestamp = float(buffer_data.get("first_timestamp", current_time))
                last_timestamp = float(buffer_data.get("last_timestamp", current_time))
                fragment_count = int(buffer_data.get("fragment_count", 0))
                
                time_since_last = current_time - last_timestamp
                
                logger.debug(f"📦 Buffer existente para {phone_number[:6]}***: {fragment_count} fragmentos, {time_since_last:.1f}s desde último")
                
                if time_since_last < self.buffer_timeout:
                    # Aún dentro del tiempo de buffer, acumular
                    new_text = accumulated + " " + message_text
                    
                    await self._redis.hset(key, mapping={
                        "text": new_text,
                        "first_timestamp": str(first_timestamp),
                        "last_timestamp": str(current_time),
                        "fragment_count": str(fragment_count + 1)
                    })
                    await self._redis.expire(key, self.ttl)
                    
                    logger.info(f"📥 Mensaje buffeado ({fragment_count + 1} fragmentos): {phone_number[:6]}***")
                    
                    # Esperar más fragmentos
                    return (True, None)
                else:
                    # Timeout excedido, procesar buffer acumulado
                    logger.info(f"⏰ Timeout de buffer alcanzado para {phone_number[:6]}***, procesando {fragment_count} fragmentos")
                    
                    # Limpiar buffer
                    await self._redis.delete(key)
                    
                    # Procesar texto acumulado + mensaje actual
                    final_text = accumulated + " " + message_text
                    return (False, final_text)
            else:
                # No hay buffer, crear uno nuevo
                await self._redis.hset(key, mapping={
                    "text": message_text,
                    "first_timestamp": str(current_time),
                    "last_timestamp": str(current_time),
                    "fragment_count": "1"
                })
                await self._redis.expire(key, self.ttl)
                
                logger.debug(f"📤 Nuevo buffer creado para {phone_number[:6]}***")
                
                # Esperar un momento para ver si llegan más fragmentos
                return (True, None)

        return await self._execute_with_retry(_do_buffer)
    
    async def flush_buffer(self, phone_number: str) -> Optional[str]:
        """
        Fuerza el flush del buffer y retorna el texto acumulado.
        
        Args:
            phone_number: Número de teléfono del usuario
            
        Returns:
            str: Texto acumulado o None si no hay buffer
        """
        async def _do_flush():
            key = self._get_key(phone_number)
            
            # TRANSACCIÓN ATÓMICA: GET + DEL (Manual Pipeline)
            pipe = self._redis.pipeline()
            try:
                await pipe.watch(key)
                
                exists = await pipe.exists(key)
                if not exists:
                    await pipe.unwatch()
                    return None
                
                pipe.multi()
                await pipe.hgetall(key)
                await pipe.delete(key)
                results = await pipe.execute()
                
                if results and results[0]:
                    buffer_data = results[0]
                    accumulated = buffer_data.get("text", "")
                    logger.info(f"🔄 Buffer flushed ATÓMICAMENTE para {phone_number[:6]}***")
                    return accumulated
                
                return None
                    
            except aioredis.WatchError:
                logger.debug(f"🛑 Race condition evitada en flush para {phone_number[:6]}***")
                return None
                
        return await self._execute_with_retry(_do_flush)
    
    async def has_pending_buffer(self, phone_number: str) -> bool:
        """Verifica si hay un buffer pendiente."""
        async def _do_check():
            key = self._get_key(phone_number)
            return bool(await self._redis.exists(key))
        return await self._execute_with_retry(_do_check)

    def _get_typing_key(self, phone_number: str) -> str:
        """Genera la clave para el estado 'escribiendo'."""
        return f"typing:{phone_number}"

    async def set_typing(self, phone_number: str):
        """Registra que el usuario está escribiendo."""
        async def _do_set_typing():
            key = self._get_typing_key(phone_number)
            await self._redis.set(key, "typing", ex=self.ttl)
        await self._execute_with_retry(_do_set_typing)

    async def is_typing(self, phone_number: str) -> bool:
        """Verifica si el usuario está escribiendo."""
        async def _do_is_typing():
            key = self._get_typing_key(phone_number)
            return bool(await self._redis.exists(key))
        return await self._execute_with_retry(_do_is_typing)

    # ============================================================
    # GESTIÓN DE INTERRUPCIONES (Active Task Tracking)
    # ============================================================
    
    def _get_active_task_key(self, phone_number: str) -> str:
        """Genera la clave para el ID de tarea activa."""
        return f"active_task:{phone_number}"

    async def set_active_task(self, phone_number: str, task_id: str):
        """
        Establece cuál es la tarea activa actual para este usuario.
        Cualquier tarea anterior verifica esto y se cancela si no coincide.
        """
        async def _do_set_task():
            key = self._get_active_task_key(phone_number)
            # TTL de 5 min por seguridad (no queremos claves huerfanas)
            await self._redis.set(key, task_id, ex=300)
            logger.debug(f"📌 Tarea activa establecida para {phone_number[:6]}***: {task_id}")
            
        await self._execute_with_retry(_do_set_task)

    async def is_task_active(self, phone_number: str, task_id: str) -> bool:
        """
        Verifica si la tarea dada sigue siendo la activa/oficial.
        Retorna False si el usuario envió otro mensaje y cambió el ID activo.
        """
        async def _do_check_task():
            key = self._get_active_task_key(phone_number)
            current_active = await self._redis.get(key)
            
            # Si no hay tarea activa registrada, asumimos que esta es válida (o expiró)
            if not current_active:
                return True
                
            return current_active == task_id
            
        return await self._execute_with_retry(_do_check_task)


async def wait_for_buffer_completion(
    buffer: MessageBuffer,
    phone_number: str,
    wait_time: float = 40.0
) -> Optional[str]:
    """
    Espera a que se complete el buffer o timeout, extendiendo si el usuario sigue escribiendo.
    """
    start_time = time.time()
    
    while time.time() - start_time < wait_time:
        await asyncio.sleep(3.0)  # Check cada 3s
        
        # Si el usuario sigue escribiendo (vía presence.update), reiniciamos el cronómetro de espera
        # pero solo hasta un máximo razonable (ej: 90s)
        USER_TYPING_TIMEOUT = 90.0
        USER_TYPING_WAITING_TIME = 3.0
        if await buffer.is_typing(phone_number) and (time.time() - start_time) < USER_TYPING_TIMEOUT:
            logger.debug(f"✍️ Usuario {phone_number[:6]}*** sigue escribiendo, extendiendo espera...")
            # No reseteamos start_time por completo para evitar bucles infinitos, 
            # pero damos un margen extra de 2s
            await asyncio.sleep(USER_TYPING_WAITING_TIME)
            continue
            
        if not await buffer.has_pending_buffer(phone_number):
            # Buffer fue procesado por otro mensaje
            return None
    
    # Timeout alcanzado, flush el buffer
    return await buffer.flush_buffer(phone_number)

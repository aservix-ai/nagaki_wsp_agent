import time
import random
import logging
import math
from typing import Optional
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

class ThinkingDelayManager:
    """
    Gestiona los tiempos de espera simulados para dar naturalidad al agente.
    Ajusta el delay basándose en:
    1. Longitud del mensaje del usuario (tiempo de lectura).
    2. Fluidez de la conversación (modo "ráfaga").
    3. Uso de herramientas (tiempo de consulta).
    """

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None
        self._closed = False
        
        # Parámetros de configuración
        self.BURST_TIMEOUT = 300  # 5 minutos para considerar que la conversación sigue "caliente"
        self.CHARS_PER_SECOND_READ = 25  # Velocidad de lectura humana promedio
        self.CHARS_PER_SECOND_WRITE = 20 # Velocidad de escritura
        self.MIN_READ_TIME = 3.0
        self.MAX_READ_TIME = 6.0
        self.BASE_THINKING_TIME = 2.0
        self.TOOL_USAGE_DELAY = (3.0, 6.0) # Rango extra si usa herramientas
        
    async def connect(self):
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url, 
                encoding="utf-8", 
                decode_responses=True,
                health_check_interval=30
            )

    async def _get_context_key(self, thread_id: str) -> str:
        return f"delay_context:{thread_id}"

    async def get_delay_parameters(self, thread_id: str, user_message_len: int, used_tools: bool = False) -> dict:
        """
        Calcula los tiempos de espera recomendados.
        
        Returns:
            dict: {
                "reading_delay": float, # Tiempo para "leer" el mensaje del usuario
                "typing_delay": float,  # Tiempo para "escribir" la respuesta (simulado)
                "thinking_delay": float # Tiempo de procesamiento interno
            }
        """
        if not self._redis: await self.connect()
        
        key = await self._get_context_key(thread_id)
        current_time = time.time()
        
        # Obtener contexto actual
        context = await self._redis.hgetall(key)
        
        last_msg_time = float(context.get("last_msg_time", 0))
        burst_count = int(context.get("burst_count", 0))
        
        # Determinar si estamos en "ráfaga" (conversación fluida)
        time_since_last = current_time - last_msg_time
        is_burst = time_since_last < self.BURST_TIMEOUT
        
        if is_burst:
            burst_count += 1
        else:
            burst_count = 1 # Reiniciar ráfaga
            
        # Actualizar contexto
        await self._redis.hset(key, mapping={
            "last_msg_time": str(current_time),
            "burst_count": str(burst_count)
        })
        await self._redis.expire(key, self.BURST_TIMEOUT)
        
        # --- CÁLCULO DE TIEMPOS ---
        
        # 1. Factor de Aceleración (mientras más mensajes seguidos, más rápido responde)
        # Decay logarítmico: empieza en 1.0, baja hasta aprox 0.6
        speed_factor = max(0.6, 1.0 - (math.log(burst_count + 1) * 0.15))
        
        if not is_burst: # Si hacía tiempo que no hablaban, resetear velocidad
            speed_factor = 1.1 # Un poco más lento al retomar
            
        logger.info(f"⏱️ Delay Context para {thread_id}: Burst={burst_count}, SpeedFactor={speed_factor:.2f}")

        # 2. Tiempo de Lectura (Simula leer el mensaje del usuario)
        read_time = user_message_len / self.CHARS_PER_SECOND_READ
        read_time = max(self.MIN_READ_TIME, min(read_time, self.MAX_READ_TIME))
        read_time *= speed_factor
        
        # 3. Tiempo de "Pensar" / Sistema
        think_time = self.BASE_THINKING_TIME * speed_factor
        if used_tools:
            # Si consultó herramientas, añadir delay significativo y variable
            tool_delay = random.uniform(*self.TOOL_USAGE_DELAY)
            think_time += tool_delay
            logger.info(f"🛠️ Detectado uso de herramientas -> Añadiendo delay extra de {tool_delay:.1f}s")
        
        # Añadir aleatoriedad natural (+- 20%)
        think_time *= random.uniform(0.8, 1.2)
        
        return {
            "reading_delay": read_time,
            "thinking_delay": think_time,
            "total_delay": read_time + think_time
        }

    async def simulate_typing_pause(self, response_text: str, speed_factor: float = 1.0):
        """
        Calcula cuánto tiempo tardaría en 'escribir' la respuesta.
        Útil para delays entre chunks de mensajes.
        """
        length = len(response_text)
        typing_time = length / self.CHARS_PER_SECOND_WRITE
        typing_time *= speed_factor
        # Límites razonables por mensaje
        return max(1.5, min(typing_time, 5.0))

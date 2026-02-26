
import asyncio
import sys
import os
import time
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

# Allow importing from src
sys.path.append(os.getcwd())

async def concurrent_buffer_test():
    print(f"🧪 [{datetime.now().time()}] Iniciando prueba de concurrencia de buffer...")
    
    # 0. Importar módulo bajo prueba
    try:
        from src.support.utils.message_buffer import MessageBuffer
    except ImportError as e:
        print(f"❌ Error importando: {e}")
        return

    # Usar Redis real (debe estar corriendo en docker)
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Configurar timeout CORTO para la prueba (2s)
    buffer_timeout = 2
    ttl = 10
    
    print(f"⚙️ Configurando buffer: timeout={buffer_timeout}s, ttl={ttl}s")
    
    buffer = MessageBuffer(redis_url=redis_url, buffer_timeout=buffer_timeout, ttl=ttl)
    await buffer.connect()
    
    phone = f"test_{int(time.time())}"
    
    # 1. Simular llegada rápida de 3 mensajes
    print("📨 Enviando ráfaga de 3 mensajes...")
    
    results = []
    
    async def process_message(text, msg_id):
        # Simula lo que hace el webhook
        should_wait, acc = await buffer.should_buffer(phone, text)
        print(f"   Mensaje {msg_id}: should_wait={should_wait}, acc={bool(acc)}")
        
        if should_wait:
            from src.support.utils.message_buffer import wait_for_buffer_completion
            final_text = await wait_for_buffer_completion(buffer, phone, wait_time=buffer_timeout)
            return final_text
        return acc

    # Lanzar 3 tareas "casi" simultáneas
    t1 = asyncio.create_task(process_message("Hola", 1))
    await asyncio.sleep(0.5)
    t2 = asyncio.create_task(process_message("busco", 2))
    await asyncio.sleep(0.5)
    t3 = asyncio.create_task(process_message("piso", 3))
    
    # Esperar resultados
    r1, r2, r3 = await asyncio.gather(t1, t2, t3)
    
    print("\n📊 Resultados:")
    print(f"Task 1 result: {r1}")
    print(f"Task 2 result: {r2}")
    print(f"Task 3 result: {r3}")
    
    # VERIFICACIÓN
    # Solo UNA tarea debe devolver el texto completo. Las demás None.
    valid_results = [r for r in [r1, r2, r3] if r]
    
    if len(valid_results) == 1:
        print(f"✅ ÉXITO: Solo una tarea obtuvo el resultado final: '{valid_results[0]}'")
        if "Hola busco piso" in valid_results[0]:
             print("✅ ÉXITO: El texto está completo y ordenado.")
        else:
             print(f"⚠️ Warning: El texto no parece estar concatenado correctamente: {valid_results[0]}")
    elif len(valid_results) == 0:
        print("❌ FALLO: Ninguna tarea devolvió resultado (pérdida de datos).")
    else:
        print(f"❌ FALLO: Múltiples tareas devolvieron resultado (duplicados): {valid_results}")

    await buffer.close()

if __name__ == "__main__":
    asyncio.run(concurrent_buffer_test())

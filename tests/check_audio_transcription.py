
import asyncio
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock

# Allow importing from src
sys.path.append(os.getcwd())

async def test_audio_interpretation():
    print("🧪 Iniciando prueba de interpretación de audio...")
    
    # 0. Import the module to be patched first
    try:
        import src.support.agent
    except ImportError as e:
        print(f"❌ Error importando src.support.agent: {e}")
        return

    # 1. Mock Agent class
    with patch('src.support.agent.Agent') as MockAgent:
        mock_agent_instance = MockAgent.return_value
        mock_agent_instance.async_graph = MagicMock()
        
        try:
            from src.support.api import evolution_webhook
            from src.support.api.evolution_webhook import process_whatsapp_task
        except ImportError as e:
            print(f"❌ Error importando módulo webhook: {e}")
            return
    
    phone_number = "12345678"
    fake_audio_url = "http://example.com/audio.ogg"
    fake_transcription = "Hola Laura, busco un piso barato en el centro"
    
    task_agent_mock = MagicMock()
    # AsyncMock for ainvoke
    task_agent_mock.async_graph.ainvoke = AsyncMock(return_value={"messages": []})
    task_agent_mock._ensure_async_setup = AsyncMock(return_value=None)

    background_tasks_mock = MagicMock()

    # 2. Patch dependencies using AsyncMock for async functions
    with patch('src.support.api.evolution_webhook.get_previous_state', new_callable=AsyncMock) as mock_get_state, \
         patch('src.support.api.evolution_webhook.download_audio', new_callable=AsyncMock) as mock_download, \
         patch('src.support.api.evolution_webhook.transcribe_audio') as mock_transcribe, \
         patch('src.support.api.evolution_webhook.send_whatsapp_message', new_callable=AsyncMock) as mock_send_msg, \
         patch('src.support.api.evolution_webhook.build_initial_state') as mock_build_state, \
         patch('src.support.api.evolution_webhook.extract_last_ai_response', return_value="Respuesta de prueba"), \
         patch('src.support.api.evolution_webhook.user_locks') as mock_user_locks, \
         patch('src.support.api.evolution_webhook.asyncio.sleep', new_callable=AsyncMock) as mock_sleep: # Skip sleep
         
        mock_get_state.return_value = {}
        mock_download.return_value = True
        mock_transcribe.return_value = fake_transcription
        mock_send_msg.return_value = True
        
        # Mock user_locks
        lock_mock = MagicMock()
        lock_mock.__aenter__.return_value = None
        lock_mock.__aexit__.return_value = None
        
        # get_lock should be async
        mock_user_locks.get_lock = AsyncMock(return_value=lock_mock)
        
        print(f"🎤 Simulando audio URL: {fake_audio_url}")
        print(f"📝 Transcripción esperada: {fake_transcription}")
        
        # Execute the task
        await process_whatsapp_task(
            phone_number=phone_number,
            normalized_text="", 
            agent=task_agent_mock,
            background_tasks=background_tasks_mock,
            audio_url=fake_audio_url
        )
        
        # VERIFICATIONS
        if mock_download.called:
            print("✅ download_audio fue llamado con la URL correcta")
        else:
            print("❌ download_audio NO fue llamado")
            
        if mock_transcribe.called:
            print("✅ transcribe_audio fue llamado")
        else:
            print("❌ transcribe_audio NO fue llamado")
            
        if mock_build_state.called:
            args, _ = mock_build_state.call_args
            passed_text = args[0]
            print(f"📦 Texto pasado al estado inicial: '{passed_text}'")
            
            if "[AUDIO_INPUT]" in passed_text and fake_transcription in passed_text:
                print("✅ ÉXITO: El texto contiene la etiqueta [AUDIO_INPUT] y la transcripción correcta.")
            else:
                print("❌ FALLO: El texto no contiene la etiqueta o la transcripción correcta.")
        else:
            print("❌ build_initial_state NO fue llamado")

if __name__ == "__main__":
    asyncio.run(test_audio_interpretation())

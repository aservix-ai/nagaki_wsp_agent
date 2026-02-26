
import os
import logging
from pathlib import Path
import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)

# Configuración
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM" # Rachel (default) or any other

client = OpenAI(api_key=OPENAI_API_KEY)

async def download_audio(url: str, save_path: str) -> bool:
    """
    Descarga un archivo de audio desde una URL.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                return True
            logger.error(f"Error descargando audio: {response.status_code}")
            logger.error(f"Error descargando audio: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error descargando audio: {e}")
        return False

import base64

def save_base64_audio(base64_string: str, save_path: str) -> bool:
    """Guarda un string base64 como archivo de audio."""
    try:
        # Evolution API a veces envía el prefijo data:audio/ogg;base64,
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]
            
        audio_data = base64.b64decode(base64_string)
        with open(save_path, "wb") as f:
            f.write(audio_data)
        return True
    except Exception as e:
        logger.error(f"Error guardando audio base64: {e}")
        return False

def transcribe_audio(file_path: str) -> str:
    """
    Transcribe un archivo de audio usando OpenAI Whisper.
    """
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY no configurada")
        return ""
        
    try:
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
        return transcript.text
    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}")
        return ""

async def generate_voice(text: str, output_path: str) -> bool:
    """
    Genera audio a partir de texto usando ElevenLabs.
    """
    if not ELEVENLABS_API_KEY:
        logger.error("ELEVENLABS_API_KEY no configurada")
        return False

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=headers, timeout=30.0)
            
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                return True
            else:
                logger.error(f"Error ElevenLabs: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"Error generando voz: {e}")
        return False

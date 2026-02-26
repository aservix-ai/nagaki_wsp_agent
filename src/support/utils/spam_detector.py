"""
Sistema de Detección de Spam y Usuarios Problemáticos

Este módulo detecta comportamientos abusivos como:
- Mensajes muy seguidos (flooding)
- Lenguaje ofensivo/insultos
- Mensajes sin sentido (gibberish)
- Mensajes repetitivos

Sistema de Strikes:
- 0-2 strikes: Usuario normal
- 3-4 strikes: Advertencia
- 5+ strikes: Usuario bloqueado
"""

import re
import time
import logging
from typing import Dict, List, Tuple, Optional
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SpamDetector:
    """
    Detecta patrones de spam y comportamiento abusivo.
    """
    
    # Lista de palabras ofensivas/insultos (en español)
    OFFENSIVE_WORDS = [
        # Insultos comunes
        "idiota", "estúpid", "imbécil", "tonto", "tonta", "bolud", 
        "pendejo", "pendeja", "mierda", "carajo", "estafador", "estafadora",
        "basura", "porquería", "puta", "puto", "hijo de", "hdp",
        "maldito", "maldita", "inútil", "incompetent", "chingar",
        # Groserías
        "verga", "coño", "concha", "pija", "chingad", "joder",
        "cagar", "cagad", "mamon", "mamona", "culero", "culera",
        # Palabras agresivas
        "cállate", "callate", "cierr", "largate", "vete a la",
    ]
    
    # Patrones de gibberish (mensajes sin sentido)
    GIBBERISH_PATTERNS = [
        r'^[aeiou]{5,}$',  # aaaaa, eeeee
        r'^[^aeiou]{7,}$',  # consonantes repetidas
        r'(.)\1{4,}',  # Carácter repetido 5+ veces
        r'^[0-9]+$',  # Solo números
        r'^[!@#$%^&*()_+=\-\[\]{};:\'",.<>?/\\|`~]+$',  # Solo símbolos
        r'^[a-z]{1,2}$',  # Mensajes de 1-2 letras (salvo casos válidos)
    ]
    
    # Mensajes válidos de 1-2 letras
    VALID_SHORT_MESSAGES = ["si", "no", "ok", "ya", "ah", "oh", "eh", "a"]
    
    def __init__(self, 
                 max_messages_per_minute: int = 8,
                 max_messages_per_10_seconds: int = 4,
                 strike_threshold: int = 5,
                 warning_threshold: int = 3):
        """
        Inicializa el detector de spam.
        
        Args:
            max_messages_per_minute: Máximo de mensajes por minuto
            max_messages_per_10_seconds: Máximo de mensajes en 10 segundos
            strike_threshold: Strikes para bloquear usuario
            warning_threshold: Strikes para advertir
        """
        self.max_messages_per_minute = max_messages_per_minute
        self.max_messages_per_10_seconds = max_messages_per_10_seconds
        self.strike_threshold = strike_threshold
        self.warning_threshold = warning_threshold
        
        # Tracking por usuario: {phone_number: deque of timestamps}
        self.message_history: Dict[str, deque] = {}
        
        # Strikes por usuario: {phone_number: int}
        self.user_strikes: Dict[str, int] = {}
        
        # Últimos mensajes por usuario (para detectar repetición)
        self.recent_messages: Dict[str, deque] = {}
        
        # Usuarios bloqueados: {phone_number: timestamp_blocked}
        self.blocked_users: Dict[str, float] = {}
        
        # Usuarios advertidos: {phone_number: warning_count}
        self.warned_users: Dict[str, int] = {}
    
    def check_message(self, phone_number: str, message: str) -> Tuple[bool, str, int]:
        """
        Verifica si un mensaje es spam y retorna el veredicto.
        
        Args:
            phone_number: Número de teléfono del usuario
            message: Contenido del mensaje
            
        Returns:
            Tuple[bool, str, int]: (is_spam, reason, strikes)
                - is_spam: True si es spam/bloqueado
                - reason: Razón de detección
                - strikes: Número actual de strikes
        """
        # Verificar si el usuario está bloqueado
        if self.is_blocked(phone_number):
            return True, "Usuario bloqueado", self.user_strikes.get(phone_number, 0)
        
        current_time = time.time()
        strikes_added = 0
        reasons = []
        
        # 1. Verificar flooding (mensajes muy seguidos)
        flooding_result = self._check_flooding(phone_number, current_time)
        if flooding_result:
            strikes_added += flooding_result["strikes"]
            reasons.append(flooding_result["reason"])
        
        # 2. Verificar lenguaje ofensivo
        offensive_result = self._check_offensive_language(message)
        if offensive_result:
            strikes_added += offensive_result["strikes"]
            reasons.append(offensive_result["reason"])
        
        # 3. Verificar gibberish (mensajes sin sentido)
        gibberish_result = self._check_gibberish(message)
        if gibberish_result:
            strikes_added += gibberish_result["strikes"]
            reasons.append(gibberish_result["reason"])
        
        # 4. Verificar mensajes repetitivos
        repetition_result = self._check_repetition(phone_number, message)
        if repetition_result:
            strikes_added += repetition_result["strikes"]
            reasons.append(repetition_result["reason"])
        
        # Actualizar strikes
        if strikes_added > 0:
            self.user_strikes[phone_number] = self.user_strikes.get(phone_number, 0) + strikes_added
            total_strikes = self.user_strikes[phone_number]
            
            logger.warning(
                f"🚨 Spam detectado de {phone_number[:6]}***: {', '.join(reasons)} "
                f"(+{strikes_added} strikes, total: {total_strikes})"
            )
            
            # Verificar si debe ser bloqueado
            if total_strikes >= self.strike_threshold:
                self._block_user(phone_number)
                return True, f"BLOQUEADO: {', '.join(reasons)}", total_strikes
            
            # Verificar si debe ser advertido
            elif total_strikes >= self.warning_threshold:
                if phone_number not in self.warned_users:
                    self.warned_users[phone_number] = 1
                    logger.warning(f"⚠️ Usuario {phone_number[:6]}*** recibió primera advertencia")
                    return False, f"ADVERTENCIA: {', '.join(reasons)}", total_strikes
        
        # Registrar mensaje normal
        self._record_message(phone_number, message, current_time)
        
        return False, "", self.user_strikes.get(phone_number, 0)
    
    def _check_flooding(self, phone_number: str, current_time: float) -> Optional[Dict]:
        """Verifica si el usuario está enviando mensajes muy seguidos."""
        if phone_number not in self.message_history:
            return None
        
        history = self.message_history[phone_number]
        
        # Limpiar mensajes antiguos (>1 minuto)
        while history and current_time - history[0] > 60:
            history.popleft()
        
        # Contar mensajes en última minuto
        messages_last_minute = len(history)
        
        # Contar mensajes en últimos 10 segundos
        messages_last_10_seconds = sum(
            1 for ts in history if current_time - ts <= 10
        )
        
        # Verificar límites
        if messages_last_10_seconds >= self.max_messages_per_10_seconds:
            return {
                "strikes": 2,
                "reason": f"Flooding: {messages_last_10_seconds} mensajes en 10 segundos"
            }
        
        if messages_last_minute >= self.max_messages_per_minute:
            return {
                "strikes": 1,
                "reason": f"Flooding: {messages_last_minute} mensajes en 1 minuto"
            }
        
        return None
    
    def _check_offensive_language(self, message: str) -> Optional[Dict]:
        """Verifica si el mensaje contiene lenguaje ofensivo."""
        message_lower = message.lower()
        
        # Buscar palabras ofensivas
        for word in self.OFFENSIVE_WORDS:
            if word in message_lower:
                return {
                    "strikes": 3,  # Insultos son muy graves
                    "reason": f"Lenguaje ofensivo detectado"
                }
        
        return None
    
    def _check_gibberish(self, message: str) -> Optional[Dict]:
        """Verifica si el mensaje es gibberish (sin sentido)."""
        # Ignorar mensajes muy cortos válidos
        message_clean = message.strip().lower()
        
        if len(message_clean) <= 2:
            if message_clean in self.VALID_SHORT_MESSAGES:
                return None
        
        # Si el mensaje es muy corto y NO está en la lista válida
        if len(message_clean) <= 2:
            return {
                "strikes": 1,
                "reason": "Mensaje demasiado corto sin sentido"
            }
        
        # Verificar patrones de gibberish
        for pattern in self.GIBBERISH_PATTERNS:
            if re.search(pattern, message_clean, re.IGNORECASE):
                return {
                    "strikes": 1,
                    "reason": "Mensaje sin sentido (gibberish)"
                }
        
        return None
    
    def _check_repetition(self, phone_number: str, message: str) -> Optional[Dict]:
        """Verifica si el usuario está repitiendo el mismo mensaje."""
        if phone_number not in self.recent_messages:
            return None
        
        recent = self.recent_messages[phone_number]
        message_normalized = message.strip().lower()
        
        # Contar cuántas veces aparece este mensaje
        repetition_count = sum(1 for msg in recent if msg == message_normalized)
        
        if repetition_count >= 3:
            return {
                "strikes": 2,
                "reason": f"Mensaje repetido {repetition_count} veces"
            }
        
        return None
    
    def _record_message(self, phone_number: str, message: str, timestamp: float):
        """Registra un mensaje para tracking."""
        # Registrar timestamp
        if phone_number not in self.message_history:
            self.message_history[phone_number] = deque(maxlen=20)
        self.message_history[phone_number].append(timestamp)
        
        # Registrar contenido (últimos 10 mensajes)
        if phone_number not in self.recent_messages:
            self.recent_messages[phone_number] = deque(maxlen=10)
        self.recent_messages[phone_number].append(message.strip().lower())
    
    def _block_user(self, phone_number: str):
        """Bloquea a un usuario."""
        self.blocked_users[phone_number] = time.time()
        logger.error(f"🚫 Usuario {phone_number[:6]}*** ha sido BLOQUEADO por spam")
    
    def is_blocked(self, phone_number: str) -> bool:
        """Verifica si un usuario está bloqueado."""
        return phone_number in self.blocked_users
    
    def unblock_user(self, phone_number: str) -> bool:
        """
        Desbloquea a un usuario y resetea sus strikes.
        
        Returns:
            bool: True si se desbloqueó, False si no estaba bloqueado
        """
        if phone_number in self.blocked_users:
            del self.blocked_users[phone_number]
            self.user_strikes[phone_number] = 0
            logger.info(f"✅ Usuario {phone_number[:6]}*** ha sido desbloqueado")
            return True
        return False
    
    def get_user_status(self, phone_number: str) -> Dict:
        """
        Obtiene el estado actual de un usuario.
        
        Returns:
            Dict con strikes, bloqueado, advertencias, etc.
        """
        return {
            "phone": phone_number,
            "strikes": self.user_strikes.get(phone_number, 0),
            "blocked": self.is_blocked(phone_number),
            "warnings": self.warned_users.get(phone_number, 0),
            "blocked_since": self.blocked_users.get(phone_number),
        }
    
    def reset_user_strikes(self, phone_number: str):
        """Resetea los strikes de un usuario (sin desbloquearlo)."""
        self.user_strikes[phone_number] = 0
        if phone_number in self.warned_users:
            del self.warned_users[phone_number]
        logger.info(f"🔄 Strikes reseteados para {phone_number[:6]}***")


# Instancia global del detector
spam_detector = SpamDetector()

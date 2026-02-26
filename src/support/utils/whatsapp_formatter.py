"""
Formateador de mensajes para WhatsApp - Grupo Nagaki

Este módulo proporciona funciones para formatear mensajes de manera natural
para WhatsApp, incluyendo:
- División de mensajes largos en bloques cortos
- Aplicación de formato markdown de WhatsApp
- Preservación de contexto al dividir mensajes
"""

import re
from typing import List


class WhatsAppFormatter:
    """Formateador de mensajes para WhatsApp con división inteligente."""
    
    # Límites de longitud
    MAX_MESSAGE_LENGTH = 150  # Caracteres por mensaje (más corto para parecer humano)
    MAX_CHUNKS = 6  # Más bloques permitidos si se divide por frases
    
    # Patrones de formato WhatsApp
    # *texto* = negrita, _texto_ = cursiva, ```texto``` = monoespaciado
    
    def __init__(self):
        """Inicializa el formateador."""
        pass
    
    @staticmethod
    def limit_emojis(text: str, max_emojis: int = 1) -> str:
        """
        Limita la cantidad de emojis en un texto.
        
        Args:
            text: Texto original
            max_emojis: Máximo de emojis permitidos
            
        Returns:
            str: Texto con emojis limitados
        """
        import emoji
        emoji_list = emoji.emoji_list(text)
        if len(emoji_list) <= max_emojis:
            return text
            
        # Mantener solo los primeros N emojis
        new_text = ""
        emojis_count = 0
        last_idx = 0
        
        for em in emoji_list:
            if emojis_count < max_emojis:
                emojis_count += 1
                continue
            
            # Reemplazar emoji excedente por nada
            start = em['match_start']
            end = em['match_end']
            
            # Este es un enfoque simple, funcionará para la mayoría de los casos
            # Podríamos ser más precisos pero esto suele bastar
            text = text[:start] + " " + text[end:]
            # Re-encontrar emojis después de modificar el string
            return WhatsAppFormatter.limit_emojis(text, max_emojis)
            
        return text

    @staticmethod
    def apply_whatsapp_format(text: str) -> str:
        """
        Aplica formato markdown de WhatsApp automáticamente.
        """
        if not text:
            return text
            
        # 1. Normalizar Markdown de LLM a WhatsApp
        # Convertir **bold** a *bold*
        text = text.replace("**", "*")
        # Convertir __italic__ a _italic_ (aunque menos común)
        text = text.replace("__", "_")
        
        # ELIMINAR SIGNOS DE APERTURA (Estilo Grupo Nagaki)
        text = text.replace("¿", "").replace("¡", "")
        
        # Limitar emojis primero
        text = WhatsAppFormatter.limit_emojis(text, max_emojis=1)
        
        # Aplicar negrita a montos de dinero (ej: €100,000)
        text = re.sub(r'(€\s*[\d,]+(?:\.\d{2})?)', r'*\1*', text)
        text = re.sub(r'(\$\s*[\d,]+(?:\.\d{2})?)', r'*\1*', text)
        
        # Aplicar monoespaciado a rangos de precio
        text = re.sub(r'(€[\d,]+-€[\d,]+)', r'```\1```', text)
        
        # Keywords importantes en negrita (SOLO si no tienen ya asteriscos)
        # Usamos lookaround para asegurarnos que no estamos dentro de unos asteriscos ya
        keywords = [
            'Cesión de Remate', 'NPL', 'Ocupado', 'Libre',
            'NO visitable', 'NO hipotecable',
            'capital propio', 'al contado'
        ]
        
        for keyword in keywords:
            # Simple check: si la keyword existe y no está rodeada de *, la rodeamos.
            # Regex: (?<!\*)KEYWORD(?!\*)
            # Esto evita ***KEYWORD*** o **KEYWORD**
            pattern = r'(?<!\*)' + re.escape(keyword) + r'(?!\*)'
            text = re.sub(pattern, f'*{keyword}*', text, flags=re.IGNORECASE)
        
        # Cleanup: Avoid triple asterisks that might happen if logic fails
        text = text.replace("***", "*")
        
        return text
    
    @staticmethod
    def split_into_chunks(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> List[str]:
        """
        Divide un texto en bloques cortos por frases.
        """
        if not text:
            return []
            
        # Dividir por frases pero protegiendo listas numeradas
        # No dividir si el punto está precedido por un dígito (ej: "1.")
        # Regex explanation:
        # (?<=[^0-9][.!?]) : Positive lookbehind - ensure preceded by non-digit then punct
        # \s+              : Match whitespace
        sentences = re.split(r'(?<=[^0-9][.!?])\s+', text.strip())
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Forzar división si el mensaje anterior ya tiene una longitud mínima
            # o si simplemente queremos que cada frase sea un mensaje (más humano)
            if current_chunk:
                # Si el chunk actual ya es suficientemente largo (>60 chars)
                # o si la nueva frase lo haría muy largo, dividimos.
                if len(current_chunk) > 60 or len(current_chunk) + len(sentence) > max_length:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    current_chunk += " " + sentence
            else:
                current_chunk = sentence
                
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks[:WhatsAppFormatter.MAX_CHUNKS]
    
    @classmethod
    def format_message(cls, text: str, apply_format: bool = True) -> List[str]:
        """
        Formatea un mensaje completo: divide en chunks y aplica formato.
        """
        if not text or not text.strip():
            return []
        
        text = text.strip()
        
        # Dividir en chunks PRIMERO para que cada mensaje sea independiente
        chunks = cls.split_into_chunks(text)
        
        # Aplicar formato y limitar emojis a cada chunk
        final_chunks = []
        import emoji
        
        for chunk in chunks:
            if apply_format:
                chunk = cls.apply_whatsapp_format(chunk)
            
            # Verificar si el chunk es SOLO emojis
            # Eliminamos todos los emojis y vemos si queda texto
            text_without_emojis = emoji.replace_emoji(chunk, replace='').strip()
            
            # Si no queda texto (es solo emoji) y el chunk no estaba vacío, lo saltamos
            # Sin embargo, si el chunk era SOLO un emoji desde el principio (ej: respuesta corta), 
            # Asumimos que es un chunk extra no deseado.
            # Si el chunk es solo emojis, lo ignoramos para evitar mensajes "sueltos" de emojis
            if not text_without_emojis and chunk.strip():
                continue
                
            if chunk.strip():
                final_chunks.append(chunk)
        
        return final_chunks


def format_for_whatsapp(text: str) -> List[str]:
    """
    Función helper para formatear un mensaje para WhatsApp.
    """
    formatter = WhatsAppFormatter()
    return formatter.format_message(text)

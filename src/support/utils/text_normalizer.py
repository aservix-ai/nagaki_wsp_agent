"""
Normalizador de texto con corrección ortográfica - Grupo Nagaki

Este módulo proporciona funciones para normalizar y corregir texto
de usuarios, incluyendo:
- Corrección ortográfica con symspellpy
- Normalización de sinónimos
- Limpieza de texto
"""

import re
import logging
import unicodedata
from typing import Optional, Set, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

# Intentar importar symspellpy (opcional)
try:
    from symspellpy import SymSpell, Verbosity
    SYMSPELL_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ symspellpy no disponible. Corrección ortográfica deshabilitada.")
    SYMSPELL_AVAILABLE = False


class TextNormalizer:
    """
    Normalizador de texto con corrección ortográfica y manejo de sinónimos.
    """
    
    # Diccionario de sinónimos comunes en inmobiliaria
    SYNONYMS = {
        "barato": {"económico", "accesible", "low cost", "asequible", "varato"},
        "caro": {"premium", "exclusivo", "alto precio"},
        "piso": {"apartamento", "departamento", "pizo"},
        "casa": {"vivienda", "hogar", "residencia", "chalet"},
        "zona": {"área", "sector", "barrio", "distrito"},
        "centro": {"céntrico", "downtown", "casco antiguo"},
        "cerca": {"cercano", "próximo", "al lado"},
        "libre": {"desocupado", "disponible", "vacío"},
        "ocupado": {"con okupas", "habitado", "ocupada"},
    }
    
    # Términos inmobiliarios importantes (no corregir)
    REAL_ESTATE_TERMS = {
        "NPL", "npl",
        "cesión", "remate", "cesión de remate",
        "okupas", "ocupado", "ocupada",
        "hipoteca", "hipotecable",
        "visitable", "no visitable",
        "capital propio", "al contado",
        "madrid", "barcelona", "sevilla", "valencia",
        "retiro", "salamanca", "chamartín", "chamberí",
    }
    
    def __init__(self):
        """Inicializa el normalizador."""
        self.sym_spell: Optional[SymSpell] = None
        
        if SYMSPELL_AVAILABLE:
            self._init_symspell()
    
    def _init_symspell(self):
        """Inicializa SymSpell con diccionario español."""
        try:
            self.sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
            
            # Intentar cargar diccionario español
            # Nota: symspellpy incluye diccionarios básicos
            # Para producción, se debería usar un diccionario español completo
            
            # Agregar términos inmobiliarios al diccionario
            for term in self.REAL_ESTATE_TERMS:
                self.sym_spell.create_dictionary_entry(term, 1000)  # Alta frecuencia
            
            # Agregar sinónimos al diccionario
            for key, synonyms in self.SYNONYMS.items():
                self.sym_spell.create_dictionary_entry(key, 500)
                for syn in synonyms:
                    self.sym_spell.create_dictionary_entry(syn, 300)
            
            # Palabras comunes españolas básicas
            common_words = [
                "quiero", "busco", "necesito", "tengo", "hay",
                "donde", "cuando", "como", "cuanto", "cual",
                "algo", "nada", "todo", "poco", "mucho",
                "muy", "mas", "menos", "mejor", "peor",
            ]
            for word in common_words:
                self.sym_spell.create_dictionary_entry(word, 1000)
            
            logger.info("✅ SymSpell inicializado con diccionario personalizado")
        except Exception as e:
            logger.error(f"❌ Error inicializando SymSpell: {e}")
            self.sym_spell = None
    
    def normalize_text(self, text: str, correct_spelling: bool = True) -> str:
        """
        Normaliza un texto completo.
        
        Args:
            text: Texto a normalizar
            correct_spelling: Si True, aplica corrección ortográfica
            
        Returns:
            str: Texto normalizado
        """
        if not text:
            return text
        
        # 1. Limpieza básica
        text = self._clean_text(text)
        
        # 2. Normalizar sinónimos
        text = self._normalize_synonyms(text)
        
        # 3. Corrección ortográfica (si está disponible)
        if correct_spelling and self.sym_spell:
            text = self._correct_spelling(text)
        
        return text
    
    def _clean_text(self, text: str) -> str:
        """Limpia el texto de caracteres extraños y elimina tildes."""
        # 1. Normalizar unicode (NFD) y eliminar marcas diacríticas (tildes)
        # Esto convierte "canción" -> "cancion", "está" -> "esta"
        text = ''.join(c for c in unicodedata.normalize('NFD', text)
                      if unicodedata.category(c) != 'Mn')
        
        # 2. Eliminar espacios múltiples
        text = re.sub(r'\s+', ' ', text)
        
        # 3. Eliminar caracteres especiales excepto puntuación básica
        # Preservar: . , ! ? ¿ ¡ € $ números letras espacios
        
        return text.strip()
    
    def _normalize_synonyms(self, text: str) -> str:
        """
        Normaliza sinónimos a su forma estándar.
        No reemplaza en el texto, solo ayuda a la comprensión.
        """
        # Esta función podría ser más agresiva, pero para preservar
        # la naturalidad del usuario, solo hacemos limpieza básica
        
        # Normalizar variaciones ortográficas comunes
        replacements = {
            "pizo": "piso",
            "varcelona": "barcelona",
            "varato": "barato",
            "hipotecable": "hipotecable",  # Ya correcto
        }
        
        text_lower = text.lower()
        for wrong, correct in replacements.items():
            if wrong in text_lower:
                # Reemplazar preservando mayúsculas
                pattern = re.compile(re.escape(wrong), re.IGNORECASE)
                text = pattern.sub(correct, text)
        
        return text
    
    def _correct_spelling(self, text: str) -> str:
        """
        Corrige la ortografía usando SymSpell.
        
        Args:
            text: Texto a corregir
            
        Returns:
            str: Texto corregido
        """
        if not self.sym_spell:
            return text
        
        words = text.split()
        corrected_words = []
        
        for word in words:
            # Preservar puntuación
            match = re.match(r'^(\W*)(\w+)(\W*)$', word)
            if match:
                prefix, core_word, suffix = match.groups()
                
                # No corregir palabras muy cortas o números
                if len(core_word) <= 2 or core_word.isdigit():
                    corrected_words.append(word)
                    continue
                
                # No corregir términos conocidos
                if core_word.lower() in self.REAL_ESTATE_TERMS:
                    corrected_words.append(word)
                    continue
                
                # Buscar sugerencias
                suggestions = self.sym_spell.lookup(
                    core_word.lower(),
                    Verbosity.CLOSEST,
                    max_edit_distance=2
                )
                
                if suggestions and suggestions[0].distance <= 2:
                    # Preservar mayúsculas originales
                    corrected = suggestions[0].term
                    if core_word[0].isupper():
                        corrected = corrected.capitalize()
                    
                    corrected_words.append(prefix + corrected + suffix)
                else:
                    corrected_words.append(word)
            else:
                corrected_words.append(word)
        
        return ' '.join(corrected_words)
    
    def extract_synonyms(self, word: str) -> Set[str]:
        """
        Extrae sinónimos conocidos de una palabra.
        
        Args:
            word: Palabra a buscar
            
        Returns:
            Set[str]: Conjunto de sinónimos
        """
        word_lower = word.lower()
        
        # Buscar en el diccionario de sinónimos
        for key, synonyms in self.SYNONYMS.items():
            if word_lower == key or word_lower in synonyms:
                return {key} | synonyms
        
        return {word}


# Instancia global del normalizador
_normalizer_instance: Optional[TextNormalizer] = None


def get_normalizer() -> TextNormalizer:
    """Obtiene la instancia global del normalizador."""
    global _normalizer_instance
    if _normalizer_instance is None:
        _normalizer_instance = TextNormalizer()
    return _normalizer_instance


def normalize_text(text: str, correct_spelling: bool = False) -> str:
    """
    Función helper para normalizar texto.
    
    Args:
        text: Texto a normalizar
        correct_spelling: Si True, aplica corrección ortográfica (Default False por seguridad)
        
    Returns:
        str: Texto normalizado
    """
    normalizer = get_normalizer()
    return normalizer.normalize_text(text, correct_spelling)

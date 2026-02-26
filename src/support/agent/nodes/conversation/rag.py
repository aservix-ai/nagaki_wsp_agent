"""
Sistema RAG (Retrieval Augmented Generation) para el Agente Laura

Este módulo implementa un sistema RAG que:
- Carga documentos Markdown del directorio docs_rag
- Divide los documentos usando MarkdownHeaderTextSplitter
- Crea chunks de 1024 tokens con overlap de 200 tokens
- Genera embeddings con OpenAI
- Almacena los vectores en ChromaDB
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional

import tiktoken
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
)
from langchain_chroma import Chroma
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

class RAGSystem:
    """
    Sistema RAG para recuperar información de los documentos de conocimiento.
    
    Utiliza:
    - MarkdownHeaderTextSplitter para dividir por headers
    - RecursiveCharacterTextSplitter con chunk_size=1024 y chunk_overlap=200
    - OpenAI embeddings
    - ChromaDB como vector store
    """
    
    def __init__(
        self,
        docs_dir: Optional[str] = None,
        persist_directory: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ):
        """
        Inicializa el sistema RAG.
        
        Args:
            docs_dir: Directorio donde están los documentos .md.
                     Por defecto: src/support/agent/docs_rag
            persist_directory: Directorio donde persistir ChromaDB.
                              Por defecto: ./chroma_db
            openai_api_key: API key de OpenAI. Si no se proporciona,
                          se usa OPENAI_API_KEY de las variables de entorno.
        """
        # Configurar directorios
        if docs_dir is None:
            # Obtener el directorio base del proyecto
            current_file = Path(__file__).resolve()
            # Desde conversation/rag.py subimos: conversation -> nodes -> agent -> support -> src -> root
            project_root = current_file.parent.parent.parent.parent.parent
            docs_dir = project_root / "support" / "agent" / "docs_rag"
        
        self.docs_dir = Path(docs_dir).resolve()
        
        if persist_directory is None:
            # Usar ruta absoluta para persist_directory
            persist_directory = str(Path.cwd() / "chroma_db")
        self.persist_directory = str(Path(persist_directory).resolve())
        
        # Configurar embeddings
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=openai_api_key or os.getenv("OPENAI_API_KEY")
        )
        
        # Configurar text splitters
        self._setup_text_splitters()
        
        # Inicializar vector store (se creará al cargar documentos)
        self.vector_store: Optional[Chroma] = None
    
    def _setup_text_splitters(self):
        """Configura los text splitters para dividir los documentos."""
        # MarkdownHeaderTextSplitter para dividir por headers
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on
        )
        
        # Tokenizer para contar tokens exactos (usando el mismo que OpenAI)
        # Usamos cl100k_base que es el tokenizer para text-embedding-ada-002 y GPT-4
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Función para contar tokens
        def count_tokens(text: str) -> int:
            return len(self.tokenizer.encode(text))
        
        # Crear un text splitter personalizado que respete los límites de tokens
        # Usamos RecursiveCharacterTextSplitter pero con una función de longitud
        # que cuenta tokens, y ajustamos chunk_size/chunk_overlap para aproximarnos
        # a los valores deseados (1024 tokens y 200 tokens de overlap)
        
        # Aproximación: en español, 1 token ≈ 1-2 caracteres en promedio
        # Para estar seguros, usamos una aproximación conservadora
        # Probamos con un texto de ejemplo para calibrar
        sample_text = "Este es un texto de ejemplo en español para calibrar el tokenizer. "
        sample_tokens = count_tokens(sample_text)
        chars_per_token = len(sample_text) / sample_tokens if sample_tokens > 0 else 2.5
        
        # Calcular chunk_size y chunk_overlap en caracteres para aproximarse a tokens
        chunk_size_chars = int(1024 * chars_per_token)
        chunk_overlap_chars = int(200 * chars_per_token)
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size_chars,
            chunk_overlap=chunk_overlap_chars,
            length_function=count_tokens,  # Usar conteo de tokens
            separators=["\n\n", "\n", ". ", " ", ""],
            is_separator_regex=False,
        )
    
    def _load_markdown_files(self) -> List[Document]:
        """
        Carga todos los archivos .md del directorio docs_rag.
        
        Returns:
            Lista de documentos cargados
        """
        if not self.docs_dir.exists():
            raise ValueError(f"El directorio {self.docs_dir} no existe")
        
        documents = []
        
        # Buscar todos los archivos .md
        md_files = list(self.docs_dir.glob("*.md"))
        
        if not md_files:
            raise ValueError(
                f"No se encontraron archivos .md en {self.docs_dir}\n"
                f"   Archivos encontrados en el directorio: {list(self.docs_dir.iterdir())}"
            )
        
        print(f"📄 Archivos .md encontrados: {[f.name for f in md_files]}")
        
        for md_file in md_files:
            try:
                print(f"  📖 Procesando {md_file.name}...")
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()
                
                if not content.strip():
                    print(f"  ⚠️ {md_file.name} está vacío, saltando...")
                    continue
                
                # Dividir por headers de markdown
                md_header_splits = self.markdown_splitter.split_text(content)
                print(f"    → Dividido en {len(md_header_splits)} secciones por headers")
                
                # Dividir cada sección en chunks más pequeños
                file_chunks = 0
                for split in md_header_splits:
                    # Agregar metadata del archivo fuente
                    split.metadata["source"] = str(md_file.name)
                    split.metadata["file_path"] = str(md_file)
                    
                    # Dividir en chunks con el text splitter
                    chunks = self.text_splitter.split_documents([split])
                    documents.extend(chunks)
                    file_chunks += len(chunks)
                
                print(f"    ✅ {md_file.name}: {file_chunks} chunks creados")
            
            except Exception as e:
                print(f"  ❌ Error al cargar {md_file}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return documents
    
    def initialize_vector_store(self, force_reload: bool = False):
        """
        Inicializa el vector store cargando los documentos.
        
        Args:
            force_reload: Si True, recarga los documentos incluso si ya existen.
        """
        print(f"🔍 Inicializando vector store...")
        print(f"📁 Directorio de documentos: {self.docs_dir}")
        print(f"💾 Directorio de persistencia: {self.persist_directory}")
        
        # Verificar si el directorio de documentos existe
        if not self.docs_dir.exists():
            raise ValueError(
                f"❌ El directorio de documentos no existe: {self.docs_dir}\n"
                f"   Verifica que la ruta sea correcta."
            )
        
        # Verificar si ya existe un vector store persistido
        if not force_reload and os.path.exists(self.persist_directory):
            try:
                print(f"📂 Vector store existente encontrado en {self.persist_directory}")
                # Cargar el vector store existente
                self.vector_store = Chroma(
                    persist_directory=self.persist_directory,
                    embedding_function=self.embeddings,
                )
                print(f"✅ Vector store cargado exitosamente")
                return
            except Exception as e:
                print(f"⚠️ Error al cargar vector store existente: {e}")
                print("🔄 Recargando documentos...")
                # Eliminar el directorio corrupto si existe
                if os.path.exists(self.persist_directory):
                    try:
                        shutil.rmtree(self.persist_directory)
                        print(f"🗑️ Directorio anterior eliminado")
                    except Exception as cleanup_error:
                        print(f"⚠️ No se pudo eliminar el directorio: {cleanup_error}")
        
        # Crear el directorio de persistencia si no existe
        os.makedirs(self.persist_directory, exist_ok=True)
        
        # Cargar documentos
        print(f"📖 Cargando documentos desde {self.docs_dir}...")
        try:
            documents = self._load_markdown_files()
            print(f"✅ Se cargaron {len(documents)} chunks de documentos")
            
            if len(documents) == 0:
                raise ValueError("No se cargaron documentos. Verifica que haya archivos .md en el directorio.")
            
        except Exception as e:
            print(f"❌ Error al cargar documentos: {e}")
            raise
        
        # Crear vector store
        print(f"🔨 Creando vector store con ChromaDB...")
        try:
            self.vector_store = Chroma.from_documents(
                documents=documents,
                embedding=self.embeddings,
                persist_directory=self.persist_directory,
            )
            print(f"✅ Vector store creado exitosamente")
            print(f"💾 Vector store persistido en {self.persist_directory}")
        except Exception as e:
            print(f"❌ Error al crear vector store: {e}")
            raise
    
    def get_retriever(self, k: int = 4):
        """
        Obtiene un retriever del vector store.
        
        Args:
            k: Número de documentos a recuperar
            
        Returns:
            Retriever configurado
        """
        if self.vector_store is None:
            raise ValueError(
                "El vector store no está inicializado. "
                "Llama a initialize_vector_store() primero."
            )
        
        return self.vector_store.as_retriever(search_kwargs={"k": k})
    
    def search(self, query: str, k: int = 4) -> List[Document]:
        """
        Busca documentos similares a la consulta.
        
        Args:
            query: Consulta de búsqueda
            k: Número de documentos a recuperar
            
        Returns:
            Lista de documentos relevantes
        """
        if self.vector_store is None:
            raise ValueError(
                "El vector store no está inicializado. "
                "Llama a initialize_vector_store() primero."
            )
        
        return self.vector_store.similarity_search(query, k=k)
    
    def search_with_score(self, query: str, k: int = 4) -> List[tuple]:
        """
        Busca documentos similares con sus scores de similitud.
        
        Args:
            query: Consulta de búsqueda
            k: Número de documentos a recuperar
            
        Returns:
            Lista de tuplas (Document, score)
        """
        if self.vector_store is None:
            raise ValueError(
                "El vector store no está inicializado. "
                "Llama a initialize_vector_store() primero."
            )
        
        return self.vector_store.similarity_search_with_score(query, k=k)


# Instancia global del sistema RAG (se inicializa cuando se necesite)
_rag_instance: Optional[RAGSystem] = None


def get_rag_system(
    force_reload: bool = False,
    docs_dir: Optional[str] = None,
    persist_directory: Optional[str] = None,
) -> RAGSystem:
    """
    Obtiene la instancia global del sistema RAG.
    
    Args:
        force_reload: Si True, recarga los documentos
        docs_dir: Directorio de documentos (solo en primera inicialización)
        persist_directory: Directorio de persistencia (solo en primera inicialización)
        
    Returns:
        Instancia del sistema RAG
    """
    global _rag_instance
    
    if _rag_instance is None or force_reload:
        _rag_instance = RAGSystem(
            docs_dir=docs_dir,
            persist_directory=persist_directory,
        )
        _rag_instance.initialize_vector_store(force_reload=force_reload)
    
    return _rag_instance


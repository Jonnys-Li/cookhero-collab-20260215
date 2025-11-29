import logging
from pathlib import Path
from typing import List

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.rag.config import RAGConfig

logger = logging.getLogger(__name__)

class IndexConstructionModule:
    """
    Handles the creation and persistence of the vector index.
    """
    def __init__(self, config: RAGConfig):
        """
        Initializes the index construction module.
        Args:
            config: The RAG configuration object.
        """
        self.config = config
        self.index_save_path = Path(config.INDEX_SAVE_PATH)
        self.embeddings: Embeddings = self._init_embeddings()
        self.vectorstore: FAISS | None = None

    def _init_embeddings(self) -> Embeddings:
        """Initializes the embedding model based on the configuration."""
        if self.config.EMBEDDING_MODE == 'local':
            logger.info(f"Initializing local embedding model: {self.config.LOCAL_EMBEDDING_MODEL}")
            return HuggingFaceEmbeddings(
                model_name=self.config.LOCAL_EMBEDDING_MODEL,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
        elif self.config.EMBEDDING_MODE == 'remote':
            logger.info(f"Initializing remote embedding model: {self.config.REMOTE_EMBEDDING_MODEL}")
            if not self.config.EMBEDDING_API_KEY:
                raise ValueError("EMBEDDING_API_KEY must be set in config for remote embedding mode.")
            
            # Use OpenAIEmbeddings client
            return OpenAIEmbeddings(
                model=self.config.REMOTE_EMBEDDING_MODEL,
                api_key=self.config.EMBEDDING_API_KEY, # type: ignore
                base_url=self.config.EMBEDDING_API_URL,
                # Depending on the API, you might need to add other headers or params
            )
        else:
            raise ValueError(f"Invalid EMBEDDING_MODE: {self.config.EMBEDDING_MODE}")

    def build_or_load_index(self, chunks: List[Document]):
        """
        Loads the index from disk if it exists, otherwise builds a new one from documents.
        Args:
            chunks: A list of Document chunks to be indexed if no existing index is found.
        """
        if self.index_save_path.exists():
            logger.info(f"Loading existing FAISS index from: {self.index_save_path}")
            try:
                self.vectorstore = FAISS.load_local(
                    folder_path=str(self.index_save_path),
                    embeddings=self.embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info("Successfully loaded FAISS index.")
            except Exception as e:
                logger.warning(f"Failed to load index: {e}. Rebuilding index from scratch.")
                self._build_new_index(chunks)
        else:
            logger.info("No existing index found. Building a new index from scratch.")
            self._build_new_index(chunks)
            
    def _build_new_index(self, chunks: List[Document]):
        """
        Builds a new FAISS index from the provided document chunks.
        Args:
            chunks: A list of Document chunks to be indexed.
        """
        if not chunks:
            raise ValueError("Cannot build index from an empty list of chunks.")
        
        logger.info(f"Building FAISS index from {len(chunks)} chunks...")
        self.vectorstore = FAISS.from_documents(
            documents=chunks,
            embedding=self.embeddings
        )
        logger.info("FAISS index built successfully.")
        
        self._save_index()

    def _save_index(self):
        """Saves the FAISS index to the configured path."""
        if not self.vectorstore:
            raise ValueError("Vectorstore is not initialized. Cannot save index.")
        
        self.index_save_path.mkdir(parents=True, exist_ok=True)
        self.vectorstore.save_local(str(self.index_save_path))
        logger.info(f"FAISS index saved to: {self.index_save_path}")

    def get_vectorstore(self) -> FAISS:
        """
        Returns the initialized FAISS vectorstore.
        """
        if not self.vectorstore:
            raise ValueError("Vectorstore has not been built or loaded.")
        return self.vectorstore

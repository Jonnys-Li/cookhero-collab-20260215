# app/rag/data_sources/base.py
from abc import ABC, abstractmethod
from typing import List
from langchain_core.documents import Document

class BaseDataSource(ABC):
    """
    Abstract base class for all data sources.
    """
    @abstractmethod
    def get_chunks(self) -> List[Document]:
        """
        Loads, processes, and chunks documents from the data source,
        returning the chunks that are ready to be embedded and indexed.
        
        Returns:
            A list of child chunk Document objects.
        """
        pass

    @abstractmethod
    def post_process_retrieval(self, retrieved_chunks: List[Document]) -> List[Document]:
        """
        Post-processes the chunks returned by the retriever to generate
        the final documents for the LLM context.
        
        Args:
            retrieved_chunks: The raw list of chunks from the vector store.
            
        Returns:
            A list of final Document objects (e.g., the full parent documents).
        """
        pass

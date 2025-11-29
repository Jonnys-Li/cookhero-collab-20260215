# app/rag/data_sources/base.py
from abc import ABC, abstractmethod
from typing import List
from langchain_core.documents import Document

class BaseDataSource(ABC):
    """
    Abstract base class for all data sources.
    """
    @abstractmethod
    def load_documents(self) -> List[Document]:
        """
        Loads documents from the data source.
        This method should be implemented by all concrete data source classes.
        
        Returns:
            A list of Document objects.
        """
        pass

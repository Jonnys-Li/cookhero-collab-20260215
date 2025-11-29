# Project: CookHero

## Project Overview

CookHero is an intelligent dietary assistant system designed for the general public. It provides comprehensive support throughout the cooking process, from kitchen preparation and recipe learning to nutritional planning and personalized dietary recommendations.

The backend is built primarily in Python, leveraging LangChain for Retrieval-Augmented Generation (RAG), intelligent agents, and vector retrieval. Milvus is used as the vector database for managing recipes and other data. The backend exposes a unified REST API using FastAPI.

The frontend is planned to be developed using React and TypeScript to provide a user-friendly interface for interacting with the system.

## Key Technologies

*   **Backend:** Python, FastAPI, LangChain, Milvus
*   **Frontend:** React, TypeScript
*   **Database:** Milvus (Vector DB), Relational Database (for structured data)
*   **Key Concepts:** Retrieval-Augmented Generation (RAG), Intelligent Agents, Vector Search, Multi-modal Embeddings

## Building and Running

**TODO:** The build and run commands are not yet defined. This section should be updated with instructions on how to set up the development environment, build the project, and run the application.

-   **Backend:** Instructions for setting up the Python environment, installing dependencies (e.g., from a `requirements.txt` file), and running the FastAPI server.
-   **Frontend:** Instructions for setting up the Node.js environment, installing dependencies (e.g., from a `package.json` file), and starting the React development server.

## Development Conventions

The project follows a modular architecture with a clear separation between the frontend, backend, and intelligent engine layers.

*   **High Cohesion, Low Coupling:** Modules are designed to be independent and communicate through standardized interfaces.
*   **Code Style:** While not explicitly defined, it's recommended to follow standard Python (PEP 8) and TypeScript style guides.
*   **Testing:** **TODO:** Testing practices are not yet defined. It is recommended to add unit and integration tests for each module.

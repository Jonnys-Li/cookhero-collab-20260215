#!/usr/bin/env python3
"""
Render startup script for CookHero backend.
Ensures quick port binding for successful deployment.
"""

import os
import sys

# Ensure output is not buffered
os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

def main():
    # Check required environment variables
    port = os.getenv("PORT")
    if not port:
        print("ERROR: PORT environment variable not set", file=sys.stderr)
        sys.exit(1)

    print(f"Starting CookHero backend on port {port}...")
    print(f"Python version: {sys.version}")

    # Import and run uvicorn
    import uvicorn

    # Run the application
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(port),
        log_level="info",
        access_log=True,
        timeout_keep_alive=30,
        # Limit concurrent connections for free tier
        limit_concurrency=10,
    )

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Entry point to launch the Virtual Sales Associate chatbot web app."""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

from server import run_server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    run_server(host=host, port=port)

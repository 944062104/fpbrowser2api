"""FPBrowser2API - Main Entry Point

启动方式：
  cd fpbrowser2api
  python main.py
"""

import uvicorn


import sys

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if __name__ == "__main__":
    from src.core.config import config

    uvicorn.run(
        "src.main:app",
        host=config.server_host,
        port=config.server_port,
        reload=False,
        ws_ping_interval=30,
        ws_ping_timeout=120,
    )


#!/usr/bin/env python3
"""CMIScope entry point: python run.py [--config path] [--host addr] [--port n]

Zero third-party dependencies; Python 3.9 or newer is sufficient.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace

from cmis_service.config import load_settings
from cmis_service.db import initialize
from cmis_service.server import serve


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CMIScope - lightweight CMIS dashboard")
    parser.add_argument("--config", help="Config file (default: config.ini then config.ini.example)")
    parser.add_argument("--host", help="Override listen address")
    parser.add_argument("--port", type=int, help="Override listen port")
    args = parser.parse_args(argv)

    settings = load_settings(args.config)
    if args.host:
        settings = replace(settings, host=args.host)
    if args.port:
        settings = replace(settings, port=args.port)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("cmis")
    log.info("Config loaded | base_dir=%s db=%s kg=%s",
             settings.base_dir, settings.db_file, settings.kg_file)

    conn = initialize(settings)
    try:
        serve(settings, conn)
    except KeyboardInterrupt:
        log.info("Interrupted, shutting down")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
host.py - Sync SERVER + authoritative clock (runs on YOUR laptop).

Listens on Port B for your friend's client.py, and keeps YOUR local VLC in
lockstep with his. The host is the clock authority: it heartbeats its playback
time so the client can correct drift.

Stdlib only (asyncio TCP, newline-delimited JSON). No pip installs.

Usage:
    python host.py                      # reads config.json (or defaults)
    python host.py --config config.json
    python host.py --port 9876 --vlc-password mypw
"""

import argparse
import asyncio
import json
import os

from sync_common import VlcController, SyncEngine, run_session


DEFAULTS = {
    "sync_port": 9876,          # Port B (public)
    "vlc_host": "127.0.0.1",
    "vlc_port": 8080,
    "vlc_password": "",
    "poll_interval": 0.25,
    "seek_threshold": 0.7,
    "drift_threshold": 1.5,
    "mute_window": 0.6,
    "report_time_jitter": 0.7,
    "heartbeat": 2.0,
}


def load_config(path):
    cfg = dict(DEFAULTS)
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


async def main_async(cfg):
    vlc = VlcController(cfg["vlc_host"], cfg["vlc_port"], cfg["vlc_password"])
    # quick reachability hint
    if vlc.get_state() is None:
        print("WARNING: local VLC not reachable / no media playing yet.")
        print("  Make sure VLC's Web interface is on (127.0.0.1:%d) and the "
              "movie is open." % cfg["vlc_port"])

    async def on_client(reader, writer):
        engine = SyncEngine(
            origin="host",
            seek_threshold=cfg["seek_threshold"],
            drift_threshold=cfg["drift_threshold"],
            mute_window=cfg["mute_window"],
            report_time_jitter=cfg["report_time_jitter"],
        )
        writer.write(b'{"type":"hello","role":"host"}\n')
        await writer.drain()
        await run_session(
            reader, writer, vlc, engine,
            poll_interval=cfg["poll_interval"],
            is_authority=True,
            heartbeat=cfg["heartbeat"],
            label="host",
        )

    server = await asyncio.start_server(on_client, "0.0.0.0", cfg["sync_port"])
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    print(f"Sync server (host/authority) listening on {addrs}")
    print(f"Friend's client connects to:  <your-public-ip>:{cfg['sync_port']}")
    print("Press Ctrl+C to stop.")
    async with server:
        await server.serve_forever()


def main():
    ap = argparse.ArgumentParser(description="VLC watch-party sync host (server + clock).")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--port", type=int, help="Override sync_port (Port B).")
    ap.add_argument("--vlc-password", help="Override VLC web interface password.")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.port:
        cfg["sync_port"] = args.port
    if args.vlc_password is not None:
        cfg["vlc_password"] = args.vlc_password

    try:
        asyncio.run(main_async(cfg))
    except KeyboardInterrupt:
        print("\nHost stopped.")


if __name__ == "__main__":
    main()

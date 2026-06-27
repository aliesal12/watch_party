#!/usr/bin/env python3
"""
client.py - Sync CLIENT (runs on your FRIEND'S PC).

Connects to the host's Port B and keeps your friend's local VLC in lockstep
with yours. Performs drift correction against the host's authoritative clock.

Stdlib only (asyncio TCP, newline-delimited JSON). No pip installs.

Your friend just needs:
  1. VLC running, Web interface ON (127.0.0.1:8080), movie opened as a network
     stream from your public IP.
  2. python client.py --host <YOUR-PUBLIC-IP>          (or edit config.json)

The start-client.bat you hand him can bake in your IP so he double-clicks it.
"""

import argparse
import asyncio
import json
import os

from sync_common import VlcController, SyncEngine, run_session


DEFAULTS = {
    "host_ip": "127.0.0.1",     # YOUR public IP (the friend fills this in)
    "sync_port": 9876,          # Port B
    "vlc_host": "127.0.0.1",
    "vlc_port": 8080,
    "vlc_password": "",
    "poll_interval": 0.25,
    "seek_threshold": 0.7,
    "drift_threshold": 1.5,
    "mute_window": 0.6,
    "report_time_jitter": 0.7,
    "reconnect_delay": 3.0,
}


def load_config(path):
    cfg = dict(DEFAULTS)
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


async def main_async(cfg):
    vlc = VlcController(cfg["vlc_host"], cfg["vlc_port"], cfg["vlc_password"])
    if vlc.get_state() is None:
        print("WARNING: local VLC not reachable / no media playing yet.")
        print("  Open VLC, enable the Web interface (127.0.0.1:%d), and open the "
              "movie URL from your friend's PC first." % cfg["vlc_port"])

    while True:
        try:
            print(f"Connecting to host {cfg['host_ip']}:{cfg['sync_port']} ...")
            reader, writer = await asyncio.open_connection(
                cfg["host_ip"], cfg["sync_port"])
            engine = SyncEngine(
                origin="client",
                seek_threshold=cfg["seek_threshold"],
                drift_threshold=cfg["drift_threshold"],
                mute_window=cfg["mute_window"],
                report_time_jitter=cfg["report_time_jitter"],
            )
            writer.write(b'{"type":"hello","role":"client"}\n')
            await writer.drain()
            await run_session(
                reader, writer, vlc, engine,
                poll_interval=cfg["poll_interval"],
                is_authority=False,
                label="client",
            )
        except (ConnectionError, OSError) as e:
            print(f"Connection failed/lost: {e}")

        delay = cfg["reconnect_delay"]
        print(f"Reconnecting in {delay:.0f}s (Ctrl+C to quit)...")
        await asyncio.sleep(delay)


def main():
    ap = argparse.ArgumentParser(description="VLC watch-party sync client.")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--host", help="Host's public IP (overrides config host_ip).")
    ap.add_argument("--port", type=int, help="Override sync_port (Port B).")
    ap.add_argument("--vlc-password", help="Override VLC web interface password.")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.host:
        cfg["host_ip"] = args.host
    if args.port:
        cfg["sync_port"] = args.port
    if args.vlc_password is not None:
        cfg["vlc_password"] = args.vlc_password

    try:
        asyncio.run(main_async(cfg))
    except KeyboardInterrupt:
        print("\nClient stopped.")


if __name__ == "__main__":
    main()

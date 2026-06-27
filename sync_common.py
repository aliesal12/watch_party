#!/usr/bin/env python3
"""
sync_common.py - Shared sync engine pieces used by BOTH host.py and client.py.

Contains:
  * VlcController  - talks to a local VLC over its HTTP (Lua) interface on
                     127.0.0.1:<port>. Reads playback state and issues
                     pause / play / seek / rate commands.
  * PlayState      - the small JSON-able state object exchanged over the wire.
  * SyncEngine     - the symmetric brain that runs on each side: polls local
                     VLC, decides when to broadcast, applies remote updates,
                     and prevents feedback loops (seq numbers + mute window +
                     dead-band thresholds).

Stdlib only. Networking lives in host.py / client.py; this file is transport
agnostic - it just hands you bytes to send and consumes bytes you received.

VLC HTTP interface commands used (verified, VLC 3.x):
  GET /requests/status.json                         -> state, time, length, position, rate
  GET /requests/status.json?command=pl_pause        -> toggle... so we guard with state
  GET /requests/status.json?command=pl_forceresume  -> resume if paused
  GET /requests/status.json?command=seek&val=<sec>  -> absolute seek (seconds)
  GET /requests/status.json?command=rate&val=<rate> -> set playback rate
"""

import asyncio
import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict


# --------------------------------------------------------------------------
# Wire message
# --------------------------------------------------------------------------
@dataclass
class PlayState:
    paused: bool = True
    time: float = 0.0       # playback position in seconds
    rate: float = 1.0
    seq: int = 0            # monotonically increasing; newer wins
    origin: str = ""        # "host" or "client" - who sent it (debug/echo guard)

    def to_bytes(self) -> bytes:
        return (json.dumps(asdict(self)) + "\n").encode("utf-8")

    @staticmethod
    def from_json(obj: dict) -> "PlayState":
        return PlayState(
            paused=bool(obj.get("paused", True)),
            time=float(obj.get("time", 0.0)),
            rate=float(obj.get("rate", 1.0)),
            seq=int(obj.get("seq", 0)),
            origin=str(obj.get("origin", "")),
        )


# --------------------------------------------------------------------------
# VLC HTTP control
# --------------------------------------------------------------------------
class VlcController:
    """Synchronous client for one local VLC's HTTP interface.

    Calls are quick localhost GETs. We keep them synchronous and call them
    from the asyncio loop via run_in_executor (see host/client) so a slow/
    unreachable VLC never blocks the event loop.
    """

    def __init__(self, host="127.0.0.1", port=8080, password=""):
        self.base = f"http://{host}:{port}/requests/status.json"
        # VLC uses HTTP Basic auth with an EMPTY username + your password.
        token = base64.b64encode(f":{password}".encode("utf-8")).decode("ascii")
        self._auth_header = f"Basic {token}"

    def _request(self, query=""):
        url = self.base + (("?" + query) if query else "")
        req = urllib.request.Request(url)
        req.add_header("Authorization", self._auth_header)
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ---- read -------------------------------------------------------
    def get_state(self) -> PlayState | None:
        """Return current PlayState, or None if VLC has no media / is unreachable."""
        try:
            data = self._request()
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
            return None

        vlc_state = data.get("state", "stopped")  # playing | paused | stopped
        if vlc_state == "stopped":
            return None

        # 'time' is integer seconds in VLC; 'position' (0..1) * 'length' is finer.
        length = float(data.get("length", 0) or 0)
        position = float(data.get("position", 0) or 0)
        t = position * length if length > 0 else float(data.get("time", 0) or 0)

        return PlayState(
            paused=(vlc_state == "paused"),
            time=t,
            rate=float(data.get("rate", 1.0) or 1.0),
        )

    # ---- commands ---------------------------------------------------
    def pause(self):
        # pl_pause toggles; only call when we KNOW vlc is playing (caller guards)
        try:
            self._request("command=pl_pause")
        except (urllib.error.URLError, OSError):
            pass

    def play(self):
        try:
            self._request("command=pl_forceresume")
        except (urllib.error.URLError, OSError):
            pass

    def seek_seconds(self, seconds: float):
        s = max(0, int(round(seconds)))
        try:
            self._request(f"command=seek&val={s}")
        except (urllib.error.URLError, OSError):
            pass

    def set_rate(self, rate: float):
        try:
            self._request(f"command=rate&val={rate}")
        except (urllib.error.URLError, OSError):
            pass

    def apply(self, target: PlayState, cur: PlayState, seek_threshold: float):
        """Drive local VLC toward `target`, given current state `cur`.

        Order matters: fix pause/play, then seek if off, then rate.
        Only issues commands that are actually needed (avoids churn).
        """
        # rate first is fine, but do play/pause + seek as the visible actions
        if abs(cur.time - target.time) > seek_threshold:
            self.seek_seconds(target.time)

        if target.paused and not cur.paused:
            self.pause()
        elif (not target.paused) and cur.paused:
            self.play()

        if abs(cur.rate - target.rate) > 0.01:
            self.set_rate(target.rate)


# --------------------------------------------------------------------------
# Symmetric sync brain
# --------------------------------------------------------------------------
class SyncEngine:
    """Runs identically on host and client.

    You feed it the locally-observed PlayState each tick (observe_local) and
    it returns an optional PlayState to BROADCAST. You feed it remote messages
    (on_remote) and it returns an optional PlayState to APPLY to local VLC.

    Loop prevention (expectation-based, NOT blanket time-muting):
      * seq: every broadcast bumps a shared counter; we ignore messages whose
        seq is not strictly newer than what we've already accepted.
      * expected-state echo guard: when we APPLY a remote command we record the
        state we expect local VLC to reach. While local matches that expectation
        we stay silent (it's the echo). The instant local DIVERGES from the
        expectation it's a genuine NEW user action and we broadcast it -- so a
        user pausing right after a synced seek is never swallowed.
      * short settle window: a brief grace period gives VLC time to actually
        reach the applied state before we start echo-checking, so we don't
        misread "hasn't moved yet" as divergence.
      * dead-band: tiny time jitter while playing is not reported as a seek.
    """

    def __init__(
        self,
        origin: str,
        seek_threshold: float = 0.7,
        drift_threshold: float = 1.5,
        mute_window: float = 0.6,
        report_time_jitter: float = 0.7,
    ):
        self.origin = origin
        self.seek_threshold = seek_threshold      # apply-side: seek if off by more
        self.drift_threshold = drift_threshold    # playing-drift correction bound
        self.settle_window = mute_window          # grace for VLC to reach applied state
        self.report_time_jitter = report_time_jitter

        self.seq = 0                              # last seq we originated/accepted
        self.shared = PlayState(origin=origin)    # last agreed state
        self._have_state = False
        # echo guard: state we expect local VLC to reach after an apply
        self._expecting = None                    # PlayState or None
        self._settle_until = 0.0

    # -- helpers ------------------------------------------------------
    def _arm_expectation(self, target: PlayState):
        """After applying `target`, expect local VLC to reach it."""
        self._expecting = PlayState(
            paused=target.paused, time=target.time, rate=target.rate,
            seq=target.seq, origin=target.origin,
        )
        self._settle_until = time.monotonic() + self.settle_window

    def _matches_expectation(self, local: PlayState) -> bool:
        """True if local looks like the state we applied (i.e. an echo)."""
        e = self._expecting
        if e is None:
            return False
        if local.paused != e.paused:
            return False
        if abs(local.rate - e.rate) > 0.01:
            return False
        # while playing, the expected time advances; allow a generous window
        # that grows a little so normal playback progression still matches.
        tol = max(self.report_time_jitter, self.seek_threshold) + 1.5
        if abs(local.time - e.time) > tol and local.paused:
            return False
        if local.paused and abs(local.time - e.time) > self.seek_threshold:
            return False
        return True

    def _material_change(self, local: PlayState) -> bool:
        s = self.shared
        if local.paused != s.paused:
            return True
        if abs(local.rate - s.rate) > 0.01:
            return True
        # only treat a time gap as a (seek) change worth broadcasting
        if abs(local.time - s.time) > self.report_time_jitter:
            return True
        return False

    # -- inputs -------------------------------------------------------
    def observe_local(self, local: PlayState | None) -> PlayState | None:
        """Call every poll tick with local VLC state.
        Returns a PlayState to broadcast, or None."""
        if local is None:
            return None

        if not self._have_state:
            # first observation: adopt as baseline, don't broadcast
            self.shared = PlayState(
                paused=local.paused, time=local.time, rate=local.rate,
                seq=self.seq, origin=self.origin,
            )
            self._have_state = True
            return None

        # Echo guard: if we're waiting for an applied state to take effect...
        if self._expecting is not None:
            if self._matches_expectation(local):
                # this is the echo of what we applied -> absorb it, stay silent,
                # and stop expecting (we've converged)
                self.shared = PlayState(
                    paused=local.paused, time=local.time, rate=local.rate,
                    seq=self.seq, origin=self._expecting.origin,
                )
                # keep expecting while playing so normal progression stays muted
                # only until settle window passes; for paused we can clear now.
                if local.paused or time.monotonic() >= self._settle_until:
                    self._expecting = None
                return None
            elif time.monotonic() < self._settle_until:
                # VLC hasn't reached the applied state yet; give it time
                return None
            else:
                # settle window elapsed AND local diverges from expectation
                # => a genuine NEW user action. Clear expectation, fall through
                # to broadcast it below.
                self._expecting = None

        if self._material_change(local):
            self.seq += 1
            self.shared = PlayState(
                paused=local.paused, time=local.time, rate=local.rate,
                seq=self.seq, origin=self.origin,
            )
            return self.shared
        else:
            # passive update of our notion of "now" while playing
            self.shared.time = local.time
            return None

    def on_remote(self, msg: PlayState, local: PlayState | None):
        """Process an incoming remote PlayState.
        Returns a PlayState to APPLY to local VLC, or None."""
        # Only act on strictly-newer messages (stale/echoed updates ignored).
        if msg.seq <= self.seq:
            return None

        # accept it
        self.seq = msg.seq
        self.shared = PlayState(
            paused=msg.paused, time=msg.time, rate=msg.rate,
            seq=self.seq, origin=msg.origin,
        )

        if local is None:
            # nothing playing locally yet; still record + expect the state
            self._arm_expectation(msg)
            return msg

        # Decide whether applying is even needed
        needs = (
            local.paused != msg.paused
            or abs(local.time - msg.time) > self.seek_threshold
            or abs(local.rate - msg.rate) > 0.01
        )
        if not needs:
            # already in sync; mark expectation so the (already-matching) state
            # isn't mistaken for a new user action
            self._arm_expectation(msg)
            return None

        self._arm_expectation(msg)
        return msg

    def drift_correction(self, local: PlayState | None, authoritative: PlayState):
        """Optional: while both playing, gently pull local toward authoritative
        time. Returns a PlayState to apply (a seek), or None.

        `authoritative` is the host's broadcast clock; only the client calls
        this (host IS the clock)."""
        if local is None or local.paused or authoritative.paused:
            return None
        # don't fight an in-flight apply we're still settling
        if self._expecting is not None and time.monotonic() < self._settle_until:
            return None
        if abs(local.time - authoritative.time) > self.drift_threshold:
            self._arm_expectation(authoritative)
            return PlayState(
                paused=False, time=authoritative.time, rate=authoritative.rate,
                seq=self.seq, origin=authoritative.origin,
            )
        return None


# --------------------------------------------------------------------------
# Shared asyncio session loop (used by both host.py and client.py)
# --------------------------------------------------------------------------
async def run_session(reader, writer, vlc, engine, *,
                      poll_interval=0.25, is_authority=False,
                      heartbeat=2.0, label="peer"):
    """Drive one connected sync session over an asyncio stream pair.

    reader/writer : asyncio StreamReader/StreamWriter to the other side.
    vlc           : VlcController for the LOCAL VLC.
    engine        : SyncEngine.
    is_authority  : True on the host; periodically broadcasts its clock so the
                    client can do drift correction.
    """
    loop = asyncio.get_running_loop()
    peer = writer.get_extra_info("peername")
    print(f"[{label}] connected to {peer}")

    async def vlc_get():
        return await loop.run_in_executor(None, vlc.get_state)

    async def vlc_apply(target, cur):
        await loop.run_in_executor(None, vlc.apply, target, cur, engine.seek_threshold)

    async def send(state: PlayState):
        try:
            writer.write(state.to_bytes())
            await writer.drain()
        except (ConnectionError, OSError):
            raise

    # ---- reader task: apply remote updates --------------------------
    async def reader_task():
        last_authority_broadcast = None
        while True:
            line = await reader.readline()
            if not line:
                print(f"[{label}] peer closed connection")
                return
            try:
                obj = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if obj.get("type") == "hello":
                continue
            msg = PlayState.from_json(obj)
            cur = await vlc_get()
            to_apply = engine.on_remote(msg, cur)
            if to_apply is not None:
                cur2 = cur if cur is not None else PlayState()
                await vlc_apply(to_apply, cur2)
                print(f"[{label}] applied remote seq={msg.seq} "
                      f"paused={msg.paused} t={msg.time:.1f} rate={msg.rate}")
            # client-side drift correction against host's authoritative clock
            if not is_authority and not msg.paused:
                last_authority_broadcast = msg
                cur3 = await vlc_get()
                corr = engine.drift_correction(cur3, last_authority_broadcast)
                if corr is not None:
                    cur4 = cur3 if cur3 is not None else PlayState()
                    await vlc_apply(corr, cur4)
                    print(f"[{label}] drift-correct -> t={corr.time:.1f}")

    # ---- writer task: poll local VLC and broadcast changes ----------
    async def writer_task():
        last_beat = 0.0
        while True:
            cur = await vlc_get()
            out = engine.observe_local(cur)
            if out is not None:
                await send(out)
                print(f"[{label}] broadcast seq={out.seq} "
                      f"paused={out.paused} t={out.time:.1f} rate={out.rate}")
            elif is_authority and cur is not None and not cur.paused:
                # heartbeat the authoritative clock so client can de-drift,
                # even when nothing "changed"
                now = time.monotonic()
                if now - last_beat >= heartbeat:
                    last_beat = now
                    beat = PlayState(
                        paused=cur.paused, time=cur.time, rate=cur.rate,
                        seq=engine.seq, origin=engine.origin,
                    )
                    await send(beat)
            await asyncio.sleep(poll_interval)

    try:
        await asyncio.gather(reader_task(), writer_task())
    except (ConnectionError, OSError) as e:
        print(f"[{label}] connection error: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass

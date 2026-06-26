# Synced Remote VLC Watch-Party (host-streamed)

Watch a movie that lives **only on your laptop**, together with one remote
friend, both in **VLC** — fully synced (pause / play / seek / speed mirror both
ways) and at **exactly the same quality** for your friend (the raw file bytes
are streamed; nothing is re-encoded or downscaled).

There are two independent layers:

1. **Transport** — `serve.py` streams the raw file over HTTP with range support,
   so your friend's VLC opens it like a local file and can seek anywhere.
2. **Sync** — `host.py` (you) + `client.py` (friend) keep both VLC instances in
   lockstep by reading/driving each VLC's local HTTP control interface.

**Stdlib only — no `pip install` needed.** Just Python 3 + VLC on both machines.

```
   YOUR LAPTOP (host)                         FRIEND'S PC (client)
  movie.mkv ──serve.py──HTTP:8000──────────►  VLC (opens the URL, can seek)
  VLC (local) ◄─127.0.0.1:8080─ host.py                 ▲ 127.0.0.1:8080
                         host.py ◄──TCP:9000──► client.py
                       (sync server + clock)     (sync client + de-drift)
```

Only ports **8000** (video) and **9000** (sync) are public. VLC's **8080**
control port stays bound to `127.0.0.1` and is never exposed.

---

## Files

| File | Where it runs | What it does |
|------|---------------|--------------|
| `serve.py` | host | Range-aware HTTP server for the raw video (seekable). |
| `host.py` | host | Sync server + authoritative clock; drives your VLC. |
| `client.py` | friend | Sync client; drives friend's VLC; corrects drift. |
| `sync_common.py` | both | VLC HTTP control + sync brain (loop-prevention). |
| `config.host.example.json` | host | Copy to `config.json` on the host. |
| `config.client.example.json` | friend | Copy to `config.json` on the friend's PC. |
| `start-host.bat` | host | One-click: VLC + file server + sync host. |
| `start-client.bat` | friend | One-click: VLC + sync client (your IP baked in). |

The friend only needs: `client.py`, `sync_common.py`, `start-client.bat`
(prefilled with your public IP), and VLC + Python.

---

## One-time setup (BOTH machines)

1. **Install VLC 3.x and Python 3** on both machines.
2. **Enable VLC's Web interface** (so the scripts can read/drive playback):
   - `Tools → Preferences` → bottom-left set **Show settings: All**.
   - `Interface → Main interfaces` → check **Web**.
   - `Interface → Main interfaces → Lua` → set a **Lua HTTP Password**
     (use the SAME password on both machines for simplicity).
   - Restart VLC.
   - *(The `.bat` files instead launch VLC with `--http-password=...` so you can
     skip the GUI step if you use them.)*
3. Confirm it works: with VLC open and a video playing, browse to
   `http://127.0.0.1:8080` (user blank, the password) — you should see VLC's web
   remote. If yes, the scripts will work.

---

## Host setup (your laptop — you own the movie)

### A. Open your ports

- **Windows Firewall**: allow inbound TCP **8000** and **9000**.
- **Router**: port-forward TCP **8000** and **9000** to your laptop's LAN IP.
  Give your laptop a **static LAN IP / DHCP reservation** so it doesn't change.
- Do **not** forward 8080.

### B. Configure

```
copy config.host.example.json config.json
```
Edit `config.json`: set `vlc_password` to your VLC web password.

Edit `start-host.bat`: set `MOVIE_DIR`, `MOVIE_FILE`, and `VLC_PW`.

### C. Run

Double-click **`start-host.bat`** (or run the three commands manually):

```
python serve.py --dir "D:\path\to\movies" --port 8000
python host.py --vlc-password YOUR_VLC_PW
:: and open the movie locally in VLC with the web interface enabled
```

Find your **public IP** (e.g. visit whatismyip.com) and give it to your friend.

---

## Friend setup (dead-simple version)

Send your friend the folder with `client.py`, `sync_common.py`, and a
**`start-client.bat` that you pre-filled** with:
- `HOST_IP` = your public IP
- `VIDEO_URL` = `http://<your-ip>:8000/<your-file-name>`
- `VLC_PW` = the shared VLC password

Then your friend:
1. Installs **VLC** and **Python 3** (during Python install, tick *"Add Python to
   PATH"*).
2. Double-clicks **`start-client.bat`**.

That's it — VLC opens streaming your movie, and the client connects and syncs.

> Why isn't it *zero* setup for the friend? His VLC won't pause itself — a small
> local script must drive it. The `.bat` reduces that to one double-click.

---

## How sync behaves

- **Pause/Play**: either side pauses/plays → the other mirrors within ~0.5 s.
- **Seek / fast-forward**: jump anywhere → the other jumps to match.
- **Speed**: change playback rate → the other matches.
- **Drift**: while both play, the host heartbeats its real time; the client
  nudges itself to stay within ~1 s.
- **No ping-pong**: sequence numbers + a short "mute window" after applying a
  remote command stop the infinite echo loop.

Tune in `config.json`:
- `seek_threshold` (s): how far off before a corrective seek fires.
- `drift_threshold` (s): allowed playing-drift before the client re-seeks.
- `mute_window` (s): "settle" grace period after applying a remote command,
  giving VLC time to reach that state before echo-checking resumes. (Genuine new
  user actions are detected by divergence and are never swallowed.)
- `poll_interval` (s): how often each side reads its VLC (lower = snappier, busier).

---

## Verify it works (do these in order)

1. **Transport + seek (make-or-break):** From a *different* device, open
   `http://<your-public-ip>:8000/<file>` in VLC. It should play **and** let you
   drag the seek bar forward/back. If seeking fails, the range server isn't
   reachable / the file isn't indexed (try a lossless remux: `ffmpeg -i in.mkv
   -c copy out.mkv`).
2. **Exact quality:** On the friend's VLC, `Tools → Codec Information` and
   `Tools → Media Information → Statistics` — resolution/codec/bitrate must match
   your source exactly (proves raw passthrough, zero quality loss).
3. **Pause/Play:** Host runs `host.py`, friend runs `client.py`. Pause on one →
   the other pauses. No ping-pong.
4. **Seek:** Jump to 45:00 on one side → the other follows. Reverse roles.
5. **Drift:** Let both play untouched 5–10 min → stay within ~1 s.
6. **Security:** From outside, confirm `:8080` is **not** reachable; only 8000
   and 9000 are.

---

## Troubleshooting

- **`python` not found (friend):** reinstall Python with *Add to PATH*, or edit
  the `.bat` to use the full path to `python.exe`.
- **"local VLC not reachable":** Web interface not enabled, wrong password, or
  wrong `vlc_port`. Confirm `http://127.0.0.1:8080` works in a browser.
- **Friend can't open the video URL:** firewall/port-forward not set, wrong
  public IP, or the file name in the URL is wrong (it's case-sensitive-ish; match
  it exactly). Test the URL in his browser first.
- **Seeking works locally but not for the friend:** that's the range server —
  make sure he's hitting `serve.py` (port 8000), not VLC's stream output.
- **Stutters/buffering for the friend:** that's bandwidth, not quality. His VLC
  buffers; quality stays full. Raise VLC's network caching
  (`Tools → Preferences → Input/Codecs → Network caching`) on his side.
- **They drift apart:** lower `drift_threshold`, or raise `poll_interval`
  slightly if VLC is being hammered.

---

## Security notes

- Keep VLC's `:8080` bound to `127.0.0.1` (the scripts/`.bat` do this).
- `serve.py` serves only the folder you point it at — use a **dedicated movie
  folder**, never your home directory.
- Optional: run `serve.py --token SECRET`; then the URL is
  `http://<ip>:8000/<file>?token=SECRET` so random port-scanners can't grab it.
- Stop everything (close the windows / Ctrl+C) when you're done to close the
  open ports' usefulness.

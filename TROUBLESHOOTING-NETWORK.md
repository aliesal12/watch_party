# Network Troubleshooting — "WinError 121 / semaphore timeout" on the client

## What we confirmed

On the **host laptop**, everything is working correctly:

- `serve.py` is listening on `0.0.0.0:8975` (video) ✓
- `host.py` is listening on `0.0.0.0:9876` (sync) ✓
- VLC web interface is on `127.0.0.1:8080` ✓
- Both ports accept connections via loopback **and** the LAN IP (`192.168.18.3`) ✓
- **portchecker.co confirms port 9876 is OPEN** from the public internet ✓

Yet the **friend's client** (on the **same ISP, different house**) times out with
`[WinError 121] The semaphore timeout period has expired` when connecting to the
host's public IP `175.107.202.121:9876`.

## Root cause: ISP internal-path blocking (same-ISP customer ↔ customer)

The signature is unambiguous:

| Tester | Result |
|--------|--------|
| Portchecker (outside the ISP) | ✅ port OPEN — reaches the host fine |
| Friend (inside the SAME ISP) | ❌ times out (and ping also fails) |

If this were CGNAT on the host side, **portchecker would also fail** — but it
succeeds. The only party that fails is the one on the *same ISP*. That means when
the friend sends a packet to the host's public IP, the ISP routes it internally
and drops it instead of "hairpinning" it back in from the outside. This is either:

- **Peer/client isolation** (ISP deliberately blocks customer-to-customer traffic
  on residential plans), or
- **CGNAT NAT-loopback failure** (the ISP's carrier-grade NAT can't reflect a
  customer's packet back to another customer behind the same NAT).

Either way the data never traverses the public path that portchecker uses, so the
open port is irrelevant for two customers of the same ISP.

## Confirm it in 30 seconds (optional but worth it)

Pick ONE:

1. **Mobile-hotspot test (best):** Friend turns on his phone's hotspot, connects
   his PC to it (now off the shared ISP), and re-runs `start-client.bat`. If it
   connects over mobile data but not over his home ISP → confirmed. Same PC, only
   the network path changed.
2. **Compare two testers:** Friend runs
   `Test-NetConnection 175.107.202.121 -Port 9876` (expect `False`); someone on a
   *different* network runs the same (expect `True`).

## The fix: Tailscale (free, ~5 min, routes around the ISP)

Tailscale builds a private encrypted tunnel (WireGuard) between your two PCs. It
does NOT depend on the ISP's customer-to-customer routing, so the block doesn't
apply. Bonus: **you no longer need router port-forwarding at all** — Tailscale
carries both the video stream and the sync channel.

### Steps (BOTH PCs)

1. Install Tailscale: https://tailscale.com/download
2. Sign in with the **same** account (Google/GitHub/Microsoft) on **both**
   machines so they join the same private network ("tailnet").
3. Find the **host laptop's Tailscale IP** — it looks like `100.x.x.x`:
   - Run `tailscale ip -4`, or hover the Tailscale tray icon, or check the admin
     console at https://login.tailscale.com/admin/machines

### Then point the client at the Tailscale IP

On the **friend's PC**, edit `start-client.bat` line ~17:

```bat
set "HOST_IP=100.X.X.X"        REM <- host's Tailscale IP (100.x.x.x)
```

That's the only change. `VIDEO_URL` uses `%HOST_IP%` so it updates automatically,
and `host.py`/`serve.py` already bind to `0.0.0.0`, so the **host needs no changes**.

### Verify

On the friend's PC, after both are on Tailscale:

```powershell
ping 100.X.X.X                              # should reply now
Test-NetConnection 100.X.X.X -Port 9876     # TcpTestSucceeded : True
Test-NetConnection 100.X.X.X -Port 8975     # TcpTestSucceeded : True
```

Then double-click `start-client.bat`. VLC opens the stream over the tunnel and the
sync client connects.

> Once on Tailscale you can leave the public ports closed/unforwarded — the tunnel
> handles everything, and it's more secure (only your tailnet devices can reach the
> server, not random port-scanners).

## If you'd rather not use Tailscale

Alternatives that also bypass same-ISP blocking, in rough order of ease:

- **ZeroTier** — same idea as Tailscale (virtual LAN), also free.
- **Friend on a different network** — e.g. mobile hotspot (uses data though).
- **A relay/VPS** — host the file on a cheap cloud server and run the sync server
  there; both of you connect "outward" to it. Most work; only needed if you can't
  install a mesh-VPN on both ends.

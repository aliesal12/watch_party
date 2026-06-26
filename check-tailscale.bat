@echo off
REM ============================================================
REM  check-tailscale.bat  -  run on EITHER PC after installing Tailscale
REM
REM  Prints this machine's Tailscale IP (the 100.x.x.x address you put
REM  into the client's HOST_IP), and shows whether the link to the other
REM  machine is DIRECT (fast) or via a RELAY (works, a bit slower).
REM ============================================================

set "TS=C:\Program Files\Tailscale\tailscale.exe"
if not exist "%TS%" (
    echo Tailscale not found at %TS%
    echo Install it from https://tailscale.com/download and sign in, then re-run this.
    pause
    exit /b 1
)

echo.
echo === THIS machine's Tailscale IP (use this as HOST_IP on the host) ===
"%TS%" ip -4
echo.

echo === Peers on your tailnet + connection type ===
echo   (look for "direct" = fast P2P, or "relay ..." = via DERP relay)
echo.
"%TS%" status
echo.
echo Tip: if it says "relay", playback still works but is routed through a
echo Tailscale server. "direct" gives full LAN-like speed.
echo.
pause

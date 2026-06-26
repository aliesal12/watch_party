@echo off
REM ============================================================
REM  start-client.bat  -  run on the FRIEND'S PC
REM
REM  The host (your friend who owns the movie) fills in:
REM    HOST_IP    = the host's address. USE THE TAILSCALE IP (100.x.x.x)
REM                 if direct public IP fails (ISP blocks same-ISP traffic).
REM                 See TROUBLESHOOTING-NETWORK.md.
REM    VIDEO_URL  = http://<HOST_IP>:8975/<filename>
REM    VLC_PW     = the SAME password the host told you to set in VLC
REM
REM  Then the friend just double-clicks this file.
REM ============================================================

REM ---- SET THESE THREE ----
REM HOST_IP: the host's Tailscale IP (100.x.x.x) -- run check-tailscale.bat on
REM          the HOST to get it. (Same-ISP direct public IP is blocked by the
REM          ISP; Tailscale is the fix. See TROUBLESHOOTING-NETWORK.md.)
set "HOST_IP=100.107.158.59"
REM MOVIE_FILE: exact file name as it sits in the host's movie folder.
set "MOVIE_FILE=The.Amazing.Spiderman.2012.720p.BrRip.x264.YIFY.mp4"
REM VLC_PW: the shared VLC web-interface password.
set "VLC_PW=Inshal"
REM -------------------------

set "VIDEO_PORT=8975"
set "SYNC_PORT=9876"
set "VLC_PORT=8080"
set "VIDEO_URL=http://%HOST_IP%:%VIDEO_PORT%/%MOVIE_FILE%"

set "VLC=C:\Program Files\VideoLAN\VLC\vlc.exe"
if not exist "%VLC%" set "VLC=C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"

echo.
echo === VLC Watch-Party CLIENT ===
echo Host      : %HOST_IP%   Sync port: %SYNC_PORT%
echo Video URL : %VIDEO_URL%
echo.

REM 1) Open VLC streaming the host's file (RAW, full quality) with web interface on.
echo Launching VLC and opening the stream...
start "" "%VLC%" --extraintf=http --http-host=127.0.0.1 --http-port=%VLC_PORT% --http-password=%VLC_PW% "%VIDEO_URL%"

REM Give VLC a moment to start the web interface before the client polls it.
timeout /t 4 /nobreak >nul

REM 2) Start the sync client (connects to the host).
echo Starting sync client...
python "%~dp0client.py" --host %HOST_IP% --port %SYNC_PORT% --vlc-password %VLC_PW%

echo.
echo Client stopped.
pause

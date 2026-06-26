@echo off
REM ============================================================
REM  start-client.bat  -  run on the FRIEND'S PC
REM
REM  The host (your friend who owns the movie) fills in:
REM    HOST_IP    = the host's public IP address
REM    VIDEO_URL  = http://<HOST_IP>:8000/<filename>
REM    VLC_PW     = the SAME password the host told you to set in VLC
REM
REM  Then the friend just double-clicks this file.
REM ============================================================

set "HOST_IP=175.107.202.121"
set "VIDEO_URL=http://%HOST_IP%:8000/The.Amazing.Spiderman.2012.720p.BrRip.x264.YIFY.mp4"
set "VLC_PW=Inshal"

set "SYNC_PORT=9000"
set "VLC_PORT=8080"

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

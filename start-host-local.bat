@echo off
REM ============================================================
REM  start-host-local.bat  -  HOST (local playback mode)
REM  Both you and your friend have the same local video file.
REM  Only sync signals travel over Tailscale -- zero video bytes.
REM ============================================================

set "MOVIE_DIR=D:\Movies\The Amazing Spiderman (2012)"
set "MOVIE_FILE=The.Amazing.Spiderman.2012.720p.BrRip.x264.YIFY.mp4"
set "VLC_PW=Inshal"

set "SYNC_PORT=9876"
set "VLC_PORT=8080"

set "VLC=D:\Softwares\VideoLAN\VLC\vlc.exe"
if not exist "%VLC%" set "VLC=C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"

echo.
echo === VLC Watch-Party HOST (local mode) ===
echo Movie : %MOVIE_DIR%\%MOVIE_FILE%
echo Sync  : Tailscale port %SYNC_PORT%
echo.

echo Ensuring firewall allows sync port %SYNC_PORT%...
netsh advfirewall firewall add rule name="VLC Watch-Party Sync %SYNC_PORT%" dir=in action=allow protocol=TCP localport=%SYNC_PORT% >nul 2>&1

echo Launching VLC (local file + web interface)...
start "" "%VLC%" --extraintf=http --http-host=127.0.0.1 --http-port=%VLC_PORT% --http-password=%VLC_PW% "%MOVIE_DIR%\%MOVIE_FILE%"

echo Starting sync host...
start "sync-host-local" cmd /k python "%~dp0host.py" --port %SYNC_PORT% --vlc-password %VLC_PW%

echo.
echo Friend needs their own copy of %MOVIE_FILE% and runs start-client-local.bat.
echo Your Tailscale IP (for friend's HOST_IP): run check-tailscale.bat to see it.
echo.
pause

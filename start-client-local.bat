@echo off
REM ============================================================
REM  start-client-local.bat  -  CLIENT (local playback mode)
REM  You have your own local copy of the video file.
REM  Set MOVIE_FOLDER to where YOUR copy lives on this PC.
REM ============================================================

REM ---- SET THESE FOUR ----
set "HOST_IP=100.107.158.59"
set "MOVIE_FOLDER=C:\Movies"
set "MOVIE_FILE=The.Amazing.Spiderman.2012.720p.BrRip.x264.YIFY.mp4"
set "VLC_PW=Inshal"
REM ------------------------

set "SYNC_PORT=9876"
set "VLC_PORT=8080"

set "VLC=C:\Program Files\VideoLAN\VLC\vlc.exe"
if not exist "%VLC%" set "VLC=C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"

echo.
echo === VLC Watch-Party CLIENT (local mode) ===
echo Local file : %MOVIE_FOLDER%\%MOVIE_FILE%
echo Host       : %HOST_IP%   Sync port: %SYNC_PORT%
echo.

echo Launching VLC (local file + web interface)...
start "" "%VLC%" --extraintf=http --http-host=127.0.0.1 --http-port=%VLC_PORT% --http-password=%VLC_PW% "%MOVIE_FOLDER%\%MOVIE_FILE%"

timeout /t 4 /nobreak >nul

echo Starting sync client...
python "%~dp0client.py" --host %HOST_IP% --port %SYNC_PORT% --vlc-password %VLC_PW%

echo.
echo Client stopped.
pause

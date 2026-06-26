@echo off
REM ============================================================
REM  start-host.bat  -  run on YOUR laptop (the host)
REM
REM  Before running, set the three values below:
REM    MOVIE_DIR  = folder that contains your video file
REM    MOVIE_FILE = the video file name
REM    VLC_PW     = the password you set in VLC's Web interface
REM ============================================================

set "MOVIE_DIR=D:\Ali Stuff\stream\movies"
set "MOVIE_FILE=movie.mkv"
set "VLC_PW=CHANGE_ME"

set "VIDEO_PORT=8000"
set "SYNC_PORT=9000"
set "VLC_PORT=8080"

set "VLC=C:\Program Files\VideoLAN\VLC\vlc.exe"
if not exist "%VLC%" set "VLC=C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"

echo.
echo === VLC Watch-Party HOST ===
echo Movie     : %MOVIE_DIR%\%MOVIE_FILE%
echo Video port: %VIDEO_PORT%   Sync port: %SYNC_PORT%
echo.

REM 1) Open VLC locally with the Web (HTTP/Lua) interface enabled, playing your file.
echo Launching VLC (local playback + web interface on 127.0.0.1:%VLC_PORT%)...
start "" "%VLC%" --extraintf=http --http-host=127.0.0.1 --http-port=%VLC_PORT% --http-password=%VLC_PW% "%MOVIE_DIR%\%MOVIE_FILE%"

REM 2) Start the range-aware file server so your friend can stream + seek the RAW file.
echo Starting file server (raw bytes, seekable)...
start "file-server" cmd /k python "%~dp0serve.py" --dir "%MOVIE_DIR%" --port %VIDEO_PORT%

REM 3) Start the sync server + authoritative clock.
echo Starting sync host...
start "sync-host" cmd /k python "%~dp0host.py" --port %SYNC_PORT% --vlc-password %VLC_PW%

echo.
echo All started. Tell your friend to open in VLC:
echo     http://YOUR-PUBLIC-IP:%VIDEO_PORT%/%MOVIE_FILE%
echo and to run start-client.bat (with your public IP set).
echo.
pause

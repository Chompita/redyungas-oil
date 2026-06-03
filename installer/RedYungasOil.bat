@echo off
rem ===========================================================================
rem  REDYUNGAS OIL — lanzador. Pone git (MinGit) y ffmpeg en el PATH para que la
rem  app los encuentre (auto-update y audio) y arranca SIN consola con pythonw.
rem  Lo invoca run_redyungas_oil.vbs (oculto). %~dp0 = carpeta de instalación.
rem ===========================================================================
set "APP=%~dp0"
set "PATH=%APP%tools\git\cmd;%APP%tools\ffmpeg;%PATH%"
cd /d "%APP%repo"
start "" "%APP%venv\Scripts\pythonw.exe" -m redyungas_oil

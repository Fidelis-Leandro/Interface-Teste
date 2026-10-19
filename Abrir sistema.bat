@echo off
rem Abre o sistema de avaliacao da mao com dois cliques (sem janela de terminal).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo O sistema ainda nao foi instalado. Rode primeiro o Instalar sistema.bat.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" sistema.py %*

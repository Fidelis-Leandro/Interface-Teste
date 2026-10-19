@echo off
rem Instala a mao 3D (modelo MANO) a partir do mano_v1_2.zip baixado em
rem https://mano.is.tue.mpg.de (conta propria; a licenca nao permite redistribuir).
rem Procura o zip na pasta Downloads; ou arraste o zip sobre este arquivo.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo O sistema ainda nao foi instalado. Rode primeiro o Instalar sistema.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tools\instalar_mano.py %*
pause

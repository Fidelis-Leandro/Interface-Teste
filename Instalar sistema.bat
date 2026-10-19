@echo off
rem Instala o sistema de avaliacao da mao: ambiente Python, pacotes, modelo do
rem MediaPipe, testes e pacientes ficticios de demonstracao. Pode rodar de novo.
cd /d "%~dp0"
echo.
echo === Instalacao do sistema de avaliacao da mao ===
echo.

rem --- 1. Python 3.11 (as versoes dos pacotes foram testadas com ele)
set "PY="
py -3.11 --version >nul 2>&1 && set "PY=py -3.11"
if not defined PY (
    python -c "import sys; sys.exit(sys.version_info[:2] != (3, 11))" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)
if not defined PY (
    echo Python 3.11 nao encontrado.
    echo Instale com o comando abaixo e rode este arquivo de novo:
    echo     winget install -e --id Python.Python.3.11
    echo ou baixe em https://www.python.org/downloads/release/python-3119/
    echo marcando "Add python.exe to PATH".
    goto falhou
)
echo [1/5] Python encontrado: %PY%

rem --- 2. Ambiente virtual (.venv) so deste projeto
if not exist ".venv\Scripts\python.exe" (
    echo [2/5] Criando o ambiente .venv ...
    %PY% -m venv .venv || goto falhou
) else (
    echo [2/5] Ambiente .venv ja existe.
)

rem --- 3. Pacotes
echo [3/5] Instalando os pacotes (pode levar alguns minutos na primeira vez) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet || goto falhou
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet || goto falhou

rem --- 4. Modelo do MediaPipe (deteccao da mao na camera)
echo [4/5] Baixando o modelo do MediaPipe (se ainda nao tiver) ...
".venv\Scripts\python.exe" -c "import capture; capture.ensure_model()" || goto falhou

rem --- 5. Testes e demonstracao
echo [5/5] Rodando os testes e criando os pacientes ficticios de demonstracao ...
".venv\Scripts\python.exe" tools\testar.py || goto falhou
".venv\Scripts\python.exe" tools\criar_demonstracao.py || goto falhou

echo.
echo === Instalacao concluida ===
echo Abra o sistema com "Abrir sistema.bat" (webcam) ou "Abrir simulacao.bat" (sem camera).
echo Mao 3D (opcional): veja assets\mano\LEIA-ME.txt e depois rode Instalar mao 3D.bat.
echo.
pause
exit /b 0

:falhou
echo.
echo === A instalacao parou com erro. Veja a mensagem acima e o arquivo INSTALACAO.md. ===
echo.
pause
exit /b 1

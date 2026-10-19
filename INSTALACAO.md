# Guia de instalação para um agente (Claude no VS Code)

Este guia é para um assistente de IA instalar e abrir o sistema no Windows da pessoa que pediu. Siga os
passos na ordem e confira o resultado esperado de cada um antes de seguir. Se um passo falhar, veja
**Problemas comuns** no fim.

**Regras**
- Trabalhe só dentro da pasta do projeto. Não instale pacotes no Python global: use o `.venv` do projeto.
- Não altere o código para "fazer funcionar" sem antes explicar o problema para a pessoa.
- Não publique nem envie para lugar nenhum a pasta `dados_locais/` (banco de pacientes).
- O modelo **MANO** (mão 3D) não pode ser baixado por você: exige conta e aceite de licença pela própria
  pessoa. Explique o passo e deixe que ela faça (ver passo 7). O sistema funciona sem ele.

Testado com: Windows 11, Python 3.11.9, os pacotes do `requirements.txt`.

---

## Caminho curto

Se o terminal for o PowerShell, na pasta do projeto:

```powershell
cmd /c "Instalar sistema.bat"
```

O script faz os passos 1 a 6 abaixo e termina com `=== Instalacao concluida ===`. Ele espera uma tecla no
fim (`pause`); se o terminal não for interativo, use `cmd /c "Instalar sistema.bat" < nul`.
Se terminar com erro, siga os passos manuais a partir do que falhou.

---

## Passos manuais (PowerShell, na pasta do projeto)

### 1. Encontrar o Python 3.11

As versões dos pacotes foram testadas com o Python **3.11** (64 bits). Teste, nesta ordem:

```powershell
py -3.11 --version
python --version
& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" --version
```

Use o primeiro que responder `Python 3.11.x`. Nos comandos abaixo ele aparece como `PYTHON311`.

Se nenhum responder, instale (peça autorização à pessoa antes):

```powershell
winget install -e --id Python.Python.3.11
```

Depois feche e abra o terminal e teste de novo. Sem o `winget`: <https://www.python.org/downloads/release/python-3119/>,
instalador de 64 bits, marcando *Add python.exe to PATH*.

### 2. Criar o ambiente do projeto

```powershell
PYTHON311 -m venv .venv
.venv\Scripts\python.exe --version
```

Esperado: `Python 3.11.x`.

### 3. Instalar os pacotes

```powershell
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Esperado: termina sem `ERROR`. São cerca de 300 MB (mediapipe, opencv, PyQt5). Confira:

```powershell
.venv\Scripts\python.exe -c "import PyQt5, pyqtgraph, OpenGL, numpy, mediapipe, cv2; print('ok')"
```

### 4. Baixar o modelo de detecção da mão (MediaPipe)

```powershell
.venv\Scripts\python.exe -c "import capture; capture.ensure_model()"
```

Esperado: aparece o arquivo `hand_landmarker.task` (cerca de 7,8 MB) na pasta do projeto.

### 5. Rodar os testes automáticos

```powershell
.venv\Scripts\python.exe tools\testar.py
```

Esperado: cinco linhas `ok` e `Todos os testes passaram.` Sem o MANO, o teste da mão 3D avisa
"arquivos não encontrados ... pulando": isso é normal.

### 6. Criar os pacientes fictícios de demonstração

```powershell
.venv\Scripts\python.exe tools\criar_demonstracao.py
```

Esperado: EX-001 (5 avaliações), João (8) e Maria (9). Rodar de novo não duplica. Os dados ficam em
`dados_locais\`.

### 7. Mão 3D (opcional, feito pela pessoa)

Explique para a pessoa:

1. Criar uma conta em <https://mano.is.tue.mpg.de> e aceitar a licença (uso acadêmico, não comercial).
2. Em **Download**, baixar **Models & Code** (`mano_v1_2.zip`) para a pasta Downloads.
3. Avisar você quando terminar.

Depois rode:

```powershell
.venv\Scripts\python.exe tools\instalar_mano.py
```

(ou passe o caminho do zip: `tools\instalar_mano.py C:\caminho\mano_v1_2.zip`). Esperado:
`Mão 3D instalada.` Rode `tools\testar.py` de novo: o teste da mão 3D agora verifica os arquivos reais.

### 8. Abrir o sistema

```powershell
.venv\Scripts\python.exe sistema.py          # com a webcam
.venv\Scripts\python.exe sistema.py --sim    # mão simulada, sem câmera
```

Ou, por dois cliques: `Abrir sistema.bat` / `Abrir simulacao.bat` (abrem sem janela de terminal).

Esperado: a janela "Avaliação da mão" com a lista de pacientes. Sugira à pessoa o **Roteiro de teste** do
README.md.

---

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `Python 3.11 nao encontrado` | Passo 1: instalar o Python 3.11 (64 bits). Outras versões (3.12, 3.13) podem não ter os pacotes nessas versões. |
| `pip` falha baixando `mediapipe` | Confirme que o `.venv` é 3.11 e 64 bits (`.venv\Scripts\python.exe -c "import struct; print(struct.calcsize('P')*8)"` deve dar 64). Verifique a internet / proxy da instituição. |
| `ImportError: DLL load failed` ao importar `mediapipe` ou `cv2` | Instalar o *Microsoft Visual C++ Redistributable* (x64): `winget install -e --id Microsoft.VCRedist.2015+.x64`. |
| O `.bat` abre e fecha, ou a janela não aparece | Rode pelo terminal para ver a mensagem: `.venv\Scripts\python.exe sistema.py --sim`. |
| `não consegui abrir a câmera 0` | Outra câmera: `sistema.py --cam 1`. Feche outros programas que usam a câmera (Teams, Zoom). Verifique a permissão de câmera do Windows (Configurações > Privacidade > Câmera). |
| Erro de OpenGL / tela 3D preta | Atualize o driver de vídeo. As medidas funcionam mesmo sem a mão 3D. |
| Download do `hand_landmarker.task` falha | Baixe manualmente de `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task` e coloque na pasta do projeto. |
| A interface aparece muito pequena ou grande | Em Configurações > Interface > Tamanho (vale ao reiniciar). |

## Estrutura (resumo)

- `sistema.py`: ponto de entrada. `app/`: telas, motor da avaliação, dados. Raiz: cálculo (`kinematics.py`,
  `medidas.py`), câmera (`capture.py`), mão 3D (`hand_skin.py`).
- `tools/`: testes, demonstração, instalador do MANO e análise de gravações.
- Detalhes para manutenção: `LEIA-ME.md`.

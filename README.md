# Goniometria digital da mão — versão de testes

Sistema que mede os movimentos da mão com uma **webcam comum**, sem marcadores, para profissionais de
reabilitação. A câmera encontra 21 pontos da mão (MediaPipe) e o sistema calcula, ao vivo, os ângulos de
cada articulação dos dedos (MCP, PIP, DIP e IP do polegar), o TAM (total active motion), as repetições e a
qualidade do movimento. As avaliações ficam numa ficha por paciente, com a evolução ao longo do tempo.

> **Versão de testes, para avaliação das funcionalidades.** Use apenas dados **fictícios**. Os dados ficam
> só no computador onde o sistema está instalado (pasta `dados_locais/`), nada é enviado para a internet.

---

## Instalação rápida (Windows 10 ou 11)

**Precisa de:** Windows 10/11, **Python 3.11** (64 bits), internet durante a instalação, cerca de 1 GB de
espaço livre e, para medir de verdade, uma webcam (sem câmera dá para testar com a mão simulada).

1. Baixe o projeto: no GitHub, **Code → Download ZIP** (e descompacte), ou `git clone` do repositório.
2. Se ainda não tiver o Python 3.11: abra o PowerShell e rode
   `winget install -e --id Python.Python.3.11`
   (ou baixe em <https://www.python.org/downloads/release/python-3119/>, marcando *Add python.exe to PATH*).
3. Dê dois cliques em **`Instalar sistema.bat`**. Ele cria o ambiente Python só deste projeto (`.venv`),
   instala os pacotes, baixa o modelo de detecção da mão, roda os testes automáticos e cria 3 pacientes
   fictícios de demonstração. Leva de 2 a 10 minutos na primeira vez.
4. Abra o sistema:
   - **`Abrir sistema.bat`**: com a webcam;
   - **`Abrir simulacao.bat`**: com uma mão simulada (não precisa de câmera).

### Instalando com o Claude no VS Code

Abra a pasta do projeto no VS Code e peça ao Claude, por exemplo:

> Leia o README.md e o INSTALACAO.md deste projeto, instale todas as dependências, rode os testes e abra o
> sistema.

O [INSTALACAO.md](INSTALACAO.md) tem o passo a passo detalhado para o Claude, com as verificações e as
soluções para os problemas mais comuns.

### Mão 3D (opcional)

A tela de avaliação mostra uma mão 3D com pele (modelo **MANO**, do Max-Planck). A licença do MANO não
permite redistribuir os arquivos, então **cada pessoa baixa com a própria conta** (gratuita, uso acadêmico):

1. Crie uma conta em <https://mano.is.tue.mpg.de> e aceite a licença.
2. Em **Download**, baixe **Models & Code** (`mano_v1_2.zip`) para a pasta Downloads.
3. Dê dois cliques em **`Instalar mao 3D.bat`**.

Sem o MANO o sistema funciona e mede normalmente; só a mão 3D não aparece (a tela mostra um aviso no lugar).

---

## Roteiro de teste (10 a 15 minutos)

1. **Lista de pacientes**: três pacientes fictícios, com situação (em tratamento / alta), % do normal e
   tendência. Clique nos títulos das colunas para ordenar; use as abas *Em tratamento / Alta / Todos*.
2. **Ficha do João** (tendões flexores, zona II): veja o **Resumo** (aponta a DIP do anelar e "sugere
   déficit do flexor profundo"), clique em **Mapa** no cartão de evolução e em uma célula vermelha.
   Passe o mouse sobre os pontos do gráfico (data, valor e observação da avaliação).
3. **Ficha da Maria** (fratura do rádio distal): evolução até a **alta**, com **platô** nas últimas avaliações.
   Teste o gráfico em **Semanas desde a lesão** e o botão **Comparar** (primeira × última).
4. **Nova avaliação** (com a webcam ou a simulação): mão aberta e parada para calibrar, depois abrir e fechar
   a mão algumas vezes. Clique nos dedos, nas abas *Amplitude / Repetições / Padrão / Mão* e acompanhe a linha
   **Repetições fortes**. Ao encerrar, o sistema avisa se a medida ficou pouco confiável.
5. **Relatório**: faça um **reteste**, salve na ficha, gere o **PDF** e o **CSV**.
6. **Ajuda** (botão no topo): passo a passo e o significado de cada medida. Em quase todos os números da
   tela, **passar o mouse** mostra a explicação (o cursor vira uma seta com "?").

---

## O que o sistema faz

| Tela | Funções |
|---|---|
| **Pacientes** | cadastro (dados fictícios), busca, filtro por situação, % do normal, tendência, destaque de quem está sem avaliação há mais de 3 semanas, exportação para pesquisa |
| **Ficha** | dados do paciente, resumo clínico por regras, lista de avaliações, gráfico de evolução (datas ou semanas desde a lesão), mapa da evolução, comparação entre avaliações, exclusão de avaliação |
| **Avaliação** | câmera + mão 3D, contagem de movimentos por dedo, medidas ao vivo, aviso de mão de lado / longe / perto, qualidade da captura, contador de repetições fortes, conferência ao encerrar |
| **Relatório** | resultado por dedo, observações do profissional, reteste, PDF e CSV |
| **Configurações** | instituição e logotipo do PDF, tema claro/escuro, tamanho da interface, recálculo de avaliações antigas |
| **Ajuda** | como avaliar, como medir bem, glossário de todas as medidas, limites do sistema |

**Medidas** (detalhes na tela de Ajuda): flexão de cada articulação, TAM e TAM ativo (% do normal),
déficit de extensão, arco de movimento e arco funcional (Bain et al., 2015), escore de Strickland,
distância polpa–palma, repetições (movimento / parcial / completa), velocidades de flexão, extensão e pico,
suavidade (SPARC), ciclo, cadência e regularidade, indicadores de fadiga, consistência do esforço,
independência dos dedos e contribuição de cada articulação, abertura dos dedos e do polegar, tremor,
confiabilidade da avaliação, erro de medida por teste–reteste (MDC), mudança real, tendência e platô.

## Limites

- As medidas são **estimativas por câmera comum**, sem marcadores: não substituem a goniometria.
- O erro aumenta com a mão de lado; por isso só entram na medida os quadros com a palma até 60° da frente.
- Com uma câmera só, dedos escondidos atrás de outros não são medidos.
- A interpretação (resumo, mudança real, platô) é feita por regras explícitas: apoio à decisão, não diagnóstico.

## Dados e privacidade

- Pacientes, avaliações e pontos da mão ficam em `dados_locais/` (SQLite + arquivos `.npz`, sem vídeo).
  Essa pasta **não vai para o GitHub** (está no `.gitignore`).
- Não cadastre pacientes reais nesta versão de testes.
- Para recriar os pacientes fictícios: `.venv\Scripts\python.exe tools\criar_demonstracao.py`.

## Para quem for mexer no código

- Estrutura do projeto, como acrescentar uma medida e combinados do projeto: [LEIA-ME.md](LEIA-ME.md).
- Testes automáticos: `.venv\Scripts\python.exe tools\testar.py`.
- Opções de linha de comando: `.venv\Scripts\python.exe sistema.py --help`
  (`--sim` mão simulada, `--cam 1` outra câmera, `--resolucao 1280x720`, `--banco outro.sqlite`).

## Licenças de terceiros

- **MediaPipe** (Google) e o modelo `hand_landmarker.task`: Apache 2.0 (o modelo é baixado na instalação).
- **MANO** (Max-Planck): licença de pesquisa não comercial; não incluído (cada usuário baixa o seu).
- **PyQt5**: GPL v3. **pyqtgraph**, **NumPy**, **PyOpenGL**, **OpenCV**: licenças livres (MIT/BSD/Apache).

"""Tela de Ajuda: como fazer uma avaliação e o que significa cada medida.

As explicações das medidas vêm de app/glossario.py (o mesmo texto das dicas
ao passar o mouse); aqui ficam só o passo a passo, as dicas de captura e os limites."""

from PyQt5 import QtCore, QtWidgets

from app.componentes.cabecalho import ScreenHeader
from app import glossario
from app.tema import *  # noqa: F401,F403

# (âncora, título, corpo em HTML simples ou lista de termos do glossário)
SECTIONS = [
    ("avaliar", "Como fazer uma avaliação", """
<ol>
<li>Em <b>Pacientes</b>, abra a ficha (dois cliques) ou cadastre um paciente novo
    (nesta versão de teste, só dados fictícios).</li>
<li>Na ficha, clique em <b>Nova avaliação</b>. A câmera leva alguns segundos para abrir.</li>
<li>Peça para o paciente mostrar a mão com a <b>palma voltada para a câmera</b>, a cerca de 50 cm.</li>
<li><b>Calibração</b>: o sistema pede a mão aberta e parada por 2 segundos. Ele mede o tremor
    natural da mão e o lado (direita ou esquerda). Quem não consegue abrir toda a mão
    (ex.: contratura) pode ficar como está: depois de 5 s o sistema aceita.</li>
<li>Peça o movimento, por exemplo <b>abrir e fechar a mão o máximo que conseguir</b>, algumas vezes.
    Os cartões dos dedos contam os movimentos ao vivo; clique num dedo para ver os detalhes.</li>
<li>Clique em <b>Encerrar sessão</b>. No relatório, escreva as observações e, de vez em quando,
    faça o <b>reteste</b> (veja abaixo). Depois, <b>Salvar na ficha</b>.</li>
<li>Com a avaliação salva, gere o <b>PDF</b> ou o <b>CSV</b>. A ficha mostra a evolução.</li>
</ol>"""),
    ("medir", "Para medir bem", """
<ul>
<li><b>Luz</b> de frente para a mão, sem contraluz (janela atrás do paciente atrapalha).</li>
<li><b>Palma de frente</b> para a câmera. Com a mão de lado (mais de 60° da palma de frente), o
    MediaPipe erra os ângulos: a medição pausa e a barra do topo fica amarela.</li>
<li><b>Uma mão por vez</b> na imagem, com o punho visível (manga longe do punho).</li>
<li>A barra do topo mostra a <b>qualidade da captura</b> (velocidade da imagem, luz e quanto a mão
    é encontrada).</li>
</ul>"""),
    # seções de medidas: termos do glossário (app/glossario.py), na ordem da tela
    ("dedo", "Medidas de cada dedo (aba Amplitude)",
     ["flexao", "agora", "min", "max", "arco", "tam_agora", "tam_ativo", "pct_normal", "deficit",
      "arco_funcional", "strickland", "polpa_palma"]),
    ("repeticoes", "Repetições e qualidade do movimento (aba Repetições)",
     ["movimentos", "sensibilidade", "vel_flexao", "vel_extensao", "vel_pico", "sparc", "ciclo",
      "regularidade", "amp_fim_inicio", "vel_tendencia", "esforco", "repeticoes_fortes"]),
    ("padrao", "Padrão do movimento (aba Padrão)", ["independencia", "acompanhamento", "contribuicao"]),
    ("mao", "Mão inteira e captura (aba Mão e barra do topo)",
     ["abertura_dedos", "abertura_polegar", "tremor", "confiabilidade", "qualidade_captura", "distancia", "tam_ao_vivo"]),
    ("evolucao", "Evolução e interpretação (ficha e lista de pacientes)",
     ["reteste", "erro_medida", "mudanca_real", "faixa_erro", "tendencia", "plato", "resumo", "mapa", "semanas",
      "situacao", "ultima_avaliacao"]),
    ("limites", "Limites do sistema", """
<ul>
<li>As medidas são <b>estimativas por câmera comum</b>, sem marcadores: não substituem a goniometria.
    Use o reteste para saber o erro de medida no seu consultório.</li>
<li>O erro cresce quando a mão gira: em teste com mão renderizada, o erro médio variou de 6° a 36°
    conforme a vista. Por isso só entram na medida os quadros com a palma até 60° da frente.</li>
<li>Com uma câmera só, dedos escondidos atrás de um objeto ou da própria mão não são medidos.</li>
<li>Versão de teste: use apenas dados fictícios. Os dados ficam só neste computador.</li>
</ul>"""),
]


def help_html():
    index = " &nbsp;·&nbsp; ".join(f"<a href='#{a}' style='color:{ACCENT};'>{t}</a>" for a, t, _ in SECTIONS)
    parts = [f"<p style='color:{MUTED};'>{index}</p>"]
    for anchor, title, body in SECTIONS:
        if isinstance(body, list):                  # termos do glossário
            body = "".join(glossario.help_html(key) for key in body)
        parts.append(f"<a name='{anchor}'></a><h2 style='color:{TEXT}; margin-top:18px;'>{title}</h2>" + body)
    return f"<div style='color:{TEXT}; font-size:14px; line-height:140%;'>{''.join(parts)}</div>"


class HelpScreen(QtWidgets.QWidget):
    back = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = ScreenHeader("Ajuda", back_text="Voltar")
        self.header.subtitle.setText("Como fazer uma avaliação e o que significa cada medida")
        self.header.back.connect(self.back.emit)
        v.addWidget(self.header)
        self.text = QtWidgets.QTextBrowser()
        self.text.setOpenExternalLinks(False)
        self.text.setStyleSheet(f"QTextBrowser {{ background: {SURFACE}; border: 1px solid {BORDER};"
                                " border-radius: 8px; padding: 12px 24px; }")
        self.text.setHtml(help_html())
        self.text.setMaximumWidth(980)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(24, 16, 24, 16)
        row.addWidget(self.text)
        v.addLayout(row, stretch=1)

    def show_top(self):
        self.text.verticalScrollBar().setValue(0)

"""
Tema da interface: cores, fontes e peças básicas (rótulos, botões, cartões).
Todas as telas importam daqui (from app.tema import *), para a aparência
ficar consistente; a formatação de números e datas (app/formato.py) vem junto.

Dois temas, escuro e claro, escolhidos em Configurações. O tema é lido ao abrir
o programa: as cores viram constantes e cada tela monta seus estilos com elas
(por isso trocar de tema pede reiniciar). O palco (câmera + mão 3D) fica escuro
nos dois, como uma área de vídeo: a imagem e a mão 3D mantêm o contraste.
"""

from PyQt5 import QtCore, QtGui, QtWidgets

from icons import pixmap
from app.dados import config as _config
from app.formato import (age_from, date_labels, fmt_date, fmt_datetime, fmt_deg,  # noqa: F401
                         fmt_duration, fmt_num, fmt_pct)                          # (usados pelas telas)

THEMES = {
    "escuro": {
        "BG": "#0b1118", "SURFACE": "#111923", "SURFACE_HI": "#18232f", "BORDER": "#223041",
        "TEXT": "#e6edf3", "MUTED": "#93a1ae", "FAINT": "#4a5866",
        "ACCENT": "#4fc3f7", "ACCENT_HOVER": "#81d4fa", "ON_ACCENT": "#00151f",
        "GOOD": "#66bb6a", "FAIR": "#ffca28", "POOR": "#ef8a80", "MOVE": "#5d8fb3",
        "JOINT_PIP": "#b39ddb", "JOINT_DIP": "#4db6ac",
        "CHART_OTHERS": "#3b4856", "CHART_GUIDE": "#2c3a4a",
    },
    # contraste dos textos no pior fundo claro (branco, BG ou SURFACE_HI), WCAG >= 4,5:1:
    # TEXT 13:1, MUTED 5,2:1, ACCENT 4,8:1, GOOD 4,9:1, FAIR 4,7:1, POOR 4,6:1
    # (as cores do tema escuro sumiriam no fundo claro: o amarelo ficaria em 1,5:1)
    "claro": {
        "BG": "#eef2f6", "SURFACE": "#ffffff", "SURFACE_HI": "#e3eaf1", "BORDER": "#cfd8e1",
        "TEXT": "#17212b", "MUTED": "#55616d", "FAINT": "#a3adb8",
        "ACCENT": "#026aa7", "ACCENT_HOVER": "#01579b", "ON_ACCENT": "#ffffff",
        "GOOD": "#2a7230", "FAIR": "#8a5d00", "POOR": "#c62828", "MOVE": "#4f7ea8",
        "JOINT_PIP": "#7e57c2", "JOINT_DIP": "#00796b",
        "CHART_OTHERS": "#c3ccd5", "CHART_GUIDE": "#dde3ea",
    },
}
THEME = _config.load().get("tema", "escuro")
if THEME not in THEMES:
    THEME = "escuro"
_P = THEMES[THEME]
# Tamanho da interface (texto, botões, ícones), aplicado pelo Qt ao abrir o
# programa (QT_SCALE_FACTOR em sistema.py). Aqui só para saber o que está em uso.
SCALES = {1.0: "Normal", 1.15: "Grande", 1.3: "Muito grande"}
SCALE = float(_config.load().get("escala", 1.0))

BG = _P["BG"]
SURFACE = _P["SURFACE"]
SURFACE_HI = _P["SURFACE_HI"]
BORDER = _P["BORDER"]
TEXT = _P["TEXT"]
MUTED = _P["MUTED"]               # textos secundários (contraste ≥ 6:1 sobre SURFACE)
FAINT = _P["FAINT"]               # só para traços/fundos, nunca para texto
ACCENT = _P["ACCENT"]             # seleção / dedo em foco
ACCENT_HOVER = _P["ACCENT_HOVER"]
ON_ACCENT = _P["ON_ACCENT"]       # texto sobre ACCENT
GOOD = _P["GOOD"]                 # > 75% do normal
FAIR = _P["FAIR"]                 # 50-75%
POOR = _P["POOR"]                 # < 50%
MOVE = _P["MOVE"]                 # repetição só "movimento" (abaixo de parcial)
CHART_OTHERS = _P["CHART_OTHERS"]  # linhas dos outros dedos nos gráficos
CHART_GUIDE = _P["CHART_GUIDE"]   # linhas-guia pontilhadas (50%, 75%)
WARN = "#ffb300"                  # mão fora do quadro (faixa amarela nos dois temas)
ON_WARN = "#1a1300"
FONT = "Segoe UI"
MIN_FONT_PX = 12                  # nenhum texto abaixo disso

# Palco (câmera + mão 3D): sempre escuro, com as cores do tema escuro
VIEW_BG = "#0b1118"
VIEW_TEXT = "#e6edf3"
VIEW_MUTED = "#93a1ae"
VIEW_ACCENT = "#4fc3f7"
VIEW_GRADE_COLOR = {"ruim": "#ef8a80", "regular": "#ffca28", "bom": "#66bb6a", None: None}

GRADE_COLOR = {"ruim": POOR, "regular": FAIR, "bom": GOOD, None: None}
KIND_COLOR = {"movimento": MOVE, "parcial": FAIR, "completa": GOOD}
RELIABILITY_COLOR = {"alta": GOOD, "media": FAIR, "baixa": POOR}


def qcolor(hex_color, alpha=255):
    c = QtGui.QColor(hex_color)
    c.setAlpha(alpha)
    return c


def rgba(hex_color, a=1.0):
    c = QtGui.QColor(hex_color)
    return (c.redF(), c.greenF(), c.blueF(), a)


def blend(color, background, a):
    """Cor opaca equivalente a `color` com opacidade `a` sobre `background`."""
    c, b = QtGui.QColor(color), QtGui.QColor(background)
    mix = lambda x, y: round(a * x + (1 - a) * y)
    return QtGui.QColor(mix(c.red(), b.red()), mix(c.green(), b.green()), mix(c.blue(), b.blue())).name()


def label(text="", size=13, color=TEXT, bold=False):
    w = QtWidgets.QLabel(text)
    w.setStyleSheet(f"color: {color}; font-size: {max(size, MIN_FONT_PX)}px;"
                    f" font-weight: {700 if bold else 400}; background: transparent;")
    return w


def swatch(color, width=14):
    """Quadradinho de cor em texto rico (legendas), sem caracteres especiais."""
    return (f"<span style='background-color:{color}; color:{color};'>"
            f"{'&nbsp;' * max(2, width // 5)}</span>")


def button(text, icon_name=None, kind="secondary", checkable=False):
    """Botões padronizados: primary (destaque), secondary (contorno), quiet (barra)."""
    b = QtWidgets.QPushButton(text)
    b.setCursor(QtCore.Qt.PointingHandCursor)
    b.setCheckable(checkable)
    if icon_name:
        set_button_icon(b, icon_name, kind)
    if kind == "primary":
        css = (f"QPushButton {{ background: {ACCENT}; color: {ON_ACCENT}; border: 1px solid {ACCENT};"
               f" border-radius: 6px; padding: 7px 16px; font-size: 13px; font-weight: 600; }}"
               f"QPushButton:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}")
    elif kind == "quiet":
        css = (f"QPushButton {{ background: transparent; color: {TEXT}; border: 1px solid {BORDER};"
               f" border-radius: 6px; padding: 5px 12px; font-size: 13px; }}"
               f"QPushButton:hover {{ background: {SURFACE_HI}; }}"
               f"QPushButton:checked {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT};"
               f" font-weight: 600; }}")
    else:
        css = (f"QPushButton {{ background: transparent; color: {TEXT}; border: 1px solid {MUTED};"
               f" border-radius: 6px; padding: 7px 16px; font-size: 13px; font-weight: 600; }}"
               f"QPushButton:hover {{ background: {SURFACE_HI}; }}")
    css += f" QPushButton:disabled {{ color: {FAINT}; border-color: {BORDER}; }}"
    b.setStyleSheet(css)
    b.setIconSize(QtCore.QSize(16, 16))
    return b


def set_button_icon(b, icon_name, kind="secondary"):
    ic = QtGui.QIcon()
    normal = ON_ACCENT if kind == "primary" else TEXT
    ic.addPixmap(pixmap(icon_name, normal, 16), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    ic.addPixmap(pixmap(icon_name, ON_ACCENT, 16), QtGui.QIcon.Normal, QtGui.QIcon.On)
    ic.addPixmap(pixmap(icon_name, FAINT, 16), QtGui.QIcon.Disabled, QtGui.QIcon.Off)
    b.setIcon(ic)


JOINT_COLORS = {"MCP": ACCENT, "PIP": _P["JOINT_PIP"], "IP": _P["JOINT_PIP"], "DIP": _P["JOINT_DIP"]}
FUNCTIONAL_BAND = blend(GOOD, SURFACE, 0.35)      # faixa do arco funcional nas réguas e gráficos


# =============================================================================
# Estilos das telas de cadastro, ficha e relatório
# =============================================================================
def scrollbar_css(handle, hover, track="transparent"):
    """Barras de rolagem finas. Sem isto, o fundo herdado do QWidget fazia o Qt
    desenhar a barra nativa com um padrão quadriculado."""
    return (f"QScrollBar:vertical {{ background: {track}; width: 10px; margin: 0; border: none; }}"
            f"QScrollBar:horizontal {{ background: {track}; height: 10px; margin: 0; border: none; }}"
            f"QScrollBar::handle {{ background: {handle}; border-radius: 4px; margin: 2px; }}"
            f"QScrollBar::handle:hover {{ background: {hover}; }}"
            f"QScrollBar::handle:vertical {{ min-height: 32px; }}"
            f"QScrollBar::handle:horizontal {{ min-width: 32px; }}"
            f"QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; }}"
            f"QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}")


APP_CSS = (f"QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; font-family: '{FONT}'; }}"
           f"QToolTip {{ background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER};"
           f" padding: 6px; font-size: 13px; }}"
           + scrollbar_css(FAINT, MUTED))

# TABLE_BASE_CSS: só a tabela e os títulos. As regras de célula (::item) do
# TABLE_CSS impedem a cor de fundo de cada célula; o mapa da evolução usa só a base.
TABLE_BASE_CSS = (f"QTableWidget {{ background: {SURFACE}; color: {TEXT}; gridline-color: {BORDER};"
                  f" border: 1px solid {BORDER}; border-radius: 6px; font-size: 13px;"
                  f" selection-background-color: {SURFACE_HI}; selection-color: {TEXT}; }}"
                  f"QHeaderView::section {{ background: {SURFACE_HI}; color: {MUTED}; border: none;"
                  f" padding: 8px; font-weight: 600; font-size: 13px; }}")
TABLE_CSS = (TABLE_BASE_CSS
             + f"QTableWidget::item {{ padding: 4px 8px; border-bottom: 1px solid {BORDER}; }}"
             f"QTableWidget::item:selected {{ background: {SURFACE_HI}; color: {TEXT};"
             f" border-left: 3px solid {ACCENT}; }}")

INPUT_CSS = (f"QLineEdit, QComboBox, QDateEdit, QPlainTextEdit {{ background: {SURFACE};"
             f" color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 8px;"
             f" font-size: 13px; selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; }}"
             f"QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {{"
             f" border-color: {ACCENT}; }}"
             f"QComboBox QAbstractItemView {{ background: {SURFACE}; color: {TEXT};"
             f" selection-background-color: {SURFACE_HI}; }}")

CARD_CSS = f"background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;"


def card(object_name):
    """QFrame com o fundo de cartão (usa o nome do objeto para o estilo não vazar)."""
    frame = QtWidgets.QFrame()
    frame.setObjectName(object_name)
    frame.setStyleSheet(f"#{object_name} {{ {CARD_CSS} }}")
    return frame


def table(columns, stretch=(), selectable=False):
    """Tabela só de leitura, sem grade nem numeração das linhas. As colunas ficam
    no tamanho do conteúdo, menos as de `stretch`, que dividem a sobra.
    selectable = permite escolher uma linha (senão, nada fica selecionado)."""
    t = QtWidgets.QTableWidget(0, len(columns))
    t.setStyleSheet(TABLE_CSS)
    t.setHorizontalHeaderLabels(columns)
    t.verticalHeader().hide()
    t.setShowGrid(False)
    t.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    if selectable:
        t.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        t.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    else:
        t.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
    header = t.horizontalHeader()
    header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
    for col in stretch:
        header.setSectionResizeMode(col, QtWidgets.QHeaderView.Stretch)
    return t

"""Peças pequenas das telas: botão do dedo, réguas e barras do painel e abas
segmentadas (usadas também na ficha e na lista de pacientes)."""

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets

import kinematics as kin
from app.tema import *  # noqa: F401,F403


class FingerChip(QtWidgets.QAbstractButton):
    """Botão de um dedo: sigla, número de movimentos, faixa de cor e % do
    normal escrito (a cor sozinha não serve para quem não distingue cores)."""

    def __init__(self, finger):
        super().__init__()
        self.finger = finger
        self.count, self.color, self.pct = 0, None, None
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WA_Hover, True)
        self.setMinimumSize(60, 92)
        self._update_tooltip()

    def set_data(self, count, color, pct):
        if (count, color, pct) != (self.count, self.color, self.pct):
            self.count, self.color, self.pct = count, color, pct
            self._update_tooltip()
            self.update()

    def _update_tooltip(self):
        pct = "--" if self.pct is None else f"{self.pct * 100:.0f}%"
        self.setToolTip(f"{kin.NAME[self.finger]}: {self.count} movimentos, {pct} do normal.\n"
                        "Clique para ver os detalhes.")

    def enterEvent(self, ev):
        self.update()

    def leaveEvent(self, ev):
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        sel, hover = self.isChecked(), self.underMouse()
        border = ACCENT if sel else (MUTED if hover else BORDER)
        p.setPen(QtGui.QPen(qcolor(border), 2 if sel else 1))
        p.setBrush(qcolor(SURFACE_HI if (sel or hover) else SURFACE))
        p.drawRoundedRect(r, 6, 6)

        f = QtGui.QFont(FONT, 9)
        f.setBold(True)
        p.setFont(f)
        p.setPen(qcolor(TEXT if sel else MUTED))
        p.drawText(QtCore.QRectF(r.x(), r.y() + 5, r.width(), 18), QtCore.Qt.AlignHCenter,
                   kin.SHORT[self.finger])
        f.setPointSize(16)
        p.setFont(f)
        p.setPen(qcolor(TEXT))
        p.drawText(QtCore.QRectF(r.x(), r.y() + 22, r.width(), 30), QtCore.Qt.AlignCenter,
                   str(self.count))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(qcolor(self.color or FAINT))
        p.drawRoundedRect(QtCore.QRectF(r.x() + 10, r.y() + 56, r.width() - 20, 5), 2, 2)
        f.setPointSize(9)
        f.setBold(False)
        p.setFont(f)
        p.setPen(qcolor(MUTED))
        p.drawText(QtCore.QRectF(r.x(), r.y() + 64, r.width(), 18), QtCore.Qt.AlignHCenter,
                   "--" if self.pct is None else f"{self.pct * 100:.0f}%")


class ArcBar(QtWidgets.QWidget):
    """Régua de uma articulação, de -20° até 115% do normal:
      faixa do arco funcional (atividades diárias) por trás, em verde claro,
      déficit de extensão (0° -> menor flexão) em vermelho claro,
      arco de movimento (menor -> maior flexão) em azul,
      valor atual (ponto) e traços em 0° e no valor normal."""

    LOW = -20.0

    def __init__(self):
        super().__init__()
        self.setMinimumSize(110, 14)
        self.setMaximumHeight(14)
        self.now = self.mn = self.mx = None
        self.normal = 1.0
        self.functional = None

    def set_values(self, now, mn, mx, normal, functional=None):
        self.now, self.mn, self.mx, self.normal = now, mn, mx, normal
        self.functional = functional
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        hi = self.normal * 1.15
        x = lambda v: 4 + (w - 8) * float(np.clip((v - self.LOW) / (hi - self.LOW), 0, 1))
        y = h / 2
        p.setPen(QtCore.Qt.NoPen)
        if self.functional:
            lo_f, hi_f = self.functional
            p.setBrush(qcolor(FUNCTIONAL_BAND))
            p.drawRoundedRect(QtCore.QRectF(x(lo_f), y - 6, x(hi_f) - x(lo_f), 12), 3, 3)
        p.setBrush(qcolor(BORDER))
        p.drawRoundedRect(QtCore.QRectF(4, y - 3, w - 8, 6), 3, 3)
        if self.mn is not None and self.mx is not None:
            if self.mn > 0:                              # déficit de extensão
                p.setBrush(qcolor(POOR, 170))
                p.drawRect(QtCore.QRectF(x(0), y - 3, x(self.mn) - x(0), 6))
            p.setBrush(qcolor(ACCENT, 150))              # arco de movimento
            p.drawRect(QtCore.QRectF(x(self.mn), y - 3, max(2.0, x(self.mx) - x(self.mn)), 6))
        p.setPen(QtGui.QPen(qcolor(MUTED), 1))
        for v in (0.0, self.normal):
            p.drawLine(QtCore.QPointF(x(v), y - 6), QtCore.QPointF(x(v), y + 6))
        if self.now is not None:
            p.setPen(QtGui.QPen(qcolor(SURFACE), 1.5))
            p.setBrush(qcolor(TEXT))
            p.drawEllipse(QtCore.QPointF(x(self.now), y), 4.5, 4.5)


class ProgressBar(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(10)
        self.pct, self.color = 0.0, FAINT

    def set_value(self, pct, color):
        self.pct, self.color = pct or 0.0, color or FAINT
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(qcolor(BORDER))
        p.drawRoundedRect(QtCore.QRectF(self.rect()), 4, 4)
        p.setBrush(qcolor(self.color))
        p.drawRoundedRect(QtCore.QRectF(0, 0, self.width() * min(1.0, self.pct), self.height()), 4, 4)


class RepBars(QtWidgets.QWidget):
    """Uma barrinha por repetição, altura = amplitude: a "escadinha"."""

    MAX_BARS = 40

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(96)
        self.reps, self.normal = [], 260.0

    def set_reps(self, reps, normal):
        self.reps, self.normal = reps[-self.MAX_BARS:], normal
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        font = QtGui.QFont(FONT, 9)
        text_h = QtGui.QFontMetrics(font).height() + 2
        base = h - text_h - 2                          # espaço exato para o texto embaixo
        p.setFont(font)
        p.setPen(QtGui.QPen(qcolor(BORDER), 1))
        p.drawLine(0, base, w, base)
        if not self.reps:
            p.setPen(qcolor(MUTED))
            p.drawText(QtCore.QRectF(0, 0, w, base), QtCore.Qt.AlignCenter,
                       "As repetições vão aparecer aqui")
            return
        top = max(max(r.amplitude for r in self.reps), 0.3 * self.normal) * 1.15
        slot = w / max(len(self.reps), 12)
        bw = max(3.0, min(14.0, slot - 3))
        p.setPen(QtCore.Qt.NoPen)
        for i, r in enumerate(self.reps):
            bh = (base - 14) * r.amplitude / top
            p.setBrush(qcolor(KIND_COLOR[r.kind]))
            p.drawRoundedRect(QtCore.QRectF(i * slot + 1, base - bh, bw, bh), 2, 2)
        # primeira e última amplitude: a evolução numa olhada
        p.setPen(qcolor(MUTED))
        p.drawText(QtCore.QRectF(0, base + 2, 160, text_h), QtCore.Qt.AlignLeft,
                   f"1ª: {self.reps[0].amplitude:.0f}°")
        p.drawText(QtCore.QRectF(w - 160, base + 2, 160, text_h), QtCore.Qt.AlignRight,
                   f"última: {self.reps[-1].amplitude:.0f}°")


class SegmentedTabs(QtWidgets.QWidget):
    """Abas do painel do dedo: botões lado a lado, um ativo."""

    changed = QtCore.pyqtSignal(int)

    def __init__(self, items):
        super().__init__()
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        self.buttons = []
        for i, (text, tip) in enumerate(items):
            b = button(text, None, "quiet", checkable=True)
            # margem lateral menor: quatro abas cabem na largura do painel
            b.setStyleSheet(b.styleSheet() + " QPushButton { padding: 5px 4px; }")
            b.setToolTip(tip)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            b.clicked.connect(lambda _c, i=i: self.changed.emit(i))
            group.addButton(b)
            h.addWidget(b)
            self.buttons.append(b)
        self.buttons[0].setChecked(True)


class MetricCell(QtWidgets.QWidget):
    """Rótulo pequeno em cima, valor embaixo; a definição fica na dica (tooltip)."""

    def __init__(self, caption, tooltip):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(label(caption, 12, MUTED))
        self.value = label("--", 15, TEXT, bold=True)
        v.addWidget(self.value)
        self.setToolTip(tooltip)
        self.setCursor(QtCore.Qt.WhatsThisCursor)   # sinal de que há explicação

    def set(self, text, color=TEXT):
        self.value.setText(text)
        self.value.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: 700;"
                                 " background: transparent;")


class StackedBar(QtWidgets.QWidget):
    """Barra dividida em partes (contribuição de cada articulação)."""

    def __init__(self, height=22, alpha=255, show_text=True):
        super().__init__()
        self.setFixedHeight(height)
        self.parts, self.alpha, self.show_text = [], alpha, show_text

    def set_parts(self, parts):
        """parts = [(rótulo, fração 0..1, cor)]"""
        self.parts = parts
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QtCore.Qt.NoPen)
        if not self.parts:
            p.setBrush(qcolor(BORDER))
            p.drawRoundedRect(QtCore.QRectF(0, 0, w, h), 4, 4)
            return
        font = QtGui.QFont(FONT, 9)
        font.setBold(True)
        p.setFont(font)
        x = 0.0
        for text, frac, color in self.parts:
            seg = w * frac
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(qcolor(color, self.alpha))
            p.drawRect(QtCore.QRectF(x, 0, seg, h))
            if self.show_text and seg > 56:
                p.setPen(qcolor(ON_ACCENT))
                p.drawText(QtCore.QRectF(x, 0, seg, h), QtCore.Qt.AlignCenter,
                           f"{text} {frac * 100:.0f}%")
            x += seg

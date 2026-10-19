"""Dicas guiadas: escurece a tela, destaca uma área por vez e explica num cartão ao lado."""

from PyQt5 import QtCore, QtGui, QtWidgets

from app.tema import *  # noqa: F401,F403


class GuidedTour(QtWidgets.QWidget):
    """Cobre o widget `host`. steps = [(alvo, título, texto)]; alvo = widget ou lista de
    widgets (destaca a área que reúne todos). Esc ou "Pular dicas" encerram; Enter ou
    "Próxima" avançam. Enquanto aberto, os cliques não chegam à tela de baixo.
    Ao terminar (ou pular), emite `finished` e se apaga."""

    finished = QtCore.pyqtSignal()
    MARGIN = 6                     # folga do destaque em volta do alvo
    GAP, PAD = 16, 12              # distância cartão-alvo e cartão-borda da tela
    CARD_W = 380

    def __init__(self, host, steps, finish_text="Fechar"):
        super().__init__(host)
        self.host, self.steps, self.index = host, steps, 0
        self.finish_text = finish_text
        self._done = False
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("tourCard")
        self.card.setStyleSheet(f"#tourCard {{ background: {SURFACE}; border: 1px solid {BORDER};"
                                " border-radius: 10px; }")
        self.card.setFixedWidth(self.CARD_W)
        v = QtWidgets.QVBoxLayout(self.card)
        v.setContentsMargins(20, 16, 20, 14)
        v.setSpacing(6)
        self.counter = label("", 12, MUTED)
        self.title = label("", 16, TEXT, bold=True)
        self.text = label("", 14, TEXT)
        self.text.setWordWrap(True)
        self.text.setTextFormat(QtCore.Qt.RichText)
        for w in (self.counter, self.title, self.text):
            v.addWidget(w)
        v.addSpacing(8)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.b_skip = button("Pular dicas", None, "quiet")
        self.b_back = button("Voltar", None, "secondary")
        self.b_next = button("Próxima", None, "primary")
        self.b_skip.clicked.connect(self.finish)
        self.b_back.clicked.connect(lambda: self.go(self.index - 1))
        self.b_next.clicked.connect(lambda: self.go(self.index + 1))
        row.addWidget(self.b_skip)
        row.addStretch()
        row.addWidget(self.b_back)
        row.addWidget(self.b_next)
        v.addLayout(row)

        host.installEventFilter(self)          # acompanha o tamanho da tela
        self.setGeometry(host.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self.go(0)
        # a tela pode ter acabado de aparecer: posiciona de novo depois do layout
        QtCore.QTimer.singleShot(0, self._place)

    # ------------------------------------------------------------ navegação
    def go(self, index):
        if index >= len(self.steps):
            self.finish()
            return
        self.index = max(0, index)
        _, title, text = self.steps[self.index]
        last = self.index == len(self.steps) - 1
        self.counter.setText(f"Dica {self.index + 1} de {len(self.steps)}")
        self.title.setText(title)
        self.text.setText(text)
        self.b_back.setVisible(self.index > 0)
        self.b_skip.setVisible(not last)
        self.b_next.setText(self.finish_text if last else "Próxima")
        self._place()

    def finish(self):
        if self._done:
            return
        self._done = True
        self.host.removeEventFilter(self)
        self.hide()
        self.deleteLater()
        self.finished.emit()

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Escape:
            self.finish()
        elif ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.go(self.index + 1)
        else:
            ev.accept()

    def mousePressEvent(self, ev):
        ev.accept()                            # nada embaixo recebe o clique

    def wheelEvent(self, ev):
        ev.accept()

    # ------------------------------------------------------------- desenho
    def eventFilter(self, obj, ev):
        if obj is self.host and ev.type() == QtCore.QEvent.Resize:
            self._place()
        return False

    def _target_rect(self):
        target = self.steps[self.index][0]
        widgets = target if isinstance(target, (list, tuple)) else [target]
        rect = QtCore.QRect()
        for w in widgets:
            if w.isVisible():
                rect = rect.united(QtCore.QRect(w.mapTo(self.host, QtCore.QPoint(0, 0)), w.size()))
        m = self.MARGIN
        return rect.adjusted(-m, -m, m, m).intersected(self.rect().adjusted(2, 2, -2, -2))

    def _place(self):
        """Cartão no lado com mais espaço em volta do destaque (sem sair da tela)."""
        if self._done:
            return
        self.setGeometry(self.host.rect())
        t, r = self._target_rect(), self.rect()
        hfw = self.card.heightForWidth(self.CARD_W)   # altura exata do texto quebrado
        if hfw > 0:
            self.card.setFixedHeight(hfw)
        else:
            self.card.adjustSize()
        cw, ch = self.card.width(), self.card.height()
        sides = [  # (sobra de espaço, posição do cartão)
            (r.right() - t.right() - cw, QtCore.QPoint(t.right() + self.GAP, t.top())),
            (t.left() - r.left() - cw, QtCore.QPoint(t.left() - self.GAP - cw, t.top())),
            (r.bottom() - t.bottom() - ch, QtCore.QPoint(t.left(), t.bottom() + self.GAP)),
            (t.top() - r.top() - ch, QtCore.QPoint(t.left(), t.top() - self.GAP - ch)),
        ]
        room, pos = max(sides, key=lambda s: s[0])
        if room < 0:                           # não cabe fora: centraliza
            pos = QtCore.QPoint((r.width() - cw) // 2, (r.height() - ch) // 2)
        x = min(max(pos.x(), self.PAD), r.width() - cw - self.PAD)
        y = min(max(pos.y(), self.PAD), r.height() - ch - self.PAD)
        self.card.move(x, y)
        self.raise_()
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        hole = QtGui.QPainterPath()
        hole.addRoundedRect(QtCore.QRectF(self._target_rect()), 10, 10)
        dim = QtGui.QPainterPath()
        dim.addRect(QtCore.QRectF(self.rect()))
        p.fillPath(dim.subtracted(hole), QtGui.QColor(0, 0, 0, 160))
        # contorno claro: aparece sobre o escurecido nos dois temas
        p.setPen(QtGui.QPen(qcolor(VIEW_ACCENT), 2))
        p.drawPath(hole)

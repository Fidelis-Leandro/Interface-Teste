"""Cabeçalho padrão das telas: voltar (opcional), título, subtítulo e ações à direita."""

from PyQt5 import QtCore, QtWidgets

from app.tema import *  # noqa: F401,F403


class ScreenHeader(QtWidgets.QFrame):
    back = QtCore.pyqtSignal()

    def __init__(self, title, back_text=None):
        super().__init__()
        self.setObjectName("header")
        self.setStyleSheet(f"#header {{ background: {BG}; border-bottom: 1px solid {BORDER}; }}")
        self.setFixedHeight(64)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(12)
        if back_text:
            b = button(back_text, "back", "quiet")
            b.clicked.connect(self.back.emit)
            h.addWidget(b)
            h.addSpacing(4)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(0)
        self.title = label(title, 18, TEXT, bold=True)
        self.subtitle = label("", 13, MUTED)
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        h.addLayout(col)
        h.addStretch()
        self.actions = QtWidgets.QHBoxLayout()
        self.actions.setSpacing(8)
        h.addLayout(self.actions)

    def add_action(self, widget):
        self.actions.addWidget(widget)
        return widget

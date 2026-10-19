"""Diálogos padronizados."""

from PyQt5 import QtWidgets

from app.tema import *  # noqa: F401,F403


DIALOG_CSS = (f"QDialog {{ background: {BG}; }} QLabel {{ color: {TEXT}; }}"
              f"QTableWidget {{ background: {SURFACE}; color: {TEXT}; gridline-color: {BORDER};"
              f" border: 1px solid {BORDER}; font-size: 13px; }}"
              f"QHeaderView::section {{ background: {SURFACE_HI}; color: {MUTED};"
              f" border: none; padding: 6px; font-weight: 600; font-size: 13px; }}")


class ConfirmDialog(QtWidgets.QDialog):
    def __init__(self, title, text, confirm, cancel, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(DIALOG_CSS)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(10)
        v.addWidget(label(title, 17, TEXT, bold=True))
        msg = label(text, 14, MUTED)
        msg.setWordWrap(True)
        v.addWidget(msg)
        v.addSpacing(8)
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        b_cancel = button(cancel, None, "secondary")
        b_ok = button(confirm, None, "primary")
        b_cancel.clicked.connect(self.reject)
        b_ok.clicked.connect(self.accept)
        row.addWidget(b_cancel)
        row.addWidget(b_ok)
        v.addLayout(row)
        self.setMinimumWidth(420)

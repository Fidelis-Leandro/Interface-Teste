"""Mapa da evolução: todas as articulações (linhas) em todas as avaliações
(colunas), cada célula colorida pela flexão máxima em % do normal da
articulação. Mostra de relance qual articulação está atrasada."""

from PyQt5 import QtCore, QtGui, QtWidgets

import kinematics as kin
from app.tema import *  # noqa: F401,F403

ROWS = [(f, i, name) for f in kin.FINGERS for i, (name, _) in enumerate(kin.JOINTS[f])]


class EvolutionMap(QtWidgets.QWidget):
    """Clicar numa célula emite open_joint(dedo, índice da articulação)."""

    open_joint = QtCore.pyqtSignal(str, int)

    def __init__(self):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.table = table(["Articulação"])
        self.table.setStyleSheet(TABLE_BASE_CSS)             # deixa a cor de fundo de cada célula aparecer
        self.table.setShowGrid(True)                         # grade fina separa as células coloridas
        self.table.cellClicked.connect(self._clicked)
        v.addWidget(self.table, stretch=1)
        legend = label(f"{swatch(POOR)} abaixo de {kin.GRADE_FAIR * 100:.0f}% &nbsp; "
                       f"{swatch(FAIR)} {kin.GRADE_FAIR * 100:.0f}–{kin.GRADE_GOOD * 100:.0f}% &nbsp; "
                       f"{swatch(GOOD)} acima de {kin.GRADE_GOOD * 100:.0f}% &nbsp;·&nbsp; "
                       "flexão máxima em % do normal da articulação  ·  clique numa célula para ver o gráfico",
                       12, MUTED)
        legend.setWordWrap(True)
        v.addWidget(legend)

    def set_data(self, sessions):
        t = self.table
        t.clear()
        t.setColumnCount(1 + len(sessions))
        t.setHorizontalHeaderLabels(["Articulação"] + [fmt_date(s["inicio"])[:5] for s in sessions])
        t.setRowCount(len(ROWS))
        for r, (f, i, name) in enumerate(ROWS):
            first = name == kin.JOINTS[f][0][0]              # nome do dedo só na primeira linha dele
            head = QtWidgets.QTableWidgetItem(f"{kin.NAME[f] if first else ''}  {name}".strip())
            head.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            t.setItem(r, 0, head)
            normal = kin.NORMAL_JOINT[f][name]
            for c, s in enumerate(sessions, start=1):
                value = s["resultados"]["dedos"][f]["articulacoes"][i]["max"]
                item = QtWidgets.QTableWidgetItem("--" if value is None else f"{value / normal * 100:.0f}%")
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                if value is not None:
                    color = GRADE_COLOR[kin.grade(value / normal)]
                    item.setBackground(QtGui.QBrush(qcolor(color, 110)))
                    item.setToolTip(f"{name} do {kin.NAME[f].lower()}, {fmt_date(s['inicio'])}:\n"
                                    f"flexão máxima {value:.0f}° de {normal:.0f}° (normal)")
                t.setItem(r, c, item)
            t.setRowHeight(r, 26)
        if sessions:
            t.scrollToItem(t.item(0, len(sessions)))          # avaliações mais recentes à vista

    def _clicked(self, row, col):
        if col > 0:
            f, i, _ = ROWS[row]
            self.open_joint.emit(f, i)

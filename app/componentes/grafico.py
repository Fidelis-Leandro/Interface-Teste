"""Gráfico de TAM dos últimos 20 s."""

import numpy as np
from PyQt5 import QtGui

import pyqtgraph as pg

import kinematics as kin
from app.tema import *  # noqa: F401,F403


class TamChart(pg.PlotWidget):
    """TAM dos últimos 20 s: dedo selecionado em destaque, outros em cinza."""

    OTHERS = CHART_OTHERS

    def __init__(self):
        super().__init__()
        self.setBackground(SURFACE)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()
        self.setMenuEnabled(False)
        self.setXRange(-kin.Session.HISTORY_S - 0.4, 0.4, padding=0)   # folga: marcas das bordas aparecem
        self.setYRange(0, 280, padding=0.02)
        self.showGrid(x=False, y=True, alpha=0.12)
        font = QtGui.QFont(FONT, 9)
        for ax in ("left", "bottom"):
            a = self.getAxis(ax)
            a.setTextPen(MUTED)
            a.setPen(BORDER)
            a.setStyle(tickFont=font)
        self.getAxis("left").setTicks([[(0, "0°"), (130, "130°"), (260, "260°")]])
        self.getAxis("bottom").setTicks([[(-20, "-20 s"), (-15, "-15 s"), (-10, "-10 s"),
                                          (-5, "-5 s"), (0, "agora")]])
        self.curves = {f: self.plot(connect="finite") for f in kin.FINGERS}

    def update_data(self, history, now, selected):
        if not history:
            for c in self.curves.values():
                c.setData([], [])
            return
        t = np.array([h[0] for h in history]) - now
        values = np.array([h[1] for h in history])
        for i, f in enumerate(kin.FINGERS):
            sel = f == selected
            self.curves[f].setPen(pg.mkPen(ACCENT if sel else self.OTHERS, width=3 if sel else 1.3))
            self.curves[f].setZValue(10 if sel else 0)
            self.curves[f].setData(t, values[:, i])

"""Barra do topo (estado, qualidade da captura, tempo) e o cálculo da qualidade."""

import numpy as np
from PyQt5 import QtWidgets

from icons import pixmap
from app.glossario import tip
from app.tema import *  # noqa: F401,F403


class TopBar(QtWidgets.QFrame):
    """Só informação (nada clicável): etapa e mão, qualidade da captura,
    estado do rastreamento e tempo de sessão."""

    STATES = {
        # estado: (ícone, texto, cor do texto, fundo da barra)
        "tracking": ("dot", "Rastreando", GOOD, BG),
        "waiting": ("ring", "Aguardando a mão", MUTED, BG),
        "paused": ("pause", "Sessão pausada", FAIR, BG),
        "lost": ("alert", "Mão fora do quadro", ON_WARN, WARN),
        "other_hand": ("alert", "Outra mão na câmera", ON_WARN, WARN),
        "bad_view": ("alert", "Mão de lado: medição pausada", ON_WARN, WARN),
    }

    def __init__(self):
        super().__init__()
        self.setFixedHeight(48)
        self.setObjectName("top")
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(6)
        self.title = label("", 15, TEXT, bold=True)
        self.quality = QtWidgets.QLabel()
        self.status_icon = QtWidgets.QLabel()
        self.status = QtWidgets.QLabel()
        self.clock_icon = QtWidgets.QLabel()
        self.clock = QtWidgets.QLabel()
        for w in (self.status_icon, self.clock_icon):
            w.setStyleSheet("background: transparent;")   # a barra fica amarela no alerta
        h.addWidget(self.title)
        h.addStretch()
        h.addWidget(self.quality)
        h.addSpacing(24)
        h.addWidget(self.status_icon)
        h.addWidget(self.status)
        h.addSpacing(20)
        h.addWidget(self.clock_icon)
        h.addWidget(self.clock)
        self._state = self._quality = None
        self.set_state("waiting")

    def set_quality(self, level, text, details):
        """Qualidade da captura: "boa" / "regular" / "ruim" + motivo."""
        if (level, text) == self._quality:
            return
        self._quality = (level, text)
        self.quality.setText(text)
        self.quality.setToolTip(tip("qualidade_captura") + ("\n\n" + details if details else ""))
        self._style_quality()

    def _style_quality(self):
        dark = self._state in ("lost", "other_hand", "bad_view")
        level = self._quality[0] if self._quality else "boa"
        color = ON_WARN if dark else {"boa": MUTED, "regular": FAIR, "ruim": POOR}[level]
        self.quality.setStyleSheet(f"color: {color}; font-size: 13px; background: transparent;")

    def set_state(self, state):
        if state == self._state:
            return
        self._state = state
        icon_name, text, color, bg = self.STATES[state]
        dark = bg == WARN
        fg = ON_WARN if dark else TEXT
        self.setStyleSheet(f"#top {{ background: {bg}; border-bottom: 1px solid {BORDER}; }}")
        self.status_icon.setPixmap(pixmap(icon_name, color, 16))
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600;"
                                  " background: transparent;")
        self.title.setStyleSheet(f"color: {fg}; font-size: 15px; font-weight: 700; background: transparent;")
        self.clock_icon.setPixmap(pixmap("clock", fg, 16))
        self.clock.setStyleSheet(f"color: {fg}; font-size: 15px; background: transparent;")
        self._style_quality()


class CaptureQuality:
    """Qualidade da captura nos últimos 2 s: fps, luz e quanto a mão é detectada.
    Vira um texto curto no topo, com o motivo quando não está boa."""

    WINDOW_S = 2.0

    def __init__(self):
        self.samples = []          # (t, mão presente, brilho)

    def add(self, raw):
        t = raw["t"]
        self.samples.append((t, raw["world"] is not None, raw.get("brightness")))
        while self.samples and t - self.samples[0][0] > self.WINDOW_S:
            self.samples.pop(0)

    def evaluate(self, judge_detection=True):
        """judge_detection=False antes da avaliação: a mão ainda nem foi
        mostrada, então "mão sumindo" seria um falso alarme."""
        if len(self.samples) < 5:
            return "boa", "", ""
        span = self.samples[-1][0] - self.samples[0][0]
        fps = (len(self.samples) - 1) / span if span > 0 else 0
        detect = np.mean([s[1] for s in self.samples])
        lights = [s[2] for s in self.samples if s[2] is not None]
        light = np.mean(lights) if lights else None
        problems = []                                  # (gravidade, texto)
        if light is not None and light < 50:
            problems.append((2, "pouca luz"))
        elif light is not None and light < 80:
            problems.append((1, "luz fraca"))
        if fps < 15:
            problems.append((2, "imagem lenta (mais luz ajuda)"))
        elif fps < 22:
            problems.append((1, "imagem um pouco lenta"))
        if judge_detection and detect < 0.6:
            problems.append((2, "mão sumindo com frequência"))
        elif judge_detection and detect < 0.85:
            problems.append((1, "mão some às vezes"))
        details = (f"{fps:.0f} quadros por segundo · mão detectada em {detect * 100:.0f}% dos quadros"
                   + (f" · brilho {light:.0f}/255" if light is not None else ""))
        if not problems:
            return "boa", f"Captura boa · {fps:.0f} fps", details
        severity = max(p[0] for p in problems)
        worst = [p[1] for p in problems if p[0] == severity]
        level = "ruim" if severity == 2 else "regular"
        return level, f"Captura {level}: {', '.join(worst)}", details

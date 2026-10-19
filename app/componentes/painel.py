"""Painel do dedo: as abas de detalhe (Amplitude, Repetições, Padrão e Mão
inteira). As peças pequenas (réguas, barras, abas) ficam em pecas.py."""

from PyQt5 import QtCore, QtWidgets

import kinematics as kin
import medidas
from icons import pixmap
from app.componentes.pecas import ArcBar, MetricCell, ProgressBar, RepBars, SegmentedTabs, StackedBar
from app.glossario import explain, tip
from app.tema import *  # noqa: F401,F403



class AmplitudeTab(QtWidgets.QWidget):
    """Aba 1: TAM agora, TAM ativo e, por articulação, agora / mín / máx /
    arco com a régua (déficit de extensão + arco)."""

    def __init__(self):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(6)
        top = QtWidgets.QHBoxLayout()
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(0)
        self.tam_now = label("--", 40, TEXT, bold=True)
        self.tam_now.setMinimumWidth(self.tam_now.fontMetrics().horizontalAdvance("888°") + 12)
        left.addWidget(self.tam_now)
        left.addWidget(label("TAM agora", 12, MUTED))
        top.addLayout(left)
        top.addSpacing(8)
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(4)
        right.addStretch()
        self.active = label("--", 16, TEXT, bold=True)
        right.addWidget(self.active)
        self.active_bar = ProgressBar()
        right.addWidget(self.active_bar)
        caption = label("TAM ativo = flexão máx. − déficit de extensão", 12, MUTED)
        right.addWidget(caption)
        for w in (self.active, caption):
            explain(w, "tam_ativo", "pct_normal")
        top.addLayout(right, stretch=1)
        v.addLayout(top)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        for col, text in enumerate(("agora", "mín", "máx", "arco"), start=1):
            hdr = label(text, 12, MUTED)
            hdr.setAlignment(QtCore.Qt.AlignRight)
            explain(hdr, {"agora": "agora", "mín": "min", "máx": "max", "arco": "arco"}[text])
            grid.addWidget(hdr, 0, col)
        self.rows = []
        self._warn_pixmap = pixmap("alert", WARN, 16)
        for i in range(3):
            name = label("", 13, TEXT, bold=True)
            cells = [label("", 14, TEXT), label("", 14, MUTED), label("", 14, MUTED),
                     label("", 14, TEXT, bold=True)]
            for c in cells:
                c.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                c.setMinimumWidth(40)
            warn = QtWidgets.QLabel()
            warn.setFixedWidth(18)
            warn.setStyleSheet("background: transparent;")
            bar = ArcBar()
            r = 1 + 2 * i
            grid.addWidget(name, r, 0)
            for col, c in enumerate(cells, start=1):
                grid.addWidget(c, r, col)
            grid.addWidget(warn, r, 5)
            grid.addWidget(bar, r + 1, 0, 1, 6)
            grid.setRowMinimumHeight(r + 1, 18)
            self.rows.append((name, cells, warn, bar))
        grid.setColumnStretch(0, 1)
        v.addLayout(grid)
        legend = label(f"{swatch(POOR)} déficit de extensão &nbsp; {swatch(ACCENT)} arco de movimento"
                       f" &nbsp; {swatch(FUNCTIONAL_BAND)} arco funcional &nbsp; traços: 0° e normal", 12, MUTED)
        legend.setWordWrap(True)
        explain(legend, "deficit", "arco", "arco_funcional")
        v.addWidget(legend)
        self.functional = label("", 12, TEXT)
        self.functional.setTextFormat(QtCore.Qt.RichText)
        explain(self.functional, "arco_funcional")
        v.addWidget(self.functional)
        self.extra = label("", 12, TEXT)
        self.extra.setTextFormat(QtCore.Qt.RichText)
        explain(self.extra, "strickland", "polpa_palma")
        v.addWidget(self.extra)
        self.deficit = label("", 12, TEXT)
        self.deficit.setWordWrap(True)
        # sempre texto rico: sem nenhum <b>, o Qt trataria "&nbsp;" como texto puro
        self.deficit.setTextFormat(QtCore.Qt.RichText)
        explain(self.deficit, "deficit")
        v.addWidget(self.deficit)
        v.addStretch()

    def update_from(self, tr, hand=None):
        self.tam_now.setText(fmt_deg(tr.tam))
        pct, active = tr.percent_normal(), tr.active_tam()
        if active is None:
            self.active.setText(f"-- / {tr.normal:.0f}°")
        else:
            self.active.setText(f"{max(0.0, active):.0f}° / {tr.normal:.0f}°   ·   {pct * 100:.0f}%")
        self.active_bar.set_value(pct, GRADE_COLOR[kin.grade(pct)])
        limiting = tr.limiting_joint()
        deficits, coverage = [], []
        for i, (name, cells, warn, bar) in enumerate(self.rows):
            visible = i < len(tr.joint_names)
            for w in (name, *cells, warn, bar):
                w.setVisible(visible)
            if not visible:
                continue
            jn = tr.joint_names[i]
            now = None if tr.joints is None else tr.joints[i]
            mn = None if tr.min_joints is None else tr.min_joints[i]
            mx = None if tr.max_joints is None else tr.max_joints[i]
            name.setText(jn)
            for c, val in zip(cells, (now, mn, mx, None if mn is None else mx - mn)):
                c.setText(fmt_deg(val))
            bar.set_values(now, mn, mx, tr.normal_joints[i], medidas.functional_range(tr.finger, jn))
            cov = medidas.functional_coverage(tr.finger, jn, mn, mx)
            if cov is not None:
                color = GOOD if cov >= 0.9 else FAIR if cov >= 0.5 else POOR
                coverage.append(f"{jn} <span style='color:{color}; font-weight:600;'>{cov * 100:.0f}%</span>")
            if limiting == i:
                warn.setPixmap(self._warn_pixmap)
                warn.setToolTip("Articulação que menos se moveu nas repetições não completas")
            else:
                warn.clear()
                warn.setToolTip("")
            tol = kin.DEFICIT_TOLERANCE                  # abaixo disso: erro de medida
            if mn is None:
                deficits.append(f"{jn} --")
            elif mn > tol:
                deficits.append(f"{jn} <b>{mn:.0f}°</b>")
            elif mn < -tol:
                deficits.append(f"{jn} 0° (hiperextensão {abs(mn):.0f}°)")
            else:
                deficits.append(f"{jn} 0°")
        self.deficit.setText("Déficit de extensão: &nbsp;" + " &nbsp;·&nbsp; ".join(deficits))
        if tr.finger == "thumb":
            self.functional.setText(f"<span style='color:{MUTED};'>Arco funcional: sem referência "
                                    "para o polegar</span>")
            self.extra.setVisible(False)
            return
        self.functional.setText("Arco funcional: &nbsp;" + (" &nbsp;·&nbsp; ".join(coverage) or "--"))
        self.extra.setVisible(True)
        stk = medidas.strickland(tr.finger, tr.max_joints, tr.deficits())
        stk_txt = "--" if stk is None else f"<b>{stk * 100:.0f}%</b>, {medidas.strickland_grade(stk)}"
        tpd = (hand or {}).get("tpd", {}).get(tr.finger)
        tpd_txt = "--" if tpd is None else f"<b>≈ {fmt_num(tpd, 1)} cm</b>"
        self.extra.setText(f"Strickland (PIP + DIP): {stk_txt} &nbsp;·&nbsp; Polpa–palma: {tpd_txt}")


class RepsTab(QtWidgets.QWidget):
    """Aba 2: contagem, escadinha e qualidade do movimento."""

    SPECS = [("flex", "Velocidade de flexão", "vel_flexao"),
             ("ext", "Velocidade de extensão", "vel_extensao"),
             ("peak", "Velocidade de pico", "vel_pico"),
             ("smooth", "Suavidade (SPARC)", "sparc"),
             ("cycle", "Ciclo e cadência", "ciclo"),
             ("regular", "Regularidade", "regularidade"),
             ("change", "Amplitude: fim × início", "amp_fim_inicio"),
             ("vel_trend", "Velocidade: tendência", "vel_tendencia"),
             ("effort", "Consistência do esforço", "esforco")]

    def __init__(self):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(6)
        self.counts = label("", 13, TEXT)
        explain(self.counts, "movimentos")
        v.addWidget(self.counts)
        self.bars = RepBars()
        v.addWidget(self.bars)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        self.cells = {}
        for k, (key, caption, term) in enumerate(self.SPECS):
            cell = MetricCell(caption, tip(term))
            grid.addWidget(cell, k // 2, k % 2)
            self.cells[key] = cell
        v.addLayout(grid)
        self.sens = label("", 12, MUTED)
        self.sens.setWordWrap(True)
        v.addWidget(self.sens)
        v.addStretch()

    def update_from(self, tr, calibrated):
        c = tr.counts()
        total = sum(c.values())
        self.counts.setText(
            f"<b>{total}</b> {'movimento' if total == 1 else 'movimentos'} &nbsp;·&nbsp; "
            f"<span style='color:{FAIR}'>{c['parcial']} parciais</span> &nbsp;·&nbsp; "
            f"<span style='color:{GOOD}'>{c['completa']} completas</span>")
        self.bars.set_reps(tr.reps, tr.normal)
        q = tr.quality()
        self.cells["flex"].set(fmt_num(q["flex_velocity"], 0, " °/s"))
        self.cells["ext"].set(fmt_num(q["ext_velocity"], 0, " °/s"))
        self.cells["peak"].set(fmt_num(q["peak_velocity"], 0, " °/s"))
        self.cells["smooth"].set(fmt_num(q["sparc"], 1))
        cycle = fmt_num(q["cycle_s"], 1, " s")
        if q["cadence"] is not None:
            cycle += f" · {fmt_num(q['cadence'], 0)}/min"
        self.cells["cycle"].set(cycle)
        vt = q["vel_trend"]
        if vt is None:
            self.cells["vel_trend"].set("--")
        else:
            word, color = (("queda", FAIR) if vt < -0.10 else ("aumento", GOOD) if vt > 0.10
                           else ("estável", TEXT))
            self.cells["vel_trend"].set(f"{'−' if vt < 0 else '+'}{abs(vt) * 100:.0f}% ({word})", color)
        if q["effort"]:
            color = {"Consistente": GOOD, "Moderada": FAIR, "Variável": POOR}[q["effort"]]
            self.cells["effort"].set(f"{q['effort']} ({q['effort_cv'] * 100:.0f}%)", color)
        else:
            self.cells["effort"].set("--")
        if q["regularity"]:
            color = {"Regular": GOOD, "Moderada": FAIR, "Irregular": POOR}[q["regularity"]]
            self.cells["regular"].set(f"{q['regularity']} ({q['cv'] * 100:.0f}%)", color)
        else:
            self.cells["regular"].set("--")
        ch = q["amp_change"]
        if ch is None:
            self.cells["change"].set("--")
        else:
            word, color = (("queda", FAIR) if ch < -0.10 else ("aumento", GOOD) if ch > 0.10
                           else ("estável", TEXT))
            sign = "−" if ch < 0 else "+"
            self.cells["change"].set(f"{sign}{abs(ch) * 100:.0f}% ({word})", color)
        origin = {True: "medido na calibração", "aproximada": "calibração aproximada: "
                  "a mão não ficou parada", False: "valor padrão"}[calibrated]
        self.sens.setText(f"Sensibilidade {tr.sens:.0f}°: menor movimento contado ({origin})")


class PatternTab(QtWidgets.QWidget):
    """Aba 3: independência do dedo e contribuição de cada articulação."""

    def __init__(self):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(6)
        row = QtWidgets.QHBoxLayout()
        self.indep = label("--", 28, TEXT, bold=True)
        explain(self.indep, "independencia")
        self.indep.setMinimumWidth(self.indep.fontMetrics().horizontalAdvance("100%") + 10)
        row.addWidget(self.indep)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label("Independência do dedo", 13, TEXT, bold=True))
        expl = label("Quanto os outros dedos ficaram parados enquanto este se movia.", 12, MUTED)
        expl.setWordWrap(True)
        col.addWidget(expl)
        row.addLayout(col, stretch=1)
        v.addLayout(row)
        self.indep_bar = ProgressBar()
        v.addWidget(self.indep_bar)

        v.addSpacing(4)
        together = label("Movimento junto dos outros dedos (média das repetições)", 12, MUTED)
        explain(together, "acompanhamento")
        v.addWidget(together)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self.assoc = []
        for i in range(4):
            name = label("", 13, TEXT)
            name.setMinimumWidth(78)
            bar = ProgressBar()
            pct = label("", 13, TEXT)
            pct.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            pct.setMinimumWidth(44)
            grid.addWidget(name, i, 0)
            grid.addWidget(bar, i, 1)
            grid.addWidget(pct, i, 2)
            self.assoc.append((name, bar, pct))
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)

        v.addSpacing(6)
        v.addWidget(label("Contribuição de cada articulação no movimento", 12, MUTED))
        self.contrib = StackedBar(22)
        v.addWidget(self.contrib)
        self.reference = StackedBar(7, alpha=110, show_text=False)
        explain(self.reference, "contribuicao")
        v.addWidget(self.reference)
        self.legend = label("", 12, MUTED)
        self.legend.setWordWrap(True)
        v.addWidget(self.legend)
        note = label("Em exercícios de abrir e fechar a mão inteira, a independência é "
                     "naturalmente baixa.", 12, MUTED)
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch()

    def update_from(self, tr):
        ind = tr.independence()
        self.indep.setText("--" if ind is None else f"{ind * 100:.0f}%")
        color = None if ind is None else (GOOD if ind >= 0.75 else FAIR if ind >= 0.5 else MOVE)
        self.indep_bar.set_value(ind, color)
        coupling = tr.coupling()
        others = [g for g in kin.FINGERS if g != tr.finger]
        for (name, bar, pct), g in zip(self.assoc, others):
            name.setText(kin.NAME[g])
            val = coupling.get(g)
            bar.set_value(None if val is None else min(1.0, val), MOVE)
            # acima de 100% = o outro dedo se mexeu MAIS que este (comum na mão inteira)
            pct.setText("--" if val is None else "100%" if val >= 1.0 else f"{val * 100:.0f}%")
        contrib, names = tr.contribution(), tr.joint_names
        self.contrib.set_parts([] if contrib is None else
                               [(n, float(c), JOINT_COLORS[n]) for n, c in zip(names, contrib)])
        # partes estreitas não cabem o texto: os três valores ficam na dica
        self.contrib.setToolTip("" if contrib is None else
                                "  ·  ".join(f"{n} {c * 100:.0f}%" for n, c in zip(names, contrib)))
        ref = tr.normal_joints / tr.normal_joints.sum()
        self.reference.set_parts([(n, float(c), JOINT_COLORS[n]) for n, c in zip(names, ref)])
        self.legend.setText(" &nbsp; ".join(f"{swatch(JOINT_COLORS[n])} {n}" for n in names)
                            + " &nbsp;·&nbsp; barra fina = proporção normal ("
                            + " / ".join(f"{c * 100:.0f}%" for c in ref) + ")")


class HandTab(QtWidgets.QWidget):
    """Aba 4: medidas da mão inteira (iguais para qualquer dedo escolhido):
    abertura dos dedos e do polegar, mão parada (tremor) e confiabilidade."""

    def __init__(self):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(6)
        v.addWidget(label("Abertura dos dedos (máximo da sessão)", 12, MUTED))
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        self.spread = []
        for i, text in enumerate(("Indicador – médio", "Médio – anelar", "Anelar – mínimo", "Total")):
            grid.addWidget(label(text, 13, TEXT, bold=i == 3), i, 0)
            value = label("--", 14, TEXT, bold=True)
            value.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            grid.addWidget(value, i, 1)
            self.spread.append(value)
        grid.setColumnStretch(0, 1)
        box = QtWidgets.QWidget()
        box.setLayout(grid)
        explain(box, "abertura_dedos")
        v.addWidget(box)
        v.addSpacing(4)
        self.thumb = MetricCell("Abertura do polegar (máximo)", tip("abertura_polegar"))
        v.addWidget(self.thumb)
        self.tremor = MetricCell("Mão parada (tremor)", tip("tremor"))
        v.addWidget(self.tremor)
        self.reliability = MetricCell("Confiabilidade da sessão até agora", tip("confiabilidade"))
        v.addWidget(self.reliability)
        self.reasons = label("", 12, MUTED)
        self.reasons.setWordWrap(True)
        v.addWidget(self.reasons)
        v.addStretch()

    def update_from(self, hand):
        hand = hand or {}
        spread = hand.get("spread") or [None, None, None]
        total = None if None in spread else sum(spread)
        for w, val in zip(self.spread, list(spread) + [total]):
            w.setText(fmt_deg(val))
        self.thumb.set(fmt_deg(hand.get("thumb")))
        tr = hand.get("tremor") or {}
        if not tr.get("janelas"):
            self.tremor.set("precisa de 2 s com a mão parada", MUTED)
        elif tr["ritmico"]:
            self.tremor.set(f"oscilação de ~{fmt_num(tr['frequencia_hz'], 1)} Hz "
                            f"({fmt_num(tr['rms_mm'], 1)} mm)", FAIR)
        else:
            self.tremor.set(f"sem oscilação rítmica ({fmt_num(tr['rms_mm'], 1)} mm)")
        rel = hand.get("reliability")
        if not rel or not rel["detalhes"]["quadros"]:
            self.reliability.set("--")
            self.reasons.setText("")
            return
        self.reliability.set(medidas.RELIABILITY_NAMES[rel["nivel"]], RELIABILITY_COLOR[rel["nivel"]])
        d = rel["detalhes"]
        self.reasons.setText("; ".join(rel["motivos"]) or
                             f"{d['validos_pct']:.0f}% dos quadros com medida válida")


class DetailPanel(QtWidgets.QWidget):
    """Detalhe do dedo selecionado, em abas para não poluir o painel."""

    TABS = [("Amplitude", "Flexão, extensão e arco de cada articulação"),
            ("Repetições", "Contagem, evolução e qualidade do movimento"),
            ("Padrão", "Independência do dedo e contribuição de cada articulação"),
            ("Mão", "Abertura dos dedos e do polegar, tremor e confiabilidade da sessão")]

    def __init__(self):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(4, 6, 4, 4)
        v.setSpacing(8)
        self.title = label("", 14, MUTED, bold=True)
        v.addWidget(self.title)
        self.tabs = SegmentedTabs(self.TABS)
        v.addWidget(self.tabs)
        self.stack = QtWidgets.QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: transparent; }")
        self.pages = [AmplitudeTab(), RepsTab(), PatternTab(), HandTab()]
        for page in self.pages:
            self.stack.addWidget(page)
        # rola quando a altura não basta (notebook, tamanho de interface grande)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setWidget(self.stack)
        v.addWidget(scroll, stretch=1)
        self.tabs.changed.connect(self._show_tab)
        self._last = None

    def _show_tab(self, index):
        self.stack.setCurrentIndex(index)
        if self._last:
            self.show_tracker(*self._last)

    def show_tracker(self, tr, calibrated, hand=None):
        """Atualiza só a aba visível (as outras atualizam ao serem abertas).
        hand = medidas da mão inteira (polpa-palma, abertura, tremor, confiabilidade)."""
        self._last = (tr, calibrated, hand)
        index = self.stack.currentIndex()
        self.title.setText("MÃO INTEIRA" if index == 3 else kin.NAME[tr.finger].upper())
        if index == 0:
            self.pages[0].update_from(tr, hand)
        elif index == 1:
            self.pages[1].update_from(tr, calibrated)
        elif index == 2:
            self.pages[2].update_from(tr)
        else:
            self.pages[3].update_from(hand)

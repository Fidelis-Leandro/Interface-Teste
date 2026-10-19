"""Ficha do paciente: dados, resumo clínico, avaliações salvas, evolução (TAM ou
cada articulação) e comparação de duas avaliações.

"Mudança real" = maior que o erro de medida estimado pelos retestes
(app/dados/interpretacao.py); sem retestes suficientes, as diferenças aparecem
sem essa classificação."""

import datetime
import math
import re
import textwrap

from PyQt5 import QtCore, QtGui, QtWidgets

import pyqtgraph as pg

import kinematics as kin
import medidas
from app.componentes.cabecalho import ScreenHeader
from app.componentes.dialogos import DIALOG_CSS, ConfirmDialog
from app.componentes.mapa import EvolutionMap
from app.componentes.pecas import SegmentedTabs
from app.dados import interpretacao as interp
from app.dados.resultados import mean_pct, total_moves
from app.glossario import explain_columns
from app.tema import *  # noqa: F401,F403
from app.telas.pacientes import PatientDialog, situation_text

CHANGE_WORDS = {"melhora": "melhora real", "piora": "piora real", "estavel": "dentro do erro de medida",
                None: None}
CHANGE_COLOR = {"melhora": GOOD, "piora": POOR}


def _tip(session, value):
    """Texto do ponto do gráfico: data, valor, confiabilidade, reteste e observação."""
    res = session["resultados"]
    rel = res.get("confiabilidade") or {}
    lines = [fmt_datetime(session["inicio"]), value]
    if rel.get("nivel"):
        reasons = "; ".join(rel.get("motivos") or [])
        lines.append(f"Confiabilidade {medidas.RELIABILITY_NAMES[rel['nivel']]}" + (f": {reasons}" if reasons else ""))
    if res.get("reteste"):
        lines.append("Com reteste")
    note = (session.get("observacoes") or "").strip()
    if note:
        lines.append("")
        lines += textwrap.wrap(note, 60)
    return "\n".join(lines)


_JOINT_NAME = re.compile(r"\b(MCP|PIP|DIP|IP) do (polegar|indicador|médio|anelar|mínimo)\b")
_FINGER_BY_NAME = {kin.NAME[f].lower(): f for f in kin.FINGERS}


def _link_joints(html):
    """"DIP do anelar" -> link "ring:2" (dedo:índice da articulação), para abrir o gráfico."""
    def link(m):
        finger = _FINGER_BY_NAME[m.group(2)]
        names = [n for n, _ in kin.JOINTS[finger]]
        if m.group(1) not in names:
            return m.group(0)
        return f"<a href='{finger}:{names.index(m.group(1))}' style='color:{ACCENT};'>{m.group(0)}</a>"
    return _JOINT_NAME.sub(link, html)


def _signed_change(delta, mdc, lower_is_better=False):
    return interp.change(None if delta is None else (-delta if lower_is_better else delta), mdc)


class EvolutionChart(pg.PlotWidget):
    """Evolução entre avaliações.
    TAM: % do normal de cada dedo (o escolhido em destaque, os outros em cinza).
    Articulação: flexão máxima (linha forte) e mínima (linha fina) do dedo
    escolhido, com a faixa do arco funcional atrás.
    Ponto maior e colorido = mudança em relação à avaliação anterior maior que
    o erro de medida (verde melhora, vermelho piora). Ponto vazado = avaliação
    com confiabilidade média ou baixa. Faixa azul = erro de medida em volta da
    última avaliação (a próxima, fora dela, é mudança real). Com o mouse sobre
    um ponto aparecem a data, o valor e a observação da avaliação."""

    OTHERS = CHART_OTHERS

    def __init__(self):
        super().__init__()
        self.setBackground(SURFACE)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()
        self.setMenuEnabled(False)
        self.showGrid(x=False, y=False)
        font = QtGui.QFont(FONT, 9)
        for ax in ("left", "bottom"):
            a = self.getAxis(ax)
            a.setTextPen(MUTED)
            a.setPen(BORDER)
            a.setStyle(tickFont=font)
        self.guides = []
        for v, color, style in ((100, MUTED, QtCore.Qt.DashLine), (75, CHART_GUIDE, QtCore.Qt.DotLine),
                                (50, CHART_GUIDE, QtCore.Qt.DotLine)):
            line = pg.InfiniteLine(pos=v, angle=0, pen=pg.mkPen(color, width=1, style=style))
            self.addItem(line)
            self.guides.append(line)
        self.band = pg.LinearRegionItem(orientation="horizontal", movable=False,
                                        brush=qcolor(FUNCTIONAL_BAND, 150), pen=pg.mkPen(None))
        self.band.setZValue(-10)
        self.addItem(self.band)
        self.error_band = pg.LinearRegionItem(orientation="horizontal", movable=False,
                                              brush=qcolor(ACCENT, 40), pen=pg.mkPen(None))
        self.error_band.setZValue(-5)
        self.addItem(self.error_band)
        self.curves = {f: self.plot() for f in kin.FINGERS}
        self.joint_max, self.joint_min = self.plot(), self.plot()
        self.tips = []                     # (x, y, texto) de cada ponto em destaque
        self.scene().sigMouseMoved.connect(self._hover)

    @staticmethod
    def _markers(values, levels, mdc, base, lower_is_better=False):
        """Cor, tamanho e contorno de cada ponto. levels = confiabilidade de cada
        avaliação: "media" ou "baixa" deixam o ponto vazado."""
        brushes, sizes, pens = [], [], []
        for i, v in enumerate(values):
            c = None if i == 0 else _signed_change(v - values[i - 1], mdc, lower_is_better)
            color = CHANGE_COLOR.get(c, base)
            hollow = levels[i] in ("media", "baixa")
            brushes.append(qcolor(SURFACE if hollow else color))
            pens.append(pg.mkPen(color, width=2) if hollow else pg.mkPen(SURFACE, width=1.5))
            sizes.append(12 if c in CHANGE_COLOR else 8)
        return brushes, sizes, pens

    def _show_error_band(self, last, mdc):
        if last is None or mdc is None:
            self.error_band.hide()
        else:
            self.error_band.setRegion((last - mdc, last + mdc))
            self.error_band.show()

    def _hover(self, pos):
        """Mouse sobre um ponto: mostra os detalhes daquela avaliação."""
        vb = self.getViewBox()
        for x, y, text in self.tips:
            if (vb.mapViewToScene(QtCore.QPointF(x, y)) - pos).manhattanLength() < 10:
                QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), text, self)
                return
        QtWidgets.QToolTip.hideText()

    def _set_x_axis(self, sessions, injury):
        """Posição de cada avaliação no eixo x: uma após a outra (com a data) ou,
        com a data da lesão, em semanas desde ela (distância real no tempo)."""
        axis = self.getAxis("bottom")
        if not injury:
            labels = date_labels([s["inicio"] for s in sessions])
            step = max(1, math.ceil(len(labels) / 8))                # até ~8 datas, sem sobrepor
            axis.setTicks([[(i, t) for i, t in enumerate(labels) if i % step == 0 or i == len(labels) - 1]])
            axis.showLabel(False)
            self.setXRange(-0.3, max(len(sessions) - 1, 1) + 0.3, padding=0)
            return list(range(len(sessions)))
        start = datetime.datetime.fromisoformat(injury[:10])
        xs = [(datetime.datetime.fromisoformat(s["inicio"]) - start).total_seconds() / (7 * 86400)
              for s in sessions]
        first, last = math.floor(min(xs)), math.ceil(max(xs))
        step = max(1, math.ceil((last - first) / 8))          # semanas inteiras, até ~8 marcas
        axis.setTicks([[(w, str(w)) for w in range(first, last + 1, step)]])
        axis.setLabel("semanas desde a lesão ou cirurgia", color=MUTED)
        self.setXRange(min(xs) - 0.5, max(max(xs), min(xs) + 1) + 0.5, padding=0)
        return xs

    def set_data(self, sessions, finger, metric, error, injury=None):
        """metric = None (TAM) ou o índice da articulação do dedo;
        injury = data da lesão (aaaa-mm-dd) para o eixo em semanas, ou None."""
        x = self._set_x_axis(sessions, injury)
        levels = [(s["resultados"].get("confiabilidade") or {}).get("nivel") for s in sessions]
        self.tips = []
        if metric is None:
            mdc = error["tam_pp"]["mdc"]
            self.setYRange(0, 120, padding=0.03)
            self.getAxis("left").setTicks([[(0, "0%"), (50, "50%"), (75, "75%"), (100, "100%")]])
            for g in self.guides:
                g.show()
            self.band.hide()
            self.joint_max.setData([], [])
            self.joint_min.setData([], [])
            for f, curve in self.curves.items():
                pts = [(x[i], s["resultados"]["dedos"][f]["pct_normal"]) for i, s in enumerate(sessions)]
                xs = [px for px, v in pts if v is not None]
                ys = [v * 100 for _, v in pts if v is not None]
                sel = f == finger
                if sel:
                    lv = [levels[i] for i, (_, v) in enumerate(pts) if v is not None]
                    brushes, sizes, pens = self._markers(ys, lv, mdc, ACCENT)
                    curve.setData(xs, ys, pen=pg.mkPen(ACCENT, width=3), symbol="o", symbolSize=sizes,
                                  symbolBrush=brushes, symbolPen=pens)
                    self._show_error_band(ys[-1] if ys else None, mdc)
                    self.tips = [(x[i], v * 100, _tip(s, f"{v * 100:.0f}% do normal"))
                                 for i, (s, (_, v)) in enumerate(zip(sessions, pts)) if v is not None]
                else:
                    curve.setData(xs, ys, pen=pg.mkPen(self.OTHERS, width=1.3), symbol=None)
                curve.setZValue(10 if sel else 0)
            return
        mdc = error["articulacao"]["mdc"]
        for c in self.curves.values():
            c.setData([], [])
        for g in self.guides:
            g.hide()
        self.setYRange(-30, 130, padding=0.02)
        self.getAxis("left").setTicks([[(v, f"{v}°") for v in (-20, 0, 30, 60, 90, 120)]])
        name = kin.JOINTS[finger][metric][0]
        ref = medidas.functional_range(finger, name)
        if ref:
            self.band.setRegion(ref)
            self.band.show()
        else:
            self.band.hide()
        for key, curve, color, width, lower in (("max", self.joint_max, ACCENT, 3, False),
                                                 ("min", self.joint_min, MOVE, 1.6, True)):
            pts = [(x[i], s["resultados"]["dedos"][finger]["articulacoes"][metric][key], levels[i], s)
                   for i, s in enumerate(sessions)]
            pts = [p for p in pts if p[1] is not None]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            brushes, sizes, pens = self._markers(ys, [p[2] for p in pts], mdc, color, lower)
            curve.setData(xs, ys, pen=pg.mkPen(color, width=width), symbol="o", symbolSize=sizes,
                          symbolBrush=brushes, symbolPen=pens)
            curve.setZValue(10)
            what = "flexão máxima" if key == "max" else "flexão mínima"
            self.tips += [(px, v, _tip(s, f"{name}: {what} {fmt_num(v, 0, '°')}")) for px, v, _, s in pts]
            if key == "max":
                self._show_error_band(ys[-1] if ys else None, mdc)


class CompareDialog(QtWidgets.QDialog):
    """Duas avaliações lado a lado, dedo por dedo."""

    def __init__(self, sessions, error, finger="index", parent=None):
        super().__init__(parent)
        self.sessions, self.error, self.finger = sessions, error, finger
        self.setWindowTitle("Comparar avaliações")
        self.setStyleSheet(DIALOG_CSS + INPUT_CSS)
        self.resize(760, 640)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)
        v.addWidget(label("Comparar avaliações", 17, TEXT, bold=True))
        row = QtWidgets.QHBoxLayout()
        self.combo_a, self.combo_b = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        for combo in (self.combo_a, self.combo_b):
            combo.addItems([fmt_datetime(s["inicio"]) for s in sessions])
        self.combo_a.setCurrentIndex(0)
        self.combo_b.setCurrentIndex(len(sessions) - 1)
        row.addWidget(label("A", 13, MUTED))
        row.addWidget(self.combo_a, stretch=1)
        row.addSpacing(16)
        row.addWidget(label("B", 13, MUTED))
        row.addWidget(self.combo_b, stretch=1)
        v.addLayout(row)
        self.tabs = SegmentedTabs([(kin.NAME[f], "") for f in kin.FINGERS])
        self.tabs.buttons[kin.FINGERS.index(finger)].setChecked(True)
        self.tabs.changed.connect(self._select)
        v.addWidget(self.tabs)
        self.table = table(["Medida", "A", "B", "B − A", "Mudança"], stretch=(0,))
        explain_columns(self.table, {4: "mudanca_real"})
        v.addWidget(self.table, stretch=1)
        note = label(interp.error_note(error), 12, MUTED)
        note.setWordWrap(True)
        v.addWidget(note)
        close = button("Fechar", None, "secondary")
        close.clicked.connect(self.accept)
        v.addWidget(close, alignment=QtCore.Qt.AlignRight)
        for combo in (self.combo_a, self.combo_b):        # só depois que a tabela existe
            combo.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def _select(self, index):
        self.finger = kin.FINGERS[index]
        self.refresh()

    def _rows(self, a, b):
        """(medida, valor A, valor B, unidade, casas, MDC ou None, menor é melhor)."""
        f = self.finger
        da, db = a["dedos"][f], b["dedos"][f]
        pct = lambda v: None if v is None else v * 100
        e_tam, e_joint = self.error["tam_pp"]["mdc"], self.error["articulacao"]["mdc"]
        rows = [("TAM ativo (% do normal)", pct(da["pct_normal"]), pct(db["pct_normal"]), "%", 0, e_tam, False),
                ("TAM ativo (°)", da["tam_ativo"], db["tam_ativo"], "°", 0, None, False)]
        if f != "thumb":
            rows.append(("Strickland (PIP + DIP)", pct(interp.finger_strickland(f, da)),
                         pct(interp.finger_strickland(f, db)), "%", 0, None, False))
            rows.append(("Polpa–palma (≈ cm)", da.get("polpa_palma_cm"), db.get("polpa_palma_cm"),
                         " cm", 1, None, True))
        for ja, jb in zip(da["articulacoes"], db["articulacoes"]):
            n = ja["nome"]
            rows += [(f"{n}: flexão máxima", ja["max"], jb["max"], "°", 0, e_joint, False),
                     (f"{n}: flexão mínima (extensão)", ja["min"], jb["min"], "°", 0, e_joint, True)]
            if f != "thumb":
                rows.append((f"{n}: arco funcional", pct(interp.joint_coverage(f, ja)),
                             pct(interp.joint_coverage(f, jb)), "%", 0, None, False))
        qa, qb = da["qualidade"], db["qualidade"]
        rows += [("Movimentos", da["movimentos"], db["movimentos"], "", 0, None, False),
                 ("Independência", pct(da["independencia"]), pct(db["independencia"]), "%", 0, None, False),
                 ("Velocidade de pico", qa.get("peak_velocity"), qb.get("peak_velocity"), " °/s", 0, None, False),
                 ("Suavidade (SPARC)", qa.get("sparc"), qb.get("sparc"), "", 1, None, False)]
        wa, wb = a.get("mao_inteira") or {}, b.get("mao_inteira") or {}
        rows += [("Mão: abertura dos dedos (total)", wa.get("abertura_dedos_total"),
                  wb.get("abertura_dedos_total"), "°", 0, None, False),
                 ("Mão: abertura do polegar", wa.get("abertura_polegar"), wb.get("abertura_polegar"),
                  "°", 0, None, False)]
        return rows

    def refresh(self):
        a = self.sessions[self.combo_a.currentIndex()]["resultados"]
        b = self.sessions[self.combo_b.currentIndex()]["resultados"]
        rows = self._rows(a, b)
        self.table.setRowCount(len(rows))
        fmt = lambda v, unit, dec: "--" if v is None else fmt_num(v, dec, unit)
        for r, (name, va, vb, unit, dec, mdc, lower) in enumerate(rows):
            delta = None if va is None or vb is None else vb - va
            c = _signed_change(delta, mdc, lower)
            delta_txt = "--" if delta is None else ("+" if delta >= 0 else "−") + fmt_num(abs(delta), dec, unit)
            cells = [name, fmt(va, unit, dec), fmt(vb, unit, dec), delta_txt, CHANGE_WORDS[c] or "--"]
            for col, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                if col:
                    item.setTextAlignment(QtCore.Qt.AlignCenter)
                if col == 4 and c in CHANGE_COLOR:
                    item.setForeground(QtGui.QBrush(qcolor(CHANGE_COLOR[c])))
                self.table.setItem(r, col, item)
            self.table.setRowHeight(r, 30)


class RecordScreen(QtWidgets.QWidget):
    back = QtCore.pyqtSignal()
    new_evaluation = QtCore.pyqtSignal(int)
    open_help = QtCore.pyqtSignal()
    open_session = QtCore.pyqtSignal(int)

    COLUMNS = ["Data", "Mão", "% normal", "Movim.", "Confiab."]

    def __init__(self, db, get_config):
        super().__init__()
        self.db, self.get_config = db, get_config
        self.pid, self.patient, self.sessions = None, {}, []
        self.selected = "index"
        self.metric = None                    # None = TAM; senão, índice da articulação
        self.weeks = False                    # eixo do gráfico: datas ou semanas desde a lesão
        self.map_view = False                 # cartão de evolução: gráfico ou mapa
        self.error = interp.measurement_error([])

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = ScreenHeader("", back_text="Pacientes")
        self.header.back.connect(self.back.emit)
        b_help = self.header.add_action(button("Ajuda", "help", "quiet"))
        b_help.setToolTip("O que significa cada medida")
        b_help.clicked.connect(self.open_help.emit)
        b_edit = self.header.add_action(button("Editar dados", "edit", "quiet"))
        b_edit.clicked.connect(self.edit_patient)
        b_new = self.header.add_action(button("Nova avaliação", "play", "primary"))
        b_new.clicked.connect(lambda: self.new_evaluation.emit(self.pid))
        v.addWidget(self.header)

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(14)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(14)
        # --- dados ---
        data_card = card("dataCard")
        dv = QtWidgets.QVBoxLayout(data_card)
        dv.setContentsMargins(16, 12, 16, 12)
        dv.addWidget(label("Dados do paciente", 14, TEXT, bold=True))
        self.data_grid = QtWidgets.QGridLayout()
        self.data_grid.setHorizontalSpacing(12)
        self.data_grid.setVerticalSpacing(6)
        dv.addLayout(self.data_grid)
        self.data_labels = {}
        for r, (key, text) in enumerate((("nascimento", "Nascimento"), ("mao_dominante", "Mão dominante"),
                                         ("mao_avaliada", "Mão avaliada"), ("condicao", "Condição"),
                                         ("data_lesao", "Lesão / cirurgia"), ("profissional", "Profissional"),
                                         ("situacao", "Situação"), ("observacoes", "Observações"))):
            k = label(text, 13, MUTED)
            k.setAlignment(QtCore.Qt.AlignTop)
            val = label("", 13, TEXT)
            val.setWordWrap(True)
            self.data_grid.addWidget(k, r, 0)
            self.data_grid.addWidget(val, r, 1)
            self.data_labels[key] = val
        self.data_grid.setColumnStretch(1, 1)
        left.addWidget(data_card)

        # --- avaliações ---
        ses_card = card("sesCard")
        sv = QtWidgets.QVBoxLayout(ses_card)
        sv.setContentsMargins(16, 12, 16, 12)
        sv.setSpacing(8)
        sv.addWidget(label("Avaliações", 14, TEXT, bold=True))
        self.table = table(self.COLUMNS, stretch=(1,), selectable=True)     # "Mão" ocupa a sobra
        explain_columns(self.table, {2: "pct_normal", 3: "movimentos", 4: "confiabilidade"})
        self.table.setToolTip("% normal = média dos 5 dedos. Confiab. = confiabilidade da captura.\n"
                              "Dois cliques abrem o relatório.")
        self.table.cellDoubleClicked.connect(lambda r, _c: self._open_row(r))
        self.table.itemSelectionChanged.connect(self._sync)
        sv.addWidget(self.table, stretch=1)
        self.no_sessions = label("Nenhuma avaliação ainda. Clique em Nova avaliação.", 13, MUTED)
        self.no_sessions.setAlignment(QtCore.Qt.AlignCenter)
        sv.addWidget(self.no_sessions, stretch=1)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.b_compare = button("Comparar", "search", "secondary")
        self.b_compare.setToolTip("Abre com a primeira e a última avaliação, lado a lado, dedo por dedo\n"
                                  "(dá para escolher outras)")
        self.b_compare.clicked.connect(self.compare)
        self.b_delete = button("Excluir", "trash", "secondary")
        self.b_delete.setToolTip("Apaga a avaliação selecionada (ex.: feita por engano ou com captura ruim)")
        self.b_delete.clicked.connect(self.delete_session)
        self.b_report = button("Abrir relatório", "file", "secondary")
        self.b_report.clicked.connect(lambda: self._open_row(self.table.currentRow()))
        buttons.addWidget(self.b_compare)
        buttons.addWidget(self.b_delete)
        buttons.addWidget(self.b_report)
        sv.addLayout(buttons)
        left.addWidget(ses_card, stretch=1)

        left_box = QtWidgets.QWidget()
        left_box.setLayout(left)
        left_box.setFixedWidth(500)          # cabe a tabela de avaliações com os títulos inteiros
        body.addWidget(left_box)

        right = QtWidgets.QVBoxLayout()
        right.setSpacing(14)
        # --- resumo clínico ---
        sum_card = card("sumCard")
        smv = QtWidgets.QVBoxLayout(sum_card)
        smv.setContentsMargins(16, 12, 16, 12)
        smv.setSpacing(6)
        smv.addWidget(label("Resumo", 14, TEXT, bold=True))
        self.summary = label("", 13, TEXT)
        self.summary.setTextFormat(QtCore.Qt.RichText)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(QtCore.Qt.LinksAccessibleByMouse)
        self.summary.linkActivated.connect(self._summary_link)
        smv.addWidget(self.summary)
        self.error_note = label("", 12, MUTED)
        self.error_note.setWordWrap(True)
        self.error_note.setTextFormat(QtCore.Qt.RichText)
        smv.addWidget(self.error_note)
        right.addWidget(sum_card)

        # --- evolução ---
        evo_card = card("evoCard")
        ev = QtWidgets.QVBoxLayout(evo_card)
        ev.setContentsMargins(16, 12, 16, 12)
        ev.setSpacing(8)
        title_row = QtWidgets.QHBoxLayout()
        self.view_tabs = SegmentedTabs([("Gráfico", "Evolução de um dedo ou de uma articulação"),
                                        ("Mapa", "Todas as articulações em todas as avaliações, "
                                         "coloridas pelo % do normal")])
        self.view_tabs.setFixedWidth(200)
        self.view_tabs.changed.connect(self._select_view)
        title_row.addWidget(self.view_tabs, alignment=QtCore.Qt.AlignTop)
        self.evo_title = label("", 14, TEXT, bold=True)
        self.evo_title.setWordWrap(True)
        title_row.addWidget(self.evo_title, stretch=1)
        self.axis_tabs = SegmentedTabs([("Datas", "Uma avaliação depois da outra, com a data"),
                                        ("Semanas desde a lesão", "Distância real no tempo, contada "
                                         "da data da lesão ou cirurgia (cadastro)")])
        self.axis_tabs.setFixedWidth(380)
        self.axis_tabs.changed.connect(self._select_axis)
        title_row.addWidget(self.axis_tabs, alignment=QtCore.Qt.AlignTop)
        ev.addLayout(title_row)
        self.finger_tabs = SegmentedTabs([(kin.NAME[f], f"Ver a evolução do {kin.NAME[f].lower()}")
                                          for f in kin.FINGERS])
        self.finger_tabs.buttons[kin.FINGERS.index(self.selected)].setChecked(True)
        self.finger_tabs.changed.connect(self._select_finger)
        ev.addWidget(self.finger_tabs)
        self.metric_tabs = SegmentedTabs([("TAM ativo", "% do normal de cada dedo"),
                                          ("MCP", ""), ("PIP", ""), ("DIP", "")])
        self.metric_tabs.changed.connect(self._select_metric)
        ev.addWidget(self.metric_tabs)
        self.chart = EvolutionChart()
        ev.addWidget(self.chart, stretch=1)
        self.chart_hint = label("Faixa azul: erro de medida em volta da última avaliação  ·  ponto vazado: "
                                "confiabilidade média ou baixa  ·  passe o mouse num ponto para ver os detalhes",
                                12, MUTED)
        self.chart_hint.setWordWrap(True)
        ev.addWidget(self.chart_hint)
        self.map = EvolutionMap()
        self.map.open_joint.connect(self.show_joint)
        ev.addWidget(self.map, stretch=1)
        self.no_evolution = label("A evolução aparece a partir da primeira avaliação salva.", 14, MUTED)
        self.no_evolution.setAlignment(QtCore.Qt.AlignCenter)
        ev.addWidget(self.no_evolution, stretch=1)
        self.compare_text = label("", 13, TEXT)
        self.compare_text.setTextFormat(QtCore.Qt.RichText)
        self.compare_text.setWordWrap(True)
        ev.addWidget(self.compare_text)
        right.addWidget(evo_card, stretch=1)
        body.addLayout(right, stretch=1)
        v.addLayout(body, stretch=1)

    # ---------------------------------------------------------------- dados
    def show_patient(self, pid):
        self.pid = pid
        self.patient = self.db.paciente(pid) or {}
        self.sessions = self.db.sessoes(pid)
        self.error = interp.measurement_error([s["resultados"] for s in self.db.todas_sessoes()])
        p = self.patient
        age = age_from(p.get("nascimento"))
        self.header.title.setText(p.get("identificacao") or "")
        parts = ["--" if age is None else f"{age} anos"]
        if p.get("mao_avaliada"):
            parts.append(f"avalia mão {p['mao_avaliada'].lower()}")
        parts.append(f"{len(self.sessions)} {'avaliação' if len(self.sessions) == 1 else 'avaliações'}")
        if p.get("situacao") == "alta":
            parts.append(situation_text(p).lower())
        self.header.subtitle.setText("  ·  ".join(parts))
        # semanas desde a lesão: só com a data da lesão no cadastro
        has_injury = bool(p.get("data_lesao"))
        self.axis_tabs.buttons[1].setEnabled(has_injury)
        self.axis_tabs.buttons[1].setToolTip("" if has_injury else "Preencha a data da lesão ou cirurgia no cadastro")
        if not has_injury and self.weeks:
            self.weeks = False
            self.axis_tabs.buttons[0].setChecked(True)

        injury = fmt_date(p.get("data_lesao"))
        if p.get("data_lesao"):
            weeks = (datetime.date.today() - datetime.date.fromisoformat(p["data_lesao"][:10])).days // 7
            injury += f"  (há {weeks} semanas)" if weeks >= 0 else ""
        values = {"nascimento": fmt_date(p.get("nascimento")) + ("" if age is None else f"  ({age} anos)"),
                  "mao_dominante": p.get("mao_dominante") or "--", "mao_avaliada": p.get("mao_avaliada") or "--",
                  "condicao": p.get("condicao") or "--", "data_lesao": injury,
                  "profissional": p.get("profissional") or "--", "situacao": situation_text(p),
                  "observacoes": p.get("observacoes") or "--"}
        for k, val in values.items():
            self.data_labels[k].setText(val)

        recent_first = list(reversed(self.sessions))
        self.table.setRowCount(len(recent_first))
        for r, s in enumerate(recent_first):
            res = s["resultados"]
            pct = mean_pct(res)
            rel = (res.get("confiabilidade") or {}).get("nivel")
            cells = [fmt_datetime(s["inicio"]), {"Right": "dir.", "Left": "esq."}.get(s["mao"], "--"),
                     "--" if pct is None else f"{pct * 100:.0f}%", str(total_moves(res)),
                     "--" if rel is None else medidas.RELIABILITY_NAMES[rel]]
            tip = "Com reteste." if res.get("reteste") else ""
            if rel and rel != "alta":
                tip = (tip + " " if tip else "") + "Confiabilidade: " + "; ".join(res["confiabilidade"]["motivos"])
            for c, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                item.setToolTip(tip)
                if c == 2 and pct is not None:
                    item.setForeground(QtGui.QBrush(qcolor(GRADE_COLOR[kin.grade(pct)])))
                if c == 4 and rel:
                    item.setForeground(QtGui.QBrush(qcolor(RELIABILITY_COLOR[rel])))
                self.table.setItem(r, c, item)
            self.table.setRowHeight(r, 38)
        self.table.setVisible(bool(self.sessions))
        self.no_sessions.setVisible(not self.sessions)
        summary = "<br>".join(interp.clinical_summary(self.sessions, self.error))
        self.summary.setText(_link_joints(summary) if summary else "Sem avaliações ainda.")
        self.error_note.setText(self._error_text())
        self._sync()
        self._update_metric_tabs()
        self._update_evolution()

    def _sync(self):
        selected = self.table.currentRow() >= 0 and bool(self.sessions)
        self.b_report.setEnabled(selected)
        self.b_delete.setEnabled(selected)
        self.b_compare.setEnabled(len(self.sessions) >= 2)

    def _selected_session(self):
        recent_first = list(reversed(self.sessions))
        row = self.table.currentRow()
        return recent_first[row] if 0 <= row < len(recent_first) else None

    def _open_row(self, row):
        recent_first = list(reversed(self.sessions))
        if 0 <= row < len(recent_first):
            self.open_session.emit(recent_first[row]["id"])

    def delete_session(self):
        s = self._selected_session()
        if s is None:
            return
        dlg = ConfirmDialog("Excluir esta avaliação?",
                            f"A avaliação de {fmt_datetime(s['inicio'])} e os pontos da mão gravados nela "
                            "serão apagados. Isso não pode ser desfeito.", "Excluir", "Cancelar", self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.db.excluir_sessao(s["id"])
            self.show_patient(self.pid)

    def _error_text(self):
        """Nota do erro de medida; sem retestes suficientes, vira um lembrete."""
        pairs = self.error.get("tam_pp") or {"n": 0, "mdc": None}
        if pairs["mdc"] is not None:
            return interp.error_note(self.error)
        missing = max(1, math.ceil((interp.MIN_PAIRS - pairs["n"]) / len(kin.FINGERS)))
        return (f"<b style='color:{FAIR}'>Lembrete:</b> faça um reteste na próxima avaliação. "
                f"{'Falta' if missing == 1 else 'Faltam'} {missing} "
                f"{'reteste' if missing == 1 else 'retestes'} para o sistema saber o próprio erro de "
                "medida e marcar o que é mudança real.")

    def _summary_link(self, href):
        finger, joint = href.split(":")
        self.show_joint(finger, int(joint))

    def show_joint(self, finger, joint):
        """Abre o gráfico de uma articulação (clique no mapa ou num link do Resumo)."""
        self.view_tabs.buttons[0].click()
        self.finger_tabs.buttons[kin.FINGERS.index(finger)].click()
        self.metric_tabs.buttons[joint + 1].click()

    def compare(self):
        if len(self.sessions) >= 2:
            CompareDialog(self.sessions, self.error, self.selected, self).exec_()

    # ------------------------------------------------------------- evolução
    def _select_finger(self, index):
        self.selected = kin.FINGERS[index]
        self._update_metric_tabs()
        self._update_evolution()

    def _select_view(self, index):
        self.map_view = index == 1
        self._update_evolution()

    def _select_axis(self, index):
        self.weeks = index == 1
        self._update_evolution()

    def _select_metric(self, index):
        self.metric = None if index == 0 else index - 1
        self._update_evolution()

    def _update_metric_tabs(self):
        names = [n for n, _ in kin.JOINTS[self.selected]]
        for i, b in enumerate(self.metric_tabs.buttons[1:]):
            b.setVisible(i < len(names))
            if i < len(names):
                b.setText(names[i])
                b.setToolTip(f"Flexão máxima e mínima da {names[i]} ao longo das avaliações")
        if self.metric is not None and self.metric >= len(names):
            self.metric = None
            self.metric_tabs.buttons[0].setChecked(True)

    def _update_evolution(self):
        has = bool(self.sessions)
        graph = has and not self.map_view
        self.chart.setVisible(graph)
        self.chart_hint.setVisible(graph)
        self.map.setVisible(has and self.map_view)
        for w in (self.finger_tabs, self.metric_tabs, self.axis_tabs):     # o mapa mostra todos os dedos
            w.setVisible(not self.map_view)
        self.no_evolution.setVisible(not has)
        if self.map_view:
            self.evo_title.setText("Mapa da evolução: flexão máxima de cada articulação")
            self.compare_text.setText("")
            self.map.set_data(self.sessions)
            return
        name = kin.NAME[self.selected]
        if self.metric is None:
            self.evo_title.setText("Evolução do TAM ativo (% do normal)")
        else:
            joint = kin.JOINTS[self.selected][self.metric][0]
            band = "" if self.selected == "thumb" else " · faixa verde: arco funcional"
            self.evo_title.setText(f"Evolução da {joint} do {name.lower()}: flexão máxima (linha forte) "
                                   f"e mínima (linha fina){band}")
        if not has:
            self.compare_text.setText("")
            return
        injury = self.patient.get("data_lesao") if self.weeks else None
        self.chart.set_data(self.sessions, self.selected, self.metric, self.error, injury)
        self.compare_text.setText(self._compare_text())

    def _describe(self, delta, unit, mdc, lower_is_better=False):
        c = _signed_change(delta, mdc, lower_is_better)
        sign = "+" if delta >= 0 else "−"
        txt = f"{sign}{abs(delta):.0f}{unit}"
        if c is None:
            return txt
        color = CHANGE_COLOR.get(c, MUTED)
        return f"{txt} <span style='color:{color};'>({CHANGE_WORDS[c]})</span>"

    def _compare_text(self):
        name = kin.NAME[self.selected]
        dedos = [s["resultados"]["dedos"][self.selected] for s in self.sessions]
        if self.metric is None:
            series = [None if d["pct_normal"] is None else d["pct_normal"] * 100 for d in dedos]
            last, mdc, unit = series[-1], self.error["tam_pp"]["mdc"], " pp"
            if last is None:
                return f"{name}: sem dados na última avaliação."
            text = f"<b>{name}: {last:.0f}%</b> na última avaliação"
            if len(series) >= 2 and series[-2] is not None:
                text += f"  ·  {self._describe(last - series[-2], unit, mdc)} em relação à anterior"
            if len(series) >= 3 and series[0] is not None:
                text += f"  ·  {self._describe(last - series[0], unit, mdc)} em relação à primeira"
            return text
        joints = [d["articulacoes"][self.metric] for d in dedos]
        jn, mdc = joints[-1]["nome"], self.error["articulacao"]["mdc"]
        last = joints[-1]
        if last["max"] is None:
            return f"{jn} do {name.lower()}: sem dados na última avaliação."
        text = f"<b>{jn} do {name.lower()}</b>: flexão máx. {last['max']:.0f}°, mín. {last['min']:.0f}°"
        cov = interp.joint_coverage(self.selected, last)
        if cov is not None:
            text += f", arco funcional {cov * 100:.0f}%"
        if len(joints) >= 2 and joints[-2]["max"] is not None:
            prev = joints[-2]
            text += (f"  ·  em relação à anterior: máx. {self._describe(last['max'] - prev['max'], '°', mdc)}, "
                     f"mín. {self._describe(last['min'] - prev['min'], '°', mdc, lower_is_better=True)}")
        return text

    # -------------------------------------------------------------- edição
    def edit_patient(self):
        dlg = PatientDialog(self.patient, self.get_config().get("profissional_padrao", ""), self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        if dlg.result_action == "excluir":
            self.db.excluir_paciente(self.pid)
            self.back.emit()
        elif dlg.result_action == "salvar":
            self.db.salvar_paciente(dlg.data(), self.pid)
            self.show_patient(self.pid)

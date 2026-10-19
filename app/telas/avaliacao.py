"""
Tela de avaliação: mostra o que o motor (app/avaliador.py) decide a cada quadro.

A câmera só fica aberta enquanto esta tela está em uso: start() cria a fonte
(câmera, simulação ou gravação) e stop() fecha. "Encerrar sessão" emite
`finished` com os resultados (a tela de relatório decide salvar ou descartar);
sem dados ainda, oferece sair e emite `cancelled`.

Reteste (start_retest): a mesma avaliação repetida logo em seguida, com a mão
reposicionada e calibrada de novo; emite `retest_finished`.
"""

import time

import numpy as np
from PyQt5 import QtCore, QtWidgets

import geometria
import hand_skin
import kinematics as kin
import medidas
from app.avaliador import Avaliador
from app.componentes.dialogos import ConfirmDialog
from app.componentes.grafico import TamChart
from app.componentes.guia import GuidedTour
from app.componentes.painel import DetailPanel
from app.componentes.pecas import FingerChip
from app.componentes.palco import Hand3D, StageToolbar, ViewStage
from app.componentes.topo import CaptureQuality, TopBar
from app.glossario import explain
from app.tema import *  # noqa: F401,F403

DISTANCE_TEXT = {"longe": "Mão longe: aproxime da câmera (cerca de 50 cm)",
                 "perto": "Mão muito perto: afaste um pouco da câmera"}
TIMER_MS = 33                 # ~30 fps
PANEL_REFRESH_S = 0.2         # números do painel: 5x por segundo (legíveis)
PHASE_TITLES = {"preparacao": "Preparação", "calibracao": "Calibração", "avaliacao": "Avaliação"}


class EvaluationScreen(QtWidgets.QWidget):
    finished = QtCore.pyqtSignal(dict)       # resultados da sessão encerrada
    cancelled = QtCore.pyqtSignal()          # saiu sem dados para salvar
    retest_finished = QtCore.pyqtSignal(dict)    # resultados do reteste
    retest_cancelled = QtCore.pyqtSignal()       # saiu do reteste sem medir

    def __init__(self, source_factory):
        """source_factory() -> (fonte, nome da fonte)."""
        super().__init__()
        self.source_factory = source_factory
        self.source = None
        self.source_name = ""
        self.patient = {}
        self.hand3d = Hand3D()                   # criada uma vez só (OpenGL)
        self.selected = "index"
        self.av = Avaliador()
        self.quality = CaptureQuality()
        self.distance = medidas.DistanceCheck()
        self.needs_retest = False                # a janela informa: o sistema ainda não sabe o próprio erro
        self._last_panel = 0.0
        self._last_colors = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.top = TopBar()
        root.addWidget(self.top)

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(10, 8, 10, 6)
        body.setSpacing(10)
        stage_box = QtWidgets.QVBoxLayout()
        stage_box.setSpacing(0)
        self.toolbar = StageToolbar()
        stage_box.addWidget(self.toolbar)
        self.stage = ViewStage(self.hand3d.view)
        stage_box.addWidget(self.stage, stretch=1)
        body.addLayout(stage_box, stretch=1)
        self.panel = self._build_panel()
        body.addWidget(self.panel)
        root.addLayout(body, stretch=1)
        self.bottom = self._build_bottom()
        root.addWidget(self.bottom)

        self.toolbar.btn_3d.clicked.connect(lambda: self.stage.set_camera_main(False))
        self.toolbar.btn_cam.clicked.connect(lambda: self.stage.set_camera_main(True))
        self.stage.swapped.connect(self.toolbar.sync)
        self.toolbar.btn_center.clicked.connect(self.hand3d.reset_camera)
        self.toolbar.btn_full.clicked.connect(self.toggle_expanded)
        self.toolbar.btn_tips.clicked.connect(lambda: self.show_tips())
        self.expanded = False
        self._tour = None

        self.timer = QtCore.QTimer(self)
        self.timer.setTimerType(QtCore.Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self._refresh_panel(force=True)
        self._update_actions()

    # ------------------------------------------------------------- ciclo de vida
    def prepare(self, patient):
        """Tela zerada para o paciente, ainda sem abrir a câmera (ex.: durante as dicas)."""
        self.stop()
        self.patient = patient or {}
        self._reset(Avaliador())

    def start(self, patient):
        """Começa uma sessão nova para o paciente (abre a fonte)."""
        self.prepare(patient)
        # a câmera e o MediaPipe levam alguns segundos para abrir e a tela fica parada
        self.stage.show_message("Abrindo a câmera…", "Isso leva alguns segundos.")
        QtWidgets.QApplication.processEvents()
        try:
            self.source, self.source_name = self.source_factory()
        except Exception as exc:                 # câmera ocupada, ausente...
            self.source = None
            self.stage.show_message("Não foi possível abrir a câmera",
                                    f"{exc}. Feche outros programas que usem a câmera e tente "
                                    "de novo pela ficha do paciente.")
            self._update_actions()
            return
        self._update_actions()
        self.timer.start(TIMER_MS)

    def start_retest(self):
        """Reteste logo após a avaliação: medições novas, mesma gravação de pontos,
        mão pedida de novo e recalibrada. Usa a câmera já aberta."""
        self._reset(Avaliador(retest=True, frames=self.av.frames))
        if self.source is not None:
            self.timer.start(TIMER_MS)

    def _reset(self, av):
        self.av = av
        self.quality = CaptureQuality()
        self.distance = medidas.DistanceCheck()
        self._last_panel = 0.0
        self._last_colors = None
        self.btn_end.setText("Encerrar reteste" if av.retest else "Encerrar sessão")
        self.chart.update_data([], time.monotonic(), self.selected)
        self._refresh_panel(force=True)
        self.stage.show_banner(None)
        self.stage.show_message(None)
        self.top.set_state("waiting")
        self.top.set_quality("boa", "", "")
        self._update_clock(time.monotonic())
        self._update_actions()

    def stop(self):
        """Fecha a fonte."""
        self.timer.stop()
        if self.source is not None and hasattr(self.source, "stop"):
            self.source.stop()
        self.source = None

    def pause_for_report(self):
        """Encerrou: para relógio e medições, mas mantém a câmera (pode continuar)."""
        self.av.stop_clock(time.monotonic())
        self.timer.stop()

    def resume(self):
        """Voltou do relatório sem salvar: continua a mesma sessão."""
        if not self.av.paused:
            self.av.start_clock(time.monotonic())
        self._update_actions()
        if self.source is not None:
            self.timer.start(TIMER_MS)

    def results(self):
        return self.av.results(time.monotonic(), self.source_name)

    def write_points(self, rel_path):
        """Grava os pontos da mão de todos os quadros (avaliação e reteste)."""
        self.av.write_points(rel_path, getattr(self.source, "settings", {}))

    # ---------------------------------------------------------- construção
    def _build_panel(self):
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(390)
        panel.setStyleSheet(f"#panel {{ background: {SURFACE}; border: 1px solid {BORDER};"
                            " border-radius: 8px; }")
        v = QtWidgets.QVBoxLayout(panel)
        v.setContentsMargins(14, 12, 14, 10)
        v.setSpacing(8)
        v.addWidget(label("Movimentos por dedo  ·  clique para ver os detalhes", 12, MUTED))
        chips = QtWidgets.QHBoxLayout()
        chips.setSpacing(6)
        self.chips = {}
        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        for f in kin.FINGERS:
            chip = FingerChip(f)
            explain(chip, "movimentos", "pct_normal")
            chip.clicked.connect(lambda _c, f=f: self.select_finger(f))
            group.addButton(chip)
            chips.addWidget(chip)
            self.chips[f] = chip
        self.chips[self.selected].setChecked(True)
        v.addLayout(chips)
        self.strong = label("", 12, MUTED)
        self.strong.setTextFormat(QtCore.Qt.RichText)
        self.strong.setWordWrap(True)
        explain(self.strong, "repeticoes_fortes")
        v.addWidget(self.strong)
        line = QtWidgets.QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {BORDER};")
        v.addWidget(line)
        self.detail = DetailPanel()
        v.addWidget(self.detail, stretch=1)
        return panel

    def _build_bottom(self):
        box = QtWidgets.QWidget()
        box.setFixedHeight(156)
        h = QtWidgets.QHBoxLayout(box)
        h.setContentsMargins(10, 0, 10, 10)
        h.setSpacing(10)
        chart_box = QtWidgets.QFrame()
        chart_box.setObjectName("chart")
        chart_box.setStyleSheet(f"#chart {{ background: {SURFACE}; border: 1px solid {BORDER};"
                                " border-radius: 8px; }")
        cv = QtWidgets.QVBoxLayout(chart_box)
        cv.setContentsMargins(12, 6, 8, 4)
        cv.setSpacing(0)
        self.chart_title = label("", 12, MUTED)
        cv.addWidget(self.chart_title)
        self.chart = TamChart()
        explain(self.chart, "tam_ao_vivo")
        cv.addWidget(self.chart)
        h.addWidget(chart_box, stretch=1)

        actions = QtWidgets.QVBoxLayout()
        actions.setSpacing(8)
        self.btn_pause = button("Pausar", "pause", "secondary")
        self.btn_pause.setToolTip("Para de contar repetições e o tempo; a imagem continua ao vivo")
        self.btn_recal = button("Recalibrar", "refresh", "secondary")
        self.btn_recal.setToolTip("Mede de novo o tremor e o lado da mão (mantém os dados da sessão)")
        self.btn_end = button("Encerrar sessão", "stop", "secondary")
        for b in (self.btn_pause, self.btn_recal, self.btn_end):
            b.setFixedSize(390, 40)
            actions.addWidget(b)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_recal.clicked.connect(self.recalibrate)
        self.btn_end.clicked.connect(self.end_session)
        h.addLayout(actions)
        self._update_chart_title()
        return box

    # ------------------------------------------------------------ ações
    def select_finger(self, finger):
        self.selected = finger
        self.chips[finger].setChecked(True)
        self._update_chart_title()
        self._refresh_panel(force=True)

    def _update_chart_title(self):
        self.chart_title.setText(
            f"TAM nos últimos 20 s &nbsp;&nbsp; {swatch(ACCENT)} {kin.NAME[self.selected]}"
            f" &nbsp;&nbsp; {swatch(TamChart.OTHERS)} outros dedos")

    def toggle_expanded(self):
        self.expanded = not self.expanded
        self.panel.setVisible(not self.expanded)
        self.bottom.setVisible(not self.expanded)
        self.toolbar.set_expanded(self.expanded)

    def toggle_pause(self):
        self.av.toggle_pause(time.monotonic())
        self._show_message()
        self._update_actions()

    def recalibrate(self):
        self.av.recalibrate(time.monotonic())
        self._update_actions()

    def _update_actions(self):
        av = self.av
        active = av.phase == "avaliacao" and not av.recalibrating and self.source is not None
        self.btn_pause.setEnabled(active)
        self.btn_recal.setEnabled(active and not av.paused)
        self.btn_end.setEnabled(not av.recalibrating)   # sem dados: serve para sair
        self.btn_pause.setText("Retomar" if av.paused else "Pausar")
        set_button_icon(self.btn_pause, "play" if av.paused else "pause")

    def end_session(self):
        measured = self.av.phase == "avaliacao"
        if self.av.retest:
            if not measured:
                dlg = ConfirmDialog("Sair do reteste?", "O reteste ainda não mediu nada. A avaliação "
                                    "continua no relatório, sem reteste.", "Sair do reteste",
                                    "Continuar aqui", self)
                if dlg.exec_() == QtWidgets.QDialog.Accepted:
                    self.pause_for_report()
                    self.retest_cancelled.emit()
                return
            dlg = ConfirmDialog("Encerrar o reteste?", "O sistema compara o reteste com a avaliação "
                                "para estimar o próprio erro de medida.", "Encerrar reteste", "Cancelar", self)
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                self.pause_for_report()
                self.retest_finished.emit(self.results())
            return
        if not measured:                      # nada medido ainda: só sair
            dlg = ConfirmDialog("Sair da avaliação?", "Ainda não há medições nesta sessão.",
                                "Sair", "Continuar aqui", self)
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                self.stop()
                self.cancelled.emit()
            return
        issues = self._quality_issues()
        if issues:                            # dá para corrigir agora, com o paciente aqui
            dlg = ConfirmDialog("Antes de encerrar", "<br><br>".join(issues),
                                "Encerrar assim", "Continuar avaliando", self)   # Esc = continuar
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                self.pause_for_report()
                self.finished.emit(self.results())
            return
        dlg = ConfirmDialog("Encerrar a sessão?",
                            "As medições param e o relatório é exibido. Lá você pode salvar na "
                            "ficha do paciente, descartar ou voltar e continuar a avaliação.",
                            "Encerrar e ver relatório", "Cancelar", self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.pause_for_report()
            self.finished.emit(self.results())

    # ---------------------------------------------------------------- dicas
    def _tips(self):
        grade = (f"{swatch(POOR)} abaixo de 50%, {swatch(FAIR)} de 50 a 75% e "
                 f"{swatch(GOOD)} acima de 75%")
        return [
            (self.stage, "Câmera e mão 3D",
             "A vista grande mostra a mão em 3D e a miniatura, a câmera. <b>Clique na miniatura</b> "
             "para trocar as duas. No 3D, arraste para girar e use a roda do mouse para aproximar."),
            (list(self.chips.values()), "Um cartão por dedo",
             "Cada cartão mostra quantos movimentos o dedo fez e o % do normal da amplitude "
             f"total (TAM): {grade}. <b>Clique num dedo</b> para ver os detalhes dele."),
            (self.detail, "Detalhes do dedo escolhido",
             "<b>Amplitude</b>: ângulos de cada articulação agora, mínimo, máximo e arco. "
             "<b>Repetições</b>: contagem e qualidade do movimento. <b>Padrão</b>: independência "
             "do dedo e quanto cada articulação contribui. Passe o mouse sobre um valor para ver "
             "a definição."),
            (self.top, "Barra de estado",
             "Mostra a etapa, a qualidade da imagem, se a mão está sendo rastreada e o tempo. "
             "Fica <b>amarela</b> quando a mão sai do quadro ou fica de lado. Antes de medir, o "
             "sistema pede a mão aberta e parada por 2 segundos (calibração)."),
        ]

    def show_tips(self, on_finish=None, finish_text="Fechar"):
        """Dicas guiadas sobre esta tela. Durante a avaliação, pausa enquanto estão abertas."""
        if self._tour is not None:
            return
        if self.expanded:
            self.toggle_expanded()             # as dicas apontam para o painel
        av = self.av
        paused_here = (av.phase == "avaliacao" and self.source is not None
                       and not av.paused and not av.recalibrating)
        if paused_here:
            self.toggle_pause()
        illustrative = self.source is None       # câmera fechada: mão 3D de exemplo
        if illustrative:
            self.hand3d.show_neutral()

        def done():
            self._tour = None
            if illustrative:
                self.hand3d.hide_until_pose()
            if paused_here and self.av.paused:
                self.toggle_pause()
            if on_finish:
                on_finish()

        self._tour = GuidedTour(self, self._tips(), finish_text)
        self._tour.finished.connect(done)

    # ------------------------------------------------------- loop principal
    def tick(self):
        if self.source is None:
            return
        now = time.monotonic()
        self._update_clock(now)
        raw = self.source.latest()
        if raw is None:                       # câmera ainda sem quadro novo
            return
        av = self.av
        measuring = av.phase == "avaliacao" and not av.recalibrating
        self.stage.set_camera_frame(raw.get("frame"))   # a imagem é sempre a mais nova
        self.quality.add(raw)
        self.top.set_quality(*self.quality.evaluate(judge_detection=measuring))

        # o motor usa o instante da CAPTURA do quadro (gravado junto com os pontos):
        # recalcular a avaliação a partir dos pontos dá exatamente o mesmo resultado
        passo = av.step(raw, raw["t"])
        distance = self.distance.update(raw)
        self.stage.show_banner("Vire a palma para a câmera" if passo.state == "vista"
                               else DISTANCE_TEXT.get(distance))
        if passo.pose is not None:
            img = passo.pose["img"] * [passo.pose["aspect"], 1.0]
            self.hand3d.update(geometria.world_to_gl(passo.pose["world"]), av.mirrored, img)
        if passo.calibrar_3d:
            self.hand3d.start_calibration()
        self._show_message()
        if av.paused:
            self.top.set_state("paused")
            return
        if passo.calibrou:
            self._update_actions()
            self._refresh_panel(force=True)
        if av.phase == "avaliacao":
            self.chart.update_data(av.session.history, now, self.selected)
            self._refresh_panel()
        state = passo.state
        if state in ("ok", "segurando"):
            self.top.set_state("tracking")
        elif state == "vista":
            self.top.set_state("bad_view")
        elif av.phase == "avaliacao":
            self.top.set_state("other_hand" if state == "outra_mao" else "lost")
        else:
            self.top.set_state("waiting")

    # -------------------------------------------------------- atualizações
    def _show_message(self):
        """Aviso sobre o palco decidido pelo motor (número = contagem regressiva grande)."""
        if not self.av.message:
            self.stage.show_message(None)
            return
        title, sub = self.av.message
        if isinstance(sub, int):
            sub = f"<span style='font-size:40px; color:{ACCENT}; font-weight:700;'>{sub}</span>"
        self.stage.show_message(title, sub)

    def _update_clock(self, now):
        av = self.av
        title = "Recalibração" if av.recalibrating else PHASE_TITLES[av.phase]
        if av.retest:
            title = f"Reteste ({title.lower()})"
        parts = [title, self.patient.get("identificacao") or "", av.hand_name]
        self.top.title.setText("  ·  ".join(p for p in parts if p))
        secs = av.elapsed(now)
        self.top.clock.setText(f"{secs // 60:02d}:{secs % 60:02d}")

    def _refresh_panel(self, force=False):
        now = time.monotonic()
        if not force and now - self._last_panel < PANEL_REFRESH_S:
            return
        self._last_panel = now
        trackers = self.av.session.trackers
        for f, chip in self.chips.items():
            pct = trackers[f].percent_normal()
            chip.set_data(len(trackers[f].reps), GRADE_COLOR[kin.grade(pct)], pct)
        self.strong.setText(self._strong_text())
        self.detail.show_tracker(trackers[self.selected], self.av.calibrated, self.av.hand_info(now))
        self._color_hand()

    def _strong_text(self):
        """Repetições fortes de cada dedo: verde quando chega à meta; cinza se não se moveu."""
        parts = []
        for f, tr in self.av.session.trackers.items():
            n = tr.strong_reps()
            color = GOOD if n >= kin.EFFORT_TOP_REPS else TEXT if tr.moved() else FAINT
            parts.append(f"<span style='color:{color}'>{kin.SHORT[f]} <b>{n}</b></span>")
        return f"Repetições fortes (meta {kin.EFFORT_TOP_REPS}): " + " · ".join(parts)

    def _quality_issues(self):
        """O que pode deixar a medida ruim, para avisar antes de encerrar ([] = tudo bem)."""
        issues = []
        rel = self.av.reliability(time.monotonic())
        if rel["nivel"] == "baixa":
            issues.append("Confiabilidade baixa: " + "; ".join(rel["motivos"]) + ".")
        short = [kin.NAME[f].lower() for f, tr in self.av.session.trackers.items()
                 if tr.moved() and tr.strong_reps() < kin.EFFORT_TOP_REPS]
        if short:
            issues.append(f"Menos de {kin.EFFORT_TOP_REPS} repetições fortes em: {', '.join(short)}. "
                          "Mais algumas repetições deixam o valor máximo confiável.")
        if issues and self.needs_retest:
            issues.append("O sistema ainda não tem retestes suficientes: faça o reteste no relatório.")
        return issues

    def _color_hand(self):
        """Pele 3D: cada dedo com a cor da sua classificação; o selecionado
        forte, os outros em tom pastel da mesma cor. Cores do palco (VIEW_*):
        o fundo do 3D é escuro nos dois temas."""
        skin = np.array(hand_skin.SKIN_COLOR)
        colors = {}
        for f in kin.FINGERS:
            grade_hex = VIEW_GRADE_COLOR[kin.grade(self.av.session.trackers[f].percent_normal())]
            if f == self.selected:
                c = np.array(rgba(grade_hex or VIEW_ACCENT))
            elif grade_hex:
                # tom pastel (escurecer deixava o vermelho marrom, parecendo pele)
                c = 0.55 * np.array(rgba(grade_hex)) + 0.45 * np.array((0.78, 0.80, 0.82, 1.0))
            else:
                c = skin
            colors[f] = tuple(c)
        key = tuple(sorted((k, tuple(np.round(v, 3))) for k, v in colors.items()))
        if key != self._last_colors:
            self._last_colors = key
            self.hand3d.set_finger_colors(colors)

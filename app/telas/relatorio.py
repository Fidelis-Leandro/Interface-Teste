"""
Relatório da sessão: prévia do documento (igual ao PDF, sem o logotipo, que
vai apenas no PDF), observações do profissional e ações.

Sessão recém-encerrada:  Salvar na ficha · Fazer reteste · Continuar avaliação · Descartar
Sessão já salva:         Gerar PDF · Exportar CSV · Ir para a ficha

O reteste (a mesma medição repetida logo em seguida) fica guardado junto da
avaliação; é o que estima o erro de medida do sistema. Depois dele a avaliação
não pode mais ser continuada (as medições do reteste ocupam a tela de avaliação).
"""

import os
import re

from PyQt5 import QtCore, QtGui, QtWidgets

from app.componentes.cabecalho import ScreenHeader
from app.componentes.dialogos import ConfirmDialog
from app.dados import documento
from app.dados import interpretacao as interp
from app.dados.banco import ROOT
from app.dados.resultados import retest_summary, write_csv
from app.tema import *  # noqa: F401,F403

REPORTS_DIR = os.path.join(ROOT, "relatorios")


def _safe(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text or "paciente").strip("_")[:40]


class ReportScreen(QtWidgets.QWidget):
    continue_evaluation = QtCore.pyqtSignal()
    retest_requested = QtCore.pyqtSignal()
    leave = QtCore.pyqtSignal(int)            # volta para a ficha do paciente (id)
    session_saved = QtCore.pyqtSignal(int)    # id da sessão salva

    def __init__(self, db, get_config):
        super().__init__()
        self.db, self.get_config = db, get_config
        self.patient, self.results, self.history = {}, None, []
        self.sid = None                       # None = sessão ainda não salva

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = ScreenHeader("Relatório da sessão")
        v.addWidget(self.header)

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(14)
        # prévia: folha branca, exatamente o documento do PDF
        self.preview = QtWidgets.QTextBrowser()
        self.preview.setOpenLinks(False)
        # o documento cabe na largura (tabelas a 100%); o arredondamento sobrava 1 px
        self.preview.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.preview.setStyleSheet("QTextBrowser { background: #ffffff; color: #1d2733;"
                                   f" border: 1px solid {BORDER}; border-radius: 6px; padding: 18px 28px; }}"
                                   + scrollbar_css("#c5cdd5", "#9aa5b1", track="#ffffff"))
        body.addWidget(self.preview, stretch=1)

        side = card("reportSide")
        side.setFixedWidth(340)
        sv = QtWidgets.QVBoxLayout(side)
        sv.setContentsMargins(16, 14, 16, 14)
        sv.setSpacing(10)
        sv.addWidget(label("Observações do profissional", 14, TEXT, bold=True))
        hint = label("Entram no relatório e ficam salvas com a avaliação.", 12, MUTED)
        hint.setWordWrap(True)
        sv.addWidget(hint)
        self.notes = QtWidgets.QPlainTextEdit()
        self.notes.setStyleSheet(INPUT_CSS)
        self.notes.setPlaceholderText("Ex.: paciente relatou dor leve no fim da sessão.")
        self.notes.textChanged.connect(self._schedule_refresh)
        sv.addWidget(self.notes, stretch=1)

        self.status = label("", 12, MUTED)
        self.status.setWordWrap(True)
        sv.addWidget(self.status)
        # ações da sessão recém-encerrada
        self.b_save = button("Salvar na ficha", "check", "primary")
        self.b_retest = button("Fazer reteste", "refresh", "secondary")
        self.b_retest.setToolTip("O paciente reposiciona a mão e repete o movimento agora. Comparando as\n"
                                 "duas medições, o sistema estima o próprio erro de medida e passa a dizer\n"
                                 "se uma mudança entre avaliações é real ou está dentro do erro.")
        self.b_continue = button("Continuar avaliação", "play", "secondary")
        self.b_discard = button("Descartar sessão", "trash", "secondary")
        # ações da sessão salva
        self.b_pdf = button("Gerar PDF", "file", "primary")
        self.b_csv = button("Exportar CSV", "download", "secondary")
        self.b_open_pdf = button("Abrir o PDF gerado", "file", "secondary")
        self.b_back = button("Ir para a ficha", "back", "secondary")
        for b in (self.b_save, self.b_retest, self.b_continue, self.b_discard, self.b_pdf, self.b_csv,
                  self.b_open_pdf, self.b_back):
            b.setMinimumHeight(40)
            sv.addWidget(b)
        self.b_save.clicked.connect(self.save_session)
        self.b_retest.clicked.connect(self._request_retest)
        self.b_continue.clicked.connect(self.continue_evaluation.emit)
        self.b_discard.clicked.connect(self.discard)
        self.b_pdf.clicked.connect(self.export_pdf)
        self.b_csv.clicked.connect(self.export_csv)
        self.b_open_pdf.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(self.last_pdf)))
        self.b_back.clicked.connect(lambda: self.leave.emit(self.patient.get("id")))
        body.addWidget(side)
        v.addLayout(body, stretch=1)

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh_preview)
        self.last_pdf = None

    # ---------------------------------------------------------------- abrir
    def show_new(self, patient, results):
        """Sessão que acabou de ser encerrada (ainda não salva)."""
        self.patient, self.results, self.sid = patient, results, None
        self.retest_started = False
        self.history = [(s["inicio"], s["resultados"]) for s in self.db.sessoes(patient["id"])]
        self.notes.blockSignals(True)
        self.notes.setPlainText("")
        self.notes.blockSignals(False)
        self._set_mode(saved=False)
        self.status.setText("Revise o relatório. Salve na ficha para guardar a avaliação.")
        self.refresh_preview()

    def show_saved(self, sid):
        s = self.db.sessao(sid)
        self.sid, self.results = sid, s["resultados"]
        self.patient = self.db.paciente(s["paciente_id"]) or {}
        self.history = [(x["inicio"], x["resultados"]) for x in self.db.sessoes(s["paciente_id"])
                        if x["inicio"] < s["inicio"]]
        self.notes.blockSignals(True)
        self.notes.setPlainText(s.get("observacoes") or "")
        self.notes.blockSignals(False)
        self._set_mode(saved=True)
        self.status.setText(self._retest_text())
        self.refresh_preview()

    def _set_mode(self, saved):
        for b in (self.b_save, self.b_discard):
            b.setVisible(not saved)
        started = getattr(self, "retest_started", False)
        self.b_retest.setVisible(not saved and not started)
        self.b_continue.setVisible(not saved and not started)
        for b in (self.b_pdf, self.b_csv, self.b_back):
            b.setVisible(saved)
        self.b_open_pdf.setVisible(False)
        self.header.title.setText("Relatório da sessão" if saved else "Relatório da sessão (não salva)")
        self.header.subtitle.setText(f"{self.patient.get('identificacao', '')}  ·  "
                                     f"{fmt_datetime(self.results['inicio'])}")

    # --------------------------------------------------------------- prévia
    def _schedule_refresh(self):
        self._refresh_timer.start(400)       # atualiza a prévia 0,4 s depois de parar de digitar

    def _document(self, for_print=False):
        """for_print=True: documento do PDF (com logotipo); False: prévia na tela (sem)."""
        density = documento.PRINT_DENSITY if for_print else documento.screen_density(self.preview)
        return documento.build_document(self.patient, self.results, self.notes.toPlainText(),
                                        self.history, self.get_config(), density=density,
                                        with_logo=for_print)

    def refresh_preview(self):
        scroll = self.preview.verticalScrollBar().value()
        self.preview.setDocument(self._document())
        self.preview.verticalScrollBar().setValue(scroll)

    # -------------------------------------------------------------- reteste
    def _request_retest(self):
        self.retest_started = True
        self._set_mode(saved=False)
        self.retest_requested.emit()

    def add_retest(self, retest_results):
        """Reteste concluído: fica guardado junto da avaliação (não muda o relatório)."""
        self.results["reteste"] = retest_summary(retest_results)
        self.status.setText(self._retest_text() + " Salve na ficha para guardar as duas medições.")

    def retest_cancelled(self):
        self.status.setText("Reteste cancelado. Salve na ficha ou descarte a avaliação.")

    def _retest_text(self):
        diff = interp.retest_difference(self.results)
        if diff is None:
            return ""
        return (f"Reteste feito: diferença média de {diff[0]:.0f}° por articulação entre as duas "
                f"medições ({diff[1]} comparações).")

    # ---------------------------------------------------------------- ações
    def save_session(self):
        self.sid = self.db.salvar_sessao(self.patient["id"], self.results, self.notes.toPlainText())
        self._set_mode(saved=True)
        self.status.setText("Avaliação salva na ficha do paciente.")
        self.session_saved.emit(self.sid)

    def discard(self):
        dlg = ConfirmDialog("Descartar esta sessão?",
                            "As medições desta avaliação não serão salvas.", "Descartar", "Cancelar", self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.leave.emit(self.patient.get("id"))

    def _save_notes(self):
        if self.sid is not None:
            self.db.atualizar_observacoes(self.sid, self.notes.toPlainText())

    def _default_name(self, ext):
        os.makedirs(REPORTS_DIR, exist_ok=True)
        stamp = self.results["inicio"][:16].replace("-", "").replace(":", "").replace("T", "_")
        return os.path.join(REPORTS_DIR, f"relatorio_{_safe(self.patient.get('identificacao'))}_{stamp}.{ext}")

    def export_pdf(self):
        self._save_notes()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Salvar relatório em PDF",
                                                        self._default_name("pdf"), "PDF (*.pdf)")
        if not path:
            return
        documento.save_pdf(self._document(for_print=True), path)
        self.last_pdf = path
        self.b_open_pdf.setVisible(True)
        self.status.setText(f"PDF salvo em {path}")

    def export_csv(self):
        self._save_notes()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar dados em CSV",
                                                        self._default_name("csv"), "CSV (*.csv)")
        if path:
            write_csv(path, self.results, self.patient)
            self.status.setText(f"CSV salvo em {path}")

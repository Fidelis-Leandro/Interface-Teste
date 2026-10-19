"""
Janela principal: uma tela por vez (QStackedWidget) e a navegação entre elas.

  Pacientes -> Ficha do paciente -> Avaliação -> Relatório -> Ficha
       \\-> Configurações        (Ajuda: a partir de Pacientes e da Ficha)

Primeiro uso: na primeira avaliação, as dicas da tela aparecem antes de a câmera abrir.
"""

import datetime
import os
import sys

from PyQt5 import QtCore, QtGui, QtWidgets

from app.componentes.dialogos import ConfirmDialog
from app.dados import config as cfgmod
from app.dados import interpretacao as interp
from app.dados.banco import DB_PATH, ROOT, Banco
from app.dados.exportacao import export_research
from app.tema import APP_CSS
from app.telas.ajuda import HelpScreen
from app.telas.avaliacao import EvaluationScreen
from app.telas.configuracoes import SettingsScreen
from app.telas.ficha import RecordScreen
from app.telas.pacientes import PatientsScreen
from app.telas.relatorio import ReportScreen


class AppWindow(QtWidgets.QMainWindow):
    def __init__(self, source_factory, db_path=DB_PATH):
        super().__init__()
        self.setWindowTitle("Avaliação da mão")
        self.resize(1366, 768)
        self.setStyleSheet(APP_CSS)
        self.db = Banco(db_path)
        self.cfg = cfgmod.load()
        get_config = lambda: self.cfg

        self.stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stack)
        self.patients = PatientsScreen(self.db, get_config)
        self.record = RecordScreen(self.db, get_config)
        self.evaluation = EvaluationScreen(source_factory)
        self.report = ReportScreen(self.db, get_config)
        self.settings = SettingsScreen(self.db)
        self.help = HelpScreen()
        for screen in (self.patients, self.record, self.evaluation, self.report, self.settings, self.help):
            self.stack.addWidget(screen)
        self._help_return = self.patients

        # navegação
        self.patients.open_patient.connect(self.show_record)
        self.patients.open_settings.connect(self.show_settings)
        self.patients.open_help.connect(self.show_help)
        self.patients.export_data.connect(self.export_data)
        self.record.open_help.connect(self.show_help)
        self.help.back.connect(self._leave_help)
        self.record.back.connect(self.show_patients)
        self.record.new_evaluation.connect(self.start_evaluation)
        self.record.open_session.connect(self.show_saved_report)
        self.evaluation.finished.connect(self.show_new_report)
        self.evaluation.cancelled.connect(lambda: self.show_record(self.record.pid))
        self.report.continue_evaluation.connect(self.continue_evaluation)
        self.report.retest_requested.connect(self.start_retest)
        self.evaluation.retest_finished.connect(self._retest_finished)
        self.evaluation.retest_cancelled.connect(self._retest_cancelled)
        self.report.session_saved.connect(self._session_saved)
        self.report.leave.connect(self.leave_report)
        self.settings.back.connect(self.show_patients)
        self.settings.saved.connect(self._config_saved)
        self.settings.restart_requested.connect(self.restart)
        self.show_patients()

    # ------------------------------------------------------------- telas
    def show_patients(self):
        self.patients.refresh()
        self.stack.setCurrentWidget(self.patients)

    def show_record(self, pid):
        if pid is None or self.db.paciente(pid) is None:
            self.show_patients()
            return
        self.record.show_patient(pid)
        self.stack.setCurrentWidget(self.record)

    def show_settings(self):
        self.settings.load()
        self.stack.setCurrentWidget(self.settings)

    def show_help(self):
        """Ajuda: "Voltar" retorna à tela de onde veio."""
        self._help_return = self.stack.currentWidget()
        self.help.show_top()
        self.stack.setCurrentWidget(self.help)

    def _leave_help(self):
        if self._help_return is self.patients:
            self.show_patients()
        elif self._help_return is self.record:
            self.show_record(self.record.pid)
        else:
            self.stack.setCurrentWidget(self._help_return)

    def start_evaluation(self, pid):
        patient = self.db.paciente(pid)
        error = interp.measurement_error([s["resultados"] for s in self.db.todas_sessoes()])
        self.evaluation.needs_retest = error["tam_pp"]["mdc"] is None   # lembrete na conferência final
        self.stack.setCurrentWidget(self.evaluation)
        if self.cfg.get("dicas_vistas"):
            self.evaluation.start(patient)
            return

        def begin():                          # primeiro uso: dicas antes de abrir a câmera
            self.cfg["dicas_vistas"] = True
            cfgmod.save(self.cfg)
            self.evaluation.start(patient)

        self.evaluation.prepare(patient)
        self.evaluation.show_tips(on_finish=begin, finish_text="Começar a avaliação")

    def show_new_report(self, results):
        self.report.show_new(self.evaluation.patient, results)
        self.stack.setCurrentWidget(self.report)

    def show_saved_report(self, sid):
        self.report.show_saved(sid)
        self.stack.setCurrentWidget(self.report)

    def continue_evaluation(self):
        self.stack.setCurrentWidget(self.evaluation)
        self.evaluation.resume()

    def start_retest(self):
        self.stack.setCurrentWidget(self.evaluation)
        self.evaluation.start_retest()

    def _retest_finished(self, results):
        self.report.add_retest(results)
        self.stack.setCurrentWidget(self.report)

    def _retest_cancelled(self):
        self.report.retest_cancelled()
        self.stack.setCurrentWidget(self.report)

    def _session_saved(self, _sid):
        """Salvou na ficha: grava os pontos da mão (só agora, para descartar não deixar
        arquivo) e fecha a câmera."""
        points = self.report.results.get("pontos")
        if points:
            self.evaluation.write_points(points)
        self.evaluation.stop()

    def leave_report(self, pid):
        self.evaluation.stop()                # descartou, ou já salvou: fecha a câmera
        self.show_record(pid)

    def _config_saved(self, cfg):
        self.cfg = cfg

    def export_data(self, folder=None):
        """Exportação para pesquisa numa pasta nova (escolhida pelo usuário)."""
        if folder is None:
            base = QtWidgets.QFileDialog.getExistingDirectory(self, "Pasta para a exportação",
                                                              os.path.join(ROOT, "relatorios"))
            if not base:
                return None
            folder = os.path.join(base, datetime.datetime.now().strftime("exportacao_%Y%m%d_%H%M"))
        path, rows = export_research(self.db, folder)
        dlg = ConfirmDialog("Dados exportados",
                            f"{rows} linhas (uma por avaliação e dedo) em {path}, com o dicionário de "
                            "dados ao lado.", "Abrir a pasta", "Fechar", self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))
        return path

    def restart(self):
        """Abre o programa de novo, com os mesmos argumentos (o tema é lido ao abrir)."""
        started = QtCore.QProcess.startDetached(sys.executable, sys.argv)
        if isinstance(started, tuple):        # algumas versões do PyQt devolvem (ok, pid)
            started = started[0]
        if started:
            self.close()

    def closeEvent(self, ev):
        self.evaluation.stop()                # libera a câmera e salva a gravação, se houver
        super().closeEvent(ev)

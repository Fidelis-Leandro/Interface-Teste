"""Tela inicial: lista de pacientes (busca, filtro por situação, tendência, novo,
abrir ficha) e o formulário de cadastro."""

import datetime

from PyQt5 import QtCore, QtGui, QtWidgets

import kinematics as kin
from icons import icon
from app.componentes.cabecalho import ScreenHeader
from app.componentes.dialogos import DIALOG_CSS, ConfirmDialog
from app.componentes.pecas import SegmentedTabs
from app.dados import interpretacao as interp
from app.dados.resultados import mean_pct
from app.glossario import explain_columns
from app.tema import *  # noqa: F401,F403

NOT_INFORMED = "não informada"
HANDS_DOMINANT = [NOT_INFORMED, "Direita", "Esquerda", "Ambidestro"]
HANDS_EVALUATED = [NOT_INFORMED, "Direita", "Esquerda", "Ambas"]
SITUATIONS = [("tratamento", "Em tratamento"), ("alta", "Alta")]
FICTITIOUS_NOTE = "Versão de teste: cadastre apenas dados fictícios."
TREND_COLOR = {"melhora": GOOD, "piora": POOR, "plato": FAIR, "estavel": MUTED}


def situation_text(p):
    """"Em tratamento" ou "Alta em dd/mm/aaaa"."""
    if p.get("situacao") != "alta":
        return "Em tratamento"
    return "Alta" + (f" em {fmt_date(p['data_alta'])}" if p.get("data_alta") else "")




class _Item(QtWidgets.QTableWidgetItem):
    """Célula que ordena pelo valor (número ou data), não pelo texto:
    assim "79%" vem antes de "102%" e "6 anos" antes de "55 anos"."""

    def __init__(self, text, key):
        super().__init__(text)
        self.key = key

    def __lt__(self, other):
        return self.key < other.key


def _ago(iso):
    days = (datetime.date.today() - datetime.date.fromisoformat(iso[:10])).days
    return "hoje" if days <= 0 else "ontem" if days == 1 else f"há {days} dias"


class _DateField(QtWidgets.QDateEdit):
    """Data opcional: o primeiro dia possível vale como "não informada"."""

    EMPTY = QtCore.QDate(1900, 1, 1)

    def __init__(self):
        super().__init__()
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd/MM/yyyy")
        self.setMinimumDate(self.EMPTY)
        self.setSpecialValueText("não informada")
        self.setDate(self.EMPTY)

    def iso(self):
        d = self.date()
        return None if d == self.EMPTY else d.toString("yyyy-MM-dd")

    def set_iso(self, iso):
        if iso:
            self.setDate(QtCore.QDate.fromString(iso[:10], "yyyy-MM-dd"))
        else:
            self.setDate(self.EMPTY)


class PatientDialog(QtWidgets.QDialog):
    """Cadastro / edição. result_action = "salvar" | "excluir"."""

    def __init__(self, data=None, default_professional="", parent=None):
        super().__init__(parent)
        editing = bool(data)
        self.result_action = None
        self.setWindowTitle("Editar paciente" if editing else "Novo paciente")
        self.setStyleSheet(DIALOG_CSS + INPUT_CSS)
        self.setMinimumWidth(520)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(label("Editar paciente" if editing else "Novo paciente", 18, TEXT, bold=True))
        note = label(FICTITIOUS_NOTE, 13, FAIR)
        v.addWidget(note)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.ident = QtWidgets.QLineEdit()
        self.ident.setPlaceholderText("Código ou nome fictício (obrigatório)")
        self.birth = _DateField()
        self.dominant = QtWidgets.QComboBox()
        self.dominant.addItems(HANDS_DOMINANT)
        self.evaluated = QtWidgets.QComboBox()
        self.evaluated.addItems(HANDS_EVALUATED)
        self.condition = QtWidgets.QLineEdit()
        self.condition.setPlaceholderText("Ex.: pós-operatório de tendão flexor")
        self.injury = _DateField()
        self.professional = QtWidgets.QLineEdit()
        self.situation = QtWidgets.QComboBox()
        self.situation.addItems([text for _, text in SITUATIONS])
        self.discharge = _DateField()
        self.notes = QtWidgets.QPlainTextEdit()
        self.notes.setFixedHeight(80)
        rows = [("Identificação", self.ident), ("Data de nascimento", self.birth),
                ("Mão dominante", self.dominant), ("Mão avaliada", self.evaluated),
                ("Condição / diagnóstico", self.condition),
                ("Data da lesão ou cirurgia", self.injury),
                ("Profissional responsável", self.professional), ("Situação", self.situation),
                ("Data da alta", self.discharge), ("Observações", self.notes)]
        for text, w in rows:
            form.addRow(label(text, 13, MUTED), w)
        v.addLayout(form)
        self.error = label("", 13, POOR)
        v.addWidget(self.error)

        buttons = QtWidgets.QHBoxLayout()
        if editing:
            b_del = button("Excluir paciente", "trash", "secondary")
            b_del.clicked.connect(self._delete)
            buttons.addWidget(b_del)
        buttons.addStretch()
        b_cancel = button("Cancelar", None, "secondary")
        b_save = button("Salvar", "check", "primary")
        b_cancel.clicked.connect(self.reject)
        b_save.clicked.connect(self._save)
        buttons.addWidget(b_cancel)
        buttons.addWidget(b_save)
        v.addLayout(buttons)

        data = data or {}
        self.ident.setText(data.get("identificacao") or "")
        self.birth.set_iso(data.get("nascimento"))
        self.dominant.setCurrentText(data.get("mao_dominante") or NOT_INFORMED)
        self.evaluated.setCurrentText(data.get("mao_avaliada") or NOT_INFORMED)
        self.condition.setText(data.get("condicao") or "")
        self.injury.set_iso(data.get("data_lesao"))
        self.professional.setText(data.get("profissional") or default_professional or "")
        self.situation.setCurrentIndex(1 if data.get("situacao") == "alta" else 0)
        self.discharge.set_iso(data.get("data_alta"))
        self.notes.setPlainText(data.get("observacoes") or "")
        self.situation.currentIndexChanged.connect(self._sync_discharge)
        self._sync_discharge()

    def _sync_discharge(self):
        """Data da alta só vale com a situação "Alta" (sugere hoje ao marcar)."""
        discharged = self.situation.currentIndex() == 1
        self.discharge.setEnabled(discharged)
        if discharged and self.discharge.iso() is None:
            self.discharge.setDate(QtCore.QDate.currentDate())

    def data(self):
        hand = lambda combo: "" if combo.currentText() == NOT_INFORMED else combo.currentText()
        discharged = self.situation.currentIndex() == 1
        return {"identificacao": self.ident.text().strip(), "nascimento": self.birth.iso(),
                "mao_dominante": hand(self.dominant), "mao_avaliada": hand(self.evaluated),
                "condicao": self.condition.text().strip(), "data_lesao": self.injury.iso(),
                "profissional": self.professional.text().strip(),
                "situacao": "alta" if discharged else None,
                "data_alta": self.discharge.iso() if discharged else None,
                "observacoes": self.notes.toPlainText().strip()}

    def _save(self):
        if not self.ident.text().strip():
            self.error.setText("Preencha a identificação (código ou nome fictício).")
            self.ident.setFocus()
            return
        self.result_action = "salvar"
        self.accept()

    def _delete(self):
        dlg = ConfirmDialog("Excluir este paciente?",
                            "O cadastro, todas as avaliações e as gravações ligadas a elas serão "
                            "apagados. Isso não pode ser desfeito.", "Excluir tudo", "Cancelar", self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.result_action = "excluir"
            self.accept()


class PatientsScreen(QtWidgets.QWidget):
    open_patient = QtCore.pyqtSignal(int)
    open_settings = QtCore.pyqtSignal()
    open_help = QtCore.pyqtSignal()
    export_data = QtCore.pyqtSignal()

    COLUMNS = ["Identificação", "Idade", "Mão avaliada", "Condição", "Situação", "Avaliações",
               "% normal", "Tendência", "Última avaliação"]
    FILTERS = [("tratamento", "Em tratamento"), ("alta", "Alta"), (None, "Todos")]

    def __init__(self, db, get_config):
        super().__init__()
        self.db, self.get_config = db, get_config
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = ScreenHeader("Pacientes")
        self.header.subtitle.setText(FICTITIOUS_NOTE)
        self.header.subtitle.setStyleSheet(f"color: {FAIR}; font-size: 13px; background: transparent;")
        b_help = self.header.add_action(button("Ajuda", "help", "quiet"))
        b_help.setToolTip("Como fazer uma avaliação e o que significa cada medida")
        b_help.clicked.connect(self.open_help.emit)
        b_export = self.header.add_action(button("Exportar dados", "download", "quiet"))
        b_export.setToolTip("Todas as avaliações de todos os pacientes em CSV, com dicionário de dados,\n"
                            "para análise em planilha, R ou Python")
        b_export.clicked.connect(self.export_data.emit)
        b_settings = self.header.add_action(button("Configurações", "settings", "quiet"))
        b_settings.clicked.connect(self.open_settings.emit)
        v.addWidget(self.header)

        body = QtWidgets.QVBoxLayout()
        body.setContentsMargins(24, 18, 24, 18)
        body.setSpacing(12)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)
        self.search = QtWidgets.QLineEdit()
        self.search.setStyleSheet(INPUT_CSS)
        self.search.setPlaceholderText("Buscar por identificação ou condição")
        self.search.addAction(icon("search", MUTED), QtWidgets.QLineEdit.LeadingPosition)
        self.search.setFixedWidth(420)
        self.search.textChanged.connect(self.refresh)
        row.addWidget(self.search)
        self.situation = "tratamento"           # filtro: começa mostrando quem está em tratamento
        self.filter = SegmentedTabs([(text, "") for _, text in self.FILTERS])
        self.filter.setFixedWidth(360)
        self.filter.changed.connect(self._set_filter)
        row.addWidget(self.filter)
        row.addStretch()
        b_new = button("Novo paciente", "plus", "primary")
        b_new.clicked.connect(self.new_patient)
        row.addWidget(b_new)
        body.addLayout(row)

        self.table = table(self.COLUMNS, stretch=(3,), selectable=True)     # "Condição" ocupa a sobra
        explain_columns(self.table, {4: "situacao", 6: "pct_normal", 7: "tendencia", 8: "ultima_avaliacao"})
        self.table.setToolTip("% normal = TAM ativo médio dos 5 dedos na última avaliação.\n"
                              "Tendência = última avaliação comparada à anterior, considerando o erro\n"
                              "de medida dos retestes (sem retestes, mostra só a diferença).")
        self.table.setSortingEnabled(True)               # clique no título da coluna ordena
        self.table.horizontalHeader().setSortIndicator(8, QtCore.Qt.DescendingOrder)   # mais recentes primeiro
        self.table.cellDoubleClicked.connect(lambda r, _c: self._open_row(r))
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        body.addWidget(self.table, stretch=1)
        self.empty = label("", 14, MUTED)
        self.empty.setAlignment(QtCore.Qt.AlignCenter)
        body.addWidget(self.empty, stretch=1)

        foot = QtWidgets.QHBoxLayout()
        foot.addWidget(label("Dois cliques numa linha abrem a ficha.", 12, MUTED))
        foot.addStretch()
        self.b_open = button("Abrir ficha", "file", "secondary")
        self.b_open.clicked.connect(lambda: self._open_row(self.table.currentRow()))
        foot.addWidget(self.b_open)
        body.addLayout(foot)
        v.addLayout(body, stretch=1)
        self.refresh()

    def _set_filter(self, index):
        self.situation = self.FILTERS[index][0]
        self.refresh()

    def refresh(self):
        situation = self.situation
        patients = self.db.pacientes(self.search.text(), situation)
        everything = self.db.todas_sessoes()
        error = interp.measurement_error([s["resultados"] for s in everything])
        by_patient = {}
        for s in everything:
            by_patient.setdefault(s["paciente_id"], []).append(s)
        self.table.setSortingEnabled(False)              # preencher com a ordenação ligada embaralha as linhas
        self.table.setRowCount(len(patients))
        for r, p in enumerate(patients):
            sessions = by_patient.get(p["id"], [])
            age = age_from(p.get("nascimento"))
            pct = mean_pct(sessions[-1]["resultados"]) if sessions else None
            trend, kind = interp.patient_trend(sessions, error)
            last = p.get("ultima_sessao")
            overdue = (bool(last) and p.get("situacao") != "alta"
                       and (datetime.date.today() - datetime.date.fromisoformat(last[:10])).days > interp.OVERDUE_DAYS)
            # (texto, valor usado para ordenar)
            values = [(p["identificacao"], p["identificacao"].lower()),
                      ("--" if age is None else f"{age} anos", -1 if age is None else age),
                      (p.get("mao_avaliada") or "--", p.get("mao_avaliada") or ""),
                      (p.get("condicao") or "--", (p.get("condicao") or "").lower()),
                      (situation_text(p), situation_text(p)),
                      (str(p["n_sessoes"]), p["n_sessoes"]),
                      (fmt_pct(pct), -1 if pct is None else pct),
                      (trend, kind or ""),
                      ("--" if not last else f"{fmt_date(last)}  ·  {_ago(last)}", last or "")]
            for c, (text, key) in enumerate(values):
                item = _Item(text, key)
                if c == 0:
                    item.setData(QtCore.Qt.UserRole, p["id"])   # a linha muda ao ordenar; o id vai junto
                if c in (1, 5, 6, 7):
                    item.setTextAlignment(QtCore.Qt.AlignCenter)
                if c == 6 and pct is not None:
                    item.setForeground(QtGui.QBrush(qcolor(GRADE_COLOR[kin.grade(pct)])))
                if c == 7 and kind in TREND_COLOR:
                    item.setForeground(QtGui.QBrush(qcolor(TREND_COLOR[kind])))
                if c == 8 and overdue:
                    item.setForeground(QtGui.QBrush(qcolor(FAIR)))
                    item.setToolTip(f"Em tratamento e sem avaliação há mais de {interp.OVERDUE_DAYS // 7} semanas")
                self.table.setItem(r, c, item)
            self.table.setRowHeight(r, 40)
        self.table.setSortingEnabled(True)
        self.table.setVisible(bool(patients))
        self.empty.setVisible(not patients)
        if self.search.text().strip():
            self.empty.setText("Nenhum paciente encontrado para esta busca.")
        elif situation == "alta":
            self.empty.setText("Nenhum paciente com alta.")
        elif self.db.pacientes(""):
            self.empty.setText("Nenhum paciente em tratamento. Veja a aba Alta ou Todos.")
        else:
            self.empty.setText("Nenhum paciente cadastrado. Clique em Novo paciente para começar.")
        self._sync_buttons()

    def _sync_buttons(self):
        self.b_open.setEnabled(self.table.item(self.table.currentRow(), 0) is not None)

    def _open_row(self, row):
        item = self.table.item(row, 0)
        if item is not None:
            self.open_patient.emit(item.data(QtCore.Qt.UserRole))

    def new_patient(self):
        dlg = PatientDialog(None, self.get_config().get("profissional_padrao", ""), self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted and dlg.result_action == "salvar":
            pid = self.db.salvar_paciente(dlg.data())
            self.refresh()
            self.open_patient.emit(pid)

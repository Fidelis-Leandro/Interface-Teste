"""
Banco local (SQLite, um arquivo só) com pacientes e sessões.

Versão de teste: use apenas dados fictícios. Dado de saúde é dado pessoal
sensível (LGPD, art. 11); antes de qualquer uso com pacientes reais este banco
precisa de controle de acesso, criptografia e consentimento.
"""

import datetime
import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "dados_locais")
DB_PATH = os.path.join(DATA_DIR, "avaliacoes.sqlite")

FIELDS = ["identificacao", "nascimento", "mao_dominante", "mao_avaliada", "condicao",
          "data_lesao", "profissional", "observacoes", "situacao", "data_alta"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS pacientes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    identificacao TEXT NOT NULL,          -- código ou nome FICTÍCIO
    nascimento    TEXT,                   -- aaaa-mm-dd
    mao_dominante TEXT,
    mao_avaliada  TEXT,
    condicao      TEXT,                   -- condição / diagnóstico
    data_lesao    TEXT,                   -- data da lesão ou cirurgia, aaaa-mm-dd
    profissional  TEXT,
    observacoes   TEXT,
    situacao      TEXT,                   -- "alta" ou vazio (= em tratamento)
    data_alta     TEXT,                   -- aaaa-mm-dd
    criado_em     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessoes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id  INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
    inicio       TEXT NOT NULL,           -- aaaa-mm-ddThh:mm:ss
    duracao_s    INTEGER,
    mao          TEXT,                    -- "Right" / "Left" (mão real detectada)
    resultados   TEXT NOT NULL,           -- JSON (app/dados/resultados.py)
    observacoes  TEXT,                    -- texto do profissional, vai para o relatório
    criado_em    TEXT NOT NULL
);
"""


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


class Banco:
    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(SCHEMA)
        # bancos criados antes da situação do paciente: acrescenta as colunas (nada se perde)
        columns = {r["name"] for r in self.con.execute("PRAGMA table_info(pacientes)")}
        for col in ("situacao", "data_alta"):
            if col not in columns:
                self.con.execute(f"ALTER TABLE pacientes ADD COLUMN {col} TEXT")
        self.con.commit()

    # ------------------------------------------------------------ pacientes
    def pacientes(self, busca="", situacao=None):
        """Lista com nº de sessões e data da última, mais recentes primeiro.
        situacao = "tratamento", "alta" ou None (todos)."""
        like = f"%{busca.strip()}%"
        only = {"alta": "AND p.situacao = 'alta'",
                "tratamento": "AND IFNULL(p.situacao, '') <> 'alta'"}.get(situacao, "")
        rows = self.con.execute(
            f"""SELECT p.*, COUNT(s.id) AS n_sessoes, MAX(s.inicio) AS ultima_sessao
                FROM pacientes p LEFT JOIN sessoes s ON s.paciente_id = p.id
                WHERE (p.identificacao LIKE ? OR IFNULL(p.condicao, '') LIKE ?) {only}
                GROUP BY p.id
                ORDER BY (ultima_sessao IS NULL), ultima_sessao DESC, p.identificacao""",
            (like, like))
        return [dict(r) for r in rows]

    def paciente(self, pid):
        row = self.con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        return dict(row) if row else None

    def salvar_paciente(self, dados, pid=None):
        values = [dados.get(f) or None for f in FIELDS]
        if pid is None:
            cur = self.con.execute(
                f"INSERT INTO pacientes ({', '.join(FIELDS)}, criado_em) "
                f"VALUES ({', '.join('?' * len(FIELDS))}, ?)", values + [_now()])
            pid = cur.lastrowid
        else:
            self.con.execute(f"UPDATE pacientes SET {', '.join(f + ' = ?' for f in FIELDS)} WHERE id = ?",
                             values + [pid])
        self.con.commit()
        return pid

    def excluir_paciente(self, pid):
        """Apaga o paciente, as sessões e as gravações ligadas a elas."""
        for s in self.sessoes(pid):
            self._apagar_arquivos(s["resultados"])
        self.con.execute("DELETE FROM pacientes WHERE id = ?", (pid,))
        self.con.commit()

    @staticmethod
    def _apagar_arquivos(resultados):
        """Arquivo de pontos da mão da sessão, se houver."""
        pts = resultados.get("pontos")
        if pts and os.path.exists(os.path.join(ROOT, pts)):
            os.remove(os.path.join(ROOT, pts))

    # -------------------------------------------------------------- sessões
    def _sessao(self, row):
        d = dict(row)
        d["resultados"] = json.loads(d["resultados"])
        return d

    def sessoes(self, pid):
        """Sessões do paciente, da mais antiga para a mais recente."""
        rows = self.con.execute("SELECT * FROM sessoes WHERE paciente_id = ? ORDER BY inicio", (pid,))
        return [self._sessao(r) for r in rows]

    def sessao(self, sid):
        row = self.con.execute("SELECT * FROM sessoes WHERE id = ?", (sid,)).fetchone()
        return self._sessao(row) if row else None

    def todas_sessoes(self):
        """Todas as sessões de todos os pacientes (erro de medida, exportação)."""
        rows = self.con.execute("SELECT * FROM sessoes ORDER BY paciente_id, inicio")
        return [self._sessao(r) for r in rows]

    def salvar_sessao(self, pid, resultados, observacoes=""):
        cur = self.con.execute(
            "INSERT INTO sessoes (paciente_id, inicio, duracao_s, mao, resultados, observacoes, criado_em)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pid, resultados["inicio"], resultados["duracao_s"], resultados["mao"],
             json.dumps(resultados, ensure_ascii=False), observacoes, _now()))
        self.con.commit()
        return cur.lastrowid

    def atualizar_resultados(self, sid, resultados):
        """Troca os resultados de uma sessão (recálculo a partir dos pontos gravados)."""
        self.con.execute("UPDATE sessoes SET resultados = ?, mao = ? WHERE id = ?",
                         (json.dumps(resultados, ensure_ascii=False), resultados["mao"], sid))
        self.con.commit()

    def atualizar_observacoes(self, sid, texto):
        self.con.execute("UPDATE sessoes SET observacoes = ? WHERE id = ?", (texto, sid))
        self.con.commit()

    def excluir_sessao(self, sid):
        s = self.sessao(sid)
        if s:
            self._apagar_arquivos(s["resultados"])
        self.con.execute("DELETE FROM sessoes WHERE id = ?", (sid,))
        self.con.commit()

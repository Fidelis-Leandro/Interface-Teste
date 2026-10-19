"""
Estabilizador: fica entre a fonte (MediaPipe) e a interface.

Corrige três problemas encontrados na inspeção da v2:
  1. O lado da mão (direita/esquerda) às vezes troca por alguns frames. Em
     cada troca a pele 3D mudava de modelo e "pulava". Agora o lado é FIXADO
     na calibração (rótulo mais frequente) e frames com o lado trocado são
     tratados como falha.
  2. Uma única falha de detecção já mostrava "mão perdida" e congelava a mão.
     Agora falhas curtas (até HOLD_S) mantêm a última pose ("segurando").
  3. Cada falha zerava o detector de repetições (perdia repetições). Agora só
     uma perda longa conta como "sem mão".

Estados devolvidos por process():
  "ok"          frame bom: atualiza tudo
  "segurando"   falha curta: mantém a última pose, não atualiza as métricas
  "perdida"     sem mão há mais de HOLD_S
  "outra_mao"   o lado detectado é o oposto do fixado há mais de HOLD_S
  "vista"       mão de lado há mais de HOLD_S (frames que não servem para medir)
"""

from collections import Counter, deque

HOLD_S = 0.4                  # falhas mais curtas que isso não são "mão perdida"
VOTE_FRAMES = 15              # antes de fixar: rótulo mais frequente nos últimos N frames


class HandStabilizer:
    def __init__(self):
        self.locked_hand = None
        self._votes = deque(maxlen=VOTE_FRAMES)
        self._last_good = None        # último raw "ok"
        self._bad_since = None        # instante da primeira falha da sequência atual
        self._absent_since = None     # instante desde quando a mão sumiu de vez
        self._run_kind = None         # motivo da sequência ("vista"/"outra_mao")

    # ------------------------------------------------------------- lado da mão
    @property
    def hand(self):
        """Lado fixado; antes disso, o mais frequente nos últimos frames."""
        if self.locked_hand:
            return self.locked_hand
        return Counter(self._votes).most_common(1)[0][0] if self._votes else None

    def lock(self, votes=None):
        """Fixa o lado (chamado ao fim da calibração)."""
        votes = votes if votes is not None else list(self._votes)
        if votes:
            self.locked_hand = Counter(votes).most_common(1)[0][0]

    def unlock(self):
        self.locked_hand = None
        self._votes.clear()

    # -------------------------------------------------------------- por frame
    def process(self, raw, valid=True, bad_kind="perdida"):
        """raw -> (raw a usar ou None, estado).
        valid=False: a mão foi detectada mas o frame não serve para medir
        (medida impossível ou mão de lado) -> tratado como uma falha; se durar
        mais que HOLD_S, o estado vira `bad_kind` ("perdida" ou "vista")."""
        t = raw["t"]
        present = raw["world"] is not None and valid
        wrong_side = (present and self.locked_hand is not None
                      and raw["handedness"] not in (None, self.locked_hand))

        if present and not wrong_side:
            if raw["handedness"]:
                self._votes.append(raw["handedness"])
            self._last_good = raw
            self._bad_since = self._absent_since = self._run_kind = None
            out = dict(raw)
            out["handedness"] = self.hand
            return out, "ok"

        if self._bad_since is None:
            self._bad_since = t
        if wrong_side:
            self._run_kind = "outra_mao"
        elif raw["world"] is not None and not valid and bad_kind != "perdida":
            self._run_kind = bad_kind
        # mão ausente (sem detecção) desde quando? frames detectados zeram isso
        if raw["world"] is None:
            if self._absent_since is None:
                self._absent_since = t
        else:
            self._absent_since = None

        if self._last_good is not None and t - self._bad_since <= HOLD_S:
            return self._last_good, "segurando"
        # O motivo é o da SEQUÊNCIA, não o do frame: com a mão de lado o
        # MediaPipe alterna frames de lado, vazios e impossíveis, e o aviso
        # piscaria entre "de lado" e "perdida". Só vira "perdida" se a mão
        # sumir de vez por mais de HOLD_S.
        if self._absent_since is not None and t - self._absent_since > HOLD_S:
            return None, "perdida"
        return None, self._run_kind or "perdida"

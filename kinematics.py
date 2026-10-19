"""
Cinemática dos dedos (usada pelo motor da avaliação, app/avaliador.py).

Tudo aqui é numpy puro e não depende da interface:
  - ângulos MCP / PIP / DIP (polegar: MCP / IP) com sinal:
      positivo = flexão, negativo = hiperextensão
  - TAM (Total Active Motion) e referência da literatura (~260° dedos longos, ~140° polegar)
  - TAM ativo (como na goniometria) = soma das flexões máximas - soma dos déficits de extensão
  - repetições por dedo (movimento / parcial / completa) com o tempo de cada fase
  - por dedo: déficit de extensão e arco de cada articulação, qualidade do
    movimento (velocidade média e de pico, suavidade, ciclo, cadência,
    regularidade, variação de amplitude e de velocidade), independência em
    relação aos outros dedos e contribuição de cada articulação
  - calibração: mede quanto cada dedo "treme" parado -> sensibilidade
"""

from collections import deque
from dataclasses import dataclass, field

import numpy as np

FINGERS = ["thumb", "index", "middle", "ring", "pinky"]
SHORT = {"thumb": "POL", "index": "IND", "middle": "MÉD", "ring": "ANE", "pinky": "MÍN"}
NAME = {"thumb": "Polegar", "index": "Indicador", "middle": "Médio",
        "ring": "Anelar", "pinky": "Mínimo"}

# Articulações de cada dedo: (sigla, (landmark antes, vértice, landmark depois))
# Índices MediaPipe: 0 punho; 1-4 polegar; 5-8 indicador; 9-12 médio; 13-16 anelar; 17-20 mínimo
JOINTS = {
    "thumb": [("MCP", (1, 2, 3)), ("IP", (2, 3, 4))],
    "index": [("MCP", (0, 5, 6)), ("PIP", (5, 6, 7)), ("DIP", (6, 7, 8))],
    "middle": [("MCP", (0, 9, 10)), ("PIP", (9, 10, 11)), ("DIP", (10, 11, 12))],
    "ring": [("MCP", (0, 13, 14)), ("PIP", (13, 14, 15)), ("DIP", (14, 15, 16))],
    "pinky": [("MCP", (0, 17, 18)), ("PIP", (17, 18, 19)), ("DIP", (18, 19, 20))],
}

# Flexão ativa normal (graus), valores típicos da literatura.
# TAM normal = soma: ~260° nos dedos longos, ~140° no polegar.
_LONG = {"MCP": 85.0, "PIP": 105.0, "DIP": 70.0}
NORMAL_JOINT = {"thumb": {"MCP": 60.0, "IP": 80.0}, "index": _LONG, "middle": _LONG,
                "ring": _LONG, "pinky": _LONG}


def normal_tam(finger):
    return sum(NORMAL_JOINT[finger].values())


# Classificação do TAM ativo em % do normal (no estilo ASSH):
# < 50% ruim, 50-75% regular, > 75% bom.  Usada para colorir os dedos.
GRADE_FAIR = 0.50
GRADE_GOOD = 0.75

# Repetição: amplitude (pico - vale do TAM) em fração do TAM normal.
COMPLETE_FRACTION = 0.75      # >= 75% do normal -> completa
PARTIAL_FRACTION = 0.25       # >= 25% do normal -> parcial; abaixo -> "movimento"

# Sensibilidade = menor movimento contado = 3x o tremor medido parado.
SENS_FACTOR = 3.0
# Teto de 30°: na webcam real (14 fps) o tremor do TAM medido parado foi de
# 7-8° (desvio padrão) -> 3x = 21-24°. Com teto de 15° o ruído contaria.
SENS_MIN, SENS_MAX, SENS_DEFAULT = 2.0, 30.0, 5.0

# O detector de repetições olha a média dos últimos N frames do TAM (só
# para contar; os números exibidos continuam crus). Sem isso, o tremor faz o
# "vale" cair até o extremo do ruído e conta repetições com a mão parada.
# Ajustado na simulação: 8 frames + fator 3 = zero repetições falsas em
# 3 x 2 min de mão parada (5 frames ainda contava algumas).
DETECTOR_SMOOTH_FRAMES = 8

CALIBRATION_FRAMES = 60       # ~2 s a 30 fps (45 subestimava o tremor)
STILL_WINDOW = 15             # frames usados para checar se a mão está parada
# Desvio padrão do TAM (°) acima disso = mão se mexendo. Medido na webcam
# real com boa luz (gravação de 20 s): tremor parado de 0,5-1,1°. Um limite
# folgado (12°) aceitava a mão em movimento como "parada" e inflava a
# sensibilidade; se não ficar parada, o tempo limite usa o trecho mais calmo.
STILL_MAX_STD = 4.0
CALIBRATION_TIMEOUT_S = 10.0  # sem 2 s parados nesse tempo -> usa o trecho mais calmo
# Mão "aberta" para calibrar: mediana do TAM dos 4 dedos longos abaixo disso.
# Na webcam real, mão aberta e parada deu TAM ~61° (o MediaPipe nunca dá 0°).
OPEN_HAND_MAX_TAM = 90.0

# Déficit de extensão (e hiperextensão) abaixo disso conta como 0°: está dentro
# do erro de medida (o goniômetro manual tem ~±5°; o tremor da câmera, 1-2°).
DEFICIT_TOLERANCE = 3.0

# Qualidade do movimento: calculada sobre as últimas N repetições.
QUALITY_LAST_REPS = 10
REGULAR_CV, MODERATE_CV = 0.15, 0.30   # variação da duração do ciclo
TREND_MIN_REPS = 6                     # tendência (fadiga) só com 6 repetições ou mais
# Consistência do esforço: variação do fechamento máximo (TAM no pico) entre as
# repetições mais fortes. Pouca variação = esforço parecido, máximo confiável.
EFFORT_TOP_REPS, EFFORT_MIN_REPS = 5, 3
CONSISTENT_CV, MODERATE_EFFORT_CV = 0.10, 0.20
# Repetições fortes: fechamento (TAM no pico) até STRONG_MARGIN abaixo do melhor da
# própria sessão. Com EFFORT_TOP_REPS delas, o valor máximo é confiável. Não depende
# do normal da literatura: um paciente com 45% do normal também chega lá.
STRONG_MARGIN = 0.10

# Velocidade de pico e suavidade usam o TAM CRU de cada repetição, reamostrado
# em grade uniforme. Abaixo desta amplitude o tremor domina o sinal e as duas
# medidas perdem o sentido.
SIGNAL_FS = 30.0
MIN_SMOOTH_AMPLITUDE = 15.0


def is_open_hand(angles):
    return float(np.median([angles[f].sum() for f in FINGERS[1:]])) < OPEN_HAND_MAX_TAM


# Ângulo fora desta faixa não é da mão, é erro do MediaPipe (pontos trocados
# ou escondidos ao girar a mão). O frame inteiro é DESCARTADO, como uma falha
# de detecção; nenhum valor é corrigido ou suavizado. Na gravação real, 8 de
# 1.550 frames (todos num giro rápido da mão) davam até 155° de flexão e -142°
# de "hiperextensão" e estragavam máximos e mínimos da sessão.
PLAUSIBLE_RANGE = (-60.0, 130.0)


def plausible(angles):
    lo, hi = PLAUSIBLE_RANGE
    return all(((v >= lo) & (v <= hi)).all() for v in angles.values())


# Vista da mão: com a mão de lado o MediaPipe erra muito os ângulos (teste com
# mão renderizada: 6-36° de erro médio conforme a vista; na gravação real, os
# extremos absurdos aconteceram com a mão a 74-92° da palma de frente). Só
# frames até VIEW_MAX_DEG da palma de frente entram nas medições.
# (180 desliga a regra.)
VIEW_MAX_DEG = 60.0


def view_angle(world, hand):
    """Ângulo entre a palma e a câmera: 0° = palma de frente, 90° = de lado,
    180° = dorso de frente. hand = mão real ("Right"/"Left")."""
    P = np.asarray(world, dtype=np.float64)
    n = np.cross(P[5] - P[0], P[17] - P[0])
    n /= np.linalg.norm(n) + 1e-12
    # conferido com a simulação: mão real direita com a palma para a câmera
    # tem n = (0, 0, +1); a esquerda, o oposto
    cos = n[2] * (1.0 if hand == "Right" else -1.0)
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def good_view(world, hand):
    return hand not in ("Right", "Left") or view_angle(world, hand) <= VIEW_MAX_DEG


# =============================================================================
# Ângulos
# =============================================================================
def joint_angles(world, hand=None):
    """21 landmarks 3D -> {dedo: array com a flexão de cada articulação (°)}.

    hand = mão REAL ("Right"/"Left", imagem espelhada): flexão medida como
    num goniômetro, no PLANO do movimento e COM SINAL (positivo = flexão,
    negativo = hiperextensão). Os dois segmentos são projetados no plano
    perpendicular ao eixo de flexão antes de medir o ângulo; assim o desvio
    lateral (abrir/fechar os dedos) não entra como flexão. Eixo de flexão:
      - dedos longos: eixo transversal da palma (base do indicador -> base do
        mínimo), que não muda com a postura do dedo;
      - polegar: normal da palma (a flexão do polegar cruza a palma).
    O sentido do eixo dos dedos longos depende do lado da mão; o da normal
    se inverte junto com a geometria e não precisa de correção.

    Sem hand: ângulo 3D sem sinal (sempre >= 0) - usado antes de se saber
    qual é a mão.
    """
    P = np.asarray(world, dtype=np.float64)
    signed = hand in ("Right", "Left")
    if signed:
        lateral = (P[17] - P[5]) * (1.0 if hand == "Right" else -1.0)
        normal = np.cross(P[5] - P[0], P[17] - P[0])
        axes = {"long": lateral / np.linalg.norm(lateral), "thumb": normal / np.linalg.norm(normal)}
    out = {}
    for f in FINGERS:
        values = []
        for _, (a, b, c) in JOINTS[f]:
            u, v = P[b] - P[a], P[c] - P[b]
            if signed:
                ax = axes["thumb" if f == "thumb" else "long"]
                u = u - (u @ ax) * ax                     # projeta no plano da flexão
                v = v - (v @ ax) * ax
                ang = float(np.degrees(np.arctan2(np.cross(u, v) @ ax, u @ v)))
            else:
                cos = u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12)
                ang = float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))
            values.append(ang)
        out[f] = np.array(values)
    return out


# =============================================================================
# Sinal: velocidade e suavidade de um trecho de movimento
# =============================================================================
def uniform(t, x, fs=SIGNAL_FS):
    """Amostras em intervalos irregulares -> grade uniforme (interpolação linear)."""
    t, x = np.asarray(t, dtype=float), np.asarray(x, dtype=float)
    n = int(np.floor((t[-1] - t[0]) * fs)) + 1
    tu = t[0] + np.arange(n) / fs
    return tu, np.interp(tu, t, x)


def derivative(x, fs=SIGNAL_FS):
    """Derivada por mínimos quadrados em 5 pontos (Savitzky-Golay, 1ª ordem).
    Só entra no CÁLCULO da velocidade: nada exibido é suavizado. A diferença
    entre quadros vizinhos transformaria o tremor de ~1° do MediaPipe em ~40°/s."""
    x = np.asarray(x, dtype=float)
    d = np.gradient(x) * fs
    if len(x) >= 5:
        d[2:-2] = (-2 * x[:-4] - x[1:-3] + x[3:-1] + 2 * x[4:]) / 10.0 * fs
    return d


def sparc(speed, fs=SIGNAL_FS, pad_level=4, fc=10.0, amp_th=0.05):
    """Suavidade do movimento: comprimento do arco espectral (SPARC,
    Balasubramanian et al. 2015). Mais perto de zero = mais suave; um movimento
    em forma de sino dá cerca de -1,5, e trancos o deixam mais negativo."""
    speed = np.asarray(speed, dtype=float)
    if len(speed) < 6 or speed.max() <= 0:
        return None
    nfft = int(2 ** (np.ceil(np.log2(len(speed))) + pad_level))
    f = np.arange(nfft) * fs / nfft
    mag = np.abs(np.fft.fft(speed, nfft))
    mag = mag / mag.max()
    keep = f <= fc
    f, mag = f[keep], mag[keep]
    above = np.nonzero(mag >= amp_th)[0]
    f, mag = f[above[0]:above[-1] + 1], mag[above[0]:above[-1] + 1]
    if len(f) < 2:
        return None
    return float(-np.sum(np.sqrt((np.diff(f) / (f[-1] - f[0])) ** 2 + np.diff(mag) ** 2)))


def trend(values):
    """Variação relativa do início ao fim pela reta de regressão (ex.: -0,12 =
    caiu 12% ao longo das repetições). None com poucos valores."""
    v = np.asarray([x for x in values if x is not None], dtype=float)
    if len(v) < TREND_MIN_REPS:
        return None
    a, b = np.polyfit(np.arange(len(v)), v, 1)
    first, last = b, a * (len(v) - 1) + b
    return float((last - first) / first) if first > 0 else None


# =============================================================================
# Repetições por dedo
# =============================================================================
@dataclass
class Rep:
    amplitude: float          # pico - vale do TAM (°)
    peak_tam: float           # TAM no pico (°)
    excursion: np.ndarray     # quanto cada articulação se moveu nessa repetição (°)
    kind: str                 # "movimento" | "parcial" | "completa"
    t_start: float = None     # início da flexão (vale)
    t_peak: float = None      # fim da flexão (pico)
    t_end: float = None       # quando a repetição foi fechada (já voltando)
    ext_amplitude: float = None   # extensão completa: pico -> vale seguinte
    t_ext_end: float = None       #   (preenchida quando o próximo vale é achado)
    coupling: dict = field(default=None)   # {outro dedo: quanto se moveu junto (0..1,5)}
    independence: float = None             # 1 - média do acoplamento (0..1)
    peak_velocity: float = None            # maior velocidade na flexão (°/s), sinal cru
    sparc_flex: float = None               # suavidade da flexão
    sparc_ext: float = None                # suavidade da extensão (quando o vale seguinte chega)

    @property
    def flex_velocity(self):
        """Velocidade média de flexão (°/s) = amplitude / tempo de subida."""
        dt = (self.t_peak - self.t_start) if self.t_start is not None else None
        return self.amplitude / dt if dt and dt > 0.05 else None

    @property
    def ext_velocity(self):
        if self.t_ext_end is None or self.ext_amplitude is None:
            return None
        dt = self.t_ext_end - self.t_peak
        return self.ext_amplitude / dt if dt > 0.05 else None


class FingerTracker:
    """Estado de um dedo durante a sessão.

    Uma repetição = o TAM sobe (flexão) e volta (extensão). Para o ruído não
    contar repetições falsas, usa histerese do tamanho da sensibilidade: só
    vira "subindo" quando passa do vale + sensibilidade, e só fecha a
    repetição quando cai do pico - sensibilidade.
    """

    def __init__(self, finger, sensitivity=SENS_DEFAULT):
        self.finger = finger
        self.sens = sensitivity
        self.normal = normal_tam(finger)
        self.normal_joints = np.array(list(NORMAL_JOINT[finger].values()))
        self.joint_names = [n for n, _ in JOINTS[finger]]
        self.reps = []
        self.tam = None            # agora
        self.joints = None         # agora (array)
        self.max_tam = None        # máximo da sessão (soma no mesmo instante)
        self.max_joints = None     # flexão máxima de cada articulação
        self.min_joints = None     # menor flexão (= extensão máxima) de cada articulação
        self._mode = None          # None | "down" (procurando vale) | "up" (procurando pico)
        self._awaiting_ext = False # a última repetição espera o vale seguinte
        self._recent = deque(maxlen=DETECTOR_SMOOTH_FRAMES)
        self._raw = deque(maxlen=900)   # (t, TAM cru) dos últimos ~30 s: velocidade e suavidade

    def update(self, joints, t=None):
        """joints = flexões das articulações deste dedo, ou None (sem mão).
        Devolve a Rep fechada neste frame, se houver."""
        if joints is None:
            self.tam = self.joints = None
            self._mode = None                  # recomeça depois de perder a mão
            self._awaiting_ext = False
            self._recent.clear()
            self._raw.clear()
            return None
        self.tam, self.joints = float(joints.sum()), joints
        if t is not None:
            self._raw.append((t, self.tam))
        self.max_tam = self.tam if self.max_tam is None else max(self.max_tam, self.tam)
        self.max_joints = joints.copy() if self.max_joints is None else np.maximum(self.max_joints, joints)
        self.min_joints = joints.copy() if self.min_joints is None else np.minimum(self.min_joints, joints)

        self._recent.append(joints)
        if len(self._recent) < self._recent.maxlen:
            return None
        joints = np.mean(self._recent, axis=0)     # só para detectar repetições
        tam = float(joints.sum())

        if self._mode is None:
            self._mode = "down"
            self._valley, self._valley_joints, self._valley_t = tam, joints.copy(), t
        elif self._mode == "down":
            if tam < self._valley:
                self._valley, self._valley_joints, self._valley_t = tam, joints.copy(), t
            elif tam > self._valley + self.sens:
                if self._awaiting_ext and self.reps:   # o vale achado fecha a extensão anterior
                    prev = self.reps[-1]
                    prev.ext_amplitude = prev.peak_tam - self._valley
                    prev.t_ext_end = self._valley_t
                    seg = self._segment(prev.t_peak, self._valley_t, rising=False)
                    if seg is not None and prev.amplitude >= MIN_SMOOTH_AMPLITUDE:
                        prev.sparc_ext = sparc(np.abs(derivative(seg)))
                self._awaiting_ext = False
                self._mode, self._peak, self._peak_t, self._up_max = "up", tam, t, joints.copy()
        else:
            self._up_max = np.maximum(self._up_max, joints)
            if tam > self._peak:
                self._peak, self._peak_t = tam, t
            elif tam < self._peak - self.sens:
                rep = self._close(t)
                self._mode = "down"
                self._valley, self._valley_joints, self._valley_t = tam, joints.copy(), t
                self._awaiting_ext = True
                return rep
        return None

    def _close(self, t):
        amp = self._peak - self._valley
        if amp >= COMPLETE_FRACTION * self.normal:
            kind = "completa"
        elif amp >= PARTIAL_FRACTION * self.normal:
            kind = "parcial"
        else:
            kind = "movimento"
        rep = Rep(amp, self._peak, np.maximum(0.0, self._up_max - self._valley_joints), kind,
                  t_start=self._valley_t, t_peak=self._peak_t, t_end=t)
        seg = self._segment(rep.t_start, rep.t_peak, rising=True)
        if seg is not None and amp >= MIN_SMOOTH_AMPLITUDE:
            speed = derivative(seg)
            rep.peak_velocity = float(speed.max())
            rep.sparc_flex = sparc(np.abs(speed))
        self.reps.append(rep)
        return rep

    def _segment(self, t0, t1, rising):
        """TAM cru (grade uniforme) de um movimento: do extremo perto de t0 ao
        extremo perto de t1. t0/t1 vêm do detector, que olha a média dos últimos
        quadros e por isso atrasa ~0,1 s: o extremo cru é procurado um pouco antes."""
        if t0 is None or t1 is None or t1 - t0 < 0.1:
            return None
        pts = [(tt, v) for tt, v in self._raw if t0 - 0.4 <= tt <= t1 + 0.1]
        if len(pts) < 6:
            return None
        tu, x = uniform(*zip(*pts))
        head = tu <= t0 + 0.1
        tail = tu >= t1 - 0.4
        if not head.any() or not tail.any():
            return None
        pick_start, pick_end = (np.argmin, np.argmax) if rising else (np.argmax, np.argmin)
        i0 = int(pick_start(np.where(head, x, np.inf if rising else -np.inf)))
        i1 = int(pick_end(np.where(tail, x, -np.inf if rising else np.inf)))
        return x[i0:i1 + 1] if i1 - i0 >= 5 else None

    # ------------------------------------------------------------- amplitude
    def counts(self):
        c = {"movimento": 0, "parcial": 0, "completa": 0}
        for r in self.reps:
            c[r.kind] += 1
        return c

    def deficits(self):
        """Déficit de extensão por articulação (°): menor flexão alcançada, se
        passar da tolerância (0 = estendeu por completo; hiperextensão também
        conta 0)."""
        if self.min_joints is None:
            return None
        return np.where(self.min_joints > DEFICIT_TOLERANCE, self.min_joints, 0.0)

    def arcs(self):
        """Arco de movimento por articulação (°) = flexão máx - flexão mín."""
        return None if self.min_joints is None else self.max_joints - self.min_joints

    def active_tam(self):
        """TAM ativo (como na goniometria) = soma das flexões máximas - soma
        dos déficits de extensão. Também desconta o viés do MediaPipe, que
        nunca mede 0° com o dedo esticado."""
        if self.max_joints is None:
            return None
        return float(self.max_joints.sum() - self.deficits().sum())

    def percent_normal(self):
        """TAM ativo / TAM normal (None sem dados)."""
        tam = self.active_tam()
        return None if tam is None else max(0.0, tam) / self.normal

    def limiting_joint(self):
        """Índice da articulação que menos se moveu (em % do normal dela) nas
        repetições não completas; None se não houver."""
        reps = [r for r in self.reps if r.kind != "completa"]
        if not reps:
            return None
        ratio = np.mean([r.excursion / self.normal_joints for r in reps], axis=0)
        return int(np.argmin(ratio))

    # ------------------------------------------------- qualidade do movimento
    def quality(self):
        """Métricas das últimas repetições (None onde ainda não dá para calcular)."""
        recent = self.reps[-QUALITY_LAST_REPS:]
        flex = [r.flex_velocity for r in recent if r.flex_velocity is not None]
        ext = [r.ext_velocity for r in recent if r.ext_velocity is not None]
        starts = [r.t_start for r in self.reps if r.t_start is not None]
        periods = np.diff(starts)[-QUALITY_LAST_REPS:] if len(starts) > 1 else np.array([])
        peaks = [r.peak_velocity for r in recent if r.peak_velocity is not None]
        smooth = [v for r in recent for v in (r.sparc_flex, r.sparc_ext) if v is not None]
        q = {"flex_velocity": float(np.mean(flex)) if flex else None,
             "ext_velocity": float(np.mean(ext)) if ext else None,
             "peak_velocity": float(np.mean(peaks)) if peaks else None,
             "sparc": float(np.mean(smooth)) if smooth else None,
             "cycle_s": float(np.median(periods)) if len(periods) >= 1 else None,
             "cadence": 60.0 / float(np.median(periods)) if len(periods) >= 2 else None,
             "cv": None, "regularity": None, "amp_change": None,
             # fadiga: tendência ao longo de TODAS as repetições (reta de regressão)
             "amp_trend": trend([r.amplitude for r in self.reps]),
             "vel_trend": trend([r.flex_velocity for r in self.reps])}
        if len(periods) >= 3:
            q["cv"] = float(np.std(periods) / np.mean(periods))
            q["regularity"] = ("Regular" if q["cv"] < REGULAR_CV else
                               "Moderada" if q["cv"] < MODERATE_CV else "Irregular")
        if len(self.reps) >= 6:
            first = np.mean([r.amplitude for r in self.reps[:3]])
            last = np.mean([r.amplitude for r in self.reps[-3:]])
            q["amp_change"] = float((last - first) / first) if first > 0 else None
        q["effort_cv"], q["effort"] = None, None
        peaks = sorted(r.peak_tam for r in self.reps)[-EFFORT_TOP_REPS:]
        if len(peaks) >= EFFORT_MIN_REPS and np.mean(peaks) > 0:
            cv = float(np.std(peaks) / np.mean(peaks))
            q["effort_cv"] = cv
            q["effort"] = ("Consistente" if cv < CONSISTENT_CV else
                           "Moderada" if cv < MODERATE_EFFORT_CV else "Variável")
        return q

    def strong_reps(self):
        """Quantas repetições chegaram perto do melhor fechamento desta sessão."""
        if not self.reps:
            return 0
        best = max(r.peak_tam for r in self.reps)
        return sum(r.peak_tam >= best * (1 - STRONG_MARGIN) for r in self.reps)

    def moved(self):
        """O dedo fez ao menos uma repetição de verdade (num exercício isolado de outro
        dedo, ele fica parado e não entra na conferência das repetições fortes)."""
        return any(r.amplitude >= MIN_SMOOTH_AMPLITUDE for r in self.reps)

    # ---------------------------------------------------------------- padrão
    def independence(self):
        vals = [r.independence for r in self.reps if r.independence is not None]
        return float(np.mean(vals)) if vals else None

    def coupling(self):
        """Média do quanto cada outro dedo se moveu junto (0..1,5)."""
        acc = {}
        for r in self.reps:
            for g, v in (r.coupling or {}).items():
                acc.setdefault(g, []).append(v)
        return {g: float(np.mean(v)) for g, v in acc.items()}

    def contribution(self):
        """Fração média de cada articulação no movimento das repetições."""
        parts = [r.excursion / r.excursion.sum() for r in self.reps if r.excursion.sum() > 0]
        return np.mean(parts, axis=0) if parts else None


def grade(pct):
    """% do normal -> "ruim" | "regular" | "bom" (None sem dados)."""
    if pct is None:
        return None
    if pct < GRADE_FAIR:
        return "ruim"
    return "regular" if pct < GRADE_GOOD else "bom"


# =============================================================================
# Calibração (mão aberta e parada)
# =============================================================================
class Calibration:
    def __init__(self, frames=CALIBRATION_FRAMES):
        self.frames = frames
        self.best = None           # {dedo: desvio} do trecho mais calmo já visto
        self.approximate = False   # True se terminou pelo tempo limite
        self.reset()

    def reset(self):
        """Recomeça a contagem (a mão mexeu). O trecho mais calmo é mantido."""
        self.tams = {f: [] for f in FINGERS}

    def add(self, angles):
        for f in FINGERS:
            self.tams[f].append(float(angles[f].sum()))
        if self.count >= STILL_WINDOW:
            window = {f: float(np.std(v[-STILL_WINDOW:])) for f, v in self.tams.items()}
            if self.best is None or max(window.values()) < max(self.best.values()):
                self.best = window

    @property
    def count(self):
        return len(self.tams["index"])

    @property
    def progress(self):
        return min(1.0, self.count / self.frames)

    def is_still(self):
        """A mão está parada? (desvio padrão recente do TAM de cada dedo)."""
        if self.count < STILL_WINDOW:
            return True
        return all(np.std(v[-STILL_WINDOW:]) < STILL_MAX_STD for v in self.tams.values())

    def done(self):
        return self.count >= self.frames

    def sensitivity(self):
        """Menor movimento contado por dedo = 3x o tremor medido parado.
        Se a calibração não completou (tempo limite), usa o trecho mais calmo."""
        if self.done():
            stds = {f: float(np.std(v)) for f, v in self.tams.items()}
        else:
            self.approximate = True
            stds = self.best or {f: SENS_DEFAULT / SENS_FACTOR for f in FINGERS}
        return {f: float(np.clip(SENS_FACTOR * s, SENS_MIN, SENS_MAX)) for f, s in stds.items()}


# =============================================================================
# Sessão
# =============================================================================
class Session:
    HISTORY_S = 20.0           # janela do gráfico de TAM (e da independência)

    def __init__(self, sensitivity=None, start_time=0.0):
        sensitivity = sensitivity or {}
        self.trackers = {f: FingerTracker(f, sensitivity.get(f, SENS_DEFAULT)) for f in FINGERS}
        self.start_time = start_time
        self.history = deque()     # (t, [TAM de cada dedo ou nan])
        self.discarded = 0         # frames descartados por ângulo impossível

    def update(self, angles, t):
        """angles = joint_angles(...) ou None (sem mão neste frame)."""
        tams = [np.nan if angles is None else float(angles[f].sum()) for f in FINGERS]
        self.history.append((t, tams))
        while self.history and t - self.history[0][0] > self.HISTORY_S:
            self.history.popleft()
        for f, tr in self.trackers.items():
            rep = tr.update(None if angles is None else angles[f], t)
            if rep is not None:
                self._annotate(f, rep)

    def _annotate(self, finger, rep):
        """Independência: quanto os OUTROS dedos se moveram durante esta
        repetição. Do movimento de cada um desconta-se a sensibilidade dele
        (a faixa que o próprio tremor ocupa), para o tremor não parecer movimento."""
        if rep.t_start is None:
            return
        window = [vals for tt, vals in self.history if rep.t_start - 0.2 <= tt <= rep.t_end]
        if len(window) < 3:
            return
        V = np.array(window)
        coupling = {}
        for i, g in enumerate(FINGERS):
            if g == finger:
                continue
            col = V[:, i][~np.isnan(V[:, i])]
            if len(col) < 3:
                continue
            moved = max(0.0, float(col.max() - col.min()) - self.trackers[g].sens)
            coupling[g] = min(1.5, moved / max(rep.amplitude, 1e-6))
        rep.coupling = coupling
        if coupling:
            rep.independence = float(np.clip(1.0 - np.mean(list(coupling.values())), 0.0, 1.0))

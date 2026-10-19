"""
Medidas clínicas além da cinemática básica (numpy puro, sem interface):

  - arco funcional por articulação: a faixa usada nas atividades diárias
  - escore de Strickland (PIP + DIP), usado após reparo de tendão flexor
  - distância polpa-palma estimada
  - abertura dos dedos (abdução) e do polegar
  - tremor nos trechos com a mão parada
  - confiabilidade da sessão

Padrões posturais (pescoço de cisne, botoeira, garra) ficaram de fora: na
gravação real de uma mão saudável aberta o MediaPipe marcou até 48° de flexão na
PIP e -41° de hiperextensão na MCP; qualquer regra de postura marcaria a mão
saudável. Precisam de validação com goniômetro antes.
"""

import numpy as np

import kinematics as kin

# -----------------------------------------------------------------------------
# Arco funcional (Bain et al., J Hand Surg Eur 2015): faixa de flexão usada em
# atividades diárias, dedos longos. Sem referência equivalente para o polegar.
# -----------------------------------------------------------------------------
FUNCTIONAL_ROM = {"MCP": (19.0, 71.0), "PIP": (23.0, 87.0), "DIP": (10.0, 64.0)}


def functional_range(finger, joint):
    return None if finger == "thumb" else FUNCTIONAL_ROM.get(joint)


def functional_coverage(finger, joint, mn, mx):
    """Fração (0..1) da faixa funcional coberta pelo arco medido [mn, mx];
    None sem referência ou sem dado."""
    ref = functional_range(finger, joint)
    if ref is None or mn is None or mx is None:
        return None
    lo, hi = ref
    return float(max(0.0, min(mx, hi) - max(mn, lo)) / (hi - lo))


# -----------------------------------------------------------------------------
# Strickland (Strickland & Glogovac 1980): (flexão PIP + DIP - déficits) / 175°
# -----------------------------------------------------------------------------
STRICKLAND_TOTAL = 175.0
STRICKLAND_GRADES = ((0.85, "excelente"), (0.70, "bom"), (0.50, "regular"), (0.0, "ruim"))


def strickland(finger, maxs, deficits):
    """maxs / deficits = arrays MCP, PIP, DIP do dedo. None no polegar ou sem dado."""
    if finger == "thumb" or maxs is None or deficits is None:
        return None
    return float(max(0.0, maxs[1] + maxs[2] - deficits[1] - deficits[2]) / STRICKLAND_TOTAL)


def strickland_grade(value):
    if value is None:
        return None
    return next(name for limit, name in STRICKLAND_GRADES if value >= limit)


# -----------------------------------------------------------------------------
# Distância polpa-palma (estimada)
# -----------------------------------------------------------------------------
TIPS = {"index": 8, "middle": 12, "ring": 16, "pinky": 20}
# "Zero" de cada dedo, em comprimentos de palma (punho -> base do médio): a
# distância ponta -> linha das bases dos dedos no punho mais fechado de uma mão
# saudável (gravação de teste de 14/10/2026). Os pontos do MediaPipe ficam no
# centro das articulações, não na pele: mesmo com a ponta encostada na palma
# sobra essa distância (1,4 a 2,3 cm naquela mão).
TPD_ZERO = {"index": 0.24, "middle": 0.14, "ring": 0.15, "pinky": 0.24}


def _segment_distance(p, a, b):
    ab = b - a
    s = np.clip((p - a) @ ab / (ab @ ab), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + s * ab)))


def tip_to_palm_cm(world):
    """Distância (cm) da ponta de cada dedo longo até a palma. A escala do
    MediaPipe é a de uma mão de tamanho médio: os centímetros são aproximados."""
    P = np.asarray(world, dtype=np.float64)
    palm = np.linalg.norm(P[9] - P[0])
    return {f: max(0.0, _segment_distance(P[tip], P[5], P[17]) - TPD_ZERO[f] * palm) * 100.0
            for f, tip in TIPS.items()}


# -----------------------------------------------------------------------------
# Abertura dos dedos e do polegar
# -----------------------------------------------------------------------------
SPREAD_PAIRS = [("index", "middle"), ("middle", "ring"), ("ring", "pinky")]
PROXIMAL = {"index": (5, 6), "middle": (9, 10), "ring": (13, 14), "pinky": (17, 18)}
# Só com os dedos pouco flexionados: ao fechar, a falange se inclina para a palma,
# a projeção encolhe e o ângulo entre os dedos deixa de significar afastamento.
SPREAD_MAX_MCP = 30.0


def finger_spread(world, angles):
    """[ind-méd, méd-ane, ane-mín]: ângulo (°) entre as falanges proximais de
    dedos vizinhos, no plano da palma (None no par com dedo flexionado demais)."""
    P = np.asarray(world, dtype=np.float64)
    n = np.cross(P[5] - P[0], P[17] - P[0])
    n /= np.linalg.norm(n) + 1e-12

    def direction(f):
        a, b = PROXIMAL[f]
        u = P[b] - P[a]
        u = u - (u @ n) * n
        return u / (np.linalg.norm(u) + 1e-12)

    out = []
    for f, g in SPREAD_PAIRS:
        if angles[f][0] > SPREAD_MAX_MCP or angles[g][0] > SPREAD_MAX_MCP:
            out.append(None)
        else:
            out.append(float(np.degrees(np.arccos(np.clip(direction(f) @ direction(g), -1.0, 1.0)))))
    return out


def thumb_opening(world):
    """Ângulo (°) entre o metacarpo do polegar e o do indicador (abertura da
    primeira comissura, misturando abdução radial e palmar)."""
    P = np.asarray(world, dtype=np.float64)
    u, v = P[2] - P[1], P[5] - P[0]
    cos = u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12)
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


class HandMeasures:
    """Máximos e mínimos da sessão das medidas da mão inteira."""

    def __init__(self):
        self.spread_max = [None, None, None]
        self.thumb_max = None
        self.tpd_min = {f: None for f in TIPS}

    def add(self, world, angles):
        for i, v in enumerate(finger_spread(world, angles)):
            if v is not None:
                self.spread_max[i] = v if self.spread_max[i] is None else max(self.spread_max[i], v)
        th = thumb_opening(world)
        self.thumb_max = th if self.thumb_max is None else max(self.thumb_max, th)
        for f, d in tip_to_palm_cm(world).items():
            self.tpd_min[f] = d if self.tpd_min[f] is None else min(self.tpd_min[f], d)

    def results(self):
        total = None
        if None not in self.spread_max:
            total = float(sum(self.spread_max))
        return {"abertura_dedos": [None if v is None else round(v, 1) for v in self.spread_max],
                "abertura_dedos_total": None if total is None else round(total, 1),
                "abertura_polegar": None if self.thumb_max is None else round(self.thumb_max, 1),
                "polpa_palma_cm": {f: None if v is None else round(v, 1) for f, v in self.tpd_min.items()}}


# -----------------------------------------------------------------------------
# Tremor nos trechos com a mão parada
# -----------------------------------------------------------------------------
TREMOR_WINDOW_S = 2.0
TREMOR_BAND = (3.0, 12.0)         # Hz: repouso parkinsoniano ~4-6, fisiológico ~8-12
TREMOR_PEAK_RATIO = 4.0           # pico >= 4x a mediana da banda = oscilação rítmica
_GRID = np.arange(0.0, 15.01, 0.25)


class TremorMeter:
    """Junta trechos de ~2 s com a mão parada (TAM de todos os dedos variando
    menos que kin.STILL_MAX_STD) e procura uma oscilação rítmica na posição
    média das pontas dos dedos em relação ao punho. O MediaPipe tem ruído de
    fundo de cerca de 1 mm, espalhado por todas as frequências: só um pico bem
    acima da mediana do espectro conta como oscilação rítmica."""

    def __init__(self):
        self.buf = []
        self.spectra, self.rms, self.fmax = [], [], []

    def add(self, t, world, angles):
        if t is None:
            return
        P = np.asarray(world, dtype=np.float64)
        self.buf.append((t, P[[4, 8, 12, 16, 20]].mean(axis=0) - P[0],
                         [float(angles[f].sum()) for f in kin.FINGERS]))
        if self.buf[-1][0] - self.buf[0][0] >= TREMOR_WINDOW_S:
            self._analyze()
            self.buf = []

    def interrupt(self):
        """Mão perdida ou medição parada: o trecho atual não continua."""
        self.buf = []

    def _analyze(self):
        T = np.array([b[0] for b in self.buf])
        X = np.array([b[1] for b in self.buf])
        tams = np.array([b[2] for b in self.buf])
        if len(T) < 16 or tams.std(axis=0).max() >= kin.STILL_MAX_STD:
            return                                    # mão se mexendo: não é repouso
        fs = 1.0 / float(np.median(np.diff(T)))
        if fs < 10:
            return
        n = int((T[-1] - T[0]) * fs) + 1
        tu = T[0] + np.arange(n) / fs
        power = np.zeros(n // 2 + 1)
        detrended = []
        for k in range(3):
            x = np.interp(tu, T, X[:, k])
            x = x - np.polyval(np.polyfit(tu - tu[0], x, 1), tu - tu[0])
            detrended.append(x)
            power += np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
        freqs = np.fft.rfftfreq(n, 1.0 / fs)
        self.spectra.append(np.interp(_GRID, freqs, power, right=0.0))   # acima de fs/2: fora da banda
        self.rms.append(float(np.sqrt(np.mean(np.sum(np.square(detrended), axis=0)))))
        self.fmax.append(min(TREMOR_BAND[1], 0.45 * fs))

    def result(self):
        windows = len(self.spectra)
        out = {"janelas": windows, "segundos": round(windows * TREMOR_WINDOW_S),
               "ritmico": False, "frequencia_hz": None, "rms_mm": None, "razao_pico": None}
        if not windows:
            return out
        spectrum = np.mean(self.spectra, axis=0)
        band = (_GRID >= TREMOR_BAND[0]) & (_GRID <= min(self.fmax))
        out["rms_mm"] = round(float(np.median(self.rms)) * 1000.0, 2)
        if band.sum() < 4:
            return out
        b = spectrum[band]
        i = int(np.argmax(b))
        ratio = float(b[i] / (np.median(b) + 1e-20))
        out["razao_pico"] = round(ratio, 1)
        # um tremor faz um pico no meio da banda; movimento voluntário lento deixa
        # energia que só desce a partir da borda de 3 Hz (máximo na borda = não é tremor)
        peak = 0 < i < len(b) - 1 and b[i] >= 2 * b[0]
        if ratio >= TREMOR_PEAK_RATIO and peak:
            out["ritmico"] = True
            out["frequencia_hz"] = round(float(_GRID[band][i]), 1)
        return out


# -----------------------------------------------------------------------------
# Distância da câmera
# -----------------------------------------------------------------------------
# Tamanho da mão na imagem: punho -> base do dedo médio, em fração da altura.
# Nas gravações reais, a ~50 cm: 0,27-0,29. A mão inclinada parece menor por um
# instante; por isso só avisa depois de DISTANCE_FRAMES quadros seguidos.
HAND_FAR, HAND_NEAR = 0.13, 0.50
DISTANCE_FRAMES = 15                # ~0,5 s


def hand_image_size(img, aspect):
    dx = (img[9][0] - img[0][0]) * aspect
    dy = img[9][1] - img[0][1]
    return float(np.hypot(dx, dy))


class DistanceCheck:
    """update(raw) -> "longe", "perto" ou None. Só avisa quando a mesma situação
    dura DISTANCE_FRAMES quadros seguidos (o aviso não fica piscando)."""

    def __init__(self):
        self.kind, self.count = None, 0

    def update(self, raw):
        kind = None
        if raw.get("img") is not None:
            size = hand_image_size(raw["img"], raw.get("aspect") or 1.0)
            kind = "longe" if size < HAND_FAR else "perto" if size > HAND_NEAR else None
        self.count = self.count + 1 if kind is not None and kind == self.kind else int(kind is not None)
        self.kind = kind
        return kind if self.count >= DISTANCE_FRAMES else None


# -----------------------------------------------------------------------------
# Confiabilidade da sessão
# -----------------------------------------------------------------------------
RELIABILITY_NAMES = {"alta": "alta", "media": "média", "baixa": "baixa"}


def session_reliability(frames, ok, fps=None, brightness=None, view=None, reps=0, duration_s=0):
    """frames = quadros com imagem durante a avaliação; ok = os que viraram medida.
    fps / brightness / view = medianas (None se a fonte não informa).
    Devolve {"nivel": "alta"|"media"|"baixa", "motivos": [...], "detalhes": {...}}."""
    problems = []                                    # (gravidade, texto)
    valid = ok / frames if frames else 0.0
    if frames:
        if valid < 0.60:
            problems.append((2, f"{(1 - valid) * 100:.0f}% dos quadros sem medida válida"))
        elif valid < 0.85:
            problems.append((1, f"{(1 - valid) * 100:.0f}% dos quadros sem medida válida"))
    if fps is not None:
        if fps < 15:
            problems.append((2, "imagem lenta"))
        elif fps < 20:
            problems.append((1, "imagem um pouco lenta"))
    if brightness is not None:
        if brightness < 50:
            problems.append((2, "pouca luz"))
        elif brightness < 80:
            problems.append((1, "luz fraca"))
    if view is not None:
        if view > 50:
            problems.append((2, f"mão muito inclinada (mediana {view:.0f}° da palma de frente)"))
        elif view > 40:
            problems.append((1, f"mão inclinada (mediana {view:.0f}° da palma de frente)"))
    if reps < 3 or duration_s < 15:
        problems.append((1, "sessão curta (poucas repetições)"))
    if not frames:
        problems.append((2, "sem quadros na avaliação"))
    worst = max((p[0] for p in problems), default=0)
    return {"nivel": {0: "alta", 1: "media", 2: "baixa"}[worst],
            "motivos": [p[1] for p in sorted(problems, key=lambda p: -p[0])],
            "detalhes": {"quadros": int(frames), "validos_pct": round(valid * 100, 1),
                         "fps": None if fps is None else round(fps, 1),
                         "brilho": None if brightness is None else round(brightness),
                         "vista_graus": None if view is None else round(view)}}

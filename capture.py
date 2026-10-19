"""
Captura: webcam + MediaPipe Hand Landmarker, e os arquivos de pontos da mão.

Fontes (todas entregam o mesmo dicionário "raw" via latest()):
  CameraSource   - webcam ao vivo (thread separada)
  ReplaySource   - reproduz um arquivo de pontos (.npz) no tempo em que foi gravado
  (app/simulacao.py tem a mão simulada, no mesmo formato)

Formato "raw":
  t           instante (s)                world   (21,3) metros ou None (sem mão)
  img         (21,2) 0..1 na imagem       confidence  0..1
  handedness  "Left"/"Right" (mão REAL)   aspect  largura/altura
  frame       imagem RGB ou None          fps / brightness / inference_ms  (qualidade)

Arquivo de pontos (.npz, sem vídeo): save_recording / load_recording. É o que
fica em dados_locais/pontos/ para cada avaliação salva.
"""

import os
import sys
import threading
import time
import urllib.request

import numpy as np

from geometria import FINGERTIPS, HAND_CONNECTIONS

# O mediapipe atual usa a API Tasks, que precisa de um arquivo de modelo (.task),
# baixado na primeira execução.
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")

# Limiares do MediaPipe (0..1). Mais baixos = insiste mais em manter a mão,
# com mais risco de "achar" mão onde não tem. Padrão do MediaPipe = 0.5.
DETECTION_CONFIDENCE = 0.5
PRESENCE_CONFIDENCE = 0.5
TRACKING_CONFIDENCE = 0.5

FRAME_KEYS = ("t", "world", "img", "confidence", "handedness", "aspect", "fps", "brightness",
              "inference_ms")


def ensure_model():
    """Baixa o modelo do MediaPipe se ainda não estiver na pasta (o Instalar sistema.bat
    chama na instalação; a câmera chama de novo por garantia)."""
    if not os.path.exists(MODEL_PATH):
        print(f"Baixando modelo do MediaPipe para {MODEL_PATH} ...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)


class _Stats:
    """fps medido e média móvel de brilho / tempo de inferência."""

    def __init__(self):
        self.last_t = None
        self.fps = 0.0
        self.brightness = 0.0
        self.inference_ms = 0.0

    def update(self, t, brightness, inference_ms):
        if self.last_t is not None and t > self.last_t:
            inst = 1.0 / (t - self.last_t)
            self.fps = inst if self.fps == 0 else 0.9 * self.fps + 0.1 * inst
        self.last_t = t
        a = 0.1 if self.brightness else 1.0
        self.brightness += a * (brightness - self.brightness)
        self.inference_ms += a * (inference_ms - self.inference_ms)


# =============================================================================
# Webcam
# =============================================================================
class CameraSource:
    def __init__(self, cam_index=0, width=640, height=480, detection=DETECTION_CONFIDENCE,
                 presence=PRESENCE_CONFIDENCE, tracking=TRACKING_CONFIDENCE):
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self.cv2, self.mp = cv2, mp

        ensure_model()

        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(cam_index, backend)
        if not self.cap.isOpened():
            raise RuntimeError(f"não consegui abrir a câmera {cam_index}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        self.settings = {"detection": detection, "presence": presence, "tracking": tracking,
                         "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                         "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}
        self.landmarker = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO, num_hands=1,
            min_hand_detection_confidence=detection,
            min_hand_presence_confidence=presence,
            min_tracking_confidence=tracking))

        self.stats = _Stats()
        self._lock = threading.Lock()
        self._raw, self._seq, self._seq_read = None, 0, 0
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        cv2 = self.cv2
        last_ts = 0
        while self._running:
            ok, bgr = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            bgr = cv2.flip(bgr, 1)                    # espelho (modo "selfie")
            now = time.monotonic()
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            ts = max(int(now * 1000), last_ts + 1)    # modo VIDEO: tempo estritamente crescente
            last_ts = ts
            t0 = time.perf_counter()
            result = self.landmarker.detect_for_video(
                self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ts)
            inference_ms = 1000 * (time.perf_counter() - t0)
            self.stats.update(now, float(rgb[::8, ::8].mean()), inference_ms)
            raw = result_to_raw(result, now, rgb)
            raw.update(fps=self.stats.fps, brightness=self.stats.brightness,
                       inference_ms=self.stats.inference_ms)
            if raw["world"] is not None:
                draw_skeleton(cv2, rgb, raw["img"])
            with self._lock:
                self._raw = raw
                self._seq += 1

    def latest(self):
        """Último resultado, ou None se não chegou nada novo desde a última chamada."""
        with self._lock:
            if self._seq == self._seq_read:
                return None
            self._seq_read = self._seq
            return self._raw

    def stop(self):
        self._running = False
        self._thread.join(timeout=1.0)
        self.cap.release()
        self.landmarker.close()


def result_to_raw(result, now, rgb):
    """Resultado do MediaPipe -> raw. A imagem foi espelhada antes da detecção,
    e o rótulo descreve a mão como ela aparece na imagem: a mão real é a oposta."""
    h, w = rgb.shape[:2]
    raw = {"t": now, "world": None, "img": None, "confidence": 0.0, "handedness": None,
           "aspect": w / h, "frame": rgb}
    if result.hand_landmarks:
        category = result.handedness[0][0]
        raw.update(
            world=np.array([[p.x, p.y, p.z] for p in result.hand_world_landmarks[0]]),
            img=np.array([[p.x, p.y] for p in result.hand_landmarks[0]]),
            confidence=float(category.score),
            handedness={"Left": "Right", "Right": "Left"}.get(category.category_name))
    return raw


def draw_skeleton(cv2, rgb, img):
    h, w = rgb.shape[:2]
    pts = [(int(x * w), int(y * h)) for x, y in img]
    for i, j in HAND_CONNECTIONS:
        cv2.line(rgb, pts[i], pts[j], (150, 165, 180), 2, cv2.LINE_AA)
    for k, p in enumerate(pts):
        color = (38, 198, 218) if k in FINGERTIPS else (0, 230, 118)
        cv2.circle(rgb, p, 5, color, -1, cv2.LINE_AA)


# =============================================================================
# Arquivos de pontos
# =============================================================================
def save_recording(path, rows, settings=None):
    """rows = raws (só as chaves de FRAME_KEYS e "fase") -> .npz compactado."""
    n = len(rows)
    world = np.full((n, 21, 3), np.nan)
    img = np.full((n, 21, 2), np.nan)
    for i, r in enumerate(rows):
        if r["world"] is not None:
            world[i], img[i] = r["world"], r["img"]
    num = lambda k: np.array([np.nan if r.get(k) is None else r[k] for r in rows], dtype=float)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    np.savez_compressed(       # pontos em float32: precisão de micrômetros, metade do tamanho
        path, t=num("t"), world=world.astype(np.float32), img=img.astype(np.float32),
        confidence=num("confidence"), handedness=np.array([r["handedness"] or "" for r in rows]),
        aspect=num("aspect"), fps=num("fps"), brightness=num("brightness"),
        inference_ms=num("inference_ms"), fase=np.array([r.get("fase") or "" for r in rows]),
        settings=np.array(repr(settings or {})))


def load_recording(path):
    """Arquivo de pontos -> lista de raws (sem imagem), na ordem em que aconteceram."""
    with np.load(path) as f:
        d = {k: f[k] for k in f.files}   # lê cada coluna uma vez: f[k] descompacta o arquivo a cada acesso
    phases = d.get("fase")               # arquivos antigos não têm a fase
    # valor ausente foi gravado como NaN (ex.: a simulação não mede brilho): volta a ser None
    num = lambda k, i: None if np.isnan(d[k][i]) else float(d[k][i])
    rows = []
    for i in range(len(d["t"])):
        present = not np.isnan(d["world"][i, 0, 0])
        rows.append({
            "t": float(d["t"][i]),
            "world": d["world"][i] if present else None,
            "img": d["img"][i] if present else None,
            "confidence": num("confidence", i),
            "handedness": str(d["handedness"][i]) or None,
            "aspect": num("aspect", i),
            "fps": num("fps", i), "brightness": num("brightness", i),
            "inference_ms": num("inference_ms", i), "frame": None,
            "fase": "" if phases is None else str(phases[i]),
        })
    return rows


class ReplaySource:
    """Reproduz um arquivo de pontos respeitando os tempos originais (para a
    interface se comportar como na sessão gravada). Desenha o esqueleto numa
    imagem escura no lugar do vídeo."""

    def __init__(self, path, loop=True):
        self.rows = load_recording(path)
        if not self.rows:
            raise ValueError(f"gravação vazia: {path}")
        self.loop = loop
        self.t0 = time.monotonic()
        self.i = -1
        try:
            import cv2
            self.cv2 = cv2
        except ImportError:
            self.cv2 = None

    def latest(self):
        elapsed = time.monotonic() - self.t0
        start = self.rows[0]["t"]
        j = self.i
        while j + 1 < len(self.rows) and self.rows[j + 1]["t"] - start <= elapsed:
            j += 1
        if j == self.i:
            if self.loop and j == len(self.rows) - 1:
                self.t0, self.i = time.monotonic(), -1     # recomeça
            return None
        self.i = j
        raw = dict(self.rows[j])
        raw["t"] = time.monotonic()
        raw["frame"] = self._draw(raw)
        return raw

    def _draw(self, raw):
        if self.cv2 is None:
            return None
        frame = np.full((480, 640, 3), 38, np.uint8)
        # embaixo: no alto, a legenda da miniatura cobriria o texto
        self.cv2.putText(frame, "GRAVACAO", (20, 460), self.cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                         (120, 130, 140), 2, self.cv2.LINE_AA)
        if raw["img"] is not None:
            draw_skeleton(self.cv2, frame, raw["img"])
        return frame

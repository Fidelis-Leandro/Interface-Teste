"""Paciente simulado (sem câmera), para testar a interface."""

import time

import numpy as np

import capture
import geometria


class DemoHand:
    """Mão virtual que começa com "passinhos de formiguinha" e vai ganhando
    amplitude, para mostrar a escadinha de repetições. Entrega o mesmo
    formato "raw" da câmera."""

    PEAK = [95, 90, 80, 55]     # flexão PIP máxima (°) ao fim da rampa: ind, méd, ane, mín
    THUMB_PEAK = 30

    def __init__(self):
        self.t0 = None             # o relógio da simulação começa no 1º pedido
        self.rng = np.random.default_rng()
        try:
            import cv2
            self.cv2 = cv2
        except ImportError:
            self.cv2 = None

    def latest(self):
        now = time.monotonic()
        if self.t0 is None:
            self.t0 = now
        t = now - self.t0
        raw = {"t": now, "world": None, "img": None, "confidence": 0.0,
               "handedness": None, "aspect": 4 / 3, "frame": None}
        # sem mão no começo e por 1,5 s aos 75 s (para ver os estados)
        if t < 1.5 or 75 < t < 76.5:
            raw["frame"] = self._draw(None)
            return raw
        if t < 5:                                   # mão aberta e parada (calibração)
            flex, thumb = [3, 3, 3, 3], 3
        else:
            ramp = min(1.0, 0.04 + (t - 5) / 45)    # amplitude cresce em ~45 s
            cycle = (1 - np.cos(2 * np.pi * 0.35 * (t - 5))) / 2
            flex = [3 + ramp * p * cycle for p in self.PEAK]
            thumb = 3 + ramp * self.THUMB_PEAK * cycle
        # ruído de 0,15 mm: dá ~1° de tremor no TAM, como medido na webcam real
        world = geometria.build_hand_world(flex, thumb) + self.rng.normal(0, 0.00015, (21, 3))
        img = np.array([0.5 + 0.03 * np.sin(0.4 * t), 0.58]) + world[:, :2] * 2.5
        raw.update(world=world, img=img, confidence=0.95, handedness="Right",
                   frame=self._draw(img))
        return raw

    def _draw(self, img):
        """Imagem "de câmera" sintética: fundo escuro + esqueleto."""
        if self.cv2 is None:
            return None
        frame = np.full((480, 640, 3), 38, np.uint8)
        # embaixo: no alto, a legenda da miniatura ("Câmera · clique para ampliar") cobria o texto
        self.cv2.putText(frame, "SIMULACAO", (20, 460), self.cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                         (120, 130, 140), 2, self.cv2.LINE_AA)
        if img is not None:
            capture.draw_skeleton(self.cv2, frame, img)
        return frame

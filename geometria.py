"""
Geometria da mão: índices e ligações dos 21 pontos do MediaPipe, uma mão
sintética (simulação e testes) e a conversão para a cena 3D.

Pontos do MediaPipe: 0 punho; 1-4 polegar; 5-8 indicador; 9-12 médio;
13-16 anelar; 17-20 mínimo.
"""

import numpy as np

FINGERTIPS = [4, 8, 12, 16, 20]
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # polegar
    (0, 5), (5, 6), (6, 7), (7, 8),          # indicador
    (5, 9), (9, 10), (10, 11), (11, 12),     # médio
    (9, 13), (13, 14), (14, 15), (15, 16),   # anelar
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),  # mínimo + palma
]

# Mão sintética: (ponto da base, posição x/y da base em metros, comprimento das falanges)
_FINGERS = [
    (5, (-0.025, -0.030), (0.040, 0.025, 0.020)),   # indicador
    (9, (0.000, -0.035), (0.045, 0.028, 0.022)),    # médio
    (13, (0.022, -0.030), (0.042, 0.026, 0.020)),   # anelar
    (17, (0.042, -0.020), (0.032, 0.020, 0.018)),   # mínimo
]


def _chain(start, lengths, bends_deg, direction):
    """Cinemática direta de um dedo: soma segmentos, acumulando as dobras."""
    pts, p, theta = [], np.asarray(start, float), 0.0
    for length, bend in zip(lengths, bends_deg):
        theta += np.radians(bend)
        p = p + length * direction(theta)
        pts.append(p)
    return pts


def build_hand_world(flex_fingers, flex_thumb):
    """Os 21 pontos (metros, eixos do MediaPipe) de uma mão com a palma para a
    câmera. flex_fingers = [ind, méd, ane, mín] em graus de flexão da PIP
    (MCP = 60% e DIP = 70% disso); flex_thumb = flexão da IP do polegar."""
    world = np.zeros((21, 3))
    world[0] = [0.0, 0.06, 0.0]                     # punho
    world[1] = [-0.025, 0.04, 0.0]                  # base do polegar

    # Polegar: gira no plano da palma, em direção ao dedo mínimo
    phi0 = np.radians(50)
    thumb_dir = lambda th: np.array([-np.sin(phi0 - th), -np.cos(phi0 - th), 0.0])
    world[2:5] = _chain(world[1], (0.035, 0.030, 0.025), (0, 0.4 * flex_thumb, flex_thumb), thumb_dir)

    # Dedos: curvam em direção à câmera (z negativo = mais perto)
    finger_dir = lambda th: np.array([0.0, -np.cos(th), -np.sin(th)])
    for (base, (x, y), lengths), f in zip(_FINGERS, flex_fingers):
        world[base] = [x, y, 0.0]
        world[base + 1:base + 4] = _chain(world[base], lengths, (0.6 * f, f, 0.7 * f), finger_dir)
    return world


WORLD_SCALE = 10.0            # metros -> unidades da cena 3D (mão ~2 unidades)


def world_to_gl(world):
    """Eixos do MediaPipe (x direita, y baixo, z profundidade) -> eixos da cena
    3D (x, y profundidade, z cima), com a mão um pouco acima da grade."""
    pts = np.column_stack([world[:, 0], world[:, 2], -world[:, 1]]) * WORLD_SCALE
    pts[:, 2] += 1.0
    return pts

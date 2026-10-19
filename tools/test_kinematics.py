"""
Testes do kinematics.py com a mão simulada (sem câmera e sem interface).

  1) mão PARADA com ruído por 60 s -> não pode contar repetições
  2) movimentos pequenos ("formiguinha") acima da sensibilidade -> conta todos
  3) classificação movimento / parcial / completa

    .venv\\Scripts\\python.exe tools\\test_kinematics.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kinematics as kin  # noqa: E402
import geometria  # noqa: E402

FPS = 30
# Ruído dos pontos (m): 0,6 mm = cenário ruim (pouca luz); 0,15 mm ~ webcam
# real com boa luz (~1° de tremor no TAM). Padrão: cenário ruim.
NOISE_M = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0006
print(f"ruído dos pontos: {NOISE_M * 1000:.2f} mm")
rng = np.random.default_rng(1)


def hand(pip_flex, thumb=3.0):
    world = geometria.build_hand_world([pip_flex] * 4, thumb) + rng.normal(0, NOISE_M, (21, 3))
    return kin.joint_angles(world)


# --- calibração com a mão parada ---------------------------------------------
calib = kin.Calibration()
while not calib.done():
    calib.add(hand(3.0))
sens = calib.sensitivity()
print("sensibilidade por dedo:", {kin.SHORT[f]: round(v, 1) for f, v in sens.items()})

# --- 1) 60 s parada ------------------------------------------------------------
s = kin.Session(sens)
for i in range(60 * FPS):
    s.update(hand(3.0), i / FPS)
false = {kin.SHORT[f]: len(tr.reps) for f, tr in s.trackers.items()}
print("1) mão parada 60 s -> repetições contadas:", false,
      "OK" if sum(false.values()) == 0 else "FALHOU")

# --- 2) e 3) amplitudes crescentes ------------------------------------------------
# flexão PIP de pico de cada ciclo; TAM do dedo ~ 2,3x isso (MCP 0,6 + PIP 1 + DIP 0,7)
peaks = [4, 6, 8, 12, 20, 40, 60, 90]
s = kin.Session(sens)
t = 0.0
for peak in peaks:
    for k in range(int(2.0 * FPS)):                  # ciclo de 2 s
        cycle = (1 - np.cos(2 * np.pi * k / (2.0 * FPS))) / 2
        s.update(hand(3.0 + peak * cycle), t)
        t += 1 / FPS
for _ in range(FPS):                                  # 1 s parado no fim
    s.update(hand(3.0), t)
    t += 1 / FPS
tr = s.trackers["index"]
print(f"2) indicador, sensibilidade {tr.sens:.1f}°: {len(peaks)} ciclos feitos, "
      f"{len(tr.reps)} contados")
for r in tr.reps:
    print(f"     amplitude {r.amplitude:5.1f}° -> {r.kind}")

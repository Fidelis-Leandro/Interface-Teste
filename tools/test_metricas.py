"""
Testes das métricas por dedo do kinematics.py (sem câmera, sem interface):
sinal dos ângulos, déficit de extensão, arco, velocidade, ciclo, cadência,
regularidade, variação de amplitude, independência e contribuição.

    .venv\\Scripts\\python.exe tools\\test_metricas.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kinematics as kin  # noqa: E402
import geometria  # noqa: E402

FPS = 30
NOISE_M = 0.00015              # ~1° de tremor no TAM, como na webcam real
rng = np.random.default_rng(3)
ok_all = True


def check(name, cond, detail=""):
    global ok_all
    ok_all &= bool(cond)
    print(f"{'OK    ' if cond else 'FALHOU'} {name} {detail}")


def hand(fingers, thumb, mirror=False, noise=NOISE_M):
    W = geometria.build_hand_world(fingers, thumb) + rng.normal(0, noise, (21, 3))
    if mirror:                                   # geometria de mão do outro lado
        W[:, 0] *= -1
    return W


# --- 1) sinal e plano da flexão ---------------------------------------------
a = kin.joint_angles(hand([30] * 4, 30, noise=0), "Right")
check("flexão de 30° (PIP) dá ângulos positivos", all((a[f] > 0).all() for f in kin.FINGERS),
      f"(indicador MCP/PIP/DIP = {np.round(a['index'], 1)})")
check("PIP do indicador mede a flexão aplicada", abs(a["index"][1] - 30) < 0.5)
check("MCP do indicador = 0,6 x flexão (sem o desvio lateral)", abs(a["index"][0] - 18) < 0.5)
a = kin.joint_angles(hand([-15] * 4, -15, noise=0), "Right")
check("hiperextensão dá ângulos negativos", all((a[f] < 0).all() for f in kin.FINGERS),
      f"(indicador = {np.round(a['index'], 1)})")
a = kin.joint_angles(hand([30] * 4, 30, mirror=True, noise=0), "Left")
check("mão do outro lado (espelhada) também dá flexão positiva",
      all((a[f] > 0).all() for f in kin.FINGERS))
a0 = kin.joint_angles(hand([0] * 4, 0, noise=0), "Right")
check("dedo esticado ~0° (o desvio lateral da base não entra)",
      np.abs(np.concatenate(list(a0.values()))).max() < 0.5,
      f"(maior = {np.abs(np.concatenate(list(a0.values()))).max():.2f}°)")


# --- sessão com ciclos controlados -------------------------------------------
def run(cycles, only_index=False, period=2.0, low=20.0):
    """cycles = flexão PIP de pico de cada ciclo; o dedo não estende abaixo de `low`."""
    cal = kin.Calibration()
    while not cal.done():
        cal.add(kin.joint_angles(hand([low] * 4, low), "Right"))
    s = kin.Session(cal.sensitivity())
    t = 0.0
    for peak in cycles:
        n = int(period * FPS)
        for k in range(n):
            x = low + (peak - low) * (1 - np.cos(2 * np.pi * k / n)) / 2
            fingers = [x, low, low, low] if only_index else [x] * 4
            s.update(kin.joint_angles(hand(fingers, low), "Right"), t)
            t += 1 / FPS
    for _ in range(FPS):
        s.update(kin.joint_angles(hand([low] * 4, low), "Right"), t)
        t += 1 / FPS
    return s


s = run([60] * 8)
tr = s.trackers["index"]
d, arc = tr.deficits(), tr.arcs()
check("déficit de extensão da PIP ~20° (o dedo nunca passou de 20°)", abs(d[1] - 20) < 3,
      f"(MCP/PIP/DIP = {np.round(d, 1)})")
check("arco da PIP ~40° (20° -> 60°)", abs(arc[1] - 40) < 3, f"(arcos = {np.round(arc, 1)})")
exp_active = (np.array([0.6, 1, 0.7]) * 60).sum() - (np.array([0.6, 1, 0.7]) * 20).sum()
# máx e mín vêm do sinal cru (sem suavização): incluem o tremor nos dois
# extremos, ~1-3° a mais por articulação -> tolerância de 12°
check(f"TAM ativo = flexão máx - déficit (~{exp_active:.0f}°, + tremor nos extremos)",
      abs(tr.active_tam() - exp_active) < 12, f"(medido {tr.active_tam():.0f}°)")
q = tr.quality()
amp = (np.array([0.6, 1, 0.7]) * 40).sum()
check("velocidade de flexão ~ amplitude / 1 s", q["flex_velocity"] and abs(q["flex_velocity"] - amp) / amp < 0.25,
      f"(esperado ~{amp:.0f} °/s, medido {q['flex_velocity']:.0f})")
check("velocidade de extensão parecida com a de flexão (ciclo simétrico)",
      q["ext_velocity"] and abs(q["ext_velocity"] - amp) / amp < 0.25, f"(medido {q['ext_velocity']:.0f})")
check("ciclo ~2 s e cadência ~30/min", abs(q["cycle_s"] - 2) < 0.15 and abs(q["cadence"] - 30) < 2.5,
      f"(ciclo {q['cycle_s']:.2f} s, cadência {q['cadence']:.1f}/min)")
check("ritmo constante = Regular", q["regularity"] == "Regular", f"(variação {q['cv'] * 100:.0f}%)")
c = tr.contribution()
check("contribuição MCP/PIP/DIP ~ 26/43/30%", np.abs(c - np.array([0.6, 1, 0.7]) / 2.3).max() < 0.04,
      f"(medido {np.round(c * 100)})")
cp = tr.coupling()
check("dedos longos juntos -> acoplados ~100%; polegar parado ~0%",
      min(cp["middle"], cp["ring"], cp["pinky"]) > 0.8 and cp["thumb"] < 0.1,
      f"({', '.join(f'{kin.SHORT[g]} {v * 100:.0f}%' for g, v in cp.items())};"
      f" independência {tr.independence() * 100:.0f}%)")

s = run([60] * 8, only_index=True)
tr = s.trackers["index"]
check("só o indicador mexendo -> independência alta", tr.independence() > 0.8,
      f"({tr.independence() * 100:.0f}%; outros: "
      + ", ".join(f"{kin.SHORT[g]} {v * 100:.0f}%" for g, v in tr.coupling().items()) + ")")

s = run([90, 85, 80, 70, 60, 50, 45, 40])
q = s.trackers["index"].quality()
check("amplitude caindo -> variação negativa (fadiga)", q["amp_change"] is not None and q["amp_change"] < -0.3,
      f"({q['amp_change'] * 100:+.0f}%)")

print("\nTODOS OK" if ok_all else "\nHÁ FALHAS")

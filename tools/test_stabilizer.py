"""
Testes do stabilizer.py com sequências montadas (30 fps).

    .venv\\Scripts\\python.exe tools\\test_stabilizer.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stabilizer import HOLD_S, HandStabilizer  # noqa: E402

FPS = 30
HAND = np.zeros((21, 3))


def frame(i, hand="Right", present=True):
    return {"t": i / FPS, "world": HAND if present else None, "img": np.zeros((21, 2)) if present else None,
            "handedness": hand if present else None, "aspect": 4 / 3}


def run(seq):
    s = HandStabilizer()
    s.lock(["Right"] * 30)
    return [s.process(f)[1] for f in seq]


ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"{'OK    ' if cond else 'FALHOU'} {name}")


# 1) troca de lado por 3 frames no meio -> segura a pose, nunca "outra_mao"
seq = [frame(i) for i in range(30)] + [frame(30 + i, "Left") for i in range(3)] + \
      [frame(33 + i) for i in range(30)]
states = run(seq)
check("troca de lado de 3 frames vira 'segurando'", states[30:33] == ["segurando"] * 3)
check("depois volta a 'ok'", states[33] == "ok")

# 2) falha curta (5 frames = 0,17 s) -> segurando
seq = [frame(i) for i in range(30)] + [frame(30 + i, present=False) for i in range(5)] + \
      [frame(35 + i) for i in range(10)]
states = run(seq)
check("falha de 0,17 s vira 'segurando'", set(states[30:35]) == {"segurando"})

# 3) falha longa (1 s) -> 'perdida' só depois de HOLD_S
seq = [frame(i) for i in range(30)] + [frame(30 + i, present=False) for i in range(30)]
states = run(seq)
first_lost = states.index("perdida")
check(f"falha longa vira 'perdida' após ~{HOLD_S} s "
      f"(foi após {(first_lost - 30) / FPS:.2f} s)", abs((first_lost - 30) / FPS - HOLD_S) < 0.05)

# 4) outra mão de verdade (2 s com o lado oposto) -> 'outra_mao'
seq = [frame(i) for i in range(30)] + [frame(30 + i, "Left") for i in range(60)]
states = run(seq)
check("lado oposto por 2 s vira 'outra_mao'", states[-1] == "outra_mao")

# 4b) mão de lado (frame detectado, mas inválido para medir) -> 'vista' após HOLD_S
s = HandStabilizer()
s.lock(["Right"] * 30)
states = [s.process(frame(i))[1] for i in range(30)]
states += [s.process(frame(30 + i), valid=False, bad_kind="vista")[1] for i in range(30)]
check("mão de lado por 1 s: 'segurando' e depois 'vista'",
      states[31] == "segurando" and states[-1] == "vista")

# 4c) de lado alternando com frames vazios (como o MediaPipe faz) -> não pisca
s = HandStabilizer()
s.lock(["Right"] * 30)
for i in range(30):
    s.process(frame(i))
states = []
for i in range(45):
    f = frame(30 + i, present=(i % 3 != 2))            # 1 em cada 3 frames vazio
    states.append(s.process(f, valid=False, bad_kind="vista")[1])
after = states[int(HOLD_S * FPS) + 2:]
check(f"de lado com frames vazios no meio: fica 'vista', sem piscar 'perdida' {sorted(set(after))}",
      set(after) == {"vista"})
states = [s.process(frame(75 + i, present=False))[1] for i in range(30)]
check("depois, a mão some de vez por > 0,4 s: vira 'perdida'", states[-1] == "perdida")

# 5) antes de fixar: o nome segue o voto da maioria, não pisca
s = HandStabilizer()
names = []
for i in range(40):
    hand = "Left" if i in (10, 11, 25) else "Right"
    out, _ = s.process(frame(i, hand))
    names.append(out["handedness"])
check("antes da calibração o lado mostrado não pisca", set(names) == {"Right"})

print("\nTODOS OK" if ok else "\nHÁ FALHAS")

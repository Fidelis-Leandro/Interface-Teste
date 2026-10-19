"""
Analisa um arquivo de pontos (dados_locais/pontos/*.npz ou tools/gravacao_referencia.npz)
passando-o pelo mesmo motor da tela de avaliação (app/avaliador.py):

  1) captura: quadros, fps, brilho, quanto a mão foi detectada, falhas
  2) linha do tempo a cada 5 s: fase, mão detectada, movimento, vista da palma
     e repetições contadas
  3) trechos com a mão parada (>= 3 s): repetições contadas ali são falsas
  4) resultado final por dedo

    .venv\\Scripts\\python.exe tools\\analisar_gravacao.py ARQUIVO.npz
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capture  # noqa: E402
import kinematics as kin  # noqa: E402
from app.avaliador import Avaliador  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
rows = capture.load_recording(sys.argv[1])
t = np.array([r["t"] for r in rows])
t0, dur = t[0], t[-1] - t[0]
present = np.array([r["world"] is not None for r in rows])

# 1) captura -------------------------------------------------------------------
print(f"{os.path.basename(sys.argv[1])}: {len(rows)} quadros em {dur:.1f} s ({len(rows) / dur:.1f} fps)")
print(f"  brilho médio {np.nanmean([r['brightness'] for r in rows]):.0f} | mão detectada em "
      f"{100 * present.mean():.1f}% dos quadros")
gaps, start = [], None
for i, p in enumerate(present):
    if not p and start is None:
        start = i
    if p and start is not None:
        gaps.append(t[i] - t[start])
        start = None
print(f"  falhas de detecção: {len(gaps)} | até 0,4 s: {sum(g <= 0.4 for g in gaps)} | "
      f"maior: {max(gaps, default=0):.2f} s")

# o mesmo motor da tela, guardando o que acontece em cada quadro
av = Avaliador()
timeline = []                  # (t, fase, estado, TAM dos dedos ou None, vista ou None, repetições novas)
for r in rows:
    before = sum(len(tr.reps) for tr in av.session.trackers.values())
    phase = av.phase
    passo = av.step(r, r["t"])
    tams = view = None
    if passo.state == "ok":
        a = kin.joint_angles(r["world"], av.stab.hand)
        tams = np.array([a[f].sum() for f in kin.FINGERS])
        view = kin.view_angle(r["world"], av.stab.hand)
    after = sum(len(tr.reps) for tr in av.session.trackers.values())
    timeline.append((r["t"] - t0, phase, passo.state, tams, view, after - before))

# 2) linha do tempo ------------------------------------------------------------
print("\n trecho   | fase        | mão  | movimento* | vista** | repetições")
for a in np.arange(0, dur, 5):
    part = [x for x in timeline if a <= x[0] < a + 5]
    ok = [x for x in part if x[3] is not None]
    phase = max({x[1] for x in part}, key=lambda p: sum(x[1] == p for x in part)) if part else "-"
    reps = sum(x[5] for x in part)
    detected = 100 * np.mean([x[2] in ("ok", "segurando") for x in part]) if part else 0
    if len(ok) > 5:
        X = np.array([x[3] for x in ok])
        motion = np.mean(np.abs(np.diff(X, axis=0)).sum(axis=1)) * len(ok) / 5
        view = np.median([x[4] for x in ok])
        print(f"{a:3.0f}-{a + 5:3.0f}s | {phase:11s} | {detected:3.0f}% | {motion:8.0f}   | {view:5.0f}°  | {reps:4d}")
    else:
        print(f"{a:3.0f}-{a + 5:3.0f}s | {phase:11s} | {detected:3.0f}% | (quase sem mão)")
print("* soma das variações de TAM dos 5 dedos (°/s)   ** 0° = palma de frente, 90° = de lado")

# 3) repetições com a mão parada -------------------------------------------------
ok = [x for x in timeline if x[3] is not None]
T = np.array([x[0] for x in ok])
X = np.array([x[3] for x in ok])
still = np.array([(w := (T >= T[i] - 0.5) & (T <= T[i] + 0.5)).sum() > 10 and X[w].std(axis=0).max() < 2.0
                  for i in range(len(T))])
segments, start = [], None
for i, s in enumerate(still):
    if s and start is None:
        start = i
    if (not s or i == len(still) - 1) and start is not None:
        if T[i] - T[start] >= 3:
            segments.append((T[start], T[i]))
        start = None
print("\nTrechos com a mão parada (>= 3 s):" + ("" if segments else " nenhum"))
for a, b in segments:
    n = sum(x[5] for x in timeline if a <= x[0] <= b)
    print(f"  {a:5.1f}-{b:5.1f} s: repetições contadas = {n}" + ("   <-- FALSAS" if n else "   ok"))

# 4) resultado final -------------------------------------------------------------
res = av.results(rows[-1]["t"], "gravação")
print(f"\nResultado ({res['calibracao']} | confiabilidade {res['confiabilidade']['nivel']} "
      f"{res['confiabilidade']['motivos']}):")
for f in kin.FINGERS:
    d = res["dedos"][f]
    pct = "--" if d["pct_normal"] is None else f"{d['pct_normal'] * 100:.0f}%"
    print(f"  {kin.NAME[f]:9s} {d['movimentos']:3d} movimentos | TAM ativo {pct:>5s} | "
          f"sensibilidade {d['sensibilidade']:.0f}°")

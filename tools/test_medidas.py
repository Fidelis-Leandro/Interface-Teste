"""
Testes das medidas novas (velocidade de pico, suavidade, fadiga, Strickland,
arco funcional, polpa-palma, abertura, tremor, confiabilidade) e da
interpretação (erro de medida por reteste, mudança real, tendência).
Também passa uma gravação real pelo motor (tools/gravacao_referencia.npz, mão
saudável, ou outro arquivo de pontos informado) e mostra as medidas dela.

    .venv\\Scripts\\python.exe tools\\test_medidas.py
    .venv\\Scripts\\python.exe tools\\test_medidas.py dados_locais\\pontos\\sessao_xxx.npz
"""

import datetime
import os
import sys
import tempfile
import types

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capture  # noqa: E402
import kinematics as kin  # noqa: E402
import medidas  # noqa: E402
import geometria  # noqa: E402
import app.simulacao as sim  # noqa: E402
from app.avaliador import Avaliador, analisar  # noqa: E402
from app.dados import interpretacao as interp  # noqa: E402

FPS = 30
rng = np.random.default_rng(3)
failures = []


def check(name, ok, detail=""):
    print(f"[{'ok' if ok else 'FALHOU'}] {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def world(flex, thumb, noise=0.00015):
    return geometria.build_hand_world(flex, thumb) + rng.normal(0, noise, (21, 3))


def run_session(amplitudes, low=5.0, period=2.2, noise=0.00015):
    """Uma repetição por amplitude (PIP do indicador, em graus), em cosseno."""
    s = kin.Session({f: 5.0 for f in kin.FINGERS})
    t = 0.0
    n = int(period * FPS)
    for peak in amplitudes:
        for k in range(n):
            w = (1 - np.cos(2 * np.pi * k / n)) / 2
            flex = [low + (peak - low) * w] * 4
            s.update(kin.joint_angles(world(flex, low, noise), "Right"), t)
            t += 1 / FPS
    return s, t


# ---------------------------------------------------------------- sinal
x = np.linspace(0, 10, 50)
check("derivada de uma reta é exata", np.allclose(kin.derivative(3 * x, fs=1 / (x[1] - x[0])), 3))
tt = np.linspace(0, 1, 31)
bell = 30 * tt ** 2 - 60 * tt ** 3 + 30 * tt ** 4           # velocidade de mínimo jerk
jerky = bell * (1 + 0.6 * np.sin(2 * np.pi * 4 * tt))
s_bell, s_jerky = kin.sparc(bell), kin.sparc(np.abs(jerky))
check("SPARC: movimento em sino é mais suave que com trancos", s_bell > s_jerky,
      f"sino {s_bell:.2f}, trancos {s_jerky:.2f}")
check("SPARC do sino perto de -1,4", -1.8 < s_bell < -1.2, f"{s_bell:.2f}")

# ------------------------------------------- velocidade de pico e suavidade
s, _ = run_session([100] * 8)
tr = s.trackers["index"]
amp = np.mean([r.amplitude for r in tr.reps])
expected = amp * np.pi / 2.2                                  # pico de A(1-cos)/2
q = tr.quality()
check("velocidade de pico ~ A*pi/T", q["peak_velocity"] is not None
      and abs(q["peak_velocity"] / expected - 1) < 0.12,
      f"medida {q['peak_velocity']:.0f}°/s, esperada {expected:.0f}°/s")
check("SPARC de repetições suaves entre -2,2 e -1,2", q["sparc"] is not None and -2.2 < q["sparc"] < -1.2,
      f"{q['sparc']}")
check("sem fadiga: tendências perto de zero", abs(q["amp_trend"]) < 0.05 and abs(q["vel_trend"]) < 0.08,
      f"amplitude {q['amp_trend']:+.3f}, velocidade {q['vel_trend']:+.3f}")
s, _ = run_session(np.linspace(100, 72, 10))
q = s.trackers["index"].quality()
check("fadiga: amplitude caindo ~30% aparece na tendência", -0.40 < q["amp_trend"] < -0.20,
      f"amplitude {q['amp_trend']:+.2f}, velocidade {q['vel_trend']:+.2f}")
s, _ = run_session([9] * 8)                  # PIP 5 -> 9° = ~9° de TAM
check("movimentos pequenos (< 15° de TAM): contados, mas sem velocidade de pico",
      len(s.trackers["index"].reps) >= 6 and s.trackers["index"].quality()["peak_velocity"] is None,
      f"{len(s.trackers['index'].reps)} repetições")

# ------------------------------------------------ consistência do esforço
s, _ = run_session([100] * 8)
q = s.trackers["index"].quality()
check("esforço igual em todas as repetições: consistente", q["effort"] == "Consistente",
      f"variação {q['effort_cv']:.3f}")
s, _ = run_session([100, 50] * 4)            # 5 mais fortes: 4 de 100° e 1 de 50°
q = s.trackers["index"].quality()
check("fechamento máximo alternando 100° e 50°: variável", q["effort"] == "Variável",
      f"variação {q['effort_cv']:.3f}")
s, _ = run_session([100] * 2)
check("menos de 3 repetições: sem consistência do esforço",
      s.trackers["index"].quality()["effort_cv"] is None)

# ------------------------------------------------ repetições fortes
s, _ = run_session([100, 50] * 4)            # 4 fechamentos fortes e 4 fracos
check("repetições fortes: só as perto do melhor fechamento", s.trackers["index"].strong_reps() == 4,
      f"{s.trackers['index'].strong_reps()}")
s, _ = run_session([40] * 6)                 # pouca amplitude, mas sempre igual
check("repetições fortes não dependem do normal (paciente limitado chega à meta)",
      s.trackers["index"].strong_reps() >= kin.EFFORT_TOP_REPS, f"{s.trackers['index'].strong_reps()}")

# ------------------------------------------------ distância da câmera
hand = lambda size: {"img": np.array([[0.5, 0.5]] * 9 + [[0.5, 0.5 - size]] + [[0.5, 0.5]] * 11), "aspect": 4 / 3}
dc = medidas.DistanceCheck()
far = [dc.update(hand(0.08)) for _ in range(medidas.DISTANCE_FRAMES)]
check("mão longe: avisa só depois de meio segundo", far[-2] is None and far[-1] == "longe")
check("mão de volta à distância certa: aviso some na hora", dc.update(hand(0.28)) is None)
check("um quadro só muito perto não avisa", dc.update(hand(0.6)) is None)
dc = medidas.DistanceCheck()
reference = capture.load_recording(os.path.join(os.path.dirname(__file__), "gravacao_referencia.npz"))
warned = sum(dc.update(r) is not None for r in reference)
check("gravação real a ~50 cm: nenhum aviso de distância", warned == 0, f"{warned} quadros com aviso")

# ------------------------------------------------ Strickland / arco funcional
v = medidas.strickland("index", np.array([80, 100, 70.0]), np.array([0, 10, 0.0]))
check("Strickland (100 + 70 - 10) / 175", abs(v - 160 / 175) < 1e-9 and medidas.strickland_grade(v) == "excelente",
      f"{v:.3f}")
check("Strickland não se aplica ao polegar", medidas.strickland("thumb", np.ones(2), np.zeros(2)) is None)
c = medidas.functional_coverage("index", "PIP", 30, 60)
check("arco funcional PIP 30-60° cobre 30/64 da faixa 23-87°", abs(c - 30 / 64) < 1e-9, f"{c:.3f}")
check("arco funcional completo", medidas.functional_coverage("ring", "DIP", 0, 80) == 1.0)

# ------------------------------------------------ polpa-palma e abertura
hm = medidas.HandMeasures()
for flex in (5, 40, 80, 110):
    w = world([flex] * 4, 5, 0)
    hm.add(w, kin.joint_angles(w, "Right"))
r = hm.results()
open_d = medidas.tip_to_palm_cm(world([5] * 4, 5, 0))
check("polpa-palma diminui ao fechar", all(r["polpa_palma_cm"][f] < open_d[f] for f in medidas.TIPS),
      f"aberta {open_d['index']:.1f} cm, fechada {r['polpa_palma_cm']['index']:.1f} cm")
check("abertura dos dedos medida com a mão aberta", None not in r["abertura_dedos"], f"{r['abertura_dedos']}")

# ------------------------------------------------------------------ tremor
def tremor_run(freq, amp_m, slow_flex=0.0):
    tm = medidas.TremorMeter()
    for k in range(20 * FPS):
        t = k / FPS
        flex = 5 + slow_flex * (1 - np.cos(2 * np.pi * 0.35 * t)) / 2   # movimento voluntário lento
        w = world([flex] * 4, 5)
        w[[4, 8, 12, 16, 20], 0] += amp_m * np.sin(2 * np.pi * freq * t)
        tm.add(t, w, kin.joint_angles(w, "Right"))
    return tm.result()


r5 = tremor_run(5.0, 0.0015)
check("tremor de 5 Hz (1,5 mm) detectado perto de 5 Hz", r5["ritmico"] and abs(r5["frequencia_hz"] - 5) <= 0.5,
      f"{r5['frequencia_hz']} Hz, pico {r5['razao_pico']}x, {r5['rms_mm']} mm")
r0 = tremor_run(5.0, 0.0)
check("mão parada sem tremor: nada rítmico", not r0["ritmico"], f"pico {r0['razao_pico']}x, {r0['rms_mm']} mm")
rs = tremor_run(5.0, 0.0, slow_flex=4.0)
check("movimento lento e pequeno (0,35 Hz) não vira tremor", not rs["ritmico"],
      f"{rs['janelas']} janelas, pico {rs['razao_pico']}x")
rb = tremor_run(5.0, 0.0015, slow_flex=4.0)
check("tremor de 5 Hz junto com movimento lento ainda aparece", rb["ritmico"] and abs(rb["frequencia_hz"] - 5) <= 0.5,
      f"{rb['frequencia_hz']} Hz")

# --------------------------------------------------------- confiabilidade
good = medidas.session_reliability(1000, 950, fps=28, brightness=120, view=30, reps=10, duration_s=60)
bad = medidas.session_reliability(1000, 500, fps=28, brightness=40, view=30, reps=10, duration_s=60)
check("confiabilidade alta com boa captura", good["nivel"] == "alta", f"{good['motivos']}")
check("confiabilidade baixa com metade dos quadros e pouca luz", bad["nivel"] == "baixa", f"{bad['motivos']}")

# ---------------------------------------------- erro de medida por reteste
def fake(pct, joint_vals):
    d = {f: {"pct_normal": pct, "articulacoes": [{"nome": n, "min": joint_vals[0], "max": joint_vals[1]}
                                                for n, _ in kin.JOINTS[f]]} for f in kin.FINGERS}
    return {"dedos": d}


diffs = rng.normal(0, 3, 40)
results = []
for k in range(8):
    a = fake(0.5, (10.0, 80.0))
    a["reteste"] = fake(0.5 - diffs[k] / 100, (10.0 - diffs[k + 8], 80.0 - diffs[k + 16]))
    results.append(a)
err = interp.measurement_error(results)
pct_d = np.repeat(diffs[:8], 5)
check("MDC do TAM = 1,96 x desvio das diferenças", abs(err["tam_pp"]["mdc"] - 1.96 * pct_d.std(ddof=1)) < 1e-6,
      f"{err['tam_pp']['mdc']:.2f} pp com {err['tam_pp']['n']} pares")
check("sem retestes: sem estimativa", interp.measurement_error([fake(0.5, (0, 1))])["tam_pp"]["mdc"] is None)
check("mudança real só acima do MDC", interp.change(8, 5) == "melhora" and interp.change(-8, 5) == "piora"
      and interp.change(3, 5) == "estavel" and interp.change(3, None) is None)


def ses(day, pct):
    iso = (datetime.date(2026, 9, 1) + datetime.timedelta(days=day)).isoformat() + "T14:00:00"
    return {"inicio": iso, "resultados": {"dedos": {f: {"pct_normal": pct} for f in kin.FINGERS}}}


up = [ses(7 * k, 0.30 + 0.05 * k) for k in range(5)]
t_up = interp.trend(up, "index", mdc_pp=4)
check("tendência de +5 pp por semana", abs(t_up["pp_semana"] - 5) < 0.01 and not t_up["plato"],
      f"{t_up['pp_semana']:+.1f} pp/semana")
flat = [ses(7 * k, v) for k, v in enumerate((0.30, 0.40, 0.50, 0.51, 0.52))]
check("platô nas últimas 3 avaliações", interp.trend(flat, "index", mdc_pp=4)["plato"])

# tendência da lista de pacientes (média dos 5 dedos, última x penúltima avaliação)
mdc4, no_mdc = {"tam_pp": {"mdc": 4.0}}, {"tam_pp": {"mdc": None}}
check("lista: melhora acima do erro", interp.patient_trend(up, mdc4) == ("melhora", "melhora"))
check("lista: platô", interp.patient_trend(flat, mdc4) == ("platô", "plato"))
check("lista: piora acima do erro", interp.patient_trend([ses(0, 0.5), ses(7, 0.4)], mdc4)[1] == "piora")
check("lista: sem erro estimado mostra só a diferença",
      interp.patient_trend([ses(0, 0.5), ses(7, 0.42)], no_mdc) == ("−8 pp", None))
check("lista: uma avaliação só", interp.patient_trend([ses(0, 0.5)], mdc4) == ("--", None))

# ---------------------------- pontos gravados: recalcular dá o mesmo resultado
clock = [100.0]
sim.time = types.SimpleNamespace(monotonic=lambda: clock[0])   # simulação com relógio controlado
demo = sim.DemoHand()
demo.cv2 = None                                                  # sem desenhar a imagem
demo.rng = np.random.default_rng(5)
live = Avaliador()
for _ in range(30 * FPS):
    raw = demo.latest()                     # a simulação não mede brilho nem fps (None)
    if raw["world"] is not None:            # pontos com a precisão do MediaPipe (float32), como na câmera
        raw["world"] = raw["world"].astype(np.float32).astype(float)
    live.step(raw, raw["t"])
    clock[0] += 1 / FPS
with tempfile.TemporaryDirectory() as tmp:
    capture.save_recording(os.path.join(tmp, "p.npz"), live.frames)
    rows = capture.load_recording(os.path.join(tmp, "p.npz"))
check("pontos gravados: valor ausente volta como ausente", rows[-1]["brightness"] is None and rows[-1]["fps"] is None)
same = lambda res: {k: res[k] for k in ("dedos", "mao_inteira", "confiabilidade")}
check("recalcular a partir dos pontos gravados reproduz a avaliação ao vivo",
      same(live.results(rows[-1]["t"], "")) == same(analisar(rows).results(rows[-1]["t"], "")))

# -------------------------------------------- gravação real (se informada)
RECORDING = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "gravacao_referencia.npz")
if os.path.exists(RECORDING):
    rows = capture.load_recording(RECORDING)
    av = analisar(rows)                        # o mesmo motor da tela de avaliação
    res = av.results(rows[-1]["t"], "gravação")
    rel = res["confiabilidade"]

    def fmt(v, decimals=0, scale=1.0):
        return "--" if v is None else f"{v * scale:.{decimals}f}"

    print(f"\nGravação {os.path.basename(RECORDING)} (mão {res['mao']}, calibração {res['calibracao']}):")
    for f in kin.FINGERS:
        d = res["dedos"][f]
        qq = d["qualidade"]
        cov = " ".join(f"{j['nome']} {fmt(j['arco_funcional'], 0, 100)}%" for j in d["articulacoes"])
        print(f"  {kin.SHORT[f]}: {d['movimentos']:2d} mov | TAM {fmt(d['pct_normal'], 0, 100)}% | "
              f"Strickland {fmt(d['strickland'], 0, 100)}% | polpa-palma {fmt(d['polpa_palma_cm'], 1)} cm | "
              f"pico {fmt(qq['peak_velocity'])}°/s | SPARC {fmt(qq['sparc'], 2)} | "
              f"tend. amp {fmt(qq['amp_trend'], 0, 100)}% vel {fmt(qq['vel_trend'], 0, 100)}% | "
              f"arco funcional: {cov}")
    whole = res["mao_inteira"]
    print(f"  abertura dos dedos {whole['abertura_dedos']} | polegar {whole['abertura_polegar']}°")
    print(f"  tremor: {whole['tremor']}")
    print(f"  confiabilidade: {rel['nivel']} {rel['motivos']} {rel['detalhes']}")
    lim = interp.limitations(res)
    print(f"  limitações apontadas: {lim or 'nenhuma'}")
    check("mão saudável: nenhuma limitação apontada", not lim)

print("\n" + ("Todos os testes passaram." if not failures else f"{len(failures)} falha(s): {failures}"))
sys.exit(1 if failures else 0)

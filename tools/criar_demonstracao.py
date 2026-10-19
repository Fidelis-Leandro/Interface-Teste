"""
Cria 3 pacientes FICTÍCIOS para demonstração, com todos os campos preenchidos,
avaliações semanais, observações do profissional, retestes e uma alta:

  EX-001 (exemplo fictício)  pós-operatório de tendão flexor, 5 avaliações
  João Pereira (fictício)     tendões flexores em zona II do médio e do anelar,
                              8 avaliações (a DIP do anelar fica para trás)
  Maria Souza (fictícia)      fratura do rádio distal, mão esquerda, 9 avaliações,
                              platô e alta

Cada avaliação é uma mão simulada passando pelo MESMO motor da câmera
(app/avaliador.py), com os pontos gravados: relatório, PDF, mapa e "Recalcular
avaliações" funcionam como numa avaliação de verdade. As datas são contadas a
partir de hoje, então a demonstração fica sempre "recente". Rodar de novo não
duplica: pacientes que já existem são pulados.

    .venv\\Scripts\\python.exe tools\\criar_demonstracao.py                (banco padrão)
    .venv\\Scripts\\python.exe tools\\criar_demonstracao.py outro.sqlite   (outro banco; pontos ao lado dele)
"""

import datetime
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import geometria  # noqa: E402
import app.avaliador as avaliador  # noqa: E402
from app.dados.banco import DB_PATH, Banco  # noqa: E402
from app.dados.resultados import mean_pct, retest_summary  # noqa: E402

FPS = 30
rng = np.random.default_rng(16)
TODAY = datetime.date.today()
PRO = "Ft. Ana Ribeiro (fictícia) · CREFITO 00000-F"


def day(days_after, start, hour=14, minute=0):
    """Data e hora `days_after` dias depois de `start` (uma data)."""
    d = start + datetime.timedelta(days=days_after)
    return datetime.datetime(d.year, d.month, d.day, hour, minute)


# ------------------------------------------------------------- mão simulada
def hand_world(fingers, thumb_ip, left):
    """fingers = [(mcp, pip, dip)] x 4 em graus; thumb_ip = flexão da IP do polegar."""
    world = geometria.build_hand_world([0, 0, 0, 0], thumb_ip)
    finger_dir = lambda th: np.array([0.0, -np.cos(th), -np.sin(th)])
    for (base, _, lengths), bends in zip(geometria._FINGERS, fingers):
        world[base + 1:base + 4] = geometria._chain(world[base], lengths, bends, finger_dir)
    world = world + rng.normal(0, 0.00015, (21, 3))    # ruído parecido com o da webcam
    if left:
        world[:, 0] *= -1                                # mão esquerda = espelho da direita
    return world


def frames(p, t0, left):
    """Quadros "de câmera": chegada sem mão, mão aberta e parada (calibração),
    depois abrir e fechar `reps` vezes. A mão some por um instante na 4ª repetição."""
    hand = "Left" if left else "Right"
    low, peak = np.array(p["low"], float), np.array(p["peak"], float)
    th_low, th_peak = p["thumb"]
    rows, t = [], t0

    def add(fingers, thumb, present=True):
        nonlocal t
        raw = {"t": t, "world": None, "img": None, "confidence": 0.0, "handedness": None,
               "aspect": 4 / 3, "fps": float(rng.normal(29, 0.6)), "brightness": float(p.get("luz", 125)),
               "inference_ms": 14.0, "frame": None}
        if present:
            w = hand_world(fingers, thumb, left)
            raw.update(world=w, img=np.array([0.5, 0.58]) + w[:, :2] * 2.5, confidence=0.95, handedness=hand)
        rows.append(raw)
        t += 1 / FPS

    for _ in range(FPS):
        add(None, None, present=False)
    for _ in range(4 * FPS):
        add(low, th_low)
    for c in range(p["reps"]):
        n = int(p["periodo"] * FPS * rng.uniform(0.9, 1.1))
        effort = 1 - abs(rng.normal(0, p["variacao"]))   # o fechamento varia um pouco entre repetições
        for k in range(n):
            w = (1 - np.cos(2 * np.pi * k / n)) / 2 * effort
            add(low + (peak - low) * w, th_low + (th_peak - th_low) * w, present=not (c == 3 and 10 < k < 16))
    for _ in range(FPS):
        add(low, th_low)
    return rows


def evaluate(p, start, left, retest=None):
    """Passa os quadros pelo motor; com `retest`, faz o reteste em seguida (mão reposicionada)."""
    av = avaliador.Avaliador()
    av.started_at = start
    for raw in frames(p, 1000.0, left):
        av.step(raw, raw["t"])
    res = av.results(av.frames[-1]["t"], "simulação")
    if retest:
        again = avaliador.Avaliador(retest=True, frames=av.frames)    # continua os mesmos pontos
        again.started_at = start + datetime.timedelta(minutes=3)
        for raw in frames(dict(p, **retest), av.frames[-1]["t"] + 180, left):
            again.step(raw, raw["t"])
        res["reteste"] = retest_summary(again.results(again.frames[-1]["t"], "simulação"))
    av.write_points(res["pontos"])
    return res


def jitter(p):
    """Reteste: a mão reposicionada muda um pouco a medida."""
    return {"peak": [[v * rng.normal(1, 0.06) for v in f] for f in p["peak"]],
            "low": [[max(0.0, v + rng.normal(0, 3.0)) for v in f] for f in p["low"]]}


def lerp(a, b, x):
    return [[ai + (bi - ai) * x for ai, bi in zip(fa, fb)] for fa, fb in zip(a, b)]


def add_patient(db, data, curve, plan, left=False):
    """curve = flexões no começo e no fim do tratamento; plan = [(quando, progresso 0..1,
    observação, com reteste?, ajustes)]."""
    if any(p["identificacao"] == data["identificacao"] for p in db.pacientes("")):
        print(f"  {data['identificacao']}: já existe, pulado")
        return
    pid = db.salvar_paciente(data)
    for when, x, note, with_retest, extra in plan:
        p = {"peak": lerp(curve["peak0"], curve["peak1"], x), "low": lerp(curve["low0"], curve["low1"], x),
             "thumb": (curve["thumb"][0], curve["thumb"][1] + (curve["thumb"][2] - curve["thumb"][1]) * x),
             "reps": 10, "periodo": 3.0 - 0.9 * x, "variacao": 0.14 - 0.11 * x}
        p.update(extra)
        res = evaluate(p, when, left, jitter(p) if with_retest else None)
        db.salvar_sessao(pid, res, note)
    print(f"  {data['identificacao']}: {len(plan)} avaliações, última com "
          f"{mean_pct(res) * 100:.0f}% do normal")


# ------------------------------------------------------------------ EX-001
EX_INJURY = TODAY - datetime.timedelta(weeks=7)
EX = {"identificacao": "EX-001 (exemplo fictício)", "nascimento": "1971-03-12",
      "mao_dominante": "Direita", "mao_avaliada": "Direita",
      "condicao": "Pós-operatório de tendão flexor (exemplo)", "data_lesao": EX_INJURY.isoformat(),
      "profissional": "Profissional de exemplo", "observacoes": "Paciente fictício gerado para teste."}
EX_CURVE = {"peak0": [(15, 25, 18)] * 4, "peak1": [(51, 85, 60)] * 4,
            "low0": [(14, 14, 14)] * 4, "low1": [(2, 2, 2)] * 4, "thumb": (3, 18, 42)}
EX_PLAN = [(day(21 + 7 * k, EX_INJURY), k / 4, f"Semana {k + 1} de reabilitação (exemplo).", k in (1, 2, 4), {})
           for k in range(5)]

# ------------------------------------------------------------------ João
# Tenorrafia de flexores em zona II do médio e do anelar (mão direita): indicador e
# mínimo quase normais; médio e anelar com PIP e, sobretudo, DIP limitadas.
JOAO_INJURY = TODAY - datetime.timedelta(days=83)
FREE0, FREE1 = (55, 75, 45), (80, 100, 65)
JOAO = {"identificacao": "João Pereira (fictício)", "nascimento": "1992-05-09",
        "mao_dominante": "Direita", "mao_avaliada": "Direita",
        "condicao": "Lesão de tendões flexores em zona II do 3º e 4º dedos (corte com vidro); "
                    "tenorrafia do FDP e FDS",
        "data_lesao": JOAO_INJURY.isoformat(), "profissional": PRO,
        "observacoes": "Marceneiro, destro. Protocolo de mobilização ativa precoce (Saint John) desde a 1ª "
                       "semana; órtese dorsal de bloqueio até a 6ª semana. Queixa de rigidez matinal no anelar. "
                       "Objetivo: voltar a segurar ferramentas (martelo, formão)."}
JOAO_CURVE = {"peak0": [FREE0, (35, 40, 16), (35, 38, 14), FREE0], "peak1": [FREE1, (75, 88, 32), (72, 84, 17), FREE1],
              "low0": [(4, 8, 4), (8, 28, 10), (8, 30, 11), (4, 8, 4)],
              "low1": [(2, 3, 2), (3, 9, 5), (4, 11, 6), (2, 3, 2)], "thumb": (3, 55, 70)}
JOAO_PLAN = [
    (day(30, JOAO_INJURY, 9, 10), 0.00, "4ª semana pós-op. Primeira avaliação por câmera. Edema leve no 3º e 4º "
     "dedos, cicatriz aderida na base do médio. Paciente com medo de fechar a mão; movimento lento. "
     "Mantém órtese de bloqueio.", True, {"reps": 8}),
    (day(37, JOAO_INJURY, 9, 0), 0.18, "5ª semana. Menos edema. Iniciado deslizamento tendíneo e massagem de "
     "cicatriz. DIP do médio e do anelar quase não flexiona ativamente.", False, {}),
    (day(44, JOAO_INJURY, 9, 15), 0.34, "6ª semana. Retirada da órtese. Ganho de flexão da PIP; DIP ainda "
     "limitada. Orientado bloqueio da PIP para exercitar a DIP em casa.", True, {}),
    (day(51, JOAO_INJURY, 9, 5), 0.48, "7ª semana. Boa adesão aos exercícios. Déficit de extensão da PIP do "
     "anelar diminuindo. Sem dor ao fechar.", False, {}),
    (day(58, JOAO_INJURY, 9, 0), 0.62, "8ª semana. Iniciado fortalecimento leve com massinha. Relata conseguir "
     "segurar o celular com a mão direita.", True, {}),
    (day(65, JOAO_INJURY, 9, 20), 0.76, "9ª semana. Fechamento da mão quase completo; DIP do anelar ainda é a "
     "mais limitada. Avaliação feita com pouca luz (janela atrás).", False, {"luz": 70}),
    (day(72, JOAO_INJURY, 9, 0), 0.84, "10ª semana. Movimento mais rápido e regular. Liberado para atividades "
     "leves na marcenaria, sem ferramentas pesadas.", True, {}),
    (day(79, JOAO_INJURY, 9, 10), 1.00, "11ª semana. Mantém ganho. Discutida a alta para as próximas 2 semanas, "
     "se o DIP do anelar continuar progredindo.", False, {"reps": 12}),
]

# ----------------------------------------------------------------- Maria
# Fratura do rádio distal esquerdo, gesso por 6 semanas: rigidez de todos os dedos.
MARIA_INJURY = TODAY - datetime.timedelta(days=129)
MARIA = {"identificacao": "Maria Souza (fictícia)", "nascimento": "1965-03-22",
         "mao_dominante": "Direita", "mao_avaliada": "Esquerda",
         "condicao": "Fratura do rádio distal esquerdo (queda da própria altura), tratamento conservador com "
                     "gesso por 6 semanas; rigidez dos dedos",
         "data_lesao": MARIA_INJURY.isoformat(), "profissional": PRO,
         "observacoes": "Aposentada, destra, mora sozinha. Osteopenia. Chegou com edema de dedos e medo de mexer. "
                        "Objetivo: abrir potes, pentear o cabelo e voltar ao crochê.",
         "situacao": "alta", "data_alta": (MARIA_INJURY + datetime.timedelta(days=119)).isoformat()}
MARIA_CURVE = {"peak0": [(38, 50, 25), (38, 48, 22), (35, 45, 20), (32, 42, 20)],
               "peak1": [(78, 98, 62), (80, 100, 64), (78, 96, 60), (72, 92, 58)],
               "low0": [(12, 22, 10), (12, 24, 10), (14, 25, 12), (14, 24, 12)],
               "low1": [(3, 4, 2), (3, 4, 2), (4, 5, 3), (4, 5, 3)], "thumb": (6, 30, 68)}
MARIA_PLAN = [
    (day(49, MARIA_INJURY, 15, 0), 0.00, "7ª semana (1 semana após retirar o gesso). Edema moderado em todos os "
     "dedos, pele brilhante. Fecha a mão só até a metade. Dor 6/10 ao final do movimento.", True, {"reps": 7}),
    (day(56, MARIA_INJURY, 15, 10), 0.20, "Edema menor após enfaixamento compressivo e elevação. Ainda não "
     "encosta a ponta dos dedos na palma.", False, {}),
    (day(63, MARIA_INJURY, 15, 0), 0.38, "Melhora visível. Iniciados exercícios de pinça com prendedores. "
     "Dor 4/10.", True, {}),
    (day(70, MARIA_INJURY, 15, 5), 0.54, "Fecha a mão com mais facilidade. Polegar ainda limitado para tocar o "
     "dedo mínimo.", False, {}),
    (day(77, MARIA_INJURY, 15, 0), 0.70, "Consegue abrir pote pequeno com ajuda da outra mão. Dor 2/10.", True, {}),
    (day(91, MARIA_INJURY, 15, 0), 0.84, "Intervalo de 2 semanas (viagem). Manteve os exercícios em casa e "
     "ganhou amplitude.", False, {}),
    (day(105, MARIA_INJURY, 15, 20), 0.96, "Quase todo o arco funcional atingido. Voltou ao crochê por 20 "
     "minutos por dia.", True, {}),
    (day(112, MARIA_INJURY, 15, 0), 0.985, "Sem queixas funcionais. Medidas parecidas com as da avaliação "
     "anterior.", False, {"reps": 12}),
    (day(119, MARIA_INJURY, 15, 0), 1.00, "Alta. Medidas estáveis nas 3 últimas avaliações (platô). Orientado "
     "programa de exercícios domiciliares e retorno se houver perda de movimento.", True, {"reps": 12}),
]


def main(db_path=DB_PATH):
    if db_path != DB_PATH:                       # outro banco: pontos numa pasta ao lado dele
        avaliador.POINTS_DIR = os.path.join(os.path.dirname(os.path.abspath(db_path)), "pontos")
    db = Banco(db_path)
    print("Criando pacientes fictícios de demonstração (leva cerca de 1 minuto)...")
    add_patient(db, EX, EX_CURVE, EX_PLAN)
    add_patient(db, JOAO, JOAO_CURVE, JOAO_PLAN)
    add_patient(db, MARIA, MARIA_CURVE, MARIA_PLAN, left=True)
    print(f"Pronto: {db_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DB_PATH)

"""
Resultado de uma sessão como dicionário simples (números, textos e listas).
É o mesmo formato que vai para o banco (JSON), para o relatório e para o CSV,
então uma sessão salva semanas atrás é lida exatamente como uma recém-feita.
"""

import csv

import kinematics as kin
import medidas

# 2: medidas novas (arco funcional, Strickland, polpa-palma, velocidade de pico,
#    suavidade, tendências, mão inteira, tremor, confiabilidade, pontos gravados).
#    Sessões da versão 1 continuam legíveis: todo campo novo é opcional na leitura.
VERSION = 2
HAND_NAMES = {"Right": "Mão direita", "Left": "Mão esquerda"}
CALIBRATION_NAMES = {"completa": "medida na calibração",
                     "aproximada": "aproximada (a mão não ficou parada)",
                     "padrao": "valor padrão (sem calibração)"}


def finger_results(tr, tpd=None):
    """FingerTracker -> dicionário do dedo (também usado no reteste)."""
    counts = tr.counts()
    deficits, arcs, contrib = tr.deficits(), tr.arcs(), tr.contribution()

    def at(arr, i):
        return None if arr is None else float(arr[i])

    joints = []
    for i, n in enumerate(tr.joint_names):
        mn, mx = at(tr.min_joints, i), at(tr.max_joints, i)
        joints.append({"nome": n, "min": mn, "max": mx, "deficit": at(deficits, i), "arco": at(arcs, i),
                       "contribuicao": at(contrib, i), "normal": float(tr.normal_joints[i]),
                       "arco_funcional": medidas.functional_coverage(tr.finger, n, mn, mx)})
    active = tr.active_tam()
    return {
        "movimentos": sum(counts.values()), "parciais": counts["parcial"],
        "completas": counts["completa"],
        "tam_ativo": None if active is None else max(0.0, active),
        "pct_normal": tr.percent_normal(), "tam_max": tr.max_tam, "normal": float(tr.normal),
        "articulacoes": joints, "independencia": tr.independence(),
        "acoplamento": tr.coupling(), "qualidade": tr.quality(),
        "strickland": medidas.strickland(tr.finger, tr.max_joints, deficits),
        "polpa_palma_cm": tpd,
        "amplitudes": [round(float(r.amplitude), 1) for r in tr.reps],
        "tipos": [r.kind for r in tr.reps], "sensibilidade": float(tr.sens),
    }


def session_results(session, *, start, duration_s, hand, calibrated, source,
                    hand_measures=None, tremor=None, reliability=None, points=None):
    """kinematics.Session + dados da sessão -> dicionário serializável em JSON."""
    calib = {True: "completa", "aproximada": "aproximada", False: "padrao"}[calibrated]
    whole = hand_measures.results() if hand_measures is not None else None
    tpd = (whole or {}).get("polpa_palma_cm", {})
    fingers = {f: finger_results(session.trackers[f], tpd.get(f)) for f in kin.FINGERS}
    if whole is not None:
        whole = {k: v for k, v in whole.items() if k != "polpa_palma_cm"}   # já vai em cada dedo
        whole["tremor"] = tremor.result() if tremor is not None else None
    return {"versao": VERSION, "inicio": start.isoformat(timespec="seconds"),
            "duracao_s": int(duration_s), "mao": hand, "calibracao": calib, "fonte": source,
            "pontos": points, "descartados": int(session.discarded),
            "confiabilidade": reliability, "mao_inteira": whole, "dedos": fingers}


def retest_summary(results):
    """Só o que o reteste precisa guardar: flexões máx./mín. e TAM de cada dedo."""
    return {"inicio": results["inicio"], "duracao_s": results["duracao_s"],
            "confiabilidade": results.get("confiabilidade"),
            "dedos": {f: {"tam_ativo": d["tam_ativo"], "pct_normal": d["pct_normal"],
                          "articulacoes": [{"nome": j["nome"], "min": j["min"], "max": j["max"]}
                                           for j in d["articulacoes"]]}
                      for f, d in results["dedos"].items()}}


def mean_pct(results):
    """% do normal médio dos dedos com dado (None se nenhum)."""
    vals = [d["pct_normal"] for d in results["dedos"].values() if d["pct_normal"] is not None]
    return sum(vals) / len(vals) if vals else None


def total_moves(results):
    return sum(d["movimentos"] for d in results["dedos"].values())


def deficit_total(finger):
    vals = [j["deficit"] for j in finger["articulacoes"] if j["deficit"] is not None]
    return sum(vals) if vals else None


def csv_num(v, decimals=0):
    """Número para CSV em português: vírgula decimal, vazio se não houver."""
    if v is None:
        return ""
    v = round(float(v), decimals) + 0.0              # + 0.0 tira o "-0"
    return f"{v:.{decimals}f}".replace(".", ",")


def write_csv(path, results, patient=None):
    """CSV com ';', vírgula decimal e BOM: abre direto no Excel em português."""
    num = csv_num
    whole = results.get("mao_inteira") or {}
    tremor = whole.get("tremor") or {}
    rel = results.get("confiabilidade") or {}
    spread = whole.get("abertura_dedos") or [None, None, None]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        if patient:
            w.writerow(["paciente", patient.get("identificacao", "")])
        w.writerow(["inicio", results["inicio"]])
        w.writerow(["mao", HAND_NAMES.get(results["mao"], "")])
        w.writerow(["duracao_s", results["duracao_s"]])
        w.writerow(["quadros_descartados_medida_impossivel", results["descartados"]])
        w.writerow(["confiabilidade", rel.get("nivel", ""), " / ".join(rel.get("motivos", []))])
        w.writerow(["abertura_ind_med_graus", num(spread[0]), "abertura_med_ane_graus", num(spread[1]),
                    "abertura_ane_min_graus", num(spread[2])])
        w.writerow(["abertura_polegar_graus", num(whole.get("abertura_polegar"))])
        w.writerow(["tremor_ritmico", "sim" if tremor.get("ritmico") else "nao",
                    "tremor_frequencia_hz", num(tremor.get("frequencia_hz"), 1),
                    "tremor_rms_mm", num(tremor.get("rms_mm"), 2)])
        w.writerow([])
        w.writerow(CSV_HEADER)
        for f in kin.FINGERS:
            w.writerow(finger_row(f, results["dedos"][f], num))


SLOTS = [("mcp", ("MCP",)), ("pip_ou_ip", ("PIP", "IP")), ("dip", ("DIP",))]
CSV_HEADER = (["dedo", "movimentos", "parciais", "completas", "tam_ativo", "pct_normal",
               "tam_max_simultaneo"]
              + [f"{slot}_{k}" for slot, _ in SLOTS
                 for k in ("flexao_max", "flexao_min", "deficit_extensao", "arco", "contribuicao_pct",
                           "arco_funcional_pct")]
              + ["strickland_pct", "polpa_palma_cm", "independencia_pct", "vel_flexao_media",
                 "vel_extensao_media", "vel_pico_media", "suavidade_sparc", "ciclo_s",
                 "cadencia_por_min", "regularidade", "variacao_ciclo_pct", "variacao_amplitude_pct",
                 "tendencia_amplitude_pct", "tendencia_velocidade_pct", "consistencia_esforco_pct",
                 "amplitude_primeira", "amplitude_ultima", "sensibilidade"])


def finger_row(f, d, num=csv_num):
    """Uma linha do CSV (colunas de CSV_HEADER) para o dedo f."""
    pct = lambda v: None if v is None else v * 100
    q = d["qualidade"]
    amps = d["amplitudes"]
    line = [kin.NAME[f], d["movimentos"], d["parciais"], d["completas"], num(d["tam_ativo"]),
            num(pct(d["pct_normal"])), num(d["tam_max"])]
    by_name = {j["nome"]: j for j in d["articulacoes"]}
    for _, names in SLOTS:
        j = next((by_name[n] for n in names if n in by_name), {})
        line += [num(j.get("max")), num(j.get("min")), num(j.get("deficit")), num(j.get("arco")),
                 num(pct(j.get("contribuicao"))), num(pct(j.get("arco_funcional")))]
    line += [num(pct(d.get("strickland"))), num(d.get("polpa_palma_cm"), 1), num(pct(d["independencia"])),
             num(q["flex_velocity"]), num(q["ext_velocity"]), num(q.get("peak_velocity")),
             num(q.get("sparc"), 2), num(q["cycle_s"], 2), num(q["cadence"], 1), q["regularity"] or "",
             num(pct(q["cv"])), num(pct(q["amp_change"])), num(pct(q.get("amp_trend"))),
             num(pct(q.get("vel_trend"))), num(pct(q.get("effort_cv"))), num(amps[0] if amps else None),
             num(amps[-1] if amps else None), num(d["sensibilidade"], 1)]
    return line

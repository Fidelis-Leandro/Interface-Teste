"""
Interpretação dos resultados, por regras explícitas (apoio à decisão, não diagnóstico).

  - erro de medida do sistema, estimado pelos retestes (mesma avaliação repetida
    logo em seguida, com a mão reposicionada): MDC95 = 1,96 x desvio padrão das
    diferenças teste - reteste (= 1,96 x raiz(2) x EPM)
  - mudança real entre duas avaliações: maior que o MDC
  - tendência ao longo das avaliações e platô
  - limitações da última avaliação (arco funcional, DIP que não acompanha a PIP,
    dedo que não se move isoladamente)
  - resumo clínico em frases curtas para a ficha
"""

import datetime

import numpy as np

import kinematics as kin
import medidas
from app.dados.resultados import mean_pct
from app.formato import fmt_date

MIN_PAIRS = 10                 # pares teste-reteste para estimar o erro
TREND_MIN_SESSIONS = 4
PLATEAU_SESSIONS = 3
OVERDUE_DAYS = 21             # em tratamento e sem avaliação há mais que isso: destaque na lista
LONG = kin.FINGERS[1:]


# =============================================================================
# Erro de medida (teste-reteste)
# =============================================================================
def measurement_error(all_results):
    """all_results = resultados de todas as sessões do banco (qualquer paciente).
    Devolve {"retestes": n, "articulacao": {...} | None, "tam_pp": {...} | None},
    cada item com n de pares, MDC e viés médio (teste - reteste)."""
    joint_diffs, pct_diffs, retests = [], [], 0
    for res in all_results:
        rt = res.get("reteste")
        if not rt:
            continue
        # captura ruim no teste ou no reteste não entra: um par ruim infla o erro de todos
        if "baixa" in ((res.get("confiabilidade") or {}).get("nivel"),
                       (rt.get("confiabilidade") or {}).get("nivel")):
            continue
        retests += 1
        for f in kin.FINGERS:
            a, b = res["dedos"][f], rt["dedos"].get(f)
            if not b:
                continue
            if a["pct_normal"] is not None and b["pct_normal"] is not None:
                pct_diffs.append((a["pct_normal"] - b["pct_normal"]) * 100)
            for ja, jb in zip(a["articulacoes"], b["articulacoes"]):
                for k in ("max", "min"):
                    if ja[k] is not None and jb[k] is not None:
                        joint_diffs.append(ja[k] - jb[k])

    def estimate(diffs):
        if len(diffs) < MIN_PAIRS:
            return {"n": len(diffs), "mdc": None, "vies": None}
        d = np.asarray(diffs)
        return {"n": len(d), "mdc": float(1.96 * d.std(ddof=1)), "vies": float(d.mean())}

    return {"retestes": retests, "articulacao": estimate(joint_diffs), "tam_pp": estimate(pct_diffs)}


def retest_difference(results):
    """Diferença média absoluta (°) entre teste e reteste nas articulações."""
    rt = results.get("reteste")
    if not rt:
        return None
    diffs = [abs(ja[k] - jb[k]) for f in kin.FINGERS
             for ja, jb in zip(results["dedos"][f]["articulacoes"], rt["dedos"][f]["articulacoes"])
             for k in ("max", "min") if ja[k] is not None and jb[k] is not None]
    return (float(np.mean(diffs)), len(diffs)) if diffs else None


def change(delta, mdc):
    """'melhora' | 'piora' | 'estavel' (dentro do erro) | None (sem erro estimado)."""
    if delta is None or mdc is None:
        return None
    return "melhora" if delta > mdc else "piora" if delta < -mdc else "estavel"


# =============================================================================
# Medidas derivadas das sessões salvas (inclusive as da versão 1)
# =============================================================================
def finger_strickland(f, d):
    if d.get("strickland") is not None:
        return d["strickland"]
    maxs = [j["max"] for j in d["articulacoes"]]
    defs = [j["deficit"] for j in d["articulacoes"]]
    if None in maxs or None in defs:
        return None
    return medidas.strickland(f, np.array(maxs), np.array(defs))


def joint_coverage(f, j):
    v = j.get("arco_funcional")
    return v if v is not None else medidas.functional_coverage(f, j["nome"], j["min"], j["max"])


def _date(iso):
    return datetime.date.fromisoformat(iso[:10])


def _ddmm(iso):
    return fmt_date(iso)[:5]


# =============================================================================
# Tendência
# =============================================================================
def trend(sessions, finger, mdc_pp=None):
    """sessions em ordem cronológica. Devolve {"pp_semana", "plato", "n"} ou None."""
    pts = [(s["inicio"], s["resultados"]["dedos"][finger]["pct_normal"]) for s in sessions]
    pts = [(iso, v * 100) for iso, v in pts if v is not None]
    if len(pts) < TREND_MIN_SESSIONS:
        return None
    pts = pts[-5:]
    days = np.array([(_date(iso) - _date(pts[0][0])).days for iso, _ in pts], dtype=float)
    vals = np.array([v for _, v in pts])
    slope = float(np.polyfit(days, vals, 1)[0]) * 7 if np.ptp(days) > 0 else None
    last = vals[-PLATEAU_SESSIONS:]
    plateau = None if mdc_pp is None else bool(np.ptp(last) <= mdc_pp)
    return {"pp_semana": slope, "plato": plateau, "n": len(pts)}


TREND_WORDS = {"melhora": "melhora", "piora": "piora", "estavel": "estável", "plato": "platô"}


def patient_trend(sessions, error):
    """Tendência do paciente pelo % do normal médio dos 5 dedos (lista de pacientes).
    Devolve (texto, tipo): tipo = "melhora" | "piora" | "estavel" | "plato" | None.
    Usa o erro de medida de um dedo para a média dos cinco: fica do lado cauteloso.
    Sem erro estimado (poucos retestes), mostra só a diferença em pp."""
    vals = [mean_pct(s["resultados"]) for s in sessions]
    vals = [v * 100 for v in vals if v is not None]
    if len(vals) < 2:
        return "--", None
    mdc = error["tam_pp"]["mdc"]
    delta = vals[-1] - vals[-2]
    if mdc is None:
        return f"{'+' if delta >= 0 else '−'}{abs(delta):.0f} pp", None
    if len(vals) >= PLATEAU_SESSIONS and np.ptp(vals[-PLATEAU_SESSIONS:]) <= mdc:
        return TREND_WORDS["plato"], "plato"
    kind = change(delta, mdc)
    return TREND_WORDS[kind], kind


# =============================================================================
# Limitações de uma avaliação
# =============================================================================
DIP_SHARE_RATIO = 0.4          # DIP com menos de 40% da participação normal no movimento
MIN_PIP_ARC = 30.0
ISOLATED_OK, ISOLATED_LOW = 0.6, 0.3


def limitations(results):
    """Frases curtas (texto simples) sobre a avaliação, só com regras que não
    marcaram limitação na gravação de uma mão saudável."""
    out = []
    # arco funcional não alcançado
    missing, total = [], 0
    for f in LONG:
        for j in results["dedos"][f]["articulacoes"]:
            cov = joint_coverage(f, j)
            if cov is None:
                continue
            total += 1
            if cov < 0.9:
                lo, hi = medidas.functional_range(f, j["nome"])
                missing.append((f, j["nome"], j["max"] < hi, j["min"] > lo))
    if missing:
        flex = sum(m[2] for m in missing)
        ext = sum(m[3] for m in missing)
        why = ("falta flexão" if not ext else "falta extensão" if not flex
               else f"falta flexão em {flex}, extensão em {ext}")
        if len(missing) > 4:                       # muitas: só a contagem
            out.append(f"Ainda fora do arco funcional: {len(missing)} de {total} articulações dos "
                       f"dedos longos ({why}).")
        else:
            names = ", ".join(f"{n} do {kin.NAME[f].lower()}" for f, n, _, _ in missing)
            out.append(f"Fora do arco funcional: {names} ({why}).")
    # DIP que não acompanha a PIP
    for f in LONG:
        d = results["dedos"][f]
        by = {j["nome"]: j for j in d["articulacoes"]}
        dip, pip = by["DIP"], by["PIP"]
        ref = kin.NORMAL_JOINT[f]["DIP"] / kin.normal_tam(f)
        if (d["movimentos"] >= 3 and dip["contribuicao"] is not None and pip["arco"] is not None
                and pip["arco"] >= MIN_PIP_ARC and dip["contribuicao"] < DIP_SHARE_RATIO * ref):
            out.append(f"No {kin.NAME[f].lower()}, a DIP se move pouco em relação à PIP "
                       f"({dip['contribuicao'] * 100:.0f}% do movimento; o normal é ~{ref * 100:.0f}%): "
                       "sugere déficit do flexor profundo.")
    # dedo que não se move isoladamente (só se outro dedo conseguiu)
    ind = {f: results["dedos"][f]["independencia"] for f in LONG}
    known = {f: v for f, v in ind.items() if v is not None}
    if known and max(known.values()) >= ISOLATED_OK:
        low = [kin.NAME[f].lower() for f, v in known.items() if v < ISOLATED_LOW]
        if low:
            out.append(f"Não se move isoladamente (os outros dedos acompanham): {', '.join(low)}.")
    return out


# =============================================================================
# Resumo clínico (ficha)
# =============================================================================
def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def clinical_summary(sessions, error):
    """Frases (texto rico simples) sobre a evolução do paciente."""
    if not sessions:
        return []
    last = sessions[-1]["resultados"]
    out = []
    pct = _mean([d["pct_normal"] for d in last["dedos"].values()])
    stk = _mean([finger_strickland(f, last["dedos"][f]) for f in LONG])
    line = f"Última avaliação ({_ddmm(last['inicio'])}): TAM ativo médio de "
    line += "--" if pct is None else f"<b>{pct * 100:.0f}%</b> do normal"
    if stk is not None:
        line += f"; Strickland médio dos dedos longos <b>{stk * 100:.0f}%</b> ({medidas.strickland_grade(stk)})"
    out.append(line + ".")

    mdc = (error.get("tam_pp") or {}).get("mdc")
    if len(sessions) >= 2:
        prev = sessions[-2]["resultados"]
        deltas = []
        for f in kin.FINGERS:
            a, b = last["dedos"][f]["pct_normal"], prev["dedos"][f]["pct_normal"]
            if a is not None and b is not None:
                deltas.append((f, (a - b) * 100))
        since = f"Desde {_ddmm(prev['inicio'])}: "
        if mdc is None:
            shown = sorted(deltas, key=lambda x: -abs(x[1]))[:3]
            out.append(since + ", ".join(f"{kin.NAME[f].lower()} {d:+.0f} pp" for f, d in shown)
                       + " (ainda sem estimativa do erro de medida).")
        else:
            up = [f"{kin.NAME[f].lower()} ({d:+.0f} pp)" for f, d in deltas if change(d, mdc) == "melhora"]
            down = [f"{kin.NAME[f].lower()} ({d:+.0f} pp)" for f, d in deltas if change(d, mdc) == "piora"]
            parts = []
            if up:
                parts.append("melhora real em " + ", ".join(up))
            if down:
                parts.append("<b>piora real</b> em " + ", ".join(down))
            out.append(since + ("; ".join(parts) if parts else "nenhuma mudança além do erro de medida")
                       + f" (erro de medida: ±{mdc:.0f} pp).")

    trends = {f: trend(sessions, f, mdc) for f in kin.FINGERS}
    slopes = [t["pp_semana"] for t in trends.values() if t and t["pp_semana"] is not None]
    if slopes:
        n = max(t["n"] for t in trends.values() if t)
        rate = f"{np.mean(slopes):+.1f}".replace(".", ",")
        out.append(f"Nas últimas {n} avaliações, variação média de {rate} pp por semana.")
        flat = [kin.NAME[f].lower() for f, t in trends.items() if t and t["plato"]]
        if flat:
            out.append(f"Platô nas últimas {PLATEAU_SESSIONS} avaliações: {', '.join(flat)}.")
    out += limitations(last)
    rel = last.get("confiabilidade")
    if rel and rel["nivel"] == "baixa":
        out.append(f"<b>Atenção</b>: a última avaliação teve confiabilidade baixa "
                   f"({', '.join(rel['motivos'][:2])}); interprete com cautela.")
    return out


def error_note(error):
    """Uma linha sobre o erro de medida estimado (ou o que falta para estimar)."""
    j, t = error["articulacao"], error["tam_pp"]
    if j["mdc"] is not None and t["mdc"] is not None:
        return (f"Erro de medida estimado por {error['retestes']} retestes: ±{j['mdc']:.0f}° por "
                f"articulação e ±{t['mdc']:.0f} pp no TAM. Mudanças menores que isso podem ser só erro.")
    return (f"Sem reteste suficiente para estimar o erro de medida ({t['n']} de {MIN_PAIRS} pares de "
            "dedos; cada reteste soma 5). Faça o reteste pelo relatório, logo após avaliar.")

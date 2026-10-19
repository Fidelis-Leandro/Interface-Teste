"""
Exportação para pesquisa: todas as avaliações de todos os pacientes num CSV
"longo" (uma linha por avaliação x dedo), mais o dicionário de dados.
CSV com ';', vírgula decimal e BOM (abre direto no Excel em português; no R:
read.csv2; no pandas: sep=';', decimal=',').
"""

import csv
import datetime
import os

import kinematics as kin
from app.dados.resultados import CALIBRATION_NAMES, CSV_HEADER, SLOTS, csv_num, finger_row
from app.formato import age_from

HAND = {"Right": "direita", "Left": "esquerda"}

SESSION_COLUMNS = [
    ("paciente_id", "Número interno do paciente no banco", ""),
    ("paciente_codigo", "Identificação do paciente (FICTÍCIA nesta versão de teste)", ""),
    ("idade_anos", "Idade na data da avaliação", "anos"),
    ("mao_dominante", "Mão dominante (cadastro)", ""),
    ("mao_avaliada", "Mão avaliada (cadastro)", ""),
    ("condicao", "Condição / diagnóstico (cadastro)", ""),
    ("dias_desde_lesao", "Dias entre a lesão ou cirurgia e a avaliação", "dias"),
    ("sessao_id", "Número interno da avaliação", ""),
    ("data", "Data e hora de início da avaliação", "aaaa-mm-ddThh:mm:ss"),
    ("duracao_s", "Tempo de avaliação (sem pausas)", "s"),
    ("mao_medida", "Mão detectada pela câmera", ""),
    ("calibracao", "Como a sensibilidade foi obtida", ""),
    ("confiabilidade", "Confiabilidade da captura: alta, media ou baixa", ""),
    ("confiabilidade_motivos", "Motivos quando não é alta", ""),
    ("quadros_validos_pct", "Quadros da avaliação com medida válida", "%"),
    ("quadros_descartados", "Quadros descartados por ângulo impossível", "quadros"),
    ("tem_reteste", "A avaliação tem reteste (medição repetida logo depois)", "sim/nao"),
    ("arquivo_pontos", "Arquivo com os pontos da mão de cada quadro (.npz, pasta do projeto)", ""),
    ("abertura_ind_med", "Abertura máxima entre indicador e médio (MCP < 30°)", "graus"),
    ("abertura_med_ane", "Abertura máxima entre médio e anelar", "graus"),
    ("abertura_ane_min", "Abertura máxima entre anelar e mínimo", "graus"),
    ("abertura_total", "Soma das três aberturas", "graus"),
    ("abertura_polegar", "Ângulo máximo entre os metacarpos do polegar e do indicador", "graus"),
    ("tremor_ritmico", "Oscilação rítmica com a mão parada (pico >= 4x a mediana do espectro 3-12 Hz)", "sim/nao"),
    ("tremor_frequencia_hz", "Frequência da oscilação rítmica", "Hz"),
    ("tremor_rms_mm", "Variação (RMS) das pontas dos dedos com a mão parada; inclui ~1 mm de ruído", "mm"),
    ("tremor_segundos", "Tempo com a mão parada analisado", "s"),
]

FINGER_DESCRIPTIONS = {
    "dedo": ("Dedo", ""),
    "movimentos": ("Repetições contadas (qualquer amplitude acima da sensibilidade)", "repetições"),
    "parciais": ("Repetições com amplitude >= 25% do TAM normal e < 75%", "repetições"),
    "completas": ("Repetições com amplitude >= 75% do TAM normal", "repetições"),
    "tam_ativo": ("TAM ativo = soma das flexões máximas - soma dos déficits de extensão", "graus"),
    "pct_normal": ("TAM ativo em % do normal da literatura (260° dedos longos, 140° polegar)", "%"),
    "tam_max_simultaneo": ("Maior soma das flexões num mesmo instante", "graus"),
    "flexao_max": ("Maior flexão da articulação na avaliação", "graus"),
    "flexao_min": ("Menor flexão (= extensão máxima; negativo = hiperextensão)", "graus"),
    "deficit_extensao": ("Déficit de extensão (menor flexão acima de 3°)", "graus"),
    "arco": ("Arco de movimento = flexão máxima - mínima", "graus"),
    "contribuicao_pct": ("Participação da articulação no movimento das repetições", "%"),
    "arco_funcional_pct": ("Parte da faixa funcional coberta (Bain 2015: MCP 19-71, PIP 23-87, DIP 10-64)", "%"),
    "strickland_pct": ("Strickland: (flexão PIP + DIP - déficits) / 175°", "%"),
    "polpa_palma_cm": ("Menor distância estimada da ponta do dedo à palma (escala de mão média)", "cm"),
    "independencia_pct": ("Quanto os outros dedos ficaram parados enquanto este se movia", "%"),
    "vel_flexao_media": ("Amplitude / tempo de subida, média das últimas 10 repetições", "graus/s"),
    "vel_extensao_media": ("Amplitude da volta / tempo de descida, média das últimas 10", "graus/s"),
    "vel_pico_media": ("Maior velocidade na flexão (derivada em 5 quadros), média das últimas 10 >= 15°", "graus/s"),
    "suavidade_sparc": ("SPARC (Balasubramanian 2015); mais perto de 0 = mais suave", "adimensional"),
    "ciclo_s": ("Mediana do tempo entre inícios de repetições (últimas 10)", "s"),
    "cadencia_por_min": ("Repetições por minuto pelo ciclo", "repetições/min"),
    "regularidade": ("Regular (variação do ciclo < 15%), Moderada (< 30%) ou Irregular", ""),
    "variacao_ciclo_pct": ("Coeficiente de variação do ciclo", "%"),
    "variacao_amplitude_pct": ("Média das 3 últimas amplitudes vs. 3 primeiras", "%"),
    "tendencia_amplitude_pct": ("Variação da amplitude do início ao fim pela reta de regressão", "%"),
    "tendencia_velocidade_pct": ("Variação da velocidade de flexão do início ao fim pela reta", "%"),
    "consistencia_esforco_pct": ("Variação (CV) do TAM no pico entre as 5 repetições mais fortes", "%"),
    "amplitude_primeira": ("Amplitude da primeira repetição", "graus"),
    "amplitude_ultima": ("Amplitude da última repetição", "graus"),
    "sensibilidade": ("Menor movimento contado (3x o tremor medido na calibração)", "graus"),
}

RETEST_COLUMNS = [("reteste_pct_normal", "TAM ativo do reteste em % do normal", "%"),
                  ("reteste_tam_ativo", "TAM ativo do reteste", "graus")]


def _finger_descriptions():
    rows = []
    for col in CSV_HEADER:
        key = next((k for k in FINGER_DESCRIPTIONS if col == k or col.endswith("_" + k)), None)
        desc, unit = FINGER_DESCRIPTIONS[key]
        slot = next((names for s, names in SLOTS if col.startswith(s + "_")), None)
        if slot:
            desc = f"{'/'.join(slot)}: {desc}"
        rows.append((col, desc, unit))
    return rows


def export_research(db, folder):
    """Grava avaliacoes_por_dedo.csv e dicionario_de_dados.csv em `folder`.
    Devolve (caminho do CSV, nº de linhas)."""
    os.makedirs(folder, exist_ok=True)
    data_path = os.path.join(folder, "avaliacoes_por_dedo.csv")
    patients = {p["id"]: p for p in db.pacientes("")}
    n = 0
    with open(data_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow([c for c, _, _ in SESSION_COLUMNS] + CSV_HEADER + [c for c, _, _ in RETEST_COLUMNS])
        for s in db.todas_sessoes():
            p = patients.get(s["paciente_id"], {})
            res = s["resultados"]
            day = datetime.date.fromisoformat(res["inicio"][:10])
            injury = p.get("data_lesao")
            whole = res.get("mao_inteira") or {}
            spread = whole.get("abertura_dedos") or [None, None, None]
            tremor = whole.get("tremor") or {}
            rel = res.get("confiabilidade") or {}
            calib = CALIBRATION_NAMES.get(res["calibracao"], "")
            age = age_from(p.get("nascimento"), day)
            session = [s["paciente_id"], p.get("identificacao", ""), "" if age is None else age,
                       p.get("mao_dominante") or "", p.get("mao_avaliada") or "", p.get("condicao") or "",
                       (day - datetime.date.fromisoformat(injury[:10])).days if injury else "",
                       s["id"], res["inicio"], res["duracao_s"], HAND.get(res["mao"], ""), calib,
                       rel.get("nivel", ""), " / ".join(rel.get("motivos", [])),
                       csv_num((rel.get("detalhes") or {}).get("validos_pct"), 1), res["descartados"],
                       "sim" if res.get("reteste") else "nao", res.get("pontos") or "",
                       csv_num(spread[0]), csv_num(spread[1]), csv_num(spread[2]),
                       csv_num(whole.get("abertura_dedos_total")), csv_num(whole.get("abertura_polegar")),
                       ("sim" if tremor.get("ritmico") else "nao") if tremor else "",
                       csv_num(tremor.get("frequencia_hz"), 1), csv_num(tremor.get("rms_mm"), 2),
                       tremor.get("segundos", "")]
            for f in kin.FINGERS:
                rt = ((res.get("reteste") or {}).get("dedos") or {}).get(f) or {}
                pct = rt.get("pct_normal")
                w.writerow(session + finger_row(f, res["dedos"][f])
                           + [csv_num(None if pct is None else pct * 100), csv_num(rt.get("tam_ativo"))])
                n += 1
    with open(os.path.join(folder, "dicionario_de_dados.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["variavel", "descricao", "unidade"])
        for row in SESSION_COLUMNS + _finger_descriptions() + RETEST_COLUMNS:
            w.writerow(row)
        w.writerow([])
        w.writerow(["observacao", "Uma linha por avaliação e dedo. Ambiente de teste: dados fictícios. "
                    "Medidas estimadas por câmera (MediaPipe), não substituem a goniometria.", ""])
    return data_path, n

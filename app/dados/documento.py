"""
Relatório da sessão: documento (HTML + gráficos) usado na prévia da tela E no
PDF - o que aparece na tela é o que sai impresso, exceto o logotipo, que vai
apenas no PDF (relatório final).

Só PyQt5 (QTextDocument + QPrinter), sem dependências novas. Visual claro,
próprio para impressão.
"""

import datetime
import html
import math

from PyQt5 import QtCore, QtGui, QtPrintSupport

import kinematics as kin
from app.dados import config as cfgmod
from app.dados.resultados import CALIBRATION_NAMES, HAND_NAMES, deficit_total
from app.formato import age_from, date_labels, fmt_date, fmt_datetime, fmt_deg, fmt_duration, fmt_num, fmt_pct

# Cores para papel (fundo branco)
INK = "#1d2733"
INK_MUTED = "#5b6875"
LINE = "#d5dbe1"
HEAD_BG = "#eef2f5"
GRADE_INK = {"ruim": "#d9534f", "regular": "#d39e00", "bom": "#3c9d4e", None: "#9aa5b1"}
# Paleta Okabe-Ito: distinguível também por quem não enxerga cores
FINGER_INK = {"thumb": "#D55E00", "index": "#0072B2", "middle": "#009E73",
              "ring": "#CC79A7", "pinky": "#E69F00"}

CHART_W, IMG_W = 700, 620    # largura de desenho dos gráficos e largura em que aparecem
LOGO_H = 56                  # altura do logotipo no cabeçalho
PRINT_DENSITY = 2.5          # pixels de imagem por pixel do documento no PDF: nítido no papel

METHOD_NOTE = (
    "Medidas estimadas por câmera comum com o MediaPipe Hand Landmarker, sem marcadores. "
    "A flexão de cada articulação é medida no plano do movimento; positivo = flexão, "
    "negativo = hiperextensão. TAM ativo = soma das flexões máximas − soma dos déficits de "
    "extensão (MCP+PIP+DIP; polegar MCP+IP); o % do normal usa referências da literatura "
    "(≈260° nos dedos longos, ≈140° no polegar). A MCP é medida em relação à linha "
    "punho–base do dedo, pois o MediaPipe não marca o metacarpo. Quadros com ângulo "
    "impossível ou com a mão de lado (mais de 60° da palma de frente) foram descartados. "
    "São estimativas, não substituem a goniometria: em testes, o erro típico ficou entre 5° e 15° "
    "por articulação, conforme a posição da mão.")


def _pp(a, b):
    """Diferença em pontos percentuais entre dois % (None se faltar)."""
    if a is None or b is None:
        return "--"
    d = (a - b) * 100
    return f"{'+' if d >= 0 else '−'}{abs(d):.0f} pp"


# =============================================================================
# Gráficos (desenhados com QPainter já na resolução de destino: tela ou PDF)
# =============================================================================
def screen_density(widget):
    """Densidade das imagens na prévia: um pixel de imagem por pixel da tela. Reduzir na
    tela (sem suavização) a imagem feita para o PDF deixava o texto serrilhado."""
    return widget.devicePixelRatioF()


def _canvas(w, h, scale):
    img = QtGui.QImage(int(w * scale), int(h * scale), QtGui.QImage.Format_ARGB32)
    img.fill(QtGui.QColor("white"))
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing)
    p.scale(scale, scale)
    return img, p


def chart_percent(results, density=PRINT_DENSITY):
    """Barras horizontais: % do normal (TAM ativo) de cada dedo."""
    W, row_h, top = CHART_W, 30, 12
    H = top + 5 * row_h + 34
    img, p = _canvas(W, H, density * IMG_W / CHART_W)
    left, right, maxv = 92, W - 70, 1.2
    x = lambda v: left + (right - left) * min(max(v, 0.0), maxv) / maxv
    bottom = top + 5 * row_h
    p.setFont(QtGui.QFont("Segoe UI", 8))
    for v, txt in ((0.5, "50%"), (0.75, "75%"), (1.0, "100% = normal")):
        pen = QtGui.QPen(QtGui.QColor(LINE if v < 1 else INK_MUTED), 1, QtCore.Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(x(v), top), QtCore.QPointF(x(v), bottom))
        p.setPen(QtGui.QColor(INK_MUTED))
        p.drawText(QtCore.QRectF(x(v) - 60, bottom + 4, 120, 16), QtCore.Qt.AlignCenter, txt)
    for i, f in enumerate(kin.FINGERS):
        y = top + i * row_h
        pct = results["dedos"][f]["pct_normal"]
        p.setPen(QtGui.QColor(INK))
        p.setFont(QtGui.QFont("Segoe UI", 9))
        p.drawText(QtCore.QRectF(0, y, left - 10, row_h), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                   kin.NAME[f])
        if pct is None:
            p.setPen(QtGui.QColor(INK_MUTED))
            p.drawText(QtCore.QRectF(left + 6, y, 200, row_h), QtCore.Qt.AlignVCenter, "sem dados")
            continue
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(GRADE_INK[kin.grade(pct)]))
        p.drawRoundedRect(QtCore.QRectF(left, y + 7, max(2.0, x(pct) - left), row_h - 14), 3, 3)
        p.setPen(QtGui.QColor(INK))
        f9b = QtGui.QFont("Segoe UI", 9)
        f9b.setBold(True)
        p.setFont(f9b)
        p.drawText(QtCore.QRectF(x(pct) + 6, y, 70, row_h), QtCore.Qt.AlignVCenter, f"{pct * 100:.0f}%")
    p.end()
    return img


def chart_evolution(history, density=PRINT_DENSITY):
    """Linhas: % do normal de cada dedo ao longo das sessões.
    history = [(inicio_iso, resultados), ...] em ordem cronológica."""
    W, H = CHART_W, 250
    img, p = _canvas(W, H, density * IMG_W / CHART_W)
    left, right, top, bottom = 50, W - 40, 34, H - 34    # folga à direita p/ o rótulo "dd/mm hh:mm"
    n = len(history)
    maxv = 1.2
    x = lambda i: left + (right - left) * (i / max(n - 1, 1))
    y = lambda v: bottom - (bottom - top) * min(max(v, 0.0), maxv) / maxv
    p.setFont(QtGui.QFont("Segoe UI", 8))
    for v in (0.0, 0.5, 0.75, 1.0):
        p.setPen(QtGui.QPen(QtGui.QColor(LINE if v != 1.0 else INK_MUTED), 1,
                            QtCore.Qt.SolidLine if v == 0 else QtCore.Qt.DashLine))
        p.drawLine(QtCore.QPointF(left, y(v)), QtCore.QPointF(right, y(v)))
        p.setPen(QtGui.QColor(INK_MUTED))
        p.drawText(QtCore.QRectF(0, y(v) - 8, left - 6, 16), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                   f"{v * 100:.0f}%")
    labels = date_labels([iso for iso, _ in history])
    step = max(1, math.ceil(n * 70 / (right - left)))   # rótulos com ~70 px; o último sempre aparece
    for i, text in enumerate(labels):
        if (n - 1 - i) % step == 0:
            p.drawText(QtCore.QRectF(x(i) - 40, bottom + 6, 80, 16), QtCore.Qt.AlignCenter, text)
    # legenda
    lx = left
    for f in kin.FINGERS:
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(FINGER_INK[f]))
        p.drawRoundedRect(QtCore.QRectF(lx, 10, 18, 6), 2, 2)
        p.setPen(QtGui.QColor(INK))
        p.drawText(QtCore.QRectF(lx + 22, 4, 90, 18), QtCore.Qt.AlignVCenter, kin.NAME[f])
        lx += 112
    for f in kin.FINGERS:
        pts = [(x(i), y(r["dedos"][f]["pct_normal"])) for i, (_, r) in enumerate(history)
               if r["dedos"][f]["pct_normal"] is not None]
        color = QtGui.QColor(FINGER_INK[f])
        p.setPen(QtGui.QPen(color, 2))
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            p.drawLine(QtCore.QPointF(x0, y0), QtCore.QPointF(x1, y1))
        p.setBrush(color)
        for px, py in pts:
            p.drawEllipse(QtCore.QPointF(px, py), 3.2, 3.2)
    p.end()
    return img


# =============================================================================
# Documento
# =============================================================================
def _table(headers, rows, widths=None):
    """widths = % de cada coluna; sem elas o Qt às vezes estreita demais uma coluna de
    título com uma palavra só e a quebra no meio ("Parciai-s")."""
    th_style = (f"background-color:{HEAD_BG}; color:{INK_MUTED}; padding:5px; font-weight:600;"
                " font-size:9pt;")
    td_style = f"padding:4px 5px; border-bottom:1px solid {LINE}; font-size:9pt;"
    th = "".join("<th align='left' style='%s'%s>%s</th>" % (th_style, " width='%d%%'" % w if w else "", h)
                 for h, w in zip(headers, widths or [None] * len(headers)))
    body = "".join("<tr>" + "".join("<td style='%s'>%s</td>" % (td_style, c) for c in row) + "</tr>"
                   for row in rows)
    # <thead>: no PDF o cabeçalho se repete quando a tabela continua na página seguinte
    return ("<table width='100%' cellspacing='0' cellpadding='0' style='border-collapse:collapse;'>"
            f"<thead><tr>{th}</tr></thead>{body}</table>")


def build_document(patient, results, notes, history, cfg, density=PRINT_DENSITY, with_logo=True):
    """patient = dict do banco; results = resultados da sessão; history =
    sessões ANTERIORES [(inicio_iso, resultados)]; cfg = configurações;
    density = pixels de imagem por pixel do documento (PRINT_DENSITY no PDF,
    screen_density na prévia); with_logo = False na prévia (logotipo só no PDF)."""
    doc = QtGui.QTextDocument()
    doc.setDefaultFont(QtGui.QFont("Segoe UI", 10))
    esc = lambda s: html.escape(s or "")

    # --- cabeçalho: logotipo (arquivo oficial escolhido em Configurações) ---
    logo = cfgmod.logo_path(cfg)
    logo_img = QtGui.QImage(logo) if logo else QtGui.QImage()
    if not logo_img.isNull() and not with_logo:
        logo_html = ""                          # há logotipo, mas ele vai apenas no PDF
    elif not logo_img.isNull():
        # reamostrado com suavização já na resolução final: um arquivo pequeno, ampliado
        # pelo leitor de PDF, ficaria quadriculado
        logo_img = logo_img.scaledToHeight(round(LOGO_H * density), QtCore.Qt.SmoothTransformation)
        doc.addResource(QtGui.QTextDocument.ImageResource, QtCore.QUrl("logo"), logo_img)
        logo_html = f"<img src='logo' height='{LOGO_H}'>"
    else:
        logo_html = f"<span style='font-size:13pt; font-weight:700; color:{INK};'>{esc(cfg['instituicao'].split('—')[0].strip())}</span>"
    head = (f"<table width='100%'><tr><td valign='middle'>{logo_html}</td>"
            f"<td align='right' valign='middle' style='color:{INK_MUTED}; font-size:9pt;'>"
            f"{esc(cfg['instituicao'])}</td></tr></table>"
            f"<hr style='color:{LINE};'>"
            f"<p style='font-size:15pt; font-weight:700; color:{INK}; margin:6px 0 2px 0;'>{esc(cfg['titulo'])}</p>")

    # --- paciente e sessão ---
    age = age_from(patient.get("nascimento"), datetime.date.fromisoformat(results["inicio"][:10]))
    pat_rows = [
        ("Paciente", f"<b>{esc(patient.get('identificacao'))}</b>"),
        ("Idade", "--" if age is None else f"{age} anos"),
        ("Condição / diagnóstico", esc(patient.get("condicao")) or "--"),
        ("Data da lesão ou cirurgia", fmt_date(patient.get("data_lesao"))),
        ("Mão dominante / avaliada", f"{esc(patient.get('mao_dominante')) or '--'} / "
                                      f"{esc(patient.get('mao_avaliada')) or '--'}"),
        ("Profissional", esc(patient.get("profissional")) or "--"),
    ]
    sens = [d["sensibilidade"] for d in results["dedos"].values()]
    ses_rows = [
        ("Data", fmt_datetime(results["inicio"])),
        ("Duração", fmt_duration(results["duracao_s"])),
        ("Mão medida", HAND_NAMES.get(results["mao"], "--")),
        ("Calibração", CALIBRATION_NAMES.get(results["calibracao"], "--")),
        ("Sensibilidade", (f"{min(sens):.0f}°" if round(min(sens)) == round(max(sens))
                           else f"{min(sens):.0f}° a {max(sens):.0f}°") + " (menor movimento contado)"),
        ("Quadros descartados", f"{results['descartados']} (medida impossível)"),
    ]
    two_col = lambda rows: "".join(
        f"<tr><td style='color:{INK_MUTED}; padding:2px 10px 2px 0;' width='42%'>{k}</td>"
        f"<td style='padding:2px 0;'>{v}</td></tr>" for k, v in rows)
    info = (f"<table width='100%' cellspacing='0'><tr>"
            f"<td valign='top' width='50%'><table width='100%'>{two_col(pat_rows)}</table></td>"
            f"<td valign='top' width='50%'><table width='100%'>{two_col(ses_rows)}</table></td>"
            f"</tr></table>")

    # --- resultado por dedo ---
    doc.addResource(QtGui.QTextDocument.ImageResource, QtCore.QUrl("grafico_pct"),
                    chart_percent(results, density))
    rows = []
    for f in kin.FINGERS:
        d = results["dedos"][f]
        amps = d["amplitudes"]
        color = GRADE_INK[kin.grade(d["pct_normal"])]
        rows.append([f"<b>{kin.NAME[f]}</b>", fmt_deg(d["tam_ativo"]),
                     f"<span style='color:{color}; font-weight:700;'>{fmt_pct(d['pct_normal'])}</span>",
                     fmt_deg(deficit_total(d)), str(d["movimentos"]), str(d["parciais"]),
                     str(d["completas"]), fmt_pct(d["independencia"]),
                     "--" if not amps else f"{amps[0]:.0f}° → {amps[-1]:.0f}°"])
    by_finger = _table(["Dedo", "TAM ativo", "% do normal", "Déficit de extensão", "Movimentos",
                        "Parciais", "Completas", "Independência", "Amplitude 1ª → última"], rows,
                       widths=[12, 8, 9, 10, 12, 9, 11, 15, 14])

    # --- articulações ---
    jrows = []
    for f in kin.FINGERS:
        for k, j in enumerate(results["dedos"][f]["articulacoes"]):
            jrows.append([f"<b>{kin.NAME[f]}</b>" if k == 0 else "", j["nome"], fmt_deg(j["min"]),
                          fmt_deg(j["max"]), fmt_deg(j["arco"]), fmt_deg(j["deficit"]),
                          "--" if j["contribuicao"] is None else f"{j['contribuicao'] * 100:.0f}%"])
    joints = _table(["Dedo", "Articulação", "Flexão mín.", "Flexão máx.", "Arco", "Déficit ext.",
                     "Contribuição"], jrows)

    # --- qualidade do movimento ---
    qrows = []
    for f in kin.FINGERS:
        q = results["dedos"][f]["qualidade"]
        ch = q["amp_change"]
        qrows.append([f"<b>{kin.NAME[f]}</b>", fmt_num(q["flex_velocity"], 0, " °/s"),
                      fmt_num(q["ext_velocity"], 0, " °/s"), fmt_num(q["cycle_s"], 1, " s"),
                      fmt_num(q["cadence"], 0, "/min"),
                      "--" if not q["regularity"] else f"{q['regularity']} ({q['cv'] * 100:.0f}%)",
                      "--" if ch is None else f"{'+' if ch >= 0 else '−'}{abs(ch) * 100:.0f}%"])
    quality = _table(["Dedo", "Vel. flexão", "Vel. extensão", "Ciclo", "Cadência", "Regularidade",
                      "Amplitude fim × início"], qrows)

    # --- evolução (se houver sessões anteriores) ---
    evolution = ""
    if history:
        series = list(history) + [(results["inicio"], results)]
        doc.addResource(QtGui.QTextDocument.ImageResource, QtCore.QUrl("grafico_evolucao"),
                        chart_evolution(series, density))
        prev, first = history[-1][1], history[0][1]
        erows = [[f"<b>{kin.NAME[f]}</b>", fmt_pct(results["dedos"][f]["pct_normal"]),
                  _pp(results["dedos"][f]["pct_normal"], prev["dedos"][f]["pct_normal"]),
                  _pp(results["dedos"][f]["pct_normal"], first["dedos"][f]["pct_normal"])]
                 for f in kin.FINGERS]
        evolution = (f"<h3 style='page-break-before:always;'>Evolução ({len(series)} avaliações)</h3>"
                     f"<p align='center'><img src='grafico_evolucao' width='{IMG_W}'></p>"
                     + _table(["Dedo", "% normal hoje",
                               f"vs. anterior ({fmt_date(history[-1][0])})",
                               f"vs. primeira ({fmt_date(history[0][0])})"], erows))

    notes_html = esc(notes).replace("\n", "<br>") if notes and notes.strip() else \
        f"<span style='color:{INK_MUTED};'>Sem observações.</span>"
    generated = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    # 1ª página = resumo (resultado, observações, limitações); a 2ª começa na evolução
    # ou, sem evolução, nas articulações
    joints_break = "" if evolution else " style='page-break-before:always;'"
    body = (
        f"<html><body style='color:{INK};'>{head}{info}"
        f"<h3>Resultado por dedo</h3>"
        f"<p align='center'><img src='grafico_pct' width='{IMG_W}'></p>{by_finger}"
        f"<h3>Observações do profissional</h3><p>{notes_html}</p>"
        f"<h3>Método e limitações</h3><p style='color:{INK_MUTED}; font-size:8.5pt;'>{METHOD_NOTE}</p>"
        f"{evolution}"
        f"<h3{joints_break}>Articulações</h3>{joints}"
        f"<h3>Qualidade do movimento</h3>{quality}"
        f"<hr style='color:{LINE};'><p style='color:{INK_MUTED}; font-size:8pt;'>"
        f"Gerado em {generated} · Ambiente de teste: dados fictícios.</p>"
        f"</body></html>")
    doc.setHtml(body)
    # depois do setHtml (que limpa o título): nome do PDF e rodapé de cada página
    ident = patient.get("identificacao") or ""
    doc.setMetaInformation(QtGui.QTextDocument.DocumentTitle, f"{cfg['titulo']} - {ident}")
    doc.setProperty("rodape", f"{ident} · avaliação de {fmt_datetime(results['inicio'])} · "
                              "ambiente de teste, dados fictícios")
    return doc


def save_pdf(doc, path):
    """Imprime o documento em PDF A4, com rodapé (paciente e "Página X de N").

    Pagina por conta própria: o QTextDocument.print_ soma 2 cm de margem às margens
    da impressora e deixava só ~14 cm de largura útil, espremendo as tabelas."""
    printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.HighResolution)
    printer.setOutputFormat(QtPrintSupport.QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageSize(QtGui.QPageSize(QtGui.QPageSize.A4))
    printer.setPageMargins(15, 14, 15, 10, QtPrintSupport.QPrinter.Millimeter)
    printer.setDocName(doc.metaInformation(QtGui.QTextDocument.DocumentTitle))
    footer = doc.property("rodape") or ""

    painter = QtGui.QPainter()
    if not painter.begin(printer):
        raise OSError(f"Não foi possível gravar o PDF em {path}")
    painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)   # imagens suavizadas no PDF
    try:
        mm = printer.logicalDpiY() / 25.4
        footer_h = 9 * mm
        page = QtCore.QRectF(0, 0, printer.width(), printer.height() - footer_h)
        paged = doc.clone()                      # a prévia na tela continua intacta
        layout = paged.documentLayout()
        layout.setPaintDevice(printer)           # mede o texto na resolução do PDF
        root = paged.rootFrame().frameFormat()
        root.setMargin(0)
        paged.rootFrame().setFrameFormat(root)
        paged.setPageSize(page.size())
        total = paged.pageCount()
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor(INK))
        font = QtGui.QFont("Segoe UI", 7)
        for i in range(total):
            if i:
                printer.newPage()
            view = page.translated(0, i * page.height())
            painter.save()
            painter.translate(0, -view.top())
            painter.setClipRect(view)
            ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()
            ctx.clip = view
            ctx.palette = palette
            layout.draw(painter, ctx)
            painter.restore()

            y = page.height() + 3 * mm
            painter.setPen(QtGui.QPen(QtGui.QColor(LINE), 0.25 * mm))
            painter.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(page.width(), y))
            painter.setPen(QtGui.QColor(INK_MUTED))
            painter.setFont(font)
            text = QtCore.QRectF(0, y + 1 * mm, page.width(), footer_h - 4 * mm)
            painter.drawText(text, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, footer)
            painter.drawText(text, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                             f"Página {i + 1} de {total}")
    finally:
        painter.end()

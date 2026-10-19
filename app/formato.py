"""Formatação de números, datas e idades em português (sem interface).
Usada pelas telas (via app.tema), pelo relatório em PDF e pela exportação."""

import datetime


def fmt_deg(v):
    """Graus inteiros; hiperextensão com o sinal de menos tipográfico."""
    if v is None:
        return "--"
    return ("−" if v < -0.5 else "") + f"{abs(v):.0f}°"


def fmt_num(v, decimals=0, suffix=""):
    """Número com vírgula decimal (pt-BR)."""
    if v is None:
        return "--"
    v = round(float(v), decimals) + 0.0              # + 0.0 tira o "-0"
    return f"{v:.{decimals}f}".replace(".", ",") + suffix


def fmt_pct(fraction):
    """0,42 -> '42%'."""
    return "--" if fraction is None else f"{fraction * 100:.0f}%"


def fmt_date(iso):
    """'2026-10-14' ou '2026-10-14T15:35:16' -> '14/10/2026' (vazio -> '--')."""
    if not iso:
        return "--"
    d = iso[:10].split("-")
    return f"{d[2]}/{d[1]}/{d[0]}" if len(d) == 3 else iso


def fmt_datetime(iso):
    if not iso:
        return "--"
    return fmt_date(iso) + (f" {iso[11:16]}" if len(iso) >= 16 else "")


def fmt_duration(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def date_labels(isos):
    """Rótulos curtos (dd/mm) para eixos de gráficos; avaliações no mesmo dia
    ganham também a hora."""
    days = [fmt_date(iso)[:5] for iso in isos]
    return [d if days.count(d) == 1 else f"{d} {iso[11:16]}" for d, iso in zip(days, isos)]


def age_from(iso_birth, ref=None):
    """Idade em anos a partir de 'aaaa-mm-dd' (None se não informada)."""
    if not iso_birth:
        return None
    try:
        b = datetime.date.fromisoformat(iso_birth[:10])
    except ValueError:
        return None
    ref = ref or datetime.date.today()
    return ref.year - b.year - ((ref.month, ref.day) < (b.month, b.day))

"""Configurações: relatório (instituição, logotipo, título, profissional padrão),
tema da interface e se as dicas da avaliação já foram vistas."""

import json
import os

from app.dados.banco import DATA_DIR, ROOT

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOGO_DIR = os.path.join(ROOT, "assets")
DEFAULTS = {
    "instituicao": "UFCSPA — Universidade Federal de Ciências da Saúde de Porto Alegre",
    "titulo": "Relatório de avaliação cinemática da mão",
    "logo": "assets/logo_relatorio.png",   # relativo à pasta do projeto; trocado em Configurações
    "profissional_padrao": "",
    "tema": "escuro",           # "escuro" ou "claro" (lido ao abrir o programa)
    "escala": 1.0,              # tamanho da interface: 1.0, 1.15 ou 1.3 (idem)
    "dicas_vistas": False,      # as dicas da avaliação já apareceram uma vez
}


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=1)


def logo_path(cfg):
    """Caminho absoluto do logotipo, se o arquivo existir."""
    path = cfg.get("logo") or ""
    if path and not os.path.isabs(path):
        path = os.path.join(ROOT, path)
    return path if path and os.path.exists(path) else None

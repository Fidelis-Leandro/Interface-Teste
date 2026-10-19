"""
Instala o modelo MANO (pele da mão 3D) a partir do arquivo oficial baixado pelo
próprio usuário. A licença do MANO não permite redistribuir os arquivos, por
isso eles não vêm com o projeto: cada pessoa baixa com a própria conta.

1. Crie uma conta em https://mano.is.tue.mpg.de e aceite a licença
   (uso de pesquisa não comercial).
2. Em "Download", baixe "Models & Code" (mano_v1_2.zip).
3. Rode este script (ou "Instalar mao 3D.bat"). Sem argumento, ele procura o
   mano_v1_2*.zip, ou a pasta mano_v1_2 já extraída, em Downloads (inclusive
   Downloads dentro do OneDrive). Também aceita o caminho do zip ou da pasta:

    .venv\\Scripts\\python.exe tools\\instalar_mano.py
    .venv\\Scripts\\python.exe tools\\instalar_mano.py C:\\caminho\\mano_v1_2.zip
    .venv\\Scripts\\python.exe tools\\instalar_mano.py C:\\caminho\\mano_v1_2

No fim, confere que a mão 3D carrega: "Mão 3D instalada e verificada".
"""

import glob
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import hand_skin  # noqa: E402

WANTED = ("MANO_RIGHT.pkl", "MANO_LEFT.pkl")


def download_dirs():
    """Downloads do usuário; em computadores com OneDrive ela costuma ficar lá dentro."""
    home = os.path.expanduser("~")
    return [os.path.join(home, "Downloads")] + glob.glob(os.path.join(home, "OneDrive*", "Downloads"))


def find_source():
    """Caminho do zip ou da pasta extraída (o mais recente), ou None."""
    if len(sys.argv) > 1:
        return sys.argv[1]
    found = []
    for d in download_dirs():
        found += glob.glob(os.path.join(d, "mano_v1_2*.zip"))
        found += [p for p in glob.glob(os.path.join(d, "mano_v1_2*")) if os.path.isdir(p)]
    return max(found, key=os.path.getmtime) if found else None


def copy_from_zip(path):
    with zipfile.ZipFile(path) as z:
        for name in WANTED:
            member = next((m for m in z.namelist() if m.endswith("/" + name) or m == name), None)
            if member is None:
                return name
            with z.open(member) as src, open(os.path.join(hand_skin.MANO_DIR, name), "wb") as dst:
                shutil.copyfileobj(src, dst)
    return None


def copy_from_folder(path):
    for name in WANTED:
        found = glob.glob(os.path.join(path, "**", name), recursive=True)
        if not found:
            return name
        shutil.copyfile(found[0], os.path.join(hand_skin.MANO_DIR, name))
    return None


def main():
    path = find_source()
    if not path or not os.path.exists(path):
        print("Não encontrei o mano_v1_2.zip (nem a pasta mano_v1_2) em:")
        for d in download_dirs():
            print("   ", d)
        print("Baixe em https://mano.is.tue.mpg.de (Download > Models & Code) e rode de novo,")
        print("ou informe o caminho: tools\\instalar_mano.py C:\\caminho\\mano_v1_2.zip")
        return 1
    print(f"Usando {path}")
    os.makedirs(hand_skin.MANO_DIR, exist_ok=True)
    missing = copy_from_zip(path) if zipfile.is_zipfile(path) else copy_from_folder(path)
    if missing:
        print(f"Não achei {missing} dentro de {path}.")
        print("Confira se é o download 'Models & Code' (mano_v1_2.zip), e não outro arquivo do site.")
        return 1
    for side in ("right", "left"):
        npz = os.path.join(hand_skin.MANO_DIR, f"mano_{side}.npz")
        if os.path.exists(npz):                      # reinstalação: refaz a conversão
            os.remove(npz)
        hand_skin.ManoModel(hand_skin.load_mano(side))   # converte e confere que o modelo carrega
    print("Mão 3D instalada e verificada. Feche e abra o sistema para vê-la.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

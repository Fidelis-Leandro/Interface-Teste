"""
Instala o modelo MANO (pele da mão 3D) a partir do zip oficial baixado pelo
próprio usuário. A licença do MANO não permite redistribuir os arquivos, por
isso eles não vêm com o projeto: cada pessoa baixa com a própria conta.

1. Crie uma conta em https://mano.is.tue.mpg.de e aceite a licença
   (uso de pesquisa não comercial).
2. Em "Download", baixe "Models & Code" (mano_v1_2.zip).
3. Rode este script (ou Instalar mao 3D.bat). Ele procura o zip na pasta
   Downloads; também aceita o caminho do zip como argumento:

    .venv\\Scripts\\python.exe tools\\instalar_mano.py
    .venv\\Scripts\\python.exe tools\\instalar_mano.py C:\\caminho\\mano_v1_2.zip
"""

import glob
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import hand_skin  # noqa: E402

WANTED = ("MANO_RIGHT.pkl", "MANO_LEFT.pkl")


def find_zip():
    if len(sys.argv) > 1:
        return sys.argv[1]
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    found = sorted(glob.glob(os.path.join(downloads, "mano_v1_2*.zip")), key=os.path.getmtime)
    return found[-1] if found else None


def main():
    path = find_zip()
    if not path or not os.path.exists(path):
        print("Não encontrei o mano_v1_2.zip na pasta Downloads.")
        print("Baixe em https://mano.is.tue.mpg.de (Download > Models & Code) e rode de novo,")
        print("ou informe o caminho: tools\\instalar_mano.py C:\\caminho\\mano_v1_2.zip")
        return 1
    print(f"Usando {path}")
    os.makedirs(hand_skin.MANO_DIR, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        for name in WANTED:
            member = next((m for m in z.namelist() if m.endswith("/" + name) or m == name), None)
            if member is None:
                print(f"O zip não tem {name}. É o arquivo 'Models & Code' (mano_v1_2.zip)?")
                return 1
            with z.open(member) as src, open(os.path.join(hand_skin.MANO_DIR, name), "wb") as dst:
                dst.write(src.read())
    for side in ("right", "left"):                  # converte para .npz (feito uma vez só)
        hand_skin.load_mano(side)
    print("Mão 3D instalada. Abra o sistema de novo para vê-la.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

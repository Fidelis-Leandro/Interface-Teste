"""
Roda todos os testes automáticos (sem câmera e sem abrir janelas) e resume.

    .venv\\Scripts\\python.exe tools\\testar.py

Com uma gravação real, os testes de medidas também conferem que uma mão
saudável não recebe nenhuma limitação:

    .venv\\Scripts\\python.exe tools\\testar.py gravacoes\\sessao_XXXX.npz
"""

import os
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
TESTS = ["test_kinematics.py", "test_metricas.py", "test_medidas.py", "test_stabilizer.py",
         "test_hand_skin.py"]

failed = []
for name in TESTS:
    args = [sys.executable, os.path.join(TOOLS, name)]
    if name == "test_medidas.py" and len(sys.argv) > 1:
        args.append(sys.argv[1])
    t0 = time.monotonic()
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = proc.returncode == 0
    print(f"{'ok    ' if ok else 'FALHOU'} {name}  ({time.monotonic() - t0:.0f} s)")
    if not ok:
        failed.append(name)
        print("\n".join("    " + line for line in (proc.stdout + proc.stderr).strip().splitlines()[-15:]))
print("\nTodos os testes passaram." if not failed else f"\n{len(failed)} arquivo(s) com falha: {failed}")
sys.exit(1 if failed else 0)

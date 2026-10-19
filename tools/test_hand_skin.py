"""
Testes do hand_skin.py SEM os arquivos do MANO.

Monta um modelo sintético com o mesmo formato do MANO (778 vértices, 16
articulações, pontas nos mesmos índices de vértice, pesos de skinning) usando
a mão de referência do geometria.py, e verifica:
  1) pose neutra devolve a malha de repouso
  2) cinemática inversa recupera poses aleatórias (erro ~0)
  3) desempenho por frame

Se os arquivos reais estiverem em assets/mano/, roda também com eles.

    .venv\\Scripts\\python.exe tools\\test_hand_skin.py
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hand_skin as hs  # noqa: E402
import geometria  # noqa: E402


def synthetic_model():
    return hs.ManoModel(synthetic_data())


def synthetic_data(radius=0.008, ring=8):
    """Mão de 'tubos' com o mesmo formato de dados do MANO."""
    P = geometria.build_hand_world([0, 0, 0, 0], 0)          # 21 pontos, mão aberta (m)
    n_verts = 778
    reserved = set(hs.TIP_VERTS.values())
    free = [i for i in range(n_verts) if i not in reserved]

    verts = np.zeros((n_verts, 3))
    weights = np.zeros((n_verts, 16))
    J_regressor = np.zeros((16, n_verts))

    # Vértices das juntas (o regressor só copia esses vértices)
    for j in range(16):
        v = free.pop(0)
        verts[v] = P[hs.MP_FROM_MANO.index(("j", j))]
        J_regressor[j, v] = 1.0
        weights[v, max(hs.MANO_PARENTS[j], 0)] = 1.0
    # Pontas dos dedos: presas à última junta do dedo
    for mp, (kind, idx) in enumerate(hs.MP_FROM_MANO):
        if kind == "v":
            verts[idx] = P[mp]
            weights[idx, [j for j, m in hs.MP_OF_JOINT.items() if m == mp - 1][0]] = 1.0

    # Tubos ao redor de cada osso (3 anéis), presos à junta que gira o osso
    faces = []
    for j in range(1, 16):
        m = hs.MP_OF_JOINT[j]
        a, b = P[m], P[m + 1]
        d = (b - a) / np.linalg.norm(b - a)
        e1 = np.cross(d, [0, 0, 1.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(d, e1)
        rings = []
        for t in (0.0, 0.5, 1.0):
            idx = []
            for k in range(ring):
                ang = 2 * np.pi * k / ring
                v = free.pop(0)
                verts[v] = a + t * (b - a) + radius * (np.cos(ang) * e1 + np.sin(ang) * e2)
                weights[v, j] = 1.0
                idx.append(v)
            rings.append(idx)
        for r0, r1 in zip(rings[:-1], rings[1:]):
            for k in range(ring):
                k2 = (k + 1) % ring
                faces += [[r0[k], r0[k2], r1[k]], [r0[k2], r1[k2], r1[k]]]
    for v in free:                                    # sobras: no punho
        verts[v] = P[0]
        weights[v, 0] = 1.0

    kintree = np.vstack([np.where(hs.MANO_PARENTS < 0, 2**32 - 1, hs.MANO_PARENTS), np.arange(16)])
    return ({
        "v_template": verts, "shapedirs": np.zeros((n_verts, 3, 10)),
        "posedirs": np.zeros((n_verts, 3, 135)), "J_regressor": J_regressor,
        "weights": weights, "kintree_table": kintree, "faces": np.array(faces),
    })


def random_pose(model, rng):
    """Pose plausível: dobradiça nas PIP/DIP, sem torção nas demais."""
    R = np.tile(np.eye(3), (16, 1, 1))
    R[0] = hs.axis_angle(rng.normal(size=3), rng.uniform(0, np.pi))
    for j in range(1, 16):
        if j in hs.HINGE_JOINTS:
            R[j] = hs.axis_angle(model.hinge_axes[j], np.radians(rng.uniform(0, 90)))
        else:
            d = model.rest_dirs[j]
            new = d + rng.normal(scale=0.35, size=3)
            R[j] = hs.rotation_between(d, new)
    return R


def check(name, model, n=200):
    rng = np.random.default_rng(0)
    verts0, _ = model.forward(np.tile(np.eye(3), (16, 1, 1)))
    print(f"[{name}] pose neutra = repouso: erro máx {np.abs(verts0 - model.v_shaped).max():.2e} m")

    errors = []
    for _ in range(n):
        verts, joints = model.forward(random_pose(model, rng))
        P = model.landmarks21(joints, verts)
        scale, shift = rng.uniform(5, 15), rng.normal(size=3)   # como na cena GL
        P = P * scale + shift
        fitted = model.fit(P)
        # landmarks do resultado (juntas reposicionadas na mesma escala)
        _, j2 = model.forward(model.solve(P))
        j2 = (j2 - model.J[0]) * scale + P[0]
        P2 = model.landmarks21(j2, fitted)
        errors.append(np.linalg.norm(P2 - P, axis=1).max() / scale * 1000)
    print(f"[{name}] IK em {n} poses aleatórias: erro máx {max(errors):.3f} mm, "
          f"mediano {np.median(errors):.3f} mm")

    P = geometria.world_to_gl(geometria.build_hand_world([60, 50, 40, 30], 30))
    t0 = time.perf_counter()
    for _ in range(100):
        verts = model.fit(P)
        hs.vertex_normals(verts, model.faces)
    print(f"[{name}] tempo por frame (IK + skinning + normais): "
          f"{(time.perf_counter() - t0) * 10:.2f} ms")


def check_open_and_pinch(name, model):
    # --- Calibração: MediaPipe "dobra" 15° cada junta com a mão aberta ------
    R = np.tile(np.eye(3), (16, 1, 1))
    for j in hs.FLEX_JOINTS:
        R[j] = hs.axis_angle(model.flex_axes[j], np.radians(15))
    verts, joints = model.forward(R)
    P = model.landmarks21(joints, verts)
    offsets = model.flex_angles(model.solve(P))
    open_hand = model.fit(P, offsets)
    rest = model.v_shaped - model.J[0] + P[0]
    tips = list(hs.TIP_VERTS.values())
    print(f"[{name}] calibração: flexão medida {np.degrees(np.mean(list(offsets.values()))):.1f}° "
          f"| pontas sem calibrar a {1000 * np.abs(model.fit(P) - rest)[tips].max():.0f} mm da mão aberta, "
          f"calibrada a {1000 * np.abs(open_hand - rest)[tips].max():.1f} mm")

    # --- Toque do polegar em cada dedo (dedos meio dobrados) ---------------
    R = np.tile(np.eye(3), (16, 1, 1))
    for j in hs.FLEX_JOINTS:
        R[j] = hs.axis_angle(model.flex_axes[j], np.radians(30))
    verts, joints = model.forward(R)
    P = model.landmarks21(joints, verts)
    for finger in ("index", "middle", "ring", "pinky"):
        gaps = []
        for contact in (None, (finger, 1.0)):
            v = model.fit(P, None, contact)
            gaps.append(1000 * np.linalg.norm(v[hs.TIP_VERTS["thumb"]] - v[hs.TIP_VERTS[finger]]))
        print(f"[{name}] toque polegar-{finger:6s}: sem contato {gaps[0]:5.1f} mm -> com contato {gaps[1]:4.1f} mm")

    # --- Detecção pela imagem ----------------------------------------------
    img = P[:, :2].copy()                       # "imagem" = projeção x, y
    lm = hs.FINGER_CHAINS["middle"][2]
    palm = np.linalg.norm(img[9] - img[0])
    for frac in (0.6, 0.3, 0.1):                # polegar a 60%, 30%, 10% da palma do médio
        img2 = img.copy()
        img2[[8, 16, 20]] += 10 * palm          # demais pontas longe, na imagem
        img2[4] = img[lm] + np.array([1.0, 0]) * frac * palm
        P2 = P.copy()
        P2[4] = P[lm] + np.array([0.01, 0, 0])  # 1 cm em 3D (passa na trava)
        finger, w, d = hs.detect_touch(P2, img2, 100.0)
        print(f"[{name}] detecção: polegar a {frac:.1f} palma do médio -> {finger}, contato {w:.0%}")


if __name__ == "__main__":
    check("sintético", synthetic_model())
    for side in ("right", "left"):
        try:
            model = hs.ManoModel(hs.load_mano(side))
        except FileNotFoundError:
            print(f"[MANO {side}] arquivos não encontrados em {hs.MANO_DIR} - pulando")
            continue
        check(f"MANO {side}", model)
        check_open_and_pinch(f"MANO {side}", model)

"""
Mão com pele (modelo MANO) para a cena 3D do pyqtgraph.opengl - só numpy.

MANO: Romero, Tzionas & Black, "Embodied Hands", SIGGRAPH Asia 2017.
(c) Max Planck Institute for Intelligent Systems - licença de pesquisa NÃO
comercial; os arquivos não podem ser redistribuídos. Baixe em
https://mano.is.tue.mpg.de (veja assets/mano/LEIA-ME.txt).

O que é o MANO, em matrizes:
  v_template (778,3)     malha da mão aberta em repouso (metros)
  shapedirs  (778,3,10)  como a malha muda com o "formato" da mão (betas)
  posedirs   (778,3,135) correções da pele que dependem da pose
  J_regressor (16,778)   articulações = média ponderada de vértices
  weights    (778,16)    quanto cada vértice segue cada articulação (skinning)
  parents    (16,)       hierarquia: punho -> dedos (3 juntas cada)
  faces      (1538,3)    triângulos

Fluxo por frame:
  21 landmarks --[cinemática inversa analítica]--> 16 rotações
  16 rotações  --[cinemática direta + skinning linear]--> 778 vértices
  778 vértices --[GLMeshItem.setMeshData]--> GPU
"""

import json
import os
import pickle

import numpy as np
import pyqtgraph.opengl as gl
from pyqtgraph.opengl import shaders

MANO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "mano")
SKIN_COLOR = (0.89, 0.70, 0.60, 1.0)

# Shader próprio: o "shaded" do pyqtgraph tem luz fixa e fica escuro demais.
# Aqui a luz sai da câmera (como uma lanterna na cabeça): luz ambiente +
# difusa + um leve brilho especular. Os uniforms/atributos (u_mvp, u_normal,
# a_position, a_normal, a_color) são os que o GLMeshItem já fornece.
SKIN_SHADER = shaders.ShaderProgram("skin", [
    shaders.VertexShader("""
        uniform mat4 u_mvp;
        uniform mat3 u_normal;
        attribute vec4 a_position;
        attribute vec3 a_normal;
        attribute vec4 a_color;
        varying vec4 v_color;
        varying vec3 v_normal;
        void main() {
            v_normal = normalize(u_normal * a_normal);
            v_color = a_color;
            gl_Position = u_mvp * a_position;
        }
    """),
    shaders.FragmentShader("""
        #ifdef GL_ES
        precision mediump float;
        #endif
        varying vec4 v_color;
        varying vec3 v_normal;
        void main() {
            vec3 n = normalize(v_normal);
            float diffuse = abs(dot(n, normalize(vec3(0.3, 0.4, 1.0))));
            float specular = pow(abs(n.z), 24.0) * 0.25;
            vec3 rgb = v_color.rgb * (0.30 + 0.70 * diffuse) + specular;
            gl_FragColor = vec4(rgb, v_color.a);
        }
    """),
])

# Ordem das 16 articulações do MANO:
#   0 punho | 1-3 indicador | 4-6 médio | 7-9 mínimo | 10-12 anelar | 13-15 polegar
MANO_PARENTS = np.array([-1, 0, 1, 2, 0, 4, 5, 0, 7, 8, 0, 10, 11, 0, 13, 14])

# O MANO não tem articulação na ponta dos dedos: usa-se um vértice fixo da
# malha (mesma convenção do manopth/manotorch).
TIP_VERTS = {"thumb": 745, "index": 317, "middle": 444, "ring": 556, "pinky": 673}

# Landmark MediaPipe (0..20) <- articulação MANO ("j") ou vértice da ponta ("v")
MP_FROM_MANO = [
    ("j", 0),
    ("j", 13), ("j", 14), ("j", 15), ("v", TIP_VERTS["thumb"]),
    ("j", 1), ("j", 2), ("j", 3), ("v", TIP_VERTS["index"]),
    ("j", 4), ("j", 5), ("j", 6), ("v", TIP_VERTS["middle"]),
    ("j", 10), ("j", 11), ("j", 12), ("v", TIP_VERTS["ring"]),
    ("j", 7), ("j", 8), ("j", 9), ("v", TIP_VERTS["pinky"]),
]
# Landmark MediaPipe de cada articulação MANO. O "filho" (para onde aponta o
# osso que a articulação gira) é sempre o landmark seguinte: MP_OF_JOINT[j] + 1.
MP_OF_JOINT = {idx: mp for mp, (kind, idx) in enumerate(MP_FROM_MANO) if kind == "j"}

# Juntas interfalângicas (PIP/DIP) dos 4 dedos: só dobram, como uma dobradiça.
HINGE_JOINTS = {2, 3, 5, 6, 8, 9, 11, 12}
MAX_HINGE_DEG = 130.0

# Juntas dos 4 dedos (MCP, PIP, DIP) que entram na calibração de mão aberta.
# O polegar fica de fora: ele não tem um eixo de flexão simples.
FLEX_JOINTS = range(1, 13)

# Cada dedo: (juntas MANO da base à ponta, vértice da ponta, landmark da ponta)
FINGER_CHAINS = {
    "thumb": ([13, 14, 15], TIP_VERTS["thumb"], 4),
    "index": ([1, 2, 3], TIP_VERTS["index"], 8),
    "middle": ([4, 5, 6], TIP_VERTS["middle"], 12),
    "ring": ([10, 11, 12], TIP_VERTS["ring"], 16),
    "pinky": ([7, 8, 9], TIP_VERTS["pinky"], 20),
}

# Toque de pontas (polegar com outro dedo). A profundidade do MediaPipe é
# ruim: com as pontas encostadas, a distância 3D medida ficou com mediana de
# 3,5 cm (até 8 cm). Por isso o toque é detectado na IMAGEM, em frações do
# tamanho da palma na imagem (punho -> base do médio):
#   abaixo de START a pele começa a aproximar as pontas; abaixo de CONTACT tocam.
TOUCH_START_PALM = 0.40
TOUCH_CONTACT_PALM = 0.22
# Trava 3D folgada: acima disso é um dedo "atrás" do outro, não um toque.
TOUCH_MAX_3D_CM = 9.0
CCD_MAX_ITERATIONS = 20
CCD_TOLERANCE_M = 0.0015      # pontas a até 1,5 mm da distância desejada

# Partes da mão para colorir a pele (cada articulação MANO pertence a uma).
# A base do polegar (13) fica com a palma, para a cor do polegar não "vazar".
PARTS = ["palm", "thumb", "index", "middle", "ring", "pinky"]
JOINT_PART = (["palm"] + ["index"] * 3 + ["middle"] * 3 + ["pinky"] * 3
              + ["ring"] * 3 + ["palm", "thumb", "thumb"])

CALIBRATION_FILE = os.path.join(MANO_DIR, "calibracao_mao_aberta.json")
CALIBRATION_FRAMES = 30


# =============================================================================
# Leitura dos arquivos do MANO
# =============================================================================
class _Stub:
    """Substitui classes antigas (chumpy, scipy.sparse) ao ler o .pkl.

    Os .pkl oficiais foram salvos em Python 2 com objetos do 'chumpy', que não
    funciona com numpy 2. Em vez de instalá-lo, guardamos o estado de cada
    objeto aqui e extraímos os arrays depois."""

    def __init__(self, *args, **kwargs):
        self._args = args

    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)
        else:
            self._state = state


class _ManoUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module.startswith(("chumpy", "scipy")):
            # subclasse com o nome original, para saber o tipo depois
            return type(name, (_Stub,), {"_cls": f"{module}.{name}"})
        if module.startswith("numpy.core"):              # pickles antigos, numpy 2
            module = module.replace("numpy.core", "numpy._core", 1)
        return super().find_class(module, name)


def _to_array(obj):
    """Converte o que veio do pickle (array, chumpy ou matriz esparsa) em ndarray."""
    if isinstance(obj, np.ndarray):
        return obj
    if isinstance(obj, _Stub):
        d = obj.__dict__
        if "indptr" in d:                                  # scipy.sparse (csc/csr)
            shape = d.get("_shape") or d.get("shape")
            data, idx, ptr = (np.asarray(d[k]) for k in ("data", "indices", "indptr"))
            dense = np.zeros(shape)
            csc = "csr" not in getattr(obj, "_cls", "")
            for k in range(len(ptr) - 1):
                sl = slice(ptr[k], ptr[k + 1])
                if csc:
                    dense[idx[sl], k] = data[sl]
                else:
                    dense[k, idx[sl]] = data[sl]
            return dense
        if "x" in d:                                       # chumpy.Ch
            return _to_array(d["x"])
        if "idxs" in d and "a" in d:                       # chumpy.reordering.Select
            flat = _to_array(d["a"]).ravel()               # (recorte de outro array)
            return flat[np.asarray(d["idxs"])].reshape(d["preferred_shape"])
        raise ValueError(f"objeto do pickle não reconhecido: {sorted(d)}")
    return np.asarray(obj)


def convert_pkl(pkl_path, npz_path):
    """MANO_*.pkl oficial -> .npz só com arrays numpy (feito uma única vez)."""
    with open(pkl_path, "rb") as fh:
        raw = _ManoUnpickler(fh, encoding="latin1").load()
    data = {
        "v_template": _to_array(raw["v_template"]),
        "shapedirs": _to_array(raw["shapedirs"]),
        "posedirs": _to_array(raw["posedirs"]),
        "J_regressor": _to_array(raw["J_regressor"]),
        "weights": _to_array(raw["weights"]),
        "kintree_table": _to_array(raw["kintree_table"]),
        "faces": _to_array(raw["f"]).astype(np.int64),
    }
    np.savez_compressed(npz_path, **data)
    return data


def load_mano(side):
    """Carrega mano_<side>.npz; se só existir o .pkl oficial, converte antes."""
    npz = os.path.join(MANO_DIR, f"mano_{side}.npz")
    pkl = os.path.join(MANO_DIR, f"MANO_{side.upper()}.pkl")
    if os.path.exists(npz):
        return dict(np.load(npz))
    if os.path.exists(pkl):
        print(f"Convertendo {pkl} -> {npz} ...")
        return convert_pkl(pkl, npz)
    raise FileNotFoundError(f"coloque MANO_{side.upper()}.pkl em {MANO_DIR}")


# =============================================================================
# Rotações
# =============================================================================
def cross3(a, b):
    """Produto vetorial de 2 vetores 3D (np.cross é ~10x mais lento nesse
    tamanho, e a pinça chama isto milhares de vezes por segundo)."""
    return np.array([a[1] * b[2] - a[2] * b[1],
                     a[2] * b[0] - a[0] * b[2],
                     a[0] * b[1] - a[1] * b[0]])


def rotation_between(a, b):
    """Menor rotação que leva a direção a até a direção b (sem 'torcer')."""
    a = a / np.sqrt(a @ a)
    b = b / (np.sqrt(b @ b) + 1e-12)
    v, c = cross3(a, b), float(a @ b)
    if c < -0.999999:                                  # 180°: qualquer eixo perpendicular
        axis = np.cross(a, [1.0, 0, 0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, [0, 1.0, 0])
        return axis_angle(axis, np.pi)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1.0 + c)


def axis_angle(axis, angle):
    """Fórmula de Rodrigues: rotação de `angle` rad em torno de `axis`."""
    k = axis / np.linalg.norm(axis)
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(angle) * kx + (1 - np.cos(angle)) * kx @ kx


def palm_frame(P):
    """Eixos da palma a partir de punho (0), base do indicador (5), do médio
    (9) e do mínimo (17). Colunas = (x ao longo do médio, y, z normal)."""
    x = P[9] - P[0]
    x = x / np.linalg.norm(x)
    z = np.cross(P[5] - P[0], P[17] - P[0])
    z = z - (z @ x) * x
    z = z / np.linalg.norm(z)
    return np.column_stack([x, np.cross(z, x), z])


# =============================================================================
# Modelo: cinemática direta (skinning) e inversa
# =============================================================================
class ManoModel:
    def __init__(self, data):
        self.v_template = data["v_template"].astype(np.float64)
        self.shapedirs = data["shapedirs"].astype(np.float64)
        self.posedirs = data["posedirs"].reshape(-1, 3, data["posedirs"].shape[-1]).astype(np.float64)
        self.J_regressor = data["J_regressor"].astype(np.float64)
        self.weights = data["weights"].astype(np.float64)
        self.faces = data["faces"].astype(np.uint32)
        kt = data.get("kintree_table")
        self.parents = MANO_PARENTS if kt is None else np.where(kt[0] > 15, -1, kt[0]).astype(int)
        # Quanto cada vértice pertence a cada parte (soma dos pesos de skinning):
        # cor do vértice = mistura das cores das partes -> transições suaves.
        self.part_weights = np.stack(
            [self.weights[:, [j for j, p in enumerate(JOINT_PART) if p == part]].sum(1)
             for part in PARTS], axis=1)
        self.set_shape(np.zeros(self.shapedirs.shape[-1]))

    # ---------------------------------------------------------------- forma
    def set_shape(self, betas):
        """Aplica o formato da mão (10 betas; 0 = mão média) e pré-calcula a
        geometria de repouso usada pela cinemática inversa."""
        self.v_shaped = self.v_template + self.shapedirs @ betas
        self.J = self.J_regressor @ self.v_shaped                      # (16, 3)
        self.rest21 = self.landmarks21(self.J, self.v_shaped)

        normal = palm_frame(self.rest21)[:, 2]
        self.rest_dirs, self.flex_axes = {}, {}
        for j in range(1, 16):
            m = MP_OF_JOINT[j]
            d = self.rest21[m + 1] - self.rest21[m]
            self.rest_dirs[j] = d / np.linalg.norm(d)
            if j in FLEX_JOINTS:
                # eixo de flexão: perpendicular ao osso e à normal da palma
                axis = np.cross(self.rest_dirs[j], normal)
                self.flex_axes[j] = axis / np.linalg.norm(axis)
        self.hinge_axes = {j: self.flex_axes[j] for j in HINGE_JOINTS}
        self.rest_palm = palm_frame(self.rest21)
        self.rest_size = np.linalg.norm(self.rest21[9] - self.rest21[0])

    @staticmethod
    def landmarks21(joints, verts):
        return np.array([joints[i] if kind == "j" else verts[i] for kind, i in MP_FROM_MANO])

    # ----------------------------------------------------- cinemática direta
    def forward(self, R):
        """R = (16, 3, 3) rotações locais -> (vértices (778,3), juntas (16,3)).

        1) "pose blend shapes": pequenas correções da pele (dobras dos nós)
        2) cada articulação acumula a rotação dos pais (cinemática direta)
        3) skinning linear: cada vértice = média ponderada das transformações
        """
        n = len(self.parents)
        pose_feature = (R[1:] - np.eye(3)).ravel()                       # (135,)
        v_posed = self.v_shaped + self.posedirs @ pose_feature

        G = np.zeros((n, 4, 4))
        for j in range(n):
            local = np.eye(4)
            local[:3, :3] = R[j]
            p = self.parents[j]
            local[:3, 3] = self.J[j] - (self.J[p] if p >= 0 else 0)
            G[j] = local if p < 0 else G[p] @ local
        joints = G[:, :3, 3].copy()

        # Transformação relativa à pose de repouso (tira a posição original da junta)
        G[:, :3, 3] -= np.einsum("jab,jb->ja", G[:, :3, :3], self.J)
        T = np.einsum("vj,jab->vab", self.weights, G)                    # (778, 4, 4)
        verts = np.einsum("vab,vb->va", T[:, :3, :3], v_posed) + T[:, :3, 3]
        return verts, joints

    # ---------------------------------------------------- cinemática inversa
    def solve(self, P):
        """21 landmarks (qualquer escala/unidade) -> (16, 3, 3) rotações locais.

        Solução analítica, sem otimização:
          - punho: alinha os eixos da palma de repouso com os da palma observada
          - cada junta, do punho para as pontas: a menor rotação que faz o osso
            de repouso apontar para a direção observada, já descontando a
            rotação acumulada dos pais. PIP/DIP só dobram (dobradiça).
        """
        R = np.tile(np.eye(3), (16, 1, 1))
        G = [None] * 16                                   # rotação acumulada (global)
        R[0] = G[0] = palm_frame(P) @ self.rest_palm.T
        for j in range(1, 16):
            p = self.parents[j]
            m = MP_OF_JOINT[j]
            target = G[p].T @ (P[m + 1] - P[m])           # direção no sistema do pai
            if np.linalg.norm(target) < 1e-9:
                target = self.rest_dirs[j]
            if j in HINGE_JOINTS:
                R[j] = self._hinge(j, target)
            else:
                R[j] = rotation_between(self.rest_dirs[j], target)
            G[j] = G[p] @ R[j]
        return R

    def _hinge(self, j, target):
        axis, d = self.hinge_axes[j], self.rest_dirs[j]
        t = target - (target @ axis) * axis               # projeta no plano da dobra
        angle = np.arctan2(cross3(d, t) @ axis, d @ t)
        angle = np.clip(angle, -np.radians(MAX_HINGE_DEG), np.radians(MAX_HINGE_DEG))
        return axis_angle(axis, angle)

    # ------------------------------------------------- calibração (mão aberta)
    def flex_angles(self, R):
        """Flexão (rad) de cada junta dos 4 dedos em torno do eixo de dobra."""
        out = {}
        for j, axis in self.flex_axes.items():
            d = self.rest_dirs[j]
            t = R[j] @ d
            t = t - (t @ axis) * axis
            out[j] = float(np.arctan2(np.cross(d, t) @ axis, d @ t))
        return out

    def apply_flex_offsets(self, R, offsets):
        """Desconta a flexão medida com a mão aberta (só a flexão: a abertura
        lateral dos dedos continua como o MediaPipe mediu)."""
        R = R.copy()
        for j, off in offsets.items():
            R[j] = axis_angle(self.flex_axes[j], -off) @ R[j]
        return R

    # ------------------------------------------------------ pinça (contato)
    def _chain_fk(self, R, chain):
        """Rotações globais e posições das juntas de um dedo (punho fixo)."""
        rots, pos = [], []
        G, p, Jp = R[0], self.J[0], self.J[0]
        for j in chain:
            p = p + G @ (self.J[j] - Jp)
            G = G @ R[j]
            rots.append(G)
            pos.append(p)
            Jp = self.J[j]
        return rots, pos

    def _tip(self, R, chain, vert, fk=None):
        rots, pos = fk or self._chain_fk(R, chain)
        return pos[-1] + rots[-1] @ (self.v_shaped[vert] - self.J[chain[-1]])

    def _ccd_pass(self, R, chain, vert, target):
        """Uma volta de CCD (Cyclic Coordinate Descent): da junta da ponta até
        a da base, gira cada uma para a ponta do dedo apontar para o alvo."""
        for k in reversed(range(len(chain))):
            j = chain[k]
            rots, pos = self._chain_fk(R, chain)
            tip = self._tip(R, chain, vert, (rots, pos))
            a, b = tip - pos[k], target - pos[k]
            if a @ a < 1e-18 or b @ b < 1e-18:
                continue
            parent = R[0] if k == 0 else rots[k - 1]
            new = parent.T @ rotation_between(a, b) @ rots[k]
            R[j] = self._hinge(j, new @ self.rest_dirs[j]) if j in HINGE_JOINTS else new

    def pinch_contact(self, R, finger, w):
        """Leva as pontas do polegar e de `finger` da pele até o ponto médio
        entre elas, com peso w (0 = nada, 1 = encostadas).

        Necessário porque o MANO tem as proporções dele, não as suas: copiando
        só as direções dos ossos, as pontas nunca chegam a se encostar."""
        if w <= 0:
            return R
        thumb, thumb_vert, _ = FINGER_CHAINS["thumb"]
        chain, vert, _ = FINGER_CHAINS[finger]
        R = R.copy()
        gap0 = np.linalg.norm(self._tip(R, chain, vert) - self._tip(R, thumb, thumb_vert))
        goal = (1.0 - w) * gap0                       # distância final desejada
        # O CCD usa uma estimativa rápida da ponta (presa rigidamente ao último
        # osso). Nas dobras fortes a pele real desvia alguns mm disso, então:
        # 1ª rodada -> mede o desvio com o skinning completo -> 2ª rodada.
        bias_t = bias_f = np.zeros(3)
        for round_ in range(2):
            for _ in range(CCD_MAX_ITERATIONS):
                e_t = self._tip(R, thumb, thumb_vert) + bias_t
                e_f = self._tip(R, chain, vert) + bias_f
                D = e_f - e_t
                gap = np.linalg.norm(D)
                if gap <= goal + CCD_TOLERANCE_M:     # chegou (o MANO está em metros)
                    break
                # Alvo recalculado a cada volta: cada ponta anda metade do que
                # falta, uma em direção à outra. Se um dedo não alcança, na
                # volta seguinte o outro compensa.
                step = D / gap * (gap - goal) / 2
                self._ccd_pass(R, thumb, thumb_vert, e_t + step - bias_t)
                self._ccd_pass(R, chain, vert, e_f - step - bias_f)
            if round_ == 0:
                verts, _ = self.forward(R)
                bias_t = verts[thumb_vert] - self._tip(R, thumb, thumb_vert)
                bias_f = verts[vert] - self._tip(R, chain, vert)
        return R

    # -------------------------------------------------------------- tudo junto
    def fit(self, P, flex_offsets=None, contact=None):
        """Pose completa encaixada nos landmarks P: vértices no mesmo sistema
        de coordenadas (e escala) de P.

        flex_offsets: calibração de mão aberta ({junta: rad}) ou None
        contact:      (dedo, peso) do toque de pontas com o polegar, ou None
                      (ver detect_touch)
        """
        R = self.solve(P)
        if flex_offsets:
            R = self.apply_flex_offsets(R, flex_offsets)
        if contact:
            R = self.pinch_contact(R, *contact)
        verts, _ = self.forward(R)
        scale = np.linalg.norm(P[9] - P[0]) / self.rest_size
        return (verts - self.J[0]) * scale + P[0]


def detect_touch(P, img, cm_per_unit):
    """Qual dedo o polegar está tocando, e quanto (0..1).

    P:   21 landmarks 3D (unidades da cena); img: 21 landmarks 2D na imagem
    (x já multiplicado pela proporção da imagem); cm_per_unit: cm por unidade
    de P. Devolve (dedo, peso, distância na imagem / palma)."""
    palm = np.linalg.norm(img[9] - img[0]) + 1e-9
    best, best_d = None, np.inf
    for finger in ("index", "middle", "ring", "pinky"):
        lm = FINGER_CHAINS[finger][2]
        if np.linalg.norm(P[4] - P[lm]) * cm_per_unit > TOUCH_MAX_3D_CM:
            continue                                   # um atrás do outro
        d = np.linalg.norm(img[4] - img[lm]) / palm
        if d < best_d:
            best, best_d = finger, d
    if best is None:
        return None, 0.0, np.inf
    x = np.clip((TOUCH_START_PALM - best_d) / (TOUCH_START_PALM - TOUCH_CONTACT_PALM), 0.0, 1.0)
    return best, float(x * x * (3 - 2 * x)), float(best_d)   # smoothstep: entra sem "salto"


def vertex_normals(verts, faces):
    """Normais por vértice (soma das normais das faces vizinhas), vetorizado."""
    tri = verts[faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    vn = np.zeros_like(verts)
    for k in range(3):
        np.add.at(vn, faces[:, k], fn)
    return (vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)).astype(np.float32)


# =============================================================================
# Item para a cena 3D
# =============================================================================
class SkinHand:
    """Um GLMeshItem com a malha MANO, re-deformada a cada frame.

    Uso:
        skin = SkinHand(gl_view)          # FileNotFoundError se faltar o MANO
        skin.set_pose(landmarks, mirrored)
        skin.hide()                       # some até a próxima pose
    """

    def __init__(self, view, models=None):
        if models is None:
            models = {}
            for side in ("right", "left"):
                try:
                    models[side] = ManoModel(load_mano(side))
                except FileNotFoundError:
                    pass
            if not models:
                raise FileNotFoundError(f"arquivos MANO não encontrados em {MANO_DIR}")
        self.models = models
        any_model = next(iter(models.values()))
        self.item = gl.GLMeshItem(
            vertexes=any_model.v_shaped.astype(np.float32), faces=any_model.faces,
            smooth=True, color=SKIN_COLOR, shader=SKIN_SHADER, glOptions="opaque")
        self.item.setVisible(False)                   # aparece na 1ª pose
        view.addItem(self.item)
        self.side = None                              # modelo usado no último frame
        self.offsets = self._load_calibration()       # {"left"/"right": {junta: rad}}
        self._calib = None                            # lista de medições em andamento
        self.part_colors = None                       # {parte: rgba} ou None = cor de pele
        self._last = None                             # (modelo, vértices) do último frame

    def set_part_colors(self, colors):
        """Cor por parte da mão ({"index": (r,g,b,a), ...}; partes ausentes
        ficam com a cor de pele). Redesenha a última pose na hora."""
        self.part_colors = colors
        if self._last is not None:
            self._upload(*self._last)

    def _upload(self, model, verts):
        kw = {}
        if self.part_colors:
            C = np.array([self.part_colors.get(p, SKIN_COLOR) for p in PARTS], dtype=np.float64)
            kw["vertexColors"] = np.clip(model.part_weights @ C, 0, 1).astype(np.float32)
        md = gl.MeshData(vertexes=verts.astype(np.float32), faces=model.faces, **kw)
        # Normais prontas: evita o laço Python por vértice do MeshData.
        md._vertexNormals = vertex_normals(verts, model.faces)
        self.item.setMeshData(meshdata=md)

    # ------------------------------------------------- calibração (mão aberta)
    @staticmethod
    def _load_calibration():
        try:
            with open(CALIBRATION_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
            return {side: {int(j): v for j, v in offs.items()} for side, offs in data.items()}
        except (OSError, ValueError):
            return {}

    def start_calibration(self):
        """Mede os próximos CALIBRATION_FRAMES frames com a mão ABERTA."""
        self._calib = []

    def calibration_status(self):
        """(medidos, total) durante a calibração; senão None."""
        return None if self._calib is None else (len(self._calib), CALIBRATION_FRAMES)

    def _collect_calibration(self, model, P):
        self._calib.append(model.flex_angles(model.solve(P)))
        if len(self._calib) < CALIBRATION_FRAMES:
            return
        # Média por junta -> quanto o MediaPipe "dobra" um dedo esticado
        self.offsets[self.side] = {j: float(np.mean([m[j] for m in self._calib]))
                                   for j in self._calib[0]}
        self._calib = None
        os.makedirs(MANO_DIR, exist_ok=True)
        with open(CALIBRATION_FILE, "w", encoding="utf-8") as fh:
            json.dump(self.offsets, fh, indent=1)

    def hide(self):
        """Esconde a mão até a próxima pose."""
        self.item.setVisible(False)

    def set_pose(self, L, mirrored, img=None, cm_per_unit=None):
        """L = 21 landmarks 3D; img = 21 landmarks na imagem (ativa o toque de
        pontas, junto com cm_per_unit = cm por unidade de L)."""
        # Imagem espelhada + mão real direita = geometria de mão esquerda ->
        # modelo MANO esquerdo (se existir).
        side = "left" if mirrored else "right"
        self.side = side if side in self.models else next(iter(self.models))
        model = self.models[self.side]
        P = np.asarray(L, dtype=np.float64)
        if self._calib is not None:
            self._collect_calibration(model, P)
        contact = None
        if img is not None and cm_per_unit:
            finger, weight, _ = detect_touch(P, np.asarray(img, dtype=np.float64), cm_per_unit)
            contact = (finger, weight) if weight > 0 else None
        verts = model.fit(P, self.offsets.get(self.side), contact)
        self._last = (model, verts)
        self._upload(model, verts)
        self.item.setVisible(True)

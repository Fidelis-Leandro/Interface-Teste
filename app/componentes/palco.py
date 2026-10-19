"""Palco da avaliação: mão 3D, vista principal + miniatura e a barra acima dele."""

from PyQt5 import QtCore, QtGui, QtWidgets

import pyqtgraph as pg
import pyqtgraph.opengl as gl

import geometria
import hand_skin
from app.tema import *  # noqa: F401,F403


class Hand3D:
    """GLViewWidget com a pele MANO. Sem os arquivos do MANO, mostra só a grade
    (as medições continuam funcionando; veja assets/mano/LEIA-ME.txt)."""

    def __init__(self):
        self.view = gl.GLViewWidget()
        self.view.setBackgroundColor(VIEW_BG)     # escuro nos dois temas (área de vídeo)
        grid = gl.GLGridItem()
        grid.setSize(x=4, y=4)
        grid.setSpacing(x=0.25, y=0.25)
        grid.setColor((60, 75, 90, 110))
        self.view.addItem(grid)
        self.reset_camera()
        try:
            self.skin = hand_skin.SkinHand(self.view)
        except FileNotFoundError as exc:
            print(f"Mão 3D indisponível: {exc}")
            self.skin = None
            # aviso na própria tela: sem ele, a área vazia parece defeito
            note = QtWidgets.QLabel("Mão 3D não instalada (modelo MANO).\n"
                                    "As medidas funcionam normalmente.\n"
                                    "Para instalar: Instalar mao 3D.bat (veja assets/mano/LEIA-ME.txt).",
                                    self.view)
            note.setStyleSheet(f"color: {VIEW_MUTED}; background: transparent; font-size: 13px;"
                               " padding-bottom: 4px;")   # sem isso o "_" da última linha fica cortado
            note.ensurePolished()                 # aplica a fonte do estilo antes de medir o texto
            note.adjustSize()
            note.move(16, 16)

    def reset_camera(self):
        self.view.setCameraPosition(distance=5, elevation=12, azimuth=-90)
        self.view.opts["center"] = pg.Vector(0, 0, 1.1)
        self.view.update()

    def start_calibration(self):
        if self.skin:
            self.skin.start_calibration()

    def update(self, landmarks, mirrored, img):
        if self.skin:
            self.skin.set_pose(landmarks, mirrored, img=img, cm_per_unit=100.0 / geometria.WORLD_SCALE)

    def set_finger_colors(self, colors):
        if self.skin:
            self.skin.set_part_colors(colors)

    def show_neutral(self):
        """Mão aberta e parada, só para ilustrar a tela (ex.: durante as dicas)."""
        if self.skin and self.skin.calibration_status() is None:
            self.skin.set_pose(geometria.world_to_gl(geometria.build_hand_world([3, 3, 3, 3], 3)), True)

    def hide_until_pose(self):
        """Esconde a mão ilustrativa: ela volta quando a câmera achar a mão de verdade."""
        if self.skin:
            self.skin.hide()


# =============================================================================
# PALCO: vista principal + miniatura (câmera <-> 3D)
# =============================================================================
class ViewStage(QtWidgets.QWidget):
    """Duas vistas sempre visíveis: uma ocupa o palco, a outra fica em
    miniatura no canto. Clique na miniatura = trocar. Os widgets nunca mudam
    de pai (o OpenGL não gosta disso): só trocam de posição e tamanho.
    Os rótulos sobre a imagem usam as cores VIEW_* (o palco é escuro nos dois temas)."""

    swapped = QtCore.pyqtSignal(bool)          # True = câmera é a vista principal

    def __init__(self, gl_view):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: #000;")
        self.camera_main = False

        self.cam = QtWidgets.QLabel("Aguardando câmera…", self)
        self.cam.setAlignment(QtCore.Qt.AlignCenter)
        self.cam.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.gl_frame = QtWidgets.QFrame(self)
        lay = QtWidgets.QVBoxLayout(self.gl_frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(gl_view)
        self.gl = gl_view
        for w in (self.cam, self.gl):
            w.installEventFilter(self)
        self._qimage = None

        # nome da miniatura + como trocar (antes: rótulo de 10 px sem nome)
        self.mini_caption = QtWidgets.QLabel(self)
        self.mini_caption.setStyleSheet(f"color: {VIEW_TEXT}; font-size: 12px; background: rgba(0,0,0,170);"
                                        " padding: 3px 8px; border-radius: 4px;")
        self.legend = QtWidgets.QLabel(self)
        self.legend.setStyleSheet(f"color: {VIEW_MUTED}; font-size: 12px; background: rgba(11,17,24,200);"
                                  " padding: 5px 9px; border-radius: 4px;")
        grade = VIEW_GRADE_COLOR
        self.legend.setText(f"Cor de cada dedo = % do normal na sessão &nbsp;&nbsp;"
                            f"{swatch(grade['ruim'])} abaixo de 50% &nbsp; {swatch(grade['regular'])} 50 a 75%"
                            f" &nbsp; {swatch(grade['bom'])} acima de 75%")
        # faixa de aviso curta, sem escurecer a imagem (ex.: "vire a palma")
        self.banner = QtWidgets.QLabel(self)
        self.banner.setAlignment(QtCore.Qt.AlignCenter)
        self.banner.setStyleSheet(f"color: {ON_WARN}; background: {WARN}; font-size: 15px;"
                                  " font-weight: 600; padding: 8px 18px; border-radius: 6px;")
        self.banner.hide()
        # aviso de orientação: escurece o palco inteiro + cartão com borda
        self.overlay = QtWidgets.QWidget(self)
        self.overlay.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.overlay.setStyleSheet("background: rgba(0, 0, 0, 150);")
        self.overlay_card = QtWidgets.QLabel(self.overlay)
        self.overlay_card.setAlignment(QtCore.Qt.AlignCenter)
        self.overlay_card.setWordWrap(True)
        self.overlay_card.setStyleSheet(f"color: {TEXT}; background: {SURFACE}; border: 1px solid {ACCENT};"
                                        " border-radius: 12px; padding: 24px 30px;")
        self.overlay.hide()
        self._apply_styles()

    # ------------------------------------------------------------ interação
    def eventFilter(self, obj, ev):
        mini = self.gl if self.camera_main else self.cam
        if obj is mini and ev.type() == QtCore.QEvent.MouseButtonPress:
            self.swap()
            return True                                # não gira o 3D no clique
        return False

    def swap(self):
        self.set_camera_main(not self.camera_main)

    def set_camera_main(self, camera_main):
        if camera_main == self.camera_main:
            return
        self.camera_main = camera_main
        self._apply_styles()
        self._layout()
        self._render_camera()
        self.swapped.emit(camera_main)

    def show_message(self, title, subtitle=None):
        """Cartão de orientação sobre o palco (None = esconde)."""
        if not title:
            if self.overlay.isVisible():
                self.overlay.hide()
            return
        html = f"<div style='font-size:22px; font-weight:600;'>{title}</div>"
        if subtitle:
            html += f"<div style='font-size:15px; color:{MUTED}; margin-top:8px;'>{subtitle}</div>"
        if html != self.overlay_card.text() or not self.overlay.isVisible():
            self.overlay_card.setText(html)
            self.overlay.show()
            self._layout()

    def show_banner(self, text):
        """Faixa amarela no alto do palco (None = esconde)."""
        if not text:
            if self.banner.isVisible():
                self.banner.hide()
            return
        if text != self.banner.text() or not self.banner.isVisible():
            self.banner.setText(text)
            self.banner.show()
            self._layout()

    def set_camera_frame(self, rgb):
        if rgb is None:
            return
        h, w = rgb.shape[:2]
        self._qimage = QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
        self._render_camera()

    def _render_camera(self):
        if self._qimage is not None:
            size = self.cam.contentsRect().size()
            self.cam.setPixmap(QtGui.QPixmap.fromImage(self._qimage).scaled(
                size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    # ---------------------------------------------------------------- layout
    def _apply_styles(self):
        mini_border = f"border: 2px solid {VIEW_ACCENT}; border-radius: 6px;"
        self.cam.setStyleSheet(f"background: #000; color: {VIEW_MUTED}; font-size: 14px;"
                               + (mini_border if not self.camera_main else "border: none;"))
        self.gl_frame.setStyleSheet("QFrame { " + (mini_border if self.camera_main else "border: none;")
                                    + " background: #000; }")
        self.gl_frame.layout().setContentsMargins(*(2, 2, 2, 2) if self.camera_main else (0, 0, 0, 0))
        self.mini_caption.setText(("Modelo 3D" if self.camera_main else "Câmera") + "  ·  clique para ampliar")

    def resizeEvent(self, ev):
        self._layout()
        self._render_camera()

    def _layout(self):
        r = self.rect()
        main, mini = (self.cam, self.gl_frame) if self.camera_main else (self.gl_frame, self.cam)
        main.setGeometry(r)
        mw = max(200, int(r.width() * 0.27))
        mh = int(mw * 0.75)
        mini.setGeometry(r.width() - mw - 14, r.height() - mh - 14, mw, mh)
        main.lower()
        mini.raise_()
        self.mini_caption.adjustSize()
        self.mini_caption.move(mini.x() + 8, mini.y() + 8)
        self.legend.adjustSize()
        self.legend.move(12, r.height() - self.legend.height() - 12)
        self.legend.setVisible(not self.camera_main)
        if self.banner.isVisible():
            self.banner.adjustSize()
            self.banner.move((r.width() - self.banner.width()) // 2, 14)
        if self.overlay.isVisible():
            self.overlay.setGeometry(r)
            ow = min(int(r.width() * 0.7), 540)
            self.overlay_card.setFixedWidth(ow)
            self.overlay_card.adjustSize()
            self.overlay_card.move((r.width() - ow) // 2, (r.height() - self.overlay_card.height()) // 2)
        for w in (self.mini_caption, self.legend, self.banner, self.overlay):
            w.raise_()


class StageToolbar(QtWidgets.QWidget):
    """Barra fixa acima do palco: qual vista é a principal, centralizar o 3D
    e tela cheia. Antes eram botões flutuantes e translúcidos sobre o 3D."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(44)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 6)
        h.setSpacing(8)
        self.btn_3d = button("Modelo 3D", "cube", "quiet", checkable=True)
        self.btn_cam = button("Câmera", "camera", "quiet", checkable=True)
        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        for b in (self.btn_3d, self.btn_cam):
            group.addButton(b)
            h.addWidget(b)
        self.btn_3d.setChecked(True)
        h.addSpacing(10)
        self.hint = label("Arraste para girar  ·  roda do mouse para aproximar", 12, MUTED)
        # pode ser cortada: com a janela estreita, a dica não deve alargar a tela inteira
        self.hint.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        h.addWidget(self.hint, stretch=1)
        h.addStretch()
        self.btn_center = button("Centralizar", "crosshair", "quiet")
        self.btn_center.setToolTip("Volta o modelo 3D para a posição de frente")
        self.btn_full = button("Tela cheia", "maximize", "quiet")
        self.btn_tips = button("Dicas", "help", "quiet")
        self.btn_tips.setToolTip("Mostra de novo as dicas sobre esta tela")
        h.addWidget(self.btn_center)
        h.addWidget(self.btn_full)
        h.addWidget(self.btn_tips)

    def sync(self, camera_main):
        (self.btn_cam if camera_main else self.btn_3d).setChecked(True)
        self.hint.setVisible(not camera_main)
        self.btn_center.setVisible(not camera_main)

    def set_expanded(self, expanded):
        self.btn_full.setText("Sair da tela cheia" if expanded else "Tela cheia")
        set_button_icon(self.btn_full, "minimize" if expanded else "maximize", "quiet")

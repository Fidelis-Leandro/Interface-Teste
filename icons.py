"""
Ícones vetoriais (SVG) da interface - substituem emojis e símbolos de texto,
que mudam de aparência conforme a fonte instalada no Windows.

Desenhados aqui mesmo (grade 24x24, traço 2 px, pontas arredondadas), então
não dependem de pacote nem licença externa. "currentColor" é trocado pela
cor pedida na hora de desenhar.

    from icons import icon, pixmap
    botao.setIcon(icon("pause", "#e6edf3"))
    rotulo.setPixmap(pixmap("alert", "#ffb300", 16))
"""

from PyQt5 import QtCore, QtGui, QtSvg, QtWidgets

_STROKE = ('fill="none" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round"')

_PATHS = {
    # vistas
    "cube": f'<path {_STROKE} d="M12 2.5 L20.5 7.2 V16.8 L12 21.5 L3.5 16.8 V7.2 Z'
            f' M3.5 7.2 L12 12 L20.5 7.2 M12 12 V21.5"/>',
    "camera": f'<rect {_STROKE} x="2.5" y="6.5" width="19" height="13.5" rx="2.5"/>'
              f'<circle {_STROKE} cx="12" cy="13.2" r="3.6"/>'
              f'<path {_STROKE} d="M8.5 6.5 L10 4 H14 L15.5 6.5"/>',
    "maximize": f'<path {_STROKE} d="M4 9 V4 H9 M20 9 V4 H15 M4 15 V20 H9 M20 15 V20 H15"/>',
    "minimize": f'<path {_STROKE} d="M9 4 V9 H4 M15 4 V9 H20 M9 20 V15 H4 M15 20 V15 H20"/>',
    "crosshair": f'<circle {_STROKE} cx="12" cy="12" r="7"/>'
                 f'<path {_STROKE} d="M12 2.5 V6 M12 18 V21.5 M2.5 12 H6 M18 12 H21.5"/>',
    # estados
    "alert": f'<path {_STROKE} d="M12 3.5 L21.5 20 H2.5 Z"/>'
             f'<path {_STROKE} d="M12 9.5 V14"/><path {_STROKE} d="M12 17 V17.2"/>',
    "dot": '<circle fill="currentColor" cx="12" cy="12" r="5"/>',
    "ring": f'<circle {_STROKE} cx="12" cy="12" r="5"/>',
    "clock": f'<circle {_STROKE} cx="12" cy="12" r="9"/><path {_STROKE} d="M12 7 V12 L15.5 14"/>',
    # ações
    # (sem repetir atributos: um atributo duplicado invalida o SVG e o ícone some)
    "pause": f'<path {_STROKE} d="M9 5.5 V18.5 M15 5.5 V18.5"/>',
    "play": '<path fill="currentColor" d="M8 5 L19 12 L8 19 Z"/>',
    "refresh": f'<path {_STROKE} d="M19.5 12 A7.5 7.5 0 1 1 17.3 6.7"/>'
               f'<path {_STROKE} d="M18 3 V7.2 H13.8"/>',
    "stop": '<rect fill="currentColor" x="6.5" y="6.5" width="11" height="11" rx="1.8"/>',
    "download": f'<path {_STROKE} d="M12 4 V15 M7 10.5 L12 15.5 L17 10.5 M5 20 H19"/>',
    "check": f'<path {_STROKE} d="M5 12.5 L10 17.5 L19 7"/>',
    # navegação e telas
    "back": f'<path {_STROKE} d="M14.5 5 L7.5 12 L14.5 19"/>',
    "plus": f'<path {_STROKE} d="M12 5 V19 M5 12 H19"/>',
    "settings": f'<circle {_STROKE} cx="12" cy="12" r="3"/><circle {_STROKE} cx="12" cy="12" r="7"/>'
                f'<path {_STROKE} d="M12 2.5 V5 M12 19 V21.5 M2.5 12 H5 M19 12 H21.5"/>',
    "file": f'<path {_STROKE} d="M6 3 H14 L19 8 V21 H6 Z M14 3 V8 H19 M9 13 H16 M9 17 H16"/>',
    "trash": f'<path {_STROKE} d="M4 7 H20 M9 7 V4 H15 V7 M6.5 7 L7.5 20 H16.5 L17.5 7 M10 11 V16 M14 11 V16"/>',
    "search": f'<circle {_STROKE} cx="11" cy="11" r="6.5"/><path {_STROKE} d="M16 16 L20.5 20.5"/>',
    "edit": f'<path {_STROKE} d="M4 20 H8 L19 9 L15 5 L4 16 Z M13 7 L17 11"/>',
    "help": f'<circle {_STROKE} cx="12" cy="12" r="9"/>'
            f'<path {_STROKE} d="M9.3 9.4 A2.8 2.8 0 1 1 13.4 11.9 C12.5 12.4 12 13 12 14"/>'
            f'<path {_STROKE} d="M12 17 V17.2"/>',
}


def _svg(name, color):
    body = _PATHS[name].replace("currentColor", color)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'


def pixmap(name, color, size=18):
    """Ícone como QPixmap nítido (respeita a escala de tela do Windows)."""
    app = QtWidgets.QApplication.instance()
    dpr = app.devicePixelRatio() if app else 1.0
    pm = QtGui.QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(QtCore.Qt.transparent)
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(_svg(name, color).encode()))
    p = QtGui.QPainter(pm)
    renderer.render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name, color, size=18):
    return QtGui.QIcon(pixmap(name, color, size))

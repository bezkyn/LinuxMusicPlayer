#!/usr/bin/env python3
"""Linux Music Player: tocador de músicas com biblioteca.

Precisa de: python3-pyqt6 e python3-pyqt6.qtmultimedia.
Opcional:   python3-mutagen, para mostrar tags, duração e capas.
Uso:  python3 linux-music-player.py [PASTA_OU_ARQUIVOS...]   (toca na hora, sem pôr na biblioteca)
"""
import base64
import hashlib
import json
import math
import os
import random
import re
import sys

os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*=false")   # menos mensagens no terminal
try:
    import mutagen
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import ID3
    from mutagen.mp4 import MP4
except ImportError:
    mutagen = None

from PyQt6 import sip  # noqa: E402
from PyQt6.QtCore import (QByteArray, QEvent, QMimeData, QPointF, QRect, QRectF, QSettings,  # noqa: E402
                          QSize, Qt, QThread, QTimer, QUrl, pyqtSignal)
from PyQt6.QtGui import (QAction, QActionGroup, QBrush, QColor, QDesktopServices,  # noqa: E402
                         QFont, QFontDatabase, QFontMetrics, QIcon, QImage, QKeySequence,
                         QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF, QShortcut)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer  # noqa: E402
try:
    from PyQt6.QtSvg import QSvgRenderer  # noqa: E402
except ImportError:                                  # sem python3-pyqt6.qtsvg: fica sem ícones
    QSvgRenderer = None
from PyQt6.QtWidgets import (  # noqa: E402
    QAbstractItemView, QApplication, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPushButton, QSizePolicy, QSlider, QSplitter, QStackedWidget, QStyle,
    QStyledItemDelegate, QStyleOptionViewItem, QTableWidget, QTableWidgetItem, QToolButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

__version__ = "1.0.0"
APP = "reprodutor"
EXTS = {".mp3", ".m4a", ".mp4", ".aac", ".flac", ".ogg", ".oga", ".opus",
        ".wav", ".aif", ".aiff", ".webm", ".mka", ".wma"}
REPEAT = ["Sem repetir", "Repetir lista", "Repetir faixa"]
MIME = "application/x-reprodutor-caminhos"
ROLE = Qt.ItemDataRole.UserRole
COL_ALBUM, COL_NUM, COL_TITLE, COL_DUR, COL_RATE, COL_ARTIST = range(6)
THEME_CHANGE = 210                     # QEvent::ThemeChange (o PyQt6 não tem o nome)
ALBUM_W, COVER, ROW_H, HEAD_H, GAP = 256, 92, 32, 38, 12   # medidas da proposta (px)


def _xdg(var, default):
    return os.path.join(os.environ.get(var) or os.path.expanduser(default), APP)


CACHE_DIR = _xdg("XDG_CACHE_HOME", "~/.cache")
DATA_DIR = _xdg("XDG_DATA_HOME", "~/.local/share")
COVER_DIR = os.path.join(CACHE_DIR, "capas")
CACHE_FILE = os.path.join(CACHE_DIR, "biblioteca.json")
LISTS_DIR = os.path.join(DATA_DIR, "listas")
RATINGS_FILE = os.path.join(DATA_DIR, "notas.json")
QUEUE_FILE = os.path.join(DATA_DIR, "lista-atual.json")


# ================================================================ utilidades
def fmt(seconds):
    s = int(seconds or 0)
    h, m, s = s // 3600, s // 60 % 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_total(seconds):
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} horas".replace(".", ",")
    if seconds >= 60:
        return f"{round(seconds / 60)} minuto(s)"
    return f"{int(seconds)} segundo(s)"


def _int(text):
    try:
        return int(str(text).split("/")[0])
    except (ValueError, TypeError):
        return 0


def _first(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value) if value is not None else ""


def _stars_from_popm(r):
    """Nota do Windows Media Player / Winamp (0-255) para 0-5 estrelas."""
    if not r:
        return 0
    return 1 if r < 32 else 2 if r < 96 else 3 if r < 160 else 4 if r < 224 else 5


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


# Ícones Phosphor 2.1.1 (https://phosphoricons.com), licença MIT, Copyright (c) 2023
# Phosphor Icons. Só o miolo do SVG (viewBox 0 0 256 256): (contorno, preenchido).
PHOSPHOR = {
    'user': ('<path d="M230.92,212c-15.23-26.33-38.7-45.21-66.09-54.16a72,72,0,1,0-73.66,0C63.78,166.78,40.31,185.66,25.08,212a8,8,0,1,0,13.85,8c18.84-32.56,52.14-52,89.07-52s70.23,19.44,89.07,52a8,8,0,1,0,13.85-8ZM72,96a56,56,0,1,1,56,56A56.06,56.06,0,0,1,72,96Z"/>',
        '<path d="M230.93,220a8,8,0,0,1-6.93,4H32a8,8,0,0,1-6.92-12c15.23-26.33,38.7-45.21,66.09-54.16a72,72,0,1,1,73.66,0c27.39,8.95,50.86,27.83,66.09,54.16A8,8,0,0,1,230.93,220Z"/>'),
    'tag': ('<path d="M243.31,136,144,36.69A15.86,15.86,0,0,0,132.69,32H40a8,8,0,0,0-8,8v92.69A15.86,15.86,0,0,0,36.69,144L136,243.31a16,16,0,0,0,22.63,0l84.68-84.68a16,16,0,0,0,0-22.63Zm-96,96L48,132.69V48h84.69L232,147.31ZM96,84A12,12,0,1,1,84,72,12,12,0,0,1,96,84Z"/>',
        '<path d="M243.31,136,144,36.69A15.86,15.86,0,0,0,132.69,32H40a8,8,0,0,0-8,8v92.69A15.86,15.86,0,0,0,36.69,144L136,243.31a16,16,0,0,0,22.63,0l84.68-84.68a16,16,0,0,0,0-22.63ZM84,96A12,12,0,1,1,96,84,12,12,0,0,1,84,96Z"/>'),
    'palette': ('<path d="M200.77,53.89A103.27,103.27,0,0,0,128,24h-1.07A104,104,0,0,0,24,128c0,43,26.58,79.06,69.36,94.17A32,32,0,0,0,136,192a16,16,0,0,1,16-16h46.21a31.81,31.81,0,0,0,31.2-24.88,104.43,104.43,0,0,0,2.59-24A103.28,103.28,0,0,0,200.77,53.89Zm13,93.71A15.89,15.89,0,0,1,198.21,160H152a32,32,0,0,0-32,32,16,16,0,0,1-21.31,15.07C62.49,194.3,40,164,40,128a88,88,0,0,1,87.09-88h.9a88.35,88.35,0,0,1,88,87.25A88.86,88.86,0,0,1,213.81,147.6ZM140,76a12,12,0,1,1-12-12A12,12,0,0,1,140,76ZM96,100A12,12,0,1,1,84,88,12,12,0,0,1,96,100Zm0,56a12,12,0,1,1-12-12A12,12,0,0,1,96,156Zm88-56a12,12,0,1,1-12-12A12,12,0,0,1,184,100Z"/>',
        '<path d="M200.77,53.89A103.27,103.27,0,0,0,128,24h-1.07A104,104,0,0,0,24,128c0,43,26.58,79.06,69.36,94.17A32,32,0,0,0,136,192a16,16,0,0,1,16-16h46.21a31.81,31.81,0,0,0,31.2-24.88,104.43,104.43,0,0,0,2.59-24A103.28,103.28,0,0,0,200.77,53.89ZM84,168a12,12,0,1,1,12-12A12,12,0,0,1,84,168Zm0-56a12,12,0,1,1,12-12A12,12,0,0,1,84,112Zm44-24a12,12,0,1,1,12-12A12,12,0,0,1,128,88Zm44,24a12,12,0,1,1,12-12A12,12,0,0,1,172,112Z"/>'),
    'arrows-clockwise': ('<path d="M224,48V96a8,8,0,0,1-8,8H168a8,8,0,0,1,0-16h28.69L182.06,73.37a79.56,79.56,0,0,0-56.13-23.43h-.45A79.52,79.52,0,0,0,69.59,72.71,8,8,0,0,1,58.41,61.27a96,96,0,0,1,135,.79L208,76.69V48a8,8,0,0,1,16,0ZM186.41,183.29a80,80,0,0,1-112.47-.66L59.31,168H88a8,8,0,0,0,0-16H40a8,8,0,0,0-8,8v48a8,8,0,0,0,16,0V179.31l14.63,14.63A95.43,95.43,0,0,0,130,222.06h.53a95.36,95.36,0,0,0,67.07-27.33,8,8,0,0,0-11.18-11.44Z"/>',
        '<path d="M224,48V96a8,8,0,0,1-8,8H168a8,8,0,0,1-5.66-13.66L180.65,72a79.48,79.48,0,0,0-54.72-22.09h-.45A79.52,79.52,0,0,0,69.59,72.71,8,8,0,0,1,58.41,61.27,96,96,0,0,1,192,60.7l18.36-18.36A8,8,0,0,1,224,48ZM186.41,183.29A80,80,0,0,1,75.35,184l18.31-18.31A8,8,0,0,0,88,152H40a8,8,0,0,0-8,8v48a8,8,0,0,0,13.66,5.66L64,195.3a95.42,95.42,0,0,0,66,26.76h.53a95.36,95.36,0,0,0,67.07-27.33,8,8,0,0,0-11.18-11.44Z"/>'),
    'books': ('<path d="M231.65,194.55,198.46,36.75a16,16,0,0,0-19-12.39L132.65,34.42a16.08,16.08,0,0,0-12.3,19l33.19,157.8A16,16,0,0,0,169.16,224a16.25,16.25,0,0,0,3.38-.36l46.81-10.06A16.09,16.09,0,0,0,231.65,194.55ZM136,50.15c0-.06,0-.09,0-.09l46.8-10,3.33,15.87L139.33,66Zm6.62,31.47,46.82-10.05,3.34,15.9L146,97.53Zm6.64,31.57,46.82-10.06,13.3,63.24-46.82,10.06ZM216,197.94l-46.8,10-3.33-15.87L212.67,182,216,197.85C216,197.91,216,197.94,216,197.94ZM104,32H56A16,16,0,0,0,40,48V208a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V48A16,16,0,0,0,104,32ZM56,48h48V64H56Zm0,32h48v96H56Zm48,128H56V192h48v16Z"/>',
        '<path d="M231.65,194.55,198.46,36.75a16,16,0,0,0-19-12.39L132.65,34.42a16.08,16.08,0,0,0-12.3,19l33.19,157.8A16,16,0,0,0,169.16,224a16.25,16.25,0,0,0,3.38-.36l46.81-10.06A16.09,16.09,0,0,0,231.65,194.55ZM136,50.15c0-.06,0-.09,0-.09l46.8-10,3.33,15.87L139.33,66Zm10,47.38-3.35-15.9,46.82-10.06,3.34,15.9Zm70,100.41-46.8,10-3.33-15.87L212.67,182,216,197.85C216,197.91,216,197.94,216,197.94ZM104,32H56A16,16,0,0,0,40,48V208a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V48A16,16,0,0,0,104,32ZM56,48h48V64H56Zm48,160H56V192h48v16Z"/>'),
    'file-audio': ('<path d="M99.06,128.61a8,8,0,0,0-8.72,1.73L68.69,152H48a8,8,0,0,0-8,8v40a8,8,0,0,0,8,8H68.69l21.65,21.66A8,8,0,0,0,104,224V136A8,8,0,0,0,99.06,128.61ZM88,204.69,77.66,194.34A8,8,0,0,0,72,192H56V168H72a8,8,0,0,0,5.66-2.34L88,155.31ZM152,180a40.55,40.55,0,0,1-20,34.91A8,8,0,0,1,124,201.09a24.49,24.49,0,0,0,0-42.18A8,8,0,0,1,132,145.09,40.55,40.55,0,0,1,152,180Zm61.66-97.66-56-56A8,8,0,0,0,152,24H56A16,16,0,0,0,40,40v80a8,8,0,0,0,16,0V40h88V88a8,8,0,0,0,8,8h48V216H168a8,8,0,0,0,0,16h32a16,16,0,0,0,16-16V88A8,8,0,0,0,213.66,82.34ZM160,51.31,188.69,80H160Z"/>',
        '<path d="M152,180a40.55,40.55,0,0,1-20,34.91A8,8,0,0,1,124,201.09a24.49,24.49,0,0,0,0-42.18A8,8,0,0,1,132,145.09,40.55,40.55,0,0,1,152,180ZM99.06,128.61a8,8,0,0,0-8.72,1.73L68.69,152H48a8,8,0,0,0-8,8v40a8,8,0,0,0,8,8H68.69l21.65,21.66A8,8,0,0,0,104,224V136A8,8,0,0,0,99.06,128.61ZM216,88V216a16,16,0,0,1-16,16H168a8,8,0,0,1,0-16h32V96H152a8,8,0,0,1-8-8V40H56v80a8,8,0,0,1-16,0V40A16,16,0,0,1,56,24h96a8,8,0,0,1,5.66,2.34l56,56A8,8,0,0,1,216,88Zm-56-8h28.69L160,51.31Z"/>'),
    'floppy-disk': ('<path d="M219.31,72,184,36.69A15.86,15.86,0,0,0,172.69,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V83.31A15.86,15.86,0,0,0,219.31,72ZM168,208H88V152h80Zm40,0H184V152a16,16,0,0,0-16-16H88a16,16,0,0,0-16,16v56H48V48H172.69L208,83.31ZM160,72a8,8,0,0,1-8,8H96a8,8,0,0,1,0-16h56A8,8,0,0,1,160,72Z"/>',
        '<path d="M219.31,72,184,36.69A15.86,15.86,0,0,0,172.69,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V83.31A15.86,15.86,0,0,0,219.31,72ZM208,208H184V152a16,16,0,0,0-16-16H88a16,16,0,0,0-16,16v56H48V48H172.69L208,83.31ZM160,72a8,8,0,0,1-8,8H96a8,8,0,0,1,0-16h56A8,8,0,0,1,160,72Z"/>'),
    'folder': ('<path d="M216,72H131.31L104,44.69A15.86,15.86,0,0,0,92.69,40H40A16,16,0,0,0,24,56V200.62A15.4,15.4,0,0,0,39.38,216H216.89A15.13,15.13,0,0,0,232,200.89V88A16,16,0,0,0,216,72ZM40,56H92.69l16,16H40ZM216,200H40V88H216Z"/>',
        '<path d="M216,72H131.31L104,44.69A15.88,15.88,0,0,0,92.69,40H40A16,16,0,0,0,24,56V200.62A15.41,15.41,0,0,0,39.39,216h177.5A15.13,15.13,0,0,0,232,200.89V88A16,16,0,0,0,216,72ZM40,56H92.69l16,16H40Z"/>'),
    'folder-open': ('<path d="M245,110.64A16,16,0,0,0,232,104H216V88a16,16,0,0,0-16-16H130.67L102.94,51.2a16.14,16.14,0,0,0-9.6-3.2H40A16,16,0,0,0,24,64V208h0a8,8,0,0,0,8,8H211.1a8,8,0,0,0,7.59-5.47l28.49-85.47A16.05,16.05,0,0,0,245,110.64ZM93.34,64,123.2,86.4A8,8,0,0,0,128,88h72v16H69.77a16,16,0,0,0-15.18,10.94L40,158.7V64Zm112,136H43.1l26.67-80H232Z"/>',
        '<path d="M245,110.64A16,16,0,0,0,232,104H216V88a16,16,0,0,0-16-16H130.67L102.94,51.2a16.14,16.14,0,0,0-9.6-3.2H40A16,16,0,0,0,24,64V208h0a8,8,0,0,0,8,8H211.1a8,8,0,0,0,7.59-5.47l28.49-85.47A16.05,16.05,0,0,0,245,110.64ZM93.34,64,123.2,86.4A8,8,0,0,0,128,88h72v16H69.77a16,16,0,0,0-15.18,10.94L40,158.7V64Z"/>'),
    'folder-plus': ('<path d="M216,72H131.31L104,44.69A15.86,15.86,0,0,0,92.69,40H40A16,16,0,0,0,24,56V200.62A15.4,15.4,0,0,0,39.38,216H216.89A15.13,15.13,0,0,0,232,200.89V88A16,16,0,0,0,216,72ZM92.69,56l16,16H40V56ZM216,200H40V88H216Zm-88-88a8,8,0,0,1,8,8v16h16a8,8,0,0,1,0,16H136v16a8,8,0,0,1-16,0V152H104a8,8,0,0,1,0-16h16V120A8,8,0,0,1,128,112Z"/>',
        '<path d="M216,72H131.31L104,44.69A15.88,15.88,0,0,0,92.69,40H40A16,16,0,0,0,24,56V200.62A15.41,15.41,0,0,0,39.39,216h177.5A15.13,15.13,0,0,0,232,200.89V88A16,16,0,0,0,216,72ZM40,56H92.69l16,16H40Zm112,96H136v16a8,8,0,0,1-16,0V152H104a8,8,0,0,1,0-16h16V120a8,8,0,0,1,16,0v16h16a8,8,0,0,1,0,16Z"/>'),
    'guitar': ('<path d="M249.66,46.34l-40-40a8,8,0,0,0-11.31,11.32L200.69,20,140.52,80.16C117.73,68.3,92.21,69.29,76.75,84.74a42.27,42.27,0,0,0-9.39,14.37A8.24,8.24,0,0,1,59.81,104c-14.59.49-27.26,5.72-36.65,15.11C11.08,131.22,6,148.6,8.74,168.07,11.4,186.7,21.07,205.15,36,220s33.34,24.56,52,27.22A71.13,71.13,0,0,0,98.1,248c15.32,0,28.83-5.23,38.76-15.16,9.39-9.39,14.62-22.06,15.11-36.65a8.24,8.24,0,0,1,4.92-7.55,42.12,42.12,0,0,0,14.37-9.39c15.45-15.46,16.44-41,4.58-63.77L236,55.31l2.34,2.34a8,8,0,1,0,11.32-11.31ZM160,167.93a26.12,26.12,0,0,1-8.95,5.83,24.24,24.24,0,0,0-15,21.89c-.36,10.46-4,19.41-10.43,25.88-8.44,8.43-21,11.95-35.36,9.89C75,229.25,59.73,221.19,47.27,208.73S26.75,181,24.58,165.81c-2-14.37,1.46-26.92,9.89-35.36C40.94,124,49.89,120.37,60.35,120h0a24.22,24.22,0,0,0,21.89-15,26.12,26.12,0,0,1,5.83-9c5.49-5.49,13-8.13,21.38-8.13a49.38,49.38,0,0,1,19.13,4.19L108.5,112.19a32,32,0,1,0,35.31,35.31l20.08-20.08C170.41,142.71,169.47,158.41,160,167.93Zm-10.4-61.48a72.9,72.9,0,0,1,5.93,6.75l-15.42,15.42a32.22,32.22,0,0,0-12.68-12.68l15.42-15.43A73,73,0,0,1,149.55,106.45ZM112,128a16,16,0,0,1,16,16h0a16,16,0,1,1-16-16Zm48.85-32.85a86.94,86.94,0,0,0-6.68-6L176,67.31,188.69,80l-21.83,21.82A86.94,86.94,0,0,0,160.86,95.14ZM200,68.68,187.32,56,212,31.31,224.69,44ZM93.66,194.33a8,8,0,0,1-11.31,11.32l-32-32a8,8,0,0,1,11.32-11.31Z"/>',
        '<path d="M249.66,46.34l-40-40a8,8,0,0,0-11.32,11.32L200.69,20,140.52,80.16C117.73,68.3,92.21,69.29,76.75,84.74a42.27,42.27,0,0,0-9.39,14.37A8.24,8.24,0,0,1,59.81,104c-14.59.49-27.26,5.72-36.65,15.11C11.08,131.22,6,148.6,8.74,168.07,11.4,186.7,21.07,205.15,36,220s33.34,24.56,52,27.22A71.13,71.13,0,0,0,98.1,248c15.32,0,28.83-5.23,38.76-15.16,9.39-9.39,14.62-22.06,15.11-36.65a8.24,8.24,0,0,1,4.92-7.55,42.22,42.22,0,0,0,14.37-9.39c15.45-15.46,16.44-41,4.58-63.77L236,55.31l2.34,2.35a8,8,0,0,0,11.32-11.32Zm-156,159.31a8,8,0,0,1-11.31,0l-32-32a8,8,0,0,1,11.32-11.31l32,32A8,8,0,0,1,93.66,205.65Zm42.14-45.86a28,28,0,1,1,0-39.59A28,28,0,0,1,135.8,159.79Zm31.06-58a86.94,86.94,0,0,0-6-6.68,85.23,85.23,0,0,0-6.69-6L176,67.31,188.69,80ZM200,68.68,187.32,56,212,31.31,224.69,44Z"/>'),
    'list-plus': ('<path d="M32,64a8,8,0,0,1,8-8H216a8,8,0,0,1,0,16H40A8,8,0,0,1,32,64Zm8,72H216a8,8,0,0,0,0-16H40a8,8,0,0,0,0,16Zm104,48H40a8,8,0,0,0,0,16H144a8,8,0,0,0,0-16Zm88,0H216V168a8,8,0,0,0-16,0v16H184a8,8,0,0,0,0,16h16v16a8,8,0,0,0,16,0V200h16a8,8,0,0,0,0-16Z"/>',
        '<path d="M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32ZM64,72H192a8,8,0,0,1,0,16H64a8,8,0,0,1,0-16Zm56,112H64a8,8,0,0,1,0-16h56a8,8,0,0,1,0,16Zm16-48H64a8,8,0,0,1,0-16h72a8,8,0,0,1,0,16Zm64,32H184v16a8,8,0,0,1-16,0V168H152a8,8,0,0,1,0-16h16V136a8,8,0,0,1,16,0v16h16a8,8,0,0,1,0,16Z"/>'),
    'magnifying-glass': ('<path d="M229.66,218.34l-50.07-50.06a88.11,88.11,0,1,0-11.31,11.31l50.06,50.07a8,8,0,0,0,11.32-11.32ZM40,112a72,72,0,1,1,72,72A72.08,72.08,0,0,1,40,112Z"/>',
        '<path d="M168,112a56,56,0,1,1-56-56A56,56,0,0,1,168,112Zm61.66,117.66a8,8,0,0,1-11.32,0l-50.06-50.07a88,88,0,1,1,11.32-11.31l50.06,50.06A8,8,0,0,1,229.66,229.66ZM112,184a72,72,0,1,0-72-72A72.08,72.08,0,0,0,112,184Z"/>'),
    'microphone-stage': ('<path d="M168,16A72.07,72.07,0,0,0,96,88a73.29,73.29,0,0,0,.63,9.42L27.12,192.22A15.93,15.93,0,0,0,28.71,213L43,227.29a15.93,15.93,0,0,0,20.78,1.59l94.81-69.53A73.29,73.29,0,0,0,168,160a72,72,0,1,0,0-144Zm56,72a55.72,55.72,0,0,1-11.16,33.52L134.49,43.16A56,56,0,0,1,224,88ZM54.32,216,40,201.68,102.14,117A72.37,72.37,0,0,0,139,153.86ZM112,88a55.67,55.67,0,0,1,11.16-33.51l78.34,78.34A56,56,0,0,1,112,88Zm-2.35,58.34a8,8,0,0,1,0,11.31l-8,8a8,8,0,1,1-11.31-11.31l8-8A8,8,0,0,1,109.67,146.33Z"/>',
        '<path d="M115.06,46.36a4,4,0,0,0-6.11.54A71.54,71.54,0,0,0,96,88a73.29,73.29,0,0,0,.63,9.42L27.12,192.22A15.93,15.93,0,0,0,28.71,213L43,227.29a15.93,15.93,0,0,0,20.78,1.59l94.81-69.53A73.29,73.29,0,0,0,168,160a71.54,71.54,0,0,0,41.09-12.93,4,4,0,0,0,.54-6.11Zm2.61,103.28-16,16a8,8,0,1,1-11.31-11.31l16-16a8,8,0,0,1,11.31,11.31Zm109.4-20.56a4,4,0,0,1-6.12.54L126.38,35.05a4,4,0,0,1,.54-6.12A71.93,71.93,0,0,1,227.07,129.08Z"/>'),
    'music-note-simple': ('<path d="M210.3,56.34l-80-24A8,8,0,0,0,120,40V148.26A48,48,0,1,0,136,184V50.75l69.7,20.91a8,8,0,1,0,4.6-15.32ZM88,216a32,32,0,1,1,32-32A32,32,0,0,1,88,216Z"/>',
        '<path d="M210.3,56.34l-80-24A8,8,0,0,0,120,40V148.26A48,48,0,1,0,136,184V50.75l69.7,20.91a8,8,0,1,0,4.6-15.32Z"/>'),
    'music-notes': ('<path d="M212.92,17.69a8,8,0,0,0-6.86-1.45l-128,32A8,8,0,0,0,72,56V166.08A36,36,0,1,0,88,196V110.25l112-28v51.83A36,36,0,1,0,216,164V24A8,8,0,0,0,212.92,17.69ZM52,216a20,20,0,1,1,20-20A20,20,0,0,1,52,216ZM88,93.75V62.25l112-28v31.5ZM180,184a20,20,0,1,1,20-20A20,20,0,0,1,180,184Z"/>',
        '<path d="M212.92,17.71a7.89,7.89,0,0,0-6.86-1.46l-128,32A8,8,0,0,0,72,56V166.1A36,36,0,1,0,88,196V102.25l112-28V134.1A36,36,0,1,0,216,164V24A8,8,0,0,0,212.92,17.71Z"/>'),
    'pause': ('<path d="M200,32H160a16,16,0,0,0-16,16V208a16,16,0,0,0,16,16h40a16,16,0,0,0,16-16V48A16,16,0,0,0,200,32Zm0,176H160V48h40ZM96,32H56A16,16,0,0,0,40,48V208a16,16,0,0,0,16,16H96a16,16,0,0,0,16-16V48A16,16,0,0,0,96,32Zm0,176H56V48H96Z"/>',
        '<path d="M216,48V208a16,16,0,0,1-16,16H160a16,16,0,0,1-16-16V48a16,16,0,0,1,16-16h40A16,16,0,0,1,216,48ZM96,32H56A16,16,0,0,0,40,48V208a16,16,0,0,0,16,16H96a16,16,0,0,0,16-16V48A16,16,0,0,0,96,32Z"/>'),
    'play': ('<path d="M232.4,114.49,88.32,26.35a16,16,0,0,0-16.2-.3A15.86,15.86,0,0,0,64,39.87V216.13A15.94,15.94,0,0,0,80,232a16.07,16.07,0,0,0,8.36-2.35L232.4,141.51a15.81,15.81,0,0,0,0-27ZM80,215.94V40l143.83,88Z"/>',
        '<path d="M240,128a15.74,15.74,0,0,1-7.6,13.51L88.32,229.65a16,16,0,0,1-16.2.3A15.86,15.86,0,0,1,64,216.13V39.87a15.86,15.86,0,0,1,8.12-13.82,16,16,0,0,1,16.2.3L232.4,114.49A15.74,15.74,0,0,1,240,128Z"/>'),
    'playlist': ('<path d="M32,64a8,8,0,0,1,8-8H216a8,8,0,0,1,0,16H40A8,8,0,0,1,32,64Zm8,72H160a8,8,0,0,0,0-16H40a8,8,0,0,0,0,16Zm72,48H40a8,8,0,0,0,0,16h72a8,8,0,0,0,0-16Zm135.66-57.7a8,8,0,0,1-10,5.36L208,122.75V192a32.05,32.05,0,1,1-16-27.69V112a8,8,0,0,1,10.3-7.66l40,12A8,8,0,0,1,247.66,126.3ZM192,192a16,16,0,1,0-16,16A16,16,0,0,0,192,192Z"/>',
        '<path d="M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32ZM64,72H192a8,8,0,0,1,0,16H64a8,8,0,0,1,0-16Zm0,48h72a8,8,0,0,1,0,16H64a8,8,0,0,1,0-16Zm40,64H64a8,8,0,0,1,0-16h40a8,8,0,0,1,0,16Zm103.59-53.47a8,8,0,0,1-10.12,5.06L184,131.1V176a24,24,0,1,1-16-22.62V120a8,8,0,0,1,10.53-7.59l24,8A8,8,0,0,1,207.59,130.53Z"/>'),
    'plus': ('<path d="M224,128a8,8,0,0,1-8,8H136v80a8,8,0,0,1-16,0V136H40a8,8,0,0,1,0-16h80V40a8,8,0,0,1,16,0v80h80A8,8,0,0,1,224,128Z"/>',
        '<path d="M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32ZM184,136H136v48a8,8,0,0,1-16,0V136H72a8,8,0,0,1,0-16h48V72a8,8,0,0,1,16,0v48h48a8,8,0,0,1,0,16Z"/>'),
    'queue': ('<path d="M32,64a8,8,0,0,1,8-8H216a8,8,0,0,1,0,16H40A8,8,0,0,1,32,64Zm104,56H40a8,8,0,0,0,0,16h96a8,8,0,0,0,0-16Zm0,64H40a8,8,0,0,0,0,16h96a8,8,0,0,0,0-16Zm112-24a8,8,0,0,1-3.76,6.78l-64,40A8,8,0,0,1,168,200V120a8,8,0,0,1,12.24-6.78l64,40A8,8,0,0,1,248,160Zm-23.09,0L184,134.43v51.14Z"/>',
        '<path d="M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32ZM64,72H192a8,8,0,0,1,0,16H64a8,8,0,0,1,0-16Zm40,112H64a8,8,0,0,1,0-16h40a8,8,0,0,1,0,16Zm0-48H64a8,8,0,0,1,0-16h40a8,8,0,0,1,0,16Zm92.44,22.66-48,32A8,8,0,0,1,144,192a8,8,0,0,1-8-8V120a8,8,0,0,1,12.44-6.66l48,32a8,8,0,0,1,0,13.32Z"/>'),
    'repeat': ('<path d="M24,128A72.08,72.08,0,0,1,96,56H204.69L194.34,45.66a8,8,0,0,1,11.32-11.32l24,24a8,8,0,0,1,0,11.32l-24,24a8,8,0,0,1-11.32-11.32L204.69,72H96a56.06,56.06,0,0,0-56,56,8,8,0,0,1-16,0Zm200-8a8,8,0,0,0-8,8,56.06,56.06,0,0,1-56,56H51.31l10.35-10.34a8,8,0,0,0-11.32-11.32l-24,24a8,8,0,0,0,0,11.32l24,24a8,8,0,0,0,11.32-11.32L51.31,200H160a72.08,72.08,0,0,0,72-72A8,8,0,0,0,224,120Z"/>',
        '<path d="M24,128A72.08,72.08,0,0,1,96,56h96V40a8,8,0,0,1,13.66-5.66l24,24a8,8,0,0,1,0,11.32l-24,24A8,8,0,0,1,192,88V72H96a56.06,56.06,0,0,0-56,56,8,8,0,0,1-16,0Zm200-8a8,8,0,0,0-8,8,56.06,56.06,0,0,1-56,56H64V168a8,8,0,0,0-13.66-5.66l-24,24a8,8,0,0,0,0,11.32l24,24A8,8,0,0,0,64,216V200h96a72.08,72.08,0,0,0,72-72A8,8,0,0,0,224,120Z"/>'),
    'repeat-once': ('<path d="M24,128A72.08,72.08,0,0,1,96,56H204.69L194.34,45.66a8,8,0,0,1,11.32-11.32l24,24a8,8,0,0,1,0,11.32l-24,24a8,8,0,0,1-11.32-11.32L204.69,72H96a56.06,56.06,0,0,0-56,56,8,8,0,0,1-16,0Zm200-8a8,8,0,0,0-8,8,56.06,56.06,0,0,1-56,56H51.31l10.35-10.34a8,8,0,0,0-11.32-11.32l-24,24a8,8,0,0,0,0,11.32l24,24a8,8,0,0,0,11.32-11.32L51.31,200H160a72.08,72.08,0,0,0,72-72A8,8,0,0,0,224,120Zm-88,40a8,8,0,0,0,8-8V104a8,8,0,0,0-11.58-7.16l-16,8a8,8,0,1,0,7.16,14.31l4.42-2.21V152A8,8,0,0,0,136,160Z"/>',
        '<path d="M24,128A72.08,72.08,0,0,1,96,56h96V40a8,8,0,0,1,13.66-5.66l24,24a8,8,0,0,1,0,11.32l-24,24A8,8,0,0,1,192,88V72H96a56.06,56.06,0,0,0-56,56,8,8,0,0,1-16,0Zm200-8a8,8,0,0,0-8,8,56.06,56.06,0,0,1-56,56H64V168a8,8,0,0,0-13.66-5.66l-24,24a8,8,0,0,0,0,11.32l24,24A8,8,0,0,0,64,216V200h96a72.08,72.08,0,0,0,72-72A8,8,0,0,0,224,120Zm-88,40a8,8,0,0,0,8-8V104a8,8,0,0,0-11.58-7.16l-16,8a8,8,0,1,0,7.16,14.31l4.42-2.21V152A8,8,0,0,0,136,160Z"/>'),
    'shuffle': ('<path d="M237.66,178.34a8,8,0,0,1,0,11.32l-24,24a8,8,0,0,1-11.32-11.32L212.69,192H200.94a72.12,72.12,0,0,1-58.59-30.15l-41.72-58.4A56.1,56.1,0,0,0,55.06,80H32a8,8,0,0,1,0-16H55.06a72.12,72.12,0,0,1,58.59,30.15l41.72,58.4A56.1,56.1,0,0,0,200.94,176h11.75l-10.35-10.34a8,8,0,0,1,11.32-11.32ZM143,107a8,8,0,0,0,11.16-1.86l1.2-1.67A56.1,56.1,0,0,1,200.94,80h11.75L202.34,90.34a8,8,0,0,0,11.32,11.32l24-24a8,8,0,0,0,0-11.32l-24-24a8,8,0,0,0-11.32,11.32L212.69,64H200.94a72.12,72.12,0,0,0-58.59,30.15l-1.2,1.67A8,8,0,0,0,143,107Zm-30,42a8,8,0,0,0-11.16,1.86l-1.2,1.67A56.1,56.1,0,0,1,55.06,176H32a8,8,0,0,0,0,16H55.06a72.12,72.12,0,0,0,58.59-30.15l1.2-1.67A8,8,0,0,0,113,149Z"/>',
        '<path d="M237.66,178.34a8,8,0,0,1,0,11.32l-24,24A8,8,0,0,1,200,208V192a72.15,72.15,0,0,1-57.65-30.14l-41.72-58.4A56.1,56.1,0,0,0,55.06,80H32a8,8,0,0,1,0-16H55.06a72.12,72.12,0,0,1,58.59,30.15l41.72,58.4A56.08,56.08,0,0,0,200,176V160a8,8,0,0,1,13.66-5.66ZM143,107a8,8,0,0,0,11.16-1.86l1.2-1.67A56.08,56.08,0,0,1,200,80V96a8,8,0,0,0,13.66,5.66l24-24a8,8,0,0,0,0-11.32l-24-24A8,8,0,0,0,200,48V64a72.15,72.15,0,0,0-57.65,30.14l-1.2,1.67A8,8,0,0,0,143,107Zm-30,42a8,8,0,0,0-11.16,1.86l-1.2,1.67A56.1,56.1,0,0,1,55.06,176H32a8,8,0,0,0,0,16H55.06a72.12,72.12,0,0,0,58.59-30.15l1.2-1.67A8,8,0,0,0,113,149Z"/>'),
    'skip-back': ('<path d="M199.81,34a16,16,0,0,0-16.24.43L64,109.23V40a8,8,0,0,0-16,0V216a8,8,0,0,0,16,0V146.77l119.57,74.78A15.95,15.95,0,0,0,208,208.12V47.88A15.86,15.86,0,0,0,199.81,34ZM192,208,64.16,128,192,48.07Z"/>',
        '<path d="M208,47.88V208.12a16,16,0,0,1-24.43,13.43L64,146.77V216a8,8,0,0,1-16,0V40a8,8,0,0,1,16,0v69.23L183.57,34.45A15.95,15.95,0,0,1,208,47.88Z"/>'),
    'skip-forward': ('<path d="M200,32a8,8,0,0,0-8,8v69.23L72.43,34.45A15.95,15.95,0,0,0,48,47.88V208.12a16,16,0,0,0,24.43,13.43L192,146.77V216a8,8,0,0,0,16,0V40A8,8,0,0,0,200,32ZM64,207.93V48.05l127.84,80Z"/>',
        '<path d="M208,40V216a8,8,0,0,1-16,0V146.77L72.43,221.55A15.95,15.95,0,0,1,48,208.12V47.88A15.95,15.95,0,0,1,72.43,34.45L192,109.23V40a8,8,0,0,1,16,0Z"/>'),
    'speaker-high': ('<path d="M155.51,24.81a8,8,0,0,0-8.42.88L77.25,80H32A16,16,0,0,0,16,96v64a16,16,0,0,0,16,16H77.25l69.84,54.31A8,8,0,0,0,160,224V32A8,8,0,0,0,155.51,24.81ZM32,96H72v64H32ZM144,207.64,88,164.09V91.91l56-43.55Zm54-106.08a40,40,0,0,1,0,52.88,8,8,0,0,1-12-10.58,24,24,0,0,0,0-31.72,8,8,0,0,1,12-10.58ZM248,128a79.9,79.9,0,0,1-20.37,53.34,8,8,0,0,1-11.92-10.67,64,64,0,0,0,0-85.33,8,8,0,1,1,11.92-10.67A79.83,79.83,0,0,1,248,128Z"/>',
        '<path d="M160,32.25V223.69a8.29,8.29,0,0,1-3.91,7.18,8,8,0,0,1-9-.56l-65.57-51A4,4,0,0,1,80,176.16V79.84a4,4,0,0,1,1.55-3.15l65.57-51a8,8,0,0,1,10,.16A8.27,8.27,0,0,1,160,32.25ZM60,80H32A16,16,0,0,0,16,96v64a16,16,0,0,0,16,16H60a4,4,0,0,0,4-4V84A4,4,0,0,0,60,80Zm126.77,20.84a8,8,0,0,0-.72,11.3,24,24,0,0,1,0,31.72,8,8,0,1,0,12,10.58,40,40,0,0,0,0-52.88A8,8,0,0,0,186.74,100.84Zm40.89-26.17a8,8,0,1,0-11.92,10.66,64,64,0,0,1,0,85.34,8,8,0,1,0,11.92,10.66,80,80,0,0,0,0-106.66Z"/>'),
    'speaker-x': ('<path d="M155.51,24.81a8,8,0,0,0-8.42.88L77.25,80H32A16,16,0,0,0,16,96v64a16,16,0,0,0,16,16H77.25l69.84,54.31A8,8,0,0,0,160,224V32A8,8,0,0,0,155.51,24.81ZM32,96H72v64H32ZM144,207.64,88,164.09V91.91l56-43.55Zm101.66-61.3a8,8,0,0,1-11.32,11.32L216,139.31l-18.34,18.35a8,8,0,0,1-11.32-11.32L204.69,128l-18.35-18.34a8,8,0,0,1,11.32-11.32L216,116.69l18.34-18.35a8,8,0,0,1,11.32,11.32L227.31,128Z"/>',
        '<path d="M245.66,146.34a8,8,0,0,1-11.32,11.32L216,139.31l-18.34,18.35a8,8,0,0,1-11.32-11.32L204.69,128l-18.35-18.34a8,8,0,0,1,11.32-11.32L216,116.69l18.34-18.35a8,8,0,0,1,11.32,11.32L227.31,128ZM60,80H32A16,16,0,0,0,16,96v64a16,16,0,0,0,16,16H60a4,4,0,0,0,4-4V84A4,4,0,0,0,60,80Zm97.15-54.15a8,8,0,0,0-10-.16l-65.57,51A4,4,0,0,0,80,79.84v96.32a4,4,0,0,0,1.55,3.15l65.57,51a8,8,0,0,0,9,.56,8.29,8.29,0,0,0,3.91-7.18V32.25A8.27,8.27,0,0,0,157.12,25.85Z"/>'),
    'star': ('<path d="M239.18,97.26A16.38,16.38,0,0,0,224.92,86l-59-4.76L143.14,26.15a16.36,16.36,0,0,0-30.27,0L90.11,81.23,31.08,86a16.46,16.46,0,0,0-9.37,28.86l45,38.83L53,211.75a16.38,16.38,0,0,0,24.5,17.82L128,198.49l50.53,31.08A16.4,16.4,0,0,0,203,211.75l-13.76-58.07,45-38.83A16.43,16.43,0,0,0,239.18,97.26Zm-15.34,5.47-48.7,42a8,8,0,0,0-2.56,7.91l14.88,62.8a.37.37,0,0,1-.17.48c-.18.14-.23.11-.38,0l-54.72-33.65a8,8,0,0,0-8.38,0L69.09,215.94c-.15.09-.19.12-.38,0a.37.37,0,0,1-.17-.48l14.88-62.8a8,8,0,0,0-2.56-7.91l-48.7-42c-.12-.1-.23-.19-.13-.5s.18-.27.33-.29l63.92-5.16A8,8,0,0,0,103,91.86l24.62-59.61c.08-.17.11-.25.35-.25s.27.08.35.25L153,91.86a8,8,0,0,0,6.75,4.92l63.92,5.16c.15,0,.24,0,.33.29S224,102.63,223.84,102.73Z"/>',
        '<path d="M234.29,114.85l-45,38.83L203,211.75a16.4,16.4,0,0,1-24.5,17.82L128,198.49,77.47,229.57A16.4,16.4,0,0,1,53,211.75l13.76-58.07-45-38.83A16.46,16.46,0,0,1,31.08,86l59-4.76,22.76-55.08a16.36,16.36,0,0,1,30.27,0l22.75,55.08,59,4.76a16.46,16.46,0,0,1,9.37,28.86Z"/>'),
    'stop': ('<path d="M200,40H56A16,16,0,0,0,40,56V200a16,16,0,0,0,16,16H200a16,16,0,0,0,16-16V56A16,16,0,0,0,200,40Zm0,160H56V56H200V200Z"/>',
        '<path d="M216,56V200a16,16,0,0,1-16,16H56a16,16,0,0,1-16-16V56A16,16,0,0,1,56,40H200A16,16,0,0,1,216,56Z"/>'),
    'trash': ('<path d="M216,48H176V40a24,24,0,0,0-24-24H104A24,24,0,0,0,80,40v8H40a8,8,0,0,0,0,16h8V208a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V64h8a8,8,0,0,0,0-16ZM96,40a8,8,0,0,1,8-8h48a8,8,0,0,1,8,8v8H96Zm96,168H64V64H192ZM112,104v64a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Zm48,0v64a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Z"/>',
        '<path d="M216,48H176V40a24,24,0,0,0-24-24H104A24,24,0,0,0,80,40v8H40a8,8,0,0,0,0,16h8V208a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V64h8a8,8,0,0,0,0-16ZM112,168a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Zm48,0a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Zm0-120H96V40a8,8,0,0,1,8-8h48a8,8,0,0,1,8,8Z"/>'),
    'vinyl-record': ('<path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216Zm0-144a56.06,56.06,0,0,0-56,56,8,8,0,0,1-16,0,72.08,72.08,0,0,1,72-72,8,8,0,0,1,0,16Zm72,56a72.08,72.08,0,0,1-72,72,8,8,0,0,1,0-16,56.06,56.06,0,0,0,56-56,8,8,0,0,1,16,0Zm-40,0a32,32,0,1,0-32,32A32,32,0,0,0,160,128Zm-48,0a16,16,0,1,1,16,16A16,16,0,0,1,112,128Z"/>',
        '<path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24ZM72,128a8,8,0,0,1-16,0,72.08,72.08,0,0,1,72-72,8,8,0,0,1,0,16A56.06,56.06,0,0,0,72,128Zm32,0a24,24,0,1,1,24,24A24,24,0,0,1,104,128Zm24,72a8,8,0,0,1,0-16,56.06,56.06,0,0,0,56-56,8,8,0,0,1,16,0A72.08,72.08,0,0,1,128,200Z"/>'),
    'x': ('<path d="M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z"/>',
        '<path d="M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32ZM181.66,170.34a8,8,0,0,1-11.32,11.32L128,139.31,85.66,181.66a8,8,0,0,1-11.32-11.32L116.69,128,74.34,85.66A8,8,0,0,1,85.66,74.34L128,116.69l42.34-42.35a8,8,0,0,1,11.32,11.32L139.31,128Z"/>'),
}


_ICONS = {}


def ph(name, fill=False, color=None, sizes=(16, 20, 24, 32, 40, 48)):
    """Ícone Phosphor desenhado na cor do tema (claro ou escuro)."""
    if QSvgRenderer is None or name not in PHOSPHOR:
        return QIcon()
    pal = QApplication.palette()
    col = QColor(color) if color is not None else pal.color(pal.ColorRole.WindowText)
    key = (name, fill, col.name(QColor.NameFormat.HexArgb), sizes)
    if key not in _ICONS:
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" fill="%s">%s</svg>'
               % (col.name(), PHOSPHOR[name][1 if fill else 0]))
        ren = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        app = QApplication.instance()
        dpr = max(1.0, app.devicePixelRatio()) if app else 1.0
        icon = QIcon()
        for size in sizes:
            px = max(1, round(size * dpr))
            pm = QPixmap(px, px)
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            ren.render(painter)
            painter.end()
            pm.setDevicePixelRatio(dpr)
            icon.addPixmap(pm)
        _ICONS[key] = icon
    return _ICONS[key]


# ================================================================ temas de cores
# Três temas, um layout: LMP 1 (claro), LMP 2 (escuro) e "Do sistema". Cada tema é só um
# dicionário com os doze papéis abaixo, e a folha de estilo (QSS) é gerada a partir dele.
#   bg: fundo da janela · surface: cartões e botões · surface2: cabeçalho, "tocando agora", mouse em cima
#   border: bordas e trilhos · text / text2: texto principal e secundário
#   accent: item selecionado, play, progresso · accentText: destaque usado em texto
#   tint: fundo da música tocando e de aleatório/repetir ligados · onAccent: texto sobre o destaque
#   star / starOff: estrelas cheias e vazias
THEMES = {
    "mp12-claro": {
        "nome": "LMP 1",
        "bg": "#EEF3F6", "surface": "#FFFFFF", "surface2": "#F4F8FA", "border": "#E1E7EC",
        "text": "#171C20", "text2": "#5E7080", "accent": "#176A9A", "accentText": "#176A9A",
        "tint": "#E3F1FA", "onAccent": "#FFFFFF", "star": "#39BCE0", "starOff": "#C9D2D9",
    },
    "mp12-escuro": {
        "nome": "LMP 2",
        "bg": "#0F1316", "surface": "#171C20", "surface2": "#1E252B", "border": "#262F36",
        "text": "#F4F8FA", "text2": "#9BAAB6", "accent": "#39BCE0", "accentText": "#39BCE0",
        "tint": "#16313F", "onAccent": "#0B1A22", "star": "#39BCE0", "starOff": "#3A454E",
    },
}
THEME_ORDER = [("mp12-claro", "LMP 1"), ("mp12-escuro", "LMP 2"), ("sistema", "Do sistema")]
THEME = dict(THEMES["mp12-claro"])     # o dicionário do tema atual
_SYSTEM = {}                           # paleta e fonte originais do sistema
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fontes")
_FONTS = {}


def C(key):
    """Cor do tema atual."""
    return QColor(THEME[key])


def misturar(a, b, forca):
    """Cor a misturada sobre b (forca 0..1)."""
    a, b = QColor(a), QColor(b)
    m = lambda x, y: round(y + (x - y) * forca)
    return QColor(m(a.red(), b.red()), m(a.green(), b.green()), m(a.blue(), b.blue())).name()


def _lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    c = QColor(c)
    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def contraste(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def legivel(cor, fundo, alvo=4.5):
    """Escurece (fundo claro) ou clareia (fundo escuro) a cor em passos de 6%
    até o contraste chegar a 4,5:1 (regra WCAG AA)."""
    alvo_cor = "#000000" if _lum(fundo) > 0.18 else "#FFFFFF"
    c = QColor(cor).name()
    for _ in range(17):
        if contraste(c, fundo) >= alvo:
            break
        c = misturar(alvo_cor, c, 0.06)
    return c


def cores_do_sistema(pal):
    """O tema "Do sistema": só as cores vêm do KDE/GNOME; cantos, espaços e fonte ficam iguais."""
    cor = lambda papel: pal.color(QPalette.ColorGroup.Active, papel).name()
    R = QPalette.ColorRole
    base, texto, destaque = cor(R.Base), cor(R.Text), cor(R.Highlight)
    tint = misturar(destaque, base, 0.16)
    return {
        "nome": "Do sistema",
        "bg": cor(R.Window),
        "surface": base,
        "surface2": cor(R.AlternateBase),
        "border": misturar(texto, base, 0.14),
        "text": texto,
        "text2": legivel(misturar(texto, base, 0.62), base),
        "accent": destaque,
        "accentText": legivel(destaque, tint),
        "tint": tint,
        "onAccent": cor(R.HighlightedText),
        "star": destaque,
        "starOff": misturar(texto, base, 0.22),
    }


def load_fonts():
    """A Inter vai junto com o programa: a interface fica igual em qualquer distribuição."""
    for peso in ("Regular", "Medium", "SemiBold", "Bold"):
        f = os.path.join(FONT_DIR, f"Inter-{peso}.ttf")
        if os.path.exists(f):
            QFontDatabase.addApplicationFont(f)


def base_font():
    """Inter 10 pt (13 px a 96 dpi) em todos os temas, inclusive no "Do sistema"."""
    if "Inter" in QFontDatabase.families():
        f = QFont("Inter", 10)
    else:                                            # sem a pasta fontes/: a do sistema
        f = QFont(_SYSTEM.get("font") or QApplication.font())
        f.setPointSize(10)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def F(kind="base"):
    """Escala de tamanhos da proposta (pt, peso)."""
    if kind not in _FONTS:
        W = QFont.Weight
        size, weight = {
            "base": (10, W.Normal), "semi": (10, W.DemiBold), "bold": (10, W.Bold),
            "artist": (10.5, W.Bold), "crumb": (10.5, W.Normal), "crumb_cur": (10.5, W.DemiBold),
            "button": (9, W.Medium), "np": (11, W.DemiBold), "label": (9, W.DemiBold),
            "small": (9, W.Normal), "small_semi": (9, W.DemiBold), "time": (9, W.Normal),
        }[kind]
        f = QFont(base_font())
        f.setPointSizeF(size)
        f.setWeight(weight)
        if kind == "label":
            f.setCapitalization(QFont.Capitalization.AllUppercase)
            f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 105)
        if kind in ("time", "small", "small_semi", "base", "semi"):
            try:                                     # números de largura fixa (Qt 6.7+)
                f.setFeature(QFont.Tag("tnum"), 1)
            except (AttributeError, TypeError):
                pass
        _FONTS[kind] = f
    return _FONTS[kind]


def _theme_palette(t):
    p = QPalette()
    R = QPalette.ColorRole
    for role, key in ((R.Window, "bg"), (R.WindowText, "text"), (R.Base, "surface"),
                      (R.AlternateBase, "surface2"), (R.Text, "text"), (R.Button, "surface"),
                      (R.ButtonText, "text"), (R.Highlight, "accent"), (R.HighlightedText, "onAccent"),
                      (R.Link, "accentText"), (R.LinkVisited, "accentText"), (R.PlaceholderText, "text2"),
                      (R.ToolTipBase, "surface"), (R.ToolTipText, "text"), (R.Mid, "starOff"),
                      (R.Midlight, "surface2"), (R.Light, "surface"), (R.Dark, "border"),
                      (R.BrightText, "accent")):
        p.setColor(role, QColor(t[key]))
    p.setColor(R.Shadow, QColor("#000000"))
    for role in (R.WindowText, R.Text, R.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["text2"]))
    return p


def _theme_qss(t):
    css = """
/* Janela e cartões */
QMainWindow, QWidget#central { background: %(bg)s; }
QFrame#navCard, QFrame#libraryCard, QFrame#queueCard, QFrame#playerBar {
    background: %(surface)s; border: 1px solid %(border)s; border-radius: 14px; }
QFrame#nowCard { background: %(surface2)s; border: 0; border-radius: 12px; }
QLabel { background: transparent; color: %(text)s; }
QLabel#sub { color: %(text2)s; }
QLabel#secao { color: %(text2)s; }
QLabel#time { color: %(text2)s; }
QFrame#sep { background: %(border)s; border: 0; }
QSplitter, QSplitter::handle { background: transparent; }

/* Barra de ferramentas (mesmos botões de hoje) */
QPushButton, QToolButton#toolButton {
    background: %(surface)s; color: %(text)s;
    border: 1px solid %(border)s; border-radius: 10px;
    padding: 0 12px; min-height: 32px; font-size: 9pt; font-weight: 500; }
QPushButton:hover, QToolButton#toolButton:hover { background: %(surface2)s; }
QPushButton:pressed, QToolButton#toolButton:pressed { background: %(tint)s; }
QPushButton:default { border-color: %(accent)s; }
QToolButton#toolButton { padding-right: 30px; }
QToolButton#toolButton::menu-indicator { image: url(%(seta_baixo)s); subcontrol-origin: padding;
    subcontrol-position: right center; right: 10px; width: 12px; height: 12px; }

/* Pesquisa */
QLineEdit#search {
    background: %(surface)s; color: %(text)s;
    border: 1px solid %(border)s; border-radius: 17px;
    padding: 0 12px; min-height: 32px; font-size: 9pt;
    selection-background-color: %(accent)s; selection-color: %(onAccent)s; }
QLineEdit#search:focus { border-color: %(accent)s; }
QLineEdit { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s;
    border-radius: 8px; padding: 4px 8px;
    selection-background-color: %(accent)s; selection-color: %(onAccent)s; }
QLineEdit:focus { border-color: %(accent)s; }

/* Árvore da biblioteca (o fundo do item é desenhado em NavTree.drawRow) */
QTreeView#nav { background: transparent; border: 0; outline: 0; color: %(text)s; }
QTreeView#nav::item, QTreeView#nav::item:selected, QTreeView#nav::item:hover {
    min-height: 30px; padding-left: 4px; background: transparent; color: %(text)s; }
QTreeView#nav::branch { background: transparent; }
QTreeView#nav::branch:has-children:closed { image: url(%(seta_fechada)s); }
QTreeView#nav::branch:has-children:open { image: url(%(seta_aberta)s); }
QTreeView#nav::branch:has-children:closed:selected { image: url(%(seta_fechada_sel)s); }
QTreeView#nav::branch:has-children:open:selected { image: url(%(seta_aberta_sel)s); }

/* Tabela agrupada por álbum */
QTableView#library { background: transparent; border: 0; outline: 0; color: %(text)s;
    selection-background-color: transparent; selection-color: %(text)s; }
QTableView#library::item, QTableView#library::item:selected, QTableView#library::item:hover,
QTableView#library::item:focus { background: transparent; border: 0; color: %(text)s; }
QTableView#library QHeaderView { background: transparent; border: 0; }
QTableView#library QHeaderView::section {
    background: %(surface2)s; color: %(text2)s;
    border: 0; border-bottom: 1px solid %(border)s;
    padding: 0 8px; min-height: 35px; font-size: 9pt; font-weight: 500; }
QTableView#library QHeaderView::section:first { padding-left: 16px; border-top-left-radius: 13px; }
QTableView#library QHeaderView::section:last { border-top-right-radius: 13px; }
QTableView#library QTableCornerButton::section { background: %(surface2)s; border: 0; }

/* Grade (artistas, álbuns, gêneros, listas, pastas) */
QListView#grid { background: transparent; border: 0; outline: 0; color: %(text)s; padding: 8px; }
QListView#grid::item { border-radius: 12px; padding: 6px; color: %(text)s; }
QListView#grid::item:hover { background: %(surface2)s; }
QListView#grid::item:selected { background: %(tint)s; color: %(text)s; }

/* Lista atual */
QTreeView#queue {
    background: %(surface)s; border: 1px solid %(border)s;
    border-radius: 12px; padding: 4px; outline: 0; color: %(text)s; }
QTreeView#queue::item, QTreeView#queue::item:selected, QTreeView#queue::item:hover {
    min-height: 26px; background: transparent; color: %(text)s; }
QTreeView#queue::branch, QTreeView#nav::branch:selected { background: transparent; }

/* Controles */
QToolButton#transport { background: transparent; border: 0; border-radius: 10px;
    min-width: 38px; min-height: 38px; max-width: 38px; max-height: 38px; }
QToolButton#transport:hover { background: %(surface2)s; }
QToolButton#transport:checked { background: %(tint)s; }
QToolButton#playButton {
    background: %(accent)s; border: 0; border-radius: 23px;
    min-width: 46px; max-width: 46px; min-height: 46px; max-height: 46px; }
QToolButton#playButton:hover { background: %(accent_hover)s; }
QToolButton#playButton:pressed { background: %(accent_press)s; }

/* Progresso e volume */
QSlider { background: transparent; min-height: 16px; }
QSlider::groove:horizontal { height: 4px; border-radius: 2px; background: %(border)s; }
QSlider::sub-page:horizontal { border-radius: 2px; background: %(accent)s; }
QSlider#volume::sub-page:horizontal { background: %(text2)s; }
QSlider::handle:horizontal { width: 12px; height: 12px; margin: -4px 0;
    border-radius: 6px; background: %(accent)s; }
QSlider#volume::handle:horizontal { background: %(text2)s; }

/* Rolagem fina */
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px 4px; }
QScrollBar::handle:vertical { background: %(border)s; border-radius: 3px; min-height: 40px; }
QScrollBar::handle:horizontal { background: %(border)s; border-radius: 3px; min-width: 40px; }
QScrollBar::handle:hover { background: %(starOff)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* Barra de status */
QStatusBar { background: transparent; color: %(text2)s; padding-left: 8px; font-size: 9pt; }
QStatusBar QLabel { color: %(text2)s; font-size: 9pt; }
QStatusBar::item { border: 0; }

/* Menus, dicas e janelas de diálogo */
QMenu { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s;
    border-radius: 10px; padding: 6px; }
QMenu::item { padding: 6px 22px 6px 12px; border-radius: 7px; }
QMenu::item:selected { background: %(surface2)s; color: %(text)s; }
QMenu::item:disabled { color: %(text2)s; }
QMenu::icon { padding-left: 8px; }
QMenu::separator { height: 1px; background: %(border)s; margin: 4px 8px; }
QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 4px; }
QDialog, QMessageBox, QInputDialog { background: %(bg)s; }
"""
    fechada, aberta, baixo = _arrows(t["text2"])
    fechada_sel, aberta_sel, _ = _arrows(t["onAccent"])
    ac = QColor(t["accent"])
    return css % dict(t, seta_fechada=fechada, seta_aberta=aberta, seta_baixo=baixo,
                      seta_fechada_sel=fechada_sel, seta_aberta_sel=aberta_sel,
                      accent_hover=ac.lighter(108).name(), accent_press=ac.darker(108).name())


def _arrows(color):
    """Setas finas (abrir/fechar da árvore e a do botão Tema), gravadas como PNG no cache."""
    paths = []
    for name, pts in (("fechada", [(6, 4), (10, 8), (6, 12)]), ("aberta", [(4, 6), (8, 10), (12, 6)]),
                      ("baixo", [(4, 6), (8, 10), (12, 6)])):
        path = os.path.join(CACHE_DIR, "seta2-%s-%s.png" % (name, color.lstrip("#").lower()))
        if not os.path.exists(path):
            os.makedirs(CACHE_DIR, exist_ok=True)
            pm = QPixmap(32, 32)                     # desenhada em 2x: fica nítida em telas HiDPI
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(color), 3.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline(QPolygonF([QPointF(x * 2, y * 2) for x, y in pts]))
            p.end()
            pm.save(path)
        paths.append(path.replace("\\", "/"))
    return paths


def apply_theme(key):
    """Troca o tema do programa inteiro. Devolve a chave aplicada."""
    app = QApplication.instance()
    if not _SYSTEM:
        _SYSTEM.update(palette=QPalette(app.palette()), font=QFont(app.font()))
    if key not in THEMES:
        key = "sistema"
    t = cores_do_sistema(_SYSTEM["palette"]) if key == "sistema" else THEMES[key]
    THEME.clear()
    THEME.update(t)
    _FONTS.clear()
    _ICONS.clear()
    app.setStyle("Fusion")                 # nos três temas: o Breeze desmancharia os cantos
    app.setPalette(_theme_palette(t))
    app.setFont(base_font())
    app.setStyleSheet(_theme_qss(t))
    return key


def theme_swatch(key, size=16):
    """Bolinha com as cores do tema, para o menu de temas."""
    t = THEMES.get(key) or cores_do_sistema(_SYSTEM.get("palette") or QApplication.palette())
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = pm.rect().adjusted(2, 2, -2, -2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(t["bg"]))
    p.drawEllipse(rect)
    p.setBrush(QColor(t["accent"]))
    p.drawPie(rect, -45 * 16, 180 * 16)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QColor(t["border"]))
    p.drawEllipse(rect)
    p.end()
    return QIcon(pm)


def rounded_pix(src, size, radius, dpr=1.0):
    """Capa recortada em quadrado com cantos arredondados (feita uma vez e guardada no cache)."""
    px = max(1, round(size * dpr))
    out = QPixmap(px, px)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, px, px), radius * dpr, radius * dpr)
    p.setClipPath(path)
    s = src.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                   Qt.TransformationMode.SmoothTransformation)
    p.drawPixmap(QPointF((px - s.width()) / 2, (px - s.height()) / 2), s)
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


def star_poly(cx, cy, r):
    pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36)
        rr = r if i % 2 == 0 else r * 0.45
        pts.append(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return QPolygonF(pts)


STAR_STEP, STAR_X = 13, 10          # distância entre estrelas e margem da coluna Avaliação


def paint_stars(p, rect, n, on=None, off=None):
    """Cinco estrelas: cheias em star, vazias em starOff."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    cy = rect.center().y() + 0.5
    for i in range(5):
        p.setBrush(on or C("star") if i < n else off or C("starOff"))
        p.drawPolygon(star_poly(rect.left() + STAR_X + 5.5 + i * STAR_STEP, cy, 5.6))
    p.restore()


def elide(text, font, width):
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, max(0, int(width)))


# ================================================================ tags (só leitura)
def read_tags(path, want_cover=False):
    """Devolve (campos, duração em segundos, bytes da capa ou None)."""
    if mutagen is None:
        return {}, 0, None
    f = mutagen.File(path)
    if f is None:
        return {}, 0, None
    dur = getattr(f.info, "length", 0) or 0
    t, c, cover = f.tags, {}, None
    if isinstance(t, ID3):                                   # MP3, WAV, AIFF
        for k, fr in (("title", "TIT2"), ("artist", "TPE1"), ("albumartist", "TPE2"),
                      ("album", "TALB"), ("genre", "TCON"), ("date", "TDRC"),
                      ("track", "TRCK"), ("disc", "TPOS")):
            if t.get(fr) is not None and t[fr].text:
                c[k] = _first(t[fr].genres if fr == "TCON" else t[fr].text)
        popm = t.getall("POPM")
        if popm:
            c["rating"] = _stars_from_popm(popm[0].rating)
        if want_cover:
            pics = sorted(t.getall("APIC"), key=lambda p: p.type != 3)   # capa frontal primeiro
            cover = pics[0].data if pics else None
    elif isinstance(f, MP4):                                 # M4A
        t = t or {}
        for k, key in (("title", "\xa9nam"), ("artist", "\xa9ART"), ("albumartist", "aART"),
                       ("album", "\xa9alb"), ("genre", "\xa9gen"), ("date", "\xa9day")):
            if t.get(key):
                c[k] = _first(t[key])
        for k, key in (("track", "trkn"), ("disc", "disk")):
            if t.get(key):
                c[k] = str(t[key][0][0])
        if want_cover and t.get("covr"):
            cover = bytes(t["covr"][0])
    elif t is not None and hasattr(t, "get"):                # FLAC, Ogg, Opus (Vorbis)
        for k, key in (("title", "title"), ("artist", "artist"), ("albumartist", "albumartist"),
                       ("album", "album"), ("genre", "genre"), ("date", "date"),
                       ("track", "tracknumber"), ("disc", "discnumber")):
            try:
                if t.get(key):
                    c[k] = _first(t[key])
            except Exception:
                pass
        if want_cover:
            pics = list(f.pictures) if isinstance(f, FLAC) else []
            try:
                for b64 in t.get("metadata_block_picture") or []:
                    pics.append(Picture(base64.b64decode(b64)))
            except Exception:
                pass
            pics.sort(key=lambda p: p.type != 3)
            cover = pics[0].data if pics else None
    return c, dur, cover


def save_cover(data=None, path=None):
    """Grava a miniatura de uma capa no cache e devolve o nome do arquivo ('' se não deu).
    O nome vem do conteúdo da imagem: capas iguais (mesmo álbum) viram um arquivo só."""
    try:
        seed = data if data else f"{path}|{os.path.getmtime(path)}".encode("utf-8")
    except OSError:
        return ""
    name = hashlib.sha1(seed).hexdigest()[:24] + ".png"
    full = os.path.join(COVER_DIR, name)
    if os.path.exists(full):
        return name
    img = QImage()
    if not (img.loadFromData(data) if data else img.load(path)):
        return ""
    os.makedirs(COVER_DIR, exist_ok=True)
    img.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio,
               Qt.TransformationMode.SmoothTransformation).save(full)
    return name


def read_entry(path, want_cover=False):
    """Tags de um arquivo. Com want_cover, também a capa DELE (a que está dentro do
    arquivo; se não tiver, a imagem da pasta, como cover.jpg)."""
    folder = os.path.dirname(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    e = {"path": path, "title": stem, "artist": "", "albumartist": "", "album": "",
         "genre": "", "year": "", "track": 0, "disc": 0, "dur": 0, "rating_file": 0}
    data = None
    try:
        c, dur, data = read_tags(path, want_cover=want_cover)
        m = re.match(r"\d{4}", c.get("date", ""))
        e.update(title=c.get("title") or stem, artist=c.get("artist", ""),
                 albumartist=c.get("albumartist", ""), album=c.get("album", ""),
                 genre=c.get("genre", ""), year=m.group(0) if m else "",
                 track=_int(c.get("track")), disc=_int(c.get("disc")), dur=dur,
                 rating_file=c.get("rating", 0))
    except Exception:
        pass
    aa = e["albumartist"] or e["artist"]
    e["album_id"] = f"{aa.lower()}|{e['album'].lower()}" if e["album"] else "pasta:" + folder
    if want_cover:
        e["cover"] = save_cover(data=data) if data else ""
        if not e["cover"]:
            fi = folder_image(folder)
            e["cover"] = save_cover(path=fi) if fi else ""
    return e


def group_artist(e):
    return e["albumartist"] or e["artist"] or "Artista desconhecido"


def album_name(e):
    return e["album"] or os.path.basename(os.path.dirname(e["path"])) or "Álbum desconhecido"


def album_order(e):
    return (not (e["albumartist"] or e["artist"]), group_artist(e).lower(), album_name(e).lower(), e["album_id"], e["disc"] or 1,
            e["track"] or 9999, e["title"].lower())


def collect(paths):
    files = []
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                files += [os.path.join(root, n) for n in sorted(names)]
        elif os.path.isfile(p):
            files.append(p)
    return [f for f in files if os.path.splitext(f)[1].lower() in EXTS]


def folder_image(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    imgs = [n for n in names if n.lower().endswith((".jpg", ".jpeg", ".png"))]
    for want in ("cover", "folder", "front", "capa", "albumart"):
        for n in imgs:
            if os.path.splitext(n)[0].lower().startswith(want):
                return os.path.join(folder, n)
    return os.path.join(folder, imgs[0]) if len(imgs) == 1 else None


# ================================================================ listas (.m3u8)
def read_m3u(path):
    out, base = [], os.path.dirname(path)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(os.path.normpath(os.path.join(base, line)))
    except OSError:
        pass
    return out


def write_m3u(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#EXTM3U\n")
        for e in entries:
            who = f"{e['artist']} - " if e["artist"] else ""
            fh.write(f"#EXTINF:{int(e['dur'] or -1)},{who}{e['title']}\n{e['path']}\n")


# ================================================================ leitura em segundo plano
class Scanner(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(dict, dict)

    def __init__(self, folders, old_tracks, excluded=()):
        super().__init__()
        self.folders, self.old, self.excluded = folders, old_tracks, list(excluded)

    def run(self):
        files = [f for f in collect(self.folders)
                 if not any(f.startswith(x + os.sep) for x in self.excluded)]
        tracks, n = {}, len(files)
        for i, p in enumerate(files, 1):
            if i % 10 == 0 or i == n:
                self.progress.emit(i, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            old = self.old.get(p)
            if (old and old.get("mtime") == st.st_mtime and old.get("size") == st.st_size
                    and (not old.get("cover") or os.path.exists(os.path.join(COVER_DIR, old["cover"])))):
                tracks[p] = old
                continue
            e = read_entry(p, want_cover=True)
            e["mtime"], e["size"] = st.st_mtime, st.st_size
            tracks[p] = e
        covers = {}                     # capa do álbum (para a grade): a da 1ª faixa que tiver
        for e in sorted(tracks.values(), key=album_order):
            if e.get("cover") and not covers.get(e["album_id"]):
                covers[e["album_id"]] = e["cover"]
        _write_json(CACHE_FILE, {"versao": 3, "faixas": tracks, "capas": covers})
        self.done.emit(tracks, covers)


# ================================================================ peças da janela
class ClickSlider(QSlider):
    """Barra que pula direto para onde você clica."""
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.maximum() > 0:
            self.setValue(QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(ev.position().x()), self.width()))
            self.sliderMoved.emit(self.value())
        super().mousePressEvent(ev)


class TrackDelegate(QStyledItemDelegate):
    """Desenha a tabela agrupada: nome do artista, bloco do álbum (capa + dados) e as faixas
    com fundo arredondado (mouse em cima: surface2; tocando: tint, texto em accentText)."""

    def paint(self, p, opt, idx):
        t = self.parent()
        r, c = idx.row(), idx.column()
        kind = t.row_kind.get(r)
        rect = QRectF(opt.rect)
        if kind == "header":
            f = F("artist")
            p.save()
            p.setFont(f)
            p.setPen(C("accentText"))
            txt = QRectF(rect.left() + 16, rect.top() + 6, rect.width() - 32, rect.height() - 6)
            p.drawText(txt, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       elide(idx.data() or "", f, txt.width()))
            p.restore()
            return
        if c == COL_ALBUM:
            e = t.album_at.get(r)
            if e is not None:
                self.paint_album(p, rect, e)
            return
        if kind != "track":
            return
        path = t.row_path[r]
        playing = path == t.playing
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        back = (C("tint") if playing else
                QColor(misturar(THEME["tint"], THEME["surface"], 0.55)) if sel else
                C("surface2") if r == t.hover_row else None)
        if back is not None:
            left = t.columnViewportPosition(COL_NUM)
            right = t.columnViewportPosition(COL_ARTIST) + t.columnWidth(COL_ARTIST) - 10
            p.save()
            p.setClipRect(opt.rect)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(back)
            p.drawRoundedRect(QRectF(left, rect.top() + 0.5, right - left, rect.height() - 1), 8, 8)
            p.restore()
        if c == COL_RATE:
            paint_stars(p, rect, int(idx.data(ROLE) or 0))
            return
        f = F("semi") if playing else F("base")
        p.save()
        p.setFont(f)
        p.setPen(C("accentText") if playing else C("text2") if c in (COL_NUM, COL_DUR) else C("text"))
        if c in (COL_NUM, COL_DUR):
            box = rect.adjusted(4, 0, -8, 0)
            al = Qt.AlignmentFlag.AlignRight
        else:
            box = rect.adjusted(10, 0, -8, 0)
            al = Qt.AlignmentFlag.AlignLeft
        p.drawText(box, al | Qt.AlignmentFlag.AlignVCenter, elide(idx.data() or "", f, box.width()))
        p.restore()

    def paint_album(self, p, rect, e):
        """Capa de 92 px (cantos de 12) e, ao lado, álbum, artista, gênero e ano."""
        t = self.parent()
        p.save()
        p.setClipRect(rect)
        x, y = rect.left() + 16, rect.top()
        pm = t.cover_fn(e) if t.cover_fn else None
        if pm is not None:
            p.drawPixmap(QPointF(x, y), pm)
        tx = x + COVER + 12
        w = rect.right() - tx - 8
        p.setFont(F("semi"))
        p.setPen(C("text"))
        fm = QFontMetrics(F("semi"))
        name = QRectF(tx, y - 1, w, fm.lineSpacing() * 2 + 1)
        br = p.boundingRect(name, int(Qt.TextFlag.TextWordWrap), album_name(e))
        if br.height() > name.height():                  # mais de duas linhas: corta a segunda
            first = fm.elidedText(album_name(e), Qt.TextElideMode.ElideRight, int(w) * 2)
            p.drawText(name, int(Qt.TextFlag.TextWordWrap), first)
            yy = name.bottom() + 2
        else:
            p.drawText(name, int(Qt.TextFlag.TextWordWrap), album_name(e))
            yy = y - 1 + br.height() + 2
        p.setFont(F("base"))
        p.setPen(C("text2"))
        lh = QFontMetrics(F("base")).lineSpacing() + 3
        for txt in (group_artist(e), e["genre"], e["year"]):
            if txt and yy + lh <= rect.bottom() + 2:
                p.drawText(QRectF(tx, yy, w, lh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           elide(txt, F("base"), w))
                yy += lh
        p.restore()


class TrackTable(QTableWidget):
    """Músicas agrupadas por artista e álbum, com a capa ao lado e notas clicáveis."""
    rated = pyqtSignal(str, int)

    def __init__(self):
        super().__init__(0, 6)
        self.setObjectName("library")
        self.setHorizontalHeaderLabels(["Álbum", "#", "Título", "Duração", "Avaliação",
                                        "Artista participante"])
        self.horizontalHeaderItem(COL_NUM).setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setMinimumSectionSize(1)
        self.verticalHeader().setDefaultSectionSize(ROW_H)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setMouseTracking(True)
        self.setItemDelegate(TrackDelegate(self))
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        h = self.horizontalHeader()
        h.setHighlightSections(False)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.setFixedHeight(36)
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(COL_ARTIST, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(COL_ALBUM, ALBUM_W)
        self.setColumnWidth(COL_NUM, 40)
        self.setColumnWidth(COL_DUR, 64)
        self.setColumnWidth(COL_RATE, 90)
        self.row_path, self.row_kind, self.album_at = {}, {}, {}
        self.playing, self.hover_row, self.cover_fn = None, -1, None

    def paths_in_order(self):
        return [self.row_path[r] for r in sorted(self.row_path)]

    def selected_rows(self):
        """Posição (0, 1, 2…) das músicas selecionadas, na ordem em que aparecem."""
        order = sorted(self.row_path)
        sel = {i.row() for i in self.selectedIndexes()}
        return [k for k, r in enumerate(order) if r in sel]

    def selected_paths(self):
        rows = sorted({i.row() for i in self.selectedIndexes()})
        return [self.row_path[r] for r in rows if r in self.row_path]

    def fill(self, tracks, cover_fn, rating, playing):
        self.clearSpans()
        self.setRowCount(0)
        self.row_path, self.row_kind, self.album_at = {}, {}, {}
        self.cover_fn, self.hover_row = cover_fn, -1
        # monta os blocos: nome do artista, depois um bloco por álbum (faixas + espaço até a capa)
        rows, prev_artist, i = [], None, 0
        while i < len(tracks):
            e = tracks[i]
            j = i
            while j < len(tracks) and tracks[j]["album_id"] == e["album_id"]:
                j += 1
            if group_artist(e) != prev_artist:
                rows.append(("header", group_artist(e)))
                prev_artist = group_artist(e)
            rows.append(("album", tracks[i:j]))
            i = j
        n = sum(1 if kind == "header" else len(v) + 1 for kind, v in rows)
        self.setRowCount(n)
        blank = Qt.ItemFlag.ItemIsEnabled
        r = 0
        for kind, val in rows:
            if kind == "header":
                it = QTableWidgetItem(val)
                it.setFlags(blank)
                self.setItem(r, 0, it)
                self.setSpan(r, 0, 1, self.columnCount())
                self.setRowHeight(r, HEAD_H)
                self.row_kind[r] = "header"
                r += 1
                continue
            first = r
            for e in val:
                self.row_path[r] = e["path"]
                self.row_kind[r] = "track"
                cells = ["", str(e["track"] or ""), e["title"], fmt(e["dur"]) if e["dur"] else "",
                         "", e["artist"]]
                for c, v in enumerate(cells):
                    it = QTableWidgetItem(v)
                    it.setToolTip(e["path"])
                    self.setItem(r, c, it)
                self.set_rating_cell(r, rating(e))
                self.setRowHeight(r, ROW_H)
                r += 1
            # espaço embaixo: completa a altura da capa e separa do próximo álbum
            self.row_kind[r] = "filler"
            for c in range(self.columnCount()):
                it = QTableWidgetItem("")
                it.setFlags(blank)
                self.setItem(r, c, it)
            self.setRowHeight(r, max(GAP, COVER + GAP - len(val) * ROW_H))
            r += 1
            self.setSpan(first, COL_ALBUM, len(val) + 1, 1)
            self.album_at[first] = val[0]
            self.item(first, COL_ALBUM).setToolTip(album_name(val[0]))
        self.playing = playing

    def set_rating_cell(self, r, n):
        it = self.item(r, COL_RATE)
        it.setData(ROLE, n)
        it.setToolTip("Clique para dar nota" if not n else f"{n} estrela(s) — clique para mudar")

    def mark_playing(self, path):
        self.playing = path
        self.viewport().update()

    def _set_hover(self, row):
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()

    def mouseMoveEvent(self, ev):
        r = self.rowAt(int(ev.position().y()))
        self._set_hover(r if self.row_kind.get(r) == "track" else -1)
        super().mouseMoveEvent(ev)

    def leaveEvent(self, ev):
        self._set_hover(-1)
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        idx = self.indexAt(ev.position().toPoint())
        if (ev.button() == Qt.MouseButton.LeftButton and idx.isValid()
                and idx.column() == COL_RATE and idx.row() in self.row_path):
            rect = self.visualRect(idx)
            x = ev.position().x() - rect.x() - STAR_X
            if 0 <= x <= STAR_STEP * 5:
                n = min(5, int(x // STAR_STEP) + 1)
                cur = int(self.item(idx.row(), COL_RATE).data(ROLE) or 0)
                self.rated.emit(self.row_path[idx.row()], 0 if n == cur else n)
        super().mousePressEvent(ev)

    def mimeTypes(self):
        return [MIME, "text/uri-list"]

    def mimeData(self, items):
        rows = sorted({it.row() for it in items})
        paths = [self.row_path[r] for r in rows if r in self.row_path]
        md = QMimeData()
        md.setData(MIME, "\n".join(paths).encode("utf-8"))
        md.setUrls([QUrl.fromLocalFile(p) for p in paths])
        return md


class QueueDelegate(QStyledItemDelegate):
    """Itens da lista atual: texto em 9 pt; a música tocando em accentText com ▶."""

    def paint(self, p, opt, idx):
        q = self.parent()
        it = q.itemFromIndex(idx)
        playing = it is not None and it is q.playing
        f = F("small_semi") if playing else F("small")
        rect = QRectF(opt.rect)
        p.save()
        p.setFont(f)
        p.setPen(C("accentText") if playing else C("text"))
        if idx.column() == 0:
            x = rect.left() + 8
            if playing:
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setBrush(C("accentText"))
                p.setPen(Qt.PenStyle.NoPen)
                cy = rect.center().y()
                p.drawPolygon(QPolygonF([QPointF(x, cy - 4), QPointF(x + 7, cy), QPointF(x, cy + 4)]))
                p.setPen(C("accentText"))
                x += 14
            box = QRectF(x, rect.top(), rect.right() - x - 4, rect.height())
            p.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       elide(idx.data() or "", f, box.width()))
        else:
            box = rect.adjusted(4, 0, -8, 0)
            p.drawText(box, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, idx.data() or "")
        p.restore()

    def sizeHint(self, opt, idx):
        s = super().sizeHint(opt, idx)
        return QSize(s.width() + (22 if idx.column() == 0 else 12), 26)


class QueueList(QTreeWidget):
    """A lista atual: arrasta para reordenar, recebe músicas da tabela e do gerenciador de arquivos."""
    dropped = pyqtSignal(list, int)
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setColumnCount(2)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setIndentation(4)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        h = self.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.setObjectName("queue")
        self.setMouseTracking(True)
        self.setItemDelegate(QueueDelegate(self))
        self.playing, self.hover_item = None, None

    def drawRow(self, p, opt, idx):
        """Fundo do item: cantos de 7 px; tocando em tint, mouse em cima em surface2."""
        it = self.itemFromIndex(idx)
        sel = self.selectionModel().isSelected(idx)
        back = (C("tint") if it is not None and it is self.playing else
                QColor(misturar(THEME["tint"], THEME["surface"], 0.55)) if sel else
                C("surface2") if it is not None and it is self.hover_item else None)
        if back is not None:
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(back)
            p.drawRoundedRect(QRectF(opt.rect).adjusted(0, 0.5, 0, -0.5), 7, 7)
            p.restore()
        super().drawRow(p, opt, idx)

    def mouseMoveEvent(self, ev):
        it = self.itemAt(ev.position().toPoint())
        if it is not self.hover_item:
            self.hover_item = it
            self.viewport().update()
        super().mouseMoveEvent(ev)

    def leaveEvent(self, ev):
        self.hover_item = None
        self.viewport().update()
        super().leaveEvent(ev)

    def items(self):
        return [self.topLevelItem(i) for i in range(self.topLevelItemCount())]

    def mimeData(self, items):
        md = super().mimeData(items)
        md.setData(MIME, "\n".join(it.data(0, ROLE) for it in items).encode("utf-8"))
        return md

    def dragEnterEvent(self, ev):
        if ev.source() is self:
            return super().dragEnterEvent(ev)
        md = ev.mimeData()
        if md.hasFormat(MIME) or md.hasUrls():
            ev.setDropAction(Qt.DropAction.CopyAction)
            ev.accept()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        if ev.source() is self:
            return super().dragMoveEvent(ev)
        ev.setDropAction(Qt.DropAction.CopyAction)
        ev.accept()

    def dropEvent(self, ev):
        if ev.source() is self:
            super().dropEvent(ev)
            self.changed.emit()
            return
        md = ev.mimeData()
        if md.hasFormat(MIME):
            paths = bytes(md.data(MIME)).decode("utf-8").split("\n")
        else:
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        pos = ev.position().toPoint()
        it = self.itemAt(pos)
        at = self.indexOfTopLevelItem(it) if it else self.topLevelItemCount()
        if it and pos.y() > self.visualItemRect(it).center().y():
            at += 1
        ev.setDropAction(Qt.DropAction.CopyAction)
        ev.accept()
        self.dropped.emit([p for p in paths if p], at)



# ================================================================ MPRIS (widget de mídia do Plasma, tela de bloqueio, KDE Connect…)
try:
    from PyQt6.QtCore import QMetaType, QObject, pyqtClassInfo, pyqtProperty, pyqtSlot
    from PyQt6.QtDBus import (QDBusAbstractAdaptor, QDBusArgument, QDBusConnection, QDBusMessage,
                              QDBusObjectPath)
except ImportError:
    QDBusConnection = None

MPRIS_PATH = "/org/mpris/MediaPlayer2"
MPRIS_ROOT = "org.mpris.MediaPlayer2"
MPRIS_PLAYER = "org.mpris.MediaPlayer2.Player"
LOOP = ["None", "Playlist", "Track"]          # mesma ordem de REPEAT

if QDBusConnection is not None:
    def _as(items):
        return QDBusArgument([str(x) for x in items], QMetaType.Type.QStringList.value)

    def _x(n):
        return QDBusArgument(int(n), QMetaType.Type.LongLong.value)

    @pyqtClassInfo("D-Bus Interface", MPRIS_ROOT)
    class MprisRoot(QDBusAbstractAdaptor):
        def __init__(self, parent, win):
            super().__init__(parent)
            self.win = win

        @pyqtProperty(bool)
        def CanQuit(self):
            return True

        @pyqtProperty(bool)
        def CanRaise(self):
            return True

        @pyqtProperty(bool)
        def HasTrackList(self):
            return False

        @pyqtProperty(str)
        def Identity(self):
            return "Linux Music Player"

        @pyqtProperty(str)
        def DesktopEntry(self):
            return QApplication.desktopFileName() or APP

        @pyqtProperty("QStringList")
        def SupportedUriSchemes(self):
            return ["file"]

        @pyqtProperty("QStringList")
        def SupportedMimeTypes(self):
            return ["audio/mpeg", "audio/flac", "audio/ogg", "audio/x-opus+ogg", "audio/mp4",
                    "audio/x-m4a", "audio/x-wav", "audio/aac", "audio/webm"]

        @pyqtSlot()
        def Raise(self):
            self.win.showNormal()
            self.win.raise_()
            self.win.activateWindow()

        @pyqtSlot()
        def Quit(self):
            self.win.close()

    @pyqtClassInfo("D-Bus Interface", MPRIS_PLAYER)
    class MprisPlayer(QDBusAbstractAdaptor):
        Seeked = pyqtSignal("qlonglong")

        def __init__(self, parent, win):
            super().__init__(parent)
            self.win = win

        @pyqtProperty(str)
        def PlaybackStatus(self):
            return self.win.mpris_status()

        def _get_loop(self):
            return LOOP[self.win.repeat]

        def _set_loop(self, v):
            if v in LOOP:
                while self.win.repeat != LOOP.index(v):
                    self.win.cycle_repeat()
        LoopStatus = pyqtProperty(str, fget=_get_loop, fset=_set_loop)

        def _get_rate(self):
            return 1.0

        def _set_rate(self, v):
            pass
        Rate = pyqtProperty(float, fget=_get_rate, fset=_set_rate)

        def _get_shuffle(self):
            return self.win.btn_shuffle.isChecked()

        def _set_shuffle(self, v):
            self.win.btn_shuffle.setChecked(bool(v))
        Shuffle = pyqtProperty(bool, fget=_get_shuffle, fset=_set_shuffle)

        @pyqtProperty("QVariantMap")
        def Metadata(self):
            return self.win.mpris_metadata()

        def _get_volume(self):
            return 0.0 if self.win.btn_mute.isChecked() else self.win.volume.value() / 100

        def _set_volume(self, v):
            self.win.volume.setValue(round(max(0.0, min(1.0, float(v))) * 100))
        Volume = pyqtProperty(float, fget=_get_volume, fset=_set_volume)

        @pyqtProperty("qlonglong")
        def Position(self):
            return int(self.win.player.position()) * 1000

        @pyqtProperty(float)
        def MinimumRate(self):
            return 1.0

        @pyqtProperty(float)
        def MaximumRate(self):
            return 1.0

        @pyqtProperty(bool)
        def CanGoNext(self):
            return self.win.queue.topLevelItemCount() > 0

        @pyqtProperty(bool)
        def CanGoPrevious(self):
            return self.win.queue.topLevelItemCount() > 0

        @pyqtProperty(bool)
        def CanPlay(self):
            return self.win.queue.topLevelItemCount() > 0 or bool(self.win.table.row_path)

        @pyqtProperty(bool)
        def CanPause(self):
            return self.win.cur_path() is not None

        @pyqtProperty(bool)
        def CanSeek(self):
            return self.win.cur_path() is not None

        @pyqtProperty(bool)
        def CanControl(self):
            return True

        @pyqtSlot()
        def Next(self):
            self.win.next()

        @pyqtSlot()
        def Previous(self):
            self.win.prev()

        @pyqtSlot()
        def Pause(self):
            self.win.player.pause()

        @pyqtSlot()
        def PlayPause(self):
            self.win.toggle()

        @pyqtSlot()
        def Stop(self):
            self.win.stop()

        @pyqtSlot()
        def Play(self):
            if self.win.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.win.toggle()

        @pyqtSlot("qlonglong")
        def Seek(self, offset_us):
            if self.win.cur_path():
                self.win.seek_to(max(0, self.win.player.position() + offset_us // 1000))

        @pyqtSlot(QDBusObjectPath, "qlonglong")
        def SetPosition(self, track, pos_us):
            if track.path() == self.win.mpris_trackid() and 0 <= pos_us // 1000 <= self.win.player.duration():
                self.win.seek_to(pos_us // 1000)

        @pyqtSlot(str)
        def OpenUri(self, uri):
            path = QUrl(uri).toLocalFile()
            if path:
                self.win.queue_add([path], self.win.next_pos(), play=True)

    class Mpris(QObject):
        """Publica o reprodutor no D-Bus da sessão, no padrão MPRIS2."""
        def __init__(self, win):
            super().__init__(win)
            self.root = MprisRoot(self, win)
            self.player = MprisPlayer(self, win)
            self.bus = QDBusConnection.sessionBus()
            self.ok = self.bus.isConnected() and self.bus.registerObject(MPRIS_PATH, self)
            if self.ok:
                name = "org.mpris.MediaPlayer2." + APP
                if not self.bus.registerService(name):                       # outra janela aberta
                    self.ok = self.bus.registerService(f"{name}.instancia{os.getpid()}")

        def changed(self, props):
            if not self.ok:
                return
            msg = QDBusMessage.createSignal(MPRIS_PATH, "org.freedesktop.DBus.Properties",
                                            "PropertiesChanged")
            msg.setArguments([MPRIS_PLAYER, props, _as([])])
            self.bus.send(msg)
else:
    Mpris = None

class NavDelegate(QStyledItemDelegate):
    """Item da árvore: ícone Phosphor em text2 e texto em text; selecionado em onAccent, SemiBold.
    Nas pastas, com o mouse em cima, aparece a lixeira para excluir da biblioteca."""

    def paint(self, p, opt, idx):
        tree = self.parent()
        it = tree.itemFromIndex(idx)
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        rect = QRectF(opt.rect)
        top = it is not None and it.parent() is None
        f = F("bold") if top else F("semi") if sel else F("base")
        fg = C("onAccent") if sel else C("text")
        x = rect.left() + 2
        icon = idx.data(ROLE + 1)
        if icon:
            pm = ph(icon, color=C("onAccent") if sel else C("text2")).pixmap(18, 18)
            p.drawPixmap(QRectF(x, rect.center().y() - 9, 18, 18).toRect(), pm)
            x += 26
        right = rect.right() - 6
        key = idx.data(ROLE)
        if it is not None and it is tree.hover_item and key and key[0] == "folder":
            tr = tree.trash_rect(opt.rect)
            p.drawPixmap(tr, ph("trash", color=C("onAccent") if sel else C("text2")).pixmap(16, 16))
            right = tr.left() - 4
        p.save()
        p.setFont(f)
        p.setPen(fg)
        box = QRectF(x, rect.top(), right - x, rect.height())
        p.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   elide(idx.data() or "", f, box.width()))
        p.restore()

    def sizeHint(self, opt, idx):
        s = super().sizeHint(opt, idx)
        return QSize(s.width() + 30, 30)


class NavTree(QTreeWidget):
    """Navegação da esquerda. Soltar músicas em cima de uma lista adiciona a ela;
    em cima de "Listas", cria uma lista nova. A lixeira das pastas exclui da biblioteca."""
    dropped = pyqtSignal(object, list)
    removeFolder = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setMouseTracking(True)
        self.setIndentation(18)
        self.setItemDelegate(NavDelegate(self))
        self.hover_item = None

    def trash_rect(self, item_rect):
        r = QRect(item_rect)
        return QRect(self.viewport().width() - 30, r.center().y() - 8, 16, 16)

    def drawRow(self, p, opt, idx):
        """A pílula do item ocupa a largura toda: selecionado em accent, mouse em cima em surface2."""
        it = self.itemFromIndex(idx)
        sel = self.selectionModel().isSelected(idx)
        back = C("accent") if sel else C("surface2") if it is not None and it is self.hover_item else None
        if back is not None:
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(back)
            p.drawRoundedRect(QRectF(0, opt.rect.top() + 0.5, self.viewport().width(),
                                     opt.rect.height() - 1), 8, 8)
            p.restore()
        super().drawRow(p, opt, idx)

    def mouseMoveEvent(self, ev):
        it = self.itemAt(ev.position().toPoint())
        if it is not self.hover_item:
            self.hover_item = it
            self.viewport().update()
        super().mouseMoveEvent(ev)

    def leaveEvent(self, ev):
        self.hover_item = None
        self.viewport().update()
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        pos = ev.position().toPoint()
        it = self.itemAt(pos)
        key = it.data(0, ROLE) if it else None
        if (ev.button() == Qt.MouseButton.LeftButton and key and key[0] == "folder"
                and self.trash_rect(self.visualItemRect(it)).adjusted(-4, -6, 4, 6).contains(pos)):
            self.removeFolder.emit(key[1])
            ev.accept()
            return
        super().mousePressEvent(ev)


    def _target(self, ev):
        it = self.itemAt(ev.position().toPoint())
        key = it.data(0, ROLE) if it else None
        return key if key and key[0] in ("playlist", "playlists") else None

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME):
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        key = self._target(ev) if ev.mimeData().hasFormat(MIME) else None
        if key:
            self.setCurrentItem(self.itemAt(ev.position().toPoint()))   # mostra onde vai cair
            ev.setDropAction(Qt.DropAction.CopyAction)
            ev.accept()
        else:
            ev.ignore()

    def dropEvent(self, ev):
        key = self._target(ev)
        if not key:
            ev.ignore()
            return
        paths = [p for p in bytes(ev.mimeData().data(MIME)).decode("utf-8").split("\n") if p]
        ev.setDropAction(Qt.DropAction.CopyAction)
        ev.accept()
        self.dropped.emit(key, paths)


# ================================================================ janela
class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self._applying = True                     # até o fim do __init__
        self.setWindowTitle("Linux Music Player")
        self.resize(1360, 860)
        self.setAcceptDrops(True)
        self.settings = QSettings(APP, APP)
        tema = self.settings.value("tema", "mp12-claro")
        if tema == "sonivell":                    # o LMP 3 saiu: quem usava cai no LMP 2
            tema = "mp12-escuro"
        self.theme = apply_theme(tema)
        self.excluded = [f for f in json.loads(self.settings.value("excluidas", "[]")) if f]
        self.folders = [f for f in json.loads(self.settings.value("pastas", "[]")) if f]
        cache = _read_json(CACHE_FILE, {})
        self.lib = cache.get("faixas", {}) if cache.get("versao") == 3 else {}   # 3: capa por arquivo
        self.covers = cache.get("capas", {}) if cache.get("versao") == 3 else {}
        self.extra = {}                       # músicas tocadas fora da biblioteca
        self.ratings = _read_json(RATINGS_FILE, {})
        self._pix = {}
        self._pos_shown = -1
        self.view_key, self.view_tracks, self.view_pos = ("all",), [], []
        self.cur_item, self.history, self.shuffle_done = None, [], set()
        self.scanner, self._errors, self._dragging, self._rescan = None, 0, False, False

        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self.on_position)
        self.player.durationChanged.connect(self.on_duration)
        self.player.mediaStatusChanged.connect(self.on_status)
        self.player.playbackStateChanged.connect(self.on_state)
        self.player.errorOccurred.connect(self.on_error)

        # ---- 1. barra de ferramentas (direto sobre o fundo, sem cartão)
        self.crumb = QLabel()
        self.crumb.setObjectName("crumb")
        self.crumb.setTextFormat(Qt.TextFormat.RichText)
        self.crumb.setMinimumWidth(80)
        self.crumb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        b_add = QPushButton(" Adicionar pasta à biblioteca…")
        b_add.clicked.connect(self.add_library_folder)
        b_scan = QPushButton(" Atualizar")
        b_scan.setToolTip("Procura músicas novas, alteradas ou apagadas nas pastas da biblioteca")
        b_scan.clicked.connect(self.rescan)
        b_play_folder = QPushButton(" Tocar pasta…")
        b_play_folder.setToolTip("Toca uma pasta sem colocá-la na biblioteca")
        b_play_folder.clicked.connect(self.play_folder_dialog)
        b_files = QPushButton(" Tocar arquivos…")
        b_files.clicked.connect(self.play_files_dialog)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Pesquisar")
        self.search.setClearButtonEnabled(True)
        self.search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)   # não rouba o foco ao abrir
        self.search_icon = self.search.addAction(QIcon(), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(lambda _: self.refresh_view())
        self.btn_theme = QToolButton()
        self.btn_theme.setObjectName("toolButton")
        self.btn_theme.setText(" Tema")
        self.btn_theme.setToolTip("Tema de cores")
        self.btn_theme.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_theme.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_theme.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        theme_menu = QMenu(self.btn_theme)
        group = QActionGroup(theme_menu)
        self.theme_actions = {}
        for key, name in THEME_ORDER:
            a = theme_menu.addAction(theme_swatch(key), name)
            a.setCheckable(True)
            a.setChecked(key == self.theme)
            group.addAction(a)
            a.triggered.connect(lambda _c=False, k=key: self.set_theme(k))
            self.theme_actions[key] = a
        theme_menu.addSeparator()
        theme_menu.addAction(f"Linux Music Player {__version__}").setEnabled(False)
        self.btn_theme.setMenu(theme_menu)
        self._icon_buttons = [(b_add, "folder-plus"), (b_scan, "arrows-clockwise"),
                              (b_play_folder, "folder-open"), (b_files, "file-audio")]
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        for w in (b_add, b_scan, b_play_folder, b_files):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            top.addWidget(w)
        top.addSpacing(14)
        top.addWidget(self.crumb, 1)
        top.addSpacing(8)
        top.addWidget(self.search)
        top.addWidget(self.btn_theme)

        # ---- 2. árvore da biblioteca (cartão de 230 px)
        self.nav = NavTree()
        self.nav.setObjectName("nav")
        self.nav.dropped.connect(self.on_nav_drop)
        self.nav.removeFolder.connect(self.remove_folder)
        self.nav.setHeaderHidden(True)
        self.nav.itemClicked.connect(lambda it, _c: self.open_key(it.data(0, ROLE)))
        self.nav.currentItemChanged.connect(
            lambda it, _p: it is not None and self.open_key(it.data(0, ROLE)))
        self.nav.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.nav.customContextMenuRequested.connect(self.nav_menu)
        nav_card = self.card("navCard", self.nav, (8, 10, 8, 10))
        nav_card.setMinimumWidth(180)

        # ---- 3. tabela agrupada ou grade (artistas, álbuns, gêneros…) — cartão principal
        self.table = TrackTable()
        self.table.cellDoubleClicked.connect(self.on_table_double)
        self.table.rated.connect(self.set_rating)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_menu)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self.table,
                  lambda: self.play_from_table(self.table.currentRow()),
                  context=Qt.ShortcutContext.WidgetShortcut)
        self.grid = QListWidget()
        self.grid.setObjectName("grid")
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setIconSize(QSize(150, 150))
        self.grid.setGridSize(QSize(180, 222))
        self.grid.setSpacing(4)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setWordWrap(True)
        self.grid.setUniformItemSizes(True)
        self.grid.itemActivated.connect(lambda it: self.open_key(it.data(ROLE)))
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self.grid_menu)
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setContentsMargins(40, 20, 40, 20)
        el.addStretch()
        self.empty_lbl = QLabel()
        self.empty_lbl.setObjectName("sub")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setWordWrap(True)
        el.addWidget(self.empty_lbl)
        el.addSpacing(10)
        b_empty = QPushButton(" Adicionar pasta à biblioteca…")
        b_empty.clicked.connect(self.add_library_folder)
        el.addWidget(b_empty, 0, Qt.AlignmentFlag.AlignCenter)
        self._icon_buttons.append((b_empty, "folder-plus"))
        el.addStretch()
        self.center = QStackedWidget()
        for w in (self.table, self.grid, empty):
            self.center.addWidget(w)
        lib_card = self.card("libraryCard", self.center, (1, 1, 1, 1))

        # ---- 4. lista atual (cartão de 290 px)
        b_save = QPushButton(" Salvar lista")
        b_save.clicked.connect(self.save_queue_dialog)
        b_clr = QPushButton(" Limpar lista")
        b_clr.clicked.connect(self.clear_queue)
        for b in (b_save, b_clr):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._icon_buttons += [(b_save, "floppy-disk"), (b_clr, "trash")]
        qbtn = QHBoxLayout()
        qbtn.setSpacing(8)
        qbtn.addWidget(b_save)
        qbtn.addStretch()
        qbtn.addWidget(b_clr)
        self.np_cover = QLabel()
        self.np_cover.setFixedSize(84, 84)
        self.np_title = QLabel("Nada tocando")
        self.np_title.setWordWrap(True)
        self.np_info = QLabel("")
        self.np_info.setObjectName("sub")
        self.np_info.setWordWrap(True)
        np_txt = QVBoxLayout()
        np_txt.setSpacing(2)
        np_txt.addWidget(self.np_title)
        np_txt.addWidget(self.np_info)
        np_txt.addStretch()
        np = QHBoxLayout()
        np.setContentsMargins(10, 10, 10, 10)
        np.setSpacing(12)
        np.addWidget(self.np_cover, 0, Qt.AlignmentFlag.AlignTop)
        np.addLayout(np_txt, 1)
        now_card = QFrame()
        now_card.setObjectName("nowCard")
        now_card.setLayout(np)
        self.q_title = QLabel("Lista atual")
        self.q_title.setObjectName("secao")
        self.queue = QueueList()
        self.queue.itemDoubleClicked.connect(lambda it, _c: self.play_item(it))
        self.queue.dropped.connect(lambda paths, at: self.queue_add(paths, at))
        self.queue.changed.connect(self.queue_changed)
        self.queue.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue.customContextMenuRequested.connect(self.queue_menu)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self.queue, self.remove_selected_from_queue,
                  context=Qt.ShortcutContext.WidgetShortcut)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self.queue,
                  lambda: self.queue.currentItem() and self.play_item(self.queue.currentItem()),
                  context=Qt.ShortcutContext.WidgetShortcut)
        self.q_foot = QLabel("")
        self.q_foot.setObjectName("sub")
        right = QVBoxLayout()
        right.setContentsMargins(12, 12, 12, 10)
        right.setSpacing(10)
        right.addLayout(qbtn)
        right.addWidget(now_card)
        right.addSpacing(2)
        right.addWidget(self.q_title)
        right.addWidget(self.queue, 1)
        right.addWidget(self.q_foot)
        queue_card = QFrame()
        queue_card.setObjectName("queueCard")
        queue_card.setLayout(right)
        queue_card.setMinimumWidth(250)

        self.split = QSplitter()
        self.split.setHandleWidth(10)
        self.split.setChildrenCollapsible(False)
        for w in (nav_card, lib_card, queue_card):
            self.split.addWidget(w)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([230, 800, 290])

        # ---- 5. barra de reprodução (cartão na largura toda)
        self.lbl_pos = QLabel("0:00")
        self.lbl_pos.setObjectName("time")
        self.seek = ClickSlider(Qt.Orientation.Horizontal)
        self.seek.setObjectName("seek")
        self.seek.setRange(0, 0)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.seek.sliderReleased.connect(self.on_seek_release)
        self.seek.sliderMoved.connect(lambda v: self.lbl_pos.setText(fmt(v / 1000)))
        self.lbl_dur = QLabel("0:00")
        self.lbl_dur.setObjectName("time")
        self.lbl_dur.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        seek_row = QHBoxLayout()
        seek_row.setSpacing(12)
        seek_row.addWidget(self.lbl_pos)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.lbl_dur)

        self.mini_cover = QLabel()
        self.mini_cover.setFixedSize(44, 44)
        self.mini_title = QLabel("")
        self.mini_artist = QLabel("")
        self.mini_artist.setObjectName("sub")
        for lb in (self.mini_title, self.mini_artist):
            lb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        mini_txt = QVBoxLayout()
        mini_txt.setSpacing(0)
        mini_txt.addStretch()
        mini_txt.addWidget(self.mini_title)
        mini_txt.addWidget(self.mini_artist)
        mini_txt.addStretch()

        def tb(name, tip, slot, check=False):
            b = QToolButton()
            b.setObjectName("transport")
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setIconSize(QSize(20, 20))
            b.setCheckable(check)
            b.clicked.connect(slot)
            return b
        self.btn_shuffle = tb("shuffle", "Aleatório", lambda: None, check=True)
        self.btn_shuffle.toggled.connect(self.on_shuffle)
        self.repeat = 0
        self.btn_repeat = tb("repeat", REPEAT[0], self.cycle_repeat, check=True)
        self.btn_stop = tb("stop", "Parar", self.stop)
        self.btn_prev = tb("skip-back", "Anterior (Ctrl+←)", self.prev)
        self.btn_play = QToolButton()
        self.btn_play.setObjectName("playButton")
        self.btn_play.setToolTip("Tocar / pausar (Espaço)")
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.setFixedSize(46, 46)
        self.btn_play.setIconSize(QSize(22, 22))
        self.btn_play.clicked.connect(self.toggle)
        self.btn_next = tb("skip-forward", "Próxima (Ctrl+→)", self.next)
        self.btn_mute = tb("speaker-high", "Mudo", lambda: None, check=True)
        self.btn_mute.toggled.connect(self.on_mute)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("volume")
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(120)
        self.volume.setSingleStep(5)
        self.volume.setPageStep(10)
        self.volume.setToolTip("Volume (Ctrl+↑ / Ctrl+↓)")
        self.vol_lbl = QLabel("")
        self.vol_lbl.setObjectName("time")
        self.vol_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.volume.valueChanged.connect(self.on_volume)
        # as barras não ficam selecionadas: as setas do teclado não mudam volume nem posição
        for w in (self.volume, self.seek):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sep = QFrame()
        sep.setObjectName("sep")
        sep.setFixedSize(1, 22)

        # o play fica exatamente no centro da barra: os botões da esquerda vão colados nele
        # (no lado esquerdo) e a próxima e o volume no lado direito; os dois lados têm o mesmo peso
        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        left.addWidget(self.mini_cover)
        left.addSpacing(4)
        left.addLayout(mini_txt, 1)
        left.addSpacing(10)
        for w in (self.btn_shuffle, self.btn_repeat):
            left.addWidget(w)
        left.addSpacing(6)
        left.addWidget(sep)
        left.addSpacing(6)
        for w in (self.btn_stop, self.btn_prev):
            left.addWidget(w)
        left_w = QWidget()
        left_w.setLayout(left)
        rgt = QHBoxLayout()
        rgt.setContentsMargins(0, 0, 0, 0)
        rgt.setSpacing(6)
        rgt.addWidget(self.btn_next)
        rgt.addStretch()
        rgt.addWidget(self.btn_mute)
        rgt.addWidget(self.volume)
        rgt.addSpacing(6)
        rgt.addWidget(self.vol_lbl)
        right_w = QWidget()
        right_w.setLayout(rgt)
        for w in (left_w, right_w):          # lados com o mesmo peso: o play fica no centro
            w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        bottom.addWidget(left_w, 1)
        bottom.addWidget(self.btn_play)
        bottom.addWidget(right_w, 1)

        bar = QVBoxLayout()
        bar.setContentsMargins(16, 10, 16, 10)
        bar.setSpacing(6)
        bar.addLayout(seek_row)
        bar.addLayout(bottom)
        bar_w = QFrame()
        bar_w.setObjectName("playerBar")
        bar_w.setLayout(bar)

        lay = QVBoxLayout()
        lay.setContentsMargins(10, 10, 10, 0)
        lay.setSpacing(10)
        lay.addLayout(top)
        lay.addWidget(self.split, 1)
        lay.addWidget(bar_w)
        central = QWidget()
        central.setObjectName("central")
        central.setLayout(lay)
        self.setCentralWidget(central)

        # ---- 6. barra de status: o resumo da biblioteca, direto sobre o fundo
        self.status_lbl = QLabel("")
        self.statusBar().addWidget(self.status_lbl, 1)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().setContentsMargins(10, 0, 10, 2)

        # ---- atalhos
        for keys, slot in ((Qt.Key.Key_MediaTogglePlayPause, self.toggle),
                           (Qt.Key.Key_MediaPlay, self.toggle),
                           (Qt.Key.Key_MediaPause, self.player.pause),
                           (Qt.Key.Key_MediaStop, self.stop),
                           (Qt.Key.Key_MediaNext, self.next),
                           (Qt.Key.Key_MediaPrevious, self.prev),
                           ("Ctrl+Right", self.next), ("Ctrl+Left", self.prev),
                           ("Ctrl+P", self.toggle),
                           ("Ctrl+F", self.search.setFocus), ("Ctrl+E", self.search.setFocus),
                           ("F5", self.rescan)):
            QShortcut(QKeySequence(keys), self).activated.connect(slot)
        QShortcut(QKeySequence("Space"), self, self.space)
        QShortcut(QKeySequence("Alt+Right"), self, lambda: self.jump(+10))
        QShortcut(QKeySequence("Alt+Left"), self, lambda: self.jump(-10))
        QShortcut(QKeySequence("Ctrl+Up"), self, lambda: self.volume.setValue(self.volume.value() + 5))
        QShortcut(QKeySequence("Ctrl+Down"), self, lambda: self.volume.setValue(self.volume.value() - 5))

        # ---- preferências salvas
        self.volume.setValue(int(self.settings.value("volume", 70)))
        self.on_volume(self.volume.value())
        self.btn_shuffle.setChecked(self.settings.value("aleatorio", "false") == "true")
        for _ in range(int(self.settings.value("repetir", 0)) % 3):
            self.cycle_repeat()
        if self.settings.value("divisao-cartoes"):
            self.split.restoreState(self.settings.value("divisao-cartoes"))
        self.show_now(None)
        self.style_extras()
        self.build_nav()
        self._serial, self._art = 0, None
        self.restore_queue()
        self.open_key(("all",))
        self.update_summary()
        self.mpris = None
        if Mpris is not None:
            try:
                self.mpris = Mpris(self)
            except Exception as err:            # sem D-Bus: o reprodutor funciona igual
                print("MPRIS indisponível:", err, file=sys.stderr)
        if self.folders:
            self.rescan()
        self._applying = False

    def card(self, name, child, margins):
        """Um cartão: QFrame com nome (o QSS dá fundo, borda e cantos de 14 px)."""
        f = QFrame()
        f.setObjectName(name)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(*margins)
        lay.setSpacing(0)
        lay.addWidget(child)
        return f

    # ================================================================ biblioteca
    def entry(self, path):
        e = self.lib.get(path) or self.extra.get(path)
        if e is None:
            e = self.extra[path] = read_entry(path)
        return e

    def rating(self, e):
        return int(self.ratings.get(e["path"], e.get("rating_file", 0)) or 0)

    def set_rating(self, path, n):
        self.ratings[path] = n
        _write_json(RATINGS_FILE, self.ratings)
        for r, p in self.table.row_path.items():
            if p == path:
                self.table.set_rating_cell(r, n)

    def cover_file(self, e):
        """A capa da própria música (a de dentro do arquivo ou a da pasta dela)."""
        if "cover" not in e and e["path"] in self.extra:      # tocada de fora da biblioteca
            e["cover"] = read_entry(e["path"], want_cover=True).get("cover", "")
        if "cover" in e:
            return e["cover"] or ""
        return self.covers.get(e["album_id"]) or ""

    def cover_file_pix(self, fn, size):
        """Miniatura gravada no cache (ou a capa vazia)."""
        key = ("f", fn, size)
        if key not in self._pix:
            pm = QPixmap(os.path.join(COVER_DIR, fn)) if fn else QPixmap()
            if pm.isNull():
                pm = self._placeholder(size)
            else:
                pm = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._pix[key] = pm
        return self._pix[key]

    def cover_round(self, fn, size, radius):
        """Capa com cantos arredondados, feita uma vez por tamanho (44, 84, 92 px…) e guardada
        na memória e em ~/.cache; nunca no paint."""
        dpr = max(1.0, self.devicePixelRatioF())
        key = ("r", fn, size, radius, dpr)
        if key not in self._pix:
            disk = os.path.join(COVER_DIR, f"r{size}-{radius}-{dpr:g}-{fn}") if fn else None
            pm = QPixmap(disk) if disk and os.path.exists(disk) else QPixmap()
            if pm.isNull():
                pm = rounded_pix(self.cover_file_pix(fn, round(size * dpr)), size, radius, dpr)
                if disk:
                    os.makedirs(COVER_DIR, exist_ok=True)
                    pm.save(disk)
            pm.setDevicePixelRatio(dpr)
            self._pix[key] = pm
        return self._pix[key]

    def cover_of(self, e, size, radius):
        return self.cover_round(self.cover_file(e) if e else "", size, radius)

    def album_cover(self, e, size=COVER, radius=12):
        """Capa do bloco do álbum na tabela e na grade."""
        return self.cover_round(self.covers.get(e["album_id"]) or self.cover_file(e), size, radius)

    # ================================================================ tema
    def style_extras(self):
        """O que a folha de estilo não alcança: ícones recoloridos, fontes da escala e o caminho."""
        t2, tx = C("text2"), C("text")
        for b, name in self._icon_buttons:
            b.setIcon(ph(name, color=t2))
        self.search_icon.setIcon(ph("magnifying-glass", color=t2))
        self.btn_theme.setIcon(ph("palette", color=t2))
        for b, name in ((self.btn_stop, "stop"), (self.btn_prev, "skip-back"), (self.btn_next, "skip-forward")):
            b.setIcon(ph(name, fill=True, color=tx))
        self.mode_icons()
        self.on_mute(self.btn_mute.isChecked())
        self.on_state(self.player.playbackState())
        for w, kind in ((self.np_title, "np"), (self.np_info, "base"), (self.q_title, "label"),
                        (self.q_foot, "small"), (self.mini_title, "semi"), (self.mini_artist, "small"),
                        (self.lbl_pos, "time"), (self.lbl_dur, "time"), (self.vol_lbl, "time"),
                        (self.status_lbl, "small"), (self.empty_lbl, "base")):
            w.setFont(F(kind))
        fm = QFontMetrics(F("time"))
        self.vol_lbl.setFixedWidth(fm.horizontalAdvance("100%") + 2)
        for lb in (self.lbl_pos, self.lbl_dur):
            lb.setMinimumWidth(fm.horizontalAdvance("0:00:00"))
        self.set_crumb()

    def set_theme(self, key):
        self.theme = apply_theme(key)
        self.settings.setValue("tema", self.theme)
        for k, a in self.theme_actions.items():
            a.setChecked(k == self.theme)
        self._pix.clear()                      # capas vazias são desenhadas na cor do tema
        self.style_extras()
        self.build_nav()
        self.refresh_view()
        self.mark_queue()
        p = self.cur_path()
        self.show_now(self.entry(p) if p else None)

    def event(self, ev):
        """No "Do sistema", troca as cores junto com o esquema de cores do Plasma/GNOME."""
        t = ev.type().value
        if t in (THEME_CHANGE, QEvent.Type.ApplicationPaletteChange.value) and not self._applying:
            QTimer.singleShot(150, lambda th=(t == THEME_CHANGE): self.system_colors_changed(th))
        return super().event(ev)

    def system_colors_changed(self, theme_event):
        if self._applying:
            return
        app = QApplication.instance()
        mine = _theme_palette(THEME)
        self._applying = True
        try:
            if app.palette() != mine:                 # alguém trocou a paleta do programa
                new = QPalette(app.palette())
            elif theme_event and self.theme == "sistema":
                app.setPalette(QPalette())            # lê a paleta atual do sistema…
                new = QPalette(app.palette())
                app.setPalette(mine)                  # …e devolve a nossa
            else:
                return
            if new == _SYSTEM.get("palette") and app.palette() == mine:
                return
            _SYSTEM["palette"] = new
            self.set_theme(self.theme)
        finally:
            self._applying = False

    def _placeholder(self, size):
        """Capa vazia: quadrado em surface2 com uma nota musical."""
        pm = QPixmap(size, size)
        pm.fill(C("surface2"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(C("starOff"))
        f = QFont(base_font())
        f.setPixelSize(max(6, int(size * 0.42)))
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "♪")
        p.end()
        return pm

    def add_library_folder(self):
        start = self.folders[-1] if self.folders else os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Adicionar pasta à biblioteca", start)
        if d:
            self.add_folder(d)

    def add_folder(self, d):
        d = os.path.abspath(d)
        inside_excluded = d in self.excluded or any(d.startswith(x + os.sep) for x in self.excluded)
        if any(d == f or d.startswith(f + os.sep) for f in self.folders) and not inside_excluded:
            self.statusBar().showMessage(f"{d} já está na biblioteca.", 6000)
            return
        if d in self.excluded or any(d.startswith(x + os.sep) for x in self.excluded):
            # era uma subpasta excluída: volta a aparecer
            self.excluded = [x for x in self.excluded if not (x == d or x.startswith(d + os.sep)
                                                              or d.startswith(x + os.sep))]
            self.settings.setValue("excluidas", json.dumps(self.excluded))
            self.build_nav()
            self.rescan()
            return
        self.folders = [f for f in self.folders if not f.startswith(d + os.sep)] + [d]
        self.settings.setValue("pastas", json.dumps(self.folders))
        self.build_nav()
        self.rescan()

    def remove_folder(self, d):
        """Exclui uma pasta (ou subpasta) da biblioteca. Nada é apagado do disco."""
        n = sum(1 for p in self.lib if p.startswith(d + os.sep))
        box = QMessageBox(QMessageBox.Icon.Question, "Excluir da biblioteca",
                          f"Excluir esta pasta da biblioteca?\n\n{d}\n\n{n} música(s) deixa(m) de "
                          "aparecer aqui. Os arquivos NÃO são apagados do disco; dá para pôr a pasta "
                          "de volta com \"Adicionar pasta\".", parent=self)
        ok = box.addButton("Excluir da biblioteca", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not ok:
            return
        if d in self.folders:
            self.folders = [f for f in self.folders if f != d]
        else:                                    # subpasta: fica na lista de excluídas
            self.excluded.append(d)
        # o que estava dentro dela some das listas de excluídas também
        self.excluded = [x for x in self.excluded
                         if any(x.startswith(f + os.sep) for f in self.folders)]
        self.settings.setValue("pastas", json.dumps(self.folders))
        self.settings.setValue("excluidas", json.dumps(self.excluded))
        self.lib = {p: e for p, e in self.lib.items() if not p.startswith(d + os.sep)}
        self.build_nav()
        if self.view_key[0] == "folder" and (self.view_key[1] == d or self.view_key[1].startswith(d + os.sep)):
            self.open_key(("folders",))
        else:
            self.refresh_view()
        self.statusBar().showMessage(f"Pasta excluída da biblioteca: {d}", 8000)
        self.rescan()

    def rescan(self):
        if self.scanner is not None and self.scanner.isRunning():
            self._rescan = True                      # termina a atual e lê de novo
            return
        if not self.folders:
            self.lib, self.covers = {}, {}
            self.refresh_view()
            return
        self.statusBar().showMessage("Lendo a biblioteca…")
        self.scanner = Scanner(list(self.folders), dict(self.lib), self.excluded)
        self.scanner.progress.connect(
            lambda i, n: self.statusBar().showMessage(f"Lendo a biblioteca… {i} de {n}"))
        self.scanner.done.connect(self.on_scanned)
        self.scanner.start()

    def on_scanned(self, tracks, covers):
        self.lib, self.covers, self._pix = tracks, covers, {}
        self.extra = {p: e for p, e in self.extra.items() if p not in tracks}
        if self._rescan:
            self._rescan = False
            self.scanner.wait()
            self.rescan()
            return
        self.statusBar().clearMessage()
        self.update_summary()
        self.build_nav()
        self.refresh_view()
        self.refresh_queue_texts()

    def update_summary(self):
        """A barra de status: o resumo da biblioteca."""
        if not self.lib:
            self.status_lbl.setText("")
            return
        total = sum(e["dur"] for e in self.lib.values())
        self.status_lbl.setText(
            f"Biblioteca: {len(self.lib)} música(s), {len({e['album_id'] for e in self.lib.values()})} "
            f"álbum(ns), {fmt_total(total)}.")

    # ================================================================ navegação
    def playlist_files(self):
        try:
            names = sorted(n for n in os.listdir(LISTS_DIR) if n.lower().endswith((".m3u8", ".m3u")))
        except OSError:
            names = []
        return [os.path.join(LISTS_DIR, n) for n in names]

    def build_nav(self):
        keep = self.view_key
        self.nav.blockSignals(True)
        self.nav.clear()
        dir_icon = "folder"

        def add(parent, text, key, icon=None):
            it = QTreeWidgetItem([text])
            it.setData(0, ROLE, key)
            it.setData(0, ROLE + 1, icon)
            (parent.addChild(it) if parent else self.nav.addTopLevelItem(it))
            return it
        lib = add(None, "Biblioteca", ("all",), "books")
        pl = add(lib, "Listas", ("playlists",), "playlist")
        pl.setToolTip(0, "Solte músicas aqui para criar uma lista nova")
        for fpath in self.playlist_files():
            li = add(pl, os.path.splitext(os.path.basename(fpath))[0], ("playlist", fpath), "queue")
            li.setToolTip(0, f"{len(read_m3u(fpath))} música(s) — solte músicas aqui para adicionar")
        mus = add(lib, "Músicas", ("all",), "music-notes")
        add(mus, "Todas as músicas", ("all",), "music-note-simple")
        add(mus, "Artista", ("artists",), "user")
        add(mus, "Álbum", ("albums",), "vinyl-record")
        add(mus, "Gênero", ("genres",), "tag")
        fol = add(lib, "Pastas", ("folders",), "folder")
        dirs = {os.path.dirname(p) for p in self.lib
                if not any(p.startswith(x + os.sep) for x in self.excluded)}
        for root in self.folders:
            node = add(fol, os.path.basename(root) or root, ("folder", root), dir_icon)
            node.setToolTip(0, root)
            node.setExpanded(True)
            tree = {}
            for d in dirs:
                if d.startswith(root + os.sep):
                    cur = tree
                    for part in os.path.relpath(d, root).split(os.sep):
                        cur = cur.setdefault(part, {})

            def grow(parent, sub, base):
                for name in sorted(sub, key=str.lower):
                    path = os.path.join(base, name)
                    child = add(parent, name, ("folder", path), dir_icon)
                    child.setToolTip(0, path)
                    grow(child, sub[name], path)
            grow(node, tree, root)
        for it in (lib, mus, fol, pl):
            it.setExpanded(True)
        found = self._find_nav(keep)
        if found:
            self.nav.setCurrentItem(found)
        self.nav.blockSignals(False)

    def _find_nav(self, key):
        stack = [self.nav.topLevelItem(i) for i in range(self.nav.topLevelItemCount())]
        best = None
        while stack:
            it = stack.pop(0)
            if it.data(0, ROLE) == key:
                if best is None or it.text(0) == "Todas as músicas":
                    best = it
            stack += [it.child(i) for i in range(it.childCount())]
        return best

    def crumb_for(self, key):
        kind = key[0]
        names = {"all": "Músicas ▸ Todas as músicas", "artists": "Músicas ▸ Artista",
                 "albums": "Músicas ▸ Álbum", "genres": "Músicas ▸ Gênero",
                 "playlists": "Listas", "folders": "Pastas"}
        if kind in names:
            return "Biblioteca ▸ " + names[kind]
        if kind == "artist":
            return f"Biblioteca ▸ Artista ▸ {key[1]}"
        if kind == "genre":
            return f"Biblioteca ▸ Gênero ▸ {key[1]}"
        if kind == "album":
            e = next((e for e in self.lib.values() if e["album_id"] == key[1]), None)
            return "Biblioteca ▸ Álbum ▸ " + (album_name(e) if e else "")
        if kind == "playlist":
            return "Biblioteca ▸ Listas ▸ " + os.path.splitext(os.path.basename(key[1]))[0]
        if kind == "folder":
            root = next((f for f in self.folders if key[1] == f or key[1].startswith(f + os.sep)), None)
            rel = os.path.relpath(key[1], os.path.dirname(root)) if root else key[1]
            return "Biblioteca ▸ Pastas ▸ " + rel.replace(os.sep, " ▸ ")
        return "Biblioteca"

    def set_crumb(self):
        """Biblioteca › Músicas › Todas as músicas: text2, e o lugar atual em SemiBold text."""
        parts = self.crumb_for(self.view_key).split(" ▸ ")
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        sep = f'<span style="color:{THEME["text2"]}">&nbsp;&nbsp;›&nbsp;&nbsp;</span>'
        html = sep.join(f'<span style="color:{THEME["text2"]}">{esc(p)}</span>' for p in parts[:-1])
        cur = f'<span style="color:{THEME["text"]}; font-weight:600">{esc(parts[-1])}</span>'
        self.crumb.setFont(F("crumb"))
        self.crumb.setText((html + sep if html else "") + cur)
        self.crumb.setToolTip(" › ".join(parts))

    def tracks_for(self, key):
        kind, lib = key[0], self.lib.values()
        if kind == "all":
            sel = list(lib)
        elif kind == "artist":
            sel = [e for e in lib if group_artist(e) == key[1]]
        elif kind == "album":
            sel = [e for e in lib if e["album_id"] == key[1]]
        elif kind == "genre":
            sel = [e for e in lib if (e["genre"] or "Sem gênero") == key[1]]
        elif kind == "folder":
            sel = [e for e in lib if e["path"].startswith(key[1] + os.sep)]
        elif kind == "playlist":
            return [self.entry(p) for p in read_m3u(key[1])]   # na ordem da lista
        else:
            sel = []
        return sorted(sel, key=album_order)

    def open_key(self, key):
        if not key:
            return
        self.view_key = tuple(key)
        self.set_crumb()
        cur = self.nav.currentItem()
        if cur is None or cur.data(0, ROLE) != self.view_key:
            found = self._find_nav(self.view_key)
            self.nav.blockSignals(True)
            if found:
                self.nav.setCurrentItem(found)
            else:
                self.nav.clearSelection()
                self.nav.setCurrentItem(None)
            self.nav.blockSignals(False)
        self.refresh_view(scroll_top=True)

    def refresh_view(self, scroll_top=False):
        key = self.view_key
        text = self.search.text().strip().lower()
        if not self.lib and key[0] not in ("playlist", "playlists"):
            self.empty_lbl.setText(
                "A biblioteca está vazia.\n\nAdicione as pastas onde ficam suas músicas "
                "(por exemplo ~/Music ou ~/Downloads). Elas aparecem em Pastas, à esquerda, e as "
                "músicas ficam organizadas por artista, álbum e gênero.\n\n"
                "Para só ouvir uma pasta sem adicionar, use \"Tocar pasta…\"."
                if not self.folders else "Lendo a biblioteca…")
            self.center.setCurrentIndex(2)
            return
        if key[0] in ("artists", "albums", "genres", "playlists", "folders"):
            self.fill_grid(key[0], text)
            self.center.setCurrentIndex(1)
            return
        tracks = self.tracks_for(key)
        pos = list(range(len(tracks)))                 # posição de cada linha na lista salva
        if text:
            keep = [i for i, e in enumerate(tracks) if text in " ".join(
                (e["title"], e["artist"], e["albumartist"], e["album"], e["genre"], e["year"],
                 os.path.basename(e["path"]))).lower()]
            tracks, pos = [tracks[i] for i in keep], keep
        self.view_tracks, self.view_pos = tracks, pos
        bar = self.table.verticalScrollBar().value()
        self.table.fill(tracks, self.album_cover, self.rating, self.cur_path())
        if not scroll_top:
            self.table.verticalScrollBar().setValue(bar)
        else:
            self.table.scrollToTop()
        self.center.setCurrentIndex(0)

    def fill_grid(self, kind, text):
        self.grid.clear()
        groups = []                  # (rótulo, key, música da capa ou None, ícone)
        if kind in ("artists", "albums", "genres"):
            bucket = {}
            for e in sorted(self.lib.values(), key=album_order):
                if kind == "artists":
                    k = group_artist(e)
                elif kind == "albums":
                    k = e["album_id"]
                else:
                    k = e["genre"] or "Sem gênero"
                bucket.setdefault(k, []).append(e)
            for k, es in bucket.items():
                e = es[0]
                n = f"{len(es)} música(s)"
                if kind == "albums":
                    label, key = f"{album_name(e)}\n{group_artist(e)}", ("album", k)
                elif kind == "artists":
                    label, key = f"{k}\n{n}", ("artist", k)
                else:
                    label, key = f"{k}\n{n}", ("genre", k)
                groups.append((label, key, e, None))
            groups.sort(key=lambda g: g[0].lower())
        elif kind == "playlists":
            for fpath in self.playlist_files():
                n = len(read_m3u(fpath))
                groups.append((f"{os.path.splitext(os.path.basename(fpath))[0]}\n{n} música(s)",
                               ("playlist", fpath), None, "playlist"))
        else:
            for root in self.folders:
                n = sum(1 for p in self.lib if p.startswith(root + os.sep))
                groups.append((f"{os.path.basename(root) or root}\n{n} música(s)",
                               ("folder", root), None, "folder"))
        for label, key, aid, std in groups:
            if text and text not in label.lower():
                continue
            it = QListWidgetItem(label)
            it.setData(ROLE, key)
            if aid is not None:
                it.setIcon(QIcon(self.album_cover(aid, 150, 12)))
            else:
                it.setIcon(ph(std, color=C("text2"), sizes=(96, 150)))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.grid.addItem(it)

    def paths_for_key(self, key):
        if key[0] in ("artists", "albums", "genres", "all"):
            return [e["path"] for e in sorted(self.lib.values(), key=album_order)]
        if key[0] == "folders":
            return [e["path"] for e in sorted(self.lib.values(), key=album_order)
                    if any(e["path"].startswith(f + os.sep) for f in self.folders)]
        if key[0] == "playlists":
            return []
        return [e["path"] for e in self.tracks_for(key)]

    # ================================================================ menus
    def _menu_play(self, menu, paths_fn):
        menu.addAction(ph("play", fill=True), "Tocar", lambda: self.queue_replace(paths_fn()))
        menu.addAction(ph("queue"), "Tocar a seguir", lambda: self.queue_add(paths_fn(), self.next_pos()))
        menu.addAction(ph("list-plus"), "Adicionar à lista atual", lambda: self.queue_add(paths_fn()))
        menu.addAction(ph("shuffle"), "Tocar em ordem aleatória",
                       lambda: self.queue_replace(paths_fn(), shuffle=True))
        self._menu_lists(menu, paths_fn)

    def _menu_lists(self, menu, paths_fn, skip=None):
        sub = menu.addMenu(ph("playlist"), "Adicionar à lista")
        for fpath in self.playlist_files():
            if fpath == skip:
                continue
            act = sub.addAction(ph("queue"), os.path.splitext(os.path.basename(fpath))[0])
            act.triggered.connect(lambda _c=False, f=fpath: self.add_to_playlist(f, paths_fn()))
        if sub.actions():
            sub.addSeparator()
        sub.addAction(ph("plus"), "Nova lista…", lambda: self.new_playlist(paths_fn()))

    def nav_menu(self, pos):
        it = self.nav.itemAt(pos)
        if not it:
            return
        key = it.data(0, ROLE)
        m = QMenu(self)
        if key[0] != "playlists":
            self._menu_play(m, lambda: self.paths_for_key(key))
        if key[0] == "folder":
            m.addSeparator()
            m.addAction(ph("folder-open"), "Abrir no gerenciador de arquivos",
                        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(key[1])))
            m.addAction(ph("trash"), "Excluir da biblioteca…", lambda: self.remove_folder(key[1]))
        if key[0] in ("folders", "all"):
            m.addSeparator()
            m.addAction(ph("folder-plus"), "Adicionar pasta à biblioteca…", self.add_library_folder)
        if key[0] == "playlists":
            m.addAction(ph("plus"), "Nova lista vazia…", lambda: self.new_playlist([]))
        if key[0] == "playlist":
            m.addSeparator()
            m.addAction("Renomear lista…", lambda: self.rename_playlist(key[1]))
            m.addAction(ph("trash"), "Excluir lista…", lambda: self.delete_playlist(key[1]))
        m.exec(self.nav.viewport().mapToGlobal(pos))

    def grid_menu(self, pos):
        it = self.grid.itemAt(pos)
        if not it:
            return
        key = it.data(ROLE)
        m = QMenu(self)
        self._menu_play(m, lambda: self.paths_for_key(key))
        if key[0] == "playlist":
            m.addSeparator()
            m.addAction("Renomear lista…", lambda: self.rename_playlist(key[1]))
            m.addAction(ph("trash"), "Excluir lista…", lambda: self.delete_playlist(key[1]))
        m.exec(self.grid.viewport().mapToGlobal(pos))

    def table_menu(self, pos):
        paths = self.table.selected_paths()
        if not paths:
            return
        m = QMenu(self)
        self._menu_play(m, lambda: paths)
        if self.view_key[0] == "playlist":
            lst = self.view_key[1]
            rows = self.table.selected_rows()
            m.addSeparator()
            m.addAction(ph("x"), "Tirar desta lista", lambda: self.remove_from_playlist(lst, rows))
            m.addAction("Subir na lista", lambda: self.move_in_playlist(lst, rows, -1))
            m.addAction("Descer na lista", lambda: self.move_in_playlist(lst, rows, +1))
        rate = m.addMenu(ph("star"), "Avaliar")
        for n in range(6):
            act = QAction("Sem nota" if n == 0 else "★" * n, rate)
            act.triggered.connect(lambda _c=False, n=n: [self.set_rating(p, n) for p in paths])
            rate.addAction(act)
        m.addSeparator()
        m.addAction(ph("folder-open"), "Abrir pasta do arquivo",
                    lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(paths[0]))))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def queue_menu(self, pos):
        it = self.queue.itemAt(pos)
        m = QMenu(self)
        if it:
            sel = [x.data(0, ROLE) for x in self.queue.selectedItems()] or [it.data(0, ROLE)]
            m.addAction(ph("play", fill=True), "Tocar", lambda: self.play_item(it))
            m.addAction(ph("x"), "Tirar da lista atual", self.remove_selected_from_queue)
            self._menu_lists(m, lambda: sel)
            m.addAction(ph("folder-open"), "Abrir pasta do arquivo", lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.dirname(it.data(0, ROLE)))))
            m.addSeparator()
        m.addAction(ph("shuffle"), "Embaralhar a lista", self.shuffle_queue)
        m.addAction(ph("floppy-disk"), "Salvar lista…", self.save_queue_dialog)
        m.addAction(ph("trash"), "Limpar lista", self.clear_queue)
        m.exec(self.queue.viewport().mapToGlobal(pos))

    # ================================================================ lista atual
    def cur_path(self):
        if self.cur_item is not None and not sip.isdeleted(self.cur_item):
            return self.cur_item.data(0, ROLE)
        return None

    def _make_item(self, path):
        e = self.entry(path)
        who = f" - {e['artist']}" if e["artist"] else ""
        it = QTreeWidgetItem([e["title"] + who, fmt(e["dur"]) if e["dur"] else ""])
        it.setData(0, ROLE, path)
        it.setToolTip(0, path)
        it.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled |
                    Qt.ItemFlag.ItemIsDragEnabled)     # sem DropEnabled: não vira "pasta"
        return it

    def expand_paths(self, paths):
        out = []
        for p in paths:
            if os.path.isdir(p):
                found = collect([p])
                out += sorted(found, key=lambda f: album_order(self.entry(f)))
            elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in EXTS:
                out.append(os.path.abspath(p))
        return out

    def queue_add(self, paths, at=None, play=False):
        paths = self.expand_paths(paths)
        if not paths:
            return
        at = self.queue.topLevelItemCount() if at is None else at
        items = [self._make_item(p) for p in paths]
        self.queue.insertTopLevelItems(at, items)
        self.queue_changed()
        if play:
            self.play_item(items[0])

    def queue_replace(self, paths, start=None, shuffle=False):
        paths = self.expand_paths(paths)
        if not paths:
            return
        self.queue.clear()
        self.cur_item, self.history = None, []
        self.shuffle_done.clear()
        if shuffle:
            random.shuffle(paths)
        self.queue_add(paths)
        items = self.queue.items()
        first = next((it for it in items if it.data(0, ROLE) == start), None)
        if first is None:
            first = random.choice(items) if self.btn_shuffle.isChecked() and not shuffle else items[0]
        self.play_item(first)

    def next_pos(self):
        i = self.queue.indexOfTopLevelItem(self.cur_item) if self.cur_path() else -1
        return i + 1 if i >= 0 else self.queue.topLevelItemCount()

    def remove_selected_from_queue(self):
        for it in self.queue.selectedItems():
            if it is self.cur_item:
                self._next_hint = self.queue.indexOfTopLevelItem(it)
                self.cur_item = None
            self.queue.takeTopLevelItem(self.queue.indexOfTopLevelItem(it))
        self.queue_changed()

    def clear_queue(self):
        self.stop()
        self.queue.clear()
        self.cur_item, self.history = None, []
        self.mpris_notify(metadata=True)
        self.shuffle_done.clear()
        self.show_now(None)
        self.queue_changed()

    def shuffle_queue(self):
        items = [self.queue.takeTopLevelItem(0) for _ in range(self.queue.topLevelItemCount())]
        random.shuffle(items)
        if self.cur_item in items:                 # a que está tocando vai para o topo
            items.remove(self.cur_item)
            items.insert(0, self.cur_item)
        self.queue.addTopLevelItems(items)
        self.queue_changed()

    def queue_changed(self):
        self.mpris_notify()
        items = self.queue.items()
        total = sum(self.entry(it.data(0, ROLE))["dur"] for it in items)
        self.q_foot.setText(f"{len(items)} música(s), {fmt_total(total)}" if items else "Lista vazia")
        self.mark_queue()

    def refresh_queue_texts(self):
        for it in self.queue.items():
            e = self.entry(it.data(0, ROLE))
            who = f" - {e['artist']}" if e["artist"] else ""
            it.setText(0, e["title"] + who)
            it.setText(1, fmt(e["dur"]) if e["dur"] else "")
        self.queue_changed()
        if self.cur_path():
            self.show_now(self.entry(self.cur_path()))

    def mark_queue(self):
        self.queue.playing = self.cur_item if self.cur_path() else None
        self.queue.viewport().update()

    def save_queue_dialog(self):
        if not self.queue.topLevelItemCount():
            QMessageBox.information(self, "Salvar lista", "A lista atual está vazia.")
            return
        name, ok = QInputDialog.getText(self, "Salvar lista", "Nome da lista:",
                                        text=self.__dict__.get("_last_list", ""))
        name = re.sub(r'[\\/:*?"<>|]', "", name or "").strip()
        if not ok or not name:
            return
        path = os.path.join(LISTS_DIR, name + ".m3u8")
        if os.path.exists(path) and QMessageBox.question(
                self, "Salvar lista", f"Já existe uma lista \"{name}\". Substituir?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.save_queue(path)

    def save_queue(self, path):
        write_m3u(path, [self.entry(it.data(0, ROLE)) for it in self.queue.items()])
        self.build_nav()
        if self.view_key[0] in ("playlists", "playlist"):
            self.refresh_view()
        self.statusBar().showMessage(f"Lista salva: {path}", 8000)

    def list_name_dialog(self, title, label, current=""):
        name, ok = QInputDialog.getText(self, title, label, text=current)
        name = re.sub(r'[\\/:*?"<>|]', "", name or "").strip()
        return name if ok and name else None

    def _list_changed(self, path, msg):
        self.build_nav()
        if self.view_key == ("playlist", path) or self.view_key[0] == "playlists":
            self.refresh_view()
        self.statusBar().showMessage(msg, 8000)

    def add_to_playlist(self, path, paths):
        paths = self.expand_paths(paths)
        if not paths:
            return
        old = read_m3u(path)
        have = set(old)
        new = [p for p in paths if p not in have]
        nome = os.path.splitext(os.path.basename(path))[0]
        if new:
            write_m3u(path, [self.entry(p) for p in old + new])
        msg = f"{len(new)} música(s) adicionada(s) à lista \"{nome}\"."
        if len(new) < len(paths):
            msg += f" {len(paths) - len(new)} já estava(m) nela."
        self._list_changed(path, msg)

    def new_playlist(self, paths):
        name = self.list_name_dialog("Nova lista", "Nome da nova lista:")
        if not name:
            return
        path = os.path.join(LISTS_DIR, name + ".m3u8")
        if os.path.exists(path):
            if QMessageBox.question(self, "Nova lista", f"Já existe uma lista \"{name}\". "
                                    "Adicionar as músicas a ela?") == QMessageBox.StandardButton.Yes:
                self.add_to_playlist(path, paths)
            return
        paths = self.expand_paths(paths)
        write_m3u(path, [self.entry(p) for p in paths])
        self._list_changed(path, f"Lista \"{name}\" criada com {len(paths)} música(s).")

    def remove_from_playlist(self, path, rows):
        old = read_m3u(path)
        gone = {self.view_pos[r] for r in rows if r < len(self.view_pos)}
        write_m3u(path, [self.entry(p) for i, p in enumerate(old) if i not in gone])
        self._list_changed(path, f"{len(gone)} música(s) tirada(s) da lista. Os arquivos continuam no disco.")

    def move_in_playlist(self, path, rows, delta):
        items = read_m3u(path)
        sel = sorted(self.view_pos[r] for r in rows if r < len(self.view_pos))
        if not sel or (delta < 0 and sel[0] == 0) or (delta > 0 and sel[-1] == len(items) - 1):
            return
        for i in (sel if delta < 0 else reversed(sel)):
            items[i], items[i + delta] = items[i + delta], items[i]
        write_m3u(path, [self.entry(p) for p in items])
        self._list_changed(path, "Ordem da lista atualizada.")
        moved = {i + delta for i in sel}               # mantém as mesmas músicas selecionadas
        order = sorted(self.table.row_path)
        self.table.clearSelection()
        flags = (self.table.selectionModel().SelectionFlag.Select |
                 self.table.selectionModel().SelectionFlag.Rows)
        for k, r in enumerate(order):
            if k < len(self.view_pos) and self.view_pos[k] in moved:
                self.table.selectionModel().select(self.table.model().index(r, COL_TITLE), flags)

    def rename_playlist(self, path):
        old = os.path.splitext(os.path.basename(path))[0]
        name = self.list_name_dialog("Renomear lista", "Novo nome:", old)
        if not name or name == old:
            return
        new = os.path.join(LISTS_DIR, name + ".m3u8")
        if os.path.exists(new):
            QMessageBox.warning(self, "Renomear lista", f"Já existe uma lista \"{name}\".")
            return
        os.rename(path, new)
        if self.view_key == ("playlist", path):
            self.view_key = ("playlist", new)
            self.set_crumb()
        self._list_changed(new, f"Lista renomeada para \"{name}\".")

    def on_nav_drop(self, key, paths):
        if key[0] == "playlist":
            self.add_to_playlist(key[1], paths)
        else:
            self.new_playlist(paths)

    def delete_playlist(self, path):
        nome = os.path.splitext(os.path.basename(path))[0]
        if QMessageBox.question(self, "Excluir lista",
                                f"Excluir a lista \"{nome}\"?\n\nAs músicas continuam no disco; "
                                "só a lista some.") != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(path)
        except OSError as err:
            QMessageBox.warning(self, "Excluir lista", str(err))
        if self.view_key == ("playlist", path):
            self.view_key = ("playlists",)
        self.build_nav()
        self.open_key(self.view_key)

    def restore_queue(self):
        data = _read_json(QUEUE_FILE, {})
        paths = [p for p in data.get("caminhos", []) if os.path.isfile(p)]
        if not paths:
            self.queue_changed()
            return
        self.queue.addTopLevelItems([self._make_item(p) for p in paths])
        cur = data.get("atual")
        if cur in paths:
            self.cur_item = self.queue.topLevelItem(paths.index(cur))
            self.player.setSource(QUrl.fromLocalFile(cur))     # pronta para tocar, sem tocar
            self.show_now(self.entry(cur))
        self.queue_changed()

    def save_state(self):
        _write_json(QUEUE_FILE, {"caminhos": [it.data(0, ROLE) for it in self.queue.items()],
                                 "atual": self.cur_path()})

    # ================================================================ tocar
    def on_table_double(self, row, _col):
        self.play_from_table(row)

    def play_from_table(self, row):
        path = self.table.row_path.get(row)
        if path:
            if self.view_key[0] == "playlist":
                self._last_list = os.path.splitext(os.path.basename(self.view_key[1]))[0]
            self.queue_replace(self.table.paths_in_order(), start=path)

    def play_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "Tocar pasta", self.settings.value("ultima") or
                                             os.path.expanduser("~"))
        if d:
            self.settings.setValue("ultima", d)
            self.queue_replace([d])

    def play_files_dialog(self):
        exts = " ".join("*" + e for e in sorted(EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, "Tocar arquivos", self.settings.value("ultima") or
                                                os.path.expanduser("~"), f"Músicas ({exts})")
        if files:
            self.settings.setValue("ultima", os.path.dirname(files[0]))
            self.queue_replace(files)

    def play_item(self, it, add_history=True):
        if it is None or sip.isdeleted(it):
            return
        if add_history and self.cur_path():
            self.history.append(self.cur_item)
        self.cur_item = it
        self.shuffle_done.add(id(it))
        path = it.data(0, ROLE)
        self._serial += 1
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        self.show_now(self.entry(path))
        self.mark_queue()
        self.table.mark_playing(path)
        self.queue.scrollToItem(it)
        self.mpris_notify(metadata=True)

    def space(self):
        if not self.search.hasFocus():
            self.toggle()

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self.cur_path():
            self.player.play()
        elif self.queue.topLevelItemCount():
            items = self.queue.items()
            self.play_item(random.choice(items) if self.btn_shuffle.isChecked() else items[0])
        elif self.table.row_path:
            sel = self.table.selected_paths()
            self.queue_replace(self.table.paths_in_order(), start=sel[0] if sel else None)

    def stop(self):
        self.player.stop()

    def next_item(self):
        items = self.queue.items()
        if not items:
            return None
        cur = self.cur_item if self.cur_path() else None
        if self.btn_shuffle.isChecked():
            options = [it for it in items if id(it) not in self.shuffle_done and it is not cur]
            if not options and self.repeat == 1:
                self.shuffle_done.clear()
                options = [it for it in items if it is not cur] or items
            return random.choice(options) if options else None
        if cur is not None:
            i = self.queue.indexOfTopLevelItem(cur) + 1
        else:
            i = getattr(self, "_next_hint", 0)
        self._next_hint = 0
        if i < len(items):
            return items[i]
        return items[0] if self.repeat == 1 else None

    def next(self):
        it = self.next_item()
        if it is None:
            self.stop()
            self.statusBar().showMessage("Fim da lista.", 6000)
        else:
            self.play_item(it)

    def prev(self):
        if self.player.position() > 3000 or not self.cur_path():
            self.seek_to(0)
            return
        while self.history:
            it = self.history.pop()
            if not sip.isdeleted(it) and self.queue.indexOfTopLevelItem(it) >= 0:
                self.play_item(it, add_history=False)
                return
        i = self.queue.indexOfTopLevelItem(self.cur_item)
        if i > 0:
            self.play_item(self.queue.topLevelItem(i - 1), add_history=False)
        else:
            self.seek_to(0)

    def jump(self, seconds):
        if self.cur_path():
            self.seek_to(max(0, self.player.position() + seconds * 1000))

    def on_shuffle(self, on):
        self.shuffle_done = {id(self.cur_item)} if self.cur_path() else set()
        self.settings.setValue("aleatorio", "true" if on else "false")
        self.mode_icons()
        self.mpris_notify(Shuffle=bool(on))

    def mode_icons(self):
        """Aleatório/repetir ligados: fundo tint (QSS :checked) e ícone no destaque."""
        on, off = C("accent"), C("text")
        sh = self.btn_shuffle.isChecked()
        self.btn_shuffle.setIcon(ph("shuffle", color=on if sh else off))
        self.btn_shuffle.setToolTip("Aleatório: " + ("ligado" if sh else "desligado"))
        name = "repeat-once" if self.repeat == 2 else "repeat"
        self.btn_repeat.setIcon(ph(name, color=on if self.repeat else off))
        self.btn_repeat.setChecked(bool(self.repeat))
        self.btn_repeat.setToolTip(REPEAT[self.repeat] + " (clique para mudar)")

    def cycle_repeat(self):
        self.repeat = (self.repeat + 1) % 3
        self.mode_icons()
        self.settings.setValue("repetir", self.repeat)
        self.mpris_notify(LoopStatus=LOOP[self.repeat])

    def on_volume(self, v):
        self.audio.setVolume(v / 100)
        self.vol_lbl.setText(f"{v}%")
        self.mpris_notify(Volume=0.0 if self.btn_mute.isChecked() else v / 100)

    def on_mute(self, on):
        self.audio.setMuted(on)
        self.mpris_notify(Volume=0.0 if on else self.volume.value() / 100)
        self.btn_mute.setIcon(ph("speaker-x" if on else "speaker-high", color=C("text")))

    # ================================================================ sinais do player
    def on_position(self, ms):
        if not self._dragging:
            self.seek.setValue(ms)
            if ms // 1000 != self._pos_shown:          # o texto só muda uma vez por segundo
                self._pos_shown = ms // 1000
                self.lbl_pos.setText(fmt(ms / 1000))

    def on_duration(self, ms):
        self.seek.setRange(0, ms)
        self.lbl_dur.setText(fmt(ms / 1000))
        if ms:
            self.mpris_notify(metadata=True)          # duração exata

    def on_seek_release(self):
        self._dragging = False
        self.seek_to(self.seek.value())

    def on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._errors = 0
            if self.repeat == 2:
                self.seek_to(0)
                self.player.play()
            else:
                self.next()
        elif status == QMediaPlayer.MediaStatus.BufferedMedia:
            self._errors = 0

    def on_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.btn_play.setIcon(ph("pause" if playing else "play", fill=True, color=C("onAccent")))
        self.mpris_notify()

    # ---------------------------------------------------------------- MPRIS
    def mpris_status(self):
        st = self.player.playbackState()
        if st == QMediaPlayer.PlaybackState.PlayingState:
            return "Playing"
        if st == QMediaPlayer.PlaybackState.PausedState:
            return "Paused"
        return "Stopped"

    def mpris_trackid(self):
        if not self.cur_path():
            return "/org/mpris/MediaPlayer2/TrackList/NoTrack"
        return f"/org/reprodutor/faixa/{self._serial}"

    def mpris_art(self, e):
        """Capa em tamanho cheio para o Plasma (a miniatura da biblioteca é pequena)."""
        if self._art and self._art[0] == e["path"]:
            return self._art[1]
        url = ""
        try:
            data = read_tags(e["path"], want_cover=True)[2]
        except Exception:
            data = None
        if data:
            ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            os.makedirs(CACHE_DIR, exist_ok=True)
            for old in os.listdir(CACHE_DIR):
                if old.startswith("tocando-"):
                    try:
                        os.remove(os.path.join(CACHE_DIR, old))
                    except OSError:
                        pass
            f = os.path.join(CACHE_DIR, f"tocando-{self._serial}{ext}")   # nome novo: o Plasma recarrega
            with open(f, "wb") as fh:
                fh.write(data)
            url = QUrl.fromLocalFile(f).toString()
        else:
            fn = self.cover_file(e)
            if fn and os.path.exists(os.path.join(COVER_DIR, fn)):
                url = QUrl.fromLocalFile(os.path.join(COVER_DIR, fn)).toString()
        self._art = (e["path"], url)
        return url

    def mpris_metadata(self):
        md = {"mpris:trackid": QDBusObjectPath(self.mpris_trackid())}
        path = self.cur_path()
        if not path:
            return md
        e = self.entry(path)
        md["xesam:title"] = e["title"]
        md["xesam:url"] = QUrl.fromLocalFile(path).toString()
        if e["artist"]:
            md["xesam:artist"] = _as([e["artist"]])
        if e["album"]:
            md["xesam:album"] = e["album"]
        if e["albumartist"]:
            md["xesam:albumArtist"] = _as([e["albumartist"]])
        if e["genre"]:
            md["xesam:genre"] = _as([e["genre"]])
        if e["track"]:
            md["xesam:trackNumber"] = int(e["track"])
        if e["disc"]:
            md["xesam:discNumber"] = int(e["disc"])
        if e["year"]:
            md["xesam:contentCreated"] = e["year"]
        n = self.rating(e)
        if n:
            md["xesam:userRating"] = n / 5
        dur_ms = self.player.duration() or int(e["dur"] * 1000)
        if dur_ms:
            md["mpris:length"] = _x(dur_ms * 1000)
        art = self.mpris_art(e)
        if art:
            md["mpris:artUrl"] = art
        return md

    def mpris_notify(self, metadata=False, **extra):
        if not self.__dict__.get("mpris"):
            return
        props = {"PlaybackStatus": self.mpris_status(),
                 "CanGoNext": self.queue.topLevelItemCount() > 0,
                 "CanGoPrevious": self.queue.topLevelItemCount() > 0,
                 "CanPlay": self.queue.topLevelItemCount() > 0 or bool(self.table.row_path),
                 "CanPause": self.cur_path() is not None,
                 "CanSeek": self.cur_path() is not None}
        if metadata:
            props["Metadata"] = self.mpris_metadata()
        props.update(extra)
        self.mpris.changed(props)

    def seek_to(self, ms):
        self.player.setPosition(int(ms))
        if self.__dict__.get("mpris"):
            self.mpris.player.Seeked.emit(int(ms) * 1000)

    def on_error(self, _err, msg):
        if not self.cur_path():
            return
        self.statusBar().showMessage(f"Não consegui tocar {os.path.basename(self.cur_path())}: {msg}",
                                     10000)
        self._errors += 1
        if self._errors < self.queue.topLevelItemCount():   # pula, sem laço se nada toca
            self.next()

    # ================================================================ tela
    def show_now(self, e):
        if e is None:
            self.np_title.setText("Nada tocando")
            self.np_info.setText("Dê dois cliques numa música, ou arraste músicas e pastas para cá.")
            self.mini_title.setText("")
            self.mini_artist.setText("")
            self.setWindowTitle("Linux Music Player")
            self.np_cover.setPixmap(self.cover_of(None, 84, 12))
            self.mini_cover.setPixmap(self.cover_of(None, 44, 8))
            return
        self.np_title.setText(e["title"])
        self.np_info.setText("\n".join(x for x in (e["artist"], album_name(e) if e["album"] else "") if x))
        self.mini_title.setText(e["title"])
        self.mini_artist.setText(e["artist"])
        self.mini_title.setToolTip(e["title"])
        self.setWindowTitle(f"{e['title']} — {e['artist']}" if e["artist"] else e["title"])
        self.np_cover.setPixmap(self.cover_of(e, 84, 12))
        self.mini_cover.setPixmap(self.cover_of(e, 44, 8))

    # arrastar da área de trabalho / gerenciador de arquivos para fora da lista
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls() and ev.source() is None:
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        self.queue_add(paths, play=not self.cur_path())

    def closeEvent(self, ev):
        self.settings.setValue("volume", self.volume.value())
        self.settings.setValue("divisao-cartoes", self.split.saveState())
        self.save_state()
        self.player.stop()
        if self.scanner is not None and self.scanner.isRunning():
            self.scanner.wait(5000)
        ev.accept()


# ================================================================ atalho no menu (AppImage)
def _apps_dirs():
    home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    dirs = [home] + (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    return [os.path.join(d, "applications") for d in dirs if d], home


def desktop_name():
    """Nome do atalho instalado que abre este AppImage (Gear Lever, AppImageLauncher ou o nosso).

    A janela se apresenta com esse nome; assim, fixar na barra de tarefas usa o atalho
    instalado, e não o de dentro do AppImage (que some quando o programa fecha)."""
    appimage = os.environ.get("APPIMAGE")
    if not appimage:
        # instalado pelo .deb: o atalho do sistema é linux-music-player.desktop
        if os.path.abspath(__file__).startswith("/usr/share/linux-music-player/"):
            return "linux-music-player"
        return APP
    alvos = {appimage, os.path.realpath(appimage)}
    for d in _apps_dirs()[0]:
        try:
            nomes = sorted(n for n in os.listdir(d) if n.endswith(".desktop"))
        except OSError:
            continue
        for n in nomes:
            try:
                with open(os.path.join(d, n), encoding="utf-8", errors="replace") as fh:
                    if any(l.startswith(("Exec=", "TryExec=")) and any(a in l for a in alvos) for l in fh):
                        return n[:-len(".desktop")]
            except OSError:
                pass
    return APP


def install_shortcut(icon_file):
    appimage = os.environ.get("APPIMAGE")
    if not appimage:
        print("Rode esta opção a partir do arquivo .AppImage.")
        return 1
    _, home = _apps_dirs()
    mine = os.path.join(home, "applications", APP + ".desktop")
    cur = desktop_name()
    if cur != APP:
        print(f"Já existe um atalho para este AppImage ({cur}.desktop). Nada foi criado.")
        return 0
    real = os.path.realpath(appimage)
    q = real
    for c in ("\\", '"', "`", "$"):
        q = q.replace(c, "\\" + c)
    exe = f'"{q}"'.replace("\\", "\\\\")
    icons = os.path.join(home, "icons", "hicolor", "256x256", "apps")
    os.makedirs(icons, exist_ok=True)
    os.makedirs(os.path.dirname(mine), exist_ok=True)
    with open(icon_file, "rb") as src, open(os.path.join(icons, APP + ".png"), "wb") as dst:
        dst.write(src.read())
    with open(mine, "w", encoding="utf-8") as fh:
        fh.write(f"""[Desktop Entry]
Type=Application
Name=Linux Music Player
GenericName=Tocador de músicas
Comment=Toca músicas com biblioteca, capas e listas
Exec={exe} %F
TryExec={real}
Icon={APP}
Terminal=false
Categories=AudioVideo;Audio;Player;
Keywords=música;mp3;player;tocar;
MimeType=audio/mpeg;audio/flac;audio/ogg;audio/x-opus+ogg;audio/mp4;audio/x-wav;audio/x-m4a;
StartupWMClass={APP}
""")
    _refresh_menu(home)
    print(f"Atalho criado no menu de aplicativos:\n  {mine}\nEle abre: {real}\n"
          "Se você mover ou renomear o .AppImage, rode --instalar-atalho de novo.")
    return 0


def remove_shortcut():
    _, home = _apps_dirs()
    files = [os.path.join(home, "applications", APP + ".desktop"),
             os.path.join(home, "icons", "hicolor", "256x256", "apps", APP + ".png")]
    gone = [f for f in files if os.path.exists(f)]
    for f in gone:
        os.remove(f)
    _refresh_menu(home)
    print("Atalho removido." if gone else "Não havia atalho criado por este programa.")
    return 0


def _refresh_menu(home):
    import shutil
    import subprocess
    for cmd in ("kbuildsycoca6", "kbuildsycoca5", "update-desktop-database"):
        if shutil.which(cmd):
            args = [cmd] if cmd.startswith("kbuild") else [cmd, os.path.join(home, "applications")]
            subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def app_icon():
    """O ícone do programa: o do AppImage ou o .png ao lado deste arquivo."""
    for path in (os.environ.get("REPRODUTOR_ICONE"),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "linux-music-player.png")):
        if path and os.path.exists(path):
            return path
    return ""


def main():
    if sys.argv[1:2] in (["--versao"], ["--version"]):
        print(f"Linux Music Player {__version__}")
        return
    if sys.argv[1:2] == ["--instalar-atalho"]:
        sys.exit(install_shortcut(sys.argv[2] if len(sys.argv) > 2 else app_icon()))
    if sys.argv[1:2] == ["--remover-atalho"]:
        sys.exit(remove_shortcut())
    app = QApplication(sys.argv)
    app.setApplicationName("Linux Music Player")
    app.setDesktopFileName(desktop_name())    # casa com o atalho instalado no menu
    load_fonts()                              # a Inter, antes das janelas, em todos os temas
    icon = app_icon()
    if icon:
        app.setWindowIcon(QIcon(icon))
    w = Window()
    w.show()
    if sys.argv[1:]:
        w.queue_replace(sys.argv[1:])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

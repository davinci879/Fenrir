# -*- coding: utf-8 -*-
"""图片支撑模块：图片入库、尺寸换算、浮动图片控件（浮于文字上方 / 衬于文字下方 / 四周型环绕）。

设计取舍（PyQt 的 QTextDocument 没有 Word 那套浮动版式）
- 嵌入型：真正的文档内容，用 QTextImageFormat 内联插入，随文字流动、可随 HTML 存档；
- 四周型环绕（左/右）：把图片放进一个「浮动帧」(QTextFrame + FloatLeft/FloatRight)，
  正文文字绕其矩形排布，效果等同 Word 的「四周型」；图片仍是文档内容，随 HTML 存档；
- 浮于文字上方：不进入文字流，用子控件贴在 viewport 上，可拖动、可缩放、压住正文；
- 衬于文字下方：同样不进入文字流，改为在 viewport 的 Paint 事件里**先画图、后让
  QTextEdit 画文字**，于是文字真的压在图片上面，效果与 Word 一致。

浮动图（above/behind）的位置以「文档坐标」存储（x 像素、y 为文档像素），滚动时按滚动量
换算，所以滚动、切文档都不会跑位。浮动图不参与文字流，删除要用右键菜单，不能用退格。
四周型环绕是文档内容，删除与普通图片一样（选中后退格），空帧会被自动清理。
"""
import os
import shutil
import uuid

from PyQt5.QtCore import Qt, QRect, QUrl
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTextDocument
from PyQt5.QtWidgets import QMenu, QInputDialog, QWidget

# image_support.py 位于 src/，项目根目录是其父目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, 'data', 'images')

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff')
IMAGE_FILTER = '图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff);;所有文件 (*.*)'

# 环绕方式：界面文字 <-> 内部键
# 新增「四周型环绕（左/右）」：用浮动帧让正文文字绕图片矩形排布（类 Word 四周型）。
WRAP_MODES = ('嵌入型', '四周型环绕（左）', '四周型环绕（右）',
             '浮于文字上方', '衬于文字下方')
MODE_KEYS = {'嵌入型': 'inline',
             '四周型环绕（左）': 'wrap_left',
             '四周型环绕（右）': 'wrap_right',
             '浮于文字上方': 'above',
             '衬于文字下方': 'behind'}
MODE_NAMES = dict((v, k) for k, v in MODE_KEYS.items())


def is_wrap_mode(mode):
    """是否是「四周型环绕」（文字绕图）模式。"""
    return mode in ('wrap_left', 'wrap_right')

# 入库时先缩到这个宽度，避免 4K 截图把排版拖慢
MAX_IMPORT_W = 1600

_HANDLE = 14          # 右下角缩放手柄边长


def ensure_dir():
    os.makedirs(IMAGE_DIR, exist_ok=True)
    return IMAGE_DIR


def image_uri(path):
    """本地路径 -> QTextDocument 可识别的 file:/// 地址。"""
    return QUrl.fromLocalFile(os.path.abspath(path)).toString()


def _new_name(ext):
    return os.path.join(ensure_dir(), '%s%s' % (uuid.uuid4().hex[:16], ext))


def import_image(src_path):
    """把外部图片复制进 data/images（过大先缩小），返回 (新路径, QImage)。"""
    img = QImage(src_path)
    if img.isNull():
        raise IOError('无法读取图片：%s' % src_path)
    if img.width() > MAX_IMPORT_W:
        img = img.scaledToWidth(MAX_IMPORT_W, Qt.SmoothTransformation)
        dst = _new_name('.png')
        img.save(dst, 'PNG')
        return dst, img
    ext = os.path.splitext(src_path)[1].lower()
    if ext not in IMAGE_EXTS:
        ext = '.png'
    dst = _new_name(ext)
    try:
        shutil.copyfile(src_path, dst)
    except Exception:
        img.save(dst)
    return dst, img


def save_image_object(img):
    """把内存里的 QImage（剪贴板截图等）落盘，返回路径。"""
    dst = _new_name('.png')
    img.save(dst, 'PNG')
    return dst


def fit_size(w, h, max_w, max_h=None):
    """等比缩小到不超过 max_w（可选 max_h），不放大小图。"""
    w, h = max(1, int(w)), max(1, int(h))
    max_w = max(24, int(max_w))
    scale = 1.0
    if w > max_w:
        scale = max_w / float(w)
    if max_h and h * scale > max_h:
        scale = min(scale, max_h / float(h))
    return max(1, int(w * scale)), max(1, int(h * scale))


def load_pixmap(editor, uri):
    """按 uri 取 QPixmap：先读本地文件，再退回文档资源表。"""
    path = QUrl(uri).toLocalFile()
    if path and os.path.isfile(path):
        pix = QPixmap(path)
        if not pix.isNull():
            return pix
    try:
        res = editor.document().resource(QTextDocument.ImageResource, QUrl(uri))
    except Exception:
        res = None
    if isinstance(res, QPixmap):
        return res
    if isinstance(res, QImage):
        return QPixmap.fromImage(res)
    return QPixmap()


class FloatImage(QWidget):
    """浮于文字上方的图片控件：拖动移动，右下角拖动缩放，右键切换环绕/删除。"""

    def __init__(self, editor, info):
        super().__init__(editor.viewport())
        self.editor = editor
        self.info = info                      # {'uri','x','y','w','h','mode'}
        self._pix = load_pixmap(editor, info.get('uri', ''))
        self._mode = None                     # 'move' / 'resize'
        self._press = None
        self._hover = False
        self.setMouseTracking(True)
        self.setCursor(Qt.SizeAllCursor)
        self.setToolTip('拖动移动图片；右下角拖动缩放；右键切换环绕方式或删除')
        self._apply_geometry()

    # ---- 外观 ----
    def _apply_geometry(self):
        r = self.editor._float_rect(self.info)
        self.setGeometry(r)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        if not p.isActive():
            return
        r = self.rect().adjusted(0, 0, -1, -1)
        if not self._pix.isNull():
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.drawPixmap(r, self._pix)
        else:
            p.fillRect(r, QColor('#243240'))
            p.setPen(QPen(QColor('#7d8894')))
            p.drawText(r, Qt.AlignCenter, '图片丢失\n' + os.path.basename(
                QUrl(self.info.get('uri', '')).toLocalFile()))
        p.setPen(QPen(QColor('#4a9eff' if (self._hover or self._mode) else '#5b6b7c'), 1))
        p.drawRect(r)
        # 右下角缩放手柄
        h = _HANDLE
        hx, hy = self.width() - h, self.height() - h
        if self.width() > h * 2 and self.height() > h * 2:
            p.fillRect(QRect(hx, hy, h, h), QColor(74, 158, 255, 190))
            p.setPen(QPen(QColor('#ffffff'), 1))
            for i in (1, 2):
                p.drawLine(hx + 3, hy + h - 3 - i * 4, hx + h - 3 - i * 4, hy + 3)

    # ---- 鼠标 ----
    def _in_handle(self, pos):
        h = _HANDLE
        return (self.width() - h <= pos.x() <= self.width()
                and self.height() - h <= pos.y() <= self.height())

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        self._mode = 'resize' if self._in_handle(event.pos()) else 'move'
        self._press = (event.globalPos(), self.geometry())
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._mode:
            self.setCursor(Qt.SizeFDiagCursor if self._in_handle(event.pos())
                           else Qt.SizeAllCursor)
            return super().mouseMoveEvent(event)
        delta = event.globalPos() - self._press[0]
        x0, y0, w0, h0 = (self._press[1].x(), self._press[1].y(),
                          self._press[1].width(), self._press[1].height())
        if self._mode == 'move':
            self.editor._move_float(self.info, x0 + delta.x(), y0 + delta.y())
        else:
            ratio = (self._pix.height() / float(self._pix.width())
                     if self._pix.width() else 1.0)
            w = max(32, w0 + delta.x())
            h = max(24, int(w * ratio))
            self.editor._resize_float(self.info, w, h)
        self._apply_geometry()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._mode = None
        self._press = None
        self.update()
        self.editor._persist_floats()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击回到原始比例（宽度不超过正文一半）。"""
        self.editor._reset_float_size(self.info, self._pix)
        self._apply_geometry()
        self.editor._persist_floats()
        event.accept()

    def contextMenuEvent(self, event):
        self.editor.float_menu(self.info, self, self.mapToGlobal(event.pos()))


def build_float_menu(editor, info, widget=None, global_pos=None):
    """浮动图的右键菜单：环绕方式 / 尺寸 / 删除。"""
    menu = QMenu(widget or editor)
    cur = info.get('mode', 'above')
    for name in ('浮于文字上方', '衬于文字下方'):
        act = menu.addAction(name)
        act.setCheckable(True)
        act.setChecked(MODE_KEYS.get(name) == cur)
        act.triggered.connect(lambda _c, n=name: editor.change_float_mode(info, MODE_KEYS[n]))
    menu.addSeparator()
    act = menu.addAction('嵌入到文字中')
    act.triggered.connect(lambda: editor.embed_float(info))
    act = menu.addAction('原始大小')
    act.triggered.connect(lambda: editor._reset_float_size(info, None, widget))
    menu.addSeparator()
    act = menu.addAction('删除图片')
    act.triggered.connect(lambda: editor.remove_float(info))
    if global_pos is not None:
        pos = global_pos
    elif widget is not None:
        pos = widget.mapToGlobal(widget.rect().center())
    else:
        pos = editor.mapToGlobal(editor.rect().center())
    menu.exec_(pos)
    return menu

# -*- coding: utf-8 -*-
"""无边框顶层窗口的通用能力：四边 / 四角缩放 + 空白处拖动移动。

供「文本校验」(``WindowBook``) 与「特殊字符」(``SpecialCharPanel``) 共用，避免
两处各写一份 Windows 原生命中测试。用法::

    class MyPanel(FramelessResizableMixin, QWidget):
        ...

设计要点：

* 缩放靠 ``WM_NCHITTEST`` 返回 HTLEFT / HTRIGHT / ... 命中测试常量，后续拖拽
  由系统接管，比自己用 ``mouseMove`` 改 geometry 稳定（不抖、不会吞掉释放事件）；
  只有命中边框时才拦截消息，客户区一律交回 Qt，避免影响 hover / 光标。
* 移动靠鼠标事件：只在**非交互控件的空白区域**按下才启动拖动，不会抢走按钮
  点击、输入框光标、表格选择、符号格悬停。
* 磁吸跟随：浮窗吸附在主窗口边缘后，主窗口移动时浮窗同步跟随（在主窗口上
  装事件过滤器监听 Move，按吸附轴平移同样距离）；用户把浮窗拖离吸附带即脱附。
* PyQt5 的 ``nativeEvent`` 必须返回 ``(bool, int)`` 二元组；返回裸 ``int`` 会在
  每次命中测试时抛 ``TypeError``，密集的鼠标消息会把界面拖成假死。
* 子类可覆盖 ``_drag_zone_ok()`` 限制拖动区域、``_is_drag_handle()`` 补充
  不允许拖动的控件类型。
"""
import sys

from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (QAbstractScrollArea, QAbstractSpinBox, QCheckBox,
                             QApplication, QComboBox, QLineEdit, QListWidget,
                             QMainWindow, QPushButton, QRadioButton, QScrollBar,
                             QSlider, QTabWidget, QTableWidget, QTextBrowser,
                             QTextEdit, QToolButton, QTreeWidget)


class FramelessResizableMixin:
    """为无边框 QWidget 提供系统级边框缩放与鼠标拖动。"""

    FRAME_EDGE = 7          # 命中测试的边框敏感带（像素）
    DRAG_ZONE_H = 0         # 0 = 整个窗口的空白区都可拖；>0 则只允许顶部若干像素
    SNAP_DIST = 20          # 拖动时边缘距主窗口小于该值即吸附；0 = 关闭吸附

    _snap_target = None     # 吸附参照窗口（主窗口）；缺省自动找可见的 QMainWindow
    _snap_watch = None      # 被装了事件过滤器的顶层窗口（用于监听主窗口移动）
    # 是否吸附在主窗口的 X 边缘（左右贴边）/ Y 边缘（上下贴边）。
    # None 表示尚未评估（例如旧版吸附后未再拖动过的浮窗），首次需要时惰性检测。
    _snap_axis_x = None
    _snap_axis_y = None
    _dragging = False
    _drag_offset = None

    @property
    def snap_target(self):
        return self._snap_target

    @snap_target.setter
    def snap_target(self, w):
        if w is self:                       # 防御：不能以自己为吸附参照
            w = None
        old = self._snap_target
        if old is w:
            return
        if self._snap_watch is not None:
            self._snap_watch.removeEventFilter(self)
            self._snap_watch = None
        self._snap_target = w
        self._snap_axis_x = self._snap_axis_y = None
        if w is not None:
            top = w.window()                # 监听真正的顶层窗口的移动
            self._snap_watch = top
            top.installEventFilter(self)

    def eventFilter(self, obj, ev):
        """主窗口移动时，已吸附（或处于吸附带内）的浮窗跟随同样的位移。"""
        if (obj is self._snap_watch and ev.type() == QEvent.Move
                and self.isVisible() and not self._dragging):
            self._follow_target(ev.oldPos(), ev.pos())
        return super().eventFilter(obj, ev)

    def _follow_target(self, old_pos, new_pos):
        dx = new_pos.x() - old_pos.x()
        dy = new_pos.y() - old_pos.y()
        if not dx and not dy:
            return
        target = self._snap_target_rect()
        if target is None:
            return
        ax, ay = self._snap_axis_x, self._snap_axis_y
        if ax is None or ay is None:
            # 惰性检测必须对照主窗口**移动前**的矩形：吸附关系是相对移动前
            # 的位置建立的，对照新矩形会把已经贴边的浮窗误判成「不吸附」。
            ax, ay = self._detect_snap_axes(target.translated(-dx, -dy))
            self._snap_axis_x, self._snap_axis_y = ax, ay
        if not ax and not ay:
            return                          # 未吸附：不跟随
        g = self.frameGeometry()
        # 只吸了水平边（左右贴边）时，若浮窗与主窗口在竖向上重叠（典型的
        # 侧停靠），主窗口上下移动也应带着浮窗；反之亦然。
        overlap_y = g.top() <= target.bottom() and g.bottom() >= target.top()
        overlap_x = (g.left() <= target.right() + 1
                     and g.right() + 1 >= target.left())
        follow_x = bool(ax or (ay and overlap_x))
        follow_y = bool(ay or (ax and overlap_y))
        if follow_x or follow_y:
            self.move(g.left() + (dx if follow_x else 0),
                      g.top() + (dy if follow_y else 0))

    def _detect_snap_axes(self, target_rect=None):
        """按当前几何惰性判断是否处于吸附带内（兼容升级前已吸附的浮窗）。

        target_rect 缺省用主窗口当前矩形；判断历史吸附时传入移动前的矩形。
        """
        d = self.SNAP_DIST
        target = target_rect if target_rect is not None \
            else self._snap_target_rect()
        if target is None or d <= 0:
            return False, False
        g = self.frameGeometry()
        ax = (abs(g.left() - (target.right() + 1)) <= d
              or abs((g.right() + 1) - target.left()) <= d)
        ay = (abs(g.top() - (target.bottom() + 1)) <= d
              or abs((g.bottom() + 1) - target.top()) <= d)
        return ax, ay

    # ---------------- Windows 原生边框缩放 ----------------
    def nativeEvent(self, eventType, message):
        if sys.platform == 'win32' and eventType == b'windows_generic_MSG':
            try:
                import ctypes
                import ctypes.wintypes          # 必须显式导入，ctypes 不自动带出
                addr = int(message)
                if addr:
                    msg = ctypes.wintypes.MSG.from_address(addr)
                    if msg.message == 0x0084:  # WM_NCHITTEST
                        ht = self._hit_test(QCursor.pos())
                        if ht != 1:           # 客户区交回 Qt 自己处理
                            return True, ht
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def _hit_test(self, pos):
        g = self.frameGeometry()
        e = self.FRAME_EDGE
        x, y = pos.x(), pos.y()
        # 命中测试只发给鼠标下的窗口，这里再兜一层范围判断更保险
        if not (g.left() - e <= x <= g.right() + e and
                g.top() - e <= y <= g.bottom() + e):
            return 1                                # HTCLIENT
        left = x - g.left() <= e
        right = g.right() - x <= e
        top = y - g.top() <= e
        bottom = g.bottom() - y <= e
        if left and top:
            return 13                               # HTTOPLEFT
        if left and bottom:
            return 16                               # HTBOTTOMLEFT
        if right and top:
            return 14                               # HTTOPRIGHT
        if right and bottom:
            return 17                               # HTBOTTOMRIGHT
        if left:
            return 10                               # HTLEFT
        if right:
            return 11                               # HTRIGHT
        if top:
            return 12                               # HTTOP
        if bottom:
            return 15                               # HTBOTTOM
        return 1                                    # HTCLIENT

    # ---------------- 鼠标拖动移动 ----------------
    def _drag_zone_ok(self, pos):
        h = self.DRAG_ZONE_H
        return True if not h else pos.y() <= h

    @staticmethod
    def _is_drag_handle(child):
        """只有背景 / 标签类区域可作为拖动起点；交互控件一律排除。"""
        if child is None:
            return True
        blocked = (QPushButton, QToolButton, QLineEdit, QComboBox,
                   QTableWidget, QTabWidget, QAbstractSpinBox,
                   QTextEdit, QTextBrowser, QListWidget, QTreeWidget,
                   QScrollBar, QSlider, QCheckBox, QRadioButton,
                   QAbstractScrollArea)
        return not isinstance(child, blocked)

    def mousePressEvent(self, event):
        if (event.button() == Qt.LeftButton
                and self.isWindow()
                and self._drag_zone_ok(event.pos())
                and self._is_drag_handle(self.childAt(event.pos()))):
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self._dragging = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, '_dragging', False) and (event.buttons() & Qt.LeftButton):
            self.move(self._snap_pos(event.globalPos() - self._drag_offset))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    # ---------------- 靠近主窗口时吸附 ----------------
    def _snap_target_rect(self):
        """吸附参照矩形（主窗口的 frameGeometry）；找不到返回 None。"""
        t = self.snap_target
        if t is None:
            for w in QApplication.topLevelWidgets():
                if (w is not self and w.isVisible()
                        and isinstance(w, QMainWindow)):
                    t = w
                    break
        if t is None or t is self or not t.isVisible():
            return None
        return t.frameGeometry()

    def _snap_pos(self, pos):
        """拖动目标位置 pos 靠近主窗口边缘时，贴齐到边缘（外贴合）。

        同时记录本次落点吸在了哪个轴上（_snap_axis_x / _snap_axis_y），
        供主窗口移动时的跟随逻辑使用；拖离吸附带即自动脱附。
        """
        d = self.SNAP_DIST
        ax = ay = False
        if d > 0:
            target = self._snap_target_rect()
            if target is not None:
                g = self.frameGeometry()
                x, y = pos.x(), pos.y()
                # 水平：浮窗左缘贴主窗口右缘 / 浮窗右缘贴主窗口左缘
                if abs(x - (target.right() + 1)) <= d:
                    x = target.right() + 1
                    ax = True
                elif abs((x + g.width()) - target.left()) <= d:
                    x = target.left() - g.width()
                    ax = True
                # 垂直：浮窗顶缘贴主窗口底缘 / 浮窗底缘贴主窗口顶缘
                if abs(y - (target.bottom() + 1)) <= d:
                    y = target.bottom() + 1
                    ay = True
                elif abs((y + g.height()) - target.top()) <= d:
                    y = target.top() - g.height()
                    ay = True
                pos = QPoint(x, y)
        self._snap_axis_x, self._snap_axis_y = ax, ay
        return pos

    @staticmethod
    def set_drag_hint(widget):
        """给可拖动的背景区域一个「移动」光标与说明（不影响文字内容）。"""
        if widget is not None:
            widget.setCursor(Qt.SizeAllCursor)
            widget.setToolTip('拖动空白处移动窗口 · 拖动四边 / 四角缩放 · '
                              '靠近主窗口边缘自动吸附，吸附后随主窗口移动')

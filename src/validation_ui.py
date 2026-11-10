# -*- coding: utf-8 -*-
"""「文本校验」面板专用的轻量自绘控件。

把得分环、历史趋势这类必须自己画的东西从 main.py 里剥出来，
WindowBook 只负责组装与业务逻辑，不再膨胀成一大段 QPainter 代码。
全部控件只依赖 PyQt5，不读写用户数据，也不持有主窗口引用。
"""

from PyQt5.QtCore import (Qt, QRectF, QPointF, pyqtSignal, pyqtProperty,
                          QPropertyAnimation, QEasingCurve)
from PyQt5.QtGui import (QColor, QFont, QPainter, QPen, QBrush, QLinearGradient,
                         QPainterPath, QPolygonF)
from PyQt5.QtWidgets import QWidget

import math

_LEVEL_COLORS = {
    '严重': '#e2685f',
    '警告': '#e8a33d',
    '提示': '#4a8ae8',
    '通过': '#63b96b',
}


def level_color(name):
    return _LEVEL_COLORS.get(name, '#4a8ae8')


class ScoreRing(QWidget):
    """仪表盘式得分显示：270° 刻度弧 + 居中「校验」按钮。

    整枚分数盘本身就是一个「校验」按钮：点击即按当前文档与标记列表
    重新执行全部检查项（recheckRequested），hover 时弧线与文字高亮。

    Qt 的 drawArc 角度单位是 1/16 度、0° 在三点方向、正角逆时针。
    仪表盘从 225°（左下）顺时针扫 270° 到 -45°（右下），缺口留在底部。
    """

    recheckRequested = pyqtSignal()

    _START = 225          # 弧起点（度）
    _SWEEP = 270          # 弧总扫角（度）
    _PEN_W = 8            # 弧线宽度

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('ValidationScoreRing')
        self.setFixedSize(116, 116)
        self._value = 0                   # 目标分数（立即生效）
        self._display = 0.0               # 绘制用分数（动画逐步逼近目标）
        self._accent = QColor('#63b96b')
        self._caption = '待校验'
        self._serious = False
        self._hover = False
        self._anim = QPropertyAnimation(self, b'displayValue', self)
        self._anim.setDuration(650)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        # AI 校验进行中：一段亮弧沿 270° 外环 0→1→0 往复扫动（-1 = 无限循环）
        self._busy = False
        self._phase = 0.0
        self._busy_anim = QPropertyAnimation(self, b'busyPhase', self)
        self._busy_anim.setDuration(1700)
        self._busy_anim.setKeyValueAt(0.0, 0.0)
        self._busy_anim.setKeyValueAt(0.5, 1.0)
        self._busy_anim.setKeyValueAt(1.0, 0.0)
        self._busy_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._busy_anim.setLoopCount(-1)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('点击分数盘校验')
        self.setMouseTracking(True)

    # 彩虹色标：沿 270° 弧从低分（左下 / 左侧）到高分（右下 / 右侧）
    # 依次 红 → 橙 → 黄 → 绿，全程 RGB 线性插值，没有分段跳变。
    _SPECTRUM = ((0.0, '#e2685f'), (33.3, '#ef9a3d'),
                 (66.6, '#e8cf4a'), (100.0, '#5fd08a'))

    @staticmethod
    def color_for(score, serious=0):
        """分数 -> 彩虹色标上的颜色；有严重问题时锁定红色。"""
        if serious:
            return QColor('#e2685f')
        return ScoreRing._smooth_color(score)

    @staticmethod
    def _smooth_color(score):
        """分数（0~100）-> 彩虹色：红 → 橙 → 黄 → 绿 连续过渡。

        这个色标既用于「分数 -> 单点颜色」（SparkLine 末点、严重度判断），
        也用于沿弧按位置着色：弧上 t 处取 _smooth_color(t*100)，
        因此左侧低分区天然偏红、右侧高分区天然偏绿。
        """
        stops = ScoreRing._SPECTRUM
        s = max(0.0, min(100.0, float(score)))
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if s <= b:
                t = 0.0 if b == a else (s - a) / (b - a)
                ra, ga, ba = QColor(ca).red(), QColor(ca).green(), QColor(ca).blue()
                rb, gb, bb = QColor(cb).red(), QColor(cb).green(), QColor(cb).blue()
                return QColor(int(ra + (rb - ra) * t),
                              int(ga + (gb - ga) * t),
                              int(ba + (bb - ba) * t))
        return QColor(stops[-1][1])

    def _shade(self, t, light=100, dim=1.0):
        """弧上位置 t -> 彩虹色；light 提亮，dim 与深色底色混合做暗色标。"""
        c = QColor(self._smooth_color(max(0.0, min(100.0, t * 100.0))))
        if light != 100:
            c = c.lighter(light)
        if dim < 1.0:
            base = QColor('#233140')
            c = QColor(int(base.red() + (c.red() - base.red()) * dim),
                       int(base.green() + (c.green() - base.green()) * dim),
                       int(base.blue() + (c.blue() - base.blue()) * dim))
        return c

    def _draw_arc_spectrum(self, p, rect, cx, cy, a0, sweep, width,
                           alpha=255, light=100, dim=1.0, caps=True,
                           step=2.0, alpha_fn=None):
        """把一段弧拆成小段，逐段按它在整条色标上的位置取彩虹色。

        Qt 的 QConicalGradient 插值方向与仪表盘 225° 顺时针扫角相反，
        直接套用会把红色放到终点；分段绘制让「左低右高」的方向完全可控，
        也方便给扫光做从亮到暗的彗尾透明度渐变。
        """
        if sweep <= 0:
            return
        n = max(1, int(math.ceil(sweep / step)))
        da = sweep / n
        for i in range(n):
            hi = a0 - i * da
            mid = hi - da / 2.0
            t = (self._START - mid) / self._SWEEP
            c = self._shade(t, light, dim)
            a = alpha_fn(i / max(1, n - 1)) if alpha_fn else alpha
            c.setAlpha(int(max(0, min(255, a))))
            p.setPen(QPen(c, width, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(rect, int(round(hi * 16)), -int(round(da * 16)))
        if caps:
            # FlatCap 段间无缝但两端是平的，补两个圆头保持原来的胶囊形状。
            r = rect.width() / 2.0
            for deg, frac in ((a0, 0.0), (a0 - sweep, 1.0)):
                t = (self._START - deg) / self._SWEEP
                c = self._shade(t, light, dim)
                a = alpha_fn(frac) if alpha_fn else alpha
                c.setAlpha(int(max(0, min(255, a))))
                ang = math.radians(deg)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(c))
                p.drawEllipse(QPointF(cx + r * math.cos(ang),
                                      cy - r * math.sin(ang)),
                              width / 2.0, width / 2.0)

    # 动画驱动的属性：displayValue 变化时自动重绘
    @pyqtProperty(float)
    def displayValue(self):
        return self._display

    @displayValue.setter
    def displayValue(self, v):
        self._display = float(v)
        self.update()

    @pyqtProperty(float)
    def busyPhase(self):
        return self._phase

    @busyPhase.setter
    def busyPhase(self, v):
        self._phase = float(v)
        self.update()

    def setBusy(self, busy):
        """AI 校验进行中开关：外环亮弧往复扫动；结束后立即停并复位。"""
        busy = bool(busy)
        if busy == self._busy:
            return
        self._busy = busy
        if busy:
            self._phase = 0.0
            self._busy_anim.start()
        else:
            self._busy_anim.stop()
            self._phase = 0.0
        self.update()

    def isBusy(self):
        return self._busy

    def setValue(self, value, serious=0, animate=True):
        """设置目标分数；可见时用 650ms 缓动动画从当前值过渡过去。

        动画期间弧长跟随 ``displayValue`` 逐渐伸长/缩短；进度弧按弧上
        位置取彩虹色标（红 → 橙 → 黄 → 绿），严重问题时整条锁定红色。
        """
        self._value = max(0, min(100, int(value)))
        self._serious = bool(serious)
        self._accent = self.color_for(self._value, serious)
        self._caption = ('存在严重问题' if serious else
                         '建议修改' if self._value < 80 else
                         '检查通过' if self._value >= 95 else '基本合格')
        if animate and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._display)
            self._anim.setEndValue(float(self._value))
            self._anim.start()
        else:
            self._anim.stop()
            self._display = float(self._value)
        self.update()

    def value(self):
        return self._value

    def caption(self):
        return self._caption

    def markPending(self):
        """回到「待校验」：弧平滑收回，等待手动校验。"""
        self._anim.stop()
        self._value = 0
        self._caption = '待校验'
        self._serious = False
        self._anim.setStartValue(self._display)
        self._anim.setEndValue(0.0)
        self._anim.start()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        h = self.height()
        cx, cy = w / 2.0, h / 2.0
        rect = QRectF(12, 12, w - 24, h - 24)

        disp = max(0.0, min(100.0, self._display))
        red = QColor('#e2685f')

        # ---- 轨道弧：完整 270° 暗彩虹色标，左低分红 → 右高分绿 ----
        # 用不透明的混色而非半透明，保证任何父窗口底色下都能看清色标。
        self._draw_arc_spectrum(p, rect, cx, cy, self._START, self._SWEEP,
                                self._PEN_W, dim=0.54 if self._hover else 0.44)

        # ---- 进度弧：亮彩虹；AI 校验期间不画，去掉上一轮评分的环状色盘 ----
        sweep = self._SWEEP * disp / 100.0
        if sweep > 1.0 and not self._busy:
            if self._serious:
                grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
                grad.setColorAt(0.0, red.lighter(132))
                grad.setColorAt(1.0, red)
                p.setPen(QPen(QBrush(grad), self._PEN_W, Qt.SolidLine, Qt.RoundCap))
                p.drawArc(rect, self._START * 16, -int(sweep * 16))
            else:
                self._draw_arc_spectrum(p, rect, cx, cy, self._START, sweep,
                                        self._PEN_W, light=106)

        # ---- AI 校验进行中：彩虹彗尾沿外环 0→1→0 往复扫动 ----
        head = None
        if self._busy:
            span = 46.0
            head = self._START - (self._SWEEP - span) * self._phase

            def tail_alpha(frac):
                # frac=0 是亮头，frac=1 是彗尾末端；颜色本身也随弧上位置
                # 从红→橙→黄→绿过渡，扫动时能看到整条彩虹依次掠过。
                return 20 + 220 * (1.0 - frac) ** 1.6

            self._draw_arc_spectrum(p, rect, cx, cy, head, span,
                                    self._PEN_W + 2, light=116,
                                    caps=False, alpha_fn=tail_alpha)
            # 亮头：靠 head 的 12° 再叠一层高亮彩虹，形成彗核
            self._draw_arc_spectrum(p, rect, cx, cy, head, 12.0,
                                    self._PEN_W + 2, alpha=238, light=132)

        # ---- 刻度线：每 5 分一格，整 25 分加长提亮（画在弧外缘之外）----
        r0 = rect.width() / 2.0 + 6.0
        for i in range(0, 101, 5):
            major = (i % 25 == 0)
            ang = math.radians(self._START - self._SWEEP * i / 100.0)
            r1 = r0 + (5.0 if major else 3.0)
            p.setPen(QPen(QColor('#5f7183') if major else QColor('#384858'), 1))
            p.drawLine(QPointF(cx + r0 * math.cos(ang), cy - r0 * math.sin(ang)),
                       QPointF(cx + r1 * math.cos(ang), cy - r1 * math.sin(ang)))

        # ---- 仪表中心「校验」：busy 时文字也跟着扫光位置做颜色过渡 ----
        if self._busy and head is not None:
            t = (self._START - head) / self._SWEEP
            text_col = self._shade(t, light=138)
        else:
            text_col = QColor('#7fb2ff')
        p.setPen(text_col.lighter(118) if self._hover else text_col)
        f = QFont('Microsoft YaHei', 12)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, '校验')
        p.end()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.recheckRequested.emit()
        super().mousePressEvent(event)


class SparkLine(QWidget):
    """最近若干次校验得分的迷你趋势线（只在会话内保存，不写磁盘）。"""

    MAX_POINTS = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('ValidationSpark')
        self.setFixedHeight(34)
        self.setMinimumWidth(90)
        self._values = []

    def setValues(self, values):
        self._values = [max(0, min(100, int(v))) for v in values][-self.MAX_POINTS:]
        self.update()

    def values(self):
        return list(self._values)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        pad = 5.0
        if w <= 2 * pad or h <= 2 * pad:
            p.end()
            return

        # 参考线：100 / 60 分
        for val, col in ((100, '#2c3946'), (60, '#283440')):
            y = h - pad - (h - 2 * pad) * (val / 100.0)
            p.setPen(QPen(QColor(col), 1, Qt.DashLine))
            p.drawLine(QPointF(pad, y), QPointF(w - pad, y))

        vals = self._values
        if not vals:
            p.setPen(QColor('#6b7a8a'))
            f = QFont('Microsoft YaHei', 9)
            p.setFont(f)
            p.drawText(QRectF(pad, 0, w - 2 * pad, h),
                       Qt.AlignVCenter | Qt.AlignLeft, '暂无历史记录')
            p.end()
            return

        # 单点时也画一个可辨认的圆点，避免折线不可见
        pts = []
        step = (w - 2 * pad) / max(1, len(vals) - 1) if len(vals) > 1 else 0
        for i, v in enumerate(vals):
            x = pad + (step * i if len(vals) > 1 else (w - 2 * pad) / 2.0)
            y = h - pad - (h - 2 * pad) * (v / 100.0)
            pts.append(QPointF(x, y))

        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        # 面积填充
        fill = QPainterPath(path)
        fill.lineTo(QPointF(pts[-1].x(), h - pad))
        fill.lineTo(QPointF(pts[0].x(), h - pad))
        fill.closeSubpath()
        grad = QLinearGradient(0, pad, 0, h - pad)
        grad.setColorAt(0.0, QColor(74, 138, 232, 70))
        grad.setColorAt(1.0, QColor(74, 138, 232, 0))
        p.fillPath(fill, QBrush(grad))
        p.setPen(QPen(QColor('#4a8ae8'), 1.8, Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)

        last = pts[-1]
        last_color = QColor(ScoreRing.color_for(vals[-1]))
        p.setBrush(QBrush(last_color))
        p.setPen(QPen(QColor('#202b36'), 1.5))
        p.drawEllipse(last, 3.4, 3.4)
        p.end()

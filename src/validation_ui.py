# -*- coding: utf-8 -*-
"""「文本校验」面板专用的轻量自绘控件。

把得分环、历史趋势这类必须自己画的东西从 main.py 里剥出来，
WindowBook 只负责组装与业务逻辑，不再膨胀成一大段 QPainter 代码。
全部控件只依赖 PyQt5，不读写用户数据，也不持有主窗口引用。
"""

from PyQt5.QtCore import (Qt, QRectF, QPointF, pyqtSignal, pyqtProperty,
                          QPropertyAnimation, QEasingCurve)
from PyQt5.QtGui import (QColor, QFont, QImage, QPainter, QPen, QBrush,
                         QLinearGradient, QRadialGradient, QPainterPath,
                         QPolygonF)
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
    # 立体灯管横截面（由内到外）：(半径偏移/笔宽, 带宽/笔宽, 提亮%, 压暗, alpha倍率, Screen叠加)
    # 一条满色打底保证管体无缝，内侧先压一道 AO 再补很淡的环境反光，
    # 外侧叠一条偏外的镜面高光 + 最外 AO 收边 → 读起来是一根受光的圆管。
    _PIPE = (
        ( 0.00, 1.00, 100, 1.00, 1.00, False),   # 主色满底
        (-0.41, 0.22, 100, 0.50, 0.90, False),   # 内缘 AO 暗边
        (-0.22, 0.30, 120, 1.00, 0.32, True ),   # 内侧环境反光（淡）
        ( 0.11, 0.30, 172, 1.00, 0.82, True ),   # 镜面高光（偏外）
        ( 0.42, 0.20, 100, 0.55, 0.88, False),   # 外缘 AO 暗边
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('ValidationScoreRing')
        self.setFixedSize(116, 116)
        # 自绘全靠 paintEvent：控件本身透出 ValidationScoreCard 的卡片底色，
        # 3D 落影 / 中心凹槽才落在正确的深色上（不被 qdarkstyle 的 QWidget
        # 默认背景盖成另一种灰）。
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
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
        # 3D 灯管缓存：满弧分层只栅格化一次（key 含 hover / serious），
        # 进度弧再按 displayValue 用遮罩裁出，动画时不再逐段重画 5 层。
        # 缓存用 2× 尺寸栅格化再缩回，兼顾高分屏清晰度；单帧只剩 2~3 次
        # drawImage + 一次遮罩，setValue 动画（650ms）不再掉帧。
        self._bg_cache = {}            # (w, h, hover) -> QImage  落影+凹槽+轨道+刻度
        self._bright_cache = {}        # (w, h, hover, serious) -> QImage  满弧亮管
        self._cache_ratio = 2

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

    def _shade(self, t, light=100, dim=1.0, solid=None):
        """弧上位置 t -> 彩虹色；light 提亮，dim 与深色底色混合做暗色标。

        solid 给定时忽略彩虹色标、直接用该颜色（严重问题的整条红弧也走
        同一套 3D 灯管绘制，只是底色锁定为红）。
        """
        c = QColor(solid) if solid is not None else QColor(
            self._smooth_color(max(0.0, min(100.0, t * 100.0))))
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
                           step=2.0, alpha_fn=None, profile=None, solid=None):
        """把一段弧拆成小段逐段着色；profile 给定时按立体灯管横截面分层绘制。

        profile 的每一项是 (半径偏移/笔宽, 带宽/笔宽, 提亮%, 压暗, alpha倍率,
        Screen叠加)。半径偏移把同心细弧铺在管体截面的不同深度上，叠出受光
        圆管；不给 profile 时退化为原来的单层弧（busy 彗尾仍走这条快路）。
        """
        if sweep <= 0:
            return
        profile = profile or ((0.0, 1.0, 100, 1.0, 1.0, False),)
        n = max(1, int(math.ceil(sweep / step)))
        da = sweep / n
        p.save()
        try:
            # 由内到外逐层铺同心细弧，后来的 Screen 层叠在先前主色之上。
            # 每层段数相同、角度严格对齐，FlatCap 拼接处才不会留缝。
            for off, wf, blight, bdim, balpha, screen in profile:
                d = off * width                       # 半径偏移（像素，正=向外）
                band_rect = rect.adjusted(-d, -d, d, d)
                band_w = max(0.6, wf * width)
                eff_dim = min(1.0, dim * bdim)
                eff_light = int(round(light * blight / 100.0))
                p.setCompositionMode(QPainter.CompositionMode_Screen if screen
                                     else QPainter.CompositionMode_SourceOver)
                # 一支笔复用整层：循环里只换颜色，不为每段新建 QPen / QColor
                pen = QPen()
                pen.setWidthF(band_w)
                pen.setStyle(Qt.SolidLine)
                pen.setCapStyle(Qt.FlatCap)
                for i in range(n):
                    hi = a0 - i * da
                    mid = hi - da / 2.0
                    t = (self._START - mid) / self._SWEEP
                    c = self._shade(t, eff_light, eff_dim, solid)
                    a = alpha_fn(i / max(1, n - 1)) if alpha_fn else alpha
                    c.setAlpha(int(max(0, min(255, a * balpha))))
                    pen.setColor(c)
                    p.setPen(pen)
                    p.drawArc(band_rect, int(round(hi * 16)),
                              -int(round(da * 16)))

            # 端点：满色底补圆头（FlatCap 两端是平的），再叠一枚偏左上的高光
            # 小球，读起来是胶囊端面的立体圆头，而非两刀切平的截面。
            if caps:
                r = rect.width() / 2.0
                for deg, frac in ((a0, 0.0), (a0 - sweep, 1.0)):
                    a = alpha_fn(frac) if alpha_fn else alpha
                    self._paint_cap(p, cx, cy, r, deg, width, light, dim,
                                    solid, a)
        finally:
            p.restore()

    def _paint_cap(self, p, cx, cy, r, deg, width, light, dim, solid=None,
                   alpha=255):
        """一枚立体圆头：彩虹底色圆 + 偏左上的高光小球。进度弧被遮罩裁出
        后，起点/末端两个圆头也靠它补回（否则是径向一刀切的平口）。"""
        t = (self._START - deg) / self._SWEEP
        c = self._shade(t, light, dim, solid)
        c.setAlpha(int(max(0, min(255, alpha))))
        ang = math.radians(deg)
        pos = QPointF(cx + r * math.cos(ang), cy - r * math.sin(ang))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        p.drawEllipse(pos, width / 2.0, width / 2.0)
        p.setCompositionMode(QPainter.CompositionMode_Screen)
        hl = self._shade(t, 165, 1.0, solid)
        hl.setAlpha(int(max(0, min(255, alpha * 0.62))))
        p.setBrush(QBrush(hl))
        p.drawEllipse(QPointF(pos.x() - width * 0.09,
                              pos.y() - width * 0.09),
                      width * 0.22, width * 0.22)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def _draw_arc_shadow(self, p, rect, cx, cy, a0, sweep, width):
        """整条弧的软落影：向外扩一圈极低透明度的深色，让灯管看起来浮在
        卡片上方。用 3 层同心弧近似高斯羽化，比 QGraphicsDropShadowEffect
        便宜得多，也不引入额外的图形effect节点。"""
        p.save()
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        for spread, alpha in ((0.9, 26), (0.5, 30), (0.0, 24)):
            d = width * spread * 0.75
            sr = rect.adjusted(-d, -d, d, d)
            c = QColor('#050b12')
            c.setAlpha(alpha)
            p.setPen(QPen(c, width * (1.0 + spread * 0.55),
                          Qt.SolidLine, Qt.RoundCap))
            p.drawArc(sr, int(round(a0 * 16)), -int(round(sweep * 16)))
        p.restore()

    def _draw_center_well(self, p, cx, cy, r):
        """中心「表盘」凹槽：贴着灯管内缘一圈柔和内阴影 + 上壁一道淡冷反光，
        做出灯管嵌在一枚凹陷圆盘里的深度感。纯装饰，压得很淡不抢文字。"""
        if r <= 2:
            return
        p.save()
        # 内阴影：中心透明，靠近灯管的一圈压暗，最外再收回透明，避免硬边
        p.setPen(Qt.NoPen)
        g = QRadialGradient(cx, cy, r)
        g.setColorAt(0.00, QColor(18, 28, 38, 0))
        g.setColorAt(0.62, QColor(18, 28, 38, 0))
        g.setColorAt(0.94, QColor(6, 11, 17, 46))
        g.setColorAt(1.00, QColor(6, 11, 17, 0))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), r, r)
        # 凹槽上壁反光：一道 160° 的细弧（左上到右上），模拟顶光
        ar = r * 0.965
        arc_rect = QRectF(cx - ar, cy - ar, ar * 2, ar * 2)
        p.setCompositionMode(QPainter.CompositionMode_Screen)
        c = QColor(116, 158, 198)
        c.setAlpha(20)
        p.setPen(QPen(c, 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc_rect, int(round(28 * 16)), -int(round(124 * 16)))
        p.restore()

    def _draw_ticks(self, p, rect, cx, cy):
        """刻度线：每 5 分一格，整 25 分加长提亮；主刻度叠一道冷高光，
        与灯管共用「左上受光」方向。属于静态背景，随背景层一起缓存。"""
        r0 = rect.width() / 2.0 + 6.0
        for i in range(0, 101, 5):
            major = (i % 25 == 0)
            ang = math.radians(self._START - self._SWEEP * i / 100.0)
            r1 = r0 + (5.0 if major else 3.0)
            ca, sa = math.cos(ang), math.sin(ang)
            x0, y0 = cx + r0 * ca, cy - r0 * sa
            x1, y1 = cx + r1 * ca, cy - r1 * sa
            p.setPen(QPen(QColor('#64788b') if major else QColor('#3b4b5b'), 1))
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
            if major:
                p.setCompositionMode(QPainter.CompositionMode_Screen)
                hl = QColor(150, 182, 210)
                hl.setAlpha(60)
                p.setPen(QPen(hl, 1))
                p.drawLine(QPointF(x0 - 0.7, y0 - 0.7),
                           QPointF(x1 - 0.7, y1 - 0.7))
                p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def _new_layer(self, w, h):
        """开一张透明离屏层，按缓存倍率放大坐标系，返回 (image, painter)。"""
        ratio = self._cache_ratio
        img = QImage(w * ratio, h * ratio, QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.scale(ratio, ratio)
        return img, p

    def _build_bg(self, w, h, hover):
        """静态背景层：整环软落影 + 中心凹槽 + 暗轨道灯管 + 刻度。
        只在尺寸或 hover 变化时重建一次；动画帧直接 drawImage。"""
        img, p = self._new_layer(w, h)
        try:
            cx, cy = w / 2.0, h / 2.0
            rect = QRectF(12, 12, w - 24, h - 24)
            self._draw_arc_shadow(p, rect, cx, cy, self._START, self._SWEEP,
                                  self._PEN_W)
            self._draw_center_well(p, cx, cy,
                                   rect.width() / 2.0 - self._PEN_W / 2.0)
            # 暗轨道：完整 270° 立体灯管（带两端圆头）
            self._draw_arc_spectrum(p, rect, cx, cy, self._START, self._SWEEP,
                                    self._PEN_W,
                                    dim=0.54 if hover else 0.44,
                                    profile=self._PIPE)
            self._draw_ticks(p, rect, cx, cy)
        finally:
            p.end()
        return img

    def _build_bright(self, w, h, hover, serious):
        """满弧亮管层：完整 270° 亮彩虹立体灯管（两端圆头）。进度显示时
        用扇形遮罩从这层裁出 0..sweep 的一段，避免每帧逐段重画 5 层。"""
        img, p = self._new_layer(w, h)
        try:
            cx, cy = w / 2.0, h / 2.0
            rect = QRectF(12, 12, w - 24, h - 24)
            self._draw_arc_spectrum(
                p, rect, cx, cy, self._START, self._SWEEP, self._PEN_W,
                light=112 if hover else 106, profile=self._PIPE,
                solid=QColor('#e2685f') if serious else None)
        finally:
            p.end()
        return img

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
        target = QRectF(0, 0, w, h)
        disp = max(0.0, min(100.0, self._display))

        # ---- ① 静态背景层：落影 + 凹槽 + 暗轨道灯管 + 刻度（带缓存）----
        # 这一层只在尺寸 / hover 变化时重建；setValue 动画期间逐帧零重算。
        bgk = (w, h, self._hover)
        bg = self._bg_cache.get(bgk)
        if bg is None:
            bg = self._build_bg(w, h, self._hover)
            self._bg_cache[bgk] = bg
        p.drawImage(target, bg)

        # ---- ② 进度弧：满弧亮管缓存 + 扇形遮罩裁出 0..sweep ----
        # 5 层灯管只栅格化一次，动画帧仅一次 drawImage + 一次 clipPath，
        # 从原来的 ~110ms 降到亚毫秒级；两个径向平口补成立体圆头。
        head = None
        sweep = self._SWEEP * disp / 100.0
        if sweep > 1.0 and not self._busy:
            bk = (w, h, self._hover, self._serious)
            bright = self._bright_cache.get(bk)
            if bright is None:
                bright = self._build_bright(w, h, self._hover, self._serious)
                self._bright_cache[bk] = bright
            # 扇形（1× 坐标）：圆心 → 起点，顺时针扫 sweep → 回到圆心。
            # 半径取控件对角线，确保盖住整枚灯管；中心区本就透明，不影响。
            R = math.hypot(w, h)
            wedge = QPainterPath()
            wedge.moveTo(cx, cy)
            n = max(2, int(math.ceil(sweep / 2.0)))
            for i in range(n + 1):
                deg = self._START - sweep * i / n
                a = math.radians(deg)
                wedge.lineTo(cx + R * math.cos(a), cy - R * math.sin(a))
            wedge.closeSubpath()
            p.save()
            p.setClipPath(wedge)
            p.drawImage(target, bright)
            p.restore()
            # 遮罩切出的平口补立体圆头（起点固定、末端随分数移动）
            light = 112 if self._hover else 106
            solid = QColor('#e2685f') if self._serious else None
            r = rect.width() / 2.0
            self._paint_cap(p, cx, cy, r, self._START, self._PEN_W,
                            light, 1.0, solid)
            self._paint_cap(p, cx, cy, r, self._START - sweep, self._PEN_W,
                            light, 1.0, solid)

        # ---- ③ AI 校验进行中：彩虹彗尾往复扫动 ----
        # 彗尾刻意扁平发光（不叠 3D）、位置随 phase 移动无法缓存，仍逐段；
        # 但它走无 profile 的单层快路，开销很小。
        if self._busy:
            span = 46.0
            head = self._START - (self._SWEEP - span) * self._phase

            def tail_alpha(frac):
                # frac=0 是亮头，frac=1 是彗尾末端；颜色随弧上位置红→橙→黄→绿
                return 20 + 220 * (1.0 - frac) ** 1.6

            self._draw_arc_spectrum(p, rect, cx, cy, head, span,
                                    self._PEN_W + 2, light=116,
                                    caps=False, alpha_fn=tail_alpha,
                                    step=4.0)
            # 亮头：靠 head 的 12° 再叠一层高亮彩虹，形成彗核
            self._draw_arc_spectrum(p, rect, cx, cy, head, 12.0,
                                    self._PEN_W + 2, alpha=238, light=132,
                                    step=4.0)

        # ---- ④ 中心「校验」：浮雕（下沉暗影 + 主体亮字）----
        if self._busy and head is not None:
            t = (self._START - head) / self._SWEEP
            text_col = self._shade(t, light=138)
        else:
            text_col = QColor('#7fb2ff')
        f = QFont('Microsoft YaHei', 12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(4, 10, 17, 150))
        p.drawText(QRectF(0, 1, w, h), Qt.AlignCenter, '校验')
        p.setPen(text_col.lighter(118) if self._hover else text_col)
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

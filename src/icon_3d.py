"""Fenrir 3D 图标工厂（统一接管 qtawesome 图标）。

原界面里所有按钮图标都是 qtawesome 的单色字字形：扁平、和深色背景对比弱。
本模块把字形的 alpha 蒙版重新合成为一枚有体积感的图标，保留原始图形与
尺寸，不改变任何按钮/动作的创建逻辑：

    底部投影  →  垂直渐变主体（顶亮 / 中彩 / 底暗）
              →  球面高光（左上偏亮）
              →  左上高光斜边 + 右下暗斜边（bevel，模拟厚度）

颜色按图标语义分组（文件=蓝、模板=紫、图片=青、危险=珊瑚、工具=琥珀、
校验=绿），并统一往白色提亮，保证深色主题下协调、不刺眼；调用处显式传了
``color=`` 的（窗口按钮、搜索框、查找替换栏等中性线条图标）则以该色为
基准做同色明暗渐变，不引入色相，避免系统按钮变成彩色糖果。

每个图标按 16 / 26 / 64 / 128 四种尺寸分别渲染（bevel 宽度按尺寸取 1~3px），
小尺寸下斜边不会因为从大图缩小而糊掉；结果按 (name, color) 缓存复用。
任何异常都会静默回落到 qtawesome 原始图标，绝不影响程序启动。
"""

import hashlib
import os
import pickle
import sys

from PyQt5.QtCore import (Qt, QPointF, QSize, QByteArray, QBuffer,
                          QIODevice, QTimer)
from PyQt5.QtGui import (QBrush, QColor, QIcon, QImage, QLinearGradient,
                         QPainter, QPixmap, QRadialGradient)

# 常用请求尺寸：功能区小按钮 15px、大按钮 26px、窗口图标更大。
_SIZES = (16, 26, 64, 128)
_CACHE = {}

# ---- 跨进程磁盘缓存 -----------------------------------------------------
# 72 个图标 × 4 尺寸 × 2 状态 = 576 张 QPixmap，qtawesome 每生成一张都要
# 用字体重新栅格化一次（实测启动约 2.6s）。生成的位图与机器无关，缓存到
# data/ 下后，下次启动只需解码 PNG（约 0.1s）。签名用本文件源码 + 配色表
# + qtawesome 版本的 md5：任何影响外观的改动都会让旧缓存自动失效。
_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', '.icon3d_cache.bin')
_DISK = None            # None = 尚未读盘
_FLUSH_PENDING = False


def _signature():
    try:
        with open(__file__, 'rb') as f:
            src = f.read()
    except Exception:
        src = b''
    _q = sys.modules.get('qtawesome')
    ver = getattr(_q, '__version__', '') if _q is not None else ''
    tail = repr((_SIZES, _COLOR_RULES, _DEFAULT_COLOR, _DISABLED, ver)).encode()
    return hashlib.md5(src + tail).hexdigest()


def _disk_cache():
    global _DISK
    if _DISK is None:
        _DISK = {}
        try:
            with open(_CACHE_PATH, 'rb') as f:
                sig, payload = f.read().split(b'\n', 1)
            if sig.decode('ascii') == _signature():
                obj = pickle.loads(payload)
                if isinstance(obj, dict):
                    _DISK = obj
        except Exception:
            _DISK = {}
    return _DISK


def flush_icon_cache():
    """把本次新渲染的图标一次性落盘（由延迟定时器调用，也可手动调用）。"""
    global _FLUSH_PENDING
    _FLUSH_PENDING = False
    disk = _DISK
    if not disk:
        return
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        blob = _signature().encode('ascii') + b'\n' + pickle.dumps(disk, protocol=4)
        tmp = _CACHE_PATH + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(blob)
        os.replace(tmp, _CACHE_PATH)
    except Exception:
        pass


def _schedule_flush():
    global _FLUSH_PENDING
    if _FLUSH_PENDING:
        return
    _FLUSH_PENDING = True
    try:
        QTimer.singleShot(2500, flush_icon_cache)
    except Exception:
        _FLUSH_PENDING = False


def _png_bytes(pm):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, 'PNG')
    buf.close()
    return bytes(ba)

# 语义配色：靠前的规则优先。只取图标名的最后一段做匹配（如 'mdi6.plus' → 'plus'）。
_COLOR_RULES = (
    (('close', 'times', 'delete', 'trash', 'eraser', 'remove', 'ban',
      'flame', 'cancel', 'minus'), '#ff9d8f'),
    (('save', 'check', 'shield', 'thumb', 'cloud-check', 'book-check'), '#7fdfa8'),
    (('folder', 'file', 'plus', 'paste', 'download', 'upload', 'content-save',
      'archive', 'document'), '#7bbdff'),
    (('rocket', 'template', 'polygon', 'poker', 'recycle', 'hammer', 'law',
      'xml', 'hub', 'slack', 'planet', 'path'), '#c6aaff'),
    (('gear', 'wrench', 'server', 'webhook', 'search', 'help', 'toolbox',
      'settings', 'cog', 'brain', 'translate', 'searchengin'), '#ffd08c'),
    (('image', 'table', 'picasa', 'paint', 'brush', 'camera', 'palette',
      'pic', 'picture'), '#6bd8d2'),
)
_DEFAULT_COLOR = '#9fcdff'
_DISABLED = ('#a8b4c2', '#788692', '#48535f')


def _blend(a, b, t):
    """QColor 线性插值（t=0 取 a，t=1 取 b）。"""
    return QColor(round(a.red() * (1 - t) + b.red() * t),
                  round(a.green() * (1 - t) + b.green() * t),
                  round(a.blue() * (1 - t) + b.blue() * t),
                  round(a.alpha() * (1 - t) + b.alpha() * t))


def _semantic_color(name, explicit):
    """返回 (top, mid, bottom, is_neutral) 三色渐变端点。"""
    if explicit is not None:
        base = QColor(explicit)
        if not base.isValid():
            base = QColor('#cdd9e3')
        neutral = True
    else:
        key = str(name).split('.')[-1].lower()
        hex_color = _DEFAULT_COLOR
        for words, color in _COLOR_RULES:
            if any(w in key for w in words):
                hex_color = color
                break
        base = QColor(hex_color)
        neutral = False
    white, ink = QColor('#ffffff'), QColor('#0a1626')
    # 顶部提亮到接近白、底部压向深蓝黑：中间保留基色，形成玻璃/金属的立体层次。
    top = _blend(base, white, 0.62 if not neutral else 0.34)
    mid = _blend(base, white, 0.10 if not neutral else 0.0)
    bottom = _blend(base, ink, 0.48 if not neutral else 0.46)
    return top, mid, bottom, neutral


def _mask(src):
    """把 qtawesome 字形变成纯白 + 保留抗锯齿 alpha 的蒙版。"""
    img = src.toImage().convertToFormat(QImage.Format_ARGB32)
    out = QPixmap(img.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(out.rect(), Qt.white)
    p.end()
    return out


def _tint(mask, color):
    """给蒙版着色（保留 alpha）。"""
    out = QPixmap(mask.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, mask)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor(color))
    p.end()
    return out


def _shift(mask, dx, dy):
    out = QPixmap(mask.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap(dx, dy, mask)
    p.end()
    return out


def _edge(mask, dx, dy):
    """mask 减去平移后的 mask，得到一侧的细斜边。"""
    out = QPixmap(mask.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, mask)
    p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    p.drawPixmap(dx, dy, mask)
    p.end()
    return out


def _render(raw_pm, n, shades, neutral=False, disabled=False):
    """合成单枚 n×n 的 3D 图标。

    小尺寸（功能区小按钮 15~16px）要单独收敛效果：字形笔画往往只有 1~2px，
    1px 的暗斜边会吃掉近一半笔画，加上底部压暗会让图标下半截融进深色背景
    （离屏实测比改前的扁平图标更难辨认）。所以小图只保留渐变与球面高光，
    暗边减到几乎不可见、不放投影，并把渐变下端整体提亮。
    """
    mask = _mask(raw_pm)
    bevel = 1 if n <= 26 else (2 if n <= 64 else 3)
    small = n <= 26
    if disabled:
        top, mid, bottom = (QColor(c) for c in _DISABLED)
        hi_alpha, lo_alpha, glow_alpha = 70, 60, 0
        if small:
            bottom = _blend(bottom, QColor('#ffffff'), 0.30)
    else:
        top, mid, bottom = shades
        if neutral:
            hi_alpha, lo_alpha, glow_alpha = 110, 80, 34
        else:
            hi_alpha, lo_alpha, glow_alpha = 150, 105, 66
        if small:
            # 绝对亮度必须明显高于 #1b2530 的功能区底色，只保留相对明暗差。
            mid = _blend(mid, QColor('#ffffff'), 0.20)
            bottom = _blend(bottom, QColor('#ffffff'), 0.48)
            hi_alpha, lo_alpha = 95, 24

    canvas = QPixmap(n, n)
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    # 1) 底部投影：让字形从深色底上"浮"起来（小图标省略，否则笔画发糊）
    if not disabled and not small:
        shadow = _tint(_shift(mask, 0, bevel + 1), QColor(3, 10, 20, 88))
        p.drawPixmap(0, 0, shadow)

    # 2) 主体垂直渐变 ∩ 字形蒙版
    grad = QLinearGradient(0, 0, 0, n)
    grad.setColorAt(0.0, top)
    grad.setColorAt(0.46, mid)
    grad.setColorAt(1.0, bottom)
    body = QPixmap(n, n)
    body.fill(Qt.transparent)
    pb = QPainter(body)
    pb.fillRect(body.rect(), QBrush(grad))
    pb.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    pb.drawPixmap(0, 0, mask)
    pb.end()
    p.drawPixmap(0, 0, body)

    # 3) 左上球面高光：只在已绘制出的像素内提亮
    if glow_alpha:
        glow = QRadialGradient(QPointF(n * 0.34, n * 0.20), n * 0.78)
        glow.setColorAt(0.0, QColor(255, 255, 255, glow_alpha))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        p.fillRect(canvas.rect(), QBrush(glow))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    # 4) 左上高光斜边 / 右下暗斜边：模拟挤出厚度
    hi = _tint(_edge(mask, bevel, bevel), QColor(255, 255, 255, hi_alpha))
    p.drawPixmap(0, 0, hi)
    lo = _tint(_edge(mask, -bevel, -bevel), QColor(6, 16, 30, lo_alpha))
    p.drawPixmap(0, 0, lo)
    p.end()
    return canvas


def build(raw_icon, name, explicit=None):
    """把 qtawesome 的 QIcon 包装成 3D QIcon；失败时返回原图标。

    命中磁盘缓存时直接解码 PNG 组回 QIcon，跳过全部字体栅格化；
    未命中才走原来的合成路径，并把结果排进延迟写盘。
    """
    key = (str(name), str(explicit) if explicit is not None else None)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    disk = _disk_cache()
    hit = disk.get(key)
    if hit is not None:
        try:
            out = QIcon()
            for n, mode, state, png in hit:
                pm = QPixmap()
                if not pm.loadFromData(QByteArray(png), 'PNG') or pm.isNull():
                    raise ValueError('bad pixmap')
                out.addPixmap(pm, QIcon.Mode(mode), QIcon.State(state))
            if not out.isNull():
                _CACHE[key] = out
                return out
        except Exception:
            pass                     # 缓存损坏 → 回落到正常渲染并覆写
    top, mid, bottom, neutral = _semantic_color(name, explicit)
    shades = (top, mid, bottom)
    out = QIcon()
    frames = []
    _off = QIcon.Off
    for n in _SIZES:
        src = raw_icon.pixmap(QSize(n, n), QIcon.Normal, _off)
        if src.isNull():
            return raw_icon
        normal = _render(src, n, shades, neutral)
        # 主动提供禁用态，避免 QStyle 差异导致禁用按钮仍显示鲜艳图标
        disabled = _render(src, n, None, neutral, disabled=True)
        out.addPixmap(normal, QIcon.Normal, _off)
        out.addPixmap(disabled, QIcon.Disabled, _off)
        frames.append((n, int(QIcon.Normal), int(_off), _png_bytes(normal)))
        frames.append((n, int(QIcon.Disabled), int(_off), _png_bytes(disabled)))
    disk[key] = frames
    _CACHE[key] = out
    _schedule_flush()
    return out


class _QtAwesomeProxy:
    """只代理 icon()，其余属性原样转发，不污染 qtawesome 全局模块。"""

    __slots__ = ('_module',)

    def __init__(self, module):
        self._module = module

    def icon(self, *args, **kwargs):
        raw = self._module.icon(*args, **kwargs)
        try:
            name = '.'.join(str(a) for a in args) if args else ''
            return build(raw, name, kwargs.get('color'))
        except Exception:
            return raw

    def __getattr__(self, item):
        return getattr(self._module, item)


def wrap(module):
    """接管模块里的 icon()，main.py 只需在 import 后调用一次。"""
    return _QtAwesomeProxy(module)

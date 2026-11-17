# -*- coding: utf-8 -*-
"""申请文件打印：把 100004 / 100001 / 100002 / 100003 排成国知局（CPC）样式的 A4 PDF。

版式取自国知局打印稿（受通 + 申请文件）实测参数：

    A4 210×297mm
    正文区：左 2.5cm、右 1.5cm、上 2.5cm，宽 17cm
    正文：宋体 10.5pt（五号），行距 15.6pt
    文档名（说明书 / 权利要求书 / 说明书摘要 / 说明书附图）：14pt，居中，
        骑在正文区顶边的横线上方；正文区顶边画一条 0.75 宽横线
    页脚：9pt，左＝文档代码（100002…），中＝页码（每份文档重新计），右＝2023.03
    说明书正文按 [0001] 起逐段编号，章节标题单独成行
    附图：一页三图，图下居中标注「图 N」

只做排版，不碰 XML：正文从 XML 的叶节点按文档顺序取出来后交给本模块。
"""

import gc
import os
import tempfile

from PyQt5.QtCore import QPointF, QRectF, QSizeF
from PyQt5.QtGui import (QColor, QFont, QFontInfo, QFontMetricsF, QImage,
                         QPainter, QPen)

DPI = 720                    # 720 = 72×10，让「pt→像素」为整数，坐标不丢精度
PT = DPI / 72.0
MM = DPI / 25.4

PAGE_W, PAGE_H = 210 * MM, 297 * MM
MARGIN_L, MARGIN_R = 25 * MM, 15 * MM
MARGIN_T, MARGIN_B = 25 * MM, 20 * MM
TEXT_W = PAGE_W - MARGIN_L - MARGIN_R
TEXT_TOP = MARGIN_T
TEXT_BOTTOM = PAGE_H - MARGIN_B

BODY_PT = 10.5
LEAD_PT = 15.6
HEAD_PT = 14.0
FOOT_PT = 9.0
VER = '2023.03'

# 行首禁则（不能出现在行首）/ 行末禁则（不能出现在行末）
HEAD_FORBID = '，。、；：？！）〉》」』】〕”’%,.;:?!)]}›»·…—～'
TAIL_FORBID = '（〈《「『【〔“‘([{‹«'

# 章节标题：说明书按这些小标题切段（含常见别写）
SECS = ('技术领域', '背景技术', '发明内容', '实用新型内容', '附图说明', '具体实施方式')
SEC_ALIAS = {
    '所属技术领域': '技术领域', '发明所属技术领域': '技术领域',
    '本实用新型所属技术领域': '技术领域', '技术领域': '技术领域',
    '背景技术': '背景技术', '发明内容': '发明内容', '实用新型内容': '发明内容',
    '本实用新型内容': '发明内容', '实用新型的技术方案': '发明内容',
    '附图说明': '附图说明', '附图及附图说明': '附图说明',
    '具体实施方式': '具体实施方式', '实施例': '具体实施方式',
    '具体实施例': '具体实施方式', '实施方式': '具体实施方式',
}

DOC_CODES = {'abs': '100004', 'claims': '100001', 'desc': '100002', 'draw': '100003'}
DOC_NAMES = {'abs': '说明书摘要', 'claims': '权利要求书',
             'desc': '说明书', 'draw': '说明书附图'}


def canon_section(text):
    """把一段文字归一成章节名；不是章节标题返回 ''。"""
    t = (text or '').strip()
    if not t or len(t) > 20:
        return ''
    t = t.replace('\u3000', ' ')
    for a, b in (('【', ''), ('】', ''), ('[', ''), (']', ''),
                 ('（', ''), ('）', ''), ('(', ''), (')', '')):
        t = t.replace(a, b)
    t = t.strip(' ：:．.、，,')
    if not t:
        return ''
    # 去掉「一、」「1.」这类序号前缀
    i = 0
    while i < len(t) and t[i] in '一二三四五六七八九十0123456789':
        i += 1
    if 0 < i < len(t) and t[i] in '、.．)）':
        t = t[i + 1:].strip()
    return SEC_ALIAS.get(t, t if t in SECS else '')


def _font_family():
    """国知局打印稿用宋体：优先解析到宋体系，实在没有才退回系统默认。"""
    for name in ('宋体', 'SimSun', 'NSimSun', '新宋体', '仿宋', 'FangSong'):
        fam = QFontInfo(QFont(name)).family()
        low = (fam or '').lower()
        if fam and (fam == name or 'sun' in low or '宋' in fam or 'fang' in low):
            return fam
    return QFontInfo(QFont()).family()


class _Measurer(object):
    """按字符量算宽度（带缓存），中文字符宽度≈字号。"""

    def __init__(self, font):
        self.fm = QFontMetricsF(font)
        self.cache = {}

    def __call__(self, ch):
        w = self.cache.get(ch)
        if w is None:
            w = self.fm.horizontalAdvance(ch)
            self.cache[ch] = w
        return w


def wrap_text(text, measure, max_w):
    """按字符折行，带行首/行末禁则。"""
    lines = []
    cur = ''
    cur_w = 0.0
    for ch in text:
        cw = measure(ch)
        if not cur or cur_w + cw <= max_w:
            cur += ch
            cur_w += cw
            continue
        if ch in HEAD_FORBID:
            # 标点跟着上一行走（允许极轻微超出）
            lines.append(cur + ch)
            cur, cur_w = '', 0.0
            continue
        if cur[-1] in TAIL_FORBID and len(cur) > 1:
            moved = cur[-1]
            lines.append(cur[:-1])
            cur = moved + ch
            cur_w = measure(moved) + cw
            continue
        lines.append(cur)
        cur, cur_w = ch, cw
    if cur:
        lines.append(cur)
    return lines


class _NullPainter(object):
    """量算模式下的哑画笔：所有绘制调用都吞掉，只为跑出「会占多少页」。"""

    def __getattr__(self, name):
        return lambda *a, **k: None


class _Canvas(object):
    """在 QPdfWriter（dpi=720）或 QImage（预览，dpi 可调）上画页。"""

    def __init__(self, dpi=DPI, preview_dir=None, measure=False):
        self.dpi = dpi
        self.measure = measure
        self.k = dpi / 25.4                      # mm → px
        self.pt = dpi / 72.0                     # pt → px
        self.preview_dir = preview_dir
        self.page_w = 210 * self.k
        self.page_h = 297 * self.k
        self.ml = 25 * self.k
        self.mr = 15 * self.k
        self.mt = 25 * self.k
        self.mb = 20 * self.k
        self.text_w = self.page_w - self.ml - self.mr
        self.text_top = self.mt
        self.text_bottom = self.page_h - self.mb
        self.body_px = BODY_PT * self.pt
        self.lead = LEAD_PT * self.pt
        self.head_px = HEAD_PT * self.pt
        self.foot_px = FOOT_PT * self.pt
        self.family = _font_family()
        self._pdf = None
        self._path = None
        self.painter = None
        self.page_index = 0
        self._img = None

    # ---------- 设备 ----------
    def open(self):
        if self.measure:
            return                      # 量算模式：不建 PDF、不建图片
        if self.preview_dir:
            os.makedirs(self.preview_dir, exist_ok=True)
            return
        from PyQt5.QtGui import QPdfWriter
        fd, self._path = tempfile.mkstemp(suffix='.pdf', prefix='fenrir_app_')
        os.close(fd)
        self._pdf = QPdfWriter(self._path)
        self._pdf.setPageSizeMM(QSizeF(210, 297))
        self._pdf.setResolution(int(self.dpi))
        self._pdf.setCreator('Fenrir 专利写作助手')
        self._pdf.setTitle('专利申请文件')

    def begin_page(self):
        if self.measure:
            self.painter = _NullPainter()
            self.page_index += 1
            return
        if self.preview_dir:
            # 预览：一页一张 QImage，各自一个 painter
            self._img = QImage(int(round(self.page_w)), int(round(self.page_h)),
                               QImage.Format_RGB32)
            self._img.fill(QColor('#ffffff'))
            self.painter = QPainter(self._img)
        else:
            # PDF：整份文档共用一个 painter，翻页用 QPdfWriter.newPage()。
            # （每页都 end() 会把 PDF 收尾成单页文档，只留最后一页。）
            if self.painter is None:
                self.painter = QPainter(self._pdf)
            elif self.page_index:
                self._pdf.newPage()
        self.painter.setRenderHint(QPainter.TextAntialiasing, True)
        self.painter.setRenderHint(QPainter.Antialiasing, True)
        self.page_index += 1

    def end_page(self):
        if not self.painter:
            return
        if self.measure:
            self.painter = None
            return
        if self.preview_dir:
            self.painter.end()
            self.painter = None
            if self._img is not None:
                self._img.save(os.path.join(self.preview_dir,
                                            'page-%03d.png' % self.page_index))
                self._img = None

    def close(self):
        if self.measure:
            self.painter = None
            return b''
        if self.preview_dir:
            self.end_page()
            return b''
        if self.painter:
            self.painter.end()
            self.painter = None
        if self._pdf is not None:
            self._pdf = None        # 析构时 flush 到文件
            gc.collect()
        data = b''
        if self._path and os.path.exists(self._path):
            with open(self._path, 'rb') as fh:
                data = fh.read()
            try:
                os.remove(self._path)
            except OSError:
                pass
        return data

    # ---------- 字体 ----------
    def body_font(self, bold=False, size=None):
        f = QFont(self.family)
        f.setPixelSize(max(1, int(round(size or self.body_px))))
        f.setBold(bold)
        f.setHintingPreference(QFont.PreferFullHinting)
        return f

    # ---------- 页眉页脚 ----------
    def draw_frame(self, header, code, page_no):
        """横线 + 页眉 + 页脚。"""
        p = self.painter
        pen = QPen(QColor('#000000'))
        pen.setWidthF(max(1.0, 0.75 * self.pt / 10.0))
        p.setPen(pen)
        y = self.text_top
        p.drawLine(QPointF(self.ml, y), QPointF(self.ml + self.text_w, y))

        if header:
            f = self.body_font(size=self.head_px)
            p.setFont(f)
            fm = QFontMetricsF(f)
            w = fm.horizontalAdvance(header)
            # 页眉文字骑在横线上方：基线距横线约 1.4 字高
            base = self.text_top - 14.0 * self.pt
            p.drawText(QPointF(self.ml + (self.text_w - w) / 2.0, base), header)

        f = self.body_font(size=self.foot_px)
        p.setFont(f)
        fm = QFontMetricsF(f)
        base = self.page_h - 12 * self.k
        p.drawText(QPointF(self.ml, base), code)
        s = str(page_no)
        p.drawText(QPointF(self.ml + (self.text_w - fm.horizontalAdvance(s)) / 2.0,
                           base), s)
        p.drawText(QPointF(self.ml + self.text_w - fm.horizontalAdvance(VER),
                           base), VER)


class _DocWriter(object):
    """单份文档的流式排版：自动换页、页脚页码在同一份文档内连号。"""

    def __init__(self, canvas, key):
        self.c = canvas
        self.key = key
        self.header = DOC_NAMES[key]
        self.code = DOC_CODES[key]
        self.page_no = 0
        self.y = 0.0
        self.page_open = False

    def new_page(self):
        if self.page_open:
            self.c.end_page()
        self.c.begin_page()
        self.page_no += 1
        self.c.draw_frame(self.header, self.code, self.page_no)
        self.y = self.c.text_top + 12 * self.c.pt
        self.page_open = True

    def ensure(self, need):
        if not self.page_open or self.y + need > self.c.text_bottom:
            self.new_page()

    def finish(self):
        if self.page_open:
            self.c.end_page()
            self.page_open = False

    # ---- 基本行 ----
    def line(self, text, font=None, indent=0.0, align='left', lead=None):
        c = self.c
        f = font or c.body_font()
        lead = lead or c.lead
        self.ensure(lead)
        c.painter.setFont(f)
        fm = QFontMetricsF(f)
        base = self.y + fm.ascent()
        x = c.ml + indent
        if align == 'center':
            x = c.ml + (c.text_w - fm.horizontalAdvance(text)) / 2.0
        c.painter.setPen(QPen(QColor('#000000')))
        c.painter.drawText(QPointF(x, base), text)
        self.y += lead

    def para(self, text, font=None, indent_chars=0, numbering=None):
        """按正文宽度折行输出一段。numbering 为段号前缀（如 '[0001] '）。"""
        c = self.c
        f = font or c.body_font()
        m = _Measurer(f)
        body = text or ''
        if numbering:
            body = numbering + body
        max_w = c.text_w - indent_chars * c.body_px
        lines = wrap_text(body, m, max_w)
        first = True
        for ln in lines:
            self.ensure(c.lead)
            c.painter.setFont(f)
            fm = QFontMetricsF(f)
            x = c.ml + (indent_chars * c.body_px if first and indent_chars else 0)
            c.painter.setPen(QPen(QColor('#000000')))
            c.painter.drawText(QPointF(x, self.y + fm.ascent()), ln)
            self.y += c.lead
            first = False


# ============================ 对外接口 ============================

def _blank(text):
    return not (text or '').strip()


def _claims_text(item, idx):
    t = (item or '').strip()
    if not t:
        return ''
    # 已有「1.」「1、」「1．」编号就不再补
    head = t.lstrip()
    j = 0
    while j < len(head) and head[j].isdigit():
        j += 1
    if 0 < j < 6 and j < len(head) and head[j] in '.、．)）':
        return head
    return '%d. %s' % (idx, head)


def _emit_body(canvas, docs):
    """排「摘要 → 权利要求书 → 说明书 → 说明书附图」，返回各文档实际页数。"""
    counts = {}
    title = ((docs or {}).get('title') or '').strip()

    # ---- 1. 说明书摘要 ----
    abstract = [p for p in (docs.get('abstract') or []) if not _blank(p)]
    if abstract:
        w = _DocWriter(canvas, 'abs')
        w.new_page()
        for p in abstract:
            w.para(p.strip())
        w.finish()
        counts[DOC_CODES['abs']] = w.page_no

    # ---- 2. 权利要求书 ----
    claims = [p for p in (docs.get('claims') or []) if not _blank(p)]
    if claims:
        w = _DocWriter(canvas, 'claims')
        w.new_page()
        for i, p in enumerate(claims, 1):
            w.para(_claims_text(p, i))
        w.finish()
        counts[DOC_CODES['claims']] = w.page_no

    # ---- 3. 说明书 ----
    desc = [b for b in (docs.get('description') or [])
            if b and not _blank(b[1])]
    if desc:
        w = _DocWriter(canvas, 'desc')
        w.new_page()
        if title:
            tf = canvas.body_font(bold=True, size=canvas.head_px)
            w.line(title, font=tf, align='center',
                   lead=canvas.head_px * 1.9)
        num = 0
        for kind_, text in desc:
            text = (text or '').strip()
            if not text:
                continue
            if kind_ == 'h':
                w.line(text, font=canvas.body_font(bold=True))
                continue
            if text.startswith('['):
                # 已经带 [0001] 段号：沿用，并把计数器对齐
                k = text.find(']')
                if 0 < k <= 8:
                    try:
                        num = int(''.join(ch for ch in text[1:k] if ch.isdigit()))
                    except ValueError:
                        num += 1
                    w.para(text)
                    continue
            num += 1
            w.para(text, numbering='[%04d] ' % num)
        w.finish()
        counts[DOC_CODES['desc']] = w.page_no

    # ---- 4. 说明书附图 ----
    figs = [f for f in (docs.get('figures') or []) if f and f[1]]
    if figs:
        counts[DOC_CODES['draw']] = _write_figures(canvas, figs)

    return counts


def _measure(docs):
    """空跑一遍，只为拿到各文档会占多少页（请求书的文件清单要用）。"""
    c = _Canvas(measure=True)
    c.open()
    try:
        return _emit_body(c, docs)
    finally:
        c.close()


def write_document(docs, dpi=DPI, preview_dir=None):
    """把 docs 排成 PDF（或预览 PNG 目录），返回 PDF 字节（预览模式返回 b''）。"""
    docs = docs or {}
    req = docs.get('request') or None

    if req:
        # 请求书里要写「说明书共 N 页」，所以先量一遍正文与请求书自身
        from patent_request import fill_file_pages, write_request

        counts = _measure(docs)
        fill_file_pages(req, counts)
        c = _Canvas(measure=True)
        c.open()
        try:
            req['self_pages'] = write_request(c, req)
        finally:
            c.close()
        fill_file_pages(req, counts)

    canvas = _Canvas(dpi=dpi, preview_dir=preview_dir)
    canvas.open()
    try:
        if req:
            from patent_request import write_request
            write_request(canvas, req)       # 递交顺序：请求书在最前
        _emit_body(canvas, docs)
    finally:
        data = canvas.close()
    return data, canvas.page_index


def _write_figures(canvas, figs):
    """附图页：一页三图，图下标注「图 N」。"""
    c = canvas
    per_page = 3
    cell_h = (c.text_bottom - c.text_top) / float(per_page)
    label_h = c.lead * 1.7
    pad = 4 * c.pt
    page_no = 0
    c.begin_page()
    page_no += 1
    c.draw_frame(DOC_NAMES['draw'], DOC_CODES['draw'], page_no)
    for i, (label, blob) in enumerate(figs, 1):
        slot = (i - 1) % per_page
        if slot == 0 and i > 1:
            c.end_page()
            c.begin_page()
            page_no += 1
            c.draw_frame(DOC_NAMES['draw'], DOC_CODES['draw'], page_no)
        top = c.text_top + slot * cell_h + pad
        box_h = cell_h - label_h - pad
        img = QImage()
        if isinstance(blob, QImage):
            img = blob
        else:
            img = QImage.fromData(bytes(blob))
        if img.isNull():
            continue
        scale = min(c.text_w / float(img.width()), box_h / float(img.height()))
        w = img.width() * scale
        h = img.height() * scale
        x = c.ml + (c.text_w - w) / 2.0
        y = top + (box_h - h) / 2.0
        c.painter.drawImage(QRectF(x, y, w, h), img)
        f = c.body_font()
        c.painter.setFont(f)
        fm = QFontMetricsF(f)
        lab = label or ('图 %d' % i)
        c.painter.setPen(QPen(QColor('#000000')))
        c.painter.drawText(
            QPointF(c.ml + (c.text_w - fm.horizontalAdvance(lab)) / 2.0,
                    top + box_h + fm.ascent() + 2 * c.pt), lab)
    c.end_page()
    return page_no


def build_pdf(docs, dpi=DPI):
    """返回 (PDF 字节, 页数)。"""
    return write_document(docs, dpi=dpi)


def render_preview(docs, out_dir, dpi=150):
    """把同样的版式画成 PNG（调试/核对用，不进 PDF）。返回 (b'', 页数)。"""
    return write_document(docs, dpi=dpi, preview_dir=out_dir)

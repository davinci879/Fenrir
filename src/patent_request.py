# -*- coding: utf-8 -*-
"""专利申请请求书（110101 发明 / 120101 实用新型 / 130101 外观设计）的打印排版。

版式取自国知局「五书模板」打印稿：

    页面顶部：标题居中（字间留空）
    标题下：一行小字 —— 左「表格代码 版本 页码」，中「用户案卷号 …」，
            右「此框内容由国家知识产权局填写」
    再往下一条横线，横线以下是表格
    表格逐行绘制：每行 12 个单位宽，行内可自由分栏（官方表格本身逐行不同，
    例如「① 申请号」一行只有两格，「③ 申请日 / ② 分案提交日 / ④ 名称」是一行四格）
    行高随内容自动增高，写满一页自动续页（续页重画标题与小字，页码连号）

数据由 design_adjust_service 从请求书 XML 里抽好再传进来，本模块只负责画。
"""

from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtGui import QColor, QFontMetricsF, QPen

from patent_pdf import VER, _Measurer, wrap_text

UNITS = 12.0

TITLE_PT = 15.0
SMALL_PT = 7.5
LABEL_PT = 7.5
VALUE_PT = 9.0
SECTION_PT = 8.0
CHECK_PT = 7.5

LABEL_FILL = QColor('#f4f4f4')     # 栏目名浅底，打印接近白
SECTION_FILL = QColor('#ededed')
LINE_W = 0.5                       # pt

# 申请人类型代码 → 名称（国知局请求书填表说明）
APPLICANT_TYPES = {
    '1': '个人', '2': '大学', '3': '工矿企业',
    '4': '科研机构', '5': '机关团体', '6': '其他',
}

# 省级区划代码 → 名称（GB/T 2260），拼接申请人地址用
PROVINCES = {
    '110000': '北京市', '120000': '天津市', '130000': '河北省', '140000': '山西省',
    '150000': '内蒙古自治区', '210000': '辽宁省', '220000': '吉林省',
    '230000': '黑龙江省', '310000': '上海市', '320000': '江苏省', '330000': '浙江省',
    '340000': '安徽省', '350000': '福建省', '360000': '江西省', '370000': '山东省',
    '410000': '河南省', '420000': '湖北省', '430000': '湖南省', '440000': '广东省',
    '450000': '广西壮族自治区', '460000': '海南省', '500000': '重庆市',
    '510000': '四川省', '520000': '贵州省', '530000': '云南省', '540000': '西藏自治区',
    '610000': '陕西省', '620000': '甘肃省', '630000': '青海省',
    '640000': '宁夏回族自治区', '650000': '新疆维吾尔自治区', '710000': '台湾省',
    '810000': '香港特别行政区', '820000': '澳门特别行政区',
}

COUNTRY = {'CN': '中国', 'HK': '中国香港', 'MO': '中国澳门', 'TW': '中国台湾'}

# 带圈数字只到 ⑳，21 以上退回「(21)」写法
CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'


def _no(n):
    """栏目编号：①..⑳ 用带圈数字，㉑ 以后用 CJK 兼容带圈字符，再不够才退回 (n)。"""
    n = int(n or 0)
    if 1 <= n <= len(CIRCLED):
        return CIRCLED[n - 1]
    if 21 <= n <= 35:
        return chr(0x3250 + n - 20)      # ㉑ = U+3251
    return '(%d)' % n


def country_name(code):
    c = (code or '').strip().upper()
    return COUNTRY.get(c, code or '')


def applicant_type_name(code):
    c = (code or '').strip()
    return APPLICANT_TYPES.get(c, c)


def joined_address(ap):
    """省级名称 + 详细地址；市县代码没有通用字典，地址里已带区县时不再补。"""
    ap = ap or {}
    prov = PROVINCES.get((ap.get('prov') or '').strip(), '')
    detail = (ap.get('detail') or '').strip()
    if prov and detail.startswith(prov):
        return detail
    return (prov + detail) if prov else detail


class _Pager(object):
    """请求书的逐页绘制器。"""

    def __init__(self, canvas, req):
        self.c = canvas
        self.req = req or {}
        self.code = (self.req.get('code') or '110101').strip()
        self.title = self.req.get('head') or '专 利 请 求 书'
        self.case_no = (self.req.get('case_no') or '').strip()
        self.page_no = 0
        self.open = False
        self.y = 0.0

    # ---------- 页面 ----------
    def begin(self):
        self.new_page()

    def new_page(self):
        c = self.c
        if self.open:
            c.end_page()
        c.begin_page()
        self.page_no += 1
        self._head()
        self.open = True

    def _head(self):
        c = self.c
        p = c.painter
        pen = QPen(QColor('#000000'))
        p.setPen(pen)

        y = c.mt
        f = c.body_font(size=TITLE_PT * c.pt)
        p.setFont(f)
        fm = QFontMetricsF(f)
        p.drawText(QPointF(c.ml + (c.text_w - fm.horizontalAdvance(self.title)) / 2.0,
                           y + fm.ascent()), self.title)
        y += fm.height() + 1.4 * c.k

        fs = c.body_font(size=SMALL_PT * c.pt)
        p.setFont(fs)
        fms = QFontMetricsF(fs)
        p.drawText(QPointF(c.ml, y + fms.ascent()),
                   '%s %s %d' % (self.code, VER, self.page_no))
        if self.case_no:
            mid = '用户案卷号 %s' % self.case_no
            p.drawText(QPointF(c.ml + (c.text_w - fms.horizontalAdvance(mid)) / 2.0,
                               y + fms.ascent()), mid)
        right = '此框内容由国家知识产权局填写'
        p.drawText(QPointF(c.ml + c.text_w - fms.horizontalAdvance(right),
                           y + fms.ascent()), right)
        y += fms.height() + 1.6 * c.k

        lp = QPen(QColor('#000000'))
        lp.setWidthF(max(1.0, 0.75 * c.pt / 10.0))
        p.setPen(lp)
        p.drawLine(QPointF(c.ml, y), QPointF(c.ml + c.text_w, y))
        self.y = y

    def finish(self):
        if self.open:
            self.c.end_page()
            self.open = False

    # ---------- 行 ----------
    def _font(self, kind):
        c = self.c
        if kind == 'l':
            return c.body_font(size=LABEL_PT * c.pt)
        if kind == 's':
            return c.body_font(bold=True, size=SECTION_PT * c.pt)
        if kind in ('f', 'c'):
            return c.body_font(size=CHECK_PT * c.pt)
        return c.body_font(size=VALUE_PT * c.pt)
    def ensure(self, h):
        if not self.open or self.y + h > self.c.text_bottom:
            self.new_page()

    def row(self, cells, h=None):
        """一格一行。cells = [(单位宽, 文字, 类型[, 勾选态])]。"""
        c = self.c
        pad = 1.4 * c.k
        lead_k = 1.3
        need = 0.0
        wrapped = []
        for cell in cells:
            units, text, kind = cell[0], cell[1], cell[2]
            w = c.text_w * units / UNITS - 2 * pad
            f = self._font(kind)
            lines = wrap_text((text or ''), _Measurer(f), max(w, 1.0)) if text else ['']
            lh = QFontMetricsF(f).height() * lead_k
            need = max(need, len(lines) * lh)
            wrapped.append((cell, lines, f, lh))

        hh = h or max(7.2 * c.k, need + 2 * pad)
        self.ensure(hh)
        x = c.ml
        for cell, lines, f, lh in wrapped:
            units, text, kind = cell[0], cell[1], cell[2]
            chk = cell[3] if len(cell) > 3 else None
            w = c.text_w * units / UNITS
            self._cell(x, self.y, w, hh, text, kind, lines, f, lh, pad, chk)
            x += w
        self.y += hh

    def _cell(self, x, y, w, h, text, kind, lines, f, lh, pad, chk):
        c = self.c
        p = c.painter
        pen = QPen(QColor('#000000'))
        pen.setWidthF(max(0.9, LINE_W * c.pt / 10.0))
        p.setPen(pen)
        p.setBrush(QColor('#ffffff'))
        p.drawRect(QRectF(x, y, w, h))
        if kind == 'l':
            p.setBrush(LABEL_FILL)
            p.drawRect(QRectF(x, y, w, h))
        elif kind == 's':
            p.setBrush(SECTION_FILL)
            p.drawRect(QRectF(x, y, w, h))
        p.setBrush(QColor('transparent'))

        tx = x + pad
        avail = w - 2 * pad
        if chk is not None:
            box = 3.0 * c.k
            by = y + (h - box) / 2.0
            p.setPen(QPen(QColor('#000000')))
            p.setBrush(QColor('#ffffff'))
            p.drawRect(QRectF(tx, by, box, box))
            if chk:
                p.setPen(QPen(QColor('#000000'), max(1.0, 0.9 * c.pt / 10.0)))
                p.drawLine(QPointF(tx + box * 0.18, by + box * 0.52),
                           QPointF(tx + box * 0.42, by + box * 0.78))
                p.drawLine(QPointF(tx + box * 0.42, by + box * 0.78),
                           QPointF(tx + box * 0.86, by + box * 0.22))
                p.setPen(QPen(QColor('#000000')))
            p.setBrush(QColor('transparent'))
            tx += box + 1.4 * c.k
            avail -= box + 1.4 * c.k

        p.setFont(f)
        p.setPen(QPen(QColor('#000000')))
        fm = QFontMetricsF(f)
        total = len(lines) * lh
        ty = y + (h - total) / 2.0
        for ln in lines:
            if kind == 'vc':                    # 居中值（签章、机构名）
                p.drawText(QPointF(x + (w - fm.horizontalAdvance(ln)) / 2.0,
                                   ty + fm.ascent()), ln)
            else:
                p.drawText(QPointF(tx, ty + fm.ascent()), ln)
            ty += lh

    def section(self, title, h=None):
        self.row([(UNITS, title, 's')], h=h)


# ======================= 各页内容 =======================

def _page1(p, req):
    p.begin()
    kind_word = {'invention': '发明', 'utility': '实用新型', 'design': '外观设计'}
    kw = kind_word.get(req.get('kind'), '发明')

    p.row([(2.2, '%s 申请号' % _no(1), 'l'), (9.8, '', 'v')])
    p.row([(2.2, '%s 申请日' % _no(3), 'l'), (2.6, '', 'v'),
           (2.2, '%s 分案提交日' % _no(2), 'l'), (5.0, '', 'v')])
    p.row([(2.2, '%s %s名称' % (_no(4), kw), 'l'), (9.8, req.get('title') or '', 'v')])

    p.section('%s 发明人' % _no(5))
    p.row([(3.2, '姓名', 'l'), (2.2, '不公布姓名', 'l'),
           (1.8, '国籍或地区', 'l'), (4.8, '身份证件号码', 'l')])
    invs = req.get('inventors') or [{}]
    for inv in invs:
        p.row([(3.2, inv.get('name') or '', 'v'),
               (2.2, '', 'c', bool(inv.get('private'))),
               (1.8, country_name(inv.get('country')), 'v'),
               (4.8, inv.get('id') or '', 'v')])

    p.row([(UNITS, '全体申请人请求费用减缴且已完成费用减缴资格备案', 'c',
            bool(req.get('fee_reduction')))])

    p.section('%s 申请人' % _no(6))
    apps = req.get('applicants') or [{}]
    for i, ap in enumerate(apps, 1):
        p.row([(1.7, '申请人(%d)' % i, 'l'),
               (2.3, '姓名或名称', 'l'), (4.4, ap.get('name') or '', 'v'),
               (2.0, '申请人类型', 'l'), (1.6, applicant_type_name(ap.get('type')), 'v')])
        p.row([(3.6, '国籍或注册国家（地区）', 'l'), (2.8, country_name(ap.get('country')), 'v'),
               (1.8, '电子邮箱', 'l'), (3.8, ap.get('email') or '', 'v')])
        p.row([(4.0, '身份证件号码或统一社会信用代码', 'l'),
               (8.0, ap.get('id') or '', 'v')])
        p.row([(4.0, '经常居所地或营业所所在地', 'l'),
               (2.4, country_name(ap.get('business')), 'v'),
               (1.0, '电话', 'l'), (4.6, ap.get('phone') or '', 'v')])
        p.row([(4.0, '详细地址', 'l'), (5.6, joined_address(ap), 'v'),
               (1.2, '邮政编码', 'l'), (1.2, ap.get('zip') or '', 'v')])

    ct = req.get('contact') or {}
    p.section('%s 联系人' % _no(7))
    p.row([(1.4, '姓名', 'l'), (2.8, ct.get('name') or '', 'v'),
           (1.4, '电话', 'l'), (3.0, ct.get('phone') or '', 'v'),
           (1.6, '邮政编码', 'l'), (1.8, ct.get('zip') or '', 'v')])
    p.row([(1.4, '电子邮箱', 'l'), (4.4, ct.get('email') or '', 'v'),
           (1.6, '详细地址', 'l'), (4.6, joined_address(ct), 'v')])


def _agency_rows(p, req, no_clause):
    ag = req.get('agency') or {}
    p.section('%s 专利代理机构' % no_clause)
    p.row([(1.4, '名称', 'l'), (6.2, ag.get('name') or '', 'v'),
           (1.8, '机构代码', 'l'), (2.6, ag.get('code') or '', 'v')])
    p.row([(UNITS, '声明已经与申请人签订了专利代理委托书且本表中的信息与委托书中相应信息一致',
            'c', bool(ag.get('statement')))])
    p.row([(1.6, '代理师', 'l'), (2.6, '姓名', 'l'),
           (2.6, '资格证号', 'l'), (5.2, '电话', 'l')])
    agents = ag.get('agents') or []
    if not agents:
        agents = [{}]
    for i, a in enumerate(agents, 1):
        p.row([(1.6, '(%d)' % i, 'l'), (2.6, a.get('name') or '', 'v'),
               (2.6, a.get('cert') or '', 'v'), (5.2, a.get('phone') or '', 'v')])


def _priority_rows(p, req, no_clause):
    p.section('%s 要求优先权声明' % no_clause)
    p.row([(1.2, '序号', 'l'), (5.2, '原受理机构名称', 'l'),
           (2.8, '在先申请日', 'l'), (2.8, '在先申请号', 'l')])
    items = req.get('priority') or []
    for i in range(max(4, len(items))):
        it = items[i] if i < len(items) else {}
        p.row([(1.2, str(i + 1), 'v'), (5.2, it.get('office') or '', 'v'),
               (2.8, it.get('date') or '', 'v'), (2.8, it.get('number') or '', 'v')])


def _novelty_rows(p, req, no_clause):
    p.section('%s 不丧失新颖性宽限期声明' % no_clause)
    flags = req.get('novelty') or []
    for i, txt in enumerate((
            '已在国家出现紧急状态或者非常情况时，为公共利益目的首次公开',
            '已在中国政府主办或承认的国际展览会上首次展出',
            '已在规定的学术会议或技术会议上首次发表',
            '他人未经申请人同意而泄露其内容')):
        p.row([(UNITS, txt, 'c', bool(flags[i]) if i < len(flags) else False)])


def _page2(p, req):
    p.new_page()
    is_inv = req.get('kind') == 'invention'

    p.section('%s 代表人为非第一署名申请人时声明' % _no(8))
    rep = int(req.get('rep_index') or 0)
    p.row([(UNITS, '特声明第 %d 署名申请人为代表人' % (rep or 1), 'c', bool(rep and rep != 1))])

    n = 9
    _agency_rows(p, req, _no(n))

    n = 10
    p.section('%s 分案申请' % _no(n))
    div = req.get('divisional') or {}
    p.row([(3.0, '原申请号', 'l'), (3.0, div.get('origin') or '', 'v'),
           (3.4, '针对的分案申请号', 'l'), (2.6, div.get('target') or '', 'v')])
    p.row([(3.0, '原申请日', 'l'), (9.0, div.get('date') or '', 'v')])

    n = 11
    if is_inv:
        p.section('%s 生物材料样品' % _no(n))
        bio = req.get('bio') or {}
        p.row([(3.2, '保藏单位代码', 'l'), (3.0, bio.get('unit') or '', 'v'),
               (1.8, '是否存活', 'l'), (4.0, '是 / 否', 'v')])
        p.row([(3.2, '保藏日期', 'l'), (3.0, bio.get('date') or '', 'v'),
               (1.8, '保藏编号', 'l'), (4.0, bio.get('no') or '', 'v')])
        p.row([(3.2, '分类命名', 'l'), (8.8, bio.get('name') or '', 'v')])
        n += 1

        p.section('%s 序列表' % _no(n))
        p.row([(UNITS, '本专利申请涉及核苷酸或氨基酸序列表', 'c', bool(req.get('sequence')))])
        n += 1
        p.section('%s 遗传资源' % _no(n))
        p.row([(UNITS, '本专利申请涉及的发明创造是依赖于遗传资源完成的', 'c',
                bool(req.get('genetic')))])
        n += 1

    _priority_rows(p, req, _no(n)); n += 1
    _novelty_rows(p, req, _no(n)); n += 1

    if not is_inv:
        p.section('%s 援引加入声明' % _no(n))
        p.row([(UNITS, '本申请在递交日要求了优先权，声明以援引加入方式补交缺少或者错误提交的文件',
                'c', bool(req.get('join_by_ref')))]); n += 1

    p.section('%s 同日申请' % _no(n))
    p.row([(UNITS, req.get('same_day_text') or
            '声明本申请人对同样的发明创造在同日申请了另一类型专利', 'c',
            bool(req.get('same_day')))]); n += 1

    if is_inv:
        p.section('%s 提前公布' % _no(n))
        p.row([(UNITS, '请求早日公布该专利申请', 'c', bool(req.get('early_pub')))]); n += 1
        p.section('%s 请求实质审查' % _no(n))
        p.row([(UNITS, '根据专利法第 35 条的规定，请求对该专利申请进行实质审查', 'c',
                bool(req.get('sub_exam')))])
        p.row([(UNITS, '请求对本申请延迟审查，延迟期限为 1 年 / 2 年 / 3 年', 'c',
                bool(req.get('delay')))])
        p.row([(UNITS, '申请人声明，放弃专利法实施细则第 57 条规定的主动修改的权利', 'c',
                bool(req.get('waive_amend')))])
    else:
        p.section('%s 放弃主动修改权利' % _no(n))
        p.row([(UNITS, '申请人声明，放弃专利法实施细则第 57 条规定的主动修改的权利', 'c',
                bool(req.get('waive_amend')))]); n += 1
        p.section('%s 摘要附图' % _no(n))
        p.row([(UNITS, '指定说明书附图中的图 %s 为摘要附图' % (req.get('abs_figure') or '1'),
                'c', bool(req.get('abs_figure')))]); n += 1
        p.section('%s 延迟审查' % _no(n))
        p.row([(UNITS, '请求对本申请延迟审查，延迟期限为 1 年 / 2 年 / 3 年', 'c',
                bool(req.get('delay')))])


def _page3(p, req):
    if not p.open:                 # 上一页还有空位就接着排，别硬留半页空白
        p.new_page()
    is_inv = req.get('kind') == 'invention'
    n = 19 if is_inv else 18

    if is_inv:
        p.section('%s 摘要附图' % _no(n))
        p.row([(UNITS, '指定说明书附图中的图 %s 为摘要附图' % (req.get('abs_figure') or '1'),
                'c', bool(req.get('abs_figure')))]); n += 1
        p.section('%s 援引加入声明' % _no(n))
        p.row([(UNITS, '本申请在递交日要求了优先权，声明以援引加入方式补交缺少或者错误提交的文件',
                'c', bool(req.get('join_by_ref')))]); n += 1

    p.section('%s 申请文件清单' % _no(n))
    p.row([(1.2, '序号', 'l'), (7.4, '文件名称', 'l'),
           (2.0, '表格代码', 'l'), (1.4, '页数', 'l')])
    for i, f in enumerate(req.get('files') or [], 1):
        p.row([(1.2, str(i), 'v'), (7.4, f.get('name') or '', 'v'),
               (2.0, f.get('code') or '', 'v'),
               (1.4, '共 %s 页' % (f.get('pages') or ''), 'v')])
    p.row([(UNITS, '权利要求的项数：%s 项' % (req.get('claim_count') or 0), 'f')]); n += 1

    p.section('%s 附加文件清单' % _no(n))
    extras = req.get('extra_files') or []
    if extras:
        for i, f in enumerate(extras, 1):
            p.row([(1.2, str(i), 'v'), (7.6, f.get('name') or '', 'v'),
                   (3.2, '共 %s 页' % (f.get('pages') or ''), 'v')])
    else:
        p.row([(UNITS, '（无）', 'f')])
    p.row([(3.6, '总委托书（编号）', 'l'), (2.4, req.get('total_entrust') or '', 'v'),
           (3.2, '证明文件备案编号', 'l'), (2.8, req.get('record_no') or '', 'v')]); n += 1

    p.section('%s 代表人或专利代理机构' % _no(n))
    sign = req.get('sign') or {}
    p.row([(UNITS, sign.get('name') or (req.get('agency') or {}).get('name') or '', 'vc')],
          h=26 * p.c.k)
    date = ''
    if sign.get('y') or sign.get('m') or sign.get('d'):
        date = '%s 年 %s 月 %s 日' % (sign.get('y') or '', sign.get('m') or '',
                                      sign.get('d') or '')
    p.row([(UNITS, '签章日期：' + (date or '   年   月   日'), 'f')])


def write_request(canvas, req):
    """把请求书画在 canvas 上（接在已有内容之后），返回本次排版占的页数。"""
    p = _Pager(canvas, req)
    _page1(p, req)
    _page2(p, req)
    _page3(p, req)
    p.finish()
    return p.page_no


def fill_file_pages(req, counts):
    """把「申请文件清单」里的页数换成实际排版页数（XML 里的是申报时填的旧值）。"""
    counts = counts or {}
    self_code = (req.get('code') or '').strip()
    for f in req.get('files') or []:
        code = (f.get('code') or '').strip()
        if not code:
            continue
        if code == self_code and req.get('self_pages'):
            f['pages'] = req['self_pages']
        elif counts.get(code):
            f['pages'] = counts[code]

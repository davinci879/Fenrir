# -*- coding: utf-8 -*-
"""Fenrir「特殊字符」面板（重写版，独立于主窗口）。

旧实现在 main.py 里用 ``Label_Symbol(QLabel)`` 网格 + ``cursor.insertHtml()``，
实测存在这些缺陷：

* ``insertHtml('<>')`` 会被当成 HTML 标签，符号被整段吞掉；``&`` 等也可能被转义；
* 每个 QLabel 持有**创建时**的编辑器引用，切换文档后符号仍插进旧文档；
* 每次 F3 都重建整个 QWidget，搜索词/滚动位置/状态全丢，还泄漏旧窗口；
* 搜索只是 ``setVisible(False)``，网格留下空洞；无结果时没有任何提示；
* 希腊字母是「Αα」两个字符一起插入，单位字符串长度不一撑乱 5 列网格；
* 只能按符号本身匹配，无法按「约等于」「alpha」这类名称查找。

新实现：

* 面板只发 ``symbolChosen(text, caret_back)`` 信号，由主窗口取**当前**编辑器并用
  ``insertText`` 字面插入，既不会被 HTML 解析，也不会插错文档；
* 成对括号/引号插入后光标自动停在中间（caret_back=1）；
* 分类符号表带中文名 + 拼音/英文关键词，支持实时搜索、分组名搜索、空结果提示；
* 记录「最近使用」（QSettings 持久化），面板一次创建、反复 show/hide；
* 分组可折叠，网格按字符长度跨列、无空洞；支持 Esc 关闭、回车插入首个结果；
* 自带样式表，不依赖主窗口 QSS，也不会污染其它控件。

UI 重写（第二轮）：品牌头（徽标 / 统计 / 密度切换）、搜索框图标、
两行分类胶囊快捷筛选、卡片化 6 列网格、悬停预览条（大字符 + 中文名 +
Unicode 码点）、底部状态栏。新增收藏（★ 或右键，QSettings 持久化）、
复制到剪贴板而非插入、自定义符号增删、紧凑 / 舒适密度切换。动态分组
（最近使用 / 我的收藏 / 自定义）只在「全部 + 无搜索词」时显示，
且不计入 ``all_symbols()`` / ``visible_symbols()`` 的内置统计。

用法::

    panel = SpecialCharPanel()
    panel.symbolChosen.connect(main_window._insert_special_char)
    panel.closeRequested.connect(main_window.symbol_close)
    panel.move(x, y); panel.show()
"""

from collections import namedtuple

from PyQt5.QtCore import Qt, QEvent, QSettings, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit, QScrollArea,
                             QToolButton, QVBoxLayout, QWidget)
try:
    from frameless_resizable import FramelessResizableMixin
except ImportError:  # 以包方式导入时
    from .frameless_resizable import FramelessResizableMixin

Symbol = namedtuple('Symbol', 'char name keys caret')

# 每行 6 列；按钮按字符长度占 1~3 列，避免长单位串把网格撑乱
COLUMNS = 6
CELL_W = 36
CELL_H_COMFORT = 29
CELL_H_DENSE = 22
GRID_GAP = 3
PANEL_W = 272
RECENT_MAX = 12
HEADER_DRAG_H = 46

# 动态分组（由用户行为产生，不计入内置符号表、搜索时跳过以免重复格子）
DYNAMIC_TITLES = ('最近使用', '我的收藏', '自定义')

# 分类胶囊的短标签与主题色：272px 宽用两行放得下全部 9 个入口
CHIP_LABELS = {
    '常用符号': '常用', '成对括号': '括号', '数学与关系': '数学',
    '希腊字母': '希腊', '单位与上下标': '单位', '箭头': '箭头',
    '序号与编号': '序号', '几何与制表': '几何',
}
CATEGORY_COLORS = {
    '最近使用': '#e8a33d', '我的收藏': '#e2685f', '自定义': '#63b96b',
    '常用符号': '#4a8ae8', '成对括号': '#7e9ff0', '数学与关系': '#59b8c4',
    '希腊字母': '#a98ae8', '单位与上下标': '#d99a5b', '箭头': '#63b96b',
    '序号与编号': '#e08b9d', '几何与制表': '#8fa0b3',
}


class _SymbolButton(QToolButton):
    """符号格：仍是普通 QToolButton（objectName=SymbolCell），额外提供
    悬停预览与右键信号；左键点击与 ``b.click()`` 行为完全不变。"""

    hovered = pyqtSignal(object)
    altTriggered = pyqtSignal(object)

    def __init__(self, sym, parent=None):
        super().__init__(parent)
        self.setObjectName('SymbolCell')
        self.sym = sym
        self.setText(sym.char)

    def enterEvent(self, event):
        self.hovered.emit(self.sym)
        super().enterEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.altTriggered.emit(self.sym)
            event.accept()
            return
        super().mousePressEvent(event)

# 分类搜索关键词：搜「希腊」「arrow」「括号」也能命中整组
CATEGORY_KEYS = {
    '最近使用': 'zuijin recent history',
    '常用符号': 'changyong common law punctuation',
    '成对括号': 'kuohao bracket paren quote bracketpair',
    '数学与关系': 'shuxue math relation operator',
    '希腊字母': 'xila greek letter zimu',
    '单位与上下标': 'danwei unit superscript subscript',
    '箭头': 'jiantou arrow direction',
    '序号与编号': 'xuhao number circled roman',
    '几何与制表': 'jihe geometry box drawing table',
}

_STYLESHEET = """
QFrame#SpecialCharPanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #243240, stop:0.35 #202b36, stop:1 #1c2731);
    border: 1px solid #4a5a6b; border-radius: 8px; font-size: 12px;
}
/* 品牌头（徽标 / 标题 / 统计副标题）已按用户要求去除 */
QFrame#SpecialCharPanel QLabel#SymbolHint,
QFrame#SpecialCharPanel QLabel#SymbolEmpty {
    color: #8997a5; font-size: 11px;
}
QFrame#SpecialCharPanel QToolButton#SymbolClose {
    background: transparent; color: #a9b6c3; border: 1px solid transparent;
    border-radius: 4px; font-size: 12px;
}
QFrame#SpecialCharPanel QToolButton#SymbolClose { font-size: 16px; }
QFrame#SpecialCharPanel QToolButton#SymbolClose:hover {
    color: #ffffff; background: #34507a; border: 1px solid #4a8ae8;
}
QFrame#SpecialCharPanel QWidget#SymbolSearchBox {
    background: #19232d; border: 1px solid #3a4756; border-radius: 5px;
}
QFrame#SpecialCharPanel QLabel#SymbolSearchIcon { color: #6b7a8a; font-size: 14px; }
QFrame#SpecialCharPanel QLineEdit#SymbolSearch {
    background: transparent; color: #e6ecf2; border: none;
    padding: 3px 2px; font-size: 12px;
}
QFrame#SpecialCharPanel QWidget#SymbolCategoryBar { background: transparent; }
QFrame#SpecialCharPanel QToolButton#SymbolCategoryChip {
    background: #26333f; color: #a9b6c3; border: 1px solid #34414f;
    border-radius: 9px; padding: 2px 8px; font-size: 12px;
}
QFrame#SpecialCharPanel QToolButton#SymbolCategoryChip:checked {
    background: #34507a; color: #ffffff; border: 1px solid #4a8ae8;
}
QFrame#SpecialCharPanel QToolButton#SymbolCategoryChip:hover {
    border: 1px solid #4a8ae8; color: #ffffff;
}
QFrame#SpecialCharPanel QToolButton#SymbolSection {
    background: transparent; color: #8997a5; border: none;
    font-size: 12px; text-align: left; padding: 3px 2px; font-weight: bold;
}
QFrame#SpecialCharPanel QToolButton#SymbolSection:hover { color: #e6ecf2; }
QFrame#SpecialCharPanel QToolButton#SymbolClear {
    background: transparent; color: #8997a5; border: none; font-size: 11px;
}
QFrame#SpecialCharPanel QToolButton#SymbolClear:hover { color: #ffffff; }
QFrame#SpecialCharPanel QToolButton#SymbolCell {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2d3c4a, stop:1 #26333f);
    color: #e6ecf2; border: 1px solid #3a4756;
    border-radius: 4px; font-size: 16px; padding: 0px 2px;
}
QFrame#SpecialCharPanel QToolButton#SymbolCell:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #3f6396, stop:1 #34507a);
    color: #ffffff; border: 1px solid #6ba6f5;
}
QFrame#SpecialCharPanel QToolButton#SymbolCell:pressed { background: #2f6bc4; }
QFrame#SpecialCharPanel QScrollArea#SymbolScroll,
QFrame#SpecialCharPanel QWidget#SymbolBody,
QFrame#SpecialCharPanel QWidget#SymbolSectionBox {
    background: transparent; border: none;
}
QFrame#SpecialCharPanel QFrame#SymbolPreview {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1b2530, stop:1 #23303d);
    border: 1px solid #34414f; border-radius: 6px;
}
QFrame#SpecialCharPanel QLabel#SymbolPreviewChar {
    color: #8fd0ff; font-size: 28px; font-weight: bold;
}
QFrame#SpecialCharPanel QLabel#SymbolPreviewName { color: #e6ecf2; font-size: 12px; }
QFrame#SpecialCharPanel QLabel#SymbolPreviewCode {
    color: #8997a5; font-size: 10px;
}
QFrame#SpecialCharPanel QToolButton#SymbolPreviewAction {
    background: transparent; color: #a9b6c3; border: 1px solid #3a4756;
    border-radius: 4px; font-size: 13px;
    min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;
}
QFrame#SpecialCharPanel QToolButton#SymbolPreviewAction:hover {
    background: #34507a; color: #ffffff; border-color: #4a8ae8;
}
QFrame#SpecialCharPanel QToolButton#SymbolPreviewAction:checked {
    background: #5a4630; color: #ffd28a; border-color: #e8a33d;
}
"""


def _rows(spec):
    """把紧凑文本表解析为 Symbol 列表：字符 | 名称 | 关键词 | 光标回退位数。"""
    out = []
    for line in spec.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split('|')]
        ch = parts[0]
        name = parts[1] if len(parts) > 1 and parts[1] else ch
        keys = parts[2] if len(parts) > 2 else ''
        try:
            caret = int(parts[3]) if len(parts) > 3 and parts[3] else 0
        except ValueError:
            caret = 0
        out.append(Symbol(ch, name, keys, caret))
    return out


def _bulk(chars, name, keys='', caret=0):
    """单字符批量生成，位置序号写进名称便于按「①」或「序号1」查找。"""
    return [Symbol(c, '%s %d %s' % (name, i + 1, c), keys, caret)
            for i, c in enumerate(chars)]


def _greek():
    upper = 'ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ'
    lower = 'αβγδεζηθικλμνξοπρστυφχψω'
    names = ('alpha beta gamma delta epsilon zeta eta theta iota kappa '
             'lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega').split()
    out = []
    for i, en in enumerate(names):
        out.append(Symbol(upper[i], '希腊字母 %s 大写' % en,
                          '%s upper capital' % en, 0))
        out.append(Symbol(lower[i], '希腊字母 %s 小写' % en,
                          '%s lower small' % en, 0))
    return out


_CATEGORIES = (
    ('常用符号', _rows("""
、|顿号|dunhao comma
。|句号|juhao period
·|间隔号|jiangehao middle dot
—|破折号|pozhehao em dash
…|省略号|shengluehao ellipsis
％|百分号|baifenhao percent
‰|千分号|qianfenhao permille
§|章节号（法条引用）|zhangjiehao section law
¶|段落号|duanluohao paragraph
№|编号符|bianhaofu numero
©|版权符号|banquan copyright
®|注册商标|zhucesangbiao registered
™|商标符号|shangbiao trademark
℗|录音制品版权|luyinbanquan phonorecord
°|度|du degree
℃|摄氏度|sheshidu celsius
℉|华氏度|huashidu fahrenheit
±|正负号|zhengfu plusminus
×|乘号|chenghao multiply
÷|除号|chuhao divide
※|参考标记|cankao reference note
&|和号（HTML 实体符）|hehao ampersand and
<|小于号（HTML 敏感）|xiaoyu less than html
>|大于号（HTML 敏感）|dayu greater than html
""")),
    ('成对括号', _rows("""
（）|全角圆括号|quanjiao bracket|1
()|半角圆括号|banjiao paren|1
【】|方头括号|fangtou bracket|1
[]|方括号|fangkuohao bracket|1
《》|书名号|shuminghao|1
〈〉|单书名号|dan shuminghao|1
「」|直角引号|zhijiao quote|1
『』|双直角引号|shuang zhijiao quote|1
“”|双引号|shuangyinhao quote|1
‘’|单引号|danyinhao quote|1
｛｝|全角大括号|quanjiao brace|1
{}|大括号|dakuohao brace|1
＜＞|全角尖括号|jiankuohao angle|1
<>|半角尖括号（HTML 尖括号，光标不回退）|jiankuohao angle html
〔〕|六角括号|liujiao bracket|1
""")),
    ('数学与关系', _rows("""
≡|恒等于|hengdengyu identical
≌|全等于|quandengyu congruent
≈|约等于|yuedengyu approx
≠|不等于|budengyu neq
≤|小于等于|xiaoyudengyu leq
≥|大于等于|dayudengyu geq
≦|不大于等于|leq
≧|不小于等于|geq
∝|正比于|zhengbi proportional
∽|相似|xiangsi similar
∈|属于|shuyu in
∉|不属于|bushuyu notin
∅|空集|kongji emptyset
⊂|真包含于|subset
⊃|真包含|supset
⊆|包含于|subseteq
⊇|包含|supseteq
∪|并集|bingji union
∩|交集|jiaoji intersection
∑|求和|qiuhe sum
∏|求积|qiuji product
∫|积分|jifen integral
∮|闭合积分|bihe jifen
√|根号|genhao sqrt
∞|无穷大|wuqiong infinity
∠|角|jiao angle
⊥|垂直|chuizhi perpendicular
∥|平行|pingxing parallel
∵|因为|yinwei because
∴|所以|suoyi therefore
⇒|推出|tuichu implies
⇔|等价于|dengjia iff
∧|逻辑与|luojiyu and
∨|逻辑或|luojihuo or
¬|逻辑非|luojifei not
∂|偏导数|piandao partial
∇|梯度|tidu nabla
""")),
    ('希腊字母', _greek()),
    ('单位与上下标', _rows("""
¹|上标 1|superscript one
²|平方（上标 2）|pingfang superscript two square
³|立方（上标 3）|lifang superscript three
⁰|上标 0|superscript zero
ⁿ|上标 n|superscript n
₀|下标 0|subscript zero
₁|下标 1|subscript one
₂|下标 2|subscript two
₃|下标 3|subscript three
m²|平方米|pingfangmi m2 square meter
m³|立方米|lifangmi m3 cubic meter
cm²|平方厘米|cm2
cm³|立方厘米|cm3
kg/m³|千克每立方米|kg m3 density
g/cm³|克每立方厘米|g cm3 density
kW·h|千瓦时|kwh
m/s|米每秒|ms velocity
km/h|千米每小时|kmh
MPa|兆帕|zhaopa megapascal
kPa|千帕|qianpa kilopascal
dB|分贝|fenbei decibel
Ω|欧姆|oumu ohm
μ|微（微米/微法）|wei micro
Å|埃|ai angstrom
㎡|平方米符号|pingfangmi
㎥|立方米符号|lifangmi
""")),
    ('箭头', _rows("""
→|右箭头|rightarrow right
←|左箭头|leftarrow left
↑|上箭头|uparrow up
↓|下箭头|downarrow down
↔|左右双向箭头|leftrightarrow
↗|右上箭头|nearrow
↘|右下箭头|searrow
↖|左上箭头|nwarrow
↙|左下箭头|swarrow
⇄|左右互换箭头|leftrightarrows
⇆|反向双向箭头|leftleftarrows
⇒|推出箭头|Rightarrow
⇐|反推箭头|Leftarrow
⇔|等价箭头|Leftrightarrow
⟶|长右箭头|longrightarrow
""")),
    ('序号与编号', (
        _bulk(''.join(chr(0x2460 + i) for i in range(20)), '圈码', 'circled number')
        + _bulk(''.join(chr(0x2488 + i) for i in range(20)), '点号码', 'number dot')
        + _bulk('ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ', '罗马数字', 'roman numeral')
        + _bulk('⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽⑾⑿⒀⒁⒂', '括号数字', 'paren number')
        + _bulk('㈠㈡㈢㈣㈤㈥㈦㈧㈨㈩', '中文括号数字', 'chinese paren number'))),
    ('几何与制表',
     _rows("""
△|空心三角|triangle
▲|实心三角|triangle filled
▽|空心倒三角|triangle down
▼|实心倒三角|triangle down filled
□|空心方块|square
■|实心方块|square filled
◇|空心菱形|diamond
◆|实心菱形|diamond filled
○|空心圆|circle
●|实心圆|circle filled
◎|双圆环|circle double
⊙|带点圆|circle dot
★|实心五角星|star
☆|空心五角星|star outline
""") + _bulk('─│┌┐└┘├┤┬┴┼═║╔╗╚╝╬╭╮╰╯',
                        '制表符', 'box drawing table line')),
)


class SpecialCharPanel(FramelessResizableMixin, QFrame):
    """独立、无边框、可拖动 / 可缩放的特殊字符窗口；只发信号，不持有编辑器引用。

    缩放与拖动能力来自 ``FramelessResizableMixin``：四边 / 四角由 Windows
    原生命中测试处理，空白处按下可移动窗口，交互控件不抢拖拽。窗口放大时
    符号网格的列数会跟着增加（``_columns()``），不会把内容挤在左侧留大片空白。
    """

    symbolChosen = pyqtSignal(str, int)   # (要插入的文本, 插入后光标回退位数)
    closeRequested = pyqtSignal()

    def __init__(self, parent=None, persist=True):
        super().__init__(parent)
        self.setObjectName('SpecialCharPanel')
        self.setWindowTitle('')      # 去掉窗体标题
        # 独立窗口（不再置顶、不再停靠）：点击主窗口即可让它退到后面，
        # 不会压住正文；从四边 / 四角拖动缩放，从空白处拖动移动。
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_STYLESHEET)
        self.setMinimumSize(240, 280)
        self.resize(PANEL_W, 620)
        self._dragging = False
        self._drag_offset = None
        self._last_columns = None
        self._resize_timer = None

        self._settings = QSettings('Fenrir', 'SpecialChars') if persist else None
        self._recent = self._load_list('recent')[:RECENT_MAX]
        self._favorites = self._load_list('favorites')
        self._custom = self._load_list('custom')
        self._recent_dirty = False
        self._by_char = {}
        for _title, items in _CATEGORIES:
            for s in items:
                self._by_char.setdefault(s.char, s)

        self._collapsed = set()
        self._section_grids = {}
        self._first_match = None
        self._force_expand = False
        self._drag_offset = None
        self._active_category = None
        self._category_chips = {}
        self._dense = True    # 固定紧凑模式（密度切换已按需求移除）
        self._current_symbol = None
        self._build_ui()
        self._rebuild('')
        self._show_preview(None)

    # ---------------- 数据 ----------------
    @staticmethod
    def all_symbols():
        """全部内置符号（不含「最近使用」），供自测与统计。"""
        return [s for _t, items in _CATEGORIES for s in items]

    @staticmethod
    def categories():
        return [(t, list(items)) for t, items in _CATEGORIES]

    def _load_list(self, key):
        """QSettings 里的字符串列表；未开启持久化时永远返回空列表。"""
        if not self._settings:
            return []
        value = self._settings.value(key, [])
        if isinstance(value, str):
            value = [value]
        try:
            return [str(v) for v in value if str(v).strip()]
        except TypeError:
            return []

    def _save_list(self, key, values):
        if self._settings:
            self._settings.setValue(key, list(values))
            self._settings.sync()

    def _load_recent(self):
        """保留旧接口；内部统一走 _load_list。"""
        return self._load_list('recent')[:RECENT_MAX]

    def _remember(self, char):
        self._recent = ([char] + [c for c in self._recent if c != char])[:RECENT_MAX]
        self._save_list('recent', self._recent)
        self._recent_dirty = True

    def clear_recent(self):
        self._recent = []
        if self._settings:
            self._settings.remove('recent')
            self._settings.sync()
        self._rebuild(self._search.text())

    def clear_favorites(self):
        self._favorites = []
        self._save_list('favorites', self._favorites)
        self._rebuild(self._search.text())

    def toggle_favorite(self, char=None):
        """收藏 / 取消收藏；★ 按钮与符号格右键都会走这里。"""
        char = char or (self._current_symbol.char if self._current_symbol else None)
        if not char:
            return
        if char in self._favorites:
            self._favorites.remove(char)
        else:
            self._favorites.insert(0, char)
        self._save_list('favorites', self._favorites)
        self._show_preview(self._by_char.get(char) or Symbol(char, char, '', 0))
        if not self._search.text() and not self._active_category:
            self._rebuild('')

    def add_custom(self, text=None):
        """把常用字符串加入「自定义」分组（QSettings 持久化）。"""
        if text is None:
            text, ok = QInputDialog.getText(
                self, '自定义符号', '输入要加入面板的字符或字符串：')
            if not ok:
                return
        text = (text or '').strip()
        if not text or text in self._custom:
            return
        self._custom.insert(0, text)
        self._save_list('custom', self._custom)
        self._set_category('全部')

    def remove_custom(self, char):
        if char in self._custom:
            self._custom.remove(char)
            self._save_list('custom', self._custom)
            self._rebuild(self._search.text())

    def _data(self):
        """动态分组 + 内置分类。动态分组只在「全部」且无搜索词时显示，
        也不计入 ``visible_symbols`` / ``all_symbols`` 的内置统计。"""
        groups = []
        if self._recent:
            groups.append((
                '最近使用',
                [self._by_char.get(c) or Symbol(c, '最近使用 ' + c, '', 0)
                 for c in self._recent]))
        if self._favorites:
            groups.append((
                '我的收藏',
                [self._by_char.get(c) or Symbol(c, '我的收藏 ' + c, '', 0)
                 for c in self._favorites]))
        if self._custom:
            groups.append((
                '自定义',
                [Symbol(c, '自定义 ' + c, 'custom zidingyi', 0)
                 for c in self._custom]))
        groups.extend((t, items) for t, items in _CATEGORIES)
        return groups

    @staticmethod
    def _matches(sym, query):
        if not query:
            return True
        hay = ('%s %s %s' % (sym.char, sym.name, sym.keys)).lower()
        return query in hay or all(p in hay for p in query.split() if p)

    def visible_symbols(self, query=''):
        """按当前搜索词与分类筛选返回内置符号（与面板渲染保持一致）。"""
        q = (query or '').strip().lower()
        out = []
        for title, items in self._data():
            if title in DYNAMIC_TITLES:
                continue       # 动态分组是内置符号的重复入口，搜索时不重复计
            if self._active_category and title != self._active_category:
                continue
            cat_hit = q and (q in title.lower()
                             or q in CATEGORY_KEYS.get(title, '').lower())
            out.extend(items if (not q or cat_hit)
                       else [s for s in items if self._matches(s, q)])
        return out

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ① 去掉窗体标题：不再有徽标 / 标题 / 统计副标题这一行，
        #    省下的 46px 全给符号网格；统计信息仍在底部状态栏。
        #    密度固定为紧凑模式（不再提供 紧凑/舒适 切换），右侧只留关闭按钮。
        close_btn = QToolButton()
        close_btn.setObjectName('SymbolClose')
        close_btn.setText('×')
        close_btn.setToolTip('关闭（Esc）')
        close_btn.setFixedSize(22, 22)
        close_btn.clicked.connect(self.closeRequested.emit)

        # ② 搜索框（放大镜图标 + 清除按钮）+ 密度 / 关闭
        search_wrap = QWidget()
        sw = QHBoxLayout(search_wrap)
        sw.setContentsMargins(9, 7, 9, 5)
        sw.setSpacing(0)
        box = QWidget()
        box.setObjectName('SymbolSearchBox')
        bl = QHBoxLayout(box)
        bl.setContentsMargins(7, 0, 5, 0)
        bl.setSpacing(5)
        icon = QLabel('⌕')
        icon.setObjectName('SymbolSearchIcon')
        icon.setFixedWidth(14)
        self._search = QLineEdit()
        self._search.setObjectName('SymbolSearch')
        self._search.setPlaceholderText('搜索符号 / 中文名 / 拼音')
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(26)
        self._search.setToolTip('回车插入第一个匹配项，Esc 关闭面板')
        self._search.textChanged.connect(self._rebuild)
        self._search.returnPressed.connect(self._insert_first)
        self._search.installEventFilter(self)
        bl.addWidget(icon)
        bl.addWidget(self._search, 1)
        sw.addWidget(box, 1)
        sw.addSpacing(6)
        sw.addWidget(close_btn)
        root.addWidget(search_wrap)

        # ③ 分类胶囊：两行排下「全部 + 8 组」，无需横向滚动
        chips_box = QWidget()
        chips_box.setObjectName('SymbolCategoryBar')
        cv = QVBoxLayout(chips_box)
        cv.setContentsMargins(9, 0, 9, 5)
        cv.setSpacing(3)
        names = ['全部'] + [t for t, _ in _CATEGORIES]
        for start in (0, 5):
            row = QHBoxLayout()
            row.setSpacing(3)
            for t in names[start:start + 5]:
                b = QToolButton()
                b.setObjectName('SymbolCategoryChip')
                b.setText('全部' if t == '全部' else CHIP_LABELS.get(t, t))
                b.setCheckable(True)
                b.setChecked(t == '全部')
                b.setToolTip('显示全部符号' if t == '全部' else '只看「%s」分类' % t)
                b.clicked.connect(lambda checked=False, title=t:
                                  self._set_category(title))
                self._category_chips[t] = b
                row.addWidget(b)
            row.addStretch(1)
            cv.addLayout(row)
        root.addWidget(chips_box)

        # ④ 符号网格
        self._scroll = QScrollArea()
        self._scroll.setObjectName('SymbolScroll')
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._body = QWidget()
        self._body.setObjectName('SymbolBody')
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(0, 0, 0, 0)
        self._body_lay.setSpacing(7)
        self._body_lay.addStretch(1)
        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll, 1)

        # ⑤ 悬停预览条：大字符 + 中文名 + Unicode 码点 + 收藏/复制/自定义
        preview = QFrame()
        preview.setObjectName('SymbolPreview')
        preview.setFixedHeight(56)
        pl = QHBoxLayout(preview)
        pl.setContentsMargins(7, 4, 7, 4)
        pl.setSpacing(7)
        self._preview_char = QLabel('—')
        self._preview_char.setObjectName('SymbolPreviewChar')
        self._preview_char.setFixedWidth(44)
        self._preview_char.setAlignment(Qt.AlignCenter)
        pv = QVBoxLayout()
        pv.setSpacing(1)
        self._preview_name = QLabel('悬停或点击符号查看信息')
        self._preview_name.setObjectName('SymbolPreviewName')
        self._preview_code = QLabel('Unicode 码点 / 收藏 / 复制')
        self._preview_code.setObjectName('SymbolPreviewCode')
        pv.addWidget(self._preview_name)
        pv.addWidget(self._preview_code)
        pl.addWidget(self._preview_char)
        pl.addLayout(pv, 1)
        self._btn_fav = QToolButton()
        self._btn_fav.setText('★')
        self._btn_fav.setCheckable(True)
        self._btn_fav.setToolTip('收藏 / 取消收藏')
        self._btn_fav.clicked.connect(lambda: self.toggle_favorite())
        self._btn_copy = QToolButton()
        self._btn_copy.setText('⧉')
        self._btn_copy.setToolTip('复制符号到剪贴板（不插入正文）')
        self._btn_copy.clicked.connect(self.copy_current)
        self._btn_add = QToolButton()
        self._btn_add.setText('＋')
        self._btn_add.setToolTip('添加自定义符号 / 字符串')
        self._btn_add.clicked.connect(self.add_custom)
        for b in (self._btn_fav, self._btn_copy, self._btn_add):
            b.setObjectName('SymbolPreviewAction')
            b.setFixedSize(24, 24)
            pl.addWidget(b)
        preview_wrap = QWidget()
        pw = QHBoxLayout(preview_wrap)
        pw.setContentsMargins(8, 3, 8, 3)
        pw.setSpacing(0)
        pw.addWidget(preview)
        root.addWidget(preview_wrap)

        # ⑥ 底部状态栏（同时是明显的拖动抓手：QLabel 不拦截点击）
        self._hint = QLabel()
        self._hint.setObjectName('SymbolHint')
        self._hint.setContentsMargins(10, 0, 10, 7)
        self.set_drag_hint(self._hint)
        root.addWidget(self._hint)
        self.set_drag_hint(chips_box)

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            child = item.layout()
            if child is not None:
                SpecialCharPanel._clear_layout(child)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _columns(self):
        """按窗口宽度决定每行符号列数。

        默认 ``PANEL_W``(272px) 时算出来正好是 6 列，与固定宽度时代完全一致，
        所以既有布局 / 断言都不受影响；把窗口拖宽后每行能排下更多符号。
        """
        avail = max(CELL_W + GRID_GAP, self.width() - 36)
        return max(COLUMNS, min(18, avail // (CELL_W + GRID_GAP)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 只有列数真正变化才重排，且用 140ms 防抖，避免拖动窗口时反复重建网格
        if not hasattr(self, '_body_lay'):
            return
        cols = self._columns()
        if cols == self._last_columns:
            return
        self._last_columns = cols
        if self._resize_timer is None:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._relayout_for_width)
        self._resize_timer.start(140)

    def _relayout_for_width(self):
        try:
            pos = self._scroll.verticalScrollBar().value()
        except Exception:
            pos = 0
        self._rebuild(self._search.text())
        try:
            self._scroll.verticalScrollBar().setValue(pos)
        except Exception:
            pass

    def _rebuild(self, query=''):
        q = (query or '').strip().lower()
        # 搜索或指定了分类时强制展开所有分组；此时也隐藏动态分组，
        # 否则「最近使用 / 收藏」会把同一符号渲染两遍，搜索结果不再精确。
        self._force_expand = bool(q) or bool(self._active_category)
        self._section_grids = {}
        self._first_match = None
        self._clear_layout(self._body_lay)

        total = 0
        cell_h = CELL_H_DENSE if self._dense else CELL_H_COMFORT
        for title, items in self._data():
            if self._force_expand and title in DYNAMIC_TITLES:
                continue
            if self._active_category and title != self._active_category:
                continue
            cat_hit = q and (q in title.lower()
                             or q in CATEGORY_KEYS.get(title, '').lower())
            hits = (items if (not q or cat_hit)
                    else [s for s in items if self._matches(s, q)])
            if not hits:
                continue
            total += len(hits)
            collapsed = (not self._force_expand) and (title in self._collapsed)

            box = QWidget()
            box.setObjectName('SymbolSectionBox')
            vb = QVBoxLayout(box)
            vb.setContentsMargins(0, 0, 0, 0)
            vb.setSpacing(3)

            head_row = QHBoxLayout()
            head_row.setSpacing(2)
            head = QToolButton()
            head.setObjectName('SymbolSection')
            head.setText('%s ● %s  ·  %d' % ('▸' if collapsed else '▾',
                                             title, len(hits)))
            head.setToolTip('点击折叠 / 展开该分组')
            head.setCheckable(not self._force_expand)
            head.setChecked(not collapsed)
            head.setStyleSheet('color:%s;' %
                               CATEGORY_COLORS.get(title, '#8997a5'))
            head.clicked.connect(
                lambda checked, t=title: self._toggle_section(t, checked))
            head_row.addWidget(head)
            head_row.addStretch(1)
            if title in ('最近使用', '我的收藏'):
                clear = QToolButton()
                clear.setObjectName('SymbolClear')
                clear.setText('清空')
                clear.setToolTip('清空%s' % title)
                clear.clicked.connect(self.clear_recent if title == '最近使用'
                                      else self.clear_favorites)
                head_row.addWidget(clear)
            vb.addLayout(head_row)

            grid = QWidget()
            gl = QGridLayout(grid)
            gl.setContentsMargins(0, 0, 0, 0)
            gl.setSpacing(GRID_GAP)
            row = col = 0
            cols = self._columns()
            for sym in hits:
                span = 1 if len(sym.char) <= 2 else (2 if len(sym.char) <= 4 else 3)
                if col + span > cols:
                    col = 0
                    row += 1
                btn = _SymbolButton(sym)
                btn.setToolTip('%s\n左键插入 · 右键收藏/移除' % sym.name)
                btn.setFixedSize(span * CELL_W + (span - 1) * GRID_GAP, cell_h)
                if len(sym.char) > 2 or self._dense:
                    btn.setStyleSheet('font-size: %dpx;' %
                                      (11 if self._dense else 12))
                btn.clicked.connect(lambda checked=False, s=sym: self._emit(s))
                btn.hovered.connect(self._show_preview)
                btn.altTriggered.connect(self._on_cell_alt)
                gl.addWidget(btn, row, col, 1, span)
                if self._first_match is None:
                    self._first_match = sym
                col += span
                if col >= cols:
                    col = 0
                    row += 1
            vb.addWidget(grid)
            grid.setVisible(not collapsed)
            self._section_grids[title] = grid
            self._body_lay.addWidget(box)

        if total == 0:
            empty = QLabel('没有找到「%s」\n试试符号本身、中文名或拼音' % (query or ''))
            empty.setObjectName('SymbolEmpty')
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self._body_lay.addWidget(empty)
        self._body_lay.addStretch(1)
        # 窗口已经显示之后再重建（搜索、切换分类、拖宽窗口触发列数重排）时，
        # 新建的 QWidget 默认是 hidden，即便父布局可见也不会自动 show，结果是
        # 符号网格整片消失、几何还停在未布局的 640x480。初始构建因为随后有
        # 一次整体 show() 才看不出问题，所以这里必须显式补一次 show()。
        if self.isVisible():
            for _i in range(self._body_lay.count()):
                _w = self._body_lay.itemAt(_i).widget()
                if _w is not None:
                    _w.show()
        self._hint.setText('%s · 共 %d 个符号 · 左键插入 · 右键收藏 · Esc 关闭'
                           % (self._active_category or '全部', total))

    def _toggle_section(self, title, expanded):
        if self._force_expand:
            return
        if expanded:
            self._collapsed.discard(title)
        else:
            self._collapsed.add(title)
        grid = self._section_grids.get(title)
        if grid is not None:
            grid.setVisible(expanded)

    def _emit(self, sym):
        self._remember(sym.char)
        self._show_preview(sym)
        self.symbolChosen.emit(sym.char, int(sym.caret))

    def _insert_first(self):
        if self._first_match is not None:
            self._emit(self._first_match)

    # ---------------- 新增交互：分类 / 密度 / 预览 / 收藏 / 复制 ----------------
    def _set_category(self, title):
        self._active_category = None if title == '全部' else title
        for t, b in self._category_chips.items():
            b.setChecked((t == '全部' and self._active_category is None)
                         or t == self._active_category)
        self._rebuild(self._search.text())

    def toggle_density(self):
        """密度切换已移除：固定紧凑模式，保留空实现兼容旧调用。"""
        if not self._dense:
            self._dense = True
            self._rebuild(self._search.text())

    @staticmethod
    def _codepoints(text):
        pts = ['U+%04X' % ord(c) for c in text]
        return '  '.join(pts[:5]) + (' …' if len(pts) > 5 else '')

    def _show_preview(self, sym):
        self._current_symbol = sym
        if sym is None:
            self._preview_char.setText('—')
            self._preview_name.setText('悬停或点击符号查看信息')
            self._preview_code.setText('Unicode 码点 / 收藏 / 复制')
            self._btn_fav.setChecked(False)
            self._btn_fav.setEnabled(False)
            self._btn_copy.setEnabled(False)
            return
        self._btn_fav.setEnabled(True)
        self._btn_copy.setEnabled(True)
        self._preview_char.setText(sym.char)
        self._preview_name.setText(sym.name)
        self._preview_code.setText('%s  ·  %d 字符' %
                                   (self._codepoints(sym.char), len(sym.char)))
        self._btn_fav.setChecked(sym.char in self._favorites)

    def copy_current(self):
        """复制到剪贴板而不是插入正文（不改动编辑器）。"""
        if not self._current_symbol:
            return
        QApplication.clipboard().setText(self._current_symbol.char)
        self._hint.setText('已复制「%s」到剪贴板' % self._current_symbol.char)

    def _on_cell_alt(self, sym):
        # 自定义分组右键删除；其它符号右键收藏 / 取消收藏
        if sym.char in self._custom:
            self.remove_custom(sym.char)
        else:
            self.toggle_favorite(sym.char)

    # ---------------- 交互 ----------------
    def filter_symbols(self, query):
        """对外提供一次搜索（会同步刷新面板网格）。"""
        self._search.setText(query)

    def first_match(self):
        return self._first_match

    def showEvent(self, event):
        super().showEvent(event)
        if self._recent_dirty:
            self._recent_dirty = False
            self._rebuild(self._search.text())
        QTimer.singleShot(0, self._focus_search)

    def _focus_search(self):
        if self.isVisible():
            self._search.setFocus()
            self._search.selectAll()

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.KeyPress
                and event.key() == Qt.Key_Escape and obj is self._search):
            self.closeRequested.emit()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.closeRequested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    # 拖动 / 缩放统一由 FramelessResizableMixin 提供：窗口内任意非交互空白处
    # 可拖动，四边 / 四角走 WM_NCHITTEST。这里不再重写鼠标事件，避免抢走
    # 符号格点击、搜索框光标与分类按钮，也和「文本校验」窗口行为保持一致。

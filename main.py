# 将 src/ 加入模块搜索路径（其他模块仍在 src/ 下），并锁定 CWD 为项目根
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.join(_HERE, 'src'))
_os.chdir(_HERE)
"""
Fenrir 专利写作助手
管理多 tab 文本编辑器、附图标记补全、结构导航、查找替换、OCR、附图标记校验等核心功能。
"""
# 抑制 libpng iCCP 警告（C 层 fprintf 直接写 fd 2，Python 包装拦不住）
# 在 import 阶段临时关闭 fd 2，启动后恢复
import os as _os, sys as _sys
_fd2 = _sys.stderr.fileno() if hasattr(_sys.stderr, 'fileno') else 2
_devnull = _os.open(_os.devnull, _os.O_WRONLY)
_saved_fd2 = _os.dup(_fd2)
_os.dup2(_devnull, _fd2)  # 临时屏蔽
class _RestoreStderr:
    def __init__(self):
        self._restored = False
    def restore(self):
        if not self._restored:
            _os.dup2(_saved_fd2, _fd2)
            _os.close(_devnull)
            _os.close(_saved_fd2)
            self._restored = True
_stderr_restore = _RestoreStderr()
class _StderrFilter:
    def __init__(self, orig):
        self._orig = orig
    def write(self, s):
        if 'libpng' not in s and 'iCCP' not in s and 'cHRM' not in s:
            self._orig.write(s)
    def flush(self):
        self._orig.flush()
    def __getattr__(self, name):
        return getattr(self._orig, name)
_sys.stderr = _StderrFilter(_sys.stderr)

# 旧版「编辑图片 / 一键改图」是两个独立 QWidget 弹窗（txteditor_figeditor /
# txteditor_adjustimg_single），已由 design_adjust_service 内嵌的三个标签页取代。
from resources import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import qtawesome as qta
import icon_3d as _icon_3d
import formal_checks as fc  # 专利预审形式缺陷规则引擎（src/formal_checks.py）
import typo_detector        # 错别字识别模块：易混词表 + 同音误写（src/typo_detector.py）
import ai_check             # 火山方舟 AI 内容校验：配置 + Ark 请求 + 结果解析
from ai_settings_ui import AISettingsDialog  # 「工具 → 服务」里的 AI 接口设置
import sound_effects as sfx  # 按键音效：全局按钮咔哒声 + 校验结果节奏提示
from validation_ui import ScoreRing, SparkLine, level_color  # 校验面板自绘控件
from frameless_resizable import FramelessResizableMixin  # 无边框窗口：拖动 + 四边缩放
import html as _html  # 完整报告语法着色时转义正文，避免把 <> 当标签
# 统一接管全部按钮图标：qta.icon(...) 返回的仍是 QIcon，但经由 icon_3d
# 合成为带渐变/高光/斜边/投影的立体图标。用模块代理而不是改 90+ 处调用点，
# 既有 QAction / QPushButton / setIcon 逻辑一行都不用动；代理也保留了
# qtawesome 的其它属性，且不会污染其它模块拿到的原始 qtawesome。
qta = _icon_3d.wrap(qta)
import sys
import threading
import webbrowser
import urllib.request
import urllib.error
from urllib.parse import quote
import re
import os
import time
import csv
import io
import random
import win32api,win32gui
import design_adjust_service as design_service
import word_features as wf
import draft_store as store
import image_support as imgs
from completer_popup import CompleterPopup
from web_search_panel import SearchResultPanel
from special_chars import SpecialCharPanel, PANEL_W  # 重写版特殊字符面板 + 面板宽度

# 设计调整服务内嵌的功能标签页编号，与 design_adjust_service.py 内嵌页面的 tabN 对应
DESIGN_TAB_LABELS = {1: '调整外观图', 2: '附图标注', 3: 'XML 修改', 4: '特征关系分析'}

# 项目主页：帮助 / 软件更新 / 设置统一跳转
FENRIR_HOME_URL = 'https://github.com/davinci879'

# 分词词典，双击高亮功能用
SPLIT_TXT_1 = r'会能并如或与及的了和置有是为以个者在于行从果到可该从前后上下内外着过将时等且已经旦括含来够而[{\(（）\)，，。；:：;,、“”"‘’\'1234567890 \n'
SPLIT_TXT_2 = r'在以的等于中是该已如与和进及中为前后上下内外着时可或从会能并到来才，，。；;,.:：]}\)）\(（、“”"‘’\'1234567890 \n'

# 「预设格式」内置默认关键词表：一键格式(F5)据此自动加粗专利段落标题。
# 用户可在「批处理 → 文本整理 → 预设格式」中自定义，自定义内容存于
# data/settings.json 的 format_preset 字段；留空则回落到本表。不再使用任何 TXT 文件。
FORMAT_ARRAY_BASE = [
    '技术领域', '背景技术', '具体实施方式', '对于区别特征', '从结构上，',
    '从解决技术问题上，', '从技术启示上，', '本发明：', '本发明:',
    '解决的技术问题：', '本发明权利要求1请求保护的技术方案整体解决的技术问题是：',
    '区别技术特征分析', '发明内容', '实用新型内容', '附图说明',
    '审查员的主要观点答复', '重新确定的技术问题', '审查员认为：', '申请人认为：',
    '区别技术特征的确定', '非显而易见性论述', '本发明的有益效果', '本实用新型的有益效果',
    '创造性的意见陈述', '实际解决的技术问题：',
    '区别技术特征确定以及各区别技术特征所要实际解决的技术问题：',
    '区别技术特征确定以及各区别特征所要实际解决的技术问题：',
    '申请人：', '社会统一信用代码：', '地址：', '发明人：',
    '申请文件的修改', '尊敬的审查员：',
    '为实现上述目的，本发明提供了如下技术方案',
    '为实现上述目的，本发明采用了如下技术方案',
    '为实现上述目的，本实用新型提供了如下技术方案',
    '为实现上述目的，本实用新型采用了如下技术方案',
    '本发明：', '本实用新型：', '尊敬的复审和无效审理部', '尊敬的审查员',
    '一、无效宣告请求所针对的权利要求 ', '二、无效宣告理由', '引用的证据',
    '无效理由', '附图标记说明',
    '1.1', '1.2', '1.3', '2.1', '2.2', '2.3', '2.4', '3.1', '3.2',
]

# 文档标签页与附图标记列表一一对应。DOC_TAB_COUNT 是默认/最少的文档数，
# 标签栏末尾的「+」可按需新增到 MAX_DOC_TAB_COUNT 个（与旧版 30 存档序号对齐）。
# 文档数量持久化在 data/workspace.json 的名称个数里，重启后自动恢复。
DOC_TAB_COUNT = 10
MAX_DOC_TAB_COUNT = 30


class _MarkToolRow(QWidget):
    """标记面板底部常显工具行：排序分段器 + 同步状态开关。

    早期版本把三个按钮设为「不用时隐藏」，实际效果不好：
      · 排序方式、同步开关都是**当前生效的状态**，隐藏后看不出正在用哪一种；
      · hover 才浮出容易误触，鼠标进出还会闪一下；
      · 整行仍要留 24px 空白热区，其实并没有真正省下面板高度。
    因此改为常显，但把视觉重量压到最低：前两个互斥选项合成一个分段
    选择器，同步做成独立状态 chip；未选中一律透明描边，只有选中项着色，
    常显也不会抢走编辑区的注意力。按钮对象与信号全部复用，逻辑零改动。
    """

    def __init__(self, buttons, parent=None):
        super().__init__(parent)
        self.setObjectName('MarkToolRow')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(28)
        first, second, sync = buttons
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(6)

        lab = QLabel('排序')
        lab.setObjectName('MarkToolLabel')
        lay.addWidget(lab)

        seg = QWidget(self)
        seg.setObjectName('MarkSegmented')
        seg.setAttribute(Qt.WA_StyledBackground, True)
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(2, 2, 2, 2)
        seg_lay.setSpacing(0)
        for btn in (first, second):
            seg_lay.addWidget(btn, 1)          # 两段等宽，中间无缝
            btn.show()
        lay.addWidget(seg, 1)

        lay.addStretch(1)
        lay.addWidget(sync)
        sync.show()
        self._segment = seg


class _PlusTabBar(QTabBar):
    """末尾「+」占位页专用标签栏：按索引固定占位页宽度，不依赖 QSS 的 :last。

    不能用 QTabBar::tab:last 控制占位页样式。QTabBar 在 usesScrollButtons=True
    且发生横向滚动后，Qt 按 QStyleOptionTab::End 判定的 :last 会落到「可视区
    最后一个标签」上（占位页滚出可视区时即倒数第二个真实标签），于是：
      · DocTabs 最后一个新增文档被压成 0 宽，右键 tabAt 落到「+」页，
        「关闭当前文档」恒被禁用（表现为新增文档关不掉）；
      · MarkTabs 最后一个「列表N」被染蓝、压成 30px，显示成「列…」。
    tabSizeHint 是虚函数，按 index 直接返回宽度与滚动状态无关，最可靠。
    """
    def __init__(self, plus_width, parent=None):
        super().__init__(parent)
        self._plus_width = plus_width

    def tabSizeHint(self, index):
        if index == self.count() - 1:
            return QSize(self._plus_width, super().tabSizeHint(index).height())
        return super().tabSizeHint(index)


class _BookTabBar(QTabBar):
    """校验面板（问题清单 / 完整报告 / 对应表）的标签栏。

    QSS 用 `font-size: 13px` 指定标签字号时，QTabBar 的默认 sizeHint 是按
    控件字体（9pt ≈ 12px）算的，而实际绘制用的是 QSS 的 13px 字体。文字一宽
    就差几个像素，「问题清单 (11)」的右括号正好被切掉——截图里那个「(11」
    后面缺半边的现象。

    这里直接按 QFontMetrics 实测文字宽度，再留 12% + 36px 的余量（余量同时
    兜住 QSS 与控件字体不一致、以及不同 DPI 下的取整误差）。标签栏空间足够，
    宽一点不会挤。
    """

    PAD_X = 18          # 左右内边距（与 QSS 的 padding: 6px 14px 呼应）
    SAFETY = 1.12       # 文字宽度安全系数

    def tabSizeHint(self, index):
        base = super().tabSizeHint(index)
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.tabText(index))
        want = int(text_w * self.SAFETY) + self.PAD_X * 2
        return QSize(max(base.width(), want), base.height())


# ============ Word 2019 风格功能区 ============
class _RibbonGroup(QWidget):
    """功能区分组：上方按钮区，底部分组名，右侧细分隔线（Word 风格竖线）。"""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName('RibbonGroup')
        self._divider = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 2)
        outer.setSpacing(2)
        self.body = QHBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(2)
        # 按钮区靠上、组名压在最底部：行数不同的分组（如 2 行 vs 3 行）组名才对得齐，
        # 与 Word 功能区一致
        outer.addLayout(self.body)
        outer.addStretch(1)
        # 组名标签按用户要求删除（不再显示「校对/专利/文件/服务」等底部文字）

    def add(self, widget, colspan=0):
        self.body.addWidget(widget, colspan)

    def add_column(self, widgets, spacing=4):
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(spacing)
        for w in widgets:
            col.addWidget(w, 0, Qt.AlignLeft)
        col.addStretch(1)
        self.body.addLayout(col)

    def add_grid(self, widgets, columns=3, spacing=1):
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(spacing)
        for i, w in enumerate(widgets):
            grid.addWidget(w, i // columns, i % columns)
        self.body.addLayout(grid)

    def add_stretch(self):
        self.body.addStretch(1)

    def paintEvent(self, event):
        """自绘右侧分组分隔线：QSS 的 border-right 对 QWidget 子类不生效，
        直接画一条 1px 竖线，位置落在两个分组之间（各留 8px 内边距，视觉居中）。"""
        if not self._divider:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(QPen(QColor(PAL['mid']), 1))
        x = self.width() - 1
        p.drawLine(x, 5, x, self.height() - 4)
        p.end()


class _RibbonVLine(QWidget):
    """分组内部的竖直分隔线：把同一组里语义不同的控件隔成独立单元。

    线画在控件正中，宽度固定 9px，左右各留 4px 空隙——比分组之间的
    分隔线轻一档，既分得开又不会把功能区切得太碎。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(9)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(QPen(QColor(PAL['mid']), 1))
        x = self.width() // 2
        p.drawLine(x, 3, x, self.height() - 4)
        p.end()


# ========== 统一 UI 参数（调色板） ==========
# 全部 QSS 与内联样式的颜色统一由 PAL 取值：同一颜色只定义一次，调整配色
# 改这一处即可全局生效，不再以字面量散落数十处。QSS 内用 $token 引用
# （string.Template 替换；QSS 语法不含 $，不冲突），Python 侧内联样式用
# PAL['key']。近似色值已归并：#2f6fb3→accent、#4a76d6→accent_hi、
# #263440→raised、#2f4050→hover2、#44536a→frame、#3d4c5c→mid。
from string import Template

PAL = {
    # 背景
    'bg':              '#19232d',  # 深底：输入控件 / 编辑区 / 表格
    'panel':           '#202b36',  # 面板底：弹窗 / 菜单 / 校验面板
    'panel2':          '#1e2933',  # 功能区 / 状态栏底
    'panel_hi':        '#25323f',  # 功能区渐变亮端
    'raised':          '#26333f',  # 凸起控件：按钮 / 表头 / 标签页
    'hover':           '#2b3947',  # 悬停底
    'hover2':          '#2f4256',  # 悬停底（深一档）
    # 边框 / 分隔
    'border':          '#3a4756',  # 常规边框 / 分隔线
    'hairline':        '#34414f',  # 面板内细分隔线
    'frame':           '#45566a',  # 弹出面板外框（含原 #44536a）
    'frame_lo':        '#2c3744',  # 停靠面板内容边框（低对比发丝线）
    'line':            '#455364',  # 停靠分隔条 / 搜索框悬停边
    'line_hi':         '#60798b',  # 停靠分隔条悬停
    'mid':             '#4a5a6b',  # 滑块 / 指示器中灰（含原 #3d4c5c）
    'mid_hi':          '#5d708a',  # 滑块 / 状态栏滑块悬停
    # 主色（蓝）
    'accent':          '#2f6bc4',  # 选中背景 / 主按钮（含原 #2f6fb3）
    'accent_hover':    '#3b7ee0',  # 主按钮悬停
    'accent_hi':       '#4a8ae8',  # 亮阶：下划线 / 强调边框（含原 #4a76d6）
    'accent_soft':     '#34507a',  # 勾选 / 菜单选中的柔和底
    'accent_dn':       '#2a5a9e',  # 按下再深一档
    # 文字
    'text':            '#e6ecf2',  # 主文字
    'text_hi':         '#d7dee6',  # 次亮文字（复选框等）
    'text_mid':        '#c3cdd7',  # 次级文字
    'text_low':        '#a9b6c3',  # 弱文字
    'text_body':       '#dbe4ed',  # 正文/说明文字
    'text_inactive':   '#b7c4d0',  # 未选中标签页文字
    'text_dim':        '#8997a5',  # 分组标题等更弱文字
    'text_mute':       '#8fa0b3',  # 状态栏等弱文字
    'text_weak':       '#6b7a8a',  # 版本号等最弱文字
    'link':            '#8fd0ff',  # 「+」新建页 / 可点击提示
    # 特定用途
    'title_bg':        '#19232D',  # 停靠面板标题栏深蓝
    'summary_bg':      '#1b2530',  # 校验得分条底
    'grid':            '#2c3845',  # 表格网格线
    'search_bg':       '#1b2734',  # 标题栏搜索框底（比 bg 略蓝）
    'search_bg_hover': '#212e3b',
    'search_bg_focus': '#26323e',
    'search_border':   '#33414f',
    'white':           '#ffffff',
}
_QSS_TOKENS = PAL  # string.Template 替换用；字号/间距仍直接写字面量


# ============ Word 2019 风格「文件」后台视图 ============
class _BackstagePaper(QWidget):
    """模板卡片上的空白纸张：自绘浅灰文本线，模拟 Word 的文档缩略图。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(108, 132)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#f7f8fa'))
        p.setPen(QPen(QColor('#cfd7e0'), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor('#dde3ea'), 1))
        for i in range(6):
            y = 26 + i * 15
            p.drawLine(14, y, self.width() - (14 if i % 3 else 34), y)
        p.end()


class _BackstageCard(QWidget):
    """「新建」区的模板卡片：白纸 + 名称，整块可点。"""
    clicked = pyqtSignal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(108)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(_BackstagePaper(self))
        cap = QLabel(title)
        cap.setAlignment(Qt.AlignHCenter)
        cap.setStyleSheet('color:%s; font-size:13px;' % PAL['text'])
        lay.addWidget(cap)
        lay.addStretch(1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class BackstageView(QWidget):
    """覆盖在主窗口内容区之上的「文件」后台页（Word 2019 Backstage 风格）。

    左侧竖排导航：开始 / 新建 / 打开 / 信息 / 保存 / 另存为；右侧是主页、
    新建页与信息页。自身不碰业务，只发 actionTriggered / closeRequested。
    """
    actionTriggered = pyqtSignal(str)   # open / save / saveas / blank / recent:N
    closeRequested = pyqtSignal()

    NAV = (
        ('home', '开始'), ('new', '新建'), ('open', '打开'), (None, None),
        ('info', '信息'), ('save', '保存'), ('saveas', '另存为'), (None, None),
        ('history', '历史记录'),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('BackstageView')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet('QWidget#BackstageView { background: %s; }' % PAL['bg'])
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        nav = QWidget()
        nav.setObjectName('BackstageNav')
        nav.setFixedWidth(210)
        nav.setAttribute(Qt.WA_StyledBackground, True)
        nav.setStyleSheet('QWidget#BackstageNav { background: %s; }' % PAL['panel2'])
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(18, 18, 12, 18)
        nv.setSpacing(2)
        back = QToolButton()
        back.setText('←')
        back.setToolTip('返回文档（Esc）')
        back.setFixedSize(34, 34)
        back.setCursor(Qt.PointingHandCursor)
        back.setStyleSheet(
            'QToolButton { background: %s; color: %s; border: 1px solid %s;'
            ' border-radius: 17px; font-size: 17px; }'
            'QToolButton:hover { background: %s; }'
            % (PAL['raised'], PAL['text'], PAL['border'], PAL['hover2']))
        back.clicked.connect(self.closeRequested.emit)
        nv.addWidget(back, 0, Qt.AlignLeft)
        nv.addSpacing(20)

        self._nav_buttons = {}
        for key, label in self.NAV:
            if key is None:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFixedHeight(1)
                line.setStyleSheet('background: %s; border: none;' % PAL['border'])
                nv.addSpacing(8)
                nv.addWidget(line)
                nv.addSpacing(8)
                continue
            b = QPushButton(label)
            b.setFixedHeight(38)
            b.setCursor(Qt.PointingHandCursor)
            b.setEnabled(key != 'history')
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
            nv.addWidget(b)
            self._nav_buttons[key] = b
        nv.addStretch(1)
        root.addWidget(nav)

        self.stack = QStackedWidget()
        self.stack.setAttribute(Qt.WA_StyledBackground, True)
        self.stack.setStyleSheet('QStackedWidget { background: %s; }' % PAL['bg'])
        self._recent_box = None
        self._info_labels = {}
        self.stack.addWidget(self._build_home())
        self.stack.addWidget(self._build_new())
        self.stack.addWidget(self._build_info())
        root.addWidget(self.stack, 1)
        self.show_page('home')

    # ---------- 左栏 ----------
    def _paint_nav(self, active):
        for key, b in self._nav_buttons.items():
            if not b.isEnabled():
                b.setStyleSheet(
                    'QPushButton { background: transparent; color: %s; border: none;'
                    ' text-align: left; padding-left: 22px; font-size: 13px; }'
                    % PAL['text_weak'])
                continue
            common = ('border: none; text-align: left; padding-left: 22px;'
                      ' font-size: 13px; ')
            if key == active:
                b.setStyleSheet('QPushButton { background: %s; color: %s; %s}'
                                % (PAL['accent'], PAL['white'], common))
            else:
                b.setStyleSheet(
                    'QPushButton { background: transparent; color: %s; %s}'
                    'QPushButton:hover { background: %s; color: %s; }'
                    % (PAL['text_mid'], common, PAL['hover2'], PAL['white']))

    def _on_nav(self, key):
        if key in ('home', 'new', 'info'):
            self.show_page(key)
        elif key in ('open', 'save', 'saveas'):
            self.actionTriggered.emit(key)

    def show_page(self, key):
        self.stack.setCurrentIndex({'home': 0, 'new': 1, 'info': 2}.get(key, 0))
        self._paint_nav(key)

    # ---------- 右栏：控件工厂 ----------
    @staticmethod
    def _page_title(text):
        lab = QLabel(text)
        lab.setStyleSheet('color: %s; font-size: 26px; font-weight: 600;' % PAL['white'])
        return lab

    @staticmethod
    def _section_title(text):
        lab = QLabel(text)
        lab.setStyleSheet('color: %s; font-size: 16px; font-weight: 600;' % PAL['text_hi'])
        return lab

    @staticmethod
    def _rule():
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet('background: %s; border: none;' % PAL['hairline'])
        return line

    def _blank_card(self):
        card = _BackstageCard('空白文档')
        card.clicked.connect(lambda: self.actionTriggered.emit('blank'))
        return card

    def _build_home(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(48, 34, 48, 24)
        lay.setSpacing(0)
        lay.addWidget(self._page_title('晚上好'))
        sub = QLabel('今天想写点什么？')
        sub.setStyleSheet('color: %s; font-size: 13px;' % PAL['text_mute'])
        lay.addSpacing(6)
        lay.addWidget(sub)
        lay.addSpacing(30)
        lay.addWidget(self._section_title('⌄  新建'))
        lay.addSpacing(16)
        cards = QHBoxLayout()
        cards.setSpacing(24)
        cards.addWidget(self._blank_card())
        open_link = QPushButton('打开其他文档  →')
        open_link.setFlat(True)
        open_link.setCursor(Qt.PointingHandCursor)
        open_link.setStyleSheet(
            'QPushButton { color: %s; border: none; text-align: left;'
            ' font-size: 13px; padding: 0; }'
            'QPushButton:hover { color: %s; }' % (PAL['link'], PAL['accent_hi']))
        open_link.clicked.connect(lambda: self.actionTriggered.emit('open'))
        cards.addWidget(open_link, 0, Qt.AlignTop)
        cards.addStretch(1)
        lay.addLayout(cards)
        lay.addSpacing(28)
        lay.addWidget(self._rule())
        lay.addSpacing(22)
        lay.addWidget(self._section_title('最近'))
        lay.addSpacing(12)
        self._recent_box = QVBoxLayout()
        self._recent_box.setSpacing(4)
        lay.addLayout(self._recent_box)
        lay.addStretch(1)
        return page

    def _build_new(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(48, 34, 48, 24)
        lay.setSpacing(0)
        lay.addWidget(self._page_title('新建'))
        lay.addSpacing(10)
        hint = QLabel('从空白文档开始撰写，或返回打开已有文件。')
        hint.setStyleSheet('color: %s; font-size: 13px;' % PAL['text_mute'])
        lay.addWidget(hint)
        lay.addSpacing(28)
        lay.addWidget(self._section_title('⌄  可用模板'))
        lay.addSpacing(16)
        row = QHBoxLayout()
        row.setSpacing(24)
        row.addWidget(self._blank_card())
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return page

    def _build_info(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(48, 34, 48, 24)
        lay.setSpacing(0)
        lay.addWidget(self._page_title('信息'))
        lay.addSpacing(28)
        self._info_labels = {}
        for key, label in (('name', '当前文档'), ('path', '文件位置'),
                           ('count', '打开的文档数')):
            row = QHBoxLayout()
            row.setSpacing(16)
            k = QLabel(label)
            k.setFixedWidth(110)
            k.setStyleSheet('color: %s; font-size: 13px;' % PAL['text_mute'])
            v = QLabel('—')
            v.setStyleSheet('color: %s; font-size: 13px;' % PAL['text'])
            v.setWordWrap(True)
            row.addWidget(k)
            row.addWidget(v, 1)
            lay.addLayout(row)
            lay.addSpacing(14)
            self._info_labels[key] = v
        lay.addSpacing(16)
        lay.addWidget(self._rule())
        lay.addSpacing(18)
        tip = QLabel('提示：另存为可用 Ctrl+Shift+S；打开 / 保存 / 另存为也可从左侧导航直接执行。')
        tip.setStyleSheet('color: %s; font-size: 12px;' % PAL['text_dim'])
        lay.addWidget(tip)
        lay.addStretch(1)
        return page

    # ---------- 主窗口灌数据 ----------
    def set_recent(self, items):
        """items: [(名称, 路径或空), ...]，对应主窗口的文档标签页。"""
        box = self._recent_box
        if box is None:
            return
        while box.count():
            it = box.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        if not items:
            empty = QLabel('暂无文档')
            empty.setStyleSheet('color: %s; font-size: 13px;' % PAL['text_dim'])
            box.addWidget(empty)
        for i, (name, path) in enumerate(items[:8]):
            b = QPushButton('%s\n%s' % (name, path or '草稿 · 未保存到文件'))
            b.setFixedHeight(48)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                'QPushButton { background: transparent; color: %s; border: none;'
                ' border-bottom: 1px solid %s; text-align: left;'
                ' padding: 4px 8px; font-size: 13px; }'
                'QPushButton:hover { background: %s; }'
                % (PAL['text'], PAL['hairline'], PAL['hover']))
            b.clicked.connect(
                lambda checked=False, k=i: self.actionTriggered.emit('recent:%d' % k))
            box.addWidget(b)
        box.addStretch(1)

    def set_document_info(self, name, path, count):
        self._info_labels['name'].setText(name or '—')
        self._info_labels['path'].setText(path or '尚未保存到文件')
        self._info_labels['count'].setText(str(count))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.closeRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()

_RIBBON_QSS_TPL = """
/* QTabWidget 自身不能有底色：pane 左右默认内缩 3px，这段如果由控件自己
   刷 #19232d，功能区渐变两侧就会出现 3px 深色竖条。设为透明后由工具栏
   （RibbonHolder）的统一渐变透上来，左右边缘连成一片。 */
QTabWidget#RibbonTabs { background: transparent; border: 0px; padding: 0px; }
/* QTabWidget 内部的 QStackedWidget 铺满整个控件（含 pane 的 3px 内缩边），
   它自己刷 #19232d 时，功能区的渐变在这几条缝里就断成深色竖条。 */
QTabWidget#RibbonTabs QStackedWidget { background: transparent; border: 0px; }
QTabWidget#RibbonTabs::pane { border: 0; border-bottom: 1px solid $border; background: $panel2; }
QTabWidget#RibbonTabs QTabBar::tab {
    background: transparent; color: $text_low; padding: 4px 15px;
    border: none; border-bottom: 2px solid transparent; font-size: 13px;
}
QTabWidget#RibbonTabs QTabBar::tab:selected { color: $white; border-bottom: 2px solid $accent_hi; }
QTabWidget#RibbonTabs QTabBar::tab:hover { color: $white; background: $hover; }
/* ribbon 内所有按钮默认透明：让页面级「上深下浅」渐变透出，
   悬停/选中/按下仍给出高亮底（Word 风格） */
QTabWidget#RibbonTabs QToolButton, QTabWidget#RibbonTabs QPushButton {
    background: transparent; border: none; border-radius: 3px;
}
QTabWidget#RibbonTabs QToolButton:hover, QTabWidget#RibbonTabs QPushButton:hover { background: $hover; }
QTabWidget#RibbonTabs QToolButton:checked, QTabWidget#RibbonTabs QPushButton:checked { background: $accent_soft; }
QTabWidget#RibbonTabs QToolButton:pressed { background: $accent; }
QWidget#RibbonGroup { background: transparent; border: none; }
QWidget#RibbonRows { background: transparent; border: none; }
QLabel#RibbonGroupTitle { color: $text_dim; font-size: 11px; }
QToolButton#RibbonBig {
    color: $text; font-size: 12px; padding: 2px 6px;
}
/* 特殊字符：竖排（上图下字）小按钮，比 RibbonBig 窄一号，
   padding 压到 2px 才能把「特殊字符」四个字放进 58px 宽度 */
QToolButton#RibbonSym {
    color: $text; font-size: 11px; padding: 2px 2px;
}
QToolButton#RibbonSmall, QPushButton#RibbonSmall {
    color: $text_hi; font-size: 12px; text-align: left; padding: 1px 6px;
}
/* 纯图标按钮（开始→段落）：文字全省略，完整名称放 tooltip。
   padding 收窄才能让图标在小按钮里真正居中 */
QToolButton#RibbonIconOnly { color: $text_hi; padding: 1px 2px; }
QToolButton#RibbonCollapse {
    background: transparent; border: none; color: $text_low; font-size: 14px;
}
QToolButton#RibbonCollapse:hover { background: $hover2; color: $white; }
/* 标记面板底部常显工具行：排序分段器 + 同步状态开关。
   旧版三个独立立体按钮 + hover 浮出，视觉重且看不出前两个是互斥选项。
   现在未选中一律透明描边，只有生效项着色：常显也不抢编辑区注意力。 */
QWidget#MarkToolRow { background: transparent; }
QLabel#MarkToolLabel {
    background: transparent; color: $text_mute; font-size: 11px; padding: 0;
}
QWidget#MarkSegmented {
    background: $raised; border: 1px solid $border; border-radius: 5px;
}
QWidget#MarkSegmented QPushButton {
    background: transparent; border: none; border-radius: 4px;
    color: $text_mid; font-size: 12px; padding: 3px 8px; min-height: 20px;
}
QWidget#MarkSegmented QPushButton:hover { background: $hover2; color: $white; }
QWidget#MarkSegmented QPushButton:checked {
    background: $accent_soft; color: $white; font-weight: bold;
}
QPushButton#MarkSync {
    background: transparent; border: 1px solid $border; border-radius: 5px;
    color: $text_mid; font-size: 12px; padding: 3px 12px; min-height: 20px;
}
QPushButton#MarkSync:hover { background: $hover2; color: $white; }
QPushButton#MarkSync:checked {
    background: #2b5945; border: 1px solid #4f9e78;
    color: #e2f6ea; font-weight: bold;
}
QWidget#RibbonPage { background: $panel2; }
/* border/padding/margin 必须写成 0px：border:none 不参与 QStyleSheetStyle 的
   盒模型计算，QAbstractScrollArea 仍按样式默认的 2px 边框内缩视口，
   渐变两侧就会露出 2px 深色竖条。 */
QScrollArea#RibbonScroll { background: $panel2; border: 0px; padding: 0px; margin: 0px; }
QScrollArea#RibbonScroll QScrollBar:horizontal {
    height: 6px; background: transparent; margin: 0; border: none;
}
QScrollArea#RibbonScroll QScrollBar::handle:horizontal {
    background: $mid; border-radius: 3px; min-width: 36px;
}
QScrollArea#RibbonScroll QScrollBar::add-line:horizontal,
QScrollArea#RibbonScroll QScrollBar::sub-line:horizontal { width: 0; height: 0; }
QTabWidget#DocTabs QTabBar::tab {
    /* 不设 max-width：每个标签按文字自然宽度排开，字体/字号始终不变。
       窗口变窄时不压缩标签，超出部分在切换文档时由 QTabBar 自动滚入
       可视区（不再把 11 个标签一起挤成 34px、名字截成「…」）。 */
    padding: 5px 12px; min-width: 88px; color: $text_mid;
    background: $raised;
    border: 1px solid $border; border-bottom: none;
    border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 1px;
}
/* 不显示左右滚动箭头：scroller 与按钮尺寸归零、背景/边框透明，
   QStyleSheetStyle 不会再描出三角（离屏像素实测右端亮像素 60 → 0）。
   两个标签栏内部仍保留 usesScrollButtons=True：① QTabBar 的 minimumSizeHint
   不会把所有标签宽度相加（否则窗口/面板被顶宽、右边缘拉不动）；② 切换文档
   时选中标签会自动滚入可视区，左侧「列表N」不会再跑到屏幕外。 */
QTabWidget#DocTabs QTabBar::scroller,
QTabWidget#MarkTabs QTabBar::scroller { width: 0px; }
QTabWidget#DocTabs QTabBar QToolButton,
QTabWidget#MarkTabs QTabBar QToolButton {
    min-width: 0px; max-width: 0px; min-height: 0px; max-height: 0px;
    border: 0px; padding: 0px; margin: 0px; background: transparent;
}
QTabWidget#DocTabs QTabBar QToolButton:hover,
QTabWidget#MarkTabs QTabBar QToolButton:hover { background: transparent; }
QTabWidget#DocTabs QTabBar::tab:selected {
    /* 选中页与停靠面板标题栏同款深蓝（用户指定 #1c3a5c），
       外加一圈强调色高亮边框便于一眼定位当前文档 */
    background: $title_bg; color: $white;
    border: 1px solid $accent_hi; border-bottom: none;
}
QTabWidget#DocTabs QTabBar::tab:hover:!selected { background: $hover2; color: $text_body; }
QDockWidget { border: none; }
/* 停靠面板标题栏：深蓝色。qdarkstyle 的同名规则（background-color:#455364）
   优先级异常，无法被后追加的规则覆盖，已在 _load_app_stylesheet() 里整段剔除。 */
QDockWidget::title { background-color: $title_bg; border: none; padding: 3px 6px; }
/* 边框画在停靠面板的内容控件上，避免被内容控件覆盖（QDockWidget 自身边框常被子控件盖住） */
/* 用更低对比的 hairline 色，让边框视觉上更细（1px 已是实线最小宽度）；
   右缘不画——左侧停靠面板与正文之间会露出一条多余竖线（已删除），
   面板停靠到右侧时其左缘分隔线不受影响 */
QDockWidget > QWidget { border: 1px solid $frame_lo; border-right: 0px; }
QDialog, QMessageBox, QWidget#FenrirPopup { background: $panel; color: $text; }
QDialog QPushButton, QMessageBox QPushButton, QWidget#FenrirPopup QPushButton {
    min-width: 76px; padding: 5px 12px; border: 1px solid $frame;
    border-radius: 3px; background: $hover; color: $text;
}
QDialog QPushButton:hover, QMessageBox QPushButton:hover, QWidget#FenrirPopup QPushButton:hover {
    background: $accent_soft; border-color: $accent_hi;
}
QStatusBar { border: none; }
/* 停靠面板与编辑区之间的分隔条：2px 细线，保留可拖拽热区。
   注意：qdarkstyle 自带的同名规则（width/height 5px + padding 2px + image 图标）
   决定停靠区间隙，后面追加同名选择器覆盖不了它；已在 _load_app_stylesheet()
   里把原始规则整段剔除，本段是唯一生效的定义。 */
QMainWindow::separator {
    background-color: $line; border: none; padding: 0px; margin: 0px;
    spacing: 0px; image: none; width: 2px; height: 2px;
}
QMainWindow::separator:hover { background-color: $line_hi; }
/* 两个标签栏末尾「+」占位页的宽度由 _PlusTabBar.tabSizeHint() 按索引固定：
   DocTabs 为 0（真正可点的是右上角常驻按钮），MarkTabs 为 30px 的普通「+」页。
   这里绝不能再写 QTabBar::tab:last：横向滚动后 Qt 会把 :last 判给「可视区
   最后一个标签」，样式就会误套到倒数第二个真实文档/列表标签上。 */
QToolButton#DocAddTab {
    color: $link; font-size: 15px; font-weight: bold;
    background: $raised; border: 1px solid $border; border-bottom: none;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
    min-width: 26px; max-width: 30px; padding: 4px 6px; margin-right: 1px;
}
QToolButton#DocAddTab:hover { background: $accent_soft; color: $white; }
/* 统一右键菜单 / 提示条 / 原生弹窗的观感 */
QMenu { background: $panel; color: $text; border: 1px solid $border; padding: 4px; }
QMenu::item { padding: 5px 32px 5px 28px; border-radius: 3px; font-size: 12px; min-height: 18px; }
/* 特殊字符面板（重写版）样式表自带于 src/special_chars.py，
   这里不再定义 SymbolCell / SymbolBody，避免与面板自身 stylesheet 冲突。 */
QMenu::item:selected { background: $accent_soft; color: $white; }
QMenu::separator { height: 1px; background: $border; margin: 4px 8px; }
QMenu::icon { margin-left: 8px; margin-top: 3px; }
/* 有子菜单的条目右侧显示箭头（重新声明以覆盖全局样式表的优先级） */
QMenu::right-arrow {
    margin: 4px 6px 4px 4px; width: 12px; height: 12px;
    image: url(":/qss_icons/dark/rc/arrow_right.png");
}
QToolTip { background: $hover; color: $text; border: 1px solid $accent_hi; padding: 4px 6px; }
/* 滚动条与面板同色：细轨道 + 圆角滑块，去掉深色边框与上下箭头按钮 */
QScrollBar:horizontal { height: 10px; background: $panel; border: none; margin: 0; border-radius: 5px; }
QScrollBar:vertical { width: 10px; background: $panel; border: none; margin: 0; border-radius: 5px; }
QScrollBar::handle:horizontal { background: $mid; border: none; border-radius: 5px; min-width: 28px; }
QScrollBar::handle:vertical { background: $mid; border: none; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:horizontal:hover, QScrollBar::handle:vertical:hover { background: $mid_hi; }
/* 焦点态的滚动条滑块：去掉 qdarkstyle 默认的浅蓝 #1A72BB 描边（文本框左下角的浅蓝即来源于此）。
   放在 APP_QSS（拼接在 qdarkstyle 之后），用 border:none 覆盖其 focus 规则。 */
QScrollBar::handle:horizontal:focus, QScrollBar::handle:vertical:focus { border: none; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar QScrollBar::up-arrow, QScrollBar QScrollBar::down-arrow,
QScrollBar QScrollBar::left-arrow, QScrollBar QScrollBar::right-arrow { background: none; }
QMessageBox QLabel { color: $text; font-size: 12px; }
QMessageBox QLabel#qt_msgbox_informativelabel { color: $text_low; }
QFileDialog, QInputDialog { background: $panel; color: $text; }
/* 其余无边框弹出面板（替换 / 特殊符号 / 表格 / 联想框等）统一观感 */
QWidget#FenrirPopup { border: 1px solid $frame; border-radius: 5px; }
QWidget#FenrirPopup QLabel { color: $text_body; }
QWidget#FenrirPopup QLineEdit, QWidget#FenrirPopup QTextEdit,
QWidget#FenrirPopup QComboBox, QWidget#FenrirPopup QListWidget,
QWidget#FenrirPopup QTreeWidget, QWidget#FenrirPopup QTableWidget {
    background: $bg; color: $text; border: 1px solid $frame;
    border-radius: 3px; selection-background-color: $accent;
}
QWidget#FenrirPopup QCheckBox, QWidget#FenrirPopup QRadioButton { color: $text_hi; }
QWidget#FenrirPopup QTabWidget::pane { border: 1px solid $border; background: $panel; }
QWidget#FenrirPopup QTabBar::tab {
    background: $raised; color: $text_inactive; padding: 4px 12px; border: none;
}
QWidget#FenrirPopup QTabBar::tab:selected { color: $white; border-bottom: 2px solid $accent_hi; }
/* ===== 文本校验：品牌头 + 得分卡 + 卡片化结果页 ===== */
QWidget#ValidationPanel { background: $panel; border: 1px solid $frame; font-size: 12px; }
QFrame#ValidationFrame { background: $panel; border: none; }
/* 品牌头（logo / 标题 / 副标题）已按用户要求去掉，不再占用一行高度 */
QToolButton#ValidationClose {
    color: $text_low; border: none; font-size: 14px;
    min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;
}
QToolButton#ValidationClose:hover { color: $white; background: $accent_soft; border-radius: 4px; }
/* 音效开关：图标按钮，无边框；开关状态靠图标区分，不用颜色打扰视线 */
QToolButton#ValidationSfx {
    border: none; padding: 0;
    min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;
}
QToolButton#ValidationSfx:hover { background: $accent_soft; border-radius: 4px; }
QWidget#ValidationTools { background: $panel; border-bottom: 1px solid $hairline; }
QWidget#ValidationTools QPushButton,
QWidget#ValidationOptions QToolButton,
QWidget#ValidationReportPage QToolButton,
QWidget#ValidationLegendPage QToolButton {
    background: $raised; color: $text_mid; border: 1px solid $border;
    border-radius: 4px; padding: 4px 10px; font-size: 12px;
}
QWidget#ValidationTools QPushButton:hover,
QWidget#ValidationOptions QToolButton:hover,
QWidget#ValidationReportPage QToolButton:hover,
QWidget#ValidationLegendPage QToolButton:hover {
    background: $hover2; color: $white; border-color: $mid;
}
QPushButton#ValidationPrimary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $accent_hover, stop:1 $accent);
    color: $white; border: 1px solid $accent_hi; border-radius: 4px;
    padding: 4px 12px; font-size: 13px; font-weight: bold;
}
QPushButton#ValidationPrimary:hover { background: $accent_hover; }
QPushButton#ValidationPrimary:pressed { background: $accent_dn; }

QWidget#ValidationScoreWrap { background: $panel; }
QFrame#ValidationScoreCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 $summary_bg, stop:1 $panel);
    border: 1px solid $border; border-radius: 7px;
}
QLabel#ValidationSummary { color: $text; font-size: 14px; font-weight: bold; background: transparent; }
QLabel#ValidationMeta { color: $text_dim; font-size: 11px; }
QToolButton#ValidationLevelChip {
    background: $raised; color: $text_mid; border: 1px solid $border;
    border-radius: 10px; padding: 2px 9px; font-size: 12px;
}
QToolButton#ValidationLevelChip:checked {
    background: $accent_soft; color: $white; border: 1px solid $accent_hi;
}
QToolButton#ValidationLevelChip:hover { border-color: $accent_hi; }
QToolButton#ValidationIgnoredChip {
    background: transparent; color: $text_dim; border: 1px dashed $border;
    border-radius: 4px; padding: 2px 7px; font-size: 11px;
}
QToolButton#ValidationIgnoredChip:checked {
    background: $hover2; color: $white; border: 1px solid $mid;
}
QToolButton#ValidationDisclosure {
    background: transparent; color: $text_hi; border: none;
    font-size: 12px; font-weight: bold; padding: 1px 3px;
}
QToolButton#ValidationDisclosure:hover { color: $white; }
QToolButton#ValidationGhostButton {
    background: transparent; color: $text_mid; border: 1px solid $border;
    border-radius: 4px; padding: 3px 8px; font-size: 11px;
}
QToolButton#ValidationGhostButton:hover { background: $hover2; color: $white; }
QLineEdit#ValidationSearch {
    background: $bg; color: $text; border: 1px solid $border;
    border-radius: 4px; padding: 3px 8px; font-size: 12px;
}
QLineEdit#ValidationSearch:focus { border-color: $accent_hi; }
QComboBox#ValidationSort { font-size: 11px; padding: 2px 6px; }
QLabel#ValidationIssuesEmpty {
    color: $text_dim; font-size: 13px; padding: 18px 8px;
    background: $bg; border: 1px dashed $border; border-radius: 5px;
}

QTabWidget#ValidationTabs::pane { border: none; background: $panel; top: -1px; }
QTabWidget#ValidationTabs QTabBar::tab {
    background: transparent; color: $text_inactive; padding: 6px 14px;
    font-size: 13px; border: none; border-bottom: 2px solid transparent;
    margin-right: 3px;
}
QTabWidget#ValidationTabs QTabBar::tab:selected {
    color: $white; border-bottom: 2px solid $accent_hi;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $panel, stop:1 $panel_hi);
}
QTabWidget#ValidationTabs QTabBar::tab:hover:!selected { color: $text_hi; }
QWidget#ValidationIssuesPage, QWidget#ValidationReportPage { background: $panel; }
QTabWidget#ValidationTabs QTableWidget, QTabWidget#ValidationTabs QTextBrowser {
    background: $bg; color: $text_body; border: 1px solid $hairline;
    border-radius: 5px; font-size: 12px; gridline-color: $grid;
    selection-background-color: $accent_soft; selection-color: $white;
    padding: 2px;
}
QTabWidget#ValidationTabs QTableWidget::item { padding: 3px 5px; }
QTabWidget#ValidationTabs QHeaderView::section {
    background: $raised; color: $text_mid; border: none;
    border-right: 1px solid $hairline; padding: 5px 6px; font-size: 12px;
}
/* 对应表页：状态卡 + 工具条 + 表格 */
QWidget#ValidationLegendPage { background: $panel; }
QWidget#ValidationLegendStatus {
    background: $summary_bg; border: 1px solid $hairline; border-radius: 5px;
}
QLabel#ValidationLegendBadge {
    background: $accent_soft; color: $white; border-radius: 9px;
    padding: 2px 9px; font-size: 12px; font-weight: bold;
}
QLabel#ValidationLegendState { color: $text_mid; font-size: 12px; }
QWidget#ValidationLegendPage QPushButton {
    background: $raised; color: $text_mid; border: 1px solid $border;
    border-radius: 4px; padding: 3px 9px; font-size: 12px;
}
QWidget#ValidationLegendPage QPushButton:hover { background: $hover2; color: $white; }
QWidget#ValidationLegendPage QComboBox,
QWidget#ValidationLegendPage QLineEdit { font-size: 12px; }
QLabel#ValidationLegendHint { color: $text_dim; font-size: 12px; padding: 0px 2px; }
/* 底部检查项抽屉 */
QWidget#ValidationOptions { background: $panel; border-top: 1px solid $hairline; }
QWidget#ValidationChecksBox QCheckBox { color: $text_mid; font-size: 12px; spacing: 4px; }
QWidget#ValidationChecksBox QCheckBox::indicator { width: 13px; height: 13px; }
/* ========== UI 美化：统一控件观感 ========== */
/* 下拉框（焦点边框已弱化为常色） */
QComboBox {
    background: $raised; color: $text; border: 1px solid $border;
    border-radius: 3px; padding: 3px 8px; min-height: 18px;
}
QComboBox:hover { border-color: $mid; }
QComboBox:focus, QComboBox:on { border-color: $border; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox::down-arrow {
    /* SVG data URL 里的 %238fa0b3 即 text_mute（URL 编码的 #），无法用模板令牌。
       url() 必须用双引号包住：未加引号的 url 值里含空格是非法 CSS 语法，
       Qt 解析器会直接放弃【整张】样式表（曾致全局样式静默失效）。 */
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M0 0l5 6 5-6z' fill='%238fa0b3'/></svg>");
    width: 10px; height: 6px; margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: $panel; color: $text; border: 1px solid $border;
    selection-background-color: $accent; outline: none;
}
/* 输入框：边框常色（焦点不再发蓝） */
QLineEdit, QTextEdit, QPlainTextEdit {
    background: $bg; color: $text; border: 1px solid $border;
    border-radius: 3px; padding: 2px 4px; selection-background-color: $accent;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: $border; }
/* 主编辑框（带行号/右缘波形的那个）：右侧不留 padding，viewport 直接顶到
   边框，右缘波形才贴得住；其余输入框保持 4px 内缩不变。 */
QTextEditWithLineNum {
    background: $bg; color: $text; border: 1px solid $border;
    border-radius: 3px; padding: 2px 0px 2px 4px;
    selection-background-color: $accent;
}
/* 文档标签栏（与上方合并后的主定义衔接）：选中页顶部圆角 + 底色融入 */
QTabWidget#DocTabs::pane { border: none; border-top: 1px solid $border; background: $bg; }
/* 标记面板：qdarkstyle 给 QTabWidget::pane 画一圈 #455364 外框，与编辑框
   自身的 $border 边框叠成「双边框」。去掉 pane 外框，只留编辑框一圈单边框。 */
QTabWidget#MarkTabs::pane { border: 0px; }

/* 复选框 / 单选框 */
QCheckBox, QRadioButton { color: $text_hi; spacing: 6px; background: transparent; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 14px; height: 14px; border: 1px solid $mid; border-radius: 3px;
    background: $bg;
}
QRadioButton::indicator { border-radius: 7px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: $accent; border-color: $accent_hi;
}
/* 表格头 */
QHeaderView::section {
    background: $raised; color: $text_mid; border: none;
    border-right: 1px solid $hairline; border-bottom: 1px solid $hairline;
    padding: 4px 8px; font-size: 11px; font-weight: normal;
}
/* 状态栏 */
QStatusBar { background: $panel2; color: $text_mute; border-top: 1px solid $border; }
QStatusBar QLabel { color: $text_mute; padding: 0 6px; }
/* 按钮按下反馈 */
QToolButton:pressed, QPushButton:pressed { background: $accent_dn; }
"""

# 状态栏专用样式由 word_features 提供，追加到全局样式表末尾
RIBBON_QSS = Template(_RIBBON_QSS_TPL).substitute(_QSS_TOKENS)
RIBBON_QSS += wf.STATUS_QSS

# ========== 应用样式（固定深蓝配色 + 细微渐变纹理） ==========
# 主题选择功能已移除，全应用统一使用这一套配色，不再读取/写入主题设置。
# 功能区背景为纯 QSS 线性渐变（不依赖外部图片）：「上深下浅」过渡色——
# 顶端 $bg（#19232d，与「开始/插入/批处理」标签栏行背景同色，实测采样确认），
# 过渡到底端 $hover（浅）。渐变只画在 RibbonPage 一层上，
# 滚动容器/视口/分组/按钮行/按钮全部透明，保证整条功能区呈现同一张渐变。
# 停靠面板标题栏不用渐变：Qt 对 subcontrol 的 qlineargradient 不绘制背景，
# 实测会退化成透明；已统一在 RIBBON_QSS 里用纯色 $title_bg 定义
# （同名规则只保留一条，避免 qdarkstyle 抢先生效）。
_APP_QSS_EXTRA_TPL = (
    "QWidget#RibbonPage { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 $bg, stop:1 $hover); }"
    "QTabWidget#RibbonTabs::pane { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 $bg, stop:1 $hover); }"
    "QScrollArea#RibbonScroll { background: transparent; border: 0px; padding: 0px; margin: 0px; }"
    "QScrollArea#RibbonScroll > #qt_scrollarea_viewport { background: transparent; }"
)
APP_QSS = RIBBON_QSS + Template(_APP_QSS_EXTRA_TPL).substitute(_QSS_TOKENS)

# 标题栏控件样式（原散落在各处的内联 setStyleSheet 统一收拢至此）
APP_QSS += Template("""
/* 顶部网络搜索框：高 22px、border-radius 11px=高度一半 → 两端全圆的椭圆（胶囊）形 */
QLineEdit#TopSearch {
    background-color: $search_bg; color: $text;
    border: 1px solid $search_border; border-radius: 11px;
    padding-left: 2px; padding-right: 4px;
    selection-background-color: $accent_hi;
}
QLineEdit#TopSearch:hover { background-color: $search_bg_hover; border-color: $line; }
QLineEdit#TopSearch:focus { background-color: $search_bg_focus; border-color: $border; }
/* Fenrir 的字重由 MainWindow 里显式设置的 QFont.Black(87) 控制，这里刻意
   不写 font-weight：QStyleSheetStyle 在 polish 时会用样式表的字重覆盖控件
   字体，写 bold 只会把 Black 压回 75，视觉上仍偏细。颜色/字号/内边距照旧。 */
QLabel#BrandLabel { color: $white; font-size: 14px; padding-left: 4px; padding-bottom: 0px; }
QLabel#VersionLabel { color: $text_weak; font-size: 12px; padding-left: 5px; padding-right: 10px; padding-top: 1px; }
/* 顶部标题栏中部的当前文档名（原底部状态栏左侧的「文档1」） */
QLabel#TopDocTitle {
    background: transparent; color: $text;
    font-size: 13px; font-weight: 600; padding: 0 6px;
}
""").substitute(_QSS_TOKENS)


class _UrlProbe(QObject):
    """后台线程探测 URL 可达性，结果经信号排队回 UI 线程。

    用于「打开内网服务」类按钮：先以指定超时探测一次，可达才交给系统
    浏览器，避免打开一个一直转圈的白页；探测期间 UI 线程完全不阻塞。
    """
    finished = pyqtSignal(bool, str)          # (是否可达, 错误描述)

    def __init__(self, url, timeout, parent=None):
        super().__init__(parent)
        self._url = url
        self._timeout = timeout

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        ok, err = True, ''
        try:
            # 内网地址不走系统代理：代理拦内网请求会误报 502/超时
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}))
            req = urllib.request.Request(
                self._url, headers={'User-Agent': 'Fenrir'})
            with opener.open(req, timeout=self._timeout) as resp:
                resp.read(1024)               # 只读一小段确认真的有响应
        except urllib.error.HTTPError:
            pass      # 服务器已给出 HTTP 应答即视为可达（页面级错误浏览器自会显示）
        except Exception as e:                # 超时/拒绝连接/DNS 失败都算不可达
            ok, err = False, str(e) or type(e).__name__
        self.finished.emit(ok, err)


class MainWindow(QMainWindow):
    # 下角热区边长（px）。光标提示与按下后的 drag_flag 判定共用这一个值，
    # 避免「显示对角箭头、拖起来却只能水平/竖直缩放」的不一致。
    CORNER_SIZE = 16
    # 状态栏最底部可竖直拖拽缩放的窄带宽度（px）。离屏实测状态栏高 28px，
    # 最底部 4px 全是 QStatusBar 自身、无子控件遮挡；从 dy=5 起会被状态栏右侧
    # 的缩放按钮 / 滑块覆盖，事件到不了状态栏。取 4px 既贴合「底边框」语义，
    # 又不把整个状态栏变回拖拽热区。
    STATUS_BOTTOM_GRIP = 4
    # 「文件」是功能区选项卡行的第一个 tab，不承载页面：
    # 点击它打开后台视图，currentIndex 永远不落在它身上。
    FILE_TAB_INDEX = 0
    # 启动时左侧停靠区占窗口宽度的比例。Qt 默认按 QDockWidget 内容的 sizeHint
    # 分配宽度，会随字体 / DPI 变化（本机离屏实测 21.4% ~ 39.2%），因此显式指定，
    # 见 _apply_initial_dock_ratio()。
    DOCK_INITIAL_RATIO = 0.20

    def __init__(self):
        super().__init__()
        # 监听主窗口自身的鼠标按下，保证工具浮窗不被主窗口遮挡
        self.installEventFilter(self)
        self.FONT_SIZES = [4,5,6,7, 8, 9, 10, 11, 12, 13, 14, 18, 24,30,36,42,48,54,60,66,72,78,84,90,96]
        self.LINE_HEIGHT = ['0.0','0.2','0.5','1.0','1.5','2.0','2.5','3.0','3.5','4.0']
        self.HTML_EXTENSIONS = ['.htm', '.html']
        self.rename_history_array = ['发明 => 实用新型','实用新型 => 发明','所述的 => ','所述 => ','^p^p => ^p',', => ，','( => （',') => ）']
        self.path = None
        self.start_drag_pos = (0,0)
        self.tab_drag_flag = False
        self.window_notebook = ''
        self.dock_validation = None      # 兼容字段：文本校验已改为独立窗口，无停靠容器
        self.fig_dic = {}
        # 联想补全弹窗（附图标记 / 关键词共用，全会话复用，不再每次按键 new 一个）
        self._completion_popup = CompleterPopup(self)
        self._completion_popup.hide()
        self._completion_popup.itemActivated.connect(self.fn_completion_accept)
        self._completion_mode = ''        # 'mark' / 'keyword'
        self._completion_token = ''       # 光标前已输入的编号/前缀串
        self.window_show = ''
        self.window_rep = ''
        self.window_symbol = ''
        self.dock_symbol = None          # 兼容字段：特殊字符已改为独立窗口，无停靠容器
        self.window_help = ''
        self.window_search = ''
        self.window_table = ''
        self.window_location = ''
        self.brush_flag = False
        self.key_1, self.key_2, self.key_3, self.key_4, self.key_5 = '', '', '', '' ,''
        self.total_key = ''
        self.table_x = 5
        self.table_y = 5
        self.word_array = []
        self.type_v = ''
        self.char_format = ''
        self.dragging = False
        self.db_flag = False
        self.window_state = 'normal'
        self.window_pos = ''
        self.drag_flag = False
        self.old_x,self.old_y = 0,0
        # 拖动缩放（拉伸窗口边缘）时的重绘节流状态，见 _live_resize_begin
        self._live_resize = False
        self._live_resize_slow = None    # None=未探测；True=重绘慢，启用节流
        self._live_resize_timer = QTimer(self)
        self._live_resize_timer.setSingleShot(True)
        self._live_resize_timer.timeout.connect(self._live_resize_tick)
        # 状态栏 / 查找替换 / 文档数量相关的运行状态
        self._doc_dirty = False
        self._closing_confirmed = False
        self._overwrite_mode = False
        self._focus_mode = False
        self._find_dialog = None
        self.doc_count = DOC_TAB_COUNT
        self._status_timer = None
        # 用于高亮颜色（统一取自调色板 PAL）
        self.highlight_color = PAL['accent_hi']
        self.background_color = PAL['bg']
        self.font_color = '#aa0000'
        self.type_cursor = ''
        # 分词词典已内嵌为 SPLIT_TXT_1 / SPLIT_TXT_2 常量
        self.load_txt_1 = SPLIT_TXT_1
        self.load_txt_2 = SPLIT_TXT_2
        # 原模块级全局状态下沉为实例属性
        self.text_editor_array = []
        self.mark_editor_array = []
        self.active_textcomponent = ''
        self.active_figmark = ''
        self.tab_widget_text = None
        self.tab_widget_mark = None
        self.tab_count_array = []
        self.window_show_text_array = []
        self.window_show_mark_array = []
        self.toggle_flag = 0
        self.rep_model = 0
        self.model_type = '联想'
        self.write_type = '撰写'
        self.write_auto = '关闭'
        self.main_ui()
        self._load_tab_contents()
        self._init_status_tracking()
        self.set_doc_title(self.tab_name_array[0])
        self.status.set_saved(True)
        self._refresh_status_bar()

    def _load_tab_contents(self):
        """从统一草稿存档恢复上次会话内容（单次读取，不再逐文件打开）。"""
        store.ensure_loaded()
        for index, editor in enumerate(self.text_editor_array):
            try:
                html, _marks = store.get_tab(index)
                if html:
                    editor.setHtml(html)
                    # 空白草稿里若残留编号/项目符号列表，第一行会有一个
                    # 由块格式生成、按退格也删不掉的「1.」。恢复后清掉。
                    self._strip_empty_doc_list(editor)
                else:
                    editor.insertPlainText('')
                # 浮动图不在 HTML 里，单独还原
                editor.load_floats(store.get_tab_floats(index))
            except Exception as e:
                editor.insertPlainText('')
                print('Error Code 205', e)
        for index, editor in enumerate(self.mark_editor_array):
            try:
                editor.setPlainText(store.get_tab(index)[1])
            except Exception as e:
                print('Error Code 602', e)
                editor.setPlainText('')
        self.text_genword.setPlainText(store.main_userwords())
        # 内存基线直接取存档，避免首次同步时再读磁盘
        self._mark_snapshot = {
            i: [x for x in store.get_tab(i)[1].replace('\n', '\u2029').split('\u2029') if x.strip()]
            for i in range(len(self.mark_editor_array))
        }

    def wheelEvent(self,event):
        if event.modifiers() == Qt.ControlModifier and event.angleDelta().y() > 0:
            self.slider_fontsize.setValue(self.slider_fontsize.value()+1)
        elif event.modifiers() == Qt.ControlModifier and event.angleDelta().y() < 0:
            self.slider_fontsize.setValue(self.slider_fontsize.value()-1)
    def _save_all_drafts(self):
        """把全部文档 / 标记列表 / 名称 / 词库一次性写入单一草稿存档。"""
        try:
            store.save_main_snapshot(
                self.tab_name_array,
                self.text_genword.toPlainText(),
                [e.toHtml() for e in self.text_editor_array],
                [e.toPlainText() for e in self.mark_editor_array])
        except Exception as e:
            print('Error Code 603', e)
        self._doc_dirty = False
        self.status.set_saved(True)

    # ---------------- 图片插入 / 环绕 ----------------
    def _on_wrap_mode_changed(self, index=0):
        """插入→图片 的环绕方式：直接写进所有编辑器的插入模式。"""
        name = self.combo_wrap.currentText()
        mode = imgs.MODE_KEYS.get(name, 'inline')
        for editor in getattr(self, 'text_editor_array', []) or []:
            try:
                editor.image_insert_mode = mode
            except Exception:
                pass
        try:
            self.status.showMessage('图片环绕方式：%s' % name, 2500)
        except Exception:
            pass

    def fn_insert_image(self):
        """插入图片：走当前文档的插入模式（嵌入型 / 浮于文字上方 / 衬于文字下方）。"""
        try:
            self.active_textcomponent.insert_picture()
        except Exception as e:
            print('Error Code 432', e)

    def _persist_all_floats(self):
        """浮动图不进 HTML，按标签序号另存在 workspace.json 的 floats 里。"""
        for i, editor in enumerate(self.text_editor_array):
            try:
                store.set_tab_floats(i, editor.floats_payload())
            except Exception as e:
                print('Error Code 433', e)


    def _close_child_windows(self):
        for name in ('window_notebook', 'window_help', 'window_api', 'window_symbol',
                     'window_rep', 'window_search', 'window_table',
                     'window_location', 'window_show',
                     'dock_validation', 'dock_symbol'):
            w = getattr(self, name, None)
            if w:
                try:
                    w.close()
                except Exception:
                    pass
        if self._find_dialog:
            self._find_dialog.close()

    def _confirm_close(self):
        """Word 2019 风格关闭确认。返回 (是否退出, 是否先保存)。

        有未保存内容时提供「保存并退出 / 不保存退出 / 取消」；否则只有「退出 / 取消」。
        """
        if self._doc_dirty:
            buttons = [('保存并退出', 2, True), ('不保存退出', 1), ('取消', 0)]
            detail = ('当前有尚未存盘的修改。保存会把全部 %d 个文档写入草稿存档；'
                      '选择「不保存退出」将保留上一次自动保存的内容。' % self.doc_count)
        else:
            buttons = [('退出', 1, True), ('取消', 0)]
            detail = '所有文档均已保存到草稿。关闭窗口后可在下次启动时继续编辑。'
        reply = wf.ask(self, '关闭 Fenrir', '确定要退出 Fenrir 吗？', buttons,
                       detail=detail, kind='question', width=470)
        if reply == 0:  # 取消 / Esc / 标题栏 ✕
            return False, False
        return True, reply == 2

    def fn_closeEvent(self, event=None):
        """标题栏 ✕ / 菜单退出按钮：确认后触发一次标准 close()。"""
        ok, save = self._confirm_close()
        if not ok:
            return
        if save:
            self._save_all_drafts()
        # 申请人信息的落盘防抖可能还没到点，关闭前补一次
        try:
            self._flush_party_info()
        except Exception:
            pass
        self._closing_confirmed = True
        self._close_child_windows()
        self.close()

    def closeEvent(self, event):
        """Alt+F4 / 系统关闭：在本次事件内直接 accept，避免嵌套 close() 被 Qt 忽略。"""
        if getattr(self, '_closing_confirmed', False):
            event.accept()
            return
        ok, save = self._confirm_close()
        if not ok:
            event.ignore()
            return
        if save:
            self._save_all_drafts()
        # 申请人信息的落盘防抖可能还没到点，关闭前补一次
        try:
            self._flush_party_info()
        except Exception:
            pass
        self._closing_confirmed = True
        self._close_child_windows()
        event.accept()
    def main_ui(self):
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.setWindowTitle(f'FENRIR ver {version}')
        self.setGeometry(300, 200, 1300, 750)
        self.setMouseTracking(True)
        self.setWindowFlags(Qt.FramelessWindowHint) # 隐藏标题栏 
        # 增加右键菜单
        self.add_mouse_rightclick()
        # 设置主文本框
        self.texteditor_tabwidget = QWidget()
        self.layoutwidget = QGridLayout(self.texteditor_tabwidget)
        # 网格默认四边 9px 边距，下边距在编辑器与状态栏之间露出一条空隙；
        # 显式保留左右上边距、清零下边距（只缩文本框与底部状态栏的间距）
        self.layoutwidget.setContentsMargins(9, 9, 9, 0)
        self.setCentralWidget(self.texteditor_tabwidget)
        self.texteditor_tabwidget.setMouseTracking(True)
        # 设置输入框选项卡
        self.add_texteditors()
        # 附图标记联想输入
        self.add_markeditors()
        # 底部内联查找/高亮条（toolbar_bottom）已彻底移除：此前仅从布局移除却仍作为
        # 子控件浮在编辑器左上角（高亮关键词输入框 + 上下查找按钮 + 区分大小写复选框），
        # 造成“未删干净”的残留。查找/替换仍可用 Ctrl+H（fn_show_find_dialog）。
        # fn_bottom_bar 现仅创建状态栏缩放控件，不再创建该内联栏。
        self.fn_bottom_bar()

        self.dock_mark = QDockWidget('')
        self.dock_mark.setWidget(self.main_widget_mark)
        self.dock_mark.setMinimumWidth(36)
        self.dock_mark.setMaximumWidth(1000)
        self.dock_mark.setMouseTracking(True)
        # dock 外框 / 标题栏观感全部由全局 QSS 统一控制（QDockWidget::title
        # 深蓝 $title_bg、内容边框 $frame_lo），不再单独 setStyleSheet，
        # 与 dock_outline / dock_keywords 保持一致。

        self.dock_keywords = QDockWidget('')
        self.dock_keywords.setWidget(self.main_widget_keywords)
        self.dock_keywords.setMinimumWidth(36)
        self.dock_keywords.setHidden(True) # 设置dock为隐藏状态
        self.dock_keywords.setMouseTracking(True)

        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_mark)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_keywords)
        # 申请文件结构导航
        self.dock_outline = QDockWidget('')
        outline_widget = QWidget()
        outline_layout = QVBoxLayout(outline_widget)
        outline_layout.setContentsMargins(2,2,2,2)
        self.tree_outline = QTreeWidget()
        self.tree_outline.setHeaderHidden(True)
        # 关闭根节点装饰：不显示顶层展开箭头/连接线，让「说明书」与「权利要求书」
        # 都左对齐，视觉上明确并列（否则说明书有▼箭头、权利要求书无箭头，会被误看成从属）
        self.tree_outline.setRootIsDecorated(False)
        # 不在这里写死深色：底色/文字交给全局 QSS 统一控制；选中色取统一调色板
        self.tree_outline.setStyleSheet(
            "QTreeWidget{border:none;font-size:12px} "
            "QTreeWidget::item{padding:3px} "
            "QTreeWidget::item:selected{background:%s;color:%s}"
            % (PAL['accent_hi'], PAL['white']))
        sec_items = ['技术领域','背景技术','发明/实用新型内容','附图说明','具体实施方式']
        root_spec = QTreeWidgetItem(self.tree_outline, ['说明书'])
        for s in sec_items:
            QTreeWidgetItem(root_spec, [s])
        # 权利要求书与说明书并列（同属顶层节点），不要挂到说明书节点下
        self.root_claims = QTreeWidgetItem(self.tree_outline, ['权利要求书'])
        # 两个顶层节点加粗，突出它们是同级大纲（子章节保持常规字重）
        for _top in (root_spec, self.root_claims):
            _f = _top.font(0)
            _f.setBold(True)
            _top.setFont(0, _f)
        # 刷新按钮已集成到「说明书 / 权利要求书」文字上：双击顶层节点即触发刷新，
        # 不再单独放置底部按钮（fn_outline_jump 中拦截顶层节点分发）
        root_spec.setToolTip(0, '双击刷新')
        self.root_claims.setToolTip(0, '双击刷新')
        self.tree_outline.expandAll()
        # 关键修复：禁用双击展开/折叠切换。Qt 默认在双击时切换节点展开状态，
        # 且该切换发生在 itemDoubleClicked 信号处理之后——双击刷新刚重建并
        # 展开的子项会立刻被折叠回去；而本树 RootIsDecorated=False 没有展开
        # 箭头，一旦折叠用户无法再手动展开，表现为「权利要求内容不再出现」。
        self.tree_outline.setExpandsOnDoubleClick(False)
        outline_layout.addWidget(self.tree_outline)
        self.dock_outline.setWidget(outline_widget)
        self.dock_outline.setMinimumWidth(36)
        self.dock_outline.setMaximumWidth(1000)
        self.dock_outline.setMouseTracking(True)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_outline)
        self.tree_outline.itemDoubleClicked.connect(self.fn_outline_jump)
        # 申请人/发明人信息面板（每个文档独立一份，切文档自动切换）
        self._create_party_dock()
        # 单一数据源：createPopupMenu() 也用它兜底修复 action 文本/可用性。
        # 停靠时隐藏标题名；拖成独立窗体时显示对应标题。
        self._dock_action_titles = (
            ('dock_mark', '标记补全'),
            ('dock_keywords', '关键词补全'),
            ('dock_outline', '结构导航'),
            ('dock_party', '申请人信息'),
        )
        for _name, _title in self._dock_action_titles:
            _dock = getattr(self, _name)
            # 隐藏标题栏右上角的「浮动」与「关闭 ×」两个按钮（Qt 默认
            # Closable|Movable|Floatable 会同时画出它们）。面板的显示/隐藏
            # 统一由「视图 → 面板」的三个开关和 F11 专注模式控制，停靠区域
            # 由四个布局按钮或拖动标题栏调整；保留 Movable 让标题栏仍可拖动。
            _dock.setFeatures(QDockWidget.DockWidgetMovable)
            # Qt 在去掉 DockWidgetClosable 后会顺手把 toggleViewAction 禁用，
            # 「视图 → 面板」三个按钮和右键菜单会一起变灰点不动，这里强制恢复。
            # 另外 QDockWidget 会把 windowTitle 同步成 action 文本，所以停靠时
            # 清空标题（隐藏标题名）的动作会连文字一起抹掉，见 _on_dock_top_level。
            _act = _dock.toggleViewAction()
            _act.setText(_title)
            _act.setEnabled(True)
            _dock.topLevelChanged.connect(
                lambda floating, d=_dock, t=_title: self._on_dock_top_level(d, t, floating))
        # 状态栏（Word 2019 风格：左侧文档名/消息，右侧行列/字数/保存状态/缩放）
        self.status = wf.WordStatusBar()
        self.status.setMouseTracking(True)
        self.setStatusBar(self.status)
        # 文档名标题移到顶部标题栏中部（top_doc_title），底部状态栏不再重复显示；
        # lbl_doc 保留对象，set_doc_name 仍照常写入，消息标签自动左移到最左。
        self.status.lbl_doc.hide()
        self.status.wordCountClicked.connect(self.fn_show_wordcount)
        self.status.modeToggled.connect(self.fn_set_overwrite_mode)
        self.status.zoomResetClicked.connect(self.fn_zoom_reset)
        self.status.focusToggled.connect(self.fn_focus_mode)
        self.status.attach_zoom(self.bt_fontsize_down, self.slider_fontsize,
                               self.bt_fontsize_up, self.label_fontsize)
        self.status.set_accent()
        # 整个窗体外边框：宽度3，颜色与底部状态栏一致（鼠标穿透，不影响边缘缩放）
        self._edge_bar_width = 6
        self._edge_bars = []
        for _ in range(4):
            bar = QWidget(self)
            bar.setStyleSheet(f"background-color: transparent; border: none;")
            # 不设 WA_TransparentForMouseEvents：让边缘条真正接收鼠标事件，
            # 成为无边框窗口的缩放手柄（覆盖底部标签栏/dock 等子控件对边缘事件的拦截）
            self._edge_bars.append(bar)
        # 按需求删除最底部边框线（bars[3]），保留底部状态栏 QStatusBar
        self._edge_bars[3].hide()
        # 给四条边条挂鼠标事件：左/右/上/下及四角触发对应 drag_flag
        self._wire_edge_bar(self._edge_bars[0], 'left')
        self._wire_edge_bar(self._edge_bars[1], 'right')
        self._wire_edge_bar(self._edge_bars[2], 'up')
        self._position_edge_bars()
        self.status.setToolTip('点击状态栏可刷新字数；双击标题栏可最大化窗口')
        self.status.mousePressEvent = self.count_words
        # 状态栏横跨底部、盖住两个下角。不自己设光标就会继承 MainWindow 上一次
        # setCursor 的结果（角落常残留水平/垂直箭头）；这里按窗口坐标自判。
        self.status.mouseMoveEvent = self._status_mouse_move
        self.status.mouseReleaseEvent = self._status_release
        self.status.mouseDoubleClickEvent = self.status_dbclick
        # 底部边框抓手：一条 STATUS_BOTTOM_GRIP px 高的透明控件，盖住状态栏内
        # 字数 / 缩放按钮的下沿。否则按钮会吞掉底边的鼠标事件，热区在那些
        # 位置失效（离屏实测最底部 4px 内仍有 StatusButton 覆盖若干 x）。
        self.status_grip = QWidget(self.status)
        self.status_grip.setStyleSheet('background: transparent; border: none;')
        self.status_grip.setMouseTracking(True)
        self.status_grip.setCursor(Qt.SizeVerCursor)
        self.status_grip.mousePressEvent = self.count_words
        self.status_grip.mouseMoveEvent = self._status_mouse_move
        self.status_grip.mouseReleaseEvent = self._status_release
        self.status_grip.mouseDoubleClickEvent = self.status_dbclick
        self._position_status_grip()
        ''' 工具栏 '''
        self.main_toolbar = QToolBar("特殊符号、插入表格、一键格式化、重置格式")
        self.main_toolbar.setIconSize(QSize(20, 20))
        self.main_toolbar.setAllowedAreas(Qt.AllToolBarAreas)
        self.addToolBar(self.main_toolbar)
        # 输入方式、高亮色、背景色
        self.type_toolbar = QToolBar("输入方式、字体格式、上下角标")
        self.type_toolbar.setIconSize(QSize(20, 20))
        self.type_toolbar.setStyleSheet(
            "QToolBar { background: transparent; border: none; spacing: 2px; }")
        self.addToolBar(self.type_toolbar)
        # 选择输入方式
        # 5 种编号格式，最后一档「删除线的 Num」= 只补名称、不加序号（原 '-Num-'）
        self.combo_typev = QComboBox()
        self.combo_typev.addItems(['(Num)', '（Num）', '[Num]', 'Num'])
        self.combo_typev.addItem('Num')          # 第 5 项：显示为带删除线的 Num
        _norm = QFont(self.combo_typev.font())
        _strike = QFont(_norm)
        _strike.setStrikeOut(True)
        for _i in range(4):
            self.combo_typev.setItemData(_i, _norm, Qt.FontRole)   # 前 4 项显式正常字体
        self.combo_typev.setItemData(4, _strike, Qt.FontRole)
        for _i, _tip in enumerate((
                '(Num) → 机架(1)',
                '（Num） → 机架（1）',
                '[Num] → 机架[1]',
                'Num → 机架1',
                '删除线的 Num → 机架（只补名称，不加序号）')):
            self.combo_typev.setItemData(_i, _tip, Qt.ToolTipRole)
        self.combo_typev.setToolTip(
            '附图标记序号格式（Num = 序号的占位写法）\n'
            '输入方式：正文里写完名称后直接敲数字（如「机架1」的 1），\n'
            '弹出标记补全候选后按 空格 / Enter / Tab 确认，序号自动按所选格式补上：\n'
            '　(Num) → 机架(1)　　（Num） → 机架（1）\n'
            '　[Num] → 机架[1]　　Num → 机架1\n'
            '　删除线的 Num → 只补名称，不加序号（机架）\n'
            '↑↓ 选择候选，Esc 取消')
        self.combo_typev.currentIndexChanged.connect(self._sync_typev_strike)
        self.combo_typev.setCurrentIndex(0)
        # 与上下两个控件同宽，避免中间下拉框因选项短而缩窄、左边缘不对齐
        self.combo_typev.setMinimumWidth(96)
        # 图片环绕方式（插入→图片）：决定「插入图片 / 粘贴截图 / 拖入图片」时怎么放
        self.combo_wrap = QComboBox()
        self.combo_wrap.addItems(list(imgs.WRAP_MODES))
        for _i, _tip in enumerate((
                '嵌入型 → 图片当作一个字符排进正文，随文字移动，可随文档保存',
                '四周型环绕（左）→ 图片靠左浮动，正文文字绕到右侧',
                '四周型环绕（右）→ 图片靠右浮动，正文文字绕到左侧',
                '浮于文字上方 → 盖在正文上，可拖动、可缩放，适合加标注',
                '衬于文字下方 → 正文压在图片上，适合放底图/水印')):
            self.combo_wrap.setItemData(_i, _tip, Qt.ToolTipRole)
        self.combo_wrap.setToolTip(
            '图片环绕方式\n'
            '嵌入型：随文字排版（推荐，附图存档不会丢）\n'
            '四周型环绕：文字绕图片排布（左/右浮动）\n'
            '浮于文字上方：可拖动，压住正文\n'
            '衬于文字下方：正文压在图片上')
        self.combo_wrap.currentIndexChanged.connect(self._on_wrap_mode_changed)
        self.combo_wrap.setCurrentIndex(0)
        self.combo_wrap.setMinimumWidth(96)
        # 选择背景色
        self.choose_gcolor_action = QPushButton(" 背 ")
        self.choose_gcolor_action.setToolTip('自定义背景色')
        self.choose_gcolor_action.setStyleSheet(f"background-color: {self.background_color}")
        self.choose_gcolor_action.clicked.connect(self.choose_gcolor)
        
        # 设置字体
        self.combo_fonts = QFontComboBox()
        self.combo_fonts.setMaximumWidth(110)
        # 设置字体大小
        self.combo_fontsize = QComboBox()
        self.combo_fontsize.setToolTip('字体大小')
        self.combo_fontsize.addItems([str(s) for s in self.FONT_SIZES])
        self.combo_fontsize.setCurrentIndex(8)
        self.combo_fontsize.setFixedWidth(46)
        # 设置行间距
        self.combo_lineheight = QComboBox()
        self.combo_lineheight.setToolTip('行间距')
        self.combo_lineheight.addItems(self.LINE_HEIGHT)
        self.combo_lineheight.setCurrentIndex(2)
        self.combo_lineheight.currentIndexChanged.connect(self.on_lineheight_changed)
        
        self.action_undo = QAction(QIcon(qta.icon('mdi.undo')),'撤销')
        self.action_undo.setToolTip('撤销')
        self.action_undo.triggered.connect(self.fn_undo) # 撤销
        self.action_undo.setShortcut('Ctrl+Z')

        self.action_redo = QAction(QIcon(qta.icon('mdi.redo')),'重复')
        self.action_redo.setToolTip('重复')
        self.action_redo.triggered.connect(self.fn_redu) # 重做
        self.action_redo.setShortcut('Ctrl+Y')

        # 设置字体格式
        self.bt_bold = QPushButton(QIcon(qta.icon('ph.text-bolder-bold')),"")
        self.bt_bold.setShortcut(QKeySequence.Bold)
        self.bt_bold.setCheckable(True)

        self.bt_italic = QPushButton(QIcon(qta.icon('ph.text-italic-bold')),"")
        self.bt_italic.setShortcut(QKeySequence.Italic)
        self.bt_italic.setCheckable(True)

        self.bt_underline = QPushButton(QIcon(qta.icon('ph.text-underline-bold')),"")
        self.bt_underline.setShortcut(QKeySequence.Underline)
        self.bt_underline.setCheckable(True)

        self.bt_upper = QPushButton(QIcon(qta.icon('fa5s.superscript')),"")
        self.bt_upper.setToolTip('上角标')
        self.bt_upper.setCheckable(True)
        self.bt_upper.clicked.connect(self.font_upper)


        self.bt_lower = QPushButton(QIcon(qta.icon('fa5s.subscript')),"")
        self.bt_lower.setToolTip('下角标')
        self.bt_lower.setCheckable(True)
        self.bt_lower.clicked.connect(self.font_lower)

        self.bt_toggle = QPushButton(QIcon(qta.icon('fa5s.exchange-alt')),"")
        self.bt_toggle.setToolTip('大小写转换，按一次转大写，再按一次转小写')
        self.bt_toggle.setCheckable(True)
        self.bt_toggle.clicked.connect(self.font_toggle)
        # 清除格式
        self.toobar_resetformat = QPushButton(QIcon(qta.icon('mdi.restore')),"")
        self.toobar_resetformat.setToolTip('清除全部格式')
        self.toobar_resetformat.clicked.connect(self.fn_reset_allformat)

        self.toobar_clearformat = QPushButton(QIcon(qta.icon('ri.brush-2-line')),'')
        self.toobar_clearformat.setToolTip('清除所选内容的格式')
        self.toobar_clearformat.clicked.connect(self.clear_select_format)
        # 设置字体的前景颜色 — Office Word 风格：大 A + 底部彩色指示条
        self.bt_fontcolor = QPushButton('A')
        self.bt_fontcolor.setFixedSize(22, 28)
        self.bt_fontcolor.setStyleSheet(
            "QPushButton { font-family: 'Times New Roman'; font-weight: bold; "
            "font-size: 14px; color: %s; border: none; "
            "border-bottom: 3px solid #ff0000; background: %s; }"
            "QPushButton:hover { background: %s; }"
            % (PAL['text'], PAL['panel2'], PAL['hover']))
        self.bt_fontcolor.setToolTip('修改字体颜色')
        self.bt_fontcolor.clicked.connect(self.change_font_color)

        self.bt_color = QPushButton('▾')
        self.bt_color.setFixedSize(20, 28)
        self.bt_color.setToolTip('选择颜色')
        self.bt_color.setStyleSheet(
            "QPushButton { border: none; font-size: 10px; color: %s; "
            "background: %s; }"
            "QPushButton:hover { background: %s; }"
            % (PAL['text'], PAL['panel2'], PAL['hover']))
        self.bt_color.clicked.connect(self.choose_fontcolor)
    
        self.bt_brush = QPushButton(QIcon(qta.icon('ri.paint-brush-fill')),"") # 格式刷
        self.bt_brush.setToolTip('格式刷')
        self.bt_brush.setCheckable(True)
        self.bt_brush.clicked.connect(self.fn_brush)
        self.bt_brush.mouseDoubleClickEvent = self.fn_brush_dbclick

        self.bt_inserttable = QAction(QIcon(qta.icon('fa5s.table')),'插入表格')
        self.bt_inserttable.triggered.connect(self.fn_insert_table)

        self.bt_onekeyformat = QAction(QIcon(qta.icon('ph.rocket-launch')),'一键格式化(F5)')
        self.bt_onekeyformat.triggered.connect(self.one_key_format)
        self.bt_onekeyformat.setShortcut('F5')

        self.bt_defaultformat = QAction(QIcon(qta.icon('ph.eraser-fill')),'重置为默认格式(F6)')
        self.bt_defaultformat.triggered.connect(self.default_format)
        self.bt_defaultformat.setShortcut('F6')

        self.main_toolbar.addAction(self.action_undo) # 撤销
        self.main_toolbar.addAction(self.action_redo) # 重做
        self.main_toolbar.addWidget(self.bt_brush) # 格式刷
        self.main_toolbar.addAction(self.bt_inserttable) # 插入表格
        self.main_toolbar.addAction(self.bt_onekeyformat) # 一键格式化
        self.main_toolbar.addAction(self.bt_defaultformat) # 重置格式

        self.type_toolbar.addWidget(self.combo_typev)
        self.type_toolbar.addWidget(self.combo_fonts)
        self.type_toolbar.addWidget(self.combo_fontsize)
        self.type_toolbar.addWidget(self.combo_lineheight)
        self.type_toolbar.addWidget(self.bt_bold)
        self.type_toolbar.addWidget(self.bt_italic)
        self.type_toolbar.addWidget(self.bt_underline)
        self.type_toolbar.addWidget(self.bt_upper)
        self.type_toolbar.addWidget(self.bt_lower)
        self.type_toolbar.addWidget(self.bt_toggle)
        self.type_toolbar.addWidget(self.bt_fontcolor)
        self.type_toolbar.addWidget(self.bt_color)

        # 设置工具栏_3
        self.format_toolbar = QToolBar("段落格式")
        self.format_toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(self.format_toolbar)
        # 设置对齐方式（Remix 标准图标：Office ribbon 视觉风格，粗细适中；
        # ei.* 粗块状与 phosphor thin 过细均已弃用）
        self.toobar_alignl = QAction(QIcon(qta.icon('ri.align-left')),"左对齐")
        self.toobar_alignl.setCheckable(True)
        self.toobar_alignc = QAction(QIcon(qta.icon('ri.align-center')),"居中对齐")
        self.toobar_alignc.setCheckable(True)
        self.toobar_alignr = QAction(QIcon(qta.icon('ri.align-right')),"右对齐")
        self.toobar_alignr.setCheckable(True)
        self.toobar_alignj = QAction(QIcon(qta.icon('ri.align-justify')),"两端对齐")
        self.toobar_alignj.setCheckable(True)

        self.format_toolbar.addAction(self.toobar_alignl)
        self.format_toolbar.addAction(self.toobar_alignc)
        self.format_toolbar.addAction(self.toobar_alignr)
        self.format_toolbar.addAction(self.toobar_alignj)

        # 文件工具
        self.file_toolbar = QToolBar("文件操作")
        self.file_toolbar.setIconSize(QSize(20, 20))

        self.action_open_file = QAction(QIcon(qta.icon('ei.folder-open')),"打开")
        self.action_open_file.triggered.connect(self.file_open)
        self.action_save_file = QAction(QIcon(qta.icon('fa5s.save')),"保存")
        self.action_save_file.triggered.connect(self.file_save)
        self.action_saveas_file = QAction(QIcon(qta.icon('mdi6.content-save-edit')),"另存为")
        self.action_saveas_file.triggered.connect(self.file_saveas)
        self.action_options = QAction(QIcon(qta.icon('fa6s.gears')),"设置")
        self.action_options.triggered.connect(self.fn_options)

        # ---- Word 2019 风格的编辑 / 视图 / 输出功能 ----
        # QAction 快捷键由 Qt 在事件到达编辑器之前处理，因此即使编辑器重写了
        # keyPressEvent 也能生效；不要再往 fn_keypressevent 的映射里重复添加。
        def _act(icon, text, slot, shortcut=None, tip=None):
            a = QAction(QIcon(qta.icon(icon)), text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(shortcut)
            a.setToolTip(tip or ('%s%s' % (text, ' (%s)' % shortcut if shortcut else '')))
            return a

        self.action_find = _act('mdi6.file-search-outline', '查找和替换',
                                self.fn_show_find_dialog, 'Ctrl+H',
                                '查找 / 替换 / 全部替换 / 高亮全部（Ctrl+H）')
        self.action_goto = _act('mdi6.target', '定位到行',
                                self.fn_goto_line, 'Ctrl+Shift+G')
        self.action_wordcount = _act('mdi6.counter', '字数统计',
                                     self.fn_show_wordcount)
        self.action_selectall = _act('mdi6.select-all', '全选',
                                     self.fn_select_all, 'Ctrl+A')
        self.action_datetime = _act('mdi6.calendar-month', '日期和时间',
                                    self.fn_insert_datetime, 'Shift+Alt+D')
        self.action_divider = _act('mdi6.minus', '插入分隔线',
                                   self.fn_insert_divider)
        # 段落组图标：Remix 标准图标（Office ribbon 视觉风格，粗细适中；
        # phosphor thin 过细发虚、mdi6 过粗，均弃用）
        self.action_bullet = _act('ri.list-unordered', '项目符号',
                                  self.fn_bullet_list)
        self.action_numberlist = _act('ri.list-ordered', '编号',
                                      self.fn_number_list)
        self.action_indent_in = _act('mdi6.format-indent-increase', '增加缩进',
                                     self.fn_indent_increase)
        self.action_indent_out = _act('mdi6.format-indent-decrease', '减少缩进',
                                      self.fn_indent_decrease)
        # 首行缩进
        self.action_firstline = _act('mdi6.format-paragraph', '首行缩进',
                                     self.fn_first_line_indent)
        self.action_print = _act('mdi6.printer', '打印',
                                 self.fn_print, 'Ctrl+P')
        self.action_exportpdf = _act('mdi6.file-pdf-box', '导出为 PDF',
                                     self.fn_export_pdf)
        self.action_focusmode = _act('mdi6.fullscreen', '专注模式',
                                     self.fn_focus_mode, 'F11')
        self.action_overwrite = _act('mdi6.keyboard-outline', '插入 / 改写',
                                     lambda: self.fn_set_overwrite_mode(
                                         not self._overwrite_mode), 'Insert')
        self.action_clearscreen = _act('mdi6.delete-sweep-outline', '清空文档',
                                       self.fn_clearscreen,
                                       tip='清空当前文档正文与附图标记列表，并重置文档名称')

        # 辅助工具
        self.tools_toolbar = QToolBar("常用工具")
        self.tools_toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(self.tools_toolbar)

        self.tool_figeditor = QAction(QIcon(qta.icon('ei.picasa')),"编辑图片", self)
        self.tool_figeditor.triggered.connect(self.fn_show_figeditor)
        self.tool_figeditor.setToolTip('编辑图片 —— 打开「附图标注」标签页')

        self.tool_adjustfigs = QAction(QIcon(qta.icon('mdi6.webhook')),"一键改图", self)
        self.tool_adjustfigs.triggered.connect(self.fn_show_adjust)
        self.tool_adjustfigs.setToolTip('一键改图 —— 打开「调整外观图」标签页')

        # XML 修改：设计调整服务的第 3 个标签页，主程序新增入口
        self.tool_xmlmodify = QAction(QIcon(qta.icon('mdi6.xml')),"XML修改", self)
        self.tool_xmlmodify.triggered.connect(self.fn_show_xmlmodify)
        self.tool_xmlmodify.setToolTip('打开「XML 修改」标签页（申请 ZIP 字段批量改写）')

        # 服务信息：查看内嵌处理服务的端口与局域网地址
        self.tool_designservice = QAction(QIcon(qta.icon('mdi6.server')),"服务信息", self)
        self.tool_designservice.triggered.connect(self.fn_design_service_info)
        self.tool_designservice.setToolTip('查看设计调整服务状态与访问地址')

        # AI 接口设置：与「服务信息」同属「工具 → 服务」组
        self.tool_ai_settings = QAction(QIcon(qta.icon('mdi6.robot-outline')),
                                        "AI 接口设置", self)
        self.tool_ai_settings.triggered.connect(self.fn_ai_settings)
        self.tool_ai_settings.setToolTip(
            '配置火山方舟模型接口（API Key / Endpoint / 校验范围），用于文本校验')

        self.tool_eureka = QAction(QIcon(qta.icon('mdi6.hub-outline')), "特征关系分析", self)
        self.tool_eureka.triggered.connect(self.fn_eureka)
        self.tool_eureka.setToolTip('特征关系分析：识别特征从属/连接关系，生成 3D 气泡蛛网图')

        self.tool_reexam = QAction(QIcon(qta.icon('msc.law')),"复审无效", self)
        self.tool_reexam.triggered.connect(self.fn_reexam)
        self.tool_reexam.setToolTip('复审无效')

        self.tool_formatset = QAction(QIcon(qta.icon('fa5s.wrench')),"预设格式")
        self.tool_formatset.triggered.connect(self.fn_formatset)

        self.tool_loadimgs = QAction(QIcon(qta.icon('ri.image-add-line')),"批量导入附图")
        self.tool_loadimgs.triggered.connect(self.fn_loadimgs)

        self.tools_toolbar.addAction(self.tool_figeditor)
        self.tools_toolbar.addAction(self.tool_adjustfigs)
        self.tools_toolbar.addAction(self.tool_xmlmodify)
        self.tools_toolbar.addAction(self.tool_designservice)
        self.tools_toolbar.addAction(self.tool_eureka)
        self.tools_toolbar.addAction(self.tool_reexam)

        # 弹出工具
        self.tools_toolbar_addition = QToolBar("文本校验、特殊字符、资源管理器、使用帮助")
        self.addToolBar(self.tools_toolbar_addition)
        self.tools_toolbar_addition.setMinimumWidth(50)
        
        self.tool_showhelp = QAction(QIcon(qta.icon('mdi.help-rhombus-outline')),"使用帮助(F1)")
        self.tool_showhelp.triggered.connect(self.fn_showhelp)
        self.tool_showhelp.setShortcut('F1')

        self.tool_showbook = QAction(QIcon(qta.icon('fa5s.toolbox')),"文本校验(F2)")
        self.tool_showbook.triggered.connect(self.fn_showbook)
        self.tool_showbook.setShortcut('F2')

        self.bt_showsymbol = QAction(QIcon(qta.icon('fa5b.slack')),'特殊字符')
        self.bt_showsymbol.setToolTip('特殊字符（F3）')
        self.bt_showsymbol.triggered.connect(self.fn_show_symbol)
        self.bt_showsymbol.setShortcut('F3')

        # F1/F2/F3/F5/F6 全局化：挂主窗口 + ApplicationShortcut，
        # 切到「开始」页后这些按钮虽不可见，快捷键仍能触发。
        for _a, _seq in ((self.tool_showhelp, 'F1'), (self.tool_showbook, 'F2'),
                          (self.bt_showsymbol, 'F3'),
                          (self.bt_onekeyformat, 'F5'), (self.bt_defaultformat, 'F6')):
            _a.setParent(self)
            self.addAction(_a)
            _a.setShortcutContext(Qt.ApplicationShortcut)
            _old = _a.toolTip()
            if _old and _seq not in _old:
                _a.setToolTip(f'{_old}（{_seq}）')

        self.tools_toolbar_addition.addAction(self.tool_showhelp) # 使用帮助F1
        self.tools_toolbar_addition.addAction(self.tool_showbook) # 文本校验F2
        self.tools_toolbar_addition.addAction(self.bt_showsymbol) # 特殊字符F3

        # 顶部工具栏
        self.file_menu = self.menuBar()
        # 不再画 #455364 的 top/left/right 边框：黑条(dragger_top)只盖到
        # 窗口 y=34，菜单栏固定 38px 的底部 4px 露在外面，左右 2px 边框会在
        # 标题栏两角以「浅色小点」的形式露出来（实测右下角 2x4px 的 #455364
        # 色块，左下角对称）。全部去掉，只保留黑色底。
        self.file_menu.setStyleSheet("border: none;background-color:black;")
        self.file_menu.setFixedHeight(38)
        self.fn_menu_bar() # 设置拖动、最大化、最小化、关闭按钮
        # 文件/工具/帮助菜单已移除，功能入口整合到 Ribbon 功能区
        # 绑定editor功能
        for editor in self.text_editor_array:
            self.combo_fonts.currentFontChanged.connect(editor.setCurrentFont)
            self.combo_fontsize.currentIndexChanged.connect(editor.setFontPointSize)
            self.add_action(editor)
        format_group = QActionGroup(self)
        format_group.setExclusive(True)
        format_group.addAction(self.toobar_alignl)
        format_group.addAction(self.toobar_alignc)
        format_group.addAction(self.toobar_alignr)
        format_group.addAction(self.toobar_alignj)
        self._format_actions = [self.combo_fonts,self.combo_fontsize,self.bt_bold,self.bt_italic,self.bt_underline]
        self._build_ribbon()
        # 文本校验 / 特殊字符面板按需创建（首次按 F2 / F3 时才构造），
        # 避免启动阶段创建三张表格与报告浏览器拖慢首帧。两者都是停靠面板，
        # 容器也一并延迟创建。
        self.window_notebook = ''
        self.dock_validation = None
        self.dock_symbol = None
        self.resizeEvent = self.window_change_event
    @staticmethod
    def _ribbon_rows(rows):
        """把若干行小控件叠成一个面板，模拟 Word 功能区的多行按钮组。"""
        box = QWidget()
        box.setObjectName('RibbonRows')
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        for row in rows:
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(2)
            for w in row:
                h.addWidget(w)
            h.addStretch(1)
            v.addLayout(h)
        v.addStretch(1)
        return box

    def _ribbon_button(self, action, big=False, label=None, bind=True, tip=None):
        """由 QAction 生成功能区按钮。
        bind=True 用 setDefaultAction 保持 checkable 状态同步；
        bind=False 只转发点击。label 可给出更短的显示文案，完整名称留在 tooltip；
        tip 显式指定提示文字（按钮只放符号时，用 tooltip 说明含义）；
        tip='' 表示不显示 tooltip——按钮文字已经说明用途时不必再弹提示框。"""
        btn = QToolButton()
        if bind:
            btn.setDefaultAction(action)
            if label is not None:
                btn.setText(label)
        else:
            btn.setIcon(action.icon())
            btn.setText(label if label is not None else action.text())
            btn.setToolTip(action.toolTip() or action.text())
            btn.clicked.connect(lambda checked=False, a=action: a.trigger())
        btn.setObjectName('RibbonBig' if big else 'RibbonSmall')
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon if big else Qt.ToolButtonTextBesideIcon)
        btn.setIconSize(QSize(26, 26) if big else QSize(15, 15))
        if big:
            btn.setFixedHeight(62)
            btn.setMinimumWidth(56)
            btn.setMaximumWidth(72)
        else:
            btn.setFixedHeight(22)
            btn.setMinimumWidth(84)
            btn.setMaximumWidth(160)
        # bind=True 时 setDefaultAction 会把 action 的 tooltip 搬到按钮上，
        # 这里用 tip='' 覆盖掉即可清空，不必改 action（菜单里仍保留提示）。
        if tip is not None:
            btn.setToolTip(tip)
        return btn

    @staticmethod
    def _ribbon_small(widget, label=None, style=True):
        """把既有 QPushButton / QComboBox 统一成功能区小控件。"""
        widget.setFixedHeight(21)
        if style:
            widget.setObjectName('RibbonSmall')
        if label is not None and hasattr(widget, 'setText'):
            widget.setText(label)
        if style and hasattr(widget, 'setMinimumWidth'):
            widget.setMinimumWidth(88)
        if hasattr(widget, 'setMaximumWidth'):
            widget.setMaximumWidth(160)
        return widget

    def createPopupMenu(self):
        """主窗口/工具栏区域的右键菜单：只保留三个停靠面板显隐开关。

        QMainWindow 默认实现会把所有 QToolBar 的 toggleViewAction 一起列进来，
        于是菜单里出现「特殊符号、插入表格…」「输入方式、字体格式…」「段落格式」
        「常用工具」「文本校验、特殊字符…」以及「功能区」六项 —— 前五项是改造成
        功能区后遗留的隐藏工具栏，本来就不该让用户看见；「功能区」一旦在这里
        被误勾掉，界面上方会整条消失且无处恢复（折叠按钮也随之被隐藏）。

        面板的显示/隐藏统一由「视图 → 面板」的三个开关和 F11 专注模式负责，
        这里保持与它们一一对应即可。
        """
        self._sync_dock_actions()
        menu = QMenu(self)
        for _name, _title in self._dock_action_titles:
            _dock = getattr(self, _name, None)
            if _dock is not None:
                menu.addAction(_dock.toggleViewAction())
        return menu

    def _sync_dock_actions(self):
        """兜底：保证三个面板开关始终有文字、可点击。

        QDockWidget 有两处会自动破坏 toggleViewAction：
          1. setFeatures() 去掉 DockWidgetClosable 时把 action 设为 disabled；
          2. setWindowTitle() 把 action 的 text 同步成新标题（停靠时是空串）。
        三个开关同时被右键菜单和「视图 → 面板」的 QToolButton 共享，修一次
        两处一起恢复。
        """
        for _name, _title in getattr(self, '_dock_action_titles', ()):
            _dock = getattr(self, _name, None)
            if _dock is None:
                continue
            _act = _dock.toggleViewAction()
            if _act.text() != _title:
                _act.setText(_title)
            if not _act.isEnabled():
                _act.setEnabled(True)

    @staticmethod
    def _on_dock_top_level(dock, title, floating):
        """面板浮动/停靠：只隐藏停靠时的标题名，别把开关文字一起抹掉。"""
        dock.setWindowTitle(title if floating else '')
        act = dock.toggleViewAction()
        act.setText(title)      # setWindowTitle 已把它同步成 ''
        act.setEnabled(True)

    # ---------------- Word 2019「文件」后台视图 ----------------
    def _init_backstage(self):
        """懒创建：首次点「文件」才构造，不拖慢启动首帧。"""
        if getattr(self, '_backstage', None) is not None:
            return
        bs = BackstageView(self)
        bs.hide()
        bs.closeRequested.connect(self._hide_backstage)
        bs.actionTriggered.connect(self._on_backstage_action)
        self._backstage = bs

    def _show_backstage(self):
        self._init_backstage()
        self._refresh_backstage_data()
        self._backstage.show_page('home')
        self._position_backstage()
        self._backstage.show()
        self._backstage.raise_()
        self._backstage.setFocus()

    def _hide_backstage(self):
        bs = getattr(self, '_backstage', None)
        if bs is not None and bs.isVisible():
            bs.hide()

    def _position_backstage(self):
        """后台页盖住功能区与文档区，只保留自绘标题栏（与 Word 一致）。"""
        bs = getattr(self, '_backstage', None)
        if bs is None:
            return
        tabs = getattr(self, 'ribbon', None)
        top = tabs.mapTo(self, QPoint(0, 0)).y() if tabs is not None else 0
        bs.setGeometry(0, top, self.width(), max(self.height() - top, 1))

    def _refresh_backstage_data(self):
        self._init_backstage()
        bs = self._backstage
        tabs = getattr(self, 'tab_widget_text', None)
        names = list(getattr(self, 'tab_name_array', []))
        cur = tabs.currentIndex() if tabs is not None else -1
        path = getattr(self, 'path', None) or ''
        bs.set_recent([(n, path if i == cur else '')
                       for i, n in enumerate(names)])
        cur_name = names[cur] if 0 <= cur < len(names) else (names[0] if names else '')
        bs.set_document_info(cur_name, path, len(names))

    def _on_backstage_action(self, key):
        if key == 'open':
            self._hide_backstage()
            self.file_open()
        elif key == 'save':
            self._hide_backstage()
            self.file_save()
        elif key == 'saveas':
            self._hide_backstage()
            self.file_saveas()
        elif key == 'blank':
            self._hide_backstage()
            self.fn_add_document()
        elif key.startswith('recent:'):
            try:
                idx = int(key.split(':', 1)[1])
            except ValueError:
                return
            self._hide_backstage()
            tabs = getattr(self, 'tab_widget_text', None)
            if tabs is not None and 0 <= idx < tabs.count():
                tabs.setCurrentIndex(idx)

    def _ribbon_pane(self):
        """QTabWidget 内承载各页的 QStackedWidget，隐藏它即可只留下选项卡栏。"""
        return self.ribbon.findChild(QStackedWidget)

    def _set_ribbon_collapsed(self, collapsed):
        """折叠/展开功能区。折叠时隐藏按钮面板，保留选项卡栏可切换。"""
        tabs = self.ribbon
        self._ribbon_collapsed = collapsed
        pane = self._ribbon_pane()
        if collapsed:
            if pane is not None:
                pane.hide()
            height = max(tabs.tabBar().sizeHint().height(), 24)
            self._ribbon_fold_btn.setText('⌄')
            self._ribbon_fold_btn.setToolTip('展开功能区（也可双击选项卡）')
        else:
            if pane is not None:
                pane.show()
            height = self._ribbon_full_height
            self._ribbon_fold_btn.setText('⌃')
            self._ribbon_fold_btn.setToolTip('折叠功能区（也可双击选项卡）')
        tabs.setFixedHeight(height)
        holder = getattr(self, '_ribbon_holder', None)
        if holder is not None:
            holder.setFixedHeight(height)
        tabs.updateGeometry()
        self._apply_ribbon_backdrop()
        # 折叠后 tabBar 高度会变，搜索框的垂直位置跟着重算
        self._position_ribbon_search()
        # 展开/折叠后页面位置要等这一轮布局完成才准确，再补算一次
        QTimer.singleShot(0, self._apply_ribbon_backdrop)
        QTimer.singleShot(0, self._position_ribbon_search)
        status = getattr(self, 'status', None)
        if status is not None:
            status.showMessage('功能区已折叠，双击选项卡可展开' if collapsed else '功能区已展开', 3000)

    def _toggle_ribbon(self):
        self._set_ribbon_collapsed(not self._ribbon_collapsed)

    def _apply_ribbon_backdrop(self):
        """功能区整条背景统一交给工具栏（RibbonHolder）自绘。

        功能区内部有三处让页面渐变「缩进去」的缝隙，会在左右两侧露出深色竖带：
          · 工具栏右侧 6px —— 功能区宽度比窗口少 6px（让出无边框窗口的右边缘缩放条）
          · QTabWidget 的 pane —— 样式默认左右各内缩 3px
          · QScrollArea —— 视口之外的 2px 边框
        把同一条渐变画在工具栏自己的背景上，这些缝隙露出的就是渐变本身，
        左右不再有深色边带。渐变比例按页面控件在工具栏内的实际纵向位置换算，
        折叠后只剩选项卡栏时退化为纯色 $bg（否则渐变会被压进标签行）。
        """
        holder = getattr(self, '_ribbon_holder', None)
        tabs = getattr(self, 'ribbon', None)
        if holder is None or tabs is None:
            return
        base = ('QToolBar#RibbonHolder { border: 0px; padding: 0px; '
                'margin: 0px; spacing: 0px; ')
        collapsed = bool(getattr(self, '_ribbon_collapsed', False))
        ratio = 0.0
        if not collapsed:
            page = tabs.currentWidget()
            if page is not None and holder.height() > 0:
                top = page.mapTo(holder, page.rect().topLeft()).y()
                ratio = min(max(top / float(holder.height()), 0.0), 1.0)
        # 只有比例真的变了才重设样式表：setStyleSheet 会触发整棵子树重新 polish，
        # 拖拽改窗口大小时每帧都调会很卡（见 window_change_event 的节流说明）。
        key = (collapsed, round(ratio, 3))
        if key == getattr(self, '_ribbon_backdrop_key', None):
            return
        self._ribbon_backdrop_key = key
        if collapsed:
            # 收纳时 pane 被压到标签栏下方，全局 QSS 给 pane 画的
            # border-bottom: 1px 会在标签行底下露出一条多余横线；
            # 折叠态就地抹掉它（holder 样式表比全局表更靠近控件，优先生效）
            holder.setStyleSheet(base + 'background: %s; } '
                                 'QTabWidget#RibbonTabs::pane { border-bottom: 0px; }'
                                 % PAL['bg'])
            return
        holder.setStyleSheet(
            base + 'background: qlineargradient(x1:0,y1:0,x2:0,y2:1, '
                   'stop:0 %s, stop:%.3f %s, stop:1 %s); }'
                   % (PAL['bg'], ratio, PAL['bg'], PAL['hover']))

    def eventFilter(self, obj, event):
        """双击功能区选项卡栏折叠/展开（Word 2019 行为）；
        并处理标签就地重命名框的 Esc 取消 / 失焦提交。"""
        # 点击主窗口时把工具浮窗重新抬到主窗口上方（浮窗不被主窗体遮挡；
        # 应用失活时浮窗是普通窗口，自动落到其它程序之后，不遮挡外部软件）
        if obj is self and event.type() == QEvent.MouseButtonPress:
            self._raise_tool_windows()
        edit = getattr(self, '_tab_rename_edit', None)
        if edit is not None and obj is edit:
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self._tab_rename_finish(apply=False)
                return True
            if event.type() == QEvent.FocusOut:
                self._tab_rename_finish(apply=True)
                return False
        # 文档/标记标签栏的滚轮处理：QTabBar 默认用滚轮切换选项卡，指针停在
        # 标签上滚动时会一路切到末尾「+」占位页，从而误触发「新建文档」
        # （见 _guard_tabbar_wheel）。
        if event.type() == QEvent.Wheel and obj.property('NoWheelSwitch'):
            doc_bar = getattr(self, 'tab_widget_text', None)
            doc_bar = doc_bar.tabBar() if doc_bar is not None else None
            if obj is doc_bar:
                # 新行为：指针位于文档名称标签上时，滚轮切换文档；
                # 「+」页与空白处仍吞掉（绝不借此新建文档）
                pos = obj.mapFromGlobal(event.globalPos())
                idx = obj.tabAt(pos)
                last = obj.count() - 1          # 末页是「+」占位页
                if 0 <= idx < last:
                    step = 1 if event.angleDelta().y() < 0 else -1
                    new_idx = max(0, min(last - 1, obj.currentIndex() + step))
                    if new_idx != obj.currentIndex():
                        obj.setCurrentIndex(new_idx)
                return True
            return True  # 标记列表标签栏等：维持原来的完全吞掉
        tabs = getattr(self, 'ribbon', None)
        if tabs is not None and obj is tabs and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._position_ribbon_search)
        if tabs is not None and obj is tabs.tabBar():
            et = event.type()
            if et == QEvent.Resize:
                # 选项卡行宽度变了，搜索框要重新贴到最后一个选项卡之后
                QTimer.singleShot(0, self._position_ribbon_search)
            if et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                # 「文件」是入口 tab，不参与页面切换：吞掉鼠标事件，
                # 否则 QTabBar 在 MouseButtonPress 时就会把它设为当前页。
                if obj.tabAt(event.pos()) == self.FILE_TAB_INDEX:
                    if et == QEvent.MouseButtonPress:
                        self._show_backstage()
                    return True
            if et == QEvent.Paint:
                # 功能区选项卡文字左对齐：拦截 QTabBar 的 Paint 事件自绘
                # （QSS text-align / per-widget QProxyStyle 在应用级样式表下
                # 均被 QStyleSheetStyle 绕过，实证见 temp 时期的间谍样式测试）
                self._paint_ribbon_tabs(obj)
                return True
            if et == QEvent.MouseButtonDblClick:
                if obj.tabAt(event.pos()) == self.FILE_TAB_INDEX:
                    return True
                self._toggle_ribbon()
                return True  # 吞掉双击，避免连带的两次单击误切页
        return super().eventFilter(obj, event)

    # 功能区标签文字与 QSS 内边距对齐：RIBBON_QSS 里 tab 的 padding 为 4px 15px，
    # QStyleSheetStyle 的 SE_TabBarTabText 不含该内边距（返回整格），自绘时手动补上
    RIBBON_TAB_TEXT_PAD = 15

    def _paint_ribbon_tabs(self, bar):
        """功能区选项卡自绘：形状走样式层（QSS 观感不变），文字左对齐。
        文字颜色与 QSS 规则保持同一来源（PAL）：常规 text_low、悬停/选中 white。"""
        p = QPainter(bar)
        style = bar.style()
        pad = self.RIBBON_TAB_TEXT_PAD
        for i in range(bar.count()):
            opt = QStyleOptionTab()
            bar.initStyleOption(opt, i)
            opt.rect = bar.tabRect(i)
            style.drawControl(QStyle.CE_TabBarTabShape, opt, p, bar)
            text_rect = style.subElementRect(QStyle.SE_TabBarTabText, opt, bar)
            if not text_rect.isValid() or not opt.text:
                continue
            text_rect = text_rect.adjusted(pad, 0, -pad, 0)
            if not text_rect.isValid() or text_rect.width() <= 0:
                continue
            fm = opt.fontMetrics
            text = fm.elidedText(opt.text, bar.elideMode(),
                                 max(text_rect.width() - 2, 0))
            if opt.state & QStyle.State_Selected or opt.state & QStyle.State_MouseOver:
                p.setPen(QColor(PAL['white']))
            else:
                p.setPen(QColor(PAL['text_low']))
            p.setFont(bar.font())  # QSS 的 font-size 已由 polish 写入控件字体
            p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)
        p.end()

    def _ribbon_guard_file_tab(self, index):
        """「文件」tab 只是入口：被键盘导航选中时立即退回上一个功能页。

        不 blockSignals，这样 _ribbon_keep_collapsed 仍会收到切换事件，
        折叠态下能把 Qt 自动显示的面板重新收起。
        """
        if getattr(self, '_ribbon_reverting', False):
            return
        if index != self.FILE_TAB_INDEX:
            self._last_ribbon_index = index
            return
        prev = getattr(self, '_last_ribbon_index', self.FILE_TAB_INDEX + 1)
        if prev <= self.FILE_TAB_INDEX or prev >= self.ribbon.count():
            prev = self.FILE_TAB_INDEX + 1
        self._ribbon_reverting = True
        try:
            self.ribbon.setCurrentIndex(prev)
        finally:
            self._ribbon_reverting = False

    def _ribbon_keep_collapsed(self, index):
        """折叠状态下切换选项卡，Qt 会自动显示新页，这里重新收起。"""
        if not self._ribbon_collapsed:
            return
        pane = self._ribbon_pane()
        if pane is not None:
            pane.hide()
        QTimer.singleShot(0, lambda: pane.hide() if pane is not None and self._ribbon_collapsed else None)

    def _ribbon_page(self, tabs, title):
        """每页放进横向自适应滚动容器：窗口够宽时正常铺满，
        变窄时组内按钮保持最小宽度并出现细滚动条，不再被压扁截断。"""
        page = QWidget()
        page.setObjectName('RibbonPage')
        # 普通 QWidget 的 QSS background 默认不绘制（grab/显示均为调色板灰），
        # 必须显式开启 WA_StyledBackground，「上深下浅」渐变才会真正画出来
        page.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName('RibbonScroll')
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(page)
        tabs.addTab(scroll, title)
        self._ribbon_pages.append(page)
        return lay

    def _build_ribbon(self):
        """Word 2019 风格功能区：按组重新摆放散落在工具栏/菜单/右键里的功能。
        全部沿用既有控件与信号，只改变挂载位置；旧 QToolBar 隐藏但保留，
        快捷键与菜单引用不受影响。"""
        tabs = QTabWidget()
        tabs.setObjectName('RibbonTabs')
        bar = tabs.tabBar()
        bar.setObjectName('RibbonTabBar')
        self._ribbon_pages = []
        tabs.setFixedHeight(125)
        self.ribbon = tabs
        self._ribbon_full_height = 125
        self._ribbon_collapsed = False
        # 选项卡文字左对齐：应用级样式表存在时 QStyleSheetStyle 接管标签绘制，
        # drawItemText 固定居中——QSS 的 text-align 与 per-widget QProxyStyle
        # 均被绕过、不会生效（已用间谍样式实证）。因此改为在 eventFilter 里
        # 拦截该 tabBar 的 Paint 事件自绘文字（见 _paint_ribbon_tabs）。
        # QTabBar 是 C++ 内部类，实例上赋值 mouseDoubleClickEvent 不生效，
        # 用事件过滤器捕获双击与 Paint（见 MainWindow.eventFilter）
        bar.installEventFilter(self)
        tabs.currentChanged.connect(self._ribbon_keep_collapsed)
        self._ribbon_fold_btn = QToolButton()
        self._ribbon_fold_btn.setObjectName('RibbonCollapse')
        self._ribbon_fold_btn.setFixedSize(26, 22)
        self._ribbon_fold_btn.setText('⌃')
        self._ribbon_fold_btn.setToolTip('折叠功能区（也可双击选项卡）')
        self._ribbon_fold_btn.clicked.connect(self._toggle_ribbon)
        tabs.setCornerWidget(self._ribbon_fold_btn, Qt.TopRightCorner)
        # 「文件」改为真正的第一个选项卡，与「开始 / 插入 / … / 视图」共用
        # 同一套 QTabBar::tab QSS 和 _paint_ribbon_tabs 自绘文字，字体、颜色、
        # 内边距、hover 底色、选中下划线完全一致（不再是独立的深蓝 QToolButton）。
        # 它的页面是空 QWidget：点击由 eventFilter 拦截后打开后台视图，
        # QTabWidget 的 currentIndex 始终保持在实际的功能页上。
        tabs.addTab(QWidget(), '文件')
        tabs.setTabToolTip(self.FILE_TAB_INDEX,
                           '文件：新建 / 打开 / 保存 / 另存为 / 信息')

        # ---------------- 开始 ----------------
        lay = self._ribbon_page(tabs, '开始')
        g = _RibbonGroup('剪贴板')
        g.add(self._ribbon_button(self.action_03, big=True))
        g.add_column([
            self._ribbon_button(self.action_01),
            self._ribbon_button(self.action_02),
            self._ribbon_button(self.action_undo),
        ])
        g.add_column([
            self._ribbon_button(self.action_redo),
            self._ribbon_small(self.bt_brush, '格式刷'),
            self._ribbon_button(self.action_selectall),
        ])
        lay.addWidget(g)

        g = _RibbonGroup('字体')
        # 字体颜色（大 A）与取色（▾）合成一个 split 按钮组，放在第二行「B 加粗」
        # 的左侧，与 Word 的字体组顺序一致；第一行只保留字体/字号/行距三个下拉。
        dropdowns = [self.combo_fonts, self.combo_fontsize, self.combo_lineheight]
        color_btns = [self.bt_fontcolor, self.bt_color]
        style_btns = [self.bt_bold, self.bt_italic, self.bt_underline,
                      self.bt_upper, self.bt_lower, self.bt_toggle,
                      self.toobar_resetformat, self.toobar_clearformat]
        for c in dropdowns:
            self._ribbon_small(c, style=False)
        for b in color_btns + style_btns:
            self._ribbon_small(b, style=False)
            b.setMinimumWidth(26)
            b.setMaximumWidth(32)
        color_box = QFrame()
        color_box.setObjectName('FontColorGroup')
        color_box.setFrameShape(QFrame.NoFrame)
        color_box.setLineWidth(0)
        # 固定 44px：窄窗口下 QHBoxLayout 会优先压缩 Preferred 尺寸的容器，
        # 曾把 A/▾ 挤成 21px（取色按钮被裁剪），固定宽度后两枚按钮始终完整。
        color_box.setFixedSize(44, 21)
        _color_lay = QHBoxLayout(color_box)
        _color_lay.setContentsMargins(0, 0, 0, 0)
        _color_lay.setSpacing(0)
        for b in color_btns:
            _color_lay.addWidget(b)
        font_rows = self._ribbon_rows([
            dropdowns,                  # 第一行：字体 / 字号 / 行距
            [color_box] + style_btns,   # 第二行：字体颜色组 → B I U X² X₂ … 清除/重置格式
        ])
        # 两行的最小宽度约 270px；不设下限的话，窗口收窄时 QHBoxLayout 会把
        # 第二行控件硬挤到互相重叠（实测 700px 下 B 被压进颜色组 20px）。
        # 固定下限后由 RibbonScroll 横向滚动，字体组始终保持整齐。
        font_rows.setMinimumWidth(280)
        g.add(font_rows)
        lay.addWidget(g)

        g = _RibbonGroup('段落')
        # Word 风格：3×3 纯图标方阵，按钮上的文字全省略，完整名称与用途放 tooltip。
        # 4 个对齐按钮是 checkable，bind=True 保留选中态高亮；纯图标下仍需能看出当前对齐方式。
        _para = (
            (self.toobar_alignl, '左对齐',
             '段落文字靠左对齐（不改变缩进；要贴左请用减少缩进）'),
            (self.toobar_alignc, '居中对齐', '段落文字水平居中'),
            (self.toobar_alignr, '右对齐', '段落文字靠右对齐'),
            (self.toobar_alignj, '两端对齐', '同时对齐左右两端'),
            (self.action_bullet, '项目符号', '添加 / 取消无序列表'),
            (self.action_numberlist, '编号', '添加 / 取消有序列表'),
            (self.action_indent_out, '减少缩进',
             '逐级左移；到 0 时清除全部缩进（含列表与首行缩进）'),
            (self.action_indent_in, '增加缩进', '段落整体右移一级'),
            (self.action_firstline, '首行缩进',
             '首行空 2 字符，再点一次取消'),
        )
        _para_btns = []
        for _a, _name, _desc in _para:
            # tooltip 挂在 action 上而不是按钮上：4 个对齐按钮是 checkable，
            # update_format 里的 setChecked 会让 QToolButton 从 action 重新同步
            # tooltip，直接 setToolTip(btn) 会被冲掉（只剩 action 的名称）。
            _a.setToolTip('%s\n%s' % (_name, _desc))
            _b = self._ribbon_button(_a)
            _b.setObjectName('RibbonIconOnly')
            _b.setToolButtonStyle(Qt.ToolButtonIconOnly)
            _b.setFixedSize(34, 24)
            _b.setIconSize(QSize(18, 18))
            _para_btns.append(_b)
        g.add_grid(_para_btns, 3, spacing=3)
        lay.addWidget(g)

        g = _RibbonGroup('编辑')
        g.add(self._ribbon_button(self.action_find, big=True, label='查找'))
        lay.addWidget(g)

        # 「清空文档」破坏性操作不再强制推到最右侧，改为与其它组一起靠左排列
        # （用户要求该按钮靠左对齐而非置于最右）。
        g = _RibbonGroup('文档')
        clear_btn = self._ribbon_button(self.action_clearscreen, big=True, label='清空文档')
        clear_btn.setStyleSheet(
            'color:#ffb4a2; border:1px solid #6a3a33; border-radius:3px;'
            ' background:#33242a; padding:2px 8px;')
        g.add(clear_btn)
        lay.addWidget(g)
        # 多余横向空间由末尾 stretch 吸收，避免字体 combobox 等控件被拉宽
        lay.addStretch(1)

        # ---------------- 插入 ----------------
        lay = self._ribbon_page(tabs, '插入')
        # 输入模式（联想/撰写阅读/自动补全）：由「开始」页移入「插入」页，
        # 属于编辑行为开关，与图片/表格等插入项就近摆放，顶部不再重复显示
        g = _RibbonGroup('输入模式')
        # 自定义列：开关水平居中、上下留白，比默认紧凑堆叠更通透美观
        _col = QVBoxLayout()
        _col.setContentsMargins(6, 4, 6, 4)
        _col.setSpacing(7)
        _col.addStretch(1)
        for _s in (self.switch_associate, self.switch_writetype, self.switch_autocomplete):
            self._ribbon_small(_s, style=False)
            _s.setMinimumWidth(64)
            _col.addWidget(_s, alignment=Qt.AlignHCenter)
        _col.addStretch(1)
        g.body.addLayout(_col)
        lay.addWidget(g)
        g = _RibbonGroup('图片')
        self._ribbon_small(self.combo_wrap, style=False)
        self._ribbon_small(self.combo_typev, style=False)
        # 插入图片整体缩小约 10%：高 62→56、图标 26→23。
        # 宽度保持 56 不动——再压到 50 时，「插入图片」四个字（12px 下约 44px）
        # 加上左右 QSS padding 12px 就放不下，会被省略号截断。
        _ins_btn = self._ribbon_button(self.action_insertimage, big=True,
                                       label='插入图片')
        _ins_btn.setFixedHeight(56)
        _ins_btn.setIconSize(QSize(23, 23))
        # 特殊字符：改成「上图下字」的竖排按钮，做成和插入图片同尺寸的方块，
        # 再用两条竖线把它从图片/文本控件里独立出来（不再去掉图标）。
        _sym_btn = self._ribbon_button(self.bt_showsymbol, big=True,
                                       label='特殊字符', tip='')
        _sym_btn.setObjectName('RibbonSym')
        _sym_btn.setFixedSize(56, 56)
        _sym_btn.setIconSize(QSize(30, 30))
        # 日期 / 分隔线 从原「文本」分组移入，与 (Num) 排在同一列
        _date_btn = self._ribbon_button(self.action_datetime, label='日期')
        _div_btn = self._ribbon_button(self.action_divider, label='分隔线')
        from PyQt5.QtWidgets import QSizePolicy as _QSP
        for _w in (self.combo_wrap, self.combo_typev, _date_btn, _div_btn):
            _w.setMinimumWidth(100)
            _w.setMaximumWidth(100)
            _w.setFixedHeight(21)
            _w.setSizePolicy(_QSP.Fixed, _QSP.Fixed)
        # 三列等宽（100px）：① 插入图片 + 嵌入型 ｜ ② 特殊字符 + (Num) ｜ ③ 日期/分隔线
        # 两条竖线把第②列夹成独立单元；(Num) 紧随特殊字符下方，两个下拉框因此
        # 与第①列的嵌入型同高、同一水平线，左右两列形成对称
        _col_a = QVBoxLayout()
        _col_a.setContentsMargins(0, 0, 0, 0)
        _col_a.setSpacing(3)
        _col_a.addWidget(_ins_btn, 0, Qt.AlignHCenter)
        _col_a.addWidget(self.combo_wrap, 0, Qt.AlignLeft)
        _col_a.addStretch(1)
        _col_b = QVBoxLayout()
        _col_b.setContentsMargins(0, 0, 0, 0)
        _col_b.setSpacing(3)
        _col_b.addWidget(_sym_btn, 0, Qt.AlignHCenter)
        _col_b.addWidget(self.combo_typev, 0, Qt.AlignLeft)
        _col_b.addStretch(1)
        _col_c = QVBoxLayout()
        _col_c.setContentsMargins(0, 0, 0, 0)
        _col_c.setSpacing(5)
        for _w in (_date_btn, _div_btn):
            _col_c.addWidget(_w, 0, Qt.AlignLeft)
        _col_c.addStretch(1)
        g.body.addLayout(_col_a)
        g.body.addWidget(_RibbonVLine(g))
        g.body.addLayout(_col_b)
        g.body.addWidget(_RibbonVLine(g))
        g.body.addLayout(_col_c)
        lay.addWidget(g)
        g = _RibbonGroup('表格')
        g.add(self._ribbon_button(self.bt_inserttable, big=True, label='插入表格'))
        lay.addWidget(g)
        g = _RibbonGroup('常用模板')
        # 3 行 2 列：5 个模板按钮（最后一行右侧留空）
        g.add_grid([
            self._ribbon_button(a, label=t, bind=False) for a, t in (
                (self.action_21, 'OA模板'),
                (self.action_22, '说明书模板'),
                (self.action_23, '权利要求书'),
                (self.action_24, '复审请求'),
                (self.action_25, '无效宣告'),
            )], 2)
        lay.addWidget(g)
        lay.addStretch(1)

        # ---------------- 批处理 ----------------
        lay = self._ribbon_page(tabs, '批处理')
        # 标记补全、文本整理按钮组已按需求从功能区移除
        #（功能仍在右键菜单「批量文本(E) / 生成模板(H)」与全局快捷键上）
        # 格式类批处理（原「工具→校对」的一键/重置格式 + 「插入→符号与格式」的预设格式）
        g = _RibbonGroup('格式')
        g.add_column([
            self._ribbon_button(self.bt_onekeyformat, label='一键格式'),
            self._ribbon_button(self.bt_defaultformat, label='重置格式'),
            self._ribbon_button(self.tool_formatset, label='预设格式'),
        ])
        lay.addWidget(g)
        lay.addStretch(1)

        # ---------------- 工具 ----------------
        lay = self._ribbon_page(tabs, '工具')
        g = _RibbonGroup('校对')
        # 一键/重置格式、预设格式已移入 批处理→文本整理；「全部替换」按需求移除
        # （功能仍在 编辑(E) 菜单、右键菜单与 Ctrl+Shift+H 上）
        g.add(self._ribbon_button(self.tool_showbook, big=True, label='文本校验'))
        lay.addWidget(g)
        # 「使用帮助」只保留 帮助(H) 菜单与 F1，避免与功能区重复
        g = _RibbonGroup('专利')
        # 两列 × 三行：左侧检索/关系类，右侧附图与 XML 设计调整类
        # 按钮自带文字，不再弹 tooltip（tip='' 显式清空）
        g.add_column([
            self._ribbon_button(self.action_00, label='专利检索', tip=''),
            self._ribbon_button(self.tool_eureka, label='特征关系分析', tip=''),
            self._ribbon_button(self.tool_reexam, label='复审无效', tip=''),
        ])
        g.add_column([
            self._ribbon_button(self.tool_figeditor, label='附图标注', bind=False,
                                tip=''),
            self._ribbon_button(self.tool_adjustfigs, label='调整外观图', bind=False,
                                tip=''),
            self._ribbon_button(self.tool_xmlmodify, label='XML修改', bind=False,
                                tip=''),
        ])
        lay.addWidget(g)
        g = _RibbonGroup('服务')
        g.add(self._ribbon_button(self.tool_designservice, big=True, label='服务信息'))
        g.add(self._ribbon_button(self.tool_ai_settings, big=True, label='AI 接口设置'))
        lay.addWidget(g)
        lay.addStretch(1)

        # ---------------- 视图 ----------------
        lay = self._ribbon_page(tabs, '视图')
        g = _RibbonGroup('窗口布局')
        panels = (self.tool_panel_1, self.tool_panel_2,
                  self.tool_panel_4, self.tool_panel_5)
        # 四个布局按钮铺满分组：功能区高 125 → 组内容区 81px，
        # 2×2 每格 40×40 + 1px 间距正好填满，原来 30×21 会在下方留 39px 空白。
        # 不用 _ribbon_small（它会把高度锁成 21px）。
        for b in panels:
            b.setFixedSize(40, 40)
            b.setIconSize(QSize(24, 24))
        g.add_grid(list(panels), 2)
        lay.addWidget(g)
        g = _RibbonGroup('面板')
        # 4 个面板开关排两列：单列 4 个会超出 81px 的内容区高度
        g.add_column([
            self._ribbon_button(self.dock_mark.toggleViewAction(), label='标记补全'),
            self._ribbon_button(self.dock_keywords.toggleViewAction(), label='关键词补全'),
        ])
        g.add_column([
            self._ribbon_button(self.dock_outline.toggleViewAction(), label='导航'),
            self._ribbon_button(self.dock_party.toggleViewAction(), label='申请人'),
        ])
        lay.addWidget(g)
        lay.addStretch(1)

        # 每组之间画竖分隔线；每页最后一个分组（后面是撑开的空白）不画，避免悬空竖线
        for page in self._ribbon_pages:
            last = None
            for i in range(page.layout().count()):
                w = page.layout().itemAt(i).widget()
                if isinstance(w, _RibbonGroup):
                    last = w
            if last is not None:
                last._divider = False

        # 记录每页的最小宽度，窗口变窄时由滚动容器接管，不压缩按钮
        for page in self._ribbon_pages:
            page.setMinimumWidth(max(page.minimumSizeHint().width(), 200))

        # 功能区挂在顶部工具栏区，横跨整个窗口（在左侧停靠面板之上），
        # 与 Word 2019 的标题栏下方功能区一致。
        holder = QToolBar('功能区')
        holder.setObjectName('RibbonHolder')
        holder.setMovable(False)
        holder.setFloatable(False)
        holder.setAllowedAreas(Qt.TopToolBarArea)
        # 背景由 _apply_ribbon_backdrop() 统一绘制（渐变铺满整条功能区，
        # 顺带盖住右侧 6px / pane 3px / 滚动区 2px 的缝隙）；先给个透明底占位。
        holder.setStyleSheet('QToolBar#RibbonHolder {background: transparent; border:none; padding:0; margin:0; spacing:0;}')
        holder.addWidget(tabs)
        self._ribbon_holder = holder
        self.addToolBar(Qt.TopToolBarArea, holder)
        # 首帧前拿不到页面控件的真实位置，等布局稳定后再换算渐变比例
        QTimer.singleShot(0, self._apply_ribbon_backdrop)
        # QToolBar 不会自动拉伸内部控件，宽度随窗口同步（见 window_change_event）
        tabs.setFixedWidth(max(self.width() - 6, 400))
        tabs.setMinimumWidth(200)   # 不把窗口最小宽度锁死成当前宽度（见 window_change_event）
        # 网络搜索框从标题栏迁到选项卡行末尾（「视图」之后）
        self._attach_ribbon_search()
        # 所有页加完后默认选中「开始」，不能停在「文件」这个空页上
        self._last_ribbon_index = self.FILE_TAB_INDEX + 1
        tabs.setCurrentIndex(self._last_ribbon_index)
        # 键盘导航（Ctrl+Tab / 方向键）同样不允许把「文件」变成当前页
        tabs.currentChanged.connect(self._ribbon_guard_file_tab)
        self.layoutwidget.setRowStretch(1, 1)
        for tb in (self.main_toolbar, self.type_toolbar, self.format_toolbar,
                   self.file_toolbar, self.tools_toolbar, self.tools_toolbar_addition):
            tb.hide()
        # QToolBar.addWidget 用 QWidgetAction 包装控件：控件被迁入功能区时
        # Qt 会自动 hide() 它，且随后隐藏旧工具栏不会恢复，需显式 show。
        for w in (self.combo_typev, self.combo_wrap, self.combo_fonts, self.combo_fontsize,
                  self.combo_lineheight, self.bt_bold, self.bt_italic,
                  self.bt_underline, self.bt_upper, self.bt_lower, self.bt_toggle,
                  self.bt_fontcolor, self.bt_color, self.toobar_resetformat,
                  self.toobar_clearformat, self.bt_brush):
            w.show()

        # 下拉框与 ribbon 同色背景（QSS 不覆盖 QComboBox）
        for _w in (self.combo_typev, self.combo_wrap, self.combo_fonts, self.combo_fontsize, self.combo_lineheight):
            _w.setStyleSheet(
                "QComboBox { background: %s; border: none; "
                "padding: 1px 6px; color: %s; }"
                "QComboBox::drop-down { border: none; width: 18px; background: transparent; }"
                "QComboBox QAbstractItemView { background: %s; color: %s; "
                "selection-background-color: %s; border: 1px solid %s; }"
                % (PAL['panel2'], PAL['text_body'], PAL['panel2'],
                   PAL['text_body'], PAL['accent'], PAL['border']))

    def fn_outline_jump(self, item, column):
        """双击结构导航树节点，跳转到当前编辑器中对应章节标题位置。
        节点文本（如"技术领域"）映射为搜索关键词，在文档中查找并定位光标。
        顶层「说明书 / 权利要求书」节点例外：双击触发权利要求刷新
        （底部刷新按钮已集成到这两个节点文字上）。"""
        # 刷新按钮集成：双击顶层节点 = 刷新（原底部「刷新」按钮的功能）
        if item.parent() is None and item.text(0) in ('说明书', '权利要求书'):
            self.fn_refresh_claims()
            return
        if not self.active_textcomponent:
            return
        title = item.text(0)
        keymap = {
            '技术领域':'技术领域','背景技术':'背景技术','发明内容':'发明内容',
            '附图说明':'附图说明','具体实施方式':'具体实施方式',
            '权利要求书':'权利要求'
        }
        # 发明/实用新型内容：优先匹配发明内容，其次实用新型内容
        if title == '发明/实用新型内容':
            targets = ['发明内容', '实用新型内容']
        else:
            targets = [keymap.get(title, title)]
        doc = self.active_textcomponent.document()
        cursor = QTextCursor(doc)
        for target in targets:
            cursor = doc.find(target, QTextCursor(doc))
            if not cursor.isNull():
                break
        if not cursor.isNull():
            self.active_textcomponent.setTextCursor(cursor)
            self.active_textcomponent.ensureCursorVisible()
    def fn_refresh_claims(self):
        """解析当前文档中的权利要求，构建层级树显示在结构导航中。
        规则：不含"根据权利要求X所述"的为独立权利要求；
        含引用的为从属权利要求，挂到其引用的最小编号权利要求节点下。
        迭代处理多级引用（如权7引权2、权2引权1）。"""
        import re
        # 清空权利要求书节点的子项
        self.root_claims.takeChildren()
        if not self.active_textcomponent:
            return
        text = self.active_textcomponent.toPlainText()
        # 定位"权利要求书"章节：必须独立成行，避免匹配正文中"根据权利要求1"
        m_section = re.search(r'\n\s*(权利要求书|权\s*利\s*要\s*求)\s*\n', text)
        if m_section:
            text = text[m_section.end():]
            # 遇到下一个大章节标题则截断
            m_next = re.search(r'\n\s*(摘要|说明书|技术领域|背景技术|发明内容|附图说明|具体实施方式|实施例)\s*\n', text)
            if m_next:
                text = text[:m_next.start()]
        # 匹配 "N. " 开头的行
        all_items = []
        for m in re.finditer(r'(?:^|\n)\s*(\d+)\s*[\.、．]\s*(.+)', text):
            num = int(m.group(1))
            body = m.group(2).strip()
            if num > 100:
                continue
            all_items.append((num, body))
        # 找不到"权利要求书"标题时，看编号1的内容判断是否为权利要求书
        if not m_section and all_items:
            first_body = all_items[0][1]
            # 编号1像权利要求：以"一种"开头，或含"其特征在于"，或含"根据权利要求"
            looks_like_claim = (
                first_body.startswith(('一种', '本发明', '本实用新型', '本申请', '根据'))
                or '其特征在于' in first_body
                or '根据权利要求' in first_body
            )
            if not looks_like_claim:
                all_items = []
        claims = {num: body for num, body in all_items}
        if not claims:
            QTreeWidgetItem(self.root_claims, ['（未识别到权利要求）'])
            self.tree_outline.expandItem(self.root_claims)
            return
        # 分析引用关系
        children_map = {}  # parent_num -> [child_num]
        independents = []
        for num, body in claims.items():
            cites = [int(x) for x in re.findall(r'根据权利要求\s*([\d、或至]+)\s*所述', body)]
            parsed = []
            for c in cites:
                for p in re.split(r'[或和]|至', str(c)):
                    try: parsed.append(int(p))
                    except: pass
            if not parsed:
                independents.append(num)
            else:
                parent = min(parsed)
                children_map.setdefault(parent, []).append(num)
        # 提取主题名称（"一种XXX"中的XXX）和特征部分（"其特征在于/其特征是"之后）
        def theme_of(body):
            m = re.match(r'(?:一种|本发明|本实用新型|本申请|根据[^，,。]*)?[，,]?\s*(.+)', body)
            t = m.group(1) if m else body
            # 截断到其特征在于之前
            t = re.split(r'其特征(?:在于|是)', t)[0]
            return t[:15].rstrip('，,。；;')
        def feature_of(body):
            m = re.search(r'其特征(?:在于|是)[，,：:]?\s*(.+)', body)
            s = m.group(1).strip() if m else body
            return s
        # 建树：先建独权节点，再递归挂从权
        item_map = {}
        for num in sorted(independents):
            txt = f'{num}. [独]{theme_of(claims[num])}'
            item = QTreeWidgetItem(self.root_claims, [txt])
            item.setToolTip(0, feature_of(claims[num]))
            item_map[num] = item
        # 迭代挂从权（按编号顺序，保证父节点先建）
        pending = set()
        for parent, kids in children_map.items():
            for kid in kids:
                if parent not in item_map:
                    pending.add(kid)
                    continue
                feat = feature_of(claims[kid]).rstrip('，,；;：:')
                txt = f'{kid}. [从]引权{parent}-{feat}'
                item = QTreeWidgetItem(item_map[parent], [txt])
                item.setToolTip(0, feature_of(claims[kid]))
                item_map[kid] = item
        # 处理挂不上的（引用的父权也是从权还没建）——再跑一轮
        for _ in range(5):
            if not pending: break
            for kid in list(pending):
                for parent, kids in children_map.items():
                    if kid in kids and parent in item_map:
                        feat = feature_of(claims[kid]).rstrip('，,；;：:')
                        txt = f'{kid}. [从]引权{parent}-{feat}'
                        item = QTreeWidgetItem(item_map[parent], [txt])
                        item.setToolTip(0, feature_of(claims[kid]))
                        item_map[kid] = item
                        pending.discard(kid)
                        break
        # 仍挂不上的（引用了不存在的权），当独权挂根
        for kid in pending:
            txt = f'{kid}. [?]{theme_of(claims[kid])}'
            item = QTreeWidgetItem(self.root_claims, [txt])
            item.setToolTip(0, feature_of(claims[kid])) 
            item_map[kid] = item
        self.tree_outline.expandItem(self.root_claims)
    def status_dbclick(self,event):
        if 18 <= event.y() <= 21:
            try:
                second_screen = QGuiApplication.screens()[1]
            except:
                second_screen = ''
            try:
                third_screen = QGuiApplication.screens()[2]
            except:
                third_screen = ''
            screen_geometry = QGuiApplication.primaryScreen().geometry()
            screen_width = screen_geometry.width()
            screen_height = screen_geometry.height()
            self.move(self.pos().x(),40)
            if self.pos().x() >= 0 and self.pos().x() < screen_width and self.pos().y() > 0 and self.pos().y() < screen_height:
                self.resize(self.width(),screen_height - 40)
            elif second_screen:
                self.resize(self.width(),second_screen.geometry().height() - 40)
            elif third_screen:
                self.resize(self.width(),third_screen.geometry().height() - 40)
    def fn_brush(self):
        if self.brush_flag == True:
            self.bt_brush.setChecked(False)
            self.brush_flag = False
            self.char_format = ''
        if self.brush_flag == False:
            if self.bt_brush.isChecked():
                cursor = self.active_textcomponent.textCursor()
                self.char_format = cursor.charFormat()
            else:
                if not self.char_format:
                    return
                cursor = self.active_textcomponent.textCursor()
                cursor.mergeCharFormat(self.char_format)
                self.active_textcomponent.mergeCurrentCharFormat(self.char_format)
    def fn_brush_dbclick(self,event):
        if self.brush_flag == False:
            cursor = self.active_textcomponent.textCursor()
            self.char_format = cursor.charFormat()
            self.bt_brush.setChecked(True)
            self.brush_flag = True
    def font_toggle(self):
        cursor = self.active_textcomponent.textCursor()
        select_text = cursor.selectedText()
        if not select_text:
            return
        if self.toggle_flag == 0:
            select_text = select_text.upper()
            self.toggle_flag = 1
        else:
            select_text = select_text.lower()
            self.toggle_flag = 0
        cursor.movePosition(QTextCursor.Left, len(select_text))
        if len(select_text) > 1:
            cursor.deleteChar()
        cursor.deleteChar()
        cursor.insertText(select_text)
    def font_lower(self):
        cursor = self.active_textcomponent.textCursor()
        select_text = cursor.selectedText()
        if not select_text:
            return
        format_sub = QTextCharFormat()
        if self.bt_lower.isChecked():
            format_sub.setVerticalAlignment(QTextCharFormat.AlignSubScript)
        else:
            format_sub.setFontPointSize(12)
        cursor.movePosition(QTextCursor.Left, len(select_text))
        if len(select_text) > 1:
            cursor.deleteChar()
        cursor.deleteChar()
        cursor.setCharFormat(format_sub)
        cursor.insertText(select_text)
    def font_upper(self):
        cursor = self.active_textcomponent.textCursor()
        select_text = cursor.selectedText()
        if not select_text:
            return            
        format_sup = QTextCharFormat()
        if self.bt_upper.isChecked():
            format_sup.setVerticalAlignment(QTextCharFormat.AlignSuperScript)
        else:
            format_sup.setFontPointSize(12)
        cursor.movePosition(QTextCursor.Left, len(select_text))
        if len(select_text) > 1:
            cursor.deleteChar()
        cursor.deleteChar()
        cursor.setCharFormat(format_sup)
        cursor.insertText(select_text)
    def fn_fontsize_down(self):
        if not self.active_textcomponent.textCursor().selectedText():
            self.slider_fontsize.setValue(self.slider_fontsize.value() - 1)
            font_size = self.slider_fontsize.value()
            change_num = int(abs(font_size - 12)*25/3)
            ori_html = self.active_textcomponent.toHtml()
            find_txt = re.findall(rf'font-size:\d+pt',ori_html) + re.findall(rf'font-size:\d+pt',ori_html)
            for _ in find_txt:
                ori_html = ori_html.replace(_,f'font-size:{font_size}pt')
            self.active_textcomponent.setHtml(ori_html)
            if font_size < 12:
                self.label_fontsize.setText(f'{100 - change_num}%')
            else:
                self.label_fontsize.setText(f'{100 + change_num}%')
    def fn_fontsize_up(self):
        if not self.active_textcomponent.textCursor().selectedText():
            self.slider_fontsize.setValue(self.slider_fontsize.value() + 1)
            font_size = self.slider_fontsize.value()
            change_num = int(abs(font_size - 12)*25/3)
            ori_html = self.active_textcomponent.toHtml()
            find_txt = re.findall(rf'font-size:\d\dpt',ori_html) + re.findall(rf'font-size:\dpt',ori_html)
            for _ in find_txt:
                ori_html = ori_html.replace(_,f'font-size:{font_size}pt')
            self.active_textcomponent.setHtml(ori_html)
            if font_size < 12:
                self.label_fontsize.setText(f'{100 - change_num}%')
            else:
                self.label_fontsize.setText(f'{100 + change_num}%')
    def slider_fontsize_changed(self):
        if not self.active_textcomponent.textCursor().selectedText():
            font_size = self.slider_fontsize.value()
            change_num = int(abs(font_size - 12)*25/3)
            ori_html = self.active_textcomponent.toHtml()
            find_txt = re.findall(rf'font-size:\d\dpt',ori_html) + re.findall(rf'font-size:\dpt',ori_html)
            for _ in find_txt:
                ori_html = ori_html.replace(_,f'font-size:{font_size}pt')
            self.active_textcomponent.setHtml(ori_html)
            if font_size < 12:
                self.label_fontsize.setText(f'{100 - change_num}%')
            else:
                self.label_fontsize.setText(f'{100 + change_num}%')
    def on_lineheight_changed(self):
        lh = round(float(self.combo_lineheight.currentText()),1)
        for ed in self.text_editor_array:
            try:
                ed.line_height = lh
            except Exception:
                pass
        ori_html = self.active_textcomponent.toHtml()
        find_txt = re.findall(rf'margin-top:\d\dpx',ori_html) + re.findall(rf'margin-top:\dpx',ori_html)
        for _ in find_txt:
            ori_html = ori_html.replace(_,f'margin-top:{lh*5}px')
        find_txt = re.findall(rf'margin-bottom:\d\dpx',ori_html) + re.findall(rf'margin-bottom:\dpx',ori_html)
        for _ in find_txt:
            ori_html = ori_html.replace(_,f'margin-bottom:{lh*5}px')
        self.active_textcomponent.setHtml(ori_html)

    def default_format(self):
        # 获取光标当前位置
        block_cursor = self.active_textcomponent.textCursor()
        para_line_number = block_cursor.blockNumber()
        total_paragraphs = self.active_textcomponent.document().blockCount()
        if para_line_number + 7 > total_paragraphs:
            para_line_number = total_paragraphs
        else:
            para_line_number += 7

        self.active_textcomponent.setFont(QFont("SimSun", 12))
        format = QTextCharFormat()
        format.setBackground(QColor(Qt.transparent))
        format.setFont(QFont("SimSun", 12))
        format.setFontPointSize(12)
        self.slider_fontsize.setValue(12)
        self.label_fontsize.setText('100%')
        cursor = self.active_textcomponent.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(format)

        format.setFontPointSize(9)
        cursor = self.active_figmark.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(format)

        ori_html = self.active_textcomponent.toHtml()
        find_txt = re.findall(rf'margin-top:\d\dpx',ori_html) + re.findall(rf'margin-top:\dpx',ori_html)
        for _ in find_txt:
            ori_html = ori_html.replace(_,f'margin-top:0px')
        find_txt = re.findall(rf'margin-bottom:\d\dpx',ori_html) + re.findall(rf'margin-bottom:\dpx',ori_html)
        for _ in find_txt:
            ori_html = ori_html.replace(_,f'margin-bottom:0px')
        self.active_textcomponent.clear()
        self.active_textcomponent.setHtml(ori_html)
        self.on_lineheight_changed()
        # 重新定位
        block_cursor.movePosition(QTextCursor.Start)
        for _ in range(para_line_number):
            block_cursor.movePosition(QTextCursor.NextBlock)
        self.active_textcomponent.setTextCursor(block_cursor)
    def one_key_format(self):
        block_cursor = self.active_textcomponent.textCursor()
        para_line_number = block_cursor.blockNumber()
        total_paragraphs = self.active_textcomponent.document().blockCount()
        if para_line_number + 7 > total_paragraphs:
            para_line_number = total_paragraphs
        else:
            para_line_number += 7
        self.fn_reset_allformat()
        format_array = self._format_keywords()

        # 生成关键词列表
        for i in range(1,30):
            format_array.append(f'步骤S{i}')
            format_array.append(f'步骤K{i}')
            format_array.append(f'步骤P{i}')
            format_array.append(f'步骤{i}')
            format_array.append(f'实施例{i}')
            format_array.append(f'区别特征{i}')
            format_array.append(f'区别技术特征{i}')
            format_array.append(f'针对区别技术特征{i}')
            format_array.append(f'对于区别技术特征{i}')
            format_array.append(f'基于区别技术特征{i}，其实际所要解决的技术问题是')
            format_array.append(f'证据{i}')
            format_array.append(f'D{i}')
            format_array.append(f'{i}：')
            # 【新增】匹配中文句号序号 1． 2．
            format_array.append(f'{i}．')
            format_array.append(f'\u2029{i}．')

        for i in range(1,999):
            format_array.append(f'\u2029[%04d]' % i)

        font_format = QTextCharFormat()
        font_format.setFontWeight(QFont.Bold)
        cursor = self.active_textcomponent.textCursor()
        doc_text = self.active_textcomponent.document().toPlainText().replace('\n','\u2029')

        for pat_str in format_array:
            # 判断：如果是序号正则，不escape；普通文本关键词，escape防止正则元字符干扰
            # 简易方案：全部字面匹配，如果你需要正则再单独拆分列表
            pattern = re.compile(re.escape(pat_str))
            matches = pattern.finditer(doc_text)
            for match in matches:
                s = match.start()
                e = match.end()
                cursor.setPosition(s)
                cursor.setPosition(e, QTextCursor.KeepAnchor)
                cursor.mergeCharFormat(font_format)

        self.on_lineheight_changed()
        # 光标回位
        block_cursor.movePosition(QTextCursor.Start)
        for _ in range(para_line_number):
            block_cursor.movePosition(QTextCursor.NextBlock)
        self.active_textcomponent.setTextCursor(block_cursor)

    @staticmethod
    def _split_preset(text):
        """把「预设格式」编辑框的按行文本解析成关键词列表（去空行、保留每条原样）。"""
        return [ln for ln in (text or '').replace('\u2029', '\n').splitlines()
                if ln.strip()]

    def _format_keywords(self):
        """一键格式(F5)使用的关键词表：优先用户在「预设格式」里自定义的，
        未自定义（留空）则回落到 main.py 内置的 FORMAT_ARRAY_BASE。
        自定义内容持久化在 data/settings.json 的 format_preset 字段，不再读取任何 TXT。"""
        custom = self._split_preset(store.main_format_preset())
        return custom if custom else list(FORMAT_ARRAY_BASE)

    def fn_formatset(self):
        """「预设格式」：编辑一键格式(F5)自动加粗的段落标题关键词表。"""
        raw = store.main_format_preset()
        lines = (self._split_preset(raw) if raw.strip()
                 else list(FORMAT_ARRAY_BASE))
        dlg = wf.FenrirDialog(
            self, title='预设格式', kind='info', width=560,
            message='每行一条关键词。「一键格式(F5)」会把文档中匹配到这些词的段落标题自动加粗。',
            detail='设置保存在 data/settings.json；留空或点「恢复内置默认」即使用程序内置表。')
        edit = QTextEdit()
        edit.setPlainText('\n'.join(lines))
        edit.setMinimumHeight(320)
        edit.setPlaceholderText('每行一条关键词，例如：技术领域')
        dlg.add_content(edit)
        dlg.add_button('保存', QDialog.Accepted, primary=True)
        dlg.add_button('恢复内置默认', 2)
        dlg.add_button('取消', QDialog.Rejected)
        dlg.set_hint('共 %d 条' % len(lines))
        code = dlg.exec_()
        if code == QDialog.Accepted:
            text = '\n'.join(self._split_preset(edit.toPlainText()))
            store.set_main_format_preset(text)
            n = len(self._split_preset(text)) or len(FORMAT_ARRAY_BASE)
            self.status.showMessage('> 预设格式已保存：%d 条关键词（F5 生效）' % n, 5000)
        elif code == 2:
            store.set_main_format_preset('')
            self.status.showMessage('> 预设格式已恢复内置默认（%d 条）' % len(FORMAT_ARRAY_BASE), 5000)

    def fn_loadimgs(self):
        # 说明书附图面板已移除，此方法保留为空避免菜单调用报错
        pass
    def clear_select_format(self):
        format = QTextCharFormat()
        format.setForeground(QColor(PAL['text']))
        format.setBackground(QColor(Qt.transparent))
        format.setFontPointSize(12)
        cursor = self.active_textcomponent.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        cursor.setCharFormat(format)
    def fn_bottom_bar(self):
        # 底部内联查找/高亮条（toolbar_bottom）已彻底移除：此前仅从布局移除，却仍作为
        # 子控件浮在编辑器左上角（高亮关键词输入框 + 上下查找按钮 + 区分大小写），
        # 造成“未删干净”的残留。查找/替换仍可用 Ctrl+H（fn_show_find_dialog），
        # 故本方法不再创建该内联栏。
        # 仅保留状态栏缩放控件（− / 滑块 / + / 百分比），由 status.attach_zoom
        # 挂载到状态栏右侧，与底部栏无关。
        font = QFont()
        font.setPointSize(13)

        self.bt_fontsize_down = QPushButton('-')
        self.bt_fontsize_down.setFixedSize(25, 25)
        self.bt_fontsize_down.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.bt_fontsize_down.clicked.connect(self.fn_fontsize_down)
        self.bt_fontsize_down.setFont(font)

        self.slider_fontsize = QSlider(Qt.Horizontal)
        self.slider_fontsize.setRange(2, 22)
        self.slider_fontsize.setValue(12)
        self.slider_fontsize.setTickPosition(QSlider.TicksBelow)  # 设置滑块的刻度位置
        self.slider_fontsize.setFixedWidth(150)
        self.slider_fontsize.valueChanged.connect(self.slider_fontsize_changed)

        self.bt_fontsize_up = QPushButton('+')
        self.bt_fontsize_up.setFixedSize(25, 25)
        self.bt_fontsize_up.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.bt_fontsize_up.clicked.connect(self.fn_fontsize_up)
        self.bt_fontsize_up.setFont(font)

        self.label_fontsize = QLabel('100%')
        self.label_fontsize.setFixedWidth(40)

    # 内联查找/高亮条（search_next / search_back / fn_highlighttxt_change）已随
    # toolbar_bottom 一并移除：相关控件（text_tool_highlight、ck_1）已不存在，
    # 且已无信号连接，属死代码。文档内查找/替换请用 Ctrl+H（fn_show_find_dialog）。

    def fn_menu_bar(self): # 设置与menubar重叠的拖拽控件
        self.dragger_top = QWidget(self)
        self.dragger_top_layout = QHBoxLayout(self.dragger_top)
        self.dragger_top_layout.setContentsMargins(2,10,6,4) # 左 上 右 下
        self.dragger_top.setMouseTracking(True)

        self.dragger_top.setStyleSheet("background-color: black")
        self.dragger_top.setFixedSize(self.width(), 40)
        # 这里用的是父窗口内的相对坐标：x=0 让黑条左右完全贴边
        self.dragger_top.move(0, -6)

        self.dragger_top.mouseDoubleClickEvent = self.dragger_top_dbclick
        self.dragger_top.mousePressEvent = self.start_drag
        self.dragger_top.mouseReleaseEvent = self.window_pressrelease

        self.switch_associate = SwitchBtn('联想', '关闭', False)
        self.switch_associate.setFixedSize(64,20)
        self.switch_associate.setToolTip('联想输入 开/关\n输入对应的附图标记序号，即可弹出对应的附图标记全称\n按空格后根据选定的补全方式自动补全')

        self.switch_writetype = SwitchBtn('撰写', '阅读', False)
        self.switch_writetype.setFixedSize(64,20)
        self.switch_writetype.setToolTip('模式切换 撰写/阅读\n拖拽选择相应文本后，高亮显示所有相同内容\n按住CTRL键可连续选择\nESC键 或 鼠标中键，取消所有高亮内容')

        self.switch_autocomplete = SwitchBtn('补全', '关闭', True)
        self.switch_autocomplete.setFixedSize(64,20)
        self.switch_autocomplete.setToolTip('自动补全 开启/关闭\n不在弹出对应的附图标记输入框\n无需按空格，即可自动补全光标位置之前的附图标记')
        # 开关状态通过信号同步到实例属性，替代模块级全局变量
        self.switch_associate.checkedChanged.connect(lambda checked: setattr(self, 'model_type', '关' if checked else '联想'))
        self.switch_writetype.checkedChanged.connect(lambda checked: setattr(self, 'write_type', '阅读' if checked else '撰写'))
        self.switch_autocomplete.checkedChanged.connect(lambda checked: setattr(self, 'write_auto', '关闭' if checked else '补全'))

        # 左侧占位条：宽度由 _position_top_title() 动态计算，用来补偿标题栏
        # 左右两端控件宽度不对称，使中部文档标题的中心恒等于窗口水平中心。
        self.search_fill_1 = QLabel()
        self.search_fill_1.setText('')
        self.search_fill_1.setMinimumWidth(5)
        self.search_fill_1.setFixedHeight(25)

        # 顶部标题栏中部：当前文档名。原来这个位置是网络搜索框（已移到
        # 功能区选项卡行末尾），文档名则由底部状态栏左侧上移到这里。
        self.top_doc_title = QLabel('文档1')
        self.top_doc_title.setObjectName('TopDocTitle')
        self.top_doc_title.setAlignment(Qt.AlignCenter)
        self.top_doc_title.setFixedHeight(25)
        self.top_doc_title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.top_doc_title.setToolTip('当前文档')

        self.search_box = QLineEdit(self.dragger_top)
        self.search_box.setObjectName('TopSearch')  # 样式统一在 APP_QSS（胶囊形）
        font = QFont()
        font.setPointSize(9)

        self.search_box.setFont(font)
        self.search_box.setPlaceholderText('搜索')
        # 高度对齐标题栏的窗口按钮（22px）：标题栏只有 40 高，上边距 15，
        # 超过 25 会被容器底边裁掉，圆角边框看着像被切了一刀
        self.search_box.setFixedHeight(22)
        # 搜索框现挂在功能区选项卡行末尾（不再占标题栏中部），宽度由
        # _position_ribbon_search() 按最后一个选项卡之后的剩余空间计算。
        self.search_box.setMinimumWidth(120)
        self.search_box.setMaximumWidth(260)
        self.search_box.setClearButtonEnabled(False)   # 用自绘的清空按钮，样式统一
        self.search_box.setToolTip(
            f'网络搜索（Fenrir ver{version}）\n'
            '回车在本地结果面板展示搜索结果，点击结果才打开浏览器\n'
            'Enter 百度　Ctrl+Enter 必应　Shift+Enter 谷歌\n'
            'Ctrl+F 定位到此框　Esc 清空')
        # 框内左右两个图标：放大镜（点击即搜）/ 清空（有内容时出现）
        self._search_go_action = self.search_box.addAction(
            qta.icon('fa5s.search', color='#7d8894'),
            QLineEdit.LeadingPosition)
        self._search_go_action.setToolTip('开始搜索')
        self._search_go_action.triggered.connect(lambda: self.fn_web_search())
        self._search_clear_action = self.search_box.addAction(
            qta.icon('fa5s.times-circle', color='#7d8894'),
            QLineEdit.TrailingPosition)
        self._search_clear_action.setToolTip('清空搜索')
        self._search_clear_action.triggered.connect(self.fn_search_clear)
        self._search_clear_action.setVisible(False)
        self.search_box.keyReleaseEvent = self.fn_search_keyreleaseevent
        self.search_box.keyPressEvent = self.fn_search_keypressEvent
        self.search_box.textChanged.connect(self.fn_search_text_changed)
        self.search_box.setMouseTracking(True)

        # 右侧占位条吃掉剩余空间，把最小化/最大化/关闭按钮继续顶到最右
        self.search_fill_2 = QLabel()
        self.search_fill_2.setText('')
        self.search_fill_2.setMinimumWidth(5)
        self.search_fill_2.setFixedHeight(25)
        self.search_fill_2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.search_fill_1.setMouseTracking(True)
        self.search_fill_2.setMouseTracking(True)     

        # 「清空文档」已迁到功能区「开始」最右侧，标题栏不再保留同功能的 C 按钮。
        self.tool_panel_1 = QPushButton(qta.icon('mdi6.dock-left', color='#cdd9e3'),'')
        self.tool_panel_1.setToolTip('左侧布局')
        self.tool_panel_1.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.tool_panel_1.setFixedSize(30,22)
        self.tool_panel_1.setIconSize(QSize(16,16))
        self.tool_panel_1.clicked.connect(self.fn_distribute_left)

        self.tool_panel_2 = QPushButton(qta.icon('mdi6.dock-top', color='#cdd9e3'),'')
        self.tool_panel_2.setToolTip('顶端布局')
        self.tool_panel_2.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.tool_panel_2.setFixedSize(30,22)
        self.tool_panel_2.setIconSize(QSize(16,16))
        self.tool_panel_2.clicked.connect(self.fn_distribute_top)

        self.tool_panel_4 = QPushButton(qta.icon('mdi6.dock-right', color='#cdd9e3'),'')
        self.tool_panel_4.setToolTip('右侧布局')
        self.tool_panel_4.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.tool_panel_4.setFixedSize(30,22)
        self.tool_panel_4.setIconSize(QSize(16,16))
        self.tool_panel_4.clicked.connect(self.fn_distribute_right)

        self.tool_panel_5 = QPushButton(qta.icon('mdi6.dock-bottom', color='#cdd9e3'),'')
        self.tool_panel_5.setToolTip('底部布局')
        self.tool_panel_5.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.tool_panel_5.setFixedSize(30,22)
        self.tool_panel_5.setIconSize(QSize(16,16))
        self.tool_panel_5.clicked.connect(self.fn_distribute_bottom)

        self.tool_minimize = QPushButton(qta.icon('mdi6.window-minimize', color='#cdd9e3'),'')
        self.tool_minimize.setToolTip('最小化')
        self.tool_minimize.setStyleSheet(
            'QPushButton{border:none;background:transparent;}'
            'QPushButton:hover{background-color:#3d4c5c;}')
        self.tool_minimize.setFixedSize(40,22)
        self.tool_minimize.setIconSize(QSize(16,16))
        self.tool_minimize.clicked.connect(lambda:[self.showMinimized()])

        self.tool_maximize = QPushButton(qta.icon('mdi6.window-maximize', color='#cdd9e3'),'')
        self.tool_maximize.setToolTip('最大化')
        self.tool_maximize.setStyleSheet(
            'QPushButton{border:none;background:transparent;}'
            'QPushButton:hover{background-color:#3d4c5c;}')
        self.tool_maximize.setFixedSize(40,22)
        self.tool_maximize.setIconSize(QSize(16,16))
        self.tool_maximize.clicked.connect(lambda:[self.dragger_top_dbclick(self.event)])

        self.tool_close = QPushButton(qta.icon('mdi6.close', color='#cdd9e3'),'')
        self.tool_close.setToolTip('关闭')
        self.tool_close.setStyleSheet(
            'QPushButton{border:none;background:transparent;}'
            'QPushButton:hover{background-color:#e81123;color:white;}'
            'QPushButton:hover QToolTip{color:white;}')
        self.tool_close.setFixedSize(40,22)
        self.tool_close.setIconSize(QSize(16,16))
        self.tool_close.clicked.connect(lambda:[self.fn_closeEvent(self.event)])

        # 输入模式三个开关已移入功能区「插入」页（避免同一控件在两处重复放置）

        # 左上角品牌名和版本号（纵向堆叠：品牌名在上，版本号在下）
        brand_box = QWidget()
        brand_box.setStyleSheet('background: transparent;')
        # Maximum：宽度锁在 sizeHint，不让 QHBoxLayout 把品牌框拉伸去吃空白，
        # 否则它的宽度会随窗口变化，搜索框的居中计算就失去基准。
        brand_box.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        # 标题栏固定 40px、上下 margin 10/4，内容区只有 26px。原先两行被各压
        # 成 13px 且 spacing=0，Fenrir 与版本号完全贴在一起；这里把品牌框单独
        # 放宽到 30px（黑条可见范围到 bar-y=40，仍留 1px 余量），两行之间留
        # 2px 行距。只加高品牌框不会带动中部文档标题和右侧窗口按钮（实测几何
        # 不变），文档标题的居中计算只用 brand.width()。
        brand_box.setFixedHeight(30)
        self.brand_box = brand_box
        brand_vbox = QVBoxLayout(brand_box)
        brand_vbox.setContentsMargins(0, 0, 0, 0)
        brand_vbox.setSpacing(2)

        self.brand_label = QLabel('Fenrir')
        self.brand_label.setObjectName('BrandLabel')  # 颜色/字号统一在 APP_QSS
        # 品牌名加粗：显式提到 Black(87)，比原来的 bold(75) 粗一档。
        # APP_QSS 中刻意不声明 font-weight，否则 polish 会把这里的字重压回 75。
        _brand_font = QFont(self.brand_label.font())
        _brand_font.setWeight(QFont.Black)
        self.brand_label.setFont(_brand_font)
        self.brand_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.version_label = QLabel(f'V{version}')
        self.version_label.setObjectName('VersionLabel')  # 样式统一在 APP_QSS
        self.version_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        brand_vbox.addWidget(self.brand_label)
        brand_vbox.addWidget(self.version_label)

        self.dragger_top_layout.addWidget(brand_box)
        self.dragger_top_layout.addWidget(self.search_fill_1)
        self.dragger_top_layout.addWidget(self.top_doc_title)
        self.dragger_top_layout.addWidget(self.search_fill_2)
        self.dragger_top_layout.addWidget(self.tool_panel_1)
        self.dragger_top_layout.addWidget(self.tool_panel_2)
        self.dragger_top_layout.addWidget(self.tool_panel_4)
        self.dragger_top_layout.addWidget(self.tool_panel_5)
        self.dragger_top_layout.addWidget(self.tool_minimize)
        self.dragger_top_layout.addWidget(self.tool_maximize)
        self.dragger_top_layout.addWidget(self.tool_close)

        # 搜索相关快捷键（窗口级，不依赖焦点在哪个控件）
        # 只占 Ctrl+F：F3 已用于「插入特殊字符」，不抢
        for seq, handler in (('Ctrl+F', self.fn_search_focus),):
            act = QAction(self)
            act.setShortcut(seq)
            act.setShortcutContext(Qt.WindowShortcut)
            act.triggered.connect(handler)
            self.addAction(act)

        self._position_top_title()

    def set_doc_title(self, name):
        """同步当前文档名。

        显示位置已由底部状态栏左侧改为顶部标题栏中部（Word 2019 风格）；
        状态栏的 lbl_doc 仍保留数据（隐藏显示），以便其它逻辑继续读取。
        """
        name = name or '未命名'
        status = getattr(self, 'status', None)
        if status is not None:
            status.set_doc_name(name)
        title = getattr(self, 'top_doc_title', None)
        if title is not None:
            title.setText(name)
            title.setToolTip('当前文档：%s' % name)

    def _position_top_title(self):
        """让顶部标题栏中部的文档名以窗口水平中心线为轴居中。

        标题栏是 QHBoxLayout：左端品牌名与右端窗口按钮宽度不对称，
        Qt 会把剩余空间均分给两个占位 QLabel，结果中部控件中心偏右
        （离屏实测 1300px 窗口下偏 +65px）。

        固定品牌框与标题宽度，用左侧占位条 search_fill_1 的固定宽度
        补偿两侧差值：标题左边 = 左 margin + 品牌框 + 2×spacing
        + search_fill_1，令它等于 W/2 - tw/2。右侧占位条 Expanding
        吃掉剩余空间、把窗口按钮顶到最右。resize / 首显都会重算。
        """
        lay = getattr(self, 'dragger_top_layout', None)
        title = getattr(self, 'top_doc_title', None)
        if lay is None or title is None:
            return
        W = self.dragger_top.width()
        if W <= 0:
            return
        margins = lay.contentsMargins()
        sp = lay.spacing()
        tw = min(360, max(180, int(W * 0.30)))
        title.setFixedWidth(tw)
        item0 = lay.itemAt(0)
        brand = item0.widget() if item0 is not None else None
        brand_w = brand.width() if brand is not None else 0
        prefix = margins.left() + brand_w + 2 * sp
        f1 = int(round(W / 2.0 - tw / 2.0 - prefix))
        self.search_fill_1.setFixedWidth(max(5, f1))
        lay.activate()

    def _position_search_box(self):
        """兼容旧调用名：搜索框已迁到功能区，这里重算两处位置。"""
        self._position_top_title()
        self._position_ribbon_search()

    def _attach_ribbon_search(self):
        """把网络搜索框挂到功能区选项卡行，位于「视图」等选项卡之后。

        QTabBar 只占选项卡文字所需的宽度（离屏实测 5 个 tab 仅 185px），
        其后到窗口右边缘的空白属于 QTabWidget 本身，因此搜索框必须挂在
        QTabWidget 上，不能挂在 QTabBar 上，否则会被压在选项卡堆里。
        """
        tabs = getattr(self, 'ribbon', None)
        box = getattr(self, 'search_box', None)
        if tabs is None or box is None:
            return
        if box.parent() is not tabs:
            box.setParent(tabs)
        tabs.installEventFilter(self)
        box.show()
        # tabRect 要等 QTabWidget 布局跑完才有真实值，首帧再补算一次
        self._position_ribbon_search()
        QTimer.singleShot(0, self._position_ribbon_search)

    def _position_ribbon_search(self):
        """搜索框紧贴在最后一个选项卡右侧；窄窗口时退到选项卡行右端。"""
        tabs = getattr(self, 'ribbon', None)
        box = getattr(self, 'search_box', None)
        if tabs is None or box is None:
            return
        if box.parent() is not tabs or tabs.width() <= 0:
            return
        bar = tabs.tabBar()
        n = bar.count()
        last_right = bar.tabRect(n - 1).right() if n > 0 else 0
        # 把最后一个 tab 的右边缘、tabBar 顶边换算到 QTabWidget 坐标
        x = bar.mapTo(tabs, QPoint(last_right + 10, 0)).x()
        top_y = bar.mapTo(tabs, QPoint(0, 0)).y()
        fold = getattr(self, '_ribbon_fold_btn', None)
        right = (fold.mapTo(tabs, QPoint(0, 0)).x() - 8
                 if fold is not None else tabs.width() - 34)
        right = min(right, tabs.width() - 8)
        avail = right - x
        w = min(240, max(120, avail))
        if avail < 120:
            x = max(right - 120, 8)      # 不隐藏：Ctrl+F 仍要能用
            w = 120
        y = top_y + max(0, (bar.height() - box.height()) // 2)
        box.setGeometry(x, y, w, box.height())
        box.show()

    def _anchor_search_panel(self):
        """搜索结果面板锚定在搜索框正下方（搜索框现位于功能区选项卡行）。

        用 mapTo 换算到主窗口坐标，不再假定搜索框固定在标题栏 y=30。
        """
        if self.window_search and hasattr(self, 'search_box'):
            box = self.search_box
            anchor = box.mapTo(self, QPoint(0, box.height() + 2))
            self.window_search.move(
                self.pos().x() + anchor.x(), self.pos().y() + anchor.y())

    def fn_distribute_left(self):
        self.dock_mark.setHidden(False)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_mark)
    def fn_distribute_top(self):
        self.dock_mark.setHidden(False)
        self.addDockWidget(Qt.TopDockWidgetArea, self.dock_mark)
    def fn_distribute_right(self):
        self.dock_mark.setHidden(False)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_mark)
    def fn_distribute_bottom(self):
        self.dock_mark.setHidden(False)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_mark)

    def fn_clearscreen(self):
        tab_index = self.tab_widget_text.currentIndex()
        if tab_index < 0 or tab_index >= len(self.tab_name_array):
            return
        name = self.tab_name_array[tab_index]
        reply = wf.ask(
            self, '清空当前文档', f'确定要清空「{name}」的全部内容吗？',
            [('清空', 1, False, True), ('取消', 0)],
            detail='正文与对应的附图标记列表都会被清空，并重置文档名称。'
                   '此操作不可撤销（Ctrl+Z 可撤销正文）。',
            kind='warning', width=450)
        if reply == 1:
            self.active_textcomponent.setText('')
            self.active_figmark.setText('')
            tab_index = self.tab_widget_text.currentIndex()
            self.tab_widget_text.setTabText(tab_index, f'文档{tab_index+1}')
            self.tab_name_array[tab_index] = f'文档{tab_index+1}'
            self._save_tab_names()
            self.set_doc_title(f'文档{tab_index+1}')
            self._refresh_status_bar()
            self.status.showMessage(f'> 已清空「文档{tab_index+1}」', 5000)

    def fn_search_keyreleaseevent(self,event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            return
        elif event.key() == Qt.Key_Escape:
            if self.window_search:
                self.window_search.hide()
    def fn_search_keypressEvent(self,event):
        """顶栏搜索框：Enter 走网络搜索，Esc 清空，其余交给 QLineEdit 原生处理。

        原实现把 cursorPosition() 返回的整数当成 QTextCursor 用
        （cursor.selectedText()／deleteChar()），复制、剪切、粘贴、删除、
        方向键全部抛异常被 except 吞掉（Error 401），等于把查找框的编辑与
        复制功能全部废掉。原生处理顺带修好了从查找框复制/粘贴的问题。
        """
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.fn_web_search(event.modifiers())
            return
        if key == Qt.Key_Escape:
            self.fn_search_clear(focus_editor=True)
            return
        QLineEdit.keyPressEvent(self.search_box, event)

    # ---------------- 顶部搜索框：网络搜索（本地结果面板，点击结果才开浏览器） ----------------

    def fn_search_focus(self):
        """Ctrl+F：定位到搜索框；正文有选中文字时带入作关键词（不超过 60 字）。"""
        try:
            ed = self.active_textcomponent
            sel = ed.textCursor().selectedText().replace('\u2029', ' ').strip()
            if sel and len(sel) <= 60:
                self.search_box.setText(sel)
        except Exception:
            pass
        self.search_box.setFocus(Qt.ShortcutFocusReason)
        self.search_box.selectAll()

    def fn_search_text_changed(self, text=''):
        """只有「清空」按钮跟随内容显隐，输入过程中不做任何本地检索。"""
        try:
            self._search_clear_action.setVisible(bool(text))
        except RuntimeError:
            pass

    def fn_web_search(self, modifiers=None):
        """在本地结果面板中展示网络搜索结果；点击结果才打开浏览器。

        Enter 百度 / Ctrl+Enter 必应 / Shift+Enter 谷歌 仅决定首选引擎，
        任一引擎失败会自动回退，提高联网成功率。
        """
        try:
            keyword = self.search_box.text().strip()
        except RuntimeError:
            return
        if not keyword:
            self.search_box.setFocus(Qt.ShortcutFocusReason)
            try:
                self.status.showMessage('请输入要搜索的内容', 3000)
            except Exception:
                pass
            return
        preferred = 'baidu'
        if modifiers is not None:
            if modifiers & Qt.ControlModifier:
                preferred = 'bing'
            elif modifiers & Qt.ShiftModifier:
                preferred = 'google'
        self.fn_open_search_panel(keyword, preferred)

    def fn_open_search_panel(self, keyword, preferred='bing'):
        """创建/复用本地搜索结果面板并启动搜索。"""
        try:
            if not isinstance(self.window_search, SearchResultPanel):
                self.window_search = SearchResultPanel(self, open_url=self._open_search_url)
            self.window_search.show()
            self.window_search.raise_()
            # 锚定在搜索框正下方（与窗口移动时的定位保持一致）
            self._anchor_search_panel()
            self.window_search.search(keyword, preferred)
        except Exception as e:
            print('Error Code 417', e)

    def _open_search_url(self, url):
        """点击搜索结果时打开浏览器（失败则复制链接）。"""
        ok = False
        try:
            ok = bool(webbrowser.open(url))
        except Exception as e:
            print('Error Code 418', e)
        if ok:
            try:
                self.status.showMessage('> 已打开：%s' % url, 5000)
            except Exception:
                pass
        else:
            try:
                QApplication.clipboard().setText(url)
                self.status.showMessage('> 浏览器未打开，链接已复制到剪贴板', 6000)
            except Exception:
                pass

    def fn_search_clear(self, focus_editor=False):
        try:
            self.search_box.blockSignals(True)
            self.search_box.clear()
            self.search_box.blockSignals(False)
            self._search_clear_action.setVisible(False)
        except RuntimeError:
            pass
        if focus_editor:
            try:
                self.active_textcomponent.setFocus()
            except Exception:
                pass

   
    def fn_undo(self):
        self.active_textcomponent.undo()
    def fn_redu(self):
        self.active_textcomponent.redo()
    
    def fn_texttab_changed(self, *args):
        tab_index = self.tab_widget_text.currentIndex()
        # 选中末尾「+」占位页 = 新建文档，先跳过所有数组索引操作
        if self._is_plus_tab(self.tab_widget_text, tab_index):
            QTimer.singleShot(0, self.fn_add_document)
            return
        if tab_index < 0 or tab_index >= len(self.text_editor_array):
            return
        # 切换文档时收起联想弹窗，避免残留到新文档
        self.fn_hide_completion()
        # 切走前把浮动图位置落盘（set_tab_floats 自带差异判断，不会重复写文件）
        try:
            self._persist_all_floats()
        except Exception:
            pass
        # 两个工具窗口都是独立顶层窗口，切换文档时保持打开
        # （校验窗口会在下方自动同步文档名并重新校验）。
        # 文档标签与左侧标记列表一一对应，切换文档时同步切换列表
        if self.tab_widget_mark.currentIndex() != tab_index:
            self.tab_widget_mark.setCurrentIndex(tab_index)
        for _ in self.tab_count_array:
            if _ <= tab_index:
                tab_index += 1
        self.active_textcomponent = self.text_editor_array[tab_index]
        self.active_figmark = self.mark_editor_array[tab_index]
        try:
            self.fn_refresh_claims()
        except Exception:
            pass

        self.start_drag_pos = (0, 0)
        self.tab_drag_flag = False
        self.active_textcomponent.setOverwriteMode(self._overwrite_mode)
        name_index = self.tab_widget_text.currentIndex()
        self.set_doc_title(
            self.tab_name_array[name_index] if name_index < len(self.tab_name_array)
            else f'文档{name_index + 1}')
        self._refresh_status_bar()
        self._update_cursor_pos()
        # 校验面板动态指向当前文档；切文档**不自动校验**，只清掉上一个文档
        # 的高亮与旧结果、回到待校验态，等用户点击分数盘再校验新文档。
        if self.window_notebook and self.window_notebook.isVisible():
            try:
                self.window_notebook.reset_state()
            except Exception:
                pass

        # 特殊字符窗口不再持有编辑器引用（改为发信号给当前编辑器），
        # 切换文档时无需重建；保持可见并提到最前。
        if self.window_symbol not in (None, '') and self.window_symbol.isVisible():
            self.window_symbol.raise_()

        # 申请人/发明人信息跟随文档切换（每个文档独立一份）
        self._load_party_info()

    # ---------------- 申请人 / 发明人信息 ----------------
    # 粘贴识别不要求固定写法。以下写法都能认：
    #   标签：申请人/专利权人/公司名称/姓名…，社会统一信用代码/身份证号/证件号…，
    #        地址/通讯地址/住址…，邮编，发明人/设计人（含「发明人1」这类编号标签）
    #   分隔：全角半角冒号、有没有冒号都行；Word 表格粘出来的制表符也行
    #   排版：整段一行 / 每个字段一行 / 标签一行内容另起一行
    #   发明人：姓名与号码之间 空格·逗号·顿号·分号·换行·无分隔 都行；
    #          号码可以写在括号里，可以带 1. /（1）/① 编号，姓名和号码可以分行
    #   字符：全角数字字母、圈号（①②③）自动转半角
    _PARTY_TAGS = (
        ('inventor', '发明人姓名'), ('inventor', '发明创造人'),
        ('inventor', '发明人'), ('inventor', '设计人'), ('inventor', '创作人'),
        ('applicant', '申请人姓名'), ('applicant', '申请人名称'),
        ('applicant', '专利申请人'), ('applicant', '公司名称'),
        ('applicant', '单位名称'), ('applicant', '企业名称'),
        ('applicant', '申请人'), ('applicant', '专利权人'),
        # 「姓名」「名称」是弱标签：第一个当申请人，后面再出现就按发明人处理
        ('name', '姓名'), ('name', '名称'),
        ('cert', '社会统一信用代码'), ('cert', '统一社会信用代码'),
        ('cert', '统一信用代码'), ('cert', '信用代码'),
        ('cert', '纳税人识别号'), ('cert', '税务登记号'),
        ('cert', '身份证号码'), ('cert', '身份证号'), ('cert', '证件号码'),
        ('cert', '证件号'), ('cert', '身份证'),
        ('address', '通讯地址'), ('address', '联系地址'), ('address', '详细地址'),
        ('address', '地址'), ('address', '住址'), ('address', '住所'),
        ('postcode', '邮政编码'), ('postcode', '邮编'),
    )
    # 这些词常出现在信息块里，但不是人名
    _PARTY_NAME_STOP = frozenset((
        '姓名', '名字', '身份证', '身份证号', '身份证号码', '号码', '证件号',
        '电话', '手机', '手机号', '邮箱', '地址', '邮编', '邮政编码',
        '性别', '国籍', '出生', '出生日期', '日期', '职务', '单位', '公司',
        '申请人', '发明人', '设计人', '发明', '实用新型', '无', '暂无',
        '不详', '待定', '同上', '第一发明人', '第二发明人', '第三发明人',
    ))

    @staticmethod
    def _norm_party_text(text):
        """归一化粘贴文本：全角→半角、圈号→数字、去零宽字符、统一换行。"""
        import unicodedata
        s = (text or '').replace('\u2029', '\n').replace('\r\n', '\n')
        s = s.replace('\r', '\n')
        # NFKC 一次搞定全角数字/字母/括号/空格和 ①②③ 这类圈号
        s = unicodedata.normalize('NFKC', s)
        s = re.sub(r'[\u200b-\u200f\ufeff\u00a0]', ' ', s)
        return s

    @staticmethod
    def _party_split(text):
        """按标签把文本切成字段块，返回 {'name','cert','address','postcode','inventor'}。

        标签后允许有冒号也可以没有（Word 表格粘出来是「申请人\\t甲公司」）；
        标签前必须是行首、空白或标点，避免把「公司地址是…」正文里的词当标签。

        归并规则（应对用户实际粘贴的各种写法）：
        * 第一个「申请人 / 专利权人 / 公司名称」→ 申请人；
        * 后续出现的「申请人 / 专利权人」→ 其他申请人（多申请人，见 extra_applicants）；
        * 第一个「姓名 / 名称」（没有更强的申请人标签时）→ 申请人；
        * 出现「发明人 / 设计人」之后的所有块 → 发明人；
        * 「姓名」「身份证号」成对重复出现 → 除第一组外都算发明人
          （很多人粘的是「姓名：李四 / 身份证号码：110…」逐人列表，不写「发明人」）。
        """
        # 「发明人1」「申请人2」这类带编号的标签也能认（键名查表时去掉数字）
        pat = '|'.join((re.escape(t) + r'\d*')
                       if t in ('发明人', '申请人', '专利权人') else re.escape(t)
                       for _, t in
                       sorted(MainWindow._PARTY_TAGS, key=lambda x: -len(x[1])))
        key_of = {t: k for k, t in MainWindow._PARTY_TAGS}
        rx = re.compile(r'(?:^|(?<=[\s:,;、]))(%s)(?=[ \t]*[:：]|[ \t]|\n|$)'
                        % pat)
        hits = []
        for m in rx.finditer(text):
            word = m.group(1)
            key = key_of.get(word) or key_of.get(re.sub(r'\d+$', '', word))
            if key:
                hits.append((m.start(), m.end(), key))

        seq = []
        for i, (start, end, key) in enumerate(hits):
            nxt = hits[i + 1][0] if i + 1 < len(hits) else len(text)
            body = re.sub(r'^[ \t]*[:：]', '', text[end:nxt]).strip(' \t\n')
            if body:
                seq.append((key, body))

        fields, inv_parts = {}, []
        app_parts, app_addr_parts, app_zip_parts = [], [], []
        inv_mode = name_done = cert_done = False
        for key, body in seq:
            if key in ('applicant', 'name'):
                if not name_done and not inv_mode:
                    fields['name'] = body
                    name_done = True
                    continue
                if not inv_mode and key == 'applicant':
                    # 第二个及以后的「申请人 / 专利权人」→ 多申请人（不再算发明人）
                    app_parts.append(body)
                    continue
                inv_mode = True          # 第二个「姓名」起算发明人
            elif key == 'inventor':
                inv_mode = True
            elif key == 'cert':
                if not cert_done and not inv_mode:
                    fields['cert'] = body
                    cert_done = True
                    continue
                if not inv_mode:
                    # 还没出现发明人时多出来的证件号 → 归给其他申请人
                    app_parts.append(body)
                    continue
                inv_mode = True
            if inv_mode and key in ('applicant', 'name', 'inventor', 'cert'):
                inv_parts.append(body)
            elif key in ('address', 'postcode') and not fields.get(key):
                fields[key] = body
            elif key in ('address', 'postcode') and not inv_mode:
                # 后续「地址 / 邮编」标签按顺序归后面的申请人
                (app_addr_parts if key == 'address' else app_zip_parts).append(body)
        if inv_parts:
            fields['inventor'] = '\n'.join(inv_parts)
        if app_parts:
            fields['extra_applicants'] = '\n'.join(app_parts)
        if app_addr_parts:
            fields['extra_addresses'] = '\n'.join(app_addr_parts)
        if app_zip_parts:
            fields['extra_postcodes'] = '\n'.join(app_zip_parts)
        return fields

    @staticmethod
    def _party_clean_name(tok):
        """从 token 里剥出人名；不像人名就返回空。"""
        s = re.sub(r'^[\s\d（(]+', '', tok)
        s = re.sub(r'^[)）.、．:：]+', '', s).strip(' .。,;:、')
        s = re.sub(r'(先生|女士|同志)$', '', s)
        if not s or len(s) > 24:
            return ''
        if re.search(r'\d', s):
            return ''
        if s in MainWindow._PARTY_NAME_STOP:
            return ''
        if not re.search(r'[\u4e00-\u9fa5A-Za-z]', s):
            return ''
        return s

    @staticmethod
    def _party_inventors(block):
        """在发明人块里抽出所有 (姓名, 身份证号) 对，顺序保持原样。"""
        if not block:
            return []
        t = block
        # ① 去掉区域内残留的子标签词
        t = re.sub(r'(发明人姓名|发明人\d*|发明人|设计人|创作人'
                   r'|身份证号码|身份证号|证件号码|证件号|身份证)', ' ', t)
        # ② 括号：含号码的留下号码（「李四（110…）」），纯说明的删掉（「（姓名）」）
        t = re.sub(r'[（(]([^（）()]*)[)）]',
                   lambda m: ' %s ' % m.group(1) if re.search(r'\d{6,}', m.group(1))
                   else ' ', t)
        # ③ 去编号：1. / 1、 / (1) / 1)
        t = re.sub(r'(?:^|(?<=[\s,;、]))[（(]?\d{1,2}[）).、．]', ' ', t, flags=re.M)
        # ③b 连字符分隔的「李四-110108…」
        t = re.sub(r'(?<=[\u4e00-\u9fa5·])[-—~](?=\d)', ' ', t)
        t = re.sub(r'(?<=\d)[-—~](?=[\u4e00-\u9fa5])', ' ', t)
        # ④ 姓名与号码粘连（李四110108…）时劈开
        t = re.sub(r'([\u4e00-\u9fa5·]{2,15})([0-9]{6,21}[Xx]?)', r'\1 \2', t)
        num_rx = re.compile(r'(?=[0-9A-Za-z]*\d{6})[0-9A-Za-z]{6,21}')

        pairs, pending, orphans = [], [], []
        for tok in re.split(r'[\s,;、/|]+', t):
            tok = tok.strip(' .。,;:、')
            if not tok:
                continue
            if num_rx.fullmatch(tok):
                num = tok.upper()
                if pending:
                    pairs.append((pending.pop(0), num))
                else:
                    orphans.append(num)
                continue
            nm = MainWindow._party_clean_name(tok)
            if not nm:
                continue
            # 外文名「John Smith」被空格切开，粘回去
            if (pending and re.fullmatch(r'[A-Za-z.]+', nm)
                    and re.fullmatch(r'[A-Za-z.]+', pending[-1])):
                pending[-1] = pending[-1] + ' ' + nm
            else:
                pending.append(nm)
        pairs.extend((nm, '') for nm in pending)
        pairs.extend(('', num) for num in orphans)

        out = []
        for pair in pairs:
            if pair not in out:
                out.append(pair)
        return out

    @staticmethod
    def _parse_party_text(text):
        """识别粘贴的申请人/发明人信息块，返回结构化 dict。"""
        info = {'name': '', 'cert': '', 'address': '', 'postcode': '',
                'inventors': [], 'applicants': []}
        norm = MainWindow._norm_party_text(text)
        if not norm.strip():
            return info
        fields = MainWindow._party_split(norm)

        if fields.get('name'):
            info['name'] = fields['name'].split('\n')[0].strip(' ,;、')

        if fields.get('cert'):
            codes = [t.upper() for t in re.split(r'[\s,;、/|]+', fields['cert'])
                     if re.fullmatch(r'(?=[0-9A-Za-z]*\d{6})[0-9A-Za-z]{6,21}', t)]
            if codes:
                info['cert'] = max(codes, key=len)

        mz = re.search(r'\d{6}', fields.get('postcode', ''))
        if mz:
            info['postcode'] = mz.group(0)

        addr = re.sub(r'\s*\n\s*', ' ', fields.get('address', '')).strip()
        if addr:
            # 地址里的括号邮编：「北京市…88号（邮编100080）」
            mzp = re.search(r'[（(]\s*(?:邮政编码?|邮编|zip)?\s*[:：]?\s*(\d{6})\s*[)）]',
                            addr, re.I)
            if mzp:
                info['postcode'] = info['postcode'] or mzp.group(1)
                addr = (addr[:mzp.start()] + ' ' + addr[mzp.end():]).strip()
            # 地址行尾的 6 位数字也是邮编（「北京市…88号 100080」）
            mz2 = re.search(r'[ \t](\d{6})$', addr)
            if mz2:
                info['postcode'] = info['postcode'] or mz2.group(1)
                addr = addr[:mz2.start()].strip()
            info['address'] = addr

        info['inventors'] = MainWindow._party_inventors(fields.get('inventor', ''))

        # 多个申请人：除第一个外还有「申请人 / 专利权人」标签的逐一识别。
        # 姓名与证件号的配对逻辑和发明人一样（粘连、分行、括号都能配）；
        # 地址 / 邮编按标签出现顺序配给各申请人。
        apps = []
        if info['name'] or info['cert']:
            apps.append((info['name'], info['cert'],
                         info['address'], info['postcode']))
        addrs = [a for a in re.split(r'[\n;；]+', fields.get('extra_addresses', ''))
                 if a.strip()]
        zips = [z for z in re.split(r'[\n;；]+', fields.get('extra_postcodes', ''))
                if z.strip()]
        # 地址行尾的 6 位数字也是邮编（与主申请人地址同一规则）
        for i in range(len(addrs)):
            mz = re.search(r'[ \t](\d{6})$', addrs[i])
            if mz and not (zips[i] if i < len(zips) else ''):
                addrs[i] = addrs[i][:mz.start()].strip()
                if i < len(zips):
                    zips[i] = mz.group(1)
                else:
                    zips.append(mz.group(1))
        have2 = [(a[0], a[1]) for a in apps]
        for i, (nm, num) in enumerate(MainWindow._party_inventors(
                fields.get('extra_applicants', ''))):
            if not (nm or num) or (nm, num) in have2:
                continue
            have2.append((nm, num))
            apps.append((nm, num,
                         addrs[i] if i < len(addrs) else '',
                         zips[i] if i < len(zips) else ''))
        info['applicants'] = apps
        return info

    def _create_party_dock(self):
        """创建「申请人信息」停靠面板：粘贴识别框 + 结构化字段 + 发明人表。"""
        self.dock_party = QDockWidget('')
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        self.text_party_paste = QTextEdit()
        self.text_party_paste.setObjectName('PartyPaste')
        # 只说明「粘贴即可」，不在提示里罗列格式：写格式反而让人以为必须照着写。
        self.text_party_paste.setPlaceholderText('粘贴申请人 / 发明人信息，自动识别')
        self.text_party_paste.setFixedHeight(92)
        v.addWidget(self.text_party_paste)

        app_label = QLabel('申请人（名称 + 证件号 + 地址邮编）')
        app_label.setStyleSheet('color:#8997a5; font-size:11px;')
        v.addWidget(app_label)
        self.table_applicants = QTableWidget(0, 4)
        self.table_applicants.setHorizontalHeaderLabels(
            ['名称', '证件号', '地址', '邮编'])
        self.table_applicants.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        # 证件号/地址列固定宽度，同发明人表：面板一窄就被截断，像识别错了
        self.table_applicants.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Interactive)
        self.table_applicants.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Interactive)
        self.table_applicants.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Interactive)
        self.table_applicants.setColumnWidth(1, 185)
        self.table_applicants.setColumnWidth(2, 185)
        self.table_applicants.setColumnWidth(3, 68)
        self.table_applicants.verticalHeader().setVisible(False)
        self.table_applicants.setMinimumHeight(76)
        v.addWidget(self.table_applicants)

        abtns = QHBoxLayout()
        btn_add_app = QPushButton('+ 添加申请人')
        btn_del_app = QPushButton('− 删除选中')
        btn_as_inv = QPushButton('作为发明人 ➤')
        for b in (btn_add_app, btn_del_app, btn_as_inv):
            b.setFixedHeight(22)
        btn_as_inv.setToolTip(
            '把选中的申请人（名称 + 证件号）加入下方发明人列表')
        btn_add_app.clicked.connect(self._party_add_applicant)
        btn_del_app.clicked.connect(self._party_del_applicant)
        btn_as_inv.clicked.connect(self._party_as_inventor)
        abtns.addWidget(btn_add_app)
        abtns.addWidget(btn_del_app)
        abtns.addStretch(1)
        abtns.addWidget(btn_as_inv)
        v.addLayout(abtns)

        inv_label = QLabel('发明人（姓名 + 身份证号）')
        inv_label.setStyleSheet('color:#8997a5; font-size:11px;')
        v.addWidget(inv_label)
        self.table_inventors = QTableWidget(0, 2)
        self.table_inventors.setHorizontalHeaderLabels(['姓名', '身份证号'])
        self.table_inventors.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        # 身份证号固定一个够放 18 位的宽度：两列都 Stretch 时面板一窄号码就被
        # 截成「1101081990」，看起来像识别错了。
        self.table_inventors.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Interactive)
        self.table_inventors.setColumnWidth(1, 210)
        self.table_inventors.verticalHeader().setVisible(False)
        self.table_inventors.setMinimumHeight(110)
        v.addWidget(self.table_inventors, 1)

        btns = QHBoxLayout()
        btn_add = QPushButton('+ 添加发明人')
        btn_del = QPushButton('− 删除选中')
        btn_clear = QPushButton('清空')
        for b in (btn_add, btn_del, btn_clear):
            b.setFixedHeight(22)
        btn_add.clicked.connect(self._party_add_inventor)
        btn_del.clicked.connect(self._party_del_inventor)
        btn_clear.clicked.connect(self._party_clear)
        btns.addWidget(btn_add)
        btns.addWidget(btn_del)
        btns.addStretch(1)
        btns.addWidget(btn_clear)
        v.addLayout(btns)

        self.dock_party.setWidget(w)
        self.dock_party.setMinimumWidth(36)
        self.dock_party.setMaximumWidth(1000)
        self.dock_party.setHidden(True)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_party)

        # 粘贴识别：防抖后解析填充；字段编辑实时保存到当前文档
        self._party_loading = False
        self._party_paste_timer = QTimer(self)
        self._party_paste_timer.setSingleShot(True)
        self._party_paste_timer.setInterval(400)
        self._party_paste_timer.timeout.connect(self._apply_party_paste)
        # 落盘防抖：字段编辑后 800ms 再写存档（见 _save_party_info）
        self._party_save_timer = QTimer(self)
        self._party_save_timer.setSingleShot(True)
        self._party_save_timer.setInterval(800)
        self._party_save_timer.timeout.connect(self._flush_party_info)
        self.text_party_paste.textChanged.connect(
            self._party_paste_timer.start)
        self.table_applicants.cellChanged.connect(self._save_party_info)
        self.table_inventors.cellChanged.connect(self._save_party_info)
        # 首次载入当前文档已存的信息
        self._load_party_info()

    def _apply_party_paste(self):
        """把粘贴框内容解析成结构化字段并填充（自动识别）。"""
        text = self.text_party_paste.toPlainText()
        if not text.strip():
            return
        info = self._parse_party_text(text)
        if not (info['name'] or info['cert'] or info['address']
                or info['postcode'] or info['inventors']
                or info.get('applicants')):
            # 静默返回会让人以为程序没收到粘贴，明确说一句
            self.status.showMessage('未识别到申请人/发明人信息，请检查粘贴内容', 4000)
            return
        self._party_loading = True
        self.table_applicants.setRowCount(0)
        for nm, num, addr, zc in info.get('applicants') or []:
            self._insert_applicant_row(nm, num, addr, zc)
        self.table_inventors.setRowCount(0)
        for nm, num in info['inventors']:
            r = self.table_inventors.rowCount()
            self.table_inventors.insertRow(r)
            it_name = QTableWidgetItem(nm)
            it_num = QTableWidgetItem(num)
            # 面板窄时号码会被列宽截断，悬停给出完整值，避免「看起来没识别对」
            it_name.setToolTip(nm)
            it_num.setToolTip(num)
            self.table_inventors.setItem(r, 0, it_name)
            self.table_inventors.setItem(r, 1, it_num)
        self._party_loading = False
        self._save_party_info()
        # 说清楚认出了什么：发明人漏识别时用户一眼能看出来，不用去数表格
        got = []
        n_app = len(info.get('applicants') or [])
        if n_app == 1:
            got.append('申请人')
        elif n_app > 1:
            got.append('申请人 %d 个' % n_app)
        if info['address']:
            got.append('地址')
        if info['postcode']:
            got.append('邮编')
        if info['inventors']:
            got.append('发明人 %d 人' % len(info['inventors']))
        msg = ('已识别：' + '、'.join(got)) if got else '未识别到信息'
        if got and not info['inventors']:
            msg += '（未识别到发明人，可点「+ 添加发明人」手动填）'
        self.status.showMessage(msg, 4000)

    def _party_add_inventor(self):
        r = self.table_inventors.rowCount()
        self.table_inventors.insertRow(r)
        self.table_inventors.setCurrentCell(r, 0)

    def _party_del_inventor(self):
        rows = sorted({i.row() for i in self.table_inventors.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.table_inventors.removeRow(r)
        if rows:
            self._save_party_info()

    @staticmethod
    def _table_pairs(table):
        """读出表格里所有非空 (第一列, 第二列) 行。"""
        rows = []
        for r in range(table.rowCount()):
            a = table.item(r, 0)
            b = table.item(r, 1)
            nm = a.text().strip() if a else ''
            num = b.text().strip() if b else ''
            if nm or num:
                rows.append((nm, num))
        return rows

    def _party_add_applicant(self):
        r = self.table_applicants.rowCount()
        self.table_applicants.insertRow(r)
        self.table_applicants.setCurrentCell(r, 0)

    def _read_applicants(self):
        """读出申请人表所有非空行：(名称, 证件号, 地址, 邮编)。"""
        rows = []
        for r in range(self.table_applicants.rowCount()):
            vals = []
            for c in range(4):
                it = self.table_applicants.item(r, c)
                vals.append(it.text().strip() if it else '')
            if any(vals):
                rows.append(tuple(vals))
        return rows

    def _insert_applicant_row(self, nm, num, addr='', zc=''):
        """申请人表追加一行；列宽窄时截断，悬停给完整值。"""
        r = self.table_applicants.rowCount()
        self.table_applicants.insertRow(r)
        for c, val in enumerate((nm, num, addr, zc)):
            it = QTableWidgetItem(val)
            it.setToolTip(val)
            self.table_applicants.setItem(r, c, it)

    def _party_del_applicant(self):
        rows = sorted({i.row() for i in self.table_applicants.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.table_applicants.removeRow(r)
        if rows:
            self._save_party_info()

    def _party_as_inventor(self):
        """把选中的申请人（名称 + 证件号）加入发明人列表。"""
        rows = sorted({i.row()
                       for i in self.table_applicants.selectedIndexes()})
        if not rows:
            # 只有一个申请人时不强求先选中，直接用它
            if self.table_applicants.rowCount() == 1:
                rows = [0]
            else:
                self.status.showMessage(
                    '请先在申请人列表中选中要作为发明人的行', 4000)
                return
        have = set(self._table_pairs(self.table_inventors))
        added = dup = 0
        for r in rows:
            nm_it = self.table_applicants.item(r, 0)
            num_it = self.table_applicants.item(r, 1)
            pair = ((nm_it.text().strip() if nm_it else ''),
                    (num_it.text().strip() if num_it else ''))
            if not (pair[0] or pair[1]):
                continue
            if pair in have:
                dup += 1
                continue
            have.add(pair)
            rr = self.table_inventors.rowCount()
            self.table_inventors.insertRow(rr)
            it_name = QTableWidgetItem(pair[0])
            it_num = QTableWidgetItem(pair[1])
            it_name.setToolTip(pair[0])
            it_num.setToolTip(pair[1])
            self.table_inventors.setItem(rr, 0, it_name)
            self.table_inventors.setItem(rr, 1, it_num)
            added += 1
        if added:
            self._save_party_info()
        if added and dup:
            self.status.showMessage(
                '已加入发明人 %d 人，%d 人已在列表中' % (added, dup), 4000)
        elif dup and not added:
            self.status.showMessage('选中的申请人已在发明人列表中', 4000)

    def _party_clear(self):
        self._party_loading = True
        self.text_party_paste.clear()
        self.table_applicants.setRowCount(0)
        self.table_inventors.setRowCount(0)
        self._party_loading = False
        self._save_party_info()

    def _collect_party_info(self):
        """从界面控件收集当前文档的申请人/发明人信息。"""
        applicants = self._read_applicants()
        inventors = self._table_pairs(self.table_inventors)
        # name/cert/address/postcode 保留为第一个申请人的值：兼容旧存档和旧脚本
        first = applicants[0] if applicants else ('', '', '', '')
        return {'name': first[0], 'cert': first[1],
                'address': first[2], 'postcode': first[3],
                'applicants': applicants, 'inventors': inventors}

    def _save_party_info(self, *args):
        """把当前字段保存到活动文档（每个文档独立一份）。"""
        if getattr(self, '_party_loading', False):
            return
        ed = self.active_textcomponent
        if not hasattr(ed, 'setProperty'):
            return
        ed.setProperty('party_info', self._collect_party_info())
        # 输入框每敲一个字都会触发这里；立刻写盘会把几 MB 的 HTML 重写一遍，
        # 800ms 防抖后再落盘。编辑器属性是即时生效的，界面不受影响。
        timer = getattr(self, '_party_save_timer', None)
        if timer is not None:
            timer.start()

    def _party_tab_index(self):
        """当前文档在存档里的下标（与编辑器数组一一对应）。"""
        try:
            return self.tab_widget_text.currentIndex()
        except Exception:
            return -1

    def _flush_party_info(self):
        """把当前文档的申请人信息写进存档（防抖到点 / 关闭程序时调用）。"""
        idx = self._party_tab_index()
        if idx < 0:
            return
        ed = self.active_textcomponent
        info = ed.property('party_info') if hasattr(ed, 'property') else None
        if isinstance(info, dict):
            store.set_tab_party(idx, info)

    def _load_party_info(self):
        """切换文档时载入该文档的申请人/发明人信息。"""
        if not hasattr(self, 'table_applicants'):
            return
        ed = self.active_textcomponent
        info = ed.property('party_info') if hasattr(ed, 'property') else None
        if not info:
            # 重启后编辑器属性是空的，从存档回填
            idx = self._party_tab_index()
            info = store.get_tab_party(idx) if idx >= 0 else None
            if info and hasattr(ed, 'setProperty'):
                ed.setProperty('party_info', info)
        info = info or {'name': '', 'cert': '', 'address': '',
                        'postcode': '', 'inventors': [], 'applicants': []}
        # 兼容三种旧格式：4 元组 / 2 元组 / 只有单个 name+cert+address 的旧存档
        apps = []
        for a in (info.get('applicants') or []):
            a = tuple(a) + ('',) * max(0, 4 - len(a))
            if any(a[:4]):
                apps.append(a[:4])
        if not apps and (info.get('name') or info.get('cert')):
            apps = [(info.get('name', ''), info.get('cert', ''),
                     info.get('address', ''), info.get('postcode', ''))]
        self._party_loading = True
        self.table_applicants.setRowCount(0)
        for nm, num, addr, zc in apps:
            self._insert_applicant_row(nm, num, addr, zc)
        self.table_inventors.setRowCount(0)
        for nm, num in info.get('inventors', []):
            r = self.table_inventors.rowCount()
            self.table_inventors.insertRow(r)
            it_name = QTableWidgetItem(nm)
            it_num = QTableWidgetItem(num)
            it_name.setToolTip(nm)
            it_num.setToolTip(num)
            self.table_inventors.setItem(r, 0, it_name)
            self.table_inventors.setItem(r, 1, it_num)
        self._party_loading = False

    def fn_marktab_changed(self, *args):
        tab_index = self.tab_widget_mark.currentIndex()
        if self._is_plus_tab(self.tab_widget_mark, tab_index):
            QTimer.singleShot(0, self.fn_add_document)
            return
        if tab_index < 0 or tab_index >= len(self.mark_editor_array):
            return
        # 两个工具窗口都是独立顶层窗口，切换文档时保持打开
        # （校验窗口会在下方自动同步文档名并重新校验）。
        self.active_figmark = self.mark_editor_array[tab_index]
    def dragger_top_dbclick(self,event):
        try:
            y = event.y()
        except:
            y = 0
        if self.window_state == 'max':
            self.window_state = 'normal'
            self.setGeometry(self.window_pos.x(), self.window_pos.y(), self.window_width, self.window_height)
            self.dragger_top.setFixedSize(self.width(), 40)
            self.tool_maximize.setIcon(qta.icon('fa5s.window-maximize', color='white'))
            self.tool_maximize.setToolTip('最大化')
            
        elif self.window_state == 'normal':
            if y and 10 <= y <= 15:
                try:
                    second_screen = QGuiApplication.screens()[1]
                except:
                    second_screen = ''
                try:
                    third_screen = QGuiApplication.screens()[2]
                except:
                    third_screen = ''
                screen_geometry = QGuiApplication.primaryScreen().geometry()
                screen_width = screen_geometry.width()
                screen_height = screen_geometry.height()
                self.move(self.pos().x(),40)
                if self.pos().x() >= 0 and self.pos().x() < screen_width and self.pos().y() > 0 and self.pos().y() < screen_height:
                    self.resize(self.width(),screen_height - 40)
                elif second_screen:
                    self.resize(self.width(),second_screen.geometry().height() - 40)
                elif third_screen:
                    self.resize(self.width(),third_screen.geometry().height() - 40)
            else:
                self.window_state = 'max'
                self.tool_maximize.setIcon(qta.icon('fa5s.window-restore', color='white'))
                self.tool_maximize.setToolTip('向下还原')
                self.window_width = self.width()  # 用于最小化时还原
                self.window_height = self.height()
                self.window_pos = self.pos()
                try:
                    second_screen = QGuiApplication.screens()[1]
                except:
                    second_screen = ''
                try:
                    third_screen = QGuiApplication.screens()[2]
                except:
                    third_screen = ''
                primary_screen = QGuiApplication.primaryScreen()
                screen_geometry = primary_screen.geometry()
                screen_width = screen_geometry.width()
                screen_height = screen_geometry.height()
                if self.pos().x() >= 0 and self.pos().x() < screen_width and self.pos().y() > 0 and self.pos().y() < screen_height:
                    self.setGeometry(screen_geometry)
                    self.dragger_top.setFixedSize(self.width(), 40)
                elif second_screen:
                    self.setGeometry(second_screen.geometry())
                elif third_screen:
                    self.setGeometry(third_screen.geometry())
    # ---------- 拖动缩放的重绘节流 ----------
    # 整窗重绘一次约 50~60ms（800+ 控件 + 文本排版），而拉伸窗口时每个鼠标
    # 移动事件都会触发一次重绘，事件队列迅速积压，边框远远跟不上光标。
    # 所以拖动期间先关掉重绘，只按固定间隔刷新，松手后再做一次完整刷新。
    _LIVE_RESIZE_INTERVAL = 110

    def _live_resize_begin(self):
        if self._live_resize:
            return
        # 先量一次整窗重绘耗时：快的机器（<30ms）照常实时重绘，不需要节流；
        # 只有重绘很慢时才冻结画面、按固定间隔刷新，保证边框跟得上光标。
        if self._live_resize_slow is None:
            _t0 = time.perf_counter()
            self.repaint()
            self._live_resize_slow = (time.perf_counter() - _t0) > 0.03
        if not self._live_resize_slow:
            return
        self._live_resize = True
        self.setUpdatesEnabled(False)
        self._live_resize_timer.start(self._LIVE_RESIZE_INTERVAL)

    def _live_resize_tick(self):
        if not self._live_resize:
            return
        self.setUpdatesEnabled(True)
        self.repaint()
        if self._live_resize:
            self.setUpdatesEnabled(False)
            self._live_resize_timer.start(self._LIVE_RESIZE_INTERVAL)

    def _live_resize_end(self):
        if not self._live_resize:
            return
        self._live_resize = False
        self._live_resize_timer.stop()
        self.setUpdatesEnabled(True)
        self.update()

    def window_change_event(self,event): 
        self.dragger_top.setFixedSize(self.width(), 40)
        # 窗口宽度一变就重算左侧补偿占位条，保持顶部文档标题居中
        self._position_top_title()
        if getattr(self, 'ribbon', None):
            self.ribbon.setFixedWidth(max(self.width() - 6, 400))
            # setFixedWidth 会把「最小宽度」一并锁成当前宽度，而功能区在顶部工具栏里，
            # 于是窗口的最小宽度 = 当前宽度 —— 往左拉右边缘时每帧都在请求更小尺寸却被
            # 拒绝，只剩整窗反复重排重绘，表现为拖动极慢甚至拉不动。这里放开最小值。
            self.ribbon.setMinimumWidth(200)
            # 功能区宽度刚更新，搜索框重新贴到最后一个选项卡之后
            self._position_ribbon_search()
            # 页面控件位置可能随选项卡栏高度变化，重新换算功能区背景渐变比例
            self._apply_ribbon_backdrop()
            # 后台视图（若打开）跟着窗口尺寸重算覆盖区域
            self._position_backstage()
        # 文本校验 / 特殊字符已改为停靠面板：高度、位置由 QMainWindow 布局管理，
        # 窗口缩放时正文自动让位，无需再手动 setFixedHeight / move。
        self._anchor_search_panel()
        # 拉伸窗口时让左/右/上三边边框线跟随窗口边缘（底线已隐藏）
        if hasattr(self, '_edge_bars'):
            self._position_edge_bars()
    def window_pressrelease(self,event):
        self.dragging = False
        self.drag_flag = False
        self._live_resize_end()
        x = event.globalX()
        y = event.globalY()
        primary_screen = QGuiApplication.primaryScreen()
        screen_geometry = primary_screen.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        
        try:
            second_screen = QGuiApplication.screens()[1]
            screen_geometry_2 = second_screen.geometry()
        except:
            second_screen = ''
        try:
            third_screen = QGuiApplication.screens()[2]
            screen_geometry_3 = third_screen.geometry()
        except:
            third_screen = ''

        if x >= 0 and x < screen_width and y > 0 and y < screen_height:
            if x >= 0 and x < 10:
                self.setGeometry(0,40,int(screen_width/2),screen_height - 40)
            elif x >= screen_width - 10:
                self.setGeometry(int(screen_width/2),40,int(screen_width/2),screen_height - 40)
        elif second_screen:
            if (x >= 0 and x >= screen_geometry_2.x() and x < screen_geometry_2.x() + 10) or (x < 0 and x < - screen_geometry_2.width() + 10):# 左半屏
                self.setGeometry(screen_geometry_2.x(),screen_geometry_2.y(),int(screen_geometry_2.width()/2),screen_geometry_2.height() - 40)
            elif (x > 0 and x > screen_geometry_2.x() and x > screen_geometry_2.x() + screen_geometry_2.width() - 10) or (x < 0 and x > - 10): # 右半屏
                self.setGeometry(screen_geometry_2.x() + screen_geometry_2.width()/2,screen_geometry_2.y(),int(screen_geometry_2.width()/2),screen_height - 40)
        elif third_screen:
            if (x >= 0 and x >= screen_geometry_3.x() and x < screen_geometry_3.x() + 10) or (x < 0 and x < - screen_geometry_3.width() + 10):# 左半屏
                self.setGeometry(screen_geometry_3.x(),screen_geometry_3.y(),int(screen_geometry_3.width()/2),screen_geometry_3.height() - 40)
            elif (x > 0 and x > screen_geometry_3.x() and x > screen_geometry_3.x() + screen_geometry_3.width() - 10) or (x < 0 and x > - 10): # 右半屏
                self.setGeometry(screen_geometry_3.x() + screen_geometry_3.width()/2,screen_geometry_3.y(),int(screen_geometry_3.width()/2),screen_height - 40)
        self.dragger_top.setFixedSize(self.width(), 40)
        try: 
            self.window_location.close()
        except:
            pass
        
    def start_drag(self, event):
        self.dragging = True    
        self.old_pos = event.globalPos()
        self.old_x = self.pos().x()
        self.old_y = self.pos().y()
        y = event.y()
        if 10 <= y <= 15: #  上边缘
            self.drag_flag = 'up'
            self.old_height = self.height()
        if self.window_show:self.window_show.close()
        if self.window_table:self.window_table.close() 
    def fn_open_design_tab(self, n):
        """打开进程内设计调整服务的指定标签页。
        1=调整外观图（一键改图） / 2=附图标注（编辑图片） / 3=XML 修改。
        服务按需惰性启动；端口被占用时会自动复用或顺延，详见 design_adjust_service。"""
        label = DESIGN_TAB_LABELS.get(n, '设计调整')
        ok, msg = design_service.ensure_started()
        if not ok:
            wf.notice(self, '设计调整服务',
                      '服务启动失败，无法打开「%s」。' % label,
                      detail=msg, kind='warning', width=440)
            self.status.showMessage('> ' + msg, 8000)
            return
        url = design_service.tab_url(n)
        try:
            webbrowser.open(url)
        except Exception as exc:
            wf.notice(self, '设计调整服务', '无法打开浏览器。',
                      detail='%s\n\n可手动访问：%s' % (exc, url),
                      kind='warning', width=460)
            return
        self.status.showMessage('> 已打开「%s」：%s' % (label, url), 10000)

    def fn_show_figeditor(self):
        """编辑图片 → 附图标注（tab2）"""
        self.fn_open_design_tab(2)

    def fn_show_xmlmodify(self):
        """Qt 主界面新增入口 → XML 修改（tab3）"""
        self.fn_open_design_tab(3)

    def fn_design_service_info(self):
        """展示内嵌处理服务的状态、端口与局域网地址。"""
        ok, msg = design_service.ensure_started()
        local = design_service.tab_url(1)
        lan = design_service.lan_url(1)
        box = wf.FenrirDialog(
            self, title='设计调整服务',
            message='设计调整服务（附图标注 / 调整外观图 / XML 修改）',
            detail='状态：%s\n本机地址：%s\n局域网地址：%s\n\n'
                   '服务已整合进主程序，无需再单独运行 start.vbs；'
                   '关闭主程序时自动停止。'
                   % (design_service.describe(), local, lan),
            kind='info' if ok else 'warning', width=520)
        box.add_button('打开工具首页', 2, primary=True)
        box.add_button('复制局域网地址', 1)
        box.add_button('关闭', 0)
        result = box.exec_()
        if result == 2:
            webbrowser.open(local)
        elif result == 1:
            QApplication.clipboard().setText(lan)
            self.status.showMessage('> 已复制局域网地址：' + lan, 8000)

    def fn_ai_settings(self):
        """「AI 接口设置」：配置火山方舟凭据与 AI 内容校验范围。"""
        if AISettingsDialog(self).exec_() == QDialog.Accepted:
            self.status.showMessage('> AI 接口设置已保存，下一次文本校验生效', 6000)

    def fn_eureka(self):
        """特征关系分析（原 EUREKA）：在内嵌网页端解析特征从属/连接关系，
        生成角度可调的 3D 气泡蛛网图。"""
        self.fn_open_design_tab(4)
    def fn_reexam(self):
        """复审无效：打开内网复审/无效审理服务（端口 5000）。

        先在后台线程以 15 秒超时探测服务可达性：可达才调用系统浏览器打开；
        超时/连接失败则弹窗提示，不再打开打不开的空白页。探测期间界面不卡。
        """
        self._open_url_with_probe(
            "http://192.168.124.40:5000/reexam", timeout=15, title='复审无效')

    def _open_url_with_probe(self, url, timeout=15, title=''):
        """后台探测 url（timeout 秒超时）后打开浏览器，失败则弹窗提示。"""
        probe = _UrlProbe(url, timeout, self)
        def _on_done(ok, err):
            if ok:
                webbrowser.open(url)
            else:
                QMessageBox.warning(
                    self, title or '打开链接',
                    '无法连接 %s\n（等待 %d 秒超时）\n\n%s'
                    % (url, timeout, err))
            probe.deleteLater()
        probe.finished.connect(_on_done)
        probe.start()

    def fn_show_adjust(self):
        """一键改图 → 调整外观图（tab1）"""
        self.fn_open_design_tab(1)


    # 显示批量替换窗口
    def fn_animation(self,widget,start,end):
        widget.setWindowOpacity(0.01)
        self.animation = QPropertyAnimation(widget, b"windowOpacity")
        self.animation.setDuration(600)  # 动画持续时间（毫秒）
        # 淡入效果
        self.animation.setStartValue(start)  # 起始透明度为 0（完全透明）
        self.animation.setEndValue(end)  # 结束透明度为 1（完全不透明）
    def _edge_region_at(self, wx, wy):
        """把「相对窗口左上角」的坐标映射到缩放区域名。

        无边框窗口的边缘被 _edge_bars、QStatusBar 等子控件盖住，鼠标事件先落在
        子控件上；各处若各自用 5px / 12px 硬编码判定，光标提示与实际拖拽就会
        对不上。这里做唯一判定入口：光标与 drag_flag 共用同一套区域。
        """
        W, H = self.width(), self.height()
        c = self.CORNER_SIZE
        e = max(5, getattr(self, '_edge_bar_width', 6))
        if wy >= H - c and wx >= W - c:
            return 'rd'                      # 右下角
        if wy >= H - c and wx <= c:
            return 'ld'                      # 左下角
        if wx <= e:
            return 'left'
        if wx >= W - e:
            return 'right'
        if wy >= H - e:
            return 'down'
        if wy <= e:
            return 'up'
        return None

    def _edge_cursor_at(self, wx, wy):
        """区域 → Qt 光标。依据 Qt 5 官方 Qt::CursorShape 定义：
        SizeFDiagCursor 用于 top-left / bottom-right，SizeBDiagCursor 用于
        top-right / bottom-left；水平、垂直边分别用 SizeHor / SizeVer。
        """
        region = self._edge_region_at(wx, wy)
        if region == 'rd':
            return Qt.SizeFDiagCursor
        if region == 'ld':
            return Qt.SizeBDiagCursor
        if region in ('left', 'right'):
            return Qt.SizeHorCursor
        if region in ('down', 'up'):
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def _edge_hover_cursor(self, widget, event):
        """用全局鼠标坐标换算成窗口坐标后设置光标，直接落在接收事件的子控件上。

        不依赖子控件向父窗口传播，也不依赖父窗口 cursor 的继承，避免状态栏／
        边缘条显示上一次 setCursor 留下的水平或垂直箭头。
        """
        if self.drag_flag:
            return                            # 拖拽中固定光标，不随位置抖动
        wx = event.globalX() - self.pos().x()
        wy = event.globalY() - self.pos().y()
        c = self._edge_cursor_at(wx, wy)
        if widget.cursor().shape() != c:
            widget.setCursor(c)

    def _status_edge_region_at(self, wx, wy):
        """状态栏专用的缩放区域：两个下角 + 最底部窄边框，其余一律不缩放。

        _edge_region_at() 把窗口最底部 6px 都算作 'down'，但状态栏高 28px，
        若整段照搬会让「拖状态栏就缩小窗口」的旧问题回来。这里把 'down'
        收窄到 STATUS_BOTTOM_GRIP px（实测该带无子控件遮挡）；'ld' / 'rd'
        仍沿用角落对角缩放。光标与 drag_flag 共用本方法，保证提示与行为一致。
        """
        region = self._edge_region_at(wx, wy)
        if region in ('ld', 'rd'):
            return region
        if region == 'down' and wy >= self.height() - self.STATUS_BOTTOM_GRIP:
            return 'down'
        return None

    def _status_cursor_at(self, wx, wy):
        region = self._status_edge_region_at(wx, wy)
        if region == 'down':
            return Qt.SizeVerCursor
        if region in ('ld', 'rd'):
            return self._edge_cursor_at(wx, wy)
        return Qt.ArrowCursor

    def _status_drag_resize(self, gx, gy):
        """按 drag_flag 直接缩放窗口（底边竖直 / 两下角对角）。

        与 _wire_edge_bar()._move 同一套规则。这里不把移动事件 ignore 给父窗口，
        而是自己 resize 后 accept：离屏实测鼠标一旦移出状态栏，合成 / 真实
        移动事件都不保证沿父链传播，依赖传播会漏掉拖拽帧。
        """
        min_w = max(440, self.minimumWidth())
        min_h = max(450, self.minimumHeight())
        if self.drag_flag == 'down':
            self.resize(self.width(), max(min_h, gy - self.old_y))
        elif self.drag_flag == 'rd':
            self.resize(max(min_w, gx - self.old_x), max(min_h, gy - self.old_y))
        elif self.drag_flag == 'ld':
            anchor_x = self.old_x + self.old_width
            new_w = max(min_w, anchor_x - gx)
            new_h = max(min_h, gy - self.old_y)
            new_left = gx if new_w > min_w else anchor_x - min_w
            self.move(new_left, self.old_y)
            self.resize(new_w, new_h)

    def _status_release(self, event):
        """松开鼠标：清状态、解除抓取、恢复刷新。"""
        self.drag_flag = False
        grabber = getattr(self, '_status_grabber', None)
        if grabber is not None:
            try:
                grabber.releaseMouse()
            except Exception:
                pass
            self._status_grabber = None
        self._live_resize_end()
        event.accept()

    def _status_mouse_move(self, event):
        """状态栏 / 底部抓手共用：底边显示上下箭头、两下角对角、其余普通箭头。

        非拖拽时只更新光标并 accept（状态栏中部拖拽无响应）；拖拽时按全局
        坐标自行缩放，同样 accept，不依赖向 MainWindow 的事件传播。
        """
        wx = event.globalX() - self.pos().x()
        wy = event.globalY() - self.pos().y()
        if self.drag_flag:
            self._status_drag_resize(event.globalX(), event.globalY())
            event.accept()
            return
        if self._live_resize:          # 兜底：清理被中断的缩放留下的冻结状态
            self._live_resize_end()
        c = self._status_cursor_at(wx, wy)
        for widget in (self.status, getattr(self, 'status_grip', None)):
            if widget is not None and widget.cursor().shape() != c:
                widget.setCursor(c)
        event.accept()

    def mousePressEvent(self,event):
        self.old_x = self.pos().x()
        self.old_y = self.pos().y()
        # 事件可能由子控件 ignore 后传播上来，用全局坐标换算成窗口坐标更可靠
        x = event.globalX() - self.pos().x()
        y = event.globalY() - self.pos().y()
        self.old_width = self.width()
        self.old_height = self.height()
        region = self._edge_region_at(x, y)
        if region:
            self.drag_flag = region
    def mouseReleaseEvent(self,event):
        self.drag_flag = False
        self._live_resize_end()
        try:
            self.window_location.close()
        except:
            pass
    def _position_edge_bars(self):
        # 将四条边框贴在窗体最外边缘，贯穿全宽/全高
        w = self._edge_bar_width
        W, H = self.width(), self.height()
        bars = self._edge_bars
        bars[0].setGeometry(0, 0, w, H)        # 左
        bars[1].setGeometry(W-w, 0, w, H)      # 右
        bars[2].setGeometry(0, 0, W, w)        # 上
        # bars[3]（下边框）已按需求删除，不在此布局；状态栏保留
        for b in bars:
            b.raise_()
        # 上边条、右边条需压过顶部黑色横条 dragger_top 的右端
        bars[2].raise_()
        bars[1].raise_()
        # 状态栏宽度随窗口变化，底部抓手同步铺满整条底边
        self._position_status_grip()

    def _position_status_grip(self):
        """把透明抓手贴在状态栏最底部，并压过状态栏内的按钮 / 滑块。"""
        if not hasattr(self, 'status_grip'):
            return
        h = self.STATUS_BOTTOM_GRIP
        self.status_grip.setGeometry(0, self.status.height() - h,
                                     self.status.width(), h)
        self.status_grip.raise_()

    def _wire_edge_bar(self, bar, edge):
        """把边缘条变成真正的缩放手柄：捕获鼠标按下/移动/释放，
        覆盖底部标签栏/dock 等子控件对窗口边缘事件的拦截。"""
        # 未按下时也要收到 mouseMove，才能随位置切换光标；否则静态 setCursor
        # 会让整条左/右边（含两个下角）一直显示水平箭头。
        bar.setMouseTracking(True)

        def _hover(event):
            if self.drag_flag:
                return                        # 拖拽中保持按下时的光标
            if edge == 'up':
                # 顶部是自定义标题栏，只支持竖直缩放，不做对角
                c = Qt.SizeVerCursor
            else:
                wx = event.globalX() - self.pos().x()
                wy = event.globalY() - self.pos().y()
                c = self._edge_cursor_at(wx, wy)
            if bar.cursor().shape() != c:
                bar.setCursor(c)

        def _press(event):
            self.drag_flag = False
            _hover(event)                     # 先把光标固定成当前区域对应的形状
            self.old_x = self.pos().x(); self.old_y = self.pos().y()
            self.old_width = self.width(); self.old_height = self.height()
            wx = event.globalX() - self.pos().x()
            wy = event.globalY() - self.pos().y()
            if edge in ('left', 'right'):
                # 与 _edge_cursor_at 共用区域判定：底部 CORNER_SIZE 内是下角，
                # 显示对角箭头的同时也确实按对角缩放。
                self.drag_flag = self._edge_region_at(wx, wy) or edge
            elif edge == 'up':
                # 顶部两角由上边条覆盖，只做竖直缩放
                self.drag_flag = 'up'
            bar.grabMouse()
        def _move(event):
            _hover(event)
            # 直接调用 self.mouseMoveEvent 不行（事件坐标相对 bar），
            # 这里手动做缩放：根据 drag_flag 和全局鼠标位置
            gx = event.globalX(); gy = event.globalY()
            min_w, min_h = 440, 450
            if self.drag_flag == 'right':
                nw = max(min_w, gx - self.old_x)
                self.resize(nw, self.old_height)
            elif self.drag_flag == 'left':
                nw = max(min_w, self.old_x + self.old_width - gx)
                self.setGeometry(gx, self.old_y, nw, self.old_height)
            elif self.drag_flag == 'up':
                nh = max(min_h, self.old_y + self.old_height - gy)
                self.setGeometry(self.old_x, gy, self.old_width, nh)
            elif self.drag_flag == 'rd':
                nw = max(min_w, gx - self.old_x)
                nh = max(min_h, gy - self.old_y)
                self.resize(nw, nh)
            elif self.drag_flag == 'ld':
                nw = max(min_w, self.old_x + self.old_width - gx)
                nh = max(min_h, gy - self.old_y)
                self.setGeometry(gx, self.old_y, nw, nh)
        def _release(event):
            self.drag_flag = False
            bar.releaseMouse()
            self._live_resize_end()
            _hover(event)                     # 松手后按当前位置恢复悬停光标
        bar.mousePressEvent = _press
        bar.mouseMoveEvent = _move
        bar.mouseReleaseEvent = _release
        # 初始光标；进入条内后由 _hover 按位置动态覆盖（含两个下角的对角箭头）
        if edge in ('left', 'right'):
            bar.setCursor(Qt.SizeHorCursor)
        else:
            bar.setCursor(Qt.SizeVerCursor)
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_edge_bars'):
            self._position_edge_bars()
    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, '_edge_bars'):
            self._position_edge_bars()
        # 功能区会把 4 个布局按钮 reparent 走，标题栏布局项数在启动过程中
        # 会变化；首帧再算一次，确保文档标题居中、搜索框贴住选项卡末尾
        self._position_top_title()
        self._position_ribbon_search()
        QTimer.singleShot(0, self._position_ribbon_search)
        # 只在首次显示时设定初始比例；之后用户手动拖出的宽度不再被覆盖
        if not getattr(self, '_dock_ratio_applied', False) and hasattr(self, 'dock_mark'):
            self._dock_ratio_applied = True
            self._apply_initial_dock_ratio()

    def _apply_initial_dock_ratio(self):
        """启动时把左侧停靠区设为窗口宽度的 DOCK_INITIAL_RATIO。

        依据 Qt 5 QMainWindow::resizeDocks()：它按给定尺寸重新分配停靠区，
        Qt 默认的分配来自 QDockWidget 内容的 sizeHint，会随字体/DPI 变化。
        这里按「实际显示时的窗口宽度」计算，且只作用于当前可见的左侧 dock
        （dock_keywords 启动即隐藏，不参与分配）。
        """
        target = max(self.dock_mark.minimumWidth(),
                     int(self.width() * self.DOCK_INITIAL_RATIO))
        docks = [d for d in (self.dock_mark, self.dock_outline)
                 if not d.isHidden()]
        if docks:
            self.resizeDocks(docks, [target] * len(docks), Qt.Horizontal)

    def mouseMoveEvent(self, event):
        if self._live_resize and not self.drag_flag:
            # 兜底：拖动被中途打断（丢失释放事件）时不要一直冻结画面
            self._live_resize_end()
        x = event.globalX()
        y = event.globalY()
        # 光标判定用窗口坐标：事件可能由子控件 ignore 后传播上来，
        # event.x()/y() 不能当作主窗口坐标；拖拽中保持按下时的光标不动。
        if not self.drag_flag:
            wx = x - self.pos().x()
            wy = y - self.pos().y()
            c = self._edge_cursor_at(wx, wy)
            if self.cursor().shape() != c:
                self.setCursor(c)
        if self.drag_flag:
            # 缩放期间节流重绘：先冻结画面，只按固定间隔刷新一次
            self._live_resize_begin()
        if self.drag_flag == 'right':
            self.resize(x - self.old_x,self.height())
        elif self.drag_flag == 'left':
            temp_length = x - self.old_x
            # 收到最小宽度后必须把位移一起限死：只夹住 resize、不夹 move 的话，
            # 宽度已经不能再变，窗口却继续跟着光标右移，看起来就变成「拖动窗口」了
            min_w = max(440, self.minimumWidth())
            if temp_length > self.old_width - min_w:
                temp_length = self.old_width - min_w
                x = self.old_x + temp_length
            self.move(x, self.old_y)
            self.resize(self.old_width - temp_length, self.height())
        elif self.drag_flag == 'down':
            self.resize(self.width(),y - self.old_y)
        elif self.drag_flag == 'up':
            temp_height = y - self.old_y
            # 同上：到达最小高度后连位移一起夹住，否则只剩窗口往下滑
            min_h = max(450, self.minimumHeight())
            if temp_height > self.old_height - min_h:
                temp_height = self.old_height - min_h
                y = self.old_y + temp_height
            self.move(self.old_x, y)
            self.resize(self.width(), self.old_height - temp_height)
        elif self.drag_flag in ('rd', 'ld'):
            # 对角缩放：固定「光标所拖对角」另一侧的那个角，被拖的角跟随光标移动。
            #  rd（右下角）→ 固定左上角；ld（左下角）→ 固定右上角。
            #  旧实现两分支都按“左上角固定”写，导致拖左下角时左边缘不动、只能竖直缩放。
            min_w = max(440, self.minimumWidth())
            min_h = max(450, self.minimumHeight())
            new_left = self.old_x
            if self.drag_flag == 'rd':
                new_w = x - self.old_x
                new_h = y - self.old_y
            else:  # ld：右边缘不动，左边缘随光标移动
                anchor_x = self.old_x + self.old_width
                new_w = anchor_x - x
                new_h = y - self.old_y
                new_left = x
            if new_w < min_w:
                new_w = min_w
                new_left = (self.old_x + self.old_width - min_w) if self.drag_flag == 'ld' else self.old_x
            if new_h < min_h:
                new_h = min_h
            self.move(new_left, self.old_y)
            self.resize(new_w, new_h)
        # 左右桌面填充
        primary_screen = QGuiApplication.primaryScreen()
        screen_geometry = primary_screen.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        if not self.window_location:
            self.window_location = QWidget()
            QGridLayout(self.window_location)
            self.window_location.setWindowTitle(f"FENRIR ver{version}")
            self.window_location.setStyleSheet("QWidget { background-color: white; }")
            self.window_location.setWindowFlags(Qt.FramelessWindowHint) # 隐藏标题栏
            self.fn_animation(self.window_location,0.0,0.1)
        try:
            second_screen = QGuiApplication.screens()[1]
            screen_geometry_2 = second_screen.geometry()
        except:
            second_screen = ''
        try:
            third_screen = QGuiApplication.screens()[2]
            screen_geometry_3 = third_screen.geometry()
        except:
            third_screen = ''
        if self.dragging and not self.drag_flag:
            if x >= 0 and x < screen_width and y > 0 and y < screen_height:
                if x == 0 and x < 20 and not self.window_location.isVisible():
                    self.window_location.setGeometry(20,0,int(screen_width/2)- 20,screen_height)
                    self.window_location.show()
                    self.animation.start()
                elif x > 0 and x >= screen_width - 20 and not self.window_location.isVisible():
                    self.window_location.setGeometry(int(screen_width/2),0,int(screen_width/2) - 20,screen_height)
                    self.window_location.show()
                    self.animation.start()
            elif second_screen:
                if (x >= 0 and x >= screen_geometry_2.x() and x < screen_geometry_2.x() + 20) or (x < 0 and x < - screen_geometry_2.width() + 20) and not self.window_location.isVisible():# 左半屏
                    self.window_location.setGeometry(screen_geometry_2.x(),screen_geometry_2.y(),int(screen_geometry_2.width()/2),screen_geometry_2.height())
                    self.window_location.show()
                    self.animation.start()
                elif (x >0 and x > screen_geometry_2.x() and x > screen_geometry_2.x() + screen_geometry_2.width() - 20) or (x < 0 and x > - 20) and not self.window_location.isVisible(): # 右半屏
                    self.window_location.setGeometry(screen_geometry_2.x() + screen_geometry_2.width()/2,screen_geometry_2.y(),int(screen_geometry_2.width()/2),screen_height)
                    self.window_location.show()
                    self.animation.start()
            elif third_screen:
                if (x >= 0 and x >= screen_geometry_3.x() and x < screen_geometry_3.x() + 20) or (x < 0 and x < - screen_geometry_3.width() + 20) and not self.window_location.isVisible():# 左半屏
                    self.window_location.setGeometry(screen_geometry_3.x(),screen_geometry_3.y(),int(screen_geometry_3.width()/2),screen_geometry_3.height())
                    self.window_location.show()
                    self.animation.start()
                elif (x >0 and x > screen_geometry_3.x() and x > screen_geometry_3.x() + screen_geometry_3.width() - 20) or (x < 0 and x > - 20) and not self.window_location.isVisible(): # 右半屏
                    self.window_location.setGeometry(screen_geometry_3.x() + screen_geometry_3.width()/2,screen_geometry_3.y(),int(screen_geometry_3.width()/2),screen_height)
                    self.window_location.show()
                    self.animation.start()
            
            if self.window_location and x > 20 and x < screen_width - 20:
                self.window_location.close()
            elif second_screen:
                if (x > 0 and x >= screen_geometry_2.x() + 20 and x < screen_geometry_2.x() + screen_geometry_2.width() - 20) or (x < 0 and x > - screen_geometry_2.width() + 20 and x < - 20):
                    self.window_location.close()
            elif third_screen:
                if (x > 0 and x >= screen_geometry_3.x() + 20 and x < screen_geometry_3.x() + screen_geometry_3.width() - 20) or (x < 0 and x > - screen_geometry_3.width() + 20 and x < - 20):
                    self.window_location.close()

        
            delta = QPoint(event.globalPos() - self.old_pos)

            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()
            # 工具面板是主窗口的停靠子部件，随窗口一起移动，无需再手动 move
            if self.window_rep:
                self.window_rep.move(self.pos().x() + self.width() - 270,self.pos().y() + 100)
            self._anchor_search_panel()
        # self.window_notebook.activateWindow()
        
    def fn_showhelp(self):
        if not self.window_help:
            self.help_ui()
        if self.window_help.isVisible():
            self.window_help.hide()
        else:
            self.fn_animation(self.window_help,0.0,1.0)
            self.animation.start()
            self.window_help.show()

    def help_ui(self):
        self.window_help = QWidget_Notop('如何使用')
        self.layout_windowhelp = QGridLayout(self.window_help)
        self.window_help.move(400, 200)
        self.window_help.setFixedSize(600, 400)
        bt_1 = QPushButton("功能选择")
        bt_1.setStyleSheet('background-color: #e55f00;color:white')
        bt_1.setFixedSize(100,20)
        bt_close = QPushButton("X")
        bt_close.setToolTip('关闭')
        bt_close.setFixedSize(20,20)
        self.combo_help = QComboBox()
        self.combo_help.addItems(['主界面-联想输入','主界面-附图标记查重','主界面-高亮相同的关键词','主界面-标注相同技术特征','主界面-标记自动同步','主界面-重命名文档',
                                  '主界面-批量替换 CTRL+F','主界面-高亮关键词','主界面-识别文件','主界面-格式化文档','主界面-OCR获取附图标记','主界面-双击查找相同内容','主界面-工具查询',
                                  'AI-文本补全 ALT+Q','AI-AI续写 ALT+W','AI-AI润色 ALT+E','AI-概念查询 Alt+R','AI-AI校验','AI-撰写助理',
                                  '文本校验',
                                  '快捷菜单-批量文本','快捷菜单-生成模板',
                                  '特征比对-一键导入本发明或对比文件',
                                  '图片编辑-添加删除标记','图片编辑-擦除标记','图片编辑-批量标注','图片编辑-转线条图','图片编辑-图像锐化','图片编辑-批量修改图片尺寸'])
        self.combo_help.setCurrentIndex(0)
        self.combo_help.setMinimumWidth(200)
        self.label_help = QLabel()
        self.label_help.setScaledContents(True)

        movie = QMovie(f"./help/主界面-联想输入.gif")
        self.label_help.setMovie(movie)
        self.window_help.setFixedSize(movie.scaledSize())
        movie.start()
        self.layout_windowhelp.addWidget(bt_1,0,0,1,1)
        self.layout_windowhelp.addWidget(self.combo_help,0,1,1,1)
        self.layout_windowhelp.addWidget(bt_close,0,2,1,1)

        self.layout_windowhelp.addWidget(self.label_help,1,0,1,3)

        self.combo_help.currentIndexChanged.connect(self.on_help_changed)
        bt_close.clicked.connect(self.window_help.close)
    def on_help_changed(self):
        try:
            txt = self.combo_help.currentText()
            movie = QMovie(f"./help/{txt}.gif")
            self.label_help.setMovie(movie)
            self.window_help.setFixedSize(movie.scaledSize())
            movie.start()
        except Exception as e:
            print('Error Code 203',e)
    def _ensure_book_window(self):
        """创建或复用「文本校验」独立窗口（懒创建，只定位一次）。"""
        if self.window_notebook in (None, ''):
            self.window_notebook = WindowBook(self)
            # 弹出时不抢主窗口焦点：点浮窗内部才会激活它
            self.window_notebook.setAttribute(Qt.WA_ShowWithoutActivating)
            self._position_tool_window(self.window_notebook, 560)
        return self.window_notebook

    def _ensure_symbol_window(self):
        """创建或复用「特殊字符」独立窗口（懒创建，只定位一次）。"""
        if self.window_symbol in (None, ''):
            panel = SpecialCharPanel()
            panel.snap_target = self          # 拖到主窗口边缘附近时自动吸附
            panel.setAttribute(Qt.WA_ShowWithoutActivating)   # 弹出不抢焦点
            panel.symbolChosen.connect(self._insert_special_char)
            panel.closeRequested.connect(self.symbol_close)
            self.window_symbol = panel
            self._position_tool_window(panel, PANEL_W)
        return self.window_symbol

    def _make_tool_dock(self, which):
        """兼容旧调用点：两个工具现在都是独立窗口，不再有 QDockWidget。

        历史上这里把面板塞进无标题栏 QDockWidget 停在右侧；现行设计是
        「文本校验」「特殊字符」各自一个无边框、可拖动、可缩放的顶层窗口。
        保留函数名，让切文档 / Esc / 旧验证脚本的调用继续有效。
        """
        if which == 'book':
            return self._ensure_book_window()
        return self._ensure_symbol_window()

    def _show_tool_dock(self, which):
        """显示指定工具窗口；两个窗口互斥显示。弹出时高度与主窗口对齐。"""
        panel = self._make_tool_dock(which)
        other = self.window_symbol if which == 'book' else self.window_notebook
        if other not in (None, '') and other.isVisible():
            other.hide()
        return self._popup_tool_window(panel)

    def _hide_tool_dock(self, which=None):
        """隐藏工具窗口，并把左侧标记列表的最小/最大宽度放开。

        ``which='book'`` 是切文档时的历史调用：校验窗口需要保持打开并自动
        重校当前文档，所以这里刻意不隐藏它；只有 ``None``（全部收起）才关。
        """
        if which in (None, 'symbol') and self.window_symbol not in (None, ''):
            self.window_symbol.hide()
        if which is None and self.window_notebook not in (None, ''):
            self.window_notebook.hide()
        self.dock_mark.setMinimumWidth(36)
        self.dock_mark.setMaximumWidth(1000)

    def fn_showbook(self):
        """切换文本校验窗口（复用同一个实例，独立可拖动 / 可缩放）。"""
        panel = self._ensure_book_window()
        if panel.isVisible():
            panel.hide()
            return
        panel.refresh_doc_name()
        # 与特殊字符窗口互斥：打开校验时收起符号窗口
        other = self.window_symbol
        if other not in (None, '') and other.isVisible():
            other.hide()
        self._popup_tool_window(panel)

    def _position_tool_window(self, widget, prefer_w=None, sync_height=False):
        """定位工具窗口：贴主窗口左/右侧；两侧都放不下则悬于左上角。

        ``sync_height=True``（弹出时）自动识别主窗体高度，浮窗高度与主窗口
        保持一致、顶边对齐，形成并排效果；宽度沿用浮窗当前值。
        首次创建传入 ``prefer_w`` 设定设计宽度；之后不再重置宽度。
        """
        try:
            screen = QApplication.primaryScreen().availableGeometry()
        except Exception:
            screen = self.geometry()
        w = prefer_w or widget.width()
        h = widget.height()
        if sync_height:
            h = self.frameGeometry().height()
        h = max(widget.minimumHeight(), min(h, screen.height() - 40))
        main = self.frameGeometry()
        if sync_height:
            top = main.top()          # 高度一致时顶边对齐，并排显示
        else:
            top = max(screen.top() + 8, main.top())
        # ① 右侧：主窗口右缘之外能完整放下
        if main.right() + 1 + w <= screen.right() + 1:
            x = main.right() + 1
        # ② 左侧：主窗口左缘之外能完整放下
        elif main.left() - 1 - w >= screen.left():
            x = main.left() - 1 - w
        # ③ 两侧都没空间：悬于主窗口左上角
        else:
            x, top = main.left(), (main.top() if sync_height else top)
        # 兜底：主窗口比屏幕还宽时角落位可能越界，夹回屏幕内
        x = max(screen.left(), min(x, screen.right() - w + 1))
        widget.setGeometry(x, min(top, screen.bottom() - h + 1), w, h)

    def _popup_tool_window(self, panel, prefer_w=None):
        """弹出工具浮窗：重新贴合主窗口左右侧，高度与主窗口自动对齐。

        每次弹出（首次打开 / F11 退出专注模式 / 切换显示）都执行，
        保证浮窗始终与当前主窗口尺寸配套；拖动 / 缩放仅在浮窗停留期间有效。
        """
        self._position_tool_window(panel, prefer_w, sync_height=True)
        panel.show()
        panel.raise_()
        return panel

    def _raise_tool_windows(self):
        """把可见的工具浮窗抬到主窗口之上（不遮其它程序：普通 Qt.Window
        在本应用失活时会自动落到其他程序之后）。"""
        for w in (self.window_notebook, self.window_symbol):
            if w not in (None, '') and w.isVisible():
                w.raise_()

    def changeEvent(self, event):
        """主窗口获得激活时，把工具浮窗重新抬到主窗口上方。"""
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self._raise_tool_windows()

    def _position_book_window(self, book):
        """兼容旧调用：按设计宽度定位文本校验窗口。"""
        self._position_tool_window(book, 560)
    def fn_reset_allformat(self):# 重置格式
        format = QTextCharFormat()
        format.setBackground(QColor(Qt.transparent))
        self.active_textcomponent.setFont(QFont("SimSun", 12))
        cursor = self.active_textcomponent.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.mergeCharFormat(format)

        format.setFontPointSize(9)
        cursor = self.active_figmark.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(format)
    def change_font_color(self):
        font_format = QTextCharFormat()
        font_format.setForeground(QColor(self.font_color))
        cursor = self.active_textcomponent.textCursor()
        # 记住原始光标位置（用于后续新输入文字的颜色）
        orig_pos = cursor.position()
        select_txt = cursor.selectedText().replace('\n','\u2029')
        if select_txt:
            re_search = QRegExp(select_txt)
            matches = re.finditer(re_search.pattern(), self.active_textcomponent.document().toPlainText().replace('\n','\u2029'))
            for match in matches:
                index = match.start()
                cursor.setPosition(index)
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(select_txt))
                cursor.mergeCharFormat(font_format)
        # 设置光标处的字符格式，使之后新输入的文字使用该颜色
        cursor.setPosition(orig_pos)
        cursor.mergeCharFormat(font_format)
        self.active_textcomponent.setTextCursor(cursor)
    def choose_fontcolor(self,event): # 选择字体颜色
        self.font_color = QColorDialog().getColor().name()
        if not self.font_color:
            self.font_color = '#ff0000'
        self.bt_fontcolor.setStyleSheet(
            "QPushButton { font-family: 'Times New Roman'; font-weight: bold; "
            "font-size: 14px; color: %s; border: none; "
            "border-bottom: 3px solid %s; background: transparent; }"
            "QPushButton:hover { background: #2a3a48; }" % (PAL['text'], self.font_color))
        # 选色后立即应用到当前光标位置，使之后新输入文字使用该颜色
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.font_color))
        cursor = self.active_textcomponent.textCursor()
        cursor.mergeCharFormat(fmt)
        self.active_textcomponent.setTextCursor(cursor)

    def choose_gcolor(self): # 选择背景色
        self.background_color = QColorDialog().getColor().name()
        if self.background_color == '#000000':
            self.choose_gcolor_action.setStyleSheet(f'background-color: {self.background_color}')
            self.active_textcomponent.setStyleSheet(f'background-color: {self.background_color}')
        else:
            self.choose_gcolor_action.setStyleSheet(f'background-color: {self.background_color}')
            self.active_textcomponent.setStyleSheet(f'background-color: {self.background_color}')
    def add_mouse_rightclick(self):  # 右键菜单
        self.action_00 = QAction(QIcon(qta.icon('fa5b.searchengin')),'专利检索')
        # 生成摘要：文本摘要卡图标（右键菜单其他项都有图标，仅它空着）
        self.action_summary = QAction(
            QIcon(qta.icon('mdi6.card-text-outline')), '生成摘要')
        self.action_01 = QAction(QIcon(qta.icon('mdi6.content-cut')),'剪切')
        self.action_02 = QAction(QIcon(qta.icon('ph.copy-fill')),'复制')
        self.action_03 = QAction(QIcon(qta.icon('fa5s.paste')),'粘贴')
        # 原「批量替换」按需求改为「查找」：与功能区「查找」同一图标、同一行为
        self.action_04 = QAction(
            QIcon(qta.icon('mdi6.file-search-outline')), '查找')
        self.action_insertimage = QAction(QIcon(qta.icon('fa5s.image')), '插入图片')
        self.action_insertimage.setToolTip(
            '插入图片（Ctrl+Shift+I）\n'
            '按「插入→图片」里选择的环绕方式放置：嵌入型 / 浮于文字上方 / 衬于文字下方\n'
            '也可以直接把图片文件拖进正文，或 Ctrl+V 粘贴截图')

        
        # 1-7 只保留「编号 + 符号」，含义交给 tooltip / 功能区按钮；第 8 项改名「合并附图标记」
        self.action_11 = QAction('<01> A→A1')
        self.action_12 = QAction('<02> A→A(1)')
        self.action_13 = QAction('<03> 1→A1')
        self.action_14 = QAction('<04> 1→A(1)')
        self.action_15 = QAction('<05> A1/(1)→A')
        self.action_16 = QAction('<06> A1→A(1)')
        self.action_17 = QAction('<07> A(1)→A1')
        self.action_18 = QAction('<08> 合并附图标记')
        self.action_11.setToolTip('名称加序号：把「机架」补成「机架1」')
        self.action_12.setToolTip('名称加括号序号：把「机架」补成「机架（1）」')
        self.action_13.setToolTip('序号加名称：把「1」补成「机架1」')
        self.action_14.setToolTip('序号加括号名称：把「（1）」补成「机架（1）」')
        self.action_15.setToolTip('删除标记（精确）：把「机架1」/「机架（1）」还原成「机架」')
        self.action_16.setToolTip('序号转括号：把「机架1」改成「机架（1）」')
        self.action_17.setToolTip('括号转序号：把「机架（1）」改成「机架1」')
        self.action_18.setToolTip('合并附图标记：把标记面板里的多行标记合并为一整段')
        self.action_19 = QAction('<09> 提取发明内容')
        self.action_110 = QAction('<10> 提取附图标记')
        self.action_111 = QAction('<11> 统一单位')
        self.action_112 = QAction('<12> 统一元素符号')
        self.action_113 = QAction('<13> 删除多余回车')
        self.action_114 = QAction('<14> 删除空格')
        self.action_115 = QAction('<15> 删除段号')
        self.action_116 = QAction('<16> 增加段号')
        self.action_117 = QAction('<17> 模糊删除标记（谨慎使用）')

        # 模板项不带图标（原各项图标风格杂乱且与菜单文字重复，右缘一列图标已删）
        self.action_21 = QAction('<01> OA模板')
        self.action_22 = QAction('<02> 说明书模板')
        self.action_23 = QAction('<03> 权利要求书模板')
        self.action_24 = QAction('<04> 复审请求模板')
        self.action_25 = QAction('<05> 无效宣告模板')

        # 添加快捷键
        self.action_01.setShortcut('Ctrl+X')
        self.action_02.setShortcut('Ctrl+C')
        self.action_03.setShortcut('Ctrl+V')
        self.action_04.setShortcut('Ctrl+Shift+H')   # 查找（原批量替换）

        self.action_11.setShortcut('Ctrl+1')
        self.action_12.setShortcut('Ctrl+2')
        self.action_13.setShortcut('Ctrl+3')
        self.action_14.setShortcut('Ctrl+4')
        self.action_15.setShortcut('Ctrl+5')
        self.action_16.setShortcut('Ctrl+6')
        self.action_17.setShortcut('Ctrl+7')
        self.action_18.setShortcut('Ctrl+8')
        self.action_19.setShortcut('Ctrl+9')
        self.action_110.setShortcut('Ctrl+Q')
        self.action_111.setShortcut('Ctrl+W')
        self.action_112.setShortcut('Ctrl+E')
        self.action_113.setShortcut('Ctrl+R')
        self.action_114.setShortcut('Ctrl+T')
        self.action_115.setShortcut('Ctrl+J')
        self.action_116.setShortcut('Ctrl+G')

        self.action_21.setShortcut('Alt+1')
        self.action_22.setShortcut('Alt+2')
        self.action_23.setShortcut('Alt+3')
        self.action_24.setShortcut('Alt+4')
        self.action_25.setShortcut('Alt+5')

        # ---- 让批处理 / 常用模板等功能快捷键成为「窗口级」快捷键 ----
        # 这些 QAction 之前没有父对象，只在所在功能区按钮可见（即所在页被选中）时
        # 快捷键才生效；于是切到「开始」页快捷键就失效。现挂到主窗口并改用
        # ApplicationShortcut：只要本程序处于活动状态，任何功能区页下都可触发，
        # 真正实现「全局可用」。同时把快捷键写进 tooltip，方便记忆。
        _fn_shortcuts = {
            self.action_11: 'Ctrl+1', self.action_12: 'Ctrl+2', self.action_13: 'Ctrl+3',
            self.action_14: 'Ctrl+4', self.action_15: 'Ctrl+5', self.action_16: 'Ctrl+6',
            self.action_17: 'Ctrl+7', self.action_18: 'Ctrl+8', self.action_19: 'Ctrl+9',
            self.action_110: 'Ctrl+Q', self.action_111: 'Ctrl+W', self.action_112: 'Ctrl+E',
            self.action_113: 'Ctrl+R', self.action_114: 'Ctrl+T', self.action_115: 'Ctrl+J',
            self.action_116: 'Ctrl+G',
            self.action_21: 'Alt+1', self.action_22: 'Alt+2', self.action_23: 'Alt+3',
            self.action_24: 'Alt+4', self.action_25: 'Alt+5',
        }
        for _a, _seq in _fn_shortcuts.items():
            _a.setParent(self)
            self.addAction(_a)
            _a.setShortcutContext(Qt.ApplicationShortcut)
            _old = _a.toolTip()
            if _old and _seq not in _old:
                _a.setToolTip(f'{_old}（{_seq}）')

        self.action_00.triggered.connect(self.fn_searchpatent)
        self.action_summary.triggered.connect(self.fn_gen_summary)
        self.action_01.triggered.connect(self.fn_cut)
        self.action_02.triggered.connect(self.fn_copy)
        self.action_03.triggered.connect(self.fn_paste)
        # 与功能区「查找」一致：打开查找/替换对话框（非批量模式）
        self.action_04.triggered.connect(self.fn_show_find_dialog)
        self.action_insertimage.setShortcut('Ctrl+Shift+I')
        self.action_insertimage.triggered.connect(self.fn_insert_image)
        # 插入图片快捷键全局化（任意功能区页下都可触发）
        self.action_insertimage.setParent(self)
        self.addAction(self.action_insertimage)
        self.action_insertimage.setShortcutContext(Qt.ApplicationShortcut)
        # 批量文本
        self.action_11.triggered.connect(lambda:[self.complete_marknum(0)])
        self.action_12.triggered.connect(lambda:[self.complete_marknum(1)])
        self.action_13.triggered.connect(lambda:[self.complete_markname(0)])
        self.action_14.triggered.connect(lambda:[self.complete_markname(1)])
        self.action_15.triggered.connect(self.delete_figmarks)
        self.action_16.triggered.connect(self.num_to_bracket_num)
        self.action_17.triggered.connect(self.bracket_num2num)
        self.action_18.triggered.connect(self.marks_to_para)
        self.action_19.triggered.connect(self.extract_patent_content)
        self.action_110.triggered.connect(self.extract_figmarks)
        self.action_111.triggered.connect(self.refine_form)
        self.action_112.triggered.connect(self.rep_element)
        self.action_113.triggered.connect(self.del_useless_enters)
        self.action_114.triggered.connect(self.del_spaces)
        self.action_115.triggered.connect(self.del_paranum)
        self.action_116.triggered.connect(self.add_paranum)
        self.action_117.triggered.connect(self.delete_figmarks_mohu)
        # 生成模板
        self.action_21.triggered.connect(self.generate_oa_model)
        self.action_22.triggered.connect(self.generate_description_model)
        self.action_23.triggered.connect(self.generate_claim_model)
        self.action_24.triggered.connect(self.generate_re_model)
        self.action_25.triggered.connect(self.generate_invalid_model)
    def _clipboard_source_widget(self):
        """取当前应参与复制/剪切的文本控件。

        优先取真正有选区的焦点控件（查找框、其他编辑器等），否则回退到
        active_textcomponent。原实现只认 active_textcomponent，一旦用户在
        别的文本框里选中文字再复制，就会去读主编辑器——那里没有选区，
        结果把系统剪贴板写成空内容，浏览器里自然"粘不出东西"。
        """
        fw = QApplication.focusWidget()
        if fw is not None and hasattr(fw, 'textCursor') and fw.textCursor().hasSelection():
            return fw
        target = self.active_textcomponent
        if target not in (None, '') and hasattr(target, 'textCursor'):
            return target
        return None

    @staticmethod
    def _plain_text_from_cursor(cursor):
        """QTextCursor.selectedText() 用 U+2029 表示段落分隔、U+2028 表示换行。

        浏览器 textarea / 记事本 / 各类网页编辑器并不认这两个字符，粘出来
        会变成一行或夹杂怪字符，这里统一还原成真正的换行符 \\n。
        """
        return cursor.selectedText().replace('\u2029', '\n').replace('\u2028', '\n')

    def _put_clipboard(self, cursor):
        """把选区同时以纯文本 + HTML 写入剪贴板，返回写入的纯文本。"""
        plain = self._plain_text_from_cursor(cursor)
        self.clip_txt = plain
        mime = QMimeData()
        mime.setText(plain)                      # text/plain（浏览器/记事本用这个）
        try:
            mime.setHtml(QTextDocumentFragment(cursor).toHtml())
        except Exception:
            pass
        self.mime_data = mime                     # 保持引用，避免被回收后剪贴板失效
        clipboard = QApplication.clipboard()
        clipboard.setMimeData(mime, QClipboard.Clipboard)
        if not clipboard.text():                  # 兜底：极端情况下只写纯文本
            clipboard.setText(plain)
        return plain

    def fn_copy(self):
        target = self._clipboard_source_widget()
        if target is None:
            return
        cursor = target.textCursor()
        if not cursor.hasSelection():
            # 没有选区就直接返回：绝不能碰系统剪贴板，否则会把它清空，
            # 用户随后在网页里粘贴就什么都没有（"复制了却粘不出来"）。
            return
        plain = self._put_clipboard(cursor)
        try:
            self.status.showMessage(f'> 已复制 {len(plain)} 个字符', 3000)
        except Exception:
            pass
    def fn_gen_summary(self):
        """从说明书全文提取内容生成摘要（300字以内）
        结构：技术领域 + 技术问题 + 技术方案（主要部件）+ 有益效果"""
        txt = self.active_textcomponent.toPlainText()
        if not txt.strip():
            return
        def extract_section(name, next_names):
            """按章节标题提取段落内容"""
            pat = r'(?:\n\s*' + name + r'\s*\n)(.+?)(?=\n\s*(?:' + '|'.join(next_names) + r')\s*\n|\Z)'
            m = re.search(pat, txt, re.S)
            return m.group(1).strip() if m else ''
        sections = ['技术领域','背景技术','发明内容','附图说明','具体实施方式','权利要求书','摘要']
        # 1. 技术领域
        field = extract_section('技术领域', ['背景技术','发明内容','附图说明','具体实施方式','权利要求书'])
        # 取前两句
        field = re.split(r'[。；]', field)
        field = '。'.join(field[:2]).rstrip('。') + '。' if field else ''
        # 2. 背景技术中的问题
        bg = extract_section('背景技术', ['发明内容','附图说明','具体实施方式','权利要求书'])
        problem = ''
        for kw in ['存在','缺点','不足','问题','难以','无法','导致']:
            m = re.search(r'[^。；]*' + kw + r'[^。；]*[。；]', bg)
            if m:
                problem = m.group(0).strip()
                break
        # 3. 技术方案：独立权利要求1 或 发明内容
        claim1 = ''
        m = re.search(r'\n\s*1[\.、]\s*(.+?)(?=\n\s*2[\.、]|\Z)', txt, re.S)
        if m:
            claim1 = m.group(1).strip()
        # 提取主要部件
        feats = []
        for m in re.finditer(r'(?:包括|设有|具有|设置有)([\u4e00-\u9fa5]{2,8}(?:、[\u4e00-\u9fa5]{2,8}){0,4})', txt):
            for part in m.group(1).split('、'):
                part = part.strip()
                if part and part not in feats and len(part) >= 2:
                    feats.append(part)
        # 4. 有益效果
        effect = ''
        m = re.search(r'(?:有益效果|技术效果)[：:。]?\s*(.+?)(?=\n\s*[\u4e00-\u9fa5]{2,10}\n|\Z)', txt, re.S)
        if m:
            effect = m.group(1).strip()
            effect = re.split(r'[。；]', effect)
            effect = '。'.join(effect[:2]).rstrip('。') + '。' if effect else ''
        # 拼接
        parts = []
        if field:
            parts.append(field)
        if problem:
            parts.append('针对上述问题，' + problem.rstrip('。') + '。')
        if claim1:
            if '其特征在于' in claim1:
                pre, feat = claim1.split('其特征在于', 1)
                parts.append(pre.strip().rstrip('。') + '，')
                parts.append('其特征在于，' + feat.strip().rstrip('。'))
            else:
                parts.append(claim1.rstrip('。'))
        elif feats:
            parts.append('主要包括' + '、'.join(feats[:5]) + '。')
        if effect:
            parts.append(effect)
        summary = ''.join(parts)
        if len(summary) > 300:
            summary = summary[:300].rstrip('，。、；') + '。'
        # 插入到当前光标处
        self.active_textcomponent.textCursor().insertText(summary)
    def fn_searchpatent(self):
        try:
            self.search_url = 'https://www.iprdb.com/s?q='
            self.select_txt = self.active_textcomponent.textCursor().selectedText()
            webbrowser.open(f"{self.search_url}={self.select_txt}")
        except:
            pass
    def fn_cut(self):
        target = self._clipboard_source_widget()
        if target is None:
            return
        cursor = target.textCursor()
        if not cursor.hasSelection():
            return
        # 原实现只写 text/html（没有纯文本），浏览器/记事本粘贴时拿不到内容；
        # 这里与 fn_copy 共用同一套写入逻辑，保证两种格式都在。
        self._put_clipboard(cursor)
        cursor.deleteChar()
    def fn_paste(self):
        cursor = self.active_textcomponent.textCursor()
        clipboard = QApplication.clipboard()
        cursor.removeSelectedText()
        text = clipboard.text(QClipboard.Clipboard)
        cursor.insertText(text)
    def fn_show_symbol(self):
        """F3：切换特殊字符独立窗口（可拖动 / 可缩放，与校验窗口互斥）。"""
        panel = self._ensure_symbol_window()
        if panel.isVisible():
            panel.hide()
            return
        other = self.window_notebook
        if other not in (None, '') and other.isVisible():
            other.hide()
        self._popup_tool_window(panel)

    def symbol_close(self):
        self._hide_tool_dock('symbol')

    def symbol_ui(self):
        """创建或复用「特殊字符」窗口（完整实现见 src/special_chars.py）。

        面板只发信号，由 `_insert_special_char` 取「当前」编辑器做字面插入；
        窗口定位见 `_position_tool_window()`，此处不再 move / setFixedHeight。
        """
        return self._make_tool_dock('symbol')

    def _insert_special_char(self, text, caret_back=0):
        """把符号插入「当前」编辑器；用 insertText 而不是 insertHtml。

        insertHtml 会把 <> 当成标签吞掉、把 & 当实体解析；字面插入原样保留，
        且沿用光标处字符格式。成对括号按 caret_back 把光标退到中间。
        """
        editor = self.active_textcomponent
        if not editor or not text:
            return
        cursor = editor.textCursor()
        cursor.insertText(text)
        if caret_back:
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor,
                                min(int(caret_back), len(text)))
        editor.setTextCursor(cursor)
        editor.setFocus()
        editor.ensureCursorVisible()
    def fn_insert_table(self):
        self.window_table = QWidget()
        self.layout_windowtable = QGridLayout(self.window_table)
        self.window_table.setWindowTitle("表格")
        self.window_table.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_table.move(self.pos().x() + 125,self.pos().y() + 55)
        self.window_table.setFixedSize(250, 180)
        self.window_table.setWindowFlags(Qt.FramelessWindowHint) # 隐藏标题栏
        self.label_array = [QLabel() for _ in range(100)]
        for idx, lbl in enumerate(self.label_array):
            lbl.setStyleSheet('QLabel {background-color: white ; color:white} QLabel:hover {background-color: #6a7c91}')
            lbl.setFixedSize(15, 10)
            lbl.enterEvent = self.label_on_enter
            lbl.mousePressEvent = self.insert_tabel
            self.layout_windowtable.addWidget(lbl, idx // 10, idx % 10, 1, 1)
        self.label_square = QLabel('')
        self.label_square.setFixedHeight(25)
        self.label_square.setFont(QFont('Times', 12))
        self.layout_windowtable.addWidget(self.label_square,10,3,1,5)
        self.fn_animation(self.window_table,0.0,1.0)
        self.animation.start()
        self.window_table.show()

    def label_on_enter(self,event):
        self.table_x = int((QCursor().pos().x() - self.window_table.pos().x() - 13) / 22) + 1
        self.table_y = int((QCursor().pos().y() - self.window_table.pos().y() - 11) / 15) + 1
        if self.table_x == 11:
            self.table_x = 10
        if self.table_y == 11:
            self.table_y = 10
        for idx, lbl in enumerate(self.label_array):
            row, col = idx // 10, idx % 10
            bg = '#6a7c91' if (row < self.table_y and col < self.table_x) else 'white'
            lbl.setStyleSheet(f'QLabel {{background-color: {bg}}}')

        self.label_square.setText(f'{self.table_x}  X  {self.table_y}')
    def insert_tabel(self,event):
        self.window_table.close()
        rows = []
        for row in range(self.table_y):
            cells = ''.join(
                f'<td>column {c + 1}</td>' if row == 0 else '<td></td>'
                for c in range(self.table_x)
            )
            rows.append(f'<tr>{cells}</tr>')
        table_html = "<table border='1'>" + ''.join(rows) + '</table>'

        cursor = self.active_textcomponent.textCursor()
        cursor.insertHtml('\n' + table_html)

    def insert_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择要导入的图片", "", "JPEG Files(*.jpg);;PNG Files (*.png);;BMP Files(*.bmp);;All files (*.*)")
        if not file_path:
            return
        else:
            try:
                image = QImage(file_path)
                width = image.width()
                height = image.height()
                if width >= height:
                    height = int(height / (width/400))
                    width = 400

                else:
                    width = int(width / (height/400))
                    height = 400

            except Exception as e:
                print('Error Code 204',e)
                # 将图片转换为HTML格式，并将其插入到TextEdit中
            cursor = self.active_textcomponent.textCursor()
            html = f"<img src=\"{file_path}\" alt=\"{os.path.basename(file_path)}\" width=\"{width}\" height=\"{height}\" />"
            cursor.insertHtml(html)
 
    # ================= 文档标签页：数量、命名、新建 / 关闭 =================
    def _read_tab_names(self):
        """从统一草稿存档恢复文档数量与名称。

        名称个数即文档个数：默认至少 DOC_TAB_COUNT 个，用户通过「+」新增后
        写入的名称会在下次启动时自动恢复，最多 MAX_DOC_TAB_COUNT 个。
        """
        names = [n.strip() for n in store.main_names()][:MAX_DOC_TAB_COUNT]
        # 只丢弃末尾空项，中间的空格子保留位置并回填默认名，避免序号错位
        while names and not names[-1]:
            names.pop()
        count = max(DOC_TAB_COUNT, len(names))
        return [(names[i] or f'文档{i + 1}') if i < len(names)
                else f'文档{i + 1}' for i in range(count)]

    def _save_tab_names(self):
        try:
            store.set_main_names(self.tab_name_array)
        except Exception as e:
            print('Error Code 604', e)

    def _add_plus_tab(self, tabs):
        """标签栏末尾的「+」占位页，点击等价于新建文档。"""
        placeholder = QWidget()
        placeholder.setObjectName('PlusTabPlaceholder')
        tabs.addTab(placeholder, '+')
        tabs.tabBar().setTabToolTip(tabs.count() - 1, '新建文档')

    def _guard_tabbar_wheel(self, bar):
        """接管标签栏的滚轮行为（由 MainWindow.eventFilter 统一处理）。

        QTabBar 默认把滚轮事件当成「切换上一个/下一个选项卡」。指针停在
        「文档1~10」的标签上滚动时，选中项会被一路推到末尾的「+」占位页；
        而「+」的选中又等价于「新建文档」，于是滚一下滚轮就凭空多出一个文档，
        且新建的文档只能从末尾逐个关闭，看起来像关不掉。
        处理规则见 eventFilter：文档标签栏在指针悬停于文档名称标签上时
        滚轮切换文档（绝不落到「+」页），「+」页/空白处及标记列表标签栏
        仍完全吞掉滚轮。
        """
        bar.setProperty('NoWheelSwitch', True)
        bar.installEventFilter(self)

    @staticmethod
    def _is_plus_tab(tabs, index):
        return index == tabs.count() - 1

    def _connect_editor_tracking(self, editor):
        """状态栏实时跟踪：光标位置即时更新，字数统计延迟合并（避免大文档卡顿）。"""
        if getattr(self, '_status_timer', None) is None:
            self._status_timer = QTimer(self)
            self._status_timer.setSingleShot(True)
            self._status_timer.setInterval(220)
            self._status_timer.timeout.connect(self._refresh_status_bar)
        editor.cursorPositionChanged.connect(self._update_cursor_pos)
        editor.textChanged.connect(self._on_doc_modified)

    def _new_text_editor(self):
        editor = QTextEditWithLineNum()
        editor.setContextMenuPolicy(Qt.CustomContextMenu)
        editor.customContextMenuRequested.connect(self.show_context_menu)
        editor.focusOutEvent = self.fn_texteditor_focusout_autosave
        editor.mouseReleaseEvent = self.fn_mouse_keyrelease_text
        editor.mouseDoubleClickEvent = self.fn_mouse_dbclick
        editor.keyReleaseEvent = self.fn_keyreleaseevent
        editor.keyPressEvent = self.fn_keypressevent
        editor.textChanged.connect(self.fn_text_changed)
        # 拖选关键词后：正文与左侧附图标记列表同时临时高亮该词
        editor.selectionChanged.connect(lambda: self.fn_selection_kw_highlight(editor))
        self._connect_editor_tracking(editor)
        return editor

    def _new_mark_editor(self):
        editor = OcrDropTextEdit()
        editor.focusOutEvent = self.fn_textmark_focusout_autosave
        editor.mouseReleaseEvent = self.fn_highlight_figmarks
        editor.mouseDoubleClickEvent = self.mark_dbclick_event
        editor.dropEvent = self.markeditor_dropEvent
        editor.dragMoveEvent = self.dragMoveEvent
        editor.dragEnterEvent = self.dragEnterEvent
        return editor

    def fn_add_document(self):
        """点击「+」：新增一个文档标签页，并同步新增左侧对应的附图标记文本框。"""
        if getattr(self, '_adding_document', False):
            return
        self._adding_document = True
        try:
            self._fn_add_document_impl()
        finally:
            self._adding_document = False

    def _fn_add_document_impl(self):
        if self.doc_count >= MAX_DOC_TAB_COUNT:
            wf.notice(self, '无法新建文档',
                      f'最多可创建 {MAX_DOC_TAB_COUNT} 个文档。',
                      detail='如需继续，请先关闭末尾新增的文档。',
                      kind='warning', width=400)
            return
        text_tabs, mark_tabs = self.tab_widget_text, self.tab_widget_mark
        idx = self.doc_count
        name = f'文档{idx + 1}'
        text_ed, mark_ed = self._new_text_editor(), self._new_mark_editor()
        text_tabs.blockSignals(True)
        mark_tabs.blockSignals(True)
        text_tabs.insertTab(idx, text_ed, name)
        mark_tabs.insertTab(idx, mark_ed, f'列表{idx + 1}')
        self.text_editor_array.append(text_ed)
        self.mark_editor_array.append(mark_ed)
        self.contextMenu_array.append(None)
        self.tab_name_array.append(name)
        self.doc_count += 1
        self._save_tab_names()
        # 新编辑器补接字体、字号与格式按钮信号（与启动时 main_ui 的处理一致）
        self.combo_fonts.currentFontChanged.connect(text_ed.setCurrentFont)
        self.combo_fontsize.currentIndexChanged.connect(text_ed.setFontPointSize)
        self.add_action(text_ed)
        text_tabs.blockSignals(False)
        mark_tabs.blockSignals(False)
        # 统一存档里为新增文档留一个空槽位（不再创建散文件）
        try:
            store.set_tab(idx, html='', marks='')
        except Exception as e:
            print('Error Code 605', e)
        text_tabs.setCurrentIndex(idx)
        mark_tabs.setCurrentIndex(idx)
        self.fn_texttab_changed()
        self.status.set_saved(False)
        self.status.showMessage(
            f'> 已新建「{name}」，左侧附图标记列表同步增加「列表{idx + 1}」', 6000)

    def fn_close_document(self, index=None):
        """关闭末尾新增的文档（前 DOC_TAB_COUNT 个为常驻文档，不可关闭）。"""
        idx = self.tab_widget_text.currentIndex() if index is None else index
        if idx < DOC_TAB_COUNT or idx != self.doc_count - 1:
            wf.notice(self, '无法关闭',
                      '只能关闭末尾新增的文档，前 %d 个文档为常驻文档。' % DOC_TAB_COUNT,
                      detail='这样可保证存档序号与标签序号始终一一对应。',
                      kind='info', width=430)
            return
        name = self.tab_name_array[idx]
        reply = wf.ask(self, '关闭文档', f'确定要关闭「{name}」吗？',
                       [('保存并关闭', 2, True), ('不保存关闭', 1), ('取消', 0)],
                       detail='该文档的内容会从草稿存档中移除，其余文档不受影响。',
                       kind='question', width=450)
        if reply == 0:
            return
        if reply == 2:
            self._save_all_drafts()
        self.tab_widget_text.blockSignals(True)
        self.tab_widget_mark.blockSignals(True)
        self.tab_widget_text.setCurrentIndex(idx - 1)
        self.tab_widget_mark.setCurrentIndex(idx - 1)
        self.tab_widget_text.removeTab(idx)
        self.tab_widget_mark.removeTab(idx)
        self.text_editor_array.pop().deleteLater()
        self.mark_editor_array.pop().deleteLater()
        self.contextMenu_array.pop()
        self.tab_name_array.pop()
        self.doc_count -= 1
        self._save_tab_names()
        store.drop_last_tabs(self.doc_count)
        self.tab_widget_text.blockSignals(False)
        self.tab_widget_mark.blockSignals(False)
        self.fn_texttab_changed()
        self.status.showMessage(f'> 已关闭「{name}」', 5000)

    def fn_tabbar_doubleclicked(self, index):
        if self._is_plus_tab(self.tab_widget_text, index):
            return  # 「+」由单击（currentChanged）处理，避免重复新建
        self.rename_tabtext()

    def fn_doctab_context_menu(self, pos):
        """文档标签栏右键：重命名 / 新建 / 关闭（Word 标签右键菜单风格）。"""
        bar = self.tab_widget_text.tabBar()
        index = bar.tabAt(pos)
        menu = QMenu(self)
        act_new = menu.addAction(qta.icon('mdi6.plus'), '新建文档')
        act_rename = menu.addAction(qta.icon('mdi6.rename-box'), '重命名')
        act_close = menu.addAction(qta.icon('mdi6.close'), '关闭当前文档')
        # 前 DOC_TAB_COUNT 个为常驻文档；新增文档按存档序号从末尾逐个关闭。
        # index 必须真的落在最后一个「真实文档」标签上（末尾还有「+」占位页）。
        # 之前末尾标签被 ::tab:last 压成 0 宽时，tabAt() 只会返回占位页索引，
        # 这一项便恒被禁用，看起来就是「新增的文档无法关闭」。
        act_close.setEnabled(
            DOC_TAB_COUNT <= index < self.tab_widget_text.count() - 1
            and index == self.doc_count - 1)
        chosen = menu.exec_(bar.mapToGlobal(pos))
        if chosen is act_new:
            self.fn_add_document()
        elif chosen is act_rename and 0 <= index < self.doc_count:
            self.tab_widget_text.setCurrentIndex(index)
            self.rename_tabtext()
        elif chosen is act_close:
            self.fn_close_document(index)

    def add_texteditors(self):
        # 多标签文本
        self.tab_widget_text = QTabWidget()
        self.tab_widget_text.setObjectName('DocTabs')
        # 必须在 addTab 之前替换标签栏：占位页宽度由 tabSizeHint 按索引固定，
        # 不再依赖会随滚动错位的 QSS ::tab:last。
        self.tab_widget_text.setTabBar(_PlusTabBar(0, self.tab_widget_text))
        self.tab_widget_text.setMouseTracking(True)
        # 文档标签采用「列表标签」的方式：每个标签保持按文字自然宽度、字体不变，
        # 名字不省略；窗口变窄时也绝不把标签一起挤扁。
        # usesScrollButtons=True 有两个作用：① QTabBar 的 minimumSizeHint 从
        # 「所有标签宽度之和」降到「一个标签」，窗口右边缘才能继续往左收
        # （离屏实测关掉后窗口下限会顶到 1303px）；② 切换文档时自动把当前
        # 标签滚入可视区。左右箭头按钮本身不显示：QSS 已把 scroller/按钮压成
        # 0 尺寸、透明无边框（QTabBar 每次布局都会重设 arrowType，故不在代码里
        # 改按钮属性，只靠样式层，实测右端不再出现三角）。
        self.tab_widget_text.tabBar().setElideMode(Qt.ElideNone)
        self.tab_widget_text.tabBar().setUsesScrollButtons(True)
        # 滚轮不得切换选项卡（否则会误选「+」而新建文档）
        self._guard_tabbar_wheel(self.tab_widget_text.tabBar())

        # 弹窗对照视图按需创建，启动时不再构造多余的编辑器
        self.window_show_text_array = []
        self.window_show_mark_array = []
        self.tab_name_array = self._read_tab_names()
        self.doc_count = len(self.tab_name_array)
        self.text_editor_array = [self._new_text_editor() for _ in range(self.doc_count)]
        self.contextMenu_array = [None for _ in range(self.doc_count)]
        self.active_textcomponent = self.text_editor_array[0]

        self.show_cursor_menu()  # 右键菜单
        for idx, editor in enumerate(self.text_editor_array):
            self.tab_widget_text.addTab(editor, self.tab_name_array[idx])
        self._add_plus_tab(self.tab_widget_text)
        # 「+」做成右上角常驻按钮：文档标签放不下时 QTabBar 会横向滚动，末尾的
        # 「+」占位页会滚出可视区（左右箭头已隐藏，也滚不回去）。占位页保留，
        # 所有「最后一页 = 新建文档」的索引逻辑不变，只是 QSS 把它压成 0 宽
        # 透明；真正可点的是这个永远不会被滚走的角落按钮。
        self._doc_add_btn = QToolButton()
        self._doc_add_btn.setObjectName('DocAddTab')
        self._doc_add_btn.setText('+')
        self._doc_add_btn.setToolTip('新建文档')
        self._doc_add_btn.setCursor(Qt.PointingHandCursor)
        self._doc_add_btn.clicked.connect(self.fn_add_document)
        self.tab_widget_text.setCornerWidget(self._doc_add_btn, Qt.TopRightCorner)

        self.layoutwidget.addWidget(self.tab_widget_text, 1, 0, 1, 1)
        self.tab_widget_text.currentChanged.connect(self.fn_texttab_changed)
        self.tab_widget_text.tabBarDoubleClicked.connect(self.fn_tabbar_doubleclicked)
        self.tab_widget_text.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_widget_text.tabBar().customContextMenuRequested.connect(
            self.fn_doctab_context_menu)

    def fn_mouse_dbclick(self,event):

        list_1 = list(self.load_txt_1) + ['包含','已经','可以','包括','能够','一旦','一种','通过','进行','用于','如果','可能','或者'] # 向前查找
        list_2 = list(self.load_txt_2) # 向后查找
        cursor = self.active_textcomponent.textCursor()
        format = QTextCharFormat()
        format.setBackground(QColor(PAL['accent_hi']))

        for i in range(1,10):
            cursor.movePosition(cursor.Left,i)
            select_txt_1 = cursor.selectedText()
            if not select_txt_1:
                continue
            if select_txt_1[0] in list_1:
                cursor.movePosition(cursor.Right,QTextCursor.KeepAnchor,1)
                cursor.mergeCharFormat(format)
                for j in range(1 ,i + 10):
                    cursor.movePosition(cursor.Right,j)
                    select_txt_2 = cursor.selectedText()
                    if not select_txt_2:
                        continue
                    for _ in list_2:
                        if _ in select_txt_2[-1]:
                            select_txt = select_txt_1[1:] + select_txt_2.split(_)[0]
                            if len(select_txt_2) > 1:
                                move_length = len(select_txt_2.split(_)[1])
                                if move_length == 0:
                                    move_length = 1
                                cursor.movePosition(cursor.Left,QTextCursor.KeepAnchor,move_length)
                            else:
                                cursor.movePosition(cursor.Left,QTextCursor.KeepAnchor,1)
                            cursor.mergeCharFormat(format)
                            self.db_flag = True
                            self.get_same_markindex_1(select_txt,self.active_textcomponent,self.highlight_color)
                            return
                if j == i + 9:
                    select_txt = select_txt_1[1:]
                    self.db_flag = True
                    self.get_same_markindex_1(select_txt,self.active_textcomponent,self.highlight_color)
                    return
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()  # 接受包含URLs的拖拽事件
        else:
            event.ignore()
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
    def texteditor_dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = [url.toLocalFile() for url in event.mimeData().urls()]
            # 处理拖放的本地文件路径
            self.in_dir = urls[0]
            self.status.showMessage('文件识别中...')
            self.tab_txt_index = self.tab_widget_text.currentIndex()
            self.ocr_thread = Worker_Ocr(self.in_dir)
            self.ocr_thread.progress.connect(self.text_editor_ocr)
            self.ocr_thread.start()
            event.accept()
        else:
            event.ignore()
    def text_editor_ocr(self,in_txt):
        self.text_editor_array[self.tab_txt_index].insertPlainText('\n' + in_txt)
        self.status.showMessage('文件完成')
        self.status.set_accent()
        self.setCursor(Qt.ArrowCursor)
    def rename_tabtext(self, index=None):
        """双击 / 右键重命名文档标签：在标签原位就地编辑（Excel 工作表风格）。

        原实现是一个跟随鼠标位置的独立无边框小窗，缺陷：
        * 弹窗出现在鼠标处，可能离标签很远，改完不知道改的是哪个文档；
        * Esc 键是「提交」而不是「取消」，误按后把占位符当成了新名字；
        * 焦点丢失时输入为空会把文档重置成「文档N」，无法反悔。
        现改为把 QLineEdit 直接覆盖在标签上：回车/点击别处提交，Esc 取消；
        提交时若标题被清空，则恢复默认名「文档N」（Esc 仍保留原名）。
        """
        bar = self.tab_widget_text.tabBar()
        if index is None:
            index = self.tab_widget_text.currentIndex()
        if self._is_plus_tab(self.tab_widget_text, index):
            return
        if getattr(self, '_tab_rename_edit', None) is None:
            self._tab_rename_edit = QLineEdit(bar)
            self._tab_rename_edit.setAlignment(Qt.AlignCenter)
            self._tab_rename_edit.installEventFilter(self)
            self._tab_rename_edit.returnPressed.connect(self._tab_rename_commit)
        edit = self._tab_rename_edit
        rect = bar.tabRect(index)
        # 留出标签左右圆角与底边选中条，编辑框比标签略窄略高，视觉上像在改标签文字
        edit.setGeometry(rect.x() + 6, rect.y() + 1,
                         max(60, rect.width() - 12), rect.height() - 3)
        self._tab_rename_index = index
        self._tab_rename_origin = self.tab_name_array[index] or f'文档{index + 1}'
        edit.setText(self._tab_rename_origin)
        edit.selectAll()
        edit.show()
        edit.raise_()
        edit.setFocus(Qt.MouseFocusReason)

    def _tab_rename_finish(self, apply):
        edit = getattr(self, '_tab_rename_edit', None)
        if edit is None or not edit.isVisible():
            return
        index = self._tab_rename_index
        edit.hide()
        new_name = edit.text().strip() if apply else ''
        if not apply:
            return                       # Esc：取消，保留原名
        if not new_name:
            # 标题被全部删除：回退到默认名「文档N」，而不是留在原名上
            new_name = f'文档{index + 1}'
        if new_name == self._tab_rename_origin:
            return                       # 未改动
        self.tab_widget_text.setTabText(index, new_name)
        self.tab_name_array[index] = new_name
        self._save_tab_names()
        if index == self.tab_widget_text.currentIndex():
            self.set_doc_title(new_name)

    def _tab_rename_commit(self):
        self._tab_rename_finish(apply=True)
    def show_context_menu(self, pos):
        # 显示右键菜单
        self.context_menu.exec_(self.active_textcomponent.mapToGlobal(pos))
    # text_component中高亮显示mark相同的文本
    def get_same_markindex(self,mark,input_component,highlight_color):
        if mark == '.' or not mark:
            return
        try:
            mark = re.escape(mark.replace('\u2029','\n'))
            all_txt = input_component.toPlainText().replace('\u2029','\n')
            if not getattr(self, '_case_sensitive', False): # 默认不区分大小写（原复选框未勾选行为）
                all_txt = all_txt.lower()
                mark = mark.lower()
            matches = re.finditer(mark, all_txt, re.S)
            format = QTextCharFormat()
            format.setBackground(QColor(highlight_color))
            # 循环查找文档
            match_num = 0
            for match in matches:
                match_num += 1
                index = match.start()
                cursor = input_component.textCursor()
                cursor.setPosition(index)
                bracket_count = len(re.findall(r'\\(|\\)|\\{|\\}|\\[|\\]',mark))
                if index - len(mark) < 0:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark))
                else:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark) - bracket_count)
                cursor.mergeCharFormat(format)  # 改变文本的背景颜色
            self.status.showMessage(f"共匹配到{match_num}个结果")
            return match_num
        except Exception as e:
            print('Error Code 206',e)
    
    def get_same_markindex_1(self,mark,input_component,highlight_color):

        if mark == '.' or not mark:
            return
        try:
            mark = re.escape(mark.replace('\u2029','\n'))
            all_txt = input_component.toPlainText().replace('\u2029','\n')
            if not getattr(self, '_case_sensitive', False): # 默认不区分大小写（原复选框未勾选行为）
                all_txt = all_txt.lower()
                mark = mark.lower()
            matches = re.finditer(mark, all_txt, re.S)
            format = QTextCharFormat()
            format.setBackground(QColor(highlight_color))
            # 循环查找文档
            match_num = 0
            for match in matches:
                match_num += 1
                index = match.start()
                cursor = input_component.textCursor()
                cursor.setPosition(index)
                bracket_count = len(re.findall(r'\\(|\\)|\\{|\\}|\\[|\\]',mark))
                if index - len(mark) < 0:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark))
                else:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark) - bracket_count)
                cursor.mergeCharFormat(format)  # 改变文本的背景颜色
            if match_num == 1 and self.db_flag == False:
                self.reset_textcomponentformat()
            all_txt = self.active_textcomponent.toPlainText()
            all_txt_without_dots = all_txt
            select_txt = self.active_textcomponent.textCursor().selectedText()
            select_txt_without_dots = select_txt
            for _ in '!"#$%&\！@￥%……*（）()-_+=[]\\|;:，。《》？、~·！&——+\\{\\}【】‘；：”“’。，、？\'：；':
                select_txt_without_dots = select_txt_without_dots.replace(_, '')
                all_txt_without_dots = all_txt_without_dots.replace(_, '')
            len_all = len(all_txt)
            len_all_without_dots = len(all_txt_without_dots)
            if select_txt.strip(' '):
                len_select = len(select_txt)
                len_select_without_dots = len(select_txt_without_dots)
                self.status.showMessage(f"> 共匹配到{match_num}个结果 已选择{len_select}/{len_all}个字（含标点） 已选择{len_select_without_dots}/{len_all}个字（不含标点）")
            else:  
                self.status.showMessage(f"> 共匹配到{match_num}个结果 共{len_all}个字（含标点） 共{len_all_without_dots}个字（不含标点）")
        except Exception as e:
            print('Error Code 208',e)
    
    def fn_mouse_keyrelease_text(self,event):
        if self.brush_flag == True:
            if not self.char_format:
                return
            cursor = self.active_textcomponent.textCursor()
            cursor.mergeCharFormat(self.char_format)
            self.active_textcomponent.mergeCurrentCharFormat(self.char_format)
        else:
            if event.button() == 4: # 1 左键 2 右键 4 中键
                self.reset_textcomponentformat()
            if self.db_flag == True:
                self.db_flag = False
                return
            if self.write_type == '撰写' and QApplication.keyboardModifiers() != Qt.ControlModifier:
                self.reset_textcomponentformat()
            self.status.showMessage(f"")
            text_cursor = self.active_textcomponent.textCursor()
            select_txt = text_cursor.selectedText()
            if self.window_table:
                self.window_table.close()
            if select_txt:
                self.get_same_markindex(select_txt,self.active_figmark,self.highlight_color)
                self.get_same_markindex_1(select_txt,self.active_textcomponent,self.highlight_color)
    
    def fn_texteditor_focusout_autosave(self,event):
        try:
            text_idx = self.text_editor_array.index(self.active_textcomponent)
            # 文档未改动就跳过 toHtml() 序列化 + 文件写（失焦很频繁，这一步能省掉大部分开销）
            if self.active_textcomponent.document().isModified():
                store.set_tab(text_idx, html=self.active_textcomponent.toHtml())
                self.active_textcomponent.document().setModified(False)
            self._doc_dirty = False
            self.status.set_saved(True)
        except Exception as e:
            print('Error Code 209',e)
        # 编辑器失焦：若焦点转移到弹窗之外，收起联想弹窗；点击弹窗内候选项不收起
        # （焦点会先进入弹窗，itemClicked 再触发确认，若这里收起就点不到了）。
        try:
            fw = QApplication.focusWidget()
            if self._completion_popup.isVisible() and (fw is None
                    or not self._completion_popup.isAncestorOf(fw)):
                self.fn_hide_completion()
        except Exception:
            pass
    def fn_sync_clicked(self):
        """开启/关闭「标记→正文」同步。

        旧版勾选时弹窗要求把正文重置为默认格式——破坏性操作，且并非同步的前提。
        现在改为以当前标记列表建立基线，之后只同步真实发生的差异。
        """
        status = getattr(self, 'status', None)
        if self.checkbox_sync.isChecked():
            idx = self.mark_editor_array.index(self.active_figmark)
            self._mark_snapshot[idx] = [x for x in self.active_figmark.toPlainText().split('\n') if x.strip()]
            if status is not None:
                status.showMessage('同步已开启：修改标记后自动更新正文中的编号', 5000)
        else:
            if status is not None:
                status.showMessage('同步已关闭', 3000)
        # 按钮常显，开启态由 QSS 的 :checked 直接呈现，不再需要
        # 工具行做「同步时常显 / 关闭时收起」的特殊处理。

    def _fn_mark_refresh(self):
        """排序方式切换后立即重排，不再等编辑器失焦。"""
        self.fn_textmark_focusout_autosave(None)

    def add_markeditors(self):
        '''标记补全'''
        self.main_widget_mark = QWidget()
        # 放开内容最小宽度：覆盖 minimumSizeHint 的宽度，使左侧面板可拖到很窄。
        # 仅 setMinimumWidth(0) 无效——布局的固有最小宽度提示仍会卡住拖动下限。
        _mw = self.main_widget_mark
        _orig_hint = _mw.minimumSizeHint
        _mw.minimumSizeHint = lambda: QSize(0, _orig_hint().height())
        self.layout_mark_main = QGridLayout(self.main_widget_mark) # 将frame 1 & 2 横向排列
        self.main_widget_mark.setMouseTracking(True) 

        # 排序方式 / 同步开关：改用带选中态的按钮。
        # 原来的 QRadioButton/QCheckBox 在深色样式下 indicator 不可见、无选中反馈，
        # 用户看不出当前是哪种排序；同时这些按钮设为 NoFocus，点击时不会让标记
        # 编辑器失焦（失焦早于按钮状态更新，曾用旧排序方式重排，表现为「切不动」）。
        self.radio_1 = QPushButton('上下位')
        self.radio_1.setObjectName('MarkSegFirst')
        self.radio_1.setCheckable(True)
        self.radio_1.setChecked(True)
        self.radio_1.setFocusPolicy(Qt.NoFocus)
        self.radio_1.setToolTip('按标号上下位分组排序')
        self.radio_2 = QPushButton('按顺序')
        self.radio_2.setObjectName('MarkSegLast')
        self.radio_2.setCheckable(True)
        self.radio_2.setFocusPolicy(Qt.NoFocus)
        self.radio_2.setToolTip('按标号自然顺序排序')
        self.mark_sort_group = QButtonGroup(self)
        self.mark_sort_group.setExclusive(True)
        self.mark_sort_group.addButton(self.radio_1, 0)
        self.mark_sort_group.addButton(self.radio_2, 1)
        self.checkbox_sync = QPushButton('同步')
        self.checkbox_sync.setObjectName('MarkSync')
        self.checkbox_sync.setCheckable(True)
        self.checkbox_sync.setChecked(False)
        self.checkbox_sync.setFocusPolicy(Qt.NoFocus)
        self.checkbox_sync.setToolTip('修改附图标记后，自动更新正文中对应的标记编号')
        self.checkbox_sync.clicked.connect(self.fn_sync_clicked)
        # 放开排序/同步按钮最小宽度，面板拖窄时允许文字被裁切而非卡住最小宽度
        for _b in (self.radio_1, self.radio_2, self.checkbox_sync):
            _b.setMinimumWidth(0)
        # 切换排序方式后立即重排，不再依赖编辑器失焦
        self.radio_1.clicked.connect(self._fn_mark_refresh)
        self.radio_2.clicked.connect(self._fn_mark_refresh)
        # 同步基线：内存中的上一次标记列表，替代反复读取磁盘存档
        self._mark_snapshot = {}
        self._mark_refreshing = False

        self.tab_widget_mark = QTabWidget()
        self.tab_widget_mark.setObjectName('MarkTabs')
        # 与 DocTabs 同理：末尾「+」页固定 30px，避免 :last 样式误伤「列表N」
        self.tab_widget_mark.setTabBar(_PlusTabBar(30, self.tab_widget_mark))
        self.tab_widget_mark.setMinimumWidth(0)
        # 与文档标签页严格一一对应：文档 N ↔ 列表 N
        self.mark_editor_array = [self._new_mark_editor() for _ in range(self.doc_count)]
        self.active_figmark = self.mark_editor_array[0]
        # 原「标记补全 *共N个标记」计数标签按需求删除；底部工具行改为
        # 常显的排序分段器 + 同步开关，只保留一个「排序」小标签。
        for idx, editor in enumerate(self.mark_editor_array):
            self.tab_widget_mark.addTab(editor, f'列表{idx + 1}')
        self._add_plus_tab(self.tab_widget_mark)
        # 列表跟随文档切换：fn_texttab_changed 会 setCurrentIndex 同步并自动
        # 滚动选中项；标签栏本身不显示（高度压为 0），整行空间让给列表内容。
        # 选项卡机制（含末尾「+」页与 fn_marktab_changed 逻辑）原样保留，
        # 仅为不可见状态——用户通过正文标签栏新建/切换文档即可。
        self._guard_tabbar_wheel(self.tab_widget_mark.tabBar())
        bar = self.tab_widget_mark.tabBar()
        bar.setFixedHeight(0)
        bar.hide()
        # QSS 给 MarkTabs QTabBar 设置过 min-height，压不掉；直接限定最大高度
        bar.setMaximumHeight(0)
        bar.setMinimumHeight(0)

        self.tab_widget_mark.currentChanged.connect(self.fn_marktab_changed)

        # 顶部整行留给标记列表并占满剩余高度；底部是常显的排序 / 同步
        # 工具行（_MarkToolRow）。两者之间留 5px 呼吸间距，不再用 hover
        # 浮出方式，也不再留空白热区。
        self.layout_mark_main.setVerticalSpacing(5)
        self.layout_mark_main.addWidget(self.tab_widget_mark, 0, 0, 1, 3)
        self.mark_tool_row = _MarkToolRow(
            (self.radio_1, self.radio_2, self.checkbox_sync))
        self.layout_mark_main.addWidget(self.mark_tool_row, 1, 0, 1, 3)
        self.layout_mark_main.setRowStretch(0, 1)
        self.layout_mark_main.setRowStretch(1, 0)

        '''关键词补全'''
        self.main_widget_keywords = QWidget()
        self.layout_keywords_main = QGridLayout(self.main_widget_keywords)

        # 定义一个复选框
        self.checkbox_markcheck = QCheckBox("识别未用标记")
        self.checkbox_markcheck.setChecked(False)
        self.checkbox_userwords = QCheckBox("关键词补全")
        self.checkbox_userwords.setChecked(True)

        # 自定义词库（存档内容在 _load_tab_contents 中加载）
        self.text_genword = QTextEdit()
        # 底色/文字交给全局 QSS 统一控制
        self.text_genword.setPlaceholderText("关键词补全")
        self.text_genword.setMinimumWidth(50)
        self.text_genword.setLineWrapMode(0) #不换行
        self.text_genword.focusOutEvent = self.fn_textuserword_focusout
        self.text_genword.mouseReleaseEvent = self.fn_highlight_userwords
        self.text_genword.mouseDoubleClickEvent = self.userwords_dbclick_event

        self.label_keywords = QLabel()
        self.label_keywords.setText(f"关键词补全 *共0个标记")

        self.layout_keywords_main.addWidget(self.checkbox_markcheck,0,0,1,1)
        self.layout_keywords_main.addWidget(self.checkbox_userwords,0,1,1,1)
        self.layout_keywords_main.addWidget(self.text_genword,1,0,1,2)
        self.layout_keywords_main.addWidget(self.label_keywords,2,0,1,2)

    def mark_dbclick_event(self,event):
        insert_cursor = self.active_figmark.textCursor()
        insert_cursor.select(insert_cursor.LineUnderCursor)
        self.active_figmark.setTextCursor(insert_cursor)
        select_mark = insert_cursor.selectedText().strip(' \n').split(' ')[-1]

        font_format = QTextCharFormat()
        font_format.setForeground(QColor(self.font_color))
        cursor = self.active_textcomponent.textCursor()
        re_search = QRegExp(select_mark)
        matches = re.finditer(re_search.pattern(), self.active_textcomponent.document().toPlainText().replace('\n','\u2029'))
        # 循环查找文档
        match_num = 0
        for match in matches:
            match_num += 1
            index = match.start()
            cursor.setPosition(index)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(select_mark))
            cursor.mergeCharFormat(font_format)

    def userwords_dbclick_event(self,event):
        insert_cursor = self.text_genword.textCursor()
        insert_cursor.select(insert_cursor.LineUnderCursor)
        self.text_genword.setTextCursor(insert_cursor)
        select_userword = insert_cursor.selectedText().strip(' \n')

        font_format = QTextCharFormat()
        font_format.setForeground(QColor(self.font_color))
        cursor = self.active_textcomponent.textCursor()
        re_search = QRegExp(select_userword)
        matches = re.finditer(re_search.pattern(), self.active_textcomponent.document().toPlainText().replace('\n','\u2029'))
        # 循环查找文档
        match_num = 0
        for match in matches:
            match_num += 1
            index = match.start()
            cursor.setPosition(index)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(select_userword))
            cursor.mergeCharFormat(font_format)

    def markeditor_dropEvent(self,event):
        if event.mimeData().hasUrls():
            urls = [url.toLocalFile() for url in event.mimeData().urls()]
            # 处理拖放的本地文件路径
            self.in_dir = urls[0]
            self.status.showMessage('文件识别中...')
            self.tab_mark_index = self.tab_widget_mark.currentIndex()
            self.ocr_thread = Worker_Ocr(self.in_dir)
            self.ocr_thread.progress.connect(self.mark_editor_ocr)
            self.ocr_thread.start()
            event.accept()
        else:
            event.ignore()
    def mark_editor_ocr(self,in_txt):
        in_txt = self.ocr_extract_figmarks(in_txt)
        self.mark_editor_array[self.tab_mark_index].insertPlainText('\n' + in_txt)
        self.status.showMessage('文件完成')
        self.status.set_accent()
        self.setCursor(Qt.ArrowCursor)
    def ocr_extract_figmarks(self,in_txt):
        # 统一标点符号
        if not in_txt:
            return
        # 给附图标记加括号
        find_txt = re.findall(rf'.\d\d?\d?\d?[a-z|A-Z]?.',in_txt)
        if find_txt:
            for _ in find_txt:
                if ('（' in _ and '）' in _) or ('(' in _ and ')' in _):
                    continue
                if _[0] not in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' and _[-1] not in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    in_txt = in_txt.replace(_,_[0]+'（' + _[1:-1] + '）' +_[-1])
        # 查找附图标记名称
        mark_array_name = search_marks(in_txt)
        # 查找附图标记编号
        mark_array,same_marks_array = get_figmarks(mark_array_name,in_txt)
        # 输出结果
        return '\n'.join(mark_array)
    def fn_textuserword_focusout(self,event):
        all_txt_array = re.split('\n|\u2029',self.text_genword.toPlainText().strip('\r\t\n\u2029'))
        all_txt_array = refine_array(all_txt_array, 'set')
        all_txt_array.sort()
        self.text_genword.clear()
        self.text_genword.insertPlainText('\u2029'.join(all_txt_array))
        try:
            store.set_main_userwords('\u2029'.join(all_txt_array))
        except Exception as e:
            print('Error Code 606', e)
        self.label_keywords.setText(f'关键词补全 *共{len(all_txt_array)}个关键词')
    # 用于自由撰写的附图标记高亮
    def fn_highlight_figmarks(self,event):
        all_mark_txt = self.active_figmark.toPlainText().strip('\u2029\r ')
        if '、' in all_mark_txt:
            return
        # 获取当前光标所在的位置
        cursor_mark = self.active_figmark.textCursor()
        select_txt = cursor_mark.selectedText()
        self.reset_figmarkformat()
        if select_txt:
            self.get_same_markindex(select_txt,self.active_figmark,self.highlight_color)
            self.get_same_markindex(select_txt,self.active_textcomponent,self.highlight_color)
        else:
            # 获取当前光标所在的行
            cursor_mark.select(QTextCursor.LineUnderCursor)
            current_mark = cursor_mark.selectedText().strip('\u2029')
            if QApplication.keyboardModifiers() != Qt.ControlModifier:
                self.reset_textcomponentformat()
            try: # 纯文本
                highlight_mark = current_mark.split(' ')[1] 
                num_1 = self.get_same_markindex(highlight_mark,self.active_textcomponent,'#e06061')
            except:
                num_1 = 0
            try: # 英文括号标记
                highlight_mark = current_mark.split(' ')[1] + '(' + current_mark.split(' ')[0] + ')'
                num_2 = self.get_same_markindex(highlight_mark,self.active_textcomponent,self.highlight_color)
            except:
                num_2 = 0

            try: # 中文括号标记
                highlight_mark = current_mark.split(' ')[1] + '（' + current_mark.split(' ')[0] + '）'
                num_3 = self.get_same_markindex(highlight_mark,self.active_textcomponent,self.highlight_color)
            except:
                num_3 = 0

            try: # 无括号标记
                highlight_mark = current_mark.split(' ')[1] + current_mark.split(' ')[0]
                num_4 = self.get_same_markindex(highlight_mark,self.active_textcomponent,self.highlight_color)
            except:
                num_4 = 0
            self.status.showMessage(f"> 匹配结果：纯文本{num_1}个 英文括号标记{num_2}个 中文括号标记{num_3}个 无括号标记{num_4}个")
        

    def fn_highlight_userwords(self,event):
        all_mark_txt = self.text_genword.toPlainText().strip('\u2029\r ')
        if '、' in all_mark_txt:
            return
        # 获取当前光标所在的位置
        cursor = self.text_genword.textCursor()
        # 获取当前光标所在的行
        current_mark = cursor.block().text().strip('\u2029')
        self.reset_textcomponentformat()
        try:
            self.get_same_markindex(current_mark,self.active_textcomponent,self.highlight_color)
        except:
            pass
        text_cursor = self.text_genword.textCursor()
        select_txt = text_cursor.selectedText()
        self.reset_figmarkformat()
        if select_txt:
            self.get_same_markindex(select_txt,self.text_genword,self.highlight_color)
    # 初始化active_figmark的格式
    def reset_figmarkformat(self):
        format = QTextCharFormat()
        format.setFontPointSize(9)
        format.setBackground(QColor(Qt.transparent))

        cursor = self.active_figmark.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(self.active_textcomponent.toPlainText()))
        cursor.mergeCharFormat(format)

        cursor = self.text_genword.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(self.active_textcomponent.toPlainText()))
        cursor.mergeCharFormat(format)
    # 初始化active_figmark的格式
    def reset_textcomponentformat(self):
        format = QTextCharFormat()
        format.setBackground(QColor(Qt.transparent))
        cursor = self.active_textcomponent.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(self.active_textcomponent.toPlainText()))
        cursor.mergeCharFormat(format)
    def fn_textmark_focusout_autosave(self,event):
        """标记编辑器失焦 / 切换排序方式时的统一入口，带防重入。"""
        if getattr(self, '_mark_refreshing', False):
            return
        self._mark_refreshing = True
        try:
            self._apply_mark_changes()
        finally:
            self._mark_refreshing = False

    def _apply_mark_changes(self):
        # 统一标记格式
        list_num = self.mark_editor_array.index(self.active_figmark)
        all_marks = self.active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('：', '').replace(':', '').replace('	', ' ').replace('，',',').strip('\u2029。')
        # 选择排序方式
        if self.radio_1.isChecked():
            figmarks_array = split_marks(all_marks)
        elif self.radio_2.isChecked():
            figmarks_array = split_marks_bysort(all_marks)
        while ' ' in figmarks_array:
            figmarks_array.remove(' ')
        # 获取光标当前的行号
        block_cursor = self.active_figmark.textCursor()
        mark_line_number = block_cursor.blockNumber()
        total_paragraphs = self.active_figmark.document().blockCount()
        line_add = int(self.active_figmark.height()/28)
        if mark_line_number + line_add >= total_paragraphs:
            mark_line_number = total_paragraphs
        else:
            mark_line_number += line_add
            
        self.active_figmark.setPlainText('\n'.join(figmarks_array))
        # 重置format
        self.reset_figmarkformat()
        check_num_count = 0
        for num in '1234567890':
            if num not in all_marks:
                check_num_count += 1
        if check_num_count >= 9:  # 如果不含有任何标记，自动标号
            autonum_marks = all_marks.split()
            while '' in autonum_marks:
                autonum_marks.remove('')
            autonum_marks = list(set(autonum_marks))
            autonum_marks.sort()
            i = 1
            j = 0
            for _ in autonum_marks:
                j += 1
                if j == 10:
                    i += 1
                    j = 1
                else:
                    self.active_figmark.insertPlainText(f'{i}{j} {_}\u2029')
        else:  # 获取标号列表 和 部件名称列表
            same_marks_array, same_nums_array = [], []
            cursor = QTextCursor(self.active_figmark.document())
            all_marks = '\u2029' + '\u2029'.join(figmarks_array) + '\u2029'
            for item in figmarks_array:
                fig_num, fig_text = judge_mark(item)
                num_find = re.findall(f'\u2029{fig_num} ', all_marks)
                mark_find = re.findall(f' {fig_text}\u2029', all_marks)
                if len(num_find) >= 2:
                    same_nums_array.append(f'{fig_num}')
                if len(mark_find) >= 2:
                    same_marks_array.append(f'{fig_text}')
            same_nums_array = list(set(same_nums_array))
            same_marks_array = list(set(same_marks_array))
            # 高亮显示重复的标记
            mark_index = 0
            for item_num in same_nums_array:
                mark_index += 1
                rnd_color = f'#{random.randint(100000, 999999)}'
                for mark in figmarks_array:
                    if item_num == mark.split(' ')[0]:
                        # 选择相应行
                        cursor = QTextCursor(self.active_figmark.document())
                        cursor.movePosition(QTextCursor.Start)
                        cursor.movePosition(QTextCursor.Down,QTextCursor.MoveAnchor, figmarks_array.index(mark))
                        cursor.movePosition(QTextCursor.StartOfLine)
                        cursor.movePosition(QTextCursor.WordRight, QTextCursor.KeepAnchor)
                        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor,1)
                        # 设置高亮
                        format = cursor.charFormat()
                        format.setBackground(QColor(rnd_color))
                        cursor.mergeCharFormat(format)
            # 高亮显示重复的名称
            mark_index = 0
            for item_mark in same_marks_array:
                mark_index += 1
                rnd_color = f'#{random.randint(100000, 999999)}'
                for mark in figmarks_array:
                    if item_mark == mark.split(' ')[1]:
                        # 选择相应行
                        cursor = QTextCursor(self.active_figmark.document())
                        cursor.movePosition(QTextCursor.Start)
                        cursor.movePosition(QTextCursor.Down,QTextCursor.MoveAnchor, figmarks_array.index(mark))
                        cursor.movePosition(QTextCursor.EndOfLine)
                        cursor.movePosition(QTextCursor.WordLeft, QTextCursor.KeepAnchor)
                        # 设置高亮
                        format = cursor.charFormat()
                        format.setBackground(QColor(rnd_color))
                        cursor.mergeCharFormat(format)
            # 重新定位光标
            for _ in range(mark_line_number):
                cursor.movePosition(QTextCursor.Down)
            self.active_figmark.setTextCursor(cursor)        
            for _ in range(line_add):
                cursor.movePosition(QTextCursor.Down)
        # 自动同步正文中的附图标记（内存基线 + 批量替换，保留正文格式）
        if self.checkbox_sync.isChecked():
            try:
                self._sync_marks_to_document(list_num, figmarks_array)
            except Exception as e:
                print('Error Code 611', e)
        # 更新标记缓存：统一存档 + 内存快照供下次同步做差异比对
        try:
            store.set_tab(list_num, marks='\u2029'.join(figmarks_array))
        except Exception as e:
            print('Error Code 602', e)
        self._mark_snapshot[list_num] = list(figmarks_array)
        # 原底部「共N个标记」计数文字已按需求移除，这里不再刷新标签。

    def _sync_marks_to_document(self, list_num, new_marks):
        """把标记列表的改动同步到正文。

        与旧实现的差别：
        * 基线取内存快照，不再每次读磁盘存档，文件缺失也不会抛异常；
        * 先算出全部「旧→新」配对，再一次性查找替换；
        * 用 QTextDocument.find + insertText 就地替换，不重建 HTML，
          正文的字体、颜色、高亮等富文本格式得以保留；
        * 不再调用 on_lineheight_changed()（它内部 setHtml 会重建文档），
          也不再清掉正文格式；只恢复光标所在段落。
        """
        old_marks = self._mark_snapshot.get(list_num)
        if old_marks is None:
            # 首次没有基线时退回统一存档；仍为空则只建立基线，避免误替换
            try:
                raw = store.get_tab(list_num)[1]
                old_marks = [x for x in raw.replace('\n', '\u2029').split('\u2029') if x.strip()]
            except Exception:
                old_marks = []
            self._mark_snapshot[list_num] = list(old_marks)
        new_set, old_set = set(new_marks), set(old_marks)
        removed = [m for m in old_marks if m not in new_set]
        added = [m for m in new_marks if m not in old_set]
        if not removed or not added:
            return
        # 按「名称相同、编号相同、或同位置整行改动」配对：
        # 1) 名称相同 → 用户改了标号，同步正文中的编号；
        # 2) 编号相同 → 用户改了特征名称，同步正文中的名称；
        # 3) 恰好一处删除 + 一处新增 → 视为同一行的标号与名称同时改动。
        pairs, used = [], set()
        for old_mark in removed:
            old_num, old_txt = judge_mark(old_mark)
            if not old_num or not old_txt:
                continue
            for new_mark in added:
                if new_mark in used:
                    continue
                new_num, new_txt = judge_mark(new_mark)
                if not new_num or not new_txt:
                    continue
                if new_txt == old_txt or new_num == old_num:
                    pairs.append((old_num, old_txt, new_num, new_txt))
                    used.add(new_mark)
                    break
        # 整行同时改标号 + 改名称：剩余未配对的恰好各一处时直接配对
        rest_old = [m for m in removed if not any(
            judge_mark(m)[0] == p[0] and judge_mark(m)[1] == p[1] for p in pairs)]
        rest_new = [m for m in added if m not in used]
        if len(rest_old) == 1 and len(rest_new) == 1:
            old_num, old_txt = judge_mark(rest_old[0])
            new_num, new_txt = judge_mark(rest_new[0])
            if old_num and old_txt and new_num and new_txt:
                pairs.append((old_num, old_txt, new_num, new_txt))
                used.add(rest_new[0])
        if not pairs:
            return
        ed = self.active_textcomponent
        doc = ed.document()
        line_no = ed.textCursor().blockNumber()
        replaced = 0
        for old_num, old_txt, new_num, new_txt in pairs:
            variants = (
                (f'{old_txt}{old_num}', f'{new_txt}{new_num}'),
                (f'{old_txt}({old_num})', f'{new_txt}({new_num})'),
                (f'{old_txt}（{old_num}）', f'{new_txt}（{new_num}）'),
                (f'{old_num} {old_txt}', f'{new_num} {new_txt}'),
            )
            for old_str, new_str in variants:
                if not old_str or old_str == new_str:
                    continue
                probe = QTextCursor(doc)
                while True:
                    hit = doc.find(old_str, probe)
                    if hit.isNull():
                        break
                    hit.insertText(new_str)
                    probe = hit
                    replaced += 1
        if not replaced:
            return
        cursor = ed.textCursor()
        cursor.movePosition(QTextCursor.Start)
        for _ in range(line_no):
            cursor.movePosition(QTextCursor.NextBlock)
        ed.setTextCursor(cursor)
        status = getattr(self, 'status', None)
        if status is not None:
            status.showMessage(f'已同步 {replaced} 处附图标记到正文', 5000)

    def show_cursor_menu(self):
        self.context_menu = QMenu()
        self.context_menu.addAction(self.action_00)
        self.context_menu.addAction(self.action_summary)
        self.context_menu.addAction(self.action_01)
        self.context_menu.addAction(self.action_02)
        self.context_menu.addAction(self.action_03)
        self.context_menu.addAction(self.action_04)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.action_insertimage)
        # 批量文本：多份文本批量处理 → 多文本框图标（原「星球」与功能无关）
        self.menu_1 = self.context_menu.addMenu(
            QIcon(qta.icon('mdi6.text-box-multiple-outline')), "批量文本(E)")
        self.menu_1.addAction(self.action_11)
        self.menu_1.addAction(self.action_12)
        self.menu_1.addAction(self.action_13)
        self.menu_1.addAction(self.action_14)
        self.menu_1.addAction(self.action_15)
        self.menu_1.addAction(self.action_16)
        self.menu_1.addAction(self.action_17)
        self.menu_1.addAction(self.action_18)
        self.menu_1.addAction(self.action_19)
        self.menu_1.addAction(self.action_110)
        self.menu_1.addAction(self.action_111)
        self.menu_1.addAction(self.action_112)
        self.menu_1.addAction(self.action_113)
        self.menu_1.addAction(self.action_114)
        self.menu_1.addAction(self.action_115)
        self.menu_1.addAction(self.action_116)
        self.menu_1.addAction(self.action_117)

        # 生成模板：多份文书模板 → 多文档图标（原「路径」与功能无关）
        self.menu_2 = self.context_menu.addMenu(
            QIcon(qta.icon('mdi6.file-document-multiple-outline')), "生成模板(H)")
        self.menu_2.addAction(self.action_21)
        self.menu_2.addAction(self.action_22)
        self.menu_2.addAction(self.action_23)
        self.menu_2.addAction(self.action_24)
        self.menu_2.addAction(self.action_25)
    def fn_selection_kw_highlight(self, editor=None):
        """拖选关键词后：正文与左侧附图标记列表同时临时高亮该词。

        使用 ExtraSelections 实现——不写入文档字符格式，选区折叠/清除时自动还原，
        与「标记列表点击高亮」（mergeCharFormat 版 get_same_markindex）互不干扰。
        """
        if editor is None:
            editor = getattr(self, 'active_textcomponent', None)
        if editor is None or not hasattr(editor, 'textCursor'):
            return
        mark_editor = getattr(self, 'active_figmark', None)
        targets = [e for e in (editor, mark_editor)
                   if e is not None and hasattr(e, 'setExtraSelections')]
        kw = editor.textCursor().selectedText().replace('\u2029', '\n').strip()
        # 空选区 / 跨行选区 / 过长选区：清除高亮
        if not kw or '\n' in kw or len(kw) > 60:
            for e in targets:
                e.setExtraSelections([])
            return
        for e in targets:
            self._selection_highlight_pattern(e, kw)

    def _selection_highlight_pattern(self, editor, kw):
        """在单个文本控件内以 ExtraSelections 临时高亮 kw 的全部出现位置。"""
        try:
            text = editor.toPlainText().replace('\u2029', '\n')
            if not getattr(self, '_case_sensitive', False):
                text_l, kw_l = text.lower(), kw.lower()
            else:
                text_l, kw_l = text, kw
            hits = list(re.finditer(re.escape(kw_l), text_l, re.S))[:400]
        except Exception as e:
            print('Error Code 207', e)
            return
        fmt = QTextCharFormat()
        fmt.setBackground(QColor('#2f5d9e'))   # 主题蓝，贴合深色风格
        fmt.setForeground(QColor('#ffffff'))
        selections = []
        for m in hits:
            cur = QTextCursor(editor.document())
            cur.setPosition(m.start())
            cur.setPosition(m.end(), QTextCursor.KeepAnchor)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)
        editor.setExtraSelections(selections)

    def add_action(self,editor):
        self.bt_bold.toggled.connect(lambda x: editor.setFontWeight(QFont.Bold if x else QFont.Normal))
        self.bt_italic.toggled.connect(editor.setFontItalic)
        self.bt_underline.toggled.connect(editor.setFontUnderline)
        self.toobar_alignl.triggered.connect(lambda: editor.setAlignment(Qt.AlignLeft))
        self.toobar_alignc.triggered.connect(lambda: editor.setAlignment(Qt.AlignCenter))
        self.toobar_alignr.triggered.connect(lambda: editor.setAlignment(Qt.AlignRight))
        self.toobar_alignj.triggered.connect(lambda: editor.setAlignment(Qt.AlignJustify))
    def set_boldfont(self):
        count = 0
        font_format = QTextCharFormat()
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().replace('\n','\u2029')
        if cursor.charFormat().font().bold():
            count += 1
        elif not cursor.charFormat().font().bold():
            pass
        re_search = QRegExp(select_txt)
        matches = re.finditer(re_search.pattern(), self.active_textcomponent.document().toPlainText().replace('\n','\u2029'))
        # 循环查找文档
        match_count = 0
        for match in matches:
            match_count += 1
        if count == match_count:
            font_format.setFontWeight(QFont.Normal)
        else:
            font_format.setFontWeight(QFont.Bold)
        for match in matches:
            index = match.start()
            cursor.setPosition(index)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(select_txt))
            cursor.mergeCharFormat(font_format)
    def block_signals(self, objects, b):
        for o in objects:
            o.blockSignals(b)
    def update_format(self,editor):
        self.block_signals(self._format_actions, True)
        self.combo_fonts.setCurrentFont(editor.currentFont())
        self.combo_fontsize.setCurrentText(str(int(editor.fontPointSize())))
        self.bt_italic.setChecked(editor.fontItalic())
        self.bt_underline.setChecked(editor.fontUnderline())
        self.bt_bold.setChecked(editor.fontWeight() == QFont.Bold)
        self.toobar_alignl.setChecked(editor.alignment() == Qt.AlignLeft)
        self.toobar_alignc.setChecked(editor.alignment() == Qt.AlignCenter)
        self.toobar_alignr.setChecked(editor.alignment() == Qt.AlignRight)
        self.toobar_alignj.setChecked(editor.alignment() == Qt.AlignJustify)
        self.block_signals(self._format_actions, False)
    def _init_status_tracking(self):
        # 编辑器创建时已逐一连接；这里只做初次计算
        self._refresh_status_bar()
        self._update_cursor_pos()

    def _on_doc_modified(self):
        self._doc_dirty = True
        self.status.set_saved(False)
        if self._status_timer is not None:
            self._status_timer.start()

    def _refresh_status_bar(self):
        ed = getattr(self, 'active_textcomponent', None)
        status = getattr(self, 'status', None)
        if not ed or status is None:
            return
        text = ed.toPlainText()
        sel = ed.textCursor().selectedText()
        stats = wf.collect_text_stats(text, sel)
        status.set_words(stats['字数'], len(sel) if sel else 0)
        self._update_cursor_pos()

    def _update_cursor_pos(self):
        ed = getattr(self, 'active_textcomponent', None)
        status = getattr(self, 'status', None)
        if not ed or status is None:
            return
        c = ed.textCursor()
        status.set_position(c.blockNumber() + 1,
                            c.position() - c.block().position() + 1,
                            ed.document().blockCount())

    def fn_show_wordcount(self):
        """状态栏「字数」→ Word 2019 风格字数统计窗口。"""
        ed = self.active_textcomponent
        stats = wf.collect_text_stats(ed.toPlainText(),
                                     ed.textCursor().selectedText())
        wf.WordCountDialog(self, stats).exec_()

    def fn_set_overwrite_mode(self, on):
        self._overwrite_mode = bool(on)
        for ed in self.text_editor_array:
            try:
                ed.setOverwriteMode(self._overwrite_mode)
            except Exception:
                pass
        self.status.set_mode(self._overwrite_mode)
        self.status.showMessage('已切换到「改写」模式' if on else '已切换到「插入」模式', 4000)

    def fn_zoom_reset(self):
        self.slider_fontsize.setValue(12)
        self.label_fontsize.setText('100%')
        self.status.showMessage('显示比例已重置为 100%', 4000)

    # ================= Word 2019 风格编辑功能 =================
    def fn_show_find_dialog(self, show_batch=False):
        """Ctrl+H / 功能区：非模态「查找和替换」，无损高亮全部结果。
        show_batch=True 时直接切到「批量替换」页签（Ctrl+Shift+H）。"""
        if self._find_dialog is None or not self._find_dialog.isVisible():
            sel = self.active_textcomponent.textCursor().selectedText()
            self._find_dialog = wf.FindReplaceDialog(
                self, lambda: self.active_textcomponent, sel)
            self._find_dialog.show()
        else:
            self._find_dialog.raise_()
            self._find_dialog.activateWindow()
        if show_batch:
            self._find_dialog._tabs.setCurrentIndex(2)
            self._find_dialog.batch_left.setFocus()
        else:
            self._find_dialog.edit_find.setFocus()
            self._find_dialog.edit_find.selectAll()

    def fn_goto_line(self):
        ed = self.active_textcomponent
        dlg = wf.GoToDialog(self, ed.document().blockCount())
        if dlg.exec_() == QDialog.Accepted:
            block = ed.document().findBlockByNumber(dlg.line() - 1)
            if block.isValid():
                c = QTextCursor(block)
                ed.setTextCursor(c)
                ed.ensureCursorVisible()
                ed.setFocus()
                self.status.showMessage('> 已定位到第 %d 行' % dlg.line(), 4000)

    def fn_select_all(self):
        self.active_textcomponent.selectAll()
        self._refresh_status_bar()

    def fn_insert_datetime(self):
        from datetime import datetime
        now = datetime.now()
        choices = [
            now.strftime('%Y年%m月%d日'),
            now.strftime('%Y年%m月%d日 %H:%M'),
            now.strftime('%Y-%m-%d'),
            now.strftime('%Y/%m/%d'),
            now.strftime('%H:%M:%S'),
            now.strftime('%Y年%m月%d日（%A）'),
        ]
        dlg = wf.FenrirDialog(self, title='日期和时间',
                              message='选择格式后插入到光标位置：',
                              kind='info', width=400)
        combo = QComboBox()
        combo.addItems(choices)
        combo.setMinimumHeight(28)
        dlg.add_content(combo)
        dlg.add_button('插入', QDialog.Accepted, primary=True)
        dlg.add_button('取消', QDialog.Rejected)
        if dlg.exec_() == QDialog.Accepted:
            self.active_textcomponent.textCursor().insertText(combo.currentText())
            self.status.showMessage('> 已插入日期时间', 3000)

    def fn_insert_divider(self):
        c = self.active_textcomponent.textCursor()
        c.insertText('\n' + '─' * 40 + '\n')
        self.status.showMessage('> 已插入分隔线', 3000)

    @staticmethod
    def _clear_list_block(editor, block):
        """把某个 QTextBlock 从列表里摘出来（编号是格式生成的，不是字符）。"""
        if block is None or not block.isValid() or block.textList() is None:
            return False
        c = QTextCursor(block)
        c.setBlockFormat(QTextBlockFormat())   # 同时清掉列表缩进
        return True

    def _strip_empty_doc_list(self, editor):
        """清理空白草稿里残留的列表格式，避免第一行永远挂一个「1.」。

        不依赖 document().isEmpty()：Qt 解析存档里的 <li><br /></li> 时可能
        给出一个只有换行的块，isEmpty() 为假，但本质上仍是空文档。
        """
        doc = editor.document()
        if doc.toPlainText().strip():
            return False
        cursors = []
        block = doc.begin()
        while block.isValid():
            if block.textList() is not None:
                cursors.append(QTextCursor(block))
            block = block.next()
        for c in cursors:
            c.setBlockFormat(QTextBlockFormat())
        return bool(cursors)

    def _clear_empty_list_at_cursor(self):
        """退格 / Delete 落在空列表项行首时，取消列表格式而不是删字符。

        QTextList 的编号由 QTextBlockFormat.objectIndex 生成，
        deletePreviousChar() 碰不到它 —— 这就是空白文档里那个「1.」
        按多少次 Backspace 都还在的原因。仅在「光标在块首 + 该行
        无正文 + 无选区」时生效，不影响正常删除文字和已有编号列表。
        """
        ed = self.active_textcomponent
        c = ed.textCursor()
        if c.hasSelection():
            return False
        block = c.block()
        if c.position() != block.position() or block.text().strip():
            return False
        return self._clear_list_block(ed, block)

    def _apply_list(self, style):
        c = self.active_textcomponent.textCursor()
        cur = c.currentList()
        # 同一个列表样式再点一次 = 取消编号/项目符号（此前只能加不能去）
        if cur is not None and cur.format().style() == style:
            self._clear_list_block(self.active_textcomponent, c.block())
            self.active_textcomponent.setFocus()
            return
        fmt = QTextListFormat()
        fmt.setStyle(style)
        fmt.setIndent(1)
        c.createList(fmt)
        self.active_textcomponent.setFocus()

    def fn_bullet_list(self):
        self._apply_list(QTextListFormat.ListDisc)

    def fn_number_list(self):
        self._apply_list(QTextListFormat.ListDecimal)

    @staticmethod
    def _indent_char_width(editor):
        """当前字号下 1 个汉字的像素宽。离屏/无字体环境给出兜底值。"""
        try:
            fm = QFontMetrics(editor.currentFont())
            try:
                w = fm.horizontalAdvance('中')
            except AttributeError:            # Qt 5.11 之前只有 width()
                w = fm.width('中')
        except Exception:
            w = 0
        if w < 8:
            w = max(12.0, editor.fontPointSize() or 12.0)
        return w

    def fn_indent_change(self, delta):
        """调整段落缩进级别。

        归零时不能只清 indent：
        · 旧版「首行缩进」会留下 textIndent=24，减少缩进后首行仍永远偏右；
        · 编号/项目符号列表的缩进存在 QTextListFormat 上，blockFormat.indent()
          始终是 0，旧版在列表里点「减少缩进」被 clamp 住，完全不起作用。
        两者都在归零时一并清掉，段落才能真正回到最左侧。
        """
        ed = self.active_textcomponent
        c = ed.textCursor()
        fmt = c.blockFormat()
        old = fmt.indent()
        new = max(0, min(8, old + delta))
        fmt.setIndent(new)
        if new == 0:
            fmt.setLeftMargin(0)
            fmt.setTextIndent(0)
        c.setBlockFormat(fmt)
        # 整段缩进已为 0 时，继续减列表自身的缩进（列表编号才会往左靠）
        if delta < 0 and old == 0:
            lst = c.currentList()
            if lst is not None:
                lf = lst.format()
                if lf.indent() > 0:
                    lf.setIndent(lf.indent() - 1)
                    lst.setFormat(lf)
        ed.setTextCursor(c)

    def fn_indent_increase(self):
        self.fn_indent_change(1)

    def fn_indent_decrease(self):
        self.fn_indent_change(-1)

    def fn_first_line_indent(self):
        """中文专利说明书常用的「首行缩进 2 字符」；再点一次取消。

        只设 textIndent，不动整段缩进 —— 旧版同时 setIndent(1) 会把整段
        右移一级，看起来就是「怎么都靠不到最左边」。
        """
        ed = self.active_textcomponent
        c = ed.textCursor()
        fmt = c.blockFormat()
        if fmt.textIndent() > 0:
            fmt.setTextIndent(0)
            msg = '已取消首行缩进'
        else:
            fmt.setTextIndent(2 * self._indent_char_width(ed))
            msg = '已设置首行缩进（2 字符）'
        c.setBlockFormat(fmt)
        ed.setTextCursor(c)
        self.status.showMessage('> ' + msg, 3000)

    def fn_focus_mode(self):
        """F11：隐藏功能区 / 侧边停靠面板 / 查找条，进入沉浸式编辑。"""
        self._focus_mode = not self._focus_mode
        self.status.btn_focus.setChecked(self._focus_mode)
        panels = [d for d in (self.dock_mark, self.dock_keywords,
                              self.dock_outline, self.dock_validation,
                              self.dock_symbol) if d is not None]
        # 两个独立工具窗口同样跟随专注模式收起 / 恢复
        for w in (self.window_notebook, self.window_symbol):
            if w not in (None, '') and w.isVisible():
                panels.append(w)
        if self._focus_mode:
            self._dock_state = {d: d.isVisible() for d in panels}
            for d in panels:
                d.hide()
            self._set_ribbon_collapsed(True)
            self.status.showMessage('已进入专注模式（F11 退出）', 5000)
        else:
            for d, visible in getattr(self, '_dock_state', {}).items():
                d.setVisible(visible)
            self._set_ribbon_collapsed(False)
            self.status.showMessage('已退出专注模式', 3000)
        self.active_textcomponent.setFocus()

    # ================= 打开 / 保存 / 另存为 / 打印 =================
    def _last_doc_dir(self):
        return os.path.dirname(self.path) if self.path else os.path.expanduser('~')

    def _decode_text(self, path):
        raw = open(path, 'rb').read()
        for enc in ('utf-8-sig', 'utf-8', 'gbk', 'gb18030'):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', errors='replace')

    def file_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '打开文件', self._last_doc_dir(),
            'HTML 文档 (*.html *.htm);;Word 文档 (*.docx);;'
            '文本 / Markdown (*.txt *.md);;所有文件 (*.*)')
        if not path:
            return
        ext = self.splitext(path)
        try:
            if ext in self.HTML_EXTENSIONS:
                self.active_textcomponent.setHtml(self._decode_text(path))
            elif ext == '.docx':
                from docx import Document
                doc = Document(path)
                self.active_textcomponent.setPlainText(
                    '\n'.join(p.text for p in doc.paragraphs))
            else:
                self.active_textcomponent.setPlainText(self._decode_text(path))
        except Exception as e:
            wf.notice(self, '打开失败', '无法读取该文件。',
                      detail='%s\n%s' % (path, e), kind='critical', width=460)
            return
        self.path = path
        self._doc_dirty = False
        self.status.set_saved(True)
        self.set_doc_title(os.path.basename(path))
        self.status.showMessage('> 已打开：' + path, 6000)
        self._refresh_status_bar()

    def splitext(self, p):
        return os.path.splitext(p)[1].lower()

    def _write_document(self, path, editor, fmt=None):
        """按扩展名写文件；统一 UTF-8，避免旧版 open(path,'w') 在中文环境报错。"""
        ext = (fmt or self.splitext(path)).lower()
        if ext in self.HTML_EXTENSIONS:
            open(path, 'w', encoding='utf-8').write(editor.toHtml())
        elif ext == '.docx':
            from docx import Document
            from docx.shared import Pt
            doc = Document()
            normal = doc.styles['Normal']
            normal.font.name = '宋体'
            normal.font.size = Pt(12)
            for para in editor.toPlainText().split('\n'):
                doc.add_paragraph(para)
            doc.save(path)
        elif ext == '.pdf':
            from PyQt5.QtPrintSupport import QPrinter
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(path)
            editor.document().print_(printer)
        else:  # .txt / .md / 其它
            open(path, 'w', encoding='utf-8').write(editor.toPlainText())

    def _export_marks(self, path, index):
        if index >= len(self.mark_editor_array):
            return
        mark_path = os.path.splitext(path)[0] + '.marks.txt'
        open(mark_path, 'w', encoding='utf-8').write(
            self.mark_editor_array[index].toPlainText())
        return mark_path

    def _after_save(self, paths):
        self._doc_dirty = False
        self.status.set_saved(True)
        if len(paths) == 1:
            self.path = paths[0]
            self.set_doc_title(os.path.basename(paths[0]))
            self.status.showMessage('> 已保存：' + paths[0], 6000)
        else:
            self.path = None
            self.status.showMessage('> 已导出 %d 个文档到：%s'
                                   % (len(paths), os.path.dirname(paths[0])), 8000)
        self._refresh_status_bar()

    def file_save(self):
        if self.path is None:
            return self.file_saveas()
        try:
            self._write_document(self.path, self.active_textcomponent)
        except Exception as e:
            wf.notice(self, '保存失败', '无法写入文件。',
                      detail='%s\n%s' % (self.path, e), kind='critical', width=460)
            return
        self._after_save([self.path])

    def fn_options(self):
        # 「设置」改为打开项目主页（GitHub），原 options.txt 不再使用
        webbrowser.open(FENRIR_HOME_URL)

    def file_saveas(self):
        """Word 2019 风格「另存为」：文件名 / 位置 / 类型 / 导出选项。"""
        idx = self.tab_widget_text.currentIndex()
        if idx < 0 or idx >= len(self.tab_name_array):
            idx = 0
        safe = re.sub(r'[\\/:*?"<>|]', '_', self.tab_name_array[idx]).strip()
        dlg = wf.SaveAsDialog(
            self, default_name=safe or '未命名',
            default_dir=os.path.dirname(self.path) if self.path else None)
        if dlg.exec_() != QDialog.Accepted or not dlg.is_accepted():
            return
        opts = dlg.options()
        targets = list(range(len(self.text_editor_array))) if opts['all'] else [idx]
        folder = dlg.target_dir()
        ext = opts['format']
        written = []
        try:
            for i in targets:
                if opts['all']:
                    doc_name = re.sub(r'[\\/:*?"<>|]', '_',
                                      self.tab_name_array[i]).strip()
                    path = os.path.join(folder, f'{dlg.base_name()}_{doc_name}{ext}')
                else:
                    path = dlg.target_path()
                self._write_document(path, self.text_editor_array[i], ext)
                if opts['marks']:
                    self._export_marks(path, i)
                written.append(path)
        except Exception as e:
            wf.notice(self, '另存为失败', '写入文件时出错。',
                      detail=str(e), kind='critical', width=430)
            return
        self._after_save(written)
        if opts['open_dir']:
            try:
                os.startfile(folder)
            except Exception:
                pass

    def fn_print(self):
        from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle('打印')
        if dlg.exec_() == QDialog.Accepted:
            self.active_textcomponent.document().print_(printer)
            self.status.showMessage('> 已发送到打印机', 5000)

    def fn_export_pdf(self):
        idx = self.tab_widget_text.currentIndex()
        name = re.sub(r'[\\/:*?"<>|]', '_',
                      self.tab_name_array[idx] if idx < len(self.tab_name_array)
                      else '未命名')
        path, _ = QFileDialog.getSaveFileName(
            self, '导出为 PDF', os.path.join(self._last_doc_dir(), name + '.pdf'),
            'PDF 文档 (*.pdf)')
        if not path:
            return
        try:
            self._write_document(path, self.active_textcomponent, '.pdf')
        except Exception as e:
            wf.notice(self, '导出失败', '无法生成 PDF。', detail=str(e),
                      kind='critical', width=420)
            return
        self.status.showMessage('> 已导出 PDF：' + path, 6000)
    def complete_marknum(self,rep_type):
        repeat_mark_dic = {}
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')#.lstrip('1234567890')
        all_marks = self.active_figmark.toPlainText().replace('\n','\u2029').replace('	', ' ').replace(',','，').strip('。\r\n\t\u2029')
        figmarks_array = re.split('\r|\n|\t|\u2029',all_marks)
        # 判断重复标记
        for item_1 in figmarks_array:
            for item_2 in figmarks_array:
                mark_1 = item_1.split()[1]
                mark_2 = item_2.split()[1]
                if mark_1 in mark_2 and mark_1 != mark_2: # mark_2中含有mark_1
                    repeat_mark_dic[item_2] = item_1
        if select_txt:
            new_select_txt,repeat_array,item_lack_array = completion_nums(rep_type,all_marks,select_txt)
            out_txt = self._finish_replace(select_txt, new_select_txt)
            for item in repeat_mark_dic: # mark_2中含有mark_1
                mark_1 = repeat_mark_dic[item].split()[1]
                num_1 = repeat_mark_dic[item].split()[0]
                mark_2 = item.split()[1]
                num_2 = item.split()[0]
                tmp_1 = mark_2.replace(mark_1,mark_1+num_1)
                tmp_2 = mark_2.replace(mark_1,mark_1+'('+num_1+')')
                out_txt = out_txt.replace(tmp_1,mark_2+num_2).replace(tmp_2,mark_2+'('+num_2+')')
                out_txt = out_txt.replace('('+num_2+')'+'('+num_2+')','('+num_2+')')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def complete_markname(self,rep_type):
        cursor = self.active_textcomponent.textCursor()
        all_marks = self._normalize_marks()
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        if select_txt:            
            new_select_txt,repeat_array,item_lack_array = completion_marks(rep_type,all_marks,select_txt)
            out_txt = self._finish_replace(select_txt, new_select_txt)
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def delete_figmarks_mohu(self):
        cursor = self.active_textcomponent.textCursor()
        all_marks = self._normalize_marks()
        select_txt = cursor.selectedText().strip('\u2029\r\t')#.lstrip('1234567890')
        if select_txt:
            # 删除带括号标记
            new_select_txt = delete_bracketmarks_mohu(select_txt)
            #  删除所有非括号标记
            find_txt_array = re.findall(r'.?\d.',new_select_txt)
            for _old in find_txt_array:
                if '.' not in _old and '据' not in _old and '求' not in _old and '至' not in _old and '~' not in _old and '-' not in _old and '或' not in _old and '图' not in _old:
                    _new = _old
                    for num in '0123456789':
                        _new = _new.replace(num,'')
                    new_select_txt = new_select_txt.replace(_old,_new)
            new_select_txt = new_select_txt.replace('（','').replace('）','')
            out_txt = self._finish_replace(select_txt, new_select_txt)
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def delete_figmarks(self):
        cursor = self.active_textcomponent.textCursor()
        all_marks = self._normalize_marks()
        select_txt = cursor.selectedText().strip('\u2029\r\t')#.lstrip('1234567890')
        if select_txt:
            # 删除带括号标记
            new_select_txt = delete_bracketmarks(select_txt,all_marks)
            # 删除所有非括号标记
            figmarks_array = split_marks(all_marks)
            del_array = []
            for item in figmarks_array:
                num, mark = judge_mark(item)

                del_array_4 = re.findall(mark + r'[0-9]{4}[a-z]{0,2}', new_select_txt)
                for item in del_array_4:
                    new_select_txt = new_select_txt.replace(item,mark)

                del_array_3 = re.findall(mark + r'[0-9]{3}[a-z]{0,2}', new_select_txt)
                for item in del_array_3:
                    new_select_txt = new_select_txt.replace(item,mark) 

                del_array_2 = re.findall(mark + r'[0-9]{2}[a-z]{0,2}', new_select_txt)
                for item in del_array_2:
                    new_select_txt = new_select_txt.replace(item,mark)

                del_array_1 = re.findall(mark + r'[0-9]{1}[a-z]{0,2}', new_select_txt)
                for item in del_array_1:
                    new_select_txt = new_select_txt.replace(item,mark)    
            out_txt = self._finish_replace(select_txt, new_select_txt)
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def num_to_bracket_num(self): # 直接为附图标记增加括号   具体实施方式 → 权利要求 答复OA从说明书中增加内容
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t') + '。' # .lstrip('1234567890')
        if select_txt:
            new_select_txt = select_txt
            find_txt = re.findall(rf'.\d\d?\d?\d?[a-z|A-Z]?.',new_select_txt)
            if find_txt:
                for _ in find_txt:
                    if '图' in _:
                        pass
                    elif _[0] not in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' and _[-1] not in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        new_select_txt = new_select_txt.replace(_,_[0]+'(' + _[1:-1] + ')' +_[-1])
            # 删除权利要求(x)的括号
            find_txt = re.findall(f'权利要求\\(.*?\\)',new_select_txt)
            if find_txt:
                for _ in find_txt:
                    new_select_txt = new_select_txt.replace(_,_.replace('(','').replace(')',''))
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt.strip('。'),new_select_txt.strip('。')).replace('。。','。').replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def refine_form(self):
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')#.lstrip('1234567890')
        if select_txt:
            new_select_txt = arrenge_document(select_txt)
            out_txt = self._finish_replace(select_txt, new_select_txt)
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def del_useless_enters(self):
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().replace('\u2029','\n').strip('\u2029\n\r\t')#.lstrip('1234567890')
        new_select_txt = refine_mutilines(select_txt)
        out_txt = select_txt.replace(select_txt,new_select_txt).replace('。。','。')
        cursor.deleteChar()
        cursor.insertText(out_txt)
        self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def del_spaces(self):
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().replace('\u2029','\n').strip('\u2029\r\t')
        if select_txt:
            new_select_txt = select_txt.replace(' ','').replace(']','] ').replace(']  ','] ')
            out_txt = select_txt.replace('\u2029','\n').replace(select_txt,new_select_txt).replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def rep_element(self):
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')#.lstrip('1234567890')
        if select_txt:
            new_select_txt = rep_elements(select_txt)
            out_txt = self._finish_replace(select_txt, new_select_txt)
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def bracket_num2num(self):
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        all_marks = self._normalize_marks()
        figmarks_array = split_marks(all_marks)
        if select_txt:
            new_select_txt = select_txt
            for item in figmarks_array:
                fig_text = item.split(' ')[1]
                fig_num = item.split(' ')[0]
                new_select_txt = new_select_txt.replace(f'{fig_text}({fig_num})',f'{fig_text}{fig_num}')
                new_select_txt = new_select_txt.replace(f'{fig_text}（{fig_num}）',f'{fig_text}{fig_num}')
            out_txt = self._finish_replace(select_txt, new_select_txt)
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    def marks_to_para(self):
        try:
            marks_array = self.active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('	', ' ').strip('\u2029。 ').split('\u2029')
            out_txt = marks_array[0]
            temp_num = marks_array[0][0]
            for mark_index in range(1,len(marks_array)):
                _ = marks_array[mark_index]
                if _[0] == temp_num[0]:
                    out_txt += f'、{_}'
                elif _[0] != temp_num[0]:
                    out_txt += f'；\u2029{_}'
                if mark_index == len(marks_array) - 1:
                    out_txt += '。'
                temp_num = _[0]
            out_txt = '\u2029附图标记说明：\u2029' + out_txt
            self.active_textcomponent.insertHtml(out_txt)
        except Exception as e:
            print('Error Code 103',e)
    def extract_patent_content(self):#claim 2 content
        cursor = self.active_textcomponent.textCursor()
        all_marks = self._normalize_marks()
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        if select_txt:
            # 删除带括号标记
            new_select_txt = delete_bracketmarks(select_txt.replace(':','：').replace('所述的','所述'),all_marks)
            # 删除所有数字
            for num in range(99,0,-1):
                new_select_txt = new_select_txt.replace(f"{num}.",'')
            # 将“根据权利要求……,其特征在于：” 替换为”进一步的“
            find_txt_array = re.findall(r'根据.*?，其特征在于：',new_select_txt)
            for _ in find_txt_array:
                new_select_txt = new_select_txt.replace(_,'进一步的，')
            new_select_txt = new_select_txt.replace('一种','该').replace('其特征是：','其技术要点是：').replace('其特征在于：','其技术要点是：')
            out_txt = select_txt.strip('\u2029').replace(select_txt,new_select_txt).replace('。。','。').replace(' ','')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
    #获取附图标记
    def extract_figmarks(self):
        """从选中文本提取附图标记，输出到左侧标记面板。
        识别模式：
        1) 名称(标号)  如 壳体(1)、绑带（11）、电机(2a)
        2) 名称标号   如 壳体1、电机2a（后接标点或中文）
        输出格式：每行"标号 名称"，按标号数字排序，自动去重。"""
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        if not select_txt:
            return
        # 清洗：去掉年份、百分比、数量词，避免误识别
        cleaned = re.sub(r'(19|20)\d{2}\s*年', '', select_txt)
        cleaned = re.sub(r'\d+\s*%', '', cleaned)
        cleaned = re.sub(r'\d+\s*(个|件|台|套|次|项|倍|米|毫米|厘米|cm|mm|kg|g|度|伏|安|瓦)', '', cleaned)
        # 统一括号为全角
        cleaned = cleaned.replace('(', '（').replace(')', '）')
        # 提取标记：{标号: 名称}，同一标号取最长名称
        # 截词符：动词/介词，匹配到的名称按截词符分割，只保留后半部分
        # 如 "还包括壳体" → "壳体"，"通过绑带" → "绑带"
        split_words = ('还包括','包括','通过','设有','设置','具有','所述的','所述','根据','与','和',
                       '用于','在于','于',
                        '以上','以下','上述','中的')
        def extract_name(raw):
            for sw in split_words:
                if sw in raw:
                    tail = raw.split(sw)[-1].strip()
                    if 2 <= len(tail) <= 8:
                        return tail
                    return None
            return raw
        marks = {}
        # 模式1：名称（标号）  如 壳体（1）、绑带（11）
        for m in re.finditer(r'([\u4e00-\u9fa5]{2,15})（(\d{1,3}[a-zA-Z]?)）', cleaned):
            name = extract_name(m.group(1))
            num = m.group(2)
            if not name:
                continue
            if num not in marks or len(name) > len(marks[num]):
                marks[num] = name
        # 模式2：名称标号（无括号，后接标点/中文/结尾）
        for m in re.finditer(r'([\u4e00-\u9fa5]{2,15})(\d{1,3}[a-zA-Z]?)(?=[，。；、：\u4e00-\u9fa5]|$)', cleaned):
            raw = m.group(1)
            if raw[-1] in '个件台套次项倍米度':
                continue
            name = extract_name(raw)
            num = m.group(2)
            if not name:
                continue
            if num not in marks or len(name) > len(marks[num]):
                marks[num] = name
        # 按标号数字排序
        def sort_key(item):
            num = item[0]
            m = re.match(r'(\d+)', num)
            return (int(m.group(1)) if m else 999, num)
        sorted_marks = sorted(marks.items(), key=sort_key)
        # 输出"标号 名称"
        lines = [f'{num} {name}' for num, name in sorted_marks]
        if lines:
            self.active_figmark.insertPlainText('\n' + '\n'.join(lines))
    # 删除段号
    def del_paranum(self):
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        if select_txt:
            new_select_txt = select_txt
            del_array = re.findall(rf'\[\d\d\d\d\]',select_txt)
            for _ in del_array:
                new_select_txt = new_select_txt.replace(_ + ' \u2029','').replace(_ + '\u2029','').replace(_ + ' ','').replace(_,'')
            out_txt = self._finish_replace(select_txt, new_select_txt)
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
            self.active_textcomponent.setTextCursor(cursor)
    # 增加段号
    def add_paranum(self):
        cursor = self.active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t').replace('\n','\u2029').replace('］',']').replace('[','[')
        txt_array = select_txt.split('\u2029')
        para_array = []
        para_index = 1
        for para in txt_array:
            # 删除段号
            if para.strip('\n\u2029\r\t') in '技术领域 背景技术 发明内容 实用新型内容 附图说明 具体实施方式'.split(' ') or para == '':
                para_array.append(para)
            # 增加短号
            else:
                para_num = '[%04d]' % para_index
                para_array.append(f'{para_num} {para}')
                para_index += 1
        new_select_txt = '\n'.join(para_array)
        out_txt = select_txt.replace('\n','\u2029').replace(select_txt,new_select_txt).replace('。。','。')
        cursor.deleteChar()
        cursor.insertText(out_txt)
        self.get_same_markindex(out_txt,self.active_textcomponent,self.highlight_color)
        self.active_textcomponent.setTextCursor(cursor)
    def generate_oa_model(self):
        title = self._tab_title()
        all_txt = self.active_textcomponent.toHtml() + store.get_template('oa').replace('&lt;TITLE&gt;',title)
        self.active_textcomponent.clear()
        self.active_textcomponent.setHtml(all_txt)
    def generate_description_model(self):
        title = self._tab_title()
        all_txt = self.active_textcomponent.toHtml() + store.get_template('des').replace('&lt;标题&gt;',title)
        self.active_textcomponent.clear()
        self.active_textcomponent.setHtml(all_txt)
    def generate_claim_model(self):
        title = self._tab_title()
        all_txt = store.get_template('claim').replace('&lt;TITLE&gt;',title) + self.active_textcomponent.toHtml()
        self.active_textcomponent.clear()
        self.active_textcomponent.setHtml(all_txt)
    def generate_re_model(self):
        title = self._tab_title()
        all_txt = self.active_textcomponent.toHtml() + store.get_template('re').replace('&lt;TITLE&gt;',title)
        self.active_textcomponent.clear()
        self.active_textcomponent.setHtml(all_txt)
    def generate_invalid_model(self):
        title = self._tab_title()
        all_txt = self.active_textcomponent.toHtml() + store.get_template('invalid').replace('&lt;TITLE&gt;',title)
        self.active_textcomponent.clear()
        self.active_textcomponent.setHtml(all_txt)
    def image_marks(self, inputtxt, fig_dic):
        '''根据输入的编号串返回所有匹配的附图标记（多候选，按相关度排序）。

        支持数字 + a~d 后缀（如 11、11a、11b）。
        匹配规则：标记编号以输入串为前缀即命中，于是「输入 1」能列出 1/11/12…，
        方便发现；「输入 11」精确命中 11/11a/11b。
        排序：完全相等最优先，其余按编号长度升序、再字典序；最多返回 20 条。
        '''
        self.word_array, self.ori_array = [], []
        token = (inputtxt or '').strip().lower()
        if not token:
            return []
        matches = []
        for key in fig_dic:
            num = str(key[0]).lower()
            if num == token or num.startswith(token):
                matches.append((key[0], key[1]))
        matches.sort(key=lambda kv: (0 if kv[0].lower() == token else 1,
                                     len(kv[0]), kv[0]))
        matches = matches[:20]
        for num, name in matches:
            self.ori_array.append(num)
            self.word_array.append(name)
        return matches

    def _normalize_marks(self):
        """统一规范化附图标记文本：换行→段落符、中文分号→英文、Tab→空格、去首尾标点。"""
        return (self.active_figmark.toPlainText()
                .replace('\n', '\u2029').replace('；', ';')
                .replace('\t', ' ').strip('\u2029。 '))

    def _finish_replace(self, select_txt, new_txt):
        """替换文本后统一规范化：换行→段落符、替换、去双句号。"""
        return select_txt.replace('\n', '\u2029').replace(select_txt, new_txt).replace('。。', '。')

    def _tab_title(self):
        """当前文档标签名去掉「实用新型-」「发明-」前缀。"""
        idx = self.tab_widget_text.currentIndex()
        return self.tab_widget_text.tabText(idx).replace('实用新型-', '').replace('发明-', '')

    def get_totalkeys(self):
        try:
            self.key_1, self.key_2, self.key_3, self.key_4, self.key_5 = '', '', '', '', ''
            cursor = self.active_textcomponent.textCursor()
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, 5)
            self.total_key = cursor.selectedText()
            if len(self.total_key) >= 5:
                self.key_1, self.key_2, self.key_3, self.key_4, self.key_5 = self.total_key[:5]
        except Exception:
            pass
    def count_words(self, event):
        """点击状态栏：刷新统计并给出摘要；按位置决定是否进入缩放状态。

        缩放只发生在三类区域（见 _status_edge_region_at）：最底部窄边框
        （'down' 竖直缩放）、左下角 / 右下角（'ld' / 'rd' 对角缩放）。
        状态栏中部一律 drag_flag=False，拖拽无响应——旧实现无条件设成
        'down'，才导致「拖一下状态栏窗口就矮一截」。
        """
        # event.x()/y() 是相对状态栏自身的，用全局坐标换算成窗口坐标
        wx = event.globalX() - self.pos().x()
        wy = event.globalY() - self.pos().y()
        region = self._status_edge_region_at(wx, wy)
        grip = getattr(self, 'status_grip', None)
        targets = tuple(t for t in (self.status, grip) if t is not None)
        if region:
            self.old_x = self.pos().x()
            self.old_y = self.pos().y()
            self.old_width = self.width()
            self.old_height = self.height()
            self.drag_flag = region
            # 鼠标可能刚从窗口外落进来、还没经过一次 hover；按下时就设好
            # 光标，避免「能拖却显示普通箭头」。
            c = self._status_cursor_at(wx, wy)
            for widget in targets:
                widget.setCursor(c)
            # 显式抓取鼠标：拖出控件范围后仍持续收到 move（与边缘条同理）
            grabber = (grip if (grip is not None and
                       wy >= self.height() - self.STATUS_BOTTOM_GRIP)
                       else self.status)
            grabber.grabMouse()
            self._status_grabber = grabber
        else:
            self.drag_flag = False
            self._status_grabber = None
            for widget in targets:
                widget.setCursor(Qt.ArrowCursor)
        ed = self.active_textcomponent
        stats = wf.collect_text_stats(ed.toPlainText(), ed.textCursor().selectedText())
        self._refresh_status_bar()
        if stats['选中字数']:
            self.status.showMessage(
                '> 已选 %d 字 / 共 %d 字（含标点 %d 字，不含标点 %d 字）'
                % (stats['选中字数'], stats['字数'],
                   stats['字符数(计空格)'], stats['字符数(不计空格)']), 6000)
        else:
            self.status.showMessage(
                '> 共 %d 字（含标点 %d 字，不含标点 %d 字 · 段落 %d · 行 %d）'
                % (stats['字数'], stats['字符数(计空格)'],
                   stats['字符数(不计空格)'], stats['段落数'], stats['行数']), 6000)
    def get_word_array(self):
        self.fig_dic = {}
        all_marks = self._normalize_marks()
        figmarks_array = split_marks(all_marks)
        for _ in figmarks_array:
            fig_num, fig_text = judge_mark(_)
            self.fig_dic[fig_num] = fig_text
        fig_dic_t = self.fig_dic
        self.fig_dic = sorted(fig_dic_t.items(), key=lambda fig_dic_t: len(fig_dic_t[0]), reverse=True)
        self.image_marks(self.total_key, self.fig_dic)
    def fn_text_changed(self):
        # 补全弹窗已弹出时，不静默自动插入（避免与弹窗交互冲突）
        if self._completion_popup.isVisible():
            return
        select_txt = ''
        if self.write_auto == '补全' and self.total_key:
            self.total_key = ''
            cursor = self.active_textcomponent.textCursor()
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor,2)
            select_txt = cursor.selectedText()
            try:
                if select_txt[-1] not in '1234567890\u2029\n' and select_txt[0] in '1234567890':
                    cursor = self.active_textcomponent.textCursor()
                    for i in range(0,5):
                        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor,1)
                        select_txt = cursor.selectedText().replace(')','）').replace('(','（')
                        if select_txt[-1] in '（）[]<>《》\\{\\}':
                            self.total_key = ''
                            break
                        elif len(select_txt) > 1 and select_txt[0] in '1234567890' and select_txt[0] not in '（）[]<>《》\\{\\}':
                            self.total_key = select_txt[0:-1]
                        elif len(select_txt) > 1 and select_txt[0] in '（）[]<>《》\\{\\}':
                            break
                        elif len(select_txt) > 1 and select_txt[0] not in '1234567890':
                            break
                if self.total_key:
                    self.get_word_array()
                    if not self.word_array:
                        return
                    self.space_out_words()
                    if select_txt[-1] == '.':
                        self.active_textcomponent.insertPlainText('。')
                    else:
                        self.active_textcomponent.insertPlainText(select_txt[-1])
            except Exception as e:
                print(e)
    def fn_keyreleaseevent(self,event): # active_textcomponent 按下任意键
        if event.key() in [Qt.Key_Up,Qt.Key_Down,Qt.Key_Left,Qt.Key_Right]:
            self.reset_textcomponentformat()
            cursor = self.active_textcomponent.textCursor()
            self.get_same_markindex_1(cursor.selectedText(),self.active_textcomponent,self.highlight_color)
        # ---- 编号补全（搜狗式）：手动补全模式下，输入真实附图编号即弹出候选 ----
        # 不再强制要求先开「联想」开关——只要光标前输入的是附图标记编号，就像输入法
        # 那样实时给出候选，按空格/Enter/Tab 确认，↑↓ 选择，Esc 取消。无匹配则自动隐藏。
        token = self._mark_token_at_cursor()
        if self._completion_popup.isVisible():
            # 弹窗已打开：导航键（↑↓←→）已在 fn_keypressevent 处理，
            # 松开方向键时不重建弹窗，避免选中位置被重置回第一项。
            if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right,
                               Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter,
                               Qt.Key_Tab, Qt.Key_Space):
                return
            if self._completion_mode == 'mark':
                self.fn_refresh_mark_completion()
            elif self._completion_mode == 'keyword':
                self.fn_refresh_keyword_completion()
            return
        # 编号补全（搜狗式）：无论手动/自动补全模式，输入数字即弹出候选
        _digit_keys = frozenset(range(48, 58)) | frozenset(range(65, 72))
        if token:
            if (event.key() in _digit_keys) \
                    and not (event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
                self.fn_refresh_mark_completion()
                return
        # ---- 联想模式下的其余能力（高亮未用标记 / 关键词补全 / 序号自动续写） ----
        if self.model_type == '联想':
            self.get_totalkeys()
            try:
                # 高亮未使用标记
                if self.checkbox_markcheck.checkState() == 2: 
                    self.check_text_figmarks_unused()
                # 关键词联想输入：Ctrl+`
                elif self.checkbox_userwords.checkState() == 2 and self.total_key and event.modifiers() == Qt.ControlModifier and event.key() == 96: 
                    self.fn_refresh_keyword_completion()
                elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Return: # 判断序号 并自动续写
                    cursor = self.active_textcomponent.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock,QTextCursor.KeepAnchor,1)
                    cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                    cursor.movePosition(QTextCursor.MoveOperation.NextBlock,QTextCursor.KeepAnchor,2) # 包括前文1段内容
                    base_txt = cursor.selectedText()
                    cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                
                if base_txt[0:2] == '步骤':
                    base_num = base_txt[2]
                    cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                    cursor.insertHtml('步骤S' + str(int(base_num) + 1) +'，')
                elif base_txt[0:6] == '区别技术特征':
                    base_num = base_txt[6]
                    cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                    cursor.insertHtml('区别技术特征' + str(int(base_num) + 1) +'，')
                elif base_txt[0:8] == '对于区别技术特征':
                    base_num = base_txt[8]
                    cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                    cursor.insertHtml('对于区别技术特征' + str(int(base_num) + 1) +'，')
                elif base_txt[0] == '图' and base_txt[1] in '123456789':
                    if base_txt[2] in '1234567890':
                        base_num = base_txt[1:3]
                    else:
                        base_num = base_txt[1]
                    base_num = int(base_num) + 1
                    cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                    cursor.insertHtml(f'图{base_num}为本发明XXXX的结构示意图。')
                elif base_txt[0] in '01234567890':
                        base_num = ''
                        i = 0
                        for i, ch in enumerate(base_txt[:10]):
                            if ch not in '01234567890' and ch in '.、：:)）':
                                base_num = base_txt[0:i]
                                break
                        if base_num:
                            cn_txt = base_txt.replace(',', '，')
                            base_title = re.findall(r'一种(.*?)，', cn_txt) or re.findall(r'根据.*?所述的(.*?)，', cn_txt)
                            base_title = base_title[0] if base_title else ''
                            if f'{base_num}. 一种' in base_txt or f'{base_num}.一种' in base_txt:
                                cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                                cursor.insertHtml(str(int(base_num) + 1) + base_txt[i] + f'根据权利要求1所述的{base_title}，其特征在于：')
                            elif f'{base_num}. 根据权利要求' in base_txt or f'{base_num}.根据权利要求' in base_txt:
                                cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                                cursor.insertHtml(str(int(base_num) + 1) + base_txt[i] + f'根据权利要求1所述的{base_title}，其特征在于：')
                            else:
                                cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                                cursor.insertHtml(str(int(base_num) + 1) + base_txt[i])
                else:
                    self.key_1, self.key_2, self.key_3, self.key_4,self.key_5 = '', '', '', '',''
                    self.type_cursor == ''
                    return # 删除会导致 额外弹窗
            except Exception as e:
                pass
        else:
            return


    def fn_keypressevent(self, event):
        try:
            # 联想补全弹窗打开时，导航/确认键在此拦截，不再进入正文：
            # ↑↓ 选择、空格/Enter/Tab 确认、Esc 取消；其余键放行到正文，释放时再刷新候选。
            if self._completion_popup.isVisible():
                k = event.key()
                if k == Qt.Key_Escape:
                    self.fn_hide_completion(); return
                if k == Qt.Key_Left:
                    self._completion_popup.move_selection(-1); return
                if k == Qt.Key_Right:
                    self._completion_popup.move_selection(1); return
                if k == Qt.Key_Up:
                    self._completion_popup.move_page(-1); return
                if k == Qt.Key_Down:
                    self._completion_popup.move_page(1); return
                if k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Space):
                    self.fn_completion_accept(); return
                # 数字 / 字母 / 退格 等放行，由 fn_keyreleaseevent 负责刷新候选
            cursor = self.active_textcomponent.textCursor()
            clipboard = QApplication.clipboard()

            def copy_action():
                # 原实现在选区 >60 字时只写 text/html、不写 text/plain，
                # 浏览器/记事本等外部程序拿不到纯文本，表现就是"复制了却
                # 粘不进网页"。统一改走 _put_clipboard：纯文本 + HTML 都写。
                if cursor.hasSelection():
                    self._put_clipboard(cursor)
            def cut_action():
                if cursor.hasSelection():
                    self._put_clipboard(cursor)
                    cursor.removeSelectedText()

            def paste_action():
                if cursor.hasSelection():
                    cursor.removeSelectedText()
                text = clipboard.text()
                if not text:
                    text = self.clip_txt or ''
                if text:
                    cursor.insertText(text)
            def update_status():
                tab_index = self.tab_widget_text.currentIndex()
                tab_name = self.tab_name_array[tab_index]
                self.status.showMessage(f'> 《{tab_name}》 保存成功')
            # 定义按键映射
            key_mapping = {
                (Qt.ControlModifier, Qt.Key_C): copy_action,
                (Qt.ControlModifier, Qt.Key_X): cut_action,
                (Qt.ControlModifier, Qt.Key_V): paste_action,
                (Qt.ControlModifier, Qt.Key_1): lambda: self.complete_marknum(0),
                (Qt.ControlModifier, Qt.Key_2): lambda: self.complete_marknum(1),
                (Qt.ControlModifier, Qt.Key_3): lambda: self.complete_markname(0),
                (Qt.ControlModifier, Qt.Key_4): lambda: self.complete_markname(1),
                (Qt.ControlModifier, Qt.Key_5): self.delete_figmarks,
                (Qt.ControlModifier, Qt.Key_6): self.num_to_bracket_num,
                (Qt.ControlModifier, Qt.Key_7): self.bracket_num2num,
                (Qt.ControlModifier, Qt.Key_8): self.marks_to_para,
                (Qt.ControlModifier, Qt.Key_9): self.extract_patent_content,
                (Qt.ControlModifier | Qt.ShiftModifier, Qt.Key_H): lambda: self.fn_show_find_dialog(show_batch=True),
                (Qt.ControlModifier, Qt.Key_Q): self.extract_figmarks,
                (Qt.ControlModifier, Qt.Key_W): self.refine_form,
                (Qt.ControlModifier, Qt.Key_E): self.rep_element,
                (Qt.ControlModifier, Qt.Key_R): self.del_useless_enters,
                (Qt.ControlModifier, Qt.Key_T): self.del_spaces,
                (Qt.ControlModifier, Qt.Key_J): self.del_paranum,
                (Qt.ControlModifier, Qt.Key_G): self.add_paranum,
                (Qt.ControlModifier, 96): lambda: self.fn_refresh_keyword_completion() if self.checkbox_userwords.checkState() == 2 and self.total_key else None,
                (Qt.ControlModifier, Qt.Key_A): lambda: self.active_textcomponent.selectAll(),
                (Qt.ControlModifier, Qt.Key_Z): lambda: self.active_textcomponent.undo(),
                (Qt.ControlModifier, Qt.Key_Y): lambda: self.active_textcomponent.redo(),
                (Qt.ControlModifier, Qt.Key_S): lambda: (self.fn_texteditor_focusout_autosave(event), self.fn_textmark_focusout_autosave(event), update_status()),
                # Word 2019 常用快捷键：QAction 全局快捷键优先被 Qt 消费，
                # 这里作为编辑器焦点/窗口非激活时的兜底，不会重复触发。
                (Qt.ControlModifier, Qt.Key_H): self.fn_show_find_dialog,
                (Qt.ControlModifier, Qt.Key_P): self.fn_print,
                (Qt.ControlModifier | Qt.ShiftModifier, Qt.Key_G): self.fn_goto_line,
                (Qt.ControlModifier | Qt.ShiftModifier, Qt.Key_S): self.file_saveas,
                (Qt.ShiftModifier | Qt.AltModifier, Qt.Key_D): self.fn_insert_datetime,
                (Qt.NoModifier, Qt.Key_F11): self.fn_focus_mode,
                (Qt.NoModifier, Qt.Key_Insert): lambda: self.fn_set_overwrite_mode(not self._overwrite_mode),
                (Qt.AltModifier, Qt.Key_1): self.generate_oa_model,
                (Qt.AltModifier, Qt.Key_2): self.generate_description_model,
                (Qt.AltModifier, Qt.Key_3): self.generate_claim_model,
                (Qt.AltModifier, Qt.Key_4): self.generate_re_model,
                (Qt.AltModifier, Qt.Key_5): self.generate_invalid_model,
            }

            # 处理按键组合
            key_combination = (event.modifiers(), event.key())
            if key_combination in key_mapping:
                key_mapping[key_combination]()
            elif event.key() == Qt.Key_PageDown:
                cursor.movePosition(QTextCursor.Down, n=20)
                self.active_textcomponent.setTextCursor(cursor)
            elif event.key() == Qt.Key_PageUp:
                cursor.movePosition(QTextCursor.Up, n=20)
                self.active_textcomponent.setTextCursor(cursor)
            elif event.key() == Qt.Key_Escape:
                self.reset_textcomponentformat()
                self.fn_hide_completion()
                for window in [self.window_search, self.window_show,
                            self.window_rep, self.window_table]:
                    if window:
                        window.close()
                self._hide_tool_dock('symbol')
            elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                cursor.insertHtml('\u2029')
            elif event.key() in [Qt.Key_Delete, Qt.Key_Backspace, Qt.Key_Tab, Qt.Key_Home, Qt.Key_End]:
                # 空列表项行首按退格 / Delete → 先摘掉编号格式（「1.」删不掉的问题），
                # 否则照常删除前一个字符
                if event.key() in (Qt.Key_Backspace, Qt.Key_Delete) \
                        and self._clear_empty_list_at_cursor():
                    pass
                else:
                    actions = {
                        Qt.Key_Delete: cursor.deleteChar,
                        Qt.Key_Backspace: cursor.deletePreviousChar,
                        Qt.Key_Tab: lambda: cursor.insertText('\t'),
                        Qt.Key_Home: lambda: cursor.setPosition(0),
                        Qt.Key_End: lambda: cursor.setPosition(len(self.active_textcomponent.toPlainText()))
                    }
                    actions[event.key()]()
                    if event.key() in [Qt.Key_Home, Qt.Key_End]:
                        self.active_textcomponent.setTextCursor(cursor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
                directions = {
                    Qt.Key_Up: QTextCursor.Up,
                    Qt.Key_Down: QTextCursor.Down,
                    Qt.Key_Left: QTextCursor.Left,
                    Qt.Key_Right: QTextCursor.Right
                }
                self.active_textcomponent.moveCursor(directions[event.key()], QTextCursor.KeepAnchor)
            elif event.key() in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
                directions = {
                    Qt.Key_Up: QTextCursor.Up,
                    Qt.Key_Down: QTextCursor.Down,
                    Qt.Key_Left: QTextCursor.Left,
                    Qt.Key_Right: QTextCursor.Right
                }
                self.active_textcomponent.moveCursor(directions[event.key()])
            elif event.text() and event.text() in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                cursor.insertText(event.text())
                self.active_textcomponent.setTextCursor(cursor)
            elif event.modifiers() in [Qt.ControlModifier, Qt.AltModifier]:
                pass
            else:
                cursor.insertText(chr(event.key()))
        except Exception as e:
            pass


    # 校验未被使用的附图标记
    def check_text_figmarks_unused(self):
        self.reset_figmarkformat()
        self.fig_dic = {}
        all_marks = self._normalize_marks()
        figmarks_array = split_marks(all_marks)
        all_txt = self.active_textcomponent.toPlainText()
        for _ in figmarks_array:
            fig_num, fig_text = judge_mark(_)
            self.fig_dic[fig_num] = fig_text
        mark_index = 0
        for _ in self.fig_dic:
            mark_index += 1
            item = self.fig_dic[_]
            if item not in all_txt:
                # 选择相应行
                cursor = QTextCursor(self.active_figmark.document())
                cursor.movePosition(QTextCursor.Start)
                cursor.movePosition(QTextCursor.Down,QTextCursor.MoveAnchor, figmarks_array.index(f'{_} {item}'))
                cursor.movePosition(QTextCursor.StartOfLine)
                cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
                self.active_figmark.setTextCursor(cursor)
                # 设置高亮
                format = cursor.charFormat()
                format.setBackground(QColor(self.highlight_color))
                cursor.setCharFormat(format)
    # 补全自定义词库
    # 生成关联内容
    # 用于自由撰写的附图标记
    def fn_show_repwindow(self):
        self.window_rep = QWidget()
        self.window_rep_layout = QGridLayout(self.window_rep)
        self.window_rep_layout.setContentsMargins(6, 6, 6, 6)
        self.window_rep_layout.setSpacing(4)
        self.window_rep.setWindowTitle("批量替换")
        self.window_rep.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_rep.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.window_rep.setStyleSheet(
            'QWidget{background:#1e2730;color:#cdd9e3;}'
            'QTextEdit{background:#141c25;border:1px solid #33414f;border-radius:4px;'
            'padding:4px;font-size:12px;}QPushButton{background:#26323e;border:1px solid #3d4c5c;'
            'border-radius:3px;color:#cdd9e3;}QPushButton:hover{background:#2f6fb3;border-color:#4a76d6;}')
        self.window_rep.setFixedSize(250, 230)
        self.window_rep.move(self.pos().x() + self.width() - 265, self.pos().y() + 95)

        # 批量替换：左右两栏，每行一对「替换前 => 替换后」
        self.text_rep_left = QTextEdit()
        self.text_rep_left.setPlaceholderText('替换前（每行一个）')
        self.text_rep_left.setText(self.select_txt)

        self.text_rep_right = QTextEdit()
        self.text_rep_right.setPlaceholderText('替换后（每行一个）')
        self.text_rep_right.setText(self.select_txt)

        bt_find_prev = QPushButton(qta.icon('ri.arrow-left-s-line', color='white'), '')
        bt_find_prev.setToolTip('查找上一个')
        bt_find_prev.setFixedSize(34, 22)
        bt_find_prev.clicked.connect(self.fn_find_prev)

        bt_find_next = QPushButton(qta.icon('ri.arrow-right-s-line', color='white'), '')
        bt_find_next.setToolTip('查找下一个')
        bt_find_next.setFixedSize(34, 22)
        bt_find_next.clicked.connect(self.fn_find_next)

        bt_rep_one = QPushButton(qta.icon('fa6s.pencil', color='white'), '')
        bt_rep_one.setToolTip('替换当前')
        bt_rep_one.setFixedSize(34, 22)
        bt_rep_one.clicked.connect(self.fn_rep_one)

        bt_rep = QPushButton(qta.icon('fa5s.exchange-alt', color='white'), '')
        bt_rep.setToolTip('全部替换')
        bt_rep.setFixedSize(34, 22)
        bt_rep.clicked.connect(self.fn_rep)

        bt_close = QPushButton(qta.icon('fa5s.times', color='white'), '')
        bt_close.setToolTip('关闭')
        bt_close.setFixedSize(34, 22)
        bt_close.clicked.connect(lambda: self.window_rep.hide())

        self.window_rep_layout.addWidget(self.text_rep_left, 0, 0, 1, 1)
        self.window_rep_layout.addWidget(self.text_rep_right, 0, 1, 1, 1)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(4)
        for b in (bt_find_prev, bt_find_next, bt_rep_one, bt_rep, bt_close):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        self.window_rep_layout.addLayout(btn_row, 1, 0, 1, 2)
        # 固定批量模式（rep_model=1），单条模式不再使用
        self.rep_model = 1
    def fn_find_prev(self):
        find_txt = self.text_rep_left.toPlainText().strip().split('\n')[0]
        if not find_txt:
            return
        cursor = self.active_textcomponent.textCursor()
        doc = self.active_textcomponent.document()
        found = doc.find(find_txt, cursor, QTextDocument.FindBackward)
        if found.isNull():
            tail = QTextCursor(doc)
            tail.movePosition(QTextCursor.End)
            found = doc.find(find_txt, tail, QTextDocument.FindBackward)
        if not found.isNull():
            self.active_textcomponent.setTextCursor(found)
            self.active_textcomponent.ensureCursorVisible()
    def fn_find_next(self):
        find_txt = self.text_rep_left.toPlainText().strip().split('\n')[0]
        if not find_txt:
            return
        cursor = self.active_textcomponent.textCursor()
        doc = self.active_textcomponent.document()
        found = doc.find(find_txt, cursor)
        if found.isNull():
            found = doc.find(find_txt, QTextCursor(doc))
        if not found.isNull():
            self.active_textcomponent.setTextCursor(found)
            self.active_textcomponent.ensureCursorVisible()
    def fn_rep_one(self):
        before_txt = self.text_rep_left.toPlainText().strip().split('\n')[0]
        after_txt = self.text_rep_right.toPlainText().strip().split('\n')[0]
        cursor = self.active_textcomponent.textCursor()
        selected = cursor.selectedText().replace('\u2029', '\n')
        if selected == before_txt and before_txt:
            cursor.insertText(after_txt)
            self.active_textcomponent.setTextCursor(cursor)
            self.fn_find_next()
    def fn_rep(self):
        block_cursor = self.active_textcomponent.textCursor()
        line_number = block_cursor.blockNumber()
        total_paragraphs = self.active_textcomponent.document().blockCount()
        if line_number + 5 > total_paragraphs:
            line_number = total_paragraphs
        else:
            line_number += 5
        if self.rep_model == 0:
            before_txt = self.text_rename_before.toPlainText().strip('\n\u2029')
            end_txt = self.text_rename_after.toPlainText().strip('\n\u2029')
            self.rename_history_array = [f'{before_txt} => {end_txt}'] + self.rename_history_array
            if '^p' in before_txt:
                before_txt = before_txt.strip('\n\r\t\u2029').replace('^p', '\u2029')
            else:
                before_txt = before_txt.strip('\n\r\t\u2029')
            if '^p' in end_txt:
                end_txt = end_txt.strip('\n\r\t\u2029').replace('^p', '\u2029')
            else:
                end_txt = end_txt.strip('\n\r\t\u2029')
            if before_txt == ' ':
                all_txt = self.active_textcomponent.toHtml()
                rep_array = re.findall(r'>.*?<',all_txt)
                temp_array = []
                for item in rep_array:
                    if ' ' in item:
                        rep_item = item.replace(' ','')
                        temp_array.append(f'{item}_{rep_item}')
                for item in temp_array:
                    before_txt = item.split('<_>')[0] +'<'
                    end_txt = '>'+item.split('<_>')[1]
                    all_txt = all_txt.replace(before_txt, end_txt)
                self.active_textcomponent.setHtml(all_txt)
            elif end_txt != before_txt:
                all_txt = self.active_textcomponent.toHtml()
                all_txt = all_txt.replace(before_txt, end_txt)
                all_txt = all_txt.replace('实用新型人', '发明人')
                self.active_textcomponent.setHtml(all_txt)
            self.window_rep.hide()
            self.on_lineheight_changed()
        elif self.rep_model == 1:
            before_array = re.split('\n | \u2029',self.text_rep_left.toPlainText().strip('\n\u2029'))
            end_array = re.split('\n | \u2029',self.text_rep_right.toPlainText().strip('\n\u2029'))
            
            all_txt = self.active_textcomponent.toHtml()
            if before_array and len(before_array) == len(end_array):
                for i in range(0,len(before_array)):
                    before_txt = before_array[i]
                    end_txt = end_array[i]
                    all_txt = all_txt.replace(before_txt, end_txt)
            self.active_textcomponent.setHtml(all_txt)
        # 重新定位光标
        cursor = self.active_textcomponent.textCursor()
        cursor.movePosition(QTextCursor.Start)
        for _ in range(line_number):
            cursor.movePosition(QTextCursor.NextBlock)
        self.active_textcomponent.setTextCursor(cursor)
    def _sync_typev_strike(self, index):
        """编号格式下拉框：选中「删除线的 Num」时，收起状态也显示删除线。

        弹出列表里各条目用的是 item 的 FontRole，不受影响；收起状态由
        QComboBox 自身字体绘制，只能改控件字体来呈现。
        """
        try:
            f = QFont(self.combo_typev.font())
            f.setStrikeOut(index == 4)
            self.combo_typev.setFont(f)
        except Exception as e:
            print('Error Code 416', e)

    def space_out_words(self):
        insert_word = self.word_array[0]
        # 按序号取格式，不再比对显示文本（第 5 项显示为「删除线的 Num」，文本与第 4 项相同）
        # 0：(Num) 机架(1) / 1：（Num） 机架（1） / 2：[Num] 机架[1]
        # 3：Num 机架1 / 4：删除线的 Num → 只补名称
        _typev_fmt = ('({})', '（{}）', '[{}]', '{}', '')
        _typev_idx = self.combo_typev.currentIndex()
        self.type_v = self.combo_typev.currentText()
        for key in self.fig_dic:
            if insert_word == key[1]:
                _fmt = _typev_fmt[_typev_idx] if 0 <= _typev_idx < len(_typev_fmt) else '{}'
                all_word = f'{insert_word}{_fmt.format(key[0])}' if _fmt else insert_word
                all_word = all_word.replace(' ','')
                # 手动补全
                cursor = self.active_textcomponent.textCursor()
                if self.write_auto == '补全':
                    cursor.movePosition(QTextCursor.Left, 2)
                    cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(key[0]))
                elif self.write_auto == '关闭':
                    cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(key[0]))
                cursor.deleteChar()
                cursor.insertText(all_word)
                self.total_key = ''
                self.word_array = ''
                if self.window_show:self.window_show.close()
                break

    # ---------------- 联想补全弹窗（附图标记 / 关键词） ----------------
    def _typev_format(self):
        """按编号格式下拉框返回格式串；第 5 项（删除线 Num）返回空串 → 只补名称。"""
        idx = self.combo_typev.currentIndex()
        fmts = ('({})', '（{}）', '[{}]', '{}', '')
        return fmts[idx] if 0 <= idx < len(fmts) else '{}'

    def _mark_token_at_cursor(self):
        """取光标前「数字 + a~e 后缀」的连续串，作为当前正在输入的附图标记编号。"""
        try:
            cursor = self.active_textcomponent.textCursor()
            text_before = cursor.block().text()[:cursor.positionInBlock()]
            m = re.search(r'[0-9a-eA-E]+$', text_before)
            return m.group(0) if m else ''
        except Exception:
            return ''

    def fn_refresh_mark_completion(self):
        """根据光标前的编号刷新附图标记补全候选；无候选则隐藏弹窗。"""
        try:
            token = self._mark_token_at_cursor()
            self._completion_token = token
            self.total_key = token
            if not token:
                self.fn_hide_completion()
                return
            self.get_word_array()           # 重建 fig_dic 并按 token 匹配 word_array/ori_array
            fmt = self._typev_format()
            cands = []
            for num, name in zip(self.ori_array, self.word_array):
                preview = f'{name}{fmt.format(num)}' if fmt else name
                cands.append({'num': num, 'name': name, 'preview': preview})
            if not cands:
                self.fn_hide_completion()
                return
            self._completion_mode = 'mark'
            self._completion_popup.set_items(
                cands, 'mark', title='标记补全  ·  输入编号')
            self._position_completion_popup()
            self._completion_popup.show()
            self._completion_popup.raise_()
        except Exception as e:
            print('Error Code 419', e)

    def fn_refresh_keyword_completion(self):
        """根据光标前的文字刷新关键词补全候选；无候选则隐藏弹窗。"""
        try:
            token = (self.total_key or '').strip()
            if not token:
                self.fn_hide_completion()
                return
            words = [w.strip() for w in
                     self.text_genword.toPlainText().replace('\n', '\u2029').split('\u2029')
                     if w.strip()]
            words = list(dict.fromkeys(words))            # 去重保序
            tk = token.lower()
            cands = [{'text': w} for w in words
                     if w.lower().startswith(tk) or tk in w.lower()][:20]
            if not cands:
                self.fn_hide_completion()
                return
            self._completion_mode = 'keyword'
            self._completion_popup.set_items(
                cands, 'keyword', title='关键词补全  ·  Ctrl+`')
            self._position_completion_popup()
            self._completion_popup.show()
            self._completion_popup.raise_()
        except Exception as e:
            print('Error Code 420', e)

    def fn_completion_accept(self, payload=None):
        """确认当前/指定候选：按模式替换光标前的输入串。"""
        if payload is None:
            payload = self._completion_popup.current_payload()
        if not payload:
            self.fn_hide_completion()
            return
        try:
            if self._completion_mode == 'mark':
                self._apply_mark_completion(payload['num'], payload['name'])
            else:
                self._apply_keyword_completion(payload['text'])
        except Exception as e:
            print('Error Code 421', e)
        finally:
            self.fn_hide_completion()
            try:
                self.active_textcomponent.setFocus()
            except Exception:
                pass

    def _apply_mark_completion(self, number, name):
        fmt = self._typev_format()
        all_word = f'{name}{fmt.format(number)}' if fmt else name
        cursor = self.active_textcomponent.textCursor()
        token = self._completion_token
        if token:
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(token))
            cursor.removeSelectedText()
        cursor.insertText(all_word)
        self.total_key = ''
        self.word_array = []

    def _apply_keyword_completion(self, text):
        cursor = self.active_textcomponent.textCursor()
        token = (self.total_key or '').strip()
        if token:
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(token))
            cursor.removeSelectedText()
        cursor.insertText(text)
        self.total_key = ''

    def fn_hide_completion(self):
        try:
            if self._completion_popup.isVisible():
                self._completion_popup.hide()
        except Exception:
            pass
        self._completion_mode = ''
        self._completion_token = ''

    def _position_completion_popup(self):
        # 输入法式：紧跟光标位置弹出，而不是固定在窗口右上角
        ed = self.active_textcomponent
        w = self._completion_popup.width()
        h = self._completion_popup.height()
        # 光标在编辑器视口中的矩形 → 映射到全局坐标
        cursor = ed.textCursor()
        rect = ed.cursorRect(cursor)
        # 视口坐标 → 屏幕全局坐标
        top_left = ed.viewport().mapToGlobal(rect.topLeft())
        gx = top_left.x()
        gy = top_left.y() + rect.height() + 4   # 光标下方
        # 右边界溢出则左移
        screen = ed.screen().availableGeometry() if hasattr(ed, 'screen') and ed.screen() else None
        if screen is None:
            from PyQt5.QtWidgets import QApplication
            screen = QApplication.primaryScreen().availableGeometry()
        if gx + w > screen.right() - 8:
            gx = screen.right() - 8 - w
        if gx < screen.left() + 4:
            gx = screen.left() + 4
        # 底部溢出则翻到光标上方
        if gy + h > screen.bottom() - 8:
            gy = top_left.y() - h - 4
        self._completion_popup.move(gx, gy)

class WindowBook(FramelessResizableMixin, QWidget):
    """文本校验面板（Word 2019 风格检查结果窗格）。

    保留原有说明书 / 权利要求书合规检查算法，重做交互层：
    * 通过主窗口动态取当前编辑器，切换文档后不会再校验到旧文档；
    * 高亮改用 ExtraSelections，不再用 mergeCharFormat 永久改写正文格式；
    * 结果分为「问题清单 / 完整报告 / 对应表」三页，问题可点击定位；
    * UI 重写：品牌头、得分环 + 三级统计胶囊 + 会话趋势卡、卡片化结果页、
      问题搜索/筛选/排序/忽略、报告着色与多格式导出、可折叠检查项抽屉；
      自绘控件在 src/validation_ui.py；
    * 三个此前定义却从未被调用的检查项（术语一致性、空泛词、标号-名称）
      接入全文校验，可按开关选择；
    * 补齐空标记列表、短文档等场景的越界保护，单项异常不会中断整轮校验。
    """
    LEVEL_COLORS = {'严重': '#d9534f', '警告': '#e8a33d',
                    '提示': PAL['accent_hi'], '通过': '#5cb85c'}

    # 常见错别字/易混词表与同音误写识别已抽取为独立模块 src/typo_detector.py：
    # TYPO_PAIRS（易混词表）+ TERM_LEXICON（技术词库同音识别，依赖 pypinyin，
    # 缺失时自动只走词表层）。保留类属性别名，旧引用与测试不受影响。
    TYPO_PAIRS = typo_detector.TYPO_PAIRS

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.snap_target = main_window   # 拖到主窗口边缘附近时自动吸附
        self.dock_mark = main_window.dock_mark
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.setWindowTitle('')   # 去掉窗体标题
        # 独立可缩放窗口：不再停靠，也不置顶于其它程序——本应用失活时自动
        # 落到外部程序之后，不遮挡别的软件；但在本应用内部，主窗口点击 /
        # 激活时会把它重新抬到主窗口上方，正文永远不会盖住浮窗。
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setObjectName('ValidationPanel')
        self.setMinimumSize(380, 460)
        self.resize(560, 660)
        self._drag_offset = None
        self._dragging = False
        self.highlight_color = PAL['accent_hi']
        self.des_part_count = 0
        self._extra = []            # 当前编辑器上的非破坏性高亮
        self._issues = []           # [(级别, 类别, 位置, 说明, 扣分)]
        self._locate_map = {}       # (类别, 位置, 说明) -> 正文中的精确定位词
        self._fix_map = {}          # (类别, 位置, 说明) -> (原文片段, 建议改法)
        self._legend_rows = []      # 说明书「附图说明」解析出的编号→技术特征对应表
        self._legend_warnings = []
        self._legend_from = ''
        self._legend_loading = False
        self._legend_manual = False
        self._last_report = ''
        self.score = 100

        # 新增交互状态：本轮筛选、忽略标记与会话内得分历史（都不写磁盘）
        self._ignored = set()          # {(类别, 位置, 说明)} 标记为「已处理」
        self._level_filter = ''        # '' / 严重 / 警告 / 提示
        self._show_ignored = False
        self._score_history = []
        self._check_expanded = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        frame = QFrame(self)
        frame.setObjectName('ValidationFrame')
        outer.addWidget(frame)
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 去掉窗体标题：不再有 logo / 标题 / 副标题这一行，省下的 46px 全给内容。
        # 关闭按钮移到下方操作条；文档名作为数据显示在得分卡的元信息行。
        self._doc_name = ''   # 导出报告仍引用

        # ---- 操作条 ----
        tools = QWidget()
        tools.setObjectName('ValidationTools')
        tl = QHBoxLayout(tools)
        tl.setContentsMargins(10, 5, 10, 8)
        tl.setSpacing(6)
        # 「点击分数盘重新校验」提示条已移除：分数盘中心自带「↻ 重新校验」。
        # 操作条空白处继续作为无边框窗口的拖动抓手。
        self.set_drag_hint(tools)
        self.btn_clear = QPushButton('清除高亮')
        self.btn_clear.setToolTip('移除校验产生的临时高亮，不改动正文格式')
        self.btn_clear.clicked.connect(self.fn_clear_highlight)
        self.btn_export = QPushButton('导出报告')
        self.btn_export.setToolTip('导出为 txt / Markdown / CSV')
        self.btn_export.clicked.connect(self.fn_export_report)
        for b in (self.btn_clear, self.btn_export):
            b.setFixedHeight(29)
            b.setMinimumWidth(88)
            b.setCursor(Qt.ArrowCursor)   # 抓手光标不覆盖按钮
        self.btn_close = QToolButton()
        self.btn_close.setText('✕')
        self.btn_close.setObjectName('ValidationClose')
        self.btn_close.setToolTip('关闭校验面板')
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.ArrowCursor)
        self.btn_close.clicked.connect(self.fn_close_book)
        # 音效开关：只控制按键音（含校验结果提示音），不影响任何检查逻辑
        self.btn_sfx = QToolButton()
        self.btn_sfx.setObjectName('ValidationSfx')
        self.btn_sfx.setCheckable(True)
        self.btn_sfx.setFixedSize(24, 24)
        self.btn_sfx.setCursor(Qt.ArrowCursor)
        self.btn_sfx.clicked.connect(self.fn_toggle_sfx)
        self._sync_sfx_btn()
        tl.addStretch(1)
        tl.addWidget(self.btn_clear)
        tl.addWidget(self.btn_export)
        tl.addWidget(self.btn_sfx)
        tl.addWidget(self.btn_close)
        v.addWidget(tools)

        # ---- 得分概览卡：得分环 + 状态 + 分级筛选胶囊 + 历史趋势 ----
        card = QFrame()
        card.setObjectName('ValidationScoreCard')
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 9, 12, 9)
        cl.setSpacing(12)
        self.score_ring = ScoreRing()
        self.score_ring.recheckRequested.connect(self.submit_check_main)
        cl.addWidget(self.score_ring, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(5)
        self.lbl_summary = QLabel('尚未校验 — 点击分数盘开始')
        self.lbl_summary.setObjectName('ValidationSummary')
        self.lbl_summary.setWordWrap(True)
        col.addWidget(self.lbl_summary)
        chips = QHBoxLayout()
        chips.setSpacing(5)
        self._level_chips = {}
        for key, label in (('', '全部'), ('严重', '严重'), ('警告', '警告'),
                           ('提示', '提示')):
            b = QToolButton()
            b.setObjectName('ValidationLevelChip')
            b.setText(label)
            b.setCheckable(True)
            b.setChecked(key == '')
            b.setToolTip('只看「%s」级别的问题' % (label if key else '全部问题'))
            b.clicked.connect(lambda checked=False, k=key: self._set_level_filter(k))
            self._level_chips[key] = b
            chips.addWidget(b)
        chips.addStretch(1)
        col.addLayout(chips)
        self.spark_history = SparkLine()
        col.addWidget(self.spark_history)
        cl.addLayout(col, 1)
        card_wrap = QWidget()
        card_wrap.setObjectName('ValidationScoreWrap')
        cw = QHBoxLayout(card_wrap)
        cw.setContentsMargins(10, 8, 10, 4)
        cw.setSpacing(0)
        cw.addWidget(card)
        v.addWidget(card_wrap)

        # ---- 结果三页 ----
        self.tab_widget_book = QTabWidget()
        self.tab_widget_book.setObjectName('ValidationTabs')
        # 标签按实测文字宽度 + 余量排布：QSS 的 13px 字号会让默认 sizeHint
        # 算窄几个像素，「问题清单 (11)」的右括号被裁。细节见 _BookTabBar。
        self.tab_widget_book.setTabBar(_BookTabBar(self.tab_widget_book))
        # 标签文字保持完整：不再压缩 / 省略，宽度不够时出左右滚动按钮，
        # 拖宽窗口或点箭头即可看到被挡住的标签。
        tb = self.tab_widget_book.tabBar()
        tb.setElideMode(Qt.ElideNone)
        tb.setExpanding(False)
        tb.setUsesScrollButtons(True)

        # ① 问题清单：搜索 / 排序 / 忽略 / 右键菜单
        issues_page = QWidget()
        issues_page.setObjectName('ValidationIssuesPage')
        iv = QVBoxLayout(issues_page)
        iv.setContentsMargins(8, 8, 8, 8)
        iv.setSpacing(6)
        fbar = QWidget()
        fbar.setObjectName('ValidationFilterBar')
        fl = QHBoxLayout(fbar)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(5)
        self.edit_issue_filter = QLineEdit()
        self.edit_issue_filter.setObjectName('ValidationSearch')
        self.edit_issue_filter.setPlaceholderText('搜索类别 / 位置 / 说明…')
        self.edit_issue_filter.setClearButtonEnabled(True)
        self.edit_issue_filter.setFixedHeight(26)
        self.edit_issue_filter.textChanged.connect(self._apply_issue_filter)
        self.combo_sort = QComboBox()
        self.combo_sort.setObjectName('ValidationSort')
        self.combo_sort.addItems(['按原文顺序', '按扣分优先', '按类别分组'])
        self.combo_sort.setFixedWidth(102)
        self.combo_sort.setToolTip('问题清单排序方式')
        # 连接延后到 __init__ 末尾：addItems 会立刻发 currentIndexChanged，
        # 此刻 table_issues 还没创建，_render_issues 会踩空。
        self.btn_show_ignored = QToolButton()
        self.btn_show_ignored.setObjectName('ValidationIgnoredChip')
        self.btn_show_ignored.setText('已忽略 0')
        self.btn_show_ignored.setCheckable(True)
        self.btn_show_ignored.setToolTip('显示被标记为「已处理」的问题')
        self.btn_show_ignored.clicked.connect(self._toggle_show_ignored)
        self.btn_apply_all = QToolButton()
        self.btn_apply_all.setObjectName('ValidationGhostButton')
        self.btn_apply_all.setText('全部修改')
        self.btn_apply_all.setToolTip(
            '把清单中所有带「建议修改」的问题一次性写回正文；Ctrl+Z 可一次撤销')
        self.btn_apply_all.clicked.connect(self.fn_apply_all_fixes)
        fl.addWidget(self.edit_issue_filter, 1)
        fl.addWidget(self.combo_sort)
        fl.addWidget(self.btn_show_ignored)
        fl.addWidget(self.btn_apply_all)
        iv.addWidget(fbar)

        self.table_issues = QTableWidget(0, 6)
        self.table_issues.setHorizontalHeaderLabels(
            ['级别', '类别', '位置', '说明', '扣分', '修改'])
        self.table_issues.setColumnWidth(0, 52)
        self.table_issues.setColumnWidth(1, 80)
        self.table_issues.setColumnWidth(2, 92)
        self.table_issues.setColumnWidth(4, 46)
        self.table_issues.setColumnWidth(5, 84)
        self.table_issues.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_issues.setCornerButtonEnabled(False)
        self.table_issues.verticalHeader().setVisible(False)
        self.table_issues.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_issues.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_issues.setAlternatingRowColors(True)
        self.table_issues.cellClicked.connect(self.on_issue_clicked)
        self.table_issues.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_issues.customContextMenuRequested.connect(self._issue_context_menu)
        self.lbl_issues_empty = QLabel('没有符合条件的问题\n试试切换级别筛选或清空搜索词')
        self.lbl_issues_empty.setObjectName('ValidationIssuesEmpty')
        self.lbl_issues_empty.setAlignment(Qt.AlignCenter)
        self.lbl_issues_empty.setVisible(False)
        iv.addWidget(self.table_issues, 1)
        iv.addWidget(self.lbl_issues_empty)
        self.tab_widget_book.addTab(issues_page, '问题清单')

        # ② 完整报告：语法着色 + 一键复制
        report_page = QWidget()
        report_page.setObjectName('ValidationReportPage')
        rv = QVBoxLayout(report_page)
        rv.setContentsMargins(8, 8, 8, 8)
        rv.setSpacing(6)
        rbar = QHBoxLayout()
        rbar.setSpacing(6)
        self.btn_copy_report = QToolButton()
        self.btn_copy_report.setObjectName('ValidationGhostButton')
        self.btn_copy_report.setText('复制全文')
        self.btn_copy_report.setToolTip('把纯文本完整报告复制到剪贴板')
        self.btn_copy_report.clicked.connect(self._copy_report)
        self.lbl_report_stat = QLabel('尚未生成报告')
        self.lbl_report_stat.setObjectName('ValidationMeta')
        rbar.addWidget(self.btn_copy_report)
        rbar.addStretch(1)
        rbar.addWidget(self.lbl_report_stat)
        rv.addLayout(rbar)
        self.text_checkresult = QTextBrowser()
        self.text_checkresult.setFont(QFont('Microsoft YaHei', 11))
        self.text_checkresult.setPlaceholderText(
            '在左侧附图标记列表填入标记后，点击分数盘重新校验。\n'
            '说明书请按 技术领域 / 背景技术 / 发明内容或实用新型内容 / '
            '附图说明 / 具体实施方式 分段；权利要求书尽量不分段。')
        rv.addWidget(self.text_checkresult, 1)
        self.tab_widget_book.addTab(report_page, '完整报告')

        # ---- ③ 对应表显示区（论文 073/074 页）----
        # 从说明书「附图说明」自动解析「编号 → 技术特征」，可切换/自定义分隔符、
        # 手动增改删；任何改动都会自动重跑权利要求书与说明书查错。
        legend_page = QWidget()
        legend_page.setObjectName('ValidationLegendPage')
        lv = QVBoxLayout(legend_page)
        lv.setContentsMargins(8, 8, 8, 8)
        lv.setSpacing(7)
        status = QWidget()
        status.setObjectName('ValidationLegendStatus')
        sl = QHBoxLayout(status)
        sl.setContentsMargins(9, 6, 9, 6)
        sl.setSpacing(7)
        self.lbl_legend_badge = QLabel('0 条')
        self.lbl_legend_badge.setObjectName('ValidationLegendBadge')
        self.lbl_legend_badge.setToolTip('当前对应表条目数')
        self.lbl_legend_status = QLabel('等待解析附图说明')
        self.lbl_legend_status.setObjectName('ValidationLegendState')
        sl.addWidget(self.lbl_legend_badge)
        sl.addWidget(self.lbl_legend_status, 1)
        lv.addWidget(status)

        legend_bar = QWidget()
        lh = QHBoxLayout(legend_bar)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(5)
        sep_lbl = QLabel('分隔符')
        sep_lbl.setObjectName('ValidationMeta')
        self.combo_sep = QComboBox()
        self.combo_sep.addItems(list(fc.PAIR_SEP_PRESETS.keys()) + ['自定义'])
        self.combo_sep.setToolTip('编号与技术特征之间的分隔符号；解析失败时可切换或自定义')
        self.edit_sep = QLineEdit()
        self.edit_sep.setPlaceholderText('自定义')
        self.edit_sep.setFixedWidth(58)
        self.edit_sep.setEnabled(False)
        # 连接放到 __init__ 末尾：addItems 会触发 currentTextChanged，
        # 那时 lbl_legend / table_marks 还没建好。
        self.btn_reparse = QPushButton(qta.icon('mdi6.refresh'), '重新解析')
        self.btn_reparse.setToolTip('按当前分隔符重新提取附图说明中的编号与技术特征')
        self.btn_reparse.clicked.connect(lambda: self._reparse_legend())
        self.btn_add_row = QPushButton('增加')
        self.btn_add_row.setToolTip('手动补录一条「编号—技术特征」对应关系')
        self.btn_add_row.clicked.connect(self._legend_add_row)
        self.btn_del_row = QPushButton('删除')
        self.btn_del_row.setToolTip('删除选中的对应关系')
        self.btn_del_row.clicked.connect(self._legend_del_row)
        self.btn_legend_export = QToolButton()
        self.btn_legend_export.setObjectName('ValidationGhostButton')
        self.btn_legend_export.setText('导出 CSV')
        self.btn_legend_export.setToolTip('把当前对应表导出为 CSV，便于下次复用')
        self.btn_legend_export.clicked.connect(self._export_legend_csv)
        for w in (sep_lbl, self.combo_sep, self.edit_sep,
                  self.btn_reparse, self.btn_add_row, self.btn_del_row):
            lh.addWidget(w)
        lh.addStretch(1)
        lh.addWidget(self.btn_legend_export)
        lv.addWidget(legend_bar)
        self.lbl_legend = QLabel('尚未建立对应表 — 点击「重新解析」')
        self.lbl_legend.setObjectName('ValidationLegendHint')
        self.lbl_legend.setWordWrap(True)
        lv.addWidget(self.lbl_legend)

        self.table_marks = QTableWidget(0, 4)
        self.table_marks.setHorizontalHeaderLabels(['标号', '名称', '标号数', '名称数'])
        self.table_marks.setColumnWidth(0, 62)
        self.table_marks.setColumnWidth(2, 62)
        self.table_marks.setColumnWidth(3, 62)
        self.table_marks.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_marks.setCornerButtonEnabled(False)
        self.table_marks.verticalHeader().setVisible(False)
        # 前两列可编辑：论文「手动输入 / 修改 / 增加 / 删除，实时更新查找结果」
        self.table_marks.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table_marks.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_marks.setAlternatingRowColors(True)
        self.table_marks.itemClicked.connect(self.cell_clicked)
        self.table_marks.itemChanged.connect(self._on_legend_item_changed)
        lv.addWidget(self.table_marks, 1)
        self.tab_widget_book.addTab(legend_page, '对应表')
        v.addWidget(self.tab_widget_book, 1)

        # ---- 检查项抽屉：可折叠、可全选/全不选，按「论文规则 / 通用检查」分两行 ----
        opts = QWidget()
        opts.setObjectName('ValidationOptions')
        ov = QVBoxLayout(opts)
        ov.setContentsMargins(10, 7, 8, 7)
        ov.setSpacing(6)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.btn_toggle_checks = QToolButton()
        self.btn_toggle_checks.setObjectName('ValidationDisclosure')
        self.btn_toggle_checks.setText('▾  检查项')
        self.btn_toggle_checks.setCheckable(True)
        self.btn_toggle_checks.setChecked(True)
        self.btn_toggle_checks.setToolTip('折叠 / 展开检查项开关')
        self.btn_toggle_checks.clicked.connect(self._toggle_checks_group)
        self.lbl_check_count = QLabel('6 / 8 已启用')
        self.lbl_check_count.setObjectName('ValidationMeta')
        self.btn_all_checks = QToolButton()
        self.btn_all_checks.setObjectName('ValidationGhostButton')
        self.btn_all_checks.setText('全选')
        self.btn_all_checks.clicked.connect(lambda: self._set_all_checks(True))
        self.btn_none_checks = QToolButton()
        self.btn_none_checks.setObjectName('ValidationGhostButton')
        self.btn_none_checks.setText('全不选')
        self.btn_none_checks.clicked.connect(lambda: self._set_all_checks(False))
        bar.addWidget(self.btn_toggle_checks)
        bar.addWidget(self.lbl_check_count)
        bar.addStretch(1)
        bar.addWidget(self.btn_all_checks)
        bar.addWidget(self.btn_none_checks)
        # 宽度改由停靠区分隔条调整，不再放尺寸手柄（会误以为能拖动浮窗）
        ov.addLayout(bar)

        self.check_formal = QCheckBox('形式缺陷')
        self.check_formal.setChecked(True)
        self.check_formal.setToolTip('按《专利预审常见形式缺陷及查错软件设计实现》检查'
                                     '权利要求书/说明书形式缺陷与附图标记对应关系')
        self.check_claimtree = QCheckBox('权利要求树')
        self.check_claimtree.setChecked(True)
        self.check_terms = QCheckBox('术语一致性')
        self.check_terms.setChecked(True)
        self.check_vague = QCheckBox('空泛词')
        self.check_vague.setChecked(True)
        self.check_markname = QCheckBox('标号-名称')
        self.check_markname.setChecked(True)
        self.check_typo = QCheckBox('错别字')
        # 默认不启用：错别字 / 语法由「AI 内容校验」接管，避免与大模型结果重复报；
        # 需要纯离线检查时可在检查项里手动勾选。
        self.check_typo.setChecked(False)
        self.check_typo.setToolTip(
            '错别字识别模块：易混词表 + 同音误写识别（技术词库同音比对，'
            '疑似项橙色高亮），计入评分')
        self.check_grammar = QCheckBox('语法')
        self.check_grammar.setChecked(False)
        self.check_grammar.setToolTip('检查重复用字、重复标点、英文标点混用、括号不配对、超长句，计入评分')
        self.check_ai = QCheckBox('AI 内容校验')
        self.check_ai.setChecked(True)
        self.check_ai.setToolTip(
            '调用火山方舟大模型检查错别字 / 语法标点 / 表述问题；'
            '密钥与校验范围在「工具 → 服务 → AI 接口设置」中配置')
        self._all_checks = [self.check_formal, self.check_claimtree,
                            self.check_terms, self.check_vague,
                            self.check_markname, self.check_typo,
                            self.check_grammar, self.check_ai]
        self.checks_container = QWidget()
        self.checks_container.setObjectName('ValidationChecksBox')
        cv = QVBoxLayout(self.checks_container)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(4)
        for group in (self._all_checks[:4], self._all_checks[4:]):
            row = QHBoxLayout()
            row.setSpacing(10)
            for c in group:
                c.stateChanged.connect(self._sync_check_count)
                row.addWidget(c)
            row.addStretch(1)
            cv.addLayout(row)
        self._sync_check_count()          # 按上面的默认勾选状态刷新「N / 8 已启用」
        ov.addWidget(self.checks_container)
        v.addWidget(opts)

        self.combo_sep.currentTextChanged.connect(self._on_sep_mode_changed)
        self.combo_sort.currentIndexChanged.connect(self._render_issues)
        self.framewidget_1()

    # 动态绑定主窗口的当前编辑器 / 状态栏，切换文档后不失效
    @property
    def active_figmark(self):
        return self.mw.active_figmark

    @property
    def active_textcomponent(self):
        return self.mw.active_textcomponent

    @property
    def status(self):
        return self.mw.status

    def framewidget_1(self):
        self.refresh_doc_name()

    def refresh_doc_name(self):
        try:
            idx = self.mw.tab_widget_text.currentIndex()
            names = self.mw.tab_name_array
            name = names[idx] if 0 <= idx < len(names) else '当前文档'
        except Exception:
            name = '当前文档'
        self._doc_name = '当前文档：%s' % name

    # ---------------- 新增交互：筛选 / 排序 / 忽略 / 概览 ----------------
    def _set_level_filter(self, level):
        self._level_filter = level
        for k, b in self._level_chips.items():
            b.setChecked(k == level)
        self._apply_issue_filter()
        self.tab_widget_book.setCurrentIndex(0)

    def _toggle_show_ignored(self, checked=False):
        self._show_ignored = bool(checked)
        self._apply_issue_filter()

    def _set_all_checks(self, enabled):
        for c in self._all_checks:
            c.setChecked(bool(enabled))
        self._sync_check_count()

    def _toggle_checks_group(self, checked=False):
        self._check_expanded = bool(checked)
        self.checks_container.setVisible(self._check_expanded)
        self.btn_toggle_checks.setText('▾  检查项' if self._check_expanded
                                       else '▸  检查项')

    def _sync_check_count(self, *_):
        if not hasattr(self, 'lbl_check_count'):
            return
        n = sum(1 for c in self._all_checks if c.isChecked())
        self.lbl_check_count.setText('%d / %d 已启用' % (n, len(self._all_checks)))

    def _issue_tip(self, idx, detail=False):
        """问题行的悬停提示。

        detail=True 给「说明」列用：说明在表格里被省略号截断，悬停要能看到
        全文和具体改法。卡片固定 430px 宽，Qt 才会自动换行；不写宽度的话
        上百字的 AI 建议会排成一条超宽提示，贴到屏幕边直接被裁掉。

        颜色全部取 PAL / LEVEL_COLORS，与面板配色一致（提示框 QSS 的底色
        是 $hover，深色），不再出现浅底深字或纯黑字。
        """
        if not (0 <= idx < len(self._issues)):
            return ''
        level, cat, loc, msg, sc = self._issues[idx]
        color = self.LEVEL_COLORS.get(level, PAL['text'])

        def esc(text):
            return (str(text).replace('&', '&amp;').replace('<', '&lt;')
                    .replace('>', '&gt;'))

        head = ('<span style="color:%s; font-weight:600;">%s</span>'
                '<span style="color:%s;">　扣分 %s 分</span>'
                % (color, esc(level), PAL['text_mute'], esc(sc)))
        meta = ('<div style="color:%s; margin-top:3px;">类别：%s　位置：%s</div>'
                % (PAL['text_low'], esc(cat), esc(loc)))
        body = ('<div style="margin-top:6px; color:%s;">说明：%s</div>'
                % (PAL['text'], esc(msg)))
        if not detail:
            return '<div style="width:300px;">%s%s%s</div>' % (head, meta, body)

        fix_html = ''
        fix = self._fix_map.get(self._issue_key(idx))
        if fix:
            fix_html = ('<div style="margin-top:6px; color:%s;">建议：'
                        '把「<span style="color:#e2685f;">%s</span>」改为'
                        '「<span style="color:#5fd08a;">%s</span>」</div>'
                        % (PAL['text'], esc(fix[0]), esc(fix[1])))
        return ('<div style="width:430px;">%s%s%s%s'
                '<div style="color:%s; margin-top:6px;">'
                '单击行定位到正文　·　右键可忽略此条</div></div>'
                % (head, meta, body, fix_html, PAL['text_dim']))

    def _render_issues(self, *_):
        """按排序方式重建表格；每行用 UserRole 记住 _issues 里的原始下标。"""
        if not hasattr(self, 'table_issues'):
            return
        order = list(range(len(self._issues)))
        mode = self.combo_sort.currentIndex()
        if mode == 1:                       # 扣分优先（最严重的排最前）
            order.sort(key=lambda i: (self._issues[i][4], i))
        elif mode == 2:                     # 按类别 + 位置分组
            order.sort(key=lambda i: (self._issues[i][1], self._issues[i][2], i))
        self.table_issues.setRowCount(len(order))
        for r, i in enumerate(order):
            level, cat, loc, msg, sc = self._issues[i]
            # 悬停显示这条问题的详情。「说明」列用固定宽度的富文本卡片：
            # 说明文字常被省略号截断，AI 建议又可能上百字，不定宽的话 Qt 会
            # 排成一整条超宽提示，贴到屏幕边缘直接被裁掉。
            tip = self._issue_tip(i, detail=True)
            tip_short = self._issue_tip(i, detail=False)
            for c, value in enumerate((level, cat, loc, msg, str(sc))):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, i)
                # 让单元格字体跟随表格（QSS 字号已 +1），避免第一列被
                # setFont 固化成旧的较小字号
                item.setFont(self.table_issues.font())
                if c == 0:
                    item.setForeground(QColor(self.LEVEL_COLORS[level]))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                item.setToolTip(tip if c == 3 else tip_short)
                self.table_issues.setItem(r, c, item)
            # 第 6 列：带「原文 → 建议」的问题给「同意修改」按钮；
            # 原文里已找不到该片段时显示「已修改」，Ctrl+Z 撤销后自动恢复。
            # 旧按钮必须彻底脱离 viewport：removeCellWidget 只摘掉表格记录，
            # 不管的话重复渲染（每次点修改都会重排）会留下浮在 (0,0) 的残影。
            old = self.table_issues.cellWidget(r, 5)
            if old is not None:
                self.table_issues.removeCellWidget(r, 5)
                old.hide()
                old.setParent(None)
                old.deleteLater()
            state, fix = self._fix_state(i)
            if state == 'none':
                cell = QTableWidgetItem('—')
                cell.setToolTip(tip_short)
                cell.setData(Qt.UserRole, i)
                self.table_issues.setItem(r, 5, cell)
            else:
                btn = QToolButton()
                btn.setObjectName('ValidationGhostButton')
                btn.setText('同意修改' if state == 'ready' else '已修改')
                btn.setEnabled(state == 'ready')
                btn.setToolTip(
                    '把「%s」改为「%s」并写回正文（Ctrl+Z 可撤销）' % fix
                    if state == 'ready' else '该片段已不在正文中')
                btn.clicked.connect(
                    lambda _checked=False, idx=i: self.fn_apply_fix(idx))
                self.table_issues.setCellWidget(r, 5, btn)
        self._apply_issue_filter()

    def _row_issue_index(self, row):
        item = self.table_issues.item(row, 0)
        if item is None:
            return row
        data = item.data(Qt.UserRole)
        try:
            return int(data) if data is not None else row
        except (TypeError, ValueError):
            return row

    # ---------------- 建议修改 / 同意修改 ----------------

    def _issue_key(self, idx):
        if not (0 <= idx < len(self._issues)):
            return None
        _lv, cat, loc, msg, _sc = self._issues[idx]
        return (cat, loc, msg)

    def _fix_state(self, idx):
        """返回 (none / ready / done, (原文片段, 建议改法))。

        状态由正文实时判断：改过之后片段消失就是 done，Ctrl+Z 撤销后
        片段回来又自动变回 ready，不需要额外维护「已应用」集合。
        """
        key = self._issue_key(idx)
        if key is None:
            return 'none', None
        fix = self._fix_map.get(key)
        if not fix:
            return 'none', None
        original = (fix[0] or '').replace('\u2029', '\n')
        suggestion = str(fix[1] or '')
        if not original or not suggestion or original == suggestion:
            return 'none', None
        ed = self.active_textcomponent
        if ed is None or original not in ed.toPlainText():
            return 'done', (original, suggestion)
        return 'ready', (original, suggestion)

    def _replace_all(self, cursor, needle, replacement, limit=200):
        """把正文中 needle 的所有出现改成 replacement，返回改动处数。

        从上一次替换的末尾继续找，避免 replacement 含 needle 时死循环。
        """
        doc = cursor.document()
        start, n = 0, 0
        while n < limit:
            pos = doc.toPlainText().find(needle, start)
            if pos < 0:
                break
            cursor.setPosition(pos)
            cursor.setPosition(pos + len(needle), QTextCursor.KeepAnchor)
            cursor.insertText(replacement)
            start = pos + len(replacement)
            n += 1
        return n

    def fn_apply_fix(self, idx):
        """同意修改一行：把该问题的建议写回正文，Ctrl+Z 可撤销。"""
        state, fix = self._fix_state(idx)
        if state != 'ready':
            self.status.showMessage('> 这一行没有可自动应用的修改建议', 4000)
            return 0
        ed = self.active_textcomponent
        if ed is None:
            return 0
        cur = QTextCursor(ed.document())
        n = self._replace_all(cur, fix[0], fix[1])
        if not n:
            self.status.showMessage('> 正文中已找不到该片段', 4000)
            return 0
        self.status.showMessage(
            '> 已修改 %d 处：「%s」→「%s」（Ctrl+Z 可撤销）'
            % (n, fix[0][:16], fix[1][:16]), 6000)
        self._render_issues()
        return n

    def fn_apply_all_fixes(self):
        """一次应用清单里全部可改建议；包成一个 edit block，Ctrl+Z 一次撤销。"""
        ed = self.active_textcomponent
        if ed is None:
            return 0
        ready = []
        for i in range(len(self._issues)):
            state, fix = self._fix_state(i)
            if state == 'ready':
                ready.append(fix)
        if not ready:
            self.status.showMessage('> 没有可自动应用的修改建议', 4000)
            return 0
        cur = QTextCursor(ed.document())
        cur.beginEditBlock()
        n = 0
        try:
            for original, suggestion in ready:
                n += self._replace_all(cur, original, suggestion)
        finally:
            cur.endEditBlock()
        self.status.showMessage('> 已应用 %d 处修改（Ctrl+Z 一次撤销）' % n, 6000)
        self._render_issues()
        return n

    def _apply_issue_filter(self, *_):
        if not hasattr(self, 'table_issues') or not hasattr(self, 'edit_issue_filter'):
            return
        q = self.edit_issue_filter.text().strip().lower()
        level = self._level_filter
        visible = 0
        for r in range(self.table_issues.rowCount()):
            idx = self._row_issue_index(r)
            if not (0 <= idx < len(self._issues)):
                self.table_issues.setRowHidden(r, True)
                continue
            lv, cat, loc, msg, _sc = self._issues[idx]
            key = (cat, loc, msg)
            ignored = key in self._ignored
            ok = (not level or lv == level)
            if ok and q:
                ok = q in ('%s %s %s' % (cat, loc, msg)).lower()
            if self._show_ignored:
                ok = ok and ignored        # 该视图只列已处理项
            else:
                ok = ok and not ignored
            self.table_issues.setRowHidden(r, not ok)
            visible += bool(ok)
        self.btn_show_ignored.setText('已忽略 %d' % len(self._ignored))
        if not hasattr(self, 'lbl_issues_empty'):
            return
        self.lbl_issues_empty.setVisible(visible == 0)
        self.lbl_issues_empty.setText(
            '本轮没有发现问题' if self.table_issues.rowCount() == 0 else
            '没有符合条件的问题\n试试切换级别筛选或清空搜索词')

    def _issue_context_menu(self, pos):
        row = self.table_issues.rowAt(pos.y())
        idx = self._row_issue_index(row)
        if row < 0 or not (0 <= idx < len(self._issues)):
            return
        lv, cat, loc, msg, _sc = self._issues[idx]
        key = (cat, loc, msg)
        menu = QMenu(self)
        act_ignore = menu.addAction(
            '取消已处理' if key in self._ignored else '标记为已处理（本轮忽略）')
        act_locate = menu.addAction(qta.icon('mdi6.crosshairs-gps'), '定位到正文')
        state, _fix = self._fix_state(idx)
        act_fix = menu.addAction('同意修改这一行（写回正文）') if state == 'ready' else None
        act_copy = menu.addAction('复制这条说明')
        chosen = menu.exec_(self.table_issues.viewport().mapToGlobal(pos))
        if chosen is act_ignore:
            if key in self._ignored:
                self._ignored.discard(key)
            else:
                self._ignored.add(key)
            self._apply_issue_filter()
        elif chosen is act_locate:
            self.on_issue_clicked(row, 0)
        elif act_fix is not None and chosen is act_fix:
            self.fn_apply_fix(idx)
        elif chosen is act_copy:
            QApplication.clipboard().setText(
                '[%s] %s | %s | %s' % (lv, cat, loc, msg))

    def reset_state(self):
        """切文档后回到「未校验」状态：清结果与高亮，等待用户手动校验。

        校验只在点击分数盘时触发；切换文档不自动重跑，避免打断浏览，
        旧文档的结果也不能留着误导，所以一并清成初始待校验态。
        """
        self._clear_highlights()
        self.ckresult_txt = ''
        self._last_report = ''
        self._issues = []
        self._locate_map = {}
        self._fix_map = {}
        self.text_checkresult.clear()
        self.table_issues.setRowCount(0)
        self.refresh_doc_name()
        self.score_ring.markPending()
        self.lbl_summary.setText('尚未校验 — 点击分数盘开始')
        self.lbl_summary.setStyleSheet('')
        for k, b in self._level_chips.items():
            b.setText('全部' if not k else k)

    def _update_score_card(self):
        serious = sum(1 for x in self._issues if x[0] == '严重')
        warning = sum(1 for x in self._issues if x[0] == '警告')
        tips = len(self._issues) - serious - warning
        self.score_ring.setValue(self.score, serious)
        self._score_history.append(self.score)
        self.spark_history.setValues(self._score_history)
        counts = {'': len(self._issues), '严重': serious,
                  '警告': warning, '提示': tips}
        for k, b in self._level_chips.items():
            b.setText(('全部 %d' % counts[k]) if not k
                      else ('%s %d' % (k, counts[k])))
        verdict = ('存在 %d 项严重问题，建议优先处理' % serious) if serious else (
            '发现 %d 项待修改' % len(self._issues)) if self._issues else (
            '未发现问题，形式检查通过')
        self.lbl_summary.setText('%s · 得分 %d / 100' % (verdict, self.score))
        self.lbl_summary.setStyleSheet('color:%s;' % (
            '#e2685f' if serious else '#e8a33d' if self._issues else '#63b96b'))

    @staticmethod
    def _report_to_html(text):
        """纯文本报告 → 轻度语法着色的 HTML；正文先转义，<> 不会被当标签。"""
        if not text:
            return '<p style="color:#8997a5;">尚未生成报告</p>'
        out = ['<div style="font-family:Microsoft YaHei,Consolas; font-size:11px; '
               'line-height:1.55; color:#dbe4ed;">']
        for line in text.splitlines():
            s = _html.escape(line.rstrip())
            if not s:
                out.append('<div style="height:5px;"></div>')
                continue
            if '形式缺陷' in line:
                color, weight = '#8fd0ff', 'bold'
            elif '未完成' in line or '错误' in line:
                color, weight = '#e2685f', 'normal'
            elif line.startswith('[') or line.startswith('<'):
                color, weight = '#e8a33d', 'normal'
            elif '得分' in line:
                color, weight = '#63b96b', 'bold'
            else:
                color, weight = '#dbe4ed', 'normal'
            out.append('<div style="color:%s; font-weight:%s; '
                       'white-space:pre-wrap;">%s</div>' % (color, weight, s))
        out.append('</div>')
        return ''.join(out)

    def _copy_report(self):
        QApplication.clipboard().setText(self._last_report or '')
        self.status.showMessage('> 完整报告已复制到剪贴板', 4000)

    def _export_legend_csv(self):
        name = '对应表_%s.csv' % time.strftime('%Y%m%d_%H%M%S')
        path, _ = QFileDialog.getSaveFileName(self, '导出对应表', name,
                                              'CSV (*.csv)')
        if not path:
            return
        rows = self._legend_rows_from_table()
        try:
            with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                wr = csv.writer(f)
                wr.writerow(['标号', '名称'])
                for r in rows:
                    wr.writerow([r['num'], r['name']])
            self.status.showMessage('> 对应表已导出：%s' % path, 6000)
        except Exception as exc:
            wf.notice(self, '导出失败', '无法写入对应表文件。',
                      detail=str(exc), kind='warning', width=420)

    # ---------------- 非破坏性高亮 ----------------
    def _clear_highlights(self):
        ed = self.active_textcomponent
        self._extra = []
        if ed is not None:
            try:
                ed.setExtraSelections([])
            except Exception:
                pass

    def _add_highlight(self, start, length, color):
        ed = self.active_textcomponent
        if ed is None or length <= 0 or start < 0:
            return
        doc = ed.document()
        if start + length > doc.characterCount():
            return
        cur = QTextCursor(doc)
        cur.setPosition(start)
        cur.setPosition(start + length, QTextCursor.KeepAnchor)
        sel = QTextEdit.ExtraSelection()
        sel.cursor = cur
        sel.format.setBackground(QColor(color))
        sel.format.setForeground(QColor('#ffffff'))
        self._extra.append(sel)
        if len(self._extra) <= 600:
            ed.setExtraSelections(list(self._extra))

    def _highlight_pattern(self, editor, needle, color, literal=True):
        """把命中的字符串做成临时高亮，不写入文档格式。"""
        if editor is None or not needle or needle == '.':
            return
        try:
            needle = needle.replace('\u2029', '\n')
            pattern = re.escape(needle) if literal else needle
            text = editor.toPlainText().replace('\u2029', '\n')
            hits = list(re.finditer(pattern, text, re.S))[:400]
        except Exception:
            return
        selections = []
        for m in hits:
            cur = QTextCursor(editor.document())
            cur.setPosition(m.start())
            cur.setPosition(m.end(), QTextCursor.KeepAnchor)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cur
            sel.format.setBackground(QColor(color))
            sel.format.setForeground(QColor('#ffffff'))
            selections.append(sel)
        editor.setExtraSelections(selections)
        if editor is self.active_textcomponent:
            self._extra = list(selections)

    def fn_clear_highlight(self):
        self._clear_highlights()
        self.status.showMessage('> 已清除校验高亮', 3000)

    def reset_textcomponentformat(self):
        """旧实现会把整篇正文的字体/颜色/背景一次性清掉；现在只清临时高亮。"""
        self._clear_highlights()
    def _push_issue(self, category, location, message, score):
        """登记一条结构化发现；叙述文本由各检查项自行写入完整报告，避免重复。"""
        self.dataframe_list.append(['', category, location, message, str(score)])

    def check_terms_consistency(self, quiet=False):
        """技术术语一致性：同一术语混用「该 / 上述 / 其」等前缀时提示。"""
        text = self.active_textcomponent.toPlainText()
        pattern = re.compile(r'(该|上述|其)([\u4e00-\u9fa5]{2,8})')
        term_prefix, term_count = {}, {}
        for m in pattern.finditer(text):
            prefix, term = m.group(1), m.group(2)
            term_prefix.setdefault(term, set()).add(prefix)
            term_count[term] = term_count.get(term, 0) + 1
        inconsistent = sorted(
            [(t, sorted(p), term_count[t]) for t, p in term_prefix.items()
             if term_count[t] >= 3 and len(p) >= 2],
            key=lambda x: -x[2])
        self.ckresult_txt += '\u2029=== 术语一致性检查 ===\u2029'
        if not inconsistent:
            self.ckresult_txt += '未发现明显的指代不一致。\u2029'
            return []
        self.ckresult_txt += '发现 %d 个术语混用指代前缀：\u2029' % len(inconsistent)
        for term, prefixes, cnt in inconsistent[:30]:
            msg = '「%s」共出现%d次，混用前缀：%s' % (term, cnt, '、'.join(prefixes))
            self.ckresult_txt += '  ' + msg + '\u2029'
            self._push_issue('术语一致性', '全文', msg, -2)
            for m in re.finditer(re.escape(term), text):
                self._add_highlight(m.start(), len(term), '#e55f00')
        self.ckresult_txt += '建议：全文统一为一种指代。\u2029'
        return inconsistent

    def check_vague_words(self, quiet=False):
        """专利法 26 条 3/4 款空泛词自检（句末「等」单独匹配，减少误报）。"""
        patterns = [
            ('等', r'等(?=[，。；、,;）)]|\s|$)'),
            ('大约', r'大约'), ('优选地', r'优选地'), ('例如', r'例如'),
            ('最好', r'最好'), ('特别是', r'特别是'), ('左右', r'左右'),
            ('上下', r'上下'), ('基本上', r'基本上'), ('本质上', r'本质上'),
            ('大概', r'大概'), ('尽量', r'尽量'), ('较为', r'较为'),
        ]
        text = self.active_textcomponent.toPlainText()
        self.ckresult_txt += '\u2029=== 专利法26条3/4款 空泛词检查 ===\u2029'
        total = 0
        for word, pat in patterns:
            try:
                hits = list(re.finditer(pat, text))
            except Exception:
                continue
            if not hits:
                continue
            total += len(hits)
            self.ckresult_txt += '  「%s」出现 %d 次\u2029' % (word, len(hits))
            self._push_issue('空泛词', '全文',
                             '「%s」出现 %d 次，建议给出明确限定' % (word, len(hits)), -1)
            for m in hits[:100]:
                self._add_highlight(m.start(), m.end() - m.start(), '#c9a227')
        self.ckresult_txt += '合计空泛词 %d 处（黄色高亮）。\u2029' % total
        self.ckresult_txt += ('提示：26条3款要求充分公开、4款要求权利要求得到说明书支持；'
                              '空泛词过多会使保护范围不清楚。\u2029')
        return total

    def check_typos(self):
        """错别字检查：typo_detector 模块（易混词表 + 同音误写识别）。

        词表命中（-2 确定 / -1 易混）红色高亮；同音误写疑似（-1）橙色
        高亮，均计入评分，点击问题清单可定位。
        """
        text = self.active_textcomponent.toPlainText()
        self.ckresult_txt += '\u2029=== 错别字检查 ===\u2029'
        try:
            findings = typo_detector.detect(text)
        except Exception as e:
            self.ckresult_txt += '  错别字检查异常：%s\u2029' % e
            return 0
        found = 0
        for f in findings:
            wrong, right, sc = f['wrong'], f['correct'], f['score']
            cnt = f['count']
            found += cnt
            if f['kind'] in ('homophone', 'pinyin_stat'):
                msg = '「%s」疑似「%s」的同音误写，请核对' % (wrong, right)
            elif sc <= -2:
                msg = '「%s」应为「%s」' % (wrong, right)
            else:
                msg = '「%s」请核对语境，通常应写「%s」' % (wrong, right)
            self.ckresult_txt += '  「%s」→「%s」出现 %d 次\u2029' % (
                wrong, right, cnt)
            issue_msg = '%s（出现 %d 次）' % (msg, cnt)
            self._push_issue('错别字', '全文', issue_msg, sc)
            # 只给确定误写（-2 且非疑似同音）登记自动改法，疑似项不自动改正文
            if f['kind'] not in ('homophone', 'pinyin_stat') and sc <= -2:
                self._fix_map[('错别字', '全文', issue_msg)] = (wrong, right)
            color = '#d9534f' if sc <= -2 else '#f0ad4e'
            for pos in f['positions'][:100]:
                self._add_highlight(pos, len(wrong), color)
        if found:
            self.ckresult_txt += '合计 %d 处（红色=错误 / 橙色=疑似），点击问题清单可定位。\u2029' % found
        else:
            self.ckresult_txt += '未发现错别字。\u2029'
        return found

    def check_grammar_rules(self):
        """语法与标点检查：规则可解释、离线执行，命中即高亮并计入评分。

        覆盖：重复用字 / 重复标点 / 中文句内英文标点 / 括号不配对 / 超长句。
        （方法名避开同名复选框 self.check_grammar）
        """
        text = self.active_textcomponent.toPlainText()
        self.ckresult_txt += '\u2029=== 语法与标点检查 ===\u2029'
        found = 0

        def line_of(pos):
            return text.count('\n', 0, pos) + 1

        def add(loc, msg, sc, pos=None, length=0, color='#e2685f'):
            nonlocal found
            found += 1
            self._push_issue('语法', loc, msg, sc)
            if pos is not None and length:
                self._add_highlight(pos, length, color)

        # 1) 正则类规则（各上限 100 条，避免刷屏）
        regex_rules = [
            ('重复用字', re.compile(r'(的的|地地|得得|了了|是是|在在)'), -2),
            ('重复标点', re.compile(r'[。，,；;、]{2,}'), -1),
            ('中文句内英文标点', re.compile(r'[\u4e00-\u9fa5][,;:!?]'), -1),
        ]
        for name, pat, sc in regex_rules:
            count = 0
            for m in pat.finditer(text):
                if count >= 100 or found >= 400:
                    break
                add('第%d行' % line_of(m.start()),
                    '%s：「%s」' % (name, m.group(0)), sc,
                    m.start(), m.end() - m.start())
                count += 1

        # 2) 括号不配对（逐行统计，每行只报一次）
        bracket_pairs = [('(', ')'), ('（', '）'), ('[', ']'),
                         ('【', '】'), ('{', '}')]
        for i, line in enumerate(text.split('\n'), 1):
            if found >= 400:
                break
            for lch, rch in bracket_pairs:
                if line.count(lch) != line.count(rch):
                    add('第%d行' % i,
                        '括号不配对：「%s」%d 个、「%s」%d 个'
                        % (lch, line.count(lch), rch, line.count(rch)), -1)
                    break

        # 3) 超长句：按句末标点分句后仍超过 160 字无停顿
        sent_split = re.compile(r'[。；：！？!?]')
        for i, line in enumerate(text.split('\n'), 1):
            if found >= 400:
                break
            for seg in sent_split.split(line):
                seg = seg.strip()
                if len(seg) > 160:
                    add('第%d行' % i,
                        '句子过长（约 %d 字无停顿），建议拆分' % len(seg), -1)
                    break

        if found:
            self.ckresult_txt += '合计 %d 处（红色高亮），点击问题清单可定位。\u2029' % found
        else:
            self.ckresult_txt += '未发现语法/标点问题。\u2029'
        return found

    def closeEvent(self, event):
        """AI 请求未结束时不要销毁窗口（QThread 正挂在窗口对象上）。

        等后台线程发 finished 后自动重试关闭，避免 PyQt 抛出
        「QThread: Destroyed while thread is still running」。
        """
        worker = getattr(self, '_ai_worker', None)
        if worker is not None and worker.isRunning():
            event.ignore()
            try:
                worker.finished.connect(self.close)
            except Exception:
                pass
            try:
                self.status.showMessage('AI 内容校验结束后自动关闭校验窗口', 4000)
            except Exception:
                pass
            return
        ring = getattr(self, 'score_ring', None)
        if ring is not None:
            ring.setBusy(False)         # 无限循环动画不能随窗口一起被硬销毁
        super().closeEvent(event)

    def _await_ai(self, fn, timeout_ms):
        """后台线程执行 fn；主线程用局部事件循环等待，界面仍可响应。

        返回 ('ok', 值) / ('error', 说明)；超时返回 None（线程结果丢弃）。
        """
        if ai_check.Worker is None:
            return None
        loop = QEventLoop()
        box = {}
        worker = ai_check.Worker(fn, self)
        self._ai_worker = worker       # 保住引用，防止线程运行中被回收

        def _done(res):
            box['result'] = res
            loop.quit()

        # 显式排队回主线程：worker 线程只负责 emit，local loop 与结果字典
        # 都在主线程里收尾，避免跨线程碰 UI 对象。
        worker.finished_with.connect(_done, Qt.QueuedConnection)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(max(1000, int(timeout_ms)))
        worker.start()
        loop.exec_()
        timer.stop()
        if 'result' not in box:
            try:
                worker.finished_with.disconnect(_done)
            except Exception:
                pass
            return None
        return box['result']

    def check_ai_content(self):
        """AI 内容校验：火山方舟模型检查错别字 / 语法标点 / 表述。

        结果并入问题清单、完整报告与正文高亮；未配置、超时或接口异常时
        只写一行说明，离线检查与评分完全不受影响。
        """
        cfg = ai_check.load_config()
        self.ckresult_txt += '\u2029=== AI 内容校验（火山方舟） ===\u2029'

        def _note(msg):
            """零结果时把原因同时写进报告和问题清单，避免「静默没发现」。

            以前超时 / 未启用 / 解析失败只在报告里留一行，用户看问题清单时
            会以为模型检查过却一个错都没找到。现在清单里也会出现一条
            「系统 / AI 内容校验」，score=0，不影响评分。
            """
            self.ckresult_txt += msg + '\u2029'
            self._push_issue('系统', 'AI 内容校验', msg.strip(), 0)
            self.status.showMessage(msg.strip(), 8000)

        if not cfg.get('enabled'):
            _note('未启用（工具 → 服务 → AI 接口设置 中开启）。')
            return 0
        miss = ai_check.missing_fields(cfg)
        if miss:
            _note('未配置：%s，请在「工具 → 服务 → AI 接口设置」中填写。'
                  % '、'.join(miss))
            return 0
        text = self.active_textcomponent.toPlainText()
        if not text.strip():
            return 0
        self.status.showMessage('AI 内容校验中（快速模式，通常数秒）…', 0)
        # 快速模式下多批并发、每批一次重试预算，最坏约 2×timeout；
        # 关闭快速模式时批次串行，最坏 timeout*(批数+1)。等待上限必须给足，
        # 否则局部事件循环先超时会把算出来的结果丢掉，表现为「一个错都没发现」。
        if cfg.get('fast_mode', True):
            total_ms = (int(cfg['timeout']) * 2 + 20) * 1000
        else:
            total_ms = (int(cfg['timeout']) * (int(cfg['max_batches']) + 1) + 15) * 1000
        self._ai_running = True
        ring = getattr(self, 'score_ring', None)
        if ring is not None:
            ring.setBusy(True)          # 外环亮弧往复扫动，等待模型返回期间可见
        t0 = time.time()
        try:
            result = self._await_ai(lambda: ai_check.check_text(text, cfg), total_ms)
        finally:
            self._ai_elapsed = time.time() - t0
            self._ai_running = False
            if ring is not None:
                ring.setBusy(False)
        self.status.showMessage('文本校验中...', 0)
        self.ckresult_txt += '本次 AI 调用耗时 %.1f 秒\u2029' % self._ai_elapsed
        if result is None:
            _note('AI 校验超时或线程不可用，已跳过；离线检查不受影响。'
                  '可在「AI 接口设置」里调大超时后重试。')
            return 0
        state, value = result
        if state != 'ok':
            _note('AI 校验失败：%s' % value)
            return 0
        findings, err = value
        if err:
            self.ckresult_txt += '部分批次未完成：%s；已返回的结果仍有效。\u2029' % err
        if not findings:
            _note('模型未发现额外的内容问题。' if not err
                  else '未取得模型结果（%s），可在「AI 接口设置」里调大超时后重试。' % err)
            return 0
        self.ckresult_txt += ('模型发现 %d 处（类别标注 AI·…，点击问题清单可定位）：\u2029'
                              % len(findings))
        for f in findings:
            original = f['original']
            cat = 'AI·' + f['type']
            needle = original.replace('\u2029', '\n')
            pos = text.find(needle)
            loc = ('第%d行' % (text.count('\n', 0, pos) + 1)) if pos >= 0 else '全文'
            msg = '「%s」→「%s」：%s' % (
                original, f['suggestion'] or '请核对语境',
                f['reason'] or '建议核对语境')
            sc = -2 if f['severity'] == '严重' else -1
            self._push_issue(cat, loc, msg, sc)
            # 有明确改法才允许「同意修改」；「请核对语境」这类不算可自动改。
            sug = (f.get('suggestion') or '').strip()
            if sug and not sug.startswith('请') and '核对' not in sug:
                self._fix_map[(cat, loc, msg)] = (needle, sug)
            if pos >= 0:
                self._add_highlight(pos, len(needle),
                                    '#d9534f' if f['type'] == '错别字' else '#8e6bd8')
                self._locate_map[(cat, loc, msg)] = original
            self.ckresult_txt += '  [%s] %s\u2029' % (cat, msg)
        return len(findings)

    def check_mark_name_consistency(self):
        """标号-名称对应关系：同一标号多名称 / 同一名称多标号 / 正文编号不符。

        旧版用「任意 2~15 个汉字 + (标号)」抓正文，会把「倾斜固定于机架（1）」
        里的动词短语当成部件名称，几乎每个标号都误报。现在只拿左侧标记列表里
        已经登记的名称去正文里比对，结果才具备可操作性。
        """
        pairs, official = [], {}
        for item in getattr(self, 'marks_array', []) or []:
            item = (item or '').strip()
            if not item:
                continue
            m = re.match(r'^(\d+[a-zA-Z]?)[\s\.、：:_-]*(.+)', item)
            if m and m.group(2).strip():
                num, name = m.group(1), m.group(2).strip()
                pairs.append((num, name))
                official.setdefault(num, name)
                continue
            m = re.match(r'^([\u4e00-\u9fa5A-Za-z]{2,})[\s\(\（\[]*(\d+[a-zA-Z]?)[\s\)\）\]]*$', item)
            if m:
                pairs.append((m.group(2), m.group(1)))
                official.setdefault(m.group(2), m.group(1))
        text = getattr(self, 'all_txt', '') or ''
        wrong_nums = []
        for num, name in official.items():
            if not name or len(name) < 2:
                continue
            try:
                for m in re.finditer(re.escape(name) + r'[\(（](\d+[a-zA-Z]?)[\)）]', text):
                    found = m.group(1)
                    if found != num:
                        pairs.append((found, name))
                        wrong_nums.append((name, num, found))
                        self._add_highlight(m.start(), m.end() - m.start(), '#d9534f')
            except Exception:
                continue
        self.ckresult_txt += '\u2029=== 标号-名称对应关系检查 ===\u2029'
        pairs = list(dict.fromkeys(pairs))
        if not pairs:
            self.ckresult_txt += '未提取到可比的标号-名称对。\u2029'
            return []
        num_to_names, name_to_nums = {}, {}
        for num, name in pairs:
            num_to_names.setdefault(num, set()).add(name)
            name_to_nums.setdefault(name, set()).add(num)
        num_conflicts = {k: v for k, v in num_to_names.items() if len(v) > 1}
        name_conflicts = {k: v for k, v in name_to_nums.items() if len(v) > 1}
        for name, expect, found in wrong_nums[:20]:
            msg = '「%s」在列表中为 %s，正文中写作 %s' % (name, expect, found)
            self.ckresult_txt += '  ' + msg + '\u2029'
            self._push_issue('编号不符', name, msg, -5)
        if not num_conflicts and not name_conflicts:
            self.ckresult_txt += '未发现一个标号对应多个名称，或同一名称对应多个标号。\u2029'
            return []
        rows = []
        for num, names in sorted(num_conflicts.items()):
            msg = '标号「%s」对应多个名称：%s' % (num, '、'.join(sorted(names)))
            self.ckresult_txt += '  ' + msg + '\u2029'
            self._push_issue('标号-名称', num, msg, -5)
            rows.append((num, ' / '.join(sorted(names)), '?', '?'))
        for name, nums in sorted(name_conflicts.items()):
            msg = '名称「%s」对应多个标号：%s' % (name, '、'.join(sorted(nums)))
            self.ckresult_txt += '  ' + msg + '\u2029'
            self._push_issue('标号-名称', name, msg, -5)
            rows.append((' / '.join(sorted(nums)), name, '?', '?'))
        red, white = QColor('#d9534f'), QColor(Qt.white)
        start = self.table_marks.rowCount()
        self.table_marks.setRowCount(start + len(rows))
        for r, values in enumerate(rows, start):
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setBackground(red)
                item.setForeground(white)
                self.table_marks.setItem(r, c, item)
        return rows

    def fn_close_book(self):
        self._clear_highlights()
        self.hide()

    # ---------------- 音效开关 ----------------
    def _sync_sfx_btn(self):
        """按钮外观跟随实际开关状态（状态落盘，重启后保持）。"""
        on = sfx.enabled()
        self.btn_sfx.setChecked(on)
        self.btn_sfx.setIcon(qta.icon('fa5s.volume-up' if on
                                      else 'fa5s.volume-mute'))
        self.btn_sfx.setToolTip('按键音效：%s（点击切换）' % ('开' if on else '关'))

    def fn_toggle_sfx(self):
        on = sfx.toggle()
        self._sync_sfx_btn()
        # 开的时候立刻给一声，确认音量与扬声器正常；关的时候自然静音
        if on:
            sfx.play('click')
        try:
            self.status.showMessage('按键音效已%s' % ('开启' if on else '关闭'), 2500)
        except Exception:
            pass

    # 拖动 / 四边缩放统一由 FramelessResizableMixin 提供（与特殊字符窗口共用
    # 同一套 Windows 命中测试，且修掉了返回裸 int 会在 PyQt5 抛 TypeError 的坑）。
    # 这里只保留独有排除规则：分数盘本身可点击，不作为拖动起点。

    @staticmethod
    def _is_drag_handle(child):
        """只有空白/标签等背景区域可拖动窗口；按钮、输入、表格、分数盘等
        交互控件不作为拖动起点，避免误拖。"""
        if child is None:
            return True
        from PyQt5.QtWidgets import (QPushButton, QToolButton, QLineEdit,
                                     QComboBox, QTableWidget, QTabWidget,
                                     QAbstractSpinBox, QTextEdit, QTextBrowser,
                                     QListWidget)
        if isinstance(child, (QPushButton, QToolButton, QLineEdit, QComboBox,
                              QTableWidget, QTabWidget, QAbstractSpinBox,
                              QTextEdit, QTextBrowser, QListWidget, ScoreRing)):
            return False
        return True

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def get_same_markindex(self, mark, input_component, highlight_color):
        """临时高亮所有相同内容（ExtraSelections，不写回文档格式）。"""
        self._highlight_pattern(input_component, mark, highlight_color)

    def get_same_markindex_check(self, mark, text_component):
        self._highlight_pattern(text_component, mark, '#d9534f')

    def cell_clicked(self, item):
        row, column = item.row(), item.column()
        item0 = self.table_marks.item(row, 0)
        item1 = self.table_marks.item(row, 1)
        if not item0:
            return
        self._clear_highlights()
        select_txt = item0.text() if column == 0 else (item1.text() if item1 else item0.text())
        self.get_same_markindex(select_txt, self.active_textcomponent, self.highlight_color)

    # ---------------- 结果展示与导航 ----------------
    def on_issue_clicked(self, row, column):
        """点击问题清单：定位并高亮正文中对应的错误词句（论文「错误显示区」）。

        新规则引擎在 _locate_map 里给出的是可直接 find 的原文片段，优先于
        从说明文字里猜词；命中后高亮该词句的**全部**出现，而不只是第一处。
        """
        idx = self._row_issue_index(row)
        if not (0 <= idx < len(self._issues)):
            return
        level, cat, loc, msg, score = self._issues[idx]
        editor = self.active_textcomponent
        if editor is None:
            return
        needles = []
        exact = self._locate_map.get((cat, loc, msg))
        if exact:
            needles.append(exact.replace('\u2029', '\n'))
        needles += [n.strip() for n in
                    re.findall(r'[<「【]([^<>「」【】]{2,40})[>」】]', msg)]
        if loc and loc not in ('N/A', '全文', '-', ''):
            needles.append(loc)
        needles.append(cat)
        self._clear_highlights()
        pos = self._highlight_all(needles, self.LEVEL_COLORS.get(level, '#4a8ae8'))
        if pos >= 0:
            cur = QTextCursor(editor.document())
            cur.setPosition(pos)
            editor.setTextCursor(cur)
            editor.ensureCursorVisible()
            try:
                self.mw.activateWindow()
            except Exception:
                pass
            self.status.showMessage('> 已定位：%s'
                                    % next((n for n in needles if n), ''), 4000)
        else:
            self.status.showMessage('> 正文中未找到对应词句，请查看「完整报告」', 5000)

    def fn_export_report(self):
        """导出 txt / Markdown / CSV 三种格式（按选择或扩展名判定）。"""
        name = '校验报告_%s' % time.strftime('%Y%m%d_%H%M%S')
        path, selected = QFileDialog.getSaveFileName(
            self, '导出校验报告', name,
            'Text (*.txt);;Markdown (*.md);;CSV (*.csv)')
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        fmt = ('csv' if ext == '.csv' or 'CSV' in selected else
               'md' if ext == '.md' or 'Markdown' in selected else 'txt')
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        if fmt == 'csv':
            buf = io.StringIO()
            wr = csv.writer(buf)
            wr.writerow(['级别', '类别', '位置', '说明', '扣分'])
            for level, cat, loc, msg, sc in self._issues:
                wr.writerow([level, cat, loc, msg, sc])
            content = '\ufeff' + buf.getvalue()
        elif fmt == 'md':
            lines = ['# Fenrir 文本校验报告', '',
                     '- 生成时间：%s' % stamp,
                     '- %s' % self._doc_name,
                     '- 得分：**%d / 100**，共 %d 项发现' %
                     (self.score, len(self._issues)), '',
                     '## 问题清单', '',
                     '| 级别 | 类别 | 位置 | 说明 | 扣分 |',
                     '| --- | --- | --- | --- | --- |']
            for level, cat, loc, msg, sc in self._issues:
                safe = str(msg).replace('|', '\\|').replace('\n', ' ')
                lines.append('| %s | %s | %s | %s | %+d |' %
                             (level, cat, loc, safe, sc))
            lines += ['', '## 完整报告', '', '```text', self._last_report, '```']
            content = '\n'.join(lines)
        else:
            lines = ['Fenrir 文本校验报告',
                     '生成时间：%s' % stamp,
                     self._doc_name,
                     '得分：%d / 100，共 %d 项发现' % (self.score, len(self._issues)),
                     '', '===== 问题清单 =====']
            for level, cat, loc, msg, sc in self._issues:
                lines.append('[%s] %s | %s | %s (%+d)' % (level, cat, loc, msg, sc))
            lines += ['', '===== 完整报告 =====', self._last_report]
            content = '\n'.join(lines)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.status.showMessage('> 校验报告已导出：%s' % path, 6000)
        except Exception as exc:
            wf.notice(self, '导出失败', '无法写入报告文件。',
                      detail=str(exc), kind='warning', width=420)

    def _post_check(self):
        """把 dataframe_list 渲染为可点击的问题清单，并刷新概览。"""
        self._issues = []
        score = 100
        seen = set()
        for row in self.dataframe_list:
            try:
                sc = int(row[4])
            except Exception:
                sc = 0
            # 论文「错误显示区」最后一步：按 类别+位置+说明 剔除冗余错误信息，
            # 同一处同一个问题只保留一条，也不重复扣分。
            key = (row[1], row[2], row[3])
            if key in seen:
                continue
            seen.add(key)
            score += sc
            level = ('严重' if sc <= -10 else '警告' if sc <= -5
                     else '提示' if sc < 0 else '通过')
            self._issues.append((level, row[1], row[2], row[3], sc))
        self.score = max(0, min(100, score))
        # 表格改由 _render_issues 统一渲染（含排序与 UserRole 原始下标）
        self._render_issues()
        self._update_score_card()
        self.tab_widget_book.setTabText(0, '问题清单 (%d)' % len(self._issues))
        self.tab_widget_book.setTabText(2, '对应表 (%d)' % len(self._legend_rows))
        # 完整报告里的「得分」是旧检查项汇总时写的（get_score_from_list），
        # 不含后接入的形式缺陷扣分；这里同步成概览条的最终得分。
        self._last_report = re.sub(
            r'得分：<\d+/100>', '得分：<%d/100>' % self.score,
            self.ckresult_txt.replace('\u2029', '\n'))
        self.text_checkresult.setHtml(self._report_to_html(self._last_report))
        n_lines = len(self._last_report.splitlines())
        self.lbl_report_stat.setText('%d 行 · %d 字' %
                                     (n_lines, len(self._last_report)))
        self.lbl_legend_badge.setText('%d 条' % len(self._legend_rows))
        self.lbl_legend_status.setText(
            '来源：%s' % (self._legend_from or '未解析')
            + ('（手动编辑）' if self._legend_manual else ''))
        self._sync_check_count()
        self.refresh_doc_name()

    # ---------------- 附图说明「对应表」（论文 073/074 页） ----------------
    def _pair_seps(self):
        mode = self.combo_sep.currentText()
        if mode == '自定义':
            return self.edit_sep.text().strip() or fc.DEFAULT_PAIR_SEPS
        return fc.PAIR_SEP_PRESETS.get(mode, fc.DEFAULT_PAIR_SEPS)

    def _on_sep_mode_changed(self, text):
        self.edit_sep.setEnabled(text == '自定义')
        if hasattr(self, 'lbl_legend'):
            QTimer.singleShot(0, lambda: self._reparse_legend(force=True))

    def _collect_legend_source(self):
        """优先当前文档的「附图说明」，其次其它文档标签，最后回退左侧标记列表。

        论文的软件界面同时有权利要求书 / 说明书两个区域；Fenrir 是多个文档
        标签页，所以跨标签找附图说明才能对权利要求书做对应关系校验。
        返回 (章节文本, 来源说明, 回退解析出的行)。
        """
        eds = list(getattr(self.mw, 'text_editor_array', []) or [])
        cur = self.active_textcomponent
        ordered = ([cur] if cur is not None else []) + [e for e in eds if e is not cur]
        for ed in ordered:
            try:
                text = ed.toPlainText()
            except Exception:
                continue
            sections, _, _, heads = fc.find_sections(text)
            legend = sections.get('附图说明', '')
            if legend and re.search(r'\d', legend):
                if ed is cur:
                    label = '当前文档'
                else:
                    try:
                        label = '文档%d' % (eds.index(ed) + 1)
                    except ValueError:
                        label = '其它文档'
                return legend, label, []
        raw = ''
        try:
            raw = self.active_figmark.toPlainText()
        except Exception:
            pass
        rows = []
        for line in raw.splitlines():
            m = re.match(r'^\s*(\d{1,4}[a-zA-Z]?)\s*[、,，.．：:\-]?\s*(\S.*)$',
                         line.strip())
            if m:
                rows.append({'num': m.group(1), 'name': m.group(2).strip(),
                             'raw': line.strip()})
        return '', ('左侧标记列表' if rows else '未找到'), rows

    def _legend_rows_from_table(self):
        rows = []
        for r in range(self.table_marks.rowCount()):
            a = self.table_marks.item(r, 0)
            b = self.table_marks.item(r, 1)
            num = a.text().strip() if a else ''
            name = b.text().strip() if b else ''
            if num and name:
                rows.append({'num': num, 'name': name, 'raw': num + name})
        return rows

    def _fill_legend_table(self):
        """渲染对应表；前两列可编辑，计数列只读。"""
        rows = self._legend_rows
        text = getattr(self, 'all_txt', '') or ''
        if not text:
            try:
                text = self.active_textcomponent.toPlainText()
            except Exception:
                text = ''
        self._legend_loading = True
        try:
            self.table_marks.setRowCount(max(1, len(rows)))
            norm = text.replace('（', '(').replace('）', ')')
            for r, row in enumerate(rows):
                num, name = row['num'], row['name']
                try:
                    num_count = (len(re.findall(re.escape(name + num), text))
                                 + len(re.findall(r'\(' + re.escape(num) + r'\)', norm)))
                    name_count = len(re.findall(re.escape(name), text))
                except Exception:
                    num_count, name_count = 0, 0
                items = [QTableWidgetItem(num), QTableWidgetItem(name),
                         QTableWidgetItem(str(num_count)),
                         QTableWidgetItem(str(name_count))]
                bad = num_count != name_count
                for c, item in enumerate(items):
                    if c >= 2:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if bad and c < 2:
                        item.setBackground(QColor('#4d2a2c'))
                        item.setForeground(QColor('#ffb3ab'))
                    if num_count == 0 and c == 2:
                        item.setBackground(QColor('#4d3d22'))
                        item.setForeground(QColor('#ffd28a'))
                    self.table_marks.setItem(r, c, item)
        finally:
            self._legend_loading = False

    def _reparse_legend(self, force=False):
        """按当前分隔符重新提取对应表；不触发校验，结果等手动校验时使用。"""
        if self._legend_manual and not force:
            self._legend_rows = self._legend_rows_from_table()
            return
        src, label, fallback = self._collect_legend_source()
        if src:
            rows, warns = fc.parse_legend(src, self._pair_seps())
        else:
            rows, warns = fallback, []
            if not rows:
                warns = ['未找到「附图说明」章节，也没有左侧附图标记列表；'
                         '可点「增加」手动补录对应表条目']
        self._legend_rows = rows
        self._legend_warnings = warns
        self._legend_from = label
        self._legend_manual = False
        self._fill_legend_table()
        body = ''
        try:
            body = self.active_textcomponent.toPlainText()
        except Exception:
            pass
        gaps = fc.legend_gaps(rows, body) if rows else []
        missing = [g for g in gaps if g.category == '对应表遗漏']
        hint = '对应表 %d 条 · 来源：%s' % (len(rows), label)
        if missing:
            hint += ' · 附图说明可能遗漏 %d 个编号（%s）' % (
                len(missing), '、'.join(m.message[-3:].strip() for m in missing[:3]))
        if warns:
            hint += ' · ' + warns[0][:40]
        self.lbl_legend.setText(hint)
        self.lbl_legend.setToolTip('\n'.join(warns) if warns else hint)
        # 对应表变化后不自动重跑校验：结果在下次点击分数盘时按新表计算。

    def _legend_add_row(self):
        r = self.table_marks.rowCount()
        if self._legend_rows:
            self.table_marks.insertRow(r)
        self.table_marks.setItem(r, 0, QTableWidgetItem(''))
        self.table_marks.setItem(r, 1, QTableWidgetItem(''))
        self.table_marks.setCurrentCell(r, 0)
        self.table_marks.editItem(self.table_marks.item(r, 0))
        self._legend_manual = True

    def _legend_del_row(self):
        r = self.table_marks.currentRow()
        if r < 0:
            return
        self.table_marks.removeRow(r)
        self._legend_rows = self._legend_rows_from_table()
        self._legend_manual = True

    def _on_legend_item_changed(self, item):
        if self._legend_loading or item.column() not in (0, 1):
            return
        self._legend_rows = self._legend_rows_from_table()
        self._legend_manual = True
        # 只记录手动修改，不自动重跑校验；结果在下次点击分数盘时刷新。

    def _doc_title(self):
        """取文档首行作为发明名称（权利要求书首行很长时不算名称）。"""
        try:
            first = self.active_textcomponent.toPlainText().strip().splitlines()[0]
        except Exception:
            return ''
        first = re.sub(r'^\d+\s*[.、．]\s*', '', first).strip()
        if not first or len(first) > 40 or '技术领域' in first:
            return ''
        # 权利要求书在前时首行是权利要求正文（可能带「权利要求书」标题或
        # 含「其特征在于」），不是发明名称，不参与主题名称一致性比对
        if '权利要求' in first or '其特征' in first:
            return ''
        return self._norm_title(first)

    @staticmethod
    def _norm_title(s):
        """主题名称比对前的规范化：去段号 [0001]、空白与「一种」前缀。"""
        s = re.sub(r'\[\d{3,5}\]', '', s or '')
        s = s.replace('一种', '')
        return re.sub(r'\s', '', s)

    @staticmethod
    def _canonical_heading(line):
        """段落是说明书小标题（含装饰/别名/组合写法）时返回标准小标题。

        「【发明内容】」「（三）发明内容：」「发明内容、实用新型内容」
        「实用新型内容」等统一归一到标准名（实用新型内容 → 发明内容），
        与规则引擎 find_sections 的识别口径一致；非标题返回 ''。
        """
        try:
            name = fc._canon_section(line)
        except Exception:
            return ''
        return name or ''

    def _run_formal_checks(self):
        """接入论文形式缺陷规则，写入问题清单与精确定位映射。"""
        if not self.check_formal.isChecked():
            return
        try:
            text = self.active_textcomponent.toPlainText()
        except Exception:
            return
        if not text.strip():
            return
        issues = fc.analyze(text, self._legend_rows, self._pair_seps(),
                            self._doc_title())
        for w in self._legend_warnings:
            issues.append(fc.Issue('对应表', '附图说明', w, 0, '附图说明'))
        # 新旧规则在同类同位置上会各报一条：撤掉旧校验器的笼统条目，
        # 保留规则引擎的精确描述。先一次性算出旧条目里要撤的 (类别, 位置)，
        # 再整体追加新条目——逐条替换会把上一条同位置的新结果也删掉。
        overlap = {'标点', '划界词', '序号', '不确定用语', '主题名称',
                   '引用基础', '多引多'}
        replaced = {(it.category, it.location) for it in issues
                    if it.category in overlap}
        legacy = [r for r in self.dataframe_list
                  if (r[1], r[2]) not in replaced]
        for it in issues:
            legacy.append(['', it.category, it.location, it.message,
                           str(it.score)])
            self._locate_map[(it.category, it.location, it.message)] = it.locate
            self.ckresult_txt += '\u2029[形式缺陷·%s] %s | %s\u2029' % (
                it.category, it.location, it.message)
        self.dataframe_list = legacy

    def _highlight_all(self, needles, color):
        """高亮某个词句在正文里的全部出现，返回首个命中位置。"""
        ed = self.active_textcomponent
        if ed is None:
            return -1
        text = ed.toPlainText()
        selections, first = [], -1
        for needle in needles:
            if not needle:
                continue
            try:
                hits = list(re.finditer(re.escape(needle), text))[:400]
            except Exception:
                continue
            if not hits:
                continue
            first = hits[0].start()
            for m in hits:
                cur = QTextCursor(ed.document())
                cur.setPosition(m.start())
                cur.setPosition(m.end(), QTextCursor.KeepAnchor)
                sel = QTextEdit.ExtraSelection()
                sel.cursor = cur
                sel.format.setBackground(QColor(color))
                sel.format.setForeground(QColor('#ffffff'))
                selections.append(sel)
            break
        ed.setExtraSelections(selections)
        self._extra = list(selections)
        return first

    def submit_check_main(self):
        """执行一轮完整校验。任何单项异常都记录为提示，不中断整轮检查。"""
        # AI 请求在后台线程执行、主线程用局部事件循环等待；等待期间不允许重入，
        # 否则两轮校验会互相覆盖问题清单与高亮。
        if getattr(self, '_ai_running', False):
            self.status.showMessage('AI 内容校验进行中，请稍候', 3000)
            return
        # 文本框没有有效文本时直接回待校验态：即使左侧附图标记列表还有内容，
        # 也不能对空文档跑检查（否则会误报一堆「标记未用 -5」）。
        ed = self.active_textcomponent
        if ed is None or not ed.toPlainText().strip():
            self.reset_state()
            self.lbl_summary.setText('文本框为空 — 请先输入文本再校验')
            self.status.showMessage('文本框为空，没有可校验的内容', 4000)
            self.status.set_accent()
            sfx.play('warn')
            return
        # 分数盘是自绘控件、不在按钮音效的覆盖面里，这里补一声，保证从
        # 任何入口（分数盘 / 快捷键 / 外部调用）触发校验都有按下的反馈。
        sfx.play('click')
        self.textsplit_array = []
        self.dataframe_list = []
        self.error_array = []
        self.ckresult_txt = ''
        self._locate_map = {}
        self._fix_map = {}
        self._ai_elapsed = None
        # 每轮校验前刷新「附图说明 → 编号/技术特征」对应表；用户手动改过的
        # 对应表优先保留，不被自动解析覆盖（论文图 4 的增改删分支）。
        if self._legend_manual:
            self._legend_rows = self._legend_rows_from_table()
        else:
            self._reparse_legend()
        self.splittemp_array = ['技术领域', '背景技术', '发明内容', '实用新型内容',
                                '附图说明', '具体实施方式']
        self.paras_array = dict.fromkeys(
            ['专利名称', '技术领域', '背景技术', '发明内容', '实用新型内容',
             '附图说明', '具体实施方式'], '')
        self.one_cite_muti_dic = {}
        self.one_cite_one_dic = {}
        self.claim_array = []
        self.claim_dic = {}
        self.title = ''
        self.claim_max = 1
        self.claim_check_flag = True
        self.des_check_flag = True
        self.txt_type = 'other'
        self.marks_dic = {}
        self.parts_dic = {}
        self.fig_dic = {}
        self.des_part_count = 0

        self._clear_highlights()
        self.text_checkresult.clear()
        self.table_issues.setRowCount(0)
        self.table_marks.setRowCount(0)
        self.refresh_doc_name()
        self.status.showMessage('文本校验中...')
        self.status.set_accent('#cc6633')

        self.all_txt = (self.active_textcomponent.toPlainText()
                        .replace(' ', '').replace('\r', '\u2029')
                        .replace('\t', '\u2029').replace('\n', '\u2029')
                        .replace('\u2029\u2029', '\u2029').strip('\u2029'))
        self.para_array = self.all_txt.split('\u2029')
        # 小标题容错归一：「【发明内容】」「（三）发明内容：」「发明内容、
        # 实用新型内容」等写法统一替换为标准小标题，后续分段与名称比对
        # 都基于标准名，不再因为装饰写法而漏识别章节。
        for _i, _para in enumerate(self.para_array):
            _name = self._canonical_heading(_para)
            if _name:
                self.para_array[_i] = _name
        self.all_txt = '\u2029'.join(self.para_array)
        marks_raw = self.active_figmark.toPlainText().replace('\n', '\u2029')
        self.marks_array = [x for x in marks_raw.strip('\u2029').split('\u2029') if x.strip()]
        try:
            self.figmarks_array = split_marks('\u2029'.join(self.marks_array))
        except Exception:
            self.figmarks_array = list(self.marks_array)

        if not self.marks_array:
            self.ckresult_txt = ('未识别到附图标记：与标记相关的检查已跳过；'
                                 '错别字、语法与 AI 内容校验仍照常执行。')
        else:
            while '\u2029\u2029' in self.all_txt:
                self.all_txt = self.all_txt.replace('\u2029\u2029', '\u2029')
            steps = [
                ('文档类型与主体检查', self._check_document),
                ('附图标记一致性', self.marks_consistent),
                ('标记对照表', self.marks_to_table),
            ]
            if self.check_terms.isChecked():
                steps.append(('术语一致性', lambda: self.check_terms_consistency(True)))
            if self.check_vague.isChecked():
                steps.append(('空泛词', lambda: self.check_vague_words(True)))
            if self.check_markname.isChecked():
                steps.append(('标号-名称', self.check_mark_name_consistency))
            for label, func in steps:
                try:
                    func()
                except Exception as exc:
                    self.ckresult_txt += '\u2029[%s] 未完成：%s\u2029' % (label, exc)
                    self._push_issue('系统', label, '%s 未完成：%s' % (label, exc), 0)
            try:
                self.get_score_from_list()
                self.add_num_to_data()
            except Exception as exc:
                self.ckresult_txt += '\u2029[汇总] %s\u2029' % exc

        # 错别字 / 语法标点检查不依赖附图标记，未填标记时也可执行；
        # 扣分经 _push_issue 汇总到 _post_check 的评分里。
        for label, flag, func in (
                ('错别字', self.check_typo, self.check_typos),
                ('语法标点', self.check_grammar, self.check_grammar_rules)):
            if not flag.isChecked():
                continue
            try:
                func()
            except Exception as exc:
                self.ckresult_txt += '\u2029[%s] 未完成：%s\u2029' % (label, exc)
                self._push_issue('系统', label, '%s 未完成：%s' % (label, exc), 0)

        # 论文形式缺陷规则：与原有检查项并列，结果进同一张问题清单
        try:
            self._run_formal_checks()
        except Exception as exc:
            self.ckresult_txt += '\u2029[形式缺陷] 未完成：%s\u2029' % exc
        # AI 内容校验（火山方舟）：结果并入同一张问题清单，失败时静默降级
        if self.check_ai.isChecked():
            try:
                self.check_ai_content()
            except Exception as exc:
                self.ckresult_txt += '\u2029[AI 内容校验] 未完成：%s\u2029' % exc
                self._push_issue('系统', 'AI 内容校验',
                                 'AI 内容校验未完成：%s' % exc, 0)
        else:
            # 以前未勾选时报告里完全没有 AI 段落，用户会以为模型查过却没找到错。
            self.ckresult_txt += ('\u2029=== AI 内容校验（火山方舟） ===\u2029'
                                  '未勾选「AI 内容校验」，本轮未调用模型；'
                                  '在检查项中勾选后重新校验即可。\u2029')
        self._post_check()
        _ai_tail = (' · AI %.1fs' % self._ai_elapsed) if self._ai_elapsed else ''
        self.status.showMessage('校验完成：%d 项发现 · 得分 %d/100%s'
                                % (len(self._issues), self.score, _ai_tail), 6000)
        self.status.set_accent()
        # 结果提示音：单响=通过，双响=一般问题，三响低沉=有严重问题。
        # 都是短促按键声，不是旋律，且只在不看屏幕也能判断结果的场景下有用。
        sfx.play_for_issues(self._issues, self.score)

    def _check_document(self):
        """按识别出的文档类型分派到说明书 / 权利要求书检查。"""
        self.txt_type = self.is_description() or 'other'
        if self.txt_type == 'claim':
            self.check_claim()
        elif self.txt_type == 'description':
            self.check_description()
        else:
            self.check_text_ckmarks_unused()

    def marks_to_table(self):
        # 对应表页已升级为「附图说明自动解析 + 可编辑」；有解析结果或用户
        # 手动编辑过时按新表重算计数，避免旧逻辑用 fig_dic 覆盖对应表。
        if self._legend_rows or self._legend_manual:
            self._fill_legend_table()
            return
        # 旧版固定 300 行（绝大多数是空行），改为按实际标记数动态生成
        self.table_marks.clearContents()
        self.table_marks.setRowCount(max(1, len(self.fig_dic)))
        for index,num in enumerate(self.fig_dic):
            mark = self.fig_dic[num]
            try:
                mark_count = re.findall(re.escape(mark), self.all_txt)
                num_count = (re.findall(re.escape(mark + num), self.all_txt)
                             + re.findall(r'\(' + re.escape(num) + r'\)',
                                          self.all_txt.replace('（', '(').replace('）', ')')))
            except Exception:
                mark_count, num_count = [], []
            item_1 = QTableWidgetItem(num)
            item_2 = QTableWidgetItem(mark)
            item_3 = QTableWidgetItem(str(len(num_count)))
            item_4 = QTableWidgetItem(str(len(mark_count)))
            # 语义色与深色主题调和：不一致=暗红底浅红字，计数为 0=暗橙底琥珀字
            if len(mark_count) != len(num_count):
                bad_bg, bad_fg = QColor('#4d2a2c'), QColor('#ffb3ab')
                item_1.setBackground(bad_bg); item_1.setForeground(bad_fg)
                item_2.setBackground(bad_bg); item_2.setForeground(bad_fg)
            if len(num_count) == 0:
                item_3.setBackground(QColor('#4d3d22'))
                item_3.setForeground(QColor('#ffd28a'))
            if len(mark_count) == 0:
                item_4.setBackground(QColor('#4d3d22'))
                item_4.setForeground(QColor('#ffd28a'))
            self.table_marks.setItem(index, 0, item_1)
            self.table_marks.setItem(index, 1, item_2)
            self.table_marks.setItem(index, 2, item_3)
            self.table_marks.setItem(index, 3, item_4)
    ''' 技术特征 & 附图编号一致性'''
    def marks_consistent(self):
        self.ckresult_txt += f'\u2029<附图标记一致性>\u2029'
        if not self.marks_array:
            return
        # 旧版硬取 marks_array[2][0] 且 split(' ')[1]，标记少于 3 条或格式
        # 略有差异就会 IndexError 中断整轮校验；改为容错解析。
        first = next((x.strip() for x in self.marks_array if x and x.strip()), '')
        starts_with_number = bool(first) and first[0] in '1234567890'
        if starts_with_number:
            for item in self.marks_array:
                parts = item.strip().split()
                if len(parts) >= 2:
                    self.marks_dic[parts[1]] = parts[0]  # {'机架': '1'}
        # 查找附图标记
        for mark in self.marks_dic:
            for num in [rf'\d{4}[a-z]',rf'\d{3}[a-z]',rf'\d{4}',rf'\d{2}[a-z]',rf'\d{3}',rf'\d{2}',rf'\d[a-z]',rf'\d{1}',rf'[a-z]']:
                find_txt = []
                if self.txt_type == 'claim': # 被核对文本为权利要求书   仅含独权？
                    find_txt = re.findall(f'{mark}\\({num}\\)',self.all_txt.replace('（','(').replace('）',')'))
                elif self.txt_type == 'other':  # 被核对文本为其他
                    find_txt = re.findall(f'{mark}{num}',self.all_txt)
                find_txt = list(set(find_txt))
                if find_txt:
                    try:
                        find_txt.remove(f'{mark}{self.marks_dic[mark]}')
                    except:
                        try:
                            find_txt.remove(f'{mark}({self.marks_dic[mark]})')
                        except Exception as e:
                            print('Error Check_01',e)
                    self.error_array += find_txt
                    break
        # 不含数字编号的关键词式附图标记
        if not starts_with_number:
            for char in self.marks_array:
                # 排除字符长度为1的关键词
                if len(char) <= 2:
                    continue
                re_search_array = []
                for i in range(len(char)):
                    if i == 0:
                        item = '.' + char[1:]
                    elif i == len(char) - 1:
                        item = char[0:i] + '.'
                    else:
                        item = char[0:i] + '.' + char[i:]
                    re_search_array.append(item)
                find_char = []
                for pat in re_search_array:
                    find_char += re.findall(pat, self.all_txt)
                # 剔除标点符号与原文
                find_char = [
                    item.strip('。,、;:() ') for item in find_char
                    if len(item.strip('。,、;:() ')) == len(char) and item.strip('。,、;:() ') != char
                ]
                find_char = refine_array(find_char, 'set')
                self.error_array += find_char
        # 高亮显示错误文本、标号不一致
        tag_para_index = 0
        if self.error_array:
            for para in self.para_array:
                tag_para_index += 1
                for error in self.error_array:
                    if error in para:
                        # 判定为权利要求书
                        if '权利要求' in self.all_txt and '其特征' in self.all_txt:
                            for claim_index,claim in enumerate(self.claim_array): # 判断错误位于权几
                                if error in claim:
                                    self.ckresult_txt += f'权{claim_index + 1},{error}与附图标记不一致\u2029'
                                    self.dataframe_list.append(['','标记不一致',f'权{claim_index + 1}',f'{error}与附图标记不一致','-5'])
                        # 判定为说明书
                        else:
                            para_index,sen_index = self.get_para_sen_index(error,para)
                            self.ckresult_txt += f'第{para_index}段，第[{sen_index}]句,<{error}>与附图标记不一致\u2029'
                            self.dataframe_list.append(['','标记不一致',f'第{para_index}段，第[{sen_index}]句,',f'{error}与附图标记不一致','-5'])
                        self.get_same_markindex_check(error,self.active_textcomponent)

    def is_description(self):  # 判断是否为说明书
        for para in self.para_array:
            if not para:
                continue
            elif para in self.splittemp_array:
                self.textsplit_array.append(para)
                self.des_part_count += 1
        if self.des_part_count < 4:
            if '实施例' in self.all_txt:
                self.ckresult_txt += '=======文本为<说明书>=======\u2029'
                self.ckresult_txt += '请以技术领域、背景技术、发明内容/实用新型内容、附图说明（可不填）、具体实施方式划分说明书\u2029'
                return 'short_for_description'
            elif ('1.一种' in self.all_txt.replace(' ','') or '1、一种' in self.all_txt.replace(' ','') or '权利要求' in self.all_txt) and '实施例' not in self.all_txt:
                self.ckresult_txt += '=======文本为<权利要求书>=======\u2029'
                return 'claim'
        elif self.des_part_count >= 4:
            # 说明书后附权利要求是很常见的排版；只要识别出 4 个以上标准章节，
            # 就按说明书做完整检查，不再因为出现「1.一种」而误判为其他文本。
            self.ckresult_txt += '=======文本为<说明书>=======\u2029'
            return 'description'
        # 无分段、又不含权要特征时旧版返回 None，后续分支全部落空；统一按其他文本处理
        self.ckresult_txt += '=======文本为<其他文本>=======\u2029'
        return 'other'

    def check_text_ckmarks_unused(self): # 校验未被使用的附图标记
        self.ckresult_txt += '\u2029<未使用的附图标记>\u2029'
        if not self.marks_array:
            self.ckresult_txt += '无附图标记\u2029'
            return
        for _ in self.figmarks_array:
            try:
                fig_num, fig_text = judge_mark(_)
                self.fig_dic[fig_num] = fig_text
            except Exception:
                continue
        used = 0
        for _ in self.fig_dic:
            item = self.fig_dic[_]
            if item and item not in self.all_txt:
                self.ckresult_txt += f'标记<{_} {item}>未使用\u2029'
                self.dataframe_list.append(['', '标记未用', 'N/A',
                                            f'标记<{_} {item}>未使用', '-5'])
            else:
                used += 1
        if used:
            self.ckresult_txt += '已使用 %d 个标记。\u2029' % used
    def add_num_to_data(self): # 更新 data_list序号
        for index in range(0,len(self.dataframe_list)):
            self.dataframe_list[index][0] = index + 1
    def get_score_from_list(self): # 统计同分数
        total_score = 100
        for data_array in self.dataframe_list:
            try:
                total_score += int(data_array[4])
            except Exception:
                continue
        total_score = max(0, min(100, total_score))
        self.score = total_score
        self.ckresult_txt += '\u2029<结果>\u2029得分：<%d/100>\u2029' % total_score
        if total_score <= 60:
            self.ckresult_txt += '\u2029技术方案细节过于单薄，请进一步完善'

    def get_para_sen_index(self,error,para_txt):  # 判断错误位于说明书的第几段第几句
        # 判断段落号
        para_index = re.findall(rf'\\[\d\d\d\d\\]',para_txt)
        if para_index:
            para_index = para_index[0]
        else:
            para_index = '[N/A]'
        sen_index = 0
        # 判断 句子号
        for sen in para_txt.split('。'):
            sen_index += 1
            if error in sen:
                return para_index,sen_index
        return para_index,'N/A'
    def get_des_detail(self):
        self.paras_array['专利名称'] = self.title
        # 获取说明书各部分
        if len(self.textsplit_array) <= 1:
            self.textsplit_array.append('')
        for i in range(0,len(self.textsplit_array)):
            index_word = self.textsplit_array[i]
            if not index_word:
                continue
            if i == 0:
                index_word_1 = self.textsplit_array[i]
                index_word_2 = self.textsplit_array[i + 1]
                find_text = re.findall(f"{index_word_1}\n(.*)\n{index_word_2}",self.all_txt,re.S)
                if find_text:
                    self.paras_array[index_word] = find_text[0]
            elif i == (len(self.textsplit_array) - 1):
                find_text = re.findall(f"{index_word}\n(.*)",self.all_txt,re.S)
                if find_text:
                    self.paras_array[index_word] = find_text[0]
            else:
                index_word_1 = self.textsplit_array[i]
                index_word_2 = self.textsplit_array[i + 1]
                find_text = re.findall(f"{index_word_1}\n(.*)\n{index_word_2}",self.all_txt,re.S)
                if find_text:
                    self.paras_array[index_word_1] = find_text[0]
    def check_description(self):
        self.des_check_flag = True
        if self.all_txt[0:4] != '技术领域':
            self.title = self.para_array[0]
            # 权利要求书在前时首行是「权利要求书」标题或权利要求正文；
            # 此时发明名称是第一个小标题前面紧邻的那一行
            if (len(self.title) > 40 or '权利要求' in self.title
                    or '其特征' in self.title):
                self.title = ''
                for _i, _p in enumerate(self.para_array):
                    if _p in self.splittemp_array and _i > 0:
                        _cand = self.para_array[_i - 1]
                        if (0 < len(_cand) <= 40 and '权利要求' not in _cand
                                and '其特征' not in _cand
                                and not re.match(r'^\d+\s*[.、．]', _cand)):
                            self.title = _cand
                        break
        self.all_txt = self.all_txt.replace('\u2029','\n')
        self.get_des_detail() # 获取 self.paras_array 的各元素
        for para_title,des_part in self.paras_array.items():
            if para_title == '发明内容' or para_title == '实用新型内容' or para_title == '附图说明':
                continue
            elif not des_part:
                self.ckresult_txt += f'<{para_title}>未检测到{para_title}\u2029'
                self.dataframe_list.append(['','形式缺陷',para_title,f'缺少{para_title}','-5'])
                self.des_check_flag = False
        if not self.paras_array['发明内容'] and not self.paras_array['实用新型内容']:
            self.ckresult_txt += '<发明内容>未检测到发明内容/实用新型内容\u2029'
            self.dataframe_list.append(['','形式缺陷','发明内容','缺少','-5'])
            self.des_check_flag = False
        if not self.des_check_flag:
            self.ckresult_txt += f'> 缺少说明书主体内容，请修改后重试\u2029> 请以“技术领域、背景技术、发明内容/实用新型内容、附图说明、具体实施方式”分段，避免导致无法识别的问题\u2029'
            return
        for para_title,des_part in self.paras_array.items(): # 分段名称，具体内容
            if para_title == '专利名称':
                if len(self.title) > 25:
                    self.ckresult_txt += '<专利名称>应少于25个字\u2029'
                    self.dataframe_list.append(['','形式缺陷','专利名称','应少于25个字','-2'])
                if '新型' in self.title:
                    self.ckresult_txt += '<专利名称>“新型”使用不当\u2029'
                    self.dataframe_list.append(['','形式缺陷','专利名称','“新型”使用不当','-2'])
            elif para_title == '技术领域':
                if len(des_part) < 20:
                    self.ckresult_txt += '<技术领域>内容过于简单\u2029'
                    self.dataframe_list.append(['','形式缺陷','技术领域','内容过于简单','-5'])
                if self.title and self._norm_title(
                        self.paras_array['专利名称']) not in self._norm_title(des_part):
                    self.ckresult_txt += '<技术领域>主题名称不一致\u2029'
                    self.dataframe_list.append(['','形式缺陷','技术领域','主题名称不一致','-2'])
            elif para_title == '背景技术':
                if '公开号' not in des_part and '公布号' not in des_part and '申请号' not in des_part and '实用新型' not in des_part and '发明' not in des_part and '公开' not in des_part:
                    self.ckresult_txt += '<背景技术>未引证现有技术\u2029'
                    self.dataframe_list.append(['','形式缺陷','背景技术','未引证现有技术','-5'])
                if '问题' not in des_part and '缺陷' not in des_part:
                    self.ckresult_txt += '<背景技术>未阐述现有技术存在的技术问题\u2029'
                    self.dataframe_list.append(['','形式缺陷','背景技术','未阐述现有技术存在的技术问题','-10'])
                if len(re.split('\n|\u2029',des_part)) <= 2 and len(des_part) < 300:
                    self.ckresult_txt += '<背景技术>内容过于简单\u2029'
                    self.dataframe_list.append(['','形式缺陷','背景技术','内容过于简单','-5'])
            elif para_title == '发明内容':
                if not des_part:
                    des_part = self.paras_array['实用新型内容']
                des_part_array = re.split('\n|\u2029',des_part) # 发明目的 发明内容第一段
                des_part_array = refine_array(des_part_array,'')
                destination_txt = des_part_array[0] if des_part_array else ''
                # 匹配发明内容阐述的技术问题概述
                find_problem_txt = []
                for ser in ['解决.*?问题', '解决.*?缺陷','解决.*?难题']:
                    find_problem_txt = re.findall(ser, destination_txt)
                    if len(find_problem_txt) >= 1:
                        break
                judge_lengh = (len(destination_txt) - len(self.paras_array['专利名称']))
                if find_problem_txt == [] and judge_lengh < 10:
                    self.ckresult_txt += '<发明内容>首段未撰写技术问题概述\u2029'
                    self.dataframe_list.append(['','形式缺陷','发明内容','首段未撰写技术问题概述','-5'])
                # 匹配发明内容阐述的技术效果概述
                find_effect_txt = []
                for ser in ['具有.*?优点', '具有.*?特点']:
                    find_effect_txt = re.findall(ser, destination_txt)
                    if len(find_effect_txt) >= 1:
                        find_effect_txt = refine_txt(find_effect_txt[0], '具有 优点 特点 等'.split())
                        abs_effect_array = find_effect_txt.split('，')
                        if len(abs_effect_array) <= 1:
                            abs_effect_array = find_effect_txt.split('、')
                        if len(abs_effect_array) > 1:
                            for _ in abs_effect_array:
                                if 2 <= len(_) <= 6 and not _.endswith('的') and _ not in des_part:
                                    para_index,sen_index = self.get_para_sen_index(_,destination_txt)
                                    self.ckresult_txt += f'<有益效果>第{para_index}段缺少与<{_}>对应的内容\u2029'
                                    self.dataframe_list.append(['','形式缺陷','有益效果',f'第{para_index}段缺少与<{_}>对应的内容','-2'])
                            break
                if find_effect_txt == [] and judge_lengh < 10:
                    self.ckresult_txt += '<发明内容>首段未撰写技术效果概述\u2029'
                    self.dataframe_list.append(['','形式缺陷','有益效果',f'首段未撰写技术效果概述','-5'])
                # 匹配有益效果详述 与 背景技术的技术问题
                for ser in ['产生.*?问题', '存在.*?问题', '导致.*?问题', '造成.*?问题', '产生.*?缺陷', '存在.*?缺陷', '导致.*?缺陷', '造成.*?缺陷', '产生.*?缺点', '存在.*?缺点','导致.*?缺点', '造成.*?缺点','解决.*?难题','解决.*?问题']:
                    find_problem_txt = re.findall(ser, self.paras_array['背景技术'])
                    if len(find_problem_txt) >= 1:
                        find_problem_txt = refine_txt(find_problem_txt[0], '产生 存在 造成 导致 缺点 缺陷 问题 解决 等'.split())
                        sub_problem_array = find_problem_txt.split('，')
                        if len(sub_problem_array) <= 1:
                            sub_problem_array = find_problem_txt.split('、')
                        if len(sub_problem_array) > 1:
                            for _ in sub_problem_array:
                                if 2 <= len(_) <= 6 and not _.endswith('的') and _ not in des_part:
                                    para_index,sen_index = self.get_para_sen_index(_,destination_txt)
                                    self.ckresult_txt += f'<技术问题>第{para_index}段缺少与<{_}>对应的内容\u2029'
                                    self.dataframe_list.append(['','形式缺陷','技术问题',f'第{para_index}段缺少与<{_}>对应的内容','-2'])
                        break
                if self.title and self._norm_title(
                        self.paras_array['专利名称']) not in self._norm_title(des_part):
                    self.ckresult_txt += '<发明内容>主题名称不一致\u2029'
                    self.dataframe_list.append(['','形式缺陷','发明内容','主题名称不一致','-2'])
            elif para_title == '具体实施方式': # 未将发明内容与具体实施方式比对
                # 校验附图说明中的附图数量与具体实施方式中是否一致，如果无附图说明则PASS
                if self.paras_array['附图说明']:
                    # 原来 range(50,1,-1) 不含 1：只有「图1」的说明书会一路
                    # 落到 fig_max=2，然后因为具体实施方式里没有「图2」而误报。
                    for fig_max in range(50,0,-1):
                        if f'图{fig_max}' in self.paras_array['附图说明']:
                            break
                    if f'图{fig_max}' not in des_part and f'~{fig_max}' not in des_part:
                        self.ckresult_txt += '<具体实施方式>实施例附图与附图说明不一致\u2029'
                        self.dataframe_list.append(['','形式缺陷','具体实施方式',f'实施例附图与附图说明不一致','-2'])
                embo_paras = para_refine(des_part)
                for ser in ['\u2029实例', '\u2029实施例','end']:
                    if ser in des_part:
                        embo_labels = re.findall(ser, des_part)
                        if len(embo_labels) <= 1 or ser == 'end':
                            self.ckresult_txt += '<具体实施方式>实施例数量过少\u2029'
                            self.dataframe_list.append(['','形式缺陷','具体实施方式',f'实施例数量过少','-10'])
                            if len(embo_paras) < 4 and len(des_part) <= 400:
                                self.ckresult_txt += '<具体实施方式>实施例1内容过于简单\u2029'
                                self.dataframe_list.append(['','形式缺陷','具体实施方式',f'实施例1内容过于简单','-10'])
                            if '工作原理' not in des_part and '原理' not in des_part:
                                self.ckresult_txt += '<具体实施方式>未阐述工作原理\u2029'
                                self.dataframe_list.append(['','形式缺陷','具体实施方式',f'未阐述工作原理','-5'])
                            break
                        elif len(embo_labels) >= 2:
                            embo_array = des_part.split(f'\u2029{ser}')
                            for _ in embo_array:
                                if len(_) < 300:
                                    embo_index = embo_array.index(_) + 1
                                    self.ckresult_txt += f'<具体实施方式><实施例{embo_index}>内容过于简单\u2029'
                                    self.dataframe_list.append(['','形式缺陷',f'实施例{embo_index}',f'内容过于简单','-5'])
                            break
        # 校验未使用的附图标记
        self.check_text_ckmarks_unused()
    ''' 校验权利要求 '''                
    def check_preliminary(self): #校验末尾'句号'
        # 权利要求书在前、说明书在后时只取权利要求书区域切分：否则最后一条
        # 权利要求会吞并说明书正文，谎报「含有多个"。"」「缺少划界词」。
        region = fc.claims_region(self.all_txt.replace('\u2029', '\n'))
        region_txt = '\u2029' + region.replace('\n', '\u2029').replace(' ', '') + '\u2029'
        split_array = [f'\u2029{i}\\.' for i in range(50,0,-1)] + [f'\u2029{i}、' for i in range(50,0,-1)]# +  [f'\u2029{i}' for i in range(50,0,-1)]
        self.claim_array = re.split('|'.join(split_array),region_txt)
        while '' in self.claim_array:
            try:
                self.claim_array.remove('')
            except:
                pass
        self.claim_max = len(self.claim_array)
        self.ckresult_txt += f'\u2029<句号、划界词、权要序号>\u2029\u2029<共{self.claim_max}项权利要求>\u2029'
        self.claim_check_flag = True
        # 检查句号、划界词
        for claim_index,claim in enumerate(self.claim_array):
            claim_index += 1
            claim = claim.replace(' ','')
            if len(re.findall(r'。',claim)) >= 2: # 校验多个句号
                self.ckresult_txt += f'权利要求<{claim_index}>含有多个“。”\u2029'
                self.dataframe_list.append(['','标点',f'权{claim_index}','含有多个"。"','-10'])
                self.claim_check_flag = False 
            elif '。' not in claim: # 校验缺少句号
                self.ckresult_txt += f'权利要求<{claim_index}>缺少“。”\u2029'
                self.dataframe_list.append(['','标点',f'权{claim_index}','缺少"。"','-10'])
                self.claim_check_flag = False 
            if '其特征' not in claim: # 校验划界词
                self.ckresult_txt += f'权利要求<{claim_index}>缺少划界词\u2029'
                self.dataframe_list.append(['','划界词',f'权{claim_index}','缺少划界词','-10'])
                self.claim_check_flag = False 
        # 序号检查改为按实际切分出的编号判断是否 1..N 连续。
        # 旧写法 `f'{i}、{claim}' in all_txt or f'{i}.{claim}' not in all_txt`
        # 在「1、」中文顿号排版下恒为真，会把 claim_check_flag 置 False，
        # 于是 check_claim() 提前 return，后面 5 项权利要求检查全部不执行。
        nums = [c['index'] for c in fc.split_claims(
            fc.claims_region(self.all_txt.replace('\u2029', '\n')))]
        if nums and nums != list(range(1, len(nums) + 1)):
            self.ckresult_txt += '权利要求序号不连续：%s\u2029' % nums
            self.dataframe_list.append(['', '序号', '全文', '权利要求序号不连续', '-5'])
        # 生成claim_dic{[1：全文，前序，特征]，[2:全文，前序，特征]}
        for index,claim in enumerate(self.claim_array):
            index += 1
            self.claim_dic[index] = [claim.strip('\u2029\n '),'',''] # claim全文，前序部分，特征部分
        return self.claim_check_flag
    def check_uncertain_words(self):# 校验不确定用语
        self.ckresult_txt += f'\u2029<主题词、不确定用语>\u2029'
        # 旧词表含「厚/薄/强/弱/等/可以/约」等单字，专利文书里几乎必然出现，
        # 会造成大量假阳性；主题名称也不再用「标题是否出现在整条权要里」判断
        # （旧写法把「1.一种XXX」当标题，导致每一项都报主题名称不一致）。
        # 两项都由 formal_checks 的规则引擎给出更精确的结果。
        for claim_index,claim in enumerate(self.claim_array):
            claim_index += 1
            claim = claim.replace(' ','')
            for word in fc.UNCERTAIN_WORDS:
                if word in claim:
                    self.ckresult_txt += f'权利要求<{claim_index}>存在不确定用语“{word}”\u2029'
                    self.dataframe_list.append(['','不确定用语',f'权{claim_index}','含不确定用语“%s”' % word,'-5'])
                    break
    def get_fore_char(self): # 获取前序部分、特征部分
        for index,claim in self.claim_dic.items():
            find_txt = []
            for _ in ['权力要求书(.*)其特征','权利要求书(.*)其特征','权力要求(.*)其特征','权利要求(.*)其特征','1\\.(.*)其特征','、(.*)其特征']:# 获取前序部分
                try:
                    find_txt = re.findall(_,claim[0])
                    if find_txt:
                        claim[1] = find_txt[0]
                        break
                except:
                    pass
            for _ in ['其特征在于(.*)','其特征是(.*)']: # 获取全部特征部分
                try:
                    find_txt = re.findall(_,claim[0])
                    if find_txt:
                        claim[2] = find_txt[0]
                        break
                except:
                    pass
    def get_one_cite_multi_claim(self):
        for index,claim in self.claim_dic.items():
            forepart = claim[1]
            cited_num = []
            if '或' in forepart or '至' in forepart or '~' in forepart or '-' in forepart or '任意项' in forepart or '任一项' in forepart:
                for claim_num in range(50,0,-1):
                    if str(claim_num) in forepart:
                        cited_num.append(claim_num)
                        forepart = forepart.replace(str(claim_num),'')
                self.one_cite_muti_dic[index] = cited_num
    def get_one_cite_one_claim(self): # 获取 单引多 和 多引多 的权利要求编号
        for index,claim in self.claim_dic.items():
            if index in self.one_cite_muti_dic or index == 1:
                continue
            forepart = claim[1]
            for claim_num in range(50,0,-1):
                if str(claim_num) in forepart:
                    self.one_cite_one_dic[index] = [claim_num]
                    break
    
    def check_multi_cite_claim(self):   # 校验直接多引多 & 间接多引多
        self.ckresult_txt += f'\u2029<多引多>\u2029'
        if self.claim_max < 3:  # 独权不校验多引多
            return
        self.one_cite_muti_dic = {}
        self.one_cite_one_dic = {}
        # 获取具有 引用多项的权利要求编号  {claim_index:citednumarray(eg:[1,3,5])}
        self.get_one_cite_multi_claim()
        if not self.one_cite_muti_dic:
            return
        # 获取具有  引用单项的权利要求编号 {claim_index:citednumarray(eg:[1])}
        self.get_one_cite_one_claim()

        # 判断直接多引多
        for claim_index_1 in self.one_cite_muti_dic:
            for claim_index_2 in self.one_cite_muti_dic:
                if claim_index_1 in self.one_cite_muti_dic[claim_index_2]:
                    self.ckresult_txt += f'权利要求{claim_index_2}，<直接>多引多\u2029'
                    self.dataframe_list.append(['','多引多',f'权{claim_index_2}','直接多引多','-10'])
        # 判断间接多引多（一层）
        for claim_index_1 in self.one_cite_one_dic: # 单引单 #  4:[3]  2:[1]   1  2:1 3:1,2  4:3  5:1,4
            if self.one_cite_one_dic[claim_index_1][0] in self.one_cite_muti_dic:
                for claim_index_2 in self.one_cite_muti_dic: # 单引多 # 3:[1,2] 5:[1,4]
                    if claim_index_1 in self.one_cite_muti_dic[claim_index_2]:
                        self.ckresult_txt += f'权利要求{claim_index_2}，<间接>多引多\u2029'
                        self.dataframe_list.append(['','多引多',f'权{claim_index_2}','间接多引多','-10'])
        # 判断间接多引多（两层） # 单引单  1  2:1 3:1,2  4:3  5:4  6:1,4
        for claim_index_1 in self.one_cite_one_dic:
            for claim_index_2 in self.one_cite_one_dic: # 单引单
                if claim_index_2 == self.one_cite_one_dic[claim_index_1]:
                    if self.one_cite_one_dic[claim_index_1][0] in self.one_cite_muti_dic:
                        for claim_index_3 in self.one_cite_muti_dic:
                            if claim_index_1 in self.one_cite_muti_dic[claim_index_3]:
                                self.ckresult_txt += f'权利要求{claim_index_3}，<间接>多引多\u2029'
                                self.dataframe_list.append(['','多引多',f'权{claim_index_3}','间接多引多','-10'])
        # 判断间接多引多（两层） # 单引单  1  2:1 3:1,2  4:3  5:4  6:1,5
        for claim_index_1 in self.one_cite_one_dic:  # idx1 = 5
            for claim_index_2 in self.one_cite_one_dic: # 单引单  idx2 = 4
                if claim_index_2 == self.one_cite_one_dic[claim_index_1]:
                    for claim_index_3 in self.one_cite_muti_dic:
                        if claim_index_1 in self.one_cite_muti_dic[claim_index_3]:
                            self.ckresult_txt += f'权利要求{claim_index_3}，<间接>多引多\u2029'
                            self.dataframe_list.append(['','多引多',f'权{claim_index_3}','间接多引多','-10'])
    def check_ckmarks_not_cited(self): # 校验引用基础
        # 校验各项权利要求自身的引用基础
        self.ckresult_txt += f'\u2029<特征引用基础>\u2029'
        for claim_index in self.claim_dic:
            if claim_index == 1:
                continue
            claim = self.claim_dic[claim_index][0].replace('\u2029','').replace('所述的','所述').replace('(','（').replace(')','）')
            forepart = self.claim_dic[claim_index][1]
            # 获取所采用的附图标记
            part_array = get_mark_nums(claim)
            # 获取特征词典parts_dic 字典格式 '权利要求编号':从属的权利要求 $ 权利要求含有的特征
            num_cite = []
            if '或' in forepart:
                nums_array = forepart.split('或')
                for i in range(0,len(nums_array)):
                    if i == 0:
                        num_cite.append(nums_array[0])
                    elif i == len(nums_array) - 1:
                        for _ in nums_array[-1]:
                            if _ not in '1234567890':
                                num_cite.append(nums_array[-1].split(_)[0])
                                break
                    else:
                        num_cite.append(str(i))
            elif '至' in forepart:
                nums_array = forepart.split('至')
                num_1 = nums_array[0]
                for _ in nums_array[-1]:
                    if _ not in '1234567890':
                        num_2 = nums_array[-1].split(_)[0]
                        break
                for i in range(int(num_1),int(num_2) + 1):
                    num_cite.append(str(i))
            elif '~' in forepart:
                nums_array = forepart.split('~')
                num_1 = nums_array[0]
                for _ in nums_array[-1]:
                    if _ not in '1234567890':
                        num_2 = nums_array[-1].split(_)[0]
                        break
                for i in range(int(num_1),int(num_2) + 1):
                    num_cite.append(str(i))
            else:
                if forepart[0] not in '1234567890':
                    num_cite = ['\n']
                else:
                    for _ in forepart:
                        if _ not in '1234567890':
                            num_cite.append(forepart.split(_)[0])
                            break
            # parts_dic赋值 权X 所包含的特征
            self.parts_dic[claim_index] = ' '.join(num_cite) + '$' + ' '.join(part_array)
        # 校验权利要求之间的引用基础
        for claim_index in range(2,len(self.parts_dic)):# 跳过独权1
            cite_num_array = self.parts_dic[claim_index].split('$')[0].split() # 被引用的权利要求序号
            parts_cited_array = self.parts_dic[claim_index].split('$')[1].split() # 权利要求含有的技术特征
            all_claim_txt = ''
            # 整合所有被引用权利要求全文
            for cite_num in cite_num_array: # 被引用的权利要求序号列表
                all_claim_txt += self.claim_dic[int(cite_num)][0]
            # 判断claim_index中的所有技术特征是否存在于all_claim_txt中
            for part in parts_cited_array:
                if f'{part}' not in all_claim_txt and f'{part}包括' in self.claim_dic[claim_index][0]:
                    self.ckresult_txt += f'权利要求{claim_index}的特征<{part}>未出现在引用的权利要求{cite_num}中\u2029'
                    self.dataframe_list.append(['','引用基础',f'权{claim_index}',f'权{claim_index}的<{part}>未出现在引用的权{cite_num}中','-5'])
    def extract_claim_tree(self): # 权利要求树
        self.ckresult_txt += f'\u2029<权利要求树>\u2029'
        all_forepart_array = []
        for claim_index in self.claim_dic:
            all_forepart_array.append(self.claim_dic[claim_index][1])
        claim_tree_array = get_claimtree(all_forepart_array)
        for item in claim_tree_array:
            self.ckresult_txt += f'{item}\u2029'

    def check_claim(self):  
        # 初步校验  '句号'、划界词、序号
        # 不再因为基础标点问题提前 return：论文要求错误显示区一次列出全部
        # 形式缺陷，旧逻辑只要有一项缺句号就跳过后面 5 项检查。
        if not self.check_preliminary():
            self.ckresult_txt += '<请确认句号、划界词、序号；其余检查仍继续执行>\u2029'
        # 校验不确定用语
        self.check_uncertain_words()
        # 获取前序部分、特征部分
        self.get_fore_char()
        # 校验直接多引多 & 间接多引多 
        self.check_multi_cite_claim()
        # 校验引用基础
        self.check_ckmarks_not_cited()
        # 校验未使用的附图标记
        self.check_text_ckmarks_unused()
        # 提取权利要求树
        if self.check_claimtree.checkState() == 2: # 选中  0未选中
            self.extract_claim_tree()


class Worker_Ocr(QThread):
    """OCR 后台线程：调用百度 OCR API 识别 PDF/Word/图片中的文字。
    避免阻塞 UI 线程。"""
    progress = pyqtSignal(str)
    def __init__(self,strPathFile):
        super().__init__()
        self.out_ocr_txt = ''
        self.strPathFile = strPathFile
    def run(self):
        if self.strPathFile:
            self.image_ocr()
            self.progress.emit(self.out_ocr_txt)
    def image_ocr(self):
        import requests, base64
        self.api_key = ''
        self.secret_key = ''
        self.access_token = ''
        try:
            url=f'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={self.api_key}&client_secret={self.secret_key}'
            headers={'Content-Type': 'application/json; charset=UTF-8'}
            response = requests.get(url,headers).json()
            self.access_token = response['access_token']
            if '.pdf' in self.strPathFile:
                self.get_pdftxt(self.strPathFile)
            elif '.txt' in self.strPathFile:
                self.out_ocr_txt = open(self.strPathFile,'r',encoding='utf-8').read()
            elif '.doc' in self.strPathFile or '.docx' in self.strPathFile:
                self.out_ocr_txt = self.read_word_file(self.strPathFile)
            elif '.jpg' in self.strPathFile or '.jpeg' in self.strPathFile or '.png' in self.strPathFile or '.bmp' in self.strPathFile:
                marks_array = []
                url = 'https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic' # 高精度文字识别 无位置
                img = base64.b64encode(open(self.strPathFile, 'rb').read())
                params = {"image":img}
                url = url + "?access_token=" + self.access_token
                headers = {'content-type': 'application/x-www-form-urlencoded'}
                response = requests.post(url, data=params, headers=headers)
                img_data = response.json()['words_result']
                for _ in img_data:
                    mark = _['words']
                    marks_array.append(mark)
                self.out_ocr_txt = '\n'.join(marks_array)
                self.out_ocr_txt = refine_mutilines(self.out_ocr_txt)
            else: # 其他文件
                self.out_ocr_txt = ''
        except Exception as e:
            print('Error Code 501',e)
            self.out_ocr_txt = ''
    def get_pdftxt(self,file_path):
        try:
            import pdfplumber
            pdf = pdfplumber.open(file_path)
            for page in pdf.pages:
                self.out_ocr_txt += page.extract_text()
        except Exception as e:
            print('> Error Code 701',e)
    def read_word_file(self,file_path):
        import docx
        doc = docx.Document(file_path)
        text = []
        for paragraph in doc.paragraphs:
            text.append(paragraph.text)
        return '\n'.join(text)

class FileDropLabel(QLabel):
    """支持拖拽文件的 QLabel，用于接收图片/文档拖入。"""
    def __init__(self,label_txt):
        super().__init__()
        self.setAcceptDrops(True)  # 设置控件接受拖放事件
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(50)
        self.setMinimumWidth(50)
        self.setText(label_txt)
        self.setToolTip(label_txt)
        self.resizeEvent = self.label_change_event
        self.dir = ''
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()  # 接受包含URLs的拖拽事件
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            urls = [url.toLocalFile() for url in event.mimeData().urls()]
            # 处理拖放的本地文件路径
            self.dir = urls[0]
            self.resize_label_img()
            # 在这里可以对拖入的文件进行进一步操作，例如读取内容、显示文件名等
            event.accept()
        else:
            event.ignore()
    def label_change_event(self,event):
        if 'pdf' in self.dir or 'doc' in self.dir:
            return
        if not self.dir:
            return
        img = QImage(self.dir)
        img_w = img.width()
        img_h = img.height()

        if img_w >= img_h:
            img_rate = img_w/self.width()
            img_w = self.width()
            img_h = img_h/img_rate
        else:
            img_rate = img_h/self.height()
            img_h = self.height()
            img_w = img_w/img_rate
        result=img.scaled(int(img_w),int(img_h),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        self.setPixmap(QPixmap.fromImage(result))
    def resize_label_img(self):
        if 'pdf' in self.dir or 'doc' in self.dir:
            return
        img = QImage(self.dir)
        img_w = img.width()
        img_h = img.height()

        if img_w >= img_h:
            img_rate = img_w/1000
            img_w = 1000
            img_h = img_h/img_rate
        result = img.scaled(int(img_w),int(img_h),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        self.setPixmap(QPixmap.fromImage(result))
class SwitchBtn(QWidget):
    """通用开关按钮：左上角三个开关（联想/撰写阅读/自动补全）共用。"""
    checkedChanged = pyqtSignal(bool)
    status_sig = pyqtSignal()
    def __init__(self, text_off='联想', text_on='关闭', checked=False, parent=None):
        super().__init__(parent)
        self.edge = QColor(PAL['border'])       # 轨道描边：与功能区边框同色
        self.checked = checked
        # 轨道配色（贴合深色主题）：未选中=主题蓝（功能「启用/激活」），选中=深灰（「关闭/停用」）
        self.bgColorOff = QColor(PAL['accent_hi'])  # 激活态：主题蓝
        self.bgColorOn = QColor(PAL['hover'])       # 停用态：深灰
        # 旋钮：浅色，在蓝/灰轨道上都清晰；带一点渐变高光由 drawSlider 处理
        self.sliderColorOff = QColor('#f4f7fb')
        self.sliderColorOn = QColor('#e3e9f0')
        # 文本：浅色，贴合深色 ribbon（替代原本的黑色）
        self.textColorOff = QColor('#eef3f8')
        self.textColorOn = QColor('#c3cdd7')
        self.textOff = text_off
        self.textOn = text_on
        self.space = 1
        self.step = self.width() / 50
        self.startX = self.width() - self.height() if checked else 0
        self.endX = self.startX
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateValue)
        self.status_sig.connect(self.auto_step)
    def isChecked(self):
        return self.checked
    def auto_step(self):
        self.step = self.width() / 40
        self.endX = self.width() - self.height() if self.checked else 0
        self.timer.start(5)
    def updateValue(self):
        if self.checked:
            if self.startX < self.endX:
                self.startX += self.step
            else:
                self.startX = self.endX
                self.timer.stop()
        else:
            if self.startX > self.endX:
                self.startX -= self.step
            else:
                self.startX = self.endX
                self.timer.stop()
        self.update()
    def mousePressEvent(self, event):
        self.checked = not self.checked
        self.checkedChanged.emit(self.checked)
        self.step = self.width() / 40
        self.endX = self.width() - self.height() if self.checked else 0
        self.timer.start(5)
    def mouseMoveEvent(self, event):
        pass
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # __init__ 阶段宽高为0，无法定位圆点；拿到真实尺寸后按 checked 状态归位
        self.startX = self.width() - self.height() if self.checked else 0
        self.endX = self.startX
        self.update()
    def paintEvent(self, evt):
        try:
            painter = QPainter()
            painter.begin(self)
            painter.setRenderHint(QPainter.Antialiasing)
            self.drawBg(evt, painter)
            self.drawSlider(evt, painter)
            self.drawText(evt, painter)
            painter.end()
        except:
            pass
    def drawText(self, event, painter):
        painter.save()
        if self.checked:
            painter.setPen(self.textColorOn)
            painter.drawText(int(self.space*4), 0, int(self.width()/2+self.space*2), self.height(), Qt.AlignCenter, self.textOn)
        else:
            painter.setPen(self.textColorOff)
            painter.drawText(int(self.width()/2), 0, int(self.width()/2-self.space), self.height(), Qt.AlignCenter, self.textOff)
        painter.restore()
    def drawBg(self, event, painter):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRect(0, 0, self.width(), self.height())
        radius = (rect.height() - 2) / 2.0
        painter.setPen(QPen(self.edge, 1))
        painter.setBrush(self.bgColorOn if self.checked else self.bgColorOff)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
        painter.restore()
    def drawSlider(self, event, painter):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRect(0, 0, self.width(), self.height())
        knob = int(rect.height() - 4)
        x = int(self.startX + 2)
        y = int((rect.height() - knob) / 2)
        krect = QRect(x, y, knob, knob)
        # 投影：让旋钮有轻微悬浮感
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 55))
        painter.drawEllipse(krect.adjusted(0, 1, 0, 1))
        # 旋钮：径向渐变（左上高光）营造立体感
        grad = QRadialGradient(krect.center().x(),
                               krect.center().y() - knob * 0.3,
                               knob * 0.85)
        grad.setColorAt(0, QColor('#ffffff'))
        grad.setColorAt(1, self.sliderColorOn if self.checked else self.sliderColorOff)
        painter.setBrush(grad)
        painter.drawEllipse(krect)
        painter.restore()

# 旧版 Label_Symbol（QLabel + insertHtml + 固定编辑器引用）已移除：
# 现由 src/special_chars.py 的 SpecialCharPanel 发信号给当前编辑器。
class QWidget_Notop(QWidget):
    """无边框置顶可拖拽小窗口基类，用于各类弹出面板。"""
    def __init__(self,title):
        super().__init__()
        self.setObjectName('FenrirPopup')
        self.dragging = False
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint) # 隐藏标题栏
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.mousePressEvent = self.start_drag
        self.mouseReleaseEvent = self.window_pressrelease
    def window_pressrelease(self,event):
        self.dragging = False
    def start_drag(self, event):
        self.dragging = True
        self.old_pos = event.globalPos()
    def mouseMoveEvent(self, event):
        if self.dragging:
            delta = QPoint(event.globalPos() - self.old_pos)
            x = event.globalX()
            y = event.globalY()
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

class OcrDropTextEdit(QTextEdit):
    """支持拖拽文件并触发 OCR 的 QTextEdit。"""
    # 定义一个信号
    sendmsg = pyqtSignal(object)
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.strPathFile = ""
        # 编辑器底色/文字由全局 QSS 统一控制
        self.setMinimumWidth(50)
        self.setLineWrapMode(0) #依据编辑框宽度换行  0 为不换行
        self.setPlaceholderText("按照下述格式粘贴后，将自动整理格式\n例1：\n1壳体、2把手、3内壁\n例2：\n1壳体、11把手；2内壁\n例3：\n1壳体；2把手；3内壁\n例4：\n1壳体，2把手，3内壁")
        self.setToolTip('按Ctrl点击相应标记，可同时高亮显示多个技术特征')
        self.setUndoRedoEnabled(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff) # 隐藏垂直滚动条

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
    def dropEvent(self, event):
        self.strPathFile = event.mimeData().text().replace('file:///', '')
        self.start_work()
    def start_work(self):
        if self.strPathFile.endswith('.jpg') or self.strPathFile.endswith('.png') or self.strPathFile.endswith('.bmp') or self.strPathFile.endswith('.jpeg') or self.strPathFile.endswith('.gif'):
            try:
                image = QImage(self.strPathFile)
                width = image.width()
                height = image.height()
                if width >= height:
                    height = int(height / (width/400))
                    width = 400

                else:
                    width = int(width / (height/400))
                    height = 400
            except Exception as e:
                print(e)
                # 将图片转换为HTML格式，并将其插入到TextEdit中
            cursor = self.textCursor()
            html = f"<img src=\"{self.strPathFile}\" alt=\"{os.path.basename(self.strPathFile)}\" width=\"{width}\" height=\"{height}\" />"
            cursor.insertHtml(html)
        else:
            self.ocr_thread = Worker_Ocr(self.strPathFile)
            self.ocr_thread.progress.connect(self.update_text)
            self.ocr_thread.start()
        
    def update_text(self,in_txt):
        self.insertPlainText('\n' + in_txt)

class LineNumPaint(QWidget):
    """行号绘制组件，与 QTextEditWithLineNum 配合显示左侧行号栏。"""
    def __init__(self, q_edit):
        super().__init__(q_edit)
        self.q_edit_line_num: QTextEditWithLineNum = q_edit

    def sizeHint(self):
        return QSize(self.q_edit_line_num.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        """ 把原来QTextEditWithLineNum.lineNumberAreaPaintEvent全部移到这里，这才是行号控件真正的paintEvent """
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(PAL['bg']))
        te = self.q_edit_line_num
        lh = te.line_height
        first_visible_block_number = te.cursorForPosition(QPoint(0, 1)).blockNumber()
        blockNumber = first_visible_block_number
        block = te.document().findBlockByNumber(blockNumber)
        top = 3
        if blockNumber == 0:
            additional_margin = int(te.document().documentMargin() - te.verticalScrollBar().sliderPosition() - 1)
        else:
            prev_block = te.document().findBlockByNumber(blockNumber - 1)
            additional_margin = int(te.document().documentLayout().blockBoundingRect(prev_block).bottom()) - te.verticalScrollBar().sliderPosition()
        top += additional_margin
        bottom = top + int(te.document().documentLayout().blockBoundingRect(block).height())
        last_block_number = te.cursorForPosition(QPoint(0, te.height() - 1)).blockNumber()
        height = te.fontMetrics().height()
        while block.isValid() and (top <= event.rect().bottom()) and blockNumber <= last_block_number:
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                if number != '1':
                    if lh == 0:
                        pass
                    elif lh == 0.2:
                        height += 1.8
                    elif lh == 0.5:
                        height += 5.6
                    elif lh == 1.0:
                        height += 9.6
                    elif lh == 1.5:
                        height += 15.5
                    elif lh == 2.0:
                        height += 19.5
                    elif lh == 2.5:
                        height += 25.0
                    elif lh == 3.0:
                        height += 31
                    elif lh == 3.5:
                        height += 35.5
                    elif lh == 4.0:
                        height += 39.5
                painter.setPen(QColor('#8c9196'))
                painter.drawText(0, int(top), int(te.lineNumberAreaWidth()), int(height), Qt.AlignCenter, number)
            block = block.next()
            top = bottom
            bottom = top + int(te.document().documentLayout().blockBoundingRect(block).height())
            blockNumber += 1

import math as _math


class _WaveRail(QWidget):
    """编辑器右侧「音浪 / 海浪」装饰栏的绘制控制器（卡顿修复版）。

    旧实现把波形画在 viewport 上一个 26px 宽的半透明 QWidget 里。Qt 为了给
    半透明子控件合成背景，每刷新一帧都会把**整个编辑器视口**（离屏实测
    870×714）标记为脏并重绘整篇文档：波形单帧 17ms + 文档 4ms，40ms 的
    定时器只能跑到 21fps，帧间隔忽长忽短，输入明显发涩。

    现在这个对象只是隐藏的控制器（仍保留 26px 窄带几何便于定位），波形
    直接画进 QTextEditWithLineNum.paintEvent 的末尾，定时器只让 viewport
    重绘 26px 窄带（文档绘制 4.08ms → 1.08ms）。配套优化：
      * 相位按真实时间推进，掉帧时波速恒定，不再「一顿一顿」；
      * 采样 2px → 4px，三角函数改成和角公式 + 查找表，每帧不再算
        近 700 次 sin/exp；
      * 渐变、音浪柱画笔、标题锚点按 (高度, 光标, 文档版本) 缓存；
      * 按最近帧耗时自动降级（省掉雾气 / 第二道浪），慢机器也不堵输入。
    波形形态与配色沿用旧版：x(y) = 光标能量包络 × 两条反向行波。另外叠了
    一层「湖面水汽」（曲线到右缘的淡淡雾面 + 宽柔光），光标光点用径向
    渐变散焦，而不是硬边圆点。
    """
    TAU = 2 * _math.pi
    RAIL_W = 26
    BASE_PAD = 0        # 波形基线距右边缘：0 = viewport 右沿
    EDGE_INSET = 1.5    # 基线再向内 1.5px，让 2px 圆头笔触完整落在视口内
    AMP = 18            # 最大向左振幅
    WAVE_LEN = 168.0    # 主波波长 px
    STEP = 4.0          # 曲线采样步长（旧版主波 2px / 副波 3px）
    OMEGA = 2.875       # rad/s，等价于旧版 0.115 rad / 40ms
    INTERVAL = 16       # 目标 60fps：去掉横向短柱后单帧只剩 ~1.5ms
    SLOW_INTERVAL = 24  # 慢机器降级到约 42fps，宁可慢也不堵输入
    # 单帧相位上限 ≈ 一个 20ms 帧的步进。主线程偶发卡 100ms 时，恢复后
    # 也只往前走一帧的距离——波形会「停一下再走」，但绝不会一次跳好几格。
    MAX_STEP = 0.058
    BUDGET = 0.007      # 单帧绘制预算 7ms，超出自动降级

    def __init__(self, editor):
        super().__init__(editor.viewport())
        self.ed = editor
        self.setObjectName('WaveRail')
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.NoFocus)
        # 三条波各自的相位。必须**分别**回绕：副浪 / 第三道浪的时间系数
        # 是 0.72 / 1.1，不是 1 的整数倍，若共用一个 total phase 再取模，
        # 每次 2π 回绕时 sin(k*y - 0.72*ph) 会凭空跳 4.5rad（实测光标行
        # 2.1px、整条曲线 4.7px 的突跳，就是「缺帧、突然落到最低点」）。
        # 独立累加 + 独立取模后 sin/cos 始终连续，波速不变。
        self.phase = 0.0
        self.phase2 = 0.0
        self.phase3 = 0.0
        self._active = True
        self._clock = QElapsedTimer()
        self._clock.start()
        self._perf = QElapsedTimer()
        self._perf.start()
        self._last_ms = 0
        self._frame_cost = 0.004
        self._quality = 2          # 2 全效 / 1 省光晕 / 0 只画主浪
        self._quality_hold = 0     # 切换后的冷却帧数，防止画质来回抖动
        self._cache_key = None
        self._cache = None
        self._mist_img = None
        self._mist_key = None
        self._mist_phase = -99.0
        self._title_key = None
        self._title_ys = ()
        # 静态画笔只建一次，避免每帧构造大量 QColor / QPen
        _c = QColor('#4a8ae8'); _c.setAlpha(60)
        self._pen_low = QPen(_c, 1.0, Qt.SolidLine, Qt.RoundCap)
        _c = QColor('#4a8ae8'); _c.setAlpha(24)
        self._pen_glow = QPen(_c, 7.0, Qt.SolidLine, Qt.RoundCap)
        # 光标光点：用径向渐变做出「散焦」的柔光，而不是一颗硬边圆点。
        # 渐变建在原点，绘制时 translate 过去，避免每帧重建（见 _draw_dot）。
        self._dot_halo = QRadialGradient(QPointF(0.0, 0.0), 15.0)
        for _p, _a in ((0.00, 88), (0.28, 60), (0.55, 30), (0.78, 12), (1.00, 0)):
            _c = QColor('#FB8073'); _c.setAlpha(_a)
            self._dot_halo.setColorAt(_p, _c)
        self._dot_core = QRadialGradient(QPointF(0.0, 0.0), 6.0)
        for _p, _a in ((0.00, 215), (0.32, 178), (0.60, 96), (0.84, 28),
                       (1.00, 0)):
            _c = QColor('#FFB794'); _c.setAlpha(_a)
            self._dot_core.setColorAt(_p, _c)
        # 段落标题锚点也做同样的散焦处理，只是更小更淡
        self._dot_title = QRadialGradient(QPointF(0.0, 0.0), 4.2)
        for _p, _a in ((0.00, 190), (0.45, 120), (0.78, 40), (1.00, 0)):
            _c = QColor('#FB8073'); _c.setAlpha(_a)
            self._dot_title.setColorAt(_p, _c)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(self.INTERVAL)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        # 关键：不显示。显示半透明子控件会让 Qt 每帧重绘整篇文档。
        self.hide()
        # 焦点冻结不在这里做：主程序会用实例属性覆盖 editor.focusOutEvent，
        # 而额外挂 eventFilter / 全局 focusChanged 在本机 PyQt 的退出阶段
        # 都会触发进程崩溃。可见性自停（_tick + paintEvent.resume）已足够
        # 把 10 个页签的空转定时器收敛到当前页那一个。

    # ---- 刷新 / 动画 ---------------------------------------------------
    def invalidate(self):
        """只把 26px 窄带标记为脏，绝不触发整篇文档重绘。"""
        vp = self.ed.viewport()
        vp.update(QRect(vp.width() - self.RAIL_W, 0,
                        self.RAIL_W, vp.height()))

    def _now_ms(self):
        """毫秒级浮点时间。QElapsedTimer.elapsed() 是整数毫秒，16ms 帧下
        量化误差可达 ±3ms（波速抖动 ±7%），用纳秒接口换算更均匀。"""
        return self._clock.nsecsElapsed() / 1000000.0

    def resume(self):
        """（重新）启动动画并重置时间基准，避免恢复瞬间波形大跳。"""
        self._last_ms = self._now_ms()
        self._timer.start()

    def set_active(self, on):
        """有焦点时波在流动，失焦后冻结成静态波形（不隐藏、不跳变）。"""
        self._active = bool(on)
        if self._active and self.ed.isVisible():
            self.resume()
        else:
            self._timer.stop()
        self.invalidate()

    def _tick(self):
        if not self._active or not self.ed.isVisible():
            # 主窗口一次会建 10 个编辑器（每个 tab 一个），只有当前页可见。
            # 不可见就彻底停表，避免 10 个 QTimer 在主线程里空转。
            self._timer.stop()
            return
        now = self._now_ms()
        dt = (now - self._last_ms) / 1000.0
        self._last_ms = now
        # 挂起 / 休眠恢复后不要一次跳一大截；其余时刻按真实时间推进
        if dt < 0.0 or dt > 0.25:
            dt = self.INTERVAL / 1000.0
        # 掉帧时限制单帧位移，宁可整体慢一点也不让波形「跳一格」
        dphi = min(self.OMEGA * dt, self.MAX_STEP)
        # 三条波各自累加、各自回绕：回绕点不会在波形上留下任何突跳
        self.phase = (self.phase + dphi) % self.TAU
        self.phase2 = (self.phase2 - dphi * 0.72) % self.TAU
        self.phase3 = (self.phase3 + dphi * 1.1) % self.TAU
        self.invalidate()

    # ---- 波形 ----------------------------------------------------------
    def cursor_y(self):
        return (getattr(self.ed, 'cursor_doc_y', 0.0)
                - self.ed.verticalScrollBar().value())

    def _envelope(self, y, cy):
        """光标处能量最高，向上下平滑衰减，远端仍保留 0.30 的基础波幅。"""
        d = (y - cy) / 118.0
        return 0.30 + 0.70 * _math.exp(-d * d)

    def wave_x(self, y, cy):
        k = 2 * _math.pi / self.WAVE_LEN
        w1 = _math.sin(k * y + self.phase)
        w2 = _math.sin(k * 0.61 * y + self.phase2 + 1.15)
        norm = 0.62 * w1 + 0.38 * w2
        return self._x_of(norm, self._envelope(y, cy))

    def _x_of(self, norm, env):
        """归一波幅 → rail 局部 x。绘制与取点共用，避免两套公式算出偏差。"""
        return (self.RAIL_W - self.BASE_PAD - self.EDGE_INSET
                - (self.AMP * env * (0.5 + 0.5 * norm)))

    @staticmethod
    def _blend(c1, c2, t):
        t = max(0.0, min(1.0, t))
        return QColor(int(c1.red() + (c2.red() - c1.red()) * t),
                      int(c1.green() + (c2.green() - c1.green()) * t),
                      int(c1.blue() + (c2.blue() - c1.blue()) * t))

    def _color_at(self, y, cy, h):
        t = y / max(1.0, h)
        dark = QColor('#2b4a6f')
        cyan = QColor('#7fd4f0')
        base = self._blend(dark, cyan, 1.0 - abs(2.0 * t - 1.0) ** 1.4)
        d = (y - cy) / 82.0
        return self._blend(base, QColor('#FB8073'), 0.86 * _math.exp(-d * d))

    # ---- 帧缓存 --------------------------------------------------------
    def _build_cache(self, h, cy):
        """与相位无关的量全部预计算；cy 量化到 4px，避免光标抖动时反复重建。"""
        key = (h, int(cy) >> 2)
        if self._cache_key == key and self._cache is not None:
            return self._cache
        k = 2 * _math.pi / self.WAVE_LEN
        k2, k3 = k * 0.61, k * 0.83
        ys, y = [], 0.0
        while y < h:
            ys.append(y)
            y += self.STEP
        ys.append(float(h))
        # sin(k*y + phase) = sin(k*y)cos(phase) + cos(k*y)sin(phase)
        s1 = [_math.sin(k * v) for v in ys]
        c1 = [_math.cos(k * v) for v in ys]
        s2 = [_math.sin(k2 * v + 1.15) for v in ys]
        c2 = [_math.cos(k2 * v + 1.15) for v in ys]
        s3 = [_math.sin(k3 * v + 0.6) for v in ys]
        c3 = [_math.cos(k3 * v + 0.6) for v in ys]
        env = [0.30 + 0.70 * _math.exp(-((v - cy) / 118.0) ** 2)
               for v in ys]
        # 纵向渐变（只依赖 h / cy）
        m = cy / max(1.0, h)
        span = min(0.20, max(0.06, 86.0 / max(1.0, h)))
        stops = {}
        def add(pos, col):
            stops[round(max(0.0, min(1.0, pos)), 5)] = QColor(col)
        add(0.0, '#2b4a6f')
        add(0.5, '#7fd4f0')
        add(1.0, '#2b4a6f')
        add(m - span, '#2f6bc4')
        add(m - span * 0.42, '#d8948a')
        add(m, '#FB8073')
        add(m + span * 0.42, '#d8948a')
        add(m + span, '#2f6bc4')
        ordered = sorted(stops.items())

        def make_grad(alpha_mul=1.0, floor_a=0):
            g = QLinearGradient(0, 0, 0, h)
            for pos, col in ordered:
                c = QColor(col)
                a = int(c.alpha() * alpha_mul)
                c.setAlpha(max(floor_a, min(255, a)))
                g.setColorAt(pos, c)
            return g

        pen_main = QPen(QBrush(make_grad()), 2.0, Qt.SolidLine, Qt.RoundCap)
        # 雾：贴着曲线的两层柔光 + 曲线到右缘之间的雾面，模拟湖面上的水汽
        pen_mist_wide = QPen(QBrush(make_grad(0.18, 5)), 12.0,
                             Qt.SolidLine, Qt.RoundCap)
        pen_mist_near = QPen(QBrush(make_grad(0.38, 10)), 4.5,
                             Qt.SolidLine, Qt.RoundCap)
        mist = QLinearGradient(0, 0, 0, h)
        for pos, a in ((0.0, 13), (m - span * 2.6, 17), (m - span, 26),
                       (m, 48), (m + span, 26), (m + span * 2.6, 17), (1.0, 13)):
            c = QColor('#c6ebff')
            c.setAlpha(a)
            mist.setColorAt(max(0.0, min(1.0, pos)), c)
        brush_mist = QBrush(mist)
        self._cache_key = key
        self._cache = (ys, s1, c1, s2, c2, s3, c3, env, pen_main,
                       pen_mist_wide, pen_mist_near, brush_mist)
        return self._cache

    def _title_points(self, h):
        """标题锚点的 y 坐标缓存：只有滚动 / 改文 / 改高度才重新遍历文档。"""
        try:
            doc = self.ed.document()
            scroll = self.ed.verticalScrollBar().value()
            key = (h, scroll, doc.revision())
            if self._title_key == key:
                return self._title_ys
            layout = doc.documentLayout()
            titles = getattr(self.ed, 'section_titles', ())
            block = self.ed.cursorForPosition(QPoint(0, 0)).block()
            found = []
            while block.isValid():
                by = layout.blockBoundingRect(block).top() - scroll
                if by > h:
                    break
                if -8 <= by <= h and block.text().strip() in titles:
                    found.append(by + 3.0)
                block = block.next()
            self._title_key = key
            self._title_ys = tuple(found)
            return self._title_ys
        except Exception:
            return ()

    # ---- 绘制 ----------------------------------------------------------
    def _draw_mist(self, p, xs, ys, h, xoff, pen_wide, pen_near, brush):
        """把雾画进 1/2 分辨率的缓冲，再平滑放大贴到右缘。

        全分辨率 + 宽笔触抗锯齿单帧要 3ms 以上；而雾本身没有细节，1/2 尺度
        再双线性放大的结果是「更柔」，正好就是想要的湖面水汽。
        """
        sw = self.RAIL_W
        iw, ih = (sw + 1) // 2, (int(h) + 1) // 2
        img = self._mist_img
        # 雾是慢速低对比的图形：每隔一帧重绘一次就够（每帧都重画看不到差别，
        # 却要多花一倍主线程时间）。几何 / 光标变化时立刻重绘。
        key = (iw, ih, self._cache_key)
        dphi = abs(self.phase - self._mist_phase)
        if dphi > _math.pi:
            dphi = self.TAU - dphi
        redraw = (img is None or img.width() != iw or img.height() != ih
                  or self._mist_key != key or dphi > 0.075)
        if img is None or img.width() != iw or img.height() != ih:
            img = QImage(iw, ih, QImage.Format_ARGB32_Premultiplied)
            self._mist_img = img
        if redraw:
            self._mist_key = key
            self._mist_phase = self.phase
            img.fill(0)
            pm = QPainter(img)
            try:
                pm.setRenderHint(QPainter.Antialiasing, True)
                pm.scale(iw / float(sw), ih / float(h))
                path = QPainterPath()
                path.moveTo(QPointF(xs[0], ys[0]))
                for i in range(1, len(ys)):
                    path.lineTo(QPointF(xs[i], ys[i]))
                curtain = QPainterPath(path)
                curtain.lineTo(QPointF(float(sw), float(h)))
                curtain.lineTo(QPointF(float(sw), 0.0))
                curtain.closeSubpath()
                pm.setPen(Qt.NoPen)
                pm.setBrush(brush)
                pm.drawPath(curtain)
                pm.setPen(pen_wide)
                pm.drawPath(path)
                pm.setPen(pen_near)
                pm.drawPath(path)
            finally:
                pm.end()
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(QRectF(xoff, 0.0, float(sw), float(h)), img,
                    QRectF(0.0, 0.0, float(iw), float(ih)))

    def paint(self, p, region=None):
        """由 QTextEditWithLineNum.paintEvent 在文档绘制完成后调用。"""
        # PyQt 虚拟方法中的未捕获异常会让 Qt 直接终止进程；装饰是纯视觉，
        # 任何异常都只跳过本帧，绝不影响编辑器本体。
        try:
            self._paint_wave(p, region)
        except Exception:
            pass

    def _paint_wave(self, p, region=None):
        self._perf.start()
        vp = self.ed.viewport()
        h, w = vp.height(), vp.width()
        if h <= 0 or w <= self.RAIL_W:
            return
        p.save()
        # 只在右缘 26px 作画；编辑器因滚动 / 输入整篇重绘时也不会越界
        p.setClipRect(QRect(w - self.RAIL_W, 0, self.RAIL_W, h))
        p.setRenderHint(QPainter.Antialiasing, True)
        xoff = w - self.RAIL_W          # rail 局部坐标 → viewport 坐标
        cy = self.cursor_y()
        (ys, s1, c1, s2, c2, s3, c3, env, pen_main,
         pen_mist_wide, pen_mist_near, brush_mist) = self._build_cache(h, cy)
        # 三条波各有自己的相位累加器（见 _tick），回绕对波形完全无感
        cp, sp = _math.cos(self.phase), _math.sin(self.phase)
        cp2, sp2 = _math.cos(self.phase2), _math.sin(self.phase2)
        cp3, sp3 = _math.cos(self.phase3), _math.sin(self.phase3)

        # 1) 主浪 / 副浪的所有 x 一次算完：每点只剩乘加，无 sin / exp
        xs = []
        for i in range(len(ys)):
            norm = (0.62 * (s1[i] * cp + c1[i] * sp)
                    + 0.38 * (s2[i] * cp2 + c2[i] * sp2))
            xs.append(self._x_of(norm, env[i]))
        path = QPainterPath()
        path.moveTo(QPointF(xoff + xs[0], ys[0]))
        for i in range(1, len(ys)):
            path.lineTo(QPointF(xoff + xs[i], ys[i]))

        # 2) 湖面水汽：曲线到右缘之间的雾面（光标高度最浓）+ 两条宽柔光。
        #    雾是低频图形，画在 1/2 分辨率的缓冲里再双线性放大，看不出差别，
        #    却能全程开抗锯齿（否则宽笔触会露出台阶、雾面变成一块硬边色块）。
        if self._quality >= 1:
            self._draw_mist(p, xs, ys, h, xoff,
                            pen_mist_wide, pen_mist_near, brush_mist)

        if self._quality >= 1:
            path2 = QPainterPath()
            for i, v in enumerate(ys):
                x2 = xs[i] + 2.5 - 2.6 * (s3[i] * cp3 - c3[i] * sp3)
                if i == 0:
                    path2.moveTo(QPointF(xoff + x2, v))
                else:
                    path2.lineTo(QPointF(xoff + x2, v))
            p.setPen(self._pen_low)
            p.drawPath(path2)
            p.setPen(self._pen_glow)
            p.drawPath(path)

        p.setPen(pen_main)
        p.drawPath(path)

        # 3) 当前行：曲线上的珊瑚红光点。用径向渐变散焦，边缘完全化开，
        #    不再是截图里那颗硬边圆点；渐变建在原点，靠平移复用。
        if -12 <= cy <= h + 12:
            cx = xoff + self.wave_x(cy, cy)
            p.setPen(Qt.NoPen)
            p.translate(cx, cy)
            p.setBrush(QBrush(self._dot_halo))
            p.drawEllipse(QPointF(0.0, 0.0), 15.0, 15.0)
            p.setBrush(QBrush(self._dot_core))
            p.drawEllipse(QPointF(0.0, 0.0), 6.0, 6.0)
            p.translate(-cx, -cy)

        # 4) 说明书段落标题：只留曲线上的暖色光点，不再画横向亮柱
        titles = self._title_points(h)
        if titles:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(self._dot_title))
            for yy in titles:
                cx = xoff + self.wave_x(yy, cy)
                p.translate(cx, yy)
                p.drawEllipse(QPointF(0.0, 0.0), 4.2, 4.2)
                p.translate(-cx, -yy)
        p.restore()

        # 自适应：先减绘制层数，仍吃力就降帧率；反之逐级恢复。
        # 每次切换留 40 帧冷却，避免在临界耗时上反复横跳造成闪烁。
        cost = self._perf.elapsed() / 1000.0
        self._frame_cost = self._frame_cost * 0.8 + cost * 0.2
        if self._quality_hold > 0:
            self._quality_hold -= 1
            return
        c = self._frame_cost
        if c > self.BUDGET:
            if self._quality > 0:
                self._quality -= 1
            elif self._timer.interval() < self.SLOW_INTERVAL:
                self._timer.setInterval(self.SLOW_INTERVAL)
            else:
                return
            self._quality_hold = 40
        elif c < self.BUDGET * 0.32:
            if self._timer.interval() > self.INTERVAL:
                self._timer.setInterval(self.INTERVAL)
            elif self._quality < 2:
                self._quality += 1
            else:
                return
            self._quality_hold = 40


class QTextEditWithLineNum(QTextEdit):
    """带左侧行号栏的多行文本编辑器，是 Fenrir 的核心编辑组件。"""
    sendmsg = pyqtSignal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_height = 0.5
        # 说明书分段标题关键词集合
        self.section_titles = {"技术领域", "背景技术", "发明内容", "实用新型内容", "附图说明", "具体实施方式","本发明的有益效果：","本实用新型的有益效果：","附图标记说明：","实施例1","实施例2","实施例3"}
        # 旧版只靠 textChanged/cursorPositionChanged 回调懒赋值；动态新建的空白
        # 编辑器不会触发这两个信号，首次 paintEvent 读取该属性会抛异常并被 Qt
        # 直接终止进程（PyQt 虚拟方法中的未捕获异常）。这里显式初始化。
        self.cursor_doc_y = 0.0
        # 右侧音浪 / 海浪装饰栏控制器（详见 _WaveRail）。被绘制逻辑读取的
        # 属性必须在它之前就绪——构造期就可能收到绘制事件。
        self.wave_rail = _WaveRail(self)

        # 滚动时只需重画右缘窄带；显示半透明子控件会让 Qt 重绘整篇文档
        self.verticalScrollBar().valueChanged.connect(
            self.wave_rail.invalidate)
        self.cursorPositionChanged.connect(self.update_cursor_doc_y)
        self.textChanged.connect(self.update_cursor_doc_y)

        shortcut_txt_2 = "模板快捷键：\nAlt+1：OA答复\nAlt+2：说明书\nAlt+3：权利要求书\nAlt+4：复审请求\nAlt+5：无效宣告请求\nAlt+6：AI撰写说明书\n"
        shortcut_txt_3 = "批量文本快捷键（A=特征名称，1=序号）：\nCtrl+1：名称加序号 A→A1\nCtrl+2：名称加括号序号 A→A(1)\nCtrl+3：序号加名称 1→A1\nCtrl+4：序号加括号名称 1→A(1)\nCtrl+5：删除标记（精确） A1/(1)→A\nCtrl+6：序号转括号 A1→A(1)\nCtrl+7：括号转序号 A(1)→A1\nCtrl+8：标记列表合并成段\nCtrl+9：提取发明内容\n"
        shortcut_txt_4 = "Ctrl+Q：提取附图标记\nCtrl+W：统一单位\nCtrl+E：统一元素符号\nCtrl+R：删除多余回车\nCtrl+T：删除空格\nCtrl+J：删除段号\nCtrl+G：增加段号\nCtrl+F：定位顶部网络搜索框（框内 Enter 百度 / Ctrl+Enter 必应 / Shift+Enter 谷歌）\nCtrl+Shift+H：批量替换\nCtrl+H：查找和替换\nCtrl+Shift+I：插入图片（Ctrl+V 粘贴截图 / 直接拖入图片文件）\n\nCtrl+~：自定义文本联想\nCtrl+Enter：自动补充序号/从权"
        self.setPlaceholderText(f'{shortcut_txt_2}\n{shortcut_txt_3}\n{shortcut_txt_4}')
        self.setFontPointSize(12)
        self.setUndoRedoEnabled(True)

        # =========行号控件初始化 修复重点 =========
        self.lineNumberArea = LineNumPaint(self)
        self.document().blockCountChanged.connect(self.update_line_num_width)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.verticalScrollBar().valueChanged.connect(self.lineNumberArea.update)
        self.update_line_num_width()

        self.setAcceptDrops(True)
        self.strPathFile = ""
        self._init_image_support()

    def paintEvent(self, event):
        """文档由 QTextEdit 绘制完成后，把波形叠在右缘 26px 窄带上。

        定时器只 update 这条窄带，因此 Qt 会把文档绘制裁剪到 26px，
        不会像半透明子控件那样每帧重绘整篇文档（卡顿的主因）。
        PyQt 虚拟方法里的异常会直接终止进程，这里全部兜住。
        """
        try:
            super().paintEvent(event)
            rail = getattr(self, 'wave_rail', None)
            if rail is None:
                return
            # 切回这个 tab / 窗口重新可见时，把之前自停的动画唤醒。
            # paintEvent 只在可见时触发，用它当恢复信号最可靠。
            if rail._active and self.isVisible() and not rail._timer.isActive():
                rail.resume()
            p = QPainter(self.viewport())
            try:
                rail.paint(p, event.rect())
            finally:
                p.end()
        except Exception:
            pass

    def viewportEvent(self, event: QEvent):
        """标准QTextEdit行号实现：视口变化更新行号栏与右侧波形栏几何"""
        result = super().viewportEvent(event)
        cr = self.contentsRect()
        # 构造期向 viewport 挂子控件也会派发 viewportEvent，此时两个覆盖层
        # 可能都还没创建；PyQt 虚拟方法里的未捕获异常会让 Qt 直接终止进程。
        num = getattr(self, 'lineNumberArea', None)
        if num is not None:
            num.setGeometry(QRect(cr.left(), cr.top(),
                                  self.lineNumberAreaWidth(), cr.height()))
        rail = getattr(self, 'wave_rail', None)
        if rail is not None:
            # rail 是隐藏的控制器，保留几何只为定位 / 校验；坐标系仍用
            # viewport 自身，不能用 QTextEdit 的 contentsRect（差一个 frame）。
            vr = self.viewport().rect()
            rail.setGeometry(QRect(vr.right() - _WaveRail.RAIL_W + 1,
                                   vr.top(), _WaveRail.RAIL_W, vr.height()))
        return result

    def focusInEvent(self, event):
        super().focusInEvent(event)
        rail = getattr(self, 'wave_rail', None)
        if rail is not None:
            rail.set_active(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        rail = getattr(self, 'wave_rail', None)
        if rail is not None:
            rail.set_active(False)

    def update_cursor_doc_y(self):
        cursor = self.textCursor()
        rect = self.cursorRect(cursor)
        self.cursor_doc_y = rect.y() + self.verticalScrollBar().value()
        rail = getattr(self, 'wave_rail', None)
        if rail is not None:
            rail.invalidate()

            


    def lineNumberAreaWidth(self):
        block_count = self.document().blockCount()
        max_value = max(1, block_count)
        d_count = len(str(max_value))
        _width = self.fontMetrics().width('9') * d_count + 5
        return 15

    def update_line_num_width(self):
        self.setViewportMargins(self.lineNumberAreaWidth() + 5, 0, 0, 0)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        self.strPathFile = event.mimeData().text().replace('file:///', '')
        self.drop_start_work()

    def drop_start_work(self):
        # 图片拖入：统一走 insert_picture，遵循「插入→图片」里选的环绕方式，
        # 同时把图片复制进 data/images（原来的写法直接引用原路径，源文件一删就裂图）
        if self.strPathFile.lower().endswith(imgs.IMAGE_EXTS):
            self.insert_picture(self.strPathFile)
        else:
            self.ocr_thread = Worker_Ocr(self.strPathFile)
            self.ocr_thread.progress.connect(self.update_text)
            self.ocr_thread.start()

    def update_text(self,in_txt):
        self.insertPlainText('\n' + in_txt)

    # ================= 图片插入 / 浮动图 =================
    def _init_image_support(self):
        self._floats = []                    # 每项 {uri,x,y,w,h,mode}
        self._float_widgets = []             # 仅 above 模式有控件
        self._cleaning_frames = False        # 防 contentsChanged 重入
        self._has_float_frames = False       # 文档是否存在浮动帧（快速跳过整棵遍历）
        self._clean_timer = QTimer(self)     # 防抖：连续打字时不反复遍历帧树
        self._clean_timer.setSingleShot(True)
        self._clean_timer.setInterval(250)
        self._clean_timer.timeout.connect(self._do_clean_empty_wrap_frames)
        self.verticalScrollBar().valueChanged.connect(self._sync_floats)
        self.viewport().installEventFilter(self)
        self.document().contentsChanged.connect(self._on_contents_changed_for_clean)

    def eventFilter(self, obj, event):
        """「衬于文字下方」的图必须在 QTextEdit 画文字之前画进 viewport。

        paintEvent 里画会盖住文字；这里抢在事件派发前画完，QTextEdit 随后把
        文字画在上面，于是文字真的压在图片上（与 Word 的衬于文字下方一致）。
        """
        if obj is self.viewport() and event.type() == QEvent.Paint:
            if any(f.get('mode') == 'behind' for f in self._floats):
                self._paint_behind_images()
        return super().eventFilter(obj, event)

    def _paint_behind_images(self):
        painter = QPainter(self.viewport())
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        for info in self._floats:
            if info.get('mode') != 'behind':
                continue
            pix = info.get('_pix')
            if pix is None or pix.isNull():
                pix = imgs.load_pixmap(self, info.get('uri', ''))
                info['_pix'] = pix
            if pix.isNull():
                continue
            painter.drawPixmap(self._float_rect(info), pix)
        painter.end()

    def _float_rect(self, info):
        return QRect(int(info['x']),
                     int(info['y'] - self.verticalScrollBar().value()),
                     max(8, int(info['w'])), max(8, int(info['h'])))

    def _on_contents_changed_for_clean(self):
        """contentsChanged 入口：250ms 防抖，连续打字只跑一次。"""
        # 没有浮动帧的文档直接跳过整棵帧树遍历（绝大多数情况）
        if not self._has_float_frames:
            return
        self._clean_timer.start()

    def _do_clean_empty_wrap_frames(self):
        """用户把「四周型环绕」图片删掉后，清掉残留的空浮动帧，避免留下看不见的排版空洞。"""
        if self._cleaning_frames:
            return
        root = self.document().rootFrame()
        to_remove = []
        it = root.begin()
        while not it.atEnd():
            fr = it.currentFrame()
            if fr is not None and fr is not root:
                ff = fr.frameFormat()
                if ff.position() in (QTextFrameFormat.FloatLeft,
                                     QTextFrameFormat.FloatRight):
                    blk = fr.firstCursorPosition().block()
                    # 帧内首个块若只剩块分隔符（图片/文字都被删光）即视为空帧
                    if blk.length() <= 1:
                        to_remove.append(fr)
            it += 1
        if to_remove:
            self._cleaning_frames = True
            try:
                max_pos = self.document().characterCount()
                for fr in to_remove:
                    c = QTextCursor(self.document())
                    c.setPosition(fr.firstPosition())
                    hi = fr.lastPosition() + 1
                    if hi > max_pos:
                        hi = max_pos
                    c.setPosition(hi, QTextCursor.KeepAnchor)
                    c.removeSelectedText()
            finally:
                self._cleaning_frames = False
            self.document().setModified(True)
            self.viewport().update()
        else:
            # 遍历后没发现浮动帧，标记一次，后续打字完全跳过
            self._has_float_frames = False

    def _behind_floats(self):
        return [f for f in self._floats if f.get('mode') == 'behind']

    # ---- 浮动图几何 / 状态 ----
    def _move_float(self, info, vx, vy):
        vp = self.viewport()
        w = int(info['w'])
        vx = max(-w // 3, min(int(vx), vp.width() - w // 3))
        info['x'] = int(vx)
        info['y'] = int(max(0, vy + self.verticalScrollBar().value()))

    def _resize_float(self, info, w, h):
        w = max(32, min(int(w), max(64, self.viewport().width())))
        info['w'] = int(w)
        info['h'] = max(24, int(h))

    def _reset_float_size(self, info, pix=None, widget=None):
        if pix is None or (hasattr(pix, 'isNull') and pix.isNull()):
            pix = imgs.load_pixmap(self, info.get('uri', ''))
        if pix.isNull():
            return
        w, h = imgs.fit_size(pix.width(), pix.height(),
                             int(max(120, self.viewport().width() * 0.6)))
        info['w'], info['h'] = w, h
        if widget is not None:
            widget._pix = pix
            widget._apply_geometry()
        self._sync_floats()
        self._persist_floats()

    def change_float_mode(self, info, mode):
        if info.get('mode') == mode:
            return
        info['mode'] = mode
        if mode == 'above':
            self._make_float_widget(info)
        else:
            self._drop_float_widget(info)
            self.viewport().update()
        self._persist_floats()

    def embed_float(self, info):
        """浮动图转成正文里的嵌入型图片。"""
        pix = info.get('_pix') or imgs.load_pixmap(self, info.get('uri', ''))
        if pix is None or pix.isNull():
            return
        self._insert_inline_image(pix.toImage(), QUrl(info.get('uri', '')).toLocalFile(),
                                  width=int(info['w']), height=int(info['h']))
        self.remove_float(info)

    def remove_float(self, info):
        self._drop_float_widget(info)
        try:
            self._floats.remove(info)
        except ValueError:
            pass
        self.viewport().update()
        self._persist_floats()

    def float_menu(self, info, widget, global_pos):
        return imgs.build_float_menu(self, info, widget, global_pos)

    def _make_float_widget(self, info):
        for w in self._float_widgets:
            if w.info is info:
                w._apply_geometry()
                w.show()
                w.raise_()
                return w
        w = imgs.FloatImage(self, info)
        self._float_widgets.append(w)
        w.show()
        w.raise_()
        return w

    def _drop_float_widget(self, info):
        keep = []
        for w in self._float_widgets:
            if w.info is info:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            else:
                keep.append(w)
        self._float_widgets = keep

    def _sync_floats(self):
        for w in list(self._float_widgets):
            try:
                w._apply_geometry()
            except RuntimeError:
                pass
        if self._behind_floats():
            self.viewport().update()

    def floats_payload(self):
        """给 draft_store 的纯数据版本（去掉 _pix 之类的运行时字段）。"""
        out = []
        for info in self._floats:
            out.append(dict((k, info[k]) for k in ('uri', 'x', 'y', 'w', 'h', 'mode')
                            if k in info))
        return out

    def load_floats(self, data):
        for w in list(self._float_widgets):
            w.hide()
            w.setParent(None)
            w.deleteLater()
        self._float_widgets = []
        self._floats = []
        for item in (data or []):
            if not isinstance(item, dict) or not item.get('uri'):
                continue
            info = {'uri': item.get('uri'),
                    'x': int(item.get('x', 24)), 'y': int(item.get('y', 24)),
                    'w': int(item.get('w', 240)), 'h': int(item.get('h', 180)),
                    'mode': item.get('mode', 'above')}
            self._floats.append(info)
            if info['mode'] == 'above':
                self._make_float_widget(info)
        self.viewport().update()

    def _persist_floats(self):
        win = self.window()
        fn = getattr(win, '_persist_all_floats', None)
        if fn is None:
            return
        try:
            fn()
        except Exception as e:
            print('Error Code 434', e)

    # ---- 插入入口 ----
    def insert_picture(self, path=None):
        """插入图片（文件对话框），按 image_insert_mode 决定嵌入 / 四周型环绕 / 浮动。"""
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, '插入图片', '', imgs.IMAGE_FILTER)
        if not path or not os.path.isfile(path):
            return False
        try:
            dst, img = imgs.import_image(path)
        except Exception as e:
            print('Error Code 435', e)
            return False
        self.insert_image_object(img, dst)
        return True

    def insert_image_object(self, img, path, mode=None):
        mode = mode or getattr(self, 'image_insert_mode', 'inline')
        if mode == 'inline':
            self._insert_inline_image(img, path)
        elif imgs.is_wrap_mode(mode):
            self._insert_wrap_image(img, path,
                                   'left' if mode == 'wrap_left' else 'right')
        else:
            self._add_floating_image(img, path, mode)
        return True

    def _insert_inline_image(self, img, path, width=None, height=None):
        uri = imgs.image_uri(path) if path else ''
        if not uri:
            return
        self.document().addResource(QTextDocument.ImageResource, QUrl(uri), img)
        if width and height:
            w, h = int(width), int(height)
        else:
            w, h = imgs.fit_size(img.width(), img.height(),
                                 max(160, self.viewport().width() - 60))
        fmt = QTextImageFormat()
        fmt.setName(uri)
        fmt.setWidth(w)
        fmt.setHeight(h)
        cur = self.textCursor()
        cur.insertImage(fmt)
        self.setTextCursor(cur)
        self.document().setModified(True)
        self.viewport().update()

    def _insert_wrap_image(self, img, path, align='right', width=None, height=None):
        """四周型环绕：把图片放进「浮动帧」，正文文字绕其矩形排布（类 Word 四周型）。

        用 QTextFrame + FloatLeft/FloatRight 让后面的文字在图片旁边收窄、图片下方恢复
        整行宽度。图片本身仍是文档内容（addResource + 帧内 QTextImageFormat），随 HTML
        存档；插入后光标移回正文流，避免后续输入被塞进帧里。
        """
        uri = imgs.image_uri(path) if path else ''
        if not uri:
            return
        self.document().addResource(QTextDocument.ImageResource, QUrl(uri), img)
        if width and height:
            w, h = int(width), int(height)
        else:
            w, h = imgs.fit_size(img.width(), img.height(),
                                 max(160, int(self.viewport().width() * 0.45)))
        cur = self.textCursor()
        ff = QTextFrameFormat()
        if align == 'left':
            ff.setPosition(QTextFrameFormat.FloatLeft)
        else:
            ff.setPosition(QTextFrameFormat.FloatRight)
        ff.setWidth(w)
        ff.setHeight(h)
        ff.setPadding(0)
        ff.setMargin(6)                            # 图文间距
        ff.setBorder(0)
        frame = cur.insertFrame(ff)
        self._has_float_frames = True   # 标记文档含浮动帧，后续才做空帧清理
        ifmt = QTextImageFormat()
        ifmt.setName(uri)
        ifmt.setWidth(w)
        ifmt.setHeight(h)
        cur.insertImage(ifmt)
        # 把光标送回帧之后的正文流（用帧尾位置 + NextBlock 才能跳出帧外）
        after = QTextCursor(self.document())
        after.setPosition(frame.lastPosition())
        if not after.movePosition(QTextCursor.NextBlock):
            after.insertBlock()
        if frame.firstPosition() <= after.position() <= frame.lastPosition():
            after.insertBlock()
        self.setTextCursor(after)
        self.document().setModified(True)
        self.viewport().update()

    def _add_floating_image(self, img, path, mode):
        vp = self.viewport()
        w, h = imgs.fit_size(img.width(), img.height(),
                             int(max(160, vp.width() * 0.7)))
        rect = self.cursorRect()
        info = {'uri': imgs.image_uri(path),
                'x': max(0, int((vp.width() - w) / 2)),
                'y': max(0, int(rect.y() + self.verticalScrollBar().value())),
                'w': w, 'h': h, 'mode': mode,
                '_pix': QPixmap.fromImage(img)}
        self._floats.append(info)
        if mode == 'above':
            self._make_float_widget(info)
        else:
            self.viewport().update()
        self.document().setModified(True)
        self._persist_floats()

    # ---- 粘贴 / 拖放 ----
    def canInsertFromMimeData(self, source):
        if source.hasImage():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        """Ctrl+V 截图：把剪贴板图片按当前环绕方式插入，不进正文纯文本。"""
        if source.hasImage():
            img = QImage(source.imageData())
            if not img.isNull():
                try:
                    path = imgs.save_image_object(img)
                except Exception as e:
                    print('Error Code 436', e)
                    return
                self.insert_image_object(img, path)
                return
        super().insertFromMimeData(source)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self._sync_floats()
        except Exception:
            pass

version = '3.5.16'
line_height = 0.5


# qdarkstyle 里所有 QMainWindow::separator 规则（含 :hover / :horizontal / :vertical）。
# 它们的 width/height:5px + padding:2px + image 图标决定停靠区布局间隙，且实测无法
# 被后追加的同名选择器覆盖，必须在拼接 APP_QSS 之前整段剔除。
_RE_QDARK_SEPARATOR = re.compile(r'QMainWindow::separator[^{}]*\{[^{}]*\}', re.S)
# qdarkstyle 的 QDockWidget::title 把停靠面板标题栏画成浅蓝灰 #455364。
# 与 separator 同样：同名 subcontrol 规则只有首次出现的生效，后追加的
# background / background-color / !important 都无法覆盖，必须整段剔除。
_RE_QDARK_DOCK_TITLE = re.compile(r'QDockWidget::title\s*\{[^{}]*\}', re.S)
# qdarkstyle 的 QDockWidget 主规则给整个停靠面板画了一圈浅灰蓝 #455364
# 外框 / outline（dock 浮动成独立窗口时可见）。压暗到主题边框色，
# 保留块内其余声明（背景色、标题栏按钮图标资源等）。
# 注意：停靠时标题栏上沿另有一条 2px 的 #455364，那是 RIBBON_QSS 里
# QMainWindow::separator 分隔条（上一轮定为 2px 可拖动），不属于本规则。
_RE_QDARK_DOCK_MAIN = re.compile(r'QDockWidget\s*\{[^{}]*\}', re.S)


def _dim_qdark_dock_border(match):
    return match.group(0).replace('#455364', '#2c3744')


def _load_app_stylesheet():
    """加载 qdarkstyle 样式表并把结果缓存到临时目录。

    load_stylesheet 每次都要重新拼装 5 万余字符的 QSS，冷启动约 55~300 ms。
    缓存命中时直接读文件，连 qdarkstyle 都不必导入（再省约 66 ms）。
    缓存首行额外保存 QPalette.Link 颜色：qdarkstyle.load_stylesheet 会顺带
    把链接色改成强调色，命中路径需手动补上，避免首次/后续启动外观不一致。
    """
    import tempfile
    import hashlib
    from PyQt5.QtCore import PYQT_VERSION_STR
    from PyQt5.QtGui import QColor, QPalette
    from PyQt5.QtWidgets import QApplication
    # 不用 importlib.metadata 探测版本：它首次导入约 150 ms，比缓存省下的还多。
    # 应用版本升级即换缓存；单独升级 qdarkstyle 时删除临时目录的 fenrir_qss_*.qss 即可。
    # 同时把本文件里的 QSS 内容纳入缓存键：否则改了 APP_QSS/RIBBON_QSS 却因键没变
    # 仍命中旧缓存，源码改动对运行实例完全不生效（排查过的坑）。
    _qss_sig = hashlib.md5((RIBBON_QSS + APP_QSS).encode('utf-8')).hexdigest()[:10]
    key = f'fenrir|{version}|pyqt5|{PYQT_VERSION_STR}|{_qss_sig}'
    cache_path = os.path.join(
        tempfile.gettempdir(),
        'fenrir_qss_' + hashlib.md5(key.encode('utf-8')).hexdigest()[:10] + '.qss')
    app = QApplication.instance()
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            link_color, stylesheet = f.read().split('\n', 1)
        if app is not None and link_color.startswith('#'):
            pal = app.palette()
            pal.setColor(QPalette.Normal, QPalette.Link, QColor(link_color))
            app.setPalette(pal)
        # 缓存命中时跳过了 qdarkstyle 导入，但其 QSS 引用的
        # :/qss_icons 资源库（菜单/滚动条箭头图标）必须显式注册。
        import qdarkstyle.dark.darkstyle_rc  # noqa: F401
    except (OSError, ValueError):
        import qdarkstyle
        stylesheet = qdarkstyle.load_stylesheet(qt_api='pyqt5')
        link_color = ''
        if app is not None:
            link_color = app.palette().color(QPalette.Normal, QPalette.Link).name()
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                f.write(link_color + '\n' + stylesheet)
        except OSError:
            pass
    # qdarkstyle 只改样式表、不改 QPalette；qtawesome 默认取 QPalette.Text
    # （Windows 默认是黑色）生成图标，深色界面上几乎看不见。这里统一调亮，
    # QSS 里显式设过 color 的控件不受影响。
    if app is not None:
        pal = app.palette()
        pal.setColor(QPalette.Active, QPalette.Text, QColor('#dbe4ed'))
        pal.setColor(QPalette.Inactive, QPalette.Text, QColor('#dbe4ed'))
        pal.setColor(QPalette.Disabled, QPalette.Text, QColor('#7d8894'))
        app.setPalette(pal)
    # 此时 stylesheet 仍是纯 qdarkstyle 段，剔除后 APP_QSS 里的 2px 定义才生效，
    # 停靠区之间的间隙由 9px 降到 2px。缓存文件保持原始内容，兼容旧缓存。
    stylesheet = _RE_QDARK_SEPARATOR.sub('', stylesheet)
    # 剔除 qdarkstyle 的浅色标题栏规则后，RIBBON_QSS 里的深蓝 #1c3a5c 才会生效
    stylesheet = _RE_QDARK_DOCK_TITLE.sub('', stylesheet)
    stylesheet = _RE_QDARK_DOCK_MAIN.sub(_dim_qdark_dock_border, stylesheet)
    return stylesheet + APP_QSS


# ---------------------------------------------------------------- 单实例
# 用本地 socket 当实例锁：第一个进程监听，后来的进程连得上就说明已有实例，
# 发一条激活消息后直接退出。相比 Windows Mutex / QSharedMemory，进程被强杀时
# 内核会自动回收管道，不会留下一个让程序永远起不来的死锁。
# 环境变量仅用于自动化测试时换一个锁名，避免和用户正在运行的实例冲突；
# 正常启动时始终用同一个固定名字。
_SI_SERVER_NAME = (os.environ.get('FENRIR_SINGLE_INSTANCE_NAME')
                   or 'FenrirV3.5_SingleInstance')


def _notify_existing_instance(name=_SI_SERVER_NAME, timeout=800):
    """已有实例在跑：请求它把窗口调到前台并返回 True；否则返回 False。"""
    from PyQt5.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(timeout):
        sock.abort()
        return False
    sock.write(b'activate')
    sock.waitForBytesWritten(timeout)
    sock.disconnectFromServer()
    return True


def _start_single_instance_server(name=_SI_SERVER_NAME):
    """启动实例锁监听。失败返回 None（降级放行，避免环境异常时锁死程序）。"""
    from PyQt5.QtNetwork import QLocalServer
    # 上次被强杀时 Unix 域会残留 socket 文件；Windows 上这个调用无害。
    QLocalServer.removeServer(name)
    server = QLocalServer()
    if not server.listen(name):
        return None
    return server


def _inform_already_running():
    """第二个实例退出前的轻量提示。

    不用 QMessageBox：离屏 / 缺字体的环境里渲染对话框会直接段错误；
    单实例的核心动作（通知原窗口前置 + 立即退出）不依赖这个提示。
    """
    try:
        sys.stdout.write('本程序已在运行，已将原窗口调至前台。\n')
        sys.stdout.flush()
    except Exception:
        pass


if __name__ == '__main__':
    import traceback as _tb
    _startup_err = None
    try:
        # 隐藏控制台窗口（仅在存在控制台时有效；失败不影响启动）
        try:
            ct = win32api.GetConsoleTitle()
            hd = win32gui.FindWindow(0, ct)
            if hd:
                win32gui.ShowWindow(hd, 0)
        except Exception:
            pass
        app = QApplication(sys.argv)
        # 全局按键音：挂 QApplication 级事件过滤器，所有按钮按下都有一声轻咔哒。
        # 必须在 QApplication 建好之后、任何窗口创建之前装上，覆盖才完整。
        sfx.install_button_sfx(app)

        # 单实例限制：同一时刻最多一个 main.py 实例。第二个进程不加载样式表、
        # 不构造主窗口，通知已有实例把窗口调到前台，提示后立刻退出。
        if _notify_existing_instance():
            _inform_already_running()
            sys.exit(0)
        _si_server = _start_single_instance_server()
        # 竞态兜底：两个进程同时探测失败、其中一个 listen 落败时，再探一次；
        # 连得上说明确实已有实例，退出；仍连不上则是环境限制，降级放行。
        if _si_server is None and _notify_existing_instance():
            _inform_already_running()
            sys.exit(0)
        if _si_server is not None:
            def _raise_existing_window(server=_si_server):
                conn = server.nextPendingConnection()
                if conn is not None:
                    conn.disconnectFromServer()
                    conn.deleteLater()
                win = globals().get('window_main')
                if win is not None:
                    win.showNormal()
                    win.raise_()
                    win.activateWindow()
            _si_server.newConnection.connect(_raise_existing_window)

        app.setStyleSheet(_load_app_stylesheet())
        window_main = MainWindow()
        window_main.show()
        # 设计调整服务延后到首帧显示之后、在后台线程启动：加载 server.py（Pillow）
        # 与首次绑定端口都不占用 UI 线程；用户先点到功能按钮时 ensure_started()
        # 会惰性兜底，两者靠同一把锁保证只启动一次。
        QTimer.singleShot(0, design_service.start_async)
        app.aboutToQuit.connect(design_service.stop)
        app.exec_()
    except Exception as _e:
        _startup_err = _tb.format_exc()
        # 落盘日志，便于排查「启动即闪退、无任何提示」的情况
        try:
            _logp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp', 'startup_error.log')
            os.makedirs(os.path.dirname(_logp), exist_ok=True)
            with open(_logp, 'w', encoding='utf-8') as _lf:
                _lf.write(_startup_err)
        except Exception:
            pass
        # 尽量弹窗提示；若连 Qt 都没起来，则直接打印
        try:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(None, '启动失败', 'main.py 启动失败：\n\n' + str(_e) + '\n\n详细见 temp/startup_error.log')
        except Exception:
            sys.stderr.write(_startup_err)
            sys.stderr.write('\n')

# -*- coding: utf-8 -*-
"""申请人 / 发明人收藏夹的界面（Qt5）。

两个弹窗：
  PartyLibraryDialog  —— 收藏夹浏览：搜索、预览、把某套档案调用回左侧面板；
                         申请人、发明人可分别调用，委托书 JPG 在这里增删查看
  SavePartyDialog     —— 收藏 / 重命名：给档案起个名字（可加备注）

样式沿用 word_features.FenrirDialog（无边框、深色、可拖拽），
数据读写全部交给 party_library。
"""
import os

from PyQt5.QtCore import QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PyQt5.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout,
                             QHeaderView, QLabel, QLayout, QLineEdit,
                             QListWidget, QListWidgetItem, QMenu, QPushButton,
                             QSplitter, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

import party_library as plib
import word_features as wf
from frameless_resizable import FramelessResizableMixin

# 分区小标题统一字号：11px 在 125% 缩放下偏小，整体加 1px
_SECTION_QSS = 'color:#9fb0c0; font-size:12px; background:transparent;'


def _button(text, slot, kind=''):
    b = QPushButton(text)
    b.setObjectName({'primary': 'DialogPrimary', 'danger': 'DialogDanger'}
                    .get(kind, 'DialogButton'))
    b.setCursor(Qt.PointingHandCursor)
    # 三种按钮的 QSS 各自命中不同选择器，宽高靠 QSS 容易走偏，
    # 这里统一钉死尺寸，避免「删除 / 调用全部」比旁边小一圈
    b.setMinimumHeight(28)
    b.setMinimumWidth(92)
    b.clicked.connect(slot)
    return b


def _section_label(text):
    lb = QLabel(text)
    lb.setStyleSheet(_SECTION_QSS)
    lb.setWordWrap(True)
    return lb


def _fill_table(table, rows, headers):
    table.setRowCount(0)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    for row in rows:
        r = table.rowCount()
        table.insertRow(r)
        for c, val in enumerate(row):
            it = QTableWidgetItem(val)
            it.setToolTip(val)
            table.setItem(r, c, it)


class _PaneTable(QTableWidget):
    """只读表：sizeHint 故意给得很小。

    QTableWidget 默认 sizeHint 约 192 高，两张叠起来会把收藏夹窗口的理想高度
    顶到 777；而 Qt 在布局激活时会按 sizeHint 撑开顶层窗口，用户把窗口拖矮后
    一松手又被弹回去，表现成「高度调不动」。这里声明「理想就一行」，实际高度
    完全交给布局 stretch 和用户拖拽。
    """

    def sizeHint(self):
        return QSize(320, 60)


def _readonly_table(headers, widths=None):
    t = _PaneTable(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.NoSelection)
    t.setFocusPolicy(Qt.NoFocus)
    t.setWordWrap(False)
    t.setAlternatingRowColors(False)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    for c in range(1, len(headers)):
        t.horizontalHeader().setSectionResizeMode(c, QHeaderView.Interactive)
    for c, w in (widths or {}).items():
        t.setColumnWidth(c, w)
    t.setMinimumHeight(70)
    return t


# ---------------- 谁拉伸、谁固定 ----------------
# 申请人 / 发明人两张表是主要阅读区：给一个「表头 + 两行」的下限，剩下的高度
# 按 stretch 比例在两张表之间分配，窗口拉高它们就跟着长、拉矮就缩到下限后滚动。
# 委托书列表反过来——固定高度（按张数算），窗口再高也不跟着变。
_TABLE_ROW_H = 30       # 单行高度（实测 12px 字号下 QTableWidget 默认行高）
_TABLE_MIN_ROWS = 1     # 最少露一行：窗口压到很低时表格还能再让出空间
_TABLE_STRETCH = (4, 5)  # 申请人 : 发明人的拉伸比例（发明人一般人多，略高）
_POA_MIN_H = 48         # 委托书列表为空时的高度：够放下拖拽提示
_POA_ROW_H = 48         # 每张缩略图（30×40 图标 + 上下留白）
_POA_MAX_H = 156        # 三张以上就滚动
_NO_MAX = 16777215      # QWIDGETSIZE_MAX


def _table_floor(table):
    """给只读表设一个最小高度（表头 + 两行），之后由布局拉伸。

    高度用控件自己的表头 / 行高 / 边框实测值算，写死常数会差几像素，
    最后一行的下沿被裁掉半条。同时清掉可能残留的最大高度限制，
    否则早先按内容定高时设的 fixedHeight 会把它重新钉死。
    """
    row_h = table.rowHeight(0) if table.rowCount() else _TABLE_ROW_H
    head_h = table.horizontalHeader().height() or 26
    h = head_h + _TABLE_MIN_ROWS * row_h + 2 * max(1, table.frameWidth()) + 2
    if table.minimumHeight() != h:
        table.setMinimumHeight(h)
    if table.maximumHeight() != _NO_MAX:
        table.setMaximumHeight(_NO_MAX)


def _fit_poa_list(lst):
    """委托书列表固定高度：空 48px，每多一张加 48px，最多 156px。

    它是「固定尺寸」的那一块：只按张数变，不参与窗口拉伸。
    占位提示项（UserRole 为空）不计数，否则空列表也会被算成一张。
    """
    n = sum(1 for i in range(lst.count()) if lst.item(i).data(Qt.UserRole))
    h = _POA_MIN_H if n <= 0 else min(_POA_MAX_H, 8 + n * _POA_ROW_H)
    if lst.minimumHeight() != h or lst.maximumHeight() != h:
        lst.setFixedHeight(h)


def _poa_icon(path):
    """委托书缩略图（列表图标）；文件缺失或不是图片时返回 None。"""
    if not path or not os.path.isfile(path):
        return None
    pm = QPixmap(path)
    if pm.isNull():
        return None
    return QIcon(pm.scaled(30, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class _PoaDropList(QListWidget):
    """委托书列表：把 JPG / PNG 直接拖进来就能添加（可一次拖多张）。"""

    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setToolTip('把委托书 JPG / PNG 拖到这里即可添加（可多张）；'
                        '右键可添加 / 查看 / 删除')

    @staticmethod
    def _paths(event):
        md = event.mimeData()
        if not md or not md.hasUrls():
            return []
        out = []
        for u in md.urls():
            if not u.isLocalFile():
                continue
            p = u.toLocalFile()
            if os.path.splitext(p)[1].lower() in plib.POA_EXTS:
                out.append(p)
        return out

    def dragEnterEvent(self, e):
        if self._paths(e):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if self._paths(e):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        paths = self._paths(e)
        if not paths:
            e.ignore()
            return
        e.acceptProposedAction()
        self.filesDropped.emit(paths)


class PartyLibraryDialog(FramelessResizableMixin, wf.FenrirDialog):
    """收藏夹（独立窗口：可拖动、可缩放、靠近主窗口自动吸附）。

    非模态：双击 / 按钮套用后窗口不关，可以连续给多个文档套用。
    套用请求通过 applyRequested(mode, item) 发给主窗口，由 main.py 写进面板。
    """

    applyRequested = pyqtSignal(str, dict)
    SNAP_DIST = 24          # 靠近主窗口边缘多少像素内吸附
    _last_size = None       # 上次显示时的尺寸（本进程内记忆，隐藏再开不变）

    def __init__(self, parent=None, items=None, modal=False):
        super().__init__(
            parent, title='申请人 / 发明人收藏夹',
            message='双击一条档案即可整套套用到左侧面板；也可以只取申请人或只取发明人。'
                    '窗口可拖动、拖四边缩放，靠近主窗口自动吸附。',
            detail='收藏入口在「申请人信息」面板顶部的「★ 收藏」（可选只收藏申请人或只收藏发明人）。'
                   '委托书 JPG 统一存放在 data/poa/，可直接拖进窗口里的委托书区域，'
                   '或在列表上右键「添加 JPG / 查看 / 删除」；'
                   '调用全部时会随「XML 修改 → 导入所有信息」一起写进 ZIP。',
            kind='info', width=940, position='center', modal=modal)
        # 委托书固定、两张表随窗体拉伸，所以下限放得比内容最小高再低一点：
        # 用户可以把窗口压成「只剩列表 + 一行表格」，需要时再拖高。
        self.setMinimumSize(820, 480)
        # 不约束：默认的 SetDefaultConstraint 会在布局激活时把顶层窗口按
        # sizeHint（这里约 777）重新撑开，用户拖矮后一松手就弹回去，表现成
        # 「高度调不动」。尺寸完全交给用户拖 + 上面的最小尺寸兜底。
        self.layout().setSizeConstraint(QLayout.SetNoConstraint)
        self.action = ''
        self.chosen = None
        self._items = plib.load() if items is None else list(items)

        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        top = QWidget()
        h = QHBoxLayout(top)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText('搜索：档案名 / 申请人 / 发明人 / 备注')
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.textChanged.connect(self._refresh_list)
        self.lb_stat = QLabel('')
        self.lb_stat.setObjectName('DialogHint')
        h.addWidget(self.ed_search, 1)
        h.addWidget(self.lb_stat)
        v.addWidget(top)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        self.list = QListWidget()
        self.list.setMinimumWidth(250)
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(1)
        # 条目用双行小部件渲染（名称 + 摘要），选中态必须由列表自己画，
        # 否则透明的小部件会把高亮盖住、看不出选了哪条
        self.list.setStyleSheet(
            'QListWidget { background:#19232d; border:1px solid #3a4756;'
            ' border-radius:4px; padding:2px; }'
            'QListWidget::item { border-radius:3px; border-left:2px solid transparent; }'
            'QListWidget::item:hover { background:#26333f; }'
            'QListWidget::item:selected { background:#2b3947;'
            ' border-left:2px solid #4a8ae8; }')
        self.list.currentRowChanged.connect(self._show_current)
        self.list.itemDoubleClicked.connect(lambda *_: self._apply('all'))
        split.addWidget(self.list)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(4)
        self.lb_note = QLabel('')
        self.lb_note.setObjectName('DialogHint')
        self.lb_note.setWordWrap(True)
        rv.addWidget(self.lb_note)
        self.lb_app = _section_label('申请人（名称 / 证件号 / 地址 / 邮编）')
        rv.addWidget(self.lb_app)
        self.table_apps = _readonly_table(
            ['名称', '证件号', '地址', '邮编'], {1: 175, 2: 190, 3: 58})
        # 两张表都随窗口拉高：只给最小高度（表头 + 两行），余量按比例分
        rv.addWidget(self.table_apps, _TABLE_STRETCH[0])
        self.lb_inv = _section_label('发明人（姓名 / 身份证号）')
        rv.addWidget(self.lb_inv)
        self.table_invs = _readonly_table(['姓名', '身份证号'], {1: 200})
        rv.addWidget(self.table_invs, _TABLE_STRETCH[1])

        # 委托书：只存 JPG/PNG 扫描件，随「调用全部」一起进 XML
        self.lb_poa = _section_label('委托书（JPG，可多张，可直接拖入，右键添加）')
        rv.addWidget(self.lb_poa)
        self.list_poa = _PoaDropList()
        self.list_poa.setIconSize(QSize(30, 40))
        # 高度随张数走（空着就 48px），别用一个常驻 122px 的空框占着地方
        self.list_poa.setFixedHeight(_POA_MIN_H)
        self.list_poa.setSpacing(0)
        self.list_poa.setStyleSheet(
            'QListWidget { background:#19232d; border:1px solid #3a4756;'
            ' border-radius:4px; padding:2px; font-size:12px; }'
            'QListWidget::item { padding:2px 4px; border-radius:3px; }'
            'QListWidget::item:hover { background:#26333f; }'
            'QListWidget::item:selected { background:#2b3947; color:#ffffff; }')
        self.list_poa.itemDoubleClicked.connect(lambda *_: self._open_poa())
        self.list_poa.filesDropped.connect(self._add_poa_paths)
        # 添加 / 查看 / 删除收进右键菜单：委托书多数时候只用来「存着」，
        # 常驻三个按钮占一行高度，还把小窗口的底栏往上顶。
        self.list_poa.customContextMenuRequested.connect(self._poa_menu)
        rv.addWidget(self.list_poa)
        # 委托书是固定高度（上面 setFixedHeight），这里不能再放弹簧——
        # 余量要全部给上面两张表，窗口拉高时表格跟着长。
        self._right_col = right
        self._split = split
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([270, 600])
        v.addWidget(split, 1)
        self.add_content(body)

        self.btn_all = _button('调用全部', lambda: self._apply('all'), 'primary')
        self.btn_apps = _button('只填申请人', lambda: self._apply('apps'))
        self.btn_invs = _button('只填发明人', lambda: self._apply('invs'))
        self.btn_rename = _button('重命名', self._rename)
        self.btn_del = _button('删除', self._delete, 'danger')
        btn_close = _button('关闭', self.reject)
        # 六个按钮统一尺寸：文字长短不影响宽度，底栏看起来才齐
        for b in (self.btn_rename, self.btn_del, self.btn_invs, self.btn_apps,
                  self.btn_all, btn_close):
            b.setFixedSize(100, 28)
        # 左侧放「管理档案」，右侧放「套用到文档」，关闭永远在最右
        for b in (self.btn_rename, self.btn_del):
            self.button_layout.insertWidget(self.button_layout.count() - 1, b)
        for b in (self.btn_invs, self.btn_apps, self.btn_all, btn_close):
            self.button_layout.addWidget(b)
        self._refresh_list()
        if self.list.count():
            self.list.setCurrentRow(0)
        self.set_hint('共 %d 条档案' % len(self._items))

    # ------------------------------------------------ 列表
    def _refresh_list(self):
        keep = self._current_id()
        self.list.clear()
        items = plib.search(self.ed_search.text(), self._items)
        for it in items:
            row = QListWidgetItem()
            row.setData(Qt.UserRole, it['id'])
            row.setSizeHint(QSize(0, 44))
            row.setToolTip('%s\n%s' % (it.get('name') or '',
                                       plib.summary(it)))
            self.list.addItem(row)
            self.list.setItemWidget(row, self._row_widget(it))
        if not items:
            empty = QListWidgetItem('收藏夹还是空的' if not self._items
                                    else '没有匹配的档案')
            empty.setFlags(Qt.NoItemFlags)
            empty.setSizeHint(QSize(0, 40))
            self.list.addItem(empty)
        self.lb_stat.setText('显示 %d / %d 条' % (len(items), len(self._items))
                             if self.ed_search.text().strip()
                             else '共 %d 条' % len(self._items))
        # 尽量保持原来选中的那条
        if keep:
            for r in range(self.list.count()):
                if self.list.item(r).data(Qt.UserRole) == keep:
                    self.list.setCurrentRow(r)
                    return
        if self.list.count() and not self.list.currentItem():
            self.list.setCurrentRow(0)

    @staticmethod
    def _row_widget(it):
        w = QWidget()
        w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 4, 8, 4)
        v.setSpacing(1)
        name = QLabel(it.get('name') or '未命名')
        name.setStyleSheet('color:#e6ecf2; font-size:12px; font-weight:bold;'
                           'background:transparent;')
        name.setTextFormat(Qt.PlainText)
        sub = QLabel(plib.summary(it))
        sub.setStyleSheet('color:#8fa0b0; font-size:11px; background:transparent;')
        sub.setTextFormat(Qt.PlainText)
        v.addWidget(name)
        v.addWidget(sub)
        return w

    def _current_id(self):
        it = self.list.currentItem() if hasattr(self, 'list') else None
        return it.data(Qt.UserRole) if it is not None else None

    def _current(self):
        cid = self._current_id()
        if not cid:
            return None
        return next((x for x in self._items if x['id'] == cid), None)

    def _show_current(self, *_):
        it = self._current()
        keep_poa = self._poa_selected()     # 重建列表前记下选中的那张
        self.list_poa.clear()
        if not it:
            self.table_apps.setRowCount(0)
            self.table_invs.setRowCount(0)
            _table_floor(self.table_apps)
            _table_floor(self.table_invs)
            _fit_poa_list(self.list_poa)
            self.lb_note.setText('')
            self.lb_app.setText('申请人（名称 / 证件号 / 地址 / 邮编）')
            self.lb_inv.setText('发明人（姓名 / 身份证号）')
            self.lb_poa.setText('委托书（JPG，可多张，可直接拖入，右键添加）')
            for b in (self.btn_all, self.btn_apps, self.btn_invs,
                      self.btn_rename, self.btn_del):
                b.setEnabled(False)
            return
        apps = it.get('applicants') or []
        invs = it.get('inventors') or []
        _fill_table(self.table_apps, apps, ['名称', '证件号', '地址', '邮编'])
        _fill_table(self.table_invs, invs, ['姓名', '身份证号'])
        _table_floor(self.table_apps)
        _table_floor(self.table_invs)
        self.lb_app.setText('申请人（名称 / 证件号 / 地址 / 邮编）'
                            + ('' if apps else '　—　这条档案没有申请人'))
        self.lb_inv.setText('发明人（姓名 / 身份证号）'
                            + ('' if invs else '　—　这条档案没有发明人'))
        poa = it.get('poa') or []
        for e in poa:
            path = plib.poa_path(it['id'], e)
            row = QListWidgetItem('%s · %.0f KB'
                                  % (e.get('name') or e.get('file'),
                                     (e.get('size') or 0) / 1024.0))
            row.setData(Qt.UserRole, e.get('file'))
            row.setToolTip(path or e.get('file') or '')
            icon = _poa_icon(path)
            if icon is not None:
                row.setIcon(icon)
            self.list_poa.addItem(row)
        if not poa:
            # 空态占位：按钮收进右键后，空框不容易看出「可以往里拖/右键」
            tip = QListWidgetItem('　把 JPG 拖到这里，或在此右键「添加 JPG」')
            tip.setFlags(Qt.NoItemFlags)
            tip.setData(Qt.UserRole, None)
            tip.setForeground(QColor('#78889a'))
            self.list_poa.addItem(tip)
        # 重建后把原来选中的那张选回来（右键菜单的「查看 / 删除」靠它判断）
        if keep_poa:
            for r in range(self.list_poa.count()):
                if self.list_poa.item(r).data(Qt.UserRole) == keep_poa:
                    self.list_poa.setCurrentRow(r)
                    break
        _fit_poa_list(self.list_poa)
        self.lb_poa.setText('委托书（JPG，可多张，可直接拖入，右键添加）'
                            + ('　—　%d 张，右键可查看 / 删除，调用全部时一并导入'
                               % len(poa)
                               if poa else '　—　还没有添加 JPG，拖进来或右键添加'))
        bits = []
        if it.get('note'):
            bits.append('备注：' + it['note'])
        if it.get('count'):
            bits.append('已调用 %d 次' % it['count'])
        self.lb_note.setText('　'.join(bits))
        self.btn_all.setEnabled(True)
        self.btn_apps.setEnabled(bool(apps))
        self.btn_invs.setEnabled(bool(invs))
        self.btn_rename.setEnabled(True)
        self.btn_del.setEnabled(True)

    def _poa_menu(self, pos):
        """委托书右键菜单：添加 JPG / 查看 / 删除。

        右键点在某一项上就先把该项选中，让「查看 / 删除」直接作用于它；
        点在空白处也弹菜单，只留「添加 JPG」可用——这样委托书为空时
        仍有入口，不必非去拖文件。
        """
        row = self.list_poa.itemAt(pos)
        if row is not None:
            self.list_poa.setCurrentItem(row)
        menu, acts = self._poa_menu_build()
        got = menu.exec_(self.list_poa.viewport().mapToGlobal(pos))
        self._poa_menu_run(acts, got)

    def _poa_menu_build(self):
        """建菜单（不弹）。拆出来是为了能单独截图/测试菜单项状态。"""
        fname = self._poa_selected()
        m = QMenu(self)
        acts = {'add': m.addAction('＋ 添加 JPG…')}
        acts['add'].setEnabled(self._current() is not None)
        m.addSeparator()
        acts['open'] = m.addAction('查看')
        acts['del'] = m.addAction('删除')
        for k in ('open', 'del'):
            acts[k].setEnabled(bool(fname))
        return m, acts

    def _poa_menu_run(self, acts, chosen):
        if chosen is None:
            return
        if chosen is acts['add']:
            self._add_poa()
        elif chosen is acts['open']:
            self._open_poa()
        elif chosen is acts['del']:
            self._del_poa()

    # ------------------------------------------------ 动作
    def _apply(self, mode):
        it = self._current()
        if not it:
            return
        if mode == 'apps' and not it.get('applicants'):
            self.set_hint('这条档案没有申请人')
            return
        if mode == 'invs' and not it.get('inventors'):
            self.set_hint('这条档案没有发明人')
            return
        self.action = mode
        self.chosen = it
        # 非模态：发给主窗口去写面板，收藏夹本身继续开着，方便连续套用
        self.applyRequested.emit(mode, it)
        self.set_hint('已套用「%s」' % (it.get('name') or ''))

    def showEvent(self, e):
        """首次显示按 960×640，之后沿用用户拖出来的尺寸。

        布局的理想高度（约 777）比默认高，直接在这里 resize 会被 show 流程末尾
        按 sizeHint 调回来，窗口一显示就顶到 777、再想压矮会觉得「高度调不动」。
        所以排到下一轮事件循环再压回默认值。
        """
        super().showEvent(e)
        if getattr(self, '_sized_once', False):
            return
        self._sized_once = True
        size = self._last_size or QSize(960, 640)
        QTimer.singleShot(0, lambda: self.resize(size))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, '_sized_once', False):
            self._last_size = self.size()

    def _align_height_to_target(self):
        """吸附后不跟随主窗口高度：收藏夹的尺寸由用户拖，保持不动。"""
        return

    # ------------------------------------------------ 委托书 JPG
    def _poa_selected(self):
        row = self.list_poa.currentItem() if hasattr(self, 'list_poa') else None
        return row.data(Qt.UserRole) if row is not None else None

    def _add_poa(self):
        if not self._current():
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择委托书 JPG', os.path.expanduser('~'),
            '图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)')
        if paths:
            self._add_poa_paths(paths)

    def _add_poa_paths(self, paths):
        """添加委托书：右键菜单选文件与拖入走同一条路径。"""
        cur = self._current()
        if not cur or not paths:
            return
        before = len(cur.get('poa') or [])
        plib.add_poa(cur['id'], paths)
        self._items = plib.load()
        self._refresh_list()
        self._show_current()
        after = len((self._current() or {}).get('poa') or [])
        added = max(0, after - before)
        # 新增的最后一张自动选中：右键「查看 / 删除」立刻能作用于它
        if added and self.list_poa.count():
            self.list_poa.setCurrentRow(self.list_poa.count() - 1)
        if added < len(paths):
            self.set_hint('已添加 %d 张；%d 张重复、不是图片或过大，已跳过'
                          % (added, len(paths) - added))
        else:
            self.set_hint('已添加 %d 张委托书' % added)

    def _del_poa(self):
        cur, fname = self._current(), self._poa_selected()
        if not cur or not fname:
            return
        code = wf.ask(
            self, '删除委托书',
            '确定删除这张委托书吗？',
            [('删除', 1), ('取消', 0)], kind='warning', width=420,
            detail='只删收藏夹里的这份 JPG，已经导入 ZIP 的不受影响。')
        if code != 1:
            return
        plib.remove_poa(cur['id'], fname)
        self._items = plib.load()
        self._refresh_list()
        self._show_current()
        self.set_hint('已删除委托书')

    def _open_poa(self):
        cur, fname = self._current(), self._poa_selected()
        if not cur or not fname:
            return
        path = plib.poa_path(cur['id'], fname)
        if not os.path.isfile(path):
            self.set_hint('文件已不存在：%s' % (path or fname))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _rename(self):
        it = self._current()
        if not it:
            return
        dlg = SavePartyDialog(self, mode='rename', name=it.get('name') or '',
                              note=it.get('note') or '')
        if dlg.exec_() != dlg.Accepted:
            return
        plib.update(it['id'], name=dlg.name, note=dlg.note)
        self._items = plib.load()
        self._refresh_list()
        self.set_hint('已重命名为「%s」' % dlg.name)

    def _delete(self):
        it = self._current()
        if not it:
            return
        code = wf.ask(self, '删除档案',
                      '确定删除「%s」？' % (it.get('name') or ''),
                      [('删除', 1), ('取消', 0)], kind='warning',
                      detail='只删收藏夹里的这一条，当前文档面板里的信息不受影响。')
        if code != 1:
            return
        plib.delete(it['id'])
        self._items = plib.load()
        self._refresh_list()
        self.set_hint('已删除')

    def refresh_after_external_change(self):
        self._items = plib.load()
        self._refresh_list()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and \
                self.focusWidget() is not self.ed_search:
            self._apply('all')
            return
        super().keyPressEvent(e)


class SavePartyDialog(wf.FenrirDialog):
    """收藏 / 重命名：起名字（默认取第一申请人），可加备注。

    only='all' / 'apps' / 'invs' 对应「整套收藏 / 只收藏申请人 / 只收藏发明人」，
    只影响提示文案，真正的合并规则在 party_library.upsert。
    """

    def __init__(self, parent=None, mode='save', name='', note='', info=None,
                 only='all'):
        title = '收藏到收藏夹' if mode == 'save' else '重命名档案'
        super().__init__(
            parent, title=title,
            message=('给这套信息起个名字，下次在收藏夹里双击就能整套套用。'
                     if mode == 'save' else '修改档案名称（不影响已套用的文档）。'),
            kind='info', width=460)
        self.name = ''
        self.note = ''
        self.only = only
        self._mode = mode
        self._info = info or {}

        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(8)

        self.ed_name = QLineEdit(name)
        self.ed_name.setPlaceholderText('例如：远大铝业 / 沈阳科威 / 张三')
        self.ed_name.selectAll()
        v.addWidget(self.ed_name)

        self.ed_note = QLineEdit(note)
        self.ed_note.setPlaceholderText('备注（可留空）：例如 2026 年老客户')
        v.addWidget(self.ed_note)

        self.lb_info = QLabel('')
        self.lb_info.setObjectName('DialogHint')
        self.lb_info.setWordWrap(True)
        v.addWidget(self.lb_info)
        self.add_content(body)

        btn_ok = _button('保存', self._ok, 'primary')
        btn_cancel = _button('取消', self.reject)
        btn_ok.setFixedSize(100, 28)
        btn_cancel.setFixedSize(100, 28)
        self.button_layout.addWidget(btn_ok)
        self.button_layout.addWidget(btn_cancel)

        if mode == 'save':
            apps, invs = plib.normalize(self._info)
            bits = []
            if apps and only in ('all', 'apps'):
                names = '、'.join(a[0] for a in apps if a[0]) or '（未命名）'
                bits.append('申请人 %d 个：%s' % (len(apps), names))
            if invs and only in ('all', 'invs'):
                names = '、'.join(i[0] for i in invs if i[0]) or '（未命名）'
                bits.append('发明人 %d 人：%s' % (len(invs), names))
            head = {'apps': '只保存申请人（发明人保留原样）：',
                    'invs': '只保存发明人（申请人保留原样）：'}.get(
                        only, '将保存：')
            self.lb_info.setText(head + ('；'.join(bits) or '空档案'))
        else:
            self.lb_info.setText('')
        self.ed_name.returnPressed.connect(self._ok)

    def _ok(self):
        name = (self.ed_name.text() or '').strip()
        if not name:
            self.set_hint('名称不能为空')
            self.ed_name.setFocus()
            return
        self.name = name
        self.note = (self.ed_note.text() or '').strip()
        self.accept()

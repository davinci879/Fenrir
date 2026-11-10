# -*- coding: utf-8 -*-
"""
Fenrir 的 Word 2019 风格 UI 组件（可复用、可单独测试）。

包含：
  FenrirDialog      统一外观的无边框弹窗基类（标题栏 / 图标 / 按钮区）
  ask               快速确认弹窗（保存 / 不保存 / 取消一类的多按钮场景）
  notice            快速提示弹窗
  WordCountDialog   字数统计
  SaveAsDialog      另存为（文件名 / 位置 / 文件类型 / 导出选项）
  FindReplaceDialog 查找和替换（非模态，使用 ExtraSelections 无损高亮）
  GoToDialog        定位到指定行
  WordStatusBar     状态栏（文档名 / 消息 / 行列 / 字数 / 保存状态 / 缩放）

设计原则：只依赖 PyQt5，不反向依赖 main.py；main.py 通过回调把「当前编辑器」
交给查找替换面板，避免两个模块互相 import。
"""
import os
import re
from PyQt5.QtWidgets import (
    QDialog, QWidget, QLabel, QPushButton, QToolButton, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QComboBox, QCheckBox, QTabWidget, QFrame, QStatusBar,
    QSlider, QSizePolicy, QApplication, QGroupBox, QTextEdit,
)
from PyQt5.QtGui import QFont, QTextCursor, QTextCharFormat, QColor, QTextDocument
from PyQt5.QtCore import (Qt, QTimer, QSettings, pyqtSignal, QSize,
                          QPropertyAnimation, QEasingCurve, pyqtProperty)


DIALOG_QSS = """
QDialog#FenrirDialog {
    background: #202b36; color: #e6ecf2;
    border: 1px solid #45566a; border-radius: 6px;
}
/* 应用级 qdarkstyle 会给 QLabel 刷 #19232d 底色，弹窗内一律透明 */
QDialog#FenrirDialog QLabel { background: transparent; border: none; }
/* 标题栏 / 正文 / 按钮区统一底色，避免内部出现深浅不一的色块 */
QWidget#DialogTitleBar {
    background: #202b36; border: none; border-bottom: 1px solid #33414f;
    border-top-left-radius: 5px; border-top-right-radius: 5px;
}
QWidget#DialogBody { background: #202b36; }
QWidget#DialogButtonBar { background: #202b36; border: none; }
QLabel#DialogTitle { background: transparent; color: #f2f6fa; font-size: 13px; font-weight: bold; }
QLabel#DialogBadge { font-size: 15px; font-weight: bold; border-radius: 12px; }
QToolButton#DialogClose {
    background: transparent; border: none; color: #9fb0c0; font-size: 15px;
    min-width: 30px; max-width: 30px; min-height: 26px; max-height: 26px;
}
QToolButton#DialogClose:hover { background: #c0392b; color: #ffffff; border-radius: 3px; }
QLabel#DialogMessage { background: transparent; color: #e6ecf2; font-size: 13px; }
QLabel#DialogDetail { background: transparent; color: #9fb0c0; font-size: 12px; }
QFrame#DialogSeparator { color: #3a4756; background: #3a4756; border: none; max-height: 1px; }
QPushButton#DialogButton {
    min-width: 88px; padding: 6px 14px; border: 1px solid #4a5b70;
    border-radius: 3px; background: #2b3947; color: #e6ecf2; font-size: 12px;
}
QPushButton#DialogButton:hover { background: #34507a; border-color: #6b95e0; }
QPushButton#DialogPrimary {
    background: #2f6bc4; border-color: #4a8ae8; color: #ffffff; font-weight: bold;
}
QPushButton#DialogPrimary:hover { background: #3a7fdd; }
QPushButton#DialogDanger { background: #9d3b30; border-color: #c35a4b; color: #ffffff; }
QPushButton#DialogDanger:hover { background: #bb483a; }
QDialog#FenrirDialog QLineEdit, QDialog#FenrirDialog QComboBox,
QDialog#FenrirDialog QTextEdit, QDialog#FenrirDialog QSpinBox {
    background: #19232d; color: #e6ecf2; border: 1px solid #45566a;
    border-radius: 3px; padding: 4px 6px; font-size: 12px; selection-background-color: #2f6bc4;
}
QDialog#FenrirDialog QLineEdit:focus, QDialog#FenrirDialog QComboBox:focus { border-color: #4a8ae8; }
QDialog#FenrirDialog QComboBox QAbstractItemView {
    background: #19232d; color: #e6ecf2; selection-background-color: #2f6bc4;
    border: 1px solid #45566a;
}
QDialog#FenrirDialog QCheckBox { color: #d7dee6; font-size: 12px; spacing: 6px; }
QDialog#FenrirDialog QCheckBox::indicator { width: 14px; height: 14px; }
QDialog#FenrirDialog QGroupBox {
    color: #c6d3df; font-size: 12px; border: 1px solid #3a4756;
    border-radius: 3px; margin-top: 12px; padding-top: 8px;
}
QDialog#FenrirDialog QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QDialog#FenrirDialog QTabWidget::pane { border: 1px solid #3a4756; background: #202b36; }
QDialog#FenrirDialog QTabBar::tab {
    background: #26333f; color: #b7c4d0; padding: 5px 16px; border: none;
}
QDialog#FenrirDialog QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #4a8ae8; }
QLabel#StatValue { color: #ffffff; font-size: 12px; font-weight: bold; }
QLabel#StatLabel { color: #a9b7c4; font-size: 12px; }
QLabel#DialogHint { background: transparent; color: #8fa0b0; font-size: 11px; }
QLabel#DialogResult { background: transparent; color: #7fc4ff; font-size: 12px; }
"""


STATUS_QSS = """
QStatusBar#WordStatusBar {
    background: #1e2933; border: none; border-top: 1px solid #3a4756;
    min-height: 27px; max-height: 27px;
}
QStatusBar#WordStatusBar QLabel { color: #dce5ee; font-size: 12px; background: transparent; }
QStatusBar#WordStatusBar QLabel#StatusDoc { color: #ffffff; font-weight: bold; padding-left: 8px; }
QStatusBar#WordStatusBar QLabel#StatusMessage { color: #cbd8e4; padding-left: 10px; }
QStatusBar#WordStatusBar QLabel#StatusSaved { color: #a8e0b4; padding-right: 4px; }
QStatusBar#WordStatusBar QLabel#StatusDirty { color: #ffd28a; padding-right: 4px; }
QPushButton#StatusButton {
    background: transparent; border: none; border-radius: 3px; color: #dce5ee;
    font-size: 12px; padding: 2px 8px; min-height: 20px;
}
QPushButton#StatusButton:hover { background: #2b3947; color: #ffffff; }
QToolButton#StatusZoom {
    background: transparent; border: none; color: #dce5ee; font-size: 13px;
    min-width: 20px; max-width: 20px; min-height: 20px;
}
QToolButton#StatusZoom:hover { background: #5b6d80; border-radius: 3px; }
QSlider#StatusZoom { background: transparent; border: none; }
QSlider#StatusZoom::groove:horizontal { height: 3px; background: #5b6d80; border: none; border-radius: 1px; }
QSlider#StatusZoom::handle:horizontal {
    width: 9px; height: 14px; margin: -6px 0; border-radius: 2px;
    background: #e6ecf2; border: 1px solid #ffffff;
}
QSlider#StatusZoom::sub-page:horizontal { background: #7fb0f0; }
"""


class _TitleBar(QWidget):
    """可拖拽的无边框弹窗标题栏。"""

    def __init__(self, dialog, title, badge):
        super().__init__(dialog)
        self.setObjectName('DialogTitleBar')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(38)
        self._dialog = dialog
        self._drag_pos = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(8)
        if badge:
            glyph, color = badge if isinstance(badge, tuple) else (badge, '#4a8ae8')
            lb = QLabel(glyph)
            lb.setObjectName('DialogBadge')
            lb.setFixedSize(24, 24)
            lb.setAlignment(Qt.AlignCenter)
            lb.setStyleSheet(
                'background: %s; color: #101820; border-radius: 12px;' % color)
            lay.addWidget(lb)
        t = QLabel(title)
        t.setObjectName('DialogTitle')
        lay.addWidget(t)
        lay.addStretch(1)
        close = QToolButton()
        close.setObjectName('DialogClose')
        close.setText('✕')
        close.setToolTip('关闭 (Esc)')
        close.clicked.connect(dialog.reject)
        lay.addWidget(close)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self._dialog.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self._dialog.move(e.globalPos() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None


_BADGES = {
    'question': ('?', '#e0a83b'),
    'warning': ('!', '#d9823b'),
    'critical': ('!', '#c0524b'),
    'info': ('i', '#4a8ae8'),
    'success': ('✓', '#4c9c6b'),
}


class FenrirDialog(QDialog):
    """统一风格的弹窗基类。

    buttons 通过 add_button() 手动添加，done(code) 作为结果码返回；
    这样「保存 / 不保存 / 取消」三按钮无需再受 QMessageBox 标准按钮限制。
    """

    def __init__(self, parent=None, title='', message='', detail='', kind='info',
                 width=460, modal=True, position='center'):
        super().__init__(parent)
        self.setObjectName('FenrirDialog')
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(modal)
        self.setMinimumWidth(width)
        self.setStyleSheet(DIALOG_QSS)
        self._position = position
        self._centered = False
        self._default_message = message

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_TitleBar(self, title, _BADGES.get(kind)))

        body = QWidget()
        body.setObjectName('DialogBody')
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(20, 16, 20, 14)
        self.body_layout.setSpacing(10)
        if message:
            lb = QLabel(message)
            lb.setObjectName('DialogMessage')
            lb.setWordWrap(True)
            lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.body_layout.addWidget(lb)
        if detail:
            lb = QLabel(detail)
            lb.setObjectName('DialogDetail')
            lb.setWordWrap(True)
            self.body_layout.addWidget(lb)
        root.addWidget(body, 1)

        sep = QFrame()
        sep.setObjectName('DialogSeparator')
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        bar = QWidget()
        bar.setObjectName('DialogButtonBar')
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(16, 10, 16, 12)
        bar_lay.setSpacing(8)
        self._hint = QLabel('')
        self._hint.setObjectName('DialogHint')
        bar_lay.addWidget(self._hint)
        bar_lay.addStretch(1)
        self.button_layout = bar_lay
        root.addWidget(bar)

    def set_hint(self, text):
        self._hint.setText(text)

    def add_content(self, widget):
        self.body_layout.addWidget(widget)
        return widget

    def add_layout(self, layout):
        self.body_layout.addLayout(layout)
        return layout

    def add_button(self, text, code, primary=False, danger=False):
        b = QPushButton(text)
        if danger:
            b.setObjectName('DialogDanger')
        elif primary:
            b.setObjectName('DialogPrimary')
        else:
            b.setObjectName('DialogButton')
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda checked=False, c=code: self.done(c))
        self.button_layout.addWidget(b)
        return b

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            # 让输入框内的回车交给具体对话框处理，不误触发默认按钮
            if not isinstance(self.focusWidget(), (QTextEdit,)):
                super().keyPressEvent(e)
        else:
            super().keyPressEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        if self._centered:
            return
        self._centered = True
        p = self.parentWidget()
        if p is None:
            return
        g = p.frameGeometry()
        if self._position == 'topright':
            self.move(max(g.right() - self.width() - 24, g.left() + 10),
                      g.top() + 90)
        else:
            self.move(g.center().x() - self.width() // 2,
                      max(g.top() + 60, g.center().y() - self.height() // 2))


def ask(parent, title, message, buttons, detail='', kind='question', width=460):
    """通用确认弹窗。buttons = [(文字, 结果码, 是否主按钮), ...]，返回被点击的结果码。

    Esc / 标题栏 ✕ 返回 buttons 中最后一个「取消」按钮的码（默认 -1）。
    """
    dlg = FenrirDialog(parent, title=title, message=message, detail=detail,
                       kind=kind, width=width)
    cancel_code = -1
    for item in buttons:
        text, code = item[0], item[1]
        primary = item[2] if len(item) > 2 else False
        danger = item[3] if len(item) > 3 else False
        if code in (QDialog.Rejected, -1) or '取消' in text:
            cancel_code = code
        dlg.add_button(text, code, primary=primary, danger=danger)
    result = dlg.exec_()
    return result if result not in (None,) else cancel_code


def notice(parent, title, message, detail='', kind='info', width=440):
    """单按钮提示弹窗（替代 QMessageBox.information / warning / critical）。"""
    dlg = FenrirDialog(parent, title=title, message=message, detail=detail,
                       kind=kind, width=width)
    dlg.add_button('确定', QDialog.Accepted, primary=True)
    return dlg.exec_()


def collect_text_stats(text, selection=''):
    """Word 2019「字数统计」口径的近似实现（中文按字计，西文按单词计）。"""
    text = text or ''
    han = len(re.findall(r'[\u3400-\u9fff]', text))
    latin_words = len(re.findall(r'[A-Za-z0-9_]+(?:[\.\'\-][A-Za-z0-9_]+)*', text))
    paragraphs = len([p for p in text.split('\n') if p.strip()])
    return {
        '字数': han + latin_words,
        '字符数(不计空格)': len(re.sub(r'\s', '', text)),
        '字符数(计空格)': len(text),
        '段落数': paragraphs,
        '行数': text.count('\n') + 1 if text else 0,
        '中文字符': han,
        '非中文单词': latin_words,
        '选中字数': len(selection) if selection else 0,
    }


class WordCountDialog(FenrirDialog):
    def __init__(self, parent, stats):
        super().__init__(parent, title='字数统计', kind='info', width=400)
        group = QGroupBox('统计信息')
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(26)
        form.setVerticalSpacing(7)
        order = ['字数', '选中字数', '字符数(不计空格)', '字符数(计空格)',
                 '段落数', '行数', '中文字符', '非中文单词']
        for key in order:
            value = QLabel(f'{stats.get(key, 0):,}')
            value.setObjectName('StatValue')
            value.setAlignment(Qt.AlignRight)
            label = QLabel(key + '：')
            label.setObjectName('StatLabel')
            form.addRow(label, value)
        self.add_content(group)
        tip = QLabel('提示：单击状态栏的「字数」可随时打开此窗口。')
        tip.setObjectName('DialogHint')
        self.add_content(tip)
        self.add_button('关闭', QDialog.Accepted, primary=True)


class SaveAsDialog(FenrirDialog):
    """Word 2019「另存为」风格的紧凑面板：文件名 + 位置 + 类型 + 选项。"""

    FORMATS = [
        ('HTML 文档 (*.html)', '.html'),
        ('Word 文档 (*.docx)', '.docx'),
        ('纯文本 (*.txt)', '.txt'),
        ('Markdown (*.md)', '.md'),
        ('PDF 文档 (*.pdf)', '.pdf'),
    ]
    SETTINGS_KEY = 'Fenrir/SaveAs'

    def __init__(self, parent, default_name='未命名', default_dir=None,
                 allow_pdf=True):
        super().__init__(parent, title='另存为', kind='info', width=520)
        self._ok = False
        settings = QSettings('Fenrir', 'FenrirV3.5')
        last_dir = settings.value(self.SETTINGS_KEY + '/dir', '')
        self._dir = default_dir or last_dir or os.path.join(
            os.path.expanduser('~'), 'Documents')
        if not os.path.isdir(self._dir):
            self._dir = os.path.expanduser('~')

        self.edit_name = QLineEdit(default_name)
        self.edit_name.setPlaceholderText('输入文件名（无需填写扩展名）')
        self.edit_name.setMinimumHeight(28)
        self.edit_dir = QLineEdit(self._dir)
        self.edit_dir.setMinimumHeight(28)

        self.combo_format = QComboBox()
        for label, ext in self.FORMATS:
            if ext == '.pdf' and not allow_pdf:
                continue
            self.combo_format.addItem(label, ext)
        last_ext = settings.value(self.SETTINGS_KEY + '/format', '.html')
        for i in range(self.combo_format.count()):
            if self.combo_format.itemData(i) == last_ext:
                self.combo_format.setCurrentIndex(i)
                break
        self.combo_format.currentIndexChanged.connect(self._sync_extension)

        browse = QPushButton('浏览(B)…')
        browse.setObjectName('DialogButton')
        browse.setFixedWidth(88)
        browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        dir_row.addWidget(self.edit_dir, 1)
        dir_row.addWidget(browse)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.addRow('文件名(N)：', self.edit_name)
        form.addRow('保存类型(T)：', self.combo_format)
        form.addRow('保存位置：', dir_row)
        self.add_layout(form)

        self.chk_marks = QCheckBox('同时导出该文档的附图标记列表（同名 .marks.txt）')
        self.chk_all = QCheckBox('导出全部文档（每个文档一个文件）')
        self.chk_open = QCheckBox('保存后打开所在文件夹')
        self.chk_open.setChecked(False)
        self.add_content(self.chk_marks)
        self.add_content(self.chk_all)
        self.add_content(self.chk_open)

        self.hint = QLabel('')
        self.hint.setObjectName('DialogResult')
        self.add_content(self.hint)
        self.set_hint('提示：HTML 保留全部格式，docx / txt / md 导出纯文本。')

        self.add_button('保存(S)', QDialog.Accepted, primary=True)
        self.add_button('取消', QDialog.Rejected)
        self.edit_name.setFocus()
        self.edit_name.selectAll()
        self.combo_format.currentIndexChanged.connect(
            lambda: self.hint.setText(''))

    def _sync_extension(self):
        # 仅更新提示，不改用户已输入的文件名（避免打断中文输入法）
        self.hint.setText('')

    def _browse(self):
        from PyQt5.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, '选择保存位置', self.edit_dir.text())
        if d:
            self.edit_dir.setText(d)

    def _clean_name(self, name):
        name = re.sub(r'[\\/:*?"<>|]', '_', name).strip().strip('.')
        return name or '未命名'

    def target_dir(self):
        return self.edit_dir.text().strip() or os.path.expanduser('~')

    def extension(self):
        return self.combo_format.currentData() or '.html'

    def base_name(self):
        name = self._clean_name(self.edit_name.text())
        low = name.lower()
        for _, ext in self.FORMATS:
            if low.endswith(ext):
                return name[:-len(ext)]
        return name

    def target_path(self):
        return os.path.join(self.target_dir(), self.base_name() + self.extension())

    def options(self):
        return {
            'marks': self.chk_marks.isChecked(),
            'all': self.chk_all.isChecked(),
            'open_dir': self.chk_open.isChecked(),
            'format': self.extension(),
        }

    def done(self, code):
        if code == QDialog.Accepted:
            d = self.target_dir()
            if not os.path.isdir(d):
                notice(self, '无法保存', '保存位置不存在，请重新选择。',
                       detail=d, kind='warning', width=400)
                return
            path = self.target_path()
            if not self.options()['all'] and os.path.exists(path):
                r = ask(self, '确认覆盖',
                        f'文件「{os.path.basename(path)}」已存在，要替换它吗？',
                        [('替换', 1, False, True), ('取消', 0)],
                        detail=path, kind='warning', width=430)
                if r != 1:
                    return
            settings = QSettings('Fenrir', 'FenrirV3.5')
            settings.setValue(self.SETTINGS_KEY + '/dir', d)
            settings.setValue(self.SETTINGS_KEY + '/format', self.extension())
            self._ok = True
        super().done(code)

    def is_accepted(self):
        return self._ok


class FindReplaceDialog(FenrirDialog):
    """非模态查找 / 替换面板；高亮使用 ExtraSelections，不改动文档格式。"""

    HIGHLIGHT = QColor('#b98a20')

    def __init__(self, parent, get_editor, initial_text=''):
        super().__init__(parent, title='查找和替换', kind='info',
                         width=470, modal=False, position='topright')
        self._get_editor = get_editor
        self._editor = None
        self._selections = []

        tabs = QTabWidget()
        self._tabs = tabs
        find_page = QWidget()
        fl = QVBoxLayout(find_page)
        fl.setContentsMargins(12, 14, 12, 12)
        fl.setSpacing(10)
        self.edit_find = QLineEdit(initial_text)
        self.edit_find.setPlaceholderText('输入要查找的内容')
        self.edit_replace = QLineEdit()
        self.edit_replace.setPlaceholderText('替换为（可留空表示删除）')
        ft = QFormLayout()
        ft.setLabelAlignment(Qt.AlignRight)
        ft.setSpacing(10)
        ft.addRow('查找内容(N)：', self.edit_find)
        fl.addLayout(ft)

        row = QHBoxLayout()
        row.setSpacing(6)
        b_prev = QPushButton('上一处')
        b_next = QPushButton('查找下一处')
        b_count = QPushButton('全部高亮')
        for b in (b_prev, b_next, b_count):
            b.setObjectName('DialogButton')
            b.setMinimumWidth(88)
        b_next.setObjectName('DialogPrimary')
        row.addWidget(b_prev)
        row.addWidget(b_next)
        row.addWidget(b_count)
        fl.addLayout(row)

        self.chk_case = QCheckBox('区分大小写')
        self.chk_words = QCheckBox('全词匹配')
        self.chk_loop = QCheckBox('循环查找')
        self.chk_loop.setChecked(True)
        opt = QHBoxLayout()
        opt.setSpacing(14)
        for c in (self.chk_case, self.chk_words, self.chk_loop):
            opt.addWidget(c)
        opt.addStretch(1)
        fl.addLayout(opt)
        fl.addStretch(1)
        tabs.addTab(find_page, '查找')

        rep_page = QWidget()
        rl = QVBoxLayout(rep_page)
        rl.setContentsMargins(12, 14, 12, 12)
        rl.setSpacing(10)
        self.edit_find2 = QLineEdit()
        self.edit_find2.setPlaceholderText('输入要查找的内容')
        rt = QFormLayout()
        rt.setLabelAlignment(Qt.AlignRight)
        rt.setSpacing(10)
        rt.addRow('查找内容(N)：', self.edit_find2)
        rt.addRow('替换为(I)：', self.edit_replace)
        rl.addLayout(rt)
        rrow = QHBoxLayout()
        rrow.setSpacing(6)
        b_rep = QPushButton('替换')
        b_repall = QPushButton('全部替换')
        b_repall.setObjectName('DialogPrimary')
        b_rep.setObjectName('DialogButton')
        b_repall.setObjectName('DialogPrimary')
        rrow.addWidget(b_rep)
        rrow.addWidget(b_repall)
        rrow.addStretch(1)
        rl.addLayout(rrow)
        rl.addStretch(1)
        tabs.addTab(rep_page, '替换')

        # ---- 批量替换页签：左右两栏，每行一对「替换前 => 替换后」 ----
        batch_page = QWidget()
        bl = QVBoxLayout(batch_page)
        bl.setContentsMargins(12, 14, 12, 12)
        bl.setSpacing(8)
        from PyQt5.QtWidgets import QTextEdit
        self.batch_left = QTextEdit()
        self.batch_left.setPlaceholderText('替换前（每行一个）')
        self.batch_right = QTextEdit()
        self.batch_right.setPlaceholderText('替换后（每行一个）')
        brow = QHBoxLayout()
        brow.setSpacing(6)
        brow.addWidget(self.batch_left, 1)
        brow.addWidget(self.batch_right, 1)
        bl.addLayout(brow)
        brow2 = QHBoxLayout()
        brow2.setSpacing(6)
        b_batch = QPushButton('执行批量替换')
        b_batch.setObjectName('DialogPrimary')
        brow2.addWidget(b_batch)
        brow2.addStretch(1)
        bl.addLayout(brow2)
        bl.addStretch(1)
        tabs.addTab(batch_page, '批量替换')
        self._batch_tab_index = 2
        b_batch.clicked.connect(self.batch_replace_all)
        tabs.currentChanged.connect(
            lambda i: (self.edit_find2 if i == 1 else self.batch_left if i == 2 else self.edit_find).setFocus())

        self.add_content(tabs)

        self.result = QLabel('输入关键字后按回车查找')
        self.result.setObjectName('DialogResult')
        self.add_content(self.result)
        self.set_hint('Ctrl+H 打开 · Esc 关闭')
        self.add_button('关闭', QDialog.Rejected)

        # 两个页签的输入框内容双向同步
        self.edit_find.textChanged.connect(self._sync_find_forward)
        self.edit_find2.textChanged.connect(self._sync_find_back)
        self.edit_find.returnPressed.connect(self.find_next)
        self.edit_find2.returnPressed.connect(self.find_next)
        b_prev.clicked.connect(self.find_previous)
        b_next.clicked.connect(self.find_next)
        b_count.clicked.connect(self.highlight_all)
        b_rep.clicked.connect(self.replace_one)
        b_repall.clicked.connect(self.replace_all)
        tabs.currentChanged.connect(
            lambda i: (self.edit_find2 if i else self.edit_find).setFocus())

    def _sync_find_forward(self, text):
        if self.edit_find2.text() != text:
            self.edit_find2.blockSignals(True)
            self.edit_find2.setText(text)
            self.edit_find2.blockSignals(False)
        self.clear_highlight()

    def _sync_find_back(self, text):
        if self.edit_find.text() != text:
            self.edit_find.blockSignals(True)
            self.edit_find.setText(text)
            self.edit_find.blockSignals(False)
        self.clear_highlight()

    def _editor_now(self):
        ed = self._get_editor()
        if ed is not self._editor:
            self.clear_highlight()
            self._editor = ed
        return ed

    @staticmethod
    def _flags(backward=False, case=False, words=False):
        f = QTextDocument.FindFlags()
        if backward:
            f |= QTextDocument.FindBackward
        if case:
            f |= QTextDocument.FindCaseSensitively
        if words:
            f |= QTextDocument.FindWholeWords
        return f

    def _find(self, ed, text, start_cursor, backward=False):
        flags = self._flags(backward, self.chk_case.isChecked(),
                            self.chk_words.isChecked())
        found = ed.document().find(text, start_cursor, flags)
        if found.isNull() and self.chk_loop.isChecked():
            c = QTextCursor(ed.document())
            if backward:
                c.movePosition(QTextCursor.End)
            found = ed.document().find(text, c, flags)
        return found

    def _start_cursor(self, ed, backward=False):
        c = QTextCursor(ed.textCursor())
        if c.hasSelection():
            c.setPosition(c.selectionStart() if not backward else c.selectionEnd())
        return c

    def find_next(self, backward=False):
        ed = self._editor_now()
        text = self.edit_find.text()
        if ed is None or not text:
            self.result.setText('请输入要查找的内容')
            return None
        found = self._find(ed, text, self._start_cursor(ed, backward), backward)
        if found.isNull():
            self.result.setText('未找到「%s」' % text)
            return None
        ed.setTextCursor(found)
        ed.ensureCursorVisible()
        count = self._count(ed, text)
        self.result.setText('找到 %d 个匹配项' % count)
        return found

    def find_previous(self):
        return self.find_next(backward=True)

    def _count(self, ed, text):
        flags = self._flags(case=self.chk_case.isChecked(),
                            words=self.chk_words.isChecked())
        n = 0
        c = QTextCursor(ed.document())
        while n < 5000:
            c = ed.document().find(text, c, flags)
            if c.isNull():
                break
            n += 1
        return n

    def clear_highlight(self):
        if self._editor is not None:
            try:
                self._editor.setExtraSelections([])
            except RuntimeError:
                pass
        self._selections = []

    def highlight_all(self):
        ed = self._editor_now()
        text = self.edit_find.text()
        if ed is None or not text:
            return
        flags = self._flags(case=self.chk_case.isChecked(),
                            words=self.chk_words.isChecked())
        fmt = QTextCharFormat()
        fmt.setBackground(QColor('#8a6a18'))
        fmt.setForeground(QColor('#ffffff'))
        sels = []
        c = QTextCursor(ed.document())
        while len(sels) < 2000:
            c = ed.document().find(text, c, flags)
            if c.isNull():
                break
            sel = QTextEdit.ExtraSelection()
            sel.cursor = c
            sel.format = fmt
            sels.append(sel)
        ed.setExtraSelections(sels)
        self._selections = sels
        self.result.setText('已高亮 %d 个匹配项' % len(sels))

    def replace_one(self):
        ed = self._editor_now()
        text = self.edit_find.text()
        if ed is None or not text:
            return
        cur = ed.textCursor()
        same = (cur.selectedText() == text if self.chk_case.isChecked()
                else cur.selectedText().lower() == text.lower())
        if same:
            cur.beginEditBlock()
            cur.insertText(self.edit_replace.text())
            cur.endEditBlock()
        self.find_next()

    def replace_all(self):
        ed = self._editor_now()
        text = self.edit_find.text()
        if ed is None or not text:
            return
        flags = self._flags(case=self.chk_case.isChecked(),
                            words=self.chk_words.isChecked())
        cur = QTextCursor(ed.document())
        cur.beginEditBlock()
        n = 0
        while n < 5000:
            cur = ed.document().find(text, cur, flags)
            if cur.isNull():
                break
            cur.insertText(self.edit_replace.text())
            n += 1
        cur.endEditBlock()
        self.clear_highlight()
        self.result.setText('已替换 %d 处' % n)

    def batch_replace_all(self):
        """批量替换：左右两栏每行一对，逐对替换全文。"""
        ed = self._editor_now()
        if ed is None:
            return
        import re as _re
        before = [s for s in self.batch_left.toPlainText().strip().split('\n') if s.strip()]
        after = [s for s in self.batch_right.toPlainText().strip().split('\n') if s.strip()]
        if not before or not after:
            self.result.setText('请在左右两栏分别填写替换前/替换后内容')
            return
        if len(before) != len(after):
            self.result.setText('行数不一致：左栏 %d 行，右栏 %d 行' % (len(before), len(after)))
            return
        ed.textCursor().beginEditBlock()
        html = ed.toHtml()
        total = 0
        for b, a in zip(before, after):
            cnt = html.count(b)
            if cnt:
                html = html.replace(b, a)
                total += cnt
        ed.setHtml(html)
        ed.textCursor().endEditBlock()
        self.clear_highlight()
        self.result.setText('批量完成：共替换 %d 处' % total)

    def hideEvent(self, e):
        self.clear_highlight()
        super().hideEvent(e)

    def done(self, code):
        self.clear_highlight()
        super().done(code)


class GoToDialog(FenrirDialog):
    def __init__(self, parent, max_line):
        super().__init__(parent, title='定位', message='输入要跳转到的行号',
                         kind='info', width=380)
        from PyQt5.QtWidgets import QSpinBox
        self.spin = QSpinBox()
        self.spin.setRange(1, max(1, max_line))
        self.spin.setValue(1)
        self.spin.setMinimumHeight(28)
        form = QFormLayout()
        form.addRow('行号(L)：', self.spin)
        self.add_layout(form)
        self.set_hint('共 %d 行' % max(1, max_line))
        self.add_button('定位', QDialog.Accepted, primary=True)
        self.add_button('取消', QDialog.Rejected)

    def line(self):
        return self.spin.value()


class WordStatusBar(QStatusBar):
    """Word 2019 风格状态栏：左侧文档名 + 消息，右侧行列 / 字数 / 保存状态 / 缩放。

    重写 showMessage：传统 QStatusBar 会在显示消息时临时隐藏普通控件，
    这里改为写入专用 QLabel，保证所有指示器常驻可见。
    """

    wordCountClicked = pyqtSignal()
    modeToggled = pyqtSignal(bool)
    zoomResetClicked = pyqtSignal()
    focusToggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('WordStatusBar')
        self.setSizeGripEnabled(False)
        self.setFixedHeight(27)
        self._overwrite = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.lbl_msg.setText('就绪'))

        self.lbl_doc = QLabel('文档1')
        self.lbl_doc.setObjectName('StatusDoc')
        self.lbl_doc.setMinimumWidth(96)
        self.lbl_doc.setMaximumWidth(220)
        self.lbl_doc.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.lbl_msg = QLabel('就绪')
        self.lbl_msg.setObjectName('StatusMessage')
        self.lbl_msg.setMinimumWidth(140)
        self.lbl_msg.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.addWidget(self.lbl_doc)
        self.addWidget(self.lbl_msg, 1)

        self.lbl_pos = QLabel('第 1 行，第 1 列')
        self.lbl_pos.setMinimumWidth(165)
        self.lbl_pos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_pos.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.btn_words = QPushButton('字数 0')
        self.btn_words.setMinimumWidth(110)
        self.btn_words.setObjectName('StatusButton')
        self.btn_words.setCursor(Qt.PointingHandCursor)
        self.btn_words.setToolTip('单击查看字数统计（Word 2019 风格）')
        self.btn_words.clicked.connect(self.wordCountClicked.emit)
        self.lbl_saved = QLabel('已保存')
        self.lbl_saved.setObjectName('StatusSaved')
        self.lbl_saved.setMinimumWidth(66)
        self.lbl_saved.setAlignment(Qt.AlignCenter)
        self.lbl_saved.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.btn_mode = QPushButton('插入')
        self.btn_mode.setMinimumWidth(48)
        self.btn_mode.setObjectName('StatusButton')
        self.btn_mode.setToolTip('插入 / 改写模式（Insert 键切换）')
        self.btn_mode.setCursor(Qt.PointingHandCursor)
        self.btn_mode.clicked.connect(self._toggle_mode)

        self.btn_focus = QPushButton('专注')
        self.btn_focus.setMinimumWidth(48)
        self.btn_focus.setObjectName('StatusButton')
        self.btn_focus.setCheckable(True)
        self.btn_focus.setToolTip('专注模式（F11）')
        self.btn_focus.setCursor(Qt.PointingHandCursor)
        self.btn_focus.clicked.connect(self.focusToggled.emit)

        for w in (self.lbl_pos, self.btn_words, self.lbl_saved, self.btn_mode, self.btn_focus):
            self.addPermanentWidget(w)
        self.zoom_widgets = []

        # 「进行中」扫光线：贴着状态栏顶边的一段暖色亮线，往复移动。
        # 只在 set_accent(color) 的强调态显示；常态隐藏，不参与布局、不吞鼠标事件。
        self._sweep = QWidget(self)
        self._sweep.setObjectName('StatusSweepLine')
        self._sweep.setAttribute(Qt.WA_StyledBackground, True)
        self._sweep.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._sweep.setFixedHeight(2)
        self._sweep.hide()
        self._sweep_progress = 0.0
        self._sweep_anim = QPropertyAnimation(self, b'sweepProgress', self)
        self._sweep_anim.setDuration(1900)
        self._sweep_anim.setLoopCount(-1)
        self._sweep_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._sweep_anim.setKeyValueAt(0.0, 0.0)
        self._sweep_anim.setKeyValueAt(0.5, 1.0)
        self._sweep_anim.setKeyValueAt(1.0, 0.0)

    def _get_sweep_progress(self):
        return self._sweep_progress

    def _set_sweep_progress(self, value):
        """动画回调：按窗口当前宽度把亮线放在 0→1 的往复位置上。"""
        self._sweep_progress = max(0.0, min(1.0, float(value)))
        seg = max(88, int(self.width() * 0.22))
        x = int(-seg + (self.width() + seg * 2) * self._sweep_progress)
        self._sweep.setGeometry(x, 0, seg, 2)
        self._sweep.raise_()

    sweepProgress = pyqtProperty(float, _get_sweep_progress, _set_sweep_progress)

    def _toggle_mode(self):
        self.set_mode(not self._overwrite)
        self.modeToggled.emit(self._overwrite)

    def attach_zoom(self, down_btn, slider, up_btn, percent_label):
        """把主程序已有的缩放控件迁到状态栏右侧，保持同一套对象与信号。"""
        for b in (down_btn, up_btn):
            b.setObjectName('StatusZoom')
            b.setFixedSize(20, 20)
        slider.setObjectName('StatusZoom')
        slider.setFixedWidth(110)
        slider.setMaximumHeight(18)
        slider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        percent_label.setFixedWidth(42)
        percent_label.setAlignment(Qt.AlignCenter)
        percent_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        percent_label.mouseDoubleClickEvent = lambda e: self.zoomResetClicked.emit()
        for w in (down_btn, slider, up_btn, percent_label):
            self.addPermanentWidget(w)
            self.zoom_widgets.append(w)

    def minimumSizeHint(self):
        """状态栏右侧指示器很多，若直接用布局建议值，会把主窗口最小宽度钉死在 870+，
        导致拖动左边框收窄时窗口很快就缩不动（只会跟着光标平移）。
        这里放开最小宽度，由 _update_compact 在窄窗口下依次隐藏次要指示器。"""
        hint = super().minimumSizeHint()
        return QSize(300, hint.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_compact()
        if not self._sweep.isHidden():
            self._set_sweep_progress(self._sweep_progress)

    def _update_compact(self):
        """窗口变窄时按重要性依次让位：消息 → 行列 → 保存状态。"""
        w = self.width()
        self.lbl_msg.setVisible(w >= 620)
        self.lbl_pos.setVisible(w >= 480)
        self.lbl_saved.setVisible(w >= 420)

    def showMessage(self, text, timeout=0):
        self.lbl_msg.setText(text or '就绪')
        if timeout and timeout > 0:
            self._timer.start(timeout)
        else:
            self._timer.stop()

    def clearMessage(self):
        self._timer.stop()
        self.lbl_msg.setText('就绪')

    def currentMessage(self):
        return self.lbl_msg.text()

    @staticmethod
    def _mix(a, b, t):
        """两个 QColor 按 t 线性混合（t=0 → a，t=1 → b），用于派生暖色色阶。"""
        return QColor(int(a.red() + (b.red() - a.red()) * t),
                      int(a.green() + (b.green() - a.green()) * t),
                      int(a.blue() + (b.blue() - a.blue()) * t))

    def set_accent(self, color=None):
        """切换状态栏底色（识别中 / 校验中等进度反馈）。

        注意：状态栏的内联样式表会同时作用于子控件（按钮 / 滑块 / 标签），必须
        全部写出，否则子控件会回退到默认调色板，出现比状态栏更深的色块。

        旧版把整条状态栏刷成高饱和橙 #cc6633，却把按钮底色写死为常态深蓝
        #1e2933 —— 于是「字数 / 插入 / 专注」变成三块深色矩形浮在橙色之上，
        反而抢走了本该属于「校验中」消息的注意力。现在的强调态遵循三条规则：
          1. 橙色只覆盖左侧消息区，横向渐变到右侧常态深蓝，不再满屏高饱和；
          2. 所有按钮 / 缩放控件底色透明，深色成为「底」而不是「块」；
          3. 消息加粗 + 左侧暖橙竖条 + 顶边往复扫光线，成为唯一视觉焦点。
        所有强调态颜色都由传入的强调色派生；color=None 时完全恢复常态配色。
        """
        # 全应用固定深蓝配色（主题选择功能已移除），不再读取 QSettings 里的主题设置。
        _bg = '#1e2933'
        # (文字, hover文字, 已保存, 未保存, 消息, 按钮hover底, 顶部分隔线, 滑块柄, 滑块已填充)
        (_txt, _txth, _saved, _dirty, _msg, _btnhover, _border, _handle, _subpage) = \
            ('#dce5ee', '#ffffff', '#a8e0b4', '#ffd28a', '#cbd8e4',
             '#2b3947', '#3a4756', '#e6ecf2', '#7fb0f0')
        bar_bg = _bg
        chip_bg = _bg                  # 常态下控件底色 = 状态栏底色，二者融为一体
        _groove = _btnhover            # 滑块槽常态沿用 hover 底色
        extra = ''

        if color:
            acc = QColor(color)
            base = QColor(_bg)
            warm0 = self._mix(acc, base, 0.42)   # 左端：暗橙
            warm1 = self._mix(acc, base, 0.72)   # 中段：深棕，向常态底色过渡
            bar_bg = ('qlineargradient(x1:0,y1:0,x2:1,y2:0, '
                      'stop:0 %s, stop:0.34 %s, stop:0.66 %s, stop:1 %s)'
                      % (warm0.name(), warm1.name(), _bg, _bg))
            chip_bg = 'transparent'  # 关键：深色块消失，指示器融入背景
            _txt, _txth = '#f2ddd0', '#fff6ec'
            _msg, _saved, _dirty = '#fff0dc', '#c6e6c8', '#ffe1a6'
            _btnhover = self._mix(acc, base, 0.30).name()
            _border = self._mix(acc, base, 0.52).name()
            # 右侧缩放槽保持低对比：否则一条亮橙线会比左侧消息更抢眼。
            _groove = self._mix(acc, base, 0.76).name()
            _handle, _subpage = '#ffe9d0', '#ffb066'
            extra = (
                'QStatusBar#WordStatusBar QLabel#StatusMessage {'
                '  color: %s; font-weight: bold; padding-left: 10px;'
                '  background: transparent; border: none;'
                '  border-left: 3px solid %s;'
                '}'
                'QWidget#StatusSweepLine {'
                '  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,'
                '    stop:0 rgba(255,176,102,0), stop:0.5 rgba(255,208,150,255),'
                '    stop:1 rgba(255,176,102,0));'
                '  border: none; border-radius: 1px;'
                '}'
                % (_msg, _subpage))

            if self._sweep.isHidden():
                self._sweep.show()
                self._sweep_anim.start()
        else:
            self._sweep_anim.stop()
            self._sweep.hide()

        self.setStyleSheet(
            'QStatusBar#WordStatusBar {'
            '  background: %s; border: none; border-top: 1px solid %s;'
            '  min-height: 27px; max-height: 27px;'
            '}'
            'QStatusBar#WordStatusBar QLabel { background: transparent; color: %s; font-size: 12px; }'
            'QStatusBar#WordStatusBar QLabel#StatusDoc { color: %s; font-weight: bold; padding-left: 8px; }'
            'QStatusBar#WordStatusBar QLabel#StatusMessage { color: %s; padding-left: 10px; }'
            'QStatusBar#WordStatusBar QLabel#StatusSaved { color: %s; padding-right: 4px; }'
            'QStatusBar#WordStatusBar QLabel#StatusDirty { color: %s; padding-right: 4px; }'
            'QPushButton#StatusButton {'
            '  background: %s; border: none; border-radius: 3px; color: %s;'
            '  font-size: 12px; padding: 2px 8px; min-height: 20px;'
            '}'
            'QPushButton#StatusButton:hover { background: %s; color: %s; }'
            'QToolButton#StatusZoom {'
            '  background: %s; border: none; color: %s; font-size: 13px;'
            '  min-width: 20px; max-width: 20px; min-height: 20px;'
            '}'
            'QToolButton#StatusZoom:hover { background: %s; border-radius: 3px; }'
            'QSlider#StatusZoom { background: transparent; border: none; }'
            'QSlider#StatusZoom::groove:horizontal { height: 3px; background: %s; border: none; border-radius: 1px; }'
            'QSlider#StatusZoom::handle:horizontal {'
            '  width: 9px; height: 14px; margin: -6px 0; border-radius: 2px;'
            '  background: %s; border: 1px solid %s;'
            '}'
            'QSlider#StatusZoom::sub-page:horizontal { background: %s; }'
            % (bar_bg, _border, _txt, _txth, _msg, _saved, _dirty,
               chip_bg, _txt, _btnhover, _txth, chip_bg, _txt, _btnhover,
               _groove, _handle, _border, _subpage)
            + extra)

    def set_doc_name(self, name):
        self.lbl_doc.setText(name or '未命名')

    def set_position(self, line, column, total=0):
        suffix = ' / 共 %d 行' % total if total else ''
        self.lbl_pos.setText('第 %d 行，第 %d 列%s' % (line, column, suffix))

    def set_words(self, count, selected=0):
        text = '字数 %s' % format(count, ',')
        if selected:
            text += '（已选 %s）' % format(selected, ',')
        self.btn_words.setText(text)

    def set_saved(self, saved):
        self.lbl_saved.setText('已保存' if saved else '● 未保存')
        self.lbl_saved.setObjectName('StatusSaved' if saved else 'StatusDirty')
        self.lbl_saved.style().unpolish(self.lbl_saved)
        self.lbl_saved.style().polish(self.lbl_saved)

    def set_mode(self, overwrite):
        self._overwrite = bool(overwrite)
        self.btn_mode.setText('改写' if self._overwrite else '插入')

    def overwrite(self):
        return self._overwrite

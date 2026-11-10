"""联想补全弹窗：输入法式横向候选条。

- 每页最多 4 项，1 行高度；超过 4 项 ←→ 翻页；
- 深色背景、1px 白色圆角边框；不抢焦点。
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPainter, QPen, QColor
from PyQt5.QtWidgets import (
    QWidget, QListWidget, QListWidgetItem, QVBoxLayout,
    QListView,
)

COMPLETER_QSS = """
QWidget#FenrirCompleter {
    background: #1e2730;
}
QListWidget#cmpList {
    background: transparent;
    border: none;
    outline: 0;
    padding: 2px 4px;
}
QListWidget#cmpList::item {
    color: #dce6f0;
    padding: 4px 8px 4px 6px;
    border-radius: 3px;
    margin: 2px 3px;
}
QListWidget#cmpList::item:selected {
    background: transparent;
    color: #5ac8fa;
}
QListWidget#cmpList::item:hover {
    background: #2a3a48;
}
"""

PAGE_SIZE = 4


class CompleterPopup(QWidget):
    itemActivated = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setObjectName('FenrirCompleter')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._payloads = []
        self._mode = 'mark'
        self._page = 0
        self._build_ui()
        self.list.setMouseTracking(True)
        self.list.itemClicked.connect(self._on_click)
        self.list.itemEntered.connect(self._on_hover)

    def paintEvent(self, event):
        """自绘 1px 白色圆角边框，QSS border 在无边框浮窗上不渲染。"""
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor('#ffffff'))
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 6, 6)
        p.end()

    def _build_ui(self):
        self.setStyleSheet(COMPLETER_QSS)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(0)

        self.list = QListWidget()
        self.list.setObjectName('cmpList')
        self.list.setFlow(QListView.LeftToRight)
        self.list.setWrapping(False)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.list, 1)

    # ---------------- 数据填充 ----------------
    def set_items(self, items, mode='mark', title='', footer=''):
        self._mode = mode
        self._payloads = list(items)
        self._page = 0
        self.list.clear()
        for it in self._payloads:
            item = QListWidgetItem()
            if mode == 'mark':
                item.setText('%s %s' % (it.get('num', ''), it.get('name', '')))
            else:
                item.setText(it.get('text', ''))
            item.setData(Qt.UserRole, it)
            item.setFont(QFont('Microsoft YaHei', 8))
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.list.addItem(item)
        self._apply_page()

    def _total_pages(self):
        return max(1, (len(self._payloads) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _apply_page(self):
        n = self.list.count()
        start = self._page * PAGE_SIZE
        end = min(start + PAGE_SIZE, n)
        for i in range(n):
            it = self.list.item(i)
            it.setHidden(i < start or i >= end)
        if n > 0:
            self.list.setCurrentRow(start)
        self._resize_to_content()

    def _resize_to_content(self):
        n = self.list.count()
        if n == 0:
            self.setFixedSize(120, 30)
            return
        row_h = 26
        start = self._page * PAGE_SIZE
        end = min(start + PAGE_SIZE, n)
        visible = list(range(start, end))
        w = 16
        for i in visible:
            it = self._payloads[i]
            if self._mode == 'mark':
                txt = '%s %s' % (it.get('num', ''), it.get('name', ''))
            else:
                txt = it.get('text', '')
            w += sum(12 if ord(c) > 0x2e80 else 8 for c in txt) + 28
        h = row_h + 8
        self.setFixedSize(w, h)

    # ---------------- 键盘导航 ----------------
    def move_selection(self, delta):
        n = self.list.count()
        if not n:
            return
        start = self._page * PAGE_SIZE
        end = min(start + PAGE_SIZE, n)
        cur = self.list.currentRow()
        if cur < start or cur >= end:
            self.list.setCurrentRow(start)
            return
        r = cur + delta
        if r > end - 1:
            r = start
        elif r < start:
            r = end - 1
        self.list.setCurrentRow(r)

    def move_page(self, delta):
        tp = self._total_pages()
        if tp <= 1:
            return
        self._page = (self._page + delta) % tp
        self._apply_page()

    def current_payload(self):
        it = self.list.currentItem()
        if it is None or it.isHidden():
            return None
        return it.data(Qt.UserRole)

    def _on_hover(self, item):
        if not item.isHidden():
            self.list.setCurrentItem(item)

    def _on_click(self, item):
        if not item.isHidden():
            self.itemActivated.emit(item.data(Qt.UserRole))

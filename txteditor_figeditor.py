# -*- coding: utf-8 -*-
"""
Fenrir 附图编辑器 - Figeditor
功能：在专利附图上手动/自动标注附图标记，支持OCR识别、转线条图、锐化。
"""
import os
import sys
import base64
import numpy as np
import cv2
import requests
import qtawesome as qta
import qdarkstyle
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *


# ============ 百度OCR线程 ============
OCR_TOKEN_URL = 'https://aip.baidubce.com/oauth/2.0/token'
OCR_API_URL = 'https://aip.baidubce.com/rest/2.0/ocr/v1/general'
_BAIDU_AK = ''
_BAIDU_SK = ''


class Worker_OCR(QThread):
    """百度通用文字识别"""
    done = pyqtSignal(list)

    def __init__(self, img_path):
        super().__init__()
        self.img_path = img_path

    def run(self):
        try:
            token = self._get_token()
            with open(self.img_path, 'rb') as f:
                img = base64.b64encode(f.read())
            r = requests.post(
                OCR_API_URL + '?access_token=' + token,
                data={'image': img},
                headers={'content-type': 'application/x-www-form-urlencoded'},
                timeout=15)
            self.done.emit(r.json().get('words_result', []))
        except Exception as e:
            print('OCR error:', e)
            self.done.emit([])

    @staticmethod
    def _get_token():
        r = requests.post(OCR_TOKEN_URL, params={
            'grant_type': 'client_credentials',
            'client_id': _BAIDU_AK,
            'client_secret': _BAIDU_SK}, timeout=10)
        return r.json().get('access_token', '')


# ============ 贝塞尔曲线标注 ============
class CurveItem(QGraphicsItem):
    def __init__(self, x1, y1, x2, y2, x3, y3, color, width):
        super().__init__()
        self.pts = (x1, y1, x2, y2, x3, y3)
        self.color = QColor(color)
        self.width = width

    def boundingRect(self):
        x1, y1, x2, y2, x3, y3 = self.pts
        # 扩大范围避免曲线被裁剪
        pad = 20
        return QRectF(min(x1, x2, x3) - pad, min(y1, y2, y3) - pad,
                      max(x1, x2, x3) - min(x1, x2, x3) + pad * 2,
                      max(y1, y2, y3) - min(y1, y2, y3) + pad * 2)

    def paint(self, painter, option=None, widget=None):
        painter.setPen(QPen(self.color, self.width, Qt.SolidLine))
        painter.setRenderHint(QPainter.Antialiasing)
        x1, y1, x2, y2, x3, y3 = self.pts
        # 两段贝塞尔 S 形，M 点按 3:2 比例（初始端:末端 = 3:2）
        # M = P0 + (P3-P0)*0.6
        mx = x1 + (x3 - x1) * 0.6
        my = y1 + (y3 - y1) * 0.6
        # 第二段第一个控制点 = 2M-C2，保证相切
        c3x, c3y = 2 * mx - x2, 2 * my - y2
        path = QPainterPath()
        path.moveTo(x1, y1)
        path.cubicTo(x1, y1, x2, y2, mx, my)
        path.cubicTo(c3x, c3y, x3, y3, x3, y3)
        painter.drawPath(path)


# ============ 主窗口 ============
class Figeditor(QWidget):
    def __init__(self, active_figmark=None):
        super().__init__()
        self.active_figmark = active_figmark
        self.in_dir = ''
        self.pixmap = None
        self.line_color = 'black'
        self.draw_yes = False
        self.x0 = self.y0 = 0
        # 标注列表：每项是 dict
        # {text_item, line1, line2, curve, x0,y0,x1,y1,x2,y2,x3,y3, xt,yt, mark}
        self.marks = []
        self.preview_items = []   # 鼠标移动时的临时项
        self.figmark_json = []
        self.reco_flag = False
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle('Figeditor  推荐 1200px*1200px 以下')
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.setFixedSize(900, 620)
        self.move(400, 200)
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # 画布
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(Qt.white))
        self.scene.mouseMoveEvent = self._mouse_move
        self.scene.mousePressEvent = self._mouse_press
        self.scene.dragEnterEvent = lambda e: e.accept() if e.mimeData().hasUrls() else e.ignore()
        self.scene.dropEvent = self._on_drop
        self.canvas = QGraphicsView(self.scene)
        self.canvas.setFixedSize(600, 600)
        self.canvas.setMouseTracking(True)
        root.addWidget(self.canvas)

        # 右侧控制面板
        panel = QVBoxLayout()
        panel.setSpacing(6)

        # 模式行
        row1 = QHBoxLayout()
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(['线条标注', '曲线标注', '文字标注', '阅览模式'])
        self.combo_mode.setFixedHeight(28)
        row1.addWidget(self.combo_mode)
        self.bt_color = QPushButton('█')
        self.bt_color.setToolTip('线条颜色')
        self.bt_color.setFixedSize(28, 28)
        self.bt_color.clicked.connect(self._pick_color)
        row1.addWidget(self.bt_color)
        panel.addLayout(row1)

        # 操作类型行
        self.combo_op = QComboBox()
        self.combo_op.addItems(['单独标注', '识别标注', '擦除标记', '一键标注', '转线条图', '图像锐化'])
        self.combo_op.setFixedHeight(28)
        self.combo_op.currentIndexChanged.connect(self._on_op_changed)
        panel.addWidget(self.combo_op)

        # 标记文本行
        row2 = QHBoxLayout()
        row2.addWidget(QLabel('标记'))
        self.text_mark = QLineEdit('1')
        self.text_mark.setFixedHeight(28)
        row2.addWidget(self.text_mark)
        panel.addLayout(row2)

        # 滑块
        row3 = QHBoxLayout()
        row3.addWidget(QLabel('字号'))
        self.slider_font = QSlider(Qt.Horizontal)
        self.slider_font.setRange(10, 100)
        self.slider_font.setValue(40)
        row3.addWidget(self.slider_font)
        panel.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel('线宽'))
        self.slider_width = QSlider(Qt.Horizontal)
        self.slider_width.setRange(1, 10)
        self.slider_width.setValue(2)
        row4.addWidget(self.slider_width)
        panel.addLayout(row4)

        # 按钮网格
        btn_grid = QGridLayout()
        btn_grid.setSpacing(4)
        self.bt_load = QPushButton('加载')
        self.bt_load.setFixedHeight(28)
        self.bt_load.clicked.connect(self._load_pic)
        self.bt_save = QPushButton('保存')
        self.bt_save.setFixedHeight(28)
        self.bt_save.clicked.connect(self._save_pic)
        self.bt_load_mark = QPushButton('加载标记')
        self.bt_load_mark.setFixedHeight(28)
        self.bt_load_mark.clicked.connect(self._load_marks_from_panel)
        self.bt_mspaint = QPushButton('画图板')
        self.bt_mspaint.setFixedHeight(28)
        self.bt_mspaint.clicked.connect(self._open_mspaint)
        self.bt_clear = QPushButton('清空')
        self.bt_clear.setFixedHeight(28)
        self.bt_clear.setStyleSheet('QPushButton{background:#e55f00;color:white}')
        self.bt_clear.clicked.connect(self.clear_all)
        self.bt_submit = QPushButton('提交')
        self.bt_submit.setFixedHeight(30)
        self.bt_submit.setStyleSheet('QPushButton{background:#e55f00;color:white}')
        self.bt_submit.setEnabled(False)
        self.bt_submit.clicked.connect(self._submit)
        btn_grid.addWidget(self.bt_load, 0, 0)
        btn_grid.addWidget(self.bt_save, 0, 1)
        btn_grid.addWidget(self.bt_load_mark, 1, 0)
        btn_grid.addWidget(self.bt_mspaint, 1, 1)
        btn_grid.addWidget(self.bt_clear, 2, 0)
        btn_grid.addWidget(self.bt_submit, 2, 1, 1, 1)
        panel.addLayout(btn_grid)

        # 标记列表
        self.text_allmarks = QTextEdit()
        self.text_allmarks.setPlaceholderText('附图标记列表')
        self.text_allmarks.setVisible(False)
        panel.addWidget(self.text_allmarks, 1)

        self.table = QTableWidget(99, 2)
        self.table.setHorizontalHeaderLabels(['符号', '名称'])
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 60)
        self.table.cellChanged.connect(self._on_cell_changed)
        panel.addWidget(self.table, 1)

        root.addLayout(panel, 1)

    # ---------- 事件 ----------
    def _on_drop(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.in_dir = urls[0].toLocalFile()
            self.reload_pic(self.in_dir)
            self.bt_submit.setEnabled(True)
        event.accept()

    def _on_op_changed(self):
        if self.combo_op.currentText() == '一键标注':
            self.text_allmarks.setVisible(True)
            self.table.setVisible(False)
            if not self.text_allmarks.toPlainText():
                self.text_allmarks.setPlainText('1 组件1\n2 组件2')
        else:
            self.text_allmarks.setVisible(False)
            self.table.setVisible(True)

    def _pick_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.line_color = c.name()
            self.bt_color.setStyleSheet(f'QPushButton{{color:{self.line_color}}}')

    def _load_pic(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开', '', '图片 (*.jpg *.jpeg *.png *.bmp)')
        if path:
            self.in_dir = path
            self.reload_pic(path)
            self.bt_submit.setEnabled(True)

    def _load_marks_from_panel(self):
        if self.active_figmark:
            self.text_allmarks.setHtml(self.active_figmark.toHtml())

    def _open_mspaint(self):
        try:
            os.makedirs('./temp', exist_ok=True)
            path = './temp/paint.jpg'
            img = QImage(self.scene.sceneRect().size().toSize(), QImage.Format_ARGB32)
            p = QPainter(img)
            self.scene.render(p)
            p.end()
            img.save(path)
        except Exception as e:
            print('export error:', e)
        QDesktopServices.openUrl(QUrl('mspaint:' + os.path.abspath(path).replace('\\', '/')))

    def _save_pic(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存', '未命名.jpg', 'JPG(*.jpg);;PNG(*.png);;BMP(*.bmp)')
        if not path:
            return
        img = QImage(self.scene.sceneRect().size().toSize(), QImage.Format_ARGB32)
        p = QPainter(img)
        self.scene.render(p)
        p.end()
        img.save(path)
        # 可选裁边
        if QMessageBox.question(self, '裁边', '是否裁掉边缘空白？') == QMessageBox.Yes:
            self._crop_border(path)

    def clear_all(self):
        self.table.clearContents()
        self.scene.clear()
        self.scene.setBackgroundBrush(QBrush(Qt.white))
        self.canvas.setFixedSize(600, 600)
        self.setFixedSize(880, 615)
        self.marks.clear()
        self.preview_items.clear()
        self.bt_submit.setEnabled(False)

    def reload_pic(self, path):
        self.clear_all()
        self.text_mark.setText('1')
        self.pixmap = QPixmap(path)
        self.scene.addPixmap(self.pixmap)
        self.canvas.setFixedSize(self.pixmap.width() + 15, self.pixmap.height() + 15)
        self.setFixedSize(self.pixmap.width() + 300, self.pixmap.height() + 50)

    # ---------- 坐标计算 ----------
    def _cursor_pos(self):
        """全局光标坐标 → scene 坐标"""
        gp = QCursor.pos()
        vp = self.canvas.mapFromGlobal(gp)
        return vp.x(), vp.y()

    def _calc_anchor(self):
        """根据当前光标位置算标注落点 xt, yt 和辅助线终点 x2,y2,x3,y3"""
        x2, y2 = self._cursor_pos()
        pw = self.pixmap.width() if self.pixmap else 600
        ph = self.pixmap.height() if self.pixmap else 600
        x2 = max(20, min(x2, pw - 25))
        y2 = max(27, min(y2, ph - 10))
        fs = self.slider_font.value()
        mark = self.text_mark.text()
        mode = self.combo_mode.currentText()
        # 弧线末端方向
        dx = 1 if x2 > self.x0 else -1
        x3 = x2 + dx * fs
        y3 = y2
        if mode == '曲线标注':
            # 数字位于弧线外端，根据方向避免与曲线干涉
            mark_w = len(mark) * fs / 4
            if dx > 0:
                xt = x3 + fs / 4
                yt = y3 - fs * 0.3
            else:
                xt = x3 - fs / 4 - mark_w
                yt = y3 - fs * 0.3
        elif mode == '文字标注':
            xt = x2 - fs / 3 - len(mark) + (15 if x2 <= self.x0 else -5)
            yt = y2 - fs * 0.7 - 3
        else:
            xt = (x2 - fs / 2) - fs / 3 - len(mark) if x2 <= self.x0 else (x2 + fs / 2) - fs / 3 - len(mark)
            yt = y2 - fs * 0.7 - 13
        return x2, y2, x3, y3, xt, yt

    def _font(self):
        return QFont(self.font().family(), max(8, int(self.slider_font.value() / 2)))

    # ---------- 鼠标交互 ----------
    def _mouse_press(self, event):
        if not self.pixmap or event.button() == Qt.RightButton:
            return
        if self.combo_op.currentText() not in ('单独标注', '识别标注'):
            return
        if self.combo_mode.currentText() not in ('线条标注', '曲线标注', '文字标注'):
            return
        if not self.draw_yes:
            # 第一次点击：起点
            self.draw_yes = True
            self.x0, self.y0 = self._cursor_pos()
        else:
            # 第二次点击：落点，固化
            self.draw_yes = False
            x2, y2, x3, y3, xt, yt = self._calc_anchor()
            mark = self.text_mark.text()
            items = {}
            txt = self.scene.addText(mark, self._font())
            txt.setDefaultTextColor(QColor(self.line_color))
            txt.setPos(xt, yt)
            items['text'] = txt
            mode = self.combo_mode.currentText()
            if mode == '线条标注':
                pen = QPen(QColor(self.line_color), self.slider_width.value())
                l1 = self.scene.addLine(self.x0, self.y0, x2, y2, pen)
                l2 = self.scene.addLine(x2, y2, x3, y3, pen)
                items.update(line1=l1, line2=l2)
            elif mode == '曲线标注':
                # 美国专利风格：起点→控制点→落点 的贝塞尔曲线
                curve = CurveItem(self.x0, self.y0, x2, y2, x3, y3,
                                  self.line_color, self.slider_width.value())
                self.scene.addItem(curve)
                items['curve'] = curve
            items.update(x0=self.x0, y0=self.y0, x2=x2, y2=y2,
                         x3=x3, y3=y3, xt=xt, yt=yt, mark=mark)
            self.marks.append(items)
            # 写表格
            for r in range(99):
                if not self.table.item(r, 0) or not self.table.item(r, 0).text():
                    self.table.setItem(r, 0, QTableWidgetItem(mark))
                    break
            # 标号自增
            self._inc_mark()
            self._clear_preview()

    def _mouse_move(self, event):
        if not self.draw_yes:
            return
        self._clear_preview()
        x2, y2, x3, y3, xt, yt = self._calc_anchor()
        mark = self.text_mark.text()
        txt = self.scene.addText(mark, self._font())
        txt.setDefaultTextColor(QColor(self.line_color))
        txt.setPos(xt, yt)
        self.preview_items.append(txt)
        mode = self.combo_mode.currentText()
        if mode == '线条标注':
            pen = QPen(QColor(self.line_color), self.slider_width.value())
            l1 = self.scene.addLine(self.x0, self.y0, x2, y2, pen)
            l2 = self.scene.addLine(x2, y2, x3, y3, pen)
            self.preview_items += [l1, l2]
        elif mode == '曲线标注':
            curve = CurveItem(self.x0, self.y0, x2, y2, x3, y3,
                              self.line_color, self.slider_width.value())
            self.scene.addItem(curve)
            self.preview_items.append(curve)

    def _clear_preview(self):
        for it in self.preview_items:
            self.scene.removeItem(it)
        self.preview_items.clear()

    def _inc_mark(self):
        old = self.text_mark.text()
        if not old:
            return
        last = old[-1]
        if last.isdigit():
            self.text_mark.setText(str(int(old) + 1))
        elif last.isalpha() and last not in ('z', 'Z'):
            self.text_mark.setText(old[:-1] + chr(ord(last) + 1))

    # ---------- 表格编辑 ----------
    def _on_cell_changed(self, row, col):
        if self.reco_flag:
            return
        cell = self.table.item(row, col)
        if not cell or row >= len(self.marks):
            return
        m = self.marks[row]
        if col == 0:
            new_text = cell.text()
            if not new_text:
                for k in ('text', 'line1', 'line2', 'curve'):
                    if k in m:
                        self.scene.removeItem(m[k])
                return
            # 更新文本
            if 'text' in m:
                self.scene.removeItem(m['text'])
            t = self.scene.addText(new_text, self._font())
            t.setDefaultTextColor(QColor(self.line_color))
            t.setPos(m['xt'], m['yt'])
            m['text'] = t
            m['mark'] = new_text
        elif col == 1:
            num = self.table.item(row, 0).text() if self.table.item(row, 0) else ''
            name = cell.text()
            if 'text' in m:
                self.scene.removeItem(m['text'])
            t = self.scene.addText(num + name, self._font())
            t.setDefaultTextColor(QColor(self.line_color))
            t.setPos(m['xt'], m['yt'])
            m['text'] = t

    # ---------- 提交（OCR + 后处理） ----------
    def _submit(self):
        if not self.in_dir:
            return
        self.op = self.combo_op.currentText()
        if self.op == '单独标注':
            return
        self.ocr = Worker_OCR(self.in_dir)
        self.ocr.done.connect(self._on_ocr_done)
        self.ocr.start()

    def _on_ocr_done(self, words):
        self.figmark_json = words
        if self.op == '识别标注':
            self._reco_and_mark()
        elif self.op == '擦除标记':
            self._erase()
        elif self.op == '一键标注':
            self._add_auto()
        elif self.op == '转线条图':
            self._to_line()
        elif self.op == '图像锐化':
            self._to_sharp()

    def _reco_and_mark(self):
        """OCR识别后，白色矩形盖住原文字，重新写上"""
        self.reco_flag = True
        self.marks.clear()
        for i, item in enumerate(self.figmark_json):
            mark = item['words']
            loc = item['location']
            xt = loc['left'] - len(mark) * 3
            yt = loc['top']
            w = loc['width'] + len(mark) * 9
            h = loc['height'] + 5
            rect = self.scene.addRect(xt, yt, w, h, QPen(Qt.white), QBrush(Qt.white))
            t = self.scene.addText(mark, self._font())
            t.setDefaultTextColor(QColor(self.line_color))
            t.setPos(xt, yt)
            self.marks.append({'text': t, 'xt': xt, 'yt': yt, 'mark': mark, 'rect': rect})
            self.table.setItem(i, 0, QTableWidgetItem(mark))
        self.reco_flag = False

    def _erase(self):
        """白色矩形盖住所有识别到的文字"""
        for item in self.figmark_json:
            loc = item['location']
            self.scene.addRect(loc['left'], loc['top'], loc['width'], loc['height'],
                               QPen(Qt.white), QBrush(Qt.white))

    def _add_auto(self):
        """根据标记列表，把OCR识别到的文字替换成"编号+名称\""""
        wanted = {}
        for line in self.text_allmarks.toPlainText().split('\n'):
            parts = line.split()
            if len(parts) >= 2:
                wanted[parts[0]] = ''.join(parts)
        for item in self.figmark_json:
            word = item['words']
            if word not in wanted:
                continue
            loc = item['location']
            label = wanted[word]
            x = loc['left'] - len(label) * 3
            y = loc['top']
            self.scene.addRect(x, y, loc['width'] + len(label) * 9, loc['height'] + 5,
                               QPen(Qt.white), QBrush(Qt.white))
            t = self.scene.addText(label, self._font())
            t.setDefaultTextColor(QColor(self.line_color))
            t.setPos(x, y)

    # ---------- 图像后处理 ----------
    def _read_cn(self, path):
        with open(path, 'rb') as f:
            return cv2.imdecode(np.frombuffer(f.read(), np.uint8), -1)

    def _write_cn(self, path, img):
        ext = os.path.splitext(path)[1] or '.jpg'
        cv2.imencode(ext, img)[1].tofile(path)

    def _to_sharp(self):
        img = self._read_cn(self.in_dir)
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        out = cv2.filter2D(img, -1, kernel)
        path = self.in_dir.rsplit('.', 1)[0] + '_temp.jpg'
        self._write_cn(path, out)
        self.reload_pic(path)

    def _to_line(self):
        img = self._read_cn(self.in_dir)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        out = cv2.adaptiveThreshold(gray, 200, cv2.ADAPTIVE_THRESH_MEAN_C,
                                    cv2.THRESH_BINARY, 3, 5)
        path = self.in_dir.rsplit('.', 1)[0] + '_temp.jpg'
        self._write_cn(path, out)
        self.reload_pic(path)

    def _crop_border(self, path):
        """裁掉图片白边（numpy 向量化找 bbox）"""
        img = self._read_cn(path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_TRUNC)
        canny = cv2.Canny(binary, 0, 100)
        ys, xs = np.where(canny > 0)
        if len(ys) == 0:
            return
        y1, y2, x1, x2 = ys.min(), ys.max(), xs.min(), xs.max()
        crop = img[max(0, y1 - 2):y2 + 2, max(0, x1 - 2):x2 + 2]
        self._write_cn(path, crop)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5'))
    win = Figeditor()
    win.show()
    app.exec_()

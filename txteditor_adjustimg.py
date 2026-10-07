# -*- coding: utf-8 -*-
"""
Fenrir 附图编辑器 - 视图裁剪与尺寸统一
功能：拖入6视图（主后左右俯仰）+立体图，自动裁剪边缘、按主视图尺寸统一各视图比例。
优化：numpy 向量化找边界替代双重循环；抽出公共函数消除重复；global img_dic 改参数传递。
"""
import os
import cv2
import numpy as np
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import qtawesome as qta
import qdarkstyle
import sys
import win32api
import win32gui


# ============ 公共图像处理函数（三处复用） ============
def imread_chinese(path):
    """中文路径读图（cv2.imread 不支持中文）"""
    with open(path, 'rb') as f:
        buf = np.frombuffer(f.read(), dtype=np.uint8)
    return cv2.imdecode(buf, 1)


def imwrite_chinese(path, img, quality=95):
    """中文路径写图"""
    ext = os.path.splitext(path)[1] or '.jpg'
    cv2.imencode(ext, img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tofile(path)


def find_bbox(canny):
    """从 Canny 边缘图找有效区域 bbox。numpy 向量化，比双重循环快百倍。
    返回 (y1, y2, x1, x2)，无边缘返回 None。"""
    ys, xs = np.where(canny > 0)
    if len(ys) == 0:
        return None
    return int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())


def crop_to_content(img, thr_binary=200, thr_canny=100):
    """二值化→Canny→裁剪到有效区域。返回 (crop_img, width, height)。"""
    _, binary = cv2.threshold(img, thr_binary, 255, cv2.THRESH_TRUNC)
    canny = cv2.Canny(binary, 0, thr_canny)
    bbox = find_bbox(canny)
    if bbox is None:
        h, w = img.shape[:2]
        return img, w, h
    y1, y2, x1, x2 = bbox
    # 加 2px 边距避免切到线
    y1, x1 = max(0, y1 - 2), max(0, x1 - 2)
    y2, x2 = min(img.shape[0], y2 + 2), min(img.shape[1], x2 + 2)
    crop = img[y1:y2, x1:x2]
    return crop, x2 - x1, y2 - y1


def resize_cn(path, rate_w, rate_h):
    """按比例缩放并覆盖写回"""
    img = imread_chinese(path)
    h, w = img.shape[:2]
    new = cv2.resize(img, (int(w * rate_w), int(h * rate_h)), interpolation=cv2.INTER_AREA)
    imwrite_chinese(path, new)


# ============ 单图裁剪线程 ============
class Worker_single(QThread):
    progress = pyqtSignal(list)

    def __init__(self, img_dir, thr, label):
        super().__init__()
        self.img_dir = img_dir
        self.thr = thr
        self.label = label

    def run(self):
        img = imread_chinese(self.img_dir)
        crop, w, h = crop_to_content(img, self.thr, self.thr)
        imwrite_chinese(self.img_dir, crop)
        self.progress.emit([w, h])
        self.label.setPixmap(QPixmap(self.img_dir))


# ============ 多视图批量调整线程 ============
class Worker_Adjust(QThread):
    progress = pyqtSignal(list)

    # 视图名（与 img_dic 下标对应）
    VIEW_NAMES = ['主视图', '后视图', '左视图', '右视图', '俯视图', '仰视图', '立体图']

    def __init__(self, thr, status, labels, img_dic):
        super().__init__()
        self.thr = thr
        self.status = status
        self.labels = labels
        self.img_dic = img_dic          # {0: path, 1: path, ...}
        self.sizes = {}                 # {下标: (w, h)}
        self.object_size = [0, 0, 0]    # 宽 高 厚

    def log(self, msg):
        self.status.append(msg)

    def run(self):
        # 1) 逐图裁剪边缘
        for idx in range(1, 7):  # 0 主视图不裁（作为基准）
            path = self.img_dic.get(idx, '')
            if not path:
                continue
            try:
                img = imread_chinese(path)
                crop, w, h = crop_to_content(img, self.thr, self.thr)
                imwrite_chinese(path, crop)
                self.sizes[idx] = (w, h)
                self.log(f'> {self.VIEW_NAMES[idx]}裁剪完成')
            except Exception as e:
                print(f'>> Error 401 idx={idx}: {e}')
        # 立体图
        p6 = self.img_dic.get(6, '')
        if p6:
            img = imread_chinese(p6)
            crop, w, h = crop_to_content(img, self.thr, self.thr)
            imwrite_chinese(p6, crop)
            self.sizes[6] = (w, h)
            self.log('> 立体图裁剪完成')

        # 2) 以主视图+左视图为基准算实际尺寸
        self._calc_object_size()

        # 3) 按比例调整各视图
        for idx in range(1, 6):
            try:
                self._adjust_one(idx)
            except Exception as e:
                print(f'>> adjust_size idx={idx}: {e}')

        # 4) 重新加载显示
        for idx in range(7):
            path = self.img_dic.get(idx, '')
            if path:
                _set_label_pixmap(self.labels[idx], path)
        self.log('> 全部视图处理完成')
        self.progress.emit(self.object_size)

    def _calc_object_size(self):
        """主视图裁剪得宽×高，左视图裁剪得厚，按比例统一"""
        p0 = self.img_dic.get(0, '')
        p2 = self.img_dic.get(2, '')
        if not p0 or not p2:
            return
        img0 = imread_chinese(p0)
        crop0, w0, h0 = crop_to_content(img0, self.thr, self.thr)
        imwrite_chinese(p0, crop0)
        img2 = imread_chinese(p2)
        crop2, w2, h2 = crop_to_content(img2, self.thr, self.thr)
        # 按高度比例缩放左视图，使与主视图同高
        if h2 > 0:
            rate = round(h0 / h2, 6)
            resize_cn(p2, rate, rate)
            crop2, w2, h2 = crop_to_content(imread_chinese(p2), self.thr, self.thr)
            imwrite_chinese(p2, crop2)
        self.object_size = [w0, h0, w2]
        self.log(f'产品尺寸 宽×高×厚: {self.object_size}')

    def _adjust_one(self, idx):
        """按 object_size 缩放 idx 对应视图"""
        path = self.img_dic.get(idx, '')
        if not path or idx not in self.sizes:
            return
        ow, oh, od = self.object_size
        cw, ch = self.sizes[idx]
        if cw == 0 or ch == 0:
            return
        if idx == 1:      # 后视图：宽高同主视图
            rw, rh = ow / cw, oh / ch
        elif idx == 2:    # 左视图：厚×高
            rw, rh = od / cw, oh / ch
        elif idx == 3:    # 右视图：厚×高
            rw, rh = od / cw, oh / ch
        elif idx == 4:    # 俯视图：宽×厚
            rw, rh = ow / cw, od / ch
        elif idx == 5:    # 仰视图：宽×厚
            rw, rh = ow / cw, od / ch
        else:
            return
        resize_cn(path, rw, rh)
        self.log(f'> {self.VIEW_NAMES[idx]}调整完成')


# ============ 工具：QLabel 显示图片（统一宽度300） ============
def _set_label_pixmap(label, path, max_side=300):
    img = QImage(path)
    w, h = img.width(), img.height()
    if w == 0 or h == 0:
        return
    if w >= h:
        nw, nh = max_side, int(h * max_side / w)
    else:
        nw, nh = int(w * max_side / h), max_side
    label.setPixmap(QPixmap.fromImage(img.scaled(nw, nh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)))


# ============ 主窗口 ============
class Design_Adjust(QWidget):
    def __init__(self):
        super().__init__()
        self.thr = 200
        self.img_dic = {i: '' for i in range(9)}
        self.object_size = [0, 0, 0]
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle('FigAdjust')
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.setFixedSize(1070, 850)
        self.move(400, 100)
        layout = QGridLayout()
        self.setLayout(layout)

        # 9 个拖拽标签：(对象属性名, 显示文字, 下标)
        self.label_fig_li = FileDropLabel('立体图\n右键清空', 7, self)
        self.label_fig_fu = FileDropLabel('俯视图\n右键清空', 5, self)
        self.label_fig_hou = FileDropLabel('后视图\n右键清空', 2, self)
        self.label_fig_zuo = FileDropLabel('左视图\n右键清空', 3, self)
        self.label_fig_zhu = FileDropLabel('主视图\n右键清空', 1, self)
        self.label_fig_you = FileDropLabel('右视图\n右键清空', 4, self)
        self.label_fig_7 = FileDropLabel('状态图I\n右键清空', 8, self)
        self.label_fig_yang = FileDropLabel('仰视图\n右键清空', 6, self)
        self.label_fig_9 = FileDropLabel('状态图II\n右键清空', 9, self)

        # 阈值滑条
        self.slider_bin = QSlider(Qt.Horizontal)
        self.slider_bin.setRange(0, 255)
        self.slider_bin.setValue(200)
        self.slider_bin.setMaximumWidth(100)

        # 按钮
        self.bt_load = QPushButton('一键导入')
        self.bt_load.setFixedSize(180, 30)
        self.bt_load.clicked.connect(self.load_all_imgs)

        self.bt_submit = QPushButton('提  交')
        self.bt_submit.setFixedSize(180, 30)
        self.bt_submit.setStyleSheet('QPushButton{background:#e55f00;color:white} QPushButton:hover{background:#f69958}')
        self.bt_submit.clicked.connect(self.start_worker)

        self.bt_genmodel = QPushButton('生成模型')
        self.bt_genmodel.setFixedSize(180, 30)
        self.bt_genmodel.setEnabled(False)

        self.text_status = QTextBrowser()
        self.text_status.setPlaceholderText(
            '推荐尺寸：1000px*1000px以下\n'
            '使用前，请确保主视图和左视图的宽高比相同\n'
            '拖拽图片文件名无要求；一键导入需按 01~06 顺序命名\n'
            '如产品边缘与背景色接近，先调阈值确保识别外轮廓')
        self.text_status.setStyleSheet('border:none')
        self.text_status.setFixedSize(180, 800)

        self.labels = [self.label_fig_zhu, self.label_fig_hou, self.label_fig_zuo,
                       self.label_fig_you, self.label_fig_fu, self.label_fig_yang,
                       self.label_fig_li, self.label_fig_7, self.label_fig_9]

        # 布局
        layout.addWidget(self.label_fig_li, 0, 0, 3, 3)
        layout.addWidget(self.label_fig_fu, 0, 3, 3, 3)
        layout.addWidget(self.label_fig_hou, 0, 6, 3, 3)
        layout.addWidget(self.label_fig_zuo, 4, 0, 3, 3)
        layout.addWidget(self.label_fig_zhu, 4, 3, 3, 3)
        layout.addWidget(self.label_fig_you, 4, 6, 3, 3)
        layout.addWidget(self.label_fig_7, 8, 0, 3, 3)
        layout.addWidget(self.label_fig_yang, 8, 3, 3, 3)
        layout.addWidget(self.label_fig_9, 8, 6, 3, 3)
        layout.addWidget(self.bt_load, 0, 9, 1, 2)
        layout.addWidget(self.bt_submit, 1, 9, 1, 2)
        layout.addWidget(self.bt_genmodel, 2, 9, 1, 2)
        layout.addWidget(QLabel('二值化阈值'), 3, 9, 1, 1)
        layout.addWidget(self.slider_bin, 3, 10, 1, 1)
        layout.addWidget(self.text_status, 5, 9, 3, 2)

    def load_all_imgs(self):
        """批量导入：选文件夹，按 01.jpg~06.jpg 命名"""
        folder = QFileDialog.getExistingDirectory(self, '选择文件夹', '')
        if not folder:
            return
        files = os.listdir(folder)
        for i, label in enumerate(self.labels, 1):
            fname = next((f for ext in ('jpg', 'jpeg', 'png', 'bmp')
                         if f'%02d.{ext}' % i in files), '')
            if not fname:
                continue
            path = os.path.join(folder, fname).replace('\\', '/')
            _set_label_pixmap(label, path)
            self.img_dic[i - 1] = path
        self.text_status.append('> 文件导入完成')
        self.bt_submit.setEnabled(True)

    def start_worker(self):
        """检查必备视图后启动后台线程"""
        names = ['主', '后', '左', '右', '俯', '仰']
        for i in range(6):
            if not self.img_dic.get(i):
                self.text_status.append(f'> 缺少{names[i]}视图')
                return
        self.bt_submit.setEnabled(False)
        self.bt_submit.setText('处理中...')
        self.thr = self.slider_bin.value()
        self.worker = Worker_Adjust(self.thr, self.text_status, self.labels, self.img_dic)
        self.worker.progress.connect(self._on_done)
        self.worker.start()

    def _on_done(self, obj_size):
        self.object_size = obj_size
        for i, label in enumerate(self.labels):
            path = self.img_dic.get(i, '')
            if path:
                _set_label_pixmap(label, path)
        self.bt_submit.setText('提  交')
        self.bt_submit.setEnabled(True)


# ============ 可拖拽 QLabel ============
class FileDropLabel(QLabel):
    def __init__(self, text, index, window):
        super().__init__()
        self._text = text
        self.index = index
        self._win = window
        self.dir = ''
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(300)
        self.setMaximumWidth(300)
        self.setText(text)
        self.setToolTip(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._win.img_dic[self.index - 1] = ''
            self.setPixmap(QPixmap())
            self.setText(self._text)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        self.dir = urls[0].toLocalFile()
        self._win.img_dic[self.index - 1] = self.dir
        _set_label_pixmap(self, self.dir)
        event.acceptProposedAction()


if __name__ == '__main__':
    ct = win32api.GetConsoleTitle()
    hd = win32gui.FindWindow(0, ct)
    win32gui.ShowWindow(hd, 0)
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5'))
    win = Design_Adjust()
    win.show()
    app.exec_()

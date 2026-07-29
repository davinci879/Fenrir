
import numpy as np
import base64
import json
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import sys
import qtawesome as qta
import requests
import qdarkstyle
import cv2
from matplotlib import pyplot as plt
import os,subprocess,time
class Worker_Submit(QThread):
    progress = pyqtSignal(list)
    def __init__(self,in_dir):
        super().__init__()
        self.in_dir = in_dir
        self.figmark_json = []
    def run(self):
        try:
            self.get_figmark_pos()
        except Exception as e:
            print(e)
        self.progress.emit(self.figmark_json)
    def get_access_token(self):
        url = "https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id=4dS07QkGwFnXCH15GA3Ia5dx&client_secret=uaXtCWB99PzlffMIOhgdhLgqWNG0OqXT"
        payload = json.dumps("")
        headers = {'Content-Type': 'application/json','Accept': 'application/json'}
        response = requests.request("POST", url, headers=headers, data=payload)
        return response.json().get("access_token")
    def get_figmark_pos(self):
        global user
        # if user == 'admin':
        #     request_url = 'https://aip.baidubce.com/rest/2.0/ocr/v1/accurate' # 高精度
        # else:
        request_url = "https://aip.baidubce.com/rest/2.0/ocr/v1/general" # 普通
        # 二进制方式打开图片文件
        img = base64.b64encode(open(self.in_dir, 'rb').read())

        params = {"image":img}
        access_token = self.get_access_token()
        request_url = request_url + "?access_token=" + access_token
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        response = requests.post(request_url, data=params, headers=headers)
        if response:
            self.figmark_json = response.json()['words_result']
        else:
            self.figmark_json = []
            print('No response')

class Figeditor(QWidget):
    def __init__(self,user_login,active_figmark):
        super().__init__()
        self.in_dir = ''
        self.pixmap = ''
        global user
        user = user_login
        self.active_figmark = active_figmark
        self.mark = '1'
        self.draw_yes = '0'
        self.line_color = 'black'
        self.mark = '1'
        self.pos_item_array = []
        self.pos_item_array_temp = []
        self.figmark_json ={}
        self.reco_mark_flag = False
        self.x0,self.y0 = 0,0
        self.main_ui()
    def main_ui(self):
        self.setWindowTitle("Figeditor 推荐尺寸 DPI 300 10cm * 10cm 以下  或  1200px * 1200px 以下")
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.main_layout = QGridLayout()
        self.setLayout(self.main_layout)
        self.setLayout(self.main_layout)

        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(QColor(Qt.white)))
        self.scene.mouseMoveEvent = self.fn_mouse_motion
        self.scene.mousePressEvent = self.fn_mouse_press
        self.scene.dropEvent = self.dropEvent
        self.scene.dragMoveEvent = self.dragMoveEvent
        self.scene.dragEnterEvent = self.dragEnterEvent

        self.canvas_fig = QGraphicsView(self.scene)
        self.canvas_fig.setFixedSize(600,600)
        self.move(400, 200)
        self.setFixedSize(880, 615)

        self.bt_color = QPushButton('█')
        self.bt_color.setToolTip('选择线条颜色')
        # self.bt_color.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Fixed)
        self.bt_color.setStyleSheet('QPushButton {background-color: #19232d ;color:black} QPushButton:hover {background-color: #b3b3b3 ;color:black}')
        self.bt_color.setFixedSize(10,20)
        self.bt_color.clicked.connect(self.color_change)

        self.combo_linetype = QComboBox()
        self.combo_linetype.addItems(['线条标注','文字标注','阅览模式']) # ,'曲线标注'
        self.combo_linetype.setFixedSize(70,30)

        self.label_content = QLabel('标记文本')
        self.label_content.setFixedSize(70,30)

        self.text_mark = QLineEdit()
        self.text_mark.setMinimumWidth(120)
        self.text_mark.setMaximumHeight(30)
        self.text_mark.setPlaceholderText('附图标记编号/名称')
        self.text_mark.insert('1')

        self.bt_load = QPushButton('加 载')
        self.bt_load.setFixedSize(70,30)
        self.bt_load.clicked.connect(self.fn_load_pic)

        self.bt_save = QPushButton('保 存')
        self.bt_save.setFixedSize(70,30)
        self.bt_save.clicked.connect(self.fn_figsave)

        self.bt_clear = QPushButton('清空画布')
        self.bt_clear.setFixedSize(70,30)
        self.bt_clear.setStyleSheet('QPushButton {background-color: #e55f00 ; color:white} QPushButton:hover {background-color: #f69958}')
        self.bt_clear.clicked.connect(self.clear_all)

        self.bt_mspaint = QPushButton('画图板')
        self.bt_mspaint.setToolTip('打开系统画图板')
        self.bt_mspaint.setFixedSize(70,30)
        self.bt_mspaint.clicked.connect(self.fn_mspaint)

        self.combo_submittype = QComboBox()
        self.combo_submittype.addItems(['单独标注','识别标注','擦除标记','一键标注','转线条图','图像锐化'])#['无损放大'])
        self.combo_submittype.setFixedSize(70,30)
        self.combo_submittype.currentIndexChanged.connect(self.on_combobox_changed)

        self.bt_load_mark = QPushButton('加载标记')
        self.bt_load_mark.setToolTip('载入正在使用的标记')
        self.bt_load_mark.setFixedSize(70,30)
        self.bt_load_mark.clicked.connect(self.fn_load_mark)

        self.bt_submit = QPushButton('提  交')
        self.bt_submit.setFixedSize(150,30)
        self.bt_submit.setStyleSheet('QPushButton {background-color: #e55f00 ; color:grey} QPushButton:hover {background-color: #f69958}')
        self.bt_submit.setEnabled(False)
        self.bt_submit.clicked.connect(self.fn_submit)

        self.label_fontsize = QLabel('标记尺寸')
        self.label_fontsize.setFixedSize(70,30)

        self.slider_fontsize = QSlider(Qt.Horizontal)
        self.slider_fontsize.setRange(10, 100)
        self.slider_fontsize.setValue(40)
        self.slider_fontsize.setTickPosition(QSlider.TicksBelow)  # 设置滑块的刻度位置
        self.slider_fontsize.setMinimumWidth(100)
        self.slider_fontsize.valueChanged.connect(self.change_value_1)
        self.slider_fontsize.mouseReleaseEvent = self.slider_pressrelease_1

        self.label_linewidth = QLabel('线  宽')
        self.label_linewidth.setFixedSize(70,30)

        self.slider_linewidth = QSlider(Qt.Horizontal)
        self.slider_linewidth.setRange(1, 10)
        self.slider_linewidth.setValue(2)
        self.slider_linewidth.setTickPosition(QSlider.TicksBelow)  # 设置滑块的刻度位置
        self.slider_linewidth.setMinimumWidth(100)
        self.slider_linewidth.valueChanged.connect(self.change_value_2)
        self.slider_linewidth.mouseReleaseEvent = self.slider_pressrelease_2

        self.text_allmarks = QTextEdit()
        self.text_allmarks.setPlaceholderText('附图标记列表')
        self.text_allmarks.setMinimumWidth(60)
        self.text_allmarks.setMinimumHeight(160)
        self.text_allmarks.setVisible(False)

        self.table_allmarks = QTableWidget()
        self.table_allmarks.setMinimumHeight(100)
        self.table_allmarks.setToolTip('双击修改/删除对应的标记')
        self.table_allmarks.setRowCount(99)             # 给列表设置行数
        self.table_allmarks.setColumnCount(2)          # 给表格设置列数
        self.table_allmarks.setHorizontalHeaderLabels(["符号","名称"])   # 设置行标题
        self.table_allmarks.setVerticalHeaderLabels(('%02d' % _) for _ in range(1,99))
        self.table_allmarks.setColumnWidth(0,75)     # 设置第1列列宽
        self.table_allmarks.setColumnWidth(1,75)
        # self.table_allmarks.horizontalHeader().hide()  # 隐藏水平表头
        # self.table_allmarks.verticalHeader().hide()    # 隐藏垂直表头
        self.table_allmarks.cellChanged.connect(self.on_cell_changed)
        self.main_layout.addWidget(self.canvas_fig,0,0,11,1) # y,x,height,width

        self.lb_0 = QLabel('')

        self.main_layout.addWidget(self.bt_color,0,9,1,1)
        self.main_layout.addWidget(self.combo_linetype,0,10,1,1)
        self.main_layout.addWidget(self.bt_load,0,11,1,1)
        self.main_layout.addWidget(self.bt_save,0,12,1,1)

        self.main_layout.addWidget(self.label_content,1,10,1,1)
        self.main_layout.addWidget(self.text_mark,1,11,1,2)

        self.main_layout.addWidget(self.label_fontsize,2,10,1,1)
        self.main_layout.addWidget(self.slider_fontsize,2,11,1,2)

        self.main_layout.addWidget(self.label_linewidth,3,10,1,1)
        self.main_layout.addWidget(self.slider_linewidth,3,11,1,2)

        self.main_layout.addWidget(self.bt_load_mark,4,10,1,1)
        self.main_layout.addWidget(self.bt_clear,4,11,1,1)
        self.main_layout.addWidget(self.bt_mspaint,4,12,1,1)

        self.main_layout.addWidget(self.combo_submittype,5,10,1,1)
        self.main_layout.addWidget(self.bt_submit,5,11,1,2)

        self.main_layout.addWidget(self.text_allmarks,6,10,6,3)
        self.main_layout.addWidget(self.table_allmarks,6,10,6,3)
    
    def on_cell_changed(self, row, column):
        current_cell = self.table_allmarks.item(row, column)
       
        if current_cell:
            current_txt = current_cell.text()
            if column == 0: # 数字行
                if not current_txt:
                    try:
                        self.scene.removeItem(self.pos_item_array[row][0])
                    except:
                        pass
                    try:
                        self.scene.removeItem(self.pos_item_array[row][1])
                    except:
                        pass
                    try:
                        self.scene.removeItem(self.pos_item_array[row][2])
                    except:
                        pass
                    try:
                        self.pos_item_array[row] = ['','','','','','','','','','','','','']
                        # self.pos_item_array.remove(self.pos_item_array[row])
                    except:
                        pass
                elif current_txt and self.text_mark.text() != current_txt and not self.reco_mark_flag:
                    try:
                        self.scene.removeItem(self.pos_item_array[row][0])
                        txt = self.scene.addText(current_txt,QFont(self.font().family(), self.slider_fontsize.value()/2))
                        txt.setDefaultTextColor(QColor(self.line_color))
                        txt.setPos(float(self.pos_item_array[row][-2]),float(self.pos_item_array[row][-1]))
                        self.pos_item_array[row][0] = txt
                    except:
                        pass
                    
            elif column == 1: # 文本行
                num = self.table_allmarks.item(row, 0).text()
                name = self.table_allmarks.item(row, 1).text()
                try:
                    self.scene.removeItem(self.pos_item_array[row][0])
                    txt = self.scene.addText(f'{num}{name}',QFont(self.font().family(), self.slider_fontsize.value()/2))
                    txt.setDefaultTextColor(QColor(self.line_color))
                    txt.setPos(float(self.pos_item_array[row][-2]),float(self.pos_item_array[row][-1]))
                    self.pos_item_array[row][0] = txt
                except:
                    pass

    def change_value_1(self):
        self.label_fontsize.setText(str(self.slider_fontsize.value()))
    def slider_pressrelease_1(self,event):
        self.label_fontsize.setText('标记尺寸')
    def change_value_2(self):
        self.label_linewidth.setText(str(self.slider_linewidth.value()))
    def slider_pressrelease_2(self,event):
        self.label_linewidth.setText('线 宽')
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
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = [url.toLocalFile() for url in event.mimeData().urls()]
            # 处理拖放的本地文件路径
            self.in_dir = urls[0]
            self.reload_pic(self.in_dir)
            self.bt_submit.setEnabled(True)
            self.bt_submit.setStyleSheet('QPushButton {background-color: #e55f00 ; color:white} QPushButton:hover {background-color: #f69958}')
            event.accept()
        else:
            event.ignore()

    def on_combobox_changed(self):
        if self.combo_submittype.currentText() == '一键标注':
            self.text_allmarks.setVisible(True)
            self.table_allmarks.setVisible(False)
            if not self.text_allmarks.toPlainText():
                self.text_allmarks.setPlainText('1 组件1\n2 组件2')
        else:
            self.text_allmarks.setVisible(False)
            self.table_allmarks.setVisible(True)
    def fn_load_mark(self):
        if self.active_figmark:
            self.text_allmarks.setHtml(self.active_figmark.toHtml())
    def fn_submit(self):
        if self.in_dir:
            self.submit_type = self.combo_submittype.currentText()
            self.figsubmit_thread = Worker_Submit(self.in_dir)
            self.figsubmit_thread.progress.connect(self.image_handle)
            self.figsubmit_thread.start()
        else:
            return
    def fn_mspaint(self):
        image_path = './temp/paint.jpg'
        try:
            image = QImage(self.scene.sceneRect().size().toSize(), QImage.Format_ARGB32)
            painter = QPainter(image)
            self.scene.render(painter)
            painter.end()
            image.save(image_path)       
        except Exception as e:
            print('Error Code Fig 102',e)
        time.sleep(1)
        os.system(f'cd temp & mspaint paint.jpg')
        
    def image_handle(self,figmark_json):
        if self.submit_type == '单独标注':
            return
        else:
            self.figmark_json = figmark_json
            if self.submit_type == '识别标注':
                self.reco_and_mark()
            elif self.submit_type == '擦除标记':
                self.remove_figmark()
            elif self.submit_type == '一键标注':
                self.add_marks()
            elif self.submit_type == '转线条图':
                self.img_to_line()
            elif self.submit_type == '图像锐化':
                self.img_to_sharp()
    def reco_and_mark(self):
        self.pos_item_array = []
        self.reco_mark_flag = True
        for index,item in enumerate(self.figmark_json):
            mark = item['words']
            mark_pos = item['location']
            xt = mark_pos['left'] - len(mark)*3
            yt = mark_pos['top']
            # 覆盖原位置
            rect = QGraphicsRectItem(xt, yt, mark_pos['width'] + len(mark)*9, mark_pos['height'] + 5)
            rect.setBrush(QBrush(Qt.white)) # 白色填充
            rect.setPen(QPen(Qt.white)) #  白色边框
            self.scene.addItem(rect)
            # 增加新文本
            txt = self.scene.addText(mark,QFont(self.font().family(), self.slider_fontsize.value()/2))
            txt.setPos(xt,yt)
            txt.setDefaultTextColor(QColor(self.line_color))
            if xt >= len(mark)*3:
                txt.setPos(xt, yt)
            else:
                txt.setPos(xt, yt)
            self.pos_item_array.append([txt,'','','','','','','','','','',xt,yt])
            self.table_allmarks.setItem(index, 0, QTableWidgetItem(mark))
        self.reco_mark_flag = False
    def img_to_sharp(self):
        # 读取图像
        img = cv2.imread(self.in_dir)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        Laplace_kernel = np.array([[-1,-1,-1],[-1, 9,-1],[-1,-1,-1]])  # 定义拉普拉斯算子
        # 应用锐化卷积核
        sharpened_img = cv2.filter2D(img, -1, Laplace_kernel)
        plt.subplot(1,1,1),plt.imshow(sharpened_img,'gray')
        plt.xticks([]),plt.yticks([])
        if '.png' in self.in_dir:
            path = self.in_dir.replace('.png','_temp.png')
        elif '.jpg' in self.in_dir:
            path = self.in_dir.replace('.jpg','_temp.jpg')
        elif '.bmp' in self.in_dir:
            path = self.in_dir.replace('.bmp','_temp.bmp')
        plt.savefig(path)
        self.reload_pic(path)

    def img_to_line(self):
        img=cv2.imdecode(np.fromfile(self.in_dir,dtype=np.uint8),-1)
        #将img转化成灰度图
        GrayImage=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
        # 中值滤波
        GrayImage= cv2.medianBlur(GrayImage,5)
        #二值图
        ret,th1 = cv2.threshold(GrayImage,127,200,cv2.THRESH_BINARY)
        # 轮廓线，3为Block size, 5为param1值
        th2 = cv2.adaptiveThreshold(GrayImage,200,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY,3,5)

        plt.subplot(1,1,1),plt.imshow(th2,'gray')
        plt.xticks([]),plt.yticks([])
        if '.png' in self.in_dir.lower():
            path = self.in_dir.lower().replace('.png','_temp.png')
        elif '.jpg' in self.in_dir.lower() or '.jpeg' in self.in_dir.lower():
            path = self.in_dir.lower().replace('.jpg','_temp.jpg').replace('.jpeg','_temp.jpg')
        elif '.bmp' in self.in_dir.lower():
            path = self.in_dir.lower().replace('.bmp','_temp.bmp')
        plt.savefig(path)
        self.reload_pic(path)

    def reload_pic(self,in_dir):
        self.clear_all()
        self.text_mark.setText('1')
        self.pos_item_array = []
        self.pos_item_array_temp = []
        self.table_allmarks.clearContents()
        self.pixmap = QPixmap(in_dir)
        self.scene.addItem(QGraphicsPixmapItem(self.pixmap))
        self.canvas_fig.setFixedSize(self.pixmap.width() + 15, self.pixmap.height() + 15)
        self.setFixedSize(self.pixmap.width() + 300, self.pixmap.height() + 50)
        
    def fn_load_pic(self): # 载入图片
        # self.in_dir = '000.png'
        self.in_dir, _ = QFileDialog.getOpenFileName(self, "Open file", "", "All files (*.*);;JPG documents(*.jpg);;BMP documents(*.bmp);; PNG documents(*.png)")
        if self.in_dir:
            self.reload_pic(self.in_dir)
            self.bt_submit.setEnabled(True)
            self.bt_submit.setStyleSheet('QPushButton {background-color: #e55f00 ; color:white} QPushButton:hover {background-color: #f69958}')
        else:
            return


    def clear_all(self): # 清空画布
        self.table_allmarks.clearContents()
        self.scene.clear()
        self.scene.setBackgroundBrush(QBrush(QColor(Qt.white)))
        self.canvas_fig.setFixedSize(600,600)
        self.setFixedSize(880, 615)
        self.bt_submit.setStyleSheet('QPushButton {background-color: #e55f00 ; color:grey} QPushButton:hover {background-color: #f69958}')
        self.bt_submit.setEnabled(False)
    def color_change(self): # 选择画笔颜色
        self.line_color = QColorDialog().getColor().name()
        if not self.line_color:
            self.line_color = 'black'
        self.bt_color.setStyleSheet("QPushButton {background-color:#19232d;color:"+ self.line_color + '} QPushButton:hover {background-color: #b3b3b3 ;color:'+ self.line_color+'}')
    def preview_edge(self,path): # 获取最大、最小点的坐标,并裁切
        # 图像读取
        img = self.imread_chinese(path)
        # 二值化
        ret, binary = cv2.threshold(img, 200, 255, cv2.THRESH_TRUNC)  # 这里指定threshold为阈值
        # Canny边缘检测
        canny = cv2.Canny(binary, 0, 100)  # 阈值0,100  较小的阈值将间断的边缘连接起来，较大的阈值检测图像中明显的边缘
        # 获取边缘最大、最小坐标
        ans, highest_h, highest_w, lowest_h, lowest_w = [], 0, 0, 100000, 100000
        highest_Coordinate, lowest_Coordinate = [0, 0], [0, 0]
        for h in range(0, canny.shape[0]):
            for w in range(0, canny.shape[1]):
                if canny[h, w] != 0:
                    ans = ans + [[h, w]]
                    if highest_h < h:
                        highest_h = h
                    if highest_w < w:
                        highest_w = w
                    highest_Coordinate = [highest_h, highest_w]
                    if lowest_h > h:
                        lowest_h = h
                    if lowest_w > w:
                        lowest_w = w
                    lowest_Coordinate = [lowest_h, lowest_w]
        crop = img[lowest_h:highest_h,lowest_w:highest_w]
        cv2.imencode('.jpg',crop)[1].tofile(path)
    def imread_chinese(self,path):
        with open(path, 'rb') as f:
            img = np.asarray(bytearray(f.read()), dtype="uint8")
            return cv2.imdecode(img, 1)
    def fn_figsave(self): #保存图片
        try:
            reply = QMessageBox.question(self, '裁切边缘空白', '是否裁切边缘空白？',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            image = QImage(self.scene.sceneRect().size().toSize(), QImage.Format_ARGB32)
            painter = QPainter(image)
            self.scene.render(painter)
            painter.end()
            path, _ = QFileDialog.getSaveFileName(self, "Save file", "未命名.jpg", "JPG documents(*.jpg);;BMP documents(*.bmp);; PNG documents(*.png);;All files (*.*)")
            if not path:
                return
            painter.end()
            image.save(path)
            
            if reply == QMessageBox.Yes:
                self.preview_edge(path)
        except Exception as e:
            print('Error Code Fig 101',e)
    def got_linepoint(self): #自动识别方位
        self.x1 = self.x0
        self.y1 = self.y0
        self.x2 = QCursor.pos().x() - self.pos().x() - 23
        self.y2 = QCursor.pos().y() - self.pos().y() - 50
        # 获取self.x2
        if self.x2 >= self.pixmap.width() - 25:
            self.x2 = self.pixmap.width() - 25
        elif self.x2 <= 20:
            self.x2 = 20
        else:
            pass
        # 获取self.y2
        if self.y2 >= self.pixmap.height() - 10:
            self.y2 = self.pixmap.height() - 10
        elif self.y2 <= 27:
            self.y2 = 27
        else:
            pass

        if self.x2 <= self.x1 and self.y2 < self.y1: #左上
            self.x3 = self.x2 - self.slider_fontsize.value() #横线长度
            self.xt = self.x2 - self.slider_fontsize.value()/2 #标注位置
        elif self.x2 <= self.x1 and self.y2 >= self.y1: #左下
            self.x3 = self.x2 - self.slider_fontsize.value()
            self.xt = self.x2 - self.slider_fontsize.value()/2
        elif self.x2 > self.x1 and self.y2 >= self.y1: #右下
            self.x3 = self.x2 + self.slider_fontsize.value()
            self.xt = self.x2 + self.slider_fontsize.value()/2
        elif self.x2 > self.x1 and self.y2 < self.y1: #右上
            self.x3 = self.x2 + self.slider_fontsize.value()
            self.xt = self.x2 + self.slider_fontsize.value()/2
        self.y3 = self.y2
        self.xt = self.xt - self.slider_fontsize.value()/3 - len(self.mark)
        self.yt = self.y2 - self.slider_fontsize.value()*0.7 - 13#标号与横线间距
        if self.combo_linetype.currentText() == '文字标注':
            if self.x2 <= self.x1:
                self.xt = self.xt - self.slider_fontsize.value()/3 - len(self.mark) + 15
            else:
                self.xt = self.xt - self.slider_fontsize.value()/3 - len(self.mark) - 5
            self.yt = self.y2 - self.slider_fontsize.value()*0.7 - 3
    def fn_mouse_press(self,event): 
        if not self.pixmap:
            return
        try:
            if event.button() == Qt.RightButton:
                return
            elif event.button() == Qt.LeftButton:
                if self.combo_submittype.currentText() not in ['单独标注','识别标注']:
                    return
                if self.combo_linetype.currentText() not in ['文字标注','线条标注','曲线标注']:
                    return
                self.mark = self.text_mark.text()
                if self.draw_yes == '0':
                    self.draw_yes = '1'
                    self.x0 = QCursor.pos().x() - self.pos().x() - 23
                    self.y0 = QCursor.pos().y() - self.pos().y() - 50
                    
                    self.got_linepoint()
                    temp_txt = self.scene.addText(self.mark,QFont(self.font().family(), self.slider_fontsize.value()/2))
                    temp_txt.setDefaultTextColor(QColor(self.line_color))
                    temp_txt.setPos(self.xt,self.yt)
                    if self.combo_linetype.currentText() == '文字标注':
                        self.pos_item_array_temp.append([temp_txt,'',''])
                    elif self.combo_linetype.currentText() == '线条标注':
                        pen = QPen(QColor(self.line_color),self.slider_linewidth.value())
                        temp_line_1 = self.scene.addLine(self.x1,self.y1,self.x2,self.y2, pen) # 起点的x y坐标,终点的x y
                        temp_line_2 = self.scene.addLine(self.x2,self.y2,self.x3,self.y3, pen)
                        self.pos_item_array_temp.append([temp_txt,temp_line_1,temp_line_2])

                elif self.draw_yes == '1':
                    self.draw_yes = '0'
                    self.got_linepoint()
                    txt = self.scene.addText(self.mark,QFont(self.font().family(), self.slider_fontsize.value()/2))
                    txt.setDefaultTextColor(QColor(self.line_color))
                    self.pos_item_array.append(['','','','','','','','','','','','',''])
                    if self.combo_linetype.currentText() == '文字标注':
                        txt.setPos(self.xt,self.yt)
                        for index,_ in enumerate(self.pos_item_array):
                            if self.pos_item_array[index] == ['','','','','','','','','','','','','']:
                                self.pos_item_array[index] = [txt,'','','','','','','','','','',self.xt,self.yt]
                                break
                    elif self.combo_linetype.currentText() == '线条标注':
                        txt.setPos(self.xt,self.yt)
                        pen = QPen(QColor(self.line_color),self.slider_linewidth.value())
                        line_1 = self.scene.addLine(self.x1,self.y1,self.x2,self.y2, pen) # 起点的x y坐标,终点的x y
                        line_2 = self.scene.addLine(self.x2,self.y2,self.x3,self.y3, pen)
                        for index,_ in enumerate(self.pos_item_array):
                            if self.pos_item_array[index] == ['','','','','','','','','','','','','']:
                                self.pos_item_array[index] = [txt,line_1,line_2,self.x0,self.y0,self.x1,self.y1,self.x2,self.y2,self.x3,self.y3,self.xt,self.yt]
                                break
                    elif self.combo_linetype.currentText() == '曲线标注':
                        txt.setPos(self.xt,self.yt)
                        curve_line = CurveItem(self.x1,self.y1,self.x2,self.y2,self.x3,self.y3,self.line_color,self.slider_linewidth)
                        self.scene.addItem(curve_line)
                        for index,_ in enumerate(self.pos_item_array):
                            if self.pos_item_array[index] == ['','','','','','','','','','','','','']:
                                self.pos_item_array[index] = [txt,curve_line,'',self.x0,self.y0,self.x1,self.y1,self.x2,self.y2,self.x3,self.y3,self.xt,self.yt]
                                break
                    # 添加列表
                    for index in range(0,100):
                        table_item_tmp = self.table_allmarks.item(index,0)
                        if table_item_tmp:
                            if not table_item_tmp.text():
                                # self.table_allmarks.setItem(index, 0, QTableWidgetItem(line_type))
                                self.table_allmarks.setItem(index, 0, QTableWidgetItem(self.mark))
                                break
                        elif not table_item_tmp:
                            # self.table_allmarks.setItem(index, 0, QTableWidgetItem(line_type))
                            self.table_allmarks.setItem(index, 0, QTableWidgetItem(self.mark))
                            break
                    # 递增mark
                    self.old_mark = self.text_mark.text()
                    if self.old_mark[-1] not in '1234567890':
                        if self.old_mark[-1] != 'z' and self.old_mark[-1] != 'Z':
                            self.add_mark = self.old_mark[0:-1] + chr(ord(self.old_mark[-1])+1)
                        else:
                            self.add_mark = self.old_mark
                    else:
                        self.add_mark = int(self.old_mark) + 1
                    self.text_mark.setText(str(self.add_mark))

        except Exception as e:
            print('Error Code 301',e)
        self.fn_remove_lineitem_motion() # 避免最后元素无法移除
    def fn_remove_lineitem_motion(self):
        try:
            self.scene.removeItem(self.pos_item_array_temp[-1][0])
        except:
            pass
        try:
            self.scene.removeItem(self.pos_item_array_temp[-1][1])
        except:
            pass
        try:
            self.scene.removeItem(self.pos_item_array_temp[-1][2])
        except:
            pass
        try:
            self.pos_item_array_temp.pop()
        except:
            pass 
    def fn_mouse_motion(self,event): # 鼠标移动
        if self.draw_yes == '1':
            try:
                self.fn_remove_lineitem_motion() # 移除上一个item
            except:
                pass
            if self.combo_linetype.currentText() in ['线条标注','曲线标注','文字标注']:
                self.got_linepoint()
                temp_txt = self.scene.addText(self.mark,QFont(self.font().family(), self.slider_fontsize.value()/2))
                temp_txt.setDefaultTextColor(QColor(self.line_color))
                temp_txt.setPos(self.xt,self.yt)
                if self.combo_linetype.currentText() == '文字标注':
                    self.pos_item_array_temp.append([temp_txt,'',''])
                elif self.combo_linetype.currentText() == '线条标注':
                    pen = QPen(QColor(self.line_color),self.slider_linewidth.value())
                    temp_line_1 = self.scene.addLine(self.x1,self.y1,self.x2,self.y2, pen) # 起点的x y坐标,终点的x y
                    temp_line_2 = self.scene.addLine(self.x2,self.y2,self.x3,self.y3, pen)
                    self.pos_item_array_temp.append([temp_txt,temp_line_1,temp_line_2])
                elif self.combo_linetype.currentText() == '曲线标注':
                    temp_curve_line = CurveItem(self.x1,self.y1,self.x2,self.y2,self.x3,self.y3,self.line_color,self.slider_linewidth)
                    self.scene.addItem(temp_curve_line)
                    self.pos_item_array_temp.append([temp_txt,temp_curve_line,''])
        else:
            return
    def remove_figmark(self):
        # self.get_figmark_pos()
        for _ in self.figmark_json:
            mark_pos = _['location']
            rect = QGraphicsRectItem(mark_pos['left'], mark_pos['top'], mark_pos['width'], mark_pos['height'])
            rect.setBrush(QBrush(Qt.white))
            rect.setPen(QPen(Qt.white))
            self.scene.addItem(rect)
    def add_marks(self):
        # self.get_figmark_pos()
        all_marks = self.text_allmarks.toPlainText().replace('\n','\u2029').split('\u2029')
        for _ in self.figmark_json:
            mark_in_fig = _['words']
            mark_pos = _['location']
            for mark in all_marks:
                if mark.split()[0] == mark_in_fig:
                    rect = QGraphicsRectItem(mark_pos['left'] - len(mark)*3, mark_pos['top'], mark_pos['width'] + len(mark)*9, mark_pos['height'] + 5)
                    rect.setBrush(QBrush(Qt.white)) # 白色填充
                    rect.setPen(QPen(Qt.white)) #  红色边框
                    self.scene.addItem(rect)
                    txt = self.scene.addText(mark.replace(' ',''),QFont(self.font().family(), self.slider_fontsize.value()/2))
                    txt.setDefaultTextColor(QColor(self.line_color))
                    if mark_pos['left'] >= len(mark)*3:
                        txt.setPos(mark_pos['left'] - len(mark)*3, mark_pos['top'])
                    else:
                        txt.setPos(mark_pos['left'], mark_pos['top'])
                    break
class CurveItem(QGraphicsItem):
    def __init__(self,x1,y1,x2,y2,x3,y3,line_color,slider_linewidth):
        super().__init__()
        self.x1 = x1
        self.x2 = x2
        self.x3 = x3
        self.y1 = y1
        self.y2 = y2
        self.y3 = y3
        self.line_color = line_color
        self.linewidth = slider_linewidth.value()
    def paint(self, painter, option, widget=None):
        painter.setPen(QPen(QColor(self.line_color),self.linewidth, Qt.SolidLine)) 
        path = QPainterPath()  # 创建QPainterPath对象
 
        # 使用曲线方法绘制样条曲线
        path.moveTo(self.x1,self.y1)  # 起点
        path.cubicTo(self.x1,self.y1, self.x2,self.y2, self.x3,self.y3)  # 控制点1, 控制点2, 终点

 
        painter.drawPath(path)  # 绘制路径
 
        # 返回绘制区域，这里我们绘制整个视图
        return QRectF(0, 0, 200, 200)
    

class BezierCurveWidget(QWidget):
    def __init__(self,x1,y1,x2,y2,x3,y3,line_color,slider_linewidth):
        super().__init__()
        self.x1 = x1
        self.x2 = x2
        self.x3 = x3
        self.y1 = y1
        self.y2 = y2
        self.y3 = y3
        self.line_color = line_color
        self.linewidth = slider_linewidth.value()
        self.setFixedSize(400, 300)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(self.line_color),self.linewidth)
        painter.setPen(pen)

        path = QPainterPath()
        path.moveTo(self.x1,self.y1)  # 起始点
        path.cubicTo(self.x2 - 10,self.y2 - 10, self.x2 + 10,self.y2 + 10, self.x3,self.y3)  # 控制点1, 控制点2, 终点
 
        painter.drawPath(path)
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5'))#, palette=qdarkstyle.light.palette.LightPalette))
    window = Figeditor('admin','')
    window.show()
    app.exec_()
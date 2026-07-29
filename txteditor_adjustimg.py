from main_general import *
import win32api,win32gui
# from txteditor_img2model import Jpg2cloud
import cv2
import os
import numpy as np
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import qtawesome as qta
import qdarkstyle
import sys
class Worker_single(QThread):
    progress = pyqtSignal(list)
    def __init__(self,img_dir,threshold,in_label):
        super().__init__()
        self.img_dir = img_dir
        self.threshold_1 = threshold
        self.in_label = in_label
        self.img_size = []
    def run(self):
        self.cut_edge(self.img_dir)
        self.progress.emit(self.img_size)
        self.in_label.setPixmap(QPixmap(self.img_dir))


    def imread_chinese(self,path):
        with open(path, 'rb') as f:
            img = np.asarray(bytearray(f.read()), dtype="uint8")
            return cv2.imdecode(img, 1)

    def cut_edge(self,img_dir): # 获取最大、最小点的坐标,并裁切
        # 图像读取
        # img = cv2.imread(img_dir, 1) # 直接read无法识别中文路径
        img = self.imread_chinese(img_dir)
        # 二值化
        ret, binary = cv2.threshold(img, self.threshold_1, 255, cv2.THRESH_TRUNC)  # 这里指定threshold为阈值
        # Canny边缘检测
        canny = cv2.Canny(binary, 0, self.threshold_1)  # 阈值0,100  较小的阈值将间断的边缘连接起来，较大的阈值检测图像中明显的边缘
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
        img_size = [int(highest_w-lowest_w),int(highest_h-lowest_h)]
        crop = img[lowest_h:highest_h,lowest_w:highest_w]
        # if lowest_h and lowest_w:
        # cv2.imwrite(img_dir, crop, [cv2.IMWRITE_JPEG_QUALITY, 100]) # 无法识别中文路径
        cv2.imencode('.jpg',crop)[1].tofile(img_dir)
        return img_size
class Worker_Adjust(QThread):
    progress = pyqtSignal(list)
    def __init__(self,threshold,text_status,label_array):
        super().__init__()
        self.object_size = []
        self.threshold_1 = threshold
        # img_dic  # {0:dir_1,1:dir_2,2:dir_3,3:dir_4,4:dir_5,5:dir_6}
        self.text_status = text_status
        self.label_array = label_array
    def run(self):
        global img_dic
        for img_index in img_dic: # img_dic[index] = file_dir  #0 zhu 1 hou 2 zuo 3 you 4 fu 5 yang 6 li
            try:
                img_dir = img_dic[img_index] 
                if img_index == 0: #主视图
                    self.text_status.append(f'> 主视图裁剪完成')
                    continue
                elif img_index == 1: #后视图
                    self.img_size_hou = self.cut_edge(img_dir)
                    self.text_status.append(f'> 后视图裁剪完成')
                elif img_index == 2:#左视图
                    self.img_size_zuo = self.cut_edge(img_dir)
                    self.text_status.append(f'> 左视图裁剪完成')

                elif img_index == 3:#右视图
                    self.img_size_you = self.cut_edge(img_dir)
                    self.text_status.append(f'> 右视图裁剪完成')
                elif img_index == 4:#俯视图
                    self.img_size_fu = self.cut_edge(img_dir)
                    self.text_status.append(f'> 俯视图裁剪完成')

                elif img_index == 5:#仰视图
                    self.img_size_yang = self.cut_edge(img_dir)
                    self.text_status.append(f'> 仰视图裁剪完成')

                elif img_index == 6:#立体图
                    self.img_size = self.cut_edge(img_dir)
                    self.text_status.append(f'> 立体图裁剪完成')
            except Exception as e:
                print('>> Error Code 401',img_index,e)
        # 以裁剪后的尺寸重新加载图片
        for index in range(0,9): 
            img_dir = img_dic[index]
            if img_dir:
                # print('Code 401',index,img_dir)
                self.resize_label_img(self.label_array[index],img_dir)

        self.get_object_size()
        for fig_num in range(1,6):
            try:
                self.adjust_size(fig_num)
            except Exception as e:
                print(e)
        self.progress.emit(self.object_size)
        # 以调整后的尺寸重新加载图片
        for index in range(0,9): 
            img_dir = img_dic[index]
            if img_dir:
                # print('Code 401',index,img_dir)
                self.resize_label_img(self.label_array[index],img_dir)
        self.text_status.append(f'> 全部视图 处理完成')
    def resize_label_img(self,label_component,dir):
        img=QImage(dir)
        img_w = img.width()
        img_h = img.height()
        if img_w >= img_h:
            img_rate = img_w/300
            img_w = 300
            img_h = img_h/img_rate
        else:
            img_rate = img_h/300
            img_h = 300
            img_w = img_w/img_rate
        result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        label_component.setPixmap(QPixmap.fromImage(result))
    def imread_chinese(self,path):
        with open(path, 'rb') as f:
            img = np.asarray(bytearray(f.read()), dtype="uint8")
            return cv2.imdecode(img, 1)

    def cut_edge(self,img_dir): # 获取最大、最小点的坐标,并裁切
        # 图像读取
        # img = cv2.imread(img_dir, 1) # 直接read无法识别中文路径
        img = self.imread_chinese(img_dir)
        # 二值化
        ret, binary = cv2.threshold(img, self.threshold_1, 255, cv2.THRESH_TRUNC)  # 这里指定threshold为阈值
        # Canny边缘检测
        canny = cv2.Canny(binary, 0, self.threshold_1)  # 阈值0,100  较小的阈值将间断的边缘连接起来，较大的阈值检测图像中明显的边缘
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
        img_size = [int(highest_w-lowest_w),int(highest_h-lowest_h)]
        crop = img[lowest_h:highest_h,lowest_w:highest_w]
        # if lowest_h and lowest_w:
        # cv2.imwrite(img_dir, crop, [cv2.IMWRITE_JPEG_QUALITY, 100]) # 无法识别中文路径
        cv2.imencode('.jpg',crop)[1].tofile(img_dir)
        return img_size
    def resize_img(self,in_dir,out_dir,rate_w,rate_h): # x_abs,y_abs  x,y方向上的缩放比例
        # img = cv2.imread(in_dir,1) # 直接read无法识别中文路径
        img = self.imread_chinese(in_dir)
        h, w = img.shape[:2]
        # 根据比例缩放尺寸
        w_n,h_n = int(w*rate_w),int(h*rate_h)
        new_img = cv2.resize(img, (w_n,h_n), interpolation=cv2.INTER_AREA)
        # cv2.imwrite(out_dir, new_img, [cv2.IMWRITE_JPEG_QUALITY, 100]) #  100 最高质量  默认95 无法识别中文路径
        cv2.imencode('.jpg',new_img)[1].tofile(out_dir)
    def get_object_size(self): # 获取物品尺寸
        global img_dic
        try:
            img_size_1 = [0,0]
            img_size_2 = [0,0]
            # self.img_front_dir = img_dic[0] #主视图dir
            # self.img_left_dir = img_dic[2] #左视图dir
            img_size_1[0],img_size_1[1] = self.cut_edge(img_dic[0])
            img_size_2[0],img_size_2[1] = self.cut_edge(img_dic[2])
            print(f'> Old Size {img_size_1},{img_size_2}')
            abs_rate = round(img_size_1[1]/img_size_2[1],10)
            self.resize_img(img_dic[2],img_dic[2],abs_rate,abs_rate) # 覆盖原图
            img_size_2[0],img_size_2[1] = self.cut_edge(img_dic[2])
            print(f'New Size {img_size_1},{img_size_2}')
            self.object_size = [img_size_1[0],img_size_1[1],img_size_2[0]]
            print(f'产品尺寸 宽×高×厚:{self.object_size}')
            self.text_status.append(f'产品尺寸 宽×高×厚:\n{self.object_size}')
        except Exception as e:
            print('Error Code 301',e)
    def adjust_size(self,fig_num):
        global img_dic
        if fig_num == 1: #后视图
            rate_w = round(self.object_size[0]/self.img_size_hou[0],10) # object_size  宽  高  厚
            rate_h = round(self.object_size[1]/self.img_size_hou[1],10)
            self.resize_img(img_dic[fig_num],img_dic[fig_num],rate_w,rate_h)
            self.text_status.append(f'> 后视图调整完成')
        elif fig_num == 2:#左视图
            rate_w = round(self.object_size[2]/self.img_size_zuo[0],10)
            rate_h = round(self.object_size[1]/self.img_size_zuo[1],10)
            # self.resize_img(img_dic[fig_num],img_dic[fig_num],rate_w,rate_h)
            self.text_status.append(f'> 左视图调整完成')
        elif fig_num == 3:#右视图
            rate_w = round(self.object_size[2]/self.img_size_you[0],10)
            rate_h = round(self.object_size[1]/self.img_size_you[1],10)
            self.resize_img(img_dic[fig_num],img_dic[fig_num],rate_w,rate_h)
            self.text_status.append(f'> 右视图调整完成')
        elif fig_num == 4:#俯视图
            rate_w = round(self.object_size[0]/self.img_size_fu[0],10)
            rate_h = round(self.object_size[2]/self.img_size_fu[1],10)
            self.resize_img(img_dic[fig_num],img_dic[fig_num],rate_w,rate_h)
            self.text_status.append(f'> 俯视图调整完成')
        elif fig_num == 5:#仰视图
            rate_w = round(self.object_size[0]/self.img_size_yang[0],10)
            rate_h = round(self.object_size[2]/self.img_size_yang[1],10)
            self.resize_img(img_dic[fig_num],img_dic[fig_num],rate_w,rate_h)
            self.text_status.append(f'> 仰视图调整完成')
class Design_Adjust(QWidget):
    def __init__(self):
        super().__init__()
        self.threshold_1 = 200
        self.threshold_2 = 100
        self.main_ui()
    def main_ui(self):
        global img_dic
        self.window_adjust_layout = QGridLayout()
        self.setLayout(self.window_adjust_layout)
        self.move(400, 100)
        self.setFixedSize(1070,850)

        self.setWindowTitle("FigAdjust ")
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))

        self.file_list_dir = [] # 批量导入
        img_dic = {0:'',1:'',2:'',3:'',4:'',5:'',6:'',7:'',8:''}
        # 顶部画布
        self.label_fig_li = FileDropLabel('立体图\n右键清空',7)
        self.label_fig_li.setMinimumHeight(300)
        self.label_fig_fu = FileDropLabel('俯视图\n右键清空',5)
        self.label_fig_fu.setMinimumHeight(300)
        self.label_fig_hou = FileDropLabel('后视图\n右键清空',2)
        self.label_fig_hou.setMinimumHeight(300)

        # 中部画布
        self.label_fig_zuo = FileDropLabel('左视图\n右键清空',3)
        self.label_fig_zuo.setMinimumHeight(300)
        self.label_fig_zhu = FileDropLabel('主视图\n右键清空',1)
        self.label_fig_zhu.setMinimumHeight(300)
        self.label_fig_you = FileDropLabel('右视图\n右键清空',4)
        self.label_fig_you.setMinimumHeight(300)
        # 底部画布
        self.label_fig_7 = FileDropLabel('状态图I\n右键清空',8)
        self.label_fig_7.setMinimumHeight(300)
        self.label_fig_yang = FileDropLabel('仰视图\n右键清空',6)
        self.label_fig_yang.setMinimumHeight(300)
        self.label_fig_9 = FileDropLabel('状态图II\n右键清空',9)
        self.label_fig_9.setMinimumHeight(300)

        # 按钮
        self.label_threshold_1 = QLabel('二值化阈值')
        self.label_threshold_1.setFixedWidth(70)

        self.slider_threshold_1 = QSlider(Qt.Horizontal)
        self.slider_threshold_1.setRange(0, 255)
        self.slider_threshold_1.setValue(200)
        self.slider_threshold_1.setMaximumWidth(100)
        self.slider_threshold_1.valueChanged.connect(self.change_value_1)
        self.slider_threshold_1.mouseReleaseEvent = self.slider_pressrelease_1

        self.label_threshold_2 = QLabel('边缘阈值')
        self.label_threshold_2.setFixedWidth(70)

        self.slider_threshold_2 = QSlider(Qt.Horizontal)
        self.slider_threshold_2.setRange(0, 255)
        self.slider_threshold_2.setValue(100)
        self.slider_threshold_2.setMaximumWidth(100)
        self.slider_threshold_2.valueChanged.connect(self.change_value_2)
        self.slider_threshold_2.mouseReleaseEvent = self.slider_pressrelease_2

        self.bt_load = QPushButton('一键导入')
        self.bt_load.setFixedSize(180,30)
        self.bt_load.clicked.connect(self.load_all_imgs)

        self.bt_submit = QPushButton('提  交')
        self.bt_submit.setFixedSize(180,30)
        # self.bt_submit.setEnabled(False)
        self.bt_submit.setStyleSheet('QPushButton {background-color: #e55f00 ; color:white} QPushButton:hover {background-color: #f69958}')
        self.bt_submit.clicked.connect(self.start_worker)

        self.bt_genmodel = QPushButton('生成模型')
        self.bt_genmodel.setFixedSize(180,30)
        self.bt_genmodel.setEnabled(False)

        self.text_status = QTextBrowser()
        self.text_status.setPlaceholderText('推荐尺寸：1000px*1000px以下\n使用前，请确保主视图和左视图的宽高比相同(立体图、状态图非必要)\n如通过拖拽图片，则文件名无要求\n如通过一键导入图片，则需将主后左右俯仰视图，按照01~06的顺序重命名\n如果产品边缘颜色与背景色接近，则先调整二值化阈值和边缘阈值，确保能够正确识别图片外轮廓\n推荐尺寸：1000px*1000px以下')
        self.text_status.setStyleSheet('border:none')
        self.text_status.setFixedSize(180,800)
        self.label_array = [self.label_fig_zhu,self.label_fig_hou,self.label_fig_zuo,self.label_fig_you,self.label_fig_fu,self.label_fig_yang,self.label_fig_li,self.label_fig_7,self.label_fig_9]
        self.window_adjust_layout.addWidget(self.label_fig_li,0,0,3,3)
        self.window_adjust_layout.addWidget(self.label_fig_fu,0,3,3,3)
        self.window_adjust_layout.addWidget(self.label_fig_hou,0,6,3,3)

        self.window_adjust_layout.addWidget(self.label_fig_zuo,4,0,3,3)
        self.window_adjust_layout.addWidget(self.label_fig_zhu,4,3,3,3)
        self.window_adjust_layout.addWidget(self.label_fig_you,4,6,3,3)

        self.window_adjust_layout.addWidget(self.label_fig_7,8,0,3,3)
        self.window_adjust_layout.addWidget(self.label_fig_yang,8,3,3,3)
        self.window_adjust_layout.addWidget(self.label_fig_9,8,6,3,3)

        self.window_adjust_layout.addWidget(self.bt_load,0,9,1,2)
        self.window_adjust_layout.addWidget(self.bt_submit,1,9,1,2)
        self.window_adjust_layout.addWidget(self.bt_genmodel,2,9,1,2)

        self.window_adjust_layout.addWidget(self.label_threshold_1,3,9,1,1)
        self.window_adjust_layout.addWidget(self.slider_threshold_1,3,10,1,1)
        self.window_adjust_layout.addWidget(self.label_threshold_2,4,9,1,1)
        self.window_adjust_layout.addWidget(self.slider_threshold_2,4,10,1,1)
        self.window_adjust_layout.addWidget(self.text_status,5,9,3,2)

    def load_all_imgs(self):
        global img_dic
        self.file_list_dir = QFileDialog.getExistingDirectory(self, "选择文件夹", "")#,"BMP IMAGES (*.bmp);;JPG IMAGES(*.jpg);;Docx IMAGES(*.png);;All files (*.*)")
        if self.file_list_dir:
            for root, dirs, files in os.walk(self.file_list_dir):
                all_files = files
            for index,label_component in enumerate(self.label_array):
                index += 1
                try:
                    if '%02d.jpg' % index in all_files or '%02d.jpeg' % index in all_files:
                        file_dir = self.file_list_dir+ '/%02d.jpg' % index
                    elif '%02d.png' % index in all_files:
                        file_dir = self.file_list_dir+ '/%02d.png' % index
                    elif '%02d.bmp' % index in all_files:
                        file_dir = self.file_list_dir+ '/%02d.bmp' % index
                    else:
                        file_dir = ''
                        continue
                    self.resize_label_img(label_component,file_dir)
                    img_dic[index - 1] = file_dir  #0 zhu 1 hou 2 zuo 3 you 4 fu 5 yang 6 li 7 状态1 8 状态2
                except Exception as e:
                    print(f'{index} Error Code 301',e)
        self.text_status.append('> 文件导入完成')
        self.bt_submit.setEnabled(True)
    def change_value_1(self):
        self.label_threshold_1.setText(str(self.slider_threshold_1.value()))
        self.threshold_1 = self.slider_threshold_1.value()
    def slider_pressrelease_1(self,event):
        self.label_threshold_1.setText('二值化阈值')
        self.preview_img_threshold()
    def change_value_2(self):
        self.label_threshold_2.setText(str(self.slider_threshold_2.value()))
        self.threshold_2 = self.slider_threshold_2.value()
    def slider_pressrelease_2(self,event):
        self.label_threshold_2.setText('边缘阈值')
        self.preview_img_threshold()
    def start_worker(self):
        global img_dic
        self.bt_submit.setEnabled(False)
        # 查验图片以正确加载
        for index in range(0,6):
            img_dir = img_dic[index]
            tmp_array = list('主后左右俯仰')
            if not img_dir:
                self.text_status.append(f'> 缺少{tmp_array[index]}视图')
                self.bt_submit.setEnabled(True)
                return
        self.bt_submit.setText('文件处理中')
        self.threshold_1 = self.slider_threshold_1.value()
        self.adjust_thread = Worker_Adjust(self.threshold_1,self.text_status,self.label_array)
        self.adjust_thread.progress.connect(self.update_image)
        self.adjust_thread.start()
    def update_image(self,object_size): # 重新加载 主后左右俯仰立
        global img_dic
        self.object_size = object_size  # 主视图为准  宽 高 厚
        for img_index in range(0,7): 
            try:
                label_component = self.label_array[img_index]
                img_dir = img_dic[img_index]
                self.reload_imgs(label_component,img_dir)
            except Exception as e:
                print('Error 404',e)
        self.bt_submit.setText('提  交')
        self.bt_submit.setEnabled(True)
    def preview_img_threshold(self):
        try:
            for img_index,label_component in enumerate(self.label_array): # img_dic[index] = file_dir  #0 zhu 1 hou 2 zuo 3 you 4 fu 5 yang 6 li
                img_temp = label_component.pixmap()
                img_temp.save('./temp/preview.jpg', quality = 95)
                self.preview_edge(label_component)
        except Exception as e:
            print('Error Code 201',e)
        # self.text_status.append('> 预览完成')
    def imread_chinese(self,path):
        with open(path, 'rb') as f:
            img = np.asarray(bytearray(f.read()), dtype="uint8")
            return cv2.imdecode(img, 1)
    def preview_edge(self,label_component): # 获取最大、最小点的坐标,并裁切
        # 图像读取
        # img = cv2.imread('./temp/preview.jpg', 1) # 直接read无法识别中文路径
        img = self.imread_chinese('./temp/preview.jpg')
        # 二值化
        ret, binary = cv2.threshold(img, self.threshold_1, 255, cv2.THRESH_TRUNC)  # 这里指定threshold为阈值
        # Canny边缘检测
        canny = cv2.Canny(binary, 0, self.threshold_2)  # 阈值0,100  较小的阈值将间断的边缘连接起来，较大的阈值检测图像中明显的边缘
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
        # cv2.imwrite('./temp/preview.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 100]) # 无法识别中文路径
        cv2.imencode('.jpg',crop)[1].tofile('./temp/preview.jpg')
        # self.resize_label_img(label_component,'./temp/preview.jpg')
        label_component.setPixmap(QPixmap('./temp/preview.jpg'))
    def resize_label_img(self,label_component,dir):
        img=QImage(dir)
        img_w = img.width()
        img_h = img.height()
        if img_w >= img_h:
            img_rate = img_w/300
            img_w = 300
            img_h = img_h/img_rate
        else:
            img_rate = img_h/300
            img_h = 300
            img_w = img_w/img_rate
        result=img.scaled(int(img_w),int(img_h),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        label_component.setPixmap(QPixmap.fromImage(result))
    def reload_imgs(self,label_component,dir):
        if max(self.object_size) == self.object_size[0]:
            zoom_rate = self.object_size[0]/300
            if zoom_rate == 0:
                return
            file_name = dir.split('/')[-1].split('.')[0]
            if file_name in ['01','02']:
                img=QImage(dir)
                img_w = 300
                img_h = self.object_size[1]/zoom_rate
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))
            elif file_name in ['03','04']:
                img=QImage(dir)
                img_w = self.object_size[2]/zoom_rate
                img_h = self.object_size[1]/zoom_rate
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))
            elif file_name in ['05','06']:
                img=QImage(dir)
                img_w = 300
                img_h = self.object_size[2]/zoom_rate
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))
            elif file_name in ['07','08']:
                img=QImage(dir)
                img_w = 300
                img_h = self.object_size[2]/zoom_rate
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))
        elif max(self.object_size) == self.object_size[1]:
            zoom_rate = self.object_size[1]/300
            if zoom_rate == 0:
                return
            if '/01.' in dir or '/02.' in dir:
                img=QImage(dir)
                img_w = self.object_size[0]/zoom_rate
                img_h = 300
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))
            elif '/03.' in dir or '/04.' in dir:
                img=QImage(dir)
                img_w = self.object_size[2]/zoom_rate
                img_h = 300
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))
            elif '/05.' in dir or '/06.' in dir:
                img=QImage(dir)
                img_w = self.object_size[0]/zoom_rate
                img_h = self.object_size[2]/zoom_rate
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))
        elif max(self.object_size) == self.object_size[2]:
            zoom_rate = self.object_size[2]/300
            if zoom_rate == 0:
                return
            if '/01.' in dir or '/02.' in dir:
                img=QImage(dir)
                img_w = self.object_size[0]/zoom_rate
                img_h = self.object_size[1]/zoom_rate
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))
            elif '/03.' in dir or '/04.' in dir:
                img=QImage(dir)
                img_w = 300
                img_h = self.object_size[1]/zoom_rate
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))
            elif '/05.' in dir or '/06.' in dir:
                img=QImage(dir)
                img_w = self.object_size[0]/zoom_rate
                img_h = 300
                result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                label_component.setPixmap(QPixmap.fromImage(result))

class FileDropLabel(QLabel):
    def __init__(self,label_txt,index):
        super().__init__()
        self.label_txt = label_txt 
        self.setAcceptDrops(True)  # 设置控件接受拖放事件
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(300)
        self.setMaximumWidth(300)
        self.setText(label_txt)
        self.setToolTip(label_txt)
        # self.resizeEvent = self.label_change_event
        self.dir = ''
        self.index = index
        self.mousePressEvent = self.fn_mouse_right_click
    def fn_mouse_right_click(self,event):
        global img_dic
        if event.button() == 2:
            img_dic[self.index] = ''
            self.setPixmap(QPixmap(""))
            self.setText(self.label_txt)

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
        result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        self.setPixmap(QPixmap.fromImage(result))
    def resize_label_img(self):
        global img_dic
        if 'pdf' in self.dir or 'doc' in self.dir:
            return
        img = QImage(self.dir)
        img_dic[self.index-1] = self.dir
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
        result=img.scaled(img_w,img_h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        self.setPixmap(QPixmap.fromImage(result))
if __name__ == '__main__':
    ct = win32api.GetConsoleTitle()
    hd = win32gui.FindWindow(0, ct)
    win32gui.ShowWindow(hd, 0)
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5'))#, palette=qdarkstyle.light.palette.LightPalette))
    window = Design_Adjust()
    window.show()
    app.exec_()

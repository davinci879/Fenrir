import os
import tkinter as tk
import tkinter.messagebox
from threading import Thread
from tkinter import IntVar, filedialog, ttk

import cv2
import ttkthemes
import windnd
from PIL import Image, ImageGrab, ImageSequence, ImageTk

img_dic = {0:'',1:'',2:'',3:'',4:'',5:'',6:'',7:'',8:''} # 主 后 左 右 俯 仰 立 状态I 状态II
def main(in_conn,window_main,user_login,label_lefttimes): 
    def remove_background(img):
        return
    def load_edge_posxy(img_dir,threshold): # 获取最大、最小点的坐标
        # 图像读取
        img = cv2.imread(img_dir, 1)
        # 二值化
        ret, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_TRUNC)  # 这里指定threshold为阈值
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
        img_size = [int(highest_w-lowest_w),int(highest_h-lowest_h)]  
        crop = img[lowest_h:highest_h,lowest_w:highest_w]
        # print(f"Lowest {lowest_Coordinate} Highest {highest_Coordinate} Image_size{img_size}")
        # if '01' in img_dir:
        #     # 图像展示
        #     plt.rcParams['font.sans-serif']=['宋体'] #用来正常显示中文标签 
        #     plt.rcParams['axes.unicode_minus']=False #用来正常显示负号 #有中文出现的情况，需要u'内容'
        #     plt.figure(figsize=(10, 8), dpi=100)
        #     plt.subplot(121), plt.imshow(img, cmap=plt.cm.gray), plt.title('原图')
        #     plt.xticks([]), plt.yticks([])
        #     plt.plot(highest_w, highest_h, 'ro', 'MarkerSize', 1)
        #     plt.plot(lowest_w, lowest_h, 'ro', 'MarkerSize', 1)
        #     plt.subplot(122), plt.imshow(canny, cmap=plt.cm.gray), plt.title('边缘识别，请确保边缘能被正确识别')
        #     plt.xticks([]), plt.yticks([])
        #     plt.show()
        if lowest_h != 0 and lowest_w != 0:
            if not file_over_write:
                img_dir = img_dir.replace('.jpg','_temp.jpg').replace('.jpeg','_temp.jpeg')
            cv2.imwrite(img_dir, crop, [cv2.IMWRITE_JPEG_QUALITY, 100])
        redpi_img(img_dir)
        return img_size
    def redpi_img(in_dir):
        im = Image.open(in_dir)
        im.convert('RGB')
        # in_dir = in_dir.split('.')[0]+'.jpg'
        im.save(in_dir,'jpeg',quality=100,dpi=(300.0,300.0))
    def resize_img(in_dir,out_dir,rate_w,rate_h): # x_abs,y_abs  x,y方向上的缩放比例
        img = cv2.imread(in_dir,1)
        h, w = img.shape[:2]
        # 根据比例缩放尺寸
        h_n,w_n = int(h*rate_h), int(w*rate_w)
        new_img = cv2.resize(img, (w_n,h_n), interpolation=cv2.INTER_AREA)
        # cv2.imshow('new_img', new_img)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()
        if not file_over_write:
            out_dir = out_dir.replace('.jpg','_temp.jpg').replace('.jpeg','_temp.jpeg')
        cv2.imwrite(out_dir, new_img, [cv2.IMWRITE_JPEG_QUALITY, 100]) #  100 最高质量  默认95
        redpi_img(out_dir)
    def get_object_size(img_dic,input_threshold): # 获取物品尺寸
        object_size = [0,0,0] # width,height,depth
        img_size_1 = [0,0]
        img_size_2 = [0,0]
        img_front_dir = img_dic[0] #主视图dir
        img_left_dir = img_dic[2] #左视图dir
        img_size_1[0],img_size_1[1] = load_edge_posxy(img_front_dir,input_threshold)
        img_size_2[0],img_size_2[1] = load_edge_posxy(img_left_dir,input_threshold)
        # print(f'>>>Old Size {img_size_1},{img_size_2}')
        abs_rate = round(img_size_1[1]/img_size_2[1],10)
        resize_img(img_left_dir,img_left_dir,abs_rate,abs_rate) # 覆盖原图
        img_size_2[0],img_size_2[1] = load_edge_posxy(img_left_dir,input_threshold)
        # print(f'New Size {img_size_1},{img_size_2}')
        object_size = [img_size_1[0],img_size_1[1],img_size_2[0]]
        print(f'>>>Object Size {object_size}')
        text_handleinfo.insert('insert',f'>>>产品尺寸 \n{object_size}\n')
        return object_size # 主视图为准  宽 高 厚

    def show_img_0(file_dir):
        global inserted_fig_5
        canvas_fig_5.delete(tk.ALL)
        fig = Image.open(file_dir)
        inserted_fig_5,fig = resize_image(fig)
        canvas_fig_5.create_image((140,140),image = inserted_fig_5)
        canvas_fig_5.pack()
    def show_img_1(file_dir):
        global inserted_fig_3
        canvas_fig_3.delete(tk.ALL)
        fig = Image.open(file_dir)
        inserted_fig_3,fig = resize_image(fig)
        canvas_fig_3.create_image((140,140),image = inserted_fig_3)
        canvas_fig_3.pack()
    def show_img_2(file_dir):
        global inserted_fig_4
        canvas_fig_4.delete(tk.ALL)
        fig = Image.open(file_dir)
        inserted_fig_4,fig = resize_image(fig)
        canvas_fig_4.create_image((140,140),image = inserted_fig_4)
        canvas_fig_4.pack()
    def show_img_3(file_dir):
        global inserted_fig_6
        canvas_fig_6.delete(tk.ALL)
        fig = Image.open(file_dir)
        inserted_fig_6,fig = resize_image(fig)
        canvas_fig_6.create_image((140,140),image = inserted_fig_6)
        canvas_fig_6.pack()
    def show_img_4(file_dir):
        global inserted_fig_2
        canvas_fig_2.delete(tk.ALL)
        fig = Image.open(file_dir)
        inserted_fig_2,fig = resize_image(fig)
        canvas_fig_2.create_image((140,140),image = inserted_fig_2)
        canvas_fig_2.pack()
    def show_img_5(file_dir):
        global inserted_fig_8
        canvas_fig_8.delete(tk.ALL)
        fig = Image.open(file_dir)
        inserted_fig_8,fig = resize_image(fig)
        canvas_fig_8.create_image((140,140),image = inserted_fig_8)
        canvas_fig_8.pack()
    def show_img_7(file_dir):
        global inserted_fig_9
        canvas_fig_1.delete(tk.ALL)
        fig = Image.open(file_dir)
        inserted_fig_9,fig = resize_image(fig)
        canvas_fig_1.create_image((140,140),image = inserted_fig_9)
        canvas_fig_1.pack()
    def adjust_size(img_dic,input_threshold,object_size):
        for i in range(0,6):# 去背景
            if removebg_checkvar.get() == 1:
                remove_background(img_dic[i])
                if i == 0:
                    print(f'>>>主视图 背景去除完成')
                    text_handleinfo.insert('insert',f'>>>主视图 背景去除完成\n')
                    show_img_0(img_dic[i])
                elif i == 1:
                    print(f'>>>后视图 背景去除完成')
                    text_handleinfo.insert('insert',f'>>>后视图 背景去除完成\n')
                    show_img_1(img_dic[i])
                elif i == 2:
                    print(f'>>>左视图 背景去除完成')
                    text_handleinfo.insert('insert',f'>>>左视图 背景去除完成\n')
                    show_img_2(img_dic[i])
                elif i == 3:
                    print(f'>>>右视图 背景去除完成')
                    text_handleinfo.insert('insert',f'>>>右视图 背景去除完成\n')
                    show_img_3(img_dic[i])
                elif i == 4:
                    print(f'>>>俯视图 背景去除完成')
                    text_handleinfo.insert('insert',f'>>>俯视图 背景去除完成\n')
                    show_img_4(img_dic[i])
                elif i == 5:
                    print(f'>>>仰视图 背景去除完成')
                    text_handleinfo.insert('insert',f'>>>仰视图 背景去除完成\n')
                    show_img_5(img_dic[i])
                elif i == 6:                    
                    print(f'>>>立体图 背景去除完成')
                    text_handleinfo.insert('insert',f'>>>立体图 背景去除完成\n')
                    show_img_7(img_dic[i])
        for i in range(0,6):
            if i == 0: #主视图
                print('>>>主视图 调整完成')
                text_handleinfo.insert('insert','>>>主视图 调整完成\n')
                show_img_0(img_dic[i])
            elif i == 1: #后视图
                img_size = load_edge_posxy(img_dic[i],input_threshold)
                rate_w = round(object_size[0]/img_size[0],10)
                rate_h = round(object_size[1]/img_size[1],10)
                resize_img(img_dic[i],img_dic[i],rate_w,rate_h)
                print('>>>后视图 调整完成')
                text_handleinfo.insert('insert','>>>后视图 调整完成\n')
                show_img_1(img_dic[i])
            elif i == 2:#左视图
                img_size = load_edge_posxy(img_dic[i],input_threshold)
                rate_w = round(object_size[2]/img_size[0],10)
                rate_h = round(object_size[1]/img_size[1],10)
                resize_img(img_dic[i],img_dic[i],rate_w,rate_h)
                print('>>>左视图 调整完成')
                text_handleinfo.insert('insert','>>>左视图 调整完成\n')
                show_img_2(img_dic[i])
            elif i == 3:#右视图
                img_size = load_edge_posxy(img_dic[i],input_threshold)
                rate_w = round(object_size[2]/img_size[0],10)
                rate_h = round(object_size[1]/img_size[1],10)
                resize_img(img_dic[i],img_dic[i],rate_w,rate_h)
                print('>>>右视图 调整完成')
                text_handleinfo.insert('insert','>>>右视图 调整完成\n')
                show_img_3(img_dic[i])
            elif i == 4:#俯视图
                img_size = load_edge_posxy(img_dic[i],input_threshold)
                rate_w = round(object_size[0]/img_size[0],10)
                rate_h = round(object_size[2]/img_size[1],10)
                resize_img(img_dic[i],img_dic[i],rate_w,rate_h)
                print('>>>俯视图 调整完成')
                text_handleinfo.insert('insert','>>>俯视图 调整完成\n')
                show_img_4(img_dic[i])
            elif i == 5:#仰视图
                img_size = load_edge_posxy(img_dic[i],input_threshold)
                rate_w = round(object_size[0]/img_size[0],10)
                rate_h = round(object_size[2]/img_size[1],10)
                resize_img(img_dic[i],img_dic[i],rate_w,rate_h) 
                print('>>>仰视图 调整完成')
                text_handleinfo.insert('insert','>>>仰视图 调整完成\n')
                show_img_5(img_dic[i])
            elif i == 6:#立体图
                img_size = load_edge_posxy(img_dic[i],input_threshold)
                print('>>>立体图 调整完成')
                text_handleinfo.insert('insert','>>>立体图 调整完成\n')
                show_img_7(img_dic[i])
            else:
                pass
        text_handleinfo.insert('insert','>>>全部视图 处理完成\n')
    def handle_file():
        def handle_file_t():
            for i in range(0,6):
                if not img_dic[i] and i == 0 or ('jpg' not in img_dic[i] and 'jpeg' in img_dic[i]): 
                    text_handleinfo.insert('insert','>>>缺少主视图 或 文件格式错误\n')
                    return
                if not img_dic[i] and i == 1 or ('jpg' not in img_dic[i] and 'jpeg' in img_dic[i]): 
                    text_handleinfo.insert('insert','>>>缺少后视图 或 文件格式错误\n')
                    return
                if not img_dic[i] and i == 2 or ('jpg' not in img_dic[i] and 'jpeg' in img_dic[i]): 
                    text_handleinfo.insert('insert','>>>缺少左视图 或 文件格式错误\n')
                    return
                if not img_dic[i] and i == 3 or ('jpg' not in img_dic[i] and 'jpeg' in img_dic[i]): 
                    text_handleinfo.insert('insert','>>>缺少右视图 或 文件格式错误\n')
                    return
                if not img_dic[i] and i == 4 or ('jpg' not in img_dic[i] and 'jpeg' in img_dic[i]): 
                    text_handleinfo.insert('insert','>>>缺少俯视图 或 文件格式错误\n')
                    return
                if (not img_dic[i] and i == 5) or ('jpg' not in img_dic[i] and 'jpeg' in img_dic[i]): 
                    text_handleinfo.insert('insert','>>>缺少仰视图 或 文件格式错误\n')
                    return
            adjust_size(img_dic,input_threshold,object_size)
        global file_over_write
        input_threshold = int(text_threshold.get('1.0','end').strip('\n\r\t'))
        text_handleinfo.delete('1.0','end')
        object_size = get_object_size(img_dic,input_threshold)  # width,height,depth
        if tk.messagebox.askyesno('Notice', f'是否覆盖原文件?<Y/N>'):
            file_over_write = True
        else:
            file_over_write = False
        if tk.messagebox.askyesno('Notice', f'当前阈值为{input_threshold}\n如无法识别完整边缘，请尝试提高阈值（上限254）后重试\n处理结果将直接覆盖原图片，请确保已经做好了备份\n是否继续?<Y/N>'):
            Thread(target=(handle_file_t)).start()
    #主窗体
    window_adjust_imgs = tk.Toplevel() 
    window_adjust_imgs.title(f'Hades')
    window_adjust_imgs.geometry('%dx%d+%d+%d' % (1040, 870, (window_adjust_imgs.winfo_screenwidth()- 1000 - 20)/2, (window_adjust_imgs.winfo_screenheight()- 870 -30)/2))
    window_adjust_imgs.resizable(0,0)
    # 菜单栏
    menu_bar = tk.Menu(window_adjust_imgs)
    # 菜单1
    file_menu = tk.Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label='文件', menu=file_menu)
    file_menu.add_command(label='运行', accelerator='Ctrl+R',command=lambda:[handle_file()])
    file_menu.add_separator()
    file_menu.add_command(label='退出', accelerator='Alt+F4')

    window_adjust_imgs.config(menu = menu_bar)# 删除无法显示菜单栏
    # 顶部框架
    frame_top = tk.Frame(window_adjust_imgs)
    frame_top.pack(padx=0,pady=0,anchor='nw',side='top')
    # 中部框架
    frame_middle = tk.Frame(window_adjust_imgs)
    frame_middle.pack(padx=0,pady=0,anchor='nw',side='top')
    # 底部框架
    frame_bottom = tk.Frame(window_adjust_imgs)
    frame_bottom.pack(padx=0,pady=0,anchor='nw',side='top')

    # 顶部画布
    canvas_fig_1 = tk.Canvas(frame_top,width=280,height=280,bg = 'grey')
    canvas_fig_1.pack(padx=0, pady=0, anchor='nw',side='left')
    canvas_fig_1.create_text(140, 140, text='立体图')

    canvas_fig_2 = tk.Canvas(frame_top,width=280,height=280,bg = 'grey')
    canvas_fig_2.pack(padx=0, pady=0, anchor='nw',side='left')
    canvas_fig_2.create_text(140, 140, text='俯视图')

    canvas_fig_3 = tk.Canvas(frame_top,width=280,height=280,bg = 'grey')
    canvas_fig_3.pack(padx=0, pady=0, anchor='nw',side='left')
    canvas_fig_3.create_text(140, 140, text='后视图')

    text_handleinfo = tk.Text(frame_top,height=21,width = 25,font=('宋体',10))
    text_handleinfo.pack(padx=5,pady=5,anchor='w',fill='y')
    text_handleinfo.insert('insert','注：\n使用前，请确保主视图和左视图的宽高比例无异常（立体图、状态图非必要）\n暂时仅支持JPG')
    # 中部画布
    canvas_fig_4 = tk.Canvas(frame_middle,width=280,height=280,bg = 'grey')
    canvas_fig_4.pack(padx=0, pady=0, anchor='nw',side='left')
    canvas_fig_4.create_text(140, 140, text='左视图')

    canvas_fig_5 = tk.Canvas(frame_middle,width=280,height=280,bg = 'grey')
    canvas_fig_5.pack(padx=0, pady=0, anchor='nw',side='left')
    canvas_fig_5.create_text(140, 140, text='主视图')

    canvas_fig_6 = tk.Canvas(frame_middle,width=280,height=280,bg = 'grey')
    canvas_fig_6.pack(padx=0, pady=0, anchor='nw',side='left')
    canvas_fig_6.create_text(140, 140, text='右视图')
    frame_middle_2 = tk.Frame(frame_middle)
    frame_middle_2.pack(padx=0,pady=0,anchor='nw',side='top')
    frame_middle_3 = tk.Frame(frame_middle_2)
    frame_middle_3.pack(padx=0,pady=0,anchor='nw',side='top')
    frame_middle_4 = tk.Frame(frame_middle_2)
    frame_middle_4.pack(padx=0,pady=0,anchor='nw',side='top')
    frame_middle_5 = tk.Frame(frame_middle_4)
    frame_middle_5.pack(padx=0,pady=0,anchor='nw',side='top')
    frame_middle_6 = tk.Frame(frame_middle_4)
    frame_middle_6.pack(padx=0,pady=0,anchor='nw',side='top')
    tk.Label(frame_middle_5,height=1,width = 5,text='阈值',font=('宋体',9)).pack(padx=2,pady=5,anchor='nw',side='left')
    text_threshold = tk.Text(frame_middle_5,height=1,width = 4,font=('宋体',9))
    text_threshold.pack(padx=5,pady=5,anchor='w',fill='both',side='left')
    text_threshold.insert('insert','200')
    removebg_checkvar = tk.IntVar()  # 去除背景
    removebg_ckbutton = tk.Checkbutton(frame_middle_5, text='去除背景',cursor='left_ptr', variable=removebg_checkvar, onvalue=1, offvalue=0)
    removebg_ckbutton.pack(padx=5, pady=0, side='left')
    tk.Label(frame_middle_6,height=1,width = 10,text='调整后尺寸',font=('宋体',9)).pack(padx=2,pady=5,anchor='nw',side='left')
    text_resize = tk.Text(frame_middle_6,height=1,width = 10,font=('宋体',9))
    text_resize.pack(padx=5,pady=5,anchor='w',fill='both',side='left')
    def load_all_imgs():
        file_dir = filedialog.askdirectory()+'/'
        if file_dir:
            for filename in os.listdir(file_dir):
                if 'jpg' not in file_dir+filename and 'jpeg' not in file_dir+filename:
                    print(f'>>>{file_dir+filename}文件格式错误，应为JPG\n')
                    text_handleinfo.insert('insert',f'>>>{file_dir+filename}文件格式错误，应为JPG\n')
                    return
            for filename in os.listdir(file_dir):
                if '1' in filename or '主' in filename:
                    img_dic[0] = f'{file_dir}/{filename}'
                    show_img_0(img_dic[0])
                elif '2' in filename or '后' in filename:
                    img_dic[1] = f'{file_dir}/{filename}'
                    show_img_1(img_dic[1])
                elif '3' in filename or '左' in filename:
                    img_dic[2] = f'{file_dir}/{filename}'
                    show_img_2(img_dic[2])
                elif '4' in filename or '右' in filename:
                    img_dic[3] = f'{file_dir}/{filename}'
                    show_img_3(img_dic[3])
                elif '5' in filename or '俯' in filename:
                    img_dic[4] = f'{file_dir}/{filename}'
                    show_img_4(img_dic[4])
                elif '6' in filename or '仰' in filename:
                    img_dic[5] = f'{file_dir}/{filename}'
                    show_img_5(img_dic[5])
                elif '7' in filename or '立' in filename:
                    img_dic[6] = f'{file_dir}/{filename}'
                    show_img_7(img_dic[6])
                elif '9' in filename or '状态II' in filename:
                    img_dic[8] = f'{file_dir}/{filename}' 
                elif '8' in filename or '状态I' in filename:
                    img_dic[7] = f'{file_dir}/{filename}' 
            text_handleinfo.insert('insert','>>>文件导入完成\n')
    ttk.Button(frame_middle_4,text='一键导入', width=9,command = load_all_imgs).pack(padx=(5,2), pady=0, anchor='nw',side='left')
    ttk.Button(frame_middle_4,text='运  行', width=9,command = handle_file).pack(padx=(10,0), pady=0, anchor='nw',side='left')

    # 底部画布
    canvas_fig_7 = tk.Canvas(frame_bottom,width=280,height=280,bg = 'grey')
    canvas_fig_7.pack(padx=0, pady=0, anchor='nw',side='left')
    canvas_fig_7.create_text(140, 140, text='状态图I')

    canvas_fig_8 = tk.Canvas(frame_bottom,width=280,height=280,bg = 'grey')
    canvas_fig_8.pack(padx=0, pady=0, anchor='nw',side='left')
    canvas_fig_8.create_text(140, 140, text='仰视图')

    canvas_fig_9 = tk.Canvas(frame_bottom,width=280,height=280,bg = 'grey')
    canvas_fig_9.pack(padx=0, pady=0, anchor='nw',side='left')
    canvas_fig_9.create_text(140, 140, text='状态图II')
    
    def resize_image(fig):
        # 获取图片尺寸
        fw = fig.width   
        fh = fig.height
        # 获取偏移量
        abx = int(140 - fw/2)
        aby = int(140 - fh/2)
        abs_constant = 1
        if abx >=0 and aby >=0:
            if fw >= fh: #横向标准
                print(f'>>>{fw},{fh}横向标准图片')
            elif fw < fh: #纵向标准
                print(f'>>>{fw},{fh}纵向标准图片')
        elif abx < 0 or aby < 0:
            if fw >= fh:  #横向非标准
                # print(f'>>>{fw},{fh}横向非标准图片')
                abs_constant = fw / 280
                fh_temp = fh * (1 / abs_constant)
                if fh_temp > 280:
                    abs_constant = fh / 280
                    fw = fw * (1 / abs_constant)
                    fh = 280
                    abx = int(140 - fw/2)
                    aby = 50
                else:
                    fh = fh_temp
                    fw = 280
                    abx = 50
                    aby = int(140 - fh/2)            
            elif fw < fh: #纵向非标准
                # print(f'>>>{fw},{fh}纵向非标准图片')
                abs_constant = fh / 280
                fw_temp = fw * (1 / abs_constant)
                if fw_temp > 280:
                    abs_constant = fw / 700
                    fh = fh * (1 / abs_constant)
                    fw = 280
                    abx = 50
                    aby = int(140 - fh/2) 
                else:
                    fw = fw_temp
                    fh = 280
                    abx = int(140 - fw/2)
                    aby = 50
            else:
                print(f'>>>{fw},{fh}其他')
            fig = fig.resize((int(fw) , int(fh)), Image.ANTIALIAS) 
            # print(f'>>>修改后尺寸：{fw},{fh},{abx},{aby}')
        inserted_fig = ImageTk.PhotoImage(fig)            
        return inserted_fig,fig
    def dragged_files_1(files):
        global inserted_fig_1
        file_dir = '\n'.join((item.decode('gbk') for item in files))
        img_dic[6] = file_dir
        if '.jpg' in file_dir or '.jpeg' in file_dir or '.png' in file_dir or '.bmp' in file_dir:
            canvas_fig_1.delete(tk.ALL)
            fig = Image.open(file_dir)
            inserted_fig_1,fig = resize_image(fig)
            canvas_fig_1.create_image((140,140),image = inserted_fig_1)
            canvas_fig_1.pack()
    def dragged_files_2(files):
        global inserted_fig_2
        file_dir = '\n'.join((item.decode('gbk') for item in files))
        img_dic[4] = file_dir
        if '.jpg' in file_dir or '.jpeg' in file_dir or '.png' in file_dir or '.bmp' in file_dir:
            canvas_fig_2.delete(tk.ALL)
            fig = Image.open(file_dir)
            inserted_fig_2,fig = resize_image(fig)
            canvas_fig_2.create_image((140,140),image = inserted_fig_2)
            canvas_fig_2.pack()
    def dragged_files_3(files):
        global inserted_fig_3
        file_dir = '\n'.join((item.decode('gbk') for item in files))
        img_dic[1] = file_dir
        if '.jpg' in file_dir or '.jpeg' in file_dir or '.png' in file_dir or '.bmp' in file_dir:
            canvas_fig_3.delete(tk.ALL)
            fig = Image.open(file_dir)
            inserted_fig_3,fig = resize_image(fig)
            canvas_fig_3.create_image((140,140),image = inserted_fig_3)
            canvas_fig_3.pack()
    def dragged_files_4(files):
        global inserted_fig_4
        file_dir = '\n'.join((item.decode('gbk') for item in files))
        img_dic[2] = file_dir
        if '.jpg' in file_dir or '.jpeg' in file_dir or '.png' in file_dir or '.bmp' in file_dir:
            canvas_fig_4.delete(tk.ALL)
            fig = Image.open(file_dir)
            inserted_fig_4,fig = resize_image(fig)
            canvas_fig_4.create_image((140,140),image = inserted_fig_4)
            canvas_fig_4.pack()
    def dragged_files_5(files):
        global inserted_fig_5
        file_dir = '\n'.join((item.decode('gbk') for item in files))
        img_dic[0] = file_dir
        if '.jpg' in file_dir or '.jpeg' in file_dir or '.png' in file_dir or '.bmp' in file_dir:
            canvas_fig_5.delete(tk.ALL)
            fig = Image.open(file_dir)
            inserted_fig_5,fig = resize_image(fig)
            canvas_fig_5.create_image((140,140),image = inserted_fig_5)
            canvas_fig_5.pack()
            canvas_fig_5.update()
    def dragged_files_6(files):
        global inserted_fig_6
        file_dir = '\n'.join((item.decode('gbk') for item in files))
        img_dic[3] = file_dir
        if '.jpg' in file_dir or '.jpeg' in file_dir or '.png' in file_dir or '.bmp' in file_dir:
            canvas_fig_6.delete(tk.ALL)
            fig = Image.open(file_dir)
            inserted_fig_6,fig = resize_image(fig)
            canvas_fig_6.create_image((140,140),image = inserted_fig_6)
            canvas_fig_6.pack()
    def dragged_files_7(files):
        global inserted_fig_7
        file_dir = '\n'.join((item.decode('gbk') for item in files))
        img_dic[7] = file_dir
        if '.jpg' in file_dir or '.jpeg' in file_dir or '.png' in file_dir or '.bmp' in file_dir:
            canvas_fig_6.delete(tk.ALL)
            fig = Image.open(file_dir)
            inserted_fig_7,fig = resize_image(fig)
            canvas_fig_7.create_image((140,140),image = inserted_fig_7)
            canvas_fig_7.pack()
    def dragged_files_8(files):
        global inserted_fig_8
        file_dir = '\n'.join((item.decode('gbk') for item in files))
        img_dic[5] = file_dir
        if '.jpg' in file_dir or '.jpeg' in file_dir or '.png' in file_dir or '.bmp' in file_dir:
            canvas_fig_8.delete(tk.ALL)
            fig = Image.open(file_dir)
            inserted_fig_8,fig = resize_image(fig)
            canvas_fig_8.create_image((140,140),image = inserted_fig_8)
            canvas_fig_8.pack()
    def dragged_files_9(files):
        global inserted_fig_9
        file_dir = '\n'.join((item.decode('gbk') for item in files))
        img_dic[8] = file_dir
        if '.jpg' in file_dir or '.jpeg' in file_dir or '.png' in file_dir or '.bmp' in file_dir:
            canvas_fig_9.delete(tk.ALL)
            fig = Image.open(file_dir)
            inserted_fig_9,fig = resize_image(fig)
            canvas_fig_9.create_image((140,140),image = inserted_fig_9)
            canvas_fig_9.pack()
            canvas_fig_9.update()
    windnd.hook_dropfiles(canvas_fig_1, func = dragged_files_1) # 立体图
    windnd.hook_dropfiles(canvas_fig_2, func = dragged_files_2) # 俯视图
    windnd.hook_dropfiles(canvas_fig_3, func = dragged_files_3) # 后视图
    windnd.hook_dropfiles(canvas_fig_4, func = dragged_files_4) # 左视图
    windnd.hook_dropfiles(canvas_fig_5, func = dragged_files_5) # 主视图
    windnd.hook_dropfiles(canvas_fig_6, func = dragged_files_6) # 右视图
    windnd.hook_dropfiles(canvas_fig_7, func = dragged_files_7) # 状态图I
    windnd.hook_dropfiles(canvas_fig_8, func = dragged_files_8) # 仰视图
    windnd.hook_dropfiles(canvas_fig_9, func = dragged_files_9) # 状态图II
    # window_adjust_imgs.protocol('WM_DELETE_WINDOW',window_close)
    window_adjust_imgs.mainloop() 

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from txteditor_adjustimg import Design_Adjust
from txteditor_figeditor import Figeditor
import qtawesome as qta
from openai import OpenAI
import sys
import webbrowser
import pdfplumber
import base64
from main_general import *
import docx
from volcenginesdkarkruntime import Ark
import qdarkstyle
import re
import requests
import json
import os
import operator
import random
import time
import win32api,win32gui

class MainWindow(QMainWindow):
    def __init__(self):
        global global_active_textcomponent,global_active_figmark
        super().__init__()
        self.FONT_SIZES = [4,5,6,7, 8, 9, 10, 11, 12, 13, 14, 18, 24,30,36,42,48,54,60,66,72,78,84,90,96]
        self.LINE_HEIGHT = ['0.0','0.2','0.5','1.0','1.5','2.0','2.5','3.0','3.5','4.0']
        self.HTML_EXTENSIONS = ['.htm', '.html']
        self.rename_history_array = ['发明 => 实用新型','实用新型 => 发明','^p^p => ^p',', => ，','( => （',') => ）']
        self.path = None
        self.start_drag_pos = (0,0)
        self.tab_drag_flag = False
        self.window_notebook = ''
        self.fig_dic = {}
        self.user_login = ''
        global window_adjust,window_figeditor,window_login
        self.window_adjust = window_adjust
        self.window_figeditor = window_figeditor
        self.window_login = window_login
        self.window_show = ''
        self.window_rep = ''
        self.window_symbol = ''
        self.window_help = ''
        self.window_api = ''
        self.window_decorate = ''
        self.window_continue = ''
        self.window_aihelp = ''
        self.window_aitrans = ''
        self.window_search = ''
        self.toolbar_bottom = ''
        self.window_table = ''
        self.window_location = ''
        self.brush_flag = False
        self.aihelp_search_history = {}
        self.aitrans_search_history = {}
        self.key_1, self.key_2, self.key_3, self.key_4, self.key_5 = '', '', '', '' ,''
        self.out_keywords = ''
        self.ori_keywords = ''
        self.total_key = ''
        self.table_x = 5
        self.table_y = 5
        self.temp_found_index = 0
        self.word_array = []
        self.type_v = ''
        self.char_format = ''
        self.character_array = []
        self.dragging = False
        self.db_flag = False
        self.window_state = 'normal'
        self.window_pos = ''
        self.drag_flag = False
        self.old_x,self.old_y = 0,0
        # 用于高亮颜色
        self.highlight_color = '#4a76d6'
        self.background_color = '#19232d'
        self.font_color = '#aa0000'
        self.type_cursor = ''
        self.tab_drag = False
        self.usual_words_array = [] # open('./data/words_data.txt','r',encoding='utf-8').read().split('\n')
        self.url_ai = open('./data/url_token.txt','r').read()
        self.load_txt_1 = open(f'./data/split_txt_1.txt','r',encoding='utf-8').read()
        self.load_txt_2 = open(f'./data/split_txt_2.txt','r',encoding='utf-8').read()
        self.main_ui()
    def wheelEvent(self,event):
        if event.modifiers() == Qt.ControlModifier and event.angleDelta().y() > 0:
            self.slider_fontsize.setValue(self.slider_fontsize.value()+1)
        elif event.modifiers() == Qt.ControlModifier and event.angleDelta().y() < 0:
            self.slider_fontsize.setValue(self.slider_fontsize.value()-1)
    def main_focusout(self,event):
        self.toolbar_bottom.setStyleSheet("background-color: grey")
        
    def fn_closeEvent(self,event):
        global user
        message_box = QMessageBox()#.question(self, '关闭程序', '即将关闭程序 <是/否>？',QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        message_box.setWindowTitle('关闭程序')
        message_box.setText('关闭程序 <是/否>？')
        message_box.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        message_box.button(QMessageBox.Yes).setText('是')
        message_box.button(QMessageBox.No).setText('否')
        reply = message_box.exec()
        if reply == QMessageBox.Yes:
            if self.window_notebook:self.window_notebook.close()
            if self.window_figeditor:self.window_figeditor.close()
            if self.window_adjust:self.window_adjust.close()
            if self.window_help:self.window_help.close()
            if self.window_api:self.window_api.close()
            if self.window_symbol:self.window_symbol.close()
            if self.window_rep:self.window_rep.close()
            if self.toolbar_bottom:self.toolbar_bottom.close()
            if self.window_aihelp:self.window_aihelp.close()
            if self.window_search:self.window_search.close()
            if self.window_continue:self.window_continue.close()
            if self.window_decorate:self.window_decorate.close()
            if self.window_table:self.window_table.close()
            if self.window_aitrans:self.window_aitrans.close()
            self.close()
    def add_showimg(self):
        self.window_showimg = QWidget()
        self.window_showimg.setMouseTracking(True)
        self.layout_windowshowimg = QGridLayout(self.window_showimg)
        self.window_showimg.setWindowTitle("说明书附图")
        self.window_showimg.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_showimg.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) # 隐藏标题栏

        self.tab_showimg = QTabWidget()
        self.lb_showimg_array = [FileDropLabel('请拖入图片') for i in range(20)]
        for tab_index,lb_showimg in enumerate(self.lb_showimg_array):
            self.tab_showimg.addTab(lb_showimg,f'图{tab_index + 1}')
            lb_showimg.setMinimumHeight(50)
            # lb_showimg.setMaximumHeight(400)
            lb_showimg.setMinimumWidth(50)
            
        self.bt_showimg = QPushButton('一键标注')
        self.bt_showimg.setFixedHeight(30)
        self.bt_showimg.setStyleSheet('QPushButton {background-color: #e55f00 ; color:white} QPushButton:hover {background-color: #f69958}')
        self.bt_showimg.clicked.connect(self.fn_txt2img)

        self.bt_close_con = QPushButton('转线条图')
        self.bt_close_con.setFixedHeight(30)
        
        self.layout_windowshowimg.addWidget(self.tab_showimg,0,0,1,2)
        # self.layout_windowshowimg.addWidget(self.bt_showimg,1,0,1,1)
        # self.layout_windowshowimg.addWidget(self.bt_close_con,1,1,1,1)

    def main_ui(self):
        global global_active_textcomponent,global_active_figmark
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.setWindowTitle(f'FENRIR ver{version}')
        self.setGeometry(300, 200, 1300, 750)
        self.setMouseTracking(True)
        self.setWindowFlags(Qt.FramelessWindowHint) # 隐藏标题栏 
        # 增加右键菜单
        self.add_mouse_rightclick()
        # 设置主文本框
        self.texteditor_tabwidget = QWidget()
        self.layoutwidget = QGridLayout(self.texteditor_tabwidget)
        self.setCentralWidget(self.texteditor_tabwidget)
        self.texteditor_tabwidget.setMouseTracking(True)
        # 设置输入框选项卡
        self.add_texteditors()
        # 附图标记联想输入
        self.add_markeditors()
        self.add_showimg()
        # 设置底部工具栏
        self.fn_bottom_bar()
        self.layoutwidget.addWidget(self.toolbar_bottom,1,0,1,1)
        
        self.dock_mark = QDockWidget('附图标记补全')
        # self.dock_mark.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures) # 不可浮动
        self.dock_mark.setWidget(self.main_widget_mark)
        self.dock_mark.setMinimumWidth(50)
        self.dock_mark.setMaximumWidth(1000)
        self.dock_mark.setMouseTracking(True)

        self.dock_showimg = QDockWidget('说明书附图')
        self.dock_showimg.setWidget(self.window_showimg)
        self.dock_showimg.setMinimumWidth(50)
        self.dock_showimg.setMouseTracking(True)

        self.dock_keywords = QDockWidget('关键词补全')
        self.dock_keywords.setWidget(self.main_widget_keywords)
        self.dock_keywords.setMinimumWidth(50)
        self.dock_keywords.setHidden(True) # 设置dock为隐藏状态
        self.dock_keywords.setMouseTracking(True)
         
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_mark)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_showimg)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_keywords)
        # 状态栏
        self.status = QStatusBar()
        self.status.setMouseTracking(True)
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setStatusBar(self.status)
        self.status.setToolTip('点击获取字数统计')
        self.status.mousePressEvent = self.count_words
        self.status.mouseDoubleClickEvent = self.status_dbclick
        ''' 工具栏 '''
        self.main_toolbar = QToolBar("特殊符号、插入表格、一键格式化、重置格式")
        self.main_toolbar.setIconSize(QSize(20, 20))
        self.main_toolbar.setAllowedAreas(Qt.AllToolBarAreas)
        self.addToolBar(self.main_toolbar)
        # 输入方式、高亮色、背景色
        self.type_toolbar = QToolBar("输入方式、字体格式、上下角标")
        self.type_toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(self.type_toolbar)
        # 选择输入方式
        self.combo_typev = QComboBox()
        self.combo_typev.addItems(['(Num)', '（Num）', '[Num]', 'Num','Void'])
        self.combo_typev.setToolTip('选择技术特征模式')
        self.combo_typev.setCurrentIndex(0)
        # 选择背景色
        self.choose_gcolor_action = QPushButton(" 背 ")
        self.choose_gcolor_action.setToolTip('自定义背景色')
        self.choose_gcolor_action.setStyleSheet(f"background-color: {self.background_color}")
        self.choose_gcolor_action.clicked.connect(self.choose_gcolor)
        
        # 设置字体
        self.combo_fonts = QFontComboBox()
        self.combo_fonts.setMaximumWidth(80)
        # 设置字体大小
        self.combo_fontsize = QComboBox()
        self.combo_fontsize.setToolTip('字体大小')
        self.combo_fontsize.addItems([str(s) for s in self.FONT_SIZES])
        self.combo_fontsize.setCurrentIndex(8)
        self.combo_fontsize.setFixedWidth(40)
        # self.combo_fontsize.currentIndexChanged.connect(self.on_fontsize_changed)
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

        self.bt_upper = QPushButton(QIcon(qta.icon('fa.superscript')),"")
        self.bt_upper.setToolTip('上角标')
        self.bt_upper.setCheckable(True)
        self.bt_upper.clicked.connect(self.font_upper)


        self.bt_lower = QPushButton(QIcon(qta.icon('fa.subscript')),"")
        self.bt_lower.setToolTip('下角标')
        self.bt_lower.setCheckable(True)
        self.bt_lower.clicked.connect(self.font_lower)

        self.bt_toggle = QPushButton(QIcon(qta.icon('fa.exchange')),"")
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
        # 设置字体的前景颜色
        self.bt_fontcolor = QPushButton(QIcon(qta.icon('ri.font-color')),'')
        # self.bt_fontcolor.setStyleSheet("color : #dfe1e2")
        self.bt_fontcolor.setStyleSheet("QPushButton {border-right: 0px}")

        self.bt_fontcolor.setToolTip('修改字体颜色')
        self.bt_fontcolor.clicked.connect(self.change_font_color)

        self.bt_color = QPushButton('▎')
        self.bt_color.setToolTip('选择颜色')
        self.bt_color.setStyleSheet("QPushButton {border-left: 0px}")
        self.bt_color.clicked.connect(self.choose_fontcolor)
    
        self.bt_brush = QPushButton(QIcon(qta.icon('ri.paint-brush-fill')),"") # 格式刷
        self.bt_brush.setToolTip('格式刷')
        self.bt_brush.setCheckable(True)
        self.bt_brush.clicked.connect(self.fn_brush)
        self.bt_brush.mouseDoubleClickEvent = self.fn_brush_dbclick

        self.bt_inserttable = QAction(QIcon(qta.icon('fa.table')),'插入表格')
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
        # 设置对齐方式
        self.toobar_alignl = QAction(QIcon(qta.icon('ei.align-left')),"左对齐")
        self.toobar_alignl.setCheckable(True)
        self.toobar_alignc = QAction(QIcon(qta.icon('ei.align-center')),"居中对齐")
        self.toobar_alignc.setCheckable(True)
        self.toobar_alignr = QAction(QIcon(qta.icon('ei.align-right')),"右对齐")
        self.toobar_alignr.setCheckable(True)
        self.toobar_alignj = QAction(QIcon(qta.icon('ei.align-justify')),"两端对齐")
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
        self.action_save_file = QAction(QIcon(qta.icon('fa.save')),"保存")
        self.action_save_file.triggered.connect(self.file_save)
        self.action_saveas_file = QAction(QIcon(qta.icon('mdi6.content-save-edit')),"另存为")
        self.action_saveas_file.triggered.connect(self.file_saveas)
        self.action_options = QAction(QIcon(qta.icon('fa.gears')),"设置")
        self.action_options.triggered.connect(self.fn_options)
        
        # 辅助工具
        self.tools_toolbar = QToolBar("常用工具")
        self.tools_toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(self.tools_toolbar)

        self.tool_figeditor = QAction(QIcon(qta.icon('ei.picasa')),"编辑图片", self)
        self.tool_figeditor.triggered.connect(self.fn_show_figeditor)
        self.tool_figeditor.setToolTip('编辑图片')

        self.tool_adjustfigs = QAction(QIcon(qta.icon('mdi6.webhook')),"一键改图", self)
        self.tool_adjustfigs.triggered.connect(self.fn_show_adjust)
        self.tool_adjustfigs.setToolTip('一键改图')
        
        self.tool_eureka = QAction(QIcon(qta.icon('fa5b.codepen')),"EUREKA", self)
        self.tool_eureka.triggered.connect(self.fn_eureka)
        self.tool_eureka.setToolTip('EUREKA')

        self.tool_reexam = QAction(QIcon(qta.icon('msc.law')),"复审无效", self)
        self.tool_reexam.triggered.connect(self.fn_reexam)
        self.tool_reexam.setToolTip('复审无效')

        self.tool_analyze = QAction(QIcon(qta.icon('ri.bubble-chart-line')),"专利分析", self)
        self.tool_analyze.triggered.connect(self.fn_analyze)
        self.tool_analyze.setToolTip('专利分析')

        self.tool_formatset = QAction(QIcon(qta.icon('fa.wrench')),"预设格式")
        self.tool_formatset.triggered.connect(self.fn_formatset)

        self.tool_loadimgs = QAction(QIcon(qta.icon('ri.image-add-line')),"批量导入附图")
        self.tool_loadimgs.triggered.connect(self.fn_loadimgs)

        self.tools_toolbar.addAction(self.tool_figeditor)
        self.tools_toolbar.addAction(self.tool_adjustfigs)
        self.tools_toolbar.addAction(self.tool_analyze)
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

        self.bt_showsymbol = QAction(QIcon(qta.icon('fa.slack')),'特殊字符(F3)')
        self.bt_showsymbol.triggered.connect(self.fn_show_symbol)
        self.bt_showsymbol.setShortcut('F3')
        
        self.tool_aiapi = QAction(QIcon(qta.icon('mdi.transit-connection-variant')),"AI接口(F4)")
        self.tool_aiapi.triggered.connect(self.fn_aiapi)
        self.tool_aiapi.setShortcut('F4')

        self.tools_toolbar_addition.addAction(self.tool_showhelp) # 使用帮助F1
        self.tools_toolbar_addition.addAction(self.tool_showbook) # 文本校验F2
        self.tools_toolbar_addition.addAction(self.bt_showsymbol) # 特殊符号F3
        self.tools_toolbar_addition.addAction(self.tool_aiapi) # AI_API

        # 顶部工具栏
        self.file_menu = self.menuBar()
        self.file_menu.setStyleSheet("border: none;background-color:black")
        self.fn_menu_bar() # 设置拖动、最大化、最小化、关闭按钮
        # self.fn_bottom_bar()
        sub_menu1 = self.file_menu.addMenu("&文件(F)")
        sub_menu1.addAction(self.action_open_file)
        sub_menu1.addSeparator()
        sub_menu1.addAction(self.action_save_file)
        sub_menu1.addAction(self.action_saveas_file)
        sub_menu1.addSeparator()
        sub_menu1.addAction(self.action_options)
        sub_menu1.addSeparator()
        exitAction = QAction(QIcon(qta.icon('mdi.exit-to-app')),"退出(X)", self.file_menu)
        exitAction.triggered.connect(self.close)
        sub_menu1.addAction(exitAction)

        sub_menu2 = self.file_menu.addMenu("&工具(T)")
        sub_menu2.addAction(self.tool_figeditor)
        sub_menu2.addAction(self.tool_adjustfigs)
        sub_menu2.addAction(self.tool_eureka)
        sub_menu2.addAction(self.tool_reexam)
        sub_menu2.addAction(self.tool_formatset)
        sub_menu2.addAction(self.tool_loadimgs)

        
        help_action = QAction(QIcon(qta.icon('mdi.help')),"使用帮助(H)", self)
        help_action.triggered.connect(lambda:[webbrowser.open("https://space.bilibili.com/418451046/channel/seriesdetail?sid=3179119")])
        sub_menu3 = self.file_menu.addMenu("&帮助(H)")
        sub_menu3.addAction(help_action)
        self.file_menu.addSeparator()
        about_action = QAction(QIcon(qta.icon('ei.heart')),"软件更新(A)", self.file_menu)
        sub_menu3.addAction(about_action)
        # 绑定editor功能
        global text_editor_array
        for editor in text_editor_array:
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
        # 将ContextMenuPolicy设置为Qt.CustomContextMenu # 否则无法使用customContextMenuRequested信号
        self.window_notebook = WindowBook(global_active_figmark,global_active_textcomponent,self.status,self.dock_mark)
        self.resizeEvent = self.window_change_event
        # self.fn_show_window()
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
    def fn_txt2img(self):
        return
    def fn_brush(self):
        global global_active_textcomponent
        if self.brush_flag == True:
            self.bt_brush.setChecked(False)
            self.brush_flag = False
            self.char_format = ''
        if self.brush_flag == False:
            if self.bt_brush.isChecked():
                cursor = global_active_textcomponent.textCursor()
                self.char_format = cursor.charFormat()
            else:
                if not self.char_format:
                    return
                cursor = global_active_textcomponent.textCursor()
                cursor.mergeCharFormat(self.char_format)
                global_active_textcomponent.mergeCurrentCharFormat(self.char_format)
    def fn_brush_dbclick(self,event):
        global global_active_textcomponent
        if self.brush_flag == False:
            cursor = global_active_textcomponent.textCursor()
            self.char_format = cursor.charFormat()
            self.bt_brush.setChecked(True)
            self.brush_flag = True
    def font_toggle(self):
        global toggle_flag,global_active_textcomponent
        cursor = global_active_textcomponent.textCursor()
        select_text = cursor.selectedText()
        if not select_text:
            return
        if toggle_flag == 0:
            select_text = select_text.upper()
            toggle_flag = 1
        else:
            select_text = select_text.lower()
            toggle_flag = 0
        cursor.movePosition(QTextCursor.Left, len(select_text))
        if len(select_text) > 1:
            cursor.deleteChar()
        cursor.deleteChar()
        cursor.insertText(select_text)
    def font_lower(self):
        global global_active_textcomponent
        cursor = global_active_textcomponent.textCursor()
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
        global global_active_textcomponent
        cursor = global_active_textcomponent.textCursor()
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
        global global_active_textcomponent
        if not global_active_textcomponent.textCursor().selectedText():
            self.slider_fontsize.setValue(self.slider_fontsize.value() - 1)
            font_size = self.slider_fontsize.value()
            change_num = int(abs(font_size - 12)*25/3)
            ori_html = global_active_textcomponent.toHtml()
            find_txt = re.findall('font-size:\d+pt',ori_html) + re.findall('font-size:\d+pt',ori_html)
            for _ in find_txt:
                ori_html = ori_html.replace(_,f'font-size:{font_size}pt')
            global_active_textcomponent.setHtml(ori_html)
            if font_size < 12:
                self.label_fontsize.setText(f'{100 - change_num}%')
            else:
                self.label_fontsize.setText(f'{100 + change_num}%')
    def fn_fontsize_up(self):
        global global_active_textcomponent
        if not global_active_textcomponent.textCursor().selectedText():
            self.slider_fontsize.setValue(self.slider_fontsize.value() + 1)
            font_size = self.slider_fontsize.value()
            change_num = int(abs(font_size - 12)*25/3)
            ori_html = global_active_textcomponent.toHtml()
            find_txt = re.findall('font-size:\d\dpt',ori_html) + re.findall('font-size:\dpt',ori_html)
            for _ in find_txt:
                ori_html = ori_html.replace(_,f'font-size:{font_size}pt')
            global_active_textcomponent.setHtml(ori_html)
            if font_size < 12:
                self.label_fontsize.setText(f'{100 - change_num}%')
            else:
                self.label_fontsize.setText(f'{100 + change_num}%')
    def slider_fontsize_changed(self):
        global global_active_textcomponent
        if not global_active_textcomponent.textCursor().selectedText():
            font_size = self.slider_fontsize.value()
            change_num = int(abs(font_size - 12)*25/3)
            ori_html = global_active_textcomponent.toHtml()
            find_txt = re.findall('font-size:\d\dpt',ori_html) + re.findall('font-size:\dpt',ori_html)
            for _ in find_txt:
                ori_html = ori_html.replace(_,f'font-size:{font_size}pt')
            global_active_textcomponent.setHtml(ori_html)
            if font_size < 12:
                self.label_fontsize.setText(f'{100 - change_num}%')
            else:
                self.label_fontsize.setText(f'{100 + change_num}%')
    def on_lineheight_changed(self):
        global line_height
        line_height = round(float(self.combo_lineheight.currentText()),1)
        ori_html = global_active_textcomponent.toHtml()
        find_txt = re.findall('margin-top:\d\dpx',ori_html) + re.findall('margin-top:\dpx',ori_html)
        for _ in find_txt:
            ori_html = ori_html.replace(_,f'margin-top:{line_height*5}px')
        find_txt = re.findall('margin-bottom:\d\dpx',ori_html) + re.findall('margin-bottom:\dpx',ori_html)
        for _ in find_txt:
            ori_html = ori_html.replace(_,f'margin-bottom:{line_height*5}px')
        global_active_textcomponent.setHtml(ori_html)

    def auto_complete(self,in_array,in_component):
        for index,_ in enumerate(in_array):
            if len(_.split()) >= 2:
                in_array[index] = _.split()[-1]
        self.completer = QCompleter(in_array)
        self.completer.setFilterMode(Qt.MatchContains)
        in_component.setCompleter(self.completer)
    def default_format(self):
        global global_active_textcomponent,global_active_figmark
        # 获取光标当前位置
        block_cursor = global_active_textcomponent.textCursor()
        para_line_number = block_cursor.blockNumber()
        total_paragraphs = global_active_textcomponent.document().blockCount()
        if para_line_number + 7 > total_paragraphs:
            para_line_number = total_paragraphs
        else:
            para_line_number += 7

        global_active_textcomponent.setFont(QFont("SimSun", 12))
        format = QTextCharFormat()
        # format.setForeground(QColor('#dfe1e2'))
        format.setBackground(QColor(Qt.transparent))
        format.setFont(QFont("SimSun", 12))
        format.setFontPointSize(12)
        self.slider_fontsize.setValue(12)
        self.label_fontsize.setText('100%')
        cursor = global_active_textcomponent.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(format)

        format.setFontPointSize(9)
        cursor = global_active_figmark.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(format)

        ori_html = global_active_textcomponent.toHtml()
        find_txt = re.findall('margin-top:\d\dpx',ori_html) + re.findall('margin-top:\dpx',ori_html)
        for _ in find_txt:
            ori_html = ori_html.replace(_,f'margin-top:0px')
        find_txt = re.findall('margin-bottom:\d\dpx',ori_html) + re.findall('margin-bottom:\dpx',ori_html)
        for _ in find_txt:
            ori_html = ori_html.replace(_,f'margin-bottom:0px')
        global_active_textcomponent.clear()
        global_active_textcomponent.setHtml(ori_html)
        self.on_lineheight_changed()
        # 重新定位
        block_cursor.movePosition(QTextCursor.Start)
        for _ in range(para_line_number):
            block_cursor.movePosition(QTextCursor.NextBlock)
        global_active_textcomponent.setTextCursor(block_cursor)
    def one_key_format(self):
        global global_active_textcomponent
        # 获取光标当前位置
        block_cursor = global_active_textcomponent.textCursor()
        para_line_number = block_cursor.blockNumber()
        total_paragraphs = global_active_textcomponent.document().blockCount()
        if para_line_number + 7 > total_paragraphs:
            para_line_number = total_paragraphs
        else:
            para_line_number += 7

        # if event.button() == 1:
        self.fn_reset_allformat()
        # line_height = int(self.combo_lineheight.currentText())
        format_array = open('./data/format_array.txt','r',encoding='utf-8').read().split()
        for i in range(1,30):
            format_array.append(f'步骤S{i}')
            format_array.append(f'步骤{i}')
            format_array.append(f'实施例{i}')
            format_array.append(f'证据{i}')
            format_array.append(f'{i}：')
            format_array.append(f'{i}\.')
            format_array.append(f'\u2029{i}\.')
            format_array.append(f'\u2029{i}、')
        for i in range(1,999):
            format_array.append(f'\u2029\[%04d]' % i)
        font_format = QTextCharFormat()
        font_format.setFontWeight(QFont.Bold)
        # global_active_textcomponent.setStyleSheet('margin-bottom: 20px; margin-top: 20px;')

        cursor = global_active_textcomponent.textCursor()
        for _ in format_array:
            matches = re.finditer(_, global_active_textcomponent.document().toPlainText().replace('\n','\u2029'))
            # 循环查找文档
            match_num = 0
            for match in matches:
                match_num += 1
                index = match.start()
                cursor.setPosition(index)
                bracket_count = len(re.findall(r'\\',_))
                if index - len(_) < 0:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(_))
                else:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(_) - bracket_count)
                cursor.mergeCharFormat(font_format)
        self.on_lineheight_changed()
        # 重新定位
        block_cursor.movePosition(QTextCursor.Start)
        for _ in range(para_line_number):
            block_cursor.movePosition(QTextCursor.NextBlock)
        global_active_textcomponent.setTextCursor(block_cursor)

    def fn_formatset(self):
        os.startfile('.\\data\\format_array.txt')
    def fn_loadimgs(self):
        file_list_dir = QFileDialog.getExistingDirectory(self, "选择文件夹","BMP IMAGES (*.bmp);;JPG IMAGES(*.jpg);;PNG IMAGES(*.png);;All files (*.*)")
        if file_list_dir:
            for root, dirs, files in os.walk(file_list_dir):
                all_files = files
            lb_index = 0
            for file in files:
                file_dir = file_list_dir+'/'+ file
                if file.split('.')[-1].lower() in ['jpg','jpeg','png','bmp']:
                    lb_img = self.lb_showimg_array[lb_index]
                    lb_index += 1
                    img = QImage(file_dir)
                    img_w = img.width()
                    img_h = img.height()
                    if img_w >= img_h:
                        img_rate = img_w/700
                        img_w = 700
                        img_h = img_h/img_rate
                    result=img.scaled(int(img_w),int(img_h),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                    lb_img.setPixmap(QPixmap.fromImage(result))
    def clear_select_format(self):
        global global_active_textcomponent
        format = QTextCharFormat()
        format.setForeground(QColor('#dfe1e2'))
        format.setBackground(QColor(Qt.transparent))
        # format.setFont('宋体')
        format.setFontPointSize(12)
        cursor = global_active_textcomponent.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        cursor.setCharFormat(format)
    def fn_bottom_bar(self):
        self.toolbar_bottom = QWidget()
        self.toolbar_bottom_layout = QHBoxLayout(self.toolbar_bottom)
        # self.toolbar_bottom_layout.setHorizontalSpacing(2)
        self.toolbar_bottom_layout.setContentsMargins(0,0,0,0)
        self.toolbar_bottom.setStyleSheet(f"background-color: {self.background_color}")
        self.toolbar_bottom.setMaximumHeight(40)
        # self.toolbar_bottom.setMouseTracking(True)

        self.text_tool_highlight = QLineEdit()
        self.text_tool_highlight.setMaximumWidth(200)
        self.text_tool_highlight.setPlaceholderText("高亮关键词")
        self.text_tool_highlight.setStyleSheet("color: white")
        self.text_tool_highlight.setToolTip('当前文档中显示所有关键词，多个关键词用空格间隔')
        self.text_tool_highlight.keyReleaseEvent = self.fn_highlighttxt_change

        bt_1 = QPushButton(QIcon('./UI/arrow_up.png'),"") # 上箭头
        bt_1.setStyleSheet('QPushButton:hover {background-color: grey}')
        bt_1.setToolTip('查找上一个')
        bt_1.setFixedSize(25,25)
        bt_2 = QPushButton(QIcon('./UI/arrow_down.png'),"")  # 下箭头
        bt_2.setStyleSheet('QPushButton:hover {background-color: grey}')
        bt_2.setToolTip('查找下一个')
        bt_2.setFixedSize(25,25)
        bt_1.clicked.connect(self.search_back)
        bt_2.clicked.connect(self.search_next)

        self.ck_1 = QCheckBox('区分大小写')

        lb_1 = QLabel()
        lb_1.setMinimumWidth(50)
        lb_1.setMaximumWidth(400)

        font = QFont()
        font.setPointSize(13)
        
        self.bt_fontsize_down = QPushButton('-')
        self.bt_fontsize_down.setFixedSize(25,25)
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
        self.bt_fontsize_up.setFixedSize(25,25)
        self.bt_fontsize_up.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.bt_fontsize_up.clicked.connect(self.fn_fontsize_up)
        self.bt_fontsize_up.setFont(font)

        self.label_fontsize = QLabel('100%')
        self.label_fontsize.setFixedWidth(40)

        self.toolbar_bottom_layout.addWidget(self.text_tool_highlight)
        self.toolbar_bottom_layout.addWidget(bt_1)
        self.toolbar_bottom_layout.addWidget(bt_2)
        self.toolbar_bottom_layout.addWidget(self.ck_1)
        self.toolbar_bottom_layout.addWidget(lb_1)
        self.toolbar_bottom_layout.addWidget(self.bt_fontsize_down)
        self.toolbar_bottom_layout.addWidget(self.slider_fontsize)
        self.toolbar_bottom_layout.addWidget(self.bt_fontsize_up)
        self.toolbar_bottom_layout.addWidget(self.label_fontsize)

    def search_next(self):# 查找下一个
        global global_active_textcomponent
        self.reset_textcomponentformat()
        cursor = global_active_textcomponent.textCursor()
        keyword = self.text_tool_highlight.text().strip(' ')
        all_txt = global_active_textcomponent.toPlainText()
        if self.ck_1.checkState() == 0:
            keyword = keyword.lower()
            all_txt = all_txt.lower()
        if self.temp_found_index == 0:
            self.found_index = all_txt.find(keyword)
        else:
            self.found_index = all_txt.find(keyword,self.temp_found_index + 1)
        if self.found_index == -1:
            self.temp_found_index = 0
            return
        else:
            self.temp_found_index = self.found_index
        if self.found_index:
            cursor.setPosition(self.found_index)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor,len(keyword))
            format = QTextCharFormat()
            format.setFontPointSize(12)
            format.setBackground(QColor("#d44b3e"))
            cursor.mergeCharFormat(format)
            # self.get_same_markindex(keyword,global_active_textcomponent,'#346792')
            self.status.showMessage(f"共匹配到{len(re.findall(keyword,all_txt))}个结果")
            global_active_textcomponent.setTextCursor(cursor)
    def search_back(self): # 查找上一个
        global global_active_textcomponent
        self.reset_textcomponentformat()
        cursor = global_active_textcomponent.textCursor()
        keyword = self.text_tool_highlight.text().strip(' ')
        if not keyword:
            return
        all_txt = global_active_textcomponent.toPlainText()
        if self.ck_1.checkState() == 0:
            keyword = keyword.lower()
            all_txt = all_txt.lower()
        if self.temp_found_index == 0:
            self.found_index = all_txt.rfind(keyword)
        else:
            self.found_index = all_txt.rfind(keyword,0,self.temp_found_index - 1)
        if self.found_index == -1:
            self.temp_found_index = 0
            return
        else:
            self.temp_found_index = self.found_index
        if self.found_index:
            cursor.setPosition(self.found_index)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor,len(keyword))
            format = QTextCharFormat()
            format.setFontPointSize(12)
            format.setBackground(QColor("#d44b3e"))
            cursor.mergeCharFormat(format)
            # self.get_same_markindex(keyword,global_active_textcomponent,'#346792')
            self.status.showMessage(f"共匹配到{len(re.findall(keyword,all_txt))}个结果")
            global_active_textcomponent.setTextCursor(cursor)
    # 高亮关键词
    def fn_highlighttxt_change(self,event):
        global global_active_textcomponent,global_active_figmark
        self.reset_textcomponentformat()
        keyword = self.text_tool_highlight.text()
        if not keyword:
            return
        if self.ck_1.checkState() == 0: # 未选中
            keyword = keyword.lower()
        self.highlight_array = keyword.replace('*', '').split()

        for _ in self.highlight_array:
            rnd_color = f'#FF{random.randint(1000, 9999)}'
            self.get_same_markindex(_,global_active_figmark,rnd_color)
            self.get_same_markindex(_,global_active_textcomponent,rnd_color)

    def fn_menu_bar(self): # 设置与menubar重叠的拖拽控件
        self.dragger_top = QWidget(self)
        self.dragger_top_layout = QHBoxLayout(self.dragger_top)
        self.dragger_top_layout.setContentsMargins(20,15,10,10) # 左 上 右 下
        self.dragger_top.setMouseTracking(True)

        self.dragger_top.setStyleSheet("background-color: black")
        self.dragger_top.setFixedSize(self.width() - 130, 40)
        self.dragger_top.move(self.pos().x() - 160, self.pos().y() - 211)

        self.dragger_top.mouseDoubleClickEvent = self.dragger_top_dbclick
        self.dragger_top.mousePressEvent = self.start_drag
        self.dragger_top.mouseReleaseEvent = self.window_pressrelease

        self.switch_associate = SwitchBtn_1()
        self.switch_associate.setFixedSize(55,20)
        self.switch_associate.setToolTip('联想输入 开/关\n输入对应的附图标记序号，即可弹出对应的附图标记全称\n按空格后根据选定的补全方式自动补全')

        self.switch_writetype = SwitchBtn_2()
        self.switch_writetype.setFixedSize(55,20)
        self.switch_writetype.setToolTip('模式切换 撰写/阅读\n拖拽选择相应文本后，高亮显示所有相同内容\n按住CTRL键可连续选择\nESC键 或 鼠标中键，取消所有高亮内容')

        self.switch_autocomplete = SwitchBtn_4()
        self.switch_autocomplete.setFixedSize(55,20)
        self.switch_autocomplete.setToolTip('自动补全 开启/关闭\n不在弹出对应的附图标记输入框\n无需按空格，即可自动补全光标位置之前的附图标记')

        self.search_fill_1 = QLabel()
        self.search_fill_1.setText('')
        self.search_fill_1.setMinimumWidth(5)
        self.search_fill_1.setMaximumWidth(600)
        self.search_fill_1.setFixedHeight(25)

        self.search_box = BreathTextEdit()
        font = QFont()
        font.setPointSize(9)

        self.search_box.setFont(font)
        self.search_box.setPlaceholderText(f'>> 搜索 [Fenrir ver{version}]')
        self.search_box.setFixedHeight(28)
        self.search_box.setMinimumWidth(25)
        self.search_box.setMaximumWidth(300)  
        self.search_box.setStyleSheet("QLineEdit {background-color: black;color: white} QLineEdit:focus{background-color:#212e3b;color: white}")
        self.search_box.keyReleaseEvent = self.fn_search_keyreleaseevent
        self.search_box.keyPressEvent = self.fn_search_keypressEvent
        self.search_box.setMouseTracking(True)

        self.search_fill_2 = QLabel()
        self.search_fill_2.setText('')
        self.search_fill_2.setMinimumWidth(5)
        self.search_fill_2.setFixedHeight(25)

        self.search_fill_1.setMouseTracking(True)
        self.search_fill_2.setMouseTracking(True)     

        self.tool_clearscreen = QPushButton('C')
        self.tool_clearscreen.setToolTip('清空当前文档')
        self.tool_clearscreen.setStyleSheet('QPushButton {background-color:#af3a22} QPushButton:hover {background-color:#fc5531}')
        self.tool_clearscreen.setFixedSize(30,20)
        self.tool_clearscreen.clicked.connect(self.fn_clearscreen)

        self.tool_panel_1 = QPushButton(QIcon('./UI/panel_left.png'),'')
        self.tool_panel_1.setToolTip('切换至左侧布局')
        self.tool_panel_1.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.tool_panel_1.setFixedSize(30,20)
        self.tool_panel_1.clicked.connect(self.fn_distribute_left)

        self.tool_panel_2 = QPushButton(QIcon('./UI/panel_top.png'),'')
        self.tool_panel_2.setToolTip('切换至顶端布局')
        self.tool_panel_2.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.tool_panel_2.setFixedSize(30,20)
        self.tool_panel_2.clicked.connect(self.fn_distribute_top)

        self.tool_minimize = QPushButton('—')
        self.tool_minimize.setToolTip('最小化')
        self.tool_minimize.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.tool_minimize.setFixedSize(30,20)
        self.tool_minimize.clicked.connect(lambda:[self.showMinimized()])

        self.tool_maximize = QPushButton(QIcon('./UI/max.png'),'')
        self.tool_maximize.setToolTip('最大化')
        self.tool_maximize.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.tool_maximize.setFixedSize(30,20)
        self.tool_maximize.clicked.connect(lambda:[self.dragger_top_dbclick(self.event)])

        self.tool_close = QPushButton('×')
        self.tool_close.setToolTip('关闭')
        self.tool_close.setStyleSheet('QPushButton:hover {background-color: grey}')
        self.tool_close.setFixedSize(30,20)
        self.tool_close.clicked.connect(lambda:[self.fn_closeEvent(self.event)])

        self.dragger_top_layout.addWidget(self.switch_associate)
        self.dragger_top_layout.addWidget(self.switch_writetype)
        self.dragger_top_layout.addWidget(self.switch_autocomplete)
        # self.dragger_top_layout.addWidget(self.label_top)
        self.dragger_top_layout.addWidget(self.search_fill_1)
        self.dragger_top_layout.addWidget(self.search_box)
        self.dragger_top_layout.addWidget(self.search_fill_2)
        self.dragger_top_layout.addWidget(self.tool_clearscreen)
        self.dragger_top_layout.addWidget(self.tool_panel_1)
        self.dragger_top_layout.addWidget(self.tool_panel_2)
        self.dragger_top_layout.addWidget(self.tool_minimize)
        self.dragger_top_layout.addWidget(self.tool_maximize)
        self.dragger_top_layout.addWidget(self.tool_close)
    
    def fn_distribute_left(self):
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_mark)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_showimg)
    def fn_distribute_top(self):
        self.addDockWidget(Qt.TopDockWidgetArea, self.dock_showimg)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_mark)

    def fn_clearscreen(self):
        global global_active_textcomponent,global_active_figmark
        global tab_widget_text
        message_box = QMessageBox()
        message_box.setWindowTitle('清空当前文档')
        message_box.setText('即将清空当前文档，是否继续 <是/否>？')
        message_box.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        message_box.button(QMessageBox.Yes).setText('是')
        message_box.button(QMessageBox.No).setText('否')
        reply = message_box.exec()
        if reply == QMessageBox.Yes:
            global_active_textcomponent.setText('')
            global_active_figmark.setText('')
            tab_index = tab_widget_text.currentIndex()
            tab_widget_text.setTabText(tab_index, f'文档{tab_index+1}')
            self.tab_name_array[tab_index] = f'文档{tab_index+1}'
            open(f'./data/tab_name.txt','w+',encoding='utf-8').write('，'.join(self.tab_name_array))
    def fn_search_keyreleaseevent(self,event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter: # 回车
            self.fn_search_tools()
        elif event.key() == Qt.Key_Escape:
            if self.window_search:
                self.window_search.hide()
    def fn_search_keypressEvent(self,event):
        cursor = self.search_box.textCursor()
        clipboard = QApplication.clipboard()
        try:
            if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
                clipboard.setText(cursor.selectedText())
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_X:
                clipboard.setText(cursor.selectedText())
                cursor.deleteChar()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_V:
                if clipboard.text():
                    cursor.insertText(clipboard.text())
                elif self.clip_txt:
                    cursor.insertText(self.clip_txt)
            elif event.key() == Qt.Key_Delete:
                cursor.deleteChar()
            elif event.key() == Qt.Key_Backspace:
                cursor.deletePreviousChar()
            elif event.key() == Qt.Key_Home:
                cursor.setPosition(0)
                self.search_box.setTextCursor(cursor)
            elif event.key() == Qt.Key_End:
                cursor.setPosition(len(self.search_box.toPlainText()))
                self.search_box.setTextCursor(cursor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Up:
                self.search_box.moveCursor(QTextCursor.Up, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Down:
                self.search_box.moveCursor(QTextCursor.Down, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Left:
                self.search_box.moveCursor(QTextCursor.Left, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Right:
                self.search_box.moveCursor(QTextCursor.Right, QTextCursor.KeepAnchor)
            elif event.key() == Qt.Key_Up:
                self.search_box.moveCursor(QTextCursor.Up)
            elif event.key() == Qt.Key_Down:
                self.search_box.moveCursor(QTextCursor.Down)
            elif event.key() == Qt.Key_Left:
                self.search_box.moveCursor(QTextCursor.Left)
            elif event.key() == Qt.Key_Right:
                self.search_box.moveCursor(QTextCursor.Right)
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_A:
                self.search_box.selectAll()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Z:
                self.search_box.undo()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Y:
                self.search_box.redo()
            else:
                cursor.insertText(chr(event.key()))
        except Exception as e:
            print('Error 401',e)  
    def fn_search_tools(self):
        global user,model_api
        if self.window_search:self.window_search.hide() 
        in_txt = self.search_box.toPlainText().strip(' ')
        if not in_txt:
            return
        self.status.showMessage('概念查询中，请稍后...')
        self.status.setStyleSheet("QStatusBar {background-color: #cc6633;color: white;border:none} QStatusBar:hover{background-color:#d2794c;color: white}")
        # self.setCursor(Qt.WaitCursor)
        if model_api == 'Doubao':
            self.aitrans_thread = Worker_ai_doubao('用300~500字阐述以下内容：' + in_txt,'')
        else:
            self.aitrans_thread = Worker_ai_deepseek('用300~500字阐述以下内容：' + in_txt,'')
        self.aitrans_thread.progress.connect(self.fn_aisearch)
        self.aitrans_thread.start()
    
    def fn_aisearch(self,in_txt): # AI搜索
        self.status.showMessage('查询完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
        self.window_search = QWidget()
        self.layout_windowsearch = QVBoxLayout(self.window_search)
        self.window_search.setWindowTitle("工具搜索")
        self.window_search.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_search.move(self.pos().x() + 358 + self.search_fill_1.width(),self.pos().y() + 30)
        self.window_search.setFixedWidth(402)
        self.window_search.setMinimumHeight(25)
        self.window_search.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) # 隐藏标题栏
        self.text_lb = QTextBrowser()
        self.text_lb.setFontPointSize(11)
        self.text_lb.setPlainText(in_txt)
        self.text_lb.setFixedWidth(380)
        self.text_lb.setMinimumHeight(500)
        self.text_lb.keyReleaseEvent = self.fn_search_keyreleaseevent
        self.layout_windowsearch.addWidget(self.text_lb)
        self.fn_animation(self.window_search,0.0,1.0)
        self.animation.start()
        self.window_search.show()

        self.window_search.focusOutEvent = self.fn_search_focusout
    
    def fn_search_focusout(self,event):
        try:
            self.window_search.hide()
        except:
            pass
    def fn_undo(self):
        global global_active_textcomponent
        global_active_textcomponent.undo()
    def fn_redu(self):
        global global_active_textcomponent
        global_active_textcomponent.redo()
    def get_aicontinue(self):
        global expand_length
        global global_active_textcomponent
        self.status.showMessage('文本续写中，请稍后...')
        self.status.setStyleSheet("QStatusBar {background-color: #cc6633;color: white;border:none} QStatusBar:hover{background-color:#d2794c;color: white}")
        # self.setCursor(Qt.WaitCursor)
        try:
            cursor = global_active_textcomponent.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock,QTextCursor.KeepAnchor,3)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock,QTextCursor.KeepAnchor,4) # 包括前文三段内容
            base_txt = cursor.selectedText()
        except:
            pass
        self.window_continue = QWidget()
        self.layout_windowcontinue = QGridLayout(self.window_continue)
        self.window_continue.setWindowTitle("AI续写")
        self.window_continue.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_continue.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
        self.window_continue.setFixedSize(400,400)
        self.window_continue.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) # 隐藏标题栏

        self.text_continue = QTextEdit()
        self.text_continue.setFontPointSize(11)
        self.text_continue.setMinimumHeight(100)
        self.text_continue.setMinimumWidth(380)
        self.text_continue.setPlaceholderText('文本续写中，请稍后...')

        self.bt_continue = QPushButton('确定')
        self.bt_continue.setFixedHeight(30)
        self.bt_continue.setStyleSheet('QPushButton {background-color: #e55f00 ; color:white} QPushButton:hover {background-color: #f69958}')
        self.bt_continue.clicked.connect(self.insert_aicontinue)

        self.bt_close_con = QPushButton('关闭')
        self.bt_close_con.setFixedHeight(30)
        self.bt_close_con.clicked.connect(lambda:[self.window_continue.close()])
        
        self.layout_windowcontinue.addWidget(self.text_continue,0,0,1,2)
        self.layout_windowcontinue.addWidget(self.bt_continue,1,0,1,1)
        self.layout_windowcontinue.addWidget(self.bt_close_con,1,1,1,1)

        self.fn_animation(self.window_continue,0.0,1.0)
        self.animation.start()
        self.window_continue.show()
        global model_api
        if base_txt:
            if model_api == 'Doubao':
                self.aicontinue_thread = Worker_ai_doubao(f'根据{base_txt}内容续写{expand_length}个字',self.text_continue)
            else:
                self.aicontinue_thread = Worker_ai_deepseek(f'根据{base_txt}内容续写{expand_length}个字',self.text_continue)

            self.aicontinue_thread.progress.connect(self.fn_aicontinue)
            self.aicontinue_thread.start()
        else:
            self.status.showMessage('发生未知错误')
            self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")

    def fn_aicontinue(self,in_txt):
        # self.text_continue.setPlainText(in_txt) 
        self.status.showMessage('续写完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
    def insert_aicontinue(self):
        global global_active_textcomponent
        in_txt = self.text_continue.toPlainText()
        cursor = global_active_textcomponent.textCursor()
        cursor.insertText(in_txt)
        self.window_continue.close()
    def get_aidecorate(self):
        global global_active_textcomponent
        select_txt = global_active_textcomponent.textCursor().selectedText()
        if not select_txt:
            return
        self.status.showMessage('文本润色中，请稍后...')
        self.status.setStyleSheet("QStatusBar {background-color: #cc6633;color: white;border:none} QStatusBar:hover{background-color:#d2794c;color: white}")
        # self.setCursor(Qt.WaitCursor)
        cursor = global_active_textcomponent.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock,QTextCursor.KeepAnchor,3)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.NextBlock,QTextCursor.KeepAnchor,4) # 包括前文三段的内容
        base_txt = cursor.selectedText()
        
        self.window_decorate = QWidget()
        self.layout_windowdecorate = QGridLayout(self.window_decorate)
        self.window_decorate.setWindowTitle("AI润色")
        self.window_decorate.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_decorate.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
        self.window_decorate.setFixedSize(400,400)
        self.window_decorate.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) # 隐藏标题栏

        self.text_windowdecorate = QTextEdit()
        self.text_windowdecorate.setFontPointSize(11)
        self.text_windowdecorate.setMinimumHeight(100)
        self.text_windowdecorate.setMinimumWidth(380)
        self.text_windowdecorate.setPlaceholderText('文本润色中，请稍后...')

        self.bt_decorate = QPushButton('确定')
        self.bt_decorate.setFixedHeight(30)
        self.bt_decorate.setStyleSheet('QPushButton {background-color: #e55f00 ; color:white} QPushButton:hover {background-color: #f69958}')
        self.bt_decorate.clicked.connect(self.insert_aidecorate)

        self.bt_decorate_close = QPushButton('关闭')
        self.bt_decorate_close.setFixedHeight(30)
        self.bt_decorate_close.clicked.connect(lambda:[self.window_decorate.close()])

        self.layout_windowdecorate.addWidget(self.text_windowdecorate,0,0,1,2)
        self.layout_windowdecorate.addWidget(self.bt_decorate,1,0,1,1)
        self.layout_windowdecorate.addWidget(self.bt_decorate_close,1,1,1,1)

        self.fn_animation(self.window_decorate,0.0,1.0)
        self.animation.start()
        self.window_decorate.show()
        global model_api
        if model_api == 'Doubao':
            self.aidecorate_thread = Worker_ai_doubao(f'{base_txt}\n请对上述内容进行润色改写，尽可能丰富内容细节：{select_txt}',self.text_windowdecorate)
        else:
            self.aidecorate_thread = Worker_ai_deepseek(f'{base_txt}\n请对上述内容进行润色改写，尽可能丰富内容细节：{select_txt}',self.text_windowdecorate)

        self.aidecorate_thread.progress.connect(self.fn_aidecorate)
        self.aidecorate_thread.start()
    def fn_aidecorate(self,in_txt):
        # self.text_windowdecorate.setPlainText(in_txt)
        self.status.showMessage('润色完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
    def insert_aidecorate(self):
        global global_active_textcomponent
        cursor = global_active_textcomponent.textCursor()
        in_txt = self.text_windowdecorate.toPlainText()
        cursor.insertText('\n' + in_txt)
        self.window_decorate.close()
    def fn_texttab_changed(self):
        global tab_count_array,tab_widget_text,tab_widget_mark,text_editor_array,mark_editor_array
        global global_active_textcomponent,global_active_figmark
        try:
            self.window_notebook.hide()
            self.dock_mark.setMinimumWidth(50)
            self.dock_mark.setMaximumWidth(1000)
        except:
            pass
        tab_index = tab_widget_text.currentIndex()
        tab_widget_mark.setCurrentIndex(tab_index)
        for _ in tab_count_array:
            if _ <= tab_index:
                tab_index += 1
        global_active_textcomponent = text_editor_array[tab_index]
        global_active_figmark = mark_editor_array[tab_index]
        
        self.start_drag_pos = (0,0)
        self.tab_drag_flag = False

        if self.window_symbol and self.window_symbol.isVisible():
            self.fn_show_symbol()
            self.fn_animation(self.window_symbol,0.0,1.0)
            self.animation.start()
            self.window_symbol.show()

        self.auto_complete(self.text_genword.toPlainText().split('\n') + global_active_figmark.toPlainText().split('\n'),self.text_tool_highlight)

    def fn_marktab_changed(self):
        global tab_widget_mark,mark_editor_array
        global global_active_textcomponent,global_active_figmark
        try:
            self.window_notebook.hide()
            self.dock_mark.setMinimumWidth(50)
            self.dock_mark.setMaximumWidth(1000)
        except:
            pass
        tab_index = tab_widget_mark.currentIndex()
        global_active_figmark = mark_editor_array[tab_index]
    def dragger_top_dbclick(self,event):
        try:
            y = event.y()
        except:
            y = 0
        if self.window_state == 'max':
            self.window_state = 'normal'
            self.setGeometry(self.window_pos.x(), self.window_pos.y(), self.window_width, self.window_height)
            self.dragger_top.setFixedSize(self.width() - 130, 40)
            self.tool_maximize.setIcon(QIcon('./UI/max.png'))
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
                self.tool_maximize.setIcon(QIcon('./UI/normal.png'))
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
                    self.dragger_top.setFixedSize(self.width() - 130, 40)
                elif second_screen:
                    self.setGeometry(second_screen.geometry())
                elif third_screen:
                    self.setGeometry(third_screen.geometry())
    def window_change_event(self,event): 
        global global_active_textcomponent
        self.dragger_top.setFixedSize(self.width() - 130, 40)
        if self.window_notebook:
            self.window_notebook.setFixedHeight(self.height() - 90)
            self.window_notebook.move(self.pos().x(), self.pos().y() + 63)
        if self.window_symbol:
            self.window_symbol.move(self.pos().x(), self.pos().y() + 63)
            self.window_symbol.setFixedHeight(self.height() - 90)
        if self.window_aihelp:
            self.window_aihelp.setFixedSize(400, global_active_textcomponent.height()*0.67)
            self.window_aihelp.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
        if self.window_aitrans: # 靠右上
            self.window_aitrans.setFixedSize(400, global_active_textcomponent.height()*0.67)
            self.window_aitrans.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
        if self.window_search: 
            self.window_search.move(self.pos().x() + 358 + self.search_fill_1.width(),self.pos().y() + 30)
    def window_pressrelease(self,event):
        self.dragging = False
        self.drag_flag = False
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
        self.dragger_top.setFixedSize(self.width() - 130, 40)
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
    def fn_show_figeditor(self):
        global global_active_textcomponent,global_active_figmark
        if self.window_figeditor and self.window_figeditor.isVisible():
            self.window_figeditor.close()
        else:
            self.window_figeditor = Figeditor('User',global_active_figmark)
            self.fn_animation(self.window_figeditor,0.00,1.0)
            self.animation.start()
            self.window_figeditor.show()
    def fn_analyze(self):
        webbrowser.open("http://www.fenrir.fun/analyze")
    def fn_eureka(self):
        webbrowser.open("http://www.fenrir.fun/eureka")
    def fn_reexam(self):
        webbrowser.open("http://www.fenrir.fun/reexam")

    def fn_show_adjust(self):
        if self.window_adjust and self.window_adjust.isVisible():
            self.window_adjust.hide()
        else:
            self.window_adjust = Design_Adjust()
            self.fn_animation(self.window_adjust,0.0,1.0)
            self.animation.start()
            self.window_adjust.show()


    # 显示批量替换窗口
    def show_repwindow(self):
        global global_active_textcomponent
        try:
            self.select_txt = global_active_textcomponent.textCursor().selectedText()
        except:
            self.select_txt = ''
        self.fn_show_repwindow()
        if self.window_rep.isVisible():
            self.window_rep.hide()
        else:
            self.fn_animation(self.window_rep,0.0,1.0)
            self.animation.start()
            self.window_rep.show()
            self.text_rename_after.setFocus()


    def fn_animation(self,widget,start,end):
        widget.setWindowOpacity(0.01)
        self.animation = QPropertyAnimation(widget, b"windowOpacity")
        self.animation.setDuration(600)  # 动画持续时间（毫秒）
        # 淡入效果
        self.animation.setStartValue(start)  # 起始透明度为 0（完全透明）
        self.animation.setEndValue(end)  # 结束透明度为 1（完全不透明）
    def mousePressEvent(self,event):
        self.old_x = self.pos().x()
        self.old_y = self.pos().y()
        # 鼠标相对于桌面的位置
        x = event.x() 
        y = event.y()
        self.old_width = self.width()
        self.old_height = self.height()
        if self.width()-5 <= x <= self.width() and self.height()-5 <= y <= self.height(): # 右下
            self.drag_flag = 'rd'
        elif 0 <= x <= 5 and self.height()-5 <= y <= self.height(): # 左下
            self.drag_flag = 'ld'
        elif 0 <= x <= 5: # 左边缘
            self.drag_flag = 'left'
        elif self.width()-5 <= x <= self.width(): # 右边缘
            self.drag_flag = 'right'
        elif self.height()-5 <= y <= self.height(): # 下边缘
            self.drag_flag = 'down'
        elif 0 <= y <= 5: #  上边缘
            self.drag_flag = 'up'
    def mouseReleaseEvent(self,event):
        self.drag_flag = False
        try:
            self.window_location.close()
        except:
            pass
    def mouseMoveEvent(self, event):
        global version,global_active_textcomponent
        x = event.globalX()
        y = event.globalY()
        x2 = event.x() 
        y2 = event.y()
        # 缩放窗体
        if self.width()-5 <= x2 <= self.width() and self.height()-5 <= y2 <= self.height(): # 右下
            self.setCursor(Qt.SizeFDiagCursor)
        elif 0 <= x2 <= 5 and self.height()-5 <= y2 <= self.height(): # 左下
            self.setCursor(Qt.SizeBDiagCursor)
        elif 0 <= x2 <= 5 or self.width()-5 <= x2 <= self.width(): # 左右边缘
            self.setCursor(Qt.SizeHorCursor)
        elif self.height()-5 <= y2 <= self.height(): # 下边缘
            self.setCursor(Qt.SizeVerCursor)
        elif 0 <= y2 <= 5: #  上边缘
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        if self.drag_flag == 'right':
            self.resize(x - self.old_x,self.height())
        elif self.drag_flag == 'left':
            temp_length = x - self.old_x
            if temp_length > 0 and self.width() > 750: # 缩小
                self.move(x,self.old_y)
                self.resize(self.old_width - temp_length,self.height())
            elif temp_length <= 0:
                self.move(x,self.old_y)
                self.resize(self.old_width - temp_length,self.height())
        elif self.drag_flag == 'down':
            self.resize(self.width(),y - self.old_y)
        elif self.drag_flag == 'up':
            temp_height = y - self.old_y
            if temp_height > 0 and self.height() > 450: # 缩小
                self.move(self.old_x,y)
                self.resize(self.width(),self.old_height - temp_height)
            elif temp_height <= 0:
                self.move(self.old_x,y)
                self.resize(self.width(),self.old_height - temp_height)
        elif self.drag_flag == 'rd':
            self.resize(x - self.old_x,y - self.old_y)
        elif self.drag_flag == 'ld':
            self.resize(x - self.old_x,y - self.old_y)
        # 左右桌面填充
        primary_screen = QGuiApplication.primaryScreen()
        screen_geometry = primary_screen.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        if not self.window_location:
            self.window_location = QWidget()
            self.layout_window_location = QGridLayout(self.window_location)
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
            # if y > 50 and y < 900 and x > 200:
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()
            if self.window_notebook:
                self.window_notebook.move(self.pos().x(), self.pos().y()+63)
            if self.window_symbol:
                self.window_symbol.move(self.pos().x(),self.pos().y()+63)
            if self.window_aihelp:
                self.window_aihelp.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
            if self.window_aitrans:
                self.window_aitrans.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
            if self.window_rep:
                self.window_rep.move(self.pos().x() + self.width() - 270,self.pos().y() + 100)
            if self.window_decorate:
                self.window_decorate.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
            if self.window_continue:
                self.window_continue.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
            if self.window_search: 
                self.window_search.move(self.pos().x() + 358 + self.search_fill_1.width(),self.pos().y() + 30)
        # self.window_notebook.activateWindow()
        
    def fn_aiapi(self):
        global messages
        messages = []
        if not self.window_api:
            self.api_ui()
        if self.window_api.isVisible():
            self.window_api.hide()
        else:
            self.fn_animation(self.window_api,0.0,1.0)
            self.animation.start()
            self.window_api.show()
    def fn_showhelp(self):
        if not self.window_help:
            self.help_ui()
        if self.window_help.isVisible():
            self.window_help.hide()
        else:
            self.fn_animation(self.window_help,0.0,1.0)
            self.animation.start()
            self.window_help.show()
    def submit_api(self):
        if self.combo_api.currentText() == 'Doubao':
            ak = self.text_ak.text()
            sk = self.text_sk.text()
            model = self.text_model.text()
            open('./data/doubao_token.txt','w+').write(f'{ak}\n{sk}\n{model}')
        elif self.combo_api.currentText() == 'Deepseek':
            ak = self.text_ak.text()
            open('./data/deepseek_token.txt','w+').write(f'{ak}')
        self.window_api.hide()
    def api_ui(self):
        global messages
        messages = []
        doubao_array = open('./data/doubao_token.txt','r').read().split('\n')
        ak,sk,model = '','',''
        if len(doubao_array) == 3:
            ak = doubao_array[0]
            sk = doubao_array[1]
            model = doubao_array[2]
        
        self.window_api = QWidget_Notop('API')
        self.layout_windowapi = QGridLayout(self.window_api)
        self.window_api.move(800, 400)
        self.window_api.setFixedSize(400, 150)

        self.text_ak = QLineEdit()
        self.text_ak.setText(ak)
        self.text_ak.setToolTip('Access Key ID (AK)')
        self.text_ak.setPlaceholderText(f'Access Key ID (AK)')
        self.text_ak.setFixedSize(380,25)

        self.text_sk = QLineEdit()
        self.text_sk.setText(sk)
        self.text_sk.setToolTip('Secret Access Key (SK)')
        self.text_sk.setPlaceholderText(f'Secret Access Key (SK)')
        self.text_sk.setFixedSize(380,25)

        self.text_model = QLineEdit()
        self.text_model.setText(model)
        self.text_model.setToolTip('Model')
        self.text_model.setPlaceholderText(f'Model')
        self.text_model.setFixedSize(380,25)

        self.combo_model = QComboBox()
        self.combo_model.addItem('deepseek-chat')
        self.combo_model.addItem('deepseek-reasoner')
        self.combo_model.setCurrentIndex(0)
        self.combo_model.currentIndexChanged.connect(self.combo_model_changed)
        self.combo_model.setFixedSize(380,25)

        self.combo_api = QComboBox()
        self.combo_api.addItem('Doubao')
        self.combo_api.addItem('Deepseek')
        self.combo_api.setCurrentIndex(0)
        self.combo_api.currentIndexChanged.connect(self.combo_api_changed)
        self.combo_api.setFixedSize(100,25)


        bt_submit = QPushButton("提交")
        bt_submit.setToolTip('关闭')
        bt_submit.clicked.connect(self.submit_api)
        bt_submit.setStyleSheet('background-color: #e55f00;color:white')
        bt_submit.setFixedSize(130,25)

        bt_close = QPushButton("X")
        bt_close.setToolTip('关闭')
        bt_close.setFixedSize(130,25)
        bt_close.clicked.connect(self.window_api.hide)

        self.layout_windowapi.addWidget(self.text_ak,0,0,1,3)
        self.layout_windowapi.addWidget(self.text_sk,1,0,1,3)

        self.layout_windowapi.addWidget(self.text_model,2,0,1,3)
        self.layout_windowapi.addWidget(self.combo_api,4,0,1,3)
        self.layout_windowapi.addWidget(bt_submit,4,1,1,1)
        self.layout_windowapi.addWidget(bt_close,4,2,1,1)
    def combo_model_changed(self):
        global deep_model
        deep_model = self.combo_model.currentText().strip('\n ')
            
    def combo_api_changed(self):
        global model_api
        ak,sk,model = '','',''
        doubao_array = open('./data/doubao_token.txt','r').read().split('\n')
        if len(doubao_array) == 3:
            ak = doubao_array[0]
            sk = doubao_array[1]
            model = doubao_array[2]
        deepseek_array = open('./data/deepseek_token.txt','r').read().split('\n')
        if len(deepseek_array) == 1:
            deepseek_ak = deepseek_array[0]
        if self.combo_api.currentText() == 'Deepseek':
            self.text_sk.hide()
            self.text_model.hide()
            self.text_ak.setText(deepseek_ak)
            self.combo_model.show()
            self.layout_windowapi.addWidget(self.combo_model,1,0,1,3)
            model_api = 'Deepseek'
        else:
            self.text_ak.show()
            self.text_sk.show()
            self.text_model.show()
            self.combo_model.hide()
            self.text_ak.setText(ak)
            self.text_sk.setText(sk)
            self.text_model.setText(model)
            model_api = 'Doubao'

    def help_ui(self):
        self.window_help = QWidget_Notop('如何使用')
        self.layout_windowhelp = QGridLayout(self.window_help)
        self.window_help.move(400, 200)
        self.window_help.setFixedSize(600, 400)
        bt_1 = QPushButton("功能选择")
        bt_1.setStyleSheet('background-color: #e55f00;color:white')
        bt_1.setFixedSize(100,20)
        bt_close = QPushButton("X")
        # bt_close.setStyleSheet('background-color: #e55f00;color:white')
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
    def fn_showbook(self):
        global global_active_textcomponent,global_active_figmark
        if self.window_notebook.isVisible():
            self.window_notebook.hide()
            self.dock_mark.setMinimumWidth(50)
            self.dock_mark.setMaximumWidth(1000)
        else:
            self.window_notebook = WindowBook(global_active_figmark,global_active_textcomponent,self.status,self.dock_mark)
            self.fn_animation(self.window_notebook,0.0,1.0)
            self.animation.start()
            self.window_notebook.show()
            self.window_notebook.move(self.pos().x(), self.pos().y()+63)
            self.window_notebook.setFixedHeight(self.height() - 90)
            self.dock_mark.setFixedWidth(500)
    def fn_reset_allformat(self):# 重置格式
        global global_active_textcomponent,global_active_figmark
        format = QTextCharFormat()
        # format.setForeground(QColor('#dfe1e2'))
        format.setBackground(QColor(Qt.transparent))
        global_active_textcomponent.setFont(QFont("SimSun", 12))
        # format.setFont('宋体')
        # format.setFontPointSize(12)
        cursor = global_active_textcomponent.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.mergeCharFormat(format)

        format.setFontPointSize(9)
        cursor = global_active_figmark.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(format)
    def change_font_color(self):
        global global_active_textcomponent
        font_format = QTextCharFormat()
        font_format.setForeground(QColor(self.font_color))
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().replace('\n','\u2029')
        re_search = QRegExp(select_txt)
        matches = re.finditer(re_search.pattern(), global_active_textcomponent.document().toPlainText().replace('\n','\u2029'))
        # 循环查找文档
        match_num = 0
        for match in matches:
            match_num += 1
            index = match.start()
            cursor.setPosition(index)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(select_txt))
            cursor.mergeCharFormat(font_format)
    def choose_fontcolor(self,event): # 选择字体颜色
        self.font_color = QColorDialog().getColor().name()
        if self.font_color:
            self.bt_color.setStyleSheet("QPushButton {border-left: 0px; color:"+ self.font_color + '}')
        else:
            self.bt_color.setStyleSheet("QPushButton {border-left: 0px; color:#aa0000}")

    def change_font_bgcolor(self):
        global global_active_textcomponent
        font_format = QTextCharFormat()
        font_format.setBackground(QColor(self.background_color))
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().replace('\n','\u2029')
        re_search = QRegExp(select_txt)
        matches = re.finditer(re_search.pattern(), global_active_textcomponent.document().toPlainText().replace('\n','\u2029'))
        # 循环查找文档
        match_num = 0
        for match in matches:
            match_num += 1
            index = match.start()
            cursor.setPosition(index)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(select_txt))
            cursor.mergeCharFormat(font_format)
    def choose_font_bgcolor(self,event): # 选择字体颜色
        self.background_color = QColorDialog().getColor().name()
        # self.toobar_bgcolor.setStyleSheet(f'background-color: {self.background_color}')
        

    def set_default_color(self):
        global global_active_textcomponent
        format = QTextCharFormat()
        global_active_textcomponent.setStyleSheet('background-color: #dfe1e2')
        self.background_color = '#dfe1e2'
        format.setForeground(QColor("black"))
        format.setBackground(QColor(Qt.transparent))
        cursor = global_active_textcomponent.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.mergeCharFormat(format)
    def choose_gcolor(self): # 选择背景色
        global global_active_textcomponent
        self.background_color = QColorDialog().getColor().name()
        if self.background_color == '#000000':
            self.choose_gcolor_action.setStyleSheet(f'background-color: {self.background_color}')
            global_active_textcomponent.setStyleSheet(f'background-color: {self.background_color}')
        else:
            self.choose_gcolor_action.setStyleSheet(f'background-color: {self.background_color}')
            global_active_textcomponent.setStyleSheet(f'background-color: {self.background_color}')
    def add_mouse_rightclick(self):  # 右键菜单
        self.action_00 = QAction(QIcon(qta.icon('fa5b.searchengin')),'专利检索')
        self.action_01 = QAction(QIcon(qta.icon('mdi6.content-cut')),'剪切')
        self.action_02 = QAction(QIcon(qta.icon('ph.copy-fill')),'复制')
        self.action_03 = QAction(QIcon(qta.icon('fa.paste')),'粘贴')
        self.action_04 = QAction(QIcon(qta.icon('ph.flame-thin')),'全部替换')

        self.action_08 = QAction(QIcon(qta.icon('ei.idea')),'AI填充')
        self.action_09 = QAction(QIcon(qta.icon('msc.debug-continue-small')),'AI续写')
        self.action_05 = QAction(QIcon(qta.icon('ph.brain')),'AI润色')
        self.action_06 = QAction(QIcon(qta.icon('mdi.file-search-outline')),'概念查询')
        self.action_07 = QAction(QIcon(qta.icon('mdi6.translate-variant')),'文本翻译')
        
        self.action_11 = QAction(QIcon(qta.icon('mdi6.zodiac-aquarius')),'<01> A => A1')
        self.action_12 = QAction(QIcon(qta.icon('mdi6.zodiac-aries')),'<02> A => A(1)')
        self.action_13 = QAction(QIcon(qta.icon('mdi6.zodiac-cancer')),'<03> 1 => A1')
        self.action_14 = QAction(QIcon(qta.icon('mdi6.zodiac-capricorn')),'<04> 1 => A(1)')
        self.action_15 = QAction(QIcon(qta.icon('mdi6.zodiac-gemini')),'<05> A1/(1) => A(精确)')
        self.action_16 = QAction(QIcon(qta.icon('mdi6.zodiac-leo')),'<06> A1 => A(1)')
        self.action_17 = QAction(QIcon(qta.icon('mdi6.zodiac-libra')),'<07> A(1) => A1')
        self.action_18 = QAction(QIcon(qta.icon('mdi6.zodiac-pisces')),'<08> 合并附图标记')
        self.action_19 = QAction(QIcon(qta.icon('mdi6.zodiac-sagittarius')),'<09> 提取发明内容')
        self.action_110 = QAction(QIcon(qta.icon('mdi6.zodiac-scorpio')),'<10> 提取附图标记')
        self.action_111 = QAction(QIcon(qta.icon('mdi6.zodiac-taurus')),'<11> 统一单位')
        self.action_112 = QAction(QIcon(qta.icon('mdi6.zodiac-virgo')),'<12> 统一元素符号')
        self.action_113 = QAction(QIcon(qta.icon('ph.package-thin')),'<13> 删除多余回车')
        self.action_114 = QAction(QIcon(qta.icon('ph.paint-bucket-thin')),'<14> 删除空格')
        self.action_115 = QAction(QIcon(qta.icon('ph.path-thin')),'<15> 删除段号')
        self.action_116 = QAction(QIcon(qta.icon('mdi6.zodiac-sagittarius')),'<16> 增加段号')
        self.action_117 = QAction(QIcon(qta.icon('mdi6.zodiac-gemini')),'<17> 模糊删除标记(谨慎使用)')

        self.action_21 = QAction(QIcon(qta.icon('mdi6.cloud-check-variant-outline')),'<01> OA模板')
        self.action_22 = QAction(QIcon(qta.icon('ph.poker-chip-thin')),'<02> 说明书模板')
        self.action_23 = QAction(QIcon(qta.icon('ph.polygon-thin')),'<03> 权利要求书模板')
        self.action_24 = QAction(QIcon(qta.icon('ph.recycle')),'<04> 复审请求模板')
        self.action_25 = QAction(QIcon(qta.icon('mdi6.hammer')),'<05> 无效请求模板')
        self.action_26 = QAction(QIcon(qta.icon('mdi6.hammer')),'<06> AI撰写说明书模板')

        # 添加快捷键
        self.action_01.setShortcut('Ctrl+X')
        self.action_02.setShortcut('Ctrl+C')
        self.action_03.setShortcut('Ctrl+V')
        self.action_04.setShortcut('Ctrl+F')
        self.action_05.setShortcut('Alt+E')
        self.action_06.setShortcut('Alt+R')
        self.action_07.setShortcut('Alt+T')
        self.action_08.setShortcut('Alt+Q')
        self.action_09.setShortcut('Alt+W')

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
        self.action_26.setShortcut('Alt+6')

        self.action_00.triggered.connect(self.fn_searchpatent)
        self.action_01.triggered.connect(self.fn_cut)
        self.action_02.triggered.connect(self.fn_copy)
        self.action_03.triggered.connect(self.fn_paste)
        self.action_04.triggered.connect(self.show_repwindow)
        # AI
        self.action_05.triggered.connect(self.get_aidecorate)
        self.action_06.triggered.connect(self.get_aihelp)
        self.action_07.triggered.connect(self.get_aitrans)
        self.action_08.triggered.connect(self.get_aisupplement)
        self.action_09.triggered.connect(self.get_aicontinue)
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
        self.action_26.triggered.connect(self.generate_ai_model)
    def fn_copy(self):
        global global_active_textcomponent
        cursor = global_active_textcomponent.textCursor()
        clipboard = QApplication.clipboard()
        self.clip_txt = cursor.selectedText()
        self.mime_data = QMimeData()
        fragment = QTextDocumentFragment(cursor)
        html = fragment.toHtml()
        try:
            self.mime_data.setData("text/html", bytes(html, 'utf-8'))
            clipboard.setMimeData(self.mime_data)
        except:
            clipboard.setText(cursor.selectedText())
    def fn_searchpatent(self):
        global global_active_textcomponent
        try:
            for url in open("options.txt",'r',encoding='utf-8').readlines():
                if 'search_url' in url:
                    self.search_url = url.split('=')[1].strip(' ')
                    self.select_txt = global_active_textcomponent.textCursor().selectedText()
                    webbrowser.open(f"{self.search_url}={self.select_txt}")
                    break
        except:
            pass
    def fn_cut(self):
        global global_active_textcomponent
        cursor = global_active_textcomponent.textCursor()
        clipboard = QApplication.clipboard()
        self.clip_txt = cursor.selectedText()
        self.mime_data = QMimeData()
        fragment = QTextDocumentFragment(cursor)
        html = fragment.toHtml()
        try:
            self.mime_data.setData("text/html", bytes(html, 'utf-8'))
            clipboard.setMimeData(self.mime_data)
        except:
            clipboard.setText(cursor.selectedText())
        cursor.deleteChar()
    def fn_paste(self):
        global global_active_textcomponent
        cursor = global_active_textcomponent.textCursor()
        clipboard = QApplication.clipboard()
        cursor.removeSelectedText()
        text = clipboard.text(QClipboard.Clipboard)
        cursor.insertText(text)
    def fn_show_symbol(self):
        if not self.window_symbol or not self.window_symbol.isVisible():
            self.symbol_ui()
            self.fn_animation(self.window_symbol,0.0,1.0)
            self.animation.start()
            self.window_symbol.show()

            self.dock_mark.setFixedWidth(250)
        elif self.window_symbol.isVisible():
            self.window_symbol.hide()
            self.dock_mark.setMinimumWidth(50)
            self.dock_mark.setMaximumWidth(1000)
    def symbol_close(self):
        if self.window_symbol.isVisible():
            self.window_symbol.hide()
            self.dock_mark.setMinimumWidth(50)
            self.dock_mark.setMaximumWidth(1000)
    def symbol_ui(self):
        self.window_symbol = QWidget_Notop('特殊字符')
        self.layout_windowsymbol = QGridLayout(self.window_symbol)
        self.window_symbol.setFixedSize(250, self.height() - 90)
        self.window_symbol.move(self.pos().x(),self.pos().y()+63)
        
        line_length = 5 # 每行个数
        array_1 = ['()','（）','〔〕','[]','【】','〈〉','「」','『』','{}','《》','＜＞','<>','“”','〝〞','‘’']
        array_2 = ['≦','≧','≡','×','÷','≤','≥','≈','≠','∞','∝','∽','∈','±','※','√','≌','∫','‰','℅','∮','△']
        array_3 = ['→','←','↑','↓','↘','↖','↗','↙']
        array_4 = ['Αα','Ββ','Γγ','Δδ','Εε','Ζζ','Ηη','Θθ','Ιι','Κκ','Λλ','Μμ','Νν','Ξξ','Ππ','Ρρ','Σσ','Ττ','Υυ','Φφ','Χχ','Ψψ','Ωω']
        array_5 = ['kg/m3','g/cm3','°','℃','℉','km','cm','mm','μm','nm','kg','mg','μg','ng','lbs','kPa','MPa','bar','kw·h','GW','m/s','km/h']

        lb_array_1 = [Label_Symbol(global_active_textcomponent,array_1[i]) for i in range(len(array_1))]
        lb_array_2 = [Label_Symbol(global_active_textcomponent,array_2[i]) for i in range(len(array_2))]
        lb_array_3 = [Label_Symbol(global_active_textcomponent,array_3[i]) for i in range(len(array_3))]
        lb_array_4 = [Label_Symbol(global_active_textcomponent,array_4[i]) for i in range(len(array_4))]
        lb_array_5 = [Label_Symbol(global_active_textcomponent,array_5[i]) for i in range(len(array_5))]

        label_symbol_logo = QLabel()
        movie = QMovie(f"./ui/news.gif")
        label_symbol_logo.setScaledContents(True)
        label_symbol_logo.setMovie(movie)
        label_symbol_logo.setFixedSize(230,60)
        
        bt_close = QPushButton('X')
        bt_close.setToolTip('关闭')
        bt_close.clicked.connect(self.symbol_close)
        movie.start()
        self.layout_windowsymbol.addWidget(label_symbol_logo,0,0,1,line_length)
        self.layout_windowsymbol.addWidget(QLabel('<标点>'),1,0,1,1)
        self.layout_windowsymbol.addWidget(bt_close,1,line_length-1,1,1)

        for index,label in enumerate(lb_array_1):
            label.setMinimumWidth(20);label.setMaximumHeight(20);label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet('QLabel {background-color: #455364 ; color:white} QLabel:hover {background-color: #6a7c91}')
            self.layout_windowsymbol.addWidget(label,2 + int(index/line_length),index % line_length,1,1)

        self.layout_windowsymbol.addWidget(QLabel('<公式>'),11,0,1,line_length)
        for index,label in enumerate(lb_array_2):
            label.setMinimumWidth(20);label.setMaximumHeight(20);label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet('QLabel {background-color: #455364 ; color:white} QLabel:hover {background-color: #6a7c91}')
            self.layout_windowsymbol.addWidget(label,12 + int(index/line_length),index % line_length,1,1)

        self.layout_windowsymbol.addWidget(QLabel('<制表符>'),21,0,1,line_length)
        for index,label in enumerate(lb_array_3):
            label.setMinimumWidth(20);label.setMaximumHeight(20);label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet('QLabel {background-color: #455364 ; color:white} QLabel:hover {background-color: #6a7c91}')
            self.layout_windowsymbol.addWidget(label,22 + int(index/line_length),index % line_length,1,1)

        self.layout_windowsymbol.addWidget(QLabel('<希腊字母>'),31,0,1,line_length)
        for index,label in enumerate(lb_array_4):
            label.setMinimumWidth(20);label.setMaximumHeight(20);label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet('QLabel {background-color: #455364 ; color:white} QLabel:hover {background-color: #6a7c91}')
            self.layout_windowsymbol.addWidget(label,32 + int(index/line_length),index % line_length,1,1)

        self.layout_windowsymbol.addWidget(QLabel('<单位>'),41,0,1,line_length)
        for index,label in enumerate(lb_array_5):
            label.setMinimumWidth(20);label.setMaximumHeight(20);label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet('QLabel {background-color: #455364 ; color:white} QLabel:hover {background-color: #6a7c91}')
            self.layout_windowsymbol.addWidget(label,42 + int(index/line_length),index % line_length,1,1)
    def fn_insert_table(self):
        self.window_table = QWidget()
        self.layout_windowtable = QGridLayout(self.window_table)
        self.window_table.setWindowTitle("表格")
        self.window_table.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_table.move(self.pos().x() + 125,self.pos().y() + 55)
        self.window_table.setFixedSize(250, 180)
        self.window_table.setWindowFlags(Qt.FramelessWindowHint) # 隐藏标题栏
        self.label_array = [QLabel() for _ in range(0,100)]
        for i in range(0,10):
            for j in range(0,10):
                self.label_array[i*10+j].setStyleSheet('QLabel {background-color: white ; color:white} QLabel:hover {background-color: #6a7c91}')
                self.label_array[i*10+j].setFixedSize(15,10)
                self.label_array[i*10+j].enterEvent = self.label_on_enter
                self.label_array[i*10+j].mousePressEvent = self.insert_tabel
                self.layout_windowtable.addWidget(self.label_array[i*10+j],j,i,1,1)
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
        for i in range(0,10):
            for j in range(0,10):
                self.label_array[i*10+j].setStyleSheet('QLabel {background-color: white}')
        for i in range(0,self.table_x):
            for j in range(0,self.table_y):
                self.label_array[i*10+j].setStyleSheet('QLabel {background-color: #6a7c91}')
            
        self.label_square.setText(f'{self.table_x}  X  {self.table_y}')
    def insert_tabel(self,event):
        self.window_table.close()
        table_html = "<table border='1'>"
        for row in range(0,self.table_y):
            table_html += '<tr>'
            for column in range(0,self.table_x):
                if row == 0:
                    table_html += f'<td>column {column + 1}</td>'
                else:
                    table_html += f'<td></td>'
            table_html += '</tr>'
        table_html += '</table>'

        cursor = global_active_textcomponent.textCursor()
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
            cursor = global_active_textcomponent.textCursor()
            html = f"<img src=\"{file_path}\" alt=\"{os.path.basename(file_path)}\" width=\"{width}\" height=\"{height}\" />"
            cursor.insertHtml(html)
 
    def show_new_window(self):
        global tab_count_array,tab_widget_text,tab_widget_mark,window_show_array,text_editor_array,mark_editor_array,window_show_text_array,window_show_mark_array
        global global_active_textcomponent,global_active_figmark
        self.index = tab_widget_text.currentIndex()
        if self.index == -1:
            return
        tab_widget_text.removeTab(self.index)
        tab_widget_mark.removeTab(self.index)
        # 校正 self.index
        for _ in tab_count_array:
            if _ <= self.index:
                self.index += 1
        tab_count_array.append(self.index)

        tab_name = self.tab_name_array[self.index]
        new_window = window_show_array[self.index]
        new_window.setWindowTitle(tab_name)
        
        all_txt = open(f'./data/text_saver_{self.index + 1}.html','r',encoding='utf-8').read()
        marks_txt = open(f'./data/marks_saver_{self.index + 1}.txt', 'r', encoding='utf-8').read()

        new_window.new_text_editor.setHtml(all_txt)
        new_window.new_mark_editor.setPlainText(marks_txt)

        global_active_textcomponent = new_window.new_text_editor
        global_active_figmark = new_window.new_mark_editor

        new_window.setGeometry(400, 400, 800, 600)   
        new_window.show()
    def fn_tabbar_click(self):
        self.tab_drag_flag = True
        self.start_drag_pos = (QCursor.pos().x(),QCursor.pos().y())
        # print('Start_point',self.start_drag_pos)
    def fn_tabbar_move(self,event):
        self.end_drag_pos = (QCursor.pos().x(),QCursor.pos().y())
        abs_x = abs(self.end_drag_pos[0] - self.start_drag_pos[0])
        abs_y = abs(self.end_drag_pos[1] - self.start_drag_pos[1])
        # print('Start_point',self.start_drag_pos,'Abs_x,Abs_y',abs_x,abs_y,self.tab_drag_flag)
        if self.start_drag_pos != (0,0) and self.tab_drag_flag and (abs_x > 0 or abs_y > 0):
            self.show_new_window()
            self.start_drag_pos = (0,0)
            self.tab_drag_flag = False
    def fn_tabbar_mousepress_event(self,event):
        if event.button() == 2:
            self.show_new_window()
    def add_texteditors(self):
        global tab_widget_text,text_editor_array,window_show_array,window_show_text_array,window_show_mark_array,global_active_textcomponent,global_active_figmark
        # 多标签文本
        tab_widget_text = QTabWidget()
        tab_widget_text.setMouseTracking(True)
        tab_widget_text.tabBarClicked.connect(self.fn_tabbar_click)
        tab_widget_text.mouseMoveEvent = self.fn_tabbar_move
        # tab_widget_text.mousePressEvent = self.fn_tabbar_mousepress_event
        text_editor_array = [QTextEditWithLineNum() for i in range(30)]
        window_show_text_array = [QTextEditWithLineNum() for i in range(30)]
        window_show_mark_array = [OcrDropTextEdit() for i in range(30)]
        window_show_array = [NewWindow(i) for i in range(30)]
        
        self.contextMenu_array = [_ for _ in range(30)]
        global_active_textcomponent = text_editor_array[0]
        
        self.show_cursor_menu() # 右键菜单
        self.tab_name_array = open(f'./data/tab_name.txt','r',encoding='utf-8').read().split('，')
        for editor in text_editor_array:
            # 设置editor
            editor.setContextMenuPolicy(Qt.CustomContextMenu)
            editor.customContextMenuRequested.connect(self.show_context_menu)
            editor.focusOutEvent = self.fn_texteditor_focusout_autosave
            editor.mouseReleaseEvent = self.fn_mouse_keyrelease_text
            editor.mouseDoubleClickEvent = self.fn_mouse_dbclick
            editor.keyReleaseEvent = self.fn_keyreleaseevent
            editor.keyPressEvent = self.fn_keypressevent
            
            editor.textChanged.connect(self.fn_text_changed)
            editor_index = text_editor_array.index(editor)
            try:
                load_txt = open(f'./data/text_saver_{editor_index + 1}.html','r',encoding='utf-8').read()
                editor.setHtml(load_txt)
            except Exception as e:
                editor.insertPlainText('')
                print('Error Code 205',e)
            start_num = len(self.tab_name_array)
            if len(self.tab_name_array) < 30:
                for i in range(start_num,30):
                    self.tab_name_array.append(f'文档{i + 1}')
            if self.tab_name_array:
                tab_widget_text.addTab(editor,self.tab_name_array[editor_index])
            else:
                tab_widget_text.addTab(editor,f'文档{editor_index + 1}')
    
        for index,editor in enumerate(window_show_text_array):
            editor.mouseReleaseEvent = self.fn_mouse_keyrelease_text
            
        for index,editor in enumerate(window_show_mark_array):
            editor.mouseReleaseEvent = self.fn_highlight_figmarks

        self.layoutwidget.addWidget(tab_widget_text,0,0,1,1)
        tab_widget_text.currentChanged.connect(self.fn_texttab_changed)
        tab_widget_text.tabBarDoubleClicked.connect(self.rename_tabtext)

    def fn_mouse_dbclick(self,event):
        global global_active_textcomponent,global_active_figmark

        list_1 = list(self.load_txt_1) + ['包含','已经','可以','包括','能够','一旦','一种','通过','进行','用于','如果','可能','或者'] # 向前查找
        list_2 = list(self.load_txt_2) # 向后查找
        cursor = global_active_textcomponent.textCursor()
        format = QTextCharFormat()
        format.setBackground(QColor('#4a76d6'))

        for i in range(1,10):
            cursor.movePosition(cursor.Left,i)
            select_txt_1 = cursor.selectedText()
            if not select_txt_1:
                continue
            if select_txt_1[0] in list_1:
                # if len(select_txt_1) > 1:
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
                            self.get_same_markindex_1(select_txt,global_active_textcomponent,self.highlight_color)
                            return
                if j == i + 9:
                    select_txt = select_txt_1[1:]
                    self.db_flag = True
                    self.get_same_markindex_1(select_txt,global_active_textcomponent,self.highlight_color)
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
        global tab_widget_text
        if event.mimeData().hasUrls():
            urls = [url.toLocalFile() for url in event.mimeData().urls()]
            # 处理拖放的本地文件路径
            self.in_dir = urls[0]
            self.status.showMessage('文件识别中...')
            self.tab_txt_index = tab_widget_text.currentIndex()
            self.ocr_thread = Worker_Ocr(self.in_dir)
            self.ocr_thread.progress.connect(self.text_editor_ocr)
            self.ocr_thread.start()
            event.accept()
        else:
            event.ignore()
    def text_editor_ocr(self,in_txt):
        global text_editor_array
        text_editor_array[self.tab_txt_index].insertPlainText('\n' + in_txt)
        self.status.showMessage('文件完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
    def rename_tabtext(self):
        # if event.button() != 2: # 1左键 2 右键 4 中键
        #     return
        global tab_widget_text
        self.tab_name_widget = QWidget()
        self.tab_name_layout = QGridLayout(self.tab_name_widget)
        self.tab_name_widget.setFixedSize(220,50)
        self.tab_name_widget.setWindowFlags(Qt.FramelessWindowHint) # 隐藏标题栏

        self.tab_name_text = BreathTextEdit()
        self.tab_name_text.setPlaceholderText('输入文档标题')
        self.tab_name_text.setMinimumHeight(30)
        self.tab_name_text.setMinimumWidth(200)
        tab_index = tab_widget_text.currentIndex()
        tab_txt = tab_widget_text.tabText(tab_index)
        if tab_txt != f'文档{tab_index + 1}':
            self.tab_name_text.setText(tab_txt)
        self.tab_name_layout.addWidget(self.tab_name_text,0,0)
        self.tab_name_widget.move(QCursor.pos().x(),QCursor.pos().y())
        self.fn_animation(self.tab_name_widget,0.0,1.0)
        self.animation.start()
        self.tab_name_widget.show()

        self.start_drag_pos = (0,0)
        self.tab_drag_flag = False

        self.tab_name_text.focusOutEvent = self.tab_name_focusout
        self.tab_name_text.keyPressEvent = self.tab_name_keypressEvent
    def tab_name_keypressEvent(self,event):
        global tab_widget_text
        cursor = self.tab_name_text.textCursor()
        clipboard = QApplication.clipboard()
        try:
            if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
                clipboard.setText(cursor.selectedText())
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_X:
                clipboard.setText(cursor.selectedText())
                cursor.deleteChar()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_V:
                if clipboard.text():
                    cursor.insertText(clipboard.text())
                elif self.clip_txt:
                    cursor.insertText(self.clip_txt)
            elif event.key() == Qt.Key_Delete:
                cursor.deleteChar()
            elif event.key() == Qt.Key_Backspace:
                cursor.deletePreviousChar()
            elif event.key() == Qt.Key_Home:
                cursor.setPosition(0)
                self.tab_name_text.setTextCursor(cursor)
            elif event.key() == Qt.Key_End:
                cursor.setPosition(len(self.tab_name_text.toPlainText()))
                self.tab_name_text.setTextCursor(cursor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Up:
                self.tab_name_text.moveCursor(QTextCursor.Up, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Down:
                self.tab_name_text.moveCursor(QTextCursor.Down, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Left:
                self.tab_name_text.moveCursor(QTextCursor.Left, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Right:
                self.tab_name_text.moveCursor(QTextCursor.Right, QTextCursor.KeepAnchor)
            elif event.key() == Qt.Key_Up:
                self.tab_name_text.moveCursor(QTextCursor.Up)
            elif event.key() == Qt.Key_Down:
                self.tab_name_text.moveCursor(QTextCursor.Down)
            elif event.key() == Qt.Key_Left:
                self.tab_name_text.moveCursor(QTextCursor.Left)
            elif event.key() == Qt.Key_Right:
                self.tab_name_text.moveCursor(QTextCursor.Right)
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_A:
                self.tab_name_text.selectAll()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Z:
                self.tab_name_text.undo()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Y:
                self.tab_name_text.redo()
            elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Escape: # 回车 或 esc
                tab_index = tab_widget_text.currentIndex()
                self.tab_name_widget.hide()
                tab_txt = self.tab_name_text.toPlainText()
                if tab_txt:
                    pass
                elif not tab_txt:
                    tab_txt = f'文档{tab_index + 1}'
                tab_widget_text.setTabText(tab_index, tab_txt)
                self.tab_name_array[tab_index] = tab_txt
                open(f'./data/tab_name.txt','w+',encoding='utf-8').write('，'.join(self.tab_name_array))
            else:
                cursor.insertText(chr(event.key()))
        except Exception as e:
            print('Error 301',e)      
        self.start_drag_pos = (0,0)
        self.tab_drag_flag = False
    def tab_name_focusout(self,event):
        global tab_widget_text
        tab_index = tab_widget_text.currentIndex()
        self.tab_name_widget.hide()
        tab_txt = self.tab_name_text.toPlainText()
        if tab_txt:
            pass
        elif not tab_txt:
            tab_txt = f'文档{tab_index + 1}'
        tab_widget_text.setTabText(tab_index, tab_txt)
        self.tab_name_array[tab_index] = tab_txt
        open(f'./data/tab_name.txt','w+',encoding='utf-8').write('，'.join(self.tab_name_array))

        self.start_drag_pos = (0,0)
        self.tab_drag_flag = False
    def show_context_menu(self, pos):
        global global_active_textcomponent,global_active_figmark
        # 显示右键菜单
        self.context_menu.exec_(global_active_textcomponent.mapToGlobal(pos))
    def on_text_changed(self):
        global global_active_textcomponent,global_active_figmark

        # 获取当前选中的文本
        selected_text = global_active_textcomponent.textCursor().selectedText()
        # 如果选中的文本不为空，则设置选中文本的背景色和前景色
        if selected_text:
            select_text = global_active_textcomponent.textCursor() # 获取当前光标位置
            text_format = global_active_textcomponent.currentCharFormat() # 获取当前字文本的字符串格式
            text_format.setBackground(QColor(self.highlight_color))  # 设置高亮颜色
            select_text.mergeCharFormat(text_format) # 追加格式到原有文本
    # text_component中高亮显示mark相同的文本
    def get_same_markindex(self,mark,input_component,highlight_color):
        if mark == '.' or not mark:
            return
        try:
            mark = mark.replace('\u2029','\n').replace('{','\{').replace('}','\}').replace('(','\(').replace(')','\)').replace('[','\[').replace(']','\]')
            all_txt = input_component.toPlainText().replace('\u2029','\n')#.replace('{','\{').replace('}','\}').replace('(','\(').replace(')','\)')
            if self.ck_1.checkState() == 0: # 未选中
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
                bracket_count = len(re.findall('\(|\)|\{|\}|\[|\]',mark))
                if index - len(mark) < 0:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark))
                else:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark) - bracket_count)
                cursor.mergeCharFormat(format)  # 改变文本的背景颜色
            # input_component.setTextCursor(cursor) # 定位至标记位置
            self.status.showMessage(f"共匹配到{match_num}个结果")
            return match_num
        except Exception as e:
            print('Error Code 206',e)
    
    def get_same_markindex_1(self,mark,input_component,highlight_color):
        global global_active_textcomponent,global_active_figmark

        if mark == '.' or not mark:
            return
        try:
            mark = mark.replace('\u2029','\n').replace('{','\{').replace('}','\}').replace('(','\(').replace(')','\)').replace('[','\[').replace(']','\]')
            all_txt = input_component.toPlainText().replace('\u2029','\n')#.replace('{','\{').replace('}','\}').replace('(','\(').replace(')','\)')
            if self.ck_1.checkState() == 0: # 未选中
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
                bracket_count = len(re.findall('\(|\)|\{|\}|\[|\]',mark))
                if index - len(mark) < 0:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark))
                else:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark) - bracket_count)
                cursor.mergeCharFormat(format)  # 改变文本的背景颜色
            # input_component.setTextCursor(cursor) # 定位至标记位置
            if match_num == 1 and self.db_flag == False:
                self.reset_textcomponentformat()
            all_txt = global_active_textcomponent.toPlainText()
            all_txt_without_dots = all_txt
            select_txt = global_active_textcomponent.textCursor().selectedText()
            select_txt_without_dots = select_txt
            for _ in '!"#$%&\！@￥%……*（）()-_+=[]\\|;:，。《》？、~·！&——+\{\}【】‘；：”“’。，、？\'：；':
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
    def fn_aitrans_keyrelease(self,event):
        if event.key() == 16777216:
            self.window_aitrans.hide()
    def ai_trans_changed(self):
        txt = self.combo_aitrans.currentText()
        self.text_aitrans_history.setPlainText(self.aitrans_search_history[txt])
    def fn_aitrans(self,in_txt):
        # self.text_aitrans.setPlainText(in_txt)
        self.aitrans_search_history[self.trans_txt] = in_txt
        self.status.showMessage('翻译完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
    def get_aitrans(self):
        global global_active_textcomponent,global_active_figmark
        self.trans_txt = global_active_textcomponent.textCursor().selectedText()
        if not self.trans_txt:
            return
        self.aitrans_search_history[self.trans_txt] = ''

        self.window_aitrans = QWidget()
        self.layout_aitrans = QGridLayout(self.window_aitrans)
        self.window_aitrans.setWindowTitle('AI翻译')
        self.window_aitrans.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_aitrans.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
        self.window_aitrans.setFixedSize(400, int(global_active_textcomponent.height()*0.67))
        self.window_aitrans.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint) # 隐藏标题栏
        
        self.text_aitrans = QTextEdit()
        self.text_aitrans.setMinimumWidth(100)
        self.text_aitrans.setMinimumHeight(60)
        self.text_aitrans.setFontPointSize(11)
        self.text_aitrans.setPlaceholderText('翻译中,请稍后...')
        self.text_aitrans.setToolTip('按ESC键关闭')
        self.text_aitrans.keyReleaseEvent = self.fn_aitrans_keyrelease

        self.text_aitrans_history = QTextEdit()
        self.text_aitrans_history.setMinimumWidth(100)
        self.text_aitrans_history.setMinimumHeight(60)
        self.text_aitrans_history.setFontPointSize(11)
        self.text_aitrans_history.setToolTip('按ESC键关闭')
        self.text_aitrans_history.keyReleaseEvent = self.fn_aitrans_keyrelease
        
        self.widget_transhistory = QWidget()
        self.transhistory_layout = QGridLayout(self.widget_transhistory)
        self.combo_aitrans = QComboBox()
        self.combo_aitrans.addItems(self.aitrans_search_history)
        self.combo_aitrans.currentIndexChanged.connect(self.ai_trans_changed)
        self.transhistory_layout.addWidget(self.combo_aitrans,0,0,1,1)
        self.transhistory_layout.addWidget(self.text_aitrans_history,1,0,1,1)

        self.tab_widget_aitrans = QTabWidget()
        self.tab_widget_aitrans.addTab(self.text_aitrans,'翻译结果')
        self.tab_widget_aitrans.addTab(self.widget_transhistory,'翻译历史')
        
        self.layout_aitrans.addWidget(self.tab_widget_aitrans,0,0,0,0)
        self.fn_animation(self.window_aitrans,0.0,1.0)
        self.animation.start()
        self.window_aitrans.show()

        global model_api
        if model_api == 'Doubao':
            self.aitrans_thread = Worker_ai_doubao('你精通专利翻译，将以下文本翻译为中文：'+self.trans_txt,self.text_aitrans)
        else:
            self.aitrans_thread = Worker_ai_deepseek('你精通专利翻译，将以下文本翻译为中文：'+self.trans_txt,self.text_aitrans)
        self.aitrans_thread.progress.connect(self.fn_aitrans)
        self.aitrans_thread.start()
    def fn_aisupplement(self,in_txt):
        global global_active_textcomponent,global_active_figmark
        self.status.showMessage('填充完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
        self.default_format()
        all_html = global_active_textcomponent.toHtml()
        self.supplement_txt = self.supplement_txt.replace('<','&lt;').replace('>','&gt;')
        all_html = all_html.replace(self.supplement_txt,in_txt)
        global_active_textcomponent.setHtml(all_html)
        self.one_key_format()
        self.get_same_markindex(in_txt,global_active_textcomponent,self.highlight_color)

    def get_aisupplement(self):
        global global_active_textcomponent,global_active_figmark
        self.supplement_txt = global_active_textcomponent.textCursor().selectedText().strip('\u2029\n ，。；、：')
        if not self.supplement_txt:
            self.status.showMessage('未识别到待填充文本，请重试')
        elif self.supplement_txt[0] == '<' and self.supplement_txt[-1] == '>':
            self.status.showMessage('文本补充中，请稍后...')
            self.status.setStyleSheet("QStatusBar {background-color: #cc6633;color: white;border:none} QStatusBar:hover{background-color:#d2794c;color: white}")
            # self.setCursor(Qt.WaitCursor)
            
            cursor = global_active_textcomponent.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock,QTextCursor.KeepAnchor,2)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock,QTextCursor.KeepAnchor,5)
            all_txt = cursor.selectedText()

            global model_api
            if model_api == 'Doubao':
                self.supplement_thread = Worker_ai_doubao(f'请结合{all_txt}上下文，以最简短的语言填充{self.supplement_txt}部分','')
            else:
                self.supplement_thread = Worker_ai_deepseek(f'请结合{all_txt}上下文，以最简短的语言填充{self.supplement_txt}部分','')

            self.supplement_thread.progress.connect(self.fn_aisupplement)
            self.supplement_thread.start()
        else:
            self.status.showMessage('未识别到待填充文本，请重试')
    def fn_aihelp_keyrelease(self,event):
        if event.key() == 16777216:
            self.window_aihelp.hide()
    def ai_help_changed(self):
        txt = self.combo_aihelp.currentText()
        self.text_aihelp_history.setPlainText(self.aihelp_search_history[txt])
    def fn_aihelp(self,in_txt):
        self.status.showMessage('查询完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
        # self.text_aihelp.setPlainText(in_txt)
        self.aihelp_search_history[self.help_txt] = in_txt
    def get_aihelp(self):
        global global_active_textcomponent,global_active_figmark
        self.status.showMessage('内容查询中,请稍后...')
        self.status.setStyleSheet("QStatusBar {background-color: #cc6633;color: white;border:none} QStatusBar:hover{background-color:#d2794c;color: white}")
        # self.setCursor(Qt.WaitCursor)

        self.help_txt = global_active_textcomponent.textCursor().selectedText()
        if not self.help_txt:
            return
        self.aihelp_search_history[self.help_txt] = ''

        self.window_aihelp = QWidget()
        self.layout_aihelp = QGridLayout(self.window_aihelp)
        self.window_aihelp.setWindowTitle(self.help_txt + '的含义')
        self.window_aihelp.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_aihelp.move(self.pos().x() + self.width() - 430,self.pos().y() + 100)
        self.window_aihelp.setFixedSize(400, int(global_active_textcomponent.height()*0.67))
        self.window_aihelp.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint) # 隐藏标题栏
        
        self.text_aihelp = QTextEdit()
        self.text_aihelp.setMinimumWidth(100)
        self.text_aihelp.setMinimumHeight(60)
        self.text_aihelp.setFontPointSize(11)
        self.text_aihelp.setPlaceholderText('内容查询中,请稍后...')
        self.text_aihelp.setToolTip('按ESC键关闭')
        self.text_aihelp.keyReleaseEvent = self.fn_aihelp_keyrelease

        self.text_aihelp_history = QTextEdit()
        self.text_aihelp_history.setMinimumWidth(100)
        self.text_aihelp_history.setMinimumHeight(60)
        self.text_aihelp_history.setFontPointSize(11)
        self.text_aihelp_history.setToolTip('按ESC键关闭')
        self.text_aihelp_history.keyReleaseEvent = self.fn_aihelp_keyrelease
        
        self.widget_history = QWidget()
        self.history_layout = QGridLayout(self.widget_history)
        self.combo_aihelp = QComboBox()
        self.combo_aihelp.addItems(self.aihelp_search_history)
        self.combo_aihelp.currentIndexChanged.connect(self.ai_help_changed)
        self.history_layout.addWidget(self.combo_aihelp,0,0,1,1)
        self.history_layout.addWidget(self.text_aihelp_history,1,0,1,1)

        self.tab_widget_aihelp = QTabWidget()
        self.tab_widget_aihelp.addTab(self.text_aihelp,'查询结果')
        self.tab_widget_aihelp.addTab(self.widget_history,'查询历史')
        
        self.layout_aihelp.addWidget(self.tab_widget_aihelp,0,0,0,0)
        self.fn_animation(self.window_aihelp,0.0,1.0)
        self.animation.start()
        self.window_aihelp.show()

        global model_api

        if model_api == 'Doubao':
            self.aihelp_thread = Worker_ai_doubao(self.help_txt + '是什么意思？',self.text_aihelp)
        else:
            self.aihelp_thread = Worker_ai_deepseek(self.help_txt + '是什么意思？',self.text_aihelp)


        self.aihelp_thread.progress.connect(self.fn_aihelp)
        self.aihelp_thread.start()
    def fn_mouse_keyrelease_text(self,event):
        global write_type,global_active_textcomponent,global_active_figmark
        if self.brush_flag == True:
            if not self.char_format:
                return
            cursor = global_active_textcomponent.textCursor()
            cursor.mergeCharFormat(self.char_format)
            global_active_textcomponent.mergeCurrentCharFormat(self.char_format)
        else:
            if event.button() == 4: # 1 左键 2 右键 4 中键
                self.reset_textcomponentformat()
            if self.db_flag == True:
                self.db_flag = False
                return
            if write_type == '撰写' and QApplication.keyboardModifiers() != Qt.ControlModifier:
                self.reset_textcomponentformat()
            self.status.showMessage(f"")
            text_cursor = global_active_textcomponent.textCursor()
            select_txt = text_cursor.selectedText()
            if self.window_table:
                self.window_table.close()
            if select_txt:
                self.get_same_markindex(select_txt,global_active_figmark,self.highlight_color)
                self.get_same_markindex_1(select_txt,global_active_textcomponent,self.highlight_color)
    
    def fn_texteditor_focusout_autosave(self,event):
        global text_editor_array,global_active_textcomponent
        try:
            text_idx = text_editor_array.index(global_active_textcomponent)
            open(f'./data/text_saver_{text_idx + 1}.html','w+',encoding='utf-8').write(global_active_textcomponent.toHtml())
        except Exception as e:
            print('Error Code 209',e)
    def fn_sync_clicked(self):
        if self.checkbox_sync.checkState() == 2:
            message_box = QMessageBox()#.question(self, '关闭程序', '即将关闭程序 <是/否>？',QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            message_box.setWindowTitle('重置格式')
            message_box.setText('为避免同步异常，即将重置当前文档为默认格式，是否继续 <是/否>？')
            message_box.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
            message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            message_box.button(QMessageBox.Yes).setText('是')
            message_box.button(QMessageBox.No).setText('否')
            reply = message_box.exec()
            if reply == QMessageBox.Yes:
                self.default_format()
                self.one_key_format()
                self.on_lineheight_changed()
    def add_markeditors(self):
        '''附图标记补全'''
        global tab_widget_mark,mark_editor_array
        global global_active_textcomponent,global_active_figmark
        self.main_widget_mark = QWidget()
        self.layout_mark_main = QGridLayout(self.main_widget_mark) # 将frame 1 & 2 横向排列
        self.main_widget_mark.setMouseTracking(True) 

        self.radio_1 = QRadioButton('上下位')
        self.radio_1.setChecked(True)
        self.radio_1.setStyleSheet("font-size: 12px;")
        self.radio_2 = QRadioButton('按顺序')
        self.radio_2.setStyleSheet("font-size: 12px;")
        self.checkbox_sync = QCheckBox("同步")
        self.checkbox_sync.setChecked(False)
        self.checkbox_sync.clicked.connect(self.fn_sync_clicked)

        tab_widget_mark = QTabWidget()
        mark_editor_array = [OcrDropTextEdit() for i in range(30)]
        global_active_figmark = mark_editor_array[0]
        self.label_mark = QLabel()
        self.label_mark.setText(f"标记补全 *共0个标记")
        # 附图标记列表
        for editor in mark_editor_array:
            editor.focusOutEvent = self.fn_textmark_focusout_autosave
            editor.mouseReleaseEvent = self.fn_highlight_figmarks  # 绑定鼠标按下事件处理方法
            editor.mouseDoubleClickEvent = self.mark_dbclick_event
            # 拖拽文件识别内容
            editor.dropEvent = self.markeditor_dropEvent
            editor.dragMoveEvent = self.dragMoveEvent
            editor.dragEnterEvent = self.dragEnterEvent

            tab_index = mark_editor_array.index(editor)
            try:
                load_txt = open(f'./data/marks_saver_{tab_index + 1}.txt','r',encoding='utf-8').read()
            except Exception as e:
                print('Error Code 602',e)
                open(f'./data/marks_saver_{tab_index + 1}.txt','a+',encoding='utf-8').write('')
                load_txt = ''
            editor.setPlainText(load_txt)

            tab_widget_mark.addTab(editor,f'列表{tab_index + 1}')

        tab_widget_mark.currentChanged.connect(self.fn_marktab_changed)

        self.layout_mark_main.addWidget(self.radio_1,0,0,1,1)
        self.layout_mark_main.addWidget(self.radio_2,0,1,1,1)
        self.layout_mark_main.addWidget(self.checkbox_sync,0,2,1,1)
        self.layout_mark_main.addWidget(tab_widget_mark,1,0,1,3)
        self.layout_mark_main.addWidget(self.label_mark,2,0,1,3)

        '''关键词补全'''
        self.main_widget_keywords = QWidget()
        self.layout_keywords_main = QGridLayout(self.main_widget_keywords)

        # 定义一个复选框
        self.checkbox_markcheck = QCheckBox("识别未用标记")
        self.checkbox_markcheck.setChecked(False)
        self.checkbox_userwords = QCheckBox("关键词补全")
        self.checkbox_userwords.setChecked(True)

        load_txt = open(f'./data/userwords_saver.txt','r',encoding='utf-8').read()
        # 自定义词库
        self.text_genword = QTextEdit()
        self.text_genword.setStyleSheet("QTextEdit {background-color: #19232d;color: white} QTextEdit:hover{background-color:#212e3b;color: white}")
        self.text_genword.setPlaceholderText("关键词补全")
        self.text_genword.setMinimumWidth(50)
        self.text_genword.setLineWrapMode(0) #不换行
        self.text_genword.setPlainText(load_txt)
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
        global global_active_textcomponent,global_active_figmark
        insert_cursor = global_active_figmark.textCursor()
        insert_cursor.select(insert_cursor.LineUnderCursor)
        global_active_figmark.setTextCursor(insert_cursor)
        select_mark = insert_cursor.selectedText().strip(' \n').split(' ')[-1]

        font_format = QTextCharFormat()
        font_format.setForeground(QColor(self.font_color))
        cursor = global_active_textcomponent.textCursor()
        re_search = QRegExp(select_mark)
        matches = re.finditer(re_search.pattern(), global_active_textcomponent.document().toPlainText().replace('\n','\u2029'))
        # 循环查找文档
        match_num = 0
        for match in matches:
            match_num += 1
            index = match.start()
            cursor.setPosition(index)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(select_mark))
            cursor.mergeCharFormat(font_format)

    def userwords_dbclick_event(self,event):
        global global_active_textcomponent,global_active_figmark
        insert_cursor = self.text_genword.textCursor()
        insert_cursor.select(insert_cursor.LineUnderCursor)
        self.text_genword.setTextCursor(insert_cursor)
        select_userword = insert_cursor.selectedText().strip(' \n')

        font_format = QTextCharFormat()
        font_format.setForeground(QColor(self.font_color))
        cursor = global_active_textcomponent.textCursor()
        re_search = QRegExp(select_userword)
        matches = re.finditer(re_search.pattern(), global_active_textcomponent.document().toPlainText().replace('\n','\u2029'))
        # 循环查找文档
        match_num = 0
        for match in matches:
            match_num += 1
            index = match.start()
            cursor.setPosition(index)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(select_userword))
            cursor.mergeCharFormat(font_format)

    def markeditor_dropEvent(self,event):
        global tab_widget_mark
        if event.mimeData().hasUrls():
            urls = [url.toLocalFile() for url in event.mimeData().urls()]
            # 处理拖放的本地文件路径
            self.in_dir = urls[0]
            self.status.showMessage('文件识别中...')
            self.tab_mark_index = tab_widget_mark.currentIndex()
            self.ocr_thread = Worker_Ocr(self.in_dir)
            self.ocr_thread.progress.connect(self.mark_editor_ocr)
            self.ocr_thread.start()
            event.accept()
        else:
            event.ignore()
    def mark_editor_ocr(self,in_txt):
        global mark_editor_array
        in_txt = self.ocr_extract_figmarks(in_txt)
        mark_editor_array[self.tab_mark_index].insertPlainText('\n' + in_txt)
        self.status.showMessage('文件完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
    def ocr_extract_figmarks(self,in_txt):
        # 统一标点符号
        if not in_txt:
            return
        # 给附图标记加括号
        find_txt = re.findall(f'.\d\d?\d?\d?[a-z|A-Z]?.',in_txt)
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
        all_txt_array = self.text_genword.toPlainText().replace('\n','\u2029').strip('\u2029\r ').split('\u2029')
        all_txt_array = refine_array(all_txt_array, 'set')
        all_txt_array.sort()
        self.text_genword.clear()
        self.text_genword.insertPlainText('\u2029'.join(all_txt_array))
        open('./data/userwords_saver.txt', 'w+', encoding='utf-8').write('\u2029'.join(all_txt_array))
        self.label_keywords.setText(f'关键词补全 *共{len(all_txt_array)}个关键词')
    # 用于自由撰写的附图标记高亮
    def fn_highlight_figmarks(self,event):
        global global_active_textcomponent,global_active_figmark
        all_mark_txt = global_active_figmark.toPlainText().strip('\u2029\r ')
        if '、' in all_mark_txt:
            return
        # 获取当前光标所在的位置
        cursor_mark = global_active_figmark.textCursor()
        select_txt = cursor_mark.selectedText()
        self.reset_figmarkformat()
        if select_txt:
            self.get_same_markindex(select_txt,global_active_figmark,self.highlight_color)
            self.get_same_markindex(select_txt,global_active_textcomponent,self.highlight_color)
        else:
            # 获取当前光标所在的行
            cursor_mark.select(QTextCursor.LineUnderCursor)
            current_mark = cursor_mark.selectedText().strip('\u2029')
            if QApplication.keyboardModifiers() != Qt.ControlModifier:
                self.reset_textcomponentformat()
            try: # 纯文本
                highlight_mark = current_mark.split(' ')[1] 
                num_1 = self.get_same_markindex(highlight_mark,global_active_textcomponent,'#e06061')
            except:
                num_1 = 0
            try: # 英文括号标记
                highlight_mark = current_mark.split(' ')[1] + '(' + current_mark.split(' ')[0] + ')'
                num_2 = self.get_same_markindex(highlight_mark,global_active_textcomponent,self.highlight_color)
            except:
                num_2 = 0

            try: # 中文括号标记
                highlight_mark = current_mark.split(' ')[1] + '（' + current_mark.split(' ')[0] + '）'
                num_3 = self.get_same_markindex(highlight_mark,global_active_textcomponent,self.highlight_color)
            except:
                num_3 = 0

            try: # 无括号标记
                highlight_mark = current_mark.split(' ')[1] + current_mark.split(' ')[0]
                num_4 = self.get_same_markindex(highlight_mark,global_active_textcomponent,self.highlight_color)
            except:
                num_4 = 0
            self.status.showMessage(f"> 匹配结果：纯文本{num_1}个 英文括号标记{num_2}个 中文括号标记{num_3}个 无括号标记{num_4}个")
        

    def fn_highlight_userwords(self,event):
        global global_active_textcomponent,global_active_figmark
        all_mark_txt = self.text_genword.toPlainText().strip('\u2029\r ')
        if '、' in all_mark_txt:
            return
        # 获取当前光标所在的位置
        cursor = self.text_genword.textCursor()
        # 获取当前光标所在的行
        current_mark = cursor.block().text().strip('\u2029')
        self.reset_textcomponentformat()
        try:
            self.get_same_markindex(current_mark,global_active_textcomponent,self.highlight_color)
        except:
            pass
        text_cursor = self.text_genword.textCursor()
        select_txt = text_cursor.selectedText()
        self.reset_figmarkformat()
        if select_txt:
            self.get_same_markindex(select_txt,self.text_genword,self.highlight_color)
    # 初始化active_figmark的格式
    def reset_figmarkformat(self):
        global global_active_textcomponent,global_active_figmark
        format = QTextCharFormat()
        format.setFontPointSize(9)
        format.setBackground(QColor(Qt.transparent))

        cursor = global_active_figmark.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(global_active_textcomponent.toPlainText()))
        cursor.mergeCharFormat(format)

        cursor = self.text_genword.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(global_active_textcomponent.toPlainText()))
        cursor.mergeCharFormat(format)
    # 初始化active_figmark的格式
    def reset_textcomponentformat(self):
        global global_active_textcomponent,global_active_figmark
        format = QTextCharFormat()
        format.setBackground(QColor(Qt.transparent))
        cursor = global_active_textcomponent.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(global_active_textcomponent.toPlainText()))
        cursor.mergeCharFormat(format)
    def fn_textmark_focusout_autosave(self,event):
        global mark_editor_array,global_active_textcomponent,global_active_figmark
        # 统一标记格式
        list_num = mark_editor_array.index(global_active_figmark)
        all_marks = global_active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('：', '').replace(':', '').replace('	', ' ').replace('，',',').strip('\u2029。')
        # 选择排序方式
        if self.radio_1.isChecked():
            figmarks_array = split_marks(all_marks)
        elif self.radio_2.isChecked():
            figmarks_array = split_marks_bysort(all_marks)
        while ' ' in figmarks_array:
            figmarks_array.remove(' ')
        # 获取光标当前的行号
        block_cursor = global_active_figmark.textCursor()
        mark_line_number = block_cursor.blockNumber()
        total_paragraphs = global_active_figmark.document().blockCount()
        line_add = int(global_active_figmark.height()/28)
        if mark_line_number + line_add >= total_paragraphs:
            mark_line_number = total_paragraphs
        else:
            mark_line_number += line_add
            
        global_active_figmark.setPlainText('\n'.join(figmarks_array))
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
                    global_active_figmark.insertPlainText(f'{i}{j} {_}\u2029')
        else:  # 获取标号列表 和 部件名称列表
            same_marks_array, same_nums_array = [], []
            cursor = QTextCursor(global_active_figmark.document())
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
                        cursor = QTextCursor(global_active_figmark.document())
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
                        cursor = QTextCursor(global_active_figmark.document())
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
            global_active_figmark.setTextCursor(cursor)        
            for _ in range(line_add):
                cursor.movePosition(QTextCursor.Down)
        # 自动同步text_component中的标记
        if self.checkbox_sync.checkState() == 2: # 0 为未选中
            # 获取当前光标位置
            block_cursor = global_active_textcomponent.textCursor()
            para_line_number = block_cursor.blockNumber()
            total_paragraphs = global_active_textcomponent.document().blockCount()
            if para_line_number + 5 > total_paragraphs:
                para_line_number = total_paragraphs
            else:
                para_line_number += 5
            self.reset_textcomponentformat()
            oldmarks_array = open(f'./data/marks_saver_{list_num + 1}.txt', 'r', encoding='utf-8').read().replace('\n','\u2029').split('\u2029')
            for old_mark in oldmarks_array:
                if not figmarks_array or not oldmarks_array:
                    break
                if old_mark not in figmarks_array:
                    old_num, old_txt = judge_mark(old_mark)
                    for new_mark in figmarks_array:
                        if new_mark not in oldmarks_array:
                            new_num, new_txt = judge_mark(new_mark)
                            if new_txt == old_txt or new_num == old_num:
                                all_txt = global_active_textcomponent.toHtml()
                                # 无附图标记的不替换
                                all_txt = all_txt.replace(f'{old_txt}{old_num}', f'{new_txt}{new_num}').replace(f'{old_txt}({old_num})', f'{new_txt}({new_num})').replace(f'{old_txt}（{old_num}）', f'{new_txt}（{new_num}）').strip('\u2029\r\t ')
                                all_txt = all_txt.replace(f'{old_num} {old_txt}', f'{new_num} {new_txt}') # 更新附图标记列表
                                global_active_textcomponent.setHtml(all_txt)
                                break
            self.on_lineheight_changed()
            block_cursor.movePosition(QTextCursor.Start)
            for _ in range(para_line_number):
                block_cursor.movePosition(QTextCursor.NextBlock)
            global_active_textcomponent.setTextCursor(block_cursor)
        # 更新标记缓存
        open(f'./data/marks_saver_{list_num + 1}.txt', 'w+', encoding='utf-8').write('\u2029'.join(figmarks_array))
        # global_active_figmark.config(foreground='grey')
        
        self.label_mark.setText(f'标记补全 *共{len(figmarks_array)}个标记')
    def show_cursor_menu(self):
        self.context_menu = QMenu()
        # self.context_menu.addSeperator()
        self.context_menu.addAction(self.action_00)
        self.context_menu.addAction(self.action_01)
        self.context_menu.addAction(self.action_02)
        self.context_menu.addAction(self.action_03)
        self.context_menu.addAction(self.action_04)
        self.menu_0 = self.context_menu.addMenu(QIcon(qta.icon('fa5b.uncharted')),"辅助撰写(A)")
        self.menu_0.addAction(self.action_08)
        self.menu_0.addAction(self.action_09)
        self.menu_0.addAction(self.action_05)
        self.menu_0.addAction(self.action_06)
        self.menu_0.addAction(self.action_07)
        self.menu_1 = self.context_menu.addMenu(QIcon(qta.icon('ph.planet-thin')),"批量文本(E)")
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

        self.menu_2 = self.context_menu.addMenu(QIcon(qta.icon('ph.path-thin')),"生成模板(H)")
        self.menu_2.addAction(self.action_21)
        self.menu_2.addAction(self.action_22)
        self.menu_2.addAction(self.action_23)
        self.menu_2.addAction(self.action_24)
        self.menu_2.addAction(self.action_25)
        self.menu_2.addAction(self.action_26)
    def add_tab_editor(self,editor):
        editor.setAutoFormatting(QTextEdit.AutoAll)
        editor.selectionChanged.connect(lambda:[self.update_format(editor)])
        editor.selectionChanged.connect(lambda:[self.add_action(editor)])
        font = QFont('宋体', 12)
        editor.setFont(font)
        editor.setFontPointSize(12)
    def add_action(self,editor):
        self.bt_bold.toggled.connect(lambda x: editor.setFontWeight(QFont.Bold if x else QFont.Normal))
        # self.toobar_bold.toggled.connect(self.set_boldfont)
        self.bt_italic.toggled.connect(editor.setFontItalic)
        self.bt_underline.toggled.connect(editor.setFontUnderline)
        self.toobar_alignl.triggered.connect(lambda: editor.setAlignment(Qt.AlignLeft))
        self.toobar_alignc.triggered.connect(lambda: editor.setAlignment(Qt.AlignCenter))
        self.toobar_alignr.triggered.connect(lambda: editor.setAlignment(Qt.AlignRight))
        self.toobar_alignj.triggered.connect(lambda: editor.setAlignment(Qt.AlignJustify))
    def set_boldfont(self):
        global global_active_textcomponent,global_active_figmark
        count = 0
        font_format = QTextCharFormat()
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().replace('\n','\u2029')
        if cursor.charFormat().font().bold():
            count += 1
        elif not cursor.charFormat().font().bold():
            pass
        re_search = QRegExp(select_txt)
        matches = re.finditer(re_search.pattern(), global_active_textcomponent.document().toPlainText().replace('\n','\u2029'))
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
    def dialog_critical(self, s):
        dlg = QMessageBox(self)
        dlg.setText(s)
        dlg.setIcon(QMessageBox.Critical)
        dlg.show()
    def file_open(self):
        global global_active_textcomponent,global_active_figmark
        path, _ = QFileDialog.getOpenFileName(self, "Open file", "", "HTML documents (*.html);;Text documents (*.txt);;Doc documents(*.doc);;Docx documents(*.docx);;All files (*.*)")
        try:
            text = open(path, 'rU').read()
        except Exception as e:
            print(e)
        else:
            self.path = path
            global_active_textcomponent.setPlainText(text)
    def splitext(self,p):
        return os.path.splitext(p)[1].lower()
    def file_save(self):
        global global_active_textcomponent,global_active_figmark
        if self.path is None:
            return self.file_saveas()
        text = global_active_textcomponent.toHtml() if self.splitext(self.path) in self.HTML_EXTENSIONS else global_active_textcomponent.toPlainText()
        try:
            with open(self.path, 'w') as f:
                f.write(text)
            self.status.showMessage('> 保存成功')
        except Exception as e:
            print(e)
    def fn_options(self):
        os.startfile('options.txt')
    def file_saveas(self):
        global global_active_textcomponent,global_active_figmark
        path, _ = QFileDialog.getSaveFileName(self, "Save file", "未命名.html", "Doc documents (*.doc);;Docx documents (*.docx);;Text documents (*.txt);;HTML documents (*.html);;All files (*.*)")
        if not path:
            return
        text = global_active_textcomponent.toHtml() if self.splitext(path) in self.HTML_EXTENSIONS else global_active_textcomponent.toPlainText()
        try:
            with open(path, 'w') as f:
                f.write(text)
            self.status.showMessage('> 保存成功')
        except Exception as e:
            print(e)
        else:
            self.path = path
    def complete_marknum(self,rep_type):
        global global_active_textcomponent,global_active_figmark
        repeat_mark_dic = {}
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')#.lstrip('1234567890')
        all_marks = global_active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('	', ' ').strip('\u2029。 ')
        figmarks_array = all_marks.replace('\r','\u2029').replace('\t','\u2029').replace('\n','\u2029').replace(',','，').replace(';','；').split('\u2029')
        # 判断重复标记
        for item_1 in figmarks_array:
            for item_2 in figmarks_array:
                mark_1 = item_1.split()[1]
                mark_2 = item_2.split()[1]
                if mark_1 in mark_2 and mark_1 != mark_2: # mark_2中含有mark_1
                    repeat_mark_dic[item_2] = item_1
        if select_txt:
            new_select_txt,repeat_array,item_lack_array = completion_nums(rep_type,all_marks,select_txt)
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt,new_select_txt).replace('。。','。')
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
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def complete_markname(self,rep_type):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        all_marks = global_active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('	', ' ').strip('\u2029。 ')
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        if select_txt:            
            new_select_txt,repeat_array,item_lack_array = completion_marks(rep_type,all_marks,select_txt)
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt,new_select_txt).replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def delete_figmarks_mohu(self):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        all_marks = global_active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('	', ' ').strip('\u2029。 ')
        select_txt = cursor.selectedText().strip('\u2029\r\t')#.lstrip('1234567890')
        if select_txt:
            # 删除带括号标记
            new_select_txt = delete_bracketmarks_mohu(select_txt)
            #  删除所有非括号标记
            find_txt_array = re.findall('.?\d.',new_select_txt)
            for _old in find_txt_array:
                if '.' not in _old and '据' not in _old and '求' not in _old and '至' not in _old and '~' not in _old and '-' not in _old and '或' not in _old and '图' not in _old:
                    _new = _old
                    for num in '0123456789':
                        _new = _new.replace(num,'')
                    new_select_txt = new_select_txt.replace(_old,_new)
            new_select_txt = new_select_txt.replace('（','').replace('）','')
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt,new_select_txt).replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def delete_figmarks(self):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        all_marks = global_active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('	', ' ').strip('\u2029。 ')
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
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt,new_select_txt).replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def num_to_bracket_num(self): # 直接为附图标记增加括号   具体实施方式 → 权利要求 答复OA从说明书中增加内容
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t') + '。' # .lstrip('1234567890')
        if select_txt:
            new_select_txt = select_txt
            find_txt = re.findall(f'.\d\d?\d?\d?[a-z|A-Z]?.',new_select_txt)
            if find_txt:
                for _ in find_txt:
                    if '图' in _:
                        pass
                    elif _[0] not in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' and _[-1] not in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        new_select_txt = new_select_txt.replace(_,_[0]+'(' + _[1:-1] + ')' +_[-1])
            # 删除权利要求(x)的括号
            find_txt = re.findall(f'权利要求\(.*?\)',new_select_txt)
            if find_txt:
                for _ in find_txt:
                    new_select_txt = new_select_txt.replace(_,_.replace('(','').replace(')',''))
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt.strip('。'),new_select_txt.strip('。')).replace('。。','。').replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def refine_form(self):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')#.lstrip('1234567890')
        if select_txt:
            new_select_txt = arrenge_document(select_txt)
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt,new_select_txt).replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def del_useless_enters(self):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().replace('\u2029','\n').strip('\u2029\n\r\t')#.lstrip('1234567890')
        new_select_txt = refine_mutilines(select_txt)
        out_txt = select_txt.replace(select_txt,new_select_txt).replace('。。','。')
        cursor.deleteChar()
        cursor.insertText(out_txt)
        self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def del_spaces(self):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().replace('\u2029','\n').strip('\u2029\r\t')
        if select_txt:
            new_select_txt = select_txt.replace(' ','').replace(']','] ').replace(']  ','] ')
            out_txt = select_txt.replace('\u2029','\n').replace(select_txt,new_select_txt).replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def rep_element(self):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')#.lstrip('1234567890')
        if select_txt:
            new_select_txt = rep_elements(select_txt)
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt,new_select_txt).replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def bracket_num2num(self):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        all_marks = global_active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('	', ' ').strip('\u2029。 ')
        figmarks_array = split_marks(all_marks)
        if select_txt:
            new_select_txt = select_txt
            for item in figmarks_array:
                fig_text = item.split(' ')[1]
                fig_num = item.split(' ')[0]
                new_select_txt = new_select_txt.replace(f'{fig_text}({fig_num})',f'{fig_text}{fig_num}')
                new_select_txt = new_select_txt.replace(f'{fig_text}（{fig_num}）',f'{fig_text}{fig_num}')
            # for _ in '()（）':
            #     new_select_txt = new_select_txt.replace(_,'')
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt,new_select_txt).replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    def marks_to_para(self):
        global global_active_textcomponent,global_active_figmark
        try:
            marks_array = global_active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('	', ' ').strip('\u2029。 ').split('\u2029')
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
            global_active_textcomponent.insertHtml(out_txt)
        except Exception as e:
            print('Error Code 103',e)
    def extract_patent_content(self):#claim 2 content
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        all_marks = global_active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('	', ' ').strip('\u2029。 ')
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        if select_txt:
            # 删除带括号标记
            new_select_txt = delete_bracketmarks(select_txt.replace(':','：').replace('所述的','所述'),all_marks)
            # 删除所有数字
            for num in range(99,0,-1):
                new_select_txt = new_select_txt.replace(f"{num}.",'')
            # 将“根据权利要求……,其特征在于：” 替换为”进一步的“
            find_txt_array = re.findall('根据.*?，其特征在于：',new_select_txt)
            for _ in find_txt_array:
                new_select_txt = new_select_txt.replace(_,'进一步的，')
            new_select_txt = new_select_txt.replace('一种','该').replace('其特征是：','其技术要点是：').replace('其特征在于：','其技术要点是：')
            out_txt = select_txt.strip('\u2029').replace(select_txt,new_select_txt).replace('。。','。').replace(' ','')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
    #获取附图标记
    def extract_figmarks(self):
        global global_active_textcomponent,global_active_figmark
        # 统一标点符号
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        select_txt = refine_intxt(select_txt)
        if select_txt:
            # 给附图标记加括号
            find_txt = re.findall(f'.\d\d?\d?\d?[a-z|A-Z]?.',select_txt)
            if find_txt:
                for _ in find_txt:
                    if ('（' in _ and '）' in _) or ('(' in _ and ')' in _):
                        continue
                    if _[0] not in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' and _[-1] not in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        select_txt = select_txt.replace(_,_[0]+'（' + _[1:-1] + '）' +_[-1])
            # 查找附图标记名称
            mark_array_name = search_marks(select_txt)
            # 查找附图标记编号
            mark_array,same_marks_array = get_figmarks(mark_array_name,select_txt)
            # 输出结果
            global_active_figmark.insertPlainText('\n'+'\n'.join(mark_array))
    # 删除段号
    def del_paranum(self):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t')
        if select_txt:
            new_select_txt = select_txt
            del_array = re.findall('\[\d\d\d\d\]',select_txt)
            for _ in del_array:
                new_select_txt = new_select_txt.replace(_ + ' \u2029','').replace(_ + '\u2029','').replace(_ + ' ','').replace(_,'')
            out_txt = select_txt.replace('\n','\u2029').replace(select_txt,new_select_txt).replace('。。','。')
            cursor.deleteChar()
            cursor.insertText(out_txt)
            self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
            global_active_textcomponent.setTextCursor(cursor)
    # 增加段号
    def add_paranum(self):
        global global_active_textcomponent,global_active_figmark
        cursor = global_active_textcomponent.textCursor()
        select_txt = cursor.selectedText().strip('\u2029\r\t').replace('\n','\u2029').replace('］',']').replace('[','[')
        txt_array = select_txt.split('\u2029')
        para_array = []
        para_index = 1
        for para in txt_array:
            # 删除短号
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
        self.get_same_markindex(out_txt,global_active_textcomponent,self.highlight_color)
        global_active_textcomponent.setTextCursor(cursor)
    def generate_oa_model(self):
        global tab_widget_text,global_active_textcomponent,global_active_figmark
        tab_index = tab_widget_text.currentIndex()
        title = tab_widget_text.tabText(tab_index).replace('实用新型-','').replace('发明-','')
        all_txt = global_active_textcomponent.toHtml() + open('./data/model_oa.html','r',encoding='utf-8').read().replace('&lt;TITLE&gt;',title)
        global_active_textcomponent.clear()
        global_active_textcomponent.setHtml(all_txt)
    def generate_description_model(self):
        global tab_widget_text,global_active_textcomponent,global_active_figmark
        tab_index = tab_widget_text.currentIndex()
        title = tab_widget_text.tabText(tab_index).replace('实用新型-','').replace('发明-','')
        all_txt = global_active_textcomponent.toHtml() + open('./data/model_des.html','r',encoding='utf-8').read().replace('&lt;标题&gt;',title) 
        global_active_textcomponent.clear()
        global_active_textcomponent.setHtml(all_txt)
    def generate_claim_model(self):
        global tab_widget_text,global_active_textcomponent,global_active_figmark
        tab_index = tab_widget_text.currentIndex()
        title = tab_widget_text.tabText(tab_index).replace('实用新型-','').replace('发明-','')
        all_txt = open('./data/model_claim.html','r',encoding='utf-8').read().replace('&lt;TITLE&gt;',title) + global_active_textcomponent.toHtml()
        global_active_textcomponent.clear()
        global_active_textcomponent.setHtml(all_txt)
    def generate_re_model(self):
        global tab_widget_text,global_active_textcomponent,global_active_figmark
        tab_index = tab_widget_text.currentIndex()
        title = tab_widget_text.tabText(tab_index).replace('实用新型-','').replace('发明-','')
        all_txt = global_active_textcomponent.toHtml() + open('./data/model_re.html','r',encoding='utf-8').read().replace('&lt;TITLE&gt;',title)
        global_active_textcomponent.clear()
        global_active_textcomponent.setHtml(all_txt)
    def generate_invalid_model(self):
        global tab_widget_text,global_active_textcomponent,global_active_figmark
        tab_index = tab_widget_text.currentIndex()
        title = tab_widget_text.tabText(tab_index).replace('实用新型-','').replace('发明-','')
        all_txt = global_active_textcomponent.toHtml() + open('./data/model_invalid.html','r',encoding='utf-8').read().replace('&lt;TITLE&gt;',title)
        global_active_textcomponent.clear()
        global_active_textcomponent.setHtml(all_txt)
    def generate_ai_model(self):
        global tab_widget_text,global_active_textcomponent,global_active_figmark
        tab_index = tab_widget_text.currentIndex()
        title = tab_widget_text.tabText(tab_index).replace('实用新型-','').replace('发明-','')
        all_txt = global_active_textcomponent.toHtml() + open('./data/model_ai.html','r',encoding='utf-8').read().replace('&lt;TITLE&gt;',title)
        global_active_textcomponent.clear()
        global_active_textcomponent.setHtml(all_txt)
    def image_marks(self, inputtxt, fig_dic):
        self.word_array, self.ori_array = [], []
        for key in fig_dic:  # 判断附图标记
            if len(self.word_array) >= 5:
                break
            if inputtxt[-5:] == key[0] and len(inputtxt) == 5:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-5:])
                break
            elif inputtxt[-4:] == key[0] and len(inputtxt) >= 4:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-4:])
                break
            elif inputtxt[-3:] == key[0] and len(inputtxt) >= 3:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-3:])
                break
            elif inputtxt[-2:] == key[0] and len(inputtxt) >= 2:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-2:])
                break
            elif inputtxt[-1:] == key[0] and len(inputtxt) >= 1:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-1:])
    def get_totalkeys(self):
        global global_active_textcomponent,global_active_figmark
        try:
            self.key_1, self.key_2, self.key_3, self.key_4,self.key_5 = '', '', '', '',''
            cursor = global_active_textcomponent.textCursor()
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor,5)
            self.total_key = cursor.selectedText()
            self.key_5 = self.total_key[4]
            self.key_4 = self.total_key[3]
            self.key_3 = self.total_key[2]
            self.key_2 = self.total_key[1]
            self.key_1 = self.total_key[0]
        except:
            pass
    def count_words(self,event):
        global global_active_textcomponent,global_active_figmark
        # 统计字数
        all_txt = global_active_textcomponent.toPlainText()
        all_txt_without_dots = all_txt
        select_txt = global_active_textcomponent.textCursor().selectedText()
        select_txt_without_dots = select_txt
        for _ in '!"#$%&\！@￥%……*（）()-_+=[]\\|;:，。《》？、~·！#——+\{\}【】‘；：”“’。，、？\'：；':
            select_txt_without_dots = select_txt_without_dots.replace(_, '')
            all_txt_without_dots = all_txt_without_dots.replace(_, '')
        len_all = len(all_txt)
        len_all_without_dots = len(all_txt_without_dots)
        if select_txt.strip(' '):
            len_select = len(select_txt)
            len_select_without_dots = len(select_txt_without_dots)
            self.status.showMessage(f'> 已选择{len_select}/{len_all}个字（含标点） 已选择{len_select_without_dots}/{len_all}个字（不含标点）')
        else: 
            self.status.showMessage(f'> 共{len_all}个字（含标点） 共{len_all_without_dots}个字（不含标点）')
        self.old_x = self.pos().x()
        self.old_y = self.pos().y()
        self.drag_flag = 'down'
    def get_word_array(self):
        global global_active_textcomponent,global_active_figmark
        self.fig_dic = {}
        all_marks = global_active_figmark.toPlainText().replace('\n','\u2029').replace('；', ';').replace('	', ' ').strip('\u2029。 ')
        figmarks_array = split_marks(all_marks)
        for _ in figmarks_array:
            fig_num, fig_text = judge_mark(_)
            self.fig_dic[fig_num] = fig_text
        fig_dic_t = self.fig_dic
        self.fig_dic = sorted(fig_dic_t.items(), key=lambda fig_dic_t: len(fig_dic_t[0]), reverse=True)
        self.image_marks(self.total_key, self.fig_dic)
    def fn_keypressevent_tmp(self,event):
        global global_active_textcomponent,global_active_figmark
        try:
            insert_txt = chr(event.key())
            global_active_textcomponent.insertPlainText(insert_txt)
        except:
            pass
        if event.key() == 16777219: # 代表退格键
            cursor = global_active_textcomponent.textCursor()
            cursor.deletePreviousChar()
        elif event.key() == 32: # 空格
            global_active_textcomponent.insertPlainText(' ')
    def fn_text_changed(self):
        global global_active_textcomponent,global_active_figmark
        select_txt = ''
        if write_auto == '补全' and self.total_key:
            self.total_key = ''
            cursor = global_active_textcomponent.textCursor()
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor,2)
            select_txt = cursor.selectedText()
            try:
                if select_txt[-1] not in '1234567890\u2029\n' and select_txt[0] in '1234567890':
                    cursor = global_active_textcomponent.textCursor()
                    for i in range(0,5):
                        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor,1)
                        select_txt = cursor.selectedText().replace(')','）').replace('(','（')
                        if select_txt[-1] in '（）[]<>《》\{\}':
                            self.total_key = ''
                            break
                        elif len(select_txt) > 1 and select_txt[0] in '1234567890' and select_txt[0] not in '（）[]<>《》\{\}':
                            self.total_key = select_txt[0:-1]
                        elif len(select_txt) > 1 and select_txt[0] in '（）[]<>《》\{\}':
                            break
                        elif len(select_txt) > 1 and select_txt[0] not in '1234567890':
                            break
                if self.total_key:
                    self.get_word_array()
                    if not self.word_array:
                        return
                    self.space_out_words()
                    if select_txt[-1] == '.':
                        global_active_textcomponent.insertPlainText('。')
                    else:
                        global_active_textcomponent.insertPlainText(select_txt[-1])
            except Exception as e:
                print(e)
    def fn_keyreleaseevent(self,event): # active_textcomponent 按下任意键
        global model_type,write_auto,global_active_textcomponent,global_active_figmark
        if event.key() in [Qt.Key_Up,Qt.Key_Down,Qt.Key_Left,Qt.Key_Right]:
            self.reset_textcomponentformat()
            cursor = global_active_textcomponent.textCursor()
            self.get_same_markindex_1(cursor.selectedText(),global_active_textcomponent,self.highlight_color)
        if model_type == '联想':
            self.get_totalkeys()
            try:
                if self.checkbox_markcheck.checkState() == 2: # 查找未使用标记
                    self.check_text_figmarks_unused()
                elif event.key() in [i for i in range(48,58)] or event.key() in [i for i in range(65,72)] and write_auto == '关闭':  # '1234567890abcdefg'未选中自动补全附图标记
                    self.get_word_array()
                    modifiers = event.modifiers()
                    if not self.word_array:
                        return
                    elif modifiers & Qt.ControlModifier:
                        return
                    elif modifiers & Qt.AltModifier:
                        return
                    elif modifiers & (Qt.ControlModifier | Qt.AltModifier):
                        return
                    self.fn_show_window()
                elif self.checkbox_userwords.checkState() == 2 and self.total_key and event.modifiers() == Qt.ControlModifier and event.key() == 96:
                    self.fn_show_window_keywords()
                elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Return: # 判断序号 并自动续写
                    cursor = global_active_textcomponent.textCursor()
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
                        for i in range(0,10): # 判断前十个字符是否为数字
                            if base_txt[i] not in '01234567890' and base_txt[i] in '.、：:)）':
                                base_num = base_txt[0:i]
                                base_title = re.findall('一种(.*?)，',base_txt.replace(',','，')) + re.findall('根据.*?所述的(.*?)，',base_txt.replace(',','，'))
                                if base_title:
                                    base_title = base_title[0]
                                else:
                                    base_title = ''
                                break
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
        global global_active_textcomponent, global_active_figmark, tab_widget_text
        try:
            cursor = global_active_textcomponent.textCursor()
            clipboard = QApplication.clipboard()

            def copy_action():
                if cursor.hasSelection():
                    if len(cursor.selectedText()) <= 60:
                        clipboard.setText(cursor.selectedText())
                    else:
                        self.clip_txt = cursor.selectedText()
                        self.mime_data = QMimeData()
                        fragment = QTextDocumentFragment(cursor)
                        html = fragment.toHtml()
                        try:
                            self.mime_data.setData("text/html", bytes(html, 'utf-8'))
                            clipboard.setMimeData(self.mime_data)
                        except:
                            clipboard.setText(cursor.selectedText())
            def cut_action():
                copy_action()
                cursor.deleteChar()

            def paste_action():
                try:
                    cursor.removeSelectedText(cursor.selectedText())
                except:
                    pass
                if clipboard.text():
                    cursor.insertText(clipboard.text())
                elif self.clip_txt:
                    cursor.insertText(self.clip_txt)
            def update_status():
                tab_index = tab_widget_text.currentIndex()
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
                (Qt.ControlModifier, Qt.Key_F): self.show_repwindow,
                (Qt.ControlModifier, Qt.Key_Q): self.extract_figmarks,
                (Qt.ControlModifier, Qt.Key_W): self.refine_form,
                (Qt.ControlModifier, Qt.Key_E): self.rep_element,
                (Qt.ControlModifier, Qt.Key_R): self.del_useless_enters,
                (Qt.ControlModifier, Qt.Key_T): self.del_spaces,
                (Qt.ControlModifier, Qt.Key_J): self.del_paranum,
                (Qt.ControlModifier, Qt.Key_G): self.add_paranum,
                (Qt.ControlModifier, 96): lambda: self.fn_show_window_keywords() if self.checkbox_userwords.checkState() == 2 and self.total_key else None,
                (Qt.ControlModifier, Qt.Key_A): lambda: global_active_textcomponent.selectAll(),
                (Qt.ControlModifier, Qt.Key_Z): lambda: global_active_textcomponent.undo(),
                (Qt.ControlModifier, Qt.Key_Y): lambda: global_active_textcomponent.redo(),
                (Qt.ControlModifier, Qt.Key_S): lambda: (self.fn_texteditor_focusout_autosave(event), self.fn_textmark_focusout_autosave(event), update_status()),
                (Qt.AltModifier, Qt.Key_1): self.generate_oa_model,
                (Qt.AltModifier, Qt.Key_2): self.generate_description_model,
                (Qt.AltModifier, Qt.Key_3): self.generate_claim_model,
                (Qt.AltModifier, Qt.Key_4): self.generate_re_model,
                (Qt.AltModifier, Qt.Key_5): self.generate_invalid_model,
                (Qt.AltModifier, Qt.Key_6): self.generate_ai_model,
                (Qt.AltModifier, Qt.Key_Q): self.get_aisupplement,
                (Qt.AltModifier, Qt.Key_W): self.get_aicontinue,
                (Qt.AltModifier, Qt.Key_E): self.get_aidecorate,
                (Qt.AltModifier, Qt.Key_R): self.get_aihelp,
                (Qt.AltModifier, Qt.Key_T): self.get_aitrans,
            }

            # 处理按键组合
            key_combination = (event.modifiers(), event.key())
            if key_combination in key_mapping:
                key_mapping[key_combination]()
            elif event.key() == Qt.Key_PageDown:
                cursor.movePosition(QTextCursor.Down, n=20)
                global_active_textcomponent.setTextCursor(cursor)
            elif event.key() == Qt.Key_PageUp:
                cursor.movePosition(QTextCursor.Up, n=20)
                global_active_textcomponent.setTextCursor(cursor)
            elif event.key() == Qt.Key_Escape:
                self.reset_textcomponentformat()
                for window in [self.window_aitrans, self.window_aihelp, self.window_continue, self.window_search,
                            self.window_decorate, self.window_show, self.window_symbol, self.window_rep,
                            self.window_table, self.window_api]:
                    if window:
                        window.close()
            elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                cursor.insertHtml('\u2029')
            elif event.key() in [Qt.Key_Delete, Qt.Key_Backspace, Qt.Key_Tab, Qt.Key_Home, Qt.Key_End]:
                actions = {
                    Qt.Key_Delete: cursor.deleteChar,
                    Qt.Key_Backspace: cursor.deletePreviousChar,
                    Qt.Key_Tab: lambda: cursor.insertText('\t'),
                    Qt.Key_Home: lambda: cursor.setPosition(0),
                    Qt.Key_End: lambda: cursor.setPosition(len(global_active_textcomponent.toPlainText()))
                }
                actions[event.key()]()
                if event.key() in [Qt.Key_Home, Qt.Key_End]:
                    global_active_textcomponent.setTextCursor(cursor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
                directions = {
                    Qt.Key_Up: QTextCursor.Up,
                    Qt.Key_Down: QTextCursor.Down,
                    Qt.Key_Left: QTextCursor.Left,
                    Qt.Key_Right: QTextCursor.Right
                }
                global_active_textcomponent.moveCursor(directions[event.key()], QTextCursor.KeepAnchor)
            elif event.key() in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
                directions = {
                    Qt.Key_Up: QTextCursor.Up,
                    Qt.Key_Down: QTextCursor.Down,
                    Qt.Key_Left: QTextCursor.Left,
                    Qt.Key_Right: QTextCursor.Right
                }
                global_active_textcomponent.moveCursor(directions[event.key()])
            elif event.text() and event.text() in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                cursor.insertText(event.text())
            elif event.modifiers() in [Qt.ControlModifier, Qt.AltModifier]:
                pass
            else:
                cursor.insertText(chr(event.key()))
        except Exception as e:
            # print('Error 210',e)
            pass


    def fn_keypressevent_xxxx(self,event):
        global global_active_textcomponent,global_active_figmark,tab_widget_text
        try:
            cursor = global_active_textcomponent.textCursor()
            clipboard = QApplication.clipboard()
            if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C and cursor.hasSelection():
                self.clip_txt = cursor.selectedText()
                self.mime_data = QMimeData()
                fragment = QTextDocumentFragment(cursor)
                html = fragment.toHtml()
                try:
                    self.mime_data.setData("text/html", bytes(html, 'utf-8'))
                    clipboard.setMimeData(self.mime_data)
                except:
                    clipboard.setText(cursor.selectedText())
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_X and cursor.hasSelection():
                self.clip_txt = cursor.selectedText()
                self.mime_data = QMimeData()
                fragment = QTextDocumentFragment(cursor)
                html = fragment.toHtml()
                try:
                    self.mime_data.setData("text/html", bytes(html, 'utf-8'))
                    clipboard.setMimeData(self.mime_data)
                except:
                    clipboard.setText(cursor.selectedText())
                cursor.deleteChar()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_V:
                try:
                    cursor.removeSelectedText(cursor.selectedText())
                except:
                    pass
                if clipboard.text():
                    cursor.insertText(clipboard.text())
                elif self.clip_txt:
                    cursor.insertText(self.clip_txt)
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_1:
                self.complete_marknum(0)
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_2:
                self.complete_marknum(1)
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_3:
                self.complete_markname(0)
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_4:
                self.complete_markname(1)
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_5:
                self.delete_figmarks()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_6:
                self.num_to_bracket_num()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_7:
                self.bracket_num2num()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_8:
                self.marks_to_para()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_9:
                self.extract_patent_content()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_F:
                self.show_repwindow()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Q:
                self.extract_figmarks()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_W:
                self.refine_form()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_E:
                self.rep_element()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_R:
                self.del_useless_enters()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_T:
                self.del_spaces()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_J:
                self.del_paranum()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_G:
                self.add_paranum()
            elif event.modifiers() == Qt.ControlModifier and event.key() == 96:
                if self.checkbox_userwords.checkState() == 2 and self.total_key:
                    self.fn_show_window_keywords()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_A:
                global_active_textcomponent.selectAll()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Z:
                global_active_textcomponent.undo()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Y:
                global_active_textcomponent.redo()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_S:
                self.fn_texteditor_focusout_autosave(event)
                self.fn_textmark_focusout_autosave(event)
                tab_index = tab_widget_text.currentIndex()
                tab_name = self.tab_name_array[tab_index]
                self.status.showMessage(f'> 《{tab_name}》 保存成功')
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_1:
                self.generate_oa_model()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_2:
                self.generate_description_model()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_3:
                self.generate_claim_model()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_4:
                self.generate_re_model()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_5:
                self.generate_invalid_model()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_6:
                self.generate_ai_model()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_Q:
                self.get_aisupplement()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_W:
                self.get_aicontinue()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_E:
                self.get_aidecorate()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_R:
                self.get_aihelp()
            elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_T:
                self.get_aitrans()
            elif event.key() == Qt.Key_PageDown:
                cursor.movePosition(QTextCursor.Down, n=20)
                global_active_textcomponent.setTextCursor(cursor)
            elif event.key() == Qt.Key_PageUp:
                cursor.movePosition(QTextCursor.Up, n=20)
                global_active_textcomponent.setTextCursor(cursor)
            elif event.key() == Qt.Key_Escape:
                self.reset_textcomponentformat()
                if self.window_aitrans:self.window_aitrans.close()
                if self.window_aihelp:self.window_aihelp.close()
                if self.window_continue:self.window_continue.close()
                if self.window_search:self.window_search.close()
                if self.window_decorate:self.window_decorate.close()
                if self.window_show:self.window_show.close()
                if self.window_symbol:self.window_symbol.close()
                if self.window_rep:self.window_rep.close()
                if self.window_table:self.window_table.close()
                if self.window_api:self.window_api.close()
            elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                cursor.insertHtml('\u2029')
            elif event.key() == Qt.Key_Delete:
                cursor.deleteChar()
            elif event.key() == Qt.Key_Backspace:
                cursor.deletePreviousChar()
            elif event.key() == Qt.Key_Tab:
                cursor.insertText('\t')
            elif event.key() == Qt.Key_Home:
                cursor.setPosition(0)
                global_active_textcomponent.setTextCursor(cursor)
            elif event.key() == Qt.Key_End:
                cursor.setPosition(len(global_active_textcomponent.toPlainText()))
                global_active_textcomponent.setTextCursor(cursor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Up:
                global_active_textcomponent.moveCursor(QTextCursor.Up, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Down:
                global_active_textcomponent.moveCursor(QTextCursor.Down, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Left:
                global_active_textcomponent.moveCursor(QTextCursor.Left, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Right:
                global_active_textcomponent.moveCursor(QTextCursor.Right, QTextCursor.KeepAnchor)
            elif event.key() == Qt.Key_Up:
                global_active_textcomponent.moveCursor(QTextCursor.Up)
            elif event.key() == Qt.Key_Down:
                global_active_textcomponent.moveCursor(QTextCursor.Down)
            elif event.key() == Qt.Key_Left:
                global_active_textcomponent.moveCursor(QTextCursor.Left)
            elif event.key() == Qt.Key_Right:
                global_active_textcomponent.moveCursor(QTextCursor.Right)
            elif event.text() and event.text() in '1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                cursor.insertText(event.text())            
            elif event.modifiers() == Qt.ControlModifier or event.modifiers() == Qt.AltModifier:
                pass
            else:
                cursor.insertText(chr(event.key()))
        except Exception as e:
            # print('Error 210',e)
            pass
    # 校验未被使用的附图标记
    def check_text_figmarks_unused(self):
        global global_active_textcomponent,global_active_figmark
        self.reset_figmarkformat()
        self.fig_dic = {}
        all_marks = global_active_figmark.toPlainText().replace('；', ';').replace('\n', '\u2029').replace('	', ' ').strip('\u2029。 ')
        figmarks_array = split_marks(all_marks)
        all_txt = global_active_textcomponent.toPlainText()
        for _ in figmarks_array:
            fig_num, fig_text = judge_mark(_)
            self.fig_dic[fig_num] = fig_text
        mark_index = 0
        for _ in self.fig_dic:
            mark_index += 1
            item = self.fig_dic[_]
            if item not in all_txt:
                # 选择相应行
                cursor = QTextCursor(global_active_figmark.document())
                cursor.movePosition(QTextCursor.Start)
                cursor.movePosition(QTextCursor.Down,QTextCursor.MoveAnchor, figmarks_array.index(f'{_} {item}'))
                cursor.movePosition(QTextCursor.StartOfLine)
                cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
                global_active_figmark.setTextCursor(cursor)
                # 设置高亮
                format = cursor.charFormat()
                format.setBackground(QColor(self.highlight_color))
                cursor.setCharFormat(format)
    # 补全自定义词库
    def image_words(self, inputtxt, inputarray):
        self.word_array, self.ori_array = [], []
        for key in inputarray:
            if len(self.word_array) >= 5:
                break
            if inputtxt[-5:] in key and len(inputtxt) == 5:
                self.word_array.append(key)
                self.ori_array.append(inputtxt[-5:])
            elif inputtxt[-4:] in key and len(inputtxt) >= 4:
                self.word_array.append(key)
                self.ori_array.append(inputtxt[-4:])
            elif inputtxt[-3:] in key and len(inputtxt) >= 3:
                self.word_array.append(key)
                self.ori_array.append(inputtxt[-3:])
            elif inputtxt[-2:] in key and len(inputtxt) >= 2:
                self.word_array.append(key)
                self.ori_array.append(inputtxt[-2:])
    # 生成关联内容
    # 用于自由撰写的附图标记
    def fn_show_repwindow(self):
        global global_active_textcomponent,global_active_figmark
        self.window_rep = QWidget()
        self.window_rep_layout = QGridLayout(self.window_rep)
        self.window_rep.setWindowTitle("替换")
        self.window_rep.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_rep.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) # 隐藏标题栏
        self.window_rep.setFixedSize(240, 250)
        self.window_rep.move(self.pos().x() + self.width() - 270,self.pos().y() + 100)

        self.text_rename_before = QTextEdit()
        self.text_rename_before.setFixedSize(self.window_rep.width()-15,30)
        self.text_rename_before.setPlaceholderText('替换前')
        self.text_rename_before.setText(self.select_txt)

        self.text_rename_after = QTextEdit()
        self.text_rename_after.setFixedSize(self.window_rep.width()-15,30)
        self.text_rename_after.setPlaceholderText('替换后')
        self.text_rename_after.setText(self.select_txt)
        self.text_rename_after.keyPressEvent = self.fn_rep_keypressEvent

        self.text_rename_history = QTextEdit()
        self.text_rename_history.setLineWrapMode(QTextEdit.NoWrap)
        self.text_rename_history.setFixedWidth(self.window_rep.width()-15)
        self.text_rename_history.setMinimumHeight(60)
        self.text_rename_history.setPlaceholderText('替换历史')
        self.text_rename_history.setPlainText('\n'.join(self.rename_history_array))
        self.text_rename_history.mouseReleaseEvent = self.fn_rep_mouserelease

        bt_rep = QPushButton('全部替换')
        bt_rep.setFixedSize(95, 30)
        bt_rep.clicked.connect(self.fn_rep)

        bt_close = QPushButton('关  闭')
        bt_close.setFixedSize(95, 30)
        bt_close.clicked.connect(lambda:[self.window_rep.hide()])
       
        bt_more = QPushButton('<>')
        bt_more.setToolTip('切换模式')
        bt_more.setFixedSize(15, 30)
        bt_more.clicked.connect(self.fn_more)

        self.text_rep_left = QTextEdit()
        self.text_rep_left.setFixedSize(95,190)
        self.text_rep_left.setPlaceholderText('替换前')
        self.text_rep_left.setText(self.select_txt)

        self.text_rep_right = QTextEdit()
        self.text_rep_right.setFixedSize(95,190)
        self.text_rep_right.setPlaceholderText('替换后')
        self.text_rep_right.setText(self.select_txt)

        self.window_rep_layout.addWidget(self.text_rename_before,0,0,1,3)
        self.window_rep_layout.addWidget(self.text_rename_after,1,0,1,3)
        self.window_rep_layout.addWidget(self.text_rename_history,2,0,1,3)
        self.window_rep_layout.addWidget(bt_rep,3,0,1,1)
        self.window_rep_layout.addWidget(bt_close,3,1,1,1)
        self.window_rep_layout.addWidget(bt_more,3,2,1,1)

        array_txt = global_active_figmark.toPlainText().replace(' ','')
        for i in '0123456789':
            array_txt = array_txt.replace(i,'')
        # self.auto_complete(array_txt.split('\n') + self.text_genword.toPlainText().split('\n'),self.text_rename_before)
        # self.auto_complete(array_txt.split('\n') + self.text_genword.toPlainText().split('\n'),self.text_rename_after)
    def fn_more(self):
        global rep_model
        if rep_model == 1:
            self.text_rename_before.show()
            self.text_rename_after.show()
            self.text_rename_history.show()
            self.text_rep_left.hide()
            self.text_rep_right.hide()
            rep_model = 0
        elif rep_model == 0:
            self.text_rename_before.hide()
            self.text_rename_after.hide()
            self.text_rename_history.hide()
            self.text_rep_left.show()
            self.text_rep_right.show()
            self.window_rep_layout.addWidget(self.text_rep_left,0,0,1,1)
            self.window_rep_layout.addWidget(self.text_rep_right,0,1,1,1)
            rep_model = 1
    def fn_rep(self):
        global global_active_textcomponent,global_active_figmark
        block_cursor = global_active_textcomponent.textCursor()
        line_number = block_cursor.blockNumber()
        total_paragraphs = global_active_textcomponent.document().blockCount()
        if line_number + 5 > total_paragraphs:
            line_number = total_paragraphs
        else:
            line_number += 5
        if rep_model == 0:
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
                all_txt = global_active_textcomponent.toHtml()
                rep_array = re.findall('>.*?<',all_txt)
                temp_array = []
                for item in rep_array:
                    if ' ' in item:
                        rep_item = item.replace(' ','')
                        temp_array.append(f'{item}_{rep_item}')
                for item in temp_array:
                    before_txt = item.split('<_>')[0] +'<'
                    end_txt = '>'+item.split('<_>')[1]
                    all_txt = all_txt.replace(before_txt, end_txt)
                global_active_textcomponent.setHtml(all_txt)
            elif end_txt != before_txt:
                all_txt = global_active_textcomponent.toHtml()
                all_txt = all_txt.replace(before_txt, end_txt)
                all_txt = all_txt.replace('实用新型人', '发明人')
                global_active_textcomponent.setHtml(all_txt)
            self.window_rep.hide()
            self.on_lineheight_changed()
        elif rep_model == 1:
            before_array = self.text_rep_left.toPlainText().strip('\n\u2029').split('\n')
            end_array = self.text_rep_right.toPlainText().strip('\n\u2029').split('\n')
            all_txt = global_active_textcomponent.toHtml()
            if before_array and len(before_array) == len(end_array):
                for i in range(0,len(before_array)):
                    before_txt = before_array[i]
                    end_txt = end_array[i]
                    all_txt = all_txt.replace(before_txt, end_txt)
            global_active_textcomponent.setHtml(all_txt)
        # 重新定位光标
        cursor = global_active_textcomponent.textCursor()
        cursor.movePosition(QTextCursor.Start)
        for _ in range(line_number):
            cursor.movePosition(QTextCursor.NextBlock)
        global_active_textcomponent.setTextCursor(cursor)
    def fn_rep_keypressEvent(self,event):
        global global_active_textcomponent,global_active_figmark
        cursor = self.text_rename_after.textCursor()
        clipboard = QApplication.clipboard()
        try:
            if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
                clipboard.setText(cursor.selectedText())
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_X:
                clipboard.setText(cursor.selectedText())
                cursor.deleteChar()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_V:
                if clipboard.text():
                    cursor.insertText(clipboard.text())
                elif self.clip_txt:
                    cursor.insertText(self.clip_txt)
            elif event.key() == Qt.Key_Delete:
                cursor.deleteChar()
            elif event.key() == Qt.Key_Backspace:
                cursor.deletePreviousChar()
            elif event.key() == Qt.Key_Home:
                cursor.setPosition(0)
                self.text_rename_after.setTextCursor(cursor)
            elif event.key() == Qt.Key_End:
                cursor.setPosition(len(self.text_rename_after.toPlainText()))
                self.text_rename_after.setTextCursor(cursor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Up:
                self.text_rename_after.moveCursor(QTextCursor.Up, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Down:
                self.text_rename_after.moveCursor(QTextCursor.Down, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Left:
                self.text_rename_after.moveCursor(QTextCursor.Left, QTextCursor.KeepAnchor)
            elif event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Right:
                self.text_rename_after.moveCursor(QTextCursor.Right, QTextCursor.KeepAnchor)
            elif event.key() == Qt.Key_Up:
                self.text_rename_after.moveCursor(QTextCursor.Up)
            elif event.key() == Qt.Key_Down:
                self.text_rename_after.moveCursor(QTextCursor.Down)
            elif event.key() == Qt.Key_Left:
                self.text_rename_after.moveCursor(QTextCursor.Left)
            elif event.key() == Qt.Key_Right:
                self.text_rename_after.moveCursor(QTextCursor.Right)
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_A:
                self.text_rename_after.selectAll()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Z:
                self.text_rename_after.undo()
            elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Y:
                self.text_rename_after.redo()
            elif event.key() == Qt.Key_Escape:
                self.window_rep.hide()
            elif event.key() == Qt.Key_Enter or event.key() == Qt.Key_Return:
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
                    all_txt = global_active_textcomponent.toHtml()
                    rep_array = re.findall('>.*?<',all_txt)
                    temp_array = []
                    for item in rep_array:
                        if ' ' in item:
                            rep_item = item.replace(' ','')
                            temp_array.append(f'{item}_{rep_item}')
                    for item in temp_array:
                        before_txt = item.split('<_>')[0] +'<'
                        end_txt = '>'+item.split('<_>')[1]
                        all_txt = all_txt.replace(before_txt, end_txt)
                    global_active_textcomponent.setHtml(all_txt)
                elif end_txt != before_txt:
                    all_txt = global_active_textcomponent.toHtml()
                    all_txt = all_txt.replace(before_txt, end_txt)
                    global_active_textcomponent.setHtml(all_txt)
                self.window_rep.hide()
                self.on_lineheight_changed()
            else:
                cursor.insertText(chr(event.key()))
        except Exception as e:
            pass
            # print('Error 301',e)  
        
    def fn_rep_mouserelease(self,event): # 左键 叠加 右键 替换
        cursor = self.text_rename_history.textCursor()
        txt_temp = cursor.block().text().strip('> \n\u2029').split('=>')
        try:
            txt_1 = txt_temp[0]
        except:
            txt_1 = ''
        try:
            txt_2 = txt_temp[1]
        except:
            txt_2 = ''
        self.text_rename_before.setPlainText(txt_1.strip(' ='))
        self.text_rename_after.setPlainText(txt_2.strip(' '))
        self.text_rename_after.setFocus()
    def fn_windowshow_focusout(self,e):
        try:
            self.window_show.close()
        except:
            pass

    def fn_show_window_keywords(self): # 关键词补全
        self.word_array = ''
        self.word_array, self.ori_array = [], []
        self.window_show = QWidget()
        self.layout_windowshow = QGridLayout(self.window_show)
        self.window_show.move(self.pos().x() + self.width() - 190,self.pos().y() + 100)
        self.window_show.setFixedSize(150, 80)
        self.window_show.setWindowTitle("联想输入")
        self.window_show.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_show.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) # 隐藏标题栏

        self.text_windowshow = QLineEdit()
        self.text_windowshow.setMaximumWidth(150)
        self.text_windowshow.setMaximumHeight(40)
        self.text_windowshow.focusOutEvent = self.fn_windowshow_focusout
        self.text_windowshow.keyPressEvent = self.fn_windowshow_keypressevent_keywords
        # self.text_windowshow.textChanged.connect(self.image_keywords)

        self.label_windowshow = QLabel()
        self.label_windowshow.setStyleSheet('border:none')
        self.label_windowshow.setMaximumWidth(150)
        self.label_windowshow.setMaximumHeight(40)

        self.layout_windowshow.addWidget(self.text_windowshow,0,0)
        self.layout_windowshow.addWidget(self.label_windowshow,1,0)

        self.word_array = self.text_genword.toPlainText().replace('\n','\u2029').strip('\u2029\r ').split('\u2029')
        self.word_array = list(set(self.word_array))
        self.image_keywords()
        # cursor = global_active_textcomponent.textCursor()
        # cursor.movePosition(QTextCursor.Left, 2)
        # cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(self.ori_keywords)-1)
        # cursor.deleteChar()
        # cursor.insertText(self.out_keywords)
        # self.total_key = ''
        # self.word_array = ''
        # self.out_keywords = ''
        # self.ori_keywords = ''
    def image_keywords(self):
        for _ in self.word_array:
            if len(_) >= 5:
                for i in range(0,5):
                    tmp_length = len(self.total_key[i:])
                    if self.total_key[i:] and self.total_key[i:] == _[0:tmp_length]:
                        self.ori_keywords = self.total_key[i:]
                        self.out_keywords = _
                        self.text_windowshow.insert(self.total_key[i:])
                        self.label_windowshow.setText(f'{_}')
                        self.window_show.show()
                        return
            else:
                for i in range(0,len(_)):
                    tmp_length = len(self.total_key[i:])
                    if self.total_key[i:] and self.total_key[i:] == _[0:tmp_length]:
                        self.ori_keywords = self.total_key[i:]
                        self.out_keywords = _
                        self.text_windowshow.insert(self.total_key[i:])
                        self.label_windowshow.setText(f'{_}')
                        self.window_show.show()
                        return
    def fn_show_window(self): # 附图标记补全
        self.word_array = ''
        txt = ''
        self.word_array, self.ori_array = [], []
        self.window_show = QWidget()
        self.layout_windowshow = QGridLayout(self.window_show)
        self.window_show.move(self.pos().x() + self.width() - 190,self.pos().y() + 100)
        self.window_show.setFixedSize(150, 80)
        self.window_show.setWindowTitle("联想输入")
        self.window_show.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.window_show.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) # 隐藏标题栏

        self.text_windowshow = QLineEdit()
        self.text_windowshow.setMaximumWidth(150)
        self.text_windowshow.setMaximumHeight(40)
        self.text_windowshow.focusOutEvent = self.fn_windowshow_focusout
        self.text_windowshow.keyPressEvent = self.fn_windowshow_keypressevent
        self.text_windowshow.textChanged.connect(self.fn_windowshow_onchange)

        self.label_windowshow = QLabel()
        self.label_windowshow.setStyleSheet('border:none')
        self.label_windowshow.setMaximumWidth(150)
        self.label_windowshow.setMaximumHeight(40)

        self.layout_windowshow.addWidget(self.text_windowshow,0,0)
        self.layout_windowshow.addWidget(self.label_windowshow,1,0)

        for _ in reversed(list(self.total_key)):
            if _ in '1234567890abcde':
                txt += _
            else:
                break
        self.text_windowshow.insert(txt[::-1])
        self.image_marks(self.text_windowshow.text(), self.fig_dic)
        if self.word_array:
            self.label_windowshow.setText(f'{self.ori_array[0]} {self.word_array[0]}')
        self.window_show.show()
    def image_marks(self, inputtxt, fig_dic):
        self.word_array, self.ori_array = [], []
        for key in fig_dic:  # 判断附图标记
            if len(self.word_array) >= 5:
                break
            if inputtxt[-5:] == key[0] and len(inputtxt) == 5:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-5:])
                break
            elif inputtxt[-4:] == key[0] and len(inputtxt) >= 4:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-4:])
                break
            elif inputtxt[-3:] == key[0] and len(inputtxt) >= 3:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-3:])
                break
            elif inputtxt[-2:] == key[0] and len(inputtxt) >= 2:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-2:])
                break
            elif inputtxt[-1:] == key[0] and len(inputtxt) >= 1:
                self.word_array.append(key[1])
                self.ori_array.append(inputtxt[-1:])

    def fn_windowshow_onchange(self,txt):
        global global_active_textcomponent,global_active_figmark
        try:
            # if txt[-1] in list('~·、，；。！：“”’‘@#￥$%……^&*()（）【】[]？《》<>'):
            if txt[-1] not in '1234567890abcdefg':
                self.window_show.hide()
                cursor = global_active_textcomponent.textCursor()
                cursor.insertText(txt[-1])
        except:
            pass
    def fn_windowshow_keypressevent_keywords(self,event):
        global global_active_textcomponent,global_active_figmark
        self.get_totalkeys()
        if event.key() == Qt.Key_Backspace:
            cursor = global_active_textcomponent.textCursor()
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor,1)
            cursor.deleteChar()
            current_text = self.text_windowshow.text()
            new_text = current_text[:-1]
            self.text_windowshow.clear()
            self.text_windowshow.insert(new_text)
        elif event.key() == 32:# 32代表空格
            cursor = global_active_textcomponent.textCursor()
            cursor.movePosition(QTextCursor.Left, 2)
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(self.ori_keywords)-1)
            cursor.deleteChar()
            cursor.insertText(self.out_keywords)
            self.total_key = ''
            self.word_array = ''
            self.out_keywords = ''
            self.ori_keywords = ''
            if self.window_show:self.window_show.close()
        else:
            self.window_show.hide()
    def fn_windowshow_keypressevent(self,event):
        global global_active_textcomponent,global_active_figmark
        self.get_totalkeys()
        # if event.key() == Qt.Key_Escape:
        #     self.window_show.hide()
        if event.key() == Qt.Key_Backspace:
            cursor = global_active_textcomponent.textCursor()
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor,1)
            cursor.deleteChar()
            current_text = self.text_windowshow.text()
            new_text = current_text[:-1]
            self.text_windowshow.clear()
            self.text_windowshow.insert(new_text)

            if not self.text_windowshow.text():
                self.window_show.hide()
            else:
                self.image_marks(self.text_windowshow.text(), self.fig_dic)
                if self.word_array:
                    self.label_windowshow.setText(f'{self.ori_array[0]} {self.word_array[0]}')
        elif event.key() == 32:# 32代表空格
            self.image_marks(self.total_key, self.fig_dic)
            if not self.word_array:
                return
            self.space_out_words()
        elif event.text() in '1234567890abcdefg':
            cursor = global_active_textcomponent.textCursor()
            try:
                cursor.insertText(event.text())
                self.text_windowshow.insert(event.text())
            except:
                pass
            self.image_marks(self.text_windowshow.text(), self.fig_dic)
            if self.word_array:
                self.label_windowshow.setText(f'{self.ori_array[0]} {self.word_array[0]}')
        else:
            self.window_show.hide()
            
    def space_out_words(self):
        global global_active_textcomponent,global_active_figmark,write_auto
        insert_word = self.word_array[0]
        self.type_v = self.combo_typev.currentText() # 选择 '(Num)', '（Num）', '[Num]', 'Num','Void'
        for key in self.fig_dic:
            if insert_word == key[1]:
                if self.type_v == '(Num)':
                    all_word = f'{insert_word}({key[0]})'
                elif self.type_v == '（Num）':
                    all_word = f'{insert_word}（{key[0]}）'
                elif self.type_v ==  '[Num]':
                    all_word = f'{insert_word}[{key[0]}]'
                elif self.type_v == 'Num':
                    all_word = f'{insert_word}{key[0]}'
                else:
                    all_word = f'{insert_word}'
                all_word = all_word.replace(' ','')
                # 手动补全
                cursor = global_active_textcomponent.textCursor()
                if write_auto == '补全':
                    cursor.movePosition(QTextCursor.Left, 2)
                    cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(key[0]))
                elif write_auto == '关闭':
                    cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(key[0]))
                cursor.deleteChar()
                cursor.insertText(all_word)
                self.total_key = ''
                self.word_array = ''
                if self.window_show:self.window_show.close()
                break
class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        global window_main
        self.dragging = False
        self.in_widget = window_main
        txt_read = open('login.txt', 'r', encoding='utf-8').read()
        self.user_login = ''
        self.user_password = ''
        self.user_superkey = ''
        try:
            self.user_login = txt_read.split('\n')[0].split('=')[-1]
            self.user_password = txt_read.split('\n')[1].split('=')[-1]
            self.user_superkey = txt_read.split('\n')[2].split('=')[-1]
        except:
            self.user_login = ''
            self.user_password = ''
        self.closeEvent = self.closeEvent
        self.login_ui()
            
    def closeEvent(self,event):
        self.close()
        if self.in_widget:self.in_widget.close()

    def login_ui(self):
        self.status_wait = False
        self.user_level = ''
        self.fig_txt_array_temp = []
        self.main_login_layout = QGridLayout(self)
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.setWindowTitle(f"FENRIR ver{version}")
        self.setWindowFlags(Qt.FramelessWindowHint) # 隐藏标题栏
        # logo
        self.label_logo = QLabel()
        self.label_logo.setToolTip('点击')
        self.label_logo.setMaximumHeight(300)
        self.label_logo.setScaledContents(True)
        self.label_logo.mousePressEvent = self.change_pic

        self.change_pic(self.event)
        # 获取窗口坐标系
        screen = QDesktopWidget().screenGeometry()
        size = self.geometry()
        self.setFixedSize(350, 420)
        self.move(int((screen.width() - size.width()) / 2)+150, int((screen.height() - size.height()) / 2))
        self.mousePressEvent = self.start_drag
        self.mouseReleaseEvent = self.window_pressrelease
        self.closeEvent = self.closeEvent

        self.text_user = QLineEdit()
        self.text_user.setPlaceholderText('用户名')
        self.text_user.setMaximumHeight(30)
        self.text_user.setMinimumWidth(300)
        self.text_user.insert(self.user_login)

        self.text_password = QLineEdit()
        self.text_password.setPlaceholderText('密码')
        self.text_password.setMaximumHeight(30)
        self.text_password.setMinimumWidth(300)
        self.text_password.insert(self.user_password)
        self.text_password.setEchoMode(QLineEdit.Password)

        self.bt_login = QPushButton(QIcon(qta.icon('fa5b.wolf-pack-battalion')),'')
        self.bt_login.setIconSize(QSize(40, 40))
        self.bt_login.setMaximumHeight(40)
        self.bt_login.setToolTip('账号注册请访问 http://www.fenrir.fun/register')
        self.bt_login.clicked.connect(self.fn_login)
        
        self.label_login_status = QLabel()
        self.label_login_status.setStyleSheet("color : red")

        self.main_login_layout.addWidget(self.label_logo,0,0,2,2)
        self.main_login_layout.addWidget(self.text_user,5,0,1,2)
        self.main_login_layout.addWidget(self.text_password,6,0,1,2)
        self.main_login_layout.addWidget(self.bt_login,7,0,1,2)
        
        self.show()
    def window_pressrelease(self,event):
        self.dragging = False
    def start_drag(self, event):
        self.dragging = True
        self.old_pos = event.globalPos()
    def mouseMoveEvent(self, event):
        if self.dragging:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()
            self.move(QCursor().pos().x() - 150,QCursor().pos().y() - 150)
        
    def change_pic(self,event):
        self.old_pos = self.pos()
        self.dragging = True
        index = int(random.randint(1,6))
        self.movie = QMovie("./ui/%02d.gif" % index)
        self.label_logo.setMovie(self.movie)
        self.movie.start()
    def fn_login(self):
        user = self.text_user.text()
        password = self.text_password.text()
        if not user:
            self.main_login_layout.addWidget(self.label_login_status,0,0,1,1)
            self.label_login_status.setText('请输入用户名')
            return
        elif not password:
            self.main_login_layout.addWidget(self.label_login_status,0,0,1,1)
            self.label_login_status.setText('请输入密码')
            return
        else:
            self.label_login_status.setText('')
            data = {"username": user,
                    "password": password,
                    }
            try:
                response = requests.post('http://www.fenrir.fun/postlogin', data=data)
            except:
                QMessageBox.critical(self, "连接失败", "服务器连接失败，请联系管理员")
                return
            json_data = json.loads(response.text)
            if json_data['Status'] == 'OK':
                txt_write = open('login.txt', 'r', encoding='utf-8').read().replace(open('login.txt', 'r', encoding='utf-8').read().split('\n')[0], '[user]=' + user).replace(open('login.txt', 'r', encoding='utf-8').read().split('\n')[1], '[password]=' + password)
                open('login.txt', 'w+', encoding='utf-8').write(txt_write)
                self.close()
                self.in_widget.show()
                self.setWindowTitle(f"FENRIR ver{version} | {user}")
                self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
            else:
                self.main_login_layout.addWidget(self.label_login_status,0,0,1,1)
                self.label_login_status.setText('用户名或密码错误，请重试！')

class WindowBook(QWidget):
    def __init__(self,active_figmark,active_textcomponent,status,dock_mark):
        global global_active_textcomponent,global_active_figmark
        super().__init__()
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.setWindowTitle('文本校验')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint) # 隐藏标题栏
        self.setFixedWidth(500)
        self.move(1700, 100)
        global_active_figmark = active_figmark
        global_active_textcomponent = active_textcomponent
        self.status = status
        self.dock_mark = dock_mark
        self.highlight_color = '#4a76d6'
        self.font_size_trans = 10
        self.result_json = ()
        self.response_array = []
        self.des_part_count = 0
        self.url_ai = open('./data/url_token.txt','r').read()
        self.layout_windowbook = QGridLayout(self)
        self.layout_windowbook.setContentsMargins(0,0,0,0)

        self.tab_widget_book = QTabWidget()

        # tab_1 校验文本
        self.framewidget_1()

        self.layout_windowbook.addWidget(self.tab_widget_book,0,0,1,2)
        # self.layout_windowbook.addWidget(self.bt_close,1,1,1,1)


    def framewidget_1(self): # 校验文本
        main_widget = QWidget()
        main_layout = QGridLayout(main_widget)

        self.table_marks = QTableWidget()
        self.table_marks.setMinimumWidth(300)
        self.table_marks.setMinimumHeight(400)
        self.table_marks.setRowCount(300) 
        self.table_marks.setColumnCount(4)
        self.table_marks.setHorizontalHeaderLabels(["标号","名称","标号数","名称数"])
        self.table_marks.setVerticalHeaderLabels(('%02d' % _) for _ in range(1,300))
        self.table_marks.setColumnWidth(0,60) 
        self.table_marks.setColumnWidth(1,145) 
        self.table_marks.setColumnWidth(2,50) 
        self.table_marks.setColumnWidth(3,50) 
        self.table_marks.itemClicked.connect(self.cell_clicked)

        self.text_checkresult = QTextBrowser()
        self.text_checkresult.setFont(QFont("宋体", 11))
        self.text_checkresult.setPlaceholderText('> 请选择待校验的文档\n***无需在此处粘贴任何文本***\n***附图标记不能为空***\n> 校验说明书\n请以“技术领域、背景技术、发明内容/实用新型内容、附图说明、具体实施方式”分段\n> 校验权利要求书\n***每项权利要求尽量撰写在一段中***\n***最多支持50项权利要求***')
        self.text_checkresult.mouseReleaseEvent = self.fn_highlight_figmarks_2
        self.text_checkresult.setMinimumWidth(300)

        bt_check = QPushButton('全文校验')
        bt_check.setFixedSize(90,30)
        bt_check.setCheckable(True)
        bt_check.setStyleSheet('QPushButton {background-color: #e55f00 ; color:white} QPushButton:hover {background-color: #f69958}')
        bt_check.clicked.connect(self.submit_check_main)

        bt_aicheck = QPushButton('AI校验')
        bt_aicheck.setFixedSize(90,30)
        bt_aicheck.setCheckable(True)
        bt_aicheck.setStyleSheet('QPushButton {background-color: #e55f00 ; color:white} QPushButton:hover {background-color: #f69958}')
        bt_aicheck.clicked.connect(self.submit_aicheck)

        bt_close = QPushButton('关闭')
        bt_close.setFixedSize(90,30)
        bt_close.clicked.connect(self.fn_close_book)

        self.check_claimtree = QCheckBox('权利要求树')
        self.check_claimtree.setFixedSize(90,30)
        self.check_claimtree.setChecked(True)

        main_layout.addWidget(self.table_marks,0,0,8,8)
        main_layout.addWidget(self.text_checkresult,8,0,3,8)

        main_layout.addWidget(self.check_claimtree,0,8,1,2)
        main_layout.addWidget(bt_check,2,8,1,2)
        main_layout.addWidget(bt_aicheck,3,8,1,2)
        main_layout.addWidget(bt_close,6,8,1,2)
        
        self.tab_widget_book.addTab(main_widget, '文本校验')
    def fn_close_book(self):
        self.close()
        self.dock_mark.setMinimumWidth(50)
        self.dock_mark.setMaximumWidth(1000)
    
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

        
    def fn_highlight_figmarks_2(self,event):
        select_txt = self.text_checkresult.textCursor().selectedText()
        if select_txt:
            self.reset_textcomponentformat()
            self.get_same_markindex(select_txt,global_active_textcomponent,self.highlight_color)
    def get_same_markindex(self,mark,input_component,highlight_color):
        if mark == '.' or not mark:
            return
        try:
            mark = mark.replace('\u2029','\n').replace('{','\{').replace('}','\}').replace('(','\(').replace(')','\)').replace('[','\[').replace(']','\]')
            all_txt = input_component.toPlainText().replace('\u2029','\n')#.replace('{','\{').replace('}','\}').replace('(','\(').replace(')','\)')
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
                bracket_count = len(re.findall('\(|\)|\{|\}|\[|\]',mark))
                if index - len(mark) < 0:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark))
                else:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark) - bracket_count)
                cursor.mergeCharFormat(format)  # 改变文本的背景颜色
            # input_component.setTextCursor(cursor) # 定位至标记位置
        except:
            pass
    
    def fn_animation(self,widget,start,end):
        self.animation = QPropertyAnimation(widget, b"windowOpacity")
        self.animation.setDuration(400)  # 动画持续时间（毫秒）
        # 淡入效果
        self.animation.setStartValue(start)  # 起始透明度为 0（完全透明）
        self.animation.setEndValue(end)  # 结束透明度为 1（完全不透明）

    def get_same_markindex_check(self,mark,text_component):
        if mark == '.':
            return
        try:
            all_txt = text_component.document().toPlainText()
            re_search = QRegExp(mark)
            matches = re.finditer(re_search.pattern(), all_txt)
            format = QTextCharFormat()
            format.setBackground(QColor('red'))
            # 循环查找文档
            match_num = 0
            for match in matches:
                match_num += 1
                index = match.start()
                cursor = text_component.textCursor()
                cursor.setPosition(index)
                if '\(' in mark:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark)-2)
                else:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(mark))
                # text_component.setFocus()
                cursor.mergeCharFormat(format)  # 改变文本的背景颜色
        except:
            pass
    def submit_aicheck(self):
        self.status.showMessage('文本校验中，请稍后...')
        self.status.setStyleSheet("QStatusBar {background-color: #cc6633;color: white;border:none} QStatusBar:hover{background-color:#d2794c;color: white}")
        # self.setCursor(Qt.WaitCursor)

        all_txt = global_active_textcomponent.toPlainText()
        global model_api
        if model_api == 'Doubao':
            if '尊敬的审查员' in all_txt:
                self.aicheck_thread = Worker_ai_doubao('你是一个经验丰富的专利代理人，请根据下文的审查意见答复提出修改建议，以提高授权率：' + all_txt,self.text_checkresult)        
            else:
                self.aicheck_thread = Worker_ai_doubao('你是一个经验丰富的专利代理人，请检查以下专利文本中的撰写缺陷，例如错别字，语法错误，附图标记不一致等，并提出改进建议：' + all_txt,self.text_checkresult)
        else:
            if '尊敬的审查员' in all_txt:
                self.aicheck_thread = Worker_ai_deepseek('你是一个经验丰富的专利代理人，请根据下文的审查意见答复提出修改建议，以提高授权率：' + all_txt,self.text_checkresult)        
            else:
                self.aicheck_thread = Worker_ai_deepseek('你是一个经验丰富的专利代理人，请检查以下专利文本中的撰写缺陷，例如错别字，语法错误，附图标记不一致等，并提出改进建议：' + all_txt,self.text_checkresult)

        self.aicheck_thread.progress.connect(self.fn_aicheck)
        self.aicheck_thread.start()
    def fn_aicheck(self,in_txt):
        # self.text_checkresult.insertPlainText(in_txt)
        self.status.showMessage('校验完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
    def reset_textcomponentformat(self):
        format = QTextCharFormat()
        format.setBackground(QColor(Qt.transparent))
        cursor = global_active_textcomponent.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(global_active_textcomponent.toPlainText()))
        cursor.mergeCharFormat(format)
    def cell_clicked(self,item):
        row,column = item.row(),item.column()
        self.reset_textcomponentformat()
        if column == 0:
            select_txt = self.table_marks.item(row, 0).text()
            self.get_same_markindex(select_txt,global_active_textcomponent,self.highlight_color)
        elif column in [1,2,3]:
            select_txt = self.table_marks.item(row, 1).text()
            self.get_same_markindex(select_txt,global_active_textcomponent,self.highlight_color)
    def submit_check_main(self):
        global global_active_textcomponent,global_active_figmark
        # 参数初始化
        self.textsplit_array = []
        self.dataframe_list = [] # 输出dataframe结果
        self.error_array = []
        self.ckresult_txt = '' # 输出txt结果
        self.splittemp_array = ['技术领域','背景技术','发明内容','实用新型内容','附图说明','具体实施方式'] # 用于判断说明书分段标题
        self.paras_array = {'专利名称':'','技术领域':'','背景技术':'','发明内容':'','实用新型内容':'','附图说明':'','具体实施方式':''}
        self.err_details = [] # 错别字明细
        self.one_cite_muti_dic = {} # 多引多
        self.one_cite_one_dic = {} # 单引单
        self.claim_array = []
        self.claim_dic = {} #序号:[权利要求，前序，特征]
        self.title = ''
        self.claim_max = 1
        self.claim_check_flag = True
        self.des_check_flag = True
        self.txt_type = 'other'
        self.marks_dic = {}
        self.parts_dic = {} # 获取权利要求序号,引用权要,特征列表
        self.fig_dic = {}
       # 获取校验文本与附图标记
        self.all_txt = global_active_textcomponent.toPlainText().replace(' ','').replace('\r','\u2029').replace('\t','\u2029').replace('\n','\u2029').replace('\u2029\u2029','\u2029').strip('\u2029')
        self.para_array = self.all_txt.split('\u2029')
        self.marks_array = global_active_figmark.toPlainText().replace('\n','\u2029').strip('\u2029').split('\u2029')
        self.figmarks_array = split_marks('\u2029'.join(self.marks_array))
        self.status.showMessage('文本校验中...')
        self.status.setStyleSheet("QStatusBar {background-color: #cc6633;color: white;border:none} QStatusBar:hover{background-color:#d2794c;color: white}")
        # self.setCursor(Qt.WaitCursor)
        self.text_checkresult.clear()
        if not global_active_figmark.toPlainText().strip('\n\u2029 '):
            self.text_checkresult.insertPlainText('\n> 未识别到附图标记，请在左侧填入附图标记后重试')
        else:
            while '\u2029\u2029' in self.all_txt:
                self.all_txt = self.all_txt.replace('\u2029\u2029','\u2029')
            # 判断是否为说明书
            self.txt_type = self.is_description()
            
            if self.txt_type =='claim': # 正常校验权利要求书  多项权利要求
                self.check_claim()
            elif self.txt_type =='short_for_description': # 说明书分段有问题
                self.check_text_ckmarks_unused()
            elif self.txt_type =='description':# 正常校验说明书
                self.check_description()
            elif self.txt_type =='other':
                self.check_text_ckmarks_unused()
            
            self.marks_consistent() # 附图标记一致性
            self.marks_to_table() # 将校验结果反应在表格中
            self.get_score_from_list() # 结论
            self.add_num_to_data() # 为dataframe编号列赋值
            self.text_checkresult.insertPlainText(self.ckresult_txt)
        if self.txt_type =='description' and self.des_check_flag:
            self.status.showMessage('正在给出进一步撰写建议，请稍后...')
            self.ai_suggestion() # 修改建议
        else:
            self.status.showMessage('校验完成')
            self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
            self.setCursor(Qt.ArrowCursor)
            
    def marks_to_table(self):
        self.table_marks.clearContents()
        for index,num in enumerate(self.fig_dic):
            mark = self.fig_dic[num]
            mark_count = re.findall(mark,self.all_txt)
            num_count = re.findall(f'{mark}{num}',self.all_txt)  + re.findall(f'\({num}\)',self.all_txt.replace('（','(').replace('）',')'))
            item_1 = QTableWidgetItem(num)
            item_2 = QTableWidgetItem(mark)
            item_3 = QTableWidgetItem(str(len(num_count)))
            item_4 = QTableWidgetItem(str(len(mark_count)))
            if len(mark_count) != len(num_count):
                item_1.setBackground(QColor('#e20000'))
                item_1.setForeground(Qt.white)
                item_2.setBackground(QColor('#e20000'))
                item_2.setForeground(Qt.white)
            if len(num_count) == 0:
                item_3.setBackground(QColor('#e55f00'))
                item_3.setForeground(Qt.white)
            if len(mark_count) == 0:
                item_4.setBackground(QColor('#e55f00'))
                item_4.setForeground(Qt.white)
            self.table_marks.setItem(index, 0, item_1)
            self.table_marks.setItem(index, 1, item_2)
            self.table_marks.setItem(index, 2, item_3)
            self.table_marks.setItem(index, 3, item_4)
    def ai_suggestion(self):
        global model_api
        
        self.status.showMessage('校验完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
    def fn_ai_suggestion(self,in_txt):
        self.ckresult_txt += f'\u2029=======<撰写建议>=======\u2029{in_txt}\u2029'
        # self.text_checkresult.insertPlainText(self.ckresult_txt)
        self.status.showMessage('校验完成')
        self.status.setStyleSheet("QStatusBar {background-color: #455364;color: white;border:none} QStatusBar:hover{background-color:#54687a;color: white}")
        self.setCursor(Qt.ArrowCursor)
    ''' 技术特征 & 附图编号一致性'''
    def marks_consistent(self):
        self.ckresult_txt += f'\u2029<附图标记一致性>\u2029'
        if not self.marks_array:
            return
        # 提取附图标记和标记名称
        if self.marks_array[2][0] in '1234567890':
            for item in self.marks_array:
                self.marks_dic[item.split(' ')[1]] = item.split(' ')[0] # {'1':'壳体'}
        # 查找附图标记
        for mark in self.marks_dic:
            for num in [r'\d{4}[a-z]',r'\d{3}[a-z]',r'\d{4}',r'\d{2}[a-z]',r'\d{3}',r'\d{2}',r'\d[a-z]',r'\d{1}',r'[a-z]']:
                find_txt = []
                if self.txt_type == 'claim': # 被核对文本为权利要求书   仅含独权？
                    find_txt = re.findall(f'{mark}\({num}\)',self.all_txt.replace('（','(').replace('）',')'))
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
        # 不含有附图标记
        if self.marks_array[2][0] not in '1234567890':
            for char in self.marks_array:
                # 排除字符长度为1的关键词
                if len(char) <= 2:
                    continue
                re_search_array = []
                find_char = []
                for i in range(0,len(char)):
                    if i == 0:
                        item = '.' + char[1:]
                    elif i == len(char) - 1:
                        item = char[0:i] + '.'
                    else:
                        item = char[0:i] + '.' + char[i:]
                    re_search_array.append(item)
                for _ in re_search_array:
                    find_char += re.findall(_,self.all_txt)
                # 剔除标点符号
                for i in range(0,len(find_char)):
                    item = find_char[i]
                    item = item.strip('。,、;:() ')
                    if len(item) != len(char) or item == char:
                        find_char[i] = ''
                find_char = refine_array(find_char,'set')
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
                        self.get_same_markindex_check(error,global_active_textcomponent)

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
                # if self.all_txt[0:4] == '技术领域':
                #     self.ckresult_txt += '请输入说明书名称\u2029'
                self.ckresult_txt += '请以技术领域、背景技术、发明内容/实用新型内容、附图说明（可不填）、具体实施方式划分说明书\u2029'
                return 'short_for_description'
            elif ('1.一种' in self.all_txt.replace(' ','') or '1、一种' in self.all_txt.replace(' ','') or '权利要求' in self.all_txt) and '实施例' not in self.all_txt:
                self.ckresult_txt += '=======文本为<权利要求书>=======\u2029'
                return 'claim'
        elif self.des_part_count >= 4 and ('1.一种' in self.all_txt.replace(' ','') or '1、一种' in self.all_txt.replace(' ','')):
            self.ckresult_txt += '=======文本为<其他文本>=======\u2029'
            return 'other'
        elif self.des_part_count >= 4:
            self.ckresult_txt += '=======文本为<说明书>=======\u2029'
            return 'description'
        
    def check_text_ckmarks_unused(self): # 校验未被使用的附图标记
        self.ckresult_txt += '\u2029<未使用的附图标记>\u2029'
        if not self.marks_array:
            self.ckresult_txt += '无附图标记\u2029'
        for _ in self.figmarks_array:
            fig_num,fig_text = judge_mark(_)
            self.fig_dic[fig_num] = fig_text
        for _ in self.fig_dic:
            item = self.fig_dic[_]
            if item not in self.all_txt:
                self.ckresult_txt += f'标记<{_} {item}>未使用\u2029'
                self.dataframe_list.append(['','标记未用','N/A',f'标记<{_} {item}>未用','0'])
    def add_num_to_data(self): # 更新 data_list序号
        for index in range(0,len(self.dataframe_list)):
            self.dataframe_list[index][0] = index + 1
    def get_score_from_list(self): # 统计同分数
        total_score = 100
        for data_array in self.dataframe_list:
            total_score += int(data_array[4])
        self.ckresult_txt += f'\u2029<结果>\u2029得分：<{total_score}/100>\u2029'
        if total_score <= 60:
            self.ckresult_txt += f'\u2029技术方案细节过于单薄，请进一步完善'

    def get_errors(self,corrected_text, origin_text):
        for i, ori_char in enumerate(origin_text):
            try:
                if ori_char in [' ', '“', '”', '‘', '’', '琊', '\u2029', '…', '—', '擤']:
                    # add unk word
                    corrected_text = corrected_text[:i] + ori_char + corrected_text[i:]
                    continue
                if i >= len(corrected_text):
                    continue
                if ori_char != corrected_text[i]:
                    if ori_char.lower() == corrected_text[i]:
                        # pass english upper char
                        corrected_text = corrected_text[:i] + ori_char + corrected_text[i + 1:]
                        continue
                    self.err_details.append((ori_char, corrected_text[i], i, i + 1))
            except:
                pass
        self.err_details = sorted(self.err_details, key=operator.itemgetter(2))

    ''' 校验说明书 '''
    def get_para_sen_index(self,error,para_txt):  # 判断错误位于说明书的第几段第几句
        # 判断段落号
        para_index = re.findall('\[\d\d\d\d\]',para_txt)
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
                if self.paras_array['专利名称'].replace('一种','') not in des_part:
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
                destination_txt = des_part_array[0]
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
                                if len(_) <= 5 and _ not in des_part:
                                    para_index,sen_index = self.get_para_sen_index(_,destination_txt)
                                    self.ckresult_txt += f'<有益效果>第{para_index}段缺少与<{_}>对应的内容\u2029'
                                    self.dataframe_list.append(['','形式缺陷','有益效果',f'第{para_index}段缺少与<{_}>对应的内容','-10'])
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
                                if len(_) <= 5 and _ not in des_part:
                                    para_index,sen_index = self.get_para_sen_index(_,destination_txt)
                                    self.ckresult_txt += f'<技术问题>第{para_index}段缺少与<{_}>对应的内容\u2029'
                                    self.dataframe_list.append(['','形式缺陷','技术问题',f'第{para_index}段缺少与<{_}>对应的内容','-10'])
                        break
                if self.paras_array['专利名称'].replace('一种','') not in des_part:
                    self.ckresult_txt += '<发明内容>主题名称不一致\u2029'
                    self.dataframe_list.append(['','形式缺陷','发明内容','主题名称不一致','-2'])
            elif para_title == '具体实施方式': # 未将发明内容与具体实施方式比对
                # 校验附图说明中的附图数量与具体实施方式中是否一致，如果无附图说明则PASS
                if self.paras_array['附图说明']:
                    for fig_max in range(50,1,-1):
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
        self.all_txt = '\u2029' + self.all_txt + '\u2029'
        split_array = [f'\u2029{i}\.' for i in range(50,0,-1)] + [f'\u2029{i}、' for i in range(50,0,-1)]# +  [f'\u2029{i}' for i in range(50,0,-1)]
        self.claim_array = re.split('|'.join(split_array),self.all_txt)
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
            if len(re.findall('。',claim)) >= 2: # 校验多个句号
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
            if f'{claim_index}、{claim}' in self.all_txt or f'{claim_index}.{claim}' not in self.all_txt: # 校验序号
                self.ckresult_txt += f'权利要求<{claim_index}>序号错误\u2029'
                self.dataframe_list.append(['','序号',f'权{claim_index}','序号错误','-10'])
                self.claim_check_flag = False 
        # 生成claim_dic{[1：全文，前序，特征]，[2:全文，前序，特征]}
        for index,claim in enumerate(self.claim_array):
            index += 1
            self.claim_dic[index] = [claim.strip('\u2029\n '),'',''] # claim全文，前序部分，特征部分
        return self.claim_check_flag
    def check_uncertain_words(self):# 校验不确定用语
        self.ckresult_txt += f'\u2029<主题词、不确定用语>\u2029'
        title = re.split('，|,',self.claim_array[0])[0].replace('一种','')
        for claim_index,claim in enumerate(self.claim_array):
            claim_index += 1
            claim = claim.replace(' ','')
            for word in ['厚','薄','强','弱','高温','高压','很宽','例如','最好','尤其','必要时','约','接近','等','类似物','可以','优选']:
                if word in claim:
                    self.ckresult_txt += f'权利要求<{claim_index}>存在不确定用语“{word}”\u2029'
                    self.dataframe_list.append(['','不确定用语',f'权{claim_index}','不确定用语','-5'])
            if title not in claim:
                self.ckresult_txt += f'权利要求<{claim_index}>主题名称不一致\u2029'
                self.dataframe_list.append(['','主题名称',f'权{claim_index}','主题名称不一致','-5'])
    def get_fore_char(self): # 获取前序部分、特征部分
        for index,claim in self.claim_dic.items():
            find_txt = []
            for _ in ['权力要求书(.*)其特征','权利要求书(.*)其特征','权力要求(.*)其特征','权利要求(.*)其特征','1\.(.*)其特征','、(.*)其特征']:# 获取前序部分
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
        if not self.check_preliminary():
            self.ckresult_txt += f'<请确认句号、划界词、序号无误后重试>\u2029'
            return
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

class Worker_ai_deepseek(QThread):
    progress = pyqtSignal(str)
    def __init__(self,in_txt,in_widget):
        super().__init__()
        self.result = ''
        self.in_txt = in_txt
        if not user:
            self.client = OpenAI(api_key="", base_url="https://api.deepseek.com")
        else:
            doubao_array = open('./data/deepseek_token.txt','r').read().split('\n')
            ak = doubao_array[0]
            self.client = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
        self.text_out = in_widget
    def run(self):
        self.result = self.deepseek_ai(self.in_txt)
        self.progress.emit(self.result)
    def out_txt_by_time(self):
        txt_array = self.reply.split('，')
        for index,word in enumerate(txt_array):
            if index == len(txt_array) -1:
                self.text_out.insertPlainText(word)
            else:
                self.text_out.insertPlainText(word + '，')
            time.sleep(random.uniform(0.05,0.2))
    def deepseek_ai(self,in_txt):
        global messages,deep_model
        try:
            if not in_txt:
                self.reply = ""
                return
            if user and not open('./data/deepseek_token.txt','r').read():
                return '请先在AI接口(F4)中输入deepseek的API Key'
            else:
                # if not messages:
                messages=[
                    {"role": "system", "content":"经验丰富的具有所有领域相关知识的专利代理人"},
                    {"role": "user", "content": in_txt},
                    ]
                # else:
                #     messages.append({"role": "user","content": in_txt})
                response = self.client.chat.completions.create(
                model = 'deepseek-chat', # deep_model
                messages = messages,
                stream=False
                )
                self.reply = response.choices[0].message.content
                # if deep_model != 'deepseek-chat':
                # messages = []
                # else:
                # if len(messages) >= 10:
                #     messages = [{"role": "user","content": in_txt},{"role": "system","content": self.reply},]
                # else:
                #     messages.append(response.choices[0].message)
                    
                if self.text_out:
                    self.out_txt_by_time()
            return self.reply
        except Exception as e:
            return f"错误代码101：API调用失败"
class Worker_ai_doubao(QThread):
    progress = pyqtSignal(str)
    def __init__(self,in_txt,in_widget):
        super().__init__()
        self.result = ''
        self.in_txt = in_txt
        if not user:
            self.client = Ark(ak="", sk="")
            self.model = ''
        else:
            doubao_array = open('./data/doubao_token.txt','r').read().split('\n')
            ak = doubao_array[0]
            sk = doubao_array[1]
            self.model = doubao_array[2]
            self.client = Ark(ak=ak, sk=sk)

        self.text_out = in_widget
    def run(self):
        self.result = self.doubao_ai(self.in_txt)
        self.progress.emit(self.result)
    def out_txt_by_time(self):
        txt_array = self.reply.split('，')
        for index,word in enumerate(txt_array):
            if index == len(txt_array) -1:
                self.text_out.insertPlainText(word)
            else:
                self.text_out.insertPlainText(word + '，')
            time.sleep(random.uniform(0.05,0.2))
    def doubao_ai(self,in_txt):
        global messages
        try:
            if not in_txt:
                self.reply = ""
                return
            messages =[{"role": "user","content": in_txt}]
                
            if user and len(open('./data/doubao_token.txt','r').read().split('\n')) != 3:
                return '请先在AI接口(F4)中输入doubao的ak & sk & model'
            else:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages)
                self.reply = completion.choices[0].message.content.strip('\n\r')
                # messages.append({"role": "assistant","content": self.reply})
                # if len(messages) >= 5:
                #     messages = [{"role": "user","content": in_txt},{"role": "assistant","content": self.reply},]
                # messages = []
                if self.text_out:
                    self.out_txt_by_time()
            return self.reply
        except Exception as e:
            return f"错误代码102：API调用失败"

class Worker_Ocr(QThread):
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
            pdf = pdfplumber.open(file_path)
            for page in pdf.pages:
                self.out_ocr_txt += page.extract_text()
        except Exception as e:
            print('> Error Code 701',e)
    def read_word_file(self,file_path):
        doc = docx.Document(file_path)
        text = []
        for paragraph in doc.paragraphs:
            text.append(paragraph.text)
        return '\n'.join(text)

class FileDropLabel(QLabel):
    def __init__(self,label_txt):
        super().__init__()
        self.setAcceptDrops(True)  # 设置控件接受拖放事件
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(50)
        self.setMinimumWidth(50)
        # self.setMaximumWidth(500)
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
        # else:
        #     img_rate = img_h/self.height()
        #     img_h = self.height()
        #     img_w = img_w/img_rate
        result = img.scaled(int(img_w),int(img_h),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        self.setPixmap(QPixmap.fromImage(result))
class SwitchBtn_1(QWidget):
    checkedChanged = pyqtSignal(bool)
    status_sig = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.edge = QColor(0, 0, 0)  # 边框颜色
        self.checked = False
        self.bgColorOff = QColor(255, 255, 255)  # 滑动条颜色
        self.bgColorOn = QColor(255, 255, 255)
        
        self.sliderColorOff = QRadialGradient(int(self.width() / 2), int(self.height() / 2), int(self.width() / 2), int(self.width() / 6),int(self.height() / 6))
        # 滑块颜色
        self.sliderColorOff.setColorAt(1, QColor('#e55f00')) # 开启状态
        # self.sliderColorOff.setColorAt(0.8, QColor(50, 100, 0))
        self.sliderColorOn = QRadialGradient(int(self.width() / 2), int(self.height() / 2), int(self.width() / 2), int(3 * self.width() / 4), int(self.height() / 2))
        self.sliderColorOn.setColorAt(1, QColor('#19232d')) # 关闭状态
        # self.sliderColorOn.setColorAt(0.8, QColor(255, 0, 0))
        self.textColorOff = QColor(0, 0, 0)  # 文本颜色
        self.textColorOn = QColor(0, 0, 0)
        self.textOff = "联想"  # 初始文本
        self.textOn = "关闭"
        self.space = 2
        self.rectRadius = 5
        self.step = self.width() / 50
        self.startX = 0
        self.endX = 0
        self.timer = QTimer(self)  # 初始化一个定时器
        self.timer.timeout.connect(self.updateValue)  # 计时结束调用operate()方法
        self.status_sig.connect(self.auto_step)
        # self.timer.start(5)  # 设置计时间隔并启动
    def isChecked(self):
        return self.checked
    def to_open(self):
        # 打开状态
        self.checked = True
        # self.auto_step()
        self.status_sig.emit()
    def to_close(self):
        # 关闭状态
        self.checked = False
        # self.auto_step()
        self.status_sig.emit()
    def auto_step(self):
        # 每次移动的步长为宽度的50分之一
        self.step = self.width() / 40
        # 状态切换改变后自动计算终点坐标
        if self.checked:
            self.endX = self.width() - self.height()
        else:
            self.endX = 0
        self.timer.start(5)
    def setInitText(self, text):
        self.textOff = text
    def setSecondText(self, text):
        self.textOn = text
    def updateValue(self):
        if self.checked:
            if self.startX < self.endX:
                self.startX = self.startX + self.step
            else:
                self.startX = self.endX
                self.timer.stop()
        else:
            if self.startX > self.endX:
                self.startX = self.startX - self.step
            else:
                self.startX = self.endX
                self.timer.stop()
        self.update()
    def mousePressEvent(self, event):
        global model_type
        self.checked = not self.checked
        # 发射信号
        self.checkedChanged.emit(self.checked)

        # 每次移动的步长为宽度的50分之一
        self.step = self.width() / 40
        # 状态切换改变后自动计算终点坐标
        if self.checked:
            model_type = '关'
            self.endX = self.width() - self.height()
        else:
            self.endX = 0
            model_type = '联想'
        self.timer.start(5)
    def mouseMoveEvent(self, event):
        pass
    def paintEvent(self, evt):
        try:
            # 绘制准备工作, 启用反锯齿
            painter = QPainter()
            painter.begin(self)
            painter.setRenderHint(QPainter.Antialiasing)
            # 绘制背景
            self.drawBg(evt, painter)
            # 绘制滑块
            self.drawSlider(evt, painter)
            # 绘制文字
            self.drawText(evt, painter)
            painter.end()
        except:
            pass
    def drawText(self, event, painter):
        painter.save()
        if self.checked:
            painter.setPen(self.textColorOn)
            # painter.drawText(0, 0, int(self.width() / 2 + self.space * 2), self.height(), Qt.AlignCenter, self.textOn)
            painter.drawText(int(self.space * 4), 0, int(self.width() / 2 + self.space * 2), self.height(), Qt.AlignCenter,self.textOn)
        else:
            painter.setPen(self.textColorOff)
            # painter.drawText(int(self.width() / 2), 0,int(self.width() / 2 - self.space), self.height(), Qt.AlignCenter, self.textOff)
            painter.drawText(int(self.width() / 2), 0, int(self.width() / 2 - self.space), self.height(), Qt.AlignCenter,self.textOff)
        painter.restore()
    def drawBg(self, event, painter):
        painter.save()
        painter.setPen(self.edge)
        if self.checked:
            painter.setBrush(self.bgColorOn)
        else:
            painter.setBrush(self.bgColorOff)
        rect = QRect(0, 0, self.width(), self.height())
        # 半径为高度的一半
        radius = rect.height() / 2
        # 圆的宽度为高度
        circleWidth = rect.height()
        path = QPainterPath()
        path.moveTo(radius, rect.left())
        path.arcTo(QRectF(rect.left(), rect.top(), circleWidth, circleWidth), 90, 180)
        path.lineTo(rect.width() - radius, rect.height())
        path.arcTo(QRectF(rect.width() - rect.height(), rect.top(), circleWidth, circleWidth), 270, 180)
        path.lineTo(radius, rect.top())
        painter.drawPath(path)
        painter.restore()
    def drawSlider(self, event, painter):
        painter.save()
        if self.checked:
            painter.setBrush(self.sliderColorOn)
        else:
            painter.setBrush(self.sliderColorOff)
        rect = QRect(0, 0, self.width(), self.height())
        sliderWidth = int(rect.height() - self.space * 4)
        sliderRect = QRect(int(self.startX + self.space * 2), self.space * 2, sliderWidth, sliderWidth)
        painter.drawEllipse(sliderRect)
        painter.restore()
class SwitchBtn_2(QWidget):
    checkedChanged = pyqtSignal(bool)
    status_sig = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.edge = QColor(0, 0, 0)  # 边框颜色
        self.checked = False
        self.bgColorOff = QColor(255, 255, 255)  # 滑动条颜色
        self.bgColorOn = QColor(255, 255, 255)
       
        self.sliderColorOff = QRadialGradient(int(self.width() / 2), int(self.height() / 2), int(self.width() / 2), int(self.width() / 6),int(self.height() / 6))
        # 滑块颜色
        self.sliderColorOff.setColorAt(1, QColor('#e55f00')) # 开启状态
        # self.sliderColorOff.setColorAt(0.8, QColor(50, 100, 0))
        self.sliderColorOn = QRadialGradient(int(self.width() / 2), int(self.height() / 2), int(self.width() / 2), int(3 * self.width() / 4), int(self.height() / 2))
        self.sliderColorOn.setColorAt(1, QColor('#19232d')) # 关闭状态
        # self.sliderColorOn.setColorAt(0.8, QColor(255, 0, 0))
        self.textColorOff = QColor(0, 0, 0)  # 文本颜色
        self.textColorOn = QColor(0, 0, 0)
        self.textOff = "撰写"  # 初始文本
        self.textOn = "阅读"
        self.space = 2
        self.rectRadius = 5
        self.step = self.width() / 50
        self.startX = 0
        self.endX = 0
        self.timer = QTimer(self)  # 初始化一个定时器
        self.timer.timeout.connect(self.updateValue)  # 计时结束调用operate()方法
        self.status_sig.connect(self.auto_step)
        # self.timer.start(5)  # 设置计时间隔并启动
    def isChecked(self):
        return self.checked
    def to_open(self):
        # 打开状态
        self.checked = True
        # self.auto_step()
        self.status_sig.emit()
    def to_close(self):
        # 关闭状态
        self.checked = False
        # self.auto_step()
        self.status_sig.emit()
    def auto_step(self):
        # 每次移动的步长为宽度的50分之一
        self.step = self.width() / 40
        # 状态切换改变后自动计算终点坐标
        if self.checked:
            self.endX = self.width() - self.height()
        else:
            self.endX = 0
        self.timer.start(5)
    def setInitText(self, text):
        self.textOff = text
    def setSecondText(self, text):
        self.textOn = text
    def updateValue(self):
        if self.checked:
            if self.startX < self.endX:
                self.startX = self.startX + self.step
            else:
                self.startX = self.endX
                self.timer.stop()
        else:
            if self.startX > self.endX:
                self.startX = self.startX - self.step
            else:
                self.startX = self.endX
                self.timer.stop()
        self.update()
    def mousePressEvent(self, event):
        global write_type
        self.checked = not self.checked
        # 发射信号
        self.checkedChanged.emit(self.checked)

        # 每次移动的步长为宽度的50分之一
        self.step = self.width() / 40
        # 状态切换改变后自动计算终点坐标
        if self.checked:
            write_type = '阅读'
            self.endX = self.width() - self.height()
        else:
            self.endX = 0
            write_type = '撰写'
        self.timer.start(5)
    def mouseMoveEvent(self, event):
        pass
    def paintEvent(self, evt):
        try:
            # 绘制准备工作, 启用反锯齿
            painter = QPainter()
            painter.begin(self)
            painter.setRenderHint(QPainter.Antialiasing)
            # 绘制背景
            self.drawBg(evt, painter)
            # 绘制滑块
            self.drawSlider(evt, painter)
            # 绘制文字
            self.drawText(evt, painter)
            painter.end()
        except:
            pass
    def drawText(self, event, painter):
        painter.save()
        if self.checked:
            painter.setPen(self.textColorOn)
            # painter.drawText(0, 0, int(self.width() / 2) + self.space * 2, self.height(), Qt.AlignCenter, self.textOn)
            painter.drawText(self.space * 4, 0, int(self.width() / 2 + self.space * 2), self.height(), Qt.AlignCenter,self.textOn)
        else:
            painter.setPen(self.textColorOff)
            # painter.drawText(self.width() / 2, 0,int(self.width() / 2 - self.space), self.height(), Qt.AlignCenter, self.textOff)
            painter.drawText(int(self.width() / 2), 0, int(self.width() / 2 - self.space), self.height(), Qt.AlignCenter,self.textOff)
        painter.restore()
    def drawBg(self, event, painter):
        painter.save()
        painter.setPen(self.edge)
        if self.checked:
            painter.setBrush(self.bgColorOn)
        else:
            painter.setBrush(self.bgColorOff)
        rect = QRect(0, 0, self.width(), self.height())
        # 半径为高度的一半
        radius = rect.height() / 2
        # 圆的宽度为高度
        circleWidth = rect.height()
        path = QPainterPath()
        path.moveTo(radius, rect.left())
        path.arcTo(QRectF(rect.left(), rect.top(), circleWidth, circleWidth), 90, 180)
        path.lineTo(rect.width() - radius, rect.height())
        path.arcTo(QRectF(rect.width() - rect.height(), rect.top(), circleWidth, circleWidth), 270, 180)
        path.lineTo(radius, rect.top())
        painter.drawPath(path)
        painter.restore()
    def drawSlider(self, event, painter):
        painter.save()
        if self.checked:
            painter.setBrush(self.sliderColorOn)
        else:
            painter.setBrush(self.sliderColorOff)
        rect = QRect(0, 0, self.width(), self.height())
        sliderWidth = int(rect.height() - self.space * 4)
        sliderRect = QRect(int(self.startX + self.space * 2), self.space * 2, sliderWidth, sliderWidth)
        painter.drawEllipse(sliderRect)
        painter.restore()

class SwitchBtn_4(QWidget): # 自动补全
    checkedChanged = pyqtSignal(bool)
    status_sig = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.edge = QColor(0, 0, 0)  # 边框颜色
        self.checked = True
        self.bgColorOff = QColor(255, 255, 255)  # 滑动条颜色
        self.bgColorOn = QColor(255, 255, 255)
        self.sliderColorOff = QRadialGradient(int(self.width() / 2), int(self.height() / 2), int(self.width() / 2), int(self.width() / 6),int(self.height() / 6))
        # 滑块颜色
        self.sliderColorOff.setColorAt(1, QColor('#e55f00')) # 开启状态
        self.sliderColorOn = QRadialGradient(int(self.width() / 2), int(self.height() / 2), int(self.width() / 2), int(3 * self.width() / 4), int(self.height() / 2))
        self.sliderColorOn.setColorAt(1, QColor('#19232d')) # 关闭状态
        self.textColorOff = QColor(0, 0, 0)  # 文本颜色
        self.textColorOn = QColor(0, 0, 0)
        self.textOff = "补全"  # 初始文本
        self.textOn = "关闭"
        self.space = 2
        self.rectRadius = 5
        self.step = self.width() / 50
        self.startX = self.width() / 20 # 初始位置
        self.endX = 0
        self.timer = QTimer(self)  # 初始化一个定时器
        self.timer.timeout.connect(self.updateValue)  # 计时结束调用operate()方法
        self.status_sig.connect(self.auto_step)
        # self.timer.start(5)  # 设置计时间隔并启动
    def isChecked(self):
        return self.checked
    def to_open(self):
        # 打开状态
        self.checked = True
        # self.auto_step()
        self.status_sig.emit()
    def to_close(self):
        # 关闭状态
        self.checked = False
        # self.auto_step()
        self.status_sig.emit()
    def auto_step(self):
        # 每次移动的步长为宽度的50分之一
        self.step = self.width() / 40
        # 状态切换改变后自动计算终点坐标
        if self.checked:
            self.endX = self.width() - self.height()
        else:
            self.endX = 0
        self.timer.start(5)
    def setInitText(self, text):
        self.textOff = text
    def setSecondText(self, text):
        self.textOn = text
    def updateValue(self):
        if self.checked:
            if self.startX < self.endX:
                self.startX = self.startX + self.step
            else:
                self.startX = self.endX
                self.timer.stop()
        else:
            if self.startX > self.endX:
                self.startX = self.startX - self.step
            else:
                self.startX = self.endX
                self.timer.stop()
        self.update()
    def mousePressEvent(self, event):
        global write_auto
        self.checked = not self.checked
        # 发射信号
        self.checkedChanged.emit(self.checked)

        # 每次移动的步长为宽度的50分之一
        self.step = self.width() / 40
        # 状态切换改变后自动计算终点坐标
        if self.checked:
            write_auto = '关闭'
            self.endX = self.width() - self.height()
        else:
            self.endX = 0
            write_auto = '补全'
        self.timer.start(5)
    def mouseMoveEvent(self, event):
        pass
    def paintEvent(self, evt):
        try:
            # 绘制准备工作, 启用反锯齿
            painter = QPainter()
            painter.begin(self)
            painter.setRenderHint(QPainter.Antialiasing)
            # 绘制背景
            self.drawBg(evt, painter)
            # 绘制滑块
            self.drawSlider(evt, painter)
            # 绘制文字
            self.drawText(evt, painter)
            painter.end()
        except:
            pass
    def drawText(self, event, painter):
        painter.save()
        if self.checked:
            painter.setPen(self.textColorOn)
            painter.drawText(int(self.space * 4), 0, int(self.width() / 2 + self.space * 2), self.height(), Qt.AlignCenter,self.textOn)
        else:
            painter.setPen(self.textColorOff)
            painter.drawText(int(self.width() / 2), 0,int(self.width() / 2 - self.space), self.height(), Qt.AlignCenter,self.textOff)
        painter.restore()
    def drawBg(self, event, painter):
        painter.save()
        painter.setPen(self.edge)
        if self.checked:
            painter.setBrush(self.bgColorOn)
        else:
            painter.setBrush(self.bgColorOff)
        rect = QRect(0, 0, self.width(), self.height())
        # 半径为高度的一半
        radius = rect.height() / 2
        # 圆的宽度为高度
        circleWidth = rect.height()
        path = QPainterPath()
        path.moveTo(radius, rect.left())
        path.arcTo(QRectF(rect.left(), rect.top(), circleWidth, circleWidth), 90, 180)
        path.lineTo(rect.width() - radius, rect.height())
        path.arcTo(QRectF(rect.width() - rect.height(), rect.top(), circleWidth, circleWidth), 270, 180)
        path.lineTo(radius, rect.top())
        painter.drawPath(path)
        painter.restore()
    def drawSlider(self, event, painter):
        painter.save()
        if self.checked:
            painter.setBrush(self.sliderColorOn)
        else:
            painter.setBrush(self.sliderColorOff)
        rect = QRect(0, 0, self.width(), self.height())
        sliderWidth = int(rect.height() - self.space * 4)
        sliderRect = QRect(int(self.startX + self.space * 2), int(self.space * 2), sliderWidth, sliderWidth)
        painter.drawEllipse(sliderRect)
        painter.restore()

class Label_Symbol(QLabel):
    def __init__(self,active_textcomponent,txt):
        super().__init__()
        global_active_textcomponent = active_textcomponent
        self.setText(txt)
        self.mousePressEvent = self.insert_symbol

    def insert_symbol(self,event):
        cursor = global_active_textcomponent.textCursor()
        lb_txt = self.text()
        cursor.insertHtml(lb_txt)
        
class QWidget_Notop(QWidget):
    def __init__(self,title):
        super().__init__()
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
            # if y > 50 and y < 900 and x > 200:
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

class OcrDropTextEdit(QTextEdit):
    # 定义一个信号
    sendmsg = pyqtSignal(object)
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.strPathFile = ""
        self.setStyleSheet("QTextEdit {background-color: #19232d;color: white} QTextEdit:hover{background-color:#212e3b;color: white}")
        self.setMinimumWidth(50)
        self.setLineWrapMode(0) #依据编辑框宽度换行  0 为不换行
        self.setPlaceholderText("按照下述格式粘贴后，将自动整理格式\n例1：\n1壳体、2把手、3内壁\n例2：\n1壳体、11把手；2内壁\n例3：\n1壳体；2把手；3内壁\n例4：\n1壳体，2把手，3内壁")
        self.setToolTip('按Ctrl点击相应标记，可同时高亮显示多个技术特征')
        self.setUndoRedoEnabled(True)

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
class Worker_Start(QThread):
    progress = pyqtSignal(int)
    def __init__(self):
        super().__init__()
        self.count = 0
    def run(self):
        for i in range(0,2):
            self.count += 1
            time.sleep(0.5)
        self.progress.emit(self.count)
class Window_Start(QWidget):
    def __init__(self):
        super().__init__()
        self.start_ui()
        self.start_thread = Worker_Start()
        self.start_thread.progress.connect(self.fn_worker_start)
        self.start_thread.start()
    def fn_worker_start(self):
        self.hide()
        window_login = LoginWindow()
        window_login.show()

    def start_ui(self):
        self.start_layout = QGridLayout(self)
        self.setWindowTitle(f"FENRIR ver{version}")
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.setStyleSheet("background-color: white")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        screen = QDesktopWidget().screenGeometry()
        self.move(int((screen.width() - 300) / 2), int((screen.height() - 210) / 2))
        self.setFixedSize(400, 210)
        self.label_start_1 = QLabel(f'FENRIR ver{version} 启动中...')
        self.label_start_1.setStyleSheet("background-color: white;color:black")
        self.label_start_1.setMaximumHeight(30)

        self.label_start_2 = QLabel('© Fenrir. All Rights Reserved.')
        self.label_start_2.setStyleSheet("background-color: white;color:black")
        self.label_start_2.setMaximumHeight(30)

        self.label_logo = QLabel()
        movie = QMovie(f"./ui/start.gif")
        self.label_logo.setScaledContents(True)
        self.label_logo.setMovie(movie)
        self.label_logo.setMinimumWidth(400)
        self.label_logo.setMinimumHeight(200)
        movie.start()
        self.start_layout.addWidget(self.label_start_1,0,0)
        self.start_layout.addWidget(self.label_start_2,0,1)

        self.start_layout.addWidget(self.label_logo,1,0)
        self.show()
class QTextEditWithLineNum(QTextEdit):
    sendmsg = pyqtSignal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        shortcut_txt_1 = "AI功能快捷键：\nAlt+Q：AI填充\nAlt+W：AI续写\nAlt+E：AI润色\nAlt+R：概念查询\nAlt+T：文本翻译\n"
        shortcut_txt_2 = "模板快捷键：\nAlt+1：OA答复\nAlt+2：说明书\nAlt+3：权利要求书\nAlt+4：复审请求\nAlt+5：无效宣告请求\nAlt+6：AI撰写说明书\n"
        shortcut_txt_3 = "批量文本快捷键：\nCtrl+1：A => A1\nCtrl+2：A => A(1)\nCtrl+3：1 => A1\nCtrl+4：1 => A(1)\nCtrl+5：A1/(1) => A\nCtrl+6：A1 => A(1)\nCtrl+7：A(1) => A1\nCtrl+8：合并附图标记\nCtrl+9：提取发明内容\n"
        shortcut_txt_4 = "Ctrl+Q：提取附图标记\nCtrl+W：统一单位\nCtrl+E：统一元素符号\nCtrl+R：删除多余回车\nCtrl+T：删除空格\nCtrl+J：删除段号\nCtrl+G：增加段号\nCtrl+F：全部替换\n\nCtrl+~：自定义文本联想\nCtrl+Enter：自动补充序号/从权"
        self.setPlaceholderText(f'{shortcut_txt_1}\n{shortcut_txt_2}\n{shortcut_txt_3}\n{shortcut_txt_4}')
        self.setFontPointSize(12)
        self.setUndoRedoEnabled(True)
        # self.setLineWrapMode(QTextEdit.NoWrap)  # 不自动换行
        self.lineNumberArea = LineNumPaint(self)
        self.setAcceptDrops(True)
        self.strPathFile = ""
        self.document().blockCountChanged.connect(self.update_line_num_width)

        self.verticalScrollBar().valueChanged.connect(self.lineNumberArea.update)
        # self.textChanged.connect(self.lineNumberArea.update)
        # self.cursorPositionChanged.connect(self.lineNumberArea.update)
        self.update_line_num_width()
        self.counter = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(120)
    def lineNumberAreaWidth(self):
        block_count = self.document().blockCount()
        max_value = max(1, block_count)
        d_count = len(str(max_value))
        _width = self.fontMetrics().width('9') * d_count + 5
        return _width
    def update_line_num_width(self):
        self.setViewportMargins(self.lineNumberAreaWidth() + 5, 0, 0, 0)
    
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
    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))
    def lineNumberAreaPaintEvent(self, event):
        global line_height
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor("#19232d"))
        # 获取首个可见文本块
        first_visible_block_number = self.cursorForPosition(QPoint(0, 1)).blockNumber()
        # 从首个文本块开始处理
        blockNumber = first_visible_block_number
        block = self.document().findBlockByNumber(blockNumber)
        top = 3 #self.viewport().geometry().top()
        if blockNumber == 0:
            additional_margin = int(self.document().documentMargin() - self.verticalScrollBar().sliderPosition() - 1)
        else:
            prev_block = self.document().findBlockByNumber(blockNumber - 1)
            additional_margin = int(self.document().documentLayout().blockBoundingRect(prev_block).bottom()) - self.verticalScrollBar().sliderPosition()
        top += additional_margin
        bottom = top + int(self.document().documentLayout().blockBoundingRect(block).height())
        last_block_number = self.cursorForPosition(QPoint(0, self.height() - 1)).blockNumber()
        height = self.fontMetrics().height()
        while block.isValid() and (top <= event.rect().bottom()) and blockNumber <= last_block_number:
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                if number != '1':
                    # top +=  int((line_height + 1)*1)
                    if line_height == 0:
                        pass
                    elif line_height == 0.2:
                        height += 1.8
                    elif line_height == 0.5:
                        height += 5.6
                    elif line_height == 1.0:
                        height += 9.6
                    elif line_height == 1.5:
                        height += 15.5
                    elif line_height == 2.0:
                        height += 19.5
                    elif line_height == 2.5:
                        height += 25.0
                    elif line_height == 3.0:
                        height += 31
                    elif line_height == 3.5:
                        height += 35.5
                    elif line_height == 4.0:
                        height += 39.5
                painter.setPen(QColor('#8c9196'))
                painter.drawText(0, int(top), int(self.lineNumberArea.width()), int(height), Qt.AlignCenter, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.document().documentLayout().blockBoundingRect(block).height())
            blockNumber += 1
    def update(self):
        if self.counter % 30 == 0:
            self.setStyleSheet("QTextEdit {border: 1px solid #19232d;}")
        elif self.counter % 30 == 1:
            self.setStyleSheet("QTextEdit {border: 1px solid #212f3c;}")
        elif self.counter % 30 == 2:
            self.setStyleSheet("QTextEdit {border: 1px solid #2a3a4b;}")
        elif self.counter % 30 == 3:
            self.setStyleSheet("QTextEdit {border: 1px solid #32465a;}")
        elif self.counter % 30 == 4:
            self.setStyleSheet("QTextEdit {border: 1px solid #3a5269;}")
        elif self.counter % 30 == 5:
            self.setStyleSheet("QTextEdit {border: 1px solid #435d78;}")
        elif self.counter % 30 == 6:
            self.setStyleSheet("QTextEdit {border: 1px solid #4b6987;}")
        elif self.counter % 30 == 7:
            self.setStyleSheet("QTextEdit {border: 1px solid #547596;}")
        elif self.counter % 30 == 8:
            self.setStyleSheet("QTextEdit {border: 1px solid #5c80a5;}")
        elif self.counter % 30 == 9:
            self.setStyleSheet("QTextEdit {border: 1px solid #648cb4;}")
        elif self.counter % 30 == 10:
            self.setStyleSheet("QTextEdit {border: 1px solid #6d98c3;}")
        elif self.counter % 30 == 11:
            self.setStyleSheet("QTextEdit {border: 1px solid #75a3d2;}")
        elif self.counter % 30 == 12:
            self.setStyleSheet("QTextEdit {border: 1px solid #7dafe1;}")
        elif self.counter % 30 == 13:
            self.setStyleSheet("QTextEdit {border: 1px solid #86bbf0;}")
        elif self.counter % 30 == 14:
            self.setStyleSheet("QTextEdit {border: 1px solid #8ec7ff;}")
        elif self.counter % 30 == 15:
            self.setStyleSheet("QTextEdit {border: 1px solid #8ec7ff;}")
        elif self.counter % 30 == 16:
            self.setStyleSheet("QTextEdit {border: 1px solid #8ec7ff;}")
        elif self.counter % 30 == 17:
            self.setStyleSheet("QTextEdit {border: 1px solid #86bbf0;}")
        elif self.counter % 30 == 18:
            self.setStyleSheet("QTextEdit {border: 1px solid #7dafe1;}")
        elif self.counter % 30 == 19:
            self.setStyleSheet("QTextEdit {border: 1px solid #75a3d2;}")
        elif self.counter % 30 == 20:
            self.setStyleSheet("QTextEdit {border: 1px solid #6d98c3;}")
        elif self.counter % 30 == 21:
            self.setStyleSheet("QTextEdit {border: 1px solid #648cb4;}")
        elif self.counter % 30 == 22:
            self.setStyleSheet("QTextEdit {border: 1px solid #5c80a5;}")
        elif self.counter % 30 == 23:
            self.setStyleSheet("QTextEdit {border: 1px solid #547596;}")
        elif self.counter % 30 == 23:
            self.setStyleSheet("QTextEdit {border: 1px solid #4b6987;}")
        elif self.counter % 30 == 24:
            self.setStyleSheet("QTextEdit {border: 1px solid #435d78;}")
        elif self.counter % 30 == 25:
            self.setStyleSheet("QTextEdit {border: 1px solid #3a5269;}")
        elif self.counter % 30 == 26:
            self.setStyleSheet("QTextEdit {border: 1px solid #32465a;}")
        elif self.counter % 30 == 27:
            self.setStyleSheet("QTextEdit {border: 1px solid #2a3a4b;}")
        elif self.counter % 30 == 28:
            self.setStyleSheet("QTextEdit {border: 1px solid #212f3c;}")
        if self.counter % 30 == 29:
            self.setStyleSheet("QTextEdit {border: 1px solid #11171e;}")
        self.counter += 1
class LineNumPaint(QWidget):
    def __init__(self, q_edit):
        super().__init__(q_edit)
        self.q_edit_line_num = q_edit
    def sizeHint(self):
        return QSize(self.q_edit_line_num.lineNumberAreaWidth(), 0)
    def paintEvent(self, event):
        self.q_edit_line_num.lineNumberAreaPaintEvent(event)
    
class BreathLineEdit(QLineEdit): # 呼吸灯
    def __init__(self):
        global version
        super().__init__()
        self.counter = 0      
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(140)
    def update(self):
        if self.counter % 30 == 0:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #19232d;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 1:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #212f3c;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 2:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #2a3a4b;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 3:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #32465a;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 4:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #3a5269;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 5:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #435d78;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 6:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #4b6987;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 7:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #547596;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 8:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #5c80a5;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 9:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #648cb4;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 10:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #6d98c3;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 11:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #75a3d2;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 12:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #7dafe1;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 13:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #86bbf0;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 14:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #8ec7ff;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 15:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #8ec7ff;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 16:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #8ec7ff;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 17:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #86bbf0;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 18:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #7dafe1;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 19:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #75a3d2;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 20:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #6d98c3;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 21:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #648cb4;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 22:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #5c80a5;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 23:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #547596;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 23:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #4b6987;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 24:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #435d78;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 25:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #3a5269;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 26:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #32465a;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 27:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #2a3a4b;} QLineEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 28:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #212f3c;} QLineEdit:focus{background-color:#212e3b;color: white}")
        if self.counter % 30 == 29:
            self.setStyleSheet("QLineEdit {background-color: black;color: white; border: 1px solid #11171e;} QLineEdit:focus{background-color:#212e3b;color: white}")
        self.counter += 1

class BreathTextEdit(QTextEdit): # 呼吸灯
    def __init__(self):
        global version
        super().__init__()
        self.counter = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(150)
    def update(self):
        if self.counter % 30 == 0:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #19232d;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 1:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #212f3c;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 2:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #2a3a4b;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 3:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #32465a;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 4:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #3a5269;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 5:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #435d78;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 6:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #4b6987;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 7:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #547596;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 8:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #5c80a5;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 9:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #648cb4;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 10:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #6d98c3;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 11:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #75a3d2;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 12:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #7dafe1;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 13:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #86bbf0;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 14:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #8ec7ff;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 15:
            pass
        elif self.counter % 30 == 16:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #8ec7ff;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 17:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #86bbf0;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 18:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #7dafe1;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 19:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #75a3d2;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 20:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #6d98c3;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 21:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #648cb4;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 22:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #5c80a5;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 23:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #547596;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 23:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #4b6987;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 24:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #435d78;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 25:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #3a5269;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 26:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #32465a;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 27:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #2a3a4b;} QTextEdit:focus{background-color:#212e3b;color: white}")
        elif self.counter % 30 == 28:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #212f3c;} QTextEdit:focus{background-color:#212e3b;color: white}")
        if self.counter % 30 == 29:
            self.setStyleSheet("QTextEdit {background-color: black;color: white; border: 1px solid #11171e;} QTextEdit:focus{background-color:#212e3b;color: white}")
        self.counter += 1
class NewWindow(QWidget):
    def __init__(self,tab_index):
        super().__init__()
        global window_show_text_array,window_show_mark_array
        self.setWindowIcon(QIcon(qta.icon('fa5b.wolf-pack-battalion')))
        self.tab_index = tab_index
        self.new_layout = QGridLayout(self)

        self.new_text_editor = window_show_text_array[self.tab_index]
        self.new_mark_editor = window_show_mark_array[self.tab_index]
        self.new_mark_editor.setFixedWidth(150)

        self.mousePressEvent = self.mouse_press_event
        # self.new_text_editor.mousePressEvent = self.mouse_press_event

        self.new_layout.addWidget(self.new_mark_editor, 0, 0, 1, 1)
        self.new_layout.addWidget(self.new_text_editor, 0, 1, 1, 1)


    def closeEvent(self, event): 
        global tab_count_array,tab_widget_text,tab_widget_mark,window_show_array,text_editor_array,mark_editor_array
        new_tab_index = self.tab_index
        tab_count_array.remove(self.tab_index)

        all_txt = self.new_text_editor.toHtml()
        marks_txt = self.new_mark_editor.toPlainText()

        open(f'./data/text_saver_{self.tab_index + 1}.html','w+',encoding='utf-8').write(all_txt)
        open(f'./data/marks_saver_{self.tab_index + 1}.txt', 'w+', encoding='utf-8').write(marks_txt)

        self.ori_text_editor = text_editor_array[self.tab_index]
        self.ori_mark_editor = mark_editor_array[self.tab_index]

        self.ori_text_editor.setHtml(all_txt)
        self.ori_mark_editor.setPlainText(marks_txt)

        tab_name = self.windowTitle()
        # 校正 self.tab_index
        for _ in tab_count_array:
            if _ < self.tab_index:
                new_tab_index -= 1
        tab_widget_text.insertTab(new_tab_index,self.ori_text_editor, tab_name)
        tab_widget_text.setCurrentIndex(new_tab_index)

        tab_widget_mark.insertTab(new_tab_index,self.ori_mark_editor, f'列表{new_tab_index+1}')
        tab_widget_mark.setCurrentIndex(new_tab_index)

        window_show_array[self.tab_index].close() 

    def mouse_press_event(self,event):
        global global_active_textcomponent,global_active_figmark
        global_active_textcomponent = self.new_text_editor
        global_active_figmark = self.new_mark_editor
        # print('Active_Window Index:',self.tab_index)


version = '3.5.15'
user = ''
tab_count_array = []
model_type = '联想'
write_type = '撰写'
write_auto = '关闭'
global_active_textcomponent,global_active_figmark = '',''
window_adjust = ''
window_figeditor = ''
window_login = ''
window_main = ''
rep_model = 0
line_height = 0.5
toggle_flag = 0 # 标记大小写转换
expand_length = '200~400' # open('./data/expand_length.txt','r',encoding='utf-8').read()
messages = []
xinghuo_messages = []
model_api = 'Doubao'
deep_model = 'deepseek-chat'
if __name__ == '__main__':
    ct = win32api.GetConsoleTitle()
    hd = win32gui.FindWindow(0, ct)
    win32gui.ShowWindow(hd, 0)
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5'))#, palette=qdarkstyle.light.palette.LightPalette))
    # window_start = Window_Start()
    window_main = MainWindow()
    window_main.show()
    app.exec_()

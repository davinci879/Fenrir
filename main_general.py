from ctypes import *
import re
import time
import random
from threading import Thread

check_port = 4408
file_over_write = False
img_dic = {0:'',1:'',2:'',3:'',4:'',5:'',6:'',7:'',8:''} # 主 后 左 右 俯 仰 立 状态I 状态II

def judge_dot(intxt):
    for _ in list('，。；：？！'):
        if _ in intxt:
            return 1
    return 0

# 补全句子
# 查找包含前句末尾
def refine_array(in_array, type):
    if type == 'set':
        in_array = list(set(in_array))
    while '' in in_array:
        in_array.remove('')
    while ' ' in in_array:
        in_array.remove(' ')
    return in_array

def split_marks_bysort(all_marks):  # 按顺序排列
    temp_array, figmarks_array = [], []
    temp_array = all_marks.replace('\r','\u2029').replace('\t','\u2029').replace('\n','\u2029').replace(',','，').replace(';','；').split('\u2029')
    for mark1 in temp_array:
        if '；' in mark1:
            _temp = mark1.split('；')
            for mark2 in _temp:
                if len(mark2.split('、')) > 2:
                    figmarks_array += mark2.split('、')
                elif len(mark2.split('，')) > 2:
                    figmarks_array += mark2.split('，')
                else:
                    figmarks_array.append(mark2.replace('、', ''))
        else:
            figmarks_array += re.split('、|，',mark1)
    # 将标号与文字用空格间隔
    temp_array = figmarks_array
    while '' in temp_array:
        temp_array.remove('')
    temp_array = list(set(temp_array))
    temp_array.sort()
    figmarks_array = []
    for i in range(1, 10):
        for item in temp_array:
            fig_num, fig_text = judge_mark(item.replace(' ', ''))
            if len(fig_num) == i or len(fig_num.strip('abcdefghijklmnopqrstuvwxyz')) == i:
                figmarks_array.append(f'{fig_num} {fig_text}'.strip('，。,；;'))
                # if len(figmarks_array) == len(all_marks.replace('\n','\u2029').split('\u2029|、|；')):
                #     return figmarks_array
    return figmarks_array


def split_marks(all_marks):  # 上下位排列
    temp_array, figmarks_array = [], []
    temp_array = all_marks.replace('\r','\u2029').replace('\t','\u2029').replace('\n','\u2029').replace(',','，').replace(';','；').split('\u2029')
    for mark1 in temp_array:
        if '；' in mark1:
            _temp = mark1.split('；')
            for mark2 in _temp:
                if len(mark2.split('、')) > 2:
                    figmarks_array += mark2.split('、')
                elif len(mark2.split('，')) > 2:
                    figmarks_array += mark2.split('，')
                else:
                    figmarks_array.append(mark2.replace('、', ''))
        else:
            figmarks_array += re.split('、|，',mark1)
    # 将标号与文字用空格间隔
    temp_array = figmarks_array
    figmarks_array = []
    for item in temp_array:
        fig_num, fig_text = judge_mark(item.replace(' ', ''))
        figmarks_array.append(f'{fig_num} {fig_text}')
    # 去重排序输出结果
    while '' in figmarks_array:
        figmarks_array.remove('')
    figmarks_array = list(set(figmarks_array))
    figmarks_array.sort()
    return figmarks_array


def judge_mark(text):
    fig_num, fig_text = '', ''
    text = text.replace(' ', '').replace('\n','\u2029').strip('\r\n\t\u2029')
    for i in range(0, len(text)):
        if text[i] not in '1234567890abcdefghijklmnopqrstuvwxyz':
            fig_num = text[0:i]
            fig_text = text[i:]
            break
    return fig_num, fig_text

def para_refine(txt):
    txt_array = txt.replace('\n','\u2029').split('\u2029')
    for _ in txt_array:
        if len(_) <= 5:
            txt_array.remove(_)
    return txt_array

def refine_txt(text, del_array):
    for del_txt in del_array:
        text = text.replace(del_txt, '')
    return text

def list_join(a, b):
    c = []
    for i in range(0, len(a)):
        c.append('<' + str("%02d" % i) + '> ' + a[i] + ' ' + b[i])
    return c


def list_join_1(a):
    b = []
    i = 1
    for _ in a:
        b.append(f'{i}.{_}')
        i += 1
    return b
# 命令行启动LOGO


def start_logo():
    logo = open('./data/logo.txt', 'r', encoding='utf-8').read()
    print(logo)


def handlerAdaptor(fun, **kwds):
    return lambda event, fun=fun, kwds=kwds: fun(event, **kwds)

''' 用于提取附图标记 '''
def refine_intxt(intxt):
    intxt = intxt.replace('（', '(').replace('）', ')').replace('：', ':').replace('，', ',').replace(
        '；', ';').replace('\r', '').replace('\n', '')  # .replace('特征在于','').replace('以及','')
    for i in range(1, 100):
        intxt = intxt.replace(f'图{i}', '')
    num_arr = '一二三四五六七八九十'
    for i in range(1, 10):
        for item in '个第':
            intxt = intxt.replace(f'{item}{i}', f'{item}{num_arr[int(i-1)]}').replace(
                f'{i}{item}', f'{num_arr[int(i-1)]}{item}')
    return intxt


''' 提取附图标记 type6 '''
def search_marks(intxt): # 获取标记名称
    intxt = intxt.replace('(', '（').replace(')', '）').replace(',', '，').replace(';', '；').replace(':', '：').replace('-', '').replace('—', '').replace('：', '').replace('为', '')
    all_array = []
    for _ in ['所述', '通过', '设置', '而且', '并且', '包括', '以及', '从', '该', '的', '且', '与', '是', '以', '将', '向', '沿', '即', '在', '有', '和', '使', '、', '；', '。', '，', '：']:
        all_array += re.findall(f'{_}(.*?)\（\d', intxt)
        all_array += re.findall(f'{_}(.*?)\d', intxt)
        all_array += re.findall(f'{_}(.*?)[a-zA-Z]', intxt)
    all_array += re.findall(f'所述(.*?组件)', intxt)
    all_array += re.findall(f'、(.*?)和', intxt)
    all_array += re.findall(f'(.*?)\d）的', intxt)
    all_array += re.findall(f'，(.*?)包括', intxt)
    for i in range(0, len(all_array)):
        item_temp = ''
        item = all_array[i].strip('着在于包括有与和以及均（）1234567890，。；').replace('上部', '').replace('下部', '').replace('外部', '').replace('内部', '')
        item = item.replace('侧部', '').replace('顶部', '').replace('底部', '').replace('权利要求', '').replace('其特征', '').replace('所述的', '').replace('所述', '')
        item = item.split('于')[-1]
        item = item.split('，')[-1]
        item = item.split('有')[-1]
        item = item.split('个')[-1]
        item = item.split('组')[-1]
        item = item.split('为')[-1]
        item = item.split('的')[-1]
        item = item.split('包括')[-1]
        item_temp = item.split('固定')[-1]
        if len(item_temp) >= 3:
            item = item.split('固定')[-1]
        item = item.strip('：')
        if len(item) >= 2:
            all_array[i] = item
        else:
            all_array[i] = ''
    all_array = refine_array(all_array, 'set')
    # 按字符长度降序排列
    all_array.sort(key=lambda x: len(x), reverse=True)
    array_dsc = all_array
    # 按字符长度升序排列
    all_array.sort(key=lambda x: len(x), reverse=False)
    array_asc = all_array
    all_array = []
    for item_1 in array_dsc:
        insert_flag = 1
        for item_2 in array_asc:
            # 如果item1中含有item2则排除item1
            if item_2 in item_1 and item_1 != item_2 and len(item_2) >= 2:
                insert_flag = 0
                break
        if insert_flag == 1:
            all_array.append(item_1)
    all_array.sort(key=lambda x: len(x), reverse=False)
    return all_array



# 补全标号 type1_2
def completion_nums(rep_type, all_marks, new_txt):
    item_lack_array, all_key_array, repeat_array, add_array = [], [], [], []
    figmarks_array = split_marks(all_marks)
    for item in figmarks_array:
        item_num, item_mark = judge_mark(item)
        all_key_array.append(item_mark)
    all_key_array.sort(key=lambda x: len(x), reverse=True)
    array_temp1 = all_key_array
    all_key_array.sort(key=lambda x: len(x))
    array_temp2 = all_key_array
    for word1 in array_temp1:
        for word2 in array_temp2:
            if word1 != word2 and word2 in word1:
                repeat_array.append(word2)
                add_array.append(word1)
    for item in figmarks_array:
        num, mark = judge_mark(item)
        if rep_type == 0 and mark not in repeat_array:
            if mark[-1] == 'I':
                new_txt = new_txt.replace(mark, mark + num)
            else:
                new_txt = new_txt.replace(mark.lower(), mark.lower() + num)
        elif rep_type == 1 and mark not in repeat_array:
            if mark[-1] == 'I':
                new_txt = new_txt.replace(mark, mark + '(' + num + ')')
            else:
                new_txt = new_txt.replace(mark.lower(), mark.lower() + '(' + num + ')')
        elif rep_type == 0 and mark in repeat_array:
            new_txt = new_txt.replace(mark.lower(), mark.lower() + num)
            for i in (0, len(repeat_array) - 1):
                if repeat_array[i] == mark:
                    new_txt = new_txt.replace(add_array[i].replace(mark.lower(), mark.lower() + num), add_array[i])
        elif rep_type == 1 and mark in repeat_array:
            new_txt = new_txt.replace(mark.lower(), mark.lower() + '(' + num + ')')
            for i in (0, len(repeat_array) - 1):
                if repeat_array[i] == mark:
                    new_txt = new_txt.replace(add_array[i].replace(mark.lower(), mark.lower() + '(' + num + ')'), add_array[i])
        if mark not in new_txt:
            item_lack_array.append(f'{num} {mark}')
    return new_txt, repeat_array, item_lack_array
# 补全名称  type3_4
def completion_marks(rep_type, all_marks, new_txt):
    num_array, mark_array, all_key_array, repeat_array, add_array, item_lack_array = [], [], [], [], [], []
    figmarks_array = split_marks(all_marks)
    for item in figmarks_array:
        item_num, item_mark = judge_mark(item)
        num_array.append(item_num)
        mark_array.append(item_mark)
    for index,item in enumerate(num_array):
        if len(item) == 5:
            new_txt = new_txt.replace(item, mark_array[index])
    for index,item in enumerate(num_array):
        if len(item) == 4:
            new_txt = new_txt.replace(item, mark_array[index])
    for index,item in enumerate(num_array):
        if len(item) == 3:
            new_txt = new_txt.replace(item, mark_array[index])
            new_txt = new_txt.replace(mark_array[index] + '.', item + '.')
            new_txt = new_txt.replace('权利要求' + mark_array[index], '权利要求' + item)
    for index,item in enumerate(num_array):
        if len(item) == 2:
            new_txt = new_txt.replace(item, mark_array[index])
            new_txt = new_txt.replace(mark_array[index] + '.', item + '.')
            new_txt = new_txt.replace('权利要求' + mark_array[index], '权利要求' + item)
    for index,item in enumerate(num_array):
        if len(item) == 1:
            new_txt = new_txt.replace(item, mark_array[index])
            new_txt = new_txt.replace(mark_array[index] + '.', item + '.')
            new_txt = new_txt.replace('权利要求' + mark_array[index], '权利要求' + item)
            new_txt = new_txt.replace('\n' + mark_array[index], '\n' + item)
            new_txt = new_txt.replace('-' + mark_array[index], '-' + item)
    for item in figmarks_array:
        fig_num, fig_text = judge_mark(item)
        all_key_array.append(fig_text)
    all_key_array.sort(key=lambda x: len(x), reverse=True)
    array_temp1 = all_key_array
    all_key_array.sort(key=lambda x: len(x))
    array_temp2 = all_key_array
    for word1 in array_temp1:
        for word2 in array_temp2:
            if word1 != word2 and word2 in word1:
                repeat_array.append(word2)
                add_array.append(word1)
    for item in figmarks_array:  # lower？
        num, mark = judge_mark(item)
        if rep_type == 0 and mark not in repeat_array:
            # new_txt = new_txt.replace(mark.lower(),mark.lower() + num)
            new_txt = new_txt.replace(mark, mark + num)
        elif rep_type == 1 and mark not in repeat_array:
            # new_txt = new_txt.replace(mark.lower(),mark.lower() + '(' + num + ')')
            new_txt = new_txt.replace(mark, mark + '(' + num + ')')

        elif rep_type == 0 and mark in repeat_array:
            # new_txt = new_txt.replace(mark.lower(),mark.lower() + num)
            new_txt = new_txt.replace(mark, mark + num)
            for i in (0, len(repeat_array) - 1):
                if repeat_array[i] == mark:
                    new_txt = new_txt.replace(add_array[i].replace(
                        mark.lower(), mark.lower() + num), add_array[i])
        elif rep_type == 1 and mark in repeat_array:
            new_txt = new_txt.replace(
                mark.lower(), mark.lower() + '(' + num + ')')
            for i in (0, len(repeat_array) - 1):
                if repeat_array[i] == mark:
                    new_txt = new_txt.replace(add_array[i].replace(
                        mark.lower(), mark.lower() + '(' + num + ')'), add_array[i])
        if mark not in new_txt:
            item_lack_array.append(f'{num} {mark}')
    return new_txt, repeat_array, item_lack_array
def delete_bracketmarks_mohu(intxt):
    del_array = []
    intxt = intxt.replace('(','（').replace(')','）')
    del_array = re.findall('（.*?）', intxt)# + re.findall(mark+'[.*?]', intxt) + re.findall(mark+'{.*?}', intxt)
    for item in del_array:
        intxt = intxt.replace(item, '')
    return intxt
# 去除括号标记 type5
def delete_bracketmarks(intxt,all_marks):
    figmarks_array = split_marks(all_marks)
    del_array = []
    intxt = intxt.replace('(','（').replace(')','）')
    for item in figmarks_array:
        num, mark = judge_mark(item)
        del_array = re.findall(mark+'（.*?）', intxt)# + re.findall(mark+'[.*?]', intxt) + re.findall(mark+'{.*?}', intxt)
        for item in del_array:
            intxt = intxt.replace(item, mark)
    return intxt
# 获得附图标记 type6
def get_figmarks(in_array, intxt):
    # 删除段号
    para_num = re.findall('\[\d\d?\d?\d?\]',intxt)
    for _ in para_num:
        intxt = intxt.replace(_,'')
    figmarks_array = []
    for item in in_array:
        for word in ['\d{4}[a-z]', '\d{3}[a-z]', '\d{4}', '\d{2}[a-z]', '\d{3}', '\d{2}', '\d[a-z]', '\d{1}', '[a-z]']:
            try:
                search_txt = re.findall(f'{item}({word})', intxt)
                search_txt += re.findall(f'{item}（({word})）', intxt)
                search_txt += re.findall(f'{item}\(({word})\)', intxt)
                if search_txt and search_txt[0][0] != '0':
                    figmarks_array.append(f'{search_txt[0]}{item}')
                    break
            except Exception as e:
                pass#print(word,e)
    figmarks_array = list(set(figmarks_array))
    figmarks_array.sort()
    num_array, mark_array, out_array, same_marks_array = [], [], [], []
    for item in figmarks_array:
        fig_num, fig_text = judge_mark(item)
        if fig_num != '' and fig_text != '':
            if fig_num in num_array or fig_text in mark_array:
                same_marks_array.append(f'{fig_num} {fig_text}')
            num_array.append(fig_num)
            mark_array.append(fig_text)

    for i in range(0, len(num_array)):
        out_array.append(f"{num_array[i]} {mark_array[i]}")
    out_array = list(set(out_array))
    out_array.sort()
    return out_array, same_marks_array
# type9
def arrenge_document(txt):
    ori = ["X型", "S型", "A型", "C型", "L型", "V型", " ", ".根据", ".一种",
           "1次", "2次", "3次", "4次", "5次", "6次", "7次", "8次", "9次", "10次",
           "1个", "2个", "3个", "4个", "5个", "6个", "7个", "8个", "9个", "10个",
           ":", ";", ",,", "。。", "，，", "、、", "；；", "？？", "““", "””", "：：",
           ";;", "::", "..",
           "摄氏度", "°C",
           "毫升", "微升",
           "毫米", "分米", "厘米", "纳米", "微米", "米", "英尺", "英寸",
           "千帕", "兆帕",
           "千克", "毫克", "微克", "KG",
           "小时", "分钟", "毫秒", "微秒", "秒",
           "；图1", "；图2", "；图3", "；图4", "；图5", "；图6", "；图7", "；图8", "；图9", "；图10",
           "1 ", "2 ", "3 ", "4 ", "5 ", "6 ", "7 ", "8 ", "9 ", "10 ",
           "实用新型人", "每个", '\n\n']

    rep = ["X形", "S形", "A形", "C形", "L形", "V形", "", ". 根据", ". 一种",
           "一次", "两次", "三次", "四次", "五次", "六次", "七次", "八次", "九次", "十次",
           "一个", "两个", "三个", "四个", "五个", "六个", "七个", "八个", "九个", "十个",
           "：", "；", ",", "。", "，", "、", "；", "？", "“", "”", "：",
           ";", ":", ".",
           "℃", "℃",
           "ml", "μl",
           "mm", "dm", "cm", "nm", "μm", "m", "ft", "in",
           "kPa", "mPa",
           "kg", "mg", "μg", "kg",
           "h", "min", "ms", "μs", "s",
           "浓度", "照度", "光度", "碳纳米管", "升降", "抬升", "升压",
           "；\n图1", "；\n图2", "；\n图3", "；\n图4", "；\n图5", "；\n图6", "；\n图7", "；\n图8", "；\n图9", "；\n图10",
           "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
           "发明人", "各", '\n']
    for index,item in enumerate(ori):
        txt = txt.replace(item, rep[index])
    return txt
# type 12
def rep_elements(intxt):
    Acid_ori4 = ["亚硫酸", "硫酸", "碳酸", "氰酸", "硝酸", "偏铝酸", "硅酸", "原硅酸", "亚硫酸氢",
                 "硫酸氢", "硫代硫酸", "次氯酸", "氯酸", "高氯酸", "锰酸", "次溴酸", "溴酸", "碘酸", "磷酸"]
    Acid_rep4 = ["SO3", "SO4", "CO3", "HCN", "NO3", 'SiO3', 'SiO4', 'HSO3',
                 'HSO4', 'S2O3', 'ClO', 'ClO3', 'ClO4', 'MnO4', 'BrO', 'BrO3', 'IO3', "PO4"]
    Acid_ori1 = ["氢氰酸", "碳酸氢", "醋酸根", "硫氰酸", "亚硝酸", "高锰酸", "氢氧", ]
    Acid_rep1 = ["HCN", "HCO3", "Ac", "HS", "NO2", "MnO4", 'OH']
    num_array = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
                 "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]
    element_1 = ["氦", "锂", "铍", "氖", "钠", "镁", "铝", "硅", "氯", "氩", "钙", "钪", "钛", "铬", "锰", "铁", "钴", "镍", "铜", "锌", "镓", "锗", "砷", "硒", "溴", "氪", "铷", "锶", "锆", "铌", "钼", "锝", "钌", "铑", "钯",
                 "银", "镉", "铟", "锡", "锑", "碲", "氙", "铯", "钡", "铪", "钽", "铼", "锇", "铱", "铂", "金", "汞", "铊", "铅", "铋", "钋", "砹", "氡", "钫", "镭", "磷", "硫", "氟", "碘", "氮", "硼", "氢", "钨", "碳", "氧", "钒", "钇", "钾"]
    element_2 = ["He", "Li", "Be", "Ne", "Na", "Mg", "Al", "Si", "Cl", "Ar", "Ca", "Sc", "Ti", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh",
                 "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "Xe", "Cs", "Ba", "Hf", "Ta", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "P", "S", "F", "I", "N", "B", "H", "W", "C", "O", "V", "Y", "K"]
    for index1,item1 in enumerate(element_1):
        for index2,item2 in enumerate(element_1):
            if item1 == item2:
                continue
            for index3,num1 in enumerate(num_array):
                index3 += 1
                for index4,num2 in enumerate(num_array):
                    index4 += 1
                    intxt = intxt.replace(f'{num1}{item1}化{num2}{item2}', f'{element_2[index2]}{index4}{element_2[index1]}{index3}')
                intxt = intxt.replace(f'{num1}{item1}化{item2}', f'{element_2[index2]}{element_2[index1]}{index3}')
            intxt = intxt.replace(f'{item1}化{item2}',f'{element_2[index2]}{element_2[index1]}')
    return intxt


# 图片标记编辑
position_array_temp, fig_lines_array_temp, mark_array_temp = [], [], []
fig_lines_array, mark_array, position_array = [], [], []
all_x2y2_array, x2_array, y2_array = [], [], []
fw, fh, all_x2_array, canvas_width, canvas_height, edge_distence, scale_angle, font_size = 0, 0, [], 0, 0, 30, 10, 10
mark_loc = 'up'
x1_temp, y1_temp = 0, 0


def get_xarray(all_x2y2_array):  # 获取最大x2对应的坐标x2y2
    global x2_array, y2_array
    x2max, y2max = '', ''
    if all_x2y2_array:
        for item in all_x2y2_array:
            x2_array.append(int(item.split(' ')[0]))
            y2_array.append(int(item.split(' ')[1]))
        x2max = max(x2_array)
        y2max = y2_array[x2_array.index(x2max)]
    return x2_array

def arrow_type_get(value):
    global arrow_type
    arrow_type = value
    if arrow_type == '0':
        arrow_type = 'normal'
    elif arrow_type == '1':
        arrow_type = 'arrow'
    elif arrow_type == '2':
        arrow_type = 'point'
    elif arrow_type == '3':
        arrow_type = 'circle'


def curve_r_get(value):  # 调整曲线半径
    global curve_r
    curve_r = int(value)
# 生成权利要求树


def get_claimtree(all_forepart_array):
    # 获取前序部分引用的权利要求
    claim_tree_dic = {}  # 权利要求书字典
    claim_index = 0
    # 替换“至”
    for part_index,forepart in enumerate(all_forepart_array):
        if '至' in forepart and part_index != 0:
            fore_num = int(forepart.split('至')[0])
            for search_ in ['至(\d{2})', '至(\d{1})']:
                back_num = re.findall(search_, forepart)
                if back_num:
                    back_num = int(back_num[0])
                    break
            all_num = ''
            for i in range(fore_num, back_num + 1):
                all_num += f'{i}或'
            all_forepart_array[part_index] = all_num
    for forepart in all_forepart_array:
        claim_index += 1
        if claim_index == 1:
            claim_tree_dic[str(claim_index)] = '0'
        else:
            fore_nums = []
            for i in range(100, 0, -1):
                i = str(i)
                if i in forepart:
                    fore_nums.append(i)
                    forepart = forepart.replace(i, '')
            claim_tree_dic[str(claim_index)] = ' '.join(fore_nums)
    # 拆分引用关系dic
    claim_tree_array = []  # 拆分引用关系
    for num_1 in claim_tree_dic:
        num_2_array = claim_tree_dic[num_1].split(' ')
        for num_2 in num_2_array:
            if num_2 == '0':
                break
            if int(num_2) < int(num_1):
                claim_tree_array.append(f'{num_2} {num_1}')
            else:
                claim_tree_array.append(f'{num_1} {num_2}')
    # 校验权利要求引用关系
    while True:
        total_tree_length = len(claim_tree_array)
        for item_1 in claim_tree_array:
            if item_1[0] != '1':
                continue
            for item_2 in claim_tree_array:
                if item_1.split(' ')[-1] == item_2.split(' ')[0] and f'{item_1} {item_2}' not in claim_tree_array:
                    claim_tree_array.append(f'{item_1} {item_2}')
        if total_tree_length == len(claim_tree_array):
            break
    claim_tree_array.sort(key=lambda x: len(x), reverse=True)
    # 筛选最终结果
    out_array, out_array_temp = [], []
    for item_1 in claim_tree_array:
        add_judge = '0'
        if item_1.split(' ')[0] == '1':
            for item_2 in claim_tree_array:
                if item_1 in item_2 and item_1 != item_2:
                    add_judge = '1'
                    break
            if add_judge != '1':
                out_array_temp.append(item_1)
    # 整理内容
    for item in out_array_temp:
        item_array = item.split(' ')
        item_array = list(set(item_array))
        item_array.sort(key=lambda x: int(x), reverse=False)
        out_array.append('=>'.join(item_array))
    out_array.sort(key=lambda x: int(x.split('=>')[1]), reverse=False)
    return out_array

'''txteditor'''
# text_component中高亮设置与mark相似的文本
def get_similar_markindex(all_txt, mark,text_component,type_highlight_color):
    tag_index, para_index = 0, 0
    para_array = re.split('\n', all_txt)
    similar_txt_array = []
    similar_txt = ''
    for _ in mark:
        similar_txt += (_ + '.?.?')
    similar_txt = similar_txt.strip('.?')
    similar_txt_array.append(similar_txt)
    for index,_ in enumerate(mark):
        if len(mark) <= 1:
            break
        if index == 0 or index == -1:
            similar_txt_array.append(mark.replace(_, '.?'))
        else:
            similar_txt_array.append(mark.replace(_, '.?.?'))
    for para in para_array:
        word_index = 0
        para_index += 1
        for similar_txt in similar_txt_array:
            find_txt_array = re.findall(similar_txt, para)
            if find_txt_array:
                for find_txt in find_txt_array:
                    sentence_array = para.split(find_txt)
                    for sentence in sentence_array:
                        try:
                            word_index += len(sentence)
                            tag_index += 1
                            text_component.tag_add(f'tag_{tag_index}', f'{para_index}.{word_index}', f'{para_index}.{word_index + len(find_txt)}')
                            text_component.tag_config(f'tag_{tag_index}', foreground='white', background=type_highlight_color)
                            word_index += len(find_txt)
                        except Exception as e:
                            print('Error Code 0_102', e)


# 校验未被使用的附图标记
def check_text_figmarks_unused(active_textcomponent,text_figmark,type_highlight_color):
    fig_dic = {}
    all_marks = text_figmark.get('1.0', 'end').replace('；', ';').replace('	', ' ').strip('\n。 ')
    #reset_tags(text_figmark)
    figmarks_array = split_marks(all_marks)
    all_txt = active_textcomponent.get('1.0', 'end')
    for _ in figmarks_array:
        fig_num, fig_text = judge_mark(_)
        fig_dic[fig_num] = fig_text
    mark_index = 0
    for _ in fig_dic:
        mark_index += 1
        item = fig_dic[_]
        if item not in all_txt:
            text_figmark.tag_add(f'tag_{mark_index}', f'{mark_index}.0', f'{mark_index}.{len(_) + len(item) + 1}')
            text_figmark.tag_config(f'tag_{mark_index}', foreground='white', background=type_highlight_color)


def chat_insert_txt(in_txt,active_textcomponent,time_limit):# 将in_txt拆分 并间隔随机时间输入至text_component
    def chat_insert_txt_t():
        in_txt_array = re.split('，| ',in_txt)
        for _sen in in_txt_array:
            time.sleep(random.uniform(0.1, time_limit))
            if in_txt_array.index(_sen) == len(in_txt_array) - 1:
                active_textcomponent.insert('insert',_sen)
            else:
                active_textcomponent.insert('insert',_sen + '，')
            active_textcomponent.see('end')
    t1 = Thread(target=chat_insert_txt_t)
    t1.start()
    
def chat_insert_txt_by_word(in_txt,text_component,time_limit):# 将in_txt拆分 并间隔随机时间输入至text_component
    def chat_insert_txt_t():
        in_txt_array = list(in_txt)
        for _ in in_txt_array:
            time.sleep(random.uniform(0.1, time_limit))
            text_component.insert('insert',_)
            text_component.see('end')
    t1 = Thread(target=chat_insert_txt_t)
    t1.start()


def refine_ai_claim(in_txt):
    out_txt= ''
    temp_array = []
    in_array = in_txt.split('其特征在于')
    for index,_ in enumerate(in_array):
        if index == 0:
            out_txt += f'{_}其特征在于'
        else:
            out_txt += _
    if '。' in out_txt:
        return out_txt.split('。')[0]+'。'
    elif '、' in out_txt:
        in_txt = out_txt
        out_txt = ''
        in_array = re.split('、',in_txt)
        for _ in in_array:
            if _ not in temp_array:
                temp_array.append(_)
                out_txt += f'{_}、'
        return out_txt.replace('，；','；')
    else:
        in_txt = out_txt
        out_txt = ''
        in_array = re.split('；|\.|\n',in_txt)
        for _ in in_array:
            out_txt += f'{_}；'
        return out_txt.replace('，；','；')


def refine_ai_others(in_txt):
    out_txt= ''
    in_array = re.split('；|\.|。|\n',in_txt)
    for _ in in_array:
        out_txt += f'{_}；'
    return out_txt.replace('，；','；')

       
        
def refine_mutilines(in_txt):
    # 删除OCR识别的多余内容
    all_txt_array = in_txt.replace('\r','').replace('\u2029','\n').split('\n')
    all_txt = ''
    for _ in all_txt_array:
        del_txt = re.findall('\d.*?说 明 书.*?页',_,re.S) + re.findall('CCNN|CN.*?页',_,re.S)# re.findall('\d.*?/.*?页',_) 
        if del_txt:
            _ = _.replace(del_txt[0],'')
        if not _:
            continue
        if _[-1] == '。':
            all_txt += (_ + '\n')
        else:
            all_txt += _
    # 说明书分段
    all_txt = all_txt.replace('。[','。\n[').replace(' .','. ')
    for _ in ['技术领域','背景技术','发明内容','实用新型内容','附图说明','具体实施方式']:
        all_txt = all_txt.replace(f'{_}[',f'{_}\n[').replace(f'{_}',f'{_}\n')
    # 权利要求换行
    for i in range(1,50):
        all_txt = all_txt.replace(f'。{i}.',f'。\n{i}.')
    all_txt = all_txt.replace('技术领域\n','\n技术领域\n').replace('技术领域\n，','技术领域，').replace('\n技术领域\n。','技术领域。').replace('\n技术领域，','技术领域，').replace('；[','；\n[').replace('：[','；\n[').replace('\n\n','\n')
    
    return all_txt


# 获取所有附图标记
def get_mark_nums(in_txt): 
    part_array = re.findall('（.*?）',in_txt)
    part_array = list(set(part_array))
    part_array.sort()
    return part_array

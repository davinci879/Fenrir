# -*- coding: utf-8 -*-
"""
Fenrir resource 工具函数库
优化：预编译正则、修复边遍历边删除、修复 range 误用、去掉未用 import。
"""
import re
import time
import random
from threading import Thread

# ============ 预编译正则（提速） ============
_RE_SPLIT_MARKS = re.compile(r'\u2029|\r|\t|\n')
_RE_SEMI = re.compile(r';|；')
_RE_DUNDOU = re.compile(r'、|，|,')
_RE_NUM_PREFIX = re.compile(r'^(\d{1,3}[a-zA-Z]?)')
_RE_PARANUM = re.compile(r'\[\d{1,4}\]')
_RE_CHAPTER = re.compile(r'(技术领域|背景技术|发明内容|实用新型内容|附图说明|具体实施方式)')
_RE_CLAIM_REF = re.compile(r'根据权利要求\s*([\d、或至]+)\s*所述')


def judge_dot(intxt):
    """判断文本是否含句读标点"""
    return 1 if any(c in intxt for c in '，。；：？！') else 0


def refine_array(in_array, type=''):
    """去空字符串去重"""
    if type == 'set':
        in_array = list(set(in_array))
    return [x for x in in_array if x not in ('', ' ')]


def judge_mark(text):
    """从 '1壳体' 拆分出 (标号, 名称)。标号开头连续数字+字母。"""
    text = text.replace(' ', '').replace('\n', '\u2029').strip('\r\n\t\u2029')
    m = _RE_NUM_PREFIX.match(text)
    if m:
        return m.group(1), text[m.end():]
    return '', text


def split_marks(all_marks):
    """把标记文本按行/分号/顿号拆分，输出 ['1 壳体', '2 电机'] 列表"""
    if not all_marks:
        return []
    temp = _RE_SPLIT_MARKS.split(all_marks.strip('\r\n\t\u2029'))
    out = []
    for mark1 in temp:
        if '；' in mark1 or ';' in mark1:
            for mark2 in _RE_SEMI.split(mark1):
                if len(mark2.split('、')) > 2:
                    out += mark2.split('、')
                elif len(_RE_DUNDOU.split(mark2)) > 2:
                    out += _RE_DUNDOU.split(mark2)
                else:
                    out.append(mark2.replace('、', ''))
        else:
            out += _RE_DUNDOU.split(mark1)
    # 补空格
    result = []
    for item in out:
        num, name = judge_mark(item.replace(' ', ''))
        if num or name:
            result.append(f'{num} {name}')
    # 去重排序
    return sorted(set(x for x in result if x.strip()))


def split_marks_bysort(all_marks):
    """按标号位数排序输出"""
    if not all_marks:
        return []
    temp = _RE_SPLIT_MARKS.split(all_marks.strip('\r\n\t\u2029'))
    out = []
    for mark1 in temp:
        if '；' in mark1:
            for mark2 in _RE_SEMI.split(mark1):
                if len(mark2.split('、')) > 2:
                    out += mark2.split('、')
                elif len(_RE_DUNDOU.split(mark2)) > 2:
                    out += _RE_DUNDOU.split(mark2)
                else:
                    out.append(mark2.replace('、', ''))
        else:
            out += _RE_DUNDOU.split(mark1)
    # 去空
    out = [x for x in (item.strip() for item in out) if x]
    out = sorted(set(out))
    # 按标号长度分组排序
    result = []
    for i in range(1, 6):  # 标号最多5位
        for item in out:
            num, name = judge_mark(item.replace(' ', ''))
            if len(num) == i or len(num.strip('abcdefghijklmnopqrstuvwxyz')) == i:
                result.append(f'{num} {name}'.strip('，。,；;'))
    return result


def para_refine(txt):
    """按段落拆分，过滤<=5字的短段（修复边遍历边删除漏元素）"""
    txt_array = txt.replace('\n', '\u2029').split('\u2029')
    return [x for x in txt_array if len(x) > 5]


def refine_txt(text, del_array):
    for d in del_array:
        text = text.replace(d, '')
    return text


def list_join(a, b):
    return [f'<{i+1:02d}> {a[i]} {b[i]}' for i in range(len(a))]


def list_join_1(a):
    return [f'{i+1}.{x}' for i, x in enumerate(a)]


def start_logo():
    try:
        with open('./data/logo.txt', 'r', encoding='utf-8') as f:
            print(f.read())
    except Exception:
        pass


def handlerAdaptor(fun, **kwds):
    return lambda event, fun=fun, kwds=kwds: fun(event, **kwds)


def refine_intxt(intxt):
    """统一标点，去掉'图N'"""
    intxt = (intxt.replace('（', '(').replace('）', ')')
                  .replace('：', ':').replace('，', ',').replace('；', ';')
                  .replace('\r', '').replace('\n', ''))
    for i in range(1, 100):
        intxt = intxt.replace(f'图{i}', '')
    num_arr = '一二三四五六七八九十'
    for i in range(1, 10):
        for item in '个第':
            intxt = intxt.replace(f'{item}{i}', f'{item}{num_arr[i-1]}')
            intxt = intxt.replace(f'{i}{item}', f'{num_arr[i-1]}{item}')
    return intxt


# ============ 提取附图标记名称 ============
_SPLIT_WORDS = ('于', '，', '有', '个', '组', '为', '的', '包括', '固定')
_STRIP_CHARS = '着在于包括有与和以及均（）1234567890，。；：\u2029\r\t '

def search_marks(intxt):
    """从文本提取可能的部件名称。优化：用一次正则批量提取，替代原来的循环+逐词 findall。"""
    intxt = (intxt.replace('(', '（').replace(')', '）')
                  .replace(',', '，').replace(';', '；').replace(':', '：')
                  .replace('-', '').replace('—', '').replace('：', '').replace('为', ''))
    # 一次性提取所有 "X（数字" 中间的中文片段
    all_array = re.findall(r'[\u4e00-\u9fa5]{2,15}(?=（\d)', intxt)
    # 清洗
    cleaned = []
    for item in all_array:
        # 取最后一个截词符之后的部分
        for sw in _SPLIT_WORDS:
            if sw in item:
                item = item.split(sw)[-1]
        item = item.strip(_STRIP_CHARS)
        # 去掉方位词
        for fw in ('上部', '下部', '外部', '内部', '侧部', '顶部', '底部',
                   '权利要求', '其特征', '所述'):
            item = item.replace(fw, '')
        if 2 <= len(item) <= 15:
            cleaned.append(item)
    cleaned = refine_array(cleaned, 'set')
    # 去掉被更长名称包含的短名称
    cleaned.sort(key=len, reverse=True)
    result = []
    for long_name in cleaned:
        if not any(long_name != short and short in long_name and len(short) >= 2 for short in result):
            result.append(long_name)
    return sorted(result, key=len)


def completion_nums(rep_type, all_marks, new_txt):
    """补全标号 type1/2。修复 for i in (0, len-1) 误用为 range。"""
    figmarks_array = split_marks(all_marks)
    all_key_array = [judge_mark(item)[1] for item in figmarks_array]
    # 找包含关系
    repeat_array, add_array = [], []
    for w1 in sorted(all_key_array, key=len, reverse=True):
        for w2 in all_key_array:
            if w1 != w2 and w2 in w1:
                repeat_array.append(w2)
                add_array.append(w1)
    item_lack_array = []
    for item in figmarks_array:
        num, mark = judge_mark(item)
        suffix = f'({num})' if rep_type == 1 else num
        if mark not in repeat_array:
            new_txt = new_txt.replace(mark, mark + suffix)
        else:
            new_txt = new_txt.replace(mark, mark + suffix)
            for i, rep in enumerate(repeat_array):
                if rep == mark:
                    new_txt = new_txt.replace(
                        add_array[i].replace(mark, mark + suffix), add_array[i])
        if mark not in new_txt:
            item_lack_array.append(f'{num} {mark}')
    return new_txt, repeat_array, item_lack_array


def completion_marks(rep_type, all_marks, new_txt):
    """补全名称 type3/4"""
    figmarks_array = split_marks(all_marks)
    num_array = [judge_mark(item)[0] for item in figmarks_array]
    mark_array = [judge_mark(item)[1] for item in figmarks_array]
    # 长标号先替换，避免短标号误匹配
    for length in (5, 4, 3, 2, 1):
        for i, num in enumerate(num_array):
            if len(num) == length:
                new_txt = new_txt.replace(num, mark_array[i])
                new_txt = new_txt.replace(mark_array[i] + '.', num + '.')
                new_txt = new_txt.replace('权利要求' + mark_array[i], '权利要求' + num)
                if length == 1:
                    new_txt = new_txt.replace('\n' + mark_array[i], '\n' + num)
                    new_txt = new_txt.replace('-' + mark_array[i], '-' + num)
    # 找包含关系
    all_key_array = mark_array
    repeat_array, add_array = [], []
    for w1 in sorted(all_key_array, key=len, reverse=True):
        for w2 in all_key_array:
            if w1 != w2 and w2 in w1:
                repeat_array.append(w2)
                add_array.append(w1)
    item_lack_array = []
    for item in figmarks_array:
        num, mark = judge_mark(item)
        suffix = f'({num})' if rep_type == 1 else num
        new_txt = new_txt.replace(mark, mark + suffix)
        if mark in repeat_array:
            for i, rep in enumerate(repeat_array):
                if rep == mark:
                    new_txt = new_txt.replace(
                        add_array[i].replace(mark, mark + suffix), add_array[i])
        if mark not in new_txt:
            item_lack_array.append(f'{num} {mark}')
    return new_txt, repeat_array, item_lack_array


def delete_bracketmarks_mohu(intxt):
    """模糊删除所有括号内容"""
    intxt = intxt.replace('(', '（').replace(')', '）')
    for item in re.findall(r'（.*?）', intxt):
        intxt = intxt.replace(item, '')
    return intxt


def delete_bracketmarks(intxt, all_marks):
    """删除指定标记的括号标号"""
    figmarks_array = split_marks(all_marks)
    intxt = intxt.replace('(', '（').replace(')', '）')
    for item in figmarks_array:
        num, mark = judge_mark(item)
        for hit in re.findall(mark + r'（.*?）', intxt):
            intxt = intxt.replace(hit, mark)
    return intxt


def get_figmarks(in_array, intxt):
    """根据名称找标号。优化：预编译 word 列表。"""
    # 删段号
    for p in _RE_PARANUM.findall(intxt):
        intxt = intxt.replace(p, '')
    words = [r'\d{4}[a-z]', r'\d{3}[a-z]', r'\d{4}', r'\d{2}[a-z]',
             r'\d{3}', r'\d{2}', r'\d[a-z]', r'\d', r'[a-z]']
    found = []
    for item in in_array:
        for w in words:
            try:
                hits = re.findall(rf'{item}({w})', intxt)
                hits += re.findall(rf'{item}（({w})）', intxt)
                if hits and hits[0][0] != '0':
                    found.append(f'{hits[0]}{item}')
                    break
            except Exception:
                pass
    found = sorted(set(found))
    num_array, mark_array = [], []
    same_marks_array = []
    for item in found:
        num, name = judge_mark(item)
        if num and name:
            if num in num_array or name in mark_array:
                same_marks_array.append(f'{num} {name}')
            num_array.append(num)
            mark_array.append(name)
    out = sorted(set(f'{n} {m}' for n, m in zip(num_array, mark_array)))
    return out, same_marks_array


def arrenge_document(txt):
    """统一单位/标点"""
    ori = ["X型", "S型", "A型", "C型", "L型", "V型", " ", ".根据", ".一种",
           "1次", "2次", "3次", "4次", "5次", "6次", "7次", "8次", "9次", "10次",
           "1个", "2个", "3个", "4个", "5个", "6个", "7个", "8个", "9个", "10个",
           ":", ";", ",,", "。。", "，，", "、、", "；；", "？？", "““", "””", "：：",
           ";;", "::", "..", "摄氏度", "°C", "毫升", "微升",
           "毫米", "分米", "厘米", "纳米", "微米", "米", "英尺", "英寸",
           "千帕", "兆帕", "千克", "毫克", "微克", "KG",
           "小时", "分钟", "毫秒", "微秒", "秒",
           "；图1", "；图2", "；图3", "；图4", "；图5", "；图6", "；图7", "；图8", "；图9", "；图10",
           "1 ", "2 ", "3 ", "4 ", "5 ", "6 ", "7 ", "8 ", "9 ", "10 ",
           "实用新型人", "每个", '\n\n']
    rep = ["X形", "S形", "A形", "C形", "L形", "V形", "", ". 根据", ". 一种",
           "一次", "两次", "三次", "四次", "五次", "六次", "七次", "八次", "九次", "十次",
           "一个", "两个", "三个", "四个", "五个", "六个", "七个", "八个", "九个", "十个",
           "：", "；", ",", "。", "，", "、", "；", "？", "“", "”", "：",
           ";", ":", ".", "℃", "℃", "ml", "μl",
           "mm", "dm", "cm", "nm", "μm", "m", "ft", "in",
           "kPa", "mPa", "kg", "mg", "μg", "kg",
           "h", "min", "ms", "μs", "s",
           "浓度", "照度", "光度", "碳纳米管", "升降", "抬升", "升压",
           "；\n图1", "；\n图2", "；\n图3", "；\n图4", "；\n图5", "；\n图6", "；\n图7", "；\n图8", "；\n图9", "；\n图10",
           "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
           "发明人", "各", '\n']
    for i, item in enumerate(ori):
        txt = txt.replace(item, rep[i])
    return txt


# 元素符号对照表（预生成 dict，避免四重循环）
_ELEMENT_MAP = {
    '氢': 'H', '氦': 'He', '锂': 'Li', '铍': 'Be', '硼': 'B', '碳': 'C', '氮': 'N',
    '氧': 'O', '氟': 'F', '氖': 'Ne', '钠': 'Na', '镁': 'Mg', '铝': 'Al', '硅': 'Si',
    '磷': 'P', '硫': 'S', '氯': 'Cl', '氩': 'Ar', '钾': 'K', '钙': 'Ca', '钪': 'Sc',
    '钛': 'Ti', '钒': 'V', '铬': 'Cr', '锰': 'Mn', '铁': 'Fe', '钴': 'Co', '镍': 'Ni',
    '铜': 'Cu', '锌': 'Zn', '镓': 'Ga', '锗': 'Ge', '砷': 'As', '硒': 'Se', '溴': 'Br',
    '氪': 'Kr', '铷': 'Rb', '锶': 'Sr', '锆': 'Zr', '铌': 'Nb', '钼': 'Mo', '锝': 'Tc',
    '钌': 'Ru', '铑': 'Rh', '钯': 'Pd', '银': 'Ag', '镉': 'Cd', '铟': 'In', '锡': 'Sn',
    '锑': 'Sb', '碲': 'Te', '氙': 'Xe', '铯': 'Cs', '钡': 'Ba', '钨': 'W', '铪': 'Hf',
    '钽': 'Ta', '铼': 'Re', '锇': 'Os', '铱': 'Ir', '铂': 'Pt', '金': 'Au', '汞': 'Hg',
    '铊': 'Tl', '铅': 'Pb', '铋': 'Bi', '钋': 'Po', '砹': 'At', '氡': 'Rn', '钫': 'Fr', '镭': 'Ra'
}
_NUM_CN = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
           '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十']

def rep_elements(intxt):
    """把 'A化B' 中文元素名替换为元素符号。优化：dict 查找替代四重循环。"""
    # 先替换 "十X" 等复合数字+元素
    for cn_num, i in zip(_NUM_CN[1:], range(1, 21)):
        for cn_e, en_e in _ELEMENT_MAP.items():
            # "二氧化硅" → 处理"二氧"→O2 等
            intxt = intxt.replace(f'{cn_num}{cn_e}化', f'{en_e}{i}')
    # "X化Y" → Y_X
    for cn1, en1 in _ELEMENT_MAP.items():
        for cn2, en2 in _ELEMENT_MAP.items():
            if cn1 != cn2:
                intxt = intxt.replace(f'{cn1}化{cn2}', f'{en2}{en1}')
    return intxt



def get_claimtree(all_forepart_array):
    """生成权利要求引用树。优化：while True 加循环上限防死循环。"""
    claim_tree_dic = {}
    for idx, forepart in enumerate(all_forepart_array):
        claim_index = idx + 1
        if claim_index == 1:
            claim_tree_dic[str(claim_index)] = '0'
            continue
        # 展开 "N至M"
        if '至' in forepart:
            m = re.search(r'(\d+)\s*至\s*(\d+)', forepart)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                forepart = '或'.join(str(i) for i in range(a, b + 1))
        # 提取所有数字
        fore_nums = [str(n) for n in re.findall(r'\d+', forepart)]
        claim_tree_dic[str(claim_index)] = ' '.join(fore_nums)
    # 拆边
    edges = []
    for cnum, ref in claim_tree_dic.items():
        for r in ref.split(' '):
            if r == '0' or not r:
                continue
            a, b = (r, cnum) if int(r) < int(cnum) else (cnum, r)
            edges.append(f'{a} {b}')
    edges = list(set(edges))
    # 传递闭包（最多20轮）
    for _ in range(20):
        before = len(edges)
        new_edges = []
        for e1 in edges:
            for e2 in edges:
                if e1.split(' ')[-1] == e2.split(' ')[0]:
                    combo = f'{e1} {e2.split(" ")[1]}'
                    if combo not in edges:
                        new_edges.append(combo)
        edges += new_edges
        if len(edges) == before:
            break
    # 筛叶子路径
    result = []
    for e1 in edges:
        if e1.split(' ')[0] != '1':
            continue
        if not any(e1 != e2 and e1 in e2 for e2 in edges):
            path = sorted(set(e1.split(' ')), key=int)
            result.append('=>'.join(path))
    result.sort(key=lambda x: int(x.split('=>')[-1]))
    return result


def get_similar_markindex(all_txt, mark, text_component, type_highlight_color):
    """Tkinter 语法保留（PyQt 中不调用）"""
    return


def check_text_figmarks_unused(active_textcomponent, text_figmark, type_highlight_color):
    """Tkinter 语法保留"""
    return



def refine_ai_claim(in_txt):
    if '其特征在于' in in_txt:
        pre, feat = in_txt.split('其特征在于', 1)
        out = pre + '其特征在于' + feat
    else:
        out = in_txt
    if '。' in out:
        return out.split('。')[0] + '。'
    parts = []
    for p in re.split(r'、|；|\.|\n', out):
        p = p.strip()
        if p and p not in parts:
            parts.append(p)
    return '、'.join(parts) + '。'


def refine_ai_others(in_txt):
    parts = [p.strip() for p in re.split(r'；|\.|。|\n', in_txt) if p.strip()]
    return '；'.join(parts) + '；'


def refine_mutilines(in_txt):
    """OCR 文本分段整理"""
    lines = re.split(r'\r|\n|\t|\u2029', in_txt.strip('\r\n\t\u2029'))
    out = ''
    for line in lines:
        # 删页眉页脚
        for bad in re.findall(r'\d.*?说\s*明\s*书.*?页', line) + re.findall(r'CCNN|CN.*?页', line):
            line = line.replace(bad, '')
        if not line:
            continue
        out += line + ('\u2029' if line[-1] == '。' else '')
    out = out.replace('。[', '。\u2029[').replace(' .', '. ')
    for ch in ('技术领域', '背景技术', '发明内容', '实用新型内容', '附图说明', '具体实施方式'):
        out = out.replace(f'{ch}[', f'{ch}\u2029[').replace(ch, f'{ch}\u2029')
    for i in range(1, 50):
        out = out.replace(f'。{i}.', f'。\u2029{i}.')
    out = out.replace('；[', '；\u2029[').replace('：[', '；\u2029[')
    while '\u2029\u2029' in out:
        out = out.replace('\u2029\u2029', '\u2029')
    return out


def get_mark_nums(in_txt):
    """提取所有括号内容"""
    return sorted(set(re.findall(r'（.*?）', in_txt)))

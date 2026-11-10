#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设计调整服务进程内托管（已完全内联，无外部文件依赖）。

功能：调整外观图（六视图尺寸/PPI）/ 附图标注（编辑图片）/ XML修改（ZIP+XML）
      / 特征关系分析（EUREKA 3D 气泡蛛网图）。
实现：HTTP Handler + 特征关系解析 + index.html 前端全部内置为本模块资源，
      在守护线程里运行 ThreadingHTTPServer，生命周期与 Qt 应用一致，
      并支持端口占用时复用/顺延。

对外接口：
    ensure_started()          -> (ok: bool, message: str)  幂等，可重复调用
    tab_url(n, host=None)     -> 'http://127.0.0.1:<port>/?tab=n'
    lan_url(n=None)           -> 局域网可访问的地址
    state()                   -> 状态字典
    stop()                    -> 仅关闭本进程启动的服务；复用外部服务时不碰它
"""

import io
import os
import json
import base64
import struct
import threading
import uuid
import time
import traceback
import socket
import zipfile
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, quote
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

# design_adjust_service.py 位于 src/，项目根目录是其父目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------- 特征关系分析（原 relations.py） ----------------
# 目标：宁可多识别，也不要把「本来有关系的两个特征」漏掉——蛛网图是给人看结构用的，
# 漏边比多边更糟。所以分四层识别：
#   L0 断句：句号/分号/问号/换行 + 权项编号 + 「此外/同时/并且…」这类分句引导词；
#   L1 模板：名称（可带附图标记）跑 包含 / 组成 / 设置 / 位置 / 连接 / 固定方式 /
#      驱动 / 上下位 / 从属 / 并列 模板；
#   L2 无标号兜底：全篇几乎没有附图标记时，改用「技术名词词尾」提取特征，跑同一套模板；
#   L3 同句共现兜底：一句话里出现多个特征却没有任何动词，按出现顺序连成「相关」链；
#   L4 上下位推断：显式句式（为/是/属于/构成/一种/组成部分/均为…）+ 类别词兜底。
# 每条边带 kind 字段（contain / connect / fix / position / drive / hyponym / depend /
# sibling / related），前端按类别着色，图例里能直接看出关系分布。

# ---- 包含 / 组成 ----
_CONTAIN_WORDS = [
    '进一步包括', '还包括', '包括', '包含', '具有', '带有', '具备', '含有',
    '设有', '设置有', '配置有', '安装有', '固定有', '连接有', '内置有', '形成有',
    '开设有', '加工有', '集成有', '装配有', '安设有', '装设有', '架设有', '挂设有',
    '镶嵌有', '嵌装有', '嵌设有', '焊接有', '粘接有', '铆接有', '夹持有',
    '填充有', '收容有', '容纳有', '布设有', '布置有', '排布有', '涂覆有',
    '镀设有', '套设有', '穿设有', '叠设有', '层叠有', '延伸有', '凸设有',
]
# ---- 位置 / 装配动词（长词在前，「固定于」不会被「固定」截胡）----
POS_WORDS = [
    '可转动地设置于', '可滑动地设置于', '可活动地设置于', '可拆卸地设置于',
    '可翻转地设置于', '可升降地设置于', '固定连接于', '固定安装于',
    '设置于', '设置在', '安装于', '安装在', '固定于', '固定在', '固设于', '固设在',
    '嵌设于', '嵌设在', '嵌装于', '镶嵌于', '埋设于', '装设于', '装设在',
    '布置于', '布置在', '布设于', '布设在', '排布于', '设于', '设在',
    '位于', '内置于', '内置在', '收容于', '容纳于', '容置于', '装配于', '装配在',
    '伸入至', '伸入', '伸出于', '伸出', '延伸至', '延伸到', '穿过', '穿设于',
    '穿设在', '套设于', '套设在', '套装于', '套接于', '压装于', '卡装于',
    '插装于', '插接于', '插入', '接入', '连通于', '连通至', '连通到',
    '抵靠于', '抵接于', '贴合于', '贴设于', '贴附于', '覆设于', '包覆于',
    '缠绕于', '绕设于', '绕设', '悬挂于', '悬设于', '悬置于', '垂设于',
    '开设于', '开设在', '加工于', '连接于', '联接于', '转动连接于',
    '相邻于', '邻近于', '靠近', '朝向', '正对于', '对应设置', '相对设置',
    '对称设置', '平齐设置', '层叠设置', '并排设置',
]
# ---- 连接 / 固定方式（关系名即文中动词，连线上能直接读到「螺栓连接」）----
CONNECT_WORDS = [
    '可拆卸固定连接', '可拆卸地连接', '可拆卸连接', '可转动地连接', '可滑动地连接',
    '可翻转地连接', '可调节地连接', '可分离地连接',
    '螺栓固定连接', '螺钉固定连接', '螺纹固定连接', '卡扣固定连接', '焊接固定连接',
    '粘接固定连接', '过盈配合连接', '销轴固定连接', '铆接固定连接', '一体成型连接',
    '固定连接', '螺栓连接', '螺钉连接', '螺丝连接', '螺接固定', '螺接', '螺纹连接',
    '螺纹旋合', '旋合', '螺合', '销轴连接', '销连接', '键连接', '花键连接',
    '卡扣连接', '卡接固定', '卡接', '卡合', '扣接', '铆钉连接', '铆接固定', '铆接',
    '铆合', '铆固', '焊接固定', '焊接', '焊固', '焊合', '熔接', '热熔',
    '粘接固定', '粘接', '黏接', '胶接', '胶粘', '铰接', '枢接', '枢设',
    '转动连接', '旋转连接', '滑动连接', '活动连接', '滚动连接', '柔性连接',
    '传动连接', '驱动连接', '联动连接', '动力连接', '控制连接', '电连接',
    '电气连接', '通信连接', '信号连接', '耦接', '密封连接', '插接配合', '插接固定',
    '插接', '压装配合', '压接', '压合', '压铆', '过盈配合', '过渡配合', '间隙配合',
    '滑动配合', '转动配合', '螺纹配合', '啮合配合', '啮合', '抱箍连接', '抱紧',
    '绑扎', '捆扎', '搭接', '拼接', '对接', '法兰连接', '螺纹装配',
    '套设', '套接', '抵接', '贴合', '连通', '相连通', '相连接', '相连', '连接',
    '联接', '接触', '固定', '紧固', '锁紧', '压紧', '夹紧', '夹持', '支撑', '支承',
    '承载', '抵靠', '穿设', '绕设', '缠绕', '密封', '一体成型', '一体设置',
    '一体相连', '连为一体', '一体注塑', '注塑成型', '模压成型', '冲压成型',
    '折弯成型', '挤压成型', '编织', '缝制',
]
# ---- 驱动 / 功能动词（「控制器3控制电机4」也算一种结构关系）----
DRIVE_WORDS = [
    '传动配合', '驱动配合', '驱动连接', '控制连接', '通信连接', '电性连接',
    '驱动', '带动', '推动', '拉动', '牵引', '联动', '控制', '调节', '调整',
    '检测', '采集', '感应', '识别', '测量', '监测', '采集数据',
    '传输', '输送', '传送', '传递', '传导', '导向', '限位', '止挡', '阻挡',
    '隔离', '隔开', '反馈', '供电', '充电',
    '显示', '指示', '报警', '提示', '存储', '运算', '处理', '转换', '整流',
    '逆变', '放大', '滤波', '调制', '加热', '冷却', '散热', '风冷', '水冷',
    '润滑', '喷淋', '清洗', '吹扫', '抽吸', '吸取', '吸附', '抓取', '夹取',
    '顶升', '升降', '回转', '翻转', '平移', '横移', '驱动旋转',
]

_REL_WORDS = sorted(set(POS_WORDS + CONNECT_WORDS + DRIVE_WORDS),
                    key=lambda w: (-len(w), w))
_REL_RE = '|'.join(_REL_WORDS)
_POS_RE = '|'.join(sorted(set(POS_WORDS), key=lambda w: (-len(w), w)))
_CONTAIN_RE = '|'.join(sorted(set(_CONTAIN_WORDS), key=lambda w: (-len(w), w)))
# 通用动词（含「设有/设置有」这类存在动词）——位置/设置/连接/驱动一起匹配
_VERB_RE = '|'.join(sorted(set(POS_WORDS + _CONTAIN_WORDS + CONNECT_WORDS + DRIVE_WORDS),
                          key=lambda w: (-len(w), w)))

# 关系类别（前端按类别着色）
_KIND = {}
for _w in _CONTAIN_WORDS:
    _KIND[_w] = 'contain'
for _w in POS_WORDS:
    _KIND[_w] = 'position'
for _w in CONNECT_WORDS:
    _KIND[_w] = 'connect'
for _w in DRIVE_WORDS:
    _KIND[_w] = 'drive'
_FIX_HINTS = ('固定', '焊', '粘', '胶', '铆', '卡', '扣', '配合', '螺纹', '螺栓',
              '螺钉', '螺接', '销', '键', '一体', '穿设', '绕设', '缠绕', '夹',
              '绑扎', '捆扎', '抱', '熔')


def _kind(rel):
    """把关系词归到类别：固定/连接/位置/驱动/包含，其余归 related。
    组合关系名（「螺栓连接固定在」「软管51连通」）取其中最长的一个已知关系词来判断。"""
    k = _KIND.get(rel)
    if k is None:
        for w in _REL_WORDS:
            if w in rel:
                k = _KIND.get(w)
                if k:
                    break
    if k == 'connect' and any(h in rel for h in _FIX_HINTS):
        return 'fix'
    return k or 'related'


# 特征名称字符集：不能含数字（标号单独算），也不含连词/助词，
# 否则「驱动电机4的输出轴」会被并成一个词、「输出轴与切刀22」会被当成一个特征。
_NAME_BAD = '与和及或的在为由把将被从对于是之其所该各并则即又再有等了着过'
_NAME_CHAR = r'(?!\d)(?![%s])[\u4e00-\u9fa5A-Za-z]' % _NAME_BAD
_NAME = r'(?:%s){1,12}' % _NAME_CHAR
_FEAT = _NAME + r'\d{1,3}'

# 无标号模式的技术名词词尾：只保留以这些词收尾的候选，避免把「通过」「设置」当特征
_HEAD_NOUNS = [
    '组件', '装置', '设备', '系统', '机构', '单元', '模块', '结构', '总成', '本体',
    '主体', '主体部', '基座', '底座', '机架', '机壳', '外壳', '壳体', '箱体', '柜体',
    '框架', '支架', '支座', '安装座', '固定座', '面板', '盖板', '底板', '顶板', '侧板',
    '隔板', '挡板', '支撑板', '连接板', '安装板', '基板', '齿条', '蜗杆', '蜗轮',
    '导轨', '滑块', '丝杠', '轴承', '皮带', '链条', '滚轮', '密封圈', '密封件',
    '垫圈', '垫片', '螺栓', '螺钉', '螺母', '铆钉', '铰链', '转轴', '曲轴', '凸轮轴',
    '连杆', '活塞', '活塞杆', '气缸', '液压缸', '喷嘴', '喷头', '滤网', '滤芯', '风扇', '散热片',
    '加热器', '制冷器', '换热器', '冷凝器', '蒸发器', '电机', '马达', '发电机', '电池',
    '电源', '光源', '镜头', '镜片', '传感器', '控制器', '处理器', '存储器', '芯片',
    '电路板', '显示屏', '屏幕', '按键', '开关', '接口', '接头', '管道', '软管', '阀门',
    '线束', '夹具', '刀具', '切刀', '刀片', '刀头', '焊枪', '电极', '托盘', '传送带',
    '辊筒', '手轮', '把手', '手柄', '旋钮', '卡扣', '卡槽', '滑槽', '导槽', '限位件',
    '限位块', '限位面', '定位件', '定位销', '定位孔', '定位槽', '凸起', '凸台', '凹槽',
    '凹坑', '缺口', '通孔', '盲孔', '螺纹孔', '安装孔', '过孔', '穿孔', '法兰盘',
    '法兰', '连接件', '紧固件', '支撑件', '固定件', '安装件', '驱动件', '传动件',
    '检测件', '端盖', '端面', '端部', '内腔', '外壁', '内壁', '输出轴', '输入轴',
    '连接轴', '传动轴', '主动轮', '从动轮', '同步带', '张紧轮', '叶轮', '轴套',
    '轴座', '轴承座', '管体', '导管', '支管', '主管', '连接管', '换热管', '翅片',
    '散热器', '加热片', '发热体', '电热丝', '电极片', '触点', '导电件', '绝缘件',
    '导线', '电缆', '插头', '插座', '连接器', '端子', '指示灯', '显示件', '控制板',
    '主板', '线路', '横梁', '纵梁', '立柱', '横杆', '支腿', '脚轮', '万向轮', '拉杆',
    '推杆', '拨杆', '滑杆', '导向杆', '导向柱', '导向件', '筒体', '圆盘', '圆环',
    '弹簧', '弹片', '齿轮', '滚珠', '膜层', '涂层', '面层', '层板', '隔膜', '锁舌',
    '锁芯', '锁扣', '卡钩', '挂钩', '舌', '门锁', '锁具', '锁体', '指纹模块',
    '阀体', '阀芯', '泵体', '泵盖', '机柜', '基台', '工作台', '台面', '机座',
    '减速箱', '变速箱', '联轴器', '离合器', '制动器', '伺服电机', '步进电机',
    '臂', '桨叶', '桨毂', '轮毂', '定子', '转子', '磁钢', '线圈', '绕组', '铁芯',
    '电芯', '电池仓', '安装槽', '凸缘', '台阶', '轴承盖', '油封', '密封垫',
    '挡圈', '卡簧', '导向套', '压板', '压块', '法兰轴', '齿圈', '蜗轮蜗杆',
    '驱动电机', '真空泵', '离心泵', '隔膜泵', '油缸', '气泵', '压缩机', '压缩机',
    '传送机构', '输送带', '输送辊', '输送机构', '导向轨', '滑轨', '轨道', '轨道组件',
    '安装架', '支撑架', '连接架', '固定架', '底架', '机架体', '外壳体', '内壳',
    '铭牌', '标签', '贴片', '插件', '座体', '壳体部', '安装部', '连接部', '固定部',
    '容置腔', '容纳腔', '安装腔', '空腔', '开口', '开口部', '收容腔', '通道',
    '壁', '板', '轴', '套', '环', '片', '块', '条', '带', '线', '管', '杆', '柱',
    '销', '孔', '槽', '腔', '口', '面', '轮', '泵', '阀', '灯', '针', '层',
    '膜', '箱', '盖', '门', '窗', '盘', '筒', '件', '体',
]
_HEAD_SET = set(_HEAD_NOUNS)
# 首字 → 头名词列表（长的在前）：纯 Python 扫名词短语，比 400 项正则交替快两个数量级
_HEAD_BY_FIRST = {}
for _h in _HEAD_SET:
    _HEAD_BY_FIRST.setdefault(_h[0], []).append(_h)
for _k in _HEAD_BY_FIRST:
    _HEAD_BY_FIRST[_k].sort(key=len, reverse=True)
_NAME_CHAR_RE = re.compile('^(?:%s)$' % _NAME_CHAR)


def _plain_spans(seg):
    """扫出句子里所有「技术名词短语」的区间：先定位词尾名词，再向左扩展到最多 10 个字符。
    返回 [(start, end), ...]，长的优先、互不重叠。"""
    hits = []
    n = len(seg)
    prev_end = 0
    for i in range(n):
        if i < prev_end:
            continue
        cands = _HEAD_BY_FIRST.get(seg[i])
        if not cands:
            continue
        for h in cands:
            if seg.startswith(h, i):
                # 单字头名词若紧跟另一个名词（「线」+「腔」），说明它只是长词的一部分
                if len(h) == 1 and any(seg.startswith(h2, i + 1) for h2 in _HEAD_BY_FIRST.get(seg[i + 1:i + 2], ())):
                    break
                j, ext = i, 0
                while j > prev_end and ext < 10 and _NAME_CHAR_RE.match(seg[j - 1]):
                    j -= 1
                    ext += 1
                hits.append((j, i + len(h)))
                prev_end = i + len(h)
                break
    if not hits:
        return []
    hits.sort(key=lambda ab: (ab[0] - ab[1], ab[0]))       # 长的优先
    keep = []
    for a, b in hits:
        if all(b <= ka or a >= kb for ka, kb in keep):
            keep.append((a, b))
    keep.sort()
    return keep


def _tok_for(names):
    """按本句实际出现的名词短语构造 token（字面量交替），编译快、匹配准。"""
    lits = sorted(set(names), key=lambda x: (-len(x), x))
    inner = '|'.join(re.escape(x) for x in lits)
    if inner:
        return r'(?:所述|上述|该|对应的|相应的)?(?:%s|%s)' % (_FEAT, inner)
    return r'(?:所述|上述|该|对应的|相应的)?(?:%s)' % _FEAT

_HEAD_RE = '|'.join(sorted(_HEAD_SET, key=lambda w: (-len(w), w)))
# 名称模式：最多 10 个字符的前缀 + 技术名词词尾
_PLAIN = r'(?:%s){0,10}?(?:%s)' % (_NAME_CHAR, _HEAD_RE)
# 混合模式：带标号特征 或 技术名词词尾（上下位句子里常常一半带号一半不带）
_MIX = r'(?:%s|%s)' % (_FEAT, _PLAIN)
# 模板里用的 token：允许「所述/上述/该」这类指代前缀（「所述减速箱4、所述输出法兰5」）
# 模板 token 由 _tok_for(本句名词) 动态生成，不再用全局大正则（编译太慢）
# 类别词：以这些词收尾的基本都是「上位概念」，用于上下位推断
_SUPER_WORDS = ('部件', '零件', '元件', '构件', '器件', '组件', '装置', '机构',
                '单元', '模块', '系统', '结构', '设备', '总成', '材料', '部件组')
# 无标号候选里常被「通过/采用」这类虚动词串在一起：「锁体通过卡扣」→「卡扣」
_PLAIN_GLUE = ('通过', '经由', '经过', '采用', '利用', '借助', '使用')

# 特征名称首尾不允许出现的「功能词」字符，用于裁剪出真实特征名。
# 注意：这里只能收「单字功能词」；多字的（本发明／本实用新型／其中／因此…）交给
# _LEAD_WORDS 前缀剥离，否则「锁体」「壳体」「具体」这类词会被误伤成「锁」「壳」。
_STOP_CHARS = set('通过与和及或的在为由了是所述其之各并从被将把以去到另外同然且者又再则即')
# 首部要剥掉的前缀词（按长度从长到短尝试）
_LEAD_WORDS = ('固定安装在', '固定连接在', '可转动地', '可滑动地', '可拆卸地',
               '可活动地', '可升降地', '固定在', '设置在', '安装在', '固定于',
               '设置于', '位于', '内置于', '固定', '设置', '安装',
               '本发明', '本实用新型', '一种', '一个', '一组', '一对', '上述',
               '其中', '所述', '该', '每个', '若干', '多个', '至少一个',
               '进一步', '优选', '具体地', '尤其是', '特别是', '另外', '此外',
               '同时', '并且', '而且', '然后', '接着', '此时', '也就是说')
# 「侧固定有X」「底部设有Y」这类前缀：方位词 + 存在动词，整段剥掉
_LEAD_VERB_RE = re.compile(
    r'^(?:(?:上|下|左|右|前|后|内|外|侧|底|顶|端|中)部?)?(?:还|进一步|分别|均)?'
    r'(?:包括|包含|具有|具备|带有|设有|设置有|配置有|安装有|固定有|连接有|开设有|'
    r'形成有|集成有|装配有|嵌设有|装设有|固定|安装|设置)')
_PLAIN_STOP = {'本发明', '本实用新型', '技术方案', '实施例', '附图', '图中', '权利要求',
               '上述', '其中', '因此', '并且', '或者', '以及', '同时', '然后', '此时',
               '此外', '另外', '而且', '接着', '进一步', '优选', '具体地'}
# 允许从特征名开头剥掉的动词（这些词基本不做零件名的开头）
_VERB_PREFIX = ('相连通', '相连接', '连通', '相连', '接触', '抵接', '抵靠', '贴合',
                '支撑', '支承', '承载', '穿过', '伸入', '伸出', '密封', '连接',
                '联接', '固定', '安装', '设置')

# ---- 断句：分句引导词（出现在这些词前面切开，能让长句里的每条关系独立成立）----
_CLAUSE_LEADS = ('此外', '另外', '同时', '并且', '而且', '然后', '接着', '此时',
                 '其中', '进一步地', '进一步', '优选地', '优选', '具体地', '尤其',
                 '特别是', '也就是说', '换言之', '又如', '再如', '另一方面',
                 '上述', '本实施例中', '本实施方式中', '在本实施例中')


def _split_sents(text):
    """断句：标点 + 换行 + 权项编号 + 分句引导词，尽量让每句只讲一条关系。"""
    t = text.replace('（', '(').replace('）', ')').replace('，', '，')
    # 「壳体（1）」这种括号标号统一成「壳体1」，否则标号和名称之间被括号隔断，
    # 所有「A…动词…B」的相邻模板都会失配（权利要求书里这种写法很常见）
    t = re.sub(r'\((\d{1,3})\)', r'\1', t)
    t = re.sub(r'[ \t\u3000]+', '', t)
    # 换行当句号：条文换行处常常没有标点，不切断就会跨段落乱连线
    t = re.sub(r'\r\n|\r|\n', '。', t)
    # 权项编号「1.」「2、」单独成句（小数点不算：后面不能跟数字）
    t = re.sub(r'(?:(?<=^)|(?<=[。；;！？]))(\d{1,2})[.．、](?!\d)', r'。\1、', t)
    t = re.sub(r'[。；;！？!?]+', '。', t)

    out = []
    for seg in t.split('。'):
        seg = seg.strip('，、 ')
        if not seg:
            continue
        # 长句再按「此外/同时/并且…」切成更小的关系句；短句不动（避免切断 A…动词…B）
        if len(seg) > 30:
            pat = '|'.join(re.escape(w) for w in sorted(_CLAUSE_LEADS, key=lambda w: -len(w)))
            pieces = re.split(r'(?:，)?(?:%s)' % pat, seg)
        else:
            pieces = [seg]
        for p in pieces:
            p = p.strip('，、 ')
            if p:
                out.append(p)
    return out


def _clean_name(name):
    """从首尾裁掉功能词/方位词，得到干净的特征名称。"""
    if not name:
        return ''
    for _ in range(2):  # 「所述一种」这类叠前缀剥两轮
        for pre in _LEAD_WORDS:
            if name.startswith(pre) and len(name) > len(pre):
                name = name[len(pre):]
                break
    # 「侧固定有张紧轮4」→「张紧轮4」；剥完只剩一个字说明是名词本身（固定座/安装板），不剥
    m = _LEAD_VERB_RE.match(name)
    if m and len(name) - m.end() >= 2:
        name = name[m.end():]
    # 「连通吸油口21」这类被关系动词开头的候选：剥掉动词后若剩下的是合法名词才剥。
    # 只剥那些基本不会做零件名开头的动词——「驱动电机」「控制阀」「检测器」要保持原样。
    for pre in _VERB_PREFIX:
        if name.startswith(pre) and len(name) > len(pre):
            rest = name[len(pre):]
            base = re.sub(r'\d{1,3}$', '', rest)
            if len(base) >= 2 and any(base.endswith(h) for h in _HEAD_SET):
                name = rest
                break
    while name and name[-1] in _STOP_CHARS:
        name = name[:-1]
    while name and name[0] in _STOP_CHARS:
        name = name[1:]
    return name


def _ends_head(name):
    """无标号模式：候选必须收尾于技术名词，才认作特征（标号数字先剥掉）。"""
    if not name or len(name) < 2 or name in _PLAIN_STOP:
        return False
    base = re.sub(r'\d{1,3}$', '', name)
    for h in _HEAD_SET:
        if base.endswith(h):
            return True
    return False


def _is_super(name):
    """是否是上位类别词（部件/装置/机构/系统/组件…）。"""
    base = re.sub(r'\d{1,3}$', '', name or '')
    return any(base.endswith(w) for w in _SUPER_WORDS)


def _find_tokens(seg, tok, plain=False):
    """按 token 模式提取片段中的特征（去重保序）。"""
    out, seen = [], set()
    for m in re.finditer('(%s)' % tok, seg or ''):
        name = _clean_name(m.group(1))
        if plain:
            name = _plain_name(name)
        if name and len(name) >= 2 and name not in seen:
            seen.add(name)
            out.append(name)
    return out


_GLUE_RE = '|'.join(sorted(set(_PLAIN_GLUE + tuple(_CONTAIN_WORDS)),
                            key=lambda w: (-len(w), w)))


def _plain_name(name):
    """把被动词串起来的候选切到真正的名词部分：
    「铰链包括销轴」→「销轴」、「锁体通过卡扣」→「卡扣」。
    只切「包括/设有/形成有…」这类基本不做零件名开头的动词，避免把「连接器」「固定座」切坏。"""
    if not name:
        return name
    cut = -1
    for m in re.finditer('(?:%s)' % _GLUE_RE, name):
        if m.start() > 0 and len(name) - m.end() >= 2:
            cut = m.end()
    if cut > 0:
        name = name[cut:]
    return _clean_name(name)


def _clean(tok):
    tok = (tok or '').strip('的了之其与及和、，。；：').strip()
    if not tok or len(tok) < 2:
        return None
    return _clean_name(tok) or None


def relations_analyze(text):
    """解析文本，返回 {nodes, edges, stats}。"""
    if not text:
        return {'nodes': [], 'edges': [],
                'stats': {'features': 0, 'relations': 0, 'mode': '', 'sentences': 0}}
    sents = _split_sents(text)

    edges, seen = [], set()

    def add(a, b, rel, kind=None):
        a, b = _clean(a), _clean(b)
        if not a or not b or a == b or len(a) < 2 or len(b) < 2:
            return
        key = (a, b, rel)
        if key in seen:
            return
        seen.add(key)
        edges.append({'a': a, 'b': b, 'rel': rel, 'kind': kind or _kind(rel)})

    def scan(sent, tok, plain, ctx, spans):
        """在一句话里跑全部模板，返回新增的边数。"""
        before = len(edges)

        # 预处理：一次扫出所有 token，建立「结束位置 → 最长 token 起点」映射，
        # 之后 tok_end 是 O(1)，避免每条边都对整句重扫（长文本下这是主要耗时点）
        end_map = {}
        for mm in re.finditer('(%s)' % tok, sent):
            e, st = mm.end(), mm.start()
            if e not in end_map or st < end_map[e]:
                end_map[e] = st

        def tok_end(pos):
            """取以 pos 结尾的「最长」token：把被动词截断的片段还原成完整特征名
            （「输送带2」被「输送」切成「带2」→ 还原；「侧固定有张紧轮4」→ 交给清洗）。"""
            st = end_map.get(pos)
            return sent[st:pos] if st is not None else ''

        def norm(raw):
            n = _clean_name(raw)
            if plain:
                n = _plain_name(n)
            return n

        def valid(n):
            """名称合法性：带附图标记的照收；不带的必须收尾于技术名词。"""
            if not n or len(n) < 2 or n in _PLAIN_STOP:
                return False
            if re.search(r'\d{1,3}$', n):
                return True
            return _ends_head(n)

        def pair(m, ga, gb, verb):
            """从两个捕获组取特征名，做清洗与合法性校验。"""
            a = norm(tok_end(m.end(ga)))
            b = norm(tok_end(m.end(gb)))
            if not valid(a) or not valid(b):
                return None
            # 动词其实被吃进了名词（输送带 / 连接器 / 固定架 / 支撑座），不是关系
            if verb and (verb in a or verb in b):
                return None
            return a, b

        def pick(seg):
            """包含列表里的一个分句：动词开头取宾语（最后一个），否则取第一个特征。"""
            toks = _find_tokens(seg, tok, plain)
            if not toks:
                return []
            if re.match(r'(?:%s)' % _REL_RE, seg):
                return [toks[-1]]
            return [toks[0]]

        def name_before(pos):
            """取 pos 之前的主语名：权利要求书开头的「一种切割装置」没有附图标记，
            用技术名词词尾兜底，否则整段「包括…」会因为找不到父节点而全部丢失。"""
            tail = sent[:pos].rstrip('，,：:、 ')
            raw = tok_end(len(tail))
            if raw:
                return norm(raw)
            # 「一种电子设备，其特征在于，包括…」：主语被「其特征在于」隔开，
            # 往前找最后一个技术名词短语（spans 已按句预扫，直接查）
            for a, b in reversed(spans):
                if b <= len(tail) and b - a >= 2:
                    return _plain_name(_clean_name(sent[a:b]))
            return ''

        def contain_children(parent, rest, word):
            """把「包括B、C和D」的列表元素挂到 parent 下。"""
            if not parent or len(parent) < 2 or not valid(parent):
                return
            rest = re.sub(r'^[：:，,、\s]*', '', rest)
            for seg in re.split(r'[，,、；;和及与]', rest):
                # 这一段里「特征+动词」说明已经进入下一个关系句，列表到此结束
                if re.search(r'(?:%s)[^，,]{0,8}?(?:%s)' % (tok, _VERB_RE), seg):
                    break
                for child in pick(seg):
                    if child and child != parent:
                        add(parent, child, word)

        # 1) 包含 / 组成：A包括B、C和D
        for m in re.finditer(r'(%s)(%s)(.+)' % (tok, _CONTAIN_RE), sent):
            parent = name_before(m.end(1)) or ctx.get('subj', '')
            contain_children(parent, m.group(3), m.group(2))

        # 1b) 主语没有附图标记（权利要求书开头常见）：「一种切割装置，包括机架1、导轨组件2」
        for m in re.finditer(r'[，,：:](%s)(.+)' % _CONTAIN_RE, sent):
            parent = name_before(m.start(1)) or ctx.get('subj', '')
            contain_children(parent, m.group(2), m.group(1))

        # 2) 设置 / 位置：A(的X)(上|内|中) 设置有/固定于/位于 B
        pos_pat = (r'(%s)(?:的[^，。；、与和]{0,8})?'
                   r'(?:上|内|中|外|侧|顶部|底部|端部|中部|下方|上方)?'
                   r'(%s)(?:的[^，。；、]{0,8})?(%s)' % (tok, _VERB_RE, tok))
        for m in re.finditer(pos_pat, sent):
            got = pair(m, 1, 3, m.group(2))
            if got:
                add(got[0], got[1], m.group(2))

        # 3) 通用动词：A …(≤12字)… 动词 …(≤6字)… B
        gen_pat = r'(%s)[^，。；、与和]{0,12}?(%s)[^，。；、]{0,6}?(%s)' % (tok, _VERB_RE, tok)
        for m in re.finditer(gen_pat, sent):
            got = pair(m, 1, 3, m.group(2))
            if got:
                add(got[0], got[1], m.group(2))

        # 4) 动词落在 B 之后：A与B固定连接 / A与B的输出轴键连接
        rev_pat = (r'(%s)(?:的[^，。；、]{0,8}?)?(?:与|同|跟|和)(?:所述)?(%s)'
                   r'([^，。；、]{0,10}?)(%s)' % (tok, tok, _VERB_RE))
        for m in re.finditer(rev_pat, sent):
            got = pair(m, 1, 2, m.group(4))
            if not got:
                continue
            mid = m.group(3)
            # 「主动轮21与驱动电机3的输出轴31键连接」：真正相连的是省略号里的那个特征
            inner = _find_tokens(mid, tok, plain) if mid.startswith('的') else []
            add(got[0], inner[0] if inner else got[1], m.group(4))

        # 5) A通过K与B连接：K 当作连接方式写进关系名（K 可能带标号，如「软管51」）
        via_pat = (r'(%s)通过([\u4e00-\u9fa5]{2,8}\d{0,3})(?:与|和|同)?(%s)'
                   r'[^，。；、]{0,3}?(%s)' % (tok, tok, _VERB_RE))
        for m in re.finditer(via_pat, sent):
            # 「A与B通过K相连」是两端关系，交给 5c 处理，这里别把 B 当成连接件
            if re.search(r'[与和及]$', sent[:m.start()]):
                continue
            got = pair(m, 1, 3, m.group(4))
            if got:
                add(got[0], got[1], m.group(2) + m.group(4))
        # 5b) 「真空泵5通过软管51连通吸油口21」：动词在 B 之前
        via2_pat = (r'(%s)通过([\u4e00-\u9fa5]{2,8}\d{0,3})(%s)[^，。；、]{0,4}?(%s)'
                    % (tok, _VERB_RE, tok))
        for m in re.finditer(via2_pat, sent):
            got = pair(m, 1, 4, m.group(3))
            if got:
                add(got[0], got[1], m.group(2) + m.group(3))
        # 5c) 「A与B通过K相连接」：A、B 是两端，K 是连接件
        via3_pat = (r'(%s)(?:与|和)(?:所述)?(%s)通过([\u4e00-\u9fa5]{2,8}\d{0,3})'
                    r'[^，。；、]{0,4}?(%s)' % (tok, tok, _VERB_RE))
        for m in re.finditer(via3_pat, sent):
            got = pair(m, 1, 2, m.group(4))
            if got:
                add(got[0], got[1], m.group(3) + m.group(4))

        # 6) 上下位：A为/是/属于/作为/构成 B
        hyp_pat = (r'(%s)(?:为|是|属于|作为|用作|构成|组成|选用|采用)'
                   r'(?:一种|一个|一类|一种类型的|所述)?(%s)' % (tok, tok))
        for m in re.finditer(hyp_pat, sent):
            got = pair(m, 1, 2, None)
            if got:
                add(got[0], got[1], '属于', 'hyponym')

        # 6b) A为B的一种 / A是B的组成部分 / A属于B这一类
        hyp2_pat = (r'(%s)(?:为|是|属于|作为)(?:所述)?(%s)的'
                    r'(?:一种|一类|一个|一部分|组成部分|子部件|分支|具体形式|下位概念)'
                    % (tok, tok))
        for m in re.finditer(hyp2_pat, sent):
            got = pair(m, 1, 2, None)
            if got:
                add(got[0], got[1], '属于', 'hyponym')

        # 6c) A、B均为C（并列上位）
        hyp3_pat = (r'(%s)(?:、|和|与|及)(%s)(?:均|都|皆|分别)?(?:为|是|属于)(%s)'
                    % (tok, tok, tok))
        for m in re.finditer(hyp3_pat, sent):
            a, b, c = (pair(m, 1, 1, None), pair(m, 2, 2, None), pair(m, 3, 3, None))
            parent = c[0] if c else None
            if not parent:
                continue
            for item in (a, b):
                if item and item[0] and item[0] != parent:
                    add(item[0], parent, '属于', 'hyponym')

        # 7) 组成：A和B构成C → C 包含 A、B
        com_pat = r'(%s)(?:和|与|、)(%s)(?:共同|一起|均)?(?:构成|组成|形成)(%s)' % (tok, tok, tok)
        for m in re.finditer(com_pat, sent):
            a, b, c = (pair(m, 1, 1, None), pair(m, 2, 2, None), pair(m, 3, 3, None))
            parent = c[0] if c else None
            if not parent:
                continue
            for item in (a, b):
                if item and item[0] and item[0] != parent:
                    add(parent, item[0], '组成')

        # 8) 从属：A的B（B 是 A 的组成部分）
        for m in re.finditer(r'(%s)的(%s)' % (tok, tok), sent):
            got = pair(m, 1, 2, None)
            if got and got[0] != got[1]:
                add(got[0], got[1], '从属', 'depend')

        # 9) 在A上/内设置有B（动词主语在介词短语里，方向反过来）
        prep_pat = (r'(?:在|于)(%s)(?:的[^，。；、]{0,8})?'
                    r'(?:上|内|中|外|侧|顶部|底部|端部|中部|下方|上方)?'
                    r'(%s)(?:有|着)?(%s)' % (tok, _VERB_RE, tok))
        for m in re.finditer(prep_pat, sent):
            got = pair(m, 1, 3, m.group(2))
            if got:
                add(got[0], got[1], m.group(2))

        # 10) 将A固定于/安装在B（把字句）
        ba_pat = (r'(?:将|把)(?:所述)?(%s)(?:通过[^，。；、]{0,8})?'
                  r'(?:固定|安装|设置|连接|装配|嵌设|套设|焊接|卡接)(?:在|于|到)'
                  r'(?:所述)?(%s)' % (tok, tok))
        for m in re.finditer(ba_pat, sent):
            got = pair(m, 1, 2, None)
            if got:
                add(got[0], got[1], '安装于', 'position')

        # 11) A与B之间设置有C（C 同时与两端相邻）
        mid_pat = (r'(%s)(?:与|和)(?:所述)?(%s)之间(?:%s)(?:有)?(%s)'
                   % (tok, tok, _VERB_RE, tok))
        for m in re.finditer(mid_pat, sent):
            a, b, c = (pair(m, 1, 1, None), pair(m, 2, 2, None), pair(m, 3, 3, None))
            if c and c[0]:
                if a and a[0]:
                    add(a[0], c[0], '之间设置', 'position')
                if b and b[0]:
                    add(b[0], c[0], '之间设置', 'position')

        # 12) A和B均/分别设置于C（并列主语）
        both_pat = (r'(%s)(?:和|与|、|及)(%s)(?:均|都|分别|同时)?'
                    r'(?:设置|安装|固定|连接|装配|布置)(?:在|于|到)(?:所述)?(%s)'
                    % (tok, tok, tok))
        for m in re.finditer(both_pat, sent):
            a, b, c = (pair(m, 1, 1, None), pair(m, 2, 2, None), pair(m, 3, 3, None))
            if not (c and c[0]):
                continue
            for item in (a, b):
                if item and item[0] and item[0] != c[0]:
                    add(item[0], c[0], '设置于', 'position')

        # 13) 材质/类别归属：A由B制成 / A采用B
        mat_pat = (r'(%s)(?:由|采用|选用|使用)(%s)(?:制成|构成|加工|形成|制备)?' % (tok, tok))
        for m in re.finditer(mat_pat, sent):
            got = pair(m, 1, 2, None)
            if got:
                add(got[0], got[1], '采用', 'hyponym')

        return len(edges) - before

    # ---- 先判断用哪种模式：有 4 个以上带标号特征就走标号模式，否则退回名称模式 ----
    num_tokens = set()
    for s in sents:
        num_tokens.update(_find_tokens(s, _FEAT))
    plain = len(num_tokens) < 4

    # ---- L1 / L2 + L3：逐句识别；句内没有识别到关系时，按共现串成「相关」链 ----
    ctx = {'subj': ''}
    # 全篇的名词短语先扫一遍：token 用全篇并集，几十条模板只编译一次
    spans_by_sent, all_names = [], []
    for s in sents:
        sp = _plain_spans(s) if s else []
        spans_by_sent.append(sp)
        for a, b in sp:
            nm = _plain_name(_clean_name(s[a:b]))
            if (nm and len(nm) >= 2 and nm not in _PLAIN_STOP
                    and _ends_head(nm) and nm not in all_names):
                all_names.append(nm)
    tok = _tok_for(all_names)

    for idx, s in enumerate(sents):
        if not s:
            continue
        spans = spans_by_sent[idx]
        found = scan(s, tok, plain, ctx, spans)
        feats = _find_tokens(s, tok, plain)
        if not found:
            for i in range(len(feats) - 1):
                add(feats[i], feats[i + 1], '相关')
        # 记录本句的第一个特征，供下一句「还包括X」这类省略主语的句子承接
        if feats:
            head = feats[0]
            if not _is_super(head) or not ctx.get('subj'):
                ctx['subj'] = head

    # 同一对特征上的重叠关系只留更具体的那条（「螺栓连接」vs「螺栓连接固定在」），
    # 互不包含的关系（「包括」「设置有」）都保留
    best = {}
    for e in edges:
        key = (e['a'], e['b'])
        prev = best.get(key)
        if prev is None:
            best[key] = e
        elif e['rel'] in prev['rel'] or prev['rel'] in e['rel']:
            if len(e['rel']) > len(prev['rel']):
                best[key] = e
        else:
            best.setdefault(key + (e['rel'],), e)
    edges = list(best.values())

    # ---- 同类：第一壳体1 / 第二壳体2 → 同一族，横向连一条「同类」 ----
    names = []
    for e in edges:
        for x in (e['a'], e['b']):
            if x not in names:
                names.append(x)
    fam = {}
    for n in names:
        base = re.sub(r'\d{1,3}$', '', n)
        base = re.sub(r'^第[一二三四五六七八九十]+', '', base)
        fam.setdefault(base, []).append(n)
    for base, lst in fam.items():
        if 1 < len(lst) <= 6:
            for i in range(len(lst) - 1):
                add(lst[i], lst[i + 1], '同类', 'sibling')

    # ---- L4 上下位推断：只在「同句共现 + 名词有包含关系」时补一条，避免乱连 ----
    #      例：文本里出现「减速箱4」和「减速箱组件」这种同词干的上位词时补连；
    #      纯靠类别词（部件/装置…）硬连会把每个节点都挂到根节点上，所以不做。
    sup_pairs = []
    for i, n1 in enumerate(names):
        b1 = re.sub(r'\d{1,3}$', '', n1)
        for n2 in names[i + 1:]:
            b2 = re.sub(r'\d{1,3}$', '', n2)
            if not b1 or not b2 or b1 == b2:
                continue
            if not (_is_super(n1) or _is_super(n2)):
                continue
            short, long_ = (b1, b2) if len(b1) <= len(b2) else (b2, b1)
            if len(short) >= 3 and short in long_:
                sup_pairs.append((n1, n2, short == b1))
    for n1, n2, first_is_sub in sup_pairs:
        sub, sup = (n1, n2) if first_is_sub else (n2, n1)
        add(sub, sup, '属于', 'hyponym')

    # 边太多反而看不清：超量时保留前面的（模板命中的边优先于共现兜底）
    if len(edges) > 600:
        edges = edges[:600]

    degree = {}
    for e in edges:
        degree[e['a']] = degree.get(e['a'], 0) + 1
        degree[e['b']] = degree.get(e['b'], 0) + 1
    nodes = [{'id': name, 'label': name,
              'num': (re.search(r'(\d{1,3})$', name).group(1)
                      if re.search(r'(\d{1,3})$', name) else ''),
              'degree': deg}
             for name, deg in sorted(degree.items(), key=lambda x: -x[1])]
    return {'nodes': nodes, 'edges': edges,
            'stats': {'features': len(nodes), 'relations': len(edges),
                      'mode': '名称' if plain else '标记',
                      'sentences': len(sents),
                      'kinds': dict(Counter(e['kind'] for e in edges))}}

# ---------------- 前端页面（原 index.html，完整内嵌） ----------------
INDEX_HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<!-- 主程序用此标记判断端口上跑的是否为本项目自带的整合服务 -->
<meta name="fenrir-design-adjust" content="1" />
<title>CYBER—FORGE · 外观专利图批处理</title>
<style>
  :root{
    --bg:#0a0d14; --panel:#111725; --panel2:#161d2c; --line:#232c40;
    --neon:#4d8dff; --neon2:#a78bfa; --neon3:#3ddc97; --accent:#4d8dff;
    --text:#e8edf7; --muted:#8b97ad;
    --warn:#f3b23c; --danger:#f2596f;
    --r:14px; --r-sm:9px;
    --sh:0 1px 2px rgba(0,0,0,.45),0 14px 34px -16px rgba(0,0,0,.85);
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--bg);color:var(--text);
    font-family:"Inter","PingFang SC","Microsoft YaHei",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    font-size:13.5px;line-height:1.6;
    background-image:
      radial-gradient(1100px 520px at 12% -8%,rgba(77,141,255,.11),transparent 62%),
      radial-gradient(900px 480px at 100% 0%,rgba(167,139,250,.075),transparent 58%);
    background-attachment:fixed}
  ::selection{background:rgba(77,141,255,.32)}
  *::-webkit-scrollbar{width:10px;height:10px}
  *::-webkit-scrollbar-track{background:transparent}
  *::-webkit-scrollbar-thumb{background:#2a3448;border-radius:8px;border:2px solid var(--bg)}
  *::-webkit-scrollbar-thumb:hover{background:#3a4760}

  /* ---------- 顶部应用栏 ---------- */
  header{position:sticky;top:0;z-index:60;display:flex;align-items:center;justify-content:space-between;
    gap:18px;flex-wrap:wrap;padding:10px 24px;
    background:rgba(11,15,23,.82);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
    border-bottom:1px solid var(--line)}
  .appHeader{display:flex;align-items:center;gap:12px;min-width:0}
  header h1{margin:0;font-size:16px;font-weight:800;letter-spacing:1.8px;color:var(--text);white-space:nowrap;
    font-family:"SF Mono",ui-monospace,Menlo,Consolas,monospace;display:flex;align-items:center;gap:6px}
  header h1 .h1dash{color:#5ef2d0;opacity:.85;font-weight:600;
    text-shadow:0 0 10px rgba(94,242,208,.55)}
  header h1 .h1tag{font-family:inherit;font-size:9px;font-weight:700;letter-spacing:1.4px;
    padding:2px 6px 2px 7px;margin-left:2px;border-radius:5px;color:#0a0d14;
    background:linear-gradient(135deg,#5ef2d0,#4d8dff);
    box-shadow:0 0 12px rgba(94,242,208,.35);transform:translateY(-1px)}
  header p{margin:3px 0 0;color:var(--muted);font-size:11.5px;letter-spacing:.2px;line-height:1.45}
  .appLogo{width:40px;height:40px;flex:0 0 40px;animation:apFloat 6s ease-in-out infinite}
  .appLogo svg{width:100%;height:100%;display:block;filter:drop-shadow(0 0 9px rgba(77,141,255,.4))}

  /* ---------- 页签（分段控件） ---------- */
  .tabs{display:flex;gap:4px;padding:4px;background:var(--panel);border:1px solid var(--line);
    border-radius:12px;box-shadow:inset 0 1px 0 rgba(255,255,255,.03)}
  .tab{padding:7px 18px;cursor:pointer;color:var(--muted);border:0;background:transparent;
    border-radius:9px;font-size:13px;font-weight:600;font-family:inherit;letter-spacing:.2px;
    transition:background .16s,color .16s,box-shadow .16s;white-space:nowrap;box-shadow:none}
  .tab:hover{color:var(--text);background:rgba(255,255,255,.045)}
  .tab.on{color:#fff;background:linear-gradient(180deg,#4d8dff,#3a72e4);
    box-shadow:0 2px 10px rgba(77,141,255,.38)}

  /* ---------- 布局 ---------- */
  .wrap{padding:22px 24px 64px;max-width:1280px;margin:0 auto}
  .card{background:linear-gradient(180deg,rgba(255,255,255,.022),rgba(255,255,255,0)),var(--panel);
    border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;margin-bottom:18px;
    box-shadow:var(--sh);position:relative}
  .card h2{margin:0 0 15px;padding-bottom:12px;border-bottom:1px solid var(--line);
    font-size:14.5px;font-weight:650;color:var(--text);letter-spacing:.2px;
    display:flex;align-items:center;gap:10px}
  .card h2 .step{display:inline-flex;align-items:center;justify-content:center;min-width:23px;height:23px;
    padding:0 7px;border-radius:7px;background:rgba(77,141,255,.15);border:1px solid rgba(77,141,255,.25);
    color:var(--neon);font-size:12px;font-weight:700;font-variant-numeric:tabular-nums;flex:none}

  .row{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end}
  .field{display:flex;flex-direction:column;gap:6px;min-width:0}
  label{font-size:12px;color:var(--muted);letter-spacing:.2px}

  /* ---------- 表单控件 ---------- */
  .filePick{position:relative;display:flex;align-items:center;gap:10px;min-width:250px;max-width:360px;
    border:1px solid var(--line);background:#0c1220;border-radius:var(--r-sm);padding:5px 6px;
    cursor:pointer;transition:border-color .15s,box-shadow .15s}
  .filePick:hover{border-color:#33405c}
  .filePick:focus-within{border-color:var(--neon);box-shadow:0 0 0 3px rgba(77,141,255,.16)}
  .filePick input[type=file]{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;margin:0}
  .filePickBtn{flex:none;background:var(--panel2);border:1px solid var(--line);border-radius:7px;
    padding:6px 12px;font-size:12px;font-weight:600;color:var(--text);transition:.15s}
  .filePick:hover .filePickBtn{border-color:var(--neon);color:var(--neon);background:rgba(77,141,255,.1)}
  .filePickName{font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap;min-width:0;padding-right:6px}
  .filePickName.set{color:var(--text)}
  input[type=file]{color:var(--muted);font-size:12px;max-width:100%}
  input[type=file]::file-selector-button{background:var(--panel2);color:var(--text);
    border:1px solid var(--line);border-radius:8px;padding:7px 13px;margin-right:10px;
    font-family:inherit;font-size:12px;cursor:pointer;transition:.15s}
  input[type=file]::file-selector-button:hover{border-color:var(--neon);color:var(--neon);
    background:rgba(77,141,255,.1)}
  select,input[type=number],input[type=text],textarea{background:#0c1220;color:var(--text);
    border:1px solid var(--line);border-radius:var(--r-sm);padding:8px 11px;font-size:13px;
    font-family:inherit;outline:none;transition:border-color .15s,box-shadow .15s;min-width:0}
  select:hover,input[type=number]:hover,input[type=text]:hover{border-color:#33405c}
  select:focus,input[type=number]:focus,input[type=text]:focus,textarea:focus{
    border-color:var(--neon);box-shadow:0 0 0 3px rgba(77,141,255,.16)}
  select{appearance:none;-webkit-appearance:none;padding-right:30px;cursor:pointer;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M3 4.5 6 8l3-3.5' fill='none' stroke='%238b97ad' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/></svg>");
    background-repeat:no-repeat;background-position:right 10px center}
  input[type=checkbox]{accent-color:var(--neon);width:15px;height:15px;cursor:pointer}
  input[type=range]{accent-color:var(--neon);cursor:pointer}
  input::placeholder{color:#5c6a83}

  /* ---------- 按钮 ---------- */
  button{background:linear-gradient(180deg,#4d8dff,#3a72e4);color:#fff;
    border:1px solid rgba(255,255,255,.1);border-radius:var(--r-sm);
    padding:9px 17px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;
    letter-spacing:.2px;transition:background .15s,transform .1s,box-shadow .15s;
    box-shadow:0 1px 2px rgba(0,0,0,.35),0 7px 18px -9px rgba(77,141,255,.85)}
  button:hover:not(:disabled){background:linear-gradient(180deg,#5f9bff,#4680f0);
    transform:translateY(-1px);box-shadow:0 2px 4px rgba(0,0,0,.35),0 12px 24px -9px rgba(77,141,255,.9)}
  button:active:not(:disabled){transform:translateY(0);filter:brightness(.95)}
  button.ghost{background:var(--panel2);color:var(--text);border:1px solid var(--line);box-shadow:none}
  button.ghost:hover:not(:disabled){background:#1d2639;border-color:#39465f;color:#fff;transform:translateY(-1px)}
  button:disabled{opacity:.42;cursor:not-allowed;filter:grayscale(.35)}
  button:focus-visible{outline:2px solid rgba(77,141,255,.7);outline-offset:2px}

  .hint{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.7}
  .hint b{color:var(--text);font-weight:600}
  .note{font-size:12.5px;color:var(--text);border:1px solid var(--line);border-left:3px solid var(--neon);
    border-radius:var(--r-sm);padding:12px 14px;background:rgba(77,141,255,.055);margin-top:10px;line-height:1.8}
  .note b{color:#fff}
  .msg{font-size:12.5px;padding:9px 13px;margin-top:10px;display:none;
    border:1px solid transparent;border-left-width:3px;border-radius:var(--r-sm);line-height:1.6}
  .msg.warn{display:block;background:rgba(243,178,60,.1);color:#ffd479;border-color:rgba(243,178,60,.32)}
  .msg.err{display:block;background:rgba(242,89,111,.1);color:#ff9dab;border-color:rgba(242,89,111,.38)}
  .msg.ok{display:block;background:rgba(61,220,151,.1);color:#7cf0c4;border-color:rgba(61,220,151,.32)}

  /* ---------- 视图卡片 ---------- */
  .views{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
  .view{background:var(--panel2);border:1px solid var(--line);border-radius:var(--r-sm);padding:12px;
    transition:border-color .16s,box-shadow .16s}
  .view:hover{border-color:#33405c}
  .view.stereo{border-color:rgba(167,139,250,.42);box-shadow:inset 0 0 0 1px rgba(167,139,250,.1)}
  .view .vh{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px}
  .view .vh b{color:var(--text);font-size:12.5px;font-weight:600;letter-spacing:.2px}
  .view .vh .badge{color:var(--neon2);border-color:rgba(167,139,250,.34);background:rgba(167,139,250,.1)}
  .view select{width:100%;margin-bottom:9px}
  .ba{display:flex;gap:8px}
  .ba .col{flex:1;min-width:0}
  .ba .cap{font-size:10.5px;color:var(--muted);margin-bottom:5px;letter-spacing:.5px;text-transform:uppercase}
  .ba img{width:100%;height:150px;object-fit:contain;background:#080c14;border:1px solid var(--line);
    border-radius:7px;display:block}
  .ba .dim{font-size:11px;color:var(--muted);margin-top:5px;text-align:center;font-variant-numeric:tabular-nums}
  .ba .dim b{color:var(--neon3)}
  .grid2{display:grid;grid-template-columns:1.08fr 1fr;gap:20px}

  /* ---------- 表格 ---------- */
  table{width:100%;border-collapse:separate;border-spacing:0;font-size:12px;font-variant-numeric:tabular-nums}
  th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:center}
  th{background:var(--panel2);color:var(--muted);font-size:11px;font-weight:600;
    letter-spacing:.3px;white-space:nowrap}
  th:first-child{border-top-left-radius:8px}
  th:last-child{border-top-right-radius:8px}
  tr:last-child td{border-bottom:none}
  td.k{color:var(--neon3);font-weight:600}
  tr:hover td{background:rgba(255,255,255,.025)}

  .tableWrap{overflow:auto;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.012)}
  #alignCanvas{width:100%;height:auto;background:#0b1120;border:1px solid var(--line);
    border-radius:10px;display:block}
  .badge{display:inline-flex;align-items:center;gap:6px;background:var(--panel2);
    border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:11.5px;
    color:var(--muted);letter-spacing:.2px;white-space:nowrap}
  .spinner{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--neon);
    animation:blink .8s ease-in-out infinite;vertical-align:-1px;margin-right:7px}
  @keyframes blink{50%{opacity:.25}}
  .glitch{color:var(--neon2);font-weight:600}

  /* ---------- 附图标注 ---------- */
  .figCv{width:100%;background:#fff;border:1px solid var(--line);border-radius:8px;
    cursor:crosshair;display:block}
  .figPage{margin-top:16px;border:1px solid var(--line);border-radius:12px;padding:12px 14px;
    background:var(--panel2);transition:border-color .16s}
  .figBadge{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;color:var(--neon);
    background:rgba(77,141,255,.12);border:1px solid rgba(77,141,255,.28);border-radius:999px;padding:2px 10px}

  /* ---------- XML 修改（tab3） ---------- */
  .zxGroup{margin-top:16px;padding-top:14px;border-top:1px solid var(--line)}
  .zxGroup:first-child{border-top:none;margin-top:0;padding-top:0}
  .zxGroupTitle{display:flex;align-items:center;gap:9px;color:var(--text);font-size:12.5px;
    font-weight:650;letter-spacing:.2px;margin-bottom:11px}
  .zxGroupTitle:before{content:"";width:3px;height:13px;border-radius:2px;background:var(--neon);flex:none}
  .zxFileRow{display:flex;align-items:center;gap:10px;padding:6px 0;font-size:12px;
    border-bottom:1px solid var(--line);flex-wrap:wrap}
  .zxFileRow:last-child{border-bottom:none}
  .zxFileRow .fk{color:var(--muted);font-variant-numeric:tabular-nums}
  .zxFileRow .fk.kind{flex:none;font-size:10px;font-weight:600;letter-spacing:.4px;
    padding:1px 7px;border-radius:5px;border:1px solid var(--line);background:var(--panel2);color:var(--muted)}
  .zxFileRow .fk.kind.xml{color:#8fb4ff;border-color:rgba(77,141,255,.35);background:rgba(77,141,255,.12)}
  .zxFileRow .fk.kind.img{color:#5ee0ab;border-color:rgba(61,220,151,.32);background:rgba(61,220,151,.1)}
  .zxFileRow .fk.kind.bin{color:#c9a6ff;border-color:rgba(167,139,250,.32);background:rgba(167,139,250,.1)}
  .zxFileRow .fname{color:var(--text);max-width:46%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .zxFileRow .fdir{color:#63718a;font-size:11px;max-width:34%;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap;flex:1;min-width:0}
  .zxFileRow .fsize{color:var(--muted);font-variant-numeric:tabular-nums;margin-left:auto;flex:none}
  .zxFilesBox{margin-top:12px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.012)}
  .zxFilesBox>summary{display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;
    list-style:none;user-select:none;border-radius:10px;transition:background .15s}
  .zxFilesBox>summary::-webkit-details-marker{display:none}
  .zxFilesBox>summary:hover{background:rgba(255,255,255,.03)}
  .zxFilesBox>summary:before{content:"▸";color:var(--muted);font-size:11px;transition:transform .15s}
  .zxFilesBox[open]>summary:before{transform:rotate(90deg)}
  .zxFilesBox[open]>summary{border-bottom:1px solid var(--line);border-radius:10px 10px 0 0}
  .zxFilesBox .zxFilesSum{font-size:12.5px;font-weight:600;color:var(--text)}
  .zxFilesBox .zxFilesTip{font-size:11.5px;color:var(--muted);margin-left:auto}
  .zxFilesBox #zxFiles{padding:4px 14px 10px}
  .zxEmpty{grid-column:1/-1;color:var(--muted);font-size:12.5px;text-align:center;
    padding:34px 12px;border:1px dashed var(--line);border-radius:10px;line-height:1.9}
  .zxEmpty b{color:var(--text);font-weight:600}
  .row>.field.actions{margin-left:auto;flex-direction:row;align-items:center;gap:8px}
  .zxFileRow .scanflag{color:#ffd479;border:1px solid rgba(243,178,60,.4);background:rgba(243,178,60,.1);
    border-radius:6px;padding:1px 7px;font-size:11px}
  .zxInvRow{display:flex;gap:10px;align-items:center;margin-bottom:8px;flex-wrap:wrap}
  .zxInvRow input[type="text"]{width:220px}
  .zxInvRow .idx{color:var(--neon2);min-width:22px;text-align:center;font-size:12px;
    font-variant-numeric:tabular-nums}
  #zxDetail input[type=text]{width:100%}
  .zxLayout{display:block}
  .zxMain{min-width:0}

  .zxDoc{margin-top:14px;border:1px solid var(--line);border-radius:12px;overflow:hidden;
    background:rgba(255,255,255,.012)}
  .zxDoc:first-child{margin-top:0}
  .zxDocHead{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--panel2);
    border-bottom:1px solid var(--line);color:var(--text);font-size:12.5px;font-weight:650;letter-spacing:.2px}
  .zxDocHead .cnt{color:var(--muted);font-size:11px;font-weight:400;letter-spacing:0;margin-left:auto}

  .zxFields{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:10px 16px;padding:12px 14px}
  .zxField{display:flex;flex-direction:column;gap:5px;min-width:0}
  .zxField .fpath{font-size:10.5px;color:var(--muted);word-break:break-all;line-height:1.4}
  .zxField input[type=text]{width:100%}
  .zxField .chk{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--text)}
  .zxField input[type=checkbox]{width:15px;height:15px}
  .zxCat{display:grid;grid-template-columns:minmax(110px,180px) 1fr;gap:0 16px;align-items:start;
    padding:8px 14px;border-top:1px solid rgba(255,255,255,.035)}
  .zxCat:first-child{border-top:none}
  .zxCatHead{font-size:11px;letter-spacing:.4px;color:var(--neon2);font-weight:600;
    padding:9px 0 0;line-height:1.5;word-break:break-word}
  .zxCat .zxFields{padding:4px 0 6px}

  .zxImgs{display:flex;flex-wrap:wrap;gap:12px;padding:12px 14px;border-top:1px solid var(--line)}
  .zxImgCard{width:168px;border:1px solid var(--line);border-radius:10px;overflow:hidden;
    background:#0a0f18;position:relative;cursor:zoom-in;padding-bottom:24px;
    transition:transform .16s,border-color .16s,box-shadow .16s}
  .zxImgCard:hover{transform:translateY(-2px);border-color:#39465f;box-shadow:0 12px 26px -14px rgba(0,0,0,.95)}
  .zxImgCard.drag{border-color:var(--neon);box-shadow:0 0 0 2px rgba(77,141,255,.3)}
  .zxImgCard img{width:100%;display:block;min-height:100px;background:#fff;pointer-events:none}
  .zxImgCard .nm{font-size:10px;color:var(--muted);padding:5px 7px;word-break:break-all;
    border-top:1px solid var(--line);line-height:1.45;background:var(--panel2)}
  .zxImgCard .lim{font-size:10px;color:#6b7a92;padding:3px 7px;text-align:center;line-height:1.35}
  .zxImgCard button.ghost{border-radius:0;font-family:inherit;box-shadow:none;transform:none}
  .zxImgCard button.ghost:hover{background:rgba(77,141,255,.16)!important;color:var(--neon)!important}
  .zxImgCard .res{font-size:10px;color:var(--neon);padding:3px 7px 6px;text-align:center;
    line-height:1.35;word-break:break-all;font-variant-numeric:tabular-nums}
  .zxImgCard .res.warn{color:#ffbe55}
  .zxImgCard .rp{position:absolute;top:6px;right:6px;z-index:2;background:var(--neon);color:#04121a;
    font-size:10px;padding:2px 8px;border-radius:999px;display:none;font-weight:700}
  .zxImgCard.replaced .rp{display:block}
  .zxImgCard.added .rp{display:block;background:var(--neon2);color:#150a26}
  .zxImgCard.deleted{opacity:.45;filter:grayscale(.9)}
  .zxImgCard.deleted .rp{display:block;background:var(--danger);color:#fff}
  .zxImgCard .del{position:absolute;top:6px;left:6px;z-index:3;background:rgba(18,24,36,.86);
    color:#ff9dab;border:1px solid rgba(242,89,111,.45);font-size:10.5px;padding:2px 7px;
    border-radius:6px;cursor:pointer;font-family:inherit;opacity:.9;transition:.15s;box-shadow:none}
  .zxImgCard .del:hover{background:var(--danger);color:#fff;transform:none;box-shadow:none}
  .zxImgCard .undo{position:absolute;top:6px;left:6px;z-index:3;background:var(--neon);color:#04121a;
    border:none;font-size:10.5px;padding:2px 7px;border-radius:6px;cursor:pointer;
    font-family:inherit;font-weight:700;box-shadow:none}
  .zxImgCard .undo:hover{background:#6ba0ff;transform:none;box-shadow:none}
  .zxImgCard .ov{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    background:rgba(6,10,18,.62);color:#fff;font-size:11px;text-align:center;opacity:0;
    transition:.15s;line-height:1.6;padding:8px}
  .zxImgCard:hover .ov{opacity:1}
  .zxImgAdd{width:168px;min-height:168px;border:1.5px dashed #33405c;border-radius:10px;
    display:flex;align-items:center;justify-content:center;flex-direction:column;gap:6px;
    color:var(--muted);cursor:pointer;font-size:12px;background:rgba(255,255,255,.015);
    font-family:inherit;line-height:1.5;text-align:center;padding:10px;transition:.16s;box-shadow:none}
  .zxImgAdd:hover{border-color:var(--neon);color:var(--neon);background:rgba(77,141,255,.07)}
  .zxSubTitle{color:var(--neon2);font-size:11.5px;font-weight:600;letter-spacing:.3px;margin:14px 0 8px}
  .zxBins{padding:12px 14px;border-top:1px solid var(--line)}
  .zxNoImg{color:var(--muted);font-size:12.5px;padding:26px 8px;text-align:center;
    border:1px dashed var(--line);border-radius:10px}
  .zxImgModal{position:fixed;inset:0;background:rgba(4,6,12,.9);backdrop-filter:blur(6px);
    display:none;z-index:9999;align-items:center;justify-content:center;padding:24px}
  .zxImgModal.on{display:flex}
  .zxImgModal img{max-width:96vw;max-height:92vh;background:#fff;border-radius:8px;
    box-shadow:0 24px 70px rgba(0,0,0,.6)}
  .zxImgModal .close{position:absolute;top:18px;right:24px;color:#cbd5e5;font-size:22px;
    cursor:pointer;line-height:1;font-family:inherit;width:38px;height:38px;border-radius:10px;
    display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.07);
    border:1px solid rgba(255,255,255,.12)}
  .zxImgModal .close:hover{background:rgba(255,255,255,.14);color:#fff}
  .zxImgModal .cap{position:absolute;bottom:18px;left:0;right:0;text-align:center;
    color:#9aa7bd;font-size:12px;padding:0 20px}

  /* ---------- LOGO 动画 ---------- */
  @keyframes apFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}
  .appLogo .ring{transform-origin:50px 50px;animation:apSpin 16s linear infinite}
  @keyframes apSpin{to{transform:rotate(360deg)}}
  .appLogo .scan{animation:apScan 3.2s ease-in-out infinite}
  @keyframes apScan{0%{transform:translateY(-26px);opacity:0}20%{opacity:.9}80%{opacity:.9}100%{transform:translateY(26px);opacity:0}}
  .appLogo .pulse{animation:apPulse 2.2s ease-in-out infinite}
  @keyframes apPulse{0%,100%{opacity:.4}50%{opacity:1}}
  .appLogo .frame{animation:apGlow 3s ease-in-out infinite}
  @keyframes apGlow{0%,100%{stroke-opacity:.65}50%{stroke-opacity:1}}

  /* ---------- 响应式 ---------- */
  @media(max-width:980px){
    .views{grid-template-columns:repeat(2,1fr)}
    .grid2{grid-template-columns:1fr}
  }
  @media(max-width:720px){
    header{padding:10px 14px;gap:10px}
    .wrap{padding:16px 12px 48px}
    .card{padding:14px 14px;border-radius:12px}
    header p{display:none}
    .tabs{width:100%;justify-content:space-between}
    .tab{flex:1;text-align:center;padding:8px 6px}
  }
  @media(max-width:720px){
    .zxCat{grid-template-columns:1fr;gap:0}
    .zxCatHead{padding:6px 0 2px}
  }
  @media(max-width:620px){
    .views{grid-template-columns:1fr}
    .zxImgCard,.zxImgAdd{width:calc(50% - 6px)}
  }
</style>
</head>
<body>
<header>
  <div class="appHeader">
    <div class="appLogo" aria-hidden="true">
      <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="cpG1" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#5ef2d0"/><stop offset="1" stop-color="#4d8dff"/>
          </linearGradient>
        </defs>
        <g class="ring">
          <circle cx="50" cy="50" r="45" fill="none" stroke="#4d8dff" stroke-width="1.3" stroke-dasharray="7 9" opacity=".45"/>
        </g>
        <rect class="frame" x="22" y="22" width="56" height="56" rx="8" fill="none" stroke="url(#cpG1)" stroke-width="3"/>
        <path d="M22 35 V22 H35" stroke="#5ef2d0" stroke-width="3" fill="none" stroke-linecap="round"/>
        <path d="M65 22 H78 V35" stroke="#5ef2d0" stroke-width="3" fill="none" stroke-linecap="round"/>
        <path d="M78 65 V78 H65" stroke="#5ef2d0" stroke-width="3" fill="none" stroke-linecap="round"/>
        <path d="M35 78 H22 V65" stroke="#5ef2d0" stroke-width="3" fill="none" stroke-linecap="round"/>
        <g class="pulse" fill="#4d8dff">
          <rect x="39" y="39" width="10" height="10" rx="2"/>
          <rect x="51" y="39" width="10" height="10" rx="2"/>
          <rect x="39" y="51" width="10" height="10" rx="2"/>
          <rect x="51" y="51" width="10" height="10" rx="2"/>
        </g>
        <rect class="scan" x="24" y="44" width="52" height="2.5" rx="1.2" fill="#7fb2ff" opacity=".9"/>
      </svg>
    </div>
    <div>
      <h1>CYBER<span class="h1dash">—</span>FORGE<span class="h1tag">BATCH</span></h1>
      <p>外观专利图批处理引擎 · 批量调图 / 批量标注 / 批量改 XML</p>
    </div>
  </div>
  <nav class="tabs">
    <button class="tab on" id="tabBtn1">调整外观图</button>
    <button class="tab" id="tabBtn2">附图标注</button>
    <button class="tab" id="tabBtn3">XML 修改</button>
    <button class="tab" id="tabBtn4">特征关系分析</button>
  </nav>
</header>

<div id="tab1" class="wrap">

  <div class="card">
    <h2><span class="step">1</span>选择视图所在文件夹 / 文件</h2>
    <div class="row">
      <div class="field">
        <label>选择文件夹（自动识别 01~07）</label>
        <label class="filePick">
          <input type="file" id="folderInput" webkitdirectory directory multiple />
          <span class="filePickBtn">选择文件夹</span>
          <span class="filePickName">未选择文件夹</span>
        </label>
      </div>
      <div class="field">
        <label>或手动选择多个图片文件</label>
        <label class="filePick">
          <input type="file" id="filesInput" accept=".png,.bmp,.jpg,.jpeg" multiple />
          <span class="filePickBtn">选择图片</span>
          <span class="filePickName">未选择图片</span>
        </label>
      </div>
      <div class="field">
        <button class="ghost" id="resetBtn">清空重置</button>
      </div>
    </div>
    <div class="hint">自动映射优先级：文件名含 <b>01~07</b>（对应 主/后/左/右/俯/仰/立体）→ 关键字（主前/后/左/右/俯顶/仰底/立体stereo）→ 顺序兜底。支持 png / bmp / jpg / jpeg。</div>
    <div id="msg" class="msg"></div>
  </div>

  <div class="card">
    <h2><span class="step">2</span>视图映射与改前/改后预览</h2>
    <div class="row" style="margin-bottom:12px">
      <button id="uploadBtn">上传并计算</button>
      <span class="badge" id="statusBadge">未上传</span>
      <span id="busy"></span>
    </div>
    <div class="views" id="viewsGrid"><div class="zxEmpty">尚未载入视图。选择上面的<b>文件夹</b>或<b>图片文件</b>后点「上传并计算」，这里会显示七视图的映射与<b>改前 / 改后</b>对照。</div></div>
  </div>

  <div class="card">
    <h2><span class="step">3</span>对齐规则与参数</h2>
    <div class="grid2">
      <div>
        <div class="note" style="margin-top:0">
          <b>尺寸对齐规则（以主视图【产品】为基准）：</b><br/>
          · <b>主视图</b>按下方设定的<b>目标宽度/高度</b>调整（默认等于原始尺寸，可改；锁定比例则只改一项，另一项自动换算）<br/>
          · 其余视图按各自比例<b>等比缩放</b>（不变形）以对齐主视图：<br/>
          · 后视图 = 主视图（同宽同高）；左 / 右视图高度 = 主视图高度；俯 / 仰视图宽度 = 主视图宽度<br/>
          · 左 / 右视图宽度 = 俯 / 仰视图高度（统一「深度 D」），六视图盒子闭合<br/>
          · <b class="glitch">07 立体图</b>：默认宽度 <b>10cm</b>、高度 <b>&lt; 15cm</b>（等比，超出钳制）；可在下方自定义目标尺寸，<b>立体图可不上传</b>
        </div>
        <div class="field" style="margin-top:12px">
          <label>立体图目标尺寸（cm）</label>
          <div class="row" style="align-items:flex-end;gap:14px">
            <div class="field" style="margin:0">
              <label>宽度</label>
              <input type="number" id="stereoWcm" min="0.1" step="0.1" value="" placeholder="默认 10" style="width:90px" />
            </div>
            <div class="field" style="margin:0">
              <label>高度</label>
              <input type="number" id="stereoHcm" min="0.1" step="0.1" value="" placeholder="默认 ≤15" style="width:90px" />
            </div>
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text);margin-bottom:8px">
              <input type="checkbox" id="lockStereoRatio" checked /> 锁定宽高比
            </label>
          </div>
          <div class="hint" style="margin-top:6px">立体图<b>不是必须上传</b>的视图——未上传时跳过、不影响六视图处理。都不填则按默认规则（宽 10cm、高 &lt;15cm，等比）；只填一项则等比换算另一项；两项都填则精确调整为该尺寸。</div>
        </div>
        <div class="field" style="margin-top:12px">
          <label>主视图目标尺寸（cm）</label>
          <div class="row" style="align-items:flex-end;gap:14px">
            <div class="field" style="margin:0">
              <label>宽度</label>
              <input type="number" id="mainWcm" min="0.1" step="0.1" value="" placeholder="原始宽" style="width:90px" />
            </div>
            <div class="field" style="margin:0">
              <label>高度</label>
              <input type="number" id="mainHcm" min="0.1" step="0.1" value="" placeholder="原始高" style="width:90px" />
            </div>
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text);margin-bottom:8px">
              <input type="checkbox" id="lockMainRatio" checked /> 锁定宽高比
            </label>
          </div>
        </div>
        <div class="field" style="margin-top:12px">
          <label>产品轮廓识别（纯色背景）</label>
          <div class="row" style="align-items:center;gap:16px">
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text)">
              <input type="checkbox" id="cropOutline" checked /> 裁剪到产品轮廓
            </label>
            <div style="display:flex;align-items:center;gap:6px">
              <label style="margin:0">识别容差</label>
              <input type="number" id="tol" min="0" max="120" value="30" style="width:70px" />
            </div>
          </div>
        </div>
        <div class="field" style="margin-top:10px">
          <label>输出 PPI（全部统一）</label>
          <input type="number" id="targetPpi" min="1" value="300" />
        </div>
      </div>
      <div>
        <div class="tableWrap"><table id="sizeTable">
          <thead><tr><th>视图</th><th>产品原始(px)</th><th>整图(px)</th><th>原始PPI</th><th>目标 (px)</th><th>物理尺寸 (cm)</th></tr></thead>
          <tbody></tbody>
        </table></div>
        <div class="hint" id="dInfo" style="margin-top:8px"></div>
      </div>
    </div>
  </div>

  <div class="card">
    <h2><span class="step">4</span>布局对齐预览与导出</h2>
    <div class="grid2">
      <div>
        <label style="font-size:12px;color:var(--muted)">六视图对齐示意（改后缩略图；立体图独立处理，不参与盒子）</label>
        <canvas id="alignCanvas" width="700" height="560"></canvas>
      </div>
      <div>
        <label style="font-size:12px;color:var(--muted)">导出 · 直接覆盖原文件（由后台 Python 写盘，不再打包 ZIP）</label>
        <div class="note" style="margin-top:6px">
          在下方输入<b>原图所在的文件夹完整路径</b>（如 <b>D:\products\A001\视图</b>），点「覆盖原文件」后，
          后台会把每张改后图按<b>原文件名</b>直接写回该文件夹（保持原格式，写入 300 PPI）。<br/>
          ⚠ 覆盖后原图不可恢复，如有需要请先备份。
        </div>
        <div class="field" style="margin-top:12px">
          <label>原图所在文件夹（完整路径）</label>
          <input type="text" id="folderPath" placeholder="D:\products\A001\视图" style="width:100%" />
        </div>
        <div class="row" style="margin-top:12px; gap:10px; flex-wrap:wrap">
          <button id="overwriteBtn" disabled>覆盖原文件（后台写盘）</button>
          <button id="downloadBtn" disabled class="ghost">逐个下载（备选）</button>
          <span class="badge" id="statusBadge2">未就绪</span>
        </div>
        <div class="hint" style="margin-top:10px">提示：选择文件夹输入框（webkitdirectory）后，浏览器只提供相对路径；因此覆盖写盘需要粘贴完整路径。写盘由后台服务完成，无浏览器写盘限制。</div>
      </div>
    </div>
  </div>

</div><!-- /tab1 -->

<div id="tab2" class="wrap" style="display:none">

  <div class="card">
    <h2><span class="step">1</span>导入附图并转为专利线条图</h2>
    <div class="row">
      <div class="field">
        <label>导入图片（jpg / png / bmp，可多选）</label>
        <label class="filePick">
          <input type="file" id="figInput" accept=".png,.bmp,.jpg,.jpeg" multiple />
          <span class="filePickBtn">选择附图</span>
          <span class="filePickName">未选择图片</span>
        </label>
      </div>
      <div class="field">
        <label>线条图模式</label>
        <select id="figMode">
          <option value="edge">边缘检测（轮廓线条，白底黑线）</option>
          <option value="thresh">黑白阈值（剪影/大色块）</option>
          <option value="gray">灰度</option>
          <option value="raw">原图</option>
        </select>
      </div>
      <div class="field">
        <label id="figThreshLab">边缘阈值</label>
        <input type="range" id="figThresh" min="10" max="220" value="70" style="width:160px" />
      </div>
      <div class="field">
        <button class="ghost" id="figUndo">撤销标注</button>
      </div>
      <div class="field">
        <button class="ghost" id="figClear">清除全部标注</button>
      </div>
      <div class="field actions">
        <button id="figDownload">下载标注图 (JPG)</button>
        <button id="figDownloadPsd">下载分层 PSD</button>
      </div>
    </div>
    <div class="hint">线条图在浏览器本地生成：边缘检测模式（Sobel 算子）输出白底黑线的专利风格线条图；阈值模式把深色区域转为黑色块。阈值滑杆实时调整线条浓淡。</div>
  </div>

  <div class="card">
    <h2><span class="step">2</span>标注（点击两次完成一个标记）</h2>
    <div class="row" style="margin-bottom:12px">
      <div class="field">
        <label>标记内容（留空 = 自动编号 1,2,3…）</label>
        <input type="text" id="markLabel" placeholder="自动编号" style="width:220px" />
      </div>
      <div class="field">
        <label>引出线样式</label>
        <select id="markStyle">
          <option value="balloon">O</option>
          <option value="std">引线</option>
          <option value="wave">曲线</option>
          <option value="arrow">箭头</option>
          <option value="brace">括号</option>
        </select>
      </div>
      <div class="field">
        <label>序号圆圈大小</label>
        <input type="number" id="balloonR" min="8" max="40" value="14" style="width:80px" />
      </div>
      <div class="field">
        <label>文字尺寸 (px)</label>
        <input type="number" id="textSize" min="8" max="80" value="18" style="width:80px" />
      </div>
      <div class="field">
        <label>横线长度 (px，0=自动)</label>
        <input type="number" id="landLen" min="0" max="200" value="0" style="width:80px" />
      </div>
      <div class="field">
        <label>标注字体</label>
        <select id="fontFam">
          <option value='"Times New Roman",serif'>Times New Roman（衬线，专利常用）</option>
          <option value='Arial,"Helvetica Neue",sans-serif'>Arial（无衬线）</option>
          <option value='"SimSun","宋体",serif'>宋体</option>
          <option value='"SimHei","黑体",sans-serif'>黑体</option>
          <option value='"KaiTi","楷体",serif'>楷体</option>
        </select>
      </div>
    </div>
    <div class="hint">每张附图一个独立编辑区，可同时导入多张依次向下排列；点击某张附图的画布即切换为当前编辑图（带 ◆ 标记），上方工具栏和撤销/清除作用于当前图。每张附图单独下载 JPG / PSD。</div>
    <div id="figPages"></div>
    <div id="figEmpty" class="zxEmpty">尚未导入附图。选择图片后会在此生成独立的标注画布，可同时处理多张。</div>
  </div>

</div><!-- /tab2 -->

<div id="tab3" class="wrap" style="display:none">
  <div class="zxLayout"><div class="zxMain"><div class="card">
    <h2><span class="step">1</span>选择申请 ZIP</h2>
    <div class="row">
      <div class="field">
        <label>选择 ZIP（支持外层套内层的嵌套结构）</label>
        <label class="filePick">
          <input type="file" id="zxFile" accept=".zip" />
          <span class="filePickBtn">选择 ZIP</span>
          <span class="filePickName">未选择 ZIP</span>
        </label>
      </div>
      <div class="field">
        <label>&nbsp;</label>
        <button id="zxParse">解析 ZIP</button>
      </div>
    </div>
    <div id="zxStatus" class="msg"></div>
    <details class="zxFilesBox" id="zxFilesBox">
      <summary>
        <span class="zxFilesSum">文件清单</span>
        <span class="badge" id="zxFilesCnt">0 个文件</span>
        <span class="zxFilesTip">展开查看 ZIP 内全部文件与嵌套结构</span>
      </summary>
      <div id="zxFiles"></div>
    </details>
    <div class="hint">自动递归解包嵌套 ZIP，列出全部文件；XML 中的所有标签会在下方表格中列出，可直接编辑。图片/PDF 附件（如委托书扫描件）可在此替换。</div>
  </div>

  <div class="card" id="zxCards" style="display:none">
    <h2><span class="step">2</span>常用信息（快捷表单）</h2>
    <div class="zxGroup"><div class="zxGroupTitle">基本信息</div><div class="row" id="zxBase"></div></div>
    <div class="zxGroup"><div class="zxGroupTitle">申请人（第一申请人）</div><div class="row" id="zxApp"></div></div>
    <div class="zxGroup"><div class="zxGroupTitle" id="zxInvTitle">发明人</div><div id="zxInventors"></div></div>
    <div class="zxGroup"><div class="zxGroupTitle">代理与委托</div><div class="row" id="zxAgent"></div><div id="zxAgents"></div><div class="row" id="zxDate"></div>
      <div id="zxPoaBox" style="display:none">
        <div class="zxSubTitle">委托书扫描件 / 图片（可替换、可增减）</div>
        <div id="zxPoaImgs" class="zxImgs"></div>
        <div id="zxPoaBins" class="zxBins"></div>
      </div>
    </div>
    <div class="zxGroup" id="zxOptGroup" style="display:none"><div class="zxGroupTitle">选项与声明（复选框）</div><div id="zxOptions"></div></div>
    <div class="hint">快捷表单按标签自动匹配：同一信息在请求书/委托书/list.xml 等多处出现时会「同步修改 N 处」；未匹配到的字段留空并提示，可到下方「字段明细表」手动修改。省份/城市代码会显示为名称，保存时自动转回代码。</div>
  </div>

  <div class="card" id="zxTableCard" style="display:none">
    <h2><span class="step">3</span>XML 字段明细（按文档分组）</h2>
    <div class="row">
      <div class="field">
        <label>筛选（按标签/文件名/值）</label>
        <input type="text" id="zxFilter" placeholder="例如：发明名称 / 100007 / 柳州" style="min-width:280px" />
      </div>
      <div class="field">
        <label>&nbsp;</label>
        <span id="zxCount" class="badge"></span>
      </div>
    </div>
    <div id="zxDetail" style="margin-top:10px"></div>
  </div>

  <div class="card" id="zxSaveCard" style="display:none">
    <h2><span class="step">4</span>生成</h2>
    <div class="row">
      <button id="zxSave">生成并下载修改后的 ZIP</button>
      <button class="ghost" id="zxReset">重置全部修改</button>
    </div>
    <div id="zxSaveMsg" class="msg"></div>
    <div class="hint">只重写被修改的 XML 与替换的附件，其余文件按原始字节保留（含 DOCTYPE / xsl 样式表声明）；目录结构、内外层嵌套与文件名全部保持不变。</div>
  </div>
    <datalist id="zxDivList"></datalist>
  </div><!-- /zxMain -->
  </div><!-- /zxLayout -->
  <div class="zxImgModal" id="zxImgModal"><span class="close" id="zxImgClose">✕</span><img id="zxImgBig" alt="预览" /><div class="cap" id="zxImgCap"></div></div>
</div><!-- /tab3 -->

<div id="tab4" class="wrap" style="display:none">
  <div class="card">
    <h2><span class="step">1</span>粘贴权利要求书 / 说明书文本</h2>
    <textarea id="relText" rows="9" style="width:100%;background:#101820;color:#dbe4ed;border:1px solid #3a4756;border-radius:6px;padding:10px;font-size:13px;line-height:1.7"
      placeholder="例：一种切割装置，包括机架1、导轨组件2和驱动电机4……机架1上设置有真空泵5，切刀22通过螺栓连接固定在导轨组件2上……&#10;识别范围：包含/组成（包括、具有、设有…）、设置与位置（上设置有、固定于、套设于、穿过、之间设置有…）、连接与固定方式（螺栓/焊接/粘接/卡接/过盈配合/键连接/铰接/压铆/抱箍…约 150 种）、驱动与功能（传动连接、带动、控制、检测、密封、导向、限位、导电…）、上下位（为/是/属于/构成/A为B的一种/A、B均为C）、从属（A的B）、同类（第一/第二X）；没有附图标记时自动改用「装置/机构/组件/壳体/支架/轴/孔/槽…」等名词识别，长句会按「此外/同时/并且/而且」和权项编号自动断句"></textarea>
    <div class="row" style="margin-top:10px">
      <button id="relAnalyze">分析特征关系</button>
      <button class="ghost" id="relSample">填入示例</button>
      <span id="relMsg" class="msg"></span>
    </div>
    <div class="hint">粘贴后点击「分析特征关系」或按 Ctrl+Enter 提交；气泡大小 = 连接数（相连的特征越多气泡越大）；连线上标注关系，颜色区分类别（<span style="color:#25d98a">包含</span> / <span style="color:#4f9bff">连接</span> / <span style="color:#ffb224">固定</span> / <span style="color:#b06bff">位置</span> / <span style="color:#ff4d8d">驱动</span> / <span style="color:#22d3ee">上下位</span> / <span style="color:#94a3b8">从属</span>）；<b>拖动气泡可单独移动节点、拖动空白旋转视角、滚轮缩放、单击节点在右下角列出它的全部关系</b>。</div>
  </div>

  <div class="card" id="relGraphCard" style="display:none">
    <h2><span class="step">2</span>特征关系蛛网图（3D · 可交互）</h2>
    <div class="row" style="margin-bottom:8px;gap:8px;align-items:center">
      <button class="ghost" id="relReset">重置视角</button>
      <button class="ghost" id="relSpin">自动旋转：关</button>
      <span style="color:#7d8fa3;font-size:12px">拖动气泡可移动节点 · 拖动空白旋转 · 滚轮缩放 · 单击节点查看关系详情 · 双击居中</span>
    </div>
    <div style="position:relative">
      <canvas id="relCanvas" width="1200" height="680" style="width:100%;display:block;background:#0b1016;border-radius:8px;cursor:grab"></canvas>
      <div id="relLegend" style="position:absolute;right:14px;top:12px;font-size:12px;color:#9fb0c0;text-align:right;line-height:1.9;pointer-events:none"></div>
      <div id="relHover" style="position:absolute;left:14px;bottom:12px;font-size:12px;color:#cfe0f0"></div>
      <div id="relDetail" style="display:none;position:absolute;right:14px;bottom:12px;width:300px;max-height:64%;overflow:auto;background:rgba(10,16,22,0.93);border:1px solid #2b3b4c;border-radius:8px;padding:10px 12px"></div>
    </div>
  </div>
</div><!-- /tab4 -->

<script>
"use strict";
/* 后端固定监听 5000；通过 http://IP:5000 访问时自动跟随当前 host，双击 file:// 打开时回退到 127.0.0.1 */
const API = (location.protocol === 'http:' || location.protocol === 'https:')
  ? location.origin
  : 'http://127.0.0.1:5000';
function $(id){return document.getElementById(id);}

/* ---------- 标签页1：七视图（原版：文件夹/文件导入 + 视图映射 + 六视图盒子对齐 + 改前改后预览 + 覆盖/下载） ---------- */
const VIEWS = [
  {key:'main',   label:'主视图 (前)', cn:'主', keywords:['主','前','正','front','main']},
  {key:'back',   label:'后视图',      cn:'后', keywords:['后','背','back','rear']},
  {key:'left',   label:'左视图',      cn:'左', keywords:['左','left']},
  {key:'right',  label:'右视图',      cn:'右', keywords:['右','right']},
  {key:'top',    label:'俯视图 (顶)', cn:'俯', keywords:['俯','顶','top']},
  {key:'bottom', label:'仰视图 (底)', cn:'仰', keywords:['仰','底','bottom','bot']},
  {key:'stereo', label:'立体图 (07)', cn:'立', keywords:['立体','stereo','3d','三维']},
];
const ORDER = VIEWS.slice(0,6).map(v=>v.key);   // 六视图盒子
const ALL  = VIEWS.map(v=>v.key);               // 含立体图
const CODEMAP = {'01':'main','02':'back','03':'left','04':'right','05':'top','06':'bottom','07':'stereo'};

const state = {
  files: [], assignment: {}, origDims: {},
  before: {}, after: {}, afterImgs: {},
  sid: null, ready: false, busy: false,
  mainAspect: null, mainInited: false,
  stereoAspect: null, stereoInited: false,
};

/* ---------- 工具 ---------- */
function setMsg(t,type){const m=$('msg');m.textContent=t;m.className='msg '+(type||'');}
function $(id){return document.getElementById(id);}
function getParams(){
  const mw=parseFloat($('mainWcm').value), mh=parseFloat($('mainHcm').value);
  return {
    ppi: parseInt($('targetPpi').value,10)||300,
    crop: $('cropOutline').checked,
    tol: parseFloat($('tol').value)||30,
    main_w_cm: (isFinite(mw)&&mw>0)?mw:0,
    main_h_cm: (isFinite(mh)&&mh>0)?mh:0,
    stereo_w_cm: (isFinite(parseFloat($('stereoWcm').value))&&parseFloat($('stereoWcm').value)>0)?parseFloat($('stereoWcm').value):0,
    stereo_h_cm: (isFinite(parseFloat($('stereoHcm').value))&&parseFloat($('stereoHcm').value)>0)?parseFloat($('stereoHcm').value):0,
  };
}

/* ---------- 自动识别 ---------- */
function detectKey(name){
  const lower=name.toLowerCase();
  for(const code in CODEMAP){ if(lower.includes(code)) return CODEMAP[code]; }
  const m=lower.match(/(?:^|[^0-9])([1-7])(?=$|[^0-9])/);
  if(m) return ALL[parseInt(m[1],10)-1];
  for(const v of VIEWS){ for(const k of v.keywords){ if(lower.includes(k.toLowerCase())) return v.key; } }
  return null;
}

/* ---------- 文件读取 ---------- */
function readFileB64(file){
  return new Promise((resolve,reject)=>{
    const r=new FileReader();
    r.onload=()=>{
      const res=r.result; const prefix=res.indexOf(',');
      const b64=res.slice(prefix+1);
      const ext=(file.name.split('.').pop()||'png').toLowerCase().replace('jpeg','jpg');
      resolve({b64,ext});
    };
    r.onerror=()=>reject(new Error('读取失败'));
    r.readAsDataURL(file);
  });
}

/* ---------- 收集文件 ---------- */
async function ingest(fileList){
  const arr=Array.from(fileList).filter(f=>/\.(png|bmp|jpe?g)$/i.test(f.name));
  if(!arr.length){setMsg('未找到 png/bmp/jpg 图片文件。','warn');return;}
  state.files=arr.map(f=>({name:f.name, file:f, url:URL.createObjectURL(f)}));
  state.assignment={}; state.origDims={};
  for(const f of state.files){
    const k=detectKey(f.name);
    if(k && state.assignment[k]==null) state.assignment[k]=state.files.indexOf(f);
  }
  const unassigned=state.files.map((f,i)=>i).filter(i=>!Object.values(state.assignment).includes(i));
  for(const v of VIEWS){
    if(state.assignment[v.key]==null && unassigned.length) state.assignment[v.key]=unassigned.shift();
  }
  await Promise.all(state.files.map(async (f,i)=>{
    if(Object.values(state.assignment).includes(i)){
      const im=new Image();
      await new Promise(res=>{im.onload=res;im.src=f.url;});
      const vk=ALL.find(k=>state.assignment[k]===i);
      if(vk) state.origDims[vk]={w:im.naturalWidth,h:im.naturalHeight};
    }
  }));
  renderGrid();
  const auto=ALL.filter(k=>state.assignment[k]!=null && detectKey(state.files[state.assignment[k]].name)===k)
                .map(k=>VIEWS.find(v=>v.key===k).cn);
  setMsg(`已载入 ${state.files.length} 个文件。自动识别到：${auto.length?auto.join('、'):'无'}（可在下拉框手动调整，然后点“上传并计算”）。`,'ok');
  updateStatus();
}

/* ---------- 渲染映射网格 ---------- */
function renderGrid(){
  const grid=$('viewsGrid'); grid.innerHTML='';
  for(const v of VIEWS){
    const idx=state.assignment[v.key];
    const card=document.createElement('div');card.className='view'+(v.key==='stereo'?' stereo':'');
    const sel=document.createElement('select');
    const o0=document.createElement('option');o0.value='';o0.textContent='— 未选择 —';sel.appendChild(o0);
    state.files.forEach((f,i)=>{const o=document.createElement('option');o.value=i;o.textContent=f.name;sel.appendChild(o);});
    sel.value=(idx!=null)?String(idx):'';
    sel.addEventListener('change',()=>{
      state.assignment[v.key]=sel.value===''?null:parseInt(sel.value,10);
      state.after[v.key]=null; state.afterImgs[v.key]=null;
      updateStatus();
    });
    const ba=document.createElement('div');ba.className='ba';
    const before=document.createElement('div');before.className='col';
    before.innerHTML=`<div class="cap">改前（原图）</div><img id="before_${v.key}" alt=""><div class="dim" id="bdim_${v.key}"></div>`;
    const after=document.createElement('div');after.className='col';
    const capTxt = v.key==='stereo' ? '改后（可选，独立尺寸）' : '改后（实时）';
    after.innerHTML=`<div class="cap">${capTxt}</div><img id="after_${v.key}" alt=""><div class="dim" id="adim_${v.key}"></div>`;
    ba.appendChild(before);ba.appendChild(after);
    card.innerHTML=`<div class="vh"><b>${v.label}</b><span class="badge">${v.cn}</span></div>`;
    card.appendChild(sel);card.appendChild(ba);
    grid.appendChild(card);
    if(idx!=null){
      const b=state.before[v.key];
      const imgEl=$('before_'+v.key);
      if(b){
        imgEl.src=b.url;
        $('bdim_'+v.key).innerHTML = b.cropped
          ? `产品 <b>${b.product[0]}×${b.product[1]}</b> · 整图 ${b.full[0]}×${b.full[1]}`
          : `整图 <b>${b.full[0]}×${b.full[1]}</b>`;
      }else{
        imgEl.src=state.files[idx].url;
        const d=state.origDims[v.key];
        if(d) $('bdim_'+v.key).innerHTML=`${d.w}×${d.h} px`;
      }
    }
    if(state.after[v.key]) fillAfter(v.key, state.after[v.key]);
  }
}
function fillAfter(key, info){
  const im=$('after_'+key);
  if(!im)return;
  state.afterImgs[key]=new Image();
  state.afterImgs[key].onload=renderAlignment;
  state.afterImgs[key].src=info.afterUrl;
  im.src=info.afterUrl;
  $('adim_'+key).innerHTML=`<b>${info.w}×${info.h}</b>px · ${info.cm[0]}×${info.cm[1]}cm`;
}

/* ---------- 上传 + 预览 ---------- */
async function uploadThenPreview(){
  if(state.busy)return;
  if(state.assignment.main==null){setMsg('请先指定主视图（main/01）。','warn');return;}
  state.busy=true; setBusy(true);
  try{
    const images={}; let hasMain=false;
    for(const k of ALL){
      const idx=state.assignment[k];
      if(idx==null)continue;
      const {b64,ext}=await readFileB64(state.files[idx].file);
      images[k]=b64; images['_ext_'+k]=ext; images['_name_'+k]=state.files[idx].name;
      if(k==='main')hasMain=true;
    }
    if(!hasMain){setMsg('缺少主视图，无法上传。','warn');return;}
    const up=await fetch(API+'/api/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({images})});
    const upj=await up.json();
    if(!up.ok){setMsg('上传失败：'+(upj.error||'未知错误'),'err');return;}
    state.sid=upj.sid;
    await doPreview();
  }catch(e){ setMsg('上传/处理出错：'+e.message+'（请确认后台已启动：python server.py）','err'); }
  finally{ state.busy=false; setBusy(false); }
}
async function doPreview(){
  if(!state.sid)return;
  state.busy=true; setBusy(true);
  try{
    const body=Object.assign({sid:state.sid}, getParams());
    const r=await fetch(API+'/api/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json();
    if(!r.ok){setMsg('预览失败：'+(j.error||'未知'),'err');return;}
    state.after={}; state.afterImgs={}; state.before={};
    for(const k of ALL){
      if(j.views[k]){
        const v=j.views[k];
        state.after[k]={w:v.target[0],h:v.target[1],cm:v.cm,afterUrl:v.after};
        state.before[k]={url:v.before, full:v.full, product:v.orig, cropped:v.cropped};
      }
    }
    if(!state.mainInited && j.views.main){
      state.mainAspect = j.views.main.orig[0]/j.views.main.orig[1];
      if(!$('mainWcm').value) $('mainWcm').value = j.views.main.cm[0];
      if(!$('mainHcm').value) $('mainHcm').value = j.views.main.cm[1];
      state.mainInited=true;
    }
    if(!state.stereoInited && j.views.stereo){
      state.stereoAspect = j.views.stereo.orig[0]/j.views.stereo.orig[1];
      state.stereoInited=true;
    }
    renderGrid(); renderTableFromServer(j.views); renderAlignment();
    $('dInfo').textContent='深度 D = '+j.depthD+' px（左/右视图宽 = 俯/仰视图高）';
    const noOutline=ALL.filter(k=>j.views[k] && !j.views[k].cropped);
    const resized = j.views._main_resized;
    let msg = resized
      ? '已就绪。主视图已调整为 '+j.views._main_target_cm[0]+'×'+j.views._main_target_cm[1]+' cm，其余视图等比对齐。'
      : '已就绪。主视图保持原始尺寸，其余视图等比对齐。';
    if(noOutline.length) msg += '（'+noOutline.map(k=>VIEWS.find(x=>x.key===k).cn).join('、')+' 未检测到明显产品轮廓，已按整图处理）';
    if(j.notes && j.notes.length) msg += ' ⚠ ' + j.notes.join('；');
    setMsg(msg,'ok');
    state.ready=true;
  }catch(e){ setMsg('预览出错：'+e.message,'err'); }
  finally{ state.busy=false; setBusy(false); updateStatus(); }
}
let previewTimer=null;
function onParamChange(){
  if(!state.sid){return;}
  clearTimeout(previewTimer);
  previewTimer=setTimeout(doPreview,180);
}

/* ---------- 表格 ---------- */
function renderTableFromServer(views){
  const tb=document.querySelector('#sizeTable tbody');tb.innerHTML='';
  for(const v of VIEWS){
    const k=v.key, info=views[k];
    const tr=document.createElement('tr');
    if(!info){tr.innerHTML=`<td class="k">${v.label}</td><td colspan="5">未指定</td>`;tb.appendChild(tr);continue;}
    const o=info.orig.join('×'); const full=info.full.join('×'); const op=info.orig_ppi??'未知';
    const t=info.target.join('×'); const ph=info.cm.join('×');
    tr.innerHTML=`<td class="k">${v.label}</td><td>${o}</td><td>${full}</td><td>${op}</td><td>${t}</td><td>${ph}</td>`;
    tb.appendChild(tr);
  }
}

/* ---------- 对齐示意 ---------- */
function renderAlignment(){
  const cv=$('alignCanvas'); const ctx=cv.getContext('2d');
  ctx.clearRect(0,0,cv.width,cv.height);
  const main=state.after.main; if(!main)return;
  const W=main.w,H=main.h,D=state.after.left?state.after.left.w:Math.round(H);
  const totalW=2*(D+W), totalH=2*D+H;
  const scale=Math.min(cv.width/totalW,cv.height/totalH,1);
  const ox=(cv.width-totalW*scale)/2, oy=(cv.height-totalH*scale)/2;
  const layout={
    top:{x:D,y:0,w:W,h:D}, main:{x:D,y:D,w:W,h:H}, bottom:{x:D,y:D+H,w:W,h:D},
    left:{x:0,y:D,w:D,h:H}, right:{x:D+W,y:D,w:D,h:H}, back:{x:D+W+D,y:D,w:W,h:H},
  };
  const colors={main:'#4d8dff',back:'#8b9dff',left:'#3ddc97',right:'#3ddc97',top:'#f3b23c',bottom:'#f3b23c'};
  for(const key of ['left','top','main','right','bottom','back']){
    const L=layout[key], im=state.afterImgs[key];
    const dx=ox+L.x*scale,dy=oy+L.y*scale,dw=L.w*scale,dh=L.h*scale;
    ctx.fillStyle='#0b1120';ctx.fillRect(dx,dy,dw,dh);
    if(im && im.complete) ctx.drawImage(im,dx,dy,dw,dh);
    ctx.strokeStyle=colors[key];ctx.lineWidth=2;ctx.strokeRect(dx,dy,dw,dh);
    ctx.fillStyle=colors[key];ctx.font='700 18px system-ui, sans-serif';
    ctx.fillText(VIEWS.find(v=>v.key===key).cn,dx+4,dy+14);
  }
  ctx.fillStyle='#8b97ad';ctx.font='14px system-ui, sans-serif';
  ctx.fillText('左/主/右/后 等高 = H',ox,oy-6);
  ctx.fillText('俯/主/仰 等宽 = W',ox,oy+totalH*scale+14);
  ctx.fillText('左宽 = 俯高 = D',ox+D*scale/2-20,oy+D*scale-4);
  const st=state.after.stereo;
  if(st){
    const s=Math.min(140/st.w,140/st.h,1);
    const sx=cv.width-150, sy=10;
    ctx.fillStyle='#0b1120';ctx.fillRect(sx,sy,st.w*s,st.h*s);
    const im=state.afterImgs.stereo;
    if(im && im.complete) ctx.drawImage(im,sx,sy,st.w*s,st.h*s);
    ctx.strokeStyle='#a78bfa';ctx.lineWidth=2;ctx.strokeRect(sx,sy,st.w*s,st.h*s);
    ctx.fillStyle='#a78bfa';ctx.font='700 12.5px system-ui, sans-serif';
    ctx.fillText('立 '+st.cm[0]+'×'+st.cm[1]+'cm',sx,sy+st.h*s+14);
  }
}

/* ---------- 导出 ---------- */
async function fetchProcessed(){
  const body=Object.assign({sid:state.sid}, getParams());
  const r=await fetch(API+'/api/export_images',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok){const j=await r.json().catch(()=>({}));throw new Error(j.error||'未知');}
  return r.json();
}
function viewFileName(key){
  const idx=state.assignment[key];
  return idx!=null ? state.files[idx].name : null;
}
async function overwriteOriginals(){
  if(!state.sid||!state.ready)return;
  const folder=$('folderPath').value.trim();
  if(!folder){ setMsg('请先在输入框填写原图所在的文件夹完整路径（如 D:\\products\\A001\\视图）。','warn'); return; }
  if(!confirm('将把改后图按原文件名覆盖写入：\n'+folder+'\n\n原图将被覆盖且不可恢复，确认继续？')) return;
  setBusy(true);
  try{
    const body=Object.assign({sid:state.sid, folder}, getParams());
    const r=await fetch(API+'/api/export_disk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json();
    if(!r.ok){setMsg('写盘失败：'+(j.error||'未知'),'err');return;}
    let msg='已覆盖写回 '+j.written.length+' 个原文件。';
    if(j.failed && j.failed.length) msg+='（失败：'+j.failed.join('；')+'）';
    setMsg(msg, j.failed&&j.failed.length?'warn':'ok');
  }catch(e){ setMsg('写盘出错：'+e.message,'err'); }
  finally{ setBusy(false); }
}
async function downloadIndividually(){
  if(!state.sid||!state.ready)return;
  setBusy(true);
  try{
    const j=await fetchProcessed();
    let n=0;
    for(const v of ALL){
      const fname=viewFileName(v); if(!fname) continue;
      const b64=j.images[v]; if(!b64) continue;
      const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
      const blob=new Blob([bytes]); const url=URL.createObjectURL(blob);
      const a=document.createElement('a'); a.href=url; a.download=fname;
      document.body.appendChild(a); a.click();
      setTimeout(()=>{URL.revokeObjectURL(url);a.remove();},400);
      n++;
    }
    setMsg('已开始逐个下载 '+n+' 张改后图。','ok');
  }catch(e){ setMsg('下载出错：'+e.message,'err'); }
  finally{ setBusy(false); }
}

/* ---------- 状态 ---------- */
function setBusy(b){ $('busy').innerHTML=b?'<span class="spinner"></span>处理中…':''; }
function updateStatus(){
  const b=$('overwriteBtn'); const b2=$('downloadBtn'); const badge=$('statusBadge'); const badge2=$('statusBadge2');
  const ready=state.ready && !!state.sid;
  b.disabled=!ready; b2.disabled=!ready;
  badge.textContent=state.sid?'已上传':'未上传';
  badge2.textContent=ready?'就绪可导出':'未就绪';
}

/* ---------- 事件 ---------- */
$('folderInput').addEventListener('change',e=>ingest(e.target.files));
$('filesInput').addEventListener('change',e=>ingest(e.target.files));
$('uploadBtn').addEventListener('click',uploadThenPreview);
$('resetBtn').addEventListener('click',()=>{
  state.files=[];state.assignment={};state.origDims={};state.after={};state.afterImgs={};state.before={};
  state.sid=null;state.ready=false;state.mainAspect=null;state.mainInited=false;state.stereoAspect=null;state.stereoInited=false;
  $('mainWcm').value='';$('mainHcm').value='';$('lockMainRatio').checked=true;
  $('stereoWcm').value='';$('stereoHcm').value='';$('lockStereoRatio').checked=true;
  $('folderInput').value='';$('filesInput').value='';$('viewsGrid').innerHTML='';syncFilePick('folderInput');syncFilePick('filesInput');
  document.querySelector('#sizeTable tbody').innerHTML='';
  $('alignCanvas').getContext('2d').clearRect(0,0,$('alignCanvas').width,$('alignCanvas').height);
  setMsg('已清空。','');updateStatus();
});
['targetPpi','tol'].forEach(id=>$(id).addEventListener('input',onParamChange));
$('cropOutline').addEventListener('change',onParamChange);
function syncMainRatio(src){
  if($('lockMainRatio').checked && state.mainAspect){
    if(src==='w'){ const w=parseFloat($('mainWcm').value); if(isFinite(w)&&w>0) $('mainHcm').value=(w/state.mainAspect).toFixed(2); }
    else { const h=parseFloat($('mainHcm').value); if(isFinite(h)&&h>0) $('mainWcm').value=(h*state.mainAspect).toFixed(2); }
  }
  onParamChange();
}
$('mainWcm').addEventListener('input',()=>syncMainRatio('w'));
$('mainHcm').addEventListener('input',()=>syncMainRatio('h'));
$('lockMainRatio').addEventListener('change',()=>{ if($('lockMainRatio').checked) syncMainRatio('w'); else onParamChange(); });
function syncStereoRatio(src){
  if($('lockStereoRatio').checked && state.stereoAspect){
    if(src==='w'){ const w=parseFloat($('stereoWcm').value); if(isFinite(w)&&w>0) $('stereoHcm').value=(w/state.stereoAspect).toFixed(2); }
    else { const h=parseFloat($('stereoHcm').value); if(isFinite(h)&&h>0) $('stereoWcm').value=(h*state.stereoAspect).toFixed(2); }
  }
  onParamChange();
}
$('stereoWcm').addEventListener('input',()=>syncStereoRatio('w'));
$('stereoHcm').addEventListener('input',()=>syncStereoRatio('h'));
$('lockStereoRatio').addEventListener('change',()=>{ if($('lockStereoRatio').checked && $('stereoWcm').value) syncStereoRatio('w'); else onParamChange(); });
$('overwriteBtn').addEventListener('click',overwriteOriginals);
$('downloadBtn').addEventListener('click',downloadIndividually);

/* ---------- 文件选择器：显示所选文件 / 文件夹名称 ---------- */
function filePickText(inp){
  const fs = inp.files;
  if(!fs || !fs.length) return '';
  if(inp.hasAttribute('webkitdirectory')){
    const top = (fs[0].webkitRelativePath || '').split('/')[0];
    return (top ? top + '/ · ' : '') + fs.length + ' 个文件';
  }
  return fs.length === 1 ? fs[0].name : fs.length + ' 个文件';
}
function syncFilePick(id){
  const inp = $(id); if(!inp || !inp.parentElement) return;
  const nm = inp.parentElement.querySelector('.filePickName'); if(!nm) return;
  const t = filePickText(inp);
  const empty = inp.hasAttribute('webkitdirectory') ? '未选择文件夹' : '未选择文件';
  nm.textContent = t || empty;
  nm.classList.toggle('set', !!t);
}
['folderInput','filesInput','figInput','zxFile'].forEach(id=>{
  const inp = $(id); if(!inp) return;
  inp.addEventListener('change', ()=>syncFilePick(id));
});

/* ---------- 标签页切换 ---------- */
function showTab(n){
  for(let i=1;i<=4;i++){
    const el=$('tab'+i); if(el) el.style.display = n===i ? '' : 'none';
    const btn=$('tabBtn'+i); if(btn) btn.classList.toggle('on', n===i);
  }
  /* 把当前标签写进地址栏，刷新后仍停留在该标签 */
  try{ history.replaceState(null,'',location.pathname+'?tab='+n); }catch(e){}
  if(n===2 && fig && fig.work) redrawFig();
  if(n===4 && relGraph.hasData) relDraw();
}
$('tabBtn1').addEventListener('click',()=>showTab(1));
$('tabBtn2').addEventListener('click',()=>showTab(2));
$('tabBtn3').addEventListener('click',()=>showTab(3));
$('tabBtn4').addEventListener('click',()=>showTab(4));

/* ---------- 标签页2：附图标注（多附图：每张图一个独立编辑区） ---------- */
let fig=null;          // 当前编辑的附图页
const figPages=[];     // 全部附图页
let figSeq=0;

function figMsg(t,type){
  if(fig && fig.msgEl){ fig.msgEl.textContent=t; fig.msgEl.className='msg '+(type||''); }
}

$('figInput').addEventListener('change',e=>{
  const fs=[...(e.target.files||[])];
  e.target.value='';
  if(!fs.length) return;
  let done=0;
  for(const f of fs){
    const img=new Image();
    img.onload=()=>{
      addFigPage(f.name, img);
      if(++done===fs.length) figMsg('已导入 '+fs.length+' 张附图，点击附图区域切换编辑。','ok');
    };
    img.onerror=()=>{ done++; figMsg('图片加载失败：'+f.name,'err'); };
    img.src=URL.createObjectURL(f);
  }
});

function addFigPage(name, img){
  const id=++figSeq;
  // ---- DOM：附图编辑区 ----
  const sec=document.createElement('div');
  sec.className='figPage';
  sec.innerHTML=
    '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'+
      '<span class="figBadge" style="opacity:.45">附图'+id+'</span>'+
      '<span style="opacity:.7;font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+name+'（'+img.naturalWidth+'×'+img.naturalHeight+'px）</span>'+
      '<button class="ghost figDel" style="padding:2px 10px;font-size:12px">删除此图</button>'+
    '</div>'+
    '<div style="display:flex;gap:14px;align-items:flex-start">'+
      '<div style="flex:1;min-width:0"><canvas class="figCv" width="10" height="10"></canvas></div>'+
      '<div style="width:230px;flex:none">'+
        '<div class="field"><label>标注列表（可直接改编号）</label></div>'+
        '<div style="border:1px solid var(--line);border-radius:9px;background:var(--panel);max-height:520px;overflow:auto">'+
          '<table style="width:100%;border-collapse:collapse;font-size:13px;color:var(--fg,#eee)"><thead><tr>'+
          '<th style="padding:6px 8px;border-bottom:1px solid var(--line);text-align:left">#</th>'+
          '<th style="padding:6px 8px;border-bottom:1px solid var(--line);text-align:left">编号</th>'+
          '<th style="padding:6px 8px;border-bottom:1px solid var(--line);width:34px"></th>'+
          '</tr></thead><tbody></tbody></table>'+
          '<div class="figEmpty" style="padding:8px 10px;opacity:.6;font-size:12px">暂无标注</div>'+
        '</div>'+
      '</div>'+
    '</div>'+
    '<div class="msg" style="margin-top:8px"></div>';
  $('figPages').appendChild(sec);
  const figEmptyEl=$('figEmpty'); if(figEmptyEl) figEmptyEl.style.display='none';
  const page={
    id, name, img, work:null, scale:1, marks:[], pending:null, cursor:null, nextNum:1,
    canvas:sec.querySelector('.figCv'),
    tbody:sec.querySelector('tbody'),
    emptyEl:sec.querySelector('.figEmpty'),
    msgEl:sec.querySelector('.msg'),
    badge:sec.querySelector('.figBadge'),
    sec,
  };
  figPages.push(page);
  sec.querySelector('.figDel').addEventListener('click',()=>removeFigPage(page));
  bindFigCanvas(page);
  setActiveFig(page);
  buildWorkCanvas();
  return page;
}

function setActiveFig(p){
  fig=p;
  for(const pg of figPages){
    pg.sec.style.borderColor = pg===p ? 'var(--accent,#0ff)' : 'var(--line)';
    pg.badge.style.opacity = pg===p ? '1' : '.45';
    pg.badge.textContent = (pg===p?'◆ ':'') + '附图'+pg.id;
  }
}

function removeFigPage(p){
  const i=figPages.indexOf(p);
  if(i<0) return;
  figPages.splice(i,1);
  p.sec.remove();
  if(!figPages.length){ const e=$('figEmpty'); if(e) e.style.display=''; }
  if(fig===p){
    fig=figPages[Math.min(i,figPages.length-1)]||null;
    if(fig) setActiveFig(fig);
  }
  figMsg('已删除附图，剩余 '+figPages.length+' 张。','');
}

function bindFigCanvas(page){
  const cv=page.canvas;
  cv.addEventListener('mousedown',e=>{
    if(fig!==page) setActiveFig(page);
    if(!fig.work) return;
    const p=figPos(e);
    figPress=p; figDragged=false;
    figHadPending=!!fig.pending;
    if(!fig.pending){
      fig.pending={x:p.x,y:p.y};
      figMsg('已选定标注起点，拖拽拉伸引出线后松手固定（或再次点击）。','ok');
    }
  });
  cv.addEventListener('mousemove',e=>{
    if(fig!==page) setActiveFig(page);
    if(!fig.pending) return;
    let c=figPos(e);
    if(figPress && Math.hypot(c.x-figPress.x, c.y-figPress.y)>3) figDragged=true;
    if($('markStyle').value==='std') c=snapStd(c, fig.pending);
    fig.cursor=c;
    requestAnimationFrame(redrawFig);
  });
  cv.addEventListener('click',e=>{
    if(fig!==page) setActiveFig(page);
    if(!fig.work) return;
    if(figSuppressClick){ figSuppressClick=false; return; }
    if(!figHadPending) return;            // 第一次点击：起点已在 mousedown 时选定
    completeMark(figPos(e));              // 第二次点击：固定标注
  });
  cv.addEventListener('mouseup',e=>{
    if(fig!==page || !fig.work || !fig.pending) return;
    if(figDragged){                       // 拖拽后松手 → 直接固定标注
      figSuppressClick=true;
      completeMark(figPos(e));
    }
    figPress=null;
  });
  cv.addEventListener('mouseleave',()=>{
    if(fig===page && fig.pending){ fig.cursor=null; redrawFig(); }
  });
}

function buildWorkCanvas(){
  const img=fig.img;
  const maxW=1400, maxH=1000;
  fig.scale=Math.min(1, maxW/img.naturalWidth, maxH/img.naturalHeight);
  const w=Math.max(1,Math.round(img.naturalWidth*fig.scale));
  const h=Math.max(1,Math.round(img.naturalHeight*fig.scale));
  fig.work=document.createElement('canvas');
  fig.work.width=w; fig.work.height=h;
  const cv=fig.canvas; cv.width=w; cv.height=h;
  processFig();
}

function processFig(){
  if(!fig || !fig.img) return;
  const cv=fig.work, ctx=cv.getContext('2d');
  ctx.drawImage(fig.img,0,0,cv.width,cv.height);
  const mode=$('figMode').value;
  if(mode!=='raw'){
    const id=ctx.getImageData(0,0,cv.width,cv.height);
    const d=id.data, W=cv.width, H=cv.height;
    const gray=new Float32Array(W*H);
    for(let i=0,p=0;i<d.length;i+=4,p++){
      gray[p]=0.299*d[i]+0.587*d[i+1]+0.114*d[i+2];
    }
    const t=parseInt($('figThresh').value,10);
    if(mode==='edge'){
      const out=new Uint8ClampedArray(d.length);
      for(let p=0;p<W*H;p++){ out[p*4]=255; out[p*4+1]=255; out[p*4+2]=255; out[p*4+3]=255; }
      for(let y=1;y<H-1;y++){
        for(let x=1;x<W-1;x++){
          const i=y*W+x;
          const gx=-gray[i-W-1]-2*gray[i-1]-gray[i+W-1]+gray[i-W+1]+2*gray[i+1]+gray[i+W+1];
          const gy=-gray[i-W-1]-2*gray[i-W]-gray[i-W+1]+gray[i+W-1]+2*gray[i+W]+gray[i+W+1];
          const mag=Math.sqrt(gx*gx+gy*gy);
          if(mag>t){ const o=i*4; out[o]=out[o+1]=out[o+2]=0; }
        }
      }
      id.data.set(out);
    }else if(mode==='thresh'){
      for(let p=0;p<W*H;p++){
        const v=gray[p]<t?0:255, o=p*4;
        d[o]=d[o+1]=d[o+2]=v;
      }
    }else{ // gray
      for(let p=0;p<W*H;p++){
        const o=p*4;
        d[o]=d[o+1]=d[o+2]=Math.round(gray[p]);
      }
    }
    ctx.putImageData(id,0,0);
  }
  redrawFig();
}

function drawMark(ctx, m, s, ts, font, part){
  // part: undefined=完整绘制；'line'=仅引线图形；'text'=仅编号文字（用于 PSD 分层导出）
  ts = ts || 16;
  font = font || '"Times New Roman",serif';
  const x0=m.x0*s, y0=m.y0*s, x1=m.x1*s, y1=m.y1*s;
  const dx=x1-x0, dy=y1-y0;
  const len=Math.sqrt(dx*dx+dy*dy);
  const ux=(len>0)?dx/len:1, uy=(len>0)?dy/len:0;
  const px=-uy, py=ux;   // 垂直方向
  ctx.save();
  // 引出线笔画粗细固定 2px（随缩放）；横线长度由「横线长度」设置控制
  ctx.strokeStyle='#000'; ctx.fillStyle='#000'; ctx.lineWidth=Math.max(0.5, 2*s);
  ctx.lineCap='round';
  const landLen=parseFloat((window.$('landLen')||{value:0}).value)||0;
  if(m.style==='wave'){
    // 波浪线 = 两个圆弧（隆起方向相反）：随拉伸实时变形
    if(part!=='text' && len>2){
      const mx=x0+dx/2, my=y0+dy/2;
      const amp=Math.max(4*s, Math.min(len*0.18, 36*s));  // 随拉伸变化的弧高
      ctx.beginPath();
      ctx.moveTo(x0,y0);
      // 第一段圆弧：锚点 -> 中点（向垂直正方向隆起）
      ctx.quadraticCurveTo(x0+dx/4+px*amp, y0+dy/4+py*amp, mx, my);
      // 第二段圆弧：中点 -> 终点（向垂直反方向隆起）
      ctx.quadraticCurveTo(x0+dx*3/4-px*amp, y0+dy*3/4-py*amp, x1, y1);
      ctx.stroke();
    }
    if(part!=='line'){
      // 文字标记在引出线终点之外（沿引出方向外移，避免与波浪线末端干涉）
      ctx.font='bold '+Math.max(9,Math.round(ts*s))+'px '+font;
      const twv=ctx.measureText(m.label).width;
      const gap=twv/2 + 6*s;   // 文字中心距终点 = 半宽 + 间隙
      ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText(m.label, x1+ux*gap, y1+uy*gap);
      ctx.textAlign='left'; ctx.textBaseline='alphabetic';
    }
  }else if(m.style==='arrow'){
    // 箭头标注：镂空箭头指向被标注位置（起点），直线引出
    if(part!=='text'){
      const ah=Math.max(9*s, Math.min(15*s, len*0.35));
      const bx=x0+ux*ah, by=y0+uy*ah;              // 箭头底边中心（沿箭身方向回退）
      ctx.beginPath();
      ctx.moveTo(x0,y0);                            // 箭头尖端 = 被标注位置
      ctx.lineTo(bx+px*ah*0.35, by+py*ah*0.35);
      ctx.lineTo(bx-px*ah*0.35, by-py*ah*0.35);
      ctx.closePath(); ctx.stroke();                // 镂空：只描边不填充
      ctx.beginPath(); ctx.moveTo(bx,by); ctx.lineTo(x1,y1); ctx.stroke();
    }
    if(part!=='line'){
      // 数字位于引出线末端（尾部）之外，沿引出方向外移，避免与线干涉
      ctx.font='bold '+Math.max(9,Math.round(ts*s))+'px '+font;
      ctx.textAlign='center'; ctx.textBaseline='middle';
      const aoff=ts*s*0.9;
      ctx.fillText(m.label, x1+ux*aoff, y1+uy*aoff);
      ctx.textAlign='left'; ctx.textBaseline='alphabetic';
    }
  }else if(m.style==='brace'){
    // 大括号标注：放大的 { 字符（属图形，归入引线层）+ 编号文字
    const mx=x0+dx/2, my=y0+dy/2;
    const size=Math.max(12, Math.round(len*0.95));        // 括号高度≈拉伸长度
    const ang=Math.atan2(y0-y1, x0-x1);                    // 字形 +x 指向被标注端
    const cax=Math.cos(ang), cay=Math.sin(ang);
    if(part!=='text'){
      ctx.save();
      ctx.translate(mx,my); ctx.rotate(ang);
      ctx.font='200 '+size+'px '+font;   // 极细字重，括号线条更细
      ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText('{',0,0);
      ctx.restore();
    }
    if(part!=='line'){
      // 无引线：文字直接放在尖点外侧
      const cw=size*0.18;
      const sx=mx-cax*cw, sy=my-cay*cw;
      ctx.font='bold '+Math.max(10,Math.round(ts*s))+'px '+font;
      ctx.textAlign='center'; ctx.textBaseline='middle';
      const bgap=ts*s*0.8+cw;
      ctx.fillText(m.label, sx-cax*bgap, sy-cay*bgap);
      ctx.textAlign='left'; ctx.textBaseline='alphabetic';
    }
  }else if(m.style==='balloon'){
    // CAXA 生成序号样式：起点圆点 + 直线引出 + 终点序号圆圈（圈内数字）
    if(part!=='text'){
      const R=(m.r||14)*s;
      ctx.beginPath(); ctx.arc(x0,y0,3.5*s,0,Math.PI*2); ctx.fill();
      ctx.beginPath(); ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.stroke();
      // 白底圆圈盖住线端，再描边
      ctx.save();
      ctx.fillStyle='#fff'; ctx.strokeStyle='#000';
      ctx.lineWidth=Math.max(0.5, 2*s);
      ctx.beginPath(); ctx.arc(x1,y1,R,0,Math.PI*2); ctx.fill(); ctx.stroke();
      ctx.restore();
    }
    if(part!=='line'){
      const R=(m.r||14)*s;
      ctx.font='bold '+Math.round(R*0.95)+'px '+font;
      ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText(m.label, x1, y1);
      ctx.textAlign='left'; ctx.textBaseline='alphabetic';
    }
  }else{
    // 引线样式：横线段长度 = 全局设置的「横线长度」，0 = 自动（文字宽×1.5）
    ctx.font='bold '+Math.max(10,Math.round(ts*s))+'px '+font;
    const tw=ctx.measureText(m.label).width;
    const land=(landLen>0)?landLen*s:tw*1.5;
    const dir=(x1>=x0)?1:-1;
    if(part!=='text'){
      const dotR=3.5*s;
      ctx.beginPath(); ctx.arc(x0,y0,dotR,0,Math.PI*2); ctx.fill();
      ctx.beginPath(); ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.lineTo(x1+dir*land,y1); ctx.stroke();
    }
    if(part!=='line'){
      const cx=x1+dir*land/2;
      ctx.fillText(m.label, cx-tw/2, y1-6*s);
      ctx.textAlign='left'; ctx.textBaseline='alphabetic';
    }
  }
  ctx.restore();
}

function redrawFig(){
  if(!fig || !fig.work) return;
  const cv=fig.canvas, ctx=cv.getContext('2d');
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.drawImage(fig.work,0,0);
  const s=fig.scale;
  const ts=parseFloat($('textSize').value)||16;
  const font=$('fontFam').value;
  for(const m of fig.marks) drawMark(ctx,m,s,ts,font);
  if(fig.pending && fig.cursor){
    const style=$('markStyle').value;
    const label=$('markLabel').value || String(fig.nextNum);
    ctx.save(); ctx.globalAlpha=0.55;
    drawMark(ctx,{x0:fig.pending.x,y0:fig.pending.y,x1:fig.cursor.x,y1:fig.cursor.y,style,label,r:parseFloat($('balloonR').value)||14},s,ts,font);
    ctx.restore();
  }
}

function figPos(e){
  const cv=fig.canvas, r=cv.getBoundingClientRect();
  const sx=cv.width/r.width, sy=cv.height/r.height;
  return { x:(e.clientX-r.left)*sx/fig.scale, y:(e.clientY-r.top)*sy/fig.scale };
}

/* 引线样式磁性吸附：终点 X/Y 吸附到同侧最近引线标记的 X/Y（容差 20px） */
function snapStd(p, from){
  const side=p.x>=from.x?'right':'left';
  const tol=20;
  let sx=null, sy=null, best=Infinity;
  for(const m of fig.marks){
    if(m.style!=='std') continue;
    const ms=m.x1>=m.x0?'right':'left';
    if(ms!==side) continue;
    const d=Math.hypot(m.x1-p.x, m.y1-p.y);
    if(d<best){ best=d; sx=m.x1; sy=m.y1; }
  }
  if(best<Infinity){
    if(Math.abs(sx-p.x)<=tol) p.x=sx;      // 横线起点垂直对齐
    if(Math.abs(sy-p.y)<=tol) p.y=sy;      // 横线高度水平对齐
  }
  return p;
}

function completeMark(p){
  let label=$('markLabel').value.trim();
  if(!label){ label=String(fig.nextNum); }
  // 每次标记完成后数字自动 +1；自定义文本用完即清空，下次恢复自动编号
  if(/^\d+$/.test(label)) fig.nextNum=Math.max(fig.nextNum, parseInt(label,10)+1);
  else fig.nextNum++;
  $('markLabel').value='';
  const style=$('markStyle').value;
  // 引线样式：实时磁性吸附（拖拽过程中即生效）
  if(style==='std'){
    p=snapStd(p, fig.pending);
  }
  fig.marks.push({x0:fig.pending.x,y0:fig.pending.y,x1:p.x,y1:p.y,style,label,r:parseFloat($('balloonR').value)||14});
  fig.pending=null; fig.cursor=null;
  syncMarkTable();
  figMsg('标注「'+label+'」已固定（共 '+fig.marks.length+' 个）。继续点击可添加下一个。','ok');
  redrawFig();
}
let figSuppressClick=false;   // 拖拽松手完成标注后，抑制随后的 click 事件
let figPress=null;            // 本次按下的起点
let figDragged=false;         // 本次按下后是否发生了拖拽
let figHadPending=false;      // 按下时是否已有未完成标注（区分第一次/第二次点击）
document.addEventListener('keydown',e=>{
  if(e.key==='Escape' && fig && fig.pending){
    fig.pending=null; fig.cursor=null; redrawFig();
    figMsg('已取消当前标注。','');
  }
  // Ctrl+Z 撤销标注（文本框内输入时不拦截，保留原生撤销）
  if(e.ctrlKey && !e.shiftKey && !e.altKey && (e.key==='z'||e.key==='Z')){
    const t=e.target;
    if(t && (t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.isContentEditable)) return;
    if($('tab2').style.display!=='none' && fig && fig.work){
      e.preventDefault(); undoMark();
    }
  }
});

['figMode','figThresh'].forEach(id=>$(id).addEventListener('input',()=>{
  $('figThreshLab').textContent = $('figMode').value==='edge' ? '边缘阈值' : '黑/白阈值';
  processFig();
}));
// 标注全局参数变化 → 实时重绘
['textSize','balloonR','fontFam','landLen'].forEach(id=>$(id).addEventListener('input',redrawFig));
function undoMark(){
  if(!fig.marks.length) return;
  const m=fig.marks.pop();
  if(/^\d+$/.test(m.label) && parseInt(m.label,10)===fig.nextNum-1) fig.nextNum--;
  syncMarkTable(); redrawFig(); figMsg('已撤销上一个标注。','');
}
$('figUndo').addEventListener('click',undoMark);
$('figClear').addEventListener('click',()=>{
  fig.marks=[]; fig.pending=null; fig.nextNum=1;
  syncMarkTable(); redrawFig(); figMsg('已清除全部标注。','');
});

/* ===== 标注列表表格：与图中标注双向同步 ===== */
function syncMarkTable(){
  if(!fig) return;
  const tb=fig.tbody, empty=fig.emptyEl;
  tb.innerHTML='';
  empty.style.display = fig.marks.length ? 'none' : 'block';
  fig.marks.forEach((m,i)=>{
    const tr=document.createElement('tr');
    const td1=document.createElement('td');
    td1.textContent=i+1;
    td1.style.cssText='padding:3px 6px;border-bottom:1px solid var(--line);opacity:.7';
    const td2=document.createElement('td');
    td2.style.cssText='padding:2px 6px;border-bottom:1px solid var(--line)';
    const inp=document.createElement('input');
    inp.type='text'; inp.value=m.label;
    inp.style.cssText='width:100%;box-sizing:border-box;background:transparent;border:1px solid transparent;color:inherit;font:inherit;padding:2px 4px;outline:none';
    inp.addEventListener('focus',()=>{inp.style.borderColor='var(--line)';});
    inp.addEventListener('blur',()=>{inp.style.borderColor='transparent';});
    inp.addEventListener('input',()=>{
      const v=inp.value.trim();
      if(!v) return;                     // 不允许清空编号
      m.label=v;
      if(/^\d+$/.test(v)) fig.nextNum=Math.max(fig.nextNum, parseInt(v,10)+1);
      redrawFig();
    });
    td2.appendChild(inp);
    const td3=document.createElement('td');
    td3.style.cssText='padding:2px 4px;border-bottom:1px solid var(--line);text-align:center';
    const del=document.createElement('button');
    del.textContent='✕'; del.title='删除该标注';
    del.style.cssText='background:none;border:none;color:inherit;cursor:pointer;opacity:.6;font-size:12px';
    del.addEventListener('click',()=>{
      fig.marks.splice(i,1);
      // 重新计算自动编号：取现有数字编号最大值 +1
      let mx=0;
      for(const mm of fig.marks){ if(/^\d+$/.test(mm.label)) mx=Math.max(mx,parseInt(mm.label,10)); }
      fig.nextNum=mx+1;
      syncMarkTable(); redrawFig();
      figMsg('已删除标注 '+i+1+'。','');
    });
    td3.appendChild(del);
    tr.appendChild(td1); tr.appendChild(td2); tr.appendChild(td3);
    tb.appendChild(tr);
  });
}
$('figDownload').addEventListener('click',()=>{
  if(!fig || !fig.work){ figMsg('请先导入附图。','warn'); return; }
  redrawFig();
  // JPG 无透明通道：先铺白底再导出，质量 0.95
  const cv=fig.canvas, tmp=document.createElement('canvas');
  tmp.width=cv.width; tmp.height=cv.height;
  const tc=tmp.getContext('2d');
  tc.fillStyle='#fff'; tc.fillRect(0,0,tmp.width,tmp.height);
  tc.drawImage(cv,0,0);
  const url=tmp.toDataURL('image/jpeg',0.95);
  const a=document.createElement('a');
  a.href=url; a.download='标注图_'+Date.now()+'.jpg';
  document.body.appendChild(a); a.click();
  setTimeout(()=>{a.remove();},400);
  figMsg('已生成并下载标注图 JPG。','ok');
});

/* ===== 分层 PSD 导出：背景图 / 引线 / 编号 三个图层 ===== */
// PackBits 压缩（Photoshop RLE）
function packBits(src){
  const out=[]; let i=0;
  while(i<src.length){
    let run=1;
    while(i+run<src.length && src[i+run]===src[i] && run<128) run++;
    if(run>=2){ out.push(257-run&0xff, src[i]); i+=run; }
    else{
      const lit=[];
      while(i<src.length && lit.length<128){
        if(i+2<src.length && src[i]===src[i+1] && src[i]===src[i+2]) break;
        lit.push(src[i]); i++;
      }
      out.push(lit.length-1, ...lit);
    }
  }
  return Uint8Array.from(out);
}
function concatU8(arrs){
  let n=0; for(const a of arrs) n+=a.length;
  const out=new Uint8Array(n); let o=0;
  for(const a of arrs){ out.set(a,o); o+=a.length; }
  return out;
}
// layers: [{name, canvas}]（自底向上）；composite: 展平后的 canvas
function buildPSD(w,h,layers,composite){
  const chunks=[];
  // 大端字节序写入（PSD 规范为 big-endian）
  const dv16=v=>new Uint8Array([(v>>8)&255, v&255]);
  const dv32=v=>new Uint8Array([(v>>>24)&255, (v>>16)&255, (v>>8)&255, v&255]);
  const i16=v=>dv16(v<0 ? v+0x10000 : v);
  const ascii=str=>{const a=new Uint8Array(str.length);for(let i=0;i<str.length;i++)a[i]=str.charCodeAt(i)&0xff;return a;};
  // ---- 文件头 ----
  chunks.push(ascii('8BPS'), dv16(1), new Uint8Array(6), dv16(3), dv32(h), dv32(w), dv16(8), dv16(3));
  chunks.push(dv32(0));               // color mode data
  chunks.push(dv32(0));               // image resources
  // ---- 图层与蒙版信息 ----
  const recs=[], chDatas=[];
  for(const L of layers){
    const id=L.ctx.getImageData(0,0,w,h).data;
    // 拆 4 通道（A,R,G,B），按 PSD 顺序：-1 alpha, 0 R, 1 G, 2 B
    const chans=[new Uint8Array(w*h),new Uint8Array(w*h),new Uint8Array(w*h),new Uint8Array(w*h)];
    for(let p=0;p<w*h;p++){
      chans[0][p]=id[p*4+3]; chans[1][p]=id[p*4]; chans[2][p]=id[p*4+1]; chans[3][p]=id[p*4+2];
    }
    const comp=chans.map(ch=>{
      const rows=[];
      for(let y=0;y<h;y++) rows.push(packBits(ch.subarray(y*w,(y+1)*w)));
      // 每通道独立块：压缩标志 + 集中的行长度表 + 数据
      const parts=[dv16(1)];
      for(const r of rows) parts.push(dv16(r.length));
      for(const r of rows) parts.push(r);
      return concatU8(parts);
    });
    const chLen=comp.map(c=>c.length);
    let rec=concatU8([dv32(0),dv32(0),dv32(h),dv32(w)]);   // top,left,bottom,right（全幅图层）
    rec=concatU8([rec, dv16(4)]);
    rec=concatU8([rec, i16(-1), dv32(chLen[0]), dv16(0), dv32(chLen[1]),
                       dv16(1), dv32(chLen[2]), dv16(2), dv32(chLen[3])]);
    rec=concatU8([rec, ascii('8BIM'), ascii('norm'), new Uint8Array([255,0,0,0])]); // sig,blend,opacity,clipping,flags,filler
    // extra data：mask(0) + blending ranges(0) + pascal 图层名（4 字节对齐）
    const nm=' PSD-'+L.name;
    let nmB=new Uint8Array(nm.length+1); nmB[0]=nm.length;
    for(let i=0;i<nm.length;i++) nmB[i+1]=nm.charCodeAt(i)&0xff;
    const pad=new Uint8Array((4-(nmB.length%4))%4);
    const extra=concatU8([dv32(0), dv32(0), nmB, pad]);
    rec=concatU8([rec, dv32(extra.length), extra]);
    recs.push(rec); chDatas.push(concatU8(comp));
  }
  const layerInfoData=concatU8([dv16(layers.length), ...recs, ...chDatas]);
  // LMIS = [layerinfo长度u32（不含自身字段）][数据][全局蒙版信息u32=0]；外层长度含自身字段
  const lmis=concatU8([dv32(layerInfoData.length), layerInfoData, dv32(0)]);
  chunks.push(dv32(lmis.length), lmis);
  // ---- 合成图（展平 RGB，RLE；行长度表集中存放后再跟数据）----
  const cid=composite.getContext('2d').getImageData(0,0,w,h).data;
  const rgb=[new Uint8Array(w*h),new Uint8Array(w*h),new Uint8Array(w*h)];
  for(let p=0;p<w*h;p++){ rgb[0][p]=cid[p*4]; rgb[1][p]=cid[p*4+1]; rgb[2][p]=cid[p*4+2]; }
  const compEnc=rgb.map(ch=>{
    const rows=[];
    for(let y=0;y<h;y++) rows.push(packBits(ch.subarray(y*w,(y+1)*w)));
    return rows;
  });
  const cparts=[dv16(1)];
  for(const rows of compEnc) for(const r of rows) cparts.push(dv16(r.length)); // 3*h 行长度表
  for(const rows of compEnc) for(const r of rows) cparts.push(r);              // 全部数据
  chunks.push(concatU8(cparts));
  return new Blob(chunks, {type:'image/vnd.adobe.photoshop'});
}
$('figDownloadPsd').addEventListener('click',()=>{
  if(!fig || !fig.work){ figMsg('请先导入附图。','warn'); return; }
  if(!fig.marks.length){ figMsg('暂无标注，请先在图上标注。','warn'); return; }
  redrawFig();
  const cv=fig.canvas, w=cv.width, h=cv.height, s=fig.scale;
  const ts=parseFloat($('textSize').value)||16, font=$('fontFam').value;
  // 三个栅格图层画布：背景 / 引线 / 编号
  const mkCv=()=>{const c=document.createElement('canvas');c.width=w;c.height=h;return c;};
  const bg=mkCv(); bg.getContext('2d').drawImage(fig.work,0,0);
  const lineCv=mkCv(), textCv=mkCv();
  const lc=lineCv.getContext('2d'), tc=textCv.getContext('2d');
  for(const m of fig.marks){
    drawMark(lc,m,s,ts,font,'line');
    drawMark(tc,m,s,ts,font,'text');
  }
  // 展平合成图（白底 + 全部内容）
  const flat=mkCv(); const fc=flat.getContext('2d');
  fc.fillStyle='#fff'; fc.fillRect(0,0,w,h);
  fc.drawImage(bg,0,0); fc.drawImage(lineCv,0,0); fc.drawImage(textCv,0,0);
  const blob=buildPSD(w,h,[
    {name:'background', ctx:bg.getContext('2d')},
    {name:'leaders',    ctx:lc},
    {name:'numbers',    ctx:tc},
  ], flat);
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download='标注图分层_'+Date.now()+'.psd';
  document.body.appendChild(a); a.click();
  setTimeout(()=>{a.remove(); URL.revokeObjectURL(a.href);},600);
  figMsg('已生成并下载分层 PSD（背景图/引线/编号 三个栅格图层）。','ok');
});

/* ==================== 标签页3：XML 数据修改 ==================== */
const zxState = {
  sid:null, fname:'', fields:[], files:[], images:[],
  edits:{},               // id -> 修改后的值（字段明细表为唯一真源）
  sections:{},            // inventors / agents 草稿
  fileReplace:{},         // key -> {name, dataB64}
  imgDelete:new Set(),    // 待删除的图片/附件 key
  imgAdd:[],              // [{key, dir, name, size, dataB64, thumb, info, _added:true}]
};
const $zxMsg = m => { const el=$('zxStatus'); el.className='msg '+(m.t||''); el.textContent=m.s||''; };
const $zxSaveMsg = m => { const el=$('zxSaveMsg'); el.className='msg '+(m.t||''); el.textContent=m.s||''; };
const zxLast = seg => seg.replace(/\[\d+\]$/,'');   // 路径段去 [序号]

/* ---- 省/市 代码 ↔ 名称映射（GB/T 2260 省级 + 地级） ---- */
const ZX_DIV = {
  '110000':'北京市','120000':'天津市','130000':'河北省','140000':'山西省','150000':'内蒙古自治区',
  '210000':'辽宁省','220000':'吉林省','230000':'黑龙江省','310000':'上海市','320000':'江苏省',
  '330000':'浙江省','340000':'安徽省','350000':'福建省','360000':'江西省','370000':'山东省',
  '410000':'河南省','420000':'湖北省','430000':'湖南省','440000':'广东省','450000':'广西壮族自治区',
  '460000':'海南省','500000':'重庆市','510000':'四川省','520000':'贵州省','530000':'云南省',
  '540000':'西藏自治区','610000':'陕西省','620000':'甘肃省','630000':'青海省','640000':'宁夏回族自治区',
  '650000':'新疆维吾尔自治区','710000':'台湾省','810000':'香港特别行政区','820000':'澳门特别行政区',
  '110100':'市辖区','120100':'市辖区','310100':'市辖区','500100':'市辖区',
  '130100':'石家庄市','130200':'唐山市','130300':'秦皇岛市','130400':'邯郸市','130500':'邢台市','130600':'保定市','130700':'张家口市','130800':'承德市','130900':'沧州市','131000':'廊坊市','131100':'衡水市',
  '140100':'太原市','140200':'大同市','140300':'阳泉市','140400':'长治市','140500':'晋城市','140600':'朔州市','140700':'晋中市','140800':'运城市','140900':'忻州市','141000':'临汾市','141100':'吕梁市',
  '150100':'呼和浩特市','150200':'包头市','150300':'乌海市','150400':'赤峰市','150500':'通辽市','150600':'鄂尔多斯市','150700':'呼伦贝尔市','150800':'巴彦淖尔市','150900':'乌兰察布市','152200':'兴安盟','152500':'锡林郭勒盟','152900':'阿拉善盟',
  '210100':'沈阳市','210200':'大连市','210300':'鞍山市','210400':'抚顺市','210500':'本溪市','210600':'丹东市','210700':'锦州市','210800':'营口市','210900':'阜新市','211000':'辽阳市','211100':'盘锦市','211200':'铁岭市','211300':'朝阳市','211400':'葫芦岛市',
  '220100':'长春市','220200':'吉林市','220300':'四平市','220400':'辽源市','220500':'通化市','220600':'白山市','220700':'松原市','220800':'白城市','222400':'延边朝鲜族自治州',
  '230100':'哈尔滨市','230200':'齐齐哈尔市','230300':'鸡西市','230400':'鹤岗市','230500':'双鸭山市','230600':'大庆市','230700':'伊春市','230800':'佳木斯市','230900':'七台河市','231000':'牡丹江市','231100':'黑河市','231200':'绥化市','232700':'大兴安岭地区',
  '320100':'南京市','320200':'无锡市','320300':'徐州市','320400':'常州市','320500':'苏州市','320600':'南通市','320700':'连云港市','320800':'淮安市','320900':'盐城市','321000':'扬州市','321100':'镇江市','321200':'泰州市','321300':'宿迁市',
  '330100':'杭州市','330200':'宁波市','330300':'温州市','330400':'嘉兴市','330500':'湖州市','330600':'绍兴市','330700':'金华市','330800':'衢州市','330900':'舟山市','331000':'台州市','331100':'丽水市',
  '340100':'合肥市','340200':'芜湖市','340300':'蚌埠市','340400':'淮南市','340500':'马鞍山市','340600':'淮北市','340700':'铜陵市','340800':'安庆市','341000':'黄山市','341100':'滁州市','341200':'阜阳市','341300':'宿州市','341500':'六安市','341600':'亳州市','341700':'池州市','341800':'宣城市',
  '350100':'福州市','350200':'厦门市','350300':'莆田市','350400':'三明市','350500':'泉州市','350600':'漳州市','350700':'南平市','350800':'龙岩市','350900':'宁德市',
  '360100':'南昌市','360200':'景德镇市','360300':'萍乡市','360400':'九江市','360500':'新余市','360600':'鹰潭市','360700':'赣州市','360800':'吉安市','360900':'宜春市','361000':'抚州市','361100':'上饶市',
  '370100':'济南市','370200':'青岛市','370300':'淄博市','370400':'枣庄市','370500':'东营市','370600':'烟台市','370700':'潍坊市','370800':'济宁市','370900':'泰安市','371000':'威海市','371100':'日照市','371300':'临沂市','371400':'德州市','371500':'聊城市','371600':'滨州市','371700':'菏泽市',
  '410100':'郑州市','410200':'开封市','410300':'洛阳市','410400':'平顶山市','410500':'安阳市','410600':'鹤壁市','410700':'新乡市','410800':'焦作市','410900':'濮阳市','411000':'许昌市','411100':'漯河市','411200':'三门峡市','411300':'南阳市','411400':'商丘市','411500':'信阳市','411600':'周口市','411700':'驻马店市','419001':'济源市',
  '420100':'武汉市','420200':'黄石市','420300':'十堰市','420500':'宜昌市','420600':'襄阳市','420700':'鄂州市','420800':'荆门市','420900':'孝感市','421000':'荆州市','421100':'黄冈市','421200':'咸宁市','421300':'随州市','422800':'恩施土家族苗族自治州','429004':'仙桃市','429005':'潜江市','429006':'天门市','429021':'神农架林区',
  '430100':'长沙市','430200':'株洲市','430300':'湘潭市','430400':'衡阳市','430500':'邵阳市','430600':'岳阳市','430700':'常德市','430800':'张家界市','430900':'益阳市','431000':'郴州市','431100':'永州市','431200':'怀化市','431300':'娄底市','433100':'湘西土家族苗族自治州',
  '440100':'广州市','440200':'韶关市','440300':'深圳市','440400':'珠海市','440500':'汕头市','440600':'佛山市','440700':'江门市','440800':'湛江市','440900':'茂名市','441200':'肇庆市','441300':'惠州市','441400':'梅州市','441500':'汕尾市','441600':'河源市','441700':'阳江市','441800':'清远市','441900':'东莞市','442000':'中山市','445100':'潮州市','445200':'揭阳市','445300':'云浮市',
  '450100':'南宁市','450200':'柳州市','450300':'桂林市','450400':'梧州市','450500':'北海市','450600':'防城港市','450700':'钦州市','450800':'贵港市','450900':'玉林市','451000':'百色市','451100':'贺州市','451200':'河池市','451300':'来宾市','451400':'崇左市',
  '460100':'海口市','460200':'三亚市','460300':'三沙市','460400':'儋州市',
  '510100':'成都市','510300':'自贡市','510400':'攀枝花市','510500':'泸州市','510600':'德阳市','510700':'绵阳市','510800':'广元市','510900':'遂宁市','511000':'内江市','511100':'乐山市','511300':'南充市','511400':'眉山市','511500':'宜宾市','511600':'广安市','511700':'达州市','511800':'雅安市','511900':'巴中市','512000':'资阳市','513200':'阿坝藏族羌族自治州','513300':'甘孜藏族自治州','513400':'凉山彝族自治州',
  '520100':'贵阳市','520200':'六盘水市','520300':'遵义市','520400':'安顺市','520500':'毕节市','520600':'铜仁市','522300':'黔西南布依族苗族自治州','522600':'黔东南苗族侗族自治州','522700':'黔南布依族苗族自治州',
  '530100':'昆明市','530300':'曲靖市','530400':'玉溪市','530500':'保山市','530600':'昭通市','530700':'丽江市','530800':'普洱市','530900':'临沧市','532300':'楚雄彝族自治州','532500':'红河哈尼族彝族自治州','532600':'文山壮族苗族自治州','532800':'西双版纳傣族自治州','532900':'大理白族自治州','533100':'德宏傣族景颇族自治州','533300':'怒江傈僳族自治州','533400':'迪庆藏族自治州',
  '540100':'拉萨市','540200':'日喀则市','540300':'昌都市','540400':'林芝市','540500':'山南市','540600':'那曲市','542500':'阿里地区',
  '610100':'西安市','610200':'铜川市','610300':'宝鸡市','610400':'咸阳市','610500':'渭南市','610600':'延安市','610700':'汉中市','610800':'榆林市','610900':'安康市','611000':'商洛市',
  '620100':'兰州市','620200':'嘉峪关市','620300':'金昌市','620400':'白银市','620500':'天水市','620600':'武威市','620700':'张掖市','620800':'平凉市','620900':'酒泉市','621000':'庆阳市','621100':'定西市','621200':'陇南市','622900':'临夏回族自治州','623000':'甘南藏族自治州',
  '630100':'西宁市','630200':'海东市','632200':'海北藏族自治州','632300':'黄南藏族自治州','632500':'海南藏族自治州','632600':'果洛藏族自治州','632700':'玉树藏族自治州','632800':'海西蒙古族藏族自治州',
  '640100':'银川市','640200':'石嘴山市','640300':'吴忠市','640400':'固原市','640500':'中卫市',
  '650100':'乌鲁木齐市','650200':'克拉玛依市','650400':'吐鲁番市','650500':'哈密市','652300':'昌吉回族自治州','652700':'博尔塔拉蒙古自治州','652800':'巴音郭楞蒙古自治州','652900':'阿克苏地区','653000':'克孜勒苏柯尔克孜自治州','653100':'喀什地区','653200':'和田地区','654000':'伊犁哈萨克自治州','654200':'塔城地区','654300':'阿勒泰地区',
  '659001':'石河子市','659002':'阿拉尔市','659003':'图木舒克市','659004':'五家渠市','659006':'铁门关市','659007':'双河市','659008':'可克达拉市','659009':'昆玉市','659010':'胡杨河市','659011':'白杨市','659012':'新星市'
};
const ZX_DIV_REV = {}; for(const _c in ZX_DIV){ ZX_DIV_REV[ZX_DIV[_c]] = _c; }
(function(){
  const dl=document.getElementById('zxDivList'); if(!dl) return;
  for(const _c in ZX_DIV){
    const _n=ZX_DIV[_c];
    if(_n==='市辖区') continue;            // 直辖市市辖区名称歧义，不进候选
    const _o=document.createElement('option'); _o.value=_n; dl.appendChild(_o);
  }
})();

/* ---- 文档类型分类：把每个文件/字段归入分组容器 ---- */
const ZX_DOCS = [
  {key:'req',    label:'请求书',       codes:['110101','120101','130101']},
  {key:'poa',    label:'委托书',       codes:['100007']},
  {key:'claims', label:'权利要求书',   codes:['100001']},
  {key:'desc',   label:'说明书',       codes:['100002']},
  {key:'draw',   label:'说明书附图',   codes:['100003']},
  {key:'abs',    label:'说明书摘要',   codes:['100004']},
  {key:'brief',  label:'简要说明',     codes:['130002']},
  {key:'pic',    label:'外观设计图片', codes:['130001']},
];
const ZX_DOC_LABEL = {}; ZX_DOCS.forEach(d=>ZX_DOC_LABEL[d.key]=d.label);
ZX_DOC_LABEL.other = '其他文件（通知书 / 实质审查 / PDF 等）';
const ZX_DOC_ORDER = ['draw','abs','brief','pic','other'];
// 请求书 / 委托书 / 权利要求书 / 说明书 不单独成组：
// 请求书字段并入「常用信息」快捷表单，委托书图片并入「代理与委托」，
// 权利要求书与说明书正文篇幅长、通常无需逐字段核对，默认不在此列出。
const ZX_DOC_HIDDEN = ['req','poa','claims','desc'];

// 文件逻辑路径（去掉外层 ZIP 前缀）
function zxInnerPath(key){ return key.split('>').pop(); }
// 取文档目录 6 位代码（如 100001 / 130101）
function zxDocCode(key){
  const p = zxInnerPath(key);
  const m = p.match(/\/(\d{6})\//);
  return m ? m[1] : null;
}
function zxDocKey(key){
  const code = zxDocCode(key);
  if(code){ const d = ZX_DOCS.find(x=>x.codes.includes(code)); if(d) return d.key; }
  return 'other';
}

/* 省市控件：显示名称，保存代码 */
function zxMakeDiv(id, codeValue){
  const inp=document.createElement('input'); inp.type='text';
  inp.setAttribute('list','zxDivList');
  inp.placeholder='输入省市名称或6位代码';
  inp.value = ZX_DIV[codeValue] || codeValue;
  const resolve = v=>{ v=(v||'').trim();
    if(ZX_DIV_REV[v]) return ZX_DIV_REV[v];
    if(/^\d{4,6}$/.test(v)) return v;
    return v; };
  inp.addEventListener('input', ()=>{ const v=inp.value.trim();
    if(ZX_DIV_REV[v] || /^\d{6}$/.test(v)) zxState.edits[id]=resolve(v); });
  inp.addEventListener('change', ()=>{ const c=resolve(inp.value);
    zxState.edits[id]=c; inp._code=c; inp.value=ZX_DIV[c]||c; });
  inp._code = ZX_DIV[codeValue] ? codeValue : codeValue;
  return inp;
}

/* ---- 快捷表单字段定义：match=标签名候选，scope=整路径须包含 ---- */
const ZX_QUICK = [
  {key:'anjh',  label:'档案号（内部编号）', match:['内部编号','NEIBUBH'], group:'base'},
  {key:'sqh',   label:'申请号',             match:['申请号','SHENQINGH'], group:'base'},
  {key:'title', label:'专利名称',           match:['发明名称','委托代办发明名称','FAMINGMC','实用新型名称','外观设计名称','发明创造名称','invention-title'], group:'base'},
  {key:'sqmc',  label:'申请人名称',         match:['姓名或名称'], scope:'第一申请人', group:'app'},
  {key:'xydm',  label:'社会信用代码 / 身份证号', match:['身份证件号码或统一社会信用代码'], group:'app'},
  {key:'dz',    label:'地址（街道门牌号）', match:['城区乡街道门牌号'], scope:'第一申请人', group:'app'},
  {key:'yb',    label:'邮政编码',           match:['邮政编码'], scope:'第一申请人', group:'app'},
  {key:'dh',    label:'电话',               match:['电话'], scope:'第一申请人', group:'app'},
  {key:'sheng', label:'省级区划代码',       match:['省自治区直辖市名称'], scope:'第一申请人', group:'app'},
  {key:'shi',   label:'市县区划代码',       match:['市县名称'], scope:'第一申请人', group:'app'},
];

function zxMatchFields(q){
  // 返回匹配的字段 id 列表
  return zxState.fields
    .filter(f=>{
      const last = zxLast(f.path.split('/').pop());
      if(!q.match.includes(last)) return false;
      if(q.scope && !f.path.includes(q.scope)) return false;
      return true;
    }).map(f=>f.id);
}

/* ---- 解析 ZIP ---- */
async function zxParse(file){
  const buf = await file.arrayBuffer();
  let bin=''; const u8=new Uint8Array(buf);
  for(let i=0;i<u8.length;i+=8192) bin+=String.fromCharCode.apply(null,u8.subarray(i,i+8192));
  const b64 = btoa(bin);
  $zxMsg({t:'',s:''});
  let r;
  try{
    r = await (await fetch(API+'/api/zipxml_info', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({zipB64:b64}),
    })).json();
  }catch(e){ $zxMsg({t:'err',s:'请求失败：'+e.message}); return; }
  if(r.error){ $zxMsg({t:'err',s:r.error}); return; }
  zxState.sid=r.sid; zxState.fname=file.name;
  zxState.fields=r.fields; zxState.files=r.files; zxState.images=r.images||[];
  zxState.edits={}; zxState.fileReplace={}; zxState.sections={}; zxState.imgDelete=new Set(); zxState.imgAdd=[];
  const nimg = r.images? r.images.length : 0;
  $zxMsg({t:'ok', s:'解析完成：'+r.files.length+' 个文件，'+r.fields.length+' 个 XML 标签，'+nimg+' 张附图。'});
  zxRenderFiles(); zxRenderQuick(); zxRenderDetail();
  $('zxCards').style.display=''; $('zxTableCard').style.display=''; $('zxSaveCard').style.display='';
}

/* ---- 文件清单（只读清单，替换在下方各分组内联完成） ---- */
function zxRenderFiles(){
  const wrap = $('zxFiles'); wrap.innerHTML='';
  // 从 100007.xml（委托书）找扫描件文件名
  const scanNames = zxState.fields
    .filter(f=>f.path.includes('图片或照片') && zxLast(f.path.split('/').pop())==='文件名称')
    .map(f=>f.value.trim()).filter(Boolean);
  let n=0;
  for(const fi of zxState.files){
    const shortName = fi.key.split('>').pop();
    const segs = shortName.split('/');
    const base = segs[segs.length-1];
    const dirTxt = segs.slice(0,-1).join('/');
    const isScan = scanNames.some(sn=>shortName.includes(sn)||sn.includes(shortName));
    const kind = fi.xml ? 'xml' : (fi.img ? 'img' : 'bin');
    const kindTxt = fi.xml ? 'XML' : (fi.img ? '图片' : '附件');
    const row=document.createElement('div'); row.className='zxFileRow';
    row.title = fi.key;
    row.innerHTML = '<span class="fk kind '+kind+'">'+kindTxt+'</span>'
      + '<span class="fname">'+base.replace(/</g,'&lt;')+'</span>'
      + '<span class="fdir">'+(dirTxt?dirTxt.replace(/</g,'&lt;'):'')+'</span>'
      + '<span class="fsize">'+(fi.size/1024).toFixed(1)+' KB</span>'
      + (isScan?'<span class="scanflag">委托书扫描件</span>':'')
      + (zxState.fileReplace[fi.key]?'<span class="scanflag">已替换</span>':'');
    wrap.appendChild(row); n++;
  }
  if(!n) wrap.innerHTML='<div class="zxNoImg">（无文件）</div>';
  const cnt=$('zxFilesCnt');
  if(cnt){
    const nXml=zxState.files.filter(f=>f.xml).length, nImg=zxState.files.filter(f=>f.img).length;
    cnt.textContent = n+' 个文件 · XML '+nXml+' · 图片 '+nImg;
  }
}

/* ---- 字段明细：单个字段的紧凑卡片 ---- */
function zxFieldItem(f, label){
  const item=document.createElement('div'); item.className='zxField';
  item.title = f.path;
  if(label!==false){
    const p=document.createElement('div'); p.className='fpath';
    p.textContent = (label===undefined) ? f.path : label;
    p.title = f.path;
    item.appendChild(p);
  }
  if(f.type==='checkbox'){
    const lab=document.createElement('label'); lab.className='chk';
    const box=document.createElement('input'); box.type='checkbox';
    box.checked=(f.value==='1'); box.dataset.zxid=f.id;
    box.addEventListener('change', ()=>{
      const v=box.checked?'1':'0';
      if(v===f.value) delete zxState.edits[f.id]; else zxState.edits[f.id]=v;
    });
    const sp=document.createElement('span'); sp.textContent='勾选 = 1';
    lab.appendChild(box); lab.appendChild(sp); item.appendChild(lab);
  } else if(f.type==='div'){
    const inp=zxMakeDiv(f.id, f.value); inp.dataset.zxid=f.id; item.appendChild(inp);
  } else {
    const inp=document.createElement('input'); inp.type='text'; inp.value=f.value; inp.dataset.zxid=f.id;
    inp.addEventListener('input', ()=>{
      if(inp.value===f.value) delete zxState.edits[f.id]; else zxState.edits[f.id]=inp.value;
    });
    item.appendChild(inp);
  }
  return item;
}

/* ---- 图片增减辅助：目录推导 / 新文件命名 ---- */
// 逻辑 key -> 所在目录 key（保留嵌套 ZIP 前缀）
function zxDirOf(key){
  const i=key.lastIndexOf('>');
  const head=key.slice(0,i+1), tail=key.slice(i+1);
  const j=tail.lastIndexOf('/');
  return j<0 ? head : head+tail.slice(0,j);
}
function zxBaseName(key){ return key.split('>').pop().split('/').pop(); }
// 某分组的图片目录：优先从已有图片取，其次从该分组任意文件取
function zxGroupDir(dk){
  const im=(zxState.images||[]).find(x=>zxDocKey(x.key)===dk);
  if(im) return zxDirOf(im.key);
  const fi=(zxState.files||[]).find(x=>zxDocKey(x.key)===dk);
  if(fi) return zxDirOf(fi.key);
  return null;
}
// 目录下的下一个序号文件名（沿用已有扩展名）
function zxNextName(dir){
  const names=(zxState.images||[]).filter(x=>zxDirOf(x.key)===dir).map(x=>zxBaseName(x.key));
  (zxState.imgAdd||[]).forEach(a=>{ if(a.dir===dir) names.push(zxBaseName(a.key)); });
  let max=0, ext='.jpg';
  names.forEach(n=>{
    const m=n.match(/(\d+)/); if(m) max=Math.max(max, parseInt(m[1],10));
    const e=n.match(/\.[A-Za-z0-9]+$/); if(e) ext=e[0].toLowerCase();
  });
  return String(max+1).padStart(6,'0')+ext;
}
// 分组下（未被删除的）图片 + 新增图片
function zxImagesOf(dk){
  const live=(zxState.images||[]).filter(im=>zxDocKey(im.key)===dk && !zxState.imgDelete.has(im.key));
  const added=(zxState.imgAdd||[]).filter(a=>zxDocKey(a.key)===dk);
  return live.concat(added);
}

/* ---- 图片卡片：内联缩略图 + 点击放大 + 拖拽/选择替换 + 删除/恢复 ---- */
async function zxNormImage(file, profile){
  const b64 = await new Promise(res=>{
    const rd=new FileReader(); rd.onload=()=>res((rd.result||'').split(',')[1]||''); rd.readAsDataURL(file);
  });
  const r = await fetch(API+'/api/zipxml_norm_image',{
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({dataB64:b64, profile})
  });
  const j = await r.json();
  if(!j.ok) throw new Error(j.error||'归一化失败');
  return j;
}

function zxImgSlot(im){
  const isAdded = !!im._added;
  const dk = zxDocKey(im.key);
  const profile = (dk==='pic') ? 'appearance' : 'other';
  const limitTxt = (profile==='appearance')
    ? '限制 72–300PPI · 宽15 × 高≤22cm'
    : '限制 72–300PPI · 宽≤16.5 × 高≤24.5cm';
  const deleting = !isAdded && zxState.imgDelete.has(im.key);
  const card=document.createElement('div'); card.className='zxImgCard';
  if(isAdded) card.classList.add('added');
  else if(zxState.fileReplace[im.key]) card.classList.add('replaced');
  if(deleting) card.classList.add('deleted');
  const img=document.createElement('img'); img.alt=im.name||zxBaseName(im.key); img.loading='lazy';
  img.src=im._preview||im.thumb||im.full||'';
  if(!img.src){ card.className='zxNoImg'; card.textContent='无法生成预览：'+(im.err||'未知格式'); return card; }
  card.appendChild(img);
  const nm=document.createElement('div'); nm.className='nm';
  nm.textContent=(im.name||zxBaseName(im.key))+' · '+(im.size/1024).toFixed(1)+' KB'; card.appendChild(nm);
  const lim=document.createElement('div'); lim.className='lim'; lim.textContent=limitTxt; card.appendChild(lim);
  const rp=document.createElement('div'); rp.className='rp';
  rp.textContent = isAdded ? '新增' : (deleting ? '待删除' : '已替换');
  card.appendChild(rp);
  const res=document.createElement('div'); res.className='res'; card.appendChild(res);
  const ov=document.createElement('div'); ov.className='ov'; ov.textContent='拖入图片替换 · 点击放大'; card.appendChild(ov);
  if(isAdded && im.info){
    res.innerHTML = '适配：'+im.info.cmW+' × '+im.info.cmH+' cm @'+im.info.ppi+'PPI'
      + '（'+im.info.w+'×'+im.info.h+'px）'+(im.info.warn?'  ⚠':'');
    res.classList.toggle('warn', !!im.info.warn);
  }

  const setReplaced=(info, dataUrl)=>{
    if(isAdded){
      im.dataB64=info.dataB64; im.thumb=dataUrl; im.full=dataUrl;
      im._preview=dataUrl; im.size=Math.round(info.dataB64.length*0.75); im.info=info;
    }else{
      zxState.fileReplace[im.key]={name:im.key, dataB64:info.dataB64, info};
      im._preview=dataUrl;
    }
    card.classList.add('replaced');
    const flag = info.warn ? '  ⚠' : '';
    res.innerHTML = '适配：'+info.cmW+' × '+info.cmH+' cm @'+info.ppi+'PPI'
      + '（'+info.w+'×'+info.h+'px）'+flag;
    res.classList.toggle('warn', !!info.warn);
  };
  const replace=async (file)=>{
    if(!file) return;
    if(!/^image\//.test(file.type)){ $zxMsg({t:'warn',s:'请拖入图片文件'}); return; }
    $zxMsg({t:'', s:'正在适配尺寸…'});
    try{
      const info = await zxNormImage(file, profile);
      const dataUrl='data:image/jpeg;base64,'+info.dataB64;
      img.src=dataUrl;
      setReplaced(info, dataUrl);
      $zxMsg({t: info.warn?'warn':'ok',
        s:'已替换并适配：'+(im.name||zxBaseName(im.key))+'（'+info.cmW+'×'+info.cmH+'cm @'+info.ppi+'PPI）'});
    }catch(e){
      $zxMsg({t:'warn', s:'适配失败：'+(e.message||e)});
    }
  };
  // 删除 / 恢复 / 取消新增
  const del=document.createElement('button');
  del.className = deleting ? 'undo' : 'del';
  del.textContent = deleting ? '↺ 恢复' : (isAdded ? '✕ 取消' : '✕ 删除');
  del.addEventListener('click', (e)=>{
    e.stopPropagation();
    if(isAdded){
      const i=zxState.imgAdd.findIndex(a=>a.key===im.key);
      if(i>=0) zxState.imgAdd.splice(i,1);
      $zxMsg({t:'', s:'已取消新增：'+zxBaseName(im.key)});
    }else if(zxState.imgDelete.has(im.key)){
      zxState.imgDelete.delete(im.key);
      $zxMsg({t:'', s:'已恢复：'+(im.name||zxBaseName(im.key))});
    }else{
      zxState.imgDelete.add(im.key);
      $zxMsg({t:'warn', s:'已标记删除：'+(im.name||zxBaseName(im.key))+'（生成 ZIP 时移除）'});
    }
    zxRenderDetail();
  });
  card.appendChild(del);
  // 点击放大（排除按钮）
  card.addEventListener('click',(e)=>{
    if(e.target.tagName==='BUTTON') return;
    $('zxImgBig').src = im._preview || (im.full||im.thumb||'');
    $('zxImgCap').textContent=(im.name||zxBaseName(im.key))+'  ·  '+(im.size/1024).toFixed(1)+' KB';
    $('zxImgModal').classList.add('on');
  });
  // 拖拽替换
  card.addEventListener('dragover',(e)=>{ e.preventDefault(); card.classList.add('drag'); });
  card.addEventListener('dragleave',()=>card.classList.remove('drag'));
  card.addEventListener('drop',(e)=>{ e.preventDefault(); card.classList.remove('drag'); replace(e.dataTransfer.files[0]); });
  // 点击选择（兜底）
  const pick=document.createElement('button'); pick.className='ghost'; pick.textContent='选择图片';
  pick.style.cssText='position:absolute;left:0;right:0;bottom:0;height:24px;font-size:10px;'
    +'padding:0;border:0;border-top:1px solid var(--line);border-radius:0;background:rgba(255,255,255,.03);'
    +'color:var(--muted);letter-spacing:.2px';
  pick.addEventListener('click',(e)=>{
    e.stopPropagation();
    const inp=document.createElement('input'); inp.type='file'; inp.accept='image/*';
    inp.onchange=()=>replace(inp.files[0]); inp.click();
  });
  card.appendChild(pick);
  return card;
}

/* ---- 新增图片：归一化后按「目录 + 下一个序号」加入 ---- */
async function zxAddImages(dk, fileList){
  const dir=zxGroupDir(dk);
  if(!dir){ $zxMsg({t:'warn',s:'无法确定该分组的图片目录（该文档下无图片/文件）'}); return; }
  const arr=Array.from(fileList||[]).filter(f=>/^image\//.test(f.type));
  if(!arr.length){ $zxMsg({t:'warn',s:'请选择图片文件'}); return; }
  const profile = (dk==='pic') ? 'appearance' : 'other';
  $zxMsg({t:'', s:'正在新增并适配 '+arr.length+' 张图片…'});
  let ok=0;
  for(const f of arr){
    try{
      const info=await zxNormImage(f, profile);
      const name=zxNextName(dir);
      const url='data:image/jpeg;base64,'+info.dataB64;
      zxState.imgAdd.push({ key:dir+'/'+name, dir, name,
        size:Math.round(info.dataB64.length*0.75), dataB64:info.dataB64,
        thumb:url, full:url, info, _added:true });
      ok++;
    }catch(e){ $zxMsg({t:'warn', s:'新增失败：'+(e.message||e)}); }
  }
  zxRenderDetail();
  $zxMsg({t:ok?'ok':'warn', s: ok?('已新增 '+ok+' 张图片（生成 ZIP 时写入）'):'未新增任何图片'});
}

/* ---- 「＋ 添加图片」入口（支持点击多选与拖入） ---- */
function zxImgAddBtn(dk){
  const btn=document.createElement('button'); btn.className='zxImgAdd'; btn.type='button';
  btn.innerHTML='<span style="font-size:24px;line-height:1">＋</span><span>添加图片</span>'
    + '<span style="font-size:10px">点击多选 / 也可拖入</span>';
  btn.addEventListener('click',(e)=>{
    e.stopPropagation();
    const inp=document.createElement('input'); inp.type='file'; inp.accept='image/*'; inp.multiple=true;
    inp.onchange=()=>zxAddImages(dk, inp.files); inp.click();
  });
  btn.addEventListener('dragover',(e)=>{ e.preventDefault(); btn.style.borderColor='var(--neon)'; });
  btn.addEventListener('dragleave',()=>{ btn.style.borderColor=''; });
  btn.addEventListener('drop',(e)=>{ e.preventDefault(); btn.style.borderColor=''; zxAddImages(dk, e.dataTransfer.files); });
  return btn;
}

/* ---- 非图片附件行：选择文件替换 ---- */
function zxBinSlot(fi){
  const row=document.createElement('div'); row.className='zxFileRow';
  row.innerHTML='<span class="fk">附件</span><span>'+fi.key.replace(/</g,'&lt;')+'</span>'
    + '<span class="fk">'+(fi.size/1024).toFixed(1)+' KB</span>'
    + (zxState.fileReplace[fi.key]?'<span class="scanflag">已替换</span>':'');
  const btn=document.createElement('button'); btn.className='ghost'; btn.textContent='选择替换';
  btn.addEventListener('click',()=>{
    const inp=document.createElement('input'); inp.type='file';
    inp.onchange=async ()=>{
      const f=inp.files[0]; if(!f) return;
      const ab=await f.arrayBuffer(); let bin=''; const u8=new Uint8Array(ab);
      for(let i=0;i<u8.length;i+=8192) bin+=String.fromCharCode.apply(null,u8.subarray(i,i+8192));
      zxState.fileReplace[fi.key]={name:fi.key, dataB64:btoa(bin)};
      $zxMsg({t:'ok',s:'已标记替换：'+fi.key+'（生成 ZIP 时生效）'});
      row.innerHTML+='<span class="scanflag">已替换</span>';
    };
    inp.click();
  });
  row.appendChild(btn);
  return row;
}

/* ---- 主渲染：分组明细 ---- */
function zxRenderDetail(){
  const root=$('zxDetail'); root.innerHTML='';
  const kw=($('zxFilter').value||'').toLowerCase();
  const matchF=(f)=>{ const short=f.file.split('>').pop();
    return !kw || (short.toLowerCase().includes(kw)||f.path.toLowerCase().includes(kw)||String(f.value).toLowerCase().includes(kw)); };
  const groups={}; for(const k of ZX_DOC_ORDER) groups[k]={fields:[],images:[],bins:[]};
  for(const f of zxState.fields){
    const dk=zxDocKey(f.file);
    if(ZX_DOC_HIDDEN.includes(dk)) continue;      // 请求书 / 委托书不再单独分组
    (groups[dk]||(groups[dk]={fields:[],images:[],bins:[]})).fields.push(f);
  }
  for(const im of (zxState.images||[])){
    const dk=zxDocKey(im.key);
    if(ZX_DOC_HIDDEN.includes(dk)) continue;
    (groups[dk]||(groups[dk]={fields:[],images:[],bins:[]})).images.push(im);
  }
  for(const a of (zxState.imgAdd||[])){
    const dk=zxDocKey(a.key);
    if(ZX_DOC_HIDDEN.includes(dk)) continue;
    (groups[dk]||(groups[dk]={fields:[],images:[],bins:[]})).images.push(a);
  }
  for(const fi of zxState.files){
    if(fi.xml||fi.img) continue;
    const dk=zxDocKey(fi.key);
    if(ZX_DOC_HIDDEN.includes(dk)) continue;
    (groups[dk]||(groups[dk]={fields:[],images:[],bins:[]})).bins.push(fi);
  }

  // 可增减图片的分组（专利附图 / 外观图片）
  const ADDABLE = ['draw','pic'];

  let shownDocs=0;
  for(const dk of ZX_DOC_ORDER){
    const g=groups[dk]; if(!g) continue;
    const fs=g.fields.filter(matchF);
    const canAdd = ADDABLE.includes(dk) && !!zxGroupDir(dk);
    if(!fs.length && !g.images.length && !g.bins.length && !canAdd) continue;
    shownDocs++;
    const sec=document.createElement('section'); sec.className='zxDoc';
    const head=document.createElement('div'); head.className='zxDocHead';
    const liveImgs=g.images.filter(im=>!zxState.imgDelete.has(im.key)).length;
    head.innerHTML=''+ZX_DOC_LABEL[dk]
      + ' <span class="cnt">'+fs.length+' 字段 · '+liveImgs+' 图 · '+g.bins.length+' 附件</span>';
    sec.appendChild(head);
    if(fs.length){
      // 按「文档下的主区块」(路径第二级) 分组，换类别时换行
      const cats={};
      fs.forEach(f=>{
        const segs=(f.path||'').split('/');
        const cat = segs.length>1 ? segs[1] : (segs[0]||'其他');
        (cats[cat]||(cats[cat]=[])).push(f);
      });
      Object.keys(cats).forEach(cat=>{
        const cdiv=document.createElement('div'); cdiv.className='zxCat';
        const ch=document.createElement('div'); ch.className='zxCatHead'; ch.textContent=cat;
        cdiv.appendChild(ch);
        const box=document.createElement('div'); box.className='zxFields';
        cats[cat].forEach(f=>{
          const segs=(f.path||'').split('/');
          const short = segs.length>2 ? segs.slice(2).join(' / ') : false;
          box.appendChild(zxFieldItem(f, short));
        });
        cdiv.appendChild(box);
        sec.appendChild(cdiv);
      });
    }
    if(g.images.length || canAdd){
      const box=document.createElement('div'); box.className='zxImgs';
      g.images.forEach(im=>box.appendChild(zxImgSlot(im)));
      if(canAdd) box.appendChild(zxImgAddBtn(dk));
      sec.appendChild(box);
    }
    if(g.bins.length){
      const box=document.createElement('div'); box.className='zxBins';
      g.bins.forEach(fi=>box.appendChild(zxBinSlot(fi)));
      sec.appendChild(box);
    }
    root.appendChild(sec);
  }
  if(!shownDocs) root.innerHTML='<div class="zxNoImg">没有匹配的字段 / 文件。</div>';
  const liveTotal=(zxState.images||[]).filter(im=>!zxState.imgDelete.has(im.key)).length+(zxState.imgAdd||[]).length;
  const shownFields=Object.keys(groups).reduce((n,k)=>n+(ZX_DOC_HIDDEN.includes(k)?0:groups[k].fields.length),0);
  $('zxCount').textContent = '共 '+shownDocs+' 类文档 · '+shownFields+' 字段 · '+liveTotal+' 图';
  zxRenderPoa();
}

/* ---- 委托书扫描件 / 图片：并入「常用信息 · 代理与委托」 ---- */
function zxRenderPoa(){
  const box=$('zxPoaBox'); if(!box) return;
  const imgs=(zxState.images||[]).filter(im=>zxDocKey(im.key)==='poa')
    .concat((zxState.imgAdd||[]).filter(a=>zxDocKey(a.key)==='poa'));
  const bins=(zxState.files||[]).filter(fi=>!fi.xml&&!fi.img&&zxDocKey(fi.key)==='poa');
  const canAdd=!!zxGroupDir('poa');
  box.style.display = (imgs.length||bins.length||canAdd) ? '' : 'none';
  const ib=$('zxPoaImgs'); ib.innerHTML='';
  imgs.forEach(im=>ib.appendChild(zxImgSlot(im)));
  if(canAdd) ib.appendChild(zxImgAddBtn('poa'));
  const bb=$('zxPoaBins'); bb.innerHTML='';
  bins.forEach(fi=>bb.appendChild(zxBinSlot(fi)));
}

/* ---- 快捷表单 ---- */
function zxRenderQuick(){
  const base=$('zxBase'), app=$('zxApp');
  base.innerHTML=''; app.innerHTML='';
  for(const q of ZX_QUICK){
    const ids = zxMatchFields(q);
    const holder = q.group==='base'?base:app;
    const fld=document.createElement('div'); fld.className='field';
    const lab=document.createElement('label');
    lab.textContent = q.label + (ids.length?('（同步 '+ids.length+' 处）'):'（ZIP 中未找到）');
    if(!ids.length) lab.style.color='var(--muted)';
    if(ids.length){
      const f0 = zxState.fields.find(f=>f.id===ids[0]);
      if(f0.type==='div'){
        const inp = zxMakeDiv(ids[0], f0.value);
        inp.style.minWidth='220px';
        inp.addEventListener('change', ()=>{
          const code = inp._code;
          for(const id of ids){ zxState.edits[id]=code;
            const ti=document.querySelector('#zxDetail input[data-zxid="'+CSS.escape(id)+'"]');
            if(ti) ti.value=ZX_DIV[code]||code; }
        });
        fld.appendChild(lab); fld.appendChild(inp); holder.appendChild(fld);
        continue;
      }
      const inp=document.createElement('input'); inp.type='text';
      inp.style.minWidth='220px'; inp.value = f0.value;
      inp.dataset.zxids = JSON.stringify(ids);
      inp.addEventListener('input', ()=>{
        for(const id of ids){
          zxState.edits[id]=inp.value;
          const ti=document.querySelector('#zxDetail input[data-zxid="'+CSS.escape(id)+'"]');
          if(ti) ti.value=inp.value;
        }
      });
      fld.appendChild(lab); fld.appendChild(inp); holder.appendChild(fld);
    }else{
      const inp=document.createElement('input'); inp.type='text'; inp.disabled=true; inp.placeholder='该字段在此 ZIP 中不存在';
      fld.appendChild(lab); fld.appendChild(inp); holder.appendChild(fld);
    }
  }
  zxRenderInventors(); zxRenderAgents(); zxRenderDate(); zxRenderOptions();
}

/* ---- 发明人 / 设计人（动态行，支持增删；外观设计为设计人） ---- */
function zxIsDesign(){ return zxState.fields.some(f=>f.path.includes('/第一设计人/姓名')); }
function zxRenderInventors(){
  const wrap=$('zxInventors'); wrap.innerHTML='';
  const design = zxIsDesign();
  const firstTag = design?'第一设计人':'第一发明人';
  const otherTag = design?'其他设计人':'其他发明人';
  const word = design?'设计人':'发明人';
  const hit = zxState.fields.find(f=>f.path.includes('/'+firstTag+'/姓名'));
  if(!hit){ wrap.innerHTML='<div class="hint">此 ZIP 中没有找到'+word+'信息（请求书）。</div>'; return; }
  const file = hit.file;
  if($('zxInvTitle')) $('zxInvTitle').textContent = ''+word;
  const byFile = zxState.fields.filter(f=>f.file===file);
  const first = {
    name: (byFile.find(f=>f.path.endsWith('/'+firstTag+'/姓名'))||{value:''}).value,
    idcard: (byFile.find(f=>f.path.endsWith('/'+firstTag+'/身份证件号码'))||{value:''}).value,
  };
  const others=[];
  const re=new RegExp('/'+otherTag.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\[(\\d+)\\]\\/姓名$');
  for(const f of byFile){
    const m=f.path.match(re);
    if(m){ others.push({i:+m[1],
      name:f.value,
      idcard:(byFile.find(x=>x.path===f.path.replace(/\/姓名$/,'/身份证件号码'))||{value:''}).value}); }
  }
  const draft = zxState.sections.inventors && zxState.sections.inventors.file===file
    ? zxState.sections.inventors : {file, kind: design?'designers':'inventors',
        first, others:others.map(o=>({name:o.name,idcard:o.idcard}))};
  zxState.sections.inventors = draft;

  const mkRow=(idx, inv, removable)=>{
    const row=document.createElement('div'); row.className='zxInvRow';
    const lab=document.createElement('span'); lab.className='idx';
    lab.textContent = idx===0?'第一':('第'+(idx+1));
    row.appendChild(lab);
    const n=document.createElement('input'); n.type='text'; n.placeholder='姓名'; n.value=inv.name;
    n.addEventListener('input',()=>{inv.name=n.value;});
    const z=document.createElement('input'); z.type='text'; z.placeholder='身份证号'; z.value=inv.idcard;
    z.addEventListener('input',()=>{inv.idcard=z.value;});
    row.appendChild(n); row.appendChild(z);
    if(removable){
      const del=document.createElement('button'); del.className='ghost'; del.textContent='✕';
      del.addEventListener('click',()=>{
        draft.others.splice(idx-1,1); zxRenderInventors();
      });
      row.appendChild(del);
    }
    return row;
  };
  wrap.appendChild(mkRow(0, draft.first, false));
  draft.others.forEach((o,i)=>wrap.appendChild(mkRow(i+1, o, true)));
  const add=document.createElement('button'); add.textContent='＋ 添加'+word;
  add.style.marginTop='2px';
  add.addEventListener('click',()=>{ draft.others.push({name:'',idcard:''}); zxRenderInventors(); });
  wrap.appendChild(add);
}

/* ---- 代理师（请求书 + 委托书姓名同步） ---- */
function zxRenderAgents(){
  const wrap=$('zxAgents'); wrap.innerHTML='';
  const hit = zxState.fields.find(f=>f.path.includes('/专利代理机构/代理师'));
  if(!hit){ wrap.innerHTML='<div class="hint">此 ZIP 中没有找到代理师信息。</div>'; return; }
  const reqFile = hit.file;
  const agents=[];
  const seen=new Set();
  for(const f of zxState.fields){
    if(f.file!==reqFile) continue;
    const m=f.path.match(/\/代理师(?:\[(\d+)\])?\/姓名$/);
    if(!m) continue;
    const key=m[1]||'1';
    if(seen.has(key)) continue; seen.add(key);
    const base=f.path.replace(/\/姓名$/,'');
    agents.push({
      name:f.value,
      zgzh:(zxState.fields.find(x=>x.file===reqFile&&x.path===base+'/资格证号')||{value:''}).value,
      phone:(zxState.fields.find(x=>x.file===reqFile&&x.path===base+'/电话')||{value:''}).value,
    });
  }
  const draft = zxState.sections.agents && zxState.sections.agents.file===reqFile
    ? zxState.sections.agents : {file:reqFile, list:agents};
  zxState.sections.agents = draft;

  const mkRow=(i,a,removable)=>{
    const row=document.createElement('div'); row.className='zxInvRow';
    const lab=document.createElement('span'); lab.className='idx'; lab.textContent='代理师'+(i+1);
    row.appendChild(lab);
    const n=document.createElement('input'); n.type='text'; n.placeholder='姓名'; n.value=a.name;
    n.addEventListener('input',()=>{a.name=n.value;});
    const g=document.createElement('input'); g.type='text'; g.placeholder='资格证号'; g.value=a.zgzh;
    g.addEventListener('input',()=>{a.zgzh=g.value;});
    const p=document.createElement('input'); p.type='text'; p.placeholder='电话'; p.value=a.phone;
    p.addEventListener('input',()=>{a.phone=p.value;});
    row.appendChild(n); row.appendChild(g); row.appendChild(p);
    if(removable){
      const del=document.createElement('button'); del.className='ghost'; del.textContent='✕';
      del.addEventListener('click',()=>{ draft.list.splice(i,1); zxRenderAgents(); });
      row.appendChild(del);
    }
    return row;
  };
  draft.list.forEach((a,i)=>wrap.appendChild(mkRow(i,a,draft.list.length>1)));
  const add=document.createElement('button'); add.textContent='＋ 添加代理师';
  add.style.marginTop='2px';
  add.addEventListener('click',()=>{ draft.list.push({name:'',zgzh:'',phone:''}); zxRenderAgents(); });
  wrap.appendChild(add);
}

/* ---- 委托日期（委托书 年/月/日） ---- */
function zxRenderDate(){
  const wrap=$('zxDate'); wrap.innerHTML='';
  const df=['年','月','日'].map(u=>{
    const f=zxState.fields.find(f=>f.path.endsWith('/委托日期/'+u));
    return f?{u,f}:null;
  }).filter(Boolean);
  if(!df.length) return;
  for(const {u,f} of df){
    const fld=document.createElement('div'); fld.className='field';
    const lab=document.createElement('label'); lab.textContent='委托日期·'+u+'（委托书）';
    const inp=document.createElement('input'); inp.type='text'; inp.style.width='90px'; inp.value=f.value;
    inp.addEventListener('input',()=>{ zxState.edits[f.id]=inp.value;
      const ti=document.querySelector('#zxDetail input[data-zxid="'+CSS.escape(f.id)+'"]');
      if(ti) ti.value=inp.value; });
    fld.appendChild(lab); fld.appendChild(inp); wrap.appendChild(fld);
  }
}

/* ---- 字段明细表 ---- */
/* ---- 选项与声明（复选框）快捷组 ---- */
function zxRenderOptions(){
  const grp=$('zxOptGroup'), wrap=$('zxOptions'); if(!grp||!wrap) return;
  wrap.innerHTML='';
  const req = zxState.fields.find(f=>f.path.includes('/第一申请人'))
          || zxState.fields.find(f=>f.path.includes('/第一发明人')||f.path.includes('/第一设计人'));
  const reqFile = req ? req.file : null;
  const checks = zxState.fields.filter(f=>f.type==='checkbox' && (reqFile? f.file===reqFile : true));
  if(!checks.length){ grp.style.display='none'; return; }
  grp.style.display='';
  for(const f of checks){
    const label = (f.path.split('/').slice(-2,-1)[0]) || f.path;
    const row=document.createElement('div'); row.className='zxInvRow';
    const box=document.createElement('input'); box.type='checkbox'; box.checked=(f.value==='1');
    box.style.marginRight='8px';
    box.addEventListener('change', ()=>{
      const v=box.checked?'1':'0';
      if(v===f.value) delete zxState.edits[f.id];
      else zxState.edits[f.id]=v;
      const ti=document.querySelector('#zxDetail input[data-zxid="'+CSS.escape(f.id)+'"]');
      if(ti) ti.checked=box.checked;
    });
    const lab=document.createElement('span'); lab.textContent=label; lab.style.fontSize='13px';
    row.appendChild(box); row.appendChild(lab); wrap.appendChild(row);
  }
}

$('zxFilter').addEventListener('input', zxRenderDetail);

/* ---- 保存 ---- */
$('zxSave').addEventListener('click', async ()=>{
  if(!zxState.sid){ $zxSaveMsg({t:'warn',s:'请先解析 ZIP。'}); return; }
  const edits=Object.entries(zxState.edits).map(([id,value])=>({id,value}));
  const sections=[];
  if(zxState.sections.inventors) sections.push({file:zxState.sections.inventors.file, kind:zxState.sections.inventors.kind,
    first:{name:zxState.sections.inventors.first.name, idcard:zxState.sections.inventors.first.idcard},
    others:zxState.sections.inventors.others});
  if(zxState.sections.agents) sections.push({file:zxState.sections.agents.file, kind:'agents', list:zxState.sections.agents.list});
  const payload={
    sid:zxState.sid, edits, sections,
    fileReplace:Object.values(zxState.fileReplace),
    deletes:Array.from(zxState.imgDelete),
    adds:(zxState.imgAdd||[]).map(a=>({key:a.key, dataB64:a.dataB64})),
    fname:zxState.fname||'modified.zip',
  };
  $zxSaveMsg({t:'',s:''});
  try{
    const resp=await fetch(API+'/api/zipxml_save', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload),
    });
    if(!resp.ok){ let msg='HTTP '+resp.status; try{msg=(await resp.json()).error||msg;}catch(e){} throw new Error(msg); }
    const blob=await resp.blob();
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob); a.download='修改后_'+(zxState.fname||'modified.zip');
    document.body.appendChild(a); a.click();
    setTimeout(()=>{a.remove(); URL.revokeObjectURL(a.href);},800);
    $zxSaveMsg({t:'ok', s:'已生成下载：修改 '+edits.length+' 处文本、'+sections.length+' 组结构、'
      +Object.keys(zxState.fileReplace).length+' 个替换、'
      +zxState.imgDelete.size+' 个删除、'+(zxState.imgAdd||[]).length+' 个新增。'});
  }catch(err){
    $zxSaveMsg({t:'err', s:'生成失败：'+err.message});
  }
});

/* ---- 重置 ---- */
$('zxReset').addEventListener('click', ()=>{
  zxState.edits={}; zxState.fileReplace={}; zxState.sections={}; zxState.imgDelete=new Set(); zxState.imgAdd=[];
  zxRenderQuick(); zxRenderDetail();
  $zxSaveMsg({t:'ok', s:'已重置全部修改。'});
});

$('zxParse').addEventListener('click', ()=>{
  const f=$('zxFile').files[0];
  if(!f){ $zxMsg({t:'warn',s:'请先选择 ZIP 文件。'}); return; }
  zxParse(f);
});
$('zxFile').addEventListener('change', ()=>{
  const f=$('zxFile').files[0];
  if(f) zxParse(f);
});
$('zxImgClose').addEventListener('click', ()=>$('zxImgModal').classList.remove('on'));
$('zxImgModal').addEventListener('click', (e)=>{ if(e.target.id==='zxImgModal') $('zxImgModal').classList.remove('on'); });
document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') $('zxImgModal').classList.remove('on'); });

updateStatus();

/* ---------- tab4：特征关系分析（EUREKA → 3D 气泡蛛网图 · 可交互） ---------- */
const relGraph = { hasData:false, nodes:[], edges:[], yaw:0.6, pitch:0.35, zoom:1,
                   drag:false, dragNode:-1, lx:0, ly:0, hover:-1, pinned:-1,
                   spin:false, moved:false, raf:0, t:0 };

/* 关系类别配色：与后端 edge.kind 对应，连线和图例共用（高饱和，深色底上更醒目） */
const REL_COLORS = { contain:'#25d98a', connect:'#4f9bff', fix:'#ffb224', position:'#b06bff',
                     drive:'#ff4d8d', hyponym:'#22d3ee', depend:'#94a3b8', sibling:'#7c8ba1',
                     related:'#64748b' };
const REL_NAMES = { contain:'包含', connect:'连接', fix:'固定', position:'位置', drive:'驱动',
                    hyponym:'上下位', depend:'从属', sibling:'同类', related:'相关' };
function relColor(k){ return REL_COLORS[k] || REL_COLORS.related; }
function relAlpha(hex, a){
  const n = parseInt(hex.slice(1), 16);
  return 'rgba(' + ((n>>16)&255) + ',' + ((n>>8)&255) + ',' + (n&255) + ',' + a + ')';
}
function relMix(hex, d, a){
  const n = parseInt(hex.slice(1), 16);
  const r = Math.min(255,Math.max(0,((n>>16)&255)+d));
  const g = Math.min(255,Math.max(0,((n>>8)&255)+d));
  const b = Math.min(255,Math.max(0,(n&255)+d));
  return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
}

$('relSample').addEventListener('click', ()=>{
  $('relText').value = '一种切割装置，包括机架1、导轨组件2和驱动电机4，导轨组件2包括吸油口21、切刀22和侧壁24。所述机架1上设置有真空泵5，所述切刀22通过螺栓连接固定在导轨组件2上，侧壁24与切刀22滑动连接。驱动电机4的输出轴与切刀22传动连接，真空泵5通过软管51连通吸油口21。所述机架1固定于底座101上。';
});

/* 文本框内 Ctrl+Enter 直接提交分析 */
$('relText').addEventListener('keydown', e=>{
  if((e.ctrlKey||e.metaKey) && e.key==='Enter'){ e.preventDefault(); $('relAnalyze').click(); }
});

$('relAnalyze').addEventListener('click', async ()=>{
  const text = $('relText').value.trim();
  const msg = $('relMsg');
  if(!text){ msg.textContent='请先粘贴文本'; msg.className='msg err'; return; }
  msg.textContent='分析中…'; msg.className='msg';
  try{
    const r = await fetch(API+'/api/relations',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text})});
    const d = await r.json();
    if(d.error){ msg.textContent=d.error; msg.className='msg err'; return; }
    relGraph.nodes = d.nodes||[]; relGraph.edges = d.edges||[]; relGraph.hasData = true;
    relGraph.pinned = -1; relGraph.hover = -1; relGraph.dragNode = -1;
    relLayout();
    $('relGraphCard').style.display='';
    const mode = (d.stats.mode||'') ? '（'+d.stats.mode+'模式）' : '';
    if(relGraph.nodes.length < 2){
      msg.textContent = '只识别到 '+relGraph.nodes.length+' 个特征，无法成网：请确认文本含「名称+附图标记」，或含装置/机构/组件/壳体/支架等技术名词';
      msg.className='msg err';
    }else{
      msg.textContent = '识别特征 '+d.stats.features+' 个、关系 '+d.stats.relations+' 条'+mode+
        '，共 '+d.stats.sentences+' 句';
      msg.className='msg ok';
    }
    relDetail(null);
    relDraw();
    $('relGraphCard').scrollIntoView({behavior:'smooth'});
  }catch(e){ msg.textContent='请求失败：'+e.message; msg.className='msg err'; }
});

/* 球面布局：度数大的放中间轴附近，度数小的铺在外层 */
function relLayout(){
  const ns = relGraph.nodes, n = ns.length;
  if(!n) return;
  const ga = Math.PI*(3-Math.sqrt(5));
  for(let i=0;i<n;i++){
    const y = 1 - (i+0.5)*2/n;
    const r = Math.sqrt(Math.max(0,1-y*y));
    const th = ga*i;
    ns[i]._x = Math.cos(th)*r; ns[i]._y = y; ns[i]._z = Math.sin(th)*r;
    ns[i]._r = 9 + Math.min(24, ns[i].degree*2.6);
  }
  if(n>1){ const t=ns[0]; ns[0]=ns[1]; ns[1]=t; }
}

function relProject(p, w, h){
  const g=relGraph, cy=Math.cos(g.yaw), sy=Math.sin(g.yaw);
  const cp=Math.cos(g.pitch), sp=Math.sin(g.pitch);
  let x = p[0]*cy + p[2]*sy;
  let z = -p[0]*sy + p[2]*cy;
  let y = p[1]*cp - z*sp;
  z = p[1]*sp + z*cp;
  const d = 3.2, s = Math.min(w,h)*0.34*g.zoom;
  const f = d/(d - z);
  return {x: w/2 + x*s*f, y: h/2 - y*s*f, z: z, f: f, rz: z};
}

/* 反投影：把屏幕坐标换回 3D（保持当前深度），用于拖动单个气泡 */
function relUnproject(sx, sy, w, h, zr){
  const g=relGraph, cy=Math.cos(g.yaw), sy2=Math.sin(g.yaw);
  const cp=Math.cos(g.pitch), sp=Math.sin(g.pitch);
  const s = Math.min(w,h)*0.34*g.zoom;
  const d = 3.2, f = d/(d - zr), k = s*f;
  const X = (sx - w/2)/k;
  const Y = (h/2 - sy)/k;
  const y = (Y + zr*sp)/(Math.abs(cp)<1e-3?1e-3:cp);
  const x = X*cy - zr*sy2;
  const z = X*sy2 + zr*cy;
  const rr = Math.sqrt(x*x+y*y+z*z) || 1;
  const lim = 1.15;
  const k2 = rr > lim ? lim/rr : 1;
  return [x*k2, y*k2, z*k2];
}

function relTints(idx, es, ns){
  const cnt = ns.map(()=>({}));
  es.forEach(e=>{
    const a=idx[e.a], b=idx[e.b];
    if(a!=null) cnt[a][e.kind]=(cnt[a][e.kind]||0)+1;
    if(b!=null) cnt[b][e.kind]=(cnt[b][e.kind]||0)+1;
  });
  return cnt.map(c=>{
    let best='related', bs=-1;
    Object.keys(c).forEach(k=>{
      const wt = (k==='related'||k==='sibling') ? 0.6 : 1;
      if(c[k]*wt > bs){ bs=c[k]*wt; best=k; }
    });
    return relColor(best);
  });
}

function relDraw(){
  const cv=$('relCanvas'); if(!cv) return;
  const ctx=cv.getContext('2d'), w=cv.width, h=cv.height;
  const g=relGraph, ns=g.nodes, es=g.edges;
  const idx={}; ns.forEach((n,i)=>idx[n.id]=i);
  ctx.clearRect(0,0,w,h);
  // 深色径向底，让高饱和气泡更亮
  const bg=ctx.createRadialGradient(w/2,h*0.42,40,w/2,h/2,Math.max(w,h)*0.72);
  bg.addColorStop(0,'#141d26'); bg.addColorStop(1,'#0b1016');
  ctx.fillStyle=bg; ctx.fillRect(0,0,w,h);
  if(!ns.length) return;

  const proj = ns.map(n=>relProject([n._x,n._y,n._z],w,h));
  let focus=-1;
  if(g.pinned>=0) focus=g.pinned; else if(g.hover>=0) focus=g.hover;
  const near=new Set();
  if(focus>=0){
    near.add(focus);
    es.forEach(e=>{
      const a=idx[e.a], b=idx[e.b];
      if(a===focus) near.add(b);
      if(b===focus) near.add(a);
    });
  }
  // 连线
  ctx.lineCap='round';
  es.forEach(e=>{
    const a=idx[e.a], b=idx[e.b];
    if(a==null||b==null) return;
    const pa=proj[a], pb=proj[b];
    const on = focus>=0 && (a===focus || b===focus);
    const dim = focus>=0 && !on;
    const c = relColor(e.kind);
    ctx.strokeStyle = dim ? 'rgba(110,125,150,0.10)' : (on ? c : relAlpha(c, 0.55));
    ctx.lineWidth = dim ? 1 : (on ? 2.6 : 1.5);
    ctx.beginPath(); ctx.moveTo(pa.x,pa.y); ctx.lineTo(pb.x,pb.y); ctx.stroke();
    if(!dim && (on || es.length<=40)){
      const mx=(pa.x+pb.x)/2, my=(pa.y+pb.y)/2;
      if((pa.z+pb.z)/2 < 0.6){
        ctx.font='11px sans-serif'; ctx.textAlign='center';
        ctx.lineWidth=3; ctx.strokeStyle='rgba(6,10,15,0.85)';
        ctx.strokeText(e.rel, mx, my-3);
        ctx.fillStyle = on ? '#e8f2ff' : relAlpha(c, 0.9);
        ctx.fillText(e.rel, mx, my-3);
      }
    }
  });
  const tints = relTints(idx, es, ns);
  // 标签防重叠：按度数从高到低占位，压到已占位的标签就不再画（选中的必画）
  const labelRect = {}, labelOk = new Set(), placed = [];
  const byDeg = ns.map((n,i)=>i).sort((a,b)=>ns[b].degree-ns[a].degree);
  byDeg.forEach(i=>{
    const n=ns[i], p=proj[i], r=Math.max(5, n._r*p.f*g.zoom*0.85);
    const fs = Math.max(11, Math.min(15, 11*Math.min(p.f,1.3)));
    const tw = (n.label.length*fs*0.95);
    const ty = p.y - r - 9;
    const rc = {x:p.x-tw/2-6, y:ty-fs-2, w:tw+12, h:fs+8};
    labelRect[i]=rc;
    const hitAlready = placed.some(q=>!(rc.x+rc.w<q.x || rc.x>q.x+q.w || rc.y+rc.h<q.y || rc.y>q.y+q.h));
    if(!hitAlready){ placed.push(rc); labelOk.add(i); }
  });
  // 气泡（远的先画）
  const order = ns.map((n,i)=>i).sort((a,b)=>proj[a].z-proj[b].z);
  order.forEach(i=>{
    const n=ns[i], p=proj[i];
    const r = Math.max(5, n._r*p.f*g.zoom*0.85);
    const dim = focus>=0 && !near.has(i);
    const front = p.z<0;
    const alpha = dim?0.18:(front?1:0.78);
    const base = tints[i];
    const sel = (i===g.pinned), hov = (i===g.hover);
    ctx.save();
    if(sel || hov){
      ctx.shadowColor = base; ctx.shadowBlur = sel? 26 : 16;
    }
    const grad=ctx.createRadialGradient(p.x-r*0.35,p.y-r*0.38,r*0.12,p.x,p.y,r);
    grad.addColorStop(0, relMix(base, 105, (0.95*alpha).toFixed(3)));
    grad.addColorStop(0.45, relMix(base, 32, alpha));
    grad.addColorStop(1, relMix(base, -70, alpha));
    ctx.fillStyle=grad;
    ctx.beginPath(); ctx.arc(p.x,p.y,r,0,6.2832); ctx.fill();
    ctx.restore();
    // 外圈：选中用亮白，相邻用同色描边
    if(sel || (focus>=0 && near.has(i) && i!==focus)){
      ctx.strokeStyle = sel ? '#ffffff' : relMix(base, 90, 0.95);
      ctx.lineWidth = sel ? 2.4 : 1.6;
      ctx.beginPath(); ctx.arc(p.x,p.y,Math.max(2,r)+3.5,0,6.2832); ctx.stroke();
    }
    // 标签（选中的一定画，其它按防重叠结果）
    if(!dim && (labelOk.has(i) || sel || hov)){
      const rc = labelRect[i], fs = Math.max(11, Math.min(15, 11*Math.min(p.f,1.3)));
      ctx.font='600 '+fs+'px sans-serif';
      ctx.textAlign='center';
      ctx.fillStyle='rgba(8,12,18,'+(sel?0.9:0.62)+')';
      ctx.beginPath();
      if(ctx.roundRect){ ctx.roundRect(rc.x,rc.y,rc.w,rc.h,5); } else { ctx.rect(rc.x,rc.y,rc.w,rc.h); }
      ctx.fill();
      ctx.fillStyle = sel ? '#ffffff' : (hov ? '#eaf4ff' : 'rgba(226,236,246,'+(0.7+0.3*Math.min(1,-p.z))+')');
      ctx.fillText(n.label, p.x, rc.y+rc.h-6);
    }
  });
  // 图例
  const kd = {}; es.forEach(e=>{ kd[e.kind] = (kd[e.kind]||0) + 1; });
  const rows = Object.keys(REL_NAMES).filter(k=>kd[k])
    .map(k=>'<span style="color:'+relColor(k)+'">●</span> '+REL_NAMES[k]+' '+kd[k]).join('<br>');
  $('relLegend').innerHTML =
    '特征 <b style="color:#eaf4ff">'+ns.length+'</b> 个 · 关系 <b style="color:#eaf4ff">'+es.length+'</b> 条<br>'+rows+
    '<br><span style="color:#6b7688">拖节点移动 · 拖空白旋转<br>滚轮缩放 · 单击查看详情</span>';
}

/* 右下角详情面板：选中节点的全部关系 */
function relDetail(i){
  const box = $('relDetail'); if(!box) return;
  const g = relGraph;
  if(i==null || i<0 || i>=g.nodes.length){
    box.style.display='none'; box.innerHTML=''; return;
  }
  const n = g.nodes[i];
  const rows = [];
  g.edges.forEach(e=>{
    if(e.a===n.id) rows.push([e.rel, e.b, e.kind, '→']);
    else if(e.b===n.id) rows.push([e.rel, e.a, e.kind, '←']);
  });
  const html = ['<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">',
    '<b style="color:#fff;font-size:13px">'+n.label+'</b>',
    '<span style="color:#8fa3b8;font-size:11px">'+rows.length+' 条关系</span>',
    '<span id="relDetailClose" style="margin-left:auto;cursor:pointer;color:#8fa3b8">✕</span></div>'];
  rows.forEach(r=>{
    html.push('<div style="display:flex;gap:6px;align-items:baseline;font-size:12px;line-height:1.7">'+
      '<span style="color:'+relColor(r[2])+'">'+r[3]+'</span>'+
      '<span style="color:#c8d6e4">'+r[1]+'</span>'+
      '<span style="color:#7d8fa3;font-size:11px;margin-left:auto">'+r[0]+'</span></div>');
  });
  box.innerHTML = html.join('');
  box.style.display='';
  const c = $('relDetailClose');
  if(c) c.onclick = ()=>{ relGraph.pinned=-1; relDetail(null); relDraw(); };
}

(function(){
  const cv=$('relCanvas'); if(!cv) return;
  const pos=e=>{
    const r=cv.getBoundingClientRect();
    const p = e.touches? e.touches[0] : e;
    return {x:(p.clientX-r.left)*cv.width/r.width, y:(p.clientY-r.top)*cv.height/r.height};
  };
  const projAll=()=>relGraph.nodes.map(n=>relProject([n._x,n._y,n._z],cv.width,cv.height));
  const pick=p=>{
    const ns=relGraph.nodes, proj=projAll();
    let best=-1,bd=1e9;
    proj.forEach((q,i)=>{
      const r=Math.max(9, ns[i]._r*q.f*relGraph.zoom*0.85)+8, d=(q.x-p.x)**2+(q.y-p.y)**2;
      if(d<r*r&&d<bd){bd=d;best=i;}
    });
    return best;
  };
  const down=e=>{
    const q=pos(e);
    const hit=pick(q);
    relGraph.moved=false; relGraph.lx=q.x; relGraph.ly=q.y;
    if(hit>=0){
      relGraph.dragNode=hit; relGraph.drag=true;
      cv.style.cursor='grabbing';
    }else{
      relGraph.dragNode=-1; relGraph.drag=true;
      cv.style.cursor='grabbing';
    }
    e.preventDefault();
  };
  const move=e=>{
    const q=pos(e);
    if(relGraph.drag){
      const dx=q.x-relGraph.lx, dy=q.y-relGraph.ly;
      if(Math.abs(dx)+Math.abs(dy)>2) relGraph.moved=true;
      if(relGraph.dragNode>=0){
        const n=relGraph.nodes[relGraph.dragNode];
        const zr=relProject([n._x,n._y,n._z],cv.width,cv.height).rz;
        const p3=relUnproject(q.x, q.y, cv.width, cv.height, zr);
        n._x=p3[0]; n._y=p3[1]; n._z=p3[2];
        $('relHover').textContent = '拖动「'+n.label+'」调整位置';
      }else{
        relGraph.yaw += dx*0.008;
        relGraph.pitch = Math.max(-1.4, Math.min(1.4, relGraph.pitch + dy*0.008));
      }
      relGraph.lx=q.x; relGraph.ly=q.y;
      if(relGraph.hasData) relDraw();
      e.preventDefault();
    }else if(relGraph.hasData){
      const h=pick(q);
      if(h!==relGraph.hover){
        relGraph.hover=h; relDraw();
        cv.style.cursor = h>=0 ? 'pointer' : 'grab';
      }
      $('relHover').textContent = h>=0
        ? relGraph.nodes[h].label+'（'+relGraph.nodes[h].degree+' 个连接）· 单击查看详情，拖动可移动'
        : '拖动空白旋转视角 · 滚轮缩放';
    }
  };
  const up=e=>{
    if(relGraph.drag && !relGraph.moved){
      const q=pos(e); const h=pick(q);
      relGraph.pinned = (h===relGraph.pinned)? -1 : h;
      relDetail(relGraph.pinned);
      if(relGraph.hasData) relDraw();
    }
    relGraph.drag=false; relGraph.dragNode=-1; cv.style.cursor='grab';
  };
  cv.addEventListener('mousedown',down); cv.addEventListener('mousemove',move);
  window.addEventListener('mouseup',up);
  cv.addEventListener('wheel',e=>{
    if(!relGraph.hasData) return;
    relGraph.zoom = Math.max(0.4, Math.min(3, relGraph.zoom * (e.deltaY>0?0.92:1.09)));
    relDraw(); e.preventDefault();
  },{passive:false});
  cv.addEventListener('touchstart',down,{passive:false});
  cv.addEventListener('touchmove',move,{passive:false});
  cv.addEventListener('touchend',up);
  cv.addEventListener('dblclick', e=>{
    if(!relGraph.hasData) return;
    const h=pick(pos(e));
    if(h>=0){
      const n=relGraph.nodes[h];
      relGraph.yaw = -Math.atan2(n._z, n._x);
      relGraph.pitch = Math.asin(Math.max(-1,Math.min(1,-n._y)))*0.8;
      relGraph.pinned=h; relDetail(h); relDraw();
    }
  });

  // 自动旋转
  const spin=()=>{
    if(!relGraph.spin) return;
    relGraph.yaw += 0.0035;
    if(relGraph.hasData) relDraw();
    relGraph.raf = requestAnimationFrame(spin);
  };
  $('relSpin').addEventListener('click', ()=>{
    relGraph.spin = !relGraph.spin;
    $('relSpin').textContent = '自动旋转：' + (relGraph.spin?'开':'关');
    if(relGraph.spin){ cancelAnimationFrame(relGraph.raf); spin(); }
  });
  $('relReset').addEventListener('click', ()=>{
    relGraph.yaw=0.6; relGraph.pitch=0.35; relGraph.zoom=1;
    relGraph.pinned=-1; relDetail(null); relLayout(); relDraw();
  });
})();

/* ---------- 主程序深链：/?tab=1|2|3|4 或 /#tab1|tab2|tab3|tab4 ----------
   1 调整外观图（一键改图） / 2 附图标注（编辑图片） / 3 XML 修改 / 4 特征关系分析 */
(function(){
  var m = location.search.match(/[?&]tab=([1-4])(?:&|$)/)
       || location.hash.match(/^#tab([1-4])\b/);
  if(m) showTab(parseInt(m[1],10));
})();
</script>
</body>
</html>
'''

# ---------------- 六视图处理与 HTTP 服务（原 server.py） ----------------
SESSIONS = {}          # sid -> {'full': {view: Image}, 'ppi': {view: int}, 'ext': {view: str}, 'detect_cache': {}}
LOCK = threading.Lock()


def b64_to_image(b64):
    raw = base64.b64decode(b64)
    return Image.open(io.BytesIO(raw))


def image_to_b64(img, fmt='PNG'):
    buf = io.BytesIO()
    img.save(buf, fmt)
    return base64.b64encode(buf.getvalue()).decode('ascii')


def save_bytes(img, ext, ppi):
    """按原格式保存并设置 dpi=ppi。返回字节。"""
    buf = io.BytesIO()
    if ext == 'jpg':
        im = img.convert('RGB') if img.mode != 'RGB' else img
        im.save(buf, 'JPEG', dpi=(ppi, ppi), quality=95)
        return buf.getvalue()
    if ext == 'bmp':
        im = img.convert('RGB') if img.mode != 'RGB' else img
        im.save(buf, 'BMP', dpi=(ppi, ppi))
        return buf.getvalue()
    # png：保留原色彩模式（含透明）
    img.save(buf, 'PNG', dpi=(ppi, ppi))
    return buf.getvalue()


def detect_product_bbox(src_img, tol=30):
    """在纯色背景中识别产品外轮廓，返回 (x0,y0,x1,y1)（闭区间，基于原图坐标）。
    背景色由图像最外圈像素的众数决定；与背景色最大通道差 > tol 的像素视为前景。
    为提高速度，先在最长边 <= 400 的缩略图上检测，再映射回原图坐标。
    若几乎整图都是背景则返回 None。"""
    rgb = src_img.convert('RGB')
    w, h = rgb.size
    scale = 1.0
    long = max(w, h)
    if long > 400:
        scale = 400.0 / long
        small = rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)
    else:
        small = rgb
    sw, sh = small.size
    px = small.load()

    # 背景色：外圈像素量化后的众数（容差压缩噪点）
    border = []
    for x in range(sw):
        border.append(px[x, 0])
        border.append(px[x, sh - 1])
    for y in range(sh):
        border.append(px[0, y])
        border.append(px[sw - 1, y])
    cnt = Counter(((c[0] // 16), (c[1] // 16), (c[2] // 16)) for c in border)
    bgq = cnt.most_common(1)[0][0]
    bg = (bgq[0] * 16 + 8, bgq[1] * 16 + 8, bgq[2] * 16 + 8)

    minx, miny, maxx, maxy = sw, sh, -1, -1
    for y in range(sh):
        for x in range(sw):
            r, g, b = px[x, y]
            if abs(r - bg[0]) > tol or abs(g - bg[1]) > tol or abs(b - bg[2]) > tol:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    if maxx < 0:
        return None

    def back(v, full):
        return max(0, min(full - 1, int(round(v / scale)))) if scale != 1 else v

    x0 = back(minx, w)
    x1 = back(maxx + 1, w)
    y0 = back(miny, h)
    y1 = back(maxy + 1, h)
    return (x0, y0, x1, y1)


def build_working(session, crop, tol):
    """根据 crop/tol 得到每个视图的工作图像与其产品尺寸，并对轮廓检测结果做缓存。
    返回 (working, bbox)：working[v]=(img, (pw,ph))；bbox[v]=(x0,y0,x1,y1) 或 None。"""
    cache = session.setdefault('detect_cache', {})
    key = (bool(crop), int(tol))
    if key not in cache:
        bbox = {}
        for v in ALL_VIEWS:
            if v in session['full']:
                bbox[v] = detect_product_bbox(session['full'][v], tol) if crop else None
        cache[key] = bbox
    bbox = cache[key]

    working = {}
    for v in ALL_VIEWS:
        if v not in session['full']:
            continue
        full = session['full'][v]
        b = bbox.get(v)
        if crop and b:
            img = full.crop(b)
            pw, ph = img.size
        else:
            img = full
            pw, ph = full.size
        working[v] = (img, (pw, ph))
    return working, bbox


def stereo_target(pw, ph, ppi, sw_cm=None, sh_cm=None):
    """立体图目标尺寸：
    - 未指定任何目标：宽度 = 10cm，等比换算高度；高度超过 15cm 则钳制（等比缩宽），不变形
    - 只指定宽或高：等比换算另一项
    - 宽高都指定：精确调整为该尺寸
    """
    W10 = max(1, round(STEREO_W_CM / 2.54 * ppi))
    Hmax = max(1, round(STEREO_H_MAX_CM / 2.54 * ppi))
    if sw_cm and sh_cm:
        return max(1, sw_cm), max(1, sh_cm), False
    if sw_cm:
        W = max(1, sw_cm)
        H = max(1, round(W * (ph / pw))) if pw else Hmax
    elif sh_cm:
        H = max(1, sh_cm)
        W = max(1, round(H * (pw / ph))) if ph else W10
    else:
        W = W10
        H = max(1, round(W * (ph / pw))) if pw else Hmax
        clamped = False
        if H > Hmax:
            H = Hmax
            W = max(1, round(H * (pw / ph))) if ph else W
            clamped = True
        return W, H, clamped
    return W, H, False


def compute_targets(orig, main_w=None, main_h=None):
    """以主视图【产品】为基准。主视图按指定的目标宽/高调整（若不指定则保持原始尺寸）；
    其余视图等比缩放以对齐主视图，不变形。
    约束（与需求一致）：
      · 主视图目标尺寸 = (main_w, main_h)；二者均未指定时保持原始尺寸 (ow, oh)
      · 后视图 = 主视图（高度 = Hm，等比缩放；宽度应 = Wm）
      · 左 / 右视图 高度 = Hm，等比 → 宽度 = D
      · 俯 / 仰视图 高度 = D（= 左宽，盒子闭合），等比 → 宽度应 = Wm
      · 左 / 右视图宽度 = 俯 / 仰视图高度 = D（盒子闭合）
    返回 sizes（每视图输出像素）、notes（一致性提示）、(Wm, Hm)、D。"""
    ow, oh = orig['main'][0], orig['main'][1]
    Wm, Hm = main_w, main_h
    if Wm is None and Hm is None:
        Wm, Hm = ow, oh
    elif Wm is None:
        Wm = max(1, round(Hm * (ow / oh))) if oh else ow
    elif Hm is None:
        Hm = max(1, round(Wm * (oh / ow))) if ow else oh
    Wm = max(1, int(Wm))
    Hm = max(1, int(Hm))
    sizes = {}
    notes = []
    TOL = 2  # 像素容差，用于判断各视图是否严丝合缝

    # 主视图：按指定的目标尺寸调整（默认原始尺寸）
    sizes['main'] = (Wm, Hm)

    # 后视图：与主视图完全一致（同宽同高），需求要求「后=主」
    if 'back' in orig:
        sizes['back'] = (Wm, Hm)

    # 深度 D：优先由左视图（高度对齐到 Hm）等比推出（左/右不变形）
    D = None
    if 'left' in orig:
        lw, lh = orig['left'][0], orig['left'][1]
        s = (Hm / lh) if lh else 1.0
        D = max(1, round(lw * s))
        sizes['left'] = (D, Hm)
        sizes['right'] = (D, Hm)
    elif 'top' in orig:
        tw, th = orig['top'][0], orig['top'][1]
        s = (Wm / tw) if tw else 1.0
        D = max(1, round(th * s))

    # 俯 / 仰视图：宽度 = 主视图宽 Wm，高度 = 深度 D（盒子闭合）
    # 在「标准六视图（各视图同比例渲染）」下即等于其等比缩放结果，不会变形；
    # 若源比例不标准，会以 (Wm, D) 强制对齐（保证六视图盒子闭合）。
    if 'top' in orig:
        if D is None:
            tw, th = orig['top'][0], orig['top'][1]
            D = max(1, round(th * (Wm / tw))) if tw else Hm
        sizes['top'] = (Wm, D)
        sizes['bottom'] = (Wm, D)

    return sizes, notes, (Wm, Hm), D


def _parse_main_dims(params, ppi):
    """从 cm 参数解析主视图目标像素宽/高；未指定(<=0)返回 None。"""
    mw = params.get('main_w_cm') or 0
    mh = params.get('main_h_cm') or 0
    try:
        mw = float(mw)
    except Exception:
        mw = 0
    try:
        mh = float(mh)
    except Exception:
        mh = 0
    main_w = round(mw / 2.54 * ppi) if mw > 0 else None
    main_h = round(mh / 2.54 * ppi) if mh > 0 else None
    return main_w, main_h


def _parse_stereo_dims(params, ppi):
    """从 cm 参数解析立体图目标像素宽/高；未指定(<=0)返回 (None, None)。"""
    sw = params.get('stereo_w_cm') or 0
    sh = params.get('stereo_h_cm') or 0
    try:
        sw = float(sw)
    except Exception:
        sw = 0
    try:
        sh = float(sh)
    except Exception:
        sh = 0
    sw = round(sw / 2.54 * ppi) if sw > 0 else None
    sh = round(sh / 2.54 * ppi) if sh > 0 else None
    return sw, sh


def process(session, params):
    """返回每个视图的目标尺寸、物理尺寸与改前/改后缩略图(base64)。
    尺寸基准为产品外轮廓（crop 开启时）；否则为整图。"""
    ppi = int(params.get('ppi', 300))
    crop = bool(params.get('crop', True))
    tol = float(params.get('tol', 30))
    main_w, main_h = _parse_main_dims(params, ppi)
    stereo_w, stereo_h = _parse_stereo_dims(params, ppi)

    working, bbox = build_working(session, crop, tol)
    orig = {}
    for v in ALL_VIEWS:
        if v in working:
            _, (pw, ph) = working[v]
            orig[v] = (pw, ph, session['ppi'].get(v))
    sizes, notes, (Wm, Hm), D = compute_targets(orig, main_w, main_h)
    if 'left' in sizes:
        D = sizes['left'][0]
    elif 'top' in sizes:
        D = sizes['top'][1]
    else:
        D = Hm

    out = {}
    for v in ALL_VIEWS:
        if v not in working:
            continue
        img, (pw, ph) = working[v]
        if v == 'stereo':
            w, h, s_clamped = stereo_target(pw, ph, ppi, stereo_w, stereo_h)
            if s_clamped:
                notes.append('立体图高度已按上限 %.0fcm 钳制（等比缩小宽度，不变形）' % STEREO_H_MAX_CM)
        else:
            w, h = sizes[v]
        full = img.resize((w, h), Image.LANCZOS)
        # 改后缩略图（最长边 <= 260）
        scale = min(1.0, 260.0 / max(w, h))
        tw, th = max(1, round(w * scale)), max(1, round(h * scale))
        thumb = full.resize((tw, th), Image.LANCZOS)
        after_url = 'data:image/png;base64,' + image_to_b64(thumb, 'PNG')

        # 改前缩略图（整图）并叠加检测框
        full_img = session['full'][v]
        fw, fh = full_img.size
        bfs = min(1.0, 260.0 / max(fw, fh))
        btw, bth = max(1, round(fw * bfs)), max(1, round(fh * bfs))
        before_th = full_img.resize((btw, bth), Image.BILINEAR)
        b = bbox.get(v)
        if crop and b:
            from PIL import ImageDraw
            draw = ImageDraw.Draw(before_th)
            rx0, ry0, rx1, ry1 = round(b[0] * bfs), round(b[1] * bfs), round(b[2] * bfs), round(b[3] * bfs)
            draw.rectangle([rx0, ry0, rx1, ry1], outline=(39, 192, 138), width=2)
        before_url = 'data:image/png;base64,' + image_to_b64(before_th, 'PNG')

        out[v] = {
            'full': [fw, fh],
            'orig': [pw, ph],
            'bbox': list(b) if (crop and b) else None,
            'orig_ppi': session['ppi'].get(v),
            'target': [w, h],
            'cm': [round(w / ppi * 2.54, 2), round(h / ppi * 2.54, 2)],
            'before': before_url,
            'after': after_url,
            'cropped': bool(crop and b),
        }
    ow0, oh0 = orig['main'][0], orig['main'][1]
    out['_main_resized'] = (Wm != ow0) or (Hm != oh0)
    out['_main_target_cm'] = [round(Wm / ppi * 2.54, 2), round(Hm / ppi * 2.54, 2)]
    return out, notes, D


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._cors()
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _bytes(self, data, ctype, filename=None, fname_utf8=None):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self._cors()
        self.send_header('Content-Length', str(len(data)))
        if filename:
            if fname_utf8:
                from urllib.parse import quote as _q
                self.send_header('Content-Disposition',
                                 "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (filename, _q(fname_utf8)))
            else:
                self.send_header('Content-Disposition', 'attachment; filename="%s"' % filename)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            self._bytes(INDEX_HTML.encode('utf-8'), 'text/html; charset=utf-8')
        else:
            self._json({'error': 'not found'}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0) or 0)
        raw = self.rfile.read(length) if length else b''
        try:
            body = json.loads(raw.decode('utf-8')) if raw else {}
        except Exception:
            self._json({'error': 'invalid json'}, 400)
            return

        # 服务被主程序内嵌后监听 0.0.0.0，畸形请求不能让请求线程直接抛栈，
        # 否则会在主程序控制台刷 traceback 且客户端收不到任何响应。
        try:
            if path == '/api/upload':
                self.handle_upload(body)
            elif path == '/api/preview':
                self.handle_preview(body)
            elif path == '/api/export_images':
                self.handle_export_images(body)
            elif path == '/api/export_disk':
                self.handle_export_disk(body)
            elif path == '/api/zipxml_info':
                self.handle_zipxml_info(body)
            elif path == '/api/zipxml_save':
                self.handle_zipxml_save(body)
            elif path == '/api/zipxml_norm_image':
                self.handle_zipxml_norm_image(body)
            elif path == '/api/zip':
                self.handle_zip(body)
            elif path == '/api/relations':
                self.handle_relations(body)
            else:
                self._json({'error': 'not found'}, 404)
        except Exception as exc:
            try:
                self._json({'error': '%s: %s' % (type(exc).__name__, exc)}, 500)
            except Exception:
                pass

    def handle_upload(self, body):
        images = body.get('images', {})
        if not images or 'main' not in images:
            self._json({'error': '缺少主视图(main)'}, 400)
            return
        sess = {'full': {}, 'ppi': {}, 'ext': {}, 'name': {}, 'detect_cache': {}}
        for v in ALL_VIEWS:
            if v in images and images[v]:
                try:
                    im = b64_to_image(images[v])
                    im.load()
                    w, h = im.size
                    dpi = None
                    d = im.info.get('dpi')
                    if isinstance(d, (tuple, list)) and len(d) >= 2:
                        dpi = round(float(d[0]))
                    ext = (images.get('_ext_' + v) or (im.format or 'png')).lower()
                    if ext == 'jpeg':
                        ext = 'jpg'
                    sess['full'][v] = im
                    sess['ppi'][v] = dpi
                    sess['ext'][v] = ext
                    sess['name'][v] = images.get('_name_' + v) or ('%s.%s' % (VIEW_NAME[v], ext))
                except Exception as e:
                    self._json({'error': '视图 %s 解码失败: %s' % (v, e)}, 400)
                    return
        sid = uuid.uuid4().hex
        with LOCK:
            SESSIONS[sid] = sess
        # 清理过多会话
        with LOCK:
            if len(SESSIONS) > 50:
                oldest = next(iter(SESSIONS))
                SESSIONS.pop(oldest, None)
        self._json({'sid': sid, 'views': list(sess['full'].keys())})

    def handle_preview(self, body):
        sid = body.get('sid')
        with LOCK:
            sess = SESSIONS.get(sid)
        if not sess:
            self._json({'error': '会话不存在，请重新上传'}, 400)
            return
        try:
            out, notes, D = process(sess, body)
        except Exception as e:
            self._json({'error': '处理失败: %s' % e}, 500)
            return
        self._json({'views': out, 'notes': notes, 'depthD': D})

    def handle_relations(self, body):
        """特征关系分析（EUREKA）：解析权利要求书/说明书文本，返回气泡图数据。"""
        text = body.get('text') or ''
        try:
            result = relations_analyze(text)
        except Exception as exc:
            self._json({'error': '分析失败: %s' % exc}, 500)
            return
        self._json(result)

    def handle_zip(self, body):
        sid = body.get('sid')
        with LOCK:
            sess = SESSIONS.get(sid)
        if not sess:
            self._json({'error': '会话不存在，请重新上传'}, 400)
            return
        ppi = int(body.get('ppi', 300))
        crop = bool(body.get('crop', True))
        tol = float(body.get('tol', 30))
        main_w, main_h = _parse_main_dims(body, ppi)
        try:
            working, _ = build_working(sess, crop, tol)
            orig = {}
            for v in ORDER:
                if v in working:
                    _, (pw, ph) = working[v]
                    orig[v] = (pw, ph, sess['ppi'].get(v))
            sizes, _, _, _ = compute_targets(orig, main_w, main_h)
        except Exception as e:
            self._json({'error': '尺寸计算失败: %s' % e}, 500)
            return

        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
            for v in ALL_VIEWS:
                if v not in working:
                    continue
                img, (pw, ph) = working[v]
                if v == 'stereo':
                    w, h, _ = stereo_target(pw, ph, ppi, stereo_w, stereo_h)
                else:
                    w, h = sizes[v]
                full = img.resize((w, h), Image.LANCZOS)
                ext = sess['ext'].get(v, 'png')
                data = save_bytes(full, ext, ppi)
                z.writestr('%s.%s' % (VIEW_NAME[v], ext), data)
        ascii_name = 'six_views_%dppi.zip' % ppi
        utf8_name = '六视图_%dppi.zip' % ppi
        disp = "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_name, quote(utf8_name))
        self._bytes(buf.getvalue(), 'application/zip', disp)

    def handle_export_images(self, body):
        """返回每个视图【全分辨率】改后图（原始格式字节，base64），供前端直接写回原文件。"""
        sid = body.get('sid')
        with LOCK:
            sess = SESSIONS.get(sid)
        if not sess:
            self._json({'error': '会话不存在，请重新上传'}, 400)
            return
        ppi = int(body.get('ppi', 300))
        crop = bool(body.get('crop', True))
        tol = float(body.get('tol', 30))
        main_w, main_h = _parse_main_dims(body, ppi)
        stereo_w, stereo_h = _parse_stereo_dims(body, ppi)
        try:
            working, _ = build_working(sess, crop, tol)
            orig = {}
            for v in ALL_VIEWS:
                if v in working:
                    _, (pw, ph) = working[v]
                    orig[v] = (pw, ph, sess['ppi'].get(v))
            sizes, _, _, _ = compute_targets(orig, main_w, main_h)
        except Exception as e:
            self._json({'error': '尺寸计算失败: %s' % e}, 500)
            return
        out = {}
        for v in ALL_VIEWS:
            if v not in working:
                continue
            img, (pw, ph) = working[v]
            if v == 'stereo':
                w, h, _ = stereo_target(pw, ph, ppi, stereo_w, stereo_h)
            else:
                w, h = sizes[v]
            full = img.resize((w, h), Image.LANCZOS)
            ext = sess['ext'].get(v, 'png')
            data = save_bytes(full, ext, ppi)
            out[v] = base64.b64encode(data).decode('ascii')
        self._json({'images': out})

    def handle_export_disk(self, body):
        """把改后图按原文件名直接写回磁盘上的指定文件夹（覆盖原文件）。"""
        sid = body.get('sid')
        with LOCK:
            sess = SESSIONS.get(sid)
        if not sess:
            self._json({'error': '会话不存在，请重新上传'}, 400)
            return
        folder = (body.get('folder') or '').strip().strip('"')
        if not folder:
            self._json({'error': '请填写原图所在的文件夹完整路径'}, 400)
            return
        if not os.path.isdir(folder):
            self._json({'error': '文件夹不存在: %s' % folder}, 400)
            return
        ppi = int(body.get('ppi', 300))
        crop = bool(body.get('crop', True))
        tol = float(body.get('tol', 30))
        main_w, main_h = _parse_main_dims(body, ppi)
        stereo_w, stereo_h = _parse_stereo_dims(body, ppi)
        try:
            working, _ = build_working(sess, crop, tol)
            orig = {}
            for v in ALL_VIEWS:
                if v in working:
                    _, (pw, ph) = working[v]
                    orig[v] = (pw, ph, sess['ppi'].get(v))
            sizes, _, _, _ = compute_targets(orig, main_w, main_h)
        except Exception as e:
            self._json({'error': '尺寸计算失败: %s' % e}, 500)
            return
        written, failed = [], []
        for v in ALL_VIEWS:
            if v not in working:
                continue
            img, (pw, ph) = working[v]
            if v == 'stereo':
                w, h, _ = stereo_target(pw, ph, ppi, stereo_w, stereo_h)
            else:
                w, h = sizes[v]
            full = img.resize((w, h), Image.LANCZOS)
            ext = sess['ext'].get(v, 'png')
            fname = sess['name'].get(v) or ('%s.%s' % (VIEW_NAME[v], ext))
            # 防止路径穿越：只取文件名部分
            safe = os.path.basename(fname)
            try:
                with open(os.path.join(folder, safe), 'wb') as f:
                    f.write(save_bytes(full, ext, ppi))
                written.append(safe)
            except Exception as e:
                failed.append('%s: %s' % (safe, e))
        self._json({'written': written, 'failed': failed})

    # ============ ZIP XML 数据修改（tab3） ============

    ZIPXML_SESS = {}   # sid -> {'data': 原始zip字节, 'ts': 时间}

    def _zipxml_gc(self):
        now = time.time()
        for k in [k for k, v in self.ZIPXML_SESS.items() if now - v['ts'] > 3600]:
            self.ZIPXML_SESS.pop(k, None)

    def handle_zipxml_info(self, body):
        """解析上传的 ZIP（含嵌套 ZIP），返回文件清单 + 全部 XML 叶节点字段 + 附图预览。"""
        self._zipxml_gc()
        raw = base64.b64decode(body['zipB64'])
        sid = 'zx%d' % int(time.time() * 1000)
        self.ZIPXML_SESS[sid] = {'data': raw, 'ts': time.time()}
        files, fields, images = [], [], []
        try:
            for key, blob in _zipxml_iter(raw):
                low = key.lower()
                is_xml = low.endswith('.xml')
                is_img = _zipxml_is_image(key)
                files.append({'key': key, 'size': len(blob),
                              'xml': is_xml, 'img': is_img})
                if is_xml:
                    try:
                        root = _zipxml_parse(blob)
                        _zipxml_walk(root, [root.tag], key, fields)
                    except Exception as e:
                        fields.append({'id': key + '|!!parse', 'file': key,
                                       'path': '(解析失败)', 'value': str(e)})
                elif is_img:
                    try:
                        thumb, full = _zipxml_thumb(blob, key)
                        images.append({'key': key, 'name': key.split('>')[-1],
                                       'size': len(blob), 'thumb': thumb, 'full': full})
                    except Exception as e:
                        images.append({'key': key, 'name': key.split('>')[-1],
                                       'size': len(blob), 'thumb': '', 'full': '',
                                       'err': str(e)})
        except Exception as e:
            traceback.print_exc()
            self._json({'error': 'ZIP 解析失败: %s' % e}, 400)
            return
        self._json({'sid': sid, 'files': files, 'fields': fields, 'images': images})

    def handle_zipxml_save(self, body):
        """应用修改并重建 ZIP 返回。"""
        sess = self.ZIPXML_SESS.get(body.get('sid'))
        if not sess:
            self._json({'error': '会话已过期，请重新选择 ZIP 文件'}, 400)
            return
        edits = {}                      # id -> 新文本
        for e in body.get('edits', []):
            edits[e['id']] = e['value']
        sections = body.get('sections', [])   # 发明人/代理师 重建
        replaces = {r['name']: base64.b64decode(r['dataB64'])
                    for r in body.get('fileReplace', [])}
        deletes = frozenset(body.get('deletes') or [])          # 待删除的图片/附件 key
        adds = {}
        for a in (body.get('adds') or []):
            k = a.get('key')
            if k:
                adds[k] = {'data': base64.b64decode(a.get('dataB64', '') or b''),
                           'view': a.get('view') or ''}
        try:
            out = _zipxml_rebuild(sess['data'], edits, sections, replaces, '',
                                  deletes=deletes, adds=adds)
        except Exception as e:
            traceback.print_exc()
            self._json({'error': '重建 ZIP 失败: %s' % e}, 500)
            return
        fname = body.get('fname') or 'modified.zip'
        self._bytes(out, 'application/zip', 'modified.zip', fname_utf8=fname)


    def handle_zipxml_norm_image(self, body):
        """把替换图片归一化到专利尺寸限制后返回 JPEG(base64)。

        外观图片：72 <= ppi <= 300，宽 = 15cm，高 <= 22cm
        其他图片：72 <= ppi <= 300，宽 <= 16.5cm，高 <= 24.5cm
        """
        import io as _io
        raw = base64.b64decode(body.get('dataB64', '') or b'')
        profile = body.get('profile', 'other')
        try:
            im = Image.open(_io.BytesIO(raw))
        except Exception as e:
            self._json({'error': '无法识别图片：%s' % e}, 400)
            return
        im = im.convert('RGB')
        w0, h0 = im.size
        INCH = 2.54
        PPI_MIN, PPI_MAX = 72, 300
        if profile == 'appearance':
            WCM, HCM = 15.0, 22.0
        else:
            WCM, HCM = 16.5, 24.5
        ratio = h0 / float(w0)
        if profile == 'appearance':
            # 宽度固定 15cm；高度必须 <= 22cm
            # 取「保持原像素宽度」对应的 ppi，并钳制到 [72,300]
            ppi = w0 / (WCM / INCH)
            ppi = max(PPI_MIN, min(PPI_MAX, ppi))
            out_w = int(round(WCM / INCH * ppi))
            out_h = int(round(out_w * ratio))
            if out_h / ppi * INCH > HCM + 1e-6:
                # 太高：改为按高度 22cm 适配（此情形下宽度必 < 15cm，仍满足限制）
                ppi = min(PPI_MAX, max(PPI_MIN, h0 / (HCM / INCH)))
                out_h = int(round(HCM / INCH * ppi))
                out_w = int(round(out_h / ratio))
        else:
            # 宽 <= 16.5 高 <= 24.5，ppi <= 300；仅缩小不放大（放大无意义）
            w_box = WCM / INCH * PPI_MAX
            h_box = HCM / INCH * PPI_MAX
            scale = min(1.0, w_box / w0, h_box / h0)
            ppi = PPI_MAX
            out_w = max(1, int(round(w0 * scale)))
            out_h = max(1, int(round(h0 * scale)))
        if (out_w, out_h) != (w0, h0):
            im = im.resize((out_w, out_h), Image.LANCZOS)
        buf = _io.BytesIO()
        im.save(buf, 'JPEG', dpi=(int(round(ppi)), int(round(ppi))), quality=90)
        data = buf.getvalue()
        cmW = out_w / ppi * INCH
        cmH = out_h / ppi * INCH
        # 警告：分辨率未达 300PPI，或原图过小被迫放大（画质下降）
        warn = (ppi < PPI_MAX - 1) or (out_w > w0 + 1)
        self._json({'ok': True, 'dataB64': base64.b64encode(data).decode('ascii'),
                    'w': out_w, 'h': out_h, 'ppi': int(round(ppi)),
                    'cmW': round(cmW, 2), 'cmH': round(cmH, 2),
                    'warn': bool(warn), 'orig': {'w': w0, 'h': h0}})

# ---------- ZIP XML 辅助函数 ----------


# ---------- ZIP XML 辅助函数（续） ----------

def _zipxml_iter(data, prefix=''):
    """递归展开 ZIP（含嵌套 ZIP），yield (逻辑路径, 字节)。"""
    zin = zipfile.ZipFile(io.BytesIO(data))
    for info in zin.infolist():
        name = info.filename
        if name.endswith('/') or not name:
            continue
        blob = zin.read(name)
        key = prefix + name
        if name.lower().endswith('.zip'):
            for k, b in _zipxml_iter(blob, key + '>'):
                yield k, b
        else:
            yield key, blob


_IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff',
             '.webp', '.svg')
_MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
         '.gif': 'image/gif', '.bmp': 'image/bmp', '.tif': 'image/tiff',
         '.tiff': 'image/tiff', '.webp': 'image/webp', '.svg': 'image/svg+xml'}


def _zipxml_is_image(key):
    return key.lower().endswith(_IMG_EXT)


def _zipxml_thumb(blob, key):
    """返回 (thumb_dataurl, full_dataurl)。

    位图用 Pillow 缩放为 JPEG（透明 PNG 转白底）；SVG 与解码失败的情况
    回退为原始字节的 data URL，保证前端至少能直接显示原图。
    """
    ext = os.path.splitext(key)[1].lower()
    mime = _MIME.get(ext, 'application/octet-stream')
    if ext == '.svg':
        b64 = base64.b64encode(blob).decode('ascii')
        url = 'data:%s;base64,%s' % (mime, b64)
        return url, url
    try:
        im = Image.open(io.BytesIO(blob))
        im = im.convert('RGB')
        w, h = im.size

        def resize(side):
            if max(w, h) > side:
                r = side / float(max(w, h))
                return im.resize((max(1, int(w * r)), max(1, int(h * r))),
                                Image.LANCZOS)
            return im

        def enc(img, quality=82):
            buf = io.BytesIO()
            img.save(buf, 'JPEG', quality=quality)
            return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')

        return enc(resize(360)), enc(resize(1000))
    except Exception:
        try:
            b64 = base64.b64encode(blob).decode('ascii')
            return 'data:%s;base64,%s' % (mime, b64), 'data:%s;base64,%s' % (mime, b64)
        except Exception:
            return '', ''


def _zipxml_parse(blob):
    return ET.fromstring(blob)


def _seg(tag, idx):
    """路径段：同名兄弟节点加 [序号]。"""
    return '%s[%d]' % (tag, idx) if idx else tag


def _zipxml_children(elem):
    """返回 [(路径段, 子元素)]，同名兄弟编号 1..n。"""
    cnt = Counter(ch.tag for ch in elem)
    seen = Counter()
    out = []
    for ch in elem:
        seen[ch.tag] += 1
        out.append((_seg(ch.tag, seen[ch.tag] if cnt[ch.tag] > 1 else 0), ch))
    return out


_ZX_CHECK_TAGS = ('附加',)
_ZX_DIV_TAGS = ('省自治区直辖市名称', '市县名称', '省级区划代码', '市县区划代码',
                '省份', '城市', '省', '市')


def _zipxml_walk(elem, path, fkey, out):
    kids = _zipxml_children(elem)
    if not kids:
        tag = path[-1] if path else ''
        if tag in _ZX_CHECK_TAGS:
            ftype = 'checkbox'
        elif tag in _ZX_DIV_TAGS:
            ftype = 'div'
        else:
            ftype = 'text'
        out.append({'id': fkey + '|' + '/'.join(path), 'file': fkey,
                    'path': '/'.join(path), 'value': elem.text or '', 'type': ftype})
        return
    for seg, ch in kids:
        _zipxml_walk(ch, path + [seg], fkey, out)


def _zipxml_leaf_get(parent, tag):
    """取 parent 直接子节点中名为 tag 的第一个叶元素。"""
    if parent is None:
        return None
    for ch in parent:
        if ch.tag == tag:
            return ch
    return None


def _zipxml_serialize(root, original):
    """保留原始声明/DOCTYPE/PI 头，仅替换根元素内容。"""
    m = re.search(rb'<[^\?!/]', original)
    head = original[:m.start()] if m else b''
    body = ET.tostring(root, encoding='unicode')   # unicode 模式不含 xml 声明
    return head + body.encode('utf-8')


def _zipxml_clone_template(nodes):
    """克隆节点模板（用于重建列表型节点）。"""
    import copy
    if nodes:
        return copy.deepcopy(nodes[0])
    return None


def _zipxml_apply_sections(root, fkey, sections):
    """处理结构性重建：发明人 / 代理师 / 指定代理师 / 日期。"""
    import copy
    for sec in sections:
        if sec.get('file') != fkey:
            continue
        kind = sec['kind']
        # 在根的任意层级查找目标容器（按标签名，深度优先）
        def find_all(elem, tag):
            hits = []
            for ch in elem:
                if ch.tag == tag:
                    hits.append(ch)
                hits.extend(find_all(ch, tag))
            return hits

        if kind in ('inventors', 'designers'):
            cont_tag = '设计人' if kind == 'designers' else '发明人'
            first_tag = '第一设计人' if kind == 'designers' else '第一发明人'
            other_tag = '其他设计人' if kind == 'designers' else '其他发明人'
            conts = find_all(root, cont_tag)
            if not conts:
                continue
            cont = conts[0]
            firsts = find_all(cont, first_tag)
            others = [ch for ch in cont if ch.tag == other_tag]
            tpl = _zipxml_clone_template(others)
            # 第一发明人 / 第一设计人
            f = sec.get('first') or {}
            if firsts:
                for tag, val in (('姓名', f.get('name')), ('身份证件号码', f.get('idcard'))):
                    if val is not None:
                        leaf = _zipxml_leaf_get(firsts[0], tag)
                        if leaf is not None:
                            leaf.text = val
            # 其他：删除重建
            for ch in others:
                cont.remove(ch)
            for i, o in enumerate(sec.get('others', [])):
                if tpl is not None:
                    node = copy.deepcopy(tpl)
                else:
                    node = ET.Element(other_tag, {'顺序': str(i + 1)})
                    for t in ('姓名', '请求不公开', '英文姓名', '国籍', '身份证件号码'):
                        node.append(ET.Element(t))
                node.set('顺序', str(i + 1))
                for leaf in list(node):
                    if leaf.tag in ('姓名', '身份证件号码'):
                        leaf.text = o.get('name') if leaf.tag == '姓名' else o.get('idcard')
                cont.append(node)

        elif kind == 'agents':
            # 请求书：专利代理机构/代理师[姓名,资格证号,电话]
            for org in find_all(root, '专利代理机构'):
                olds = [ch for ch in org if ch.tag == '代理师']
                tpl = _zipxml_clone_template(olds)
                for ch in olds:
                    org.remove(ch)
                for i, a in enumerate(sec.get('list', [])):
                    if tpl is not None:
                        node = copy.deepcopy(tpl)
                    else:
                        node = ET.Element('代理师', {'顺序': str(i + 1)})
                        for t in ('姓名', '资格证号', '电话'):
                            node.append(ET.Element(t))
                    node.set('顺序', str(i + 1))
                    for leaf in node:
                        if leaf.tag in ('姓名', '资格证号', '电话'):
                            leaf.text = a.get({'姓名': 'name', '资格证号': 'zgzh',
                                               '电话': 'phone'}[leaf.tag]) or ''
                    org.append(node)

        elif kind == 'specAgents':
            # 委托书：代理师/指定代理师[姓名]
            for grp in find_all(root, '代理师'):
                olds = [ch for ch in grp if ch.tag == '指定代理师']
                tpl = _zipxml_clone_template(olds)
                for ch in olds:
                    grp.remove(ch)
                for i, a in enumerate(sec.get('list', [])):
                    if tpl is not None:
                        node = copy.deepcopy(tpl)
                    else:
                        node = ET.Element('指定代理师', {'顺序': str(i + 1)})
                        node.append(ET.Element('姓名'))
                    node.set('顺序', str(i + 1))
                    for leaf in node:
                        if leaf.tag == '姓名':
                            leaf.text = a.get('name') or ''
                    grp.append(node)


def _zx_basename(p):
    return (p or '').replace('\\', '/').split('/')[-1]


def _zx_child_text(parent, tag):
    for ch in parent:
        if ch.tag == tag:
            return ch.text or ''
    return ''


def _zipxml_sync_images(root, code, add_items, del_names):
    """按「新增 / 删除」的图片同步文档 XML 里的图片节点。

    add_items: [(文件名, 视图名称, 字节)]；del_names: 被删除文件的基本名集合。
    返回是否发生改动。
    """
    if not add_items and not del_names:
        return False
    add_items = list(add_items)
    del_names = set(del_names)
    changed = False

    if code == '130001':
        # 外观设计图片或照片：<图片或照片 顺序><视图名称><文件类型><文件名称>
        items = [e for e in list(root) if e.tag == '图片或照片']
        for e in items:
            if _zx_basename(_zx_child_text(e, '文件名称')) in del_names:
                root.remove(e)
                changed = True
        items = [e for e in list(root) if e.tag == '图片或照片']
        for fn, view, _data in add_items:
            e = ET.SubElement(root, '图片或照片', {'顺序': '0', '宽度': '', '高度': ''})
            ET.SubElement(e, '视图名称').text = view or '其他视图'
            ET.SubElement(e, '文件类型').text = (fn.rsplit('.', 1)[-1] if '.' in fn else 'jpg').lower()
            ET.SubElement(e, '文件名称').text = fn
            items.append(e)
            changed = True
        for i, e in enumerate([x for x in list(root) if x.tag == '图片或照片'], 1):
            e.set('顺序', str(i))
        return changed

    if code == '100003':
        # 说明书附图：<cn-drawings><figure id num figure-labels><img file wi he/>
        drawings = None
        for e in root.iter('cn-drawings'):
            drawings = e
            break
        if drawings is None:
            return False
        figs = [e for e in list(drawings) if e.tag == 'figure']
        for fg in figs:
            img = None
            for cc in fg:
                if cc.tag == 'img':
                    img = cc
                    break
            if img is not None and _zx_basename(img.get('file', '')) in del_names:
                drawings.remove(fg)
                changed = True
        figs = [e for e in list(drawings) if e.tag == 'figure']
        max_id = 0
        for fg in figs:
            for cc in fg:
                if cc.tag == 'img':
                    m = re.search(r'(\d+)', cc.get('id', '') or '')
                    if m:
                        max_id = max(max_id, int(m.group(1)))
        for fn, _view, _data in add_items:
            n = len(figs) + 1
            max_id += 1
            wi = he = ''
            try:
                im = Image.open(io.BytesIO(_data))
                w, h = im.size
                wi = '%.2f' % (w / 300.0 * 25.4)
                he = '%.2f' % (h / 300.0 * 25.4)
            except Exception:
                pass
            fg = ET.SubElement(drawings, 'figure',
                               {'id': 'f%04d' % n, 'num': '%04d' % n,
                                'figure-labels': '图 %d' % n})
            ET.SubElement(fg, 'img', {'id': 'idf_%04d' % max_id, 'file': fn,
                                      'img-format': (fn.rsplit('.', 1)[-1] if '.' in fn else 'jpg').lower(),
                                      'inline': 'yes', 'wi': wi, 'he': he})
            figs.append(fg)
            changed = True
        for i, fg in enumerate([x for x in list(drawings) if x.tag == 'figure'], 1):
            fg.set('id', 'f%04d' % i)
            fg.set('num', '%04d' % i)
            fg.set('figure-labels', '图 %d' % i)
        return changed

    if code == '100007':
        # 委托书：<图片或照片 顺序><说明><文件名称>
        for e in [x for x in list(root) if x.tag == '图片或照片']:
            if _zx_basename(_zx_child_text(e, '文件名称')) in del_names:
                root.remove(e)
                changed = True
        for fn, _view, _data in add_items:
            e = ET.SubElement(root, '图片或照片', {'顺序': '0'})
            ET.SubElement(e, '说明')
            ET.SubElement(e, '文件名称').text = fn
            changed = True
        for i, e in enumerate([x for x in list(root) if x.tag == '图片或照片'], 1):
            e.set('顺序', str(i))
        return changed

    return False


def _zipxml_rebuild(data, edits, sections, replaces, prefix,
                    deletes=None, adds=None):
    """递归重建 ZIP：改 XML 文本、重建结构节、替换 / 删除 / 新增文件。

    deletes: 需要移除的条目逻辑 key 集合（全路径，含嵌套 ZIP 前缀）
    adds:    {逻辑 key: 字节}，key 形如 'outer.zip>inner.zip>100003/000007.tif'
    """
    if deletes is None:
        deletes = frozenset()
    if adds is None:
        adds = {}
    zin = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    zout = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)
    for info in zin.infolist():
        name = info.filename
        if name.endswith('/') or not name:
            continue
        key = prefix + name
        if key in deletes:
            continue
        blob = zin.read(name)
        if name.lower().endswith('.zip'):
            blob = _zipxml_rebuild(blob, edits, sections, replaces, key + '>',
                                   deletes=deletes, adds=adds)
        elif key in replaces:
            blob = replaces.pop(key)
        elif key.lower().endswith('.xml'):
            root = _zipxml_parse(blob)
            changed = False
            # 文本编辑
            def walk_apply(elem, path):
                nonlocal changed
                kids = _zipxml_children(elem)
                if not kids:
                    eid = key + '|' + '/'.join(path)
                    if eid in edits:
                        if (elem.text or '') != edits[eid]:
                            elem.text = edits[eid]
                            changed = True
                    return
                for seg, ch in kids:
                    walk_apply(ch, path + [seg])
            walk_apply(root, [root.tag])
            _zipxml_apply_sections(root, key, sections)
            # 图片增减：同步文档 XML 里的图片节点（外观图片 / 说明书附图 / 委托书扫描件）
            tail = key.split('>')[-1]
            mc = re.search(r'/(\d{6})/', tail)
            code = mc.group(1) if mc else None
            if code in ('130001', '100003', '100007'):
                dir_key = tail.rsplit('/', 1)[0] if '/' in tail else ''
                add_items = []
                for akey, ainfo in adds.items():
                    atail = akey.split('>')[-1]
                    if ('/' in atail and atail.rsplit('/', 1)[0] == dir_key):
                        add_items.append((_zx_basename(akey), ainfo.get('view') or '',
                                          ainfo.get('data') or b''))
                del_names = [_zx_basename(k) for k in deletes
                             if '/' in k.split('>')[-1]
                             and k.split('>')[-1].rsplit('/', 1)[0] == dir_key]
                if _zipxml_sync_images(root, code, add_items, del_names):
                    changed = True
            if changed or any(s.get('file') == key for s in sections):
                blob = _zipxml_serialize(root, blob)
        st = zipfile.ZipInfo(info.filename, date_time=info.date_time)
        st.compress_type = zipfile.ZIP_DEFLATED
        st.external_attr = info.external_attr
        zout.writestr(st, blob)
    # 追加本层新增文件（key 去掉本层前缀后不再含 '>' 的才是本层）
    for key, ainfo in adds.items():
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        if not rest or '>' in rest:
            continue
        st = zipfile.ZipInfo(rest, date_time=time.localtime()[:6])
        st.compress_type = zipfile.ZIP_DEFLATED
        st.external_attr = 0o644 << 16
        zout.writestr(st, ainfo.get('data') or b'')
    zout.close()
    return buf.getvalue()

PROBE_MARKER = b'fenrir-design-adjust'
DEFAULT_PORT = 5000
PORT_TRIES = 5

class _DesignHTTPServer(ThreadingHTTPServer):
    # Windows 上 SO_REUSEADDR 允许多个进程绑定同一端口（会造成"端口劫持"，
    # 两个服务都监听 5000），这里关掉；请求线程设为 daemon，退出不阻塞。
    allow_reuse_address = False
    daemon_threads = True


_lock = threading.Lock()
_state = {
    'module': None,
    'httpd': None,       # 非 None 表示服务由本进程启动，stop() 才会去关它
    'thread': None,
    'port': DEFAULT_PORT,
    'external': False,
    'error': '',
}


def _probe(port, timeout=0.25):
    """端口上是否已经是本项目自带的设计调整服务。

    用裸 socket 而不是 urllib：urllib 会受系统 HTTP_PROXY 影响，且对关闭的
    端口要等完整超时；这里只发一个极小的 GET，读到标记即返回。
    """
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b'GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n'
                         b'Connection: close\r\n\r\n')
            buf = b''
            while len(buf) < 65536:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                buf += chunk
                if PROBE_MARKER in buf:
                    return True
            return b' 200' in buf[:64] and PROBE_MARKER in buf
    except Exception:
        return False


def _serve(httpd):
    try:
        httpd.serve_forever(poll_interval=0.2)
    except Exception as exc:  # 服务线程异常不应拖垮主程序
        _state['error'] = '%s: %s' % (type(exc).__name__, exc)


def ensure_started():
    """确保服务可用；返回 (ok, message)。多次调用只有第一次真正做事。"""
    with _lock:
        if _state['httpd'] is not None or _state['external']:
            return True, _describe_locked()
        try:
            handler = Handler
        except Exception as exc:
            _state['error'] = '%s: %s' % (type(exc).__name__, exc)
            return False, '设计调整服务加载失败：%s' % _state['error']

        last_err = None
        for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_TRIES):
            if _probe(port):
                _state['port'] = port
                _state['external'] = True
                _state['httpd'] = None
                _state['error'] = ''
                return True, _describe_locked()
            try:
                httpd = _DesignHTTPServer(('0.0.0.0', port), handler)
            except OSError as exc:
                last_err = exc
                continue
            th = threading.Thread(target=_serve, args=(httpd,),
                                  name='FenrirDesignAdjustServer', daemon=True)
            th.start()
            _state.update(httpd=httpd, thread=th, port=port,
                          external=False, error='')
            return True, _describe_locked()

        _state['error'] = '端口 %d~%d 均不可用：%s' % (
            DEFAULT_PORT, DEFAULT_PORT + PORT_TRIES - 1, last_err)
        return False, _describe_locked()


_bootstrap_started = False


def start_async():
    """在后台线程里启动服务，不阻塞 Qt 主线程。

    首次绑定端口在部分 Windows 环境可能耗时数秒（防火墙/网络栈初始化），
    放到线程里就不会拖慢主窗口显示；按钮点击走 ensure_started() 时若启动
    尚未完成，会在同一把锁上等待，不会重复起服务。
    """
    global _bootstrap_started
    with _lock:
        if _bootstrap_started or _state['httpd'] is not None or _state['external']:
            return None
        _bootstrap_started = True
    th = threading.Thread(target=ensure_started,
                          name='FenrirDesignAdjustBootstrap', daemon=True)
    th.start()
    return th


def _describe_locked():
    if _state['external']:
        return '复用已运行的设计调整服务（端口 %d）' % _state['port']
    if _state['httpd'] is not None:
        return '设计调整服务已启动（端口 %d）' % _state['port']
    return '设计调整服务未启动' + ('：' + _state['error'] if _state['error'] else '')


def describe():
    with _lock:
        return _describe_locked()


def running():
    with _lock:
        return _state['httpd'] is not None or _state['external']


def state():
    with _lock:
        return {
            'running': _state['httpd'] is not None or _state['external'],
            'owned': _state['httpd'] is not None,
            'external': _state['external'],
            'port': _state['port'],
            'error': _state['error'],
            'base_dir': BASE_DIR,
        }


def _lan_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return '127.0.0.1'


def tab_url(n, host=None):
    """生成深链：n=1 调整外观图 / 2 附图标注 / 3 XML 修改。"""
    with _lock:
        port = _state['port']
    host = host or '127.0.0.1'
    return 'http://%s:%d/?tab=%d' % (host, port, int(n))


def lan_url(n=None):
    host = _lan_ip()
    return tab_url(n or 1, host)


def stop():
    """关闭本进程启动的服务；复用外部服务时不做任何事。

    若在极短的时间内退出、后台启动线程还持有锁，不要卡住退出流程：
    服务线程都是 daemon，进程结束时套接字会一并关闭。
    """
    if not _lock.acquire(timeout=0.5):
        return
    try:
        httpd = _state['httpd']
        th = _state['thread']
        _state['httpd'] = None
        _state['thread'] = None
        _state['external'] = False
    finally:
        _lock.release()
    if httpd is not None:
        try:
            httpd.shutdown()
        except Exception:
            pass
        try:
            httpd.server_close()
        except Exception:
            pass
        if th is not None:
            th.join(timeout=2)

"""专利预审形式缺陷规则引擎（纯 Python，无 Qt 依赖）。

依据朱青等《专利预审常见形式缺陷及查错软件设计实现》（中国发明与专利,
2021(12)）第 71~74 页整理，补齐 Fenrir 原校验器缺失的规则，重点解决论文
反复强调的「技术特征—附图标记对应关系」查错：

    说明书附图说明 → 解析「编号、技术特征」对应表 →
    用对应表校验权利要求书 / 说明书具体实施方式中的编号与名称是否一致 →
    错误清单给出可精确定位的原文词句。

模块只做分析与解析，不碰 UI；返回的 Issue 带 locate 字段供面板定位高亮。
"""

import re
from collections import namedtuple

# category, location, message, score(负=扣分), locate(正文中的定位词句)
Issue = namedtuple('Issue', 'category location message score locate')

SECTIONS = ['技术领域', '背景技术', '发明内容', '附图说明', '具体实施方式']
SECTION_SET = set(SECTIONS) | {'实用新型内容'}
# 论文列举的非标准小标题写法
SECTION_ALIASES = {
    '具体实现方式': '具体实施方式', '实施方式': '具体实施方式',
    '具体实施方法': '具体实施方式', '具体实施例': '具体实施方式',
    '附图简要说明': '附图说明', '附图简述': '附图说明',
    '附图的简要说明': '附图说明', '附图简单说明': '附图说明',
    '所属技术领域': '技术领域', '发明所属技术领域': '技术领域',
    '已有技术': '背景技术', '现有技术': '背景技术',
    '发明目的': '发明内容', '实用新型内容': '发明内容',
    '发明内容或实用新型内容': '发明内容',
}

# 编号与名称之间允许的分隔符（论文的「顿号 / 逗号 / 自定义符号分隔」）
DEFAULT_PAIR_SEPS = '、，,．.：:；;—-—~ '
PAIR_SEP_PRESETS = {
    '自动识别': DEFAULT_PAIR_SEPS,
    '顿号、': '、',
    '逗号，': '，,',
    '分号；': '；;',
    '点号.': '.．',
    '冒号：': '：:',
}
ENTRY_SPLIT = re.compile(r'[；;。\n]+')
MARK_NUM = r'\d{1,4}[a-zA-Z]?'

CLAIM_HEAD_LINE = re.compile(r'(?m)^\s*(\d{1,2})\s*[.、．]\s*')
CLAIM_HEAD_INLINE = re.compile(r'(?:^|(?<=。))\s*(\d{1,2})\s*[.、．]\s*')
MENTION = re.compile(
    r'([\u4e00-\u9fa5]{2,12})\s*([（(])?\s*(' + MARK_NUM + r')\s*([)）])?')
CITATION = re.compile(r'根据权利要求\s*(\d{1,2})\s*(?:或|、|，|,|至|~|-|\s)*'
                      r'(?:\d{1,2}\s*)*(?:所述|中任一项|任一|之一)?')
BOUNDARY_WORDS = re.compile(r'其特征在于|其特征是|其特点在于|特征在于')

# 不确定用语：只收「语义上确实造成保护范围不清楚」的词。
# 原校验器把「厚/薄/强/弱/等/可以/约」等单字也列入，几乎每篇都会误报。
UNCERTAIN_WORDS = [
    '优选', '优选地', '最好', '最佳的', '尤其', '特别是', '必要时', '必要时可',
    '大约', '约为', '接近', '基本上', '大致', '或许', '可能', '可以是',
    '类似物', '类似材料', '等等', '例如', '比如说', '某种程度上', '一定程度',
    '适当', '适量', '理想的', '较优', '任意的', '等等',
]

# 从「编号前的中文串」里剥掉的非技术特征成分（长的排前面）
STOP_PREFIXES = (
    '所述', '上述', '根据权利要求书', '根据权利要求', '权利要求', '权力要求',
    '按照', '根据', '参见图', '如图', '见图', '实施例', '具体实施', '图', '第',
    '包括', '包含', '设置于', '设置有', '设有', '位于', '设于', '置于',
    '一种', '该', '其', '和', '与', '或', '及', '的', '中', '上', '下',
    '内', '外', '前', '后', '时', '为', '在', '有', '并',
)
# 命中这些词说明这一段不是「技术特征 + 编号」，而是引用/图号/段落描述
NON_FEATURE_MARKERS = (
    '要求', '如图', '见图', '附图', '实施例', '说明书', '本发明', '实用新型',
    '发明', '图中', '例如', '比如', '并且', '同时', '以及', '所述',
)
# 引用基础检查里，「所述装置/所述方法」这类泛指主题词不算具体技术特征
GENERIC_TERMS = {
    '装置', '设备', '系统', '组件', '部件', '结构', '方法', '产品',
    '整体', '部分', '技术方案', '内容', '领域', '问题', '效果',
}
# 注意不要把「连接/固定/安装/设置」放进截断词：它们常是「连接孔」「固定座」
# 这类技术特征名的一部分，否则「所述连接孔」会被切掉而漏报引用基础。
TERM_STOP = re.compile('(?:' + '|'.join(re.escape(w) for w in (
    '优选', '采用', '可以', '包括', '设有', '为', '是', '与', '和', '或',
    '之间', '内', '上', '中', '的', '，', ',', '。', '；', '（', '(')) + ')')


def _strip_prefix(s):
    """把「所述连接孔」这类前缀剥成技术特征名「连接孔」。

    允许整词剥离（>= 而不是 >）：「根据权利要求」「如图」等剥完为空，
    调用方据此判定它不是技术特征，避免误报「标记对应关系错误」。
    """
    s = (s or '').strip()
    changed = True
    while changed and s:
        changed = False
        for w in STOP_PREFIXES:
            if s.startswith(w):
                s = s[len(w):]
                changed = True
                break
    return s.strip('的了地与其及和或')


def _clean_name(s):
    """清洗对应表里的技术特征名。"""
    s = (s or '').strip()
    s = re.sub(r'[（(]\s*' + MARK_NUM + r'\s*[)）]\s*$', '', s)
    s = s.strip('　 \t。，,、；;：:.．')
    s = re.sub(r'\s+', '', s)
    # 「图1为本发明结构示意图」这类描述行不是对应关系
    if '示意图' in s or '流程图' in s or '框图' in s or len(s) > 20:
        return ''
    return s


def _canon_section(s):
    """容错识别小标题：去装饰/编号后匹配标准章节或别名，失败返回 None。

    支持「【发明内容】」「（三）发明内容：」「发明内容、实用新型内容」
    「发明内容和/或实用新型内容」等常见写法。
    """
    s = (s or '').strip('　 \t').strip('：:')
    s = s.strip('　 \t')
    if s in SECTION_SET:
        return SECTION_ALIASES.get(s, s)
    if s in SECTION_ALIASES:
        return SECTION_ALIASES[s]
    t = s.strip('【】[]（）() ')
    t = re.sub(r'^[（(\[【]?[一二三四五六七八九十\d]{1,3}[)）、.．\]】]?\s*', '', t)
    if t in SECTION_SET:
        return SECTION_ALIASES.get(t, t)
    if t in SECTION_ALIASES:
        return SECTION_ALIASES[t]
    if re.match(r'^(发明内容|实用新型内容)\s*[、和或/／]\s*(实用新型内容|发明内容)$', t):
        return '发明内容'
    return None


def find_sections(text):
    """定位说明书标准章节，返回 (sections, order, wrong_titles, head_lines)。

    sections: {标准章节名: 章节正文}；order: 实际出现的标准章节顺序；
    wrong_titles: [(原文小标题, 应改为)]。
    """
    text = (text or '').replace('\u2029', '\n').replace('\r', '\n')
    lines = text.split('\n')
    heads = []
    for i, raw in enumerate(lines):
        s = raw.strip().strip('　')
        canon = _canon_section(s)
        if canon is None:
            continue
        # 原文与标准名不同（别名/组合写法）时记为非标准小标题；
        # 「实用新型内容」及「发明内容、实用新型内容」组合写法视为标准，
        # 不再提示「应写作发明内容」
        plain = re.sub(r'^[（(]?[一二三四五六七八九十\d]{1,3}[)）、.．]?\s*', '',
                       s.strip('　 :：'))
        plain_ok = (plain == canon or plain == '实用新型内容'
                    or re.match(r'^(发明内容|实用新型内容)\s*[、和或/／]\s*'
                                r'(实用新型内容|发明内容)$', plain))
        raw_name = '' if plain_ok else s.strip('　 :：')
        heads.append((i, canon, raw_name))
    sections, order, wrong = {}, [], []
    for k, (ln, name, raw) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = '\n'.join(lines[ln + 1:end]).strip()
        canonical = name
        if canonical not in sections or len(body) > len(sections[canonical]):
            sections[canonical] = body
        order.append(canonical)
        if raw:
            wrong.append((raw, canonical))
    # 首段（第一个章节之前）视为专利名称——仅当它确实像名称：单行、较短、
    # 不含权利要求特征。权利要求书在前、说明书在后时，这段是整篇权利要求，
    # 误当名称会谎报「发明名称超过 25 个字」「主题名称不一致」。
    if heads and heads[0][0] > 0:
        head_block = '\n'.join(lines[:heads[0][0]]).strip()
        if ('\n' not in head_block and len(head_block) <= 30
                and not BOUNDARY_WORDS.search(head_block)
                and '权利要求' not in head_block
                and not CLAIM_HEAD_LINE.search(head_block)):
            sections['专利名称'] = head_block
    return sections, order, wrong, heads


def parse_legend(section_text, pair_seps=None):
    """从「附图说明」正文解析「编号 → 技术特征」对应表。

    返回 (rows, warnings)。rows 为 [{'num','name','raw'}]；
    pair_seps 为编号与名称之间允许的分隔符集合（论文的分隔符选择/自定义）。
    """
    seps = pair_seps or DEFAULT_PAIR_SEPS
    item_re = re.compile(
        r'^\s*(?:图\s*)?(' + MARK_NUM + r')\s*[' + re.escape(seps) + r']\s*(.+)$')
    rows, seen, warnings = [], set(), []
    text = (section_text or '').replace('\u2029', '\n')
    for entry in ENTRY_SPLIT.split(text):
        entry = entry.strip().strip('　 ')
        if not entry:
            continue
        m = item_re.match(entry)
        if not m:
            # 含编号却解析不出名称：提示用户换分隔符或手动补录
            if re.search(r'\b' + MARK_NUM + r'\b', entry) and '示意图' not in entry:
                warnings.append('附图说明未能在「%s」中分离编号与技术特征，可切换分隔符或手动补录' %
                                entry[:24])
            continue
        num, name = m.group(1), _clean_name(m.group(2))
        if not name:
            continue
        if num in seen:
            continue
        seen.add(num)
        rows.append({'num': num, 'name': name, 'raw': entry})
    return rows, warnings


def legend_from_text(text, pair_seps=None):
    """在整篇文本里找附图说明章节并解析对应表，返回 (rows, warnings, sections)。"""
    sections, order, wrong, heads = find_sections(text)
    legend_src = sections.get('附图说明', '')
    if not legend_src:
        return [], [], sections
    rows, warns = parse_legend(legend_src, pair_seps)
    return rows, warns, sections


def extract_mentions(text):
    """提取正文中「技术特征 + 附图编号」的出现，返回候选列表。

    每项 {'name','num','paren','raw','pos'}；name 已剥离「所述」等非特征前缀。
    """
    text = (text or '').replace('\u2029', '\n')
    out = []
    for m in MENTION.finditer(text):
        core = _strip_prefix(m.group(1))
        if len(core) < 2 or core.isdigit():
            continue
        # 数字紧跟在「图」字后面的是图号引用（「结合图1」「如图2所示」），
        # 不是附图标记；_strip_prefix 后 core 可能不再以「图」结尾，
        # 因此用原匹配串判断。
        if m.group(1).endswith('图'):
            continue
        if any(k in core for k in NON_FEATURE_MARKERS):
            continue
        # 定位词只保留「技术特征名 + 编号（含原括号形式）」，
        # 去掉「所述」「上设置有」等前缀，问题清单才能精确跳到词句。
        orig = m.group(0)
        k = orig.find(core)
        shown = orig[k:].strip() if k >= 0 else (core + m.group(3))
        out.append({
            'name': core,
            'num': m.group(3),
            'paren': bool(m.group(2)) and bool(m.group(4)),
            'raw': shown,
            'pos': m.start(),
        })
    return out


def _name_matches(core, correct):
    """判断正文里的名称与对应表名称是否一致（允许加长/带修饰）。"""
    if not core or not correct:
        return True
    if core == correct or correct in core or core in correct:
        return True
    # 「连接柱/连接孔」一字之差正是论文要抓的错误，不做模糊放行
    return False


def _short_loc(raw, correct):
    """把「上还设置有定位销（13）」截成「定位销（13）」用于精确定位。"""
    k = raw.rfind(correct) if correct else -1
    return raw[k:].strip() if k >= 0 else raw


def check_legend_consistency(text, legend, scope='权利要求书', require_paren=True):
    """论文核心算法：用对应表校验正文里的技术特征—附图标记对应关系。"""
    issues = []
    table = {r['num']: r['name'] for r in legend}
    if not table:
        return issues
    for hit in extract_mentions(text):
        correct = table.get(hit['num'])
        if not correct:
            continue  # 编号不在对应表里 → 由 legend_gaps 报告遗漏
        raw = _short_loc(hit['raw'], correct)
        if not _name_matches(hit['name'], correct):
            issues.append(Issue(
                '标记对应', scope,
                '%s中「%s」附图标记对应关系错误，对应表为「%s（%s）」'
                % (scope, raw, correct, hit['num']),
                -10, raw))
        elif require_paren and not hit['paren']:
            issues.append(Issue(
                '标记括号', scope,
                '%s中「%s」的附图标记未加括号，应写作「%s（%s）」'
                % (scope, raw, correct, hit['num']),
                -2, raw))
        elif not require_paren and hit['paren']:
            issues.append(Issue(
                '标记括号', scope,
                '%s具体实施方式中「%s」的附图标记带括号，说明书正文中不应加括号'
                % (scope, raw),
                -2, raw))
    return issues


def legend_gaps(legend, body_text):
    """对应表遗漏校验 + 重复技术特征/重复附图标记（论文说明书功能区）。"""
    issues = []
    by_num, by_name = {}, {}
    for r in legend:
        by_num.setdefault(r['num'], set()).add(r['name'])
        by_name.setdefault(r['name'], set()).add(r['num'])
    for num, names in by_num.items():
        if len(names) > 1:
            issues.append(Issue('重复标记', '对应表',
                                '附图标记 %s 对应多个技术特征：%s'
                                % (num, '、'.join(sorted(names))), -5, str(num)))
    for name, nums in by_name.items():
        if len(nums) > 1:
            issues.append(Issue('重复特征', '对应表',
                                '技术特征「%s」对应多个附图标记：%s'
                                % (name, '、'.join(sorted(nums))), -5, name))
    used = {h['num'] for h in extract_mentions(body_text)}
    for num in sorted(by_num, key=lambda x: (len(x), x)):
        if num in used:
            continue
        issues.append(Issue('标记未用', '对应表',
                            '对应表中「%s %s」未在正文中出现'
                            % (num, next(iter(by_num[num]))), -1, num))
    for num in sorted(used - set(by_num), key=lambda x: (len(x), x)):
        issues.append(Issue('对应表遗漏', '附图说明',
                            '正文中出现的附图标记 %s 未记载于附图说明对应表' % num,
                            -5, num))
    return issues


def _norm_head_line(raw):
    """把一行文字归一成小标题（去编号前缀 / 空白），供章节标题比对。"""
    s = (raw or '').strip().strip('　')
    s = re.sub(r'^[（(]?[一二三四五六七八九十\d]{1,3}[)）、.．]?\s*', '', s)
    return s.strip('　 :：')


def claims_region(text):
    """截取整篇文档中的权利要求书部分。

    权利要求书在前、说明书在后的排版很常见：不截断的话 split_claims 会让
    最后一条权利要求吞并说明书正文——「两个以上句号」「缺少划界词」全部
    误报，「附图标记须加括号」也会错误地作用到具体实施方式。
    说明书在前、权利要求在后时不截断（每条权利要求自带编号标题，切分无碍）。
    """
    text = (text or '').replace('\u2029', '\n').replace('\r', '\n')
    lines = text.split('\n')
    cut = None
    for i, raw in enumerate(lines):
        s = _norm_head_line(raw)
        if s in SECTION_SET or s in SECTION_ALIASES:
            cut = i
            break
    if not cut:                       # 无说明书章节 / 说明书写在第 0 行
        return text
    head = '\n'.join(lines[:cut])
    claims = split_claims(head)
    if claims and any(BOUNDARY_WORDS.search(c['text']) for c in claims):
        return head
    return text


def split_claims(text):
    """切分权利要求，兼容 1. / 1、/ 1． 与「整段不换行」两种排版。"""
    text = (text or '').replace('\u2029', '\n').replace('\r', '\n').strip()
    if not text:
        return []
    parts = CLAIM_HEAD_LINE.split(text)
    if len(parts) < 3:
        parts = CLAIM_HEAD_INLINE.split(text)
    claims = []
    for i in range(1, len(parts) - 1, 2):
        try:
            num = int(parts[i])
        except ValueError:
            continue
        body = parts[i + 1].strip()
        if body:
            claims.append({'index': num, 'text': body})
    return claims


def _norm_topic(s):
    """主题名称比对前规范化：去段号 [0001]、空白与「一种」。"""
    s = re.sub(r'\[\d{3,5}\]', '', s or '')
    s = s.replace('一种', '')
    return re.sub(r'\s', '', s)


def _claim_topic(text):
    """提取权利要求主题名称：「一种XXX，其特征在于」/「根据权利要求N所述的XXX」。"""
    m = re.match(r'^一种(.{2,40}?)[，,]\s*(?:其特征在于|其特征是|包括|包含)', text)
    if not m:
        m = re.match(r'^一种(.{2,40}?)[，,。]', text)
    if m:
        return m.group(1).strip('的 ')
    m = re.search(r'根据权利要求[^，,]{0,20}?所述的(.{2,40}?)[，,]\s*其特征在于', text)
    if m:
        return m.group(1).strip('的 ')
    m = re.search(r'所述的(.{2,40}?)[，,]\s*其特征在于', text)
    if m:
        return m.group(1).strip('的 ')
    return ''


def check_claims_formal(text, legend=None, doc_title=''):
    """论文第 71~73 页列出的权利要求书形式缺陷。

    权利要求书与说明书同篇时只取权利要求书区域：句号 / 划界词 / 括号
    规则都不得越界到说明书正文（具体实施方式的附图标记本就不加括号）。
    """
    issues = []
    text = claims_region(text)
    claims = split_claims(text)
    if not claims:
        return issues
    total = len(claims)
    full = {c['index']: c['text'] for c in claims}
    topics = {}
    for c in claims:
        i, body = c['index'], c['text']
        loc = '权%d' % i
        # 句号
        n_period = body.count('。')
        if n_period == 0:
            issues.append(Issue('标点', loc, '权利要求%d结尾缺少句号' % i, -10, body[:18]))
        elif n_period >= 2:
            issues.append(Issue('标点', loc, '权利要求%d含有两个以上句号' % i, -10, '。'))
        # 划界词
        n_bound = len(BOUNDARY_WORDS.findall(body))
        if n_bound == 0:
            issues.append(Issue('划界词', loc, '权利要求%d缺少「其特征在于」划界用语' % i,
                                -10, body[:18]))
        elif n_bound > 1:
            issues.append(Issue('划界词', loc, '权利要求%d出现多个划界用语' % i,
                                -5, '其特征在于'))
        # 常见错写
        if '权力要求' in body:
            issues.append(Issue('错别字', loc, '「权力要求」应为「权利要求」', -5, '权力要求'))
        if '根据权利要求书' in body:
            issues.append(Issue('错写', loc,
                                '「根据权利要求书…所述」应为「根据权利要求…所述」',
                                -5, '根据权利要求书'))
        # 不确定用语
        for w in UNCERTAIN_WORDS:
            if w in body:
                issues.append(Issue('不确定用语', loc,
                                    '权利要求%d含不确定用语「%s」，可能导致保护范围不清楚'
                                    % (i, w), -5, w))
                break
        # 引用关系
        cited = [int(x) for x in re.findall(r'根据权利要求\s*(\d{1,2})', body)]
        dependent = bool(cited) or '根据权利要求' in body or ('权利要求' in body and i > 1)
        if i > 1 and not cited:
            issues.append(Issue('引用编号', loc,
                                '从属权利要求%d未写明所引用的权利要求编号' % i, -10, loc))
        for n in cited:
            if n >= i:
                issues.append(Issue('引用编号', loc,
                                    '权利要求%d引用了自身或其后的权利要求%d' % (i, n),
                                    -10, '根据权利要求%d' % n))
            elif n not in full:
                issues.append(Issue('引用编号', loc,
                                    '权利要求%d引用的权利要求%d不存在' % (i, n),
                                    -10, '根据权利要求%d' % n))
        if i > 1 and not cited and not dependent:
            pass
        # 独权写在从属之后
        if i > 1 and not dependent:
            issues.append(Issue('权项顺序', loc,
                                '独立权利要求未写在引用其的从属权利要求之前', -5, loc))
        # 主题名称一致性
        topic = _claim_topic(body)
        topics[i] = topic
        if topic and 1 in topics and topics[1] and i > 1:
            if not (topics[1] in topic or topic in topics[1]):
                issues.append(Issue('主题名称', loc,
                                    '权利要求%d主题名称「%s」与独立权利要求「%s」不一致'
                                    % (i, topic, topics[1]), -5, topic))
        # 「所述」引用基础：该「所述X」出现之前必须已经引入过 X
        # （本权前文 + 被引用权全文）。不能用整句做依据，否则 X 自身
        # 就在同一句里，检查永远不报。
        basis = ''.join(full[n] for n in cited if n in full)
        for m in re.finditer(r'所述', body):
            chunk = body[m.end():m.end() + 12]
            term = TERM_STOP.split(chunk, 1)[0].strip('的了')
            if len(term) < 2 or term in GENERIC_TERMS:
                continue
            before = (basis + body[:m.start()]).replace('所述', '')
            if term not in before:
                issues.append(Issue('引用基础', loc,
                                    '权利要求%d中「所述%s」缺少引用基础' % (i, term),
                                    -5, '所述' + term))
    # 独立权利要求主题与说明书/请求书名称
    if doc_title and 1 in topics and topics[1]:
        t = _norm_topic(doc_title)
        s = _norm_topic(topics[1])
        if t and s and not (t in s or s in t):
            issues.append(Issue('主题名称', '权1',
                                '独立权利要求主题「%s」与文档名称「%s」不一致'
                                % (topics[1], t), -5, topics[1]))
    # 对应表一致性（论文核心病例）
    if legend:
        issues += check_legend_consistency(text, legend, '权利要求书', True)
    return issues


def check_description_formal(text, legend=None, pair_seps=None):
    """论文第 72~74 页列出的说明书形式缺陷。"""
    issues = []
    sections, order, wrong, heads = find_sections(text)
    if not heads:
        return issues
    # 标准小标题：齐全、顺序、写法
    for raw, right in wrong:
        issues.append(Issue('小标题', raw,
                            '「%s」不是标准的小标题，应写作「%s」' % (raw, right),
                            -5, raw))
    canonical_order = [s for s in order if s in SECTIONS or s == '发明内容']
    expected = [s for s in SECTIONS if s in canonical_order or
                (s == '发明内容' and '发明内容' in sections)]
    if canonical_order != expected and len(canonical_order) == len(expected):
        issues.append(Issue('章节顺序', '说明书',
                            '说明书章节顺序不符合「技术领域→背景技术→发明内容→附图说明→具体实施方式」',
                            -5, order[0] if order else '说明书'))
    for s in ('技术领域', '背景技术', '具体实施方式'):
        if not sections.get(s):
            issues.append(Issue('形式缺陷', s, '说明书缺少「%s」部分' % s, -5, s))
    if not sections.get('发明内容'):
        issues.append(Issue('形式缺陷', '发明内容', '说明书缺少「发明内容/实用新型内容」部分', -5, '发明内容'))
    # 发明名称
    title = sections.get('专利名称', '')
    if len(title) > 25:
        issues.append(Issue('形式缺陷', '专利名称', '发明名称超过 25 个字', -2, title[:20]))
    # 附图说明 → 对应表
    legend_src = sections.get('附图说明', '')
    if legend_src and not legend:
        issues.append(Issue('对应表', '附图说明',
                            '附图说明中未解析出「编号—技术特征」对应关系，请检查分隔符',
                            -5, '附图说明'))
    detail = sections.get('具体实施方式', '')
    if legend and detail:
        issues += check_legend_consistency(detail, legend, '说明书', False)
    if legend:
        issues += legend_gaps(legend, text)
    # 摘要字数
    abstract = re.search(r'说明书摘要[：:]?\s*\n(.{0,2000}?)(?=\n\s*权利要求书|\Z)',
                         text.replace('\u2029', '\n'), re.S)
    if abstract:
        n = len(re.sub(r'\s', '', abstract.group(1)))
        if n > 300:
            issues.append(Issue('摘要', '说明书摘要',
                                '摘要文字部分（含标点符号）共 %d 字，超过 300 字' % n,
                                -5, '说明书摘要'))
    return issues


def dedupe(issues):
    """剔除冗余错误信息（论文「错误显示区」最后一步）。"""
    seen, out = set(), []
    for it in issues:
        key = (it.category, it.location, it.message)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def analyze(text, legend=None, pair_seps=None, doc_title='', include_claims=True,
            include_description=True):
    """对一段文本执行全部形式缺陷检查，返回去重后的 Issue 列表。

    同一文档里同时含说明书章节与权利要求书时两部分都查（论文的软件界面
    本来就是「权利要求书功能区 + 说明书功能区」共享一张对应表）。
    """
    issues = []
    sections, order, wrong, heads = find_sections(text)
    if include_description and len(heads) >= 3:
        issues += check_description_formal(text, legend, pair_seps)
    # 权利要求相关规则只在权利要求书区域生效（详见 claims_region）
    claim_text = claims_region(text)
    claims = split_claims(claim_text)
    has_claims = any(BOUNDARY_WORDS.search(c['text']) for c in claims)
    if include_claims and has_claims:
        issues += check_claims_formal(claim_text, legend, doc_title)
    return dedupe(issues)

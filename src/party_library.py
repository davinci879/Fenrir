# -*- coding: utf-8 -*-
"""申请人 / 发明人收藏夹（纯数据层，不依赖 Qt）。

一条档案（item）= 一套「申请人组 + 发明人组（+ 委托书扫描件）」，按客户或
项目命名，例如「远大铝业·沈阳科威」。收藏夹放在 data/party_library.json，
与文档存档分开，原因是：草稿存档按 tab 存、体积大（几 MB），而收藏夹要频繁
被别处读写，单独一个文件既能原子保存，也不会牵动 workspace.json；委托书
这类二进制附件另放 data/poa/（所有档案共用，文件名唯一），JSON 里只记文件名。

与 main.py 的数据口径保持一致：
    申请人 = [名称, 证件号, 地址, 邮编]   （4 元组）
    发明人 = [姓名, 身份证号]             （2 元组）
    poa    = [{file, name, size, ts}, ...] （委托书 JPG，可多张）
"""
import json
import os
import re
import shutil
import time
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PATH = os.path.join(DATA_DIR, 'party_library.json')
# 委托书扫描件统一放在 data/poa/：文件名带时间戳，档案里只记文件名
FILES_DIR = os.path.join(DATA_DIR, 'poa')
# 旧版按档案分目录存放的位置，读取时自动迁移到 data/poa/
LEGACY_FILES_DIR = os.path.join(DATA_DIR, 'party_library_files')
VERSION = 1

MAX_ITEMS = 500
MAX_POA = 20
MAX_POA_BYTES = 30 * 1024 * 1024
POA_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp')


# --------------------------------------------------------------- 基础
def _now():
    return int(time.time())


def _clean(s, limit=200):
    s = ('' if s is None else str(s))
    s = s.replace('\u3000', ' ').replace('\r', ' ').replace('\n', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:limit]


def normalize(info):
    """把 main.py 的 party_info 字典收敛成 (applicants, inventors)。

    兼容三种历史形态：dict / 只有 name+cert+address 的旧存档 /
    4 元组、2 元组长度不齐的行。空行（全空）直接丢掉。
    """
    info = info or {}
    apps = []
    for row in (info.get('applicants') or []):
        if isinstance(row, dict):
            row = (row.get('name'), row.get('cert'), row.get('address'),
                   row.get('postcode'))
        row = list(row or [])
        row += [''] * max(0, 4 - len(row))
        row = [_clean(v) for v in row[:4]]
        if any(row):
            apps.append(row)
    if not apps and (_clean(info.get('name')) or _clean(info.get('cert'))):
        apps = [[_clean(info.get('name')), _clean(info.get('cert')),
                 _clean(info.get('address')), _clean(info.get('postcode'))]]
    invs = []
    for row in (info.get('inventors') or []):
        if isinstance(row, dict):
            row = (row.get('name'), row.get('idcard') or row.get('cert'))
        row = list(row or [])
        row += [''] * max(0, 2 - len(row))
        row = [_clean(v) for v in row[:2]]
        if any(row):
            invs.append(row)
    return apps, invs


def is_empty(apps, invs):
    return not apps and not invs


def summary(item):
    """列表里的第二行说明：申请人数 / 发明人数 / 委托书 / 最近使用。"""
    n_app = len(item.get('applicants') or [])
    n_inv = len(item.get('inventors') or [])
    n_poa = len(item.get('poa') or [])
    bits = []
    if n_app:
        bits.append('申请人 %d' % n_app)
    if n_inv:
        bits.append('发明人 %d' % n_inv)
    if n_poa:
        bits.append('委托书 %d 张' % n_poa)
    if not bits:
        bits = ['空档案']
    used = item.get('used')
    if used:
        bits.append(_ago(used))
    return ' · '.join(bits)


def _ago(ts):
    try:
        d = max(0, _now() - int(ts))
    except Exception:
        return ''
    if d < 60:
        return '刚刚用过'
    if d < 3600:
        return '%d 分钟前' % (d // 60)
    if d < 86400:
        return '%d 小时前' % (d // 3600)
    if d < 86400 * 30:
        return '%d 天前' % (d // 86400)
    return time.strftime('%Y-%m-%d', time.localtime(int(ts)))


# --------------------------------------------------------------- 委托书附件
def _unique_name(ext):
    """data/poa 下的唯一文件名：时间戳 + 两位序号。"""
    stamp = time.strftime('%Y%m%d_%H%M%S')
    i = 1
    while True:
        name = '%s_%02d%s' % (stamp, i, ext)
        if not os.path.exists(os.path.join(FILES_DIR, name)):
            return name
        i += 1


def _normalize_poa(raw):
    out = []
    for e in (raw or []):
        if isinstance(e, str):
            e = {'file': e}
        if not isinstance(e, dict):
            continue
        fn = os.path.basename(_clean(e.get('file'), 200))
        if not fn:
            continue
        out.append({'file': fn,
                    'name': _clean(e.get('name'), 120) or fn,
                    'size': int(e.get('size') or 0),
                    'ts': int(e.get('ts') or 0)})
    return out[:MAX_POA]


def poa_path(item_id, entry):
    """某张委托书在本机的绝对路径（所有委托书都在 data/poa 下）。

    item_id 只为保持调用签名（旧版按档案分目录），这里不参与拼接。
    """
    fn = entry.get('file') if isinstance(entry, dict) else entry
    fn = os.path.basename(str(fn or ''))
    return os.path.join(FILES_DIR, fn) if fn else ''


def poa_files(item):
    """档案里实际存在的委托书文件（绝对路径，按收藏顺序）。"""
    out = []
    for e in (item or {}).get('poa') or []:
        p = poa_path(item.get('id'), e)
        if p and os.path.isfile(p):
            out.append(p)
    return out


def _poa_in_use(exclude_item_id=None):
    """其它档案还引用着的委托书文件名集合（删除前判断用）。"""
    used = set()
    for it in load():
        if exclude_item_id and it.get('id') == exclude_item_id:
            continue
        for e in it.get('poa') or []:
            fn = os.path.basename(str(e.get('file') or ''))
            if fn:
                used.add(fn)
    return used


def _remove_poa_file(name, in_use):
    """删除 data/poa 下的文件（只删这个目录里的，且没被别的档案引用）。"""
    fn = os.path.basename(str(name or ''))
    if not fn or fn in in_use:
        return
    p = os.path.abspath(os.path.join(FILES_DIR, fn))
    base = os.path.abspath(FILES_DIR)
    if not p.startswith(base + os.sep):
        return
    try:
        os.remove(p)
    except Exception:
        pass


def add_poa(item_id, paths):
    """把若干张 JPG 复制进 data/poa/ 并挂到该档案；返回更新后的档案。"""
    items = load()
    item = next((x for x in items if x['id'] == item_id), None)
    if item is None:
        return None
    item.setdefault('poa', [])
    have = {(e.get('name'), int(e.get('size') or 0)) for e in item['poa']}
    added = 0
    try:
        os.makedirs(FILES_DIR, exist_ok=True)
    except Exception:
        return item
    for src in (paths or []):
        try:
            if not src or not os.path.isfile(src):
                continue
            ext = os.path.splitext(src)[1].lower()
            if ext not in POA_EXTS:
                continue
            size = os.path.getsize(src)
            if size <= 0 or size > MAX_POA_BYTES:
                continue
            label = _clean(os.path.basename(src), 120) or ('委托书' + ext)
            if (label, size) in have:
                continue
            dst_name = _unique_name(ext)
            shutil.copy2(src, os.path.join(FILES_DIR, dst_name))
            item['poa'].append({'file': dst_name, 'name': label,
                                'size': size, 'ts': _now()})
            have.add((label, size))
            added += 1
            if len(item['poa']) >= MAX_POA:
                break
        except Exception:
            continue
    if added:
        save(items)
    return item


def remove_poa(item_id, entry):
    """删掉一张委托书（记录 + 文件）；文件被别的档案引用时只删记录。"""
    items = load()
    for it in items:
        if it['id'] != item_id:
            continue
        target = os.path.basename(str((entry or {}).get('file')
                                      if isinstance(entry, dict) else entry))
        keep, gone = [], False
        for e in it.get('poa') or []:
            if os.path.basename(str(e.get('file') or '')) == target:
                gone = True
            else:
                keep.append(e)
        if gone:
            it['poa'] = keep
            save(items)
            _remove_poa_file(target, _poa_in_use())
            return it
    return None


# --------------------------------------------------------------- 读前迁移
_LEGACY_MIGRATED = False


def _migrate_legacy_once():
    """把旧版 data/party_library_files/<id>/ 里的委托书搬到 data/poa/。

    只做一次（模块级标记）；失败不抛异常，下次启动再试。迁移后档案里的
    文件名同步改成新目录里的名字，旧目录整棵删掉（都是本程序自己复制进去的）。
    """
    global _LEGACY_MIGRATED
    if _LEGACY_MIGRATED:
        return
    _LEGACY_MIGRATED = True
    if not os.path.isdir(LEGACY_FILES_DIR):
        return
    mapping = {}
    try:
        os.makedirs(FILES_DIR, exist_ok=True)
        for root, _dirs, files in os.walk(LEGACY_FILES_DIR):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                new = _unique_name(ext)
                shutil.move(os.path.join(root, fn),
                            os.path.join(FILES_DIR, new))
                mapping[fn] = new
    except Exception:
        return
    try:
        with open(PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        items = raw.get('items') if isinstance(raw, dict) else raw
        changed = False
        for it in (items or []):
            for e in (it.get('poa') or []):
                if not isinstance(e, dict):
                    continue
                old = os.path.basename(str(e.get('file') or ''))
                if old in mapping:
                    e['file'] = mapping[old]
                    changed = True
        if changed:
            save(items)
    except Exception:
        # JSON 同步失败就把文件搬回去，避免档案指向不存在的文件
        for old, new in mapping.items():
            try:
                shutil.move(os.path.join(FILES_DIR, new),
                            os.path.join(LEGACY_FILES_DIR, old))
            except Exception:
                pass
        return
    shutil.rmtree(LEGACY_FILES_DIR, ignore_errors=True)


# --------------------------------------------------------------- 读写
def _empty():
    return {'version': VERSION, 'items': []}


def _normalize_item(raw):
    if not isinstance(raw, dict):
        return None
    name = _clean(raw.get('name'), 80)
    apps = []
    for row in (raw.get('applicants') or []):
        row = list(row or []) + [''] * 4
        row = [_clean(v) for v in row[:4]]
        if any(row):
            apps.append(row)
    invs = []
    for row in (raw.get('inventors') or []):
        row = list(row or []) + [''] * 2
        row = [_clean(v) for v in row[:2]]
        if any(row):
            invs.append(row)
    if not name and not apps and not invs:
        return None
    if not name:
        name = apps[0][0] if apps else (invs[0][0] if invs else '未命名')
    return {'id': str(raw.get('id') or uuid.uuid4().hex[:12]),
            'name': name,
            'note': _clean(raw.get('note'), 120),
            'applicants': apps,
            'inventors': invs,
            'poa': _normalize_poa(raw.get('poa')),
            'created': int(raw.get('created') or _now()),
            'used': int(raw.get('used') or 0),
            'count': int(raw.get('count') or 0)}


def load():
    """读取全部档案，按「最近使用 → 名称」排序。文件坏了返回空表，不抛异常。"""
    _migrate_legacy_once()
    try:
        with open(PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        return []
    items = raw.get('items') if isinstance(raw, dict) else raw
    out = []
    for it in (items or []):
        it = _normalize_item(it)
        if it:
            out.append(it)
    out.sort(key=lambda x: (-(x.get('used') or 0), x.get('name') or ''))
    return out[:MAX_ITEMS]


def save(items):
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {'version': VERSION, 'items': list(items or [])[:MAX_ITEMS]}
    tmp = PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


# --------------------------------------------------------------- 操作
def find(name, items=None):
    """按名称找（忽略空格/全半角括号差异）。"""
    key = _name_key(name)
    if not key:
        return None
    for it in (load() if items is None else items):
        if _name_key(it.get('name')) == key:
            return it
    return None


def _name_key(s):
    s = _clean(s).lower()
    for a, b in (('（', '('), ('）', ')'), ('【', '['), ('】', ']'),
                 ('·', ''), ('-', ''), ('_', ''), (' ', '')):
        s = s.replace(a, b)
    return s


def suggest_name(info):
    """收藏时的默认名称：第一申请人名称（没有就用第一位发明人）。"""
    apps, invs = normalize(info)
    if apps and apps[0][0]:
        return apps[0][0]
    if invs and invs[0][0]:
        return invs[0][0]
    return ''


def make(name, info, note=''):
    apps, invs = normalize(info)
    return {'id': uuid.uuid4().hex[:12],
            'name': _clean(name, 80) or suggest_name(info) or '未命名',
            'note': _clean(note, 120),
            'applicants': apps, 'inventors': invs, 'poa': [],
            'created': _now(), 'used': 0, 'count': 0}


def upsert(name, info, note='', item_id=None, only='all'):
    """新增或按名称覆盖。返回 (item, 是否覆盖)。

    only='apps' / 'invs' 只替换申请人或发明人（「分别收藏」），另一侧与
    委托书附件原样保留；only='all' 才是整套替换。
    """
    items = load()
    item = None
    if item_id:
        item = next((x for x in items if x['id'] == item_id), None)
    if item is None:
        item = find(name, items)
    apps, invs = normalize(info)
    overwritten = item is not None
    if item is None:
        item = make(name, info, note)
        if only == 'apps':
            item['inventors'] = []
        elif only == 'invs':
            item['applicants'] = []
        items.append(item)
    else:
        item['name'] = _clean(name, 80) or item.get('name')
        if only in ('all', 'apps'):
            item['applicants'] = apps
        if only in ('all', 'invs'):
            item['inventors'] = invs
        item.setdefault('poa', [])
        if note != '':
            item['note'] = _clean(note, 120)
    save(items)
    return item, overwritten


def update(item_id, **kw):
    items = load()
    for it in items:
        if it['id'] == item_id:
            if 'name' in kw:
                it['name'] = _clean(kw['name'], 80) or it['name']
            if 'note' in kw:
                it['note'] = _clean(kw['note'], 120)
            if 'applicants' in kw:
                it['applicants'], _ = normalize({'applicants': kw['applicants']})
            if 'inventors' in kw:
                _, it['inventors'] = normalize({'inventors': kw['inventors']})
            save(items)
            return it
    return None


def delete(item_id):
    items = load()
    victim = next((x for x in items if x['id'] == item_id), None)
    left = [x for x in items if x['id'] != item_id]
    if len(left) == len(items):
        return False
    save(left)
    # 委托书文件：没被其它档案引用的一并删掉（都在 data/poa 下）
    in_use = _poa_in_use()
    for e in (victim or {}).get('poa') or []:
        _remove_poa_file(e.get('file'), in_use)
    return True


def touch(item_id):
    """记一次「用过」，让常用档案浮到列表顶部。"""
    items = load()
    for it in items:
        if it['id'] == item_id:
            it['used'] = _now()
            it['count'] = int(it.get('count') or 0) + 1
            save(items)
            return it
    return None


def search(q, items=None):
    items = load() if items is None else items
    q = _clean(q).lower()
    if not q:
        return items
    keys = [k for k in re.split(r'[\s,，、]+', q) if k]
    out = []
    for it in items:
        blob = ' '.join([it.get('name') or '', it.get('note') or ''] +
                        [' '.join(r) for r in it.get('applicants') or []] +
                        [' '.join(r) for r in it.get('inventors') or []] +
                        [str(e.get('name') or '') for e in it.get('poa') or []])
        blob = blob.lower()
        if all(k in blob for k in keys):
            out.append(it)
    return out

# -*- coding: utf-8 -*-
"""火山方舟（Ark）大模型内容校验：配置、请求、结果解析。

数据面 API（OpenAI 兼容）：
    POST {base_url}/chat/completions
    Authorization: Bearer <API Key>
    model: 推理接入点 ID（ep-...）或 Model ID
参考：https://volcengine.com/docs/ark/base-url-and-authentication
     https://volcengine.com/docs/ark/compatible-with-openai-sdk

性能设计（实测同一接入点 / 184 字样例）：
    完整 JSON + 默认深度思考   33.45s / 3283 completion tokens
    紧凑数组 + 关闭深度思考    4.35s /  294 completion tokens
带「深度思考」标签的豆包模型默认启用思维链，校对这类任务并不需要；
通过 thinking.type=disabled 关闭后耗时降到约 1/8。再配合紧凑输出、
并发分批、连接复用和同文本缓存，重复校验可做到秒回。

设计要点：
* 纯逻辑函数（load_config / check_text / test_connection）不碰 UI，便于离线测试；
* 网络请求统一放进 Worker(QThread)，界面用局部 QEventLoop 等待，绝不阻塞主线程；
* 模型只允许返回结构化 JSON 问题列表，且 original 必须逐字出现在原文中，
  过滤掉幻觉片段后才写进问题清单；
* API Key 只保存在本机 data/settings.json，不写入日志、不打印到控制台。
"""
import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
except ImportError:                 # 部署环境没有 requests 时回落到标准库
    requests = None

BASE_URL_DEFAULT = 'https://ark.cn-beijing.volces.com/api/v3'

# 内置默认值只保留与密钥无关的参数；密钥名称 / API Key / 接入点一律
# 不写进源码（便于开源上传），改由以下两个来源提供（前者优先）：
#   1. data/settings.json 的 "ai_check" 字段 —— 「工具 → AI 接口设置」保存；
#   2. data/ai_check.json —— 手工编辑的配置文件，首次部署时填好即可用。
# key_name 是控制台里显示的密钥名称，仅作备注，不参与鉴权。
DEFAULT_CONFIG = {
    'enabled': True,
    'provider': '火山方舟 / Ark',
    'key_name': '',
    'api_key': '',
    'endpoint': '',
    'base_url': BASE_URL_DEFAULT,
    # 关闭深度思考后单次实测 4~10 秒；仍保留 60 秒作为网络异常时的上限。
    'timeout': 60,
    'max_chars': 6000,
    'max_batches': 3,
    'max_tokens': 4000,
    'temperature': 0.1,
    'fast_mode': True,       # 关闭深度思考 + 紧凑输出（默认开启，可关闭以换回模型推理）
    'max_workers': 3,        # 多批文本并发请求数
    'scope': {'typo': True, 'grammar': True, 'wording': True},
}

SCOPE_LABELS = [('typo', '错别字'), ('grammar', '语法 / 标点'),
                ('wording', '表述 / 术语')]
FOCUS_LABELS = [('typo', '错别字'), ('grammar', '语法标点'), ('wording', '表述术语')]
TYPE_LABELS = {'错别字': '错别字', '语法': '语法', '标点': '语法',
               '表述': '表述', '术语': '术语'}

# 提示词版本参与缓存键，改提示词后旧结果自动失效。
PROMPT_VERSION = 'fast-v2'

# 紧凑输出：每项 [类别, 原文片段, 建议改法, 级别]。相比原来的
# {type/original/suggestion/reason/severity} 五字段对象，输出 token 少 60%+。
SYSTEM_PROMPT = (
    '中文文本校对。只输出 JSON 数组，不要解释、不要代码块。'
    '每项 4 个字符串：[类别, 原文片段, 建议改法, 级别]。'
    '类别限：错别字 / 语法 / 标点 / 表述 / 术语；级别限：严重 / 警告 / 提示。'
    '原文片段必须逐字出现在文中且不超过 20 字，尽量只圈出需修改的那几个字。'
    '不确定不报，不改专业术语、附图标记与编号，最多 30 条，无问题输出 []。'
)

# 关闭「快速模式」时退回的详细格式（带理由），兼容旧版解析与旧接入点。
SYSTEM_PROMPT_DEEP = (
    '你是中文专利文本校对助手。只检查用户给出的文本，输出严格的 JSON 数组，'
    '不要输出解释、Markdown 代码块、前言或改写后的全文。'
    '每个问题一个对象，字段：'
    'type（错别字 / 语法 / 标点 / 表述 / 术语 之一）、'
    'original（原文中确实出现的连续问题片段，不超过 30 字）、'
    'suggestion（建议改法，不超过 30 字）、'
    'reason（一句话理由，不超过 40 字）、'
    'severity（严重 / 警告 / 提示 之一）。'
    '规则：original 必须逐字出现在原文中；不确定的不要报；'
    '不要改动专业术语、附图标记和编号；最多 30 条；没有问题时返回 []。'
)


# ---------------- 配置 ----------------

def _store():
    import draft_store as store
    return store


def _manual_file_config():
    """读可选的手工配置文件 data/ai_check.json（不存在时返回 {}）。

    这是给新部署 / 开源用户的入口：复制模板、填上密钥即可，不必启动界面。
    文件里多余的键（如 "_说明"）会被 load_config 忽略。
    """
    try:
        path = os.path.join(_store().DATA_DIR, 'ai_check.json')
        with io.open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_config():
    """读 AI 配置，缺省字段回落到内置默认值。

    来源优先级：data/settings.json 的 "ai_check"（界面保存）>
    data/ai_check.json（手工配置）> 内置默认（不含密钥）。
    """
    cfg = dict(DEFAULT_CONFIG)
    cfg['scope'] = dict(DEFAULT_CONFIG['scope'])
    try:
        saved = _store().ai_config() or {}
    except Exception:
        saved = {}
    if not saved:
        saved = _manual_file_config()
    for key, value in saved.items():
        if key == 'scope' and isinstance(value, dict):
            for s, _ in SCOPE_LABELS:
                if s in value:
                    cfg['scope'][s] = bool(value[s])
        elif key in cfg and key != 'scope':
            cfg[key] = value
    # 数值项防呆：界面/手改配置可能写成字符串
    for key, default in (('timeout', 60), ('max_chars', 6000),
                         ('max_batches', 3), ('max_tokens', 4000),
                         ('max_workers', 3)):
        try:
            cfg[key] = int(cfg[key])
        except (TypeError, ValueError):
            cfg[key] = default
    cfg['max_workers'] = max(1, min(10, cfg['max_workers']))
    try:
        cfg['temperature'] = float(cfg['temperature'])
    except (TypeError, ValueError):
        cfg['temperature'] = 0.1
    for key in ('enabled', 'fast_mode'):
        v = cfg.get(key)
        cfg[key] = (str(v).strip().lower() not in ('0', 'false', 'no', 'off', '')
                    if isinstance(v, str) else bool(v))
    return cfg


def save_config(cfg):
    """把配置写入 data/settings.json（只保留已知字段）。"""
    clean = {k: v for k, v in (cfg or {}).items() if k in DEFAULT_CONFIG}
    _store().set_ai_config(clean)
    clear_cache()
    return clean


def missing_fields(cfg):
    """返回尚未填写的必填项中文名，空列表表示可调用。"""
    miss = []
    if not str(cfg.get('api_key') or '').strip():
        miss.append('API Key')
    if not str(cfg.get('endpoint') or '').strip():
        miss.append('Endpoint ID')
    if not str(cfg.get('base_url') or '').strip():
        miss.append('接口地址')
    return miss


# ---------------- HTTP ----------------

_tls = threading.local()      # 每线程一个 Session：复用 TCP/TLS，避免重复握手
# 某些接入点不认识 thinking 字段；记住它们，避免每次请求都先白跑一次 400。
_THINKING_UNSUPPORTED = set()
_THINKING_LOCK = threading.Lock()


def _post(url, payload, headers, timeout):
    """POST 并返回解析后的响应体；异常统一成 RuntimeError，信息里不含密钥。"""
    if requests is None:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            detail = ''
            try:
                err = json.loads(e.read().decode('utf-8', 'replace'))
                detail = (err.get('error') or {}).get('message') or err.get('message') or ''
            except Exception:
                pass
            raise RuntimeError('HTTP %s %s' % (e.code, detail[:200])) from None
        except urllib.error.URLError as e:
            raise RuntimeError('网络不可达：%s' % (e.reason,)) from None
        except (ValueError, TypeError) as e:
            raise RuntimeError('返回格式异常：%s' % e) from None

    session = getattr(_tls, 'session', None)
    if session is None:
        session = requests.Session()
        _tls.session = session
    try:
        resp = session.post(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as e:
        raise RuntimeError('The read operation timed out') from None
    except requests.exceptions.RequestException as e:
        raise RuntimeError('网络不可达：%s' % e) from None
    if resp.status_code != 200:
        detail = ''
        try:
            err = resp.json()
            detail = (err.get('error') or {}).get('message') or err.get('message') or ''
        except Exception:
            detail = (resp.text or '')[:200]
        raise RuntimeError('HTTP %s %s' % (resp.status_code, detail[:200]))
    try:
        return resp.json()
    except ValueError as e:
        raise RuntimeError('返回格式异常：%s' % e) from None


def _chat(cfg, messages, max_tokens=None, timeout=None, _no_thinking=False):
    """发起一次 chat/completions 请求，返回助手文本。异常信息不含密钥。

    快速模式下带 thinking.type=disabled；若接入点不支持该字段并返回 400，
    自动去掉该字段重发一次，保证换模型/换接入点时仍能工作。
    """
    url = str(cfg.get('base_url') or BASE_URL_DEFAULT).rstrip('/') + '/chat/completions'
    payload = {
        'model': str(cfg.get('endpoint') or '').strip(),
        'messages': messages,
        'temperature': float(cfg.get('temperature', 0.1)),
        'max_tokens': int(max_tokens or cfg.get('max_tokens') or 2000),
    }
    ep = str(cfg.get('endpoint') or '').strip()
    with _THINKING_LOCK:
        unsupported = ep in _THINKING_UNSUPPORTED
    if (cfg.get('fast_mode', True) and not _no_thinking and not unsupported):
        payload['thinking'] = {'type': 'disabled'}
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer %s' % str(cfg.get('api_key') or '').strip(),
    }
    timeout = int(timeout or cfg.get('timeout') or 60)
    try:
        body = _post(url, payload, headers, timeout)
    except RuntimeError as e:
        # 只有「服务端明确说 thinking 不支持」或 400 无详情时才降级；
        # 其它 400（模型名错、参数错等）原样报错，不掩盖真实配置问题。
        low = str(e).lower()
        bad_thinking = ('HTTP 400' in str(e) and 'thinking' in payload
                        and ('thinking' in low or low.strip() == 'http 400'))
        if bad_thinking:
            with _THINKING_LOCK:
                _THINKING_UNSUPPORTED.add(ep)
            return _chat(cfg, messages, max_tokens=max_tokens,
                         timeout=timeout, _no_thinking=True)
        raise
    try:
        return body['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError('返回格式异常：%s' % e) from None


def test_connection(cfg):
    """轻量连通性测试：返回 (ok, 说明文字)。"""
    try:
        miss = missing_fields(cfg)
        if miss:
            return False, '缺少：' + '、'.join(miss)
        t0 = time.time()
        reply = _chat(cfg, [{'role': 'user', 'content': '只回复两个字：正常'}],
                      max_tokens=16, timeout=min(int(cfg.get('timeout') or 60), 60))
        return True, '连接成功（%.1f 秒），模型回复：%s' % (
            time.time() - t0, (reply or '').strip()[:60])
    except Exception as e:
        return False, '连接失败：%s' % e


# ---------------- 文本分批 / 结果解析 ----------------

def _retryable(exc):
    """只对读超时 / 网络抖动 / 服务端限流重试；配置类 4xx 不重试。"""
    s = str(exc)
    return ('timed out' in s.lower() or '网络不可达' in s
            or s.startswith('HTTP 429') or s.startswith('HTTP 5'))


def split_batches(text, max_chars=6000, max_batches=3):
    """按段落聚合成不超过 max_chars 的批次，返回 [文本, ...]。"""
    text = (text or '').replace('\u2029', '\n')
    max_chars = max(500, int(max_chars or 6000))
    max_batches = max(1, min(10, int(max_batches or 3)))
    batches, buf = [], []

    def flush():
        if buf:
            batches.append('\n'.join(buf))
            buf.clear()

    size = 0
    for para in text.split('\n'):
        while len(para) > max_chars:
            flush()
            size = 0
            batches.append(para[:max_chars])
            para = para[max_chars:]
            if len(batches) >= max_batches:
                return batches[:max_batches]
        if size + len(para) + 1 > max_chars:
            flush()
            size = 0
            if len(batches) >= max_batches:
                return batches[:max_batches]
        buf.append(para)
        size += len(para) + 1
    flush()
    return batches[:max_batches]


def _loose_objects(frag):
    """回复被截断 / 夹带解释时，逐个提取其中完整的 {...} 对象。

    模型一次列出 20~30 条问题时，末尾常因 max_tokens 被截断，整体
    json.loads 会失败；但前面已经完整的条目仍然有效，不该整批丢掉。
    """
    decoder = json.JSONDecoder()
    out, pos = [], 0
    while True:
        k = frag.find('{', pos)
        if k < 0:
            return out
        try:
            obj, end = decoder.raw_decode(frag, k)
        except (ValueError, TypeError):
            pos = k + 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        pos = max(end, k + 1)


def _normalise(item):
    """把「详细对象」或「紧凑四元组」统一成问题字典。"""
    if isinstance(item, (list, tuple)):
        # 紧凑格式：[类别, 原文片段, 建议改法, 级别]
        if len(item) < 3:
            return None
        typ = str(item[0] or '表述').strip()
        item = {
            'type': typ,
            'original': item[1],
            'suggestion': item[2],
            'severity': item[3] if len(item) > 3 else '提示',
            'reason': '',
        }
    if not isinstance(item, dict):
        return None
    original = str(item.get('original') or '').strip()
    if not original or len(original) > 40:
        return None
    typ = str(item.get('type') or '表述').strip()
    typ = TYPE_LABELS.get(typ, '表述')
    sev = str(item.get('severity') or '提示').strip()
    if sev not in ('严重', '警告', '提示'):
        sev = '提示'
    suggestion = str(item.get('suggestion') or '').strip()[:40]
    reason = str(item.get('reason') or '').strip()[:80]
    if not reason:
        # 紧凑输出不带理由，给一句简短说明，避免界面显示空洞的占位文字。
        reason = '疑似%s' % typ
    return {
        'type': typ,
        'original': original,
        'suggestion': suggestion,
        'reason': reason,
        'severity': sev,
    }


def parse_findings(raw):
    """把模型回复解析成问题字典列表；容忍 Markdown、前后废话与被截断的 JSON。

    同时支持详细对象数组与紧凑四元组数组，以及被截断后的"对象流"。
    """
    s = (raw or '').strip()
    s = re.sub(r'^\s*```(?:json)?\s*', '', s, flags=re.I)
    s = re.sub(r'\s*```\s*$', '', s)
    i, j = s.find('['), s.rfind(']')
    if i < 0:
        i = s.find('{')          # 没有数组外壳，直接按对象流解析
        frag = s[i:] if i >= 0 else ''
    else:
        frag = s[i:j + 1] if j > i else s[i:]
    if not frag:
        return []
    try:
        data = json.loads(frag)
    except (ValueError, TypeError):
        # 数组被截断时也要保住里面完整的四元组：逐个抽出 [...] 片段。
        data = _loose_objects(frag)
        if not data:
            data = []
            for m in re.finditer(r'\[\s*"[^\[\]]*?\]', frag):
                try:
                    obj = json.loads(m.group(0))
                    if isinstance(obj, list):
                        data.append(obj)
                except (ValueError, TypeError):
                    continue
    if isinstance(data, dict):
        data = data.get('issues') or data.get('results') or data.get('data') or []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        norm = _normalise(item)
        if norm:
            out.append(norm)
    return out


# ---------------- 结果缓存（仅内存，不落盘，保护正文隐私） ----------------

_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 8


def clear_cache():
    """清空校验结果缓存；配置保存、对话框恢复默认时自动调用。"""
    with _CACHE_LOCK:
        _CACHE.clear()


def _cache_key(text, cfg, scope):
    raw = '\x1f'.join([
        PROMPT_VERSION,
        str(cfg.get('endpoint')), str(cfg.get('base_url')),
        str(bool(cfg.get('fast_mode', True))),
        str(cfg.get('max_chars')), str(cfg.get('max_batches')),
        ','.join('%s=%s' % (k, bool(scope.get(k, True))) for k, _ in SCOPE_LABELS),
        text or '',
    ])
    return hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()


def _cache_get(key):
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return ([dict(f) for f in hit[0]], hit[1])
    return None


def _cache_put(key, findings, err):
    with _CACHE_LOCK:
        _CACHE[key] = ([dict(f) for f in findings], err)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


# ---------------- 主流程 ----------------

def _check_one_batch(cfg, batch, focus, idx, total, fast):
    """校验一批，返回 (findings, error)。单批独立一次重试预算。"""
    if fast:
        user = '检查：%s。\n文本：\n%s' % (focus, batch)
        system = SYSTEM_PROMPT
    else:
        user = ('请重点检查：%s。\n'
                '只返回 JSON 数组，不要解释。\n'
                '待校验文本（第 %d/%d 批）：\n<<<\n%s\n>>>'
                % (focus, idx, total, batch))
        system = SYSTEM_PROMPT_DEEP
    messages = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': user}]
    max_tokens = max(3000, int(cfg.get('max_tokens') or 4000))
    for attempt in (0, 1):
        try:
            raw = _chat(cfg, messages, max_tokens=max_tokens)
        except Exception as e:
            if attempt == 0 and _retryable(e):
                time.sleep(0.5)
                continue
            return [], '第%d批：%s' % (idx, e)
        got = parse_findings(raw)
        # 回复里明显写了问题、却一条也解析不出来：多半是输出被截断或
        # 模型没按 JSON 回复。必须记为异常，不能伪装成「没有问题」。
        if not got and raw and ('original' in raw or '错别字' in raw):
            return [], '第%d批：模型回复无法解析（可能被截断或格式不符）' % idx
        return got, None
    return [], '第%d批：请求失败' % idx


def check_text(text, cfg, scope=None):
    """对全文做 AI 内容校验，返回 (findings, error)。

    findings 已按 (type, original, suggestion) 去重、过滤掉原文中不存在的片段。
    error 为 None 表示全部批次成功；部分批次失败时仍返回已完成的结果。
    多批并发执行；相同文本 + 相同配置的成功结果在进程内缓存，重复校验秒回。
    """
    miss = missing_fields(cfg)
    if miss:
        return [], '缺少：' + '、'.join(miss)
    scope = scope if isinstance(scope, dict) else cfg.get('scope') or {}
    fast = bool(cfg.get('fast_mode', True))
    labels = FOCUS_LABELS if fast else [(k, l.replace(' / ', '')) for k, l in SCOPE_LABELS]
    wants = [label for key, label in labels if scope.get(key, True)]
    focus = '、'.join(wants) if wants else '错别字、语法标点、表述'
    batches = split_batches(text, cfg.get('max_chars'), cfg.get('max_batches'))
    if not batches:
        return [], None

    key = _cache_key(text, cfg, scope)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    t0 = time.time()
    n = len(batches)
    workers = min(max(1, int(cfg.get('max_workers') or 3)), n) if fast else 1
    jobs = [(cfg, batch, focus, i, n, fast) for i, batch in enumerate(batches, 1)]
    if workers == 1:
        results = [_check_one_batch(*j) for j in jobs]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_check_one_batch, *j) for j in jobs]
            results = []
            for fut in futures:          # 按批序收集，结果顺序稳定
                try:
                    results.append(fut.result())
                except Exception as e:
                    results.append(([], '请求异常：%s' % e))

    findings, errors = [], []
    for idx, (got, err) in enumerate(results, 1):
        findings.extend(got)
        if err:
            errors.append(err)
    err = '；'.join(errors) if errors else None

    # 只保留原文中确实出现的片段（去空白后比对），抑制模型幻觉
    whole = (text or '').replace('\u2029', '\n')
    compact = re.sub(r'\s+', '', whole)
    seen, cleaned = set(), []
    for f in findings:
        needle = f['original'].replace('\u2029', '\n')
        if needle not in whole and re.sub(r'\s+', '', needle) not in compact:
            continue
        dedup = (f['type'], f['original'], f['suggestion'])
        if dedup in seen:
            continue
        seen.add(dedup)
        cleaned.append(f)
        if len(cleaned) >= 60:
            break
    # 只缓存完整成功且确实花过时间的结果；瞬时 mock 调用不进缓存，
    # 避免单元测试里替换 _chat 后拿到上一次的假结果。
    if err is None and time.time() - t0 >= 1.0:
        _cache_put(key, cleaned, None)
    return cleaned, err


# ---------------- 后台线程 ----------------

try:
    from PyQt5.QtCore import QThread, pyqtSignal

    class Worker(QThread):
        """在后台线程执行任意无参函数，结果以 (状态, 值) 回到主线程。"""
        finished_with = pyqtSignal(object)

        def __init__(self, fn, parent=None):
            super().__init__(parent)
            self.fn = fn

        def run(self):
            try:
                self.finished_with.emit(('ok', self.fn()))
            except Exception as e:
                self.finished_with.emit(('error', '%s: %s' % (type(e).__name__, e)))
except ImportError:      # 纯 CLI 环境（无 PyQt5）仍可 import 本模块的逻辑部分
    Worker = None

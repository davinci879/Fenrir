"""顶部网络搜索：在本地弹出结果面板，点击结果才打开浏览器。

- 后台线程抓取必应 / 百度 / DuckDuckGo 并解析「标题 / 链接 / 摘要」；
- 任一引擎失败时自动回退到其它引擎，提高联网成功率；
- 结果以卡片列表展示，点击卡片才调用系统浏览器打开对应链接；
- 无网络时给出提示，并提供「复制搜索链接」兜底。
"""
import re
import html as _html
from urllib.parse import quote, unquote, urlparse, parse_qs

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QCursor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QWidget as _QWidget, QFrame,
)

# 三个引擎：地址模板 + 解析函数（谷歌走与必应近似的解析兜底）
_ENGINES = {
    'bing':   ('https://www.bing.com/search?q={}&setlang=zh-CN', '必应'),
    'baidu':  ('https://www.baidu.com/s?wd={}', '百度'),
    'google': ('https://www.google.com/search?q={}', '谷歌'),
    'ddg':    ('https://html.duckduckgo.com/html/?q={}', 'DuckDuckGo'),
}

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')


def _strip_tags(s):
    s = re.sub(r'<[^>]+>', ' ', s)
    s = _html.unescape(s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _clean_url(u):
    u = unquote(u)
    # DuckDuckGo 的 /redirect?uddg= 真实地址
    if u.startswith('/redirect'):
        q = parse_qs(urlparse(u).query)
        if 'uddg' in q:
            u = unquote(q['uddg'][0])
    return u


def parse_bing(html):
    out = []
    for m in re.finditer(r'<li class="b_algo".*?</li>', html, re.S):
        block = m.group(0)
        a = re.search(r'<h2>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not a:
            continue
        title = _strip_tags(a.group(2))
        if not title:
            continue
        sn = (re.search(r'<p[^>]*class="[^"]*b_(?:lineclamp|paractl)[^"]*"[^>]*>(.*?)</p>',
                        block, re.S)
             or re.search(r'<p[^>]*>(.*?)</p>', block, re.S))
        snippet = _strip_tags(sn.group(1)) if sn else ''
        out.append({'title': title, 'url': _clean_url(a.group(1)), 'snippet': snippet})
    return out


def parse_baidu(html):
    out = []
    for m in re.finditer(r'<h3 class="t">(.*?)</h3>', html, re.S):
        th = m.group(1)
        a = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', th, re.S)
        if not a:
            continue
        title = _strip_tags(a.group(2))
        if not title:
            continue
        seg = html[m.end(): m.end() + 2500]
        sn = (re.search(r'class="c-abstract[^"]*"[^>]*>(.*?)</div>', seg, re.S)
              or re.search(r'class="content-right[^"]*"[^>]*>(.*?)</span>', seg, re.S)
              or re.search(r'class="[^"]*c-span[^"]*"[^>]*>(.*?)</div>', seg, re.S))
        snippet = _strip_tags(sn.group(1)) if sn else ''
        out.append({'title': title, 'url': _clean_url(a.group(1)), 'snippet': snippet})
    return out


def parse_ddg(html):
    out = []
    for m in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        title = _strip_tags(m.group(2))
        if not title:
            continue
        url = _clean_url(m.group(1))
        seg = html[m.end(): m.end() + 1500]
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', seg, re.S)
        snippet = _strip_tags(sn.group(1)) if sn else ''
        out.append({'title': title, 'url': url, 'snippet': snippet})
    return out


_PARSERS = {'bing': parse_bing, 'baidu': parse_baidu, 'google': parse_bing, 'ddg': parse_ddg}


def fetch_results(query, preferred):
    """抓取并解析搜索结果；优先用 preferred 引擎，失败按序回退。"""
    from urllib.request import Request, urlopen
    order = [preferred] + [e for e in ('bing', 'baidu', 'ddg') if e != preferred]
    last_err = None
    for eng in order:
        try:
            url = _ENGINES[eng][0].format(quote(query, safe=''))
            req = Request(url, headers={
                'User-Agent': _UA,
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml',
            })
            data = urlopen(req, timeout=12).read()
            try:
                txt = data.decode('utf-8')
            except UnicodeError:
                txt = data.decode('gb18030', 'ignore')
            res = _PARSERS[eng](txt)
            if res:
                return res, _ENGINES[eng][1], url
            last_err = RuntimeError('%s 未解析到结果' % _ENGINES[eng][1])
        except Exception as e:          # 网络/超时/编码异常
            last_err = e
    raise RuntimeError(str(last_err) or '网络请求失败')


class SearchWorker(QThread):
    done = pyqtSignal(list, str, str)        # results, engine_label, status
    failed = pyqtSignal(str, str)            # message, engine_url（用于复制兜底）

    def __init__(self, query, preferred):
        super().__init__()
        self.query = query
        self.preferred = preferred

    def run(self):
        try:
            results, label, url = fetch_results(self.query, self.preferred)
            self.done.emit(results, label, url)
        except Exception as e:
            self.failed.emit(str(e), _ENGINES[self.preferred][0].format(quote(self.query, safe='')))


class ResultCard(QFrame):
    """单条搜索结果卡片：整卡可点，打开浏览器。"""
    def __init__(self, item, open_url, parent=None):
        super().__init__(parent)
        self._url = item['url']
        self._open_url = open_url
        self.setObjectName('searchResultCard')
        self.setCursor(QCursor(Qt.PointingHandCursor))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)
        self.title = QLabel(item['title'])
        self.title.setObjectName('srcTitle')
        self.title.setWordWrap(True)
        self.title.setFont(QFont('Microsoft YaHei', 11))
        lay.addWidget(self.title)
        self.url = QLabel(item['url'])
        self.url.setObjectName('srcUrl')
        self.url.setWordWrap(False)
        lay.addWidget(self.url)
        if item.get('snippet'):
            self.snip = QLabel(item['snippet'])
            self.snip.setObjectName('srcSnip')
            self.snip.setWordWrap(True)
            self.snip.setFont(QFont('Microsoft YaHei', 9))
            lay.addWidget(self.snip)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._open_url(self._url)
        super().mousePressEvent(ev)


class SearchResultPanel(QWidget):
    PANEL_QSS = """
    QWidget#SearchResultPanel { background: #1e2730; border: 1px solid #3d4c5c; border-radius: 6px; }
    QLabel#srcTitle { color: #6fb3ff; }
    QLabel#srcUrl { color: #6f7f8e; font-size: 10px; }
    QLabel#srcSnip { color: #b8c4ce; }
    QFrame#searchResultCard { background: #243039; border: 1px solid #2f3d49; border-radius: 5px; }
    QFrame#searchResultCard:hover { background: #2c3a45; border-color: #4a76d6; }
    QPushButton#srcEngine { background: #243039; color: #cdd9e3; border: 1px solid #34414d;
        border-radius: 4px; padding: 3px 10px; }
    QPushButton#srcEngine:checked { background: #2f6fb3; color: #ffffff; border-color: #2f6fb3; }
    QPushButton#srcClose { background: transparent; color: #9fb0c0; border: none; font-size: 14px; }
    QPushButton#srcClose:hover { color: #ff6b6b; }
    QLabel#srcStatus { color: #8a98a6; font-size: 11px; }
    """

    def __init__(self, parent=None, open_url=None):
        super().__init__(parent, Qt.Window if parent is None else (Qt.Window | Qt.WindowStaysOnTopHint))
        self.setObjectName('SearchResultPanel')
        self.setWindowTitle('网络搜索结果 — Fenrir')
        self.resize(460, 380)
        self._open_url = open_url or self._default_open
        self._worker = None
        self._query = ''
        self._build_ui()

    def _default_open(self, url):
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:
            print('Error Code 422', e)

    def _build_ui(self):
        self.setStyleSheet(self.PANEL_QSS)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题栏
        title_bar = QWidget()
        title_bar.setObjectName('srcTitleBar')
        title_bar.setStyleSheet('background:#26323e; border-top-left-radius:6px;'
                                'border-top-right-radius:6px;')
        hb = QHBoxLayout(title_bar)
        hb.setContentsMargins(10, 6, 8, 6)
        self.title_label = QLabel('网络搜索结果')
        self.title_label.setStyleSheet('color:#cdd9e3; font-weight:bold;')
        hb.addWidget(self.title_label)
        hb.addStretch(1)
        self.close_btn = QPushButton('×')
        self.close_btn.setObjectName('srcClose')
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.clicked.connect(self.hide)
        hb.addWidget(self.close_btn)
        root.addWidget(title_bar)

        # 引擎选择 + 状态
        bar = QWidget()
        bb = QHBoxLayout(bar)
        bb.setContentsMargins(10, 6, 10, 6)
        bb.setSpacing(6)
        lbl = QLabel('引擎：')
        lbl.setStyleSheet('color:#9fb0c0;')
        bb.addWidget(lbl)
        self.engine_btns = {}
        for key in ('bing', 'baidu', 'google'):
            b = QPushButton(_ENGINES[key][1])
            b.setObjectName('srcEngine')
            b.setCheckable(True)
            b.setFixedHeight(22)
            b.clicked.connect(lambda _c, k=key: self._on_engine(k))
            self.engine_btns[key] = b
            bb.addWidget(b)
        self.engine_btns['bing'].setChecked(True)
        bb.addStretch(1)
        self.status_label = QLabel('')
        self.status_label.setObjectName('srcStatus')
        bb.addWidget(self.status_label)
        root.addWidget(bar)

        # 结果列表（滚动）
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet('border:none; background:#1e2730;')
        self.list_widget = QWidget()
        self.list_lay = QVBoxLayout(self.list_widget)
        self.list_lay.setContentsMargins(8, 8, 8, 8)
        self.list_lay.setSpacing(6)
        self.list_lay.addStretch(1)
        self.scroll.setWidget(self.list_widget)
        root.addWidget(self.scroll, 1)

    def _on_engine(self, key):
        for k, b in self.engine_btns.items():
            b.setChecked(k == key)
        if self._query:
            self.search(self._query, key)

    def search(self, query, preferred='bing'):
        self._query = query
        self.title_label.setText('网络搜索：%s' % query)
        self._clear_results()
        self.status_label.setText('搜索中…')
        if self._worker and self._worker.isRunning():
            self._worker.quit()
        self._worker = SearchWorker(query, preferred)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _clear_results(self):
        while self.list_lay.count() > 1:
            w = self.list_lay.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _on_done(self, results, label, url):
        self.status_label.setText('找到 %d 条结果（%s）' % (len(results), label))
        self._clear_results()
        if not results:
            self.status_label.setText('（%s）未返回结果，可换引擎重试' % label)
            return
        for item in results[:30]:
            card = ResultCard(item, self._open_url, self.list_widget)
            self.list_lay.insertWidget(self.list_lay.count() - 1, card)

    def _on_failed(self, msg, engine_url):
        self._clear_results()
        self.status_label.setText('搜索失败：%s' % msg)
        tip = QLabel('无法联网。点击下方按钮复制搜索链接，用浏览器手动打开：')
        tip.setStyleSheet('color:#b8c4ce;')
        self.list_lay.insertWidget(self.list_lay.count() - 1, tip)
        btn = QPushButton('复制搜索链接')
        btn.setObjectName('srcEngine')
        btn.setFixedHeight(24)
        btn.clicked.connect(lambda: self._copy_and_open(engine_url))
        self.list_lay.insertWidget(self.list_lay.count() - 1, btn)

    def _copy_and_open(self, url):
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(url)
            self.status_label.setText('搜索链接已复制：%s' % url)
        except Exception as e:
            print('Error Code 423', e)

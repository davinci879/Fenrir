# -*- coding: utf-8 -*-
"""当地实时天气 → 右上角演出规格（类型 + 强度档）。

【已停用 / DISABLED】
    用户已关闭天气同步：main.py 不再 import 本模块、不再装配 LiveWeather，
    右上角演出改为「离子流间隔 + 随机天气」，软件运行期间不会发起任何
    天气/定位网络请求。本文件仅作为 WMO 天气码映射的离线参考保留，
    如日后需要重新开启，再在 MainWindow 里装配 LiveWeather 即可。

设计要点
--------
* 启动 2 分钟后才做首次请求，之后每小时一次；成功结果写 QSettings 缓存。
* 「上次尝试时间」也缓存：调试时反复重启、或网络不通反复重试，都不会
  在一小时内重复打接口 —— 这是用户明确要求的防反爬节流。
* 全程后台线程 + pyqtSignal 回主线程，UI 绝不被网络阻塞；任何异常都
  降级为「无实时天气」，调度器自动回退原来的随机演出表。
* 强度档 level: 0=离子流(无天气) / 1=小 / 2=中 / 3=大 / 4=暴雨·暴雪。
  4 档在渲染层会额外叠加雷暴闪电 / 地面积雪。
"""
import json
import math
import threading
import time
import urllib.request

from PyQt5.QtCore import QObject, QSettings, QTimer, pyqtSignal

# WMO 天气代码（Open-Meteo / 气象部门通用）→ (演出类型, 强度档, 中文名)
WMO_EFFECTS = {
    0: ('ion', 0, '晴'), 1: ('ion', 0, '晴间多云'), 2: ('ion', 0, '多云'),
    3: ('ion', 0, '阴'),
    45: ('fog', 2, '雾'), 48: ('fog', 3, '冻雾'),
    51: ('rain', 1, '小毛毛雨'), 53: ('rain', 1, '毛毛雨'), 55: ('rain', 2, '浓毛毛雨'),
    56: ('rain', 1, '冻毛毛雨'), 57: ('rain', 2, '浓冻毛毛雨'),
    61: ('rain', 1, '小雨'), 63: ('rain', 2, '中雨'), 65: ('rain', 3, '大雨'),
    66: ('hail', 2, '冻雨'), 67: ('hail', 3, '强冻雨'),
    71: ('blizzard', 1, '小雪'), 73: ('blizzard', 2, '中雪'), 75: ('blizzard', 3, '大雪'),
    77: ('blizzard', 1, '米雪'),
    80: ('rain', 1, '阵雨'), 81: ('rain', 2, '强阵雨'), 82: ('rain', 4, '暴雨'),
    85: ('blizzard', 2, '阵雪'), 86: ('blizzard', 4, '暴雪'),
    95: ('storm', 3, '雷阵雨'), 96: ('storm', 4, '雷暴伴冰雹'),
    99: ('storm', 4, '强雷暴伴冰雹'),
}

# wttr.in 备用源的简版编码映射（只在 Open-Meteo 不可达时兜底）
_WTTR_KINDS = {
    '113': 'ion', '116': 'ion', '119': 'ion',
    '122': 'fog', '143': 'fog', '248': 'fog', '260': 'fog',
    '200': 'storm', '386': 'storm', '389': 'storm', '392': 'storm',
    '179': 'blizzard', '227': 'blizzard', '230': 'blizzard', '317': 'hail',
    '320': 'blizzard', '323': 'blizzard', '326': 'blizzard', '329': 'blizzard',
    '332': 'blizzard', '335': 'blizzard', '338': 'blizzard', '350': 'hail',
    '362': 'hail', '365': 'hail', '368': 'blizzard', '371': 'blizzard',
    '374': 'hail', '377': 'hail', '395': 'blizzard', '398': 'blizzard',
}

DEFAULT_LAT, DEFAULT_LON, DEFAULT_CITY = 39.9042, 116.4074, '默认位置'


def _http_json(url, timeout):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Fenrir/3.5 (local weather; contact: github.com/davinci879)',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read(2 * 1024 * 1024).decode('utf-8', 'replace'))


def _locate(timeout):
    """按 IP 定位经纬度；逐个源回退，全失败则用默认坐标，绝不抛异常。"""
    for url, key_lat, key_lon, key_city in (
            ('https://ipapi.co/json/', 'latitude', 'longitude', 'city'),
            ('http://ip-api.com/json/?fields=status,lat,lon,city', 'lat', 'lon', 'city'),
    ):
        try:
            d = _http_json(url, min(timeout, 5.0))
            if d.get('status') == 'fail':
                continue
            lat, lon = float(d[key_lat]), float(d[key_lon])
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                return lat, lon, str(d.get(key_city) or '')
        except Exception:
            continue
    return DEFAULT_LAT, DEFAULT_LON, DEFAULT_CITY


def wmo_to_effect(code, precip=0.0, wind=0.0):
    """天气代码 + 降水量(mm/h) + 风速(km/h) → (kind, level, 描述)。"""
    try:
        code = int(code)
    except Exception:
        code = 0
    kind, level, desc = WMO_EFFECTS.get(code, ('ion', 0, '未知天气'))
    precip = max(0.0, float(precip or 0.0))
    wind = max(0.0, float(wind or 0.0))

    if kind == 'rain':
        # 实测降水量比代码更能区分小/中/大；≥16mm/h 直接算暴雨（叠雷暴）
        if precip >= 16.0:
            level, desc = 4, '暴雨'
        elif precip >= 8.0 and level < 3:
            level, desc = 3, '大雨'
        elif precip >= 4.0 and level < 2:
            level, desc = 2, '中雨'
        elif precip > 0.0 and precip < 1.0 and level > 1:
            level, desc = 1, '小雨'
    elif kind == 'blizzard':
        if precip >= 10.0 or (level >= 3 and wind >= 30.0):
            level, desc = 4, '暴雪'
    elif kind == 'storm':
        level = max(2, min(4, 2 + int(precip >= 10.0) + int(wind >= 40.0)))
    elif kind == 'ion' and wind >= 30.0:
        # 无降水的大风天才触发狂风，避免把雨雪天盖掉
        level = 1 if wind < 40.0 else (2 if wind < 60.0 else 3)
        kind, desc = 'wind', '大风' if level == 1 else ('强风' if level == 2 else '狂风')
    return kind, max(0, min(4, int(level))), desc


def _wttr_to_effect(d):
    cur = (d.get('current_condition') or [{}])[0]
    code = str(cur.get('weatherCode', '113'))
    kind = _WTTR_KINDS.get(code, 'rain')
    desc = ((cur.get('weatherDesc') or [{}])[0].get('value') or '').strip()
    if kind == 'ion':
        level = 0
    elif code in ('395', '398', '338', '335', '332'):
        level = 4
    elif code in ('308', '359', '305', '302', '329', '326', '389', '392', '200'):
        level = 3
    elif code in ('263', '266', '281', '284', '353', '356', '179', '227', '323'):
        level = 1
    else:
        level = 2
    if kind == 'rain' and level >= 3:
        level = 4 if level >= 4 else 3
    return kind, level, desc or kind


def fetch_current(timeout=8.0):
    """后台线程调用：联网取当前天气，返回 dict；失败抛异常由调用方兜底。"""
    lat, lon, city = _locate(timeout)
    url = ('https://api.open-meteo.com/v1/forecast'
           '?latitude=%.4f&longitude=%.4f'
           '&current=weather_code,wind_speed_10m,precipitation&timezone=auto'
           % (lat, lon))
    try:
        d = _http_json(url, timeout)
        cur = d.get('current') or {}
        code = int(cur.get('weather_code', 0))
        wind = float(cur.get('wind_speed_10m', 0) or 0)
        precip = float(cur.get('precipitation', 0) or 0)
        kind, level, desc = wmo_to_effect(code, precip, wind)
    except Exception:
        # 主源不可达：wttr.in 按 IP 定位，一次请求即可拿到天气现象
        d = _http_json('https://wttr.in/?format=j1', timeout)
        kind, level, desc = _wttr_to_effect(d)
        code, wind, precip = -1, 0.0, 0.0
    return {
        'ok': True, 'kind': kind, 'level': level, 'desc': desc,
        'code': code, 'wind': wind, 'precip': precip,
        'city': city, 'lat': lat, 'lon': lon, 'at': time.time(),
    }


class LiveWeather(QObject):
    """每小时更新一次的当地天气；调度器通过 effect() 读当前演出规格。"""

    FIRST_DELAY_MS = 2 * 60 * 1000       # 启动后 2 分钟才首次请求
    PERIOD_MS = 60 * 60 * 1000           # 之后每小时一次
    TIMEOUT = 8.0
    CACHE_KEY = 'LiveWeather/last'
    ATTEMPT_KEY = 'LiveWeather/attempt'
    fetched = pyqtSignal(object)         # 后台线程 → UI 线程

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = None
        self.level = 0
        self.desc = ''
        self.city = ''
        self.code = None
        self.wind = 0.0
        self.precip = 0.0
        self.updated_at = 0.0
        self.revision = 0                 # 每次拿到新天气 +1，供调度器提前下一场
        self.last_error = ''
        self._fetching = False
        self._settings = QSettings('Fenrir', 'FenrirV3.5')
        try:
            self._last_attempt = float(self._settings.value(self.ATTEMPT_KEY, 0.0))
        except Exception:
            self._last_attempt = 0.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        self.fetched.connect(self._on_fetched)
        self._load_cache()
        self.start()

    @property
    def ok(self):
        return self.kind is not None

    def effect(self):
        """→ (kind, level) 或 None（无实时数据：调度器回退随机表）。"""
        return (self.kind, self.level) if self.ok else None

    def start(self):
        self._arm(self.FIRST_DELAY_MS)

    def _arm(self, ms):
        self._timer.setInterval(max(1000, int(ms)))
        self._timer.start()

    def _load_cache(self):
        try:
            raw = self._settings.value(self.CACHE_KEY, '')
            if not raw:
                return
            d = json.loads(raw)
            if time.time() - float(d.get('at', 0)) <= 3 * self.PERIOD_MS / 1000.0:
                self._apply(d)
        except Exception:
            pass

    def _cache_fresh(self):
        return (time.time() - self._last_attempt) < self.PERIOD_MS / 1000.0

    def _on_timer(self):
        # 距上次尝试不足一小时（含刚启动、缓存仍有效、上次失败）：
        # 不发请求，直接把下一次排到满一小时，杜绝调试期反复打接口。
        if self._cache_fresh():
            rest = (self._last_attempt + self.PERIOD_MS / 1000.0
                    - time.time()) * 1000.0
            self._arm(max(1000.0, rest))
            return
        self.refresh()
        self._arm(self.PERIOD_MS)

    def refresh(self, force=False):
        """发起一次后台获取；返回是否真的发起了请求。"""
        if self._fetching:
            return False
        if not force and self._cache_fresh():
            return False
        self._fetching = True
        self._last_attempt = time.time()
        try:
            self._settings.setValue(self.ATTEMPT_KEY, self._last_attempt)
        except Exception:
            pass
        threading.Thread(target=self._work, daemon=True).start()
        return True

    def _work(self):
        try:
            res = fetch_current(self.TIMEOUT)
        except Exception as e:
            res = {'ok': False, 'error': str(e) or type(e).__name__}
        self.fetched.emit(res)

    def _on_fetched(self, res):
        self._fetching = False
        if not isinstance(res, dict) or not res.get('ok'):
            self.last_error = str((res or {}).get('error', '') if isinstance(res, dict)
                                  else 'bad result')
            return                         # 网络失败保留旧天气，否则回退随机表
        self._apply(res)
        self.revision += 1
        # 手工注入 / 缓存恢复的场景下可能没有尝试时间，补上以免立刻重复请求
        if self._last_attempt <= 0:
            self._last_attempt = time.time()
        try:
            self._settings.setValue(self.CACHE_KEY, json.dumps({
                'kind': self.kind, 'level': self.level, 'desc': self.desc,
                'city': self.city, 'code': self.code, 'wind': self.wind,
                'precip': self.precip, 'at': self.updated_at,
            }, ensure_ascii=False))
        except Exception:
            pass

    def _apply(self, d):
        self.kind = d.get('kind') or None
        self.level = int(d.get('level', 0) or 0)
        self.desc = str(d.get('desc', ''))
        self.city = str(d.get('city', ''))
        self.code = d.get('code')
        self.wind = float(d.get('wind', 0) or 0)
        self.precip = float(d.get('precip', 0) or 0)
        self.updated_at = float(d.get('at', time.time()))

    def status_text(self):
        if not self.ok:
            return '实时天气：待获取'
        return '%s %s%s' % (self.city or '当地', self.desc,
                            '（%s）' % self.level_name() if self.level else '')

    def level_name(self):
        return ('', '小', '中', '大', '暴雨·暴雪')[max(0, min(4, self.level))]

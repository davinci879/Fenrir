"""界面音效模块 — 按键音（咔哒声）+ 校验结果的节奏提示。

不是音乐：所有声音都是 20~40ms 的极短脉冲，由「噪声瞬态 + 快速衰减正弦体」
合成，听感接近机械键盘 / 触摸板按键，没有音阶旋律。

四类事件只用**节奏和音高**区分，仍属按键声范畴：
  click  单响          —— 任意按钮按下
  ok     单响（略亮）  —— 校验通过
  warn   双响          —— 有一般问题
  fail   三响（低沉）  —— 有严重问题

技术要点：
- 不依赖任何音频素材文件，波形在内存里合成 16bit 单声道 WAV；
- Windows 用 winsound 在后台线程同步播放，其它平台退化为系统响铃；
- 同一事件 120ms 内去抖，连点按钮不会叠成噪音；
- 开关状态存 data/sound.json；任何异常都静默吞掉，音效绝不影响主流程。
"""
import json
import math
import os
import random
import struct
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF_PATH = os.path.join(BASE_DIR, 'data', 'sound.json')

RATE = 22050           # 提示音不需要 44.1k，省一半计算
DEBOUNCE = 0.12        # 同一事件的最小间隔（秒）
# 总音量（线性增益）：合成后峰值约 -14 dBFS。按键音要「听得见但不打扰」，
# 比系统「叮」轻一档；再大在安静办公室会显得吵，再小会被键盘声盖住。
MASTER = 3.3

# 每条脉冲：(频率 Hz, 起始 ms, 时长 ms, 幅度, 噪声占比)
# 噪声占比越高越「脆」，是按键声的关键；纯正弦会变成「哔」的电子音。
EVENTS = {
    # 通用按钮：一声干脆的短促咔哒
    'click': [(1500.0, 0, 24, 0.15, 0.60)],
    # 校验通过：一声略亮的单响
    'ok': [(1680.0, 0, 30, 0.17, 0.55)],
    # 一般问题：同音高双响（嗒-嗒）
    'warn': [(1020.0, 0, 24, 0.19, 0.55),
             (1020.0, 62, 28, 0.17, 0.55)],
    # 严重问题：低沉三响（嗒-嗒-嗒），靠节奏而非旋律表达紧迫
    'fail': [(660.0, 0, 24, 0.20, 0.55),
             (660.0, 56, 24, 0.20, 0.55),
             (660.0, 112, 34, 0.20, 0.55)],
}

_cache = {}            # event -> wav bytes，合成一次复用
_last_played = {}      # event -> 上次播放时间戳
_state = {'enabled': None}
_lock = threading.Lock()
_rng = random.Random(20261108)   # 固定种子：每次启动的噪声瞬态一致


# ---------------------------------------------------------------- 配置读写
def _load_enabled():
    """读 data/sound.json；文件不存在或损坏都默认开启。"""
    try:
        with open(CONF_PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        return bool(raw.get('enabled', True))
    except Exception:
        return True


def enabled():
    with _lock:
        if _state['enabled'] is None:
            _state['enabled'] = _load_enabled()
        return _state['enabled']


def set_enabled(flag):
    flag = bool(flag)
    with _lock:
        _state['enabled'] = flag
    try:
        os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
        with open(CONF_PATH, 'w', encoding='utf-8') as f:
            json.dump({'enabled': flag}, f)
    except Exception:
        pass
    return flag


def toggle():
    return set_enabled(not enabled())


# ---------------------------------------------------------------- 波形合成
def _soft_clip(x):
    """tanh 式软限幅：叠加后不硬切，避免爆音。"""
    return math.tanh(x * 1.1) * 0.9


def _render(notes, rate=RATE):
    """把脉冲表渲染成 16bit 单声道 WAV 字节流。"""
    total_ms = max(start + dur for start, dur in
                   ((n[1], n[2]) for n in notes))
    n = int(rate * total_ms / 1000.0) + 1
    buf = [0.0] * n
    fade = max(2, int(rate * 0.003))     # 尾部 3ms 淡出，消除截断爆音
    for note in notes:
        freq, start, dur, amp = note[0], note[1], note[2], note[3]
        noise_gain = note[4] if len(note) > 4 else 0.0
        s0 = int(rate * start / 1000.0)
        m = max(2, int(rate * dur / 1000.0))
        attack = max(2, min(int(rate * 0.002), m // 6))
        # 噪声瞬态衰减得比音体快得多，形成「起音脆、余音短」的按键感
        noise_decay = 220.0 / max(1, m)
        for i in range(m):
            idx = s0 + i
            if idx >= n:
                break
            t = i / float(rate)
            body = math.sin(2 * math.pi * freq * t)
            noise = (_rng.random() * 2.0 - 1.0) if noise_gain else 0.0
            if i < attack:
                env = i / float(attack)
            else:
                env = math.exp(-5.5 * (i - attack) / float(max(1, m - attack)))
            tail = m - i
            if tail < fade:
                env *= tail / float(fade)
            buf[idx] += amp * MASTER * env * (
                body * (1.0 - noise_gain)
                + noise * noise_gain * math.exp(-noise_decay * i))
        del s0, m, attack, noise_decay

    frames = bytearray()
    for v in buf:
        s = int(_soft_clip(v) * 32767)
        if s > 32767:
            s = 32767
        elif s < -32768:
            s = -32768
        frames += struct.pack('<h', s)

    data_size = len(frames)
    header = b'RIFF' + struct.pack('<I', 36 + data_size) + b'WAVE'
    header += b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate,
                                    rate * 2, 2, 16)
    header += b'data' + struct.pack('<I', data_size)
    return bytes(header) + bytes(frames)


def wav_bytes(event):
    """取事件的 WAV 数据（懒合成并缓存）。未知事件返回空字节。"""
    if event not in EVENTS:
        return b''
    if event not in _cache:
        try:
            _cache[event] = _render(EVENTS[event])
        except Exception:
            _cache[event] = b''
    return _cache[event]


# ---------------------------------------------------------------- 播放
def _play_bytes(wav):
    """在后台线程里同步播放一段 WAV，播完线程退出。"""
    try:
        if sys.platform == 'win32':
            import winsound
            winsound.PlaySound(wav, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            return
    except Exception:
        pass
    # 非 Windows / winsound 不可用：退化为系统响铃，保证「有反馈」而不是死寂
    try:
        from PyQt5.QtWidgets import QApplication
        QApplication.beep()
    except Exception:
        try:
            sys.stdout.write('\a')
            sys.stdout.flush()
        except Exception:
            pass


def play(event):
    """播放指定事件音效。关闭状态 / 未知事件 / 去抖窗口内直接返回。"""
    if not enabled() or event not in EVENTS:
        return False
    now = time.time()
    if now - _last_played.get(event, 0.0) < DEBOUNCE:
        return False
    _last_played[event] = now
    wav = wav_bytes(event)
    if not wav:
        return False
    try:
        th = threading.Thread(target=_play_bytes, args=(wav,),
                              name='sfx-%s' % event)
        th.daemon = True
        th.start()
    except Exception:
        return False
    return True


# ---------------------------------------------------------------- 全局按键音
# 挂在 QApplication 上的事件过滤器：任何按钮按下都播一声轻咔哒。
# 放在 QApplication 级而不是逐个按钮 connect，是为了让工具栏、菜单、停靠区
# 标题栏、对话框等几百个按钮全部覆盖，且以后新增按钮不用再补一行。
try:
    from PyQt5.QtCore import QEvent, QObject
    from PyQt5.QtWidgets import QAbstractButton
except Exception:      # 无 Qt 环境（纯逻辑测试）时降级为不提供按键音
    QObject = None
    QEvent = QAbstractButton = None


if QObject is not None:
    class ButtonSfxFilter(QObject):
        """按钮按下即发声；返回 False，不拦截任何事件。"""

        def eventFilter(self, obj, ev):
            try:
                if (ev.type() == QEvent.MouseButtonPress
                        and isinstance(obj, QAbstractButton)
                        and obj.isEnabled()):
                    play('click')
            except Exception:
                pass
            return False


def install_button_sfx(app):
    """给 QApplication 装按键音过滤器，返回过滤器对象（需保持引用）。

    重复调用不会装第二次；关闭音效时过滤器仍在，只是 play() 直接返回，
    这样重新开启立即生效，不用重装。
    """
    if QObject is None or app is None:
        return None
    exist = getattr(app, '_fenrir_sfx_filter', None)
    if exist is not None:
        return exist
    try:
        flt = ButtonSfxFilter(app)
        app.installEventFilter(flt)
        app._fenrir_sfx_filter = flt
        return flt
    except Exception:
        return None


def play_for_issues(issues, score=100):
    """按校验结果挑提示音：有严重问题=fail，仅有一般问题=warn，干净=ok。"""
    try:
        serious = sum(1 for x in issues if x[0] == '严重')
    except Exception:
        serious = 0
    if serious:
        return play('fail')
    if issues:
        return play('warn')
    return play('ok')

# -*- coding: utf-8 -*-
"""「AI 接口设置」对话框：火山方舟凭据、模型接入点与校验范围。

入口在功能区「工具 → 服务」组，紧挨「服务信息」。
样式沿用 wf.FenrirDialog（无边框、深色、可拖拽），设置落在
data/settings.json 的 ai_check 字段。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QDialog, QFormLayout, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QSpinBox, QVBoxLayout, QWidget)

import ai_check
import word_features as wf


class AISettingsDialog(wf.FenrirDialog):
    def __init__(self, parent=None):
        super().__init__(
            parent, title='AI 接口设置',
            message='配置火山方舟（Ark）大模型，用于文本校验中的错别字、语法标点与表述检查。',
            detail='密钥仅保存在本机 data/settings.json；校验时正文会分片发送到该接口。'
                   '开启快速模式后单次通常只需数秒。',
            kind='info', width=620)
        self._cfg = ai_check.load_config()
        cfg = self._cfg
        self._worker = None

        form = QWidget()
        fl = QFormLayout(form)
        fl.setContentsMargins(0, 6, 0, 0)
        fl.setSpacing(10)
        fl.setLabelAlignment(Qt.AlignRight)

        self.chk_enabled = QCheckBox('启用 AI 内容校验（每轮文本校验时调用模型）')
        self.chk_enabled.setChecked(bool(cfg['enabled']))
        fl.addRow('', self.chk_enabled)

        # 「密钥名称」只是给这把 Key 起的备注，不参与鉴权，允许直接修改。
        self.ed_key_name = QLineEdit(str(cfg.get('key_name') or ''))
        self.ed_key_name.setPlaceholderText('例如：my-ark-key-001（仅备注，不参与鉴权）')
        fl.addRow('密钥名称', self.ed_key_name)

        key_row = QWidget()
        kr = QHBoxLayout(key_row)
        kr.setContentsMargins(0, 0, 0, 0)
        kr.setSpacing(8)
        self.ed_key = QLineEdit(str(cfg['api_key']))
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.ed_key.setPlaceholderText('ark-...')
        self.chk_show = QCheckBox('显示')
        self.chk_show.toggled.connect(self._toggle_key_echo)
        kr.addWidget(self.ed_key, 1)
        kr.addWidget(self.chk_show)
        fl.addRow('API Key', key_row)

        self.ed_endpoint = QLineEdit(str(cfg['endpoint']))
        self.ed_endpoint.setPlaceholderText('ep-xxxxxxxxxx-xxxxx')
        fl.addRow('Endpoint ID', self.ed_endpoint)

        self.ed_base = QLineEdit(str(cfg['base_url']))
        self.ed_base.setPlaceholderText(ai_check.BASE_URL_DEFAULT)
        fl.addRow('接口地址', self.ed_base)

        # 四个数字框排成 2×2：单行塞四个会把「单批上限」「6000 字」挤到截断。
        nums = QWidget()
        nl = QGridLayout(nums)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setHorizontalSpacing(10)
        nl.setVerticalSpacing(6)
        self.sp_timeout = QSpinBox()
        self.sp_timeout.setRange(5, 180)
        self.sp_timeout.setValue(int(cfg['timeout']))
        self.sp_timeout.setSuffix(' 秒')
        self.sp_timeout.setToolTip(
            '单次请求超时上限。快速模式下通常 4~10 秒即返回；网络异常时才需要调大')
        self.sp_chars = QSpinBox()
        self.sp_chars.setRange(500, 20000)
        self.sp_chars.setSingleStep(500)
        self.sp_chars.setValue(int(cfg['max_chars']))
        self.sp_chars.setSuffix(' 字')
        self.sp_batches = QSpinBox()
        self.sp_batches.setRange(1, 10)
        self.sp_batches.setValue(int(cfg['max_batches']))
        self.sp_batches.setSuffix(' 批')
        self.sp_workers = QSpinBox()
        self.sp_workers.setRange(1, 10)
        self.sp_workers.setValue(int(cfg.get('max_workers') or 3))
        self.sp_workers.setSuffix(' 路')
        self.sp_workers.setToolTip(
            '长文本分成多批时同时发出的请求数；并发把「批数 × 单次耗时」压成约一次耗时')
        for i, (lab, sp) in enumerate((('超时', self.sp_timeout),
                                      ('单批上限', self.sp_chars),
                                      ('最多', self.sp_batches),
                                      ('并发', self.sp_workers))):
            sp.setMinimumWidth(100)      # 留足 suffix（秒 / 字 / 批 / 路）与上下箭头
            r, c = divmod(i, 2)
            nl.addWidget(QLabel(lab), r, c * 2)
            nl.addWidget(sp, r, c * 2 + 1)
        nl.setColumnStretch(4, 1)
        fl.addRow('请求参数', nums)

        scope_row = QWidget()
        sl = QHBoxLayout(scope_row)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(14)
        self.scope_boxes = {}
        for key, label in ai_check.SCOPE_LABELS:
            cb = QCheckBox(label)
            cb.setChecked(bool(cfg['scope'].get(key, True)))
            self.scope_boxes[key] = cb
            sl.addWidget(cb)
        sl.addStretch(1)
        fl.addRow('校验范围', scope_row)

        self.chk_fast = QCheckBox(
            '快速模式：关闭深度思考 + 紧凑输出（实测约 4~10 秒，默认开启）')
        self.chk_fast.setChecked(bool(cfg.get('fast_mode', True)))
        self.chk_fast.setToolTip(
            '关闭后模型会先做完整推理再回答，耗时约 30~60 秒；'
            '仅在需要更高判断质量、且不在意等待时间时关闭')
        fl.addRow('', self.chk_fast)

        self.lbl_status = QLabel('尚未测试连接')
        self.lbl_status.setWordWrap(True)
        fl.addRow('状态', self.lbl_status)

        reset = QPushButton('恢复默认设置')
        reset.setObjectName('DialogButton')
        reset.setFixedWidth(120)
        reset.clicked.connect(self._reset_defaults)
        fl.addRow('', reset)

        self.add_content(form)
        self.set_hint('密钥只存本机，不会写入日志')
        self._test_btn = self.add_button('测试连接', 2)
        # add_button 默认点击即关闭对话框，这里改成原地测试
        self._test_btn.clicked.disconnect()
        self._test_btn.clicked.connect(self._on_test)
        self.add_button('保存', QDialog.Accepted, primary=True)
        self.add_button('取消', QDialog.Rejected)

    # ---------------- 表单 ----------------
    def _toggle_key_echo(self, checked):
        self.ed_key.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _fill(self, cfg):
        self.chk_enabled.setChecked(bool(cfg['enabled']))
        self.ed_key_name.setText(str(cfg.get('key_name') or ''))
        self.ed_key.setText(str(cfg['api_key']))
        self.ed_endpoint.setText(str(cfg['endpoint']))
        self.ed_base.setText(str(cfg['base_url']))
        self.sp_timeout.setValue(int(cfg['timeout']))
        self.sp_chars.setValue(int(cfg['max_chars']))
        self.sp_batches.setValue(int(cfg['max_batches']))
        self.sp_workers.setValue(int(cfg.get('max_workers') or 3))
        self.chk_fast.setChecked(bool(cfg.get('fast_mode', True)))
        for key, cb in self.scope_boxes.items():
            cb.setChecked(bool(cfg['scope'].get(key, True)))

    def _reset_defaults(self):
        self._fill(ai_check.DEFAULT_CONFIG)
        self._set_status('已恢复默认设置，点「保存」后生效', '#8fd0ff')

    def collect(self):
        cfg = dict(self._cfg)
        cfg.update({
            'enabled': self.chk_enabled.isChecked(),
            'key_name': self.ed_key_name.text().strip(),
            'api_key': self.ed_key.text().strip(),
            'endpoint': self.ed_endpoint.text().strip(),
            'base_url': self.ed_base.text().strip(),
            'timeout': self.sp_timeout.value(),
            'max_chars': self.sp_chars.value(),
            'max_batches': self.sp_batches.value(),
            'max_workers': self.sp_workers.value(),
            'fast_mode': self.chk_fast.isChecked(),
            'scope': {k: cb.isChecked() for k, cb in self.scope_boxes.items()},
        })
        return cfg

    # ---------------- 测试连接 ----------------
    def _set_status(self, text, color='#9fb0c0'):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet('color: %s; font-size: 12px;' % color)

    def _on_test(self):
        cfg = self.collect()
        miss = ai_check.missing_fields(cfg)
        if miss:
            self._set_status('请先填写：' + '、'.join(miss), '#f0a05a')
            return
        if ai_check.Worker is None:
            self._set_status('当前环境不支持后台线程', '#f0a05a')
            return
        self._set_status('正在连接火山方舟…', '#8fd0ff')
        self._test_btn.setEnabled(False)
        self._worker = ai_check.Worker(
            lambda: ai_check.test_connection(cfg), self)
        self._worker.finished_with.connect(self._on_test_done)
        self._worker.start()

    def _on_test_done(self, result):
        self._test_btn.setEnabled(True)
        state, value = result
        if state != 'ok':
            self._set_status('连接失败：%s' % value, '#f0a05a')
            return
        ok, text = value
        self._set_status(text, '#8fe0a8' if ok else '#f0a05a')

    # ---------------- 保存 ----------------
    def done(self, code):
        if code == QDialog.Accepted:
            try:
                ai_check.save_config(self.collect())
            except Exception as e:
                self._set_status('保存失败：%s' % e, '#f0a05a')
                return
        w = getattr(self, '_worker', None)
        if w is not None and w.isRunning():
            w.finished_with.disconnect()
            w.wait(2000)
        super().done(code)

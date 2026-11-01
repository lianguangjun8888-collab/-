"""桌面界面：话术和本地 AI 可用，真实千牛接入状态始终如实显示。"""
from dataclasses import replace
import json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QListWidget,QStackedWidget,QTableWidget,QTableWidgetItem,QHeaderView,QLineEdit,QComboBox,
    QPlainTextEdit,QFormLayout,QCheckBox,QFileDialog,QMessageBox,QAbstractItemView)
from .adapters import SimulationAdapter
from .ai import AIClient
from .engine import Coordinator
from .models import Rule, MessageEvent
from .diagnostics import save_report
from .ui_rules import RuleDialog
from .ui_style import STYLE
from .ui_workers import AsyncWorker, diagnostic_process
from uuid import uuid4


def button(text, callback, secondary=False):
    widget = QPushButton(text)
    if secondary:
        widget.setObjectName('secondary')
    widget.clicked.connect(callback)
    return widget


def label(text, name=None):
    widget = QLabel(text); widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.jobs = set()
        self.report = None
        self.setWindowTitle('千牛本地助手 · 自用免费版')
        self.resize(1180,790); self.setMinimumSize(960,660)
        self.setStyleSheet(STYLE)
        root = QWidget(); self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar = QWidget(); sidebar.setFixedWidth(190); sidebar.setStyleSheet('background:#142846;')
        left = QVBoxLayout(sidebar); left.setContentsMargins(8,20,8,16)
        left.addWidget(label('千牛本地助手','brand'))
        self.nav = QListWidget(); self.nav.setObjectName('nav')
        self.nav.addItems(['工作概览','话术规则','话术测试','回复设置','回复历史','千牛检测'])
        left.addWidget(self.nav)
        footer = label('自用免费 · 数据保存在本机\n目标版本：千牛 9.1907n'); footer.setStyleSheet('color:#91a9c8;padding:8px;')
        left.addWidget(footer); outer.addWidget(sidebar)
        self.pages = QStackedWidget(); outer.addWidget(self.pages,1)
        self._overview(); self._rules_page(); self._test_page(); self._ai_page(); self._history_page(); self._diagnostic_page()
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage('已暂停真实收发 · 话术编辑与本地测试可用')
        self.refresh()
        self.retention_timer = QTimer(self)
        self.retention_timer.setInterval(60*60*1000)
        self.retention_timer.timeout.connect(self.refresh_history)
        self.retention_timer.start()

    def _page(self, title, subtitle):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(28,26,28,24); layout.setSpacing(16)
        layout.addWidget(label(title,'title')); layout.addWidget(label(subtitle,'subtitle'))
        self.pages.addWidget(page)
        return layout

    def _overview(self):
        layout = self._page('工作概览','按关键词回复固定话术，也可设置统一回复。无需注册、充值或安装 AI 模型。')
        self.connection = label('千牛连接：未验证','badge'); layout.addWidget(self.connection)
        row = QHBoxLayout()
        self.rule_count = label('0\n话术规则','card'); self.enabled_count = label('0\n启用规则','card')
        self.history_count = label('0\n处理记录','card')
        for card in (self.rule_count,self.enabled_count,self.history_count): row.addWidget(card)
        layout.addLayout(row)
        layout.addWidget(label('真实自动回复尚未开放：需要先在您的 Windows 千牛 9.1907n 上完成连接测试。当前可编辑、测试话术，尚不会向千牛发送消息。','notice'))
        controls = QHBoxLayout()
        self.live_start = button('开启千牛自动回复',lambda:None); self.live_start.setEnabled(False)
        self.live_start.setToolTip('实机收发适配通过验收后才可开启')
        controls.addWidget(self.live_start); controls.addWidget(button('检测千牛环境',lambda:self.nav.setCurrentRow(5),True)); controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(label('已配置店铺（来自话术适用范围；不代表已连接）'))
        self.shop_summary = QLabel(); layout.addWidget(self.shop_summary)
        layout.addStretch()
        layout.addWidget(button('开始编辑话术',lambda:self.nav.setCurrentRow(1)))

    def _rules_page(self):
        layout = self._page('话术规则','支持包含、完全、分组和顺序匹配；优先级数字越小越优先。')
        tools = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText('搜索名称、关键词或回复')
        self.search.textChanged.connect(self.refresh_rules); tools.addWidget(self.search,1)
        self.category_filter = QComboBox(); self.category_filter.addItem('全部分类','')
        self.category_filter.currentIndexChanged.connect(self.refresh_rules); tools.addWidget(self.category_filter)
        self.add_button = button('＋ 新增话术',self.add_rule); tools.addWidget(self.add_button)
        layout.addLayout(tools)
        self.rule_table = QTableWidget(0,9)
        self.rule_table.setHorizontalHeaderLabels(['收藏','名称','分类','适用店铺','类型','关键词','回复内容','优先','状态'])
        self.rule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rule_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rule_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.rule_table.setAlternatingRowColors(True); self.rule_table.verticalHeader().setVisible(False)
        header = self.rule_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5,QHeaderView.Stretch); header.setSectionResizeMode(6,QHeaderView.Stretch)
        self.rule_table.doubleClicked.connect(self.edit_rule)
        layout.addWidget(self.rule_table,1)
        bottom = QHBoxLayout()
        for text, callback in [('编辑',self.edit_rule),('启用 / 禁用',self.toggle_rule),('收藏 / 取消',self.favorite_rule),
                                ('删除',self.delete_rule),('导入 JSON',self.import_rules),('导出 JSON',self.export_rules),('载入示例',self.load_examples)]:
            bottom.addWidget(button(text,callback,True))
        layout.addLayout(bottom)
        self.rules_note = label('双击话术可编辑。导入会合并相同标识的规则；先导出可备份当前话术。','subtitle')
        layout.addWidget(self.rules_note)

    def _test_page(self):
        layout = self._page('话术测试','预览不发送、不改变回复轮播顺序。模拟调试仅记录本地结果。')
        form = QFormLayout()
        self.test_shop = QComboBox(); self.test_shop.setEditable(True); self.test_shop.addItem('模拟店铺')
        form.addRow('测试店铺',self.test_shop)
        self.message = QPlainTextEdit(); self.message.setMaximumHeight(150); self.message.setPlaceholderText('输入买家消息，例如：可不可以发邮政？')
        form.addRow('买家消息',self.message); layout.addLayout(form)
        row = QHBoxLayout(); row.addWidget(button('匹配话术',self.test_rule))
        self.simulate_button = button('模拟处理（不发送千牛）',self.simulate,True); row.addWidget(self.simulate_button); row.addStretch(); layout.addLayout(row)
        self.test_output = QPlainTextEdit(); self.test_output.setReadOnly(True); self.test_output.setPlaceholderText('这里显示命中规则、命中词组和回复预览')
        layout.addWidget(self.test_output,1)
        layout.addWidget(label('语法：# 完整条件或　| 组内或　+ 各组都满足　& 依次出现\n例：不要|别发&中通|圆通 → “不要发中通”命中，“中通不要发”不命中。','subtitle'))

    def _ai_page(self):
        layout = self._page('回复设置','固定话术不需要 AI；本地 AI 为可选功能，默认关闭。')
        layout.addWidget(label('使用固定文字时，无需安装 Ollama、下载模型或填写店铺资料。只需设置关键词和对应回复；所有消息回同一句可开启“最简模式”。','notice'))
        cfg = self.store.settings(); form = QFormLayout()
        self.fallback = QComboBox()
        for text,value in [('未匹配不回复','none'),('未匹配用固定回复','default'),('未匹配用本地 AI','ai')]: self.fallback.addItem(text,value)
        self.fallback.setCurrentIndex(self.fallback.findData(cfg['fallback']))
        self.default_reply = QLineEdit(cfg['default_reply'])
        self.base_url = QLineEdit(cfg['base_url'])
        self.ai_model = QComboBox(); self.ai_model.setEditable(True); self.ai_model.addItem(cfg['model'])
        self.ai_shop = QLineEdit(); self.ai_shop.setPlaceholderText('留空为通用资料；填写店铺名可分别保存')
        self.ai_shop.editingFinished.connect(self.load_shop_info)
        self.shop_info = QPlainTextEdit(cfg['shop_info']); self.shop_info.setMaximumHeight(100)
        self.shop_info.setPlaceholderText('填写已核实的商品、发货、售后信息；资料不足时让 AI 转人工核实。')
        self.simple_mode = QCheckBox('最简模式：所有买家文字使用统一话术'); self.simple_mode.setChecked(cfg['simple_mode'])
        self.simple_reply = QLineEdit(cfg['simple_reply'])
        for title,widget in [('未命中策略',self.fallback),('固定默认回复',self.default_reply),('本机服务地址',self.base_url),
                             ('本地模型',self.ai_model),('资料适用店铺',self.ai_shop),('店铺资料',self.shop_info),('',self.simple_mode),('统一话术',self.simple_reply)]:
            form.addRow(title,widget)
        layout.addLayout(form)
        row = QHBoxLayout(); row.addWidget(button('保存设置',self.save_ai_settings))
        self.model_button = button('检测模型',self.detect_models,True); row.addWidget(self.model_button)
        row.addWidget(button('取消正在进行的任务',self.cancel_jobs,True)); row.addStretch(); layout.addLayout(row)
        self.ai_question = QLineEdit(); self.ai_question.setPlaceholderText('输入问题，点击测试（不会发送到千牛）')
        layout.addWidget(self.ai_question)
        self.ai_test_button = button('测试本地 AI',self.test_ai); layout.addWidget(self.ai_test_button)
        self.ai_output = QPlainTextEdit(); self.ai_output.setReadOnly(True); layout.addWidget(self.ai_output,1)
        self.ai_status = label('建议起步模型：qwen2.5:3b；电脑配置较低时可换更小的模型。','subtitle'); layout.addWidget(self.ai_status)

    def _history_page(self):
        layout = self._page('回复历史','模拟处理会标明来源；默认保存最近 30 天记录。')
        tools = QHBoxLayout(); tools.addWidget(button('刷新',self.refresh_history,True))
        tools.addWidget(button('清空历史',self.clear_history,True)); tools.addStretch()
        self.record_body = QCheckBox('记录消息和回复正文'); self.record_body.setChecked(self.store.settings()['record_body'])
        self.record_body.toggled.connect(lambda value:self.store.set_settings({'record_body':value})); tools.addWidget(self.record_body)
        layout.addLayout(tools)
        self.history_table = QTableWidget(0,6); self.history_table.setHorizontalHeaderLabels(['时间','来源 / 店铺','会话','状态','消息','回复'])
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.history_table.setWordWrap(False)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(5,QHeaderView.Stretch)
        layout.addWidget(self.history_table,1)

    def _diagnostic_page(self):
        layout = self._page('千牛兼容性检测','目标：Windows 千牛 9.1907n。检测只读，不修改客户端，也不会自动发消息。')
        layout.addWidget(label('检测结果用于确定能否可靠适配。发现进程或控件，不等于已验证消息收发。','notice'))
        self.include_names = QCheckBox('在本地报告中包含控件名称（可能含聊天文字；默认不包含）'); layout.addWidget(self.include_names)
        row = QHBoxLayout(); self.diagnose_button = button('运行检测',self.run_diagnostic); row.addWidget(self.diagnose_button)
        self.export_report_button = button('保存检测报告',self.export_report,True); self.export_report_button.setEnabled(False); row.addWidget(self.export_report_button)
        row.addStretch(); layout.addLayout(row)
        self.diagnostic_output = QPlainTextEdit(); self.diagnostic_output.setReadOnly(True); layout.addWidget(self.diagnostic_output,1)
        layout.addWidget(label('本机模型安装：安装 Ollama → 执行 ollama pull qwen2.5:3b → 保持 Ollama 运行 → 回复设置页检测模型（可选）。\n千牛实测需依次确认店铺身份、会话身份、新买家消息、草稿状态和发送确认。','subtitle'))

    def refresh(self):
        self.refresh_rules(); self.refresh_history()
        rules = self.store.rules()
        self.rule_count.setText(f'{len(rules)}\n话术规则')
        self.enabled_count.setText(f'{sum(r.enabled for r in rules)}\n启用规则')
        shops = sorted({r.shop for r in rules if r.shop})
        self.shop_summary.setText('、'.join(shops) if shops else '尚未配置专用店铺；新增话术时可填写适用店铺。')
        selected = self.test_shop.currentText(); self.test_shop.clear(); self.test_shop.addItems(['模拟店铺']+shops)
        self.test_shop.setCurrentText(selected)

    def refresh_rules(self,*args):
        if not hasattr(self,'rule_table'):
            return
        all_rules = self.store.rules(); category = self.category_filter.currentData() or ''
        choices = [''] + sorted({r.category for r in all_rules})
        if [self.category_filter.itemData(i) for i in range(self.category_filter.count())] != choices:
            self.category_filter.blockSignals(True); self.category_filter.clear(); self.category_filter.addItem('全部分类','')
            for c in choices[1:]: self.category_filter.addItem(c,c)
            self.category_filter.setCurrentIndex(max(0,self.category_filter.findData(category)))
            self.category_filter.blockSignals(False)
        query = self.search.text().casefold()
        self.visible_rules = [r for r in all_rules if (not category or r.category==category) and
                              query in ' '.join([r.name,r.expression,*r.replies]).casefold()]
        self.rule_table.setRowCount(len(self.visible_rules))
        for i,r in enumerate(self.visible_rules):
            values = ['★' if r.favorite else '',r.name,r.category,r.shop or '通用',
                      '包含' if r.match_type=='contains' else '完全',r.expression,' / '.join(r.replies),str(r.priority),'启用' if r.enabled else '禁用']
            for j,text in enumerate(values):
                item = QTableWidgetItem(text); item.setToolTip(text); self.rule_table.setItem(i,j,item)

    def _selected(self):
        row = self.rule_table.currentRow()
        return self.visible_rules[row] if 0 <= row < len(self.visible_rules) else None

    def add_rule(self):
        if RuleDialog(self.store,parent=self).exec(): self.refresh()

    def edit_rule(self,*args):
        rule = self._selected()
        if rule and RuleDialog(self.store,rule,parent=self).exec(): self.refresh()

    def toggle_rule(self):
        rule = self._selected()
        if rule: self.store.save_rule(replace(rule,enabled=not rule.enabled)); self.refresh()

    def favorite_rule(self):
        rule = self._selected()
        if rule: self.store.save_rule(replace(rule,favorite=not rule.favorite)); self.refresh()

    def delete_rule(self):
        rule = self._selected()
        if rule and QMessageBox.question(self,'删除话术',f'删除“{rule.name}”？')==QMessageBox.Yes:
            self.store.delete_rule(rule.id); self.refresh()

    def import_rules(self):
        path,_ = QFileDialog.getOpenFileName(self,'导入话术','','JSON (*.json)')
        if path:
            try:
                count = self.store.import_rules(path); self.refresh(); self.rules_note.setText(f'已导入 {count} 条话术。')
            except (ValueError,OSError) as exc: self.rules_note.setText(str(exc))

    def export_rules(self):
        path,_ = QFileDialog.getSaveFileName(self,'导出话术','话术备份.json','JSON (*.json)')
        if path:
            try: self.store.export_rules(path); self.rules_note.setText('已导出话术，不含聊天历史。')
            except OSError: self.rules_note.setText('导出失败，请检查目标目录权限。')

    def load_examples(self):
        existing = {r.id for r in self.store.rules()}
        for r in [Rule(id='example-greeting',name='问候示例',expression='你好#您好#在吗',replies=['您好，在的，请问有什么可以帮您？']),
                  Rule(id='example-post',name='邮政咨询示例',expression='发|可|能+邮政',replies=['您好，我帮您核实可用的快递方式。'],category='物流'),
                  Rule(id='example-no-courier',name='快递备注示例',expression='不要|别发&中通|圆通',replies=['已看到您的快递需求，稍后由人工核实。'],category='物流',priority=80)]:
            if r.id not in existing: self.store.save_rule(r)
        self.refresh()

    def test_rule(self):
        outcome = Coordinator(self.store,SimulationAdapter()).preview(self.test_shop.currentText(),self.message.toPlainText())
        state = {'no_match':'未命中，按设置不回复','ai_needed':'未命中，将使用本地 AI（本次仅预览，未调用）'}.get(outcome.status,'已命中')
        self.test_output.setPlainText(f'{state}\n规则：{outcome.name or "无"}\n归一化消息：{outcome.normalized}\n命中词组：{"、".join(outcome.groups)}\n\n回复预览：\n{outcome.reply or "无"}')

    def _launch(self, work, success, error, control=None):
        worker = AsyncWorker(work,self); self.jobs.add(worker)
        if control: control.setEnabled(False)
        worker.success.connect(success); worker.failed.connect(error)
        def done():
            self.jobs.discard(worker)
            if control: control.setEnabled(True)
            worker.deleteLater()
        worker.finished.connect(done); worker.start()

    def simulate(self):
        shop = self.test_shop.currentText().strip() or '模拟店铺'; text = self.message.toPlainText()
        # The simulation database is isolated from actual shop rotation state.
        async def run_simulation():
            from .store import Store
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                simulation = Store(Path(directory)/'simulation.db')
                for r in self.store.rules(): simulation.save_rule(r)
                simulation.set_settings(self.store.settings())
                engine = Coordinator(simulation,SimulationAdapter()); engine.set_enabled(True); engine.enable_shop(shop,True)
                result = await engine.handle(MessageEvent(shop,'模拟买家',uuid4().hex,text))
                self.store.record('[模拟] '+shop,'模拟买家',uuid4().hex,text,result.reply,'模拟：'+result.status,result.rule_id)
                return result
        def done(result):
            self.test_output.setPlainText(f'【模拟调试，不发送千牛】\n状态：{result.status}\n回复：{result.reply}')
            self.refresh_history()
        self._launch(run_simulation,done,lambda msg:self.test_output.setPlainText(msg),self.simulate_button)

    def _ai_config(self):
        cfg = self.store.settings()
        shop = self.ai_shop.text().strip()
        infos = cfg['shop_infos'].copy()
        if shop: infos[shop] = self.shop_info.toPlainText()
        return dict(fallback=self.fallback.currentData(),default_reply=self.default_reply.text(),
                    base_url=self.base_url.text().strip(),model=self.ai_model.currentText().strip(),
                    shop_info=cfg['shop_info'] if shop else self.shop_info.toPlainText(),shop_infos=infos,
                    simple_mode=self.simple_mode.isChecked(),simple_reply=self.simple_reply.text())

    def load_shop_info(self):
        cfg = self.store.settings(); shop = self.ai_shop.text().strip()
        self.shop_info.setPlainText(cfg['shop_infos'].get(shop,'') if shop else cfg['shop_info'])

    def save_ai_settings(self):
        try:
            self.store.set_settings(self._ai_config()); self.ai_status.setText('设置已保存；真实收发仍保持关闭。')
        except ValueError as exc: self.ai_status.setText(str(exc))

    def _client(self):
        cfg = self._ai_config()
        return AIClient(model=cfg['model'],base_url=cfg['base_url'],shop_info=self.shop_info.toPlainText())

    def detect_models(self):
        try: client = self._client()
        except ValueError as exc: self.ai_status.setText(str(exc)); return
        def done(models):
            current = self.ai_model.currentText(); self.ai_model.clear(); self.ai_model.addItems(models)
            if current in models or not models: self.ai_model.setCurrentText(current or 'qwen2.5:3b')
            self.ai_status.setText(f'检测到 {len(models)} 个本地模型。' if models else '服务已连接，但没有本地模型。请先执行 ollama pull qwen2.5:3b。')
        self._launch(client.models,done,self.ai_status.setText,self.model_button)

    def test_ai(self):
        try:
            client = self._client(); question = self.ai_question.text().strip()
            if not question: raise ValueError('请输入测试问题')
        except ValueError as exc: self.ai_status.setText(str(exc)); return
        self.ai_output.setPlainText('本地模型生成中……首次加载可能较慢。')
        self._launch(lambda:client.reply(question),self.ai_output.setPlainText,self.ai_output.setPlainText,self.ai_test_button)

    def refresh_history(self):
        rows = self.store.history(); self.history_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,key in enumerate(['created','shop','conversation','status','message','reply']):
                text = r[key]; item = QTableWidgetItem(text); item.setToolTip(text); self.history_table.setItem(i,j,item)
        self.history_count.setText(f'{len(rows)}\n最近处理记录')

    def clear_history(self):
        if QMessageBox.question(self,'清空历史','清空显示历史？事件去重记录仍保留，避免重复回复。')==QMessageBox.Yes:
            self.store.clear_history(); self.refresh_history()

    def run_diagnostic(self):
        include_names = self.include_names.isChecked()
        self.diagnostic_output.setPlainText('正在只读检测，最多等待 30 秒……')
        def done(report):
            self.report = report; self.diagnostic_output.setPlainText(json.dumps(report,ensure_ascii=False,indent=2))
            self.export_report_button.setEnabled(True); self.connection.setText('千牛连接：未验证（已生成检测报告）')
        self._launch(lambda:diagnostic_process(include_names),done,self.diagnostic_output.setPlainText,self.diagnose_button)

    def export_report(self):
        if not self.report: return
        path,_ = QFileDialog.getSaveFileName(self,'保存检测报告','千牛检测.json','JSON (*.json)')
        if path:
            try: save_report(path,self.report); self.statusBar().showMessage('检测报告已保存在本地。')
            except OSError: self.statusBar().showMessage('保存失败，请检查目录权限。')

    def cancel_jobs(self):
        for job in self.jobs: job.cancel()

    def closeEvent(self, event):
        self.cancel_jobs()
        if any(not job.wait(3000) for job in list(self.jobs)):
            self.statusBar().showMessage('正在取消任务，请稍后再次关闭。'); event.ignore(); return
        event.accept()

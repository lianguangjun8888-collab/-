from dataclasses import replace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QFormLayout,QLineEdit,QPlainTextEdit,QComboBox,
    QSpinBox,QCheckBox,QDialogButtonBox,QLabel,QVBoxLayout,QHBoxLayout,QListWidget,
    QListWidgetItem,QWidget,QPushButton)
from .models import Rule


class RuleDialog(QDialog):
    def __init__(self, store, rule=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.rule = rule or Rule(name='',expression='')
        self.setWindowTitle('编辑话术' if rule else '新增话术')
        self.resize(680,650)
        layout = QVBoxLayout(self); form = QFormLayout(); layout.addLayout(form)
        self.name = QLineEdit(self.rule.name)
        self.shop = QLineEdit(self.rule.shop); self.shop.setPlaceholderText('留空表示所有店铺通用')
        self.category = QComboBox(); self.category.setEditable(True)
        self.category.addItems(sorted({r.category for r in store.rules()} | {'通用'}))
        self.category.setCurrentText(self.rule.category)
        self.match_type = QComboBox(); self.match_type.addItem('包含匹配','contains'); self.match_type.addItem('完全匹配','exact')
        self.match_type.setCurrentIndex(self.match_type.findData(self.rule.match_type))
        self.expression = QLineEdit(self.rule.expression)
        self.expression.setPlaceholderText('例如：发|可|能+邮政，或 你好#您好')
        reply_widget = QWidget(); reply_layout = QHBoxLayout(reply_widget); reply_layout.setContentsMargins(0,0,0,0)
        list_layout = QVBoxLayout(); self.reply_list = QListWidget(); self.reply_list.setFixedWidth(150)
        self.reply_list.setMaximumHeight(145); list_layout.addWidget(self.reply_list)
        controls = QHBoxLayout(); self.add_reply_button = QPushButton('添加'); self.remove_reply_button = QPushButton('删除')
        self.add_reply_button.clicked.connect(self.add_reply); self.remove_reply_button.clicked.connect(self.remove_reply)
        controls.addWidget(self.add_reply_button); controls.addWidget(self.remove_reply_button); list_layout.addLayout(controls)
        reply_layout.addLayout(list_layout)
        self.replies = QPlainTextEdit(); self.replies.setMaximumHeight(190)
        self.replies.setPlaceholderText('编辑选中的一条完整回复，支持换行和正文中的 #。多条回复用左侧“添加”。')
        self.replies.textChanged.connect(self.update_reply)
        self.reply_list.currentRowChanged.connect(self.select_reply)
        reply_layout.addWidget(self.replies,1)
        for content in self.rule.replies:
            self._append_reply(content)
        self.reply_list.setCurrentRow(0)
        self.priority = QSpinBox(); self.priority.setRange(0,9999); self.priority.setValue(self.rule.priority)
        self.enabled = QCheckBox('启用此规则'); self.enabled.setChecked(self.rule.enabled)
        self.favorite = QCheckBox('收藏'); self.favorite.setChecked(self.rule.favorite)
        for title, widget in [('名称',self.name),('适用店铺',self.shop),('分类',self.category),('匹配方式',self.match_type),
                              ('关键词',self.expression),('回复列表（依次轮播）',reply_widget),('优先级（越小越优先）',self.priority),('',self.enabled),('',self.favorite)]:
            form.addRow(title,widget)
        help_text = QLabel('# 完整条件或　| 组内或　+ 各组都满足　& 按顺序出现\n完全匹配仅支持 #；关键词不支持减号或括号。')
        help_text.setWordWrap(True); layout.addWidget(help_text)
        self.error = QLabel(); self.error.setObjectName('error'); self.error.setWordWrap(True); layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.Save); self.save_button.setText('保存话术')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def _append_reply(self, content):
        item = QListWidgetItem(content.replace('\n',' / ')[:18] or '（待填写）')
        item.setData(Qt.UserRole,content); self.reply_list.addItem(item)

    def select_reply(self, row):
        item = self.reply_list.item(row)
        self.replies.blockSignals(True)
        self.replies.setPlainText(item.data(Qt.UserRole) if item else '')
        self.replies.blockSignals(False)

    def update_reply(self):
        item = self.reply_list.currentItem()
        if item:
            content = self.replies.toPlainText()
            item.setData(Qt.UserRole,content)
            item.setText(content.replace('\n',' / ')[:18] or '（待填写）')

    def add_reply(self):
        self._append_reply('')
        self.reply_list.setCurrentRow(self.reply_list.count()-1)
        self.replies.setFocus()

    def remove_reply(self):
        row = self.reply_list.currentRow()
        if row >= 0:
            self.reply_list.takeItem(row)
        if self.reply_list.count()==0:
            self._append_reply('')
        self.reply_list.setCurrentRow(max(0,min(row,self.reply_list.count()-1)))

    def save(self):
        try:
            self.store.save_rule(replace(self.rule,name=self.name.text().strip(),shop=self.shop.text().strip(),
                 category=self.category.currentText().strip() or '通用',expression=self.expression.text().strip(),
                 match_type=self.match_type.currentData(),replies=[self.reply_list.item(i).data(Qt.UserRole) for i in range(self.reply_list.count())],
                 priority=self.priority.value(),enabled=self.enabled.isChecked(),favorite=self.favorite.isChecked()))
        except ValueError as exc:
            self.error.setText(str(exc)); return
        self.accept()

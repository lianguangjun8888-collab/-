from dataclasses import replace
from PySide6.QtWidgets import (QDialog,QFormLayout,QLineEdit,QPlainTextEdit,QComboBox,
                               QSpinBox,QCheckBox,QDialogButtonBox,QLabel,QVBoxLayout)
from .models import Rule


class RuleDialog(QDialog):
    def __init__(self, store, rule=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.rule = rule or Rule(name='',expression='')
        self.setWindowTitle('编辑话术' if rule else '新增话术')
        self.resize(620,620)
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
        self.replies = QPlainTextEdit('\n'.join(self.rule.replies))
        self.replies.setPlaceholderText('每行一条回复；多条回复按顺序轮播；正文可保留 #')
        self.priority = QSpinBox(); self.priority.setRange(0,9999); self.priority.setValue(self.rule.priority)
        self.enabled = QCheckBox('启用此规则'); self.enabled.setChecked(self.rule.enabled)
        self.favorite = QCheckBox('收藏'); self.favorite.setChecked(self.rule.favorite)
        for label, widget in [('名称',self.name),('适用店铺',self.shop),('分类',self.category),('匹配方式',self.match_type),
                              ('关键词',self.expression),('回复（每行一条）',self.replies),('优先级（小数优先）',self.priority),('',self.enabled),('',self.favorite)]:
            form.addRow(label,widget)
        help_text = QLabel('# 完整条件或　| 组内或　+ 各组都满足　& 按顺序出现\n完全匹配仅支持 #；关键词不支持减号或括号。')
        help_text.setWordWrap(True); layout.addWidget(help_text)
        self.error = QLabel(); self.error.setObjectName('error'); self.error.setWordWrap(True); layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.Save); self.save_button.setText('保存话术')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def save(self):
        try:
            self.store.save_rule(replace(self.rule,name=self.name.text().strip(),shop=self.shop.text().strip(),
                 category=self.category.currentText().strip() or '通用',expression=self.expression.text().strip(),
                 match_type=self.match_type.currentData(),replies=[x.strip() for x in self.replies.toPlainText().splitlines() if x.strip()],
                 priority=self.priority.value(),enabled=self.enabled.isChecked(),favorite=self.favorite.isChecked()))
        except ValueError as exc:
            self.error.setText(str(exc)); return
        self.accept()

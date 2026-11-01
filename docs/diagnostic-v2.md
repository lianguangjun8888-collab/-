# 增强检测 v2

用户提供的首份报告在 Windows 10 / Python 3.12.10 中找到 AliWorkbench.exe，但三个 UIA 根节点都只有 Qt5152 窗口外框。不能据此建立买家消息、会话或输入框的映射。用户随后提供“关于千牛”截图，确认版本为 **9.19.07N（1686）**。版本资源中的构建标识不能替代这项确认。

## 使用方法

1. 重新下载 GitHub `qianniu-fixed-reply` 分支最新 ZIP，解压到新文件夹；不要继续双击旧文件夹中的检测脚本。
2. 启动千牛并打开“客服接待”，选择一个买家会话，保持窗口可见，关闭“关于”等遮挡窗口。
3. 双击根目录 `检测千牛.bat`，按提示开始。不需要输入或发送消息。
4. 上传新生成的 `reports/qianniu-diagnostic.json`；文件开头应有 `"report_version": 2`。

仍只收集结构；默认不读取控件名称、Value/Text 内容或聊天正文，也不自动上传报告。

## 本次增加的观察

- 原生子窗口、可见/最小化状态、结构限额和扫描是否不完整。
- 检测进程与目标进程的提升权限状态、Python 位数及固定数字版本资源。
- 标准 WM_GETOBJECT/UIA provider 请求之后，通过 RawViewWalker 遍历原始结构。
- 控件类型、框架标识、支持哪些辅助功能模式；不调用输入/点击/发送方法。
- 区分“接口报错”“仅外框”“发现原生子窗口”“发现 UIA 后代”，均不表示真实收发已验收。
- 25 秒独立子进程限时、原子进度文件；接口卡住时只终止检测子进程，并保留部分报告，不结束千牛。

Qt 5.15.2 的标准 UIA 后端在 `handleWmGetObject` 内激活辅助功能；旧 pywinauto 的 `children()` 内部会将部分 COM 错误转为空列表。此次使用显式原始遍历和错误记录，不能承诺一定会取得千牛聊天内容。

参考：
- https://github.com/qt/qtbase/blob/v5.15.2/src/plugins/platforms/windows/uiautomation/qwindowsuiaaccessibility.cpp
- https://github.com/pywinauto/pywinauto/blob/0.6.9/pywinauto/uia_element_info.py

Linux 上验证了结构遍历、隐私边界、错误分类、限额、子进程超时及进度保留。具体 Windows API 和当前千牛上的结果需由本次实机报告确认，尚不宣称真实自动回复可用。

## 安卓引擎工具箱 WinUI 版（Alpha 预览）

基于 C# / WinUI 3 对原 Python tkinter 工具箱的全量重写，本 Release 提供 x64 自包含安装包。

### 安装
- 下载 `YYBToolbox_Setup_1.3.4.0.exe`，按向导安装即可；应用已自包含 Windows App SDK 运行时，无需单独安装 WinApp Runtime。
- 运行时仍需可用的 `adb.exe`（自动探测 PATH / 常见 platform-tools 路径，也可在「系统设置」里手动指定）。

### 已包含功能
- 首页设备信息（型号、Android/SDK、ABI、分辨率/DPI、存储、内存、电池、运行时间、SELinux、Root/Magisk、序列号）
- 应用管理：第三方 / 系统 / 全部列表、按包名过滤；启动、停止、清除数据、禁用 / 启用、卸载、导出 APK、安装 APK
- 文件浏览：目录 / 文件 / 链接识别、Root 浏览、上级 / 前往 / 刷新、拉取、推送、删除
- 终端命令执行、日志抓取（级别 / Tag 过滤）、截图预览与保存
- 诊断、MicroG 环境检测、Root / Magisk 状态检测

### 已知未移植（待办）
- MicroG 一键安装、Magisk 模块管理、录屏、应用权限弹窗管理、部分系统设置项、检查更新对接

> 状态：Alpha 预览，仍在随实测反馈修补。源码见 `win-ui` 分支的 `winui/` 目录。

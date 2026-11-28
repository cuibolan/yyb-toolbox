# 安卓引擎工具箱 · WinUI 3（全 C# 重写版）

这是原「安卓引擎工具箱（YYB Toolbox）」的 **C# / WinUI 3 全量重写版本**，源码位于仓库
`win-ui` 分支的 `winui/` 子目录下；原 Python 实现保留在 `main` 分支及本地 `..\应用宝工具箱\`
目录，互不覆盖。

## 技术栈

- C# / WinUI 3（Windows App SDK 2.7.0），深色中文界面，unpackaged（解包）桌面应用。
- 后端不依赖第三方 NuGet：除 WinAppSDK 外只用 .NET 标准库，通过 `Process` 调用外部 `adb.exe`。
- 自包含（self-contained）发布：Windows App SDK 运行时二进制随输出目录带走，不依赖本机安装的
  Windows App Runtime MSIX 框架包 / DDLM（本机 DDLM 未注册，框架依赖方式会报 `0x80670016`）。
- 目标框架 `net9.0-windows10.0.19041.0`，x64。

## 目录结构

```
应用宝工具箱-WinUI/
├─ README.md                     # 本说明
├─ .gitignore
├─ installer/
│  ├─ YYBToolbox.iss             # Inno Setup 安装包脚本
│  └─ dist/                      # 编译产物：YYBToolbox_Setup_1.3.4.0.exe
└─ src/YYBToolbox.WinUI/
   ├─ YYBToolbox.WinUI.csproj   # 工程文件（自包含、unpackaged、x64）
   ├─ app.manifest
   ├─ App.xaml / App.xaml.cs     # 应用入口、全局异常捕获
   ├─ MainWindow.xaml / .cs      # 导航骨架：顶栏 + 左侧导航 + 内容 Frame + 状态栏
   ├─ Models/Models.cs           # AppInfo / FileEntry / DeviceInfo
   ├─ Services/                  # 后端服务层
   │  ├─ AdbClient.cs           # adb 调用、设备、应用、文件、截图、日志
   │  ├─ DeviceInfoCollector.cs# 设备信息采集（getprop / 存储 / 内存 / 电池 / Root 等）
   │  ├─ ConfigService.cs       # 配置读写（adb 路径、serial 等）
   │  ├─ AppState.cs            # 全局单例状态、连接流程与诊断日志（startup.log）
   │  ├─ AdbError.cs
   │  └─ DialogHelper.cs
   └─ Pages/                     # 10 个导航页面
      ├─ HomePage.xaml           # 设备信息面板
      ├─ AppsPage.xaml           # 应用管理
      ├─ FilesPage.xaml          # 文件浏览
      ├─ ShellPage.xaml          # 终端
      ├─ LogcatPage.xaml         # 日志抓取
      ├─ ShotPage.xaml           # 截图 / 保存
      ├─ SettingsPage.xaml       # 连接与配置
      ├─ DiagPage.xaml           # 诊断
      ├─ MicrogPage.xaml         # MicroG 环境检测
      └─ RootPage.xaml           # Root / Magisk 状态检测
```

## 环境要求

- Windows 10 1809（build 17763）及以上，x64；本机为 Windows 10 22H2（19045）。
- 开发机需安装 .NET 9 SDK。
- 运行发布产物时不需要再装 Windows App Runtime（已自包含）；操作安卓引擎时仍需可用的 `adb.exe`
  （自动探测 PATH / 常见 platform-tools 路径，也可在「系统设置」里手动指定）。

## 构建与发布

在 `src\YYBToolbox.WinUI\` 目录下：

```powershell
# 自检构建（调试）
dotnet build -c Debug

# 自包含发布（产物在 bin\Release\net9.0-windows10.0.19041.0\win-x64\publish\）
dotnet publish -c Release -r win-x64
```

发布目录里的 `YYBToolbox.WinUI.exe` 即主程序。自包含会带上整套 WinAppSDK 运行时和多语言卫星
程序集，目录体积较大；如需瘦身可裁剪不用的语言目录。

### 打包成安装包（Inno Setup）

需要本机安装 Inno Setup 7（免费，编译器 `ISCC.exe`，不进入应用 NuGet 依赖）。先按上面自包含发布，
再在 `installer\` 目录下编译：

```powershell
# 1. 先发布 Release 自包含产物
dotnet publish -c Release -r win-x64

# 2. 编译安装包（installer\YYBToolbox.iss）
& "D:\Program Files\Inno Setup 7\ISCC.exe" installer\YYBToolbox.iss
```

产物：`installer\dist\YYBToolbox_Setup_1.3.4.0.exe`（x64，LZMA2 压缩）。安装包可选安装目录、
创建开始菜单 / 桌面快捷方式、带卸载入口；打包时排除运行期生成的 `config.json`、日志、截图、
缓存和随包下载的 adb 工具目录。

## 当前已移植的功能

- **首页**：型号 / 品牌、Android / SDK、ABI、分辨率 / DPI、存储、内存、电池、运行时间、
  SELinux、Root / Magisk、序列号，可手动刷新。
- **应用管理**：第三方 / 系统 / 全部列表、按包名过滤；启动（先 `resolve-activity` 解析启动组件，`am start -n` 优先，monkey 兜底拉起）、停止、清除数据、禁用 / 启用、
  卸载、导出 APK、安装 APK。
- **文件**：远程目录浏览（含目录 / 文件 / 链接识别，支持 Root 浏览）、上级目录、前往、拉取选中文件到本地、
  推送本地文件到当前目录、删除选中项。
- **终端**：输入 adb shell 命令并回显结果。
- **日志**：按级别（V/D/I/W/E）与 Tag 过滤；有界缓冲（保留最近 1500 行）定时批量刷新，开始 / 停止抓取、清空；
  再次启动前自动清理上一轮残留的 logcat 进程，避免孤儿进程同时刷屏。
- **截图**：截取当前屏幕、预览、保存为 PNG。
- **系统设置**：adb.exe 路径、设备序列号（serial），保存后重建连接；可恢复默认。
- **诊断**：adb 探测、设备列表、当前状态、SELinux、Root 检测。
- **MicroG**：检测已安装的 GmsCore / GsfProxy / FakeGApps 等相关包。
- **Root**：su 检测、`su -c id`、Magisk 应用检测。

## MicroG 说明

MicroG **只提供谷歌服务框架**（GmsCore / GsfProxy / FakeGApps 等），本身不提供应用商店。
若要下载应用，请安装 **Aurora Store** 等第三方开源商店。

## 已知限制

- 日志框基于普通只读文本框渲染，V / D 级高频刷屏时整框重建仍有一定 CPU / 内存开销；目前已用有界队列（最近 1500 行）+ 定时批量刷新把内存压住、不再无限增长。长时间高刷屏下可把级别切到 I / W / E 减少输出；后续可换成支持虚拟化的列表控件进一步优化。

## 尚未移植（待办）

以下原 Python 工具箱中的复杂流程暂未在 C# 侧实现，对应页面先提供状态检测与说明：

1. MicroG 一键安装：Release 解析、选 asset、下载、签名冲突备份卸载、授权、电池白名单、
   FakeGApps 检测。
2. Magisk 模块管理：模块列表、启停、删除、zip 内 `manager.apk` 提取安装、刷入模块 zip。
3. 录屏、应用权限弹窗管理、系统设置项（分辨率 / 动画 / 唤醒 / 输入等）、检查更新对接。

## 与原工程的关系

| 项 | 原 Python 工程 | 本 WinUI 版本 |
| --- | --- | --- |
| 位置 | `..\应用宝工具箱\` | `应用宝工具箱-WinUI\` |
| 技术 | Python 标准库 + tkinter + adb | C# / WinUI 3 + adb |
| 仓库 | 已发布到 GitHub `cuibolan/yyb-toolbox` | 位于 `win-ui` 分支 `winui/` 子目录 |
| 构建 | PyInstaller 打包 exe | `dotnet publish` 自包含发布 |

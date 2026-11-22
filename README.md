# 应用宝引擎工具箱（YYB Toolbox）

仿「WSA 工具箱」的 Windows 桌面工具，用来调试**腾讯应用宝电脑版**内置的 Android 引擎
（Androws / AOSP on Intel Platform，ADB 端口 `127.0.0.1:5555`）。

纯 Python 标准库实现（tkinter + adb），不需要安装任何第三方包。

![界面预览](界面预览.jpg)

---

## 快速开始

1. 打开「腾讯应用宝电脑版」，随便启动一个应用/游戏，等 Android 引擎起来（约 10~30 秒）。
2. 双击 `应用宝引擎工具箱.exe`（单文件，免安装、无需 Python）。也可以双击 `启动工具箱.bat`。
3. 工具箱会自动寻找 `adb.exe`，然后自动连接 `127.0.0.1:5555`。
4. 顶部显示「已连接」即可开始使用。

### adb：自动识别，缺了就自动安装

启动时按顺序查找 adb，找到就用，不用手动配置：

1. 工具箱自己的 `tools\platform-tools\adb.exe`（自动安装的位置）；
2. 环境变量 `ADB_PATH`、系统 `PATH` 里的 `adb`；
3. `D:\Program Files\platform-tools\adb.exe`、`C:\platform-tools\adb.exe`、
   `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe` 等常见路径；
4. **应用宝自带的 adb**：`应用宝安装目录\Application\<版本号>\adb.exe`（逐版本自动扫描）；
5. 都没有时，启动后会询问是否下载 Google 官方 platform-tools（约 17 MB 解压后），
   装到 `tools\platform-tools\`，校验 `adb version` 能跑通后自动写入配置并连接。
   也可以随时点「诊断与维护 → 自动安装 adb」重新安装，或点顶部「ADB 路径」手动指定。

### 开启 ADB / 开发者模式

应用宝电脑版从 5.10.27.10 起默认关闭 ADB，需要手动打开一次（卸载前永久生效）：

1. 应用宝右上角「≡」→ 设置；
2. 在设置页**连续点击「性能」7 次**，进入开发者模式；
3. 勾选「开启开发者模式」，保存。

---

## 功能一览

| 模块 | 能力 |
| --- | --- |
| 首页 | 引擎/系统/Root/存储状态卡片，设备信息，操作记录，快捷入口 |
| 应用管理 | APK 批量安装、启动、停止、清除数据、卸载、禁用/启用、导出 APK、权限授予/撤销、应用详情 |
| MicroG | **一键安装/修复 microG Services + Companion + GsfProxy**：自动下载最新版、签名冲突时备份并卸载旧 GMS、安装、授权、电池白名单、检测 FakeGApps/LSPosed 签名伪装 |
| Root / Magisk | Root 状态、Magisk 版本、Zygisk/LSPosed 检测、模块列表、安装/启用/禁用/删除模块、Root Shell、`/system` 读写挂载、SELinux |
| 终端 | 设备内 Shell，支持以 `su` 执行、快捷命令、历史输出 |
| 日志 | 实时 Logcat，按级别/关键字/Tag 过滤，暂停、保存 |
| 文件 | 浏览 `/sdcard` 等目录（支持 Root 浏览）、上传/下载、新建/删除 |
| 截图 / 录屏 | 一键截图并预览、保存，`screenrecord` 录制 15/60 秒并拉回本地 |
| 系统设置 | 分辨率、DPI、旋转、动画缩放、保持唤醒、输入文本 |
| 诊断 | adb/设备/端口/进程全面检查，启动应用宝、结束引擎进程、开发者模式指引 |

---

## 关于「一键安装 microG」

microG 用来替代 Google 服务框架。完整生效需要两件事：

1. **microG 本体**（本工具自动完成）：`com.google.android.gms`（microG Services）
   与 `com.android.vending`（microG Companion）。
2. **GsfProxy**（本工具自动完成）：包名 `com.google.android.gsf`，只有 21 KB，是 microG 的
   GSF（Google Services Framework）代理。很多依赖 GSF 的应用（登录、推送、部分游戏）缺它会
   报「Google 服务框架未安装」，microG 自检里的 GSF 项也靠它。
   官方只发 APK、不提供其他分发：[microg/android_packages_apps_GsfProxy](https://github.com/microg/android_packages_apps_GsfProxy/releases)，
   工具箱会下载最新版并安装（已是最新则跳过）。
3. **签名伪装（signature spoofing）**：系统要允许 microG 冒充 Google 的签名。
   常见方案是 **Magisk + LSPosed + FakeGApps**：
   - 工具箱检测到没有 FakeGApps 时会自动下载安装；
   - 然后打开 **LSPosed**，在「模块」里启用 **FakeGApps**，作用域勾选「系统框架」；
   - 重启引擎后生效。打开 microG 设置 → 自检（Self-Check）可确认各项是否正常。

> 若引擎里装的是官方 Google 服务（版本号不是 `0.3.x`），签名与 microG 冲突，
> 工具箱会先把原 GMS 备份为 `cache/backup_gms.apk` 再卸载。也可以取消该选项，手动处理。

已在 Android 13 / x86_64 的应用宝引擎上验证：microG 0.3.18 + FakeGApps 6.6 + LSPosed 2.2.1 正常工作。

---

## LSPosed / Zygisk Next / Magisk 版本与安装顺序

三个组件都建议用**官方最新版**，按下面顺序装（除 manager.apk 外都是当 Magisk 模块刷入）：

| 组件 | 用什么版本 | 下载 |
| --- | --- | --- |
| Magisk | **原版**（topjohnwu 官方，不是各种分支/改版） | [releases/latest](https://github.com/topjohnwu/Magisk/releases/latest) |
| Zygisk Next | **最新版**（Dr-TSNG 官方） | [releases/latest](https://github.com/Dr-TSNG/ZygiskNext/releases/latest) |
| LSPosed | **最新版**（官方 LSPosed 或 JingMatrix 的 Vector 分支，二选一） | [LSPosed/latest](https://github.com/LSPosed/LSPosed/releases/latest) · [Vector/latest](https://github.com/JingMatrix/LSPosed/releases/latest) |
| FakeGApps | 最新版（签名伪装用） | [releases/latest](https://github.com/whew-inc/FakeGApps/releases/latest) |

1. **Magisk 装原版**：只用 topjohnwu/Magisk 的官方 APK（当前 v31.1，`Magisk-v31.1.apk`）。
   本项目的 system.vhd 方案刷出来的引擎自带 Magisk 原版 31.1，一般不用再装；要升级就在引擎内
   用官方 APK 覆盖安装，别用第三方改版，否则模块、Zygisk 行为都可能对不上。
2. **Zygisk Next 装最新版**：下载 `Zygisk-Next-<版本>-release.zip`，在「Root / Magisk → 安装
   Magisk 模块」里刷入，然后重启引擎。它是 Zygisk 的实现底座，LSPosed 依赖它。
3. **LSPosed 装最新版（关键一步）**：刷入 `LSPosed-v<版本>-<构建号>-zygisk-release.zip` 后，
   **必须从这个 zip 里解压出 `manager.apk` 并安装**（应用管理页「安装 APK」或 `adb install` 都行）。
   原因：新版 LSPosed 的管理器不再单独发布/上架，只放在模块 zip 内；只刷 zip 不装 manager.apk，
   模块虽然被加载，但**没有管理器界面**，看不到模块列表、也没法勾选作用域，等于无法管理模块。
   > 工具箱已内置这一步：刷模块 zip 时会自动扫描 `manager.apk` 并询问是否一并安装；
   > 也可以用 Root / Magisk 页的「装模块自带 APK」单独提取安装（会自动跳过 LSPosed 内部的 `daemon.apk`）。
4. **FakeGApps**：刷入模块后打开 LSPosed 管理器 → 模块 → 启用 FakeGApps → 作用域勾选
   「系统框架」→ 重启引擎，microG 的签名伪装才生效。

本机实测通过的一套组合：Magisk 31.1 + Zygisk Next 1.5.3 + LSPosed 2.2.1 (7912) +
FakeGApps 6.6 + microG 0.3.18。

## 关于 Root

应用宝引擎本质是一台 Android 13 x86_64 虚拟机，Root 方案与模拟器类似：

- 引擎镜像里带 `su`（Magisk）时，工具箱会直接识别为「已 Root」，并解锁模块管理；
- 已 Root 后可以：安装 Magisk 模块（zip）、启停模块、Root Shell、只读挂载改读写、查看 SELinux。

> 模块/挂载操作都可能让引擎无法启动，建议一次只改一个模块，出问题在工具箱里禁用该模块再重启。

### 没有 Root 怎么办：替换 system.vhd

应用宝引擎的 Root 不走「刷 boot.img」，而是**替换整个系统镜像 `system.vhd`**。
社区成熟方案（酷安 @米粉钉子户1999，2025-10）流程如下，镜像路径固定：

```
应用宝安装目录\Androws\Image\<当前版本号>\system.vhd
```

这台机器实测为：

```
E:\Program Files\Tencent\Androws\Image\5.10.7900.2936\system.vhd   （约 1.7 GB）
```

步骤：

1. **完全退出应用宝**（含托盘图标），确认 `Androws*` 进程已结束；工具箱「诊断与维护 → 结束引擎进程」可一键结束。
2. **备份 `system.vhd`**：复制一份改名 `system.vhd.bak`，失败可原样还原。
3. 用作者提供的 `qemu dd` 工具从 `system.vhd` 中提取 boot。
4. 在应用宝里打开 Magisk →「安装」→「选择并修补一个文件」，修补刚提取的 boot。
5. 修补产物重命名为 `2.boot_a`，用作者的「应用宝root.bat」生成新的 `system.vhd`。
6. 关闭应用宝与后台，把新 `system.vhd` 覆盖回原路径，重新启动应用宝。

工具箱里的对应入口：**Root / Magisk 页 →「未 Root？刷入方案」**，以及 **诊断与维护 →
「打开 system.vhd 目录」**，可直接跳到当前版本镜像所在文件夹（会自动挑选最新版本目录）。

风险提示：只替换 `system.vhd`，不要动 `data.vhd` 等其他镜像；版本号必须与应用宝当前版本对应；
替换前务必保留备份，开不了机就还原。替换成功后引擎自带 Magisk，本工具箱会自动识别为已 Root。

原教程：<https://www.coolapk.com/feed/68039703>（Root 页指引里也能直接复制链接）

---

## 免 Python 运行 / 自行打包

发布版就是根目录的 `应用宝引擎工具箱.exe`（约 12 MB，单文件，双击即用）。第一次启动会慢
1~3 秒（自解压），之后正常。运行时在 exe 同级生成 `cache/`、`screenshots/`、`config.json`，
把 exe 单独拷贝到别的文件夹也一样能用。

要自己重新打包（改过源码后），在 `构建` 目录执行：

```bat
py -m pip install pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name "应用宝引擎工具箱" --icon "app.ico" --add-data "app.ico;." ^
  --version-file "version_info.txt" .\yyb_toolbox.py
```

生成的 exe 在 `构建\dist\`，复制到上一级目录即可。源码里已处理 `sys.frozen`，打包后
配置与缓存目录会落在 exe 旁边，不会跑到临时解压目录。

## 命令行

```bash
# 自检：连接引擎、读取设备信息、截图
python yyb_toolbox.py --selftest
```

## 文件结构

```
应用宝工具箱/
├─ 应用宝引擎工具箱.exe     # 单文件发布版（免 Python）
├─ 启动工具箱.bat           # 双击启动（优先找 exe，回退到 Python 源码）
├─ README.md
├─ 界面预览.jpg             # 首页界面截图
├─ config.json             # 自动生成：adb 路径、设备地址、窗口尺寸、安装选项
├─ cache/                  # 下载的 microG / FakeGApps APK、GMS 备份
├─ screenshots/            # 截图与录屏输出
├─ tools/                  # 自动安装 adb 时的 platform-tools（未安装则不存在）
└─ 构建/                    # 源码与打包素材
   ├─ yyb_toolbox.py       # 主程序（单文件，无第三方依赖）
   ├─ app.ico              # 图标
   └─ version_info.txt     # exe 版本信息
```

## 常见问题

**连接失败 / connection refused**
先确认应用宝已启动且引擎已就绪（打开任意应用等 20 秒），再点「连接引擎」。
若装了 WSA 或其他模拟器，先退出它们，避免 5555 端口冲突。

**列表里出现 `emulator-5554`**
和 `127.0.0.1:5555` 是同一个引擎，工具箱会自动选用可用的那个。

**修改分辨率后界面异常**
应用宝自身会缩放画面，`wm size` / `wm density` 只影响部分界面；在「系统设置」点「重置」，
或重启引擎即可恢复。

**截图是黑屏**
应用宝引擎的显示层带有 `FLAG_SECURE` 保护，`screencap` 只能拿到黑图，这是系统限制，
不是工具箱的问题。录屏同样可能失败。需要截图时可用 Windows 自带截图（Win+Shift+S）。

**Hyper-V 异常**
应用宝设置内有「修复工具」；也可在「启用或关闭 Windows 功能」中修复 Hyper-V 后重启电脑。

powered by Doubao

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
应用宝引擎工具箱 (YYB Engine Toolbox)
====================================
一个类似 "WSA 工具箱" 的 Windows 桌面工具，用来调试「腾讯应用宝电脑版」内置的
Android 引擎（Androws / AOSP on Intel Platform，ADB 端口 127.0.0.1:5555）。

主要功能
--------
* 一键连接引擎（自动重试，适配引擎启动慢）
* 仪表盘：系统 / 分辨率 / Root / 存储 / 内存 一览
* 应用管理：安装 APK、启动、停止、清除数据、卸载、禁用、导出 APK、权限管理
* MicroG：一键下载并安装 microG Services + Companion，自动授权、加白名单，
  并检测签名伪装（FakeGApps / LSPosed）状态
* Root / Magisk：Root 状态、Magisk 版本、模块列表、安装 / 启停 / 删除模块、
  Root Shell、挂载读写、SELinux
* 终端、Logcat、文件浏览与 push/pull、截图 / 录屏、系统设置（分辨率 / DPI / 旋转 / 动画）
* 引擎诊断：端口、进程、adb server、开发者模式引导

仅依赖 Python 标准库（tkinter + adb），无需安装第三方包。
"""

from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

# --------------------------------------------------------------------------- #
# 常量与配置
# --------------------------------------------------------------------------- #

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = APP_DIR / "cache"
SHOT_DIR = APP_DIR / "screenshots"
CONFIG_FILE = APP_DIR / "config.json"


def resource_path(name):
    """打包后资源随 exe 解压到临时目录，源码运行时就在同目录。"""
    base = Path(getattr(sys, "_MEIPASS", APP_DIR))
    return base / name


DEFAULT_SERIAL = "127.0.0.1:5555"
ENGINE_PORT = 5555
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

MICROG_API = "https://api.github.com/repos/microg/GmsCore/releases/latest"
FAKEGAPPS_API = "https://api.github.com/repos/whew-inc/FakeGApps/releases/latest"
PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"

# 配色（深色）
BG = "#0f1218"
PANEL = "#11151c"
CARD = "#171c24"
CARD2 = "#1d232d"
BORDER = "#232a36"
TEXT = "#e6e9ef"
MUTED = "#98a2b3"
ACCENT = "#3b82f6"
ACCENT_D = "#2563eb"
GREEN = "#22c55e"
RED = "#ef4444"
YELLOW = "#f59e0b"

FONT = ("Microsoft YaHei UI", 10)
FONT_SM = ("Microsoft YaHei UI", 9)
FONT_BD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 17, "bold")
FONT_BIG = ("Microsoft YaHei UI", 16, "bold")
MONO = ("Consolas", 10)

CONFIG_DEFAULT = {
    "adb_path": "",
    "serial": DEFAULT_SERIAL,
    "geometry": "1280x820",
    "microg_uninstall_conflict": True,
    "microg_grant": True,
    "microg_fakegapps": True,
}


def load_config() -> dict:
    cfg = dict(CONFIG_DEFAULT)
    try:
        if CONFIG_FILE.exists():
            cfg.update(json.loads(CONFIG_FILE.read_text("utf-8")))
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


def now_str() -> str:
    return time.strftime("%H:%M:%S")


def find_store_launcher() -> str:
    """在注册表与常见安装目录里定位应用宝启动器。"""
    cands: list[str] = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                          (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")):
            try:
                root = winreg.OpenKey(hive, key)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    name = winreg.EnumKey(root, i)
                    with winreg.OpenKey(root, name) as sub:
                        disp, _ = winreg.QueryValueEx(sub, "DisplayName")
                        if "应用宝" not in str(disp) and "Androws" not in str(disp):
                            continue
                        icon = ""
                        try:
                            icon, _ = winreg.QueryValueEx(sub, "DisplayIcon")
                        except OSError:
                            pass
                        if icon:
                            cands.append(str(Path(icon.strip('"').split(",")[0]).parent / "AndrowsLauncher.exe"))
                except OSError:
                    continue
    except Exception:
        pass
    for base in ("C:", "D:", "E:", "F:"):
        cands.append(rf"{base}\Program Files\Tencent\Androws\Application\AndrowsLauncher.exe")
        cands.append(rf"{base}\Program Files (x86)\Tencent\Androws\Application\AndrowsLauncher.exe")
    for c in cands:
        if Path(c).exists():
            return c
    # 兜底：版本目录里的 Androws.exe
    for base in ("C:", "D:", "E:", "F:"):
        for d in Path(rf"{base}\Program Files\Tencent\Androws\Application").glob("*"):
            exe = d / "Androws.exe"
            if exe.exists():
                return str(exe)
    return ""


def find_engine_image_dirs() -> list[Path]:
    """定位应用宝引擎镜像目录（Androws\\Image\\<版本>\\system.vhd）。"""
    cands: list[Path] = []
    launcher = find_store_launcher()
    if launcher:
        cands.append(Path(launcher).resolve().parent.parent)
    for base in ("C:", "D:", "E:", "F:"):
        cands.append(Path(rf"{base}\Program Files\Tencent\Androws"))
        cands.append(Path(rf"{base}\Program Files (x86)\Tencent\Androws"))
    seen: set[str] = set()
    for root in cands:
        if str(root) in seen or not root.is_dir():
            continue
        seen.add(str(root))
        img = root / "Image"
        if not img.is_dir():
            continue
        dirs = [d for d in img.iterdir() if d.is_dir() and (d / "system.vhd").exists()]
        if dirs:
            dirs.sort(key=lambda d: d.name, reverse=True)
            return dirs
    return []


# --------------------------------------------------------------------------- #
# ADB 封装
# --------------------------------------------------------------------------- #

class AdbError(RuntimeError):
    pass


class Adb:
    """对 adb 命令的轻量封装，所有调用都是阻塞的，需在后台线程里用。"""

    def __init__(self, exe: str = "", serial: str = DEFAULT_SERIAL):
        self.exe = exe or Adb.autodetect()
        self.serial = serial or DEFAULT_SERIAL

    # -------------------------------------------------- 查找 adb
    @staticmethod
    def candidates() -> list[str]:
        res = []
        local = APP_DIR / "tools" / "platform-tools" / "adb.exe"
        if local.exists():
            res.append(str(local))
        env = os.environ.get("ADB_PATH", "").strip()
        if env:
            res.append(env)
        which = shutil.which("adb")
        if which:
            res.append(which)
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        res += [
            r"D:\Program Files\platform-tools\adb.exe",
            r"C:\Program Files\platform-tools\adb.exe",
            r"C:\platform-tools\adb.exe",
            str(local / "Android" / "Sdk" / "platform-tools" / "adb.exe"),
            r"C:\Program Files\Tencent\Androws\Application\1.0.0.0\adb.exe",
            r"C:\Program Files (x86)\Tencent\Androws\Application\1.0.0.0\adb.exe",
        ]
        # 额外扫描常见 platform-tools 目录
        for base in (r"C:\Program Files", r"D:\Program Files", r"C:\Program Files (x86)"):
            p = Path(base) / "platform-tools" / "adb.exe"
            res.append(str(p))
        # 应用宝自带 adb：Androws\Application\<版本>\adb.exe
        for base in ("C:", "D:", "E:", "F:"):
            for sub in (rf"{base}\Program Files\Tencent\Androws\Application",
                        rf"{base}\Program Files (x86)\Tencent\Androws\Application"):
                app = Path(sub)
                if app.is_dir():
                    for d in sorted(app.glob("*"), reverse=True):
                        exe = d / "adb.exe"
                        if exe.exists():
                            res.append(str(exe))
        return [p for p in res if p and Path(p).exists()]

    @staticmethod
    def install_platform_tools(emit=None) -> str:
        """下载 Google 官方 platform-tools 到 tools 目录，返回 adb.exe 路径。"""
        import zipfile
        tools = APP_DIR / "tools"
        tools.mkdir(exist_ok=True)
        zip_path = tools / "platform-tools.zip"
        if emit:
            emit("log", f"下载 platform-tools：{PLATFORM_TOOLS_URL}")
        req = urllib.request.Request(PLATFORM_TOOLS_URL, headers={"User-Agent": "YYB-Toolbox/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            with open(zip_path, "wb") as f:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total and emit:
                        emit("status", f"下载 platform-tools {done/1048576:.1f}/{total/1048576:.1f} MB")
        if emit:
            emit("status", "解压 platform-tools …")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tools)
        try:
            zip_path.unlink()
        except OSError:
            pass
        adb = tools / "platform-tools" / "adb.exe"
        if not adb.exists():
            found = list(tools.rglob("adb.exe"))
            if not found:
                raise AdbError("解压后未找到 adb.exe")
            adb = found[0]
        # 校验能跑起来
        p = subprocess.run([str(adb), "version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           creationflags=CREATE_NO_WINDOW, timeout=30)
        if p.returncode != 0:
            raise AdbError("下载的 adb 无法运行：" + (p.stderr or p.stdout))
        if emit:
            emit("log", f"platform-tools 安装完成：{adb}")
        return str(adb)

    @staticmethod
    def autodetect() -> str:
        cfg = load_config().get("adb_path", "")
        if cfg and Path(cfg).exists():
            return cfg
        cands = Adb.candidates()
        return cands[0] if cands else ""

    def ready(self) -> bool:
        return bool(self.exe) and Path(self.exe).exists()

    # -------------------------------------------------- 基础执行
    def _cmd(self, args: list[str], serial: str | None = None) -> list[str]:
        cmd = [self.exe]
        use_serial = self.serial if serial is None else serial
        no_serial_cmds = {"connect", "disconnect", "devices", "kill-server", "start-server",
                          "version", "help", "reconnect", "wait-for-device", "mdns"}
        if use_serial and args and args[0] not in no_serial_cmds:
            cmd += ["-s", use_serial]
        return cmd + args

    def run(self, args: list[str], serial: str | None = None, timeout: int = 30) -> str:
        if not self.ready():
            raise AdbError("未找到 adb.exe，请先在顶部设置 ADB 路径")
        try:
            p = subprocess.run(
                self._cmd(args, serial),
                capture_output=True, encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW, timeout=timeout,
            )
        except FileNotFoundError as e:
            raise AdbError("adb 可执行文件不存在：" + str(e))
        except subprocess.TimeoutExpired:
            raise AdbError(f"adb 命令超时（{timeout}s）：{' '.join(args)}")
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode != 0 and not out.strip():
            raise AdbError(f"adb 执行失败({p.returncode})：{' '.join(args)}")
        return out.strip()

    def shell(self, cmd: str, root: bool = False, timeout: int = 60, serial: str | None = None) -> str:
        if root:
            cmd = "su -c " + shlex.quote(cmd)
        return self.run(["shell", cmd], serial=serial, timeout=timeout)

    def exec_out(self, args: list[str], timeout: int = 60) -> bytes:
        if not self.ready():
            raise AdbError("未找到 adb.exe")
        p = subprocess.run(
            self._cmd(["exec-out"] + args),
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=timeout,
        )
        return p.stdout or b""

    # -------------------------------------------------- 连接
    def devices(self) -> list[dict]:
        out = self.run(["devices", "-l"], timeout=20)
        rows = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            info = {"serial": parts[0], "state": parts[1]}
            for kv in parts[2:]:
                if ":" in kv:
                    k, v = kv.split(":", 1)
                    info[k] = v
            rows.append(info)
        return rows

    def connect(self, serial: str | None = None, timeout: int = 20) -> str:
        serial = serial or self.serial
        self.serial = serial
        self.run(["start-server"], timeout=30)
        out = self.run(["connect", serial], timeout=timeout)
        return out

    def ensure_connected(self, serial: str | None = None, retries: int = 3, wait: float = 4.0,
                         emit=None) -> str:
        serial = serial or self.serial
        self.serial = serial
        last = ""
        for i in range(1, retries + 1):
            if emit:
                emit("log", f"[{now_str()}] 连接 {serial}（第 {i}/{retries} 次）")
            try:
                last = self.connect(serial)
            except Exception as e:
                last = str(e)
            devs = []
            try:
                devs = self.devices()
            except Exception:
                pass
            for d in devs:
                if d["serial"] == serial and d["state"] == "device":
                    return serial
            # 兼容引擎只暴露 emulator-5554 的情况
            for d in devs:
                if d["state"] == "device" and d.get("product") == "caas":
                    self.serial = d["serial"]
                    return d["serial"]
            if i < retries:
                time.sleep(wait)
        raise AdbError(f"连接 {serial} 失败：{last or '设备未就绪'}")

    def state(self, serial: str | None = None) -> str:
        try:
            return self.run(["get-state"], serial=serial or self.serial, timeout=10).strip()
        except Exception:
            return "offline"


def parse_getprop(text: str) -> dict:
    props = {}
    for line in text.splitlines():
        m = re.match(r"^\[([^\]]+)\]: \[(.*)\]$", line.strip())
        if m:
            props[m.group(1)] = m.group(2)
    return props


def fmt_size(bytes_: int) -> str:
    v = float(bytes_)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            return f"{v:.1f} {unit}" if unit != "B" else f"{int(v)} B"
        v /= 1024
    return f"{v:.1f} TB"


def parse_version(text: str) -> str:
    """从 dumpsys 输出里提取 versionName，忽略管道被截断时的杂项输出。"""
    for line in (text or "").splitlines():
        if "versionName=" in line:
            return line.split("versionName=", 1)[1].strip().split()[0]
    return ""


def collect_info(adb: Adb, emit=None) -> dict:
    """采集设备信息，返回扁平字典。"""
    info: dict = {}
    props = parse_getprop(adb.shell("getprop", timeout=30))
    info["model"] = props.get("ro.product.model", "?")
    info["brand"] = props.get("ro.product.brand", "?")
    info["android"] = props.get("ro.build.version.release", "?")
    info["sdk"] = props.get("ro.build.version.sdk", "?")
    info["abi"] = props.get("ro.product.cpu.abi", "?")
    info["fingerprint"] = props.get("ro.build.fingerprint", "?")
    info["build_type"] = props.get("ro.build.type", "?")

    # 分辨率 / DPI
    try:
        wm = adb.shell("wm size", timeout=20)
        size = ""
        for line in wm.splitlines():
            if "Override size" in line:
                size = line.split(":", 1)[1].strip()
        if not size:
            for line in wm.splitlines():
                if "Physical size" in line:
                    size = line.split(":", 1)[1].strip()
        info["resolution"] = size or "?"
        dens = adb.shell("wm density", timeout=20)
        d = ""
        for line in dens.splitlines():
            if "Override density" in line:
                d = line.split(":", 1)[1].strip()
        if not d:
            for line in dens.splitlines():
                if "Physical density" in line:
                    d = line.split(":", 1)[1].strip()
        info["density"] = d or "?"
    except Exception:
        info["resolution"] = info["density"] = "?"

    # 存储
    try:
        df = adb.shell("df -h /data /storage/emulated 2>/dev/null", timeout=30)
        target = None
        for line in df.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6 and "/data" in parts[-1]:
                target = parts
        if not target:
            for line in df.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 6 and "emulated" in parts[-1]:
                    target = parts
        if target:
            info["storage"] = f"{target[2]} / {target[1]}（剩余 {target[3]}）"
        else:
            info["storage"] = "?"
    except Exception:
        info["storage"] = "?"

    # 内存
    try:
        mem = adb.shell("cat /proc/meminfo", timeout=20)
        total = avail = 0
        for line in mem.splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) * 1024
        if total:
            info["memory"] = f"{fmt_size(total - avail)} / {fmt_size(total)} 已用"
        else:
            info["memory"] = "?"
    except Exception:
        info["memory"] = "?"

    # 电池 / 运行时间 / SELinux
    try:
        bat = adb.shell("dumpsys battery", timeout=20)
        level = temp = "?"
        for line in bat.splitlines():
            if line.strip().startswith("level:"):
                level = line.split(":", 1)[1].strip()
            elif line.strip().startswith("temperature:"):
                temp = line.split(":", 1)[1].strip()
        info["battery"] = f"{level}% / {int(temp)/10:.1f}℃" if temp.isdigit() else f"{level}%"
    except Exception:
        info["battery"] = "?"
    try:
        up = float(adb.shell("cat /proc/uptime", timeout=10).split()[0])
        h, m = int(up // 3600), int(up % 3600 // 60)
        info["uptime"] = f"{h} 小时 {m} 分"
    except Exception:
        info["uptime"] = "?"
    try:
        info["selinux"] = adb.shell("getenforce", timeout=10).strip() or "?"
    except Exception:
        info["selinux"] = "?"

    # Root / Magisk
    info["root"] = False
    info["magisk"] = ""
    try:
        out = adb.shell("id", root=True, timeout=20)
        if "uid=0" in out:
            info["root"] = True
            info["magisk"] = adb.shell("magisk -v", root=True, timeout=20).strip()
    except Exception as e:
        if emit:
            emit("log", f"Root 检测失败：{e}")

    info["serial"] = adb.serial
    return info


# --------------------------------------------------------------------------- #
# 主程序
# --------------------------------------------------------------------------- #

class ToolboxApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.adb = Adb(self.cfg.get("adb_path") or Adb.autodetect(), self.cfg.get("serial", DEFAULT_SERIAL))
        self.uiq: queue.Queue = queue.Queue()
        self.busy_count = 0
        self.info: dict = {}
        self.apps: list[dict] = []
        self.logcat_proc: subprocess.Popen | None = None
        self.logcat_thread: threading.Thread | None = None
        self.logcat_paused = False
        self.logcat_lines: queue.Queue = queue.Queue()
        self.logcat_filter = ""
        self.logcat_level = "全部"
        self.shot_img = None
        self.rec_proc = None
        self.module_rows: list[dict] = []
        self.current_dir = "/sdcard"
        self.file_root_mode = tk.BooleanVar(value=False)

        CACHE_DIR.mkdir(exist_ok=True)
        SHOT_DIR.mkdir(exist_ok=True)

        self._setup_style()
        self.current_page = None
        self._build_ui()
        self.busy_count = 0
        self.bottom_progress.pack_forget()
        self._drain_ui_queue()
        self.root.after(150, self._pump_logcat)
        if self.adb.ready():
            self.set_status(f"adb: {self.adb.exe}")
            self.root.after(300, self.connect)
        else:
            self.set_status("未找到 adb，可自动下载安装")
            self.root.after(500, self._offer_adb_install)

    def _offer_adb_install(self):
        if self.adb.ready():
            return
        if messagebox.askyesno(
                "未找到 adb",
                "工具箱没有在本机找到 adb.exe。\n\n"
                "是否自动下载 Google 官方 platform-tools（约 12 MB），安装到工具箱的 tools 目录？\n\n"
                "选「否」也不会影响以后使用：点顶部「ADB 路径」可以手动指定 adb.exe。",
                parent=self.root):
            self.install_adb(ask=False)

    # ======================================================================
    # 样式与通用组件
    # ======================================================================
    def _setup_style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                     bordercolor=BORDER, rowheight=27, font=FONT)
        st.configure("Treeview.Heading", background=CARD2, foreground=MUTED, relief="flat",
                     font=FONT_BD, padding=(6, 6))
        st.map("Treeview", background=[("selected", "#24405f")], foreground=[("selected", "#ffffff")])
        st.configure("TCombobox", fieldbackground=CARD2, background=CARD2, foreground=TEXT,
                     arrowcolor=TEXT, bordercolor=BORDER, padding=5)
        st.map("TCombobox", fieldbackground=[("readonly", CARD2)])
        st.configure("TProgressbar", background=ACCENT, troughcolor=CARD2, bordercolor=BORDER, thickness=6)
        st.configure("Vertical.TScrollbar", background=CARD2, troughcolor=CARD, bordercolor=CARD,
                     arrowcolor=MUTED, relief="flat", width=10)
        st.map("Vertical.TScrollbar", background=[("active", "#2c3542")])
        st.configure("Horizontal.TScrollbar", background=CARD2, troughcolor=CARD, bordercolor=CARD,
                     arrowcolor=MUTED, relief="flat")
        # tk.Scrollbar（ScrolledText 内部使用）
        for key, val in (("*Scrollbar.background", CARD2), ("*Scrollbar.troughcolor", CARD),
                         ("*Scrollbar.activebackground", "#2c3542"), ("*Scrollbar.highlightthickness", 0),
                         ("*Scrollbar.borderwidth", 0), ("*Scrollbar.width", 10),
                         ("*Scrollbar.arrowcolor", MUTED), ("*Scrollbar.relief", "flat")):
            self.root.option_add(key, val)
        st.configure("TCheckbutton", background=CARD, foreground=TEXT, font=FONT,
                     focuscolor=CARD)
        st.map("TCheckbutton", background=[("active", CARD)])
        st.configure("TRadiobutton", background=CARD, foreground=TEXT, font=FONT)
        self.root.option_add("*TCombobox*Listbox.background", CARD2)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_D)

    def button(self, parent, text, command, kind="ghost", width=None, font=None, pady=6):
        palettes = {
            "primary": (ACCENT, ACCENT_D, "#ffffff", "#ffffff"),
            "ghost": (CARD2, "#2b3442", TEXT, "#ffffff"),
            "danger": ("#3a1f24", "#4d262d", "#f87373", "#ffffff"),
            "success": ("#16352a", "#1c4335", "#5ee08e", "#ffffff"),
        }
        bg, active, fg, afg = palettes.get(kind, palettes["ghost"])
        b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                      activebackground=active, activeforeground=afg,
                      relief="flat", bd=0, highlightthickness=0, padx=13, pady=pady,
                      cursor="hand2", font=font or FONT)
        if width:
            b.configure(width=width)
        return b

    def entry(self, parent, textvariable=None, width=None, show=None):
        e = tk.Entry(parent, textvariable=textvariable, bg=CARD2, fg=TEXT, insertbackground=TEXT,
                     relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT, font=FONT)
        if width:
            e.configure(width=width)
        if show:
            e.configure(show=show)
        return e

    def card(self, parent, title=None):
        outer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        inner = tk.Frame(outer, bg=CARD, padx=14, pady=12)
        inner.pack(fill="both", expand=True)
        if title:
            tk.Label(inner, text=title, bg=CARD, fg=TEXT, font=FONT_BD).pack(anchor="w", pady=(0, 8))
        return outer, inner

    def label(self, parent, text="", fg=TEXT, font=None, bg=None, **kw):
        return tk.Label(parent, text=text, fg=fg, bg=bg or CARD, font=font or FONT, **kw)

    # ======================================================================
    # 界面骨架
    # ======================================================================
    def _build_ui(self):
        self.root.title("应用宝引擎工具箱 · YYB Toolbox")
        try:
            self.root.iconbitmap(default=str(resource_path("app.ico")))
        except Exception:
            pass
        self.root.geometry(self.cfg.get("geometry", "1280x820"))
        self.root.minsize(1120, 700)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # ---------- 顶栏 ----------
        top = tk.Frame(self.root, bg=PANEL, height=64)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="应用宝引擎工具箱", bg=PANEL, fg=TEXT, font=FONT_TITLE).pack(side="left", padx=(18, 8), pady=14)
        tk.Label(top, text="YYB TOOLBOX", bg=PANEL, fg=MUTED, font=("Consolas", 9)).pack(side="left", pady=(18, 0), anchor="n")

        right = tk.Frame(top, bg=PANEL)
        right.pack(side="right", padx=16, pady=12)
        self.dot = tk.Canvas(right, width=10, height=10, bg=PANEL, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 6))
        self.dot_id = self.dot.create_oval(1, 1, 9, 9, fill="#6b7280", outline="")
        self.conn_label = tk.Label(right, text="未连接", bg=PANEL, fg=MUTED, font=FONT)
        self.conn_label.pack(side="left", padx=(0, 14))

        self.serial_var = tk.StringVar(value=self.cfg.get("serial", DEFAULT_SERIAL))
        e = self.entry(right, self.serial_var, width=16)
        e.pack(side="left", ipady=5, padx=(0, 8))
        self.btn_connect = self.button(right, "连接引擎", self.connect, "primary")
        self.btn_connect.pack(side="left")
        self.button(right, "ADB 路径", self.choose_adb, "ghost").pack(side="left", padx=(8, 0))
        self.adb_label = tk.Label(top, text="", bg=PANEL, fg=MUTED, font=FONT_SM)
        self.adb_label.pack(side="right", padx=(0, 10))

        # ---------- 主体 ----------
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        side = tk.Frame(body, bg=PANEL, width=176)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        self.page_frames = {}
        self.nav_items = {}
        nav_defs = [
            ("home", "首页"),
            ("apps", "应用管理"),
            ("microg", "MicroG"),
            ("root", "Root / Magisk"),
            ("shell", "终端"),
            ("logcat", "日志 Logcat"),
            ("files", "文件"),
            ("shot", "截图 / 录屏"),
            ("settings", "系统设置"),
            ("diag", "诊断与维护"),
        ]
        for key, text in nav_defs:
            row = tk.Frame(side, bg=PANEL, cursor="hand2")
            row.pack(fill="x", padx=10, pady=2)
            bar = tk.Frame(row, bg=PANEL, width=3)
            bar.pack(side="left", fill="y")
            lab = tk.Label(row, text=text, bg=PANEL, fg=MUTED, font=FONT, anchor="w", padx=12, pady=10)
            lab.pack(side="left", fill="x", expand=True)
            for w in (row, lab):
                w.bind("<Button-1>", lambda _e, k=key: self.show_page(k))
                w.bind("<Enter>", lambda _e, r=row, l=lab, k=key: self._nav_hover(k, r, l, True))
                w.bind("<Leave>", lambda _e, r=row, l=lab, k=key: self._nav_hover(k, r, l, False))
            self.nav_items[key] = (row, lab, bar)

        self.content = tk.Frame(body, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

        # ---------- 状态栏 ----------
        status = tk.Frame(self.root, bg=PANEL, height=28)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(status, textvariable=self.status_var, bg=PANEL, fg=MUTED, font=FONT_SM, anchor="w").pack(
            side="left", padx=12)
        self.bottom_progress = ttk.Progressbar(status, mode="indeterminate", length=160)
        self.bottom_progress.pack(side="right", padx=10, pady=6)

        # ---------- 页面 ----------
        self.build_home()
        self.build_apps()
        self.build_microg()
        self.build_root()
        self.build_shell()
        self.build_logcat()
        self.build_files()
        self.build_shot()
        self.build_settings()
        self.build_diag()

        self.show_page("home")
        self.update_adb_label()

    def _nav_hover(self, key, row, lab, entering):
        active = self.current_page == key if hasattr(self, "current_page") else False
        if entering and not active:
            row.configure(bg=CARD)
            lab.configure(bg=CARD, fg=TEXT)
        elif not active:
            row.configure(bg=PANEL)
            lab.configure(bg=PANEL, fg=MUTED)

    def show_page(self, key):
        self.current_page = key
        for k, f in self.page_frames.items():
            f.pack_forget()
        self.page_frames[key].pack(fill="both", expand=True)
        for k, (row, lab, bar) in self.nav_items.items():
            on = k == key
            row.configure(bg=CARD if on else PANEL)
            lab.configure(bg=CARD if on else PANEL, fg=TEXT if on else MUTED,
                          font=FONT_BD if on else FONT)
            bar.configure(bg=ACCENT if on else PANEL)
        if key == "apps" and not self.apps:
            self.refresh_apps()
        if key == "root":
            self.refresh_root()

    def new_page(self, key):
        fr = tk.Frame(self.content, bg=BG, padx=18, pady=16)
        self.page_frames[key] = fr
        return fr

    def set_status(self, text):
        self.status_var.set(text)

    def emit(self, kind, *args):
        self.uiq.put((kind, args))

    def set_busy(self, busy: bool):
        self.busy_count = max(0, self.busy_count + (1 if busy else -1))
        if self.busy_count and not self.bottom_progress.winfo_ismapped():
            self.bottom_progress.pack(side="right", padx=10, pady=6)
            self.bottom_progress.start(12)
        elif not self.busy_count:
            self.bottom_progress.stop()
            self.bottom_progress.pack_forget()

    def bg(self, fn, done=None):
        """后台执行 fn(emit)，结束后回到 UI 线程执行 done(result)。"""
        self.set_busy(True)

        def worker():
            try:
                res = fn(self.emit)
                self.uiq.put(("done", (done, res, None, "")))
            except Exception as e:  # noqa: BLE001
                tb = traceback.format_exc()
                self.uiq.put(("done", (done, None, e, tb)))
        threading.Thread(target=worker, daemon=True).start()

    def _drain_ui_queue(self):
        try:
            while True:
                item = self.uiq.get_nowait()
                kind = item[0]
                args = item[1]
                if kind == "log":
                    self.append_home_log(args[0])
                elif kind == "status":
                    self.set_status(args[0])
                elif kind == "progress":
                    self.set_progress(*args)
                elif kind == "microg_progress":
                    frac, text = args[0], args[1]
                    if hasattr(self, "microg_bar"):
                        self.microg_bar["value"] = frac
                    self.set_status(text)
                elif kind == "microg_log":
                    self.microg_log_write(args[0])
                elif kind == "info":
                    self._info_loaded(args[0])
                elif kind == "shot":
                    self._shot_loaded(args[0])
                elif kind == "done":
                    done, res, err, tb = args
                    self.set_busy(False)
                    if err is not None:
                        self.set_status(f"失败：{err}")
                        self.append_home_log(f"[{now_str()}] 失败：{err}")
                        if done:
                            try:
                                done(None, err)
                            except TypeError:
                                pass
                        self._handle_error(err, tb)
                    else:
                        if done:
                            try:
                                done(res, None)
                            except TypeError:
                                done(res)
        except queue.Empty:
            pass
        self.root.after(60, self._drain_ui_queue)

    def _handle_error(self, err, tb=""):
        text = str(err)
        if isinstance(err, AdbError):
            messagebox.showwarning("操作失败", text, parent=self.root)
        elif text and len(text) < 300:
            self.append_home_log(f"[{now_str()}] 异常：{text}")
        if tb:
            self.append_home_log(tb.strip().splitlines()[-1])

    # ======================================================================
    # 顶部操作
    # ======================================================================
    def update_adb_label(self):
        if self.adb.ready():
            self.adb_label.configure(text="ADB 就绪", fg=GREEN)
        else:
            self.adb_label.configure(text="缺少 adb", fg=RED)

    def install_adb(self, ask=True):
        if ask and not messagebox.askyesno(
                "自动安装 adb",
                "将从 Google 官方源下载 platform-tools（约 12 MB），解压到：\n"
                f"{APP_DIR / 'tools'}\n\n继续？", parent=self.root):
            return

        def work(emit):
            return Adb.install_platform_tools(emit=emit)

        def done(path, err):
            if err:
                self.set_status("adb 安装失败：" + str(err))
                messagebox.showerror("安装 adb 失败", str(err), parent=self.root)
                return
            self.adb.exe = path
            self.cfg["adb_path"] = path
            save_config(self.cfg)
            self.update_adb_label()
            self.set_status(f"adb 已安装：{path}")
            if hasattr(self, "diag_text"):
                self.diag_write(f"已自动安装 adb：{path}")
            try:  # 换版本时先关掉旧 adb server，避免 server/client 版本不匹配
                self.adb.run(["kill-server"], timeout=20)
            except Exception:
                pass
            self.connect()

        self.bg(work, done)

    def choose_adb(self):
        path = filedialog.askopenfilename(
            title="选择 adb.exe", filetypes=[("adb", "adb.exe"), ("所有文件", "*.*")],
            initialdir=str(Path(self.adb.exe).parent) if self.adb.ready() else "C:\\",
        )
        if path:
            self.adb.exe = path
            self.cfg["adb_path"] = path
            save_config(self.cfg)
            self.update_adb_label()
            self.set_status(f"已设置 adb：{path}")

    def connect(self):
        serial = self.serial_var.get().strip() or DEFAULT_SERIAL
        self.cfg["serial"] = serial
        save_config(self.cfg)
        self.set_status(f"正在连接 {serial} …")
        self.set_conn_state("connecting")

        def work(emit):
            emit("log", f"[{now_str()}] ADB={self.adb.exe}")
            self.adb.ensure_connected(serial, retries=4, wait=4, emit=emit)
            try:
                info = collect_info(self.adb, emit)
            except Exception as e:
                emit("log", f"设备信息采集部分失败：{e}")
                info = {"model": "已连接", "android": "?", "sdk": "?", "abi": "?", "root": False,
                        "serial": self.adb.serial}
            return info

        def done(info, err):
            if err:
                self.set_conn_state("offline")
                self.set_status(f"连接失败：{err}")
                info = {"model": "未连接", "android": "?", "sdk": "?", "abi": "?", "root": False}
                self._info_loaded(info)
                self.append_home_log(f"[{now_str()}] 连接失败：{err}")
                return
            self.set_conn_state("online")
            self.serial_var.set(self.adb.serial)
            self.cfg["serial"] = self.adb.serial
            save_config(self.cfg)
            self.set_status(f"已连接 {self.adb.serial}")
            self.append_home_log(f"[{now_str()}] 已连接 {self.adb.serial}，{info.get('model')} / Android {info.get('android')}")
            self._info_loaded(info)
            self.refresh_apps(force=True)
            self.refresh_root()

        self.bg(work, done)

    def set_conn_state(self, state):
        colors = {"online": GREEN, "offline": "#6b7280", "connecting": YELLOW}
        texts = {"online": "已连接", "offline": "未连接", "connecting": "连接中…"}
        self.dot.itemconfigure(self.dot_id, fill=colors.get(state, "#6b7280"))
        self.conn_label.configure(text=texts.get(state, "未连接"),
                                  fg=GREEN if state == "online" else MUTED)

    def refresh_all(self):
        def work(emit):
            return collect_info(self.adb, emit)
        self.bg(work, lambda info, err: info and self._info_loaded(info))

    # ======================================================================
    # 首页
    # ======================================================================
    def build_home(self):
        page = self.new_page("home")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)

        # 顶部统计卡
        stats = tk.Frame(page, bg=BG)
        stats.grid(row=0, column=0, sticky="ew")
        for i in range(4):
            stats.columnconfigure(i, weight=1, uniform="s")
        self.home_stat = {}
        defs = [("conn", "引擎连接", "未连接", "127.0.0.1:5555"),
                ("sys", "系统版本", "—", "等待连接"),
                ("root", "Root 状态", "—", "等待连接"),
                ("disk", "存储 / 内存", "—", "等待连接")]
        for i, (key, title, value, sub) in enumerate(defs):
            card, inner = self.card(stats)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            tk.Label(inner, text=title, bg=CARD, fg=MUTED, font=FONT_SM).pack(anchor="w")
            v = tk.Label(inner, text=value, bg=CARD, fg=TEXT, font=FONT_BIG)
            v.pack(anchor="w", pady=(4, 2))
            s = tk.Label(inner, text=sub, bg=CARD, fg=MUTED, font=FONT_SM)
            s.pack(anchor="w")
            self.home_stat[key] = (v, s)

        # 快捷操作
        quick_card, quick = self.card(page, "快捷操作")
        quick_card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        row1 = tk.Frame(quick, bg=CARD)
        row1.pack(fill="x")
        self.button(row1, "一键连接引擎", self.connect, "primary").pack(side="left")
        self.button(row1, "安装 APK", self.install_apk_dialog).pack(side="left", padx=8)
        self.button(row1, "一键安装 MicroG", self.microg_oneclick_page, "success").pack(side="left")
        self.button(row1, "Root 终端", lambda: self.show_page("root")).pack(side="left", padx=8)
        self.button(row1, "截图", self.take_screenshot).pack(side="left")
        self.button(row1, "重启 ADB", self.restart_adb).pack(side="left", padx=8)
        self.button(row1, "应用宝开发者模式", self.show_dev_guide).pack(side="left")

        # 设备信息
        info_card, info_inner = self.card(page, "设备信息")
        info_card.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.info_labels = {}
        grid = tk.Frame(info_inner, bg=CARD)
        grid.pack(fill="x")
        fields = ["设备型号", "品牌", "系统版本", "SDK", "架构", "分辨率",
                  "DPI", "运行时间", "电池", "SELinux", "存储", "内存"]
        for idx, name in enumerate(fields):
            r, c = divmod(idx, 4)
            cell = tk.Frame(grid, bg=CARD)
            cell.grid(row=r, column=c, sticky="w", padx=(0, 22), pady=5)
            tk.Label(cell, text=name, bg=CARD, fg=MUTED, font=FONT_SM).pack(anchor="w")
            v = tk.Label(cell, text="—", bg=CARD, fg=TEXT, font=FONT)
            v.pack(anchor="w")
            self.info_labels[name] = v

        # 操作记录
        log_card, log_inner = self.card(page, "操作记录")
        log_card.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        self.home_log = scrolledtext.ScrolledText(
            log_inner, height=6, bg="#0c1015", fg="#b9c2d0", insertbackground=TEXT,
            relief="flat", font=("Consolas", 9), wrap="word")
        self.home_log.pack(fill="both", expand=True)
        self.append_home_log(f"[{now_str()}] 工具箱已启动")

    def append_home_log(self, text: str):
        if not hasattr(self, "home_log"):
            return
        try:
            self.home_log.insert("end", text.rstrip() + "\n")
            self.home_log.see("end")
            # 限制行数
            if int(self.home_log.index("end-1c").split(".")[0]) > 400:
                self.home_log.delete("1.0", "100.0")
        except Exception:
            pass

    def _info_loaded(self, info):
        if not info:
            return
        self.info = info
        v, s = self.home_stat["conn"]
        v.configure(text="已连接" if info.get("model") not in (None, "", "未连接") else "未连接",
                    fg=GREEN if info.get("model") not in (None, "", "未连接") else MUTED)
        s.configure(text=info.get("serial", "—"))
        v, s = self.home_stat["sys"]
        v.configure(text=f"Android {info.get('android', '?')}")
        s.configure(text=f"SDK {info.get('sdk', '?')} · {info.get('abi', '?')}")
        v, s = self.home_stat["root"]
        root = info.get("root")
        v.configure(text="已 Root" if root else "未 Root", fg=GREEN if root else MUTED)
        s.configure(text=(info.get("magisk") or "未检测到 Magisk"))
        v, s = self.home_stat["disk"]
        v.configure(text=(info.get("storage", "?").split("（")[0] if info.get("storage") else "—"))
        s.configure(text=info.get("memory", "—"))

        mapping = {
            "设备型号": info.get("model", "—"),
            "品牌": info.get("brand", "—"),
            "系统版本": info.get("android", "—"),
            "SDK": info.get("sdk", "—"),
            "架构": info.get("abi", "—"),
            "分辨率": info.get("resolution", "—"),
            "DPI": info.get("density", "—"),
            "运行时间": info.get("uptime", "—"),
            "电池": info.get("battery", "—"),
            "SELinux": info.get("selinux", "—"),
            "存储": info.get("storage", "—"),
            "内存": info.get("memory", "—"),
        }
        for k, val in mapping.items():
            if k in self.info_labels:
                self.info_labels[k].configure(text=str(val))

    def set_progress(self, frac, text=""):
        self.set_status(text or f"进度 {int(frac*100)}%")

    def restart_adb(self):
        def work(emit):
            emit("log", f"[{now_str()}] 重启 adb server")
            self.adb.run(["kill-server"], timeout=20)
            time.sleep(1)
            self.adb.run(["start-server"], timeout=30)
            return self.adb.ensure_connected(self.adb.serial, retries=3, wait=3, emit=emit)

        self.bg(work, lambda r, e: (self.set_status("adb 已重启" if not e else str(e)),
                                    self.refresh_all() if not e else None))

    def show_dev_guide(self):
        top = tk.Toplevel(self.root)
        top.title("应用宝引擎开发者模式 / ADB 开启指引")
        top.geometry("640x520")
        top.configure(bg=BG)
        txt = scrolledtext.ScrolledText(top, bg="#0c1015", fg=TEXT, font=FONT, relief="flat",
                                        wrap="word", padx=14, pady=12)
        txt.pack(fill="both", expand=True, padx=12, pady=12)
        guide = """一、开启 ADB（5.10.27.10 及以后版本默认关闭）
1. 打开「腾讯应用宝电脑版」，点击右上角 “≡” → 设置。
2. 在设置页连续点击“性能”7 次，直到提示进入开发者模式。
3. 勾选“开启开发者模式”，保存设置。
4. 打开一次后，在卸载/重装应用宝前永久生效。

二、连接引擎的 ADB 端口
1. 应用宝电脑版启动时会静默启动 Android 引擎（Androws）。
2. 引擎启动需要 10~30 秒，期间连接会失败，属于正常现象。
3. 引擎的 ADB 固定监听 127.0.0.1:5555，连上后设备名通常是 emulator-5554 或 127.0.0.1:5555。
4. 手动命令：
   adb connect 127.0.0.1:5555
   adb -s 127.0.0.1:5555 shell
   adb -s 127.0.0.1:5555 install xxx.apk

三、常见问题
· 连接被拒绝：先启动应用宝，随便打开一个应用/游戏，等引擎起来后再点“连接引擎”。
· 提示 adb 未授权：应用宝引擎一般默认放行；若在设置中关闭过 ADB，请回到第一步。
· 端口 5555 被占用：可能是 WSA 或其他模拟器，退出它们后重试。
· Hyper-V 异常：应用宝设置里提供“修复工具”，或用系统“启用或关闭 Windows 功能”修复 Hyper-V。
"""
        txt.insert("1.0", guide)
        txt.configure(state="disabled")
        self.button(top, "关闭", top.destroy, "primary").pack(pady=(0, 12))

    ROOT_GUIDE_URL = "https://www.coolapk.com/feed/68039703"

    def show_root_guide(self):
        top = tk.Toplevel(self.root)
        top.title("引擎没有 Root 怎么办 · 替换 system.vhd 方案")
        top.geometry("720x560")
        top.configure(bg=BG)
        txt = scrolledtext.ScrolledText(top, bg="#0c1015", fg=TEXT, font=FONT, relief="flat",
                                        wrap="word", padx=14, pady=12)
        txt.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        guide = """应用宝引擎没有 Root 时，主流做法是替换引擎的系统镜像 system.vhd
（已在其他机器上验证的社区方案，来源：酷安 @米粉钉子户1999，2025-10）。

镜像位置：
  应用宝安装目录\\Androws\\Image\\<版本号>\\system.vhd
  例如 E:\\Program Files\\Tencent\\Androws\\Image\\5.10.7900.2936\\system.vhd
  「Image」下可能有多个版本目录，要选当前正在用的那个版本。

大致流程（细节以原教程为准）：
1. 完全退出应用宝（托盘图标也要退出），确认 Androws* 进程已结束。
2. 备份 system.vhd（复制一份改名 system.vhd.bak，出问题直接还原）。
3. 用作者提供的 qemu dd 工具，从 system.vhd 里提取 boot。
4. 在应用宝里打开 Magisk，用「安装 → 选择并修补一个文件」修补这个 boot。
5. 把修补产物重命名为 2.boot_a，交给「应用宝root.bat」生成新的 system.vhd。
6. 用新 system.vhd 替换原来的 system.vhd，重新启动应用宝，引擎即带 Magisk。

风险与注意：
· 只替换 system.vhd，不要动其他镜像；版本不对可能开不了机。
· 改之前一定备份；失败就还原备份再启动。
· 替换后 Root 由镜像自带，本工具箱会直接识别为「已 Root」，模块管理即可用。

原教程链接（可复制到浏览器打开）：
""" + self.ROOT_GUIDE_URL + """

工具箱能帮你做的：定位并打开 system.vhd 目录、结束引擎进程、验证替换后是否 Root 成功。
"""
        txt.insert("1.0", guide)
        txt.configure(state="disabled")

        btns = tk.Frame(top, bg=BG)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        self.button(btns, "打开 system.vhd 目录", self.open_engine_image_dir, "primary").pack(side="left")
        self.button(btns, "复制教程链接", self.copy_root_guide_url).pack(side="left", padx=8)
        self.button(btns, "关闭", top.destroy).pack(side="right")

    def copy_root_guide_url(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.ROOT_GUIDE_URL)
            self.set_status("教程链接已复制到剪贴板")
        except Exception as e:
            messagebox.showwarning("复制失败", str(e), parent=self.root)

    def open_engine_image_dir(self):
        dirs = find_engine_image_dirs()
        if not dirs:
            messagebox.showinfo(
                "未找到 system.vhd",
                "没有在常见安装路径下找到 Androws\\Image\\<版本>\\system.vhd。\n\n"
                "可以手动定位：打开应用宝安装目录 → Androws → Image → 当前版本号文件夹。",
                parent=self.root)
            return
        target = dirs[0]
        try:
            os.startfile(str(target))
            self.set_status(f"已打开引擎镜像目录：{target}")
            if hasattr(self, "diag_text"):
                self.diag_write(f"引擎镜像目录：{target}")
        except Exception as e:
            messagebox.showwarning("打开失败", str(e), parent=self.root)

    # ======================================================================
    # 应用管理
    # ======================================================================
    def build_apps(self):
        page = self.new_page("apps")
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)

        head = tk.Frame(page, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="已安装应用", bg=BG, fg=TEXT, font=FONT_BD).pack(side="left")
        self.app_count_label = tk.Label(head, text="", bg=BG, fg=MUTED, font=FONT_SM)
        self.app_count_label.pack(side="left", padx=10)

        filter_row = tk.Frame(page, bg=BG)
        filter_row.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        tk.Label(filter_row, text="搜索", bg=BG, fg=MUTED, font=FONT_SM).pack(side="left")
        self.app_search = tk.StringVar()
        self.app_search.trace_add("write", lambda *_: self._filter_apps())
        e = self.entry(filter_row, self.app_search, width=24)
        e.pack(side="left", ipady=4, padx=(6, 12))
        tk.Label(filter_row, text="类型", bg=BG, fg=MUTED, font=FONT_SM).pack(side="left")
        self.app_scope = tk.StringVar(value="第三方")
        cb = ttk.Combobox(filter_row, textvariable=self.app_scope, values=["第三方", "系统", "全部"],
                          state="readonly", width=8, font=FONT)
        cb.pack(side="left", padx=(6, 12))
        cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh_apps(force=True))
        self.button(filter_row, "刷新", lambda: self.refresh_apps(force=True)).pack(side="left")
        self.button(filter_row, "安装 APK", self.install_apk_dialog, "primary").pack(side="left", padx=8)
        self.button(filter_row, "导出 APK", self.export_selected_apk).pack(side="left")

        tools = tk.Frame(page, bg=BG)
        tools.grid(row=2, column=0, sticky="nsew")
        tools.rowconfigure(0, weight=1)
        tools.columnconfigure(0, weight=1)

        cols = ("pkg", "ver", "type", "state", "path")
        self.app_tree = ttk.Treeview(tools, columns=cols, show="headings", selectmode="browse")
        for c, t, w, anchor in (("pkg", "包名", 340, "w"), ("ver", "版本", 110, "w"),
                                ("type", "类型", 80, "w"), ("state", "状态", 80, "w"),
                                ("path", "APK 路径", 380, "w")):
            self.app_tree.heading(c, text=t, anchor=anchor)
            self.app_tree.column(c, width=w, anchor=anchor, stretch=(c == "path"))
        sb = ttk.Scrollbar(tools, orient="vertical", command=self.app_tree.yview)
        self.app_tree.configure(yscrollcommand=sb.set)
        self.app_tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.app_tree.bind("<Double-1>", lambda _e: self.launch_app())

        actions = tk.Frame(page, bg=BG)
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for text, cmd, kind in (("启动", self.launch_app, "primary"),
                                ("停止", self.force_stop_app, "ghost"),
                                ("清除数据", self.clear_app_data, "ghost"),
                                ("卸载", self.uninstall_app, "danger"),
                                ("禁用 / 启用", self.toggle_app, "ghost"),
                                ("权限管理", self.app_permissions, "ghost"),
                                ("应用详情", self.app_details, "ghost")):
            self.button(actions, text, cmd, kind).pack(side="left", padx=(0, 8))

    def refresh_apps(self, force=False):
        if not self.adb.ready():
            self.set_status("未找到 adb，无法读取应用列表")
            return
        if self.adb.state() != "device":
            self.set_status("引擎未连接，先点击顶部“连接引擎”")
            return
        scope = self.app_scope.get() if hasattr(self, "app_scope") else "第三方"
        self.set_status("正在读取应用列表…")

        def work(emit):
            flags = []
            if scope == "第三方":
                flags = ["-3"]
            elif scope == "系统":
                flags = ["-s"]
            out = self.adb.shell("pm list packages --show-versioncode " + " ".join(flags), timeout=60)
            disabled = set()
            try:
                dout = self.adb.shell("pm list packages -d " + " ".join(flags), timeout=60)
                disabled = {l.split(":", 1)[1].strip() for l in dout.splitlines() if l.startswith("package:")}
            except Exception:
                pass
            rows = []
            for line in out.splitlines():
                m = re.match(r"package:(\S+?)(?:\s+versionCode:(\d+))?$", line.strip())
                if not m:
                    continue
                pkg, ver = m.group(1), m.group(2) or ""
                if scope == "第三方":
                    typ = "第三方"
                elif scope == "系统":
                    typ = "系统"
                else:
                    typ = "系统" if self._is_probably_system(pkg) else "第三方"
                rows.append({
                    "pkg": pkg,
                    "ver": ver,
                    "type": typ,
                    "state": "已禁用" if pkg in disabled else "已启用",
                    "path": "",
                })
            rows.sort(key=lambda r: r["pkg"])
            return rows

        def done(rows, err):
            if err:
                self.set_status(f"读取应用失败：{err}")
                return
            self.apps = rows or []
            self._populate_apps()
            self.set_status(f"共 {len(self.apps)} 个应用")

        self.bg(work, done)

    @staticmethod
    def _is_probably_system(pkg: str) -> bool:
        return pkg.startswith(("com.android.", "android.", "com.google.android.", "com.qualcomm."))

    def _populate_apps(self):
        self.app_tree.delete(*self.app_tree.get_children())
        kw = (self.app_search.get().strip().lower() if hasattr(self, "app_search") else "")
        shown = 0
        for row in self.apps:
            if kw and kw not in row["pkg"].lower():
                continue
            self.app_tree.insert("", "end", values=(row["pkg"], row["ver"], row["type"],
                                                    row["state"], row["path"]))
            shown += 1
        self.app_count_label.configure(text=f"显示 {shown} / 共 {len(self.apps)}")

    def _filter_apps(self):
        self._populate_apps()

    def selected_pkg(self, action: str) -> str | None:
        sel = self.app_tree.selection()
        if not sel:
            messagebox.showinfo("提示", f"请先在列表中选择要{action}的应用", parent=self.root)
            return None
        return self.app_tree.item(sel[0], "values")[0]

    def launch_app(self):
        pkg = self.selected_pkg("启动")
        if not pkg:
            return
        def work(emit):
            out = self.adb.shell(f"cmd package resolve-activity --brief {pkg} | tail -n 1", timeout=30)
            comp = ""
            for line in out.splitlines():
                if "/" in line:
                    comp = line.strip()
            if comp and "No activity found" not in comp:
                return self.adb.shell(f"am start -n {comp}", timeout=40)
            return self.adb.shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1", timeout=40)
        self.bg(work, lambda r, e: self.set_status(f"已启动 {pkg}" if not e else str(e)))

    def force_stop_app(self):
        pkg = self.selected_pkg("停止")
        if not pkg:
            return
        self.bg(lambda emit: self.adb.shell(f"am force-stop {pkg}", timeout=30),
                lambda r, e: self.set_status(f"已停止 {pkg}" if not e else str(e)))

    def clear_app_data(self):
        pkg = self.selected_pkg("清除数据")
        if not pkg:
            return
        if not messagebox.askyesno("确认", f"确定清除 {pkg} 的全部数据？", parent=self.root):
            return
        self.bg(lambda emit: self.adb.shell(f"pm clear {pkg}", timeout=40),
                lambda r, e: self.set_status(f"已清除 {pkg} 数据" if not e else str(e)))

    def uninstall_app(self):
        pkg = self.selected_pkg("卸载")
        if not pkg:
            return
        if not messagebox.askyesno("确认卸载", f"确定卸载 {pkg}？", parent=self.root):
            return

        def work(emit):
            try:
                return self.adb.run(["uninstall", pkg], timeout=120)
            except AdbError:
                return self.adb.shell(f"pm uninstall --user 0 {pkg}", root=True, timeout=120)

        def done(r, e):
            self.set_status(f"已卸载 {pkg}" if not e else f"卸载失败：{e}")
            self.refresh_apps(force=True)
        self.bg(work, done)

    def toggle_app(self):
        pkg = self.selected_pkg("禁用 / 启用")
        if not pkg:
            return
        row = next((r for r in self.apps if r["pkg"] == pkg), None)
        disable = bool(row and row["state"] == "已启用")
        cmd = f"pm disable-user --user 0 {pkg}" if disable else f"pm enable {pkg}"

        def done(r, e):
            self.set_status(("已禁用 " if disable else "已启用 ") + pkg if not e else str(e))
            self.refresh_apps(force=True)
        self.bg(lambda emit: self.adb.shell(cmd, timeout=40), done)

    def export_selected_apk(self):
        pkg = self.selected_pkg("导出")
        if not pkg:
            return
        folder = filedialog.askdirectory(title="选择导出目录", initialdir=str(APP_DIR))
        if not folder:
            return

        def work(emit):
            out = self.adb.shell(f"pm path {pkg}", timeout=30)
            paths = [l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("package:")]
            if not paths:
                raise AdbError("未获取到 APK 路径")
            saved = []
            for i, remote in enumerate(paths):
                suffix = "" if i == 0 else f"_{i}"
                local = Path(folder) / f"{pkg}{suffix}.apk"
                self.adb.run(["pull", remote, str(local)], timeout=300)
                saved.append(str(local))
            return saved

        def done(saved, err):
            if err:
                self.set_status(f"导出失败：{err}")
                return
            messagebox.showinfo("导出完成", "\n".join(saved), parent=self.root)
            self.set_status(f"已导出 {len(saved)} 个文件")
        self.bg(work, done)

    def app_permissions(self):
        pkg = self.selected_pkg("管理权限")
        if not pkg:
            return

        def work(emit):
            out = self.adb.shell(f"dumpsys package {pkg}", timeout=40)
            perms = []
            in_runtime = False
            for line in out.splitlines():
                if "runtime permissions:" in line:
                    in_runtime = True
                    continue
                if in_runtime:
                    if line.strip() and not line.startswith("      "):
                        break
                    m = re.match(r"\s+(android\.permission\.[A-Z_0-9]+): granted=(true|false)", line)
                    if m:
                        perms.append((m.group(1), m.group(2) == "true"))
            return perms

        def done(perms, err):
            if err:
                self.set_status(str(err))
                return
            if not perms:
                messagebox.showinfo("权限", "该应用没有可切换的运行时权限", parent=self.root)
                return
            self._perm_dialog(pkg, perms)
        self.bg(work, done)

    def _perm_dialog(self, pkg: str, perms: list[tuple[str, bool]]):
        top = tk.Toplevel(self.root)
        top.title(f"权限管理 · {pkg}")
        top.geometry("640x480")
        top.configure(bg=BG)
        tk.Label(top, text=pkg, bg=BG, fg=MUTED, font=FONT_SM).pack(anchor="w", padx=14, pady=(12, 6))
        tree = ttk.Treeview(top, columns=("perm", "granted"), show="headings", selectmode="browse")
        tree.heading("perm", text="权限", anchor="w")
        tree.heading("granted", text="状态", anchor="w")
        tree.column("perm", width=460, anchor="w")
        tree.column("granted", width=120, anchor="w")
        tree.pack(fill="both", expand=True, padx=12, pady=6)
        for p, g in perms:
            tree.insert("", "end", values=(p, "已允许" if g else "已拒绝"))

        def set_grant(value: bool):
            sel = tree.selection()
            if not sel:
                return
            perm = tree.item(sel[0], "values")[0]

            def done(r, e):
                self.set_status(f"{'授予' if value else '撤销'} {perm}" if not e else str(e))
                if not e:
                    tree.item(sel[0], values=(perm, "已允许" if value else "已拒绝"))
            self.bg(lambda emit: self.adb.shell(
                f"pm {'grant' if value else 'revoke'} {pkg} {perm}", timeout=40), done)

        btns = tk.Frame(top, bg=BG)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        self.button(btns, "允许选中", lambda: set_grant(True), "success").pack(side="left")
        self.button(btns, "撤销选中", lambda: set_grant(False), "danger").pack(side="left", padx=8)
        self.button(btns, "关闭", top.destroy).pack(side="right")

    def app_details(self):
        pkg = self.selected_pkg("查看")
        if not pkg:
            return

        def done(out, err):
            if err:
                self.set_status(str(err))
                return
            lines = out.splitlines()
            keep = []
            for line in lines:
                s = line.strip()
                if any(s.startswith(k) for k in ("versionName", "versionCode", "codePath",
                                                 "firstInstallTime", "lastUpdateTime", "installerPackageName",
                                                 "dataDir", "flags=", "privateFlags",
                                                 "User 0:", "installed=", "enabled=", "stopped=", "hidden=")):
                    keep.append(s)
            top = tk.Toplevel(self.root)
            top.title(f"应用详情 · {pkg}")
            top.geometry("720x520")
            top.configure(bg=BG)
            txt = scrolledtext.ScrolledText(top, bg="#0c1015", fg=TEXT, font=MONO, relief="flat",
                                            wrap="none")
            txt.pack(fill="both", expand=True, padx=12, pady=12)
            txt.insert("1.0", "\n".join(keep) if keep else out)
            txt.configure(state="disabled")
            self.button(top, "关闭", top.destroy, "primary").pack(pady=(0, 12))
        self.bg(lambda emit: self.adb.shell(f"dumpsys package {pkg}", timeout=40), done)

    # ======================================================================
    # 安装 APK
    # ======================================================================
    def install_apk_dialog(self):
        files = filedialog.askopenfilenames(
            title="选择 APK（可多选）",
            filetypes=[("Android 安装包", "*.apk"), ("所有文件", "*.*")],
        )
        if not files:
            return
        self.install_apks(list(files))

    def install_apks(self, files: list[str]):
        self.set_status(f"正在安装 {len(files)} 个 APK…")

        def work(emit):
            ok, fail = [], []
            for f in files:
                emit("log", f"[{now_str()}] 安装 {Path(f).name}")
                try:
                    out = self.adb.run(["install", "-r", "-d", "-g", f], timeout=600)
                    if "Success" in out:
                        ok.append(f)
                        emit("log", f"  成功：{Path(f).name}")
                    else:
                        fail.append((f, out.strip().splitlines()[-1] if out.strip() else "未知错误"))
                        emit("log", f"  失败：{Path(f).name} - {out.strip()}")
                except Exception as e:
                    fail.append((f, str(e)))
                    emit("log", f"  失败：{Path(f).name} - {e}")
            return ok, fail

        def done(res, err):
            if err:
                self.set_status(str(err))
                return
            ok, fail = res
            self.set_status(f"安装完成：成功 {len(ok)}，失败 {len(fail)}")
            if fail:
                messagebox.showwarning("部分安装失败",
                                       "\n".join(f"{Path(f).name}: {m}" for f, m in fail)[:2000],
                                       parent=self.root)
            self.refresh_apps(force=True)
        self.bg(work, done)

    # ======================================================================
    # MicroG
    # ======================================================================
    def build_microg(self):
        page = self.new_page("microg")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)

        head = tk.Frame(page, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="MicroG 一键安装与修复", bg=BG, fg=TEXT, font=FONT_BD).pack(side="left")
        tk.Label(head, text="为应用宝引擎提供 Google 服务替代方案（需签名伪装）",
                 bg=BG, fg=MUTED, font=FONT_SM).pack(side="left", padx=12)

        stat_card, stat_inner = self.card(page, "组件状态")
        stat_card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.microg_status = {}
        stat_row = tk.Frame(stat_inner, bg=CARD)
        stat_row.pack(fill="x")
        for i, (key, title) in enumerate((("gms", "microG Services"), ("vending", "microG Companion"),
                                           ("fakegapps", "签名伪装 FakeGApps"), ("lsposed", "LSPosed"))):
            cell = tk.Frame(stat_row, bg=CARD)
            cell.grid(row=0, column=i, sticky="w", padx=(0, 30))
            tk.Label(cell, text=title, bg=CARD, fg=MUTED, font=FONT_SM).pack(anchor="w")
            v = tk.Label(cell, text="检测中…", bg=CARD, fg=TEXT, font=FONT_BD)
            v.pack(anchor="w", pady=(2, 0))
            self.microg_status[key] = v

        opt_card, opt_inner = self.card(page, "安装选项")
        opt_card.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.mg_uninstall = tk.BooleanVar(value=self.cfg.get("microg_uninstall_conflict", True))
        self.mg_grant = tk.BooleanVar(value=self.cfg.get("microg_grant", True))
        self.mg_fakegapps = tk.BooleanVar(value=self.cfg.get("microg_fakegapps", True))
        self.mg_force = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_inner, text="签名冲突时自动备份并卸载已有 GMS（官方 Google 服务必须卸载）",
                        variable=self.mg_uninstall).pack(anchor="w")
        ttk.Checkbutton(opt_inner, text="安装后自动授予运行时权限、加入电池优化白名单",
                        variable=self.mg_grant).pack(anchor="w", pady=2)
        ttk.Checkbutton(opt_inner, text="未检测到签名伪装时安装 FakeGApps（需在 LSPosed 中启用）",
                        variable=self.mg_fakegapps).pack(anchor="w")
        ttk.Checkbutton(opt_inner, text="强制重新下载（忽略缓存安装包）",
                        variable=self.mg_force).pack(anchor="w", pady=2)

        row = tk.Frame(opt_inner, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        self.button(row, "一键安装 / 修复 MicroG", self.microg_install, "success").pack(side="left")
        self.button(row, "仅安装本地 APK", self.microg_local).pack(side="left", padx=8)
        self.button(row, "重新检测", self.refresh_microg).pack(side="left")
        self.button(row, "打开 MicroG 设置", self.open_microg_settings).pack(side="left", padx=8)
        self.button(row, "打开 LSPosed", self.open_lsposed).pack(side="left")

        log_card, log_inner = self.card(page, "安装日志")
        log_card.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        log_body = tk.Frame(log_inner, bg=CARD)
        log_body.pack(fill="both", expand=True)
        log_body.rowconfigure(1, weight=1)
        log_body.columnconfigure(0, weight=1)
        self.microg_bar = ttk.Progressbar(log_body, mode="determinate", maximum=100)
        self.microg_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.microg_text = scrolledtext.ScrolledText(log_body, bg="#0c1015", fg="#c3cbd8",
                                                    insertbackground=TEXT, relief="flat",
                                                    font=("Consolas", 9), wrap="word", height=8)
        self.microg_text.grid(row=1, column=0, sticky="nsew")

        note = tk.Label(
            page,
            text="说明：microG 需要在系统层面允许「签名伪装」，常见实现是 Magisk + LSPosed + FakeGApps。"
                 "若组件状态里显示未启用，请打开 LSPosed 勾选 FakeGApps 并作用到「系统框架」，然后重启引擎。",
            bg=BG, fg=MUTED, font=FONT_SM, justify="left", wraplength=1050,
        )
        note.grid(row=4, column=0, sticky="w", pady=(8, 0))

        self.root.after(1200, self.refresh_microg)

    def microg_log_write(self, text: str):
        if not hasattr(self, "microg_text"):
            return
        self.microg_text.insert("end", text.rstrip() + "\n")
        self.microg_text.see("end")

    def microg_oneclick_page(self):
        self.show_page("microg")
        self.root.after(200, self.microg_install)

    def refresh_microg(self):
        if not self.adb.ready() or not self.adb.serial:
            return

        def work(emit):
            res = {}
            for key, pkg in (("gms", "com.google.android.gms"), ("vending", "com.android.vending"),
                             ("fakegapps", "inc.whew.android.fakegapps"), ("lsposed", "org.lsposed.manager")):
                try:
                    out = self.adb.shell(f"dumpsys package {pkg} | grep versionName", timeout=30)
                    res[key] = parse_version(out)
                except Exception:
                    res[key] = ""
            # 签名伪装检测：查找 FAKE_PACKAGE_SIGNATURE 授权信息
            try:
                out = self.adb.shell(
                    "dumpsys package com.google.android.gms | grep -i 'FAKE_PACKAGE_SIGNATURE: granted'", timeout=30)
                res["spoof"] = "granted" in out
            except Exception:
                res["spoof"] = False
            return res

        def done(res, err):
            if err or not res:
                return
            spoof = res.get("spoof", False)
            for key in ("gms", "vending", "fakegapps", "lsposed"):
                lab = self.microg_status[key]
                ver = res.get(key, "")
                text = f"已安装 {ver}" if ver else "未安装"
                if key == "gms" and ver and spoof:
                    text += " · 签名伪装正常"
                lab.configure(text=text, fg=GREEN if ver else MUTED)
            self.microg_spoof_ok = spoof
        self.bg(work, done)

    def _fetch_release(self, api: str, cache_name: str, emit) -> dict:
        cache = CACHE_DIR / cache_name
        try:
            emit("microg_log", f"读取 {api} …")
            req = urllib.request.Request(api, headers={"User-Agent": "YYB-Toolbox/1.0",
                                                       "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read().decode("utf-8"))
            cache.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
            return data
        except Exception as e:
            emit("microg_log", f"在线查询失败：{e}，尝试使用本地缓存")
            if cache.exists():
                return json.loads(cache.read_text("utf-8"))
            raise

    def _download(self, url: str, dest: Path, emit, label: str):
        if dest.exists() and not getattr(self, "_mg_force", False):
            emit("microg_log", f"使用缓存：{dest.name}（{dest.stat().st_size/1048576:.1f} MB）")
            return dest
        emit("microg_log", f"下载 {label} …")
        req = urllib.request.Request(url, headers={"User-Agent": "YYB-Toolbox/1.0"})
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done * 100 / total
                        emit("microg_progress", pct, f"{label} {done/1048576:.1f}/{total/1048576:.1f} MB")
        tmp.replace(dest)
        emit("microg_log", f"下载完成：{dest.name}（{dest.stat().st_size/1048576:.1f} MB）")
        return dest

    def _pick_asset(self, release: dict, prefix: str, exclude_suffixes=(".asc", ".sha256")) -> dict | None:
        for a in release.get("assets", []):
            name = a.get("name", "")
            if name.startswith(prefix) and not name.endswith(exclude_suffixes):
                if "hw" in name:  # 优先选择通用版本而非 hw 版本
                    continue
                return a
        return None

    def microg_install(self):
        if not self.adb.ready():
            messagebox.showerror("缺少 adb", "请先设置 adb.exe 路径", parent=self.root)
            return
        if not messagebox.askyesno(
                "一键安装 MicroG",
                "将执行：\n"
                "1. 检查已有 GMS（签名冲突时备份并卸载）\n"
                "2. 下载最新 microG Services / Companion\n"
                "3. 安装两个 APK 并自动授权\n"
                "4. 加入电池优化白名单\n"
                "5. 检查 / 安装签名伪装组件\n\n"
                "安装 microG 会替换引擎内的 Google 服务，可能影响依赖官方 GMS 的应用，是否继续？",
                parent=self.root):
            return

        self.microg_text.delete("1.0", "end")
        self.microg_bar["value"] = 0
        opts = {
            "uninstall": self.mg_uninstall.get(),
            "grant": self.mg_grant.get(),
            "fakegapps": self.mg_fakegapps.get(),
            "force": self.mg_force.get(),
        }
        self._mg_force = opts["force"]

        def work(emit):
            emit("microg_log", f"[{now_str()}] 开始安装 MicroG")
            # 1. 现有 GMS
            out = self.adb.shell("dumpsys package com.google.android.gms | grep versionName", timeout=30)
            existing = parse_version(out)
            is_microg = existing.startswith("0.3.")
            emit("microg_log", f"现有 GMS：{existing or '无'}" + ("（已是 microG）" if is_microg else ""))

            release = self._fetch_release(MICROG_API, "microg_release.json", emit)
            tag = release.get("tag_name", "?")
            latest = tag.lstrip("v")
            emit("microg_log", f"最新 microG 版本：{tag}")
            skip_install = bool(is_microg and existing == latest and not opts["force"])
            if skip_install:
                emit("microg_log", "当前已是该版本，跳过下载与安装（仅执行权限与伪装检查）")
            else:
                gms_asset = self._pick_asset(release, "com.google.android.gms")
                vend_asset = self._pick_asset(release, "com.android.vending")
                if not gms_asset or not vend_asset:
                    raise AdbError("未找到 microG APK 资源")

                gms_apk = CACHE_DIR / gms_asset["name"]
                vend_apk = CACHE_DIR / vend_asset["name"]
                self._download(gms_asset["browser_download_url"], gms_apk, emit, "microG Services")
                self._download(vend_asset["browser_download_url"], vend_apk, emit, "microG Companion")

                # 2. 冲突处理
                if existing and not is_microg:
                    if not opts["uninstall"]:
                        raise AdbError("检测到不是 microG 的 GMS，请勾选“签名冲突时自动卸载”或手动卸载后重试")
                    emit("microg_log", "备份现有 GMS 到 cache/backup_gms.apk …")
                    try:
                        p = self.adb.shell("pm path com.google.android.gms", timeout=30)
                        remote = [l.split(":", 1)[1] for l in p.splitlines() if l.startswith("package:")][0]
                        self.adb.run(["pull", remote, str(CACHE_DIR / "backup_gms.apk")], timeout=300)
                    except Exception as e:
                        emit("microg_log", f"备份失败（继续）：{e}")
                    emit("microg_log", "卸载现有 com.google.android.gms …")
                    try:
                        self.adb.run(["uninstall", "com.google.android.gms"], timeout=120)
                    except Exception:
                        self.adb.shell("pm uninstall --user 0 com.google.android.gms", root=True, timeout=120)

                # 3. 安装
                for apk, label in ((gms_apk, "microG Services"), (vend_apk, "microG Companion")):
                    emit("microg_log", f"安装 {label} …")
                    out = self.adb.run(["install", "-r", "-d", "-g", str(apk)], timeout=900)
                    emit("microg_log", "  " + out.replace("\n", " ")[:160])
                    if "Success" not in out and "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out:
                        emit("microg_log", "签名冲突，卸载旧包后重试 …")
                        self.adb.run(["uninstall", "com.google.android.gms"], timeout=120)
                        out = self.adb.run(["install", "-r", "-d", "-g", str(apk)], timeout=900)
                        emit("microg_log", "  " + out.replace("\n", " ")[:160])

            # 4. 授权 / 白名单
            if opts["grant"]:
                emit("microg_log", "授予运行时权限 …")
                perms = [
                    "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION", "ACCESS_BACKGROUND_LOCATION",
                    "READ_CONTACTS", "WRITE_CONTACTS", "GET_ACCOUNTS", "READ_CALENDAR", "WRITE_CALENDAR",
                    "READ_PHONE_STATE", "READ_SMS", "RECEIVE_SMS", "BODY_SENSORS",
                    "ACTIVITY_RECOGNITION", "POST_NOTIFICATIONS", "RECORD_AUDIO", "CAMERA",
                    "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE",
                ]
                for perm in perms:
                    try:
                        self.adb.shell(f"pm grant com.google.android.gms android.permission.{perm}", timeout=20)
                    except Exception:
                        pass
                for perm in ("POST_NOTIFICATIONS", "READ_PHONE_STATE", "GET_ACCOUNTS"):
                    try:
                        self.adb.shell(f"pm grant com.android.vending android.permission.{perm}", timeout=20)
                    except Exception:
                        pass
                try:
                    self.adb.shell("dumpsys deviceidle whitelist +com.google.android.gms", timeout=20)
                    self.adb.shell("dumpsys deviceidle whitelist +com.android.vending", timeout=20)
                    self.adb.shell("cmd appops set com.google.android.gms RUN_ANY_IN_BACKGROUND allow", timeout=20)
                    self.adb.shell("cmd appops set com.google.android.gms WAKE_LOCK allow", timeout=20)
                except Exception:
                    pass
                emit("microg_log", "权限与电池白名单已处理")

            # 5. 签名伪装
            fact = self.adb.shell("dumpsys package inc.whew.android.fakegapps | grep versionName", timeout=30)
            has_fake = bool(parse_version(fact))
            emit("microg_log", "签名伪装 FakeGApps：" + ("已安装" if has_fake else "未安装"))
            if not has_fake and opts["fakegapps"]:
                try:
                    rel = self._fetch_release(FAKEGAPPS_API, "fakegapps_release.json", emit)
                    asset = self._pick_asset(rel, "app-release")
                    if not asset:
                        raise AdbError("未找到 FakeGApps APK")
                    apk = CACHE_DIR / "FakeGApps.apk"
                    self._download(asset["browser_download_url"], apk, emit, "FakeGApps")
                    out = self.adb.run(["install", "-r", "-d", str(apk)], timeout=300)
                    emit("microg_log", "  " + out.strip())
                except Exception as e:
                    emit("microg_log", f"FakeGApps 安装失败：{e}")

            emit("microg_log", "完成。若伪装未生效，请在 LSPosed 中启用 FakeGApps 并作用到系统框架，然后重启引擎。")
            return tag

        def done(res, err):
            self.microg_bar["value"] = 100 if not err else 0
            if err:
                self.microg_log_write(f"[{now_str()}] 失败：{err}")
                messagebox.showwarning("MicroG 安装失败", str(err), parent=self.root)
            else:
                messagebox.showinfo("MicroG", f"安装完成（{res}）。\n建议重启引擎后打开 MicroG 设置运行自检。",
                                    parent=self.root)
            self.refresh_microg()
            self.refresh_apps(force=True)

        self.bg(work, done)

    def microg_local(self):
        gms = filedialog.askopenfilename(title="选择 microG Services APK (com.google.android.gms)",
                                         filetypes=[("APK", "*.apk")])
        if not gms:
            return
        vend = filedialog.askopenfilename(title="选择 microG Companion APK (com.android.vending)",
                                          filetypes=[("APK", "*.apk")])
        files = [f for f in (gms, vend) if f]

        def work(emit):
            results = []
            for f in files:
                out = self.adb.run(["install", "-r", "-d", "-g", f], timeout=600)
                results.append((f, out))
            return results

        def done(res, err):
            if err:
                messagebox.showwarning("安装失败", str(err), parent=self.root)
                return
            messagebox.showinfo("安装结果", "\n\n".join(f"{Path(f).name}: {o}" for f, o in res)[:1500],
                                parent=self.root)
            self.refresh_microg()
        self.bg(work, done)

    def open_microg_settings(self):
        def work(emit):
            return self.adb.shell(
                "am start -n com.google.android.gms/org.microg.gms.ui.SettingsActivity", timeout=40)

        def done(r, e):
            self.set_status("已打开 MicroG 设置" if not e else str(e))
        self.bg(work, done)

    def open_lsposed(self):
        def work(emit):
            return self.adb.shell(
                "monkey -p org.lsposed.manager -c android.intent.category.LAUNCHER 1", timeout=40)

        def done(r, e):
            self.set_status("已打开 LSPosed" if not e else f"打开失败：{e}")
        self.bg(work, done)

    # ======================================================================
    # Root / Magisk
    # ======================================================================
    def build_root(self):
        page = self.new_page("root")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)

        head = tk.Frame(page, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="Root 与 Magisk", bg=BG, fg=TEXT, font=FONT_BD).pack(side="left")
        tk.Label(head, text="引擎已 Root 时可管理模块、执行 root 命令",
                 bg=BG, fg=MUTED, font=FONT_SM).pack(side="left", padx=12)
        self.button(head, "刷新状态", self.refresh_root).pack(side="right")

        stat_card, stat_inner = self.card(page, "Root 状态")
        stat_card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.root_stat = {}
        stat_row = tk.Frame(stat_inner, bg=CARD)
        stat_row.pack(fill="x")
        for i, (key, title) in enumerate((("su", "Root / su"), ("magisk", "Magisk"),
                                           ("zygisk", "Zygisk / LSPosed"), ("selinux", "SELinux"),
                                           ("modules", "模块数量"))):
            cell = tk.Frame(stat_row, bg=CARD)
            cell.grid(row=0, column=i, sticky="w", padx=(0, 32))
            tk.Label(cell, text=title, bg=CARD, fg=MUTED, font=FONT_SM).pack(anchor="w")
            v = tk.Label(cell, text="—", bg=CARD, fg=TEXT, font=FONT_BD)
            v.pack(anchor="w", pady=(2, 0))
            self.root_stat[key] = v

        ops, ops_inner = self.card(page, "Root 工具")
        ops.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        r1 = tk.Frame(ops_inner, bg=CARD)
        r1.pack(fill="x")
        self.button(r1, "Root Shell", self.open_root_shell, "danger").pack(side="left")
        self.button(r1, "安装 Magisk 模块", self.install_magisk_module, "primary").pack(side="left", padx=8)
        self.button(r1, "打开 Magisk", self.open_magisk).pack(side="left")
        self.button(r1, "挂载 /system 读写", self.remount_rw).pack(side="left", padx=8)
        self.button(r1, "SELinux 状态", self.show_selinux).pack(side="left")
        r2 = tk.Frame(ops_inner, bg=CARD)
        r2.pack(fill="x", pady=(8, 0))
        self.button(r2, "一键授权常见权限(su)", self.grant_su).pack(side="left")
        self.button(r2, "清理 Magisk 模块标记", self.remove_module_flags).pack(side="left", padx=8)
        self.button(r2, "Zygisk 说明", self.show_zygisk_help).pack(side="left")
        self.button(r2, "未 Root？刷入方案", self.show_root_guide, "success").pack(side="left", padx=8)
        self.button(r2, "装模块自带 APK", self.install_bundled_apk).pack(side="left")

        mods_card, mods_inner = self.card(page, "Magisk 模块")
        mods_card.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        mods_body = tk.Frame(mods_inner, bg=CARD)
        mods_body.pack(fill="both", expand=True)
        mods_body.rowconfigure(1, weight=1)
        mods_body.columnconfigure(0, weight=1)
        bar = tk.Frame(mods_body, bg=CARD)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.button(bar, "启用选中", lambda: self.toggle_module(True), "success").pack(side="left")
        self.button(bar, "禁用选中", lambda: self.toggle_module(False)).pack(side="left", padx=8)
        self.button(bar, "删除选中", lambda: self.delete_module(), "danger").pack(side="left")
        cols = ("id", "name", "ver", "state", "desc")
        self.mod_tree = ttk.Treeview(mods_body, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("id", "模块 ID", 180), ("name", "名称", 220), ("ver", "版本", 190),
                        ("state", "状态", 80), ("desc", "说明", 500)):
            self.mod_tree.heading(c, text=t, anchor="w")
            self.mod_tree.column(c, width=w, anchor="w", stretch=(c == "desc"))
        sb = ttk.Scrollbar(mods_body, orient="vertical", command=self.mod_tree.yview)
        self.mod_tree.configure(yscrollcommand=sb.set)
        self.mod_tree.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")

    def refresh_root(self):
        if not self.adb.ready() or self.adb.state() != "device":
            return

        def work(emit):
            res = {"root": False, "magisk": "", "zygisk": "", "selinux": "", "modules": 0}
            try:
                res["root"] = "uid=0" in self.adb.shell("id", root=True, timeout=20)
            except Exception:
                pass
            if res["root"]:
                try:
                    res["magisk"] = self.adb.shell("magisk -v", root=True, timeout=20).strip()
                except Exception:
                    pass
                try:
                    out = self.adb.shell("ls /data/adb/modules", root=True, timeout=20)
                    res["modules"] = len([l for l in out.splitlines() if l.strip()])
                except Exception:
                    pass
                try:
                    z = self.adb.shell("ls -d /data/adb/modules/zygisk_lsposed /data/adb/modules/zygisksu 2>/dev/null",
                                       root=True, timeout=20)
                    res["zygisk"] = "LSPosed 已装" if "lsposed" in z else ("Zygisk 已装" if "zygisksu" in z else "")
                except Exception:
                    pass
            try:
                res["selinux"] = self.adb.shell("getenforce", timeout=10).strip()
            except Exception:
                pass
            mods = self.list_modules()
            res["module_rows"] = mods
            return res

        def done(res, err):
            if err or not res:
                return
            self.root_stat["su"].configure(text="已 Root" if res["root"] else "未 Root",
                                           fg=GREEN if res["root"] else RED)
            self.root_stat["magisk"].configure(text=res["magisk"] or "—")
            self.root_stat["zygisk"].configure(text=res["zygisk"] or "—")
            self.root_stat["selinux"].configure(text=res["selinux"] or "—")
            self.root_stat["modules"].configure(text=str(res["modules"]))
            self.module_rows = res.get("module_rows", [])
            self.mod_tree.delete(*self.mod_tree.get_children())
            for m in self.module_rows:
                self.mod_tree.insert("", "end", values=(m["id"], m["name"], m["version"],
                                                        m["state"], m["desc"]))
        self.bg(work, done)

    def list_modules(self) -> list[dict]:
        if not self.adb.ready():
            return []
        try:
            out = self.adb.shell(
                'for d in /data/adb/modules/*/; do echo "MOD|$d"; cat "$d/module.prop" 2>/dev/null; '
                'if [ -f "$d/disable" ]; then echo "STATE|disabled"; '
                'elif [ -f "$d/remove" ]; then echo "STATE|remove"; else echo "STATE|enabled"; fi; done',
                root=True, timeout=60)
        except Exception:
            return []
        mods, cur = [], None
        for line in out.splitlines():
            if line.startswith("MOD|"):
                if cur:
                    mods.append(cur)
                path = line[4:].strip().rstrip("/")
                cur = {"path": path, "id": Path(path).name, "name": Path(path).name,
                       "version": "", "desc": "", "state": "未知"}
            elif line.startswith("STATE|") and cur:
                v = line.split("|", 1)[1].strip()
                cur["state"] = {"disabled": "已禁用", "remove": "待移除", "enabled": "已启用"}.get(v, v)
            elif cur is not None and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "name":
                    cur["name"] = v.strip()
                elif k.strip() == "version":
                    cur["version"] = v.strip()
                elif k.strip() == "description":
                    cur["desc"] = v.strip()[:120]
        if cur:
            mods.append(cur)
        mods.sort(key=lambda m: m["id"].lower())
        return mods

    def selected_module(self, action: str) -> dict | None:
        sel = self.mod_tree.selection()
        if not sel:
            messagebox.showinfo("提示", f"请先选择要{action}的模块", parent=self.root)
            return None
        mid = self.mod_tree.item(sel[0], "values")[0]
        return next((m for m in self.module_rows if m["id"] == mid), None)

    def toggle_module(self, enable: bool):
        mod = self.selected_module("启用" if enable else "禁用")
        if not mod:
            return
        cmd = (f"rm -f {mod['path']}/disable {mod['path']}/remove" if enable
               else f"touch {mod['path']}/disable")

        def done(r, e):
            self.set_status(("已启用 " if enable else "已禁用 ") + mod["id"] + "（重启引擎后生效）"
                            if not e else str(e))
            self.refresh_root()
        self.bg(lambda emit: self.adb.shell(cmd, root=True, timeout=30), done)

    def delete_module(self):
        mod = self.selected_module("删除")
        if not mod:
            return
        if not messagebox.askyesno("删除模块", f"确定删除模块 {mod['name']}（{mod['id']}）？\n"
                                               "建议先禁用并重启引擎，确认无问题后再删除。",
                                   parent=self.root):
            return
        self.bg(lambda emit: self.adb.shell(f"rm -rf {mod['path']}", root=True, timeout=30),
                lambda r, e: (self.set_status("已删除模块" if not e else str(e)), self.refresh_root()))

    def _module_bundled_apks(self, zip_path: str) -> list[dict]:
        """列出 Magisk 模块 zip 内自带的 APK（LSPosed/Vector 的 manager.apk 等）。"""
        import zipfile
        rows = []
        try:
            with zipfile.ZipFile(zip_path) as z:
                for name in z.namelist():
                    if not name.lower().endswith(".apk"):
                        continue
                    if "daemon" in Path(name).name.lower():  # LSPosed 的内部服务，不是用户可装的 APK
                        continue
                    info = z.getinfo(name)
                    if info.file_size < 10000:  # 忽略占位/空文件
                        continue
                    rows.append({"entry": name, "name": Path(name).name, "size": info.file_size})
        except Exception:
            return []
        # manager.apk 排前面
        rows.sort(key=lambda r: (0 if "manager" in r["name"].lower() else 1, r["name"]))
        return rows

    def _extract_module_apks(self, zip_path: str, rows: list[dict]) -> list[dict]:
        import zipfile
        out = []
        dest_dir = CACHE_DIR / "module_apk"
        dest_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            for r in rows:
                dest = dest_dir / r["name"]
                with z.open(r["entry"]) as src, open(dest, "wb") as f:
                    shutil.copyfileobj(src, f)
                out.append({"local": str(dest), "name": r["name"], "size": r["size"]})
        return out

    def install_bundled_apk(self):
        """只安装模块 zip 里的管理器 APK（不刷模块）。"""
        path = filedialog.askopenfilename(title="选择模块 zip（从中提取 manager.apk）",
                                          filetypes=[("Magisk 模块", "*.zip"), ("APK", "*.apk")])
        if not path:
            return
        if path.lower().endswith(".apk"):
            apks = [{"local": path, "name": Path(path).name, "size": Path(path).stat().st_size}]
        else:
            rows = self._module_bundled_apks(path)
            if not rows:
                messagebox.showinfo("没有 APK", "这个 zip 里没有找到 APK（例如 LSPosed 的 manager.apk）。",
                                    parent=self.root)
                return
            try:
                apks = self._extract_module_apks(path, rows)
            except Exception as e:
                messagebox.showerror("解压失败", str(e), parent=self.root)
                return

        def work(emit):
            res = []
            for apk in apks:
                rpath = "/data/local/tmp/" + apk["name"]
                emit("log", f"[{now_str()}] 安装 {apk['name']}")
                self.adb.run(["push", apk["local"], rpath], timeout=300)
                try:
                    out = self.adb.run(["install", "-r", "-d", "-g", rpath], timeout=600)
                except Exception as e:
                    out = str(e)
                res.append((apk["name"], out))
            return res

        def done(res, err):
            if err:
                messagebox.showwarning("安装失败", str(err), parent=self.root)
                return
            lines = [f"· {n}：{'成功' if 'Success' in o else o.strip()[:120]}" for n, o in res]
            messagebox.showinfo("安装结果", "\n".join(lines) + "\n\nLSPosed 管理器装好后，重启引擎即可打开。",
                                parent=self.root)
        self.set_status("正在安装模块自带 APK…")
        self.bg(work, done)

    def install_magisk_module(self):
        path = filedialog.askopenfilename(title="选择 Magisk 模块 (.zip)",
                                          filetypes=[("Magisk 模块", "*.zip")])
        if not path:
            return

        bundled = self._module_bundled_apks(path)
        apk_paths = []
        if bundled:
            names = "、".join(f"{r['name']}（{r['size']/1048576:.1f} MB）" for r in bundled[:5])
            tip = ""
            if any("manager" in r["name"].lower() for r in bundled):
                tip = ("\n\n检测到 manager.apk：LSPosed / Vector 的管理器就放在模块 zip 里，"
                       "只刷模块不装它就没有界面管理模块。")
            if not messagebox.askyesno(
                    "模块内自带 APK",
                    f"这个模块 zip 里还包含：\n{names}\n{tip}\n\n刷入模块后顺便安装这些 APK 吗？",
                    parent=self.root):
                bundled = []
            else:
                try:
                    apk_paths = self._extract_module_apks(path, bundled)
                except Exception as e:
                    messagebox.showwarning("解压失败", str(e), parent=self.root)
                    apk_paths = []

        self.set_status("正在安装 Magisk 模块…")

        def work(emit):
            remote = "/data/local/tmp/" + Path(path).name
            emit("log", f"[{now_str()}] 推送模块到 {remote}")
            self.adb.run(["push", path, remote], timeout=300)
            out = self.adb.shell(f"magisk --install-module {remote}", root=True, timeout=300)
            apk_out = []
            for apk in apk_paths:
                rpath = "/data/local/tmp/" + apk["name"]
                emit("log", f"[{now_str()}] 安装模块自带 APK：{apk['name']}")
                self.adb.run(["push", apk["local"], rpath], timeout=300)
                try:
                    res = self.adb.run(["install", "-r", "-d", "-g", rpath], timeout=600)
                except Exception as e:
                    res = str(e)
                apk_out.append((apk["name"], res))
            return out, apk_out

        def done(res, err):
            if err:
                messagebox.showwarning("安装失败", str(err), parent=self.root)
                return
            out, apk_out = res
            msg = f"模块安装输出：\n{out}\n"
            if apk_out:
                msg += "\n自带 APK 安装结果：\n"
                for name, r in apk_out:
                    ok = "Success" in r
                    msg += f"· {name}：{'成功' if ok else r.strip()[:120]}\n"
                msg += "\n重启引擎后生效。LSPosed 激活后可在管理器里勾选模块作用域。"
            else:
                msg += "\n重启引擎后生效。"
            messagebox.showinfo("Magisk 模块", msg, parent=self.root)
            self.refresh_root()
        self.bg(work, done)

    def open_root_shell(self):
        self.show_page("shell")
        self.shell_root_var.set(True)
        self.root.after(100, lambda: self.shell_input.focus_set())
        self.append_shell("已切换到 Root 模式\n", "info")

    def open_magisk(self):
        def work(emit):
            return self.adb.shell(
                "monkey -p com.topjohnwu.magisk -c android.intent.category.LAUNCHER 1", timeout=40)
        self.bg(work, lambda r, e: self.set_status("已打开 Magisk" if not e else str(e)))

    def remount_rw(self):
        def work(emit):
            emit("log", f"[{now_str()}] 尝试挂载 /system 读写")
            results = []
            for cmd in ("mount -o rw,remount /", "mount -o rw,remount /system",
                        "mount -o rw,remount -t erofs /system"):
                try:
                    results.append((cmd, self.adb.shell(cmd, root=True, timeout=30)))
                except Exception as e:
                    results.append((cmd, str(e)))
            mount = self.adb.shell("mount | grep -E ' /system | /vendor '", root=True, timeout=20)
            return "\n".join(f"{c} → {r}" for c, r in results) + "\n" + mount

        def done(out, err):
            if err:
                messagebox.showwarning("挂载失败", str(err), parent=self.root)
                return
            messagebox.showinfo("挂载结果", out[:1500], parent=self.root)
        self.bg(work, done)

    def show_selinux(self):
        def work(emit):
            return self.adb.shell("getenforce; getprop ro.boot.selinux; ls -Z /system/bin/sh", root=True, timeout=20)

        def done(out, err):
            messagebox.showinfo("SELinux", out or str(err), parent=self.root)
        self.bg(work, done)

    def grant_su(self):
        if not messagebox.askyesno("Root 授权", "将对常见系统目录与命令授予 su 访问（root 已可用时无需重复）。\n继续？",
                                   parent=self.root):
            return

        def work(emit):
            cmds = [
                "id",
                "magisk --sqlite \"select * from policies\"",
                "settings put global adb_enabled 1",
            ]
            out = []
            for c in cmds:
                try:
                    out.append(f"$ {c}\n{self.adb.shell(c, root=True, timeout=30)}")
                except Exception as e:
                    out.append(f"$ {c}\n{e}")
            return "\n\n".join(out)

        def done(out, err):
            if err:
                messagebox.showwarning("失败", str(err), parent=self.root)
                return
            messagebox.showinfo("Root 检查", out[:2000], parent=self.root)
        self.bg(work, done)

    def remove_module_flags(self):
        def work(emit):
            self.adb.shell("for d in /data/adb/modules/*/; do rm -f \"$d/remove\"; done", root=True, timeout=30)
            return "已清理所有 remove 标记"

        def done(out, err):
            self.set_status(out if not err else str(err))
            self.refresh_root()
        self.bg(work, done)

    def show_zygisk_help(self):
        messagebox.showinfo(
            "Zygisk / LSPosed",
            "应用宝引擎为 x86_64 Android 13，可使用 Magisk + Zygisk Next + LSPosed。\n\n"
            "1. 在 Magisk 中确认 Zygisk 已启用（或安装 Zygisk Next 模块）。\n"
            "2. LSPosed 模块安装后重启引擎，LSPosed 管理器会出现在应用列表。\n"
            "3. microG 的签名伪装由 FakeGApps（LSPosed 模块）提供：\n"
            "   打开 LSPosed → 模块 → 启用 FakeGApps → 作用域勾选「系统框架」。\n"
            "4. 修改模块作用域后需重启引擎生效。",
            parent=self.root)

    # ======================================================================
    # 终端
    # ======================================================================
    def build_shell(self):
        page = self.new_page("shell")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        head = tk.Frame(page, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="Shell 终端", bg=BG, fg=TEXT, font=FONT_BD).pack(side="left")
        tk.Label(head, text="命令在引擎内执行，输出实时回显", bg=BG, fg=MUTED, font=FONT_SM).pack(side="left", padx=12)
        self.shell_root_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(head, text="以 Root 执行 (su)", variable=self.shell_root_var).pack(side="right")
        self.button(head, "清空", lambda: self.shell_text.delete("1.0", "end")).pack(side="right", padx=8)

        body = tk.Frame(page, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.shell_text = scrolledtext.ScrolledText(body, bg="#0b0f14", fg="#cfd6e2",
                                                   insertbackground=TEXT, relief="flat",
                                                   font=("Consolas", 10), wrap="word")
        self.shell_text.grid(row=0, column=0, sticky="nsew")
        self.shell_text.tag_config("cmd", foreground="#7dd3fc")
        self.shell_text.tag_config("err", foreground="#f87171")
        self.shell_text.tag_config("info", foreground="#9ca3af")

        inp = tk.Frame(page, bg=BG)
        inp.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        inp.columnconfigure(0, weight=1)
        self.shell_var = tk.StringVar()
        self.shell_input = self.entry(inp, self.shell_var)
        self.shell_input.grid(row=0, column=0, sticky="ew", ipady=6, padx=(0, 8))
        self.shell_input.bind("<Return>", lambda _e: self.run_shell())
        self.button(inp, "执行", self.run_shell, "primary").grid(row=0, column=1)

        quick = tk.Frame(page, bg=BG)
        quick.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        tk.Label(quick, text="快捷命令", bg=BG, fg=MUTED, font=FONT_SM).pack(side="left", padx=(0, 8))
        for text, cmd in (("设备信息", "getprop | head -40"),
                          ("应用列表", "pm list packages -3"),
                          ("电池", "dumpsys battery"),
                          ("进程", "ps -A | head -30"),
                          ("存储", "df -h /data"),
                          ("网络", "ip addr show")):
            self.button(quick, text, lambda c=cmd: (self.shell_var.set(c), self.run_shell()),
                        font=FONT_SM, pady=3).pack(side="left", padx=(0, 6))

    def append_shell(self, text: str, tag: str | None = None):
        self.shell_text.insert("end", text, tag or ())
        self.shell_text.see("end")

    def run_shell(self):
        cmd = self.shell_var.get().strip()
        if not cmd:
            return
        root = self.shell_root_var.get()
        self.append_shell(f"{'#' if root else '$'} {cmd}\n", "cmd")
        self.shell_var.set("")

        def work(emit):
            return self.adb.shell(cmd, root=root, timeout=120)

        def done(out, err):
            if err:
                self.append_shell(str(err) + "\n", "err")
            else:
                self.append_shell((out or "(无输出)") + "\n", None)
            if int(self.shell_text.index("end-1c").split(".")[0]) > 3000:
                self.shell_text.delete("1.0", "500.0")
        self.bg(work, done)

    # ======================================================================
    # Logcat
    # ======================================================================
    def build_logcat(self):
        page = self.new_page("logcat")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)

        head = tk.Frame(page, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="Logcat", bg=BG, fg=TEXT, font=FONT_BD).pack(side="left")
        tk.Label(head, text="实时抓取引擎日志", bg=BG, fg=MUTED, font=FONT_SM).pack(side="left", padx=12)
        self.log_btn = self.button(head, "开始抓取", self.start_logcat, "primary")
        self.log_btn.pack(side="left")
        self.button(head, "暂停 / 继续", self.toggle_logcat_pause).pack(side="left", padx=8)
        self.button(head, "清空", lambda: self.log_text.delete("1.0", "end")).pack(side="left")
        self.button(head, "保存", self.save_log).pack(side="left", padx=8)
        self.button(head, "停止", self.stop_logcat, "danger").pack(side="left")

        filt = tk.Frame(page, bg=BG)
        filt.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        tk.Label(filt, text="级别", bg=BG, fg=MUTED, font=FONT_SM).pack(side="left")
        self.log_level = tk.StringVar(value="全部")
        cb = ttk.Combobox(filt, textvariable=self.log_level, values=["全部", "V", "D", "I", "W", "E"],
                          state="readonly", width=6, font=FONT)
        cb.pack(side="left", padx=(6, 14))
        tk.Label(filt, text="关键字", bg=BG, fg=MUTED, font=FONT_SM).pack(side="left")
        self.log_kw = tk.StringVar()
        e = self.entry(filt, self.log_kw, width=26)
        e.pack(side="left", ipady=4, padx=(6, 12))
        self.log_kw.trace_add("write", lambda *_: setattr(self, "logcat_filter", self.log_kw.get()))
        tk.Label(filt, text="Tag", bg=BG, fg=MUTED, font=FONT_SM).pack(side="left")
        self.log_tag = tk.StringVar()
        e2 = self.entry(filt, self.log_tag, width=18)
        e2.pack(side="left", ipady=4, padx=(6, 0))

        self.log_text = scrolledtext.ScrolledText(page, bg="#0b0f14", fg="#c8d1df", relief="flat",
                                                  font=("Consolas", 9), wrap="none")
        self.log_text.grid(row=2, column=0, sticky="nsew")
        self.log_text.tag_config("E", foreground="#f87171")
        self.log_text.tag_config("W", foreground="#fbbf24")
        self.log_text.tag_config("I", foreground="#93c5fd")

    def start_logcat(self):
        if self.logcat_proc:
            self.set_status("日志已在抓取中")
            return
        self.set_status("正在启动 logcat…")
        tag = self.log_tag.get().strip()
        threading.Thread(target=self._logcat_runner, args=(tag,), daemon=True).start()

    def _logcat_runner(self, tag: str):
        args = [self.adb.exe, "-s", self.adb.serial, "logcat", "-v", "time"]
        if tag:
            args += ["-s", f"{tag}:V"]
        try:
            self.logcat_proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1, creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            self.uiq.put(("status", (f"启动 logcat 失败：{e}",)))
            return
        self.uiq.put(("status", ("日志抓取中…",)))
        while True:
            line = self.logcat_proc.stdout.readline()
            if not line:
                break
            self.logcat_lines.put(line.rstrip("\n"))
        self.uiq.put(("status", ("logcat 已结束",)))
        self.logcat_proc = None

    def toggle_logcat_pause(self):
        self.logcat_paused = not self.logcat_paused
        self.set_status("日志已暂停（后台继续缓存）" if self.logcat_paused else "日志继续")

    def stop_logcat(self):
        if self.logcat_proc:
            self.logcat_proc.terminate()
            self.logcat_proc = None
            self.set_status("已停止 logcat")

    def _pump_logcat(self):
        if not hasattr(self, "log_text"):
            return
        level = self.log_level.get()
        kw = self.logcat_filter.lower()
        added = 0
        while added < 300:
            try:
                line = self.logcat_lines.get_nowait()
            except queue.Empty:
                break
            if self.logcat_paused:
                continue
            if kw and kw not in line.lower():
                continue
            m = re.search(r"\s([VDIWE])/", line)
            lv = m.group(1) if m else "V"
            if level != "全部":
                order = "VDIWE"
                if order.index(lv) < order.index(level):
                    continue
            self.log_text.insert("end", line + "\n", lv if lv in ("E", "W", "I") else ())
            added += 1
        if added:
            self.log_text.see("end")
            total = int(self.log_text.index("end-1c").split(".")[0])
            if total > 8000:
                self.log_text.delete("1.0", f"{total-7000}.0")
        self.root.after(120, self._pump_logcat)

    def save_log(self):
        path = filedialog.asksaveasfilename(title="保存日志", defaultextension=".txt",
                                            filetypes=[("文本", "*.txt"), ("日志", "*.log")],
                                            initialdir=str(APP_DIR))
        if not path:
            return
        Path(path).write_text(self.log_text.get("1.0", "end"), "utf-8")
        self.set_status(f"日志已保存：{path}")

    # ======================================================================
    # 文件
    # ======================================================================
    def build_files(self):
        page = self.new_page("files")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)

        head = tk.Frame(page, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="引擎文件", bg=BG, fg=TEXT, font=FONT_BD).pack(side="left")
        self.file_path_var = tk.StringVar(value=self.current_dir)
        e = self.entry(head, self.file_path_var, width=46)
        e.pack(side="left", ipady=5, padx=(12, 8))
        e.bind("<Return>", lambda _e: self.load_dir())
        self.button(head, "前往", self.load_dir, "primary").pack(side="left")
        self.button(head, "上级", self.go_up).pack(side="left", padx=8)
        self.button(head, "刷新", self.load_dir).pack(side="left")
        ttk.Checkbutton(head, text="Root 浏览", variable=self.file_root_mode,
                        command=self.load_dir).pack(side="left", padx=10)

        cols = ("name", "type", "size", "perm", "mtime")
        self.file_tree = ttk.Treeview(page, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("name", "名称", 400), ("type", "类型", 80), ("size", "大小", 110),
                        ("perm", "权限", 130), ("mtime", "修改时间", 160)):
            self.file_tree.heading(c, text=t, anchor="w")
            self.file_tree.column(c, width=w, anchor="w", stretch=(c == "name"))
        self.file_tree.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        self.file_tree.bind("<Double-1>", lambda _e: self.open_file_item())
        sb = ttk.Scrollbar(page, orient="vertical", command=self.file_tree.yview)
        sb.grid(row=2, column=1, sticky="ns", pady=(10, 0))
        self.file_tree.configure(yscrollcommand=sb.set)

        bar = tk.Frame(page, bg=BG)
        bar.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.button(bar, "上传到设备", self.push_file, "primary").pack(side="left")
        self.button(bar, "下载到电脑", self.pull_file).pack(side="left", padx=8)
        self.button(bar, "新建文件夹", self.mkdir_device).pack(side="left")
        self.button(bar, "删除", self.delete_device_file, "danger").pack(side="left", padx=8)
        self.button(bar, "打开本地保存目录", lambda: os.startfile(str(APP_DIR))).pack(side="left")

        self.root.after(800, self.load_dir)

    def _ls(self, path: str, root_mode: bool = False) -> list[dict]:
        path = "/" if path == "/" else path.rstrip("/") + "/"
        out = self.adb.shell(f'ls -la "{path}"', root=root_mode, timeout=60)
        rows = []
        for line in out.splitlines():
            line = line.rstrip()
            if not line or line.startswith("total"):
                continue
            parts = line.split(None, 7)
            if len(parts) < 8:
                parts = line.split()
                if len(parts) < 8:
                    continue
            perm, links, owner, group, size, date1, date2, name = parts[0], parts[1], parts[2], parts[3], \
                parts[4], parts[5], parts[6], parts[7]
            if name in (".", ".."):
                continue
            if " -> " in name:
                name = name.split(" -> ")[0]
            is_dir = perm.startswith("d")
            rows.append({"name": name, "is_dir": is_dir,
                         "type": "目录" if is_dir else ("链接" if perm.startswith("l") else "文件"),
                         "size": size, "perm": perm, "mtime": f"{date1} {date2}"})
        rows.sort(key=lambda r: (not r["is_dir"], r["name"].lower()))
        return rows

    def load_dir(self):
        if not self.adb.ready() or self.adb.state() != "device":
            self.set_status("引擎未连接，无法浏览文件")
            return
        path = self.file_path_var.get().strip() or "/sdcard"
        root_mode = self.file_root_mode.get()
        self.set_status(f"读取 {path} …")

        def work(emit):
            return self._ls(path, root_mode)

        def done(rows, err):
            if err:
                self.set_status(f"读取失败：{err}")
                return
            self.current_dir = path
            self.file_tree.delete(*self.file_tree.get_children())
            for r in rows:
                self.file_tree.insert("", "end", values=(r["name"], r["type"], r["size"],
                                                        r["perm"], r["mtime"]))
            self.set_status(f"{path} · {len(rows)} 项")
        self.bg(work, done)

    def go_up(self):
        cur = self.file_path_var.get().strip() or "/sdcard"
        parent = str(Path(cur).parent) if cur not in ("/", "") else "/"
        if not parent:
            parent = "/"
        self.file_path_var.set(parent)
        self.load_dir()

    def open_file_item(self):
        sel = self.file_tree.selection()
        if not sel:
            return
        name, typ = self.file_tree.item(sel[0], "values")[:2]
        path = self.file_path_var.get().strip().rstrip("/") + "/" + name
        if typ == "目录":
            self.file_path_var.set(path)
            self.load_dir()
        else:
            self.pull_file()

    def selected_remote_path(self) -> str | None:
        sel = self.file_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一个文件或文件夹", parent=self.root)
            return None
        name = self.file_tree.item(sel[0], "values")[0]
        return self.file_path_var.get().strip().rstrip("/") + "/" + name

    def push_file(self):
        files = filedialog.askopenfilenames(title="选择要上传的文件")
        if not files:
            return
        dest_dir = self.file_path_var.get().strip()

        def work(emit):
            outs = []
            for f in files:
                outs.append(self.adb.run(["push", f, dest_dir], timeout=600))
            return outs

        def done(outs, err):
            self.set_status(f"已上传 {len(outs)} 个文件" if not err else str(err))
            self.load_dir()
        self.bg(work, done)

    def pull_file(self):
        remote = self.selected_remote_path()
        if not remote:
            return
        local = filedialog.asksaveasfilename(title="保存到", initialdir=str(APP_DIR),
                                             initialfile=Path(remote).name)
        if not local:
            return

        def work(emit):
            return self.adb.run(["pull", remote, local], timeout=600)

        def done(out, err):
            self.set_status(f"已下载：{local}" if not err else f"下载失败：{err}")
        self.bg(work, done)

    def mkdir_device(self):
        name = simpledialog.askstring("新建文件夹", "文件夹名称：", parent=self.root)
        if not name:
            return
        path = self.file_path_var.get().strip().rstrip("/") + "/" + name
        root_mode = self.file_root_mode.get()

        def done(r, e):
            self.set_status(f"已创建 {path}" if not e else str(e))
            self.load_dir()
        self.bg(lambda emit: self.adb.shell(f'mkdir -p "{path}"', root=root_mode, timeout=30), done)

    def delete_device_file(self):
        remote = self.selected_remote_path()
        if not remote:
            return
        if not messagebox.askyesno("删除", f"确定删除 {remote}？", parent=self.root):
            return
        root_mode = self.file_root_mode.get()

        def done(r, e):
            self.set_status("已删除" if not e else str(e))
            self.load_dir()
        self.bg(lambda emit: self.adb.shell(f'rm -rf "{remote}"', root=root_mode, timeout=60), done)

    # ======================================================================
    # 截图 / 录屏
    # ======================================================================
    def build_shot(self):
        page = self.new_page("shot")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        head = tk.Frame(page, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="截图 / 录屏", bg=BG, fg=TEXT, font=FONT_BD).pack(side="left")
        self.button(head, "截图", self.take_screenshot, "primary").pack(side="left", padx=12)
        self.button(head, "保存图片", self.save_screenshot).pack(side="left")
        self.button(head, "打开截图目录", lambda: os.startfile(str(SHOT_DIR))).pack(side="left", padx=8)
        self.auto_shot_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(head, text="每 2 秒自动刷新", variable=self.auto_shot_var,
                        command=self.toggle_auto_shot).pack(side="left", padx=12)
        self.button(head, "录制 15 秒", lambda: self.screen_record(15)).pack(side="left")
        self.button(head, "录制 60 秒", lambda: self.screen_record(60)).pack(side="left", padx=8)

        self.shot_label = tk.Label(page, text="点击「截图」获取引擎画面", bg="#0b0f14", fg=MUTED,
                                   font=FONT, highlightbackground=BORDER, highlightthickness=1)
        self.shot_label.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.shot_info = tk.Label(page, text="", bg=BG, fg=MUTED, font=FONT_SM)
        self.shot_info.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.auto_job = None

    def take_screenshot(self):
        if not self.adb.ready():
            return
        self.set_status("正在截图…")

        def work(emit):
            data = self.adb.exec_out(["screencap", "-p"], timeout=60)
            if not data.startswith(b"\x89PNG"):
                raise AdbError("截图失败：返回数据不是 PNG")
            path = SHOT_DIR / f"shot_{time.strftime('%Y%m%d_%H%M%S')}.png"
            path.write_bytes(data)
            return path

        def done(path, err):
            if err:
                self.set_status(f"截图失败：{err}")
                return
            self._shot_loaded(path)
            self.set_status(f"已截图：{path.name}")
        self.bg(work, done)

    def _shot_loaded(self, path):
        try:
            self.last_shot = Path(path)
            img = tk.PhotoImage(file=str(path))
            w, h = img.width(), img.height()
            label_w = max(600, self.shot_label.winfo_width() - 10)
            label_h = max(400, self.shot_label.winfo_height() - 10)
            factor = max(1, -(-w // label_w), -(-h // label_h))
            if factor > 1:
                img = img.subsample(factor, factor)
            elif w * 2 < label_w and h * 2 < label_h:
                # 引擎分辨率较小时放大预览
                factor = -min(label_w // w, label_h // h, 3)
                img = img.zoom(-factor)
            self.shot_img = img
            self.shot_label.configure(image=img, text="")
            if path:
                if factor < 0:
                    scale = f"放大 {-factor} 倍"
                elif factor > 1:
                    scale = f"缩小 1/{factor}"
                else:
                    scale = "原尺寸"
                self.shot_info.configure(text=f"{Path(path).name} · 原始 {w}x{h} · {scale}")
        except Exception as e:
            self.shot_label.configure(text=f"图片加载失败：{e}", image="")

    def save_screenshot(self):
        if not self.shot_img:
            messagebox.showinfo("提示", "请先截图", parent=self.root)
            return
        path = filedialog.asksaveasfilename(title="保存截图", defaultextension=".png",
                                            filetypes=[("PNG", "*.png")], initialdir=str(SHOT_DIR))
        if not path:
            return
        # tk.PhotoImage 不能直接另存，改用最近一次截图文件
        src = getattr(self, "last_shot", None)
        if src and Path(src).exists():
            shutil.copy2(src, path)
            self.set_status(f"已保存：{path}")

    def toggle_auto_shot(self):
        if self.auto_shot_var.get():
            self._auto_loop()
        else:
            if self.auto_job:
                self.root.after_cancel(self.auto_job)
                self.auto_job = None

    def _auto_loop(self):
        if not self.auto_shot_var.get():
            return
        self.take_screenshot()
        self.auto_job = self.root.after(2000, self._auto_loop)

    def screen_record(self, seconds: int):
        remote = "/sdcard/yyb_record.mp4"
        self.set_status(f"开始录制 {seconds} 秒…")

        def work(emit):
            self.adb.shell(f"screenrecord --time-limit {seconds} --bit-rate 8000000 {remote}",
                           timeout=seconds + 30)
            return remote

        def done(remote_path, err):
            if err:
                self.set_status(f"录屏失败：{err}")
                return

            def pull(emit2):
                local = SHOT_DIR / f"record_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
                self.adb.run(["pull", remote_path, str(local)], timeout=300)
                return local

            def pulled(local, e2):
                if e2:
                    self.set_status(f"拉取录屏失败：{e2}")
                else:
                    self.set_status(f"录屏已保存：{local}")
                    messagebox.showinfo("录屏完成", str(local), parent=self.root)
            self.bg(pull, pulled)
        self.bg(work, done)

    # ======================================================================
    # 系统设置
    # ======================================================================
    def build_settings(self):
        page = self.new_page("settings")
        page.columnconfigure(0, weight=1)

        disp, disp_inner = self.card(page, "显示设置")
        disp.grid(row=0, column=0, sticky="ew")
        r1 = tk.Frame(disp_inner, bg=CARD)
        r1.pack(fill="x", pady=4)
        tk.Label(r1, text="分辨率", bg=CARD, fg=MUTED, font=FONT_SM, width=8, anchor="w").pack(side="left")
        self.res_var = tk.StringVar(value="1280x720")
        cb = ttk.Combobox(r1, textvariable=self.res_var, state="readonly", width=14, font=FONT,
                          values=["480x320", "960x540", "1280x720", "1600x900", "1920x1080", "2560x1440"])
        cb.pack(side="left", padx=(0, 8))
        self.button(r1, "应用", lambda: self.apply_wm("size"), "primary").pack(side="left")
        self.button(r1, "重置", lambda: self.reset_wm("size")).pack(side="left", padx=6)

        r2 = tk.Frame(disp_inner, bg=CARD)
        r2.pack(fill="x", pady=4)
        tk.Label(r2, text="DPI", bg=CARD, fg=MUTED, font=FONT_SM, width=8, anchor="w").pack(side="left")
        self.dpi_var = tk.StringVar(value="160")
        cb2 = ttk.Combobox(r2, textvariable=self.dpi_var, state="readonly", width=14, font=FONT,
                           values=["120", "160", "200", "240", "260", "280", "320", "400"])
        cb2.pack(side="left", padx=(0, 8))
        self.button(r2, "应用", lambda: self.apply_wm("density"), "primary").pack(side="left")
        self.button(r2, "重置", lambda: self.reset_wm("density")).pack(side="left", padx=6)

        r3 = tk.Frame(disp_inner, bg=CARD)
        r3.pack(fill="x", pady=4)
        tk.Label(r3, text="旋转", bg=CARD, fg=MUTED, font=FONT_SM, width=8, anchor="w").pack(side="left")
        for deg in (0, 90, 180, 270):
            self.button(r3, f"{deg}°", lambda d=deg: self.set_rotation(d), font=FONT_SM, pady=3).pack(
                side="left", padx=(0, 6))

        r4 = tk.Frame(disp_inner, bg=CARD)
        r4.pack(fill="x", pady=(6, 2))
        tk.Label(r4, text="动画", bg=CARD, fg=MUTED, font=FONT_SM, width=8, anchor="w").pack(side="left")
        self.button(r4, "关闭动画", lambda: self.set_anim(0), font=FONT_SM, pady=3).pack(side="left")
        self.button(r4, "0.5x", lambda: self.set_anim(0.5), font=FONT_SM, pady=3).pack(side="left", padx=6)
        self.button(r4, "1x", lambda: self.set_anim(1.0), font=FONT_SM, pady=3).pack(side="left")
        self.button(r4, "保持唤醒", self.keep_awake, font=FONT_SM, pady=3).pack(side="left", padx=12)

        info, info_inner = self.card(page, "其他设置")
        info.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        r5 = tk.Frame(info_inner, bg=CARD)
        r5.pack(fill="x")
        self.button(r5, "打开系统设置", lambda: self.open_android_settings("settings")).pack(side="left")
        self.button(r5, "打开开发者选项", lambda: self.open_android_settings(
            "com.android.settings/.Settings$DevelopmentSettingsActivity")).pack(side="left", padx=8)
        self.button(r5, "查看已安装用户", lambda: self.shell_popup("pm list users")).pack(side="left")
        self.button(r5, "查看当前 Activity", lambda: self.shell_popup(
            "dumpsys activity activities | grep -m3 mResumedActivity")).pack(side="left", padx=8)
        self.button(r5, "输入文本", self.input_text).pack(side="left")

        note = tk.Label(
            page,
            text="提示：应用宝引擎分辨率被应用宝自身缩放控制，修改 wm size/density 可能只影响部分界面，"
                 "重启引擎后会恢复默认。建议优先在应用宝「设置 - 性能」中调整。",
            bg=BG, fg=MUTED, font=FONT_SM, justify="left", wraplength=1000)
        note.grid(row=2, column=0, sticky="w", pady=(10, 0))

    def apply_wm(self, kind: str):
        val = self.res_var.get() if kind == "size" else self.dpi_var.get()
        cmd = f"wm size {val}" if kind == "size" else f"wm density {val}"
        self.bg(lambda emit: self.adb.shell(cmd, timeout=30),
                lambda r, e: (self.set_status(f"{'分辨率' if kind=='size' else 'DPI'} 已设为 {val}"
                                             if not e else str(e)), self.refresh_all()))

    def reset_wm(self, kind: str):
        cmd = "wm size reset" if kind == "size" else "wm density reset"
        self.bg(lambda emit: self.adb.shell(cmd, timeout=30),
                lambda r, e: (self.set_status("已恢复默认" if not e else str(e)), self.refresh_all()))

    def set_rotation(self, deg: int):
        cmd = (f"settings put system accelerometer_rotation 0; "
               f"settings put system user_rotation {deg // 90}")
        self.bg(lambda emit: self.adb.shell(cmd, timeout=30),
                lambda r, e: self.set_status(f"已旋转到 {deg}°" if not e else str(e)))

    def set_anim(self, scale: float):
        cmd = (f"settings put global window_animation_scale {scale}; "
               f"settings put global transition_animation_scale {scale}; "
               f"settings put global animator_duration_scale {scale}")
        self.bg(lambda emit: self.adb.shell(cmd, timeout=30),
                lambda r, e: self.set_status(f"动画缩放已设为 {scale}x" if not e else str(e)))

    def keep_awake(self):
        self.bg(lambda emit: self.adb.shell("svc power stayon true", timeout=30),
                lambda r, e: self.set_status("已开启保持唤醒" if not e else str(e)))

    def open_android_settings(self, which: str):
        cmd = (f"am start -a android.settings.SETTINGS" if which == "settings"
               else f"am start -n {which}")
        self.bg(lambda emit: self.adb.shell(cmd, timeout=30),
                lambda r, e: self.set_status("已打开设置页" if not e else str(e)))

    def shell_popup(self, cmd: str):
        def work(emit):
            return self.adb.shell(cmd, timeout=40)

        def done(out, err):
            messagebox.showinfo("结果", (out or str(err))[:2000], parent=self.root)
        self.bg(work, done)

    def input_text(self):
        from tkinter import simpledialog
        text = simpledialog.askstring("输入文本", "输入要发送到引擎的文本：", parent=self.root)
        if text is None:
            return
        escaped = text.replace(" ", "%s")
        self.bg(lambda emit: self.adb.shell(f'input text "{escaped}"', timeout=30),
                lambda r, e: self.set_status("已发送文本" if not e else str(e)))

    # ======================================================================
    # 诊断与维护
    # ======================================================================
    def build_diag(self):
        page = self.new_page("diag")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        head = tk.Frame(page, bg=BG)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="诊断与维护", bg=BG, fg=TEXT, font=FONT_BD).pack(side="left")
        self.button(head, "运行全面诊断", self.run_diag, "primary").pack(side="right")
        self.button(head, "重新连接", self.connect).pack(side="right", padx=8)
        self.button(head, "重启 adb server", self.restart_adb).pack(side="right")
        self.button(head, "自动安装 adb", lambda: self.install_adb()).pack(side="right", padx=8)

        self.diag_text = scrolledtext.ScrolledText(page, bg="#0c1015", fg="#c3cbd8", relief="flat",
                                                   font=("Consolas", 9), wrap="word")
        self.diag_text.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        bar = tk.Frame(page, bg=BG)
        bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.button(bar, "启动应用宝", self.start_store, "primary").pack(side="left")
        self.button(bar, "结束引擎进程", self.kill_engine, "danger").pack(side="left", padx=8)
        self.button(bar, "查看端口 5555", self.check_port).pack(side="left", padx=8)
        self.button(bar, "查看引擎进程", self.check_process).pack(side="left")
        self.button(bar, "查看 adb 版本", self.show_adb_version).pack(side="left", padx=8)
        self.button(bar, "开发者模式指引", self.show_dev_guide).pack(side="left")
        self.button(bar, "打开 system.vhd 目录", self.open_engine_image_dir).pack(side="left", padx=8)
        self.button(bar, "未 Root 刷入指引", self.show_root_guide).pack(side="left")

    def diag_write(self, text: str):
        self.diag_text.insert("end", text.rstrip() + "\n")
        self.diag_text.see("end")

    def run_diag(self):
        self.diag_text.delete("1.0", "end")

        def work(emit):
            lines = []
            lines.append(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"adb 路径：{self.adb.exe or '未找到'}")
            if self.adb.ready():
                try:
                    lines.append("adb 版本：" + self.adb.run(["version"], timeout=20).replace("\n", " | "))
                except Exception as e:
                    lines.append(f"adb 版本检测失败：{e}")
            try:
                lines.append("设备列表：")
                for d in self.adb.devices():
                    lines.append(f"  - {d['serial']} [{d['state']}] {d.get('product','')} {d.get('model','')}")
            except Exception as e:
                lines.append(f"设备检测失败：{e}")
            try:
                lines.append("引擎状态：" + self.adb.state())
            except Exception as e:
                lines.append(f"引擎状态失败：{e}")
            # 端口
            try:
                p = subprocess.run("netstat -ano | findstr :5555", shell=True, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=CREATE_NO_WINDOW, timeout=20)
                lines.append("端口 5555：" + (p.stdout.strip() or "未监听"))
            except Exception as e:
                lines.append(f"端口检测失败：{e}")
            # 进程
            try:
                p = subprocess.run('tasklist /FI "IMAGENAME eq Androws*"', shell=True, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=CREATE_NO_WINDOW, timeout=20)
                lines.append("引擎进程：\n" + p.stdout.strip())
            except Exception as e:
                lines.append(f"进程检测失败：{e}")
            if self.adb.ready():
                try:
                    info = collect_info(self.adb, emit)
                    lines.append(f"设备：{info.get('model')} / Android {info.get('android')} / SDK {info.get('sdk')} / "
                                 f"{info.get('abi')}")
                    lines.append(f"Root：{'是' if info.get('root') else '否'} / Magisk：{info.get('magisk') or '无'}")
                    lines.append(f"分辨率：{info.get('resolution')} / DPI：{info.get('density')}")
                    lines.append(f"存储：{info.get('storage')} / 内存：{info.get('memory')}")
                except Exception as e:
                    lines.append(f"设备信息失败：{e}")
            lines.append("")
            lines.append("常见问题：")
            lines.append("· 连接失败 → 先启动应用宝并打开任意应用，等引擎启动后再连接")
            lines.append("· 端口占用 → 关闭 WSA / 其他模拟器")
            lines.append("· ADB 被关闭 → 应用宝设置连续点“性能”7 次开启开发者模式")
            lines.append("· 引擎未 Root → 点「未 Root 刷入指引」，按替换 system.vhd 方案（先备份原文件）")
            return "\n".join(lines)

        def done(out, err):
            if err:
                self.diag_write(f"诊断失败：{err}")
                return
            self.diag_write(out)
            self.set_status("诊断完成")
        self.bg(work, done)

    def show_adb_version(self):
        try:
            out = self.adb.run(["version"], timeout=20) if self.adb.ready() else "未找到 adb"
        except Exception as e:
            out = str(e)
        messagebox.showinfo("adb 版本", out, parent=self.root)

    def check_port(self):
        p = subprocess.run("netstat -ano | findstr :5555", shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW, timeout=20)
        messagebox.showinfo("端口 5555", p.stdout.strip() or "未监听", parent=self.root)

    def check_process(self):
        p = subprocess.run('tasklist /FI "IMAGENAME eq Androws*"', shell=True, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           creationflags=CREATE_NO_WINDOW, timeout=20)
        messagebox.showinfo("引擎进程", p.stdout.strip() or "未运行", parent=self.root)

    def start_store(self):
        path = find_store_launcher()
        if not path:
            messagebox.showinfo("未找到应用宝", "未能定位应用宝启动器，请手动启动「腾讯应用宝电脑版」。",
                                parent=self.root)
            return
        try:
            os.startfile(path)
            self.set_status(f"已启动应用宝：{path}")
            self.diag_write(f"启动应用宝：{path}")
        except Exception as e:
            messagebox.showwarning("启动失败", str(e), parent=self.root)

    def kill_engine(self):
        if not messagebox.askyesno("结束引擎", "将结束所有 Androws 进程（应用宝会退出，需手动重新打开）。\n确定？",
                                   parent=self.root):
            return
        p = subprocess.run('taskkill /F /IM Androws*.exe /T', shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW, timeout=30)
        self.set_status("已结束引擎进程")
        self.diag_write(p.stdout.strip() or p.stderr.strip())
        self.set_conn_state("offline")

    # ======================================================================
    # 收尾
    # ======================================================================
    def on_close(self):
        try:
            self.stop_logcat()
        except Exception:
            pass
        try:
            self.cfg["microg_uninstall_conflict"] = self.mg_uninstall.get()
            self.cfg["microg_grant"] = self.mg_grant.get()
            self.cfg["microg_fakegapps"] = self.mg_fakegapps.get()
        except Exception:
            pass
        self.cfg["geometry"] = self.root.geometry()
        save_config(self.cfg)
        self.root.destroy()


# --------------------------------------------------------------------------- #
# 自检（无界面）
# --------------------------------------------------------------------------- #

def selftest():
    print("== YYB Toolbox selftest ==")
    print("adb:", Adb.autodetect() or "(not found)")
    adb = Adb()
    if not adb.ready():
        print("FAIL: adb not found")
        return 1
    print(adb.run(["version"]).splitlines()[0])
    try:
        serial = adb.ensure_connected(DEFAULT_SERIAL, retries=2, wait=2, emit=lambda k, m: print("  ", m))
    except Exception as e:
        print("FAIL connect:", e)
        return 1
    print("connected:", serial)
    info = collect_info(adb, emit=lambda k, m: print("  ", m))
    for k in ("model", "android", "sdk", "abi", "resolution", "density", "root", "magisk",
              "storage", "memory", "selinux", "battery"):
        print(f"  {k}: {info.get(k)}")
    pkgs = adb.shell("pm list packages -3", timeout=60).splitlines()
    print("third-party packages:", len(pkgs))
    mods = [l for l in adb.shell("ls /data/adb/modules", root=True, timeout=30).splitlines() if l.strip()]
    print("magisk modules:", mods)
    png = adb.exec_out(["screencap", "-p"])
    print("screenshot bytes:", len(png), "png:", png.startswith(b"\x89PNG"))
    if png.startswith(b"\x89PNG"):
        p = CACHE_DIR / "selftest.png"
        CACHE_DIR.mkdir(exist_ok=True)
        p.write_bytes(png)
        print("saved:", p)
    print("OK")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    root = tk.Tk()
    ToolboxApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

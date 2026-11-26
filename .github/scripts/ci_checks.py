#!/usr/bin/env python3
"""仓库自检：源码语法、零第三方依赖、版本信息、README 预览图。

只做静态检查，不导入也不运行 yyb_toolbox.py（避免在 CI 里弹 GUI）。
"""
from __future__ import annotations

import ast
import py_compile
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "yyb_toolbox.py"

notes: list[str] = []
errors: list[str] = []


def check_syntax() -> None:
    files = sorted(ROOT.glob("*.py"))
    for py in files:
        out = Path(tempfile.mkdtemp()) / (py.stem + ".pyc")
        try:
            py_compile.compile(str(py), cfile=str(out), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"语法错误 {py.name}: {exc}")
    notes.append(f"语法检查通过：{len(files)} 个 py 文件")


def check_stdlib_only() -> None:
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    if not stdlib:
        notes.append("当前 Python 不支持 stdlib_module_names，跳过依赖检查")
        return
    tree = ast.parse(ENTRY.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            imported.add(node.module.split(".")[0])
    third = sorted(m for m in imported if m not in stdlib)
    if third:
        errors.append("出现标准库以外的依赖（本项目要求零第三方包）：" + ", ".join(third))
    else:
        notes.append(f"依赖检查通过：{len(imported)} 个导入均为标准库")


def check_version() -> None:
    info = (ROOT / "version_info.txt").read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"filevers\s*=\s*\(\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\)", info)
    if not match:
        errors.append("version_info.txt 里找不到 filevers 版本号")
        return
    version = ".".join(match.groups())
    for key in ("ProductName", "FileVersion", "OriginalFilename"):
        if key not in info:
            errors.append(f"version_info.txt 缺少 {key}")
    notes.append(f"版本信息：{version}")

    source = ENTRY.read_text(encoding="utf-8", errors="ignore")
    declared = re.search(r'\bAPP_VERSION\s*=\s*"([^"]+)"', source)
    if declared and declared.group(1) != version:
        errors.append(f"源码 APP_VERSION={declared.group(1)} 与 version_info.txt={version} 不一致")


def check_readme_image() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore")
    image = ROOT / "docs" / "preview.jpg"
    if "docs/preview.jpg" in readme and not image.exists():
        errors.append("README 引用了 docs/preview.jpg，但文件不存在（预览图会断链）")
    elif image.exists():
        notes.append(f"预览图存在：docs/preview.jpg（{image.stat().st_size:,} 字节）")


def main() -> int:
    check_syntax()
    check_stdlib_only()
    check_version()
    check_readme_image()
    for item in notes:
        print(f"[OK] {item}")
    for item in errors:
        print(f"[FAIL] {item}")
    if errors:
        print(f"\n自检未通过，共 {len(errors)} 项问题")
        return 1
    print("\n全部检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

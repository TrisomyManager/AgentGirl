"""架构基线扫描脚本 (波次 0).

用途:
1. 输出业务模块之间的依赖矩阵 (横向耦合可视化)
2. 列出所有反向 import core_orchestrator 的位置 (ADR-006 硬约束 1)
3. 列出业务模块直连 LLM/ASR/TTS 厂商 SDK 的位置 (ADR-006 硬约束 2)
4. 列出"小暖"等单角色硬编码的位置 (ADR-006 硬约束 3)

零第三方依赖, 纯 stdlib AST 实现, 便于在任何环境跑.

用法:
    cd companion-ai
    python tools/check_arch.py                # 控制台输出
    python tools/check_arch.py --baseline     # 写入 tools/arch_baseline.json
    python tools/check_arch.py --check        # 与 baseline 对比, 新增违规则 exit 1
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

BUSINESS_MODULES = [
    "persona_engine",
    "memory_system",
    "voice_layer",
    "action_layer",
    "action_executor",
    "device_coordination",
    "gateway_adapter",
]

ALL_MODULES = BUSINESS_MODULES + ["core_orchestrator", "shared", "shared_contracts", "shared_runtime"]

NON_ORCHESTRATOR_MODULES = [m for m in ALL_MODULES if m != "core_orchestrator"]

DIRECT_LLM_SDKS = {"openai", "anthropic", "litellm", "dashscope"}

HARDCODED_PERSONA_KEYWORDS = ["小暖", "小汐", "huannuan", "xiaonuan", "xiaoxi"]

EXCLUDE_DIRS = {".venv", "node_modules", "__pycache__", ".git", "frontend_app", "frontend_web", "frontend_sdk", "docs", "tools"}


def iter_py_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in path.relative_to(REPO).parts):
            continue
        files.append(path)
    return files


def module_of(path: Path) -> str | None:
    """根据文件路径推断它属于哪个顶层模块."""
    rel = path.relative_to(REPO).parts
    if not rel:
        return None
    top = rel[0]
    if top in ALL_MODULES:
        return top
    return None


def collect_imports(path: Path) -> list[tuple[str, int]]:
    """返回 [(import_target, lineno), ...]."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append((node.module, node.lineno))
    return out


def scan() -> dict:
    reverse_orchestrator: list[dict] = []
    direct_llm_sdk: list[dict] = []
    cross_module: dict[str, set[str]] = defaultdict(set)
    cross_module_locations: list[dict] = []
    hardcoded_persona: list[dict] = []

    for path in iter_py_files():
        owner = module_of(path)
        rel_str = str(path.relative_to(REPO)).replace("\\", "/")

        # --- import 扫描 ---
        for target, lineno in collect_imports(path):
            top = target.split(".")[0]

            # 反向 import core_orchestrator (所有非 orchestrator 模块视角)
            if owner in NON_ORCHESTRATOR_MODULES and top == "core_orchestrator":
                reverse_orchestrator.append({"file": rel_str, "line": lineno, "import": target})

            # 直连 LLM SDK (跳过 providers/ 封装层 — provider 模块允许直接导入 SDK)
            if (
                owner in BUSINESS_MODULES + ["core_orchestrator"]
                and top in DIRECT_LLM_SDKS
                and "providers" not in path.parts
            ):
                direct_llm_sdk.append({"file": rel_str, "line": lineno, "import": target})

            # 业务模块横向 import
            if owner in BUSINESS_MODULES and top in BUSINESS_MODULES and top != owner:
                cross_module[owner].add(top)
                cross_module_locations.append({"file": rel_str, "line": lineno, "from": owner, "to": top})

        # --- 硬编码角色名扫描 ---
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for kw in HARDCODED_PERSONA_KEYWORDS:
            if kw in text:
                # 数行号: 找出现位置
                for i, line in enumerate(text.splitlines(), start=1):
                    if kw in line:
                        hardcoded_persona.append({"file": rel_str, "line": i, "keyword": kw})

    # 业务模块 → 模块依赖矩阵
    matrix = {m: sorted(cross_module.get(m, set())) for m in BUSINESS_MODULES}

    return {
        "reverse_orchestrator": reverse_orchestrator,
        "direct_llm_sdk": direct_llm_sdk,
        "cross_module_matrix": matrix,
        "cross_module_locations": cross_module_locations,
        "hardcoded_persona": hardcoded_persona,
        "summary": {
            "reverse_orchestrator_count": len(reverse_orchestrator),
            "direct_llm_sdk_count": len(direct_llm_sdk),
            "cross_module_pairs": sum(len(v) for v in matrix.values()),
            "hardcoded_persona_count": len(hardcoded_persona),
        },
    }


def render_text(report: dict) -> str:
    s = report["summary"]
    lines = [
        "=" * 70,
        "companion-ai 架构基线扫描 (波次 0)",
        "=" * 70,
        "",
        "[摘要]",
        f"  反向 import core_orchestrator : {s['reverse_orchestrator_count']}  (目标: 0, 波次 3 清零)",
        f"  业务模块直连 LLM SDK         : {s['direct_llm_sdk_count']}  (目标: 0, 波次 2 清零)",
        f"  业务模块横向 import 对数      : {s['cross_module_pairs']}  (目标: 0, 波次 3-5 清零)",
        f"  单角色硬编码出现次数          : {s['hardcoded_persona_count']}  (目标: 仅保留示例 yaml, 波次 4 清零)",
        "",
        "[业务模块依赖矩阵 (横向耦合)]",
    ]
    for m, deps in report["cross_module_matrix"].items():
        if deps:
            lines.append(f"  {m:25s} -> {', '.join(deps)}")
        else:
            lines.append(f"  {m:25s} -> (独立)")

    lines += ["", "[反向 import core_orchestrator 详情]"]
    if not report["reverse_orchestrator"]:
        lines.append("  (无)")
    else:
        for item in report["reverse_orchestrator"]:
            lines.append(f"  {item['file']}:{item['line']}  -> {item['import']}")

    lines += ["", "[业务模块直连 LLM SDK 详情]"]
    if not report["direct_llm_sdk"]:
        lines.append("  (无)")
    else:
        for item in report["direct_llm_sdk"]:
            lines.append(f"  {item['file']}:{item['line']}  -> {item['import']}")

    lines += ["", "[硬编码角色名详情 (前 30 条)]"]
    if not report["hardcoded_persona"]:
        lines.append("  (无)")
    else:
        for item in report["hardcoded_persona"][:30]:
            lines.append(f"  {item['file']}:{item['line']}  关键字={item['keyword']}")
        if len(report["hardcoded_persona"]) > 30:
            lines.append(f"  ... 还有 {len(report['hardcoded_persona']) - 30} 条")

    return "\n".join(lines)


def _fingerprints(items: list[dict], keys: list[str]) -> set[str]:
    """将违规列表转为指纹集合, 用于精确位置对比."""
    return {":".join(str(item.get(k, "")) for k in keys) for item in items}


def _check_category(name: str, current_items: list[dict], baseline_items: list[dict], keys: list[str]) -> int:
    """对比某一类违规: 返回新增违规数 (0 表示无回归)."""
    baseline_fps = _fingerprints(baseline_items, keys)
    current_fps = _fingerprints(current_items, keys)

    new_fps = current_fps - baseline_fps
    resolved_fps = baseline_fps - current_fps
    old_count = len(baseline_fps)
    new_count = len(current_fps)

    if new_fps:
        print(f"\n[regression] {name}: 新增 {len(new_fps)} 条违规 (原 {old_count}, 现 {new_count})", file=sys.stderr)
        for fp in sorted(new_fps)[:20]:
            print(f"  + {fp}", file=sys.stderr)
        if len(new_fps) > 20:
            print(f"  ... 还有 {len(new_fps) - 20} 条", file=sys.stderr)
        return len(new_fps)
    elif resolved_fps:
        print(f"  [improvement] {name}: 解决 {len(resolved_fps)} 条 (原 {old_count}, 现 {new_count})")
    else:
        print(f"  [unchanged] {name}: {old_count} 条")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true", help="把当前扫描结果写入 baseline 文件")
    parser.add_argument("--check", action="store_true", help="与 baseline 对比, 新增违规则 exit 1")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    report = scan()
    baseline_path = Path(__file__).parent / "arch_baseline.json"

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(render_text(report))

    if args.baseline:
        baseline_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[baseline] 已写入 {baseline_path}")
        print("[baseline] ⚠️  请审核确认后再提交, 禁止随意刷新 baseline")
        return 0

    if args.check:
        if not baseline_path.exists():
            print(f"\n[error] baseline 文件不存在: {baseline_path}, 请先 --baseline", file=sys.stderr)
            return 2
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

        print("\n[check] 指纹对比 (位置级) ...")
        total_new = 0

        categories = [
            ("反向 import core_orchestrator", report["reverse_orchestrator"], baseline.get("reverse_orchestrator", []), ["file", "line", "import"]),
            ("业务模块直连 LLM SDK", report["direct_llm_sdk"], baseline.get("direct_llm_sdk", []), ["file", "line", "import"]),
            ("业务模块横向 import", report["cross_module_locations"], baseline.get("cross_module_locations", []), ["file", "line", "from", "to"]),
            ("硬编码角色名", report["hardcoded_persona"], baseline.get("hardcoded_persona", []), ["file", "line", "keyword"]),
        ]

        for name, current_items, baseline_items, keys in categories:
            total_new += _check_category(name, current_items, baseline_items, keys)

        if total_new > 0:
            print(f"\n[regression] 共 {total_new} 条新增违规, 与 baseline 不符", file=sys.stderr)
            return 1
        print("\n[ok] 与 baseline 对比无新增违规 (位置级)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

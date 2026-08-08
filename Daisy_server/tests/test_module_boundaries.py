"""
模块边界护栏:依赖只能向下,禁止新增循环。

为什么需要它:项目积累了 7 个循环依赖,`core` 本该是最底层却反过来依赖
`services` / `tasks` / `prompts`。后果是没有真正的分层 —— 改任何一处都可能从
意想不到的方向回弹,表现为"修一个 bug 引入另一个"。

靠人工守纪律已经证明守不住(那 7 个环就是这么来的),所以用测试强制。

做法是**棘轮**:现存的环登记为基线,只允许减少不允许增加;新写的代码必须遵守
分层方向。这样既不用一次性大爆炸重构,又能保证不再退化。
"""

import ast
import os
from collections import defaultdict

import pytest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")

# 分层:数字越小越底层。底层不得依赖高层。
# platform 尚未抽出,先按现状给 core 一个临时层级(见 B1 任务)。
LAYERS = {
    "core": 0,        # 基础设施(目标:拆为 platform/*)
    "agents": 1,      # 领域实体(CharacterCard / CommonSettings / RoleProfile)
    "models": 1,      # 持久化实体
    "prompts": 2,     # 提示词渲染,消费领域实体
    "services": 3,    # 用例
    "multi_agent": 3,
    "workflow": 4,    # 编排
    "tasks": 4,
    "api": 5,         # 接口层
}

# 已知的循环依赖基线。**只减不增** —— 每消除一个就从这里删一行。
# 留在这里的每一条都是待还的技术债,不是"可以接受的设计"。
KNOWN_CYCLES = {
    # 空 —— 7 个环已全部还清。新增任何循环都会让 test_cycles_do_not_grow 失败。
    # ("agents", "services")      agents / multi_agent 都在向 services.llm 要 LLM 客户端。
    # ("multi_agent", "services") 但 llm.py 是基础设施(provider 配置/重试/埋点),
    #                             不是业务用例 —— 下沉到 core 后两个环一起消失。
    #                             它写轨迹带来的 core→models 依赖,则改由可插拔
    #                             trace_sink 承接(core 持接口,services 注入实现)。
    # ("core", "tasks")   分发器直接 import 任务函数。改为注册表(core/job_registry.py):
    #                     tasks 导入时自行登记,core 只查表,方向变单向。
    # ("core", "models")  database.py 为了 create_all 而 import 全部模型。
    #                     Base 下沉到 core/db_base;建表逻辑上提到
    #                     services/schema_bootstrap —— 建表本就该知道有哪些模型,
    #                     而 core 不该。core 现在只剩 engine/SessionLocal/Base。
    # 已还清的债(保留记录以免有人"顺手"改回去):
    # ("api", "services")   sse.py 是纯协议编解码(无路由)却放在接口层,被
    #                       tasks/services/api 三方共用。下沉到 core 即消除。
    # ("core", "services")  fusion.py / reflexion.py 是业务逻辑(融合引擎、反思系统),
    # ("core", "prompts")   init_data.py 是种子数据装载。三者都不是基础设施,
    #                       却住在 core 里反向依赖上层。上提到 services 即消除。
}


def _module_edges() -> dict:
    """用 AST 解析相对导入,得出顶层包之间的依赖边(比正则可靠)。"""
    edges = defaultdict(set)
    detail = defaultdict(list)
    for root, _, files in os.walk(APP):
        if "__pycache__" in root:
            continue
        rel = os.path.relpath(root, APP).split(os.sep)
        if not rel or rel[0] not in LAYERS:
            continue
        src_pkg = rel[0]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except SyntaxError:
                continue
            # `if TYPE_CHECKING:` 块内的导入运行期不存在,不构成真实依赖,
            # 也不可能造成导入循环 —— 这是给类型标注解耦的标准手法,应当排除。
            # 但只排除它,函数内的延迟导入仍然计入:那只是把循环藏起来,不是消除。
            skip = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.If):
                    test = node.test
                    is_tc = (
                        (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                        or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
                    )
                    if is_tc:
                        for sub in node.body:
                            for n in ast.walk(sub):
                                skip.add(id(n))

            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or id(node) in skip:
                    continue
                # 相对导入 `from ..core.config import x`:module 的第一段即目标顶层包。
                # 绝对导入 `from app.core.config import x`:去掉 app 前缀后同理。
                mod = node.module or ""
                parts = mod.split(".")
                if parts and parts[0] == "app":
                    parts = parts[1:]
                target = parts[0] if parts else ""
                if target and target != src_pkg and target in LAYERS:
                    edges[src_pkg].add(target)
                    detail[(src_pkg, target)].append(
                        f"{os.path.relpath(path, APP)}:{node.lineno}"
                    )
    return edges, detail


class TestNoNewCycles:

    def test_cycles_do_not_grow(self):
        """
        新增循环依赖直接失败。消除旧环时同步从 KNOWN_CYCLES 删掉那一行。
        """
        edges, detail = _module_edges()
        cycles = set()
        for a in edges:
            for b in edges[a]:
                if a in edges.get(b, set()):
                    cycles.add(tuple(sorted((a, b))))

        known = {tuple(sorted(c)) for c in KNOWN_CYCLES}
        new = cycles - known
        assert not new, (
            "出现了新的循环依赖:\n  " +
            "\n  ".join(
                f"{a} ↔ {b}\n      {a}→{b}: {detail[(a,b)][:2]}\n      {b}→{a}: {detail[(b,a)][:2]}"
                for a, b in sorted(new)
            )
        )

    def test_known_cycles_are_still_real(self):
        """
        基线里已经不存在的环要及时删除,否则棘轮会松掉 ——
        留着一条早已修好的记录,等于给未来的同名回归开了后门。
        """
        edges, _ = _module_edges()
        cycles = {
            tuple(sorted((a, b)))
            for a in edges for b in edges[a]
            if a in edges.get(b, set())
        }
        stale = {tuple(sorted(c)) for c in KNOWN_CYCLES} - cycles
        assert not stale, (
            f"这些环已经消除,请从 KNOWN_CYCLES 中删掉:{sorted(stale)}"
        )


class TestLayerDirection:

    def test_lower_layers_do_not_import_higher(self):
        """
        底层不得依赖高层。已知环内的边先豁免(它们在 KNOWN_CYCLES 里排队还债),
        除此之外一律不允许。
        """
        edges, detail = _module_edges()
        known = {tuple(sorted(c)) for c in KNOWN_CYCLES}
        violations = []
        for src, targets in edges.items():
            for tgt in targets:
                if LAYERS[src] < LAYERS[tgt] and tuple(sorted((src, tgt))) not in known:
                    violations.append(
                        f"{src}(L{LAYERS[src]}) → {tgt}(L{LAYERS[tgt]}): {detail[(src,tgt)][:2]}"
                    )
        assert not violations, "出现反向依赖(低层引用高层):\n  " + "\n  ".join(violations)

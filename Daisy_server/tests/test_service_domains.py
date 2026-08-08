"""
services 域边界护栏。

services/ 曾是平铺的 22 个文件、5225 行,从记忆、人格到主动关心全堆在一层 ——
既看不出谁属于哪块业务,也拦不住任何跨业务的随手调用。拆成 6 个域之后,
**真正有价值的不是目录变好看了,而是下面这两条可以被自动检查的性质**:

  1. 域之间无环 —— 拆完当下实测为 0 环,方向是天然分层的:
         memory(最底,不依赖任何域)
           <- learning <- persona <- dialogue
           <- proactive / system
     一旦出现环,"高内聚低耦合"就退化回原来的一团。
  2. 域内模块不被跨域直接深挖 —— 这条这里**不强制**(见文末说明)。

护栏是"只减不增"的棘轮:CYCLES 基线为空,任何新环都会让测试失败。
要新增依赖方向没问题,加环不行。
"""

import collections
import os
import re

DOMAINS = ["memory", "persona", "dialogue", "proactive", "learning", "system"]

SVC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "services",
)

# 基线:拆分完成时域间环的数量为 0。这个值只允许减少。
KNOWN_DOMAIN_CYCLES: set = set()


def _domain_edges() -> collections.Counter:
    """扫描每个域的源码,统计它引用了哪些别的域。"""
    edges: collections.Counter = collections.Counter()
    for dom in DOMAINS:
        for dirpath, _, files in os.walk(os.path.join(SVC, dom)):
            if "__pycache__" in dirpath:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                src = open(os.path.join(dirpath, fn), encoding="utf-8").read()
                for m in re.finditer(r"services\.(\w+)", src):
                    target = m.group(1)
                    if target in DOMAINS and target != dom:
                        edges[(dom, target)] += 1
    return edges


class TestDomainsAreAcyclic:

    def test_all_domains_exist(self):
        """目录缺失说明有人把域合并/删掉了 —— 后面的检查会静默失效。"""
        for dom in DOMAINS:
            path = os.path.join(SVC, dom, "__init__.py")
            assert os.path.exists(path), f"域 {dom} 不存在或缺少 __init__.py"

    def test_no_new_cycles_between_domains(self):
        """
        核心护栏。双向依赖意味着两个域实际上是一块业务被硬拆开,
        或者有人图省事反向调用 —— 两种都该在评审时被看见。
        """
        edges = _domain_edges()
        cycles = {tuple(sorted(e)) for e in edges if (e[1], e[0]) in edges}
        new = cycles - KNOWN_DOMAIN_CYCLES
        assert not new, (
            f"services 域之间出现新的循环依赖: {sorted(new)}\n"
            f"要么把共用部分下沉,要么让其中一方改为单向依赖。"
        )

    def test_baseline_only_shrinks(self):
        """棘轮:环消失了就要更新基线,否则它会悄悄退化回来。"""
        edges = _domain_edges()
        cycles = {tuple(sorted(e)) for e in edges if (e[1], e[0]) in edges}
        stale = KNOWN_DOMAIN_CYCLES - cycles
        assert not stale, (
            f"这些环已经不存在了,请从 KNOWN_DOMAIN_CYCLES 里删掉: {sorted(stale)}"
        )

    def test_memory_is_a_leaf(self):
        """
        记忆域是最底层:所有域都可能读写记忆,但记忆不该反过来
        依赖人格/对话/主动关心 —— 那会让"存取"和"决定说什么"纠缠在一起。
        """
        edges = _domain_edges()
        out = [t for (s, t) in edges if s == "memory"]
        assert not out, f"memory 域依赖了上层域: {out}"


class TestDomainInitsDoNotShadow:
    """
    tasks/__init__.py 曾经 `from .chat_task import chat_task`,
    结果 `app.tasks.chat_task` 从模块变成了函数,调用方拿到的东西悄悄换了类型。
    域包的 __init__.py 一律不做重导出,这条测试守住它。
    """

    def test_no_reexports_in_domain_inits(self):
        for dom in DOMAINS:
            src = open(os.path.join(SVC, dom, "__init__.py"), encoding="utf-8").read()
            code = "\n".join(
                l for l in src.splitlines()
                if l.strip() and not l.strip().startswith("#")
            )
            # 去掉模块 docstring 后应当没有可执行语句
            body = re.sub(r'^\s*"""[\s\S]*?"""\s*', "", code).strip()
            assert not body, (
                f"services/{dom}/__init__.py 出现了重导出或其他语句:\n{body}\n"
                f"调用方请直接导入具体模块,避免包属性遮蔽同名子模块。"
            )

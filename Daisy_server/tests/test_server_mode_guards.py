"""
server 语义在桌面版下的关闭验证。

桌面版是单机应用:账号注册/登录、白名单管理这些概念不存在。
端点若仍开放,本机任意进程都能访问 —— 属无谓攻击面。
这里锁定:嵌入模式返回 404(表现为"不存在"而非"被禁止"),
且 server 部署模式不受影响。
"""

import pytest
from fastapi import HTTPException

from app.api.deps import require_server_mode
from app.core.config import settings


def test_guard_blocks_in_embedded_mode(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDED_MODE", True)
    with pytest.raises(HTTPException) as exc:
        require_server_mode()
    assert exc.value.status_code == 404, "应表现为端点不存在,而非 403 被禁止"


def test_guard_allows_in_server_mode(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDED_MODE", False)
    assert require_server_mode() is True


def test_server_only_endpoints_declare_guard():
    """register / login / change-password 必须挂上守卫,防止后续改动漏掉。"""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "app" / "api" / "auth.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    guarded = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            text = ast.unparse(deco)
            if "require_server_mode" in text:
                guarded.add(node.name)

    for fn in ("register", "login", "change_password"):
        assert fn in guarded, f"{fn} 缺少 require_server_mode 守卫,桌面版会暴露该端点"


def test_local_session_not_guarded():
    """local_session 是桌面版专用,不能被 server 守卫挡住。"""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "app" / "api" / "auth.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "local_session":
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call):
                    assert "require_server_mode" not in ast.unparse(deco)
            return
    pytest.fail("未找到 local_session 端点")


def test_cors_disabled_in_embedded_mode():
    """嵌入模式不应注册 CORS 中间件(同源应用,开放 CORS 是无谓攻击面)。"""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "app" / "main.py"
    text = src.read_text(encoding="utf-8")
    # CORS 注册必须处在 "not EMBEDDED_MODE" 分支内
    assert "if not settings.EMBEDDED_MODE:" in text
    cors_idx = text.index("CORSMiddleware,")
    guard_idx = text.index("if not settings.EMBEDDED_MODE:")
    assert guard_idx < cors_idx, "CORS 中间件必须在 EMBEDDED_MODE 判断之后注册"

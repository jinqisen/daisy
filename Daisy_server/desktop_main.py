"""
桌面 App 后端入口(PyInstaller 打包目标)。

与 `python -m app.main` 的区别:
- 强制 EMBEDDED_MODE(单进程、fakeredis、本地 Qdrant、worker 并入)
- 解析 PyInstaller 冻结环境下的资源路径(模型、prompts、前端 dist)
- 编程式启动 uvicorn(PyInstaller 无法直接跑 `-m`)

打包后的资源布局(见 daisy_backend.spec 的 datas):
  <bundle>/Daisy_prompts/...
  <bundle>/model/bert-base-cased-goemotions-original/...
  <bundle>/frontend/index.html ...
用户数据(sqlite、向量库、日志)写到用户目录 ~/Library/Application Support/Daisy。
"""

import os
import sys
from pathlib import Path


def _bundle_dir() -> Path:
    """PyInstaller 冻结时为解压目录(sys._MEIPASS),否则为源码树。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _user_data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Daisy"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home())) / "Daisy"
    else:
        base = Path.home() / ".local" / "share" / "daisy"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _configure_env():
    bundle = _bundle_dir()
    # 允许外部预先指定数据目录(测试/隔离调试/应急迁移场景)。
    # 之前虽然尊重了 DAISY_DATA_DIR 本身,但 VECTOR_DB_PATH / DAISY_DB_PATH
    # 仍然按默认用户目录计算,导致运行期写路径分裂:一部分跟随 override,
    # 一部分偷偷落回 ~/Library/Application Support/Daisy。
    data = Path(os.environ.get("DAISY_DATA_DIR") or _user_data_dir())
    data.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("EMBEDDED_MODE", "1")
    os.environ.setdefault("HOST", "127.0.0.1")
    os.environ.setdefault("PORT", "30021")

    # 只读资源(随包)
    os.environ.setdefault("DAISY_PROMPTS_DIR", str(bundle / "Daisy_prompts"))
    emotion_model = bundle / "model" / "bert-base-cased-goemotions-original"
    if emotion_model.exists():
        os.environ.setdefault("EMOTION_MODEL_NAME", str(emotion_model))
    frontend = bundle / "frontend"
    if (frontend / "index.html").exists():
        os.environ.setdefault("FRONTEND_DIST", str(frontend))

    # 默认角色卡:配置里的默认值是相对路径(相对项目根),冻结环境下解析不到。
    # 它是深度角色卡生成失败时的兜底,缺失会让前端一直卡在"角色卡生成中"。
    default_card = bundle / "assets" / "character_cards" / "default_character_card.json"
    if default_card.exists():
        os.environ.setdefault("DEFAULT_CHARACTER_CARD_PATH", str(default_card))

    # 可写用户数据。DAISY_DATA_DIR 供 config.get_writable_data_dir() 使用,
    # 让 static/uploads、log 等所有运行期写入避开只读的应用包目录。
    os.environ.setdefault("DAISY_DATA_DIR", str(data))
    os.environ.setdefault("VECTOR_DB_PATH", str(data / "qdrant_embedded"))
    # sqlite 路径由 core/database 依据 __file__ 计算,冻结环境下改用用户目录
    os.environ.setdefault("DAISY_DB_PATH", str(data / "daisy.db"))
    # 确保远程服务地址不被 .env 带入(冻结包不含 .env,双保险)
    os.environ.pop("QDRANT_HOST", None)

    # server_config.json(含 LLM 模型名/密钥等):首次运行把随包默认复制到用户目录,
    # 之后用户可在该处编辑(改密钥/模型),配置随升级不被覆盖。
    user_config = data / "server_config.json"
    if not user_config.exists():
        import shutil
        bundled_config = bundle / "server_config.json"
        if bundled_config.exists():
            shutil.copy(bundled_config, user_config)
    if user_config.exists():
        os.environ.setdefault("DAISY_CONFIG_PATH", str(user_config))


def _watch_parent_and_exit():
    """
    父进程(Electron 外壳)消失后自杀。

    为什么不能只靠外壳来收:
      - 外壳崩溃/被强杀时 before-quit 根本不会触发;
      - 即便触发,SIGTERM 走 uvicorn 优雅关闭,而它会等所有连接结束 ——
        SSE 是长连接,永远不结束,后端就挂成孤儿(实测残留 523 MB)。
    父进程死后 PPID 会变成 1(被 init 收养),据此判断即可,无需外壳配合。
    """
    import threading
    import time

    initial_ppid = os.getppid()
    if initial_ppid <= 1:
        return  # 本来就没有父进程(直接手动运行),不启用看门狗

    def _loop():
        while True:
            time.sleep(3)
            if os.getppid() != initial_ppid:
                # 日志必须放在 try 里且不能挡住退出:外壳用管道接管了 stdout,
                # 它一死管道读端就关闭,print 会抛 BrokenPipeError ——
                # 若 print 在退出之前裸调用,异常会杀掉本线程,退出永远执行不到
                # (实测:隔离环境重定向到文件时正常,真机上后端却残留)。
                try:
                    print("[daisy] 父进程已退出,后端随之关闭", flush=True)
                except Exception:
                    pass
                os._exit(0)  # 绕过 uvicorn 的优雅关闭,否则又会卡在 SSE 上

    threading.Thread(target=_loop, daemon=True).start()


def main():
    _configure_env()
    _watch_parent_and_exit()
    # 延迟导入:环境变量必须在 app 配置加载前设好。
    # 直接导入 app 对象而非 "app.main:app" 字符串——冻结环境下 import-string
    # 的路径解析不可靠,直接传对象最稳。
    import uvicorn
    from app.main import app as fastapi_app
    host = os.environ["HOST"]
    port = int(os.environ["PORT"])
    uvicorn.run(fastapi_app, host=host, port=port, reload=False, workers=1)


if __name__ == "__main__":
    main()

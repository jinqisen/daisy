#!/usr/bin/env python3
"""
打包期拉取本地模型 —— 让安装包开箱即用,不在用户使用时才联网下载。

为什么必须在构建期做:
  这两个模型原先都是用 HuggingFace Hub ID 引用的,运行时按需下载。
  开发机因为缓存里有,一切正常;而用户拿到的安装包是干净的 ——
  第一次用到长期记忆就要拉 1.3GB,期间对话直接卡住,断网或网络受限则彻底失败。
  桌面应用不该有这种"看运气"的首次体验。

产物落在 Daisy_server/model/,由 PyInstaller spec 随包分发。
已存在则跳过(构建可重复执行,不会反复下载)。
"""

import os
import sys

MODELS = {
    # 长期记忆的中文嵌入模型。512 维,与 settings.EMBEDDING_DIMS 必须一致。
    # 选 small 而非 large:large 权重 1.3GB,会让 .dmg 从 808M 涨到 2.1G,
    # 而 small 只有 96MB。中文语义检索场景下 small 的召回质量足够。
    "bge-small-zh-v1.5": "BAAI/bge-small-zh-v1.5",
    # Reflexion 语义相似度打分用。同样原先是运行时下载。
    "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
}

# 只取推理需要的文件。默认会把 pytorch_model.bin 和 model.safetensors 都拉下来,
# 体积翻倍且没有意义 —— 有 safetensors 时优先用它。
IGNORE = ["*.h5", "*.ot", "*.msgpack", "*.onnx", "*.onnx_data", "openvino*/**"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST_ROOT = os.path.join(ROOT, "Daisy_server", "model")


def _has_weights(path: str) -> bool:
    """判断是否已经拉全:目录存在且含权重文件。"""
    if not os.path.isdir(path):
        return False
    for root, _, files in os.walk(path):
        for f in files:
            if f.endswith((".safetensors", ".bin")):
                return True
    return False


def main() -> int:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[models] 缺少 huggingface_hub,无法预拉模型。请先 pip install huggingface_hub", file=sys.stderr)
        return 1

    os.makedirs(DEST_ROOT, exist_ok=True)
    for local_name, repo_id in MODELS.items():
        dest = os.path.join(DEST_ROOT, local_name)
        if _has_weights(dest):
            print(f"[models] 已存在,跳过: {local_name}")
            continue

        print(f"[models] 拉取 {repo_id} → {dest}")
        # 依次尝试多个源:国内直连 huggingface.co 常不稳,镜像作为回落。
        endpoints = [os.environ.get("HF_ENDPOINT"), "https://huggingface.co", "https://hf-mirror.com"]
        seen, ok, last_err = set(), False, None
        for ep in endpoints:
            if not ep or ep in seen:
                continue
            seen.add(ep)
            os.environ["HF_ENDPOINT"] = ep
            try:
                snapshot_download(
                    repo_id=repo_id,
                    local_dir=dest,
                    ignore_patterns=IGNORE,
                    max_workers=4,
                )
                ok = True
                break
            except Exception as e:
                last_err = e
                print(f"[models]   源 {ep} 失败: {type(e).__name__}", file=sys.stderr)
        if not ok:
            print(f"[models] 拉取失败 {repo_id}: {last_err}", file=sys.stderr)
            return 1

        # 有 safetensors 就删掉等价的 .bin,避免包体白白翻倍
        weights = {}
        for root, _, files in os.walk(dest):
            for f in files:
                if f.endswith(".safetensors"):
                    weights.setdefault(root, set()).add("safetensors")
                elif f.endswith(".bin") and "model" in f:
                    weights.setdefault(root, set()).add("bin")
        for root, kinds in weights.items():
            if "safetensors" in kinds and "bin" in kinds:
                for f in os.listdir(root):
                    if f.endswith(".bin") and "model" in f:
                        os.remove(os.path.join(root, f))
                        print(f"[models]   已删除冗余权重 {f}(保留 safetensors)")

    total = 0
    for root, _, files in os.walk(DEST_ROOT):
        total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    print(f"[models] 本地模型总计 {total / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

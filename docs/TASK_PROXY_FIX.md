# Docker 代理配置问题修复指南

## 问题描述

在构建 Docker 镜像时，出现了以下错误：
```
dial tcp 127.0.0.1:10809: connectex: No connection could be made because the target machine actively refused it.
```

这表明 **Docker Desktop 配置了代理服务器 (http://127.0.0.1:10809)**，但该端口当前**没有服务在监听**，或者容器无法访问宿主机的该端口。

## 解决方案

请尝试以下两种方法之一：

### 方法一：关闭 Docker Desktop 代理（推荐）

如果您的网络环境不需要代理即可访问 Docker Hub 或 Debian 源，请关闭 Docker 代理：

1. 打开 **Docker Desktop** 界面。
2. 点击右上角的齿轮图标进入 **Settings**。
3. 进入 **Resources** -> **Proxies**。
4. 关闭 **Manual proxy configuration** 开关。
5. 点击 **Apply & restart**。

### 方法二：开启本地代理软件

如果您需要通过代理访问外网，请确保您的代理软件正在运行，并且端口正确：

1. 确保您的代理软件（如 Clash, v2rayN 等）正在运行。
2. 检查代理软件的设置，确认 **HTTP 代理端口** 是 `10809`。
3. 确保代理软件允许局域网连接（Allow LAN），虽然对于 Docker Desktop WSL2 模式，通常需要特殊配置才能访问宿主机 localhost。

## 重新运行构建

完成上述配置修改后，请重新运行构建脚本：

```powershell
cd e:\Daisy\Daisy_Demo\Daisy_server\scripts
.\build_local_image.ps1
```

## 已完成的优化

脚本已更新以下功能：
1. **依赖缓存**：已配置 `apt` 和 `pip` 的缓存挂载，下次构建时将自动使用缓存，无需重复下载。
2. **GPU 支持**：已修复 GTX 1060 的兼容性问题。

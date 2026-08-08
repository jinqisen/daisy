> **⚠️ 已归档 —— 前提不再成立**
> 本项目已从 server 部署转为单机桌面应用(零 Docker/零外部服务/免登录)。
> 本文档中的待办因架构变更而失效,无需执行。原因与全量清单见 [docs/ARCHIVED_TODOS.md](../../docs/ARCHIVED_TODOS.md)。

---
# 待办事项 - 前端远程镜像构建

## 1. 待解决问题
- [x] 启动 Docker Desktop
- [x] 重新执行构建脚本
- [x] 修复 Vite 构建时未读取 .env 的问题

## 2. 部署操作指引
**请使用最新的镜像文件进行部署：**

1. **上传文件**: 将 `daisyFront_remote_20251231_124646.tar` 复制到目标服务器。
2. **加载镜像**: 
   ```bash
   # 先停止并删除旧容器
   docker stop daisy_front && docker rm daisy_front
   
   # 加载新镜像
   docker load -i daisyFront_remote_20251231_124646.tar
   ```
3. **运行容器**:
   ```bash
   docker run -d --name daisy_front -p 30020:80 --restart unless-stopped daisy_front_remote:20251231_124646
   ```

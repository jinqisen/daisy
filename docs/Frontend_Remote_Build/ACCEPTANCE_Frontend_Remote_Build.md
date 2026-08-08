# 验收文档 - 前端远程镜像构建

## 1. 执行记录
### 尝试 1
- **时间**: 2025-12-31 12:25
- **结果**: 失败 (Docker 未启动)

### 尝试 2
- **时间**: 2025-12-31 12:28
- **结果**: 成功，但配置未生效 (Vite Build 未读取到 .env)
- **现象**: 部署后请求 127.0.0.1 (默认值) 导致连接拒绝。

### 尝试 3
- **时间**: 2025-12-31 12:44
- **修复**: 修改 PowerShell 脚本，显式读取 .env 并注入 `$env:VITE_API_BASE_URL`。
- **结果**: 成功。

### 尝试 4 (本次)
- **时间**: 2025-12-31 12:46
- **结果**: 成功 (用户手动触发重试)
- **日志**: `Detected API Base URL: http://171.43.173.125:30026/api`

## 2. 产物验证
- **文件路径**: `E:\Daisy\Daisy_Demo\Daisy_front\image\remote\daisyFront_remote_20251231_124646.tar`
- **文件大小**: ~128 MB
- **Docker 镜像**: `daisy_front_remote:20251231_124646`

## 3. 部署说明
1. 将 tar 文件上传到服务器。
2. 加载镜像: `docker load -i daisyFront_remote_20251231_124646.tar`
3. 运行容器: `docker run -d --name daisy_front -p 30020:80 --restart unless-stopped daisy_front_remote:20251231_124646`

## 4. 结论
镜像构建成功，环境变量传递逻辑验证无误。

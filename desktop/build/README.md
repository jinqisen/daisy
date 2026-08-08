# 应用图标(可选)

放置以下文件即可自定义应用图标,并在 ../package.json 的 build.mac.icon /
build.win.icon 中重新引用:

- `icon.icns` — macOS(1024x1024 源图,用 `iconutil` 生成)
- `icon.ico`  — Windows(含 256x256)

当前未提供,electron-builder 使用 Electron 默认图标。

// Daisy 桌面壳(Electron)。
// 职责:拉起 PyInstaller 打包的后端 sidecar → 等待 /health 就绪 → 窗口加载本地 UI。
// 前端由后端同源托管(http://127.0.0.1:PORT),故窗口直接指向该地址。

const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const net = require('net');
const path = require('path');
const fs = require('fs');

// 端口不再硬编码:硬编码会在"上次退出留下僵尸进程"或"重复启动"时
// 触发后端 Errno 48 (address already in use) 并导致整个 App 退出。
const PREFERRED_PORT = 30021;
let PORT = PREFERRED_PORT;
let backendProc = null;
let mainWindow = null;

/** 探测某端口是否可用(仅本机回环)。 */
function isPortFree(port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once('error', () => resolve(false));
    srv.once('listening', () => srv.close(() => resolve(true)));
    srv.listen(port, '127.0.0.1');
  });
}

/** 优先用默认端口,被占则顺延寻找空闲端口。 */
async function pickPort(preferred, attempts = 20) {
  for (let i = 0; i < attempts; i++) {
    const candidate = preferred + i;
    if (await isPortFree(candidate)) return candidate;
  }
  // 全部被占时交给系统分配
  return 0;
}

// 打包后 sidecar 路径:resources/daisy_backend/daisy_backend
// 开发时(未打包)指向 packaging/dist 下的构建产物
function backendExecutable() {
  const exeName = process.platform === 'win32' ? 'daisy_backend.exe' : 'daisy_backend';
  const packaged = path.join(process.resourcesPath || '', 'daisy_backend', exeName);
  if (fs.existsSync(packaged)) return packaged;
  const dev = path.join(__dirname, '..', 'packaging', 'dist', 'daisy_backend', exeName);
  return dev;
}

function startBackend() {
  const exe = backendExecutable();
  if (!fs.existsSync(exe)) {
    dialog.showErrorBox('启动失败', `未找到后端可执行文件:\n${exe}`);
    app.quit();
    return;
  }
  backendProc = spawn(exe, [], {
    env: { ...process.env, EMBEDDED_MODE: '1', HOST: '127.0.0.1', PORT: String(PORT) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  backendProc.stdout.on('data', (d) => console.log('[backend]', d.toString().trimEnd()));
  backendProc.stderr.on('data', (d) => console.log('[backend]', d.toString().trimEnd()));
  backendProc.on('exit', (code) => {
    console.log('[backend] exited', code);
    if (app.isQuitting) return;
    // 后端异常退出:给出可读原因而不是让用户面对一个空错误码。
    // 窗口已开则保留窗口(用户可看到已加载的内容),仅提示。
    const detail = code === 0
      ? '后端进程已结束。'
      : `后端进程意外退出(代码 ${code})。\n\n可尝试重新打开应用;若反复出现,请查看日志:\n${logHintPath()}`;
    dialog.showErrorBox('后端已停止', detail);
    app.quit();
  });
}

function logHintPath() {
  if (process.platform === 'darwin') {
    return `${app.getPath('home')}/Library/Application Support/Daisy/log/`;
  }
  return path.join(app.getPath('appData'), 'Daisy', 'log');
}

function waitForHealth(timeoutMs = 120000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const probe = () => {
      http
        .get(`http://127.0.0.1:${PORT}/health`, (res) => {
          if (res.statusCode === 200) return resolve();
          retry();
        })
        .on('error', retry);
    };
    const retry = () => {
      if (Date.now() - start > timeoutMs) return reject(new Error('后端启动超时'));
      setTimeout(probe, 800);
    };
    probe();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 780,
    title: 'Daisy',
    backgroundColor: '#f0f2f5',
    webPreferences: { contextIsolation: true },
  });
  mainWindow.loadURL(`http://127.0.0.1:${PORT}/`);
  mainWindow.on('closed', () => (mainWindow = null));
}

// 单实例锁:重复启动时聚焦已有窗口,而不是再拉一个后端去抢同一个端口。
// 这是"后端老是意外退出"的主要成因之一。
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    PORT = await pickPort(PREFERRED_PORT);
    if (PORT === 0) {
      dialog.showErrorBox('启动失败', '找不到可用端口,请关闭占用端口的程序后重试。');
      app.quit();
      return;
    }
    if (PORT !== PREFERRED_PORT) {
      console.log(`[shell] 默认端口被占用,改用 ${PORT}`);
    }

    startBackend();
    try {
      await waitForHealth();
    } catch (e) {
      dialog.showErrorBox('启动失败', `${e}\n\n日志位置:\n${logHintPath()}`);
      app.quit();
      return;
    }
    createWindow();
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on('before-quit', () => {
  app.isQuitting = true;
  if (!backendProc || backendProc.killed) return;

  // SIGTERM 走 uvicorn 的优雅关闭,但它会等所有连接结束 —— SSE 是长连接,
  // 永远不结束,于是后端挂住、变成占几百 MB 的孤儿进程(实测 523 MB)。
  // 给一个宽限期后强杀。
  const proc = backendProc;
  proc.kill('SIGTERM');
  setTimeout(() => {
    try {
      if (!proc.killed) proc.kill('SIGKILL');
    } catch (e) {
      // 进程已退出,忽略
    }
  }, 3000);
});

app.on('window-all-closed', () => {
  app.quit();
});

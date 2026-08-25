# ClipNest Tauri 2 Demo

这是 ClipNest Windows 剪贴板 Demo 的 Tauri 2 工程骨架。它直接复用同目录项目中的 HTML 原型，因此不会复制一份视觉代码：

- 前端：`../clipnest-prototype/index.html`
- 后端：`src-tauri/src/lib.rs`
- 数据库：Windows `%LOCALAPPDATA%/ClipNest/clipnest.db`
- 存储：SQLite WAL，当前包含文本剪贴板读写、去重保存和最近记录查询命令

## 本机运行

当前准备工程的环境没有 Node.js、Rust 或 Cargo，因此这里没有直接生成 `.exe`。在 Windows 机器上安装 Tauri 所需工具后运行：

```powershell
npm install
npm run tauri dev
```

生成安装包：

```powershell
npm run tauri build
```

也可以使用 Cargo 安装 Tauri CLI 后执行 `cargo tauri dev` 或 `cargo tauri build`。

官方环境要求：

- Rust stable-msvc 工具链
- Microsoft C++ Build Tools（Desktop development with C++）
- WebView2 Runtime（Windows 11 通常已经具备）

后续正式开发会在这个壳里加入后台剪贴板监听、全局快捷键、图片/文件内容存储、设置页与开机启动；当前 Demo 先验证视觉窗口和 Rust/SQLite 方向。


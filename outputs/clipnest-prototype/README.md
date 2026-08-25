# ClipNest

一个面向 Windows 的可视化剪贴板工作台原型。

## 打开原型

直接双击 `index.html` 即可在浏览器中预览。当前版本是纯 HTML/CSS/JavaScript，无需安装依赖。

## Figma 设计稿

[打开 ClipNest v1 · Clipboard Shelf](https://www.figma.com/design/zlwSQAJipCgPnwQAk7LfHM)

设计稿已同步当前单排卡片、统一分类色带、放大预览区和齿轮设置入口，图层可继续编辑。

## 已实现的体验

- 屏幕底部展开的紧凑型“剪贴板 shelf”布局
- 文本、图像、代码、链接、文件五类片段
- 搜索、分类筛选、收藏、卡片内预览
- 单排卡片快速取用，点击卡片即可复制，不再依赖右侧详情栏
- 分类标签、搜索入口和设置入口整合到同一行；搜索默认收起为放大镜图标
- `Esc` 收起 shelf，`Ctrl + Shift + V` 重新打开；设置内容集中在齿轮弹层
- `Ctrl + K` 搜索、`↑ ↓` 选择、`Enter` 复制、`Ctrl + P` 收藏
- 仅本地存储的产品文案方向，为后续接入 Windows 原生剪贴板监听预留空间

## 底层方案调研结论

本轮在 GitHub 重点看了以下项目：

1. [CopyQ](https://github.com/hluk/CopyQ)：成熟度最高，支持 Windows、文本/HTML/图像/自定义格式、搜索过滤、标签、快捷键、脚本和本地历史。更适合作为“能力参考”或独立进程底层，但它是完整应用，直接嵌入 UI 的成本较高；正式复用前需要单独核对许可证与分发边界。
2. [CyberShadow/Ditto](https://github.com/CyberShadow/Ditto)：GitHub 搜索中找到的 Windows 剪贴板实现，适合研究监听、序列化和快速粘贴流程。它的 UI 与本项目目标不同，建议只提取可复用的系统层思路，避免把旧式窗口模型带入新界面。
3. [PasteBar](https://github.com/PasteBar/PasteBarApp)：与目标产品形态最接近，已覆盖 Windows/macOS、历史、收藏/集合、搜索和快捷粘贴。它更适合作为交互与功能边界参考，不建议在尚未确认许可证和代码耦合前直接复制实现。

## 推荐的产品化路线

首选 **WinUI 3 + C# + SQLite**：

- 剪贴板监听：`ClipboardContentChanged` + 隐藏消息窗口/生命周期管理
- 全局快捷键：注册 `Ctrl + Shift + V`，冲突时允许用户修改
- 数据：SQLite 存元数据，图片/大文件以本地内容寻址文件保存
- UI：将本原型的 shelf、卡片、详情预览迁移到 WinUI 3；窗口设为无边框、置顶、底部对齐
- 隐私：默认本地、可排除密码管理器/隐私窗口、支持一键暂停监听和清理历史

如果需要跨平台，再考虑 **Tauri + Rust**；如果优先复用成熟能力，则应先做一个隔离的 CopyQ/Ditto 适配层，再决定是否长期保留。

## 版权与产品边界

本原型借鉴了“底部展开、按内容类型组织、快速检索”的交互方向，没有复制 Paste 的品牌、图标、文案或素材。正式产品应继续保持独立的命名、视觉 token 和资源体系，并在复用任何开源代码前确认其许可证、NOTICE 要求与商业分发限制。


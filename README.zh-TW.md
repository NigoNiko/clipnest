# ClipNest

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

> **Codex Vibe Coding 專案**：ClipNest 由維護者與 Codex 協作開發，產品選擇、測試與發佈由維護者審閱。

一款適用於 Windows 的本機剪貼簿歷史工具。複製過的文字、Markdown、連結、程式碼、顏色、圖片和檔案，會以卡片形式留在桌面底部；需要時用快捷鍵叫出、搜尋並重新貼上。

> 目前正式版：**1.00.5** · Windows x64 · [下載安裝程式](https://github.com/NigoNiko/clipnest/releases/latest)

## 介面預覽

以下截圖使用示範資料製作，不包含真實剪貼紀錄。

### 淺色模式 · 全部歷史

各種內容顯示在同一條卡片列中；頂部可切換收藏夾、搜尋和依類型篩選。

![淺色模式下的剪貼簿歷史卡片](docs/screenshots/history-light.png)

### 深色模式 · 收藏夾

收藏夾用不同顏色的圓點區分，常用內容可集中儲存，並可拖曳卡片調整順序。

![深色模式下的收藏夾](docs/screenshots/favorites-dark.png)

### 搜尋與篩選

輸入關鍵字後即時篩選歷史紀錄，也能只顯示文字、Markdown、連結、程式碼、顏色、圖片或檔案。

![搜尋並篩選剪貼紀錄](docs/screenshots/search-light.png)

### 紀錄與隱私

可調整歷史保留時間、排除不希望記錄的應用程式，並選擇是否自動取得網頁標題和圖示。

![紀錄與隱私設定](docs/screenshots/settings-privacy.png)

## 主要功能

- **快速找回與貼上**：預設按 `Ctrl + Alt + Q` 開啟卡片列，支援搜尋、類型篩選與鍵盤選擇。可直接貼到剛才使用的應用程式，也可只複製到剪貼簿。
- **多種內容預覽**：區分普通文字、Markdown、程式碼、連結、顏色、圖片與檔案。Markdown 同時保留原始碼和富文字格式，由目標應用程式選擇支援的貼上格式；連結可讀取網頁標題與網站圖示。
- **收藏夾**：將常用內容放入不同收藏夾、設定識別色，並透過拖曳調整順序。ClipNest 視窗啟用時可用 `Ctrl + 1～9`、`Ctrl + 0` 切換全部歷史與前九個收藏夾；其餘收藏夾可自訂快捷鍵。
- **可控的記錄行為**：可暫停記錄、設定保留時間、忽略指定應用程式，並管理開機啟動。程式預設跳過常見密碼管理器，以及標記為不應儲存的剪貼內容；排除規則無法識別所有敏感資訊。
- **本機資料保護**：歷史紀錄、圖片、連結預覽和設定儲存在 SQLCipher 加密資料庫中；金鑰由目前 Windows 帳戶的 DPAPI 保護。沒有雲端同步。可在設定中備份和搬移資料。
- **安裝、更新與解除安裝**：安裝程式支援覆蓋更新；「設定 → 關於」可檢查 GitHub Release。解除安裝時可選擇保留或清除本機資料。
- **介面語言**：可跟隨系統語言，或在「設定 → 外觀」選擇簡體中文、繁體中文或 English。變更後立即套用。

## 安裝與使用

1. 從 [Releases](https://github.com/NigoNiko/clipnest/releases/latest) 下載 `ClipNest-1.00.5-Setup-x64.exe`，在 Windows x64 上執行。
2. 啟動後，ClipNest 會留在系統匣。複製內容後，按 `Ctrl + Alt + Q` 叫出卡片列。
3. 選擇卡片即可再次使用；右鍵可編輯、重新命名、收藏、複製或刪除。

預設安裝於 `%LOCALAPPDATA%\Programs\ClipNest`，資料預設儲存於 `%LOCALAPPDATA%\ClipNest`。一般覆蓋更新會保留資料；互動式解除安裝可選擇是否刪除資料和金鑰。更多操作資訊請參閱[桌面版使用文件](desktop/README.md)（目前為簡體中文）。

即時模糊背景需要[微軟 .NET 8 Runtime（x64）](https://dotnet.microsoft.com/download/dotnet/8.0)。若未安裝，ClipNest 會提供下載入口，其他功能仍可使用。

先前的 `1.34.7` 是 Beta 測試版。該版本以數字比較版本號，無法自動識別號碼較小的正式版 `1.00.0`；Beta 使用者需手動下載正式版並覆蓋安裝一次，原有紀錄與設定會保留。之後可繼續在應用程式內更新。

Windows 安裝程式目前尚未進行程式碼簽署，系統可能顯示「未知發行者」或 SmartScreen 提示。請僅從本儲存庫的 Release 下載，並核對 GitHub 顯示的 SHA-256。

## 隱私說明

剪貼紀錄只儲存在本機，不會上傳到 ClipNest 伺服器。啟用連結預覽時，程式會存取複製連結指向的公開網站及其宣告的圖示網址；檢查更新時會連線至 GitHub。連結預覽可在設定中關閉。資料庫金鑰與目前 Windows 帳戶綁定；把資料庫和金鑰檔複製到其他電腦，通常無法直接讀取紀錄。這不等於能阻止在已登入帳戶下執行的程式讀取資料。

## 致謝與靈感

ClipNest 底部卡片式的瀏覽體驗受到 [Paste](https://pasteapp.io/) 啟發。ClipNest 是獨立開發的 Windows 應用程式，與 Paste 無關，也未使用 Paste 的品牌或素材。

| 專案 | 用途 | 授權與專案連結 |
| --- | --- | --- |
| Qt for Python / PySide6 | 桌面介面 | [LGPLv3/GPLv3 或商業授權](https://doc.qt.io/qtforpython-6/) |
| SQLCipher | 加密資料庫 | [BSD 風格授權與版權聲明](https://www.zetetic.net/sqlcipher/license/) |
| sqlcipher3 | Python 與 SQLCipher 的連接 | [PyPI](https://pypi.org/project/sqlcipher3/) |
| PyInstaller | 封裝 Windows 程式 | [授權說明](https://pyinstaller.org/en/stable/license.html) |
| Inno Setup | 製作 Windows 安裝程式 | [專案與授權資訊](https://jrsoftware.org/isinfo.php) |

第三方專案保留各自的版權與授權。檔案預覽圖示由 **[SeeRgb](https://dribbble.com/SeeRgb)** 創作，原作為 [File icon freebie](https://dribbble.com/shots/6273084-File-icon)。SeeRgb 已書面授權 ClipNest 使用、調整及再散布圖示，包括公開原始碼、安裝程式、專案截圖及後續版本。下載、分叉或再散布 ClipNest 的人也可繼續使用及修改這些圖示，包括商業用途。圖示版權仍屬 SeeRgb，**不在 ClipNest 自有程式碼的 MIT 授權範圍內**。詳見[圖示來源與授權說明](desktop/assets/file-icons/SOURCE.md)。

ClipNest 自行編寫的程式碼使用 [MIT 授權](LICENSE)。完整第三方聲明請參閱 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

## 從原始碼建置

建置環境為 Windows x64、Python 3.12、.NET 8 SDK、PySide6 6.9.2、PyInstaller 6.16.0、sqlcipher3 0.6.2 與 Inno Setup 7。使用 [`desktop/build-release.ps1`](desktop/build-release.ps1) 建置；目前原始碼位於 `desktop/versions/1.00.5/`。

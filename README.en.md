# ClipNest

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

> **A Codex Vibe Coding project.** ClipNest is developed by its maintainer in collaboration with Codex. The maintainer reviews product choices, testing, and releases.

A local clipboard history app for Windows. Text, Markdown, links, code, colors, images, and files appear as cards in a shelf at the bottom of your desktop. Open the shelf with a shortcut, find an item, and paste it again.

> Latest stable version: **1.00.7** · Windows x64 · [Download the installer](https://github.com/NigoNiko/clipnest/releases/latest)

## Screenshots

These screenshots use sample data and contain no real clipboard history.

### Light mode · All history

Browse different content types together, switch favorites, search, or filter by type.

![Clipboard history cards in light mode](docs/screenshots/history-light.png)

### Dark mode · Favorites

Colored dots distinguish favorite folders. Drag cards to arrange items within a folder.

![A favorite folder in dark mode](docs/screenshots/favorites-dark.png)

### Search and filtering

Search history as you type and narrow the list to text, Markdown, links, code, colors, images, or files.

![Search results filtered by keyword](docs/screenshots/search-light.png)

### History and privacy

Choose a retention period, exclude apps, and control whether website titles and icons are fetched.

![History and privacy settings](docs/screenshots/settings-privacy.png)

## Features

- **Find and paste quickly:** Press `Ctrl + Alt + Q` by default. Search, filter, and select with the keyboard. Paste into the previously active app or copy an item to the clipboard.
- **Useful previews:** Separate cards for text, Markdown, code, links, colors, images, and files. Markdown preserves its source and rich text; the destination app chooses the format it supports. Link previews can fetch a website title and icon.
- **Favorites:** Save frequently used items in colored folders and drag to reorder them. While ClipNest is active, `Ctrl + 1–9` and `Ctrl + 0` switch between All history and the first nine folders. Assign shortcuts to additional folders.
- **Control what is recorded:** Pause recording, set a retention period, exclude process names, and choose whether ClipNest starts with Windows. Common password managers and clipboard data marked as sensitive are skipped by default; exclusion cannot identify every secret.
- **Local data protection:** History, images, link previews, and settings are stored in a SQLCipher-encrypted database. Windows DPAPI protects its key for the current Windows account. There is no cloud sync. Backup and migration are available in Settings.
- **Updates and removal:** Installers upgrade in place. Check GitHub Releases from Settings → About. During interactive uninstall, choose whether to keep or remove local data.
- **Interface languages:** Follow the system language, or choose Simplified Chinese, Traditional Chinese, or English in Settings → Appearance. Changes apply immediately.

## Install and use

1. Download `ClipNest-1.00.7-Setup-x64.exe` from [Releases](https://github.com/NigoNiko/clipnest/releases/latest) and run it on Windows x64.
2. ClipNest stays in the system tray. Copy something, then press `Ctrl + Alt + Q` to open the shelf.
3. Select a card to reuse it. Right-click for editing, renaming, favorites, copying, and deletion.

The default installation path is `%LOCALAPPDATA%\Programs\ClipNest`; data is stored in `%LOCALAPPDATA%\ClipNest` by default. In-place updates retain data. Interactive uninstall offers a choice to remove the data and key. The [desktop guide](desktop/README.md) contains more detail (currently in Simplified Chinese).

Live blur requires the [Microsoft .NET 8 Runtime (x64)](https://dotnet.microsoft.com/download/dotnet/8.0). ClipNest offers the download page if it is missing and remains usable without it.

Version `1.34.7` was a Beta. Its numeric version comparison sees stable `1.00.0` as older, so Beta users must install a stable release manually once. Existing history and settings are retained. Future stable updates can be installed from the app.

The Windows installer is currently unsigned. Windows may show an “Unknown publisher” or SmartScreen prompt. Download only from this repository's Releases and verify the SHA-256 value shown by GitHub.

## Privacy

Clipboard history remains on your device and is not uploaded to a ClipNest server. If link previews are enabled, ClipNest visits the copied public URL and its declared icon URL. Checking for updates contacts GitHub. You can disable link previews in Settings. The database key is tied to the current Windows account; copying the database and key file to another computer normally does not make the history readable. This does not protect data from software running under your signed-in account.

## Credits and inspiration

The bottom-card browsing experience was inspired by [Paste](https://pasteapp.io/). ClipNest is an independent Windows app, is not affiliated with Paste, and uses none of its branding or assets.

| Project | Use | License and project |
| --- | --- | --- |
| Qt for Python / PySide6 | Desktop interface | [LGPLv3/GPLv3 or commercial](https://doc.qt.io/qtforpython-6/) |
| Avalonia | Windows live-blur helper and system composition | [MIT license and source](https://github.com/AvaloniaUI/Avalonia) |
| SQLCipher | Encrypted database | [BSD-style license and notices](https://www.zetetic.net/sqlcipher/license/) |
| sqlcipher3 | Python SQLCipher binding | [PyPI](https://pypi.org/project/sqlcipher3/) |
| PyInstaller | Windows packaging | [License](https://pyinstaller.org/en/stable/license.html) |
| Inno Setup | Windows installer | [Project and license](https://jrsoftware.org/isinfo.php) |

Each third-party project retains its own copyright and license. File preview icons were created by **[SeeRgb](https://dribbble.com/SeeRgb)**; see the original [File icon freebie](https://dribbble.com/shots/6273084-File-icon). SeeRgb granted written permission for ClipNest to use, adapt, and redistribute the icons in public source, installers, screenshots, and future releases. People who download, fork, or redistribute ClipNest may keep using and adapting the icons, including commercially. The icons remain SeeRgb's work and **are not covered by the MIT license for ClipNest's original code**. See the [icon attribution and permission notes](desktop/assets/file-icons/SOURCE.md).

ClipNest's original code is licensed under [MIT](LICENSE). See [third-party notices](THIRD-PARTY-NOTICES.md) for details.

## Build from source

The Windows x64 build uses Python 3.12, .NET 8 SDK, PySide6 6.9.2, PyInstaller 6.16.0, sqlcipher3 0.6.2, and Inno Setup 7. Run [`desktop/build-release.ps1`](desktop/build-release.ps1); the current source is under `desktop/versions/1.00.7/`.

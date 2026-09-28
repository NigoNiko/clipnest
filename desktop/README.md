# ClipNest desktop releases

This private repository contains the Windows ClipNest desktop source snapshots starting with Version 1.20. Version numbers use two digits after the decimal point: 1.20, 1.21, and so on through 1.99, followed by 2.00.

The `versions` directory keeps the source and PyInstaller spec used for each release. `build-release.ps1` builds a Windows artifact with Python 3.12, PySide6 6.9.2, and PyInstaller 6.16.0. Version 1.20 is a portable ZIP; Version 1.21 and later use an Inno Setup installer with one stable application identity and installation directory.

The release workflow publishes the artifacts as private GitHub Releases. The app checks the latest published Release through the GitHub REST API. A private repository requires a user's own read-only token; after the repository and Releases become public, updates work anonymously. Never add a personal token to source code, workflow files, or an installer.

Clipboard history and settings remain on the user's machine under `%LOCALAPPDATA%\ClipNest` unless the user selected a different database folder in Settings.


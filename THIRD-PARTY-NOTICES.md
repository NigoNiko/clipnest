# Third-party notices

ClipNest's own code is licensed under the [MIT License](LICENSE). The following projects retain their own copyrights and licenses. This document distinguishes libraries shipped with the app from tools used to build its installer.

The Windows installation includes this file, ClipNest's `LICENSE`, and the relevant license texts in `_internal/licenses/`. Open-source Qt shared libraries remain in `_internal/` and can be replaced there. The corresponding upstream source is available through the project links below.

## Libraries shipped with the app

### Qt for Python / PySide6 / Qt

Qt for Python provides the application UI and is available under LGPLv3/GPLv3 or a commercial license. ClipNest uses the community distribution. See the [Qt for Python licensing page](https://doc.qt.io/qtforpython-6/) and [third-party licenses in Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html). The application must preserve the user's ability to replace the shared Qt libraries under the applicable LGPL terms.

The complete LGPLv3 and GPLv3 texts are included in `_internal/licenses/`.

### SQLCipher

SQLCipher provides encrypted database storage. Copyright (c) 2025, ZETETIC LLC. It is used under the following BSD-style license. See the [SQLCipher project](https://github.com/sqlcipher/sqlcipher) and [license information](https://www.zetetic.net/sqlcipher/license/).

> Copyright (c) 2025, ZETETIC LLC
> All rights reserved.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are met:
>     * Redistributions of source code must retain the above copyright
>       notice, this list of conditions and the following disclaimer.
>     * Redistributions in binary form must reproduce the above copyright
>       notice, this list of conditions and the following disclaimer in the
>       documentation and/or other materials provided with the distribution.
>     * Neither the name of the ZETETIC LLC nor the
>       names of its contributors may be used to endorse or promote products
>       derived from this software without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY ZETETIC LLC ''AS IS'' AND ANY
> EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
> WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
> DISCLAIMED. IN NO EVENT SHALL ZETETIC LLC BE LIABLE FOR ANY
> DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
> (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
> LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
> ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
> (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
> THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

### sqlcipher3

The Python [sqlcipher3](https://github.com/coleifer/sqlcipher3) package connects the app to SQLCipher. Its source repository includes a zlib-style license with the original copyright notice. The PyPI 0.6.2 metadata identifies the package as MIT; retain the package's own license files when redistributing its source or binaries.

### OpenSSL and SQLite

SQLCipher may include or link to [OpenSSL](https://openssl-library.org/source/license/index.html) and is based on [SQLite](https://sqlite.org/copyright.html). Their own notices and licenses apply to the components present in the selected build.

### Python

The packaged application includes the Python runtime under the [Python Software Foundation License](https://docs.python.org/3/license.html). Its license text is included in `_internal/licenses/`.

## Build and installer tools

- [PyInstaller](https://pyinstaller.org/en/stable/license.html) packages the Python application. Its bootloader is included in the executable under PyInstaller's GPL license with a bundling exception.
- [Inno Setup](https://jrsoftware.org/isinfo.php) builds the Windows installer. Its own license applies to the generated installer components.

## Artwork

The file preview artwork in `desktop/assets/file-icons/` is by **[SeeRgb](https://dribbble.com/SeeRgb)**, based on the original [File icon freebie](https://dribbble.com/shots/6273084-File-icon). SeeRgb granted written permission on October 9, 2026 to use, adapt, modify, and redistribute the icons as part of ClipNest, including in public source repositories, installers, screenshots, and future releases. People who download, fork, or redistribute ClipNest may continue using and adapting the icons as part of the project, including commercially. The icons remain SeeRgb's artwork and are not covered by ClipNest's MIT license; see [SOURCE.md](desktop/assets/file-icons/SOURCE.md).

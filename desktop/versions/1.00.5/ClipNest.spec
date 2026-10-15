# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH)
host_publish = project.parents[1] / 'composition-host' / 'publish-framework'
host_data = [(str(host_publish), 'composition-host')] if (host_publish / 'dotnet-runtime-required.marker').exists() else []
a = Analysis(
    [str(project / 'clipnest.py')],
    pathex=[],
    binaries=[],
    datas=host_data + [
        (str(project / 'locales.json'), '.'),
        (str(project.parents[1] / 'assets' / 'file-icons'), 'assets/file-icons'),
        (str(project.parents[2] / 'LICENSE'), '.'),
        (str(project.parents[2] / 'THIRD-PARTY-NOTICES.md'), '.'),
        (str(project.parents[1] / 'licenses'), 'licenses'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# QWidget, QImage and the network client use Qt Core, GUI, Widgets and Network.
# PDF rendering and the QML virtual keyboard arrive through optional plugins.
unused_qt = {
    'qt6pdf.dll', 'qt6qml.dll', 'qt6qmlmeta.dll', 'qt6qmlmodels.dll',
    'qt6qmlworkerscript.dll', 'qt6quick.dll', 'qt6virtualkeyboard.dll',
    'qt6opengl.dll', 'pyside6/opengl32sw.dll',
    'pyside6/plugins/imageformats/qpdf.dll',
    'pyside6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll',
}
a.binaries = [entry for entry in a.binaries
              if entry[0].lower().replace('\\', '/') not in unused_qt]
# Keep only the Qt dialog translations used by ClipNest's three interface languages.
a.datas = [entry for entry in a.datas
           if not entry[0].lower().replace('\\', '/').startswith('pyside6/translations/')
           or entry[0].lower().replace('\\', '/').endswith(
               ('qt_zh_cn.qm', 'qtbase_zh_cn.qm', 'qt_zh_tw.qm', 'qtbase_zh_tw.qm', 'qt_en.qm', 'qtbase_en.qm'))]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ClipNest',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(project / 'ClipNest.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ClipNest',
)

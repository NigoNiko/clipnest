"""ClipNest: a local Windows clipboard shelf."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import base64
import hashlib
import ipaddress
import socket
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import zlib
from functools import lru_cache
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from urllib.error import HTTPError

from sqlcipher3 import dbapi2 as sqlite3

if os.name == "nt":
    import winreg

from PySide6.QtCore import Qt, QBuffer, QByteArray, QIODevice, QMimeData, QTimer, Signal, QObject, QPoint, QPointF, QRectF, QSize, QEvent, QEventLoop, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtGui import QAction, QColor, QCursor, QDesktopServices, QDrag, QFont, QGuiApplication, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QRegion, QKeySequence
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpacerItem, QStackedWidget, QKeySequenceEdit,
    QSizePolicy, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
)


APP = "ClipNest"
VERSION = "1.26"
GITHUB_REPO = "NigoNiko/clipnest"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}"
DEFAULT_ACCENT = "#3679d8"
ACCENT_PRESETS = ("#3679d8", "#e8908d", "#37a98f", "#825fce", "#df9a32")
BOARD_RAINBOW = (
    ("红色", "#e55454"), ("橙色", "#ee8b39"), ("黄色", "#d5b034"),
    ("绿色", "#43aa69"), ("青色", "#28a9bb"), ("蓝色", "#4d78dc"),
    ("紫色", "#9868c9"),
)
BOARD_COLORS = tuple(color for _, color in BOARD_RAINBOW)
DEFAULT_EXCLUDED = "1Password.exe, Bitwarden.exe, KeePass.exe, KeePassXC.exe, LastPass.exe, Dashlane.exe, Enpass.exe, ProtonPass.exe"
DEFAULT_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP
CONFIG_PATH = DEFAULT_DATA_DIR / "config.json"
DB_PATH = DEFAULT_DATA_DIR / "clipnest.db"
SQLITE_HEADER = b"SQLite format 3\0"
GITHUB_TOKEN_PATH = DEFAULT_DATA_DIR / "github-token.dat"
UPDATE_DIR = DEFAULT_DATA_DIR / "updates"
MAX_TEXT = 2_000_000
MAX_IMAGE = 12_000_000
MAX_MIME = 32_000_000
DEFAULT_HOTKEY = "Ctrl+Alt+Q"
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
KIND_NAMES = {"text": "文本", "link": "链接", "code": "代码", "color": "颜色", "image": "图片", "files": "文件"}
KIND_COLORS = {"text": "#c9cdd4", "link": "#9bcbb6", "code": "#3d4248", "color": "#c8b5d8", "image": "#ddaeb1", "files": "#d7c3a0"}
CARD_WIDTH = 188
CARD_HEIGHT = 176
CARD_GAP = 11
SOURCE_NAMES = {
    "weixin.exe": "微信", "wechat.exe": "微信", "wxwork.exe": "企业微信",
    "chrome.exe": "Chrome 浏览器", "msedge.exe": "Edge 浏览器", "firefox.exe": "Firefox 浏览器",
    "excel.exe": "Excel", "winword.exe": "Word", "powerpnt.exe": "PowerPoint",
    "et.exe": "WPS 表格", "wps.exe": "WPS", "wpp.exe": "WPS 演示",
    "code.exe": "VS Code", "explorer.exe": "文件资源管理器", "photos.exe": "照片",
    "chatgpt.exe": "ChatGPT", "qq.exe": "QQ", "dingtalk.exe": "钉钉", "feishu.exe": "飞书",
    "notepad.exe": "记事本", "notepad++.exe": "Notepad++", "figma.exe": "Figma",
    "outlook.exe": "Outlook", "acrobat.exe": "Adobe Acrobat", "sogouexplorer.exe": "搜狗浏览器",
}


def friendly_source(source: str) -> str:
    if not source:
        return "剪贴板"
    name = Path(source).name
    return SOURCE_NAMES.get(name.lower(), re.sub(r"[_-]+", " ", Path(name).stem).strip() or "剪贴板")


def rainbow_board_color(value: str) -> str:
    """Map existing free-form board colors to the fixed seven-color palette."""
    value = (value or "").lower()
    if value in BOARD_COLORS:
        return value
    original = QColor(value)
    if not original.isValid() or original.hue() < 0:
        return BOARD_COLORS[5]
    hue = original.hue()
    return min(BOARD_COLORS, key=lambda candidate: min(
        abs(QColor(candidate).hue() - hue), 360 - abs(QColor(candidate).hue() - hue)))


def version_parts(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d{2})", value.strip(), re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _protect_token(value: bytes, decrypt: bool = False) -> bytes:
    class DataBlob(ctypes.Structure):
        _fields_ = [("size", ctypes.wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

    source = ctypes.create_string_buffer(value)
    input_blob = DataBlob(len(value), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    output_blob = DataBlob()
    crypt32 = ctypes.windll.crypt32
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    arguments = (ctypes.byref(input_blob), None, None, None, None, flags, ctypes.byref(output_blob))
    if not function(*arguments):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.data, output_blob.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(output_blob.data, ctypes.c_void_p))


def store_key_path(path: Path) -> Path:
    return Path(str(path) + ".key")


def save_store_key(path: Path, key: bytes) -> None:
    """Keep the database key beside the database, protected for this Windows user."""
    protected = _protect_token(key)
    staging = Path(str(path) + ".new")
    try:
        staging.write_bytes(protected)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def load_store_key(path: Path) -> bytes:
    key_file = store_key_path(path)
    if key_file.exists():
        key = _protect_token(key_file.read_bytes(), decrypt=True)
        if len(key) != 32:
            raise ValueError("剪贴板数据库密钥无效，无法打开记录。")
        return key
    if path.exists() and path.stat().st_size:
        with path.open("rb") as stream:
            if stream.read(16) != SQLITE_HEADER:
                raise RuntimeError("数据库已加密，但找不到对应的密钥文件。请恢复原有的 .key 文件。")
    key = os.urandom(32)
    save_store_key(key_file, key)
    return key


def set_database_key(connection, key: bytes) -> None:
    connection.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    if not connection.execute("PRAGMA cipher_version").fetchone():
        raise RuntimeError("当前 SQLite 不支持数据库加密。")


def encrypt_legacy_store(path: Path, key: bytes) -> None:
    """Convert a plaintext SQLite database without keeping a plaintext backup."""
    staging = Path(str(path) + ".encrypted-migrating")
    if staging.exists():
        raise FileExistsError(f"加密迁移临时文件已存在：{staging}")
    source = sqlite3.connect(path)
    try:
        if source.execute("PRAGMA integrity_check").fetchall()[0][0] != "ok":
            raise RuntimeError("原数据库校验未通过，未进行加密迁移。")
        source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        if source.execute("PRAGMA journal_mode=DELETE").fetchall()[0][0].lower() != "delete":
            raise RuntimeError("无法关闭原数据库的写入日志，未进行加密迁移。")
        escaped = str(staging).replace("'", "''")
        source.execute(f"ATTACH DATABASE '{escaped}' AS encrypted KEY \"x'{key.hex()}'\"")
        try:
            source.execute("SELECT sqlcipher_export('encrypted')").fetchall()
        finally:
            source.execute("DETACH DATABASE encrypted")
        check = sqlite3.connect(staging)
        try:
            set_database_key(check, key)
            if check.execute("PRAGMA integrity_check").fetchall()[0][0] != "ok":
                raise RuntimeError("加密后的数据库校验未通过，原记录保持不变。")
            old_count = source.execute("SELECT COUNT(*) FROM clips").fetchall()[0][0]
            new_count = check.execute("SELECT COUNT(*) FROM clips").fetchall()[0][0]
            if old_count != new_count:
                raise RuntimeError("加密后的记录数量不一致，原记录保持不变。")
        finally:
            check.close()
    except Exception:
        source.close()
        staging.unlink(missing_ok=True)
        raise
    source.close()
    os.replace(staging, path)
    for suffix in ("-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def github_token() -> str:
    if not GITHUB_TOKEN_PATH.exists():
        return ""
    return _protect_token(GITHUB_TOKEN_PATH.read_bytes(), decrypt=True).decode("utf-8")


def save_github_token(value: str) -> None:
    GITHUB_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not value:
        GITHUB_TOKEN_PATH.unlink(missing_ok=True)
        return
    encrypted = _protect_token(value.encode("utf-8"))
    temporary = GITHUB_TOKEN_PATH.with_suffix(".tmp")
    temporary.write_bytes(encrypted)
    os.replace(temporary, GITHUB_TOKEN_PATH)


class GithubRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = urlparse(newurl)
        host = (target.hostname or "").lower()
        if target.scheme != "https" or not (
            host == "github.com" or host.endswith(".github.com")
            or host == "githubusercontent.com" or host.endswith(".githubusercontent.com")
        ):
            raise RuntimeError("更新下载跳转到了非 GitHub 地址，已停止下载。")
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected and urlparse(request.full_url).hostname != target.hostname:
            redirected.remove_header("Authorization")
            redirected.unredirected_hdrs.pop("Authorization", None)
        return redirected


def github_request(url: str, token: str, accept: str = "application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": f"ClipNest/{VERSION}",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return build_opener(GithubRedirect()).open(Request(url, headers=headers), timeout=20)


def latest_github_release(token: str) -> dict:
    authenticated = False
    try:
        try:
            with github_request(f"{GITHUB_API}/releases/latest", "") as response:
                release = json.load(response)
        except HTTPError as error:
            if error.code not in (403, 404) or not token:
                raise
            with github_request(f"{GITHUB_API}/releases/latest", token) as response:
                release = json.load(response)
            authenticated = True
    except HTTPError as error:
        if error.code in (401, 403, 404):
            raise RuntimeError("无法读取 GitHub 发布信息。私有仓库需要有读取权限的访问令牌；请检查“关于”页的 GitHub 凭据。") from error
        raise RuntimeError(f"GitHub 返回 HTTP {error.code}。") from error
    version = version_parts(str(release.get("tag_name", "")))
    if version is None:
        raise RuntimeError("GitHub 最新发布的版本号格式无效。")
    release["parsed_version"] = version
    release["authenticated"] = authenticated
    return release


def matching_installer(release: dict) -> dict:
    version = release["parsed_version"]
    filename = f"ClipNest-{version[0]}.{version[1]:02d}-Setup-x64.exe"
    for asset in release.get("assets", []):
        if asset.get("name") == filename and isinstance(asset.get("id"), int):
            if asset.get("size", 0) > 200_000_000:
                raise RuntimeError("安装包超过预期大小，已停止下载。")
            return asset
    raise RuntimeError(f"GitHub 发布版本缺少安装包 {filename}。")


def clear_update_cache() -> None:
    if not UPDATE_DIR.exists():
        return
    for candidate in UPDATE_DIR.iterdir():
        if candidate.is_file() and re.fullmatch(r"ClipNest-\d+\.\d{2}-Setup-x64\.exe(?:\.part)?", candidate.name):
            try:
                candidate.unlink()
            except OSError:
                pass


def download_update(release: dict, token: str) -> Path:
    asset = matching_installer(release)
    digest = asset.get("digest", "")
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise RuntimeError("GitHub 没有提供安装包的 SHA-256 校验值，已停止更新。")
    clear_update_cache()
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPDATE_DIR / asset["name"]
    temporary = destination.with_suffix(destination.suffix + ".part")
    url = f"{GITHUB_API}/releases/assets/{asset['id']}"
    hasher = hashlib.sha256()
    try:
        with github_request(url, token, "application/octet-stream") as response, temporary.open("wb") as output:
            if "json" in response.headers.get("Content-Type", "").lower():
                raise RuntimeError("GitHub 返回了发布信息而非安装包。")
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 200_000_000:
                    raise RuntimeError("安装包超过预期大小，已停止下载。")
                hasher.update(chunk)
                output.write(chunk)
        if size != asset.get("size") or hasher.hexdigest().lower() != digest[7:].lower():
            raise RuntimeError("安装包完整性校验失败，已停止更新。")
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def file_kind(path: str) -> tuple[str, str, str]:
    extension = Path(path).suffix.lower()
    groups = (
        ({".xlsx", ".xls", ".xlsm", ".xlsb", ".csv", ".ods"}, "Excel 表格", "X", "#188656"),
        ({".docx", ".doc", ".docm", ".odt", ".rtf"}, "Word 文档", "W", "#2769bb"),
        ({".pptx", ".ppt", ".pptm", ".odp"}, "PowerPoint 演示", "P", "#d66a38"),
        ({".pdf"}, "PDF 文档", "PDF", "#d95354"),
        ({".txt", ".md", ".log"}, "文本文档", "TXT", "#657c99"),
        ({".zip", ".7z", ".rar", ".tar", ".gz"}, "压缩文件", "ZIP", "#bd8b37"),
        ({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}, "图片文件", "▧", "#9a6bc0"),
    )
    for extensions, label, glyph, color in groups:
        if extension in extensions: return label, glyph, color
    return "文件", "▤", "#66758b"


def file_type_icon(path: str, count: int = 1) -> QPixmap:
    """Fill a card's preview area with a recognizable document-format mark."""
    _, glyph, hex_color = file_kind(path)
    return _render_file_type_icon(glyph, hex_color, count)


@lru_cache(maxsize=64)
def _render_file_type_icon(glyph: str, hex_color: str, count: int) -> QPixmap:
    color = QColor(hex_color)
    pix = QPixmap(150, 100); pix.fill(Qt.transparent)
    painter = QPainter(pix); painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color.lighter(550))
    painter.drawRoundedRect(QRectF(0, 0, 150, 100), 8, 8)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(QRectF(53, 10, 83, 80), 7, 7)
    painter.setPen(QPen(color.lighter(170), 1.5))
    if glyph == "X":
        for y in (27, 40, 53, 66, 79): painter.drawLine(70, y, 124, y)
        for x in (86, 104): painter.drawLine(x, 26, x, 79)
    else:
        for y, end in ((30, 122), (43, 116), (56, 124), (69, 109)):
            painter.drawLine(69, y, end, y)
    painter.setPen(Qt.NoPen); painter.setBrush(color)
    painter.drawRoundedRect(QRectF(15, 15, 64, 70), 8, 8)
    painter.setPen(QColor("#ffffff"))
    font = painter.font(); font.setBold(True); font.setPixelSize(48 if len(glyph) == 1 else 24)
    painter.setFont(font); painter.drawText(QRectF(15, 15, 64, 70), Qt.AlignCenter, glyph)
    if count > 1:
        painter.setPen(Qt.NoPen); painter.setBrush(color.darker(120))
        painter.drawRoundedRect(QRectF(120, 5, 25, 21), 7, 7)
        painter.setPen(QColor("#ffffff"))
        font.setPixelSize(12); painter.setFont(font)
        painter.drawText(QRectF(120, 5, 25, 21), Qt.AlignCenter, str(count))
    painter.end()
    return pix


def display_title(row) -> str:
    title = row["title"]
    if row["kind"] == "link":
        keys = row.keys()
        return ((row["user_title"] if "user_title" in keys else None)
                or (row["preview_title"] if "preview_title" in keys else None)
                or (row["clipboard_title"] if "clipboard_title" in keys else None)
                or title)
    if row["kind"] == "image" and title.startswith("图片 · "):
        return "图片 · " + friendly_source(title[5:])
    return title


def link_identity(url: str) -> tuple[str, str, str, str]:
    """Offline link card identity; never request or reveal the copied URL."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.lower()
    if host == "docs.google.com":
        if path.startswith("/spreadsheets/"): return "Google 表格", host, "▦", "#29a56a"
        if path.startswith("/presentation/"): return "Google 幻灯片", host, "▤", "#e6aa2d"
        return "Google 文档", host, "▤", "#4285f4"
    known = {
        "ark.xiaohongshu.com": ("小红书", "小", "#ed5158"),
        "xiaohongshu.com": ("小红书", "小", "#ed5158"),
        "xhslink.com": ("小红书", "小", "#ed5158"),
        "drive.google.com": ("Google 云端硬盘", "▲", "#34a853"),
        "github.com": ("GitHub", "GH", "#24292f"),
        "youtube.com": ("YouTube", "▶", "#ed3d3d"),
        "youtu.be": ("YouTube", "▶", "#ed3d3d"),
        "figma.com": ("Figma", "F", "#a259ff"),
        "notion.so": ("Notion", "N", "#242424"),
    }
    if host in known:
        name, glyph, color = known[host]
        return name, host, glyph, color
    site = host.split(".")[-2] if len(host.split(".")) >= 2 else host
    glyph = (site[:1] or "↗").upper()
    return host or "网页链接", host, glyph, "#438f80"


class PageTitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.social_title = ""
        self.site_name = ""
        self.icon_url = ""
        self.icon_urls: list[str] = []
        self.og_image = ""

    def handle_starttag(self, tag, attrs):
        if tag == "title": self.in_title = True
        fields = dict(attrs)
        if tag == "meta":
            key = (fields.get("property") or fields.get("name") or "").lower()
            if key in ("og:title", "twitter:title"):
                self.social_title = fields.get("content", "") or self.social_title
            elif key == "og:site_name": self.site_name = fields.get("content", "") or self.site_name
            elif key == "og:image": self.og_image = fields.get("content", "") or self.og_image
        elif tag == "link":
            rel = fields.get("rel", "").lower().split()
            href = fields.get("href", "")
            if href and ("icon" in rel or "apple-touch-icon" in rel):
                self.icon_urls.append(href)
                if "icon" in rel: self.icon_url = href

    def handle_endtag(self, tag):
        if tag == "title": self.in_title = False

    def handle_data(self, data):
        if self.in_title: self.title_parts.append(data)

    def result(self) -> str:
        title = self.social_title or "".join(self.title_parts)
        return re.sub(r"\s+", " ", title).strip()[:120]


def parse_page_metadata(body: bytes, declared_charset: str = "") -> PageTitleParser:
    """Try declared encodings, then common fallbacks when a page labels itself incorrectly."""
    candidates = [item for item in re.split(r"[,;\s]+", declared_charset.lower()) if item]
    meta = re.search(rb"charset\s*=\s*[^A-Za-z0-9_-]*([A-Za-z0-9_-]+)", body[:8192], re.I)
    if meta: candidates.append(meta.group(1).decode("ascii", errors="ignore").lower())
    candidates.extend(("utf-8", "gb18030"))
    best = None
    best_score = None
    for index, encoding in enumerate(dict.fromkeys(candidates)):
        try: decoded = body.decode(encoding, errors="replace")
        except LookupError: continue
        parser = PageTitleParser()
        parser.feed(decoded)
        title = parser.result()
        score = (20 * (title.count("\ufffd") + parser.site_name.count("\ufffd"))
                 + decoded[:8192].count("\ufffd"), index)
        if best_score is None or score < best_score:
            best, best_score = parser, score
    return best or PageTitleParser()


class ClipboardLinkParser(HTMLParser):
    def __init__(self, url: str):
        super().__init__(convert_charrefs=True)
        self.url = url.strip(); self.in_anchor = False; self.parts: list[str] = []; self.title = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a" and dict(attrs).get("href", "").strip() == self.url:
            self.in_anchor = True; self.parts = []

    def handle_endtag(self, tag):
        if tag == "a" and self.in_anchor:
            candidate = re.sub(r"\s+", " ", "".join(self.parts)).strip()
            if candidate and candidate != self.url: self.title = candidate[:120]
            self.in_anchor = False

    def handle_data(self, data):
        if self.in_anchor: self.parts.append(data)


def clipboard_link_title(url: str, html: str) -> str:
    if not html or len(html) > 262_144: return ""
    parser = ClipboardLinkParser(url)
    try: parser.feed(html)
    except (ValueError, UnicodeError): return ""
    return parser.title


def allowed_link_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host or len(url) > 2048 or parsed.username or parsed.password:
        return False
    if host.lower().endswith((".local", ".internal", ".localhost")):
        return False
    try:
        address = ipaddress.ip_address(host)
        return address.is_global
    except ValueError:
        try:
            addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
        except (OSError, ValueError): return False


class CheckedRedirect(HTTPRedirectHandler):
    def __init__(self):
        super().__init__(); self.hops = 0

    def redirect_request(self, request, fp, code, message, headers, new_url):
        self.hops += 1
        if self.hops > 3 or not allowed_link_url(new_url): return None
        return super().redirect_request(request, fp, code, message, headers, new_url)


def fetch_link_preview(url: str) -> tuple[str, str, bytes]:
    if not allowed_link_url(url): return "", "", b""
    parser = PageTitleParser()
    final_url = url
    try:
        request = Request(url, headers={"User-Agent": f"ClipNest/{VERSION}", "Accept": "text/html"})
        with build_opener(CheckedRedirect()).open(request, timeout=4) as response:
            final_url = response.geturl()
            if not allowed_link_url(final_url): return "", "", b""
            if "html" in response.headers.get("Content-Type", "").lower():
                body = response.read(524_288)
                compression = response.headers.get("Content-Encoding", "").lower()
                if compression in ("gzip", "deflate"):
                    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS if compression == "gzip" else zlib.MAX_WBITS)
                    body = inflater.decompress(body, 1_048_576)
                encoding = response.headers.get_content_charset() or ""
                parser = parse_page_metadata(body, encoding)
    except (OSError, ValueError, UnicodeError, LookupError, HTTPError, zlib.error):
        pass
    title = parser.result()
    if title.lower() in ("just a moment...", "access denied", "403 forbidden", "sign in", "log in"):
        title = ""
    site = re.sub(r"\s+", " ", parser.site_name).strip()[:80]
    if not site and urlparse(final_url).hostname != urlparse(url).hostname:
        site = link_identity(final_url)[0]
    icon = b""
    candidates = [urljoin(final_url, candidate) for candidate in parser.icon_urls]
    candidates.extend((urljoin(final_url, "/favicon.ico"), urljoin(final_url, "/apple-touch-icon.png")))
    for icon_url in dict.fromkeys(candidates):
        if not allowed_link_url(icon_url): continue
        try:
            with build_opener(CheckedRedirect()).open(Request(icon_url, headers={"User-Agent": f"ClipNest/{VERSION}", "Accept": "image/*"}), timeout=3) as response:
                data = response.read(65_537)
            if len(data) > 65_536: continue
            image = QImage.fromData(data)
            if image.isNull() or image.width() > 1024 or image.height() > 1024: continue
            image = image.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            output = QByteArray(); buffer = QBuffer(output); buffer.open(QIODevice.WriteOnly)
            image.save(buffer, "PNG"); buffer.close(); icon = bytes(output)
            break
        except (OSError, ValueError): continue
    return title, site, icon


def fetch_page_title(url: str) -> str:
    return fetch_link_preview(url)[0]


def resolve_db_path(config_path: Path = CONFIG_PATH) -> Path:
    override = os.environ.get("CLIPNEST_DATA_DIR")
    if override:
        return Path(override) / "clipnest.db"
    try:
        directory = json.loads(config_path.read_text(encoding="utf-8")).get("data_dir")
        if isinstance(directory, str) and directory:
            return Path(directory) / "clipnest.db"
    except (OSError, ValueError, TypeError):
        pass
    return DB_PATH


def pack_mime(formats: dict[str, bytes]) -> bytes:
    payload = {name: base64.b64encode(data).decode("ascii") for name, data in sorted(formats.items())}
    return zlib.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"), 6)


def unpack_mime(blob: bytes | None) -> dict[str, bytes]:
    if not blob:
        return {}
    try:
        raw = json.loads(zlib.decompress(blob))
        return {name: base64.b64decode(value, validate=True) for name, value in raw.items()}
    except (ValueError, TypeError, zlib.error):
        return {}


def hotkey_parts(sequence: str) -> tuple[int, int] | None:
    """Translate a single Qt shortcut into RegisterHotKey modifiers and a VK."""
    keys = QKeySequence(sequence)
    if keys.count() != 1:
        return None
    combination = keys[0]
    modifiers = combination.keyboardModifiers()
    key = combination.key()
    flags = 0x4000
    if modifiers & Qt.ControlModifier: flags |= 0x0002
    if modifiers & Qt.AltModifier: flags |= 0x0001
    if modifiers & Qt.ShiftModifier: flags |= 0x0004
    if modifiers & Qt.MetaModifier: flags |= 0x0008
    if flags == 0x4000:
        return None
    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        vk = int(key)
    elif Qt.Key_F1 <= key <= Qt.Key_F12:
        vk = 0x70 + key - Qt.Key_F1
    elif key == Qt.Key_Space:
        vk = 0x20
    else:
        return None
    return flags, vk


def collect_rich_formats(mime) -> dict[str, bytes]:
    """Retain transferable text formats, including Office's native Windows formats."""
    result = {}
    size = 0
    for name in mime.formats():
        low = name.lower()
        if not (low in {"text/html", "application/rtf", "text/rtf"}
                or low.startswith('application/x-qt-windows-mime;value=')):
            continue
        if any(marker in low for marker in (
            "excludeclipboard", "canincludeinclipboardhistory", "filecontents",
            "filegroupdescriptor", "object descriptor", "link source", "embedded object",
            "bitmap", "dib", "png", "jpeg", "jfif", "metafile", "image",
        )):
            continue
        try: data = bytes(mime.data(name))
        except Exception: continue
        if not data or len(data) > MAX_MIME or size + len(data) > MAX_MIME:
            continue
        result[name] = data
        size += len(data)
    return result


def windows_clipboard_unicode_text() -> str:
    """Read CF_UNICODETEXT when Qt exposes a WPS cell selection only as an image."""
    if os.name != "nt":
        return ""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.IsClipboardFormatAvailable.argtypes = [ctypes.wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = ctypes.wintypes.BOOL
    user32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
    user32.OpenClipboard.restype = ctypes.wintypes.BOOL
    user32.GetClipboardData.argtypes = [ctypes.wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.restype = ctypes.wintypes.BOOL
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    if not user32.IsClipboardFormatAvailable(13):
        return ""
    for attempt in range(3):
        if user32.OpenClipboard(None):
            break
        if attempt < 2:
            time.sleep(0.01)
    else:
        return ""
    try:
        handle = user32.GetClipboardData(13)
        if not handle:
            return ""
        size = kernel32.GlobalSize(handle)
        if not 0 < size <= (MAX_TEXT + 1) * 2:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.string_at(pointer, size).decode("utf-16-le", "replace").split("\x00", 1)[0]
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def preferred_spreadsheet_text(mime, source: str) -> str:
    formats = (name.lower() for name in mime.formats())
    spreadsheet = source.lower() in {"excel.exe", "et.exe", "wps.exe"} or any(
        marker in name for name in formats for marker in ("biff", "spreadsheet", "kingsoft"))
    if not spreadsheet and mime.hasHtml():
        spreadsheet = bool(re.search(r"<table\b", mime.html(), re.I))
    if not spreadsheet:
        return ""
    text = mime.text() if mime.hasText() else ""
    if not text.strip():
        text = windows_clipboard_unicode_text()
    return text if text.strip() else ""


def clipboard_url_without_text(mime) -> str:
    """Read an explicit URL clipboard format when no plain-text URL is present."""
    if mime.hasText() and mime.text().strip(): return ""
    if mime.hasUrls():
        remote = [item.toString() for item in mime.urls() if not item.isLocalFile()]
        if len(remote) == 1 and urlparse(remote[0]).scheme in ("http", "https"):
            return remote[0]
    for name in mime.formats():
        lower = name.lower()
        if "uniformresourcelocator" not in lower: continue
        try:
            data = bytes(mime.data(name))
            encoding = "utf-16-le" if "uniformresourcelocatorw" in lower else "utf-8"
            value = data.decode(encoding, errors="ignore").strip("\x00 \r\n\t")
            if classify(value) == "link": return value
        except (ValueError, UnicodeError): pass
    return ""


def write_config_data_dir(directory: Path, config_path: Path = CONFIG_PATH) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict): data = {}
    except (OSError, ValueError, TypeError):
        pass
    data["data_dir"] = str(directory)
    temp = config_path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, config_path)


def startup_executable() -> Path | None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve()


def startup_command() -> str | None:
    executable = startup_executable()
    return f'"{executable}" --background' if executable else None


def startup_enabled() -> bool:
    command = startup_command()
    if command is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY) as key:
            saved, _ = winreg.QueryValueEx(key, APP)
        return isinstance(saved, str) and os.path.normcase(saved) == os.path.normcase(command)
    except FileNotFoundError:
        return False


def set_startup_enabled(enabled: bool) -> None:
    command = startup_command()
    if command is None:
        raise RuntimeError("开机启动仅适用于打包后的 ClipNest.exe。")
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP, 0, winreg.REG_SZ, command)
        else:
            try: winreg.DeleteValue(key, APP)
            except FileNotFoundError: pass


def move_store(store: "Store", directory: Path, config_path: Path = CONFIG_PATH) -> "Store":
    """Backup and verify a database before switching; remove old files after success."""
    old_path = store.path.resolve()
    new_path = (directory / "clipnest.db").resolve()
    if old_path == new_path:
        return store
    new_path.parent.mkdir(parents=True, exist_ok=True)
    if new_path.exists():
        raise FileExistsError(f"目标位置已有 {new_path.name}，请选择空目录。")
    if store_key_path(new_path).exists():
        raise FileExistsError("目标位置已有数据库密钥文件，请选择空目录。")
    staging = new_path.with_suffix(".migrating")
    if staging.exists():
        raise FileExistsError(f"目标位置已有 {staging.name}，请选择空目录。")
    target = sqlite3.connect(staging)
    try:
        set_database_key(target, store.key)
        with target:
            store.db.backup(target)
        check = target.execute("PRAGMA integrity_check").fetchone()[0]
        old_count = store.db.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        new_count = target.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        if check != "ok" or old_count != new_count:
            raise RuntimeError("数据库校验未通过，原记录保持不变。")
    except Exception:
        target.close()
        staging.unlink(missing_ok=True)
        raise
    target.close()
    new_key_path = store_key_path(new_path)
    try:
        save_store_key(new_key_path, store.key)
        os.replace(staging, new_path)
    except Exception:
        staging.unlink(missing_ok=True)
        new_key_path.unlink(missing_ok=True)
        raise
    replacement = None
    try:
        replacement = Store(new_path)
        write_config_data_dir(new_path.parent, config_path)
    except Exception:
        if replacement is not None: replacement.db.close()
        new_path.unlink(missing_ok=True)
        new_key_path.unlink(missing_ok=True)
        raise
    store.db.close()
    for suffix in ("", "-wal", "-shm"):
        try: Path(str(old_path) + suffix).unlink(missing_ok=True)
        except OSError: pass
    if not old_path.exists():
        store_key_path(old_path).unlink(missing_ok=True)
    return replacement

if os.name == "nt":
    ctypes.windll.user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    ctypes.windll.user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
    ctypes.windll.kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    ctypes.windll.kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
    ctypes.windll.kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.LPWSTR, ctypes.POINTER(ctypes.wintypes.DWORD)]
    ctypes.windll.kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    ctypes.windll.user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]


def now() -> int:
    return int(time.time())


def source_app() -> str:
    """Best effort source process name for an ordinary desktop copy."""
    if os.name != "nt":
        return ""
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return ""
        try:
            name = ctypes.create_unicode_buffer(32768)
            length = ctypes.wintypes.DWORD(len(name))
            if kernel32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)):
                return Path(name.value).name
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        pass
    return ""


def classify(text: str) -> str:
    stripped = text.strip()
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", stripped) and (stripped.startswith("#") or re.search(r"[a-fA-F]", stripped)):
        return "color"
    if re.match(r"^https?://\S+$", stripped, re.I):
        return "link"
    if "\n" in stripped and (re.search(r"\b(function|def|class|const|let|import|SELECT|CREATE TABLE)\b", stripped) or "</" in stripped):
        return "code"
    return "text"


class Store:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.key = load_store_key(path)
        if path.exists():
            with path.open("rb") as stream:
                plaintext = stream.read(16) == SQLITE_HEADER
            if plaintext:
                encrypt_legacy_store(path, self.key)
        self.db = sqlite3.connect(path)
        set_database_key(self.db, self.key)
        self.db.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS boards (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, color TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS clips (
                id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                text_data TEXT NOT NULL DEFAULT '', html_data TEXT NOT NULL DEFAULT '',
                image_data BLOB, mime_data BLOB, files_data TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL UNIQUE, source TEXT NOT NULL DEFAULT '',
                captured_at INTEGER NOT NULL, board_id INTEGER REFERENCES boards(id),
                created_at INTEGER NOT NULL, board_order INTEGER
            );
            CREATE INDEX IF NOT EXISTS clips_date ON clips(captured_at DESC);
            CREATE INDEX IF NOT EXISTS clips_board ON clips(board_id);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS link_previews (
                url TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', site_name TEXT NOT NULL DEFAULT '',
                icon_data BLOB, checked_at INTEGER NOT NULL DEFAULT 0
            );
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(clips)")}
        if "mime_data" not in columns:
            self.db.execute("ALTER TABLE clips ADD COLUMN mime_data BLOB")
        if "board_order" not in columns:
            self.db.execute("ALTER TABLE clips ADD COLUMN board_order INTEGER")
            for board in self.boards():
                pinned = self.db.execute("SELECT id FROM clips WHERE board_id=? ORDER BY captured_at DESC,id DESC", (board["id"],)).fetchall()
                self.db.executemany("UPDATE clips SET board_order=? WHERE id=?", ((index, row["id"]) for index, row in enumerate(pinned)))
        if "user_title" not in columns:
            self.db.execute("ALTER TABLE clips ADD COLUMN user_title TEXT")
            for row in self.db.execute("SELECT id,title,text_data FROM clips WHERE kind='link'").fetchall():
                site, host, _, _ = link_identity(row["text_data"])
                if row["title"] not in (site, host, urlparse(row["text_data"]).netloc):
                    self.db.execute("UPDATE clips SET user_title=? WHERE id=?", (row["title"], row["id"]))
        if "clipboard_title" not in columns:
            self.db.execute("ALTER TABLE clips ADD COLUMN clipboard_title TEXT NOT NULL DEFAULT ''")
        if self.setting("link_preview_engine", "1") != "2":
            # Refresh cached failures and old icons after improving charset/favicon handling.
            self.db.execute("UPDATE link_previews SET checked_at=0")
            self.db.execute("INSERT INTO settings(key,value) VALUES('link_preview_engine','2') "
                            "ON CONFLICT(key) DO UPDATE SET value='2'")
        if self.setting("board_color_palette", "") != "1":
            for board in self.boards():
                color = rainbow_board_color(board["color"])
                if color != board["color"]:
                    self.db.execute("UPDATE boards SET color=? WHERE id=?", (color, board["id"]))
            self.db.execute("INSERT INTO settings(key,value) VALUES('board_color_palette','1') "
                            "ON CONFLICT(key) DO UPDATE SET value='1'")
        self.db.commit()

    def setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.db.commit()

    def boards(self):
        return self.db.execute("SELECT * FROM boards ORDER BY sort_order,id").fetchall()

    def add_board(self, name: str, color: str | None = None) -> int:
        if color is None:
            previous = self.db.execute("SELECT color FROM boards ORDER BY sort_order DESC,id DESC LIMIT 1").fetchone()
            choices = [candidate for candidate in BOARD_COLORS if not previous or candidate != previous[0]]
            color = random.choice(choices)
        elif color not in BOARD_COLORS:
            raise ValueError("收藏板颜色必须从彩虹七色中选择")
        order = self.db.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM boards").fetchone()[0]
        cur = self.db.execute("INSERT INTO boards(name,color,sort_order) VALUES(?,?,?)", (name.strip(), color, order))
        self.db.commit()
        return cur.lastrowid

    def set_board_color(self, board_id: int, color: str) -> None:
        if color not in BOARD_COLORS:
            raise ValueError("收藏板颜色必须从彩虹七色中选择")
        self.db.execute("UPDATE boards SET color=? WHERE id=?", (color, board_id))
        self.db.commit()

    def delete_board(self, board_id: int) -> None:
        self.db.execute("UPDATE clips SET board_id=NULL WHERE board_id=?", (board_id,))
        self.db.execute("DELETE FROM boards WHERE id=?", (board_id,))
        self.db.commit()

    def save(self, kind: str, text: str = "", html: str = "", image: bytes = b"", files: list[str] | None = None, source: str = "", mime_formats: dict[str, bytes] | None = None) -> int | None:
        files = files or []
        if len(text) > MAX_TEXT or len(image) > MAX_IMAGE:
            return None
        if not (text or image or files):
            return None
        mime_blob = pack_mime(mime_formats or {}) if mime_formats else None
        digest = hashlib.sha256(kind.encode() + b"\0" + text.encode("utf-8") + b"\0" + html.encode("utf-8") + b"\0" + image + b"\0" + json.dumps(files, ensure_ascii=False).encode() + b"\0" + (mime_blob or b"")).hexdigest()
        if kind == "image":
            title = "图片"
        elif kind == "files":
            title = Path(files[0]).name + (f" 等 {len(files)} 个文件" if len(files) > 1 else "")
        elif kind == "link":
            title = link_identity(text)[0]
        else:
            title = (text.strip().splitlines() or ["文本"])[0][:80]
        stamp = now()
        clip_title = clipboard_link_title(text, html) if kind == "link" else ""
        existing = self.db.execute("SELECT id FROM clips WHERE content_hash=?", (digest,)).fetchone()
        if existing:
            self.db.execute("UPDATE clips SET captured_at=?,source=? WHERE id=?", (stamp, source, existing[0]))
            clip_id = existing[0]
        else:
            cur = self.db.execute("""INSERT INTO clips(kind,title,text_data,html_data,image_data,mime_data,files_data,content_hash,source,captured_at,created_at,clipboard_title)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (kind, title, text, html, image or None, mime_blob, json.dumps(files, ensure_ascii=False), digest, source, stamp, stamp, clip_title))
            clip_id = cur.lastrowid
        self.db.commit()
        return clip_id

    def clips(self, board_id: int | None = None, query: str = "", kind: str = "", limit: int = 300):
        sql = "SELECT clips.id,kind,clips.title,CASE WHEN kind='link' THEN text_data ELSE substr(text_data,1,512) END AS text_data,files_data,source,captured_at,board_id,user_title,clipboard_title,link_previews.title AS preview_title,link_previews.site_name AS preview_site FROM clips LEFT JOIN link_previews ON clips.kind='link' AND link_previews.url=clips.text_data WHERE 1=1"
        args: list = []
        if board_id is not None:
            sql += " AND board_id=?"; args.append(board_id)
        if query:
            sql += " AND (clips.title LIKE ? OR text_data LIKE ? OR source LIKE ? OR user_title LIKE ? OR link_previews.title LIKE ?)"
            args.extend([f"%{query}%"] * 5)
        if kind:
            sql += " AND kind=?"; args.append(kind)
        sql += " ORDER BY " + ("COALESCE(board_order,2147483647),captured_at DESC,clips.id DESC" if board_id is not None else "captured_at DESC,clips.id DESC") + " LIMIT ?"
        args.append(limit)
        return self.db.execute(sql, args).fetchall()

    def get(self, clip_id: int):
        return self.db.execute("""SELECT clips.*,link_previews.title AS preview_title,
            link_previews.site_name AS preview_site,link_previews.icon_data AS preview_icon
            FROM clips LEFT JOIN link_previews ON clips.kind='link' AND link_previews.url=clips.text_data
            WHERE clips.id=?""", (clip_id,)).fetchone()

    def image_data(self, clip_id: int) -> bytes | None:
        row = self.db.execute("SELECT image_data FROM clips WHERE id=?", (clip_id,)).fetchone()
        return row[0] if row else None

    def link_icon(self, url: str) -> bytes | None:
        row = self.db.execute("SELECT icon_data FROM link_previews WHERE url=?", (url,)).fetchone()
        return row[0] if row else None

    def set_fetched_link_title(self, clip_id: int, url: str, title: str) -> bool:
        return self.set_link_preview(url, title, "", b"")

    def link_preview_due(self, url: str, retry: bool = False) -> bool:
        if retry: return True
        row = self.db.execute("SELECT title,site_name,icon_data,checked_at FROM link_previews WHERE url=?", (url,)).fetchone()
        if not row: return True
        ttl = 7 * 86400 if (row["title"] or row["site_name"] or row["icon_data"]) else 86400
        return now() - row["checked_at"] >= ttl

    def set_link_preview(self, url: str, title: str, site: str, icon: bytes) -> bool:
        old = self.db.execute("SELECT title,site_name,icon_data FROM link_previews WHERE url=?", (url,)).fetchone()
        self.db.execute("""INSERT INTO link_previews(url,title,site_name,icon_data,checked_at) VALUES(?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET title=excluded.title,site_name=excluded.site_name,
            icon_data=excluded.icon_data,checked_at=excluded.checked_at""", (url, title[:120], site[:80], icon or None, now()))
        self.db.commit()
        return old is None or old["title"] != title or old["site_name"] != site or old["icon_data"] != (icon or None)

    def set_board(self, clip_id: int, board_id: int | None):
        order = None
        if board_id is not None:
            order = self.db.execute("SELECT COALESCE(MIN(board_order),0)-1 FROM clips WHERE board_id=?", (board_id,)).fetchone()[0]
        self.db.execute("UPDATE clips SET board_id=?,board_order=? WHERE id=?", (board_id, order, clip_id)); self.db.commit()

    def reorder_board_clip(self, board_id: int, clip_id: int, target_id: int, before: bool) -> bool:
        ordered = [row[0] for row in self.db.execute(
            "SELECT id FROM clips WHERE board_id=? ORDER BY COALESCE(board_order,2147483647),captured_at DESC,id DESC",
            (board_id,))]
        if clip_id not in ordered or target_id not in ordered or clip_id == target_id: return False
        ordered.remove(clip_id)
        target_index = ordered.index(target_id) + (0 if before else 1)
        ordered.insert(target_index, clip_id)
        with self.db:
            self.db.executemany("UPDATE clips SET board_order=? WHERE id=? AND board_id=?",
                                ((index, ident, board_id) for index, ident in enumerate(ordered)))
        return True

    def rename(self, clip_id: int, title: str):
        row = self.get(clip_id)
        column = "user_title" if row and row["kind"] == "link" else "title"
        self.db.execute(f"UPDATE clips SET {column}=? WHERE id=?", (title[:120], clip_id)); self.db.commit()

    def clear_link_title(self, clip_id: int):
        self.db.execute("UPDATE clips SET user_title=NULL WHERE id=? AND kind='link'", (clip_id,))
        self.db.commit()

    def edit_text(self, clip_id: int, text: str):
        row = self.get(clip_id)
        if not row: return
        digest = hashlib.sha256(row["kind"].encode() + b"\0" + text.encode("utf-8") + b"\0\0\0" + row["files_data"].encode() + b"\0").hexdigest()
        try:
            self.db.execute("UPDATE clips SET text_data=?,html_data='',mime_data=NULL,content_hash=? WHERE id=?", (text, digest, clip_id))
            self.db.commit()
        except sqlite3.IntegrityError:
            self.db.rollback()

    def delete(self, clip_id: int):
        self.db.execute("DELETE FROM clips WHERE id=?", (clip_id,)); self.db.commit()

    def clear_history(self):
        self.db.execute("DELETE FROM clips WHERE board_id IS NULL"); self.db.commit()

    def expiring_count(self, days: int) -> int:
        if days <= 0:
            return 0
        return self.db.execute("SELECT COUNT(*) FROM clips WHERE board_id IS NULL AND captured_at < ?", (now() - days * 86400,)).fetchone()[0]

    def prune(self) -> int:
        days = int(self.setting("retention", "30"))
        if days > 0:
            removed = self.db.execute("DELETE FROM clips WHERE board_id IS NULL AND captured_at < ?", (now() - days * 86400,)).rowcount
            self.db.commit()
            return removed
        return 0


class Hotkey(QObject):
    activated = Signal(int)
    status = Signal(bool)

    CHANGE_MESSAGE = 0x8000 + 77

    def __init__(self, shortcut: str = DEFAULT_HOTKEY):
        super().__init__()
        self.thread_id = 0
        self.running = True
        self.shortcut = shortcut
        self.pending_shortcut = None
        self.change_done = threading.Event()
        self.change_ok = False
        self.worker = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.worker.start()

    def _run(self):
        if os.name != "nt":
            self.status.emit(False); return
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self.thread_id = kernel32.GetCurrentThreadId()
        # The second shortcut pauses capture; registration belongs to this thread.
        parts = hotkey_parts(self.shortcut) or hotkey_parts(DEFAULT_HOTKEY)
        registered = bool(user32.RegisterHotKey(None, 1, *parts))
        pause_registered = bool(user32.RegisterHotKey(None, 2, 0x0002 | 0x0004 | 0x4000, ord("C")))
        self.status.emit(registered)
        msg = ctypes.wintypes.MSG()
        while self.running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:
                self.activated.emit(int(msg.wParam))
            elif msg.message == self.CHANGE_MESSAGE:
                desired = self.pending_shortcut
                wanted_parts = hotkey_parts(desired) if desired else None
                if registered: user32.UnregisterHotKey(None, 1)
                self.change_ok = bool(wanted_parts and user32.RegisterHotKey(None, 1, *wanted_parts))
                if self.change_ok:
                    self.shortcut = desired
                    registered = True
                else:
                    registered = bool(user32.RegisterHotKey(None, 1, *parts))
                if self.change_ok: parts = wanted_parts
                self.status.emit(registered)
                self.change_done.set()
        if registered: user32.UnregisterHotKey(None, 1)
        if pause_registered: user32.UnregisterHotKey(None, 2)

    def stop(self):
        self.running = False
        if self.thread_id and os.name == "nt":
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)

    def change(self, shortcut: str) -> bool:
        if not hotkey_parts(shortcut) or shortcut == "Ctrl+Shift+C" or not self.thread_id:
            return False
        self.pending_shortcut = shortcut
        self.change_done.clear()
        ctypes.windll.user32.PostThreadMessageW(self.thread_id, self.CHANGE_MESSAGE, 0, 0)
        return self.change_done.wait(2) and self.change_ok


def app_icon() -> QIcon:
    pix = QPixmap(256, 256); pix.fill(Qt.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.Antialiasing); p.scale(4, 4)
    p.setPen(Qt.NoPen); p.setBrush(QColor("#2164c4")); p.drawRoundedRect(3, 3, 58, 58, 18, 18)
    p.setBrush(QColor("#88baff")); p.drawRoundedRect(14, 12, 31, 38, 6, 6)
    p.setBrush(QColor("#ffffff")); p.drawRoundedRect(19, 17, 31, 38, 6, 6)
    p.setBrush(QColor("#3679d8")); p.drawRoundedRect(25, 27, 19, 4, 2, 2); p.drawRoundedRect(25, 36, 15, 4, 2, 2)
    p.end(); return QIcon(pix)


def theme_accent() -> QColor:
    app = QApplication.instance()
    value = app.property("theme_accent") if app else None
    color = QColor(value or DEFAULT_ACCENT)
    return color if color.isValid() else QColor(DEFAULT_ACCENT)


def theme_tint(alpha: int = 25) -> QColor:
    color = theme_accent()
    return QColor(round(255 + (color.red() - 255) * alpha / 100),
                  round(255 + (color.green() - 255) * alpha / 100),
                  round(255 + (color.blue() - 255) * alpha / 100))


def theme_style(accent: str) -> str:
    color = QColor(accent) if QColor(accent).isValid() else QColor(DEFAULT_ACCENT)
    return (STYLE.replace("#e8908d", color.name())
                 .replace("#edaaa7", color.lighter(155).name())
                 .replace("#d77a78", color.darker(115).name())
                 .replace("#dca9a6", color.lighter(155).name())
                 .replace("#f7e9e8", theme_tint(12).name()))


STYLE = """
QWidget { font-family: 'Segoe UI', 'Microsoft YaHei'; color: #292936; }
QLabel#brand { font-size: 17px; font-weight: 800; color: #282633; }
QLabel#subtle, QLabel#meta { color: #928c96; font-size: 11px; }
QLineEdit { background: #fff; border: 1px solid #e5e0e5; border-radius: 10px; padding: 8px 11px; font-size: 12px; selection-background-color: #edaaa7; }
QLineEdit:focus { border: 1px solid #e8908d; }
QLineEdit#searchField { background: transparent; border: 0; padding: 0; }
QKeySequenceEdit { background: #fff; border: 1px solid #e5e0e5; border-radius: 10px; padding: 6px 10px; min-height: 22px; }
QKeySequenceEdit:focus { border: 1px solid #e8908d; }
QPushButton { background: transparent; border: 0; border-radius: 9px; padding: 7px 11px; font-size: 12px; }
QPushButton:hover { background: #eee9ed; }
QPushButton#activeTab { background: #fff; color: #302b35; font-weight: 700; }
QPushButton#accent { background-color: #e8908d; border: 1px solid #e8908d; color: #fff; font-weight: 700; }
QPushButton#accent:hover { background-color: #d77a78; border-color: #d77a78; }
QPushButton#quiet { color: #827b86; }
QFrame#card { background: #fff; border: 1px solid #e8e3e8; border-radius: 15px; }
QFrame#card:hover { border: 1px solid #dca9a6; }
QLabel#cardTitle { font-size: 12px; font-weight: 700; }
QLabel#preview { font-size: 13px; color: #423e48; }
QScrollArea { border: 0; background: transparent; }
QMenu { background: transparent; border: 0; padding: 6px; }
QMenu::item { padding: 7px 25px 7px 13px; border-radius: 6px; }
QMenu::item:selected { background: #f7e9e8; }
QMenu::separator { height: 1px; background: #eee9ed; margin: 5px 8px; }
QDialog { background: #faf8fa; }
QFrame#settingsSidebar { background: #f1eef2; border-radius: 12px; }
QFrame#settingsPanel { background: #fff; border: 1px solid #e8e3e8; border-radius: 12px; }
QPushButton#settingsNav { text-align: left; padding: 9px 12px; color: #625c68; border-radius: 8px; }
QPushButton#settingsNav:checked { background: #f7e9e8; color: #e8908d; font-weight: 700; }
QPushButton#secondaryAction { background: #fff; border: 1px solid #e5e0e5; }
QPushButton#secondaryAction:hover { border: 1px solid #dca9a6; background: #faf8fa; }
QPushButton#danger { color: #b94d5c; border: 1px solid #e8c5cb; background: #fff; }
QPushButton#danger:hover { background: #fff2f4; }
QTextEdit { background: #fff; border: 1px solid #e5e0e5; border-radius: 10px; padding: 10px; }
"""


class StyledComboBox(QPushButton):
    currentIndexChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(34)
        self._items = []
        self._index = -1
        self._menu = RoundedMenu(self)
        self.clicked.connect(self.showPopup)

    def addItem(self, label: str, data=None):
        index = len(self._items)
        self._items.append((label, data))
        action = self._menu.addAction(label)
        action.triggered.connect(lambda checked=False, value=index: self.setCurrentIndex(value))
        if self._index < 0: self.setCurrentIndex(0)

    def addItems(self, labels):
        for label in labels: self.addItem(label)

    def currentIndex(self) -> int:
        return self._index

    def setCurrentIndex(self, index: int):
        if not 0 <= index < len(self._items) or index == self._index: return
        self._index = index
        self.setAccessibleName(self._items[index][0])
        self.update()
        self.currentIndexChanged.emit(index)

    def currentData(self):
        return self._items[self._index][1] if self._index >= 0 else None

    def showPopup(self):
        self._menu.setMinimumWidth(self.width())
        self._menu.popup(self.mapToGlobal(QPoint(0, self.height() + 4)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(theme_accent() if self.underMouse() or self.hasFocus() else QColor("#e5e0e5"), 1))
        painter.setBrush(QColor("#fff"))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 10, 10)
        if self._index >= 0:
            painter.setPen(QColor("#292936"))
            painter.drawText(self.rect().adjusted(4, 0, -25, 0), Qt.AlignCenter,
                             self._items[self._index][0])
        painter.setPen(QPen(QColor("#8c8590"), 1.5))
        x, y = self.width() - 15, self.height() // 2
        painter.drawLine(x - 4, y - 2, x, y + 2)
        painter.drawLine(x, y + 2, x + 4, y - 2)
        painter.end()


class RoundedMenu(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._actions: list[QAction] = []
        self._submenus: dict[QAction, RoundedMenu] = {}
        self._rows: list[tuple[QAction, QRectF]] = []
        self._hovered: QAction | None = None
        self._selected: QAction | None = None
        self._loop: QEventLoop | None = None
        self._parent_menu: RoundedMenu | None = None
        self._open_child: RoundedMenu | None = None
        self._title = ""

    def setTitle(self, title: str):
        self._title = title

    def title(self) -> str:
        return self._title

    def addAction(self, label):
        action = label if isinstance(label, QAction) else QAction(label, self)
        self._actions.append(action)
        return action

    def addActions(self, actions):
        for action in actions: self.addAction(action)

    def actions(self):
        return list(self._actions)

    def addSeparator(self):
        action = QAction(self)
        action.setSeparator(True)
        self._actions.append(action)
        return action

    def addMenu(self, submenu):
        action = self.addAction(submenu.title())
        self._submenus[action] = submenu
        submenu._parent_menu = self
        return action

    def _layout_rows(self):
        metrics = self.fontMetrics()
        width = max(self.minimumWidth(), max((metrics.horizontalAdvance(a.text().replace("&", "")) for a in self._actions), default=40) + 48, 96)
        y = 6
        rows = []
        for action in self._actions:
            height = 10 if action.isSeparator() else 30
            rows.append((action, QRectF(5, y, width - 10, height)))
            y += height
        self._rows = rows
        self.resize(width, y + 6)

    def popup(self, pos):
        self._selected = None
        self._layout_rows()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        x = min(max(pos.x(), available.left()), available.right() - self.width() + 1)
        y = min(max(pos.y(), available.top()), available.bottom() - self.height() + 1)
        self.move(x, y)
        self.show()
        self.raise_()
        self.setFocus(Qt.PopupFocusReason)

    def exec(self, pos):
        self.popup(pos)
        self._loop = QEventLoop(self)
        self._loop.exec()
        self._loop = None
        return self._selected

    def _root(self):
        menu = self
        while menu._parent_menu is not None: menu = menu._parent_menu
        return menu

    def _choose(self, action):
        root = self._root()
        root._selected = action
        if root._open_child: root._open_child.close()
        root.close()
        action.trigger()

    def _action_at(self, point):
        return next((a for a, rect in self._rows if rect.contains(point) and not a.isSeparator()), None)

    def _open_submenu(self, action):
        child = self._submenus.get(action)
        if child is None: return False
        if self._open_child and self._open_child is not child: self._open_child.close()
        self._open_child = child
        rect = next(rect for a, rect in self._rows if a is action)
        child.popup(self.mapToGlobal(QPoint(self.width() - 2, int(rect.top()))))
        return True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 11, 11)
        for action, rect in self._rows:
            if action.isSeparator():
                painter.setPen(QPen(QColor("#eee9ed"), 1))
                painter.drawLine(QPointF(rect.left() + 5, rect.center().y()), QPointF(rect.right() - 5, rect.center().y()))
                painter.setPen(Qt.NoPen)
                continue
            if action is self._hovered and action.isEnabled():
                painter.setBrush(theme_tint(12))
                painter.drawRoundedRect(rect.adjusted(2, 1, -2, -1), 6, 6)
            swatch = action.data()
            has_swatch = isinstance(swatch, str) and swatch in BOARD_COLORS
            if has_swatch:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(swatch))
                painter.drawEllipse(QPointF(rect.left() + 15, rect.center().y()), 4, 4)
            painter.setPen(QColor("#292936" if action.isEnabled() else "#aaa4ad"))
            painter.drawText(rect.adjusted(27 if has_swatch else 12, 0, -20, 0),
                             Qt.AlignVCenter | Qt.AlignLeft, action.text().replace("&", ""))
            if action.isCheckable() and action.isChecked():
                painter.drawText(rect.adjusted(0, 0, -12, 0), Qt.AlignVCenter | Qt.AlignRight, "✓")
            if action in self._submenus:
                painter.drawText(rect.adjusted(0, 0, -12, 0), Qt.AlignVCenter | Qt.AlignRight, "›")
            painter.setPen(Qt.NoPen)
        painter.end()

    def mouseMoveEvent(self, event):
        hovered = self._action_at(event.position())
        if hovered is not self._hovered:
            self._hovered = hovered
            self.update()
            if hovered in self._submenus:
                QTimer.singleShot(180, lambda action=hovered: self._open_submenu(action) if self._hovered is action else None)

    def mouseReleaseEvent(self, event):
        action = self._action_at(event.position())
        if event.button() == Qt.LeftButton and action and action.isEnabled():
            if not self._open_submenu(action): self._choose(action)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close(); return
        selectable = [a for a in self._actions if not a.isSeparator() and a.isEnabled()]
        if event.key() in (Qt.Key_Down, Qt.Key_Up) and selectable:
            index = selectable.index(self._hovered) if self._hovered in selectable else (-1 if event.key() == Qt.Key_Down else 0)
            self._hovered = selectable[(index + (1 if event.key() == Qt.Key_Down else -1)) % len(selectable)]
            self.update(); return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Right) and self._hovered:
            if not self._open_submenu(self._hovered): self._choose(self._hovered)
            return
        if event.key() == Qt.Key_Left and self._parent_menu:
            self.close(); self._parent_menu.setFocus(); return
        super().keyPressEvent(event)

    def hideEvent(self, event):
        if self._open_child:
            self._open_child.close()
            self._open_child = None
        if self._loop and self._loop.isRunning(): self._loop.quit()
        super().hideEvent(event)

class RoundedPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#e9e4e8"), 1))
        painter.setBrush(QColor("#f7f5f6"))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 22, 22)
        painter.end()


def exec_standard_rounded_menu(widget, event):
    original = widget.createStandardContextMenu()
    menu = RoundedMenu(widget)
    menu.addActions(original.actions())
    menu.exec(event.globalPos())
    menu.deleteLater()
    original.deleteLater()


class RoundedLineEdit(QLineEdit):
    def contextMenuEvent(self, event):
        exec_standard_rounded_menu(self, event)


class SearchField(RoundedLineEdit):
    expand_requested = Signal()
    collapse_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("searchField")
        self.setFixedHeight(34)
        self.setFixedWidth(34)
        self.setTextMargins(35, 0, 8, 0)
        self.expanded = False
        self.set_expanded(False)

    def set_expanded(self, expanded: bool):
        self.expanded = expanded
        self.setReadOnly(not expanded)
        self.setPlaceholderText("搜索剪贴板  Ctrl + F" if expanded else "")
        self.setToolTip("点击放大镜收起搜索" if expanded else "展开搜索（Ctrl + F）")
        self.setCursor(Qt.IBeamCursor if expanded else Qt.PointingHandCursor)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(theme_accent() if self.expanded and self.hasFocus() else QColor("#e5e0e5"), 1))
        painter.setBrush(QColor("#ffffff"))
        progress = max(0.0, min(1.0, (self.width() - 34) / 201))
        radius = 17 - 7 * progress
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), radius, radius)
        painter.end()
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#807b86"), 1.8)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(QRectF(9.5, 9.5, 11, 11))
        painter.drawLine(QPointF(19.5, 19.5), QPointF(24.5, 24.5))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and (not self.expanded or event.position().x() < 32):
            (self.collapse_requested if self.expanded else self.expand_requested).emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.expanded:
            self.collapse_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class RoundedTextEdit(QTextEdit):
    def contextMenuEvent(self, event):
        exec_standard_rounded_menu(self, event)


class RecordingStatusButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.setFixedSize(104, 34)
        self.set_paused(False)

    def set_paused(self, paused: bool):
        self.paused = paused
        if paused:
            self.state_text = "已暂停记录"
            self.indicator_color = QColor("#d6a13d")
            self.setToolTip("记录已暂停，点击恢复")
        else:
            self.state_text = "正在记录"
            self.indicator_color = QColor("#43aa6a")
            self.setToolTip("正在记录，点击暂停")
        self.setAccessibleName(self.state_text)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        active = self.underMouse()
        background = "#ffefd2" if active and self.paused else "#ddf1e2" if active else "#fff6e5" if self.paused else "#eaf7ed"
        border = "#f0dfb9" if self.paused else "#d5ebda"
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 10, 10)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.indicator_color)
        painter.drawEllipse(QPointF(13, self.height() / 2), 3.3, 3.3)
        painter.setPen(QColor("#3c3a43"))
        painter.drawText(self.rect(), Qt.AlignCenter, self.state_text)
        painter.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class BoardTabButton(QPushButton):
    def __init__(self, label: str, color: str, selected: bool):
        super().__init__(label)
        self.indicator_color = QColor(color)
        self.selected = selected
        self.setFixedHeight(31)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        return QSize(max(58, self.fontMetrics().horizontalAdvance(self.text()) + 40), 31)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(theme_accent().lighter(155) if self.selected else QColor("#e6e2e6"), 1))
        painter.setBrush(theme_tint(13) if self.selected else QColor("#f9f9fa" if self.underMouse() else "#ffffff"))
        painter.drawRoundedRect(QRectF(1.2, 1.2, self.width() - 2.4, self.height() - 2.4), 9, 9)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.indicator_color)
        painter.drawEllipse(QPointF(14, self.height() / 2), 3.5, 3.5)
        font = self.font()
        font.setBold(self.selected)
        painter.setFont(font)
        painter.setPen(theme_accent() if self.selected else QColor("#202026"))
        painter.drawText(QRectF(25, 0, self.width() - 33, self.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, self.text())
        painter.end()


class HeaderIconButton(QPushButton):
    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol
        self.setFixedSize(34, 34)
        self.setCursor(Qt.PointingHandCursor)
        if symbol == "pin": self.setCheckable(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        checked = self.symbol == "pin" and self.isChecked()
        painter.setPen(QPen(theme_accent().lighter(155) if checked else QColor("#e5e0e5"), 1))
        painter.setBrush(theme_tint(13) if checked else QColor("#f7f3f6" if self.underMouse() else "#fff"))
        painter.drawEllipse(QRectF(0.5, 0.5, 33, 33))
        icon_pen = QPen(theme_accent() if checked else QColor("#807b86"), 1.8)
        icon_pen.setCapStyle(Qt.RoundCap)
        icon_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(icon_pen)
        painter.setBrush(Qt.NoBrush)
        if self.symbol == "search":
            painter.drawEllipse(QRectF(9.5, 9.5, 11, 11))
            painter.drawLine(QPointF(19.5, 19.5), QPointF(24.5, 24.5))
        else:
            # Match the rounded pushpin shown in the design reference.
            painter.save()
            painter.translate(9, 9)
            painter.scale(16 / 24, 16 / 24)
            painter.setPen(QPen(theme_accent() if checked else QColor("#807b86"), 2,
                                Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            head = QPainterPath(QPointF(9, 10.76))
            head.lineTo(9, 7)
            head.cubicTo(9, 6.45, 8.55, 6, 8, 6)
            head.cubicTo(6.9, 6, 6, 5.1, 6, 4)
            head.cubicTo(6, 2.9, 6.9, 2, 8, 2)
            head.lineTo(16, 2)
            head.cubicTo(17.1, 2, 18, 2.9, 18, 4)
            head.cubicTo(18, 5.1, 17.1, 6, 16, 6)
            head.cubicTo(15.45, 6, 15, 6.45, 15, 7)
            head.lineTo(15, 10.76)
            head.cubicTo(15, 11.52, 15.43, 12.21, 16.11, 12.55)
            head.lineTo(17.89, 13.45)
            head.cubicTo(18.57, 13.79, 19, 14.48, 19, 15.24)
            head.lineTo(19, 16)
            head.cubicTo(19, 16.55, 18.55, 17, 18, 17)
            head.lineTo(6, 17)
            head.cubicTo(5.45, 17, 5, 16.55, 5, 16)
            head.lineTo(5, 15.24)
            head.cubicTo(5, 14.48, 5.43, 13.79, 6.11, 13.45)
            head.lineTo(7.89, 12.55)
            head.cubicTo(8.57, 12.21, 9, 11.52, 9, 10.76)
            painter.drawPath(head)
            painter.drawLine(QPointF(12, 17), QPointF(12, 23.5))
            painter.restore()
        painter.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class HeaderTextButton(QPushButton):
    def __init__(self, label: str):
        super().__init__(label)
        self.setFixedSize(52, 34)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#e5e0e5"), 1))
        painter.setBrush(QColor("#f7f3f6" if self.underMouse() else "#fff"))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 10, 10)
        painter.setPen(QColor("#746d78"))
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())
        painter.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class ShelfScrollArea(QScrollArea):
    def wheelEvent(self, event):
        # A horizontal shelf uses both mouse wheels and trackpad swipes for navigation.
        pixel = event.pixelDelta()
        angle = event.angleDelta()
        delta = pixel.x() or pixel.y()
        if not delta:
            delta = round((angle.x() or angle.y()) * 0.8)
        bar = self.horizontalScrollBar()
        if delta and bar.maximum():
            bar.setValue(bar.value() - delta)
        event.accept()


class SelectionOutline(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.selected = False
        self.drop_before: bool | None = None

    def set_state(self, selected: bool | None = None, drop_before: bool | None = None):
        if selected is not None: self.selected = selected
        self.drop_before = drop_before
        self.setVisible(self.selected or self.drop_before is not None)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        if self.selected:
            painter.setPen(QPen(theme_accent(), 3))
            painter.drawRoundedRect(QRectF(1.5, 1.5, self.width() - 3, self.height() - 3), 14, 14)
        if self.drop_before is not None:
            painter.setPen(QPen(theme_accent().darker(115), 4, Qt.SolidLine, Qt.RoundCap))
            x = 3 if self.drop_before else self.width() - 3
            painter.drawLine(QPointF(x, 12), QPointF(x, self.height() - 12))
        painter.end()


class Card(QFrame):
    clicked = Signal(int)
    menu_requested = Signal(int, object)
    key_requested = Signal(object)
    drop_requested = Signal(int, int, bool)
    drag_finished = Signal()

    def __init__(self, clip, image_data: bytes | None = None):
        super().__init__(); self.clip = clip
        self.setObjectName("card"); self.setFixedSize(CARD_WIDTH, CARD_HEIGHT); self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        self.drag_enabled = False
        self._press_pos = None
        self._dragging = False
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        kind = clip["kind"]
        head = QLabel("●  " + KIND_NAMES.get(kind, kind)); head.setFixedHeight(24)
        head.setStyleSheet(f"background:{KIND_COLORS.get(kind,'#ddd')}; border-top-left-radius:14px;border-top-right-radius:14px;padding-left:10px;font-size:10px;font-weight:800;color:{'#ffffff' if kind == 'code' else '#302d36'};")
        outer.addWidget(head)
        body = QFrame(); body.setStyleSheet("background:#fff;")
        b = QVBoxLayout(body); b.setContentsMargins(11, 10, 11, 8)
        preview = QLabel(); preview.setObjectName("preview"); preview.setWordWrap(True)
        preview.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        if kind == "image":
            preview.setAlignment(Qt.AlignCenter)
            if image_data:
                pixmap = QPixmap(); pixmap.loadFromData(image_data)
                preview.setPixmap(pixmap.scaled(CARD_WIDTH - 26, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                preview.setText("▧  图片预览")
            preview.setStyleSheet("background:#f7e9ed;border-radius:7px;color:#be778e;font-size:15px;")
        elif kind == "color":
            color = clip["text_data"].strip(); color = color if color.startswith("#") else "#" + color
            preview.setText(color.upper()); preview.setAlignment(Qt.AlignCenter)
            preview.setStyleSheet(f"background:{color};border-radius:7px;color:{'#fff' if QColor(color).lightness()<140 else '#25212a'};font-weight:800;")
        elif kind == "files":
            file_paths = json.loads(clip["files_data"])
            path = file_paths[0] if file_paths else ""
            preview.setAlignment(Qt.AlignCenter)
            preview.setPixmap(file_type_icon(path, len(file_paths)))
            preview.setToolTip(file_kind(path)[0] if len(file_paths) == 1 else f"{file_kind(path)[0]} · {len(file_paths)} 个文件")
            preview.setStyleSheet("background:#ffffff;border-radius:8px;")
        elif kind == "link":
            name, host, glyph, color = link_identity(clip["text_data"])
            name = display_title(clip)
            site = clip["preview_site"] or link_identity(clip["text_data"])[0]
            link_box = QFrame()
            link_box.setObjectName("linkPreview")
            link_box.setStyleSheet("QFrame#linkPreview { background:#eaf6f2; border-radius:8px; }")
            link_layout = QVBoxLayout(link_box)
            link_layout.setContentsMargins(10, 4, 10, 4)
            link_layout.setSpacing(1)
            badge = QLabel(glyph)
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(42, 42)
            if clip["preview_icon"]:
                icon_image = QPixmap(); icon_image.loadFromData(clip["preview_icon"])
                if not icon_image.isNull(): badge.setPixmap(icon_image.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                badge.setStyleSheet("background:#fff;color:#25483f;border-radius:10px;")
            else:
                badge.setStyleSheet(f"background:{color};color:white;border-radius:10px;font-size:15px;font-weight:800;")
            link_layout.addWidget(badge)
            link_layout.addStretch(1)
            name_label = QLabel(name)
            name_label.setTextFormat(Qt.PlainText)
            name_label.setWordWrap(True)
            name_label.setFixedHeight(30)
            name_label.setStyleSheet("background:transparent;font-size:13px;font-weight:700;color:#25483f;")
            name_label.setToolTip(name)
            name_label.setText(name[:80])
            link_layout.addWidget(name_label)
            domain = QLabel(site if site != name else host)
            domain.setTextFormat(Qt.PlainText)
            domain.setStyleSheet("background:transparent;font-size:10px;color:#63877d;")
            domain.setText(domain.fontMetrics().elidedText(domain.text(), Qt.ElideRight, CARD_WIDTH - 50))
            link_layout.addWidget(domain)
            preview = link_box
        else:
            value = clip["text_data"].strip()
            preview.setText(value[:230] + ("…" if len(value) > 230 else ""))
            if kind == "code": preview.setStyleSheet("background:#151515;color:#ffffff;border-radius:7px;padding:6px;font-family:Consolas;font-size:10px;")
        preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); b.addWidget(preview)
        outer.addWidget(body, 1)
        foot = QFrame(); foot.setFixedHeight(34); foot.setStyleSheet("background:#fff;border-bottom-left-radius:14px;border-bottom-right-radius:14px;")
        fl = QVBoxLayout(foot); fl.setContentsMargins(10, 0, 10, 6); fl.setSpacing(1)
        shown_title = link_identity(clip["text_data"])[1] if kind == "link" else display_title(clip)
        title = QLabel(shown_title); title.setObjectName("cardTitle"); title.setToolTip(shown_title)
        title.setText(title.fontMetrics().elidedText(shown_title, Qt.ElideRight, CARD_WIDTH - 22)); fl.addWidget(title)
        age = max(0, now() - clip["captured_at"])
        when = "刚刚" if age < 60 else f"{age//60} 分钟前" if age < 3600 else f"{age//3600} 小时前" if age < 86400 else f"{age//86400} 天前"
        meta = QLabel(friendly_source(clip["source"]) + " · " + when + ("  ◆" if clip["board_id"] else "")); meta.setObjectName("meta"); fl.addWidget(meta)
        outer.addWidget(foot)
        self.outline = SelectionOutline(self)
        self.outline.setGeometry(self.rect())
        self.outline.hide()

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.outline.set_state(selected=selected)
        if self.outline.isVisible(): self.outline.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._dragging = False
            event.accept()
            return
        if event.button() == Qt.RightButton: self.menu_requested.emit(self.clip["id"], event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.drag_enabled and self._press_pos is not None and event.buttons() & Qt.LeftButton
                and (event.position().toPoint() - self._press_pos).manhattanLength() >= QApplication.startDragDistance()):
            self._dragging = True
            mime = QMimeData()
            mime.setData("application/x-clipnest-board-card", f"{self.clip['board_id']}:{self.clip['id']}".encode())
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.setPixmap(self.grab())
            drag.setHotSpot(self._press_pos)
            drag.exec(Qt.MoveAction)
            self._press_pos = None
            self._dragging = False
            self.drag_finished.emit()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._press_pos is not None and not self._dragging and self.rect().contains(event.position().toPoint()):
                self.clicked.emit(self.clip["id"])
            self._press_pos = None
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _drag_source(self, event):
        if not self.drag_enabled or not event.mimeData().hasFormat("application/x-clipnest-board-card"):
            return None
        try:
            board_id, clip_id = bytes(event.mimeData().data("application/x-clipnest-board-card")).decode().split(":")
            if int(board_id) == self.clip["board_id"] and int(clip_id) != self.clip["id"]:
                return int(clip_id)
        except (ValueError, UnicodeError):
            pass
        return None

    def dragEnterEvent(self, event):
        if self._drag_source(event) is None: event.ignore(); return
        event.acceptProposedAction()
        self.outline.set_state(drop_before=event.position().x() < self.width() / 2)
        self.outline.raise_()

    def dragMoveEvent(self, event):
        if self._drag_source(event) is None: event.ignore(); return
        event.acceptProposedAction()
        self.outline.set_state(drop_before=event.position().x() < self.width() / 2)

    def dragLeaveEvent(self, event):
        self.outline.set_state()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        source = self._drag_source(event)
        before = event.position().x() < self.width() / 2
        self.outline.set_state()
        if source is None: event.ignore(); return
        event.acceptProposedAction()
        self.drop_requested.emit(source, self.clip["id"], before)

    def keyPressEvent(self, event):
        self.key_requested.emit(event)


class SettingsCheckBox(QCheckBox):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        middle = self.height() / 2
        box = QRectF(0.5, middle - 7.5, 15, 15)
        checked = self.isChecked()
        enabled = self.isEnabled()
        accent = theme_accent()
        painter.setPen(QPen(accent if checked and enabled else QColor("#a9a5af"), 1))
        painter.setBrush(accent if checked and enabled else QColor("#ffffff"))
        painter.drawRoundedRect(box, 4, 4)
        if checked:
            pen = QPen(QColor("#ffffff") if enabled else QColor("#a9a5af"), 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(4.2, middle)
            path.lineTo(7.2, middle + 2.8)
            path.lineTo(12.1, middle - 3.2)
            painter.drawPath(path)
        painter.setPen(QColor("#292936") if enabled else QColor("#a9a5af"))
        painter.drawText(self.rect().adjusted(25, 0, -2, 0), Qt.AlignLeft | Qt.AlignVCenter, self.text())
        painter.end()


class UpdateBridge(QObject):
    checked = Signal(object)
    downloaded = Signal(object)


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent); self.parent_app = parent
        self.setWindowTitle("ClipNest 设置"); self.setFixedSize(650, 550)
        outer = QVBoxLayout(self); outer.setContentsMargins(22, 18, 22, 18); outer.setSpacing(12)
        title = QLabel("偏好设置"); title.setStyleSheet("font-size:20px;font-weight:800;"); outer.addWidget(title)
        caption = QLabel("ClipNest 的记录已加密保存在本机。更改设置后立即保存。")
        caption.setObjectName("subtle")
        outer.addWidget(caption)
        content = QHBoxLayout(); content.setSpacing(14); outer.addLayout(content, 1)
        sidebar = QFrame(); sidebar.setObjectName("settingsSidebar"); sidebar.setFixedWidth(145)
        navigation = QVBoxLayout(sidebar); navigation.setContentsMargins(8, 10, 8, 10); navigation.setSpacing(4)
        self.nav_buttons = []
        for index, label in enumerate(("外观与操作", "记录与隐私", "数据与备份", "快捷键说明", "关于")):
            button = QPushButton(label); button.setObjectName("settingsNav")
            button.setCheckable(True); button.setFixedHeight(38)
            button.clicked.connect(lambda checked=False, page=index: self.select_page(page))
            navigation.addWidget(button); self.nav_buttons.append(button)
        navigation.addStretch(1)
        content.addWidget(sidebar)
        panel = QFrame(); panel.setObjectName("settingsPanel")
        panel_layout = QVBoxLayout(panel); panel_layout.setContentsMargins(18, 16, 18, 16)
        self.pages = QStackedWidget(); panel_layout.addWidget(self.pages)
        content.addWidget(panel, 1)

        appearance = self.new_page("外观与操作", "调整外观、呼出方式和日常使用习惯。")
        appearance.addWidget(QLabel("主题色 · 选中框与主要按钮"))
        colors = QHBoxLayout(); colors.setSpacing(8)
        self.color_buttons = []
        for color in ACCENT_PRESETS:
            swatch = QPushButton()
            swatch.setFixedSize(30, 30); swatch.setCursor(Qt.PointingHandCursor)
            swatch.setAccessibleName(f"主题色 {color}")
            swatch.clicked.connect(lambda checked=False, value=color: self.change_theme(value))
            colors.addWidget(swatch); self.color_buttons.append((swatch, color))
        custom = QPushButton("自定义…"); custom.clicked.connect(self.choose_theme)
        colors.addWidget(custom); colors.addStretch(1); appearance.addLayout(colors)
        self.update_color_buttons()
        appearance.addSpacing(13)
        appearance.addWidget(QLabel("呼出窗口快捷键"))
        hotkey_line = QHBoxLayout()
        self.hotkey_edit = QKeySequenceEdit(QKeySequence(parent.store.setting("hotkey", DEFAULT_HOTKEY)))
        hotkey_line.addWidget(self.hotkey_edit, 1)
        save_hotkey = QPushButton("应用快捷键"); save_hotkey.setObjectName("secondaryAction")
        save_hotkey.clicked.connect(self.change_hotkey)
        hotkey_line.addWidget(save_hotkey); appearance.addLayout(hotkey_line)
        appearance.addSpacing(10)
        self.autopaste = SettingsCheckBox("选择卡片后直接粘贴到刚才的应用")
        self.autopaste.setChecked(parent.store.setting("autopaste", "1") == "1")
        self.autopaste.toggled.connect(self.change_autopaste)
        appearance.addWidget(self.autopaste)
        self.autostart = SettingsCheckBox("登录 Windows 时自动启动（驻留托盘）")
        try: self.autostart.setChecked(startup_enabled())
        except OSError: self.autostart.setChecked(False)
        if startup_command() is None:
            self.autostart.setEnabled(False)
            self.autostart.setToolTip("此选项在 ClipNest.exe 中可用")
        self.autostart.toggled.connect(self.change_startup)
        appearance.addWidget(self.autostart); appearance.addStretch(1)

        history = self.new_page("记录与隐私", "控制保留期限、排除应用和网页预览访问。")
        history.addWidget(QLabel("历史保留时间"))
        self.retention = StyledComboBox(); self.retention.addItems(["1 天", "7 天", "30 天", "365 天", "永久"])
        self.retention.setFixedWidth(106)
        self.retention_values = ["1", "7", "30", "365", "0"]
        setting = parent.store.setting("retention", "30")
        self.retention.setCurrentIndex(self.retention_values.index(setting) if setting in self.retention_values else 2)
        self.retention.currentIndexChanged.connect(self.change_retention)
        history.addWidget(self.retention)
        note = QLabel("收藏板内容不会因历史期限到期而删除。")
        note.setObjectName("subtle"); history.addWidget(note)
        history.addSpacing(15)
        history.addWidget(QLabel("忽略这些应用的复制内容"))
        self.excluded = RoundedLineEdit(parent.store.setting("excluded", DEFAULT_EXCLUDED))
        self.excluded.setPlaceholderText("例如：KeePass.exe, 1Password.exe")
        self.excluded.setToolTip(self.excluded.text())
        self.excluded.setCursorPosition(0)
        self.excluded.editingFinished.connect(lambda: parent.store.set_setting("excluded", self.excluded.text()))
        history.addWidget(self.excluded)
        hint = QLabel("填写进程名，用逗号分隔；这些应用的复制内容不会记录。")
        hint.setObjectName("subtle"); hint.setWordWrap(True); history.addWidget(hint)
        history.addSpacing(13)
        self.link_titles = SettingsCheckBox("自动获取网页标题和图标")
        self.link_titles.setChecked(parent.store.setting("link_titles", "1") == "1")
        self.link_titles.toggled.connect(self.change_link_titles)
        history.addWidget(self.link_titles)
        privacy = QLabel("开启后会访问复制链接指向的公开网页及其声明的图标地址；不使用第三方预览服务。")
        privacy.setObjectName("subtle"); privacy.setWordWrap(True); history.addWidget(privacy)
        history.addStretch(1)

        data = self.new_page("数据与备份", "查看加密记录的位置，并管理本地数据库。")
        data.addWidget(QLabel("记录保存位置"))
        storage = QHBoxLayout()
        self.storage_path = RoundedLineEdit(str(parent.store.path.parent)); self.storage_path.setReadOnly(True)
        self.storage_path.setToolTip(str(parent.store.path)); storage.addWidget(self.storage_path, 1)
        move = QPushButton("更改…"); move.setObjectName("secondaryAction")
        move.clicked.connect(self.change_storage); storage.addWidget(move)
        data.addLayout(storage)
        migration = QLabel("更改路径时会先迁移并校验数据，成功后才删除旧数据库。")
        migration.setObjectName("subtle"); migration.setWordWrap(True); data.addWidget(migration)
        data.addSpacing(18)
        backup = QPushButton("备份数据库…"); backup.setObjectName("secondaryAction")
        backup.clicked.connect(self.backup)
        data.addWidget(backup, 0, Qt.AlignLeft)
        data.addStretch(1)
        clear_label = QLabel("清空历史")
        clear_label.setStyleSheet("font-weight:700;"); data.addWidget(clear_label)
        clear_hint = QLabel("仅删除未收藏的记录；操作前会再次确认。")
        clear_hint.setObjectName("subtle"); data.addWidget(clear_hint)
        clear = QPushButton("清空未收藏的历史"); clear.setObjectName("danger")
        clear.clicked.connect(self.clear); data.addWidget(clear, 0, Qt.AlignLeft)

        help_page = self.new_page("快捷键说明", "按使用场景查看操作提示。")
        help_page.setSpacing(5)
        for heading, instruction in (
            ("卡片", "左键粘贴 · 右键更多操作 · 空格预览"),
            ("导航", "← / → 选择 · Enter 粘贴 · Shift + Enter 纯文本"),
            ("搜索", "Ctrl + F 展开 · 点击搜索栏外收起"),
            ("快速使用", "Ctrl + 1～9 使用当前列表的前九项"),
        ):
            self.add_help_row(help_page, heading, instruction)
        self.help_note = self.add_help_row(help_page, "窗口", f"{parent.store.setting('hotkey', DEFAULT_HOTKEY)} 呼出/收起 · Esc 收起")
        self.add_help_row(help_page, "记录", "Ctrl + Shift + C 暂停/恢复记录")
        help_page.addStretch(1)

        about = self.new_page("关于", "版本信息与 GitHub 更新。")
        version_label = QLabel(f"Version {VERSION}")
        version_label.setStyleSheet("font-size:22px;font-weight:800;")
        about.addWidget(version_label)
        repository = QLabel(GITHUB_REPO)
        repository.setObjectName("subtle")
        about.addWidget(repository)
        about.addSpacing(20)
        self.update_status = QLabel("点击按钮检查 GitHub 上的最新版本。")
        self.update_status.setObjectName("subtle")
        self.update_status.setWordWrap(True)
        about.addWidget(self.update_status)
        update_actions = QHBoxLayout()
        self.check_update_button = QPushButton("检查更新")
        self.check_update_button.setObjectName("accent")
        self.style_check_update_button()
        self.check_update_button.clicked.connect(self.check_updates)
        update_actions.addWidget(self.check_update_button)
        github_button = QPushButton("GitHub 页面")
        github_button.setObjectName("secondaryAction")
        github_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        update_actions.addWidget(github_button)
        update_actions.addStretch(1)
        about.addLayout(update_actions)
        about.addSpacing(20)
        credential_title = QLabel("私有仓库访问")
        credential_title.setStyleSheet("font-weight:700;")
        about.addWidget(credential_title)
        credential_hint = QLabel("私有阶段需使用你自己的 GitHub 只读访问令牌；仓库公开后无需令牌。令牌仅在当前 Windows 用户账户下加密保存。")
        credential_hint.setObjectName("subtle")
        credential_hint.setWordWrap(True)
        about.addWidget(credential_hint)
        credential_actions = QHBoxLayout()
        self.credential_button = QPushButton("设置访问令牌…")
        self.credential_button.setObjectName("secondaryAction")
        self.credential_button.clicked.connect(self.set_github_credential)
        credential_actions.addWidget(self.credential_button)
        forget_button = QPushButton("移除令牌")
        forget_button.setObjectName("secondaryAction")
        forget_button.clicked.connect(self.remove_github_credential)
        credential_actions.addWidget(forget_button)
        credential_actions.addStretch(1)
        about.addLayout(credential_actions)
        about.addStretch(1)

        self.update_bridge = UpdateBridge(self)
        self.update_bridge.checked.connect(self.on_update_checked)
        self.update_bridge.downloaded.connect(self.on_update_downloaded)
        self.latest_release = None

        saved_page = parent.store.setting("settings_page", "0")
        self.select_page(int(saved_page) if saved_page.isdigit() else 0, persist=False)

    def style_check_update_button(self):
        update_color = theme_accent()
        update_color_hex = update_color.name()
        update_hover_hex = update_color.darker(115).name()
        self.check_update_button.setStyleSheet(
            f"QPushButton {{ background-color:{update_color_hex}; border:1px solid {update_color_hex}; "
            "color:#ffffff; border-radius:9px; padding:7px 11px; font-weight:700; } "
            f"QPushButton:hover {{ background-color:{update_hover_hex}; border-color:{update_hover_hex}; }} "
            "QPushButton:disabled { background-color:#e8e3e8; border-color:#e8e3e8; color:#928c96; }"
        )

    def new_page(self, heading: str, description: str) -> QVBoxLayout:
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background:#ffffff;border:0; }")
        scroll.viewport().setStyleSheet("background:#ffffff;")
        page = QWidget(); page.setObjectName("settingsPage")
        page.setStyleSheet("QWidget#settingsPage { background:#ffffff; }")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 4, 0); layout.setSpacing(9)
        title = QLabel(heading); title.setStyleSheet("font-size:16px;font-weight:800;")
        layout.addWidget(title)
        caption = QLabel(description); caption.setObjectName("subtle"); caption.setWordWrap(True)
        layout.addWidget(caption); layout.addSpacing(11)
        scroll.setWidget(page); self.pages.addWidget(scroll)
        return layout

    def select_page(self, index: int, persist: bool = True):
        index = max(0, min(index, len(self.nav_buttons) - 1))
        self.pages.setCurrentIndex(index)
        for position, button in enumerate(self.nav_buttons): button.setChecked(position == index)
        if persist: self.parent_app.store.set_setting("settings_page", str(index))

    def set_github_credential(self):
        value, accepted = QInputDialog.getText(
            self, "私有仓库访问令牌", "输入仅授予此仓库 Contents（只读）权限的 GitHub 访问令牌：",
            QLineEdit.Password,
        )
        if not accepted or not value.strip():
            return
        try:
            save_github_token(value.strip())
            self.update_status.setText("访问令牌已加密保存，正在验证 GitHub 更新连接…")
            self.check_updates()
        except Exception as exc:
            QMessageBox.warning(self, "保存访问令牌失败", str(exc))

    def remove_github_credential(self):
        try:
            save_github_token("")
            self.update_status.setText("访问令牌已移除。公开仓库仍可直接检查更新。")
        except Exception as exc:
            QMessageBox.warning(self, "移除访问令牌失败", str(exc))

    def check_updates(self):
        try:
            token = github_token()
        except Exception as exc:
            QMessageBox.warning(self, "读取访问令牌失败", str(exc))
            return
        self.check_update_button.setEnabled(False)
        self.update_status.setText("正在连接 GitHub 检查更新…")

        def worker():
            try:
                self.update_bridge.checked.emit({"release": latest_github_release(token)})
            except Exception as exc:
                self.update_bridge.checked.emit({"error": str(exc)})

        threading.Thread(target=worker, daemon=True).start()

    def on_update_checked(self, result: dict):
        self.check_update_button.setEnabled(True)
        if "error" in result:
            self.update_status.setText("检查更新失败。")
            QMessageBox.warning(self, "检查更新失败", result["error"])
            return
        release = result["release"]
        current = version_parts(VERSION)
        latest = release["parsed_version"]
        if current is None or latest <= current:
            self.update_status.setText(f"已是最新版本：Version {VERSION}")
            QMessageBox.information(self, "检查更新", f"当前已是最新版本：Version {VERSION}")
            return
        try:
            matching_installer(release)
        except Exception as exc:
            self.update_status.setText("发现新版本，但安装包不可用。")
            QMessageBox.warning(self, "更新不可用", str(exc))
            return
        self.latest_release = release
        version_text = f"{latest[0]}.{latest[1]:02d}"
        self.update_status.setText(f"发现新版本：Version {version_text}")
        message = QMessageBox(self)
        message.setWindowTitle(f"ClipNest Version {version_text}")
        message.setText(f"发现新版本 Version {version_text}")
        message.setInformativeText((release.get("body") or "此版本没有发布说明。")[:3500])
        message.setTextFormat(Qt.PlainText)
        ignore = message.addButton("忽略本次更新", QMessageBox.RejectRole)
        install = message.addButton("立即更新", QMessageBox.AcceptRole)
        message.setDefaultButton(install)
        message.exec()
        if message.clickedButton() is install:
            self.start_update_download()

    def start_update_download(self):
        if self.latest_release is None:
            return
        try:
            token = github_token()
        except Exception as exc:
            QMessageBox.warning(self, "读取访问令牌失败", str(exc))
            return
        self.check_update_button.setEnabled(False)
        self.update_status.setText("正在下载并校验更新安装包…")
        release = self.latest_release

        def worker():
            try:
                destination = download_update(release, token if release.get("authenticated") else "")
                self.update_bridge.downloaded.emit({"path": str(destination)})
            except Exception as exc:
                self.update_bridge.downloaded.emit({"error": str(exc)})

        threading.Thread(target=worker, daemon=True).start()

    def on_update_downloaded(self, result: dict):
        self.check_update_button.setEnabled(True)
        if "error" in result:
            self.update_status.setText("更新下载失败。")
            QMessageBox.warning(self, "更新失败", result["error"])
            return
        installer = result["path"]
        try:
            subprocess.Popen(
                [installer, "/SP-", "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                close_fds=True,
            )
        except OSError as exc:
            self.update_status.setText("无法启动更新安装程序。")
            QMessageBox.warning(self, "更新失败", str(exc))
            return
        self.update_status.setText("安装程序已启动，ClipNest 即将退出。")
        QTimer.singleShot(0, QApplication.instance().quit)

    def add_help_row(self, layout: QVBoxLayout, heading: str, text_value: str) -> QLabel:
        label = QLabel(heading); label.setStyleSheet("font-weight:700;")
        layout.addWidget(label)
        detail = QLabel(text_value); detail.setWordWrap(True)
        detail.setStyleSheet("background:#f5f3f6;border-radius:8px;padding:7px;color:#55505b;font-size:12px;")
        layout.addWidget(detail); layout.addSpacing(1)
        return detail

    def update_color_buttons(self):
        selected = self.parent_app.store.setting("theme_accent", DEFAULT_ACCENT).lower()
        for button, color in self.color_buttons:
            border = "#202838" if color == selected else "#d9dce3"
            button.setStyleSheet(f"background:{color};border:2px solid {border};border-radius:15px;")
            button.setToolTip(color + (" · 当前主题色" if color == selected else ""))

    def change_theme(self, color: str):
        self.parent_app.apply_theme(color)
        self.style_check_update_button()
        self.update_color_buttons()

    def choose_theme(self):
        chosen = QColorDialog.getColor(theme_accent(), self, "选择主题色")
        if chosen.isValid(): self.change_theme(chosen.name())

    def change_retention(self, index: int):
        previous = self.parent_app.store.setting("retention", "30")
        selected = self.retention_values[index]
        if selected == previous: return
        count = self.parent_app.store.expiring_count(int(selected))
        if count and QMessageBox.question(self, "清理过期记录", f"应用新期限后会立即删除 {count} 条未收藏的过期记录。继续吗？") != QMessageBox.Yes:
            self.retention.blockSignals(True)
            self.retention.setCurrentIndex(self.retention_values.index(previous))
            self.retention.blockSignals(False)
            return
        self.parent_app.store.set_setting("retention", selected)
        self.parent_app.store.prune()
        self.parent_app.refresh()

    def change_storage(self):
        directory = QFileDialog.getExistingDirectory(self, "选择记录保存目录", str(self.parent_app.store.path.parent))
        if not directory: return
        if Path(directory).resolve() == self.parent_app.store.path.parent.resolve(): return
        if QMessageBox.question(self, "移动记录", f"将现有记录移动到：\n{directory}\n\n完成并校验后，原位置的数据库文件会删除。继续吗？") != QMessageBox.Yes:
            return
        try:
            self.parent_app.store = move_store(self.parent_app.store, Path(directory))
        except Exception as exc:
            QMessageBox.warning(self, "移动失败", str(exc)); return
        self.storage_path.setText(str(self.parent_app.store.path.parent))
        self.storage_path.setToolTip(str(self.parent_app.store.path))
        self.parent_app.refresh_tabs(); self.parent_app.refresh()
        QMessageBox.information(self, "移动完成", "剪贴记录已迁移到新位置。")

    def change_hotkey(self):
        shortcut = self.hotkey_edit.keySequence().toString(QKeySequence.PortableText)
        if not hotkey_parts(shortcut) or shortcut == "Ctrl+Shift+C":
            QMessageBox.warning(self, "快捷键无效", "请设置带 Ctrl、Alt、Shift 或 Win 的字母、数字、F1–F12 或空格组合，且不要使用 Ctrl+Shift+C。")
            return
        if shortcut == self.parent_app.store.setting("hotkey", DEFAULT_HOTKEY): return
        if not self.parent_app.hotkey.change(shortcut):
            QMessageBox.warning(self, "快捷键不可用", "这个组合键已被其他应用占用，请换一个组合。")
            return
        self.parent_app.store.set_setting("hotkey", shortcut)
        self.help_note.setText(f"{shortcut} 呼出/收起 · Esc 收起")
        self.parent_app.set_status(f"呼出快捷键已改为 {shortcut}")

    def save_checkbox(self, checkbox: QCheckBox, key: str, enabled: bool) -> bool:
        try:
            self.parent_app.store.set_setting(key, "1" if enabled else "0")
            return True
        except Exception as exc:
            checkbox.blockSignals(True)
            checkbox.setChecked(not enabled)
            checkbox.blockSignals(False)
            QMessageBox.warning(self, "设置保存失败", str(exc))
            return False

    def change_autopaste(self, enabled: bool):
        self.save_checkbox(self.autopaste, "autopaste", enabled)

    def change_link_titles(self, enabled: bool):
        if self.save_checkbox(self.link_titles, "link_titles", enabled):
            QTimer.singleShot(0, self.parent_app.refresh)

    def change_startup(self, enabled: bool):
        try:
            set_startup_enabled(enabled)
            if startup_enabled() != enabled:
                raise RuntimeError("无法确认开机启动设置，请重试。")
        except Exception as exc:
            self.autostart.blockSignals(True)
            try: self.autostart.setChecked(startup_enabled())
            except Exception: self.autostart.setChecked(not enabled)
            self.autostart.blockSignals(False)
            QMessageBox.warning(self, "开机启动设置失败", str(exc))

    def clear(self):
        if QMessageBox.question(self, "清空历史", "清空所有未收藏的历史记录？此操作无法撤销。") == QMessageBox.Yes:
            self.parent_app.store.clear_history(); self.parent_app.refresh()

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "备份 ClipNest 数据", str(Path.home() / "ClipNest-backup.db"), "SQLite 数据库 (*.db)")
        if path:
            destination = Path(path)
            staging = Path(str(destination) + ".backup-migrating")
            if destination.exists() or store_key_path(destination).exists():
                QMessageBox.warning(self, "备份失败", "目标位置已有备份或密钥文件，请选择新的文件名。")
                return
            if staging.exists():
                QMessageBox.warning(self, "备份失败", "目标位置已有未完成的备份文件，请选择其他文件名。")
                return
            target = None
            try:
                target = sqlite3.connect(staging)
                set_database_key(target, self.parent_app.store.key)
                with target:
                    self.parent_app.store.db.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("备份校验失败。")
                target.close()
                target = None
                save_store_key(store_key_path(destination), self.parent_app.store.key)
                os.replace(staging, destination)
                QMessageBox.information(self, "备份完成", "已保存加密数据库及同名 .key 密钥文件。同一 Windows 账户恢复时，两者都需要保留。")
            except Exception as exc:
                if target is not None:
                    target.close()
                staging.unlink(missing_ok=True)
                store_key_path(destination).unlink(missing_ok=True)
                QMessageBox.warning(self, "备份失败", str(exc))


class Shelf(QWidget):
    link_title_ready = Signal(str, str, str, bytes)

    def __init__(self, store: Store):
        super().__init__(); self.store = store; self.selected_id = None; self.board_id = None; self.last_target = 0
        self.capture_paused = False; self.pinned_open = False; self.hotkey_ok = False; self.own_sequence = 0; self.last_sequence = 0
        self.setWindowTitle(APP); self.setWindowIcon(app_icon())
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("shelfWindow")
        self._link_attempted: set[str] = set()
        self._link_limit = threading.Semaphore(2)
        self.link_title_ready.connect(self._apply_link_title)
        self.link_refresh_timer = QTimer(self)
        self.link_refresh_timer.setSingleShot(True)
        self.link_refresh_timer.setInterval(70)
        self.link_refresh_timer.timeout.connect(self._refresh_link_cards)
        shell = QVBoxLayout(self); shell.setContentsMargins(14, 14, 14, 14)
        panel = RoundedPanel(); panel.setObjectName("shelf"); panel.setFixedHeight(246); shell.addWidget(panel)
        self.panel = panel
        root = QVBoxLayout(panel); root.setContentsMargins(18, 10, 18, 8); root.setSpacing(5)
        top = QHBoxLayout(); top.setSpacing(9)
        self.tabs = QHBoxLayout(); self.tabs.setSpacing(3); top.addLayout(self.tabs, 1)
        self.search = SearchField(); self.search.setAccessibleName("搜索")
        self.search.expand_requested.connect(self.expand_search)
        self.search.collapse_requested.connect(self.collapse_search)
        self.search.textChanged.connect(self.refresh); top.addWidget(self.search)
        self.search.returnPressed.connect(lambda: QTimer.singleShot(0, self._focus_selected))
        self.search_open = False
        self.search_animation = QPropertyAnimation(self.search, b"maximumWidth", self)
        self.search_animation.setDuration(180)
        self.search_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.search_animation.valueChanged.connect(lambda width: self.search.setMinimumWidth(int(width)))
        self.search_animation.finished.connect(self._search_animation_finished)
        pin = HeaderIconButton("pin"); pin.setToolTip("固定窗口，点击外部时保持显示"); pin.setAccessibleName("固定窗口")
        pin.toggled.connect(self.set_pinned); top.addWidget(pin); self.pin_button = pin
        self.kind_filter = StyledComboBox(); self.kind_filter.addItem("所有类型", "")
        for key in ("text", "link", "code", "color", "image", "files"):
            self.kind_filter.addItem(KIND_NAMES[key], key)
        self.kind_filter.setFixedWidth(110); self.kind_filter.currentIndexChanged.connect(self.refresh); top.addWidget(self.kind_filter)
        pause = RecordingStatusButton(); pause.clicked.connect(self.toggle_pause); top.addWidget(pause); self.pause_button = pause
        settings = HeaderTextButton("设置"); settings.clicked.connect(lambda: SettingsDialog(self).exec()); top.addWidget(settings); self.settings_button = settings
        close = QPushButton("✕"); close.setObjectName("quiet"); close.clicked.connect(self.dismiss); top.addWidget(close)
        root.addLayout(top)
        self.scroll = ShelfScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.scroll.setFixedHeight(185)
        self.scroll.setFocusPolicy(Qt.StrongFocus)
        self.scroll.setStyleSheet("background:transparent;")
        self.holder = QWidget(); self.holder.setFixedHeight(180)
        self.cards = QHBoxLayout(self.holder); self.cards.setContentsMargins(0, 2, 0, 2); self.cards.setSpacing(CARD_GAP); self.cards.setAlignment(Qt.AlignLeft)
        self.scroll.setWidget(self.holder); root.addWidget(self.scroll)
        self.scroll.horizontalScrollBar().valueChanged.connect(self._update_visible_cards)
        self.empty_label = None
        self.card_widgets = {}
        self._pending_drag_cards = []
        self._rows = []
        self._row_indices = {}
        self._visible_range = (-1, -1)
        self._building_cards = False
        self._card_stride = CARD_WIDTH + CARD_GAP
        self.last_status = "剪贴板历史"
        self.setFixedHeight(274)
        self.slide = QPropertyAnimation(self, b"pos", self)
        self.slide.finished.connect(self._slide_finished)
        self._slide_target = "hidden"
        self._after_hide = None
        self._focus_guard_until = 0.0
        self.focus_timer = QTimer(self)
        self.focus_timer.setInterval(90)
        self.focus_timer.timeout.connect(self._dismiss_if_inactive)
        self.clipboard = QApplication.clipboard(); self.clipboard.dataChanged.connect(self.capture)
        self.hotkey = Hotkey(self.store.setting("hotkey", DEFAULT_HOTKEY)); self.hotkey.activated.connect(self.on_hotkey); self.hotkey.status.connect(self.set_hotkey_status); self.hotkey.start()
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll_clipboard); self.timer.start(600)
        self.prune_timer = QTimer(self); self.prune_timer.timeout.connect(self.prune_history); self.prune_timer.start(3600_000)
        self.tray = QSystemTrayIcon(app_icon(), self); self.tray.setToolTip("ClipNest · " + self.last_status)
        menu = RoundedMenu(); self.tray_menu = menu
        show_action = menu.addAction("打开 ClipNest"); show_action.triggered.connect(self.reveal)
        pause_action = menu.addAction("暂停记录"); pause_action.triggered.connect(self.toggle_pause); self.tray_pause_action = pause_action
        menu.addSeparator(); exit_action = menu.addAction("退出"); exit_action.triggered.connect(QApplication.quit)
        self.tray.activated.connect(self.on_tray_activated); self.tray.show()
        self.store.prune(); self.refresh_tabs(); self.refresh()
        QApplication.instance().installEventFilter(self)
        if os.name == "nt": self.last_sequence = ctypes.windll.user32.GetClipboardSequenceNumber()

    def showEvent(self, event):
        super().showEvent(event)
        if os.name == "nt":
            # The panel supplies its own antialiased corners. Avoid a second
            # radius from the Windows compositor on the translucent window.
            preference = ctypes.c_int(1)  # DWMWCP_DONOTROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()), 33, ctypes.byref(preference), ctypes.sizeof(preference))
            no_border = ctypes.c_uint(0xFFFFFFFE)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()), 34, ctypes.byref(no_border), ctypes.sizeof(no_border))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        panel_rect = QRectF(self.panel.geometry())
        # Paint the shadow on the same transparent window. A graphics effect
        # on the child panel gave Windows an extra square compositing corner.
        for spread, opacity in ((12, 3), (10, 4), (8, 5), (6, 6), (4, 7), (2, 8)):
            painter.setBrush(QColor(29, 24, 39, opacity))
            painter.drawRoundedRect(panel_rect.adjusted(-spread, -spread + 2, spread, spread + 2),
                                    22 + spread, 22 + spread)
        painter.end()

    def set_hotkey_status(self, ok: bool):
        self.hotkey_ok = ok
        if not ok: self.set_status("全局快捷键被占用；可从系统托盘打开 ClipNest")

    def set_status(self, message: str):
        self.last_status = message
        if hasattr(self, "tray"):
            self.tray.setToolTip("ClipNest · " + message)

    def apply_theme(self, color: str):
        accent = QColor(color)
        if not accent.isValid(): return
        value = accent.name()
        self.store.set_setting("theme_accent", value)
        app = QApplication.instance()
        app.setProperty("theme_accent", value)
        app.setStyleSheet(theme_style(value))
        self.refresh_tabs()
        for card in self.card_widgets.values(): card.outline.update()

    def prune_history(self):
        if self.store.prune(): self.refresh()

    def _positions(self, screen=None):
        screen = screen or QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        work = screen.availableGeometry()
        full = screen.geometry()
        self.setFixedWidth(max(1, work.width()))
        x = work.x()
        return (QPoint(x, work.y() + work.height() - self.height()),
                QPoint(x, full.y() + full.height() + 2))

    def _foreground_window(self) -> int:
        return int(ctypes.windll.user32.GetForegroundWindow() or 0) if os.name == "nt" else 0

    def reveal(self):
        if os.name == "nt":
            foreground = self._foreground_window()
            if foreground and foreground != int(self.winId()): self.last_target = foreground
        visible, hidden = self._positions()
        if self.isVisible() and self._slide_target == "shown":
            self.raise_(); self.activateWindow(); self._focus_selected(); return
        was_visible = self.isVisible()
        self.slide.stop()
        self._slide_target = "shown"; self._after_hide = None
        self._focus_guard_until = time.monotonic() + 0.38
        if not was_visible:
            self.move(hidden)
            self.show()
        self.raise_(); self.activateWindow(); self._focus_selected()
        self.slide.setDuration(230)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self.slide.setStartValue(self.pos())
        self.slide.setEndValue(visible)
        self.slide.start()
        self.focus_timer.start()

    def dismiss(self, after=None):
        if not self.isVisible():
            if after: QTimer.singleShot(0, after)
            return
        if self.pinned_open: self.pin_button.setChecked(False)
        if self._slide_target == "hidden":
            if after: self._after_hide = after
            return
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        _, hidden = self._positions(screen)
        self.slide.stop()
        self._slide_target = "hidden"; self._after_hide = after
        self.focus_timer.stop()
        self.slide.setDuration(190)
        self.slide.setEasingCurve(QEasingCurve.InCubic)
        self.slide.setStartValue(self.pos())
        self.slide.setEndValue(hidden)
        self.slide.start()

    def _slide_finished(self):
        if self._slide_target == "hidden":
            self.hide()
            after = self._after_hide; self._after_hide = None
            if after: QTimer.singleShot(40, after)
        elif self._slide_target == "shown":
            self._focus_selected()

    def _dismiss_if_inactive(self):
        if not self.isVisible() or self.pinned_open or self._slide_target != "shown" or time.monotonic() < self._focus_guard_until:
            return
        if QApplication.activePopupWidget() or QApplication.activeModalWidget():
            return
        if os.name == "nt":
            foreground = self._foreground_window()
            if foreground and foreground != int(self.winId()):
                self.dismiss()
        elif not self.isActiveWindow():
            self.dismiss()

    def event(self, event):
        if event.type() == QEvent.WindowDeactivate:
            QTimer.singleShot(60, self._dismiss_if_inactive)
        return super().event(event)

    def mousePressEvent(self, event):
        if not self.panel.geometry().contains(event.position().toPoint()):
            if not self.pinned_open: self.dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.MouseButtonRelease and self.search_open
                and not QApplication.activeModalWidget()
                and isinstance(watched, QWidget) and (watched is self or self.isAncestorOf(watched))
                and watched is not self.search and not self.search.isAncestorOf(watched)):
            # Run after the clicked control receives its release (card paste, menu, etc.).
            QTimer.singleShot(0, self.collapse_search)
        if (event.type() == QEvent.KeyPress and event.key() == Qt.Key_F
                and event.modifiers() & Qt.ControlModifier and self.isVisible()
                and not QApplication.activeModalWidget() and isinstance(watched, QWidget)
                and (watched is self or self.isAncestorOf(watched))):
            self.expand_search()
            event.accept()
            return True
        if (event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Left, Qt.Key_Right)
                and self.isVisible() and self.selected_id and not QApplication.activeModalWidget()
                and not QApplication.activePopupWidget() and isinstance(watched, QWidget)
                and (watched is self or self.isAncestorOf(watched))):
            self.navigate_selection(event.key())
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.reveal()
        elif reason == QSystemTrayIcon.Context:
            self.tray_menu.popup(QCursor.pos())

    def on_hotkey(self, key: int):
        if key == 2: self.toggle_pause()
        elif QApplication.activeModalWidget(): return
        elif self.isVisible(): self.dismiss()
        else: self.reveal()

    def toggle_pause(self):
        self.capture_paused = not self.capture_paused
        self.pause_button.set_paused(self.capture_paused)
        self.tray_pause_action.setText("恢复记录" if self.capture_paused else "暂停记录")
        self.set_status("记录已暂停" if self.capture_paused else "记录已恢复")

    def set_pinned(self, pinned: bool):
        self.pinned_open = pinned
        self.pin_button.setToolTip("取消固定窗口" if pinned else "固定窗口，点击外部时保持显示")
        self.pin_button.setAccessibleName("取消固定窗口" if pinned else "固定窗口")
        if not pinned: QTimer.singleShot(70, self._dismiss_if_inactive)

    def toggle_search(self):
        if self.search_open: self.collapse_search()
        else: self.expand_search()

    def expand_search(self):
        if self.search_open:
            self.search.setFocus(Qt.ShortcutFocusReason)
            return
        self.search_open = True
        self.search.set_expanded(True)
        self.search_animation.stop()
        start_width = self.search.width()
        self.search.setMinimumWidth(start_width)
        self.search.setMaximumWidth(start_width)
        self.search.setFocus(Qt.OtherFocusReason)
        self.search_animation.setStartValue(start_width)
        self.search_animation.setEndValue(235)
        self.search_animation.start()

    def collapse_search(self):
        if not self.search_open: return
        self.search_open = False
        self.search.clear()
        self.search.set_expanded(False)
        self.search_animation.stop()
        start_width = self.search.width()
        self.search.setMinimumWidth(start_width)
        self.search.setMaximumWidth(start_width)
        self.search_animation.setStartValue(start_width)
        self.search_animation.setEndValue(34)
        self.search_animation.start()

    def _search_animation_finished(self):
        if self.search_open:
            self.search.setFocus(Qt.OtherFocusReason)
        else:
            self._focus_selected()

    def poll_clipboard(self):
        if os.name != "nt": return
        seq = ctypes.windll.user32.GetClipboardSequenceNumber()
        if seq != self.last_sequence:
            self.last_sequence = seq; self.capture()

    def capture(self):
        if self.capture_paused: return
        seq = ctypes.windll.user32.GetClipboardSequenceNumber() if os.name == "nt" else 0
        if seq and seq == self.own_sequence: return
        if seq: self.last_sequence = seq
        mime = self.clipboard.mimeData()
        if not mime: return
        formats = set(mime.formats())
        for item in formats:
            if "ExcludeClipboardContentFromMonitorProcessing" in item:
                return
            if "CanIncludeInClipboardHistory" in item:
                marker = bytes(mime.data(item))
                if marker in (b"0", b"\0", b"\0\0\0\0"):
                    return
        source = source_app()
        excluded = {x.strip().lower() for x in self.store.setting("excluded", DEFAULT_EXCLUDED).split(",") if x.strip()}
        if source.lower() in excluded or source.lower() in {"clipnest.exe", "python.exe", "pythonw.exe"} and self.isActiveWindow(): return
        try:
            if mime.hasUrls() and all(u.isLocalFile() for u in mime.urls()):
                files = [u.toLocalFile() for u in mime.urls()]
                saved = self.store.save("files", files=files, source=source)
            elif (text := preferred_spreadsheet_text(mime, source)):
                rich = collect_rich_formats(mime)
                saved = self.store.save("text", text=text, html=mime.html() if mime.hasHtml() else "", source=source, mime_formats=rich)
            elif mime.hasImage():
                image = self.clipboard.image()
                if image.isNull(): return
                data = QByteArray(); buffer = QBuffer(data); buffer.open(QIODevice.WriteOnly)
                image.save(buffer, "PNG"); buffer.close()
                saved = self.store.save("image", image=bytes(data), source=source)
            elif (url_text := clipboard_url_without_text(mime)):
                saved = self.store.save("link", text=url_text, html=mime.html() if mime.hasHtml() else "", source=source,
                                        mime_formats=collect_rich_formats(mime))
            elif mime.hasText():
                text = mime.text()
                if not text.strip(): return
                rich = collect_rich_formats(mime)
                saved = self.store.save(classify(text), text=text, html=mime.html() if mime.hasHtml() else "", source=source, mime_formats=rich)
            else: return
            if saved: self.refresh()
        except Exception as exc:
            self.set_status(f"读取剪贴板失败：{exc}")

    def refresh_tabs(self):
        while self.tabs.count():
            item = self.tabs.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        history = BoardTabButton("全部历史", theme_accent().name(), self.board_id is None)
        history.clicked.connect(lambda: self.select_board(None))
        self.tabs.addWidget(history)
        for board in self.store.boards():
            board_id = board["id"]
            button = BoardTabButton(board["name"], board["color"], self.board_id == board_id)
            button.clicked.connect(lambda checked=False, ident=board_id: self.select_board(ident))
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda point, ident=board_id, btn=button: self.board_menu(ident, btn.mapToGlobal(point)))
            self.tabs.addWidget(button)
        add = QPushButton("＋ 新建收藏板"); add.clicked.connect(self.add_board); self.tabs.addWidget(add); self.tabs.addStretch(1)

    def select_board(self, board_id):
        self.board_id = board_id; self.refresh_tabs(); self.refresh(); self._focus_selected()

    def add_board(self):
        name, ok = QInputDialog.getText(self, "新建收藏板", "名称")
        if ok and name.strip():
            try: self.board_id = self.store.add_board(name.strip()); self.refresh_tabs(); self.refresh()
            except sqlite3.IntegrityError: QMessageBox.information(self, APP, "这个收藏板名称已存在。")

    def board_menu(self, board_id, pos):
        board = next((item for item in self.store.boards() if item["id"] == board_id), None)
        if board is None: return
        menu = RoundedMenu(self)
        colors = RoundedMenu(menu); colors.setTitle("指示点颜色")
        color_actions = {}
        for label, color in BOARD_RAINBOW:
            action = colors.addAction(label)
            action.setData(color)
            action.setCheckable(True)
            action.setChecked(board["color"] == color)
            color_actions[action] = color
        menu.addMenu(colors)
        menu.addSeparator()
        remove = menu.addAction("删除收藏板")
        result = menu.exec(pos)
        if result in color_actions:
            self.store.set_board_color(board_id, color_actions[result])
            self.refresh_tabs()
        elif result == remove and QMessageBox.question(self, "删除收藏板", "删除收藏板？其中的内容会保留在历史中。") == QMessageBox.Yes:
            self.store.delete_board(board_id); self.board_id = None; self.refresh_tabs(); self.refresh()

    def _clear_cards(self):
        while self.cards.count():
            item = self.cards.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                if isinstance(widget, Card) and widget._dragging:
                    self._pending_drag_cards.append(widget)
                else:
                    widget.deleteLater()
        self.card_widgets = {}

    def _finish_card_drag(self):
        for card in self._pending_drag_cards: card.deleteLater()
        self._pending_drag_cards.clear()
        self._update_visible_cards()

    def _update_visible_cards(self, _value=None):
        if self._building_cards or not self._rows:
            return
        offset = self.scroll.horizontalScrollBar().value()
        width = max(1, self.scroll.viewport().width())
        first = max(0, offset // self._card_stride - 2)
        last = min(len(self._rows), (offset + width + self._card_stride - 1) // self._card_stride + 2)
        if (first, last) == self._visible_range:
            return
        self._building_cards = True
        try:
            focused = QApplication.focusWidget()
            had_card_focus = any(focused is card or card.isAncestorOf(focused) for card in self.card_widgets.values()) if focused else False
            self._clear_cards()
            self._visible_range = (first, last)
            if first:
                self.cards.addSpacerItem(QSpacerItem(first * self._card_stride - CARD_GAP, 1, QSizePolicy.Fixed, QSizePolicy.Minimum))
            for row in self._rows[first:last]:
                image_data = self.store.image_data(row["id"]) if row["kind"] == "image" else None
                display_row = dict(row) if row["kind"] == "link" else row
                if row["kind"] == "link": display_row["preview_icon"] = self.store.link_icon(row["text_data"])
                card = Card(display_row, image_data)
                card.clicked.connect(self._card_clicked)
                card.menu_requested.connect(self.clip_menu)
                card.key_requested.connect(self.keyPressEvent)
                card.drag_enabled = self.board_id is not None and not self.search.text().strip() and not self.kind_filter.currentData()
                card.drop_requested.connect(self.reorder_board_clip)
                card.drag_finished.connect(self._finish_card_drag)
                if card.drag_enabled: card.setToolTip("按住并拖动以调整收藏顺序")
                self.cards.addWidget(card)
                self.card_widgets[row["id"]] = card
                card.set_selected(row["id"] == self.selected_id)
                if row["kind"] == "link": self._schedule_link_title(row)
            remaining = len(self._rows) - last
            if remaining:
                self.cards.addSpacerItem(QSpacerItem(remaining * self._card_stride - CARD_GAP, 1, QSizePolicy.Fixed, QSizePolicy.Minimum))
            if had_card_focus:
                (self.card_widgets.get(self.selected_id) or self.scroll).setFocus(Qt.OtherFocusReason)
        finally:
            self._building_cards = False

    def refresh(self):
        self._building_cards = True
        self._clear_cards()
        self._visible_range = (-1, -1)
        self.empty_label = None
        self._rows = self.store.clips(self.board_id, self.search.text().strip(), self.kind_filter.currentData())
        self._row_indices = {row["id"]: index for index, row in enumerate(self._rows)}
        self.selected_id = self._rows[0]["id"] if self._rows else None
        if not self._rows:
            self.holder.setMinimumWidth(0)
            empty = QLabel("还没有记录。复制文字、链接、图片或文件后，它们会出现在这里。" if not self.search.text() else "没有找到匹配的内容")
            empty.setObjectName("subtle"); empty.setAlignment(Qt.AlignCenter)
            self.empty_label = empty; self._size_empty_label(); self.cards.addWidget(empty)
        else:
            self.holder.setMinimumWidth(len(self._rows) * self._card_stride - CARD_GAP)
        self.scroll.horizontalScrollBar().setValue(0)
        self._building_cards = False
        self._update_visible_cards()

    def reorder_board_clip(self, clip_id: int, target_id: int, before: bool):
        if self.board_id is None or self.search.text().strip() or self.kind_filter.currentData(): return
        if self.store.reorder_board_clip(self.board_id, clip_id, target_id, before):
            self.refresh()
            self.select_clip(clip_id)

    def _schedule_link_title(self, row, retry=False):
        if self.store.setting("link_titles", "1") != "1": return
        url = row["text_data"]
        if not self.store.link_preview_due(url, retry): return
        if url in self._link_attempted and not retry: return
        self._link_attempted.add(url)

        def load():
            with self._link_limit:
                title, site, icon = fetch_link_preview(url)
            try: self.link_title_ready.emit(url, title, site, icon)
            except RuntimeError: pass

        threading.Thread(target=load, daemon=True).start()

    def _apply_link_title(self, url: str, title: str, site: str, icon: bytes):
        if self.store.setting("link_titles", "1") != "1": return
        if self.store.set_link_preview(url, title, site, icon):
            self.link_refresh_timer.start()

    def _refresh_link_cards(self):
        selected = self.selected_id
        offset = self.scroll.horizontalScrollBar().value()
        self.refresh()
        self.scroll.horizontalScrollBar().setValue(offset)
        if selected in self._row_indices:
            self.selected_id = selected
            for ident, card in self.card_widgets.items(): card.set_selected(ident == selected)

    def select_clip(self, clip_id, focus=True):
        index = self._row_indices.get(clip_id)
        if index is not None:
            bar = self.scroll.horizontalScrollBar()
            start = index * self._card_stride
            end = start + CARD_WIDTH
            if start < bar.value():
                bar.setValue(start)
            elif end > bar.value() + self.scroll.viewport().width():
                bar.setValue(end - self.scroll.viewport().width())
            self._update_visible_cards()
        self.selected_id = clip_id
        for ident, card in self.card_widgets.items():
            card.set_selected(ident == clip_id)
        card = self.card_widgets.get(clip_id)
        if card:
            if focus: card.setFocus(Qt.OtherFocusReason)

    def _focus_selected(self):
        card = self.card_widgets.get(self.selected_id)
        if card: card.setFocus(Qt.OtherFocusReason)
        elif self.selected_id in self._row_indices: self.select_clip(self.selected_id)
        else: self.search.setFocus(Qt.OtherFocusReason)

    def _card_clicked(self, clip_id):
        self.select_clip(clip_id)
        self.use_clip(clip_id)

    def _size_empty_label(self):
        if self.empty_label:
            self.empty_label.setFixedWidth(max(1, self.scroll.viewport().width() - 8))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._size_empty_label)
        QTimer.singleShot(0, self._update_visible_cards)

    def clip_menu(self, clip_id, pos, host_dialog=None):
        menu = RoundedMenu(self)
        row = self.store.get(clip_id)
        if not row: return
        rich = bool(row["html_data"] or row["mime_data"])
        paste = menu.addAction("保留格式粘贴" if rich else "粘贴")
        plain = menu.addAction("无格式粘贴"); plain.setEnabled(bool(row["text_data"]))
        copy = menu.addAction("仅复制到剪贴板")
        preview = menu.addAction("预览") if host_dialog is None else None
        retry_link = menu.addAction("重新获取链接预览") if row["kind"] == "link" else None
        rename = menu.addAction("重命名")
        reset_title = menu.addAction("恢复自动网页标题") if row["kind"] == "link" and row["user_title"] else None
        edit = menu.addAction("编辑文字") if row["kind"] not in ("image", "files") else None
        pin = RoundedMenu(menu); pin.setTitle("添加到收藏板"); menu.addMenu(pin)
        board_actions = {}
        for board in self.store.boards(): board_actions[pin.addAction(board["name"])] = board["id"]
        unpin = menu.addAction("从收藏板移除") if row["board_id"] else None
        menu.addSeparator(); delete = menu.addAction("删除记录")
        chosen = menu.exec(pos)
        if chosen and host_dialog is not None: host_dialog.accept()
        if chosen == paste: self.use_clip(clip_id)
        elif chosen == plain: self.use_clip(clip_id, plain=True)
        elif chosen == copy: self.use_clip(clip_id, paste=False)
        elif preview is not None and chosen == preview: self.preview_clip(clip_id)
        elif retry_link is not None and chosen == retry_link: self._schedule_link_title(row, retry=True)
        elif chosen == rename:
            title, ok = QInputDialog.getText(self, "重命名", "标题", text=display_title(row))
            if ok and title.strip(): self.store.rename(clip_id, title.strip()); self.refresh()
        elif reset_title is not None and chosen == reset_title:
            self.store.clear_link_title(clip_id); self.refresh()
        elif edit is not None and chosen == edit: self.edit_clip(clip_id)
        elif chosen in board_actions: self.store.set_board(clip_id, board_actions[chosen]); self.refresh()
        elif unpin is not None and chosen == unpin: self.store.set_board(clip_id, None); self.refresh()
        elif chosen == delete: self.store.delete(clip_id); self.refresh()

    def build_mime_data(self, row, plain=False):
        from PySide6.QtCore import QMimeData, QUrl
        mime = QMimeData()
        if row["kind"] == "image" and not plain:
            image = QImage.fromData(row["image_data"]); mime.setImageData(image)
        elif row["kind"] == "files" and not plain:
            mime.setUrls([QUrl.fromLocalFile(x) for x in json.loads(row["files_data"])])
        else:
            if not plain:
                for name, data in unpack_mime(row["mime_data"]).items():
                    mime.setData(name, QByteArray(data))
                if row["html_data"]: mime.setHtml(row["html_data"])
            mime.setText(row["text_data"])
        return mime

    def clipboard_write(self, row, plain=False):
        mime = self.build_mime_data(row, plain)
        self.clipboard.setMimeData(mime)
        if os.name == "nt": self.own_sequence = ctypes.windll.user32.GetClipboardSequenceNumber(); self.last_sequence = self.own_sequence

    def use_clip(self, clip_id: int, plain=False, paste=True):
        row = self.store.get(clip_id)
        if not row: return
        self.clipboard_write(row, plain)
        if paste and self.store.setting("autopaste", "1") == "1" and self.last_target and os.name == "nt":
            if self.pinned_open:
                QTimer.singleShot(40, self.send_paste)
            else:
                self.dismiss(after=self.send_paste)
        else:
            self.set_status("已复制到剪贴板，可在目标应用中按 Ctrl + V")

    def send_paste(self):
        user32 = ctypes.windll.user32
        restored = bool(user32.SetForegroundWindow(self.last_target))
        if not restored or user32.GetForegroundWindow() != self.last_target:
            self.set_status("已复制到剪贴板；请在目标应用按 Ctrl + V")
            return
        # VK_CONTROL and VK_V. keybd_event is sufficient for ordinary desktop apps.
        user32.keybd_event(0x11, 0, 0, 0); user32.keybd_event(0x56, 0, 0, 0)
        user32.keybd_event(0x56, 0, 2, 0); user32.keybd_event(0x11, 0, 2, 0)

    def preview_clip(self, clip_id):
        row = self.store.get(clip_id)
        if not row: return
        dialog = QDialog(self); dialog.setWindowTitle(display_title(row)); dialog.resize(620, 480)
        layout = QVBoxLayout(dialog); layout.setContentsMargins(18, 18, 18, 18)
        info = QLabel(f"{KIND_NAMES.get(row['kind'], row['kind'])}  ·  {friendly_source(row['source'])}"); info.setObjectName("subtle"); layout.addWidget(info)
        if row["kind"] == "image":
            image = QPixmap(); image.loadFromData(row["image_data"])
            label = QLabel(); label.setAlignment(Qt.AlignCenter); label.setPixmap(image.scaled(570, 390, Qt.KeepAspectRatio, Qt.SmoothTransformation)); layout.addWidget(label)
            content = label
        else:
            edit = QTextEdit(); edit.setReadOnly(True)
            if row["kind"] == "files": edit.setPlainText("\n".join(json.loads(row["files_data"])))
            elif row["html_data"]: edit.setHtml(row["html_data"])
            else: edit.setPlainText(row["text_data"])
            layout.addWidget(edit)
            content = edit
        content.setContextMenuPolicy(Qt.CustomContextMenu)
        content.customContextMenuRequested.connect(lambda point: self.clip_menu(clip_id, content.mapToGlobal(point), dialog))
        dialog.exec()

    def edit_clip(self, clip_id):
        row = self.store.get(clip_id); dialog = QDialog(self); dialog.setWindowTitle("编辑文字"); dialog.resize(590, 420)
        layout = QVBoxLayout(dialog); edit = RoundedTextEdit(); edit.setPlainText(row["text_data"]); layout.addWidget(edit)
        save = QPushButton("保存"); save.setObjectName("accent"); save.clicked.connect(dialog.accept); layout.addWidget(save)
        if dialog.exec() == QDialog.Accepted: self.store.edit_text(clip_id, edit.toPlainText()); self.refresh()

    def navigate_selection(self, key):
        if not self._rows: return
        current = self._row_indices.get(self.selected_id, 0)
        next_index = max(0, min(len(self._rows) - 1, current + (-1 if key == Qt.Key_Left else 1)))
        row = self._rows[next_index]
        self.select_clip(row["id"])
        self.set_status("选中：" + display_title(row))

    def keyPressEvent(self, event):
        key, mods = event.key(), event.modifiers()
        if key == Qt.Key_Escape: self.dismiss(); return
        if key == Qt.Key_F and mods & Qt.ControlModifier: self.expand_search(); return
        if key == Qt.Key_Space and self.selected_id and not self.search.hasFocus(): self.preview_clip(self.selected_id); return
        if key in (Qt.Key_Return, Qt.Key_Enter) and self.selected_id and not self.search.hasFocus():
            self.use_clip(self.selected_id, plain=bool(mods & Qt.ShiftModifier)); return
        if key in (Qt.Key_Left, Qt.Key_Right) and self.selected_id:
            self.navigate_selection(key); return
        if Qt.Key_1 <= key <= Qt.Key_9 and mods & Qt.ControlModifier:
            index = key - Qt.Key_1
            if index < len(self._rows): self.use_clip(self._rows[index]["id"], plain=bool(mods & Qt.ShiftModifier))
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        event.ignore(); self.dismiss()

    def shutdown(self):
        QApplication.instance().removeEventFilter(self)
        self.hotkey.stop(); self.tray.hide(); self.store.db.close()


def main():
    if sys.platform != "win32":
        print("ClipNest is a Windows desktop application.", file=sys.stderr); return 1
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    background = "--background" in sys.argv[1:]
    quit_request = "--quit" in sys.argv[1:]
    server_name = "ClipNest-" + hashlib.sha256(str(Path.home()).encode()).hexdigest()[:12]
    client = QLocalSocket(); client.connectToServer(server_name)
    if client.waitForConnected(250):
        client.write(b"quit" if quit_request else (b"background" if background else b"show")); client.flush(); client.waitForBytesWritten(250); client.disconnectFromServer()
        return 0
    if quit_request:
        return 0
    QLocalServer.removeServer(server_name)
    server = QLocalServer(); server.listen(server_name)
    store = Store(resolve_db_path())
    accent = store.setting("theme_accent", DEFAULT_ACCENT)
    app.setProperty("theme_accent", accent)
    app.setStyleSheet(theme_style(accent))
    shelf = Shelf(store); app.aboutToQuit.connect(shelf.shutdown)
    QTimer.singleShot(15000, clear_update_cache)
    def another_launch():
        connection = server.nextPendingConnection()
        request = b"show"
        if connection:
            connection.waitForReadyRead(100)
            request = bytes(connection.readAll())
            connection.disconnectFromServer()
        if request == b"quit": app.quit()
        elif request != b"background": shelf.reveal()
    server.newConnection.connect(another_launch)
    if not background: shelf.reveal()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

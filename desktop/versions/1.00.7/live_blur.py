"""Keep a native live backdrop behind ClipNest's Qt-painted shelf on Windows."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE = 0
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOOWNERZORDER = 0x0200
GW_HWNDNEXT = 2


def _dotnet_runtime_available() -> bool:
    """Check for the x64 .NET 8 Runtime used by the blur helper."""
    candidates = [str(Path(os.environ.get("ProgramW6432", r"C:\Program Files")) /
                      "dotnet" / "dotnet.exe"),
                  str(Path(os.environ["DOTNET_ROOT_X64"]) / "dotnet.exe")
                  if os.environ.get("DOTNET_ROOT_X64") else None,
                  str(Path(os.environ["DOTNET_ROOT"]) / "dotnet.exe")
                  if os.environ.get("DOTNET_ROOT") else None,
                  shutil.which("dotnet")]
    for candidate in dict.fromkeys(path for path in candidates if path):
        if not Path(candidate).is_file():
            continue
        try:
            result = subprocess.run([candidate, "--list-runtimes"],
                                    capture_output=True, text=True, timeout=3,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and any(
            line.startswith("Microsoft.NETCore.App 8.")
            for line in result.stdout.splitlines()
        ):
            return True
    return False


def _host_executable() -> Path | None:
    override = os.environ.get("CLIPNEST_BLUR_HOST")
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None

    roots = [Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)),
             Path(sys.executable).resolve().parent]
    for root in roots:
        candidate = root / "composition-host" / "ClipNest.BlurHost.exe"
        if candidate.is_file():
            return candidate
    return None


class LiveBlurHost:
    """A separate composition window aligned with Qt; Qt retains all input."""

    def __init__(self):
        self.executable = _host_executable() if os.name == "nt" else None
        self.process: subprocess.Popen | None = None
        self.hwnd = 0
        self.title = f"ClipNest blur {uuid.uuid4().hex}"
        self.status_path = Path(tempfile.gettempdir()) / f"{self.title}.status"
        self.missing_runtime = False
        self._runtime_checked = False
        self._started_at = 0.0
        self._styled = False
        self._started_scale = None
        if os.name == "nt":
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            self.user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            self.user32.FindWindowW.restype = wintypes.HWND
            self.user32.IsWindow.argtypes = [wintypes.HWND]
            self.user32.IsWindow.restype = wintypes.BOOL
            self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            self.user32.GetWindowRect.restype = wintypes.BOOL
            self.user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
            self.user32.GetWindow.restype = wintypes.HWND
            self.user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                                                  ctypes.c_int, ctypes.c_int,
                                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
            self.user32.SetWindowPos.restype = wintypes.BOOL
            self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            self.user32.ShowWindow.restype = wintypes.BOOL
            self.user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            self.user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            self.user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            self.user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t

    def start(self, scale: float = 1.0) -> bool:
        if self.executable is None:
            return False
        if not self._runtime_checked:
            self._runtime_checked = True
            if not _dotnet_runtime_available():
                self.missing_runtime = True
                self.executable = None
                return False
        if self.process is not None:
            if self.process.poll() is None:
                if self._started_scale is not None and abs(scale - self._started_scale) > 0.01:
                    self.stop()
                else:
                    return True
            else:
                self.executable = None
                return False
        try:
            self.process = subprocess.Popen(
                [str(self.executable), f"--title={self.title}",
                 f"--status={self.status_path}",
                 f"--radius={min(256, max(1, round(26 * scale)))}"],
                cwd=str(self.executable.parent),
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._started_at = time.monotonic()
            self._started_scale = scale
            return True
        except OSError:
            self.executable = None
            return False

    def sync(self, qt_hwnd: int, scale: float = 1.0) -> bool:
        """Position the blur host and return whether Acrylic was observed.

        The host status does not identify the GPU or prove hardware rendering.
        A reported fallback disables this host so callers can use their backup.
        """
        if not self.start(scale):
            return False
        try:
            status = self.status_path.read_text(encoding="utf-8")
        except OSError:
            status = ""
        if status == "fallback" or (not status and time.monotonic() - self._started_at > 3):
            self.stop()
            self.executable = None
            return False
        if not self.hwnd or not self.user32.IsWindow(self.hwnd):
            self.hwnd = int(self.user32.FindWindowW(None, self.title) or 0)
        if not self.hwnd:
            return False
        if not self._styled:
            style = self.user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
            self.user32.SetWindowLongPtrW(
                self.hwnd, GWL_EXSTYLE,
                style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
            self._styled = True

        rect = wintypes.RECT()
        if not self.user32.GetWindowRect(qt_hwnd, ctypes.byref(rect)):
            return False
        # Use the exact Qt HWND bounds; shrinking this window exposes an
        # unblurred strip around the translucent shelf in light mode.
        width = max(1, rect.right - rect.left)
        height = max(1, rect.bottom - rect.top)
        positioned = bool(self.user32.SetWindowPos(
            self.hwnd, qt_hwnd, rect.left, rect.top,
            width, height, SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_NOOWNERZORDER))
        return positioned and status == "acrylic"

    def is_aligned(self, qt_hwnd: int, scale: float = 1.0) -> bool:
        """Check the two HWNDs' bounds and immediate Z-order adjacency.

        Moving another topmost window can insert it between Qt and Acrylic
        without delivering a ZOrderChange event to the Qt window itself.
        """
        if (not self.hwnd or not self.user32.IsWindow(self.hwnd)
                or self.process is None or self.process.poll() is not None
                or self._started_scale is None
                or abs(scale - self._started_scale) > 0.01):
            return False
        if int(self.user32.GetWindow(qt_hwnd, GW_HWNDNEXT) or 0) != self.hwnd:
            return False
        qt_rect = wintypes.RECT()
        host_rect = wintypes.RECT()
        if (not self.user32.GetWindowRect(qt_hwnd, ctypes.byref(qt_rect))
                or not self.user32.GetWindowRect(self.hwnd, ctypes.byref(host_rect))):
            return False
        return (qt_rect.left, qt_rect.top, qt_rect.right, qt_rect.bottom) == (
            host_rect.left, host_rect.top, host_rect.right, host_rect.bottom)

    def hide(self):
        if self.hwnd and self.user32.IsWindow(self.hwnd):
            self.user32.ShowWindow(self.hwnd, SW_HIDE)

    def stop(self):
        self.hide()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process = None
        self.hwnd = 0
        self._styled = False
        self._started_scale = None
        self.status_path.unlink(missing_ok=True)

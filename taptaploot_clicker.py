"""
TapTapLoot Auto Clicker
=======================
SendInput-based auto-clicker for Tap Tap Loot (Unity game).

Safety design:
- No drivers, no DLL injection, no kernel-level operations
- Uses standard Windows SendInput API (same as AHK, accessibility tools)
- Auto-shutdown if competitive games (CS2/Valorant/etc.) detected
- System tray icon for at-a-glance status visibility

Hotkeys:
    F6 - Toggle clicking
    F7 - Switch mode (foreground / background)
    F8 - Quit
"""
from __future__ import annotations

# === Version (single source of truth) ===
__version__ = "1.0.1"
__author__ = "TapTapLoot Auto Clicker contributors"
__url__ = "https://github.com/keoy7am/TapTapLootAutoClick"
__license__ = "MIT"

import ctypes
import logging
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

import keyboard
import psutil
import pystray
import win32api
import win32con
import win32gui
import win32process
from PIL import Image, ImageDraw

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore


# ============================================================================
# Constants
# ============================================================================

COMPETITIVE_PROCS = {
    # Valve / CS2
    "cs2.exe", "csgo.exe",
    # Riot / Valorant
    "valorant.exe", "valorant-win64-shipping.exe", "vgc.exe", "vgtray.exe",
    # Easy Anti-Cheat
    "easyanticheat.exe", "easyanticheat_eos.exe",
    # BattlEye
    "beservice.exe", "beservicelauncher.exe",
    # FACEIT
    "faceitservice.exe", "faceit.exe",
}

DEFAULT_CONFIG_NAME = "config.toml"
LOG_NAME = "taptaploot_clicker.log"


# ============================================================================
# SendInput (ctypes)
# ============================================================================

PUL = ctypes.POINTER(ctypes.c_ulong)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", PUL),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", PUL),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

_user32 = ctypes.windll.user32
_send_input = _user32.SendInput
_send_input.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_send_input.restype = wintypes.UINT


def send_left_click(hold_ms: int = 30) -> None:
    """Inject a left mouse click via SendInput at current cursor position.

    Sends LEFTDOWN, sleeps for hold_ms, then sends LEFTUP. The hold delay is
    critical for Unity games which poll input per-frame: if down+up happens
    within microseconds, Unity's Input.GetMouseButtonDown may miss the event
    between frames.
    """
    extra = ctypes.c_ulong(0)
    extra_p = ctypes.pointer(extra)
    down = INPUT(
        type=INPUT_MOUSE,
        u=_INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, extra_p)),
    )
    up = INPUT(
        type=INPUT_MOUSE,
        u=_INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, extra_p)),
    )
    arr_down = (INPUT * 1)(down)
    arr_up = (INPUT * 1)(up)
    _send_input(1, arr_down, ctypes.sizeof(INPUT))
    if hold_ms > 0:
        time.sleep(hold_ms / 1000.0)
    _send_input(1, arr_up, ctypes.sizeof(INPUT))


def enable_dpi_awareness() -> None:
    """Make this process Per-Monitor DPI aware so screen coordinates match
    physical pixels on high-DPI displays. Must be called before any window APIs."""
    try:
        # Per-Monitor v2 (Windows 10 1703+)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        # Per-Monitor v1 (Windows 8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        # System DPI aware (Vista+)
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ============================================================================
# Config
# ============================================================================

@dataclass
class Config:
    target_process_name: str = "TapTapLoot.exe"
    target_window_title: str = "TapTapLoot"
    target_window_class: str = "UnityWndClass"
    cps: float = 10.0
    jitter: float = 0.15
    mode: str = "foreground"
    click_offset_x: int = 0
    click_offset_y: int = 0
    hold_ms: int = 30
    autostart: bool = False
    hk_toggle: str = "F6"
    hk_switch_mode: str = "F7"
    hk_quit: str = "F8"
    scan_interval: float = 1.0
    on_competitive_detected: str = "exit"


def app_dir() -> Path:
    """Directory where exe/script lives. Used for config + log."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def bundled_resource(name: str) -> Path | None:
    """When packaged by PyInstaller, resources are extracted to _MEIPASS."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / name
        return p if p.exists() else None
    return None


def load_config() -> Config:
    """Load config.toml from app_dir; if missing, copy from bundled default."""
    cfg_path = app_dir() / DEFAULT_CONFIG_NAME
    if not cfg_path.exists():
        bundled = bundled_resource(DEFAULT_CONFIG_NAME)
        if bundled and bundled.exists():
            shutil.copy(bundled, cfg_path)
            logging.info(f"已從打包資源建立預設設定檔：{cfg_path}")
        else:
            # Use built-in defaults
            return Config()

    with open(cfg_path, "rb") as f:
        data = tomllib.load(f)

    c = Config()
    clk = data.get("clicker", {})
    c.target_process_name = clk.get("target_process_name", c.target_process_name)
    c.target_window_title = clk.get("target_window_title", c.target_window_title)
    c.target_window_class = clk.get("target_window_class", c.target_window_class)
    c.cps = float(clk.get("cps", c.cps))
    c.jitter = float(clk.get("jitter", c.jitter))
    c.mode = clk.get("mode", c.mode)
    c.click_offset_x = int(clk.get("click_offset_x", c.click_offset_x))
    c.click_offset_y = int(clk.get("click_offset_y", c.click_offset_y))
    c.hold_ms = int(clk.get("hold_ms", c.hold_ms))
    c.autostart = bool(clk.get("autostart", c.autostart))

    hk = data.get("hotkeys", {})
    c.hk_toggle = hk.get("toggle", c.hk_toggle)
    c.hk_switch_mode = hk.get("switch_mode", c.hk_switch_mode)
    c.hk_quit = hk.get("quit", c.hk_quit)

    sf = data.get("safety", {})
    c.scan_interval = float(sf.get("scan_interval", c.scan_interval))
    c.on_competitive_detected = sf.get("on_competitive_detected", c.on_competitive_detected)

    return c


# ============================================================================
# State
# ============================================================================

@dataclass
class State:
    cfg: Config
    running: bool = False  # is clicker actively clicking?
    mode: str = "foreground"
    target_hwnd: int = 0
    cps: float = 10.0
    last_status: str = "paused"
    lock: threading.Lock = field(default_factory=threading.Lock)
    stop_event: threading.Event = field(default_factory=threading.Event)


# ============================================================================
# Window detection
# ============================================================================

def find_target_window(cfg: Config) -> int:
    """Find TapTapLoot HWND. Strategy (most reliable first):
    1. Match by process name (TapTapLoot.exe) - find largest visible top-level window
    2. Exact title match
    3. Class + title-contains fallback
    """
    # Strategy 1: by process name
    if cfg.target_process_name:
        hwnd = _find_window_by_process(cfg.target_process_name)
        if hwnd:
            return hwnd

    # Strategy 2: exact title
    if cfg.target_window_title:
        hwnd = win32gui.FindWindow(None, cfg.target_window_title)
        if hwnd:
            return hwnd

    # Strategy 3: class + title contains
    found: list[int] = []

    def _cb(h: int, _) -> bool:
        if not win32gui.IsWindowVisible(h):
            return True
        try:
            cls = win32gui.GetClassName(h)
            title = win32gui.GetWindowText(h)
        except Exception:
            return True
        if cfg.target_window_class and cls != cfg.target_window_class:
            return True
        if cfg.target_window_title and cfg.target_window_title.lower() in title.lower():
            found.append(h)
        return True

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else 0


def _find_window_by_process(process_name: str) -> int:
    """Return HWND of largest visible top-level window owned by a process matching name."""
    target_pids: set[int] = set()
    for p in psutil.process_iter(['name', 'pid']):
        try:
            n = p.info['name']
            if n and n.lower() == process_name.lower():
                target_pids.add(p.info['pid'])
        except Exception:
            continue
    if not target_pids:
        return 0

    candidates: list[tuple[int, int]] = []  # (hwnd, area)

    def _cb(h: int, _) -> bool:
        if not win32gui.IsWindowVisible(h):
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(h)
            if pid not in target_pids:
                return True
            rect = win32gui.GetWindowRect(h)
            w, h_ = rect[2] - rect[0], rect[3] - rect[1]
            if w <= 1 or h_ <= 1:
                return True
            candidates.append((h, w * h_))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(_cb, None)
    if not candidates:
        return 0
    # Pick the largest visible window (avoids hidden tooltip / IME windows)
    return max(candidates, key=lambda x: x[1])[0]


def get_window_center(hwnd: int, offset_x: int = 0, offset_y: int = 0) -> tuple[int, int]:
    """Return screen coordinates of the window's client-area center + offset."""
    rect = win32gui.GetClientRect(hwnd)
    cx = (rect[0] + rect[2]) // 2 + offset_x
    cy = (rect[1] + rect[3]) // 2 + offset_y
    sx, sy = win32gui.ClientToScreen(hwnd, (cx, cy))
    return sx, sy


def is_window_minimized(hwnd: int) -> bool:
    return bool(win32gui.IsIconic(hwnd))


# ============================================================================
# Click strategies
# ============================================================================

def click_foreground(state: State) -> str:
    """Click only if TapTapLoot is the foreground window. Return new status."""
    hwnd = state.target_hwnd
    if not hwnd or not win32gui.IsWindow(hwnd):
        return "waiting"
    if is_window_minimized(hwnd):
        return "waiting"
    if win32gui.GetForegroundWindow() != hwnd:
        return "waiting"

    x, y = get_window_center(hwnd, state.cfg.click_offset_x, state.cfg.click_offset_y)
    try:
        win32api.SetCursorPos((x, y))
    except Exception:
        # SetCursorPos can fail if user is actively moving mouse
        return "running"
    send_left_click(state.cfg.hold_ms)
    return "running"


def click_background(state: State) -> str:
    """Focus-steal: briefly bring TapTapLoot to foreground, click, restore."""
    hwnd = state.target_hwnd
    if not hwnd or not win32gui.IsWindow(hwnd):
        return "waiting"
    if is_window_minimized(hwnd):
        return "waiting"

    prev_hwnd = win32gui.GetForegroundWindow()
    if prev_hwnd == hwnd:
        # Already foreground, just click
        x, y = get_window_center(hwnd, state.cfg.click_offset_x, state.cfg.click_offset_y)
        try:
            win32api.SetCursorPos((x, y))
        except Exception:
            return "running"
        send_left_click(state.cfg.hold_ms)
        return "running"

    # Bypass SetForegroundWindow restriction with AttachThreadInput
    try:
        fg_thread, _ = win32process.GetWindowThreadProcessId(prev_hwnd)
    except Exception:
        return "waiting"
    my_thread = win32api.GetCurrentThreadId()

    attached = False
    saved_cursor = None
    try:
        try:
            win32process.AttachThreadInput(my_thread, fg_thread, True)
            attached = True
        except Exception:
            pass

        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            return "waiting"

        # Save current cursor so we can restore (minimizes user disruption)
        try:
            saved_cursor = win32api.GetCursorPos()
        except Exception:
            pass

        # Give Unity one frame to register foreground
        time.sleep(0.02)

        x, y = get_window_center(hwnd, state.cfg.click_offset_x, state.cfg.click_offset_y)
        try:
            win32api.SetCursorPos((x, y))
        except Exception:
            pass
        send_left_click(state.cfg.hold_ms)

        # Restore foreground
        try:
            win32gui.SetForegroundWindow(prev_hwnd)
        except Exception:
            pass

        if saved_cursor:
            try:
                win32api.SetCursorPos(saved_cursor)
            except Exception:
                pass

        return "running"
    finally:
        if attached:
            try:
                win32process.AttachThreadInput(my_thread, fg_thread, False)
            except Exception:
                pass


# ============================================================================
# Worker threads
# ============================================================================

def click_loop(state: State, on_status: callable) -> None:
    """Main click loop. Calls on_status(status_str) when state changes."""
    last_status_pushed = ""
    while not state.stop_event.is_set():
        # Refresh hwnd if lost
        if not state.target_hwnd or not win32gui.IsWindow(state.target_hwnd):
            state.target_hwnd = find_target_window(state.cfg)

        if not state.running:
            status = "paused"
        elif not state.target_hwnd:
            status = "waiting"
        else:
            if state.mode == "foreground":
                status = click_foreground(state)
            else:
                status = click_background(state)

        if status != last_status_pushed:
            on_status(status)
            last_status_pushed = status

        # Sleep with jitter
        if state.running and status == "running":
            base = 1.0 / max(state.cps, 0.5)
            jitter = base * state.cfg.jitter
            delay = max(0.005, base + random.gauss(0, jitter))
        else:
            delay = 0.25  # idle poll
        state.stop_event.wait(delay)


def safety_watchdog(state: State, on_danger: callable) -> None:
    """Scan process list for competitive games. Trigger on_danger() if found."""
    target_set = COMPETITIVE_PROCS
    while not state.stop_event.is_set():
        try:
            running_names = set()
            for p in psutil.process_iter(['name']):
                try:
                    n = p.info['name']
                    if n:
                        running_names.add(n.lower())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            hits = target_set & running_names
            if hits:
                on_danger(hits)
                return  # watchdog done; on_danger will exit the program
        except Exception as e:
            logging.exception(f"watchdog scan failed: {e}")
        state.stop_event.wait(state.cfg.scan_interval)


# ============================================================================
# System tray
# ============================================================================

def make_dot_icon(color: str) -> Image.Image:
    """Generate a 64x64 colored dot icon."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=color, outline="#1f2937", width=2)
    return img


ICONS = {
    "running": make_dot_icon("#22c55e"),  # green
    "paused":  make_dot_icon("#eab308"),  # yellow
    "waiting": make_dot_icon("#3b82f6"),  # blue
    "danger":  make_dot_icon("#ef4444"),  # red
}

STATUS_LABELS = {
    "running": "運行中",
    "paused":  "已暫停",
    "waiting": "等待中（找不到視窗）",
    "danger":  "偵測到競技遊戲！",
}


class TrayController:
    def __init__(self, state: State):
        self.state = state
        self.icon: pystray.Icon | None = None
        # Serialize tray updates across threads (hotkey thread, click loop, watchdog)
        # to avoid pystray's WinError 1402 (DestroyIcon race on cross-thread GDI access)
        self._update_lock = threading.Lock()
        self._last_pushed_status: str = ""
        self._last_pushed_tooltip: str = ""

    def build_menu(self) -> pystray.Menu:
        s = self.state

        def cps_setter(value: int):
            def _set(_icon, _item):
                with s.lock:
                    s.cps = float(value)
                logging.info(f"CPS 設為 {value}")
            return _set

        def cps_checked(value: int):
            return lambda _item: int(s.cps) == value

        return pystray.Menu(
            pystray.MenuItem(
                lambda _: f"{'■ 暫停' if s.running else '▶ 開始'} 點擊",
                self.on_toggle,
                default=True,
            ),
            pystray.MenuItem(
                "模式",
                pystray.Menu(
                    pystray.MenuItem(
                        "前景模式（無閃爍）",
                        self.on_set_foreground,
                        checked=lambda _: s.mode == "foreground",
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "背景模式（焦點偷渡）",
                        self.on_set_background,
                        checked=lambda _: s.mode == "background",
                        radio=True,
                    ),
                ),
            ),
            pystray.MenuItem(
                "CPS",
                pystray.Menu(
                    pystray.MenuItem("5",  cps_setter(5),  checked=cps_checked(5),  radio=True),
                    pystray.MenuItem("10", cps_setter(10), checked=cps_checked(10), radio=True),
                    pystray.MenuItem("15", cps_setter(15), checked=cps_checked(15), radio=True),
                    pystray.MenuItem("20", cps_setter(20), checked=cps_checked(20), radio=True),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("顯示視窗資訊", self.on_show_info),
            pystray.MenuItem("開啟設定檔", self.on_open_config),
            pystray.MenuItem("開啟日誌", self.on_open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"關於 v{__version__}", self.on_about),
            pystray.MenuItem("退出", self.on_quit),
        )

    def update(self, status: str) -> None:
        if not self.icon:
            return
        s = self.state
        s.last_status = status
        mode_label = "前景" if s.mode == "foreground" else "背景"
        tooltip = (
            f"TapTapLoot Clicker v{__version__} - {STATUS_LABELS.get(status, status)} "
            f"[{mode_label}模式] CPS={int(s.cps)}"
        )

        # Serialize cross-thread updates to avoid pystray DestroyIcon race
        with self._update_lock:
            new_icon = ICONS.get(status, ICONS["paused"])

            # Skip icon swap if unchanged (avoids unnecessary GDI churn that
            # can trigger WinError 1402 under thread races)
            if status != self._last_pushed_status:
                try:
                    self.icon.icon = new_icon
                    self._last_pushed_status = status
                except OSError as e:
                    # WinError 1402: invalid cursor/icon handle - benign GDI race.
                    # The icon may not visually update this round; next call will succeed.
                    logging.debug(f"tray icon swap OSError (benign, will retry): {e}")
                except Exception as e:
                    logging.exception(f"tray icon swap failed: {e}")

            if tooltip != self._last_pushed_tooltip:
                try:
                    self.icon.title = tooltip
                    self._last_pushed_tooltip = tooltip
                except Exception as e:
                    logging.debug(f"tray title set failed: {e}")

            try:
                self.icon.update_menu()
            except Exception:
                pass

    # --- menu callbacks ---

    def on_toggle(self, _icon, _item):
        with self.state.lock:
            self.state.running = not self.state.running
        logging.info(f"toggle -> running={self.state.running}")
        self.update("running" if self.state.running else "paused")

    def on_set_foreground(self, _icon, _item):
        with self.state.lock:
            self.state.mode = "foreground"
        logging.info("mode -> foreground")
        self.update(self.state.last_status)

    def on_set_background(self, _icon, _item):
        with self.state.lock:
            self.state.mode = "background"
        logging.info("mode -> background")
        self.update(self.state.last_status)

    def on_show_info(self, _icon, _item):
        s = self.state
        hwnd = s.target_hwnd
        if hwnd and win32gui.IsWindow(hwnd):
            try:
                title = win32gui.GetWindowText(hwnd)
                cls = win32gui.GetClassName(hwnd)
                rect = win32gui.GetWindowRect(hwnd)
                cx, cy = get_window_center(hwnd, s.cfg.click_offset_x, s.cfg.click_offset_y)
                msg = (
                    f"HWND: {hwnd}\n"
                    f"Class: {cls}\n"
                    f"Title: {title}\n"
                    f"Rect: {rect}\n"
                    f"Click target: ({cx}, {cy})\n"
                    f"Mode: {s.mode}  CPS: {int(s.cps)}\n"
                    f"Running: {s.running}"
                )
            except Exception as e:
                msg = f"取得視窗資訊失敗：{e}"
        else:
            msg = "尚未找到 TapTapLoot 視窗"
        win32api.MessageBox(0, msg, "TapTapLoot Clicker - 視窗資訊", 0x40)

    def on_open_config(self, _icon, _item):
        path = app_dir() / DEFAULT_CONFIG_NAME
        if not path.exists():
            win32api.MessageBox(0, f"設定檔不存在：{path}", "錯誤", 0x10)
            return
        try:
            os.startfile(str(path))
        except Exception as e:
            win32api.MessageBox(0, f"開啟失敗：{e}", "錯誤", 0x10)

    def on_open_log(self, _icon, _item):
        path = app_dir() / LOG_NAME
        if not path.exists():
            win32api.MessageBox(0, "尚無日誌", "提示", 0x40)
            return
        try:
            os.startfile(str(path))
        except Exception as e:
            win32api.MessageBox(0, f"開啟失敗：{e}", "錯誤", 0x10)

    def on_about(self, _icon, _item):
        msg = (
            f"TapTapLoot Auto Clicker\n"
            f"版本：{__version__}\n"
            f"授權：{__license__}\n\n"
            f"專案：{__url__}\n\n"
            f"使用 SendInput API，不安裝驅動、不注入遊戲。\n"
            f"啟動競技遊戲前請手動關閉本程式。"
        )
        win32api.MessageBox(0, msg, f"關於 TapTapLoot Clicker v{__version__}", 0x40)

    def on_quit(self, _icon, _item):
        logging.info("使用者從 tray 選擇退出")
        self.state.stop_event.set()
        if self.icon:
            self.icon.stop()


# ============================================================================
# Hotkeys
# ============================================================================

def setup_hotkeys(state: State, tray: TrayController) -> None:
    cfg = state.cfg

    def _safe(fn):
        """Wrap hotkey callbacks so an exception never kills the keyboard thread."""
        def wrapper():
            try:
                fn()
            except Exception as e:
                logging.exception(f"hotkey handler crashed: {e}")
        return wrapper

    def _toggle():
        tray.on_toggle(None, None)

    def _switch_mode():
        with state.lock:
            state.mode = "background" if state.mode == "foreground" else "foreground"
        logging.info(f"hotkey -> mode={state.mode}")
        tray.update(state.last_status)

    def _quit():
        tray.on_quit(None, None)

    try:
        keyboard.add_hotkey(cfg.hk_toggle, _safe(_toggle))
        keyboard.add_hotkey(cfg.hk_switch_mode, _safe(_switch_mode))
        keyboard.add_hotkey(cfg.hk_quit, _safe(_quit))
        logging.info(f"熱鍵已註冊：{cfg.hk_toggle}=toggle, {cfg.hk_switch_mode}=mode, {cfg.hk_quit}=quit")
    except Exception as e:
        logging.exception(f"熱鍵註冊失敗：{e}")


# ============================================================================
# Main
# ============================================================================

def setup_logging() -> None:
    log_path = app_dir() / LOG_NAME
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    setup_logging()
    enable_dpi_awareness()
    logging.info("=" * 50)
    logging.info(f"TapTapLoot Clicker v{__version__} 啟動")

    cfg = load_config()
    logging.info(f"設定載入完成：CPS={cfg.cps}, mode={cfg.mode}")

    # Pre-flight: check for competitive games BEFORE doing anything
    running_names = {p.info['name'].lower() for p in psutil.process_iter(['name']) if p.info.get('name')}
    hits = COMPETITIVE_PROCS & running_names
    if hits:
        msg = f"偵測到競技遊戲執行中：{', '.join(sorted(hits))}\n\n為避免反作弊問題，本程式拒絕啟動。\n請先關閉這些遊戲後再執行。"
        logging.error(msg)
        win32api.MessageBox(0, msg, "TapTapLoot Clicker - 安全檢查失敗", 0x10)
        sys.exit(1)

    state = State(cfg=cfg, mode=cfg.mode, cps=cfg.cps, running=cfg.autostart)
    state.target_hwnd = find_target_window(cfg)
    if state.target_hwnd:
        logging.info(f"找到 TapTapLoot 視窗：HWND={state.target_hwnd}")
    else:
        logging.warning("未找到 TapTapLoot 視窗，將持續嘗試")

    tray = TrayController(state)

    initial_status = "running" if state.running else "paused"
    if state.running and not state.target_hwnd:
        initial_status = "waiting"
    state.last_status = initial_status

    mode_label = "前景" if state.mode == "foreground" else "背景"
    initial_tooltip = (
        f"TapTapLoot Clicker v{__version__} - {STATUS_LABELS[initial_status]} "
        f"[{mode_label}模式] CPS={int(state.cps)}"
    )
    tray.icon = pystray.Icon(
        "TapTapLootClicker",
        ICONS[initial_status],
        initial_tooltip,
        menu=tray.build_menu(),
    )

    setup_hotkeys(state, tray)

    # Start worker threads
    def on_status(status: str):
        tray.update(status)

    def on_danger(hits: set):
        names = ", ".join(sorted(hits))
        logging.warning(f"偵測到競技遊戲：{names} - 強制退出")
        tray.update("danger")
        # Brief pause so user sees red icon
        time.sleep(0.5)
        try:
            win32api.MessageBox(
                0,
                f"偵測到競技遊戲執行中：\n{names}\n\nClicker 已自動退出以避免反作弊問題。",
                "TapTapLoot Clicker - 自動退出",
                0x30,
            )
        except Exception:
            pass
        state.stop_event.set()
        if tray.icon:
            tray.icon.stop()
        os._exit(0)

    click_thread = threading.Thread(
        target=click_loop, args=(state, on_status), name="ClickLoop", daemon=True
    )
    safety_thread = threading.Thread(
        target=safety_watchdog, args=(state, on_danger), name="SafetyWatchdog", daemon=True
    )
    click_thread.start()
    safety_thread.start()

    logging.info("Tray 圖示啟動，等待使用者操作")
    try:
        tray.icon.run()  # blocking until stop()
    except KeyboardInterrupt:
        pass
    finally:
        state.stop_event.set()
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        logging.info("TapTapLoot Clicker 結束")


if __name__ == "__main__":
    main()

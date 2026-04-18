"""
診斷工具：列出所有可見頂層視窗的 HWND / Class / Title / Process Name
用途：找出 TapTapLoot 真正的視窗 class 與 title，更新 config.toml
執行：python diagnose_windows.py
"""
import sys

import psutil
import win32gui
import win32process


def main() -> None:
    pid_to_name: dict[int, str] = {}
    for p in psutil.process_iter(['pid', 'name']):
        try:
            pid_to_name[p.info['pid']] = p.info['name'] or ""
        except Exception:
            pass

    rows: list[tuple[int, str, str, str, tuple]] = []

    def cb(hwnd: int, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        try:
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            return True
        # Filter out 0-size or off-screen
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if w <= 1 or h <= 1:
            return True
        proc = pid_to_name.get(pid, f"pid={pid}")
        rows.append((hwnd, cls, title, proc, rect))
        return True

    win32gui.EnumWindows(cb, None)

    # Highlight TapTapLoot rows
    print(f"{'HWND':>10}  {'CLASS':<30}  {'PROCESS':<25}  {'SIZE':<12}  TITLE")
    print("-" * 130)

    target_rows = [r for r in rows if "taptap" in r[3].lower() or "taptap" in r[2].lower()]
    other_rows = [r for r in rows if r not in target_rows]

    # Prioritize: process name match > Unity class > others
    def _score(row):
        _, cls, _, proc, _ = row
        score = 0
        if "taptap" in proc.lower() and "terminal" not in proc.lower() and "code" not in proc.lower():
            score += 100  # actual game process
        if cls == "UnityWndClass":
            score += 50   # Unity-class window
        if "terminal" in proc.lower() or "code" in proc.lower() or "explorer" in proc.lower():
            score -= 100  # likely false positive (IDE/terminal showing project name)
        return -score  # sort ascending

    target_rows.sort(key=_score)

    if target_rows:
        print(">>> 找到疑似 TapTapLoot 視窗（依可信度排序）：")
        for hwnd, cls, title, proc, rect in target_rows:
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            marker = "  ★" if cls == "UnityWndClass" else "   "
            print(f"{marker}{hwnd:>10}  {cls:<30}  {proc:<25}  {w}x{h:<8}  {title!r}")
        print()
        print("=" * 130)
        # Pick best candidate (Unity class first, else first row)
        best = next((r for r in target_rows if r[1] == "UnityWndClass"), target_rows[0])
        print("→ 建議的 config.toml：")
        print(f'    target_process_name = "{best[3]}"')
        print(f'    target_window_title = "{best[2]}"')
        print(f'    target_window_class = "{best[1]}"')
        print("=" * 130)
        print()
    else:
        print(">>> 未找到任何含 'taptap' 的視窗 / process！")
        print("    請確認遊戲已啟動，且不在最小化或全螢幕獨佔模式")
        print()

    print("--- 所有其他可見視窗（前 50 筆）---")
    for hwnd, cls, title, proc, rect in other_rows[:50]:
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        title_short = (title[:50] + "...") if len(title) > 50 else title
        print(f"  {hwnd:>10}  {cls:<30}  {proc:<25}  {w}x{h:<8}  {title_short!r}")


if __name__ == "__main__":
    main()

# TapTapLoot Auto Clicker

針對 [Tap Tap Loot](https://store.steampowered.com/app/3959890/Tap_Tap_Loot/)（Unity 點擊類 RPG）的自動掛機工具。

> 程式採用最溫和的模擬輸入方式（`SendInput` API），不安裝驅動、不注入遊戲，但開啟競技類遊戲時仍建議**手動關閉本程式**以確保安全。

---

## 使用方式

1. 啟動 Tap Tap Loot
2. 啟動 `TapTapLootClicker.exe`（或 `python taptaploot_clicker.py`）
3. 右下角會出現圖示（黃色 = 暫停中）
4. 按 **F6** 開始點擊（圖示變綠）

> ※ 因為遊戲會有縮放比例設定不同的問題，建議**點選書本後，將空白處移動到螢幕中央**讓其點選空白處。

### 熱鍵

| 鍵     | 動作                |
| ------ | ------------------- |
| `F6` | 開始 / 暫停         |
| `F7` | 切換前景 / 背景模式 |
| `F8` | 退出程式            |

### 系統匣圖示顏色

| 顏色  | 狀態                                                                           |
| ----- | ------------------------------------------------------------------------------ |
| 🟢 綠 | 正在點擊                                                                       |
| 🟡 黃 | 已暫停                                                                         |
| 🔵 藍 | 等待中（找不到 TapTapLoot 視窗 / 視窗最小化 / 前景模式但 TapTapLoot 不在前景） |
| 🔴 紅 | 偵測到競技遊戲，即將退出                                                       |

### 兩種模式

**前景模式（預設）**

- TapTapLoot 必須是當前前景視窗
- 直接 `SendInput`，零閃爍、零干擾
- 適合：完全離開電腦、專心掛機

**背景模式**

- 每次點擊前短暫把 TapTapLoot 切到前景（~30ms 閃爍）
- 點擊完立即切回原視窗、還原游標位置
- 適合：邊做別的事邊掛機（瀏覽、看片、寫程式）

### Tray 右鍵選單

- 開始/暫停點擊
- 切換模式（前景/背景）
- 調整 CPS（5 / 10 / 15 / 20）
- 顯示視窗資訊（HWND、座標、目前狀態）
- 開啟設定檔（用記事本編輯 `config.toml`）
- 開啟日誌
- 退出

## 設計原則

- **零驅動**：完全使用 Windows 標準 `SendInput` API，不安裝任何核心驅動
- **零注入**：不對 TapTapLoot 進行 DLL 注入、記憶體寫入
- **反作弊安全**：偵測到 CS2 / Valorant / EAC / BattlEye / FACEIT 立即自動退出
- **常駐可見**：右下角系統匣圖示，顏色一眼辨識狀態

## 安全保證

本工具相較其他方案的安全性：

| 方案                        | 反作弊風險                           | 本工具是否使用     |
| --------------------------- | ------------------------------------ | ------------------ |
| Interception 驅動           | Vanguard 拒絕啟動、VAC 有 ban 紀錄   | ❌ 不使用          |
| DLL 注入                    | 高，所有反作弊都會偵測               | ❌ 不使用          |
| 記憶體 hack                 | 高，VAC/Vanguard 直接 ban            | ❌ 不使用          |
| **`SendInput` API** | 與 AHK、輔助工具同層級，反作弊不 ban | ✅**本工具** |

> ⚠️ **重要約定**：請在啟動 CS2 等競技遊戲前**手動關閉本程式**（右下角圖示 → 退出）。
> 程式內建偵測會在 1 秒內強制退出，但仍以手動關閉為佳。

---

## 安裝（開發模式）

```bash
pip install -r requirements.txt
python taptaploot_clicker.py
```

需要 Python 3.10+（建議 3.11+ 內建 `tomllib`）。

## 打包成 exe

```bash
build.bat
```

完成後產生兩個檔案於 `dist\`（單一檔案，~30-40 MB）：

- `TapTapLootClicker.exe` — 最新版（覆寫式）
- `TapTapLootClicker-v1.0.0.exe` — 帶版本號副本，可直接上傳到 GitHub Release

> **注意**：打包前可放一個 `icon.ico` 在專案根目錄作為 exe 圖示。
> 若沒有 `icon.ico`，build.bat 會自動跳過 `--icon` 參數。

## 版本管理與發布流程

版本號的**單一來源**：`taptaploot_clicker.py` 開頭的 `__version__ = "x.y.z"`。

### 發布新版本步驟

1. 更新 `taptaploot_clicker.py` 的 `__version__`（遵循 [SemVer](https://semver.org/lang/zh-TW/)）
2. 在 `CHANGELOG.md` 新增該版本的變更條目
3. 執行 `build.bat`（會自動同步版本到 exe 屬性與檔名）
4. Git 標記與推送：
   ```bash
   git add -A
   git commit -m "release: v1.2.3"
   git tag v1.2.3
   git push && git push --tags
   ```
5. GitHub → Releases → Draft new release：
   - Tag：`v1.2.3`
   - Title：`v1.2.3`
   - Description：複製 CHANGELOG 對應段落
   - Attach：`dist\TapTapLootClicker-v1.2.3.exe`

## 設定檔（`config.toml`）

```toml
[clicker]
target_window_title = "Tap Tap Loot"     # 視窗標題（FindWindow 用）
target_window_class = "UnityWndClass"    # 視窗 class（後備辨識）
cps = 10                                  # 每秒點擊數
jitter = 0.15                             # 隨機抖動 (0~0.5)
mode = "foreground"                       # 啟動模式
click_offset_x = 0                        # 點擊位置 X 偏移（相對視窗中心）
click_offset_y = 0                        # 點擊位置 Y 偏移
autostart = false                         # 啟動時自動開始

[hotkeys]
toggle = "F6"
switch_mode = "F7"
quit = "F8"

[safety]
scan_interval = 1.0                       # 競技遊戲掃描間隔（秒）
on_competitive_detected = "exit"          # "exit" 或 "pause"
```

修改後重啟程式生效。

## 故障排除

### 圖示沒出現

- 看右下角「顯示隱藏的圖示」(^)
- 可固定到工作列：設定 → 個人化 → 工作列 → 通知區域圖示

### 找不到 TapTapLoot 視窗

- 確認遊戲視窗標題確實是 "Tap Tap Loot"
- 開啟 tray 選單 → 顯示視窗資訊 → 若顯示「尚未找到」表示偵測失敗
- 修改 `config.toml` 的 `target_window_title`

### 熱鍵無效

- `keyboard` 套件在某些 Windows 設定下需要系統管理員權限
- 用「以系統管理員身分執行」啟動 exe / Python

### 點擊沒效果（看到圖示綠但遊戲沒反應）

- TapTapLoot 視窗最小化 → 還原它（最小化時 SendInput 無效）
- 嘗試切換到背景模式（F7）測試
- 用「顯示視窗資訊」確認點擊座標落在遊戲視窗內

### 背景模式閃爍很明顯

- 這是預期行為 — 焦點偷渡必須短暫切換前景
- 若無法接受，請使用前景模式

### 程式自己退出

- 看 `taptaploot_clicker.log` 確認原因
- 最常見：偵測到競技遊戲 process（CS2/Valorant 等）

## 驗證流程（首次使用）

1. **無反作弊驅動檢查**

   ```cmd
   tasklist /svc | findstr /i "vgk vgc EasyAntiCheat BEService"
   ```

   無輸出 = 安全
2. **基本功能**：啟動遊戲 → 啟動 clicker → F6 → 觀察貓咪持續攻擊
3. **前景自動暫停**：按 F6 開始 → 切到瀏覽器 → 圖示應變藍、不點瀏覽器
4. **背景模式**：F7 切換 → 切到瀏覽器 → 觀察打字仍正常（~30ms 閃爍）
5. **安全網**：開 clicker → 啟動 CS2 → 1 秒內紅色圖示 → 自動退出 + 跳訊息框

## 授權

個人使用。本工具不修改 TapTapLoot 任何檔案，僅透過標準 Windows API 模擬輸入。

## 技術細節

- 點擊機制：`SendInput` ctypes 直接呼叫，繞過 Python wrapper 開銷
- 焦點偷渡：`AttachThreadInput` + `SetForegroundWindow` 避開 Windows 反搶焦點限制
- 視窗偵測：`FindWindow` 主、`EnumWindows` 後備（class + 標題比對）
- 安全偵測：`psutil` 列舉 process，掃描競技遊戲與反作弊服務名稱
- 系統匣：`pystray` + `Pillow` 動態生成彩色圓點圖示

## 問題回報

歡迎在 GitHub Issues 回報任何問題或建議！請盡量提供詳細資訊（錯誤訊息、日誌、重現步驟）以協助排查。

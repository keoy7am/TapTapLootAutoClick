# Changelog

本檔案記錄所有版本變更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號遵循 [SemVer](https://semver.org/lang/zh-TW/)。

## [Unreleased]

### Planned
- 多視窗同時掛機支援
- 自訂點擊序列（連點 / 鍵盤組合）
- GUI 設定面板（取代 config.toml 編輯）

---

## [1.0.0] - 2026-04-18

### Added
- 雙模式點擊（前景模式 / 背景焦點偷渡模式）
- 系統匣常駐圖示，4 色狀態（綠 / 黃 / 藍 / 紅）
- 全域熱鍵（F6 toggle / F7 切換模式 / F8 退出）
- Tray 右鍵選單：toggle、模式切換、CPS 調整、視窗資訊、開啟設定/日誌、關於、退出
- 競技遊戲偵測安全網（CS2 / Valorant / EAC / BattlEye / FACEIT）
  - 啟動時偵測：拒絕啟動
  - 執行時每秒掃描：偵測即強制退出
- Process 名稱優先的視窗偵測（最可靠，後備 title / class）
- DPI 感知支援（高解析度顯示器座標正確）
- `hold_ms` 設定（按下與放開之間延遲，解決 Unity 逐 frame 輪詢漏判問題）
- 隨機抖動（jitter）模擬人類點擊間隔
- 設定檔 `config.toml`（hot reload 需重啟）
- 完整日誌（`taptaploot_clicker.log`）
- 診斷工具 `diagnose_windows.py`（列出所有可見視窗）
- PyInstaller 一鍵打包成單一 exe（`build.bat`）
- Windows exe 檔案屬性嵌入版本資訊

### Security
- 不安裝任何核心驅動
- 不對 TapTapLoot 進行 DLL 注入或記憶體寫入
- 僅使用 Windows 標準 SendInput API

# Playwright MCP 安裝手冊（Windows + VS Code）

## 文件目的
本手冊用於在 Windows 環境完成 Playwright MCP 安裝，並在 VS Code 的 MCP Client 中正常啟用與驗證。

## 1. 前置需求

1. Node.js 版本需為 18 以上（建議使用 20 或 22 LTS）。
2. 需可使用 npm 與 npx。
3. VS Code 建議更新至新版，以降低 MCP 相容性問題。

### 快速檢查指令

~~~powershell
node -v
npm -v
npx -v
~~~

## 2. 安裝策略

建議使用 npx 啟動 Playwright MCP，避免全域安裝帶來的版本維護成本。

核心設定為：

- command: npx
- args: @playwright/mcp@latest

## 3. MCP 設定範例

請在你的 MCP Client 設定中加入以下內容：

~~~json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
~~~

## 4. 初次啟動與驗證

1. 重新載入 VS Code 或 MCP Client。
2. 確認工具清單中已出現 Playwright 相關工具。
3. 進行最小驗證流程：
   - 開啟網頁
   - 讀取頁面標題
   - 關閉頁面

## 5. 常用進階參數

可依需求加入以下參數：

1. 背景執行：--headless
2. 指定瀏覽器：--browser msedge 或 --browser chrome
3. 避免多實例衝突：--isolated
4. 指定登入資料路徑：--user-data-dir <path>

## 6. 建議設定組合

### 開發版（方便除錯）

~~~json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--browser",
        "msedge"
      ]
    }
  }
}
~~~

### 排程版（穩定、低干擾）

~~~json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--headless",
        "--browser",
        "msedge",
        "--isolated"
      ]
    }
  }
}
~~~

## 7. 常見問題排除

1. npx 指令找不到：
   - Node.js 可能未正確安裝或 PATH 尚未生效。
   - 請重開終端機後再測試。
2. 套件下載失敗（公司網路）：
   - 請先設定 npm proxy。
3. 多個 MCP Client 同時連同一個 workspace：
   - 可能發生 profile 衝突。
   - 建議改用 --isolated 或不同 --user-data-dir。

## 8. 實施建議（對目前專案）

1. 先套用最小設定確認可正常運作。
2. 穩定後加入 --headless 與 --browser msedge。
3. 若進入長期自動化，再規劃 output 目錄與 session 管理策略。

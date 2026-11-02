# taiwan-stock-bot

1. **ETF持股日報**（`main.py`）：每日抓大盤與主動式 ETF 持股，產生報表並用 LINE 推播。
2. **自動交易機器人**（`run_trading_bot.py` + `trading_bot/`）：串接富邦證券新一代 API，依策略自動下單。

---

## 自動交易機器人

> ⚠️ 程式交易有實際虧損風險。請先用模擬模式與試跑模式長時間驗證，再小額實盤。

### 架構

```
trading_bot/
├── brokers/
│   ├── base.py      # 券商介面
│   ├── paper.py     # 模擬券商（不連線，狀態存在 logs/paper_state.json）
│   └── fubon.py     # 富邦新一代 API（所有 SDK 呼叫只在這裡）
├── strategy.py      # 策略：均線交叉 ma_cross、RSI 反彈 rsi、突破新高 breakout
├── backtest.py      # 回測引擎
├── risk.py          # 風控（交易時段、金額上限、每日筆數、價格偏離、緊急停止）
├── bot.py           # 主流程：資料 → 訊號 → 風控 → 下單 → 紀錄 / LINE 通知
├── datafeed.py      # FinMind 日K
└── notifier.py      # LINE 通知（只發給 LINE_USER_ID）
trading_config.json  # 交易標的、策略參數、風控參數
backtest.py          # 回測工具（命令列）
```

### 回測：先用歷史資料比較策略

Windows 直接雙擊 `run_backtest.bat`，或：

```bash
python backtest.py                                   # 設定檔裡的股票 × 所有策略，近 3 年
python backtest.py --symbols 2884 0056 --years 5     # 指定股票與年數
python backtest.py --strategy rsi --param oversold=25 --trades   # 調參數並列出每筆交易
```

回測規則：收盤後判斷訊號、隔天開盤價成交；計入手續費（0.1425%，最低 20 元，可用 `--min-fee` 調整）
與證交稅（股票 0.3%、ETF 0.1%）。**未計入股利**，高股息 ETF 的實際報酬會比回測結果高。
過去績效不代表未來，也要小心「把參數調到剛好符合過去」的過度最佳化。

### 零股交易

設定檔 `strategy` 區塊：

| 參數 | 說明 |
|---|---|
| `name` / `params` | 使用的策略與參數 |
| `buy_amount` | 每次買進金額（元），例如 45000 |
| `allow_odd_lot` | `true` 時可買零股；超過 1000 股的部分自動拆成「整股」與「盤中零股」兩筆委託 |

例：`buy_amount` 45000、股價 30 → 買 1500 股，拆成 1000 股整股 + 500 股零股；股價 2400 → 買 18 股零股。

### 三種執行模式

| 模式 | 指令 | 會下真單？ |
|---|---|---|
| 模擬 | `python run_trading_bot.py` | 否，用虛擬資金 |
| 富邦試跑 | `python run_trading_bot.py --broker fubon` | 否，登入富邦讀庫存/報價，只記錄「會下的單」 |
| 富邦實盤 | `TRADING_MODE=live python run_trading_bot.py --broker fubon --live` | **是** |

Windows 使用者可以直接雙擊 `run_paper.bat` 執行模擬模式、雙擊 `run_backtest.bat` 執行回測。

實盤必須**同時**有 `--live` 參數與 `TRADING_MODE=live` 環境變數，避免誤觸。
加上 `--loop 5` 可在交易時段內每 5 分鐘執行一次。

### 富邦 API 申請與安裝

1. 到富邦證券官網「新一代API」頁面申請 API 使用權限並簽署同意書。
2. 申請並下載電子憑證（`.pfx`）。
3. 下載對應作業系統的 `fubon_neo` SDK（`.whl`），安裝：
   ```bash
   pip install requests
   pip install fubon_neo-<版本>-cp37-abi3-<平台>.whl
   ```
4. 複製 `.env.example` 為 `.env` 並填入身分證字號、密碼、憑證路徑與憑證密碼。
   `.env` 與 `*.pfx` 已列入 `.gitignore`，**絕對不要 commit 到 GitHub**。

### 風控設定（trading_config.json）

| 參數 | 說明 |
|---|---|
| `max_order_value` | 單筆委託金額上限（元） |
| `max_position_value` | 單一個股持有市值上限（元） |
| `max_daily_orders` | 每日最多委託筆數（重啟程式也會延續） |
| `max_price_deviation` | 委託價與最新價最大偏離比例 |
| `kill_switch_file` | 這個檔案存在時拒絕所有委託，例如 `touch STOP_TRADING` 立即停機 |

其他保護：只做現股（不放空，賣出不超過庫存）、同一檔股票每日最多委託一次。

### 換策略

改設定檔的 `strategy.name` 即可（`ma_cross` / `rsi` / `breakout`）。
要寫新策略：在 `strategy.py` 新增一個類別（有 `name`、`label`、`min_bars` 與
`generate(symbol, closes, position_qty)`），並加進 `STRATEGIES`，機器人和回測就都能用。

### 測試

```bash
pip install pytest
python -m pytest tests
```

### 注意事項

- 富邦憑證與帳密不建議放在 GitHub Actions；請在自己的電腦或 VPS 上執行實盤。
- 未處理國定假日判斷，休市日送單會被券商拒絕（不會成交）。
- 限價單送出後可能未成交，機器人不會自動改單或刪單，請到富邦 App 確認。

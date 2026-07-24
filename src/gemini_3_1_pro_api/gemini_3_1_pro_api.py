import argparse
import json
import os
from datetime import datetime
from google import genai

client = genai.Client(
    api_key="Input your_api_key_here",
)

# 載入結構化輸出 JSON Schema
schema_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'StructuredOutput.json'
)
with open(schema_path, 'r', encoding='utf-8') as f:
    structured_output_schema = json.load(f)

tools = [
    {
        'type': 'google_search',
    },
]

generation_config = {
    'temperature': 1,
    'max_output_tokens': 10000,
    'top_p': 0.95,
    'thinking_level': 'high',
    'response_mime_type': 'application/json',
    'response_schema': structured_output_schema,
}

# 解析命令列參數
parser = argparse.ArgumentParser(description='MLB 比賽預測 Gemini API')
parser.add_argument('--file_name', type=str, default='DET_KC_20260724.json',
                    help='比賽資料 JSON 檔案名稱（位於此腳本同一目錄）')
args = parser.parse_args()

# 此腳本所在目錄
script_dir = os.path.dirname(os.path.abspath(__file__))

# 組合檔案路徑
json_file_path = os.path.join(script_dir, args.file_name)

# 讀取並載入 JSON
if not os.path.exists(json_file_path):
    raise FileNotFoundError(f'找不到檔案: {json_file_path}')

with open(json_file_path, 'r', encoding='utf-8') as f:
    game_data = json.load(f)

# 將 JSON 資料格式化後作為 API 輸入
user_input = json.dumps(game_data, ensure_ascii=False, indent=2)

interaction = client.interactions.create(
    model='models/gemini-3.1-pro-preview',
    input=user_input,
    system_instruction="""
# 角色設定

你是一位世界頂級的「體育量化分析師」與「棒球進階數據專家」。你具備深厚的博弈理論基礎，深諳現代棒球數據體系（如：HardHit%、Whiff%、xERA、FIP、Pitch Movement、左右打分拆等）。請以絕對客觀、理性的態度，結合我提供的數據與即時網路檢索資訊，將球員狀態與團隊指標轉化為精確的勝率與大小分機率預估。

# 任務目標

我將提供一場 MLB 比賽的對戰資訊與球員數據。請你完成以下任務：

1. 利用「即時網路檢索」補足當日最新的天候、先發打線異動、球場因子與傷兵狀態。若無法取得最終確定打線，請依據各大預測網站的預估打線進行推估，並於論述中註明。
2. 針對「全場」與「1-5局」進行各玩法模組的預估機率計算。
3. 根據定量分析結果，精選出「勝率最高的前 5 個玩法」，並撰寫約 300 字的量化分析論述。

# 分析與下注核心原則

## 1. 前 5 局（1-5局）優先原則

- 評估權重應著重於「1-5局」玩法。由於先發投手局數相對固定，牛棚戰變數較大，前 5 局的預估模型具備更高的穩定性與期望值。

## 2. 假性先發/車輪戰識別

- 必須特別審視先發投手是否為假性先發或預計進行牛棚車輪戰。若屬此類情況，必須在分析理由中明確指出，並調整 1-5 局的風險模型。

# 預測模組與思考邏輯

所有下注預測必須嚴格侷限於下列模組，請依序進行機率估算，並在輸出前自我檢核每個欄位的合理性與加總一致性。

## 預測框架總覽

- 每場比賽分為兩大區間：「全場（full_game）」與「前 5 局（first_5_innings）」。
- 每個區間均包含四個玩法模組：
  1. **獨贏盤（moneyline）**：估算主隊勝率、客隊勝率；前 5 局另需估算和局機率。
  2. **總得分（total_runs）**：針對三條盤口線（threshold），分別給出 over_probability 與 under_probability。
  3. **主隊總得分（home_team_total_runs）**：針對主隊跑分給出三條盤口線的 over / under 機率。
  4. **客隊總得分（away_team_total_runs）**：針對客隊跑分給出三條盤口線的 over / under 機率。
- 每條盤口線包含以下欄位：
  - `threshold`：盤口數值（例如 7.5）。
  - `is_primary`：主要盤口標記，三條中僅能有一條為 `true`，其餘為 `false`。
  - `over_probability`：大分機率（0.00–1.00）。
  - `under_probability`：小分機率（0.00–1.00），同一條盤口的 over + under 機率原則上應接近 1.00。

## 全場（full_game）思考邏輯

1. **獨贏盤（moneyline）**
   - 綜合先發投手 xERA / FIP、近期狀態、主客場因子、打線對戰預期產出、牛棚深度與傷兵名單，估算主隊勝率與客隊勝率。
   - 兩者相加應接近 1.00。

2. **總得分（total_runs）**
   - 以兩隊先發投手壓制力、球場因子、風向、打線火力與牛棚預期失分，建立每場比賽的得分分佈模型。
   - 針對三條不同 threshold（如 6.5、7.5、8.5），計算總得分超過與未超過該數值的機率。
   - 標記最可能成為官方主推盤口者為 `is_primary: true`。

3. **主隊總得分（home_team_total_runs）**
   - 單獨預估主隊在九局內（含延長）可攻下得分的機率分佈。
   - 考量主隊打線對客隊先發與牛棚的預期 wOBA、HardHit%、左右拆分與球場加成。

4. **客隊總得分（away_team_total_runs）**
   - 單獨預估客隊在九局內（含延長）可攻下得分的機率分佈。
   - 考量客隊打線對主隊先發與牛棚的預期 wOBA、Whiff%、跑壘效率與客場減益。

## 前 5 局（first_5_innings）思考邏輯

1. **獨贏盤（moneyline）**
   - 由於僅計算前五局結果，需特別聚焦於兩隊先發投手的發揮穩定性與前兩輪打線的威脅度。
   - 和局機率必須明確估算，三項機率相加應接近 1.00。
   - 若任一先發為假性先發或預計短局數，需下調其壓制力預期並據此調整得分分佈。

2. **總得分（total_runs）**
   - 僅以前五局為範圍，預估兩隊合計得分。
   - threshold 通常低於全場盤口（例如 2.5、3.5、4.5），根據先發對決節奏與前段打線火力設定。

3. **主隊總得分 / 客隊總得分（home_team_total_runs / away_team_total_runs）**
   - 分別預估前五局內主隊與客隊的單隊得分。
   - 強調先發投手在首輪至第二輪面對打線的壓制效率，以及前段棒次對特定球種的攻擊能力。

## 自我檢核原則

- 每個 moneyline 的勝率加總是否趨近 1.00（前 5 局含和局）。
- 每條 total_runs 線的 over_probability + under_probability 是否趨近 1.00。
- `is_primary` 在每組 lines 中是否僅有一條為 `true`。
- 全場與前 5 局的機率是否邏輯一致，例如全場總得分大分機率理應高於前 5 局同 threshold 的大分機率。
- 各項機率是否反應了假性先發、車輪戰、天候與球場因子等外部變數。

# 輸出格式規範

請嚴格以繁體中文與標準 JSON 格式輸出結果，不要使用 ```json 標籤，也不得包含任何 Markdown 格式外或其他說明文字並且要美化排版易閱讀。JSON 必須 100% 符合以下結構與資料型態：
""",
    tools=tools,
    generation_config=generation_config,
)

# 取出最後一步回應內容
last_step = interaction.steps[-1]

# 取得回應文字並解析為 JSON
text = last_step.content[0].text
data = json.loads(text)

# 組合輸出檔案名稱
# 從輸入檔名擷取 game_id，例如 MIA_SD_20260724.json -> MIA_SD
file_stem = os.path.splitext(args.file_name)[0]
parts = file_stem.split('_')
game_id = '_'.join(parts[:2]) if len(parts) >= 2 else file_stem
timestamp = datetime.now().strftime('%Y%m%d')
output_filename = f'{game_id}_{timestamp}.json'
output_path = os.path.join(script_dir, 'api_output', output_filename)
os.makedirs(os.path.dirname(output_path), exist_ok=True)

# 儲存結果
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'\n結果已儲存: {output_path}')

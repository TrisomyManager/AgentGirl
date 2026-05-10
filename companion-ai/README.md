# Companion AI

Companion AI is the active module library and reference app in this repository. Historical upstream reference projects have been removed from the workspace; current development should stay inside this project.

## 鏋舵瀯姒傝

Companion AI 褰撳墠鍚屾椂鏀寔涓ょ杩愯鏂瑰紡锛?

- 鍗曚綋妯″紡锛氭湰鍦板紑鍙戝拰 MVP 榛樿鏂瑰紡锛屼竴涓?FastAPI 杩涚▼鎸傝浇鍏ㄩ儴 router
- 寰湇鍔℃ā寮忥細淇濈暀鍚勬ā鍧楃嫭绔嬪惎鍔ㄦ柟寮忥紝渚夸簬鍚庣画鎷嗗垎涓庡帇娴?

閫昏緫妯″潡浠嶇劧淇濇寔 7 涓湇鍔¤竟鐣?+ 1 涓墠绔?SDK锛?

| 妯″潡 | 绔彛 | 鑱岃矗 |
|------|------|------|
| `core_orchestrator` | 8000 | LangGraph 鐘舵€佹満銆佹剰鍥捐瘑鍒€佽法妯″潡璋冨害 |
| `persona_engine` | 8001 | 缁撴瀯鍖栦汉鏍笺€佹儏鎰熺姸鎬佹満銆佸叧绯绘寚鏍?|
| `memory_system` | 8002 | 鍚戦噺璁板繂銆佺煡璇嗗浘璋便€佷簲闃舵璁板繂娌夋穩 |
| `voice_layer` | 8003 | ASR(鎯呮劅鎰熺煡)銆乀TS(鎯呮劅璇煶) |
| `action_layer` | 8004 | 2D 鍔ㄤ綔鐢熸垚銆佸攪褰㈠悓姝?|
| `device_coordination` | 8005 | 璁惧娉ㄥ唽銆丮QTT 娑堟伅鎬荤嚎 |
| `gateway_adapter` | 8006 | 澶氬钩鍙扮綉鍏抽€傞厤銆丄pp WebSocket |
| `frontend_sdk` | 鈥?| TypeScript SDK锛堢嫭绔?App锛?|

## 蹇€熷紑濮?

### 1. 閰嶇疆鐜

```bash
cp .env.example .env
# 缂栬緫 .env 濉叆浣犵殑浜?API Key
```

### 2. 鍚姩鍩虹璁炬柦锛堝畬鏁存ā寮忥級

```bash
docker compose up -d postgres neo4j redis mosquitto
```

### 3. 瀹夎渚濊禆锛堝紑鍙戞ā寮忥級

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 4. 鍚姩鍗曚綋妯″紡锛堟帹鑽愶級

```bash
uvicorn main:app --reload --port 8000
```

Lite Mode锛堟棤闇€ Docker锛屼娇鐢?SQLite + 鍐呭瓨鏇夸唬锛夛細

```bash
# PowerShell
$env:COMPANION_LITE_MODE="true"
uvicorn main:app --reload --port 8000
```

### 5. 鍚姩鍚勬湇鍔★紙寰湇鍔℃ā寮忥紝鍙€夛級

```bash
# 鏍稿績缂栨帓
uvicorn core_orchestrator.main:app --reload --port 8000

# 浜烘牸寮曟搸
uvicorn persona_engine.main:app --reload --port 8001

# 璁板繂绯荤粺
uvicorn memory_system.main:app --reload --port 8002

# 璇煶灞?
uvicorn voice_layer.main:app --reload --port 8003

# 鍔ㄤ綔灞?
uvicorn action_layer.main:app --reload --port 8004

# 璁惧鍗忓悓
uvicorn device_coordination.main:app --reload --port 8005

# 缃戝叧閫傞厤
uvicorn gateway_adapter.main:app --reload --port 8006
```

### 6. 鍚姩 Celery 宸ヤ綔杩涚▼锛堝畬鏁存ā寮忥級

```bash
celery -A memory_system.pipeline worker --loglevel=info
```

### 7. 鍓嶇 Web App锛堟湰鍦伴瑙堬級

`frontend_app/` 鏄粯璁ょ殑鏈湴璋冭瘯 / 棰勮鐣岄潰锛圴ue 3 + Vite锛夈€傚厛纭繚浣犳湰鏈鸿濂戒簡
Node.js锛堚墺 18锛? npm锛岀劧鍚庯細

```bash
cd frontend_app
npm install            # 绗竴娆″繀椤诲厛瑁呬緷璧?
npm run dev            # 榛樿 http://localhost:5173
```

濡傛灉鍚庣涓嶆槸榛樿鐨?`http://127.0.0.1:8000`锛屽彲浠ョ敤鐜鍙橀噺瑕嗙洊锛?

```bash
# PowerShell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"; npm run dev

# bash / zsh
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

鎴栬€呯洿鎺ョ敤鏍圭洰褰曟彁渚涚殑涓€閿剼鏈悓鏃舵媺璧峰悗绔?+ 鍓嶇锛?

```bash
# Windows PowerShell
.\start_mvp.ps1
# Windows cmd
start_mvp.bat
```

> 杩欎袱涓剼鏈細鑷姩鍦?`frontend_app/` 涓嬪仛涓€娆?`npm install`锛堜粎褰?
> `node_modules/` 缂哄け鏃讹級锛岀劧鍚?`npm run dev`锛岄伩鍏嶅共鍑€ clone 鍚庣浜屼釜绐楀彛
> 鐩存帴 `npm run dev` 鎶ラ敊銆?

### 8. 鍓嶇 SDK锛堢嫭绔?App 闆嗘垚鏃朵娇鐢級

```bash
cd frontend_sdk
npm install
npm run build
```

## 璁捐鍐崇瓥

- **鍏ㄤ簯 API**锛歀LM銆丄SR銆乀TS銆佸姩浣滅敓鎴愬叏閮ㄨ蛋浜?API锛屾棤闇€鏈湴 GPU
- **鍗曡鑹叉繁搴﹀吇鎴?*锛氬敮涓€浜烘牸鏂囦欢 `persona_engine/data/soul.yaml`锛屽叧绯绘寚鏍囬殢鏃堕棿婕斿寲
- **2D 椹卞姩 MVP**锛氶€氫箟涓囩浉鐢熸垚鍔ㄤ綔搴忓垪锛屽墠绔簭鍒楀抚娓叉煋 + 鍞囧舰鍚屾
- **浜嬩欢椹卞姩**锛氭ā鍧楅棿閫氳繃 Redis Pub/Sub 瑙ｈ€︼紝鍚屾璋冪敤閫氳繃鍐呴儴 HTTP API

## 褰撳墠鐘舵€?

- 鍗曚綋鍏ュ彛 `main.py` 宸插彲鐢紝Lite Mode 涓?`/health` 鍙甯歌繑鍥?
- 鍏ㄩ噺 Python 娴嬭瘯宸查€氳繃锛歚97 passed / 0 failed`锛?026-05-05锛?
- 璁″垝鏂囨。浠嶄繚鐣欎腑闀挎湡鐩爣锛屼絾浠ヤ粨搴撳疄闄呭疄鐜颁负鍑?

## 妯″潡闂撮€氫俊

```
Redis Pub/Sub Channels:
  companion:turn:start      鈫?gateway 鈫?core
  companion:turn:end        鈫?core 鈫?gateway
  companion:memory:sync     鈫?core 鈫?memory
  companion:action:generate 鈫?core 鈫?action
  companion:voice:synthesize 鈫?core 鈫?voice
  companion:persona:update  鈫?core 鈫?persona
  companion:device:command  鈫?core 鈫?device

HTTP API:
  core 鈫?persona(8001) 鈫?memory(8002) 鈫?voice(8003)
       鈫?action(8004) 鈫?device(8005) 鈫?gateway(8006)
```

## 鐩綍缁撴瀯

```
companion-ai/
鈹溾攢鈹€ shared/              # 鍏变韩濂戠害锛圥ydantic 妯″瀷銆佷簨浠躲€侀厤缃級
鈹溾攢鈹€ core_orchestrator/   # 鏍稿績缂栨帓灞?
鈹溾攢鈹€ persona_engine/      # 浜烘牸寮曟搸
鈹溾攢鈹€ memory_system/       # 璁板繂绯荤粺
鈹溾攢鈹€ voice_layer/         # 璇煶浜や簰灞?
鈹溾攢鈹€ action_layer/        # 鍔ㄤ綔鐢熸垚灞?
鈹溾攢鈹€ device_coordination/ # 璺ㄨ澶囧崗鍚?
鈹溾攢鈹€ gateway_adapter/     # 缃戝叧閫傞厤灞?
鈹溾攢鈹€ frontend_sdk/        # 鍓嶇 SDK锛圱ypeScript锛?
鈹溾攢鈹€ docker-compose.yml   # 瀹屾暣閮ㄧ讲
鈹溾攢鈹€ Dockerfile           # 缁熶竴闀滃儚
鈹斺攢鈹€ pyproject.toml       # 渚濊禆绠＄悊
```

## License

MIT

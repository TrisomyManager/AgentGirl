# Companion AI 鈥?妯″潡鎺ュ彛濂戠害鏂囨。

> 鐗堟湰锛歏1.0
> 鐢ㄩ€旓細鏀寔鍚勬ā鍧楃嫭绔嬪紑鍙戙€佺嫭绔嬫祴璇曘€佺嫭绔嬮儴缃?
> 鍘熷垯锛氭ā鍧椾箣闂翠粎閫氳繃鏈枃妗ｅ畾涔夌殑鎺ュ彛閫氫俊锛岀姝㈢洿鎺ヤ唬鐮佽€﹀悎

---

## 1. 鎬讳綋鏋舵瀯

```
frontend_app (Vue 3) 鈹€鈹€HTTP/WebSocket鈹€鈹€鈻?main.py:8000 (缁熶竴鍏ュ彛)
                                              鈹?
                    鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹尖攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
                    鈻?                        鈻?                        鈻?
            gateway_adapter            core_orchestrator          persona_engine
               :8000                      :8100                     :8101
                    鈹?                        鈹?                        鈹?
                    鈹?                   鈹屸攢鈹€鈹€鈹€鈹粹攢鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?         鈹?
                    鈹?                   鈻?        鈻?       鈻?         鈹?
                    鈹?             memory_system voice_layer action_layer
                    鈹?                 :8102       :8103       :8104
                    鈹?                                             鈹?
                    鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
                                           鈹?
                                    device_coordination :8105
```

**杩愯妯″紡**锛?
- **鍗曚綋妯″紡 (Monolithic)**锛歚uvicorn main:app --port 8000`锛屾墍鏈夋ā鍧楀湪涓€涓繘绋?
- **寰湇鍔℃ā寮?(Microservice)**锛歚uvicorn {module}.main:app --port 8xxx`锛屾瘡涓ā鍧楃嫭绔嬭繘绋?

---

## 2. 鎺ュ彛瑙勮寖鎬昏

| 鎺ュ彛绫诲瀷 | 鐢ㄩ€?| 鏍煎紡 |
|---------|------|------|
| **REST API** | 鍚屾璇锋眰/鍝嶅簲 | JSON over HTTP |
| **WebSocket** | 瀹炴椂闊抽娴併€佸姩浣滃抚鎺ㄩ€?| Binary/JSON |
| **Redis Pub/Sub** | 寮傛浜嬩欢閫氱煡 | JSON |
| **鍏变韩鏁版嵁搴?* | 鎸佷箙鍖栧瓨鍌?| 鍚勮嚜鐙珛 schema |

**绂佹**锛?
- 绂佹妯″潡 A `import` 妯″潡 B 鐨勫唴閮ㄥ疄鐜?
- 绂佹妯″潡 A 鐩存帴璁块棶妯″潡 B 鐨勬暟鎹簱琛?
- 绂佹妯″潡闂撮€氳繃鍏ㄥ眬鍙橀噺閫氫俊

---

## 3. 妯″潡璇︾粏濂戠害

### 3.1 gateway_adapter锛堝墠绔綉鍏筹級

| 灞炴€?| 鍊?|
|------|-----|
| 绔彛 | 8000锛堝崟浣擄級/ 8006锛堝井鏈嶅姟锛?|
| 鑱岃矗 | 鍓嶇缁熶竴鍏ュ彛銆乄ebSocket 闀胯繛鎺ャ€佸骞冲彴娑堟伅閫傞厤 |

**鏆撮湶鎺ュ彛**锛?

| 绔偣 | 鏂规硶 | 璇锋眰 | 鍝嶅簲 | 璇存槑 |
|------|------|------|------|------|
| `/gateway/ws/{user_id}` | WebSocket | binary/JSON | JSON | 鍓嶇闀胯繛鎺?|
| `/gateway/send` | POST | `{user_id, platform, content, voice_url, action_sequence}` | `{success, message_id}` | 鍙戦€佹秷鎭?|
| `/gateway/broadcast` | POST | `{user_id, content, exclude_platforms}` | `{success, sent_to[]}` | 骞挎挱娑堟伅 |
| `/gateway/receive` | POST | `{user_id, platform, content, ...}` | `{success, session_id}` | 鎺ユ敹骞冲彴娑堟伅 |
| `/gateway/sessions/{user_id}` | GET | - | `{sessions[]}` | 浼氳瘽鍒楄〃 |

**渚濊禆鐨勫閮ㄦ湇鍔?*锛?
- core_orchestrator: `POST /orchestrator/turn`

**鐙珛寮€鍙?Mock**锛?
```python
# 涓嶉渶瑕?core_orchestrator锛岀洿鎺ヨ繑鍥炲浐瀹氬洖澶?
@app.post("/gateway/send")
async def mock_send(body):
    return {"success": True, "message_id": "mock-001"}
```

---

### 3.2 core_orchestrator锛堟牳蹇冪紪鎺掞級

| 灞炴€?| 鍊?|
|------|-----|
| 绔彛 | 8000锛堝崟浣撳叡浜級/ 8100锛堝井鏈嶅姟锛?|
| 鑱岃矗 | LangGraph 鐘舵€佹満銆丳rompt 缁勮銆佹ā鍧楄皟搴?|

**鏆撮湶鎺ュ彛**锛?

| 绔偣 | 鏂规硶 | 璇锋眰 | 鍝嶅簲 | 璇存槑 |
|------|------|------|------|------|
| `/orchestrator/turn` | POST | `TurnRequest` | `TurnResponse` | 涓诲叆鍙?|
| `/orchestrator/health` | GET/POST | - | `{status, service}` | 鍋ュ悍妫€鏌?|
| `/orchestrator/status` | GET | - | `{modules[]}` | 妯″潡鐘舵€?|

**璋冪敤鐨勪笅娓告帴鍙?*锛?

| 琚皟鐢ㄦ柟 | 绔偣 | 鐢ㄩ€?|
|---------|------|------|
| persona_engine | `POST /persona/get_profile` | 鑾峰彇浜烘牸+鎯呮劅 |
| persona_engine | `POST /persona/generate_response` | LLM 鐢熸垚鍥炲 |
| memory_system | `POST /memory/recall` | 璇箟妫€绱㈣蹇?|
| memory_system | `POST /memory/store` | 瀛樺偍瀵硅瘽 |
| voice_layer | `POST /voice/synthesize` | TTS |
| action_layer | `POST /action/generate` | 鐢熸垚鍔ㄤ綔搴忓垪 |
| device_coordination | `POST /device/send_command` | 鍙戦€佽澶囨寚浠?|
| gateway_adapter | `POST /gateway/send` | 鍙戦€佸搷搴斿埌鍓嶇 |

**鐙珛寮€鍙?Mock**锛?
```python
# 涓嬫父妯″潡鏈氨缁椂锛岀洿鎺ヨ繑鍥?fallback
@app.post("/orchestrator/turn")
async def mock_turn(body):
    return {
        "turn_id": "mock-001",
        "assistant_message": "鎴戝湪鍛紝浣犵户缁銆?,
        "emotion": "calm",
    }
```

---

### 3.3 persona_engine锛堜汉鏍煎紩鎿庯級

| 灞炴€?| 鍊?|
|------|-----|
| 绔彛 | 8101 |
| 鑱岃矗 | 浜烘牸瀹氫箟銆佹儏鎰熺姸鎬佹満銆佸叧绯昏拷韪€佽姘旂敓鎴?|

**鏆撮湶鎺ュ彛**锛?

| 绔偣 | 鏂规硶 | 璇锋眰 | 鍝嶅簲 | 璇存槑 |
|------|------|------|------|------|
| `/persona/get_profile` | POST | `{user_id}` | `{persona, emotion, relationship, tone_text}` | 鑾峰彇瀹屾暣浜烘牸 |
| `/persona/update_emotion` | POST | `{user_id, event_type, sentiment, ...}` | `{new_emotion}` | 鏇存柊鎯呮劅 |
| `/persona/relationship` | POST | `{user_id}` | `{relationship}` | 鍏崇郴鎸囨爣 |
| `/persona/daily_digest` | POST | `{user_id}` | `{digest, relationship, emotion}` | 姣忔棩鍏崇郴鎬荤粨 |
| `/persona/generate_response` | POST | `{user_id, user_message, system_prompt, emotion, relationship}` | `{assistant_message, new_emotion, sentiment}` | LLM 鐢熸垚 |

**渚濊禆鐨勫閮ㄦ湇鍔?*锛?
- LLM API锛圤penAI/Anthropic锛?
- PostgreSQL/Redis锛坆est-effort锛屽け璐ユ椂闄嶇骇鍐呭瓨瀛樺偍锛?

**鐙珛寮€鍙?Mock**锛?
```bash
# 娴嬭瘯浜烘牸鍔犺浇
curl -X POST http://localhost:8101/persona/get_profile \
  -d '{"user_id": "test"}'

# 娴嬭瘯鍥炲鐢熸垚锛堥渶瑕?LLM API Key锛?
curl -X POST http://localhost:8101/persona/generate_response \
  -d '{"user_id": "test", "user_message": "浣犲ソ", "system_prompt": "浣犳槸灏忔殩"}'
```

**鍏抽敭鏂囦欢**锛?
- `persona_engine/data/soul.yaml` 鈥?浜烘牸瀹氫箟锛堝彲淇敼锛岄噸鍚敓鏁堬級

---

### 3.4 memory_system锛堣蹇嗙郴缁燂級

| 灞炴€?| 鍊?|
|------|-----|
| 绔彛 | 8102 |
| 鑱岃矗 | 鍚戦噺璁板繂銆佸璇濆綊妗ｃ€佷簲闃舵璁板繂娴佹按绾裤€佺敤鎴风敾鍍?|

**鏆撮湶鎺ュ彛**锛?

| 绔偣 | 鏂规硶 | 璇锋眰 | 鍝嶅簲 | 璇存槑 |
|------|------|------|------|------|
| `/memory/store` | POST | `{user_id, category, content, importance, emotion_tags}` | `MemoryEntry` | 瀛樺偍璁板繂 |
| `/memory/recall` | POST | `{query, user_id, top_k, include_graph}` | `MemoryRecallResult` | 璇箟妫€绱?|
| `/memory/graph_query` | POST | `{cypher, parameters}` | `List[dict]` | 鐭ヨ瘑鍥捐氨鏌ヨ |
| `/memory/pipeline/trigger` | POST | `{turn_id, user_message, assistant_message}` | `{task_id}` | 瑙﹀彂娴佹按绾?|
| `/memory/user/{user_id}/summary` | GET | - | `{total_memories, avg_importance, ...}` | 鐢ㄦ埛鎽樿 |
| `/memory/maintenance/decay` | POST | - | `{expired_deleted}` | 娓呯悊杩囨湡璁板繂 |

**渚濊禆鐨勫閮ㄦ湇鍔?*锛?
- PostgreSQL + pgvector锛堜富瀛樺偍锛?
- Neo4j锛堢煡璇嗗浘璋憋紝鍙€夛級
- OpenAI API锛坋mbeddings锛?

**鐙珛寮€鍙?Mock**锛?
```bash
# 瀛樺偍璁板繂
curl -X POST http://localhost:8102/memory/store \
  -d '{"user_id": "u1", "category": "preference", "content": "鍠滄鍜栧暋"}'

# 鍙洖璁板繂
curl -X POST http://localhost:8102/memory/recall \
  -d '{"query": "鍠濅粈涔?, "user_id": "u1", "top_k": 5}'
```

**Lite Mode 琛屼负**锛?
- 浣跨敤 SQLite 鏇夸唬 PostgreSQL
- 鍚戦噺妫€绱㈤€€鍖栦负 Python 璁＄畻鐨勪綑寮︾浉浼煎害
- 鐭ヨ瘑鍥捐氨琚烦杩?

---

### 3.5 voice_layer锛堣闊冲眰锛?

| 灞炴€?| 鍊?|
|------|-----|
| 绔彛 | 8103 |
| 鑱岃矗 | ASR銆乀TS銆佽闊虫祦绠＄悊銆乂AD |

**鏆撮湶鎺ュ彛**锛?

| 绔偣 | 鏂规硶 | 璇锋眰 | 鍝嶅簲 | 璇存槑 |
|------|------|------|------|------|
| `/voice/transcribe` | POST | `multipart: audio file + language` | `{text, confidence, emotion}` | 璇煶杞枃瀛?|
| `/voice/synthesize` | POST | `{text, voice_id, emotion, speed}` | `{audio_url, duration_ms}` | 鏂囧瓧杞闊?|
| `/voice/stream` | WebSocket | binary audio chunks | JSON transcription | 瀹炴椂璇煶娴?|

**渚濊禆鐨勫閮ㄦ湇鍔?*锛?
- OpenAI Whisper / Groq锛圓SR锛?
- Fish Audio S2 / ChatTTS锛圱TS锛?

**鐙珛寮€鍙?Mock**锛?
```bash
# ASR 娴嬭瘯
curl -X POST http://localhost:8103/voice/transcribe \
  -F "audio=@test.wav" -F "language=zh"

# TTS 娴嬭瘯
curl -X POST http://localhost:8103/voice/synthesize \
  -d '{"text": "浣犲ソ", "emotion": "happy"}' --output output.mp3
```

---

### 3.6 action_layer锛堝姩浣滃眰锛?

| 灞炴€?| 鍊?|
|------|-----|
| 绔彛 | 8104 |
| 鑱岃矗 | 鍔ㄤ綔鎰忓浘杞崲銆佸姩浣滄ā鏉裤€佸攪褰㈠悓姝?|

**鏆撮湶鎺ュ彛**锛?

| 绔偣 | 鏂规硶 | 璇锋眰 | 鍝嶅簲 | 璇存槑 |
|------|------|------|------|------|
| `/action/generate` | POST | `{turn_id, emotion, text, audio_duration_ms}` | `ActionSequence` | 鐢熸垚鍔ㄤ綔搴忓垪 |
| `/action/lip_sync` | POST | `{text, duration_ms, fps}` | `[{frame, lip_shape}]` | 鍞囧舰鍏抽敭甯?|
| `/action/templates` | GET | - | `[{name, description}]` | 鍔ㄤ綔妯℃澘鍒楄〃 |

**渚濊禆鐨勫閮ㄦ湇鍔?*锛氭棤锛堢函鍐呴儴閫昏緫锛?

**鐙珛寮€鍙?Mock**锛?
```bash
curl -X POST http://localhost:8104/action/generate \
  -d '{"emotion": "happy", "text": "浣犲ソ", "audio_duration_ms": 1500}'
# 杩斿洖锛歠rames 鍒楄〃锛屾瘡涓抚鏈?action_type 鍜?duration_ms
```

---

### 3.7 device_coordination锛堣澶囧崗鍚岋級

| 灞炴€?| 鍊?|
|------|-----|
| 绔彛 | 8105 |
| 鑱岃矗 | 璁惧娉ㄥ唽銆丮QTT 娑堟伅鎬荤嚎銆佷换鍔″垎鍙?|

**鏆撮湶鎺ュ彛**锛?

| 绔偣 | 鏂规硶 | 璇锋眰 | 鍝嶅簲 | 璇存槑 |
|------|------|------|------|------|
| `/device/register` | POST | `{device_id, device_type, device_name, ...}` | `{success, device}` | 娉ㄥ唽璁惧 |
| `/device/heartbeat` | POST | `{device_id}` | `{success}` | 蹇冭烦 |
| `/device/list/{user_id}` | GET | `?online_only=true` | `{devices[]}` | 璁惧鍒楄〃 |
| `/device/send_command` | POST | `{device_id, command, payload}` | `{success}` | 鍙戦€佹寚浠?|
| `/device/broadcast` | POST | `{user_id, command, payload}` | `{success, sent_to[]}` | 骞挎挱鎸囦护 |

**渚濊禆鐨勫閮ㄦ湇鍔?*锛?
- MQTT broker

**鐙珛寮€鍙?Mock**锛?
```bash
# 娉ㄥ唽铏氭嫙璁惧
curl -X POST http://localhost:8105/device/register \
  -d '{"device_id": "pc-001", "device_type": "pc", "device_name": "鎴戠殑鐢佃剳"}'

# 鍙戦€佹寚浠?
curl -X POST http://localhost:8105/device/send_command \
  -d '{"device_id": "pc-001", "command": "play_music"}'
```

---

## 4. 浜嬩欢鎬荤嚎濂戠害锛圧edis Pub/Sub锛?

| Channel | 鏂瑰悜 | 杞借嵎 | 璇存槑 |
|---------|------|------|------|
| `companion:turn:start` | gateway 鈫?core | `TurnStartEvent` | 鏂板璇濊疆寮€濮?|
| `companion:turn:end` | core 鈫?gateway | `TurnEndEvent` | 瀵硅瘽杞粨鏉?|
| `companion:memory:sync` | core 鈫?memory | `MemorySyncEvent` | 瑙﹀彂璁板繂瀛樺偍 |
| `companion:action:generate` | core 鈫?action | `ActionGenerateEvent` | 璇锋眰鍔ㄤ綔鐢熸垚 |
| `companion:voice:synthesize` | core 鈫?voice | `VoiceSynthesizeEvent` | 璇锋眰璇煶鍚堟垚 |
| `companion:persona:update` | core 鈫?persona | `PersonaUpdateEvent` | 鏇存柊浜烘牸鐘舵€?|
| `companion:device:command` | core 鈫?device | `DeviceCommandEvent` | 鍙戦€佽澶囨寚浠?|

**浜嬩欢瀹氫箟鏂囦欢**锛歚shared/events.py`

---

## 5. 鏁版嵁妯″瀷濂戠害锛圥ydantic锛?

**鏍稿績妯″瀷瀹氫箟鏂囦欢**锛歚shared/models.py`

| 妯″瀷 | 鐢ㄩ€?| 鍏抽敭瀛楁 |
|------|------|----------|
| `UserProfile` | 鐢ㄦ埛韬唤 | user_id, display_name, platform, language |
| `EmotionState` | 鎯呮劅鐘舵€?| primary, intensity, valence, arousal |
| `RelationshipMetrics` | 鍏崇郴鎸囨爣 | intimacy, trust, familiarity, affection |
| `PersonaProfile` | 浜烘牸瀹氫箟 | name, core_traits, communication_style |
| `TurnContext` | 瀵硅瘽涓婁笅鏂?| turn_id, session_id, user, user_message |
| `MemoryEntry` | 璁板繂鏉＄洰 | entry_id, category, content, importance |
| `ActionSequence` | 鍔ㄤ綔搴忓垪 | frames[], total_duration_ms |
| `DeviceInfo` | 璁惧淇℃伅 | device_id, device_type, capabilities, is_online |

---

## 6. 鐙珛寮€鍙戞鏌ユ竻鍗?

姣忎釜妯″潡浣滀负鐙珛 Claude 宸ョ▼寮€鍙戞椂锛岀‘淇濓細

- [ ] 妯″潡鍙嫭绔嬪惎鍔細`uvicorn {module}.main:app --port 8xxx`
- [ ] 妯″潡鏈夌嫭绔嬬殑鍋ュ悍妫€鏌ョ鐐癸細`GET /health`
- [ ] 鎵€鏈夊閮ㄤ緷璧栧彲鐢?Mock/Stub 鏇夸唬
- [ ] 鍗曞厓娴嬭瘯涓嶄緷璧栧叾浠栨ā鍧?
- [ ] 鎺ュ彛濂戠害鏂囨。涓庡疄闄呬唬鐮佷竴鑷?

### 6.1 鎺ㄨ崘鐨勭嫭绔嬪紑鍙戦『搴?

```
1. persona_engine 鈫?鏈€绠€鍗曪紝鍙渶 LLM API
2. memory_system 鈫?闇€瑕佹暟鎹簱锛屽彲鐢?SQLite
3. voice_layer 鈫?闇€瑕?ASR/TTS API
4. action_layer 鈫?鏃犲閮ㄤ緷璧?
5. device_coordination 鈫?闇€瑕?MQTT broker
6. core_orchestrator 鈫?鏈€鍚庨泦鎴愶紝渚濊禆鎵€鏈変笅娓?
7. gateway_adapter 鈫?鏈€鍚庯紝渚濊禆 core
```

---

## 7. 閰嶇疆鐜鍙橀噺

**鍩虹閰嶇疆**锛堟墍鏈夋ā鍧楀叡鐢級锛?
```bash
# 蹇呴渶
COMPANION_OPENAI_API_KEY=sk-xxx          # LLM API Key
COMPANION_DEFAULT_LLM_MODEL=gpt-4o       # 榛樿妯″瀷

# 鍙€?
COMPANION_LITE_MODE=true                 # 鏃?Docker 妯″紡锛圫QLite + 鍐呭瓨锛?
COMPANION_ENABLE_VOICE=false             # 绂佺敤璇煶妯″潡
COMPANION_ENABLE_ACTION_2D=false        # 绂佺敤鍔ㄤ綔妯″潡
COMPANION_ENABLE_DEVICE_COORDINATION=false  # 绂佺敤璁惧妯″潡

# 璇煶锛堝彲閫夛級
COMPANION_TTS_API_KEY=xxx
COMPANION_WHISPER_API_KEY=xxx
```

---

## 8. 鍏佽 import 鐭╅樀

> **瑙勫垯**锛氣渽 = 鍏佽锛屸潓 = 绂佹锛圕I 绾㈢伅锛夛紝鈥?= 鏃犳剰涔夋垨涓嶉渶瑕併€?
> **鍘熷垯**锛氭ā鍧楃嫭绔嬪彲鎷嗭紝妯悜閫氫俊浠呴€氳繃 `shared_contracts` 鐨勫绾﹀畾涔夈€?

### 8.1 涓氬姟妯″潡 鈫?鍏变韩灞?

| 涓氬姟妯″潡 (from 鈫?/ to 鈫? | `shared_contracts` | `shared_runtime` | `shared` (搴熷純) |
|--------------------------|:---:|:---:|:---:|
| `persona_engine` | 鉁?鏁版嵁妯″瀷/浜嬩欢 | 鉁?LLMClient/閰嶇疆 | 鉂?鏂颁唬鐮佺姝? 鏃т唬鐮侀€愭杩佺Щ |
| `memory_system` | 鉁?鏁版嵁妯″瀷/浜嬩欢 | 鉁?DB/閰嶇疆 | 鉂?鏂颁唬鐮佺姝?|
| `voice_layer` | 鉁?鏁版嵁妯″瀷/浜嬩欢/Protocol | 鉁?閰嶇疆 | 鉂?鏂颁唬鐮佺姝?|
| `action_layer` | 鉁?鏁版嵁妯″瀷/浜嬩欢 | 鉁?閰嶇疆 | 鉂?鏂颁唬鐮佺姝?|
| `action_executor` | 鉁?鏁版嵁妯″瀷/浜嬩欢 | 鉁?閰嶇疆 | 鉂?鏂颁唬鐮佺姝?|
| `device_coordination` | 鉁?鏁版嵁妯″瀷/浜嬩欢 | 鉁?閰嶇疆 | 鉂?鏂颁唬鐮佺姝?|
| `gateway_adapter` | 鉁?鏁版嵁妯″瀷/浜嬩欢 | 鉁?閰嶇疆 | 鉂?鏂颁唬鐮佺姝?|
| `core_orchestrator` | 鉁?鏁版嵁妯″瀷/浜嬩欢 | 鉁?LLMClient/DB/閰嶇疆 | 鉂?鏂颁唬鐮佺姝?|

### 8.2 涓氬姟妯″潡涔嬮棿 (妯悜)

| from 鈫?/ to 鈫?| persona | memory | voice | action | action_exec | device | gateway | core_orch |
|---------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `persona_engine` | 鈥?| 鉂?| 鉂?| 鉂?| 鉂?| 鉂?| 鉂?| 鉂?|
| `memory_system` | 鉂?| 鈥?| 鉂?| 鉂?| 鉂?| 鉂?| 鉂?| 鉂?|
| `voice_layer` | 鉂?| 鉂?| 鈥?| 鉂?| 鉂?| 鉂?| 鉂?| 鉂?|
| `action_layer` | 鉂?| 鉂?| 鉂?| 鈥?| 鉂?| 鉂?| 鉂?| 鉂?|
| `action_executor` | 鉂?| 鉂?| 鉂?| 鉂?| 鈥?| 鉂?| 鉂?| 鉂?|
| `device_coordination` | 鉂?| 鉂?| 鉂?| 鉂?| 鉂?| 鈥?| 鉂?| 鉂?|
| `gateway_adapter` | 鉂?| 鉂?| 鉂?| 鉂?| 鉂?| 鉂?| 鈥?| 鉂?|
| `core_orchestrator` | 鉂?| 鉂?| 鉂?| 鉂?| 鉂?| 鉂?| 鉂?| 鈥?|

> **娉ㄦ剰**锛歚core_orchestrator` 閫氳繃 HTTP API 鎴栦簨浠舵€荤嚎璋冪敤鍚勪笟鍔℃ā鍧楋紝涓嶅緱鐩存帴 `import` 鍏跺唴閮ㄥ疄鐜般€傛墍鏈変笟鍔℃ā鍧楅棿妯悜 import 鍧囧睘杩濊銆?

### 8.3 鍏变韩灞備箣闂?

| from 鈫?/ to 鈫?| `shared_contracts` | `shared_runtime` | `shared` |
|---------------|:---:|:---:|:---:|
| `shared_contracts` | 鈥?| 鉂?闆朵緷璧栧師鍒?| 鉂?|
| `shared_runtime` | 鉁?瀹炵幇 Protocol | 鈥?| 鉂?涓嶅緱鍙嶅悜渚濊禆 shim |
| `shared` (搴熷純) | 鉁?re-export | 鉁?re-export | 鈥?|

### 8.4 Provider/鍘傚晢 SDK 璁块棶瑙勫垯

| 璁块棶鏂瑰紡 | 鍏佽 | 璇存槑 |
|---------|:---:|------|
| 涓氬姟妯″潡鐩存帴 `import openai / anthropic / litellm / dashscope` | 鉂?| 蹇呴』閫氳繃 `shared_runtime.llm_client` 鎴?`voice_layer/providers/` 灏佽 |
| `voice_layer/providers/` 鍐呴儴 import 鍘傚晢 SDK | 鉁?| 杩欐槸 provider 灏佽灞傜殑鑱岃矗 |
| `shared_runtime/llm_client.py` import `litellm` / `openai` | 鉁?| LLM 瀹㈡埛绔殑鑱岃矗 |

---

## 9. 鏋舵瀯鍩虹嚎 (baseline) 娌荤悊瑙勫垯

> **宸ュ叿**锛歚python tools/check_arch.py`锛圓ST 鎵弿锛?+ `.importlinter`锛坕mport-linter 濂戠害锛?

### 9.1 baseline 鏂囦欢 (`tools/arch_baseline.json`)

瀛樺偍褰撳墠宸插鏍哥‘璁ょ殑鏋舵瀯杩濊鍩虹嚎锛屽寘鍚瘡鏉¤繚瑙勭殑绮剧‘浣嶇疆锛堟枃浠?琛屽彿+鍐呭锛夈€?

### 9.2 baseline 鏇存柊瑙勫垯 鈿狅笍

| 鎿嶄綔 | 鍏佽锛?| 璇存槑 |
|------|:---:|------|
| `python tools/check_arch.py --check` | 鉁?CI 缁跨伅 | 瀵规瘮鍩虹嚎锛屾柊澧炶繚瑙勫垯閫€鍑虹爜 1 |
| `python tools/check_arch.py --baseline` | 鉂?绂佹闅忔剰鎵ц | 浼氳鐩栧熀绾匡紝鎺╁煁鏂板杩濊 |
| 瀹℃牳鍚庢墜鍔ㄦ洿鏂?baseline | 鉁?闇€ Review | 浠呭綋鏂板杩濊琚?Review 纭涓恒€屾湁鎰忎负涔嬩笖宸茶褰曘€嶅悗锛屾墠鏇存柊 baseline |
| Baseline 鏍煎紡鍗囩骇 | 鉁?闇€璁板綍 | 宸ュ叿鍗囩骇瀵艰嚧鏍煎紡鍙樺寲鏃讹紝閲嶆柊鐢熸垚骞惰褰曞彉鏇村師鍥?|

### 9.3 baseline 瀹℃牳娴佺▼

```
1. CI 鎵ц --check 绾㈢伅 鈫?鍙戠幇鏂板杩濊
2. 寮€鍙戣€呮鏌ヨ繚瑙勬竻鍗曪紝鍒ゆ柇鏄惁涓烘湁鎰忓紩鍏ワ細
   a. 鏄?Bug 鈫?淇浠ｇ爜锛屾秷闄よ繚瑙?
   b. 鏄妧鏈€猴紙宸茬煡涓斿凡璁板綍鍦ㄦ尝娆¤鍒掍腑锛夆啋 鎻愪氦 PR 鏃堕檮娉ㄥ師鍥?
3. 鏋舵瀯璐熻矗浜?Review 鍚庡喅瀹氾細
   a. 椹冲洖 鈫?寮€鍙戣€呬慨澶?
   b. 鎺ュ彈 鈫?杩愯 --baseline 鏇存柊鍩虹嚎锛孭R 涓寘鍚?baseline diff
4. 鏇存柊鍚?--check 蹇呴』鍐嶆閫氳繃
```

> **鍘熷垯**锛歜aseline 鍙兘鍙樺ソ锛堝噺灏戣繚瑙勶級鎴栨寔骞筹紙鐩稿悓杩濊琚‘璁わ級锛岀粷涓嶈兘璁╂柊杩濊"鎮勬倓"杩涘叆 baseline銆?

---

## 10. Upstream Reference Boundary

Historical upstream source trees (`hermes-agent/`, `airi-analysis/`) have been removed from this workspace. Module contracts in this file are authoritative for current companion-ai development; do not rely on upstream directories as live dependencies.
---

## 闄勫綍锛歝url 娴嬭瘯閫熸煡

```bash
# 1. 鍚姩鍗曚綋妯″紡
COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000

# 2. 娴嬭瘯鍋ュ悍
curl http://localhost:8000/health

# 3. 娴嬭瘯浜烘牸
curl -X POST http://localhost:8000/persona/get_profile \
  -H "Content-Type: application/json" -d '{"user_id":"u1"}'

# 4. 娴嬭瘯瀵硅瘽
curl -X POST http://localhost:8000/orchestrator/turn \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","user":{"user_id":"u1","display_name":"Test"},"user_message":"浣犲ソ","platform":"app"}'

# 5. 娴嬭瘯璁板繂瀛樺偍
curl -X POST http://localhost:8000/memory/store \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","category":"preference","content":"鍠滄鍜栧暋"}'

# 6. 娴嬭瘯璁板繂鍙洖
curl -X POST http://localhost:8000/memory/recall \
  -H "Content-Type: application/json" \
  -d '{"query":"鍠濅粈涔?,"user_id":"u1","top_k":5}'
```

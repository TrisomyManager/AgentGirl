# Companion AI 鈥?绯荤粺鏋舵瀯璁捐

> **瀹氫綅**锛氬唴閮ㄦ妧鏈師鍨?路 妯″潡鍖栭€氱敤闄即 AI 鑳藉姏搴撱€?
> **鐩爣**锛氭墍鏈夋ā鍧楅兘鍙互鐙珛鎷嗗紑鎺ュ叆浠绘剰绗笁鏂规暟瀛楃敓鍛介」鐩紙鍖呮嫭浣嗕笉闄愪簬"灏忔睈"锛夈€?
> **鏍稿績鍘熷垯**锛氬绾﹀厛琛屻€佸涓绘棤鍏炽€乣core_orchestrator` 涓?`frontend_app` 浠呮槸鍙傝€冮泦鎴?demo锛屼笉鏄繀閫夈€?
> **Live2D**锛氫粎浣滀负娓叉煋鍓嶇绀轰緥涔嬩竴锛涗换浣曞涓诲彲鎹?Unity / Unreal / Web Three.js / 妗岄潰 / 杞︽満 / MR銆?
> **鍘诲晢涓氬寲鍙ｅ緞**锛氭湰鏋舵瀯鏂囨。涓嶅啀涓庝换浣曞叿浣撳晢涓氶」鐩姤浠?/ 瀛愰泦 / 蹇呬氦浠樻竻鍗?鎸傞挬銆?

---

## 1. 璁捐鍘熷垯

- **妯″潡鐙珛**锛氭瘡涓ā鍧椾负鐙珛 Python 鍖咃紝鍙崟鐙繍琛屻€佸崟鐙祴璇曘€佸崟鐙儴缃层€?
- **濂戠害鍏堣**锛氭ā鍧楅棿閫氫俊閫氳繃 `shared/` 涓殑 Pydantic 妯″瀷鍜屼簨浠剁被鍨嬪畾涔夛紝涓嶇洿鎺ヤ緷璧栧鏂瑰疄鐜般€?
- **浜戝師鐢?*锛氬叏璧颁簯 API锛屾湰鍦颁粎杩愯缂栨帓鏈嶅姟鍜屾暟鎹眰銆?
- **浜嬩欢椹卞姩**锛氭牳蹇冩ā鍧楅棿閫氳繃 Redis Pub/Sub 寮傛瑙ｈ€︼紱鍚屾璋冪敤閫氳繃鍐呴儴 HTTP API銆?
- **Upstream reference boundary**: Historical Hermes/AIRI source trees have been removed from this workspace. `gateway_adapter/` is now a standalone companion-ai implementation; copy upstream ideas only through small, reviewed design notes.

## 2. 妯″潡鍒掑垎

> 琛ㄦ牸涓殑"绔彛"鏄弬鑰冮泦鎴?demo 鐨勯粯璁ょ鍙ｏ紱妯″潡鐙珛鎷嗗嚭鍚庣鍙ｇ敱瀹夸富鍐冲畾銆?
> 褰撳墠闃舵 P0 鐩爣鏄妸 `shared/` 鎷嗘垚 `shared_contracts/`锛堢函妯″瀷/浜嬩欢锛岄浂渚濊禆锛? `shared_runtime/`锛圠LM/閰嶇疆/鏃ュ織锛屽涓诲彲娉ㄥ叆锛夈€?

| 妯″潡 | 瑙掕壊 | 鑱岃矗 | 閮ㄧ讲褰㈡€?| 榛樿绔彛 |
|------|------|------|---------|------|
| `core_orchestrator` | 鍙傝€冮泦鎴?demo | LangGraph 鐘舵€佹満銆佹剰鍥捐瘑鍒€佽蹇?宸ュ叿/鍔ㄤ綔/璁惧璋冨害 | 涓绘湇鍔★紙鍙傝€冿級 | 8000 |
| `persona_engine` | 閫氱敤妯″潡锛堝彲鎷嗭級 | 缁撴瀯鍖栦汉鏍笺€佹儏鎰熺姸鎬佹満銆佸叧绯绘寚鏍囥€佸姩鎬佽姘旂敓鎴?| 寰湇鍔?| 8001 |
| `memory_system` | 閫氱敤妯″潡锛堝彲鎷嗭級 | 鐭湡缂撳瓨銆佸悜閲忔绱€佺煡璇嗗浘璋便€佷簲闃舵璁板繂娌夋穩 | 寰湇鍔?| 8002 |
| `voice_layer` | 閫氱敤妯″潡锛堝彲鎷嗭級 | ASR(鎯呮劅鎰熺煡)銆乀TS(鎯呮劅璇煶)銆佽闊虫祦绠＄悊 | 寰湇鍔?| 8003 |
| `action_executor` | 閫氱敤妯″潡锛堝彲鎷嗭級 | 鎻掍欢寮忓姩浣滄敞鍐屻€佽皟搴︿笌涓诲姩鎺ㄩ€佹€荤嚎 | 寰湇鍔?| 8004 |
| `action_layer` | 鈿狅笍 鍗犱綅 / 寰呬笌 `action_executor` 鍚堝苟鎴栧垹闄?| 2D 鐓х墖椹卞姩銆佸姩浣滆矾鐢便€佸攪褰?琛ㄦ儏鍚屾鍣?| 鈥?| 鈥?|
| `safety_guard` | 寰呭缓锛堟棫 OOC锛?| 杈圭晫妫€娴嬨€佽鍒欓泦澶栭儴鍙敞鍏?| 寰湇鍔?| TBD |
| `user_profile` | 寰呭缓锛堟棫 鈮?0缁寸敾鍍忥級 | 缁撴瀯鍖栫敤鎴风敾鍍忥紝schema 鍙厤缃?| 寰湇鍔?| TBD |
| `onboarding` | 寰呭缓锛堟棫 0-1 鐮村啺锛?| 鐮村啺娴佺▼寮曟搸 + 榛樿鑴氭湰 | 寰湇鍔?| TBD |
| `device_coordination` | 閫氱敤妯″潡锛堥噸鍚瘎浼帮級 | 璁惧娉ㄥ唽涓績銆丮QTT 娑堟伅鎬荤嚎銆佷换鍔″垎鍙?| 寰湇鍔?| 8005 |
| `gateway_adapter` | 閫氱敤妯″潡锛堝彲鎷嗭級 | 澶氬钩鍙版秷鎭敹鍙戙€佷細璇濆悓姝ャ€佸涓绘帴鍏ラ€傞厤 | 寰湇鍔?| 8006 |
| `frontend_app` | 鍙傝€?UI / 楠屾敹 demo | Vue 3 璋冭瘯鍙?+ Live2D 娓叉煋绀轰緥 | Web | 鈥?|
| `frontend_sdk` | 閫氱敤妯″潡锛堝彲鎷嗭級 | 鐙珛 App 閫氫俊 SDK锛圵ebSocket + REST锛?| 搴?SDK | 鈥?|
| `shared_contracts` | 鉁?濂戠害灞?| Pydantic 妯″瀷銆佷簨浠剁被鍨嬨€丳rotocol 鎺ュ彛锛堥浂杩愯鏃朵緷璧栵級 | 鍏变韩搴?| 鈥?|
| `shared_runtime` | 鉁?杩愯鏃跺眰 | LLMClient銆侀厤缃€佹棩蹇椼€佹暟鎹簱杩炴帴銆丩ite Mode锛堝涓诲彲鏁翠綋鏇挎崲锛?| 鍏变韩搴?| 鈥?|
| `shared` | 鈿狅笍 宸插簾寮?shim | 鍚戝悗鍏煎鐨勯噸鏂板鍑哄眰 + prompt_engine 娈嬬暀锛岃縼绉诲畬姣曞悗鍒犻櫎 | 鈥?| 鈥?|

### 2.1 shared 涓夊眰鏋舵瀯锛氳亴璐ｄ笌搴熷純璺緞

```
鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹?          涓氬姟妯″潡灞?                 鈹?
鈹? (persona_engine, memory_system ...)  鈹?
鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
       鈹? import       鈹? import
       鈻?              鈻?
鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹?shared_      鈹?鈹?shared_runtime/      鈹?
鈹?contracts/   鈹?鈹?(瀹夸富鍙暣浣撴浛鎹?       鈹?
鈹?闆朵緷璧栧绾﹀眰  鈹?鈹?LLMClient + 閰嶇疆+鏃ュ織 鈹?
鈹?             鈹?鈹?+ DB杩炴帴 + Lite Mode  鈹?
鈹?models.py    鈹?鈹?                     鈹?
鈹?events.py    鈹?鈹?                     鈹?
鈹?protocols.py 鈹?鈹?                     鈹?
鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
       鈻?              鈻?
       鈹?  re-export   鈹? re-export via shim
       鈹?              鈹?
鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹粹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹粹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹? shared/  鈿狅笍 DEPRECATED (shim 灞?     鈹?
鈹? 浠呭仛鍚戝悗鍏煎, 鎵€鏈夎皟鐢ㄦ柟杩佺Щ瀹屾瘯鍚庡垹闄? 鈹?
鈹? 渚嬪: prompt_engine.py 寰呰縼绉?        鈹?
鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
```

**鑱岃矗杈圭晫锛?*

| 灞?| 鍙互鍋氱殑浜嬫儏 | 绂佹鍋氱殑浜嬫儏 |
|----|-------------|-------------|
| `shared_contracts/` | 瀹氫箟绾暟鎹ā鍨?Pydantic)銆佷簨浠剁被鍨嬨€丳rotocol 鎶借薄鎺ュ彛 | import 浠讳綍涓氬姟妯″潡銆乮mport `shared_runtime`銆佹墽琛?I/O |
| `shared_runtime/` | 瀹炵幇 Protocol銆侀厤缃姞杞姐€佹暟鎹簱杩炴帴姹犮€丩LM 瀹㈡埛绔€丩ite Mode 鏇夸唬鍝?| import 浠讳綍涓氬姟妯″潡锛坧ersona_engine 绛夛級 |
| `shared/` **(宸插簾寮?** | 浠呬綔鍚戝悗鍏煎 shim锛岄噸鏂板鍑哄埌涓婅堪涓ゅ眰 | 鏂颁唬鐮佷笉寰楁柊澧?import `shared/` |

**搴熷純鏃堕棿琛細**

| 娉㈡ | 鐩爣 | 鐘舵€?|
|------|------|------|
| 娉㈡ 1 | 鎶藉嚭 `shared_contracts/`锛岃縼绉绘墍鏈夋ā鍨嬩笌浜嬩欢瀹氫箟 | 鉁?瀹屾垚 |
| 娉㈡ 2 | 鎶藉嚭 `shared_runtime/`锛孡LMClient + 閰嶇疆 + DB 灞傜嫭绔?| 鉁?瀹屾垚 |
| 娉㈡ 3 | 鎵€鏈変笟鍔℃ā鍧?import 浠?`shared.xxx` 鏀逛负 `shared_contracts` / `shared_runtime` | 杩涜涓?|
| 娉㈡ 4 | 杩佺Щ `shared/prompt_engine.py` 鈫?`shared_runtime/prompt_engine.py` | 寰呭紑濮?|
| 娉㈡ 5 | 鍒犻櫎 `shared/` 涓嬫墍鏈?shim 鏂囦欢锛屼粎淇濈暀鐩綍鍗犱綅 | 寰呭紑濮?|

> **鏂颁唬鐮佸噯鍒?*锛氫娇鐢?`from shared_contracts import X` 鑾峰彇鏁版嵁妯″瀷/浜嬩欢/鍗忚锛屼娇鐢?`from shared_runtime import X` 鑾峰彇杩愯鏃舵湇鍔°€傜姝㈡柊澧?`from shared import ...`銆?

## 3. 鏁版嵁娴?

```
User (App/Telegram/Discord)
  鈹?
  鈻?
gateway_adapter 鈹€鈹€WebSocket鈹€鈹€鈻?core_orchestrator
  鈹?                              鈹?
  鈹?   鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹尖攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
  鈹?   鈻?                         鈻?         鈻?
  鈹?persona_engine          memory_system   voice_layer
  鈹?   鈹?                         鈹?         鈹?
  鈹?   鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹?         鈹?
  鈹?                        鈻?               鈹?
  鈹?                   action_layer 鈼勨攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
  鈹?                        鈹?
  鈹?                        鈻?
  鈹?             device_coordination
  鈹?                        鈹?
  鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
```

## 4. 妯″潡闂村绾?

### 4.1 浜嬩欢鎬荤嚎 (Redis Pub/Sub)

| Channel | 鏂瑰悜 | 杞借嵎 |
|---------|------|------|
| `companion:turn:start` | gateway 鈫?core | `TurnStartEvent` |
| `companion:turn:end` | core 鈫?gateway | `TurnEndEvent` |
| `companion:memory:sync` | core 鈫?memory | `MemorySyncEvent` |
| `companion:action:generate` | core 鈫?action | `ActionGenerateEvent` |
| `companion:voice:synthesize` | core 鈫?voice | `VoiceSynthesizeEvent` |
| `companion:persona:update` | core 鈫?persona | `PersonaUpdateEvent` |
| `companion:device:command` | core 鈫?device | `DeviceCommandEvent` |

### 4.2 鍐呴儴 HTTP API

| 鏈嶅姟 | 绔偣 | 璇存槑 |
|------|------|------|
| persona_engine | `POST /persona/get_profile` | 鑾峰彇褰撳墠浜烘牸鐘舵€?|
| persona_engine | `POST /persona/update_emotion` | 鏇存柊鎯呮劅鐘舵€?|
| memory_system | `POST /memory/recall` | 璇箟妫€绱㈣蹇?|
| memory_system | `POST /memory/store` | 瀛樺偍瀵硅瘽鍥炲悎 |
| memory_system | `POST /memory/graph_query` | 鐭ヨ瘑鍥捐氨鏌ヨ |
| voice_layer | `POST /voice/transcribe` | 璇煶杞枃鏈?|
| voice_layer | `POST /voice/synthesize` | 鏂囨湰杞闊?|
| action_layer | `POST /action/generate` | 鐢熸垚鍔ㄤ綔搴忓垪 |
| device_coordination | `POST /device/list` | 鍒楀嚭鐢ㄦ埛璁惧 |
| device_coordination | `POST /device/send_command` | 鍚戣澶囧彂鎸囦护 |
| gateway_adapter | `POST /gateway/send` | 鍚戞寚瀹氬钩鍙板彂閫佹秷鎭?|
| gateway_adapter | `POST /gateway/broadcast` | 澶氬钩鍙板箍鎾?|

## 5. 鎶€鏈€夊瀷

| 灞傜骇 | 閫夊瀷 |
|------|------|
| 缂栨帓寮曟搸 | LangGraph + Pydantic AI |
| 鎰忓浘璇嗗埆 | LLM-as-intent-router (浜戠 API) |
| 鍚戦噺鏁版嵁搴?| pgvector (PostgreSQL) |
| 鐭ヨ瘑鍥捐氨 | Neo4j + LangChain GraphRAG |
| 娑堟伅鎬荤嚎 | Redis Pub/Sub + MQTT (璺ㄨ澶? |
| ASR | Whisper API / Groq / 闃块噷浜?|
| TTS | Fish Audio S2 / ChatTTS API |
| 2D 鍔ㄤ綔 | Live2D Cubism (PixiJS) 鈥?褰撳墠鍙傝€冨墠绔ず渚嬶紱wan2.2-animate-move 涓哄閫夋帰绱?|
| 缂撳瓨 | Redis |
| 閮ㄧ讲 | Docker Compose (MVP) |
| 鐩戞帶 | Prometheus + Grafana |

## 6. Upstream Reference Boundary

The old Hermes and AIRI source trees are no longer part of this repository. They were useful as early references, but the active architecture is now owned by `companion-ai/`. Do not import from, test, or ask Agents to inspect those upstream projects during normal work.
## 7. 鍗曡鑹叉繁搴﹀吇鎴愯璁¤鐐?

- **鍞竴浜烘牸鏂囦欢**锛歚persona_engine/data/soul.yaml` 鈥?涓嶅彲鍒囨崲锛岄殢鏃堕棿婕斿寲
- **鍏崇郴鎸囨爣**锛氫翰瀵嗗害(intimacy)銆佷俊浠诲害(trust)銆佹儏缁尝鍔?emotion_variance) 鈥?鎸佷箙鍖栧湪 memory_system
- **璁板繂娌夋穩**锛氫簲闃舵娴佹按绾垮皢瀵硅瘽鑷姩褰掓。涓恒€屼簨瀹炪€嶃€屾儏鎰熴€嶃€屼簨浠躲€嶃€屽亸濂姐€嶃€屽叧绯婚噷绋嬬銆?
- **鎴愰暱鎰?*锛歱ersona_engine 瀹氭湡锛堟瘡鏃?姣忓懆锛夌敓鎴愩€屽叧绯绘€荤粨銆嶆敞鍏ョ郴缁熸彁绀猴紝璁╀汉鏍兼劅鍙楀埌鍏崇郴娣卞寲

## 8. 2D 椹卞姩 MVP 鑼冨洿

- 杈撳叆锛歀LM 杈撳嚭鐨?`action_intent` + `emotion_tag`
- 璺敱锛氭牴鎹剰鍥鹃€夋嫨銆宨dle銆嶃€宼alk銆嶃€宭isten銆嶃€宺eact_happy銆嶃€宺eact_sad銆嶇瓑鍔ㄤ綔妯℃澘
- 鐢熸垚锛氳皟鐢ㄩ€氫箟涓囩浉 API锛岃緭鍏ュ弬鑰冨浘 + 鍔ㄤ綔鎻忚堪 鈫?杈撳嚭鍔ㄧ敾甯у簭鍒?
- 鍚屾锛歍TS 闊抽鏃堕暱 鈫?鍞囧舰鍏抽敭甯ф彃鍊?鈫?鍓嶇鎸夋椂闂磋酱鎾斁
- 鍓嶇锛欰pp 鍐?WebView 娓叉煋搴忓垪甯э紙鎴?Lottie锛?

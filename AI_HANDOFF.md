# AI 宸ョ▼浜ゆ帴鏂囨。

> 鍐欑粰涓嬩竴浣嶆帴鎵嬫湰宸ョ▼鐨?AI锛屾垨鑰呬笅涓€杞璇濋噷鐨勮嚜宸便€?
> 鏇存柊鏃ユ湡锛?026-05-07 (V2.3 浜烘牸杩炵画鎬ч棴鐜?

---

## 0. 椤圭洰瀹氫綅锛氬唴閮ㄦ妧鏈師鍨?路 妯″潡鍖栭€氱敤鑳藉姏搴?

**涓ゆ潯鏍稿績瀹氫綅**锛?

1. **褰撳墠宸ョ▼鏄唴閮ㄦ彁鍓嶅仛鐨勬妧鏈師鍨?Demo**锛屼笉缁戝畾浠讳綍鍏蜂綋鍟嗕笟椤圭洰锛屼笉涓庝换浣曞晢鍔℃姤浠锋寕閽┿€?
2. **鏈€缁堢洰鏍囨槸鎵€鏈夋ā鍧楅兘鍙互鐙珛鎷嗗紑鎺ュ叆浠绘剰绗笁鏂规暟瀛楃敓鍛介」鐩?*锛屽寘鎷絾涓嶉檺浜?灏忔睈"椤圭洰銆?

```
companion-ai锛堟湰浠撳簱锛? 閫氱敤闄即 AI 妯″潡搴?+ 涓€涓弬鑰冮泦鎴?demo
  鈹溾攢鈹€ 閫氱敤妯″潡锛堟瘡涓兘瑕佸彲鐙珛鎷嗗嚭鍘伙級
  鈹?  persona_engine / memory_system / voice_layer / action_executor /
  鈹?  safety_guard(寰呭缓) / user_profile(寰呭缓) / onboarding(寰呭缓) /
  鈹?  gateway_adapter / device_coordination
  鈹溾攢鈹€ 濂戠害灞?
  鈹?  shared_contracts(寰呭缓) 鈥?绾ā鍨?+ 浜嬩欢绫诲瀷锛岄浂渚濊禆
  鈹溾攢鈹€ 杩愯鏃跺眰锛堝涓诲彲娉ㄥ叆鎴栨浛鎹級
  鈹?  shared_runtime(寰呭缓) 鈥?LLMClient / 閰嶇疆 / 鏃ュ織
  鈹斺攢鈹€ 鍙傝€冮泦鎴?demo
      core_orchestrator(LangGraph 鍙傝€冪紪鎺? + frontend_app(Web + Live2D)
```

**鍏抽敭璁ょ煡**锛?

- **娌℃湁"蹇呬氦浠樻竻鍗?**锛氭ā鍧楃殑"瀹屾垚搴?浠?*瀵瑰濂戠害绋冲畾 + 鍙嫭绔嬭繍琛?+ 鍙嫭绔嬮泦鎴?*琛￠噺銆?
- **`core_orchestrator` 鏄弬鑰冨疄鐜帮紝涓嶆槸妯″潡鏈綋**锛氱涓夋柟鎺ュ叆涓嶅簲琚揩浣跨敤鎴戜滑鐨勭紪鎺掑櫒銆?
- **`frontend_app` + Live2D 鏄弬鑰?UI / 楠屾敹 demo**锛氬涓诲彲鎹?Unity / Unreal / Web Three.js / 妗岄潰 / 杞︽満 / MR銆?
- **Live2D 鍦ㄦ柊瀹氫綅涓嬪彧鏄?娓叉煋鍓嶇绀轰緥涔嬩竴"**锛屼笉鍐嶄互"灏忔睈 M1 闄嶇骇3 鍏滃簳鏂规"涓哄畾浣嶃€?
- **鍘诲晢涓氬寲鍙ｅ緞**锛氫互鍓嶆墍鏈?灏忔睈 楼XX涓?/ 鎶ヤ环琛?/ 瀛愰泦 / 鐏甸瓊宸ョ▼蹇呬氦浠?鎺緸鍏ㄩ儴搴熷純銆?

---

## 1. 鍏堢湅缁撹

褰撳墠鐪熸娲昏穬銆佸簲璇ヤ紭鍏堟帹杩涚殑宸ョ▼鏄?**[companion-ai](companion-ai/)** 鈥?閫氱敤闄即 AI 妯″潡搴擄紙鍐呴儴鎶€鏈師鍨嬶級銆?
历史上游源码（hermes-agent / airi-analysis）已移出仓库；当前开发入口只看 `companion-ai/`。

鐩墠椤圭洰鎵€澶勯樁娈碉細

- **Phase 3锛氫汉鏍艰繛缁€ч棴鐜?路 鍙皟璇曠姸鎬佹敹鏁?*
- **V2.3 鏈疆浜や粯**锛氫汉鏍艰繛缁€ч棴鐜紙emotion/relationship/profile/memory 姣忚疆鐪熷疄鏇存柊锛? 鏋舵瀯P0鏀跺彛锛堢‖缂栫爜37鈫?4锛岀洿杩濻DK 0锛? onboarding閾捐矾 + 璋冭瘯鍙?
- **demo 褰㈡€佸畬鏁?*锛欶astAPI 鍗曚綋 + LangGraph 缂栨帓 + 瀹炴椂璇煶 + 璁板繂鍙屽眰 + 琛屽姩鎵ц鍣?+ Live2D 鍓嶇
- **鏍稿績闂幆宸叉墦閫?*锛?
  1. 鐢ㄦ埛杈撳叆 鈫?浜烘牸/鎯呯华/鍏崇郴/璁板繂/鐢诲儚鍙備笌鍐崇瓥 鈫?鍥炲/鍔ㄤ綔/璇煶 鈫?鐘舵€佽鏇存柊 鈫?涓嬩竴杞璇濈湡瀹炲彈褰卞搷
  2. onboarding 鈫?user_profile.role_id 鈫?persona 鍔犺浇 鈫?椋庢牸鍖归厤
  3. 璋冭瘯鍙?/debug/state 鍙瘖鏂畬鏁翠汉鏍肩姸鎬侊紙system_prompt + emotion + relationship + working_memory + user_profile锛?

- `companion-ai/main.py`
  - 鍗曚綋鍏ュ彛鍙寕杞藉叏閮?router锛岄€傚悎浣滀负鏈湴寮€鍙戦粯璁ゅ叆鍙ｃ€?
- `companion-ai/frontend_app/`
  - 宸叉湁鑱婂ぉ鐣岄潰銆佽缃娊灞夈€佽蹇嗗簱銆侀」鐩姸鎬侀潰鏉裤€佸疄鏃惰闊抽€氳瘽闈㈡澘銆?
- `companion-ai/voice_layer/`
  - 宸叉墦閫氭祻瑙堝櫒绔?VAD銆丄udioWorklet PCM 褰曢煶銆乄ebSocket 鍙屽悜娴併€佽竟鍚堟垚杈规挱鏀俱€乥arge-in 鎵撴柇銆?
- `companion-ai/shared/`
  - 宸叉湁缁熶竴 LLM 閰嶇疆銆佽繍琛屾椂閰嶇疆鎸佷箙鍖栥€佸叡浜ā鍨嬩笌鏃ュ織鍩虹璁炬柦銆?
  - `LLMClient.generate_stream()` 宸插氨浣嶏紝OpenAI / Anthropic 鍙?provider 閮芥敮鎸?token 绾ф祦寮忋€?
- `companion-ai/core_orchestrator/`
  - LangGraph 鐘舵€佹満 + `POST /orchestrator/turn/stream` SSE 绔偣宸叉墦閫氾紝涓昏亰澶╁拰瀹炴椂璇煶鐨?娴佸紡璇箟"宸茬粡缁熶竴銆?
- `companion-ai/core_orchestrator/project_status.py`
  - 鐩墠鏄€滈」鐩綋鍓嶅疄鐜扮姸鎬佲€濈殑鏈€鍑嗗叆鍙ｄ箣涓€锛屽墠绔姸鎬侀〉鐩存帴娑堣垂瀹冦€?

### 杩樻病鐪熸鏀跺彛鐨勯儴鍒?

- `action_executor` 涓诲姩鎬фā鍧?
  - 宸叉湁 5 涓唴缃?handler 鍜屾彁閱?SSE 鎺ㄩ€侊紝澶╂皵/鏃ュ巻鏄?stub锛涘惊鐜?cron椋庢牸璋冨害灏氭湭瀹炵幇銆?
  - 涓诲姩鎬у叧鎬€锛堝埌鐐规彁閱掋€侀暱鏈熸湭浜掑姩闂€欍€佽蹇嗚Е鍙戠邯蹇垫棩锛夌瓑鐘舵€侀棴鐜ǔ瀹氬悗鍐嶆墿灞曘€?
- `action_layer` / `device_coordination`
  - action_layer 宸?deprecated shim 鈫?action_executor.action2d锛沝evice_coordination 浠嶆槸鍗犱綅銆?
- working memory 鎽樿璐ㄩ噺
  - dominant_topic / 鐢ㄦ埛鎽樿鐩墠鏄?bag-of-words 鍚彂寮忥紝鍙浛鎹负 LLM 鎽樿鍣ㄣ€?
- Lite Mode 鐘舵€佹寔涔呭寲
  - emotion_state 浠呭瓨鍐呭瓨锛堟棤 Redis锛夛紝鍏崇郴鎸囨爣璧?SQLite锛涢噸鍚涪澶辨儏缁姸鎬併€?

---

## 3. 鐜板湪浠ｇ爜閲屸€滅湡瀹炲瓨鍦ㄢ€濈殑鑳藉姏

### companion-ai

- 杩愯妯″紡
  - 鍗曚綋妯″紡锛歚uvicorn main:app --reload --port 8000`
  - Lite Mode锛歚COMPANION_LITE_MODE=true`锛屼娇鐢?SQLite + 鍐呭瓨鏇夸唬锛岄€傚悎鏃?Docker 鐜
- 鍓嶇鑳藉姏
  - 鏂囨湰鑱婂ぉ
  - 璇煶杈撳叆
  - 瀹炴椂璇煶閫氳瘽
  - Live2D 灞曠ず
  - LLM / Voice Provider 杩愯鏃跺垏鎹?
  - 椤圭洰鐘舵€佸彲瑙嗗寲
- 杩愯鏃堕厤缃?
  - `companion_llm_config.json`
  - `companion_voice_config.json`
- 鐘舵€佹帴鍙?
  - `/health`
  - `/orchestrator/project_status`
  - `/orchestrator/settings/llm`
  - `/orchestrator/settings/voice`

### 历史上游参考

历史上游源码（hermes-agent / airi-analysis）已移出仓库；当前开发入口只看 `companion-ai/`。
- 如果未来需要重新参考上游，只能在仓库外调研，并把结论沉淀为小范围设计说明或经过评审的代码。
---

## 4. 鍏堣鍝簺鏂囦欢

濡傛灉瑕佸湪鏈€鐭椂闂村唴鎭㈠涓婁笅鏂囷紝寤鸿鎸夎繖涓『搴忥細

1. [companion-ai/main.py](D:/DeskTop/AgentGril/companion-ai/main.py)
2. [companion-ai/core_orchestrator/project_status.py](D:/DeskTop/AgentGril/companion-ai/core_orchestrator/project_status.py)
3. [companion-ai/core_orchestrator/api.py](D:/DeskTop/AgentGril/companion-ai/core_orchestrator/api.py)
4. [companion-ai/core_orchestrator/state_machine.py](D:/DeskTop/AgentGril/companion-ai/core_orchestrator/state_machine.py)
5. [companion-ai/frontend_app/src/App.vue](D:/DeskTop/AgentGril/companion-ai/frontend_app/src/App.vue)
6. [companion-ai/frontend_app/src/components/ProjectStatusPanel.vue](D:/DeskTop/AgentGril/companion-ai/frontend_app/src/components/ProjectStatusPanel.vue)
7. [companion-ai/voice_layer/realtime.py](D:/DeskTop/AgentGril/companion-ai/voice_layer/realtime.py)
8. [companion-ai/shared/llm_client.py](D:/DeskTop/AgentGril/companion-ai/shared/llm_client.py)

---

## 5. 鏈湴楠岃瘉寤鸿

### 鏈€灏忛獙璇佽矾寰?

鍦?`companion-ai/` 鐩綍鎵ц锛?

```powershell
python -m pytest -q
uvicorn main:app --reload --port 8000
```

鍓嶇鍗曠嫭楠岃瘉锛?

```powershell
cd frontend_app
npm run build
```

### 2026-05-05 鐨勫疄闄呴獙璇佺粨鏋?

- `python -m pytest -q`
  - **125 passed / 0 failed**锛坰treaming 4 + working memory 9 + action_executor 15锛?
- 淇瑕佺偣
  - `pyproject.toml` 鐜板湪鏄惧紡澹版槑 `numpy` 渚濊禆锛宍voice_layer` 涓嶅啀鍥?
    `ModuleNotFoundError: numpy` 鍦ㄥ共鍑€ venv 涓暣缁?collect 澶辫触銆?
  - `shared/tests/test_prompt_engine.py` 鐨勮嫳鏂囨柇瑷€宸蹭笌
    `shared/prompt_engine.py` 鐨勪腑鏂?prompt 瀵归綈锛? 涓暱鏈熺孩娴嬪凡杞豢銆?
  - `memory_system/tests/test_memory.py` 涔嬪墠鐨?SQLite 鍚戦噺缁戝畾闂鍦?
    涓婁竴杞?`memory_system/db.py` / `vector_store.py` 璋冩暣鍚庡凡鎭㈠缁胯壊銆?
- 浠嶉渶娉ㄦ剰锛歚voice_layer` 鐨勭湡瀹為煶棰戦泦鎴愶紙`ffmpeg`銆乣faster-whisper`銆乣piper-tts`
  妯″瀷涓嬭浇锛夊湪 CI / 骞插噣鏈哄櫒涓婁粛鏄綔鍦ㄩ樆濉炵偣锛涘綋鍓嶆祴璇曢€氳繃 monkeypatch
  閬垮紑浜嗚繖鏉＄‖渚濊禆璺緞銆?

---

## 6. 褰撳墠鐘舵€佷笌涓嬩竴姝ユ帹鑽愬姩浣?

**褰撳墠 V2.3 宸插畬鎴愶細**

**P0 鏋舵瀯鏀跺彛** 鉁?
1. 鍗曡鑹茬‖缂栫爜 37鈫?4锛坰tate_machine / handlers / onboarding / prompt_engine / realtime 鍏ㄩ儴鍘?灏忔殩" 鈫?DEFAULT_PERSONA_NAME "闄即鑰?锛?
2. voice_layer DashScope SDK 杩佺Щ鑷?providers/dashscope.py 灏佽灞?鈫?check_arch 鐩磋繛SDK=0
3. check_arch.py 澧炲姞 providers/ 鐩綍 SDK 妫€鏌ヨ眮鍏嶈鍒?

**P1 浜烘牸杩炵画鎬ч棴鐜?* 
4. `persona_engine/runtime.py` 鈥?杩涚▼绾?EmotionEngine + RelationshipTracker 鍗曚緥
5. `_recall_memory_monolithic` 鈥?浠?emotion_engine.get_current_emotion() + relationship_tracker.get_metrics() 璇绘寔涔呭寲鐘舵€侊紙涓嶅啀姣忚疆閲嶇疆锛?
6. `node_sync_memory` 鈥?鍐欏洖 emotion_state锛坱ransition_from_user_message锛? relationship_metrics锛坮ecord_interaction锛? user_profile 鏇存柊锛堝悕瀛?鍋忓ソ鍙戠幇锛?

**P2 onboarding 閾捐矾**
7. `/orchestrator/onboarding/start | answer | status` 绔偣
8. OnboardingFlow 鍔ㄦ€佽 persona_store.list_available_personas()
9. apply_to_profile 鈫?SQLiteUserProfileStore锛沖recall_memory_monolithic 璇?role_id

**P3 璋冭瘯鍙?*
10. `/orchestrator/debug/state` 鈥?瀹屾暣浜烘牸鐘舵€佸揩鐓?
11. `/orchestrator/personas` 鈥?鍙敤瑙掕壊鍒楄〃
12. `/orchestrator/debug/prompt_preview` 澧炲姞 intent 瀛楁

**涓嬩竴姝ユ帹鑽愶細**
- **V2.4 涓诲姩鎬фā鍧?*锛氬湪鐘舵€侀棴鐜ǔ瀹氬悗鎵╁睍涓诲姩鍏虫€€锛堝埌鐐规彁閱掋€侀暱鏈熸湭浜掑姩闂€欍€佽蹇嗚Е鍙戠邯蹇垫棩锛?
- **V2.4 鐗╃悊鍒犻櫎 deprecated shim**锛歴hared/ 鍜?action_layer/ 鐨?re-export 鍙墿鐞嗗垹闄?
- **V2.4 voice_layer 绾敞鍏ュ紡**锛欰SRClient 浠庡瓧绗︿覆 provider 鍒嗗彂鏀逛负 Protocol 娉ㄥ叆

---

## 7. 瀹规槗韪╁潙鐨勭偣

- 不要从已移除的上游工程启动或检索；当前开发入口是 `companion-ai/`。
- `companion-ai` 鎵嶆槸褰撳墠鏈満鏈€椤烘墜鐨勫紑鍙戝叆鍙ｃ€?
- 鏍圭洰褰曟棫鏂囨。閲屽緢澶氬唴瀹规槸鈥滈暱鏈熺洰鏍団€濓紝涓嶆槸鈥滀粖澶╁凡缁忓疄鐜扳€濄€?
- 椤甸潰鐘舵€佸睍绀轰互 `core_orchestrator/project_status.py` 涓哄噯锛涘鏋滀唬鐮佸疄鐜板彉鍖栦簡锛屼紭鍏堝悓姝ヨ繖閲岋紝鍐嶅悓姝ユ枃妗ｃ€?
- 褰撳墠浠撳簱鏄剰宸ヤ綔鍖猴細
  - `.gitignore` 宸叉湁鐢ㄦ埛鏀瑰姩
  - `companion-ai/.env.lite` 鏄湭璺熻釜鏂囦欢
  - 涓嶈璇竻鐞?

---

## 8. 涓€鍙ヨ瘽浜ゆ帴

companion-ai 鏄?*鍐呴儴鎶€鏈師鍨?*锛孷2.3 宸叉墦閫氫汉鏍艰繛缁€ч棴鐜細姣忚疆瀵硅瘽鐪熷疄鏇存柊骞跺奖鍝嶄笅涓€杞殑 emotion_state / relationship_metrics / user_profile / working_memory銆傛灦鏋?P0 鏀跺彛瀹屾垚锛堢‖缂栫爜 37鈫?4锛岀洿杩?SDK 0锛夈€俹nboarding 鈫?user_profile 鈫?persona role_id 閾捐矾鎵撻€氥€傝皟璇曞彴 `/debug/state` 鍙瘖鏂畬鏁翠汉鏍肩姸鎬併€備笅涓€姝ワ細鐘舵€侀棴鐜ǔ瀹氬悗鎵╁睍涓诲姩鎬фā鍧楋紙鍒扮偣鎻愰啋/闀挎湡鏈簰鍔ㄩ棶鍊?璁板繂瑙﹀彂绾康鏃ュ叧鎬€锛夈€備换浣曞涓伙紙Unity / Unreal / Web / 妗岄潰 / 绗笁鏂瑰钩鍙帮紝鍚皬姹愶級閮芥槸鍚堟硶闆嗘垚鏂癸紝鏈粨搴撲笉鏇夸换浣曞涓诲仛宸ョ▼鍖栦氦浠樸€?

---

## 9. 鏈疆寰呯画宸ヤ綔锛?026-05-05 涓浜ゆ帴锛?

> 杩欎竴杞?token 鐢ㄥ敖鍓嶆鍦ㄥ仛"鍔ㄤ綔鎵ц鍣ㄥ垵濮嬮棴鐜?銆傚凡缁?push 鍒?`cursor/repo-issue-fixes-29a4` 鐨勪唬鐮佸浜?娴嬭瘯鍏ㄧ豢锛屼絾杩滅 lite/CF 璺緞涓嬬鍒扮 demo 娌″畬鍏ㄨ蛋閫?鐨勭姸鎬併€備笅涓€杞帴鎵嬭鎸夎繖閲岀殑娓呭崟鏀跺彛銆?

### 宸插畬鎴愶紙宸插悎鍏ュ垎鏀級

- `action_executor/` 鏂版ā鍧楋細
  - `registry.py` 鈥斺€?`ActionRegistry` + `ActionResult` + `register_action` 瑁呴グ鍣ㄣ€?
  - `handlers.py` 鈥斺€?5 涓唴缃?handler锛歚get_time` / `get_weather`(stub) / `set_reminder` / `list_reminders` / `cancel_reminder`銆俙set_reminder` 浼氳В鏋?"3 鍒嗛挓鍚?銆?in 5 minutes" 绛夎嚜鐒惰瑷€寤惰繜銆?
  - `reminders.py` 鈥斺€?`ReminderORM`锛圫QLAlchemy 琛級+ `RemindersStore`锛坅dd / list / due / mark_fired / cancel锛? `ReminderScheduler`锛堥粯璁?1s 杞锛涚敤 `_tick_once` 鍦ㄦ祴璇曚腑鍙墜鍔ㄩ┍鍔級銆?
  - `push_bus.py` 鈥斺€?杩涚▼鍐?pub/sub `ProactivePushBus`锛屾瘡涓?subscriber 涓€鏉?`asyncio.Queue`銆?
  - `api.py` 鈥斺€?`/actions/list` / `/actions/dispatch` / `/actions/reminders/{user_id}` (GET / POST) / `/actions/reminders/{id}` (DELETE) / `/actions/push` (SSE)銆?
  - `main.py` 鈥斺€?寰湇鍔℃ā寮?lifespan锛堝惎鍔?/ 鍋滄 scheduler锛夛紝鍚屾椂琚?monolithic `companion-ai/main.py` 澶嶇敤銆?
- `core_orchestrator/state_machine.py`锛?
  - 鏂板 `_try_action_executor(tc, intent)`锛氬綋 intent 鏄?`TOOL_USE` 鏃舵寜鍏抽敭瀛楀尮閰?handler 骞?dispatch銆?
  - 鍦?`node_generate_response`锛堥潪娴佸紡锛夊拰 `stream_assistant_response`锛堟祦寮忥級涓ゆ潯璺緞閲岄兘鎺ュ叆浜嗚繖涓垎鏀細handler 鍛戒腑鍚庤烦杩?LLM锛岀洿鎺ユ覆鏌?handler 杩斿洖鐨勬枃鏈€傛祦寮忓垎鏀敤 `chunk_text_stream` 鍒囩墖 SSE銆?
- `core_orchestrator/intent_router.py` 鐨?`_TOOL_KEYWORDS` 鍔犱簡銆屾彁閱掓垜 / 甯垜鎻愰啋 / 寰呭姙鎻愰啋 / 鍙栨秷鎻愰啋 / remind me / set reminder銆嶇瓑銆?
- `frontend_app/`锛?
  - `useApi.ts` 鏂板 `listReminders` / `cancelReminder` / `listActions`銆?
  - 鏂板缓 `composables/useProactivePush.ts`锛氱敤 `fetch + ReadableStream + TextDecoder` 瑙ｆ瀽 `/actions/push` SSE锛岃嚜鍔ㄦ柇绾块噸杩烇紝瀵瑰鏆撮湶 `lastReminder` ref銆?
  - 鏂板缓 `components/ReminderToast.vue`锛氱矇鑹?鈴?娴獥锛?-4 琛屽唴鏄剧ず鎻愰啋鏂囧瓧 + 鐐?`脳` 鍏抽棴銆?
  - `App.vue` 瑁呰浇 `useProactivePush()` + `<ReminderToast :reminder="lastReminder" @dismiss="...">`銆?
- `companion-ai/main.py`锛氭妸 `action_executor` 鍔犺繘浜?`_ENABLED_MODULES`锛屾寕杞?router锛屾寜鍙嶅悜椤哄簭鍗歌浇 lifespan銆?
- `pyproject.toml.tool.setuptools.packages.find` 涔熷姞涓?`action_executor*`銆?
- `core_orchestrator/project_status.py`锛?
  - `action_executor` 妯″潡鍗＄墖浠?PLANNED 10% 鍗囧埌 IN_PROGRESS 55%锛屽姞浜?7 鏉?馃啎 key_features銆?
  - 椤跺眰 `recent_highlights` / `next_focus` / `risks` / `test_snapshot` / `release_notes.items` 鍏ㄩ儴鍚屾銆?
  - `architecture_layers["鑳藉姏灞?]` 鎶?`action_executor` 鍜?`action_layer` 閮藉垪涓娿€?
  - `overall_progress=92`銆乣test_snapshot.passed=125`銆?
- `action_executor/tests/test_action_executor.py`锛?5 涓敤渚嬶紝**鍏ㄧ豢**銆傝鐩?registry / 鍐呯疆 handler / reminders store / scheduler 涓?push bus / NL 鏂囨湰瑙ｆ瀽銆?
- 鏂囨。锛歚AI_HANDOFF.md` / `PROJECT_PLAN.md` 鍚屾鍩虹嚎 110 鈫?125 / 0銆?
- `pytest -q` 鈥斺€?**125 passed, 0 failed**銆?
- 鏈湴鐩磋繛鍚庣鐨?curl 绔埌绔疄娴嬶細銆? 绉掑悗鎻愰啋鎴戝枬姘淬€嶁啋 intent_router 璺敱鍒?`tool_use` 鈫?`_try_action_executor` 閫変腑 `set_reminder` 鈫?鎸佷箙鍖栧埌 `reminders` 琛?鈫?鍚庡彴 scheduler 瑙﹀彂 鈫?`ProactivePushBus.publish` 鈫?`/actions/push` SSE 涓婄湅鍒?`event: reminder_fired`銆傛祦绋嬪畬鏁淬€?

### 杩樻病鏀跺彛鐨勪袱浠朵簨

#### 9.1 `/actions/push` 鍦?Cloudflare 闅ч亾涓嬮瀛楄妭寤惰繜澶暱

**鐥囩姸**锛氱洿杩炴湰鏈?`127.0.0.1:8000/actions/push` 涓€鍒囨甯革紱鍚屾牱鐨勮姹傜粡 Cloudflare Quick Tunnel 杞彂鍚庯紝**棣栧瓧鑺傝繜杩熶笉鍒?*锛堝湪娴忚鍣?DevTools 鎺㈤拡鑴氭湰涓瓑浜?15s 涔熸敹涓嶅埌 `event: hello`锛夈€傜洿鎺ョ粨鏋滐細娴忚鍣?`useProactivePush` 姘歌繙鎷夸笉鍒?`reminder_fired` 浜嬩欢锛屽墠绔?`ReminderToast` 涓嶆樉绀恒€?

**宸茬粡鍋氫簡鐨勪慨琛?*锛氬湪 `action_executor/api.py::push_stream` 閲岋細
- 澶村厛鍙戜竴涓?~2KB 鐨?SSE comment padding锛坄":" + " "*2048 + "\n"`锛夛紝寮哄埗 cloudflared 绔嬪埢 flush 绗竴娈点€?
- 涓诲惊鐜敤 `asyncio.wait_for` 鍖?subscriber 鐨?`__anext__()`锛屾病浜嬩欢鏃舵瘡 2s 鍙戜竴甯?`event: ping\ndata: {}\n\n` 蹇冭烦锛岄伩鍏?CF / nginx 鍦ㄩ暱鏃堕棿娌℃暟鎹椂鎸ゅ帇缂撳啿銆?
- 鍝嶅簲澶村凡缁忔湁 `Cache-Control: no-cache, no-transform`銆乣Connection: keep-alive`銆乣X-Accel-Buffering: no`銆?

**杩樻病鍋氬畬**锛氳繙绔?VM 涓婇噸鍚?backend 涔嬪悗锛?*娌℃潵寰楀強鍋氬畬鏁寸鍒扮瀹炴祴**灏辫 token 鐢ㄥ畬浜嗐€俵ite-mode 楠岃瘉锛堣 9.2锛変篃鎾炲埌涓嬮潰鐨勯棶棰橈紝鎵€浠ョ幇鍦?push_stream 鏀瑰畬涔嬪悗鏄?*鍙湪娴嬭瘯閲岃闈欐€佽皟鐢ㄨ繃锛屾病鍦ㄧ湡瀹?cloudflared 璺緞涓婅蛋閫?*銆?

涓嬩竴姝ュ缓璁細
1. 鐢?lite-mode 閲嶅惎 backend锛堣 9.2锛夈€?
2. `curl -sN https://<cf-tunnel>/actions/push` 鐪嬮瀛楄妭鏄惁 < 2s 鍒拌揪銆?
3. 鑻ュ埌杈?鈫?鐢ㄦ祻瑙堝櫒鎺㈤拡鑴氭湰锛堝湪鎴戠殑瀵硅瘽鍘嗗彶閲屾湁瀹屾暣鐗堟湰锛夎闃?`/actions/push` 鍚屾椂閫氳繃 `/orchestrator/turn` 瑙﹀彂 `8 绉掑悗鎻愰啋鎴戝枬姘碻锛岀湅 `event: reminder_fired` 鏄惁鍒般€?
4. 鑻ヤ粛涓嶅埌 鈫?缁х画鎶?padding 鍔犲埌 4KB / 鎶?ping 闂撮殧闄嶅埌 1s锛涘啀涓嶈灏辫€冭檻鐢?polling fallback (`GET /actions/push/poll?since=...`) 鏇挎崲 SSE 閭ｆ潯璺緞銆?

#### 9.2 lite-mode 鍏煎锛歚reminder_scheduler.tick_failed [Errno 111]`

**鐥囩姸**锛氬湪浜戠 VM 涓?`pkill uvicorn` 鍚庣敤 tmux 閲嶅惎鏃讹紝monolithic 妯″紡 `lite_mode=False` 鏄粯璁わ紝鎵€浠?`reminders.RemindersStore.list_due()` 璇曞浘杩?PostgreSQL 鈫?Connection refused 鈫?scheduler 姣忕 spam warning銆?

**宸茬粡鍋氫簡鐨勪慨琛?*锛氬綋鍓嶇殑 `companion-ai/main.py` 宸茬粡鍦?lifespan 閲岃皟 `init_database_schema()`锛宻hared engine 鏄寜 `settings.lite_mode` 閫?SQLite 鎴?Postgres 鐨勶紝鎵€浠?*鍙鍚姩鏃?export `COMPANION_LITE_MODE=true`锛宻cheduler 灏变細璧?SQLite锛屼笉浼氬啀鏈?Connection refused**銆?

**杩樻病鍋氬畬**锛氭垜鍦ㄦ渶鍚庝袱杞?restart 鏃舵墜鍔?export 浜?`COMPANION_LITE_MODE=true` 浣?tmux send-keys 浼间箮娌℃妸 env 鐪熸浼犺繘 uvicorn 杩涚▼锛屽鑷磋繕鏄?lite_mode=False銆備笅涓€杞帴鎵嬪姟蹇呬竴娆℃€х‘璁わ細

```bash
tmux -f /exec-daemon/tmux.portal.conf kill-session -t companion-backend 2>/dev/null
tmux -f /exec-daemon/tmux.portal.conf new-session -d -s companion-backend -c /workspace/companion-ai -- bash -l
tmux -f /exec-daemon/tmux.portal.conf send-keys -t companion-backend:0.0 \
  "export COMPANION_LITE_MODE=true COMPANION_MONOLITHIC=true COMPANION_ENABLE_VOICE=false COMPANION_ENABLE_ACTION_2D=false COMPANION_ENABLE_DEVICE_COORDINATION=false COMPANION_ENABLE_MEMORY_PIPELINE=false" C-m
tmux -f /exec-daemon/tmux.portal.conf send-keys -t companion-backend:0.0 \
  "/workspace/companion-ai/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 2>&1 | tee /tmp/backend.log" C-m
sleep 6
grep "lite_mode=" /tmp/backend.log    # 蹇呴』鐪嬪埌 lite_mode=True
```

**宸茶ˉ榻愮殑鏂囨。/绾﹀畾锛堟湰杞級**锛歚companion-ai/.env.example` 鐜板凡鍖呭惈涓婅堪 Lite Mode 鐩稿叧鍙橀噺璇存槑锛涙妸璇ユ枃浠跺鍒朵负鍚岀洰褰曚笅鐨?`.env`锛堜粨搴撳凡 gitignore锛夊嵆鍙 pydantic-settings 鍦ㄤ换鎰忓惎鍔ㄦ柟寮忎笅 pick up锛屾棤闇€渚濊禆 tmux 閲?fragile 鐨?`export` 琛屻€傛洿鐪佷簨鐨勪竴閿惎鍔ㄤ粛鎺ㄨ崘 `python scripts/start_lite_server.py`锛堝湪 import `main` 涔嬪墠寮哄埗 `COMPANION_LITE_MODE=true`锛夈€?

### Cloud preview URL锛堝彲鑳藉凡澶辨晥锛?

- 鍓嶇锛?https://condos-behind-weekend-synthesis.trycloudflare.com>
- 鍚庣锛?https://ambient-rent-immigrants-face.trycloudflare.com>

杩欎袱涓?URL 鏄笂涓€杞窇鐨?`cloudflared` quick tunnel锛?*浼氶殢 cloud agent VM 鍏虫満鑰屾秷澶?*銆備笅涓€杞帴鎵嬪鏋滆澶嶇敤棰勮锛屽缓璁細

1. `/opt/tools/cloudflared` 宸茶濂斤紱`/opt/tools/node` 鏄?Node 20銆?
2. 閲嶅惎鍚庣敤涓婇潰 9.2 鐨勫懡浠ゆ媺璧峰悗绔紝鍐?`tmux new-session -d -s cf-backend "cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000 2>&1 | tee /tmp/cf-backend.log"`锛屼粠鏃ュ織閲屾姄 `https://*.trycloudflare.com` URL銆?
3. 鍓嶇绫讳技锛歚tmux new-session -d -s companion-frontend -c /workspace/companion-ai/frontend_app -- bash -l`锛屽彂 `export VITE_API_BASE_URL=<鍒氭墠鐨勫悗绔?URL>` + `npm run dev -- --host 127.0.0.1 --port 5173`锛屽啀璧蜂竴鏉?cloudflared 杞?5173銆?
4. **Vite 5 鐨?`server.allowedHosts` 蹇呴』璁?*锛氭湰鍦版垜鎶?`vite.config.ts` 鏀规垚 `allowedHosts: true` 鐢ㄤ簬浜戠棰勮锛屼絾杩欎釜鏀瑰姩**娌℃湁鎻愪氦**锛堥伩鍏嶆薄鏌撴湰鍦拌矾寰勶級銆備笅涓€杞帴鎵嬪鏋滆鍐嶆璧?cloudflared锛岃寰楁墜鍔ㄥ湪 VM 涓婂姞涓婂悓鏍蜂竴琛屻€?

### 浠撳簱褰撳墠鐘舵€?

- 鍒嗘敮锛歚cursor/repo-issue-fixes-29a4`锛屽凡 push 鍒?`origin`銆?
- PR锛歔#2](https://github.com/TrisomyManager/AgentGirl/pull/2)銆?
- 绱 commit锛氳 `git log master..HEAD --oneline`銆?
- 宸ヤ綔鏍戞湁涓€浜?*鏈彁浜?*鐨勬湰鍦扮姸鎬侊紙璇﹁ PR 鎻忚堪搴曢儴銆屽凡鐭ラ檺鍒躲€嶏級锛?
  - `companion-ai/frontend_app/vite.config.ts` 鐨?`allowedHosts: true`锛堜簯绔瑙堜笓鐢級銆?
  - `companion-ai/frontend_app/package-lock.json`锛坣pm install 鍓骇鍝侊級銆?
  - 杩滅 `companion_lite.db` 宸茬粡瀛樹簡鍑犳潯 fired/cancelled 娴嬭瘯 reminder锛堢敤鎴峰簲褰?ignore锛屼笅娆℃湰鍦板惎鍔ㄤ細鑷繁鐢熸垚鏂扮殑锛夈€?

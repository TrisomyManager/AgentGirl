# Core Orchestrator

参考宿主的对话编排：接收消息、判断意图、取记忆/角色状态、生成文字与语音/动作、保存完成轮次。业务模块通过宿主组合；不要从业务模块反向导入这里。

## V2.9 · 自然发言与路由

- 自然发言在 `persona_engine.reply_policy` 中独立计算，由宿主传入最近对话、语音/图片等上下文。默认正常回复，读取设置失败也正常回复；已完成的安静轮次继续保存原文、活动和关系。
- 普通响应及 SSE `done` 的 `reply_suppressed` 表示成功的安静处理；客户端应显示接收状态，避免空白助手消息和无效语音播放。设置 API 为 `/persona/conversation_preferences/{user_id}`。
- `routing_rules.py` 仅把当前请求作为操作证据。历史关键词不触发操作；否定、功能说明、描述和设备命令分开处理。明确停止提醒会进入取消流程，不能被“提醒我”关键词误送到新建处理器。
- 模型分类使用少样本示例；格式、有限置信分数、低置信度和 3 秒默认超时均有规则回退。可通过 `COMPANION_INTENT_ROUTER_USE_LLM` 与 `COMPANION_INTENT_ROUTER_TIMEOUT_SECONDS` 配置。
- 自然语言取消提醒按当前用户与标题匹配；多条匹配会询问选择，只有明确“所有”才批量取消。设备执行入口也会复核当前请求，问候、否定或功能询问不会触发设备操作。

## 验证

```powershell
pytest -q core_orchestrator/tests/test_natural_reply.py core_orchestrator/tests/test_routing_quality.py
python tools/eval_intent_router.py --mode rules
python tools/eval_intent_router.py --mode model
```

评测命令从 `apps/backend` 运行；`rules` 离线验证合成样例，`model` 使用已配置服务商。报告包含模型/规则采用数和失败 case ID，不输出密钥。45 条回归全通过代表此用例集的结果，不代表泛化准确率。pytest 默认禁用真实分类模型调用。

## V2.10 · 分工与任务

`specialists.py` 的 `SubAgentOrchestrator` 通过可注入端口分配 Chat、Task、Memory、Device 职责；普通与 SSE 路径使用相同委派入口。Memory 明确调用记忆工具，Device 仍校验当前操作证据；复杂任务使用有步数/时间上限的 TaskAgent。宿主按当前请求限制可变更状态的工具，默认聊天不启用外部写操作。更多协议和 SDK 用法见 `action_executor/README.md`。

`turn_coordinator.py` 按用户和会话串行处理普通/流式输入；不同会话可并行，取消等待者与关闭流会释放锁。该协调器只服务于单个参考宿主进程。

普通响应与 SSE done 增加 `specialist` 和可选 `task`；SSE 在步骤开始/结束时输出 `tool_status`。Web/PC 的“我的事项”显示真实步骤、待补充信息和停止入口，超时/中断不会显示为工具成功。

回归：`pytest -q core_orchestrator/tests/test_specialists.py action_executor/tests/test_task_agent.py`。

## 后续

当前按用户“完成当前任务后暂停开发”的要求暂停。8.1/8.2 已验收，图片理解、完整实时人格与呈现同步等保留；生产数据库、完整隐私控制、插件平台与形象运行时等未验收事项见仓库根目录 `DEVELOPMENT_EXECUTION.md`。

## V2.11 · 分段语音与流取消

SSE 在语音已开启且客户端声明 `supports_segmented_voice=true` 时，使用 `streaming_voice.py` 将文字事件与语音事件合并。分段合成回调由宿主注入，最多 1–4 个合成工作单元，默认 2；句长、排队、单段时限及最多 128 段有界。下一段可先完成合成，交付仍按 seq 顺序。单段失败输出 `voice_segment_error`，文字与后续语音继续。

客户端消费 `voice_segment`、`voice_segment_error`、`voice_done`；最终 `done` 保存 `voice_mode=segmented` 与成功段的 `voice_segments`，无需全文 voice_url。旧客户端及普通非流式入口维持全文语音。配置见 `.env.example` 的 `COMPANION_*STREAMING_TTS*`；全局关闭或客户端未声明支持时不走分段路径。

API → orchestrator → state_machine 显式关闭嵌套异步生成器；断流取消所有合成并等待清理，然后释放用户/会话锁。前端新轮/清空会取消旧请求并停止旧播放，晚到的播放结果不能重新启动。测试：`pytest -q core_orchestrator/tests/test_streaming_voice.py`。

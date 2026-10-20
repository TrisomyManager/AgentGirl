# Avatar runtime

`src/index.ts` 是独立的 TypeScript 播放时钟及呈现数据处理，不依赖 Vue、Live2D、网络、模型厂商或参考应用。任何宿主都可以给 `createAvatarClock` 提供帧观察器，再用自己的 2D/3D 渲染器消费输出。

后端 `apps/backend/avatar_runtime` 只组装 `shared_contracts.avatar.AvatarTimeline`，没有对编排器、语音提供商或渲染引擎的依赖。宿主负责注入情绪；语音适配器只转发公开时间轴，不读取宿主内部状态。

时间轴使用实际音频播放时间，音频能量来自播放器采样。收到元数据时调用 `begin`，实际播放时调用 `sample(token, audioPositionMs, rmsEnergy)`，结束/停止时调用 `stop(token)`；已过期 token 不会改变当前帧。新宿主应把音量分析不可用作为闭嘴降级，不能用随机摆动冒充真实口型。RMS 表示开合强度，不是音素对齐。

参考集成在 Web `useAvatarPresentation.ts`、`useVoice.ts`、`useRealtimeVoice.ts` 和 `useLive2D.ts`。渲染器、语音设备、数据下载和账号权限由宿主管理，均不属于这个纯运行时。

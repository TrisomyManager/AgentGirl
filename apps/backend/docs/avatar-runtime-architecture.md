# Avatar Runtime / Digital Human Pipeline Architecture

## Purpose

`avatar_runtime` is the proposed presentation layer for Xiaonuan's visible body: Live2D, 2D video avatar, 3D avatar, or future WebRTC digital human sessions.

It is intentionally not the brain of Xiaonuan. Persona, memory, planning, tools, reminders, realtime conversation, and device operation stay owned by the existing modules. `avatar_runtime` only turns already-decided conversation state into synchronized visual and playback output.

This design absorbs the useful architectural ideas from digital-human projects such as OpenTalking: pipeline separation, avatar backend adapters, realtime transport, subtitle/status events, interruption handling, and worker orchestration. It does not require importing OpenTalking source code or adding it as a product dependency.

## Architectural Position

```text
apps/web / host app
        |
        | HTTP / WebSocket / WebRTC
        v
gateway_adapter
        |
        v
core_orchestrator  ----> persona_engine
        |              -> memory_system
        |              -> action_executor
        |              -> device_coordination
        |
        +----> voice_layer --------+
        |                          |
        +----> avatar_runtime <----+
                  |
                  v
        Live2D / video avatar / 3D avatar / WebRTC renderer
```

`core_orchestrator` remains the owner of the turn. `voice_layer` remains the owner of ASR/TTS and realtime audio providers. `avatar_runtime` consumes turn state, voice timing, emotion, tool status, and interruption events, then produces render instructions or media streams.

## Module Boundary

### Owns

- Avatar session lifecycle: create, update, interrupt, close.
- Renderer adapter selection: Live2D, frame-sequence, video-avatar backend, 3D renderer, WebRTC media session.
- Visual state mapping: listening, thinking, speaking, tool-running, idle, interrupted.
- Lip-sync and subtitle timing as presentation artifacts.
- Render events for frontend consumption.
- Optional worker orchestration for heavy avatar/video backends.
- Presentation fallback when high-quality avatar backends are unavailable.

### Does Not Own

- Xiaonuan persona definition or tone.
- Long-term memory storage or recall.
- Dialogue generation or intent routing.
- Tool execution, reminders, search, weather, or device commands.
- ASR/TTS provider implementation.
- User identity, authorization, or device permissions.
- Business decisions about whether Xiaonuan should say or do something.

### Dependency Rule

`avatar_runtime` may depend on `shared_contracts` and `shared_runtime`. It may call `voice_layer` APIs or receive events from `core_orchestrator`, but it must not import internal implementation from `persona_engine`, `memory_system`, `action_executor`, or `device_coordination`.

## Runtime Contracts

### Input Events

`avatar_runtime` should be driven by explicit presentation events, not by scraping chat text.

Recommended event types:

```text
avatar:session:start
avatar:session:end
avatar:user:listening
avatar:assistant:thinking
avatar:assistant:speaking
avatar:assistant:interrupted
avatar:tool:started
avatar:tool:ended
avatar:emotion:update
avatar:subtitle:delta
avatar:audio:timing
```

### Render Output

The module can output one of these modes:

- `live2d_state`: motion name, expression, mouth openness, gaze, idle state.
- `frame_sequence`: image/video frame references and timing.
- `webrtc_offer`: SDP/session metadata for realtime audio/video avatar playback.
- `subtitle_event`: partial/final subtitle text with timestamps.
- `status_event`: frontend-friendly state such as listening/thinking/speaking/tool-running.

### Minimal API Shape

```text
POST /avatar/session
POST /avatar/session/{session_id}/event
POST /avatar/session/{session_id}/interrupt
GET  /avatar/backends
GET  /avatar/session/{session_id}/state
WS   /avatar/session/{session_id}/events
```

These endpoints are a future contract. They should not be implemented until the current conversation, memory, tool, and device-operation loops are stable.

## Backend Adapter Model

Avatar backends should be plugins behind a small interface:

```text
AvatarBackend
  - name
  - capabilities
  - latency_class: local | realtime | batch | remote
  - supports_interrupt
  - supports_webrtc
  - start_session()
  - handle_event()
  - synthesize_or_render()
  - interrupt()
  - close()
```

Recommended backend ladder:

1. `live2d_basic`: current frontend Live2D or static avatar motion states.
2. `live2d_lipsync`: Live2D with TTS duration and mouth-shape timing.
3. `frame_sequence`: pre-rendered or generated motion frames.
4. `webrtc_video_avatar`: realtime audio/video digital human backend.
5. `external_digital_human`: third-party or self-hosted model service adapter.

OpenTalking-like systems are useful references for stages 4 and 5, especially WebRTC session management and model-backend abstraction.

## Interruption Semantics

Interruption must be handled as a first-class presentation event:

1. User starts speaking or taps interrupt.
2. `core_orchestrator` or `voice_layer` emits an interruption event.
3. `avatar_runtime` stops current speech animation or WebRTC stream if the backend supports it.
4. Frontend switches to listening state.
5. Memory and conversation ownership remains with the orchestrator.

The presentation layer must never decide to discard or rewrite conversation content by itself.

## Lite Mode

Lite Mode must not require GPU, FFmpeg, WebRTC infrastructure, or model servers.

Lite Mode fallback:

- Use static avatar or Live2D frontend state.
- Use text subtitles and simple mouth-open timing from audio duration.
- Skip heavy video rendering.
- Keep all `/health` and normal chat flows available even if `avatar_runtime` is disabled.

## Security And Privacy

- Do not send raw user camera/video to avatar backends unless the user explicitly enables such a feature.
- Do not store generated avatar video by default.
- Do not expose third-party avatar provider keys to frontend clients.
- Do not allow avatar backend prompts to override Xiaonuan persona or system instructions.
- Treat avatar rendering as presentation, not as an autonomous agent.

## Adoption Plan

### Phase 0: Documentation Only

Document the boundary and prevent accidental coupling. This is the current phase.

### Phase 1: Event Contract

Add shared contract models for avatar state, subtitle timing, render events, and interruption events. No heavy backend.

### Phase 2: Live2D Unification

Move current Live2D/action2d behavior behind the same presentation event model.

### Phase 3: Realtime Video Avatar Research

Prototype a WebRTC adapter outside the main user flow. OpenTalking can be used as an architectural reference, but its source tree must stay outside this repository unless a small, reviewed snippet is intentionally adopted.

### Phase 4: Production Backends

Support one or more optional high-quality avatar backends with clear deployment flags, health checks, cost controls, and graceful fallback.

## Non-Goals

- No full OpenTalking integration in the current repository.
- No GPU model service requirement for the main app.
- No replacement of `voice_layer`.
- No replacement of `core_orchestrator`.
- No avatar-driven memory writes.
- No avatar backend allowed to execute tools or device operations directly.

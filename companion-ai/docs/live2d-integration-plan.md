# Live2D集成方案 - 小暖角色可视化

## 一、技术选型

### 方案A：pixi-live2d-display（推荐）
- **优势**：
  - Vue 3兼容性好，通过原生DOM操作集成
  - 支持Live2D Cubism 2/3/4模型
  - 性能优秀（WebGL硬件加速）
  - 活跃维护，社区支持强
  - 支持表情切换、动作播放、鼠标交互
  
- **劣势**：
  - 需要购买或制作Live2D模型（`.moc3` + 纹理 + 动作文件）
  - 首次加载资源较大（2-5MB）

### 方案B：原生Cubism SDK for Web
- **优势**：官方SDK，最大控制力
- **劣势**：集成复杂度高，需要手写大量底层代码

## 二、实现架构

```
frontend_app/
├── public/
│   └── live2d/                    # Live2D资源目录
│       └── xiaonuan/              # 小暖角色模型
│           ├── xiaonuan.model3.json
│           ├── xiaonuan.moc3
│           ├── textures/
│           │   ├── texture_00.png
│           │   └── ...
│           └── motions/
│               ├── idle_01.motion3.json
│               ├── happy_01.motion3.json
│               └── typing_01.motion3.json
│
├── src/
│   ├── components/
│   │   └── AvatarDisplay.vue      # 改造为Live2D容器
│   │
│   └── composables/
│       └── useLive2D.ts           # Live2D逻辑封装
```

## 三、代码实现

### 3.1 安装依赖

```bash
cd frontend_app
npm install pixi.js pixi-live2d-display
```

### 3.2 useLive2D.ts（可组合函数）

```typescript
import { ref, onMounted, onUnmounted, Ref } from 'vue';
import { Application } from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display';

// 全局注册Live2D
window.PIXI = { Application };

export interface Live2DOptions {
  modelPath: string;
  width: number;
  height: number;
}

export function useLive2D(
  containerRef: Ref<HTMLElement | null>,
  options: Live2DOptions
) {
  const model = ref<Live2DModel | null>(null);
  const app = ref<Application | null>(null);
  const isLoading = ref(true);
  const error = ref<string | null>(null);

  async function initLive2D() {
    if (!containerRef.value) {
      error.value = 'Container not found';
      return;
    }

    try {
      // 创建PixiJS应用
      app.value = new Application({
        width: options.width,
        height: options.height,
        backgroundColor: 0x0d0d1a,
        backgroundAlpha: 0,
        antialias: true,
      });

      containerRef.value.appendChild(app.value.view as HTMLCanvasElement);

      // 加载Live2D模型
      const loadedModel = await Live2DModel.from(options.modelPath, {
        autoInteract: true, // 启用鼠标交互
      });

      model.value = loadedModel;

      // 模型缩放适配
      const scaleX = options.width / loadedModel.width;
      const scaleY = options.height / loadedModel.height;
      const scale = Math.min(scaleX, scaleY) * 0.8;

      loadedModel.scale.set(scale);
      loadedModel.x = options.width / 2;
      loadedModel.y = options.height / 2;
      loadedModel.anchor.set(0.5, 0.5);

      app.value.stage.addChild(loadedModel);

      isLoading.value = false;
    } catch (err) {
      error.value = `Failed to load Live2D model: ${err}`;
      isLoading.value = false;
      console.error(err);
    }
  }

  function playMotion(group: string, index = 0) {
    if (model.value) {
      model.value.motion(group, index);
    }
  }

  function setExpression(name: string) {
    if (model.value) {
      model.value.expression(name);
    }
  }

  onMounted(() => {
    initLive2D();
  });

  onUnmounted(() => {
    if (app.value) {
      app.value.destroy(true, { children: true });
    }
  });

  return {
    model,
    isLoading,
    error,
    playMotion,
    setExpression,
  };
}
```

### 3.3 AvatarDisplay.vue 改造

```vue
<template>
  <div class="avatar-display">
    <!-- Live2D容器 -->
    <div ref="live2dContainer" class="live2d-container" :class="{ floating: isTyping }">
      <div v-if="isLoading" class="loading-placeholder">
        <div class="spinner"></div>
        <p>加载小暖中...</p>
      </div>
      <div v-if="live2dError" class="error-placeholder">
        <p>{{ live2dError }}</p>
        <img src="https://placehold.co/400x600/1a1a2e/FFF?text=小暖" alt="小暖" />
      </div>
    </div>

    <!-- 情绪/动作信息 -->
    <div class="avatar-info">
      <div class="emotion-badge" :class="emotionClass">
        <span class="emotion-icon">{{ emotionIcon }}</span>
        <span>{{ emotionLabel }}</span>
      </div>
      <div v-if="actionLabel" class="action-text">
        {{ actionLabel }}
      </div>
    </div>

    <div class="decoration-orbs">
      <div class="orb orb-1"></div>
      <div class="orb orb-2"></div>
      <div class="orb orb-3"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useLive2D } from '../composables/useLive2D';

const props = defineProps<{
  emotionLabel: string;
  emotion: string;
  actionLabel: string;
  isTyping: boolean;
}>();

const live2dContainer = ref<HTMLElement | null>(null);

const {
  isLoading,
  error: live2dError,
  playMotion,
  setExpression,
} = useLive2D(live2dContainer, {
  modelPath: '/live2d/xiaonuan/xiaonuan.model3.json',
  width: 260,
  height: 390,
});

// 情绪映射到Live2D表情
const emotionToExpression: Record<string, string> = {
  happy: 'happy',
  excited: 'excited',
  sad: 'sad',
  angry: 'angry',
  surprised: 'surprised',
  calm: 'calm',
  neutral: 'neutral',
};

// 监听情绪变化，切换表情
watch(() => props.emotion, (newEmotion) => {
  const expressionName = emotionToExpression[newEmotion];
  if (expressionName) {
    setExpression(expressionName);
  }
});

// 监听打字状态，播放动作
watch(() => props.isTyping, (typing) => {
  if (typing) {
    playMotion('typing', 0); // 播放打字动作
  } else {
    playMotion('idle', 0); // 播放待机动作
  }
});

const emotionClass = computed(() => {
  const map: Record<string, string> = {
    happy: 'emotion-happy',
    excited: 'emotion-happy',
    sad: 'emotion-sad',
    angry: 'emotion-angry',
    surprised: 'emotion-surprised',
    calm: 'emotion-calm',
    neutral: 'emotion-calm',
  };
  return map[props.emotion] || 'emotion-calm';
});

const emotionIcon = computed(() => {
  const map: Record<string, string> = {
    happy: '😊',
    excited: '🤩',
    sad: '😢',
    angry: '😠',
    surprised: '😲',
    fearful: '😨',
    disgusted: '🤢',
    affectionate: '🥰',
    concerned: '😟',
    calm: '😌',
    neutral: '😐',
  };
  return map[props.emotion] || '😐';
});
</script>

<style scoped>
.live2d-container {
  position: relative;
  width: 260px;
  height: 390px;
  border-radius: 20px;
  overflow: hidden;
  transition: transform 0.3s ease;
  background: rgba(26, 26, 46, 0.3);
}

.live2d-container.floating {
  animation: float 2s ease-in-out infinite;
}

.loading-placeholder,
.error-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #94a3b8;
  font-size: 14px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(233, 69, 96, 0.2);
  border-top-color: #e94560;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}

/* 保留原有emotion-badge和decoration-orbs样式 */
/* ... */
</style>
```

## 四、Live2D模型获取方案

### 方案1：委托制作（推荐）
- **平台**：猪八戒网、Fiverr、站酷
- **预算**：¥3000-¥15000（根据精细度）
- **周期**：2-4周
- **交付物**：
  - `.moc3`模型文件
  - 纹理图（PSD分层 + PNG导出）
  - 8-12组动作文件（idle/happy/sad/typing/waving等）
  - 5-8种表情切换

### 方案2：使用免费/开源模型
- **来源**：
  - [Live2D公式样本](https://www.live2d.com/en/download/sample-data/)
  - [VTuber Maker社区](https://store.steampowered.com/app/1207050/VTuber_Maker/)
  - GitHub搜索 `live2d model free`
- **限制**：需遵守授权协议，可能不符合"小暖"人设

### 方案3：等待AIRI项目开源（如果适用）
- 如果AIRI的Live2D模型可复用且符合授权，直接迁移

## 五、性能与优化

### 资源优化
```typescript
// 懒加载Live2D模型
const { useLive2D } = await import('../composables/useLive2D');

// 压缩纹理（使用WebP格式，减少50%体积）
// 启用PixiJS纹理缓存
```

### 降级策略
```typescript
// 检测设备性能，低端设备回退到静态图片
const isLowEnd = navigator.hardwareConcurrency < 4 || 
                 /Android|webOS|iPhone/i.test(navigator.userAgent);

if (isLowEnd) {
  // 使用当前静态图片方案
} else {
  // 使用Live2D
}
```

## 六、工作量估计

| 任务 | 工作量 | 依赖 |
|------|--------|------|
| 安装配置pixi-live2d-display | 0.5天 | - |
| 编写useLive2D.ts | 1天 | - |
| 改造AvatarDisplay.vue | 0.5天 | useLive2D |
| 情绪/动作映射逻辑 | 0.5天 | - |
| Live2D模型获取/制作 | **2-4周** | 外包 |
| 集成测试与性能优化 | 1天 | 模型 |
| **总计（不含模型制作）** | **3天** | - |
| **总计（含模型制作）** | **2-4周** | - |

## 七、与当前架构的兼容性

✅ **完全兼容**：
- Vue 3 Composition API无冲突
- 不影响现有情绪系统（[useChat.ts](../frontend_app/src/composables/useChat.ts)中的`currentEmotion`）
- 与后端persona_engine的emotion输出无缝对接
- 支持渐进式增强（模型加载失败时降级到静态图）

## 八、建议

### 短期（1周内）
1. 先使用Live2D官方免费样本模型验证技术方案
2. 实现完整的`useLive2D.ts` + 改造后的`AvatarDisplay.vue`
3. 测试情绪切换、打字动作等交互效果

### 中期（2-4周）
1. 委托设计师制作"小暖"专属Live2D模型
2. 根据人设定义8-12组动作 + 5-8种表情
3. 优化资源加载（CDN、WebP压缩）

### 长期优化
1. 实现高级交互（眼球跟随鼠标、呼吸动画）
2. 与语音系统联动（说话时嘴型同步）
3. 考虑WebGPU渲染（PixiJS v8+支持）

# Live2D闆嗘垚鏂规 - 灏忔殩瑙掕壊鍙鍖?
## 涓€銆佹妧鏈€夊瀷

### 鏂规A锛歱ixi-live2d-display锛堟帹鑽愶級
- **浼樺娍**锛?  - Vue 3鍏煎鎬уソ锛岄€氳繃鍘熺敓DOM鎿嶄綔闆嗘垚
  - 鏀寔Live2D Cubism 2/3/4妯″瀷
  - 鎬ц兘浼樼锛圵ebGL纭欢鍔犻€燂級
  - 娲昏穬缁存姢锛岀ぞ鍖烘敮鎸佸己
  - 鏀寔琛ㄦ儏鍒囨崲銆佸姩浣滄挱鏀俱€侀紶鏍囦氦浜?  
- **鍔ｅ娍**锛?  - 闇€瑕佽喘涔版垨鍒朵綔Live2D妯″瀷锛坄.moc3` + 绾圭悊 + 鍔ㄤ綔鏂囦欢锛?  - 棣栨鍔犺浇璧勬簮杈冨ぇ锛?-5MB锛?
### 鏂规B锛氬師鐢烠ubism SDK for Web
- **浼樺娍**锛氬畼鏂筍DK锛屾渶澶ф帶鍒跺姏
- **鍔ｅ娍**锛氶泦鎴愬鏉傚害楂橈紝闇€瑕佹墜鍐欏ぇ閲忓簳灞備唬鐮?
## 浜屻€佸疄鐜版灦鏋?
```
frontend_app/
鈹溾攢鈹€ public/
鈹?  鈹斺攢鈹€ live2d/                    # Live2D璧勬簮鐩綍
鈹?      鈹斺攢鈹€ xiaonuan/              # 灏忔殩瑙掕壊妯″瀷
鈹?          鈹溾攢鈹€ xiaonuan.model3.json
鈹?          鈹溾攢鈹€ xiaonuan.moc3
鈹?          鈹溾攢鈹€ textures/
鈹?          鈹?  鈹溾攢鈹€ texture_00.png
鈹?          鈹?  鈹斺攢鈹€ ...
鈹?          鈹斺攢鈹€ motions/
鈹?              鈹溾攢鈹€ idle_01.motion3.json
鈹?              鈹溾攢鈹€ happy_01.motion3.json
鈹?              鈹斺攢鈹€ typing_01.motion3.json
鈹?鈹溾攢鈹€ src/
鈹?  鈹溾攢鈹€ components/
鈹?  鈹?  鈹斺攢鈹€ AvatarDisplay.vue      # 鏀归€犱负Live2D瀹瑰櫒
鈹?  鈹?鈹?  鈹斺攢鈹€ composables/
鈹?      鈹斺攢鈹€ useLive2D.ts           # Live2D閫昏緫灏佽
```

## 涓夈€佷唬鐮佸疄鐜?
### 3.1 瀹夎渚濊禆

```bash
cd frontend_app
npm install pixi.js pixi-live2d-display
```

### 3.2 useLive2D.ts锛堝彲缁勫悎鍑芥暟锛?
```typescript
import { ref, onMounted, onUnmounted, Ref } from 'vue';
import { Application } from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display';

// 鍏ㄥ眬娉ㄥ唽Live2D
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
      // 鍒涘缓PixiJS搴旂敤
      app.value = new Application({
        width: options.width,
        height: options.height,
        backgroundColor: 0x0d0d1a,
        backgroundAlpha: 0,
        antialias: true,
      });

      containerRef.value.appendChild(app.value.view as HTMLCanvasElement);

      // 鍔犺浇Live2D妯″瀷
      const loadedModel = await Live2DModel.from(options.modelPath, {
        autoInteract: true, // 鍚敤榧犳爣浜や簰
      });

      model.value = loadedModel;

      // 妯″瀷缂╂斁閫傞厤
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

### 3.3 AvatarDisplay.vue 鏀归€?
```vue
<template>
  <div class="avatar-display">
    <!-- Live2D瀹瑰櫒 -->
    <div ref="live2dContainer" class="live2d-container" :class="{ floating: isTyping }">
      <div v-if="isLoading" class="loading-placeholder">
        <div class="spinner"></div>
        <p>鍔犺浇灏忔殩涓?..</p>
      </div>
      <div v-if="live2dError" class="error-placeholder">
        <p>{{ live2dError }}</p>
        <img src="https://placehold.co/400x600/1a1a2e/FFF?text=灏忔殩" alt="灏忔殩" />
      </div>
    </div>

    <!-- 鎯呯华/鍔ㄤ綔淇℃伅 -->
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

// 鎯呯华鏄犲皠鍒癓ive2D琛ㄦ儏
const emotionToExpression: Record<string, string> = {
  happy: 'happy',
  excited: 'excited',
  sad: 'sad',
  angry: 'angry',
  surprised: 'surprised',
  calm: 'calm',
  neutral: 'neutral',
};

// 鐩戝惉鎯呯华鍙樺寲锛屽垏鎹㈣〃鎯?watch(() => props.emotion, (newEmotion) => {
  const expressionName = emotionToExpression[newEmotion];
  if (expressionName) {
    setExpression(expressionName);
  }
});

// 鐩戝惉鎵撳瓧鐘舵€侊紝鎾斁鍔ㄤ綔
watch(() => props.isTyping, (typing) => {
  if (typing) {
    playMotion('typing', 0); // 鎾斁鎵撳瓧鍔ㄤ綔
  } else {
    playMotion('idle', 0); // 鎾斁寰呮満鍔ㄤ綔
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
    happy: '馃槉',
    excited: '馃ぉ',
    sad: '馃槩',
    angry: '馃槧',
    surprised: '馃槻',
    fearful: '馃槰',
    disgusted: '馃あ',
    affectionate: '馃グ',
    concerned: '馃槦',
    calm: '馃槍',
    neutral: '馃槓',
  };
  return map[props.emotion] || '馃槓';
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

/* 淇濈暀鍘熸湁emotion-badge鍜宒ecoration-orbs鏍峰紡 */
/* ... */
</style>
```

## 鍥涖€丩ive2D妯″瀷鑾峰彇鏂规

### 鏂规1锛氬鎵樺埗浣滐紙鎺ㄨ崘锛?- **骞冲彴**锛氱尓鍏垝缃戙€丗iverr銆佺珯閰?- **棰勭畻**锛毬?000-楼15000锛堟牴鎹簿缁嗗害锛?- **鍛ㄦ湡**锛?-4鍛?- **浜や粯鐗?*锛?  - `.moc3`妯″瀷鏂囦欢
  - 绾圭悊鍥撅紙PSD鍒嗗眰 + PNG瀵煎嚭锛?  - 8-12缁勫姩浣滄枃浠讹紙idle/happy/sad/typing/waving绛夛級
  - 5-8绉嶈〃鎯呭垏鎹?
### 鏂规2锛氫娇鐢ㄥ厤璐?寮€婧愭ā鍨?- **鏉ユ簮**锛?  - [Live2D鍏紡鏍锋湰](https://www.live2d.com/en/download/sample-data/)
  - [VTuber Maker绀惧尯](https://store.steampowered.com/app/1207050/VTuber_Maker/)
  - GitHub鎼滅储 `live2d model free`
- **闄愬埗**锛氶渶閬靛畧鎺堟潈鍗忚锛屽彲鑳戒笉绗﹀悎"灏忔殩"浜鸿

### 方案3：外部上游参考（已归档）
## 浜斻€佹€ц兘涓庝紭鍖?
### 璧勬簮浼樺寲
```typescript
// 鎳掑姞杞絃ive2D妯″瀷
const { useLive2D } = await import('../composables/useLive2D');

// 鍘嬬缉绾圭悊锛堜娇鐢╓ebP鏍煎紡锛屽噺灏?0%浣撶Н锛?// 鍚敤PixiJS绾圭悊缂撳瓨
```

### 闄嶇骇绛栫暐
```typescript
// 妫€娴嬭澶囨€ц兘锛屼綆绔澶囧洖閫€鍒伴潤鎬佸浘鐗?const isLowEnd = navigator.hardwareConcurrency < 4 || 
                 /Android|webOS|iPhone/i.test(navigator.userAgent);

if (isLowEnd) {
  // 浣跨敤褰撳墠闈欐€佸浘鐗囨柟妗?} else {
  // 浣跨敤Live2D
}
```

## 鍏€佸伐浣滈噺浼拌

| 浠诲姟 | 宸ヤ綔閲?| 渚濊禆 |
|------|--------|------|
| 瀹夎閰嶇疆pixi-live2d-display | 0.5澶?| - |
| 缂栧啓useLive2D.ts | 1澶?| - |
| 鏀归€燗vatarDisplay.vue | 0.5澶?| useLive2D |
| 鎯呯华/鍔ㄤ綔鏄犲皠閫昏緫 | 0.5澶?| - |
| Live2D妯″瀷鑾峰彇/鍒朵綔 | **2-4鍛?* | 澶栧寘 |
| 闆嗘垚娴嬭瘯涓庢€ц兘浼樺寲 | 1澶?| 妯″瀷 |
| **鎬昏锛堜笉鍚ā鍨嬪埗浣滐級** | **3澶?* | - |
| **鎬昏锛堝惈妯″瀷鍒朵綔锛?* | **2-4鍛?* | - |

## 涓冦€佷笌褰撳墠鏋舵瀯鐨勫吋瀹规€?
鉁?**瀹屽叏鍏煎**锛?- Vue 3 Composition API鏃犲啿绐?- 涓嶅奖鍝嶇幇鏈夋儏缁郴缁燂紙[useChat.ts](../frontend_app/src/composables/useChat.ts)涓殑`currentEmotion`锛?- 涓庡悗绔痯ersona_engine鐨別motion杈撳嚭鏃犵紳瀵规帴
- 鏀寔娓愯繘寮忓寮猴紙妯″瀷鍔犺浇澶辫触鏃堕檷绾у埌闈欐€佸浘锛?
## 鍏€佸缓璁?
### 鐭湡锛?鍛ㄥ唴锛?1. 鍏堜娇鐢↙ive2D瀹樻柟鍏嶈垂鏍锋湰妯″瀷楠岃瘉鎶€鏈柟妗?2. 瀹炵幇瀹屾暣鐨刞useLive2D.ts` + 鏀归€犲悗鐨刞AvatarDisplay.vue`
3. 娴嬭瘯鎯呯华鍒囨崲銆佹墦瀛楀姩浣滅瓑浜や簰鏁堟灉

### 涓湡锛?-4鍛級
1. 濮旀墭璁捐甯堝埗浣?灏忔殩"涓撳睘Live2D妯″瀷
2. 鏍规嵁浜鸿瀹氫箟8-12缁勫姩浣?+ 5-8绉嶈〃鎯?3. 浼樺寲璧勬簮鍔犺浇锛圕DN銆乄ebP鍘嬬缉锛?
### 闀挎湡浼樺寲
1. 瀹炵幇楂樼骇浜や簰锛堢溂鐞冭窡闅忛紶鏍囥€佸懠鍚稿姩鐢伙級
2. 涓庤闊崇郴缁熻仈鍔紙璇磋瘽鏃跺槾鍨嬪悓姝ワ級
3. 鑰冭檻WebGPU娓叉煋锛圥ixiJS v8+鏀寔锛?

import { ref, onMounted, onUnmounted, Ref } from 'vue';
import * as PIXI from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display';

// 注册全局PIXI（pixi-live2d-display需要）
if (typeof window !== 'undefined') {
  (window as any).PIXI = PIXI;
}

export interface Live2DOptions {
  modelPath: string;
  width: number;
  height: number;
  autoInteract?: boolean;
}

export function useLive2D(
  containerRef: Ref<HTMLElement | null>,
  options: Live2DOptions
) {
  const model = ref<any>(null);
  const app = ref<PIXI.Application | null>(null);
  const isLoading = ref(true);
  const error = ref<string | null>(null);

  async function initLive2D() {
    if (!containerRef.value) {
      error.value = 'Container element not found';
      isLoading.value = false;
      return;
    }

    try {
      // 直接使用静态导入的Live2DModel

      // 创建PixiJS应用
      app.value = new PIXI.Application({
        width: options.width,
        height: options.height,
        backgroundAlpha: 0,
        antialias: true,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
      });

      // 将canvas添加到容器
      const canvas = app.value.view as HTMLCanvasElement;
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      containerRef.value.appendChild(canvas);

      // 加载Live2D模型
      const loadedModel = await Live2DModel.from(options.modelPath, {
        autoInteract: options.autoInteract ?? true,
      });

      model.value = loadedModel;

      // 模型缩放适配 - 居中显示
      const scaleX = options.width / loadedModel.width;
      const scaleY = options.height / loadedModel.height;
      const scale = Math.min(scaleX, scaleY) * 0.8;

      loadedModel.scale.set(scale);
      loadedModel.x = options.width / 2;
      loadedModel.y = options.height / 2;
      loadedModel.anchor.set(0.5, 0.5);

      app.value.stage.addChild(loadedModel as any);

      // 监听点击事件
      loadedModel.on('hit', (hitAreas: string[]) => {
        console.log('Live2D hit areas:', hitAreas);
      });

      isLoading.value = false;
      console.log('Live2D model loaded successfully');
    } catch (err) {
      error.value = `Failed to load Live2D model: ${err}`;
      isLoading.value = false;
      console.error('Live2D loading error:', err);
    }
  }

  /**
   * 播放动作
   * @param group 动作组名称（如 'idle', 'tap_body'）
   * @param index 动作索引，默认0
   * @param priority 优先级，默认2（普通）
   */
  function playMotion(group: string, index = 0, priority = 2) {
    if (model.value) {
      try {
        model.value.motion(group, index, priority);
      } catch (err) {
        console.warn(`Failed to play motion ${group}[${index}]:`, err);
      }
    }
  }

  /**
   * 设置表情
   * @param name 表情名称或索引
   */
  function setExpression(name: string | number) {
    if (model.value) {
      try {
        model.value.expression(name);
      } catch (err) {
        console.warn(`Failed to set expression ${name}:`, err);
      }
    }
  }

  /**
   * 获取可用的动作组列表
   */
  function getMotionGroups(): string[] {
    if (model.value && model.value.internalModel?.motionManager) {
      const motionManager = model.value.internalModel.motionManager as any;
      return motionManager.definitions ? Object.keys(motionManager.definitions) : [];
    }
    return [];
  }

  /**
   * 获取可用的表情列表
   */
  function getExpressions(): string[] {
    if (model.value && model.value.internalModel?.motionManager) {
      const motionManager = model.value.internalModel.motionManager as any;
      return motionManager.expressionManager?.definitions
        ? motionManager.expressionManager.definitions.map((def: any) => def.name)
        : [];
    }
    return [];
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
    getMotionGroups,
    getExpressions,
  };
}

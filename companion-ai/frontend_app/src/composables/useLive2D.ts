import { ref, onMounted, onUnmounted, type Ref } from 'vue';
import * as PIXI from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display';

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

  let resizeObserver: ResizeObserver | null = null;

  function getContainerSize() {
    const fallbackWidth = Math.max(options.width, 1);
    const fallbackHeight = Math.max(options.height, 1);
    const el = containerRef.value;

    if (!el) {
      return { width: fallbackWidth, height: fallbackHeight };
    }

    const rect = el.getBoundingClientRect();
    return {
      width: Math.max(Math.round(rect.width || fallbackWidth), 1),
      height: Math.max(Math.round(rect.height || fallbackHeight), 1),
    };
  }

  function layoutModel(targetModel = model.value) {
    if (!app.value || !targetModel) {
      return;
    }

    const { width, height } = getContainerSize();
    app.value.renderer.resize(width, height);

    const scaleX = width / targetModel.width;
    const scaleY = height / targetModel.height;
    const scale = Math.min(scaleX, scaleY) * 0.8;

    targetModel.scale.set(scale);
    targetModel.anchor.set(0.5, 0.5);
    targetModel.x = width / 2;
    targetModel.y = height / 2;
  }

  async function initLive2D() {
    if (!containerRef.value) {
      error.value = 'Container element not found';
      isLoading.value = false;
      return;
    }

    try {
      const initialSize = getContainerSize();

      app.value = new PIXI.Application({
        width: initialSize.width,
        height: initialSize.height,
        backgroundAlpha: 0,
        antialias: true,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
      });

      const canvas = app.value.view as HTMLCanvasElement;
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      containerRef.value.appendChild(canvas);

      const loadedModel = await Live2DModel.from(options.modelPath, {
        autoInteract: options.autoInteract ?? true,
      });

      model.value = loadedModel;
      app.value.stage.addChild(loadedModel as any);
      layoutModel(loadedModel);

      loadedModel.on('hit', (hitAreas: string[]) => {
        console.log('Live2D hit areas:', hitAreas);
      });

      if (typeof ResizeObserver !== 'undefined' && containerRef.value) {
        resizeObserver = new ResizeObserver(() => {
          layoutModel();
        });
        resizeObserver.observe(containerRef.value);
      }

      isLoading.value = false;
      console.log('Live2D model loaded successfully');
    } catch (err) {
      error.value = `Failed to load Live2D model: ${err}`;
      isLoading.value = false;
      console.error('Live2D loading error:', err);
    }
  }

  function playMotion(group: string, index = 0, priority = 2) {
    if (!model.value) {
      return;
    }

    try {
      model.value.motion(group, index, priority);
    } catch (err) {
      console.warn(`Failed to play motion ${group}[${index}]:`, err);
    }
  }

  function setExpression(name: string | number) {
    if (!model.value) {
      return;
    }

    try {
      model.value.expression(name);
    } catch (err) {
      console.warn(`Failed to set expression ${name}:`, err);
    }
  }

  function getMotionGroups(): string[] {
    if (model.value && model.value.internalModel?.motionManager) {
      const motionManager = model.value.internalModel.motionManager as any;
      return motionManager.definitions ? Object.keys(motionManager.definitions) : [];
    }
    return [];
  }

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
    void initLive2D();
  });

  onUnmounted(() => {
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }

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

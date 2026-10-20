import { ref, onMounted, onUnmounted, type Ref } from 'vue';
import * as PIXI from 'pixi.js';
import type { AvatarFrame } from '../../../../packages/avatar-runtime/src';

if (typeof window !== 'undefined') {
  (window as any).PIXI = PIXI;
}

type Live2DModelCtor = typeof import('pixi-live2d-display')['Live2DModel'];

function waitForCubism2Runtime(timeoutMs = 10_000): Promise<void> {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    const tick = () => {
      if (typeof (window as any).Live2D !== 'undefined') {
        resolve();
        return;
      }
      if (Date.now() >= deadline) {
        reject(new Error('Live2D Cubism 2 runtime (live2d.min.js) not loaded'));
        return;
      }
      requestAnimationFrame(tick);
    };
    tick();
  });
}

async function loadLive2DModelClass(): Promise<Live2DModelCtor> {
  await waitForCubism2Runtime();
  const { Live2DModel, config } = await import('pixi-live2d-display/cubism2');
  // Sample motions include Japanese voice clips. All speech comes from the
  // application's voice player, including when model interactions start motions.
  config.sound = false;
  return Live2DModel;
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
  let disposed = false;
  let detachPresentation: (() => void) | null = null;
  type Presentation = Pick<AvatarFrame, 'mouthOpen'> & { mouthForm: number; angleY?: number; angleZ?: number };
  let presentation: Presentation = { mouthOpen: 0, mouthForm: 0 };
  // Live2DModel.width / .height return getBounds() which is affected by the
  // current scale. If we feed those back into the next layout pass, scale
  // compounds across ResizeObserver ticks (font load, flex settle, scrollbar
  // appearing) and the model balloons out of the canvas. Cache the intrinsic
  // (scale = 1) bounds once so every subsequent layout uses a stable size.
  let intrinsicWidth = 0;
  let intrinsicHeight = 0;

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

    if (!intrinsicWidth || !intrinsicHeight) {
      const previousScale = targetModel.scale?.x ?? 1;
      targetModel.scale.set(1);
      const bounds = targetModel.getBounds?.() ?? {
        width: targetModel.width,
        height: targetModel.height,
      };
      intrinsicWidth = Math.max(bounds.width || 0, 1);
      intrinsicHeight = Math.max(bounds.height || 0, 1);
      targetModel.scale.set(previousScale);
    }

    const { width, height } = getContainerSize();
    app.value.renderer.resize(width, height);

    const scaleX = width / intrinsicWidth;
    const scaleY = height / intrinsicHeight;
    // Keep a generous margin so hair tips / desk feet stay inside the frame
    // even when getBounds() under-reports the rendered area for some Live2D
    // sample models.
    const scale = Math.min(scaleX, scaleY) * 0.78;

    targetModel.scale.set(scale);

    // Live2DModel does NOT honor PIXI.Sprite's anchor — its origin is defined
    // by the model layout file. Compute the real on-stage bounds AFTER scale
    // is applied and translate the model so its visible bounding box is
    // centered inside the canvas.
    const liveBounds = targetModel.getBounds?.() ?? {
      x: targetModel.x ?? 0,
      y: targetModel.y ?? 0,
      width: targetModel.width || intrinsicWidth * scale,
      height: targetModel.height || intrinsicHeight * scale,
    };
    const offsetX = (width - liveBounds.width) / 2 - (liveBounds.x - (targetModel.x ?? 0));
    const offsetY = (height - liveBounds.height) / 2 - (liveBounds.y - (targetModel.y ?? 0));
    targetModel.x = offsetX;
    targetModel.y = offsetY;
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
      const renderingApp = app.value;

      const canvas = app.value.view as HTMLCanvasElement;
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      containerRef.value.appendChild(canvas);

      const Live2DModel = await loadLive2DModelClass();
      if (disposed) return;
      const loadedModel = await Live2DModel.from(options.modelPath, {
        autoInteract: options.autoInteract ?? true,
      });
      if (disposed || app.value !== renderingApp) {
        loadedModel.destroy();
        return;
      }

      model.value = loadedModel;
      let mouth = 0, form = 0, headY = 0, headZ = 0, previousTime = performance.now();
      const updatePresentation = () => {
        const now = performance.now();
        const dt = Math.min(100, Math.max(0, now - previousTime));
        previousTime = now;
        mouth += (presentation.mouthOpen - mouth) * (1 - Math.exp(-dt / 45));
        form += (presentation.mouthForm - form) * (1 - Math.exp(-dt / 220));
        headY += ((presentation.angleY || 0) - headY) * (1 - Math.exp(-dt / 160));
        headZ += ((presentation.angleZ || 0) - headZ) * (1 - Math.exp(-dt / 160));
        const core = loadedModel.internalModel.coreModel as {
          setParamFloat(id: string, value: number): void;
          addToParamFloat(id: string, value: number): void;
        };
        core.setParamFloat('PARAM_MOUTH_OPEN_Y', mouth);
        core.setParamFloat('PARAM_MOUTH_FORM', form);
        core.addToParamFloat('PARAM_ANGLE_Y', headY);
        core.addToParamFloat('PARAM_ANGLE_Z', headZ);
      };
      loadedModel.internalModel.on('beforeModelUpdate', updatePresentation);
      detachPresentation = () => loadedModel.internalModel.off('beforeModelUpdate', updatePresentation);
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
      if (disposed) return;
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
      if (!getMotionGroups().includes(group)) return;
      void Promise.resolve(model.value.motion(group, index, priority)).catch(() => {});
    } catch (err) {
      console.warn(`Failed to play motion ${group}[${index}]:`, err);
    }
  }

  function setExpression(name: string | number) {
    if (!model.value) {
      return;
    }

    try {
      if (typeof name === 'string' && !getExpressions().includes(name)) return;
      void Promise.resolve(model.value.expression(name)).catch(() => {});
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

  function setPresentation(frame: Presentation) {
    presentation = {
      mouthOpen: Number.isFinite(frame.mouthOpen) ? Math.max(0, Math.min(1, frame.mouthOpen)) : 0,
      mouthForm: Number.isFinite(frame.mouthForm) ? Math.max(-1, Math.min(1, frame.mouthForm)) : 0,
      angleY: Math.max(-8, Math.min(8, frame.angleY || 0)),
      angleZ: Math.max(-8, Math.min(8, frame.angleZ || 0)),
    };
  }

  onMounted(() => {
    void initLive2D();
  });

  onUnmounted(() => {
    disposed = true;
    detachPresentation?.();
    detachPresentation = null;
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }

    if (app.value) {
      app.value.destroy(true, { children: true });
      app.value = null;
      model.value = null;
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
    setPresentation,
  };
}

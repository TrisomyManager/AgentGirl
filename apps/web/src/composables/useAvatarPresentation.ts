import { shallowRef } from 'vue';
import { createAvatarClock, IDLE_FRAME } from '../../../../packages/avatar-runtime/src';

/** Reference host composition only; the clock itself has no framework dependency. */
export const avatarFrame = shallowRef({ ...IDLE_FRAME });
export const avatarClock = createAvatarClock(frame => { avatarFrame.value = frame; });

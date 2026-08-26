// Simple test: import a composable from @/ alias
import { ref } from 'vue';
console.log('Vue loaded, ref:', typeof ref);
const msg = ref('小暖 PC Client test');
console.log(msg.value);
export { msg };

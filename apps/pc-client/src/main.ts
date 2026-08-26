// Use Vite alias to reach apps/web/src/
import App from '@/App.vue';
import { createApp } from 'vue';

const app = createApp(App as any);
app.mount('#app');

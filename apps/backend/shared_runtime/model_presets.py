"""Public Volcengine defaults. Credentials are supplied by the user."""

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
CHAT_MODEL = "doubao-seed-2-0-mini-260428"
REASONING_MODEL = "doubao-seed-2-0-pro-260215"
EMBEDDING_MODEL = "doubao-embedding-vision-251215"
EMBEDDING_DIM = 1024  # Supported reduction; fits pgvector IVFFlat (maximum 2000 dimensions).
SPEECH_BASE_URL = "https://openspeech.bytedance.com"
ASR_RESOURCE = "volc.seedasr.sauc.duration"
TTS_RESOURCE = "seed-tts-2.0"
TTS_VOICE = "zh_female_xiaohe_uranus_bigtts"
REALTIME_MODEL = "1.2.1.1"
REALTIME_VOICE = "zh_female_xiaohe_jupiter_bigtts"

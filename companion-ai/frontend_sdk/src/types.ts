export enum Platform {
  APP = 'app',
  TELEGRAM = 'telegram',
  DISCORD = 'discord',
  WECHAT = 'wechat',
  FEISHU = 'feishu',
}

export enum EmotionTag {
  NEUTRAL = 'neutral',
  HAPPY = 'happy',
  SAD = 'sad',
  ANGRY = 'angry',
  SURPRISED = 'surprised',
  FEARFUL = 'fearful',
  DISGUSTED = 'disgusted',
  AFFECTIONATE = 'affectionate',
  CONCERNED = 'concerned',
  EXCITED = 'excited',
  CALM = 'calm',
}

export enum ActionType {
  IDLE = 'idle',
  TALK = 'talk',
  LISTEN = 'listen',
  REACT_HAPPY = 'react_happy',
  REACT_SAD = 'react_sad',
  REACT_SURPRISED = 'react_surprised',
  REACT_THINKING = 'react_thinking',
  GESTURE_WAVE = 'gesture_wave',
  GESTURE_NOD = 'gesture_nod',
  GESTURE_HEAD_TILT = 'gesture_head_tilt',
}

export interface UserProfile {
  user_id: string;
  display_name: string;
  platform: Platform;
  language: string;
}

export interface EmotionState {
  primary: EmotionTag;
  intensity: number;
  valence: number;
  arousal: number;
  timestamp: string;
  trigger?: string;
}

export interface ActionFrame {
  frame_id: string;
  action_type: ActionType;
  image_url?: string;
  lip_shape?: string;
  duration_ms: number;
  emotion: EmotionTag;
}

export interface ActionSequence {
  sequence_id: string;
  turn_id: string;
  frames: ActionFrame[];
  total_duration_ms: number;
  tts_audio_url?: string;
}

export interface TurnMessage {
  message_id: string;
  session_id: string;
  user_id: string;
  platform: Platform;
  content: string;
  emotion: EmotionTag;
  action_sequence?: ActionSequence;
  voice_url?: string;
  timestamp: string;
}

export interface SendMessageRequest {
  content: string;
  has_voice?: boolean;
  voice_data_b64?: string;
  has_image?: boolean;
  image_urls?: string[];
}

export interface CompanionConfig {
  gatewayUrl: string;
  wsPath?: string;
  apiPath?: string;
  userId: string;
  platform?: Platform;
  reconnectInterval?: number;
  heartbeatInterval?: number;
  language?: string;
}

export type MessageHandler = (msg: TurnMessage) => void;
export type ConnectionHandler = (connected: boolean) => void;
export type ErrorHandler = (error: Error) => void;

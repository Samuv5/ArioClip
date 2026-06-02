export interface Clip {
  id: string;
  filename: string;
  file_path: string;
  start_time: string;
  end_time: string;
  duration: number;
  text: string;
  relevance_score: number;
  reasoning: string;
  clip_order: number;
  created_at: string;
  video_url: string;
  virality_score: number;
  hook_score: number;
  engagement_score: number;
  value_score: number;
  shareability_score: number;
  hook_type: string | null;
}

export interface TaskDetails {
  id: string;
  user_id: string;
  source_id: string;
  source_title: string;
  source_url: string;
  source_type: string;
  status: string;
  progress?: number;
  progress_message?: string;
  clips_count: number;
  created_at: string;
  updated_at: string;
  font_family?: string;
  font_size?: number;
  font_color?: string;
  caption_template?: string;
  include_broll?: boolean;
  cut_long_pauses?: boolean;
  pause_threshold_ms?: number;
  remove_filler_words?: boolean;
  filtered_words?: string[];
  error_code?: string;
}

export interface FontOption {
  name: string;
  display_name: string;
}

export interface CaptionTemplateOption {
  id: string;
  name: string;
  description: string;
  animation: string;
}

export type ExportPreset = "original" | "tiktok" | "reels" | "shorts";
export type CaptionPosition = "top" | "middle" | "bottom";

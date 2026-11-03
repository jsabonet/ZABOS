export type VideoTemplateId =
  | "showcase"
  | "tutorial"
  | "before_after"
  | "quick_tips"
  | "brand_story";

export type VisualThemeId =
  | "cinematic_stories"
  | "kinetic_editorial"
  | "modern_product";

export type VideoScene = {
  text: string;
  duration_seconds: number;
  background_color: string;
  image_path?: string;
  layers?: VideoSceneLayer[];
  captions?: CaptionSegment[];
  motion?: SceneMotion;
  image_treatment?: ImageTreatment;
  typography_animation?: TypographyAnimation;
  motion_graphic?: MotionGraphic;
};

export type ImageTreatment =
  | "natural"
  | "warm"
  | "cool"
  | "monochrome"
  | "film";

export type TypographyAnimation =
  | "fade_up"
  | "pop"
  | "typewriter"
  | "word_reveal"
  | "none";

export type MotionGraphic =
  | "none"
  | "accent_line"
  | "orbit"
  | "corner_frame";

export type EndCard = {
  enabled: boolean;
  title: string;
  subtitle?: string;
  cta: string;
  duration_seconds: number;
};

export type SceneMotion =
  | "slow_zoom"
  | "pan_left"
  | "pan_right"
  | "float"
  | "none";

export type SceneVisualPlan = {
  scene_index: number;
  camera?: {
    movement: SceneMotion;
    intensity: number;
  };
  transition?: SceneTransition;
};

export type SceneTransition = {
  type: SceneTransitionType;
  duration_frames: number;
};

export type VisualDirectionPlan = {
  schema_version: 1;
  theme: VisualThemeId;
  scenes: SceneVisualPlan[];
};

export type SceneTransitionType =
  | "cut"
  | "fade"
  | "wipe_left"
  | "wipe_right";

export type VideoSceneLayer = {
  asset_id?: string;
  asset_path?: string;
  kind: "image" | "video";
  role: "background" | "foreground";
  motion: SceneMotion;
  opacity: number;
  fit: "cover" | "contain";
};

export type CaptionSegment = {
  text: string;
  start_seconds: number;
  end_seconds: number;
};

export type VideoNarration = {
  text?: string;
  asset_id?: string;
  audio_path?: string;
  generate_local?: boolean;
};

export type VideoProps = {
  schema_version: 1 | 2;
  template_id?: VideoTemplateId;
  visual_theme_id?: VisualThemeId;
  visual_direction_plan?: VisualDirectionPlan;
  title: string;
  scenes: VideoScene[];
  narration?: VideoNarration;
  end_card?: EndCard;
};

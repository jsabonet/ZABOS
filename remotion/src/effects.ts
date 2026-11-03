import type { SceneMotion, SceneTransitionType } from "./types";

export const CAMERA_EFFECTS = {
  slow_zoom: { media: ["image", "video"], implemented: true },
  pan_left: { media: ["image", "video"], implemented: true },
  pan_right: { media: ["image", "video"], implemented: true },
  float: { media: ["image", "video"], implemented: true },
  none: { media: ["image", "video"], implemented: true },
} as const satisfies Record<
  SceneMotion,
  { media: readonly ("image" | "video")[]; implemented: boolean }
>;

export const SCENE_TRANSITIONS = {
  cut: { implemented: true },
  fade: { implemented: true },
  wipe_left: { implemented: true },
  wipe_right: { implemented: true },
} as const satisfies Record<SceneTransitionType, { implemented: boolean }>;

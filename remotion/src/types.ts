export type VideoScene = {
  text: string;
  duration_seconds: number;
  background_color: string;
  image_path?: string;
};

export type VideoProps = {
  schema_version: 1;
  title: string;
  scenes: VideoScene[];
};

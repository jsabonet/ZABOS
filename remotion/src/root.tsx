import React from "react";
import { Composition } from "remotion";

import { ShortVideo } from "./ShortVideo";
import type { VideoProps } from "./types";

const defaultProps: VideoProps = {
  schema_version: 1,
  template_id: "showcase",
  visual_theme_id: "cinematic_stories",
  title: "Dica rápida",
  scenes: [
    {
      text: "Uma boa ideia merece ser partilhada.",
      duration_seconds: 4,
      background_color: "#17172b",
    },
  ],
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="ShortVideo"
    component={ShortVideo}
    durationInFrames={120}
    fps={30}
    height={1920}
    width={1080}
    defaultProps={defaultProps}
    calculateMetadata={({ props }) => ({
      durationInFrames:
        props.scenes.reduce(
          (total, scene) => total + scene.duration_seconds,
          0,
        ) * 30 +
        (props.end_card?.enabled ? props.end_card.duration_seconds * 30 : 0),
    })}
  />
);

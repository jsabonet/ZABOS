import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import type { VideoProps, VideoScene } from "./types";

const Scene: React.FC<{ scene: VideoScene; index: number }> = ({
  scene,
  index,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const entrance = interpolate(frame, [0, 12], [36, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        backgroundColor: scene.background_color,
        color: "white",
        justifyContent: "center",
        overflow: "hidden",
        padding: 88,
        textAlign: "center",
      }}
    >
      {scene.image_path ? (
        <Img
          src={staticFile(scene.image_path)}
          style={{
            height: "100%",
            objectFit: "cover",
            opacity: 0.28,
            position: "absolute",
            width: "100%",
          }}
        />
      ) : null}
      <div
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,.05), rgba(0,0,0,.28))",
          inset: 0,
          position: "absolute",
        }}
      />
      <div
        style={{
          alignItems: "center",
          display: "flex",
          flexDirection: "column",
          gap: 48,
          position: "relative",
          transform: `translateY(${entrance}px)`,
          width: "100%",
        }}
      >
        <div
          style={{
            background: "#ff3158",
            borderRadius: 999,
            fontFamily: "Arial, sans-serif",
            fontSize: 28,
            fontWeight: 800,
            letterSpacing: 4,
            padding: "14px 28px",
            textTransform: "uppercase",
          }}
        >
          {index === 0 ? "A tua próxima ideia" : "Dica rápida"}
        </div>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: 78,
            fontWeight: 900,
            lineHeight: 1.08,
            textShadow: "0 5px 24px rgba(0,0,0,.45)",
            whiteSpace: "pre-wrap",
          }}
        >
          {scene.text}
        </div>
        <div
          style={{
            background: "rgba(255,255,255,.92)",
            borderRadius: 999,
            height: 8,
            marginTop: 16,
            overflow: "hidden",
            width: 220,
          }}
        >
          <div
            style={{
              background: "#ff3158",
              height: "100%",
              transform: `scaleX(${Math.min(frame / (scene.duration_seconds * fps), 1)})`,
              transformOrigin: "left",
              width: "100%",
            }}
          />
        </div>
      </div>
      <div
        style={{
          bottom: 76,
          fontFamily: "Arial, sans-serif",
          fontSize: 27,
          fontWeight: 700,
          left: 0,
          opacity: 0.9,
          position: "absolute",
          right: 0,
        }}
      >
        {`@${"teu_negocio"}`}
      </div>
    </AbsoluteFill>
  );
};

export const ShortVideo: React.FC<VideoProps> = ({ scenes }) => {
  let from = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#111" }}>
      {scenes.map((scene, index) => {
        const durationInFrames = scene.duration_seconds * 30;
        const sequence = (
          <Sequence
            key={`${index}-${from}`}
            durationInFrames={durationInFrames}
            from={from}
          >
            <Scene scene={scene} index={index} />
          </Sequence>
        );
        from += durationInFrames;
        return sequence;
      })}
    </AbsoluteFill>
  );
};

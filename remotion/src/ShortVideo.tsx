import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  Sequence,
  staticFile,
  Video,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import type {
  VideoProps,
  VideoScene,
  VideoSceneLayer,
  VideoTemplateId,
  SceneMotion,
  SceneTransition,
  SceneVisualPlan,
  VisualThemeId,
  ImageTreatment,
  MotionGraphic,
  TypographyAnimation,
} from "./types";
import { CAMERA_EFFECTS, SCENE_TRANSITIONS } from "./effects";

const THEME_ACCENTS: Record<VisualThemeId, string> = {
  cinematic_stories: "#D8B77C",
  kinetic_editorial: "#C5FF49",
  modern_product: "#496653",
};

const IMAGE_FILTERS: Record<ImageTreatment, string> = {
  natural: "none",
  warm: "sepia(.2) saturate(1.15)",
  cool: "hue-rotate(12deg) saturate(1.08)",
  monochrome: "grayscale(1) contrast(1.08)",
  film: "sepia(.28) contrast(.94) saturate(.82)",
};

const revealText = (
  text: string,
  animation: TypographyAnimation,
  frame: number,
) => {
  if (animation !== "typewriter") return text;
  return text.slice(0, Math.ceil(interpolate(frame, [0, 30], [0, text.length], {
    extrapolateRight: "clamp",
  })));
};

const typographyStyle = (
  animation: TypographyAnimation,
  frame: number,
): React.CSSProperties => {
  if (animation === "pop") {
    const progress = interpolate(frame, [0, 14], [0, 1], {
      extrapolateRight: "clamp",
    });
    return { opacity: progress, transform: `scale(${0.82 + progress * 0.18})` };
  }
  if (animation === "fade_up") {
    const progress = interpolate(frame, [0, 14], [0, 1], {
      extrapolateRight: "clamp",
    });
    return { opacity: progress, transform: `translateY(${24 * (1 - progress)}px)` };
  }
  return {};
};

const getSceneLabel = (
  templateId: VideoTemplateId,
  index: number,
  sceneCount: number,
) => {
  if (templateId === "tutorial") return `PASSO ${String(index + 1).padStart(2, "0")}`;
  if (templateId === "quick_tips") return `IDEIA ${String(index + 1).padStart(2, "0")}`;
  if (templateId === "before_after") {
    return index === 0 ? "ANTES" : index === sceneCount - 1 ? "DEPOIS" : "TRANSFORMAÇÃO";
  }
  if (templateId === "brand_story") return "A NOSSA HISTÓRIA";
  return "EM DESTAQUE";
};

const layerTransform = (
  motion: SceneMotion,
  frame: number,
  durationFrames: number,
  intensity = 1,
) => {
  if (!CAMERA_EFFECTS[motion]?.implemented) return "scale(1)";
  if (motion === "slow_zoom") {
    const scale = interpolate(frame, [0, durationFrames], [1.02, 1.02 + 0.1 * intensity], {
      extrapolateRight: "clamp",
    });
    return `scale(${scale})`;
  }
  if (motion === "pan_left") {
    const x = interpolate(frame, [0, durationFrames], [16 * intensity, -16 * intensity], {
      extrapolateRight: "clamp",
    });
    return `scale(${1 + 0.08 * intensity}) translateX(${x}px)`;
  }
  if (motion === "pan_right") {
    const x = interpolate(frame, [0, durationFrames], [-16 * intensity, 16 * intensity], {
      extrapolateRight: "clamp",
    });
    return `scale(${1 + 0.08 * intensity}) translateX(${x}px)`;
  }
  if (motion === "float") {
    return `scale(${1 + 0.04 * intensity}) translateY(${Math.sin(frame / 18) * 12 * intensity}px)`;
  }
  return "scale(1)";
};

const SceneMedia: React.FC<{
  scene: VideoScene;
  frame: number;
  fps: number;
  legacyTransform?: string;
  legacyOpacity?: number;
  cameraPlan?: SceneVisualPlan["camera"];
}> = ({ scene, frame, fps, legacyTransform = "scale(1.04)", legacyOpacity = 1, cameraPlan }) => {
  const layers = scene.layers ?? [];
  const durationFrames = scene.duration_seconds * fps;
  const renderLayer = (layer: VideoSceneLayer, index: number) => {
    if (!layer.asset_path) return null;
    const style: React.CSSProperties = {
      height: "100%",
      objectFit: layer.fit,
      opacity: layer.opacity,
      position: "absolute",
      filter: IMAGE_FILTERS[scene.image_treatment ?? "natural"],
      transform: layerTransform(
        cameraPlan?.movement ?? layer.motion,
        frame,
        durationFrames,
        cameraPlan?.intensity,
      ),
      width: "100%",
      zIndex: layer.role === "foreground" ? 2 : 0,
    };
    const src = staticFile(layer.asset_path);
    return layer.kind === "video" ? (
      <Video
        key={`${layer.asset_path}-${index}`}
        loop
        src={src}
        muted
        style={style}
      />
    ) : (
      <Img key={`${layer.asset_path}-${index}`} src={src} style={style} />
    );
  };

  return (
    <div style={{ inset: 0, overflow: "hidden", position: "absolute" }}>
      {scene.image_path && (
        <Img
          src={staticFile(scene.image_path)}
          style={{
            height: "100%",
            objectFit: "cover",
            opacity: legacyOpacity,
            filter: IMAGE_FILTERS[scene.image_treatment ?? "natural"],
            position: "absolute",
            transform: cameraPlan
              ? layerTransform(
                  cameraPlan.movement,
                  frame,
                  durationFrames,
                  cameraPlan.intensity,
                )
              : legacyTransform,
            width: "100%",
            zIndex: 0,
          }}
        />
      )}
      {layers.map(renderLayer)}
    </div>
  );
};

const CinematicFrame: React.FC<{
  scene: VideoScene;
  title: string;
  index: number;
  sceneCount: number;
  templateId: VideoTemplateId;
  frame: number;
  entrance: number;
  opacity: number;
  progress: number;
  cameraPlan?: SceneVisualPlan["camera"];
  typographyAnimation: TypographyAnimation;
}> = ({ scene, title, index, sceneCount, templateId, frame, entrance, opacity, progress, cameraPlan, typographyAnimation }) => {
  const zoom = interpolate(frame, [0, scene.duration_seconds * 30], [1.035, 1.12], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 68% 28%, ${scene.background_color} 0%, #171a18 74%)`,
        color: "#f5f0e5",
        justifyContent: "space-between",
        opacity,
        overflow: "hidden",
        padding: "95px 82px 105px",
      }}
    >
      <SceneMedia
        frame={frame}
        legacyOpacity={scene.image_path ? 0.62 : 0.18}
        legacyTransform={`scale(${zoom})`}
        fps={30}
        scene={scene}
        cameraPlan={cameraPlan}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(10,12,11,.16) 0%, rgba(10,12,11,.1) 32%, rgba(10,12,11,.88) 100%), linear-gradient(90deg, rgba(10,12,11,.35), transparent 82%)",
        }}
      />
      <div style={{ alignItems: "center", display: "flex", justifyContent: "space-between", position: "relative" }}>
        <span style={{ color: THEME_ACCENTS.cinematic_stories, fontFamily: "Arial, sans-serif", fontSize: 20, fontWeight: 700, letterSpacing: 4 }}>
          LUME <span style={{ color: "rgba(255,255,255,.62)", fontWeight: 400 }}>ORIGINAL</span>
        </span>
        <span style={{ color: "rgba(255,255,255,.68)", fontFamily: "Arial, sans-serif", fontSize: 18, letterSpacing: 3 }}>
          {String(index + 1).padStart(2, "0")} / {String(sceneCount).padStart(2, "0")}
        </span>
      </div>
      <div
        style={{
          maxWidth: 890,
          position: "relative",
          transform: `translateY(${entrance}px)`,
        }}
      >
        <div style={{ alignItems: "center", color: THEME_ACCENTS.cinematic_stories, display: "flex", fontFamily: "Arial, sans-serif", fontSize: 19, gap: 16, letterSpacing: 4, textTransform: "uppercase" }}>
          <span style={{ background: THEME_ACCENTS.cinematic_stories, height: 1, width: 52 }} />
          {getSceneLabel(templateId, index, sceneCount)}
        </div>
        <h1
          style={{
            color: "#f7f2e8",
            fontFamily: "Georgia, 'Times New Roman', serif",
            fontSize: Math.max(66, Math.min(104, 104 - Math.max(0, scene.text.length - 24) * 0.38)),
            fontWeight: 400,
            letterSpacing: -2.4,
            lineHeight: 1.02,
            margin: "32px 0 0",
            maxWidth: 880,
            textShadow: "0 6px 40px rgba(0,0,0,.42)",
            whiteSpace: "pre-wrap",
            ...typographyStyle(
              typographyAnimation === "word_reveal" ? "fade_up" : typographyAnimation,
              frame,
            ),
          }}
        >
          {revealText(scene.text, typographyAnimation, frame)}
        </h1>
        <p style={{ color: "rgba(245,240,229,.67)", fontFamily: "Arial, sans-serif", fontSize: 21, letterSpacing: 2, margin: "35px 0 0", textTransform: "uppercase" }}>
          {title}
        </p>
      </div>
      <div style={{ position: "relative" }}>
        <div style={{ color: "rgba(255,255,255,.72)", display: "flex", fontFamily: "Arial, sans-serif", fontSize: 18, justifyContent: "space-between", letterSpacing: 2 }}>
          <span>UMA HISTÓRIA EM MOVIMENTO</span>
          <span style={{ color: THEME_ACCENTS.cinematic_stories }}>LUME FILMS</span>
        </div>
        <div style={{ background: "rgba(255,255,255,.25)", height: 2, marginTop: 18, overflow: "hidden" }}>
          <div style={{ background: THEME_ACCENTS.cinematic_stories, height: "100%", transform: `scaleX(${progress})`, transformOrigin: "left", width: "100%" }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

const KineticFrame: React.FC<{
  scene: VideoScene;
  title: string;
  index: number;
  sceneCount: number;
  templateId: VideoTemplateId;
  frame: number;
  opacity: number;
  progress: number;
  cameraPlan?: SceneVisualPlan["camera"];
  typographyAnimation: TypographyAnimation;
}> = ({ scene, title, index, sceneCount, templateId, frame, opacity, progress, cameraPlan, typographyAnimation }) => {
  const words = scene.text.trim().split(/\s+/).filter(Boolean);
  const fontSize = Math.max(64, Math.min(106, 106 - Math.max(0, scene.text.length - 24) * 0.45));
  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(145deg, #242c30 0%, #131917 56%, #0c100e 100%)",
        color: "#f5f7ef",
        justifyContent: "space-between",
        opacity,
        overflow: "hidden",
        padding: "88px 78px 100px",
      }}
    >
      <SceneMedia
        frame={frame}
        fps={30}
        legacyOpacity={scene.image_path ? 0.17 : 0.08}
        scene={scene}
        cameraPlan={cameraPlan}
      />
      <div style={{ background: THEME_ACCENTS.kinetic_editorial, height: "100%", left: 0, position: "absolute", top: 0, transform: `scaleY(${interpolate(frame, [0, 20], [0.12, 1], { extrapolateRight: "clamp" })})`, transformOrigin: "top", width: 13 }} />
      <div style={{ alignItems: "center", display: "flex", justifyContent: "space-between", position: "relative" }}>
        <span style={{ color: THEME_ACCENTS.kinetic_editorial, fontFamily: "Arial, sans-serif", fontSize: 21, fontWeight: 900, letterSpacing: 4 }}>LUME / PLAY</span>
        <span style={{ border: `1px solid ${THEME_ACCENTS.kinetic_editorial}`, color: THEME_ACCENTS.kinetic_editorial, fontFamily: "Arial, sans-serif", fontSize: 17, fontWeight: 800, letterSpacing: 2, padding: "11px 15px" }}>
          {getSceneLabel(templateId, index, sceneCount)}
        </span>
      </div>
      <div style={{ position: "relative" }}>
        <div style={{ color: "rgba(245,247,239,.58)", fontFamily: "Arial, sans-serif", fontSize: 19, fontWeight: 700, letterSpacing: 4, marginBottom: 22 }}>
          {String(index + 1).padStart(2, "0")} <span style={{ color: THEME_ACCENTS.kinetic_editorial }}>—</span> {title.toUpperCase()}
        </div>
        <div style={{ alignContent: "flex-start", display: "flex", flexWrap: "wrap", gap: "0 20px", lineHeight: 0.94, maxWidth: 930 }}>
          {typographyAnimation === "word_reveal" ? words.map((word, wordIndex) => {
            const delay = Math.min(wordIndex * 1.5, 15);
            const wordOpacity = interpolate(frame, [delay, delay + 8], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const wordY = interpolate(frame, [delay, delay + 8], [34, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <span
                key={`${word}-${wordIndex}`}
                style={{
                  color: wordIndex % 3 === 2 ? THEME_ACCENTS.kinetic_editorial : "#f5f7ef",
                  fontFamily: "Arial, sans-serif",
                  fontSize,
                  fontWeight: 900,
                  letterSpacing: -5,
                  opacity: wordOpacity,
                  textTransform: "uppercase",
                  transform: `translateY(${wordY}px)`,
                }}
              >
                {word}
              </span>
            );
          }) : (
            <span style={{
              color: "#f5f7ef",
              fontFamily: "Arial, sans-serif",
              fontSize,
              fontWeight: 900,
              letterSpacing: -5,
              textTransform: "uppercase",
              ...typographyStyle(typographyAnimation, frame),
            }}>
              {revealText(scene.text, typographyAnimation, frame)}
            </span>
          )}
        </div>
        <div style={{ alignItems: "center", display: "flex", gap: 13, marginTop: 35 }}>
          <span style={{ background: THEME_ACCENTS.kinetic_editorial, height: 7, width: 68 }} />
          <span style={{ color: "rgba(245,247,239,.65)", fontFamily: "Arial, sans-serif", fontSize: 17, fontWeight: 700, letterSpacing: 3 }}>
            SWIPE PARA A PRÓXIMA IDEIA
          </span>
        </div>
      </div>
      <div style={{ position: "relative" }}>
        <div style={{ color: "rgba(255,255,255,.76)", display: "flex", fontFamily: "Arial, sans-serif", fontSize: 18, fontWeight: 700, justifyContent: "space-between", letterSpacing: 3 }}>
          <span>GUARDA ESTA IDEIA</span>
          <span style={{ color: THEME_ACCENTS.kinetic_editorial }}>{String(index + 1).padStart(2, "0")} / {String(sceneCount).padStart(2, "0")}</span>
        </div>
        <div style={{ background: "rgba(255,255,255,.2)", height: 6, marginTop: 16, overflow: "hidden" }}>
          <div style={{ background: THEME_ACCENTS.kinetic_editorial, height: "100%", transform: `scaleX(${progress})`, transformOrigin: "left", width: "100%" }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

const ProductFrame: React.FC<{
  scene: VideoScene;
  title: string;
  index: number;
  sceneCount: number;
  templateId: VideoTemplateId;
  frame: number;
  entrance: number;
  opacity: number;
  progress: number;
  cameraPlan?: SceneVisualPlan["camera"];
  typographyAnimation: TypographyAnimation;
}> = ({ scene, title, index, sceneCount, templateId, frame, entrance, opacity, progress, cameraPlan, typographyAnimation }) => {
  const scale = interpolate(frame, [0, 18], [0.92, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(ellipse at 50% 34%, #fbf8ef 0%, #eeeadd 56%, #dedacb 100%)",
        color: "#242c25",
        justifyContent: "space-between",
        opacity,
        overflow: "hidden",
        padding: "78px 76px 88px",
      }}
    >
      <div style={{ alignItems: "center", display: "flex", justifyContent: "space-between", position: "relative" }}>
        <span style={{ color: "#324338", fontFamily: "Arial, sans-serif", fontSize: 21, fontWeight: 800, letterSpacing: 4 }}>LUME OBJECTS</span>
        <span style={{ color: "#788074", fontFamily: "Arial, sans-serif", fontSize: 17, letterSpacing: 2 }}>EST. 2026</span>
      </div>
      <div style={{ alignItems: "center", display: "flex", flex: 1, flexDirection: "column", justifyContent: "center", padding: "34px 0", position: "relative", transform: `translateY(${entrance}px)` }}>
        <div style={{ alignItems: "center", background: "#e5e1d4", border: "1px solid rgba(57,73,60,.13)", borderRadius: 22, boxShadow: "0 28px 75px rgba(43,54,44,.14)", display: "flex", height: 760, justifyContent: "center", maxHeight: "56vh", overflow: "hidden", position: "relative", transform: `scale(${scale})`, width: "100%" }}>
          {scene.image_path || scene.layers?.length ? (
            <SceneMedia cameraPlan={cameraPlan} frame={frame} fps={30} scene={scene} />
          ) : (
            <div style={{ alignItems: "center", background: `radial-gradient(circle at 34% 26%, #d7c59f, ${scene.background_color} 72%)`, border: "1px solid rgba(35,47,37,.16)", borderRadius: "50%", boxShadow: "0 34px 54px rgba(38,48,38,.22), inset -18px -18px 34px rgba(22,31,24,.24)", color: "rgba(255,255,255,.85)", display: "flex", fontFamily: "Georgia, serif", fontSize: 25, height: 310, justifyContent: "center", letterSpacing: 5, width: 310 }}>
              LUME
            </div>
          )}
          <div style={{ background: "linear-gradient(180deg, rgba(248,246,238,.04), rgba(31,42,33,.12))", inset: 0, position: "absolute" }} />
          <span style={{ background: "#f9f7ef", border: "1px solid rgba(42,54,43,.12)", borderRadius: 99, bottom: 24, color: "#46564a", fontFamily: "Arial, sans-serif", fontSize: 15, letterSpacing: 2, padding: "11px 18px", position: "absolute" }}>
            {getSceneLabel(templateId, index, sceneCount)}
          </span>
        </div>
        <div style={{ marginTop: 34, maxWidth: 850, textAlign: "center" }}>
          <h1 style={{ color: "#242c25", fontFamily: "Arial, sans-serif", fontSize: Math.max(58, Math.min(88, 88 - Math.max(0, scene.text.length - 24) * 0.35)), fontWeight: 650, letterSpacing: -3, lineHeight: 1.02, margin: 0, ...typographyStyle(typographyAnimation === "word_reveal" ? "fade_up" : typographyAnimation, frame) }}>
            {revealText(scene.text, typographyAnimation, frame)}
          </h1>
          <p style={{ color: "#6b7469", fontFamily: "Arial, sans-serif", fontSize: 19, letterSpacing: 3, margin: "18px 0 0", textTransform: "uppercase" }}>
            {title}
          </p>
        </div>
      </div>
      <div style={{ alignItems: "center", borderTop: "1px solid rgba(36,44,37,.2)", color: "#46564a", display: "flex", fontFamily: "Arial, sans-serif", fontSize: 17, justifyContent: "space-between", letterSpacing: 2, paddingTop: 18 }}>
        <span>DESIGN FEITO PARA DURAR</span>
        <span>{String(index + 1).padStart(2, "0")} / {String(sceneCount).padStart(2, "0")}</span>
        <span style={{ background: "#496653", height: 3, left: 0, position: "absolute", right: 0, transform: `scaleX(${progress})`, transformOrigin: "left", bottom: 0 }} />
      </div>
    </AbsoluteFill>
  );
};

const Scene: React.FC<{
  scene: VideoScene;
  title: string;
  index: number;
  sceneCount: number;
  templateId: VideoTemplateId;
  visualThemeId: VisualThemeId;
  cameraPlan?: SceneVisualPlan["camera"];
  transition?: SceneTransition;
}> = ({ scene, title, index, sceneCount, templateId, visualThemeId, cameraPlan, transition }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durationFrames = scene.duration_seconds * fps;
  const entrance = interpolate(frame, [0, 18], [44, 0], { extrapolateRight: "clamp" });
  const transitionDuration = transition?.duration_frames ?? 12;
  const opacity = transition
    ? transition.type === "fade" && SCENE_TRANSITIONS.fade.implemented
      ? interpolate(frame, [0, transitionDuration], [0, 1], {
          extrapolateRight: "clamp",
        })
      : 1
    : interpolate(
        frame,
        [0, 8, durationFrames - 8, durationFrames],
        [0, 1, 1, 0],
        { extrapolateRight: "clamp" },
      );
  const wipeProgress =
    transition &&
    (transition.type === "wipe_left" || transition.type === "wipe_right") &&
    SCENE_TRANSITIONS[transition.type].implemented
      ? interpolate(frame, [0, transitionDuration], [100, 0], {
          extrapolateRight: "clamp",
        })
      : 0;
  const clipPath =
    transition?.type === "wipe_left"
      ? `inset(0 ${wipeProgress}% 0 0)`
      : transition?.type === "wipe_right"
        ? `inset(0 0 0 ${wipeProgress}%)`
        : undefined;
  const progress = Math.min(frame / durationFrames, 1);
  const typographyAnimation =
    scene.typography_animation ??
    (visualThemeId === "kinetic_editorial" ? "word_reveal" : "fade_up");

  let content: React.ReactNode;
  if (visualThemeId === "kinetic_editorial") {
    content = (
      <KineticFrame
        frame={frame}
        index={index}
        opacity={opacity}
        progress={progress}
        scene={scene}
        sceneCount={sceneCount}
        templateId={templateId}
        title={title}
        cameraPlan={cameraPlan}
        typographyAnimation={typographyAnimation}
      />
    );
  } else if (visualThemeId === "modern_product") {
    content = (
      <ProductFrame
        entrance={entrance}
        frame={frame}
        index={index}
        opacity={opacity}
        progress={progress}
        scene={scene}
        sceneCount={sceneCount}
        templateId={templateId}
        title={title}
        cameraPlan={cameraPlan}
        typographyAnimation={typographyAnimation}
      />
    );
  } else {
    content = (
      <CinematicFrame
        entrance={entrance}
        frame={frame}
        index={index}
        opacity={opacity}
        progress={progress}
        scene={scene}
        sceneCount={sceneCount}
        templateId={templateId}
        title={title}
        cameraPlan={cameraPlan}
        typographyAnimation={typographyAnimation}
      />
    );
  }

  const activeCaption = scene.captions?.find((caption) => {
    const seconds = frame / fps;
    return seconds >= caption.start_seconds && seconds < caption.end_seconds;
  });
  return (
    <AbsoluteFill style={{ backgroundColor: "#111" }}>
      <AbsoluteFill style={clipPath ? { clipPath } : undefined}>
        {content}
        <MotionGraphicOverlay
          accent={THEME_ACCENTS[visualThemeId]}
          frame={frame}
          type={scene.motion_graphic ?? "none"}
        />
        {activeCaption && (
          <div
            style={{
              background: "rgba(10,12,11,.78)",
              borderRadius: 12,
              bottom: 250,
              color: "#fff",
              fontFamily: "Arial, sans-serif",
              fontSize: 44,
              fontWeight: 800,
              left: 80,
              lineHeight: 1.15,
              padding: "16px 22px",
              position: "absolute",
              right: 80,
              textAlign: "center",
              textShadow: "0 2px 12px rgba(0,0,0,.4)",
            }}
          >
            {activeCaption.text}
          </div>
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const MotionGraphicOverlay: React.FC<{
  accent: string;
  frame: number;
  type: MotionGraphic;
}> = ({ accent, frame, type }) => {
  if (type === "none") return null;
  if (type === "accent_line") {
    const progress = interpolate(frame, [0, 20], [0, 1], {
      extrapolateRight: "clamp",
    });
    return (
      <div style={{ left: 80, position: "absolute", right: 80, top: "48%", pointerEvents: "none" }}>
        <div style={{ background: accent, height: 3, opacity: 0.8, transform: `scaleX(${progress})`, transformOrigin: "left", width: "38%" }} />
      </div>
    );
  }
  if (type === "orbit") {
    const rotation = interpolate(frame, [0, 90], [0, 360], {
      extrapolateRight: "extend",
    });
    return (
      <div style={{ border: `2px solid ${accent}`, borderRadius: "50%", height: 210, opacity: 0.55, position: "absolute", right: 62, top: 410, transform: `rotate(${rotation}deg)`, width: 210, pointerEvents: "none" }}>
        <span style={{ background: accent, borderRadius: "50%", height: 18, left: 14, position: "absolute", top: 22, width: 18 }} />
      </div>
    );
  }
  const progress = interpolate(frame, [0, 18], [0, 1], {
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ border: `2px solid ${accent}`, inset: 52, opacity: 0.45, pointerEvents: "none", position: "absolute", transform: `scale(${0.96 + progress * 0.04})` }} />
  );
};

const EndCardFrame: React.FC<{
  accent: string;
  endCard: NonNullable<VideoProps["end_card"]>;
}> = ({ accent, endCard }) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, 18], [0, 1], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ alignItems: "center", background: "linear-gradient(145deg, #121815, #27332b)", color: "#f5f2e9", justifyContent: "center", padding: 100, textAlign: "center" }}>
      <div style={{ background: accent, height: 5, marginBottom: 52, transform: `scaleX(${progress})`, transformOrigin: "center", width: 160 }} />
      <h1 style={{ fontFamily: "Georgia, serif", fontSize: 82, fontWeight: 400, lineHeight: 1.05, margin: 0, opacity: progress, transform: `translateY(${24 * (1 - progress)}px)` }}>
        {endCard.title}
      </h1>
      {endCard.subtitle && (
        <p style={{ color: "rgba(245,242,233,.72)", fontFamily: "Arial, sans-serif", fontSize: 29, lineHeight: 1.4, margin: "30px 0 0", maxWidth: 780 }}>
          {endCard.subtitle}
        </p>
      )}
      <div style={{ border: `2px solid ${accent}`, borderRadius: 999, color: accent, fontFamily: "Arial, sans-serif", fontSize: 25, fontWeight: 700, letterSpacing: 2, marginTop: 64, opacity: progress, padding: "20px 38px", textTransform: "uppercase" }}>
        {endCard.cta}
      </div>
      <span style={{ bottom: 96, color: "rgba(245,242,233,.58)", fontFamily: "Arial, sans-serif", fontSize: 20, letterSpacing: 5, position: "absolute" }}>LUME STUDIO</span>
    </AbsoluteFill>
  );
};

export const ShortVideo: React.FC<VideoProps> = ({
  scenes,
  template_id,
  visual_theme_id,
  visual_direction_plan,
  title,
  narration,
  end_card,
}) => {
  const templateId = template_id ?? "showcase";
  const visualThemeId = visual_theme_id ?? "cinematic_stories";
  let from = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#111" }}>
      {narration?.audio_path && (
        <Audio src={staticFile(narration.audio_path)} />
      )}
      {scenes.map((scene, index) => {
        const durationInFrames = scene.duration_seconds * 30;
        const sequence = (
          <Sequence
            key={`${index}-${from}`}
            durationInFrames={durationInFrames}
            from={from}
          >
            <Scene
              index={index}
              scene={scene}
              sceneCount={scenes.length}
              templateId={templateId}
              title={title}
              visualThemeId={visualThemeId}
              cameraPlan={visual_direction_plan?.scenes.find(
                (plannedScene) => plannedScene.scene_index === index,
              )?.camera}
              transition={visual_direction_plan?.scenes.find(
                (plannedScene) => plannedScene.scene_index === index,
              )?.transition}
            />
          </Sequence>
        );
        from += durationInFrames;
        return sequence;
      })}
      {end_card?.enabled && (
        <Sequence
          durationInFrames={end_card.duration_seconds * 30}
          from={scenes.reduce(
            (total, scene) => total + scene.duration_seconds * 30,
            0,
          )}
        >
          <EndCardFrame
            accent={THEME_ACCENTS[visualThemeId]}
            endCard={end_card}
          />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};

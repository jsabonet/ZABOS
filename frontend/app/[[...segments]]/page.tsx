"use client";

import {
  ChangeEvent,
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ApiRequestError, apiRequest, useAuth } from "../auth-context";
import {
  DEFAULT_VIDEO_TEMPLATE,
  isVideoTemplateId,
  VIDEO_TEMPLATES,
  type VideoTemplateId,
} from "../video-templates";
import {
  DEFAULT_VISUAL_THEME,
  isVisualThemeId,
  VISUAL_THEMES,
  type VisualThemeId,
} from "../visual-themes";

type MediaKind = "image" | "video" | "audio";
type VideoSceneLayer = {
  asset_id: string;
  kind: "image" | "video";
  role: "background" | "foreground";
  motion: "slow_zoom" | "pan_left" | "pan_right" | "float" | "none";
  opacity: number;
  fit: "cover" | "contain";
  source_credit?: string;
  source_url?: string;
};
type VideoScene = {
  text: string;
  duration_seconds: number;
  background_color: string;
  image_path?: string;
  visual_prompt?: string;
  motion?: VideoSceneLayer["motion"];
  image_treatment?: "natural" | "warm" | "cool" | "monochrome" | "film";
  typography_animation?: "fade_up" | "pop" | "typewriter" | "word_reveal" | "none";
  motion_graphic?: "none" | "accent_line" | "orbit" | "corner_frame";
  layers?: VideoSceneLayer[];
  captions?: { text: string; start_seconds: number; end_seconds: number }[];
};
type VisualDirectionPlan = {
  schema_version: 1;
  theme: VisualThemeId;
  scenes: {
    scene_index: number;
    camera?: {
      movement: VideoSceneLayer["motion"];
      intensity: number;
    };
    transition?: {
      type: SceneTransitionType;
      duration_frames: number;
    };
  }[];
};
type SceneTransitionType = "cut" | "fade" | "wipe_left" | "wipe_right";
type VideoPayload = {
  schema_version: 1 | 2;
  template_id?: VideoTemplateId;
  title: string;
  visual_direction?: string;
  visual_direction_plan?: VisualDirectionPlan;
  scenes: VideoScene[];
  narration?: {
    text?: string;
    asset_id?: string;
    generate_local?: boolean;
  };
  end_card?: {
    enabled: boolean;
    title: string;
    subtitle?: string;
    cta: string;
    duration_seconds: number;
  };
};
type UploadedAsset = {
  id: string;
  kind: MediaKind;
  file_url: string;
  original_name: string;
  size_bytes: number;
};
type GenerationStatus =
  | "queued"
  | "writing_script"
  | "draft"
  | "processing"
  | "render_queued"
  | "rendering"
  | "completed"
  | "failed";
type VideoGeneration = {
  id: string;
  prompt: string;
  template_id: VideoTemplateId;
  visual_theme_id: VisualThemeId;
  payload: VideoPayload | Record<string, never>;
  status: GenerationStatus;
  error_message: string;
  asset_pipeline_message: string;
  created_at: string;
  output_url: string | null;
};
type Paginated<T> = { results: T[] };
type PendingCreation = {
  existingIds: Set<string>;
  prompt: string;
  templateId: VideoTemplateId;
  visualThemeId: VisualThemeId;
  startedAt: number;
};
type StudioScreen =
  | "login"
  | "projects"
  | "templates"
  | "visual-themes"
  | "briefing"
  | "editor";

type StudioRoute = {
  screen: StudioScreen;
  generationId: string | null;
  valid: boolean;
};

function parseStudioRoute(pathname: string): StudioRoute {
  if (pathname === "/" || pathname === "/login") {
    return { screen: "login", generationId: null, valid: true };
  }
  if (pathname === "/projects") {
    return { screen: "projects", generationId: null, valid: true };
  }
  if (pathname === "/create/templates") {
    return { screen: "templates", generationId: null, valid: true };
  }
  if (pathname === "/create/themes") {
    return { screen: "visual-themes", generationId: null, valid: true };
  }
  if (pathname === "/create/briefing") {
    return { screen: "briefing", generationId: null, valid: true };
  }
  const videoMatch = pathname.match(/^\/videos\/([0-9a-f-]{36})$/i);
  if (videoMatch) {
    return { screen: "editor", generationId: videoMatch[1], valid: true };
  }
  return { screen: "login", generationId: null, valid: false };
}

function pathForScreen(screen: StudioScreen, generationId: string | null) {
  switch (screen) {
    case "login":
      return "/";
    case "projects":
      return "/projects";
    case "templates":
      return "/create/templates";
    case "visual-themes":
      return "/create/themes";
    case "briefing":
      return "/create/briefing";
    case "editor":
      return generationId ? `/videos/${generationId}` : "/projects";
  }
}

const TEMPLATE_PREVIEWS: Record<
  VideoTemplateId,
  { title: string; text: string; color: string }
> = {
  showcase: {
    title: "Produto em destaque",
    text: "Um sabor que fica contigo.",
    color: "#354928",
  },
  tutorial: {
    title: "Tutorial rápido",
    text: "Prepara o teu café em 3 passos.",
    color: "#19364b",
  },
  before_after: {
    title: "Antes e depois",
    text: "De espaço vazio a lugar com vida.",
    color: "#57382e",
  },
  quick_tips: {
    title: "Lista de dicas",
    text: "3 ideias simples para crescer.",
    color: "#382a52",
  },
  brand_story: {
    title: "História da marca",
    text: "Tudo começou com uma receita de família.",
    color: "#48402d",
  },
};

function TemplateArtwork({ templateId }: { templateId: VideoTemplateId }) {
  const steps: Record<VideoTemplateId, string[]> = {
    showcase: ["GANCHO", "BENEFÍCIO", "ACÇÃO"],
    tutorial: ["RESULTADO", "PASSOS", "DICA"],
    before_after: ["ANTES", "MUDANÇA", "DEPOIS"],
    quick_tips: ["GANCHO", "DICAS", "RESUMO"],
    brand_story: ["ORIGEM", "PROPÓSITO", "CONVITE"],
  };
  return (
    <span aria-hidden="true" className="template-structure-art">
      <span className="template-structure-label">ESTRUTURA DO GUIÃO</span>
      {steps[templateId].map((step, index) => (
        <span className="template-structure-step" key={step}>
          <i>{String(index + 1).padStart(2, "0")}</i>
          <strong>{step}</strong>
          {index < steps[templateId].length - 1 && (
            <span className="template-structure-connector" />
          )}
        </span>
      ))}
    </span>
  );
}

function ThemeArtwork({ themeId }: { themeId: VisualThemeId }) {
  return (
    <span aria-hidden="true" className={`theme-art theme-art-${themeId}`}>
      <span className="theme-art-glow" />
      {themeId === "cinematic_stories" ? (
        <>
          <span className="theme-art-horizon" />
          <span className="theme-art-kicker">UMA HISTÓRIA</span>
          <strong>Há um começo<br />em cada ideia.</strong>
          <span className="theme-art-credit">LUME ORIGINAL</span>
        </>
      ) : themeId === "kinetic_editorial" ? (
        <>
          <span className="theme-art-kicker">PÁRA · OLHA</span>
          <strong>FAZ<br />ACONTECER<span>.</span></strong>
          <span className="theme-art-stripe" />
          <span className="theme-art-credit">IDEIA 01 / 03</span>
        </>
      ) : (
        <>
          <span className="theme-art-kicker">OBJECTO Nº 01</span>
          <span className="theme-art-object" />
          <strong>Menos.<br />Melhor.</strong>
          <span className="theme-art-credit">EST. LUME</span>
        </>
      )}
    </span>
  );
}

function ThemePicker({
  selectedThemeId,
  onSelect,
  compact = false,
}: {
  selectedThemeId: VisualThemeId;
  onSelect: (themeId: VisualThemeId) => void;
  compact?: boolean;
}) {
  return (
    <div
      aria-label="Tema visual"
      className={`visual-theme-picker${compact ? " is-compact" : ""}`}
      role="group"
    >
      {VISUAL_THEMES.map((theme) => (
        <button
          aria-pressed={selectedThemeId === theme.id}
          className={`visual-theme-choice theme-${theme.id}${selectedThemeId === theme.id ? " is-selected" : ""}`}
          key={theme.id}
          onClick={() => onSelect(theme.id)}
          type="button"
        >
          {!compact && <ThemeArtwork themeId={theme.id} />}
          <span className="visual-theme-choice-copy">
            <strong>{theme.name}</strong>
            <span>{compact ? theme.promise : theme.description}</span>
            {!compact && <small>{theme.motion}</small>}
          </span>
          <span aria-hidden="true" className="visual-theme-check">
            {selectedThemeId === theme.id ? "✓" : ""}
          </span>
        </button>
      ))}
    </div>
  );
}

const labels: Record<GenerationStatus, string> = {
  queued: "Na fila",
  writing_script: "A criar guião",
  draft: "A aguardar revisão",
  processing: "A processar",
  render_queued: "Render na fila",
  rendering: "A renderizar",
  completed: "Concluído",
  failed: "Falhou",
};

const activeStatuses: GenerationStatus[] = [
  "queued",
  "writing_script",
  "processing",
  "render_queued",
  "rendering",
];

function isPayload(payload: VideoGeneration["payload"]): payload is VideoPayload {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "schema_version" in payload &&
    (payload.schema_version === 1 || payload.schema_version === 2) &&
    Array.isArray(payload.scenes)
  );
}

function getPreviewLabel(
  templateId: VideoTemplateId,
  sceneIndex: number,
  sceneCount: number,
) {
  if (templateId === "tutorial") return `PASSO ${String(sceneIndex + 1).padStart(2, "0")}`;
  if (templateId === "before_after") {
    if (sceneIndex === 0) return "ANTES";
    if (sceneIndex === sceneCount - 1) return "DEPOIS";
    return "TRANSFORMAÇÃO";
  }
  if (templateId === "quick_tips") return `DICA ${String(sceneIndex + 1).padStart(2, "0")}`;
  if (templateId === "brand_story") return "A NOSSA HISTÓRIA";
  return sceneIndex === 0 ? "A TUA PRÓXIMA IDEIA" : "EM DESTAQUE";
}

function imageTreatmentFilter(
  treatment: VideoScene["image_treatment"] | undefined,
) {
  switch (treatment) {
    case "warm":
      return "sepia(.2) saturate(1.15)";
    case "cool":
      return "hue-rotate(12deg) saturate(1.08)";
    case "monochrome":
      return "grayscale(1) contrast(1.08)";
    case "film":
      return "sepia(.28) contrast(.94) saturate(.82)";
    default:
      return "none";
  }
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pt-PT", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function StepMark({ done, active }: { done: boolean; active: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`step-mark${done ? " is-done" : ""}${active ? " is-active" : ""}`}
    >
      {done ? "✓" : active ? <span className="step-spinner" /> : ""}
    </span>
  );
}

function statusStep(status: GenerationStatus | null) {
  if (!status) return 0;
  if (status === "queued" || status === "writing_script") return 1;
  if (status === "draft") return 2;
  if (
    status === "processing" ||
    status === "render_queued" ||
    status === "rendering"
  )
    return 3;
  if (status === "completed") return 4;
  return 0;
}

export default function Home() {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const route = parseStudioRoute(pathname);
  const screen = route.screen;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { user, status: authStatus, error: authError, login, logout } = useAuth();
  const [generations, setGenerations] = useState<VideoGeneration[]>([]);
  const [detailLookup, setDetailLookup] = useState<{
    id: string;
    status: "not-found" | "error";
    message?: string;
  } | null>(null);
  const [detailRetryCount, setDetailRetryCount] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] =
    useState<VideoTemplateId>(DEFAULT_VIDEO_TEMPLATE);
  const [visualThemeId, setVisualThemeId] =
    useState<VisualThemeId>(DEFAULT_VISUAL_THEME);
  const [previewingTemplate, setPreviewingTemplate] = useState(true);
  const [editingPayload, setEditingPayload] = useState<VideoPayload | null>(null);
  const [editingGenerationId, setEditingGenerationId] = useState<string | null>(
    null,
  );
  const [activeSceneIndex, setActiveSceneIndex] = useState(0);
  const [videoSource, setVideoSource] = useState<{
    id: string;
    themeId: VisualThemeId;
    url: string;
  } | null>(null);
  const [assetPreviewUrls, setAssetPreviewUrls] = useState<
    Record<string, string>
  >({});
  const assetObjectUrls = useRef(new Map<string, string>());
  const pendingCreationRef = useRef<PendingCreation | null>(null);
  const authRedirectGenerationIdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [renderingId, setRenderingId] = useState<string | null>(null);
  const [mobileHistoryOpen, setMobileHistoryOpen] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const navigateToScreen = useCallback((
    nextScreen: StudioScreen,
    generationId = selectedId,
    replace = false,
  ) => {
    const path = pathForScreen(nextScreen, generationId);
    if (path === pathname) return;
    if (replace) router.replace(path, { scroll: false });
    else router.push(path, { scroll: false });
  }, [pathname, router, selectedId]);

  useEffect(() => {
    if (authStatus === "loading" || authStatus === "error") return;
    if (user && route.screen === "login") {
      router.replace("/projects", { scroll: false });
      return;
    }
    if (route.generationId && !user) {
      if (authStatus === "anonymous") {
        authRedirectGenerationIdRef.current = route.generationId;
        router.replace("/", { scroll: false });
      }
      return;
    }
    if (!route.valid) {
      router.replace(user ? "/projects" : "/", { scroll: false });
    }
  }, [
    authStatus,
    pathname,
    route.generationId,
    route.screen,
    route.valid,
    router,
    user,
  ]);

  const selected = useMemo(
    () => {
      if (route.generationId) {
        return (
          generations.find((generation) => generation.id === route.generationId) ??
          null
        );
      }
      return (
        generations.find((generation) => generation.id === selectedId) ??
        generations[0] ??
        null
      );
    },
    [generations, route.generationId, selectedId],
  );
  const selectedPayload =
    selected && isPayload(selected.payload) ? selected.payload : null;
  const currentEditingPayload =
    editingGenerationId === selected?.id ? editingPayload : null;
  const selectedTemplate =
    VIDEO_TEMPLATES.find((template) => template.id === selectedTemplateId) ??
    VIDEO_TEMPLATES[0];
  const selectedVisualTheme =
    VISUAL_THEMES.find((theme) => theme.id === visualThemeId) ??
    VISUAL_THEMES[0];
  const displayedTemplateId =
    previewingTemplate || !selected
      ? selectedTemplateId
      : isVideoTemplateId(selected.template_id)
        ? selected.template_id
        : DEFAULT_VIDEO_TEMPLATE;
  const scriptPayload = currentEditingPayload ?? selectedPayload;
  const samplePreview = TEMPLATE_PREVIEWS[displayedTemplateId];
  const previewSceneIndex = previewingTemplate ? 0 : activeSceneIndex;
  const previewSceneCount =
    previewingTemplate || !selectedPayload
      ? 1
      : currentEditingPayload?.scenes.length ?? selectedPayload.scenes.length;
  const currentScene =
    previewingTemplate || !selectedPayload
      ? {
          text: samplePreview.text,
          duration_seconds: 4,
          background_color: samplePreview.color,
        }
      : currentEditingPayload?.scenes[activeSceneIndex] ??
        selectedPayload.scenes[0] ??
        null;
  const maxCurrentSceneDuration = Math.max(
    1,
    60 -
      (scriptPayload?.end_card?.enabled
        ? scriptPayload.end_card.duration_seconds
        : 0) -
      (scriptPayload?.scenes.reduce(
        (total, scene, index) =>
          index === activeSceneIndex ? total : total + scene.duration_seconds,
        0,
      ) ?? 0),
  );
  const videoUrl =
    selected?.status === "completed" &&
    selected.visual_theme_id === visualThemeId &&
    videoSource?.id === selected.id &&
    videoSource.themeId === visualThemeId
      ? videoSource.url
      : null;
  const previewLayer =
    currentScene?.layers?.find((layer) => layer.role === "foreground") ??
    currentScene?.layers?.[0];
  const previewAssetUrl = previewLayer
    ? assetPreviewUrls[previewLayer.asset_id]
    : undefined;
  const isCreatingFromBriefing = creating && route.screen !== "editor";
  const step = statusStep(
    isCreatingFromBriefing
      ? "writing_script"
      : previewingTemplate
        ? null
        : selected?.status ?? null,
  );
  const hasActiveGeneration = generations.some((item) =>
    activeStatuses.includes(item.status),
  );
  const canEditScript =
    !previewingTemplate &&
    Boolean(scriptPayload?.scenes.length) &&
    (selected?.status === "draft" ||
      (selected?.status === "failed" && Boolean(selectedPayload)));
  const isRendering =
    selected?.status === "rendering" ||
    selected?.status === "render_queued" ||
    renderingId === selected?.id;

  const mergeGeneration = useCallback((generation: VideoGeneration) => {
    setGenerations((current) => [
      generation,
      ...current.filter((item) => item.id !== generation.id),
    ]);
  }, []);

  const cacheAssetPreview = useCallback(
    (assetId: string, url: string) => {
      assetObjectUrls.current.set(assetId, url);
      setAssetPreviewUrls((current) => ({ ...current, [assetId]: url }));
    },
    [],
  );

  const loadGenerations = useCallback(async () => {
    const data = await apiRequest<Paginated<VideoGeneration>>(
      "/api/v1/videos/",
    );
    setGenerations((current) => {
      const routeGeneration = current.find(
        (generation) => generation.id === route.generationId,
      );
      return routeGeneration &&
        !data.results.some((generation) => generation.id === routeGeneration.id)
        ? [routeGeneration, ...data.results]
        : data.results;
    });
    setSelectedId((current) =>
      current && data.results.some((item) => item.id === current)
        ? current
        : (data.results[0]?.id ?? null),
    );
    return data.results;
  }, [route.generationId]);

  useEffect(() => {
    if (!user || route.screen === "login") return;
    const timer = window.setTimeout(() => {
      loadGenerations().catch((loadError: unknown) => {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Não foi possível carregar os teus projectos.",
        );
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [user, loadGenerations, route.screen]);

  useEffect(() => {
    if (!user) return;
    const assetIds = new Set<string>();
    for (const scene of selectedPayload?.scenes ?? []) {
      for (const layer of scene.layers ?? []) assetIds.add(layer.asset_id);
    }
    if (selectedPayload?.narration?.asset_id) {
      assetIds.add(selectedPayload.narration.asset_id);
    }
    let cancelled = false;
    for (const assetId of assetIds) {
      if (assetObjectUrls.current.has(assetId)) continue;
      fetch(`/api/v1/videos/assets/${assetId}/file/`, {
        credentials: "same-origin",
        cache: "no-store",
      })
        .then((response) => {
          if (!response.ok) throw new Error("Não foi possível carregar um ficheiro de media.");
          return response.blob();
        })
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          if (cancelled) {
            URL.revokeObjectURL(url);
            return;
          }
          cacheAssetPreview(assetId, url);
        })
        .catch((assetError: unknown) => {
          if (!cancelled) {
            setError(
              assetError instanceof Error
                ? assetError.message
                : "Não foi possível carregar um ficheiro de media.",
            );
          }
        });
    }
    return () => {
      cancelled = true;
    };
  }, [cacheAssetPreview, user, selectedPayload]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(username.trim(), password);
      const loaded = await loadGenerations();
      const requestedGenerationId =
        route.generationId ?? authRedirectGenerationIdRef.current;
      const requestedGeneration = requestedGenerationId
        ? loaded.find((generation) => generation.id === requestedGenerationId)
        : null;
      const initialGeneration = requestedGeneration ?? loaded[0];
      if (requestedGenerationId) {
        navigateToScreen("editor", requestedGenerationId, true);
      } else {
        navigateToScreen("projects", null, true);
      }
      if (initialGeneration) {
        setSelectedId(initialGeneration.id);
        setVisualThemeId(
          isVisualThemeId(initialGeneration.visual_theme_id)
            ? initialGeneration.visual_theme_id
            : DEFAULT_VISUAL_THEME,
        );
        setPreviewingTemplate(false);
        setSelectedTemplateId(
          isVideoTemplateId(initialGeneration.template_id)
            ? initialGeneration.template_id
            : DEFAULT_VIDEO_TEMPLATE,
        );
        setEditingPayload(
          isPayload(initialGeneration.payload)
            ? structuredClone(initialGeneration.payload)
            : null,
        );
        setEditingGenerationId(initialGeneration.id);
      } else {
        setPreviewingTemplate(true);
        setSelectedTemplateId(DEFAULT_VIDEO_TEMPLATE);
        setVisualThemeId(DEFAULT_VISUAL_THEME);
        setEditingPayload(null);
        setEditingGenerationId(null);
      }
      authRedirectGenerationIdRef.current = null;
      setPassword("");
    } catch (loginError) {
      setError(
        loginError instanceof Error
          ? loginError.message
          : "Não foi possível autenticar.",
      );
    } finally {
      setLoading(false);
    }
  }

  const openGenerationInEditor = useCallback((generation: VideoGeneration) => {
    setSelectedId(generation.id);
    setActiveSceneIndex(0);
    setEditingPayload(
      isPayload(generation.payload) ? structuredClone(generation.payload) : null,
    );
    setEditingGenerationId(generation.id);
    setPreviewingTemplate(false);
    setSelectedTemplateId(
      isVideoTemplateId(generation.template_id)
        ? generation.template_id
        : DEFAULT_VIDEO_TEMPLATE,
    );
    setVisualThemeId(
      isVisualThemeId(generation.visual_theme_id)
        ? generation.visual_theme_id
        : DEFAULT_VISUAL_THEME,
    );
    navigateToScreen("editor", generation.id);
  }, [navigateToScreen]);

  useEffect(() => {
    const generationId = route.generationId;
    if (!user || !generationId) return;

    let cancelled = false;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    apiRequest<VideoGeneration>(`/api/v1/videos/${generationId}/`, {
      signal: controller.signal,
    })
      .then((generation) => {
        if (cancelled) return;
        mergeGeneration(generation);
        openGenerationInEditor(generation);
        setDetailLookup(null);
      })
      .catch((lookupError: unknown) => {
        if (cancelled) return;
        if (lookupError instanceof ApiRequestError && lookupError.status === 404) {
          setDetailLookup({ id: generationId, status: "not-found" });
          return;
        }
        setDetailLookup({
          id: generationId,
          status: "error",
          message:
            lookupError instanceof DOMException &&
            lookupError.name === "AbortError"
              ? "O servidor demorou demasiado a responder."
              : lookupError instanceof Error
              ? lookupError.message
              : "Não foi possível carregar este projecto.",
        });
      })
      .finally(() => {
        window.clearTimeout(timeout);
      });

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [
    detailRetryCount,
    mergeGeneration,
    openGenerationInEditor,
    route.generationId,
    user,
  ]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user || !prompt.trim()) return;

    const submittedPrompt = prompt.trim();
    const existingIds = new Set(generations.map((generation) => generation.id));
    const requestStartedAt = Date.now();
    pendingCreationRef.current = {
      existingIds,
      prompt: submittedPrompt,
      templateId: selectedTemplateId,
      visualThemeId,
      startedAt: requestStartedAt,
    };
    setCreating(true);
    setError("");
    setNotice("");
    try {
      const created = await apiRequest<VideoGeneration>(
        "/api/v1/videos/",
        {
          method: "POST",
          body: JSON.stringify({
            prompt: submittedPrompt,
            template_id: selectedTemplateId,
            visual_theme_id: visualThemeId,
          }),
        },
      );
      mergeGeneration(created);
      openGenerationInEditor(created);
      if (created.status === "failed") {
        setError(
          created.error_message ||
            "O projecto foi guardado, mas não foi possível criar o guião.",
        );
      } else {
        setPrompt("");
        setNotice(
          created.status === "draft"
            ? "Guião criado e guardado. Revê as cenas antes de renderizar."
            : "Projecto criado. O guião está a ser preparado e aparecerá aqui quando estiver pronto.",
        );
      }
    } catch (createError) {
      const createMessage =
        createError instanceof Error
          ? createError.message
          : "Não foi possível criar o guião.";
      try {
        const latest = await apiRequest<Paginated<VideoGeneration>>(
          "/api/v1/videos/",
        );
        setGenerations(latest.results);
        const recovered = latest.results.find((generation) => {
          const createdAt = Date.parse(generation.created_at);
          return (
            !existingIds.has(generation.id) &&
            generation.prompt === submittedPrompt &&
            generation.template_id === selectedTemplateId &&
            generation.visual_theme_id === visualThemeId &&
            Number.isFinite(createdAt) &&
            createdAt >= requestStartedAt - 120_000
          );
        });
        if (recovered) {
          openGenerationInEditor(recovered);
          if (recovered.status === "failed") {
            setError(
              `O projecto foi guardado, mas o guião não ficou disponível. ${recovered.error_message || createMessage}`,
            );
          } else {
            setPrompt("");
            setNotice(
              "O projecto foi guardado e está disponível no editor, apesar de a resposta inicial ter terminado com erro.",
            );
          }
          return;
        }
        setError(createMessage);
      } catch (recoveryError) {
        const recoveryMessage =
          recoveryError instanceof Error
            ? recoveryError.message
            : "erro desconhecido";
        setError(
          `${createMessage} Não foi possível confirmar se o projecto ficou guardado (${recoveryMessage}). Consulta a biblioteca antes de tentares novamente.`,
        );
      }
    } finally {
      pendingCreationRef.current = null;
      setCreating(false);
    }
  }

  async function handleRender() {
    const payload = currentEditingPayload ?? selectedPayload;
    if (!user || !selected || !payload) return;

    setError("");
    setNotice("");
    setRenderingId(selected.id);
    mergeGeneration({
      ...selected,
      payload,
      visual_theme_id: visualThemeId,
      status: "rendering",
    });
    try {
      const rendered = await apiRequest<VideoGeneration>(
        `/api/v1/videos/${selected.id}/render/`,
        {
          method: "POST",
          body: JSON.stringify({
            payload: { ...payload, template_id: selected.template_id },
            visual_theme_id: visualThemeId,
          }),
        },
      );
      mergeGeneration(rendered);
      if (rendered.status === "failed") {
        setError(rendered.error_message || "Não foi possível renderizar o vídeo.");
      }
    } catch (renderError) {
      setError(
        renderError instanceof Error
          ? renderError.message
          : "Não foi possível iniciar a renderização.",
      );
      try {
        await loadGenerations();
      } catch {
        // Keep the original render error visible.
      }
    } finally {
      setRenderingId(null);
    }
  }

  useEffect(() => {
    if (!user || (!hasActiveGeneration && !creating)) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await loadGenerations();
        const pending = pendingCreationRef.current;
        if (!pending) return;
        const generation = latest.find((item) => {
          const createdAt = Date.parse(item.created_at);
          return (
            !pending.existingIds.has(item.id) &&
            item.prompt === pending.prompt &&
            item.template_id === pending.templateId &&
            item.visual_theme_id === pending.visualThemeId &&
            Number.isFinite(createdAt) &&
            createdAt >= pending.startedAt - 120_000
          );
        });
        if (generation) {
          pendingCreationRef.current = null;
          openGenerationInEditor(generation);
          if (generation.status === "failed") {
            setError(
              generation.error_message ||
                "O projecto foi guardado, mas não foi possível criar o guião.",
            );
          } else {
            setNotice(
              generation.status === "draft"
                ? "Projecto guardado. O guião está pronto para revisão."
                : "Projecto guardado. O guião e as imagens estão a ser preparados; podes acompanhar o estado aqui.",
            );
          }
        }
      } catch (pollError) {
        setError(
          pollError instanceof Error
            ? pollError.message
            : "Não foi possível actualizar o estado.",
        );
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [
    user,
    creating,
    hasActiveGeneration,
    loadGenerations,
    openGenerationInEditor,
  ]);

  const selectedVideoId = selected?.id;
  const selectedStatus = selected?.status;
  const selectedVisualThemeId = selected?.visual_theme_id;
  useEffect(() => {
    if (
      !user ||
      !selectedVideoId ||
      !isVisualThemeId(selectedVisualThemeId) ||
      selectedStatus !== "completed"
    )
      return;
    let cancelled = false;
    let objectUrl: string | null = null;
    fetch(`/api/v1/videos/${selectedVideoId}/file/`, {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then((response) => {
        if (!response.ok) throw new Error("Não foi possível carregar o vídeo.");
        return response.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setVideoSource({
          id: selectedVideoId,
          themeId: selectedVisualThemeId,
          url: objectUrl,
        });
      })
      .catch((videoError: unknown) => {
        if (!cancelled) {
          setError(
            videoError instanceof Error
              ? videoError.message
              : "Não foi possível carregar o vídeo.",
          );
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [user, selectedVideoId, selectedStatus, selectedVisualThemeId]);

  function chooseGeneration(generation: VideoGeneration) {
    setError("");
    setNotice("");
    openGenerationInEditor(generation);
  }

  function updateScene(index: number, patch: Partial<VideoScene>) {
    setEditingGenerationId(selected?.id ?? null);
    setEditingPayload((current) => {
      const payload = current ?? selectedPayload;
      if (!payload) return current;
      const scenes = payload.scenes.map((scene, sceneIndex) =>
        sceneIndex === index ? { ...scene, ...patch } : scene,
      );
      return {
        ...payload,
        schema_version:
          patch.layers ||
          patch.captions ||
          patch.image_treatment ||
          patch.typography_animation ||
          patch.motion_graphic
            ? 2
            : payload.schema_version,
        scenes,
      };
    });
  }

  function updateSceneTransition(
    index: number,
    type: SceneTransitionType | "",
  ) {
    setEditingGenerationId(selected?.id ?? null);
    setEditingPayload((current) => {
      const payload = current ?? selectedPayload;
      if (!payload) return current;
      const existingPlan = payload.visual_direction_plan;
      const existingScenePlan = existingPlan?.scenes.find(
        (scenePlan) => scenePlan.scene_index === index,
      );
      if (!payload.scenes[index]) return current;
      if (!type && !existingScenePlan) return payload;
      const scenes = existingPlan?.scenes ?? [];
      const nextScenePlan = type
        ? {
            ...existingScenePlan,
            scene_index: index,
            transition: { type, duration_frames: 12 },
          }
        : existingScenePlan?.camera
          ? {
              scene_index: index,
              camera: existingScenePlan.camera,
            }
          : null;
      const nextScenes = existingScenePlan
        ? scenes.flatMap((item) =>
            item.scene_index === index
              ? nextScenePlan
                ? [nextScenePlan]
                : []
              : [item],
          )
        : nextScenePlan
          ? [...scenes, nextScenePlan]
          : scenes;
      const nextPlan = {
        schema_version: 1 as const,
        theme: visualThemeId,
        scenes: nextScenes,
      };
      return {
        ...payload,
        visual_direction_plan: nextScenes.length ? nextPlan : undefined,
      };
    });
  }

  function updateNarration(
    narration: NonNullable<VideoPayload["narration"]>,
  ) {
    setEditingGenerationId(selected?.id ?? null);
    setEditingPayload((current) => {
      const payload = current ?? selectedPayload;
      return payload
        ? { ...payload, schema_version: 2, narration }
        : current;
    });
  }

  function updateEndCard(endCard: NonNullable<VideoPayload["end_card"]>) {
    setEditingGenerationId(selected?.id ?? null);
    setEditingPayload((current) => {
      const payload = current ?? selectedPayload;
      return payload
        ? { ...payload, schema_version: 2, end_card: endCard }
        : current;
    });
  }

  async function uploadMediaFile(file: File, kind: MediaKind) {
    if (!user) throw new Error("Inicia sessão para carregar ficheiros.");
    const formData = new FormData();
    formData.append("kind", kind);
    formData.append("file", file);
    const asset = await apiRequest<UploadedAsset>(
      "/api/v1/videos/assets/",
      { method: "POST", body: formData },
    );
    cacheAssetPreview(asset.id, URL.createObjectURL(file));
    return asset;
  }

  async function handleSceneAssetUpload(
    event: ChangeEvent<HTMLInputElement>,
    kind: "image" | "video",
  ) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !currentScene) return;
    if ((currentScene.layers?.length ?? 0) >= 4) {
      setError("Cada cena pode ter no máximo quatro camadas de media.");
      return;
    }
    if (kind === "video" && currentScene.layers?.some((layer) => layer.kind === "video")) {
      setError("Cada cena pode conter apenas um clip de vídeo.");
      return;
    }
    setError("");
    try {
      const asset = await uploadMediaFile(file, kind);
      updateScene(activeSceneIndex, {
        layers: [
          ...(currentScene.layers ?? []),
          {
            asset_id: asset.id,
            kind,
            role: "background",
            motion: currentScene.motion ?? "slow_zoom",
            opacity: 1,
            fit: "cover",
          },
        ],
      });
    } catch (uploadError) {
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "Não foi possível carregar o ficheiro.",
      );
    }
  }

  async function handleNarrationUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !scriptPayload) return;
    setError("");
    try {
      const asset = await uploadMediaFile(file, "audio");
      updateNarration({
        ...scriptPayload.narration,
        asset_id: asset.id,
        generate_local: false,
      });
    } catch (uploadError) {
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "Não foi possível carregar a narração.",
      );
    }
  }

  function updateTitle(title: string) {
    setEditingGenerationId(selected?.id ?? null);
    setEditingPayload((current) => {
      const payload = current ?? selectedPayload;
      return payload ? { ...payload, title } : current;
    });
  }

  async function signOut() {
    try {
      await logout();
    } catch (logoutError) {
      setError(
        logoutError instanceof Error
          ? logoutError.message
          : "Não foi possível terminar a sessão.",
      );
      return;
    }
    for (const url of assetObjectUrls.current.values()) URL.revokeObjectURL(url);
    assetObjectUrls.current.clear();
    setAssetPreviewUrls({});
    setGenerations([]);
    setSelectedId(null);
    setEditingPayload(null);
    setEditingGenerationId(null);
    setVideoSource(null);
    setError("");
    setUsername("");
    setPassword("");
    navigateToScreen("login", null, true);
  }

  const stepLabels = ["Briefing", "Guião IA", "Revisão", "Render", "Pronto"];
  const topbar = (
    <header className="topbar">
      <Link aria-label="Lume Studio — início" className="brand" href="/projects">
        <span className="brand-mark">l</span>
        <span className="brand-name">lume</span>
        <span className="brand-divider" />
        <span className="brand-product">STUDIO</span>
      </Link>
      <div className="topbar-meta">
        <span className="server-state"><span className="server-dot" /> Motor local</span>
        <span className="topbar-separator" />
        {user ? (
          <button className="account-button" onClick={signOut} type="button">
            <span className="account-avatar">{user.username[0]?.toUpperCase()}</span>
            <span className="account-name">{user.username}</span>
            <span className="account-signout">Terminar sessão</span>
          </button>
        ) : (
          <span className="private-workspace">ESPAÇO PRIVADO</span>
        )}
      </div>
    </header>
  );

  if (authStatus === "loading") {
    return (
      <main className="studio-app auth-screen">
        {topbar}
        <section className="auth-layout">
          <div className="auth-intro">
            <span className="section-eyebrow">ESTÚDIO CRIATIVO · RENDER LOCAL</span>
            <h1>A recuperar<br />a tua sessão.</h1>
          </div>
        </section>
      </main>
    );
  }

  if (!user || screen === "login") {
    return (
      <main className="studio-app auth-screen">
        {topbar}
        <section className="auth-layout">
          <div className="auth-intro">
            <span className="section-eyebrow">ESTÚDIO CRIATIVO · RENDER LOCAL</span>
            <h1>Ideias que<br />ganham forma.</h1>
            <p>Transforma um briefing num vídeo pronto para publicar, sem custos de APIs de vídeo.</p>
            <div className="auth-promise"><span>✦</span> Guião com IA <i /> Vídeo composto no teu servidor</div>
          </div>
          <form className="login-card auth-card" onSubmit={handleLogin}>
            <div className="card-heading">
              <span className="card-step">01</span>
              <div><h2>Entra no teu estúdio</h2><p>Acede aos teus projectos e continua a criar.</p></div>
            </div>
            <label className="field-label">
              Utilizador
              <input autoComplete="username" onChange={(event) => setUsername(event.target.value)} placeholder="O teu utilizador" required value={username} />
            </label>
            <label className="field-label">
              Palavra-passe
              <input autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} placeholder="A tua palavra-passe" required type="password" value={password} />
            </label>
            {(error || authError) && <div className="error-banner" role="alert">{error || authError}</div>}
            <button className="button button-primary button-wide" disabled={loading} type="submit">
              {loading ? "A autenticar…" : "Entrar"} {!loading && <span aria-hidden="true">↗</span>}
            </button>
            <p className="privacy-note">Sessão segura neste browser, válida por até 14 dias.</p>
          </form>
        </section>
      </main>
    );
  }

  if (screen === "projects") {
    return (
      <main className="studio-app">
        {topbar}
        <section className="projects-page">
          <div className="projects-page-heading">
            <div>
              <span className="section-eyebrow">O TEU ESTÚDIO</span>
              <h1>Os teus projectos</h1>
              <p>Continua de onde paraste ou começa uma nova história.</p>
            </div>
            <button className="button button-primary create-project-button" onClick={() => { setError(""); navigateToScreen("templates"); }} type="button">
              Criar vídeo <span aria-hidden="true">↗</span>
            </button>
          </div>
          {error && <div className="error-banner projects-error" role="alert"><span className="error-icon">!</span><span>{error}</span><button aria-label="Fechar mensagem" onClick={() => setError("")} type="button">×</button></div>}
          <div className="projects-page-content">
            <div className="projects-page-section-heading">
              <h2>Biblioteca</h2><span>{generations.length.toString().padStart(2, "0")} PROJECTOS</span>
            </div>
            {generations.length === 0 ? (
              <div className="library-empty">
                <span className="empty-glyph">✳</span>
                <h2>A tua próxima ideia começa aqui.</h2>
                <p>Escolhe um formato e descreve o vídeo que gostarias de criar.</p>
                <button className="button button-secondary" onClick={() => navigateToScreen("templates")} type="button">Explorar formatos <span aria-hidden="true">→</span></button>
              </div>
            ) : (
              <ul className="project-grid">
                {generations.map((generation) => (
                  <li key={generation.id}>
                    <button className="project-card" onClick={() => chooseGeneration(generation)} type="button">
                      <span className={`project-card-art project-${generation.status}`}><span>{generation.status === "completed" ? "▶" : "✳"}</span><small>{VIDEO_TEMPLATES.find((template) => template.id === generation.template_id)?.name ?? "Vídeo vertical"}</small></span>
                      <span className="project-card-copy">
                        <strong>{isPayload(generation.payload) ? generation.payload.title : generation.prompt}</strong>
                        <span>{formatDate(generation.created_at)} <i /> <span className={`project-status status-${generation.status}`}>{labels[generation.status]}</span></span>
                      </span>
                      <span className="project-card-arrow" aria-hidden="true">↗</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <footer className="projects-page-footer"><span>CRIADO LOCALMENTE</span><span>1080 × 1920 · MP4</span></footer>
        </section>
      </main>
    );
  }

  if (screen === "templates") {
    return (
      <main className="studio-app">
        {topbar}
        <section className="flow-page">
          <div className="flow-topline">
            <button className="text-button" onClick={() => navigateToScreen("projects")} type="button">← Projectos</button>
            <span>PASSO 1 DE 3</span>
          </div>
          <div className="flow-heading">
            <span className="section-eyebrow">ESCOLHE UM PONTO DE PARTIDA</span>
            <h1>Que história queres contar?</h1>
            <p>Escolhe a estrutura da história. A identidade visual é escolhida separadamente no próximo passo.</p>
          </div>
          <div className="template-flow-grid">
            {VIDEO_TEMPLATES.map((template) => (
              <button
                aria-pressed={selectedTemplateId === template.id}
                className={`template-flow-card template-${template.id}${selectedTemplateId === template.id ? " is-selected" : ""}`}
                key={template.id}
                onClick={() => setSelectedTemplateId(template.id)}
                type="button"
              >
                <TemplateArtwork templateId={template.id} />
                <span className="template-flow-copy">
                  <span className="template-category">{template.category}</span>
                  <strong>{template.name}</strong>
                  <span>{template.description}</span>
                  <small>{template.hook}</small>
                </span>
                <span aria-hidden="true" className="template-flow-check">{selectedTemplateId === template.id ? "✓" : "＋"}</span>
              </button>
            ))}
          </div>
          <div className="flow-actions">
            <span className="selected-format-note"><strong>{selectedTemplate.name}</strong><i /> Estrutura narrativa</span>
            <button className="button button-primary" onClick={() => navigateToScreen("visual-themes")} type="button">Escolher identidade visual <span aria-hidden="true">→</span></button>
          </div>
        </section>
      </main>
    );
  }

  if (screen === "visual-themes") {
    return (
      <main className="studio-app">
        {topbar}
        <section className="flow-page visual-themes-page">
          <div className="flow-topline">
            <button className="text-button" onClick={() => navigateToScreen("templates")} type="button">← Formatos</button>
            <span>PASSO 2 DE 3</span>
          </div>
          <div className="flow-heading">
            <span className="section-eyebrow">IDENTIDADE VISUAL</span>
            <h1>Escolhe como a história se sente.</h1>
            <p>O guião mantém-se. O tema define o tratamento visual, a tipografia e o movimento do vídeo.</p>
          </div>
          <ThemePicker selectedThemeId={visualThemeId} onSelect={setVisualThemeId} />
          <div className="flow-actions">
            <span className="selected-format-note"><strong>{selectedVisualTheme.name}</strong><i /> {selectedVisualTheme.motion}</span>
            <button className="button button-primary" onClick={() => navigateToScreen("briefing")} type="button">Continuar para o briefing <span aria-hidden="true">→</span></button>
          </div>
        </section>
      </main>
    );
  }

  if (screen === "briefing") {
    return (
      <main className="studio-app">
        {topbar}
        <section className="flow-page briefing-page">
          <div className="flow-topline">
            <button className="text-button" onClick={() => navigateToScreen("visual-themes")} type="button">← Tema visual</button>
            <span>PASSO 3 DE 3</span>
          </div>
          <div className="briefing-flow-layout">
            <div className="briefing-flow-main">
              <span className="section-eyebrow">O PONTO DE PARTIDA</span>
              <h1>Conta-nos a tua ideia.</h1>
              <p>Não precisa de estar perfeita. O agente ajuda a transformá-la num guião claro.</p>
              {error && <div className="error-banner" role="alert"><span className="error-icon">!</span><span>{error}</span><button aria-label="Fechar mensagem" onClick={() => setError("")} type="button">×</button></div>}
              <form className="briefing-card briefing-flow-card" onSubmit={handleCreate}>
                <label className="briefing-label" htmlFor="video-brief">
                  O teu briefing <span>{prompt.length} / 2000</span>
                </label>
                <textarea
                  autoFocus
                  id="video-brief"
                  maxLength={2000}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder="Ex.: Quero apresentar a nossa pastelaria artesanal a pessoas do bairro. Destaca o pão de fermentação lenta e termina com um convite para nos visitar."
                  rows={9}
                  value={prompt}
                />
                <div className="briefing-examples"><span>Inclui, se puderes:</span><span>O que ofereces</span><span>Para quem</span><span>Tom de voz</span></div>
                <div className="briefing-flow-actions">
                  <button className="text-button" onClick={() => navigateToScreen("visual-themes")} type="button">Voltar ao tema</button>
                  <button className="button button-primary" disabled={creating || !prompt.trim()} type="submit">
                    {creating ? <><span className="button-spinner" /> A criar projecto</> : <>Criar guião <span aria-hidden="true">↗</span></>}
                  </button>
                </div>
              </form>
              {creating && <div aria-live="polite" className="agent-presence"><span className="agent-avatar">✦</span><span><strong>A preparar o teu projecto</strong><small>Estamos a criar o guião e as imagens. Esta etapa pode demorar alguns minutos.</small></span><span className="typing-indicator"><i /><i /><i /></span></div>}
            </div>
            <aside className="briefing-summary">
              <span className="section-eyebrow">DIRECÇÃO CRIATIVA</span>
              <div className="briefing-summary-art"><TemplateArtwork templateId={selectedTemplateId} /></div>
              <h2>{selectedTemplate.name}</h2>
              <p>{selectedTemplate.description}</p>
              <div><span>ESTRUTURA</span><strong>{selectedTemplate.hook}</strong></div>
              <div className="briefing-theme-summary">
                <ThemeArtwork themeId={visualThemeId} />
                <span><small>TEMA VISUAL</small><strong>{selectedVisualTheme.name}</strong></span>
              </div>
              <small>Podes rever e editar o guião antes de renderizar.</small>
            </aside>
          </div>
        </section>
      </main>
    );
  }

  if (route.generationId && !selected) {
    const lookup =
      detailLookup?.id === route.generationId ? detailLookup : null;
    return (
      <main className="studio-app auth-screen">
        {topbar}
        <section className="library-empty">
          <span className="empty-glyph">
            {lookup?.status === "not-found" || lookup?.status === "error"
              ? "!"
              : "…"}
          </span>
          <h1>
            {lookup?.status === "not-found"
              ? "Projecto não encontrado."
              : lookup?.status === "error"
                ? "Não foi possível carregar o projecto."
                : "A carregar o projecto."}
          </h1>
          <p>
            {lookup?.status === "not-found"
              ? "Este projecto não existe ou não está disponível na tua conta."
              : lookup?.status === "error"
                ? lookup.message
                : "Estamos a recuperar os dados guardados."}
          </p>
          {lookup?.status === "error" && user ? (
            <button
              className="button button-secondary"
              onClick={() => {
                setDetailLookup(null);
                setDetailRetryCount((count) => count + 1);
              }}
              type="button"
            >
              Tentar novamente <span aria-hidden="true">↻</span>
            </button>
          ) : lookup?.status === "not-found" ? (
            <button
              className="button button-secondary"
              onClick={() => navigateToScreen("projects")}
              type="button"
            >
              Voltar aos projectos <span aria-hidden="true">→</span>
            </button>
          ) : null}
        </section>
      </main>
    );
  }

  return (
    <main className="studio-app editor-screen">
      {topbar}
      {error && (
        <div className="editor-error-toast" role="alert">
          <span className="error-icon">!</span>
          <span>{error}</span>
          <button aria-label="Fechar mensagem" onClick={() => setError("")} type="button">×</button>
        </div>
      )}
      {notice && (
        <div className="editor-notice" role="status">
          <span aria-hidden="true">✓</span>
          <span>{notice}</span>
          <button aria-label="Fechar mensagem" onClick={() => setNotice("")} type="button">×</button>
        </div>
      )}
      <div className="studio-layout">
        <aside
          aria-label="Briefing e projectos"
          className={`creative-sidebar${user ? " is-authenticated" : ""}`}
          id="briefing"
        >
          <div className="sidebar-intro">
            <span className="section-eyebrow">ESTÚDIO CRIATIVO <span>01 / 03</span></span>
            <h1>Ideias que<br />ganham forma.</h1>
            <p>Transforma um briefing num vídeo pronto para publicar.</p>
          </div>

          {!user ? (
            <form className="login-card" onSubmit={handleLogin}>
              <div className="card-heading">
                <span className="card-step">01</span>
                <div>
                  <h2>Entra no teu estúdio</h2>
                  <p>Acede às tuas criações.</p>
                </div>
              </div>
              <label className="field-label">
                Utilizador
                <input
                  autoComplete="username"
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="O teu utilizador"
                  required
                  value={username}
                />
              </label>
              <label className="field-label">
                Palavra-passe
                <input
                  autoComplete="current-password"
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="A tua palavra-passe"
                  required
                  type="password"
                  value={password}
                />
              </label>
              <button className="button button-primary button-wide" disabled={loading} type="submit">
                {loading ? "A autenticar…" : "Entrar"}
                {!loading && <span aria-hidden="true">↗</span>}
              </button>
              <p className="privacy-note">A sessão permanece apenas neste browser.</p>
            </form>
          ) : (
            <>
              <div className="briefing-heading">
                <span className="step-index">01</span>
                <div>
                  <h2>Novo vídeo</h2>
                  <p>Começa com o resultado que queres alcançar.</p>
                </div>
              </div>
              <fieldset className="template-picker">
                <legend>
                  <span>Escolhe um formato</span>
                  <span>5 FORMATOS</span>
                </legend>
                <div className="template-options">
                  {VIDEO_TEMPLATES.map((template) => (
                    <button
                      aria-pressed={selectedTemplateId === template.id}
                      className={`template-option template-${template.id}${selectedTemplateId === template.id ? " is-selected" : ""}`}
                      key={template.id}
                      onClick={() => {
                        setSelectedTemplateId(template.id);
                        setPreviewingTemplate(true);
                      }}
                      type="button"
                    >
                      <TemplateArtwork templateId={template.id} />
                      <span className="template-option-details">
                        <span className="template-option-top">
                          <span className="template-category">{template.category}</span>
                          {selectedTemplateId === template.id && (
                            <span aria-hidden="true" className="template-selected-mark">✓</span>
                          )}
                        </span>
                        <strong>{template.name}</strong>
                        <span className="template-description">{template.description}</span>
                        <span className="template-hook">{template.hook}</span>
                      </span>
                    </button>
                  ))}
                </div>
                <p className="template-note">
                  <span aria-hidden="true">✦</span>
                  <span><strong>{selectedTemplate.hook}</strong> · {selectedTemplate.description}</span>
                </p>
              </fieldset>
              <form className="briefing-card" onSubmit={handleCreate}>
                <label className="briefing-label" htmlFor="video-brief">
                  O teu briefing
                  <span>IDEIA, PÚBLICO, TOM, OBJECTIVO</span>
                </label>
                <textarea
                  id="video-brief"
                  maxLength={2000}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder="Ex.: Quero apresentar a nossa pastelaria artesanal a pessoas do bairro. Destaca o pão de fermentação lenta e termina com um convite para nos visitar."
                  rows={6}
                  value={prompt}
                />
                <div className="briefing-examples">
                  <span>Uma boa ideia inclui</span>
                  <span>O que vendes</span>
                  <span>Para quem</span>
                  <span>Tom de voz</span>
                </div>
                <div className="briefing-actions">
                  <span className="character-count">{prompt.length} / 2000</span>
                  <button
                    className="button button-primary"
                    disabled={creating || !prompt.trim()}
                    type="submit"
                  >
                    {creating ? (
                      <><span className="button-spinner" /> A criar projecto</>
                    ) : (
                      <>Criar guião <span aria-hidden="true">↗</span></>
                    )}
                  </button>
                </div>
              </form>

              {creating && (
                <div aria-live="polite" className="agent-presence">
                  <span className="agent-avatar"><span>✦</span></span>
                  <span>
                    <strong>A preparar o teu projecto</strong>
                    <small>A criar o guião e as imagens. Esta etapa pode demorar alguns minutos.</small>
                  </span>
                  <span className="typing-indicator"><i /><i /><i /></span>
                </div>
              )}

              <section aria-label="Histórico de projectos" className="projects-section">
                <div className="projects-heading">
                  <div>
                    <span className="section-eyebrow">BIBLIOTECA</span>
                    <h2>Os teus projectos</h2>
                  </div>
                  <div className="projects-heading-actions">
                    <span className="project-count">{generations.length.toString().padStart(2, "0")}</span>
                    <button
                      aria-expanded={mobileHistoryOpen}
                      aria-label={mobileHistoryOpen ? "Ocultar projectos" : "Mostrar projectos"}
                      className="history-toggle"
                      onClick={() => setMobileHistoryOpen((open) => !open)}
                      type="button"
                    >
                      <span>{mobileHistoryOpen ? "Fechar" : "Ver todos"}</span>
                      <span aria-hidden="true">{mobileHistoryOpen ? "−" : "+"}</span>
                    </button>
                  </div>
                </div>
                <div className={`projects-content${mobileHistoryOpen ? " is-open" : ""}`}>
                  {generations.length === 0 ? (
                    <div className="projects-empty">
                      <span className="empty-glyph">↳</span>
                      <span>Os teus projectos vão aparecer aqui.</span>
                    </div>
                  ) : (
                    <ul className="project-list">
                      {generations.map((generation) => (
                        <li key={generation.id}>
                          <button
                            aria-current={selected?.id === generation.id ? "true" : undefined}
                            className={`project-row${selected?.id === generation.id ? " is-selected" : ""}`}
                            onClick={() => {
                              chooseGeneration(generation);
                              setMobileHistoryOpen(false);
                            }}
                            type="button"
                          >
                            <span className={`project-thumb project-${generation.status}`}>
                              {generation.status === "completed" ? "▶" : "✳"}
                            </span>
                            <span className="project-copy">
                              <span className="project-title">
                                {isPayload(generation.payload)
                                  ? generation.payload.title
                                  : generation.prompt}
                              </span>
                              <span className="project-date">{formatDate(generation.created_at)}</span>
                            </span>
                            <span className={`project-status status-${generation.status}`}>
                              {labels[generation.status]}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </section>
            </>
          )}

          {error && (
            <div className="error-banner" role="alert">
              <span className="error-icon">!</span>
              <span>{error}</span>
              <button aria-label="Fechar mensagem" onClick={() => setError("")} type="button">×</button>
            </div>
          )}
          <footer className="sidebar-footer">
            <span>CRIADO LOCALMENTE</span><span>1080 × 1920</span>
          </footer>
        </aside>

        <section aria-label="Área de edição do vídeo" className="editor-workspace">
          <div className="workspace-toolbar">
            <div className="breadcrumb">
              <button className="text-button editor-back" onClick={() => navigateToScreen("projects")} type="button">← Projectos</button>
              <span className="breadcrumb-slash">/</span>
              <strong>{selected ? (selectedPayload?.title || "Novo projecto") : "NOVO PROJECTO"}</strong>
            </div>
            <div className="toolbar-right">
              <span className="save-state"><span /> Guardado automaticamente</span>
              <span className="aspect-badge"><span /> VERTICAL · 9:16</span>
            </div>
          </div>

          <div className="creation-steps" aria-label="Etapas da criação">
            {stepLabels.map((label, index) => {
              const isDone = step > index;
              const isActive = step === index;
              return (
                <div className={`creation-step${isDone ? " is-done" : ""}${isActive ? " is-active" : ""}`} key={label}>
                  <StepMark done={isDone} active={isActive && (isCreatingFromBriefing || activeStatuses.includes(selected?.status ?? "draft"))} />
                  <span>{label}</span>
                  {index < stepLabels.length - 1 && <span aria-hidden="true" className="step-connector" />}
                </div>
              );
            })}
          </div>

          <div className="editor-grid">
            <section aria-label="Pré-visualização" className="preview-column" id="preview">
              <div className="preview-heading">
                <div>
                  <span className="section-eyebrow">CANVAS DE VÍDEO</span>
                  <h2>
                    {previewingTemplate || !selectedPayload
                      ? samplePreview.title
                      : selectedPayload.title}
                  </h2>
                </div>
                <div className="preview-meta">
                  <span className={`template-preview-badge template-badge-${displayedTemplateId}`}>
                    Formato narrativo
                  </span>
                  <span className="resolution-label">1080 × 1920 <i /> MP4</span>
                </div>
              </div>

              <div className="preview-stage">
                <div className="canvas-aura" />
                <div className="phone-shell">
                  {videoUrl && !previewingTemplate ? (
                    <video className="video-player" controls key={videoUrl} playsInline src={videoUrl} />
                  ) : currentScene ? (
                    <div className={`scene-preview template-preview-${displayedTemplateId} theme-preview-${visualThemeId}`} style={{ backgroundColor: currentScene.background_color }}>
                      {previewAssetUrl && previewLayer?.kind === "video" ? (
                        <video
                          aria-hidden="true"
                          autoPlay
                          className="scene-media-preview"
                          loop
                          muted
                          playsInline
                          src={previewAssetUrl}
                          style={{
                            filter: imageTreatmentFilter(currentScene.image_treatment),
                            objectFit: previewLayer.fit,
                          }}
                        />
                      ) : previewAssetUrl ? (
                        <Image
                          alt=""
                          className="scene-media-preview"
                          fill
                          src={previewAssetUrl}
                          style={{
                            filter: imageTreatmentFilter(currentScene.image_treatment),
                            objectFit: previewLayer?.fit ?? "cover",
                          }}
                          unoptimized
                        />
                      ) : null}
                      <div className="scene-grain" />
                      <div className="scene-safe-label"><span>{previewingTemplate ? "EXEMPLO DE ESTILO" : "PREVIEW"}</span><span>{String(previewSceneIndex + 1).padStart(2, "0")} / {String(previewSceneCount).padStart(2, "0")}</span></div>
                      <div className="scene-copy">
                        <span className="scene-tag">{getPreviewLabel(displayedTemplateId, previewSceneIndex, previewSceneCount)}</span>
                        <strong>{currentScene.text}</strong>
                        <span className="scene-progress"><i /></span>
                      </div>
                      <div className="scene-bottom"><span>@teu_negocio</span><span>✦</span></div>
                    </div>
                  ) : (
                    <div className="canvas-empty">
                      <div className="canvas-empty-art"><span>IDEIA</span><b>✳</b><span>EM MOVIMENTO</span></div>
                      <span className="canvas-empty-kicker">O TEU CANVAS VERTICAL</span>
                      <strong>Uma história<br />está prestes a começar.</strong>
                      <span className="canvas-empty-copy">Escreve um briefing para ver o teu guião ganhar forma.</span>
                      <span className="scene-bottom"><span>lume.studio</span><span>✦</span></span>
                    </div>
                  )}
                  {isRendering && (
                    <div aria-live="polite" className="rendering-overlay">
                      <span className="render-orbit"><i /></span>
                      <span className="rendering-kicker">A CRIAR O TEU VÍDEO</span>
                      <strong>O guião está em movimento.</strong>
                      <span>O Remotion está a compor cada frame no teu servidor.</span>
                    </div>
                  )}
                </div>
                <div className="preview-underbar">
                  <span className={`live-status status-${selected?.status ?? "idle"}`}><i /> {videoSource && selected?.status === "completed" && visualThemeId !== selected.visual_theme_id ? "Pré-visualização do novo tema" : previewingTemplate ? "Pré-visualização do formato" : selected ? labels[selected.status] : "À espera do briefing"}</span>
                  <span className="local-render-label">✦ RENDER LOCAL</span>
                </div>
              </div>
            </section>

            <aside aria-label="Guião e fluxo de criação" className="inspector-column" id="script">
              <section className="workflow-card">
                <div className="inspector-heading">
                  <div>
                    <span className="section-eyebrow">O PROCESSO</span>
                    <h2>Da ideia ao vídeo</h2>
                  </div>
                  <span className="workflow-sparkle">✳</span>
                </div>
                <ol className="workflow-list">
                  {[
                    ["Briefing recebido", "O teu objectivo orienta a história."],
                    ["Guião criado com IA", "Estrutura, ritmo e mensagem."],
                    ["Revisão criativa", "Tu decides o que vai para o vídeo."],
                    ["Render no servidor", "Frames compostos localmente."],
                  ].map(([title, detail], index) => {
                    const itemStep = index + 1;
                    const done =
                      step > itemStep ||
                      (selected?.status === "completed" && itemStep <= 4);
                    const active =
                      step === itemStep && selected?.status !== "failed";
                    return (
                      <li className={`${done ? "is-done" : ""}${active ? " is-current" : ""}`} key={title}>
                        <span className="workflow-node">{done ? "✓" : String(itemStep).padStart(2, "0")}</span>
                        <span className="workflow-copy"><strong>{title}</strong><small>{detail}</small></span>
                        {active && <span className="workflow-pulse" />}
                      </li>
                    );
                  })}
                </ol>
                {selected?.status === "failed" && (
                  <div className="workflow-error">
                    <span>!</span>{selected.error_message || "Esta etapa não foi concluída."}
                  </div>
                )}
              </section>

              {previewingTemplate ? (
                <section className="template-detail-card">
                  <span className="section-eyebrow">FORMATO SELECCIONADO</span>
                  <div className="template-detail-heading">
                    <span className={`template-detail-icon template-detail-${selectedTemplateId}`}>
                      {VIDEO_TEMPLATES.findIndex((template) => template.id === selectedTemplateId) + 1}
                    </span>
                    <div>
                      <h2>{selectedTemplate.name}</h2>
                      <span>{selectedTemplate.category} · 9:16</span>
                    </div>
                  </div>
                  <p>{selectedTemplate.description}</p>
                  <div className="template-detail-structure">
                    <span>ESTRUTURA NARRATIVA</span>
                    <strong>{selectedTemplate.hook}</strong>
                  </div>
                  <div className="template-detail-footnote">
                    O exemplo no canvas ilustra o estilo visual. O agente adapta o texto ao teu briefing.
                  </div>
                </section>
              ) : canEditScript && scriptPayload ? (
                <section aria-label="Revisão do guião" className="script-card">
                  <div className="script-heading">
                    <div>
                      <span className="section-eyebrow">02 — REVISÃO CRIATIVA</span>
                      <h2>O teu guião</h2>
                    </div>
                    <span className="scene-count">{scriptPayload.scenes.length} {scriptPayload.scenes.length === 1 ? "CENA" : "CENAS"}</span>
                  </div>
                  {selected?.asset_pipeline_message && (
                    <div className="asset-pipeline-message" role="status">
                      <span aria-hidden="true">✦</span>
                      {selected.asset_pipeline_message}
                    </div>
                  )}
                  <label className="title-field">
                    <span>TÍTULO DO VÍDEO</span>
                    <input
                      maxLength={100}
                      onChange={(event) => updateTitle(event.target.value)}
                      value={scriptPayload.title}
                    />
                  </label>
                  <div className="scene-list">
                    {scriptPayload.scenes.map((scene, index) => (
                      <button
                        aria-pressed={activeSceneIndex === index}
                        className={`scene-row${activeSceneIndex === index ? " is-current" : ""}`}
                        key={`${selected?.id}-${index}`}
                        onClick={() => setActiveSceneIndex(index)}
                        type="button"
                      >
                        <span className="scene-number">{String(index + 1).padStart(2, "0")}</span>
                        <span className="scene-row-copy">
                          <span>{scene.text}</span>
                          <small>{scene.duration_seconds}s · CENA {String(index + 1).padStart(2, "0")}</small>
                        </span>
                        <span aria-hidden="true" className="scene-swatch" style={{ backgroundColor: scene.background_color }} />
                      </button>
                    ))}
                  </div>
                  {currentScene && (
                    <div className="scene-edit">
                      <label className="scene-text-label">
                        TEXTO NO ECRÃ
                        <textarea
                          maxLength={140}
                          onChange={(event) => updateScene(activeSceneIndex, { text: event.target.value })}
                          rows={3}
                          value={currentScene.text}
                        />
                      </label>
                      <div className="scene-edit-footer">
                        <label className="duration-control">
                          DURAÇÃO
                          <input
                            min={1}
                            max={maxCurrentSceneDuration}
                            onChange={(event) => {
                              const seconds = event.currentTarget.valueAsNumber;
                              if (Number.isSafeInteger(seconds) && seconds >= 1) {
                                if (seconds <= maxCurrentSceneDuration) {
                                  updateScene(activeSceneIndex, {
                                    duration_seconds: seconds,
                                  });
                                } else {
                                  setError(
                                    "A duração total do vídeo não pode exceder 60 segundos.",
                                  );
                                }
                              }
                            }}
                            step={1}
                            type="number"
                            value={currentScene.duration_seconds}
                          />
                        </label>
                        <label className="color-control">
                          <span>COR DE FUNDO</span>
                          <input
                            aria-label="Cor de fundo da cena"
                            onChange={(event) => updateScene(activeSceneIndex, { background_color: event.target.value })}
                            type="color"
                            value={currentScene.background_color}
                          />
                        </label>
                        <label className="duration-control scene-transition-control">
                          TRANSIÇÃO DE ENTRADA
                          <select
                            onChange={(event) =>
                              updateSceneTransition(
                                activeSceneIndex,
                                event.target.value as SceneTransitionType | "",
                              )
                            }
                            value={
                              scriptPayload?.visual_direction_plan?.scenes.find(
                                (scenePlan) =>
                                  scenePlan.scene_index === activeSceneIndex,
                              )?.transition?.type ?? ""
                            }
                          >
                            <option value="">Padrão actual</option>
                            <option value="cut">Corte</option>
                            <option value="fade">Fade</option>
                            <option value="wipe_left">Wipe da esquerda</option>
                            <option value="wipe_right">Wipe da direita</option>
                          </select>
                        </label>
                        <label className="duration-control">
                          TRATAMENTO DE IMAGEM
                          <select
                            onChange={(event) =>
                              updateScene(activeSceneIndex, {
                                image_treatment: event.target.value as VideoScene["image_treatment"],
                              })
                            }
                            value={currentScene.image_treatment ?? "natural"}
                          >
                            <option value="natural">Natural</option>
                            <option value="warm">Quente</option>
                            <option value="cool">Frio</option>
                            <option value="monochrome">Monocromático</option>
                            <option value="film">Filme</option>
                          </select>
                        </label>
                        <label className="duration-control">
                          ANIMAÇÃO TIPOGRÁFICA
                          <select
                            onChange={(event) =>
                              updateScene(activeSceneIndex, {
                                typography_animation: event.target.value as VideoScene["typography_animation"],
                              })
                            }
                            value={currentScene.typography_animation ?? (visualThemeId === "kinetic_editorial" ? "word_reveal" : "fade_up")}
                          >
                            <option value="fade_up">Fade para cima</option>
                            <option value="pop">Pop</option>
                            <option value="typewriter">Máquina de escrever</option>
                            <option value="word_reveal">Revelar palavras</option>
                            <option value="none">Sem animação</option>
                          </select>
                        </label>
                        <label className="duration-control">
                          MOTION GRAPHICS
                          <select
                            onChange={(event) =>
                              updateScene(activeSceneIndex, {
                                motion_graphic: event.target.value as VideoScene["motion_graphic"],
                              })
                            }
                            value={currentScene.motion_graphic ?? "none"}
                          >
                            <option value="none">Nenhum</option>
                            <option value="accent_line">Linha de destaque</option>
                            <option value="orbit">Órbita</option>
                            <option value="corner_frame">Moldura animada</option>
                          </select>
                        </label>
                      </div>
                      {currentScene.visual_prompt && (
                        <p className="visual-prompt-note">
                          <strong>Direcção visual sugerida:</strong>{" "}
                          {currentScene.visual_prompt}
                        </p>
                      )}
                      {scriptPayload.visual_direction && (
                        <p className="visual-prompt-note">
                          <strong>Identidade visual partilhada:</strong>{" "}
                          {scriptPayload.visual_direction}
                        </p>
                      )}
                      <div className="media-editor">
                        <div className="media-editor-heading">
                          <div>
                            <span className="section-eyebrow">ASSETS DA CENA</span>
                            <p>Adiciona imagens ou clips; o Remotion anima-os no render.</p>
                          </div>
                          <span>{currentScene.layers?.length ?? 0} / 4</span>
                        </div>
                        <div className="media-upload-actions">
                          <label className="media-upload-button">
                            Imagem
                            <input
                              accept="image/jpeg,image/png,image/webp"
                              onChange={(event) => handleSceneAssetUpload(event, "image")}
                              type="file"
                            />
                          </label>
                          <label className="media-upload-button">
                            Clip de vídeo
                            <input
                              accept="video/mp4,video/quicktime,video/webm"
                              onChange={(event) => handleSceneAssetUpload(event, "video")}
                              type="file"
                            />
                          </label>
                        </div>
                        {(currentScene.layers ?? []).map((layer, layerIndex) => (
                          <div className="media-layer-row" key={layer.asset_id}>
                            <span>{layer.kind === "video" ? "CLIP" : "IMAGEM"} · {String(layerIndex + 1).padStart(2, "0")}</span>
                            <select
                              aria-label="Movimento da camada"
                              onChange={(event) =>
                                updateScene(activeSceneIndex, {
                                  layers: currentScene.layers?.map((item, index) =>
                                    index === layerIndex
                                      ? { ...item, motion: event.target.value as VideoSceneLayer["motion"] }
                                      : item,
                                  ),
                                })
                              }
                              value={layer.motion}
                            >
                              <option value="slow_zoom">Zoom lento</option>
                              <option value="pan_left">Panorâmica esquerda</option>
                              <option value="pan_right">Panorâmica direita</option>
                              <option value="float">Flutuar</option>
                              <option value="none">Sem movimento</option>
                            </select>
                            <button
                              aria-label="Remover camada"
                              className="media-remove-button"
                              onClick={() =>
                                updateScene(activeSceneIndex, {
                                  layers: currentScene.layers?.filter(
                                    (_, index) => index !== layerIndex,
                                  ),
                                })
                              }
                              type="button"
                            >
                              Remover
                            </button>
                            {layer.source_credit && (
                              <a
                                className="media-attribution"
                                href={layer.source_url}
                                rel="noreferrer"
                                target="_blank"
                              >
                                {layer.source_credit}
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                      <div className="narration-editor">
                        <div>
                          <span className="section-eyebrow">NARRAÇÃO</span>
                          <p>Usa um áudio teu ou gera voz com Piper local, se estiver configurado.</p>
                        </div>
                        <label className="narration-toggle">
                          <input
                            checked={Boolean(currentScene && scriptPayload.narration?.generate_local)}
                            onChange={(event) =>
                              updateNarration({
                                text: scriptPayload.narration?.text ?? "",
                                generate_local: event.target.checked,
                                ...(event.target.checked
                                  ? {}
                                  : scriptPayload.narration?.asset_id
                                    ? { asset_id: scriptPayload.narration.asset_id }
                                    : {}),
                              })
                            }
                            type="checkbox"
                          />
                          Gerar voz local
                        </label>
                        {scriptPayload.narration?.generate_local ? (
                          <textarea
                            aria-label="Texto da narração"
                            maxLength={3000}
                            onChange={(event) =>
                              updateNarration({
                                ...scriptPayload.narration,
                                text: event.target.value,
                                generate_local: true,
                              })
                            }
                            placeholder="Texto a narrar"
                            rows={3}
                            value={scriptPayload.narration.text ?? ""}
                          />
                        ) : (
                          <label className="media-upload-button narration-upload">
                            {scriptPayload.narration?.asset_id
                              ? "Substituir áudio"
                              : "Carregar narração"}
                            <input
                              accept="audio/mpeg,audio/mp4,audio/wav,audio/ogg"
                              onChange={handleNarrationUpload}
                              type="file"
                            />
                          </label>
                        )}
                      </div>
                    </div>
                  )}
                  {scriptPayload && (
                    <section className="end-card-editor">
                      <div className="media-editor-heading">
                        <div>
                          <span className="section-eyebrow">ECRÃ FINAL</span>
                          <p>Adiciona uma chamada à acção no fim do vídeo.</p>
                        </div>
                        <label className="narration-toggle">
                          <input
                            checked={Boolean(scriptPayload.end_card?.enabled)}
                            onChange={(event) => {
                              const currentEndCard = scriptPayload.end_card ?? {
                                enabled: false,
                                title: "Obrigado por assistir",
                                subtitle: "Mais ideias para colocar em prática.",
                                cta: "Segue para mais",
                                duration_seconds: 3,
                              };
                              const sceneDuration = scriptPayload.scenes.reduce(
                                (total, scene) => total + scene.duration_seconds,
                                0,
                              );
                              if (event.target.checked && sceneDuration >= 60) {
                                setError("Reduz a duração das cenas para activar o ecrã final dentro do limite de 60 segundos.");
                                return;
                              }
                              updateEndCard({
                                ...currentEndCard,
                                enabled: event.target.checked,
                                duration_seconds: Math.min(
                                  currentEndCard.duration_seconds,
                                  Math.max(1, 60 - sceneDuration),
                                ),
                              });
                              setError("");
                            }}
                            type="checkbox"
                          />
                          Incluir ecrã final
                        </label>
                      </div>
                      {scriptPayload.end_card?.enabled && (
                        <div className="end-card-fields">
                          <label className="title-field">
                            TÍTULO
                            <input
                              maxLength={100}
                              onChange={(event) =>
                                updateEndCard({ ...scriptPayload.end_card!, title: event.target.value })
                              }
                              value={scriptPayload.end_card.title}
                            />
                          </label>
                          <label className="title-field">
                            MENSAGEM
                            <input
                              maxLength={180}
                              onChange={(event) =>
                                updateEndCard({ ...scriptPayload.end_card!, subtitle: event.target.value })
                              }
                              value={scriptPayload.end_card.subtitle ?? ""}
                            />
                          </label>
                          <label className="title-field">
                            CHAMADA À ACÇÃO
                            <input
                              maxLength={80}
                              onChange={(event) =>
                                updateEndCard({ ...scriptPayload.end_card!, cta: event.target.value })
                              }
                              value={scriptPayload.end_card.cta}
                            />
                          </label>
                          <label className="duration-control">
                            DURAÇÃO (SEG.)
                            <input
                              max={Math.min(
                                10,
                                60 - scriptPayload.scenes.reduce((total, scene) => total + scene.duration_seconds, 0),
                              )}
                              min={1}
                              onChange={(event) => {
                                const seconds = event.currentTarget.valueAsNumber;
                                if (Number.isSafeInteger(seconds) && seconds >= 1) {
                                  const maxDuration = Math.min(
                                    10,
                                    60 - scriptPayload.scenes.reduce((total, scene) => total + scene.duration_seconds, 0),
                                  );
                                  if (seconds <= maxDuration) {
                                    updateEndCard({ ...scriptPayload.end_card!, duration_seconds: seconds });
                                    setError("");
                                  } else {
                                    setError("A duração do ecrã final tem de respeitar o limite total de 60 segundos.");
                                  }
                                }
                              }}
                              type="number"
                              value={scriptPayload.end_card.duration_seconds}
                            />
                          </label>
                        </div>
                      )}
                    </section>
                  )}
                  <section className="render-theme-control" aria-label="Identidade visual do render">
                    <div>
                      <span className="section-eyebrow">IDENTIDADE VISUAL</span>
                      <p>O tema pode mudar sem alterar o teu guião.</p>
                    </div>
                    <ThemePicker
                      compact
                      onSelect={setVisualThemeId}
                      selectedThemeId={visualThemeId}
                    />
                  </section>
                  <div className="script-actions">
                    <span className="approval-note"><span>✦</span> Revê antes de renderizar.</span>
                    <button className="button button-primary render-button" disabled={isRendering} onClick={handleRender} type="button">
                      {isRendering ? <><span className="button-spinner" /> A renderizar</> : <>Aprovar e renderizar <span aria-hidden="true">↗</span></>}
                    </button>
                  </div>
                </section>
              ) : selected?.status === "completed" ? (
                <section className="delivery-card">
                  <span className="delivery-check">✓</span>
                  <div>
                    <span className="section-eyebrow">ENTREGA PRONTA</span>
                    <h2>O teu vídeo está finalizado.</h2>
                    <p>MP4 vertical · pronto para TikTok, Reels e Shorts.</p>
                  </div>
                  {videoUrl && (
                    <a className="button button-primary download-button" download={`${selectedPayload?.title || "video"}.mp4`} href={videoUrl}>
                      Descarregar MP4 <span aria-hidden="true">↓</span>
                    </a>
                  )}
                  <div className="delivery-theme-control">
                    <span className="section-eyebrow">CRIAR OUTRA VERSÃO VISUAL</span>
                    <ThemePicker
                      compact
                      onSelect={setVisualThemeId}
                      selectedThemeId={visualThemeId}
                    />
                    <button
                      className="button button-secondary"
                      disabled={isRendering || visualThemeId === selected.visual_theme_id}
                      onClick={handleRender}
                      type="button"
                    >
                      {isRendering ? "A renderizar…" : "Renderizar com este tema"}
                      <span aria-hidden="true">↗</span>
                    </button>
                  </div>
                </section>
              ) : selected?.status === "failed" && !selectedPayload ? (
                <section className="script-card awaiting-card">
                  <span className="section-eyebrow">GUIÃO NÃO DISPONÍVEL</span>
                  <h2>O projecto foi guardado, mas o guião falhou.</h2>
                  <p>{selected.error_message || "Revê o briefing e tenta criar o guião novamente."}</p>
                  <button
                    className="button button-secondary"
                    onClick={() => {
                      setError("");
                      setNotice("");
                      navigateToScreen("briefing");
                    }}
                    type="button"
                  >
                    Voltar ao briefing <span aria-hidden="true">↗</span>
                  </button>
                </section>
              ) : selected?.status === "queued" || selected?.status === "writing_script" ? (
                <section aria-live="polite" className="script-card awaiting-card">
                  <span className="awaiting-orbit"><i /></span>
                  <span className="section-eyebrow">A TRABALHAR NO GUIÃO</span>
                  <h2>Estamos a estruturar a tua ideia.</h2>
                  <p>O agente está a preparar cenas, ritmo e mensagem. A pré-visualização aparece aqui assim que o guião estiver pronto.</p>
                </section>
              ) : (
                <section className="script-card awaiting-card">
                  <span className="section-eyebrow">REVISÃO CRIATIVA</span>
                  <h2>O guião aparece aqui.</h2>
                  <p>Depois de criado, podes ajustar cada cena antes de aprovar a renderização.</p>
                  <div className="awaiting-list"><span>01 <i /> Texto de cada cena</span><span>02 <i /> Duração e cor</span><span>03 <i /> Aprovação final</span></div>
                </section>
              )}
            </aside>
          </div>
          <footer className="workspace-footer">
            <span>O TEU CONTEÚDO É TEU</span>
            <span>GUIÃO COM IA <i /> RENDERIZAÇÃO LOCAL <i /> SEM API DE VÍDEO</span>
          </footer>
        </section>
      </div>
    </main>
  );
}

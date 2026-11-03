export type VisualThemeId =
  | "cinematic_stories"
  | "kinetic_editorial"
  | "modern_product";

export type VisualTheme = {
  id: VisualThemeId;
  name: string;
  promise: string;
  description: string;
  motion: string;
  accent: string;
};

export const VISUAL_THEMES: VisualTheme[] = [
  {
    id: "cinematic_stories",
    name: "Cinematic Stories",
    promise: "Narrativa com profundidade",
    description:
      "Composição documental, imagens em profundidade e movimento contemplativo.",
    motion: "Slow push · cortes suaves",
    accent: "#d8b77c",
  },
  {
    id: "kinetic_editorial",
    name: "Kinetic Editorial",
    promise: "Ideias que prendem o olhar",
    description:
      "Tipografia de alto impacto, ritmo rápido e entradas sincronizadas por palavra.",
    motion: "Tipografia cinética · ritmo rápido",
    accent: "#c5ff49",
  },
  {
    id: "modern_product",
    name: "Modern Product",
    promise: "Design premium, sem ruído",
    description:
      "Direcção premium, espaço negativo e apresentação editorial do produto.",
    motion: "Product reveal · movimento preciso",
    accent: "#5c7563",
  },
];

export const DEFAULT_VISUAL_THEME: VisualThemeId = "cinematic_stories";

export function isVisualThemeId(value: unknown): value is VisualThemeId {
  return VISUAL_THEMES.some((theme) => theme.id === value);
}

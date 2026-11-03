export type VideoTemplateId =
  | "showcase"
  | "tutorial"
  | "before_after"
  | "quick_tips"
  | "brand_story";

export type VideoTemplate = {
  id: VideoTemplateId;
  name: string;
  category: string;
  description: string;
  hook: string;
};

export const VIDEO_TEMPLATES: VideoTemplate[] = [
  {
    id: "showcase",
    name: "Produto em destaque",
    category: "VENDER",
    description: "Apresenta benefícios e termina com um convite claro.",
    hook: "Gancho · benefícios · acção",
  },
  {
    id: "tutorial",
    name: "Tutorial rápido",
    category: "ENSINAR",
    description: "Divide um processo útil em passos simples.",
    hook: "Resultado · passos · dica",
  },
  {
    id: "before_after",
    name: "Antes e depois",
    category: "TRANSFORMAR",
    description: "Mostra uma mudança e destaca o resultado.",
    hook: "Antes · mudança · depois",
  },
  {
    id: "quick_tips",
    name: "Lista de dicas",
    category: "PARTILHAR",
    description: "Dicas accionáveis, uma ideia por cena.",
    hook: "Gancho · dicas · resumo",
  },
  {
    id: "brand_story",
    name: "História da marca",
    category: "CONECTAR",
    description: "Conta a origem e os valores do teu negócio.",
    hook: "Origem · propósito · convite",
  },
];

export const DEFAULT_VIDEO_TEMPLATE: VideoTemplateId = "showcase";

export function isVideoTemplateId(value: unknown): value is VideoTemplateId {
  return VIDEO_TEMPLATES.some((template) => template.id === value);
}

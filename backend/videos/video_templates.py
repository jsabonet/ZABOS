VIDEO_TEMPLATES = {
    "showcase": {
        "name": "Produto em destaque",
        "purpose": "Apresentar um produto, serviço ou benefício de forma directa.",
        "structure": "Comece com um gancho sobre o benefício, mostre 2 a 3 vantagens concretas e termine com uma chamada à acção simples.",
    },
    "tutorial": {
        "name": "Tutorial rápido",
        "purpose": "Ensinar um processo prático em poucos passos.",
        "structure": "Abra com o resultado prometido, explique passos curtos numa ordem útil e feche com o resultado ou uma dica final.",
    },
    "before_after": {
        "name": "Antes e depois",
        "purpose": "Mostrar uma transformação, melhoria ou resultado.",
        "structure": "Apresente a situação inicial, revele a mudança e conclua com o benefício concreto; use a sequência antes, transformação, depois.",
    },
    "quick_tips": {
        "name": "Lista de dicas",
        "purpose": "Partilhar várias dicas rápidas e fáceis de guardar.",
        "structure": "Comece por prometer dicas específicas, apresente uma dica accionável por cena e termine com um resumo ou convite para guardar.",
    },
    "brand_story": {
        "name": "História da marca",
        "purpose": "Criar ligação através da origem, valores e propósito da marca.",
        "structure": "Abra com uma ideia humana, conte a origem ou motivação, mostre o valor que guia o negócio e termine com um convite pessoal.",
    },
}

VIDEO_TEMPLATE_CHOICES = tuple(
    (template_id, template["name"])
    for template_id, template in VIDEO_TEMPLATES.items()
)

DEFAULT_VIDEO_TEMPLATE = "showcase"

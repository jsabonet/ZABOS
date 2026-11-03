VISUAL_THEMES = {
    "cinematic_stories": {
        "name": "Cinematic Stories",
        "description": "Composição documental, imagens em profundidade e movimento contemplativo.",
        "motion_style": "slow_push",
        "image_prompt_style": (
            "Restrained charcoal, deep olive, and warm amber palette; motivated practical "
            "light, deep shadows, subtle film grain, documentary lensing, atmospheric depth."
        ),
    },
    "kinetic_editorial": {
        "name": "Kinetic Editorial",
        "description": "Tipografia de alto impacto, ritmo rápido e entradas sincronizadas por palavra.",
        "motion_style": "kinetic_type",
        "image_prompt_style": (
            "Disciplined charcoal, off-white, and electric-lime accents; graphic contrast, "
            "precise geometric forms, editorial studio light, energetic framing."
        ),
    },
    "modern_product": {
        "name": "Modern Product",
        "description": "Direcção premium, espaço negativo e apresentação editorial do produto.",
        "motion_style": "product_reveal",
        "image_prompt_style": (
            "Warm neutral, graphite, and muted sage palette; premium softbox lighting, "
            "clean negative space, macro product photography, controlled reflections."
        ),
    },
}

VISUAL_THEME_CHOICES = tuple(
    (theme_id, theme["name"]) for theme_id, theme in VISUAL_THEMES.items()
)
DEFAULT_VISUAL_THEME = "cinematic_stories"

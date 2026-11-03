CAMERA_EFFECTS = {
    "slow_zoom": {
        "label": "Slow push-in",
        "media": frozenset({"image", "video"}),
        "implemented": True,
    },
    "pan_left": {
        "label": "Pan left",
        "media": frozenset({"image", "video"}),
        "implemented": True,
    },
    "pan_right": {
        "label": "Pan right",
        "media": frozenset({"image", "video"}),
        "implemented": True,
    },
    "float": {
        "label": "Floating movement",
        "media": frozenset({"image", "video"}),
        "implemented": True,
    },
    "none": {
        "label": "Static",
        "media": frozenset({"image", "video"}),
        "implemented": True,
    },
}

SCENE_TRANSITIONS = {
    "cut": {
        "label": "Cut",
        "implemented": True,
    },
    "fade": {
        "label": "Fade through black",
        "implemented": True,
    },
    "wipe_left": {
        "label": "Wipe left to right",
        "implemented": True,
    },
    "wipe_right": {
        "label": "Wipe right to left",
        "implemented": True,
    },
}

CAMERA_EFFECT_CHOICES = tuple(
    (effect_id, effect["label"])
    for effect_id, effect in CAMERA_EFFECTS.items()
    if effect["implemented"]
)
SCENE_TRANSITION_CHOICES = tuple(
    (transition_id, transition["label"])
    for transition_id, transition in SCENE_TRANSITIONS.items()
    if transition["implemented"]
)
CAMERA_INTENSITY_MIN = 0.0
CAMERA_INTENSITY_MAX = 1.0
CAMERA_INTENSITY_DEFAULT = 1.0
TRANSITION_DURATION_FRAMES_DEFAULT = 12
TRANSITION_DURATION_FRAMES_MAX = 30
VISUAL_DIRECTION_PLAN_VERSION = 1

IMAGE_TREATMENTS = {
    "natural": "Natural",
    "warm": "Warm",
    "cool": "Cool",
    "monochrome": "Monochrome",
    "film": "Film",
}

TYPOGRAPHY_ANIMATIONS = {
    "fade_up": "Fade up",
    "pop": "Pop",
    "typewriter": "Typewriter",
    "word_reveal": "Word reveal",
    "none": "None",
}

MOTION_GRAPHICS = {
    "none": "None",
    "accent_line": "Animated accent line",
    "orbit": "Orbiting graphic",
    "corner_frame": "Animated corner frame",
}

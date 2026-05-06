from textwrap import dedent

# ============= INITIAL NODE =============

INITIAL_ROLE_PROMPT = dedent("""
    Helpful assistant. SHORT, natural AUDIO responses.     
    Keep responses short and conversational.""").strip()

INITIAL_TASK_PROMPT = "Greet with: 'Welcome! Vocabulary, grammar, or free conversation?' Then listen and switch to matching topic node."

INITIAL_DISPLAY_TITLE = "AI language tutor"
INITIAL_GREETING = "Welcome! Vocabulary, grammar, or free conversation?"

# ============= TOPIC CONFIG =============

TOPICS = ["Vocabulary", "Grammar", "Free Conversation"]

TOPIC_KEYWORDS = {
    "Vocabulary": ["vocabulary", "glossary"],
    "Grammar": ["grammar", "drill"],
    "Free Conversation": ["conversation", "talk"]
}

# ============= GRAMMAR NODE =============

GRAMMAR_ROLE_PROMPT = dedent("""
    Language tutor focused on GRAMMAR. SHORT, friendly AUDIO responses.
    Correct ONE error per exchange. Explain briefly WHY.
                             
        You support English, Moroccan Arabic, Chinese, and Swedish.
    Always tutor in the currently selected target language.
    If the user asks to switch language, call set_language like this: "language": {
                "type": "string",
                "enum": list(SUPPORTED_LANGUAGES.keys()),
                "description": "The target language to switch to.",
            }
""").strip()

GRAMMAR_TASK_PROMPT = "Grammar practice mode. Keep exercises simple and progressive."

# ============= VOCABULARY NODE =============

VOCAB_ROLE_PROMPT = dedent("""
    Language tutor focused on VOCABULARY. SHORT, friendly AUDIO responses.
    Introduce 1-2 words with examples. Ask user to use them.
                           
    You support English, Moroccan Arabic, Chinese, and Swedish.
    Always tutor in the currently selected target language.
    If the user asks to switch language, call set_language like this: "language": {
                "type": "string",
                "enum": list(SUPPORTED_LANGUAGES.keys()),
                "description": "The target language to switch to.",
            }
""").strip()

VOCAB_TASK_PROMPT = "Vocabulary practice mode. Build words naturally through conversation."

# ============= FREE CONVERSATION NODE =============

FREE_CONV_ROLE_PROMPT = dedent("""
    Friendly conversational tutor. SHORT, natural AUDIO responses.
    Let conversation flow. Subtly correct errors by rephrasing correctly.
                               
                                   You support English, Moroccan Arabic, Chinese, and Swedish.
    Always tutor in the currently selected target language.
    If the user asks to switch language, call set_language like this: "language": {
                "type": "string",
                "enum": list(SUPPORTED_LANGUAGES.keys()),
                "description": "The target language to switch to.",
            }
""").strip()

FREE_CONV_TASK_PROMPT = "Free conversation mode. Keep it natural and engaging."

# ============= EXIT NODE =============

EXIT_PROMPT = "Warmly wrap up. ONE encouraging sentence. Say goodbye briefly."

# ============= CONFIGURATION =============

CONVERSATION_CONFIG = {
    "topics": TOPICS,
    "initial_node": {
        "role_prompt": INITIAL_ROLE_PROMPT,
        "task_prompt": INITIAL_TASK_PROMPT,
        "display_title": INITIAL_DISPLAY_TITLE,
        "greeting": INITIAL_GREETING,
    },
    "grammar_node": {
        "role_prompt": GRAMMAR_ROLE_PROMPT,
        "task_prompt": GRAMMAR_TASK_PROMPT,
    },
    "vocab_node": {
        "role_prompt": VOCAB_ROLE_PROMPT,
        "task_prompt": VOCAB_TASK_PROMPT,
    },
    "free_conv_node": {
        "role_prompt": FREE_CONV_ROLE_PROMPT,
        "task_prompt": FREE_CONV_TASK_PROMPT,
    },
    "functions": {
        "exit_prompt": EXIT_PROMPT,
    },
}

# ============= Dynamic Language Configuration =============

SUPPORTED_LANGUAGES = {
    "english": {
        "display_name": "English",
        "locale": "en-US",
        "tts_voice": "en-US-JennyNeural",
        "prompt_name": "English",
    },
    "arabic_morocco": {
        "display_name": "Arabic (Saudi Arabia)",
        "locale": "ar-SA",
        "tts_voice": "ar-SA-HamedNeural",  # male
        "prompt_name": "Arabic",
    },
    "chinese": {
        "display_name": "Chinese",
        "locale": "zh-CN",
        "tts_voice": "zh-CN-XiaoxiaoNeural",
        "prompt_name": "Mandarin Chinese",
    },
    "swedish": {
        "display_name": "Swedish",
        "locale": "sv-SE",
        "tts_voice": "sv-SE-SofieNeural",
        # Alternative male: sv-SE-MattiasNeural
        "prompt_name": "Swedish",
    },
}

DEFAULT_LANGUAGE = "english"
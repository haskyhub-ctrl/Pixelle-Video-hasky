"""
Module A - Script parsing and visual intent extraction.

Pipeline per script:
    1. Sentence segmentation (spaCy if installed, regex otherwise)
    2. Per-sentence extraction of subjects (nouns), actions (verbs), setting,
       time of day, weather, season and mood; context that a sentence does not
       restate (e.g. "at night" earlier in the script) is inherited
    3. Several candidate stock-search queries per scene, most specific first

Three extraction backends, picked automatically:
    - "llm":       OpenAI-compatible (OpenAI, Ollama, DeepSeek, ...) or Anthropic.
                   Required for good results on non-English scripts, since it
                   also translates to English search terms.
    - "spacy":     POS tagging with `en_core_web_sm` when installed.
    - "heuristic": dependency-free stopword / suffix rules (always available).
"""

import json
import re
import unicodedata
from typing import Iterable, Optional

from loguru import logger

from .auth_manager import LLMSettings
from .lexicon import MOOD, SEASON, SETTING, TIME_OF_DAY, WEATHER, find_values
from .models import SceneAnalysis

MAX_QUERY_WORDS = 6

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "of", "at", "by", "for",
    "with", "about", "against", "between", "into", "through", "during", "before",
    "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
    "over", "under", "again", "further", "once", "here", "there", "when", "where",
    "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "than", "too", "very", "can",
    "will", "just", "should", "now", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing", "i", "me", "my", "we",
    "our", "you", "your", "he", "him", "his", "she", "her", "it", "its", "they", "them",
    "their", "what", "which", "who", "whom", "this", "that", "these", "those", "am",
    "would", "could", "may", "might", "must", "shall", "also", "as", "while", "because",
    "until", "like", "even", "still", "yet", "every", "many", "much", "one", "get",
    "gets", "got", "let", "lets", "make", "makes", "made", "thing", "things", "way",
    "really", "always", "never", "often", "maybe", "ever", "something", "anything",
    "everything", "nothing", "someone", "everyone", "people", "lot", "lots", "day",
}

# Common visual adjectives (environment / mood / lighting)
KNOWN_DESCRIPTORS = {
    "dark", "bright", "sunny", "rainy", "cloudy", "foggy", "snowy", "busy", "quiet",
    "empty", "crowded", "modern", "old", "ancient", "futuristic", "happy", "sad",
    "angry", "calm", "peaceful", "tense", "late", "early", "urban", "rural", "green",
    "blue", "red", "golden", "warm", "cold", "slow", "fast", "beautiful", "small",
    "big", "large", "huge", "tiny", "young", "elderly", "night", "nighttime",
    "morning", "evening", "sunset", "sunrise", "aerial", "cinematic", "vintage",
    "colorful", "stressed", "tired", "excited", "lonely", "neon", "cozy", "wild",
}
ADJ_SUFFIXES = ("ful", "ous", "ive", "less", "ish", "ic", "able", "ible")
VERB_SUFFIXES = ("ing", "ed")
# Nouns that end with -ing/-ed but are not verbs
NOT_VERBS = {"building", "morning", "evening", "ceiling", "king", "ring", "thing",
             "spring", "wedding", "painting", "meeting", "bed", "red", "shed", "seed",
             "speed", "need", "feed", "weed", "sled", "ceiling", "string", "wing"}
# Base forms of common filmable verbs; 3rd-person and past forms are derived
VERB_BASES = {
    "work", "run", "walk", "code", "write", "cook", "drive", "swim", "fly", "eat",
    "drink", "read", "play", "talk", "smile", "cry", "build", "type", "study", "dance",
    "sing", "sleep", "laugh", "stare", "look", "watch", "sit", "stand", "fall", "rise",
    "celebrate", "hug", "kiss", "wait", "think", "open", "close", "climb", "jump",
    "shout", "whisper", "listen", "call", "text", "shop", "pay", "count", "sign",
    "shake", "meet", "leave", "arrive", "enter", "exit", "carry", "hold", "throw",
    "catch", "push", "pull", "fight", "train", "exercise", "paint", "draw", "teach",
    "learn", "pray", "wake", "rest", "relax", "travel", "ride", "sail", "fish",
    "plant", "harvest", "clean", "wash", "fix", "repair", "burn", "flow", "shine",
    "glow", "pour", "grow", "bloom", "explode", "crash", "chase", "hide", "search",
    "present", "discuss", "argue", "negotiate", "invest", "sell", "buy", "deliver",
}
IRREGULAR_VERBS = {
    "ran": "run", "wrote": "write", "drove": "drive", "swam": "swim", "flew": "fly",
    "ate": "eat", "drank": "drink", "sang": "sing", "slept": "sleep", "sat": "sit",
    "stood": "stand", "fell": "fall", "rose": "rise", "thought": "think",
    "met": "meet", "left": "leave", "held": "hold", "threw": "throw", "caught": "catch",
    "fought": "fight", "drew": "draw", "taught": "teach", "woke": "wake", "rode": "ride",
    "hid": "hide", "sold": "sell", "bought": "buy", "grew": "grow", "shone": "shine",
}
MORE_DESCRIPTORS = {"heavy", "light", "exhausted", "alone", "silent", "gentle",
                    "huge", "narrow", "wide", "wet", "dry", "hot", "freezing"}
# Actions that say little about what is on screen; ranked after concrete ones
VAGUE_ACTIONS = {"working", "doing", "going", "being", "getting", "having", "making",
                 "trying", "starting", "continuing", "becoming", "using", "thinking",
                 "waiting", "looking"}
NON_SUBJECTS = {"outside", "inside", "suddenly", "finally", "together", "behind",
                "around", "across", "toward", "towards", "near", "far", "away",
                "back", "another", "first", "last", "next", "moment", "little"}
PRONOUNS = {"he", "she", "they", "him", "her", "his", "them", "their", "i", "we",
            "cô ấy", "anh ấy", "ông ấy", "bà ấy", "em ấy", "họ", "nó", "cậu ấy",
            "chúng tôi", "tôi", "hắn"}


def _gerund(base: str) -> str:
    if base.endswith("ie"):
        return base[:-2] + "ying"
    if base.endswith("e") and not base.endswith("ee"):
        return base[:-1] + "ing"
    if base in {"run", "swim", "sit", "shop", "plan", "hug", "chat", "jog"}:
        return base + base[-1] + "ing"
    return base + "ing"


def verb_base(word: str) -> str:
    """Return the base form if word is a known verb (any simple inflection), else ''."""
    w = word.lower()
    if w in IRREGULAR_VERBS:
        return IRREGULAR_VERBS[w]
    candidates = [w]
    if w.endswith("ies"):
        candidates.append(w[:-3] + "y")
    if w.endswith("es"):
        candidates.append(w[:-2])
    if w.endswith("s"):
        candidates.append(w[:-1])
    if w.endswith("ed"):
        candidates += [w[:-2], w[:-1], w[:-3] if len(w) > 4 and w[-3] == w[-4] else ""]
    if w.endswith("ing"):
        candidates += [w[:-3], w[:-3] + "e", w[:-4] if len(w) > 5 and w[-4] == w[-5] else ""]
    return next((c for c in candidates if c in VERB_BASES), "")

# Abstract / narrative words -> concrete visual stock terms
VISUAL_EXPANSIONS: dict[str, list[str]] = {
    "coding": ["typing", "code", "laptop"],
    "programming": ["typing", "code", "laptop"],
    "code": ["code", "laptop"],
    "engineer": ["developer"],
    "programmer": ["developer"],
    "late": ["night"],
    "working": ["office"],
    "success": ["celebration"],
    "money": ["cash"],
    "growth": ["chart", "graph"],
    "stress": ["stressed", "person"],
    "idea": ["lightbulb"],
    "time": ["clock"],
    "teamwork": ["team", "meeting"],
    "future": ["futuristic", "technology"],
    "travel": ["airplane", "road"],
    "nature": ["forest", "landscape"],
    "city": ["cityscape"],
}

# Minimal Vietnamese -> English glossary used only when no LLM is configured.
VI_GLOSSARY: dict[str, str] = {
    "kỹ sư": "engineer", "lập trình viên": "developer", "lập trình": "coding",
    "máy tính": "computer", "máy tính xách tay": "laptop", "văn phòng": "office",
    "ban đêm": "night", "đêm": "night", "buổi sáng": "morning", "thành phố": "city",
    "biển": "sea", "bãi biển": "beach", "núi": "mountain", "rừng": "forest",
    "sông": "river", "mưa": "rain", "nắng": "sunny", "trẻ em": "children",
    "gia đình": "family", "học sinh": "student", "sinh viên": "student",
    "giáo viên": "teacher", "bác sĩ": "doctor", "bệnh viện": "hospital",
    "trường học": "school", "xe hơi": "car", "ô tô": "car", "xe máy": "motorbike",
    "đường phố": "street", "cà phê": "coffee", "nấu ăn": "cooking", "ăn": "eating",
    "chạy": "running", "đi bộ": "walking", "làm việc": "working", "học": "studying",
    "tiền": "money", "kinh doanh": "business", "cuộc họp": "meeting",
    "hạnh phúc": "happy", "buồn": "sad", "mệt mỏi": "tired", "căng thẳng": "stressed",
    "người": "person", "phụ nữ": "woman", "đàn ông": "man", "bầu trời": "sky",
    "hoàng hôn": "sunset", "bình minh": "sunrise", "công nghệ": "technology",
    "điện thoại": "smartphone", "gõ phím": "typing", "khuya": "night",
    # people
    "cô gái": "girl", "chàng trai": "young man", "cậu bé": "boy", "bé gái": "girl",
    "em bé": "baby", "người già": "elderly", "ông": "old man", "bà": "old woman",
    "mẹ": "mother", "bố": "father", "cha": "father", "vợ": "wife", "chồng": "husband",
    "bạn bè": "friends", "đồng nghiệp": "colleagues", "nhân viên": "employee",
    "nông dân": "farmer", "công nhân": "worker", "cảnh sát": "police",
    "lính cứu hỏa": "firefighter", "đầu bếp": "chef", "doanh nhân": "businessman",
    "cặp đôi": "couple", "đám đông": "crowd", "khách hàng": "customer",
    # animals / objects
    "con chó": "dog", "chó": "dog", "con mèo": "cat", "mèo": "cat", "chim": "bird",
    "cá": "fish", "trâu": "buffalo", "bò": "cow", "gà": "chicken", "ngựa": "horse",
    "xe buýt": "bus", "xe đạp": "bicycle", "tàu hỏa": "train", "máy bay": "airplane",
    "thuyền": "boat", "cầu": "bridge", "sách": "book", "bàn phím": "keyboard",
    "đồng hồ": "clock", "đèn": "lights", "cửa sổ": "window", "hoa": "flowers",
    "cây": "tree", "lửa": "fire", "nước": "water", "đồ ăn": "food", "bữa ăn": "meal",
    "tiền mặt": "cash", "biểu đồ": "chart", "màn hình": "screen",
    # places
    "nông thôn": "countryside", "làng": "village", "làng quê": "village",
    "cánh đồng": "field", "ruộng lúa": "rice field", "chợ": "market", "nhà": "house",
    "phòng khách": "living room", "phòng ngủ": "bedroom", "nhà bếp": "kitchen",
    "bếp": "kitchen", "quán cà phê": "cafe", "nhà hàng": "restaurant",
    "con đường": "road", "đường": "road", "ngõ": "alley", "hẻm": "alley",
    "sân bay": "airport", "nhà ga": "train station", "công viên": "park",
    "nhà máy": "factory", "hồ": "lake", "suối": "stream", "đồi": "hill",
    "sa mạc": "desert", "vũ trụ": "space", "lớp học": "classroom", "siêu thị": "supermarket",
    # time / weather / season
    "buổi tối": "evening", "tối": "evening", "buổi trưa": "noon", "trưa": "noon",
    "buổi chiều": "afternoon", "chiều tà": "sunset", "sáng sớm": "early morning",
    "mưa phùn": "drizzle", "bão": "storm", "tuyết": "snow", "sương mù": "fog",
    "sương": "mist", "gió": "wind", "mây": "clouds", "mùa đông": "winter",
    "mùa hè": "summer", "mùa thu": "autumn", "mùa xuân": "spring", "tết": "lunar new year",
    # actions
    "đi": "walking", "đứng": "standing", "ngồi": "sitting", "nằm": "lying",
    "ngủ": "sleeping", "uống": "drinking", "đọc": "reading", "viết": "writing",
    "nói chuyện": "talking", "cười": "laughing", "khóc": "crying", "nhảy": "dancing",
    "hát": "singing", "bơi": "swimming", "lái xe": "driving", "mua sắm": "shopping",
    "nhìn": "looking", "mỉm cười": "smiling", "ngắm": "watching", "suy nghĩ": "thinking", "chờ đợi": "waiting", "ôm": "hugging",
    "chơi": "playing", "leo núi": "hiking", "câu cá": "fishing", "trồng": "planting",
}

# Vietnamese function words dropped from the native-language query
VI_STOPWORDS = {
    "và", "là", "của", "có", "một", "những", "các", "được", "trong", "với", "cho",
    "này", "đó", "thì", "mà", "như", "khi", "để", "đã", "đang", "sẽ", "rất", "cũng",
    "lại", "vào", "ra", "lên", "xuống", "từ", "tại", "ở", "trên", "dưới", "nhưng",
    "nếu", "vì", "nên", "rồi", "còn", "đến", "không", "chỉ", "vẫn", "hay", "hoặc",
    "anh", "chị", "em", "tôi", "chúng", "ta", "họ", "nó", "mình", "ấy", "kia",
}

_VI_CHARS = re.compile(
    r"[ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵ]",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。…;])\s+|\n+")
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)


def detect_language(text: str) -> str:
    """Very small language detector: 'vi' if Vietnamese diacritics dominate, else 'en'."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    vi_hits = len(_VI_CHARS.findall(text))
    return "vi" if vi_hits / len(letters) > 0.03 else "en"


def estimate_narration_seconds(sentence: str, words_per_second: float = 2.5) -> float:
    """Rough narration length: ~150 wpm for English; Vietnamese syllables count as words."""
    words = len(re.findall(r"\w+", sentence))
    return round(max(1.0, words / words_per_second), 2)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _join(words: Iterable[str], max_words: int = MAX_QUERY_WORDS) -> str:
    out: list[str] = []
    for w in _dedupe(words):
        for part in w.split():
            if part not in out:
                out.append(part)
    return " ".join(out[:max_words])


def build_queries(scene: SceneAnalysis, max_words: int = MAX_QUERY_WORDS) -> list[str]:
    """
    Candidate queries from most specific to most general. Stock libraries match
    tags loosely, so short focused queries beat long literal ones; the ranker
    later rewards clips that also match the context words that were dropped.
    """
    subj = scene.subjects[:2]
    expanded = [e for w in subj + scene.actions[:1] for e in VISUAL_EXPANSIONS.get(w, [])]
    act = scene.actions[:1]
    place = scene.setting[:1]
    ctx = [c for c in (scene.weather, scene.time_of_day) if c][:1]
    mood = [d for d in scene.descriptors if d not in ctx][:1]
    candidates = [
        _join(subj + act + place + ctx, max_words),              # full scene
        _join(subj + place + ctx, max_words),                    # without action
        _join(subj + act + expanded, max_words),                 # subject doing thing
        _join(place + [scene.time_of_day, scene.weather, scene.season] + mood, max_words),
        _join(subj[:1] + ctx, max_words),                        # subject in context
        _join(subj[:1] + expanded[:1], max_words),
        _join(subj[:1]),
    ]
    anchors = set(subj + place + ctx) | {scene.time_of_day, scene.weather, scene.season}
    anchors = {w for a in anchors if a for w in a.split()}
    return _dedupe(c for c in candidates if c and anchors & set(c.split()))


def build_query(subjects: list[str], actions: list[str], descriptors: list[str],
                max_words: int = MAX_QUERY_WORDS) -> str:
    """Single consolidated query from bare concept lists."""
    scene = SceneAnalysis(0, "", subjects=subjects, actions=actions, descriptors=descriptors)
    queries = build_queries(scene, max_words)
    return queries[0] if queries else ""


def simplify_queries(scene: SceneAnalysis) -> list[str]:
    """Queries to try for a scene, most specific first."""
    if scene.queries:
        return _dedupe([scene.query] + scene.queries if scene.query else scene.queries)
    candidates = [
        scene.query,
        " ".join(_dedupe(scene.subjects[:3] + scene.actions[:1])),
        " ".join(_dedupe(scene.subjects[:2])),
        scene.subjects[0] if scene.subjects else "",
    ]
    if scene.query:
        candidates.append(scene.query.split()[0])
    return _dedupe(c for c in candidates if c)


def _native_query(sentence: str, max_words: int = MAX_QUERY_WORDS) -> str:
    words = [w.lower() for w in _WORD.findall(sentence)]
    return " ".join([w for w in words if w not in VI_STOPWORDS][:max_words])


def apply_context(scene: SceneAnalysis, text: str) -> None:
    """Fill setting / time / weather / season / mood from lexicon matches in text."""
    scene.setting = _dedupe(scene.setting + find_values(text, SETTING))
    scene.time_of_day = scene.time_of_day or next(iter(find_values(text, TIME_OF_DAY)), "")
    scene.weather = scene.weather or next(iter(find_values(text, WEATHER)), "")
    scene.season = scene.season or next(iter(find_values(text, SEASON)), "")
    scene.mood = _dedupe(scene.mood + find_values(text, MOOD))
    # Context words are not subjects
    context_words = set(scene.setting) | {scene.time_of_day, scene.weather, scene.season}
    context_words |= {"late", "night", "nighttime", "morning", "evening", "day"}
    for canonical in scene.setting:
        context_words |= SETTING.get(canonical, set())
    scene.subjects = [s for s in scene.subjects if s not in context_words]
    scene.descriptors = [d for d in scene.descriptors if d not in context_words]


def carry_over_context(scenes: list[SceneAnalysis]) -> None:
    """
    Scripts establish place/time once ("That night, in Hanoi...") and later
    sentences assume it. Inherit missing context from the previous scene.
    """
    for prev, scene in zip(scenes, scenes[1:]):
        changed = False
        # A pronoun ("She smiles...") refers to the previous main subject
        text = " " + " ".join(_WORD.findall(scene.sentence.lower())) + " "
        if prev.subjects and any(f" {p} " in text for p in PRONOUNS) \
                and prev.subjects[0] not in scene.subjects:
            scene.subjects.insert(0, prev.subjects[0])
            scene.inherited.append("subject")
            changed = True
        # An explicit new time of day starts a new situation: keep only the season
        new_time = scene.time_of_day and scene.time_of_day != prev.time_of_day
        if new_time and "time_of_day" not in scene.inherited:
            for dim in ("setting", "weather"):
                if not getattr(scene, dim):
                    setattr(scene, dim, [] if dim == "setting" else "")
            if not scene.season and prev.season:
                scene.season = prev.season
                scene.inherited.append("season")
            if changed and scene.source != "llm":
                scene.queries = build_queries(scene)
                scene.query = scene.queries[0] if scene.queries else scene.query
            continue
        if not scene.setting and prev.setting:
            scene.setting = list(prev.setting)
            scene.inherited.append("setting")
            changed = True
        for dim in ("time_of_day", "weather", "season"):
            if not getattr(scene, dim) and getattr(prev, dim):
                setattr(scene, dim, getattr(prev, dim))
                scene.inherited.append(dim)
                changed = True
        if changed and scene.source != "llm":
            scene.queries = build_queries(scene)
            scene.query = scene.queries[0] if scene.queries else scene.query


class ScriptParser:
    """Turns a raw script into a list of SceneAnalysis objects."""

    def __init__(self, llm: Optional[LLMSettings] = None, use_spacy: bool = True,
                 spacy_model: str = "en_core_web_sm"):
        self.llm = llm if llm and llm.enabled else None
        self._nlp = self._load_spacy(spacy_model) if use_spacy else None

    @staticmethod
    def _load_spacy(model: str):
        try:
            import spacy

            return spacy.load(model)
        except Exception as e:  # not installed or model not downloaded
            logger.debug(f"spaCy unavailable ({e}); using heuristic parser")
            return None

    # ---------- segmentation ----------

    def split_sentences(self, script: str) -> list[str]:
        """Split a script into scenes. Line breaks are always scene boundaries."""
        script = unicodedata.normalize("NFC", script or "").strip()
        if not script:
            return []
        sentences: list[str] = []
        for block in re.split(r"\n+", script):
            block = block.strip().lstrip("-*•0123456789. )").strip()
            if not block:
                continue
            if self._nlp is not None and detect_language(block) == "en":
                parts = [s.text.strip() for s in self._nlp(block).sents]
            else:
                parts = [p.strip() for p in _SENTENCE_SPLIT.split(block)]
            sentences.extend(p for p in parts if p)

        # Merge fragments too short to be a scene into the previous sentence
        merged: list[str] = []
        for s in sentences:
            if merged and len(_WORD.findall(s)) < 3:
                merged[-1] = f"{merged[-1]} {s}"
            else:
                merged.append(s)
        return merged

    # ---------- extraction ----------

    def _extract_spacy(self, sentence: str) -> tuple[list[str], list[str], list[str]]:
        doc = self._nlp(sentence)
        subjects, actions, descriptors = [], [], []
        for tok in doc:
            if tok.is_stop or not tok.is_alpha:
                continue
            if tok.pos_ in ("NOUN", "PROPN"):
                (descriptors if tok.lemma_.lower() in KNOWN_DESCRIPTORS else subjects).append(
                    tok.lemma_.lower()
                )
            elif tok.pos_ == "VERB":
                actions.append(tok.text.lower() if tok.tag_ == "VBG" else tok.lemma_.lower())
            elif tok.pos_ == "ADJ":
                descriptors.append(tok.lemma_.lower())
        return _dedupe(subjects), _dedupe(actions), _dedupe(descriptors)

    @staticmethod
    def _translate_glossary(sentence: str) -> str:
        """Longest-match glossary replacement for Vietnamese without an LLM."""
        text = sentence.lower()
        found: list[tuple[int, str]] = []
        for vi in sorted(VI_GLOSSARY, key=len, reverse=True):
            for m in re.finditer(rf"(?<!\w){re.escape(vi)}(?!\w)", text):
                found.append((m.start(), VI_GLOSSARY[vi]))
                text = text[: m.start()] + " " * len(vi) + text[m.end():]
        return " ".join(en for _, en in sorted(found))

    @staticmethod
    def _extract_heuristic(sentence: str) -> tuple[list[str], list[str], list[str]]:
        subjects, actions, descriptors = [], [], []
        for raw in _WORD.findall(sentence):
            w = raw.lower()
            if w in STOPWORDS or len(w) < 3:
                continue
            if w in NON_SUBJECTS:
                continue
            if w in KNOWN_DESCRIPTORS or w in MORE_DESCRIPTORS:
                descriptors.append(w)
            elif base := verb_base(w):
                actions.append(_gerund(base))
            elif w.endswith(VERB_SUFFIXES) and w not in NOT_VERBS:
                actions.append(w)
            elif w.endswith(ADJ_SUFFIXES) and len(w) > 5:
                descriptors.append(w)
            else:
                subjects.append(w)
        return _dedupe(subjects), _dedupe(actions), _dedupe(descriptors)

    def analyze_sentence(self, index: int, sentence: str) -> SceneAnalysis:
        """Rule-based analysis for one sentence (spaCy or heuristic)."""
        lang = detect_language(sentence)
        text, source = sentence, "heuristic"
        if lang == "vi":
            text = self._translate_glossary(sentence)
            if not text:
                logger.warning(
                    f"Scene {index}: Vietnamese text without LLM configured; "
                    "set STOCK_LLM_* for proper translation"
                )
                text = sentence
        if self._nlp is not None and lang == "en":
            subjects, actions, descriptors = self._extract_spacy(text)
            source = "spacy"
        else:
            subjects, actions, descriptors = self._extract_heuristic(text)
        scene = SceneAnalysis(
            index=index,
            sentence=sentence,
            subjects=subjects,
            actions=actions,
            descriptors=descriptors,
            language=lang,
            source=source,
        )
        # Lexicon covers both languages, so scan the original and the translation
        apply_context(scene, f"{sentence} {text}")
        scene.actions.sort(key=lambda a: a in VAGUE_ACTIONS)
        scene.queries = build_queries(scene)
        scene.query = scene.queries[0] if scene.queries else ""
        if lang != "en":
            scene.native_query = _native_query(sentence)
        return scene

    # ---------- LLM ----------

    def _analyze_llm(self, sentences: list[str]) -> list[SceneAnalysis]:
        from .llm_extractor import extract_scenes

        items = extract_scenes(self.llm, sentences)
        by_index = {int(item.get("index", -1)): item for item in items}
        scenes = []
        for i, sentence in enumerate(sentences, start=1):
            item = by_index.get(i)
            if not item:
                logger.warning(f"LLM returned nothing for scene {i}; using rule-based parser")
                scenes.append(self.analyze_sentence(i, sentence))
                continue
            def words(key):
                value = item.get(key) or []
                return _dedupe([value] if isinstance(value, str) else value)

            def one(key):
                value = item.get(key) or ""
                value = value[0] if isinstance(value, list) and value else value
                return "" if str(value).lower() in ("", "none", "unknown", "any") \
                    else str(value).lower()

            scene = SceneAnalysis(
                index=i,
                sentence=sentence,
                subjects=words("subjects"),
                actions=words("actions"),
                descriptors=words("mood"),
                setting=words("setting"),
                time_of_day=one("time_of_day"),
                weather=one("weather"),
                season=one("season"),
                mood=words("mood"),
                visual_description=str(item.get("visual_description", "")),
                avoid=words("avoid"),
                language=detect_language(sentence),
                source="llm",
            )
            llm_queries = [" ".join(str(q).split()[:MAX_QUERY_WORDS]).lower()
                           for q in item.get("queries") or [item.get("query", "")]]
            # LLM queries first, then rule-based ones as a safety net
            scene.queries = _dedupe([q for q in llm_queries if q] + build_queries(scene))
            scene.query = scene.queries[0] if scene.queries else ""
            scenes.append(scene)
        return scenes

    # ---------- public ----------

    def parse(self, script: str, use_llm: Optional[bool] = None) -> list[SceneAnalysis]:
        """
        Parse a script into scenes.

        use_llm: None = use LLM when configured; True = require it; False = never.
        """
        sentences = self.split_sentences(script)
        if not sentences:
            return []
        want_llm = self.llm is not None if use_llm is None else use_llm
        if want_llm:
            if self.llm is None:
                raise RuntimeError(
                    "LLM extraction requested but no LLM is configured "
                    "(set STOCK_LLM_BACKEND / STOCK_LLM_MODEL / STOCK_LLM_API_KEY)."
                )
            try:
                scenes = self._analyze_llm(sentences)
                carry_over_context(scenes)
                return scenes
            except Exception as e:
                if use_llm:
                    raise
                logger.warning(f"LLM extraction failed ({e}); falling back to rule-based parser")
        scenes = [self.analyze_sentence(i, s) for i, s in enumerate(sentences, start=1)]
        carry_over_context(scenes)
        return scenes


def scenes_to_json(scenes: list[SceneAnalysis]) -> str:
    return json.dumps([s.to_dict() for s in scenes], ensure_ascii=False, indent=2)

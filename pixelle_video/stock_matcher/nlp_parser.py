"""
Module A - Script parsing and visual intent extraction.

Pipeline per script:
    1. Sentence segmentation (spaCy if installed, regex otherwise)
    2. Per-sentence extraction of subjects (nouns), actions (verbs) and
       descriptors (adjectives / environment / mood)
    3. A consolidated stock-search query per scene

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
COMMON_VERBS = {"work", "works", "run", "runs", "walk", "walks", "code", "codes",
                "write", "writes", "cook", "cooks", "drive", "drives", "swim", "swims",
                "fly", "flies", "eat", "eats", "drink", "drinks", "read", "reads",
                "play", "plays", "talk", "talks", "smile", "smiles", "cry", "cries",
                "build", "builds", "type", "types", "study", "studies", "dance",
                "dances", "sing", "sings", "sleep", "sleeps", "laugh", "laughs"}

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
    "điện thoại": "smartphone", "gõ phím": "typing", "khuya": "late night",
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


def _dedupe(items: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def build_query(subjects: list[str], actions: list[str], descriptors: list[str],
                max_words: int = MAX_QUERY_WORDS) -> str:
    """Combine extracted concepts into a concise search query."""
    expanded: list[str] = []
    for word in subjects[:2] + actions[:2]:
        expanded.extend(VISUAL_EXPANSIONS.get(word, []))
    # Reserve one slot for the environment / mood descriptor
    mood = _dedupe(w for d in descriptors[:1] for w in VISUAL_EXPANSIONS.get(d, [d]))[:1]
    core = [w for w in _dedupe(subjects[:2] + actions[:2] + expanded) if w not in mood]
    return " ".join(core[: max_words - len(mood)] + mood)


def simplify_queries(scene: SceneAnalysis) -> list[str]:
    """
    Progressive fallback queries, most specific first:
        full query -> drop adjectives -> core nouns -> main noun
    """
    candidates = [
        scene.query,
        " ".join(_dedupe(scene.subjects[:3] + scene.actions[:1])),
        " ".join(_dedupe(scene.subjects[:2])),
        scene.subjects[0] if scene.subjects else "",
    ]
    # Last resort for sentences without nouns: first word of the query
    if scene.query:
        candidates.append(scene.query.split()[0])
    return _dedupe(c for c in candidates if c)


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
            if w in KNOWN_DESCRIPTORS:
                descriptors.append(w)
            elif w in COMMON_VERBS or (w.endswith(VERB_SUFFIXES) and w not in NOT_VERBS):
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
        return SceneAnalysis(
            index=index,
            sentence=sentence,
            subjects=subjects,
            actions=actions,
            descriptors=descriptors,
            query=build_query(subjects, actions, descriptors),
            language=lang,
            source=source,
        )

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
            subjects = _dedupe(item.get("subjects", []))
            actions = _dedupe(item.get("actions", []))
            descriptors = _dedupe(item.get("descriptors", []))
            query = " ".join(str(item.get("query", "")).split()[:MAX_QUERY_WORDS]).lower()
            scenes.append(
                SceneAnalysis(
                    index=i,
                    sentence=sentence,
                    subjects=subjects,
                    actions=actions,
                    descriptors=descriptors,
                    query=query or build_query(subjects, actions, descriptors),
                    language=detect_language(sentence),
                    source="llm",
                )
            )
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
                return self._analyze_llm(sentences)
            except Exception as e:
                if use_llm:
                    raise
                logger.warning(f"LLM extraction failed ({e}); falling back to rule-based parser")
        return [self.analyze_sentence(i, s) for i, s in enumerate(sentences, start=1)]


def scenes_to_json(scenes: list[SceneAnalysis]) -> str:
    return json.dumps([s.to_dict() for s in scenes], ensure_ascii=False, indent=2)

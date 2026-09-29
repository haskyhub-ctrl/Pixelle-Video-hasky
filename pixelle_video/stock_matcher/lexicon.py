"""
Visual-context vocabulary shared by the parser and the relevance ranker.

Each context dimension maps a canonical English value to the words (English
and Vietnamese) that signal it in a script, and to the words that signal it in
stock-footage metadata. CONFLICTS lists values that cannot appear together in
one shot, which lets the ranker penalise e.g. a sunny clip for a night scene.
"""

import re

# canonical -> words that indicate it (script or clip metadata)
TIME_OF_DAY: dict[str, set[str]] = {
    "night": {"night", "nighttime", "midnight", "moonlight", "moon", "dark", "neon",
              "đêm", "ban đêm", "khuya", "nửa đêm", "tối mịt"},
    "evening": {"evening", "dusk", "twilight", "tối", "buổi tối", "chạng vạng"},
    "sunset": {"sunset", "golden hour", "hoàng hôn", "chiều tà", "sundown"},
    "sunrise": {"sunrise", "dawn", "daybreak", "bình minh", "rạng sáng", "sáng sớm"},
    "morning": {"morning", "buổi sáng", "sáng"},
    "day": {"day", "daytime", "daylight", "noon", "midday", "afternoon", "ban ngày",
            "trưa", "buổi trưa", "buổi chiều"},
}

WEATHER: dict[str, set[str]] = {
    "rain": {"rain", "rainy", "raining", "rainfall", "drizzle", "downpour", "umbrella",
             "raindrops", "wet", "mưa", "cơn mưa", "mưa phùn", "trời mưa"},
    "storm": {"storm", "stormy", "thunder", "lightning", "thunderstorm", "typhoon",
              "hurricane", "bão", "giông", "sấm", "sét"},
    "snow": {"snow", "snowy", "snowing", "snowfall", "blizzard", "tuyết"},
    "fog": {"fog", "foggy", "mist", "misty", "haze", "sương", "sương mù"},
    "wind": {"wind", "windy", "breeze", "gió", "gió lớn"},
    "sunny": {"sunny", "sunshine", "sunlight", "clear sky", "blue sky", "nắng",
              "trời nắng", "nắng gắt"},
    "cloudy": {"cloudy", "overcast", "clouds", "nhiều mây", "âm u", "u ám"},
}

SEASON: dict[str, set[str]] = {
    "winter": {"winter", "wintry", "mùa đông"},
    "spring": {"spring", "blossom", "mùa xuân", "xuân", "tết"},
    "summer": {"summer", "mùa hè", "mùa hạ"},
    "autumn": {"autumn", "fall", "fallen leaves", "mùa thu"},
}

SETTING: dict[str, set[str]] = {
    "office": {"office", "workplace", "desk", "coworking", "văn phòng", "công ty"},
    "city": {"city", "cityscape", "downtown", "urban", "skyline", "skyscraper",
             "thành phố", "đô thị", "phố"},
    "street": {"street", "road", "sidewalk", "alley", "crosswalk", "traffic",
               "đường", "đường phố", "con đường", "ngõ", "hẻm"},
    "home": {"home", "house", "apartment", "living room", "bedroom", "nhà",
             "căn nhà", "phòng khách", "phòng ngủ"},
    "kitchen": {"kitchen", "cooking", "bếp", "nhà bếp"},
    "cafe": {"cafe", "coffee shop", "coffee", "quán cà phê", "cà phê", "quán"},
    "restaurant": {"restaurant", "dining", "nhà hàng"},
    "school": {"school", "classroom", "student", "trường", "trường học", "lớp học"},
    "hospital": {"hospital", "clinic", "doctor", "nurse", "bệnh viện", "phòng khám"},
    "beach": {"beach", "shore", "coast", "seaside", "waves", "bãi biển", "bờ biển"},
    "sea": {"sea", "ocean", "biển", "đại dương"},
    "mountain": {"mountain", "mountains", "hill", "peak", "núi", "đồi", "đèo"},
    "forest": {"forest", "woods", "jungle", "trees", "rừng", "khu rừng"},
    "river": {"river", "stream", "lake", "sông", "suối", "hồ"},
    "countryside": {"countryside", "rural", "village", "farm", "field", "rice field",
                    "paddy", "nông thôn", "làng", "làng quê", "quê", "cánh đồng",
                    "ruộng", "ruộng lúa"},
    "market": {"market", "bazaar", "chợ", "phiên chợ"},
    "airport": {"airport", "airplane", "sân bay", "máy bay"},
    "station": {"station", "train", "railway", "subway", "metro", "nhà ga", "tàu hỏa",
                "ga tàu"},
    "park": {"park", "garden", "công viên", "vườn"},
    "factory": {"factory", "industrial", "warehouse", "nhà máy", "xưởng", "kho"},
    "stadium": {"stadium", "gym", "sân vận động", "phòng tập"},
    "desert": {"desert", "sand dunes", "sa mạc"},
    "space": {"space", "galaxy", "stars", "planet", "vũ trụ", "thiên hà"},
}

MOOD: dict[str, set[str]] = {
    "happy": {"happy", "joy", "joyful", "smiling", "cheerful", "celebration",
              "vui", "vui vẻ", "hạnh phúc", "ăn mừng"},
    "sad": {"sad", "sadness", "lonely", "crying", "grief", "buồn", "cô đơn", "khóc"},
    "tense": {"tense", "stress", "stressed", "anxious", "pressure", "căng thẳng",
              "áp lực", "lo lắng"},
    "calm": {"calm", "peaceful", "relaxing", "serene", "quiet", "yên bình",
             "thư giãn", "tĩnh lặng"},
    "busy": {"busy", "crowded", "rush", "hectic", "đông đúc", "tấp nập", "vội vã"},
    "romantic": {"romantic", "love", "couple", "lãng mạn", "tình yêu"},
    "mysterious": {"mysterious", "mystery", "dark", "bí ẩn", "huyền bí"},
    "epic": {"epic", "dramatic", "cinematic", "hùng vĩ", "hoành tráng"},
}

# Values of the same dimension that contradict each other in one shot
CONFLICTS: dict[str, set[str]] = {
    "night": {"day", "morning", "sunny"},
    "evening": {"morning", "sunny"},
    "sunset": {"night", "morning"},
    "sunrise": {"night", "evening"},
    "morning": {"night", "evening", "sunset"},
    "day": {"night", "evening"},
    "rain": {"sunny", "snow", "desert"},
    "storm": {"sunny", "calm"},
    "snow": {"summer", "sunny", "rain", "beach", "desert"},
    "fog": {"sunny"},
    "sunny": {"rain", "storm", "snow", "night", "fog"},
    "cloudy": {"sunny"},
    "winter": {"summer", "beach"},
    "summer": {"winter", "snow"},
    "spring": {"autumn", "winter"},
    "autumn": {"spring", "summer"},
}

# Extra synonyms used to match subject / action words against clip metadata
SYNONYMS: dict[str, set[str]] = {
    "man": {"man", "men", "guy", "male", "businessman", "person"},
    "woman": {"woman", "women", "girl", "lady", "female", "businesswoman", "person"},
    "person": {"person", "people", "man", "woman", "human"},
    "child": {"child", "children", "kid", "kids", "boy", "girl", "baby"},
    "developer": {"developer", "programmer", "coder", "engineer", "coding", "programming"},
    "engineer": {"engineer", "developer", "technician", "worker"},
    "laptop": {"laptop", "computer", "notebook", "pc"},
    "computer": {"computer", "laptop", "desktop", "pc", "monitor", "screen"},
    "phone": {"phone", "smartphone", "mobile", "cellphone"},
    "car": {"car", "vehicle", "automobile", "driving", "traffic"},
    "team": {"team", "colleagues", "group", "coworkers", "meeting", "people"},
    "money": {"money", "cash", "banknotes", "dollars", "coins", "finance"},
    "typing": {"typing", "keyboard", "type", "writing"},
    "walking": {"walking", "walk", "walks", "strolling", "pedestrian"},
    "running": {"running", "run", "runs", "jogging", "runner"},
    "working": {"working", "work", "works", "job", "busy"},
    "coding": {"coding", "code", "programming", "developer", "software"},
    "celebration": {"celebration", "celebrating", "celebrate", "party", "cheering",
                    "applause", "success"},
    "dog": {"dog", "dogs", "puppy", "pet"},
    "cat": {"cat", "cats", "kitten", "pet"},
}

ALL_DIMENSIONS = {
    "time_of_day": TIME_OF_DAY,
    "weather": WEATHER,
    "season": SEASON,
    "setting": SETTING,
    "mood": MOOD,
}

_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def normalize(word: str) -> str:
    """Crude English stemmer good enough to match tags ('rainy' ~ 'rain')."""
    w = word.lower()
    for suffix in ("ing", "ies", "es", "ed", "y", "s"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return w


def find_values(text: str, table: dict[str, set[str]]) -> list[str]:
    """
    Canonical values of one dimension mentioned in text (multi-word aware),
    ordered by where they first appear.
    """
    lowered = " " + " ".join(tokenize(text)) + " "
    found: list[tuple[int, str]] = []
    for canonical, words in table.items():
        positions = [lowered.find(f" {w} ") for w in words | {canonical}]
        positions = [p for p in positions if p >= 0]
        if positions:
            found.append((min(positions), canonical))
    return [c for _, c in sorted(found)]


def expand(term: str) -> set[str]:
    """A term plus its synonyms and dimension words, normalized."""
    term = term.lower()
    words = {term} | SYNONYMS.get(term, set())
    for table in ALL_DIMENSIONS.values():
        if term in table:
            words |= {w for w in table[term] if w.isascii()}
    return {normalize(t) for w in words for t in tokenize(w)}

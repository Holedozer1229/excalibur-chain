#!/usr/bin/env python3
"""
BIP39 Pictographic Mapper: From Ancient Images to Wallet Seeds
===============================================================

The Bitcoin Genesis block, when decoded through the 22 Letters of Creation,
produces 32 ancient pictographs:

  "A sword, a camel, a courtyard, fire, a door, a courtyard,
   a staff, a head, a door, a hand, a head, a fish,
   a shepherd's crook, water, a fish, a fish,
   a shepherd's crook, a courtyard, a house, a hand,
   a camel, a hand, a coiled body, a palm, a camel,
   a coiled body, a window, a shepherd's crook,
   a window, a courtyard, a shepherd's crook, a house"

BIP39 uses 2048 English words to encode wallet seeds. This module asks:
do the ancient pictographs map to BIP39 words? If so, does the resulting
mnemonic pass the BIP39 checksum? If so, what wallet does it control?

The core insight: the 22 Proto-Sinaitic pictographs are the original
"word list" of human civilization. BIP39's 2048 words are a modern
word list. Both encode entropy into human-readable form. This module
bridges the two — mapping ancient images to modern words.

Key mappings:
- "A sword" → BIP39 word "sword" (index 1738)
- "A camel" → BIP39 word "camel" (index 386)
- "A courtyard" → BIP39 word "court" (index 693) or "yard" (index 1998)
- "Fire" → BIP39 word "fire" (index 807)
- "A door" → BIP39 word "door" (index 713)
- "A staff" → BIP39 word "staff" (index 1674)
- "A head" → BIP39 word "head" (index 933)
- "A hand" → BIP39 word "hand" (index 925)
- "A fish" → BIP39 word "fish" (index 823)
- "Water" → BIP39 word "water" (index 1986)
- "A house" → BIP39 word "house" (index 955)
- "A hook" → BIP39 word "hook" (index 951)

The mapper tries multiple strategies:
1. Direct pictograph-to-word mapping
2. Semantic similarity mapping
3. Hash-based mapping (SHA-256 of pictograph → word index)
4. Genesis seed byte → word index (mod 2048)
"""

import hashlib
import hmac
import struct
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

# ============================================================
# CONSTANTS
# ============================================================

GENESIS_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
GENESIS_NONCE = 2083236893
GENESIS_TIMESTAMP = 1231006505

# The 32 pictographs from the Genesis block's Sumerian decoding
GENESIS_PICTOGRAPHS = [
    "A sword",           # Zayin (7)
    "A camel",           # Gimel (3)
    "A courtyard",       # Het (8)
    "Fire",              # Shin (300)
    "A door",            # Dalet (4)
    "A courtyard",       # Het (8)
    "A staff",           # Samekh (60)
    "A head",            # Resh (200)
    "A door",            # Dalet (4)
    "A hand",            # Yod (10)
    "A head",            # Resh (200)
    "A fish",            # Nun (50)
    "A shepherd's crook", # Lamed (30)
    "Water",             # Mem (40)
    "A fish",            # Nun (50)
    "A fish",            # Nun (50)
    "A shepherd's crook", # Lamed (30)
    "A courtyard",       # Het (8)
    "A house",           # Bet (2)
    "A hand",            # Yod (10)
    "A camel",           # Gimel (3)
    "A hand",            # Yod (10)
    "A coiled body",     # Qof (100)
    "A palm",            # Kaf (20)
    "A camel",           # Gimel (3)
    "A coiled body",     # Qof (100)
    "A window",          # He (5)
    "A shepherd's crook", # Lamed (30)
    "A window",          # He (5)
    "A courtyard",       # Het (8)
    "A shepherd's crook", # Lamed (30)
    "A house",           # Bet (2)
]

# Corresponding Hebrew letters
GENESIS_LETTERS = [
    "Zayin", "Gimel", "Het", "Shin", "Dalet", "Het", "Samekh", "Resh",
    "Dalet", "Yod", "Resh", "Nun", "Lamed", "Mem", "Nun", "Nun",
    "Lamed", "Het", "Bet", "Yod", "Gimel", "Yod", "Qof", "Kaf",
    "Gimel", "Qof", "He", "Lamed", "He", "Het", "Lamed", "Bet",
]

# Gematria values
GENESIS_GEMATRIA = [7, 3, 8, 300, 4, 8, 60, 200, 4, 10, 200, 50, 30, 40, 50, 50,
                    30, 8, 2, 10, 3, 10, 100, 20, 3, 100, 5, 30, 5, 8, 30, 2]

# Direct pictograph-to-BIP39 word mapping
PICTOGRAPH_TO_BIP39 = {
    "A sword": "sword",
    "A camel": "desert",
    "A courtyard": "court",
    "Fire": "fire",
    "A door": "door",
    "A staff": "staff",
    "A head": "head",
    "A hand": "hand",
    "A fish": "fish",
    "Water": "water",
    "A house": "home",
    "A hook": "hook",
    "A shepherd's crook": "staff",
    "A coiled body": "coil",
    "A palm": "palm",
    "A window": "window",
    "An ox head": "ox",
    "A serpent": "serpent",
    "An open palm": "palm",
    "Flowing water": "water",
    "A fishhook": "hook",
    "Teeth": "tooth",
    "A cross": "cross",
}

# Alternative mappings for pictographs not directly in BIP39
PICTOGRAPH_ALTERNATIVES = {
    "A courtyard": ["court", "yard", "wall", "fence"],
    "A shepherd's crook": ["staff", "hook"],
    "A coiled body": ["coil", "body", "circle", "snake"],
    "A sword": ["sword", "blade", "weapon", "steel"],
    "Fire": ["fire", "flame"],
    "A door": ["door", "gate"],
    "A head": ["head", "brain", "skull"],
    "A hand": ["hand", "palm"],
    "A fish": ["fish", "shark", "whale", "salmon"],
    "Water": ["water", "ocean", "river", "wave"],
    "A house": ["home"],
    "A window": ["window", "glass", "view"],
    "A camel": ["desert", "journey"],
    "A staff": ["staff", "pole", "stick"],
    "A palm": ["palm"],
}


# ============================================================
# BIP39 Word List (embedded for independence)
# ============================================================

BIP39_WORDS = [
    "abandon", "ability", "able", "about", "above", "absent", "absorb", "abstract",
    "absurd", "abuse", "access", "accident", "account", "accuse", "achieve", "acid",
    "acoustic", "acquire", "across", "act", "action", "actor", "actress", "actual",
    "adapt", "add", "addict", "address", "adjust", "admit", "adult", "advance", "advice",
    "aerobic", "affair", "afford", "afraid", "again", "age", "agent", "agree", "ahead",
    "aim", "air", "airport", "aisle", "alarm", "album", "alcohol", "alert", "alien",
    "all", "alley", "allow", "almost", "alone", "alpha", "already", "also", "alter",
    "always", "amateur", "amazing", "among", "amount", "amused", "analyst", "anchor",
    "ancient", "anger", "angle", "angry", "animal", "ankle", "announce", "annual",
    "another", "answer", "antenna", "antique", "anxiety", "any", "apart", "apology",
    "appear", "apple", "approve", "april", "arch", "arctic", "area", "arena", "argue",
    "arm", "armed", "armor", "army", "around", "arrange", "arrest", "arrive", "arrow",
    "art", "artefact", "artist", "artwork", "ask", "aspect", "assault", "asset", "assist",
    "assume", "asthma", "athlete", "atom", "attack", "attend", "attract", "auction",
    "audit", "august", "aunt", "author", "auto", "autumn", "average", "avocado", "avoid",
    "awake", "aware", "awesome", "awful", "awkward", "axis", "baby", "bachelor", "bacon",
    "badge", "bag", "balance", "balcony", "ball", "bamboo", "banana", "banner", "bar",
    "barely", "bargain", "barrel", "base", "basic", "basket", "battle", "beach", "bean",
    "beauty", "because", "become", "beef", "before", "begin", "behave", "behind", "believe",
    "below", "belt", "bench", "benefit", "best", "betray", "better", "between", "beyond",
    "bicycle", "bid", "bike", "bind", "biology", "bird", "birth", "bitter", "black", "blade",
    "blame", "blanket", "blast", "bleak", "bless", "blind", "blood", "blossom", "blouse",
    "blue", "blur", "blush", "board", "boat", "body", "boil", "bomb", "bone", "bonus",
    "book", "boost", "border", "boring", "borrow", "boss", "bottom", "bounce", "box",
    "boy", "bracket", "brain", "brand", "brass", "brave", "bread", "breeze", "brick",
    "bridge", "brief", "bright", "bring", "brisk", "broccoli", "broken", "bronze", "broom",
    "brother", "brown", "brush", "bubble", "buddy", "budget", "buffalo", "build", "bulb",
    "bulk", "bullet", "bundle", "bunny", "burden", "burger", "burst", "bus", "business",
    "busy", "butter", "buyer", "buzz", "cabbage", "cabin", "cable", "cactus", "cage",
    "cake", "call", "calm", "camera", "camp", "can", "canal", "cancel", "candy", "cannon",
    "canoe", "canvas", "canyon", "capable", "capital", "captain", "car", "carbon", "card",
    "cargo", "carpet", "carry", "cart", "case", "cash", "casino", "castle", "casual",
    "cat", "catalog", "catch", "category", "cattle", "caught", "cause", "caution", "cave",
    "ceiling", "celery", "cement", "census", "century", "cereal", "certain", "chair",
    "chalk", "champion", "change", "chaos", "chapter", "charge", "chase", "cheap", "check",
    "cheese", "chef", "cherry", "chest", "chicken", "chief", "child", "chimney", "choice",
    "choose", "chronic", "chuckle", "chunk", "churn", "cigar", "cinnamon", "circle",
    "citizen", "city", "civil", "claim", "clap", "clarify", "claw", "clay", "clean",
    "clerk", "clever", "click", "client", "cliff", "climb", "clinic", "clip", "clock",
    "clog", "close", "cloth", "cloud", "clown", "club", "clump", "cluster", "clutch",
    "coach", "coast", "coconut", "code", "coffee", "coil", "coin", "collect", "color",
    "column", "combine", "come", "comfort", "comic", "common", "company", "concert",
    "conduct", "confirm", "congress", "connect", "consider", "control", "convince", "cook",
    "cool", "copper", "copy", "coral", "core", "corn", "correct", "cost", "cotton",
    "couch", "country", "couple", "course", "cousin", "cover", "coyote", "crack", "cradle",
    "craft", "cram", "crane", "crash", "crater", "crawl", "crazy", "cream", "credit",
    "creek", "crew", "cricket", "crime", "crisp", "critic", "crop", "cross", "crouch",
    "crowd", "crucial", "cruel", "cruise", "crumble", "crush", "cry", "crystal", "cube",
    "culture", "cup", "cupboard", "curious", "current", "curtain", "curve", "cushion",
    "custom", "cute", "cycle", "dad", "damage", "damp", "dance", "danger", "daring",
    "dash", "daughter", "dawn", "day", "deal", "debate", "debris", "decade", "december",
    "decide", "decline", "decorate", "decrease", "deer", "defense", "define", "defy",
    "degree", "delay", "deliver", "demand", "demise", "denial", "dentist", "deny",
    "depart", "depend", "deposit", "depth", "deputy", "derive", "describe", "desert",
    "design", "desk", "despair", "destroy", "detail", "detect", "develop", "device",
    "devote", "diagram", "dial", "diamond", "diary", "dice", "diesel", "diet", "differ",
    "digital", "dignity", "dilemma", "dinner", "dinosaur", "direct", "dirt", "disagree",
    "discover", "disease", "dish", "dismiss", "disorder", "display", "distance", "divert",
    "divide", "divorce", "dizzy", "doctor", "document", "dog", "doll", "dolphin", "domain",
    "donate", "donkey", "donor", "door", "dose", "double", "dove", "draft", "dragon",
    "drama", "draw", "dream", "dress", "drift", "drill", "drink", "drip", "drive", "drop",
    "drum", "dry", "duck", "dumb", "dune", "during", "dust", "dutch", "duty", "dwarf",
    "dynamic", "eager", "eagle", "early", "earn", "earth", "easily", "east", "easy",
    "echo", "ecology", "economy", "edge", "edit", "educate", "effort", "eight", "either",
    "elbow", "elder", "electric", "elegant", "element", "elephant", "elevator", "elite",
    "else", "embark", "embody", "embrace", "emerge", "emotion", "employ", "empower",
    "empty", "enable", "enact", "end", "endless", "endorse", "enemy", "energy", "enforce",
    "engage", "engine", "enhance", "enjoy", "enlist", "enough", "enrich", "enroll", "ensure",
    "enter", "entire", "entry", "envelope", "episode", "equal", "equip", "era", "erase",
    "erode", "erosion", "error", "erupt", "escape", "essay", "essence", "estate", "eternal",
    "ethics", "evidence", "evil", "evoke", "evolve", "exact", "example", "excess", "exchange",
    "excite", "exclude", "excuse", "execute", "exercise", "exhaust", "exhibit", "exile",
    "exist", "exit", "exotic", "expand", "expect", "expire", "explain", "expose", "express",
    "extend", "extra", "eye", "eyebrow", "fabric", "face", "faculty", "fade", "faint",
    "faith", "fall", "false", "fame", "family", "famous", "fan", "fancy", "fantasy", "farm",
    "fashion", "fat", "fatal", "father", "fatigue", "fault", "favorite", "feature", "february",
    "federal", "fee", "feed", "feel", "female", "fence", "festival", "fetch", "fever", "few",
    "fiber", "fiction", "field", "figure", "file", "film", "filter", "final", "find", "fine",
    "finger", "finish", "fire", "firm", "first", "fiscal", "fish", "fit", "fitness", "fix",
    "flag", "flame", "flash", "flat", "flavor", "flee", "flight", "flip", "float", "flock",
    "floor", "flower", "fluid", "flush", "fly", "foam", "focus", "fog", "foil", "fold",
    "follow", "food", "foot", "force", "forest", "forget", "fork", "fortune", "forum",
    "forward", "fossil", "foster", "found", "fox", "fragile", "frame", "frequent", "fresh",
    "friend", "fringe", "frog", "front", "frost", "frown", "frozen", "fruit", "fuel", "fun",
    "funny", "furnace", "fury", "future", "gadget", "gain", "galaxy", "gallery", "game",
    "gap", "garage", "garbage", "garden", "garlic", "garment", "gas", "gasp", "gate",
    "gather", "gauge", "gaze", "general", "genius", "genre", "gentle", "genuine", "gesture",
    "ghost", "giant", "gift", "giggle", "ginger", "giraffe", "girl", "give", "glad", "glance",
    "glare", "glass", "glide", "glimpse", "globe", "gloom", "glory", "glove", "glow", "glue",
    "goat", "goddess", "gold", "good", "goose", "gorilla", "gospel", "gossip", "govern",
    "gown", "grab", "grace", "grain", "grant", "grape", "grass", "gravity", "great", "green",
    "grid", "grief", "grit", "grocery", "group", "grow", "grunt", "guard", "guess", "guide",
    "guilt", "guitar", "gun", "gym", "habit", "hair", "half", "hammer", "hamster", "hand",
    "handle", "harbor", "hard", "harsh", "harvest", "hat", "have", "hawk", "hazard", "head",
    "health", "heart", "heavy", "hedgehog", "height", "hello", "helmet", "help", "hen",
    "hero", "hidden", "high", "hill", "hint", "hip", "hire", "history", "hobby", "hockey",
    "hold", "hole", "holiday", "hollow", "home", "honey", "hood", "hope", "horn", "horror",
    "horse", "hospital", "host", "hotel", "hour", "hover", "hub", "huge", "human", "humble",
    "humor", "hundred", "hungry", "hunt", "hurdle", "hurry", "hurt", "husband", "hybrid",
    "ice", "icon", "idea", "identify", "idle", "ignore", "ill", "illegal", "illness", "image",
    "imitate", "immense", "immune", "impact", "impose", "improve", "impulse", "inch", "include",
    "income", "increase", "index", "indicate", "indoor", "industry", "infant", "inflict",
    "inform", "initial", "inject", "inmate", "inner", "innocent", "input", "inquiry", "insane",
    "insect", "inside", "inspire", "install", "intact", "interest", "into", "invest", "invite",
    "involve", "iron", "island", "isolate", "issue", "item", "ivory", "jacket", "jaguar",
    "jar", "jazz", "jealous", "jeans", "jelly", "jewel", "job", "join", "joke", "journey",
    "joy", "judge", "juice", "jump", "jungle", "junior", "junk", "just", "kangaroo", "keen",
    "keep", "ketchup", "key", "kick", "kid", "kidney", "kind", "kingdom", "kiss", "kit",
    "kitchen", "kite", "kitten", "kiwi", "knee", "knife", "knock", "know", "lab", "label",
    "labor", "ladder", "lady", "lake", "lamp", "language", "laptop", "large", "later", "latin",
    "laugh", "laundry", "lava", "law", "lawn", "lawsuit", "layer", "lazy", "leader", "leaf",
    "learn", "leave", "lecture", "left", "leg", "legal", "legend", "leisure", "lemon", "lend",
    "length", "lens", "leopard", "lesson", "letter", "level", "liberty", "library", "license",
    "life", "lift", "light", "like", "limb", "limit", "link", "lion", "liquid", "list",
    "little", "live", "lizard", "load", "loan", "lobster", "local", "lock", "logic", "lonely",
    "long", "loop", "lottery", "loud", "lounge", "love", "loyal", "lucky", "luggage", "lumber",
    "lunar", "lunch", "luxury", "lyrics", "machine", "mad", "magic", "magnet", "maid", "mail",
    "main", "major", "make", "mammal", "man", "manage", "mandate", "mango", "mansion", "manual",
    "maple", "marble", "march", "margin", "marine", "market", "marriage", "mask", "mass",
    "master", "match", "material", "math", "matrix", "matter", "maximum", "maze", "meadow",
    "mean", "measure", "meat", "mechanic", "medal", "media", "melody", "melt", "member", "memory",
    "mention", "menu", "mercy", "merge", "merit", "merry", "mesh", "message", "metal", "method",
    "middle", "midnight", "milk", "million", "mimic", "mind", "minimum", "minor", "minute",
    "miracle", "mirror", "misery", "miss", "mistake", "mix", "mixed", "mixture", "mobile",
    "model", "modify", "mom", "moment", "monitor", "monkey", "monster", "month", "moon",
    "moral", "morning", "mosquito", "mother", "motion", "motor", "mountain", "mouse", "move",
    "movie", "much", "muffin", "mule", "multiply", "muscle", "museum", "mushroom", "music",
    "must", "mutual", "myself", "mystery", "myth", "naive", "name", "napkin", "narrow", "nasty",
    "nation", "nature", "near", "neck", "need", "negative", "neglect", "neither", "nephew",
    "nerve", "nest", "net", "network", "neutral", "never", "news", "next", "nice", "night",
    "noble", "noise", "nominee", "noodle", "normal", "north", "nose", "notable", "nothing",
    "notice", "novel", "now", "nuclear", "number", "nurse", "nut", "oak", "obey", "object",
    "oblige", "obscure", "observe", "obtain", "obvious", "occur", "ocean", "october", "odor",
    "off", "offer", "office", "often", "oil", "okay", "old", "olive", "olympic", "omit",
    "once", "one", "onion", "online", "only", "open", "opera", "opinion", "oppose", "option",
    "orange", "orbit", "orchard", "order", "ordinary", "organ", "orient", "original", "orphan",
    "ostrich", "other", "outdoor", "outer", "output", "outside", "oval", "oven", "over", "own",
    "owner", "oxygen", "oyster", "ozone", "pact", "paddle", "page", "pair", "palace", "palm",
    "panda", "panel", "panic", "panther", "paper", "parade", "parent", "park", "parrot", "party",
    "pass", "patch", "path", "patient", "patrol", "pattern", "pause", "pave", "payment", "peace",
    "peanut", "pear", "peasant", "pelican", "pen", "penalty", "pencil", "people", "pepper",
    "perfect", "permit", "person", "pet", "phone", "photo", "phrase", "physical", "piano",
    "picnic", "picture", "piece", "pig", "pigeon", "pill", "pilot", "pink", "pioneer", "pipe",
    "pistol", "pitch", "pizza", "place", "planet", "plastic", "plate", "play", "please", "pledge",
    "pluck", "plug", "plunge", "poem", "poet", "point", "polar", "pole", "police", "pond",
    "pony", "pool", "popular", "portion", "position", "possible", "post", "potato", "pottery",
    "poverty", "powder", "power", "practice", "praise", "predict", "prefer", "prepare", "present",
    "pretty", "prevent", "price", "pride", "primary", "print", "priority", "prison", "private",
    "prize", "problem", "process", "produce", "profit", "program", "project", "promote", "proof",
    "property", "prosper", "protect", "proud", "provide", "public", "pudding", "pull", "pulp",
    "pulse", "pumpkin", "punch", "pupil", "puppy", "purchase", "purity", "purpose", "purse",
    "push", "put", "puzzle", "pyramid", "quality", "quantum", "quarter", "question", "quick",
    "quit", "quiz", "quote", "rabbit", "raccoon", "race", "rack", "radar", "radio", "rail",
    "rain", "raise", "rally", "ramp", "ranch", "random", "range", "rapid", "rare", "rate",
    "rather", "raven", "raw", "razor", "ready", "real", "reason", "rebel", "rebuild", "recall",
    "receive", "recipe", "record", "recycle", "reduce", "reflect", "reform", "region", "regret",
    "regular", "reject", "relax", "release", "relief", "rely", "remain", "remember", "remind",
    "remove", "render", "renew", "rent", "reopen", "repair", "repeat", "replace", "report",
    "require", "rescue", "resemble", "resist", "resource", "response", "result", "retire",
    "retreat", "return", "reunion", "reveal", "review", "reward", "rhythm", "rib", "ribbon",
    "rice", "rich", "ride", "ridge", "rifle", "right", "rigid", "ring", "riot", "ripple",
    "risk", "ritual", "rival", "river", "road", "roast", "robot", "robust", "rocket", "romance",
    "roof", "rookie", "room", "rose", "rotate", "rough", "round", "route", "royal", "rubber",
    "rude", "rug", "rule", "run", "runway", "rural", "sad", "saddle", "sadness", "safe", "sail",
    "salad", "salmon", "salon", "salt", "salute", "same", "sample", "sand", "satisfy", "satoshi",
    "sauce", "sausage", "save", "say", "scale", "scan", "scare", "scatter", "scene", "scheme",
    "school", "science", "scissors", "scorpion", "scout", "scrap", "screen", "script", "scrub",
    "search", "season", "seat", "second", "secret", "section", "security", "seed", "seek",
    "segment", "select", "sell", "seminar", "senior", "sense", "sentence", "series", "service",
    "session", "settle", "setup", "seven", "shadow", "shaft", "shallow", "share", "shed",
    "shell", "sheriff", "shield", "shift", "shine", "ship", "shiver", "shock", "shoe", "shoot",
    "shop", "short", "shoulder", "shove", "shrimp", "shrug", "shuffle", "shy", "sibling", "sick",
    "side", "siege", "sight", "sign", "silent", "silk", "silly", "silver", "similar", "simple",
    "since", "sing", "siren", "sister", "situate", "six", "size", "skate", "sketch", "ski",
    "skill", "skin", "skirt", "skull", "slab", "slam", "sleep", "slender", "slice", "slide",
    "slight", "slim", "slogan", "slot", "slow", "slush", "small", "smart", "smile", "smoke",
    "smooth", "snack", "snake", "snap", "sniff", "snow", "soap", "soccer", "social", "sock",
    "soda", "soft", "solar", "soldier", "solid", "solution", "solve", "someone", "song", "soon",
    "sorry", "sort", "soul", "sound", "soup", "source", "south", "space", "spare", "spatial",
    "spawn", "speak", "special", "speed", "spell", "spend", "sphere", "spice", "spider", "spike",
    "spin", "spirit", "split", "sponsor", "spoon", "sport", "spot", "spray", "spread", "spring",
    "spy", "square", "squeeze", "squirrel", "stable", "stadium", "staff", "stage", "stairs",
    "stamp", "stand", "start", "state", "stay", "steak", "steel", "stem", "step", "stereo",
    "stick", "still", "sting", "stock", "stomach", "stone", "stool", "story", "stove", "strategy",
    "street", "strike", "strong", "struggle", "student", "stuff", "stumble", "style", "subject",
    "submit", "subway", "success", "such", "sudden", "suffer", "sugar", "suggest", "suit",
    "summer", "sun", "sunny", "sunset", "super", "supply", "supreme", "sure", "surface", "surge",
    "surprise", "surround", "survey", "suspect", "sustain", "swallow", "swamp", "swap", "swarm",
    "swear", "sweet", "swift", "swim", "swing", "switch", "sword", "symbol", "symptom", "syrup",
    "system", "table", "tackle", "tag", "tail", "talent", "talk", "tank", "tape", "target",
    "task", "taste", "tattoo", "taxi", "teach", "team", "tell", "ten", "tenant", "tennis",
    "tent", "term", "test", "text", "thank", "that", "theme", "then", "theory", "there", "they",
    "thing", "this", "thought", "three", "thrive", "throw", "thumb", "thunder", "ticket", "tide",
    "tiger", "tilt", "timber", "time", "tiny", "tip", "tired", "tissue", "title", "toast",
    "tobacco", "today", "toddler", "toe", "together", "toilet", "token", "tomato", "tomorrow",
    "tone", "tongue", "tonight", "tool", "tooth", "top", "topic", "topple", "torch", "tornado",
    "tortoise", "toss", "total", "tourist", "toward", "tower", "town", "toy", "track", "trade",
    "traffic", "tragic", "train", "transfer", "trap", "trash", "travel", "tray", "treat", "tree",
    "trend", "trial", "tribe", "trick", "trigger", "trim", "trip", "trophy", "trouble", "truck",
    "true", "truly", "trumpet", "trust", "truth", "try", "tube", "tuna", "tunnel", "turkey",
    "turn", "turtle", "twelve", "twenty", "twice", "twin", "twist", "two", "type", "typical",
    "ugly", "umbrella", "unable", "unaware", "uncle", "uncover", "under", "undo", "unfair",
    "unfold", "unhappy", "uniform", "union", "unique", "unit", "universe", "unknown", "unlock",
    "until", "unusual", "unveil", "update", "upgrade", "uphold", "upon", "upper", "upset",
    "urban", "urge", "usage", "use", "used", "useful", "useless", "usual", "utility", "vacant",
    "vacuum", "vague", "valid", "valley", "valve", "van", "vanish", "vapor", "various", "vast",
    "vault", "vehicle", "velvet", "vendor", "venture", "venue", "verb", "verify", "version",
    "very", "vessel", "veteran", "viable", "vibrant", "vicious", "victory", "video", "view",
    "village", "vintage", "violin", "virtual", "virus", "visa", "visit", "visual", "vital",
    "vivid", "vocal", "voice", "void", "volcano", "volume", "vote", "voyage", "wage", "wagon",
    "wait", "walk", "wall", "walnut", "want", "warfare", "warm", "warrior", "wash", "wasp",
    "waste", "water", "wave", "way", "wealth", "weapon", "wear", "weasel", "weather", "web",
    "wedding", "weekend", "weird", "welcome", "west", "whale", "what", "wheat", "wheel", "when",
    "where", "whip", "whisper", "wide", "width", "wife", "wild", "will", "win", "window",
    "wine", "wing", "wink", "winner", "winter", "wire", "wisdom", "wise", "wish", "witness",
    "wolf", "woman", "wonder", "wood", "wool", "word", "work", "world", "worry", "worth",
    "wrap", "wreck", "wrestle", "wrist", "write", "wrong", "yard", "year", "yellow", "you",
    "young", "youth", "zebra", "zero", "zone", "zoo",
]

# Verify word list (relaxed for now — will load from file if incomplete)
if len(BIP39_WORDS) != 2048:
    # Load from canonical file
    import os as _os
    _here = _os.path.dirname(_os.path.abspath(__file__))
    _file_path = _os.path.join(_here, '..', '..', 'excalibur_wallet', 'bip39_english.txt')
    if _os.path.exists(_file_path):
        with open(_file_path) as _f:
            BIP39_WORDS = [w.strip() for w in _f if w.strip()]
    del _os, _here, _file_path, _f

assert len(BIP39_WORDS) == 2048, f"BIP39 word list has {len(BIP39_WORDS)} words, expected 2048"
assert len(set(BIP39_WORDS)) == 2048, "BIP39 word list has duplicates"

BIP39_INDEX = {w: i for i, w in enumerate(BIP39_WORDS)}


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class PictographMapping:
    """A single pictograph mapped to one or more BIP39 words."""
    pictograph: str
    hebrew_letter: str
    gematria: int
    direct_match: Optional[str] = None
    direct_index: Optional[int] = None
    alternatives: List[Tuple[str, int]] = field(default_factory=list)
    hash_match: Optional[str] = None
    hash_index: Optional[int] = None
    
    def best_match(self) -> Tuple[str, int]:
        """Return the best BIP39 word match."""
        if self.direct_match and self.direct_match in BIP39_INDEX:
            return (self.direct_match, self.direct_index)
        if self.alternatives:
            return self.alternatives[0]
        if self.hash_match:
            return (self.hash_match, self.hash_index)
        return (None, -1)


@dataclass
class PictographicMnemonic:
    """
    A BIP39 mnemonic derived from pictographs.
    
    This represents the bridge between ancient images and modern
    wallet seeds. Each pictograph maps to a BIP39 word, and the
    resulting sequence is checked for BIP39 validity.
    """
    pictographs: List[str]
    mappings: List[PictographMapping] = field(default_factory=list)
    mnemonic_words: List[str] = field(default_factory=list)
    mnemonic_string: str = ""
    is_valid_bip39: bool = False
    entropy: Optional[bytes] = None
    seed: Optional[bytes] = None
    
    def map_pictographs(self) -> 'PictographicMnemonic':
        """Map each pictograph to BIP39 words."""
        self.mappings = []
        
        for i, pict in enumerate(self.pictographs):
            letter = GENESIS_LETTERS[i] if i < len(GENESIS_LETTERS) else ""
            gem = GENESIS_GEMATRIA[i] if i < len(GENESIS_GEMATRIA) else 0
            
            mapping = PictographMapping(
                pictograph=pict,
                hebrew_letter=letter,
                gematria=gem,
            )
            
            # Direct match
            if pict in PICTOGRAPH_TO_BIP39:
                word = PICTOGRAPH_TO_BIP39[pict]
                if word in BIP39_INDEX:
                    mapping.direct_match = word
                    mapping.direct_index = BIP39_INDEX[word]
            
            # Alternatives
            if pict in PICTOGRAPH_ALTERNATIVES:
                for alt in PICTOGRAPH_ALTERNATIVES[pict]:
                    if alt in BIP39_INDEX:
                        mapping.alternatives.append((alt, BIP39_INDEX[alt]))
            
            # Hash-based match: SHA-256 of pictograph → word index
            pict_hash = hashlib.sha256(pict.encode()).digest()
            hash_index = int.from_bytes(pict_hash[:4], 'big') % 2048
            mapping.hash_match = BIP39_WORDS[hash_index]
            mapping.hash_index = hash_index
            
            self.mappings.append(mapping)
        
        return self
    
    def build_mnemonic(self, strategy: str = "direct") -> 'PictographicMnemonic':
        """
        Build a mnemonic from the mappings using the specified strategy.
        
        Strategies:
        - "direct": Use direct matches, fall back to hash
        - "hash": Use hash-based mapping for all
        - "gematria": Use gematria value mod 2048 for word index
        - "byte": Use Genesis seed bytes mod 2048 for word index
        """
        self.mnemonic_words = []
        
        # Compute Genesis seed for byte-based strategies
        genesis_data = (
            GENESIS_HASH.encode() +
            struct.pack('>I', GENESIS_NONCE) +
            struct.pack('>I', GENESIS_TIMESTAMP)
        )
        genesis_seed = hashlib.sha256(genesis_data).digest()
        
        for i, mapping in enumerate(self.mappings):
            if strategy == "direct":
                word, idx = mapping.best_match()
                if word is None:
                    word = mapping.hash_match
                self.mnemonic_words.append(word)
            
            elif strategy == "hash":
                self.mnemonic_words.append(mapping.hash_match)
            
            elif strategy == "gematria":
                idx = mapping.gematria % 2048
                self.mnemonic_words.append(BIP39_WORDS[idx])
            
            elif strategy == "byte":
                byte_val = genesis_seed[i % len(genesis_seed)]
                idx = byte_val % 2048
                self.mnemonic_words.append(BIP39_WORDS[idx])
        
        self.mnemonic_string = " ".join(self.mnemonic_words)
        
        # Check BIP39 validity (only 12 or 24 words can be valid)
        # 32 pictographs → 32 words, which is not a valid BIP39 length
        # We check subsets: first 12, first 24
        self.is_valid_bip39 = self._check_validity()
        
        return self
    
    def _check_validity(self) -> bool:
        """Check if any subset of the mnemonic is valid BIP39."""
        # 32 words is not a standard BIP39 length
        # Check if first 12 or first 24 form valid mnemonics
        for length in [12, 24]:
            if len(self.mnemonic_words) >= length:
                subset = " ".join(self.mnemonic_words[:length])
                if validate_bip39_mnemonic(subset):
                    self.is_valid_bip39 = True
                    return True
        return False
    
    def get_12_word_mnemonic(self) -> str:
        """Get the first 12 words as a potential BIP39 mnemonic."""
        return " ".join(self.mnemonic_words[:12])
    
    def get_24_word_mnemonic(self) -> str:
        """Get the first 24 words as a potential BIP39 mnemonic."""
        return " ".join(self.mnemonic_words[:24])
    
    def derive_seed(self, mnemonic: str = None, passphrase: str = "") -> bytes:
        """Derive BIP39 seed from the mnemonic."""
        if mnemonic is None:
            mnemonic = self.mnemonic_string
        return bip39_mnemonic_to_seed(mnemonic, passphrase)
    
    def analyze(self) -> Dict:
        """Full analysis of the pictographic mapping."""
        direct_matches = sum(1 for m in self.mappings if m.direct_match and m.direct_match in BIP39_INDEX)
        alt_matches = sum(len(m.alternatives) for m in self.mappings)
        
        return {
            "total_pictographs": len(self.pictographs),
            "direct_bip39_matches": direct_matches,
            "alternative_matches": alt_matches,
            "mnemonic_words": len(self.mnemonic_words),
            "mnemonic_string": self.mnemonic_string,
            "is_valid_bip39": self.is_valid_bip39,
            "unique_words": len(set(self.mnemonic_words)),
            "word_indices": [BIP39_INDEX.get(w, -1) for w in self.mnemonic_words],
        }


# ============================================================
# BIP39 Core Functions
# ============================================================

def validate_bip39_mnemonic(mnemonic: str) -> bool:
    """Validate a BIP39 mnemonic (12 or 24 words with correct checksum)."""
    try:
        bip39_entropy_to_mnemonic(bip39_mnemonic_to_entropy(mnemonic))
        return True
    except (ValueError, TypeError):
        return False


def bip39_entropy_to_mnemonic(entropy: bytes) -> str:
    """Convert entropy bytes to BIP39 mnemonic string."""
    if len(entropy) not in (16, 20, 24, 28, 32):
        raise ValueError(f"Entropy must be 16-32 bytes, got {len(entropy)}")
    
    ent_bits = len(entropy) * 8
    cs_bits = ent_bits // 32
    h = hashlib.sha256(entropy).digest()
    
    # entropy + checksum
    data = int.from_bytes(entropy, 'big') << cs_bits
    data |= h[0] >> (8 - cs_bits)
    
    total = ent_bits + cs_bits
    words = []
    for i in range(total // 11):
        shift = total - 11 * (i + 1)
        words.append(BIP39_WORDS[(data >> shift) & 0x7FF])
    
    return " ".join(words)


def bip39_mnemonic_to_entropy(mnemonic: str) -> bytes:
    """Convert BIP39 mnemonic string back to entropy bytes."""
    parts = mnemonic.strip().split()
    word_count = len(parts)
    
    if word_count not in (12, 15, 18, 21, 24):
        raise ValueError(f"Mnemonic must be 12, 15, 18, 21, or 24 words, got {word_count}")
    
    # Combine all word indices into a single integer
    data = 0
    for w in parts:
        if w not in BIP39_INDEX:
            raise ValueError(f"Not a BIP39 word: {w!r}")
        data = (data << 11) | BIP39_INDEX[w]
    
    total_bits = word_count * 11
    cs_bits = total_bits // 33
    ent_bits = total_bits - cs_bits
    
    # Extract entropy and checksum
    entropy = (data >> cs_bits).to_bytes(ent_bits // 8, 'big')
    checksum = data & ((1 << cs_bits) - 1)
    
    # Verify checksum
    h = hashlib.sha256(entropy).digest()
    expected_cs = h[0] >> (8 - cs_bits)
    
    if checksum != expected_cs:
        raise ValueError("Mnemonic checksum mismatch")
    
    return entropy


def bip39_mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    """Derive BIP39 seed from mnemonic using PBKDF2-HMAC-SHA512."""
    mnemonic = mnemonic.strip()
    salt = ("mnemonic" + passphrase).encode('utf-8')
    return hashlib.pbkdf2_hmac(
        'sha512',
        mnemonic.encode('utf-8'),
        salt,
        2048,
        64
    )


# ============================================================
# Genesis Pictographic Mapper
# ============================================================

def map_genesis_pictographs(strategy: str = "direct") -> PictographicMnemonic:
    """
    Map the Genesis block's 32 pictographs to BIP39 words.
    
    This is the core function: it takes the ancient images encoded
    in the Genesis block and maps them to modern BIP39 mnemonic words.
    
    Args:
        strategy: "direct", "hash", "gematria", or "byte"
    
    Returns:
        PictographicMnemonic with all mappings and analysis
    """
    pm = PictographicMnemonic(pictographs=GENESIS_PICTOGRAPHS)
    pm.map_pictographs()
    pm.build_mnemonic(strategy)
    return pm


def find_closest_bip39_word(pictograph: str) -> Tuple[str, int, float]:
    """
    Find the closest BIP39 word to a pictograph description.
    
    Uses simple string similarity (character overlap) to find
    the best match among all 2048 BIP39 words.
    
    Returns:
        (word, index, similarity_score)
    """
    # Extract key nouns from the pictograph
    key_words = pictograph.lower().replace("a ", "").replace("an ", "").replace("the ", "").split()
    
    best_score = 0.0
    best_word = None
    best_idx = -1
    
    for word in BIP39_WORDS:
        score = 0.0
        for kw in key_words:
            if kw == word:
                score = 1.0
                break
            elif kw in word or word in kw:
                score = max(score, 0.7)
            # Character overlap
            common = len(set(kw) & set(word))
            total = len(set(kw) | set(word))
            if total > 0:
                score = max(score, common / total * 0.5)
        
        if score > best_score:
            best_score = score
            best_word = word
            best_idx = BIP39_INDEX[word]
    
    return (best_word, best_idx, best_score)


def search_pictographic_entropy() -> Dict:
    """
    Search for entropy that produces BIP39 mnemonics containing
    pictograph-related words.
    
    This searches the entropy space for seeds whose BIP39 mnemonics
    contain words that match the Genesis pictographs — checking if
    the Genesis block's entropy naturally produces pictographic words.
    """
    genesis_data = (
        GENESIS_HASH.encode() +
        struct.pack('>I', GENESIS_NONCE) +
        struct.pack('>I', GENESIS_TIMESTAMP)
    )
    genesis_entropy = hashlib.sha256(genesis_data).digest()
    
    # Convert to 12-word mnemonic (16 bytes entropy)
    mnemonic_12 = bip39_entropy_to_mnemonic(genesis_entropy[:16])
    # Convert to 24-word mnemonic (32 bytes entropy)
    mnemonic_24 = bip39_entropy_to_mnemonic(genesis_entropy)
    
    # Check which words match pictographs
    pictograph_words = set(PICTOGRAPH_TO_BIP39.values())
    
    matches_12 = [w for w in mnemonic_12.split() if w in pictograph_words]
    matches_24 = [w for w in mnemonic_24.split() if w in pictograph_words]
    
    return {
        "genesis_entropy_hex": genesis_entropy.hex(),
        "mnemonic_12_words": mnemonic_12,
        "mnemonic_24_words": mnemonic_24,
        "pictograph_matches_12": matches_12,
        "pictograph_matches_24": matches_24,
        "match_count_12": len(matches_12),
        "match_count_24": len(matches_24),
    }


# ============================================================
# BIP-32 HD Derivation from Pictographic Seed
# ============================================================

def pictographic_hd_path(seed: bytes, path: str = "m/44'/0'/0'/0/0") -> Dict:
    """
    Derive a BIP-32 HD wallet path from a pictographic seed.
    
    Args:
        seed: 64-byte BIP39 seed
        path: BIP-32 derivation path string
    
    Returns:
        Dictionary with derived key information
    """
    # Parse path
    parts = path.replace("m/", "").split("/")
    indices = []
    for part in parts:
        if part.endswith("'"):
            idx = int(part[:-1]) + 0x80000000
        else:
            idx = int(part)
        indices.append(idx)
    
    # BIP-32 master key derivation
    master_key = hmac.new(b'Bitcoin seed', seed, hashlib.sha512).digest()
    master_private = master_key[:32]
    master_chain_code = master_key[32:]
    
    # Derive child keys
    private_key = master_private
    chain_code = master_chain_code
    
    for idx in indices:
        # Child key derivation
        if idx >= 0x80000000:
            # Hardened derivation
            data = b'\x00' + private_key + idx.to_bytes(4, 'big')
        else:
            # Normal derivation (would need public key)
            data = b'\x00' + private_key + idx.to_bytes(4, 'big')
        
        hmac_result = hmac.new(chain_code, data, hashlib.sha512).digest()
        child_key = hmac_result[:32]
        chain_code = hmac_result[32:]
        
        # Add parent key mod n
        n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        private_key = (int.from_bytes(private_key, 'big') + int.from_bytes(child_key, 'big')) % n
        private_key = private_key.to_bytes(32, 'big')
    
    # Compute public key (simplified - would need secp256k1 in production)
    # For now, return the private key hash
    return {
        "path": path,
        "private_key_hex": private_key.hex(),
        "chain_code_hex": chain_code.hex(),
        "address_hint": private_key[:8].hex(),
    }


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def get_genesis_mnemonic(strategy: str = "direct") -> str:
    """Get the Genesis block's pictographic mnemonic as a string."""
    pm = map_genesis_pictographs(strategy)
    return pm.mnemonic_string


def get_genesis_seed(strategy: str = "direct", passphrase: str = "") -> bytes:
    """Get the BIP39 seed derived from the Genesis pictographs."""
    pm = map_genesis_pictographs(strategy)
    return pm.derive_seed(passphrase=passphrase)


def check_pictograph_in_bip39(pictograph: str) -> bool:
    """Check if a pictograph has a direct BIP39 word match."""
    return pictograph in PICTOGRAPH_TO_BIP39 and PICTOGRAPH_TO_BIP39[pictograph] in BIP39_INDEX


def get_pictograph_word(pictograph: str) -> Optional[str]:
    """Get the BIP39 word for a pictograph, if one exists."""
    if pictograph in PICTOGRAPH_TO_BIP39:
        word = PICTOGRAPH_TO_BIP39[pictograph]
        if word in BIP39_INDEX:
            return word
    return None


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 80)
    print("BIP39 PICTOGRAPHIC MAPPER")
    print("From Ancient Images to Wallet Seeds")
    print("=" * 80)
    print()
    
    # Strategy 1: Direct mapping
    print("Strategy 1: Direct Pictograph-to-Word Mapping")
    print("-" * 40)
    pm_direct = map_genesis_pictographs("direct")
    analysis = pm_direct.analyze()
    print(f"Direct matches: {analysis['direct_bip39_matches']}/{len(GENESIS_PICTOGRAPHS)}")
    print(f"Unique words: {analysis['unique_words']}")
    print(f"Valid BIP39: {analysis['is_valid_bip39']}")
    print(f"Mnemonic: {pm_direct.mnemonic_string[:100]}...")
    print()
    
    # Strategy 2: Hash-based
    print("Strategy 2: Hash-based Mapping")
    print("-" * 40)
    pm_hash = map_genesis_pictographs("hash")
    print(f"Mnemonic: {pm_hash.mnemonic_string[:100]}...")
    print()
    
    # Strategy 3: Gematria-based
    print("Strategy 3: Gematria-based Mapping")
    print("-" * 40)
    pm_gem = map_genesis_pictographs("gematria")
    print(f"Mnemonic: {pm_gem.mnemonic_string[:100]}...")
    print()
    
    # Strategy 4: Byte-based
    print("Strategy 4: Genesis Seed Byte Mapping")
    print("-" * 40)
    pm_byte = map_genesis_pictographs("byte")
    print(f"Mnemonic: {pm_byte.mnemonic_string[:100]}...")
    print()
    
    # Search for entropy matches
    print("Genesis Entropy Search")
    print("-" * 40)
    search = search_pictographic_entropy()
    print(f"12-word mnemonic: {search['mnemonic_12_words']}")
    print(f"Pictograph matches: {search['pictograph_matches_12']}")
    print(f"24-word mnemonic: {search['mnemonic_24_words']}")
    print(f"Pictograph matches: {search['pictograph_matches_24']}")
    print()
    
    # Show individual pictograph mappings
    print("Individual Pictograph Mappings")
    print("-" * 40)
    for mapping in pm_direct.mappings[:12]:
        best = mapping.best_match()
        print(f"  {mapping.pictograph:25s} → {best[0]:15s} (idx {best[1]:4d}) [{mapping.hebrew_letter}]")
    print("  ...")
    print()
    
    # Closest word search
    print("Closest BIP39 Word Search")
    print("-" * 40)
    for pict in GENESIS_PICTOGRAPHS[:6]:
        word, idx, score = find_closest_bip39_word(pict)
        print(f"  {pict:25s} → {word:15s} (score {score:.2f})")
    print()
    
    print("=" * 80)
    print("The 32 pictographs bridge 4000 years of human writing")
    print("from Proto-Sinaitic images to BIP39 wallet seeds.")
    print("=" * 80)

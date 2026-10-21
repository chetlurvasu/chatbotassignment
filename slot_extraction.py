"""
slot_extraction.py - finds food, area and price range in what the user types

First it looks for the exact keywords (italian, north, cheap...). If a word is
not known, there are two fallbacks:
  - Levenshtein distance (typos like "brith" -> british)
  - DistilBERT embeddings (words with a similar meaning)
Whenever the fallback guesses, the system asks "Did you mean ...?" first, so
a wrong guess never goes through silently.


"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

try:
    import Levenshtein
except ImportError as e: 
    raise ImportError("pip install python-Levenshtein") from e

SLOTS = ("food", "area", "pricerange")
DONTCARE = "dontcare"

# Response templates used by this module 
TEMPLATES = {
    "confirm_value": "I did not recognize {given}. Did you mean {suggested}?",
    "unknown_value": "Sorry, I am not familiar with {given}. Would you like something else?",
}



# Spelling variants only. Paraphrases ("fancy", "inexpensive", "downtown") are
# NOT listed here, they are what the fallbacks are for.
ALIASES = {
    "area": {"center": "centre"},
    "pricerange": {
        "moderately": "moderate",
        # cheap
        "cheaper": "cheap", "cheapest": "cheap", "inexpensive": "cheap", "affordable": "cheap",
        "budget": "cheap", "low cost": "cheap", "low priced": "cheap", "low price": "cheap",
        "economical": "cheap", "less expensive": "cheap", "not expensive": "cheap",
        "lower priced": "cheap", "lower price": "cheap", "budget friendly": "cheap",
        "on a budget": "cheap", "not too expensive": "cheap", "less pricey": "cheap",
        # moderate
        "mid range": "moderate", "mid priced": "moderate", "medium priced": "moderate",
        "medium price": "moderate", "reasonably priced": "moderate", "average priced": "moderate",
        "moderate price": "moderate", "mid price": "moderate", "fairly priced": "moderate",
        "reasonable": "moderate", "good value": "moderate", "somewhere in the middle": "moderate",
        "not too cheap and not too expensive": "moderate",
        # expensive
        "pricey": "expensive", "pricy": "expensive", "costly": "expensive", "upscale": "expensive",
        "high end": "expensive", "high priced": "expensive", "high price": "expensive",
        "luxury": "expensive", "posh": "expensive", "fancy": "expensive", "pricier": "expensive",
        "fine dining": "expensive", "splurge": "expensive", "not cheap": "expensive",
    },
    "food": {"asian": "asian oriental", "oriental": "asian oriental", "gastro pub": "gastropub",
             "sea food": "seafood", "steak house": "steakhouse"},
}

# "any area", "any part of town", ...  is dontcare
DONTCARE_SPECIFIC = {
    "area": r"\bany (?:area|part of town|part|location|place)\b|\banywhere\b"
            r"|\b(?:area|part of town|location) (?:doesnt|does not) matter\b"
            r"|\b(?:dont|do not) care (?:about |where |what )?(?:the )?(?:area|location|part of town)\b",
    "pricerange": r"\bany (?:price|price range|pricerange|budget)\b"
                  r"|\bprice(?: range)? (?:doesnt|does not) matter\b"
                  r"|\b(?:dont|do not) care (?:about |what )?(?:the )?(?:price|how much|cost)\b",
    "food": r"\bany (?:kind of |type of )?(?:food|cuisine)\b"
            r"|\b(?:dont|do not) care (?:about |what )?(?:the )?(?:food|cuisine|kind of food|type of food)\b",
}


DONTCARE_GENERIC = (
    r"\b(?:i )?(?:dont|do not) care\b|\b(?:it )?(?:doesnt|does not) matter\b"
    r"|\bno preference\b|\bnot (?:important|fussed)\b"
    r"|^(?:any|anything|either|whatever)(?: (?:is|will be|would be))?(?: (?:fine|ok|okay|good|do|will do))?$"
)

NEGATION_BEFORE = r"(?:\b(?:not|dont|never|except|without)\s+(?:\w+\s+){0,2}|\bno\s+)$"

# Words that are never a preference value
STOP = set("""
a an the any some good nice great kind type of food cuisine restaurant restaurants
place places to go in for that which serves serve serving with and or i im want
would like looking find me please is it be should can could you have do what about
how then also something somewhere anywhere eat eating dinner lunch one another other
else new town part area location side near around price range priced pricerange
cheap moderate expensive moderately centre center north south east west dontcare
no preference really anything whatever dont care matter doesnt does not fine ok okay
yes thanks thank bye goodbye hello hi um uh
""".split())


CANDIDATE_CONTEXTS = [
    (r"\b((?:[a-z]+ )?[a-z]+) (?:food|cuisine)\b",             ("food",), True),
    (r"\b([a-z]+) (?:restaurants?|places?)\b",                  ("food", "pricerange"), True),
    (r"\b(?:serves?|serving|eat|eating) (?:(?:some|a|an|the) )?([a-z]+)\b", ("food",), True),
    (r"\b([a-z]+) priced\b|\bpriced ([a-z]+)\b",                ("pricerange",), False),
    (r"\b([a-z]+) price(?: range)?\b",                          ("pricerange",), False),
    (r"\bin the ([a-z]+)\b|\bnear (?:the )?([a-z]+)\b",         ("area",), False),
    (r"\b([a-z]+) (?:part of town|of town|area|side)\b",        ("area",), False),
    (r"\bsomewhere ([a-z]+)\b",                                 ("area", "pricerange"), False),
    (r"\b(?:how|what) about (?:a |an |some |the )?([a-z]+)\b",   ("food", "area", "pricerange"), False),
]


def normalize(text: str) -> str:
    """Lower case, drop apostrophes (dont, im), punctuation -> space."""
    t = text.lower().replace("'", "").replace("’", "")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def load_ontology(csv_path) -> dict:
    df = pd.read_csv(csv_path, keep_default_na=False)
    return {
        slot: sorted({v.strip().lower() for v in df[slot] if str(v).strip()})
        for slot in SLOTS
    }


@dataclass
class SlotResult:
    # committed values, e.g. {"food": "italian"}
    slots: dict = field(default_factory=dict)    
     # need a yes/no from the user first  
    pending: list = field(default_factory=list)   
    # words that matched nothing
    unknown: list = field(default_factory=list) 
    # values the user rejected ("not chinese")   
    negated: dict = field(default_factory=dict)    
    # slot -> "keyword" / "levenshtein" / "embedding"
    source: dict = field(default_factory=dict)     
    def proposed(self) -> dict:
        """Committed slots plus the values waiting for confirmation (for evaluation)."""
        out = dict(self.slots)
        for p in self.pending:
            out.setdefault(p["slot"], p["suggested"])
        return out


# Fallback 

def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance where swapping two neighbouring letters (thia -> thai) costs 1."""
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


class LevenshteinMatcher:
    name = "levenshtein"

    def __init__(self, ontology: dict):
        self.onto = ontology

    @staticmethod
    def max_distance(word: str) -> int:
        n = len(word)
        return 0 if n <= 3 else 1 if n == 4 else 2

    def match(self, word: str, slots):
        limit = self.max_distance(word)
        best = None
        for slot in slots:
            for term in self.onto[slot]:
                d = _edit_distance(word, term)
                if len(word) >= 4 and term.startswith(word):      # 'brit' -> british
                    d = min(d, 1)
                if d > limit:
                    continue
                key = (d, -Levenshtein.jaro_winkler(word, term))   # tie-break on similarity
                if best is None or key < best[0]:
                    best = (key, slot, term, d)
        if best is None:
            return None
        _, slot, term, d = best
        return {"slot": slot, "value": term, "score": float(d), "exact": d == 0}



 # DistilBERT embeddings fallabck 

class EmbeddingMatcher:
   
    name = "embedding"

    TEMPLATES = {
        "food": "i want {} food",
        "pricerange": "i want a {} restaurant",
        "area": "i want a restaurant in the {} part of town",
    }

    def __init__(self, ontology: dict, threshold=0.75, margin=0.02,
                 model_name="distilbert/distilbert-base-uncased", encoder=None):
        self.onto = ontology
        self.threshold = threshold
        self.margin = margin
        self.model_name = model_name
        self._encoder = encoder
        self._cache = {}
        self._tok = self._model = None

    def _load(self):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self._tok = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModel.from_pretrained(self.model_name).eval()
        self._torch = torch

    def _encode(self, word, template):
        if self._encoder is not None:
            return self._encoder(word, template)
        if self._model is None:
            self._load()
        before, after = template.split("{}")
        sentence = template.format(word)
        start, end = len(before), len(before) + len(word)
        enc = self._tok(sentence, return_offsets_mapping=True, return_tensors="pt")
        offsets = enc.pop("offset_mapping")[0].tolist()
        with self._torch.inference_mode():
            hidden = self._model(**enc).last_hidden_state[0]
        idx = [i for i, (s, e) in enumerate(offsets) if e > s and s >= start and e <= end]
        return hidden[idx].mean(dim=0).numpy()

    def _vec(self, word, slot):
        key = (word, slot)
        if key not in self._cache:
            v = self._encode(word, self.TEMPLATES[slot])
            self._cache[key] = v / (float((v ** 2).sum()) ** 0.5 + 1e-12)
        return self._cache[key]

    def match(self, word: str, slots):
        scored = []
        for slot in slots:
            w = self._vec(word, slot)
            for term in self.onto[slot]:
                scored.append((float(w @ self._vec(term, slot)), slot, term))
        if not scored:
            return None
        scored.sort(reverse=True)
        top, slot, term = scored[0]
        runner_up = next((s for s, _, t in scored[1:] if t != term), -1.0)
        if top < self.threshold or top - runner_up < self.margin:
            return None
        return {"slot": slot, "value": term, "score": top, "exact": False}


# extractor

class SlotExtractor:
    def __init__(self, ontology_csv="restaurant_info.csv", method="levenshtein",
                 confirm_semantic=True, embedder=None):
        self.onto = load_ontology(ontology_csv)
        self.method = method
        self.confirm_semantic = confirm_semantic
        self.matchers = {
            "levenshtein": LevenshteinMatcher(self.onto),
            "embedding": embedder or EmbeddingMatcher(self.onto),
        }
        surfaces = [(v, s, v) for s, vals in self.onto.items() for v in vals]
        surfaces += [(a, s, v) for s, al in ALIASES.items() for a, v in al.items()]
        self._surfaces = sorted(surfaces, key=lambda x: -len(x[0]))   # longest first

    #  keywords 
    def _keywords(self, t, asked_slot, res, consumed):
        for slot, pat in DONTCARE_SPECIFIC.items():
            m = re.search(pat, t)
            if m:
                res.slots[slot] = DONTCARE
                res.source[slot] = "keyword"
                consumed.append(m.span())

        for surface, slot, value in self._surfaces:
            for m in re.finditer(rf"\b{re.escape(surface)}\b", t):
                if any(m.start() < e and s < m.end() for s, e in consumed):
                    continue
                consumed.append(m.span())
                if re.search(NEGATION_BEFORE, t[:m.start()]):
                    res.negated[slot] = value
                elif slot not in res.slots:
                    res.slots[slot] = value
                    res.source[slot] = "keyword"

        if asked_slot and asked_slot not in res.slots and re.search(DONTCARE_GENERIC, t):
            res.slots[asked_slot] = DONTCARE
            res.source[asked_slot] = "keyword"

    #  leftover words -- candidates 
    def _candidates(self, t, asked_slot, res, consumed):
        def free(word_start):
            return not any(s <= word_start < e for s, e in consumed)

        found = {}   
        for pattern, slots, report in CANDIDATE_CONTEXTS:
            for m in re.finditer(pattern, t):
                g = next((i for i in range(1, (m.lastindex or 0) + 1) if m.group(i)), None)
                if g is None:
                    continue
                words = m.group(g).split()
                # try "two words" first, then the last word
                options = [(m.start(g), " ".join(words))] if len(words) > 1 else []
                options.append((m.end(g) - len(words[-1]), words[-1]))
                for start, w in options:
                    if any(x in STOP for x in w.split()) or not free(start):
                        continue
                    found.setdefault(w, (slots, report))
                    break

       
        if asked_slot and asked_slot not in res.slots and not found:
            rest = [w for w in re.finditer(r"[a-z0-9]+", t)
                    if free(w.start()) and w.group() not in STOP]
            if 1 <= len(rest) <= 2:
                found[" ".join(w.group() for w in rest)] = ((asked_slot,), True)
        return found

    def extract(self, text: str, asked_slot=None, method=None) -> SlotResult:
        method = method or self.method
        t = normalize(text)
        res, consumed = SlotResult(), []
        self._keywords(t, asked_slot, res, consumed)

        if method == "none":
            return res
        matcher = self.matchers[method]

        for word, (slots, report) in self._candidates(t, asked_slot, res, consumed).items():
            slots = [s for s in slots if s not in res.slots]
            if not slots:
                continue
            m = matcher.match(word, slots)
            if m is None:
                if report:
                    res.unknown.append(word)
                continue
            if m["exact"] or (method == "embedding" and not self.confirm_semantic):
                res.slots[m["slot"]] = m["value"]
                res.source[m["slot"]] = method
            else:
                res.pending.append({"slot": m["slot"], "given": word, "suggested": m["value"],
                                    "method": method, "score": round(m["score"], 3)})
        return res




def update_context(context: dict, result: SlotResult) -> dict:
    """Merge one SlotResult into the dialog context."""
    slots = context.setdefault("slots", {s: None for s in SLOTS})
    slots.update(result.slots)
    pending = context.setdefault("pending_confirmations", [])
    pending.extend(result.pending)
    context["unknown_preferences"] = result.unknown
    context["negated_slots"] = result.negated
    context["missing_slots"] = [s for s in SLOTS if slots[s] is None]
    context["constraints_complete"] = not context["missing_slots"] and not pending
    return context


def resolve_confirmation(context: dict, user_act: str):
    
    pending = context["pending_confirmations"]
    item = pending[0]
    if user_act in {"affirm", "confirm", "ack"}:
        pending.pop(0)
        context["slots"][item["slot"]] = item["suggested"]
        status = "accepted"
    elif user_act in {"negate", "deny"}:
        pending.pop(0)
        status = "rejected"
    else:
        status = "unclear"
    context["missing_slots"] = [s for s in SLOTS if context["slots"][s] is None]
    context["constraints_complete"] = not context["missing_slots"] and not pending
    return status, item


@dataclass
class DialogConfig:
    show_reasoning: bool = True
    slot_method: str = "levenshtein"
    confirm_semantic: bool = True
    log_path: str = "logs/interactions.jsonl"

    @staticmethod
    def add_arguments(parser):
        g = parser.add_argument_group("dialog configuration")
        g.add_argument("--reasoning", choices=["show", "hide"], default="show",
                       help="show or hide the reasoning behind a recommendation (default: show)")
        g.add_argument("--slot_method", choices=["levenshtein", "embedding"], default="levenshtein",
                       help="fallback for slot extraction when keyword matching fails")
        g.add_argument("--no_confirm_semantic", action="store_true",
                       help="accept embedding matches without asking the user")
        g.add_argument("--log_path", default="logs/interactions.jsonl")

    @classmethod
    def from_args(cls, args):
        return cls(show_reasoning=args.reasoning == "show", slot_method=args.slot_method,
                   confirm_semantic=not args.no_confirm_semantic, log_path=args.log_path)

    def condition(self) -> str:
        """Short label to store in every log line, e.g. 'reasoning=show|slots=levenshtein'."""
        return f"reasoning={'show' if self.show_reasoning else 'hide'}|slots={self.slot_method}"

    def to_dict(self) -> dict:
        return asdict(self)



PROPERTY_PHRASE = {
    ("touristic", True): "is touristic",
    ("touristic", False): "is not touristic",
    ("assigned_seats", True): "has assigned seats",
    ("assigned_seats", False): "does not have assigned seats",
    ("children", True): "is suitable for children",
    ("children", False): "is not suitable for children",
    ("romantic", True): "is romantic",
    ("romantic", False): "is not romantic",
}


def _clean(reason: str) -> str:
    reason = reason.strip().rstrip(".")
    return reason[6:] if reason.lower().startswith("since ") else reason


def explanations_from_result(result: dict, requirements) -> list:
    """Turn one reasoning result + the user's requirements into plain explanation items."""
    items = []
    for prop, wanted in requirements:
        reasons = result["reasons"].get(prop, [])
        if prop in result["contradictions"]:
            values = result["contradictions"][prop]
            support = [r for v, r in zip(values, reasons) if v == wanted]
            against = [r for v, r in zip(values, reasons) if v != wanted]
        else:
            support, against = reasons, []
        items.append({"property": prop, "value": wanted, "reasons": support, "against": against})
    return items


def indefinite(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


def format_recommendation(restaurant: dict, explanations=(), show_reasoning=True) -> str:
    name = restaurant["restaurantname"]
    price, food, area = restaurant.get("pricerange", ""), restaurant.get("food", ""), restaurant.get("area", "")
    price = "moderately priced" if price == "moderate" else price
    first = price or food or "nice"
    text = f"I recommend {name}, {indefinite(first)} {' '.join(x for x in (price, food) if x)} restaurant"
    if area:
        text += f" in the {area} of town" if area != "centre" else " in the centre of town"
    text += "."

    if not show_reasoning:
        return text

    for item in explanations:
        phrase = PROPERTY_PHRASE[(item["property"], item["value"])]
        if item["reasons"]:
            text += f" The restaurant {phrase} because {_clean(item['reasons'][0])}."
        else:
            text += f" The restaurant {phrase}."
        if item["against"]:
            text += f" (Note: one rule suggested otherwise - {_clean(item['against'][0])}.)"
    return text


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Try slot extraction interactively.")
    ap.add_argument("--csv", default="restaurant_info.csv")
    ap.add_argument("--method", default="levenshtein", choices=["levenshtein", "embedding", "none"])
    ap.add_argument("--asked", default=None, choices=[None, *SLOTS],
                    help="pretend the system just asked about this slot")
    args = ap.parse_args()
    ex = SlotExtractor(args.csv, method=args.method)
    while True:
        s = input("utterance (q to quit): ")
        if s.strip() == "q":
            break
        print(ex.extract(s, asked_slot=args.asked))

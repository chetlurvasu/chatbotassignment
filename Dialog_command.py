"""

Dialog_command.py - the restaurant recommendation chatbot (Part 1b)

This is the main file. You run this one to talk to the system in the terminal.


What it does, in order:
1. the user types something
2. dialog_classifier.py tells us the dialog act (inform, request, affirm...)
3. slot_extraction.py finds food / area / price range in the text
4. reasoning_updated.py looks up the restaurants and checks the extra
   requirements (romantic, children...)
5. state_transition() picks the next state and the answer

"""
import argparse
import json
import os
import random
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from slot_extraction import (SLOTS, SlotExtractor, DialogConfig, update_context,
                             resolve_confirmation, explanations_from_result,
                             format_recommendation, TEMPLATES)
from slot_extraction import PROPERTY_PHRASE

# handled by slot_extraction.py

SLOT_REQUIREMENTS = ("food", "area", "pricerange")      


def load_reasoning(csv_path, reasoning_file=None):
    here = Path(__file__).resolve().parent
    candidates = [Path(reasoning_file)] if reasoning_file else [
        here / "reasoning_updated.py", Path.cwd() / "reasoning_updated.py"]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise FileNotFoundError("reasoning_updated.py not found next to dialog_system.py")
    source = path.read_text(encoding="utf-8")
    cut = source.find("\nstate = {")
    if cut < 0:
        raise RuntimeError("could not find the test loop in reasoning_updated.py")

    
    csv_path = Path(csv_path).resolve()
    roots = [csv_path.parent.parent if csv_path.parent.name == "data" else csv_path.parent,
             path.parent, Path.cwd()]
    root = next((r for r in roots if (r / "data" / "restaurant_info_extended.csv").exists()), None)
    temp = None
    if root is None:                      # csv is in the main folder: give reasoning_updated.py a data/ copy to read
        import shutil, tempfile
        temp = tempfile.mkdtemp()
        os.makedirs(os.path.join(temp, "data"))
        shutil.copy(csv_path, os.path.join(temp, "data", "restaurant_info_extended.csv"))
        root = Path(temp)

    namespace = {"__name__": "reasoning_updated", "__file__": str(path)}
    old_cwd = os.getcwd()
    try:
        os.chdir(root)
        exec(compile(source[:cut], str(path), "exec"), namespace)
    finally:
        os.chdir(old_cwd)
        if temp:
            import shutil
            shutil.rmtree(temp, ignore_errors=True)
    return SimpleNamespace(**{k: v for k, v in namespace.items() if not k.startswith("__")})


S0 = "greeting"
S1 = "collect_constraints"
S1A = "ask_additional_requirements"
S1B = "resolve_contradiction"
S1C = "inform_no_match"
S1D = "adjust_constraints"
S1E = "apply_inference_rules"
S2 = "search_restaurant"          
S3 = "offer_alternative"
S4 = "suggest_restaurant"
S5 = "ask_booking"
S6 = "collect_booking_info"
S7 = "start_booking"
S8 = "give_requested_info"
S9 = "confirm_booking"
S10 = "end"
BOOKING_STATES = (S5, S6, S7, S9)

GREETING = "Hello, welcome to the Cambridge restaurant recommendation system. How may I help you?"
QUESTIONS = {
    "food": "What kind of food would you like?",
    "area": "What part of town would you prefer?",
    "pricerange": "What price range are you looking for?",
}
EXTRAS_QUESTION = "I found some restaurants matching your preferences. Do you have any additional requirements?"
CHANGE_Q = "Would you like to change a preference?"
WHICH_CHANGE = "Which preference would you like to change: the food, the area or the price range?"
NO_MORE = "I'm afraid that's all the options I have. Would you like to change a preference?"
CONTRADICTION_TEXT = {      # wording of reasoning_updated.ask_contradiction_preference
    "romantic": ("There is conflicting information about the romantic requirement: the restaurant "
                 "is busy, which is considered not romantic, but it also allows a long stay, which "
                 "is considered romantic. What is more important for you? "
                 "1 - It should be busy (not romantic). 2 - It should allow long stays (romantic)."),
    "touristic": ("There is conflicting information about the touristic requirement: the restaurant "
                  "is cheap and has good food, which is considered touristic, but it serves Romanian "
                  "food, which is considered not touristic. What is more important for you? "
                  "1 - Cheap with good food (touristic). 2 - Not Romanian food (not touristic)."),
}
CONTRADICTION_CHOICES = {"romantic": {"1": False, "2": True}, "touristic": {"1": True, "2": False}}
EXTRAS_WHICH = ("Which requirement do you have? For example: romantic, touristic, assigned seats, "
                "suitable for children, a lively or quiet place, a long dinner or a quick meal.")
EXTRAS_HELP = "Sorry, I did not catch a requirement. " + EXTRAS_WHICH


FIELD_PATTERNS = [
    ("phone", r"\b(phone|telephone|number)\b"),
    ("postcode", r"\b(post ?code|postal|zip)\b"),
    ("addr", r"\b(address|where is it|where is the|street)\b"),
    ("pricerange", r"\b(price|cost|how expensive)\b"),
    ("area", r"\b(which area|what area|part of town|which part)\b"),
    ("food", r"\b(what|which) (type|kind) of food\b|\bwhat food\b|\bcuisine\b"),
]
REQ_WORDS = {"romantic", "touristic", "tourist", "busy", "quiet", "lively", "children", "child", "kids",
             "family", "long", "quick", "seats", "seating", "assigned", "dinner", "meal", "crowded"}
ALT_RX = re.compile(r"\b(other|another|else|different|alternatives?|alternately|next|more|others|further|diff)\b"
                    r"|\b(any|got)\s+(other|more)\b|\bwhat about\b.*\b(other|another)\b", re.I)
CANCEL_RX = re.compile(r"\b(cancel|never ?mind|forget it|stop|ignore|skip|nothing)\b|\b(don'?t|do not|dont)\s+(want\s+to\s+|wanna\s+|need\s+to\s+)?(book|reserve)|\bno\s+(booking|reservation)|\bnot\s+(want\s+)?to\s+(book|reserve)")
HELP_RX = re.compile(r"\b(help|what can (i|you)|how does this work|instructions)\b|^\s*\?+\s*$")
HELP_TEXT = ("You can tell me the kind of food, the part of town and the price range you want, ask for the "
             "phone number, address or postcode of a restaurant, ask for another one, or book a table. "
             "Say 'start over' to begin again or 'bye' to stop. ")

GLOBAL_ACTS = {"restart", "bye", "repeat"}
EXTRACT_ACTS_LATE = {"inform", "reqalts", "reqmore", "null", "hello"}



def new_context(shared=None) -> dict:
    
    ctx = dict(shared or {})
    ctx.update({
        "user_text": "", "slots": {s: None for s in SLOTS}, "pending_confirmations": [],
        "unknown_preferences": [], "negated_slots": {}, "missing_slots": list(SLOTS),
        "constraints_complete": False, "restaurant_found": False, "asked_slot": None,
        "extras": [], "extras_asked": False, "resolved": set(), "contradiction": None,
        "candidates": [],
        "current": None, "index": -1, "previous_response": "", "changed": False,
        "booking": {}, "booking_asked": None, "path": [],
    })
    return ctx


def pretty_slots(slots: dict) -> str:
    return ", ".join(f"{s}={v}" for s, v in slots.items() if v not in (None, "dontcare"))


def text_to_act(text: str, act: str) -> str:
    
    t = re.sub(r"[^a-z ]", "", text.lower()).strip()
    if re.search(r"\b(bye|goodbye|good bye)\b", t):
        return "bye"
    if len(t.split()) <= 5 and re.search(r"\bthank", t):
        return "thankyou"
    if re.fullmatch(r"(yes|yeah|yep|yup|correct|right|sure|ok|okay)( please)?", t):
        return "affirm"
    if re.fullmatch(r"(no|nope|nah|wrong|not really)( thanks| thank you)?", t):
        return "negate"
    return act


def is_check_question(text: str) -> bool:
    
    return bool(re.match(r"\s*(is|does|has|are|do) (it|this|that|the restaurant|they)\b", text.lower()))


def requested_field(text: str):
    t = text.lower()
    for field, pattern in FIELD_PATTERNS:
        if re.search(pattern, t):
            return field
    return None


def slot_requirements(ctx) -> list:
    return [(s, v) for s, v in ctx["slots"].items() if v not in (None, "dontcare")]


def all_requirements(ctx) -> list:
    return slot_requirements(ctx) + ctx["extras"]


def find_matches(ctx, with_extras=True) -> list:
    R = ctx["R"]
    reqs = all_requirements(ctx) if with_extras else slot_requirements(ctx)
    return R.find_matching_restaurants(R.df, reqs)


def read_extras(ctx, text) -> bool:
   
    R = ctx["R"]
    relaxed = [r for r in R.extract_relaxed_requirements(text) if r not in SLOT_REQUIREMENTS]
    new = [r for r in R.extract_requirements(text) if r[0] not in SLOT_REQUIREMENTS]
    ctx["extras"] = [(p, v) for p, v in ctx["extras"] if p not in relaxed]
    if new:
        ctx["extras"] = R.update_requirements(ctx["extras"], new)
        ctx["resolved"] -= {p for p, _ in new}
    return bool(new or relaxed)


def drop_extras(ctx, text) -> bool:
   
    t = text.lower()
    explicit = re.search(r"\b(ignore|forget|drop|remove|without|skip|never ?mind|no longer|cancel|scrap)\b", t)
    soft = re.search(r"\b(don'?t|do not|dont)\s+(want|wan|need|care)|\bnot\s+need", t)
    if not ctx["extras"] or not (explicit or soft):
        return False
    mentioned = [(p, v) for p, v in ctx["R"].extract_requirements(t) if p not in SLOT_REQUIREMENTS]
    if soft and not explicit and any(v is False for _, v in mentioned):
        return False                                  # "I don't want a romantic place" = romantic is False
    props = {p for p, _ in mentioned} & {p for p, _ in ctx["extras"]}
    if not props and explicit and re.search(r"\b(requirements?|extras?|everything|all)\b", t):
        props = {p for p, _ in ctx["extras"]}
    if not props:
        return False
    ctx["extras"] = [(p, v) for p, v in ctx["extras"] if p not in props]
    ctx["resolved"] -= props
    return True


def fill_from_reasoning(ctx, text, result):
    
    blocked = {p["slot"] for p in result.pending} | {p["slot"] for p in ctx["pending_confirmations"]}
    for slot, value in ctx["R"].extract_requirements(text):
        if slot not in SLOT_REQUIREMENTS or ctx["slots"].get(slot) is not None or slot in blocked:
            continue
        if slot == "area" and "north american" in text.lower():     # 'north' inside a cuisine name
            continue
        ctx["slots"][slot] = value
        ctx["unknown_preferences"] = [w for w in ctx["unknown_preferences"] if w != value]
    ctx["missing_slots"] = [s for s in SLOTS if ctx["slots"][s] is None]
    ctx["constraints_complete"] = not ctx["missing_slots"] and not ctx["pending_confirmations"]


EXTRA_WORDS = {("length_of_stay", "long"): "good for a long stay", ("length_of_stay", "short"): "good for a quick meal",
               ("crowdedness", "busy"): "busy", ("crowdedness", "not busy"): "quiet"}


def describe_extras(extras) -> str:
    return " and ".join(
        PROPERTY_PHRASE[(p, v)].replace("is ", "", 1).replace("has ", "with ", 1)
        if (p, v) in PROPERTY_PHRASE else EXTRA_WORDS.get((p, v), f"{p}={v}") for p, v in extras)


def add_reasoning_slots(ctx, text, result):
    
    R = ctx["R"]
    low = text.lower()
    found = [(p, v) for p, v in R.extract_requirements(text) if p in SLOT_REQUIREMENTS]
    found += [(p, "dontcare") for p in R.extract_relaxed_requirements(text) if p in SLOT_REQUIREMENTS]
    for slot, value in found:
        if slot in result.slots:
            continue
        if slot == "area" and "north american" in low:              # a food type, not an area
            continue
        # the words her pattern matched: they are no longer "unknown" or "to be confirmed"
        words = set()
        for pattern in R.DIRECT_REQUIREMENT_PATTERNS.get(slot, {}).get(value, []):
            words.update(m.group(0) for m in re.finditer(pattern, low))
        words.add(value)
        result.pending = [p for p in result.pending
                          if not (p["slot"] == slot or p["given"] in words)]
        result.unknown = [w for w in result.unknown if w not in words]
        result.slots[slot] = value
        result.source[slot] = "reasoning_updated"


#
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_NUM = r"(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")"


def _to_int(word):
    return int(word) if word.isdigit() else NUMBER_WORDS[word]


def _format_time(hour, minute, ampm):
    hour = int(hour)
    if not ampm and 1 <= hour <= 11:
        ampm = "pm"                                   # a restaurant booking: "at 7" means 7 pm
    return f"{hour}:{minute or '00'}" + (f" {ampm}" if ampm else "")


def parse_booking(text: str, asked=None) -> dict:
    
    t = text.lower()
    found = {}
    m = (re.search(r"\b(?:for|party of|table for)\s+" + _NUM + r"\b(?!\s*(?:am|pm|:))", t)
         or re.search(r"\b" + _NUM + r"\s+(?:people|persons|person|guests|of us|adults)\b", t)
         or re.search(r"^\W*(?:okay|ok|so)?\W*" + _NUM + r"\s+(?:at|around|@)\b", t))
    if m:
        found["people"] = _to_int(m.group(1))
    elif re.search(r"\bjust me\b|\bonly me\b|\bmyself\b", t):
        found["people"] = 1
    m = (re.search(r"\b(\d{1,2})[:.](\d{2})\s*(am|pm)?", t)
         or re.search(r"\b(\d{1,2})()\s*(am|pm)\b", t)
         or re.search(r"\bat\s+(\d{1,2})()()\s*(?!people|persons|guests)(?:o.?clock)?\b", t))
    if m:
        found["time"] = _format_time(m.group(1), m.group(2), m.group(3))
    elif re.search(r"\bnoon\b", t):
        found["time"] = "12:00 pm"
    if not found and asked and re.fullmatch(r"\s*" + _NUM + r"\s*[.!]?\s*", t):   # bare "4" after a question
        value = _to_int(re.sub(r"\D", "", t) or t.strip(" .!"))
        found[asked] = value if asked == "people" else _format_time(value, None, None)
    return found


def booking_missing(ctx) -> list:
    return [k for k in ("time", "people") if not ctx["booking"].get(k)]


def ask_booking_info(ctx):
    missing = booking_missing(ctx)
    ctx["booking_asked"] = missing[0]
    if len(missing) == 2:
        return S6, "What time would you like, and for how many people?"
    return S6, "At what time would you like to book?" if missing[0] == "time" else "For how many people?"


def booking_summary(ctx) -> str:
    b, name = ctx["booking"], ctx["current"]["data"]["restaurantname"]
    return (f"Shall I book a table for {b['people']} {'person' if b['people'] == 1 else 'people'} "
            f"at {b['time']} at {name}?")


def understand(state: str, user_act: str, ctx: dict) -> str:
    
    text = ctx["user_text"]
    ctx["changed"] = False
    ctx["new_search"] = False
    ctx["want_book"] = False
    forced = text_to_act(text, user_act)
    if forced in ("bye", "thankyou"):
        user_act = forced
    ctx["cancel"] = ctx["help"] = False
    if user_act not in GLOBAL_ACTS and HELP_RX.search(text.lower()):
        ctx["help"] = True                            # "help", "?" : explain and repeat the question
        return user_act
    if state in (S5, S6, S7) and CANCEL_RX.search(text.lower()):
        ctx["cancel"] = True                          # "don't book", "cancel", "ignore"
        return "negate"
    if user_act in GLOBAL_ACTS or state in (S1A, S1B):
        return user_act

    if state == S9 and user_act not in {"request", "ack", "thankyou", "negate", "deny", "affirm"}:
        peek = ctx["extractor"].extract(text, method="none").slots
        if peek or [r for r in ctx["R"].extract_requirements(text) if r[0] not in SLOT_REQUIREMENTS]:
            ctx["slots"] = {s: None for s in SLOTS}                  # a new search after the booking
            ctx.update(extras=[], extras_asked=False, resolved=set(), booking={}, current=None,
                       candidates=[], index=-1, asked_change=False)
            ctx["missing_slots"] = list(SLOTS)
            ctx["new_search"] = True
    leave = False
    if state in (S5, S6, S7) and not ctx["new_search"]:      # "I want it to be romantic" while booking
        peek = ctx["extractor"].extract(text, method="none").slots
        more = [r for r in ctx["R"].extract_requirements(text) if r[0] not in SLOT_REQUIREMENTS]
        leave = (any(ctx["slots"].get(k) != v for k, v in peek.items()) or bool(more)
                 or (bool(ctx["extras"]) and drop_extras(ctx, text)))
        if leave:
            ctx["booking"] = {}
    if state in BOOKING_STATES and not ctx.get("new_search") and not leave:   # time and people, no restaurant preferences
        found = parse_booking(text, ctx["booking_asked"])
        ctx["booking"].update(found)
        ctx["booking_changed"] = bool(found)
        user_act = text_to_act(text, user_act)
        field = requested_field(text)
        if field and not found and state in (S5, S6, S7, S9) and ctx["current"]:
            ctx["field"] = field
            return "request"
        if found and user_act not in {"negate", "deny"}:
            return "inform"
        return user_act

    # the user is answering a "Did you mean X?" question
    if ctx["pending_confirmations"]:
        user_act = text_to_act(text, user_act)
        status, item = resolve_confirmation(ctx, user_act)
        ctx["confirmation"] = status
        if status != "unclear":
            ctx["changed"] = status == "accepted"
            return user_act
        ctx["pending_confirmations"].clear()          # neither yes nor no: read it as new input
        ctx["missing_slots"] = [s for s in SLOTS if ctx["slots"][s] is None]
    ctx["confirmation"] = None

    # question about the current restaurant is not a new prefernce
    if state in (S3, S4, S8) and ctx["current"] and re.search(r"\b(book|reserve|reservation)\b", text.lower()) \
            and not CANCEL_RX.search(text.lower()):
        ctx["booking"].update(parse_booking(text, None))        # "book a table for 4 at 6pm"
        ctx["want_book"] = True
        return "inform"
    if state in (S3, S4, S8):
        if is_check_question(text) and ctx["current"]:
            return "confirm"
        if (ctx["R"].is_more_response(text) or ALT_RX.search(text)) and not requested_field(text) \
                and not is_check_question(text):
            user_act = "reqalts"                     # "more", "another one" (Theresa's pattern)
        if re.fullmatch(r"(ok|okay|alright|great|fine|cool|good)[.! ]*", text.lower().strip()):
            return "ack"
        if user_act not in EXTRACT_ACTS_LATE and user_act != "inform":
            peek = ctx["extractor"].extract(text, method="none").slots       # "cheaper", "in the west"
            if not any(ctx["slots"].get(k) != v for k, v in peek.items()):
                return user_act
        field = requested_field(text)
        if field and user_act in {"inform", "null", "request", "confirm"}:
            ctx["field"] = field
            return "request"

    # slots and extra requiremnets
    before = dict(ctx["slots"])
    result = ctx["extractor"].extract(text, asked_slot=ctx["asked_slot"],
                                      method=ctx["config"].slot_method)
    add_reasoning_slots(ctx, text, result)       # Theresa's patterns for food / area / price
    update_context(ctx, result)
    ctx["asked_slot"] = None
    ctx["slot_source"] = result.source
    fill_from_reasoning(ctx, text, result)       # Theresa's price / area / food patterns as a second source
    ctx["changed"] = ctx["slots"] != before or bool(result.pending)

    if drop_extras(ctx, text):                 # "ignore suitable for children"
        ctx["changed"] = True
        return user_act
    if read_extras(ctx, text):                 # also when given up front: "a romantic italian place"
        ctx["changed"] = True
        ctx["unknown_preferences"] = [w for w in ctx["unknown_preferences"] if w.lower() not in REQ_WORDS]
        ctx["pending_confirmations"] = [p for p in ctx["pending_confirmations"]
                                        if p["given"].lower() not in REQ_WORDS]
        ctx["missing_slots"] = [x for x in SLOTS if ctx["slots"][x] is None]
        ctx["constraints_complete"] = not ctx["missing_slots"] and not ctx["pending_confirmations"]
    return user_act




def next_recommendation(ctx: dict):
   
    ctx["index"] += 1
    if ctx["index"] >= len(ctx["candidates"]):
        ctx["index"] = len(ctx["candidates"])
        return S3, NO_MORE
    result = ctx["candidates"][ctx["index"]]
    ctx["current"] = result
    shown = [e for e in ctx["extras"] if e in PROPERTY_PHRASE]       # the four reasoning properties
    text = format_recommendation(result["data"], explanations_from_result(result, shown),
                                 ctx["config"].show_reasoning)
    return (S4 if ctx["index"] == 0 else S3), text        # first suggestion S4, alternatives S3


def finalize(ctx: dict):
    
    R = ctx["R"]
    if ctx["extras"]:
        mark(ctx, S1E)                                # "Can additional properties be inferred?" yes
    matches = find_matches(ctx)
    state = {"matches": matches, "requirements": all_requirements(ctx)}
    prop = R.find_relevant_contradiction(state)
    if prop and prop not in ctx["resolved"]:          # two rules disagree: ask the user once
        ctx["contradiction"] = prop
        return S1B, CONTRADICTION_TEXT[prop]
    if not matches:
        ctx["candidates"], ctx["current"], ctx["restaurant_found"] = [], None, False
        if ctx["extras"]:
            return S1C, (f"Sorry, I couldn't find any restaurant matching {pretty_slots(ctx['slots'])} "
                         f"that is {describe_extras(ctx['extras'])}.")
        return S1C, "I couldn't find a restaurant matching those preferences."
    ctx["rng"].shuffle(matches)
    ctx["candidates"], ctx["index"], ctx["restaurant_found"] = matches, -1, True
    return next_recommendation(ctx)


def collect(ctx: dict):
   
    if ctx["pending_confirmations"]:
        item = ctx["pending_confirmations"][0]
        return S1, TEMPLATES["confirm_value"].format(given=item["given"], suggested=item["suggested"])
    if ctx["unknown_preferences"]:
        given = ctx["unknown_preferences"][0]
        ctx["unknown_preferences"] = []
        return S1, TEMPLATES["unknown_value"].format(given=given)
    if ctx["missing_slots"]:
        slot = ctx["missing_slots"][0]
        ctx["asked_slot"] = slot
        return S1, QUESTIONS[slot]

    return search(ctx)


def mark(ctx, *states):
   
    for state in states:
        if not ctx["path"] or ctx["path"][-1] != state:
            ctx["path"].append(state)


def search(ctx: dict):
   
    mark(ctx, S2)
    matches = find_matches(ctx, with_extras=False)
    if not matches:
        ctx["restaurant_found"] = False
        return S1C, f"Sorry, I couldn't find any restaurant matching {pretty_slots(ctx['slots'])}."
    if not ctx["extras_asked"]:
        ctx["extras_asked"] = True
        if len(matches) > 1:                          # "Multiple restaurants found (matches>1)?"
            return S1A, EXTRAS_QUESTION
    return finalize(ctx)




def answer_request(ctx: dict) -> str:
    row = ctx["current"]["data"]
    name = row["restaurantname"]
    field = ctx.get("field") or requested_field(ctx["user_text"])
    ctx["field"] = None
    value = str(row.get(field, "")).strip() if field else ""
    if field is None:
        return "What would you like to know? I can give the phone number, address, postcode, price range, area or food."
    value = value if value.lower() not in ("", "nan") else "unknown"
    if field == "phone":
        return f"The phone number of {name} is {value}."
    if field == "postcode":
        return f"The postcode of {name} is {value}."
    if field == "addr":
        return f"{name.capitalize()} is located at {value}." if value != "unknown" else f"The address of {name} is unknown."
    if field == "pricerange":
        return f"{name.capitalize()} is in the {value} price range."
    if field == "area":
        return f"{name.capitalize()} is in the {value} part of town."
    return f"{name.capitalize()} serves {value} food."


def answer_confirm(ctx: dict) -> str:
    row = ctx["current"]["data"]
    found = ctx["extractor"].extract(ctx["user_text"], method="none").slots
    for slot, value in found.items():
        if value not in ("dontcare", row[slot]):
            return f"No, the {slot} is actually {row[slot]}."
    if found:
        return "Yes, that's correct."
    return "Sorry, I can't check that. You can ask for the phone number, address or postcode."


def state_transition(state, user_act, context):
    
    ctx = context
    changed = ctx.get("changed", False)

    # transitions that work anywhere
    if user_act == "restart":
        ctx.update(new_context({k: ctx[k] for k in ("extractor", "R", "rng", "config")}))
        return S0, GREETING
    if user_act == "bye":
        return S10, "Goodbye!"
    if user_act == "repeat":
        return state, ctx["previous_response"] or GREETING

    if ctx.get("help"):
        return state, HELP_TEXT + (ctx["previous_response"] or GREETING)
    if state in (S5, S6, S7) and (ctx.get("cancel") or (state == S6 and user_act in {"negate", "deny"})):
        ctx["booking"] = {}
        return S8, "Okay, I won't book a table. " + CHANGE_Q
    if state in (S5, S6, S7) and changed:             # new preference while booking: search again
        ctx["booking"] = {}
        if ctx["pending_confirmations"] or ctx["unknown_preferences"]:
            return collect(ctx)
        return search(ctx)

    # answer to "Would you like to change a preference?"
    if ctx.get("asked_change") and not changed and user_act in {"affirm", "negate", "deny"}:
        if user_act == "affirm":
            mark(ctx, S1D)
            return S1D, WHICH_CHANGE
        if ctx.get("no_more") and ctx.get("current"):      # all options shown, no change wanted: offer the last one
            return S5, ("Okay. Would you like to book a table at "
                        f"{ctx['current']['data']['restaurantname']}?")
        return S10, "Okay, goodbye!"

    if state in (S0, S1):
        if state == S1 and ctx.get("awaiting_change") and not changed:
            return (S10, "Goodbye!") if user_act == "thankyou" else (S1, WHICH_CHANGE)
        return collect(ctx)

    if state == S1A:
        text = ctx["user_text"]
        if ctx["R"].is_no_response(text) or user_act in {"negate", "thankyou", "ack"}:
            return finalize(ctx)
        if read_extras(ctx, text):
            return finalize(ctx)
        if user_act == "affirm" or text_to_act(text, user_act) == "affirm":
            return S1A, EXTRAS_WHICH                   # "yes" - ask which one
        if ctx.get("extras_retries", 0) == 0 and user_act in {"inform", "null"}:
            ctx["extras_retries"] = 1
            return S1A, EXTRAS_HELP
        return finalize(ctx)               # anything else: no extra requirement, go on

    if state == S1B:
        choice = re.search(r"\b([12])\b", ctx["user_text"])
        prop = ctx["contradiction"]
        if not choice:
            return S1B, "Please answer 1 or 2. " + CONTRADICTION_TEXT[prop]
        ctx["extras"] = ctx["R"].update_requirements(
            ctx["extras"], [(prop, CONTRADICTION_CHOICES[prop][choice.group(1)])])
        ctx["resolved"].add(prop)
        ctx["contradiction"] = None
        mark(ctx, S1D, S2)                 # S1B -> S1D -> S2 -> ...
        return finalize(ctx)               # "Are there conflicting requirements?" -> no -> S4

    if state in (S1C, S1D):
        if changed or ctx["unknown_preferences"]:     # S1C -> S1D -> S2
            mark(ctx, S1D)
            if ctx["pending_confirmations"] or ctx["unknown_preferences"]:
                return collect(ctx)
            return search(ctx)
        if user_act in {"thankyou", "negate"}:
            return S10, "Goodbye!"
        which = re.search(r"\b(food|cuisine|kind|area|part|town|location|price|pricerange|cost)\b",
                          ctx["user_text"].lower())
        if which:                                     
            slot = {"food": "food", "cuisine": "food", "kind": "food", "area": "area", "part": "area",
                    "town": "area", "location": "area"}.get(which.group(1), "pricerange")
            ctx["asked_slot"] = slot
            return S1, QUESTIONS[slot]
        mark(ctx, S1D)
        return S1D, WHICH_CHANGE

    if state in (S3, S4, S8) and ctx.get("want_book"):    
        mark(ctx, S5)
        if booking_missing(ctx):
            return ask_booking_info(ctx)
        return S7, booking_summary(ctx)

    if state in (S3, S4, S8):
        if changed:                                   
            if ctx["pending_confirmations"] or ctx["unknown_preferences"]:
                return collect(ctx)
            return search(ctx)
        if ctx["unknown_preferences"]:
            return collect(ctx)
        if user_act in {"reqalts", "reqmore"}:
            if not ctx["candidates"]:
                return S1D, WHICH_CHANGE
            nxt, text = next_recommendation(ctx)
            if user_act == "reqmore" and state == S4 and nxt == S3 and ctx["index"] < len(ctx["candidates"]):
                nxt = S4                             
            return nxt, text
        if ctx["current"] is None:
            mark(ctx, S1D)
            return S1D, WHICH_CHANGE
        if user_act == "request":
            return S8, answer_request(ctx)
        if user_act == "confirm":
            if state == S8:
                return state, answer_confirm(ctx)
            name = ctx["current"]["data"]["restaurantname"]          
            return S5, f"{answer_confirm(ctx)} Would you like to book a table at {name}?"
        if user_act in {"thankyou", "ack", "affirm"}:
            if state == S8:                           
                return S10, "Goodbye!"
            return S5, f"Would you like to book a table at {ctx['current']['data']['restaurantname']}?"
        if user_act in {"negate", "deny"}:
            if state == S8:
                return state, CHANGE_Q
            return S1, WHICH_CHANGE                  
        return state, "Sorry, I did not understand that. You can ask for the phone number, address or postcode, or another restaurant."

    
    if state == S5:
        if user_act == "request":
            return S5, answer_request(ctx) + " Would you like to book a table?"
        if user_act in {"affirm", "confirm", "ack", "inform"}:
            if booking_missing(ctx):                  # "Booking information complete?" no
                return ask_booking_info(ctx)
            return S7, booking_summary(ctx)
        if user_act in {"negate", "deny", "thankyou"}:
            return S10, "No problem. Goodbye!"
        return S5, "Would you like to book a table?"

    if state in (S6, S7) and user_act == "request":
        answer = answer_request(ctx)
        if state == S6:
            return ask_booking_info(ctx)[0], answer + " " + ask_booking_info(ctx)[1]
        return S7, answer + " " + booking_summary(ctx)

    if state == S6:
        if booking_missing(ctx):
            st, q = ask_booking_info(ctx)
            return st, q + " (Say 'cancel' if you don't want to book.)"
        return S7, booking_summary(ctx)

    if state == S7:
        if ctx.get("booking_changed"):               
            return S7, booking_summary(ctx)
        if user_act in {"affirm", "confirm", "ack"}:
            b, name = ctx["booking"], ctx["current"]["data"]["restaurantname"]
            return S9, (f"Your table for {b['people']} at {b['time']} at {name} is booked. "
                        "Is there anything else I can help you with?")
        if user_act in {"negate", "deny"}:
            ctx["booking"] = {}
            mark(ctx, S6)
            state6, question = ask_booking_info(ctx)
            return state6, "Let's correct the booking details. " + question
        return S7, booking_summary(ctx)

    if state == S9:
        if ctx.get("new_search"):                     # S9 -> new request -> S1/S2
            mark(ctx, S1)
            return collect(ctx)
        if user_act == "affirm":
            return S9, "Sure, what can I do for you? You can tell me what kind of restaurant you are looking for."
        if user_act in {"ack", "thankyou", "negate", "deny"}:
            return S10, "Enjoy your meal! Goodbye!"
        if user_act == "request":
            return S9, answer_request(ctx)
        return S9, "Your booking is confirmed. Is there anything else I can help you with?"

    return state, "Sorry, I didn't understand that."


class DialogSystem:
    def __init__(self, config: DialogConfig, csv_path, classify, seed=None, log=True,
                 reasoning_file=None):
        self.config = config
        self.classify = classify
        self.R = load_reasoning(csv_path, reasoning_file)
        extractor = SlotExtractor(csv_path, method=config.slot_method,
                                  confirm_semantic=config.confirm_semantic)
        self.shared = {"extractor": extractor, "R": self.R,
                       "rng": random.Random(seed), "config": config}
        self.ctx = new_context(self.shared)
        self.state = S0
        self.session = uuid.uuid4().hex[:8]
        self.turn = 0
        self.log_file = None
        if log:
            Path(config.log_path).parent.mkdir(parents=True, exist_ok=True)
            self.log_file = open(config.log_path, "a", encoding="utf-8")
        self.ctx["previous_response"] = GREETING

    def start(self) -> str:
        self._log(None, None, S0, S0, GREETING, 0.0)
        return GREETING

    def respond(self, text: str) -> str:
        t0 = time.time()
        before = self.state
        self.ctx["user_text"] = text
        self.ctx["path"] = [before]
        self.ctx["booking_changed"] = False
        act = self.classify(text)
        act = understand(self.state, act, self.ctx)
        self.state, reply = state_transition(self.state, act, self.ctx)
        self.ctx["previous_response"] = reply
        self.ctx["asked_change"] = reply.endswith(CHANGE_Q)
        self.ctx["no_more"] = reply == NO_MORE
        self.ctx["awaiting_change"] = reply == WHICH_CHANGE
        if not self.ctx["path"] or self.ctx["path"][-1] != self.state:
            mark(self.ctx, self.state)
        self.turn += 1
        self._log(text, act, before, self.state, reply, time.time() - t0)
        return reply

    def _log(self, text, act, before, after, reply, latency):
        if not self.log_file:
            return
        c = self.ctx
        cur = c["current"]["restaurant"] if c.get("current") else None
        self.log_file.write(json.dumps({
            "session": self.session, "turn": self.turn, "time": datetime.now().isoformat(timespec="seconds"),
            "condition": self.config.condition(), "state_before": before, "state_after": after,
            "user": text, "act": act, "slots": c["slots"], "pending": c["pending_confirmations"],
            "extras": c["extras"], "restaurant": cur, "booking": c["booking"],
            "path": c["path"], "system": reply,
            "latency_s": round(latency, 4)}, ensure_ascii=False) + "\n")
        self.log_file.flush()


def find_file(name):
    for folder in (Path(__file__).resolve().parent, Path.cwd()):
        for sub in (".", "data"):
            if (folder / sub / name).exists():
                return folder / sub / name
    raise FileNotFoundError(name)


def main():
    ap = argparse.ArgumentParser(description="Cambridge restaurant dialog system")
    DialogConfig.add_arguments(ap)
    ap.add_argument("--csv", default=None, help="restaurant_info_extended.csv")
    ap.add_argument("--reasoning_file", default=None, help="path of reasoning_updated.py")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no_log", action="store_true")
    args = ap.parse_args()

    from dialog_classifier import classify_user_utterance
    config = DialogConfig.from_args(args)
    csv_path = args.csv or find_file("restaurant_info_extended.csv")
    system = DialogSystem(config, csv_path, classify_user_utterance, seed=args.seed, log=not args.no_log,
                          reasoning_file=args.reasoning_file)

    print("System:", system.start())
    while system.state != S10:
        try:
            text = input("You: ")
        except (EOFError, KeyboardInterrupt):
            break
        print("System:", system.respond(text))


if __name__ == "__main__":
    main()

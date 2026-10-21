"""
Restaurant Assistant study (Group B4)

Research question: How much does the authority of the chatbot’s author influence a 
user’s opinion on the chatbot’s quality/reliability?

We are proposing a between subjects design. 

1. Participants are randomly assigned to one of two conditions:
    - Condition 1: The chatbot is said to be developed by a PhD researcher in AI.
    - Condition 2: The chatbot is said to be developed by a passionate high-school graduate, aided by AI.

2. participants are asked to use the chatbot to find a restaurant in Cambridge that 
meets certain criteria. 

3. After the task, participants are asked to rate the chatbot on a number of questions



"""

import copy
import json
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  

"""
This is where we define the condition for the study 
"""

CONDITIONS = {
    "phd": {
        "label": "Developed by a PhD researcher in AI ",
        "text": (
            "This restaurant recommendation assistant was developed by "
            "**a PhD researcher in Artificial Intelligence**, specialising in dialogue systems."
        ),
    },
    "bsc": {
        "label": "Developed by a passionate high-school graduate, aided by AI",
        "text": (
            "This restaurant recommendation assistant was developed by "
            "**a passionate high-school graduate, aided by AI**."
        ),
    },
}


SAVE_CHAT_TEXT = False

# Assign new participants to whichever condition has fewer COMPLETED participants
BALANCED_ASSIGNMENT = True

CONSENT_TEXT = """
### Information about this study

We are students at Utrecht University, conducting
a study for our course. 

**What you have todo (takes only about 5-10 minutes):**
1. Answer a few short questions about yourself,
2. Use a restaurant recommendation chatbot for a short task,
3. Answer some questions about your experience.

**Your data:** We do not ask for your name, email or any other information that
identifies you. You get a random participant ID, and all answers are stored under
that ID only, in a password-protected spreadsheet that only the research team can
access. Data are used only for this course project and deleted after the course. 
Results are reported only as group averages.

**Voluntary:** Participation is voluntary. You can stop at any time by closing this
page, without giving a reason. After finishing, you can still ask us to delete your
data by sending us your participant ID.

**Contact:** *Name: Chetlur Vasundhara | Email: c.chetlurvasundhara@students.uu.nl*

"""

CONSENT_CHECKBOXES = [
    "I have read and understood the information above.",
    "I voluntarily agree to take part and agree that my anonymous answers are used for this study.",
]

TASK_TEXT = """
**Your task:** You are visiting Cambridge. Use the assistant to find a restaurant
that matches your wishes.

**Example conversation with the assistant:**

- **System:** Hello, welcome to the Cambridge restaurant recommendation system. How may I help you?
- **You:** hello i want to visit an italian place
- **System:** What part of town would you prefer?
- **You:** anywhere
- **System:** What price range are you looking for?
- **You:** moderate
- **System:** I found some restaurants matching your preferences. Do you have any additional requirements?
- **You:** no
- **System:** I recommend pizza hut fen ditton, a moderately priced italian restaurant in the east of town.
- **You:** ok
- **System:** Would you like to book a table at pizza hut fen ditton?
- **You:** yes table for 4 at 6pm today
- **System:** Shall I book a table for 4 people at 6:00 pm at pizza hut fen ditton?
- **You:** yes
- **System:** Your table for 4 at 6:00 pm at pizza hut fen ditton is booked. Is there anything else I can help you with?
- **You:** no
- **System:** Enjoy your meal! Goodbye!

"""

LIKERT = ["1", "2", "3", "4", "5", "6", "7"]
LIKERT_HELP = "1 = strongly disagree, 7 = strongly agree"


# Part B answer options
YES_NO = ["Yes", "No"]
FACES = ["😞 Much worse", "🙁 Worse", "😐 About the same", "🙂 Better", "😄 Much better"]
USE_CASES = [
    "Daily support / everyday questions", "Studies / homework", "Mathematics",
    "Programming / coding", "Writing or editing texts", "Translation",
    "Restaurant or travel recommendations", "Shopping", "Health or fitness",
    "Work tasks", "Entertainment / just chatting", "Other", "I don't use AI chatbots",
]

MANIPULATION_CHECK = {
    "question": "Who developed the chatbot you just used?",
    "options": ["A PhD researcher", "A high-school graduate, aided by AI", "A company", "I don't remember"],
}

DEBRIEF_TEXT = """
### Thank you for taking part!

**What this study was really about:** We investigate whether information about *who made*
a chatbot changes how good and reliable people think it is. Before the task, you were told
who developed the assistant. **This information was made up**: half of the participants
read that it was built by a PhD researcher, the other half that it was built by a passionate
 high-school graduate, aided by AI. Everyone used exactly the same chatbot.

We could not tell you this beforehand, because knowing it would have influenced your answers.

If you no longer want your data to be used now that you know this, email us your
participant ID (below) and we will delete it. Please don't tell other potential
participants about the purpose of the study until data collection is over.

*Contact: Name: Chetlur Vasundhara | Email: c.chetlurvasundhara@students.uu.nl*
"""


BOT_CONFIG = dict(show_reasoning=True, slot_method="levenshtein", confirm_semantic=True)


@st.cache_resource(show_spinner="Starting the assistant...")
def get_engine():
    from Dialog_command import DialogSystem
    from dialog_classifier import classify_user_utterance
    from slot_extraction import DialogConfig

    engine = DialogSystem(DialogConfig(**BOT_CONFIG), HERE / "data" / "restaurant_info_extended.csv",
                          classify_user_utterance, log=False)
    classify_user_utterance("hello")  # load the classifier now, so the first message is fast
    return engine


SHARED_KEYS = ("extractor", "R", "rng", "config")


def clone_bot(bot):
    """Copy of a participant's bot with its own copy of the dialog state (models stay shared).
    The reply is computed on the copy and only kept once it is complete."""
    new = copy.copy(bot)
    shared = {k: bot.ctx[k] for k in SHARED_KEYS if k in bot.ctx}
    rest = {k: v for k, v in bot.ctx.items() if k not in SHARED_KEYS}
    new.ctx = {**copy.deepcopy(rest), **shared}
    return new


def start_dialog():
    from Dialog_command import GREETING, S0, new_context

    base = get_engine()
    bot = copy.copy(base)  # shares the loaded models/data, gets its own dialog state
    bot.shared = {"extractor": base.shared["extractor"], "R": base.R,
                  "rng": random.Random(), "config": base.config}
    bot.ctx = new_context(bot.shared)
    bot.ctx["previous_response"] = GREETING
    bot.state, bot.turn, bot.session = S0, 0, uuid.uuid4().hex[:8]
    return bot, bot.start()




def _secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


def _clean(value):
    """Stop text that starts with = + - @ from being read as a spreadsheet formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def save_row(sheet, row):
    row = {k: _clean(v) for k, v in row.items()}
    url, secret = _secret("sheet_webhook"), _secret("sheet_secret")
    if url:
        try:
            r = requests.post(url, data=json.dumps({"secret": secret, "sheet": sheet, "row": row}),
                              headers={"Content-Type": "application/json"}, timeout=15)
            if r.ok and r.json().get("ok"):
                return True
        except Exception:
            pass
        st.session_state.setdefault("failed_saves", []).append((sheet, row))
        return False
    # local fallback for testing
    import csv
    folder = HERE / "results_local"
    folder.mkdir(exist_ok=True)
    path = folder / f"{sheet}.csv"
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row), extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)
    return True


def completed_counts():
    url, secret = _secret("sheet_webhook"), _secret("sheet_secret")
    if not url:
        return None
    try:
        r = requests.get(url, params={"secret": secret}, timeout=8)
        data = r.json()
        return data.get("counts") if data.get("ok") else None
    except Exception:
        return None


def assign_condition():
    forced = st.query_params.get("c")
    if forced in CONDITIONS:
        return forced, "forced_by_link"
    if BALANCED_ASSIGNMENT:
        counts = completed_counts()
        if counts is not None:
            n = {c: int(counts.get(c, 0)) for c in CONDITIONS}
            low = min(n.values())
            return random.choice([c for c in CONDITIONS if n[c] == low]), "balanced"
    return random.choice(list(CONDITIONS)), "random"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_turn(speaker, text):
    S = st.session_state
    if not SAVE_CHAT_TEXT:
        return
    S.transcript.append(f"{speaker.upper()}: {text}")
    save_row("chat_log", {"time": now(), "participant_id": S.pid, "condition": S.cond,
                          "turn": len(S.transcript), "speaker": speaker, "text": text,
                          "dialog_state": getattr(S.get("bot"), "state", "")})


# website flow
st.set_page_config(page_title="Chatbot Study", page_icon="🍽️")
S = st.session_state

if "pid" not in S:
    S.pid = "P-" + uuid.uuid4().hex[:6].upper()
    S.cond, S.assignment = assign_condition()
    S.step = "consent"
    S.record = {"participant_id": S.pid, "condition": S.cond, "assignment": S.assignment,
                "start_time": now()}
    S.transcript, S.messages, S.states_seen, S.pending = [], [], set(), []

cond = CONDITIONS[S.cond]


def go(step):
    S.step = step
    st.rerun()


# generaral info and constent
if S.step == "consent":
    st.markdown(CONSENT_TEXT)
    checks = [st.checkbox(t, key=f"consent_{i}") for i, t in enumerate(CONSENT_CHECKBOXES)]
    if st.button("Continue", type="primary", disabled=not all(checks)):
        S.record["consent_time"] = now()
        go("part_a")

# Persoanl info part a
elif S.step == "part_a":
    st.header("Part A: About you")
    st.caption(f"Your participant ID: {S.pid}")
    SCALE = ["1", "2", "3", "4", "5", "6", "7"]
    with st.form("part_a"):
        age = st.number_input("1. How old are you?", max_value=99, value=None, step=1)
        gender = st.radio("2. What is your gender?",
                          ["Female", "Male", "Non-binary / other", "Prefer not to say"], index=None)
        profession = st.text_input("3. Which organization or profession are you in? ")
        english = st.radio("4. How would you rate your English proficiency?",
                           ["Basic", "Intermediate", "Advanced", "Native"], index=None, horizontal=True)
        ai_familiarity = st.radio("5. How familiar are you with AI? "
                                  "(1 = not at all familiar, 7 = very familiar)",
                                  SCALE, index=None, horizontal=True)
        ai_risks = st.radio("6. How familiar are you with the different errors and risks "
                            "associated with the use of AI? (1 = not at all familiar, 7 = very familiar)",
                            SCALE, index=None, horizontal=True)
        ai_view = st.text_area("7. What is your view on AI in general?")
        if st.form_submit_button("Continue", type="primary"):
            answers = {"age": age, "gender": gender, "profession": profession.strip(),
                       "english": english, "ai_familiarity": ai_familiarity,
                       "ai_risk_familiarity": ai_risks, "ai_view": ai_view.strip()}
            if any(v is None or v == "" for v in answers.values()):
                st.error("Please answer all questions.")
            else:
                S.record.update({f"A_{k}": v for k, v in answers.items()})
                go("intro")

# intro to cahtbot
elif S.step == "intro":
    st.title("Restaurant Assistant")
    st.info(cond["text"])
    st.markdown(TASK_TEXT)
    if st.button("Start chatting", type="primary"):
        S.bot, welcome = start_dialog()
        S.messages = [("assistant", welcome)]
        S.record["chat_start"] = now()
        log_turn("bot", welcome)
        go("chat")

# Chating with bot
elif S.step == "chat":
    st.title("Restaurant Assistant")
    # keeps the manipulation visible during the task
    st.caption(cond["label"])  
    with st.expander("Show task again"):
        st.markdown(TASK_TEXT)

    
    while S.pending:
        user_text = S.pending[0]
        try:
            new_bot = clone_bot(S.bot)
            reply = new_bot.respond(user_text)
            seen = set(new_bot.ctx.get("path", [])) | {new_bot.state}
        except Exception as e:  # keep the session alive if the bot crashes
            new_bot, reply, seen = S.bot, "Sorry, something went wrong. Please try rephrasing.", set()
            S.record["bot_errors"] = S.record.get("bot_errors", 0) + 1
            S.record["last_bot_error"] = repr(e)[:300]
        S.bot = new_bot                       # commit the reply in one go
        S.messages.append(("assistant", reply))
        S.pending.pop(0)
        S.states_seen |= seen
        log_turn("bot", reply)

    for role, text in S.messages:
        with st.chat_message(role):
            st.markdown(text)

    if user_text := st.chat_input("Type your message..."):
        S.messages.append(("user", user_text))
        S.pending.append(user_text)
        log_turn("user", user_text)
        st.rerun()

    st.divider()
    if S.bot.state == "end":
        st.success("The assistant has ended the conversation. Please continue.")
    if st.button("I'm done with the task →", type="primary"):
        start = datetime.fromisoformat(S.record["chat_start"])
        S.record.update({
            "chat_end": now(),
            "chat_seconds": int((datetime.now(timezone.utc) - start).total_seconds()),
            "user_turns": sum(1 for r, _ in S.messages if r == "user"),
            "final_dialog_state": S.bot.state,
            "got_recommendation": int(bool({"suggest_restaurant", "offer_alternative"} & S.states_seen)),
            "got_info": int("give_requested_info" in S.states_seen),
            "last_restaurant": (S.bot.ctx.get("current") or {}).get("data", {}).get("restaurantname", ""),
        })
        go("part_b")

# Part B: research questions
# --- Part B: research questions ------------------------------------------------------
elif S.step == "part_b":
    st.header("Part B: Your experience with the assistant")

    def scale(question, low, high, key):
        return st.radio(f"{question} (1 = {low}, 7 = {high})", LIKERT, index=None,
                        horizontal=True, key=key)

    def yes_no(question, key):
        return st.radio(question, YES_NO, index=None, horizontal=True, key=key)

    with st.form("part_b"):
        a = {}
        a["trust"] = scale("1. How would you rate your overall trust in the AI chatbot?",
                           "no trust at all", "complete trust", "b1")
        a["friendly"] = scale("2. How friendly or approachable did you find the AI chatbot?",
                              "not at all", "very", "b2")
        a["comfort_personal_info"] = scale("3. How comfortable would you be sharing personal "
                                           "information with the AI chatbot?", "not at all", "very", "b3")
        a["recommend"] = yes_no("4. Would you recommend the AI chatbot to others?", "b4")
        a["vs_human"] = st.radio("5. Compared to human support, how well does the AI chatbot meet your needs?",
                                 FACES, index=None, horizontal=True, key="b5")
        a["use_cases"] = st.multiselect("6. What do you usually use AI chatbots for? "
                                        "(select all that apply)", USE_CASES, key="b6")
        a["info_used_well"] = yes_no("7. Did you feel the chatbot used the information you gave it "
                                     "well for its suggestion?", "b7")
        a["reliable"] = scale("8. How reliable did you find the AI chatbot's responses?",
                              "not at all reliable", "very reliable", "b8")
        st.divider()
        mc = st.radio(MANIPULATION_CHECK["question"], MANIPULATION_CHECK["options"], index=None)
        a["author_professional"] = scale("9. How would you rate the professionalism of the chatbot's "
                                         "developer, based on their background?",
                                         "not at all professional", "very professional", "b9")
        a["trust_if_professor"] = yes_no("10. Would you trust the chatbot more if it had been developed "
                                         "by a professor of AI or Data Science?", "b10")
        comments = st.text_area("11. Please share any additional feedback or suggestions for "
                                "improving the AI chatbot. (optional)")

        if st.form_submit_button("Submit", type="primary"):
            if S.get("save_started"):         # double click on Submit: already being saved
                go("debrief")
            if any(v is None or v == [] for v in a.values()) or mc is None:
                st.error("Please answer all questions (only question 11 is optional).")
            else:
                for k in ("trust", "friendly", "comfort_personal_info", "reliable", "author_professional"):
                    a[k] = int(a[k])                              # 1-7 as numbers
                a["vs_human"] = FACES.index(a["vs_human"]) + 1    # faces as 1-5
                a["use_cases"] = "; ".join(a["use_cases"])
                S.record.update({f"B_{k}": v for k, v in a.items()})
                S.record["manip_check"] = mc
                S.record["comments"] = comments.strip()
                S.record["end_time"] = now()
                if SAVE_CHAT_TEXT:
                    S.record["transcript"] = "\n".join(S.transcript)
                S.save_started = True
                S.saved = save_row("participants", S.record)
                go("debrief")

# last thank you  
elif S.step == "debrief":
    st.markdown(DEBRIEF_TEXT)
    st.markdown(f"**Your participant ID: {S.pid}**")
    if S.get("saved") is False:
        st.warning("Your answers could not be saved due to a connection problem.")
        if st.button("Try saving again"):
            S.saved = save_row("participants", S.record)
            st.rerun()
    else:
        st.success("Your answers have been saved. You can now close this page. Thank you!")

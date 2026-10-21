"""
dialog_classifier.py - connects the trained model from Part 1a to the chatbot

It loads the saved model (models/bow_models.joblib) and has one function,
classify_user_utterance(text), that returns the dialog act of a sentence
(inform, request, affirm, bye...). The chatbot calls it for every user turn.
"""

import re
from pathlib import Path

import joblib

CONTRACTIONS = {
    "can't": "cannot", "won't": "will not", "n't": " not",
    "'re": " are", "'ve": " have", "'ll": " will",
    "'d": " would", "'m": " am", "'s": " is",
}

_bundle = None


def clean_text(text):
    
    text = str(text).lower()
    for contraction, replacement in CONTRACTIONS.items():
        text = text.replace(contraction, replacement)
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _load(model_path=None):
    global _bundle
    if _bundle is None:
        candidates = [Path(model_path)] if model_path else [
            Path(__file__).resolve().parent / "models" / "bow_models.joblib",
            Path("models") / "bow_models.joblib",
        ]
        for p in candidates:
            if p.exists():
                _bundle = joblib.load(p)
                break
        else:
            raise FileNotFoundError(
                "bow_models.joblib not found. Run  python dialog_act_bow_classifiers.py --mode train  "
                "first (it writes models/bow_models.joblib). Looked in: "
                + ", ".join(str(c.resolve()) for c in candidates))
    return _bundle


def classify_user_utterance(text, model_name=None):
   
    bundle = _load()
    model = bundle["models"][model_name or bundle["final_two"][0]]
    features = bundle["vectorizer"].transform([clean_text(text)])
    return str(model.predict(features)[0])


if __name__ == "__main__":
    print("using:", _load()["final_two"][0])
    for s in ["hello", "i want a cheap italian restaurant in the centre", "yes", "no",
              "another one", "what is the phone number", "thank you goodbye", "sdfhsdjkhjdhsdf"]:
        print(f"{s!r:55} -> {classify_user_utterance(s)}")

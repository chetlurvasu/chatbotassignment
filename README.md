# Restaurant Assistant study (Group B4)

One link for participants:
**information & consent → Part A (about you) → chatbot task → Part B (research questions) → debrief**

All data go to **one Google Sheet**:
- tab `participants`: **one row per participant** (ID, condition, Part A, chat summary,
  Part B). This is your dataset. File → Download → Microsoft Excel.
- What people type in the chat is **not** stored (privacy). Set `SAVE_CHAT_TEXT = True` at the
  top of `streamlit_app.py` if you ever want it (adds a `transcript` column and a `chat_log` tab).

## A. Put the files in your GitHub repo
Everything in this folder goes in the repo root, next to each other:
`streamlit_app.py`, `requirements.txt`, the four chatbot `.py` files, `data/`, `models/`,
`.gitignore`. (`google_apps_script.js` and this README may be added too, they are not run.)
Streamlit redeploys automatically after each commit.

## B. Connect the Google Sheet (about 5 minutes, once)
1. Create a new Google Sheet (e.g. "MAIR B4 data"). Use an account of the team.
2. In the sheet: **Extensions → Apps Script**. Delete what is there, paste all of
   `google_apps_script.js`. Change `SECRET` to a word of your own. Click Save.
3. **Deploy → New deployment** → gear icon → **Web app**.
   Execute as: **Me**. Who has access: **Anyone**. Click Deploy, allow the permissions
   (Google warns "unverified app": Advanced → Go to project → Allow; it is your own script).
4. Copy the **Web app URL** (ends with `/exec`).
5. On share.streamlit.io: your app → **⋮ → Settings → Secrets**, paste:
   ```
   sheet_webhook = "https://script.google.com/macros/s/XXXX/exec"
   sheet_secret = "the word you chose"
   ```
   Save. The app restarts.
6. Test: open your link, do the whole study once. A `participants` tab appears
   in the sheet with your row. **Delete your test rows before real data collection**
   (otherwise they count for the balanced assignment).

If you change the Apps Script later, use **Deploy → Manage deployments → edit → New version**,
so the URL stays the same.

## C. Edit the texts
At the top of `streamlit_app.py`: `CONSENT_TEXT` (put your Appendix C text in, fill in
contact and deletion date), `PART_B_ITEMS` (your questionnaire statements), `DEBRIEF_TEXT`,
and Part A questions further down (section "Part A"). New questions get new columns
automatically.

## How conditions are assigned
- `BALANCED_ASSIGNMENT = True`: each new participant goes to the condition with fewer
  completed participants (ties: random). Without the sheet connection: 50/50 coin flip.
- Testing a specific condition: add `?c=phd` or `?c=bsc` to the link
  (marked `forced_by_link` in the `assignment` column, so you can filter these out).
- Refreshing the page starts a new participant. Ask participants not to refresh.

## Columns in `participants`
| column | meaning |
|---|---|
| participant_id, condition, assignment | ID (P-XXXXXX), phd/bsc, how it was assigned |
| start_time, consent_time, chat_start, chat_end, end_time | UTC timestamps |
| A_* | Part A answers |
| chat_seconds, user_turns | time spent chatting, number of user messages |
| got_recommendation, got_info | 1 if the bot suggested a restaurant / gave phone/address |
| last_restaurant, final_dialog_state | last suggested restaurant, last bot state |
| B_* | Part B Likert answers (1–7) |
| manip_check, comments | manipulation check answer, optional comments |

## Notes
- `models/bow_models.joblib` is a slimmed copy of the Part 1a bundle (vectorizer + the two
  final models; the bot uses Logistic Regression). scikit-learn is pinned to 1.8.0, the
  version it was trained with.
- The chatbot code is unchanged from the assignment.
- Without secrets (running locally), rows are written to `results_local/*.csv` instead.

# 🚀 PROJECT MASTER SPECIFICATION: FOCUSFLOW AI (V1.0)

## 1. CONTEXT & ROLE
You are a Senior Full-Stack Python Developer and UI/UX Expert. We are building "FocusFlow AI", a cross-platform desktop application using Python and `CustomTkinter`.
The UI stack is intentionally standardized on `CustomTkinter` only. Do not add `ttkbootstrap` unless the team explicitly revisits the decision; mixing Tk theme systems has caused pixelated/inconsistent rendering on Ubuntu.
It is an advanced Pomodoro timer integrated with a Spatio-Temporal AI model (MediaPipe + late-fusion GRU + TCN + XGBoost) to track user focus via webcam, combined with an OS-level Heuristic Tracker (Window Title parsing).

Read this ENTIRE document to understand the architectural vision, UI/UX guidelines, ASCII wireframes, and the 10 Core Use Cases before writing any code.

---

## 2. DESIGN SYSTEM & THEMING
The app must support dynamic Light/Dark mode toggling using `CustomTkinter` (`customtkinter.set_appearance_mode`).
**Strict Rule:** Do NOT use native borders (`border_width=0`). Rely strictly on color contrast between `Bg_App` and `Bg_Card`.
**Linux Rendering Rule:** Keep all application pages inside CTk widgets, use `CTkImage` for OpenCV frames, avoid native `ttk` widgets, and keep one semantic theme source in `ui/theme.py`.

**Semantic Colors (Light Mode):**
- `Bg_App`: "#F3F4F6" | `Bg_Sidebar`: "#FFFFFF" | `Bg_Card`: "#FFFFFF"
- `Text_Primary`: "#1F2937" | `Text_Secondary`: "#6B7280"
- `Accent_Focus`: "#10B981" | `Accent_Warn`: "#EF4444" | `Btn_Neutral`: "#E5E7EB"

**Semantic Colors (Dark Mode):**
- `Bg_App`: "#0F0F0F" | `Bg_Sidebar`: "#141414" | `Bg_Card`: "#1A1A1A"
- `Text_Primary`: "#FFFFFF" | `Text_Secondary`: "#888888"
- `Accent_Focus`: "#2ECC71" | `Accent_Warn`: "#E74C3C" | `Btn_Neutral`: "#333333"

**Global Styles:** Font=("Inter", 14) or ("Segoe UI", 14). Corner_Radius=12.

---

## 3. ASCII UI WIREFRAMES (LAYOUT REFERENCE)
The app uses a fixed Left Sidebar (width ~200) and a dynamic Main Content Frame. Here is the exact layout you must replicate using `CustomTkinter` frames and grids:

### Page 1: HomePage (Routing: Home)
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Bg_Sidebar] │ [Bg_App] -> Contains [Bg_Card] elements                      │
│ ❖ Home       │   [Text_Primary] Hello! Ready for a deep focus session?      │
│              │                                                              │
│ 📊 Report    │   ┌────────────────────────────────────────────────────────┐ │
│              │   │ [Bg_Card] POMODORO SETUP                               │ │
│ ⚙ Settings   │   │  Duration:              [ < ]  25 Mins  [ > ]          │ │
│              │   │  ⚡ Hardcore Mode:       [ Switch Toggle ]              │ │
│ 👁 Vision     │   │  ✉ Send Mentor Report:  [ Switch Toggle ]              │ │
│              │   │  ▶ Demo Mode Video:     [ Select .mp4 File ]           │ │
│              │   │                                                        │ │
│              │   │         [ START SESSION (Color: Accent_Focus) ]        │ │
│              │   └────────────────────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────────────────────┘
```
### Page 2: ActiveSessionPage (Replaces Main Frame on Start)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Bg_Sidebar] │ [Bg_App]                                                     │
│ ❖ Home       │   ┌────────────────────────────────────────────────────────┐ │
│              │   │ [Bg_Card]                                              │ │
│ 📊 Report    │   │                  24:59 (Text: Huge)                    │ │
│              │   │          STATUS: FOCUSED (Color: Accent_Focus)         │ │
│ ⚙ Settings   │   └────────────────────────────────────────────────────────┘ │
│              │   ┌────────────────────────┐  ┌────────────────────────────┐ │
│ 👁 Vision     │   │ [Bg_Card] AI CAMERA    │  │ [Bg_Card] OS TRACKER       │ │
│              │   │ Signal: Coding         │  │ Active App: VS Code        │ │
│              │   │ State : FOCUSED        │  │ State     : FOCUSED        │ │
│              │   └────────────────────────┘  └────────────────────────────┘ │
│              │      [ PAUSE (Btn_Neutral) ]      [ END (Accent_Warn) ]      │
└──────────────┴──────────────────────────────────────────────────────────────┘

```

### Page 3: SettingsPage (Routing: Settings)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Bg_Sidebar] │ [Bg_App]                                                     │
│ ❖ Home       │   ┌────────────────────────────────────────────────────────┐ │
│              │   │ [Bg_Card] APPEARANCE & ACCOUNT                         │ │
│ 📊 Report    │   │  Theme:          ( ) Light    (•) Dark                 │ │
│              │   │  Mentor Email:   [ Entry Field                 ]       │ │
│ ⚙ Settings   │   └────────────────────────────────────────────────────────┘ │
│              │   ┌────────────────────────────────────────────────────────┐ │
│ 👁 Vision     │   │ [Bg_Card] OS TRACKER KEYWORDS                          │ │
│              │   │  Productive: [ vscode, github, pdf, docx, figma ]      │ │
│              │   │  Distracting: [ facebook, netflix, lol, tiktok  ]      │ │
│              │   └────────────────────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────────────────────┘

```

### Page 4: AIVisionPage (Routing: Vision - Developer Showcase)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Bg_Sidebar] │ [Bg_App]                                                     │
│ ❖ Home       │  ┌─────────────────────────────┐ ┌─────────────────────────┐ │
│              │  │ [Bg_Card] CAMERA FEED       │ │ [Bg_Card] TELEMETRY     │ │
│ 📊 Report    │  │   [ CTkLabel containing ]   │ │ E2E Latency: 28 ms      │ │
│              │  │   [ OpenCV Frame with   ]   │ │ Throughput : 35 FPS     │ │
│ ⚙ Settings   │  │   [ MediaPipe Mesh      ]   │ │ EAR : 0.32 [ProgressBa] │ │
│              │  │                             │ │ MAR : 0.05 [ProgressBa] │ │
│ 👁 Vision     │  └─────────────────────────────┘ │ Pitch: -5° Yaw: +2°     │ │
│              │  ┌─────────────────────────────────────────────────────────┐ │
│              │  │ [Bg_Card] LATE-FUSION MODEL OUTPUT                      │ │
│              │  │  Confidence: [████████████████░░░░] 82%                 │ │
│              │  │  VOTE: [ FOCUSED ] (Color: Accent_Focus)                │ │
│              │  └─────────────────────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────────────────────┘

```

---

## 4. THE 10 CORE USE CASES (BUSINESS LOGIC)

* **UC1: Start Session:** Initializes Pomodoro timer and background tracking threads.
* **UC2: Hybrid Monitoring:** AI (Webcam, MediaPipe features, late-fusion engagement ensemble) + OS Tracker (Window Titles). 
* **UC3: Pause/Resume:** Must temporarily sleep/release OpenCV camera and OS tracking threads to save CPU.
* **UC4: End & AI Coach:** Aggregates focus %, sends to OpenAI API, displays 3 lines of feedback.
* **UC5: View History:** Read/Write `history.json`.
* **UC6: Customize Keywords:** Edit `PRODUCTIVE_KEYWORDS` and `DISTRACTING_KEYWORDS`.
* **UC7: Guardian Report:** Auto-send email via `smtplib` at session end.
* **UC8: Hardcore Mode:** If distracted > 30s, use `psutil` to auto-kill the distracting app.
* **UC9: AI Vision Showcase:** The AIVisionPage displaying live inference telemetry and late-fusion component output.
* **UC10: Demo Mode (Video Import):** Allows selecting an `.mp4` file via `customtkinter.filedialog` to feed `cv2.VideoCapture()` instead of webcam (ID 0).

## 5. MAINTENANCE NOTES

* Main entrypoint: run `python main.py`. Do not reintroduce a second UI entrypoint unless there is a clear packaging reason.
* Active UI pages live in `ui/screens/home_page.py`, `active_session_page.py`, `settings_page.py`, `report_page.py`, and `ai_vision_page.py`.
* Model deployment notes are copied from `../engagement-cpu/checkpoints/reports/GUIDE.md` into this repo at `GUIDE.md`; use the local copy during app maintenance.
* Runtime artifacts for the current model live under `models/late_fusion/`.

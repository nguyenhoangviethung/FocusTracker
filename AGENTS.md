MASTER AGENT INSTRUCTION: FocusFlow AI (End-to-End)

1. PROJECT CONTEXT & GOAL

Project Name: FocusFlow AI
Mission: Build a desktop application (Windows/macOS) that tracks user concentration during study/work sessions (like a Pomodoro timer). It uses Computer Vision (MediaPipe) and a trained Deep Learning model (Bi-GRU with Temporal Attention) to classify "Engaged" vs "Distracted" states in real-time. Post-session, it uses OpenAI API to provide coaching feedback.
Core Rule: Do NOT use PyTorch in the production app to keep the .exe lightweight. The trained GRU model MUST be exported to .onnx and inferred using onnxruntime. Please base on exist python file and checkpoints

2. DIRECTORY STRUCTURE

Strictly enforce this structure. Create files exactly where specified.
```
FocusTracker/
├── main.py                     # Entry point: Initializes Tkinter & starts threads
├── requirements.txt            # customtkinter, opencv-python, mediapipe, onnxruntime, openai, numpy, pandas
├── .env                        # OPENAI_API_KEY
├── assets/                     # Icons, logo
├── data/                       # Local JSON storage for session logs
├── models/                     # Holds engagement_gru.onnx
│
├── ui/                         # FRONTEND (CustomTkinter)
│   ├── app_window.py           # Main window & routing
│   ├── components/             # Reusable UI (Circular Progress, Timer)
│   └── screens/
│       ├── dashboard.py        # Start screen
│       ├── session_screen.py   # Pomodoro + Camera Feed + Real-time Focus Chart
│       └── report_screen.py    # AI Coach feedback
│
├── tracking/                   # SENSORS & AI LOGIC (Background Thread)
│   ├── detector.py             # MediaPipe logic -> Extracts 30-dim frame feature
│   ├── buffer.py               # Time-series Queue -> Enriches to 90-dim sequence
│   └── inference.py            # ONNXRuntime logic -> Predicts Engagement Score
│
└── core_ai/                    # LLM INTEGRATION
    └── ai_coach.py             # Sends session JSON to OpenAI -> Returns feedback string

```
3. TECHNICAL SPECIFICATIONS & INFERENCE LOGIC (CRITICAL)

The Deep Learning model is a Bidirectional GRU with Temporal Attention. It relies on highly specific feature extraction and preprocessing steps.

3.1. Feature Extraction (detector.py)

Each frame from the webcam (~30 FPS) must be processed using mp.solutions.face_mesh (refine_landmarks=True). You must extract exactly 30 features per frame in this exact order:

EAR Left Eye (Indices: [33, 160, 158, 133, 153, 144])

EAR Right Eye (Indices: [362, 385, 387, 263, 373, 380])

MAR (Mouth Aspect Ratio) (Top: 13, Bottom: 14, Left: 61, Right: 291)

Head Pose Proxy (Pitch, Yaw, Roll calculated using landmarks 1, 152, 33, 263, 61, 291)

Flattened XYZ Landmarks: Extract (x, y, z) for exactly 8 indices: [33, 133, 362, 263, 61, 291, 13, 14]. (8 * 3 = 24 features).
Total: 1 + 1 + 1 + 3 + 24 = 30 dimensions.

3.2. Sequence Enrichment (buffer.py)

The model expects a sequence length of 60 frames, but the input dimension is 90, NOT 30.

Maintain a sliding window (deque) of 60 raw frames (Shape: 60 x 30).

Velocity: Calculate the frame-to-frame difference. The first frame's velocity is 0. (Shape: 60 x 30).

Standard Deviation: Calculate the np.std over axis 0 for the 60 frames, then tile it 60 times. (Shape: 60 x 30).

Concatenate: enriched_chunk = np.concatenate([raw_frames, velocity, std_matrix], axis=-1). Final shape: (60, 90).

3.3. ONNX Inference (inference.py)

When the buffer reaches 60, convert the enriched chunk to a NumPy array of shape (1, 60, 90) with dtype=np.float32.

Run onnxruntime.InferenceSession("models/engagement_gru.onnx").run(None, {input_name: data}).

Sigmoid Activation: The ONNX model outputs RAW LOGITS. You MUST apply: probability = 1 / (1 + np.exp(-logit)).

Threshold: Compare the probability against 0.55. If >= 0.55, state is ENGAGED, else DISTRACTED.

Smoothing: Apply a Moving Average over the last 3-5 probabilities to prevent UI jitter.

3.4. Thread Safety & Concurrency

customtkinter MUST run on the Main Thread.

OpenCV, MediaPipe, Buffer, and ONNX Runtime MUST run on a Daemon Background Thread.

Communication: Use queue.Queue. The background thread puts a dictionary {"frame": cv2_image, "focus_score": prob, "state": "ENGAGED"} into the queue.

The UI thread uses .after(15, process_queue) to update the canvas.

3.5. AI Coaching (Post-Session)

At the end of a Pomodoro session, save an array of minute-by-minute focus averages to data/history.json. Send this JSON to OpenAI gpt-4o-mini with a prompt to act as an encouraging productivity coach and provide a 3-sentence actionable review.

4. EXECUTION ROADMAP FOR THE AGENT

PHASE 1: ONNX Exporter

Write scripts/export_to_onnx.py. Load the PyTorch model (EngagementGRU) with TemporalAttention, initialize dummy input torch.randn(1, 60, 90), and export to models/engagement_gru.onnx using torch.onnx.export.

PHASE 2: The Core Tracking Engine

Build tracking/detector.py (30-dim extraction).

Build tracking/buffer.py (90-dim enrichment).

Build tracking/inference.py (ONNX session + Sigmoid + 0.55 threshold).

Build a standalone test_tracker.py CLI script to verify the webcam + ONNX pipeline works.

PHASE 3: UI & Multithreading

Build ui/app_window.py and ui/session_screen.py using customtkinter.

Implement the queue.Queue pattern to stream the webcam frame and focus score securely.

PHASE 4: LLM & Packaging

Implement core_ai/ai_coach.py.

Provide a detailed .spec file and PyInstaller command to compile this app into a single standalone .exe, ensuring hidden imports (onnxruntime, mediapipe) and static assets (the .onnx file) are bundled via sys._MEIPASS.

5. STRICT RULES

Never use PyTorch in the main app. Only onnxruntime and numpy.

Never block the UI. Heavy computation (CV2, ONNX) goes to threading.Thread(daemon=True).

Write complete, modular code for the specific phase requested. No placeholder code.

Add Vietnamese comments and labels in the UI.
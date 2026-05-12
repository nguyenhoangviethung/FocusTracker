# Context & Objective
We are building a real-time, background-running "Study Engagement Tracker" desktop application. Our core AI model is a lightweight PyTorch GRU that processes MediaPipe kinematic features.

I need you to act as a Senior Product Engineer and update our project documentation (`README.md`) and scaffold the next phase of our codebase to reflect a major architectural shift.

# Architectural Shifts & Product Requirements

## 1. Strict CPU Constraint (The "Why" behind GRU)
The application is designed to run silently in the background of personal laptops without draining battery or hoarding resources. This is why we strictly enforce the use of our lightweight GRU model over state-of-the-art CNNs. The system must prioritize low CPU consumption over raw AI accuracy.

## 2. The Hybrid "AI + Heuristic" System
Because our AI model peaks at around 75% accuracy (especially struggling with "silent focus" where the user is completely still), we cannot rely purely on Deep Learning. We are transitioning to a Hybrid System. The final engagement prediction will be a fusion of:
- **AI Prediction:** The output from the GRU model (analyzing webcam kinematic features).
- **Heuristic Logic:** An OS-level tracker that monitors what the user is actually doing on their computer.

## 3. Cross-Platform OS Tracker Module
The app needs a background service to fetch the currently active window and process resource usage.
- On Linux/macOS: Using commands like `top`, `ps`, or AppleScript.
- On Windows: Using PowerShell, `tasklist`, or `psutil`.
- **Logic:** If the AI predicts "Distracted" (e.g., user is looking away or still), but the OS Tracker detects heavy interaction in an IDE (VS Code), a Word document, or a PDF reader, the Heuristic overrides the AI and classifies the state as "Focused".
- **UX Requirement:** The app must explicitly ask the user for these system-level tracking permissions upon first launch.

# Your Task

Please execute the following updates:

1. **Overhaul the `README.md`:**
   - Update the "Architecture" section to visually or textually describe the new "Hybrid System" (AI Output + OS Tracker Fusion).
   - Add a new "Permissions & Privacy" section explaining the need for OS-level process monitoring.
   - Clarify the design philosophy (CPU-friendly background app).

2. **Scaffold the `os_tracker.py` Module:**
   - Create a robust outline for a cross-platform Python class (e.g., `ActiveWindowTracker`) that handles fetching the current active process. (You can suggest using standard libraries like `subprocess` or `psutil`).

3. **Update the Main Execution Pipeline (`main.py` or equivalent):**
   - Provide a code snippet demonstrating how the GRU model's probability and the `os_tracker`'s output will be combined using a simple rule-based voting/override system to yield the final `is_focused` boolean.
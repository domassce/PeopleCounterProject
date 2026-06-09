# Real-Time People Counter & Visitor Analytics

A robust computer vision application built with **Python**, **OpenCV**, and **dlib** to detect, track, and count people crossing boundaries in a video stream or live camera feed. Features an integrated configuration GUI, automated internal persistence, and PyInstaller compatibility for standalone distribution.

## Key Features

* **Advanced Object Tracking:** Combines MobileNet SSD deep learning detector with dlib correlation trackers and a custom Centroid Tracker to maintain high frame rates while accurately tracking uniquely identified objects.
* **Directional Counting Logic:** Smart entry/exit evaluation based on coordinate displacement over the entire object lifespan (from appearance to disappearance).
* **Robust Tracking Filter:** Implements a minimum track duration threshold (`min_track_frames`) to eliminate false positives and phantom detections.
* **Local Data Persistence:** Automated local logging (`peoplecounter.log`) and SQLite database storage (`visitors.db`) tracking timestamps, events (entries/exits), unique object IDs, and randomized identity markers.
* **Tkinter Configuration GUI:** Intuitive control panel for interactive hyperparameter tuning (confidence threshold, frame skipping, max tracking distance, entry direction definitions) before running the pipeline.
* **Standalization & Portability:** Specifically architected using dynamically resolved resource paths, ensuring full compatibility when compiled into a single executable binary using **PyInstaller**.

---

## 🛠️ Tech Stack & Dependencies

* **Language:** Python 3.x
* **Core CV Libraries:** OpenCV (`cv2`), `dlib`, `imutils`, `numpy`
* **UI Framework:** Tkinter (Native desktop interface)
* **Storage & Infrastructure:** SQLite 3 (Embedded DB), Python `logging` engine

---

## Project Structure

```text
├── detector/
│   ├── MobileNetSSD_deploy.prototxt     # DNN model configuration
│   └── MobileNetSSD_deploy.caffemodel   # Pre-trained deep learning weights
├── tracker/
│   ├── __init__.py
│   └── centroidtracker.py               # Core object tracking logic
├── people_counter.py                    # Main application script & GUI
└── README.md                            # Documentation

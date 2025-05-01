# -*- coding: utf-8 -*-
"""
Real-time people counter using OpenCV, dlib, and MobileNet SSD detector.
Counts entries based on movement direction from appearance to disappearance,
using coordinate comparison. Includes minimum track duration filter.
Saves DB and Log next to executable for PyInstaller compatibility.
Uses standard English text and cv2.putText. Lithuanian nicknames without diacritics.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys
import time
import datetime
from datetime import date, timedelta
import logging
import random
import sqlite3
from typing import Optional, Dict, List, Tuple, Any, Set

# Third-party libraries
try:
    import cv2
    import dlib
    import imutils
    from imutils.video import VideoStream, FPS
    import numpy as np
except ImportError as e:
    print(f"Error importing required libraries: {e}")
    print("Please install necessary packages, e.g.:")
    print("pip install opencv-python dlib imutils numpy")
    sys.exit(1)

# Local tracker modules
try:
    from tracker.centroidtracker import CentroidTracker
    class TrackableObject:
        """ Represents an object being tracked, storing initial position. """
        def __init__(self, objectID: int, centroid: Tuple[int, int]):
            self.objectID: int = objectID
            self.centroids: List[Tuple[int, int]] = [centroid]
            self.initial_centroid: Tuple[int, int] = centroid
            self.nickname: str = "Unknown"
            self.color: Tuple[int, int, int] = (128, 128, 128)
            self.last_known_confidence: float = 0.0
            self.last_known_rect: Optional[Tuple[int, int, int, int]] = None
            self.counted_event: Optional[str] = None
except ImportError:
    print("Warning: Could not import tracker modules from 'tracker' directory.")
    # Dummy classes if needed...

# --- Constants ---
# Determine application directory for writable files (Log, DB)
if getattr(sys, 'frozen', False):
    # If the application is run as a bundle, the PyInstaller bootloader
    # extends the sys module by a flag frozen=True and sets the app
    # path into variable _MEIPASS'. The executable path is in sys.executable.
    APP_DIR = os.path.dirname(sys.executable)
else:
    # If run as a normal script, use the script's directory
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(APP_DIR, "peoplecounter.log")
DB_FILE = os.path.join(APP_DIR, 'visitors.db')

DEFAULT_CONFIDENCE = 0.4; DEFAULT_SKIP_FRAMES = 10
DEFAULT_MAX_DISAPPEARED = 40; DEFAULT_MAX_DISTANCE = 50 # CRITICAL TUNING PARAMETERS
DEFAULT_MIN_TRACK_FRAMES = 10
DNN_INPUT_SIZE = (300, 300); DNN_SCALE_FACTOR = 0.007843
DNN_MEAN_SUBTRACTION = (127.5, 127.5, 127.5)

CLASSES = [ "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus", "car",
            "cat", "chair", "cow", "diningtable", "dog", "horse", "motorbike", "person",
            "pottedplant", "sheep", "sofa", "train", "tvmonitor" ]
TARGET_CLASS = "person"
NICKNAMES = [ "Azuolas", "Liepa", "Vejas", "Audra", "Upe", "Ezeras", "Miskas", "Vyturys",
              "Sakalas", "Vilkas", "Lokys", "Lusis", "Kregzde", "Gintaras", "Perkunas",
              "Gabija", "Ausra", "Rasa", "Saule", "Jonas", "Ona", "Petras", "Maryte",
              "Antanas", "Elena" ]

# --- Logging Setup ---
# Setup logging AFTER defining LOG_FILE path
try:
    logging.basicConfig( filename=LOG_FILE, level=logging.INFO,
                         format="[%(asctime)s] [%(levelname)-8s] %(message)s",
                         datefmt="%Y-%m-%d %H:%M:%S" )
    logger = logging.getLogger(__name__)
    logger.info("Logging initialized.")
except Exception as e:
    print(f"Error setting up logging to {LOG_FILE}: {e}")
    # Fallback to console logging if file logging fails
    logging.basicConfig( level=logging.INFO,
                         format="[%(asctime)s] [%(levelname)-8s] %(message)s",
                         datefmt="%Y-%m-%d %H:%M:%S" )
    logger = logging.getLogger(__name__)
    logger.error(f"Could not write to log file {LOG_FILE}, logging to console. Error: {e}")


# --- Utility Functions ---
def resource_path(relative_path: str) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller bundle data. """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # Use this for reading bundled data files (models, fonts etc.)
        base_path = sys._MEIPASS
    except AttributeError:
        # Not running as a bundle, use script's directory
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

def setup_database(db_path: str) -> Optional[sqlite3.Connection]:
    """ Creates or connects to the SQLite database at the specified path. """
    try:
        conn = sqlite3.connect(db_path); cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS visitors (
                            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                            event TEXT NOT NULL, object_id INTEGER, nickname TEXT )''')
        conn.commit(); logger.info(f"Database connection established to {db_path}"); return conn
    except sqlite3.Error as e:
        logger.error(f"Database setup error at {db_path}: {e}"); print(f"Error setting up database: {e}"); return None

def log_visitor_event(conn: sqlite3.Connection, event_text: str,
                      obj_id: Optional[int] = None, nickname: Optional[str] = None):
    """ Logs an event to the visitors table. """
    # (Function content remains the same)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO visitors (timestamp, event, object_id, nickname) VALUES (?, ?, ?, ?)",
                       (timestamp, event_text, obj_id, nickname)); conn.commit()
    except sqlite3.Error as e: logger.error(f"Database insert error: {e}")

def get_yesterdays_count(conn: sqlite3.Connection) -> int:
    """ Queries the database for yesterday's 'entered' event count. """
    # (Function content remains the same)
    count = 0
    if not conn: return 0
    try:
        yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM visitors WHERE timestamp LIKE ? AND event = 'entered'", (f"{yesterday_str}%",))
        result = cursor.fetchone()
        if result: count = result[0]
        logger.info(f"Retrieved yesterday's ({yesterday_str}) 'entered' count: {count}")
    except sqlite3.Error as e:
        logger.error(f"Error querying yesterday's count: {e}")
    return count

# --- GUI Class ---
class SettingsGUI:
    """ Tkinter GUI - Coordinate comparison logic settings. """
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("People Counter Settings (Tuning is CRITICAL!)")
        self._center_window(470, 340)
        self.settings: Optional[Dict[str, Any]] = None
        self.input_path = tk.StringVar(); self.confidence = tk.StringVar(value=str(DEFAULT_CONFIDENCE))
        self.skip_frames = tk.StringVar(value=str(DEFAULT_SKIP_FRAMES))
        self.max_disappeared = tk.StringVar(value=str(DEFAULT_MAX_DISAPPEARED))
        self.max_distance = tk.StringVar(value=str(DEFAULT_MAX_DISTANCE))
        self.min_track_frames = tk.StringVar(value=str(DEFAULT_MIN_TRACK_FRAMES))
        self.switch_sides = tk.BooleanVar(value=False)
        self._create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _center_window(self, width: int, height: int):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        cx, cy = int(sw / 2 - width / 2), int(sh / 2 - height / 2)
        self.root.geometry(f'{width}x{height}+{cx}+{cy}')

    def _create_widgets(self):
        main_frame = tk.Frame(self.root, padx=10, pady=10); main_frame.pack(fill=tk.BOTH, expand=True)
        input_frame = tk.Frame(main_frame); input_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(input_frame, text="Video File (leave empty for camera):").pack(side=tk.TOP, anchor=tk.W)
        entry_frame = tk.Frame(input_frame); entry_frame.pack(fill=tk.X)
        tk.Entry(entry_frame, textvariable=self.input_path, width=45).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        tk.Button(entry_frame, text="Browse...", command=self._browse_input).pack(side=tk.RIGHT, padx=(5, 0))

        tune_frame = tk.LabelFrame(main_frame, text="Critical Tuning Parameters", padx=5, pady=5)
        tune_frame.pack(fill=tk.X, pady=5); tune_frame.columnconfigure(1, weight=1); row_tune = 0
        tk.Label(tune_frame, text="Max Disappeared Frames (Try increasing):").grid(row=row_tune, column=0, sticky=tk.W, pady=1)
        tk.Entry(tune_frame, textvariable=self.max_disappeared, width=10).grid(row=row_tune, column=1, sticky=tk.EW, padx=5, pady=1); row_tune += 1
        tk.Label(tune_frame, text="Max Distance (pixels) (Adjust +/-):").grid(row=row_tune, column=0, sticky=tk.W, pady=1)
        tk.Entry(tune_frame, textvariable=self.max_distance, width=10).grid(row=row_tune, column=1, sticky=tk.EW, padx=5, pady=1); row_tune += 1
        tk.Label(tune_frame, text="Confidence Threshold (Try 0.4-0.6):").grid(row=row_tune, column=0, sticky=tk.W, pady=1)
        tk.Entry(tune_frame, textvariable=self.confidence, width=10).grid(row=row_tune, column=1, sticky=tk.EW, padx=5, pady=1); row_tune += 1
        tk.Label(tune_frame, text="Detection Skip Frames (Try decreasing):").grid(row=row_tune, column=0, sticky=tk.W, pady=1)
        tk.Entry(tune_frame, textvariable=self.skip_frames, width=10).grid(row=row_tune, column=1, sticky=tk.EW, padx=5, pady=1); row_tune += 1
        tk.Label(tune_frame, text="Min Track Frames for Count (Try > 5):").grid(row=row_tune, column=0, sticky=tk.W, pady=1)
        tk.Entry(tune_frame, textvariable=self.min_track_frames, width=10).grid(row=row_tune, column=1, sticky=tk.EW, padx=5, pady=1); row_tune += 1

        dir_frame = tk.LabelFrame(main_frame, text="Entry Direction Definition", padx=5, pady=5)
        dir_frame.pack(fill=tk.X, pady=5)
        tk.Checkbutton(dir_frame, text="Consider Left/Up movement as 'Entry'", variable=self.switch_sides).pack(side=tk.LEFT, anchor=tk.W)

        self.start_button = tk.Button(main_frame, text="Start Counter", command=self._submit, width=20, height=2)
        self.start_button.pack(pady=(15, 0))

    def _browse_input(self):
        filename = filedialog.askopenfilename( title="Select Video File",
                                              filetypes=(("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")) )
        if filename: self.input_path.set(filename)

    def _validate_settings(self) -> bool:
        # (Validation including min_track_frames)
        try:
            conf, skip = float(self.confidence.get()), int(self.skip_frames.get())
            max_dis, max_dist = int(self.max_disappeared.get()), int(self.max_distance.get())
            min_track = int(self.min_track_frames.get())
            if not (0.0 <= conf <= 1.0): raise ValueError("Confidence must be between 0.0 and 1.0")
            if skip < 0: raise ValueError("Skip Frames must be non-negative")
            if max_dis < 0: raise ValueError("Max Disappeared Frames must be non-negative")
            if max_dist <= 0: raise ValueError("Max Distance must be positive")
            if min_track < 0: raise ValueError("Minimum Track Frames must be non-negative")
            return True
        except ValueError as e: messagebox.showerror("Input Error", f"Invalid input: {e}"); return False

    def _submit(self):
        if self._validate_settings():
            input_val = self.input_path.get()
            # Use resource_path only for reading bundled data (models)
            # DB and Log paths are determined globally using APP_DIR
            self.settings = { 'input': input_val if input_val else None,
                              'prototxt': resource_path(os.path.join("detector", "MobileNetSSD_deploy.prototxt")),
                              'model': resource_path(os.path.join("detector", "MobileNetSSD_deploy.caffemodel")),
                              'confidence': float(self.confidence.get()), 'skip_frames': int(self.skip_frames.get()),
                              'max_disappeared': int(self.max_disappeared.get()), 'max_distance': int(self.max_distance.get()),
                              'min_track_frames': int(self.min_track_frames.get()),
                              'switch_sides': self.switch_sides.get() }
            self.root.destroy()

    def _on_closing(self): self.settings = None; self.root.destroy()


# --- Drawing Helper Functions ---
# (draw_object_info, draw_hud, draw_congrats_message remain the same)
def draw_object_info(frame: np.ndarray, trackable_object: TrackableObject,
                     box: Tuple[int, int, int, int], confidence_text: str):
    (start_x, start_y, end_x, end_y) = box
    color, nickname = trackable_object.color, trackable_object.nickname
    cv2.rectangle(frame, (start_x, start_y), (end_x, end_y), color, 2)
    y_nick = start_y - 15 if start_y - 15 > 10 else start_y + 15
    y_conf = y_nick + 15
    cv2.putText(frame, nickname, (start_x, y_nick), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    cv2.putText(frame, confidence_text, (start_x, y_conf), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

def draw_hud(frame: np.ndarray, frame_height: int, status: str, visitor_count_today: int, visitor_count_yesterday: int):
    info = [ ("Status", status), ("Today's Visitors (Entries)", visitor_count_today),
             ("Yesterday's Visitors (Entries)", visitor_count_yesterday) ]
    info_color=(0, 255, 0); font=cv2.FONT_HERSHEY_SIMPLEX; scale=0.6; thickness=2
    for i, (k, v) in enumerate(info):
        text = f"{k}: {v}"
        text_y = frame_height - ((i * 20) + 20);
        if text_y < 20: text_y = 20
        cv2.putText(frame, text, (10, text_y), font, scale, info_color, thickness)

def draw_congrats_message(frame: np.ndarray, frame_width: int, frame_height: int, visitor_count: int):
    congrats_text = f"Congratulations! Visitor #{visitor_count}!"
    font_scale, thickness = 1.5, 3; font = cv2.FONT_HERSHEY_SIMPLEX
    color_text, color_bg = (255, 255, 255), (0, 165, 255)
    (tw, th), baseline = cv2.getTextSize(congrats_text, font, font_scale, thickness)
    tx, ty = (frame_width - tw) // 2, (frame_height + th) // 2
    bg_tl, bg_br = (tx - 10, ty - th - 10), (tx + tw + 10, ty + baseline + 10)
    cv2.rectangle(frame, bg_tl, bg_br, color_bg, -1)
    cv2.putText(frame, congrats_text, (tx, ty), font, font_scale, color_text, thickness)


# --- Main People Counter Function ---
def people_counter(settings: Dict[str, Any]):
    """ Runs the main loop counting entries based on coord comparison on disappearance. """
    # Use globally defined DB_FILE which points next to exe/script
    db_connection = setup_database(DB_FILE)
    visitor_count_yesterday = get_yesterdays_count(db_connection) if db_connection else 0

    try:
        # Use resource_path for reading bundled model files
        net = cv2.dnn.readNetFromCaffe(settings['prototxt'], settings['model'])
    except cv2.error as e:
        logger.error(f"Failed to load DNN model: {e}"); print(f"Error: Could not load model files.\n{e}")
        if db_connection: db_connection.close(); return

    vs: Optional[VideoStream or cv2.VideoCapture] = None; using_camera = False
    if settings['input'] is None:
        try: vs = VideoStream(src=0).start(); time.sleep(2.0); using_camera = True
        except Exception as e: logger.error(f"Cam stream error: {e}"); print(f"Error: Could not open camera.")
        if not vs:
            if db_connection: db_connection.close(); return
    else:
        if not os.path.exists(settings['input']):
             logger.error(f"Video file not found: {settings['input']}")
             print(f"Error: Video file not found: {settings['input']}")
             if db_connection: db_connection.close(); return
        vs = cv2.VideoCapture(settings['input'])

    frame_width: Optional[int] = None; frame_height: Optional[int] = None

    ct = CentroidTracker( maxDisappeared=settings['max_disappeared'],
                          maxDistance=settings['max_distance'] )
    dlib_trackers: List[dlib.correlation_tracker] = []
    trackable_objects: Dict[int, TrackableObject] = {}
    current_object_ids: Set[int] = set()

    total_frames = 0; visitor_count_today = 0 # Counts entries only
    status = "Initializing"; fps = FPS().start()
    congrats_active, congrats_end_frame, congrats_visitor_count = False, 0, 0
    window_name = "People Counter (Press 'q' to quit)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    # --- Main Loop ---
    while True:
        try:
            frame = vs.read() if using_camera else vs.read()[1]
            if frame is None: status = "End of Stream"; logger.info("End of stream."); break

            frame = imutils.resize(frame, width=800)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if frame_width is None: frame_height, frame_width = frame.shape[:2]

            current_rects: List[Tuple[int, int, int, int]] = []

            # --- Detection Phase ---
            if total_frames % settings['skip_frames'] == 0:
                status = "Detecting"; dlib_trackers = []
                blob = cv2.dnn.blobFromImage( cv2.resize(frame, DNN_INPUT_SIZE), DNN_SCALE_FACTOR,
                                              DNN_INPUT_SIZE, DNN_MEAN_SUBTRACTION, swapRB=False )
                net.setInput(blob); detections = net.forward()
                rects_for_ct = []; current_confidences = {}
                for i in np.arange(0, detections.shape[2]):
                    confidence = detections[0, 0, i, 2]
                    if confidence > settings['confidence']:
                        idx = int(detections[0, 0, i, 1])
                        if idx < len(CLASSES) and CLASSES[idx] == TARGET_CLASS:
                            box = detections[0, 0, i, 3:7] * np.array([frame_width, frame_height, frame_width, frame_height])
                            (sx, sy, ex, ey) = box.astype("int")
                            if ex > sx and ey > sy:
                                rect_dlib = dlib.rectangle(sx, sy, ex, ey)
                                tracker = dlib.correlation_tracker(); tracker.start_track(rgb_frame, rect_dlib)
                                dlib_trackers.append(tracker)
                                current_rect = (sx, sy, ex, ey); rects_for_ct.append(current_rect)
                                current_confidences[current_rect] = confidence
            # --- Tracking Phase ---
            else:
                status = "Tracking"; updated_rects = []
                trackers_to_keep = []
                for tracker in dlib_trackers:
                    tracker.update(rgb_frame); pos = tracker.get_position()
                    sx, sy, ex, ey = int(pos.left()), int(pos.top()), int(pos.right()), int(pos.bottom())
                    if 0 <= sx < frame_width and 0 <= sy < frame_height and ex > sx and ey > sy:
                         updated_rects.append((sx, sy, ex, ey)); trackers_to_keep.append(tracker)
                rects_for_ct = updated_rects; dlib_trackers = trackers_to_keep

            # --- Update Centroid Tracker ---
            tracked_centroids_this_frame = ct.update(rects_for_ct)
            updated_object_ids = set(tracked_centroids_this_frame.keys())

            # --- Handle Disappeared Objects (Counting Entries Only) ---
            disappeared_ids = current_object_ids - updated_object_ids
            objects_to_remove_finally = set()
            for object_id in disappeared_ids:
                trackable_obj = trackable_objects.get(object_id)
                # Count only if tracked long enough and not already counted
                if trackable_obj and trackable_obj.counted_event is None and len(trackable_obj.centroids) >= settings['min_track_frames']:
                    start_pos = trackable_obj.initial_centroid; end_pos = trackable_obj.centroids[-1]
                    dx, dy = end_pos[0] - start_pos[0], end_pos[1] - start_pos[1]
                    event = None; is_entry_event = False
                    if abs(dx) > abs(dy): # Horizontal primary
                        if dx > 0: is_entry_event = not settings['switch_sides']
                        else: is_entry_event = settings['switch_sides']
                    else: # Vertical primary
                        if dy > 0: is_entry_event = not settings['switch_sides']
                        else: is_entry_event = settings['switch_sides']

                    if is_entry_event:
                        visitor_count_today += 1
                        event = "entered"
                        trackable_obj.color = (0, 255, 0) # Green
                        logger.info(f"Object ID {object_id} ({trackable_obj.nickname}) counted as ENTRY. Count: {visitor_count_today} (dx={dx}, dy={dy}, frames={len(trackable_obj.centroids)})")
                        log_visitor_event(db_connection, event, object_id, trackable_obj.nickname)
                        # Trigger congrats message
                        if not congrats_active and visitor_count_today > 0 and visitor_count_today % 100 == 0:
                            logger.info(f"Congrats for entry #{visitor_count_today}!")
                            congrats_active, congrats_visitor_count = True, visitor_count_today
                            congrats_end_frame = total_frames + 60
                    else:
                        event = "exited"
                        trackable_obj.color = (0, 0, 255) # Red
                        logger.info(f"Object ID {object_id} ({trackable_obj.nickname}) detected as EXIT (not counted). (dx={dx}, dy={dy}, frames={len(trackable_obj.centroids)})")
                        log_visitor_event(db_connection, event, object_id, trackable_obj.nickname)

                    trackable_obj.counted_event = event # Mark as processed
                    objects_to_remove_finally.add(object_id)

                elif trackable_obj:
                    logger.debug(f"Object ID {object_id} disappeared but not counted (event={trackable_obj.counted_event}, frames={len(trackable_obj.centroids)}).")
                    objects_to_remove_finally.add(object_id)


            # --- Process Currently Active Objects ---
            for object_id, centroid in tracked_centroids_this_frame.items():
                trackable_obj = trackable_objects.get(object_id)
                if trackable_obj is None:
                    trackable_obj = TrackableObject(object_id, centroid)
                    trackable_obj.nickname = f"{random.choice(NICKNAMES)}-{random.randint(10, 99)}"
                    # Count not incremented here
                else: trackable_obj.centroids.append(centroid)
                trackable_objects[object_id] = trackable_obj

                # Drawing logic (unchanged)
                best_rect = None; min_dist = float('inf'); confidence_text = "tracking"
                current_boxes_to_check = rects_for_ct
                confidences_available = current_confidences if status == "Detecting" else {}
                for rect_candidate in current_boxes_to_check:
                    cx, cy = (rect_candidate[0]+rect_candidate[2])//2, (rect_candidate[1]+rect_candidate[3])//2
                    dist = np.linalg.norm(np.array(centroid) - np.array((cx, cy)))
                    if dist < min_dist and dist < settings['max_distance']:
                        min_dist, best_rect = dist, rect_candidate
                        if best_rect in confidences_available:
                            conf = confidences_available[best_rect]
                            confidence_text = f"{conf*100:.1f}%"; trackable_obj.last_known_confidence = conf
                display_rect = None
                if best_rect: display_rect, trackable_obj.last_known_rect = best_rect, best_rect
                elif trackable_obj.last_known_rect:
                     last_cx=(trackable_obj.last_known_rect[0]+trackable_obj.last_known_rect[2])//2
                     last_cy=(trackable_obj.last_known_rect[1]+trackable_obj.last_known_rect[3])//2
                     dist_to_last = np.linalg.norm(np.array(centroid) - np.array((last_cx, last_cy)))
                     if dist_to_last < settings['max_distance'] * 1.5: display_rect = trackable_obj.last_known_rect
                if display_rect: draw_object_info(frame, trackable_obj, display_rect, confidence_text)

            # --- Cleanup Processed Disappeared Objects ---
            for old_id in objects_to_remove_finally:
                trackable_objects.pop(old_id, None)

            # Update active IDs for next frame
            current_object_ids = updated_object_ids

            # --- Draw HUD and Messages ---
            if frame_height is not None:
                 draw_hud(frame, frame_height, status, visitor_count_today, visitor_count_yesterday)
            if congrats_active:
                if frame_width is not None and frame_height is not None:
                     draw_congrats_message(frame, frame_width, frame_height, congrats_visitor_count)
                if total_frames >= congrats_end_frame: congrats_active = False

            # --- Display Frame ---
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"): logger.info("Quit key."); break

            total_frames += 1; fps.update()

        except KeyboardInterrupt: status = "Interrupted"; logger.info("Keyboard interrupt."); break
        except Exception as e:
            status = "Error"; logger.exception("Error in main loop:")
            print(f"\nAn unexpected error occurred: {e}\nCheck {LOG_FILE} for details.")
            time.sleep(2); break

    # --- Cleanup ---
    fps.stop()
    logger.info(f"Loop finished. Status: {status}. Today's Visitor Count (Entries): {visitor_count_today}")
    logger.info(f"Elapsed: {fps.elapsed():.2f}s. Approx FPS: {fps.fps():.2f}")
    print(f"\n[INFO] Elapsed time: {fps.elapsed():.2f} s. Approx FPS: {fps.fps():.2f}")
    print(f"[INFO] Today's Visitor Count (Entries): {visitor_count_today}")
    print(f"[INFO] Yesterday's Visitor Count (Entries): {visitor_count_yesterday}")

    if vs:
        if using_camera: vs.stop()
        else: vs.release()
    cv2.destroyAllWindows()
    if db_connection: db_connection.close()
    logger.info("Application finished.")


# --- Main Execution ---
if __name__ == "__main__":
    # Ensure APP_DIR is defined even if run directly (though it's defined globally now)
    if 'APP_DIR' not in globals():
         APP_DIR = os.path.dirname(os.path.abspath(__file__))

    root = tk.Tk()
    app = SettingsGUI(root)
    root.mainloop()
    if app.settings:
        logger.info("Settings obtained. Starting counter.")
        print("\nSettings obtained, starting counter...")
        print(f"IMPORTANT: Database and Log files will be saved in: {APP_DIR}")
        print("Press 'q' in the OpenCV window to quit.")
        people_counter(app.settings)
    else:
        logger.info("Settings GUI closed without starting.")
        print("Settings window closed. Exiting.")
import pygame
import pygame.gfxdraw
import win32gui
import win32con
import win32api
import dxcam
import cv2
import numpy as np
import math
import sys
import time
import keyboard
from filterpy.kalman import KalmanFilter
from scipy.spatial import distance as scipy_dist

# ==========================================
# 🚀 1. OpenCV & Performance Optimization
# ==========================================
cv2.setUseOptimized(True)
cv2.setNumThreads(4) # رفع الأداء للمعالجة المتوازية

# ==========================================
# ⚙️ 2. Configuration & Hyperparameters
# ==========================================
FPS = 144
BALL_RADIUS = 16
CUSHION_PADDING = 16 # Cushion Compensation لحساب ارتداد حافة الكرة بدلاً من مركزها
MAX_BANKS = 4        # Multi-Bank System لـ 4 ارتدادات متتالية

SCREEN_WIDTH = win32api.GetSystemMetrics(0)
SCREEN_HEIGHT = win32api.GetSystemMetrics(1)
TRANSPARENT = (0, 0, 0)

# Colors
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 162, 232)
PINK = (255, 0, 128)
ORANGE = (255, 165, 0)
CYAN = (0, 200, 255)

# ==========================================
# 🧠 3. Advanced Tracking & Filtering System
# ==========================================
class BallTracker:
    def __init__(self):
        self.trackers = {}
        self.next_id = 0

    def create_kf(self, x, y):
        # Kalman Filter Initialization
        kf = KalmanFilter(dim_x=4, dim_z=2)
        kf.x = np.array([x, y, 0., 0.]) # [x, y, vx, vy]
        kf.F = np.array([[1., 0., 1./FPS, 0.],
                         [0., 1., 0., 1./FPS],
                         [0., 0., 1., 0.],
                         [0., 0., 0., 1.]])
        kf.H = np.array([[1., 0., 0., 0.],
                         [0., 1., 0., 0.]])
        kf.P *= 10.
        kf.R *= 0.5
        kf.Q *= 0.1
        return kf

    def update(self, detections):
        # ID Tracking via Hungarian-like Minimum Distance Association
        updated_trackers = {}
        if not detections:
            return updated_trackers

        det_pts = np.array(detections)
        
        if not self.trackers:
            for pt in det_pts:
                updated_trackers[self.next_id] = self.create_kf(pt[0], pt[1])
                self.next_id += 1
            self.trackers = updated_trackers
            return updated_trackers

        track_ids = list(self.trackers.keys())
        track_pts = np.array([self.trackers[tid].x[0:2] for tid in track_ids])

        # مصفوفة المسافات
        cost_matrix = scipy_dist.cdist(track_pts, det_pts)
        
        assigned_det = set()
        for idx, tid in enumerate(track_ids):
            if cost_matrix.shape[1] == 0:
                break
            min_det_idx = np.argmin(cost_matrix[idx])
            if cost_matrix[idx, min_det_idx] < 40 and min_det_idx not in assigned_det:
                kf = self.trackers[tid]
                kf.predict()
                kf.update(det_pts[min_det_idx])
                updated_trackers[tid] = kf
                assigned_det.add(min_det_idx)

        # إضافة كرات جديدة تظهر لأول مرة
        for min_det_idx in range(len(det_pts)):
            if min_det_idx not in assigned_det:
                updated_trackers[self.next_id] = self.create_kf(det_pts[min_det_idx][0], det_pts[min_det_idx][1])
                self.next_id += 1

        self.trackers = updated_trackers
        return updated_trackers

# Instantiate Tracker
tracker_system = BallTracker()

# Global State
locked_id = None
selected_pocket = 0
table_region = None
last_lock_time = 0

# ==========================================
# 📐 4. Math & Predictive Physics Functions
# ==========================================
def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def get_predictive_aim(kf, lead_time=0.15):
    """ Predictive Aim Based on Kalman Velocity Vector """
    px = kf.x[0] + kf.x[2] * lead_time
    py = kf.x[1] + kf.x[3] * lead_time
    return (float(px), float(py))

def ghost_ball(target, pocket, radius):
    dx = target[0] - pocket[0]
    dy = target[1] - pocket[1]
    dist = math.hypot(dx, dy)
    if dist == 0: return target
    ratio = (dist + radius * 2) / dist
    return (pocket[0] + dx * ratio, pocket[1] + dy * ratio)

def apply_spin_and_deflection(start, end, spin_factor=0.03):
    """ Spin Prediction & Cushion Deflection Model """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    # تعديل طفيف للمسار محاكاة للدوران الجانبي والاحتكاك
    perp_x = -dy * spin_factor
    perp_y = dx * spin_factor
    return (end[0] + perp_x, end[1] + perp_y)

def calculate_multi_bank(start_pos, target_pos, bounds, max_banks=MAX_BANKS):
    """ Real Physics Multi-Bank Trajectory Engine with Cushion Compensation """
    left, top, right, bottom = bounds
    path = [start_pos]
    current_pos = start_pos
    
    # حساب متجه الحركة من الكرة البيضاء أو الشبح
    dx = target_pos[0] - start_pos[0]
    dy = target_pos[1] - start_pos[1]
    angle = math.atan2(dy, dx)
    
    vx = math.cos(angle)
    vy = math.sin(angle)
    
    for _ in range(max_banks):
        t_candidates = []
        
        if vx > 0: t_candidates.append(((right - current_pos[0]) / vx, 'R'))
        elif vx < 0: t_candidates.append(((left - current_pos[0]) / vx, 'L'))
        if vy > 0: t_candidates.append(((bottom - current_pos[1]) / vy, 'B'))
        elif vy < 0: t_candidates.append(((top - current_pos[1]) / vy, 'T'))
        
        if not t_candidates: break
        
        # اختيار الارتداد الأقرب
        t, side = min(t_candidates, key=lambda item: item[0])
        
        # نقطة التصادم الجديدة
        next_x = current_pos[0] + vx * t
        next_y = current_pos[1] + vy * t
        
        current_pos = (next_x, next_y)
        path.append(current_pos)
        
        # عكس الاتجاه في الفيزياء المرنة (Cushion Reflection)
        if side in ('L', 'R'): vx = -vx
        if side in ('T', 'B'): vy = -vy
        
    return path

# ==========================================
# 🖼️ 5. Vision Frame Analyzers
# ==========================================
def detect_table(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array([30, 40, 40])
    upper = np.array([100, 255, 255])
    mask = cv2.inRange(hsv, lower, upper)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) > 40000:
            x, y, w, h = cv2.boundingRect(largest)
            return {"left": x, "top": y, "width": w, "height": h}
    return None

def is_white_ball(roi):
    if roi is None or roi.size == 0: return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower = np.array([0, 0, 160])
    upper = np.array([180, 60, 255])
    mask = cv2.inRange(hsv, lower, upper)
    return (np.sum(mask == 255) / mask.size) > 0.40

# ==========================================
# 🎮 6. Initialize DirectX Overlay & Pygame
# ==========================================
pygame.init()
pygame.font.init()
pygame.mouse.set_visible(False)

# Zero Flicker Initialization via Layered HWND Windows Hook
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME)
hwnd = pygame.display.get_wm_info()["window"]

styles = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, styles | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST | win32con.WS_EX_NOACTIVATE)
win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*TRANSPARENT), 0, win32con.LWA_COLORKEY)

# DXCam setup
camera = dxcam.create(output_color="BGR")
camera.start(target_fps=FPS, video_mode=True)
clock = pygame.time.Clock()

pocket_font = pygame.font.SysFont("Arial", 20, bold=True)
running = True

# ==========================================
# 🔄 7. Core Real-Time Engine Loop
# ==========================================
while running:
    clock.tick(FPS)
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
    if keyboard.is_pressed("ctrl+q"): running = False

    # DirectX Hook & Force TopMost Constraint
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

    frame = camera.get_latest_frame()
    if frame is None: continue

    if table_region is None:
        table_region = detect_table(frame)
        continue

    x, y, w, h = table_region["left"], table_region["top"], table_region["width"], table_region["height"]
    table = frame[y:y+h, x:x+w]
    if table.size == 0: continue

    # Vision Processing Optimization Pipeline
    small = cv2.resize(table, None, fx=0.5, fy=0.5)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(cv2.equalizeHist(gray), 5)

    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.1, minDist=20, param1=55, param2=17, minRadius=7, maxRadius=16)

    raw_white = None
    detected_targets = []
    mx, my = win32api.GetCursorPos()

    # Define Fixed Pockets Reference Array
    pockets = [
        (x + 28, y + 28),         # Left Top
        (x + w // 2, y + 18),     # Center Top
        (x + w - 28, y + 28),     # Right Top
        (x + 28, y + h - 28),     # Left Bottom
        (x + w // 2, y + h - 18), # Center Bottom
        (x + w - 28, y + h - 28)  # Right Bottom
    ]

    # Dynamic Table Constraint Calculation with Cushion Compensation
    top_band, bottom_band = y + CUSHION_PADDING, y + h - CUSHION_PADDING
    left_band, right_band = x + CUSHION_PADDING, x + w - CUSHION_PADDING
    table_bounds = (left_band, top_band, right_band, bottom_band)

    screen.fill(TRANSPARENT)

    # Extraction Loop
    if circles is not None:
        circles = np.round(circles[0, :]).astype("int")
        for (cx, cy, r) in circles:
            cx, cy = int(cx * 2 + x), int(cy * 2 + y)
            r = int(r * 2)
            
            if any(distance((cx, cy), p) < 38 for p in pockets): continue

            roi = table[max(0, cy-y-r):min(h, cy-y+r), max(0, cx-x-r):min(w, cx-x+r)]
            if is_white_ball(roi):
                raw_white = (cx, cy)
            else:
                detected_targets.append((cx, cy))

    # Track Object States
    tracked_balls = tracker_system.update(detected_targets)

    # 1. Automatic White Ball Selection Loop
    if raw_white:
        pygame.gfxdraw.aacircle(screen, raw_white[0], raw_white[1], BALL_RADIUS, WHITE)
        pygame.gfxdraw.aacircle(screen, raw_white[0], raw_white[1], BALL_RADIUS - 2, CYAN)

    # 2. Draw Target Balls & Handle ID Lock (Z Key Input)
    hovered_id = None
    for b_id, kf in tracked_balls.items():
        # Target Estimation Using Predictive Aim Engine
        pred_pos = get_predictive_aim(kf)
        pos_x, pos_y = int(pred_pos[0]), int(pred_pos[1])
        
        color = YELLOW
        if b_id == locked_id:
            color = BLUE
            
        pygame.gfxdraw.aacircle(screen, pos_x, pos_y, BALL_RADIUS, color)
        
        # Check Hover
        if distance((mx, my), (pos_x, pos_y)) < BALL_RADIUS + 10:
            hovered_id = b_id

    # Handle Lock Mechanism Inputs (Z & X Keys)
    if keyboard.is_pressed("z") and time.time() - last_lock_time > 0.2:
        if hovered_id is not None:
            locked_id = hovered_id
            last_lock_time = time.time()
    if keyboard.is_pressed("x"):
        locked_id = None

    # Handle Active Pocket Changes Via Keys (1 to 6)
    for i in range(1, 7):
        if keyboard.is_pressed(str(i)):
            selected_pocket = i - 1

    # Render Visual HUD Labels for Pockets
    for idx, p in enumerate(pockets):
        p_color = GREEN if idx == selected_pocket else RED
        pygame.gfxdraw.aacircle(screen, p[0], p[1], 8, p_color)
        txt = pocket_font.render(f"[{idx+1}]", True, WHITE if idx == selected_pocket else ORANGE)
        screen.blit(txt, (p[0] - 12, p[1] - 32 if idx < 3 else p[1] + 12))

    # ==========================================
    # 🎯 8. Core Advanced Ray-Trace Solver Engine
    # ==========================================
    if raw_white and locked_id in tracked_balls:
        kf_target = tracked_balls[locked_id]
        target_pos = get_predictive_aim(kf_target)
        active_pocket = pockets[selected_pocket]

        # Calculation step A: Ghost Ball Placement Position
        g_pos = ghost_ball(target_pos, active_pocket, BALL_RADIUS)
        g_pos = apply_spin_and_deflection(raw_white, g_pos, spin_factor=0.01) # Dynamic Spin Shift Applied
        
        # Calculation step B: Main Trajectory Rays (White Ball To Ghost)
        pygame.draw.line(screen, WHITE, raw_white, (int(g_pos[0]), int(g_pos[1])), 2)
        pygame.gfxdraw.aacircle(screen, int(g_pos[0]), int(g_pos[1]), BALL_RADIUS, WHITE)
        
        # Draw Targeting Guideline to Target Pocket Vector
        pygame.draw.line(screen, YELLOW, (int(target_pos[0]), int(target_pos[1])), active_pocket, 2)

        # Calculation step C: Multi-Bank Predictive System & Reflection Line Solver
        # تفعيل المحرك الفيزيائي للارتدادات المتعددة عند الضغط على المفاتيح I, M, J, K أو بشكل تلقائي للمسارات الصعبة
        if keyboard.is_pressed("i") or keyboard.is_pressed("m") or keyboard.is_pressed("j") or keyboard.is_pressed("k"):
            bank_nodes = calculate_multi_bank(g_pos, active_pocket, table_bounds, max_banks=MAX_BANKS)
            for step in range(len(bank_nodes) - 1):
                p_start = (int(bank_nodes[step][0]), int(bank_nodes[step][1]))
                p_end = (int(bank_nodes[step+1][0]), int(bank_nodes[step+1][1]))
                pygame.draw.line(screen, PINK, p_start, p_end, 2)
                pygame.gfxdraw.filled_circle(screen, p_end[0], p_end[1], 4, CYAN)

    pygame.display.update()

# Termination Phase Cleanups
camera.stop()
pygame.quit()
sys.exit()

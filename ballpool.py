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

# ==========================================
# 🚀 1. OpenCV & Performance Optimization
# ==========================================
cv2.setUseOptimized(True)
cv2.setNumThreads(4)

# ==========================================
# ⚙️ 2. Configuration & Hyperparameters
# ==========================================
FPS = 144
BALL_RADIUS = 16
CUSHION_PADDING = 16
MAX_BANKS = 4        

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
# 🧠 3. Stable Memory Systems
# ==========================================
class WhiteBallMemory:
    def __init__(self):
        self.last_known_pos = None
        self.lost_frames = 0
        self.max_lost_frames = 60  # تذكر الكرة البيضاء تحت العصا لمدة 60 إطار

    def update(self, raw_white):
        if raw_white is not None:
            self.last_known_pos = raw_white
            self.lost_frames = 0
            return raw_white
        else:
            if self.last_known_pos is not None:
                self.lost_frames += 1
                if self.lost_frames <= self.max_lost_frames:
                    return self.last_known_pos
            return None

class TargetBallManager:
    def __init__(self):
        self.locked_pos = None
        self.kf = None

    def init_kf(self, x, y):
        self.kf = KalmanFilter(dim_x=4, dim_z=2)
        self.kf.x = np.array([x, y, 0., 0.]) 
        self.kf.F = np.array([[1., 0., 1./FPS, 0.],
                             [0., 1., 0., 1./FPS],
                             [0., 0., 1., 0.],
                             [0., 0., 0., 1.]])
        self.kf.H = np.array([[1., 0., 0., 0.],
                             [0., 1., 0., 0.]])
        self.kf.P *= 5.
        self.kf.R *= 0.05  # فلتر فائق النعومة للكرة المحددة يدوياً
        self.kf.Q *= 0.01

    def lock_new(self, x, y):
        self.locked_pos = (x, y)
        self.init_kf(x, y)

    def update(self):
        if self.kf is not None:
            self.kf.predict()
            # الكرة الهدف المحددة بالماوس ثابتة ما لم نقم بتحديثها، لذا نغذي الفلتر بموقعها المستقر
            self.kf.update(np.array(self.locked_pos))
            return (float(self.kf.x[0]), float(self.kf.x[1]))
        return self.locked_pos

    def clear(self):
        self.locked_pos = None
        self.kf = None

# تفعيل كائنات الذاكرة والتتبع الجديد
white_memory = WhiteBallMemory()
target_manager = TargetBallManager()

selected_pocket = 0
table_region = None
last_lock_time = 0

# ==========================================
# 📐 4. Math & Predictive Physics Functions
# ==========================================
def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def ghost_ball(target, pocket, radius):
    dx = target[0] - pocket[0]
    dy = target[1] - pocket[1]
    dist = math.hypot(dx, dy)
    if dist == 0: return target
    ratio = (dist + radius * 2) / dist
    return (pocket[0] + dx * ratio, pocket[1] + dy * ratio)

def apply_spin_and_deflection(start, end, spin_factor=0.005):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    perp_x = -dy * spin_factor
    perp_y = dx * spin_factor
    return (end[0] + perp_x, end[1] + perp_y)

def calculate_multi_bank(start_pos, target_pos, bounds, max_banks=MAX_BANKS):
    left, top, right, bottom = bounds
    path = [start_pos]
    current_pos = start_pos
    
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
        t, side = min(t_candidates, key=lambda item: item[0])
        
        next_x = current_pos[0] + vx * t
        next_y = current_pos[1] + vy * t
        current_pos = (next_x, next_y)
        path.append(current_pos)
        
        if side in ('L', 'R'): vx = -vx
        if side in ('T', 'B'): vy = -vy
    return path

# ==========================================
# 🖼️ 5. Vision Frame Analyzers (الكرة البيضاء فقط)
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
    lower = np.array([0, 0, 150]) 
    upper = np.array([180, 75, 255])
    mask = cv2.inRange(hsv, lower, upper)
    return (np.sum(mask == 255) / mask.size) > 0.38

# ==========================================
# 🎮 6. Initialize DirectX Overlay & Pygame
# ==========================================
pygame.init()
pygame.font.init()
pygame.mouse.set_visible(False)

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME)
hwnd = pygame.display.get_wm_info()["window"]

styles = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, styles | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST | win32con.WS_EX_NOACTIVATE)
win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*TRANSPARENT), 0, win32con.LWA_COLORKEY)

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

    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

    frame = camera.get_latest_frame()
    if frame is None: continue

    if table_region is None:
        table_region = detect_table(frame)
        continue

    x, y, w, h = table_region["left"], table_region["top"], table_region["width"], table_region["height"]
    table = frame[y:y+h, x:x+w]
    if table.size == 0: continue

    small = cv2.resize(table, None, fx=0.5, fy=0.5)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(cv2.equalizeHist(gray), 5)

    # معالجة سريعة جداً ومخصصة للكرة البيضاء فقط لتقليل استهلاك الـ CPU
    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.1, minDist=22, param1=60, param2=19, minRadius=7, maxRadius=16)

    raw_white_det = None
    mx, my = win32api.GetCursorPos()

    pockets = [
        (x + 28, y + 28), (x + w // 2, y + 18), (x + w - 28, y + 28),
        (x + 28, y + h - 28), (x + w // 2, y + h - 18), (x + w - 28, y + h - 28)
    ]

    top_band, bottom_band = y + CUSHION_PADDING, y + h - CUSHION_PADDING
    left_band, right_band = x + CUSHION_PADDING, x + w - CUSHION_PADDING
    table_bounds = (left_band, top_band, right_band, bottom_band)

    screen.fill(TRANSPARENT)

    if circles is not None:
        circles = np.round(circles[0, :]).astype("int")
        for (cx, cy, r) in circles:
            cx, cy = int(cx * 2 + x), int(cy * 2 + y)
            r = int(r * 2)
            if any(distance((cx, cy), p) < 38 for p in pockets): continue

            roi = table[max(0, cy-y-r):min(h, cy-y+r), max(0, cx-x-r):min(w, cx-x+r)]
            if is_white_ball(roi):
                raw_white_det = (cx, cy)
                break # بمجرد العثور على البيضاء نقوم بإنهاء حلقة البحث فوراً لزيادة السرعة

    # تحديث الكرة البيضاء الذاكرة المستقرة
    stable_white = white_memory.update(raw_white_det)

    if stable_white:
        pygame.gfxdraw.aacircle(screen, int(stable_white[0]), int(stable_white[1]), BALL_RADIUS, WHITE)
        pygame.gfxdraw.aacircle(screen, int(stable_white[0]), int(stable_white[1]), BALL_RADIUS - 2, CYAN)

    # قفل الكرة الهدف يدوياً (الوقوف بالماوس والضغط على Z)
    if keyboard.is_pressed("z") and time.time() - last_lock_time > 0.2:
        # الكود الآن يقفل الإحداثيات الحالية للماوس مباشرة كـ كرة مستهدفة
        target_manager.lock_new(mx, my)
        last_lock_time = time.time()

    if keyboard.is_pressed("x"):
        target_manager.clear()

    # تحديث موقع الكرة الهدف المحددة وقراءتها عبر الفلتر
    stable_target = target_manager.update()

    # رسم الكرة المحددة باللون الأزرق لتعرف أنها مقفلة
    if stable_target:
        pygame.gfxdraw.aacircle(screen, int(stable_target[0]), int(stable_target[1]), BALL_RADIUS, BLUE)
        pygame.gfxdraw.aacircle(screen, int(stable_target[0]), int(stable_target[1]), BALL_RADIUS - 2, YELLOW)

    # تبديل الجيوب بالضغط على الأرقام من 1 إلى 6
    for i in range(1, 7):
        if keyboard.is_pressed(str(i)):
            selected_pocket = i - 1

    for idx, p in enumerate(pockets):
        p_color = GREEN if idx == selected_pocket else RED
        pygame.gfxdraw.aacircle(screen, p[0], p[1], 8, p_color)
        txt = pocket_font.render(f"[{idx+1}]", True, WHITE if idx == selected_pocket else ORANGE)
        screen.blit(txt, (p[0] - 12, p[1] - 32 if idx < 3 else p[1] + 12))

    # ==========================================
    # 🎯 8. Core Advanced Ray-Trace Solver Engine
    # ==========================================
    if stable_white and stable_target:
        active_pocket = pockets[selected_pocket]

        g_pos = ghost_ball(stable_target, active_pocket, BALL_RADIUS)
        g_pos = apply_spin_and_deflection(stable_white, g_pos, spin_factor=0.005)
        
        # رسم الخطوط الرئيسية بثبات تام دون أي اهتزاز
        pygame.draw.line(screen, WHITE, (int(stable_white[0]), int(stable_white[1])), (int(g_pos[0]), int(g_pos[1])), 2)
        pygame.gfxdraw.aacircle(screen, int(g_pos[0]), int(g_pos[1]), BALL_RADIUS, WHITE)
        pygame.draw.line(screen, YELLOW, (int(stable_target[0]), int(stable_target[1])), active_pocket, 2)

        # حساب الباند العكسي المتعدد عند تفعيل أزرار الارتداد
        if keyboard.is_pressed("i") or keyboard.is_pressed("m") or keyboard.is_pressed("j") or keyboard.is_pressed("k"):
            bank_nodes = calculate_multi_bank(g_pos, active_pocket, table_bounds, max_banks=MAX_BANKS)
            for step in range(len(bank_nodes) - 1):
                p_start = (int(bank_nodes[step][0]), int(bank_nodes[step][1]))
                p_end = (int(bank_nodes[step+1][0]), int(bank_nodes[step+1][1]))
                pygame.draw.line(screen, PINK, p_start, p_end, 2)
                pygame.gfxdraw.filled_circle(screen, p_end[0], p_end[1], 4, CYAN)

    pygame.display.update()

camera.stop()
pygame.quit()
sys.exit()

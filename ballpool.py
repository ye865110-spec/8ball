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
BALL_RADIUS = 16  # المقاس المعتمد والمثالي القديم
CUSHION_PADDING = 16

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
# 🧠 3. Ultra-Stable Memory Systems
# ==========================================
class PermanentWhiteBallMemory:
    def __init__(self):
        self.last_valid_pos = None  

    def update(self, raw_white):
        if raw_white is not None:
            self.last_valid_pos = raw_white
            return raw_white
        return self.last_valid_pos

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
        self.kf.P *= 2.
        self.kf.R *= 0.01  
        self.kf.Q *= 0.005

    def lock_new(self, x, y):
        self.locked_pos = (x, y)
        self.init_kf(x, y)

    def update(self):
        if self.kf is not None and self.locked_pos is not None:
            self.kf.predict()
            self.kf.update(np.array(self.locked_pos))
            return (float(self.kf.x[0]), float(self.kf.x[1]))
        return self.locked_pos

    def clear(self):
        self.locked_pos = None
        self.kf = None

white_memory = PermanentWhiteBallMemory()
target_manager = TargetBallManager()

selected_pocket = 0
table_region = None
last_lock_time = 0

# ==========================================
# 📐 4. Advanced Math & Physical Reflections
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

def draw_parallel_guidelines(surface, color, start, end, radius):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dist = math.hypot(dx, dy)
    if dist == 0: return

    ux = dx / dist
    uy = dy / dist
    nx = -uy * radius
    ny = ux * radius

    pygame.draw.line(surface, color, (int(start[0]), int(start[1])), (int(end[0]), int(end[1])), 1)
    pygame.draw.line(surface, color, (int(start[0] + nx), int(start[1] + ny)), (int(end[0] + nx), int(end[1] + ny)), 1)
    pygame.draw.line(surface, color, (int(start[0] - nx), int(start[1] - ny)), (int(end[0] - nx), int(end[1] - ny)), 1)

def calculate_manual_bank_point(target, pocket, bounds, side):
    """ حساب نقطة الارتداد الدقيقة بناءً على الباند المختار يدوياً عبر الحروف """
    left, top, right, bottom = bounds
    tx, ty = target
    px, py = pocket

    if side == 'top':
        mirrored_py = top - (py - top)
        if (mirrored_py - ty) != 0:
            bx = tx + (px - tx) * (top - ty) / (mirrored_py - ty)
            if left <= bx <= right: return (bx, top)
            
    elif side == 'bottom':
        mirrored_py = bottom + (bottom - py)
        if (mirrored_py - ty) != 0:
            bx = tx + (px - tx) * (bottom - ty) / (mirrored_py - ty)
            if left <= bx <= right: return (bx, bottom)
            
    elif side == 'left':
        mirrored_px = left - (px - left)
        if (mirrored_px - tx) != 0:
            by = ty + (py - ty) * (left - tx) / (mirrored_px - tx)
            if top <= by <= bottom: return (left, by)
            
    elif side == 'right':
        mirrored_px = right + (right - px)
        if (mirrored_px - tx) != 0:
            by = ty + (py - ty) * (right - tx) / (mirrored_px - tx)
            if top <= by <= bottom: return (right, by)
            
    return None

# ==========================================
# 🖼️ 5. Strict Filters & Snapping Engine
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

def is_strictly_white_ball(roi):
    if roi is None or roi.size == 0: return False
    
    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    h, w = gray_roi.shape
    
    edges = cv2.Canny(gray_roi, 100, 200)
    center_edges = edges[int(h*0.25):int(h*0.75), int(w*0.25):int(w*0.75)]
    edge_pixels = np.sum(center_edges > 0)
    
    if edge_pixels > 8: 
        return False

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_white = np.array([0, 0, 175]) 
    upper_white = np.array([180, 50, 255])
    mask = cv2.inRange(hsv, lower_white, upper_white)
    
    white_ratio = np.sum(mask == 255) / mask.size
    if white_ratio < 0.50: return False 
    
    center_roi = mask[int(h*0.35):int(h*0.65), int(w*0.35):int(w*0.65)]
    center_white_ratio = np.sum(center_roi == 255) / center_roi.size
    
    return center_white_ratio > 0.85

def find_precise_ball_center_near_mouse(table_img, mouse_table_x, mouse_table_y, search_radius=25):
    h, w, _ = table_img.shape
    
    min_x = max(0, mouse_table_x - search_radius)
    max_x = min(w, mouse_table_x + search_radius)
    min_y = max(0, mouse_table_y - search_radius)
    max_y = min(h, mouse_table_y + search_radius)
    
    roi = table_img[min_y:max_y, min_x:max_x]
    if roi.size == 0: return None
    
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(cv2.equalizeHist(gray), 5)
    
    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.0, minDist=30, param1=50, param2=15, minRadius=12, maxRadius=20)
    
    if circles is not None:
        circles = np.round(circles[0, :]).astype("int")
        best_circle = min(circles, key=lambda c: math.hypot(c[0] - search_radius, c[1] - search_radius))
        cx, cy, _ = best_circle
        return (min_x + cx, min_y + cy)
    
    return None

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

pocket_font = pygame.font.SysFont("Arial", 16, bold=True)
running = True

# ==========================================
# 🔄 7. Core Loop
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

    gray = cv2.cvtColor(table, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(cv2.equalizeHist(gray), 5)

    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.0, minDist=30, param1=70, param2=22, minRadius=12, maxRadius=20)

    raw_white_det = None
    mx, my = win32api.GetCursorPos()

    pockets = [
        (x + 24, y + 24), (x + w // 2, y + 14), (x + w - 24, y + 24),
        (x + 24, y + h - 24), (x + w // 2, y + h - 14), (x + w - 24, y + h - 24)
    ]

    top_band, bottom_band = y + CUSHION_PADDING, y + h - CUSHION_PADDING
    left_band, right_band = x + CUSHION_PADDING, x + w - CUSHION_PADDING
    table_bounds = (left_band, top_band, right_band, bottom_band)

    screen.fill(TRANSPARENT)

    if circles is not None:
        circles = np.round(circles[0, :]).astype("int")
        for (cx, cy, r) in circles:
            cx, cy = int(cx + x), int(cy + y) 
            if any(distance((cx, cy), p) < 40 for p in pockets): continue

            roi = table[max(0, cy-y-r):min(h, cy-y+r), max(0, cx-x-r):min(w, cx-x+r)]
            if is_strictly_white_ball(roi):
                raw_white_det = (cx, cy)
                break 

    stable_white = white_memory.update(raw_white_det)

    if stable_white:
        pygame.gfxdraw.aacircle(screen, int(stable_white[0]), int(stable_white[1]), BALL_RADIUS, WHITE)
        pygame.gfxdraw.aacircle(screen, int(stable_white[0]), int(stable_white[1]), BALL_RADIUS - 2, CYAN)

    if keyboard.is_pressed("z") and time.time() - last_lock_time > 0.15:
        mouse_table_x = mx - x
        mouse_table_y = my - y
        precise_center = find_precise_ball_center_near_mouse(table, mouse_table_x, mouse_table_y)
        
        if precise_center is not None:
            target_manager.lock_new(int(precise_center[0] + x), int(precise_center[1] + y))
        else:
            target_manager.lock_new(mx, my)
        last_lock_time = time.time()

    if keyboard.is_pressed("x"):
        target_manager.clear()

    stable_target = target_manager.update()

    if stable_target:
        pygame.gfxdraw.aacircle(screen, int(stable_target[0]), int(stable_target[1]), BALL_RADIUS, BLUE)
        pygame.gfxdraw.aacircle(screen, int(stable_target[0]), int(stable_target[1]), BALL_RADIUS - 2, YELLOW)

    for i in range(1, 7):
        if keyboard.is_pressed(str(i)):
            selected_pocket = i - 1

    for idx, p in enumerate(pockets):
        p_color = GREEN if idx == selected_pocket else RED
        pygame.gfxdraw.aacircle(screen, p[0], p[1], 6, p_color)
        txt = pocket_font.render(f"{idx+1}", True, WHITE if idx == selected_pocket else ORANGE)
        screen.blit(txt, (p[0] - 5, p[1] - 25 if idx < 3 else p[1] + 10))

    # ==========================================
    # 🎯 8. Dynamic Controlled Ray-Trace Engine
    # ==========================================
    if stable_white and stable_target:
        active_pocket = pockets[selected_pocket]
        
        # 🟢 رصد الحروف والتحكم اليدوي في اتجاه الباند المفرد بناءً على طلبك
        chosen_side = None
        if keyboard.is_pressed("i"): chosen_side = 'top'
        elif keyboard.is_pressed("m"): chosen_side = 'bottom'
        elif keyboard.is_pressed("j"): chosen_side = 'left'
        elif keyboard.is_pressed("k"): chosen_side = 'right'

        if chosen_side:
            # 1. حساب الباند اليدوي المختار فوراً
            bank_point = calculate_manual_bank_point(stable_target, active_pocket, table_bounds, chosen_side)
            
            if bank_point:
                g_pos = ghost_ball(stable_target, bank_point, BALL_RADIUS)
                # رسم الخطوط الثلاثية المتوازية للـ Ghost ball الموجهة للباند
                draw_parallel_guidelines(screen, GREEN, stable_white, g_pos, BALL_RADIUS)
                pygame.gfxdraw.aacircle(screen, int(g_pos[0]), int(g_pos[1]), BALL_RADIUS, WHITE)
                
                # خط من الكرة المحددة للباند (أصفر) ومن الباند للبوكيت (وردي)
                pygame.draw.line(screen, YELLOW, (int(stable_target[0]), int(stable_target[1])), (int(bank_point[0]), int(bank_point[1])), 2)
                pygame.draw.line(screen, PINK, (int(bank_point[0]), int(bank_point[1])), active_pocket, 2)
                pygame.gfxdraw.filled_circle(screen, int(bank_point[0]), int(bank_point[1]), 4, CYAN)
            else:
                # حل احتياطي ستريت إذا لم تتقاطع زاوية الحرف هندسياً
                g_pos = ghost_ball(stable_target, active_pocket, BALL_RADIUS)
                draw_parallel_guidelines(screen, GREEN, stable_white, g_pos, BALL_RADIUS)
                pygame.gfxdraw.aacircle(screen, int(g_pos[0]), int(g_pos[1]), BALL_RADIUS, WHITE)
                pygame.draw.line(screen, YELLOW, (int(stable_target[0]), int(stable_target[1])), active_pocket, 2)
        else:
            # 🎱 الوضع الافتراضي (ستريت عادي جداً ونظيف بدون أي باند عشوائي)
            g_pos = ghost_ball(stable_target, active_pocket, BALL_RADIUS)
            draw_parallel_guidelines(screen, GREEN, stable_white, g_pos, BALL_RADIUS)
            pygame.gfxdraw.aacircle(screen, int(g_pos[0]), int(g_pos[1]), BALL_RADIUS, WHITE)
            pygame.draw.line(screen, YELLOW, (int(stable_target[0]), int(stable_target[1])), active_pocket, 2)

    pygame.display.update()

camera.stop()
pygame.quit()
sys.exit()

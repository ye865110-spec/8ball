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
GUI_BG = (30, 30, 35)      
GUI_TEXT = (240, 240, 240)  
GUI_BTN = (200, 50, 50)     
GUI_HIDE_BTN = (50, 150, 50) 
GUI_ACTIVE_COLOR = (0, 162, 232)

last_known_mx = SCREEN_WIDTH // 2
last_known_my = SCREEN_HEIGHT // 2

# ==========================================
# 🎛️ 3. GUI Menu State
# ==========================================
gui_x, gui_y = 50, 50       
gui_w, gui_h = 160, 185       
is_dragging = False          
drag_offset_x = 0
drag_offset_y = 0
is_mouse_hovering_gui = False
window_has_focus = True     
is_hidden = False             

# 🕹️ متغيرات نظام القوة الفيزيائي
current_power = 50            
CUSHION_DEFORMATION = 6       # مقدار مسافة انضغاط المطاط بالبكسل

# ==========================================
# 🧠 4. Ultra-Stable Memory Systems
# ==========================================
class PermanentWhiteBallMemory:
    def __init__(self):
        self.last_valid_pos = None  

    def update(self, raw_white):
        if raw_white is not None:
            self.last_valid_pos = raw_white
            return raw_white
        return self.last_valid_pos
        
    def manual_lock(self, x, y):
        self.last_valid_pos = (x, y)

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
last_white_lock_time = 0
last_hide_toggle_time = 0
last_power_toggle_time = 0

# ==========================================
# 📐 5. Advanced Math & Physical Reflections
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

def calculate_manual_bank_point(target, pocket, bounds, side, power):
    """ 
    🎯 تحديث حركة النقطة: الآن النقطة (Cyan) تتحرك وتغوص بصرياً داخل الباند 
    عند تغيير القوة لتوضيح انضغاط جدار المطاط وتوسيع زاوية الخروج.
    """
    left, top, right, bottom = bounds
    tx, ty = target
    px, py = pocket

    # الحدود الافتراضية المعتمدة على حافة الكرة (قوة 50)
    adjusted_top = top + BALL_RADIUS
    adjusted_bottom = bottom - BALL_RADIUS
    adjusted_left = left + BALL_RADIUS
    adjusted_right = right - BALL_RADIUS

    # إزاحة الجدران هندسياً عند القوة الكاملة لامتصاص المطاط
    if power == 100:
        adjusted_top -= CUSHION_DEFORMATION
        adjusted_bottom += CUSHION_DEFORMATION
        adjusted_left -= CUSHION_DEFORMATION
        adjusted_right += CUSHION_DEFORMATION

    if side == 'top':
        mirrored_py = adjusted_top - (py - adjusted_top)
        if (mirrored_py - ty) != 0:
            bx = tx + (px - tx) * (adjusted_top - ty) / (mirrored_py - ty)
            if left <= bx <= right: 
                # إرجاع الإحداثي المشفت الجديد لكي يتحرك الخط والنقطة للداخل بصرياً
                return (bx, adjusted_top - BALL_RADIUS)
            
    elif side == 'bottom':
        mirrored_py = adjusted_bottom + (adjusted_bottom - py)
        if (mirrored_py - ty) != 0:
            bx = tx + (px - tx) * (adjusted_bottom - ty) / (mirrored_py - ty)
            if left <= bx <= right: 
                return (bx, adjusted_bottom + BALL_RADIUS)
            
    elif side == 'left':
        mirrored_px = adjusted_left - (px - adjusted_left)
        if (mirrored_px - tx) != 0:
            by = ty + (py - ty) * (adjusted_left - tx) / (mirrored_px - tx)
            if top <= by <= bottom: 
                return (adjusted_left - BALL_RADIUS, by)
            
    elif side == 'right':
        mirrored_px = adjusted_right + (adjusted_right - px)
        if (mirrored_px - tx) != 0:
            by = ty + (py - ty) * (adjusted_right - tx) / (mirrored_px - tx)
            if top <= by <= bottom: 
                return (adjusted_right + BALL_RADIUS, by)
            
    return None

# ==========================================
# 🖼️ 6. Strict Filters & Snapping Engine
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
    if np.sum(center_edges > 0) > 8: return False

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_white = np.array([0, 0, 175]) 
    upper_white = np.array([180, 50, 255])
    mask = cv2.inRange(hsv, lower_white, upper_white)
    if (np.sum(mask == 255) / mask.size) < 0.50: return False 
    
    center_roi = mask[int(h*0.35):int(h*0.65), int(w*0.35):int(w*0.65)]
    return (np.sum(center_roi == 255) / center_roi.size) > 0.85

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
        return (min_x + best_circle[0], min_y + best_circle[1])
    return None

# ==========================================
# 🎮 7. Initialize DirectX Overlay & Pygame
# ==========================================
pygame.init()
pygame.font.init()
pygame.mouse.set_visible(True)

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME)
hwnd = pygame.display.get_wm_info()["window"]

styles = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, styles | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST | win32con.WS_EX_NOACTIVATE)
win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*TRANSPARENT), 0, win32con.LWA_COLORKEY)

camera = dxcam.create(output_color="BGR")
camera.start(target_fps=FPS, video_mode=True)
clock = pygame.time.Clock()

pocket_font = pygame.font.SysFont("Arial", 16, bold=True)
gui_font = pygame.font.SysFont("Segoe UI", 12, bold=True)
gui_title_font = pygame.font.SysFont("Segoe UI", 11)

running = True

# ==========================================
# 🔄 8. Core Loop
# ==========================================
while running:
    clock.tick(FPS)
    
    try:
        mx, my = win32api.GetCursorPos()
        last_known_mx, last_known_my = mx, my
    except Exception:
        mx, my = last_known_mx, last_known_my

    if keyboard.is_pressed("f3") and time.time() - last_power_toggle_time > 0.2:
        current_power = 50
        last_power_toggle_time = time.time()
    elif keyboard.is_pressed("f4") and time.time() - last_power_toggle_time > 0.2:
        current_power = 100
        last_power_toggle_time = time.time()

    if keyboard.is_pressed("ctrl+h") and time.time() - last_hide_toggle_time > 0.3:
        is_hidden = not is_hidden
        last_hide_toggle_time = time.time()

    if not is_hidden:
        is_mouse_hovering_gui = (gui_x <= mx <= gui_x + gui_w) and (gui_y <= my <= gui_y + gui_h)
    else:
        is_mouse_hovering_gui = False

    if is_mouse_hovering_gui and not window_has_focus:
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, styles | win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST)
        window_has_focus = True
    elif not is_mouse_hovering_gui and window_has_focus:
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, styles | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST | win32con.WS_EX_NOACTIVATE)
        window_has_focus = False
        is_dragging = False

    for event in pygame.event.get():
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if is_mouse_hovering_gui:
                if (gui_x + 15 <= mx <= gui_x + 75) and (gui_y + 45 <= my <= gui_y + 75):
                    current_power = 50
                elif (gui_x + 85 <= mx <= gui_x + 145) and (gui_y + 45 <= my <= gui_y + 75):
                    current_power = 100
                elif (gui_x + 15 <= mx <= gui_x + gui_w - 15) and (gui_y + 95 <= my <= gui_y + 127):
                    is_hidden = True
                    last_hide_toggle_time = time.time()
                elif (gui_x + 15 <= mx <= gui_x + gui_w - 15) and (gui_y + 135 <= my <= gui_y + 167):
                    running = False
                else:
                    is_dragging = True
                    drag_offset_x = mx - gui_x
                    drag_offset_y = my - gui_y
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            is_dragging = False

    if is_dragging:
        gui_x = max(0, min(SCREEN_WIDTH - gui_w, mx - drag_offset_x))
        gui_y = max(0, min(SCREEN_HEIGHT - gui_h, my - drag_offset_y))

    if keyboard.is_pressed("ctrl+q"): running = False

    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

    screen.fill(TRANSPARENT)

    if is_hidden:
        pygame.display.update()
        continue

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

    pockets = [
        (x + 24, y + 24), (x + w // 2, y + 14), (x + w - 24, y + 24),
        (x + 24, y + h - 24), (x + w // 2, y + h - 14), (x + w - 24, y + h - 24)
    ]

    top_band, bottom_band = y + CUSHION_PADDING, y + h - CUSHION_PADDING
    left_band, right_band = x + CUSHION_PADDING, x + w - CUSHION_PADDING
    table_bounds = (left_band, top_band, right_band, bottom_band)

    if circles is not None:
        circles = np.round(circles[0, :]).astype("int")
        for (cx, cy, r) in circles:
            cx, cy = int(cx + x), int(cy + y) 
            if any(distance((cx, cy), p) < 40 for p in pockets): continue

            roi = table[max(0, cy-y-r):min(h, cy-y+r), max(0, cx-x-r):min(w, cx-x+r)]
            if is_strictly_white_ball(roi):
                raw_white_det = (cx, cy)
                break 

    if keyboard.is_pressed("a") and time.time() - last_white_lock_time > 0.15:
        mouse_table_x = mx - x
        mouse_table_y = my - y
        precise_white = find_precise_ball_center_near_mouse(table, mouse_table_x, mouse_table_y)
        if precise_white is not None:
            white_memory.manual_lock(int(precise_white[0] + x), int(precise_white[1] + y))
        else:
            white_memory.manual_lock(mx, my)
        last_white_lock_time = time.time()

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
    # 🎯 9. Advanced Ray-Trace Engine with Visual Shift
    # ==========================================
    if stable_white and stable_target:
        active_pocket = pockets[selected_pocket]
        chosen_side = None
        if keyboard.is_pressed("i"): chosen_side = 'top'
        elif keyboard.is_pressed("m"): chosen_side = 'bottom'
        elif keyboard.is_pressed("j"): chosen_side = 'left'
        elif keyboard.is_pressed("k"): chosen_side = 'right'

        if chosen_side:
            bank_point = calculate_manual_bank_point(stable_target, active_pocket, table_bounds, chosen_side, current_power)
            if bank_point:
                g_pos = ghost_ball(stable_target, bank_point, BALL_RADIUS)
                draw_parallel_guidelines(screen, GREEN, stable_white, g_pos, BALL_RADIUS)
                pygame.gfxdraw.aacircle(screen, int(g_pos[0]), int(g_pos[1]), BALL_RADIUS, WHITE)
                
                # خطوط الرسم والتقاطع ستتحرك بصرياً للداخل مع قوة 100% الآن لتوضح انحراف زاوية الارتداد
                pygame.draw.line(screen, YELLOW, (int(stable_target[0]), int(stable_target[1])), (int(bank_point[0]), int(bank_point[1])), 2)
                pygame.draw.line(screen, PINK, (int(bank_point[0]), int(bank_point[1])), active_pocket, 2)
                pygame.gfxdraw.filled_circle(screen, int(bank_point[0]), int(bank_point[1]), 4, CYAN)
            else:
                g_pos = ghost_ball(stable_target, active_pocket, BALL_RADIUS)
                draw_parallel_guidelines(screen, GREEN, stable_white, g_pos, BALL_RADIUS)
                pygame.gfxdraw.aacircle(screen, int(g_pos[0]), int(g_pos[1]), BALL_RADIUS, WHITE)
                pygame.draw.line(screen, YELLOW, (int(stable_target[0]), int(stable_target[1])), active_pocket, 2)
        else:
            g_pos = ghost_ball(stable_target, active_pocket, BALL_RADIUS)
            draw_parallel_guidelines(screen, GREEN, stable_white, g_pos, BALL_RADIUS)
            pygame.gfxdraw.aacircle(screen, int(g_pos[0]), int(g_pos[1]), BALL_RADIUS, WHITE)
            pygame.draw.line(screen, YELLOW, (int(stable_target[0]), int(stable_target[1])), active_pocket, 2)

    # ==========================================
    # 🖼️ 10. Rendering The Matured Floating GUI Menu
    # ==========================================
    pygame.draw.rect(screen, GUI_BG, (gui_x, gui_y, gui_w, gui_h))
    pygame.draw.rect(screen, CYAN, (gui_x, gui_y, gui_w, gui_h), 1)  
    pygame.draw.line(screen, CYAN, (gui_x, gui_y + 25), (gui_x + gui_w, gui_y + 25), 1) 

    title_txt = gui_title_font.render("🎱 Billiards Tool Panel", True, CYAN)
    screen.blit(title_txt, (gui_x + 12, gui_y + 4))

    power_lbl = gui_title_font.render(f"Target Power: {current_power}%", True, ORANGE)
    screen.blit(power_lbl, (gui_x + 15, gui_y + 28))

    # زر 50% (F3)
    p50_color = GUI_ACTIVE_COLOR if current_power == 50 else (60, 60, 65)
    pygame.draw.rect(screen, p50_color, (gui_x + 15, gui_y + 45, 60, 30))
    pygame.draw.rect(screen, WHITE, (gui_x + 15, gui_y + 45, 60, 30), 1)
    p50_txt = gui_font.render("50% (F3)", True, WHITE)
    screen.blit(p50_txt, (gui_x + 22, gui_y + 52))

    # زر 100% (F4)
    p100_color = GUI_ACTIVE_COLOR if current_power == 100 else (60, 60, 65)
    pygame.draw.rect(screen, p100_color, (gui_x + 85, gui_y + 45, 60, 30))
    pygame.draw.rect(screen, WHITE, (gui_x + 85, gui_y + 45, 60, 30), 1)
    p100_txt = gui_font.render("100%(F4)", True, WHITE)
    screen.blit(p100_txt, (gui_x + 91, gui_y + 52))

    # زر الإخفاء المؤقت (HIDE TOOL)
    pygame.draw.rect(screen, GUI_HIDE_BTN, (gui_x + 15, gui_y + 95, gui_w - 30, 32))
    pygame.draw.rect(screen, WHITE, (gui_x + 15, gui_y + 95, gui_w - 30, 32), 1)
    hide_txt = gui_font.render("HIDE TOOL", True, WHITE)
    screen.blit(hide_txt, (gui_x + 45, gui_y + 102))

    # زر الإغلاق النهائي (CLOSE TOOL)
    pygame.draw.rect(screen, GUI_BTN, (gui_x + 15, gui_y + 135, gui_w - 30, 32))
    pygame.draw.rect(screen, WHITE, (gui_x + 15, gui_y + 135, gui_w - 30, 32), 1)
    exit_txt = gui_font.render("CLOSE TOOL", True, WHITE)
    screen.blit(exit_txt, (gui_x + 38, gui_y + 142))

    pygame.display.update()

camera.stop()
pygame.quit()
sys.exit()

import pygame
import win32gui
import win32con
import win32api
import mss
import cv2
import numpy as np
import math
import keyboard
import sys

# الحصول على أبعاد الشاشة الحالية
SCREEN_WIDTH = win32api.GetSystemMetrics(0)
SCREEN_HEIGHT = win32api.GetSystemMetrics(1)

# الألوان المستخدمة في الرسم
TRANSPARENT_COLOR = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 162, 232)
YELLOW = (255, 242, 0)
ORANGE = (255, 127, 39)
PINK = (255, 0, 128)

# المتغيرات العالمية للتحكم والقفل
locked_ball_center = None
selected_pocket_index = None
smooth_white_center = None
smooth_target_balls = {}
ALPHA = 0.25  # عامل التنعيم لمنع الرعشة

def calculate_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def is_white_ball(roi):
    if roi is None or roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_white = np.array([0, 0, 180])
    upper_white = np.array([180, 40, 255])
    mask = cv2.inRange(hsv, lower_white, upper_white)
    white_ratio = np.sum(mask == 255) / mask.size
    return white_ratio > 0.45

def apply_smoothing(current, previous, alpha):
    if previous is None:
        return current
    return (int(previous[0] * (1 - alpha) + current[0] * alpha),
            int(previous[1] * (1 - alpha) + current[1] * alpha))

def get_ghost_ball_position(target_ball, pocket, ball_radius):
    dx = target_ball[0] - pocket[0]
    dy = target_ball[1] - pocket[1]
    distance = math.sqrt(dx**2 + dy**2)
    if distance == 0:
        return target_ball
    ratio = (distance + (ball_radius * 2)) / distance
    return (int(pocket[0] + dx * ratio), int(pocket[1] + dy * ratio))

def get_line_circle_intersection(p1, p2, center, r):
    x1, y1 = p1
    x2, y2 = p2
    cx, cy = center
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0: return None
    a = dx**2 + dy**2
    b = 2 * (dx * (x1 - cx) + dy * (y1 - cy))
    c = (x1 - cx)**2 + (y1 - cy)**2 - (r * 2)**2
    discriminant = b**2 - 4 * a * c
    if discriminant < 0: return None
    valid_ts = [t for t in [(-b - math.sqrt(discriminant)) / (2 * a), (-b + math.sqrt(discriminant)) / (2 * a)] if 0 <= t <= 1]
    if not valid_ts: return None
    return (x1 + min(valid_ts) * dx, y1 + min(valid_ts) * dy)

def calculate_ray_cast_with_bounces(start_pos, angle, table_bounds, obstacle_balls, ball_radius, max_bounces=4):
    """حساب المسار الارتدادي الحر بناءً على زاوية الماوس والعصا"""
    points = [start_pos]
    curr_pos = list(start_pos)
    curr_dir = [math.cos(angle), math.sin(angle)]
    
    t_top = table_bounds["top"] + 42
    t_bottom = table_bounds["top"] + table_bounds["height"] - 42
    t_left = table_bounds["left"] + 42
    t_right = table_bounds["left"] + table_bounds["width"] - 42
    
    collision_ball = None
    ghost_ball_pos = None
    
    for bounce in range(max_bounces):
        ray_end = [curr_pos[0] + curr_dir[0] * 2500, curr_pos[1] + curr_dir[1] * 2500]
        
        if bounce == 0 and len(obstacle_balls) > 0:
            closest_t = float('inf')
            closest_hit = None
            for ball in obstacle_balls:
                hit_pt = get_line_circle_intersection(curr_pos, ray_end, ball, ball_radius)
                if hit_pt:
                    d_hit = calculate_distance(curr_pos, hit_pt)
                    if d_hit < closest_t:
                        closest_t = d_hit; closest_hit = hit_pt; collision_ball = ball
            if closest_hit:
                points.append((int(closest_hit[0]), int(closest_hit[1])))
                ghost_ball_pos = (int(closest_hit[0]), int(closest_hit[1]))
                break
                
        times = []
        if curr_dir[0] > 0: times.append((t_right - curr_pos[0]) / curr_dir[0])
        elif curr_dir[0] < 0: times.append((t_left - curr_pos[0]) / curr_dir[0])
        if curr_dir[1] > 0: times.append((t_bottom - curr_pos[1]) / curr_dir[1])
        elif curr_dir[1] < 0: times.append((t_top - curr_pos[1]) / curr_dir[1])
        
        valid_times = [t for t in times if t > 0.1]
        if not valid_times: break
        min_t = min(valid_times)
        curr_pos[0] += curr_dir[0] * min_t
        curr_pos[1] += curr_dir[1] * min_t
        points.append((int(curr_pos[0]), int(curr_pos[1])))
        
        if abs(curr_pos[0] - t_right) < 4 or abs(curr_pos[0] - t_left) < 4: curr_dir[0] = -curr_dir[0]
        if abs(curr_pos[1] - t_bottom) < 4 or abs(curr_pos[1] - t_top) < 4: curr_dir[1] = -curr_dir[1]
            
    return points, collision_ball, ghost_ball_pos

def detect_table_bounds(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_table = np.array([35, 40, 40])
    upper_table = np.array([130, 255, 255])
    mask = cv2.inRange(hsv, lower_table, upper_table)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest_contour) > 40000:
            x, y, w, h = cv2.boundingRect(largest_contour)
            return {"top": y, "left": x, "width": w, "height": h}
    return {"top": 0, "left": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}

def main():
    global locked_ball_center, selected_pocket_index, smooth_white_center, smooth_target_balls
    
    pygame.init()
    pygame.font.init()
    font = pygame.font.SysFont("Arial", 16, bold=True)
    pocket_font = pygame.font.SysFont("Arial", 22, bold=True)
    
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME | pygame.HWSURFACE | pygame.DOUBLEBUF)
    hwnd = pygame.display.get_wm_info()['window']
    
    styles = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, styles | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST)
    win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*TRANSPARENT_COLOR), 0, win32con.LWA_COLORKEY)

    clock = pygame.time.Clock()
    full_monitor = {"top": 0, "left": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}

    with mss.mss() as sct:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
            
            if keyboard.is_pressed('ctrl+q'): break

            # قراءة اختصارات الجيوب (من 1 إلى 6) واختصار التصفير (0) والمسح (X)
            for n in range(1, 7):
                if keyboard.is_pressed(str(n)): selected_pocket_index = n - 1
            if keyboard.is_pressed('0'): selected_pocket_index = None
            if keyboard.is_pressed('x'): locked_ball_center = None

            screen.fill(TRANSPARENT_COLOR)
            mx, my = win32api.GetCursorPos()
            
            # فحص إذا كان زر الماوس الأيسر مضغوطاً حالياً (تفعيل وضع حركة العصا)
            mouse_click_active = win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000

            full_img = np.array(sct.grab(full_monitor))
            full_frame = cv2.cvtColor(full_img, cv2.COLOR_BGRA2BGR)
            
            table = detect_table_bounds(full_frame)
            table_frame = full_frame[table["top"]:table["top"]+table["height"], table["left"]:table["left"]+table["width"]]
            
            if table_frame.size == 0: continue

            gray = cv2.cvtColor(table_frame, cv2.COLOR_BGR2GRAY)
            filtered = cv2.bilateralFilter(gray, 7, 50, 50)
            circles = cv2.HoughCircles(filtered, cv2.HOUGH_GRADIENT, dp=1, minDist=35, param1=50, param2=35, minRadius=14, maxRadius=22)

            raw_white_center = None
            raw_target_balls = []
            detected_radius = 16
            hovered_ball = None

            # رسم الجيوب الستة وثبيت أرقامها
            pockets = [
                (table["left"] + 25, table["top"] + 25), (table["left"] + table["width"] // 2, table["top"] + 15), (table["left"] + table["width"] - 25, table["top"] + 25),
                (table["left"] + 25, table["top"] + table["height"] - 25), (table["left"] + table["width"] // 2, table["top"] + table["height"] - 15), (table["left"] + table["width"] - 25, table["top"] + table["height"] - 25)
            ]
            for idx, pocket in enumerate(pockets):
                pygame.draw.circle(screen, RED, pocket, 15, 2)
                p_text = pocket_font.render(str(idx + 1), True, ORANGE)
                screen.blit(p_text, (pocket[0] - 8, pocket[1] - 35 if idx < 3 else pocket[1] + 15))

            if circles is not None:
                circles = np.uint16(np.around(circles))
                for i in circles[0, :]:
                    cx, cy, r = int(i[0]) + table["left"], int(i[1]) + table["top"], int(i[2])
                    if not (table["left"]+10 < cx < table["left"]+table["width"]-10 and table["top"]+10 < cy < table["top"]+table["height"]-10): continue

                    ball_roi = table_frame[max(0, int(i[1])-r):min(table["height"], int(i[1])+r), max(0, int(i[0])-r):min(table["width"], int(i[0])+r)]
                    if is_white_ball(ball_roi):
                        raw_white_center = (cx, cy)
                        detected_radius = r
                    else:
                        raw_target_balls.append((cx, cy))

                    if calculate_distance((mx, my), (cx, cy)) <= r:
                        hovered_ball = (cx, cy)

            # معالجة وتنعيم حركة الكرات لمنع الرعشة
            if raw_white_center:
                smooth_white_center = apply_smoothing(raw_white_center, smooth_white_center, ALPHA)
                pygame.draw.circle(screen, WHITE, smooth_white_center, detected_radius, 2)

            current_smooth_targets = []
            for ball in raw_target_balls:
                matched_ball = next((old for old in smooth_target_balls.keys() if calculate_distance(ball, old) < 15), None)
                s_ball = apply_smoothing(ball, smooth_target_balls.get(matched_ball) if matched_ball else None, ALPHA)
                current_smooth_targets.append(s_ball)
                
                if locked_ball_center and calculate_distance(s_ball, locked_ball_center) < 8:
                    pygame.draw.circle(screen, BLUE, s_ball, detected_radius, 2)
                else:
                    pygame.draw.circle(screen, YELLOW, s_ball, detected_radius, 1)

            smooth_target_balls = {b: b for b in current_smooth_targets}

            # تفعيل زر Z لقفل الكرة المستهدفة عند الوقوف عليها بالماوس
            if keyboard.is_pressed('z') and hovered_ball and hovered_ball != smooth_white_center:
                locked_ball_center = hovered_ball

            # --- محرك حساب المسارات والتوجيه الجديد ---
            if smooth_white_center:
                if mouse_click_active:
                    # [الوضع الأول]: عند ضغط كليك الماوس، تتحرك الخطوط بحرية تامة 360 درجة مع العصا والماوس
                    stick_angle = math.atan2(my - smooth_white_center[1], mx - smooth_white_center[0])
                    bounce_pts, hit_ball, ghost_pos = calculate_ray_cast_with_bounces(smooth_white_center, stick_angle, table, current_smooth_targets, detected_radius)
                    
                    if hit_ball and ghost_pos:
                        pygame.draw.line(screen, WHITE, smooth_white_center, ghost_pos, 2)
                        pygame.draw.circle(screen, WHITE, ghost_pos, detected_radius, 1)
                        t_dx, t_dy = hit_ball[0] - ghost_pos[0], hit_ball[1] - ghost_pos[1]
                        t_dist = math.sqrt(t_dx**2 + t_dy**2)
                        if t_dist > 0:
                            pygame.draw.line(screen, YELLOW, hit_ball, (int(hit_ball[0] + (t_dx/t_dist)*400), int(hit_ball[1] + (t_dy/t_dist)*400)), 3)
                    else:
                        for idx in range(len(bounce_pts) - 1):
                            pygame.draw.line(screen, WHITE if idx == 0 else GREEN, bounce_pts[idx], bounce_pts[idx+1], 2)
                
                elif locked_ball_center:
                    # [الوضع الثاني]: عند غياب الكليك، يتم التوجيه التلقائي المبني على قفل الكرة والبوكت المحدد
                    target_pocket = pockets[selected_pocket_index] if selected_pocket_index is not None else min(pockets, key=lambda p: calculate_distance(locked_ball_center, p))
                    ghost_pos = get_ghost_ball_position(locked_ball_center, target_pocket, detected_radius)
                    
                    pygame.draw.line(screen, WHITE, smooth_white_center, ghost_pos, 2)
                    pygame.draw.circle(screen, WHITE, ghost_pos, detected_radius, 1)
                    pygame.draw.line(screen, YELLOW, locked_ball_center, target_pocket, 3)
                    
                    # رسم مسار ارتداد الكرة الثانية (الوردي) التكتيكي
                    ref_dx, ref_dy = locked_ball_center[0] - ghost_pos[0], locked_ball_center[1] - ghost_pos[1]
                    ref_dist = math.sqrt(ref_dx**2 + ref_dy**2)
                    if ref_dist > 0:
                        pygame.draw.line(screen, PINK, locked_ball_center, (int(locked_ball_center[0] + (ref_dx/ref_dist)*300), int(locked_ball_center[1] + (ref_dy/ref_dist)*300)), 2)

            pygame.display.flip()
            clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()

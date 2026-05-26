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

# الألوان المستخدمة في الرسم العائم
TRANSPARENT_COLOR = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 162, 232)
YELLOW = (255, 242, 0)

# مصفوفات لتخزين المواقع السابقة لتطبيق فلاتر التنعيم ومنع الرعشة
smooth_white_center = None
smooth_target_balls = {}
ALPHA = 0.25 # عامل التنعيم (كلما قل، زاد الثبات وانعدمت الرعشة)

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
    """فلتر رياضي لمنع رعشة وتحرك الدوائر الناتج عن تغير بكسلات الإضاءة"""
    if previous is None:
        return current
    return (int(previous[0] * (1 - alpha) + current[0] * alpha),
            int(previous[1] * (1 - alpha) + current[1] * alpha))

def get_line_circle_intersection(p1, p2, center, r):
    x1, y1 = p1
    x2, y2 = p2
    cx, cy = center
    
    dx = x2 - x1
    dy = y2 - y1
    
    if dx == 0 and dy == 0:
        return None
        
    a = dx**2 + dy**2
    b = 2 * (dx * (x1 - cx) + dy * (y1 - cy))
    c = (x1 - cx)**2 + (y1 - cy)**2 - (r * 2)**2
    
    discriminant = b**2 - 4 * a * c
    if discriminant < 0:
        return None
        
    t1 = (-b - math.sqrt(discriminant)) / (2 * a)
    t2 = (-b + math.sqrt(discriminant)) / (2 * a)
    
    valid_ts = [t for t in [t1, t2] if 0 <= t <= 1]
    if not valid_ts:
        return None
        
    return (x1 + min(valid_ts) * dx, y1 + min(valid_ts) * dy)

def calculate_ray_cast_with_bounces(start_pos, angle, table_bounds, obstacle_balls, ball_radius, max_bounces=4):
    """حساب المسار الارتدادي الحر ممتداً من زاوية اتجاه العصا الحالية"""
    points = [start_pos]
    curr_pos = list(start_pos)
    
    # حساب متجه الاتجاه بناءً على الزاوية الفعلية للعصا حول الكرة
    curr_dir = [math.cos(angle), math.sin(angle)]
    
    t_top = table_bounds["top"] + 42
    t_bottom = table_bounds["top"] + table_bounds["height"] - 42
    t_left = table_bounds["left"] + 42
    t_right = table_bounds["left"] + table_bounds["width"] - 42
    
    collision_ball = None
    ghost_ball_pos = None
    
    for bounce in range(max_bounces):
        ray_end = [curr_pos[0] + curr_dir[0] * 2500, curr_pos[1] + curr_dir[1] * 2500]
        
        # فحص التصادم مع الكرات الأخرى بناءً على خط العصا الممتد
        if bounce == 0 and len(obstacle_balls) > 0:
            closest_t = float('inf')
            closest_hit = None
            
            for ball in obstacle_balls:
                hit_pt = get_line_circle_intersection(curr_pos, ray_end, ball, ball_radius)
                if hit_pt:
                    d_hit = calculate_distance(curr_pos, hit_pt)
                    if d_hit < closest_t:
                        closest_t = d_hit
                        closest_hit = hit_pt
                        collision_ball = ball
                        
            if closest_hit:
                points.append((int(closest_hit[0]), int(closest_hit[1])))
                ghost_ball_pos = (int(closest_hit[0]), int(closest_hit[1]))
                break
                
        # حساب الارتداد من المصدات والجدران
        times = []
        if curr_dir[0] > 0: times.append((t_right - curr_pos[0]) / curr_dir[0])
        elif curr_dir[0] < 0: times.append((t_left - curr_pos[0]) / curr_dir[0])
        if curr_dir[1] > 0: times.append((t_bottom - curr_pos[1]) / curr_dir[1])
        elif curr_dir[1] < 0: times.append((t_top - curr_pos[1]) / curr_dir[1])
        
        valid_times = [t for t in times if t > 0.1]
        if not valid_times:
            break
            
        min_t = min(valid_times)
        curr_pos[0] += curr_dir[0] * min_t
        curr_pos[1] += curr_dir[1] * min_t
        points.append((int(curr_pos[0]), int(curr_pos[1])))
        
        if abs(curr_pos[0] - t_right) < 4 or abs(curr_pos[0] - t_left) < 4:
            curr_dir[0] = -curr_dir[0]
        if abs(curr_pos[1] - t_bottom) < 4 or abs(curr_pos[1] - t_top) < 4:
            curr_dir[1] = -curr_dir[1]
            
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
    global smooth_white_center, smooth_target_balls
    
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME | pygame.HWSURFACE | pygame.DOUBLEBUF)
    hwnd = pygame.display.get_wm_info()['window']
    
    styles = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    new_styles = styles | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_styles)
    win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*TRANSPARENT_COLOR), 0, win32con.LWA_COLORKEY)

    clock = pygame.time.Clock()
    full_monitor = {"top": 0, "left": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}

    with mss.mss() as sct:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            
            if keyboard.is_pressed('ctrl+q'):
                running = False
                break

            screen.fill(TRANSPARENT_COLOR)
            mx, my = win32api.GetCursorPos()

            full_img = np.array(sct.grab(full_monitor))
            full_frame = cv2.cvtColor(full_img, cv2.COLOR_BGRA2BGR)
            
            table = detect_table_bounds(full_frame)
            table_frame = full_frame[table["top"]:table["top"]+table["height"], table["left"]:table["left"]+table["width"]]
            
            if table_frame.size == 0:
                continue

            gray = cv2.cvtColor(table_frame, cv2.COLOR_BGR2GRAY)
            filtered = cv2.bilateralFilter(gray, 7, 50, 50)
            
            circles = cv2.HoughCircles(
                filtered, cv2.HOUGH_GRADIENT, dp=1, minDist=35,
                param1=50, param2=35, minRadius=14, maxRadius=22
            )

            raw_white_center = None
            raw_target_balls = []
            detected_radius = 16

            if circles is not None:
                circles = np.uint16(np.around(circles))
                for i in circles[0, :]:
                    cx = int(i[0]) + table["left"]
                    cy = int(i[1]) + table["top"]
                    r = int(i[2])
                    
                    if not (table["left"]+10 < cx < table["left"]+table["width"]-10 and table["top"]+10 < cy < table["top"]+table["height"]-10):
                        continue

                    y1, y2 = max(0, int(i[1])-r), min(table["height"], int(i[1])+r)
                    x1, x2 = max(0, int(i[0])-r), min(table["width"], int(i[0])+r)
                    ball_roi = table_frame[y1:y2, x1:x2]

                    if is_white_ball(ball_roi):
                        raw_white_center = (cx, cy)
                        detected_radius = r
                    else:
                        raw_target_balls.append((cx, cy))

            # 1. تطبيق نظام التنعيم لمنع الرعشة المزعجة نهائياً واختفاء الدوائر العشوائية
            if raw_white_center:
                smooth_white_center = apply_smoothing(raw_white_center, smooth_white_center, ALPHA)
                pygame.draw.circle(screen, WHITE, smooth_white_center, detected_radius, 2)

            current_smooth_targets = []
            for ball in raw_target_balls:
                # العثور على أقرب كرة مسجلة سابقاً لتنعيم حركتها وثباتها
                matched_ball = None
                for old_ball in smooth_target_balls.keys():
                    if calculate_distance(ball, old_ball) < 15:
                        matched_ball = old_ball
                        break
                
                prev_val = smooth_target_balls.get(matched_ball) if matched_ball else None
                s_ball = apply_smoothing(ball, prev_val, ALPHA)
                current_smooth_targets.append(s_ball)
                pygame.draw.circle(screen, YELLOW, s_ball, detected_radius, 1)

            # تحديث مصفوفة الكرات المنعمة للفريم القادم
            smooth_target_balls = {b: b for b in current_smooth_targets}

            # 2. حساب الزاوية والاتجاه الدقيق المتطابق مع حركة عصا البلياردو والماوس حول الكرة البيضاء
            if smooth_white_center:
                # حساب الزاوية الحالية الممتدة من مركز الكرة البيضاء باتجاه مؤشر العصا/الماوس
                stick_angle = math.atan2(my - smooth_white_center[1], mx - smooth_white_center[0])
                
                # إرسال الزاوية الصحيحة للحصول على مسار ارتدادي متطابق مع العصا وثابت هندسياً
                bounce_pts, hit_ball, ghost_pos = calculate_ray_cast_with_bounces(
                    smooth_white_center, stick_angle, table, current_smooth_targets, detected_radius, max_bounces=4
                )
                
                if hit_ball and ghost_pos:
                    # رسم خط التصادم الأبيض الثابت بدون رعشة
                    pygame.draw.line(screen, WHITE, smooth_white_center, ghost_pos, 2)
                    pygame.draw.circle(screen, WHITE, ghost_pos, detected_radius, 1)
                    
                    # خط خروج الكرة المضروبة بالأصفر
                    t_dx = hit_ball[0] - ghost_pos[0]
                    t_dy = hit_ball[1] - ghost_pos[1]
                    t_dist = math.sqrt(t_dx**2 + t_dy**2)
                    if t_dist > 0:
                        t_end = (hit_ball[0] + (t_dx / t_dist) * 350, hit_ball[1] + (t_dy / t_dist) * 350)
                        pygame.draw.line(screen, YELLOW, hit_ball, t_end, 3)
                        pygame.draw.circle(screen, YELLOW, hit_ball, detected_radius, 2)
                        
                    # خط انحراف البيضاء بعد اللمس بالأخضر
                    out_dx, out_dy = -t_dy, t_dx
                    if (out_dx * (ghost_pos[0] - smooth_white_center[0]) + out_dy * (ghost_pos[1] - smooth_white_center[1])) < 0:
                        out_dx, out_dy = -out_dx, -out_dy
                    out_dist = math.sqrt(out_dx**2 + out_dy**2)
                    if out_dist > 0:
                        cue_end = (ghost_pos[0] + (out_dx / out_dist) * 200, ghost_pos[1] + (out_dy / out_dist) * 200)
                        pygame.draw.line(screen, GREEN, ghost_pos, cue_end, 2)
                else:
                    # رسم خطوط المسار الحر المتعرج الممتد مع زاوية العصا وثابت تماماً مع جدران اللعبة
                    for idx in range(len(bounce_pts) - 1):
                        color = WHITE if idx == 0 else GREEN
                        pygame.draw.line(screen, color, bounce_pts[idx], bounce_pts[idx+1], 2)
                        if idx > 0:
                            pygame.draw.circle(screen, RED, bounce_pts[idx], 4, 1)

            pygame.display.flip()
            clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()

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

locked_ball_center = None
selected_pocket_index = None

def calculate_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def is_white_ball(roi):
    if roi is None or roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_white = np.array([0, 0, 190])
    upper_white = np.array([180, 45, 255])
    mask = cv2.inRange(hsv, lower_white, upper_white)
    white_ratio = np.sum(mask == 255) / mask.size
    return white_ratio > 0.50

def get_ghost_ball_position(target_ball, pocket, ball_radius):
    dx = target_ball[0] - pocket[0]
    dy = target_ball[1] - pocket[1]
    distance = math.sqrt(dx**2 + dy**2)
    if distance == 0:
        return target_ball
    ratio = (distance + (ball_radius * 2)) / distance
    ghost_x = pocket[0] + dx * ratio
    ghost_y = pocket[1] + dy * ratio
    return (int(ghost_x), int(ghost_y))

def calculate_ray_cast_with_bounces(start_pos, direction_vector, table_bounds, max_bounces=3):
    """حساب مسار الأشعة المتعرج عند الاصطدام بجدران الطاولة (Bank Shots)"""
    points = [start_pos]
    curr_pos = list(start_pos)
    curr_dir = list(direction_vector)
    
    # تحديد حدود الطاولة الفعلية للارتداد
    t_top = table_bounds["top"] + 35
    t_bottom = table_bounds["top"] + table_bounds["height"] - 35
    t_left = table_bounds["left"] + 35
    t_right = table_bounds["left"] + table_bounds["width"] - 35
    
    for _ in range(max_bounces):
        if curr_dir[0] == 0 and curr_dir[1] == 0:
            break
            
        # حساب المسافات المتبقية للجدران الأربعة بناءً على اتجاه الحركة
        times = []
        
        if curr_dir[0] > 0: # الجدار الأيمن
            times.append((t_right - curr_pos[0]) / curr_dir[0])
        elif curr_dir[0] < 0: # الجدار الأيسر
            times.append((t_left - curr_pos[0]) / curr_dir[0])
            
        if curr_dir[1] > 0: # الجدار السفلي
            times.append((t_bottom - curr_pos[1]) / curr_dir[1])
        elif curr_dir[1] < 0: # الجدار العلوي
            times.append((t_top - curr_pos[1]) / curr_dir[1])
            
        valid_times = [t for t in times if t > 0.001]
        if not valid_times:
            # امتداد افتراضي طويل جداً إذا لم يتقاطع مع جدار قريب
            curr_pos[0] += curr_dir[0] * 500
            curr_pos[1] += curr_dir[1] * 500
            points.append((int(curr_pos[0]), int(curr_pos[1])))
            break
            
        min_t = min(valid_times)
        
        # تحديث النقطة القادمة للاصطدام
        curr_pos[0] += curr_dir[0] * min_t
        curr_pos[1] += curr_dir[1] * min_t
        points.append((int(curr_pos[0]), int(curr_pos[1])))
        
        # عكس الاتجاه فيزيائياً بناءً على الجدار المصطدم به
        if abs(curr_pos[0] - t_right) < 2 or abs(curr_pos[0] - t_left) < 2:
            curr_dir[0] = -curr_dir[0] # ارتداد أفقي
        if abs(curr_pos[1] - t_bottom) < 2 or abs(curr_pos[1] - t_top) < 2:
            curr_dir[1] = -curr_dir[1] # ارتداد رأسي
            
    return points

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
    global locked_ball_center, selected_pocket_index
    
    pygame.init()
    pygame.font.init()
    font = pygame.font.SysFont("Arial", 18, bold=True)
    pocket_font = pygame.font.SysFont("Arial", 22, bold=True)
    
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME | pygame.HWSURFACE | pygame.DOUBLEBUF)
    hwnd = pygame.display.get_wm_info()['window']
    
    styles = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    new_styles = styles | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, new_styles)
    
    win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*TRANSPARENT_COLOR), 0, win32con.LWA_COLORKEY)
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

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

            for n in range(1, 7):
                if keyboard.is_pressed(str(n)):
                    selected_pocket_index = n - 1
            if keyboard.is_pressed('0'):
                selected_pocket_index = None
                
            # زر X لتفريغ القفل والبدء من جديد
            if keyboard.is_pressed('x'):
                locked_ball_center = None

            screen.fill(TRANSPARENT_COLOR)
            mx, my = win32api.GetCursorPos()

            full_img = np.array(sct.grab(full_monitor))
            full_frame = cv2.cvtColor(full_img, cv2.COLOR_BGRA2BGR)
            
            table = detect_table_bounds(full_frame)
            table_frame = full_frame[table["top"]:table["top"]+table["height"], table["left"]:table["left"]+table["width"]]
            
            if table_frame.size == 0:
                continue

            gray = cv2.cvtColor(table_frame, cv2.COLOR_BGR2GRAY)
            filtered = cv2.bilateralFilter(gray, 9, 75, 75)
            
            circles = cv2.HoughCircles(
                filtered, cv2.HOUGH_GRADIENT, dp=1, minDist=30,
                param1=50, param2=30, minRadius=13, maxRadius=23
            )

            pockets = [
                (table["left"] + 25, table["top"] + 25),
                (table["left"] + table["width"] // 2, table["top"] + 15),
                (table["left"] + table["width"] - 25, table["top"] + 25),
                (table["left"] + 25, table["top"] + table["height"] - 25),
                (table["left"] + table["width"] // 2, table["top"] + table["height"] - 15),
                (table["left"] + table["width"] - 25, table["top"] + table["height"] - 25)
            ]

            # رسم الجيوب الستة
            for idx, pocket in enumerate(pockets):
                pygame.draw.circle(screen, RED, pocket, 15, 2)
                p_text = pocket_font.render(str(idx + 1), True, ORANGE)
                screen.blit(p_text, (pocket[0] - 8, pocket[1] - 35 if idx < 3 else pocket[1] + 15))

            white_ball_center = None
            hovered_ball = None
            detected_radius = 16

            if circles is not None:
                circles = np.uint16(np.around(circles))
                for i in circles[0, :]:
                    cx = int(i[0]) + table["left"]
                    cy = int(i[1]) + table["top"]
                    r = int(i[2])
                    ball_center = (cx, cy)

                    # منع التقاط أي دوائر وهمية تقع خارج نطاق حدود اللعبة المصممة
                    if not (table["left"] < cx < table["left"] + table["width"] and table["top"] < cy < table["top"] + table["height"]):
                        continue

                    y1, y2 = max(0, int(i[1])-r), min(table["height"], int(i[1])+r)
                    x1, x2 = max(0, int(i[0])-r), min(table["width"], int(i[0])+r)
                    ball_roi = table_frame[y1:y2, x1:x2]

                    if is_white_ball(ball_roi):
                        white_ball_center = ball_center
                        detected_radius = r
                        pygame.draw.circle(screen, WHITE, ball_center, r, 2)
                    else:
                        if locked_ball_center and calculate_distance(ball_center, locked_ball_center) < 5:
                            pygame.draw.circle(screen, BLUE, ball_center, r, 2)
                        else:
                            pygame.draw.circle(screen, YELLOW, ball_center, r, 1)

                    if calculate_distance((mx, my), ball_center) <= r:
                        hovered_ball = ball_center
                        pygame.draw.circle(screen, BLUE, ball_center, r + 4, 2)

            # تفعيل قفل كرة واحدة فقط عند ضغط Z
            if keyboard.is_pressed('z') and hovered_ball is not None:
                if white_ball_center and hovered_ball != white_ball_center:
                    locked_ball_center = hovered_ball

            # تتبع المسار وحساب الارتدادات المتعرجة
            if locked_ball_center:
                best_pocket = None
                if selected_pocket_index is not None and selected_pocket_index < len(pockets):
                    best_pocket = pockets[selected_pocket_index]
                else:
                    min_distance = float('inf')
                    for pocket in pockets:
                        dist = calculate_distance(locked_ball_center, pocket)
                        if dist < min_distance:
                            min_distance = dist
                            best_pocket = pocket

                if best_pocket:
                    ghost_pos = get_ghost_ball_position(locked_ball_center, best_pocket, detected_radius)
                    
                    # حساب خط الكرة المستهدفة الممتد للبوكت
                    pygame.draw.line(screen, YELLOW, locked_ball_center, best_pocket, 3)
                    pygame.draw.circle(screen, YELLOW, ghost_pos, detected_radius, 1)

                    if white_ball_center:
                        # الحصول على متجهات الحركة البدئية
                        dx = ghost_pos[0] - white_ball_center[0]
                        dy = ghost_pos[1] - white_ball_center[1]
                        
                        # استدعاء دالة رسم الارتدادات المتقدمة (ترسم المسار متعرجاً عند الجدران)
                        bounce_points = calculate_ray_cast_with_bounces(white_ball_center, [dx, dy], table, max_bounces=4)
                        
                        # رسم خطوط المسار الارتدادي بالكامل للكرة البيضاء
                        for idx in range(len(bounce_points) - 1):
                            # تبديل الألوان لإعطاء مظهر احترافي ومحاكي دقيق للصورة المستهدفة
                            color = WHITE if idx == 0 else GREEN
                            pygame.draw.line(screen, color, bounce_points[idx], bounce_points[idx+1], 2)
                            if idx > 0:
                                pygame.draw.circle(screen, RED, bounce_points[idx], 5, 1) # نقطة التصادم بالجدار

                    # نص الحالة العلوي
                    info_text = f"Esports AI Tool | Raycast Bounce Mode Active | Press 'X' to Unlock"
                    text_surface = font.render(info_text, True, GREEN)
                    screen.blit(text_surface, (table["left"] + 10, table["top"] - 30 if table["top"] > 40 else 20))

            pygame.display.flip()
            clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()

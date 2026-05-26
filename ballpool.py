import pygame
import win32gui
import win32con
import win32api
import dxcam
import cv2
import numpy as np
import math
import sys
import time

# =========================
# إعدادات عامة
# =========================

SCREEN_WIDTH = win32api.GetSystemMetrics(0)
SCREEN_HEIGHT = win32api.GetSystemMetrics(1)

FPS = 144
BALL_RADIUS = 16
SMOOTHING = 0.55

TRANSPARENT = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
GREEN = (0, 255, 0)
BLUE = (0, 162, 232)
PINK = (255, 0, 128)
ORANGE = (255, 165, 0)

# =========================
# متغيرات عامة
# =========================

locked_ball = None
selected_pocket = None

smooth_white = None
smooth_targets = []

smooth_ghost = None

table_region = None

# =========================
# أدوات مساعدة
# =========================

def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def smooth(current, previous, alpha=SMOOTHING):

    if previous is None:
        return current

    dx = current[0] - previous[0]
    dy = current[1] - previous[1]

    if abs(dx) < 1 and abs(dy) < 1:
        return previous

    return (
        previous[0] + dx * alpha,
        previous[1] + dy * alpha
    )

def is_white_ball(roi):

    if roi is None or roi.size == 0:
        return False

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    lower = np.array([0, 0, 170])
    upper = np.array([180, 60, 255])

    mask = cv2.inRange(hsv, lower, upper)

    ratio = np.sum(mask == 255) / mask.size

    return ratio > 0.45

def detect_table(frame):

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    lower = np.array([35, 40, 40])
    upper = np.array([100, 255, 255])

    mask = cv2.inRange(hsv, lower, upper)

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if contours:

        largest = max(contours, key=cv2.contourArea)

        if cv2.contourArea(largest) > 40000:

            x, y, w, h = cv2.boundingRect(largest)

            return {
                "left": x,
                "top": y,
                "width": w,
                "height": h
            }

    return None

def ghost_ball(target, pocket, radius):

    dx = target[0] - pocket[0]
    dy = target[1] - pocket[1]

    dist = math.hypot(dx, dy)

    if dist == 0:
        return target

    ratio = (dist + radius * 2) / dist

    return (
        pocket[0] + dx * ratio,
        pocket[1] + dy * ratio
    )

# =========================
# تشغيل pygame
# =========================

pygame.init()
pygame.font.init()

font = pygame.font.SysFont("Arial", 18, bold=True)
pocket_font = pygame.font.SysFont("Arial", 22, bold=True)

cached_text = font.render(
    "Static AI Aim Assist",
    True,
    GREEN
)

screen = pygame.display.set_mode(
    (SCREEN_WIDTH, SCREEN_HEIGHT),
    pygame.NOFRAME | pygame.DOUBLEBUF
)

hwnd = pygame.display.get_wm_info()["window"]

# =========================
# إعداد نافذة شفافة
# =========================

styles = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)

win32gui.SetWindowLong(
    hwnd,
    win32con.GWL_EXSTYLE,
    styles
    | win32con.WS_EX_LAYERED
    | win32con.WS_EX_TRANSPARENT
    | win32con.WS_EX_TOPMOST
)

win32gui.SetLayeredWindowAttributes(
    hwnd,
    win32api.RGB(*TRANSPARENT),
    0,
    win32con.LWA_COLORKEY
)

# =========================
# تشغيل dxcam
# =========================

camera = dxcam.create(output_color="BGR")

camera.start(
    target_fps=FPS,
    video_mode=True
)

clock = pygame.time.Clock()

# =========================
# الحلقة الرئيسية
# =========================

running = True

while running:

    dt = clock.tick(FPS) / 1000.0

    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()

    if keys[pygame.K_q] and keys[pygame.K_LCTRL]:
        running = False

    # =========================
    # تثبيت النافذة دائماً فوق اللعبة
    # =========================

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOACTIVATE
    )

    # =========================
    # التقاط الشاشة
    # =========================

    frame = camera.get_latest_frame()

    if frame is None:
        continue

    # =========================
    # اكتشاف الطاولة مرة واحدة فقط
    # =========================

    if table_region is None:

        detected = detect_table(frame)

        if detected:
            table_region = detected

    if table_region is None:
        continue

    x = table_region["left"]
    y = table_region["top"]
    w = table_region["width"]
    h = table_region["height"]

    table = frame[y:y+h, x:x+w]

    if table.size == 0:
        continue

    # =========================
    # تصغير الصورة لتسريع المعالجة
    # =========================

    small = cv2.resize(
        table,
        None,
        fx=0.5,
        fy=0.5
    )

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    blur = cv2.GaussianBlur(gray, (7, 7), 0)

    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=20,
        param1=50,
        param2=22,
        minRadius=7,
        maxRadius=13
    )

    raw_white = None
    raw_targets = []

    mx, my = win32api.GetCursorPos()

    hovered_ball = None

    pockets = [

        (x + 25, y + 25),
        (x + w // 2, y + 15),
        (x + w - 25, y + 25),

        (x + 25, y + h - 25),
        (x + w // 2, y + h - 15),
        (x + w - 25, y + h - 25)
    ]

    screen.fill(TRANSPARENT)

    # =========================
    # رسم الجيوب
    # =========================

    for idx, p in enumerate(pockets):

        pygame.draw.circle(
            screen,
            RED,
            (int(p[0]), int(p[1])),
            14,
            2
        )

        txt = pocket_font.render(
            str(idx + 1),
            True,
            ORANGE
        )

        screen.blit(
            txt,
            (
                p[0] - 8,
                p[1] - 35 if idx < 3 else p[1] + 15
            )
        )

    # =========================
    # اكتشاف الكرات
    # =========================

    if circles is not None:

        circles = np.squeeze(circles)

        for c in circles:

            cx, cy, r = c

            cx = int(cx * 2 + x)
            cy = int(cy * 2 + y)
            r = int(r * 2)

            roi = table[
                max(0, cy-y-r):min(h, cy-y+r),
                max(0, cx-x-r):min(w, cx-x+r)
            ]

            if is_white_ball(roi):

                raw_white = (cx, cy)

            else:

                raw_targets.append((cx, cy))

            if distance((mx, my), (cx, cy)) < r:

                hovered_ball = (cx, cy)

    # =========================
    # تنعيم الكرة البيضاء
    # =========================

    if raw_white:

        smooth_white = smooth(raw_white, smooth_white)

        pygame.draw.circle(
            screen,
            WHITE,
            (int(smooth_white[0]), int(smooth_white[1])),
            BALL_RADIUS,
            2
        )

    # =========================
    # تنعيم الكرات الأخرى
    # =========================

    new_targets = []

    for b in raw_targets:

        nearest = None

        for old in smooth_targets:

            if distance(b, old) < 25:
                nearest = old
                break

        sb = smooth(b, nearest)

        new_targets.append(sb)

        color = YELLOW

        if locked_ball:

            if distance(sb, locked_ball) < 10:
                color = BLUE

        pygame.draw.circle(
            screen,
            color,
            (int(sb[0]), int(sb[1])),
            BALL_RADIUS,
            2
        )

    smooth_targets = new_targets

    # =========================
    # قفل الكرة
    # =========================

    if keys[pygame.K_z]:

        if hovered_ball:

            locked_ball = hovered_ball

            time.sleep(0.15)

    if keys[pygame.K_x]:

        locked_ball = None

    # =========================
    # اختيار الجيب
    # =========================

    if keys[pygame.K_1]:
        selected_pocket = 0

    elif keys[pygame.K_2]:
        selected_pocket = 1

    elif keys[pygame.K_3]:
        selected_pocket = 2

    elif keys[pygame.K_4]:
        selected_pocket = 3

    elif keys[pygame.K_5]:
        selected_pocket = 4

    elif keys[pygame.K_6]:
        selected_pocket = 5

    elif keys[pygame.K_0]:
        selected_pocket = None

    # =========================
    # نظام التصويب
    # =========================

    if smooth_white and locked_ball:

        if selected_pocket is not None:

            target_pocket = pockets[selected_pocket]

        else:

            target_pocket = min(
                pockets,
                key=lambda p: distance(locked_ball, p)
            )

        gp = ghost_ball(
            locked_ball,
            target_pocket,
            BALL_RADIUS
        )

        smooth_ghost = smooth(gp, smooth_ghost)

        white_pos = (
            int(smooth_white[0]),
            int(smooth_white[1])
        )

        ghost_pos = (
            int(smooth_ghost[0]),
            int(smooth_ghost[1])
        )

        lock_pos = (
            int(locked_ball[0]),
            int(locked_ball[1])
        )

        # =========================
        # خطوط ناعمة بدون رعشة
        # =========================

        pygame.draw.aaline(
            screen,
            WHITE,
            white_pos,
            ghost_pos
        )

        pygame.draw.aaline(
            screen,
            YELLOW,
            lock_pos,
            (
                int(target_pocket[0]),
                int(target_pocket[1])
            )
        )

        pygame.draw.circle(
            screen,
            WHITE,
            ghost_pos,
            BALL_RADIUS,
            1
        )

        # =========================
        # خط الانعكاس
        # =========================

        dx = lock_pos[0] - ghost_pos[0]
        dy = lock_pos[1] - ghost_pos[1]

        dist = math.hypot(dx, dy)

        if dist > 0:

            rx = lock_pos[0] + (dx / dist) * 300
            ry = lock_pos[1] + (dy / dist) * 300

            pygame.draw.aaline(
                screen,
                PINK,
                lock_pos,
                (int(rx), int(ry))
            )

    screen.blit(cached_text, (x + 10, y - 30))

    pygame.display.update()

pygame.quit()

camera.stop()

sys.exit()

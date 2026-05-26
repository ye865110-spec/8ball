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

# =========================
# OpenCV تحسين
# =========================

cv2.setUseOptimized(True)
cv2.setNumThreads(0)

# =========================
# إعدادات
# =========================

FPS = 240

BALL_RADIUS = 22

SMOOTHING = 0.18

MAX_BALL_JUMP = 50

INNER_OFFSET = BALL_RADIUS + 18

SCREEN_WIDTH = win32api.GetSystemMetrics(0)
SCREEN_HEIGHT = win32api.GetSystemMetrics(1)

TRANSPARENT = (0, 0, 0)

WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 162, 232)
PINK = (255, 0, 128)
ORANGE = (255, 165, 0)
CYAN = (0, 255, 255)

# =========================
# متغيرات
# =========================

locked_ball = None
selected_pocket = None

smooth_white = None
smooth_targets = []
smooth_ghost = None

table_region = None

top_bank = False
bottom_bank = False
left_bank = False
right_bank = False

# =========================
# أدوات
# =========================

def distance(p1, p2):

    return math.hypot(
        p1[0] - p2[0],
        p1[1] - p2[1]
    )

def smooth(current, previous):

    if previous is None:
        return current

    if distance(current, previous) > MAX_BALL_JUMP:
        return previous

    return (
        previous[0] + (current[0] - previous[0]) * SMOOTHING,
        previous[1] + (current[1] - previous[1]) * SMOOTHING
    )

def aa_circle(surface, color, pos, radius):

    pygame.gfxdraw.aacircle(
        surface,
        int(pos[0]),
        int(pos[1]),
        radius,
        color
    )

def detect_table(frame):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    lower = np.array([30, 40, 40])
    upper = np.array([100, 255, 255])

    mask = cv2.inRange(
        hsv,
        lower,
        upper
    )

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if contours:

        largest = max(
            contours,
            key=cv2.contourArea
        )

        if cv2.contourArea(largest) > 40000:

            x, y, w, h = cv2.boundingRect(largest)

            return {
                "left": x,
                "top": y,
                "width": w,
                "height": h
            }

    return None

def is_white_ball(roi):

    if roi is None or roi.size == 0:
        return False

    hsv = cv2.cvtColor(
        roi,
        cv2.COLOR_BGR2HSV
    )

    h, s, v = cv2.split(hsv)

    white_pixels = np.sum(
        (s < 35) &
        (v > 200)
    )

    ratio = white_pixels / (roi.shape[0] * roi.shape[1])

    brightness = np.mean(v)

    return ratio > 0.52 and brightness > 210

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
# pygame
# =========================

pygame.init()
pygame.font.init()

screen = pygame.display.set_mode(
    (SCREEN_WIDTH, SCREEN_HEIGHT),
    pygame.NOFRAME
)

hwnd = pygame.display.get_wm_info()["window"]

font = pygame.font.SysFont(
    "Arial",
    18,
    bold=True
)

# =========================
# Overlay
# =========================

styles = win32gui.GetWindowLong(
    hwnd,
    win32con.GWL_EXSTYLE
)

win32gui.SetWindowLong(
    hwnd,
    win32con.GWL_EXSTYLE,
    styles
    | win32con.WS_EX_LAYERED
    | win32con.WS_EX_TRANSPARENT
    | win32con.WS_EX_TOPMOST
    | win32con.WS_EX_NOACTIVATE
)

win32gui.SetLayeredWindowAttributes(
    hwnd,
    win32api.RGB(*TRANSPARENT),
    0,
    win32con.LWA_COLORKEY
)

# =========================
# dxcam
# =========================

camera = dxcam.create(
    output_color="BGR"
)

camera.start(
    target_fps=FPS,
    region=(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT),
    video_mode=True
)

clock = pygame.time.Clock()

# =========================
# Main Loop
# =========================

running = True

while running:

    clock.tick(FPS)

    pygame.event.pump()

    # =========================
    # Events
    # =========================

    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:

            # خروج

            if event.key == pygame.K_q:

                if pygame.key.get_mods() & pygame.KMOD_CTRL:
                    running = False

            # قفل الكرة

            elif event.key == pygame.K_z:

                try:

                    mx, my = win32api.GetCursorPos()

                    if len(smooth_targets) > 0:

                        nearest = min(
                            smooth_targets,
                            key=lambda b: distance(
                                b,
                                (mx, my)
                            )
                        )

                        if distance(nearest, (mx, my)) < 35:

                            locked_ball = nearest

                except:
                    pass

            # إزالة القفل

            elif event.key == pygame.K_x:

                locked_ball = None

            # الجيوب

            elif event.key == pygame.K_1:
                selected_pocket = 0

            elif event.key == pygame.K_2:
                selected_pocket = 1

            elif event.key == pygame.K_3:
                selected_pocket = 2

            elif event.key == pygame.K_4:
                selected_pocket = 3

            elif event.key == pygame.K_5:
                selected_pocket = 4

            elif event.key == pygame.K_6:
                selected_pocket = 5

            elif event.key == pygame.K_0:
                selected_pocket = None

            # الباندات

            elif event.key == pygame.K_i:

                top_bank = not top_bank

                bottom_bank = False
                left_bank = False
                right_bank = False

            elif event.key == pygame.K_m:

                bottom_bank = not bottom_bank

                top_bank = False
                left_bank = False
                right_bank = False

            elif event.key == pygame.K_j:

                left_bank = not left_bank

                top_bank = False
                bottom_bank = False
                right_bank = False

            elif event.key == pygame.K_k:

                right_bank = not right_bank

                top_bank = False
                bottom_bank = False
                left_bank = False

    # =========================
    # تثبيت Overlay
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
    # اكتشاف الطاولة
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
    # حدود الباند
    # =========================

    top_band = y + INNER_OFFSET
    left_band = x + INNER_OFFSET
    right_band = x + w - INNER_OFFSET
    bottom_band = y + h - INNER_OFFSET

    # =========================
    # معالجة الصورة
    # =========================

    small = cv2.resize(
        table,
        None,
        fx=0.5,
        fy=0.5
    )

    gray = cv2.cvtColor(
        small,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.equalizeHist(gray)

    blur = cv2.medianBlur(
        gray,
        5
    )

    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.1,
        minDist=20,
        param1=70,
        param2=21,
        minRadius=6,
        maxRadius=17
    )

    raw_white = None
    raw_targets = []

    screen.fill(TRANSPARENT)

    # =========================
    # مربع الباند
    # =========================

    pygame.draw.rect(
        screen,
        CYAN,
        (
            left_band,
            top_band,
            right_band - left_band,
            bottom_band - top_band
        ),
        2
    )

    # =========================
    # الجيوب
    # =========================

    pockets = [

        (x + 25, y + 25),
        (x + w // 2, y + 15),
        (x + w - 25, y + 25),

        (x + 25, y + h - 25),
        (x + w // 2, y + h - 15),
        (x + w - 25, y + h - 25)
    ]

    for p in pockets:

        aa_circle(
            screen,
            RED,
            p,
            14
        )

    # =========================
    # كشف الكرات
    # =========================

    if circles is not None:

        circles = np.round(
            circles[0, :]
        ).astype("int")

        for (cx, cy, r) in circles:

            cx = int(cx * 2 + x)
            cy = int(cy * 2 + y)

            ignore = False

            for p in pockets:

                if distance((cx, cy), p) < 35:
                    ignore = True
                    break

            if ignore:
                continue

            roi = table[
                max(0, cy-y-r):min(h, cy-y+r),
                max(0, cx-x-r):min(w, cx-x+r)
            ]

            if is_white_ball(roi):

                raw_white = (cx, cy)

            else:

                raw_targets.append((cx, cy))

    # =========================
    # الكرة البيضاء
    # =========================

    if raw_white:

        smooth_white = smooth(
            raw_white,
            smooth_white
        )

        aa_circle(
            screen,
            WHITE,
            smooth_white,
            BALL_RADIUS
        )

    # =========================
    # الكرات الأخرى
    # =========================

    new_targets = []

    for b in raw_targets:

        nearest = None

        for old in smooth_targets:

            if distance(b, old) < 25:
                nearest = old
                break

        sb = smooth(
            b,
            nearest
        )

        new_targets.append(sb)

        color = YELLOW

        if locked_ball:

            if distance(sb, locked_ball) < 10:
                color = BLUE

        aa_circle(
            screen,
            color,
            sb,
            BALL_RADIUS
        )

    smooth_targets = new_targets

    # =========================
    # التصويب
    # =========================

    if smooth_white and locked_ball:

        if selected_pocket is not None:

            target_pocket = pockets[selected_pocket]

        else:

            target_pocket = min(
                pockets,
                key=lambda p: distance(
                    locked_ball,
                    p
                )
            )

        gp = ghost_ball(
            locked_ball,
            target_pocket,
            BALL_RADIUS
        )

        smooth_ghost = smooth(
            gp,
            smooth_ghost
        )

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
        # الخطوط
        # =========================

        pygame.draw.line(
            screen,
            WHITE,
            white_pos,
            ghost_pos,
            5
        )

        pygame.draw.line(
            screen,
            YELLOW,
            lock_pos,
            (
                int(target_pocket[0]),
                int(target_pocket[1])
            ),
            2
        )

        aa_circle(
            screen,
            WHITE,
            ghost_pos,
            BALL_RADIUS
        )

        # =========================
        # الباند العلوي
        # =========================

        if top_bank:

            mirrored = (
                target_pocket[0],
                top_band - (
                    target_pocket[1] - top_band
                )
            )

            dx = mirrored[0] - lock_pos[0]
            dy = mirrored[1] - lock_pos[1]

            if dy != 0:

                t = (
                    top_band - lock_pos[1]
                ) / dy

                bx = lock_pos[0] + dx * t

                pygame.draw.circle(
                    screen,
                    BLUE,
                    (int(bx), int(top_band)),
                    8
                )

        # =========================
        # الباند السفلي
        # =========================

        if bottom_bank:

            mirrored = (
                target_pocket[0],
                bottom_band + (
                    bottom_band - target_pocket[1]
                )
            )

            dx = mirrored[0] - lock_pos[0]
            dy = mirrored[1] - lock_pos[1]

            if dy != 0:

                t = (
                    bottom_band - lock_pos[1]
                ) / dy

                bx = lock_pos[0] + dx * t

                pygame.draw.circle(
                    screen,
                    BLUE,
                    (int(bx), int(bottom_band)),
                    8
                )

        # =========================
        # الباند الشمال
        # =========================

        if left_bank:

            mirrored = (
                left_band - (
                    target_pocket[0] - left_band
                ),
                target_pocket[1]
            )

            dx = mirrored[0] - lock_pos[0]

            if dx != 0:

                t = (
                    left_band - lock_pos[0]
                ) / dx

                by = lock_pos[1] + (
                    mirrored[1] - lock_pos[1]
                ) * t

                pygame.draw.circle(
                    screen,
                    BLUE,
                    (int(left_band), int(by)),
                    8
                )

        # =========================
        # الباند اليمين
        # =========================

        if right_bank:

            mirrored = (
                right_band + (
                    right_band - target_pocket[0]
                ),
                target_pocket[1]
            )

            dx = mirrored[0] - lock_pos[0]

            if dx != 0:

                t = (
                    right_band - lock_pos[0]
                ) / dx

                by = lock_pos[1] + (
                    mirrored[1] - lock_pos[1]
                ) * t

                pygame.draw.circle(
                    screen,
                    BLUE,
                    (int(right_band), int(by)),
                    8
                )

    pygame.display.update()

# =========================
# إنهاء
# =========================

camera.stop()

pygame.quit()

sys.exit()

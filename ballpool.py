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

# =========================
# تحسينات OpenCV
# =========================

cv2.setUseOptimized(True)
cv2.setNumThreads(0)

# =========================
# إعدادات
# =========================

FPS = 144
BALL_RADIUS = 16
SMOOTHING = 0.60

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
CYAN = (0, 200, 255)

# =========================
# متغيرات
# =========================

locked_ball = None
selected_pocket = None

smooth_white = None
smooth_targets = []
smooth_ghost = None

table_region = None

last_lock_time = 0

# =========================
# أدوات
# =========================

def distance(p1, p2):

    return math.hypot(
        p1[0] - p2[0],
        p1[1] - p2[1]
    )

def smooth(current, previous, alpha=SMOOTHING):

    if previous is None:
        return current

    return (
        previous[0] + (current[0] - previous[0]) * alpha,
        previous[1] + (current[1] - previous[1]) * alpha
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

    lower = np.array([0, 0, 170])
    upper = np.array([180, 70, 255])

    mask = cv2.inRange(
        hsv,
        lower,
        upper
    )

    ratio = np.sum(mask == 255) / mask.size

    return ratio > 0.42

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

pygame.mouse.set_visible(False)

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

pocket_font = pygame.font.SysFont(
    "Arial",
    22,
    bold=True
)

cached_text = font.render(
    "Static AI Aim Assist",
    True,
    GREEN
)

# =========================
# إعداد Overlay
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
    video_mode=True
)

clock = pygame.time.Clock()

# =========================
# Main Loop
# =========================

running = True

while running:

    clock.tick(FPS)

    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

    if keyboard.is_pressed("ctrl+q"):
        running = False

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

    frame = camera.get_latest_frame()

    if frame is None:
        continue

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
        dp=1.15,
        minDist=22,
        param1=60,
        param2=18,
        minRadius=7,
        maxRadius=15
    )

    raw_white = None
    raw_targets = []

    try:
        mx, my = win32api.GetCursorPos()
    except:
        mx, my = (0, 0)

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
    # حدود الطاولة الداخلية
    # =========================

    top_band = y + BALL_RADIUS
    left_band = x + BALL_RADIUS
    right_band = x + w - BALL_RADIUS
    bottom_band = y + h - BALL_RADIUS

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
    # رسم الجيوب
    # =========================

    for idx, p in enumerate(pockets):

        aa_circle(
            screen,
            RED,
            p,
            14
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

        circles = np.round(
            circles[0, :]
        ).astype("int")

        for (cx, cy, r) in circles:

            cx = int(cx * 2 + x)
            cy = int(cy * 2 + y)
            r = int(r * 2)

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

            if distance((mx, my), (cx, cy)) < r + 8:

                hovered_ball = (cx, cy)

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
    # قفل الكرة
    # =========================

    if keyboard.is_pressed("z"):

        current_time = time.time()

        if current_time - last_lock_time > 0.25:

            if hovered_ball and len(smooth_targets) > 0:

                locked_ball = min(
                    smooth_targets,
                    key=lambda b: distance(
                        b,
                        hovered_ball
                    )
                )

                last_lock_time = current_time

    if keyboard.is_pressed("x"):

        locked_ball = None

    # =========================
    # اختيار الجيب
    # =========================

    if keyboard.is_pressed("1"):
        selected_pocket = 0

    elif keyboard.is_pressed("2"):
        selected_pocket = 1

    elif keyboard.is_pressed("3"):
        selected_pocket = 2

    elif keyboard.is_pressed("4"):
        selected_pocket = 3

    elif keyboard.is_pressed("5"):
        selected_pocket = 4

    elif keyboard.is_pressed("6"):
        selected_pocket = 5

    elif keyboard.is_pressed("0"):
        selected_pocket = None

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

        aa_circle(
            screen,
            WHITE,
            ghost_pos,
            BALL_RADIUS
        )

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

        # =========================
        # الباند العلوي I
        # =========================

        if keyboard.is_pressed("i"):

            mirrored_pocket = (
                target_pocket[0],
                top_band - (
                    target_pocket[1] - top_band
                )
            )

            dx2 = mirrored_pocket[0] - lock_pos[0]
            dy2 = mirrored_pocket[1] - lock_pos[1]

            if dy2 != 0:

                t = (
                    top_band - lock_pos[1]
                ) / dy2

                hit_x = lock_pos[0] + dx2 * t
                hit_y = top_band

                hit_x = max(
                    left_band,
                    min(right_band, hit_x)
                )

                pygame.draw.circle(
                    screen,
                    BLUE,
                    (int(hit_x), int(hit_y)),
                    8
                )

                pygame.draw.aaline(
                    screen,
                    BLUE,
                    lock_pos,
                    (int(hit_x), int(hit_y))
                )

                pygame.draw.aaline(
                    screen,
                    BLUE,
                    (int(hit_x), int(hit_y)),
                    (
                        int(target_pocket[0]),
                        int(target_pocket[1])
                    )
                )

        # =========================
        # الباند السفلي M
        # =========================

        if keyboard.is_pressed("m"):

            mirrored_pocket = (
                target_pocket[0],
                bottom_band + (
                    bottom_band - target_pocket[1]
                )
            )

            dx2 = mirrored_pocket[0] - lock_pos[0]
            dy2 = mirrored_pocket[1] - lock_pos[1]

            if dy2 != 0:

                t = (
                    bottom_band - lock_pos[1]
                ) / dy2

                hit_x = lock_pos[0] + dx2 * t
                hit_y = bottom_band

                hit_x = max(
                    left_band,
                    min(right_band, hit_x)
                )

                pygame.draw.circle(
                    screen,
                    BLUE,
                    (int(hit_x), int(hit_y)),
                    8
                )

                pygame.draw.aaline(
                    screen,
                    BLUE,
                    lock_pos,
                    (int(hit_x), int(hit_y))
                )

                pygame.draw.aaline(
                    screen,
                    BLUE,
                    (int(hit_x), int(hit_y)),
                    (
                        int(target_pocket[0]),
                        int(target_pocket[1])
                    )
                )

        # =========================
        # الباند الشمال J
        # =========================

        if keyboard.is_pressed("j"):

            mirrored_pocket = (
                left_band - (
                    target_pocket[0] - left_band
                ),
                target_pocket[1]
            )

            dx2 = mirrored_pocket[0] - lock_pos[0]
            dy2 = mirrored_pocket[1] - lock_pos[1]

            if dx2 != 0:

                t = (
                    left_band - lock_pos[0]
                ) / dx2

                hit_x = left_band
                hit_y = lock_pos[1] + dy2 * t

                hit_y = max(
                    top_band,
                    min(bottom_band, hit_y)
                )

                pygame.draw.circle(
                    screen,
                    BLUE,
                    (int(hit_x), int(hit_y)),
                    8
                )

                pygame.draw.aaline(
                    screen,
                    BLUE,
                    lock_pos,
                    (int(hit_x), int(hit_y))
                )

                pygame.draw.aaline(
                    screen,
                    BLUE,
                    (int(hit_x), int(hit_y)),
                    (
                        int(target_pocket[0]),
                        int(target_pocket[1])
                    )
                )

        # =========================
        # الباند اليمين K
        # =========================

        if keyboard.is_pressed("k"):

            mirrored_pocket = (
                right_band + (
                    right_band - target_pocket[0]
                ),
                target_pocket[1]
            )

            dx2 = mirrored_pocket[0] - lock_pos[0]
            dy2 = mirrored_pocket[1] - lock_pos[1]

            if dx2 != 0:

                t = (
                    right_band - lock_pos[0]
                ) / dx2

                hit_x = right_band
                hit_y = lock_pos[1] + dy2 * t

                hit_y = max(
                    top_band,
                    min(bottom_band, hit_y)
                )

                pygame.draw.circle(
                    screen,
                    BLUE,
                    (int(hit_x), int(hit_y)),
                    8
                )

                pygame.draw.aaline(
                    screen,
                    BLUE,
                    lock_pos,
                    (int(hit_x), int(hit_y))
                )

                pygame.draw.aaline(
                    screen,
                    BLUE,
                    (int(hit_x), int(hit_y)),
                    (
                        int(target_pocket[0]),
                        int(target_pocket[1])
                    )
                )

    screen.blit(
        cached_text,
        (x + 10, y - 30)
    )

    pygame.display.update()

camera.stop()

pygame.quit()

sys.exit()

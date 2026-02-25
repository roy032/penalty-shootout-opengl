from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import math

# Camera-related variables (polar coordinates for gameplay view)
cam_angle = 5
cam_height = 5.0
radius = 22.0
fovY = 120
GRID_LENGTH = 600
rand_var = 423

# Game state
ball_state = 'ready'  # 'ready', 'moving'
ball_target = [0, 0, -15]
ball_pos = [0, 0.2, -5.3]
goalkeeper_pos = [0, 0, -12]
goalkeeper_target = [0, 0, -12]
goalkeeper_state = 'ready'  # 'ready', 'moving'
player1_score = 0
player2_score = 0
current_turn = 'player1_shoot'  # 'player1_shoot', 'player2_shoot'
shots_taken = {'player1': 0, 'player2': 0}
max_shots_per_player = 5
game_state = 'normal'  # 'normal', 'sudden_death', 'ended'
winner = None

# Pause/control state
is_paused = False
_current_idle_func = None  # Tracks currently set idle function so we can restore after pause

# Penalty results tracking for scoreboard (G = goal, M = miss)
player1_results = []
player2_results = []
last_shot_by = None       # 'player1' | 'player2'
last_shot_result = None   # 'G' | 'M'

# UI / Menu state
ui_state = 'menu'          # 'menu' | 'playing' | 'ended'
game_mode = 'pvp'          # 'pvp' | 'pvc'
difficulty = 'medium'      # 'easy' | 'medium' | 'hard'
menu_focus = 0             # 0: mode, 1: difficulty, 2: start

# Difficulty parameters (initialized by set_difficulty_params)
ball_speed = 0.2
gk_reaction_delay = 250
gk_reach_x = 2.5
gk_reach_y = 2.0
gk_guess_bias = 0.6  # chance to guess correct side

# AI control flags
ai_gk_action_pending = False
ai_shot_action_pending = False
ai_gk_wait_until_ms = None
ai_next_action_ms = None

# AI shooter placement error
shooter_err_x = 0.35
shooter_err_y = 0.35

# Shot history for adaptive GK and polish
shot_history = []  # list of (by: 'player1'|'player2', tx, ty)

# Per-shot speed variance and camera shake
current_shot_speed = 0.2
shake_until_ms = None

# Enhanced kick/save mechanics state
is_aiming = False           # Shooter is selecting target
aim_target = [0.0, 0.5, -14.5]  # Default aim point on goal mouth
accuracy_active = False
accuracy_phase = 0.0        # 0..1 oscillation
accuracy_dir = 1            # direction of phase change
ball_move_start_ms = None
gk_reaction_delay_ms = 220  # goalkeeper starts move after this delay once ball moves
gk_dive_started = False

def draw_text(x, y, text, font=GLUT_BITMAP_HELVETICA_18):
    glColor3f(1,1,1)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, 1000, 0, 800)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glRasterPos2f(x, y)
    for ch in text:
        glutBitmapCharacter(font, ord(ch))
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

def draw_cube():
    glBegin(GL_QUADS)
    glVertex3f(-0.5, -0.5, 0.5)
    glVertex3f(0.5, -0.5, 0.5)
    glVertex3f(0.5, 0.5, 0.5)
    glVertex3f(-0.5, 0.5, 0.5)
    glVertex3f(-0.5, -0.5, -0.5)
    glVertex3f(-0.5, 0.5, -0.5)
    glVertex3f(0.5, 0.5, -0.5)
    glVertex3f(0.5, -0.5, -0.5)
    glVertex3f(-0.5, -0.5, -0.5)
    glVertex3f(-0.5, -0.5, 0.5)
    glVertex3f(-0.5, 0.5, 0.5)
    glVertex3f(-0.5, 0.5, -0.5)
    glVertex3f(0.5, -0.5, -0.5)
    glVertex3f(0.5, 0.5, -0.5)
    glVertex3f(0.5, 0.5, 0.5)
    glVertex3f(0.5, -0.5, 0.5)
    glVertex3f(-0.5, 0.5, -0.5)
    glVertex3f(-0.5, 0.5, 0.5)
    glVertex3f(0.5, 0.5, 0.5)
    glVertex3f(0.5, 0.5, -0.5)
    glVertex3f(-0.5, -0.5, -0.5)
    glVertex3f(0.5, -0.5, -0.5)
    glVertex3f(0.5, -0.5, 0.5)
    glVertex3f(-0.5, -0.5, 0.5)
    glEnd()

def draw_ground():
    glColor3f(0.0, 0.6, 0.0)
    glBegin(GL_QUADS)
    glVertex3f(-10, 0, -20)
    glVertex3f(10, 0, -20)
    glVertex3f(10, 0, 10)
    glVertex3f(-10, 0, 10)
    glEnd()

    glColor3f(1, 1, 1)
    glBegin(GL_LINE_STRIP)
    for i in range(0, 181, 5):
        angle_rad = math.radians(i)
        x = math.cos(angle_rad) * 2
        z = math.sin(angle_rad) * 2 - 4
        glVertex3f(x, 0.01, z)
    glEnd()

    glPushMatrix()
    glColor3f(1, 1, 1)
    glTranslatef(0, 0.01, -5.3)
    glScalef(0.2, 0.2, 0.2)
    draw_cube()
    glPopMatrix()

    glBegin(GL_LINE_LOOP)
    glVertex3f(-7, 0.01, -20)
    glVertex3f(7, 0.01, -20)
    glVertex3f(7, 0.01, -4)
    glVertex3f(-7, 0.01, -4)
    glEnd()
    
    glBegin(GL_LINE_LOOP)
    glVertex3f(-5, 0.01, -10)
    glVertex3f(5, 0.01, -10)
    glVertex3f(5, 0.01, -20)
    glVertex3f(-5, 0.01, -20)
    glEnd()

def draw_goalkeeper():
    glPushMatrix()
    glTranslatef(goalkeeper_pos[0], goalkeeper_pos[1], goalkeeper_pos[2])
    glColor3f(0.1, 0.3, 0.9)  # Jersey (blue)
    glPushMatrix()
    glTranslatef(0, 1.2, 0)
    glScalef(0.6, 1.2, 0.3)
    draw_cube()
    glPopMatrix()

    glColor3f(1.0, 0.8, 0.6)  # Head (skin)
    glPushMatrix()
    glTranslatef(0, 2.2, 0)
    glutSolidSphere(0.25, 16, 16)
    glPopMatrix()

    glColor3f(0.1, 0.3, 0.9)  # Left arm (blue)
    glPushMatrix()
    glTranslatef(-0.5, 1.2, 0)
    glScalef(0.2, 1.0, 0.2)
    draw_cube()
    glPopMatrix()

    glPushMatrix()
    glTranslatef(0.5, 1.2, 0)
    glScalef(0.2, 1.0, 0.2)
    draw_cube()
    glPopMatrix()

    glColor3f(1, 1, 1)  # Left leg (white)
    glPushMatrix()
    glTranslatef(-0.2, 0.3, 0)
    glScalef(0.2, 0.6, 0.2)
    draw_cube()
    glPopMatrix()

    glPushMatrix()
    glTranslatef(0.2, 0.3, 0)
    glScalef(0.2, 0.6, 0.2)
    draw_cube()
    glPopMatrix()

    glPopMatrix()

def draw_shooter():
    glPushMatrix()
    glTranslatef(0, 0, -5.3)
    glColor3f(0.9, 0.1, 0.1)  # Jersey (red)
    glPushMatrix()
    glTranslatef(0, 1.2, 0)
    glScalef(0.6, 1.2, 0.3)
    draw_cube()
    glPopMatrix()

    glColor3f(1.0, 0.8, 0.6)  # Head (skin)
    glPushMatrix()
    glTranslatef(0, 2.2, 0)
    glutSolidSphere(0.25, 16, 16)
    glPopMatrix()

    glColor3f(0.9, 0.1, 0.1)  # Left arm (red)
    glPushMatrix()
    glTranslatef(-0.5, 1.2, 0)
    glScalef(0.2, 1.0, 0.2)
    draw_cube()
    glPopMatrix()

    glPushMatrix()
    glTranslatef(0.5, 1.2, 0)
    glScalef(0.2, 1.0, 0.2)
    draw_cube()
    glPopMatrix()

    glColor3f(0.1, 0.1, 0.1)  # Left leg (black)
    glPushMatrix()
    glTranslatef(-0.2, 0.3, 0)
    glScalef(0.2, 0.6, 0.2)
    draw_cube()
    glPopMatrix()

    glPushMatrix()
    glTranslatef(0.2, 0.3, 0)
    glScalef(0.2, 0.6, 0.2)
    draw_cube()
    glPopMatrix()

    glPopMatrix()

def draw_goal_post():
    glColor3f(1, 1, 1)
    goal_width = 8.0
    goal_height = 4.0
    goal_depth = 2.0
    post_thickness = 0.1

    def draw_bar(x, y, z, sx, sy, sz):
        glPushMatrix()
        glTranslatef(x, y, z)
        glScalef(sx, sy, sz)
        draw_cube()
        glPopMatrix()

    half_width = goal_width / 2
    front_z = -15
    back_z = front_z + goal_depth
    
    draw_bar(-half_width, goal_height / 2, front_z, post_thickness, goal_height, post_thickness)
    draw_bar(half_width, goal_height / 2, front_z, post_thickness, goal_height, post_thickness)
    draw_bar(0, goal_height, front_z, goal_width, post_thickness, post_thickness)
    draw_bar(0, 0, front_z, goal_width, post_thickness, 0.05)
    draw_bar(-half_width, goal_height / 2, back_z, post_thickness, goal_height, post_thickness)
    draw_bar(half_width, goal_height / 2, back_z, post_thickness, goal_height, post_thickness)
    draw_bar(0, goal_height, back_z, goal_width, post_thickness, post_thickness)
    draw_bar(-half_width, goal_height, (front_z + back_z) / 2, post_thickness, post_thickness, goal_depth)
    draw_bar(half_width, goal_height, (front_z + back_z) / 2, post_thickness, post_thickness, goal_depth)
    
    glColor3f(0.8, 0.8, 0.8)
    net_div = 10
    glBegin(GL_LINES)
    for i in range(net_div + 1):
        x = -half_width + i * (goal_width / net_div)
        glVertex3f(x, 0, front_z)
        glVertex3f(x, goal_height, front_z)
    for j in range(net_div + 1):
        y = j * (goal_height / net_div)
        glVertex3f(-half_width, y, front_z)
        glVertex3f(half_width, y, front_z)
    for i in range(net_div + 1):
        x = -half_width + i * (goal_width / net_div)
        glVertex3f(x, goal_height, front_z)
        glVertex3f(x, goal_height, back_z)
    for j in range(net_div + 1):
        z = front_z + j * (goal_depth / net_div)
        glVertex3f(-half_width, goal_height, z)
        glVertex3f(half_width, goal_height, z)
    for i in range(net_div + 1):
        y = i * (goal_height / net_div)
        glVertex3f(-half_width, y, front_z)
        glVertex3f(-half_width, y, back_z)
    for j in range(net_div + 1):
        z = front_z + j * (goal_depth / net_div)
        glVertex3f(-half_width, 0, z)
        glVertex3f(-half_width, goal_height, z)
    for i in range(net_div + 1):
        y = i * (goal_height / net_div)
        glVertex3f(half_width, y, front_z)
        glVertex3f(half_width, y, back_z)
    for j in range(net_div + 1):
        z = front_z + j * (goal_depth / net_div)
        glVertex3f(half_width, 0, z)
        glVertex3f(half_width, goal_height, z)
    glEnd()

def draw_ball():
    glColor3f(1.0, 1.0, 1.0)
    glPushMatrix()
    glTranslatef(ball_pos[0], ball_pos[1], ball_pos[2])
    glutSolidSphere(0.2, 20, 20)
    glPopMatrix()

def keyboardListener(key, x, y):
    global ball_state, ball_target, goalkeeper_state, goalkeeper_target, current_turn
    global player1_score, player2_score, shots_taken, game_state, winner
    global is_paused, _current_idle_func
    global is_aiming, aim_target, accuracy_active, accuracy_phase, accuracy_dir
    global ui_state, game_mode, difficulty, menu_focus
    key = key.decode('utf-8')

    # Global controls
    if key in ['q', '\x1b']:
        glutLeaveMainLoop()
        return
    if key == 'r':
        reset_game()
        return
    if key == 'p':
        # Toggle pause
        if not is_paused:
            is_paused = True
            # Suspend ongoing animation by clearing idle func
            glutIdleFunc(None)
        else:
            is_paused = False
            # Restore appropriate animation if something is moving; otherwise neutral idle
            if ball_state == 'moving':
                glutIdleFunc(update_ball)
            elif goalkeeper_state == 'moving':
                glutIdleFunc(update_goalkeeper)
            else:
                glutIdleFunc(idle)
        glutPostRedisplay()
        return

    # Menu handling
    if ui_state == 'menu':
        if key in ['w', 's']:
            menu_focus = (menu_focus + (1 if key == 's' else -1)) % 3
        elif key in ['a', 'd']:
            if menu_focus == 0:
                game_mode = 'pvc' if (game_mode == 'pvp' and key == 'd') else ('pvp' if key == 'a' else game_mode)
            elif menu_focus == 1:
                order = ['easy','medium','hard']
                idx = order.index(difficulty)
                idx = (idx + (1 if key == 'd' else -1)) % len(order)
                difficulty = order[idx]
        elif key in ['\r', ' ']:
            # start game
            ui_state = 'playing'
            set_difficulty_params()
            reset_game()
        glutPostRedisplay()
        return

    # Ignore gameplay inputs when paused or game ended
    if winner and key.lower() == 'm':
        go_to_menu()
        return
    if is_paused or game_state == 'ended' or ui_state != 'playing':
        return

    # Player 1 controls (WASD) — human shooter in both PvP and PvC
    if current_turn == 'player1_shoot' and key in ['w', 'a', 's', 'd'] and ball_state == 'ready' and (game_mode in ['pvp','pvc']):
        if key == 'a':  # Bottom left corner
            ball_target = [-2.99, 0.5, -14.5]
        elif key == 'd':  # Bottom right corner
            ball_target = [2.99, 0.5, -14.5]
        elif key == 'w':  # Top right corner
            ball_target = [2.99, 3, -14.5]
        elif key == 's':  # Top left corner
            ball_target = [-2.99, 3, -14.5]
        ball_state = 'moving'
        _current_idle_func = update_ball
        glutIdleFunc(update_ball)
    elif current_turn == 'player2_shoot' and key in ['w', 'a', 's', 'd'] and goalkeeper_state == 'ready' and (game_mode in ['pvp','pvc']):
        if key == 'a':  # Left side
            goalkeeper_target = [-2.5, 0, -12]
        elif key == 'd':  # Right side
            goalkeeper_target = [2.5, 0, -12]
        elif key == 'w':  # Upper center
            goalkeeper_target = [0, 2.0, -12]
        elif key == 's':  # Lower center
            goalkeeper_target = [0, 0, -12]
        goalkeeper_state = 'moving'
        _current_idle_func = update_goalkeeper
        glutIdleFunc(update_goalkeeper)

    # Player 2 controls (IJKL) — disabled in PvC (computer shoots as player2)
    elif current_turn == 'player2_shoot' and key in ['i', 'j', 'k', 'l'] and ball_state == 'ready' and game_mode == 'pvp':
        if key == 'j':  # Bottom left corner
            ball_target = [-2.99, 0.5, -14.5]
        elif key == 'l':  # Bottom right corner
            ball_target = [2.99, 0.5, -14.5]
        elif key == 'i':  # Top right corner
            ball_target = [2.99, 3, -14.5]
        elif key == 'k':  # Top left corner
            ball_target = [-2.99, 3, -14.5]
        ball_state = 'moving'
        _current_idle_func = update_ball
        glutIdleFunc(update_ball)
    # Player 2 GK controls (IJKL) — disabled in PvC (computer is GK vs player1 shooter)
    elif current_turn == 'player1_shoot' and key in ['i', 'j', 'k', 'l'] and goalkeeper_state == 'ready' and game_mode == 'pvp':
        if key == 'j':  # Left side
            goalkeeper_target = [-2.5, 0, -12]
        elif key == 'l':  # Right side
            goalkeeper_target = [2.5, 0, -12]
        elif key == 'i':  # Upper center
            goalkeeper_target = [0, 2.0, -12]
        elif key == 'k':  # Lower center
            goalkeeper_target = [0, 0, -12]
        goalkeeper_state = 'moving'
        _current_idle_func = update_goalkeeper
        glutIdleFunc(update_goalkeeper)

def update_ball():
    global ball_pos, ball_target, ball_state, player1_score, player2_score
    global current_turn, shots_taken, game_state, winner, is_paused
    global last_shot_by, last_shot_result
    global gk_dive_started, ball_move_start_ms
    global goalkeeper_pos, goalkeeper_target, goalkeeper_state, gk_reaction_delay_ms
    if is_paused:
        return
    # Use per-shot speed if set
    speed = current_shot_speed if ball_state == 'moving' else ball_speed
    epsilon = 1e-3
    for i in range(3):
        diff = ball_target[i] - ball_pos[i]
        if abs(diff) > speed:
            ball_pos[i] += speed if diff > 0 else -speed
        else:
            ball_pos[i] = ball_target[i]

    # No delayed reaction logic in the simple mode

    # Collision 
    distance = math.sqrt(sum((ball_pos[i] - goalkeeper_pos[i])**2 for i in range(3)))
    if distance < 0.8:
        ball_state = 'ready'
        last_shot_by = 'player1' if current_turn == 'player1_shoot' else 'player2'
        last_shot_result = 'M'
        # camera shake on save
        trigger_camera_shake()
        end_turn()
        glutIdleFunc(idle)
        # Clear current animation reference
        try:
            _ = _current_idle_func  # ensure name exists
        except NameError:
            pass
        return

    if all(abs(ball_pos[i] - ball_target[i]) < epsilon for i in range(3)):
        ball_state = 'ready'
        if current_turn == 'player1_shoot':
            player1_score += 1
            last_shot_by = 'player1'
        else:
            player2_score += 1
            last_shot_by = 'player2'
        last_shot_result = 'G'
        # record shot
        shot_history.append(('player1' if current_turn=='player1_shoot' else 'player2', ball_target[0], ball_target[1]))
        # camera shake on goal
        trigger_camera_shake()
        end_turn()
        glutIdleFunc(idle)
        try:
            _ = _current_idle_func
        except NameError:
            pass

    glutPostRedisplay()

def update_goalkeeper():
    global goalkeeper_pos, goalkeeper_target, goalkeeper_state, is_paused
    if is_paused:
        return
    speed = 0.2
    epsilon = 1e-3
    for i in range(3):
        diff = goalkeeper_target[i] - goalkeeper_pos[i]
        if abs(diff) > speed:
            goalkeeper_pos[i] += speed if diff > 0 else -speed
        else:
            goalkeeper_pos[i] = goalkeeper_target[i]

    if all(abs(goalkeeper_pos[i] - goalkeeper_target[i]) < epsilon for i in range(3)):
        goalkeeper_state = 'ready'
        glutIdleFunc(idle)

    glutPostRedisplay()

def launch_shot():
    pass

def update_accuracy():
    pass

def end_turn():
    global current_turn, shots_taken, game_state, winner, max_shots_per_player
    global player1_score, player2_score
    global player1_results, player2_results, last_shot_by, last_shot_result

    # Record last shot result into arrays for scoreboard
    if last_shot_by is not None and last_shot_result is not None:
        if last_shot_by == 'player1':
            player1_results.append(last_shot_result)
        else:
            player2_results.append(last_shot_result)
        last_shot_by = None
        last_shot_result = None

    # Schedule AI next action delay when switching to AI turn in PvC
    global ai_next_action_ms
    # Advance turn and count shots
    if current_turn == 'player1_shoot':
        shots_taken['player1'] += 1
        current_turn = 'player2_shoot'
    else:
        shots_taken['player2'] += 1
        current_turn = 'player1_shoot'
    if game_mode == 'pvc':
        tms = glutGet(GLUT_ELAPSED_TIME)
        if 'player2' in current_turn:
            ai_next_action_ms = tms + ai_turn_delay_ms
        else:
            ai_next_action_ms = None

    # --- Proper Penalty Tie Breaker Logic ---
    # 1. Initial 5 kicks per player
    if game_state == 'normal':
        # Early win check: if one player is ahead by more than the other can catch up
        remaining1 = max_shots_per_player - shots_taken['player1']
        remaining2 = max_shots_per_player - shots_taken['player2']
        if player1_score > player2_score + remaining2:
            winner = 'Player 1'
            game_state = 'ended'
        elif player2_score > player1_score + remaining1:
            winner = 'Player 2'
            game_state = 'ended'
        # After both have taken 5, check for winner or sudden death
        elif shots_taken['player1'] >= max_shots_per_player and shots_taken['player2'] >= max_shots_per_player:
            if player1_score > player2_score:
                winner = 'Player 1'
                game_state = 'ended'
            elif player2_score > player1_score:
                winner = 'Player 2'
                game_state = 'ended'
            else:
                game_state = 'sudden_death'
    # 2. Sudden death: both must take equal number of kicks, first to lead after a pair wins
    elif game_state == 'sudden_death':
        if shots_taken['player1'] > max_shots_per_player and shots_taken['player2'] > max_shots_per_player:
            if shots_taken['player1'] == shots_taken['player2']:
                if player1_score > player2_score:
                    winner = 'Player 1'
                    game_state = 'ended'
                elif player2_score > player1_score:
                    winner = 'Player 2'
                    game_state = 'ended'

    reset_ball()
    reset_goalkeeper()

def reset_ball():
    global ball_pos
    ball_pos = [0, 0.2, -5.3]

def reset_goalkeeper():
    global goalkeeper_pos, goalkeeper_target, goalkeeper_state
    goalkeeper_pos = [0, 0, -12]
    goalkeeper_target = [0, 0, -12]
    goalkeeper_state = 'ready'

def reset_game():
    global cam_angle, cam_height, radius
    global ball_state, ball_target, ball_pos
    global goalkeeper_pos, goalkeeper_target, goalkeeper_state
    global player1_score, player2_score, current_turn, shots_taken
    global max_shots_per_player, game_state, winner, is_paused
    global player1_results, player2_results, last_shot_by, last_shot_result
    global is_aiming, aim_target, accuracy_active, accuracy_phase, accuracy_dir
    global ball_move_start_ms, gk_dive_started
    global ui_state, game_mode, difficulty
    global ball_speed, gk_reaction_delay, gk_reach_x, gk_reach_y, gk_guess_bias
    global ai_gk_wait_until_ms, current_shot_speed

    cam_angle = 5
    cam_height = 5.0
    radius = 22.0

    ball_state = 'ready'
    ball_target = [0, 0, -15]
    ball_pos = [0, 0.2, -5.3]

    goalkeeper_pos = [0, 0, -12]
    goalkeeper_target = [0, 0, -12]
    goalkeeper_state = 'ready'

    player1_score = 0
    player2_score = 0
    current_turn = 'player1_shoot'
    shots_taken = {'player1': 0, 'player2': 0}
    max_shots_per_player = 5
    game_state = 'normal'
    winner = None
    is_paused = False

    player1_results = []
    player2_results = []
    last_shot_by = None
    last_shot_result = None

    is_aiming = False
    aim_target = [0.0, 0.5, -14.5]
    accuracy_active = False
    accuracy_phase = 0.0
    accuracy_dir = 1
    ball_move_start_ms = None
    gk_dive_started = False

    glutIdleFunc(idle)
    glutPostRedisplay()
    ai_gk_wait_until_ms = None
    current_shot_speed = ball_speed

def go_to_menu():
    global ui_state, winner, game_state
    ui_state = 'menu'
    winner = None
    game_state = 'normal'
    glutIdleFunc(idle)

def set_difficulty_params():
    global ball_speed, gk_reaction_delay, gk_reach_x, gk_reach_y, gk_guess_bias
    global shooter_err_x, shooter_err_y, ai_turn_delay_ms
    if difficulty == 'easy':
        ball_speed = 0.18
        gk_reaction_delay = 350
        gk_reach_x = 2.0
        gk_reach_y = 1.5
        gk_guess_bias = 0.5
        shooter_err_x = 0.6
        shooter_err_y = 0.6
        ai_turn_delay_ms = 900
    elif difficulty == 'hard':
        ball_speed = 0.26
        gk_reaction_delay = 150
        gk_reach_x = 3.0
        gk_reach_y = 2.2
        gk_guess_bias = 0.8
        shooter_err_x = 0.15
        shooter_err_y = 0.15
        ai_turn_delay_ms = 500
    else:  # medium
        ball_speed = 0.22
        gk_reaction_delay = 250
        gk_reach_x = 2.5
        gk_reach_y = 2.0
        gk_guess_bias = 0.65
        shooter_err_x = 0.35
        shooter_err_y = 0.35
        ai_turn_delay_ms = 700

def compute_shot_speed_variation():
    # Deterministic per-shot speed variance from time, narrow band per difficulty
    t = glutGet(GLUT_ELAPSED_TIME) / 1000.0
    base = ball_speed
    amp = 0.01 if difficulty == 'easy' else (0.015 if difficulty == 'medium' else 0.02)
    return max(0.12, min(0.35, base + amp * math.sin(t*1.1)))

def get_human_shot_preference(max_samples=6):
    # Analyze recent human (player1) shots to bias GK guess
    total = 0
    right = 0
    for by, tx, ty in reversed(shot_history):
        if by != 'player1':
            continue
        total += 1
        if tx > 0:
            right += 1
        if total >= max_samples:
            break
    if total == 0:
        return None, 0.0
    pref_right = (right >= (total - right))
    confidence = abs(right - (total - right)) / float(total)
    return pref_right, confidence

def specialKeyListener(key, x, y):
    global cam_angle, cam_height, radius
    if key == GLUT_KEY_LEFT:
        cam_angle -= 5
    elif key == GLUT_KEY_RIGHT:
        cam_angle += 5
    elif key == GLUT_KEY_UP:
        cam_height += 0.5
    elif key == GLUT_KEY_DOWN:
        cam_height -= 0.5
    elif key == GLUT_KEY_PAGE_UP:
        radius -= 1
        if radius < 5:
            radius = 5
    elif key == GLUT_KEY_PAGE_DOWN:
        radius += 1
        if radius > 50:
            radius = 50
    glutPostRedisplay()

def trigger_camera_shake():
    global shake_until_ms
    shake_until_ms = glutGet(GLUT_ELAPSED_TIME) + 250

def mouseListener(button, state, x, y):
    global ui_state, game_mode, difficulty, menu_focus
    if ui_state != 'menu':
        return
    # Convert GLUT window coords (top-left origin) to our ortho coords (bottom-left origin)
    ox, oy = x, 800 - y
    if button == GLUT_LEFT_BUTTON and state == GLUT_DOWN:
        layout = get_menu_layout()
        if point_in_rect(ox, oy, layout['btn_pvp']):
            game_mode = 'pvp'
            menu_focus = 0
            glutPostRedisplay()
            return
        if point_in_rect(ox, oy, layout['btn_pvc']):
            game_mode = 'pvc'
            menu_focus = 0
            glutPostRedisplay()
            return
        if point_in_rect(ox, oy, layout['btn_easy']) and game_mode == 'pvc':
            difficulty = 'easy'
            menu_focus = 1
            glutPostRedisplay()
            return
        if point_in_rect(ox, oy, layout['btn_medium']) and game_mode == 'pvc':
            difficulty = 'medium'
            menu_focus = 1
            glutPostRedisplay()
            return
        if point_in_rect(ox, oy, layout['btn_hard']) and game_mode == 'pvc':
            difficulty = 'hard'
            menu_focus = 1
            glutPostRedisplay()
            return
        if point_in_rect(ox, oy, layout['btn_start']):
            ui_state = 'playing'
            set_difficulty_params()
            reset_game()
            glutPostRedisplay()
            return

def setupCamera():
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60, 1.25, 1.0, 100.0)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    cam_x = radius * math.sin(math.radians(cam_angle))
    cam_z = radius * math.cos(math.radians(cam_angle)) - 7
    cam_y = cam_height + 6
    # apply camera shake if active
    if shake_until_ms is not None and glutGet(GLUT_ELAPSED_TIME) < shake_until_ms:
        jitter = 0.2
        t = glutGet(GLUT_ELAPSED_TIME) / 1000.0
        cam_x += jitter * math.sin(t*40.0)
        cam_y += jitter * math.cos(t*37.0)
    gluLookAt(cam_x, cam_y, cam_z, 0, 1, -10, 0, 1, 0)

def idle():
    # Unified idle: drive AI and step animations concurrently
    if ui_state == 'playing' and game_state != 'ended' and not is_paused:
        if game_mode == 'pvc':
            run_ai()
        if ball_state == 'moving':
            update_ball()
        if goalkeeper_state == 'moving':
            update_goalkeeper()
    glutPostRedisplay()

def run_ai():
    global ball_state, _current_idle_func, current_shot_speed
    global ai_gk_wait_until_ms, goalkeeper_state, ai_next_action_ms
    # AI acts only when it's the computer's turn in PvC
    # If shooter is computer
    if 'player2' in current_turn and game_mode == 'pvc':
        # assume player1 is human, player2 is computer
        if 'shoot' in current_turn and ball_state == 'ready':
            # enforce turn delay before AI acts
            now = glutGet(GLUT_ELAPSED_TIME)
            if ai_next_action_ms is not None and now < ai_next_action_ms:
                return
            # Choose side with bias; add placement error based on difficulty
            t = glutGet(GLUT_ELAPSED_TIME) / 1000.0
            # decide correct corner vs alternate
            prefer_right = math.sin(t*0.8) > (1.0 - gk_guess_bias)
            prefer_high = math.cos(t*0.6) > 0.0
            tx = (2.99 if prefer_right else -2.99)
            ty = (3.0 if prefer_high else 0.5)
            # derive deterministic noise
            nx = math.sin(t*1.7) * shooter_err_x
            ny = math.cos(t*1.3) * shooter_err_y
            tx = max(-2.99, min(2.99, tx + nx))
            ty = max(0.5, min(3.0, ty + ny))
            ball_target[:] = [tx, ty, -14.5]
            # Record history
            shot_history.append(('player2', tx, ty))
            # Launch shot
            ball_state = 'moving'
            # per-shot speed
            current_shot_speed = compute_shot_speed_variation()
            _current_idle_func = idle
            glutIdleFunc(idle)
            return
        # If GK is computer on player1 shoot, bias dive after small delay handled by user input path
    # If goalkeeper is computer during player1 shoot
    if current_turn == 'player1_shoot' and game_mode == 'pvc':
        t_ms = glutGet(GLUT_ELAPSED_TIME)
        global ai_gk_wait_until_ms
        if ai_gk_wait_until_ms is None:
            ai_gk_wait_until_ms = t_ms + gk_reaction_delay
        if t_ms >= ai_gk_wait_until_ms and goalkeeper_state == 'ready':
            t = t_ms / 1000.0
            # guess direction with bias + adapt to human preference
            prefer_right, conf = get_human_shot_preference()
            bias = gk_guess_bias + 0.15*conf if prefer_right else gk_guess_bias - 0.15*conf if prefer_right is not None else gk_guess_bias
            bias = max(0.4, min(0.9, bias))
            guess_right = math.sin(t*0.9) > (1.0 - bias)
            target_x = gk_reach_x if guess_right else -gk_reach_x
            target_y = gk_reach_y if math.cos(t*0.5) > 0.2 else 0.0
            goalkeeper_target[0] = target_x
            goalkeeper_target[1] = target_y
            goalkeeper_state = 'moving'
            _current_idle_func = idle
            glutIdleFunc(idle)
            ai_gk_wait_until_ms = None

def reshape(w, h):
    glViewport(0, 0, w, h)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60, float(w)/float(h), 1.0, 100.0)
    glMatrixMode(GL_MODELVIEW)

def draw_menu():
    # Overlay menu
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)

    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, 1000, 0, 800)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    # Dim background
    try:
        glColor4f(0.0, 0.0, 0.0, 0.4)
    except Exception:
        glColor3f(0.0, 0.0, 0.0)
    glBegin(GL_QUADS)
    glVertex2f(0, 0)
    glVertex2f(1000, 0)
    glVertex2f(1000, 800)
    glVertex2f(0, 800)
    glEnd()

    # Panel (larger and centered)
    panel_x1, panel_y1, panel_x2, panel_y2 = 180, 230, 820, 730
    panel_w = panel_x2 - panel_x1
    glColor3f(0.10, 0.12, 0.16)
    glBegin(GL_QUADS)
    glVertex2f(panel_x1, panel_y1)
    glVertex2f(panel_x2, panel_y1)
    glVertex2f(panel_x2, panel_y2)
    glVertex2f(panel_x1, panel_y2)
    glEnd()
    # Panel border
    glColor3f(0.25, 0.55, 0.95)
    glLineWidth(2)
    glBegin(GL_LINE_LOOP)
    glVertex2f(panel_x1, panel_y1)
    glVertex2f(panel_x2, panel_y1)
    glVertex2f(panel_x2, panel_y2)
    glVertex2f(panel_x1, panel_y2)
    glEnd()
    # Header bar
    glColor3f(0.20, 0.45, 0.85)
    glBegin(GL_QUADS)
    glVertex2f(panel_x1, panel_y2-40)
    glVertex2f(panel_x2, panel_y2-40)
    glVertex2f(panel_x2, panel_y2)
    glVertex2f(panel_x1, panel_y2)
    glEnd()
    glColor3f(1,1,1)
    # Center the title
    title = "Penalty Shootout"
    approx_w = len(title) * 9
    draw_text(int(panel_x1 + panel_w/2 - approx_w/2), panel_y2-25, title, GLUT_BITMAP_HELVETICA_18)

    # Helpers
    def draw_centered_text(cx, y, text, font=GLUT_BITMAP_HELVETICA_18):
        tw = len(text) * (9 if font == GLUT_BITMAP_HELVETICA_18 else 7)
        draw_text(int(cx - tw/2), y, text, font)
    def draw_button(x, y, w, h, label, active, focused, disabled=False):
        if disabled:
            glColor3f(0.25, 0.25, 0.28)
        elif active:
            glColor3f(0.18, 0.6, 0.25)
        else:
            glColor3f(0.16, 0.18, 0.22)
        glBegin(GL_QUADS)
        glVertex2f(x, y)
        glVertex2f(x+w, y)
        glVertex2f(x+w, y+h)
        glVertex2f(x, y+h)
        glEnd()
        # button border / focus
        if focused:
            glColor3f(0.9, 0.9, 0.2)
        else:
            glColor3f(0.35, 0.35, 0.42)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x, y)
        glVertex2f(x+w, y)
        glVertex2f(x+w, y+h)
        glVertex2f(x, y+h)
        glEnd()
        # text color: dim when disabled
        if disabled:
            glColor3f(0.75, 0.75, 0.78)
        else:
            glColor3f(1,1,1)
        # center text (approximate)
        lw = len(label) * 9
        tx = int(x + (w - lw)/2)
        # clamp within padding
        pad = 10
        if tx < x + pad:
            tx = x + pad
        if tx + lw > x + w - pad:
            tx = x + w - pad - lw
        ty = int(y + h/2 + 5)
        draw_text(tx, ty, label, GLUT_BITMAP_HELVETICA_18)

    # vertical layout metrics
    center_x = panel_x1 + panel_w//2
    row1_y = panel_y2 - 120
    row2_y = row1_y - 80
    row3_y = row2_y - 100

    # Mode row label centered above buttons
    row_y = row1_y
    btn_w, btn_h = 200, 48
    draw_centered_text(panel_x1 + panel_w/2, row_y + btn_h + 18, "Game Mode:")
    btn_gap = 30
    total_w = btn_w*2 + btn_gap
    x1 = panel_x1 + (panel_w - total_w)//2
    is_pvc = (game_mode == 'pvc')
    draw_button(x1, row_y, btn_w, btn_h, "PvP", not is_pvc, menu_focus == 0 and not is_pvc)
    draw_button(x1+btn_w+btn_gap, row_y, btn_w, btn_h, "PvC", is_pvc, menu_focus == 0 and is_pvc)

    # Difficulty row label centered above buttons
    row_y = row2_y
    diff_btn_w, diff_btn_h = 160, 48
    diff_gap = 20
    draw_centered_text(panel_x1 + panel_w/2, row_y + diff_btn_h + 18, "Difficulty:")
    opts = ['Easy','Medium','Hard']
    # Three buttons centered and within panel
    diff_total_w = diff_btn_w*3 + diff_gap*2
    x = panel_x1 + (panel_w - diff_total_w)//2
    for i, name in enumerate(opts):
        active = (difficulty.lower() == name.lower())
        disabled = (not is_pvc)
        focused = (menu_focus == 1 and active)
        draw_button(x, row_y, diff_btn_w, diff_btn_h, name, active and not disabled, focused and not disabled, disabled)
        x += diff_btn_w + diff_gap
    if not is_pvc:
        glColor3f(0.8, 0.8, 0.8)
        hint = "(PvP uses manual skill only)"
        draw_centered_text(panel_x1 + panel_w/2, row_y - 24, hint, GLUT_BITMAP_HELVETICA_12)

    # Start row
    row_y = row3_y
    start_w, start_h = 240, 54
    start_x = panel_x1 + (panel_w - start_w)//2
    draw_button(start_x, row_y, start_w, start_h, "Start", True, menu_focus == 2)
    glColor3f(0.85, 0.85, 0.9)
    footer = "Use W/S to move, A/D to change, Enter/Space to start"
    draw_centered_text(panel_x1 + panel_w/2, row_y - 60, footer, GLUT_BITMAP_HELVETICA_12)
    # Expose layout rectangles for mouse hit-testing
    store_menu_layout({
        'btn_pvp': (x1, row1_y, btn_w, btn_h),
        'btn_pvc': (x1+btn_w+btn_gap, row1_y, btn_w, btn_h),
        'btn_easy': (panel_x1 + (panel_w - diff_total_w)//2, row2_y, diff_btn_w, diff_btn_h),
        'btn_medium': (panel_x1 + (panel_w - diff_total_w)//2 + diff_btn_w + diff_gap, row2_y, diff_btn_w, diff_btn_h),
        'btn_hard': (panel_x1 + (panel_w - diff_total_w)//2 + (diff_btn_w + diff_gap)*2, row2_y, diff_btn_w, diff_btn_h),
        'btn_start': (start_x, row3_y, start_w, start_h),
    })

    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)

def draw_scoreboard():
    # Disable lighting and depth test for 2D overlay
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)

    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, 1000, 0, 800)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    # Scoreboard rectangle (taller to include kick dots)
    glColor3f(0.12, 0.12, 0.18)
    glBegin(GL_QUADS)
    glVertex2f(320, 700)
    glVertex2f(680, 700)
    glVertex2f(680, 795)
    glVertex2f(320, 795)
    glEnd()
    # Accent bar
    glColor3f(0.2, 0.5, 0.9)
    glBegin(GL_QUADS)
    glVertex2f(320, 790)
    glVertex2f(680, 790)
    glVertex2f(680, 795)
    glVertex2f(320, 795)
    glEnd()

    # Borders
    glColor3f(1, 1, 1)
    glLineWidth(2)
    glBegin(GL_LINE_LOOP)
    glVertex2f(320, 700)
    glVertex2f(680, 700)
    glVertex2f(680, 795)
    glVertex2f(320, 795)
    glEnd()

    # Labels and aggregate score
    glColor3f(0.9, 0.1, 0.1)
    draw_text(335, 772, f"PLAYER 1", GLUT_BITMAP_HELVETICA_12)
    glColor3f(1, 1, 1)
    draw_text(455, 772, f"{player1_score}", GLUT_BITMAP_HELVETICA_18)
    glColor3f(1, 1, 0.2)
    draw_text(500, 772, f"-", GLUT_BITMAP_HELVETICA_18)
    glColor3f(1, 1, 1)
    draw_text(535, 772, f"{player2_score}", GLUT_BITMAP_HELVETICA_18)
    glColor3f(0.1, 0.3, 0.9)
    draw_text(585, 772, f"PLAYER 2", GLUT_BITMAP_HELVETICA_12)

    # Mode/Difficulty indicator inside panel
    if ui_state == 'playing':
        glColor3f(0.85, 0.85, 0.85)
        draw_text(330, 710, f"Mode: {'PvC' if game_mode=='pvc' else 'PvP'}  |  Difficulty: {difficulty.capitalize()}", GLUT_BITMAP_HELVETICA_12)

    # Penalty dots visualization like real-life scoreboard
    def draw_penalty_row(x_start, y, results, max_initial=5):
        spacing = 30
        r = 6
        # Draw initial five
        for i in range(max_initial):
            if i < len(results):
                if results[i] == 'G':
                    glColor3f(0.1, 0.8, 0.2)  # green for goal
                else:
                    glColor3f(0.9, 0.1, 0.1)  # red for miss
            else:
                glColor3f(0.5, 0.5, 0.5)      # grey pending
            # draw filled circle using triangle fan
            glBegin(GL_TRIANGLE_FAN)
            glVertex2f(x_start + i*spacing, y)
            for a in range(0, 361, 30):
                glVertex2f(x_start + i*spacing + r*math.cos(math.radians(a)), y + r*math.sin(math.radians(a)))
            glEnd()
        # Draw sudden-death after five
        sd_x = x_start + max_initial*spacing + 15
        for i in range(max(0, len(results) - max_initial)):
            idx = max_initial + i
            if idx < len(results):
                if results[idx] == 'G':
                    glColor3f(0.1, 0.8, 0.2)
                else:
                    glColor3f(0.9, 0.1, 0.1)
            else:
                glColor3f(0.5, 0.5, 0.5)
            glBegin(GL_TRIANGLE_FAN)
            glVertex2f(sd_x + i*spacing, y)
            for a in range(0, 361, 30):
                glVertex2f(sd_x + i*spacing + r*math.cos(math.radians(a)), y + r*math.sin(math.radians(a)))
            glEnd()

    # Player 1 row (inside the panel)
    glColor3f(1,1,1)
    draw_penalty_row(350, 760, player1_results)
    # Player 2 row (inside the panel)
    draw_penalty_row(350, 735, player2_results)

    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

    # Re-enable lighting and depth test
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)

    # No aiming UI in simple mode

_cached_menu_layout = {}
def store_menu_layout(layout):
    global _cached_menu_layout
    _cached_menu_layout = layout

def get_menu_layout():
    return _cached_menu_layout

def point_in_rect(px, py, rect):
    x, y, w, h = rect
    return (px >= x and px <= x+w and py >= y and py <= y+h)

def showScreen():
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glLoadIdentity()
    glViewport(0, 0, 1000, 800)
    setupCamera()

    if ui_state == 'playing':
        draw_ground()
        draw_goal_post()
        draw_ball()
        draw_shooter()
        draw_goalkeeper()
        draw_scoreboard()

    # Display game info text at a fixed screen position
    if ui_state == 'playing':
        draw_text(10, 710, f"Turn: {'Shooter' if 'shoot' in current_turn else 'Goalkeeper'} | {current_turn}")
    elif ui_state == 'menu':
        draw_menu()
    if is_paused and not winner:
        draw_text(400, 400, "Paused")
    if winner:
        draw_text(400, 420, f"Game Over! Winner: {winner}")
        draw_text(360, 390, "Press M to return to Menu")

    glutSwapBuffers()

def init():
    glClearColor(0.0, 0.4, 0.8, 1.0)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LINE_SMOOTH)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    light_pos = [0.0, 10.0, 0.0, 1.0]
    glLightfv(GL_LIGHT0, GL_POSITION, light_pos)
    glEnable(GL_COLOR_MATERIAL)

def main():
    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(1000, 800)
    glutInitWindowPosition(0, 0)
    glutCreateWindow(b"Penalty Kick Game")
    init()
    glutDisplayFunc(showScreen)
    glutReshapeFunc(reshape)
    glutKeyboardFunc(keyboardListener)
    glutSpecialFunc(specialKeyListener)
    glutMouseFunc(mouseListener)
    glutIdleFunc(idle)
    glutMainLoop()

if __name__ == "__main__":
    main()

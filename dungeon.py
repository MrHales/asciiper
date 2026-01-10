import curses
import time
import random
import pickle
import os
import re

# Constants
TILES_HARD_ROCK = '^' # Indestructible
TILES_SOFT_ROCK = chr(176) # '░' Diggable (Deep rock) - Texture Change (Light Shade)
TILES_DIRT_WALL = chr(177) # '▒' Render-only (Exposed Soft Rock) - Medium Shade to differentiate? Or user said "Keep characters"... let's leave it as '░' for now if user explicitly asked for 176 on deep rock.
# Actually user said "Keep the characters for exposed rock". Exposed rock was '░'. Deep rock was '"'.
# Now Deep Rock is 176 ('░'). So they are the same. I'll stick to 176 for Deep and '░' for Dirt.
TILES_DIRT_WALL = '░'
TILES_REINFORCED = '█' # Reinforced Wall
TILES_FLOOR = '.'     # Walkable
TILES_HEART = '♥'
TILES_PORTAL = 'O'
TILES_IMP = 'i'
TILES_GOLD = 'o'      # Diggable Gold
TILES_TREASURY = '$'  # Treasury Floor

COLOR_ROCK = 1
COLOR_FLOOR = 2
COLOR_HEART = 3
COLOR_PORTAL = 4
COLOR_IMP = 5
COLOR_SELECT = 6
COLOR_GOLD = 7
COLOR_REINFORCED = 8
COLOR_TREASURY = 9
COLOR_MENU = 10 # New High Contrast Menu Color

KEY_QUIT = ord('q')

class Tile:
    def __init__(self, char, x, y):

        self.char = char
        self.x = x
        self.y = y
        self.tagged = False
        self.is_solid = char in [TILES_HARD_ROCK, TILES_SOFT_ROCK, TILES_REINFORCED, TILES_GOLD]
        self.gold_value = 500 if char == TILES_GOLD else 0
        self.gold_stored = 0 # For Treasury

class Map:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.tiles = []
        self.heart_pos = (0, 0)
        self.portal_pos = (0, 0)
        self.generate()

    def generate(self):
        # 1. Fill with Soft Rock
        self.tiles = [[Tile(TILES_SOFT_ROCK, x, y) for x in range(self.width)] for y in range(self.height)]

        # 2. Border of Hard Rock (Jagged)
        for y in range(self.height):
            for x in range(self.width):
                # Distance from edge
                dist_x = min(x, self.width - 1 - x)
                dist_y = min(y, self.height - 1 - y)
                dist = min(dist_x, dist_y)
                
                # Randomize thickness 1-4
                if dist < random.randint(1, 4):
                     self.tiles[y][x].char = TILES_HARD_ROCK
                     self.tiles[y][x].is_solid = True
        
        # 3. Place Heart (Center)
        cx, cy = self.width // 2, self.height // 2
        self.tiles[cy][cx].char = TILES_HEART
        self.tiles[cy][cx].is_solid = False # Heart is walkable? Or obstacle? Let's say obstacle for now, or walkable base
        self.heart_pos = (cx, cy)

        # Clear area around heart
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                # if dx == 0 and dy == 0: continue # Heart itself is fine? Heart is at center.
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    # Keep Heart tile
                    if nx == cx and ny == cy: continue
                    self.tiles[ny][nx].char = TILES_FLOOR
                    self.tiles[ny][nx].is_solid = False

        # 4. Place Portal (Random nearby)
        while True:
            # Random direction and distance
            angle = random.uniform(0, 6.28)
            dist = random.randint(5, 10) # 5 to 10 tiles away
            
            px = int(cx + dist * 1.5 * random.uniform(0.8, 1.2)) # simple offset
            py = int(cy + dist * 0.8 * random.uniform(0.8, 1.2)) # Aspect ratio ish?
            
            # Simplified: just random circle
            import math
            px = int(cx + math.cos(angle) * dist)
            py = int(cy + math.sin(angle) * dist)

            if 2 <= px < self.width - 2 and 2 <= py < self.height - 2:
                self.tiles[py][px].char = TILES_PORTAL
                self.portal_pos = (px, py)
                break
        
        # 5. Generate Gold Veins
        num_veins = 20
        for _ in range(num_veins):
             vx = random.randint(2, self.width - 3)
             vy = random.randint(2, self.height - 3)
             length = random.randint(4, 10)
             for _ in range(length):
                 if 0 <= vx < self.width and 0 <= vy < self.height:
                     t = self.tiles[vy][vx]
                     if t.char == TILES_SOFT_ROCK: # Only replace soft rock
                         t.char = TILES_GOLD
                         t.is_solid = True
                         t.gold_value = 500
                     # Random walk
                     vx += random.randint(-1, 1)
                     vy += random.randint(-1, 1)

    def get_tile(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[y][x]
        return None

    def get_path_step(self, start_x, start_y, target_x, target_y):
        # BFS to find next step towards target
        queue = [(start_x, start_y, [])]
        visited = set([(start_x, start_y)])
        
        # Limit search depth to avoid lag if unreachable
        steps = 0
        limit = 500
        
        while queue and steps < limit:
            curr_x, curr_y, path = queue.pop(0)
            steps += 1
            
            if curr_x == target_x and curr_y == target_y:
                if path: return path[0]
                return None
            
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = curr_x + dx, curr_y + dy
                
                # Check bounds and walkability
                # We can walk on Floor or the Target itself (even if wall, we want to go adjacent)
                # Actually we need to walk on Floor. Memory of target is tricky.
                # Basic BFS for movement: Can only enter non-solid tiles.
                
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    tile = self.tiles[ny][nx]
                    if not tile.is_solid or (nx == target_x and ny == target_y):
                        if (nx, ny) not in visited:
                            visited.add((nx, ny))
                            new_path = list(path)
                            new_path.append((nx, ny))
                            queue.append((nx, ny, new_path))
        return None

    def find_nearest_tagged(self, start_x, start_y):
        # BFS to find nearest tagged tile or Gold
        queue = [(start_x, start_y)]
        visited = set([(start_x, start_y)])
        
        while queue:
            curr_x, curr_y = queue.pop(0)
            
            # Check neighbors (8-way)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    nx, ny = curr_x + dx, curr_y + dy
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                         # ... check logic
                         pass # handled in loop below
            
            # Actual Loop
            DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]
            for dx, dy in DIRECTIONS:
                nx, ny = curr_x + dx, curr_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    tile = self.tiles[ny][nx]
                    if tile.tagged and tile.is_solid:
                        return tile
            
                    if not tile.is_solid and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
        return None

    def find_nearest_treasury_space(self, start_x, start_y):
        queue = [(start_x, start_y)]
        visited = set([(start_x, start_y)])
        while queue:
            curr_x, curr_y = queue.pop(0)
            # Check if this tile is treasury with space
            tile = self.tiles[curr_y][curr_x]
            if tile.char == TILES_TREASURY and tile.gold_stored < 500:
                return tile
            
            # BFS neighbors (walkable)
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = curr_x + dx, curr_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    nt = self.tiles[ny][nx]
                    if not nt.is_solid and (nx, ny) not in visited:
                         visited.add((nx, ny))
                         queue.append((nx, ny))
        return None

    def find_nearest_tagged(self, start_x, start_y, exclude=set()):
        # BFS to find nearest tagged tile or Gold
        queue = [(start_x, start_y)]
        visited = set([(start_x, start_y)])
        
        while queue:
            curr_x, curr_y = queue.pop(0)
            
            # Check neighbors (8-way)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    nx, ny = curr_x + dx, curr_y + dy
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                         # ... check logic
                         pass # handled in loop below
            
            # Actual Loop
            DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]
            for dx, dy in DIRECTIONS:
                nx, ny = curr_x + dx, curr_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    tile = self.tiles[ny][nx]
                    if tile.tagged and tile.is_solid:
                        if (nx, ny) not in exclude:
                             # Check if digging reinforced?
                             return tile
            
            # Continue
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = curr_x + dx, curr_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    tile = self.tiles[ny][nx]
                    if not tile.is_solid and (nx, ny) not in visited:
                        # Optimization: Prefer path closer to heart?
                        visited.add((nx, ny))
                        queue.append((nx, ny))
        return None
    
    def any_tagged_gold(self):
        # Quick check if any gold is tagged
        # Could optimize by tracking count
        for row in self.tiles:
            for t in row:
                if t.tagged and t.char == TILES_GOLD:
                    return True
        return False

    def find_nearest_reinforceable(self, start_x, start_y):
        # BFS to find nearest Dirt Wall (Soft Rock adj to floor) NOT TAGGED
        queue = [(start_x, start_y)]
        visited = set([(start_x, start_y)])
        
        while queue:
            curr_x, curr_y = queue.pop(0)
            
            # Check neighbors (8-way)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    nx, ny = curr_x + dx, curr_y + dy
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                         # ... check logic
                         pass # handled in loop below
            
            # Actual Loop
            DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]
            for dx, dy in DIRECTIONS:
                nx, ny = curr_x + dx, curr_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    tile = self.tiles[ny][nx]
                    # Must be Soft Rock (Dirt Wall), Not Tagged
                    if tile.char == TILES_SOFT_ROCK and not tile.tagged:
                         return tile
            
            # Continue
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = curr_x + dx, curr_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    tile = self.tiles[ny][nx]
                    if not tile.is_solid and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
        return None

class EntityManager:
    def __init__(self, game_map):
        self.map = game_map
        self.imps = []
        self.total_gold = 0 # Legacy total?
        self.heart_gold = 0
        # Spawn initial imps
        hx, hy = self.map.heart_pos
        for _ in range(4): # Spawn 4
            self.spawn_imp(hx, hy)

    def spawn_imp(self, x, y):
        # Added tick_offset to randomize updates or idle timing
        self.imps.append({
            'x': x, 'y': y, 
            'state': 'IDLE', 
            'target': None, 
            'idle_timer': 0,
            'gold': 0,
            'work_timer': 0
        })

    def update(self):
        # Logic update for imps (1 tick per sec)
        for imp in self.imps:
            ix, iy = imp['x'], imp['y']
            
            # STATE TRANSITION LOGIC
            
            # 0. If Returning Gold (Optimized state check)
            # Legacy block removed. Logic is handled in Step 3.
            pass


            # 1. If currently working (Reinforcing or Mining)
            # Validation of current target
            target_valid = False
            if imp['target']:
                 tx, ty = imp['target']
                 t_tile = self.map.get_tile(tx, ty)
                 # If Digging/Mining: Tagged?
                 if imp['state'] == 'DIGGING':
                     if t_tile and t_tile.tagged: target_valid = True
                 # If Reinforcing: Soft Rock?
                 elif imp['state'] == 'REINFORCING':
                     if t_tile and t_tile.char == TILES_SOFT_ROCK and not t_tile.tagged: target_valid = True
            
            if not target_valid and imp['state'] not in ['RETURNING_GOLD', 'IDLE']:
                imp['target'] = None
                imp['state'] = 'IDLE'
                imp['work_timer'] = 0
            
            # 2. Look for work if Idle
            if imp['state'] == 'IDLE':
                # Check Priorities
                
                # Check 1: Force Return if Full
                if imp['gold'] >= 300:
                    imp['state'] = 'RETURNING_GOLD'
                    continue
                
                # Check 2: Return if carrying gold and no gold to mine
                if imp['gold'] > 0:
                     if not self.map.any_tagged_gold():
                         imp['state'] = 'RETURNING_GOLD'
                         continue
                
                # Priority 1: Digging/Mining (Tagged)
                # Divide and Conquer: Filter targets taken by other imps
                taken_targets = set()
                for other in self.imps:
                    if other != imp and other['target']:
                        taken_targets.add(other['target'])
                
                target_tile = self.map.find_nearest_tagged(ix, iy, exclude=taken_targets)
                if target_tile:
                    imp['target'] = (target_tile.x, target_tile.y)
                    imp['state'] = 'MOVING_DIG'
                else:
                    # Priority 2: Reinforcing (Unvisited Dirt Walls)
                    target_tile = self.map.find_nearest_reinforceable(ix, iy) # Reinforce doesn't strict need divide
                    if target_tile:
                        imp['target'] = (target_tile.x, target_tile.y)
                        imp['state'] = 'MOVING_REINFORCE'
            
            # 3. Act based on State
            if imp['state'] == 'RETURNING_GOLD':
                # Logic: Deposit at Heart (limit 5000) or Treasury (500 per tile)
                # First find target if none
                if not imp['target']:
                     hx, hy = self.map.heart_pos
                     
                     target_found = False
                     
                     # Check Heart First (if not full)
                     if self.heart_gold < 5000:
                         imp['target'] = (hx, hy)
                         target_found = True
                     
                     # If Heart Full, check Treasury
                     if not target_found:
                         t_tile = self.map.find_nearest_treasury_space(ix, iy)
                         if t_tile:
                             imp['target'] = (t_tile.x, t_tile.y)
                             target_found = True
                     
                     # If both full?
                     if not target_found:
                         # Just idle/wander? Or go to heart and wait?
                         # Let's just wander.
                         imp['state'] = 'IDLE' 
                         imp['target'] = None
                         continue # Re-eval next tick

                
                tx, ty = imp['target']
                
                # Move
                if (ix, iy) == (tx, ty):
                    # Deposit
                    tile = self.map.get_tile(ix, iy)
                    amount = imp['gold']
                    deposit = 0
                    
                    if tile.char == TILES_HEART:
                        space = 5000 - self.heart_gold
                        deposit = min(amount, space)
                        self.heart_gold += deposit
                    elif tile.char == TILES_TREASURY:
                        # Treasury tile hold 500
                        space = 500 - tile.gold_stored
                        deposit = min(amount, space)
                        tile.gold_stored += deposit
                    
                    if deposit > 0:
                        self.total_gold += deposit
                        imp['gold'] -= deposit
                        
                    if imp['gold'] <= 0:
                        imp['state'] = 'IDLE' # Done
                        imp['target'] = None
                    else:
                        imp['target'] = None # Re-eval target next tick because maybe this tile is now full
                else:
                    next_pos = self.map.get_path_step(ix, iy, tx, ty)
                    if next_pos:
                        imp['x'], imp['y'] = next_pos
            
            # 3. Act based on State
            if imp['state'] == 'MOVING_DIG' or imp['state'] == 'MOVING_REINFORCE':
                if not imp['target']: 
                    imp['state'] = 'IDLE' 
                    continue
                tx, ty = imp['target']
                t_tile = self.map.get_tile(tx, ty)
                
                # Check adjacency
                dist = abs(ix - tx) + abs(iy - ty)
                if dist == 1:
                    # Start Working
                    if imp['state'] == 'MOVING_DIG': imp['state'] = 'DIGGING'
                    else: imp['state'] = 'REINFORCING'
                    imp['work_timer'] = 0
                else:
                    path = self.map.get_path_step(ix, iy, tx, ty)
                    if path: 
                        imp['x'], imp['y'] = path
                        
            elif imp['state'] == 'DIGGING':
                tx, ty = imp['target']
                t_tile = self.map.get_tile(tx, ty)
                
                # Logic:
                # If Gold: Mine (+100g). If deplete (500g total), turn to floor.
                # If Rock: Dig (1 tick) -> Floor.
                
                if t_tile.char == TILES_GOLD:
                    # Mining Gold
                    mine_amt = 100
                    took = min(mine_amt, t_tile.gold_value)
                    t_tile.gold_value -= took
                    imp['gold'] += took
                    
                    # Full?
                    if imp['gold'] >= 300:
                        imp['state'] = 'RETURNING_GOLD'
                        imp['target'] = None
                        # Note: Tile remains tagged if valid gold left?
                        # If we leave, tile is still tagged. Another imp can come.
                    
                    if t_tile.gold_value <= 0:
                        t_tile.char = TILES_FLOOR
                        t_tile.is_solid = False
                        t_tile.tagged = False
                        imp['target'] = None
                        imp['state'] = 'IDLE' # Job Done
                elif t_tile.char == TILES_REINFORCED:
                    # Reinforced digging takes longer (2 ticks)
                    imp['work_timer'] += 1
                    if imp['work_timer'] >= 2:
                        t_tile.char = TILES_FLOOR
                        t_tile.is_solid = False
                        t_tile.tagged = False
                        imp['target'] = None
                        imp['state'] = 'IDLE'
                        imp['work_timer'] = 0
                else:
                    # Normal Dig
                    t_tile.char = TILES_FLOOR
                    t_tile.is_solid = False
                    t_tile.tagged = False
                    imp['target'] = None
                    imp['state'] = 'IDLE'

            elif imp['state'] == 'REINFORCING':
                tx, ty = imp['target']
                t_tile = self.map.get_tile(tx, ty)
                
                imp['work_timer'] += 1
                if imp['work_timer'] >= 3:
                    t_tile.char = TILES_REINFORCED
                    t_tile.is_solid = True # Should be solid
                    imp['target'] = None
                    imp['state'] = 'IDLE'
            
            elif imp['state'] == 'IDLE':
                # Random wander
                imp['idle_timer'] += 1
                if imp['idle_timer'] >= 2:
                    imp['idle_timer'] = 0
                    neighbors = []
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        nx, ny = ix + dx, iy + dy
                        t = self.map.get_tile(nx, ny)
                        if t and not t.is_solid:
                            neighbors.append((nx, ny))
                    if neighbors:
                        nx, ny = random.choice(neighbors)
                        imp['x'] = nx
                        imp['y'] = ny

class Renderer:
    def __init__(self, stdscr, game_map):
        self.stdscr = stdscr
        self.map = game_map
        self.cam_x = 0
        self.cam_y = 0
        self.setup_colors()

    def setup_colors(self):
        curses.start_color()
        curses.init_pair(COLOR_ROCK, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(COLOR_FLOOR, curses.COLOR_BLACK, curses.COLOR_WHITE) # Inverted for floor look? Or just dim.
        # Let's try standard colors first
        curses.init_pair(COLOR_FLOOR, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(COLOR_HEART, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(COLOR_PORTAL, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(COLOR_IMP, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(COLOR_SELECT, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(COLOR_GOLD, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(COLOR_REINFORCED, curses.COLOR_WHITE, curses.COLOR_BLACK) 
        curses.init_pair(COLOR_TREASURY, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(COLOR_MENU, curses.COLOR_BLACK, curses.COLOR_WHITE) # Inverted for menu

    def draw(self, paused, imps, selected_room, drag_start=None, drag_end=None, total_gold=0):
        # Removed self.stdscr.clear() to reduce flicker. 
        # We overwrite the entire viewport anyway.
        h, w = self.stdscr.getmaxyx()
        
        # Determine viewport
        # Camera is top-left corner
        
        # Helper for drag box
        drag_rect = None
        if drag_start and drag_end: # Active drag updates
             x1, y1 = drag_start
             x2, y2 = drag_end
             min_x, max_x = min(x1, x2), max(x1, x2)
             min_y, max_y = min(y1, y2), max(y1, y2)
             drag_rect = (min_x, max_x, min_y, max_y)

        for y in range(h - 1): # Leave bottom line for status
            map_y = self.cam_y + y
            for x in range(w):
                map_x = self.cam_x + x
                
                # Check bounds
                if 0 <= map_x < self.map.width and 0 <= map_y < self.map.height:
                   tile = self.map.tiles[map_y][map_x]
                   char = tile.char
                   pair = COLOR_ROCK
                   
                   # Dynamic Wall Rendering (Dirt Walls)
                   if char == TILES_SOFT_ROCK or char == TILES_GOLD:
                       # Check neighbors for floor
                       has_floor_neighbor = False
                       for dy in [-1, 0, 1]:
                           for dx in [-1, 0, 1]:
                               if dx==0 and dy==0: continue
                               nx, ny = map_x + dx, map_y + dy
                               if 0 <= nx < self.map.width and 0 <= ny < self.map.height:
                                   nt = self.map.tiles[ny][nx]
                                   if not nt.is_solid: # Floor or Heart etc
                                       has_floor_neighbor = True
                                       break
                           if has_floor_neighbor: break
                       
                       if has_floor_neighbor:
                           if char == TILES_SOFT_ROCK:
                               char = TILES_DIRT_WALL
                               #pair = COLOR_ROCK
                           # Gold stays gold char but maybe different bg? 
                           # User said "symbol for a gold block a yellow o". 
                           pass 
                       else:
                           if char == TILES_SOFT_ROCK:
                               char = TILES_SOFT_ROCK # Keep the texture char '"'
                               # char = ' ' # Legacy: Deep rock invisible/space
                   
                   if char == TILES_FLOOR: pair = COLOR_FLOOR
                   elif char == TILES_HEART: pair = COLOR_HEART
                   elif char == TILES_PORTAL: pair = COLOR_PORTAL
                   elif char == TILES_GOLD: pair = COLOR_GOLD
                   elif char == TILES_REINFORCED: pair = COLOR_REINFORCED
                   elif char == TILES_TREASURY: pair = COLOR_TREASURY
                   
                   attr = curses.color_pair(pair)
                   if tile.tagged:
                       attr = curses.color_pair(COLOR_SELECT)
                   
                   # Treasury logic
                   if char == TILES_TREASURY and tile.gold_stored > 0:
                       # Inverted visual for occupied treasury?
                       # "Make the symbol for an occupied space in the treasury an inverted yellow $."
                       attr = curses.color_pair(COLOR_TREASURY) | curses.A_REVERSE
                   
                   # Drag Selection Highlight
                   if drag_rect:
                       min_x, max_x, min_y, max_y = drag_rect
                       if min_x <= map_x <= max_x and min_y <= map_y <= max_y:
                            # Highlight logic for drag
                            # "highlight all blocks to be changed rather than just the origin block"
                            # We just highlight everything in the rect
                            attr = curses.color_pair(COLOR_SELECT) | curses.A_REVERSE

                   try:
                       self.stdscr.addch(y, x, char, attr)
                   except curses.error:
                       pass # Bottom right corner issue
                else:
                   try:
                       self.stdscr.addch(y, x, ' ')
                   except curses.error:
                       pass
        
        # Draw Imps
        for imp in imps:
            scr_x = imp['x'] - self.cam_x
            scr_y = imp['y'] - self.cam_y
            if 0 <= scr_x < w and 0 <= scr_y < h - 1:
                # If carrying gold, maybe different color?
                attr = curses.color_pair(COLOR_IMP) | curses.A_BOLD
                if imp['gold'] > 0:
                     attr = curses.color_pair(COLOR_GOLD) | curses.A_BOLD
                try:
                    self.stdscr.addch(scr_y, scr_x, TILES_IMP, attr)
                except curses.error: pass

        # Draw UI
        status = f"Pos: {self.cam_x},{self.cam_y} | Room: {selected_room} | Gold: {total_gold} | Paused: {str(paused)}"
        # Pads with spaces to clear line
        status = status.ljust(w-1) 
        
        try:
            self.stdscr.addstr(h-1, 0, status[:w-1])
        except curses.error: pass

        # Draw Pause Border
        if paused:
            self.stdscr.border()

        if paused:
            self.stdscr.border()
        
        # NOTE: refresh() removed from here to allow overlay drawing before flip


class SaveManager:
    @staticmethod
    def get_save_dir():
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        return save_dir

    @staticmethod
    def sanitize_name(name):
        # Lowercase, replace spaces with _, remove special chars
        name = name.lower().strip()
        name = name.replace(' ', '_')
        name = re.sub(r'[^a-z0-9_]', '', name)
        return name

    @staticmethod
    def save_game(game, name):
        filename = SaveManager.sanitize_name(name) + '.save'
        path = os.path.join(SaveManager.get_save_dir(), filename)
        
        # Serialize state
        data = {
            'map': game.map,
            'entities': game.entities,
            'cam_x': game.renderer.cam_x,
            'cam_y': game.renderer.cam_y,
            'paused': game.paused,
            'selected_room': game.selected_room
        }
        
        with open(path, 'wb') as f:
            pickle.dump(data, f)
            
    @staticmethod
    def load_game(game, filename):
        path = os.path.join(SaveManager.get_save_dir(), filename)
        if not os.path.exists(path): return False
        
        with open(path, 'rb') as f:
            data = pickle.load(f)
            
        game.map = data['map']
        game.entities = data['entities']
        game.renderer.map = game.map # Update renderer ref
        # game.entities.map = game.map # Already linked? Pickling preserves obj graph
        game.renderer.cam_x = data.get('cam_x', 0)
        game.renderer.cam_y = data.get('cam_y', 0)
        game.paused = True # Load paused
        game.selected_room = data.get('selected_room', 'None')
        return True
    
    @staticmethod
    def list_saves():
        d = SaveManager.get_save_dir()
        files = [f for f in os.listdir(d) if f.endswith('.save')]
        return files

class Menu:
    def __init__(self, stdscr, game):
        self.stdscr = stdscr
        self.game = game
        self.active = False
        self.state = 'MAIN' # MAIN, SAVE, LOAD, CONFIRM_QUIT
        self.options = ['Resume', 'Save', 'Load', 'Quit']
        self.selected = 0
        self.input_text = ""
        self.load_files = []
        self.load_index = 0
    
    def draw(self):
        h, w = self.stdscr.getmaxyx()
        
        # Draw Box
        box_w = 40
        box_h = 14
        start_y = h // 2 - box_h // 2
        start_x = w // 2 - box_w // 2
        
        # Menu Attribute
        menu_attr = curses.color_pair(COLOR_MENU)
        
        # Clear box area with White Background
        for y in range(box_h):
            self.stdscr.addstr(start_y + y, start_x, " " * box_w, menu_attr)
        
        # Draw explicit box border
        for x in range(box_w):
             self.stdscr.addch(start_y, start_x + x, '-', menu_attr)
             self.stdscr.addch(start_y + box_h - 1, start_x + x, '-', menu_attr)
        for y in range(box_h):
             self.stdscr.addch(start_y + y, start_x, '|', menu_attr)
             self.stdscr.addch(start_y + y, start_x + box_w - 1, '|', menu_attr)
             
        title = f" MENU: {self.state} "
        self.stdscr.addstr(start_y, start_x + 2, title, menu_attr)

        if self.state == 'MAIN':
            for i, opt in enumerate(self.options):
                prefix = "> " if i == self.selected else "  "
                # If selected, maybe invert back to Black on White? Or use Standard?
                # Actually, standard is White on Black.
                # If selected: Standard (effectively inverted relative to menu).
                # If not selected: Menu Attr (Black on White).
                
                attr = curses.A_NORMAL if i == self.selected else menu_attr
                self.stdscr.addstr(start_y + 2 + i * 2, start_x + 4, prefix + opt, attr)
                
        elif self.state == 'SAVE':
            self.stdscr.addstr(start_y + 2, start_x + 2, "Enter Name:", menu_attr)
            self.stdscr.addstr(start_y + 4, start_x + 2, self.input_text + "_", menu_attr)
            self.stdscr.addstr(start_y + 10, start_x + 2, "Press Enter to Save", menu_attr)
            self.stdscr.addstr(start_y + 11, start_x + 2, "Esc to Cancel", menu_attr)
            
        elif self.state == 'LOAD':
            if not self.load_files:
                self.stdscr.addstr(start_y + 2, start_x + 2, "No Saves Found", menu_attr)
            else:
                for i in range(min(5, len(self.load_files))):
                    idx = self.load_index + i 
                    if idx < len(self.load_files):
                         prefix = "> " if idx == self.selected else "  "
                         attr = curses.A_NORMAL if idx == self.selected else menu_attr
                         self.stdscr.addstr(start_y + 2 + i, start_x + 2, prefix + self.load_files[idx], attr)
        
        elif self.state == 'CONFIRM_QUIT':
             self.stdscr.addstr(start_y + 2, start_x + 2, "Are you sure?", menu_attr)
             opts = ["Yes", "Cancel"]
             for i, opt in enumerate(opts):
                 prefix = "> " if i == self.selected else "  "
                 attr = curses.A_NORMAL if i == self.selected else menu_attr
                 self.stdscr.addstr(start_y + 5 + i, start_x + 4, prefix + opt, attr)

    def input(self, key):
        if key == 27: # Esc
            if self.state == 'MAIN':
                self.active = False
            else:
                self.state = 'MAIN'
            return

        if self.state == 'MAIN':
            if key == curses.KEY_UP:
                self.selected = max(0, self.selected - 1)
            elif key == curses.KEY_DOWN:
                self.selected = min(len(self.options) - 1, self.selected + 1)
            elif key == 10: # Enter
                opt = self.options[self.selected]
                if opt == 'Resume': self.active = False
                elif opt == 'Save': 
                    self.state = 'SAVE'
                    self.input_text = ""
                elif opt == 'Load': 
                    self.state = 'LOAD'
                    self.load_files = SaveManager.list_saves()
                    self.selected = 0
                elif opt == 'Quit': 
                    self.state = 'CONFIRM_QUIT'
                    self.selected = 0 # Default Yes (Index 0)
                    

        elif self.state == 'SAVE':
            if key == 10: # Enter
                if self.input_text:
                    SaveManager.save_game(self.game, self.input_text)
                    self.active = False # Resume after save
                    self.state = 'MAIN'
            elif key == curses.KEY_BACKSPACE or key == 127:
                self.input_text = self.input_text[:-1]
            elif 32 <= key <= 126:
                if len(self.input_text) < 20:
                    self.input_text += chr(key)
                    
        elif self.state == 'LOAD':
            if not self.load_files: return
            if key == curses.KEY_UP:
                self.selected = max(0, self.selected - 1)
            elif key == curses.KEY_DOWN:
                self.selected = min(len(self.load_files) - 1, self.selected + 1)
            elif key == 10:
                filename = self.load_files[self.selected]
                if SaveManager.load_game(self.game, filename):
                    self.active = False
                    self.state = 'MAIN'
                    
        elif self.state == 'CONFIRM_QUIT':
             if key == curses.KEY_UP or key == curses.KEY_DOWN:
                 self.selected = 1 - self.selected
             elif key == 10:
                 if self.selected == 0: # Yes
                     self.game.running = False
                 else:
                     self.state = 'MAIN'

class Game:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.running = True
        self.paused = False
        self.selected_room = "None"
        
        # State for Drag
        self.drag_start = None
        self.drag_end = None
        
        # Setup Curses
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)
        # Setup Mouse Mask
        # We need REPORT_MOUSE_POSITION for drag highlights
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        
        self.map = Map(80, 25) # Standard terminal size
        self.entities = EntityManager(self.map)
        self.renderer = Renderer(stdscr, self.map)
        
        # Center camera roughly
        self.renderer.cam_x = max(0, self.map.width // 2 - 40)
        self.renderer.cam_y = max(0, self.map.height // 2 - 15)
        
        self.menu = Menu(stdscr, self)

    def handle_drag_action(self, x1, y1, x2, y2):
        min_x, max_x = min(x1, x2), max(x1, x2)
        min_y, max_y = min(y1, y2), max(y1, y2)
        
        # Determine Drag Mode based on Start Tile
        drag_mode_tag = True
        start_tile = self.map.get_tile(x1, y1)
        if start_tile:
            if start_tile.tagged:
                drag_mode_tag = False # We are un-tagging
            else:
                drag_mode_tag = True # We are tagging
        
        # Apply Logic to Rect
        for ry in range(min_y, max_y + 1):
            for rx in range(min_x, max_x + 1):
                tile = self.map.get_tile(rx, ry)
                if tile:
                    # Tagging Logic (Soft Rock, Gold, Reinforced)
                    if tile.char in [TILES_SOFT_ROCK, TILES_GOLD, TILES_REINFORCED]:
                        tile.tagged = drag_mode_tag
                        
                    elif tile.char == TILES_FLOOR or tile.char in ['P', 'L', TILES_TREASURY]:
                        # Room assignments should overwrite one another
                        char_to_apply = None
                        if self.selected_room == "Corridor":
                            char_to_apply = TILES_FLOOR
                        elif self.selected_room == "Prison":
                            char_to_apply = 'P'
                        elif self.selected_room == "Lair":
                            char_to_apply = 'L'
                        elif self.selected_room == "Treasury":
                            char_to_apply = TILES_TREASURY
                            
                        if char_to_apply:
                            tile.char = char_to_apply
                            if char_to_apply == TILES_TREASURY:
                                tile.gold_stored = 0

    def input(self):
        # Process all pending input
        while True:
            try:
                key = self.stdscr.getch()
            except:
                break

            if key == curses.ERR:
                break
                
            # Menu Handling
            if self.menu.active:
                self.menu.input(key)
                continue # Skip game input if menu active

            if key == 27: # Esc
                self.menu.active = True
                self.menu.state = 'MAIN'
                self.paused = True
                continue

            if key == KEY_QUIT:
                # Replaced by Menu Quit? 
                # User said "Quit should ask for a confirmation", implying standard Menu workflow.
                # But maybe keep 'q' shortcut?
                # Let's map 'q' to Confirm Quit menu state directly?
                self.menu.active = True
                self.menu.state = 'CONFIRM_QUIT'
                self.menu.selected = 1
                self.paused = True
                continue
                
            if key == ord(' '):
                self.paused = not self.paused
            elif key == ord('1'):
                self.selected_room = "Corridor"
            elif key == ord('2'):
                self.selected_room = "Prison"
            elif key == ord('3'):
                self.selected_room = "Lair"
            elif key == ord('4'):
                self.selected_room = "Treasury"
            elif key == curses.KEY_UP or key == ord('w'):
                self.renderer.cam_y -= 1
            elif key == curses.KEY_DOWN or key == ord('s'):
                self.renderer.cam_y += 1
            elif key == curses.KEY_LEFT or key == ord('a'):
                self.renderer.cam_x -= 1
            elif key == curses.KEY_RIGHT or key == ord('d'):
                self.renderer.cam_x += 1
                
            if key == curses.KEY_MOUSE:
                try:
                    _, x, y, _, bstate = curses.getmouse()
                    map_x = x + self.renderer.cam_x
                    map_y = y + self.renderer.cam_y
                    
                    # Handle Dragging
                    # Start Drag
                    if bstate & curses.BUTTON1_PRESSED:
                        self.drag_start = (map_x, map_y)
                        self.drag_end = (map_x, map_y)
                    
                    # Update Drag Position
                    # In standard curses, if REPORT_MOUSE_POSITION is on, any mouse event sends KEY_MOUSE.
                    # However, bstate might not contain pressed/released bits during simple movement.
                    # We check if drag_start is active, and if so, we update drag_end to current mouse pos.
                    if self.drag_start:
                         self.drag_end = (map_x, map_y)

                    # End Drag / Click
                    if bstate & curses.BUTTON1_RELEASED:
                        if self.drag_start:
                             x1, y1 = self.drag_start
                             x2, y2 = (map_x, map_y)
                             # Ensure we capture the final position
                             self.drag_end = (map_x, map_y)
                             
                             self.handle_drag_action(x1, y1, x2, y2)
                             self.drag_start = None
                             self.drag_end = None
                    
                except curses.error:
                    pass



    def run(self):
        last_logic_time = time.time()
        
        while self.running:
            current_time = time.time()
            
            # Logic Update (1 sec tick)
            if not self.paused and current_time - last_logic_time >= 1.0:
                self.entities.update()
                last_logic_time = current_time
            
            # Input
            self.input()
            
            # Render (~30 FPS implicitly by sleep or just fast loop)
            # Pass drags only if NOT in menu?
            d_start = self.drag_start if not self.menu.active else None
            d_end = self.drag_end if not self.menu.active else None
            
            self.renderer.draw(self.paused, self.entities.imps, self.selected_room, 
                               d_start, d_end, self.entities.total_gold)
            
            if self.menu.active:
                self.menu.draw()
            
            # Finalize Frame
            self.stdscr.refresh()
            
            # Cap framerate slightly to save CPU
            curses.napms(33)

def main(stdscr):
    game = Game(stdscr)
    game.run()

if __name__ == "__main__":
    curses.wrapper(main)

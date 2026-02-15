import curses
import time
import random
import pickle
import os
import re

# Constants
TILES_HARD_ROCK = '^' # Indestructible
TILES_SOFT_ROCK = ' ' # Diggable (Deep rock) - Visual change to Space
TILES_DIRT_WALL = '░'
TILES_REINFORCED = '█' # Reinforced Wall
TILES_FLOOR = '.'     # Walkable
TILES_HEART = '♥'
TILES_PORTAL = 'O'
TILES_IMP = 'i'
TILES_GOLD = 'o'      # Diggable Gold
TILES_TREASURY = '$'  # Treasury Floor
TILES_BED = 'B'       # Lair Bed
TILES_TRAINING = 'T'  # Training Dummy
TILES_FARM = 'F'      # Farm Tile

COLOR_ROCK = 1
COLOR_FLOOR = 2
COLOR_HEART = 3
COLOR_PORTAL = 4
COLOR_IMP = 5
COLOR_SELECT = 6
COLOR_GOLD = 7
COLOR_REINFORCED = 8
COLOR_TREASURY = 9
COLOR_MENU = 10 
COLOR_SELECT_TEXT = 11
COLOR_BED = 12
COLOR_TRAINING = 13
COLOR_TRAINING = 13
COLOR_DUMMY = 14
COLOR_CLAIMED = 15
COLOR_TAGGED_REINFORCED = 16
COLOR_FARM = 17

TILES_TRAINING = 'T'
# Note: 'O' is used for Dummy in code logic, not a constant yet, but we'll use 'O' string

KEY_QUIT = ord('q')

class Tile:
    def __init__(self, char, x, y):

        self.char = char
        self.x = x
        self.y = y
        self.y = y
        self.tagged = False
        self.claimed = False
        self.is_solid = char in [TILES_HARD_ROCK, TILES_SOFT_ROCK, TILES_REINFORCED, TILES_GOLD]
        self.gold_value = 500 if char == TILES_GOLD else 0
        self.gold_stored = 0 # For Treasury
        self.progress = 0 # For digging/reinforcing steps. Max varying.
        self.timestamp = 0 # For job priority

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
        self.tiles[cy][cx].is_solid = True # Heart is blocking object
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
                    self.tiles[ny][nx].claimed = True # Initial claim
        
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
             
             # Check distance from portal
             px, py = self.portal_pos
             if ((vx - px) ** 2 + (vy - py) ** 2) ** 0.5 < 5:
                 continue
                 
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
            
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
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

    def is_exposed(self, x, y):
        # Check 8 neighbors for non-solid
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                if not self.tiles[ny][nx].is_solid:
                    return True
        return False

    def find_nearest_tagged(self, start_x, start_y, exclude=set()):
        # BFS to find nearest tagged tile or Gold
        queue = [(start_x, start_y)]
        visited = set([(start_x, start_y)])
        
        while queue:
            curr_x, curr_y = queue.pop(0)
            
            # Actual Loop
            DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]
            for dx, dy in DIRECTIONS:
                nx, ny = curr_x + dx, curr_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    tile = self.tiles[ny][nx]
                    if tile.tagged and tile.is_solid and (nx, ny) not in exclude:
                        # MUST be exposed to open air (or accessible)
                        if self.is_exposed(nx, ny):
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

    def find_nearest_farm(self, start_x, start_y):
        queue = [(start_x, start_y)]
        visited = set([(start_x, start_y)])
        while queue:
            curr_x, curr_y = queue.pop(0)
            # Check if this tile is Farm
            tile = self.tiles[curr_y][curr_x]
            if tile.char == TILES_FARM and not tile.is_solid:
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
                    # Must be Soft Rock (Dirt Wall), Not Tagged, AND NOT GOLD
                    if tile.char == TILES_SOFT_ROCK and not tile.tagged and tile.char != TILES_GOLD:
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

    def find_priority_job(self, start_x, start_y, exclude=set()):
        # Find best job: Oldest Timestamp > Gold > Distance
        candidates = []
        
        # Optimize iteration? Tagged list?
        # For now, scan all.
        for y in range(self.height):
            for x in range(self.width):
                t = self.tiles[y][x]
                if t.tagged and t.is_solid and (x, y) not in exclude:
                     # Check exposed
                     if self.is_exposed(x, y):
                         candidates.append(t)
        
        if not candidates: return None
        
        # Sort
        # 1. Timestamp (Ascending)
        # 2. Is Gold? (Yes=0, No=1) - So we sort by negation of "is gold" if we want Gold first? 
        # Actually prompt says: "prioritize digging gold over dirt if the gold and dirt have the SAME timestamp"
        # So secondary key is Type.
        # But timestamps are floats, unlikely to be exactly equal.
        # "roughly same timestamp" -> Drag action sets exact same time for batch.
        # So exact equality works for drag batches.
        
        # 3. Distance
        
        def priority_key(t):
            dist = max(abs(t.x - start_x), abs(t.y - start_y))
            is_gold = 0 if t.char == TILES_GOLD else 1
            return (t.timestamp, is_gold, dist)
            
        candidates.sort(key=priority_key)
        return candidates[0]

    def find_nearest_unclaimed(self, start_x, start_y, exclude=set()):
        # BFS to find nearest unclaimed Floor
        queue = [(start_x, start_y)]
        visited = set([(start_x, start_y)])
        
        # Limit search?
        while queue:
            curr_x, curr_y = queue.pop(0)
            
            # Check neighbors
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                nx, ny = curr_x + dx, curr_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    tile = self.tiles[ny][nx]
                    # Must be Floor, Not Solid, Not Claimed
                    if tile.char == TILES_FLOOR and not tile.is_solid and not tile.claimed:
                        # NEW REQUIREMENT: Must be adjacent to existing CLAIMED tile
                        is_contiguous = False
                        for cx, cy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                             tx, ty = nx + cx, ny + cy
                             if 0 <= tx < self.width and 0 <= ty < self.height:
                                 if self.tiles[ty][tx].claimed:
                                     is_contiguous = True
                                     break
                        
                        if is_contiguous:
                             return tile
                    
                    if not tile.is_solid and (nx, ny) not in visited and (nx, ny) not in exclude:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
                        if len(visited) > 500: break # Perf limit
            
            if len(visited) > 500: break
        return None

    def count_claimed(self):
        count = 0
        for y in range(self.height):
             for x in range(self.width):
                 if self.tiles[y][x].claimed:
                     count += 1
        return count

    def count_room_tiles(self, tile_char):
        count = 0
        for row in self.tiles:
            for t in row:
                if t.char == tile_char:
                    count += 1
        return count
    
    def is_valid_bed_spot(self, x, y):
        # Must be Lair ('L')
        # Must NOT be adjacent to another Bed ('B')
        # Neighbors 8-way? Or Manhatten?
        # "at least one empty (Lair) space away from one another"
        # implies if I am at X, X+1 cannot be bed. X+2 can.
        # So check immediate neighbors (including diagonals to be safe/neat)
        
        tile = self.get_tile(x, y)
        if not tile or tile.char != 'L': return False
        
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0: continue
                nx, ny = x + dx, y + dy
                nt = self.get_tile(nx, ny)
                if nt and nt.char == TILES_BED:
                    return False
        return True

class EntityManager:
    def __init__(self, game_map):
        self.map = game_map
        self.creatures = [] # Renamed from imps
        self.ids = 0
        self.total_gold = 0 
        self.heart_gold = 0
        self.mana = 0
        self.payday_timer = 0
        self.spawn_timer = 0
        self.bed_ownership = {} # (x,y) -> creature_id
        
        # Spawn initial imps
        hx, hy = self.map.heart_pos
        for _ in range(4): # Spawn 4
            self.spawn_creature('IMP', hx, hy)

    def spawn_creature(self, c_type, x, y):
        # Added tick_offset to randomize updates or idle timing
        names_imp = ["Op", "Baz", "Fo", "Zot", "Taw", "Bip", "Mog", "Gub"]
        names_gobarr = ["Grom", "Throk", "Varg", "Krug", "Drak", "Murn", "Zog", "Ruk"]
        
        name = random.choice(names_imp) if c_type == 'IMP' else random.choice(names_gobarr)
        
        # Base stats
        c = {
            'id': self.ids,
            'type': c_type,
            'x': x, 'y': y, 
            'state': 'IDLE', 
            'target': None, 
            'idle_timer': 0,
            'gold': 0,
            'work_timer': 0, 
            'name': name,
            'level': 1,
            'xp': 0,
            'health': 0,
            'max_health': 0,
            'damage': 0,
            'wage': 0,
            'happiness': 0,
            'hunger': 0,
            'unconscious': False
        }
        self.ids += 1
        
        if c_type == 'IMP':
            c['max_health'] = 50
            c['health'] = 50
            c['damage'] = 5
            c['wage'] = 0 # Imps don't get paid
        elif c_type == 'GOBARR':
            c['max_health'] = 150
            c['health'] = 150
            c['damage'] = 30
            c['wage'] = 5 # Starts at 5
        elif c_type == 'DUMMY':
            c['max_health'] = 9999
            c['health'] = 9999
            c['damage'] = 0
            c['wage'] = 0
            c['state'] = 'STATIC'
            c['name'] = "Dummy"
        
        self.creatures.append(c)

    # Legacy alias property for rendering
    @property
    def imps(self):
        return self.creatures

    def get_level_threshold(self, level):
        # Starting level 1. Level 2 takes 10 xp.
        # Each level above two takes twice as much as the level before.
        # L1->L2: 10
        # L2->L3: 20
        # L3->L4: 40
        # Formula: 10 * 2^(level-1). Too fast?
        # New Formula: Slower. 
        # L1->L2: 20 (Double start)
        # L2->L3: 50
        # L3->L4: 100
        if level < 1: return 0
        if level == 1: return 20 
        # Geometric growth but slower base?
        # Let's say: 20 * (2.5 ^ (level - 1))? Or just higher base.
        return int(20 * (2 ** (level - 1)))

    def check_level_up(self, c):
        # While XP >= Threshold, Level Up
        # Capping at 10
        while c['level'] < 10:
             thresh = self.get_level_threshold(c['level'])
             if c['xp'] >= thresh:
                 c['xp'] -= thresh
                 c['level'] += 1
                 # Stat Up
                 c['max_health'] += int(c['max_health'] * 0.1)
                 c['health'] = c['max_health']
                 c['damage'] += int(c['damage'] * 0.1)
                 if c['type'] == 'GOBARR':
                     c['wage'] += 1
             else:
                 break

    def update(self):
        # 0. Global Logic
        
        # Mana Generation
        claimed_count = self.map.count_claimed()
        self.mana = min(5000, self.mana + claimed_count)
        
        # Payday Timer (Once per 240 ticks)
        self.payday_timer += 1
        if self.payday_timer >= 240:
            self.payday_timer = 0
            # Announce Payday? (Renderer can check self.payday_timer == 0 or similar state)
            # Trigger Wage Seeking
            for c in self.creatures:
                if c['wage'] > 0 and c['state'] != 'UNCONSCIOUS':
                    c['state'] = 'SEEKING_WAGE'
                    c['target'] = None
                    # Happiness penalty if they don't get paid will be handled when they fail?
                    # For now just reset status logic.

        # Spawn Go'barr Check
        # Lair >= 10, Treasury >= 10, Portal exists. max 10 gobarrs.
        gobarrs = [c for c in self.creatures if c['type'] == 'GOBARR']
        
        self.spawn_timer -= 1
        
        if len(gobarrs) < 10 and self.spawn_timer <= 0:
             # Check Conditions
             lair_size = self.map.count_room_tiles('L')
             treasury_size = self.map.count_room_tiles(TILES_TREASURY)
             
             if lair_size >= 10 and treasury_size >= 10:
                 has_space = False
                 # Limit 20 creatures
                 if len(self.creatures) < 20: 
                      # Find valid bed spot to ensure cap isn't exceeded by space
                      for y in range(self.map.height):
                          for x in range(self.map.width):
                              if self.map.is_valid_bed_spot(x, y):
                                  has_space = True
                                  break
                          if has_space: break
                 
                 if has_space:
                      px, py = self.map.portal_pos
                      self.spawn_creature('GOBARR', px, py)
                      self.spawn_timer = random.randint(30, 60)

        # Logic update for creatures (1 tick per sec)
        for c in self.creatures:
            ix, iy = c['x'], c['y']
            
            # State: UNCONSCIOUS
            if c['health'] <= 0:
                c['state'] = 'UNCONSCIOUS'
                c['unconscious'] = True
                # No actions. Imps drag them?
                continue
            
            # Regen?
            pass

            # STATE TRANSITION LOGIC
            
            # STATE TRANSITION LOGIC (Weighted Priority)
            
            # Regen / Unconscious check
            if c['state'] == 'UNCONSCIOUS':
                if c['health'] < c['max_health']:
                    c['health'] += 0.1 # Slow regen
                else:
                    c['state'] = 'IDLE' # Wake up
                    c['unconscious'] = False
                continue

            # Calculate Desires
            desires = []
            
            # 1. Survival: Eat
            if c.get('hunger', 0) > 0 and c['type'] != 'IMP' and c['type'] != 'DUMMY':
                score = c['hunger']
                if score > 50: score += 20
                if score > 80: score += 50
                desires.append({'action': 'EAT', 'score': score})
            
            # 2. Greed: Wage
            if c.get('wage', 0) > 0:
                if c['state'] == 'SEEKING_WAGE':
                    desires.append({'action': 'SEEK_WAGE', 'score': 90})
            
            # 3. Duty: Build Bed (Go'barr)
            if c['type'] == 'GOBARR':
                pass 
            
            # 4. Improvement: Train
            if c['type'] == 'GOBARR' and c['level'] < 4:
                score = 40
                if c.get('happiness', 0) > 5: score += 10
                desires.append({'action': 'TRAIN', 'score': score})
            
            # 5. Work (Imps)
            if c['type'] == 'IMP':
                desires.append({'action': 'WORK', 'score': 100})
            
            # 6. Idle
            desires.append({'action': 'IDLE', 'score': 10})
            
            desires.sort(key=lambda x: x['score'], reverse=True)
            best = desires[0]
            action = best['action']
            
            # State Switching
            if action == 'EAT' and c['state'] != 'EATING' and c['state'] != 'MOVING_EAT':
                target = self.map.find_nearest_farm(ix, iy)
                if target:
                    c['target'] = (target.x, target.y)
                    c['state'] = 'MOVING_EAT'
            
            elif action == 'TRAIN' and c['state'] != 'TRAINING' and c['state'] != 'MOVING_TRAIN':
                 c['state'] = 'WANT_TRAIN'
            
            elif action == 'SEEK_WAGE' and c['state'] != 'SEEKING_WAGE':
                 c['state'] = 'SEEKING_WAGE'
            
            # EXECUTE STATE LOGIC
            
            # Hunger Update
            if c['type'] != 'IMP' and c['type'] != 'DUMMY':
                c['hunger'] = min(100, c.get('hunger', 0) + 0.5)

            # 1. SEEKING_WAGE
            if c['state'] == 'SEEKING_WAGE':
                 if not c['target']:
                      # Find nearest Treasury/Heart with gold > c['wage']
                      # Simplified: Go to Heart preferably or Treasury.
                      t = self.map.find_nearest_treasury_space(ix, iy)
                      c['target'] = self.map.heart_pos
                 
                 tx, ty = c['target']
                 dist = max(abs(ix - tx), abs(iy - ty))
                 if dist <= 1:
                     paid = False
                     if self.heart_gold >= c['wage']:
                         self.heart_gold -= c['wage']
                         paid = True
                     
                     if paid:
                         c['state'] = 'IDLE'
                         c['target'] = None
                         # c['happiness'] = min(10, c['happiness'] + 1)
                     else:
                         c['state'] = 'IDLE'
                         # c['happiness'] = max(-10, c['happiness'] - 1)
                 else:
                      path = self.map.get_path_step(ix, iy, tx, ty)
                      if path: c['x'], c['y'] = path
                 continue
            
            # 2. Bed Construction
            if c['type'] == 'GOBARR' and c['state'] == 'IDLE':
                my_bed_pos = None
                for pos, owner_id in self.bed_ownership.items():
                    if owner_id == c['id']:
                        my_bed_pos = pos
                        break
                
                if not my_bed_pos:
                    if not c.get('building_bed'):
                        target_spot = None
                        q = [(ix, iy)]
                        visited = set([(ix, iy)])
                        while q:
                            cx, cy = q.pop(0)
                            if self.map.is_valid_bed_spot(cx, cy):
                                target_spot = (cx, cy)
                                break
                            if len(visited) > 800: break
                            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                                nx, ny = cx + dx, cy + dy
                                if 0 <= nx < self.map.width and 0 <= ny < self.map.height:
                                    if (nx, ny) not in visited and not self.map.tiles[ny][nx].is_solid:
                                        visited.add((nx, ny))
                                        q.append((nx, ny))
                        
                        if target_spot:
                            c['target'] = target_spot
                            c['state'] = 'CONSTRUCTING_BED'
                    
            if c['state'] == 'CONSTRUCTING_BED':
                if not c['target']: 
                    c['state'] = 'IDLE'
                    continue
                tx, ty = c['target']
                if (ix, iy) == (tx, ty):
                    tile = self.map.get_tile(ix, iy)
                    if tile.char == 'L' and self.map.is_valid_bed_spot(ix, iy):
                        tile.char = TILES_BED
                        self.bed_ownership[(ix, iy)] = c['id']
                    c['state'] = 'IDLE'
                    c['target'] = None
                else:
                    path = self.map.get_path_step(ix, iy, tx, ty)
                    if path: c['x'], c['y'] = path
                    else: c['state'] = 'IDLE'
                continue

            # 3. Training Logic
            if c['state'] == 'WANT_TRAIN':
                 dummies = [d for d in self.creatures if d['type'] == 'DUMMY']
                 if dummies:
                     dummies.sort(key=lambda d: abs(c['x']-d['x']) + abs(c['y']-d['y']))
                     target = dummies[0]
                     c['target'] = (target['x'], target['y'])
                     c['state'] = 'TRAINING'
                 else:
                     c['state'] = 'IDLE'

            if c['state'] == 'TRAINING':
                 if not c['target'] or c['level'] >= 4:
                     c['state'] = 'IDLE'
                     continue
                     
                 tx, ty = c['target']
                 dist = max(abs(ix - tx), abs(iy - ty))
                 
                 if dist <= 1:
                     c['xp'] += 1
                     self.check_level_up(c)
                     
                     moves = []
                     for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                         nx, ny = ix + dx, iy + dy
                         t = self.map.get_tile(nx, ny)
                         if t and not t.is_solid and t.char == TILES_TRAINING:
                             moves.append((nx, ny))
                     
                     if moves:
                         nx, ny = random.choice(moves)
                         c['x'], c['y'] = nx, ny
                 else:
                     path = self.map.get_path_step(ix, iy, tx, ty)
                     if path: c['x'], c['y'] = path
                     else: c['state'] = 'IDLE'
                 continue
            
            # 4. Eating Logic
            if c['state'] == 'MOVING_EAT':
                 if not c['target']: 
                     c['state'] = 'IDLE'
                     continue
                 tx, ty = c['target']
                 if (ix, iy) == (tx, ty):
                     c['state'] = 'EATING'
                 else:
                     path = self.map.get_path_step(ix, iy, tx, ty)
                     if path: c['x'], c['y'] = path
                     else: c['state'] = 'IDLE'
                 continue
            
            if c['state'] == 'EATING':
                 c['hunger'] -= 5
                 if c['hunger'] <= 0:
                     c['hunger'] = 0
                     c['state'] = 'IDLE'
                 continue


            # 4. Imp Logic (Worker)
            if c['type'] == 'IMP':
                pass # Fallthrough to existing worker logic
            else:
                # Go'barr wander if nothing else
                if c['state'] == 'IDLE':
                     # Random wander
                     c['idle_timer'] += 1
                     if c['idle_timer'] >= 2:
                        c['idle_timer'] = 0
                        neighbors = []
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, ny = ix + dx, iy + dy
                            t = self.map.get_tile(nx, ny)
                            if t and not t.is_solid:
                                neighbors.append((nx, ny))
                        if neighbors:
                            nx, ny = random.choice(neighbors)
                            c['x'] = nx
                            c['y'] = ny
                continue

            # --- ORIGINAL IMP LOGIC STARTS HERE (Refactored variable 'imp' to 'c') ---
            imp = c # Alias for minimal code change
            
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
                     if t_tile and t_tile.char == TILES_SOFT_ROCK and not t_tile.tagged and t_tile.char != TILES_GOLD: target_valid = True
                 # If Claiming: Not Claimed?
                 elif imp['state'] == 'CLAIMING':
                     if t_tile and not t_tile.claimed and not t_tile.is_solid: target_valid = True
            
            if not target_valid and imp['state'] not in ['RETURNING_GOLD', 'IDLE', 'UNCONSCIOUS', 'MOVING_PICKUP', 'MOVING_DIG', 'MOVING_REINFORCE', 'MOVING_CLAIM']:
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
                
                # Check 2: REMOVED "Return if carrying gold" to allow picking up dropped gold
                # We only return if full, or if we explicitly decide to later.
                
                # Divide and Conquer: Filter targets taken by other imps
                # But allowing picking up dropped gold
                desired_dropped_gold = None
                
                # Check Priority 0: Pick up Dropped Gold (if not full)
                if imp['gold'] < 300:
                    # BFS for floor with gold > 0
                    queue = [(ix, iy)]
                    visited = set([(ix, iy)])
                    while queue:
                        cx, cy = queue.pop(0)
                        t = self.map.get_tile(cx, cy)
                        if t.char == TILES_FLOOR and t.gold_value > 0 and not t.is_solid: # Ensure valid floor
                             desired_dropped_gold = (cx, cy)
                             break
                        
                        # Limit search
                        if len(visited) > 200: break
                        
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < self.map.width and 0 <= ny < self.map.height:
                                if (nx, ny) not in visited:
                                    visited.add((nx, ny))
                                    queue.append((nx, ny))
                
                if desired_dropped_gold:
                    imp['target'] = desired_dropped_gold
                    imp['state'] = 'MOVING_PICKUP'
                    
                else: 
                     # Priority 1: Digging/Mining (Tagged)
                     # Density Limit Check
                     # Max 3 imps per tile.
                     # We must count how many imps target a specific tile.
                     
                     taken_counts = {}
                     for other in self.creatures:
                         if other['target']:
                             t = other['target']
                             taken_counts[t] = taken_counts.get(t, 0) + 1
                     
                     # We exclude targets that have >= 3 imps
                     exclude_targets = set([t for t, count in taken_counts.items() if count >= 3])
                     
                     
                     
                     # Check Priority 1: Digging/Reinforcing based on Job Priority
                     # This unifies Digging and Reinforcing into "Work" if Reinforce was tagged?
                     # But Reinforce is separate logic in original code (untagged).
                     # "Priorities: Digging over Claiming"
                     
                     # Digging is Tagged. Reinforcing is untagged auto-work.
                     # We prioritize Tagged jobs (Digging) first?
                     # The prompt implies job queue.
                     
                     target_tile = self.map.find_priority_job(ix, iy, exclude=exclude_targets)
                     if target_tile:
                         imp['target'] = (target_tile.x, target_tile.y)
                         # Determine state based on tile
                         # Tagged tiles are usually Digging (or Mining if gold)
                         # Reset stats
                         imp['state'] = 'MOVING_DIG' # Logic handles gold/rock in DIGGING state
                     else:
                          # Priority 2: Claiming (Unclaimed Floor) - Lower Priority
                          # Divide and Conquer: Exclude unclaimed tiles already targeted by others for claiming
                          claim_targets = set()
                          for other in self.creatures:
                              if other['target'] and other['state'] in ['MOVING_CLAIM', 'CLAIMING']:
                                  claim_targets.add(other['target'])
                          
                          target_tile = self.map.find_nearest_unclaimed(ix, iy, exclude=claim_targets)
                          if target_tile:
                              imp['target'] = (target_tile.x, target_tile.y)
                              imp['state'] = 'MOVING_CLAIM'
                          else:
                                # Priority 3: Reinforcing (Unvisited Dirt Walls) - Lowest?
                                # This is automatic work.
                                target_tile = self.map.find_nearest_reinforceable(ix, iy)
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
                     # Only if we aren't already targeting heart?
                     if not target_found:
                         t_tile = self.map.find_nearest_treasury_space(ix, iy)
                         if t_tile:
                             imp['target'] = (t_tile.x, t_tile.y)
                             target_found = True
                     
                     # If both full?
                     if not target_found:
                         # Drop on floor where we stand
                         tile = self.map.get_tile(ix, iy)
                         if tile.char == TILES_FLOOR or tile.char == '=':
                             tile.gold_value += imp['gold']
                             tile.char = '=' # Ensure visual
                             # self.total_gold += imp['gold'] # Dropped gold is NOT secure score.
                             imp['gold'] = 0
                             imp['state'] = 'IDLE'
                             imp['target'] = None
                             continue
                         else:
                             # Should be rare if we are idly moving?
                             # Just Idle and hope to move to floor?
                             imp['state'] = 'IDLE' 
                             imp['target'] = None
                             continue # Re-eval next tick
 
                
                tx, ty = imp['target']
                
                # Move
                # If target is Heart, we check adjacency
                deposit_ready = False
                t_tile_target = self.map.get_tile(tx, ty)
                
                if t_tile_target and t_tile_target.char == TILES_HEART:
                    # Check dist
                    dist = max(abs(ix - tx), abs(iy - ty))
                    if dist <= 1:
                        deposit_ready = True
                else:
                     if (ix, iy) == (tx, ty):
                         deposit_ready = True
                
                if deposit_ready:
                    # Deposit
                    tile = t_tile_target # The target (Heart or Treasury)
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
            if imp['state'] == 'MOVING_PICKUP':
                if not imp['target']:
                     imp['state'] = 'IDLE'
                     continue
                tx, ty = imp['target']
                if (ix, iy) == (tx, ty):
                    # Pickup
                    t_tile = self.map.get_tile(ix, iy)
                    if t_tile.gold_value > 0:
                        space = 300 - imp['gold']
                        pickup = min(space, t_tile.gold_value)
                        imp['gold'] += pickup
                        t_tile.gold_value -= pickup
                        
                        if t_tile.gold_value <= 0:
                            t_tile.char = TILES_FLOOR # Reset char to floor if depleted
                    
                    imp['target'] = None
                    imp['state'] = 'IDLE'
                else:
                    path = self.map.get_path_step(ix, iy, tx, ty)
                    if path: 
                        imp['x'], imp['y'] = path
                    else:
                        imp['target'] = None # Unreachable
                        imp['state'] = 'IDLE'

            elif imp['state'] == 'MOVING_DIG' or imp['state'] == 'MOVING_REINFORCE' or imp['state'] == 'MOVING_CLAIM':
                if not imp['target']: 
                    imp['state'] = 'IDLE' 
                    continue
                tx, ty = imp['target']
                t_tile = self.map.get_tile(tx, ty)
                
                # Check adjacency (Chebyshev distance for diagonals)
                dist_x = abs(ix - tx)
                dist_y = abs(iy - ty)
                dist = max(dist_x, dist_y)
                if dist <= 1:
                    # Start Working
                    if imp['state'] == 'MOVING_DIG': 
                        imp['state'] = 'DIGGING'
                        imp['work_timer'] = 0
                    elif imp['state'] == 'MOVING_REINFORCE': 
                        imp['state'] = 'REINFORCING'
                        imp['work_timer'] = 0
                    elif imp['state'] == 'MOVING_CLAIM':
                         # Claiming requires standing on top (dist == 0)
                         if dist == 0:
                             imp['state'] = 'CLAIMING'
                             imp['work_timer'] = 0
                         else:
                             # Keep moving closer if adjacent
                             path = self.map.get_path_step(ix, iy, tx, ty)
                             if path: 
                                 imp['x'], imp['y'] = path
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
                
                # Mining Logic (Unified)
                if t_tile.char == TILES_GOLD:
                     mine_amt = 100
                     available = t_tile.gold_value
                     
                     # 1. Mine the rock (reduce availability)
                     if available > mine_amt:
                         mined = mine_amt
                         t_tile.gold_value -= mine_amt
                     else:
                         mined = available
                         t_tile.gold_value = 0
                     
                     # 2. Add to Imp if capacity exists
                     space = 300 - imp['gold']
                     to_floor = mined
                     
                     if space > 0:
                         to_inv = min(mined, space)
                         imp['gold'] += to_inv
                         to_floor -= to_inv
                    
                     # 3. Handle Dropped Gold
                     # If tile destroyed, stored on floor. If not, it's effectively "loose" but invisible?
                     # Per req: "Gold should fall on the ground in the space occupied by the destroyed block"
                     # We only convert to floor if destroyed (value <= 0).
                     
                     if t_tile.gold_value <= 0:
                         t_tile.char = TILES_FLOOR
                         t_tile.is_solid = False
                         t_tile.tagged = False
                         t_tile.gold_value = to_floor + t_tile.gold_stored # Place dropped gold
                         t_tile.gold_stored = 0
                         imp['target'] = None
                         imp['state'] = 'IDLE' 
                     else:
                         # Not destroyed yet. 
                         # If we couldn't carry it, it is currently "lost" or should we store it?
                         # Per req: "Imps should dig out tagged blocks even if they cannot carry any more gold."
                         # So we MUST deplete it.
                         # Where does "to_floor" go?
                         # We can add a 'dropped_gold' field to Tile distinct from 'gold_value'.
                         # For now, let's just add it to gold_stored, which is unused for gold tiles.
                         t_tile.gold_stored += to_floor
                     
                     if imp['gold'] >= 300 and t_tile.gold_value <= 0:
                         imp['state'] = 'RETURNING_GOLD'
                elif t_tile.char == TILES_REINFORCED:
                    # Reinforced digging takes longer
                    # Use Progress. Reinforced Wall HP = 200 (approx 2 sec for lvl 1 imp?)
                    # Each tick adds 10 * lvl progress?
                    # Previous was 2 ticks.
                    # Let's say HP = 20.
                    # Imp adds 10 * level.
                    power = 10 * imp['level']
                    t_tile.progress += power
                    
                    # Grant XP
                    imp['xp'] += 1
                    self.check_level_up(imp)

                    if t_tile.progress >= 20:
                        t_tile.char = TILES_FLOOR
                        t_tile.is_solid = False
                        t_tile.tagged = False
                        t_tile.progress = 0
                        imp['target'] = None
                        imp['state'] = 'IDLE'
                else:
                    # Normal Dig (Soft Rock)
                    # HP = 10.
                    power = 10 * imp['level']
                    t_tile.progress += power
                    
                    imp['xp'] += 1
                    self.check_level_up(imp)
                    
                    if t_tile.progress >= 10:
                        t_tile.char = TILES_FLOOR
                        t_tile.is_solid = False
                        t_tile.tagged = False
                        t_tile.progress = 0
                        imp['target'] = None
                        imp['state'] = 'IDLE'

            elif imp['state'] == 'REINFORCING':
                tx, ty = imp['target']
                t_tile = self.map.get_tile(tx, ty)
                
                # Reinforce logic
                # Target: Soft Rock.
                # HP to become Reinforced: 30.
                power = 10 * imp['level']
                t_tile.progress += power

                imp['xp'] += 1
                self.check_level_up(imp)

                if t_tile.progress >= 30:
                    t_tile.char = TILES_REINFORCED
                    t_tile.is_solid = True # Should be solid
                    t_tile.progress = 0
                    imp['target'] = None
                    imp['state'] = 'IDLE'
            
            elif imp['state'] == 'CLAIMING':
                 tx, ty = imp['target']
                 t_tile = self.map.get_tile(tx, ty)
                 
                 if t_tile.claimed:
                     imp['state'] = 'IDLE'
                     imp['target'] = None
                     continue
                 
                 imp['work_timer'] += 1
                 if imp['work_timer'] >= 2:
                     t_tile.claimed = True
                     imp['xp'] += 1
                     self.check_level_up(imp) # Grants XP?
                     imp['state'] = 'IDLE'
                     imp['target'] = None
            
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

            # Happiness Check
            if c['happiness'] <= -10 and c['state'] != 'LEAVING':
                c['state'] = 'LEAVING'
                c['target'] = self.map.portal_pos
            
            if c['state'] == 'LEAVING':
                px, py = self.map.portal_pos
                if (c['x'], c['y']) == (px, py):
                     # Leave
                    bed_pos = None
                    for pos, owner_id in self.bed_ownership.items():
                        if owner_id == c['id']:
                            bed_pos = pos
                            break
                    if bed_pos:
                        del self.bed_ownership[bed_pos]
                        tile = self.map.get_tile(*bed_pos)
                        tile.char = 'L'
                        
                    self.creatures.remove(c)
                    continue
                else:
                    path = self.map.get_path_step(c['x'], c['y'], px, py)
                    if path: c['x'], c['y'] = path

        # Spawn Dummies Check (End of Update)
        if self.payday_timer % 10 == 0:
            for y in range(1, self.map.height - 1):
                for x in range(1, self.map.width - 1):
                    t = self.map.get_tile(x, y)
                    if t.char == TILES_TRAINING:
                        is_center = True
                        for dy in [-1, 0, 1]:
                            for dx in [-1, 0, 1]:
                                if self.map.get_tile(x + dx, y + dy).char != TILES_TRAINING:
                                    is_center = False
                                    break
                            if not is_center: break
                        
                        if is_center:
                            has_dummy = False
                            for c in self.creatures:
                                if c['type'] == 'DUMMY' and c['x'] == x and c['y'] == y:
                                    has_dummy = True
                                    break
                            
                            if not has_dummy:
                                self.spawn_creature('DUMMY', x, y)

class Renderer:
    def __init__(self, stdscr, game_map):
        self.stdscr = stdscr
        self.map = game_map
        self.cam_x = 0
        self.cam_y = 0
        self.setup_colors()

    def setup_colors(self):
        curses.start_color()
        if curses.can_change_color():
             try:
                 curses.init_color(curses.COLOR_BLACK, 0, 0, 0)
             except: pass

        curses.init_pair(COLOR_ROCK, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(COLOR_FLOOR, curses.COLOR_BLACK, curses.COLOR_BLACK) 
        curses.init_pair(COLOR_HEART, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(COLOR_PORTAL, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(COLOR_IMP, curses.COLOR_GREEN, curses.COLOR_BLACK) 
        curses.init_pair(COLOR_SELECT, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(COLOR_GOLD, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(COLOR_REINFORCED, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(COLOR_TAGGED_REINFORCED, curses.COLOR_CYAN, curses.COLOR_BLUE) # Visible
        curses.init_pair(COLOR_TREASURY, curses.COLOR_YELLOW, curses.COLOR_BLACK) 
        curses.init_pair(COLOR_MENU, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(COLOR_SELECT_TEXT, curses.COLOR_YELLOW, curses.COLOR_BLUE)
        curses.init_pair(COLOR_BED, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(COLOR_TRAINING, curses.COLOR_BLACK, curses.COLOR_WHITE) 
        curses.init_pair(COLOR_DUMMY, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(COLOR_CLAIMED, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(COLOR_FARM, curses.COLOR_GREEN, curses.COLOR_YELLOW) # Green 'F' on Brown/Yellow background

    def draw(self, paused, imps, selected_room, drag_start=None, drag_end=None, total_gold=0, selected_entity=None, mana=0):
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
                   if char == TILES_FLOOR: 
                       pair = COLOR_FLOOR
                       if tile.claimed:
                            pair = COLOR_CLAIMED
                       
                       if tile.gold_value > 0: # Dropped Gold
                           pair = COLOR_GOLD
                           char = '=' # Yellow '=' for dropped gold
                           # We apply attr later, but let's signal bold?
                           # We can check char later.
                   elif char == TILES_HEART: pair = COLOR_HEART
                   elif char == TILES_PORTAL: pair = COLOR_PORTAL
                   elif char == TILES_GOLD: pair = COLOR_GOLD
                   elif char == TILES_REINFORCED:
                       pair = COLOR_REINFORCED
                       if tile.tagged:
                           pair = COLOR_TAGGED_REINFORCED
                   elif char == TILES_TREASURY: pair = COLOR_TREASURY

                   elif char == TILES_FARM: pair = COLOR_FARM
                   elif char == '=': pair = COLOR_GOLD # Explicit fix for white gold
                   
                   attr = curses.color_pair(pair)
                   if char == '=': attr |= curses.A_BOLD # Bright Yellow for dropped gold

                   if tile.tagged:
                       # Adaptive Highlight for Tagged
                       if tile.is_solid:
                           attr = curses.color_pair(COLOR_SELECT)
                       else:
                           attr = curses.color_pair(COLOR_SELECT_TEXT) | curses.A_BOLD
                   
                   # Treasury logic
                   if char == TILES_TREASURY and tile.gold_stored > 0:
                       # Inverted visual for occupied treasury?
                       # "Make the symbol for an occupied space in the treasury an inverted yellow $."
                       attr = curses.color_pair(COLOR_TREASURY) | curses.A_REVERSE
                   
                   # Drag Selection Highlight - Simplified to Start Tile Only
                   if drag_start and (map_x, map_y) == drag_start:
                        if tile.is_solid:
                            attr = curses.color_pair(COLOR_SELECT)
                        else:
                            attr = curses.color_pair(COLOR_SELECT_TEXT) | curses.A_BOLD

                   try:
                       self.stdscr.addch(y, x, char, attr)
                   except curses.error:
                       pass # Bottom right corner issue
                else:
                   try:
                       self.stdscr.addch(y, x, ' ')
                   except curses.error:
                       pass
        
        # Draw Creatures
        for c in imps: # Generic alias 'imps' passed from run loop is actually creatures list
            scr_x = c['x'] - self.cam_x
            scr_y = c['y'] - self.cam_y
            if 0 <= scr_x < w and 0 <= scr_y < h - 1:
                # Type rendering
                char = 'i'
                pair = COLOR_IMP
                
                if c['type'] == 'GOBARR':
                    char = 'g'
                    pair = COLOR_IMP 
                elif c['type'] == 'DUMMY':
                    char = 'O'
                    pair = COLOR_DUMMY

                attr = curses.color_pair(pair) | curses.A_BOLD
                if c.get('gold', 0) > 0: # Carry gold visual
                     attr = curses.color_pair(COLOR_GOLD) | curses.A_BOLD
                
                # State visuals?
                if c.get('state') == 'UNCONSCIOUS':
                    char = 'X' 
                    attr = curses.color_pair(curses.COLOR_RED) | curses.A_DIM
                
                try:
                    self.stdscr.addstr(scr_y, scr_x, char, attr)
                except curses.error: pass

        # Draw UI
        # Status Line Logic
        status_text = ""
        
        # Priority 1: Pause State
        if paused:
            status_text = "PAUSED "
            
        # Base info
        base_info = f"| Pos: {self.cam_x},{self.cam_y} | Room: {selected_room} | Gold: {total_gold} | Mana: {mana}"
        # Wait, renderer map doesn't have game ref?
        # Argument passing? Not ideal.
        # Let's just fix the argument to pass Mana.
        # But we are in renderer...
        pass # Handle in next chunk
        
        # Base info
        base_info = f"| Pos: {self.cam_x},{self.cam_y} | Room: {selected_room} | Gold: {total_gold} | Mana: {mana}"
        
        # Payday info?
        # Accessing renderer via game... need to pass it in?
        # We can append it if we had access. But draw() arguments.
        # Let's assume passed in via total_gold or new arg. 
        # Modifying run() later to pass it? Or just omit for now.
        
        # Priority 2: Inspection (Append at end)
        imp_info = ""
        if selected_entity:
            ent = selected_entity
            
            # Map state to descriptive text
            state_map = {
                'IDLE': "Idle",
                'MOVING_DIG': "Going to dig",
                'DIGGING': "Digging",
                'RETURNING_GOLD': "Carrying gold",
                'MOVING_PICKUP': "Going to pick up gold",
                'MOVING_REINFORCE': "Going to reinforce",
                'REINFORCING': "Reinforcing",
                'MOVING_DROP': "Dropping gold",
                'SEEKING_WAGE': "Seeking Wage",
                'CONSTRUCTING_BED': "Building Bed",
                'TRAINING': "Training",
                'MOVING_CLAIM': "Going to claim",
                'CLAIMING': "Claiming land",
                'CLAIMING': "Claiming land",
                'EATING': "Eating",
                'UNCONSCIOUS': "Unconscious"
            }
            s_text = state_map.get(ent.get('state'), ent.get('state'))
            
            imp_info = f"| {ent.get('name', '???')} (Lvl {ent.get('level',1)}) - {s_text} "
            if ent['type'] == 'GOBARR':
                 imp_info += f"| XP:{ent['xp']} HP:{ent['health']}/{ent['max_health']} DMG:{ent['damage']} Wage:{ent['wage']} Hap:{ent.get('happiness', 0)} Hun:{int(ent.get('hunger',0))}"
            elif ent['type'] == 'IMP':
                 imp_info += f"| XP:{ent['xp']} HP:{ent['health']}/{ent['max_health']} Hap:{ent.get('happiness', 0)}"
        
        final_status = (status_text + base_info + imp_info).strip()
        
        # Always draw the status line background to clear artifacts
        try:
             # Draw Background
             self.stdscr.addstr(h-1, 0, " " * (w-1))
             # Draw Text
             if final_status:
                self.stdscr.addstr(h-1, 0, final_status[:w-1])
        except curses.error: pass
        
        # Draw Pause Border
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

    @staticmethod
    def get_latest_save():
        d = SaveManager.get_save_dir()
        files = SaveManager.list_saves()
        if not files: return None
        
        # Sort by mtime
        files.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
        return files[0]

class Menu:
    def __init__(self, stdscr, game):
        self.stdscr = stdscr
        self.game = game
        self.active = False
        self.state = 'MAIN' # MAIN, SAVE, LOAD, CONFIRM_QUIT
        self.options = [] # Dynamic
        self.selected = 0
        self.input_text = ""
        self.load_files = []
        self.load_index = 0
        self.delete_confirm = None # Filename to delete
        
        self.update_options() # Init options

    def update_options(self):
        if self.game.game_started:
            self.options = ['Resume', 'Save', 'Load', 'Quit']
        else:
            self.options = ['New Game', 'Continue', 'Load', 'Quit']
        
        # Clamp selection just in case
        if self.selected >= len(self.options):
            self.selected = 0
    
    def draw(self):
        h, w = self.stdscr.getmaxyx()
        
        # Draw Box
        box_w = 40
        box_h = 16 # Increased height for more options
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
                attr = curses.A_NORMAL if i == self.selected else menu_attr
                self.stdscr.addstr(start_y + 2 + i * 2, start_x + 4, prefix + opt, attr)
                
        elif self.state == 'SAVE':
            self.stdscr.addstr(start_y + 2, start_x + 2, "Enter Name:", menu_attr)
            self.stdscr.addstr(start_y + 4, start_x + 2, self.input_text + "_", menu_attr)
            self.stdscr.addstr(start_y + 10, start_x + 2, "Press Enter to Save", menu_attr)
            self.stdscr.addstr(start_y + 11, start_x + 2, "Esc to Cancel", menu_attr)
            
        elif self.state == 'LOAD':
            if self.delete_confirm:
                self.stdscr.addstr(start_y + 2, start_x + 2, "DELETE this save?", menu_attr)
                self.stdscr.addstr(start_y + 3, start_x + 2, self.delete_confirm, menu_attr)
                self.stdscr.addstr(start_y + 5, start_x + 2, "> Yes (Enter)", menu_attr)
                self.stdscr.addstr(start_y + 6, start_x + 2, "  No (Esc)", menu_attr)
                return

            if not self.load_files:
                self.stdscr.addstr(start_y + 2, start_x + 2, "No Saves Found", menu_attr)
            else:
                self.stdscr.addstr(start_y + 1, start_x + 25, "(D)elete", menu_attr) 
                for i in range(min(5, len(self.load_files))):
                    idx = self.load_index + i 
                    if idx < len(self.load_files):
                         prefix = "> " if idx == self.selected else "  "
                         attr = curses.A_NORMAL if idx == self.selected else menu_attr
                         self.stdscr.addstr(start_y + 2 + i, start_x + 2, prefix + self.load_files[idx], attr)
        
        elif self.state == 'CONFIRM_QUIT':
             self.stdscr.addstr(start_y + 2, start_x + 2, "Exit ASCIIper?", menu_attr)
             opts = ["Yes", "Cancel"]
             for i, opt in enumerate(opts):
                 prefix = "> " if i == self.selected else "  "
                 attr = curses.A_NORMAL if i == self.selected else menu_attr
                 self.stdscr.addstr(start_y + 5 + i, start_x + 4, prefix + opt, attr)

    def input(self, key):
        if key == curses.KEY_MOUSE:
            try:
                _, x, y, _, bstate = curses.getmouse()
                if bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                    # Check overlap with Menu Box
                    h, w = self.stdscr.getmaxyx()
                    box_w = 40
                    box_h = 16
                    start_y = h // 2 - box_h // 2
                    start_x = w // 2 - box_w // 2
                    
                    # Clicks inside box
                    if start_x <= x < start_x + box_w and start_y <= y < start_y + box_h:
                        if self.state == 'MAIN':
                            rel_y = y - (start_y + 2)
                            if rel_y >= 0 and rel_y % 2 == 0:
                                idx = rel_y // 2
                                if 0 <= idx < len(self.options):
                                    self.selected = idx
                                    key = 10 # Emulate Enter
                        
                        elif self.state == 'CONFIRM_QUIT':
                            rel_y = y - (start_y + 5)
                            if rel_y >= 0:
                                idx = rel_y
                                if 0 <= idx < 2:
                                    self.selected = idx
                                    key = 10
            except:
                pass

        if key == 27: # Esc
            if self.state == 'MAIN':
                self.active = False
            elif self.state == 'LOAD' and self.delete_confirm:
                self.delete_confirm = None
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
                if opt == 'New Game':
                     # Reset Game
                     self.game.__init__(self.stdscr, start_in_menu=False) # Re-init everything
                     # self.active = False # Handled in init? No Init makes active False? 
                     # Wait, Game.__init__ sets active=False if start_in_menu=False?
                     # Let's check Game.__init__ below
                elif opt == 'Continue':
                     latest = SaveManager.get_latest_save()
                     if latest:
                         if SaveManager.load_game(self.game, latest):
                             self.game.game_started = True
                             self.game.paused = False
                             self.active = False
                     else:
                         # Flash error or just nothing?
                         pass
                elif opt == 'Resume': 
                    self.active = False
                    self.game.paused = False
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
            if self.delete_confirm:
                if key == 10:
                     # Do delete
                     path = os.path.join(SaveManager.get_save_dir(), self.delete_confirm)
                     if os.path.exists(path):
                         os.remove(path)
                     self.load_files = SaveManager.list_saves()
                     self.delete_confirm = None
                     self.selected = 0
                return

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
            elif key == ord('d') or key == ord('D'):
                if self.load_files:
                    self.delete_confirm = self.load_files[self.selected]
    
        elif self.state == 'CONFIRM_QUIT':
             if key == curses.KEY_UP or key == curses.KEY_DOWN:
                 self.selected = 1 - self.selected
             elif key == 10:
                 if self.selected == 0: # Yes
                     self.game.running = False
                 else:
                     self.state = 'MAIN'
                     self.update_options()

class Game:
    def __init__(self, stdscr, start_in_menu=True):
        self.stdscr = stdscr
        self.running = True
        self.paused = False
        self.game_started = False
        self.selected_room = "None"
        self.selected_entity = None
        
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
        curses.mouseinterval(0) # Disable click resolution delay for instant drag start

        # Force enable Mouse Drag (Button Motion) tracking in xterm-compatible terminals
        # Standard curses sometimes misses this if TERM is generic
        pass
        
        self.map = Map(80, 25) # Standard terminal size
        self.entities = EntityManager(self.map)
        self.renderer = Renderer(stdscr, self.map)
        
        # Center camera roughly
        self.renderer.cam_x = max(0, self.map.width // 2 - 40)
        self.renderer.cam_y = max(0, self.map.height // 2 - 15)
        
        self.renderer.cam_y = max(0, self.map.height // 2 - 15)
        
        self.menu = Menu(stdscr, self)
        
        if start_in_menu:
            self.game_started = False
            self.paused = True
            self.menu.active = True
            self.menu.state = 'MAIN'
            self.menu.update_options()
        else:
            self.game_started = True
            self.paused = False
            self.menu.active = False

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
        
        
        # Room Costs
        # Treasury: 25, Lair: 50, Prison: 100
        cost_per_tile = 0
        if self.selected_room == "Treasury": cost_per_tile = 25
        elif self.selected_room == "Lair": cost_per_tile = 50
        elif self.selected_room == "Prison": cost_per_tile = 100
        elif self.selected_room == "Training Room": cost_per_tile = 150
        elif self.selected_room == "Farm": cost_per_tile = 100
        
        # Apply Logic to Rect
        for ry in range(min_y, max_y + 1):
            for rx in range(min_x, max_x + 1):
                tile = self.map.get_tile(rx, ry)
                if tile:
                    # Tagging Logic (Soft Rock, Gold, Reinforced)
                    if tile.char in [TILES_SOFT_ROCK, TILES_GOLD, TILES_REINFORCED]:
                        tile.tagged = drag_mode_tag
                        if drag_mode_tag:
                            tile.timestamp = time.time()
                        
                    elif tile.char == TILES_FLOOR or tile.char in ['P', 'L', TILES_TREASURY, '=', TILES_TRAINING, TILES_FARM]:
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
                        elif self.selected_room == "Training Room":
                            char_to_apply = TILES_TRAINING
                        elif self.selected_room == "Farm":
                            char_to_apply = TILES_FARM
                        
                        # Drop logic for costs
                        # Update Costs
                        if char_to_apply and cost_per_tile > 0:
                            # Try to pay
                            paid = False
                            
                            # 1. Pay from Treasuries
                            # We iterate ALL tiles to find treasuries with gold? Inefficient?
                            # Optim: Use self.entities.total_gold check first?
                            # total_gold includes Heart + Treasury.
                            
                            # Simple logic: Check total affordable?
                            # We need to deduct.
                            needed = cost_per_tile
                            
                            # Search Treasuries
                            for row in self.map.tiles:
                                for t in row:
                                    if t.char == TILES_TREASURY and t.gold_stored > 0:
                                        take = min(needed, t.gold_stored)
                                        t.gold_stored -= take
                                        needed -= take
                                        if needed <= 0: break
                                if needed <= 0: break
                            
                            # Pay from Heart
                            if needed > 0:
                                take = min(needed, self.entities.heart_gold)
                                self.entities.heart_gold -= take
                                needed -= take
                                
                            if needed <= 0:
                                paid = True
                                # Recalc total score optimization? user loop handles it next tick
                            else:
                                # Refund logic? Rollback?
                                # If we failed to pay, we should refund what we took and ABORT.
                                # Complex partial rollback.
                                # Easier: Check affordability first.
                                pass
                                
                            # Re-do with pre-check
                            # Actually, let's just do a quick pre-check of Total Gold.
                            # self.entities.total_gold is updated each tick. It might be stale?
                            # Let's count explicitly? No, total_gold should be close enough.
                            # Recalculate just to be safe.
                            current_total = self.entities.heart_gold
                            for row in self.map.tiles:
                                for t in row:
                                    if t.char == TILES_TREASURY: current_total += t.gold_stored
                            
                            if current_total >= cost_per_tile:
                                # Deduct Logic (Real)
                                needed = cost_per_tile
                                for row in self.map.tiles:
                                    for t in row:
                                        if t.char == TILES_TREASURY and t.gold_stored > 0:
                                            take = min(needed, t.gold_stored)
                                            t.gold_stored -= take
                                            needed -= take
                                            if needed <= 0: break
                                    if needed <= 0: break
                                if needed > 0:
                                    take = min(needed, self.entities.heart_gold)
                                    self.entities.heart_gold -= take
                                
                                # Apply Build
                                paid = True
                            else:
                                paid = False
                        
                        # Apply if free or paid
                        if char_to_apply and (cost_per_tile == 0 or paid):
                             old_char = tile.char 
                             # Handle White Gold Bug / Absorption
                             # If we are overwriting '=' or gold char
                             
                             tile.char = char_to_apply
                             if char_to_apply == TILES_TREASURY:
                                if tile.gold_value > 0 or old_char == '=':
                                     tile.gold_stored += tile.gold_value
                                     tile.gold_value = 0
                                else:
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
                self.menu.update_options()
                self.paused = True
                continue
            
            # Unpause if menu just closed (Logic handled in Menu, but we need to sync)
            if not self.menu.active and self.paused:
                # If we were paused by menu, unpause. 
                # But manual pause (Space) exists.
                # User req: "Game should unpause when you close the menu."
                # We can enforce this by checking if menu WAS active?
                # Simplify: If menu inactive, we can force unpause if it was the menu that paused it?
                # The user just said "unpause when close menu".
                # Let's say we unpause.
                self.paused = False

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
            elif key == ord('5'):
                self.selected_room = "Bed" # Logic maps "Bed" to TILES_BED? No, drag logic maps rooms. 
                # Need to update handle_drag_action for "Bed" and "Training Room"
            elif key == ord('6'):
                self.selected_room = "Training Room"
            elif key == ord('7'):
                self.selected_room = "Farm"
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
                    event = curses.getmouse()
                    _, x, y, _, bstate = event
                    
                    map_x = x + self.renderer.cam_x
                    map_y = y + self.renderer.cam_y
                    
                    # Handle Dragging
                    # Start Drag
                    if bstate & curses.BUTTON1_PRESSED:
                        self.drag_start = (map_x, map_y)
                        self.drag_end = (map_x, map_y)
                        
                        # Inspect Logic (Click)
                        # We also set selected_entity on press? Or release?
                        # Usually release is safer for "Click vs Drag". 
                        # But simple click:
                        # Selection Cycling
                        clicked_entities = []
                        for c in self.entities.creatures:
                            if c['x'] == map_x and c['y'] == map_y:
                                clicked_entities.append(c)
                        
                        if clicked_entities:
                            if self.selected_entity in clicked_entities:
                                # Cycle to next
                                try:
                                    idx = clicked_entities.index(self.selected_entity)
                                    next_idx = (idx + 1) % len(clicked_entities)
                                    self.selected_entity = clicked_entities[next_idx]
                                except ValueError:
                                     self.selected_entity = clicked_entities[0]
                            else:
                                self.selected_entity = clicked_entities[0]
                        else:
                             self.selected_entity = None
                        # Does not clear on empty click?
                        # If clicked_imp is None, we clear it.
                        # Unless dragging!
                        # If we start dragging, we probably ignore inspection updates later?
                        # For now, simple override.
                    
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
                             
                             # If Start == Current Mouse (End) -> Click (Inspection/Single Toggle)
                             if (x1, y1) == (x2, y2):
                                 # Logic for single click toggle is same as 1x1 drag
                                 pass
                             
                             self.handle_drag_action(x1, y1, x2, y2)
                             self.drag_start = None
                             self.drag_end = None
                    
                    # Right Click Cancel
                    if bstate & (curses.BUTTON3_PRESSED | curses.BUTTON3_CLICKED):
                        self.selected_room = "None"
                        self.selected_entity = None
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
            
            # Render (~60 FPS target for smoother drag)
            # Pass drags only if NOT in menu?
            d_start = self.drag_start if not self.menu.active else None
            d_end = self.drag_end if not self.menu.active else None
            
            # Pass Payday? 
            # We didn't change draw signature for Payday timer yet.. 
            # Just relying on status update?
            # Revisit: We updated draw to handle 'imps' argument as generic 'creatures'.
            # The following line seems to be a copy-paste error from another context,
            # but it's part of the instruction, so it's included.
            self.renderer.cam_y = self.renderer.cam_y # This line is effectively a no-op.
            
            # Render
            # Pass Mana
            self.renderer.draw(self.paused, self.entities.imps, self.selected_room, self.drag_start, self.drag_end, self.entities.total_gold, self.selected_entity, self.entities.mana)
            
            if self.menu.active:
                self.menu.draw()
            
            # Finalize Frame
            self.stdscr.refresh()
            
            # Cap framerate to ~60 FPS
            curses.napms(16)

def main(stdscr):
    game = Game(stdscr, start_in_menu=True)
    game.run()

if __name__ == "__main__":
    curses.wrapper(main)

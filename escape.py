import libtcodpy as libtcod
import math
import textwrap

SCREEN_WIDTH = 80
SCREEN_HEIGHT = 50

# Size of the map
MAP_WIDTH = 80
MAP_HEIGHT = 43

BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT
MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH  - 2
MSG_HEIGHT = PANEL_HEIGHT - 1

# Parameters for dungeon generator
ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6
MAX_ROOMS = 30
MAX_ROOM_MONSTERS = 3
MAX_ROOM_ITEMS = 2
INVENTORY_WIDTH = 50

# Items and effect
HEAL_AMOUNT = 4

FOV_ALGO = 0
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 10

LIMIT_FPS = 20

color_dark_wall = libtcod.Color(0, 0, 100)
color_dark_ground = libtcod.Color(50, 50, 150)
color_light_wall = libtcod.Color(130, 110, 50)
color_light_ground = libtcod.Color(200, 180, 50)

class Rect:
    # a rectangle on the map. Used to characterize a room.
    def __init__(self, x, y, w, h):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w
        self.y2 = y + h

    def center(self):
        center_x = (self.x1 + self.x2) / 2
        center_y = (self.y2 + self.y2) / 2
        return (center_x, center_y)

    def intersect(self, other):
        # Returns true if this rectangle intersects with another
        return (self.x1 <= other.x2 and self.x2 >= other.x1 and self.y1 <= other.y2 and self.y2 >= other.y1)

class Tile:
    # A tile of the map and its properties
    def __init__(self, blocked, block_sight = None):
        self.explored = False
        self.blocked = blocked
        # By default, if the tile is blocked, it also blocks sight
        if block_sight is None: block_sight = blocked 
        self.block_sight = block_sight

class Object:
    # This is a generic object: the player, a monster, an item, the stairs...
    # It's always represented by a character on screen.
    def __init__(self, x, y, char, color, name, blocks=False, fighter=None, ai=None, item=None):
        self.x = x
        self.y = y
        self.char = char
        self.color = color
        self.name = name
        self.blocks = blocks
        self.fighter = fighter
        if self.fighter: # Let the fighter component know who owns it
            self.fighter.owner = self

        self.ai = ai
        if self.ai: # Let the AI component know who owns it
            self.ai.owner = self

        self.item = item
        if self.item: # Let the item component know who owns it
            self.item.owner = self


    def move(self, dx, dy):
        if not is_blocked(self.x + dx, self.y + dy):
            # Move by the given amount
            self.x += dx
            self.y += dy

    def move_towards(self, target_x, target_y):
        # Vector from the object to the target and the distance
        dx = target_x - self.x
        dy = target_y - self.y
        distance = math.sqrt(dx ** 2 + dy ** 2)

        # Normalize it to the length 1 (preserving direction), then round it and
        # convert to integer so the movement is restricted to the map grid
        dx = int(round(dx / distance))
        dy = int(round(dy / distance))
        self.move(dx, dy)

    def distance_to(self, other):
        # return the distance to another object
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx ** 2 + dy ** 2)

    def draw(self):
        if libtcod.map_is_in_fov(fov_map, self.x, self.y):
            # Set the color and then draw the character that represents this object at its position.
            libtcod.console_set_default_foreground(con, self.color)
            libtcod.console_put_char(con, self.x, self.y, self.char, libtcod.BKGND_NONE)

    def clear(self):
        # Erase the character that represents this object
        libtcod.console_put_char(con, self.x, self.y, ' ', libtcod.BKGND_NONE)

    def send_to_back(self):
        # Make this object draw first so all other objects appear above it if they are on the same tile
        global objects
        objects.remove(self)
        objects.insert(0, self)

class Fighter:
    # Combat-related properties and methods (monster, player, NPC)
    def __init__(self, hp, defense, power, death_function=None):
        self.max_hp = hp
        self.hp = hp
        self.defense = defense
        self.power = power
        self.death_function = death_function

    def take_damage(self, damage):
        # Apply the damage taken
        if damage > 0:
            self.hp -= damage
            # Check for death, if there is a death_function call it
            if self.hp <= 0:
                function = self.death_function
                if function is not None:
                    function(self.owner)

    def attack(self, target):
        # Simple formula for attack damage
        damage = self.power - target.fighter.defense

        if damage > 0:
            # Make the target take some damage
            message(self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points!', libtcod.yellow)
            target.fighter.take_damage(damage)
        else:
            message(self.owner.name.capitalize() + ' attacks ' + target.name + ' but has no effect.')

    def heal(self, amount):
        # Heal by the given amount without going over the maximum
        self.hp += amount
        if self.hp > self.max_hp:
            self.hp = self.max_hp


class BasicMonster:
     # AI for basic monster
     def take_turn(self):
         # the basic monster takes its turn, if you can see it, it can see you
         monster = self.owner
         if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
            # Move towards the player if far away
            if monster.distance_to(player) >= 2:
                monster.move_towards(player.x, player.y)
                # Close enough attach if the player is alive
            elif player.fighter.hp > 0: 
                monster.fighter.attack(player)

class Item:
    def __init__(self, use_function=None):
        self.use_function = use_function

    # An item that can be picked up and used
    def pick_up(self):
        # Add to the players inventory and remove from the map
        if len(inventory) >= 26:
            message('Your inventory is full, cannot pick up ' + self.owner.name + '.', libtcod.red)
        else:
            inventory.append(self.owner)
            objects.remove(self.owner)
            message('You picked up a ' + self.owner.name + '!', libtcod.green)

    def use(self):
        # Just call the use_function if it is defined
        if self.use_function is None:
            message('The ' + self.owner.name + ' cannot be used.')
        else:
            if self.use_function != 'cancelled':
                inventory.remove(self.owner) # Destroy after use unless it was cancelled for some reason

def cast_heal():
    # Heal the player
    if player.fighter.hp == player.fighter.max_hp:
        message('You are already at full health.', libtcod.red)
        return 'cancelled'

    message('Your wonds begin to heal!', libtcod.light_violet)
    player.fighter.heal(HEAL_AMOUNT)


def message(new_msg, color = libtcod.white):
    # Split messages if neccessary among multiple lines
    new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)

    for line in new_msg_lines:
        # If the buffer is full, remove the first line to make room for the new one
        if len(game_msgs) == MSG_HEIGHT:
            del game_msgs[0]

        # Add new line as tuple, with the text and color
        game_msgs.append( (line, color) )

def player_death(player):
    # the game ends
    global game_state
    message('You died!', libtcod.red)
    game_state = 'dead'

    # For added effect transform the player into a corpse
    player.char = '%'
    player.color = libtcod.dark_red

def monster_death(monster):
     # transform it into a nasty corpse it dosent block move or attack
     message(monster.name.capitalize() + ' is dead!', libtcod.orange)
     monster.char = '%'
     monster.color = libtcod.dark_red
     monster.blocks = False
     monster.fighter = None
     monster.ai = None
     monster.send_to_back()
     monster.name = 'Remains of ' + monster.name

def is_blocked(x, y):

    # First test the map tile
    if map[x][y].blocked:
        return True

    # Now check for any blocking objects
    for object in objects:
        if object.blocks and object.x == x and object.y == y:
            return True

    return False

def create_room(room):
    global map
    # Go throu the tiles in the rectangle and make them passable
    for x in range(room.x1 + 1, room.x2):
        for y in range(room.y1 + 1, room.y2):
            map[x][y].blocked = False
            map[x][y].block_sight = False

def create_h_tunnel(x1, x2, y):
    global map
    for x in range(min(x1, x2), max(x1, x2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False

def create_v_tunnel(y1, y2, x):
    global map
    # Vertical tunnel
    for y in range(min(y1, y2), max(y1, y2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False

def place_objects(room):
    # Choose a random number of monsters
    num_monsters = libtcod.random_get_int(0, 0, MAX_ROOM_MONSTERS)

    for i in range(num_monsters):
        # Choose random spot for this monsert
        x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
        y = libtcod.random_get_int(0, room.y1+1, room.y2-1)

        if not is_blocked(x, y):
            if libtcod.random_get_int(0, 0, 100) < 80: # 80 percent chance of getting an orc
                # Create an orc
                fighter_component = Fighter(hp=10, defense=0, power=3, death_function=monster_death)
                ai_component = BasicMonster()
                monster = Object(x, y, 'o', libtcod.desaturated_green, 'Orc', blocks=True, fighter=fighter_component, ai=ai_component)
            else:
                # Create a troll
                fighter_component = Fighter(hp=16, defense=1, power=4, death_function=monster_death)
                ai_component = BasicMonster()
                monster = Object(x, y, 'T', libtcod.darker_green, 'Troll', blocks=True, fighter=fighter_component, ai=ai_component)

            objects.append(monster)

    # Choose random number of room items
    num_items = libtcod.random_get_int(0, 0, MAX_ROOM_ITEMS)

    for i in range(num_items):
        # Choose random spot for this item
        x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
        y = libtcod.random_get_int(0, room.y1+1, room.y2-1)

        # Only place it if the tile is not blocked
        if not is_blocked(x, y):
            # Create a healing potion
            item_component = Item(use_function=cast_heal)
            item = Object(x, y, '!', libtcod.violet, 'Healing Potion', item=item_component)

            objects.append(item)
            item.send_to_back() #items appear below other objects


def make_map():
    global map, player
    
    # Fill map with "blocked" tiles
    map = [[ Tile(True)
        for y in range(MAP_HEIGHT) ]
            for x in range(MAP_WIDTH) ]
    rooms = []
    num_rooms = 0

    for r in range(MAX_ROOMS):
        # Random width and height
        w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        # Random position without going out of the boundaries of the map
        x = libtcod.random_get_int(0, 0, MAP_WIDTH - w -1)
        y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)

        # Rect class makes rectangles easier to work with
        new_room = Rect(x, y, w, h)

        # Run through the other rooms and see if they intersect with this one
        failed = False
        for other_room in rooms:
            if new_room.intersect(other_room):
                failed = True;
                break

        if not failed:
            # This means there are no intersections so this room is valid

            # Paint it to the maps tile
            create_room(new_room)

            # Add monsters
            place_objects(new_room)

            # Center coordinates of new room, will be usefull later
            (new_x, new_y) = new_room.center()

            if num_rooms == 0:
                # this is the first room, where the player starts
                player.x = new_x
                player.y = new_y
            else:
                # All rooms after the first
                # Connect it to the previous room with a tunnel

                # Center coordinates of previous room
                (prev_x, prev_y) = rooms[num_rooms - 1].center()

                # Draw a coin (random number that is either 0 or 1)
                if libtcod.random_get_int(0, 0, 1) == 1:
                    # First move horizontally then vertially
                    create_h_tunnel(prev_x, new_x, prev_y)
                    create_v_tunnel(prev_y, new_y, prev_x)
                else:
                    create_v_tunnel(prev_y, new_y, prev_x)
                    create_h_tunnel(prev_x, new_x, prev_y)

            # Finally append the new room to the list
            rooms.append(new_room)
            num_rooms += 1

def render_all():
    global color_light_wall, color_light_ground
    global color_dark_ground, color_dark_wall
    global fov_map, fov_recompute

    if fov_recompute:
        # Recompute of the FOV is needed
        fov_recompute = False
        libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)

        # Go through all tiles, and set their background color
        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                visible = libtcod.map_is_in_fov(fov_map, x, y)
                wall = map[x][y].block_sight
                if not visible:
                    # If it's not visible right now. The player can only see it if it is eplored
                    if map[x][y].explored:
                        if wall:
                            libtcod.console_set_char_background(con, x, y, color_dark_wall, libtcod.BKGND_SET)
                        else:
                            libtcod.console_set_char_background(con, x, y, color_dark_ground, libtcod.BKGND_SET)
                else:
                    if wall:
                        libtcod.console_set_char_background(con, x, y, color_light_wall, libtcod.BKGND_SET)
                    else:
                        libtcod.console_set_char_background(con, x, y, color_light_ground, libtcod.BKGND_SET)
                        # Since it is visible explore it
                        map[x][y].explored = True
    # Draw all objects in the list
    for object in objects:
        if object != player:
            object.draw()
    player.draw()

    # Blit the contents to the root console
    libtcod.console_blit(con, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0, 0, 0)
    
    # Prepare to render the GUI panel
    libtcod.console_set_default_background(panel, libtcod.black)
    libtcod.console_clear(panel)
    
    # print game messages one line at a time
    y = 1
    for (line, color) in game_msgs:
        libtcod.console_set_default_foreground(panel, color)
        libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
        y += 1
    
    # Show the players stats
    render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp, libtcod.light_red, libtcod.darker_red)

    # Display names of objects under the mouse
    libtcod.console_set_default_foreground(panel, libtcod.light_gray)
    libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT, get_names_under_mouse())

    # Blit the contents of panel to the root console
    libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)

def player_move_or_attack(dx, dy):
    global fov_recompute

    # The coordinates the player is moving to/attacking
    x = player.x + dx
    y = player.y + dy

    # Try to find the attackable object
    target = None
    for object in objects:
        if object.fighter and object.x == x and object.y == y:
            target = object
            break

    # Attack if object found, move if not
    if target is not None:
        player.fighter.attack(target) 
    else:
        player.move(dx, dy)
        fov_recompute = True

def get_names_under_mouse():
    global mouse;
    (x,y) = (mouse.cx, mouse.cy)
    # Create a list of all objects all the mouses position and in the player FOV
    names = [obj.name for obj in objects
            if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]
    names = ', '.join(names) # join names seperated by comma
    return names.capitalize()

def handle_keys():
    global fov_recompute, keys

    #key = libtcod.console_check_for_keypress() # real time
    #key = libtcod.console_wait_for_keypress(True) # for turn based
    if key.vk == libtcod.KEY_ENTER and key.lalt:
        # Alt+Enter toggle fullscreen
        libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
    elif key.vk == libtcod.KEY_ESCAPE:
        return 'exit' #exit game
    if game_state == 'playing':
        #movement keys
        if key.vk == libtcod.KEY_UP or key.c == ord('w'):
            #player.move(0, -1)
            player_move_or_attack(0, -1)
            #fov_recompute = True
        elif key.vk == libtcod.KEY_DOWN or key.c == ord('s'):
            player_move_or_attack(0, 1)
            #player.move(0, 1)
            #fov_recompute = True
        elif key.vk == libtcod.KEY_LEFT or key.c == ord('a'):
            player_move_or_attack(-1, 0)
            #player.move(-1, 0)
            #fov_recompute = True
        elif key.vk == libtcod.KEY_RIGHT or key.c == ord('d'):
            player_move_or_attack(1, 0)
            #player.move(1, 0)
            #fov_recompute = True
        else:
            # Test for other keys
            key_char = chr(key.c)

            if key_char == 'g':
                # Pick up an item
                for object in objects: # Look for an item in the players tile
                    if object.x == player.x and object.y == player.y and object.item:
                        object.item.pick_up()
                        break
            if key_char == 'i':
                # Show the inventory
                chosen_item = inventory_menu("Press the key next to an item to use it, or any other key to cancel.\n")
                if chosen_item is not None:
                    chosen_item.use()
            return 'didnt-take-turn'

def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
    # Render a bar (HP, experience, etc) first calculate the width of the bar
    bar_width = int(float(value) / maximum * total_width)

    # Render the background first
    libtcod.console_set_default_background(panel, back_color)
    libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)

    # Now render the bar on top
    libtcod.console_set_default_background(panel, bar_color)
    if bar_width > 0:
        libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)

    # Finaly some centered text with values
    libtcod.console_set_default_foreground(panel, libtcod.white)
    libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE, libtcod.CENTER, name + ': ' + str(value) + '/' + str(maximum))

def menu(header, options, width):
    if len(options) > 26:
        raise ValueError('Cannot have a menu with more than 26 options')

    # Calculate the total height for the header (after auto-wrap) and one line per option
    header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
    height = len(options) + header_height

    # Create an offscreen console that represents the menu's window
    window = libtcod.console_new(width, height)

    # Print the header, with auto-wrap
    libtcod.console_set_default_foreground(window, libtcod.white)
    libtcod.console_print_rect_ex(window, 0, 0, width, height, libtcod.BKGND_NONE, libtcod.LEFT, header)

    # Print all options
    y = header_height
    letter_index = ord('a')
    for option_text in options:
        text = '(' + chr(letter_index) + ') ' + option_text
        libtcod.console_print_ex(window, 0, y, libtcod.BKGND_NONE, libtcod.LEFT, text)
        y += 1
        letter_index += 1

    # Blit the contents of 'window' to the root console
    x = SCREEN_WIDTH/2 - width/2
    y = SCREEN_HEIGHT/2 - height/2
    libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 0.7)

    # Present the root console to the player and wait for a key press
    libtcod.console_flush()
    key = libtcod.console_wait_for_keypress(True)

    # Convert the ASCII code to an index: if it corrisponds to an option, return it
    index = key.c - ord('a')
    if index >= 0 and index < len(options):
        return index

    return None

def inventory_menu(header):
    # Show a menu with each item of the inventory as an option
    if len(inventory) == 0:
        options = ['Inventory is Empty']
    else:
        options = [item.name for item in inventory]

    index = menu(header, options, INVENTORY_WIDTH)

    #If an item was chosen return it
    if index is None or len(inventory) == 0:
        return None
    return inventory[index].item

#################################################
# GAME LOOP
#################################################
libtcod.console_set_custom_font('arial10x10.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_TCOD)
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'Escape', False)
libtcod.sys_set_fps(LIMIT_FPS)
con = libtcod.console_new(SCREEN_WIDTH, SCREEN_HEIGHT)
panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)

# The Player.
#player = Object(SCREEN_WIDTH/2, SCREEN_HEIGHT/2, '@', libtcod.white)
fighter_component = Fighter(hp=30, defense=2, power=5, death_function=player_death)
player = Object(0, 0, '@', libtcod.white, 'player', blocks=True, fighter=fighter_component)
# The NPC
#npc = Object(SCREEN_WIDTH/2 - 5, SCREEN_HEIGHT/2, '@', libtcod.yellow)
# Game objects
objects = [player]
# Generate map
make_map()

fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
fov_recompute = True
for y in range(MAP_HEIGHT):
    for x in range(MAP_WIDTH):
        libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)

fov_recompute = True
game_state = 'playing'
player_action = None

# Create a list of game messages and thier colors, starts empty
game_msgs = []

message('Welcome stranger! Prepare to perish in the Tombs of the Ancient Kings.', libtcod.red)
mouse = libtcod.Mouse()
key = libtcod.Key()

inventory = []

# Main Loop
while not libtcod.console_is_window_closed():
    libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)
    # Render the screen
    render_all()

    libtcod.console_flush()

    # Erase all objects at their old positions, before they move
    for object in objects:
        object.clear()

    # Handle keys and exit the game if needed.
    player_action = handle_keys()
    if player_action == 'exit':
        break

    if game_state == 'playing' and player_action != 'didnt-take-turn':
        for object in objects:
            if object.ai:
                object.ai.take_turn()



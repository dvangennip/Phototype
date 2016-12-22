import pygame
from pygame.locals import *
import ft5406

ts = ft5406.Touchscreen()

global gui_font, screen, display_size, do_exit, message, colors

do_exit = False
gui_font = None
display_size = (800, 480)
message = ""

colors = {
	'white':   pygame.Color(255, 255, 255),
	'black':   pygame.Color(  0,   0,   0),
	'support': pygame.Color( 60,   0,   0)
}

def handle_input ():
	global display_size, do_exit, message

	for touch in ts.poll():
		# touch.slot, touch.id, touch.valid, touch.x, touch.y
		if (touch.slot == 0):
			message = 'slot: ' + str(touch.slot) +', id: '+ str(touch.id) +', valid: '+ str(touch.valid) +', x: '+ str(touch.x) +', y: '+ str(touch.y)

	# handle event queue
	events = pygame.event.get()
	for event in events:
		if (event.type is KEYDOWN):
			if (event.key == K_ESCAPE):
				do_exit = True
			else:
				message = 'key: ' + str(event.key)


def gui_init ():
	global gui_font, screen
	
	pygame.init()
	pygame.mouse.set_visible(False)
	gui_font = pygame.font.Font('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 16)
	screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
	gui_draw()


# Draws the GUI by calling specific methods for each mode.
def gui_draw ():
	global screen, message

	screen.fill(colors['support'])
	pygame.display.update()


# Draws message in middle of display
# note: should be called directly when state changes for immediate feedback
# @message: should be convertible to string
def gui_draw_message ():
	global screen, gui_update, display_size, message

	# draw background
	message_bg_surface = pygame.Surface( (300, 30) )
	message_bg_surface.fill(colors['support'])
	message_bg_rect = message_bg_surface.get_rect()
	message_bg_rect.centerx = display_size[0]/2
	message_bg_rect.centery = display_size[1]/2 - 30
	screen.blit(message_bg_surface, message_bg_rect)

	# draw text to indicate preview is on, otherwise leave blank
	if (message is not None):
		state_text_surface = gui_font.render(str(message), False, colors['white'])
		state_text_rect = state_text_surface.get_rect()
		state_text_rect.centerx = display_size[0]/2
		state_text_rect.centery = display_size[1]/2 - 30
		screen.blit(state_text_surface, state_text_rect)

	# immediately update display (just affected rectangle)
	pygame.display.update(message_bg_rect)


# MAIN ------------------------------------------------------------------------


"""Unless this script is imported, do the following"""
if __name__ == '__main__':
	# initialise all components
	gui_init()

	# program stays in this loop unless called for exit
	while (True):
		# checking input
		handle_input()

		# drawing GUI
		gui_draw_message()

		# exit flag set?
		if (do_exit):
			break
		else:
			# pause between frames
			pygame.time.wait(50)

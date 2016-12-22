import os
import pygame
from pygame.locals import *

global colors, images, input_folder, screen, gui_font, current_image, do_exit

display_size = (800, 480)

colors = {
	'white':   pygame.Color(255, 255, 255),
	'black':   pygame.Color(  0,   0,   0),
	'support': pygame.Color( 60,   0,   0)
}

images = []
input_folder = '../DCIM/'

current_image = {
	'index': 99999,     # very high number, so after limiting always picks latest image
	'index_loaded': -1, # non-plausible number
	'filename': None,
	'img': None,        # pygame surface (original resolution)
	'img_scaled': None, # pygame surface (based on scaled img)
}

do_exit = False

def init():
	global screen, gui_font

	pygame.init()
	pygame.mouse.set_visible(False)
	gui_font = pygame.font.Font('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 16)
	screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)

def handle_input ():
	global do_exit

	# handle event queue
	events = pygame.event.get()
	for event in events:
		if (event.type is KEYDOWN):
			if (event.key == K_ESCAPE):
				do_exit = True
			elif (event.key == K_LEFT):
				set_current_image(-1)
			elif (event.key == K_RIGHT):
				set_current_image(1)

# --- Image viewing functions ----------------------------------

def load_images_list ():
	global images, current_image, input_folder

	images = []  # reset first
	for file in os.listdir(input_folder):
		if (file.endswith('.jpg')):
			images.append(file)
	images.sort()

	# in case an image was deleted, make sure current_image is not out of bounds
	current_image['index'] = min(max(current_image['index'], 0), len(images)-1)


# n gives direction (-1: earlier image, 1: next image)
def set_current_image (n=0):
	global current_image, images
	if (n != 0):
		current_image['index'] = min(max(current_image['index'] + n, 0), len(images)-1)

def gui_draw():
	global screen
	
	# refresh full display
	screen.fill(colors['black'])
	gui_draw_image()
	pygame.display.update()

def gui_draw_image ():
	global input_folder, images, current_image, display_size

	if (len(images) == 0):
		gui_draw_message("( no images available )")
	else:
		print("draw_image")
		# load image if necesary
		if (current_image['index'] != current_image['index_loaded']):
			# indicate progress
			gui_draw_message("( loading image )")

			# load image from file
			current_image['filename'] = input_folder + images[current_image['index']]
			current_image['img'] = pygame.image.load( current_image['filename'] )
			current_image['index_loaded'] = current_image['index']

			# draw current image as background
			current_image['img_scaled'] = aspect_scale(current_image['img'], display_size)

		# if necessary letterbox an image that does not fit on display
		screen.blit(current_image['img_scaled'],
			((display_size[0] - current_image['img_scaled'].get_width() ) / 2,
			 (display_size[1] - current_image['img_scaled'].get_height()) / 2))

# via: http://www.pygame.org/pcr/transform_scale/
def aspect_scale(img, box_size, fast=False):
	""" Scales 'img' to fit into box bx/by.
	This method will retain the original image's aspect ratio """
	ix,iy = img.get_size()
	bx,by = box_size

	if ix > iy:
		# fit to width
		scale_factor = bx/float(ix)
		sy = scale_factor * iy
		if sy > by:
			scale_factor = by/float(iy)
			sx = scale_factor * ix
			sy = by
		else:
			sx = bx
	else:
		# fit to height
		scale_factor = by/float(iy)
		sx = scale_factor * ix
		if sx > bx:
			scale_factor = bx/float(ix)
			sx = bx
			sy = scale_factor * iy
		else:
			sy = by

	if (fast is True):
		return pygame.transform.scale(img, (int(sx), int(sy)))
	return pygame.transform.smoothscale(img, (int(sx), int(sy)))

# Draws message in middle of display
# note: should be called directly when state changes for immediate feedback
# @message: should be convertible to string
def gui_draw_message (message=None):
	global screen, display_size

	# draw background
	message_bg_surface = pygame.Surface( (300, 30) )
	message_bg_surface.fill(colors['black'])
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
	load_images_list()

	init()

	while (True):
		handle_input()
		gui_draw()
		if (do_exit):
			break
		else:
			pygame.time.wait(50)

add_library('pdf')
import os
import pickle
import time

#hint(ENABLE_NATIVE_FONTS)

global data, data_folder, time_factor, max_time, max_interactions, use_pdf, font, all_actions

data_folder      = '/Users/dvangennip/Dropbox/Academic/MM/Study 4 - Longitudinal/S4 Data'
data             = []
all_actions      = []
max_time         = 0
time_factor      = 1
max_interactions = 1
use_pdf          = False
font             = None

def settings ():
    global use_pdf
    
    if (use_pdf):
        size(2500, 1240, PDF, os.path.join(data_folder, 'S4-data-visual.pdf'))
    else:
        size(2500, 1240)

def setup ():
    global data, data_folder, time_factor, max_time, max_interactions, font, all_actions
    
    colorMode(HSB, 100)
    background(0,0,100)

    # import data for all participants
    for p in range(1,12):
        data_path = os.path.join(data_folder, 'p' + str(p), 'p'+str(p)+'_data_processed.bin')
        participant_data = {
            'participant'     : p,
            'program_history' : [],
            'interactions'    : [],
            'images_simple'   : [],
            'counts'          : {}  # max_interactions, plus each action type
        }
        if os.path.exists(data_path):
            try:
                with open(data_path, 'rb') as f:
                    loaded_data = pickle.load(f)
                    for key in participant_data:
                        if (key in loaded_data):
                            participant_data[key] = loaded_data[key]
                    data.append(participant_data)
                    
                    if (loaded_data['counts']['max_interactions'] > max_interactions):
                        max_interactions = loaded_data['counts']['max_interactions'] 
            except IOError as eio:
                pass  # called when file doesn't exist (yet), which is fine
            except Exception as e:
                raise e
        
        # update the maximum timestamp found
        for ph in participant_data['program_history']:
            t_end = ph['timestamp'] + ph['duration']
            if (t_end > max_time):
                max_time = t_end
                print(p, t_end)
        
    # combine all actions into one list and sort by timestamp
    #   making one list avoids issues with later participants overdrawing
    #   earlier participant data and visually skewing graphics
    for pp in data:
        all_actions.extend(pp['interactions'])
    all_actions = sorted(all_actions, key=lambda k: k['timestamp'])
    
    # calculate time factor
    time_factor = 1.0 / max_time * (width - 50 - 10)  # width - x_offset - some margin
    
    # init fonts
    font = createFont("SourceSansPro-Regular", 18, True)
    textMode(SHAPE)
    
def draw ():
    global data, time_factor, max_time, max_interactions, use_pdf, font, all_actions
    x_offset   = 50
    y_offset   = 50
    y_stepsize = 100
    
    rectMode(CORNER)
    ellipseMode(CENTER)
    
    # first draw labels and lines, for visuals to draw on top
    
    # add lines per week
    week_width  = (7 * 24 * 60 * 60) * time_factor
    line_height = (len(data) + 1) * y_stepsize  # +1 for the all data row at the end
    stroke(0,0,90)  # grey
    strokeWeight(3)
    strokeCap(ROUND)
    
    line(x_offset,    line_height-50, x_offset,                line_height-5)
    line(x_offset +   week_width, 10, x_offset +   week_width, line_height-5)
    line(x_offset + 2*week_width, 10, x_offset + 2*week_width, line_height-5)
    line(x_offset + 3*week_width, 10, x_offset + 3*week_width, line_height-5)
    line(x_offset + 4*week_width, 10, x_offset + 4*week_width, line_height-5)
    line(x_offset + 5*week_width, 10, x_offset + 5*week_width, line_height-5)
    
    # add labels per line
    fill(0,0,70)  # grey
    textAlign(CENTER)
    textFont(font, 14)
    text('0w', x_offset,                line_height+15)
    text('1w', x_offset +   week_width, line_height+15)
    text('2w', x_offset + 2*week_width, line_height+15)
    text('3w', x_offset + 3*week_width, line_height+15)
    text('4w', x_offset + 4*week_width, line_height+15)
    text('5w', x_offset + 5*week_width, line_height+15)
    
    # draw visuals per participant
    for p in data:
        noStroke()
        
        # add participant number
        fill(0,0,0)  # black
        textAlign(CENTER)
        textFont(font, 18)
        text(str(p['participant']), 22, y_offset + 5)
        
        # lay programs as background (colour coded)
        for ph in p['program_history']:
            x_start  = ph['timestamp'] * time_factor
            x_width  = ph['duration'] * time_factor
            y_factor = constrain(log(float(ph['interactions']) / float(0.25*max_interactions) + 0.1) / log(10) + 1, 0, 1)
            y_height = 60 + (20 * y_factor)
            hsb_saturation = 25
            
            # determine whether program was active at night or day
            midtime = time.localtime( ph['start'] + ph['duration']/2 )  # use actual unix timestamp in 'start'
            if (midtime.tm_hour < 6):
                hsb_saturation = 8
            
            # change colour based on type
            if (ph['name'] == 'DualDisplay'):
                fill(30, hsb_saturation, 100)  # green
            elif (ph['name'] == 'PhotoSoup'):
                fill(15, hsb_saturation, 100)  # yellow
            else:
                noFill()  # nothing gets drawn in combination with noStroke
                
            rect(x_start + x_offset, y_offset - y_height/2, x_width, y_height)
        
        # add in interactions on top (ps.flung, dd.rate, touches, images.scan)
        for ix in p['interactions']:
            x_point = ix['timestamp'] * time_factor
            if (ix['action'] == 'dd.rate'):
                fill(53, 75, 75)  # blue
            elif (ix['action'] == 'ps.flung'):
                fill(100, 75, 75)  # magenta
            else:
                fill(75, 75, 75)  # purple
            ellipse(x_point + x_offset, y_offset + random(-25,25), 5, 5)
        
        # 
        
        # adjust offset for next iteration
        y_offset += y_stepsize
    
    # draw activity over time across all participants
    fill(0,0,0)
    text('all', 22, y_offset + 5)
    for act in all_actions:
        x_point = act['timestamp'] * time_factor
        if (act['action'] == 'dd.rate'):
            fill(53, 75, 75)  # blue
        elif (act['action'] == 'ps.flung'):
            fill(100, 75, 75)  # magenta
        else:
            fill(75, 75, 75)  # purple
        # draw the points with some randomness to their position to avoid overlap
        ellipse(x_point + x_offset + 2*randomGaussian(), y_offset + 10*randomGaussian(), 5, 5)
    
    # no need to redraw
    noLoop()
    if (use_pdf):
        exit()
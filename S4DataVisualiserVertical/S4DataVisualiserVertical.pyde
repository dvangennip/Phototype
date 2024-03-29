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
participant_list = [1,2,3,4,5,6,7,8,9,10,11,51,52,53]

def settings ():
    global use_pdf
    
    if (use_pdf):
        size(1300, 1600, PDF, os.path.join(data_folder, 'S4-data-visual.pdf'))
    else:
        size(1300, 1600)

def setup ():
    global data, data_folder, time_factor, max_time, max_interactions, font, all_actions
    
    colorMode(HSB, 100)
    background(0,0,100)

    # import data for all participants
    for p in participant_list:
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
                #print(p, t_end)
        
    # combine all actions into one list and sort by timestamp
    #   making one list avoids issues with later participants overdrawing
    #   earlier participant data and visually skewing graphics
    for pp in data:
        all_actions.extend(pp['interactions'])
    all_actions = sorted(all_actions, key=lambda k: k['timestamp'])
    
    # calculate time factor
    time_factor = 1.0 / max_time * (height - 50 - 10)  # width - y_offset - some margin
    
    # init fonts
    font = createFont("SourceSansPro-Regular", 24, True)
    textMode(SHAPE)
    
def draw ():
    global data, time_factor, max_time, max_interactions, use_pdf, font, all_actions
    y_offset   = 50
    x_offset   = 100
    x_stepsize = 80
    
    activities = {}
    
    rectMode(CORNER)
    ellipseMode(CENTER)
    
    # first draw labels and lines, for visuals to draw on top
    
    # add lines per week
    week_height = (7 * 24 * 60 * 60) * time_factor
    line_width  = (len(data) + 1) * x_stepsize  # +1 for the all data row at the end
    # print(line_width)
    weeks       = int(max_time / (3600 * 24 * 7))
    
    for w in range(0,weeks+1):
        stroke(0,0,80)  # grey
        strokeWeight(1.5)
        strokeCap(ROUND)
        line(x_offset-55, y_offset + w*week_height, x_offset + line_width-30, y_offset + w*week_height)
        
        # add labels per line
        fill(0,0,40)  # grey
        textAlign(CENTER)
        textFont(font, 24)
        text(str(w) + 'w', x_offset-80, y_offset + w*week_height + 5)
    
    # draw visuals per participant
    for p in data:
        noStroke()
        
        # add participant number
        fill(0,0,0)  # black
        textAlign(CENTER)
        textFont(font, 24)
        text('P' + str(p['participant']), x_offset, 29)
        
        # lay programs as background (colour coded)
        for ph in p['program_history']:
            draw_bar = True
            y_start  = ph['timestamp'] * time_factor
            y_height = ph['duration'] * time_factor
            x_factor = constrain(log(float(ph['interactions']) / float(0.25*max_interactions) + 0.1) / log(10) + 1, 0, 1)
            x_width = 0.6 * x_stepsize + (0.2 * x_stepsize * x_factor)
            hsb_saturation = 25
            
            # determine whether program was active at night or day
            midtime = time.localtime( ph['start'] + ph['duration']/2 )  # use actual unix timestamp in 'start'
            if (midtime.tm_hour < 6):
                draw_bar = False
                hsb_saturation = 8
            
            # change colour based on type
            if (draw_bar):
                if (ph['name'] == 'DualDisplay'):
                    fill(30, hsb_saturation, 100)  # green
                elif (ph['name'] == 'PhotoSoup'):
                    fill(15, hsb_saturation, 100)  # yellow
                elif (ph['name'] == 'PhotoPatterns'):
                    fill(50, hsb_saturation, 100)  # cyan
                else:
                    noFill()  # nothing gets drawn in combination with noStroke
                
                rect(x_offset - x_width/2, y_start + y_offset, x_width, y_height)
        
        # add in interactions on top (ps.flung, dd.rate, touches, images.scan)
        for ix in p['interactions']:
            y_point = ix['timestamp'] * time_factor
            if (ix['action'] == 'dd.rate'):
                fill(53, 75, 75)  # blue
            elif (ix['action'] == 'ps.flung'):
                fill(100, 75, 75)  # magenta
            elif (ix['action'] == 'pp.pick'):
                fill(75, 75, 75)  # purple
            else:
                fill(0, 0, 75)  # grey
            ellipse(x_offset + random(-25,25), y_point + y_offset, 5, 5)
        
        # adjust offset for next iteration
        x_offset += x_stepsize
    
    # draw activity over time across all participants
    fill(0,0,0)
    text('all', x_offset, 29)
    for act in all_actions:
        y_point = act['timestamp'] * time_factor
        if (act['action'] == 'dd.rate'):
            fill(53, 75, 75)  # blue
        elif (act['action'] == 'ps.flung'):
            fill(100, 75, 75)  # magenta
        elif (ix['action'] == 'pp.pick'):
                fill(75, 75, 75)  # purple
        else:
            if not (act['action'] in activities):
                activities[act['action']] = True
            fill(0, 0, 75)  # grey
        # draw the points with some randomness to their position to avoid overlap
        ellipse(x_offset + 0.1*x_stepsize*randomGaussian(), y_point + y_offset + 2*randomGaussian(), 5, 5)
    
    # show all unhandled activities
    # print(activities)
    
    # no need to redraw
    noLoop()
    if (use_pdf):
        exit()

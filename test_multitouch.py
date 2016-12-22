from ft5406 import Touchscreen, TS_PRESS, TS_RELEASE, TS_MOVE

ts = Touchscreen()

def touch_handler(event, touch):
    touch_info = '(slot: ' + str(touch.slot) +', id: '+ str(touch.id) +', valid: '+ str(touch.valid) +', x: '+ str(touch.x) +', y: '+ str(touch.y) +')'
    if event == TS_PRESS:
        print("PRESS",   touch, touch_info)
    if event == TS_RELEASE:
        print("RELEASE", touch, touch_info)
    if event == TS_MOVE:
        print("MOVE",    touch, touch_info)

for touch in ts.touches:
    touch.on_press = touch_handler
    touch.on_release = touch_handler
    touch.on_move = touch_handler

ts.run()

while True:
    # Redraw Code etc
    try:
        pass
    except KeyboardInterrupt:
        ts.stop()
        exit()
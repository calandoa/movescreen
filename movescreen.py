#!/usr/bin/env python

# This script is used to move windows accross monitors, if the window manager
# does not provide any shortcut.
#
# Written by Antoine Calando / 2017 - Public domain

import subprocess
import re
import sys

arg_str = [ "up", "down", "left", "right" ]
if len(sys.argv) < 2 or sys.argv[1] not in arg_str:
	print("usage: %s <left|right|up|down> [win_id]" % sys.argv[0])
	exit(-1)
arg = sys.argv[1]

# Get screens information
# scr will store a list of list: [ [ width height offset_x offset_y ] ... ]
out = subprocess.check_output(['xrandr']).decode('ascii', 'ignore')
reg = re.compile(" connected( primary)? ([0-9]+)x([0-9]+)\+([0-9]+)\+([0-9]+)")
scr = []
for l in out.splitlines():
	m = reg.search(l)
	if m:
		scr += [ list(map(int, m.groups()[1:])) ]

if 2 < len(sys.argv):
	# Get window id from argument
	id = sys.argv[2]
else:
	# Get focused window
	out = subprocess.check_output(['xprop', '-root', '_NET_ACTIVE_WINDOW']).decode('ascii', 'ignore')
	id = re.search("window id # (0x[0-9a-f]+),", out).group(1)

# Get info on focused window,
out = subprocess.check_output(['xwininfo', '-id', id, '-all']).decode('ascii', 'ignore')
geo_str = ( "Width:", "Height:",
	"Absolute upper-left X:", "Absolute upper-left Y:",
	"Relative upper-left X:", "Relative upper-left Y:", "")
state_str = ("Maximized Vert", "Maximized Horz", "Fullscreen", )
geo = {}
state = []

# Replace each geo elem with matching int, add states/types in state, converted for wmctrl
for l in out.splitlines():
	l = l.strip()
	idx = next(i for i, s in enumerate(geo_str) if l.startswith(s))
	if geo_str[idx] != "":
		geo[idx] = int(l.split()[-1])
	elif l in state_str:
		state += [l.lower().replace(' ', '_')]
	elif l == "Desktop":
		# Top level window
		sys.exit(-2)

def isect_area(a, b):
	# Compute top left and bottom right coords in scr format: [w h x y]
	tlx = max(a[2], b[2])
	tly = max(a[3], b[3])
	brx = min(a[2] + a[0], b[2] + b[0])
	bry = min(a[3] + a[1], b[3] + b[1])
	return max (0, brx - tlx) * max (0, bry - tly)

# r will hold a dict of how screens are disposed between themselves, using their idx
# e.g. if scr 0 is at left of 1, then d[left][1] == 0 and d[right][0] == 1
r = { a : [ None ] * len(scr) for a in arg_str  }

for ia, sa in enumerate(scr):
	for ib, sb in enumerate(scr):
		if sa != sb:
			# Duplicate screen on right then bottom, and check intersection
			# Using the max of interection area would be better
			if isect_area([sa[0], sa[1], sa[2] + sa[0], sa[3]], sb):
				r["right"][ia] = ib
				r["left"][ib] = ia

			if isect_area([sa[0], sa[1], sa[2], sa[3] + sa[1]], sb):
				r["bottom"][ia] = ib
				r["top"][ib] = ia

# Find screen of active window from the max area
areas = list(map(lambda s : isect_area(geo, s), scr))
try:
	sidx = areas.index(max(areas + [1]))
except ValueError:
	exit(-3)

# other screen in this direction?
nscr = r[arg][sidx]
if nscr is None:
	exit(-4)

# x/y offset from "tOp" or "bOttom" check
x_y = int(arg[1] == 'o')

# Get the new coordinates
npos = [geo[2] - geo[4], geo[3] - geo[5]]
npos[x_y] += scr[nscr][2 + x_y] - scr[sidx][2 + x_y]

# Execute move command, preserving the states
def wmctrl(id, ops):
	for op in ops:
		cmd = ['wmctrl', '-i', '-r', id ] + op
		subprocess.call(cmd)

# wmctrl very pernickety with -b argument, 'add' not really working and 2 props max
wmctrl(id, [['-b', 'toggle,' + s] for s in state])
wmctrl(id, [['-e', '0,%d,%d,-1,-1' % tuple(npos)]])
wmctrl(id, [['-b', 'toggle,' + s] for s in state])


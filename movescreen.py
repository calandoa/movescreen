#!/usr/bin/env python

# This script is used to move windows accross monitors, if the window manager
# does not provide any shortcut.
#
# Written by Antoine Calando / 2017 - Public domain

import subprocess
import re
import sys

# Parse arguments
# ==============
ratio = False
if 1 < len(sys.argv) and sys.argv[1] == '-r':
	ratio = True
	del sys.argv[1]

dir_str = [ "left", "right", "up", "down", "next", "prev", "fit" ]
if len(sys.argv) < 2 or sys.argv[1] not in dir_str:
	print("usage: %s [-r] <%s> [active|a] [mouse|m] [win_id]" % (sys.argv[0], '|'.join(dir_str)))
	exit(1)
dir = sys.argv[1]

if ratio and dir == "fit":
	print("warning: '-r' ignored with 'fit'")

list_id = []
for arg in sys.argv[2:] or 'a':
	if arg in ['m', 'mouse']:
		list_id += ['mouse']
	elif arg in ['a', 'active']:
		# Get active/focused window
		out = subprocess.check_output(['xprop', '-root', '_NET_ACTIVE_WINDOW']).decode('ascii', 'ignore')
		list_id += [re.search("window id # (0x[0-9a-f]+)", out).group(1)]
	else:
		# Get window id from argument
		try:
			list_id += [hex(int(arg, 0))]
		except ValueError:
			print("win_id must be a number!")
			exit(1)


# Get screens information and order them
# ======================================
# scr will store a list of list: [ [ width height offset_x offset_y ] ... ]
out = subprocess.check_output(['xrandr']).decode('ascii', 'ignore')
reg = re.compile(" connected( primary)? ([0-9]+)x([0-9]+)\+([0-9]+)\+([0-9]+)")
scr = []
for l in out.splitlines():
	m = reg.search(l)
	if m:
		scr += [ list(map(int, m.groups()[1:])) ]

# Returns the area ratio of the intersection between A and B, compared to A area
def isect_area(a, b):
	# Get top left and bottom right coords in scr format: [w h x y]
	tlx = max(a[2], b[2])
	tly = max(a[3], b[3])
	brx = min(a[2] + a[0], b[2] + b[0])
	bry = min(a[3] + a[1], b[3] + b[1])
	# Computes the intersection area and divides it by A area
	return max (0, brx - tlx) * max (0, bry - tly) / a[0] / a[1]

# r will hold a dict of how screens are disposed between themselves, using their idx.
# e.g. if scr 0 is at left of 1, then r[left][1] == 0 and r[right][0] == 1. Remaining pos set to None.
r = { a : [ None ] * len(scr) for a in dir_str  }

# To determine such relative positions, the following algorithm is applied:
#  - we "compare" all screens to each others with double nested iteration
#  - for each comparision of A to B, we duplicate A on the left, right, up, down directions
#  - the intersection area between each dup and B, relatively to A area, is computed
#  - the max value will decide the best neighbor for A and B in every direction
# A bit complicated, but this can manage unusal configurations

# Dict of max area ratio between intersection and base screen
rmx = { a : [ 0.0] * len(scr) for a in dir_str[0:4]  }

for ia, sa in enumerate(scr):
	for ib, sb in enumerate(scr):
		if sa != sb:
			# Get the interseaction area ration between (left duplicate of A) and B
			al_b = isect_area([sa[0], sa[1], sa[2] - sa[0], sa[3]], sb)
			if rmx["left"][ia] < al_b:
				r["left"][ia] = ib
				rmx["left"][ia] = al_b
			if rmx["right"][ib] < al_b:
				r["right"][ib] = ia
				rmx["right"][ib] = al_b

			# same for right duplicate of A
			ar_b = isect_area([sa[0], sa[1], sa[2] + sa[0], sa[3]], sb)
			if rmx["right"][ia] < ar_b:
				r["right"][ia] = ib
				rmx["right"][ia] = ar_b
			if rmx["left"][ib] < ar_b:
				r["left"][ib] = ia
				rmx["left"][ib] = ar_b

			# lower (down) duplicate of A
			ad_b = isect_area([sa[0], sa[1], sa[2], sa[3] + sa[1]], sb)
			if rmx["down"][ia] < ad_b:
				r["down"][ia] = ib
				rmx["down"][ia] = ad_b
			if rmx["up"][ib] < ad_b:
				r["up"][ib] = ia
				rmx["up"][ib] = ad_b

			# upper duplicate of A
			au_b = isect_area([sa[0], sa[1], sa[2], sa[3] - sa[1]], sb)
			if rmx["up"][ia] < au_b:
				r["up"][ia] = ib
				rmx["up"][ia] = au_b
			if rmx["down"][ib] < au_b:
				r["down"][ib] = ia
				rmx["down"][ib] = au_b


# Here we sort all screens linearly like (latin) writing to get "prev" and "next" orders
# The order is given by scanning almost horizontally (y = x/8) the middle of each screen
COEF_Y = 8
lin_idx = sorted(range(0, len(scr)), key = lambda i: scr[i][2] + scr[i][0]/2 + COEF_Y*(scr[i][3] + scr[i][1]/2))

for i, li in enumerate(lin_idx):
	r["prev"][lin_idx[ (i - 1) % len(scr) ]] = li
	r["next"][lin_idx[ (i + 1) % len(scr) ]] = li
	r["fit"][i] = i

for id in list_id:
	# Get mouse/window info
	# =====================
	if id == 'mouse':
		out = subprocess.check_output(['xdotool', 'getmouselocation']).decode('ascii', 'ignore')
		d = dict([ w.split(':') for w in out.split()])
		geo = [ 1, 1, int(d['x']), int(d['y']), 0, 0 ]
	else:
		# Get info on focused window,
		out = subprocess.check_output(['xwininfo', '-id', id, '-all']).decode('ascii', 'ignore')
		geo_str = ( "Width:", "Height:",
			"Absolute upper-left X:", "Absolute upper-left Y:",
			"Relative upper-left X:", "Relative upper-left Y:", "")
		state_str = ("Maximized Vert", "Maximized Horz", "Fullscreen", )
		geo = [None] * 6
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
				sys.exit(2)


	# Pocess mouse/window info
	# ========================

	# Find screen of active window from the max area
	areas = list(map(lambda s : isect_area(geo, s), scr))
	try:
		sidx = areas.index(max(areas + [1]))
	except ValueError:
		exit(3)

	# other screen in this direction?
	try:
		nscr = scr[r[dir][sidx]]
	except ValueError:
		exit(4)
	except TypeError:
		exit(5)

	# From the current coordinates...
	npos = [geo[2] - geo[4], geo[3] - geo[5]]
	nsiz = geo[0:2]

	#print scr, npos, nsiz

	if dir == 'fit':
		# ... reduce/move window so it fits totally in the screen (taking border into account)
		nsiz = [ min(nsiz[0], nscr[0] - 2*geo[4]), min(nsiz[1], nscr[1] - geo[4] - geo[5]) ]
		npos[0] = min(max(npos[0], nscr[2]), nscr[2] + nscr[0] - nsiz[0] - geo[4] - geo[4])
		npos[1] = min(max(npos[1], nscr[3]), nscr[3] + nscr[1] - nsiz[1] - geo[5] - geo[4])
	else:
		if ratio:
			# ... or move/scale window by keeping same ratio between each screens (+ rounding)
			for i in (0,1):
				npos[i] = int(float(npos[i] - scr[sidx][2 + i]) / scr[sidx][i] * nscr[i] + .5) + nscr[2 + i]
				nsiz[i] = int(1.0 * nsiz[i] * nscr[i] / scr[sidx][i] +.5)
		else:
			# ... or translate window by applying offset on x (left/right), y (up/down), or both (next/prev)
			for xy in [[0], [1], [0,1]][int(dir_str.index(dir)/2)]:
				npos[xy] += nscr[2 + xy] - scr[sidx][2 + xy]

	#print scr, npos, nsiz

	# Set mouse/window info
	# =========================
	if id == 'mouse':
		subprocess.call(['xdotool', 'mousemove'] + [str(n) for n in npos])
	else:
		# Execute move command, preserving the states
		def wmctrl(id, ops):
			for op in ops:
				cmd = ['wmctrl', '-i', '-r', id ] + op
				subprocess.call(cmd)

		# wmctrl very pernickety with -b argument, 'add' not really working and 2 props max
		wmctrl(id, [['-b', 'toggle,' + s] for s in state])
		wmctrl(id, [['-e', '0,%d,%d,%d,%d' % tuple(npos+nsiz)]])
		wmctrl(id, [['-b', 'toggle,' + s] for s in state])


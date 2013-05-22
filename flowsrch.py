#!/usr/bin/env python2 

import os, sys, argparse, re

# try importing NIDS; exit on error
try:
	import nids
except ImportError, ex:
	print "[-] Import failed: %s" % (ex)
	sys.exit(1)

# globals
version = "0.1"									# flowsrch version
reflags = 0									# regex match flags
matched = 0									# generic matched flag
logdir = ""									# directory to log matched content
openstreams = []								# list of open streams
udpdone = tcpdone = 0								# max packet/stream inspection flags
packetct = streamct = 0								# packet/stream counters
udpmatches = tcpmatches = 0							# udp/tcp match counters
cregexes = sregexes = aregexes = []						# list of compiled regex objects
maxinsppackets = maxinspstreams = maxinspbytes = 0				# max inspection counters
maxdisppackets = maxdispstreams = maxdispbytes = 0				# max display counters
shortestmatch = {'u':0, 't':0, 'U':0, 'T':0}					# shortest display/inspection match counters
longestmatch = {'u':0, 't':0, 'U':0, 'T':0}					# longest display/inspection match counters
flags = {'d':0, 'p':0, 'v':0, 'C':0, 'S':0, 'A':0, \
	 'k':0, 'w':0, 'q':0, 'm':0, 'h':0, 'a':0, 'r':0}			# cmdline args dictionary

def printable(src):
	print ''.join([ch for ch in src if ord(ch) > 31 and ord(ch) < 126 or ord(ch) == 9 or ord(ch) == 10 or ord(ch) == 13 or ord(ch) == 20])
	print

# raw bytes to hexdump filter
def hexdump(src, length=16, sep='.'):
	lines = []
	FILTER = ''.join([(len(repr(chr(x))) == 3) and chr(x) or sep for x in range(256)])
	for c in xrange(0, len(src), length):
		chars = src[c:c+length]
		hex = ' '.join(["%02x" % ord(x) for x in chars])
		if len(hex) > 24:
			hex = "%s %s" % (hex[:24], hex[24:])
		printable = ''.join(["%s" % ((ord(x) <= 127 and FILTER[ord(x)]) or sep) for x in chars])
		lines.append("%08x:  %-*s  |%s|\n" % (c, length*3, hex, printable))
	print ''.join(lines)

# udp callback handler
def handleudp(addrs, payload, pkt):
	global udpregex, packetct, maxinsppackets, maxinspbytes, udpmatches, udpdone, tcpdone, matched, cregexes, sregexes, aregexes
        finalpayload = timestamp = 0
	matched = 0

	if maxinsppackets != 0 and packetct >= maxinsppackets:			# if max packet inspection count is non-zero
 		udpdone = 1							# and we have reached that limit
		donetcpudp()							# set flag and return
		return

        packetct += 1								# increment packet counter
	timestamp = nids.get_pkt_ts()

	if maxinspbytes > 0:							# if max inspection depth is non-zero
		finalpayload = payload[:maxinspbytes]				# extract depth bytes from payload
	else:
		finalpayload = payload						# else extract all bytes from payload

	if not matched:
		for regexobj in cregexes:
			for match in regexobj.finditer(finalpayload):		# match regex and generate iterable match object
				matched = 1
				if not flags['v']:				# if invert match is not requested (direct match)
					start = match.start()			# find starting offset of matched bytes
					end = match.end()			# find ending offset of matched bytes
					udpmatches += 1				# increment udp match counter
					showudpmatch(timestamp, addrs, finalpayload, start, end, regexobj)
			if matched: break

	if not matched:
		for regexobj in sregexes:
			for match in regexobj.finditer(finalpayload):		# match regex and generate iterable match object
				matched = 1
				if not flags['v']:				# if invert match is not requested (direct match)
					start = match.start()			# find starting offset of matched bytes
					end = match.end()			# find ending offset of matched bytes
					udpmatches += 1				# increment udp match counter
					showudpmatch(timestamp, addrs, finalpayload, start, end, regexobj)
			if matched: break

	if not matched:
		for regexobj in aregexes:
			for match in regexobj.finditer(finalpayload):		# match regex and generate iterable match object
				matched = 1
				if not flags['v']:				# if invert match is not requested (direct match)
					start = match.start()			# find starting offset of matched bytes
					end = match.end()			# find ending offset of matched bytes
					udpmatches += 1				# increment udp match counter
					showudpmatch(timestamp, addrs, finalpayload, start, end, regexobj)
			if matched: break

	if not matched:								# packet did not match
		if flags['v']:							# and invert match is requested
			start = 0						# point to the start of the payload
			end = len(finalpayload)					# should dump all of teh payload coz we don't have match offsets
			udpmatches += 1						# increment udp match counter
			showudpmatch(timestamp, addrs, finalpayload, start, end, None)

# show udp packet details and match stats
def showudpmatch(timestamp, addrs, payload, start, end, regexobj):
	global packetct, maxinsppackets, maxinspbytes, udpmatches, maxdisppackets, shortestmatch, longestmatch
	((src,sport), (dst,dport)) = addrs

	count = end - start
	if count == 0:								# if matched payload is of size 0 (regex returns 0 bytes matches for some expressions)
		udpmatches -= 1							# don't track such matches
		return								# and return

	if maxdisppackets != 0 and udpmatches > maxdisppackets:			# if user requested packet matches have been dumped
		udpdone = 1							# mark completion of udp packets inspection
		donetcpudp()							# check if max stream and packet inspection limits have been exhausted
		return								# if above fails, return anyways

	if udpmatches == 1:							# if its the first udp match, track it as the 
		shortestmatch['u'] = count					# shortest and
		shortestmatch['U'] = udpmatches
		longestmatch['u'] = count					# longest match
		longestmatch['U'] = udpmatches

	if shortestmatch['u'] > count:						# if a shorter match if found
		shortestmatch['u'] = count					# track it as the new shortest match
		shortestmatch['U'] = udpmatches

	if longestmatch['u'] < count:						# if a new longest match is found
		longestmatch['u'] = count					# track it as the new longest match
		longestmatch['U'] = udpmatches

	if maxdispbytes == 0 or count <= maxdispbytes:				# tune display limits
		dispend = end
	else:
		dispend = start+maxdispbytes

	if flags['w']: writetofile(timestamp, src, sport, dst, dport, payload, "udp")

	if flags['q']: return

	if flags['m']: print "[U] (%d/%d/%d) %s: %s:%s > %s:%s (matched \"%s\" @ [%d:%d] - %dB)" % \
		(udpmatches, packetct, maxinsppackets, str(timestamp), src, sport, dst, dport, str(regexobj), start, end, count)

	if flags['r']: print("%s\n" % payload[start:dispend])

	if flags['a']: printable(payload[start:dispend])

	if flags['h']: hexdump(payload[start:dispend])

# tcp callback handler
def handletcp(tcp):
	global streamct, maxinspstreams, maxinspbytes, tcpmatches, tcpdone, udpdone, matched, openstreams, tcpunmatched, aregexes, cregexes, sregexes
	matched = 0
	data = finalpayload = timestamp = ""

	if tcpdone:								# if max stream inspection count is reached
		donetcpudp()							# check if we can exit
		return								# else return

	if maxinspstreams != 0 and streamct > maxinspstreams:			# if max stream inspection count is non-zero
		streamct = maxinspstreams					# adjust inspected stream count
		tcpdone = 1							# and we have reached that limit
		donetcpudp()							# set flag and return
		return

	endstates = (nids.NIDS_CLOSE, nids.NIDS_TIMED_OUT, nids.NIDS_RESET)	# possible stream termination states

	if tcp.nids_state == nids.NIDS_JUST_EST:				# if a new stream is available
		if flags['A']:
			tcp.server.collect = 1
			tcp.client.collect = 1
		if flags['C']:							# and CTS stream has to be inspected
			tcp.server.collect = 1					# mark it for data collection
		if flags['S']:							# and STC stream has to be inspected
			tcp.client.collect = 1					# mark it for data collection

		if tcp.addr not in openstreams:					# if not already tracking (nids will take care of it, but still good to have a precheck)
			openstreams.append(tcp.addr)				# start tracking this stream
			streamct += 1						# increment stream counter

	elif tcp.nids_state == nids.NIDS_DATA:                                  # if a stream has data
		tcp.discard(0)			                                # discard first 0 bytes; collect entire payload

		adata = tcp.server.data + tcp.client.data			# extract toserver and toclient data
		cdata = tcp.server.data						# extract toserver data
		sdata = tcp.client.data						# extract toclient data

		if maxinspbytes != 0:						# if max inspection depth is non-zero
			afinalpayload = adata[:maxinspbytes]			# extract depth bytes from data
			cfinalpayload = cdata[:maxinspbytes]
			sfinalpayload = sdata[:maxinspbytes]
		else:
			afinalpayload = adata					# else extract all bytes from data
			cfinalpayload = cdata
			sfinalpayload = sdata

		if flags['A'] and tcp.addr in openstreams and not matched:
			for regexobj in aregexes:
				for match in regexobj.finditer(afinalpayload):	# match regex and generate an iterable match object
					matched = 1
					if not flags['v']:
	 					start = match.start()		# find starting offset of matched bytes
						end = match.end()		# find ending offset of matched bytes
						tcpmatches += 1			# increment tcp match counter
						showtcpmatch(timestamp, tcp.addr, afinalpayload, start, end, regexobj, "ANY")
				if matched:
					if flags['k']:
						tcp.kill
					if tcp.addr in openstreams:
						openstreams.remove(tcp.addr)
					break

		if flags['C'] and tcp.addr in openstreams and not matched:
			for regexobj in cregexes:
				for match in regexobj.finditer(cfinalpayload):	# match regex and generate an iterable match object
					matched = 1
					if not flags['v']:
						start = match.start()		# find starting offset of matched bytes
						end = match.end()		# find ending offset of matched bytes
						tcpmatches += 1			# increment tcp match counter
						showtcpmatch(timestamp, tcp.addr, cfinalpayload, start, end, regexobj, "CTS")
				if matched:
					if flags['k']:
						tcp.kill
					if tcp.addr in openstreams:
						openstreams.remove(tcp.addr)
					break

		if flags['S'] and tcp.addr in openstreams and not matched:
			for regexobj in sregexes:
				for match in regexobj.finditer(sfinalpayload):	# match regex and generate an iterable match object
					matched = 1
					if not flags['v']:
						start = match.start()		# find starting offset of matched bytes
						end = match.end()		# find ending offset of matched bytes
						tcpmatches += 1			# increment tcp match counter
						showtcpmatch(timestamp, tcp.addr, sfinalpayload, start, end, regexobj, "STC")
				if matched:
					if flags['k']:
						tcp.kill
					if tcp.addr in openstreams:
						openstreams.remove(tcp.addr)
					break

		if not matched and flags['v']:					# stream did not match and invert match is requested
			start = 0						# point to the start of payload
			end = len(afinalpayload)				# should dump all of the payload coz we don't have match offsets
			tcpmatches += 1						# increment tcp match counter
			showtcpmatch(timestamp, tcp.addr, afinalpayload, start, end, None, "ANY")
			if tcp.addr in openstreams:				# are we tracking this stream?
				openstreams.remove(tcp.addr)			# stop tracking any further
				if flags['k']:
					tcp.kill				# terminate matched stream if requested

	elif tcp.nids_state in endstates:                                       # if a stream is closed, reset, or timed out
		if tcp.addr in openstreams:					# no match for this stream,
			openstreams.remove(tcp.addr)				# stop tracking it please
		timestamp = nids.get_pkt_ts()					# read timestamp

	else:
		print >>sys.stderr, "[!] Unknown NIDS state: %s" % (tcp.nids_state)

# show tcp stream details and match stats
def showtcpmatch(timestamp, addrs, payload, start, end, regexobj, dir):
	global streamct, maxinspstreams, maxinspbytes, tcpmatches, maxdispstreams, flags
	((src,sport), (dst,dport)) = addrs

	count = end - start
	if count == 0:								# if matched payload is of size 0 (regex returns 0 byte matches for some expressions)
		tcpmatches -= 1							# don't track such matches
		return								# and return

	if maxdispstreams != 0 and tcpmatches > maxdispstreams:			# if user requested streams have been dumped
		tcpdone = 1							# mark completion of tcp streams inspection
		donetcpudp()							# check if max stream and packet inspection limits have been exhausted
		return								# if above fails, return anyways

	if tcpmatches == 1:							# if its the first tcp match, track it as the
		shortestmatch['t'] = count					# shortest and
		shortestmatch['T'] = tcpmatches
		longestmatch['t'] = count					# longest match
		longestmatch['T'] = tcpmatches

	if shortestmatch['t'] > count:						# if a shorter match is found
		shortestmatch['t'] = count					# track it as the new shortest match
		shortestmatch['T'] = tcpmatches

	if longestmatch['t'] < count:						# if a longer match is found
		longestmatch['t'] = count					# track it as the new longest match
		longestmatch['T'] = tcpmatches

	if maxdispbytes == 0 or count <= maxdispbytes:				# tune display limits
		dispend = end
	else:
		dispend = start+maxdispbytes

	if flags['w']: writetofile(timestamp, src, sport, dst, dport, payload, "tcp")

	if flags['q']: return

	if flags['m']: print "[T] (%d/%d/%d) %s: %s:%s > %s:%s (matched \"%s\" on %s @ [%d:%d] - %dB)" % \
		(tcpmatches, streamct, maxinspstreams, str(timestamp), src, sport, dst, dport, str(regexobj), dir, start, end, count)

	if flags['r']: print("%s\n" % payload[start:dispend])

	if flags['a']: printable(payload[start:dispend])

	if flags['h']: hexdump(payload[start:dispend])

# ip callback handler
def handleip(pkt):
	timestamp = nids.get_pkt_ts()

# logs payload to a dir/file
def writetofile(timestamp, src, sport, dst, dport, payload, proto):
	global logdir

	try:
		if not os.path.isdir(logdir):
			os.makedirs(logdir)
	except OSError, oserr: print "[!] OSError: %s" % oserr

	filename = "%s/%s-%s.%s-%s.%s-%s" % (logdir, str(timestamp).translate(None, '.'), src, sport, dst, dport, proto)

	try:
		file = open(filename, 'ab+')
		file.write(payload)
	except IOError, io: print "[!] IOError: %s" % io

# shows arguments stats
def dumpargsstats(args):
	global flags, maxinsppackets, maxinspstreams, maxinspbytes, maxdisppackets, maxdispstreams, maxdispbytes, logdir

	if flags['p']:
		print "%-30s" % "[+] Input pcap:", ; print "[ %s ]" % (args.pcap)
	elif flags['d']:
		print "%-30s" % "[+] Listening device:", ;print "[ \"%s\" ]" % (args.device),
		if flags['k']: print "[ w/ \"killtcp\" ]"
		else: print

	if args.filter:
		print "%-30s" % "[+] BPF expression:", ; print "[ \"%s\" ]" % (args.filter)

	print "%-30s" % "[+] TCP Inspection Direction:", ; print "[",
	if flags['A']: print "ANY",
	if flags['C']: print "CTS",
	if flags['S']: print "STC",
	print "]"

	print "%-30s" % "[+] Inspection limits:",
	print "[ Streams: %d | Packets: %d | Bytes: %d ]" % (maxinspstreams, maxinsppackets, maxinspbytes)
	print "%-30s" % "[+] Display limits:",
	print "[ Streams: %d | Packets: %d | Bytes: %d ]" % (maxdispstreams, maxdisppackets, maxdispbytes)

	print "%-30s" % "[+] Output modes:", ; print "[",
	if flags['q']: print "quite"
	else:
		if flags['w']: print "write: %s" % logdir,
		if flags['m']: print "meta",
		if flags['h']: print "hex",
		if flags['a']: print "ascii",
		if flags['r']: print "raw",
	print "]"

	print

# done parsing max packets/streams
def donetcpudp():
	global udpdone, tcpdone

	if tcpdone and udpdone:							# if we're done isnpecting max streams and packets
		exitwithstats()							# display stats and exit

# keyboard interrupt handler / exit stats display routine
def exitwithstats():
	global packetct, udpmatches, streamct, tcpmatches, shortestmatch, longestmatch, openstreams

	print
	if packetct >= 0:
		print "[U] Processed: %d | Matches: %d | Shortest: %dB (#%d) | Longest: %dB (#%d)" % \
		(packetct, udpmatches, shortestmatch['u'], shortestmatch['U'], longestmatch['u'], longestmatch['U'])

	if streamct >= 0:
		print "[T] Processed: %d | Matches: %d | Shortest: %dB (#%d) | Longest: %dB (#%d)" % \
		(streamct, tcpmatches, shortestmatch['t'], shortestmatch['T'], longestmatch['t'], longestmatch['T'])

	if len(openstreams) > 0:
		print "[!] Skipped streams: %d (tcp.state did not match endstates)" % len(openstreams)

	print "[+] Flowsrch session complete. Exiting."
	sys.exit(0)

# main routine
def main():
	global version, reflags, udpregex, tcpregex, openstreams, maxinsppackets, maxinspstreams, maxinspbytes, maxdisppackets, maxdispstreams, maxdispbytes, packetct, streamct, flags, logdir, cregexes, sregexes, aregexes

	parser = argparse.ArgumentParser()

	inputgroup = parser.add_mutually_exclusive_group(required=True)
	inputgroup.add_argument('-d', metavar="--device", dest="device", default="lo", action="store", help="listening device")
	inputgroup.add_argument('-p', metavar="--pcap", dest="pcap", default="", action="store", help="input pcap file")

	parser.add_argument('-f', metavar="--filter", dest="filter", default="", action="store", required=False, help="BPF expression")

	parser.add_argument('-C', metavar="--cregex", dest="cres", default=[], action="append", required=False, help="regex to match against client stream")
	parser.add_argument('-S', metavar="--sregex", dest="sres", default=[], action="append", required=False, help="regex to match against server stream")
	parser.add_argument('-A', metavar="--aregex", dest="ares", default=[], action="append", required=False, help="regex to match against any stream")

	parser.add_argument('-i', dest="igncase", default=False, action="store_true", required=False, help="ignore case")
	parser.add_argument('-v', dest="invmatch", default=False, action="store_true", required=False, help="invert match")
	parser.add_argument('-m', dest="multiline", default=False, action="store_true", required=False, help="multiline match")

	parser.add_argument('-T', metavar="--maxinspstreams", dest="maxinspstreams", default=0, action="store", type=int, required=False, help="max streams to inspect")
	parser.add_argument('-U', metavar="--maxinsppackets", dest="maxinsppackets", default=0, action="store", type=int, required=False, help="max packets to inspect")
	parser.add_argument('-B', metavar="--maxinspbytes", dest="maxinspbytes", default=0, action="store", type=int, required=False, help="max bytes to inspect")

	parser.add_argument('-t', metavar="--maxdispstreams", dest="maxdispstreams", default=0, action="store", type=int, required=False, help="max streams to display")
	parser.add_argument('-u', metavar="--maxdisppackets", dest="maxdisppackets", default=0, action="store", type=int, required=False, help="max packets to display")
	parser.add_argument('-b', metavar="--maxdispbytes", dest="maxdispbytes", default=0, action="store", type=int, required=False, help="max bytes to display")

	parser.add_argument('-w', metavar="logdir", dest="writebytes", default="", action="store", required=False, nargs='?', help="write matching packets/streams")

	parser.add_argument('-k', dest="killtcp", default=False, action="store_true", required=False, help="kill matching TCP stream")

	parser.add_argument('-o', dest="outmode", choices=('quite', 'meta', 'hex', 'ascii', 'raw'), action="append",  default=[], required=False, help="match output mode")

	parser.add_argument('-V', action='version', version='%(prog)s 0.1')

	args = parser.parse_args()

	print "%s v%s - Use regexes to inspect network traffic" % (os.path.basename(sys.argv[0]), version)
	print "Juniper Networks - Security Research Group"
	print

	nids.chksum_ctl([('0.0.0.0/0', False)])					# disable checksum verification
	nids.param("scan_num_hosts", 0)						# disable port scan detection

	if args.pcap != "":
		flags['p'] = 1							# enable pcap inspection
		flags['d'] = 0							# disable live device inspection
		nids.param("filename", args.pcap)				# set NIDS filename parameter with input pcap
	elif args.device != "":
		flags['d'] = 1							# enable live device inspection
		flags['p'] = 0							# disable pcap inspection
		nids.param("device", args.device)				# set NIDS device parameter with device name

	if args.filter != "":
		nids.param("pcap_filter", args.filter)				# set NIDS filter parameter with input BPF expression

	if args.igncase == True:
		reflags |= re.IGNORECASE					# enable case insensitive regex match flag

	if args.invmatch == True:
		flags['v'] = 1							# enable invert match inspection

	if args.multiline == True:
		reflags |= re.MULTILINE						# enable multiline regex match flag
		reflags |= re.DOTALL						# enable dotall regex match flag (dot matches newline aswell)

	if args.killtcp == True:						# if tcp stream teardown is requested
		if flags['d']:							# and we'll be inspecting on a live network
			flags['k'] = 1						# enable killtcp

	if args.maxinspstreams:							# if max stream inspection limit is provided,
		maxinspstreams = int(args.maxinspstreams)			# enable limit

	if args.maxinsppackets:							# if max packet inspection limit is provided,
		maxinsppackets = int(args.maxinsppackets)			# enable limit

	if args.maxinspbytes:							# if max inspection depth is provided,
		maxinspbytes = int(args.maxinspbytes)				# enable depth

	if args.maxdispstreams:							# if max stream display limit is provided,
		maxdispstreams = int(args.maxdispstreams)			# enable limit

	if args.maxdisppackets:							# if max packet display limit is provided,
		maxdisppackets = int(args.maxdisppackets)			# enable limit

	if args.maxdispbytes:							# if max display depth is provided,
		maxdispbytes = int(args.maxdispbytes)				# enable depth

	if args.writebytes != "":
		flags['w'] = 1
		if args.writebytes != None:
			logdir = args.writebytes
		else:
			logdir = "."

	if not args.outmode:
		flags['m'] = 1
		flags['h'] = 1
	else:
		for mode in args.outmode:
			if mode == "quite": flags['q'] = 1
			elif mode == "meta": flags['m'] = 1
			elif mode == "hex": flags['h'] = 1
			elif mode == "ascii": flags['a'] = 1
			elif mode == "raw": flags['r'] = 1

	try:
		if args.cres:
			flags['C'] = 1
			cregexes = []
			for c in args.cres:
				cregexes.append(re.compile(c, reflags))
		if args.sres:
			flags['S'] = 1
			sregexes = []
			for s in args.sres:
				sregexes.append(re.compile(s, reflags))
		if args.ares:
			flags['A'] = 1
			aregexes = []
			for a in args.ares:
				aregexes.append(re.compile(a, reflags))

		if not cregexes and not sregexes and not aregexes:
			print "[-] Need a regex expression."
			print "[-] Use direction flags [CSA] to specify one."
			sys.exit(1)

		dumpargsstats(args)						# show current arguments stats

		nids.init()							# initialize NIDS
		nids.register_ip(handleip)					# register ip callback handler
		nids.register_udp(handleudp)					# register udp callback handler
		nids.register_tcp(handletcp)					# register tcp callback handler

		print "[+] Callback handlers registered. Press any key to continue...",
		try: input()
		except: pass

		print "[+] NIDS initialized, waiting for events..." ; print
		try: nids.run()							# invoke NIDS handler
		except KeyboardInterrupt: exitwithstats()

	except nids.error, nx:
		print
		print "[-] NIDS error: %s" % nx
		sys.exit(1)
#	except Exception, ex:
#		print
#		print "[-] Exception: %s" % ex
#		sys.exit(1)

	exitwithstats()

if __name__ == "__main__":
	main()


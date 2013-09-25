# flowinspect specific functions commonly used by modules

from globals import configopts, opentcpflows, openudpflows, ippacketsdict
from tcphandler import handletcp
from udphandler import handleudp
from iphandler import handleip
from utils import printdict, pcapwriter

import sys


def validatedfaexpr(expr):
    global configopts

    if re.search(r'^m[0-9][0-9]\s*=\s*', expr):
        (memberid, dfa) =  expr.split('=', 1)
        configopts['dfalist'].append(expr)
        return (memberid.strip(), dfa.strip())
    else:
        memberct = len(configopts['dfalist'])
        memberid = 'm%02d' % (memberct+1)
        configopts['dfalist'].append(expr)
        return (memberid, expr.strip())

def writetofile(filename, data):
    global configopts, opentcpflows

    try:
        if not os.path.isdir(configopts['logdir']): os.makedirs(configopts['logdir'])
    except OSError, oserr: print '[-] %s' % oserr

    try:
        if configopts['linemode']: file = open(filename, 'ab+')
        else: file = open(filename, 'wb+')
        file.write(data)
    except IOError, io: print '[-] %s' % io


def exitwithstats():
    global configopts, openudpflows, opentcpflows

    if configopts['verbose'] and (len(opentcpflows) > 0 or len(openudpflows) > 0):
        print
        dumpopenstreams()

    if len(ippacketsdict) > 0:
        if configopts['verbose']:
            print
            dumpippacketsdict()
        print
        writepackets()

    print
    if configopts['packetct'] >= 0:
        print '[U] Processed: %d | Matches: %d | Shortest: %dB (#%d) | Longest: %dB (#%d)' % (
                configopts['inspudppacketct'],
                configopts['udpmatches'],
                configopts['shortestmatch']['packet'],
                configopts['shortestmatch']['packetid'],
                configopts['longestmatch']['packet'],
                configopts['longestmatch']['packetid'])

    if configopts['streamct'] >= 0:
        print '[T] Processed: %d | Matches: %d | Shortest: %dB (#%d) | Longest: %dB (#%d)' % (
                configopts['insptcpstreamct'],
                configopts['tcpmatches'],
                configopts['shortestmatch']['stream'],
                configopts['shortestmatch']['streamid'],
                configopts['longestmatch']['stream'],
                configopts['longestmatch']['streamid'])

    print '[+] Flowsrch session complete. Exiting.'

    if configopts['udpmatches'] > 0 or configopts['tcpmatches'] > 0: sys.exit(0)
    else: sys.exit(1)


def dumpopenstreams():
    if len(openudpflows) > 0:
        print '[DEBUG] Dumping open/tracked UDP streams: %d' % (len(openudpflows))

        for (key, value) in openudpflows.items():
            id = value['id']
            keydst = value['keydst']
            matches = value['matches']
            ctsdatasize = value['ctsdatasize']
            stcdatasize = value['stcdatasize']
            totdatasize = value['totdatasize']
            print '[DEBUG] [%08d] %s - %s (CTS: %dB | STC: %dB | TOT: %dB) [matches: %d]' % (
                    id,
                    key,
                    keydst,
                    ctsdatasize,
                    stcdatasize,
                    totdatasize,
                    matches)

    if len(opentcpflows) > 0:
        print
        print '[DEBUG] Dumping open/tracked TCP streams: %d' % (len(opentcpflows))

        for (key, value) in opentcpflows.items():
            id = value['id']
            ((src, sport), (dst, dport)) = key

            ctsdatasize = 0
            for size in value['ctspacketlendict'].values():
                ctsdatasize += size

            stcdatasize = 0
            for size in value['stcpacketlendict'].values():
                stcdatasize += size

            totdatasize = ctsdatasize + stcdatasize
            print '[DEBUG] [%08d] %s:%s - %s:%s (CTS: %dB | STC: %dB | TOT: %dB)' % (
                    id,
                    src,
                    sport,
                    dst,
                    dport,
                    ctsdatasize,
                    stcdatasize,
                    totdatasize)


def dumpippacketsdict():
    print '[DEBUG] Dumping IP packets dictionary: %d' % (len(ippacketsdict.keys()))
    for key in ippacketsdict.keys():
        ((src, sport), (dst, dport)) = key
        print '[DEBUG] [%s#%08d] %s:%s - %s:%s (Packets: %d | Matched: %s)' % (
            ippacketsdict[key]['proto'],
            ippacketsdict[key]['id'],
            src,
            sport,
            dst,
            dport,
            len(ippacketsdict[key].keys()) - 2,
            ippacketsdict[key]['matched'])


def writepackets():
    pktlist = []
    for key in ippacketsdict.keys():
        if ippacketsdict[key]['matched']:
            del pktlist[:]
            ((src, sport), (dst, dport)) = key
            pcapfile = '%s-%08d-%s.%s-%s.%s.pcap' % (ippacketsdict[key]['proto'], ippacketsdict[key]['id'], src, sport, dst, dport)
            for subkey in ippacketsdict[key].keys():
                if subkey not in ['proto', 'id', 'matched']:
                    pktlist.append(ippacketsdict[key][subkey])
            pcapwriter(pcapfile, pktlist)
        del ippacketsdict[key]


def dumpargsstats(configopts):
    print '%-30s' % '[DEBUG] Input pcap:', ; print '[ \'%s\' ]' % (configopts['pcap'])
    print '%-30s' % '[DEBUG] Listening device:', ;print '[ \'%s\' ]' % (configopts['device']),
    if configopts['killtcp']:
        print '[ w/ \'killtcp\' ]'
    else:
        print

    print '%-30s' % '[DEBUG] Inspection Modes:', ;print '[',
    for mode in configopts['inspectionmodes']:
        if mode == 'regex': print '\'regex (%s)\'' % (configopts['regexengine']),
        if mode == 'fuzzy': print '\'fuzzy (%s)\'' % (configopts['fuzzengine']),
        if mode == 'dfa': print '\'dfa (%s)\'' % (configopts['dfaengine']),
        if mode == 'shellcode': print '\'shellcode (%s)\' | memory: %dK' % (configopts['shellcodeengine'], configopts['emuprofileoutsize']),
    print ']'

    if 'regex' in configopts['inspectionmodes']:
        print '%-30s' % '[DEBUG] CTS regex:', ; print '[ %d |' % (len(configopts['ctsregexes'])),
        for c in configopts['ctsregexes']:
            print '\'%s\'' % configopts['ctsregexes'][c]['regexpattern'],
        print ']'

        print '%-30s' % '[DEBUG] STC regex:', ; print '[ %d |' % (len(configopts['stcregexes'])),
        for s in configopts['stcregexes']:
            print '\'%s\'' % configopts['stcregexes'][s]['regexpattern'],
        print ']'

        print '%-30s' % '[DEBUG] RE stats:', ; print '[ Flags: %d - (' % (configopts['reflags']),
        if configopts['igncase']: print 'ignorecase',
        if configopts['multiline']: print 'multiline',
        print ') ]'

    if 'fuzzy' in configopts['inspectionmodes']:
        print '%-30s' % '[DEBUG] CTS fuzz patterns:', ; print '[ %d |' % (len(configopts['ctsfuzzpatterns'])),
        for c in configopts['ctsfuzzpatterns']:
            print '\'%s\'' % (c),
        print ']'

        print '%-30s' % '[DEBUG] STC fuzz patterns:', ; print '[ %d |' % (len(configopts['stcfuzzpatterns'])),
        for s in configopts['stcfuzzpatterns']:
            print '\'%s\'' % (s),
        print ']'

    if 'dfa' in configopts['inspectionmodes']:
        print '%-30s' % '[DEBUG] CTS dfa:', ; print '[ %d |' % (len(configopts['ctsdfas'])),
        for c in configopts['ctsdfas']:
            print '\'%s: %s\'' % (configopts['ctsdfas'][c]['memberid'], configopts['ctsdfas'][c]['dfapattern']),
        print ']'

        print '%-30s' % '[DEBUG] STC dfa:', ; print '[ %d |' % (len(configopts['stcdfas'])),
        for s in configopts['stcdfas']:
            print '\'%s: %s\'' % (configopts['stcdfas'][s]['memberid'], configopts['stcdfas'][s]['dfapattern']),
        print ']'

        print '%-30s' % '[DEBUG] DFA expression:',
        print '[ \'%s\' ]' % (configopts['dfaexpression'])

    if 'yara' in configopts['inspectionmodes']:
        print '%-30s' % '[DEBUG] CTS yara rules:', ; print '[ %d |' % (len(configopts['ctsyararules'])),
        for c in configopts['ctsyararules']:
            print '\'%s\'' % (c),
        print ']'

        print '%-30s' % '[DEBUG] STC yara rules:', ; print '[ %d |' % (len(configopts['stcyararules'])),
        for s in configopts['stcyararules']:
            print '\'%s\'' % (s),
        print ']'

    print '%-30s' % '[DEBUG] Inspection limits:',
    print '[ Streams: %d | Packets: %d | Offset: %d | Depth: %d ]' % (
            configopts['maxinspstreams'],
            configopts['maxinsppackets'],
            configopts['offset'],
            configopts['depth'])

    print '%-30s' % '[DEBUG] Display limits:',
    print '[ Streams: %d | Packets: %d | Bytes: %d ]' % (
            configopts['maxdispstreams'],
            configopts['maxdisppackets'],
            configopts['maxdispbytes'])

    print '%-30s' % '[DEBUG] Output modes:', ; print '[',
    if 'quite' in configopts['outmodes']:
        print '\'quite\'',
        if configopts['writelogs']:
            print '\'write: %s\'' % (configopts['logdir']),
    else:
        if 'meta' in configopts['outmodes']: print '\'meta\'',
        if 'hex' in configopts['outmodes']: print '\'hex\'',
        if 'print' in configopts['outmodes']: print '\'print\'',
        if 'raw' in configopts['outmodes']: print '\'raw\'',
        if 'graph' in configopts['outmodes']: print '\'graph: %s\'' % (configopts['graphdir']),
        if configopts['writelogs']: print '\'write: %s\'' % (configopts['logdir']),
    print ']'

    print '%-30s' % '[DEBUG] Misc options:',
    print '[ BPF: \'%s\' | invertmatch: %s | killtcp: %s | graph: %s | verbose: %s | linemode: %s ]' % (
            configopts['bpf'],
            configopts['invertmatch'],
            configopts['killtcp'],
            configopts['graph'],
            configopts['verbose'],
            configopts['linemode'])
    print


"""PSS/E file parser"""

import logging
import re

from andes.consts import deg2rad
from andes.common.utils import to_number

logger = logging.getLogger(__name__)


def is_format(fid):
    """Check the raw file for frequency base"""
    first = fid.readline()
    first = first.strip().split('/')
    first = first[0].split(',')
    if float(first[5]) == 50.0 or float(first[5]) == 60.0:
        return True
    else:
        return False


def get_block_lines(b, mdata):
    """
    Return the number of lines based on data
    """
    line_counts = [1, 1, 1, 1, 1, 4, 1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0]

    if b == 5:  # for transformer
        if mdata[0][2] == 0:  # two-winding transformer
            return 4
        else:  # three-winding transformer
            return 5

    return line_counts[b]


def read(system, file):
    """read PSS/E RAW file v32 format"""

    blocks = [
        'bus', 'load', 'fshunt', 'gen', 'branch', 'transf', 'area',
        'twotermdc', 'vscdc', 'impedcorr', 'mtdc', 'msline', 'zone',
        'interarea', 'owner', 'facts', 'swshunt', 'gne', 'Q'
    ]
    rawd = re.compile(r'rawd\d\d')

    ret = True
    block_idx = 0  # current block index
    mva = 100

    raw = {}
    for item in blocks:
        raw[item] = []

    data = []
    mdata = []  # multi-line data
    dev_line = 0  # line counter for multi-line models

    # read file into `line_list`
    with open(file, 'r') as f:
        line_list = [line.rstrip('\n') for line in f]

    # parse file into `raw` with to_number conversions
    for num, line in enumerate(line_list):
        line = line.strip()
        if num == 0:  # get basemva and frequency
            data = line.split('/')[0]
            data = data.split(',')

            mva = float(data[1])
            system.config.mva = mva
            system.config.freq = float(data[5])

            # get raw file version
            version = int(data[2])
            if not version:
                version = int(rawd.search(line).group(0).strip('rawd'))
            logger.debug('PSSE raw version {} detected'.format(version))

            if version < 32 or version > 33:
                logger.warning('RAW file version is not 32 or 33. Error may occur.')
            continue

        elif num == 1 or num == 2:  # store the case info line
            if len(line) > 0:
                logger.info(line)
            continue
        elif num >= 3:
            if line[0:2] == '0 ' or line[0:3] == ' 0 ':  # end of block
                block_idx += 1
                continue
            elif line[0] == 'Q':  # end of file
                break
            data = line.split(',')

        data = [to_number(item) for item in data]
        mdata.append(data)
        dev_line += 1

        block_lines = get_block_lines(block_idx, mdata)
        if dev_line >= block_lines:
            if block_lines == 1:
                mdata = mdata[0]
            raw[blocks[block_idx]].append(mdata)
            mdata = []
            dev_line = 0

    # add device elements to system
    sw = {}  # idx:a0
    max_bus = []
    for data in raw['bus']:
        # version 32:
        #   0,   1,      2,     3,    4,   5,  6,   7,  8
        #   ID, NAME, BasekV, Type, Area Zone Owner Vm, Va
        #
        idx = data[0]
        max_bus.append(idx)
        ty = data[3]
        a0 = data[8] * deg2rad

        if ty == 3:
            sw[idx] = a0
        param = {'idx': idx, 'name': data[1], 'Vn': data[2],
                 'v0': data[7], 'a0': a0,
                 'area': data[4], 'region': data[5], 'owner': data[6]}
        system.add('Bus', param)

    max_bus = max(max_bus)
    for data in raw['load']:
        # version 32:
        #  0,  1,      2,    3,    4,    5,    6,      7,   8,  9, 10,   11
        # Bus, Id, Status, Area, Zone, PL(MW), QL (MW), IP, IQ, YP, YQ, OWNER
        #
        bus = data[0]
        vn = system.Bus.get(src='Vn', idx=bus, attr='v')
        v0 = system.Bus.get(src='v0', idx=bus, attr='v')
        param = {'bus': bus, 'u': data[2], 'Vn': vn,
                 'p0': (data[5] + data[7] * v0 + data[9] * v0 ** 2) / mva,
                 'q0': (data[6] + data[8] * v0 - data[10] * v0 ** 2) / mva,
                 'owner': data[11]}
        system.add('PQ', param)

    for data in raw['fshunt']:
        # 0,    1,      2,      3,      4
        # Bus, name, Status, g (MW), b (Mvar)
        bus = data[0]
        vn = system.Bus.get(src='Vn', idx=bus, attr='v')

        param = {'bus': bus, 'Vn': vn, 'u': data[2],
                 'Sn': mva, 'g': data[3] / mva, 'b': data[4] / mva}
        system.add('Shunt', param)

    gen_idx = 0
    for data in raw['gen']:
        #  0, 1, 2, 3, 4, 5, 6, 7,    8,   9,10,11, 12, 13, 14,   15, 16,17,18,19
        #  I,ID,PG,QG,QT,QB,VS,IREG,MBASE,ZR,ZX,RT,XT,GTAP,STAT,RMPCT,PT,PB,O1,F1
        bus = data[0]
        vn = system.Bus.get(src='Vn', idx=bus, attr='v')
        gen_mva = data[8]  # unused yet
        gen_idx += 1
        status = data[14]
        param = {'Sn': gen_mva, 'Vn': vn, 'u': status, 'idx': gen_idx, 'bus': bus,
                 'p0': status * data[2] / mva,
                 'q0': status * data[3] / mva,
                 'pmax': data[16] / mva, 'pmin': data[17] / mva,
                 'qmax': data[4] / mva, 'qmin': data[5] / mva,
                 'v0': data[6],
                 'ra': data[9],  # ra  armature resistance
                 'xs': data[10],  # xs synchronous reactance
                 }
        if data[0] in sw.keys():
            param.update({'a0': sw[data[0]]})
            system.add('Slack', param)
        else:
            system.add('PV', param)

    for data in raw['branch']:
        #
        # I,J,CKT,R,X,B,RATEA,RATEB,RATEC,GI,BI,GJ,BJ,ST,LEN,O1,F1,...,O4,F4
        #
        param = {
            'bus1': data[0], 'bus2': data[1],
            'r': data[3], 'x': data[4], 'b': data[5],
            'Vn1': system.Bus.get(src='Vn', idx=data[0], attr='v'),
            'Vn2': system.Bus.get(src='Vn', idx=data[1], attr='v'),
        }
        system.add('Line', **param)

    xf_3_count = 1
    for data in raw['transf']:
        if len(data) == 4:
            # """
            # I,J,K,CKT,CW,CZ,CM,MAG1,MAG2,NMETR,'NAME',STAT,O1,F1,...,O4,F4
            # R1-2,X1-2,SBASE1-2
            # WINDV1,NOMV1,ANG1,RATA1,RATB1,RATC1,COD1,CONT1,RMA1,RMI1,VMA1,VMI1,NTP1,TAB1,CR1,CX1
            # WINDV2,NOMV2
            # """

            tap = data[2][0]
            phi = data[2][2]

            if tap == 1 and phi == 0:
                transf = False
            else:
                transf = True
            param = {'bus1': data[0][0], 'bus2': data[0][1], 'u': data[0][11],
                     'b': data[0][8], 'r': data[1][0], 'x': data[1][1],
                     'trans': transf, 'tap': tap, 'phi': phi,
                     'Vn1': system.Bus.get(src='Vn', idx=data[0][0], attr='v'),
                     'Vn2': system.Bus.get(src='Vn', idx=data[0][1], attr='v'),
                     }
            system.add('Line', param)
        else:
            # I, J, K, CKT, CW, CZ, CM, MAG1, MAG2, NMETR, 'NAME', STAT, Ol, Fl,...,o4, F4
            # R1—2, X1—2, SBASE1—2, R2—3, X2—3, SBASE2—3, R3—1, X3—1, SBASE3—1, VMSTAR, ANSTAR
            # WINDV1, NOMV1, ANG1, RATA1, BATB1, RATC1, COD1, CONT1, RMA1, RMI1, VMA1, VMI1, NTP1, TAB1, CR1, CX1
            # WINDV2, NOMV2, ANG2, RATA2, BATB2, RATC2, COD2, CONT2, RMA2, RMI2, VMA2, VMI2, NTP2, TAB2, CR2, CX2
            # WINDV3, NOMV3, ANG3, RATA3, BATB3, RATC3, COD3, CONT3, RMA3, RMI3, VMA3, VMI3, NTP3, TAB3, CR3, CX3
            param = {'idx': max_bus + xf_3_count, 'name': '_'.join(str(data[0][:3])),
                     'Vn': system.Bus.get(src='Vn', idx=data[0][0], attr='v'),
                     'v0': data[1][-2], 'a0': data[1][-1] * deg2rad
                     }
            system.add('Bus', param)

            r = []
            x = []
            r.append((data[1][0] + data[1][6] - data[1][3])/2)
            r.append((data[1][3] + data[1][0] - data[1][6])/2)
            r.append((data[1][6] + data[1][3] - data[1][0])/2)
            x.append((data[1][1] + data[1][7] - data[1][4])/2)
            x.append((data[1][4] + data[1][1] - data[1][7])/2)
            x.append((data[1][7] + data[1][4] - data[1][1])/2)
            for i in range(0, 3):
                param = {'trans': True, 'bus1': data[0][i], 'bus2': max_bus+xf_3_count, 'u': data[0][11],
                         'b': data[0][8], 'r': r[i], 'x': x[i],
                         'tap': data[2+i][0], 'phi': data[2+i][2],
                         'Vn1': system.Bus.get(src='Vn', idx=data[0][i], attr='v'),
                         'Vn2': system.Bus.get(src='Vn', idx=data[0][0], attr='v'),
                         }
                system.add('Line', param)
            xf_3_count += 1

    for data in raw['swshunt']:
        # I, MODSW, ADJM, STAT, VSWHI, VSWLO, SWREM, RMPCT, ’RMIDNT’,
        # BINIT, N1, B1, N2, B2, ... N8, B8
        bus = data[0]
        vn = system.Bus.get(src='Vn', idx=bus, attr='v')
        param = {'bus': bus, 'Vn': vn, 'Sn': mva, 'u': data[3],
                 'b': data[9] / mva}
        system.add('Shunt', param)

    for data in raw['area']:
        # ID, ISW, PDES, PTOL, ARNAME
        param = {'idx': data[0], 'name': data[4],
                 # 'isw': data[1],
                 # 'pdes': data[2],
                 # 'ptol': data[3],
                 }
        system.add('Area', param)

    for data in raw['zone']:
        # """ID, NAME"""
        param = {'idx': data[0], 'name': data[1]}
        # TODO: add back
        # system.add('Region', param)

    return ret
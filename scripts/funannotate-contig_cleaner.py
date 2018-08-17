#!/usr/bin/env python3

import sys, subprocess, os, itertools, argparse
from Bio import SeqIO
from Bio.SeqIO.FastaIO import SimpleFastaParser

import logging
logger = logging.getLogger('AAFTF')

#setup menu with argparse
class MyFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def __init__(self,prog):
        super(MyFormatter,self).__init__(prog,max_help_position=48)
parser=argparse.ArgumentParser(prog='contig_cleaner.py', usage="%(prog)s [options] -i genome.fa -o cleaned.fa",
    description='''Script that removes short scaffolds that are duplicated elsewhere.''',
    epilog="""Written by Jon Palmer (2016) nextgenusfs@gmail.com""",
    formatter_class = MyFormatter)
parser.add_argument('-i','--input', required=True, help='Multi-fasta genome file')
parser.add_argument('-o','--out', required=True, help='Cleaned output (FASTA)')
parser.add_argument('-p','--pident', type=int, default=95, help='percent identity of contig')
parser.add_argument('-c','--cov', type=int, default=95, help='coverage of contig')
parser.add_argument('-m','--minlen', type=int, default=500, help='Minimum length of contig')
parser.add_argument('--exhaustive', action='store_true', help='Compute every contig, else stop at N50')
parser.add_argument('--method', default='minimap2', choices=['mummer', 'minimap2'], help='program to use for calculating overlaps')
parser.add_argument('--debug', action='store_true', help='Debug the output')
args=parser.parse_args()

def which(name):
    try:
        with open(os.devnull) as devnull:
            subprocess.Popen([name, '--version'], stdout=devnull, stderr=devnull).communicate()
    except OSError as e:
        if e.errno == os.errno.ENOENT:
            return False
    return True

def CheckDependencies(input):
    missing = []
    for p in input:
        if which(p) == False:
            missing.append(p)
    if missing != []:
        error = ", ".join(missing)
        logger.error("Missing Dependencies: %s.  Please install missing dependencies and re-run script" % (error))
        sys.exit(1)

def calcN50(input):
    lengths = []
    with open(input, 'rU') as infile:
        for id, sequence in SimpleFastaParser(infile):
            lengths.append(len(sequence))
    #now get N50
    lengths.sort()
    nlist = []
    for x in lengths:
        nlist += [x]*x
    if len(nlist) % 2 == 0:
        medianpos = int(len(nlist) / 2)
        N50 = int((nlist[medianpos] + nlist[medianpos-1]) / 2)
    else:
        medianpos = int(len(nlist) / 2)
        N50 = int(nlist[medianpos])
    return N50

def Sortbysize(input, n50):
    #sort records and return a list of scaffolds in descending size order
    contigs = []
    keep = []
    with open(input, 'rU') as input:
        records = list(SeqIO.parse(input, 'fasta'))
#        records.sort(cmp=lambda x,y: cmp(len(y),len(x)), reverse=True)
        for rec in reversed(sorted(records, key=lambda x: len(x))):
            length = len(rec.seq)
            if length >= args.minlen:
                if n50:
                    if length >= n50:
                        keep.append(rec.id)
                    else:
                        contigs.append(rec.id)
                else:
                    contigs.append(rec.id)
        return contigs, keep

def countfasta(input):
    count = 0
    with open(input, 'rU') as f:
        for line in f:
            if line.startswith (">"):
                count += 1
    return count

def softwrap(string, every=80):
    lines = []
    for i in range(0, len(string), every):
        lines.append(string[i:i+every])
    return '\n'.join(lines)
         
def generateFastas(input, index, Contigs, query):
    #loop through fasta once, generating query and reference
    contiglist = Contigs[index+1:] + keepers
    with open('query.fa', 'w') as qFasta:
        with open('reference.fa', 'w') as rFasta:
            with open(input, 'rU') as infile:
                for Id, Sequence in SimpleFastaParser(infile):
                    if Id == query:
                        qFasta.write('>%s\n%s\n' % (Id, softwrap(Sequence)))
                    elif Id in contiglist:
                        rFasta.write('>%s\n%s\n' % (Id, softwrap(Sequence)))

def runNucmer(query, reference, output):
    FNULL = open(os.devnull, 'w')
    subprocess.call(['nucmer', '-p', output, query, reference], stdout = FNULL, stderr = FNULL)
    input = output + '.delta'
    coord_out = output + '.coords'
    with open(coord_out, 'w') as coords:
        subprocess.call(['show-coords', '-r', '-c', '-l', '-T', '-o', '-I', '75', input], stdout = coords, stderr = FNULL)
    #now load in results and filter
    garbage = False #assume this is a good contig
    with open(coord_out, 'rU') as c:
        for line in itertools.islice(c, 4, None):
            cols = line.split('\t')
            match = (float(cols[6]), float(cols[9]))
            if match[0] > args.pident and match[1] > args.cov:
                print("%s appears duplicated: %i%% identity over %i%% of the contig. contig length: %s " % (output, match[0], match[1], cols[7]))
                #print match
                garbage = True
                break
        if not garbage:
            keepers.append(output)
        else:
        	repeats.append(output)
    os.remove(input)
    os.remove(coord_out)
    
def runMinimap2(query, reference, output, repeats, keepers):
    '''
    I have not found parameters that mirror mummer yet, do not use minimap method
    '''
    FNULL = open(os.devnull, 'w')
    minitmp = 'minimap.tmp'
    with open(minitmp, 'w') as out:
        subprocess.call(['minimap2', '-x', 'asm5', '-N5', reference, query], stdout = out, stderr = FNULL)
    #now load in results and filter
    garbage = False #assume this is a good contig
    with open(minitmp, 'rU') as data:
        for line in data:
            line = line.replace('\n', '')
            qID, qLen, qStart, qEnd, strand, tID, tLen, tStart, tEnd, matches, alnLen, mapQ = line.split('\t')[:12]
            pident = float(matches) / int(alnLen) * 100
            coverage = float(alnLen) / int(qLen) * 100
            #print qID, str(qLen), tID, matches, alnLen, str(pident), str(coverage)
            if pident > args.pident and coverage > args.cov:
                print("{} appears duplicated: {:.0f}% identity over {:.0f}% of the contig. contig length: {}".format(output, pident, coverage, qLen))
                garbage = True
                break
        if not garbage:
            keepers.append(output)
        else:
        	repeats.append(output)
    os.remove(minitmp)


#run some checks of dependencies first
if args.method == 'mummer':
    programs = ['nucmer', 'show-coords']
else:
    programs = ['minimap2']
CheckDependencies(programs)

#calculate N50 of assembly
n50 = calcN50(args.input)

global keepers
global repeats
keepers,repeats = ([],)*2
#now get list of scaffolds, shortest->largest
if args.exhaustive:
    scaffolds, keepers = Sortbysize(args.input, False)
else:
    scaffolds, keepers = Sortbysize(args.input, n50)

print("-----------------------------------------------")
PassSize = len(scaffolds)+len(keepers)
print("{:,} input contigs, {:,} larger than {:,} bp, N50 is {:,} bp".format(countfasta(args.input), PassSize, args.minlen, n50))
if args.exhaustive:
    print("Checking duplication of {:,} contigs".format(len(scaffolds)))
else:
    print("Checking duplication of {:,} contigs shorter than N50".format(len(scaffolds)))
print("-----------------------------------------------")
#now loop through the list
for i in range(0, len(scaffolds)):
    generateFastas(args.input, i, scaffolds, scaffolds[i])
    if args.method == 'mummer':
        runNucmer('query.fa', 'reference.fa', scaffolds[i])
    elif args.method == 'minimap2':
        runMinimap2('query.fa', 'reference.fa', scaffolds[i], repeats, keepers)
    os.remove('query.fa')
    os.remove('reference.fa')

print("-----------------------------------------------")
print("{:,} input contigs; {:,} larger than {:} bp; {:,} duplicated; {:,} written to file".format(countfasta(args.input), PassSize, args.minlen, len(repeats), len(keepers)))
if args.debug:
	print("\nDuplicated contigs are:\n{:}\n".format(', '.join(repeats)))
	print("Contigs to keep are:\n{:}\n".format(', '.join(keepers)))
#finally write a new reference based on list of keepers
with open(args.out, 'w') as output:
    with open(args.input, 'rU') as input:
        SeqRecords = SeqIO.parse(input, 'fasta')
        for rec in SeqRecords:
            if rec.id in keepers and not rec.id in repeats:
                SeqIO.write(rec, output, 'fasta')

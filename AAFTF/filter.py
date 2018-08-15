import sys, os, shutil, gzip, subprocess
import urllib.request



#logging
import logging
logger = logging.getLogger('AAFTF')

from AAFTF.resources import Contaminant_Accessions
from AAFTF.resources import SeqDBs
from AAFTF.resources import DB_Links

def run(parser,args):
    
    if not args.tmpdir:
        args.tmpdir = 'working_AAFTF'

    if not os.path.exists(args.tmpdir):
        os.mkdir(args.tmpdir)

    if not args.outdir:
        args.outdir = args.indir
        
    earliest_file_age = -1
    contam_filenames = []
    # db of contaminant (PhiX)
    for url in Contaminant_Accessions.values():
        acc = os.path.basename(url)
        acc_file = os.path.join(args.tmpdir,acc)
        contam_filenames.append(acc_file)
        if not os.path.exists(acc_file):
            urllib.request.urlretrieve(url,acc_file)
        if ( earliest_file_age < 0 or
             earliest_file_age < os.path.getctime(acc_file) ):
            earliest_file_age = os.path.getctime(acc_file)

    # download univec too
    url = DB_Links['UniVec']
    acc = os.path.basename(DB_Links['UniVec'])
    acc_file = os.path.join(args.tmpdir,acc)
    contam_filenames.append(acc_file)
    if not os.path.exists(acc_file):
        urllib.request.urlretrieve(url,acc_file)
        if ( earliest_file_age < 0 or
             earliest_file_age < os.path.getctime(acc_file) ):
            earliest_file_age = os.path.getctime(acc_file)
    
    if args.screen_accessions:
        for acc in args.screen_accessions:
            acc_file = os.path.join(args.tmpdir,acc+".fna")
            contam_filenames.append(acc_file)
            if not os.path.exists(acc_file):
                url = SeqDBs['nucleotide'] % (acc)
                urllib.request.urlretrieve(url,acc_file)
            if ( earliest_file_age < 0 or
                 earliest_file_age < os.path.getctime(acc_file) ):
                earliest_file_age = os.path.getctime(acc_file)


    if args.screen_urls:
        for url in args.screen_urls:
            url_file = os.path.join(args.tmpdir,os.basename(url))
            contam_filenames.append(url_file)
            if not os.path.exists(url_file):
                urllib.request.urlretrieve(url,url_file)
            if ( earliest_file_age < 0 or
                 earliest_file_age < os.path.getctime(url_file) ):
                earliest_file_age = os.path.getctime(url_file)

    # concat vector db
    contamdb = os.path.join(args.tmpdir,'contamdb')
    if ( not os.path.exists(contamdb) or
         ( os.path.getctime(contamdb) < earliest_file_age)):
         with open(contamdb, 'wb') as wfd:
             for fname in contam_filenames:
                 with open(fname,'rb') as fd: # reasonably fast copy for append
                     shutil.copyfileobj(fd, wfd)

    left = os.path.join(args.indir,args.prefix + "_1P")
    right = os.path.join(args.indir,args.prefix + "_2P")

    # could probably subroutine this for left and right but its not that hard to code it here
    if not os.path.exists(left):
        if os.path.exists(left + ".fastq"):
            left +=  ".fastq"
        elif os.path.exists(left + ".fastq.gz"):
            left += ".fastq.gz"

    if not os.path.exists(right):
        if os.path.exists(right + ".fastq"):
            right +=  ".fastq"
        elif os.path.exists(right + ".fastq.gz"):
            right += ".fastq.gz"

    if args.bowtie2 == '1':        
        if not os.path.exists(contamdb + ".1.bt2"):
            subprocess.call(['bowtie2-build',contamdb,contamdb])

        clean_reads = os.path.join(args.outdir,
                                   args.prefix + "_cleaned")

        if ( not os.path.exists(clean_reads + '_1.fq.gz') or
             os.path.getctime(clean_reads+'_1.fq.gz') < os.path.getctime(contamdb)):
            if args.pairing:
                DEVNULL = open(os.devnull, 'w')
                logger.info(['bowtie2','-x',contamdb,
                             '-p', str(args.cpus),'-q','--very-sensitive',
                             '-1',left,'-2',right,
                             '--un-conc-gz', clean_reads])
                subprocess.run(['bowtie2','-x',contamdb,
                                '-p', str(args.cpus),'-q','--very-sensitive',
                                '-1',left,'-2',right,
                                '--un-conc-gz', clean_reads+'.gz'],
                               stdout=DEVNULL)
                shutil.move(clean_reads+'.1.gz',
                            clean_reads+'_1.fq.gz')
                shutil.move(clean_reads+'.2.gz',
                            clean_reads+'_2.fq.gz')

            else:
                single = os.path.join(args.indir,
                                args.prefix + "_1U")
                DEVNULL = open(os.devnull, 'w')
                print(['bowtie2','-x',contamdb,
                                '-p', str(args.cpus),
                                '-q','--very-sensitive',
                                '-U',single,
                                '--un-conc-gz', clean_reads+'.gz'])
                subprocess.run( ['bowtie2','-x',contamdb,
                                '-p', str(args.cpus),
                                '-q','--very-sensitive',
                                '-U',single,
                                '--un-conc-gz', clean_reads+'.gz'],
                               stdout=DEVNULL)
                shutil.move(clean_reads+'.gz',
                            clean_reads+'_single.fq.gz')
                
    elif args.bwa == '1':
        print("do bwa")
        if not os.path.exists(contamdb + ".amb"):
            subprocess.call(['bwa','index',contamdb])
        clean_reads = os.path.join(args.outdir,
                                   args.prefix + "_cleaned")
        samfile = os.path.join(args.tmpdir,
                                   args.prefix + ".contam_map.sam")
        bamfile = os.path.splitext(samfile)[0] + ".bam"
        bamfileunmapped = os.path.join(args.tmpdir,
                                   args.prefix + ".contam_unmapped.bam")
        bamfileunmapsort = os.path.join(args.tmpdir,
                                   args.prefix + ".contam_unmapped_sort.bam")
        clean_reads += "_12.fq.gz"
        if not os.path.exist(samfile):
            outsam = open(samfile, 'w')
            subprocess.run(['bwa','mem','-t',
                            str(args.cpus),contamdb,
                            left, right],stdout=outsam)
            subprocess.run(['samtools','view','-@',str(args.cpus),
                        '-b',samfile, '-o',bamfile])
            subprocess.run(['samtools','view','-@',str(args.cpus),
                        '-b',bamfile, '-f', '12','-o',bamfileunmapped])
            subprocess.run(['samtools','sort','-@',str(args.cpus),'-n',
                        '-b',bamfileunmapped, '-o',bamfileunmapsort])

        subprocess.run(['bedtools','bamtofastq','-i',
                        bamfileunmapsort,'-fq', clean_reads])
        subprocess.run(['gzip',clean_reads])        
    elif args.bbmap == '1':
        print("do bbmap")
    else:
        print("Must specify bowtie2,bwa, or bbmap for filtering")
        logger.info("Must specify bowtie2,bwa, or bbmap for filtering")

            

#!/usr/bin/env python3
"""Various functions to convert msprime simulation file to run in Heng Li's fastARG program and back again.

When run as a script, takes an msprime simulation in hdf5 format, saves to fastARG input format (haplotype sequences), runs fastARG on it, converts fastARG output to msprime input (2 files), reads these into msprime outputs the haplotype sequences again, and checks that the

E.g. ./msprime_fastARG.py ../test_files/4000.hdf5 -x ../fastARG/fastARG

"""
import sys
import os.path
sys.path.insert(1,os.path.join(sys.path[0],'..','msprime')) # use the local copy of msprime in preference to the global one
import msprime
from warnings import warn
import logging

def msprime_hdf5_to_fastARG_in(msprime_hdf5, fastARG_filehandle):
    logging.debug("== Saving to fastARG input format ==")
    ts = msprime.load(msprime_hdf5.name)
    msprime_to_fastARG_in(ts, fastARG_filehandle)
    return(ts)

def msprime_to_fastARG_in(ts, fastARG_filehandle):
    for v in ts.variants(as_bytes=True):
        print(v.position, v.genotypes.decode(), sep="\t", file=fastARG_filehandle)
    fastARG_filehandle.flush()

def variant_matrix_to_fastARG_in(var_matrix, var_positions, fastARG_filehandle):
    assert len(var_matrix)==len(var_positions)
    iterator = zip(var_positions, var_matrix)
    pos, row = next(iterator) #first line does not begin with newline
    fastARG_filehandle.write(str(pos) + "\t" + "".join((str(v) for v in row)))
    for pos, row in iterator:
        fastARG_filehandle.write("\n" + str(pos) + "\t" + "".join((str(v) for v in row)))
    fastARG_filehandle.flush()

def get_cmd(executable, fastARG_in, seed):
    files = [fastARG_in.name if hasattr(fastARG_in, "name") else fastARG_in]
    exe = [str(executable), 'build'] + files
    if seed is not None:
        exe += ['-s', str(int(seed))]
    return exe

def variant_positions_from_fastARGin_name(fastARG_in):
    with open(fastARG_in) as fastARG_in_filehandle:
        return(variant_positions_from_fastARGin(fastARG_in_filehandle))

def variant_positions_from_fastARGin(fastARG_in_filehandle):
    import numpy as np
    fastARG_in_filehandle.seek(0) #make sure we reset to the start of the infile
    vp=[]
    for line in fastARG_in_filehandle:
        try:
            pos = line.split()[0]
            vp.append(float(pos))
        except:
            warn("Could not convert the title on the following line to a floating point value:\n {}".format(line))
    return(np.array(vp))

def fastARG_out_to_msprime_txts(
        fastARG_out_filehandle, variant_positions, tree_filehandle, mutations_filehandle,
        seq_len=None):
    """
    convert the fastARG output format (plus a list of positions) to 2 text
    files (tree and mutations) which can be read in to msprime we need to split
    fastARG records that extend over the whole genome into sections that cover
    just that coalescence point.
    """
    import csv
    import numpy as np
    logging.debug("== Converting fastARG output to msprime ==")
    fastARG_out_filehandle.seek(0) #make sure we reset to the start of the infile
    ARG_nodes={} #An[X] = child1:[left,right], child2:[left,right],... : serves as intermediate ARG storage
    mutations={}
    mutation_nodes=set() #to check there aren't duplicate nodes with the same mutations - a fastARG restriction
    seq_len = seq_len if seq_len is not None else  variant_positions[-1]+1 #if not given, hack seq length to max variant pos +1
    try:
        breakpoints = np.insert(np.diff(variant_positions)/2 + variant_positions[:-1], [0, len(variant_positions)-1], [0, seq_len])
    except:
        assert FALSE, \
            "Some variant positions seem to lie outside the sequence length (l={}):\n{}".format(
            seq_len, variant_positions)
    for line_num, fields in enumerate(csv.reader(fastARG_out_filehandle, delimiter='\t')):
        if   fields[0]=='E':
            srand48seed = int(fields[1])

        elif fields[0]=='N':
            haplotypes, loci = int(fields[1]), int(fields[2])
            csv.field_size_limit(max(csv.field_size_limit(), loci)) #needed because the last line has a field as long as loci


        elif fields[0]=='C' or fields[0]=='R':
            #coalescence or recombination events -
            #coalescence events should come in pairs
            #format is curr_node, child_node, seq_start_inclusive, seq_end_noninclusive, num_mutations, mut_loc1, mut_loc2, ....
            curr_node, child_node, left, right, n_mutations = [int(i) for i in fields[1:6]]
            if curr_node<child_node:
                warn("Line {} has an ancestor node_id less than the id of its children, so node ID cannot be used as a proxy for age".format(line_num))
                sys.exit()
            #one record for each node
            if curr_node not in ARG_nodes:
                ARG_nodes[curr_node] = {}
            if child_node in ARG_nodes[curr_node]:
                warn("Child node {} already exists for node {} (line {})".format(child_node, curr_node, line_num))
            ARG_nodes[curr_node][child_node]=[breakpoints[left], breakpoints[right]]
            #mutations in msprime are placed as ancestral to a target node, rather than descending from a child node (as in fastARG)
            #we should check that (a) mutation at the same locus does not occur twice
            # (b) the same child node is not used more than once (NB this should be a fastARG restriction)
            if n_mutations:
                if child_node in mutation_nodes:
                    warn("Node {} already has some mutations: some more are being added from line {}.".format(child_node, line_num))
                mutation_nodes.add(child_node)
                for pos in fields[6:(6+n_mutations)]:
                    m = variant_positions[int(pos)]
                    if m in mutations:
                        warn("Duplicate mutations at a single locus: {}. One is from node {}.".format(m, child_node))
                    else:
                        mutations[m]=child_node


        elif fields[0]=='S':
            #sequence at root
            root_node = int(fields[1])
            base_sequence = fields[2]
        else:
            warn("Bad line format - the fastARG file has a line that does not begin with E, N, C, R, or S:\n{}".format("\t".join(fields)))

    #Done reading in

    if min(ARG_nodes.keys()) != haplotypes:
            warn("The smallest internal node id is expected to be the same as the number of haplotypes, but it is not ({} vs {})".format(min(ARG_nodes.keys()), haplotypes))

    for node,children in sorted(ARG_nodes.items()): #sort by node number == time
        #look at the break points for all the child sequences, and break up into that number of records
        breaks = set()
        for leftright in children.values():
            breaks.update(leftright)
        breaks = sorted(breaks)
        for i in range(1,len(breaks)):
            leftbreak = breaks[i-1]
            rightbreak = breaks[i]
            #NB - here we could try to input the values straight into an msprime python structure,
            #but until this feature is implemented in msprime, we simply output to a correctly formatted msprime text input file
            tree_filehandle.write("{}\t{}\t{}\t".format(leftbreak, rightbreak,node))
            tree_filehandle.write(",".join([str(cnode) for cnode, cspan in sorted(children.items()) if cspan[0]<rightbreak and cspan[1]>leftbreak]))
            tree_filehandle.write("\t{}\t{}\n".format(node, 0))

    for pos, node in sorted(mutations.items()):
        mutations_filehandle.write("{}\t{}\n".format(pos, node))

    tree_filehandle.flush()
    mutations_filehandle.flush()

def fastARG_root_seq(fastARG_out_filehandle):
    fastARG_out_filehandle.seek(0)
    for line in fastARG_out_filehandle:
        spl = line.split(None,3)
        if spl[0]=="S":
            root_seq = spl[2]
            fastARG_out_filehandle.seek(0)
            return([seq!="0" for seq in root_seq])
    warn("No root sequence found in '{}'".format(fastARG_out_filehandle.name))
    return([])

def msprime_txts_to_fastARG_in_revised(
        tree_filehandle, mutations_filehandle, root_seq, fastARG_filehandle=None,
        hdf5_outname=None, simplify=True):
    if hdf5_outname:
        logging.debug("== Saving new msprime ARG as hdf5 and also as input format for fastARG ==")
    else:
        logging.debug("== Saving new msprime ARG as input format for fastARG ==")
    tree_filehandle.seek(0)
    mutations_filehandle.seek(0)

    ts = msprime.load_txt(tree_filehandle.name, mutations_filehandle.name)
    if simplify:
        try:
            ts = ts.simplify()
        except:
            ts.dump("bad.hdf5")
            assert FALSE, "Failed to simplify the TreeSequence - original dumped to bad.hdf5"
    if hdf5_outname:
        ts.dump(hdf5_outname)
    if fastARG_filehandle:
        for j, v in enumerate(ts.variants(as_bytes=True)):
            if root_seq[j]:
                print(
                    v.position, v.genotypes.decode().translate(str.maketrans('01','10')),
                    sep="\t", file=fastARG_filehandle)
            else:
                print(v.position, v.genotypes.decode(), sep="\t", file=fastARG_filehandle)
        fastARG_filehandle.flush()
    return(ts)


def main(sim, fastARG_executable, fa_in, fa_out, tree, muts, fa_revised, hdf5_outname=None):
    """
    pass sim as either a filehandle to an hdf5 file or a set of simulate params
    """
    try:
        ts = msprime.simulate(**sim)
        logging.debug("Creating new simulation with {}".format(sim))
        msprime_to_fastARG_in(ts, fa_in)
    except:
        ts = msprime_hdf5_to_fastARG_in(sim, fa_in)
    run_fastARG(fastARG_executable, fa_in, fa_out)
    root_seq = fastARG_root_seq(fa_out)
    fastARG_out_to_msprime_txts(fa_out, variant_positions_from_fastARGin(fa_in.name), tree, muts)
    new_ts = msprime_txts_to_fastARG_in_revised(tree, muts, root_seq, simplify=False)
    simple_ts = msprime_txts_to_fastARG_in_revised(tree, muts, root_seq, fa_revised, hdf5_outname)
    logging.debug(
        "Initial num records = {}, fastARG (simplified) = {}, fastARG (unsimplified) = {}".format(
        ts.get_num_records(), simple_ts.get_num_records(), new_ts.get_num_records()))
    logging.debug("These numbers are expected to be in ascending order ")
    if ts.get_num_records() > simple_ts.get_num_records() \
            or simple_ts.get_num_records() > new_ts.get_num_records():
        warn("Numbers not in ascending order!")
    if os.stat(fa_in.name).st_size == 0:
        warn("Initial fastARG input file is empty")
    elif filecmp.cmp(fa_in.name, fa_revised.name, shallow=False) == False:
        warn("Initial fastARG input file differs from processed fastARG file")
    else:
        print("Conversion via fastARG has worked! Input and output files are identical")


if __name__ == "__main__":
    import argparse
    import filecmp
    import os
    default_sim={'sample_size':2000, 'Ne':1e4, 'length':1000000, 'mutation_rate':2e-8, 'recombination_rate':2e-8}
    parser = argparse.ArgumentParser(description='Check fastARG imports by running msprime simulation through it and back out')
    parser.add_argument('hdf5file', default=None, nargs="?", type=argparse.FileType('r', encoding='UTF-8'), help='an msprime hdf5 file. If none, a simulation is created with {}'.format(default_sim))
    parser.add_argument('--fastARG_executable', '-x', default="fastARG", help='the path & name of the fastARG executable')
    parser.add_argument('outputdir', nargs="?", default=None, help='the directory in which to store the intermediate files. If None, files are saved under temporary names')
    args = parser.parse_args()


    if args.outputdir == None:
        print("Saving everything to temporary files")
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile("w+") as fa_in, \
             NamedTemporaryFile("w+") as fa_out, \
             NamedTemporaryFile("w+") as tree, \
             NamedTemporaryFile("w+") as muts, \
             NamedTemporaryFile("w+") as fa_revised:
            main(args.hdf5file or default_sim, args.fastARG_executable, fa_in, fa_out, tree, muts, fa_revised)
    else:
        prefix = os.path.splitext(os.path.basename(args.hdf5file.name))[0]
        full_prefix = os.path.join(args.outputdir, prefix)
        with open(full_prefix + ".haps", "w+") as fa_in, \
             open(full_prefix + ".fastarg", "w+") as fa_out, \
             open(full_prefix + ".msprime", "w+") as tree, \
             open(full_prefix + ".msmuts", "w+") as muts, \
             open(full_prefix + ".haps_revised", "w+") as fa_revised:
            main(args.hdf5file or default_sim, args.fastARG_executable, fa_in, fa_out, tree, muts, fa_revised, full_prefix + ".hdf5_revised")

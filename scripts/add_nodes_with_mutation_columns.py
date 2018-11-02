import msprime
import pandas as pd
#from evaluation import mk_sim_name_from_row
from plots import mk_sim_name_from_row
dataset = "tsinfer_performance"
df = pd.read_csv("../data/{}.csv".format(dataset))
df["internal_nodes"] = None
df["internal_nodes_with_mutations"] = None
for index, row in df.iterrows(): 
    fn = mk_sim_name_from_row(row, "../data/raw__NOBACKUP__/{}/simulations".format(dataset), None)
    fn += ".hdf5"
    ts = msprime.load(fn)
    nodes_with_muts = set()
    for mut in ts.mutations():
        nodes_with_muts.add(mut.node)
    n = df.loc[index, 'internal_nodes'] = ts.num_nodes - ts.num_samples
    m = df.loc[index, 'internal_nodes_with_mutations'] = len(nodes_with_muts - set(ts.samples()))
    print(m/n)

# try to calculate number of nodes with a informative recombination above them.
# this is difficult because of 
#   https://github.com/hyanwong/treeseq-inference/issues/4#issuecomment-424715002



df.to_csv("../data/{}_new.csv".format(dataset))
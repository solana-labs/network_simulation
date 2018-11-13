import hashlib
from collections import Counter
import pygraphviz as pgv

import matplotlib.pyplot as plt

from IPython.core.debugger import set_trace

class NetworkStatus():
    def __init__(self):

        self.network_tick = []
        ## {tick: [# of branches at depth (index)]}
        self.unique_chains = {}
        self.current_partition = {}
        ## current active set
        self.current_as = {}
        
        
    def print_snapshot(self, snapshot):
        ## snapshot of form {validator : {slot : block}}
        ## print tree of current network chain status
        ## nodes show % votes
        ## Nodes are blocks, edges time between block, labels are vote counts/% across given slot
        
        if snapshot.shape[0] < 2: return
        
        g = pgv.AGraph(strict = True, directed = True)

        edge_ctr = {}
        branch_ctr = {}
        for col_num in range(snapshot.shape[1]):


            cur_snapshot = snapshot[col_num]


            ## create node ids 
            ## node IDs should be hash of all blocks in it's history --> unique branches

#            block_hashes = []
#            for i, block in enumerate(cur_snapshot):
#                if block == '0':
#                    block_hashes.append('0')
#                else:
#                    cur_block_hash = block+'-'+'-'.join(cur_snapshot[:i])
#                    cur_block_hash = hashlib.sha256(cur_block_hash).hexdigest()
#                    block_hashes.append(cur_block_hash)

#            cur_edges = zip(block_hashes, block_hashes[1:])
            
            cur_edges = zip(cur_snapshot, cur_snapshot[1:])

            ## count branch
            branch_ctr[tuple(cur_edges)] = 1 if tuple(cur_edges) not in branch_ctr else branch_ctr[tuple(cur_edges)] + 1
            
            for t, cur_edge in enumerate(cur_edges):
                ##ce = ["{}... T={}".format(node[:5],t) for node in cur_edge]
                ## converting to hex, display with slot time
                ## hacky way to avoid self loops (e.g. 0 -> 0)
                
                ce = tuple(["{}... T={}".format(node[:5], t + i) for i, node in enumerate(cur_edge)])
                if ce in edge_ctr:
                    edge_ctr[ce] += 1
                else:
                    edge_ctr[ce] = 1

                ## add weight label
                ## t is key to identify time
                g.add_edge(ce[0], ce[1], str(t),
                           weight = edge_ctr[ce],
                           label = "{0:.0%}".format(1.*edge_ctr[ce]/snapshot.shape[1]))
                
##        for e in range(len(g.edges())):
##            g.get_edge(g.edges()[e][0],g.edges()[e][1]).attr["label"] = 1.*edge_ctr[g.get_edge(g.edges()[e][0],g.edges()[e][1])]/sum(edge_ctr.values())

        ##print(g)

        g.layout(prog = "dot")
        network_file_name = "./figures/nwk_n{}_t{:02}".format(snapshot.shape[1],snapshot.shape[0]-1)
        g.draw(network_file_name+".png")

    def update_status(self, network, chain_analysis = False, print_snapshot = False):

        t = network.time        
        snapshot = network.snapshot(t)
        
        if print_snapshot == True: self.print_snapshot(snapshot)
            
        self.network_tick.append(t)
        
        self.current_partition[t] = len(network.partition_nodes)
        self.current_as[t] = len(network.nodes)
        
        ## write # of unique chains

        if chain_analysis == True:
            cur_chains = {}
            for col_num in range(snapshot.shape[1]):
                cur_snapshot = snapshot[col_num]

                for depth_num, block in enumerate(cur_snapshot):
                    str_chain_depth = cur_snapshot[:depth_num+1].to_string()
                    cur_chain_hash = hashlib.sha256(str_chain_depth).hexdigest()
                
                    if depth_num not in cur_chains:
                        cur_chains[depth_num] = [cur_chain_hash]
                    else:
                        cur_chains[depth_num].append(cur_chain_hash)

                        self.unique_chains[snapshot.shape[0]-1] = map(len,map(Counter,cur_chains.values()))
    
#            cur_snapshot = snapshot[col_num].to_string()
#            unique_chains.append(hashlib.sha256(cur_snapshot).hexdigest())

#        self.unique_chains.append(len(dict(Counter(unique_chains))))

    def plot_branches(self):

        plt.ion()
        ticks = self.unique_chains.keys()
        ticks.sort()
        
        fig, axarr = plt.subplots(2,len(ticks), sharex=True, figsize = (24, 12.8))

        for i, tick in enumerate(ticks):
            axarr[0][i].scatter(range(len(self.unique_chains[tick])), self.unique_chains[tick])
            ## other plot
            axarr[1][i].scatter(range(len(self.unique_chains[tick])), self.current_partition.values()[:(tick+1)])
        fig.show()

                   
           #        marker = 'o',
           #        c = 'r',
            #       edgecolor = 'b'
           #        )

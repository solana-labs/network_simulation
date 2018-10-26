########################
## Network Sim
## 
## TODO
## - update get_current_lockout using last *voted* block, not just block heights
## - pool size != network ticks
## - if leader is drop-out, no data in forks, need ability to 'request from network'
## - validate lockout calc
## - use virtual ticks when node received blokc
## - add node stakes
## - slot transmission times
## - destaking / leakage
##   - higher destaking rate for non-voters in smaller partition
## - viz and monitoring
## - fix NetworkStatus bug due to data missing from dropouts
## - confirm timing alignment
########################
import network as solana
reload(solana)

from random import randint

from collections import Counter

import numpy as np
np.random.seed(11)
from itertools import compress

from IPython.core.debugger import set_trace

########################
## Network Constants
########################
POOL_SIZE = 50
VALIDATOR_IDS = range(0, POOL_SIZE)
AVG_LATENCY = 0 ## currently << transmission_time
NETWORK_PARTITION = 0.1 ## tmp static partition
########################
## Functions
########################

def poisson_latency(latency):
    return lambda: 1 + int(random.gammavariate(1, 1) * latency)

########################
## Sim
########################
def run_simulation():

    ## Config network
    GENESIS = solana.Block(initial_validator_set = VALIDATOR_IDS)
    network = solana.Network(poisson_latency(AVG_LATENCY), GENESIS)

    ## Attach nodes to network
    nodes = [solana.Node(network, i) for i in VALIDATOR_IDS]


    ## Assign leader rotration
    leaders = np.random.choice(VALIDATOR_IDS, POOL_SIZE, replace = False)
    network.round_robin = leaders

    ## Set network partition
    ## Currently static...

    network_status = solana.NetworkStatus()

##    logging.info("Partitioned nodes: ",network.partition_nodes)
    ## run sim...
    cur_partition_time = 0
    for t in range(POOL_SIZE):

        ## generate partitions
        if cur_partition_time == 0 :
            network.partition_nodes = list(compress(VALIDATOR_IDS,\
                                                [np.random.uniform() < NETWORK_PARTITION for _ in nodes]))
            cur_partition_time = randint(1,POOL_SIZE/5)
        else:
            cur_partition_time -= 1

        
        network.tick()
        network.status()

        n_branches = len(Counter([str(node.chain) for node in network.nodes]))
        print("# of branches: %s:" % n_branches)

        
        network_snapshot = network.snapshot(t)

        network_status.print_snapshot(network_snapshot)

##        print("%s: %s"  % (t, str(set([n.chain[0] for n in network.nodes]))))
        
    return network

def main():
    print("Run simulation...")
    network = run_simulation()
    ## network.print_network_status()

if __name__ == '__main__':
    main()

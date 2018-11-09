########################
## Network Sim
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

import network_status as ns
reload(ns)

from random import randint

from collections import Counter

import numpy as np
np.random.seed(11)
from itertools import compress



## DEBUG
from IPython.core.debugger import set_trace
import time


########################
## Network Constants
########################
POOL_SIZE = 50
VALIDATOR_IDS = range(0, POOL_SIZE)
AVG_LATENCY = 0 ## currently << transmission_time
NETWORK_PARTITION = 0.15 ## tmp static partitionb
########################
## Functions
########################

def poisson_latency(latency):
    return lambda: 1 + int(random.gammavariate(1, 1) * latency)

########################
## Sim
########################
def run_simulation(network_status):
    
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

##    logging.info("Partitioned nodes: ",network.partition_nodes)
    ## run sim...
    cur_partition_time = -1
    network.partition_nodes = []
    long_lived_partition = False

    for t in range(POOL_SIZE*2):

        ## each tick, some % chance of long-lived partition
        if long_lived_partition == False and cur_partition_time < 0:
            long_lived_partition = np.random.uniform() < 0.05


        
        ## generate partitions
        if long_lived_partition == True:
            network.partition_nodes = list(compress(VALIDATOR_IDS,\
                                                    [np.random.uniform() < NETWORK_PARTITION for _ in nodes]))
            cur_partition_time = randint(1,POOL_SIZE/5) ## next partition
            long_lived_partition = False
        

        print("Partition size: %s for: %s" % (len(network.partition_nodes), cur_partition_time))
            

        network.tick()

        do_unique_chain_analysis = ((t + 1) % 10) == 0
        network_snapshot = network_status.update_status(network, chain_analysis = do_unique_chain_analysis, print_snapshot = False)
        
#        network_snapshot = network.snapshot(t)
#        network_status.print_snapshot(network_snapshot)

                ## if time is up, reset partition nodes
        if cur_partition_time <= 0:
            network.partition_nodes = []
            cur_partition_time = -1
        else:
            cur_partition_time -= 1

    return network


def main():
    print("Run simulation...")
    t0 = time.time()
    network_status = ns.NetworkStatus()
    network = run_simulation(network_status)
    t1 = time.time()
    print("Simulation time: %.2f" % (t1 - t0))
    set_trace()
    network_status.plot_branches()

        
##    network_status.plot_unique_chains()

if __name__ == '__main__':
    main()

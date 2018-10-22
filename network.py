######################################
## Simulating Solana branch consensus
## TODO
## - validate lockout calc
## - incorporate saved forks into chain
## - use virtual ticks when node received blokc
## - add node stakes
## - slot transmission times
## - destaking / leakage
##   - higher destaking rate for non-voters in smaller partition
## - viz and monitoring
## - fix NetworkStatus bug due to data missing from dropouts
## - confirm timing alignment
######################################

import random
random.seed(11)
import numpy as np
np.random.seed(11)
import pandas as pd

from IPython.core.debugger import set_trace

import logging, sys
logging.basicConfig(filename='global.log',filemode = 'w', level=logging.DEBUG)


########################
## Lockout Function
########################
MIN_LOCKOUT = 2 ## TMP: unit is slot, to be PoH?
MAX_LOCKOUT = 20736000 ## ~4 months in slot time (2 slots / second)

def calc_lockout_time(current_time, prev_vote_time, k = 1, base = 2,
                      min_lockout = MIN_LOCKOUT, max_lockout = MAX_LOCKOUT):

    z = (current_time - prev_vote_time) / k
    exp_z = k * (base ** (z + 1))
    lockout_time = (min_lockout + exp_z)

    if lockout_time > max_lockout:
        lockout_time = max_lockout
    return lockout_time

########################
## Network
########################

class Network():
    def __init__(self, latency, genesis):
        self.nodes = []
        self.round_robin = []
        self.latency = latency
        self.transmission_time = 1e6 # currently >> than latency
        self.time = 0
        self.msg_arrivals = {}
        self.dropout_rate = 0.1
        self.partition_nodes = []
        self.genesis = genesis

    def status(self):
        ## quick summary of network status

        ## Node agreement
        node_heads = [node.chain[max(node.chain.keys())] for node in self.nodes]
        print("Node agreement: %d%%" % (100*(1 - float(len(set(node_heads))-1)/len(node_heads))))
        
    def get_chains(self):
        ## DataFrame structure of node chains over time

        chain_data = pd.DataFrame(index = range(len(self.nodes)))

        for t in range(self.time)[:-1]:
            ## get block hashes from each node at t
            ## drop last slot because may have nodes
            ## with missing blocks from dropouts
            
            current_blocks = []
            for i, node in enumerate(self.nodes):
                ### TODO: bug here due to dropouts not having slot data
                if t == 1 and i == 191: set_trace() 
                current_blocks.append(str(node.chain[t]))
            chain_data[t] = pd.Series(current_blocks, index = chain_data.index)
        chain_data.index.name = 'Node'
        chain_data.columns.name = 'Time'
        return(chain_data)

    def broadcast(self, block_transmission):
        ## Called by leader node to transmit block to rest of network


        logging.debug("Leader broadcast: %s" % (block_transmission.get_block().hash))
        
        for i, current_node in enumerate(self.nodes):

            ## TMP: ignore delay
            ## delay = self.latency()

            ## replace with msg.block_time?
            ## send to next slot
            next_step = self.time + 1

            if next_step not in self.msg_arrivals:
                self.msg_arrivals[next_step] = []
            self.msg_arrivals[next_step].append((i, block_transmission))

    ## Network::tick
    def tick(self):
        ## Deliver all data broadcast in this slot
        ## Random network dropouts at node level and
        ## partitioned nodes
        ## TODO: partitioned nodes not currently separate network
        ##       they just miss any broadcasts currently

        if self.time in self.msg_arrivals: ## messages to be sent
            for node_index, block_transmission in self.msg_arrivals[self.time]:
                if node_index not in self.partition_nodes: ## partitioned from receiving?
                    self.nodes[node_index].receive_block(block_transmission, self.time)
            del self.msg_arrivals[self.time]

#        for node in self.nodes:
#            logging.debug("Node %s received: %s" % (node.id, node.chain[max(node.chain.keys())]))

        ## not ideal,  keep for now
        for node in self.nodes:
            ## if no data was transmiktted
            ## add virtual tick to chain
            if self.time not in node.chain:
                node.chain[self.time] = 0 

            ## find leader
            if np.random.uniform() > self.dropout_rate:
                node.tick(self.time)
            else:
                logging.debug("Dropout! Node: %d at time: %d" % (node.id, self.time))

        self.time += 1

class BlockTransmission():
    ## Data transmission unit
    ## Data: previous virtual ticks and block
    
    def __init__(self, block = None, previous_ticks = []):
        self._previous_ticks = previous_ticks
        self._block = block

    def set_block(self, block):
        self._block = block

    def get_block(self):
        return self._block

    def set_previous_ticks(self, ticks):
        self._previous_ticks = ticks

    def get_previous_ticks(self):
        return self._previous_ticks

        
class Block():
    def __init__(self, initial_validator_set = [], parent=None, created_by = None, created_at = 0):
        self.hash = random.randrange(10**30)
        self.parent = parent
        self.block_time = created_at
        if not self.parent: ## must be genesis
            self.prevhash = 0
            self.votes = {0:initial_validator_set}
            return
        # Set our block time and our prevhash
        self.prevhash = self.parent.hash
        self.votes = {self.block_time : [created_by]} ## creation of block is a vote
        

    def add_vote(self, vote_time, validator_id):
        if vote_time not in self.votes: ## first vote
            self.votes[vote_time] = [validator_id]
        else:
            self.votes[vote_time].append(validator_id)

    def get_hash_chain(self):
        ## returns a dict of time:hashes of blocks connected to self, excluding current block
        tmp_block = self
        block_hashes = {tmp_block.block_time:tmp_block.hash}
        while tmp_block.parent is not None:
            block_hashes[tmp_block.parent.block_time] = tmp_block.parent.hash
            tmp_block = tmp_block.parent

        ## backfill virtual blocks
        for j in range(self.block_time):
            if j not in block_hashes:
                block_hashes[j] = 0
            
        return(block_hashes)


class Node():
    def __init__(self, network, id):
        self.id = id
        self.network = network
        network.nodes.append(self)
        # Received blocks
        self.received = {network.genesis.hash: network.genesis}
        self.chain = {0: network.genesis.hash} ## time:hash, helps keep self.received in order
        self.lockouts = {network.genesis.hash, MIN_LOCKOUT} ## each node has lockouts attached to specific blocks/votes
        self.forks = {0 : {0 : network.genesis}} ## {broadcast time : {last non-virtual block time, broadcast block}}
        
    def receive_block(self, block_transmission, time):

        if time <= max(self.chain.keys()): ## latest time
            raise ValueError("Node ", self.id, " cannot accept block at height ", time)



        block = block_transmission.get_block()
        previous_ticks = block_transmission.get_previous_ticks()
        
        ## time for which leader last saw data
        last_block_time = time - (len(previous_ticks) + 1)

        #       print((self.id, time))
        ## 
        lockout_time = self.get_current_lockout(block, time)
        if lockout_time > time + 1: set_trace()
        
        ## if locked out, store broadcast block and ticks
        ## write virtual block
        if lockout_time > time:
            ## Locked out from voting!
            ## block, last_block_time
            self.forks[time] = {last_block_time, block}
#            print("Saving fork at %s with last block time %s due to lockout %s" % (time, last_block_time, lockout_time))
        else:
            ## TODO: check if we insert fork here
            ## receive block and vote
            self.received[block.hash] = block
            self.chain[time] = block.hash
            block.add_vote(time, self.id)

            
    def get_current_lockout(self, current_block, time):
        ## returns time when lockout on current branch expires
        ## e.g. if current_time < lockout time,  voting on leader block/branch is slashable
        ##  curent_time => lockout time: okay to vote on leader block/branch
        ##  
        ## lockout alg:
        ## - find earliest (lowest PoH) block in Node chain not included in block transmission
        ## - if lockout from that block is <= (=?) current block slot (PoH) vote on currrent chain

        ## Get history of blocks from current block
        ## Compare to history from Node's most up-to-date block
        current_block_hashes = current_block.get_hash_chain()

        ## failing in self.chain[time - 1] == 0  (rather than a hash)
        for i in range(1, time +1):
            previous_node_hash = self.chain[time - i]
            if previous_node_hash != 0: break

        
        node_block_hashes = self.received[previous_node_hash].get_hash_chain()


        ## loop through time, up to previous block time
        prev_block_time = min([max(current_block_hashes.keys()),\
                               max(node_block_hashes.keys())])

        ## Find slot where/if branch has occured
        ## i.e. find first slot where two block histories differ
        branch_time = -1
        for i in range(prev_block_time+1):
            if node_block_hashes[i] != current_block_hashes[i]:
                branch_time = i
                break

        ## TODO: validate lockout 
        if branch_time < 0:
            ## same branch, no lockout
            return time
        else:
            return time + calc_lockout_time(time, branch_time)

    ## Node::tick
    def tick(self, _time):

        ## leader:
        if self.network.round_robin[_time] == self.id:
            logging.debug("I'm the leader! Node: %s at time: %s" % (self.id, _time))

            ## find last slot time with block (not ticks)
            last_block_time = max([block_time for block_time, block in self.chain.items() if block > 0])

            # to be delived in next round
            new_block = Block(parent = self.received[self.chain[last_block_time]], created_by = self.id, created_at = _time +1) 


            ## bundle times of last N ticks (0s)
            previous_ticks = []
            for key in self.chain.keys()[::-1]:
                if self.chain[key] ==  0:
                    previous_ticks.append(key)
                else:
                    break

            new_block_transmission = BlockTransmission(block = new_block, previous_ticks = previous_ticks)
            ## generate delays and send to msg_arrivals of network
            ## to be received by network in _time + 1

            self.network.broadcast(new_block_transmission)

            ## TODO: does leader receive now?
            ## self.receive_block(new_block, _time)

class NetworkStatus():
    ## TODO: incomplete class
    def __init__(self, chain):
        self.chain = chain

    def print_network_status(self):
        print(self.chain)

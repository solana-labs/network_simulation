######################################
## Simulating Solana branch consensus
## TODO
## - reset block cache!
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

#from graphviz import Digraph
import pygraphviz as pgv

from collections import Counter

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
    lockout_time = int(min_lockout + exp_z)

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
        self.active_set = len(self.nodes)
        
    def status(self):
        ## quick summary of network status

        ## Node agreement
        node_heads = [node.chain[max(node.chain.keys())] for node in self.nodes]
        print("Node agreement: %d%%" % (100*(1 - float(len(set(node_heads))-1)/len(node_heads))))
        
    def snapshot(self, _time):
        ## DataFrame structure of node chains over time
        print(_time)

        chain_data = {}
        for i, node in enumerate(self.nodes):
            branch_chain = {}

            ## is latest block virtual
            if node.chain[_time] == 0:
                ## branch chain 
                branch_chain = {int(k):str(v.get_block().hash) for k,v in node.cache.items()}

            chain = {int(k):str(v) for k,v in node.chain.items() if k not in branch_chain}
            chain = dict(chain.items() + branch_chain.items())
                
##            if node.chain[_time] == 0:
##                ## virtual tick, get cached blocks
##                t_ctr = _time
##                while node.chain[t_ctr] == 0:
##                    if t_ctr in node.cache:
##                        branch_chain[t_ctr] = str(node.cache[t_ctr].get_block().hash)
##                    else:
##                        branch_chain[t_ctr] = str(0)
##                    t_ctr -= 1
                    
##                chain = {int(k):str(v) for k,v in node.chain.items() if v != 0}
                
            chain_data[i] = chain
            
        return(pd.DataFrame(chain_data))


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

        ## PLACEHOLDER: set active set
        self.active_set = len(self.nodes)
        
        if self.time in self.msg_arrivals: ## messages to be sent
            for node_index, block_transmission in self.msg_arrivals[self.time]:
                if node_index not in self.partition_nodes: ## partitioned from receiving?
                    self.nodes[node_index].receive_block(block_transmission, self.time)
            del self.msg_arrivals[self.time]

#        for node in self.nodes:
#            logging.debug("Node %s received: %s" % (node.id, node.chain[max(node.chain.keys())]))

        ## not ideal
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
            cur_votes = self.votes[vote_time]
            if validator_id in cur_votes:
                ValueError("Double voting on block? Maybe during rollback.")
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
        self.received = {network.genesis.hash : network.genesis}
        self.chain = {0 : network.genesis.hash} ## time:hash, helps keep self.received in order
        self.lockouts = {network.genesis.hash : MIN_LOCKOUT} ## lockouts assosiated with votes for blocks
        self.cache = {} ##{0 : BlockTransmission(block = network.genesis, previous_ticks = [])}  ## when locked out, store current transmission
        self.finalized = {0 : network.genesis} ## TESTING - store finalized blocks when observes 2/3 votes
        self.active_set = {0 : network.active_set}
        
    def receive_block(self, block_transmission, time):

        if time <= max(self.chain.keys()): ## latest time
            raise ValueError("Node ", self.id, " cannot accept block at height ", time)

        ## save active set for future finality calcs
        self.active_set[time] = self.network.active_set

        
        block = block_transmission.get_block()
        previous_ticks = block_transmission.get_previous_ticks()
        
        ## need to check if locked out
        ## Locked out if i have a record of voting on a
        ## transmission that isn't included in leader's broadcast,
        ## and if any of my vote lockout times are past current PoH
        
        node_block_hashes = self.received.keys()
        leader_hash_chain = block.get_hash_chain()

        ## if I have any blocks that aren't in leader's block chain,
        ## leader is broadcasting a branch
        on_same_branch = all([node_block in leader_hash_chain.values() for node_block in node_block_hashes])

        if not on_same_branch:

            ## what is Node's maximum lockout on earliest
            ## block not on leader branch
            
            lockout_time = self.get_current_lockout(block, time)
            #max_lockout = max(self.lockouts.values())

            if lockout_time > time:
                ## if locked out:  don't vote, don't update lockouts, store transmission
                self.cache[time] = block_transmission
                return
            else:
                ## switching branches
                ## vote on latest block chain, fill in blocks if necessary from cache, register votes on all the blocks
                ## re-write / fill in blocks from cache
                ## Keep track of depth of rollback (E&M)
                ## TODO: how to update lockouts?
                rollback_depths = []
                for t in self.chain.keys():

                    ## only roll back blocks that are different
                    if self.chain[t] == leader_hash_chain[t]:
                        continue
                    else:
                        ## remove current block from received
                        if self.chain[t] != 0: del self.received[self.chain[t]]
                        self.chain[t] = leader_hash_chain[t]

                        ## FIXME: optimize
                        err_reassigned = False
                        ## find block associated with that hash
                        cur_leader_block = block
                        while cur_leader_block != self.network.genesis:
                            if cur_leader_block.hash == self.chain[t]:
                                self.received[self.chain[t]] = cur_leader_block
                                cur_leader_block.add_vote(t, self.id)
                                err_reassigned = True
                                break
                            else:
                                cur_leader_block = cur_leader_block.parent
                        if not err_reassigned: ValueError("Block re-assignment failed during rollback!")
                        rollback_depths.append(t)
                print("Rollback depth: %s" % max(rollback_depths))

                ## receive head block
                self.received[block.hash] = block
                self.chain[time] = block.hash
                block.add_vote(time, self.id)

                ## update lockouts
                self.update_lockouts(time)
                self.lockouts[block.hash] = time + MIN_LOCKOUT

                ## clear cache
                self.cache = {}

        else:
            ## same branch, vote, update lockouts
            self.received[block.hash] = block
            self.chain[time] = block.hash
            block.add_vote(time, self.id)

            ## update lockouts
            self.update_lockouts(time)
            self.lockouts[block.hash] = time + MIN_LOCKOUT

    def update_lockouts(self, time):
        ## run through votes (blocks), re-calc lockouts with current time
        ## re-writing lockouts entirely out of laziness
        ## could deal with rollbacks much better
        self.lockouts = {}
        for block_hash in self.chain.values():
            if block_hash == 0: continue
            block_time = self.received[block_hash].block_time
            self.lockouts[block_hash] = time + calc_lockout_time(time, block_time, k = 1.5)
        
            
    def get_current_lockout(self, current_block, time):
        ## returns time when lockout on current branch expires
        ## e.g. if current_time < lockout time,  voting on leader block/branch is slashable
        ##  curent_time => lockout time: okay to vote on leader block/branch
        ##  
        ## lockout alg:
        ## - find earliest (lowest PoH) block in Node chain not included in block transmission
        ## - if lockout from that block is <= (=?) current block slot (PoH) vote on currrent chain


        ## FIXME: should chain history come from node, rather than block?
        ## !! chain from block != chain on node
        ## find last non virtual block
        previous_node_hash_time = len(self.chain) - 1
        for i in range(1, time + 1):
            previous_node_hash = self.chain[time - i]
            if previous_node_hash != 0:
                break
            else:
                previous_node_hash_time -= 1

        ## get chain history from last non-virtual block
        #node_block_hashes = self.received[previous_node_hash].get_hash_chain()

        node_block_hashes = {k: v for k, v in self.chain.iteritems() if k <= previous_node_hash_time}
        

        ## Get history of blocks from current block
        ## Compare to history from Node's most up-to-date block
        current_block_hashes = current_block.get_hash_chain()
#        current_block_hashes = {k: v for k, v in current_block_hashes.iteritems() if v != 0}
        
        ## loop through time, up to previous block time
        prev_block_time = min([max(current_block_hashes.keys()),\
                               max(node_block_hashes.keys())])

        ## Find slot where/if branch has occured
        ## i.e. find first slot where two block histories differ
        branch_time = -1
        for i in range(prev_block_time+1):
            if node_block_hashes[i] != current_block_hashes[i] and node_block_hashes[i] != 0:
                branch_time = i
                break

        ## TODO: validate lockout 
        if branch_time < 0:
            ## same branch, no lockout
            return 0
        else:
            return self.lockouts[self.chain[branch_time]]

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

    def print_snapshot(self, snapshot):
        ## snapshot of form {validator : {slot : block}}
        ## print tree of current network chain status
        ## nodes show % votes
        ## Nodes are blocks, edges time between block, labels are vote counts/% across given slot

        g = pgv.AGraph(strict = True, directed = True)

        edge_ctr = {}

        for col_num in range(snapshot.shape[1]):

            cur_edges = zip(snapshot[col_num].tolist(),
                            snapshot[col_num].tolist()[1:])

            for t, cur_edge in enumerate(cur_edges):
                ##ce = ["{}... T={}".format(node[:5],t) for node in cur_edge]
                ## converting to hex, display with slot time
                ## hacky way to avoid self loops (e.g. 0 -> 0)

                ce = tuple(["{}... T={}".format(format(int(node),'02x')[:5], t + i) for i, node in enumerate(cur_edge)])                
                if ce in edge_ctr:
                    edge_ctr[ce] += 1
                else:
                    edge_ctr[ce] = 1

                #if g.get_edge(cur_edge)
                ## t is key to identify time
                g.add_edge(ce[0], ce[1], str(t), weight = edge_ctr[ce])
                           
        if snapshot.shape[0] == 8: set_trace()
        print(g)
        g.layout(prog = "dot")
        network_file_name = "./figures/nwk_n{}_t{:02}".format(snapshot.shape[1],snapshot.shape[0])
        g.draw(network_file_name+".png")

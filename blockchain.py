import hashlib
import json
from textwrap import dedent
from time import time
from uuid import uuid4
from urllib.parse import urlparse
from flask import Flask, jsonify, request
import requests

class Blockchain (object):
	def __init__ (self):
		self.chain = []
		self.current_transactions = []
		self.nodes = set()
		# create the first block
		self.new_block(previous_hash=1, proof=100)
	
	def register_node (self, address):
		"""
		Adds a new node to the list of nodes
		:param address: <str> Address of the node, eg "http://84.86.42.91:4242"
		:return: None
		"""
		parsed_url = urlparse(address)
		self.nodes.add(parsed_url.netloc)
	
	def new_block (self, proof, previous_hash=None):
		"""
		Creates a new block in the chain
		:param proof: <int> Proof provided by the proof of work algorithm
		:param previous_hash: <std> Hash of previous block (optional)
		:return: <dict> New Block
		"""
		block = {
			'index': len(self.chain)+1,
			'timestamp': time(),
			'transactions': self.current_transactions,
			'proof': proof,
			'previous_hash': previous_hash or self.hash(self.chain[-1])
		}
		# reset the current list of transactions
		self.current_transactions = []
		self.chain.append(block)
		return block

	def new_transaction (self, sender, recipient, amount):
		"""
		Creates a new transaction to go into the next block
		:param sender: <str> Address of sender
		:param recipient: <str> Address of recipient
		:param amount: <int> Amount
		:return: <int> The index of the block holding the transaction
		"""
		self.current_transactions.append({
			'sender': sender,
			'recipient': recipient,
			'amount': amount
		})
		return self.last_block['index'] + 1
	
	def valid_chain (self, chain):
		"""
		Determines if a blockchain is valid
		
		:param chain: <list> The blockchain
		:return: <bool> 
		"""
		
		last_block = chain[0]
		i = 1
		
		while i < len(chain):
			block = chain[i]
			print(f'{last_block}')
			print(f'{block}')
			print("\n------------\n")
			if block['previous_hash'] != self.hash(last_block):
				return False
				
			if not self.valid_proof(last_block['proof'], block['proof']):
				return False
				
			last_block = block
			i += 1
			
		return True
	
	def resolve_conflicts(self):
		"""
		Consensus Algorithm finds the longest chain
		
		:return: <bool> True if chain was replaced
		"""
		
		neighboors = self.nodes
		new_chain = None
		my_length = len(self.chain)
		
		# Check all chains in the network
		for node in neighboors:
			response = requests.get(f'http://{node}/chain')
			if response.status_code == 200: # http says OK
				her_length = response.json()['length']
				chain = response.json()['chain']
				if her_length > my_length and self.valid_chain(chain):
					my_length = her_length
					new_chain = chain
					
		if new_chain:
			self.chain = new_chain
			return True
			
		return False
				
	
	@staticmethod
	def hash(block):
		"""
		Hashes a block using sha256sum
		:param block: <dict> Block
		:return: <str>
		"""
		# Order the Dictionary
		block_string = json.dumps(block, sort_keys=True).encode()
		return hashlib.sha256(block_string).hexdigest()
	
	@property
	def last_block (self):
		# return last block in chain
		return self.chain[-1]

	def proof_of_work(self, last_proof):
		"""
		Finds q such that hash(pq) contains 4 leading zeroes
		where p is the previous q
		:param last_proof: <int>
		:return: <int>
		"""
		proof=0
		while self.valid_proof(last_proof, proof) is False:
			proof += 1
		return proof

	@staticmethod
	def valid_proof (last_proof, proof):
		"""
		Validate that hash(pq) contains 4 leading zeroes
		:param last_proof: <int> p
		:param proof: <int> q
		:return: <bool>
		"""
		guess = f"{last_proof}{proof}".encode()
		guess_hash = hashlib.sha256(guess).hexdigest()
		return guess_hash[:4] == "0000"

# Instantiate our Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the Blockchain
blockchain = Blockchain()

@app.route('/mine', methods=['GET'])
def mine():
	# run the proof of work algorithm to find the next proof
	last_block = blockchain.last_block
	last_proof = last_block['proof']
	proof = blockchain.proof_of_work(last_proof)

	# miner must receive a reward for finding the proof
	blockchain.new_transaction(
		sender="0",
		recipient=node_identifier,
		amount=1
	)

	# add block to chain
	previous_hash = blockchain.hash(last_block)
	block = blockchain.new_block(proof, previous_hash)

	response = {
		'message': "New Block Forged",
		'index': block['index'],
		'transaction': block['transactions'],
		'proof': block['proof'],
		'previous_hash': block['previous_hash']
	}
	return jsonify(response), 200 # server says OK

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
	values = request.get_json()
	if values == None:
		return 'Error: failed to parse json', 400 # server says BAD
	# check lla required fields
	required = ['sender', 'recipient', 'amount']
	if not all (k in values for k in required):
		return 'Error: incomplete data', 400
	# create a new transaction
	index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount']	)
	response = {'message': f'Transaction will be added to block #{index}'}
	return jsonify(response), 201 # server says ADDED

@app.route('/chain', methods=['GET'])
def full_chain():
	response = {
		'chain': blockchain.chain,
		'length': len(blockchain.chain)
	}
	return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
	values = request.get_json()
	if values == None:
		return 'Error: Failed to parse json (?)', 400 # server says BAD

	nodes = values.get('nodes')
	if nodes is None:
		return 'Error: Please supply a valid list of nodes', 400 
	
	for node in nodes:
		blockchain.register_node(node)
		
	response = {
		'message': 'New nodes have been added',
		'total_nodes': list(blockchain.nodes)
	}
	return jsonify(response), 201 # server says ADDED

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
	replaced = blockchain.resolve_conflicts()
	if replaced:
		response = {
			'message': 'My chain was replaced',
			'new_chain': blockchain.chain
		}
		return jsonify(response), 201 # ADDED
	else:
		response = {
			'message': 'My chain was authorative',
			'chain': blockchain.chain
		}
		return jsonify(response), 200 # OK
	
	

if __name__ == '__main__':
	app.run(host='127.0.0.1', port=4242)



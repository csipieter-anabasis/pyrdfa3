# -*- coding: utf-8 -*-
#
# Copyright (c) 2011 Daniel Gerber.
#
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.

# Modified by Ivan Herman, 2011, to produce a JSON-LD serialization: http://json-ld.org/spec/latest/json-ld-syntax

"""

"""
import sys

if sys.version_info[1] >= 7 :
	from collections import OrderedDict
else :
	from pyRdfa.extras.odict import odict as OrderedDict

from rdflib.serializer import Serializer
from rdflib.term import URIRef, BNode, Literal
from rdflib	import RDF  as ns_rdf
from rdflib	import RDFS as ns_rdfs

class JsonSerializer(Serializer):
	__doc__ = __doc__

	def __init__(self, graph):
		self.graph  = graph
		self.vocab  = None

	def serialize(self, stream, base=None, encoding='utf-8', **kwds):
		d = self._build(base=base, **kwds)
		if sys.version_info[1] >= 6 :
			import json
			json.dump(d, stream, ensure_ascii = False, indent=4)
		else :
			import simplejson
			simplejson.dump(d, stream, ensure_ascii = False, indent=4)

	def _build(self, base=None, prefix_map=None, encode_literal=None):
		"""Returns dict to serialize."""
		if encode_literal:
			assert callable(encode_literal)
			self._encode_literal = encode_literal

		self.base = base        
		self.prefix_map = PrefixMap(self.graph.namespaces())
		if prefix_map:
			self.prefix_map.update(prefix_map)

		self._initialize_subjects()
		self._rdfa_vocabulary_usage()

		# Fill in the content of the json objects 
		for s in self.all_subjects.keys() :
			if self.vocab and s == self.vocab_owner : continue
			# Get the subject structure
			subj = self.all_subjects[s]
			# Get the possible types
			types = [ t for t in self.graph.objects(s,ns_rdf["type"]) ]
			if len(types) == 1 :
				subj["@type"] = self._get_node_ref(t)
			elif len(types) > 1 :
				subj["@type"] = [ self._get_node_ref(t) for t in types ]

			# Get the other properties
			for p in self.graph.predicates(s) :
				if p == ns_rdf["type"] : continue
				pobj = self._predicate(p)
				objs = [ o for o in self.graph.objects(s,p) ]
				# The cardinality of objs makes a big difference...
				if len(objs) == 0 :
					# Should not happen, though
					continue
				elif len(objs) == 1 :
					subj[pobj] = self._object(objs[0], s)
				else :
					subj[pobj] = [ self._object(ob, s) for ob in objs ]
					
		#######################################################################
		# Yet another beautification: if a top level object has no parent and is a blank node,
		# the @subject is unnecessary.
		for s in self.top_subjects :
			if len([ p for (p,x,y) in self.graph.triples((None, None, s)) ]) == 0 :
				if isinstance(s, BNode) :
					self.all_subjects[s].pop("@subject",None)
					
		#######################################################################
		# Put all together now in the top level object
		_json_obj = OrderedDict()

		# Add the @context part
		if self.base or len(self.prefix_map.used_keys) > 0 or self.vocab :
			context = OrderedDict()
			if self.base :
				context["@base"] = self.base
			for k,v in self.graph.namespaces() :
				if k in self.prefix_map.used_keys :
					context[k] = "%s" % v
			if self.vocab :
				context["@vocab"] = self.vocab
			_json_obj["@context"] = context

		# Add the top level objects; the content of these have been filled by the previous steps
		if len(self.top_subjects) == 1 :
			subj = self.all_subjects[self.top_subjects.pop()]
			for k in subj.keys() :
				_json_obj[k] = subj[k]
		elif len(self.top_subjects) > 1 :
			_json_obj["@subject"] = [ self.all_subjects[s] for s in self.top_subjects ]

		return _json_obj
	
	def _initialize_subjects(self) :
		# First get all the subjects in one place
		# all subjects are represented by a json object, store those, too
		# The initial list of subjects is also stored in the top_subject array,
		# ie, the list of those subjects that will appear on top of the serialized json output
		self.top_subjects = set([ s for s in self.graph.subjects() ])		
		self.all_subjects = {}
		for s in self.top_subjects :
			js_struct = OrderedDict()
			# This may have to be refined to remove blank nodes in a chain link...
			js_struct["@subject"] = self._get_node_ref(s)
			self.all_subjects[s] = js_struct
			
		# Now the chains have to be found
		self.chain_links = set()
		for s in self.top_subjects :
			# see the number of parents, ie, the number of other subjects for which this subject appear as an object.
			# if the number is exactly one, this means this subject may appear in a chaining structure
			if len([ p for (p,x,y) in self.graph.triples((None, None, s)) ]) == 1 :
				self.chain_links.add(s)

	def _get_node_ref(self, ident):
		"Returns the property name / local identifier for this node."
		if isinstance(ident, URIRef):
			if self.vocab and ident.startswith(self.vocab) :
				return ident.replace(self.vocab,'',1)
			else :
				return self.prefix_map.shrink(ident) or self.relativize(ident)
		elif isinstance(ident, BNode):
			return "_:%s" % ident
		raise TypeError('Expected URIRef or BNode instance, got %r' % ident)

	_predicate = _get_node_ref
	
	def _object(self, ident, parent):
		"Returns a json-serializable."
		if isinstance(ident, Literal):
			return self._encode_literal(ident)
		else :
			# This is a bnode or a URI ref. We have to see if it is a possible chain link
			if ident in self.chain_links :
				# Yep!
				# This object should be removed from the list of top level subjects
				self.top_subjects.discard(ident)
				# The parent must me removed from the chain_links, if there...
				self.chain_links.discard(parent)
				# The json structure of this object should be linked from the parent; the
				# content will be filled later
				jsubj = self.all_subjects[ident]
				# If this happens to be a BNode, this is the case when the BNode id is unnecessary
				if isinstance(ident, BNode) :
					jsubj.pop("@subject",None)
				
				return jsubj
			else :
				# no, this is either a leaf or a subject with multiple parents
				if isinstance(ident, BNode) :
					return "_:%s" % ident
				else :
					retval = OrderedDict()
					retval["@iri"] = self._get_node_ref(ident)
					return retval
	
	def _encode_literal(self, literal):
		if literal.datatype != None :
			retval = OrderedDict()
			retval["@literal"] = literal
			retval["@datatype"] = self._get_node_ref(literal.datatype)
			return retval
		elif literal.language != None and literal.language != "" :
			retval = OrderedDict()
			retval["@literal"] = literal
			retval["@language"] = literal.language
			return retval
		else :
			return literal

	# This part could/should be removed if not used with RDFa...
	def _rdfa_vocabulary_usage(self) :
		from pyRdfa	import RDFA_VOCAB
		# See if a vocabulary has been used at all and, if yes, whether there is only one
		vocabs = [ (s,p,o) for s,p,o in self.graph.triples((None, RDFA_VOCAB, None)) ]
		# if there is no vocab, or if there is more than one, there is nothing we can do...
		if len(vocabs) == 1 :
			self.vocab       = vocabs[0][2]
			self.vocab_owner = vocabs[0][0]
			parents  = [ p for (p,x,y) in self.graph.triples((None, None, self.vocab_owner)) ]
			children = [ p for (x,y,p) in self.graph.triples((self.vocab_owner, None, None)) ]
			# See if this is the only apperance of the vocab owner; if so, it should be removed from further processing
			if len(parents) == 0 and len(children) == 1:
				# the subject should be removed
				self.top_subjects.discard(self.vocab_owner)
		else :
			self.vocab       = None
			self.vocab_owner = None

class PrefixMap(dict):
	"""A mapping of prefixes to URIs.
	
	Keeps URIs and CURIEs apart, unlike 
	http://www.w3.org/TR/rdf-interfaces/#idl-def-PrefixMap .
	"""

	def __init__(self, parent=None, *args, **kwds):
		dict.__init__(self, *args, **kwds)
		self.parent = parent and dict(parent) or None
		self.used_keys = set()
		
	def shrink(self, uriref):
		"Returns a CURIE or None."
		for pfx, ns in self.iteritems():
			if uriref.startswith(ns):
				self.used_keys.add(pfx)
				return '%s:%s' % (pfx, uriref.replace(ns,'',1))
		if self.parent:
			for pfx, ns in self.parent.iteritems():
				if uriref.startswith(ns):
					self[pfx] = ns
					self.used_keys.add(pfx)
					return '%s:%s' % (pfx, uriref.replace(ns,'',1))

	def resolve(self, curie):
		"Returns an URIRef or None."
		prefix, s, relative_ref = curie.partition(':')
		if prefix in self:
			return URIRef(self[prefix] + relative_ref)
		elif self.parent and prefix in self.parent:
			return URIRef(self.parent[prefix] + relative_ref)
